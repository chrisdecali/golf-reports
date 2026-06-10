#!/usr/bin/env python3
"""
Golf Reports MCP server (stdio).

Exposes the local ingest + render pipeline to Claude Desktop (Chat / Cowork / Code
tabs). Runs LOCALLY on the user's machine, so it has network to arccos/ghin, the
user's credentials, matplotlib, and the local filesystem — the cloud Cowork VM does
not, which is why the engine lives here (see Codex/architecture notes).

Env:
  GOLF_STORE   data dir the pull scripts write + render reads  (default ~/arccos_out)
  GOLF_INGEST  dir holding the pull scripts (default: the ingest/ dir bundled next to this server)
  GOLF_REPORTS output dir for HTML/PDF  (default GOLF_STORE/reports)

Tools: list_rounds, round_stats, render_round, get_report_paths,
       sync_arccos, sync_ghin, import_18birdies, logout, trends, compare_rounds, export_dispersion.
"""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import time

HOME = os.path.expanduser("~")
STORE = os.environ.get("GOLF_STORE", os.path.join(HOME, "arccos_out"))
_DEFAULT_INGEST = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ingest"))
INGEST = os.environ.get("GOLF_INGEST", _DEFAULT_INGEST)
REPORTS = os.environ.get("GOLF_REPORTS", os.path.join(STORE, "reports"))
RENDER_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "render")
sys.path.insert(0, os.path.abspath(RENDER_DIR))

import gen_combined as gc      # noqa: E402
import gen_gps_pdf             # noqa: E402
import trends as trends_mod    # noqa: E402
import dispersion as dispersion_mod  # noqa: E402

from mcp.server.fastmcp import FastMCP  # noqa: E402

mcp = FastMCP("golf-reports")


_SYNC_COOLDOWN_S = 600
_last_sync: dict[str, float] = {}


def _mark_sync(script: str) -> None:
    _last_sync[script] = time.time()


def _cooldown_left(script: str) -> str | None:
    left = _SYNC_COOLDOWN_S - (time.time() - _last_sync.get(script, 0))
    if left > 0:
        return f"cooldown: {script} ran recently — try again in {int(left)}s (protects the API)"
    return None


def _run(script: str, *args: str, timeout: int = 600) -> str:
    """Run an ingest script with the same Python, cwd=INGEST so OUT_DIR=STORE."""
    path = os.path.join(INGEST, script)
    if not os.path.exists(path):
        return f"error: {script} not found in {INGEST} (set GOLF_INGEST)"
    os.makedirs(STORE, exist_ok=True)
    lock_path = os.path.join(STORE, ".sync.lock")
    try:
        import fcntl
    except ImportError:
        fcntl = None  # Windows: no flock; single-user desktop, low collision risk
    with open(lock_path, "w") as lock:
        if fcntl is not None:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return "error: another sync is already running — wait for it to finish"
        try:
            r = subprocess.run([sys.executable, path, *args], cwd=INGEST,
                               capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return f"error: {script} timed out"
        out_lines = (r.stdout or "").strip().splitlines()
        tail = "\n".join(out_lines[-5:])
        if r.returncode == 0:
            return "ok: " + (tail or "done")
        err = (r.stderr or "").strip()[-1000:]
        return f"exit {r.returncode}:" + (f" {tail}" if tail else "") + (f"\nstderr: {err}" if err else "")


@mcp.tool()
def list_rounds() -> list[dict]:
    """List the golfer's rounds (newest last). Reads the local store."""
    path = os.path.join(STORE, "rounds_summary.csv")
    if not os.path.exists(path):
        return [{"error": f"no rounds_summary.csv in {STORE} — run sync_arccos first"}]
    with open(path, newline="", encoding="utf-8") as f:
        return [{"round_id": r.get("round_id"), "date": r.get("date"),
                 "course": r.get("course"), "score": r.get("score"),
                 "score_to_par": r.get("score_to_par")} for r in csv.DictReader(f)]


@mcp.tool()
def round_stats(round_id: str = "") -> dict:
    """Key stats for one round (default newest): SG by category, GIR/FW/scramble,
    putting make% by distance, approach proximity, peer carry gaps."""
    d = gc.compute(STORE, round_id or None)
    return {k: d[k] for k in ("round_id", "course", "date", "score", "score_to_par",
            "gir_pct", "fairway_pct", "scramble_pct", "putts", "sg", "sg_by_band",
            "putting", "approach", "peer_label", "peer_carry", "gps_check")}


@mcp.tool()
def render_round(round_id: str = "") -> dict:
    """Render one round (default newest) to an HTML report (satellite map + stats)
    and a matplotlib shot-map PDF. Returns local file paths. Open the HTML in a
    browser for the satellite tiles; the PDF is the shareable artifact."""
    rid = round_id or None
    report = gc.gen(STORE, REPORTS, rid)
    pdf = gen_gps_pdf.gen(STORE, REPORTS, rid)
    return {"report_html": report, "shotmaps_pdf": pdf,
            "note": "Open the HTML in a normal browser for satellite tiles."}


@mcp.tool()
def get_report_paths() -> list[str]:
    """List already-rendered report files in the reports dir."""
    if not os.path.isdir(REPORTS):
        return []
    return sorted(os.path.join(REPORTS, f) for f in os.listdir(REPORTS)
                  if f.endswith((".html", ".pdf")))


@mcp.tool()
def sync_arccos() -> str:
    """Pull the latest Arccos rounds into the local store (auto-login via stored
    accessKey). Run sync first when asked about recent rounds."""
    if (cd := _cooldown_left("pull_arccos.py")):
        return cd
    out = _run("pull_arccos.py")
    if out.startswith("ok:"):
        _mark_sync("pull_arccos.py")
    return out


@mcp.tool()
def sync_ghin() -> str:
    """Pull the official GHIN handicap + score history into the local store."""
    if (cd := _cooldown_left("pull_ghin.py")):
        return cd
    out = _run("pull_ghin.py")
    if out.startswith("ok:"):
        _mark_sync("pull_ghin.py")
    return out


@mcp.tool()
def import_18birdies(archive_path: str) -> str:
    """Import an 18Birdies account-data export (18Birdies_archive.json) into the store."""
    if not archive_path:
        return "error: give the path to your 18Birdies_archive.json"
    if any(ord(ch) < 32 for ch in archive_path):
        return "error: invalid characters in path"
    resolved = os.path.realpath(os.path.expanduser(archive_path))
    home = os.path.realpath(HOME)
    if not resolved.startswith(home + os.sep):
        return "error: archive must be a file inside your home directory"
    if not resolved.endswith(".json"):
        return "error: expected a .json file (the 18Birdies_archive.json export)"
    if not os.path.isfile(resolved):
        return f"error: file not found: {resolved}"
    return _run("pull_18birdies.py", resolved)


@mcp.tool()
def logout() -> str:
    """Delete stored Arccos + GHIN credentials from this machine (file + OS keychain)."""
    removed = []
    ghin_path = os.path.join(HOME, ".ghin_creds.json")
    if os.path.exists(ghin_path):
        try:
            with open(ghin_path, encoding="utf-8") as f:
                email = json.load(f).get("email")
            if email:
                import keyring
                keyring.delete_password("golf-reports-ghin", email)
                removed.append("keychain entry")
        except Exception:
            pass  # no keyring backend / no stored entry — file removal still proceeds
    for p in (os.path.join(HOME, ".arccos_creds.json"), ghin_path):
        if os.path.exists(p):
            os.remove(p)
            removed.append(os.path.basename(p))
    return "removed: " + (", ".join(removed) if removed else "nothing")


@mcp.tool()
def trends() -> dict:
    """Scoring/handicap/stat trends across ALL sources (Arccos + GHIN +
    18Birdies): rolling scoring averages, WHS index + trajectory + projection,
    SG-category trends (needs >=2 Arccos rounds). Call after syncs. Lead with
    the worst SG category when the user asks where they're losing strokes."""
    return trends_mod.trends(STORE)


@mcp.tool()
def compare_rounds(round_id_a: str, round_id_b: str) -> dict:
    """Compare two Arccos rounds: SG deltas by category, score/putts deltas,
    biggest swing."""
    return trends_mod.compare_rounds(STORE, round_id_a, round_id_b)


@mcp.tool()
def export_dispersion() -> dict:
    """(Re)generate <store>/dispersion.json — per-club total-distance/lateral
    model (schema v1.0, golfsmart bridge artifact; distances are GPS total,
    carry+roll). Check per-club `confidence` and `source_weight` — low/small
    means prior-dominated, caveat accordingly."""
    path = dispersion_mod.write(STORE)
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    return {"path": path, "clubs": len(d["clubs"]),
            "rounds_with_gps": d["player"]["rounds_with_gps"]}


if __name__ == "__main__":
    mcp.run()

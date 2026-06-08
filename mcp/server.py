#!/usr/bin/env python3
"""
Golf Reports MCP server (stdio).

Exposes the local ingest + render pipeline to Claude Desktop (Chat / Cowork / Code
tabs). Runs LOCALLY on the user's machine, so it has network to arccos/ghin, the
user's credentials, matplotlib, and the local filesystem — the cloud Cowork VM does
not, which is why the engine lives here (see Codex/architecture notes).

Env:
  GOLF_STORE   data dir the pull scripts write + render reads  (default ~/arccos_out)
  GOLF_INGEST  dir holding pull_arccos.py / pull_ghin.py / pull_18birdies.py
               (default ~ ; its ./arccos_out must equal GOLF_STORE)
  GOLF_REPORTS output dir for HTML/PDF  (default GOLF_STORE/reports)

Tools: list_rounds, round_stats, render_round, get_report_paths,
       sync_arccos, sync_ghin, import_18birdies, logout.
"""

from __future__ import annotations

import csv
import os
import subprocess
import sys

HOME = os.path.expanduser("~")
STORE = os.environ.get("GOLF_STORE", os.path.join(HOME, "arccos_out"))
INGEST = os.environ.get("GOLF_INGEST", HOME)
REPORTS = os.environ.get("GOLF_REPORTS", os.path.join(STORE, "reports"))
RENDER_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "render")
sys.path.insert(0, os.path.abspath(RENDER_DIR))

import gen_combined as gc      # noqa: E402
import gen_gps_pdf             # noqa: E402

from mcp.server.fastmcp import FastMCP  # noqa: E402

mcp = FastMCP("golf-reports")


def _run(script: str, *args: str, timeout: int = 600) -> str:
    """Run an ingest script with the same Python, cwd=INGEST so OUT_DIR=STORE."""
    path = os.path.join(INGEST, script)
    if not os.path.exists(path):
        return f"error: {script} not found in {INGEST} (set GOLF_INGEST)"
    try:
        r = subprocess.run([sys.executable, path, *args], cwd=INGEST,
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return f"error: {script} timed out"
    out = (r.stdout or "").strip().splitlines()
    return ("ok: " if r.returncode == 0 else f"exit {r.returncode}: ") + \
           (out[-1] if out else (r.stderr or "").strip()[-300:])


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
    return _run("pull_arccos.py")


@mcp.tool()
def sync_ghin() -> str:
    """Pull the official GHIN handicap + score history into the local store."""
    return _run("pull_ghin.py")


@mcp.tool()
def import_18birdies(archive_path: str) -> str:
    """Import an 18Birdies account-data export (18Birdies_archive.json) into the store."""
    if not archive_path or not os.path.exists(os.path.expanduser(archive_path)):
        return "error: give the path to your 18Birdies_archive.json"
    return _run("pull_18birdies.py", os.path.expanduser(archive_path))


@mcp.tool()
def logout() -> str:
    """Delete stored Arccos + GHIN credentials from this machine."""
    removed = []
    for p in (os.path.join(HOME, ".arccos_creds.json"), os.path.join(HOME, ".ghin_creds.json")):
        if os.path.exists(p):
            os.remove(p)
            removed.append(os.path.basename(p))
    return "removed: " + (", ".join(removed) if removed else "nothing")


if __name__ == "__main__":
    mcp.run()

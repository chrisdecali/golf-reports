# golf-reports Phase 1 "Ship it" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make golf-reports publishable as a public Claude Desktop plugin (security + reliability fixes) and close the daily loop: cron sync → new round detected → render → Telegram alert.

**Architecture:** All fixes are in-place edits to the existing ingest/render/MCP files — no restructuring. New code: `tests/` (pytest, first tests in repo), `bin/post_round_alert.py` (cron alert), and edits to the *home-dir* pipeline (`~/arccos_update.sh`, crontab) which lives outside this repo. Spec: `docs/superpowers/specs/2026-06-10-phase1-ship-it-design.md`.

**Tech Stack:** Python 3.12 stdlib, `mcp` (FastMCP), `matplotlib`, `openpyxl`, `keyring` (new, optional backend), `pytest` (dev). Telegram via raw `urllib` POST (polo-index pattern).

**Key facts for a zero-context engineer:**
- Repo: `/home/cole/golf-reports`. Run tests from repo root: `python3 -m pytest tests/ -v`.
- `~/pull_arccos.py`, `~/pull_ghin.py`, `~/arccos_shots_geo.py` are byte-identical copies of `ingest/*` (verified 2026-06-10). Task 11 replaces them with symlinks.
- The production cron (`crontab: 0 12 * * 1 /home/cole/arccos_cron.sh` → `~/arccos_update.sh`) runs the home-dir copies with venv `~/arccos-env/bin/python`, writes to `~/arccos_out/`, pushes to public GitHub repo `chrisdecali/arccos-sg-baseline`. Cole deliberately publishes his GPS — after Task 3 the cron must set `GOLF_INCLUDE_GPS=1` (Task 11 does this).
- `render/gen_combined.py` `compute()` is pure: reads `rounds_summary.csv`, `holes.csv`, `shots.csv` from a store dir, returns a dict. Renderers (`_html`, `gen_gps_pdf.gen`) consume that dict.
- MCP server (`mcp/server.py`) imports render modules directly and shells out to ingest scripts via `_run()`.

---

### Task 1: Test harness + fixture store + compute() baseline test

**Files:**
- Create: `tests/__init__.py` (empty)
- Create: `tests/conftest.py`
- Create: `tests/test_compute.py`
- Modify: `requirements.txt` (dev note line)

- [ ] **Step 1: Create `tests/__init__.py` (empty file) and `tests/conftest.py`**

```python
"""Shared fixtures: a tiny synthetic store dir that compute() can read."""
import csv
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "render"))
sys.path.insert(0, os.path.join(REPO, "ingest"))
sys.path.insert(0, os.path.join(REPO, "mcp"))


def _write_csv(path, cols, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


@pytest.fixture
def store(tmp_path):
    """Two rounds, two holes each. Round r2 is newest (last row).
    Round r2 hole 2 has score_to_par=None (the R2 crash case).
    Course name of r1 is hostile (the S3 XSS case)."""
    s = str(tmp_path / "store")
    os.makedirs(s)

    round_cols = ["round_id", "date", "course", "tee_name", "tee_yards", "slope",
                  "rating", "holes", "score", "par", "score_to_par", "putts",
                  "gir_hits", "gir_pct", "fairway_pct", "scramble_pct",
                  "sg_total_arccos", "sg_off_tee_arccos", "sg_approach_arccos",
                  "sg_short_arccos", "sg_putting_arccos"]
    _write_csv(os.path.join(s, "rounds_summary.csv"), round_cols, [
        {"round_id": "r1", "date": "2026-06-01",
         "course": '<img src=x onerror=alert(1)>', "tee_name": "Blue",
         "tee_yards": "6400", "holes": "2", "score": "9", "par": "8",
         "score_to_par": "1", "putts": "4", "gir_pct": "50.0",
         "fairway_pct": "100.0", "scramble_pct": "0.0",
         "sg_total_arccos": "-2.1", "sg_off_tee_arccos": "-0.5",
         "sg_approach_arccos": "-1.0", "sg_short_arccos": "-0.3",
         "sg_putting_arccos": "-0.3"},
        {"round_id": "r2", "date": "2026-06-08", "course": "Wind Rose GC",
         "tee_name": "Blue", "tee_yards": "6400", "holes": "2", "score": "10",
         "par": "8", "score_to_par": "", "putts": "5", "gir_pct": "0.0",
         "fairway_pct": "50.0", "scramble_pct": "50.0",
         "sg_total_arccos": "-3.0", "sg_off_tee_arccos": "-1.0",
         "sg_approach_arccos": "-1.5", "sg_short_arccos": "-0.5",
         "sg_putting_arccos": "",
        },
    ])

    hole_cols = ["round_id", "date", "course", "hole_id", "par", "shots",
                 "score_to_par", "putts", "gir", "fairway_hit", "hole_len_yd",
                 "approach_proximity_yd", "pin_lat", "pin_lng",
                 "scramble_chance", "scramble_save", "sg_hole_broadie"]
    _write_csv(os.path.join(s, "holes.csv"), hole_cols, [
        {"round_id": "r1", "hole_id": "1", "par": "4", "shots": "4",
         "score_to_par": "0", "putts": "2", "gir": "1", "fairway_hit": "1",
         "hole_len_yd": "380", "sg_hole_broadie": "-0.2"},
        {"round_id": "r1", "hole_id": "2", "par": "4", "shots": "5",
         "score_to_par": "1", "putts": "2", "gir": "0", "fairway_hit": "1",
         "hole_len_yd": "410", "sg_hole_broadie": "-1.1"},
        {"round_id": "r2", "hole_id": "1", "par": "4", "shots": "5",
         "score_to_par": "1", "putts": "3", "gir": "0", "fairway_hit": "0",
         "hole_len_yd": "380", "sg_hole_broadie": "-1.4"},
        # the None / missing score_to_par hole (R2 crash case):
        {"round_id": "r2", "hole_id": "2", "par": "4", "shots": "5",
         "score_to_par": "", "putts": "2", "gir": "0", "fairway_hit": "1",
         "hole_len_yd": "410", "sg_hole_broadie": ""},
    ])

    shot_cols = ["round_id", "date", "hole_id", "shot_num", "club",
                 "club_category", "shot_distance_yd", "start_dist_to_pin_yd",
                 "end_dist_to_pin_yd", "start_lat", "start_lng", "end_lat",
                 "end_lng", "lie_approx", "is_tee", "is_putt", "penalties",
                 "category_approx", "sg_shot_approx"]
    _write_csv(os.path.join(s, "shots.csv"), shot_cols, [
        {"round_id": "r2", "hole_id": "1", "shot_num": "1", "club": "Driver",
         "club_category": "driver", "start_dist_to_pin_yd": "380",
         "end_dist_to_pin_yd": "140", "lie_approx": "tee", "is_tee": "1",
         "is_putt": "0", "category_approx": "off_tee", "sg_shot_approx": "-0.3"},
        {"round_id": "r2", "hole_id": "1", "shot_num": "2", "club": "7 Iron",
         "club_category": "iron", "start_dist_to_pin_yd": "140",
         "end_dist_to_pin_yd": "12", "lie_approx": "fairway", "is_tee": "0",
         "is_putt": "0", "category_approx": "approach", "sg_shot_approx": "-0.4"},
        {"round_id": "r2", "hole_id": "1", "shot_num": "3", "club": "Putter",
         "club_category": "putter", "start_dist_to_pin_yd": "12",
         "end_dist_to_pin_yd": "1", "lie_approx": "green", "is_tee": "0",
         "is_putt": "1", "category_approx": "putting", "sg_shot_approx": "-0.5"},
        {"round_id": "r2", "hole_id": "1", "shot_num": "4", "club": "Putter",
         "club_category": "putter", "start_dist_to_pin_yd": "1",
         "end_dist_to_pin_yd": "0", "lie_approx": "green", "is_tee": "0",
         "is_putt": "1", "category_approx": "putting", "sg_shot_approx": "0.1"},
    ])

    _write_csv(os.path.join(s, "clubs.csv"),
               ["club", "club_category", "smart_distance_yd", "usage_count"],
               [{"club": "Driver", "club_category": "driver",
                 "smart_distance_yd": "240", "usage_count": "20"}])
    return s
```

- [ ] **Step 2: Write the baseline test `tests/test_compute.py`**

```python
import gen_combined as gc


def test_compute_selects_newest_round_by_default(store):
    d = gc.compute(store)
    assert d["round_id"] == "r2"
    assert d["course"] == "Wind Rose GC"
    assert d["score"] == 10
    assert d["putts"] == 5
    assert d["sg"]["total"] == -3.0
    assert d["sg"]["putting"] is None          # empty cell -> None
    assert len(d["holes"]) == 2


def test_compute_selects_round_by_id(store):
    d = gc.compute(store, "r1")
    assert d["round_id"] == "r1"
    assert d["score"] == 9
```

- [ ] **Step 3: Run tests — establish they pass against current code (or document real behavior)**

Run: `cd /home/cole/golf-reports && python3 -m pytest tests/ -v`
Expected: PASS. If an assertion fails, the *test* is wrong about current behavior — read `gen_combined.compute()`, fix the expectation to the actual computed value, and note it. Do NOT change `compute()` in this task.

- [ ] **Step 4: Add dev-dependency note to `requirements.txt`**

Append:
```
# dev/test: pip install pytest
```

- [ ] **Step 5: Commit**

```bash
cd /home/cole/golf-reports
git add tests/ requirements.txt
git commit -m "test: add pytest harness, synthetic store fixture, compute() baseline tests"
```

---

### Task 2: Render hardening — XSS escape (S3), None crashes (R2), slug sanitize (S6)

**Files:**
- Modify: `render/gen_combined.py:254-345` (`_slug`, `_html`)
- Modify: `render/gen_stats.py:25-45` (`_html` body)
- Modify: `render/gen_gps_pdf.py:82-84` (cover text)
- Test: `tests/test_render.py`

- [ ] **Step 1: Write failing tests `tests/test_render.py`**

```python
import os

import gen_combined as gc
import gen_gps_pdf
import gen_stats


def test_html_escapes_api_strings(store, tmp_path):
    out = str(tmp_path / "out")
    path = gc.gen(store, out, "r1")          # r1 course = '<img src=x onerror=alert(1)>'
    html = open(path, encoding="utf-8").read()
    assert "<img src=x" not in html
    assert "&lt;img src=x" in html


def test_render_survives_none_score_to_par(store, tmp_path):
    out = str(tmp_path / "out")
    # r2 has score_to_par="" at round level and on hole 2 -> must not raise
    path = gc.gen(store, out, "r2")
    assert os.path.exists(path)
    pdf = gen_gps_pdf.gen(store, out, "r2")
    assert os.path.exists(pdf)
    stats = gen_stats.gen(store, out, "r2")
    assert os.path.exists(stats)


def test_slug_sanitizes_hostile_names():
    d = {"course": "../../etc <evil>", "date": "2026-06-08", "round_id": "r9"}
    s = gc._slug(d)
    assert "/" not in s and "<" not in s and ".." not in s
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_render.py -v`
Expected: `test_html_escapes_api_strings` FAIL (raw `<img` present), `test_render_survives_none_score_to_par` FAIL (`TypeError` from `:+d`), `test_slug_sanitizes_hostile_names` FAIL (`/` and `<` survive). Note: `..` alone is allowed by the regex fix (dots are word-adjacent); the assertion on `".." not in s` holds because `/` removal breaks the traversal — if it still fails, tighten regex to also collapse dots.

- [ ] **Step 3: Implement in `render/gen_combined.py`**

Add near the top (after existing imports):

```python
import html as _html_mod
import re


def _esc(v) -> str:
    """HTML-escape any API-sourced value; em-dash for None."""
    return _html_mod.escape(str(v)) if v is not None else "—"


def _pm(v) -> str:
    """Signed int for display; em-dash when absent."""
    return f"{v:+d}" if isinstance(v, int) else "—"
```

Replace `_slug` (line 254):

```python
def _slug(d: dict) -> str:
    raw = f"{(d.get('course') or 'round')}_{d.get('date') or d['round_id']}"
    return re.sub(r"\.\.+", "_", re.sub(r"[^\w\-.]", "_", raw))
```

In `_html()` apply, exactly:
- `cond = "  ".join(f"{_esc(k)}: {_esc(v)}" ...)`
- holes row: `<td>{_pm(h['score_to_par'])}</td>` (line 270)
- peer rows: `<td>{_esc(p['club'])}</td>`
- `<title>{_esc(d['course'])} — {_esc(d['date'])}</title>`
- `<h1>{_esc(d['course'])}</h1>`
- sub line (311-312): `{_esc(d['date'])} · {_esc(d['tee_name'])} ({_esc(d['tee_yards'])}y) · par {_esc(d['par'])} · <b>{_esc(d['score'])}</b> ({_pm(d['score_to_par'])}) · {_esc(d['putts'])} putts · {cond}`
- the later `Carry vs {d['peer_label']}` heading → `{_esc(d['peer_label'])}`
- any other `{d['course']}` / `{d['date']}` occurrences in the template (footer/provenance) → `_esc(...)`

- [ ] **Step 4: Implement in `render/gen_stats.py`**

Import the helpers from gen_combined (it already shares a process with it): `from gen_combined import _esc, _pm`. In its `_html` f-string: `<title>{_esc(d['course'])} stats</title>`, `<h1>{_esc(d['course'])} — stats</h1>`, sub line → `{_esc(d['date'])} · {_esc(d['score'])} ({_pm(d['score_to_par'])}) · {_esc(d['putts'])} putts`, peer/hole rows same as Step 3 (`_esc(p['club'])`, `_pm(h['score_to_par'])` — check the holes generator near line 23).

- [ ] **Step 5: Implement in `render/gen_gps_pdf.py` (matplotlib text — None-guard only, no HTML escaping needed)**

Replace lines 82-84:

```python
        stp = f"{d['score_to_par']:+d}" if isinstance(d.get("score_to_par"), int) else "—"
        fig.text(0.5, 0.32, f"{d.get('tee_name') or '?'} ({d.get('tee_yards') or '?'}y) · par {d.get('par') or '?'} · "
                            f"{d.get('score') or '?'} ({stp}) · {d.get('putts') or '?'} putts",
                 ha="center", fontsize=10)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python3 -m pytest tests/ -v`
Expected: all PASS (including Task 1 tests — no regression).

- [ ] **Step 7: Commit**

```bash
git add render/gen_combined.py render/gen_stats.py render/gen_gps_pdf.py tests/test_render.py
git commit -m "fix: escape API strings in HTML reports (XSS), null-guard score formats, sanitize report filenames"
```

---

### Task 3: GPS opt-in flag in pull_arccos (S2)

**Files:**
- Modify: `ingest/pull_arccos.py:26-33` (docstring), `~line 66` (new config), `568-573` (cols use), the `write_csv(... HOLE_COLS/SHOT_COLS ...)` call sites in `build()` (~lines 859-930), and the argparse block in `main` (bottom of file)
- Test: `tests/test_gps_flag.py`

- [ ] **Step 1: Write failing test `tests/test_gps_flag.py`**

```python
import importlib

import pull_arccos


def test_gps_cols_excluded_by_default(monkeypatch):
    monkeypatch.delenv("GOLF_INCLUDE_GPS", raising=False)
    importlib.reload(pull_arccos)
    cols = pull_arccos.public_cols(pull_arccos.SHOT_COLS)
    assert "start_lat" not in cols and "end_lng" not in cols
    hcols = pull_arccos.public_cols(pull_arccos.HOLE_COLS)
    assert "pin_lat" not in hcols and "pin_lng" not in hcols


def test_gps_cols_included_with_env(monkeypatch):
    monkeypatch.setenv("GOLF_INCLUDE_GPS", "1")
    importlib.reload(pull_arccos)
    assert "start_lat" in pull_arccos.public_cols(pull_arccos.SHOT_COLS)
    # reset module state for other tests
    monkeypatch.delenv("GOLF_INCLUDE_GPS")
    importlib.reload(pull_arccos)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_gps_flag.py -v`
Expected: FAIL — `AttributeError: module 'pull_arccos' has no attribute 'public_cols'`. (Importing `pull_arccos` must not execute a pull: confirm its `main()` is under `if __name__ == "__main__":` — it is.)

- [ ] **Step 3: Implement in `ingest/pull_arccos.py`**

Below the `REQUEST_DELAY_S` config (~line 66):

```python
# GPS columns are PRIVACY-SENSITIVE (home course location). Excluded from the
# public CSVs unless explicitly enabled (env GOLF_INCLUDE_GPS=1 or --include-gps).
INCLUDE_GPS = os.environ.get("GOLF_INCLUDE_GPS", "").lower() in ("1", "true", "yes")
GPS_COLS = {"start_lat", "start_lng", "end_lat", "end_lng", "pin_lat", "pin_lng"}


def public_cols(cols: list[str]) -> list[str]:
    return list(cols) if INCLUDE_GPS else [c for c in cols if c not in GPS_COLS]
```

At every `write_csv` call that passes `HOLE_COLS` or `SHOT_COLS` (in `build()`), wrap: `write_csv(..., public_cols(HOLE_COLS), hole_rows)` / `write_csv(..., public_cols(SHOT_COLS), shot_rows)`. Also in `build_xlsx` where those tabs are written, pass `public_cols(...)` the same way (find the `tab(ws, cols, rows, title)` calls for holes/shots).

In the argparse block in `main`: add

```python
    p.add_argument("--include-gps", action="store_true",
                   help="include lat/lng columns in shots.csv/holes.csv (privacy-sensitive)")
```

and after parsing: 

```python
    global INCLUDE_GPS
    if args.include_gps:
        INCLUDE_GPS = True
```

Fix the docstring: line 26 `OUTPUTS (./arccos_out/, GPS excluded by default — enable with --include-gps):` and line 29 `shots.csv  one row per shot (club, distances-to-pin, lie, SG; lat/lng only with --include-gps)`.

- [ ] **Step 4: Run tests to verify pass**

Run: `python3 -m pytest tests/ -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add ingest/pull_arccos.py tests/test_gps_flag.py
git commit -m "feat: GPS columns opt-in via --include-gps/GOLF_INCLUDE_GPS, default off for privacy"
```

---

### Task 4: MCP import_18birdies path validation (S4)

**Files:**
- Modify: `mcp/server.py:113-118`
- Test: `tests/test_server.py`

- [ ] **Step 1: Write failing test `tests/test_server.py`**

```python
import os

import pytest


@pytest.fixture
def srv(store, monkeypatch):
    monkeypatch.setenv("GOLF_STORE", store)
    import importlib
    import server
    importlib.reload(server)
    return server


def test_import_rejects_outside_home(srv):
    assert srv.import_18birdies("/etc/passwd").startswith("error")


def test_import_rejects_non_json(srv, tmp_path):
    # tmp_path is under /tmp, also outside home — use a real home file instead
    p = os.path.expanduser("~/.bashrc")
    assert srv.import_18birdies(p).startswith("error")


def test_import_rejects_creds_lookalike_traversal(srv):
    assert srv.import_18birdies("~/../../etc/passwd").startswith("error")


def test_import_rejects_control_chars(srv):
    assert srv.import_18birdies("~/x\x00y.json").startswith("error")
```

Note: FastMCP's `@mcp.tool()` returns the original function, so `srv.import_18birdies` is directly callable. If reload ordering fights the `mcp` package name (`mcp/server.py` lives in a dir named `mcp` — the installed `mcp` package wins on import because conftest puts repo `mcp/` dir on `sys.path`, **verify**: `import server` must come from our path entry; if the installed `mcp` package shadows, import via `importlib.util.spec_from_file_location("golf_server", os.path.join(REPO, "mcp", "server.py"))` instead — write a tiny helper in conftest if needed).

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_server.py -v`
Expected: FAIL — current code returns `error: give the path...` only for nonexistent files; `/etc/passwd` exists so it proceeds to `_run` and returns an `ok:`/`exit N:` string, failing the `startswith("error")` assertions for at least `test_import_rejects_outside_home`.

- [ ] **Step 3: Implement in `mcp/server.py` — replace the body of `import_18birdies`**

```python
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
```

- [ ] **Step 4: Run tests, verify pass**

Run: `python3 -m pytest tests/ -v` — all PASS.

- [ ] **Step 5: Commit**

```bash
git add mcp/server.py tests/test_server.py
git commit -m "fix: validate import_18birdies path (home-dir only, .json, no control chars)"
```

---

### Task 5: GOLF_INGEST default → bundled ingest dir (R1)

**Files:**
- Modify: `mcp/server.py:29`
- Test: append to `tests/test_server.py`

- [ ] **Step 1: Write failing test (append to `tests/test_server.py`)**

```python
def test_ingest_defaults_to_bundled_dir(store, monkeypatch):
    monkeypatch.delenv("GOLF_INGEST", raising=False)
    monkeypatch.setenv("GOLF_STORE", store)
    import importlib
    import server
    importlib.reload(server)
    assert server.INGEST.endswith(os.path.join("golf-reports", "ingest"))
    assert os.path.isfile(os.path.join(server.INGEST, "pull_arccos.py"))
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_server.py::test_ingest_defaults_to_bundled_dir -v`
Expected: FAIL — `server.INGEST` is `/home/cole` (HOME default).

- [ ] **Step 3: Implement — replace `mcp/server.py:29`**

```python
_DEFAULT_INGEST = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ingest"))
INGEST = os.environ.get("GOLF_INGEST", _DEFAULT_INGEST)
```

Also update the module docstring line 12-13 to: `GOLF_INGEST  dir holding the pull scripts (default: the ingest/ dir bundled next to this server)`.

- [ ] **Step 4: Run tests, verify pass**

Run: `python3 -m pytest tests/ -v` — all PASS.

- [ ] **Step 5: Commit**

```bash
git add mcp/server.py tests/test_server.py
git commit -m "fix: default GOLF_INGEST to bundled ingest/ dir so the server works without env vars"
```

---

### Task 6: _run error propagation (R4)

**Files:**
- Modify: `mcp/server.py:42-54`
- Test: append to `tests/test_server.py`

- [ ] **Step 1: Write failing test (append to `tests/test_server.py`)**

```python
def test_run_surfaces_stderr_and_tail(store, tmp_path, monkeypatch):
    ingest = tmp_path / "ingest"
    ingest.mkdir()
    (ingest / "fake.py").write_text(
        "import sys\n"
        "print('line1'); print('line2'); print('line3')\n"
        "print('the real error: token expired', file=sys.stderr)\n"
        "sys.exit(3)\n")
    monkeypatch.setenv("GOLF_INGEST", str(ingest))
    monkeypatch.setenv("GOLF_STORE", store)
    import importlib
    import server
    importlib.reload(server)
    out = server._run("fake.py")
    assert out.startswith("exit 3:")
    assert "line2" in out                      # more than just the last line
    assert "token expired" in out              # stderr included
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_server.py::test_run_surfaces_stderr_and_tail -v`
Expected: FAIL — current `_run` returns `exit 3: line3` (no `line2`, no stderr).

- [ ] **Step 3: Implement — replace the return logic in `_run` (`mcp/server.py:52-54`)**

```python
    out_lines = (r.stdout or "").strip().splitlines()
    tail = "\n".join(out_lines[-5:])
    if r.returncode == 0:
        return "ok: " + (tail or "done")
    err = (r.stderr or "").strip()[-1000:]
    return f"exit {r.returncode}: {tail}" + (f"\nstderr: {err}" if err else "")
```

- [ ] **Step 4: Run tests, verify pass**

Run: `python3 -m pytest tests/ -v` — all PASS.

- [ ] **Step 5: Commit**

```bash
git add mcp/server.py tests/test_server.py
git commit -m "fix: _run returns 5-line stdout tail + stderr so sync errors reach Claude"
```

---

### Task 7: GHIN 401 message (R3)

**Files:**
- Modify: `ingest/pull_ghin.py:159-162`

Context: `load_creds()` (line 129) already performs a fresh login on every run when email+password exist, so a mid-run 401 means that fresh token was rejected or the user is in manual-bearer mode. The fix is the message, not new retry machinery (YAGNI).

- [ ] **Step 1: Replace the 401 branch in `ghin_get` (`ingest/pull_ghin.py:160-162`)**

```python
        if e.code == 401:
            sys.exit("Error: 401 Unauthorized — GHIN session rejected. "
                     "If you set up with email/password: re-run setup.py (password may have changed). "
                     "If you pasted a manual bearer_token: it expires ~12h — paste a fresh one.")
```

- [ ] **Step 2: Sanity-run the test suite (no behavior change expected)**

Run: `python3 -m pytest tests/ -v` — all PASS.

- [ ] **Step 3: Commit**

```bash
git add ingest/pull_ghin.py
git commit -m "fix: GHIN 401 message matches the email/password setup flow (no DevTools)"
```

---

### Task 8: Retry on transient errors (R5)

**Files:**
- Modify: `ingest/pull_arccos.py` (`api_get`, ~line 322), `ingest/pull_ghin.py` (`ghin_get`, ~line 147)
- Test: `tests/test_retry.py`

Design note: the helper is **duplicated** in both pullers instead of a shared module — the home-dir copies become symlinks (Task 11) and a sibling-module import would resolve against the symlink's directory (`~`), not `ingest/`. Twelve duplicated lines beat a broken import.

- [ ] **Step 1: Write failing test `tests/test_retry.py`**

```python
import urllib.error

import pull_arccos
import pull_ghin
import pytest


def _flaky(fail_times, code=503):
    state = {"n": 0}
    def fn():
        if state["n"] < fail_times:
            state["n"] += 1
            raise urllib.error.HTTPError("u", code, "boom", {}, None)
        return {"ok": True}
    return fn


@pytest.mark.parametrize("mod", [pull_arccos, pull_ghin])
def test_retry_recovers_from_transient_5xx(mod, monkeypatch):
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    assert mod._with_retry(_flaky(2)) == {"ok": True}


@pytest.mark.parametrize("mod", [pull_arccos, pull_ghin])
def test_retry_gives_up_after_attempts(mod, monkeypatch):
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    with pytest.raises(urllib.error.HTTPError):
        mod._with_retry(_flaky(99))


@pytest.mark.parametrize("mod", [pull_arccos, pull_ghin])
def test_retry_does_not_retry_4xx(mod, monkeypatch):
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    calls = {"n": 0}
    def fn():
        calls["n"] += 1
        raise urllib.error.HTTPError("u", 401, "no", {}, None)
    with pytest.raises(urllib.error.HTTPError):
        mod._with_retry(fn)
    assert calls["n"] == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_retry.py -v`
Expected: FAIL — `AttributeError: ... no attribute '_with_retry'`.

- [ ] **Step 3: Implement — add to BOTH `ingest/pull_arccos.py` (above `api_get`) and `ingest/pull_ghin.py` (above `ghin_get`), identical code**

```python
_RETRY_CODES = (500, 502, 503, 504)


def _with_retry(fn, attempts: int = 3, base_delay: float = 2.0):
    """Retry transient failures (5xx, timeouts, connection drops) with backoff.
    4xx and other HTTPErrors raise immediately."""
    for i in range(attempts):
        try:
            return fn()
        except urllib.error.HTTPError as e:
            if e.code not in _RETRY_CODES or i == attempts - 1:
                raise
        except (urllib.error.URLError, TimeoutError, OSError):
            if i == attempts - 1:
                raise
        time.sleep(base_delay * (2 ** i))
```

Wire it in `pull_arccos.api_get` — replace `data = _request(url, token, form)` (line 331) with:

```python
            data = _with_retry(lambda: _request(url, token, form))
```

Wire it in `pull_ghin.ghin_get` — wrap the urlopen block. Replace lines 155-158:

```python
    def _go():
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read().decode("utf-8"))
    try:
        time.sleep(DELAY_S)
        return _with_retry(_go)
```

(keep the existing `except` clauses unchanged — `_with_retry` re-raises, so 401/soft handling still works).

- [ ] **Step 4: Run tests, verify pass**

Run: `python3 -m pytest tests/ -v` — all PASS.

- [ ] **Step 5: Commit**

```bash
git add ingest/pull_arccos.py ingest/pull_ghin.py tests/test_retry.py
git commit -m "feat: retry transient 5xx/timeouts with backoff in both API clients"
```

---

### Task 9: Atomic writes + sync lock/cooldown (R6)

**Files:**
- Modify: `ingest/pull_arccos.py:372-375` (`_save`), `761-767` (`write_csv`); `ingest/pull_ghin.py:174-177` (`_save`)
- Modify: `mcp/server.py` (`_run` lock; cooldown on sync tools)
- Test: append to `tests/test_server.py`

- [ ] **Step 1: Write failing test (append to `tests/test_server.py`)**

```python
def test_sync_cooldown(store, monkeypatch):
    monkeypatch.setenv("GOLF_STORE", store)
    import importlib
    import server
    importlib.reload(server)
    t = {"now": 1000.0}
    monkeypatch.setattr(server.time, "time", lambda: t["now"])
    server._mark_sync("pull_arccos.py")
    msg = server._cooldown_left("pull_arccos.py")
    assert msg and "cooldown" in msg          # immediately re-running is blocked
    t["now"] += 601
    assert server._cooldown_left("pull_arccos.py") is None   # expired
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_server.py::test_sync_cooldown -v`
Expected: FAIL — no `_mark_sync` attribute.

- [ ] **Step 3: Implement atomic writes (three `_save`s + `write_csv`)**

`ingest/pull_arccos.py:372` and `ingest/pull_ghin.py:174` — same pattern (adjust the dir handling each file already has):

```python
def _save(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)
    os.replace(tmp, path)
```

`ingest/pull_arccos.py:761` `write_csv` — write to `path + ".tmp"`, then `os.replace(tmp, path)` after the `with` block closes.

- [ ] **Step 4: Implement lock + cooldown in `mcp/server.py`**

Add `import time` and `import fcntl` to the imports. Add above `_run`:

```python
_SYNC_COOLDOWN_S = 600
_last_sync: dict[str, float] = {}


def _mark_sync(script: str) -> None:
    _last_sync[script] = time.time()


def _cooldown_left(script: str) -> str | None:
    left = _SYNC_COOLDOWN_S - (time.time() - _last_sync.get(script, 0))
    if left > 0:
        return f"cooldown: {script} ran recently — try again in {int(left)}s (protects the API)"
    return None
```

In `_run`, take a non-blocking exclusive lock for the subprocess duration:

```python
    os.makedirs(STORE, exist_ok=True)
    lock_path = os.path.join(STORE, ".sync.lock")
    with open(lock_path, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return "error: another sync is already running — wait for it to finish"
        try:
            r = subprocess.run([sys.executable, path, *args], cwd=INGEST,
                               capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return f"error: {script} timed out"
```

(the existing return-formatting from Task 6 stays below, inside the `with`).

In `sync_arccos` and `sync_ghin`:

```python
@mcp.tool()
def sync_arccos() -> str:
    """Pull the latest Arccos rounds into the local store (auto-login via stored
    accessKey). Run sync first when asked about recent rounds."""
    if (cd := _cooldown_left("pull_arccos.py")):
        return cd
    out = _run("pull_arccos.py")
    _mark_sync("pull_arccos.py")
    return out
```

(same shape for `sync_ghin` with `pull_ghin.py`).

- [ ] **Step 5: Run tests, verify pass**

Run: `python3 -m pytest tests/ -v` — all PASS.

- [ ] **Step 6: Commit**

```bash
git add ingest/pull_arccos.py ingest/pull_ghin.py mcp/server.py tests/test_server.py
git commit -m "feat: atomic store writes, sync lockfile, 10-min sync cooldown"
```

---

### Task 10: GHIN password → OS keyring with consent-gated fallback (S1)

**Files:**
- Modify: `setup.py:46-57`, `ingest/pull_ghin.py:106-140` (`load_creds`)
- Modify: `requirements.txt`
- Test: `tests/test_ghin_creds.py`

- [ ] **Step 1: Write failing test `tests/test_ghin_creds.py`**

```python
import json
import sys
import types

import pytest

import pull_ghin


def test_load_creds_reads_password_from_keyring(tmp_path, monkeypatch):
    creds = tmp_path / ".ghin_creds.json"
    creds.write_text(json.dumps({"email": "a@b.c", "ghin_id": "123",
                                 "password_in_keyring": True}))
    monkeypatch.setattr(pull_ghin, "CREDS_PATH", str(creds))
    for var in ("GHIN_BEARER", "GHIN_ID", "GHIN_EMAIL", "GHIN_PASSWORD"):
        monkeypatch.delenv(var, raising=False)

    fake = types.SimpleNamespace(
        get_password=lambda svc, user: "sekrit" if (svc, user) == ("golf-reports-ghin", "a@b.c") else None)
    monkeypatch.setitem(sys.modules, "keyring", fake)

    seen = {}
    def fake_login(email, password):
        seen["pw"] = password
        return "tok123", "123"
    monkeypatch.setattr(pull_ghin, "ghin_login", fake_login)

    tok, ghin = pull_ghin.load_creds()
    assert tok == "tok123" and ghin == "123"
    assert seen["pw"] == "sekrit"
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_ghin_creds.py -v`
Expected: FAIL — `load_creds` finds no password and `sys.exit`s (pytest reports `SystemExit`).

- [ ] **Step 3: Implement `pull_ghin.load_creds` keyring branch — insert after line 122 (`password = password or c.get("password")`)**

```python
        if email and not password:
            try:
                import keyring  # optional; OS keychain
                password = keyring.get_password("golf-reports-ghin", email)
            except Exception:
                password = None
```

- [ ] **Step 4: Implement `setup.py` GHIN block — replace lines 46-57**

```python
    if _yes("Link GHIN? [Y/n] "):
        em = input("  GHIN email: ").strip()
        pw = getpass.getpass("  GHIN password: ")
        tok, gid = pg.ghin_login(em, pw)
        if tok:
            meta = {"email": em, "ghin_id": gid}
            stored = ""
            try:
                import keyring
                keyring.set_password("golf-reports-ghin", em, pw)
                meta["password_in_keyring"] = True
                stored = "password in OS keychain"
            except Exception:
                if _yes("  No OS keychain available. GHIN needs the password each sync "
                        "(12h tokens, no refresh). Store it in ~/.ghin_creds.json, "
                        "chmod 600, plaintext? [Y/n] "):
                    meta["password"] = pw
                    stored = "password in ~/.ghin_creds.json (plaintext, chmod 600)"
                else:
                    stored = "password NOT stored — set GHIN_PASSWORD env or re-run setup before syncing"
            p = os.path.expanduser("~/.ghin_creds.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump(meta, f)
            os.chmod(p, 0o600)
            print(f"  ✓ GHIN linked ({stored}).\n")
        else:
            print("  ✗ GHIN login failed — check email/password.\n")
```

- [ ] **Step 5: Add to `requirements.txt`**

```
keyring>=24
```

(graceful: headless Linux without a keychain backend raises inside `set_password`/`get_password` → the fallback path covers it).

- [ ] **Step 6: Run tests, verify pass**

Run: `python3 -m pytest tests/ -v` — all PASS.

- [ ] **Step 7: Commit**

```bash
git add setup.py ingest/pull_ghin.py requirements.txt tests/test_ghin_creds.py
git commit -m "feat: GHIN password in OS keyring; plaintext fallback only with explicit consent"
```

---

### Task 11: Hygiene — .gitignore (S5), requirements (R7), home-dir symlinks, cron env

**Files:**
- Modify: `.gitignore`, `requirements.txt`
- Modify (outside repo): `~/pull_arccos.py`, `~/pull_ghin.py`, `~/arccos_shots_geo.py` → symlinks; `~/arccos_update.sh`

- [ ] **Step 1: Append to `.gitignore`**

```
# Data/output artifacts (never code-repo content)
_cache*/
maps/
arccos_out/
*.xlsx
*.html
*.pdf
*.tmp
```

- [ ] **Step 2: Append to `requirements.txt`**

```
openpyxl>=3.0
```

- [ ] **Step 3: Replace home-dir script copies with symlinks (verified byte-identical 2026-06-10 — re-verify before replacing)**

```bash
for f in pull_arccos.py pull_ghin.py arccos_shots_geo.py; do
  cmp -s ~/$f ~/golf-reports/ingest/$f && ln -sf ~/golf-reports/ingest/$f ~/$f \
    || echo "DRIFT in $f — STOP and diff before symlinking"
done
ls -la ~/pull_arccos.py   # -> ~/golf-reports/ingest/pull_arccos.py
```

Why safe: `~/arccos_update.sh` runs `./arccos-env/bin/python pull_arccos.py` from `~` — Python sets `__file__` to the symlink path, so `HERE=/home/cole` and the existing `~/arccos_out` detection still works. The `cp ../pull_arccos.py arccos_out/` step copies file *content* (cp follows symlinks).

- [ ] **Step 4: Edit `~/arccos_update.sh` — pin store + preserve Cole's GPS-publishing choice (Task 3 made GPS opt-in)**

After the `set -euo pipefail` / `cd` lines, add:

```bash
# Cole publishes his own GPS in arccos-sg-baseline (deliberate). The pull script
# now defaults GPS off for plugin users — keep it ON here. Pin the store path
# (scripts are symlinks into ~/golf-reports/ingest now).
export GOLF_INCLUDE_GPS=1
export GOLF_STORE="$HOME/arccos_out"
```

- [ ] **Step 5: Verify the cron pipeline end-to-end (don't wait for Monday)**

```bash
~/arccos-env/bin/python -c "import matplotlib, openpyxl; print('venv ok')"
bash ~/arccos_update.sh && tail -5 ~/arccos_out/_cron.log
head -3 ~/arccos_out/shots.csv | cut -c1-200   # GPS columns MUST still be present
```

Expected: run completes; `shots.csv` header still contains `start_lat`. If GPS columns vanished, `GOLF_INCLUDE_GPS` export is not reaching the script — fix before continuing.

- [ ] **Step 6: Commit (repo files only; home-dir changes have no repo)**

```bash
cd ~/golf-reports
git add .gitignore requirements.txt
git commit -m "chore: gitignore data artifacts, declare openpyxl; home pull scripts now symlink to ingest/"
```

---

### Task 12: Post-round Telegram alert (automation)

**Files:**
- Create: `bin/post_round_alert.py`
- Test: `tests/test_alert.py`
- Modify (outside repo): `~/arccos_update.sh` (hook), crontab (weekly → daily)

- [ ] **Step 1: Write failing test `tests/test_alert.py`**

```python
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin"))

import post_round_alert as pra


def test_first_run_baselines_without_alerting(store):
    new = pra.detect_new(store)
    assert new == []                          # first run: baseline only, no spam
    seen = json.load(open(os.path.join(store, "_alerted.json")))
    assert set(seen) == {"r1", "r2"}


def test_detects_only_new_rounds(store):
    pra.detect_new(store)                     # baseline
    # simulate a new round appearing
    with open(os.path.join(store, "rounds_summary.csv"), "a", newline="") as f:
        f.write("r3,2026-06-10,Wind Rose GC,Blue,6400,,,2,9,8,1,4,,50.0,100.0,0.0,-1.0,-0.2,-0.4,-0.2,-0.2\n")
    assert pra.detect_new(store) == ["r3"]
    assert pra.detect_new(store) == []        # idempotent: r3 recorded


def test_build_message_contains_essentials(store):
    msg = pra.build_message(store, "r2")
    assert "Wind Rose GC" in msg and "10" in msg
    assert "SG" in msg
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_alert.py -v`
Expected: FAIL — `ModuleNotFoundError: post_round_alert`.

- [ ] **Step 3: Implement `bin/post_round_alert.py`**

```python
#!/usr/bin/env python3
"""Post-round Telegram alert. Run after a sync (cron hook in ~/arccos_update.sh).

Detects round_ids in <store>/rounds_summary.csv not yet in <store>/_alerted.json,
renders each (HTML+PDF into <store>/reports/), sends a Telegram summary, records
the id. First run baselines all existing rounds silently. Reporting must never
fail the sync: every external step is try/except'd.

Usage: post_round_alert.py [store_dir]   (default ~/arccos_out)
Telegram creds: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID from env, ~/alfred/.env,
or ~/.secrets.env (first hit wins; values may be quoted).
"""
from __future__ import annotations

import csv
import json
import os
import sys
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.realpath(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "render"))

import gen_combined as gc        # noqa: E402
import gen_gps_pdf               # noqa: E402


def env_key(name: str) -> str | None:
    if os.environ.get(name):
        return os.environ[name]
    for envfile in ("~/alfred/.env", "~/.secrets.env"):
        try:
            with open(os.path.expanduser(envfile), encoding="utf-8") as f:
                for line in f:
                    if line.startswith(name + "="):
                        return line.split("=", 1)[1].strip().strip("'\"") or None
        except FileNotFoundError:
            continue
    return None


def detect_new(store: str) -> list[str]:
    """Round ids present in the store but not yet alerted. First call baselines."""
    path = os.path.join(store, "rounds_summary.csv")
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        ids = [r["round_id"] for r in csv.DictReader(f) if r.get("round_id")]
    seen_path = os.path.join(store, "_alerted.json")
    first_run = not os.path.exists(seen_path)
    seen = set() if first_run else set(json.load(open(seen_path, encoding="utf-8")))
    new = [i for i in ids if i not in seen]
    tmp = seen_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(sorted(seen | set(new)), f)
    os.replace(tmp, seen_path)
    return [] if first_run else new


def build_message(store: str, rid: str) -> str:
    d = gc.compute(store, rid)
    sg = d["sg"]
    stp = f"{d['score_to_par']:+d}" if isinstance(d.get("score_to_par"), int) else "—"
    lines = [f"⛳ New round: {d['course']} — {d['date']}",
             f"{d['score']} ({stp}) · {d['putts']} putts",
             "SG: " + "  ".join(
                 f"{k} {v:+.1f}" for k, v in
                 (("Tot", sg["total"]), ("Tee", sg["off_tee"]), ("App", sg["approach"]),
                  ("Short", sg["short"]), ("Putt", sg["putting"])) if v is not None)]
    worst = min(((k, v) for k, v in sg.items() if k != "total" and v is not None),
                key=lambda kv: kv[1], default=None)
    if worst:
        lines.append(f"Biggest leak: {worst[0]} ({worst[1]:+.1f})")
    return "\n".join(lines)


def send_telegram(text: str) -> bool:
    token, chat = env_key("TELEGRAM_BOT_TOKEN"), env_key("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("[alert] telegram not configured — skipping send")
        return False
    data = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data)
    with urllib.request.urlopen(req, timeout=20) as r:
        return bool(json.load(r).get("ok"))


def main() -> int:
    store = os.path.abspath(os.path.expanduser(
        sys.argv[1] if len(sys.argv) > 1 else "~/arccos_out"))
    for rid in detect_new(store):
        try:
            reports = os.path.join(store, "reports")
            gc.gen(store, reports, rid)
            gen_gps_pdf.gen(store, reports, rid)
        except Exception as e:  # render failure must not block the alert
            print(f"[alert] render failed for {rid}: {e}", file=sys.stderr)
        try:
            msg = build_message(store, rid)
            print(f"[alert] telegram sent: {send_telegram(msg)} for {rid}")
        except Exception as e:  # alerting must never fail the sync
            print(f"[alert] alert failed for {rid}: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests, verify pass**

Run: `python3 -m pytest tests/ -v` — all PASS. (The `test_build_message` case exercises the R2-hardened path: r2 has `score_to_par=None`.)

- [ ] **Step 5: Hook into `~/arccos_update.sh`** — after the `arccos_shots_geo.py` line, before `cd arccos_out`:

```bash
# Post-round Telegram alert (non-fatal; baselines silently on first run)
./arccos-env/bin/python "$HOME/golf-reports/bin/post_round_alert.py" "$HOME/arccos_out" \
  || echo "post-round alert failed (non-fatal)"
```

- [ ] **Step 6: First live run (baselines, no message) + crontab weekly → daily**

```bash
~/arccos-env/bin/python ~/golf-reports/bin/post_round_alert.py ~/arccos_out
cat ~/arccos_out/_alerted.json   # all existing round ids, nothing sent
crontab -l | sed 's|^0 12 \* \* 1 /home/cole/arccos_cron.sh|0 12 * * * /home/cole/arccos_cron.sh|' | crontab -
crontab -l | grep arccos        # confirm: 0 12 * * *
```

Rationale: alerts are only as fresh as the sync; weekly Monday sync means up-to-6-day-late alerts. One polite pull/day.

- [ ] **Step 7: Commit**

```bash
cd ~/golf-reports
git add bin/post_round_alert.py tests/test_alert.py
git commit -m "feat: post-round Telegram alert with first-run baseline and idempotent round tracking"
```

---

### Task 13: Publish

**Files:** none in-repo (README verify only). Outward-facing — **confirm with Cole before the public push.**

- [ ] **Step 1: Full suite + clean-clone smoke test**

```bash
cd ~/golf-reports && python3 -m pytest tests/ -v        # all green
T=$(mktemp -d) && git clone ~/golf-reports "$T/gr" && cd "$T/gr"
python3 -m venv v && v/bin/pip install -q -r requirements.txt
GOLF_STORE=$T/empty v/bin/python -c "
import sys; sys.path.insert(0,'mcp'); sys.path.insert(0,'render')
import server; print('INGEST =', server.INGEST)"        # must end in /gr/ingest (R1 proof)
```

- [ ] **Step 2: Sanity-scan the repo for anything private before it goes public**

```bash
cd ~/golf-reports
git ls-files | grep -vE '^(docs/|tests/)' | xargs grep -lE "cacjr88|colewinds|chris@|/home/cole" || echo CLEAN
git ls-files '*.html' '*.pdf' '*.csv' '*.xlsx'   # must print nothing (S5 proof)
```

Expected: `CLEAN` and no data files. The `mcp/server.py` docstring's `~/arccos_out` default mention is fine; personal emails/paths are not.

- [ ] **Step 3: ASK COLE, then create + push**

```bash
gh repo create chrisdecali/golf-reports --public --source ~/golf-reports --push
```

- [ ] **Step 4: Marketplace + README verify**

In Claude Code: `/plugin marketplace add chrisdecali/golf-reports` then `/plugin install golf-reports`; confirm the 8 tools appear. Fix README quickstart if any step didn't match reality. Commit doc fixes:

```bash
git add README.md && git commit -m "docs: verify quickstart against real install flow" && git push
```

---

## Execution order & dependencies

1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12 → 13. Tasks 2-10 are independent of each other except: 12 depends on 2 (null-guards) and 11 (symlinks/cron env); 13 depends on everything. Tasks 11-12 touch live cron infrastructure — do them carefully, verify each step's expected output before moving on.

## Spec coverage map

S1→T10, S2→T3, S3→T2, S4→T4, S5→T11, S6→T2, R1→T5, R2→T2, R3→T7, R4→T6, R5→T8, R6→T9, R7→T11, automation→T12, publish→T13, spec tests 1-6 → T1/T2/T2/T4/T3/T6.

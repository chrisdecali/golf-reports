# golf-reports Phase 2 Implementation Plan — Trends, Dispersion, What-if

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unified multi-source scoring history with trends + WHS index math, a low-N empirical-Bayes per-club dispersion model exported as `dispersion.json` (schema v1.0, the Phase 4 golfsmart contract), and a seeded Monte Carlo what-if simulator with practice-ROI ranking — wired into the MCP server as 4 new tools.

**Architecture:** Three new pure modules in `render/` (`trends.py`, `dispersion.py`, `simulate.py`) following the `compute()` pattern (store dir in → dict out, no side effects except explicit `write_*`). `mcp/server.py` wraps them. `bin/post_round_alert.py` regenerates dispersion.json after new rounds. Tests extend the Phase 1 harness (29 green → ~43).

**Tech Stack:** Python 3.12 stdlib only (csv, json, math, random, statistics). Test runner: `/home/cole/arccos-env/bin/python3 -m pytest tests/ -v`. Branch: `phase2-trends` off main (066730c).

**Spec:** `docs/superpowers/specs/2026-06-10-phase2-trends-dispersion-design.md`.

**Key codebase facts for a zero-context engineer:**
- Fixture `store` (tests/conftest.py) has 2 Arccos rounds r1/r2 with SG values — enough to exercise `sg_trends` positively.
- `render/gen_combined.py` exposes `_read(repo, name)` (csv→list[dict], NOT existence-tolerant — check), `_f`/`_i` numeric coercers, `_esc`/`_pm`. Reuse via import, don't duplicate.
- `mcp/server.py` loads render modules via `sys.path` insert; tests load it via `_load_server()` in tests/test_server.py.
- Real store today: 1 Arccos round / 3 GHIN scores / no 18B file yet — all code must tolerate missing files and tiny N.

---

## Pinned constants (single source of truth — implement EXACTLY these)

**WHS reduced-count table** (official): `(min_scores, num_lowest_used, adjustment)`:
```python
_WHS_TABLE = [  # (scores_available >=, diffs_used, adjustment)
    (20, 8, 0.0), (19, 7, 0.0), (17, 6, 0.0), (15, 5, 0.0),
    (12, 4, 0.0), (9, 3, 0.0), (7, 2, 0.0), (6, 2, -1.0),
    (5, 1, 0.0), (4, 1, -1.0), (3, 1, -2.0),
]
# index = round(mean(lowest_used of most-recent-20 differentials) + adjustment, 1)
# fewer than 3 differentials -> None
```

**Dispersion priors** (fractions of carry mean; comment source: Broadie ESC + published amateur dispersion studies, approximate):
```python
_SD_PRIOR = {  # category: (carry_sd_frac, lateral_sd_frac)
    "driver": (0.055, 0.07), "wood": (0.055, 0.06), "hybrid": (0.05, 0.06),
    "iron": (0.05, 0.05), "wedge": (0.06, 0.04),
}
_CARRY_DEFAULT = {  # used only when club absent from clubs.csv (yards)
    "driver": 230, "wood": 205, "hybrid": 190, "iron": 155, "wedge": 100,
}
_K_CARRY, _K_LATERAL = 15, 25   # shrinkage pseudo-counts (shots)
```

**Handicap-typical SG split** (share of total SG loss vs scratch by category; Broadie ESC ch.5 approximation for mid-handicaps):
```python
_SG_SPLIT = {"off_tee": 0.28, "approach": 0.40, "short": 0.17, "putting": 0.15}
_SG_ROUND_SD = {"off_tee": 1.2, "approach": 1.8, "short": 1.3, "putting": 1.7}  # strokes/round
_K_ROUNDS = 5  # shrinkage pseudo-count (rounds) for SG means
```

**Course-name normalization** (dedupe key): lowercase → strip non-alphanumeric → strip trailing generic tokens (`golfclub, golfcourse, countryclub, club, course, gc, cc, golf, links`) applied repeatedly. `"WindRose Golf Club"` and `"Wind Rose GC"` must both normalize to `"windrose"`.

**Simulation:** gross = par + (rating − par) + Σ category draws; draws ~ Normal(mean_cat, sd_cat) where mean_cat = shrunk player SG loss (positive strokes lost). Defaults when course unknown: par 72, rating 72.0, slope 113. `random.Random(seed)`, default seed 18, 10_000 iterations.

---

### Task P2-1: Fixture extension + history() merge/dedupe (TDD)

**Files:**
- Modify: `tests/conftest.py` (extend `store` fixture)
- Create: `tests/test_trends.py`
- Create: `render/trends.py`

- [ ] **Step 1: Extend the `store` fixture in tests/conftest.py.** Append inside the fixture, after the clubs.csv write:

```python
    # 18Birdies history: 6 rounds over 3 months; 2026-06-01 Wind Rose overlaps
    # Arccos r1 (dedupe case). No rating/slope -> excluded from index math.
    _write_csv(os.path.join(s, "18birdies_rounds.csv"),
               ["date", "course", "holes", "gross", "to_par", "fairways_hit",
                "fairway_chances", "fairway_pct", "gir", "gir_chances",
                "gir_pct", "putts", "round_id"], [
        {"date": "2026-03-07", "course": "Forest Golf Course", "holes": "18",
         "gross": "103", "to_par": "31", "putts": "38", "gir": "2",
         "gir_chances": "18", "gir_pct": "11.1", "round_id": "b1"},
        {"date": "2026-03-21", "course": "Forest Golf Course", "holes": "18",
         "gross": "99", "to_par": "27", "putts": "36", "round_id": "b2"},
        {"date": "2026-04-04", "course": "WindRose Golf Club", "holes": "18",
         "gross": "101", "to_par": "29", "putts": "35", "round_id": "b3"},
        {"date": "2026-04-18", "course": "Forest Golf Course", "holes": "9",
         "gross": "49", "to_par": "13", "round_id": "b4"},
        {"date": "2026-05-02", "course": "WindRose Golf Club", "holes": "18",
         "gross": "97", "to_par": "25", "putts": "34", "round_id": "b5"},
        {"date": "2026-06-01", "course": "Wind Rose Golf Club", "holes": "18",
         "gross": "95", "to_par": "23", "putts": "33", "round_id": "b6"},
    ])

    # GHIN: 3 scores; 2026-06-01 WindRose overlaps BOTH Arccos r1 and 18B b6
    # (richest source must win, differential must survive the merge).
    _write_csv(os.path.join(s, "ghin_scores.csv"),
               ["played_at", "course_name", "holes", "adjusted_gross_score",
                "course_rating", "slope_rating", "differential", "score_id"], [
        {"played_at": "2026-05-03", "course_name": "Forest", "holes": "18",
         "adjusted_gross_score": "101", "course_rating": "73.6",
         "slope_rating": "137", "differential": "22.6", "score_id": "g1"},
        {"played_at": "2026-06-01", "course_name": "WindRose Golf Club",
         "holes": "18", "adjusted_gross_score": "96", "course_rating": "72.1",
         "slope_rating": "127", "differential": "21.3", "score_id": "g2"},
        {"played_at": "2026-06-08", "course_name": "WindRose Golf Club",
         "holes": "18", "adjusted_gross_score": "98", "course_rating": "72.1",
         "slope_rating": "127", "differential": "23.1", "score_id": "g3"},
    ])
```

Note the fixture now encodes the merge cases: 2026-06-01 appears in Arccos (r1, course `<img...>` — WRONG name for dedupe... **use date-only secondary match**: see Step 3 dedupe rule), 18B (b6 "Wind Rose Golf Club") and GHIN (g2 "WindRose Golf Club"). IMPORTANT: Arccos r1 fixture course is the XSS payload (kept from Phase 1) — it will NOT name-match the others; the dedupe rule below therefore matches on normalized-course only, and r1 stays a separate row. That is intended: 3-way course match exercises 18B vs GHIN; Arccos r2 (2026-06-08 "Wind Rose GC") vs GHIN g3 (2026-06-08 "WindRose Golf Club") exercises Arccos-wins + differential attach.

- [ ] **Step 2: Write failing tests `tests/test_trends.py`:**

```python
import trends


def test_history_merges_three_sources(store):
    rows = trends.history(store)
    dates = [r["date"] for r in rows]
    assert dates == sorted(dates)                      # oldest first
    # 6 x 18B + 3 GHIN + 2 arccos, minus dedupes:
    # 2026-06-01 18B b6 == GHIN g2 (windrose) -> one row (18B wins over GHIN)
    # 2026-06-08 arccos r2 == GHIN g3 (windrose) -> one row (arccos wins)
    # 2026-05-02 18B b5 (windrose) vs 2026-05-03 GHIN g1 (forest): different -> keep both
    assert len(rows) == 9
    by_date = {r["date"]: r for r in rows}
    assert by_date["2026-06-08"]["source"] == "arccos"
    assert by_date["2026-06-08"]["differential"] == 23.1   # attached from GHIN
    assert by_date["2026-06-01"]["source"] in ("18birdies", "arccos")
    win_61 = [r for r in rows if r["date"] == "2026-06-01"]
    assert any(r["differential"] == 21.3 for r in win_61)  # GHIN diff survived


def test_history_tolerates_missing_files(store, tmp_path):
    import os, shutil
    partial = str(tmp_path / "partial")
    os.makedirs(partial)
    shutil.copy(os.path.join(store, "ghin_scores.csv"), partial)
    rows = trends.history(partial)
    assert len(rows) == 3 and all(r["source"] == "ghin" for r in rows)


def test_normalize_course():
    n = trends._norm_course
    assert n("WindRose Golf Club") == n("Wind Rose GC") == "windrose"
    assert n("Forest") == n("Forest Golf Course")
```

- [ ] **Step 3: Run to verify FAIL** (`ModuleNotFoundError: trends`), then implement `render/trends.py` (part 1 — history only):

```python
#!/usr/bin/env python3
"""trends.py — unified multi-source scoring history + trends + WHS index.

Pure: store dir in -> dicts out. Sources (any subset may exist):
  rounds_summary.csv (Arccos, richest), 18birdies_rounds.csv, ghin_scores.csv.
Dedupe: same date + normalized course name; richness Arccos > 18Birdies > GHIN;
the GHIN differential is attached to whichever row wins.
"""
from __future__ import annotations

import csv
import os
import re
from typing import Any, Optional

_GENERIC = ("golfclub", "golfcourse", "countryclub", "club", "course",
            "gc", "cc", "golf", "links")


def _norm_course(name: str) -> str:
    s = re.sub(r"[^a-z0-9]", "", (name or "").lower())
    changed = True
    while changed:
        changed = False
        for suf in _GENERIC:
            if s.endswith(suf) and len(s) > len(suf):
                s = s[: -len(suf)]
                changed = True
    return s


def _f(x: Any) -> Optional[float]:
    try:
        return float(x) if x not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _i(x: Any) -> Optional[int]:
    f = _f(x)
    return int(f) if f is not None else None


def _read(store: str, name: str) -> list[dict]:
    path = os.path.join(store, name)
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


_RANK = {"arccos": 3, "18birdies": 2, "ghin": 1}


def history(store: str) -> list[dict]:
    rows: list[dict] = []
    for r in _read(store, "rounds_summary.csv"):
        rows.append({"date": r.get("date"), "course": r.get("course"),
                     "holes": _i(r.get("holes")), "gross": _i(r.get("score")),
                     "to_par": _i(r.get("score_to_par")),
                     "putts": _i(r.get("putts")), "gir_pct": _f(r.get("gir_pct")),
                     "fairway_pct": _f(r.get("fairway_pct")),
                     "differential": None, "rating": _f(r.get("rating")),
                     "slope": _f(r.get("slope")),
                     "source": "arccos", "round_id": r.get("round_id")})
    for r in _read(store, "18birdies_rounds.csv"):
        rows.append({"date": r.get("date"), "course": r.get("course"),
                     "holes": _i(r.get("holes")), "gross": _i(r.get("gross")),
                     "to_par": _i(r.get("to_par")), "putts": _i(r.get("putts")),
                     "gir_pct": _f(r.get("gir_pct")),
                     "fairway_pct": _f(r.get("fairway_pct")),
                     "differential": None, "rating": None, "slope": None,
                     "source": "18birdies", "round_id": r.get("round_id")})
    for r in _read(store, "ghin_scores.csv"):
        rows.append({"date": r.get("played_at"), "course": r.get("course_name"),
                     "holes": _i(r.get("holes")),
                     "gross": _i(r.get("adjusted_gross_score")),
                     "to_par": None, "putts": None, "gir_pct": None,
                     "fairway_pct": None,
                     "differential": _f(r.get("differential")),
                     "rating": _f(r.get("course_rating")),
                     "slope": _f(r.get("slope_rating")),
                     "source": "ghin", "round_id": r.get("score_id")})

    merged: dict[tuple, dict] = {}
    for row in rows:
        key = (row["date"], _norm_course(row["course"] or ""))
        cur = merged.get(key)
        if cur is None:
            merged[key] = row
            continue
        keep, drop = ((row, cur) if _RANK[row["source"]] > _RANK[cur["source"]]
                      else (cur, row))
        for fld in ("differential", "rating", "slope", "putts", "gir_pct",
                    "fairway_pct", "to_par"):
            if keep.get(fld) is None and drop.get(fld) is not None:
                keep[fld] = drop[fld]
        merged[key] = keep
    return sorted(merged.values(), key=lambda r: (r["date"] or "", r["source"]))
```

- [ ] **Step 4: Suite green (29 + 3 = 32).** If `len(rows)` differs from 9, recount the dedupe by hand against the fixture before touching the assertion — the merge rule is the contract.

- [ ] **Step 5: Commit** `feat: unified multi-source score history with dedupe (trends part 1)`

---

### Task P2-2: WHS index + trends() + compare_rounds (TDD)

**Files:** Modify `render/trends.py`, `tests/test_trends.py`.

- [ ] **Step 1: Failing tests (append to tests/test_trends.py):**

```python
def test_whs_index_small_counts():
    # 3 diffs -> lowest 1, -2.0
    assert trends._whs_index([20.0, 25.0, 30.0]) == 18.0
    # 6 diffs -> avg lowest 2, -1.0
    assert trends._whs_index([18.0, 20.0, 25.0, 26.0, 27.0, 28.0]) == 18.0
    # <3 -> None
    assert trends._whs_index([20.0, 21.0]) is None


def test_whs_index_full_twenty():
    diffs = [float(d) for d in range(10, 30)]   # 10..29, lowest 8 = 10..17
    assert trends._whs_index(diffs) == 13.5
    # only most-recent 20 count: prepend an ancient great score, list ordered oldest->newest
    assert trends._whs_index([1.0] + diffs) == 13.5


def test_trends_blocks(store):
    t = trends.trends(store)
    assert t["scoring"]["n"] == 8                     # 9 rows minus one 9-holer
    assert t["handicap"]["index"] is not None
    assert t["sg_trends"] is not None                 # fixture has 2 arccos rounds
    assert t["sg_trends"]["n"] == 2
    assert t["rounds_total"] == 9


def test_compare_rounds(store):
    c = trends.compare_rounds(store, "r1", "r2")
    assert c["sg_delta"]["total"] == -0.9             # r2 -3.0 vs r1 -2.1
    assert c["biggest_swing"]["category"] in ("off_tee", "approach", "short", "putting")
```

- [ ] **Step 2: Verify FAIL, then implement (append to render/trends.py):**

```python
_WHS_TABLE = [  # (scores_available >=, diffs_used, adjustment)
    (20, 8, 0.0), (19, 7, 0.0), (17, 6, 0.0), (15, 5, 0.0),
    (12, 4, 0.0), (9, 3, 0.0), (7, 2, 0.0), (6, 2, -1.0),
    (5, 1, 0.0), (4, 1, -1.0), (3, 1, -2.0),
]


def _whs_index(diffs: list[float]) -> Optional[float]:
    """Official WHS: best-N of the most recent 20 differentials + adjustment.
    `diffs` ordered oldest -> newest."""
    recent = [d for d in diffs if d is not None][-20:]
    n = len(recent)
    for min_n, used, adj in _WHS_TABLE:
        if n >= min_n:
            best = sorted(recent)[:used]
            return round(sum(best) / used + adj, 1)
    return None


def _roll(vals: list, n: int) -> Optional[float]:
    sel = [v for v in vals if v is not None][-n:]
    return round(sum(sel) / len(sel), 1) if sel else None


def trends(store: str, window: int = 10) -> dict:
    rows = history(store)
    full = [r for r in rows if (r["holes"] or 18) >= 18]
    gross = [r["gross"] for r in full]
    out: dict = {"rounds_total": len(rows)}
    out["scoring"] = {"n": len([g for g in gross if g is not None]),
                      "last5": _roll(gross, 5), "last10": _roll(gross, 10),
                      "last20": _roll(gross, 20),
                      "prev10": _roll(gross[:-10], 10) if len(gross) > 10 else None}
    out["stats_trends"] = {
        k: {"last5": _roll([r[k] for r in full], 5),
            "last10": _roll([r[k] for r in full], 10)}
        for k in ("putts", "gir_pct", "fairway_pct")}
    diffs = [r["differential"] for r in full if r["differential"] is not None]
    traj = []
    seen: list[float] = []
    for r in full:
        if r["differential"] is not None:
            seen.append(r["differential"])
            idx = _whs_index(seen)
            if idx is not None:
                traj.append({"date": r["date"], "index": idx})
    recent5 = diffs[-5:]
    projected = None
    if diffs and len(recent5) >= 2:
        projected = _whs_index(diffs + [sum(recent5) / len(recent5)] * 5)
    out["handicap"] = {"index": _whs_index(diffs), "n_differentials": len(diffs),
                       "trajectory": traj, "projected_index": projected}
    arc = [r for r in _read(store, "rounds_summary.csv")]
    if len(arc) >= 2:
        cats = ("total", "off_tee", "approach", "short", "putting")
        out["sg_trends"] = {"n": len(arc), **{
            c: _roll([_f(r.get(f"sg_{c}_arccos")) for r in arc], 5) for c in cats}}
    else:
        out["sg_trends"] = None if len(arc) < 2 else out.get("sg_trends")
        out["sg_trends"] = None
        out["sg_trends_reason"] = "needs >=2 arccos rounds"
    if out["sg_trends"] is not None:
        out.pop("sg_trends_reason", None)
    return out


def compare_rounds(store: str, rid_a: str, rid_b: str) -> dict:
    arc = {str(r.get("round_id")): r for r in _read(store, "rounds_summary.csv")}
    a, b = arc.get(str(rid_a)), arc.get(str(rid_b))
    if not a or not b:
        raise SystemExit(f"round not found: {rid_a if not a else rid_b}")
    cats = ("total", "off_tee", "approach", "short", "putting")
    sg_delta = {}
    for c in cats:
        va, vb = _f(a.get(f"sg_{c}_arccos")), _f(b.get(f"sg_{c}_arccos"))
        sg_delta[c] = round(vb - va, 2) if va is not None and vb is not None else None
    swing = max(((c, v) for c, v in sg_delta.items()
                 if c != "total" and v is not None),
                key=lambda cv: abs(cv[1]), default=(None, None))
    stat_delta = {k: ((_i(b.get(k)) - _i(a.get(k)))
                      if _i(a.get(k)) is not None and _i(b.get(k)) is not None else None)
                  for k in ("score", "putts")}
    return {"a": {"round_id": rid_a, "date": a.get("date"), "score": _i(a.get("score"))},
            "b": {"round_id": rid_b, "date": b.get("date"), "score": _i(b.get("score"))},
            "sg_delta": sg_delta, "stat_delta": stat_delta,
            "biggest_swing": {"category": swing[0], "delta": swing[1]}}
```

Clean up the clumsy sg_trends else-branch while implementing: the intent is `sg_trends = {...} if len(arc) >= 2 else None`, plus `sg_trends_reason` key only when None. Write it that way.

- [ ] **Step 3: Suite green (32 + 4 = 36).** Hand-check `test_trends_blocks` expectations against the fixture if anything differs — fixture is the contract, code follows.

- [ ] **Step 4: Commit** `feat: WHS index math, scoring/handicap trends, compare_rounds`

---

### Task P2-3: Dispersion model + dispersion.json (TDD)

**Files:** Create `render/dispersion.py`, `tests/test_dispersion.py`.

- [ ] **Step 1: Failing tests `tests/test_dispersion.py`:**

```python
import json
import math
import os

import dispersion


def test_prior_only_when_no_shots(store, tmp_path):
    import shutil
    bare = str(tmp_path / "bare")
    os.makedirs(bare)
    shutil.copy(os.path.join(store, "clubs.csv"), bare)
    d = dispersion.build(bare)
    drv = next(c for c in d["clubs"] if c["club"] == "Driver")
    assert drv["carry_yd"]["n"] == 0
    assert drv["carry_yd"]["source_weight"] == 0.0
    assert drv["carry_yd"]["mean"] == 240.0            # clubs.csv smart distance
    assert drv["carry_yd"]["sd"] == round(240 * 0.055, 1)
    assert drv["confidence"] == "low"


def test_shrinkage_converges_to_sample(store, tmp_path, monkeypatch):
    # synthetic: 60 identical 7i shots at 150yd -> mean ~ (60*150 + 15*prior)/(75)
    import csv as _csv
    import shutil
    s2 = str(tmp_path / "s2")
    shutil.copytree(store, s2)
    with open(os.path.join(s2, "shots.csv"), "a", newline="") as f:
        w = _csv.writer(f)
        for i in range(60):
            w.writerow(["rX", "2026-06-09", "1", str(i + 1), "7 Iron", "iron",
                        "150", "160", "10", "", "", "", "", "fairway", "0",
                        "0", "0", "approach", "0"])
    d = dispersion.build(s2)
    seven = next(c for c in d["clubs"] if c["club"] == "7 Iron")
    assert seven["carry_yd"]["n"] >= 60
    assert seven["carry_yd"]["source_weight"] > 0.75
    assert abs(seven["carry_yd"]["mean"] - 150) < 5    # data dominates
    assert seven["confidence"] == "high"


def test_lateral_geometry():
    # start at origin-ish, pin due north 200yd, shot ends 20yd east of the line
    # 1 deg lat ~ 121,000 yd ; use small offsets
    start = (40.0, -75.0)
    pin = (40.0 + 200 / 121000.0, -75.0)
    end = (40.0 + 100 / 121000.0, -75.0 + 20 / (121000.0 * math.cos(math.radians(40.0))))
    lat = dispersion._lateral_yd(start, end, pin)
    assert abs(lat - 20.0) < 1.0


def test_schema_and_atomic_write(store):
    path = dispersion.write(store)
    assert os.path.basename(path) == "dispersion.json"
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    assert d["schema_version"] == "1.0"
    assert {"club", "category", "carry_yd", "lateral_yd", "usage_count",
            "confidence"} <= set(d["clubs"][0].keys())
    assert {"mean", "sd", "n", "source_weight"} <= set(d["clubs"][0]["carry_yd"].keys())
```

- [ ] **Step 2: Verify FAIL, implement `render/dispersion.py`:**

```python
#!/usr/bin/env python3
"""dispersion.py — low-N empirical-Bayes per-club dispersion model.

Prior carry mean: clubs.csv smart_distance_yd (Arccos's own estimate), else a
category default. Prior SDs: category fractions of carry (Broadie ESC +
published amateur dispersion studies, approximate). Evidence: shots.csv GPS
rows. Posterior = (n*sample + k*prior)/(n+k). Output: <store>/dispersion.json,
schema v1.0 — the Phase 4 golfsmart contract; aggregates only, no coordinates.
"""
from __future__ import annotations

import csv
import json
import math
import os
import statistics
from datetime import datetime, timezone
from typing import Optional

_SD_PRIOR = {"driver": (0.055, 0.07), "wood": (0.055, 0.06),
             "hybrid": (0.05, 0.06), "iron": (0.05, 0.05), "wedge": (0.06, 0.04)}
_CARRY_DEFAULT = {"driver": 230, "wood": 205, "hybrid": 190, "iron": 155, "wedge": 100}
_K_CARRY, _K_LATERAL = 15, 25
_YD_PER_DEG_LAT = 121_000.0  # ~ 111.32 km in yards


def _f(x) -> Optional[float]:
    try:
        return float(x) if x not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _read(store: str, name: str) -> list[dict]:
    path = os.path.join(store, name)
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _local_xy(origin: tuple, p: tuple) -> tuple:
    """Equirectangular yards relative to origin (fine under ~1000yd)."""
    dy = (p[0] - origin[0]) * _YD_PER_DEG_LAT
    dx = (p[1] - origin[1]) * _YD_PER_DEG_LAT * math.cos(math.radians(origin[0]))
    return dx, dy


def _lateral_yd(start: tuple, end: tuple, pin: tuple) -> Optional[float]:
    """Perpendicular distance of `end` from the start->pin line, in yards."""
    ax, ay = _local_xy(start, pin)
    line_len = math.hypot(ax, ay)
    if line_len < 1.0:
        return None
    ex, ey = _local_xy(start, end)
    return abs(ax * ey - ay * ex) / line_len  # cross product / |line|


def _confidence(n: int) -> str:
    return "high" if n >= 20 else "medium" if n >= 5 else "low"


def _shrink(sample_mean: Optional[float], n: int, prior: float, k: int) -> tuple:
    if n == 0 or sample_mean is None:
        return prior, 0.0
    w = n / (n + k)
    return (n * sample_mean + k * prior) / (n + k), round(w, 2)


def build(store: str) -> dict:
    clubs_meta = {r.get("club"): r for r in _read(store, "clubs.csv")}
    shots = _read(store, "shots.csv")

    carries: dict[str, list[float]] = {}
    laterals: dict[str, list[float]] = {}
    for s in shots:
        club = s.get("club")
        if not club or club == "Putter" or s.get("is_putt") == "1":
            continue
        if s.get("lie_approx") in ("recovery", "sand"):
            dist_ok = False
        else:
            dist_ok = True
        d = _f(s.get("shot_distance_yd"))
        if dist_ok and d and d > 10:
            carries.setdefault(club, []).append(d)
        coords = tuple(_f(s.get(k)) for k in
                       ("start_lat", "start_lng", "end_lat", "end_lng"))
        # pin = where the ball is aimed; approximate with the hole's pin via
        # end of last shot is unknown here, so use start->pin proxy:
        # start_dist_to_pin defines the line only with pin coords, which shots.csv
        # does not carry; reconstruct pin from end point + end_dist when end_dist==0
        # is unreliable -> v1: lateral only for shots whose hole pin is known via
        # holes.csv (pin_lat/pin_lng), joined on round_id+hole_id.
    holes_pin = {(h.get("round_id"), h.get("hole_id")):
                 (_f(h.get("pin_lat")), _f(h.get("pin_lng")))
                 for h in _read(store, "holes.csv")}
    for s in shots:
        club = s.get("club")
        if not club or club == "Putter" or s.get("is_putt") == "1":
            continue
        pin = holes_pin.get((s.get("round_id"), s.get("hole_id")))
        start = (_f(s.get("start_lat")), _f(s.get("start_lng")))
        end = (_f(s.get("end_lat")), _f(s.get("end_lng")))
        if pin and None not in pin and None not in start and None not in end:
            lat = _lateral_yd(start, end, pin)
            if lat is not None:
                laterals.setdefault(club, []).append(lat)

    all_clubs = sorted(set(clubs_meta) | set(carries) | set(laterals) - {None, ""})
    out_clubs = []
    for club in all_clubs:
        meta = clubs_meta.get(club, {})
        cat = (meta.get("club_category") or _guess_category(club))
        prior_carry = _f(meta.get("smart_distance_yd")) or _CARRY_DEFAULT.get(cat, 150)
        sd_frac_c, sd_frac_l = _SD_PRIOR.get(cat, (0.05, 0.05))
        cs = carries.get(club, [])
        ls = laterals.get(club, [])
        carry_mean, w_c = _shrink(statistics.fmean(cs) if cs else None,
                                  len(cs), prior_carry, _K_CARRY)
        prior_csd = prior_carry * sd_frac_c
        sample_csd = statistics.stdev(cs) if len(cs) >= 2 else None
        carry_sd, _ = _shrink(sample_csd, max(len(cs) - 1, 0), prior_csd, _K_CARRY)
        prior_lsd = carry_mean * sd_frac_l
        # lateral samples are |deviation|; sd of signed dev ~ rms of abs (half-normal):
        sample_lsd = (math.sqrt(statistics.fmean([v * v for v in ls]))
                      if len(ls) >= 2 else None)
        lat_sd, w_l = _shrink(sample_lsd, len(ls), prior_lsd, _K_LATERAL)
        n_evidence = max(len(cs), len(ls))
        out_clubs.append({
            "club": club, "category": cat,
            "carry_yd": {"mean": round(carry_mean, 1), "sd": round(carry_sd, 1),
                         "n": len(cs), "source_weight": w_c},
            "lateral_yd": {"sd": round(lat_sd, 1), "n": len(ls),
                           "source_weight": w_l},
            "usage_count": int(_f(meta.get("usage_count")) or 0) or len(cs),
            "confidence": _confidence(n_evidence)})

    ghin = {}
    gpath = os.path.join(store, "ghin_profile.json")
    if os.path.exists(gpath):
        with open(gpath, encoding="utf-8") as f:
            ghin = json.load(f) or {}
    rounds_gps = len({s.get("round_id") for s in shots if _f(s.get("start_lat"))})
    return {"schema_version": "1.0",
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "player": {"hcp_index": _f(ghin.get("handicap_index")),
                       "rounds_with_gps": rounds_gps},
            "clubs": out_clubs}


def _guess_category(club: str) -> str:
    c = (club or "").lower()
    if "driver" in c:
        return "driver"
    if "wood" in c:
        return "wood"
    if "hybrid" in c:
        return "hybrid"
    if "wedge" in c or c in ("pw", "gw", "sw", "lw"):
        return "wedge"
    return "iron"


def write(store: str) -> str:
    path = os.path.join(store, "dispersion.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(build(store), f, indent=1)
    os.replace(tmp, path)
    return path
```

NOTE the first shots loop contains a stale half-written comment block about pins — DELETE it when implementing; the holes.csv pin join (second loop) is the real mechanism. Merge the two loops into one clean pass. The plan shows the logic split for explanation; the committed code must be a single loop, no dangling comments.

- [ ] **Step 3: Suite green (36 + 4 = 40).** The shrinkage test's `n >= 60` and `weight > 0.75` follow from 60/(60+15) = 0.8.

- [ ] **Step 4: Commit** `feat: empirical-Bayes per-club dispersion model -> dispersion.json schema v1.0`

---

### Task P2-4: Monte Carlo simulator + what_if (TDD)

**Files:** Create `render/simulate.py`, `tests/test_simulate.py`.

- [ ] **Step 1: Failing tests `tests/test_simulate.py`:**

```python
import simulate


def test_deterministic_with_seed(store):
    a = simulate.what_if(store, category="putting", gain=0.5, seed=18)
    b = simulate.what_if(store, category="putting", gain=0.5, seed=18)
    assert a == b


def test_gain_lowers_mean(store):
    r = simulate.what_if(store, category="approach", gain=1.0)
    assert r["improved"]["mean"] < r["current"]["mean"]
    assert abs((r["current"]["mean"] - r["improved"]["mean"]) - 1.0) < 0.15


def test_roi_ranking_shape(store):
    r = simulate.what_if(store, category="putting", gain=0.5)
    rank = r["category_roi_ranking"]
    assert len(rank) == 4
    assert all(set(e) >= {"category", "delta_strokes"} for e in rank)


def test_honesty_fields(store):
    r = simulate.what_if(store, category="short", gain=0.5)
    assert r["n_rounds_evidence"] == 2          # fixture arccos rounds
    assert 0.0 <= r["prior_weight"] <= 1.0
```

- [ ] **Step 2: Verify FAIL, implement `render/simulate.py`:**

```python
#!/usr/bin/env python3
"""simulate.py — category-level Monte Carlo round simulator + what-if.

Round score = par + (rating - par) + sum(category SG-loss draws).
Player category means: Arccos SG shrunk toward handicap-typical splits
(Broadie ESC ch.5 approximation), k=5 rounds. Hole-level simulation is
deliberately deferred until multi-round GPS exists (see Phase 2 spec).
"""
from __future__ import annotations

import os
import random
import statistics
import sys
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import trends as _trends   # noqa: E402

_SG_SPLIT = {"off_tee": 0.28, "approach": 0.40, "short": 0.17, "putting": 0.15}
_SG_ROUND_SD = {"off_tee": 1.2, "approach": 1.8, "short": 1.3, "putting": 1.7}
_K_ROUNDS = 5
_ITER = 10_000
_CATS = tuple(_SG_SPLIT)


def _player_means(store: str) -> tuple[dict, int, float, float]:
    """-> ({category: mean SG LOSS per round (positive strokes)}, n_rounds,
          prior_weight, hcp)."""
    t = _trends.trends(store)
    hcp = t["handicap"]["index"]
    if hcp is None:
        hcp = 20.0
    arc = _trends._read(store, "rounds_summary.csv")
    n = len(arc)
    w = n / (n + _K_ROUNDS)
    means = {}
    for c in _CATS:
        prior = hcp * _SG_SPLIT[c]                      # strokes lost
        vals = [_trends._f(r.get(f"sg_{c}_arccos")) for r in arc]
        vals = [-v for v in vals if v is not None]      # SG negative -> loss positive
        sample = statistics.fmean(vals) if vals else None
        means[c] = (w * sample + (1 - w) * prior) if sample is not None else prior
    return means, n, round(1 - w if n else 1.0, 2), hcp


def _course(store: str) -> tuple[float, float]:
    rows = _trends.history(store)
    rated = [r for r in rows if r.get("rating") and r.get("slope")]
    if rated:
        last = rated[-1]
        return float(last["rating"]), 72.0
    return 72.0, 72.0


def _simulate(means: dict, rating: float, par: float, seed: int) -> list[float]:
    rng = random.Random(seed)
    out = []
    for _ in range(_ITER):
        s = par + (rating - par)
        for c in _CATS:
            s += rng.gauss(means[c], _SG_ROUND_SD[c])
        out.append(s)
    return out


def _summary(scores: list[float]) -> dict:
    scores = sorted(scores)
    n = len(scores)
    return {"mean": round(statistics.fmean(scores), 1),
            "p25": round(scores[n // 4], 1), "p75": round(scores[3 * n // 4], 1)}


def what_if(store: str, category: str = "putting", gain: float = 0.5,
            seed: int = 18) -> dict:
    if category not in _CATS:
        raise SystemExit(f"unknown category {category!r} — one of {_CATS}")
    means, n, prior_w, hcp = _player_means(store)
    rating, par = _course(store)
    cur = _simulate(means, rating, par, seed)
    imp_means = dict(means)
    imp_means[category] = means[category] - gain
    imp = _simulate(imp_means, rating, par, seed)

    rank = []
    for c in _CATS:
        m2 = dict(means)
        m2[c] = means[c] - 0.5
        sims = _simulate(m2, rating, par, seed)
        rank.append({"category": c,
                     "delta_strokes": round(statistics.fmean(sims)
                                            - statistics.fmean(cur), 2)})
    rank.sort(key=lambda e: e["delta_strokes"])

    slope = 113.0
    diffs_imp = [round((113.0 / slope) * (s - rating), 1)
                 for s in sorted(imp)[: _ITER // 2: _ITER // 40]]  # sample 20
    out = {"category": category, "gain": gain,
           "current": _summary(cur), "improved": _summary(imp),
           "delta_strokes_per_round": round(statistics.fmean(cur)
                                            - statistics.fmean(imp), 2),
           "new_projected_index": _trends._whs_index(diffs_imp),
           "category_roi_ranking": rank,
           "n_rounds_evidence": n, "prior_weight": prior_w,
           "hcp_basis": hcp}
    if prior_w >= 0.5:
        out["note"] = ("prior-dominated estimate (few Arccos rounds) — "
                       "directional, not measured")
    return out
```

NOTE on `new_projected_index`: the slicing sample of simulated differentials is crude — implement instead as: take 20 evenly spaced scores from the sorted improved distribution (`sorted(imp)[:: _ITER // 20][:20]`), convert each to a differential vs (rating, slope 113), feed `_whs_index`. Write that clean version; the intent is "index you'd settle at if you shot the improved distribution for 20 rounds."

- [ ] **Step 3: Suite green (40 + 4 = 44).**

- [ ] **Step 4: Commit** `feat: category-level Monte Carlo what-if with practice ROI ranking`

---

### Task P2-5: MCP wiring + manifests + SKILL.md + alert hook

**Files:** Modify `mcp/server.py`, `manifest.json`, `.claude-plugin/plugin.json`, `skills/golf-reports/SKILL.md`, `bin/post_round_alert.py`; append `tests/test_server.py`, `tests/test_alert.py`.

- [ ] **Step 1: Failing tests.** Append to tests/test_server.py:

```python
def test_new_tools_registered(store, monkeypatch):
    monkeypatch.setenv("GOLF_STORE", store)
    server = _load_server()
    assert server.trends()["rounds_total"] == 9
    assert server.what_if("putting", 0.5)["category"] == "putting"
    path = server.export_dispersion()
    assert "dispersion.json" in path["path"]
    import os as _os
    assert _os.path.exists(path["path"])
```

Append to tests/test_alert.py:

```python
def test_alert_regenerates_dispersion(store, monkeypatch):
    import os
    pra.detect_new(store)                      # baseline
    with open(os.path.join(store, "rounds_summary.csv"), "a", newline="") as f:
        f.write("r4,2026-06-11,Wind Rose GC,Blue,6400,,,2,9,8,1,4,,50.0,100.0,0.0,-1.0,-0.2,-0.4,-0.2,-0.2\n")
    monkeypatch.setattr(pra, "send_telegram", lambda text: True)
    pra.main_for_store(store)                  # refactor main() -> main_for_store(store)
    assert os.path.exists(os.path.join(store, "dispersion.json"))
```

- [ ] **Step 2: Implement server tools (mcp/server.py).** After existing imports of gen modules add `import trends as trends_mod`, `import dispersion as dispersion_mod`, `import simulate as simulate_mod` (render dir already on sys.path). New tools:

```python
@mcp.tool()
def trends() -> dict:
    """Scoring/handicap/stat trends across ALL sources (Arccos + GHIN +
    18Birdies). Includes WHS index + trajectory. Call after syncs."""
    return trends_mod.trends(STORE)


@mcp.tool()
def compare_rounds(round_id_a: str, round_id_b: str) -> dict:
    """Compare two Arccos rounds: SG deltas by category, biggest swing."""
    return trends_mod.compare_rounds(STORE, round_id_a, round_id_b)


@mcp.tool()
def what_if(category: str = "putting", gain: float = 0.5) -> dict:
    """Monte Carlo: if the player improves <category> by <gain> strokes/round,
    projected scoring + index change + practice-ROI ranking of all categories.
    Honesty: check prior_weight — high means prior-dominated, caveat it."""
    return simulate_mod.what_if(STORE, category, gain)


@mcp.tool()
def export_dispersion() -> dict:
    """(Re)generate <store>/dispersion.json — per-club carry/lateral model
    (schema v1.0, golfsmart bridge artifact). Returns path + club count."""
    path = dispersion_mod.write(STORE)
    import json as _json
    with open(path, encoding="utf-8") as f:
        d = _json.load(f)
    return {"path": path, "clubs": len(d["clubs"]),
            "rounds_with_gps": d["player"]["rounds_with_gps"]}
```

Name collision check: the module-level function `trends` (tool) vs imported `trends_mod` — the tool function shadows nothing because the import is aliased. Keep aliases exactly as shown.

- [ ] **Step 3: post_round_alert hook.** Refactor `main()` so the store-scoped body is `main_for_store(store: str) -> int` (main parses argv then calls it — keeps tests away from argv). At the END of `main_for_store`, after the alert loop:

```python
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(HERE), "render"))
        import dispersion as _disp
        _disp.write(store)
    except Exception as e:  # never fail the sync
        print(f"[alert] dispersion regen failed: {e}", file=sys.stderr)
```

(render path already on sys.path from module top — the insert is redundant; just `import dispersion as _disp`. Keep it minimal.)

- [ ] **Step 4: Manifests.** `manifest.json` tools array += 4 entries (one-line descriptions); `.claude-plugin/plugin.json` if it lists tools, same (read it first — it may not list tools).

- [ ] **Step 5: SKILL.md.** Add a `## Analysis tools` section documenting trends/compare_rounds/what_if/export_dispersion + interpretation rules: lead with `prior_weight`/`confidence` caveats when high/low; "Where am I losing strokes?" flow now = `trends()` → worst sg category → `what_if(that category)`; never present prior-dominated dispersion as measured.

- [ ] **Step 6: Suite green (44 + 2 = 46).** Commit `feat: MCP tools trends/compare_rounds/what_if/export_dispersion + skill guidance + alert dispersion regen`

---

### Task P2-6: Live validation + finish

- [ ] **Step 1:** Full suite + run against the REAL store read-only: `GOLF_STORE=~/arccos_out python3 -c` invoking trends() and what_if() via the render modules directly; sanity-eyeball output (index ≈ 21-23 from 3 GHIN scores → table says 3 scores = lowest 1 − 2.0 → ~19.3; verify code agrees with hand calc). `export_dispersion` on real store; inspect dispersion.json (driver/7i rows present, confidence low, prior-dominated weights).
- [ ] **Step 2:** README: add the 4 tools to the tool list section (one line each).
- [ ] **Step 3:** Commit, merge gate (finishing-a-development-branch), push.
- [ ] **Step 4 (deferred, non-blocking):** When Cole's `18Birdies_archive.json` arrives: `import_18birdies` → `trends()` against real history → eyeball scoring averages + index trajectory.

## Spec coverage map

History/merge→P2-1; trends+WHS+compare→P2-2; dispersion+schema+write→P2-3; simulate+what_if+ROI→P2-4; MCP+manifest+SKILL+alert-regen→P2-5; live validation→P2-6. Spec tests: merge/dedupe (P2-1), WHS tables (P2-2), shrinkage limits + lateral geometry + schema (P2-3), determinism/monotonicity/ROI/honesty (P2-4), MCP round-trip + alert regen (P2-5).

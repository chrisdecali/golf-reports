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


_WHS_TABLE = [  # (scores_available >=, diffs_used, adjustment)
    (20, 8, 0.0), (19, 7, 0.0), (17, 6, 0.0), (15, 5, 0.0),
    (12, 4, 0.0), (9, 3, 0.0), (7, 2, 0.0), (6, 2, -1.0),
    (5, 1, 0.0), (4, 1, -1.0), (3, 1, -2.0),
]


def _whs_index(diffs: list) -> Optional[float]:
    """Official WHS: best-N of the most recent 20 differentials + adjustment.
    `diffs` ordered oldest -> newest. None values are filtered; count = non-None entries."""
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


def trends(store: str) -> dict:
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
    seen: list = []
    for r in full:
        if r["differential"] is not None:
            seen.append(r["differential"])
            idx = _whs_index(seen)
            if idx is not None:
                traj.append({"date": r["date"], "index": idx})
    recent5 = diffs[-5:]
    projected = None
    # require >=2 recent diffs for a meaningful trend-based projection
    if diffs and len(recent5) >= 2:
        projected = _whs_index(diffs + [sum(recent5) / len(recent5)] * 5)
    out["handicap"] = {"index": _whs_index(diffs), "n_differentials": len(diffs),
                       "trajectory": traj, "projected_index": projected}
    arc = _read(store, "rounds_summary.csv")
    if len(arc) >= 2:
        cats = ("total", "off_tee", "approach", "short", "putting")
        out["sg_trends"] = {"n": len(arc), **{
            c: _roll([_f(r.get(f"sg_{c}_arccos")) for r in arc], 5) for c in cats}}
    else:
        out["sg_trends"] = None
        out["sg_trends_reason"] = "needs >=2 arccos rounds"
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
    # ties broken by cats order (off_tee first)
    swing = max(((c, v) for c, v in sg_delta.items()
                 if c != "total" and v is not None),
                key=lambda cv: abs(cv[1]), default=(None, None))
    stat_delta = {}
    for k in ("score", "putts"):
        va, vb = _i(a.get(k)), _i(b.get(k))
        stat_delta[k] = (vb - va) if va is not None and vb is not None else None
    return {"a": {"round_id": rid_a, "date": a.get("date"), "score": _i(a.get("score"))},
            "b": {"round_id": rid_b, "date": b.get("date"), "score": _i(b.get("score"))},
            "sg_delta": sg_delta, "stat_delta": stat_delta,
            "biggest_swing": {"category": swing[0], "delta": swing[1]}}

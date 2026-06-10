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

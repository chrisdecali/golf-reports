#!/usr/bin/env python3
"""dispersion.py — low-N empirical-Bayes per-club dispersion model.

Prior mean total distance: clubs.csv smart_distance_yd (Arccos's own estimate),
else a category default. Prior SDs: category fractions of total distance (Broadie
ESC + published amateur dispersion studies, approximate). Evidence: shots.csv GPS
rows. Posterior = (n*sample + k*prior)/(n+k). Output: <store>/dispersion.json,
schema v1.0 — the Phase 4 golfsmart contract; aggregates only, no coordinates.

NB: distances are GPS total (carry+roll); Arccos does not isolate carry.
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
_DIST_DEFAULT = {"driver": 230, "wood": 205, "hybrid": 190, "iron": 155, "wedge": 100}
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


def _guess_category(club: str) -> str:
    c = (club or "").lower()
    if "putter" in c:
        return "putter"
    if "driver" in c:
        return "driver"
    if "wood" in c:
        return "wood"
    if "hybrid" in c:
        return "hybrid"
    if "wedge" in c or c in ("pw", "gw", "sw", "lw"):
        return "wedge"
    return "iron"


def build(store: str) -> dict:
    clubs_meta = {r.get("club"): r for r in _read(store, "clubs.csv")}
    shots = _read(store, "shots.csv")

    # Build pin lookup from holes.csv so lateral distance can be computed.
    # Key: (round_id, hole_id) -> (pin_lat, pin_lng)
    holes_pin = {(h.get("round_id"), h.get("hole_id")):
                 (_f(h.get("pin_lat")), _f(h.get("pin_lng")))
                 for h in _read(store, "holes.csv")}

    dists: dict[str, list[float]] = {}
    laterals: dict[str, list[float]] = {}

    # Single pass: gather total-distance samples and lateral samples for each club.
    for s in shots:
        club = s.get("club")
        if not club or club == "Putter" or s.get("is_putt") == "1":
            continue
        # recovery/sand lies produce abnormally short distances — not representative
        if s.get("lie_approx") not in ("recovery", "sand"):
            d = _f(s.get("shot_distance_yd"))
            if d and d > 10:
                dists.setdefault(club, []).append(d)
        pin = holes_pin.get((s.get("round_id"), s.get("hole_id")))
        start = (_f(s.get("start_lat")), _f(s.get("start_lng")))
        end = (_f(s.get("end_lat")), _f(s.get("end_lng")))
        if (s.get("category_approx") in ("off_tee", "approach")
                and pin and None not in pin
                and None not in start and None not in end):
            lat = _lateral_yd(start, end, pin)
            if lat is not None:
                laterals.setdefault(club, []).append(lat)

    all_clubs = sorted((set(clubs_meta) | set(dists) | set(laterals)) - {None, ""})
    out_clubs = []
    for club in all_clubs:
        meta = clubs_meta.get(club, {})
        cat = (meta.get("club_category") or _guess_category(club))
        if cat == "putter":
            continue
        prior_dist = _f(meta.get("smart_distance_yd")) or _DIST_DEFAULT.get(cat, 150)
        sd_frac_d, sd_frac_l = _SD_PRIOR.get(cat, (0.05, 0.05))
        ds = dists.get(club, [])
        ls = laterals.get(club, [])
        dist_mean, w_d = _shrink(statistics.fmean(ds) if ds else None,
                                 len(ds), prior_dist, _K_CARRY)
        prior_dsd = prior_dist * sd_frac_d
        sample_dsd = statistics.stdev(ds) if len(ds) >= 2 else None
        dist_sd, _ = _shrink(sample_dsd, max(len(ds) - 1, 0), prior_dsd, _K_CARRY)
        prior_lsd = dist_mean * sd_frac_l
        # lateral samples are |deviation|; under half-normal, rms(|X|) = sigma exactly
        sample_lsd = (math.sqrt(statistics.fmean([v * v for v in ls]))
                      if len(ls) >= 2 else None)
        lat_sd, w_l = _shrink(sample_lsd, len(ls), prior_lsd, _K_LATERAL)
        n_evidence = max(len(ds), len(ls))
        out_clubs.append({
            "club": club, "category": cat,
            "total_yd": {"mean": round(dist_mean, 1), "sd": round(dist_sd, 1),
                         "n": len(ds), "source_weight": w_d},
            "lateral_yd": {"sd": round(lat_sd, 1), "n": len(ls),
                           "source_weight": w_l},
            "usage_count": int(_f(meta.get("usage_count")) or 0) or len(ds),
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


def write(store: str) -> str:
    path = os.path.join(store, "dispersion.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(build(store), f, indent=1)
    os.replace(tmp, path)
    return path

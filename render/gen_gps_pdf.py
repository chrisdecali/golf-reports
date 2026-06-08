#!/usr/bin/env python3
"""gen_gps_pdf.py — matplotlib multi-page PDF of shot maps, one hole per page.
GPS hole -> north-up geo map (local equirectangular, yards). No GPS -> distance
schematic (stacked shot distances). matplotlib is the only pip dependency."""

from __future__ import annotations

import math
import os
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402

import gen_combined as gc  # noqa: E402

CAT_COLOR = {"off_tee": "#d62728", "approach": "#ff7f0e",
             "short_game": "#2ca02c", "putting": "#1f77b4"}
YD_PER_M = 1.0936132983


def _to_yards_xy(latlng, ref):
    """(lat,lng) -> (east_yd, north_yd) relative to ref, north-up."""
    mlat = math.radians((latlng[0] + ref[0]) / 2)
    e = math.radians(latlng[1] - ref[1]) * math.cos(mlat) * 6371000.0 * YD_PER_M
    n = math.radians(latlng[0] - ref[0]) * 6371000.0 * YD_PER_M
    return e, n


def _geo_page(ax, hole, meta):
    shots = [s for s in hole["shots"] if s["start"]]
    ref = shots[0]["start"]
    for s in shots:
        x0, y0 = _to_yards_xy(s["start"], ref)
        col = CAT_COLOR.get(s["cat"], "#555")
        if s["end"]:
            x1, y1 = _to_yards_xy(s["end"], ref)
            ax.annotate("", xy=(x1, y1), xytext=(x0, y0),
                        arrowprops=dict(arrowstyle="->", color=col, lw=2))
            ax.text((x0 + x1) / 2, (y0 + y1) / 2, f"{s['club']} {s['dist_yd'] or ''}y",
                    fontsize=6, color=col)
        ax.plot(x0, y0, "o", color=col, ms=4)
    if hole.get("pin") and hole["pin"][0]:
        px, py = _to_yards_xy(hole["pin"], ref)
        ax.plot(px, py, "*", color="black", ms=14, label="pin")
    ax.set_aspect("equal")
    ax.set_title(meta, fontsize=10)
    ax.set_xlabel("yards (E)")
    ax.set_ylabel("yards (N)")
    ax.grid(alpha=0.2)


def _schematic_page(ax, shots, meta):
    y = 0
    for s in shots:
        d = gc._f(s.get("shot_distance_yd")) or 0
        ax.barh(y, d, color=CAT_COLOR.get(s.get("category_approx"), "#777"))
        ax.text(d + 2, y, f"{s.get('club')} {d:.0f}y", va="center", fontsize=7)
        y -= 1
    ax.set_title(meta + "  (no GPS — distances)", fontsize=10)
    ax.set_xlabel("yards")
    ax.set_yticks([])


def gen(repo: str, out: str, rid: Optional[str] = None) -> str:
    d = gc.compute(repo, rid)
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, f"{gc._slug(d)}_shotmaps.pdf")
    gps_by_hole = {h["hole_id"]: h for h in d["gps"]["holes"]}
    shots = [s for s in gc._read(repo, "shots.csv") if str(s.get("round_id")) == d["round_id"]]
    shots_by_hole: dict = {}
    for s in shots:
        shots_by_hole.setdefault(gc._i(s.get("hole_id")), []).append(s)
    hole_meta = {h["hole_id"]: h for h in d["holes"]}

    with PdfPages(path) as pdf:
        # cover
        fig = plt.figure(figsize=(8.5, 2.4))
        fig.text(0.5, 0.6, f"{d['course']} — {d['date']}", ha="center", fontsize=16, weight="bold")
        fig.text(0.5, 0.32, f"{d['tee_name']} ({d['tee_yards']}y) · par {d['par']} · "
                            f"{d['score']} ({d['score_to_par']:+d}) · {d['putts']} putts",
                 ha="center", fontsize=10)
        pdf.savefig(fig); plt.close(fig)

        for hid in sorted(shots_by_hole):
            m = hole_meta.get(hid, {})
            meta = (f"Hole {hid} · par {m.get('par','?')} · {m.get('len_yd') or '?'}y · "
                    f"{(m.get('score_to_par') if m.get('score_to_par') is not None else '')}"
                    + ("" if m.get("score_to_par") is None else " to par"))
            fig, ax = plt.subplots(figsize=(8.5, 8.5))
            if hid in gps_by_hole and any(s["start"] for s in gps_by_hole[hid]["shots"]):
                _geo_page(ax, gps_by_hole[hid], meta)
            else:
                _schematic_page(ax, shots_by_hole[hid], meta)
            pdf.savefig(fig); plt.close(fig)
    return path


if __name__ == "__main__":
    import sys
    print(gen(sys.argv[1] if len(sys.argv) > 1 else "store",
              sys.argv[2] if len(sys.argv) > 2 else "out",
              sys.argv[3] if len(sys.argv) > 3 else None))

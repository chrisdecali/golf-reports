#!/usr/bin/env python3
"""
gen_combined.py — primary render module.

`compute(repo, rid)` is the pure stat engine: reads rounds_summary.csv / holes.csv /
shots.csv from `repo` (a dir) for one round and returns a dict. NO network, NO DB.
`gen(repo, out, rid)` wraps that dict into the merged satellite-map + stats HTML.

Read conventions (fixed contract):
  - Select round by round_id; newest = LAST row of rounds_summary.csv.
  - Booleans are '1' / ''. Distances in yards; putt distances shown in feet (×3).
  - GPS columns (start_lat/lng, end_lat/lng, pin_lat/lng) are OPTIONAL everywhere.
  - Read by column name; if columns are renamed, adapt here — not in callers.
"""

from __future__ import annotations

import csv
import html as _html_mod
import json
import math
import os
import re
from typing import Any, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
PEER_CONFIG = os.path.join(HERE, "peer_config.json")


# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------

def _read(repo: str, name: str) -> list[dict]:
    path = os.path.join(repo, name)
    if not os.path.exists(path):
        raise SystemExit(f"missing {name} in {repo}")
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _f(x: Any) -> Optional[float]:
    try:
        return float(x) if x not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _i(x: Any) -> Optional[int]:
    v = _f(x)
    return int(v) if v is not None else None


def _b(x: Any) -> bool:
    return str(x).strip() == "1"


def _latlng(row: dict, lat_key: str, lng_key: str):
    lat, lng = _f(row.get(lat_key)), _f(row.get(lng_key))
    return [lat, lng] if (lat is not None and lng is not None) else None


# ---------------------------------------------------------------------------
# Geometry (local equirectangular; cross-checked against recorded distances)
# ---------------------------------------------------------------------------

YD_PER_M = 1.0936132983


def _dist_yd(a, b) -> Optional[float]:
    if not a or not b:
        return None
    lat1, lng1 = a
    lat2, lng2 = b
    mlat = math.radians((lat1 + lat2) / 2)
    dx = math.radians(lng2 - lng1) * math.cos(mlat) * 6371000.0
    dy = math.radians(lat2 - lat1) * 6371000.0
    return round(math.hypot(dx, dy) * YD_PER_M, 1)


# ---------------------------------------------------------------------------
# Round selection
# ---------------------------------------------------------------------------

def _select_round(rounds: list[dict], rid: Optional[str]) -> dict:
    if not rounds:
        raise SystemExit("rounds_summary.csv is empty")
    if rid is None:
        return rounds[-1]  # newest = last row
    for r in rounds:
        if str(r.get("round_id")) == str(rid):
            return r
    raise SystemExit(f"round_id {rid} not found in rounds_summary.csv")


# ---------------------------------------------------------------------------
# compute() — pure CSV -> dict
# ---------------------------------------------------------------------------

PUTT_BUCKETS = [(0, 3, "0-3 ft"), (3, 6, "3-6 ft"), (6, 10, "6-10 ft"),
                (10, 20, "10-20 ft"), (20, 1e9, "20+ ft")]
APPR_BANDS = [(0, 50, "<50 yd"), (50, 100, "50-100"), (100, 150, "100-150"),
              (150, 200, "150-200"), (200, 1e9, "200+")]


def _peer_table() -> tuple[str, dict]:
    if os.path.exists(PEER_CONFIG):
        try:
            with open(PEER_CONFIG, encoding="utf-8") as f:
                c = json.load(f)
            return c.get("peer_label", "peer"), c.get("peer_carry_yd", {})
        except (OSError, json.JSONDecodeError):
            pass
    return "peer", {}


def compute(repo: str, rid: Optional[str] = None) -> dict:
    rounds = _read(repo, "rounds_summary.csv")
    rnd = _select_round(rounds, rid)
    rid = str(rnd.get("round_id"))
    holes = [h for h in _read(repo, "holes.csv") if str(h.get("round_id")) == rid]
    shots = [s for s in _read(repo, "shots.csv") if str(s.get("round_id")) == rid]
    shots.sort(key=lambda s: (_i(s.get("hole_id")) or 0, _i(s.get("shot_num")) or 0))

    # --- round header + SG (measured, Arccos) ---
    sg = {k: _f(rnd.get(f"sg_{c}_arccos")) for k, c in
          (("total", "total"), ("off_tee", "off_tee"), ("approach", "approach"),
           ("short", "short"), ("putting", "putting"))}
    conditions = {k: rnd.get(k) for k in ("temp_f", "wind_mph", "weather", "conditions")
                  if rnd.get(k)}

    # --- SG by 15-yard approach band (measured: shots.sg_shot_approx) ---
    band15: dict[int, list] = {}
    for s in shots:
        if s.get("category_approx") != "approach":
            continue
        d = _f(s.get("start_dist_to_pin_yd"))
        sgv = _f(s.get("sg_shot_approx"))
        if d is None or sgv is None:
            continue
        b = int((d or 0.0) // 15) * 15
        band15.setdefault(b, [0.0, 0])
        band15[b][0] += sgv
        band15[b][1] += 1
    sg_by_band = [{"band": f"{b}-{b+15} yd", "sg": round(v[0], 2), "shots": v[1]}
                  for b, v in sorted(band15.items())]

    # --- holes table ---
    hole_rows = [{
        "hole_id": _i(h.get("hole_id")), "par": _i(h.get("par")),
        "len_yd": _f(h.get("hole_len_yd")), "shots": _i(h.get("shots")),
        "score_to_par": _i(h.get("score_to_par")), "putts": _i(h.get("putts")),
        "fairway_hit": _b(h.get("fairway_hit")), "gir": _b(h.get("gir")),
        "penalties": _i(h.get("penalties")), "sg_hole": _f(h.get("sg_hole_broadie")),
    } for h in holes]

    # --- putting make% by ft bucket (derived heuristic) ---
    putt_buckets = {lab: [0, 0] for *_, lab in PUTT_BUCKETS}  # [attempts, makes]
    by_hole: dict[int, list] = {}
    for s in shots:
        hid = _i(s.get("hole_id"))
        if _b(s.get("is_putt")) and hid is not None:
            by_hole.setdefault(hid, []).append(s)
    for hid, putts in by_hole.items():
        putts.sort(key=lambda s: _i(s.get("shot_num")) or 0)
        last = putts[-1].get("shot_num")
        for p in putts:
            d_ft = (_f(p.get("start_dist_to_pin_yd")) or 0) * 3.0
            made = (p.get("shot_num") == last)  # holed = last putt of the hole
            for lo, hi, lab in PUTT_BUCKETS:
                if lo <= d_ft < hi:
                    putt_buckets[lab][0] += 1
                    putt_buckets[lab][1] += 1 if made else 0
                    break
    putting = [{"bucket": lab, "attempts": a, "makes": m,
                "make_pct": round(100 * m / a, 0) if a else None}
               for lab, (a, m) in putt_buckets.items() if a]

    # --- approach proximity by from-band (derived) ---
    appr: dict[str, list] = {lab: [0, 0.0] for *_, lab in APPR_BANDS}  # [n, sum_prox]
    for hid, putts in by_hole.items():
        hshots = [s for s in shots if _i(s.get("hole_id")) == hid]
        # last non-putt shot = the approach onto the green
        non_putt = [s for s in hshots if not _b(s.get("is_putt"))]
        if not non_putt:
            continue
        appr_shot = non_putt[-1]
        frm = _f(appr_shot.get("start_dist_to_pin_yd"))
        prox = _f(appr_shot.get("end_dist_to_pin_yd"))
        if frm is None or prox is None:
            continue
        for lo, hi, lab in APPR_BANDS:
            if lo <= frm < hi:
                appr[lab][0] += 1
                appr[lab][1] += prox
                break
    approach = [{"from": lab, "attempts": n, "avg_proximity_yd": round(s / n, 1)}
                for lab, (n, s) in appr.items() if n]

    # --- peer carry delta (BAG from clubs.csv vs modeled PEER) ---
    peer_label, peer_tbl = _peer_table()
    peer_carry = []
    clubs_path = os.path.join(repo, "clubs.csv")
    if os.path.exists(clubs_path):
        for c in _read(repo, "clubs.csv"):
            name = c.get("club")
            you = _f(c.get("smart_distance_yd"))
            peer = peer_tbl.get(name)
            if you is None or peer is None:
                continue
            peer_carry.append({"club": name, "you_yd": round(you, 0),
                               "peer_yd": peer, "delta_yd": round(you - peer, 0)})

    # --- GPS shot map + distance cross-check ---
    gps_holes = []
    check = None
    for h in holes:
        hid = _i(h.get("hole_id"))
        pin = _latlng(h, "pin_lat", "pin_lng")
        gshots = []
        for s in [s for s in shots if _i(s.get("hole_id")) == hid]:
            start = _latlng(s, "start_lat", "start_lng")
            end = _latlng(s, "end_lat", "end_lng")
            if not start:
                continue
            recomputed = _dist_yd(start, end)
            recorded = _f(s.get("shot_distance_yd"))
            if check is None and recomputed and recorded:
                check = {"recomputed": recomputed, "recorded": recorded,
                         "ok": abs(recomputed - recorded) <= 1.0}
            gshots.append({"shot_num": _i(s.get("shot_num")), "club": s.get("club"),
                           "cat": s.get("category_approx"), "start": start, "end": end,
                           "dist_yd": recorded})
        if gshots:
            gps_holes.append({"hole_id": hid, "pin": pin, "shots": gshots})
    has_gps = len(gps_holes) > 0

    return {
        "round_id": rid, "course": rnd.get("course"), "date": rnd.get("date"),
        "tee_name": rnd.get("tee_name"), "tee_yards": _i(rnd.get("tee_yards")),
        "par": _i(rnd.get("par")), "score": _i(rnd.get("score")),
        "score_to_par": _i(rnd.get("score_to_par")), "putts": _i(rnd.get("putts")),
        "gir_pct": _f(rnd.get("gir_pct")), "fairway_pct": _f(rnd.get("fairway_pct")),
        "scramble_pct": _f(rnd.get("scramble_pct")), "penalties": _i(rnd.get("penalties")),
        "conditions": conditions, "sg": sg, "sg_by_band": sg_by_band, "holes": hole_rows,
        "putting": putting, "approach": approach,
        "peer_label": peer_label, "peer_carry": peer_carry,
        "gps": {"has_gps": has_gps, "holes": gps_holes}, "gps_check": check,
    }


# ---------------------------------------------------------------------------
# gen() — combined satellite + stats HTML
# ---------------------------------------------------------------------------

def _esc(v) -> str:
    """HTML-escape any API-sourced value; em-dash for None."""
    return _html_mod.escape(str(v)) if v is not None else "—"


def _pm(v) -> str:
    """Signed int for display; em-dash when absent."""
    return f"{v:+d}" if isinstance(v, int) else "—"


def _slug(d: dict) -> str:
    raw = f"{(d.get('course') or 'round')}_{d.get('date') or d['round_id']}"
    return re.sub(r"\.\.+", "_", re.sub(r"[^\w\-.]", "_", raw))


def _html(d: dict) -> str:
    j = json.dumps  # shorthand
    sg = d["sg"]
    cond = "  ".join(f"{_esc(k)}: {_esc(v)}" for k, v in d["conditions"].items())
    sg_card = lambda lab, v: (
        f'<div class="card {"pos" if (v or 0) >= 0 else "neg"}">'
        f'<div class="lab">{lab}</div><div class="val">{v:+.1f}</div></div>'
        if v is not None else
        f'<div class="card"><div class="lab">{lab}</div><div class="val">—</div></div>')
    holes_rows = "".join(
        f"<tr><td>{h['hole_id']}</td><td>{h['par']}</td>"
        f"<td>{h['len_yd'] or ''}</td><td>{h['shots']}</td>"
        f"<td>{_pm(h['score_to_par'])}</td><td>{h['putts']}</td>"
        f"<td>{'✓' if h['fairway_hit'] else ''}</td><td>{'✓' if h['gir'] else ''}</td>"
        f"<td>{(h['sg_hole'] if h['sg_hole'] is not None else '')}</td></tr>"
        for h in d["holes"])
    peer_rows = "".join(
        f"<tr><td>{_esc(p['club'])}</td><td>{p['you_yd']:.0f}</td><td>{p['peer_yd']}</td>"
        f"<td class=\"{'pos' if p['delta_yd'] >= 0 else 'neg'}\">{p['delta_yd']:+.0f}</td></tr>"
        for p in d["peer_carry"])
    map_block = (
        '<div id="map"></div>'
        '<script>const GPS=' + j(d["gps"]) + ';renderMap(GPS);</script>'
        if d["gps"]["has_gps"] else
        '<p class="note">No GPS for this round — map omitted; stats below.</p>')
    chk = d.get("gps_check")
    chk_txt = (f"GPS check: recomputed {chk['recomputed']}y vs recorded {chk['recorded']}y "
               f"({'✓ match' if chk['ok'] else '⚠ off'})") if chk else ""

    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>{_esc(d['course'])} — {_esc(d['date'])}</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
 body{{font:15px/1.5 system-ui,sans-serif;margin:0;background:#0f1115;color:#e7e9ee}}
 .wrap{{max-width:1000px;margin:0 auto;padding:20px}}
 h1{{margin:.2em 0}} .sub{{color:#9aa0aa}}
 .cards{{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0}}
 .card{{background:#1a1d24;border-radius:10px;padding:12px 16px;min-width:90px;text-align:center}}
 .card .lab{{font-size:12px;color:#9aa0aa}} .card .val{{font-size:22px;font-weight:700}}
 .pos{{color:#56d364}} .neg{{color:#f08c8c}}
 #map{{height:460px;border-radius:12px;margin:14px 0;background:#222}}
 table{{border-collapse:collapse;width:100%;margin:10px 0;font-size:13px}}
 th,td{{border-bottom:1px solid #2a2e37;padding:6px 8px;text-align:right}}
 th:first-child,td:first-child{{text-align:left}}
 .grid{{display:grid;grid-template-columns:1fr 1fr;gap:24px}}
 .note{{color:#9aa0aa;font-style:italic}} canvas{{max-height:240px}}
 h2{{margin-top:28px;border-bottom:1px solid #2a2e37;padding-bottom:4px}}
 .prov{{color:#6b7280;font-size:12px;margin-top:30px}}
</style></head><body><div class="wrap">
<h1>{_esc(d['course'])}</h1>
<div class="sub">{_esc(d['date'])} · {_esc(d['tee_name'])} ({_esc(d['tee_yards'])}y) · par {_esc(d['par'])} ·
 <b>{_esc(d['score'])}</b> ({_pm(d['score_to_par'])}) · {_esc(d['putts'])} putts · {cond}</div>

<h2>Strokes Gained (vs scratch)</h2>
<div class="cards">
 {sg_card('Total', sg['total'])}{sg_card('Off-tee', sg['off_tee'])}
 {sg_card('Approach', sg['approach'])}{sg_card('Short', sg['short'])}
 {sg_card('Putting', sg['putting'])}</div>

<h2>Shot map</h2>
{map_block}
<div class="note">{chk_txt}</div>

<h2>Breakdown</h2>
<div class="grid">
 <div><canvas id="bandChart"></canvas><div class="note">SG by approach distance (15-yd bands)</div></div>
 <div><canvas id="puttChart"></canvas><div class="note">Putting make % by distance</div></div>
</div>

<h2>Holes</h2>
<table><tr><th>#</th><th>Par</th><th>Yds</th><th>Shots</th><th>+/-</th><th>Putts</th>
<th>FW</th><th>GIR</th><th>SG</th></tr>{holes_rows}</table>

<h2>Carry vs {_esc(d['peer_label'])}</h2>
<table><tr><th>Club</th><th>You</th><th>Peer</th><th>Δ</th></tr>{peer_rows}</table>

<div class="prov">Source: Arccos (measured SG + GPS), GHIN, 18Birdies. SG-by-band &amp;
 hole SG measured; putting make% &amp; approach proximity derived; peer carry modeled.
 Satellite tiles © Esri (load client-side in a browser).</div>
</div>
<script>
function renderMap(g){{
 const pts=[]; g.holes.forEach(h=>h.shots.forEach(s=>{{if(s.start)pts.push(s.start);if(s.end)pts.push(s.end);}}));
 const map=L.map('map').setView(pts[0]||[0,0],16);
 L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}',
  {{maxZoom:21,attribution:'Esri'}}).addTo(map);
 const col={{off_tee:'#ff5252',approach:'#ffb300',short_game:'#42d77d',putting:'#4aa3ff'}};
 g.holes.forEach(h=>{{
  h.shots.forEach(s=>{{ if(s.start&&s.end){{
    L.polyline([s.start,s.end],{{color:col[s.cat]||'#fff',weight:3}}).addTo(map)
     .bindTooltip(`H${{h.hole_id}} ${{s.club}} ${{s.dist_yd||''}}y`);
  }}}});
  if(h.pin&&h.pin[0]) L.circleMarker(h.pin,{{radius:4,color:'#fff'}}).addTo(map);
 }});
 if(pts.length) map.fitBounds(pts);
}}
const BAND={j(d['sg_by_band'])}, PUTT={j(d['putting'])};
new Chart(bandChart,{{type:'bar',data:{{labels:BAND.map(b=>b.band),
 datasets:[{{label:'SG',data:BAND.map(b=>b.sg),
  backgroundColor:BAND.map(b=>b.sg>=0?'#56d364':'#f08c8c')}}]}},
 options:{{plugins:{{legend:{{display:false}}}}}}}});
new Chart(puttChart,{{type:'bar',data:{{labels:PUTT.map(p=>p.bucket),
 datasets:[{{label:'make %',data:PUTT.map(p=>p.make_pct),backgroundColor:'#4aa3ff'}}]}},
 options:{{scales:{{y:{{max:100}}}},plugins:{{legend:{{display:false}}}}}}}});
</script></body></html>"""


def gen(repo: str, out: str, rid: Optional[str] = None) -> str:
    d = compute(repo, rid)
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, f"{_slug(d)}_report.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(_html(d))
    return path


if __name__ == "__main__":
    import sys
    repo = sys.argv[1] if len(sys.argv) > 1 else "store"
    out = sys.argv[2] if len(sys.argv) > 2 else "out"
    print(gen(repo, out, sys.argv[3] if len(sys.argv) > 3 else None))

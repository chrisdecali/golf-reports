#!/usr/bin/env python3
"""gen_stats.py — stats-only HTML (no map). Imports gen_combined.compute (one
source of truth for the math; this module is presentation only)."""

from __future__ import annotations

import json
import os
from typing import Optional

import gen_combined as gc
from gen_combined import _esc, _pm


def _html(d: dict) -> str:
    j = json.dumps
    sg = d["sg"]
    card = lambda lab, v: (f'<div class="card {"pos" if (v or 0)>=0 else "neg"}">'
                           f'<div class="lab">{lab}</div><div class="val">{v:+.1f}</div></div>'
                           if v is not None else
                           f'<div class="card"><div class="lab">{lab}</div><div class="val">—</div></div>')
    holes = "".join(f"<tr><td>{h['hole_id']}</td><td>{h['par']}</td><td>{h['shots']}</td>"
                    f"<td>{_pm(h['score_to_par'])}</td><td>{h['putts']}</td>"
                    f"<td>{'✓' if h['fairway_hit'] else ''}</td><td>{'✓' if h['gir'] else ''}</td>"
                    f"<td>{h['sg_hole'] if h['sg_hole'] is not None else ''}</td></tr>"
                    for h in d["holes"])
    peer = "".join(f"<tr><td>{_esc(p['club'])}</td><td>{p['you_yd']:.0f}</td><td>{p['peer_yd']}</td>"
                   f"<td class=\"{'pos' if p['delta_yd']>=0 else 'neg'}\">{p['delta_yd']:+.0f}</td></tr>"
                   for p in d["peer_carry"])
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{_esc(d['course'])} stats</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>body{{font:15px/1.5 system-ui;margin:0;background:#0f1115;color:#e7e9ee}}
.wrap{{max-width:860px;margin:0 auto;padding:20px}}.cards{{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0}}
.card{{background:#1a1d24;border-radius:10px;padding:12px 16px;min-width:84px;text-align:center}}
.card .lab{{font-size:12px;color:#9aa0aa}}.card .val{{font-size:22px;font-weight:700}}
.pos{{color:#56d364}}.neg{{color:#f08c8c}}table{{border-collapse:collapse;width:100%;font-size:13px;margin:10px 0}}
th,td{{border-bottom:1px solid #2a2e37;padding:6px 8px;text-align:right}}th:first-child,td:first-child{{text-align:left}}
h1{{margin:.2em 0}}.sub{{color:#9aa0aa}}canvas{{max-height:240px}}</style></head><body><div class="wrap">
<h1>{_esc(d['course'])} — stats</h1><div class="sub">{_esc(d['date'])} · {_esc(d['score'])} ({_pm(d['score_to_par'])}) · {_esc(d['putts'])} putts</div>
<div class="cards">{card('Total',sg['total'])}{card('Off-tee',sg['off_tee'])}{card('Approach',sg['approach'])}{card('Short',sg['short'])}{card('Putting',sg['putting'])}</div>
<canvas id="band"></canvas><canvas id="putt"></canvas>
<table><tr><th>#</th><th>Par</th><th>Shots</th><th>+/-</th><th>Putts</th><th>FW</th><th>GIR</th><th>SG</th></tr>{holes}</table>
<table><tr><th>Club</th><th>You</th><th>Peer</th><th>Δ</th></tr>{peer}</table>
<script>const B={j(d['sg_by_band'])},P={j(d['putting'])};
new Chart(band,{{type:'bar',data:{{labels:B.map(b=>b.band),datasets:[{{data:B.map(b=>b.sg),backgroundColor:B.map(b=>b.sg>=0?'#56d364':'#f08c8c')}}]}},options:{{plugins:{{legend:{{display:false}}}},'aspectRatio':3}}}});
new Chart(putt,{{type:'bar',data:{{labels:P.map(p=>p.bucket),datasets:[{{data:P.map(p=>p.make_pct),backgroundColor:'#4aa3ff'}}]}},options:{{scales:{{y:{{max:100}}}},plugins:{{legend:{{display:false}}}},'aspectRatio':3}}}});
</script></div></body></html>"""


def gen(repo: str, out: str, rid: Optional[str] = None) -> str:
    d = gc.compute(repo, rid)
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, f"{gc._slug(d)}_stats.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(_html(d))
    return path


if __name__ == "__main__":
    import sys
    print(gen(sys.argv[1] if len(sys.argv) > 1 else "store",
              sys.argv[2] if len(sys.argv) > 2 else "out",
              sys.argv[3] if len(sys.argv) > 3 else None))

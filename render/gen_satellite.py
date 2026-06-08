#!/usr/bin/env python3
"""gen_satellite.py — map-only HTML (Leaflet + Esri tiles, shots client-side).
Raises SystemExit if the round has no GPS (callers catch it)."""

from __future__ import annotations

import json
import os
from typing import Optional

import gen_combined as gc


def gen(repo: str, out: str, rid: Optional[str] = None) -> str:
    d = gc.compute(repo, rid)
    if not d["gps"]["has_gps"]:
        raise SystemExit(f"round {d['round_id']} has no GPS — satellite map skipped")
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, f"{gc._slug(d)}_map.html")
    html = f"""<!doctype html><html><head><meta charset="utf-8"><title>{d['course']} map</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>html,body{{margin:0;height:100%}}#map{{height:100%}}</style></head><body>
<div id="map"></div><script>const G={json.dumps(d['gps'])};
const pts=[];G.holes.forEach(h=>h.shots.forEach(s=>{{if(s.start)pts.push(s.start);if(s.end)pts.push(s.end);}}));
const map=L.map('map').setView(pts[0]||[0,0],16);
L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}',{{maxZoom:21,attribution:'Esri'}}).addTo(map);
const col={{off_tee:'#ff5252',approach:'#ffb300',short_game:'#42d77d',putting:'#4aa3ff'}};
G.holes.forEach(h=>{{h.shots.forEach(s=>{{if(s.start&&s.end)L.polyline([s.start,s.end],{{color:col[s.cat]||'#fff',weight:3}}).addTo(map).bindTooltip(`H${{h.hole_id}} ${{s.club}} ${{s.dist_yd||''}}y`);}});if(h.pin&&h.pin[0])L.circleMarker(h.pin,{{radius:4,color:'#fff'}}).addTo(map);}});
if(pts.length)map.fitBounds(pts);</script></body></html>"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path


if __name__ == "__main__":
    import sys
    print(gen(sys.argv[1] if len(sys.argv) > 1 else "store",
              sys.argv[2] if len(sys.argv) > 2 else "out",
              sys.argv[3] if len(sys.argv) > 3 else None))

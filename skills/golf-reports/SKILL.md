---
name: golf-reports
description: Pull, analyze, and render the golfer's own data from Arccos, GHIN, and 18Birdies. Use whenever the user asks about their golf game, rounds, strokes gained, short game/chipping, putting, driving, club gaps, or wants a round report / shot map / PDF. Backed by the local golf-reports MCP server (tools prefixed appropriately); runs on the user's machine.
---

# Golf Reports

The user's golf data lives on **their machine**, fetched from Arccos (shot-level +
strokes-gained), GHIN (official handicap + scores), and 18Birdies (imported export).
A local MCP server (`golf-reports`) exposes the tools below — no DevTools, no manual
file wrangling. (It runs locally because the cloud sandbox can't reach the golf APIs.)

## Tools

- `list_rounds` — every round, newest last. Start here to find a `round_id`.
- `round_stats(round_id="")` — key stats for one round (default newest): SG by
  category, GIR/fairway/scramble %, putting make % by distance, approach proximity,
  peer carry gaps. Use this to **analyze** without rendering.
- `render_round(round_id="")` — build the **HTML report** (satellite shot map + stats)
  and the **shot-map PDF**. Returns local file paths.
- `get_report_paths` — list already-rendered files.
- `sync_arccos` / `sync_ghin` — pull the latest data first if the user asks about
  recent rounds. `import_18birdies(archive_path)` — load an 18Birdies export.
- `logout` — delete stored credentials.
- `trends` — scoring averages (5/10/20), official WHS index + trajectory +
  projection, putts/GIR/FW trends, SG-category trends (needs ≥2 Arccos rounds).
  All sources merged (Arccos + GHIN + 18Birdies import).
- `compare_rounds(a, b)` — SG/stat deltas between two Arccos rounds.
- `export_dispersion` — regenerate `dispersion.json` (per-club total-distance +
  lateral model; the golfsmart bridge artifact).

## Typical flows

- **"How was my last round?"** → `round_stats()` → summarize SG (lead with the
  weakest category), then offer `render_round()` for the visual report.
- **"Show me a map of round X / make a PDF I can send."** → `render_round(round_id=X)`
  → give the PDF path (shareable) and note the HTML opens in a browser for satellite.
- **"Sync / pull my latest."** → `sync_arccos` (+ `sync_ghin`) → then `list_rounds`.
- **"Where am I losing strokes?"** → `round_stats` across recent rounds; focus on the
  most-negative SG category and the matching detail (approach bands, putting buckets,
  scramble/chip rates).

## Reading the numbers (avoid wrong conclusions)

- **Strokes gained** is vs scratch; large negatives are normal for a mid-handicap.
  SG by category + by 15-yd band + hole SG are **measured** (Arccos).
- **Putting make %** and **approach proximity** are **derived heuristics**; treat as
  directional. **Peer carry** is vs a **modeled** ~12-HCP table (configurable).
- GHIN handicap index is the official **WHS** index (not Arccos's proprietary scale).
- Satellite tiles only load when the HTML is opened in a normal browser; the **PDF**
  is the reliable offline/shareable artifact.

## Player priority

If the user hasn't said otherwise, weight **short game / chipping** — it's the common
leak. Surface scramble %, chip/sand saves, SG short, and around-the-green proximity.

- Dispersion + early trends are **prior-blended**: check `confidence` /
  `source_weight` (dispersion) and `n` (trends blocks). Low n or low weight ⇒
  say "early estimate", never present as measured fact. `total_yd` is GPS
  total distance (carry + roll), not carry.
- Typical flow for "where am I losing strokes?": `trends` → worst SG category →
  `compare_rounds` on recent rounds for specifics.

# Golf Reports

A **self-contained golf-data skill**: pulls your own data from **Arccos** (shot-level
+ strokes-gained), **GHIN** (official handicap + scores), and **18Birdies** (export
import), then **renders** any round to an HTML report (satellite shot map + stats)
and a shot-map PDF. Login-based — **no browser DevTools**. Runs **locally**, so it
works inside the Claude **Desktop app** (Chat / Cowork / Code) via a local MCP server.

> Why local: the Cowork cloud sandbox can't reach the golf APIs or your files. The
> engine runs on your machine and exposes tools to Claude. (Architecture vetted with Codex.)

## What's inside
```
ingest/    pull_arccos.py · pull_ghin.py · pull_18birdies.py   (login-based, no DevTools)
render/    gen_combined · gen_stats · gen_satellite · gen_gps_pdf · build_round_pages
           trends.py      (MCP tool: unified Arccos+GHIN+18Birdies history, WHS index + trajectory)
           dispersion.py  (MCP tool: per-club distance/lateral model → <store>/dispersion.json)
mcp/       server.py        (MCP tools: list_rounds, round_stats, render_round, sync_*, …
                             trends, compare_rounds, export_dispersion)
skills/    golf-reports/SKILL.md
setup.py   one-time login wizard
manifest.json / .claude-plugin/plugin.json   packaging
```
`export_dispersion` writes `<store>/dispersion.json` — an empirical-Bayes per-club total-distance and lateral-dispersion model (schema v1.0) used as the golfsmart bridge artifact.

## 1. One-time setup (no DevTools)
```bash
pip install -r requirements.txt
python3 setup.py          # prompts for Arccos + GHIN email/password, optional 18Birdies export
```
Credentials are stored **only on your machine** (`~/.arccos_creds.json`,
`~/.ghin_creds.json`, chmod 600) and never uploaded. Arccos stores a long-lived
accessKey (password discarded); GHIN password goes to the OS keychain when available (plaintext file only with explicit consent — it's needed each sync, 12h tokens).

## 2. Use it in the Claude Desktop app
**Cowork / Chat (recommended for non-devs):** install as a one-click **Desktop
Extension** (the local MCP server) — Customize → Browse plugins/extensions → add this
package. Then ask: *"sync my golf data"*, *"how was my last round?"*, *"render my
latest round as a PDF I can send."*

**Manual MCP config** (alternative): add to `claude_desktop_config.json`:
```json
{ "mcpServers": { "golf-reports": {
  "command": "python3", "args": ["/ABSOLUTE/PATH/golf-reports/mcp/server.py"],
  "env": { "GOLF_STORE": "/ABSOLUTE/PATH/golf-data",
           "GOLF_INGEST": "/ABSOLUTE/PATH/golf-reports/ingest",
           "GOLF_REPORTS": "/ABSOLUTE/PATH/golf-data/reports",
           "PYTHONPATH": "/ABSOLUTE/PATH/golf-reports/render" } } } }
```

**Claude Code (Code tab / CLI):** `/plugin marketplace add <your-gh>/golf-reports`
then `/plugin install golf-reports`, or copy `skills/golf-reports` into `~/.claude/skills/`.

## 3. CLI (works anywhere, no Claude)
```bash
cd render
python3 build_round_pages.py <store-dir-or-git-url> ./out --all --split
# -> <course>_<date>_report.html + _shotmaps.pdf (+ _stats.html + _map.html)
```
GPS columns in the store are opt-in when pulling: pass `--include-gps` to `pull_arccos.py` (or set `GOLF_INCLUDE_GPS=1`) if you want shot maps with real coordinates in a store you keep private.

## Notes & provenance
- **Strokes gained** (by category / 15-yd band / hole) is **measured** (Arccos, vs
  scratch). **Putting make %** and **approach proximity** are **derived heuristics**.
  **Peer carry** is vs a **modeled** ~12-HCP table — edit `render/peer_config.json`.
- Satellite tiles (Esri) load only when the **HTML is opened in a browser**; the **PDF**
  is the reliable offline/shareable artifact. GPS is optional at every layer (map
  omitted / PDF falls back to a distance schematic).
- Privacy: credentials, raw data, and reports stay local. Nothing is published.

## First-run checklist
1. Install the extension and confirm a tool (e.g. `list_rounds`) appears + runs from the **Cowork** tab.
2. Ask Claude to `sync_arccos` / `sync_ghin` and confirm files appear in your store (`~/golf-data` by default).
3. Ask Claude to `render_round` and open the HTML in a browser — satellite tiles should load.

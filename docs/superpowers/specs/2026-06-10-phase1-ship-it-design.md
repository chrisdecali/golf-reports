# golf-reports Phase 1 — "Ship it": fixes, automation, publish

**Date:** 2026-06-10
**Status:** Approved (design review with Cole, 2026-06-10)
**Scope:** Phase 1 of 4. Phases 2–4 sketched in the appendix; each gets its own spec.

## Goal

Make golf-reports safe and reliable enough to publish as a public Claude Desktop
plugin, and close the daily loop: new round → auto-sync → render → Telegram alert.

## Context

Full-codebase review (2026-06-10, two-agent pass + manual verification) found 2
credential/privacy P0-class issues, 6 P1s, and a set of P2 hardening items. The
architecture (ingest/render/MCP separation, pure `compute()`, GPS degradation)
is sound and unchanged by this phase.

## 1. Security & privacy fixes

| # | Issue | Location | Fix |
|---|-------|----------|-----|
| S1 | GHIN password stored plaintext | `setup.py:53`, `ingest/pull_ghin.py:122` | Store via `keyring` (OS keychain). Fallback to chmod-600 plaintext **only** after an explicit consent prompt naming the file. `pull_ghin.py` reads keyring first, file second. |
| S2 | GPS columns in default public outputs contradict docstring | `ingest/pull_arccos.py:26,566-571,692-693` | Add `--include-gps` flag (env `GOLF_INCLUDE_GPS=1`), default **off**: omit `start_lat/lng`, `end_lat/lng`, `pin_lat/lng` from `shots.csv`/`holes.csv`. Fix docstring. Cole's own cron sets the flag on (his publish choice is deliberate). |
| S3 | XSS: API strings interpolated unescaped into report HTML | `render/gen_combined.py:_html()`, `render/gen_stats.py` | `html.escape()` every API-sourced text field (course, tee, club, date, condition strings). `json.dumps` chart payloads already safe. |
| S4 | `import_18birdies` accepts arbitrary paths (file oracle; would parse `~/.arccos_creds.json`) | `mcp/server.py:114-118` | `os.path.realpath` the input; require: inside `~`, suffix `.json`, no control chars/null bytes. |
| S5 | `.gitignore` gaps: raw caches & outputs committable via `git add .` | `.gitignore` | Add `_cache*/`, `maps/`, `*.xlsx`, `*.html`, `*.pdf`. |
| S6 | Filenames built from API course names | `render/gen_combined.py:_slug()` | Sanitize slug: `re.sub(r'[^\w\-.]', '_', raw)`. |

## 2. Reliability fixes

| # | Issue | Location | Fix |
|---|-------|----------|-----|
| R1 | `GOLF_INGEST` defaults to `$HOME` — plugin users without env get "script not found" | `mcp/server.py:29` | Default to `<server_dir>/../ingest` (bundled scripts). |
| R2 | `:+d` format on `None` crashes render for rounds missing `score_to_par` | `render/gen_combined.py:270,312`, `render/gen_gps_pdf.py:83` | Null-guard all numeric format sites; render `—` when absent. |
| R3 | GHIN 401 error tells users to use DevTools (wrong flow) | `ingest/pull_ghin.py:160-162` | On 401: attempt re-login with stored creds once; if that fails, message "GHIN credentials expired — re-run setup.py". |
| R4 | MCP `_run` returns only last stdout line; errors hidden | `mcp/server.py:52-54` | Return last 5 stdout lines + stderr tail (1000 chars). |
| R5 | Any transient 5xx kills a whole pull | `pull_arccos.py:api_get`, `pull_ghin.py:ghin_get` | Retry ×3, exponential backoff, on 5xx/timeout only. |
| R6 | Non-atomic writes; concurrent syncs can interleave | `pull_arccos.py:_save`, MCP `_run` | tempfile + `os.rename` for JSON/CSV writes; lockfile in `_run` per script + 10-minute cooldown on `sync_*` tools (runaway-agent guard). |
| R7 | `openpyxl` imported but not declared | `requirements.txt` | Add `openpyxl>=3.0`. |

Explicitly **not** in scope: consolidating the three distance implementations
(haversine ×2, equirectangular ×1) — deferred to Phase 2 where dispersion work
touches that code anyway.

## 3. Automation: post-round alert

- Extend the existing cron pull (the job writing `arccos_out/_cron.log`).
- New `bin/post_round_alert.py`: snapshot `rounds_summary.csv` round_ids before
  sync; after sync, for each new round_id → `gen_combined.gen()` +
  `gen_gps_pdf.gen()` → send Telegram message via alfred's existing bot
  (reuse polo-index telegram pattern; token/chat from `~/.secrets.env`).
- Message: course, date, score (±par), top-line SG summary, paths to report.
- Idempotent: processed round_ids recorded in `arccos_out/_alerted.json`.

## 4. Publish

- Push `golf-reports` to GitHub (`chrisdecali/golf-reports`), public.
- Plugin marketplace entry; verify `/plugin install` flow.
- README quickstart verified on a clean machine (no `~/pull_*.py` copies, no
  pre-set env) — this is what R1 protects.

## 5. Tests (new; none exist today)

pytest + small fixture CSV store under `tests/fixtures/`:

1. `compute()` returns correct stats for a known fixture round.
2. Render of a round with `score_to_par=None` does not crash (R2 regression).
3. `_slug()` sanitizes hostile course names (S6).
4. `import_18birdies` path validation rejects traversal / non-JSON / creds file (S4).
5. GPS columns absent by default, present with flag (S2).
6. `_run` surfaces stderr on failing script (R4).

## Error-handling philosophy (applies this phase and onward)

Ingest never partial-writes (tempfile+rename). Render never crashes on missing
data — degrade like the existing GPS fallback. MCP tools always return an
actionable string, never a stack trace.

---

## Appendix: Phases 2–4 (sketches, own specs later)

**Phase 2 — Trends + what-if.** `trends.py` rolling SG by category; MCP tools
`trends`, `compare_rounds`. Keystone artifact: `dispersion.json` — per-club
empirical carry + lateral distributions from `shots.csv` GPS, lie-conditioned,
versioned schema. Monte Carlo round simulator over those distributions →
practice-ROI ranking; MCP tool `what_if`.

**Phase 3 — Trackman TPS ingest.** Cole's source: sim-bay Trackman Performance
Studio exports. Recon first: obtain one real TPS session export, lock parser to
it. `pull_trackman.py` → `range_sessions.csv` (club/ball speed, spin, launch,
carry). Range-vs-course gap report vs `clubs.csv`; TPS carries tighten Phase 2
dispersion priors.

**Phase 4 — Strategy engine × golfsmart.** Bridge = artifact export (decided):
golf-reports publishes `dispersion.json`; golfsmart (own repo, own spec) ingests
it, renders per-club ellipses on hole maps, aim-point optimizer grid-samples
targets scored by the Broadie expected-strokes surface already in
`pull_arccos.py`. DECADE-style per-hole club + target output.

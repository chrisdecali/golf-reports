# golf-reports Phase 2 — Trends, Dispersion, What-if (low-N aware)

**Date:** 2026-06-10
**Status:** Approved (design review with Cole, 2026-06-10). **Amended 2026-06-10: Monte Carlo what-if (section 4) CUT per Cole — descoped before implementation.**
**Depends on:** Phase 1 (shipped `a9d2a5a`). Phase 4 (golfsmart strategy engine) consumes this phase's `dispersion.json`.

## Goal

Multi-round analysis on top of the Phase 1 store: unified scoring history with
trends, a per-club dispersion model exported as a versioned artifact, and a
Monte Carlo what-if simulator that ranks practice priorities — all designed to
be honest at today's data volume (1 Arccos round, 3 GHIN scores) and to sharpen
automatically as rounds accumulate.

## Data reality (verified 2026-06-10)

- Arccos: `totalRounds=1` (account is new) — 95 shots, 18 holes, full GPS+SG.
- GHIN: 3 scores, empty handicap history (account also new).
- 18Birdies: **long history exists in Cole's account, export pending**
  (`18Birdies_archive.json` via 18birdies.com/download-account-data).
  `ingest/pull_18birdies.py` already parses it → `18birdies_rounds.csv`
  (date, course, gross, to_par, FW/GIR/putts, scoring distribution, hole_scores
  — no GPS; 18Birdies has none).

Implication: every model in this phase blends a documented prior with player
evidence, weighted by sample size; nothing pretends precision it doesn't have.

## 1. Unified history (inside `render/trends.py`, in-memory — no new CSV)

`history(store) -> list[dict]`: merge `18birdies_rounds.csv` + `ghin_scores.csv`
+ `rounds_summary.csv`.

- Row: date, course, holes, gross, to_par, putts, gir_pct, fairway_pct,
  differential, source (`arccos|18birdies|ghin`), round_id.
- Dedupe key: (date, normalized course name). Richness priority
  Arccos > 18Birdies > GHIN; a deduped row keeps the GHIN `differential` if any
  source row had it.
- Missing files tolerated (any subset of the three may exist).

## 2. Trends — MCP tools `trends()`, `compare_rounds(a, b)`

`trends(store, window=10) -> dict`:
- `scoring`: rolling mean gross over last 5/10/20 rounds vs the prior window
  (delta + direction), 18-hole rounds only for averages; 9-hole rounds excluded
  from scoring averages but counted in `rounds_total`.
- `stats_trends`: putts, gir_pct, fairway_pct — same rolling treatment over
  rows that carry them.
- `handicap`: WHS index computed from the merged differentials — best 8 of the
  most recent 20 (fewer-than-20 uses the official WHS reduced-count table),
  plus trajectory (index recomputed at each round date) and `projected_index`
  if the newest 5 rounds' average differential continues for 5 more rounds.
- `sg_trends`: per-category SG across Arccos rounds — present only when ≥2
  Arccos rounds exist, else `null` with `reason: "needs >=2 arccos rounds"`.
- Every block carries `n` (rows behind it).

`compare_rounds(store, rid_a, rid_b) -> dict`: two Arccos rounds — SG deltas by
category, GIR/FW/putts deltas, biggest-swing category.

WHS detail (testable): differential = (113 / slope) × (adjusted gross − rating);
GHIN rows carry it precomputed (use theirs); 18B/Arccos rows synthesize it only
when course rating+slope are present on the row, else those rounds are excluded
from index math (still in scoring trends).

## 3. Dispersion model — `render/dispersion.py` → `<store>/dispersion.json`

The Phase 4 bridge artifact. Empirical-Bayes per club:

- **Prior mean total distance**: `clubs.csv` `smart_distance_yd` (Arccos's own
  estimate). Clubs absent from clubs.csv: category default table (documented
  constants). Distances are GPS total (carry+roll) — field named `total_yd` for
  honesty; Arccos does not isolate carry.
- **Prior SDs** as fraction of total distance (documented constants, cite source
  comment): driver lateral 7%, fairway/hybrid 6%, mid-iron 5%, wedge 4%;
  distance SD: driver 5.5%, irons 5%, wedges 6%.
- **Evidence** from `shots.csv` (GPS rows only): per-club total-distance samples
  (`shot_distance_yd` for full swings — exclude putts, exclude
  `lie_approx in ("recovery","sand")` rows from distance stats); lateral deviation
  = perpendicular distance of shot end-point from the start→pin line (approach
  + tee shots with all five coordinates present).
- **Shrinkage**: posterior_mean = (n·x̄ + k·prior)/(n+k) with k_carry=15,
  k_lateral=25. `source_weight = n/(n+k)` reported per stat.
- **Confidence labels**: n<5 low, 5-19 medium, ≥20 high.
- **Schema v1.0 (locked — Phase 4 contract):**

```json
{
  "schema_version": "1.0",
  "generated_at": "2026-06-10T12:00:00Z",
  "player": {"hcp_index": 21.3, "rounds_with_gps": 1},
  "clubs": [
    {"club": "7 Iron", "category": "iron",
     "total_yd": {"mean": 158.2, "sd": 8.1, "n": 3, "source_weight": 0.17},
     "lateral_yd": {"sd": 7.9, "n": 2, "source_weight": 0.07},
     "usage_count": 7, "confidence": "low"}
  ]
}
```

- Writers: MCP tool `export_dispersion()` (returns path + summary) and
  `bin/post_round_alert.py` after each new round (try/except'd, non-fatal).
  Atomic write (tmp+replace). `.gitignore` already excludes nothing relevant —
  dispersion.json lives in the STORE (data repo), and publishing it there is
  fine (no GPS coordinates inside, only aggregates).

## 4. Monte Carlo what-if — `render/simulate.py`, MCP tool `what_if()`

Category-level simulation (hole-level deferred until real multi-round GPS):

- Player per-category SG means: from Arccos rounds, shrunk toward
  handicap-typical category splits (documented table mapping index → typical
  SG split by category) with the same n/(n+k) scheme, k=5 rounds.
- Per-round category SG variance: prior constants by category (documented).
- Simulate: score = course_par + scratch_expectation + Σ category draws;
  10,000 iterations, seeded RNG (`random.Random(seed)`, default seed=18).
- `what_if(store, category, gain)` → {current: {mean, p25, p75},
  improved: {...}, delta_strokes_per_round, new_projected_index (simulated
  differentials → WHS calc), category_roi_ranking (Δmean for a standardized
  0.5-stroke gain applied to each category)}.
- Honesty fields: `n_rounds_evidence`, `prior_weight`, and a `note` when
  prior-dominated.

## 5. MCP server + skill

- New tools: `trends`, `compare_rounds`, `export_dispersion`
  (server.py imports trends/dispersion from render dir — same pattern
  as gen_combined). `what_if`/simulate descoped (see section 4 amendment).
- `skills/golf-reports/SKILL.md`: document the three tools, when to call them,
  and interpretation guidance — explicitly: confidence "low" / high
  `prior_weight` ⇒ caveat the numbers; never present prior-dominated dispersion
  as measured fact.
- `manifest.json` + `.claude-plugin/plugin.json` tool lists updated (11 tools).

## 6. Tests (extend Phase 1 harness; ~12 new)

Fixture store gains `18birdies_rounds.csv` (6 rounds spanning 3 months, one
date+course overlapping GHIN for dedupe) and `ghin_scores.csv` (3 rows, one
overlapping). Cover: merge+dedupe priority, differential attachment, WHS best-8
-of-20 + reduced-count table, rolling trend windows, sg_trends gating (<2
arccos), dispersion shrinkage limits (n=0 → prior exactly; large synthetic n →
sample stats), lateral geometry on a constructed shot line, dispersion.json
schema validation, export_dispersion MCP round-trip.

## Non-goals (this phase)

golfsmart consumption (Phase 4), per-hole/aim-point modeling, Trackman (Phase
3), any new ingest source, UI.

## Live validation (gated on Cole's 18B export)

When `18Birdies_archive.json` arrives: `import_18birdies` → re-run `trends()`
against real history → sanity-check scoring averages and index trajectory by
eye. Not a build blocker; fixtures carry the correctness burden.

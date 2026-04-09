# Brainstorming Handoff: Next Big Accuracy Improvement

## What was done (2026-04-09)

### Player-Level TD Tendency — IMPLEMENTED (PR #26, merged)

Designed and implemented per-player red zone TD conversion factors. The simulation's TD gate (`_red_zone_td_gate()`) was uniform — Travis Kelce at the goal line got the same 55% pass TD gate as a backup TE. Now each player gets a Bayesian-blended factor that modifies the gate probability.

**Key files:**
- `src/fantasy_sim/data/td_tendency.py` — `TdTendencyEngine` with Bayesian blend, PFF + PBP fallback
- `src/fantasy_sim/engine/play_resolver.py` — `_red_zone_td_gate()` now accepts `td_factor` param
- `src/fantasy_sim/models/player.py` — `receiving_td_factor` and `rushing_td_factor` on `PlayerOutcomes`
- `config/defaults.yaml` — `td_tendency:` section (disabled by default, flip after A/B validation)
- `scripts/scrape_pff.py` — New `--fantasy-only` mode scrapes `fantasy_receiving` + `fantasy_passing` facets

**Data source:** PFF Fantasy Stats API (`/api/fantasy/stats/receiving`, `/api/fantasy/stats/passing`) scraped per-week. Key fields: `rz_rec_targ`, `rz_rec_tds`, `rz_rush_carries`, `rz_rush_tds`, `i5_rush_carries`, `i5_rush_tds`. PBP fallback via `rz_tds` counters added to `_aggregate_pbp_stats()`.

**Factor computation:**
```
observed = rz_tds / rz_opportunities (per player, weeks < target_week)
prior = positional average (WR ~0.17, RB ~0.28, TE ~0.15, QB ~0.25)
blended = (n * observed + prior_strength * prior) / (n + prior_strength)
factor = blended / prior  (centered on 1.0, clamped to [0.70, 1.30])
```

**A/B testing:**
```bash
uv run python scripts/validate.py --sims 50 --set td_tendency.enabled=true --label "td-tendency"
uv run python scripts/validate.py --sims 50 --set td_tendency.prior_strength=10 --label "td-ps10"
uv run python scripts/validate.py --sims 50 --set 'td_tendency.factor_clamp=[0.80,1.20]' --label "td-clamp-tight"
```

**Test count:** 1414 → 1447 (+33 tests across 6 test files)

**Review fixes (from Codex/Copilot):**
- Disabled by default in defaults.yaml (was accidentally enabled during sweep)
- Fixed partial PFF fallback: if one PFF channel loads but the other is missing, the missing channel now gets backfilled from PBP instead of staying neutral

### A/B Sweep Status

User is actively sweeping prior_strength and factor_clamp parameters. Results pending.

### 3. Route Rate A/B Test (QUICK) - TESTED AND THERE WAS NO IMPROVEMENT AT ALL
Built but never tested. Just flip the config and run:
```bash
uv run python scripts/validate.py --sims 50 --set usage.route_rate.enabled=true --label "route-rate"
```

---

## Still To Do (from original handoff)

### 2. CPOE Activation (MODERATE)
Config says `cpoe.enabled: true` but `_compute_cpoe_rolling()` returns data that is never applied to player outcomes. The computation works (returns QB gsis_id → rolling CPOE map) and the cpoe_map is passed to TierEngine, but the actual modulation of WR catch rates was never wired up. This is half-built — the signal exists, just needs to be consumed.

**Files:** `src/fantasy_sim/data/usage/engine.py`, `src/fantasy_sim/data/pff/tier_engine.py`

### 4. Game Script / Garbage Time (HIGH but HARD)
The sim tracks score differential in GameStateBucket and adjusts pass/run split, but doesn't model backup usage in blowouts, pace changes, or desperation target concentration. Biggest weekly correlation killer.

### 5. Inside-5 Sub-Factor (FOLLOW-UP from TD tendency)
The PFF data includes `i5_rush_carries` and `i5_rush_tds` (goal-line rushing). Currently scraped and stored but not consumed. Could add a separate inside-5 factor that applies to the tighter gate bands (1-5 yard line) for more granular goal-line differentiation.

### 6. Goal-Line Concentration (FOLLOW-UP from TD tendency)
Split `red_zone_target_share` into outer-RZ (6-20) and goal-line (1-5) sub-shares. Architecturally independent from TD tendency. Would let goal-line specialists (Derrick Henry at the 1) get proportionally more touches near the end zone.

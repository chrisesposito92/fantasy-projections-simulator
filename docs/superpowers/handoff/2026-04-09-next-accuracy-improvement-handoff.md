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

### 4. Game Script / Garbage Time — IMPLEMENTED (PR #28, merged)
Built a two-phase game-script layer:

1. `trailing_late`
   - team-specific pass-rate overlay
   - team-specific pace overlay
   - rank-based target concentration toward top pass catchers
2. `leading_late_rb`
   - RB-only carry redistribution in obvious late-lead states

The architecture is intentionally split:
- `src/fantasy_sim/data/game_script/engine.py` learns historical team profiles from nflverse PBP
- `src/fantasy_sim/engine/game_script.py` resolves the live runtime regime from `GameState`
- `src/fantasy_sim/engine/play_caller.py`, `src/fantasy_sim/engine/player_selector.py`, and `src/fantasy_sim/engine/game_sim.py` apply transient overlays at play-selection time
- `src/fantasy_sim/validation/game_script.py` prints learned-profile summaries during A/B runs

**Key files:**
- `src/fantasy_sim/data/game_script/models.py`
- `src/fantasy_sim/data/game_script/config.py`
- `src/fantasy_sim/data/game_script/engine.py`
- `src/fantasy_sim/engine/game_script.py`
- `src/fantasy_sim/engine/play_caller.py`
- `src/fantasy_sim/engine/player_selector.py`
- `src/fantasy_sim/engine/game_sim.py`
- `src/fantasy_sim/validation/game_script.py`
- `scripts/validate.py`
- `config/defaults.yaml`

**Validation outcome:**

At `--sims 50`, the feature clearly helped, but the marginal value of the RB late-lead subfeature was small relative to the trailing-late pass/pace/target effects.

At `--sims 200` and `--sims 400`, the picture stayed the same:
- `trailing_late` is the main win
- `leading_late_rb` is plausible but marginal / mixed
- a tighter RB clamp (`[0.85,1.15]`) performed slightly better than the looser default `[0.80,1.20]`, but still did not cleanly beat trailing-only on every top-line metric

Representative runs:
```bash
uv run python scripts/validate.py --sims 50 --set game_script.enabled=true --set game_script.trailing_late.enabled=true --set game_script.leading_late_rb.enabled=true --label "game-script-rb-baseline"
uv run python scripts/validate.py --sims 50 --set game_script.enabled=true --set game_script.trailing_late.enabled=true --set game_script.leading_late_rb.enabled=false --label "game-script-trailing-control"
uv run python scripts/validate.py --sims 200 --set game_script.enabled=true --set game_script.trailing_late.enabled=true --set game_script.leading_late_rb.enabled=false --label "game-script-trailing-control-200"
uv run python scripts/validate.py --sims 200 --set game_script.enabled=true --set game_script.trailing_late.enabled=true --set game_script.leading_late_rb.enabled=true --set 'game_script.leading_late_rb.rb_rank_factor_clamp=[0.85,1.15]' --label "game-script-rb-clamp-tight-200"
uv run python scripts/validate.py --sims 400 --set game_script.enabled=true --set game_script.trailing_late.enabled=true --set game_script.leading_late_rb.enabled=false --label "game-script-trailing-control-400"
uv run python scripts/validate.py --sims 400 --set game_script.enabled=true --set game_script.trailing_late.enabled=true --set game_script.leading_late_rb.enabled=true --set 'game_script.leading_late_rb.rb_rank_factor_clamp=[0.85,1.15]' --label "game-script-rb-clamp-tight-400"
```

**Recommended default posture after validation:**
- `game_script.enabled: true`
- `game_script.trailing_late.enabled: true`
- `game_script.leading_late_rb.enabled: false`
- `game_script.leading_late_rb.rb_rank_factor_clamp: [0.85, 1.15]`

In other words: ship the strong trailing-late feature by default, keep the RB late-lead behavior off unless explicitly testing it.

**Important implementation fixes that landed during review:**
- phase-specific nested `enabled` flags are now respected in both runtime and build-time learning
- dual-arm validation keeps `game_script` off the bare/off Arm A builder
- QB rushes are excluded from RB late-lead learning
- season-level validation summaries no longer overstate sample counts by summing cumulative weekly windows
- Python 3.14 CI regression fixed in cache-token test coverage

---

## Still To Do (from original handoff)

### 2. CPOE Activation — ALREADY DONE (Phase 3, USG-02)
CPOE was wired up during Phase 3. Enabled at sensitivity 0.30, `cpoe_map` feeds into TierEngine for QB adjustments. No further work needed.

### 5. Inside-5 Sub-Factor — IMPLEMENTED
Per-player inside-5 rushing TD factor using PFF `i5_rush_carries`/`i5_rush_tds`. Replaces general `rushing_td_factor` for gate bands (1,3) and (4,5) when sufficient data exists. Bayesian blend with inside-5-specific priors (RB ~0.50, QB ~0.40, FB ~0.55) and heavier shrinkage (prior_strength=25). PBP fallback for yardline_100 <= 5.

**Key changes:**
- `src/fantasy_sim/data/td_tendency.py` — `_DEFAULT_I5_RUSHING_TD_PRIORS`, i5 factor computation in `apply()`, extended `_load_pff_rates()` to 3-tuple
- `src/fantasy_sim/models/player.py` — `i5_rushing_td_factor` on `PlayerOutcomes`
- `src/fantasy_sim/engine/play_resolver.py` — gate selects i5 factor at yard_line <= 5
- `src/fantasy_sim/data/player_builder.py` — `i5_rush_carries`/`i5_rush_tds` in `_aggregate_pbp_stats()`
- `config/defaults.yaml` — `i5_enabled: false`, `i5_prior_strength: 25`, `i5_min_opportunities: 3`

**Test count:** 1447 → 1488 (+41 tests)

**A/B testing:**
```bash
uv run python scripts/validate.py --sims 50 --set td_tendency.i5_enabled=true --label "i5-subfactor"
uv run python scripts/validate.py --sims 50 --set td_tendency.i5_prior_strength=15 --label "i5-ps15"
uv run python scripts/validate.py --sims 50 --set td_tendency.i5_prior_strength=35 --label "i5-ps35"
```

**Design spec:** `docs/superpowers/specs/2026-04-09-inside-5-subfactor-design.md`

---

## Still To Do

### 6. Goal-Line Concentration (FOLLOW-UP from TD tendency)
Split `red_zone_target_share` into outer-RZ (6-20) and goal-line (1-5) sub-shares. Architecturally independent from TD tendency. Would let goal-line specialists (Derrick Henry at the 1) get proportionally more touches near the end zone.

### Recommendation for next accuracy work
If continuing the accuracy initiative, `Goal-Line Concentration` is now the clearest next standalone lever. `Game Script / Garbage Time` was the biggest remaining system-level gap and is no longer the next item.

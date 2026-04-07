# CLAUDE.md

## Project Overview

NFL fantasy football projections simulator. Simulates games play-by-play using historical nflverse data, runs Monte Carlo simulations, and produces fantasy point projections with full stat distributions.

## Tech Stack

- Python 3.12+ (currently running 3.14)
- uv for package management and virtual environment
- polars for DataFrames (NOT pandas)
- numpy for numerical simulation
- nflreadpy for NFL data from nflverse
- httpx for PFF API scraping
- pytest for testing (with pytest-xdist, hypothesis)
- YAML for configuration

## Commands

```bash
# Run all tests
uv run pytest tests/ -v

# Run specific test module
uv run pytest tests/test_engine/test_game_sim.py -v

# Run statistical validation tests only
uv run pytest tests/ -v -m statistical

# Run simulation validation script (5000 games)
uv run python scripts/validate_sim.py

# Run player validation (1000 sims, no network needed)
uv run python scripts/validate_players.py

# Run data validation (requires network)
uv run python scripts/validate_data.py

# PFF data scraper (requires premium subscription + cookie setup)
# See docs/pff-setup.md for cookie extraction instructions
# NFL (default)
uv run python scripts/scrape_pff.py --season 2024
uv run python scripts/scrape_pff.py --season 2026 --weeks 1-8
uv run python scripts/scrape_pff.py --season 2024 --process-only
# NCAA (weeks 0-16)
uv run python scripts/scrape_pff.py --league ncaa --season 2024
uv run python scripts/scrape_pff.py --league ncaa --season 2025 --weeks 0-8

# PFF talent coefficient fitting (requires network + PFF data)
uv run python scripts/fit_talent_coefficients.py
uv run python scripts/fit_talent_coefficients.py --apply

# PFF talent hyperparameter sweep (requires network + PFF data, ~40-60 min)
uv run python scripts/sweep_talent_params.py --sims 30
uv run python scripts/sweep_talent_params.py --sims 30 --apply

# PFF A/B validation (requires network + PFF data)
uv run python scripts/validate_pff_signal.py --mode talent --sims 50 --label "run-name"
uv run python scripts/validate_pff_signal.py --show-ledger
uv run python scripts/validate_pff_signal.py --mode talent --config-override '{"talent": {"prior_strength": 30}}'

# Weekly PFF validation (per-week granularity, all positions)
uv run python scripts/validate_weekly_signal.py --mode all --sims 50
uv run python scripts/validate_weekly_signal.py --mode coverage+tier --positions WR --sims 50
uv run python scripts/validate_weekly_signal.py --show-ledger
uv run python scripts/validate_weekly_signal.py --mode all --sims 50 --label "weekly-baseline"

# Install dependencies
uv pip install -e ".[dev]"

# Run CLI demo (synthetic data, no network needed)
uv run fantasy-sim demo --sims 100
uv run fantasy-sim demo --sims 100 --scoring half_ppr
uv run fantasy-sim demo --sims 100 --format csv --output projections.csv
uv run fantasy-sim demo --sims 100 --format json --output projections.json

# Simulate real NFL week (requires network)
uv run fantasy-sim week 1 --season 2024 --sims 100

# Simulate real NFL season (regular season only by default, requires network)
uv run fantasy-sim season --season 2024 --sims 50

# Season with per-week breakdowns
uv run fantasy-sim season --season 2024 --sims 50 --by-week

# Season export (format auto-inferred from extension)
uv run fantasy-sim season --season 2024 --sims 50 --output rankings.json

# Backtest against historical actuals
uv run fantasy-sim backtest --season 2024 --sims 50

# Override player/team stats
uv run fantasy-sim demo --sims 100 --override "HOME_WR1.target_share=0.30"
uv run fantasy-sim week 1 --season 2024 --override "mahomes.games_played=14"
uv run fantasy-sim week 1 --season 2024 --config config/season.example.yaml

# Game command (single-game deep dive)
uv run fantasy-sim game KC BUF --week 5 --sims 100
uv run fantasy-sim game HOME AWAY --demo --sims 100

# Player command (single-player projection)
uv run fantasy-sim player "nico_collins" --week 5 --sims 100
uv run fantasy-sim player HOME_QB --demo --sims 100

# Detail mode (floor/ceiling/stddev)
uv run fantasy-sim demo --sims 100 --detail
uv run fantasy-sim week 1 --sims 100 --detail

# Custom scoring
uv run fantasy-sim week 1 --scoring-config config/custom_scoring.yaml
```

## Architecture

The project is organized as a pipeline:

1. **Data Layer** (`data/loader.py`, `data/preprocessor.py`, `data/pipeline.py`, `data/player_builder.py`, `data/rookie_builder.py`, `data/game_context.py`, `data/actuals.py`, `data/pff/`) — Fetches nflverse data, caches as parquet, preprocesses into probability distributions, builds per-player models from PBP data, generates rookie archetypes, bridges real data to sim engine, loads actual player stats for backtesting. Player models separate stats (historical PBP) from team assignment (current-season roster) via `_aggregate_pbp_stats()` (cached, expensive) + `_assemble_models()` (cheap, per-week). `build_kicker_model()` creates placeholder kicker models for scoring attribution. The `data/pff/` subpackage provides matchup engine, talent stabilizer, PFF data loading, and configuration for PFF-based adjustments.
2. **Models** (`models/game_state.py`, `models/distributions.py`, `models/player.py`) — Shared data types used by both preprocessing and simulation, including player usage/outcome models and team rosters
3. **Engine** (`engine/types.py`, `engine/play_caller.py`, `engine/play_resolver.py`, `engine/player_selector.py`, `engine/game_flow.py`, `engine/clock.py`, `engine/game_sim.py`, `engine/monte_carlo.py`) — Play-by-play game simulation with player-level tracking and Monte Carlo runner
4. **Config** (`config/loader.py`, `config/defaults.yaml`) — YAML config loading with `_inherit` scoring preset inheritance (PPR, half-PPR, standard)
5. **Scoring** (`scoring/engine.py`, `scoring/projections.py`) — Config-driven fantasy point calculation for players, DST, and kickers; projection builder aggregates sim results into ranked projections
6. **Output** (`output/tables.py`, `output/export.py`) — Rich terminal tables by position, CSV/JSON export
7. **Validation** (`validation/metrics.py`, `validation/backtester.py`, `validation/report.py`) — Accuracy metrics (Spearman, MAE, boom/bust calibration), hold-out backtesting framework, formatted validation reports
8. **Overrides** (`overrides/engine.py`, `overrides/resolver.py`, `overrides/parser.py`) — Player/team override engine with proportional share redistribution, fuzzy name matching, YAML + CLI parsing
9. **CLI** (`cli.py`) — Click-based CLI with `demo`, `week`, `season`, `game`, `player`, `backtest` commands, `--override`, `--config`, `--detail`, `--scoring-config` flags, rich progress bars

## Key Patterns

- **ConfigLoader**: `load_config()` loads YAML, `resolve_scoring()` resolves `_inherit` chains. `load_defaults()` loads `config/defaults.yaml`. Scoring presets: PPR (base), half_ppr (_inherit: ppr, reception: 0.5), standard (_inherit: ppr, reception: 0).
- **ScoringEngine**: `score_player(box, config)` for QB/RB/WR/TE with position-specific reception keys (`reception_wr`, `reception_te`) and yardage bonus thresholds (`rushing_bonus_100`, `passing_bonus_300`). `score_dst(box, opponent_score, config)` with 7 points-allowed brackets. `score_kicker(box, config)` with FG distance buckets.
- **CustomScoring**: `load_custom_scoring(path, presets)` reads `custom_scoring.yaml` with `inherit` + `overrides` format. `_resolve_config_chain()` merges defaults -> season.yaml -> --scoring-config.
- **ProjectionBuilder**: `build_player_projections(games, config)` aggregates PlayerBoxScore across sims into mean stats + fpts, sorted by fpts. `build_detailed_projections(games, config)` adds floor (10th pct), ceiling (90th pct), and stddev for fpts and all tracked stats. `build_dst_projections(games, config, team_map)` for DST. `build_kicker_projections()` accepts optional rosters for real kicker attribution.
- **GameContextBuilder**: `build_game(home, away, training_seasons, target_season, week)` constructs `TeamDistributions` + `TeamRoster` per team from real nflverse data. Three-layer cache: pipeline output (training_seasons), PBP stats (training_seasons), player models (training_seasons + target_season + week). Falls back to league-average distributions for unknown teams. Roster loaded from `target_season`, optionally filtered to `week` for per-week accuracy (mid-season trades, IR moves).
- **ActualPlayerWeek**: Loads real player stats, scores with config. Used by backtester for comparison.
- **Backtester**: `Backtester(test_season, n_sims, num_training_seasons)` runs hold-out validation. `run(scoring_config)` returns `BacktestResult` with `passes_targets()` method. Targets: rank_corr > 0.80, weekly_mae < 6.0, season_mae < 25, calibration < 0.10.
- **OverrideEngine**: `apply_player_override(roster, player_id, overrides)` applies usage/outcome/meta overrides; automatically triggers `redistribute_target_shares()` or `redistribute_carry_shares()` for share fields. `apply_team_override(dists, overrides)` modifies PlayCallingDist and TurnoverRates. Both raise on unknown fields.
- **PlayerResolver**: `PlayerResolver(rosters).resolve(query)` resolves names to player_id via exact ID → exact name → underscore conversion → fuzzy match (thefuzz, MIN_MATCH_SCORE=70).
- **OverrideParser**: `parse_override_config(path)` reads season.yaml into `OverrideSet`. `parse_cli_override("name.field=value")` parses CLI strings. `_build_overrides()` in CLI merges config + CLI overrides (CLI takes precedence).
- **CLI**: `fantasy-sim demo` runs synthetic simulations. `fantasy-sim week N --season YYYY` simulates a real NFL week. `fantasy-sim season --season YYYY` simulates a full season (regular season only by default). `fantasy-sim game HOME AWAY` simulates a single matchup with per-team breakdowns. `fantasy-sim player QUERY` shows single-player projection via fuzzy matching. `fantasy-sim backtest --season YYYY` runs historical validation. Common options: `--sims`, `--scoring` (ppr/half_ppr/standard), `--scoring-config path/to/custom.yaml`, `--detail` (floor/ceiling/stddev), `--format` (table/csv/json), `--output`, `--override "name.field=value"`, `--config path/to/season.yaml`, `--pff/--no-pff`. `--by-week` on season command outputs per-week breakdowns with week headers instead of season totals. `--output` auto-infers format from `.json`/`.csv` extension. Season config `season:` and `weeks:` keys are used as defaults when CLI flags are not explicitly provided; `scoring_format:` always overrides CLI `--scoring`. See `docs/CONFIG.md` for full configuration reference.
- **GameStateBucket**: Discretized game state (down, distance, score_diff, quarter, yard_zone) used as dict keys for probability lookups. Defined in `models/game_state.py`, used everywhere.
- **Distribution types**: `PlayCallingDist`, `PlayOutcomeDist`, `TurnoverRates`, `KickingModel`, `DriveStartModel` in `models/distributions.py`. The sim engine samples from these.
- **Empirical distributions**: Play outcomes are stored as numpy arrays of historical values and sampled from directly (non-parametric).
- **MIN_BUCKET_PLAYS = 10**: Buckets with fewer than 10 plays fall back to team/league defaults.
- **GameState**: Mutable dataclass tracking game state (quarter, clock, possession, down, distance, yard_line, scores). `score_differential` is from possessing team's perspective.
- **yardline_100 convention**: 99=own 1, 75=own 25 (touchback), 50=midfield, 20=red zone, 1=goal line. TD when `yard_line - yards <= 0`. Safety when `yard_line - yards >= 100`.
- **Play resolution priority**: Scramble check (if roster) → sack check → interception check → normal pass outcome → home-field bonus. Fumble cancels TD. Penalty check post-play in game loop.
- **simulate_game()**: Main loop: 4th down decision → select play → resolve play → update box scores → update player stats → penalty check → handle outcome (safety/TD/turnover/yards) → clock → two-minute warning → quarter transitions. Optional `home_roster`/`away_roster` params enable player-level tracking.
- **TeamDistributions**: Bundles all distribution types needed per team. Passed to `simulate_game()` for home and away.
- **PlayerModel / TeamRoster**: Per-player usage rates (target_share, carry_share) and outcome distributions (catch_rate, yards distributions). `TeamRoster` provides weighted selection of passer/receiver/rusher. When rosters are provided, play resolution uses player-specific distributions instead of team-level ones.
- **PlayerBoxScore**: Per-player stats for one game (pass/rush/receiving). Tracked in `GameResult.player_stats` dict keyed by player_id.
- **player_builder**: Builds `PlayerModel` objects from PBP + roster data. `MIN_PLAYER_PLAYS = 5` for per-player yards distributions. Computes red zone shares (yardline_100 <= 20), air_yards_share, QB scramble_rate/scramble_yards_dist, and games_played. Optional `rookie_blend_games` param enables automatic archetype blending. `blend_with_archetype()` blends sparse player data with positional archetypes. `build_team_roster()` deepcopies players from cache and normalizes carry/target shares to sum to 1.0 among eligible players (prevents amplification when former players' shares are missing from current roster).
- **rookie_builder**: Generates `PlayerModel` for rookies using draft-capital-based archetypes (3 tiers by round).
- **Recency weighting**: `Preprocessor` methods accept `season_weights: dict[int, float]` to bias toward recent seasons via row replication.
- **Penalty modeling**: `check_penalty()` samples penalties from `PenaltyRates`; `apply_penalty()` creates penalty PlayResults. Wired into game_sim loop with `getattr` fallback for backward compatibility.
- **Home-field advantage**: `resolve_play(is_home=True)` gives 50% chance of +1 yard per play. `HOME_FIELD_YARDS_BONUS = 0.5`.
- **Two-minute warning**: `check_two_minute_warning()` snaps clock to 120s once per half in Q2/Q4. `GameState.two_min_warning_fired` resets at halftime.
- **Two-point conversions**: `attempt_pat()` returns scorer_id on 2PT success. `PlayerBoxScore.two_point_conversions` flows through `score_player()` via `config["two_point"]`.
- **Defensive TDs**: `_update_box_scores(rng=rng)` rolls for pick-six (~20% of INTs via `INT_RETURN_TD_RATE`) and fumble return TD (~10% via `FUMBLE_RETURN_TD_RATE`). `TeamBoxScore.defensive_tds` flows through `score_dst()` and `build_dst_projections()`.
- **Per-week availability**: `PlayerModel.weeks_missed: list[int]` stores specific weeks a player misses. `_filter_available()` in `player_selector.py` excludes them during those weeks. `GameState.week` tracks current week (0 = unset). Set via `games_missed` override.
- **Pace factor**: `TeamDistributions.pace_factor` (default 1.0) scales clock runoff via `_scale_clock_runoff()` in `play_resolver.py`. Set via `pace_plays_per_game` team override (baseline 65 plays/game).
- **Ambiguous match detection**: `PlayerResolver.resolve()` raises `AmbiguousMatchError(KeyError)` when 2+ players match within `AMBIGUITY_THRESHOLD=5` points. Exact ID/name lookups bypass the check.
- **Red Zone TD Gate**: `_red_zone_td_gate(yard_line, play_type, rng)` in `play_resolver.py` applies a per-play probability check when a play would score inside the 20. Constants `PASS_TD_GATE` (0.55-0.15) and `RUN_TD_GATE` (0.35-0.08) are calibrated so drive-level TD rates match NFL averages (~55% of RZ drives end in TD). Failed gates result in the player being tackled short. `_clamp_yards()` prevents exceeding yard_line; no additional RZ yards capping is needed.
- **Red Zone Catch Rate**: `PlayerOutcomes.red_zone_catch_rate` stores per-player RZ catch rate from PBP data (≥10 RZ targets) or `catch_rate * 0.92` fallback. Used in `_resolve_pass()` when `yard_line <= 20`. `MIN_RZ_TARGETS = 10` constant in `player_builder.py`. `RZ_CATCH_RATE_MODIFIER = 0.92` (real NFL RZ catch rates are ~92% of overall).
- **Catch Yards Boost**: `CATCH_YARDS_BOOST = 1` in `play_resolver.py` adds 1 yard to each sampled catch **outside the red zone only** to compensate for field-position clamping bias. Inside the 20, the boost is disabled to prevent TD inflation (the TD gate controls scoring probability). Per-player `receiving_yards_dist` arrays are field-position-independent, but `_clamp_yards()` truncates long catches near the goal line, systematically reducing yards/completion by ~1-2 yd vs the distribution mean.
- **QB Designed Run Separation**: `MIN_QB_CARRY_SHARE = 0.10` in `models/player.py` excludes pocket-passer QBs from the designed-run rusher pool. In `player_builder.py`, QB carry_share is computed from **designed runs only** (scramble carries are subtracted when `qb_scramble` data is available) to prevent double-counting — scrambles are already modeled separately in `_resolve_pass()` via the scramble_rate check.
- **Sack-Fumble Attribution**: In `game_sim.py`, sack-fumbles increment `qb.fumbles_lost` (fantasy football charges sack-fumbles to the QB). The condition checks `is_fumble and not is_complete and not is_interception` (no `not is_sack` exclusion).
- **RZ Receiving Yards**: `PlayerOutcomes.rz_receiving_yards_dist` stores per-player catch yards from PBP plays inside the 20 (≥5 RZ catches). Built in `player_builder.py`. Currently populated but not used in play resolution (field-position clamping + boost is the active approach).
- **QB Pass Fumble Rate**: `PlayerOutcomes.pass_fumble_rate` stores per-QB non-sack fumble rate (≥100 passes) or league average 0.0034. Checked pre-throw in `_resolve_pass()` after INT check, before receiver selection.
- **Scramble Rate**: Uses `qb_scramble` column from nflverse PBP to separate actual scrambles from designed runs. Falls back to all QB rushes if column is missing. `scramble_yards_dist` built from scramble-only plays.
- **PFF Intelligence Layer**: Five active layers in `data/pff/` (tier + team context + matchup + kicker + dst_baseline) plus NCAA rookie tier assignment. **TierEngine** (`tier_engine.py`) assigns players to PFF grade-based tiers and blends tier distributions with PBP data weighted by reliability. Current config: 5 tiers, `reliability_floor=0.20`/`reliability_cap=0.80`, WR `secondary=_disabled` (within-tier interpolation adds noise for WRs). QBs only blend fumble_rate (all other fields skipped). `apply_team_context()` static method adjusts `TierDistributions` before blending. `_apply_rookie_tiers()` handles rookies without NFL PFF data via NCAA grades and the `pff_id` bridge, with draft-capital-modulated blend confidence (`NcaaRookieConfig`). WR archetype sub-pooling: 3 depth archetypes (slot/possession/deep) within each WR tier based on ADOT from `receiving_summary`. Overrides `receiving_yards_dist` and `catch_rate` per archetype. Falls back to full tier pool when sub-pool < `min_archetype_pool_size` (20). NCAA rookies get archetype assignment via NCAA ADOT. Config in `defaults.yaml` under `pff.tier_engine.archetypes`. **TeamContextEngine** (`team_context.py`) computes season-level team environment factors via z-scores: team pass rate (PBP) → WR/TE `target_share`, OL run block grade (PFF `offense_run_blocking`) → RB `rushing_yards_dist`, QB quality (PFF `passing_summary`) → WR/TE `catch_rate`. Same-season rolling window with early-season blend (linear ramp, `min_games=4`). Snap-weighted aggregation for OL and QB data. Applied to `TierDistributions` before `_blend_player()`. Config in `defaults.yaml` under `pff.team_context`. **MatchupEngine** (`matchup.py`) computes per-game `MatchupContext` from PFF defensive + OL data via z-scores clamped to `factor_clamp` range. Uses same-season rolling window: `compute(defense_team, offense_team, target_season, max_week)` filters PFF data to `week < max_week`. Early-season blend with previous season via linear ramp when team has < `min_games` (4) games. Medium sensitivities (0.06-0.075). Factors: `catch_rate_factor`, `pass_yards_factor`, `sack_rate_factor`, `int_rate_factor`, `rush_yards_factor`, `ol_pass_block_factor`, `ol_run_block_factor`. Applied in `GameContextBuilder.build_game()` — away D adjusts home O and vice versa. **TalentStabilizer** (`talent.py`, currently disabled) uses Bayesian blending with divergence detection. Config in `defaults.yaml` under `pff:` section. CLI `--pff/--no-pff` flag overrides config. Ordering: base model → matchup → team context + tier blend → normalize → user overrides → normalize. A/B validation with persistent results ledger (`scripts/validate_pff_signal.py --show-ledger`). `--config-override` supports `tier_engine`, `talent`, `matchup`, `team_context`, and `ncaa_rookie` keys for sweep testing. **CoverageEngine** (`coverage.py`) computes per-WR modifiers by mapping WR alignment to opposing CB, then computing z-scored catch_rate and YPR factors from the CB's rolling performance profile. Outcome-based stats (catch rate allowed, YPR allowed) serve as primary signal with PFF grades as stabilizer for low-sample CBs (reliability ramp at min_coverage_targets). Applied as the last PFF step in `build_game()` after tier engine and share normalization. Config in `defaults.yaml` under `pff.coverage`. A/B harness modes: `--mode coverage+tier`, `--mode coverage+tier+matchup`. **KickerEngine** (`kicker.py`) loads `field_goal_summary` per-kicker FG accuracy, applies Bayesian shrinkage toward league average, replaces team-level `KickingModel` in `build_game()`. Config in `defaults.yaml` under `pff.kicker`. **DstBaselineEngine** (`dst_baseline.py`) computes `fumble_rate_factor` (z-score from forced fumbles) and team-specific `int_return_td_rate`/`fumble_return_td_rate` (Bayesian shrinkage). Applied after coverage in `build_game()`. Config in `defaults.yaml` under `pff.dst_baseline`.
- **Weather Engine**: `data/weather/` package adds game-day weather adjustments as the final layer in `build_game()`, after all PFF layers. Three components: **StadiumRegistry** (`stadiums.py`) maps 32 teams to lat/lon + venue type (outdoor/dome/retractable); dome games short-circuit to neutral factors. **WeatherProvider** (`provider.py`) fetches hourly data from Open-Meteo (free, no API key) — historical archive for past dates, forecast API for future dates. JSON cache at `~/.fantasy-sim/weather/` with 6-hour TTL for forecasts. **WeatherEngine** (`engine.py`) computes multiplicative factors using threshold + linear scaling (not z-scores — weather has absolute thresholds, not relative ones). Wind (threshold 10 mph) affects FG accuracy (50+ yard multiplier 2.5x), XP, pass yards, INT rate. Temperature (threshold 35°F, inverted) affects fumble rate. Precipitation affects catch rate, fumble rate, FG, pass yards. Factors from multiple variables combine multiplicatively, clamped to `[0.80, 1.20]`. Config in `defaults.yaml` under `weather:` (enabled by default). CLI `--weather/--no-weather` flag on week/season/game/player/backtest commands. A/B harness modes: `--mode weather`, `--mode weather+tier`, `--mode weather+tier+matchup`. `--config-override` supports `weather` key for sensitivity sweeps.
- **GitHub Actions CI**: `.github/workflows/ci.yml` runs pytest on push/PR across Python 3.12/3.13/3.14 with uv caching. Statistical tests gated by PR label.

## Testing

- Tests mirror src structure: `tests/test_data/`, `tests/test_models/`, etc.
- Script tests in `tests/test_scripts/` (e.g., PFF scraper tests)
- Fixtures in `tests/conftest.py` provide sample PBP data (20 plays, KC/BUF)
- Tests use `unittest.mock.patch` to mock nflreadpy calls (no network in unit tests)
- Integration tests marked with `@pytest.mark.integration`
- Statistical tests marked with `@pytest.mark.statistical`

## Current State

- **Phase 1 (Data Pipeline)**: Complete — 67 tests
- **Phase 2 (Game State Machine)**: Complete — 80 tests (147 total)
- **Phase 3 (Player Models)**: Complete — 61 tests (208 total)
- **Phase 4 (Scoring + Config + CLI)**: Complete — 52 tests (260 total)
- **Phase 5 (Validation + Tuning)**: Complete — 31 tests (291 total)
- **Phase 6 (Overrides + Polish)**: Complete — 38 tests (329 total)
- **Phase 7A (Data + Engine Accuracy)**: Complete — 41 tests (370 total)
- **Phase 7B (Scoring + Config + CLI)**: Complete — 48 tests (418 total)
- **Phase 7C (Polish + Tests + CI)**: Complete — 87 tests (505 total)
- **Roster/Team Assignment Fix**: Complete — 21 tests (533 total). Separated player team assignment (current-season roster) from statistical profile (historical PBP). Fixes traded players, missing kickers, missing rookies, and retired player inclusion.
- **Red Zone Accuracy**: Complete — 45 tests (578 total). Red zone TD probability gates, per-player RZ catch rates, QB pre-throw fumble check, scramble rate fix using qb_scramble column.
- **Passing Yards Calibration**: Complete — 579 tests. Removed broken RZ yards blending (team distribution included incompletions/sacks, capping RZ completions to 1 yard ~45% of the time). Calibrated clock runoff for ~65 plays/team/game. Fixed fallback yards for players without personal distributions.
- **Passing Yards Boost**: Complete — 582 tests. Fixed wasted RNG call in `_resolve_pass()` (team_yards sample moved to fallback-only). Added `CATCH_YARDS_BOOST = 1` to compensate for field-position clamping bias (per-player distributions are field-position-independent; clamping near the goal line systematically reduces yards/completion by ~1-2 yd). Raised `RZ_CATCH_RATE_MODIFIER` from 0.85 to 0.92 (real NFL RZ completion rates are ~92% of overall). Added `rz_receiving_yards_dist` to PlayerOutcomes. Added passing diagnostic script (`scripts/validate_passing.py`). Added 3 statistical validation tests for completion rate, yards/completion, and pass yards/team. Top QB now projects ~4,000+ season passing yards (was ~3,500).
- **Post-Boost Bug Fixes**: Complete — 582 tests. Fixed three bugs: (1) QB carry_share double-counted scrambles — now subtracts scramble carries in `player_builder.py` + `MIN_QB_CARRY_SHARE=0.10` threshold excludes pocket passers from designed runs (Herbert 850→208 RuYd). (2) `CATCH_YARDS_BOOST` restricted to outside the red zone, preventing TD inflation (Goff 43.7→37.1 PaTD). (3) Sack-fumbles now attributed to QB's `fumbles_lost` in `game_sim.py` (QBs now show 1.3-4.2 FL/season, was 0.0-0.4).
- **Share Normalization Fix**: Complete — 594 tests. Fixed carry_share/target_share amplification bug: shares from multi-season PBP data didn't sum to 1.0 on the current roster (former players had carries/targets but aren't on roster). `select_rusher`/`select_receiver` normalize weights, so a 0.72 carry_share override became 87% actual selection probability. Fix: `build_team_roster()` now deepcopies players (preventing cache mutation from overrides) and normalizes all share types (carry, target, RZ carry, RZ target) to sum to 1.0 among eligible players. `_normalize_roster_shares()` and `_scale_shares()` in `player_builder.py`.
- **PFF Data Scraper**: Complete — 619 tests. Standalone script (`scripts/scrape_pff.py`) extracts game-level player data from PFF's premium REST API (21 facets per game). Supports NFL and NCAA via `--league` flag (`nfl` default, `ncaa`). Stores raw JSON as immutable archive at `~/.fantasy-sim/pff/raw/<league>/`, processes into per-facet-per-season parquet at `~/.fantasy-sim/pff/processed/<league>/`. NCAA weeks are 0-16 (vs NFL 1-18 + postseason). Cookie-based auth, per-league resume via `state/progress_<league>.json`, exponential backoff on rate limits. See `docs/pff-setup.md` for setup.
- **PFF Intelligence Layer**: Complete — 101 tests. Defensive matchup engine (z-score based per-game adjustments from PFF defensive + OL data) and talent stabilizer (Bayesian blending with divergence detection). Replaces failed modifier approach.
- **PFF Talent Tuning Pipeline**: Complete — 178 tests (837 total). Seven improvements to push talent stabilizer from SOFT_PASS toward PASS. Fitted OLS regression coefficients (found 2 sign errors in hand-tuned catch_rate coefficients, 13x underweight on ADOT). Added target_share, fumble_rate, and QB scramble_rate stabilization. Position-specific prior_strength (QB:60, WR:40, TE:35, RB:30). Team-change boost (prior_strength × 0.5 for traded players). Schedule-adjusted talent evaluation (architecture in place, needs per-game opponent tracking). NCAA rookie priors from college PFF grades. Persistent A/B results ledger. Sensitivity sweep script. Best A/B result: rank_corr +0.0069, season_mae -0.441 (run #3 with additional params).
- **PFF Tier Engine Config Sweep**: Complete — 875 tests. Swept reliability floor/cap, WR secondary grade, and tier count against baseline #9. Best combo (#15 tier-tight+wr-nosec): rank_corr +0.0353, wk_mae -0.254, szn_mae -3.201. Applied to defaults.yaml: `reliability_floor=0.20`, `reliability_cap=0.80` (more tier influence), WR `secondary=_disabled` (within-tier interpolation was adding noise). 4 tiers ruled out (worse rank_corr than 5 tiers). Added `--config-override` support for tier_engine in A/B harness.
- **PFF Matchup Engine Re-enablement**: Complete — 886 tests. Re-enabled matchup engine with same-season rolling window (week < max_week filter) instead of cross-season. Early-season blend: linear ramp with previous season when team has < min_games (4) games. Swept sensitivities: medium (0.06-0.075) won (#20 matchup+tier-med-sens: rank_corr +0.0376, wk_mae -0.306, szn_mae -4.331). Matchup + tier confirmed additive — tier handles ranking, matchup improves weekly MAE and calibration. Added `--mode matchup` and `--mode matchup+tier` to A/B harness.
- **PFF Team Context Layer**: Complete — 925 tests. Season-level team environment factors adjust tier distributions before blending with PBP data. Three factors: team pass rate (PBP) → WR/TE target_share, OL run blocking grade (PFF) → RB rushing_yards_dist, QB quality (PFF) → WR/TE catch_rate. Same-season rolling window with early-season blend. Snap-weighted aggregation for OL and QB. `TeamContextEngine` is a peer to `MatchupEngine` and `TierEngine`, orchestrated by `GameContextBuilder`. A/B harness modes: `--mode team_context+tier`, `--mode team_context+tier+matchup`. Config-override supports `team_context` key.
- **NCAA Rookie Tier Assignment**: Complete — 949 tests. Uses college PFF grades to place rookies into NFL talent tiers via the `pff_id` bridge (nflverse roster `pff_id` == NCAA PFF `player_id`, 85/85 drafted + 143/144 total match rate). Grade drives tier assignment (direct comparison against NFL boundaries), draft capital modulates blend confidence (`NcaaRookieConfig` with per-round confidence curve). All rookies with NCAA PFF data get grade-based assignment; players without fall back to existing `rookie_builder.py` archetypes. `TierEngine._apply_rookie_tiers()` processes players skipped by the NFL PFF crosswalk. A/B harness modes: `--mode ncaa_rookie+tier`, `--mode ncaa_rookie+tier+matchup`. Config in `defaults.yaml` under `pff.tier_engine.ncaa_rookie`.
- **WR Depth-of-Target Archetypes**: Complete — 978 tests. 3 archetype sub-pools (slot/possession/deep) within each WR tier classified by ADOT. Overrides receiving_yards_dist and catch_rate. NCAA rookies get archetype assignment. Global ADOT percentile boundaries (p33/p67). Falls back to full tier pool when sub-pool < min_archetype_pool_size.
- **PFF Coverage Matchup Engine**: Complete — 20 tests (1000 total). Per-WR coverage adjustments using defense_coverage_matchup facet. Alignment-based CB mapping (RWR→LCB, LWR→RCB, slot→SCB), outcome-based stats with grade stabilizer, catch_rate + YPR modifiers. WR-only, TEs excluded for v1.
- **Weekly Validation Harness**: Complete — scripts/validate_weekly_signal.py with per-week metrics (rank_corr, MAE, MAE by difficulty, WR directional accuracy). Separate ledger at results/weekly_ab_ledger.json.
- **PFF Kicker/DST Baseline**: Complete — 29 tests (1068 total). Per-kicker FG accuracy from PFF field_goal_summary with Bayesian shrinkage replaces placeholder model. DST baseline engine adjusts fumble_rate (z-score) and team-specific defensive TD rates (Bayesian shrinkage) from PFF defense_summary. Non-overlapping with matchup engine. Config in `defaults.yaml` under `pff.kicker` and `pff.dst_baseline`.
- **Weather Engine**: Complete — 54 tests (1122 total). Game-day weather adjustments (wind, temperature, precipitation) from Open-Meteo API. Applied as final layer in `build_game()` after all PFF layers. Threshold + linear factor model (not z-scores). 32-team stadium registry with dome detection. JSON cache with forecast TTL. CLI `--weather/--no-weather` flag. A/B harness support with `--mode weather`, `--mode weather+tier`, `--mode weather+tier+matchup`.

## Style

- Use polars, not pandas
- Use numpy for arrays and random sampling
- Dataclasses for data types (frozen when used as dict keys)
- Type hints on all function signatures
- Tests follow TDD: test first, then implement

<!-- GSD:project-start source:PROJECT.md -->
## Project

**Fantasy Projections Simulator — Accuracy Initiative**

An NFL fantasy football projections simulator that simulates games play-by-play using historical nflverse data, PFF intelligence layers, and weather adjustments, then runs Monte Carlo simulations to produce fantasy point projections with full stat distributions. This initiative focuses on improving projection accuracy across all metrics — ranking correlation, weekly/season MAE, and boom/bust calibration — through new data sources, modeling improvements, and better signal extraction.

**Core Value:** **Projection accuracy that beats the current best A/B results (run #44: rank_corr +0.0517) and pushes toward absolute targets (rank_corr > 0.80, weekly_mae < 6.0) — with WR and QB accuracy as the highest-priority positions.**

### Constraints

- **Data**: PFF premium subscription available. Open to free sources. Will consider paid if justified by A/B results.
- **Methodology**: All improvements must be validated through A/B harness before merging. No changes without measurable signal.
- **Architecture**: Open to any approach (new layers, ML models, structural changes) — whatever moves the metrics.
- **Testing**: Must maintain 1,122+ test suite. New features need tests.
- **Positions**: WR and QB accuracy are highest priority but all positions matter.
<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->
## Technology Stack

## Languages
- Python 3.12+ (currently running 3.14.3) - All source code, scripts, tests
- YAML - Configuration (`config/defaults.yaml`, scoring presets, season overrides)
- JSON - PFF raw data archive, weather cache, A/B test ledgers
## Runtime
- Python 3.14.3 (development machine)
- CI tests across Python 3.12, 3.13, 3.14
- `uv` (Astral) - Package management and virtual environment
- Lockfile: `uv.lock` present (revision 3)
- Install: `uv pip install -e ".[dev]"`
- Run commands: `uv run pytest`, `uv run fantasy-sim`
## Frameworks
- No web framework - CLI application only
- Click 8.3.1 - Command-line interface with subcommands (`demo`, `week`, `season`, `game`, `player`, `backtest`)
- Rich 14.3.3 - Terminal output (tables, progress bars, spinners)
- pytest 9.0.2 - Test runner
- pytest-xdist 3.8.0 - Parallel test execution
- Hypothesis 6.151.10 - Property-based testing
- Hatchling - Build backend (`[build-system]` in `pyproject.toml`)
- Wheel packages built from `src/fantasy_sim/`
## Key Dependencies
- `polars` 1.39.3 - All DataFrame operations (NOT pandas). Used for PBP data, rosters, PFF data, aggregations
- `numpy` 2.4.4 - Numerical arrays for play outcome distributions, random sampling (`rng.choice()`), Monte Carlo simulation
- `scipy` 1.17.1 - Statistical functions (implicit dependency, used in distribution fitting)
- `nflreadpy` 0.1.5 - NFL data from nflverse (play-by-play, rosters, schedules, snap counts, depth charts, draft picks). Returns Polars DataFrames natively. Depends on `requests`, `pydantic`, `tqdm`, `platformdirs`.
- `httpx` 0.28.1 - HTTP client for PFF REST API scraping and Open-Meteo weather API
- `pyyaml` 6.0.3 - YAML config file loading
- `thefuzz` 0.22.1 - Fuzzy string matching for player name resolution (backed by `rapidfuzz` 3.14.3)
- `click` 8.3.1 - CLI framework
- `rich` 14.3.3 - Terminal tables and progress bars
- `rapidfuzz` 3.14.3 - C-extension backend for thefuzz (fast Levenshtein distance)
- `pydantic` 2.12.5 - Used by nflreadpy internally for data validation
- `requests` 2.33.0 - Used by nflreadpy for HTTP downloads from GitHub
- `tqdm` 4.67.3 - Progress bars (nflreadpy dependency)
- `platformdirs` 4.9.4 - nflreadpy cache directory resolution
## nflverse Data Stack
| Function | Wrapper In | Used By | Purpose |
|----------|-----------|---------|---------|
| `load_pbp(seasons)` | `DataLoader.load_pbp()` | `DataPipeline`, `GameContextBuilder`, `TierEngine`, `TeamContextEngine` | Play-by-play data - the core dataset. ~13MB/season. |
| `load_rosters_weekly(seasons)` | `DataLoader.load_rosters()` | `GameContextBuilder`, `PffLoader.build_crosswalk()`, `KickerEngine` | Weekly roster snapshots with team, position, status, pff_id, college_name, rookie_year |
| `load_schedules(seasons)` | `DataLoader.load_schedules()` | `WeatherEngine`, `Backtester`, CLI `week`/`season`/`backtest` commands | Game schedule with dates, times, matchups |
| `load_player_stats(seasons)` | `DataLoader.load_player_stats()` | `Backtester`, `load_actual_scores()` | Weekly player stat lines for backtesting against actuals |
| `load_snap_counts(seasons)` | `DataLoader.load_snap_counts()` | Available but not currently called in main pipeline | Per-player snap counts |
| `load_depth_charts(seasons)` | `DataLoader.load_depth_charts()` | Available but not currently called in main pipeline | Team depth charts |
| `load_draft_picks()` | `DataLoader.load_draft_picks()` | `rookie_builder.py` (draft capital tier determination) | Historical draft data (round, pick number) |
| Column | Used In | Purpose |
|--------|---------|---------|
| `play_type` | `preprocessor.py`, `player_builder.py`, `pipeline.py` | Filter to "pass", "run", "field_goal", "extra_point", "kickoff" |
| `season` | `player_builder.py`, `preprocessor.py` | Season filtering, recency weighting |
| `posteam` | `preprocessor.py`, `player_builder.py` | Possessing team (for team-level stats) |
| `yards_gained` | `preprocessor.py`, `player_builder.py` | Play outcome yards (stored as empirical distributions) |
| `receiver_player_id` | `player_builder.py` | Links pass plays to receivers |
| `rusher_player_id` | `player_builder.py` | Links run plays to rushers |
| `passer_player_id` | `player_builder.py` | Links pass plays to QBs |
| `complete_pass` | `player_builder.py` | Catch rate computation |
| `interception` | `preprocessor.py`, `player_builder.py` | INT rate, QB fumble filtering |
| `fumble_lost` | `preprocessor.py`, `player_builder.py` | Fumble rates, sack-fumble rates |
| `sack` | `preprocessor.py`, `player_builder.py` | Sack rate, sack-fumble attribution |
| `yardline_100` | `preprocessor.py`, `player_builder.py` | Red zone detection (<=20), field position |
| `game_id` | `player_builder.py` | Games played counting (unique game_ids per player) |
| `air_yards` | `player_builder.py` | Air yards share computation (optional, may be absent) |
| `qb_scramble` | `player_builder.py` | Separating scrambles from designed QB runs (optional) |
| `penalty` | `preprocessor.py` | Penalty rate computation |
| `touchback` | `preprocessor.py` | Drive start model (touchback rate) |
| `extra_point_result` | `preprocessor.py` | XP make rate ("good" = success) |
| `kick_distance` | `preprocessor.py` | FG distance bucketing (0-39, 40-49, 50+) |
| `field_goal_result` | `preprocessor.py` | FG make rate ("made" = success) |
| Column | Used In | Purpose |
|--------|---------|---------|
| `player_id` (or `gsis_id`) | Everywhere | Primary player identifier (auto-renamed from `gsis_id`) |
| `player_name` (or `full_name`) | Everywhere | Display name (auto-renamed from `full_name`) |
| `team` | `player_builder.py`, `game_context.py` | Current team assignment |
| `position` | `player_builder.py` | Position filtering (QB, RB, WR, TE, K) |
| `status` | `player_builder.py` | Active status filtering (`ACT` only) |
| `season` | `game_context.py` | Season filtering for roster merges |
| `week` | `game_context.py` | Week filtering for mid-season roster accuracy |
| `pff_id` | `pff/loader.py` | PFF crosswalk Layer 1 (direct ID match) |
| `college_name` | `pff/loader.py` | NCAA crosswalk (name + college match for rookies) |
| `rookie_year` | `pff/loader.py` | NCAA crosswalk season filtering |
| `draft_number` / `draft_round` | `player_builder.py` | Rookie archetype tier assignment |
| Column | Used In | Purpose |
|--------|---------|---------|
| `week` | `backtester.py`, CLI, `weather/engine.py` | Week number |
| `home_team` | CLI, `weather/engine.py` | Home team abbreviation |
| `away_team` | CLI, `weather/engine.py` | Away team abbreviation |
| `game_id` | `backtester.py` | Deterministic seed for Monte Carlo |
| `gameday` | `weather/engine.py` | Game date (for weather lookup) |
| `gametime` | `weather/engine.py` | Kickoff hour (for weather window) |
| `season` | `backtester.py` | Season filtering |
| Column | Used In | Purpose |
|--------|---------|---------|
| `player_id`, `player_name`/`player_display_name` | `actuals.py` | Player identification |
| `position`, `recent_team`/`team` | `actuals.py` | Position and team |
| `season`, `week` | `actuals.py` | Time filtering |
| `passing_yards`, `passing_tds`, `interceptions`/`passing_interceptions` | `actuals.py` | QB stats for scoring |
| `rushing_yards`, `rushing_tds`, `carries` | `actuals.py` | Rush stats for scoring |
| `receptions`, `targets`, `receiving_yards`, `receiving_tds` | `actuals.py` | Receiving stats for scoring |
| `receiving_fumbles_lost`, `rushing_fumbles_lost`, `sack_fumbles_lost` | `actuals.py` | Fumble attribution |
| `completions`, `attempts`, `sacks`/`sacks_suffered` | `actuals.py` | Additional QB stats |
- Training: 3 years prior to target season (configurable via `defaults.yaml` `simulation.training_years`)
- Default: `[2022, 2023, 2024]` (set in `defaults.yaml` `simulation.historical_seasons`)
- Recency weights: `{2022: 0.2, 2023: 0.3, 2024: 0.5}` (more recent = higher weight)
- Backtester: `range(test_season - num_training_seasons, test_season)` with no data leakage
## Data Stack (General)
- Polars 1.39.3 exclusively (no pandas anywhere in codebase)
- LazyFrame evaluation not used - eager mode throughout
- `pl.read_parquet()` / `df.write_parquet()` for all caching
- NumPy 2.4.4 for all simulation arrays
- Play outcome distributions stored as `np.ndarray` (empirical, non-parametric)
- `numpy.random.Generator` for all random sampling (seeded via `np.random.default_rng()`)
- Parquet: Primary cache/storage format for nflverse data and processed PFF data
- JSON: PFF raw API responses, weather cache, scraper progress state, A/B test ledgers
- YAML: Configuration files
- **nflverse** (via nflreadpy): Play-by-play, weekly rosters, schedules, player stats, draft picks. Public data, no auth. See detailed section above.
- **PFF** (via httpx): 21 game-level facets for NFL (2018-2025) and NCAA (2022-2025). Premium subscription required.
- **Open-Meteo** (via httpx): Hourly weather data (historical archive + forecast). Free, no API key.
## Configuration
- `config/defaults.yaml` - Master configuration (simulation params, scoring presets, PFF engine configs, weather configs)
- `config/season.example.yaml` / `config/season.2025.yaml` - Per-season override configs (player/team overrides)
- `config/custom_scoring.example.yaml` - Custom scoring with `inherit` + `overrides` pattern
- `config/loader.py`: `load_defaults()` reads `defaults.yaml`, `resolve_scoring()` handles `_inherit` chains
- Scoring presets: `ppr` (base) -> `half_ppr` (inherits ppr, reception=0.5) -> `standard` (inherits ppr, reception=0)
- PFF config: `data/pff/config.py`: `load_pff_config()` extracts PFF section into typed dataclasses
- Weather config: `data/weather/config.py`: `load_weather_config()` extracts weather section
- `.env` file exists at `~/.fantasy-sim/pff/.env` (PFF cookie auth - never read this file)
- No other env vars required for core functionality
- nflverse data is public (no auth needed)
- Open-Meteo is free (no auth needed)
## Build & Deploy
- `src/fantasy_sim/` layout (src-based)
- Entry point: `fantasy-sim` CLI via `[project.scripts]` in `pyproject.toml`
- Editable install: `uv pip install -e ".[dev]"`
- Local CLI tool only - not deployed to any server
- No Docker, no cloud infrastructure
- Runs on developer machine with `uv run fantasy-sim`
- GitHub Actions (`.github/workflows/ci.yml`)
- Triggers: push to main, PRs to main
- Matrix: Python 3.12, 3.13, 3.14
- Uses `astral-sh/setup-uv@v4` with lockfile-based caching
- Two jobs:
- Concurrency: cancel-in-progress per workflow+ref
## Platform Requirements
- Python 3.12+ (3.14 recommended)
- `uv` package manager
- Network access for initial nflverse data download
- PFF premium subscription for PFF data (optional but recommended)
- ~8GB disk space for full PFF data cache
- Same as development (local CLI tool)
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

## Naming Patterns
- All source files use `snake_case.py` (e.g., `play_resolver.py`, `game_context.py`, `tier_engine.py`)
- Test files mirror source with `test_` prefix: `test_play_resolver.py`, `test_game_context.py`
- Subpackage `__init__.py` files are present but typically empty or with minimal exports
- Use `snake_case` for all functions: `resolve_play()`, `build_player_models()`, `compute_weather_factors()`
- Private/internal functions prefixed with `_`: `_resolve_pass()`, `_clamp_yards()`, `_blend_float()`
- Builder functions use `build_*` prefix: `build_game()`, `build_player_projections()`, `build_team_roster()`
- Computation functions use `compute_*` prefix: `compute_factor()`, `compute_reliability()`, `compute_weather_factors()`
- Factory helpers in tests use `make_*` or `_make_*`: `make_state()`, `make_roster()`, `_make_pool_entry()`
- `snake_case` throughout: `catch_rate`, `target_share`, `yard_line`, `score_differential`
- Constants use `UPPER_SNAKE_CASE`: `MIN_BUCKET_PLAYS = 10`, `INT_RETURN_TD_RATE = 0.20`, `MAX_PLAYS = 400`
- RNG variables named `rng` (numpy Generator): `rng = np.random.default_rng(42)`
- Abbreviations preserved from NFL domain: `rz` (red zone), `pbp` (play-by-play), `dst` (defense/special teams), `fg` (field goal), `xp` (extra point), `td` (touchdown), `int` (interception)
- `PascalCase` for all classes: `GameStateBucket`, `TeamDistributions`, `PlayerBoxScore`
- Engine classes use `*Engine` suffix: `TierEngine`, `MatchupEngine`, `CoverageEngine`, `WeatherEngine`, `ScoringEngine`
- Builder classes use `*Builder` suffix: `GameContextBuilder`
- Config dataclasses use `*Config` suffix: `MatchupConfig`, `WeatherConfig`, `TierConfig`
- Model dataclasses use descriptive names: `PlayerModel`, `PlayerUsage`, `PlayerOutcomes`, `TeamRoster`
- Context/result types: `MatchupContext`, `WeatherContext`, `BacktestResult`, `GameResult`
- No enum usage; string literals used instead (e.g., `"pass" | "run"`, `"home" | "away"`)
- Positions as string constants: `"QB"`, `"RB"`, `"WR"`, `"TE"`
## Code Style
- No explicit formatter configured (no ruff, black, prettier, flake8 config files)
- Consistent 4-space indentation throughout
- Line length generally kept under ~120 characters but no hard enforcement
- Trailing commas used in multi-line collections and function calls
- Single quotes for short strings, double quotes for docstrings (mixed usage)
- No linter configuration detected in `pyproject.toml` or standalone config files
- Code quality maintained through TDD workflow and code review rather than automated linting
- Type hints on all function signatures (enforced by project convention):
- Uses Python 3.12+ union syntax: `Path | None`, `dict[str, float] | None`, `np.ndarray | None`
- `from __future__ import annotations` used in some files for forward references
- `TYPE_CHECKING` guard for circular import prevention:
- Module-level docstrings on all files: `"""PFF data loader and player ID crosswalk builder."""`
- Class docstrings are brief single-line: `"""All distributions needed to simulate one team."""`
- Function docstrings use Google-style with Args/Returns when non-trivial:
- Inline comments explain NFL domain logic and calibration constants:
## Import Organization
- Explicit named imports preferred over module imports:
- Multi-line imports use parenthesized grouping with trailing commas
- No path aliases configured (no `[tool.mypy]` paths or import aliases)
- Scripts use `sys.path.insert(0, ...)` to add `src/` to path:
## Data Patterns
- All DataFrame operations use polars: `pl.DataFrame`, `pl.col()`, `.filter()`, `.group_by()`, `.join()`
- Polars used for data loading, PBP processing, PFF data, roster management
- Parquet for caching: `df.write_parquet(path)`, `pl.read_parquet(path)`
- `np.random.Generator` for all RNG (not legacy `RandomState` except in test fixtures)
- Empirical distributions stored as `np.ndarray` and sampled with `rng.choice(arr)`
- No parametric distributions; all sampling is non-parametric from historical data arrays
- `@dataclass` for mutable state: `GameState`, `PlayerBoxScore`, `TeamBoxScore`
- `@dataclass(frozen=True)` for dict keys: `GameStateBucket` (hashable for probability lookup)
- `field(default_factory=...)` for mutable defaults:
- Play outcomes stored as numpy arrays of historical yard values
- Sampled directly: `int(rng.choice(arr))` -- non-parametric
- Minimum bucket sizes enforced: `MIN_BUCKET_PLAYS = 10`, `MIN_PLAYER_PLAYS = 5`
- Fallback to team/league defaults when bucket is too small
## Architecture Patterns
- Each "engine" is a class with `__init__(config, loader)` and a `compute()` method
- Engines are stateless computation units with internal caching
- Examples: `TierEngine`, `MatchupEngine`, `CoverageEngine`, `WeatherEngine`, `KickerEngine`, `DstBaselineEngine`
- `compute()` returns a context/result object (e.g., `MatchupContext`, `WeatherContext`)
- `GameContextBuilder` orchestrates all engines in a defined order
- `build_game()` is the main entry point, returning `(home_dists, away_dists, home_roster, away_roster)`
- Pipeline ordering: base model -> matchup -> team context + tier blend -> normalize -> user overrides -> normalize -> weather
- Factors are multiplicative, centered on 1.0
- Clamped to configurable range (typically `[0.80, 1.20]`)
- Blends observed data toward league-average prior based on sample size
- Pattern: `adjusted = (n * observed + prior_strength * prior) / (n + prior_strength)`
- Same-season data filtered to `week < max_week` (no future leak)
- When team has < `min_games` (default 4), blends with previous season via linear ramp
- Prevents noisy adjustments in weeks 1-3
- Layer 1: Pipeline output keyed by training_seasons
- Layer 2: PBP stats keyed by training_seasons
- Layer 3: Player models keyed by (training_seasons, target_season, week)
- Caching separates expensive PBP aggregation from cheap per-week roster assembly
## Configuration Patterns
- `config/defaults.yaml` defines simulation params, scoring presets, PFF config, weather config
- Scoring uses `_inherit` chains: `half_ppr._inherit: ppr` with override fields
- `resolve_scoring()` follows `_inherit` recursively with circular reference detection
- Click-based CLI with `--pff/--no-pff`, `--weather/--no-weather`, `--scoring`, `--sims`
- Season config YAML (`--config`) provides `season:`, `weeks:`, `scoring_format:` defaults
- CLI flags take precedence over config file; `scoring_format:` always overrides CLI `--scoring`
- `--config-override '{"talent": {"prior_strength": 30}}'` on validation scripts
- Supports keys: `tier_engine`, `talent`, `matchup`, `team_context`, `ncaa_rookie`, `weather`
- Merges into default config for sweep testing without modifying `defaults.yaml`
- All adjustment engines expose sensitivity floats in their config dataclasses
- Pattern: `{stat}_sensitivity: float = {default}` (e.g., `pass_defense_sensitivity=0.08`)
- Allows A/B sweep tuning via config-override
## Error Handling
- `ConfigError(Exception)` in `config/loader.py` for YAML parsing/validation errors
- `AmbiguousMatchError(KeyError)` in `overrides/resolver.py` for fuzzy match ambiguity
- `ValueError` for invalid arguments: `raise ValueError(f"n_sims must be positive, got {n_sims}")`
- `KeyError` for missing players/items: `raise KeyError(f"No exact match for '{query}'")`
- `click.BadParameter` for CLI validation: `raise click.BadParameter(f"Invalid week range: '{weeks_str}'")`
- `SystemExit(1)` for CLI-level fatal errors (caught at top of command handlers)
- League-average distributions when team data is insufficient (`MIN_BUCKET_PLAYS = 10`)
- Previous-season blend when current-season games < `min_games` (4)
- Default catch rate modifier (`RZ_CATCH_RATE_MODIFIER = 0.92`) when player has < `MIN_RZ_TARGETS`
- Uniform weights in `select_receiver()`/`select_rusher()` when all share weights are zero
- `getattr` fallback for backward compatibility with penalty modeling
## Logging
- Module-level logger: `logger = logging.getLogger(__name__)`
- Used in data layer (`pff/loader.py`, `weather/provider.py`, `pff/tier_engine.py`)
- Not used in engine layer (pure computation, no side effects)
- Validation scripts use `print()` for user-facing output
## Comments
- NFL domain constants always commented with real-world context:
- Section separators use `# ---------- Section Name ----------` in test files
- Inline comments explain "why" not "what": `# Coin toss`, `# Fumble cancels TD`
## Function Design
- Functions typically 10-50 lines; largest are engine `compute()` methods (~100 lines)
- Complex logic broken into private helpers: `_resolve_pass()`, `_resolve_run()`, `_red_zone_td_gate()`
- Required parameters first, then optional with defaults
- `rng: np.random.Generator` always passed explicitly (never global state)
- Config objects passed as dataclasses, not raw dicts (except scoring config which is `dict[str, float]`)
- Optional roster params enable progressive feature gates: `home_roster: TeamRoster | None = None`
- Single return type (no overloaded returns)
- Dataclasses for complex returns: `PlayResult`, `GameResult`, `BacktestResult`, `MatchupContext`
- Tuples for simple multi-returns: `tuple[str, int] | None` for penalty checks
## Module Design
- Explicit imports at point of use; no `__all__` definitions
- `__init__.py` files are empty (no re-exports)
- Each module has a clear single responsibility
- Not used. All imports reference the specific module file directly:
- Module-level constants colocated with the code that uses them:
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

## Pattern Overview
- Play-by-play simulation (not statistical regression) -- each play is resolved individually with game-state-aware probability sampling
- Empirical (non-parametric) distributions -- yards gained are stored as numpy arrays of historical values and sampled directly, avoiding parametric distribution fitting
- Layered adjustment pipeline -- base PBP model -> matchup -> tier engine + team context -> coverage -> DST baseline -> kicker -> weather -> user overrides (each layer applies multiplicative factors)
- Three-layer caching strategy for expensive computations (pipeline output, PBP stats, player models)
- Mutable game state with immutable distribution inputs
## Layers
- Purpose: Fetch, cache, and preprocess NFL data into simulation-ready distributions
- Location: `src/fantasy_sim/data/`
- Contains: Data loading, PBP preprocessing, player model building, PFF intelligence, weather engine
- Depends on: nflreadpy, nflverse PBP/roster data, PFF processed parquet, Open-Meteo API
- Used by: CLI commands, validation/backtester
- Purpose: Shared data types (dataclasses) used across all layers
- Location: `src/fantasy_sim/models/`
- Contains: GameStateBucket, distribution types, player/roster models
- Depends on: numpy (for array fields)
- Used by: Everything -- engine, data, scoring, overrides
- Purpose: Play-by-play game simulation and Monte Carlo runner
- Location: `src/fantasy_sim/engine/`
- Contains: Game state machine, play calling, play resolution, player selection, clock management
- Depends on: Models layer, numpy RNG
- Used by: Monte Carlo runner, CLI, backtester
- Purpose: Config-driven fantasy point calculation and projection aggregation
- Location: `src/fantasy_sim/scoring/`
- Contains: Point scoring engine, projection builder (mean/floor/ceiling/stddev)
- Depends on: Engine types (PlayerBoxScore, TeamBoxScore, GameResult)
- Used by: CLI, backtester, output
- Purpose: User-specified modifications to player usage/outcomes and team distributions
- Location: `src/fantasy_sim/overrides/`
- Contains: Override engine, YAML/CLI parser, fuzzy name resolver
- Depends on: Models (PlayerModel, TeamRoster), engine types (TeamDistributions)
- Used by: CLI, game_context
- Purpose: YAML configuration loading with inheritance
- Location: `src/fantasy_sim/config/`, `config/`
- Contains: Config loader, scoring presets with `_inherit` chains
- Depends on: PyYAML
- Used by: CLI, PFF config, weather config
- Purpose: Backtesting against historical actuals, accuracy metrics
- Location: `src/fantasy_sim/validation/`
- Contains: Backtester, Spearman/MAE/boom-bust metrics, report formatting
- Depends on: Data layer (GameContextBuilder, actuals), engine (Monte Carlo), scoring
- Used by: CLI `backtest` command, A/B validation scripts
- Purpose: Terminal display and file export
- Location: `src/fantasy_sim/output/`
- Contains: Rich terminal tables by position, CSV/JSON export
- Depends on: Rich library
- Used by: CLI
## Data Flow
### Primary Simulation Pipeline
```
|                                                       |
|  1. MatchupEngine.compute()                          |
|     away D -> home offense factors, home D -> away   |
|     _apply_matchup() mutates dists + roster          |
|                                                       |
|  2. TierEngine.apply_tiers()                         |
|     + TeamContextEngine.compute() (if enabled)       |
|     Blends PFF grade tiers with PBP player data      |
|     _normalize_roster_shares() after                 |
|                                                       |
|  3. CoverageEngine.compute()                         |
|     Per-WR modifiers from CB matchup analysis        |
|     _apply_coverage() mutates roster                 |
|                                                       |
|  4. DstBaselineEngine.compute()                      |
|     Fumble rate factor + defensive TD rates           |
|     Sets DefensiveTdRates on TeamDistributions       |
|                                                       |
|  5. KickerEngine.compute()                           |
|     Per-kicker FG accuracy replaces team KickingModel|
|                                                       |
|  6. WeatherEngine.get_context()                      |
|     _apply_weather() mutates dists + roster          |
|                                                       |
```
### nflverse Data Flow (Detail)
| Function | nflreadpy Call | Data | Used By |
|---|---|---|---|
| `DataLoader.load_pbp()` | `nflreadpy.load_pbp(seasons)` | Play-by-play data (every NFL play) | Preprocessor, player_builder |
| `DataLoader.load_rosters()` | `nflreadpy.load_rosters_weekly(seasons)` | Weekly roster snapshots | Player model assembly, PFF crosswalk |
| `DataLoader.load_player_stats()` | `nflreadpy.load_player_stats(seasons)` | Per-player weekly stat summaries | Backtester (actuals comparison) |
| `DataLoader.load_schedules()` | `nflreadpy.load_schedules(seasons)` | Game schedule with dates/times | Backtester, WeatherEngine |
| `DataLoader.load_snap_counts()` | `nflreadpy.load_snap_counts(seasons)` | Per-player snap count data | Available but not heavily used |
| `DataLoader.load_depth_charts()` | `nflreadpy.load_depth_charts(seasons)` | Team depth charts | Available but not heavily used |
| `DataLoader.load_draft_picks()` | `nflreadpy.load_draft_picks()` | Historical draft pick data | Rookie model tier assignment |
- `play_type` (filter: "pass", "run", "field_goal", "extra_point", "kickoff")
- `posteam` (possessing team)
- `down`, `ydstogo`, `score_differential`, `qtr`, `yardline_100` (game state bucketing)
- `yards_gained` (empirical distributions)
- `interception`, `fumble_lost`, `sack` (turnover rates)
- `kick_distance`, `field_goal_result` (kicking model)
- `extra_point_result` (XP rate)
- `touchback`, `return_yards` (drive start model)
- `penalty`, `penalty_type`, `penalty_yards` (penalty rates)
- `season` (for season weighting)
- `receiver_player_id`, `rusher_player_id`, `passer_player_id` (player attribution)
- `complete_pass` (catch rate, yards on completions)
- `yards_gained` (per-player yards distributions)
- `air_yards` (air yards share)
- `yardline_100` (red zone detection, <= 20)
- `game_id` (games played counting)
- `qb_scramble` (scramble vs designed run separation)
- `fumble_lost` (QB pre-throw fumble rate)
- `player_id` (gsis_id, renamed), `player_name` (full_name, renamed)
- `team`, `position`, `status` (filter: "ACT")
- `season`, `week` (latest snapshot, per-week filtering)
- `pff_id` (PFF crosswalk bridge)
- `college_name`, `rookie_year` (NCAA rookie crosswalk)
### nflverse Caching Architecture
```
```
### PFF Intelligence Pipeline
```
```
### Weather Pipeline
```
```
## Core Subsystems
### Data Layer (`src/fantasy_sim/data/`)
- Wraps nflreadpy with parquet caching at `~/.fantasy-sim/cache/`
- Cache key = `{dataset}_{sorted_seasons}.parquet`
- Renames nflverse columns: `gsis_id` -> `player_id`, `full_name` -> `player_name`
- Orchestrates `DataLoader` + `Preprocessor`
- Single `build()` method returns dict with all distribution types
- Accepts optional `season_weights` for recency bias
- `compute_play_calling()` -> per-team P(run|state), P(pass|state) via `GameStateBucket`
- `compute_play_outcomes()` -> empirical yards distributions keyed by (play_type, bucket)
- `compute_turnover_rates()` -> per-team INT/fumble/sack rates
- `compute_kicking_model()` -> FG make rate by distance bucket, XP rate
- `compute_drive_start_model()` -> touchback rate + return yardline distribution
- `compute_penalty_rates()` -> per-team penalty frequency and type distribution
- Uses `MIN_BUCKET_PLAYS = 10` threshold: buckets with fewer plays fall back to team/league defaults
- Season weighting via row replication (max_weight -> 10 copies, others proportional)
- `_aggregate_pbp_stats()` -> extracts per-player receiving/rushing/QB stats from PBP (cached)
- `_assemble_models()` -> merges PBP stats with current roster to produce `PlayerModel` objects
- `build_team_roster()` -> deepcopies players from cache, normalizes shares to sum to 1.0
- `blend_with_archetype()` -> blends sparse player data with positional archetypes
- Separates stats (historical PBP across training seasons) from team assignment (current roster)
- Central orchestrator for building simulation inputs
- `build_game()` returns `(home_dists, away_dists, home_roster, away_roster)`
- Initializes all PFF engines and weather engine in `__init__()` via lazy imports
- Applies PFF + weather adjustments in fixed order (matchup -> tier -> coverage -> DST -> kicker -> weather)
- Contains `pre_resolve_overrides()` and `apply_overrides()` for user override application
### PFF Intelligence (`src/fantasy_sim/data/pff/`)
- Assigns players to 5 PFF grade-based tiers (percentile cutoffs: 0.85, 0.65, 0.40, 0.20)
- Builds per-(position, tier) pool entries with full stat distributions from historical player-seasons
- Blends tier distributions with PBP data weighted by reliability score (floor=0.20, cap=0.80)
- Reliability considers: games played (max 32), team change penalty (0.5x), grade variance
- WR archetypes: 3 depth-of-target sub-pools (slot/possession/deep) within each tier
- NCAA rookie assignment: maps college PFF grades to NFL tiers via `pff_id` bridge, draft capital modulates blend confidence
- Converts PFF defensive/OL stats into per-game z-score factors centered on 1.0
- 7 factors: catch_rate, pass_yards, sack_rate, int_rate, rush_yards, ol_pass_block, ol_run_block
- Same-season rolling window: `week < max_week` filter prevents future data leakage
- Early-season blend: linear ramp with previous season when team has < 4 games
- Medium sensitivities (0.06-0.075), clamped to [0.90, 1.10]
- Season-level team environment factors (not per-game like matchup)
- Three factors: pass_rate (PBP), ol_run_block (PFF), qb_quality (PFF)
- Snap-weighted aggregation for OL and QB data
- Applied to TierDistributions BEFORE player blending
- Per-WR modifiers from CB matchup analysis
- Alignment-based mapping: RWR->LCB, LWR->RCB, slot->SCB
- Outcome-based stats (catch rate allowed, YPR) with grade-based stabilizer for low-sample CBs
- Z-score relative to all CBs at the same alignment across the league
- Tight clamp [0.97, 1.03] -- small but meaningful per-WR adjustments
- WR-only (TEs excluded)
- Per-kicker FG accuracy from PFF `field_goal_summary`
- Bayesian shrinkage toward league average (prior_strength=20 pseudo-attempts)
- Replaces team-level `KickingModel` with per-kicker rates by distance bucket
- Fumble rate factor via z-score of team forced-fumble rate per defensive snap
- Team-specific defensive TD rates (pick-six rate, fumble return TD rate) via Bayesian shrinkage
- Complements MatchupEngine (handles DST scoring components specifically)
- Reads `{facet}_{season}.parquet` from `~/.fantasy-sim/pff/processed/nfl/`
- Normalizes 4 non-standard PFF team abbreviations (ARZ/BLT/CLV/HST)
- Maps PFF positions to fantasy positions (LWR/RWR/SLWR->WR, HB->RB, etc.)
- Two-layer crosswalk: pff_id direct match, then name+team fallback
- NCAA loader (`load_ncaa_facet()`) reads from `~/.fantasy-sim/pff/processed/ncaa/`
### Weather Engine (`src/fantasy_sim/data/weather/`)
- Orchestrates schedule lookup -> stadium resolution -> API fetch -> factor computation
- Dome/retractable stadiums short-circuit to neutral `WeatherContext`
- Threshold + linear scaling (not z-scores -- weather has absolute physical thresholds)
- Wind, temperature, precipitation combine multiplicatively, clamped to [0.80, 1.20]
- Fetches from Open-Meteo (free, no API key needed)
- Historical archive API for past dates, forecast API for future dates
- 3-hour game window: averages temperature/wind, sums precipitation
- JSON cache at `~/.fantasy-sim/weather/`, keyed by `{lat}_{lon}_{date}.json`
- Forecast TTL: 6 hours; stale forecast detection (refetches when game is now in the past)
- Maps all 32 NFL teams to lat/lon coordinates and venue type
- Venue types: outdoor, dome (DET, LA, LAC, LV, MIN, NO), retractable (ARI, ATL, DAL, HOU, IND)
### Simulation Engine (`src/fantasy_sim/engine/`)
- Main game loop: max 400 plays, 4 quarters + OT
- Each play: 4th-down decision -> play selection -> play resolution -> stat updates -> clock
- Tracks both team-level (`TeamBoxScore`) and player-level (`PlayerBoxScore`) stats
- Defensive TDs: 20% of INTs returned for TD, 10% of fumble recoveries (configurable via `DefensiveTdRates`)
- OT rules: 10-minute period, walk-off scoring
- `select_play_type()` looks up `GameStateBucket` in `PlayCallingDist`
- `fourth_down_decision()` uses distance-based heuristics + FG probability
- `_resolve_pass()`: scramble check -> sack check -> INT check -> QB fumble check -> receiver selection -> catch rate -> yards -> TD gate -> fumble
- `_resolve_run()`: rusher selection -> player yards dist -> TD gate -> fumble
- Red zone TD gate: per-play probability check calibrated to ~55% drive-level TD rate
- `CATCH_YARDS_BOOST = 1` compensates for field-position clamping bias
- Home-field advantage: 50% chance of +1 yard per play
- Pace factor scales clock runoff (more/fewer plays per game)
- Filters by `weeks_missed` for per-week availability
- `select_passer()` -> highest snap_share QB
- `select_receiver()` -> weighted by target_share (red_zone_target_share in RZ)
- `select_rusher()` -> weighted by carry_share, MIN_QB_CARRY_SHARE=0.10 excludes pocket passers
- Sequential loop of `simulate_game()` calls (no parallelism)
- Single `numpy.random.Generator` with configurable seed for reproducibility
- Returns `SimulationSummary` with all `GameResult` objects
### Scoring (`src/fantasy_sim/scoring/`)
- `score_player()`: config-driven, position-specific reception keys (`reception_wr`, `reception_te`), yardage bonuses
- `score_dst()`: 7 points-allowed brackets, sacks, INTs, fumble recoveries, defensive TDs, safeties
- `score_kicker()`: FG by distance bucket (0-39, 40-49, 50+), XP, FG misses
- `build_player_projections()` -> mean stats + fpts across all sims, ranked
- `build_detailed_projections()` -> adds floor (p10), ceiling (p90), stddev
- `build_dst_projections()` / `build_kicker_projections()` for DST and kickers
- Players treated as 0 in sims they don't appear in (no inflation from sparse appearances)
### Validation (`src/fantasy_sim/validation/`)
- Hold-out validation: trains on N prior seasons, tests on target season
- Iterates every game in every week, builds context + runs sims per game
- Deterministic seeds via `zlib.crc32(game_id)`
- Targets: rank_corr > 0.80, weekly_mae < 6.0, season_mae < 25, calibration < 0.10
- Spearman rank correlation, MAE, boom/bust calibration
### Overrides (`src/fantasy_sim/overrides/`)
- Player overrides: target_share, carry_share, catch_rate, fumble_rate, games_missed, etc.
- Share overrides trigger proportional redistribution to teammates
- Team overrides: pass_rate, int_rate, fumble_rate, sack_rate, pace_plays_per_game
- Resolution chain: exact ID -> exact name -> underscore conversion -> fuzzy match (thefuzz, score >= 70)
- Ambiguity detection: raises `AmbiguousMatchError` when 2+ players match within 5 points
### Config (`src/fantasy_sim/config/`, `config/`)
- YAML loading with `_inherit` chain resolution for scoring presets
- Custom scoring via `inherit` + `overrides` format
- `load_defaults()` reads `config/defaults.yaml`
- Scoring presets: PPR (base), half_ppr (_inherit: ppr), standard (_inherit: ppr)
- Position minimums (min_snaps, min_carries, min_targets)
- PFF config (all 6 engines + tier parameters + archetypes + NCAA rookie config)
- Weather config (wind/temp/precipitation sensitivities and thresholds)
- Simulation defaults (num_sims, training_years, recency_weights)
### CLI (`src/fantasy_sim/cli.py`)
- Click-based CLI with commands: `demo`, `week`, `season`, `game`, `player`, `backtest`
- Entry point: `fantasy-sim` (registered in pyproject.toml)
- Common options: `--sims`, `--scoring`, `--scoring-config`, `--detail`, `--format`, `--output`, `--override`, `--config`, `--pff/--no-pff`, `--weather/--no-weather`
- Rich progress bars for simulation loops
- Config resolution chain: defaults.yaml -> season.yaml -> --scoring-config -> CLI flags
## Key Design Decisions
- Matchup adjustments are applied to base distributions first
- Tier engine blends PFF talent data with already-matchup-adjusted PBP baselines
- Coverage is last PFF layer (fine-grained per-WR tweaks on top of broader adjustments)
- Weather is the absolute last game-condition modifier
- User overrides always take final precedence
## Concurrency & Performance
- **nflverse cache** (`~/.fantasy-sim/cache/`): Parquet files, 13-50 MB each for PBP. No TTL. Shared across all CLI invocations.
- **PFF cache** (`~/.fantasy-sim/pff/processed/`): Parquet files processed from raw JSON. ~168 NFL files + ~84 NCAA files.
- **Weather cache** (`~/.fantasy-sim/weather/`): JSON files, one per (location, date). Historical immutable, forecast TTL 6 hours.
- **In-memory caches**: GameContextBuilder caches pipeline output, PBP stats, and player models. PffLoader caches loaded DataFrames. MatchupEngine, CoverageEngine, TeamContextEngine cache loaded facets by season key.
- First run for a season: ~30-60 seconds (nflverse network fetch + parquet write)
- Subsequent runs: ~2-5 seconds for pipeline + player model building (parquet reads)
- Simulation speed: ~100-200 games/second (depends on play count per game)
- Memory: ~200-400 MB for loaded PBP data + distributions
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, or `.github/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->

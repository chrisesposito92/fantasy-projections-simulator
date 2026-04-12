# AGENTS.md

## Project Overview

NFL fantasy football projections simulator. Simulates games play-by-play using historical nflverse data, runs Monte Carlo simulations, and produces fantasy point projections with full stat distributions.

## Tech Stack

- Python 3.12+ (currently running 3.14), uv for package management
- polars for DataFrames (NOT pandas), numpy for numerical simulation
- nflreadpy for NFL data from nflverse, httpx for PFF/weather APIs
- pytest (with pytest-xdist, hypothesis), YAML for configuration
- Click CLI, Rich terminal output

## Commands

```bash
# Tests
uv run pytest tests/ -v                    # all tests
uv run pytest tests/ -v -m statistical     # statistical validation only

# Validation scripts
uv run python scripts/validate_sim.py              # 5000-game sim validation
uv run python scripts/validate_players.py          # player validation (offline)
uv run python scripts/validate_data.py             # data validation (network)
uv run python scripts/validate.py --sims 50 --label "run-name"
uv run python scripts/validate.py --set usage.ngs.enabled=true --sims 50 --label "test-ngs"
uv run python scripts/validate.py --baseline defaults --set usage.ngs.enabled=true --sims 50
uv run python scripts/validate.py --show-ledger
# Legacy (deprecated — use scripts/validate.py):
uv run python scripts/validate_pff_signal.py --mode all --sims 50
uv run python scripts/validate_weekly_signal.py --mode all --sims 50

# PFF scraper (premium subscription required, see docs/pff-setup.md)
uv run python scripts/scrape_pff.py --season 2024
uv run python scripts/scrape_pff.py --league ncaa --season 2024

# PFF tuning
uv run python scripts/fit_talent_coefficients.py [--apply]
uv run python scripts/sweep_talent_params.py --sims 30 [--apply]

# CLI
uv run fantasy-sim demo --sims 100 [--scoring half_ppr] [--detail] [--format csv --output out.csv]
uv run fantasy-sim week 1 --season 2024 --sims 100
uv run fantasy-sim season --season 2024 --sims 50 [--by-week]
uv run fantasy-sim game KC BUF --week 5 --sims 100
uv run fantasy-sim player "nico_collins" --week 5 --sims 100
uv run fantasy-sim backtest --season 2024 --sims 50

# Common flags: --sims, --scoring (ppr/half_ppr/standard), --scoring-config, --detail,
#   --format (table/csv/json), --output, --override "name.field=value", --config,
#   --pff/--no-pff, --weather/--no-weather
```

## Architecture

Pipeline: Data → Models → Engine → Scoring → Output

1. **Data Layer** (`data/`) — Fetches nflverse data, caches as parquet, preprocesses into probability distributions, builds per-player models. PFF subpackage (`data/pff/`) provides 6 intelligence engines. Weather subpackage (`data/weather/`) adds game-day adjustments.
2. **Models** (`models/`) — Shared dataclasses: GameStateBucket, distributions, player/roster models
3. **Engine** (`engine/`) — Play-by-play game simulation with player-level tracking and Monte Carlo runner
4. **Config** (`config/`) — YAML config with `_inherit` scoring preset chains (PPR → half_ppr → standard)
5. **Scoring** (`scoring/`) — Fantasy point calculation for players/DST/kickers; projection aggregation
6. **Output** (`output/`) — Rich terminal tables, CSV/JSON export
7. **Validation** (`validation/`) — A/B backtesting with config resolution (`config.py`), bare baseline caching (`cache.py`), unified ledger (`ledger.py`), Spearman/MAE/boom-bust metrics, hold-out backtesting
8. **Overrides** (`overrides/`) — Player/team override engine with share redistribution, fuzzy name matching
9. **CLI** (`cli.py`) — Click-based with `demo`, `week`, `season`, `game`, `player`, `backtest` commands

### Adjustment Pipeline Order

`GameContextBuilder.build_game()`:

base PBP model → vegas (pace + pass rate) → availability → normalize → usage → normalize → props → normalize → matchup → team context + tier blend → normalize → coverage → DST baseline → kicker → TD tendency → weather

Post-sim projection order:

role_trend → ensemble.ff_opportunity

### Three-Layer Cache

1. Pipeline output (keyed by training_seasons)
2. PBP stats (keyed by training_seasons)
3. Player models (keyed by training_seasons + target_season + week + props_enabled)

Player models separate stats (historical PBP, cached/expensive) from team assignment (current roster, cheap/per-week).

## Key Domain Patterns

- **yardline_100 convention**: 99=own 1, 75=own 25 (touchback), 50=midfield, 20=red zone, 1=goal line. TD when `yard_line - yards <= 0`. Safety when `yard_line - yards >= 100`.
- **Empirical distributions**: Play outcomes stored as numpy arrays of historical values, sampled with `rng.choice(arr)`. Non-parametric. `MIN_BUCKET_PLAYS = 10` fallback to team/league defaults.
- **GameStateBucket**: Frozen dataclass (down, distance, score_diff, quarter, yard_zone) used as dict keys for probability lookups.
- **Red Zone TD Gate**: Per-play probability check in `play_resolver.py` calibrated to ~55% drive-level TD rate. `PASS_TD_GATE` (0.55-0.15), `RUN_TD_GATE` (0.35-0.08).
- **Catch Yards Boost**: `CATCH_YARDS_BOOST = 1` adds 1 yard per catch **outside red zone only** to compensate for field-position clamping bias.
- **RZ Catch Rate**: `RZ_CATCH_RATE_MODIFIER = 0.92` (real NFL RZ catch rates ~92% of overall). Per-player override when ≥10 RZ targets.
- **QB Designed Run Separation**: `MIN_QB_CARRY_SHARE = 0.10` excludes pocket passers. QB carry_share computed from designed runs only (scrambles subtracted).
- **Sack-Fumble Attribution**: Sack-fumbles charge to QB's `fumbles_lost` (fantasy convention).
- **Share Normalization**: `build_team_roster()` deepcopies players and normalizes carry/target shares to sum to 1.0 among eligible players.
- **Play resolution**: Scramble → sack → INT → QB fumble → receiver selection → catch rate → yards → TD gate → fumble. Home-field: 50% chance +1 yard.
- **Scoring**: `score_player()` uses position-specific reception keys (`reception_wr`, `reception_te`). `score_dst()` has 7 points-allowed brackets. `score_kicker()` has FG distance buckets.
- **Overrides**: Share overrides trigger proportional redistribution. Resolution: exact ID → exact name → underscore → fuzzy match (score ≥ 70). `AmbiguousMatchError` when 2+ match within 5 points.
- **Config chain**: defaults.yaml → season.yaml → --scoring-config → CLI flags. `scoring_format:` in season config always overrides CLI `--scoring`.

## PFF Intelligence Layer

Six active layers in `data/pff/`, configured in `defaults.yaml` under `pff:`. CLI `--pff/--no-pff` flag.

| Engine | What it does | Key config |
|--------|-------------|------------|
| **TierEngine** | 5 grade-based tiers, blends tier distributions with PBP data by reliability (floor=0.20, cap=0.80). WR archetypes (slot/possession/deep). NCAA rookies via `pff_id` bridge. QBs only blend fumble_rate. | `pff.tier_engine` |
| **TeamContextEngine** | Season-level team environment: pass rate → WR/TE target_share, OL run block → RB rush yards, QB quality → WR/TE catch_rate. Snap-weighted. | `pff.team_context` |
| **MatchupEngine** | Per-game z-score factors from defensive + OL data. 7 factors, medium sensitivities (0.06-0.075). Same-season rolling window, early-season blend. | `pff.matchup` |
| **CoverageEngine** | Per-WR modifiers from CB matchup (alignment-based: RWR→LCB, LWR→RCB, slot→SCB). Catch rate + YPR. WR-only. Clamp [0.97, 1.03]. | `pff.coverage` |
| **KickerEngine** | Per-kicker FG accuracy with Bayesian shrinkage toward league average. | `pff.kicker` |
| **DstBaselineEngine** | Fumble rate factor (z-score) + team-specific defensive TD rates (Bayesian shrinkage). | `pff.dst_baseline` |

- `--config-override` on validation scripts supports: `tier_engine`, `talent`, `matchup`, `team_context`, `ncaa_rookie`, `weather`
- A/B validation with persistent ledger: `scripts/validate_pff_signal.py --show-ledger`
- All engines use same-season rolling window (`week < max_week`) with early-season blend (linear ramp, `min_games=4`)

## Weather Engine

`data/weather/` adds game-day adjustments as the final layer. Open-Meteo API (free, no key). 32-team stadium registry with dome detection. Threshold + linear scaling (not z-scores). Wind/temp/precipitation factors combine multiplicatively, clamped to [0.80, 1.20]. JSON cache with 6-hour forecast TTL. Config in `defaults.yaml` under `weather:`. CLI `--weather/--no-weather`.

## Testing

- Tests mirror src structure: `tests/test_data/`, `tests/test_models/`, etc.
- Fixtures in `tests/conftest.py` provide sample PBP data (20 plays, KC/BUF)
- `unittest.mock.patch` to mock nflreadpy (no network in unit tests)
- Markers: `@pytest.mark.integration`, `@pytest.mark.statistical`
- **1248 tests** across all phases

## Vegas Engine

`data/vegas/` adds market-derived game environment signals. Three sub-engines, configured in `defaults.yaml` under `vegas:`. CLI `--vegas/--no-vegas` and `--props/--no-props` flags.

| Engine | What it does | Key config |
|--------|-------------|------------|
| **VegasEngine (VEG-01)** | ITT-derived `pace_factor` from spread_line/total_line. Higher ITT → more plays via faster clock pace. Z-score with `compute_factor()` from matchup.py. | `vegas.itt` |
| **VegasEngine (VEG-02)** | Spread-derived `pass_rate_factor` modifying `PlayCallingDist.default` only. Favorites run more, underdogs pass more. Inverted z-score. | `vegas.spread` |
| **PlayerPropsEngine (VEG-03)** | Player-level Bayesian blend from The Odds API props (receiving yards/receptions → target_share, rushing yards → carry_share, passing yards → proportional dist shift). Levenshtein name crosswalk (≥0.85). | `vegas.props` |

- Data: nflverse `load_schedules()` for spread/total (VEG-01/02), The Odds API for player props (VEG-03, requires API key)
- League stats: `ITT_LEAGUE_AVG=21.97`, `ITT_LEAGUE_STD=3.67`, `SPREAD_STD=5.72` (854 games 2022-2024)
- Props cache: parquet at `~/.fantasy-sim/pff/props/` keyed by (season, week)
- A/B modes: `--mode vegas`, `--mode vegas+spread`, `--mode vegas+props`

## Current State

All development phases complete through the Phase 2 accuracy initiative. Key completed features:
- Core simulation engine with play-by-play resolution and Monte Carlo runner
- Player models from PBP data with roster separation (stats vs team assignment)
- Red zone accuracy (TD gates, per-player RZ catch rates, QB fumble check)
- Passing yards calibration (catch yards boost, clock runoff tuning)
- Share normalization fix (carry/target shares sum to 1.0 on current roster)
- PFF scraper (21 facets, NFL 2019-2025 + NCAA 2022-2025)
- PFF intelligence: tier engine, matchup, team context, coverage, kicker, DST baseline
- NCAA rookie tier assignment via pff_id bridge
- WR depth-of-target archetypes (slot/possession/deep)
- Weather engine (wind/temp/precipitation from Open-Meteo)
- Vegas engine: ITT pace scaling (VEG-01), spread-based pass/run conditioning (VEG-02)
- Player props engine: Bayesian blending from The Odds API with name crosswalk (VEG-03)
- Phase 1 promoted: post-sim `ff_opportunity` ensemble for QB/RB/WR/TE
- Phase 2 promoted: `availability.enabled=true` with `availability.injuries.enabled=false`
- Phase 2 kept off: `role_trend.enabled=false`
- Weekly + season A/B validation harnesses with persistent ledgers

## Style

- Use polars, not pandas
- Use numpy for arrays and random sampling
- Dataclasses for data types (frozen when used as dict keys)
- Type hints on all function signatures (Python 3.12+ union syntax: `X | None`)
- Tests follow TDD: test first, then implement
- `rng: np.random.Generator` always passed explicitly (never global state)
- Engine pattern: class with `__init__(config, loader)` + `compute()` → context/result object
- Factors are multiplicative, centered on 1.0, clamped to configurable range
- Bayesian blending: `adjusted = (n * observed + prior_strength * prior) / (n + prior_strength)`

## Data Sources

| Source | Access | Used For |
|--------|--------|----------|
| nflverse (via nflreadpy) | Public, no auth | PBP, rosters, schedules, player stats, draft picks |
| PFF (via httpx) | Premium subscription, cookie auth | 21 game-level facets (NFL + NCAA) |
| Open-Meteo (via httpx) | Free, no API key | Hourly weather (historical + forecast) |
| The Odds API (via httpx) | Paid subscription, API key | NFL player props (receiving, rushing, passing, TD) |

Caches: nflverse parquet at `~/.fantasy-sim/cache/`, PFF parquet at `~/.fantasy-sim/pff/processed/`, weather JSON at `~/.fantasy-sim/weather/`, props parquet at `~/.fantasy-sim/props/`. PFF cookie auth at `~/.fantasy-sim/pff/.env` (never read this file). Props API key at `~/.fantasy-sim/props/.env`.

## Project

**Fantasy Projections Simulator — Accuracy Initiative**

**Core Value:** Projection accuracy that beats current best A/B results (run #44: rank_corr +0.0517) and pushes toward absolute targets (rank_corr > 0.80, weekly_mae < 6.0) — with WR and QB accuracy as highest-priority positions.

### Constraints

- All improvements validated through A/B harness before merging
- PFF premium subscription available; open to free sources; will consider paid if justified
- Must maintain 1,122+ test suite; new features need tests
- Open to any approach (new layers, ML models, structural changes) — whatever moves the metrics

## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.

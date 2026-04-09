# Player-Level TD Tendency Design

## Problem

The red zone TD gate in `play_resolver.py` uses uniform per-play probabilities based only on yard line and play type. No player differentiation: Travis Kelce at the goal line gets the same 55% pass TD gate as a backup TE. TDs are the single biggest source of weekly fantasy variance (~6-12 points per TD in PPR), yet the simulation treats all players identically for TD conversion.

The snap count fix (Phase 3) addressed "who is actually playing." TD tendency addresses the analogous gap for scoring: "who actually scores TDs."

## Approach

Hybrid Bayesian: PFF-observed RZ TD rate as the signal, with position-specific league-average priors for Bayesian shrinkage. Gate-only modification — no changes to RZ opportunity distribution (target_share, carry_share). PBP fallback when PFF data is unavailable.

## Data Layer

### New PFF Fantasy Stats Facets

Two new scraper facets using existing cookie auth, scraped per-week:

| Facet | Endpoint | Covers |
|-------|----------|--------|
| `fantasy_receiving` | `/api/fantasy/stats/receiving?season={s}&weeks={w}&scoring=preset_ppr` | WR, RB, TE, FB |
| `fantasy_passing` | `/api/fantasy/stats/passing?season={s}&weeks={w}&scoring=preset_ppr` | QB |

Scraped one request per week per facet. Cached as parquet at `~/.fantasy-sim/pff/processed/fantasy_receiving/` and `~/.fantasy-sim/pff/processed/fantasy_passing/`.

### Fields Consumed — `fantasy_receiving` (WR/RB/TE)

| Field | Type | Purpose |
|-------|------|---------|
| `rz_rec_targ` | int | RZ receiving opportunities (denominator for receiving factor) |
| `rz_rec_tds` | int | RZ receiving TDs (numerator for receiving factor) |
| `rz_rush_carries` | int | RZ rushing opportunities (denominator for rushing factor) |
| `rz_rush_tds` | int | RZ rushing TDs (numerator for rushing factor) |
| `i5_rush_carries` | int | Inside-5 carries (reserved for future goal-line sub-factor) |
| `i5_rush_tds` | int | Inside-5 TDs (reserved for future goal-line sub-factor) |
| `player_id` | int | PFF player ID — joined via existing crosswalk to gsis_id |
| `position` | str | Position filter |
| `games` | int | Games played (sample size) |

### Fields Consumed — `fantasy_passing` (QB)

| Field | Type | Purpose |
|-------|------|---------|
| `rz_rush_carries` | int | QB RZ rushing opportunities |
| `rz_rush_tds` | int | QB RZ rushing TDs |
| `i5_rush_carries` | int | QB inside-5 carries |
| `i5_rush_tds` | int | QB inside-5 TDs |
| `player_id` | int | PFF player ID |
| `games` | int | Games played |

### Temporal Leakage Guard

At query time, aggregate only weeks strictly less than the target week. Per-week caching makes this a simple filter: load parquet files for weeks 1..target_week-1 and sum the count columns. Same pattern as every other engine in the codebase.

### PBP Fallback

When PFF data is unavailable, fall back to PBP-derived RZ TD rates. Requires adding `rz_receiving_tds` and `rz_rushing_tds` counters to `_aggregate_pbp_stats()` in `player_builder.py`. The PBP data already has `touchdown` + `yardline_100` fields; only the counting logic is missing.

## Factor Computation

Two independent factors per player, matching the gate's existing pass/run split.

### Receiving TD Factor (WR, RB, TE)

```
observed = sum(rz_rec_tds) / sum(rz_rec_targ)       # across weeks < target_week
prior    = positional_avg_rz_receiving_td_rate        # WR ~0.17, TE ~0.15, RB ~0.12

blended  = (n_targets * observed + prior_strength * prior) / (n_targets + prior_strength)
receiving_td_factor = blended / prior                 # centered on 1.0
receiving_td_factor = clamp(factor, factor_clamp)     # default [0.70, 1.30]
```

### Rushing TD Factor (RB, QB, FB)

```
observed = sum(rz_rush_tds) / sum(rz_rush_carries)   # across weeks < target_week
prior    = positional_avg_rz_rushing_td_rate           # RB ~0.28, QB ~0.25

blended  = (n_carries * observed + prior_strength * prior) / (n_carries + prior_strength)
rushing_td_factor = blended / prior                    # centered on 1.0
rushing_td_factor = clamp(factor, factor_clamp)        # default [0.70, 1.30]
```

### Key Behaviors

- **Minimum opportunities**: Players with fewer than `min_opportunities` (default: 5) RZ targets/carries get factor = 1.0 (neutral).
- **Zero RZ opportunities**: factor = 1.0. Unaffected.
- **Centering on 1.0**: Average player's factor is ~1.0, preserving the existing gate calibration in aggregate. Only deviations from the positional mean change the gate.
- **Positional priors computed from the PFF dataset**: league-wide mean of `rz_rec_tds / rz_rec_targ` (or rushing equivalent) per position, same season window. Not hardcoded constants.
- **PBP fallback**: Same formula, but `observed` comes from PBP-derived counts added to `_aggregate_pbp_stats()`.

## Model Changes

Two new fields on `PlayerOutcomes` in `models/player.py`:

```python
@dataclass
class PlayerOutcomes:
    # ... existing fields ...
    receiving_td_factor: float = 1.0  # multiplier for pass TD gate
    rushing_td_factor: float = 1.0    # multiplier for run TD gate
```

Default 1.0 = neutral. No change to existing behavior when the engine is disabled or data is unavailable.

## Gate Modification

`_red_zone_td_gate()` in `engine/play_resolver.py` gains one parameter:

```python
def _red_zone_td_gate(
    yard_line: int,
    play_type: str,
    rng: np.random.Generator,
    td_factor: float = 1.0,       # player-level multiplier
) -> bool:
    if yard_line > 20:
        return True
    gate_table = PASS_TD_GATE if play_type == "pass" else RUN_TD_GATE
    for (lo, hi), prob in gate_table.items():
        if lo <= yard_line <= hi:
            return rng.random() < min(1.0, prob * td_factor)
    return True
```

### Call Sites

- `_resolve_pass()` line 223: pass `receiver.outcomes.receiving_td_factor` to the gate
- `_resolve_run()` line 296: pass `rusher.outcomes.rushing_td_factor` to the gate

The `default=1.0` parameter means the legacy path (no roster) and QB scramble path are unaffected.

### QB Scramble TDs

The scramble path in `_resolve_pass()` (line 141) bypasses the gate entirely — it checks `(state.yard_line - yards) <= 0` directly. This is unchanged. QB rushing TD tendency applies only to designed runs through `_resolve_run()`. The QB calibration constraint (never modify carry_share/scramble_rate) does not apply — TD tendency modifies the conversion gate, not volume.

## Pipeline Integration

### New Module

`src/fantasy_sim/data/td_tendency.py` — single file, single class.

```python
class TdTendencyEngine:
    def __init__(self, config: TdTendencyConfig, pff_loader: PffLoader | None = None):
        ...

    def apply(self, roster: TeamRoster, season: int, week: int) -> None:
        """Compute and store TD factors on each player's outcomes. Mutates in-place."""
        ...
```

### Config Dataclass

`TdTendencyConfig` dataclass in the same module (or in a shared config location):

```python
@dataclass
class TdTendencyConfig:
    enabled: bool = True
    prior_strength: float = 15.0
    min_opportunities: int = 5
    factor_clamp: tuple[float, float] = (0.70, 1.30)
```

### Pipeline Position

Applied during `build_game()` in `game_context.py`, after tier engine blend, with the other PFF-derived engines:

```
base PBP model -> vegas -> matchup -> team context + tier blend -> normalize
-> coverage -> DST baseline -> kicker -> TD TENDENCY -> weather
-> props -> user overrides -> normalize
```

The TD factor is independent of other adjustments — it doesn't modify catch_rate, yards, or shares. Ordering is flexible; placing it with PFF engines is cleanest.

### Initialization

In `GameContextBuilder.__init__()`, same conditional pattern as kicker/dst_baseline:

```python
self._td_tendency_engine = None
if td_tendency_config is not None and td_tendency_config.enabled:
    self._td_tendency_engine = TdTendencyEngine(td_tendency_config, self._pff_loader)
```

Falls back to PBP-derived computation when `self._pff_loader` is None.

## Configuration

New section in `config/defaults.yaml`:

```yaml
td_tendency:
  enabled: false              # flip to true after A/B validation
  prior_strength: 15          # pseudo-opportunities for Bayesian shrinkage
  min_opportunities: 5        # minimum RZ targets/carries to compute factor
  factor_clamp: [0.70, 1.30]  # prevent extreme gate modifications
```

### A/B Testing

```bash
# Test TD tendency against current defaults
uv run python scripts/validate.py --sims 50 --set td_tendency.enabled=true --label "td-tendency"

# Sweep prior strength
uv run python scripts/validate.py --sims 50 --set td_tendency.prior_strength=10 --label "td-ps10"

# Marginal impact (baseline = defaults, add TD tendency)
uv run python scripts/validate.py --sims 50 --baseline defaults --set td_tendency.enabled=true --label "td-tendency-marginal"
```

### CLI Flag

`--td-tendency/--no-td-tendency` following the `--pff/--weather/--vegas` pattern.

## Scraper Changes

Add two new facets to `scripts/scrape_pff.py`:

- `fantasy_receiving`: `/api/fantasy/stats/receiving?season={s}&weeks={w}&scoring=preset_ppr`
- `fantasy_passing`: `/api/fantasy/stats/passing?season={s}&weeks={w}&scoring=preset_ppr`

Per-week scraping (one request per week), same cookie auth as existing facets. Stored as parquet files keyed by `(season, week)`.

The scraper already handles per-season, per-week patterns for the 21 existing facets. The new facets use a different URL structure (`/api/fantasy/stats/...` vs the existing game-level facet URLs) but the same auth mechanism.

## Scope Boundaries

### In Scope

- PFF fantasy stats scraper (two new facets: receiving, passing)
- `TdTendencyEngine` with Bayesian blend and PBP fallback
- `PlayerOutcomes` fields: `receiving_td_factor`, `rushing_td_factor`
- `_red_zone_td_gate()` player-aware multiplier
- Config section + CLI flag
- Tests for all new code

### Out of Scope (Future Follow-ups)

- Goal-line concentration (splitting RZ target/carry shares into outer-RZ vs inside-5) — architecturally independent
- Inside-5 sub-factor using `i5_rush_carries`/`i5_rush_tds` (data is scraped and stored but not consumed in this phase)
- PFF kicker and DST facets from the fantasy stats endpoint (available but not needed for TD tendency)
- CPOE activation (separate improvement, different signal)
- Route rate A/B test (just a config toggle, separate concern)

## Testing Strategy

- Unit tests for Bayesian blend computation (known inputs → expected factors)
- Unit tests for gate modification (factor > 1.0 increases TD probability, factor < 1.0 decreases)
- Integration test: TdTendencyEngine.apply() mutates roster correctly
- PBP fallback test: correct factors when PFF data is unavailable
- Temporal leakage test: data from target_week and later is never used
- Regression: existing tests pass unchanged (default factor = 1.0 preserves behavior)
- A/B validation via `scripts/validate.py` before merging

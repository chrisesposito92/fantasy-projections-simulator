# Inside-5 Goal-Line Sub-Factor Design

## Problem

The TD tendency engine applies a single `rushing_td_factor` uniformly across all red zone yard-line bands (1-20). A player's goal-line rushing efficiency (inside the 5-yard line) often diverges significantly from their broader red zone performance. Kyren Williams converts 60% of inside-5 carries to TDs (12/20) while Saquon Barkley converts just 24% (4/17) — yet the current system treats them identically at the goal line if their overall RZ rates are similar.

The PFF fantasy stats data already includes `i5_rush_carries` and `i5_rush_tds` columns in both `fantasy_receiving` (RB/WR/TE) and `fantasy_passing` (QB) parquets. This data is scraped and stored but not consumed. This design adds a granular inside-5 rushing factor that replaces the general `rushing_td_factor` for the (1,3) and (4,5) gate bands when sufficient data exists.

## Approach

New field on `PlayerOutcomes` with replace-with-fallback semantics. When a player has enough inside-5 carries, the gate uses their `i5_rushing_td_factor` for yard_line ≤ 5. When they don't, it falls back to the general `rushing_td_factor`. Same Bayesian blend pattern as the existing TD tendency, with inside-5-specific priors and heavier shrinkage for sparser data.

Rushing only — no inside-5 receiving data exists in PFF.

## Data Layer

No new scraping required. The `i5_rush_carries` and `i5_rush_tds` columns already exist in:
- `~/.fantasy-sim/pff/processed/nfl/fantasy_receiving_YYYY.parquet` (RB, WR, TE, FB)
- `~/.fantasy-sim/pff/processed/nfl/fantasy_passing_YYYY.parquet` (QB)

### Data Characteristics (2024 season)

- 49 players with ≥5 inside-5 carries, 67 with ≥3
- Top RBs accumulate 17-22 inside-5 carries per season
- Conversion rates vary widely: 24% to 65% among high-volume backs
- Mobile QBs (Daniels, Hurts, Richardson) also appear in the data

### Inside-5 Positional Priors

Hardcoded constants derived from 2024 PFF data analysis (league-wide mean of `i5_rush_tds / i5_rush_carries`), matching the pattern of existing `_DEFAULT_RUSHING_TD_PRIORS`:

| Position | Inside-5 TD Rate | General RZ TD Rate |
|----------|------------------|--------------------|
| RB       | ~0.50            | ~0.28              |
| QB       | ~0.40            | ~0.25              |
| FB       | ~0.55            | ~0.30              |

Significantly higher than general RZ priors because these carries start within 5 yards of the end zone.

### PBP Fallback

Add `i5_rush_carries` and `i5_rush_tds` counters to `_aggregate_pbp_stats()` in `player_builder.py`. Filter on `yardline_100 <= 5` for rushing plays. Same pattern as existing `rz_carries`/`rz_tds` counters.

## Factor Computation

```
observed = sum(i5_rush_tds) / sum(i5_rush_carries)   # weeks < target_week
prior    = positional_i5_td_rate                      # RB ~0.50, QB ~0.40, FB ~0.55

blended  = (n_carries * observed + i5_prior_strength * prior) / (n_carries + i5_prior_strength)
i5_rushing_td_factor = blended / prior                # centered on 1.0
i5_rushing_td_factor = clamp(factor, factor_clamp)    # reuse existing clamp [0.65, 1.35]
```

### Parameters

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `i5_prior_strength` | 25 | Heavier than general (20) due to sparser inside-5 data. 3 carries with prior_strength=25 produces a heavily shrunk factor near 1.0. |
| `i5_min_opportunities` | 3 | Lower than general (5). Even 3 inside-5 carries is meaningful at the goal line, and 67 players cleared this bar in 2024. |
| `factor_clamp` | [0.65, 1.35] | Reuses existing clamp — no reason for separate bounds. |

### Fallback Behavior

When a player has fewer than `i5_min_opportunities` inside-5 carries, `i5_rushing_td_factor` stays at 1.0 (neutral). The gate then uses the general `rushing_td_factor` instead. No data means no inside-5 differentiation — existing behavior preserved.

## Model Changes

One new field on `PlayerOutcomes` in `models/player.py`:

```python
@dataclass
class PlayerOutcomes:
    # ... existing fields ...
    receiving_td_factor: float = 1.0
    rushing_td_factor: float = 1.0
    i5_rushing_td_factor: float = 1.0   # inside-5 goal-line rushing
```

Default 1.0 = neutral. No change to existing behavior when the feature is disabled or data is unavailable.

## Gate Changes

In `_resolve_run()` in `engine/play_resolver.py`, one conditional selects the factor before calling `_red_zone_td_gate()`:

```python
if state.yard_line <= 5 and rusher.outcomes.i5_rushing_td_factor != 1.0:
    td_factor = rusher.outcomes.i5_rushing_td_factor
else:
    td_factor = rusher.outcomes.rushing_td_factor

if _red_zone_td_gate(state.yard_line, "run", rng, td_factor):
    is_td = True
```

`_red_zone_td_gate()` itself is untouched — it already accepts `td_factor` as a parameter. The existing gate table bands `(1,3)` at 0.35 and `(4,5)` at 0.30 exactly cover the inside-5 zone.

No changes to `_resolve_pass()` — inside-5 is rushing only.

## Engine Changes

### TdTendencyEngine

- `_load_pff_rates()`: return signature changes from 2-tuple to 3-tuple, adding `i5_rush_rates: dict[str, tuple[int, int]]` aggregated from `i5_rush_carries`/`i5_rush_tds` columns in the same parquet load.
- `_rates_from_pbp()`: similarly returns a 3-tuple with PBP-derived inside-5 counts.
- Player loop in `apply()`: compute `i5_rushing_td_factor` using inside-5 priors and `i5_prior_strength`, assign to `player.outcomes.i5_rushing_td_factor`.

### TdTendencyConfig

Three new fields:

```python
@dataclass
class TdTendencyConfig:
    enabled: bool = False
    prior_strength: float = 15.0
    min_opportunities: int = 5
    factor_clamp: tuple[float, float] = (0.70, 1.30)
    i5_enabled: bool = False              # NEW — flip after A/B validation
    i5_prior_strength: float = 25.0       # NEW
    i5_min_opportunities: int = 3         # NEW
```

`i5_enabled` is gated behind the parent `enabled` flag.

## Configuration

Nested under existing `td_tendency:` section in `config/defaults.yaml`:

```yaml
td_tendency:
  enabled: true
  prior_strength: 20
  min_opportunities: 5
  factor_clamp: [0.65, 1.35]
  i5_enabled: false              # flip after A/B validation
  i5_prior_strength: 25
  i5_min_opportunities: 3
```

### A/B Testing

```bash
# Inside-5 factor impact
uv run python scripts/validate.py --sims 50 --set td_tendency.i5_enabled=true --label "i5-subfactor"

# Sweep prior strength
uv run python scripts/validate.py --sims 50 --set td_tendency.i5_prior_strength=15 --label "i5-ps15"
uv run python scripts/validate.py --sims 50 --set td_tendency.i5_prior_strength=35 --label "i5-ps35"

# Sweep min_opportunities
uv run python scripts/validate.py --sims 50 --set td_tendency.i5_min_opportunities=5 --label "i5-mo5"
```

## Testing Strategy

- **Unit: Bayesian blend with inside-5 priors** — known inputs (e.g., 10 carries, 6 TDs, RB prior 0.50, prior_strength 25) produce expected `i5_rushing_td_factor`
- **Unit: gate factor selection** — `i5_rushing_td_factor` used at yard_line ≤ 5 when available, falls back to `rushing_td_factor` when neutral (1.0)
- **Unit: PFF data loading** — `_load_pff_rates()` returns correct 3-tuple with `i5_rush_rates` populated
- **Unit: PBP fallback** — `_rates_from_pbp()` returns inside-5 counts from `yardline_100 <= 5` rushing plays
- **Integration: apply() sets i5 factor** — with mock PFF data, sets `i5_rushing_td_factor` on RB/QB/FB players, leaves WR/TE at 1.0
- **Integration: i5_enabled=false** — factor stays 1.0 when config flag is off
- **Regression** — all existing tests pass unchanged (default 1.0 preserves behavior)
- **A/B validation** via `scripts/validate.py` before merging

## Scope Boundaries

### In Scope

- `i5_rushing_td_factor` field on `PlayerOutcomes`
- Inside-5 computation in `TdTendencyEngine` (PFF primary + PBP fallback)
- Gate factor selection in `_resolve_run()`
- Config additions under `td_tendency:`
- Tests for all new code

### Out of Scope

- Inside-5 receiving (no PFF data exists)
- Goal-line concentration / target share splitting (handoff item #6, architecturally independent)
- Changes to `_resolve_pass()` or the receiving TD gate
- New CLI flags (controlled via existing `--set` overrides)

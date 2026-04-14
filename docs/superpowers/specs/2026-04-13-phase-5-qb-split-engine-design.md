# Phase 5 QB Split Engine Design

Date: 2026-04-13
Status: Approved design
Phase: 5
Topic: QB split engine using PFF `passing_detail`

## Objective

Add a new default-off Phase 5 QB slice that uses PFF `passing_detail` to model
how each starter QB responds to pressure versus a clean pocket, then translate
that response into bounded weekly passing-efficiency nudges without creating a
new QB-only runtime surface or overlapping the responsibilities already owned
by tracking and matchup.

This slice is intentionally narrow:

- `passing_detail` only
- pressure vs no-pressure only
- opponent-aware
- pre-sim only
- efficiency only
- isolated marginal validation only

The first promotable slice adjusts only:

- pass-catcher `catch_rate`
- proportional `red_zone_catch_rate`
- base `receiving_yards_dist`

It does not adjust:

- `play_calling.default`
- team `pace_factor`
- `turnover_rates.sack_rate`
- `turnover_rates.int_rate`
- QB `scramble_rate`
- player `target_share`
- player `air_yards_share`
- `rz_receiving_yards_dist`

## Verified Current State

This design is based on a code-and-data verification pass on branch
`codex/phase-5-depth-role-v1`, not just the companion docs.

### Still true in code

- `pff.depth_role` and `pff.depth_role.efficiency` are both implemented,
  validated, and still default-off in `config/defaults.yaml`
- no `pff.qb_split` config family or runtime engine exists yet
- `GameContextBuilder` runtime order is still:
  - vegas
  - availability
  - usage
  - tracking
  - props
  - matchup
  - tier with optional team context
  - depth-role
  - coverage
  - DST baseline
  - kicker
  - TD tendency
  - weather
  - runtime game script
  - overrides
- `tracking.qb_context` already owns QB/game-environment mutations from
  participation, FTN, and NGS inputs:
  - pass rate
  - pace
  - `scramble_rate`
  - `sack_rate`
- `pff.matchup` already owns opponent and OL environment factors for:
  - `pass_yards_factor`
  - `sack_rate_factor`
  - `int_rate_factor`
  - `ol_pass_block_factor`
- `usage` explicitly does not mutate QB `carry_share` or `scramble_rate`
- current pass resolution still expresses passing efficiency through receiver
  outcome surfaces, not through a dedicated QB completion model

### Still true in local data

- local NFL PFF processed coverage exists for `2018-2025` for:
  - `passing_detail`
  - `passing_summary`
  - `fantasy_passing`
  - `offense_pass_blocking`
- local backtest-era crosswalk and support caches exist for `2022-2024`:
  - `rosters_weekly`
  - `pbp`
  - `participation`
  - `ngs_passing`

### Verified useful `passing_detail` columns

Verified locally in `passing_detail_2024.parquet`:

- `pressure_completion_percent`
- `no_pressure_completion_percent`
- `pressure_ypa`
- `no_pressure_ypa`
- `pressure_dropbacks`
- `no_pressure_dropbacks`
- `pressure_attempts`
- `no_pressure_attempts`
- `pressure_qb_rating`
- `no_pressure_qb_rating`

Verified but explicitly deferred for v1:

- play-action / non-play-action columns such as `pa_completion_percent`,
  `npa_completion_percent`, `pa_ypa`, and `npa_ypa`
- broader split families such as blitz/no-blitz, screen/no-screen, and
  depth/field-side splits
- `fantasy_passing` rushing / red-zone QB rushing fields
- `offense_pass_blocking` direct QB-split usage beyond the existing matchup
  engine's pressure environment

### Phase 5 branch state that this design must respect

- Phase 5A `WR/TE Depth-Role V1` is implemented and not promotable
- Phase 5B `WR/TE efficiency v2` is implemented and not promotable
- the current handoff's recommended next planning target is `QB split engine`
- the remaining deferred Phase 5 follow-on after this is `RB scheme-fit engine`

## Selected Approach

Use an opponent-aware pre-sim PFF `qb_split` engine that:

1. derives each starter QB's pressure-vs-clean efficiency penalty from
   `passing_detail`
2. reads the already-computed weekly pressure environment from `MatchupContext`
3. translates QB-specific pressure response into bounded pass-catcher outcome
   nudges for that week

This was chosen over:

- a new QB runtime passing surface, which would be cleaner architecturally but
  too large for the first Phase 5 QB slice
- a static QB trait layer, which would overlap tier/talent and weaken the case
  for calling this a split engine
- a broader QB bundle using play-action, blitz, red-zone rushing, and OL
  interaction at once, which would make marginal validation harder to trust

## Scope

This slice owns:

- a new `pff.qb_split` config family under `pff`
- starter-QB pressure-vs-clean trait extraction from `passing_detail`
- same-season rolling windows with early-season blend behavior
- opponent-aware weekly factor translation using the existing matchup pressure
  environment
- bounded pre-sim mutations for all non-QB players with `target_share > 0`
  on the active offense
- explicit validation coverage reporting for `pff.qb_split`
- roadmap and audit updates after the validation decision

This slice does not own:

- new QB passing-resolution runtime surfaces
- pressure estimation outside the existing matchup engine
- sack or interception rate mutation
- pass/run rate or pace mutation
- QB rushing or scramble modeling
- red-zone QB rushing from `fantasy_passing`
- play-action or blitz split modeling
- combined Phase 5 bundle validation

## Architecture

### New config family

Add a new nested PFF family under `pff`:

```yaml
pff:
  qb_split:
    enabled: false
    completion_sensitivity: 0.10
    yards_sensitivity: 0.12
    catch_rate_clamp: [0.95, 1.05]
    yards_scale_clamp: [0.94, 1.06]
    min_pressure_dropbacks: 20
    min_clean_dropbacks: 40
    min_games: 4
    early_season_blend: true
```

Reasoning:

- it belongs with the other PFF refinement layers
- it follows the existing `--pff/--no-pff` master switch
- it must be independent from `depth_role` because the QB slice needs its
  own attributable validation header and its own default-off family gate

### Modules

- `src/fantasy_sim/data/pff/qb_split.py`
  - `QbSplitEngine`
  - split aggregation helpers
  - factor derivation helpers
- `src/fantasy_sim/data/pff/models.py`
  - `QbSplitConfig`
  - compact result/context dataclass for runtime factors
- `src/fantasy_sim/data/pff/config.py`
  - parse `pff.qb_split`
- `src/fantasy_sim/data/game_context.py`
  - instantiate and wire the engine
- `src/fantasy_sim/validation/coverage.py`
  - `pff.qb_split` coverage reporting

`GameContextBuilder` orchestrates runtime ordering and mutation, while
feature extraction and factor calculation stay inside `data/pff/`.

### Runtime placement

Runtime placement in `GameContextBuilder`:

1. matchup
2. tier with optional team context
3. qb-split
4. depth-role
5. coverage

Reasoning:

- `matchup` runs first because QB split uses its already-computed weekly
  pressure environment
- `tier` keeps ownership of the broader player baseline before QB split refines
  offense-level passing efficiency response
- `coverage` stays after QB split because it is the more specific
  opponent WR/CB modifier

## Factor Model

### Starter QB identification

For each offense:

- use `roster.get_starting_qb()` after availability/usage/tracking/props/tier
- if no valid starter exists, the engine returns neutral and does nothing

### Historical split trait extraction

For the starter QB, aggregate `passing_detail` rows with the normal no-leakage
window:

- all prior seasons in the training set
- current season rows only where `week < target_week`

Build two core split traits:

- completion resilience:
  - `pressure_completion_percent / no_pressure_completion_percent`
- yards resilience:
  - `pressure_ypa / no_pressure_ypa`

Sample gates:

- require at least `min_pressure_dropbacks`
- require at least `min_clean_dropbacks`
- require at least `min_games`

If current-season support is below threshold and `early_season_blend` is true,
blend current and prior-season rows. If the combined sample still misses the
thresholds, return neutral.

### League-relative normalization

Do not use raw resilience ratios directly.

Instead, normalize each QB trait against the league-wide trait baseline from
the same historical window:

- `completion_trait = qb_completion_resilience / league_completion_resilience`
- `yards_trait = qb_yards_resilience / league_yards_resilience`

This keeps the effect centered on a league-average QB and prevents the engine
from double-counting the generic cost of pressure that already exists in the
rest of the stack.

### Weekly matchup trigger

Use the weekly pressure environment already produced by `MatchupContext`:

- `pressure_environment = sack_rate_factor * ol_pass_block_factor`

Interpretation:

- `1.0` is neutral
- `> 1.0` is a tougher pressure environment
- `< 1.0` is a cleaner pocket environment

The QB split engine must not create its own second pressure estimate.

### Weekly factor translation

Selected formulas:

- `completion_factor = 1.0 + (completion_trait - 1.0) * (pressure_environment - 1.0) * completion_sensitivity`
- `yards_factor = 1.0 + (yards_trait - 1.0) * (pressure_environment - 1.0) * yards_sensitivity`

Then clamp:

- `completion_factor` with `catch_rate_clamp`
- `yards_factor` with `yards_scale_clamp`

This keeps the slice explicitly differential:

- neutral matchup pressure means no QB split effect
- resilient QBs gain in hard-pressure matchups
- pressure-sensitive QBs lose in hard-pressure matchups
- easy-pressure matchups soften the penalty for pressure-sensitive QBs

## Runtime Mutation Rules

Apply the weekly factors to all non-QB players on the offense with
`target_share > 0`.

### Completion translation

Apply `completion_factor` to:

- `catch_rate`
- proportional `red_zone_catch_rate`

Rule:

- if a player has both values, scale `red_zone_catch_rate` by the same ratio
  used to update `catch_rate`
- clamp final rates to `[0.0, 1.0]`

### Yardage translation

Apply `yards_factor` to:

- base `receiving_yards_dist`

Rule:

- scale the existing distribution multiplicatively
- do not replace the empirical distribution with a new synthetic curve
- do not change `rz_receiving_yards_dist` in v1

### Explicit non-goals

Do not mutate:

- `target_share`
- `air_yards_share`
- `scramble_rate`
- `turnover_rates`
- `play_calling.default`
- `pace_factor`

## Data Flow

End-to-end flow:

1. `GameContextBuilder` computes the normal `MatchupContext`
2. `GameContextBuilder` computes and applies tier/team-context
3. `GameContextBuilder` calls `QbSplitEngine` for each offense, passing:
   - roster
   - `target_season`
   - `week`
   - `pff_crosswalk`
   - that offense's already-computed `MatchupContext`
4. `QbSplitEngine` identifies the starter QB
5. `QbSplitEngine` aggregates the starter's historical pressure/no-pressure
   rows and computes league-relative traits
6. `QbSplitEngine` combines those traits with the matchup pressure environment
   and returns compact runtime factors
7. `GameContextBuilder` applies those factors to eligible pass-catchers
8. downstream PFF layers continue normally, with coverage still running after
   qb-split

## Coverage Rules

Add a new validation signal:

- `pff.qb_split`

It reports full/partial/none using required historical inputs for each
test season.

Required paths per season:

- `passing_detail_<season>.parquet`
- `passing_summary_<season>.parquet`
- `rosters_weekly_<season>.parquet`

Reasoning:

- `passing_detail` is the primary feature source
- `passing_summary` keeps the signal aligned with the rest of the PFF QB
  crosswalk and summary family expectations
- `rosters_weekly` is required to resolve starter-QB mapping cleanly

`fantasy_passing` and `offense_pass_blocking` are not required for
`pff.qb_split` coverage in v1 because they are intentionally out of scope.

## Error Handling

The runtime policy is neutral fallback, never partial guesswork.

- if the starter QB cannot be found, return neutral
- if the QB is not in the PFF crosswalk, return neutral
- if required split columns are missing, return neutral
- if sample thresholds are not met after early-season blending, return neutral
- if matchup pressure is unavailable, return neutral
- if the target pool has no non-QB players with `target_share > 0`, do nothing

Do not silently degrade from pressure/no-pressure to:

- play-action/non-play-action
- overall `passing_summary`
- QB rating only
- raw sack rate alone

That kind of fallback would blur what the validation artifact actually tested.

## Testing

### Config tests

Add config coverage for:

- default `pff.qb_split` parsing
- custom-value parsing
- validation override propagation

- add parsing tests in `tests/test_data/test_pff/test_config.py`
- `tests/test_validation/test_config.py`

### Engine unit tests

Add targeted unit tests for:

- pressure-vs-clean trait computation from synthetic `passing_detail` rows
- low-sample neutral fallback
- early-season blending behavior
- league-relative normalization
- neutral matchup pressure producing neutral factors
- tough matchup pressure amplifying pressure-sensitive QBs negatively
- tough matchup pressure rewarding resilient QBs positively

- `tests/test_data/test_pff/test_qb_split.py`

### Integration tests

Add runtime tests verifying:

- qb-split is wired after matchup/tier and before coverage
- only eligible non-QB pass-catchers are mutated
- `catch_rate`, proportional `red_zone_catch_rate`, and base
  `receiving_yards_dist` change together
- `play_calling`, `turnover_rates`, `scramble_rate`, `target_share`, and
  `air_yards_share` do not change

- `tests/test_data/test_pff/test_qb_split_integration.py`

### Coverage tests

Add explicit `pff.qb_split` coverage assertions in:

- `tests/test_validation/test_coverage.py`

## Validation Plan

After implementation:

1. run narrow config and engine tests first
2. run integration and coverage tests
3. run one marginal validation artifact against `baseline=defaults`
4. require the validation header to print explicit `pff.qb_split=...` coverage
5. update both source-of-truth docs with the actual result:
   - `docs/accuracy-roadmap.md`
   - `docs/accuracy-stack-audit.md`

First validation target:

- test seasons `2022-2024`
- comparison mode `marginal_lift`
- baseline `defaults`
- leave the rest of the current default stack unchanged

## Promotion Gate

This slice is promotable only if its isolated marginal artifact shows:

- clear weekly QB improvement, or weekly QB improvement with acceptable hold on
  WR/TE weekly metrics
- no material season-level regression across the core position groups
- trustworthy `pff.qb_split` coverage in the run header

If the result is flat or regressive, keep `pff.qb_split.enabled: false` and
carry the real verdict into the roadmap, audit, and the next handoff.

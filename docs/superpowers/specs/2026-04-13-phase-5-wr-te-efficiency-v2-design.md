# Phase 5 WR/TE Efficiency V2 Design

Date: 2026-04-13
Status: Approved design
Phase: 5
Topic: WR/TE efficiency v2 using PFF `receiving_depth`

## Objective

Add a second Phase 5 WR/TE slice that uses `receiving_depth` to improve what
happens when WRs and TEs are targeted, without reopening volume/role questions,
mixing in matchup-specific logic, or bundling multiple hypotheses into one
validation artifact.

This slice should stay narrow:

- WR and TE only
- pre-sim only
- efficiency only
- isolated marginal validation only

The first promotable efficiency pass should adjust:

- `catch_rate`
- proportional `red_zone_catch_rate`
- base `receiving_yards_dist`

It should not adjust:

- `target_share`
- `air_yards_share`
- `red_zone_target_share`
- `rz_receiving_yards_dist`

## Verified Current State

This design is based on the current post-Phase-5A branch state, not the
pre-implementation roadmap assumptions.

### Still true in code

- `pff.depth_role` is now implemented in:
  - `src/fantasy_sim/data/pff/depth_role.py`
  - `src/fantasy_sim/data/game_context.py`
  - `src/fantasy_sim/validation/coverage.py`
- runtime order in `GameContextBuilder` is now:
  - matchup
  - tier with optional team context
  - depth-role
  - coverage
  - DST baseline
  - kicker
  - TD tendency
  - weather
- `depth_role` currently mutates only:
  - `target_share`
  - `air_yards_share`
- `depth_role` currently does not mutate:
  - `catch_rate`
  - `red_zone_catch_rate`
  - `receiving_yards_dist`
  - `rz_receiving_yards_dist`
- `coverage` still owns opponent-specific WR catch/YPR modifiers and remains the
  last PFF skill-position step

### Still true in local data

- local NFL `receiving_depth` coverage exists for `2018-2025`
- local NFL `receiving_summary`, `rushing_summary`, and `passing_summary`
  coverage exists for `2018-2025`
- local `rosters_weekly` cache exists through `2025`
- the current validation coverage path for `pff.depth_role` is now runtime-aware
  and requires:
  - `receiving_depth`
  - the PFF summary trio
  - `rosters_weekly`

### Phase 5A evidence that this slice must respect

The current Phase 5A artifact is:

- label: `phase-5-depth-role-v1`
- baseline: `defaults`
- comparison mode: `marginal_lift`
- coverage:
  - `pff.depth_role=full(2022,2023,2024)`
  - `pff.depth_role.wr=full(2022,2023,2024)`
  - `pff.depth_role.te=full(2022,2023,2024)`
- result:
  - `rank_corr delta:  -0.0005`
  - `weekly_mae delta: +0.002`
  - `season_mae delta: +0.013`

Interpretation:

- the Phase 5A role-volume slice is implemented and validated
- it is not promotable on current evidence
- this follow-on should not silently re-test the same role-volume hypothesis

## Recommended Approach

Extend the existing `DepthRoleEngine` with a separate efficiency branch that is
config-gated independently from the Phase 5A volume branch.

This was chosen over:

- creating a second engine class, which would duplicate `receiving_depth`
  loading, crosswalk logic, and early-season blending
- folding efficiency changes into the old Phase 5A config path, which would
  blur attribution between volume and efficiency
- a post-sim efficiency adjuster, which would ignore the existing pre-sim player
  outcome hooks and reduce interpretability

## Scope

This slice owns:

- WR/TE-only pre-sim efficiency adjustments from `receiving_depth`
- bounded updates to:
  - `catch_rate`
  - proportional `red_zone_catch_rate`
  - base `receiving_yards_dist`
- isolated marginal validation and coverage reporting for the efficiency sub-slice
- required roadmap and audit updates after the validation decision

This slice does not own:

- any further volume changes
- `target_share`
- `air_yards_share`
- `red_zone_target_share`
- `rz_receiving_yards_dist`
- QB split modeling
- RB scheme-fit work
- combined Phase 5A + 5B bundle promotion

## Architecture

### Keep one engine family

Do not create a new engine file or a new top-level config family.

Instead:

- keep one `DepthRoleEngine`
- add a nested `efficiency` config block under `pff.depth_role`
- compute role and efficiency features from the same aggregated player-season rows

Reasoning:

- one loader path for one PFF source is easier to reason about
- one engine can keep the crosswalk, early-season blending, and team-coverage
  completeness rules consistent
- separate config gates preserve clean A/B attribution

### Recommended config shape

Example target shape:

```yaml
pff:
  depth_role:
    enabled: false
    ...
    efficiency:
      enabled: false
      min_routes: 15
      min_receptions: 6
      min_games: 4
      catch_rate_clamp: [0.94, 1.06]
      yards_scale_clamp: [0.92, 1.08]
      wr:
        catch_rate_sensitivity: 0.08
        yards_scale_sensitivity: 0.10
      te:
        catch_rate_sensitivity: 0.06
        yards_scale_sensitivity: 0.08
```

The top-level `pff.depth_role.enabled` should remain the family gate. The new
`pff.depth_role.efficiency.enabled` should gate only the efficiency mutations.

### Runtime placement

Keep `DepthRoleEngine` in the existing runtime slot:

1. matchup
2. tier with optional team context
3. depth-role
4. coverage

Inside `DepthRoleEngine.apply()`:

- apply volume factors only when the Phase 5A config path is enabled
- apply efficiency factors only when the v2 efficiency config path is enabled

That preserves existing engine ordering and keeps efficiency still upstream of
coverage.

## Factor Logic

### Catch-efficiency signal

Use `receiving_depth` to derive a bounded efficiency estimate for catch success.

Candidate ingredients:

- caught-rate behavior by depth bucket
- targeted QB rating by depth bucket
- drop-related fields where present
- weighted short/medium/deep catch stability

Recommended output:

- a bounded multiplicative factor on `catch_rate`
- proportional scaling of `red_zone_catch_rate`

Recommended behavior:

- keep the factor centered on `1.0`
- clamp tightly
- require minimum routes and receptions before using the signal
- keep players neutral when team coverage is incomplete or individual sample is thin

### Yardage-efficiency signal

Use `receiving_depth` to derive a bounded yardage-efficiency estimate.

Candidate ingredients:

- yards per reception by bucket
- yards after catch per reception where present
- deep vs short efficiency shape
- weighted bucket mix from the same-season sample

Recommended output:

- scale the existing `receiving_yards_dist`

Recommended behavior:

- do not replace the empirical distribution
- do not create a synthetic or tier-selected yardage curve in this slice
- use a bounded scale factor only

### Explicit non-goals

Do not change:

- `rz_receiving_yards_dist`
- any target shares
- any red-zone target shares
- any opponent-specific catch or YPR modifiers

That keeps v2 focused on non-matchup receiving efficiency.

## Data Rules

Use the same evidence discipline already established in `DepthRoleEngine`:

- same-season rolling window with `week < max_week`
- prior-season blend when current sample is thin
- neutral behavior when team crosswalk coverage is incomplete
- neutral behavior when a player lacks sufficient efficiency observations

The current real-data caveat remains:

- side-split route columns are the correct route-volume source
- flat bucket `*_routes` columns should not drive route-volume gating when the
  side-split columns are present

## Validation Strategy

### Primary experiment

Run this as an isolated marginal validation arm:

- `defaults` vs `defaults + pff.depth_role.efficiency.enabled=true`

Do not treat this as a Phase 5A + 5B bundle test.

### Promotion gate

Promote only if:

- WR and/or TE improve materially on weekly metrics
- overall weekly MAE does not regress materially
- overall season MAE does not regress materially
- QB and RB do not regress materially
- the result is explainable as efficiency-only marginal lift

If flat or negative:

- keep it implemented but default-off
- record the result explicitly in the roadmap and audit
- do not force a combined bundle test as a rescue attempt

## Documentation Requirements

This slice is not complete without updating the two canonical docs.

### `docs/accuracy-roadmap.md`

Update to:

- mark `WR/TE efficiency v2` as the current Phase 5 priority
- keep Phase 5A recorded as implemented, validated, not promoted
- keep explicit deferrals visible:
  - `QB split engine`
  - `RB scheme-fit engine`
- record the new validation artifact and verdict

### `docs/accuracy-stack-audit.md`

Update to:

- reflect the new `pff.depth_role.efficiency` config state
- record whether the efficiency slice is implemented-only, validated, or promoted
- keep `pff.depth_role.enabled` and defaults accurate
- keep the Phase 5 ordering, caveats, and immediate-next-slice wording current

## Deferral Ledger

The following items remain outside this slice and should stay explicit in the
handoff docs:

### Immediate next after Phase 5A

- `WR/TE efficiency v2`

### Still deferred after efficiency v2

- `QB split engine`
- `RB scheme-fit engine`
- red-zone receiving-yard efficiency

## Success Definition

This slice is successful if it improves WR/TE receiving efficiency calibration
without reopening the already-tested role-volume hypothesis and without
introducing new uncertainty about whether the gain came from volume, matchup,
or post-sim cleanup.

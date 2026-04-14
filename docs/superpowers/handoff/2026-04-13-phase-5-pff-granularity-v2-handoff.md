# Handoff: Phase 5 PFF Granularity V2

## Branch

- current branch: `codex/phase-5-depth-role-v1`

## What Was Completed

Phase 5 now has two implemented slices, both validated and both left
default-off:

1. `WR/TE Depth-Role V1`
2. `WR/TE efficiency v2`

Neither slice is promotable on current evidence.

## Phase 5A: WR/TE Depth-Role V1

### What shipped

- new `pff.depth_role` config family in `config/defaults.yaml`
- runtime engine in `src/fantasy_sim/data/pff/depth_role.py`
- wiring in `src/fantasy_sim/data/game_context.py`
- validation coverage reporting in `src/fantasy_sim/validation/coverage.py`

### Decision artifact

- label: `phase-5-depth-role-v1`
- baseline: `defaults`
- comparison mode: `marginal_lift`
- coverage:
  - `pff.depth_role=full(2022,2023,2024)`
  - `pff.depth_role.wr=full(2022,2023,2024)`
  - `pff.depth_role.te=full(2022,2023,2024)`
- result:
  - `rank_corr delta: -0.0005`
  - `weekly_mae delta: +0.002`
  - `season_mae delta: +0.013`

### Verdict

- implemented
- validated
- not promoted
- keep `pff.depth_role.enabled: false`

## Phase 5B: WR/TE Efficiency V2

### What shipped

- nested `pff.depth_role.efficiency` config family
- efficiency branch inside the existing `DepthRoleEngine`
- efficiency-specific validation coverage signal:
  - `pff.depth_role.efficiency`

Current efficiency behavior is intentionally narrow:

- adjusts `catch_rate`
- scales `red_zone_catch_rate` proportionally
- scales base `receiving_yards_dist`
- does not change:
  - `target_share`
  - `air_yards_share`
  - `rz_receiving_yards_dist`

### Important implementation notes

- the engine had two runtime/schema fixes after initial implementation:
  - `receiving_depth` does not expose flat `routes`; route volume now comes from
    side-split route columns
  - bucketed `*_routes` columns in the real parquet behave like target/base-target
    counts and must not drive route-volume gating when side-split columns exist

### Decision artifact

- label: `phase-5-depth-role-efficiency-v2-activated`
- baseline: `defaults`
- comparison mode: `marginal_lift`
- coverage:
  - `pff.depth_role=full(2022,2023,2024)`
  - `pff.depth_role.wr=full(2022,2023,2024)`
  - `pff.depth_role.te=full(2022,2023,2024)`
  - `pff.depth_role.efficiency=full(2022,2023,2024)`
- result:
  - `rank_corr delta: +0.0000`
  - `weekly_mae delta: -0.002`
  - `season_mae delta: +0.030`

### Superseded setup artifact

- label: `phase-5-depth-role-efficiency-v2`
- result:
  - `rank_corr delta: +0.0002`
  - `weekly_mae delta: -0.002`
  - `season_mae delta: -0.017`
- this row is only useful as setup/debug evidence because the coverage header
  left the depth-role family disabled

### Verdict

- implemented
- validated
- not promoted
- keep:
  - `pff.depth_role.enabled: false`
  - `pff.depth_role.efficiency.enabled: false`

## Canonical Docs Updated

These are now the source-of-truth handoff docs:

- `docs/accuracy-roadmap.md`
- `docs/accuracy-stack-audit.md`

They already reflect:

- Phase 5A result
- Phase 5B activated result
- current defaults
- current deferrals

## Current Repo State

### Relevant commits on this branch

- `eaf4746` docs: record activated phase 5 efficiency artifact
- `5cf3a97` docs: record phase 5 efficiency status
- `2b3ea9a` test: isolate depth role efficiency parent gate
- `9047090` feat: add depth role efficiency coverage reporting
- `4031736` fix: isolate depth role efficiency mutations
- `48a3421` feat: add depth role efficiency adjustments
- `a621f8f` test: lock depth role efficiency defaults
- `5459d50` feat: add depth role efficiency config

### Working tree note

At handoff time there is an untracked plan file:

- `docs/superpowers/plans/2026-04-13-phase-5-wr-te-efficiency-v2.md`

It was intentionally left uncommitted. A new session can ignore it, keep it, or
clean it up before branch-finalization.

## Recommended Next Work

Do **not** keep iterating blindly on Phase 5 WR/TE slices unless there is one
very specific new hypothesis to test.

Recommended next planning target:

- `QB split engine`

Reasoning:

- both WR/TE Phase 5 slices are now implemented and validated
- both are non-promotable on current evidence
- RB scheme-fit still has the added `rushing_direction` shape complexity
- QB split modeling is the cleaner next high-granularity PFF slice

## Recommended New-Session Starting Point

Start with a fresh brainstorming/spec pass for `QB split engine`, not immediate
implementation.

Suggested files to read first:

- `docs/superpowers/handoff/2026-04-13-phase-5-pff-granularity-v2-handoff.md`
- `docs/accuracy-roadmap.md`
- `docs/accuracy-stack-audit.md`
- `src/fantasy_sim/data/pff/depth_role.py`
- `config/defaults.yaml`

## One-Line Summary

Phase 5 is complete, both WR/TE slices are implemented but not promotable, the
docs are current, and the best next move is a fresh `QB split engine` planning
session.

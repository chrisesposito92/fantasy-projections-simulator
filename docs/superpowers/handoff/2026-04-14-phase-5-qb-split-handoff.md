# Handoff: Phase 5 QB Split Engine

## Branch

- current branch: `codex/phase-5-depth-role-v1`

## What Was Completed

Phase 5 now has three implemented slices, all validated and all left
default-off:

1. `WR/TE Depth-Role V1`
2. `WR/TE efficiency v2`
3. `QB split engine`

None of the three Phase 5 slices are promotable on current evidence.

## Phase 5C: QB Split Engine

### What shipped

- new `pff.qb_split` config family in `config/defaults.yaml`
- typed config/result models in `src/fantasy_sim/data/pff/models.py`
- runtime engine in `src/fantasy_sim/data/pff/qb_split.py`
- wiring in `src/fantasy_sim/data/game_context.py`
- validation coverage reporting in `src/fantasy_sim/validation/coverage.py`
- direct config, coverage, unit, and integration tests

### Runtime scope

Current `qb_split` behavior is intentionally narrow:

- uses PFF `passing_detail`
- models QB pressure-vs-clean passing response
- applies bounded pre-sim adjustments to eligible pass-catchers:
  - `catch_rate`
  - proportional `red_zone_catch_rate`
  - base `receiving_yards_dist`
- does not change:
  - `target_share`
  - `air_yards_share`
  - `scramble_rate`
  - `turnover_rates`
  - `play_calling.default`
  - `rz_receiving_yards_dist`

### Important implementation notes

- the final branch state includes several follow-up fixes after the first
  qb-split validation run:
  - preserve prior-season QB history across team changes
  - limit early-season blending to the immediate previous season
  - require matchup availability before constructing the runtime engine
  - include `target_season` data for forward-looking qb-split runs
  - align coverage gating with runtime gating when matchup is disabled
  - fix transferred-QB crosswalk fallback to prefer the latest/current-team PFF row
  - clear stale cached crosswalk state across roster-season switches
- `passing_detail` is now the first active runtime consumer added after the
  earlier Phase 5 WR/TE slices
- the final current-head artifact is the post-fix rerun, not the earlier
  pre-fix artifact

### Current decision artifact

- label: `phase-5-qb-split-v1-postfix`
- baseline: `defaults`
- comparison mode: `marginal_lift`
- coverage:
  - `pff.qb_split=full(2022,2023,2024)`
- result:
  - `rank_corr delta: +0.0000`
  - `weekly_mae delta: +0.006`
  - `season_mae delta: +0.020`

### Superseded pre-fix artifact

- label: `phase-5-qb-split-v1`
- result:
  - `rank_corr delta: +0.0005`
  - `weekly_mae delta: -0.000`
  - `season_mae delta: -0.028`
- this earlier row is still useful as pre-fix evidence, but it is not the
  current branch decision artifact after the qb-split follow-up fixes landed

### Verdict

- implemented
- validated
- not promoted
- keep `pff.qb_split.enabled: false`

## Canonical Docs Updated

These are now the source-of-truth handoff docs:

- `docs/accuracy-roadmap.md`
- `docs/accuracy-stack-audit.md`

They already reflect:

- final qb-split implementation state
- post-fix decision artifact `phase-5-qb-split-v1-postfix`
- current runtime ordering
- current Phase 5 deferrals

## Current Repo State

### Relevant commits on this branch

- `5524ea1` docs: refresh qb split artifact after postfix rerun
- `5654cbe` Clear stale PFF crosswalk on empty season switch
- `3352fb1` Fix qb split PFF crosswalk recency
- `b3fd397` Fix qb split target-season crosswalk handling
- `993652b` Fix qb split target-season loading
- `d280a2c` fix: gate qb split on matchup dependency
- `395f1e0` feat: wire qb split into game context
- `e9d131f` fix: preserve qb split history across teams
- `51f0d14` feat: add qb split engine
- `6f7be97` feat: add qb split coverage reporting
- `a01d602` feat: add qb split config scaffolding

### Working tree note

At handoff time there are still two untracked plan files:

- `docs/superpowers/plans/2026-04-13-phase-5-qb-split-engine.md`
- `docs/superpowers/plans/2026-04-13-phase-5-wr-te-efficiency-v2.md`

They were intentionally left untouched during implementation. A new session can
ignore them, keep them, or clean them up before branch-finalization.

## Recommended Next Work

Do **not** spend another session retuning `qb_split` unless there is one very
specific new hypothesis to test.

Recommended next planning target:

- `RB scheme-fit engine`

Reasoning:

- `WR/TE depth-role`, `WR/TE efficiency`, and `QB split` are now all
  implemented and validated
- none of the three Phase 5 slices are promotable on current evidence
- `RB scheme-fit` is the only major deferred Phase 5 follow-on left
- `rushing_direction` still has structural complexity, so it needs a fresh
  brainstorming/spec pass rather than ad hoc implementation

## Recommended New-Session Starting Point

Start with a fresh brainstorming/spec pass for `RB scheme-fit engine`, not
immediate implementation.

Suggested files to read first:

- `docs/superpowers/handoff/2026-04-14-phase-5-qb-split-handoff.md`
- `docs/accuracy-roadmap.md`
- `docs/accuracy-stack-audit.md`
- `src/fantasy_sim/data/pff/qb_split.py`
- `src/fantasy_sim/data/pff/loader.py`
- `config/defaults.yaml`
- `AGENTS.md`

## One-Line Summary

Phase 5 now includes a fully implemented qb-split slice, the final post-fix
artifact is still non-promotable, the docs are current, and the best next move
is a fresh `RB scheme-fit engine` brainstorming/spec session.

---
phase: 01-bug-fixes-cheap-calibration-time-sensitive-scrape
plan: 00
type: execute
wave: 0
depends_on: []
files_modified:
  - scripts/validate.py
  - src/fantasy_sim/validation/config.py
  - src/fantasy_sim/validation/ledger.py
  - src/fantasy_sim/config/loader.py
  - config/defaults.yaml
  - tests/test_validation/test_config.py
  - tests/test_validation/test_ledger_schema.py
  - .planning/PROJECT-PHASE0-FROZEN.md
autonomous: true
requirements: [ALL_PHASE_1]
must_haves:
  truths:
    - "Per D-29 / D-32b (revised 2026-04-26 — addresses Codex HIGH-1 + HIGH-4): scripts/validate.py is extended with a new --arm-b-base {defaults,bare} flag (default: defaults — preserves backward compatibility). When --arm-b-base bare, Arm B starts from build_bare_engine_configs() and applies --set overrides on top, enabling true (bare) vs (bare + overrides) isolation."
    - "Per D-32b: Phase-0 baseline ledger entries are pinned BEFORE any KS work begins. phase0.baseline.full has Arm A=bare, Arm B=current promoted defaults; phase0.baseline.bare has Arm A=bare, Arm B=bare (self-consistency check, must show ~zero delta)."
    - "Per D-32 (revised): the Phase-0 baseline ledger Arm B metrics are the canonical reference for the end-of-phase aggregate comparison in Plan 11."
    - "The harness extension is backward-compatible — existing labels (decision_s200, residual-calibration-s200, all phase-N-* labels) are unaffected."
    - "Per D-25 (revised): the final commit on this plan uses message format `feat(01-00): KS-Phase1 PROMOTED — validate.py --arm-b-base flag + Phase-0 baseline pin + KS flags + ledger mean-bias`."
    - "Per D-43: log directory created in Wave 0 — `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/` exists with .gitkeep before any KS plan writes to it."
    - "Existing 1,200+ test suite stays green throughout."
    - "Per D-44 (Cycle 3 — addresses Cycle-2 NEW HIGH #2): bare_config_dict() enumerates EVERY .enabled gate that build_engine_configs in src/fantasy_sim/validation/config.py:118-138 keys off — including the TOP-LEVEL gates (pff.enabled, weather.enabled, vegas.enabled, props.enabled, usage.enabled, tracking.enabled, availability.enabled, role_trend.enabled, market_history.enabled, game_script.enabled, goal_line_concentration.enabled, td_tendency.enabled, target_selection.enabled, play_call_model.enabled, qb_rushing.{scramble,designed_runs}.enabled) AND the sub-engine flags. The Cycle-2 'loosen the test' escape hatch is REMOVED; the integration test is a hard gate (Task 4) that asserts every engine returns None from build_engine_configs(bare_config_dict(load_defaults()))."
    - "Per D-45 (Cycle 3 — addresses Cycle-2 NEW HIGH #1): a new `phase1_ks_flags` block is added to config/defaults.yaml with one feature flag per per-KS code change (KS-01, KS-03, KS-04, KS-05, KS-06, KS-07, KS-15, KS-32). Default `enabled: false` for every flag — preserves backward compatibility. A get_phase1_ks_flags() helper is added to src/fantasy_sim/config/loader.py so KS plans can branch on the flag at module/import time without plumbing the full config dict through every call site. bare_config_dict() also disables every phase1_ks_flag so the per-KS bare-isolation A/B can flip exactly one flag in Arm B via --set."
    - "Per D-46 (Cycle 3 — addresses Cycle-2 NEW HIGH #3): SeasonMetrics in src/fantasy_sim/validation/ledger.py is extended with an optional stat_mean_bias field (shape: {position: {stat_name: {arm_a_bias, arm_b_bias, bias_delta, n}}}); CURRENT_LEDGER_SCHEMA_VERSION bumps 4 → 5 with backward-compatible load_ledger() defaults to empty dict. validate.py writes the new field per-stat alongside stat_ks. Plan 11 reads stat_mean_bias['QB']['pass_yards']['arm_b_bias'] directly from the persisted ledger entries (Phase-0 vs post-Phase-1)."
  artifacts:
    - path: "scripts/validate.py"
      provides: "New --arm-b-base {defaults,bare} CLI flag; Arm B config construction branches on it; per-position-stat mean bias written to SeasonMetrics.stat_mean_bias alongside stat_ks"
      contains: "--arm-b-base"
    - path: "src/fantasy_sim/validation/config.py"
      provides: "Helper to produce a defaults-shaped config dict with EVERY .enabled gate (top-level + sub-engine + Phase-1 KS flags) forced false"
      contains: "def bare_config_dict"
    - path: "src/fantasy_sim/validation/ledger.py"
      provides: "SeasonMetrics.stat_mean_bias field + CURRENT_LEDGER_SCHEMA_VERSION bumped to 5; load_ledger backward-compatible default for older entries"
      contains: "stat_mean_bias"
    - path: "src/fantasy_sim/config/loader.py"
      provides: "get_phase1_ks_flags() helper returning the phase1_ks_flags block from load_defaults()"
      contains: "def get_phase1_ks_flags"
    - path: "config/defaults.yaml"
      provides: "phase1_ks_flags: block with 8 KS feature flags (default false each)"
      contains: "phase1_ks_flags:"
    - path: "tests/test_validation/test_config.py"
      provides: "Tests for bare_config_dict (with hard-gate end-to-end engine-coverage check) and apply_overrides on bare base"
      contains: "def test_bare_config_dict"
    - path: "tests/test_validation/test_ledger_schema.py"
      provides: "Tests for SeasonMetrics.stat_mean_bias schema bump + backward-compat load_ledger"
      contains: "stat_mean_bias"
    - path: ".planning/PROJECT-PHASE0-FROZEN.md"
      provides: "Phase-0 baseline pin record: defaults.yaml SHA + ledger label + run timestamp + headline metrics including QB pass_yards mean bias from new ledger field"
      contains: "## Phase-0 frozen baseline"
    - path: "results/ab_ledger.json"
      provides: "Two new entries: phase0.baseline.full and phase0.baseline.bare; both populated with stat_mean_bias per the new schema"
      contains: "phase0.baseline.full"
  key_links:
    - from: "all per-KS plans (01-08, 10) bare-isolation A/B runs"
      to: "validate.py --arm-b-base bare"
      via: "the new CLI flag"
      pattern: "--arm-b-base bare"
    - from: "all per-KS code-change plans (01, 02, 03, 04, 05, 06, 07, 10 retune)"
      to: "phase1_ks_flags.ksXX_<name>.enabled"
      via: "config feature flag plus get_phase1_ks_flags() loader helper"
      pattern: "phase1_ks_flags\\."
    - from: "Plan 11 aggregate validation"
      to: "phase0.baseline.full ledger entry stat_mean_bias field"
      via: "extended ledger schema (Cycle 3 D-46)"
      pattern: "stat_mean_bias"
    - from: "Plan 11 aggregate validation"
      to: "phase0.baseline.full ledger entry"
      via: "ledger Arm B comparison"
      pattern: "phase0.baseline.full"
---

<objective>
Implement the prerequisite Phase 1 infrastructure that the Codex reviews (`01-REVIEWS.md` Cycle 1 HIGH-1/HIGH-4 + Cycle 2 NEW HIGH #1/#2/#3) flagged as missing:

1. **Extend `scripts/validate.py` with a `--arm-b-base {defaults,bare}` flag** (Cycle 2 work, preserved) so that per-KS A/B isolation runs can perform a true `(bare) vs (bare + overrides)` comparison, instead of `(bare) vs (defaults + overrides)` contamination.
2. **Make `bare_config_dict()` exhaustive (Cycle 3 NEW HIGH #2 fix):** enumerate EVERY `.enabled` gate the engines key off — top-level (`pff.enabled`, `vegas.enabled`, `usage.enabled`, `props.enabled`, `weather.enabled`, `tracking.enabled`, `availability.enabled`, `role_trend.enabled`, `market_history.enabled`, `game_script.enabled`, `goal_line_concentration.enabled`, `td_tendency.enabled`, `target_selection.enabled`, `play_call_model.enabled`, `qb_rushing.{scramble,designed_runs}.enabled`) AND sub-engine — and REMOVE the Cycle-2 "loosen the test" escape hatch from Task 4. The integration test is a hard gate: if any engine's `<engine>_config` returns non-None from `build_engine_configs(bare_config_dict(load_defaults()))`, the helper is incomplete and must be extended.
3. **Add per-KS feature flags (Cycle 3 NEW HIGH #1 fix):** introduce a `phase1_ks_flags:` block in `config/defaults.yaml` with one flag per per-KS code change (KS-01, KS-03, KS-04, KS-05, KS-06, KS-07, KS-15, KS-32). Default `enabled: false` for every flag. Add a `get_phase1_ks_flags()` shim to `src/fantasy_sim/config/loader.py` so KS plans can read the flag at module/import time. This makes per-KS code-change A/B genuinely two-arm: Arm A executes the legacy code path (flag false), Arm B executes the new code path (flag true via `--set`).
4. **Extend `SeasonMetrics` with `stat_mean_bias` (Cycle 3 NEW HIGH #3 fix):** add an optional `stat_mean_bias` field to `SeasonMetrics` mirroring the shape of `stat_ks` so per-position-stat mean bias is persisted in the ledger. Bump `CURRENT_LEDGER_SCHEMA_VERSION` from 4 to 5; `load_ledger()` defaults old entries to empty dict for backward compatibility. Wire `validate.py` to write the new field per-position-stat alongside `stat_ks`. Plan 11 then reads `stat_mean_bias["QB"]["pass_yards"]["arm_b_bias"]` directly to evaluate Phase 1 success criterion 1 (QB pass_yards mean bias narrowed from ~−28 yd/g to within ±10 yd/g).
5. **Pin a frozen Phase-0 baseline ledger entry** (`phase0.baseline.full`) representing the current promoted defaults state. This is the reference Plan 11 will compare against. With the schema extension above, the entry now includes per-stat mean bias.
6. **Create the phase logs directory** so per-KS plans don't fail on first write.

Purpose: Without this plan, (a) every `p1.ksXX.bare` ledger entry produced by Plans 01-08 and 10 would be contaminated by all default-on engines (defeats per-plan isolation), (b) per-KS code-change A/Bs would be no-op same-code comparisons, (c) `bare_config_dict()` wouldn't actually produce a bare config (top-level gates left enabled), (d) Plan 11's mean-bias success criterion would have no data path, and (e) Plan 11's aggregate comparison would have no frozen reference. All five failures were called out by Codex as HIGH-severity blockers across Cycles 1 and 2 of `01-REVIEWS.md`.

Output: a backward-compatible `--arm-b-base` CLI flag on `validate.py`; an exhaustive tested `bare_config_dict()` helper; a `phase1_ks_flags:` config block + `get_phase1_ks_flags()` loader shim; an extended ledger schema (`SeasonMetrics.stat_mean_bias`, schema v5); two pinned Phase-0 ledger entries (now including mean bias); a `PROJECT-PHASE0-FROZEN.md` doc; and the phase logs directory.

This plan is dependency-blocking for ALL other Phase 1 plans (01-11). It must land first.

**Wave-internal task sequencing (REVISED Cycle 3 — order matters):**

1. Task 1 — define `bare_config_dict()` helper (depends on knowing the KS-flag list, but the list is hardcoded in the helper itself; safe to land first)
2. Task 2 — unit tests for the helper
3. Task 3 — wire `--arm-b-base` flag into `validate.py`
4. **Task 8 (NEW Cycle 3)** — add `phase1_ks_flags:` block to `defaults.yaml` + `get_phase1_ks_flags()` shim. MUST land before Task 4 because Task 4's hard-gate test asserts that bare_config_dict produces ALL None engines, which requires the KS flags to exist (otherwise the helper's `try/except` skips them silently and the test still passes — but for the wrong reason).
5. Task 4 — HARD-GATE integration tests (incl. Test 7 `test_bare_config_dict_produces_all_None_engines`, Tests 8 + 9 for KS-flag coverage). If Test 7 fails, return to Task 1 and extend the helper.
6. **Task 9 (NEW Cycle 3)** — extend `SeasonMetrics.stat_mean_bias` + bump ledger schema 4 → 5 + wire `validate.py` to write the field. MUST land before Task 6 because Task 6's `phase0.baseline.full` ledger entry needs to be written under schema v5 with the new field populated (otherwise Plan 11 Task 1's preflight will reject it).
7. Task 5 — create logs directory
8. Task 6 — pin Phase-0 baseline ledger entries (now under schema v5; freeze doc captures QB pass_yards mean bias from the new field)
9. Task 7 — promotion-state SUMMARY commit
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/REQUIREMENTS.md
@.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-CONTEXT.md
@.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-RESEARCH.md
@.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-REVIEWS.md
@scripts/validate.py
@src/fantasy_sim/validation/config.py
@src/fantasy_sim/validation/ledger.py

<interfaces>
**Current behavior of `scripts/validate.py` (lines 1040-1075):**

```python
if args.baseline == "bare":
    arm_a_configs = build_bare_engine_configs()
    arm_a_ensemble_config = None
else:
    arm_a_configs = build_engine_configs(defaults)
    arm_a_ensemble_config = load_ensemble_config(defaults)
    # ... ensemble guard ...

if args.overrides:
    arm_b_dict = apply_overrides(defaults, args.overrides)
else:
    arm_b_dict = defaults
arm_b_configs = build_engine_configs(arm_b_dict)
```

The buglet: when `--baseline bare`, Arm A is bare BUT Arm B always begins from `defaults`. So `--baseline bare --set X.enabled=true` actually compares `(bare) vs (defaults + X)` — contaminated by all default-on engines.

**Target behavior (post-extension):**

```python
# Arm A construction (UNCHANGED):
if args.baseline == "bare":
    arm_a_configs = build_bare_engine_configs()
    arm_a_ensemble_config = None
else:
    arm_a_configs = build_engine_configs(defaults)
    arm_a_ensemble_config = load_ensemble_config(defaults)
    # ... ensemble guard ...

# Arm B construction (NEW: branches on --arm-b-base):
if args.arm_b_base == "bare":
    if args.overrides:
        arm_b_dict = apply_overrides(bare_config_dict(defaults), args.overrides)
        arm_b_configs = build_engine_configs(arm_b_dict)
        arm_b_ensemble_config = load_ensemble_config(arm_b_dict)
    else:
        arm_b_dict = bare_config_dict(defaults)
        arm_b_configs = build_bare_engine_configs()
        arm_b_ensemble_config = None
else:  # arm_b_base == "defaults" (current behavior)
    if args.overrides:
        arm_b_dict = apply_overrides(defaults, args.overrides)
    else:
        arm_b_dict = defaults
    arm_b_configs = build_engine_configs(arm_b_dict)
    arm_b_ensemble_config = load_ensemble_config(arm_b_dict)
    # ... existing ensemble guard ...
```

**The `bare_config_dict(defaults)` helper** (NEW in `src/fantasy_sim/validation/config.py`):

Returns a deepcopy of `defaults` with every engine's `enabled` leaf flag forced to `false` and ensemble sub-engines disabled. The helper preserves the dict structure so `apply_overrides()` can locate the same leaf paths the user requests via `--set` (e.g., `--set pff.team_context.enabled=true` flips just that leaf on top of the otherwise-bare config).

Engines to disable in `bare_config_dict()` (must enumerate based on `build_bare_engine_configs()` keys at `validation/config.py:141-159`):
- `pff.tier_engine.enabled` (sets all PFF sub-engines that flow through tier_engine to off implicitly via tier_engine guard)
- `pff.team_context.enabled`
- `pff.matchup.enabled`
- `pff.coverage.enabled`
- `pff.kicker.enabled`
- `pff.dst_baseline.enabled`
- `pff.rb_scheme_fit.enabled`
- `pff.qb_split.enabled`
- `pff.depth_role.enabled`
- `weather.enabled`
- `vegas.itt.enabled`
- `vegas.spread.enabled`
- `vegas.props.enabled`
- `usage.ngs.enabled`
- `usage.route_rate.enabled`
- `tracking.enabled`
- `availability.enabled`
- `role_trend.enabled`
- `market_history.enabled`
- `game_script.enabled`
- `goal_line_concentration.enabled`
- `td_tendency.enabled`
- `target_selection.enabled`
- `play_call_model.enabled`
- `qb_rushing.scramble.enabled`
- `qb_rushing.designed_runs.enabled`
- `ensemble.enabled` (or set sub-engines: `ensemble.ff_opportunity.enabled`, `ensemble.dynamic_blend.enabled`, `ensemble.residual_calibration.enabled` to false)

The exact key list is what `build_engine_configs()` checks for `.enabled` truthiness when constructing each engine config dataclass. Inspect `load_pff_config`, `load_weather_config`, etc., to confirm.
</interfaces>

</context>

<tasks>

<task type="auto">
  <name>Task 1: Add bare_config_dict() helper to validation/config.py</name>
  <files>src/fantasy_sim/validation/config.py</files>
  <read_first>
    - src/fantasy_sim/validation/config.py (current — lines 94-160)
    - src/fantasy_sim/data/pff/config.py (load_pff_config — to confirm enabled-key paths)
    - config/defaults.yaml (current promoted state — confirm engine flag locations)
  </read_first>
  <action>
Add a new helper function `bare_config_dict(defaults: dict) -> dict` to `src/fantasy_sim/validation/config.py`. Insert AFTER `build_bare_engine_configs()` (around line 160).

**REVISED Cycle 3 (Codex Cycle-2 NEW HIGH #2 fix):** the helper must enumerate EVERY `.enabled` gate that `build_engine_configs()` (lines 118-138) keys off — including the TOP-LEVEL gates (`pff.enabled`, `vegas.enabled`, `usage.enabled`, etc.). The Cycle-2 omission of top-level gates was the reason HIGH-1 wasn't actually closed. The list below is exhaustive against the current `build_engine_configs` implementation; if a future engine is added to `build_engine_configs`, it MUST also be added here (Task 4 integration test enforces this).

```python
def bare_config_dict(defaults: dict) -> dict:
    """Return a deepcopy of defaults with every .enabled gate forced false.

    Used as the source dict for ``apply_overrides`` when ``--arm-b-base bare`` is set
    on validate.py. Preserves the dict structure so user-requested overrides like
    ``--set pff.team_context.enabled=true`` (or ``--set phase1_ks_flags.ks01_preserve_distribution.enabled=true``)
    can locate the same leaf paths.

    REVISED Cycle 3 (Codex 01-REVIEWS.md NEW HIGH #2 fix): includes BOTH the top-level
    engine gates that build_engine_configs at validation/config.py:118-138 keys off
    AND the sub-engine flags. The earlier (Cycle 2) version omitted the top-level
    gates, which meant a 'bare' base still had pff.enabled=true (etc.), so any
    --set pff.X.enabled=true override gave a config where many other PFF sub-engines
    were still bound by their defaults. Cycle 3 makes this exhaustive.

    REVISED Cycle 3 (Codex 01-REVIEWS.md NEW HIGH #1 fix): also disables every
    phase1_ks_flags.ksXX_*.enabled flag so per-KS bare-isolation A/B can flip
    exactly one flag in Arm B via --set.

    Engines disabled here must match the truthiness checks in ``build_engine_configs()``
    above. The Task 4 integration test asserts this exhaustively (every engine returns
    None from build_engine_configs(bare_config_dict(load_defaults()))).
    """
    config = copy.deepcopy(defaults)

    enabled_keys_to_disable = (
        # === Top-level engine gates (NEW Cycle 3 — fixes Codex Cycle-2 NEW HIGH #2) ===
        # Each of these is what build_engine_configs in validation/config.py:118-138 keys off.
        "pff.enabled",
        "weather.enabled",
        "vegas.enabled",
        "props.enabled",  # Top-level props block (sibling to vegas; distinct from vegas.props.enabled)
        "usage.enabled",
        "tracking.enabled",
        "availability.enabled",
        "role_trend.enabled",
        "market_history.enabled",
        "game_script.enabled",
        "goal_line_concentration.enabled",
        "td_tendency.enabled",
        "target_selection.enabled",
        "play_call_model.enabled",
        # qb_rushing: gate is `scramble.enabled OR designed_runs.enabled`, so disable BOTH
        "qb_rushing.scramble.enabled",
        "qb_rushing.designed_runs.enabled",

        # === PFF sub-engines (Cycle 2 baseline; preserved) ===
        "pff.tier_engine.enabled",
        "pff.team_context.enabled",
        "pff.matchup.enabled",
        "pff.coverage.enabled",
        "pff.kicker.enabled",
        "pff.dst_baseline.enabled",
        "pff.rb_scheme_fit.enabled",
        "pff.qb_split.enabled",
        "pff.depth_role.enabled",
        "pff.depth_role.efficiency.enabled",
        "pff.talent.enabled",
        "pff.ncaa_rookie.enabled",
        "pff.archetypes.enabled",

        # === Vegas sub-engines (Cycle 2 baseline; preserved) ===
        # Note: vegas.props.enabled is the sub-engine flag for the Vegas props integration,
        # distinct from the top-level props.enabled block above.
        "vegas.itt.enabled",
        "vegas.spread.enabled",
        "vegas.props.enabled",

        # === Usage sub-engines (Cycle 2 baseline; preserved) ===
        "usage.ngs.enabled",
        "usage.route_rate.enabled",

        # === Ensemble (Cycle 2 baseline; preserved) ===
        "ensemble.enabled",
        "ensemble.ff_opportunity.enabled",
        "ensemble.dynamic_blend.enabled",
        "ensemble.residual_calibration.enabled",

        # === Phase-1 KS feature flags (NEW Cycle 3 — fixes Codex Cycle-2 NEW HIGH #1) ===
        # Each flag gates one per-KS code change; default false (Task 8 ships defaults.yaml block).
        # Disabling them in bare_config_dict means per-KS bare A/B can flip exactly one in Arm B.
        "phase1_ks_flags.ks01_preserve_distribution.enabled",
        "phase1_ks_flags.ks03_dynamic_yard_anchor.enabled",
        "phase1_ks_flags.ks04_conditional_catch_boost.enabled",
        "phase1_ks_flags.ks05_props_recv_yds_fix.enabled",
        "phase1_ks_flags.ks06_backup_receiver_fix.enabled",
        "phase1_ks_flags.ks07_positional_rz_catch_rate.enabled",
        "phase1_ks_flags.ks15_unclamp_for_td_gate.enabled",
        "phase1_ks_flags.ks32_clock_pass_incomplete_3s.enabled",
    )

    for key_path in enabled_keys_to_disable:
        keys = key_path.split(".")
        target = config
        try:
            for k in keys[:-1]:
                target = target[k]
            if keys[-1] in target:
                target[keys[-1]] = False
        except (KeyError, TypeError):
            # Leaf doesn't exist in this defaults snapshot — engine may not be
            # configured yet. Skip silently; the corresponding load_X_config will
            # produce a disabled instance anyway.
            continue

    return config
```

NOTE on missing keys: we use a try/except for missing keys because `defaults.yaml` may not contain every key in the list (e.g., a newly added engine without a default block, or `phase1_ks_flags` block missing on a defaults snapshot taken before Task 8 lands). The `build_engine_configs()` calls a `load_X_config()` per engine which has its own defaults; the missing-key case is harmless because `apply_overrides` would fail on the missing path anyway when the user provides `--set X.enabled=true`.

NOTE on Task 8 ordering: Task 8 (config + loader shim) must land BEFORE the Task 4 integration test runs the end-to-end engine-coverage assertion, because the integration test must reference the new `phase1_ks_flags` block in `defaults.yaml`. The within-Plan-00 task order is: Task 1 (helper definition) → Task 8 (defaults.yaml block + loader shim) → Task 4 (hard-gate integration test). See updated wave-internal sequencing below.

Run the existing test suite to confirm no regression:

```bash
uv run pytest tests/test_validation/ -v 2>&1 | tail -20
```

EXPECTED: All existing validation tests still pass.

Commit: `feat(01-00): add exhaustive bare_config_dict helper for true-isolation A/B (Cycle 3 — top-level gates + KS flags)`
  </action>
  <verify>
    <automated>grep -c "^def bare_config_dict" src/fantasy_sim/validation/config.py && uv run pytest tests/test_validation/ -v 2>&1 | tail -5</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "^def bare_config_dict" src/fantasy_sim/validation/config.py` returns 1
    - `grep -c "ensemble.dynamic_blend.enabled" src/fantasy_sim/validation/config.py` returns at least 1 (sub-engine list preserved)
    - `grep -c "\"pff.enabled\"" src/fantasy_sim/validation/config.py` returns at least 1 (NEW Cycle 3 — top-level gate now in the disabled-key list)
    - `grep -c "\"vegas.enabled\"" src/fantasy_sim/validation/config.py` returns at least 1 (NEW Cycle 3 — top-level gate)
    - `grep -c "\"usage.enabled\"" src/fantasy_sim/validation/config.py` returns at least 1 (NEW Cycle 3 — top-level gate)
    - `grep -c "\"props.enabled\"" src/fantasy_sim/validation/config.py` returns at least 1 (NEW Cycle 3 — top-level gate)
    - `grep -c "phase1_ks_flags.ks01_preserve_distribution.enabled" src/fantasy_sim/validation/config.py` returns at least 1 (NEW Cycle 3 — KS feature flag)
    - `grep -c "phase1_ks_flags.ks15_unclamp_for_td_gate.enabled" src/fantasy_sim/validation/config.py` returns at least 1 (NEW Cycle 3 — KS feature flag, sanity check that all 8 are listed)
    - `uv run pytest tests/test_validation/ -v 2>&1 | tail -5` shows `passed` with no `failed`
    - Existing `build_engine_configs` and `build_bare_engine_configs` are unchanged
    - `git log -1 --pretty=%s` matches `feat(01-00): add exhaustive bare_config_dict`
  </acceptance_criteria>
  <done>Helper present with top-level gates + KS flags; existing tests still green.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Add unit tests for bare_config_dict and apply_overrides on bare base</name>
  <files>tests/test_validation/test_config.py</files>
  <read_first>
    - src/fantasy_sim/validation/config.py (post-Task 1)
    - tests/test_validation/ (existing test patterns; check if test_config.py already exists)
  </read_first>
  <behavior>
    - **Test 1 (`test_bare_config_dict_disables_pff_team_context`):** call `bare_config_dict(load_defaults())`, assert the returned dict has `["pff"]["team_context"]["enabled"] is False` even though defaults.yaml may have it true.
    - **Test 2 (`test_bare_config_dict_disables_all_engines`):** assert all listed `<engine>.enabled` keys (where present in defaults) are False after `bare_config_dict()`.
    - **Test 3 (`test_bare_config_dict_preserves_non_enabled_keys`):** assert that non-`enabled` config values (e.g., `pff.tier_engine.tier_count`, `weather.wind.thresholds`) are PRESERVED unchanged. Proves we only flip the enabled flags, not the entire config tree.
    - **Test 4 (`test_apply_overrides_on_bare_config_dict_enables_one_engine`):** call `apply_overrides(bare_config_dict(load_defaults()), ["pff.team_context.enabled=true"])`. Assert the result has `pff.team_context.enabled == True` AND every OTHER engine's `enabled == False`. Proves the bare base + targeted override gives a true single-engine isolation config.
    - **Test 5 (`test_bare_config_dict_does_not_mutate_input`):** call `bare_config_dict(d)` and assert the input `d` is not mutated (deepcopy contract).
  </behavior>
  <action>
Create or extend `tests/test_validation/test_config.py`:

```python
"""Tests for validation/config.py helpers used by scripts/validate.py."""

from __future__ import annotations

import copy

import pytest

from fantasy_sim.config.loader import load_defaults
from fantasy_sim.validation.config import (
    apply_overrides,
    bare_config_dict,
    build_bare_engine_configs,
    build_engine_configs,
)


# === KS-Phase1 / D-29 (HIGH-1): bare_config_dict for true-isolation A/B ===

def test_bare_config_dict_disables_pff_team_context():
    defaults = load_defaults()
    bare = bare_config_dict(defaults)
    assert bare["pff"]["team_context"]["enabled"] is False


def test_bare_config_dict_disables_all_engines():
    defaults = load_defaults()
    bare = bare_config_dict(defaults)
    enabled_keys_to_check = [
        ("pff", "tier_engine", "enabled"),
        ("pff", "team_context", "enabled"),
        ("pff", "matchup", "enabled"),
        ("pff", "coverage", "enabled"),
        ("pff", "kicker", "enabled"),
        ("pff", "dst_baseline", "enabled"),
        ("weather", "enabled"),
        ("vegas", "itt", "enabled"),
        ("vegas", "spread", "enabled"),
        ("vegas", "props", "enabled"),
    ]
    for path in enabled_keys_to_check:
        target = bare
        try:
            for k in path[:-1]:
                target = target[k]
            assert target.get(path[-1], False) is False, f"key {'.'.join(path)} not disabled"
        except (KeyError, TypeError):
            # Path missing in defaults — acceptable; bare_config_dict skips silently
            pass


def test_bare_config_dict_preserves_non_enabled_keys():
    defaults = load_defaults()
    bare = bare_config_dict(defaults)
    # Pick a known non-enabled key that exists in the defaults tree.
    # If the test runs and the path is missing, defaults.yaml schema changed — update the test.
    if "pff" in defaults and "tier_engine" in defaults["pff"]:
        tier_engine = defaults["pff"]["tier_engine"]
        bare_tier_engine = bare["pff"]["tier_engine"]
        for key, val in tier_engine.items():
            if key == "enabled":
                continue  # this one IS supposed to flip
            assert bare_tier_engine[key] == val, f"non-enabled key {key} was mutated"


def test_apply_overrides_on_bare_config_dict_enables_one_engine():
    defaults = load_defaults()
    bare = bare_config_dict(defaults)
    isolated = apply_overrides(bare, ["pff.team_context.enabled=true"])

    assert isolated["pff"]["team_context"]["enabled"] is True
    # Spot-check that other engines remain disabled
    if "pff" in isolated and "matchup" in isolated["pff"]:
        assert isolated["pff"]["matchup"].get("enabled", False) is False
    if "weather" in isolated:
        assert isolated["weather"].get("enabled", False) is False


def test_bare_config_dict_does_not_mutate_input():
    defaults = load_defaults()
    snapshot = copy.deepcopy(defaults)
    bare_config_dict(defaults)
    assert defaults == snapshot, "bare_config_dict mutated its input"
```

If `tests/test_validation/test_config.py` already exists, append the new tests to it under a new section header. Otherwise create the file and add the imports + tests block.

Run pytest:

```bash
uv run pytest tests/test_validation/test_config.py -v 2>&1 | tail -15
```

EXPECTED: All 5 tests pass.

Commit: `test(01-00): add tests for bare_config_dict + bare-base override resolution`
  </action>
  <verify>
    <automated>uv run pytest tests/test_validation/test_config.py -v 2>&1 | tail -10</automated>
  </verify>
  <acceptance_criteria>
    - `tests/test_validation/test_config.py` contains the 5 test function definitions
    - `uv run pytest tests/test_validation/test_config.py -v -k bare_config_dict` exits 0 with at least 5 tests passed
    - Existing tests in `tests/test_validation/` remain green
    - `git log -1 --pretty=%s` matches `test(01-00): add tests for bare_config_dict`
  </acceptance_criteria>
  <done>5 tests pass; bare_config_dict + apply_overrides interaction verified.</done>
</task>

<task type="auto">
  <name>Task 3: Wire --arm-b-base flag into scripts/validate.py</name>
  <files>scripts/validate.py</files>
  <read_first>
    - scripts/validate.py (lines 316-350 build_cli, lines 1040-1075 Arm A/B construction)
    - src/fantasy_sim/validation/config.py (post-Task 1 — bare_config_dict)
  </read_first>
  <action>
Modify `scripts/validate.py`:

1. **Add the new flag to `build_cli()` (around line 336, after the existing `--baseline` flag):**

```python
    parser.add_argument(
        "--arm-b-base",
        choices=["defaults", "bare"],
        default="defaults",
        help=(
            "Arm B base config: 'defaults' (current behavior — Arm B = defaults + --set overrides) "
            "or 'bare' (Arm B = bare engines + --set overrides, for true isolation). "
            "Combine with --baseline bare for true (bare) vs (bare + KS) isolation A/B per Phase 1 D-29."
        ),
    )
```

2. **Add `bare_config_dict` to the imports (top of file around line 39-44):**

```python
from fantasy_sim.validation.config import (
    apply_overrides,
    bare_config_dict,
    build_bare_engine_configs,
    build_engine_configs,
    build_game_config_kwargs,
)
```

3. **Replace the Arm B construction block (around lines 1061-1075) with:**

```python
    # Arm B construction (D-29 — HIGH-1 fix from 01-REVIEWS.md):
    # When --arm-b-base bare, Arm B starts from a bare config (all engines disabled)
    # and applies --set overrides on top. Provides true (bare) vs (bare + overrides) isolation.
    if args.arm_b_base == "bare":
        bare_dict = bare_config_dict(defaults)
        if args.overrides:
            arm_b_dict = apply_overrides(bare_dict, args.overrides)
        else:
            arm_b_dict = bare_dict
        arm_b_configs = build_engine_configs(arm_b_dict)
        arm_b_ensemble_config = load_ensemble_config(arm_b_dict)
        if not (
            arm_b_ensemble_config.enabled
            and (
                arm_b_ensemble_config.ff_opportunity.enabled
                or arm_b_ensemble_config.dynamic_blend.enabled
                or arm_b_ensemble_config.residual_calibration.enabled
            )
        ):
            arm_b_ensemble_config = None
    else:
        # Default: Arm B = defaults + overrides (existing behavior, backward compatible)
        if args.overrides:
            arm_b_dict = apply_overrides(defaults, args.overrides)
        else:
            arm_b_dict = defaults
        arm_b_configs = build_engine_configs(arm_b_dict)
        arm_b_ensemble_config = load_ensemble_config(arm_b_dict)
        if not (
            arm_b_ensemble_config.enabled
            and (
                arm_b_ensemble_config.ff_opportunity.enabled
                or arm_b_ensemble_config.dynamic_blend.enabled
                or arm_b_ensemble_config.residual_calibration.enabled
            )
        ):
            arm_b_ensemble_config = None
    coverage_summary = collect_signal_coverage(arm_b_dict, args.seasons)
```

4. **Update the print_header / module docstring** at the top of validate.py to mention the new flag in the Usage block:

```python
"""Unified A/B validation script.

Replaces validate_pff_signal.py and validate_weekly_signal.py.
Runs Arm A (bare baseline or defaults) vs Arm B (defaults + overrides | bare + overrides)
and reports season-level and/or weekly metrics.

Usage:
    uv run python scripts/validate.py --help
    uv run python scripts/validate.py --sims 50 --label "baseline-v1"
    uv run python scripts/validate.py --sims 50 --set usage.ngs.enabled=true --label "test-ngs"
    uv run python scripts/validate.py --sims 50 --baseline defaults --set usage.ngs.enabled=true
    # True isolation (Phase 1 D-29):
    uv run python scripts/validate.py --sims 200 --baseline bare --arm-b-base bare \\
      --set usage.ngs.enabled=true --label "test-ngs-isolated"
    uv run python scripts/validate.py --show-ledger
"""
```

Run a quick smoke test (no full sim — just verifies CLI parses and the new flag is wired):

```bash
uv run python scripts/validate.py --help 2>&1 | grep -E "arm-b-base|--baseline" | head -5
```

EXPECTED: `--arm-b-base {defaults,bare}` appears in help output.

Run the existing test suite to confirm no regression:

```bash
uv run pytest tests/ -v 2>&1 | tail -10
```

EXPECTED: All 1,200+ tests still pass.

Commit: `feat(01-00): wire --arm-b-base flag into validate.py for true-isolation A/B`
  </action>
  <verify>
    <automated>uv run python scripts/validate.py --help 2>&1 | grep -c "arm-b-base"</automated>
  </verify>
  <acceptance_criteria>
    - The verify command returns at least `1` (flag exists in help output)
    - `grep -c "if args.arm_b_base == \"bare\":" scripts/validate.py` returns 1
    - `grep -c "from fantasy_sim.validation.config import" scripts/validate.py` shows the import block updated to include `bare_config_dict`
    - `uv run pytest tests/ -v 2>&1 | tail -5` shows `passed` with no `failed`
    - `git log -1 --pretty=%s` matches `feat(01-00): wire --arm-b-base`
  </acceptance_criteria>
  <done>--arm-b-base flag wired and surfaced in --help; full test suite green.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 4: Add HARD-GATE integration tests for end-to-end --arm-b-base bare flow + exhaustive engine coverage</name>
  <files>tests/test_validation/test_config.py</files>
  <read_first>
    - scripts/validate.py (post-Task 3)
    - src/fantasy_sim/validation/config.py (post-Task 1 — bare_config_dict with top-level gates + KS flags)
    - tests/test_validation/test_config.py (post-Task 2)
    - config/defaults.yaml (post-Task 8 — phase1_ks_flags block must exist)
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-RESEARCH.md (Pattern 7)
  </read_first>
  <behavior>
    - **Test 6 (`test_arm_b_construction_bare_base_with_one_engine_override`):** simulate the exact validate.py Arm B branch by calling `apply_overrides(bare_config_dict(load_defaults()), ["pff.enabled=true", "pff.tier_engine.enabled=true", "pff.team_context.enabled=true"])` then `build_engine_configs(result)`. Assert the result has `pff_config is not None and pff_config.team_context.enabled is True`, while `weather_config is None`, `vegas_config is None`, etc. The test flips BOTH the top-level gate (`pff.enabled`) AND the sub-engine (`pff.team_context.enabled`) — this is the contract callers will use.
    - **Test 7 (`test_bare_config_dict_produces_all_None_engines`) — HARD GATE (REVISED Cycle 3 — Codex Cycle-2 NEW HIGH #2 fix):** call `bare_config_dict(load_defaults())` then `build_engine_configs(...)` with NO overrides. Assert EVERY engine config returns `None`. This is the exhaustive engine-coverage check; if ANY engine is non-None, the helper is incomplete and Task 1's enabled-key list must be extended. The Cycle-2 "loosen the test if the integration test disagrees" escape hatch is REMOVED — this test is now a hard gate and any failure means extending the helper, not the test.
    - **Test 8 (`test_bare_config_dict_disables_all_phase1_ks_flags`) — NEW Cycle 3:** call `bare_config_dict(load_defaults())`, assert that `["phase1_ks_flags"][f]["enabled"] is False` for every flag `f` in (`ks01_preserve_distribution`, `ks03_dynamic_yard_anchor`, `ks04_conditional_catch_boost`, `ks05_props_recv_yds_fix`, `ks06_backup_receiver_fix`, `ks07_positional_rz_catch_rate`, `ks15_unclamp_for_td_gate`, `ks32_clock_pass_incomplete_3s`). Sanity-checks that the per-KS feature flags are honored by the helper.
    - **Test 9 (`test_apply_overrides_on_bare_config_dict_flips_one_phase1_ks_flag`) — NEW Cycle 3:** call `apply_overrides(bare_config_dict(load_defaults()), ["phase1_ks_flags.ks01_preserve_distribution.enabled=true"])`, assert exactly ks01's flag is `True` and the other 7 flags are still `False`. Proves the per-KS flag round-trips through `apply_overrides()`.
  </behavior>
  <action>
Append to `tests/test_validation/test_config.py`:

```python
def test_arm_b_construction_bare_base_with_one_engine_override():
    """End-to-end: bare_config_dict + apply_overrides + build_engine_configs produces a one-engine config.

    REVISED Cycle 3: callers must flip BOTH the top-level gate (pff.enabled) AND the
    sub-engine flag (pff.team_context.enabled) because build_engine_configs at
    validation/config.py:118-138 keys off pff.enabled. This is the canonical contract
    for per-KS isolation A/Bs that need to enable a single PFF sub-engine.
    """
    defaults = load_defaults()
    bare = bare_config_dict(defaults)
    isolated = apply_overrides(
        bare,
        [
            "pff.enabled=true",
            "pff.tier_engine.enabled=true",
            "pff.team_context.enabled=true",
        ],
    )
    configs = build_engine_configs(isolated)

    # PFF config exists and reflects the sub-engine flip
    assert configs["pff_config"] is not None
    assert configs["pff_config"].team_context.enabled is True

    # All other engines should be None
    other_engine_keys = (
        "weather_config",
        "vegas_config",
        "props_config",
        "usage_config",
        "tracking_config",
        "availability_config",
        "role_trend_config",
        "market_history_config",
        "game_script_config",
        "goal_line_concentration_config",
        "td_tendency_config",
        "target_selection_config",
        "play_call_model_config",
        "qb_rushing_config",
    )
    for key in other_engine_keys:
        assert configs.get(key) is None, f"engine {key} should be None on bare base, got {configs.get(key)}"


# === HARD GATE (Cycle 3 — Codex Cycle-2 NEW HIGH #2 fix) ===

def test_bare_config_dict_produces_all_None_engines():
    """HARD GATE: bare_config_dict(load_defaults()) must produce a config where
    EVERY engine returns None from build_engine_configs.

    REVISED Cycle 3 (replaces Cycle-2 'loosen the test' escape hatch):
    if this test fails, bare_config_dict is incomplete. EXTEND THE HELPER (add
    the missing top-level gate or sub-engine flag to the enabled_keys_to_disable
    tuple), DO NOT loosen this test. The Cycle-2 disposition explicitly allowed
    'loosen the test' as a fallback; Codex Cycle-2 NEW HIGH #2 flagged that as
    the reason HIGH-1 wasn't actually closed. Cycle 3 forbids the escape hatch.
    """
    defaults = load_defaults()
    bare = bare_config_dict(defaults)
    configs = build_engine_configs(bare)

    # Every engine must be None — no exceptions
    all_engine_keys = (
        "pff_config",
        "weather_config",
        "vegas_config",
        "props_config",
        "usage_config",
        "tracking_config",
        "availability_config",
        "role_trend_config",
        "market_history_config",
        "game_script_config",
        "goal_line_concentration_config",
        "td_tendency_config",
        "target_selection_config",
        "play_call_model_config",
        "qb_rushing_config",
    )
    failures = []
    for key in all_engine_keys:
        if configs.get(key) is not None:
            failures.append(key)
    assert not failures, (
        f"bare_config_dict() is INCOMPLETE — engines still active after the helper: {failures}. "
        f"Fix bare_config_dict in src/fantasy_sim/validation/config.py by adding the missing "
        f"top-level .enabled gate or sub-engine flag to the enabled_keys_to_disable tuple. "
        f"DO NOT loosen this test (Cycle 3 acceptance contract; see plan 00 Task 4)."
    )


# === NEW Cycle 3 — Phase-1 KS feature flag coverage ===

def test_bare_config_dict_disables_all_phase1_ks_flags():
    """All 8 Phase-1 KS feature flags must be False after bare_config_dict()."""
    defaults = load_defaults()
    bare = bare_config_dict(defaults)
    ks_flags = bare.get("phase1_ks_flags", {})
    expected_flags = (
        "ks01_preserve_distribution",
        "ks03_dynamic_yard_anchor",
        "ks04_conditional_catch_boost",
        "ks05_props_recv_yds_fix",
        "ks06_backup_receiver_fix",
        "ks07_positional_rz_catch_rate",
        "ks15_unclamp_for_td_gate",
        "ks32_clock_pass_incomplete_3s",
    )
    for flag in expected_flags:
        block = ks_flags.get(flag, {})
        assert block.get("enabled", True) is False, (
            f"phase1_ks_flags.{flag}.enabled is {block.get('enabled')}, expected False"
        )


def test_apply_overrides_on_bare_config_dict_flips_one_phase1_ks_flag():
    """Per-KS bare-isolation A/B contract: bare base + one --set flips exactly one KS flag."""
    defaults = load_defaults()
    bare = bare_config_dict(defaults)
    isolated = apply_overrides(
        bare,
        ["phase1_ks_flags.ks01_preserve_distribution.enabled=true"],
    )
    assert isolated["phase1_ks_flags"]["ks01_preserve_distribution"]["enabled"] is True
    # Other 7 flags must still be False
    for flag in (
        "ks03_dynamic_yard_anchor",
        "ks04_conditional_catch_boost",
        "ks05_props_recv_yds_fix",
        "ks06_backup_receiver_fix",
        "ks07_positional_rz_catch_rate",
        "ks15_unclamp_for_td_gate",
        "ks32_clock_pass_incomplete_3s",
    ):
        assert isolated["phase1_ks_flags"][flag]["enabled"] is False, (
            f"phase1_ks_flags.{flag} should still be False, got {isolated['phase1_ks_flags'][flag]}"
        )
```

Run pytest:

```bash
uv run pytest tests/test_validation/test_config.py -v -k "arm_b_construction or all_None or phase1_ks" 2>&1 | tail -20
```

EXPECTED: All 4 tests pass. If `test_bare_config_dict_produces_all_None_engines` FAILS, Task 1's enabled-key list is incomplete — extend it (do NOT modify the test). Iterate Task 1 → Task 4 until the hard gate passes.

Commit: `test(01-00): hard-gate integration tests for bare_config_dict (Cycle 3 — exhaustive engine coverage + KS flags)`
  </action>
  <verify>
    <automated>uv run pytest tests/test_validation/test_config.py -v -k "arm_b_construction or all_None or phase1_ks" 2>&1 | tail -10</automated>
  </verify>
  <acceptance_criteria>
    - `tests/test_validation/test_config.py` contains `def test_arm_b_construction_bare_base_with_one_engine_override`
    - `tests/test_validation/test_config.py` contains `def test_bare_config_dict_produces_all_None_engines` (the HARD GATE)
    - `tests/test_validation/test_config.py` contains `def test_bare_config_dict_disables_all_phase1_ks_flags`
    - `tests/test_validation/test_config.py` contains `def test_apply_overrides_on_bare_config_dict_flips_one_phase1_ks_flag`
    - `uv run pytest tests/test_validation/test_config.py -v -k "all_None"` exits 0 (the hard gate passes — bare base produces ALL None engines)
    - `uv run pytest tests/test_validation/test_config.py -v -k "phase1_ks"` exits 0 (both KS-flag tests pass)
    - `git log -1 --pretty=%s` matches `test(01-00): hard-gate integration tests`
    - **NO escape hatch:** the Cycle-2 "Loosen the test if the dependency disagrees" instruction has been REMOVED from the plan. If `test_bare_config_dict_produces_all_None_engines` fails, the helper is the bug, not the test.
  </acceptance_criteria>
  <done>Integration test in place; hard gate enforced; per-KS-flag round-trip verified.</done>
</task>

<task type="auto">
  <name>Task 8 (NEW Cycle 3): Add phase1_ks_flags block to config/defaults.yaml + get_phase1_ks_flags() loader shim</name>
  <files>config/defaults.yaml,src/fantasy_sim/config/loader.py</files>
  <read_first>
    - config/defaults.yaml (current top-level structure to find a sensible insertion point — recommend just before `pff:` block)
    - src/fantasy_sim/config/loader.py (existing load_defaults() pattern + any get_X helpers)
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-RESEARCH.md (Pattern 4b for the full flag list and rationale)
  </read_first>
  <action>
**REVISED Cycle 3 (Codex Cycle-2 NEW HIGH #1 fix):** add a new `phase1_ks_flags:` block to `config/defaults.yaml` with one feature flag per per-KS code change. Default `enabled: false` for every flag — this preserves every existing test and validation run because the legacy code path stays the default until each KS plan's promotion commit flips its flag's default to `true`.

1. Edit `config/defaults.yaml`. Insert this block at the TOP of the file (before any other engine block; it's a sibling to `pff:`, `vegas:`, `weather:`, etc.):

```yaml
# Phase 1 KS code-change feature flags (added Cycle 3 — see RESEARCH.md Pattern 4b).
# Each flag gates one per-KS code change so per-KS A/B can perform a real (legacy)
# vs (new) two-arm comparison via `--set phase1_ks_flags.ksXX_<name>.enabled=true`.
# Default false everywhere; per-KS promotion commits flip the flag to `true` after
# the A/B passes hard floor + promotion bar.
phase1_ks_flags:
  ks01_preserve_distribution:
    enabled: false   # KS-01 — _tackled_short_preserve_distribution variant in play_resolver.py
  ks03_dynamic_yard_anchor:
    enabled: false   # KS-03 — _apply_matchup/_apply_coverage use np.mean(<dist>) instead of *10.0
  ks04_conditional_catch_boost:
    enabled: false   # KS-04 — CATCH_YARDS_BOOST = 1.5 only when _clamp_yards would fire
    boost_value: 1.5
  ks05_props_recv_yds_fix:
    enabled: false   # KS-05 — _apply_recv_yds magnitude fix + DEFAULT_TEAM_PASS_YDS=240
    default_team_pass_yds: 240.0
  ks06_backup_receiver_fix:
    enabled: false   # KS-06 — completed-play filter + integer fallback (5,18) + MIN_PLAYER_PLAYS=3
    min_player_plays: 3
    fallback_low: 5
    fallback_high: 18
  ks07_positional_rz_catch_rate:
    enabled: false   # KS-07 — positional RZ_CATCH_RATE_MODIFIERS dict
    rates:
      WR: 0.92
      TE: 0.95
      RB: 0.85
  ks15_unclamp_for_td_gate:
    enabled: false   # KS-15 — min(yard_line, sample) clamp + un-clamped sample drives TD gate
  ks32_clock_pass_incomplete_3s:
    enabled: false   # KS-32 — CLOCK_PASS_INCOMPLETE = 3 (only set if measurement motivates)
```

2. Add `get_phase1_ks_flags()` to `src/fantasy_sim/config/loader.py` (locate the existing `load_defaults()` function and put the helper just below it):

```python
def get_phase1_ks_flags() -> dict:
    """Return the phase1_ks_flags block from the loaded defaults.yaml.

    Used by per-KS code-change sites to branch on whether the new code path is
    enabled. Read at module import time (not per call) for performance — flag
    flips during a single Python process require a process restart anyway, since
    validate.py's two arms are a single process.

    Returns an empty dict if the block is missing (so callers' `.get(...).get('enabled', False)`
    chains stay defensive against older defaults snapshots that pre-date Cycle 3).
    """
    defaults = load_defaults()
    return defaults.get("phase1_ks_flags", {})
```

3. Verify the load + parse round-trip:

```bash
uv run python -c "
from fantasy_sim.config.loader import load_defaults, get_phase1_ks_flags
defaults = load_defaults()
assert 'phase1_ks_flags' in defaults, 'phase1_ks_flags block missing from defaults.yaml'
flags = get_phase1_ks_flags()
expected = ('ks01_preserve_distribution', 'ks03_dynamic_yard_anchor', 'ks04_conditional_catch_boost',
            'ks05_props_recv_yds_fix', 'ks06_backup_receiver_fix', 'ks07_positional_rz_catch_rate',
            'ks15_unclamp_for_td_gate', 'ks32_clock_pass_incomplete_3s')
for f in expected:
    assert f in flags, f'flag {f} missing'
    assert flags[f].get('enabled') is False, f'flag {f}.enabled is {flags[f].get(\"enabled\")}, expected False'
print('phase1_ks_flags block OK; all 8 flags present and default false')
"
```

EXPECTED: prints `phase1_ks_flags block OK; all 8 flags present and default false`.

4. Run the full test suite (the new defaults block is purely additive; nothing should break):

```bash
uv run pytest tests/ -v 2>&1 | tail -10
```

EXPECTED: 1,200+ tests pass.

Commit: `feat(01-00): add phase1_ks_flags config block + get_phase1_ks_flags loader (Cycle 3 — feature-gate per-KS code changes)`
  </action>
  <verify>
    <automated>uv run python -c "from fantasy_sim.config.loader import get_phase1_ks_flags; flags = get_phase1_ks_flags(); print(len(flags))"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "^phase1_ks_flags:" config/defaults.yaml` returns 1
    - `grep -cE "^  ks(01|03|04|05|06|07|15|32)_" config/defaults.yaml` returns at least 8 (all 8 flags listed under the block)
    - `grep -c "^def get_phase1_ks_flags" src/fantasy_sim/config/loader.py` returns 1
    - The verify command returns at least `8` (8 flags accessible via the helper)
    - `uv run pytest tests/ -v 2>&1 | tail -5` shows `passed` with no `failed`
    - `git log -1 --pretty=%s` matches `feat(01-00): add phase1_ks_flags`
  </acceptance_criteria>
  <done>phase1_ks_flags block + helper added; backward-compatible (all flags default false); per-KS plans can now branch on `get_phase1_ks_flags()`.</done>
</task>

<task type="auto">
  <name>Task 9 (NEW Cycle 3): Extend SeasonMetrics with stat_mean_bias + bump ledger schema 4 → 5 + wire validate.py to write it</name>
  <files>src/fantasy_sim/validation/ledger.py,scripts/validate.py,tests/test_validation/test_ledger_schema.py</files>
  <read_first>
    - src/fantasy_sim/validation/ledger.py (current SeasonMetrics dataclass + load_ledger backward-compat block)
    - scripts/validate.py (per-position-stat KS computation site — search for `stat_ks` writes; mean bias goes adjacent)
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-RESEARCH.md (Pattern 6 for the schema rationale)
    - .planning/ROADMAP.md §"Phase 1" success criterion 1 (QB pass_yards mean bias evaluation)
  </read_first>
  <action>
**REVISED Cycle 3 (Codex Cycle-2 NEW HIGH #3 fix):** Phase-1 success criterion 1 ("QB pass_yards mean bias narrowed from ~−28 yd/g to within ±10 yd/g") cannot be evaluated from the current ledger because `SeasonMetrics` does not carry mean bias. Cycle 3 adds it.

1. Extend `SeasonMetrics` in `src/fantasy_sim/validation/ledger.py`:

```python
@dataclass
class SeasonMetrics:
    """Per-season, per-arm metrics."""

    test_season: int
    arm_a_rank_corr: dict[str, float]
    arm_b_rank_corr: dict[str, float]
    arm_a_weekly_mae: float
    arm_b_weekly_mae: float
    arm_a_season_mae: float
    arm_b_season_mae: float
    arm_a_calibration: float
    arm_b_calibration: float
    weekly_fpts_ks: dict[str, float | int] = field(default_factory=dict)
    stat_ks: dict[str, dict[str, dict[str, float | int]]] = field(default_factory=dict)
    # NEW Cycle 3 (Codex 01-REVIEWS.md NEW HIGH #3): per-position-stat mean bias.
    # Shape: {position: {stat_name: {"arm_a_bias": float, "arm_b_bias": float,
    #                                 "bias_delta": float, "n": int}}}
    # bias = mean(projected_per_game) - mean(actual_per_game) over the season.
    # Plan 11 uses stat_mean_bias["QB"]["pass_yards"]["arm_b_bias"] to evaluate
    # success criterion 1.
    stat_mean_bias: dict[str, dict[str, dict[str, float | int]]] = field(default_factory=dict)
```

2. Bump the schema version constant in the same file:

```python
# Was: CURRENT_LEDGER_SCHEMA_VERSION = 4
CURRENT_LEDGER_SCHEMA_VERSION = 5  # Cycle 3 — added SeasonMetrics.stat_mean_bias
```

3. Update `load_ledger()` for backward compatibility — old entries (schema_version 4 or earlier) lack `stat_mean_bias`. The `dataclass` `field(default_factory=dict)` means new instances get an empty dict if the JSON doesn't have the key, but `load_ledger` currently does `SeasonMetrics(**sr)` which would fail if `sr` had unexpected keys (but is fine if `sr` is missing keys with defaults). Add an explicit setdefault for safety:

```python
def load_ledger(path: Path = DEFAULT_LEDGER_PATH) -> list[LedgerEntry]:
    # ... existing loop ...
    for item in raw:
        season_results = []
        for sr in item.get("season_results", []):
            sr = dict(sr)
            sr["weekly_fpts_ks"] = _normalize_weekly_fpts_ks(
                sr.get("weekly_fpts_ks", {})
            )
            sr.setdefault("stat_mean_bias", {})  # NEW Cycle 3 — backward compat for pre-v5 entries
            season_results.append(SeasonMetrics(**sr))
        # ... rest unchanged ...
```

4. Wire `validate.py` to compute and write per-position-stat mean bias alongside `stat_ks`. Locate the per-season metrics-collection site in `validate.py` (search for `stat_ks=` or `weekly_fpts_ks=` writes — the mean-bias computation goes right next to it). The computation:

```python
# Parallel to stat_ks computation: for each (position, stat) slice, compute mean bias.
# arm_a_bias = mean(projected_per_game_arm_a) - mean(actual_per_game)
# arm_b_bias = mean(projected_per_game_arm_b) - mean(actual_per_game)
# bias_delta = arm_b_bias - arm_a_bias (negative = bias narrowed)
stat_mean_bias = {}
for pos in ("QB", "RB", "WR", "TE"):
    stat_mean_bias[pos] = {}
    for stat in stats_for_position(pos):  # the same iteration used by stat_ks
        proj_a_per_game = ...  # from per-game projection rows for arm A
        proj_b_per_game = ...  # from per-game projection rows for arm B
        actual_per_game = ...  # from per-game actuals
        if len(actual_per_game) == 0:
            continue
        arm_a_bias = float(np.mean(proj_a_per_game) - np.mean(actual_per_game))
        arm_b_bias = float(np.mean(proj_b_per_game) - np.mean(actual_per_game))
        stat_mean_bias[pos][stat] = {
            "arm_a_bias": arm_a_bias,
            "arm_b_bias": arm_b_bias,
            "bias_delta": arm_b_bias - arm_a_bias,
            "n": int(len(actual_per_game)),
        }

# Pass into SeasonMetrics constructor:
season_metrics = SeasonMetrics(
    # ... existing args ...
    stat_ks=stat_ks,
    stat_mean_bias=stat_mean_bias,  # NEW Cycle 3
)
```

NOTE: the exact variable names for `proj_a_per_game`, `proj_b_per_game`, and `actual_per_game` depend on the existing `validate.py` collection structure. The implementer should mirror exactly the same iteration pattern used by `stat_ks` — both metrics consume the same per-position-stat slice; the only difference is the aggregation function (KS vs signed mean delta).

5. Add tests in a new file `tests/test_validation/test_ledger_schema.py`:

```python
"""Tests for the Cycle-3 SeasonMetrics.stat_mean_bias schema bump."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from fantasy_sim.validation.ledger import (
    CURRENT_LEDGER_SCHEMA_VERSION,
    LedgerEntry,
    SeasonMetrics,
    load_ledger,
    save_ledger,
)


def test_current_schema_version_is_5():
    assert CURRENT_LEDGER_SCHEMA_VERSION == 5


def test_season_metrics_default_stat_mean_bias_is_empty_dict():
    sm = SeasonMetrics(
        test_season=2024,
        arm_a_rank_corr={"QB": 0.5},
        arm_b_rank_corr={"QB": 0.55},
        arm_a_weekly_mae=5.0,
        arm_b_weekly_mae=4.8,
        arm_a_season_mae=20.0,
        arm_b_season_mae=19.5,
        arm_a_calibration=0.95,
        arm_b_calibration=0.96,
    )
    assert sm.stat_mean_bias == {}


def test_season_metrics_stat_mean_bias_round_trip():
    """Round-trip a SeasonMetrics with stat_mean_bias through save_ledger / load_ledger."""
    sm = SeasonMetrics(
        test_season=2024,
        arm_a_rank_corr={"QB": 0.5},
        arm_b_rank_corr={"QB": 0.55},
        arm_a_weekly_mae=5.0,
        arm_b_weekly_mae=4.8,
        arm_a_season_mae=20.0,
        arm_b_season_mae=19.5,
        arm_a_calibration=0.95,
        arm_b_calibration=0.96,
        stat_mean_bias={
            "QB": {
                "pass_yards": {
                    "arm_a_bias": -28.5,
                    "arm_b_bias": -8.2,
                    "bias_delta": 20.3,
                    "n": 540,
                }
            }
        },
    )
    entry = LedgerEntry(
        label="test.cycle3",
        timestamp="2026-04-26T00:00:00Z",
        sims=200,
        test_seasons=[2024],
        training_years=4,
        scoring="ppr",
        baseline="bare",
        overrides=[],
        config_snapshot={},
        season_results=[sm],
        schema_version=5,
    )
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "ledger.json"
        save_ledger(path, [entry])
        loaded = load_ledger(path)
    assert len(loaded) == 1
    assert loaded[0].season_results[0].stat_mean_bias["QB"]["pass_yards"]["arm_b_bias"] == -8.2


def test_load_ledger_backward_compat_old_entry_without_stat_mean_bias():
    """Pre-v5 entries (no stat_mean_bias key) load with stat_mean_bias defaulted to empty dict."""
    old_entry_dict = {
        "label": "phase0.legacy",
        "timestamp": "2026-01-01T00:00:00Z",
        "sims": 200,
        "test_seasons": [2024],
        "training_years": 4,
        "scoring": "ppr",
        "baseline": "bare",
        "overrides": [],
        "config_snapshot": {},
        "season_results": [
            {
                "test_season": 2024,
                "arm_a_rank_corr": {"QB": 0.5},
                "arm_b_rank_corr": {"QB": 0.55},
                "arm_a_weekly_mae": 5.0,
                "arm_b_weekly_mae": 4.8,
                "arm_a_season_mae": 20.0,
                "arm_b_season_mae": 19.5,
                "arm_a_calibration": 0.95,
                "arm_b_calibration": 0.96,
                "weekly_fpts_ks": {},
                "stat_ks": {},
                # NOTE: no stat_mean_bias — pre-v5 entry
            }
        ],
        "schema_version": 4,
    }
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "ledger.json"
        path.write_text(json.dumps([old_entry_dict]))
        loaded = load_ledger(path)
    assert len(loaded) == 1
    assert loaded[0].season_results[0].stat_mean_bias == {}
```

6. Run the new tests + the full suite:

```bash
uv run pytest tests/test_validation/test_ledger_schema.py -v 2>&1 | tail -10
uv run pytest tests/ -v 2>&1 | tail -5
```

EXPECTED: all 4 new tests pass; full 1,200+ suite still green.

Commit: `feat(01-00): extend SeasonMetrics with stat_mean_bias + bump ledger schema 4→5 (Cycle 3 — Codex NEW HIGH #3 fix)`
  </action>
  <verify>
    <automated>uv run pytest tests/test_validation/test_ledger_schema.py -v 2>&1 | tail -5 && grep -c "stat_mean_bias" src/fantasy_sim/validation/ledger.py</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "stat_mean_bias" src/fantasy_sim/validation/ledger.py` returns at least 3 (dataclass field + setdefault + docstring)
    - `grep -c "CURRENT_LEDGER_SCHEMA_VERSION = 5" src/fantasy_sim/validation/ledger.py` returns 1
    - `grep -c "stat_mean_bias" scripts/validate.py` returns at least 1 (write site)
    - `tests/test_validation/test_ledger_schema.py` contains all 4 test functions (`test_current_schema_version_is_5`, `test_season_metrics_default_stat_mean_bias_is_empty_dict`, `test_season_metrics_stat_mean_bias_round_trip`, `test_load_ledger_backward_compat_old_entry_without_stat_mean_bias`)
    - `uv run pytest tests/test_validation/test_ledger_schema.py -v` exits 0 with all 4 tests passed
    - `uv run pytest tests/ -v 2>&1 | tail -5` shows `passed` with no `failed`
    - `git log -1 --pretty=%s` matches `feat(01-00): extend SeasonMetrics`
  </acceptance_criteria>
  <done>SeasonMetrics extended; schema bumped 4→5; validate.py writes the new field; backward-compat verified; full suite green.</done>
</task>

<task type="auto">
  <name>Task 5: Create logs directory + .gitkeep for the phase</name>
  <files>.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/.gitkeep</files>
  <read_first>
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/ (verify logs/ doesn't exist or is empty)
  </read_first>
  <action>
Per D-43, ensure the phase logs directory exists before any KS plan attempts to write to it.

```bash
mkdir -p .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs
touch .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/.gitkeep
```

Commit: `chore(01-00): create phase logs directory`
  </action>
  <verify>
    <automated>test -d .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs && test -f .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/.gitkeep && echo OK</automated>
  </verify>
  <acceptance_criteria>
    - `test -d .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs && test -f .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/.gitkeep && echo OK` outputs `OK`
    - `git log -1 --pretty=%s` matches `chore(01-00): create phase logs`
  </acceptance_criteria>
  <done>Logs directory tracked in git.</done>
</task>

<task type="auto">
  <name>Task 6: Pin Phase-0 baseline ledger entries (phase0.baseline.full and phase0.baseline.bare)</name>
  <files>(no source modifications — runs validate.py twice and writes a doc)</files>
  <read_first>
    - scripts/validate.py (post-Task 3 — has --arm-b-base flag)
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-CONTEXT.md (D-32b)
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-RESEARCH.md (Pattern 3 revised)
  </read_first>
  <action>
Per D-32b, run the two pinning passes against the current pre-Phase-1 promoted defaults.

```bash
# Pin 1: Arm A = bare, Arm B = current promoted defaults (NO --set, NO --arm-b-base bare)
# This entry's Arm B fields ARE the pre-Phase-1 reference metrics for Plan 11 to compare against.
uv run python scripts/validate.py \
  --sims 200 --seasons 2022 2023 2024 --scoring ppr \
  --positions QB RB WR TE \
  --baseline bare \
  --label "phase0.baseline.full" \
  2>&1 | tee .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/phase0.baseline.full.log

# Pin 2: Arm A = bare, Arm B = bare (sanity check — should yield ~0 delta on all metrics)
# Confirms the --arm-b-base bare branch is correctly wired (Arm A == Arm B implementation match).
uv run python scripts/validate.py \
  --sims 200 --seasons 2022 2023 2024 --scoring ppr \
  --positions QB RB WR TE \
  --baseline bare --arm-b-base bare \
  --label "phase0.baseline.bare" \
  2>&1 | tee .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/phase0.baseline.bare.log

# Inspect both ledger entries
uv run python scripts/validate.py --show-ledger | grep -E "phase0\.baseline\.(full|bare)"
```

The first run (`phase0.baseline.full`) is the canonical Phase-0 reference. The second run (`phase0.baseline.bare`) is a self-consistency check; both Arms should yield identical metrics (within Monte-Carlo noise, since seeds are CRC32-shared between arms — see `validate.py:81 SEED_MODE`).

Now write the freeze doc. Create `.planning/PROJECT-PHASE0-FROZEN.md`:

```markdown
# Phase-0 Frozen Baseline Reference

**Pinned:** 2026-04-26 (Wave 0 of Phase 1 — Plan 00 Task 6)
**Defaults snapshot commit:** $(git rev-parse HEAD)  <!-- replace with the actual SHA at run time -->
**Validation command:** validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --label phase0.baseline.full
**Ledger entries:** phase0.baseline.full, phase0.baseline.bare

## Why this exists

Per `01-REVIEWS.md` HIGH-4 and the revised D-32 in CONTEXT.md, Phase 1's
end-of-phase aggregate validation (Plan 11) needs a frozen reference to compare
against. This document captures that reference and the exact validation command
that produced it.

## Headline metrics (from phase0.baseline.full Arm B)

(To be filled in after Task 6 ledger inspection — operator copies the printed
ledger row here.)

| Metric | Value |
|--------|-------|
| QB rank_corr (PPR) | ... |
| RB rank_corr (PPR) | ... |
| WR rank_corr (PPR) | ... |
| TE rank_corr (PPR) | ... |
| Aggregate rank_corr | ... |
| Aggregate weekly_mae | ... |
| Aggregate season_mae | ... |
| QB pass_yards KS | ... |
| WR receiving_yards KS | ... |
| RB rush_yards KS | ... |
| QB pass_yards mean bias (yd/g) | ... (NEW Cycle 3 — read from stat_mean_bias["QB"]["pass_yards"]["arm_b_bias"]; ledger schema v5) |

## Self-consistency check (phase0.baseline.bare)

phase0.baseline.bare ran with Arm A == Arm B (both bare engines). Expected result:
zero delta on rank_corr, MAE, KS for every position. If non-zero delta is observed,
the --arm-b-base bare wiring has a bug — investigate before proceeding to Phase 1
KS work.

| Metric | Δ (Arm B - Arm A) | OK? |
|--------|-------------------|-----|
| Aggregate rank_corr | ... | ... |
| Aggregate weekly_mae | ... | ... |

## Plan 11 contract

The end-of-phase aggregate validation (Plan 11) MUST:
1. Run `validate.py --baseline bare --label p1.aggregate.full` AFTER all KS plans
   land and `defaults.yaml` has been updated to reflect promotions.
2. Read the Arm B metrics from BOTH `phase0.baseline.full` (this entry) AND
   `p1.aggregate.full` (the Plan 11 entry).
3. Compute Δ = `p1.aggregate.full Arm B` - `phase0.baseline.full Arm B`.
4. Evaluate Δ against the success criteria in ROADMAP.md `## Phase 1` and the
   hard floor in PROJECT.md.
```

Replace the metric placeholders with the actual values printed by `validate.py --show-ledger`. The ledger row format includes per-position rank_corr, MAE, season_mae, calibration, and per-stat KS — copy the numbers verbatim.

Commit: `chore(01-00): pin Phase-0 baseline ledger entries (phase0.baseline.full, phase0.baseline.bare)`

This is a long-running task (~30-60 min for the two 200-sim runs). Use `--background` if available; otherwise expect the wall-clock budget to be 60-90 min for this task alone.
  </action>
  <verify>
    <automated>uv run python scripts/validate.py --show-ledger 2>&1 | grep -E "phase0\.baseline\.(full|bare)" | wc -l | tr -d ' '</automated>
  </verify>
  <acceptance_criteria>
    - The verify command returns `2` (both ledger entries present)
    - `.planning/PROJECT-PHASE0-FROZEN.md` exists with headline metrics filled in
    - `phase0.baseline.bare` ledger row shows ~zero delta on rank_corr (within ±0.001) and MAE (within ±0.05) — self-consistency check passes
    - `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/phase0.baseline.full.log` exists
    - `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/phase0.baseline.bare.log` exists
    - `git log -1 --pretty=%s` matches `chore(01-00): pin Phase-0 baseline`
  </acceptance_criteria>
  <done>Phase-0 reference pinned; frozen doc written; self-consistency check passes.</done>
</task>

<task type="auto">
  <name>Task 7: Promotion-state commit for Plan 00</name>
  <files>(no source modifications — promotion message + amend if needed)</files>
  <read_first>
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/phase0.baseline.full.log
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/phase0.baseline.bare.log
    - .planning/PROJECT-PHASE0-FROZEN.md
  </read_first>
  <action>
Per D-25 (revised — promotion-state commit per KS plan), create the final promotion commit. Plan 00's promotion summary is captured in a SUMMARY file rather than a separate marker commit (since Tasks 1-6 already committed the substantive work).

Create `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-00-SUMMARY.md`:

```markdown
# Plan 00 Summary — validate.py harness extension + Phase-0 baseline pin

**Promotion state:** PROMOTED
**Phase:** 1 (Bug Fixes, Cheap Calibration & Time-Sensitive Scrape)
**Wave:** 0
**Final commit:** $(git log -1 --pretty=%H)

## What shipped

1. `bare_config_dict()` helper in `src/fantasy_sim/validation/config.py` — produces a
   defaults-shaped dict with every engine's `enabled` flag flipped false. Enables
   `apply_overrides()` to construct a bare-base + targeted override config.
2. `--arm-b-base {defaults,bare}` CLI flag on `scripts/validate.py` — Arm B branches
   on the flag. Default `defaults` preserves backward compatibility.
3. 6 unit + integration tests in `tests/test_validation/test_config.py` covering:
   - Engine-flag flipping
   - Non-enabled key preservation
   - Round-trip with `apply_overrides`
   - Input non-mutation
   - End-to-end with `build_engine_configs`
4. Phase logs directory at `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/`
5. Two pinned Phase-0 baseline ledger entries:
   - `phase0.baseline.full` — Arm A = bare, Arm B = current promoted defaults (the
     canonical reference for Plan 11 aggregate comparison)
   - `phase0.baseline.bare` — Arm A = bare, Arm B = bare (self-consistency check;
     verified ~zero delta)
6. `.planning/PROJECT-PHASE0-FROZEN.md` — captures the defaults snapshot SHA, the
   validation command, and the headline metrics for downstream reference.

## Why this matters (Codex review HIGH-1, HIGH-4)

Without this plan:
- Per-KS `p1.ksXX.bare` ledger entries would compare `(bare) vs (defaults + KS-X)`,
  contaminated by every default-on engine. Codex review flagged this as HIGH-1.
- Plan 11 aggregate validation would compare defaults-vs-defaults (no `--set`),
  recording a no-op snapshot rather than a Phase-0-vs-Phase-1 delta. Codex review
  flagged this as HIGH-4.

Both blockers are now resolved. All Plans 01-08 and 10 use `--baseline bare
--arm-b-base bare` for the bare ledger entry. Plan 11 reads `phase0.baseline.full`
Arm B vs `p1.aggregate.full` Arm B for the end-of-phase delta.

## What's next

Wave 1 plans (Plan 01 KS-01 RZ TD-gate fix, Plan 09 KS-21 alt-line scrape) can
now proceed in parallel. The bare-isolation A/B contract is honored from this
point forward.
```

If a separate marker commit is desired (rather than appending the SUMMARY to the previous commit), use:

```bash
git add .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-00-SUMMARY.md
git commit -m "feat(01-00): KS-Phase1 PROMOTED — validate.py --arm-b-base flag + Phase-0 baseline pin

Wave 0 prerequisite for all per-KS A/B isolation runs in Phase 1.
Closes Codex review HIGH-1 (true-isolation harness) and HIGH-4
(frozen Phase-0 baseline reference for Plan 11 aggregate).

Ledger entries pinned: phase0.baseline.full, phase0.baseline.bare
Frozen doc: .planning/PROJECT-PHASE0-FROZEN.md"
```
  </action>
  <verify>
    <automated>test -f .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-00-SUMMARY.md && grep -c "PROMOTED" .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-00-SUMMARY.md</automated>
  </verify>
  <acceptance_criteria>
    - `test -f .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-00-SUMMARY.md && grep -c "PROMOTED" ...` returns at least `1`
    - SUMMARY contains the standardized "Promotion state:" header
    - `git log -1 --pretty=%s` matches `feat(01-00): KS-Phase1 PROMOTED` OR `chore(01-00): write SUMMARY` (either acceptable depending on whether SUMMARY commit is separate)
  </acceptance_criteria>
  <done>Plan 00 PROMOTED; SUMMARY captures the wave 0 deliverable.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| `validate.py` CLI → user shell | New flag is opt-in; default behavior unchanged. |
| `bare_config_dict` → `defaults` dict input | Deepcopy contract enforced; tests verify no mutation. |
| Pinned ledger entries → downstream Plan 11 | Read-only reference; Plan 11 must not modify or rewrite these entries. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-01-00-01 | T (Tampering) | bare_config_dict input mutation | mitigate | Test 5 asserts deepcopy behavior; existing apply_overrides also deepcopies. |
| T-01-00-02 | I (Information disclosure) | --arm-b-base flag default change | mitigate | Default explicitly `defaults` to preserve backward compatibility for all existing labels (decision_s200, residual-calibration-s200, phase-N-* labels). Existing tests still green. |
| T-01-00-03 | T (Tampering) | Phase-0 baseline ledger entries | mitigate | PROJECT-PHASE0-FROZEN.md captures the SHA + label so accidental rewrite/relabel is detectable. Plan 11 acceptance reads the labeled entries; if they're missing or rewritten, Plan 11 fails its preflight. |
| T-01-00-04 | R (Repudiation) | "I ran A/B isolation" claims by per-KS plans | mitigate | All per-KS plans now invoke `--arm-b-base bare`; the ledger entry's `overrides` and computed delta semantics make the actual comparison auditable. |
| T-01-00-05 | E (Elevation of privilege) | New CLI flag accepting arbitrary values | accept | argparse `choices=["defaults", "bare"]` enforces enum; no shell injection or path traversal vectors. |
</threat_model>

<verification>
- `bare_config_dict` helper exists in `src/fantasy_sim/validation/config.py` AND enumerates every top-level + sub-engine + KS-flag `.enabled` gate (Task 1, REVISED Cycle 3)
- 5 unit tests + 4 integration tests (incl. the HARD GATE `test_bare_config_dict_produces_all_None_engines`) pass in `tests/test_validation/test_config.py` (Tasks 2, 4 — REVISED Cycle 3)
- `--arm-b-base` flag visible in `validate.py --help` output (Task 3)
- Phase logs directory committed (Task 5)
- `phase0.baseline.full` and `phase0.baseline.bare` ledger entries exist with sane self-consistency AND populated `stat_mean_bias` field per the new schema (Task 6, REVISED Cycle 3)
- `.planning/PROJECT-PHASE0-FROZEN.md` written with headline metrics including QB pass_yards mean bias (Task 6)
- Plan 00 SUMMARY captures PROMOTED state (Task 7)
- `phase1_ks_flags:` block in `config/defaults.yaml` with all 8 flags default false; `get_phase1_ks_flags()` helper in `src/fantasy_sim/config/loader.py` (Task 8 NEW Cycle 3)
- `SeasonMetrics.stat_mean_bias` field present; `CURRENT_LEDGER_SCHEMA_VERSION = 5`; backward-compat load tests green (Task 9 NEW Cycle 3)
- 1,200+ existing test suite still green
</verification>

<success_criteria>
- Codex Cycle-1 HIGH-1 (per-KS A/B isolation) is FULLY closed: all per-KS plans now have a true-isolation invocation pattern (`--baseline bare --arm-b-base bare --set phase1_ks_flags.ksXX_<name>.enabled=true`); per-KS code-change A/Bs are no longer no-op same-code comparisons.
- Codex Cycle-1 HIGH-4 (end-of-phase aggregate has a frozen reference) is unblocked: Plan 11 reads `phase0.baseline.full` Arm B as the canonical Phase-0 metric set.
- Codex Cycle-2 NEW HIGH #1 (per-KS code-change A/B is no-op) is FULLY closed: Pattern 4b feature flags introduced in Task 8; per-KS plans (01-07, 10) all use `--set phase1_ks_flags.ksXX_<name>.enabled=true` so Arm B genuinely flips the new code path on.
- Codex Cycle-2 NEW HIGH #2 (`bare_config_dict()` incomplete) is FULLY closed: Task 1's helper enumerates EVERY `.enabled` gate (top-level + sub-engine + KS flags); Task 4's hard-gate integration test enforces this exhaustively. The "loosen the test" escape hatch is REMOVED.
- Codex Cycle-2 NEW HIGH #3 (Plan 11 mean-bias not in ledger schema) is FULLY closed: Task 9 extends `SeasonMetrics.stat_mean_bias` (schema v5); Plan 11 reads it directly from the persisted ledger entry — no side script needed.
- Backward compatibility preserved: existing labels in the ledger and existing test suite still green; pre-v5 ledger entries load with `stat_mean_bias = {}` default.
- Self-consistency check passes: `phase0.baseline.bare` shows ~zero delta on rank_corr (within ±0.001) and MAE (within ±0.05).
</success_criteria>

<output>
After completion, the SUMMARY at `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-00-SUMMARY.md` is the canonical Plan 00 closure document.
</output>

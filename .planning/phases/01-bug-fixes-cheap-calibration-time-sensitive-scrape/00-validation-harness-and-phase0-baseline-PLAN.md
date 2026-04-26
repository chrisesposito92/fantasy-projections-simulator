---
phase: 01-bug-fixes-cheap-calibration-time-sensitive-scrape
plan: 00
type: execute
wave: 0
depends_on: []
files_modified:
  - scripts/validate.py
  - src/fantasy_sim/validation/config.py
  - tests/test_validation/test_config.py
  - .planning/PROJECT-PHASE0-FROZEN.md
autonomous: true
requirements: [ALL_PHASE_1]
must_haves:
  truths:
    - "Per D-29 / D-32b (revised 2026-04-26 — addresses Codex HIGH-1 + HIGH-4): scripts/validate.py is extended with a new --arm-b-base {defaults,bare} flag (default: defaults — preserves backward compatibility). When --arm-b-base bare, Arm B starts from build_bare_engine_configs() and applies --set overrides on top, enabling true (bare) vs (bare + overrides) isolation."
    - "Per D-32b: Phase-0 baseline ledger entries are pinned BEFORE any KS work begins. phase0.baseline.full has Arm A=bare, Arm B=current promoted defaults; phase0.baseline.bare has Arm A=bare, Arm B=bare (self-consistency check, must show ~zero delta)."
    - "Per D-32 (revised): the Phase-0 baseline ledger Arm B metrics are the canonical reference for the end-of-phase aggregate comparison in Plan 11."
    - "The harness extension is backward-compatible — existing labels (decision_s200, residual-calibration-s200, all phase-N-* labels) are unaffected."
    - "Per D-25 (revised): the final commit on this plan uses message format `feat(01-00): KS-Phase1 PROMOTED — validate.py --arm-b-base flag + Phase-0 baseline pin`."
    - "Per D-43: log directory created in Wave 0 — `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/` exists with .gitkeep before any KS plan writes to it."
    - "Existing 1,200+ test suite stays green throughout."
  artifacts:
    - path: "scripts/validate.py"
      provides: "New --arm-b-base {defaults,bare} CLI flag; Arm B config construction branches on it"
      contains: "--arm-b-base"
    - path: "src/fantasy_sim/validation/config.py"
      provides: "Helper to produce a defaults-shaped config dict with all engine.enabled flags forced false (so apply_overrides can locate the same leaf paths)"
      contains: "def bare_config_dict"
    - path: "tests/test_validation/test_config.py"
      provides: "Tests for bare_config_dict and apply_overrides on bare base"
      contains: "def test_bare_config_dict"
    - path: ".planning/PROJECT-PHASE0-FROZEN.md"
      provides: "Phase-0 baseline pin record: defaults.yaml SHA + ledger label + run timestamp + headline metrics"
      contains: "## Phase-0 frozen baseline"
    - path: "results/ab_ledger.json"
      provides: "Two new entries: phase0.baseline.full and phase0.baseline.bare"
      contains: "phase0.baseline.full"
  key_links:
    - from: "all per-KS plans (01-08, 10) bare-isolation A/B runs"
      to: "validate.py --arm-b-base bare"
      via: "the new CLI flag"
      pattern: "--arm-b-base bare"
    - from: "Plan 11 aggregate validation"
      to: "phase0.baseline.full ledger entry"
      via: "ledger Arm B comparison"
      pattern: "phase0.baseline.full"
---

<objective>
Implement the prerequisite Phase 1 infrastructure that the Codex review (`01-REVIEWS.md` HIGH-1 and HIGH-4) flagged as missing:

1. **Extend `scripts/validate.py` with a `--arm-b-base {defaults,bare}` flag** so that per-KS A/B isolation runs can perform a true `(bare) vs (bare + overrides)` comparison, instead of the current `(bare) vs (defaults + overrides)` contamination.
2. **Pin a frozen Phase-0 baseline ledger entry** (`phase0.baseline.full`) representing the current promoted defaults state. This is the reference Plan 11 will compare against to evaluate Phase 1's aggregate progress.
3. **Create the phase logs directory** so per-KS plans don't fail on first write.

Purpose: Without this plan, every `p1.ksXX.bare` ledger entry produced by Plans 01-08 and 10 is contaminated by all default-on engines (defeats per-plan isolation), and Plan 11's aggregate comparison has no frozen reference to differ against (records a no-op snapshot). Both failures were called out by Codex as HIGH-severity blockers in `01-REVIEWS.md`.

Output: a backward-compatible `--arm-b-base` CLI flag on `validate.py`, a tested `bare_config_dict()` helper, two pinned Phase-0 ledger entries, a `PROJECT-PHASE0-FROZEN.md` doc capturing the defaults snapshot, and the phase logs directory.

This plan is dependency-blocking for ALL other Phase 1 plans (01-11). It must land first.
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

```python
def bare_config_dict(defaults: dict) -> dict:
    """Return a deepcopy of defaults with every engine's `enabled` flag forced false.

    Used as the source dict for ``apply_overrides`` when ``--arm-b-base bare`` is set
    on validate.py. Preserves the dict structure so user-requested overrides like
    ``--set pff.team_context.enabled=true`` can locate the same leaf paths.

    Engines disabled here must match the truthiness checks in ``build_engine_configs()``
    above. Add new engines to BOTH this helper and ``build_bare_engine_configs()`` when
    introducing them.
    """
    config = copy.deepcopy(defaults)

    # PFF sub-engines (tier_engine guard implicitly disables most PFF blending)
    for key_path in (
        "pff.tier_engine.enabled",
        "pff.team_context.enabled",
        "pff.matchup.enabled",
        "pff.coverage.enabled",
        "pff.kicker.enabled",
        "pff.dst_baseline.enabled",
        "pff.rb_scheme_fit.enabled",
        "pff.qb_split.enabled",
        "pff.depth_role.enabled",
        # Other engines
        "weather.enabled",
        "vegas.itt.enabled",
        "vegas.spread.enabled",
        "vegas.props.enabled",
        "usage.ngs.enabled",
        "usage.route_rate.enabled",
        "tracking.enabled",
        "availability.enabled",
        "role_trend.enabled",
        "market_history.enabled",
        "game_script.enabled",
        "goal_line_concentration.enabled",
        "td_tendency.enabled",
        "target_selection.enabled",
        "play_call_model.enabled",
        "qb_rushing.scramble.enabled",
        "qb_rushing.designed_runs.enabled",
        "ensemble.enabled",
        "ensemble.ff_opportunity.enabled",
        "ensemble.dynamic_blend.enabled",
        "ensemble.residual_calibration.enabled",
    ):
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

NOTE: We use a try/except for missing keys because `defaults.yaml` may not contain every engine key (e.g., a newly added engine without a default block). The `build_engine_configs()` calls a `load_X_config()` per engine which has its own defaults; the missing-key case is harmless because `apply_overrides` would fail on the missing path anyway when the user provides `--set X.enabled=true`.

Run the existing test suite to confirm no regression:

```bash
uv run pytest tests/test_validation/ -v 2>&1 | tail -20
```

EXPECTED: All existing validation tests still pass.

Commit: `feat(01-00): add bare_config_dict helper for true-isolation A/B in validate.py`
  </action>
  <verify>
    <automated>grep -c "^def bare_config_dict" src/fantasy_sim/validation/config.py && uv run pytest tests/test_validation/ -v 2>&1 | tail -5</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "^def bare_config_dict" src/fantasy_sim/validation/config.py` returns 1
    - `grep -c "ensemble.dynamic_blend.enabled" src/fantasy_sim/validation/config.py` returns at least 1 (the disabled-key list includes ensemble sub-engines)
    - `uv run pytest tests/test_validation/ -v 2>&1 | tail -5` shows `passed` with no `failed`
    - Existing `build_engine_configs` and `build_bare_engine_configs` are unchanged
    - `git log -1 --pretty=%s` matches `feat(01-00): add bare_config_dict`
  </acceptance_criteria>
  <done>Helper present; existing tests still green.</done>
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
  <name>Task 4: Add integration test for end-to-end --arm-b-base bare flow</name>
  <files>tests/test_validation/test_config.py</files>
  <read_first>
    - scripts/validate.py (post-Task 3)
    - src/fantasy_sim/validation/config.py (post-Task 1)
    - tests/test_validation/test_config.py (post-Task 2)
  </read_first>
  <behavior>
    - **Test 6 (`test_arm_b_construction_bare_base_with_one_engine_override`):** simulate the exact validate.py Arm B branch by calling `apply_overrides(bare_config_dict(load_defaults()), ["pff.team_context.enabled=true"])` then `build_engine_configs(result)`. Assert the result dict has `pff_config is not None and pff_config.team_context.enabled is True`, while `weather_config is None`, `vegas_config is None`, etc. — proving the round-trip produces a single-engine config.
  </behavior>
  <action>
Append to `tests/test_validation/test_config.py`:

```python
def test_arm_b_construction_bare_base_with_one_engine_override():
    """End-to-end: bare_config_dict + apply_overrides + build_engine_configs produces a one-engine config."""
    defaults = load_defaults()
    bare = bare_config_dict(defaults)
    isolated = apply_overrides(bare, ["pff.team_context.enabled=true"])
    configs = build_engine_configs(isolated)

    # PFF config should exist (because tier_engine is implicitly off but team_context was flipped on)
    # The exact behavior depends on whether load_pff_config returns a config when ANY sub-engine is on.
    # If load_pff_config requires tier_engine.enabled=true to produce a non-None config, this test
    # will need to flip both tier_engine.enabled AND team_context.enabled.

    # Defensive assertion: the constructed PFF config (if any) reflects team_context being on
    if configs.get("pff_config") is not None:
        # team_context enabled flag should be True on the config dataclass
        assert configs["pff_config"].team_context.enabled is True

    # All other engines should be None (no config dataclass constructed)
    assert configs.get("weather_config") is None
    assert configs.get("vegas_config") is None
    assert configs.get("usage_config") is None
    assert configs.get("tracking_config") is None
    assert configs.get("availability_config") is None
    assert configs.get("role_trend_config") is None
    assert configs.get("market_history_config") is None
    assert configs.get("game_script_config") is None
    assert configs.get("goal_line_concentration_config") is None
    assert configs.get("td_tendency_config") is None
    assert configs.get("target_selection_config") is None
    assert configs.get("play_call_model_config") is None
    assert configs.get("qb_rushing_config") is None
```

If the test reveals that `load_pff_config` requires `pff.tier_engine.enabled=true` for ANY PFF sub-engine to be reflected, the test exposes a config-dependency oddity. The fix in that case is to either:
- Document the dependency in `bare_config_dict` so users know `--set pff.team_context.enabled=true` may also need `--set pff.tier_engine.enabled=true`, OR
- Loosen the test to assert the override flowed into the dict regardless of dataclass construction.

Run pytest:

```bash
uv run pytest tests/test_validation/test_config.py -v -k arm_b_construction 2>&1 | tail -10
```

EXPECTED: Test passes (or surfaces the dependency oddity for documentation).

Commit: `test(01-00): integration test for --arm-b-base bare end-to-end`
  </action>
  <verify>
    <automated>uv run pytest tests/test_validation/test_config.py -v -k arm_b_construction 2>&1 | tail -5</automated>
  </verify>
  <acceptance_criteria>
    - `tests/test_validation/test_config.py` contains `def test_arm_b_construction_bare_base_with_one_engine_override`
    - The test exits 0 (passes) — OR clearly documents in the assertion failure why a config-dependency requires the user to flip more than one engine flag
    - `git log -1 --pretty=%s` matches `test(01-00): integration test`
  </acceptance_criteria>
  <done>Integration test in place; round-trip verified.</done>
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
| QB pass_yards mean bias (yd/g) | ... |

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
- `bare_config_dict` helper exists in `src/fantasy_sim/validation/config.py` (Task 1)
- 5 unit tests + 1 integration test pass in `tests/test_validation/test_config.py` (Tasks 2, 4)
- `--arm-b-base` flag visible in `validate.py --help` output (Task 3)
- Phase logs directory committed (Task 5)
- `phase0.baseline.full` and `phase0.baseline.bare` ledger entries exist with sane self-consistency (Task 6)
- `.planning/PROJECT-PHASE0-FROZEN.md` written with headline metrics (Task 6)
- Plan 00 SUMMARY captures PROMOTED state (Task 7)
- 1,200+ existing test suite still green
</verification>

<success_criteria>
- Codex HIGH-1 (per-KS A/B isolation) is unblocked: all per-KS plans now have a true-isolation invocation pattern (`--baseline bare --arm-b-base bare`).
- Codex HIGH-4 (end-of-phase aggregate has a frozen reference) is unblocked: Plan 11 reads `phase0.baseline.full` Arm B as the canonical Phase-0 metric set.
- Backward compatibility preserved: existing labels in the ledger and existing test suite still green.
- Self-consistency check passes: `phase0.baseline.bare` shows ~zero delta on rank_corr (within ±0.001) and MAE (within ±0.05).
</success_criteria>

<output>
After completion, the SUMMARY at `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-00-SUMMARY.md` is the canonical Plan 00 closure document.
</output>

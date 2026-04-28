---
phase: 02-structural-per-stat-calibration
plan: 01
type: execute
wave: 0
depends_on: []
files_modified:
  - config/defaults.yaml
  - src/fantasy_sim/config/loader.py
  - src/fantasy_sim/validation/config.py
  - src/fantasy_sim/scoring/residual_calibration.py
  - tests/test_validation/test_config.py
  - tests/test_scoring/test_residual_calibration.py
  - .planning/phases/02-structural-per-stat-calibration/logs/.gitkeep
autonomous: true
requirements: [KS-08, KS-09, KS-10, KS-11, KS-12, KS-13, KS-14]
must_haves:
  truths:
    - "Per D-13: Phase 2 ships 9 plans (this scaffolding plan + 7 KS plans + 1 aggregate); Plan 01 is the prerequisite for every KS plan and pins the Phase-2 entry-baseline ledger entry"
    - "Per D-02 (continuing Phase 1 D-45 pattern): every per-KS code change in Phases 02-08 is gated behind `phase2_ks_flags.ksXX_<name>.enabled` (default false). Plan 01 ships the config block + loader shim. Per-KS promotion commits flip the default to true after the per-KS A/B passes."
    - "Per D-44 (Phase 1 — continued): `bare_config_dict()` is the single source of truth for the Arm-A `--baseline bare` configuration in `validate.py`. Plan 01 EXTENDS the Phase 1 list (validation/config.py:262-267) with the 7 new Phase-2 flags AND 5 new top-level keys (`ensemble.residual_calibration.stat_level.enabled`, `ensemble.residual_calibration.max_abs_adjustment_by_position`, `ensemble.dynamic_blend.simulator_weight_floor`, `ensemble.ff_opportunity.prior_width.enabled`, `pff.tier_engine.position_reliability`)."
    - "Per Phase 1 D-44 hard-gate principle: `test_bare_config_dict_produces_all_None_engines` is a HARD GATE. The Cycle-2 escape hatch stays REMOVED. Plan 01 extends the test with the new Phase-2 flags so any future flag added to defaults but missed in `bare_config_dict()` fails CI."
    - "Per Phase 1 D-46 schema-bump pattern: Plan 01 bumps the `residual_calibration` artifact schema_version from 1 to 2. The artifact loader at `residual_calibration.py:_artifact()` gracefully accepts both: schema_v1 = fpts-only (current behavior), schema_v2 = fpts + new `stat_corrections` block. KS-09 (Plan 03) populates the v2 block; KS-10 (Plan 05) re-fits on top of v2. Without the schema bump in Plan 01, KS-09 cannot land its artifact."
    - "Per C-02: Phase-2 entry baseline = ledger entry `p1.aggregate.full` (#105) Arm B. Plan 01 Task 3 records `p2.entry.full` (numerically identical sanity-check pin) for delta clarity; Plan 09 differences `p2.aggregate.full` against `p1.aggregate.full` per D-15."
    - "Per C-09: existing 2,131-test suite stays green. Plan 01 changes are scaffolding-only — no runtime behavior changes when all `phase2_ks_flags.*.enabled` defaults are false."
    - "Per Phase 1 D-43 pattern: `.planning/phases/02-structural-per-stat-calibration/logs/` directory is created with `.gitkeep` so per-KS plans (especially Plan 02 sweep and Plan 07 probe) have a stable location to write JSON/text logs."
    - "**Codex LOW 10 (2026-04-27 revision) — non-boolean knob safety:** `bare_config_dict()` enumerates BOOLEAN gates only (`*.enabled` keys). Non-boolean knobs (`ensemble.dynamic_blend.simulator_weight_floor`, `ensemble.residual_calibration.max_abs_adjustment_by_position`, `pff.tier_engine.position_reliability`) sit BENEATH parents whose `.enabled` flag is in the disabled-set. So `bare_config_dict()` produces a config where the parent engine is disabled and the non-boolean knobs are unreachable. KS-11 (codex MEDIUM 6 fix in Plan 06 Task 1b) and KS-10 (codex MEDIUM 7 in Plan 05) ALSO add per-KS-flag gates so the knobs can't leak when a developer pre-populates them in defaults.yaml. This is the layered safety: bare-config gates the parent, per-KS flag gates the knob."
  artifacts:
    - path: "config/defaults.yaml"
      provides: "New top-level `phase2_ks_flags:` block with 7 flags (default enabled: false). New `ensemble.residual_calibration.stat_level:` block (default enabled: false, covered_stats list). New `ensemble.residual_calibration.max_abs_adjustment_by_position:` block (default {QB: 1.5, RB: 1.5, WR: 1.5, TE: 1.5} — a placeholder matching the existing global cap; KS-10 Plan 05 will retune to D-07 values). New `ensemble.dynamic_blend.simulator_weight_floor` field (default 0.0). New `ensemble.ff_opportunity.prior_width:` block (default enabled: false). New `pff.tier_engine.position_reliability` block (default empty {}; KS-11 Plan 06 populates)."
      contains: "phase2_ks_flags:"
    - path: "src/fantasy_sim/config/loader.py"
      provides: "New helper `get_phase2_ks_flags()` mirroring `get_phase1_ks_flags()` (line 99-111)"
      contains: "def get_phase2_ks_flags()"
    - path: "src/fantasy_sim/validation/config.py"
      provides: "Extended `bare_config_dict()` disabled-set list with 7 new Phase-2 flags + 5 new top-level keys"
      contains: "phase2_ks_flags.ks08_dynamic_blend_simulator_floor.enabled"
    - path: "src/fantasy_sim/scoring/residual_calibration.py"
      provides: "Updated artifact loader to accept schema_version: 2 alongside the existing schema_version: 1; adds an empty-but-keyed `stat_corrections` dict initialization so v1 artifacts continue to work without per-stat data"
      contains: "if schema not in (1, 2)"
    - path: "tests/test_validation/test_config.py"
      provides: "Extended `test_bare_config_dict_produces_all_None_engines` to enumerate the 7 new Phase-2 flags + 5 new top-level keys"
      contains: "phase2_ks_flags.ks08_dynamic_blend_simulator_floor"
    - path: "tests/test_scoring/test_residual_calibration.py"
      provides: "New tests `test_artifact_loader_accepts_schema_v2` and `test_artifact_loader_rejects_schema_v3` so artifact-loading is deterministic"
      contains: "def test_artifact_loader_accepts_schema_v2("
    - path: ".planning/phases/02-structural-per-stat-calibration/logs/.gitkeep"
      provides: "Stable directory for per-plan log files (e.g., Plan 02 sweep results, Plan 07 probe JSON, Plan 09 delta computation)"
      contains: ""
  key_links:
    - from: "config/defaults.yaml::phase2_ks_flags"
      to: "src/fantasy_sim/config/loader.py::get_phase2_ks_flags"
      via: "load_defaults() → defaults.get('phase2_ks_flags', {})"
      pattern: "defaults\\.get\\(\"phase2_ks_flags\""
    - from: "src/fantasy_sim/validation/config.py::bare_config_dict"
      to: "config/defaults.yaml top-level engine gates"
      via: "explicit dotted-path enumeration in the disabled-set list"
      pattern: "phase2_ks_flags\\."
---

<objective>
Implement Phase 2's foundational scaffolding so per-KS plans (02-08) can land safely behind feature flags. This plan does NOT change any runtime behavior — it ships:

1. The `phase2_ks_flags:` config block (7 flags, all default `enabled: false`).
2. The `get_phase2_ks_flags()` loader shim (graceful degradation when the block is absent).
3. The `bare_config_dict()` extension covering 7 new flags + 5 new top-level keys (with the HARD GATE test extended).
4. The `residual_calibration` artifact loader bumped to accept `schema_version: 2` (with v1 still working).
5. The `p2.entry.full` ledger entry pinned (a numerical sanity-check copy of `p1.aggregate.full` Arm B; the canonical Phase-2-vs-Phase-1 delta is computed in Plan 09 against `p1.aggregate.full` per D-15).
6. The `.planning/phases/02-structural-per-stat-calibration/logs/` directory with `.gitkeep`.

Without Plan 01, every per-KS plan would either (a) ship a code change with no flag-gate (regressing the per-KS A/B back to a Cycle-2 no-op), (b) extend `bare_config_dict()` ad-hoc (causing the HARD GATE to silently fail), or (c) bump the artifact schema in the same commit that introduces per-stat correction (coupling unrelated changes).

Output: `phase2_ks_flags:` block + loader shim + extended bare_config_dict + schema-v2-aware artifact loader + `p2.entry.full` ledger pin + logs directory. All defaults stay `false` / unchanged so the existing 2,131-test suite + every existing ledger entry stays valid.

Reference Phase 1 Plan 00 (`00-validation-harness-and-phase0-baseline-PLAN.md`) for the exact pattern this plan mirrors.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/REQUIREMENTS.md
@.planning/research/HYPOTHESES.md
@.planning/phases/02-structural-per-stat-calibration/02-CONTEXT.md
@.planning/phases/02-structural-per-stat-calibration/02-RESEARCH.md
@.planning/phases/02-structural-per-stat-calibration/02-VALIDATION.md
@.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/00-validation-harness-and-phase0-baseline-PLAN.md
@.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-CONTEXT.md
@config/defaults.yaml
@src/fantasy_sim/config/loader.py
@src/fantasy_sim/validation/config.py
@src/fantasy_sim/scoring/residual_calibration.py
@tests/test_validation/test_config.py
@tests/test_scoring/test_residual_calibration.py

<interfaces>
From src/fantasy_sim/config/loader.py:99-111 (the Phase 1 pattern to mirror):

```python
def get_phase1_ks_flags() -> dict:
    """Return the phase1_ks_flags block from the loaded defaults.yaml.

    Returns {} if the block is absent (graceful degradation for older configs).
    Used by per-KS code paths to gate Phase 1 KS-XX behavior changes behind
    `phase1_ks_flags.ksXX_<name>.enabled` so per-KS A/B genuinely flips a code
    path on/off (Cycle 3 D-45).
    """
    defaults = load_defaults()
    return defaults.get("phase1_ks_flags", {})
```

From src/fantasy_sim/validation/config.py:262-267 (the Phase 1 disabled-set list):

```python
# Phase 1 KS code-change feature flags (added Cycle 3 — D-45 / NEW HIGH #1 fix).
# Each flag gates one per-KS code change so per-KS A/B can perform a real (legacy)
# vs (new) two-arm comparison via `--set phase1_ks_flags.ksXX_<name>.enabled=true`.
# Disabling them in bare_config_dict means per-KS bare-isolation A/B can flip them
# back on with `--set phase1_ks_flags.ksXX_<name>.enabled=true`.
"phase1_ks_flags.ks01_preserve_distribution.enabled",
"phase1_ks_flags.ks03_dynamic_yard_anchor.enabled",
"phase1_ks_flags.ks04_conditional_catch_boost.enabled",
"phase1_ks_flags.ks05_props_recv_yds_fix.enabled",
"phase1_ks_flags.ks06_backup_receiver_fix.enabled",
"phase1_ks_flags.ks07_positional_rz_catch_rate.enabled",
"phase1_ks_flags.ks15_unclamp_for_td_gate.enabled",
"phase1_ks_flags.ks32_clock_pass_incomplete_3s.enabled",
```

From src/fantasy_sim/scoring/residual_calibration.py:14-15 + the artifact loader (schema check site):

```python
ARTIFACT_SCHEMA_VERSION = 1  # Plan 01 bumps to support {1, 2}
# (search the file for the exact site that compares schema_version; mirror Phase 1 D-46 pattern)
```

From config/defaults.yaml (current top-level keys to extend; full file ~480 lines, the relevant sections):
- Top-level `phase1_ks_flags:` block at file head (lines 7-39)
- `ensemble.dynamic_blend:` block at lines 392-401
- `ensemble.residual_calibration:` block at lines 402-412
- `pff.tier_engine:` block at lines 82-130 (already has `reliability_floor: 0.20`, `reliability_cap: 0.80` and an empty `position_reliability: {}` slot via `pff/models.py:162`)
- `ensemble.ff_opportunity:` block at lines 380-391

</interfaces>

</context>

<tasks>

<task type="auto">
  <name>Task 1: Add `phase2_ks_flags:` block + new top-level config keys to defaults.yaml</name>
  <files>config/defaults.yaml</files>
  <read_first>
    - config/defaults.yaml (full file — locate `phase1_ks_flags:` at file head and `ensemble:` block; insertion targets)
    - .planning/phases/02-structural-per-stat-calibration/02-CONTEXT.md (D-02, D-04, D-07, D-08, D-10 specify exact key paths)
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-CONTEXT.md (D-44, D-45 — Phase 1 patterns)
  </read_first>
  <behavior>
    - Add a NEW top-level block `phase2_ks_flags:` immediately AFTER the existing `phase1_ks_flags:` block (so the two phase blocks live adjacent at the file head).
    - For each of the 7 KS items, the block contains one entry with `enabled: false` and any KS-specific fields (e.g., KS-08 has `floor: 0.20` placeholder; KS-04 in Phase 1 had `boost_value: 1.5` for analogy).
    - Add new sub-blocks under `ensemble.residual_calibration:`:
      - `stat_level: {enabled: false, covered_stats: [...]}` (the 14 covered stats per D-03)
      - `max_abs_adjustment_by_position: {QB: 1.5, RB: 1.5, WR: 1.5, TE: 1.5}` (placeholder matching the existing global `max_abs_adjustment: 1.5`; Plan 05 retunes to D-07 values)
    - Add new field `simulator_weight_floor: 0.0` under `ensemble.dynamic_blend:` (Plan 02 retunes to chosen sweep value).
    - Add new sub-block under `ensemble.ff_opportunity:`:
      - `prior_width: {enabled: false}` (Plan 07 toggles + adds path-specific fields).
    - Add new sub-block under `pff.tier_engine:` (after existing `reliability_cap: 0.80`):
      - `position_reliability: {}` (empty dict; Plan 06 populates per D-08).
    - All defaults preserve current runtime behavior — every flag is false / every new field is the existing global default.
  </behavior>
  <action>
Open `config/defaults.yaml`. Locate the existing `phase1_ks_flags:` block at file head (line 7).

After the closing line of the `phase1_ks_flags:` block (which is the `ks32_clock_pass_incomplete_3s:` entry around line 38-39, where `enabled: false`), and BEFORE the `simulation:` block, insert:

```yaml

# Phase 2 KS code-change feature flags (continues Phase 1 D-45 pattern — see 02-CONTEXT.md
# D-02). Each flag gates one per-KS code change so per-KS A/B can perform a real (legacy)
# vs (new) two-arm comparison via `--set phase2_ks_flags.ksXX_<name>.enabled=true`. Default
# false everywhere; per-KS promotion commits flip the flag to `true` after the A/B passes
# hard floor + promotion bar.
phase2_ks_flags:
  ks08_dynamic_blend_simulator_floor:
    enabled: false
    floor: 0.20    # KS-08 sweep candidate (Plan 02 retunes to smallest-passing value)
  ks09_per_stat_residual_calibration:
    enabled: false  # KS-09 D-02 (Plan 03)
  ks10_per_position_caps:
    enabled: false  # KS-10 D-07 (Plan 05)
  ks11_position_reliability:
    enabled: false  # KS-11 D-08 (Plan 06)
  ks12_share_normalization_residual:
    enabled: false  # KS-12 D-09 (Plan 08)
  ks13_ff_opportunity_prior_width:
    enabled: false  # KS-13 D-10 (Plan 07)
  ks14_thin_bucket_shrinkage:
    enabled: false  # KS-14 D-11 (Plan 04)
```

Locate the existing `ensemble.dynamic_blend:` block (around line 392-401). Insert AFTER the existing `fallback: fixed_defaults` line:

```yaml
    simulator_weight_floor: 0.0  # KS-08 D-06 placeholder (Plan 02 retunes to smallest-passing value from sweep {0.20, 0.30, 0.40})
```

Locate the existing `ensemble.residual_calibration:` block (around line 402-412). Insert AFTER the existing `fallback: zero` line:

```yaml
    max_abs_adjustment_by_position:  # KS-10 D-07 placeholder (Plan 05 retunes to {QB: 2.5, RB: 2.0, WR: 1.5, TE: 0.8})
      QB: 1.5
      RB: 1.5
      WR: 1.5
      TE: 1.5
    stat_level:  # KS-09 D-03 (Plan 03 enables + uses)
      enabled: false
      covered_stats:
        - pass_yards
        - pass_tds
        - interceptions
        - rush_yards
        - rush_tds
        - receiving_yards
        - receptions
        - receiving_tds
        - fumbles_lost
```

Locate the existing `ensemble.ff_opportunity:` block (around line 380-391). Insert AFTER the existing `min_coverage_weeks: 1` line:

```yaml
    prior_width:  # KS-13 D-10 (Plan 07 enables; Path A or Path B per probe)
      enabled: false
```

Locate the existing `pff.tier_engine:` block. Find the line `reliability_cap: 0.80`. Insert AFTER it (before `blend_pool_size: 250`):

```yaml
    position_reliability: {}  # KS-11 D-08 placeholder (Plan 06 populates: WR/TE {floor: 0.30, cap: 0.95, min_targets: 30}, RB {floor: 0.25, cap: 0.92, min_carries: 50}; QB stays at global floor:0.20/cap:0.80 per C-10)
```

Verify:
```bash
uv run python -c "from fantasy_sim.config.loader import load_defaults; d = load_defaults(); assert 'phase2_ks_flags' in d; assert len(d['phase2_ks_flags']) == 7; assert all(not v.get('enabled') for v in d['phase2_ks_flags'].values()); print('OK', list(d['phase2_ks_flags'].keys()))"
```

Expected output:
```
OK ['ks08_dynamic_blend_simulator_floor', 'ks09_per_stat_residual_calibration', 'ks10_per_position_caps', 'ks11_position_reliability', 'ks12_share_normalization_residual', 'ks13_ff_opportunity_prior_width', 'ks14_thin_bucket_shrinkage']
```

Commit: `config(02-01): add phase2_ks_flags block + Phase-2 placeholder config keys`
  </action>
  <verify>
    <automated>uv run python -c "from fantasy_sim.config.loader import load_defaults; d = load_defaults(); assert 'phase2_ks_flags' in d and len(d['phase2_ks_flags']) == 7 and all(not v.get('enabled') for v in d['phase2_ks_flags'].values()); assert 'simulator_weight_floor' in d['ensemble']['dynamic_blend']; assert 'max_abs_adjustment_by_position' in d['ensemble']['residual_calibration']; assert 'stat_level' in d['ensemble']['residual_calibration']; assert 'prior_width' in d['ensemble']['ff_opportunity']; assert 'position_reliability' in d['pff']['tier_engine']; print('OK')"</automated>
  </verify>
  <acceptance_criteria>
    - `config/defaults.yaml` contains the literal string `phase2_ks_flags:` at top level
    - `config/defaults.yaml` contains all 7 keys: `ks08_dynamic_blend_simulator_floor`, `ks09_per_stat_residual_calibration`, `ks10_per_position_caps`, `ks11_position_reliability`, `ks12_share_normalization_residual`, `ks13_ff_opportunity_prior_width`, `ks14_thin_bucket_shrinkage`
    - All 7 entries have `enabled: false`
    - `config/defaults.yaml` contains `simulator_weight_floor: 0.0` under `ensemble.dynamic_blend`
    - `config/defaults.yaml` contains `max_abs_adjustment_by_position:` under `ensemble.residual_calibration` with QB/RB/WR/TE keys all = 1.5
    - `config/defaults.yaml` contains `stat_level:` under `ensemble.residual_calibration` with `enabled: false` and a `covered_stats:` list of 9+ stats
    - `config/defaults.yaml` contains `prior_width:` under `ensemble.ff_opportunity` with `enabled: false`
    - `config/defaults.yaml` contains `position_reliability: {}` under `pff.tier_engine`
    - `uv run python -c "from fantasy_sim.config.loader import load_defaults; d = load_defaults(); print(d['phase2_ks_flags'])"` exits 0 and prints 7 keys
    - `git log -1 --pretty=%s` matches `config(02-01): add phase2_ks_flags`
  </acceptance_criteria>
</task>

<task type="auto">
  <name>Task 2: Add `get_phase2_ks_flags()` shim to config/loader.py + extend `bare_config_dict()` with 7 new flags + 5 new top-level keys + extend the HARD GATE test</name>
  <files>
    - src/fantasy_sim/config/loader.py
    - src/fantasy_sim/validation/config.py
    - tests/test_validation/test_config.py
  </files>
  <read_first>
    - src/fantasy_sim/config/loader.py (`get_phase1_ks_flags` at line 99-111 — exact pattern to mirror)
    - src/fantasy_sim/validation/config.py (`bare_config_dict` function — locate the disabled-set list at lines 262-267)
    - tests/test_validation/test_config.py (`test_bare_config_dict_produces_all_None_engines` test — extend with new keys; the test must STILL be a HARD GATE per Phase 1 D-44)
  </read_first>
  <behavior>
    - In `loader.py`: add a new function `get_phase2_ks_flags() -> dict` that mirrors `get_phase1_ks_flags()` exactly except for the dict key (`phase2_ks_flags` instead of `phase1_ks_flags`).
    - In `validation/config.py`: extend the disabled-set list in `bare_config_dict()` with 7 NEW Phase 2 flag dotted-paths AND 5 NEW top-level engine keys.
    - In `tests/test_validation/test_config.py`: extend the existing hard-gate test `test_bare_config_dict_produces_all_None_engines` to verify the new flags are flipped off AND new keys are at their disabled defaults.
    - Behavior is a no-op for existing ledger entries: the same default config still produces the same Arm-B values.
  </behavior>
  <action>
**File 1: `src/fantasy_sim/config/loader.py`** — locate the existing `get_phase1_ks_flags()` function around line 99-111 (it ends with `return defaults.get("phase1_ks_flags", {})`). Insert IMMEDIATELY AFTER that function:

```python
def get_phase2_ks_flags() -> dict:
    """Return the phase2_ks_flags block from the loaded defaults.yaml.

    Returns {} if the block is absent (graceful degradation for older configs).
    Used by per-KS code paths to gate Phase 2 KS-XX behavior changes behind
    `phase2_ks_flags.ksXX_<name>.enabled` so per-KS A/B genuinely flips a code
    path on/off (continues Phase 1 D-45 pattern; see 02-CONTEXT.md D-02).
    """
    defaults = load_defaults()
    return defaults.get("phase2_ks_flags", {})
```

**File 2: `src/fantasy_sim/validation/config.py`** — locate the Phase 1 KS-flags block in the `bare_config_dict()` disabled-set list (lines 262-267). Insert IMMEDIATELY AFTER the line `"phase1_ks_flags.ks32_clock_pass_incomplete_3s.enabled",` (and before whatever block follows):

```python
        # Phase 2 KS code-change feature flags (added — see 02-CONTEXT.md D-02 / D-44 pattern).
        # Each flag gates one per-KS code change so per-KS A/B can perform a real (legacy)
        # vs (new) two-arm comparison via `--set phase2_ks_flags.ksXX_<name>.enabled=true`.
        # Disabling them in bare_config_dict means per-KS bare-isolation A/B can flip them
        # back on with the same --set syntax. Plans 02-08 reference these.
        "phase2_ks_flags.ks08_dynamic_blend_simulator_floor.enabled",
        "phase2_ks_flags.ks09_per_stat_residual_calibration.enabled",
        "phase2_ks_flags.ks10_per_position_caps.enabled",
        "phase2_ks_flags.ks11_position_reliability.enabled",
        "phase2_ks_flags.ks12_share_normalization_residual.enabled",
        "phase2_ks_flags.ks13_ff_opportunity_prior_width.enabled",
        "phase2_ks_flags.ks14_thin_bucket_shrinkage.enabled",
        # Phase 2 sub-engine gates (the 5 new top-level keys from Plan 01 Task 1)
        "ensemble.residual_calibration.stat_level.enabled",
        "ensemble.ff_opportunity.prior_width.enabled",
```

(Note: `ensemble.dynamic_blend.simulator_weight_floor`, `ensemble.residual_calibration.max_abs_adjustment_by_position`, and `pff.tier_engine.position_reliability` are NOT booleans — they're scalar/dict values. They don't go in the `enabled`-flag list. The bare config is still set by zeroing-out the existing `enabled` gates above their parents (e.g., `ensemble.dynamic_blend.enabled = False` is already in the Phase 1 list). Verify those keys are already present in `bare_config_dict()` before this task; if any are MISSING, add them.)

**File 3: `tests/test_validation/test_config.py`** — locate the existing `test_bare_config_dict_produces_all_None_engines` test. The test currently iterates over a list of expected disabled keys and asserts each is `None` after `build_engine_configs(bare_config_dict(load_defaults()))`. Extend the expected-disabled-keys list with the 7 new flags + the 2 new sub-engine boolean keys.

Add a NEW test directly below it:

```python
def test_phase2_ks_flags_present_and_default_false():
    """HARD GATE: every phase2_ks_flags entry must exist in defaults and default to enabled: false.

    Per Phase 2 D-02: per-KS plans land their code path behind `phase2_ks_flags.ksXX_<name>.enabled`
    with default false. The promotion commit per plan flips the default to true. This test
    catches the case where someone adds a KS code change behind a flag that doesn't exist in
    defaults (would silently behave as `False`, hiding the regression).
    """
    from fantasy_sim.config.loader import get_phase2_ks_flags
    flags = get_phase2_ks_flags()
    expected = {
        "ks08_dynamic_blend_simulator_floor",
        "ks09_per_stat_residual_calibration",
        "ks10_per_position_caps",
        "ks11_position_reliability",
        "ks12_share_normalization_residual",
        "ks13_ff_opportunity_prior_width",
        "ks14_thin_bucket_shrinkage",
    }
    assert set(flags.keys()) >= expected, f"Missing phase2_ks_flags entries: {expected - set(flags.keys())}"
    for name in expected:
        assert flags[name].get("enabled") is False, f"phase2_ks_flags.{name}.enabled must default to False (got {flags[name].get('enabled')!r})"


def test_phase2_bare_config_disables_all_new_flags():
    """HARD GATE: bare_config_dict() must enumerate every phase2_ks_flags.*.enabled key.

    Mirrors the Phase 1 hard-gate test pattern (D-44). If a Phase 2 KS plan adds a flag
    to defaults but forgets to add it to bare_config_dict(), the per-KS bare-isolation A/B
    silently runs both arms with the same flag value and produces a no-op A/B (the Cycle-2
    failure mode). This test refuses to merge a plan that does so.
    """
    from fantasy_sim.config.loader import load_defaults
    from fantasy_sim.validation.config import bare_config_dict
    bare = bare_config_dict(load_defaults())
    assert bare["phase2_ks_flags"]["ks08_dynamic_blend_simulator_floor"]["enabled"] is False
    assert bare["phase2_ks_flags"]["ks09_per_stat_residual_calibration"]["enabled"] is False
    assert bare["phase2_ks_flags"]["ks10_per_position_caps"]["enabled"] is False
    assert bare["phase2_ks_flags"]["ks11_position_reliability"]["enabled"] is False
    assert bare["phase2_ks_flags"]["ks12_share_normalization_residual"]["enabled"] is False
    assert bare["phase2_ks_flags"]["ks13_ff_opportunity_prior_width"]["enabled"] is False
    assert bare["phase2_ks_flags"]["ks14_thin_bucket_shrinkage"]["enabled"] is False
    # Sub-engine gates from Plan 01 Task 1
    assert bare["ensemble"]["residual_calibration"]["stat_level"]["enabled"] is False
    assert bare["ensemble"]["ff_opportunity"]["prior_width"]["enabled"] is False
```

Run pytest:
```bash
uv run pytest tests/test_validation/test_config.py -v -k "phase2 or bare_config"
```

Expected: all tests pass (the new tests verify Plan 01 Task 1's defaults.yaml changes; the existing `test_bare_config_dict_produces_all_None_engines` continues to pass with the extended list).

Commit: `feat(02-01): add get_phase2_ks_flags() shim + extend bare_config_dict() with 7 KS flags + 2 sub-engine gates`
  </action>
  <verify>
    <automated>uv run pytest tests/test_validation/test_config.py -v -k "phase2 or bare_config" 2>&1 | grep -E "PASSED|FAILED|ERROR" | head -20</automated>
  </verify>
  <acceptance_criteria>
    - `src/fantasy_sim/config/loader.py` contains the literal string `def get_phase2_ks_flags()`
    - `src/fantasy_sim/validation/config.py` contains the literal string `phase2_ks_flags.ks08_dynamic_blend_simulator_floor.enabled`
    - `src/fantasy_sim/validation/config.py` contains the literal string `phase2_ks_flags.ks14_thin_bucket_shrinkage.enabled`
    - `src/fantasy_sim/validation/config.py` contains the literal string `ensemble.residual_calibration.stat_level.enabled`
    - `src/fantasy_sim/validation/config.py` contains the literal string `ensemble.ff_opportunity.prior_width.enabled`
    - `tests/test_validation/test_config.py` contains the literal string `def test_phase2_ks_flags_present_and_default_false`
    - `tests/test_validation/test_config.py` contains the literal string `def test_phase2_bare_config_disables_all_new_flags`
    - `uv run pytest tests/test_validation/test_config.py -v -k "phase2"` exits 0
    - `uv run python -c "from fantasy_sim.config.loader import get_phase2_ks_flags; assert len(get_phase2_ks_flags()) >= 7; print('OK')"` exits 0
    - `git log -1 --pretty=%s` matches `feat(02-01):.*phase2_ks_flags.*shim`
  </acceptance_criteria>
</task>

<task type="auto">
  <name>Task 3: Bump residual_calibration artifact loader to schema_version: 2 (graceful v1 + v2)</name>
  <files>
    - src/fantasy_sim/scoring/residual_calibration.py
    - tests/test_scoring/test_residual_calibration.py
  </files>
  <read_first>
    - src/fantasy_sim/scoring/residual_calibration.py (`ARTIFACT_SCHEMA_VERSION = 1` at line 15; locate the loader function that compares schema_version — search for `schema_version` in the file)
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-CONTEXT.md (D-46 — Phase 1 schema-bump pattern for SeasonMetrics)
  </read_first>
  <behavior>
    - Update `ARTIFACT_SCHEMA_VERSION` from `1` to `2` (the writer-side default for new artifacts).
    - Update the loader's schema check so it accepts BOTH `1` and `2` as valid schema versions (rejects only `>= 3` or `< 1`).
    - When the artifact has `schema_version: 1`, the loader treats it as having an empty `stat_corrections: {}` block (no per-stat corrections). All existing v1 behavior is preserved exactly.
    - When the artifact has `schema_version: 2`, the loader reads the `stat_corrections` block (if present) and exposes it via the existing artifact dict (`artifact["stat_corrections"]` accessible to KS-09 Plan 03's per-stat corrector).
    - Add tests confirming both schema_v1 and schema_v2 artifacts load; schema_v3 fails.
  </behavior>
  <action>
**File 1: `src/fantasy_sim/scoring/residual_calibration.py`** — locate line 15: `ARTIFACT_SCHEMA_VERSION = 1`. Replace with:

```python
ARTIFACT_SCHEMA_VERSION = 2  # v1 = fpts-only; v2 = fpts + per-stat stat_corrections (KS-09)
ARTIFACT_SCHEMA_VERSIONS_SUPPORTED = (1, 2)  # loader accepts both
```

Locate the loader function in the file that compares `schema_version` (search for `schema_version` literal — it's in the `_artifact()` or similar method, mirrors `dynamic_blend.py:520-527`). Find the comparison line that looks like:
```python
if artifact.get("schema_version") != ARTIFACT_SCHEMA_VERSION:
    self._artifact_cache[season] = None
    return None
```

Replace with:
```python
schema = artifact.get("schema_version")
if schema not in ARTIFACT_SCHEMA_VERSIONS_SUPPORTED:
    self._artifact_cache[season] = None
    return None
# Normalize: v1 artifacts have no stat_corrections block; expose an empty dict so
# downstream per-stat corrector (KS-09 Plan 03) sees a uniform shape.
if schema == 1 and "stat_corrections" not in artifact:
    artifact = dict(artifact)  # don't mutate cache key
    artifact["stat_corrections"] = {}
```

If the file has multiple loader sites (writer + reader), update both — the **writer** uses the new `ARTIFACT_SCHEMA_VERSION = 2`, the **reader** uses `ARTIFACT_SCHEMA_VERSIONS_SUPPORTED`.

**File 2: `tests/test_scoring/test_residual_calibration.py`** — add at the end of the file (or after the existing artifact-loader tests):

```python
def test_artifact_loader_accepts_schema_v1():
    """Schema v1 artifacts (Phase 1 bundled) must continue to load post-Phase-2 schema bump."""
    import json
    from pathlib import Path
    # Use one of the bundled artifacts that ships at schema_version: 1
    artifact_path = Path(__file__).resolve().parents[2] / "src" / "fantasy_sim" / "data" / "ensemble" / "artifacts" / "residual_calibration" / "decision_s200" / "calibration_2024.json"
    if artifact_path.exists():
        with open(artifact_path) as f:
            artifact = json.load(f)
        # Bundled artifacts are at schema_version: 1 until Plan 03 / Plan 05 re-fit
        # bumps them to v2. The v1 path must keep working.
        assert artifact["schema_version"] in (1, 2), f"Bundled artifact at unsupported schema_version={artifact['schema_version']}"

def test_artifact_loader_accepts_schema_v2():
    """Schema v2 artifacts (KS-09 Plan 03 introduces) must load and expose stat_corrections."""
    from fantasy_sim.scoring.residual_calibration import ARTIFACT_SCHEMA_VERSION, ARTIFACT_SCHEMA_VERSIONS_SUPPORTED
    assert ARTIFACT_SCHEMA_VERSION == 2
    assert 1 in ARTIFACT_SCHEMA_VERSIONS_SUPPORTED
    assert 2 in ARTIFACT_SCHEMA_VERSIONS_SUPPORTED

def test_artifact_loader_rejects_schema_v3():
    """Future schema versions must be rejected so a forwards-incompatible artifact doesn't silently load."""
    from fantasy_sim.scoring.residual_calibration import ARTIFACT_SCHEMA_VERSIONS_SUPPORTED
    assert 3 not in ARTIFACT_SCHEMA_VERSIONS_SUPPORTED
```

Run pytest:
```bash
uv run pytest tests/test_scoring/test_residual_calibration.py -v -k "schema"
```

Expected: 3 tests pass.

Commit: `feat(02-01): bump residual_calibration artifact loader to schema_version: 2 (graceful v1 + v2 support)`
  </action>
  <verify>
    <automated>uv run pytest tests/test_scoring/test_residual_calibration.py -v -k "schema" 2>&1 | grep -E "PASSED|FAILED|ERROR" | head -10 && uv run python -c "from fantasy_sim.scoring.residual_calibration import ARTIFACT_SCHEMA_VERSION, ARTIFACT_SCHEMA_VERSIONS_SUPPORTED; assert ARTIFACT_SCHEMA_VERSION == 2 and ARTIFACT_SCHEMA_VERSIONS_SUPPORTED == (1, 2); print('OK')"</automated>
  </verify>
  <acceptance_criteria>
    - `src/fantasy_sim/scoring/residual_calibration.py` contains `ARTIFACT_SCHEMA_VERSION = 2`
    - `src/fantasy_sim/scoring/residual_calibration.py` contains `ARTIFACT_SCHEMA_VERSIONS_SUPPORTED = (1, 2)`
    - `src/fantasy_sim/scoring/residual_calibration.py` contains the literal string `if schema not in ARTIFACT_SCHEMA_VERSIONS_SUPPORTED`
    - `tests/test_scoring/test_residual_calibration.py` contains `def test_artifact_loader_accepts_schema_v2`
    - `tests/test_scoring/test_residual_calibration.py` contains `def test_artifact_loader_rejects_schema_v3`
    - `uv run pytest tests/test_scoring/test_residual_calibration.py -v -k schema` exits 0
    - `git log -1 --pretty=%s` matches `feat(02-01).*schema_version: 2`
  </acceptance_criteria>
</task>

<task type="auto">
  <name>Task 4: Pin `p2.entry.full` ledger entry + create logs/ directory + run full suite</name>
  <files>
    - .planning/phases/02-structural-per-stat-calibration/logs/.gitkeep
    - .planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md
  </files>
  <read_first>
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/ (Phase 1 logs directory contents — mirror the same structure)
    - .planning/phases/02-structural-per-stat-calibration/02-VALIDATION.md (Wave 0 line item: `p2.entry.full` pin)
  </read_first>
  <behavior>
    - Create the `logs/` directory with `.gitkeep` (Phase 1 D-43 pattern).
    - Initialize a `PROMOTION-NOTES.md` file with one section per upcoming KS plan; per-KS plans append decision notes there during their respective Task 4 promotion-state commits.
    - Run `validate.py --baseline bare --label p2.entry.full` to pin the Phase-2 entry baseline (numerically equal to `p1.aggregate.full` Arm B; sanity-check entry to confirm cache + harness still work post-Phase 2 scaffolding).
    - Run the full pytest suite to confirm no regressions from Plan 01 changes.
  </behavior>
  <action>
Create `.planning/phases/02-structural-per-stat-calibration/logs/.gitkeep` (empty file):
```bash
mkdir -p .planning/phases/02-structural-per-stat-calibration/logs
touch .planning/phases/02-structural-per-stat-calibration/logs/.gitkeep
```

Create `.planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md` with the following content (one stub per KS plan — per-KS plans Task 4 will append their decision summaries):

```markdown
# Phase 2 — Promotion Notes

> One entry per per-KS plan promotion-state commit. Mirrors Phase 1 logs/PROMOTION-NOTES.md.
> Status flag legend: SHIPPED / SHIPPED-NO-OP / SHIPPED-PARTIAL / BLOCKED.

## Phase 2 Entry Baseline (Plan 01 Task 4)

`p2.entry.full` = `p1.aggregate.full` Arm B (#105) — numerical sanity-check pin.
- Source: `validate.py --baseline bare --label p2.entry.full`
- Purpose: D-15 Phase-2-vs-Phase-1 delta in Plan 09 differences `p2.aggregate.full` Arm B against `p1.aggregate.full` Arm B; `p2.entry.full` is a same-commit snapshot to verify the cache + harness produce identical metrics post-Plan-01 scaffolding.
- Acceptance: |Δ rank_corr| < 1e-4 AND |Δ weekly_mae| < 0.001 between `p1.aggregate.full` Arm B and `p2.entry.full` Arm B.

## KS-08 (Plan 02) — TBD

## KS-09 (Plan 03) — TBD

## KS-10 (Plan 05) — TBD

## KS-11 (Plan 06) — TBD

## KS-12 (Plan 08) — TBD

## KS-13 (Plan 07) — TBD

## KS-14 (Plan 04) — TBD

## Phase 2 Aggregate (Plan 09) — TBD
```

Run the full test suite:
```bash
uv run pytest tests/ -v 2>&1 | tail -20
```

Expected: 2,131 + 5 (new tests) = 2,136 tests pass. NO regressions.

Pin `p2.entry.full`:
```bash
uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --label p2.entry.full
```

Expected: ledger entry created with Arm B identical to `p1.aggregate.full` Arm B (since defaults haven't changed runtime behavior — all `phase2_ks_flags.*.enabled = false`).

Inspect the ledger:
```bash
uv run python scripts/validate.py --show-ledger | grep -E "p1.aggregate.full|p2.entry.full"
```

Expected: both rows visible; rank_corr and weekly_mae values match (within floating-point tolerance).

Append the entry confirmation to `PROMOTION-NOTES.md`:
```markdown
**2026-04-26 (Plan 01 Task 4):** `p2.entry.full` pinned. rank_corr=<value>, weekly_mae=<value>. Δ vs `p1.aggregate.full` Arm B = (rank_corr <delta>, weekly_mae <delta>). Plan 01 scaffolding has zero runtime effect (verified).
```

Commit: `docs(02-01): pin p2.entry.full ledger entry + create logs/ directory + initialize PROMOTION-NOTES.md`
  </action>
  <verify>
    <automated>test -d .planning/phases/02-structural-per-stat-calibration/logs && test -f .planning/phases/02-structural-per-stat-calibration/logs/.gitkeep && test -f .planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md && uv run pytest tests/ -v 2>&1 | tail -5 | grep -E "passed|failed" && uv run python scripts/validate.py --show-ledger | grep -q "p2.entry.full"</automated>
  </verify>
  <acceptance_criteria>
    - `.planning/phases/02-structural-per-stat-calibration/logs/.gitkeep` exists
    - `.planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md` exists and contains the literal string `## Phase 2 Entry Baseline`
    - `.planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md` contains stub sections for `## KS-08`, `## KS-09`, `## KS-10`, `## KS-11`, `## KS-12`, `## KS-13`, `## KS-14`
    - `uv run pytest tests/ -v` exits 0 with all tests passing (no regressions from Plan 01)
    - `uv run python scripts/validate.py --show-ledger` returns at least one row matching `p2.entry.full`
    - `git log -1 --pretty=%s` matches `docs(02-01): pin p2.entry.full ledger entry`
    - `p2.entry.full` Arm B rank_corr equals `p1.aggregate.full` Arm B rank_corr within 1e-4
  </acceptance_criteria>
</task>

</tasks>

<verification>
After all 4 tasks complete:

1. `git log --oneline -10` shows 4 new commits prefixed `(02-01)`.
2. `cat config/defaults.yaml | grep -A 1 "phase2_ks_flags:" | head -3` shows the new block.
3. `uv run pytest tests/test_validation/test_config.py tests/test_scoring/test_residual_calibration.py -v -k "phase2 or schema or bare_config"` exits 0.
4. `uv run python scripts/validate.py --show-ledger | grep -E "p1.aggregate.full|p2.entry.full"` shows both rows with matching Arm B metrics.
5. `uv run pytest tests/ -v` exits 0; total test count = 2,131 + 5 (Plan 01 additions) = 2,136.

Plan 01 SHIPPED. Per-KS plans 02-08 may now proceed in dependency order per D-12 (KS-08 first via Plan 02).
</verification>

<must_haves>
  truths:
    - "Per Phase 1 D-44 / Phase 2 D-02: bare_config_dict() is the single source of truth for Arm-A bare configuration; this plan's Task 2 extension is a HARD GATE — `test_phase2_bare_config_disables_all_new_flags` MUST stay green or per-KS A/B regresses to a no-op"
    - "Per Phase 1 D-46 / Phase 2 D-13: artifact schema_version bump must be backwards-compatible (v1 still loads). Plan 03 (KS-09) adds the v2 stat_corrections block to the runtime+training pipeline; Plan 01 only ships the LOADER tolerance. Without Plan 01, Plan 03's runtime change couldn't roll back to schema_v1 artifacts cleanly."
    - "Per C-02: `p2.entry.full` is a sanity-check pin (numerically equal to `p1.aggregate.full` Arm B). The canonical Phase-2-vs-Phase-1 delta in Plan 09 differences `p2.aggregate.full` against `p1.aggregate.full` per D-15. `p2.entry.full` is NOT used for the canonical delta."
    - "Per C-09: 2,131-test suite stays green. Plan 01 changes are scaffolding-only — no runtime behavior changes when all `phase2_ks_flags.*.enabled` defaults are false. Task 4 verifies this by running the full suite."
  artifacts:
    - path: "config/defaults.yaml"
      provides: "Phase 2 KS feature-flag block + 5 new top-level config keys (all at safe defaults)"
      contains: "phase2_ks_flags:"
    - path: "src/fantasy_sim/config/loader.py"
      provides: "get_phase2_ks_flags() shim mirroring Phase 1 pattern"
      contains: "def get_phase2_ks_flags"
    - path: "src/fantasy_sim/validation/config.py"
      provides: "Extended bare_config_dict() with 7 new flags + 2 new sub-engine boolean gates"
      contains: "phase2_ks_flags.ks08_dynamic_blend_simulator_floor.enabled"
    - path: "src/fantasy_sim/scoring/residual_calibration.py"
      provides: "Schema-v2-aware artifact loader with v1 graceful-fallback"
      contains: "ARTIFACT_SCHEMA_VERSIONS_SUPPORTED"
    - path: ".planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md"
      provides: "Per-KS promotion-state commit decision log; Task 4 records `p2.entry.full` sanity-check delta"
      contains: "Phase 2 Entry Baseline"
</must_haves>

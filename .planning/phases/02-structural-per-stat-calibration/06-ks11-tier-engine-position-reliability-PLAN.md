---
phase: 02-structural-per-stat-calibration
plan: 06
type: execute
wave: 4
depends_on: ["01"]
files_modified:
  - config/defaults.yaml
  - src/fantasy_sim/data/pff/config.py
  - tests/test_data/test_pff/test_tier_engine.py
  - tests/test_data/test_pff/test_config.py
  - .planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md
autonomous: true
requirements: [KS-11]
must_haves:
  truths:
    - "Per D-08 + HYPOTHESES.md KS-11 (lines 226-245): position-specific reliability cap raise (config-only). Add `pff.tier_engine.position_reliability` block: WR/TE `{floor: 0.30, cap: 0.95, min_targets: 30}`, RB `{floor: 0.25, cap: 0.92, min_carries: 50}`. QB stays at global `{floor: 0.20, cap: 0.80}` per C-10."
    - "Per Architectural Responsibility Map in 02-RESEARCH.md: `compute_reliability(position=...)` is ALREADY plumbed (`tier_engine.py:957-965`) and reads `cfg.position_reliability` (`models.py:162`). Plan 06 is config-only — no Python source code changes are needed beyond verifying the existing test path."
    - "Per D-02 / Phase 1 D-45: change is gated behind `phase2_ks_flags.ks11_position_reliability.enabled` (default false). When false, the empty `position_reliability: {}` block keeps QB/WR/TE/RB at global floor/cap. When true, the 3 non-QB positions use the new floors/caps."
    - "**Codex MEDIUM 6 (2026-04-27 revision):** the loader at `data/pff/config.py:138` currently reads `position_reliability` UNCONDITIONALLY from defaults.yaml, which means a populated dict could leak runtime behavior even with the `ks11_position_reliability.enabled` flag false. Plan 06 Task 1 fixes this by changing the loader to: `position_reliability = tier_raw.get('position_reliability', {}) if get_phase2_ks_flags().get('ks11_position_reliability', {}).get('enabled', False) else {}`. The flag is the master gate; the populated dict is the value. Without this fix, per-KS A/B is contaminated when defaults.yaml has the dict populated."
    - "Per C-10 + Pitfall: KS-11 MUST NOT alter QB carry_share/scramble_rate/yards blending. The existing `feedback_qb_calibration.md` invariants are protected by the existing test `tests/test_data/test_pff/test_tier_engine.py:848` (test_apply_team_context::test_qb_unchanged) which is reused as the KS-11 preflight gate."
    - "Per HYPOTHESES.md KS-11 small-medium gain, low risk: single A/B (no per-position cap sweep)."
    - "Per C-08: test-after acceptable for KS-11; 5 unit + 1 behavior preflight tests."
    - "Per C-09: 2,159 + 5 (Plan 06) = 2,164 tests stay green after this plan."
  artifacts:
    - path: "config/defaults.yaml"
      provides: "Updated `pff.tier_engine.position_reliability` block from empty `{}` (Plan 01 placeholder) to D-08 values: WR/TE `{floor: 0.30, cap: 0.95, min_targets: 30}`, RB `{floor: 0.25, cap: 0.92, min_carries: 50}` (after promotion)"
      contains: "position_reliability:"
    - path: "src/fantasy_sim/data/pff/config.py"
      provides: "Codex MEDIUM 6 fix — `build_pff_config` reads `position_reliability` ONLY when `phase2_ks_flags.ks11_position_reliability.enabled=true`; else passes `{}` regardless of defaults.yaml content"
      contains: "ks11_position_reliability"
    - path: "tests/test_data/test_pff/test_tier_engine.py"
      provides: "5 new tests: ks11_wr_position_reliability_uses_per_position_floor_cap, ks11_te_position_reliability_uses_per_position_floor_cap, ks11_rb_position_reliability_uses_per_position_floor_cap, ks11_qb_unchanged_at_global_values, ks11_min_targets_carries_gate"
      contains: "def test_ks11_"
    - path: "tests/test_data/test_pff/test_config.py"
      provides: "Codex MEDIUM 6 coverage — test_ks11_loader_passes_empty_when_flag_off + test_ks11_loader_passes_populated_dict_when_flag_on"
      contains: "test_ks11_loader"
    - path: ".planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md"
      provides: "KS-11 promotion-state decision summary + QB-untouched preflight result"
      contains: "## KS-11"
  key_links:
    - from: "config/defaults.yaml::pff.tier_engine.position_reliability"
      to: "src/fantasy_sim/data/pff/tier_engine.py::compute_reliability"
      via: "TierConfig.position_reliability dict already plumbed (models.py:162; tier_engine.py:961-965)"
      pattern: "position_reliability"
---

<objective>
Implement KS-11 — raise the `tier_engine` reliability cap for high-touch non-QB players via per-position floor/cap config. Per D-08: this is a CONFIG-ONLY change. The runtime `compute_reliability(position=...)` method already accepts a per-position override (`tier_engine.py:957-965`); the `TierConfig.position_reliability` dict is already declared (`models.py:162`); the loader already reads it (`pff/config.py:138`). Plan 06 only populates the config block.

Per HYPOTHESES.md KS-11 (lines 226-245): the existing global cap `0.80` shrinks elite-player distributions toward fat-middle pools. Raising the cap to `0.95` for WR/TE (and `0.92` for RB) lets the per-player PBP distribution dominate when the player has enough sample (≥30 targets / ≥50 carries).

QB STAYS AT THE GLOBAL VALUES `floor: 0.20, cap: 0.80` per C-10 (`feedback_qb_calibration.md` invariant: PFF layers must not alter QB carry/scramble/yards).

Output:
1. Populated `position_reliability:` block in defaults.yaml with D-08 values.
2. 5 new unit tests + 1 behavior preflight test reuse.
3. Ledger entries `p2.ks11.{bare, full}`.
4. Promotion-state commit per Phase 1 D-25/D-40.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/REQUIREMENTS.md
@.planning/research/HYPOTHESES.md
@.planning/phases/02-structural-per-stat-calibration/02-CONTEXT.md
@.planning/phases/02-structural-per-stat-calibration/02-RESEARCH.md
@.planning/phases/02-structural-per-stat-calibration/02-VALIDATION.md
@src/fantasy_sim/data/pff/tier_engine.py
@src/fantasy_sim/data/pff/models.py
@src/fantasy_sim/data/pff/config.py
@config/defaults.yaml
@tests/test_data/test_pff/test_tier_engine.py

<interfaces>
From src/fantasy_sim/data/pff/tier_engine.py:957-982 (existing compute_reliability — KS-11 needs NO code change):

```python
def compute_reliability(
    self,
    games_played: int,
    changed_teams: bool,
    weekly_shares: "np.ndarray | None",
    position: str | None = None,
) -> float:
    cfg = self._config
    pos_rel = cfg.position_reliability.get(position) if position else None
    floor = pos_rel.get("floor", cfg.reliability_floor) if pos_rel else cfg.reliability_floor
    cap = pos_rel.get("cap", cfg.reliability_cap) if pos_rel else cfg.reliability_cap
    # ... rest unchanged
    return float(np.clip(raw, floor, cap))
```

From src/fantasy_sim/data/pff/models.py:162:

```python
position_reliability: dict[str, dict[str, float]] = field(default_factory=dict)
```

From src/fantasy_sim/data/pff/config.py:138:

```python
position_reliability=tier_raw.get("position_reliability", {}),
```

From config/defaults.yaml (Plan 01 placeholder):

```yaml
pff:
  tier_engine:
    ...
    reliability_floor: 0.20
    reliability_cap: 0.80
    position_reliability: {}  # KS-11 D-08 placeholder (Plan 06 populates)
    blend_pool_size: 250
    ...
```

</interfaces>

</context>

<tasks>

<task type="auto">
  <name>Task 1: Populate `pff.tier_engine.position_reliability` in defaults.yaml + add 5 unit tests + behavior preflight reuse</name>
  <files>
    - config/defaults.yaml
    - tests/test_data/test_pff/test_tier_engine.py
  </files>
  <read_first>
    - config/defaults.yaml (`pff.tier_engine` block; locate `reliability_cap: 0.80` and the placeholder `position_reliability: {}` from Plan 01)
    - src/fantasy_sim/data/pff/tier_engine.py:941-982 (compute_reliability — confirm it reads `cfg.position_reliability`)
    - tests/test_data/test_pff/test_tier_engine.py (existing patterns; line 848 has the `test_qb_unchanged` test reused as preflight)
  </read_first>
  <behavior>
    - Update defaults.yaml `position_reliability:` block from `{}` to D-08 values, BUT only as a promotion-state commit AFTER A/B passes. For Task 1, write tests first against a fixture that injects the values.
    - Add 5 unit tests: per-position floor/cap behavior for WR, TE, RB, and QB-unchanged behavior, plus the min_targets/min_carries gate.
    - The QB-unchanged test reuses the existing test path at `tests/test_data/test_pff/test_tier_engine.py:848`.
  </behavior>
  <action>
**File 1: `tests/test_data/test_pff/test_tier_engine.py`** — add at the end of the file:

```python
# === KS-11: tier_engine per-position reliability cap raise ===

import numpy as np
import pytest


def _build_engine_with_position_reliability(position_reliability_values: dict):
    """Build a TierEngine with the given position_reliability config injected."""
    from fantasy_sim.data.pff.tier_engine import TierEngine
    from fantasy_sim.data.pff.models import TierConfig
    config = TierConfig(
        cutoffs=(0.85, 0.65, 0.40, 0.20),
        position_grades={
            "QB": {"primary": "grades_pass", "secondary": "accuracy_percent"},
            "WR": {"primary": "grades_pass_route", "secondary": "_disabled"},
        },
        reliability_max_games=32,
        reliability_team_change_penalty=0.5,
        reliability_variance_weight=0.3,
        reliability_floor=0.20,
        reliability_cap=0.80,
        position_reliability=position_reliability_values,
        blend_pool_size=250,
    )
    return TierEngine(config, pff_loader=None)


def test_ks11_wr_position_reliability_uses_per_position_floor_cap():
    """WR config {floor: 0.30, cap: 0.95} overrides the global {0.20, 0.80}."""
    engine = _build_engine_with_position_reliability({
        "WR": {"floor": 0.30, "cap": 0.95, "min_targets": 30},
    })
    # High games_played → reliability would naturally be high; verify cap = 0.95
    rel = engine.compute_reliability(games_played=32, changed_teams=False, weekly_shares=None, position="WR")
    assert rel == pytest.approx(0.95, abs=1e-6)
    # Low games_played → reliability would naturally be low; verify floor = 0.30
    rel_low = engine.compute_reliability(games_played=0, changed_teams=False, weekly_shares=None, position="WR")
    assert rel_low == pytest.approx(0.30, abs=1e-6)


def test_ks11_te_position_reliability_uses_per_position_floor_cap():
    """TE config {floor: 0.30, cap: 0.95} overrides the global {0.20, 0.80}."""
    engine = _build_engine_with_position_reliability({
        "TE": {"floor": 0.30, "cap": 0.95, "min_targets": 30},
    })
    rel = engine.compute_reliability(games_played=32, changed_teams=False, weekly_shares=None, position="TE")
    assert rel == pytest.approx(0.95, abs=1e-6)


def test_ks11_rb_position_reliability_uses_per_position_floor_cap():
    """RB config {floor: 0.25, cap: 0.92} overrides the global {0.20, 0.80}."""
    engine = _build_engine_with_position_reliability({
        "RB": {"floor": 0.25, "cap": 0.92, "min_carries": 50},
    })
    rel = engine.compute_reliability(games_played=32, changed_teams=False, weekly_shares=None, position="RB")
    assert rel == pytest.approx(0.92, abs=1e-6)
    rel_low = engine.compute_reliability(games_played=0, changed_teams=False, weekly_shares=None, position="RB")
    assert rel_low == pytest.approx(0.25, abs=1e-6)


def test_ks11_qb_unchanged_at_global_values():
    """QB stays at global {floor: 0.20, cap: 0.80} per C-10 (feedback_qb_calibration.md)."""
    engine = _build_engine_with_position_reliability({
        "WR": {"floor": 0.30, "cap": 0.95, "min_targets": 30},
        "TE": {"floor": 0.30, "cap": 0.95, "min_targets": 30},
        "RB": {"floor": 0.25, "cap": 0.92, "min_carries": 50},
    })
    # QB has NO entry in position_reliability → falls back to global
    rel = engine.compute_reliability(games_played=32, changed_teams=False, weekly_shares=None, position="QB")
    assert rel == pytest.approx(0.80, abs=1e-6)  # global cap
    rel_low = engine.compute_reliability(games_played=0, changed_teams=False, weekly_shares=None, position="QB")
    assert rel_low == pytest.approx(0.20, abs=1e-6)  # global floor


def test_ks11_position_reliability_unknown_position_uses_global():
    """A position not in the dict (e.g., K, DST) uses global floor/cap."""
    engine = _build_engine_with_position_reliability({
        "WR": {"floor": 0.30, "cap": 0.95, "min_targets": 30},
    })
    rel = engine.compute_reliability(games_played=32, changed_teams=False, weekly_shares=None, position="K")
    assert rel == pytest.approx(0.80, abs=1e-6)  # global cap fallback
    rel = engine.compute_reliability(games_played=32, changed_teams=False, weekly_shares=None, position=None)
    assert rel == pytest.approx(0.80, abs=1e-6)  # None position fallback
```

Run pytest:
```bash
uv run pytest tests/test_data/test_pff/test_tier_engine.py -v -k ks11
```

Expected: 5 tests pass.

**Behavior preflight reuse:** verify the existing QB-untouched test still passes:

```bash
uv run pytest tests/test_data/test_pff/test_tier_engine.py -v -k "team_context and qb"
```

Expected: existing tests pass (QB blending is upstream of `compute_reliability`; KS-11 doesn't touch it).

Run full suite:
```bash
uv run pytest tests/ -v 2>&1 | tail -3
```

Expected: 2,159 + 5 = 2,164 tests pass.

Commit: `test(02-06): KS-11 add 5 unit tests for tier_engine position_reliability + reuse QB-untouched preflight`
  </action>
  <verify>
    <automated>uv run pytest tests/test_data/test_pff/test_tier_engine.py -v -k "ks11 or (team_context and qb)" 2>&1 | grep -E "PASSED|FAILED" | head -10 && uv run pytest tests/ -v 2>&1 | tail -3</automated>
  </verify>
  <acceptance_criteria>
    - `tests/test_data/test_pff/test_tier_engine.py` contains all 5 `def test_ks11_*` test functions
    - `uv run pytest tests/test_data/test_pff/test_tier_engine.py -v -k ks11` exits 0
    - `uv run pytest tests/ -v` exits 0 (full suite green; 2,164 tests)
    - `git log -1 --pretty=%s` matches `test(02-06): KS-11`
  </acceptance_criteria>
</task>

<task type="auto">
  <name>Task 1b: Codex MEDIUM 6 fix — gate the `position_reliability` loader on the `ks11_position_reliability.enabled` flag (not on dict presence)</name>
  <files>
    - src/fantasy_sim/data/pff/config.py
    - tests/test_data/test_pff/test_config.py
  </files>
  <read_first>
    - src/fantasy_sim/data/pff/config.py:120-145 (`build_pff_config` — locate `position_reliability=tier_raw.get(...)` at line 138)
    - src/fantasy_sim/config/loader.py (`get_phase2_ks_flags`)
    - tests/test_data/test_pff/test_config.py (existing test patterns; create file if missing)
  </read_first>
  <behavior>
    - Codex MEDIUM 6 fix: replace the unconditional read of `tier_raw["position_reliability"]` with a flag-gated read. When `phase2_ks_flags.ks11_position_reliability.enabled=false`, the loader passes `{}` regardless of defaults.yaml content. When the flag is true, the loader reads the populated dict.
    - This makes the per-KS A/B isolation real: in the `bare` arm with the flag off, `pff.tier_engine.position_reliability` is empty even if defaults.yaml has values populated (because Plan 01 set the placeholder to `{}` but a developer might populate it before promotion for prep work).
    - Add 2 unit tests: flag-off-passes-empty, flag-on-passes-populated.
  </behavior>
  <action>
**File 1: `src/fantasy_sim/data/pff/config.py`** — replace line 138:

Find:
```python
        position_reliability=tier_raw.get("position_reliability", {}),
```

Replace with:
```python
        # Codex MEDIUM 6 fix (Phase 2 D-08 / 2026-04-27 revision): the
        # position_reliability dict is read ONLY when the KS-11 flag is on.
        # Otherwise the loader passes {} so per-KS A/B isolation is real
        # (defaults.yaml may have a populated dict pre-promotion).
        position_reliability=(
            tier_raw.get("position_reliability", {})
            if _ks11_position_reliability_enabled()
            else {}
        ),
```

At the top of `config.py` (just below the imports), add:
```python
def _ks11_position_reliability_enabled() -> bool:
    """Return True iff `phase2_ks_flags.ks11_position_reliability.enabled=true`.

    Codex MEDIUM 6 (Phase 2 / 2026-04-27): this gate replaces the legacy
    'unconditional read' behavior at config.py:138 so per-KS A/B isolation is
    real even when defaults.yaml has the position_reliability dict populated.
    """
    from fantasy_sim.config.loader import get_phase2_ks_flags
    return bool(
        get_phase2_ks_flags()
        .get("ks11_position_reliability", {})
        .get("enabled", False)
    )
```

**File 2: `tests/test_data/test_pff/test_config.py`** — create the file if missing. Add:

```python
"""Tests for build_pff_config — codex MEDIUM 6 KS-11 flag-gated loader."""

import pytest


def test_ks11_loader_passes_empty_when_flag_off(monkeypatch):
    """When the KS-11 flag is off, build_pff_config MUST pass `{}` for
    position_reliability regardless of defaults.yaml content.

    Codex MEDIUM 6 (2026-04-27): this is the per-KS A/B isolation contract.
    """
    from fantasy_sim.data.pff import config as cfg_mod
    from fantasy_sim.data.pff.config import build_pff_config

    monkeypatch.setattr(
        "fantasy_sim.config.loader.get_phase2_ks_flags",
        lambda: {"ks11_position_reliability": {"enabled": False}},
    )
    raw = {
        "tier_engine": {
            "enabled": True,
            "position_reliability": {  # populated, but flag is off — must be ignored
                "WR": {"floor": 0.30, "cap": 0.95, "min_targets": 30},
            },
        },
    }
    pff_cfg = build_pff_config(raw)
    assert pff_cfg.tier_engine.position_reliability == {}, (
        "Codex MEDIUM 6: when KS-11 flag is off, loader MUST pass {} regardless of defaults"
    )


def test_ks11_loader_passes_populated_dict_when_flag_on(monkeypatch):
    """When the KS-11 flag is on, build_pff_config passes the dict from defaults."""
    from fantasy_sim.data.pff.config import build_pff_config

    monkeypatch.setattr(
        "fantasy_sim.config.loader.get_phase2_ks_flags",
        lambda: {"ks11_position_reliability": {"enabled": True}},
    )
    raw = {
        "tier_engine": {
            "enabled": True,
            "position_reliability": {
                "WR": {"floor": 0.30, "cap": 0.95, "min_targets": 30},
            },
        },
    }
    pff_cfg = build_pff_config(raw)
    assert pff_cfg.tier_engine.position_reliability == {
        "WR": {"floor": 0.30, "cap": 0.95, "min_targets": 30},
    }
```

Run pytest:
```bash
uv run pytest tests/test_data/test_pff/test_config.py -v -k ks11
```

Expected: 2 tests pass.

Run full suite:
```bash
uv run pytest tests/ -v 2>&1 | tail -3
```

Expected: 2,164 + 2 = 2,166 tests pass.

Commit: `feat(02-06): KS-11 gate position_reliability loader on phase2_ks_flags.ks11.enabled (codex MEDIUM 6 fix)`
  </action>
  <verify>
    <automated>uv run pytest tests/test_data/test_pff/test_config.py -v -k ks11_loader 2>&1 | grep -E "PASSED|FAILED" | head -5 && grep -q "_ks11_position_reliability_enabled" src/fantasy_sim/data/pff/config.py</automated>
  </verify>
  <acceptance_criteria>
    - `src/fantasy_sim/data/pff/config.py` contains the literal string `_ks11_position_reliability_enabled`
    - `src/fantasy_sim/data/pff/config.py` contains `if _ks11_position_reliability_enabled()` near the position_reliability assignment
    - `tests/test_data/test_pff/test_config.py` contains both `def test_ks11_loader_passes_empty_when_flag_off` AND `def test_ks11_loader_passes_populated_dict_when_flag_on`
    - `uv run pytest tests/test_data/test_pff/test_config.py -v -k ks11_loader` exits 0 (2 tests pass)
    - `uv run pytest tests/ -v` exits 0 (full suite green; 2,166 tests)
    - `git log -1 --pretty=%s` matches `feat(02-06): KS-11 gate position_reliability loader`
  </acceptance_criteria>
</task>

<task type="auto">
  <name>Task 2: Run KS-11 A/B with explicit `--set pff.tier_engine.position_reliability=<dict>` overrides + promotion-state commit per D-30</name>
  <files>
    - config/defaults.yaml
    - .planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md
  </files>
  <read_first>
    - config/defaults.yaml (`pff.tier_engine.position_reliability: {}` placeholder)
  </read_first>
  <behavior>
    - For the A/B, use `--set` flags to populate `position_reliability` (NOT a defaults.yaml edit) so the per-KS A/B can flip the new code path on/off cleanly.
    - Apply Phase 1 D-30 small-gain bar: hard floor + KS Δ ≤ -0.01 on WR/TE receiving_yards (primary target).
    - If SHIPPED, edit defaults.yaml in promotion commit.
    - Verify QB pass_yards is NOT regressed (C-10 invariant).
  </behavior>
  <action>
Run A/B with explicit `--set` overrides:

```bash
uv run python scripts/validate.py \
  --sims 200 --seasons 2022 2023 2024 --scoring ppr \
  --baseline bare --arm-b-base bare \
  --set pff.enabled=true \
  --set pff.tier_engine.enabled=true \
  --set phase2_ks_flags.ks11_position_reliability.enabled=true \
  --set 'pff.tier_engine.position_reliability={"WR":{"floor":0.30,"cap":0.95,"min_targets":30},"TE":{"floor":0.30,"cap":0.95,"min_targets":30},"RB":{"floor":0.25,"cap":0.92,"min_carries":50}}' \
  --label p2.ks11.bare \
  2>&1 | tee .planning/phases/02-structural-per-stat-calibration/logs/p2_ks11_bare.log

uv run python scripts/validate.py \
  --sims 200 --seasons 2022 2023 2024 --scoring ppr \
  --baseline defaults \
  --set phase2_ks_flags.ks11_position_reliability.enabled=true \
  --set 'pff.tier_engine.position_reliability={"WR":{"floor":0.30,"cap":0.95,"min_targets":30},"TE":{"floor":0.30,"cap":0.95,"min_targets":30},"RB":{"floor":0.25,"cap":0.92,"min_carries":50}}' \
  --label p2.ks11.full \
  2>&1 | tee .planning/phases/02-structural-per-stat-calibration/logs/p2_ks11_full.log

uv run python scripts/validate.py --show-ledger | grep -E "p2.ks11"
```

(If `--set` doesn't accept JSON dicts, edit defaults.yaml in a TEMPORARY commit, run the A/B, then revert. Document the chosen mechanic in plan summary. The Phase 1 D-44 pattern allows this — the bare_config_dict already disables the WHOLE `pff.tier_engine.position_reliability` block via the parent `pff.tier_engine.enabled` gate, so injecting values via either path is safe.)

Apply D-30: hard floor + Δ stat_ks[WR][receiving_yards] ≤ -0.01 OR Δ stat_ks[TE][receiving_yards] ≤ -0.01.

Apply C-10 invariant check: Δ stat_ks[QB][pass_yards] MUST be ≥ -0.001 (QB unchanged).

Append to PROMOTION-NOTES.md:
```markdown
## KS-11 (Plan 06) — <STATUS>

**A/B results (2026-04-26):**

| Mode | Δ rank_corr | Δ weekly_mae | Δ stat_ks[WR][receiving_yards] | Δ stat_ks[TE][receiving_yards] | Δ stat_ks[QB][pass_yards] | Hard Floor | KS Δ ≤ -0.01 | C-10 (QB unchanged) |
|------|-------------|--------------|---------------------------------|---------------------------------|---------------------------|-----------|--------------|---------------------|
| bare | <val>       | <val>        | <val>                           | <val>                           | <val>                     | <PASS/FAIL> | <PASS/FAIL>  | <PASS/FAIL>         |
| full | <val>       | <val>        | <val>                           | <val>                           | <val>                     | <PASS/FAIL> | <PASS/FAIL>  | <PASS/FAIL>         |

**D-30 + C-10 evaluation:** hard floor + non-regression on primary + QB-unchanged = <PASS/FAIL>.

**Decision:** `<SHIPPED | SHIPPED-NO-OP | BLOCKED>`.
```

If SHIPPED, edit defaults.yaml `position_reliability:` block to:
```yaml
    position_reliability:
      WR:
        floor: 0.30
        cap: 0.95
        min_targets: 30
      TE:
        floor: 0.30
        cap: 0.95
        min_targets: 30
      RB:
        floor: 0.25
        cap: 0.92
        min_carries: 50
```
AND set `phase2_ks_flags.ks11_position_reliability.enabled: true`.

If SHIPPED-NO-OP / BLOCKED, defaults.yaml stays at the empty placeholder.

Commit:
```
feat(02-06): KS-11 <STATUS> per D-30 + C-10 — Δ rank_corr <val>, Δ weekly_mae <val>, Δ stat_ks[WR][rec_yds] <val>; QB pass_yards Δ <val>

Defaults: phase2_ks_flags.ks11_position_reliability.enabled=<true|false>; pff.tier_engine.position_reliability=<populated|empty>
Refs: D-08 (CONTEXT.md), HYPOTHESES.md KS-11 (lines 226-245), feedback_qb_calibration.md C-10 invariant
```
  </action>
  <verify>
    <automated>uv run python scripts/validate.py --show-ledger | grep -E "p2.ks11" | wc -l | tr -d ' ' | grep -E "^2$" && grep -q "## KS-11" .planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md && uv run pytest tests/ -v 2>&1 | tail -3</automated>
  </verify>
  <acceptance_criteria>
    - `uv run python scripts/validate.py --show-ledger | grep "^p2.ks11"` returns exactly 2 rows
    - PROMOTION-NOTES.md `## KS-11` section contains A/B table + D-30 + C-10 evaluations + Decision word
    - PROMOTION-NOTES.md `## KS-11` shows `Δ stat_ks[QB][pass_yards]` value with C-10 PASS/FAIL annotation
    - `uv run pytest tests/ -v` exits 0 (2,166 tests passing)
    - `git log -1 --pretty=%s` matches `feat(02-06): KS-11`
  </acceptance_criteria>
</task>

</tasks>

<verification>
After all 3 tasks complete (Task 1, Task 1b, Task 2):

1. `git log --oneline -10` shows 3 new commits prefixed `(02-06)`.
2. If SHIPPED: defaults.yaml has populated `position_reliability:` block.
3. `uv run pytest tests/test_data/test_pff/test_tier_engine.py tests/test_data/test_pff/test_config.py -v -k "ks11 or ks11_loader"` exits 0 (5+2=7 tests pass).
4. C-10 verified: QB Δ stat_ks[pass_yards] ≥ -0.001.
5. `uv run python scripts/validate.py --show-ledger | grep "^p2.ks11"` returns 2 rows.
6. `uv run pytest tests/ -v` exits 0; total = 2,166.
7. PROMOTION-NOTES.md `## KS-11` has D-30 + C-10 evaluations + final decision word.
8. **Codex MEDIUM 6 fix verified:** `src/fantasy_sim/data/pff/config.py` contains the `_ks11_position_reliability_enabled()` flag-gate helper; the position_reliability assignment is gated on the flag, not on dict presence.

KS-11 status recorded. Plan 07 (KS-13) may now proceed (Wave 5 in D-12).
</verification>

<must_haves>
  truths:
    - "Per D-08: WR/TE {floor: 0.30, cap: 0.95, min_targets: 30}, RB {floor: 0.25, cap: 0.92, min_carries: 50}; QB stays at global {0.20, 0.80}"
    - "Per D-02: gated behind phase2_ks_flags.ks11_position_reliability.enabled (default false)"
    - "**Codex MEDIUM 6 (2026-04-27 revision):** loader at `data/pff/config.py` keys off the `phase2_ks_flags.ks11_position_reliability.enabled` flag, NOT off dict presence. When flag off, loader passes `{}` regardless of defaults content. When flag on, loader passes the populated dict."
    - "Per C-10: QB stat_ks[pass_yards] Δ MUST be ≥ -0.001 (no regression). Failing this gate = BLOCKED regardless of other deltas."
    - "Per HYPOTHESES.md KS-11: small-medium gain, low risk; single A/B (no per-position cap sweep)"
    - "Per C-09: 2,166-test suite stays green throughout (2,159 pre-Plan-06 + 5 from Task 1 + 2 from Task 1b loader gate)"
    - "Plan 06 is mostly config-only — Task 1b adds a small loader-gate change in `data/pff/config.py` for codex MEDIUM 6"
  artifacts:
    - path: "config/defaults.yaml"
      provides: "Populated position_reliability block with D-08 values (only if SHIPPED)"
      contains: "position_reliability:"
    - path: "tests/test_data/test_pff/test_tier_engine.py"
      provides: "5 ks11 unit tests + reuse of existing test_qb_unchanged at line 848"
      contains: "def test_ks11_"
    - path: ".planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md"
      provides: "KS-11 A/B table + D-30 + C-10 evaluations + decision word"
      contains: "## KS-11"
</must_haves>

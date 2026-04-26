---
phase: 01-bug-fixes-cheap-calibration-time-sensitive-scrape
plan: 06
type: execute
wave: 3
depends_on: ["00", "01", "02"]
files_modified:
  - src/fantasy_sim/engine/play_resolver.py
  - src/fantasy_sim/data/player_builder.py
  - tests/test_engine/test_play_resolver.py
  - tests/test_data/test_player_builder.py
autonomous: true
requirements: [KS-07]
must_haves:
  truths:
    - "Per D-20: RZ_CATCH_RATE_MODIFIERS = {\"WR\": 0.92, \"TE\": 0.95, \"RB\": 0.85} replaces the single RZ_CATCH_RATE_MODIFIER = 0.92"
    - "play_resolver.py:254 uses position-aware modifier (lookup by receiver.position with WR fallback)"
    - "player_builder.py:520 uses position-aware modifier when computing per-player red_zone_catch_rate fallback"
    - "Per D-45 (Cycle 3 — Codex Cycle-2 NEW HIGH #1 fix): the positional-RZ-catch-rate change is gated behind `phase1_ks_flags.ks07_positional_rz_catch_rate.enabled` (default false until promotion). The implementations in `src/fantasy_sim/engine/play_resolver.py` and `src/fantasy_sim/data/player_builder.py` read `get_phase1_ks_flags()['ks07_positional_rz_catch_rate']` and branch: flag-on path looks up the per-position rate from `phase1_ks_flags.ks07_positional_rz_catch_rate.rates[position]` (defaults: WR=0.92, TE=0.95, RB=0.85); flag-off path uses the single legacy `RZ_CATCH_RATE_MODIFIER = 0.92`. Both A/B runs use `--set phase1_ks_flags.ks07_positional_rz_catch_rate.enabled=true`. Promotion commit flips the default to true in `config/defaults.yaml`."
    - "p1.ks07.bare and p1.ks07.full ledger entries pass hard floor (Δ rank_corr ≥ -0.005 AND Δ weekly_mae ≤ +0.05) per D-30. Both runs invoke `--set phase1_ks_flags.ks07_positional_rz_catch_rate.enabled=true` per Cycle 3 D-45."
    - "Per D-25/D-26: KS-07 commit chain ships after KS-04 lands (file overlap with play_resolver.py)"
    - "Per D-34: test-after acceptable for KS-07"
    - "Per D-35: existing 1,200+ test suite stays green throughout"
  artifacts:
    - path: "src/fantasy_sim/engine/play_resolver.py"
      provides: "RZ_CATCH_RATE_MODIFIERS dict (positional) replacing scalar; lookup at line 254"
      contains: "RZ_CATCH_RATE_MODIFIERS = {"
    - path: "src/fantasy_sim/data/player_builder.py"
      provides: "Imports RZ_CATCH_RATE_MODIFIERS and uses position-aware lookup at line 520"
      contains: "RZ_CATCH_RATE_MODIFIERS"
  key_links:
    - from: "play_resolver.py line 254 (post-KS-04)"
      to: "RZ_CATCH_RATE_MODIFIERS"
      via: "position lookup with default 0.92"
      pattern: "RZ_CATCH_RATE_MODIFIERS\\.get\\("
    - from: "player_builder.py line 520"
      to: "RZ_CATCH_RATE_MODIFIERS"
      via: "position-aware fallback when ≥10 RZ targets unavailable"
      pattern: "RZ_CATCH_RATE_MODIFIERS\\.get\\("
---

<objective>
Implement KS-07 — replace the single `RZ_CATCH_RATE_MODIFIER = 0.92` with a positional dict `RZ_CATCH_RATE_MODIFIERS = {"WR": 0.92, "TE": 0.95, "RB": 0.85}` per D-20. Update both call sites: `play_resolver.py:254` (per-play resolution) and `player_builder.py:520` (per-player fallback when <10 RZ targets).

Purpose: HYPOTHESES.md KS-07 (lines 505-517) shows TEs catch RZ targets at slightly higher rates than WRs (~95% vs ~92% of overall rate) and RBs at lower rates (~85%, due to checkdowns under pressure). Single 0.92 modifier under-estimates TE RZ production and over-estimates RB RZ production.

Output: 1 dict constant; 2 lookup sites; tests; both ledger entries pass hard floor.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-CONTEXT.md
@.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-RESEARCH.md
@.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-VALIDATION.md
@src/fantasy_sim/engine/play_resolver.py
@src/fantasy_sim/data/player_builder.py

<interfaces>
Current state:

```python
# src/fantasy_sim/engine/play_resolver.py
# Line 60:
RZ_CATCH_RATE_MODIFIER = 0.92

# Line 254 (in _resolve_pass RZ branch):
effective_catch_rate = receiver.outcomes.catch_rate * RZ_CATCH_RATE_MODIFIER
```

```python
# src/fantasy_sim/data/player_builder.py
# Line 9:
from fantasy_sim.engine.play_resolver import RZ_CATCH_RATE_MODIFIER
# Line 520:
outcomes.red_zone_catch_rate = outcomes.catch_rate * RZ_CATCH_RATE_MODIFIER
```
</interfaces>

</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Replace RZ_CATCH_RATE_MODIFIER scalar with positional dict; update call site in play_resolver.py</name>
  <files>src/fantasy_sim/engine/play_resolver.py, tests/test_engine/test_play_resolver.py</files>
  <read_first>
    - src/fantasy_sim/engine/play_resolver.py (lines 60, 254)
    - tests/test_engine/test_play_resolver.py (existing tests for RZ catch rate behavior)
    - .planning/research/HYPOTHESES.md lines 505-517 (KS-07 mechanism)
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-CONTEXT.md (D-20)
  </read_first>
  <action>
1. In `src/fantasy_sim/engine/play_resolver.py`, replace line 60:
```python
# BEFORE:
RZ_CATCH_RATE_MODIFIER = 0.92
# AFTER (D-20):
RZ_CATCH_RATE_MODIFIERS: dict[str, float] = {
    "WR": 0.92,  # KS-07: real NFL WR RZ catch rate ~92% of overall
    "TE": 0.95,  # KS-07: TEs catch RZ targets at slightly higher rates than WRs
    "RB": 0.85,  # KS-07: RBs catch RZ targets at lower rates (checkdowns under pressure)
}
# Backward compatibility shim — keep the old name pointing to the WR value for any consumers
# we may not have migrated yet (e.g., player_builder.py until Task 2 lands).
RZ_CATCH_RATE_MODIFIER = RZ_CATCH_RATE_MODIFIERS["WR"]
```

2. In the same file, around line 254 (the RZ branch in `_resolve_pass`):
```python
# BEFORE:
if effective_catch_rate <= 0 and receiver.outcomes.catch_rate > 0:
    # Only fallback when RZ rate was never computed (not a valid 0.0 from data)
    effective_catch_rate = receiver.outcomes.catch_rate * RZ_CATCH_RATE_MODIFIER
# AFTER (D-20):
if effective_catch_rate <= 0 and receiver.outcomes.catch_rate > 0:
    # Only fallback when RZ rate was never computed (not a valid 0.0 from data)
    # KS-07 D-20: position-aware modifier; default to WR value for unknown positions
    modifier = RZ_CATCH_RATE_MODIFIERS.get(receiver.position, RZ_CATCH_RATE_MODIFIERS["WR"])
    effective_catch_rate = receiver.outcomes.catch_rate * modifier
```

3. Add a test in `tests/test_engine/test_play_resolver.py`:
```python
# === KS-07: positional RZ catch rate modifiers ===

def test_ks07_rz_catch_rate_modifiers_dict():
    from fantasy_sim.engine.play_resolver import RZ_CATCH_RATE_MODIFIERS
    assert RZ_CATCH_RATE_MODIFIERS == {"WR": 0.92, "TE": 0.95, "RB": 0.85}

def test_ks07_backward_compat_scalar_unchanged():
    """Legacy RZ_CATCH_RATE_MODIFIER must equal RZ_CATCH_RATE_MODIFIERS['WR']."""
    from fantasy_sim.engine.play_resolver import RZ_CATCH_RATE_MODIFIER, RZ_CATCH_RATE_MODIFIERS
    assert RZ_CATCH_RATE_MODIFIER == RZ_CATCH_RATE_MODIFIERS["WR"] == 0.92
```

4. Run pytest:
```bash
uv run pytest tests/test_engine/test_play_resolver.py -v -k ks07
uv run pytest tests/ -v 2>&1 | tail -10
```

EXPECTED: New tests pass; existing tests pass (backward-compat scalar preserved).

Commit: `feat(01-06): KS-07 positional RZ_CATCH_RATE_MODIFIERS dict in play_resolver.py per D-20`
  </action>
  <verify>
    <automated>uv run pytest tests/test_engine/test_play_resolver.py -v -k ks07 && uv run pytest tests/ -v 2>&1 | tail -5</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c 'RZ_CATCH_RATE_MODIFIERS: dict\\[str, float\\] = {' src/fantasy_sim/engine/play_resolver.py` returns 1
    - `grep -c '"WR": 0.92' src/fantasy_sim/engine/play_resolver.py` returns 1
    - `grep -c '"TE": 0.95' src/fantasy_sim/engine/play_resolver.py` returns 1
    - `grep -c '"RB": 0.85' src/fantasy_sim/engine/play_resolver.py` returns 1
    - `grep -c "RZ_CATCH_RATE_MODIFIERS.get(receiver.position" src/fantasy_sim/engine/play_resolver.py` returns 1
    - `tests/test_engine/test_play_resolver.py` contains `def test_ks07_rz_catch_rate_modifiers_dict`
    - `uv run pytest tests/ -v 2>&1 | tail -5` shows `passed` with no `failed`
    - `git log -1 --pretty=%s` matches `feat(01-06): KS-07`
  </acceptance_criteria>
  <done>Dict added; call site updated; backward-compat scalar preserved; tests pass.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Update player_builder.py:520 to use position-aware modifier</name>
  <files>src/fantasy_sim/data/player_builder.py, tests/test_data/test_player_builder.py</files>
  <read_first>
    - src/fantasy_sim/data/player_builder.py (lines 9, 518-522)
    - tests/test_data/test_player_builder.py (existing tests for red_zone_catch_rate fallback)
  </read_first>
  <action>
1. In `src/fantasy_sim/data/player_builder.py`:

Update the import at line 9:
```python
# BEFORE:
from fantasy_sim.engine.play_resolver import RZ_CATCH_RATE_MODIFIER
# AFTER:
from fantasy_sim.engine.play_resolver import RZ_CATCH_RATE_MODIFIERS
```

Update line 520 (and surrounding context — find the function that builds player outcomes):
```python
# BEFORE (around line 520):
outcomes.red_zone_catch_rate = outcomes.catch_rate * RZ_CATCH_RATE_MODIFIER
# AFTER (D-20):
modifier = RZ_CATCH_RATE_MODIFIERS.get(player_position, RZ_CATCH_RATE_MODIFIERS["WR"])
outcomes.red_zone_catch_rate = outcomes.catch_rate * modifier
```

NOTE: `player_position` may need to be looked up from the surrounding context. Inspect the function to find the position variable name (likely `position`, `player.position`, or available in the row/dict being processed). Adapt to actual variable name.

2. Add a test in `tests/test_data/test_player_builder.py`:
```python
# === KS-07: position-aware RZ catch rate fallback ===

def test_ks07_player_builder_uses_positional_modifier():
    """When a player has < 10 RZ targets, the per-player RZ catch rate falls back
    to overall_catch_rate * RZ_CATCH_RATE_MODIFIERS[position]."""
    # Build PBP for a TE with 5 RZ targets, 3 RZ catches → not enough; falls back to .catch_rate * 0.95
    # Build PBP for an RB with 5 RZ targets, 3 RZ catches → falls back to .catch_rate * 0.85
    # Compare resulting outcomes.red_zone_catch_rate values
    pass  # adapt to actual player_builder API + fixtures
```

3. Run pytest:
```bash
uv run pytest tests/test_data/test_player_builder.py -v -k ks07
uv run pytest tests/ -v 2>&1 | tail -10
```

Commit: `feat(01-06): KS-07 player_builder.py uses positional RZ_CATCH_RATE_MODIFIERS per D-20`
  </action>
  <verify>
    <automated>uv run pytest tests/test_data/test_player_builder.py -v -k ks07 && uv run pytest tests/ -v 2>&1 | tail -5</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "from fantasy_sim.engine.play_resolver import RZ_CATCH_RATE_MODIFIERS" src/fantasy_sim/data/player_builder.py` returns 1
    - `grep -c "RZ_CATCH_RATE_MODIFIERS.get(" src/fantasy_sim/data/player_builder.py` returns 1
    - `grep -c "outcomes.catch_rate \\* RZ_CATCH_RATE_MODIFIER$" src/fantasy_sim/data/player_builder.py` returns 0 (old scalar usage removed)
    - `tests/test_data/test_player_builder.py` contains `def test_ks07_player_builder_uses_positional_modifier`
    - `uv run pytest tests/ -v 2>&1 | tail -5` shows `passed` with no `failed`
    - `git log -1 --pretty=%s` matches `feat(01-06): KS-07 player_builder`
  </acceptance_criteria>
  <done>Both call sites updated; full suite green.</done>
</task>

<task type="auto">
  <name>Task 3: A/B validate KS-07 in isolation and full-stack; commit ledger entries</name>
  <files>(no source modifications)</files>
  <read_first>
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-VALIDATION.md
    - scripts/validate.py
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-CONTEXT.md (D-29, D-30)
  </read_first>
  <action>
**REVISED Cycle 3 (D-45 — Codex Cycle-2 NEW HIGH #1 fix):** the KS-07 positional-RZ-catch-rate change is gated behind `phase1_ks_flags.ks07_positional_rz_catch_rate.enabled` (default false; set in Plan 00 Task 8). Both arms use `--set phase1_ks_flags.ks07_positional_rz_catch_rate.enabled=true` for Arm B; Arm A keeps the legacy single `RZ_CATCH_RATE_MODIFIER = 0.92` constant.

Run BOTH A/B passes per D-29:

```bash
# True isolation: bare engines + KS-07 flag overlay
uv run python scripts/validate.py \
  --sims 200 --seasons 2022 2023 2024 --scoring ppr --positions QB RB WR TE \
  --baseline bare --arm-b-base bare \
  --set "phase1_ks_flags.ks07_positional_rz_catch_rate.enabled=true" \
  --label "p1.ks07.bare"

# Full-stack overlay: defaults + KS-07 flag overlay
uv run python scripts/validate.py \
  --sims 200 --seasons 2022 2023 2024 --scoring ppr --positions QB RB WR TE \
  --baseline defaults \
  --set "phase1_ks_flags.ks07_positional_rz_catch_rate.enabled=true" \
  --label "p1.ks07.full"

uv run python scripts/validate.py --show-ledger | grep "p1.ks07"
```

NOTE: REVISED Cycle 3 — KS-07's edits to `play_resolver.py` and `player_builder.py` now branch on `phase1_ks_flags.ks07_positional_rz_catch_rate.enabled`. The Cycle-2 "no `--set` flag needed" pattern was a same-code no-op (Codex Cycle-2 NEW HIGH #1). Per-position rates are read from `phase1_ks_flags.ks07_positional_rz_catch_rate.rates` (defined in defaults.yaml) when the flag is enabled.

Capture logs to `.../logs/p1.ks07.{bare,full}.log`.

Promotion decision per D-30 (small-gain item):
- Hard floor: rank_corr Δ ≥ -0.005 AND MAE Δ ≤ +0.05 on BOTH entries
- Any non-regression KS delta on RB rush_yards primary target (≥ 0); per success criterion #3, RB rush_yards KS should recover toward ≤ 0.23

If hard floor fails → revert Tasks 1+2, document under `## KS-07` in `logs/PROMOTION-NOTES.md`, mark `## PLAN BLOCKED`.

Append `## KS-07` section to `logs/PROMOTION-NOTES.md`.

Commit: `chore(01-06): record KS-07 A/B ledger entries (p1.ks07.{bare,full})`
  </action>
  <verify>
    <automated>uv run python scripts/validate.py --show-ledger 2>&1 | grep -E "p1\.ks07\.(bare|full)" | wc -l | tr -d ' '</automated>
  </verify>
  <acceptance_criteria>
    - The verify command returns `2`
    - `uv run python scripts/validate.py --show-ledger` output contains `p1.ks07.bare` and `p1.ks07.full`
    - `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/PROMOTION-NOTES.md` contains a section header `## KS-07`
    - Both ledger entries' rank_corr regression ≥ -0.005 AND MAE regression ≤ +0.05
    - `git log -1 --pretty=%s` matches `chore(01-06): record KS-07 A/B`
  </acceptance_criteria>
  <done>Both ledger entries recorded; promotion decision documented.</done>
</task>

<task type="auto">
  <name>Task 4: Promotion-state commit + SUMMARY (per D-25 revised)</name>
  <files>(no source modifications)</files>
  <read_first>
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/PROMOTION-NOTES.md (## KS-07 section)
  </read_first>
  <action>
Per D-25 (revised), create the final promotion commit + SUMMARY. Determine state from PROMOTION-NOTES `## KS-07` section per D-30 small-gain bar.

Create `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-06-SUMMARY.md`:

```markdown
# Plan 06 Summary — KS-07 positional RZ catch rate

**Promotion state:** <PROMOTED|SHIPPED-NO-OP|BLOCKED>
**Phase:** 1
**Wave:** 3
**Final commit:** $(git log -1 --pretty=%H)

## What shipped

1. `RZ_CATCH_RATE_MODIFIERS = {"WR": 0.92, "TE": 0.95, "RB": 0.85}` per D-20
2. Per-player override in `player_builder.py:520` (≥10 RZ targets) preserved

## Ledger results

| Entry | rank_corr Δ | MAE Δ | RB rush_yards KS Δ | TE recv_yards KS Δ | Hard floor? | Promotion bar? |
|-------|-------------|-------|---------------------|---------------------|-------------|----------------|
| p1.ks07.bare | ... | ... | ... | ... | ✅/❌ | ✅/❌ |
| p1.ks07.full | ... | ... | ... | ... | ✅/❌ | ✅/❌ |
```

Commit:

```bash
PROMO_STATE="PROMOTED"  # or SHIPPED-NO-OP / BLOCKED
git add .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-06-SUMMARY.md
git commit -m "feat(01-06): KS-07 ${PROMO_STATE} — positional RZ catch rate (WR 0.92, TE 0.95, RB 0.85)

Wave 3. Bare-isolation A/B uses --baseline bare --arm-b-base bare per Plan 00."
```
  </action>
  <verify>
    <automated>test -f .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-06-SUMMARY.md && grep -cE "PROMOTED|SHIPPED-NO-OP|BLOCKED" .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-06-SUMMARY.md</automated>
  </verify>
  <acceptance_criteria>
    - SUMMARY exists with explicit promotion state header
    - SUMMARY's ledger results table is filled in
    - `git log -1 --pretty=%s` matches `feat(01-06): KS-07 PROMOTED|SHIPPED-NO-OP|BLOCKED`
  </acceptance_criteria>
  <done>KS-07 promotion-state commit landed; SUMMARY captures the decision.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| (n/a) | Pure simulation code change. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-01-06-01 | T (Tampering) | RZ_CATCH_RATE_MODIFIERS dict values | mitigate | Test enforces literal dict contents. |
| T-01-06-02 | T (Tampering) | Backward-compat scalar RZ_CATCH_RATE_MODIFIER | mitigate | Test enforces scalar == dict["WR"]. |
</threat_model>

<verification>
- KS-07 tests pass
- `RZ_CATCH_RATE_MODIFIERS` dict in play_resolver; both call sites use positional lookup
- `p1.ks07.bare` and `p1.ks07.full` ledger entries exist
- Promotion decision documented
</verification>

<success_criteria>
- KS-07 requirement deliverable
- Hard floor passes on both ledger entries (or BLOCKED + reverted)
- RB rush_yards KS delta ≥ 0 on `p1.ks07.full` (per success criterion #3)
- 1,200+ existing test suite still green
</success_criteria>

<output>
After completion, create `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-06-SUMMARY.md`.
</output>

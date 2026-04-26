---
phase: 01-bug-fixes-cheap-calibration-time-sensitive-scrape
plan: 08
type: execute
wave: 5
depends_on: ["00", "01", "02", "03", "04", "05", "06", "07"]
files_modified:
  - config/defaults.yaml
autonomous: true
requirements: [KS-29]
must_haves:
  truths:
    - "Per D-21: pff.team_context.enabled = true and pass_rate_sensitivity sweep over {0.03, 0.05, 0.08} (3 sensitivities × 2 modes = 6 ledger entries)"
    - "Per D-22: team_context layer must NOT blend QB carry_share / scramble_rate / yards (per feedback_qb_calibration.md memory) — verify by inspecting tier_engine.apply_team_context"
    - "Best-of-3 sensitivity selected and committed to defaults.yaml AFTER sweep results"
    - "p1.ks29.s{003,005,008}.{bare,full} ledger entries pass hard floor (Δ rank_corr ≥ -0.005 AND Δ weekly_mae ≤ +0.05) per D-30"
    - "Per D-25/D-26: KS-29 commit chain ships after all earlier KS items land (D-26: KS-29 sits late in the sequence; independent code-wise but sequenced for clean ledger)"
    - "Per D-34: test-after acceptable for KS-29 (existing test suite covers tier_engine; new tests target team_context-enabled branch)"
    - "Per D-35: existing 1,200+ test suite stays green throughout"
  artifacts:
    - path: "config/defaults.yaml"
      provides: "pff.team_context.enabled = true with chosen sensitivity"
      contains: "team_context"
  key_links:
    - from: "pff.team_context.enabled"
      to: "tier_engine.apply_team_context"
      via: "config-driven flag flip"
      pattern: "team_context:\\s*\\n\\s*enabled:\\s*true"
---

<objective>
Implement KS-29 — re-enable `pff.team_context` (currently `enabled: false` per `config/defaults.yaml:104`) and sweep `pass_rate_sensitivity` over {0.03, 0.05, 0.08} to find the best within hard floor (D-21). Coordinate with `feedback_qb_calibration.md`: team_context must NOT blend QB carry/scramble/yards (D-22).

Purpose: HYPOTHESES.md KS-29 (lines 519-531) shows team_context's season-level pass-rate→target_share signal is currently disabled with sensitivity=0.0. Re-enabling captures team-environment effects (high-volume passing teams, run-heavy teams, OL-pass-block quality) that should improve WR/TE projection rank_corr.

Output: 6 ledger entries (sweep × modes); defaults.yaml updated with the chosen sensitivity; both isolation+full entries for the chosen sensitivity pass hard floor.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-CONTEXT.md
@.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-RESEARCH.md
@.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-VALIDATION.md
@config/defaults.yaml
@src/fantasy_sim/data/pff/tier_engine.py

<interfaces>
Current state of `config/defaults.yaml` lines 103-110:
```yaml
  team_context:
    enabled: false
    pass_rate_sensitivity: 0.0
    ol_run_sensitivity: 0.06
    qb_quality_sensitivity: 0.05
    factor_clamp: [0.90, 1.10]
    min_games: 4
    ol_run_yards_scale: 10.0
```

The sweep changes `enabled: true` and `pass_rate_sensitivity` to {0.03, 0.05, 0.08}. Other fields stay as-is per D-21 (only the sensitivity is swept).

Pre-flight verification: `tier_engine.apply_team_context` at `src/fantasy_sim/data/pff/tier_engine.py:1196-1215` must NOT touch QB carry_share/scramble_rate/yards. Inspect to confirm before running the sweep — if it does, file as a blocker (D-22).
</interfaces>

</context>

<tasks>

<task type="auto">
  <name>Task 1: Pre-flight — verify tier_engine.apply_team_context honors D-22 (no QB carry/scramble/yards blending)</name>
  <files>(no source modifications — inspection + behavior-test re-run)</files>
  <read_first>
    - src/fantasy_sim/data/pff/tier_engine.py (lines around 1196-1215 — apply_team_context function)
    - tests/test_data/test_pff/test_tier_engine.py (line ~848 — existing QB-untouched test asserting apply_team_context leaves QBs unchanged; per Codex LOW-2 from 01-REVIEWS.md)
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-CONTEXT.md (D-22, D-43)
    - User memory `feedback_qb_calibration.md` (PFF layers must NOT blend QB carry_share / scramble_rate / yards)
  </read_first>
  <action>
**REVISED 2026-04-26 (LOW-2 fix from `01-REVIEWS.md`):** Replace the original ad-hoc grep preflight with a behavior-level check using the existing `test_tier_engine.py:848` test that already asserts `apply_team_context` leaves QBs unchanged. Per D-43 (acceptance checks tightened to behavior-level assertions), running an existing test is a more reliable preflight than literal-string grep over `tier_engine.py`.

```bash
# Behavior-level preflight: re-run the existing tier_engine QB-untouched test.
# This is a stronger guarantee than grep-inspection because it actually exercises
# apply_team_context end-to-end with a QB present in the roster.
uv run pytest tests/test_data/test_pff/test_tier_engine.py -v -k "team_context and qb" 2>&1 | tee \
  .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/ks29_preflight.log
```

EXPECTED: The existing test(s) at `tests/test_data/test_pff/test_tier_engine.py` (around line 848) PASS, confirming `apply_team_context` does not mutate QB `carry_share`, `scramble_rate`, or `rushing_yards_dist`.

If the test fails or no such test is found:
1. Inspect `tests/test_data/test_pff/test_tier_engine.py` for any test name containing `qb` AND `team_context` — adjust the `-k` filter to match the actual test name
2. If no such test exists, FALL BACK to the original grep approach AND add a new behavior-test as part of this preflight task (following the canonical pattern at `test_tier_engine.py:848`-area). Commit the new test before proceeding to Task 2.
3. If the test exists and FAILS, the function violates D-22 — record under `## KS-29 — BLOCKED PRE-FLIGHT` in PROMOTION-NOTES.md and STOP. Fix in `tier_engine.py` would be out of scope for this plan (raise as follow-up).

Append to `.../logs/PROMOTION-NOTES.md` under `## KS-29 — pre-flight passed` (or `BLOCKED PRE-FLIGHT`):

```markdown
## KS-29 — pre-flight passed

Behavior test: tests/test_data/test_pff/test_tier_engine.py (around :848) PASSED.
Confirms apply_team_context does not mutate QB carry_share / scramble_rate / rushing_yards_dist.

Codex LOW-2 fix: replaced ad-hoc grep preflight with the existing behavior-level
test that already asserts QBs are untouched.
```

Commit (only the PROMOTION-NOTES update + log file): `chore(01-08): KS-29 pre-flight — re-run existing tier_engine QB-untouched test (Codex LOW-2 fix)`
  </action>
  <verify>
    <automated>uv run pytest tests/test_data/test_pff/test_tier_engine.py -v -k "team_context and qb" 2>&1 | tail -5 && test -f .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/PROMOTION-NOTES.md && grep -c "## KS-29" .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/PROMOTION-NOTES.md</automated>
  </verify>
  <acceptance_criteria>
    - `uv run pytest tests/test_data/test_pff/test_tier_engine.py -v -k "team_context and qb"` exits 0 (existing behavior test passes)
    - `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/ks29_preflight.log` exists with the test output
    - PROMOTION-NOTES.md contains `## KS-29` with pre-flight result documented
    - If test FAILED: PROMOTION-NOTES contains `BLOCKED PRE-FLIGHT` AND plan is halted
    - `git log -1 --pretty=%s` matches `chore(01-08): KS-29 pre-flight`
  </acceptance_criteria>
  <done>D-22 compliance verified via behavior test (or violation documented); plan proceeds or halts.</done>
</task>

<task type="auto">
  <name>Task 2: Run the 3×2 sensitivity sweep (6 A/B runs); collect ledger entries</name>
  <files>(no source modifications)</files>
  <read_first>
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-VALIDATION.md (KS-29 sweep mechanics)
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-CONTEXT.md (D-21, D-29)
    - scripts/validate.py (--set CLI usage)
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/PROMOTION-NOTES.md (ensure pre-flight passed)
  </read_first>
  <action>
Run the full sweep — 3 sensitivities × 2 baseline modes = 6 `validate.py` invocations (revised 2026-04-26 per D-29 — uses Plan 00's `--arm-b-base bare` for true isolation in the bare runs; full runs use the default arm-b-base of `defaults`):

```bash
# Sensitivity sweep — 6 A/B runs total
for s_str in "003 0.03" "005 0.05" "008 0.08"; do
  s_label=$(echo $s_str | cut -d' ' -f1)
  s_value=$(echo $s_str | cut -d' ' -f2)
  for mode in bare full; do
    label="p1.ks29.s${s_label}.${mode}"
    echo "=== Running ${label} ===" >&2
    if [ "$mode" = "bare" ]; then
      # True isolation: bare engines + ONLY KS-29 team_context on top
      # NOTE: tier_engine may need to be enabled too if team_context depends on it.
      # Inspect load_pff_config for the dependency; add --set pff.tier_engine.enabled=true if so.
      uv run python scripts/validate.py \
        --sims 200 \
        --seasons 2022 2023 2024 \
        --scoring ppr \
        --positions QB RB WR TE \
        --baseline bare --arm-b-base bare \
        --set "pff.team_context.enabled=true" \
        --set "pff.team_context.pass_rate_sensitivity=${s_value}" \
        --label "$label" \
        2>&1 | tee ".planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/${label}.log"
    else
      # Full-stack: promoted defaults + KS-29 sensitivity overlay
      uv run python scripts/validate.py \
        --sims 200 \
        --seasons 2022 2023 2024 \
        --scoring ppr \
        --positions QB RB WR TE \
        --baseline defaults \
        --set "pff.team_context.enabled=true" \
        --set "pff.team_context.pass_rate_sensitivity=${s_value}" \
        --label "$label" \
        2>&1 | tee ".planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/${label}.log"
    fi
  done
done

uv run python scripts/validate.py --show-ledger | grep "p1.ks29"
```

Per D-21, RESEARCH.md Pitfall 5 notes wall-clock budget — each run is ~30 min, total ~3 hours. If wall-clock is constrained, drop sweep sims to 100 and re-validate the chosen sensitivity at 200 (this plan defaults to 200; the optimization is discretion).

Append the sweep results table to `.../logs/PROMOTION-NOTES.md` under `## KS-29 sweep`:

```markdown
## KS-29 sweep results

| Label | rank_corr Δ | MAE Δ | KS Δ (WR rec_yds) | Hard floor | Notes |
|-------|------------|-------|-------------------|-----------|-------|
| p1.ks29.s003.bare | ... | ... | ... | PASS/FAIL | ... |
| p1.ks29.s003.full | ... | ... | ... | PASS/FAIL | ... |
| p1.ks29.s005.bare | ... | ... | ... | PASS/FAIL | ... |
| p1.ks29.s005.full | ... | ... | ... | PASS/FAIL | ... |
| p1.ks29.s008.bare | ... | ... | ... | PASS/FAIL | ... |
| p1.ks29.s008.full | ... | ... | ... | PASS/FAIL | ... |
```

Pick the best sensitivity per D-30 (small-gain promotion bar):
1. Filter to sensitivities where BOTH `bare` AND `full` rows pass hard floor
2. Among those, pick the sensitivity with the best `rank_corr Δ` improvement on the `full` row
3. Tiebreaker: best WR/TE receiving_yards KS Δ on the `full` row

If no sensitivity passes hard floor on both bare and full → mark `## KS-29 — SHIPPED OFF` (keep `enabled: false` in defaults; KS-29 requirement remains "delivered" per REQUIREMENTS.md "delivered" definition because the change is "implemented + tested + ledgered + promotion decision documented" — and the promotion decision is "do not promote").

Commit (sweep results only, no code changes yet): `chore(01-08): KS-29 sensitivity sweep — 6 ledger entries (s003, s005, s008 × bare, full)`
  </action>
  <verify>
    <automated>uv run python scripts/validate.py --show-ledger 2>&1 | grep -E "p1\.ks29\.(s003|s005|s008)\.(bare|full)" | wc -l | tr -d ' '</automated>
  </verify>
  <acceptance_criteria>
    - The verify command returns `6` (3 sensitivities × 2 modes)
    - `uv run python scripts/validate.py --show-ledger` output contains all 6 labels: `p1.ks29.s003.bare`, `p1.ks29.s003.full`, `p1.ks29.s005.bare`, `p1.ks29.s005.full`, `p1.ks29.s008.bare`, `p1.ks29.s008.full`
    - `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/PROMOTION-NOTES.md` contains the sweep results table under `## KS-29 sweep results`
    - Best sensitivity selected and recorded (or SHIPPED OFF documented)
    - `git log -1 --pretty=%s` matches `chore(01-08): KS-29 sensitivity sweep`
  </acceptance_criteria>
  <done>Sweep complete; 6 ledger entries; best sensitivity picked or SHIPPED OFF documented.</done>
</task>

<task type="auto">
  <name>Task 3: Promote chosen sensitivity to config/defaults.yaml (or document SHIPPED OFF)</name>
  <files>config/defaults.yaml</files>
  <read_first>
    - config/defaults.yaml (lines 103-110)
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/PROMOTION-NOTES.md (chosen sensitivity from Task 2)
  </read_first>
  <action>
Based on Task 2's chosen sensitivity, edit `config/defaults.yaml` lines 103-110:

```yaml
# BEFORE:
  team_context:
    enabled: false
    pass_rate_sensitivity: 0.0
    ol_run_sensitivity: 0.06
    qb_quality_sensitivity: 0.05
    factor_clamp: [0.90, 1.10]
    min_games: 4
    ol_run_yards_scale: 10.0

# AFTER (D-21; substitute the CHOSEN sensitivity in the value):
  team_context:
    enabled: true
    pass_rate_sensitivity: <CHOSEN_VALUE>  # KS-29 D-21: chosen from sweep {0.03, 0.05, 0.08}
    ol_run_sensitivity: 0.06
    qb_quality_sensitivity: 0.05
    factor_clamp: [0.90, 1.10]
    min_games: 4
    ol_run_yards_scale: 10.0
```

If Task 2 returned SHIPPED OFF (no sensitivity passed both modes' hard floor), DO NOT modify defaults.yaml. Instead, append a note to `.../logs/PROMOTION-NOTES.md` under `## KS-29 — final decision: SHIPPED OFF` with rationale (best ledger entry's regressing metric).

Run pytest:
```bash
uv run pytest tests/ -v 2>&1 | tail -10
```

EXPECTED: All tests pass (config change shouldn't break unit tests; only behavior in integration/statistical tests).

Commit (per D-25 revised — promotion-state commit message format):
- If sensitivity chosen: `feat(01-08): KS-29 PROMOTED — pff.team_context.enabled=true with pass_rate_sensitivity=<VALUE>`
- If SHIPPED OFF: `feat(01-08): KS-29 SHIPPED-OFF — team_context kept disabled (no sensitivity met hard floor)`

Also create `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-08-SUMMARY.md`:

```markdown
# Plan 08 Summary — KS-29 pff.team_context re-enable

**Promotion state:** <PROMOTED|SHIPPED-OFF|BLOCKED>
**Phase:** 1
**Wave:** 5
**Final commit:** $(git log -1 --pretty=%H)

## What shipped

- Pre-flight: existing `tests/test_data/test_pff/test_tier_engine.py:848` test rerun, confirms apply_team_context leaves QBs unchanged (Codex LOW-2 fix)
- Sensitivity sweep: 6 ledger entries (s003, s005, s008 × bare, full) using --baseline bare --arm-b-base bare for the bare runs (Codex HIGH-1 fix)
- Chosen sensitivity: <VALUE> (or SHIPPED-OFF if no sensitivity met both hard floors)

## Sweep results

| Sensitivity | bare rank_corr Δ | bare MAE Δ | full rank_corr Δ | full MAE Δ | Hard floor (both)? |
|-------------|------------------|------------|------------------|------------|---------------------|
| 0.03 | ... | ... | ... | ... | ✅/❌ |
| 0.05 | ... | ... | ... | ... | ✅/❌ |
| 0.08 | ... | ... | ... | ... | ✅/❌ |
```
  </action>
  <verify>
    <automated>(grep -E "team_context:" config/defaults.yaml -A 7 | head -10) && uv run pytest tests/ -v 2>&1 | tail -5</automated>
  </verify>
  <acceptance_criteria>
    - If sensitivity chosen: `grep -A 1 "team_context:" config/defaults.yaml | grep "enabled: true"` returns 1 hit
    - If sensitivity chosen: `grep "pass_rate_sensitivity:" config/defaults.yaml` returns the chosen value (NOT 0.0)
    - If SHIPPED OFF: `grep "pass_rate_sensitivity: 0.0" config/defaults.yaml` returns 1 hit (unchanged) AND PROMOTION-NOTES contains `## KS-29 — final decision: SHIPPED OFF`
    - `uv run pytest tests/ -v 2>&1 | tail -5` shows `passed` with no `failed`
    - `git log -1 --pretty=%s` matches `feat(01-08): KS-29` OR `docs(01-08): KS-29`
  </acceptance_criteria>
  <done>Final config promoted (or SHIPPED OFF documented); tests still pass.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| (n/a) | Config flag flip; no new external boundary. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-01-08-01 | T (Tampering) | QB calibration discipline (D-22) | mitigate | Task 1 pre-flight inspects `tier_engine.apply_team_context` for QB carry/scramble/yards blending — blocks if violated. |
| T-01-08-02 | T (Tampering) | Sensitivity sweep selection bias | mitigate | Sweep covers 3 values; selection rule is hard-floor-first then best rank_corr improvement (no overfitting to single metric). |
</threat_model>

<verification>
- D-22 pre-flight passed (Task 1 PROMOTION-NOTES note)
- 6 ledger entries exist for the sweep
- Either: defaults.yaml has `team_context.enabled: true` with chosen sensitivity, OR PROMOTION-NOTES documents SHIPPED OFF
- 1,200+ existing test suite still green
</verification>

<success_criteria>
- KS-29 requirement deliverable per REQUIREMENTS.md "delivered" definition (implementation + tests + ledgered + promotion decision)
- Hard floor passes on chosen sensitivity's BOTH ledger entries (or SHIPPED OFF documented)
- WR/TE receiving_yards KS Δ ≥ 0 on chosen sensitivity's `full` entry (per D-30)
- D-22 honored — team_context did not blend QB carry/scramble/yards
</success_criteria>

<output>
After completion, create `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-08-SUMMARY.md`.
</output>

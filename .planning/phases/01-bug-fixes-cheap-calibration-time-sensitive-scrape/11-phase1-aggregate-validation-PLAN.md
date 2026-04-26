---
phase: 01-bug-fixes-cheap-calibration-time-sensitive-scrape
plan: 11
type: execute
wave: 7
depends_on: ["01", "02", "03", "04", "05", "06", "07", "08", "09", "10"]
files_modified: []
autonomous: true
requirements: [KS-01, KS-03, KS-04, KS-05, KS-06, KS-07, KS-15, KS-29, KS-32]
must_haves:
  truths:
    - "Per D-32: a single p1.aggregate.full A/B run after all 9 KS items have shipped, comparing post-Phase-1 defaults vs original Phase-0 baseline; confirms no stack regression"
    - "Records Phase 1 entry/exit metrics for the next phase to baseline against"
    - "If any regression appears, walk back the smallest-gain promotion candidate first per D-32"
    - "Phase 1 success criteria 1-4 (QB pass_yards bias, QB pass_yards KS, RB rush_yards KS, hard floor across positions) verified against the aggregate ledger entry"
    - "Phase 1 success criterion 5 (KS-21 alt-line scrape) verified by Plan 09's 9 parquet caches existing"
    - "Per D-27: ledger label scheme — p1.ksXX.bare and p1.ksXX.full per change; KS-29 sweep adds p1.ks29.s003.bare/.full, p1.ks29.s005.bare/.full, p1.ks29.s008.bare/.full; KS-32 measurement adds p1.ks32.measure if no change is needed; aggregate adds p1.aggregate.full"
    - "Per D-28: validation set = all 2022-2024, 200 sims/season, PPR scoring across all per-plan and aggregate runs"
    - "Per D-29: A/B mode per change = isolation + full-stack (baseline+X AND all_engines+X); both modes ran before promotion for every KS plan; agents executed scripts/validate.py directly per the 2026-04-26 rule reversal"
  artifacts:
    - path: ".planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/PROMOTION-NOTES.md"
      provides: "## Phase 1 aggregate section with metric deltas vs Phase-0 baseline and success-criteria evaluation"
      contains: "## Phase 1 aggregate"
  key_links:
    - from: "p1.aggregate.full ledger entry"
      to: "ROADMAP success criteria 1-4"
      via: "rank_corr Δ ≥ -0.005, MAE Δ ≤ +0.05, QB pass_yards KS ≤ 0.28, RB rush_yards KS ≤ 0.23"
      pattern: "p1\\.aggregate\\.full"
---

<objective>
Implement the end-of-phase aggregate validation per D-32. Run a single `validate.py` invocation labeled `p1.aggregate.full` against the post-Phase-1 promoted defaults, comparing to the original Phase-0 baseline. Confirm no stack regression and record Phase 1's exit metrics as the baseline for Phase 2.

Per D-32: "If any regression appears, walk back the smallest-gain promotion candidate first." This task surfaces such regressions and proposes the rollback target if needed.

Per ROADMAP success criteria 1-4 + RESEARCH.md `## Validation Architecture`:
- **Success criterion 1 (QB pass_yards mean bias):** narrowed from ~−28 yd/game to within ±10 yd/game across 2022-2024
- **Success criterion 2 (QB pass_yards KS):** dropped from ~0.36 to ≤ 0.28 across 2022-2024
- **Success criterion 3 (RB rush_yards KS):** recovers from defaults' 0.26 regression back to ≤ 0.23
- **Success criterion 4 (hard floor across all positions):** rank_corr regression ≤ 0.005 AND MAE regression ≤ 0.05 vs prior promoted defaults

Success criterion 5 (KS-21 alt-line scrape) is verified separately by Plan 09's 9 parquet outputs.

Output: `p1.aggregate.full` ledger entry; PROMOTION-NOTES.md `## Phase 1 aggregate` section evaluating each success criterion against the metrics.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-CONTEXT.md
@.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-RESEARCH.md
@.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-VALIDATION.md
@.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/PROMOTION-NOTES.md
@.planning/ROADMAP.md
@.planning/PROJECT.md
@scripts/validate.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Run p1.aggregate.full A/B vs Phase-0 baseline; verify success criteria 1-4</name>
  <files>(no source modifications)</files>
  <read_first>
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-VALIDATION.md (aggregate validation criteria)
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-CONTEXT.md (D-32)
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/PROMOTION-NOTES.md (per-KS promotion decisions)
    - .planning/ROADMAP.md §"Phase 1" success criteria
    - scripts/validate.py
  </read_first>
  <action>
Confirm all 9 KS plans have completed (PROMOTION-NOTES.md should have `## KS-01` through `## KS-32` sections, plus `## KS-21 full scrape`). KS items may be PROMOTED, SHIPPED NO-OP, BLOCKED, or SHIPPED OFF — all are acceptable terminal states for Phase 1 closure.

Run the aggregate A/B:

```bash
uv run python scripts/validate.py \
  --sims 200 \
  --seasons 2022 2023 2024 \
  --scoring ppr \
  --positions QB RB WR TE \
  --baseline defaults \
  --label "p1.aggregate.full" \
  2>&1 | tee .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/p1.aggregate.full.log

uv run python scripts/validate.py --show-ledger | grep "p1.aggregate"
```

NOTE: This is a baseline-vs-baseline run (no `--set` flags). The `--baseline defaults` arm IS the post-Phase-1 promoted state; the Arm B in this case mirrors Arm A. The harness produces a ledger row that records the CURRENT post-Phase-1 baseline metrics as a snapshot — this is what becomes the Phase 2 baseline.

For the comparison to Phase-0 baseline, inspect the existing ledger for the most-recent pre-Phase-1 baseline entry (e.g., the `decision_s200` baseline entry that's been the historical reference). The harness logs deltas between Arm A and Arm B; for the snapshot purpose, the headline metrics (rank_corr, MAE, position-by-stat KS) are read from Arm A directly.

Now extract the comparison-to-Phase-0 metrics. The Phase-0 baseline is recorded in `.planning/PROJECT.md` outcome targets (TGT-01..TGT-10) — current values shown there are the pre-Phase-1 values:
- QB pass_yards KS ~0.36 → target ≤ 0.20 (Phase 1 intermediate target ≤ 0.28)
- WR receiving_yards KS ~0.26 → target ≤ 0.20
- RB rush_yards KS ~0.26 → target ≤ 0.22 (Phase 1 intermediate target ≤ 0.23)
- QB pass_yards mean bias -28 yd/g → target ±5 yd/g (Phase 1 target ±10 yd/g)

Append `## Phase 1 aggregate` to PROMOTION-NOTES.md:

```markdown
## Phase 1 aggregate (p1.aggregate.full)

**Run:** validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline defaults --label p1.aggregate.full

### Headline metrics (post-Phase-1 baseline)

| Metric | Pre-Phase-1 (PROJECT.md current) | Post-Phase-1 (this run) | Δ | Phase-1 target | Met? |
|--------|----------------------------------|------------------------|---|----------------|------|
| QB pass_yards mean bias (yd/g) | -28 | ... | ... | within ±10 | YES/NO |
| QB pass_yards KS | 0.36 | ... | ... | ≤ 0.28 | YES/NO |
| RB rush_yards KS | 0.26 | ... | ... | ≤ 0.23 | YES/NO |
| Aggregate rank_corr (PPR) | (Phase-0 value from ledger) | ... | ... | Δ ≥ -0.005 | YES/NO |
| Aggregate weekly_mae (PPR) | (Phase-0 value from ledger) | ... | ... | Δ ≤ +0.05 | YES/NO |

### Per-position KS table (Phase 1 exit baseline)

| Position | Stat | Pre-Phase-1 | Post-Phase-1 | Δ |
|----------|------|-------------|--------------|---|
| QB | pass_yards | ~0.36 | ... | ... |
| QB | rush_yards | ... | ... | ... |
| RB | rush_yards | ~0.26 | ... | ... |
| RB | receiving_yards | ~0.42 | ... | ... |
| WR | receptions | ~0.28 | ... | ... |
| WR | receiving_yards | ~0.26 | ... | ... |
| TE | receptions | ~0.35 | ... | ... |
| TE | receiving_yards | ~0.31 | ... | ... |

### Success criteria evaluation

- [ ] **Criterion 1** (QB pass_yards bias ±10 yd/g): YES/NO
- [ ] **Criterion 2** (QB pass_yards KS ≤ 0.28): YES/NO
- [ ] **Criterion 3** (RB rush_yards KS ≤ 0.23): YES/NO
- [ ] **Criterion 4** (hard floor: rank_corr Δ ≥ -0.005 AND MAE Δ ≤ +0.05): YES/NO
- [ ] **Criterion 5** (KS-21 alt-line scrape — verified separately by Plan 09): YES (9 parquet caches confirmed exist)

### Decision

If all 5 criteria met → Phase 1 COMPLETE; this is the new Phase 2 baseline.
If any criterion missed → record the smallest-gain promotion candidate to walk back per D-32:
- Smallest-gain candidates (in order): KS-32 (if RETUNE branch), KS-29 sweep choice, KS-07, KS-06
- Walk back by reverting the relevant config change or commit, then re-run p1.aggregate.full
```

Commit: `chore(01-11): KS-Phase1 aggregate ledger entry (p1.aggregate.full)`
  </action>
  <verify>
    <automated>uv run python scripts/validate.py --show-ledger 2>&1 | grep -E "p1\.aggregate\.full" | wc -l | tr -d ' '</automated>
  </verify>
  <acceptance_criteria>
    - The verify command returns at least `1` (p1.aggregate.full ledger entry exists)
    - `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/p1.aggregate.full.log` exists
    - PROMOTION-NOTES.md contains `## Phase 1 aggregate` with the 5 success criteria evaluated YES/NO and the headline metrics filled in
    - If any criterion is NO: PROMOTION-NOTES contains the walk-back proposal naming the smallest-gain candidate
    - `git log -1 --pretty=%s` matches `chore(01-11): KS-Phase1 aggregate`
  </acceptance_criteria>
  <done>p1.aggregate.full ledger entry recorded; success criteria evaluated; walk-back proposal documented if needed.</done>
</task>

<task type="auto">
  <name>Task 2: Update PROJECT.md TGT-XX current values to reflect Phase 1 exit metrics</name>
  <files>.planning/PROJECT.md</files>
  <read_first>
    - .planning/PROJECT.md (current TGT-XX table)
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/PROMOTION-NOTES.md (Task 1 headline metrics)
  </read_first>
  <action>
Update the TGT-XX outcome targets table in `.planning/PROJECT.md` to reflect the post-Phase-1 baseline.

Find the table that lists TGT-01..TGT-10 with `Current` and `Target` columns. Replace the `Current` values with the post-Phase-1 metrics from Task 1's PROMOTION-NOTES section. Preserve the `Target` values unchanged.

Example update (using placeholder post-Phase-1 values; substitute actuals from Task 1):
```markdown
| ID | Description | Current (post-Phase-1) | Target |
|----|-------------|------------------------|--------|
| TGT-01 | QB pass_yards KS | <new value> | ≤ 0.20 |
| TGT-02 | WR receiving_yards KS | <new value> | ≤ 0.20 |
| TGT-09 | QB pass_yards mean bias | <new value> | ±5 yd/g |
| TGT-10 | WR receiving_yards mean bias | <new value> | ±2 yd/g |
| ...
```

NOTE: PROJECT.md update is NOT a pre-condition for Phase 1 closure — the ledger entry IS the canonical record. PROJECT.md update is a consistency / documentation update so the next phase planner has the right baseline visible.

Commit: `docs(01-11): update PROJECT.md TGT-XX current values to post-Phase-1 baseline`
  </action>
  <verify>
    <automated>git diff HEAD~1 .planning/PROJECT.md 2>&1 | grep -E "^[+-]" | wc -l | tr -d ' '</automated>
  </verify>
  <acceptance_criteria>
    - `.planning/PROJECT.md` modified — diff against HEAD~1 shows changes to the TGT-XX table
    - The `Current` column for TGT-01, TGT-02, TGT-09, TGT-10 reflects post-Phase-1 values from Task 1's PROMOTION-NOTES
    - The `Target` column is unchanged
    - `git log -1 --pretty=%s` matches `docs(01-11): update PROJECT.md`
  </acceptance_criteria>
  <done>PROJECT.md TGT-XX table reflects Phase 1 exit baseline.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| (n/a) | Aggregate validation only; no code changes. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-01-11-01 | T (Tampering) | Phase 1 success criteria evaluation | mitigate | Task 1 spells out each criterion as a YES/NO checkbox tied to specific metric thresholds — no ambiguity. |
| T-01-11-02 | T (Tampering) | Walk-back order if criteria missed | mitigate | D-32 specifies "smallest-gain promotion candidate first"; Task 1 names the candidate explicitly. |
| T-01-11-03 | I (Information disclosure) | PROJECT.md baseline update | accept | PROJECT.md is a planning artifact; values are aggregated metrics, no PII. |
</threat_model>

<verification>
- p1.aggregate.full ledger entry exists
- PROMOTION-NOTES.md `## Phase 1 aggregate` section evaluates all 5 success criteria
- PROJECT.md TGT-XX `Current` values reflect post-Phase-1 baseline
- 1,200+ existing test suite still green
</verification>

<success_criteria>
- All 9 KS-XX requirements deliverable per REQUIREMENTS.md "delivered" definition (each has its own per-plan SUMMARY + per-KS PROMOTION-NOTES section)
- Phase 1 ROADMAP success criteria 1-5 evaluated and recorded
- Phase 2 baseline established (PROJECT.md updated; ledger snapshot p1.aggregate.full)
- If any criterion missed: walk-back candidate identified per D-32
</success_criteria>

<output>
After completion, create `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-11-SUMMARY.md`. This SUMMARY also serves as the **Phase 1 closure report** — include a section listing each KS-XX deliverable's outcome (PROMOTED / SHIPPED NO-OP / BLOCKED / SHIPPED OFF / MEASURED-NO-CHANGE) so STATE.md and ROADMAP.md updates have a single source of truth.
</output>

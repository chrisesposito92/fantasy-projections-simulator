---
phase: 01-bug-fixes-cheap-calibration-time-sensitive-scrape
plan: 11
type: execute
wave: 7
depends_on: ["00", "01", "02", "03", "04", "05", "06", "07", "08", "09", "10"]
files_modified:
  - .planning/PROJECT.md
autonomous: true
requirements: [KS-01, KS-03, KS-04, KS-05, KS-06, KS-07, KS-15, KS-29, KS-32]
must_haves:
  truths:
    - "Per D-32 (revised 2026-04-26 — addresses Codex HIGH-4): end-of-phase aggregate runs `validate.py --baseline bare --label p1.aggregate.full` (NO --set), capturing post-Phase-1 promoted defaults' metrics in Arm B. The Phase-1-vs-Phase-0 delta is computed by reading BOTH `phase0.baseline.full` (pinned in Wave 0 by Plan 00) AND `p1.aggregate.full` (this plan) from the ledger and differencing the Arm B metrics."
    - "Per D-46 (Cycle 3 — addresses Codex Cycle-2 NEW HIGH #3): mean bias is read directly from the extended ledger schema (`SeasonMetrics.stat_mean_bias`, schema v5) shipped by Plan 00 Task 9. The delta script reads `stat_mean_bias['QB']['pass_yards']['arm_b_bias']` from both `phase0.baseline.full` and `p1.aggregate.full` ledger entries and differences them. No re-simulation; no side script."
    - "The original Plan 11 ran `validate.py --baseline defaults` with no `--set`, producing Arm A == Arm B (a no-op snapshot, not a delta). This was Codex HIGH-4 and is now resolved."
    - "Per D-32b: Plan 00 must have landed (phase0.baseline.full ledger entry exists, schema v5 with stat_mean_bias populated) BEFORE this plan can compute the comparison."
    - "Records Phase 1 entry/exit metrics for the next phase to baseline against (PROJECT.md TGT-XX update)"
    - "If any regression appears in the Phase-1-vs-Phase-0 delta, walk back the smallest-gain promotion candidate first per D-32"
    - "Phase 1 success criteria 1-4 (QB pass_yards bias, QB pass_yards KS, RB rush_yards KS, hard floor across positions) verified against the differenced delta — criterion 1 specifically reads from the new `stat_mean_bias` ledger field, NOT from a re-simulated diagnostic"
    - "Phase 1 success criterion 5 (KS-21 alt-line scrape) verified by Plan 09's 9 parquet caches existing"
    - "Per D-27 (revised): ledger label scheme — phase0.baseline.{full,bare} pinned by Plan 00 in Wave 0; p1.ksXX.bare/full per change use --baseline bare --arm-b-base bare with --set phase1_ks_flags.ksXX_<name>.enabled=true for true isolation (Cycle 3 D-45); p1.aggregate.full = post-Phase-1 promoted defaults vs bare (this plan)"
    - "Per D-28: validation set = all 2022-2024, 200 sims/season, PPR scoring across all per-plan and aggregate runs"
    - "Per D-29: A/B mode per change = true isolation + full-stack overlay (uses --arm-b-base bare for the isolation runs + Cycle-3 D-45 feature flags); agents executed scripts/validate.py directly per the 2026-04-26 rule reversal"
    - "Per D-25 (revised): final commit message format `feat(01-11): KS-Phase1 PROMOTED — aggregate validation complete (post-Phase-1 vs phase0.baseline.full delta)`"
  artifacts:
    - path: ".planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/PROMOTION-NOTES.md"
      provides: "## Phase 1 aggregate section with metric deltas vs Phase-0 baseline and success-criteria evaluation"
      contains: "## Phase 1 aggregate"
    - path: ".planning/PROJECT.md"
      provides: "TGT-XX current values updated to post-Phase-1 baseline"
      contains: "Current (post-Phase-1)"
  key_links:
    - from: "p1.aggregate.full ledger entry (Arm B = post-Phase-1 defaults)"
      to: "phase0.baseline.full ledger entry (Arm B = pre-Phase-1 defaults, pinned by Plan 00)"
      via: "Arm B metric differencing in Task 1; both ledger entries share the same Arm A (bare) so the difference IS the Phase-1-vs-Phase-0 delta"
      pattern: "phase0\\.baseline\\.full"
---

<objective>
Implement the end-of-phase aggregate validation per D-32 (revised). Run a single `validate.py` invocation labeled `p1.aggregate.full` against the post-Phase-1 promoted defaults using `--baseline bare` (so Arm B = current promoted defaults). Then read BOTH this entry and the `phase0.baseline.full` entry pinned in Wave 0 by Plan 00, difference the Arm B metrics, and evaluate the resulting Phase-1-vs-Phase-0 delta against ROADMAP success criteria 1-4 and the hard floor in PROJECT.md.

Per D-32 (revised 2026-04-26 — Codex HIGH-4 fix): "If any regression appears, walk back the smallest-gain promotion candidate first." This task surfaces such regressions and proposes the rollback target if needed.

Per ROADMAP success criteria 1-4 + RESEARCH.md `## Validation Architecture`:
- **Success criterion 1 (QB pass_yards mean bias):** narrowed from ~−28 yd/game to within ±10 yd/game across 2022-2024
- **Success criterion 2 (QB pass_yards KS):** dropped from ~0.36 to ≤ 0.28 across 2022-2024
- **Success criterion 3 (RB rush_yards KS):** recovers from defaults' 0.26 regression back to ≤ 0.23
- **Success criterion 4 (hard floor across all positions):** rank_corr regression ≤ 0.005 AND MAE regression ≤ 0.05 vs prior promoted defaults

Success criterion 5 (KS-21 alt-line scrape) is verified separately by Plan 09's 9 parquet outputs.

Output: `p1.aggregate.full` ledger entry; PROMOTION-NOTES.md `## Phase 1 aggregate` section evaluating each success criterion against the Phase-1-vs-Phase-0 differenced delta.
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
@.planning/PROJECT-PHASE0-FROZEN.md
@.planning/ROADMAP.md
@.planning/PROJECT.md
@scripts/validate.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Pre-flight — confirm Plan 00 landed and phase0.baseline.full exists</name>
  <files>(no source modifications)</files>
  <read_first>
    - .planning/PROJECT-PHASE0-FROZEN.md
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-CONTEXT.md (D-32, D-32b)
  </read_first>
  <action>
Confirm Plan 00 (Wave 0) has landed and the Phase-0 baseline ledger entries exist with schema v5 (`stat_mean_bias` field populated):

```bash
# Plan 00 deliverables check:
test -f .planning/PROJECT-PHASE0-FROZEN.md && echo "PROJECT-PHASE0-FROZEN.md present" || echo "MISSING"

# Ledger entry check:
uv run python scripts/validate.py --show-ledger | grep -E "phase0\.baseline\.(full|bare)" | wc -l
# Expected: 2 (both phase0.baseline.full and phase0.baseline.bare exist)

# Validate.py extension check:
uv run python scripts/validate.py --help 2>&1 | grep -c "arm-b-base"
# Expected: 1+ (the --arm-b-base flag is wired)

# NEW Cycle 3: Schema v5 + stat_mean_bias presence check
uv run python <<'PY'
import json
from pathlib import Path
from fantasy_sim.validation.ledger import CURRENT_LEDGER_SCHEMA_VERSION
assert CURRENT_LEDGER_SCHEMA_VERSION == 5, f"Schema version is {CURRENT_LEDGER_SCHEMA_VERSION}, expected 5"
data = json.loads(Path("results/ab_ledger.json").read_text())
entries = data if isinstance(data, list) else data.get("entries", [])
phase0 = next((e for e in entries if e.get("label") == "phase0.baseline.full"), None)
assert phase0 is not None, "phase0.baseline.full ledger entry missing"
sr = phase0["season_results"][0]
assert "stat_mean_bias" in sr, "stat_mean_bias field missing from phase0.baseline.full season_results — Plan 00 Task 9 incomplete"
mb_qb = sr["stat_mean_bias"].get("QB", {}).get("pass_yards", {})
assert "arm_b_bias" in mb_qb, f"QB pass_yards arm_b_bias missing from phase0.baseline.full stat_mean_bias: {mb_qb}"
print(f"phase0.baseline.full stat_mean_bias check OK; QB pass_yards arm_b_bias = {mb_qb['arm_b_bias']:.2f}")
PY
```

If any of these checks fails, STOP this plan with a clear error and route the user back to Plan 00. Plan 11 cannot run until the Phase-0 baseline is pinned with schema v5.

If all pass, proceed.

Commit (informational, no code change): no commit needed — Task 1 is a pre-flight gate.
  </action>
  <verify>
    <automated>test -f .planning/PROJECT-PHASE0-FROZEN.md && uv run python scripts/validate.py --show-ledger 2>&1 | grep -E "phase0\.baseline\.(full|bare)" | wc -l | tr -d ' '</automated>
  </verify>
  <acceptance_criteria>
    - `.planning/PROJECT-PHASE0-FROZEN.md` exists
    - The verify command returns at least `2` (both phase0.baseline.full and phase0.baseline.bare in the ledger)
    - `uv run python scripts/validate.py --help` shows `--arm-b-base` in the output
    - Schema v5 + `stat_mean_bias` field check passes (the inline Python block prints OK + the QB pass_yards arm_b_bias value)
  </acceptance_criteria>
  <done>Plan 00 prerequisites confirmed (incl. Cycle-3 schema v5 + stat_mean_bias); safe to proceed.</done>
</task>

<task type="auto">
  <name>Task 2: Run p1.aggregate.full and compute Phase-1-vs-Phase-0 delta</name>
  <files>(no source modifications)</files>
  <read_first>
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-VALIDATION.md (aggregate validation criteria)
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-CONTEXT.md (D-32 revised)
    - .planning/PROJECT-PHASE0-FROZEN.md (Phase-0 baseline reference values)
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/PROMOTION-NOTES.md (per-KS promotion decisions)
    - .planning/ROADMAP.md §"Phase 1" success criteria
    - scripts/validate.py
  </read_first>
  <action>
Confirm all 9 KS plans + the KS-21 scrape have completed (PROMOTION-NOTES.md should have `## KS-01` through `## KS-32` sections, plus `## KS-21 raw scrape` and `## KS-21 processed parquet build` and `## KS-21 schema and timing verification`). KS items may be PROMOTED, SHIPPED-NO-OP, BLOCKED, SHIPPED-OFF, or MEASURED-NO-CHANGE — all are acceptable terminal states for Phase 1 closure.

Run the aggregate A/B (REVISED 2026-04-26 — uses `--baseline bare` for a real delta against bare, NOT `--baseline defaults` which would produce Arm A == Arm B):

```bash
uv run python scripts/validate.py \
  --sims 200 \
  --seasons 2022 2023 2024 \
  --scoring ppr \
  --positions QB RB WR TE \
  --baseline bare \
  --label "p1.aggregate.full" \
  2>&1 | tee .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/p1.aggregate.full.log

uv run python scripts/validate.py --show-ledger | grep -E "phase0\.baseline\.full|p1\.aggregate\.full"
```

This produces a ledger row where Arm A = bare (matches phase0.baseline.full's Arm A) and Arm B = current post-Phase-1 promoted defaults. The Arm B metrics are the post-Phase-1 reference values.

**Compute the Phase-1-vs-Phase-0 delta** by reading BOTH ledger entries' Arm B metrics from the JSON ledger.

**REVISED Cycle 3 (Codex Cycle-2 NEW HIGH #3 fix):** the script now also reads `stat_mean_bias` (added in Plan 00 Task 9, schema v5) so success criterion 1 (QB pass_yards mean bias) is evaluable directly from the ledger artifact. No re-simulation; no side script.

```bash
uv run python <<'EOF' | tee .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/p1_vs_phase0_delta.log
import json
from pathlib import Path

LEDGER_PATH = Path("results/ab_ledger.json")
data = json.loads(LEDGER_PATH.read_text())
entries = data.get("entries", data) if isinstance(data, dict) else data

def find_entry(label):
    for e in entries:
        if e.get("label") == label:
            return e
    raise KeyError(f"Label not found: {label}")

phase0 = find_entry("phase0.baseline.full")
p1_agg = find_entry("p1.aggregate.full")

# Arm B (engines on) metrics — these are the reference values
def collect_arm_b(entry):
    seasons = entry["season_results"]
    rank_corr = {}
    weekly_mae = []
    season_mae = []
    stat_ks = {}
    stat_mean_bias = {}  # NEW Cycle 3 — addresses Codex Cycle-2 NEW HIGH #3
    for s in seasons:
        for pos, val in s["arm_b_rank_corr"].items():
            rank_corr.setdefault(pos, []).append(val)
        weekly_mae.append(s["arm_b_weekly_mae"])
        season_mae.append(s["arm_b_season_mae"])
        # stat_ks
        for pos, stats in s.get("stat_ks", {}).items():
            for stat, ks_data in stats.items():
                if isinstance(ks_data, dict) and "arm_b_ks" in ks_data:
                    stat_ks.setdefault((pos, stat), []).append(ks_data["arm_b_ks"])
        # stat_mean_bias (NEW Cycle 3 — schema v5)
        for pos, stats in s.get("stat_mean_bias", {}).items():
            for stat, mb_data in stats.items():
                if isinstance(mb_data, dict) and "arm_b_bias" in mb_data:
                    stat_mean_bias.setdefault((pos, stat), []).append(mb_data["arm_b_bias"])
    avg = {pos: sum(v)/len(v) for pos, v in rank_corr.items()}
    return {
        "rank_corr": avg,
        "weekly_mae": sum(weekly_mae)/len(weekly_mae),
        "season_mae": sum(season_mae)/len(season_mae),
        "stat_ks": {k: sum(v)/len(v) for k, v in stat_ks.items()},
        "stat_mean_bias": {k: sum(v)/len(v) for k, v in stat_mean_bias.items()},
    }

p0 = collect_arm_b(phase0)
p1 = collect_arm_b(p1_agg)

print("=== Phase 1 vs Phase 0 (Arm B differences) ===")
print()
print("Per-position rank_corr (Phase 1 - Phase 0):")
for pos in ("QB", "RB", "WR", "TE"):
    d = p1["rank_corr"].get(pos, 0) - p0["rank_corr"].get(pos, 0)
    print(f"  {pos}: Δ {d:+.4f}  (Phase 0: {p0['rank_corr'].get(pos):.4f}, Phase 1: {p1['rank_corr'].get(pos):.4f})")

print()
print(f"Aggregate weekly_mae:")
d_w = p1["weekly_mae"] - p0["weekly_mae"]
print(f"  Δ {d_w:+.4f}  (Phase 0: {p0['weekly_mae']:.4f}, Phase 1: {p1['weekly_mae']:.4f})")
print(f"  Hard floor (Δ ≤ +0.05): {'PASS' if d_w <= 0.05 else 'FAIL'}")

print()
print(f"Aggregate season_mae:")
d_s = p1["season_mae"] - p0["season_mae"]
print(f"  Δ {d_s:+.4f}")

print()
print("Per-stat KS deltas (selected — Phase 1 - Phase 0):")
focus_stats = [("QB", "pass_yards"), ("WR", "receiving_yards"), ("RB", "rush_yards"),
               ("TE", "receiving_yards"), ("WR", "receptions"), ("TE", "receptions")]
for key in focus_stats:
    if key in p1["stat_ks"] and key in p0["stat_ks"]:
        d = p1["stat_ks"][key] - p0["stat_ks"][key]
        print(f"  {key[0]} {key[1]}: Δ {d:+.4f}  (Phase 0: {p0['stat_ks'][key]:.4f}, Phase 1: {p1['stat_ks'][key]:.4f})")

# NEW Cycle 3: Per-stat MEAN BIAS deltas — addresses Codex Cycle-2 NEW HIGH #3
# Phase-1 success criterion 1: QB pass_yards mean bias narrowed from ~−28 yd/g to within ±10 yd/g.
print()
print("Per-stat MEAN BIAS deltas (Phase 1 - Phase 0):")
for key in focus_stats:
    if key in p1["stat_mean_bias"] and key in p0["stat_mean_bias"]:
        d = p1["stat_mean_bias"][key] - p0["stat_mean_bias"][key]
        print(
            f"  {key[0]} {key[1]} bias (yd/g): Phase 0={p0['stat_mean_bias'][key]:+.2f}, "
            f"Phase 1={p1['stat_mean_bias'][key]:+.2f}, Δ={d:+.2f}"
        )

# Explicit success criterion 1 evaluation
qb_pass_yds_bias_p1 = p1["stat_mean_bias"].get(("QB", "pass_yards"))
if qb_pass_yds_bias_p1 is not None:
    crit1_met = abs(qb_pass_yds_bias_p1) <= 10.0
    print()
    print(f"Phase-1 success criterion 1 (QB pass_yards mean bias |Δ vs actual| ≤ 10 yd/g):")
    print(f"  Phase-1 Arm B QB pass_yards bias = {qb_pass_yds_bias_p1:+.2f} yd/g")
    print(f"  Criterion 1: {'YES (PASS)' if crit1_met else 'NO (FAIL — bias exceeds ±10 yd/g)'}")
else:
    print()
    print("WARNING: stat_mean_bias['QB']['pass_yards'] missing from p1.aggregate.full ledger entry.")
    print("This means Plan 00 Task 9 did not wire validate.py to write the field. Re-check Plan 00.")
EOF
```

NOTE: If `collect_arm_b` raises `KeyError` on `stat_mean_bias` for either ledger entry, that means Plan 00 Task 9 (ledger schema v5 + validate.py write site) did not complete successfully — STOP this plan and route back to Plan 00. Schema v5 with populated `stat_mean_bias` is a hard prerequisite.

Append `## Phase 1 aggregate (Phase-1-vs-Phase-0 delta)` to PROMOTION-NOTES.md using the differenced metrics:

```markdown
## Phase 1 aggregate (p1.aggregate.full vs phase0.baseline.full)

**Computation:** Arm B (engines on) of `p1.aggregate.full` minus Arm B of `phase0.baseline.full`.
Both entries share the same Arm A (bare engines), so the difference IS the Phase-1-vs-Phase-0 delta.

### Headline metrics

| Metric | Phase 0 (frozen) | Phase 1 (post-promotion) | Δ | Phase-1 target | Met? | Source |
|--------|------------------|--------------------------|---|----------------|------|--------|
| QB pass_yards mean bias (yd/g) | ... | ... | ... | \|Phase 1\| ≤ 10 | YES/NO | NEW Cycle 3: stat_mean_bias["QB"]["pass_yards"]["arm_b_bias"] from ledger v5 |
| QB pass_yards KS | ... | ... | ... | ≤ 0.28 | YES/NO | stat_ks["QB"]["pass_yards"]["arm_b_ks"] |
| RB rush_yards KS | ... | ... | ... | ≤ 0.23 | YES/NO | stat_ks["RB"]["rush_yards"]["arm_b_ks"] |
| Aggregate rank_corr (PPR) | ... | ... | ... | Δ ≥ -0.005 | YES/NO | mean(arm_b_rank_corr) over positions |
| Aggregate weekly_mae (PPR) | ... | ... | ... | Δ ≤ +0.05 | YES/NO | arm_b_weekly_mae |

### Per-position rank_corr (Phase 1 - Phase 0)

| Position | Phase 0 | Phase 1 | Δ |
|----------|---------|---------|---|
| QB | ... | ... | ... |
| RB | ... | ... | ... |
| WR | ... | ... | ... |
| TE | ... | ... | ... |

### Per-position-stat KS (Phase 1 - Phase 0)

| Position | Stat | Phase 0 | Phase 1 | Δ |
|----------|------|---------|---------|---|
| QB | pass_yards | ... | ... | ... |
| QB | rush_yards | ... | ... | ... |
| RB | rush_yards | ... | ... | ... |
| RB | receiving_yards | ... | ... | ... |
| WR | receptions | ... | ... | ... |
| WR | receiving_yards | ... | ... | ... |
| TE | receptions | ... | ... | ... |
| TE | receiving_yards | ... | ... | ... |

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

Commit: `chore(01-11): KS-Phase1 aggregate ledger entry + Phase-1-vs-Phase-0 delta computation`
  </action>
  <verify>
    <automated>uv run python scripts/validate.py --show-ledger 2>&1 | grep -E "p1\.aggregate\.full" | wc -l | tr -d ' '</automated>
  </verify>
  <acceptance_criteria>
    - The verify command returns at least `1` (p1.aggregate.full ledger entry exists)
    - `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/p1.aggregate.full.log` exists
    - `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/p1_vs_phase0_delta.log` exists with the differenced metrics
    - The delta log contains a section "Per-stat MEAN BIAS deltas" AND a "Phase-1 success criterion 1" block evaluating QB pass_yards mean bias (NEW Cycle 3 — addresses Codex Cycle-2 NEW HIGH #3)
    - PROMOTION-NOTES.md contains `## Phase 1 aggregate (p1.aggregate.full vs phase0.baseline.full)` with all 5 success criteria evaluated YES/NO (criterion 1 = QB pass_yards mean bias filled from the new `stat_mean_bias` ledger field) and the headline metrics filled in
    - If criterion 1 is NO (mean-bias miss): PROMOTION-NOTES walk-back proposal explicitly considers reverting KS-01 (the largest-mean-bias mechanism) before any smaller-gain candidate
    - If any other criterion is NO: PROMOTION-NOTES contains the walk-back proposal naming the smallest-gain candidate per D-32
    - `grep -c "stat_mean_bias" .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/p1_vs_phase0_delta.log` returns at least 1 (the script actually read the new field, didn't silently fall back to empty)
    - `git log -1 --pretty=%s` matches `chore(01-11): KS-Phase1 aggregate`
  </acceptance_criteria>
  <done>p1.aggregate.full ledger entry recorded; Phase-1-vs-Phase-0 delta computed (incl. mean-bias from ledger v5); success criteria 1-4 evaluated YES/NO; walk-back proposal documented if needed.</done>
</task>

<task type="auto">
  <name>Task 3: Update PROJECT.md TGT-XX current values to reflect Phase 1 exit metrics</name>
  <files>.planning/PROJECT.md</files>
  <read_first>
    - .planning/PROJECT.md (current TGT-XX table)
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/PROMOTION-NOTES.md (Task 2 headline metrics)
    - .planning/PROJECT-PHASE0-FROZEN.md (for the Phase 0 reference values that are being replaced)
  </read_first>
  <action>
Update the TGT-XX outcome targets table in `.planning/PROJECT.md` to reflect the post-Phase-1 baseline.

Find the table that lists TGT-01..TGT-10 with `Current` and `Target` columns. Replace the `Current` values with the post-Phase-1 metrics from Task 2's PROMOTION-NOTES section. Preserve the `Target` values unchanged. Add an explicit note that the previous (Phase-0) values are preserved in `.planning/PROJECT-PHASE0-FROZEN.md`.

Example update (using placeholder post-Phase-1 values; substitute actuals from Task 2):
```markdown
| ID | Description | Current (post-Phase-1) | Target |
|----|-------------|------------------------|--------|
| TGT-01 | QB pass_yards KS | <new value> | ≤ 0.20 |
| TGT-02 | WR receiving_yards KS | <new value> | ≤ 0.20 |
| TGT-09 | QB pass_yards mean bias | <new value> | ±5 yd/g |
| TGT-10 | WR receiving_yards mean bias | <new value> | ±2 yd/g |
| ...
```

NOTE: PROJECT.md update is NOT a pre-condition for Phase 1 closure — the ledger entries (`phase0.baseline.full` + `p1.aggregate.full`) ARE the canonical record. PROJECT.md update is a consistency / documentation update so the next phase planner has the right baseline visible.

Commit: `docs(01-11): update PROJECT.md TGT-XX current values to post-Phase-1 baseline`
  </action>
  <verify>
    <automated>git diff HEAD~1 .planning/PROJECT.md 2>&1 | grep -E "^[+-]" | wc -l | tr -d ' '</automated>
  </verify>
  <acceptance_criteria>
    - `.planning/PROJECT.md` modified — diff against HEAD~1 shows changes to the TGT-XX table
    - The `Current` column for TGT-01, TGT-02, TGT-09, TGT-10 reflects post-Phase-1 values from Task 2's PROMOTION-NOTES
    - The `Target` column is unchanged
    - A reference to `.planning/PROJECT-PHASE0-FROZEN.md` is added or preserved (so the prior values remain inspectable)
    - `git log -1 --pretty=%s` matches `docs(01-11): update PROJECT.md`
  </acceptance_criteria>
  <done>PROJECT.md TGT-XX table reflects Phase 1 exit baseline; Phase-0 reference preserved.</done>
</task>

<task type="auto">
  <name>Task 4: Promotion-state commit + Phase 1 closure SUMMARY (per D-25 revised)</name>
  <files>(no source modifications)</files>
  <read_first>
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/PROMOTION-NOTES.md (all KS sections + ## Phase 1 aggregate)
    - All `01-NN-SUMMARY.md` files from Plans 00-10
  </read_first>
  <action>
Per D-25 (revised — promotion-state commit per KS plan), create the final Phase-1-closure commit + SUMMARY. The Plan 11 SUMMARY also serves as the Phase 1 closure report.

Determine overall Phase 1 promotion state:
- All success criteria 1-5 met → `PROMOTED` (Phase 1 ships)
- Some criteria missed but no hard-floor violations → `SHIPPED-NO-OP` (Phase 1 ships, intermediate)
- Hard floor violation OR walk-back required → `BLOCKED` (Phase 1 needs rework before close)

Create `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-11-SUMMARY.md`:

```markdown
# Plan 11 Summary — Phase 1 closure: aggregate validation

**Promotion state:** <PROMOTED|SHIPPED-NO-OP|BLOCKED>
**Phase:** 1 (closure)
**Wave:** 7 (final)
**Final commit:** $(git log -1 --pretty=%H)

## Phase 1 deliverables status (per KS-XX)

| KS | Plan | Promotion state | Notes |
|----|------|-----------------|-------|
| Validation harness extension + Phase-0 baseline pin | 00 | PROMOTED | --arm-b-base flag wired; phase0.baseline.{full,bare} pinned |
| KS-01 RZ TD-gate truncation fix | 01 | <state from 01-01-SUMMARY> | |
| KS-04 CATCH_YARDS_BOOST conditional retune | 02 | <state from 01-02-SUMMARY> | |
| KS-03 matchup/coverage anchor fix | 03 | <state from 01-03-SUMMARY> | Widened scope per D-16b (MEDIUM-1 fix) |
| KS-05 props engine bug fixes | 04 | <state from 01-04-SUMMARY> | Test path corrected (MEDIUM-3 fix) |
| KS-06 backup receiver fallback fixes | 05 | <state from 01-05-SUMMARY> | Preprocessor API corrected (MEDIUM-3 fix) |
| KS-07 positional RZ catch rate | 06 | <state from 01-06-SUMMARY> | |
| KS-15 field-position clamping fix | 07 | <state from 01-07-SUMMARY> | Legacy paths patched (MEDIUM-4 fix) |
| KS-29 pff.team_context re-enable | 08 | <state from 01-08-SUMMARY> | Behavior preflight (LOW-2 fix) |
| KS-21 alt-line scrape sub-deliverable | 09 | <state from 01-09-SUMMARY> | Raw + parquet build pipeline (HIGH-2); prior_* labels (HIGH-3) |
| KS-32 clock runoff calibration | 10 | <state from 01-10-SUMMARY> | NO CHANGE branch uses --baseline bare (HIGH-4 fix) |

## Codex review fix summary

This phase replan addressed all 4 HIGH-severity concerns from `01-REVIEWS.md`:
- **HIGH-1 (per-KS A/B isolation contamination):** Plan 00 added `--arm-b-base bare` flag to `validate.py`; all per-KS plans now use `--baseline bare --arm-b-base bare` for true isolation.
- **HIGH-2 (Plan 09 raw vs parquet pipeline):** Plan 09 now explicitly invokes both `fetch_market_history_props.py` (raw JSON) AND `build_market_history_player_markets.py` (processed parquet); acceptance gates on both.
- **HIGH-3 (Tuesday 12pm ET label naming):** Snapshot labels renamed `open_*` → `prior_*` to honestly describe the API's `previous_timestamp` semantics. Phase 4 contract updated.
- **HIGH-4 (Plan 11 aggregate is no-op):** Plan 11 now uses `--baseline bare --label p1.aggregate.full` (no `--set`) and computes the Phase-1-vs-Phase-0 delta by reading both `phase0.baseline.full` (pinned in Wave 0 by Plan 00) and `p1.aggregate.full` from the ledger.

Plus 4 MEDIUM-severity concerns:
- **MEDIUM-1:** KS-03 hypothesis widened to cover `_apply_matchup` rushing branch (D-16b)
- **MEDIUM-2:** Per-KS commit cadence revised to "promotion-state commit per plan" with standardized message format (D-25 revised)
- **MEDIUM-3:** Plan 04 test path corrected to `tests/test_data/test_vegas/`; Plan 05 API ref corrected to `Preprocessor().compute_play_outcomes()`
- **MEDIUM-4:** Plan 07 widened to patch the legacy non-roster paths in `_resolve_pass`/`_resolve_run` (D-15b)

Plus LOW-2 polish: Plan 08 preflight uses existing `tests/test_data/test_pff/test_tier_engine.py` behavior test instead of ad-hoc grep.

## Phase 1 entry/exit metrics (from PROMOTION-NOTES Task 2 table)

| Metric | Phase 0 (entry) | Phase 1 (exit) | Δ |
|--------|-----------------|----------------|---|
| QB pass_yards KS | ... | ... | ... |
| WR receiving_yards KS | ... | ... | ... |
| RB rush_yards KS | ... | ... | ... |
| QB pass_yards mean bias (yd/g) | ... | ... | ... |
| Aggregate rank_corr (PPR) | ... | ... | ... |
| Aggregate weekly_mae (PPR) | ... | ... | ... |

## Phase 2 entry baseline

The Arm B metrics in `p1.aggregate.full` ledger entry ARE the Phase 2 baseline.
Phase 2 plans should compare against `p1.aggregate.full` rather than `phase0.baseline.full`.
Plan 00's pattern of pinning a Wave-0 baseline can be reused at the start of each subsequent phase.
```

Commit:

```bash
PROMO_STATE="PROMOTED"  # or SHIPPED-NO-OP / BLOCKED
git add .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-11-SUMMARY.md
git commit -m "feat(01-11): KS-Phase1 ${PROMO_STATE} — aggregate validation complete (post-Phase-1 vs phase0.baseline.full delta)

Wave 7 (final). End-of-phase aggregate run. Closes Codex review HIGH-4
by computing the Phase-1-vs-Phase-0 delta against the frozen baseline
pinned in Wave 0 by Plan 00.

All 4 Codex HIGH concerns + 4 MEDIUM concerns + LOW-2 addressed in this
replan cycle. See 01-11-SUMMARY.md for the per-KS deliverable status."
```
  </action>
  <verify>
    <automated>test -f .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-11-SUMMARY.md && grep -cE "PROMOTED|SHIPPED-NO-OP|BLOCKED" .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-11-SUMMARY.md</automated>
  </verify>
  <acceptance_criteria>
    - SUMMARY exists with explicit promotion state header
    - SUMMARY contains the per-KS deliverable status table populated from each Plan's SUMMARY
    - SUMMARY contains the Codex review fix summary section
    - SUMMARY contains the Phase 1 entry/exit metrics table
    - `git log -1 --pretty=%s` matches `feat(01-11): KS-Phase1 PROMOTED|SHIPPED-NO-OP|BLOCKED`
  </acceptance_criteria>
  <done>Phase 1 closure SUMMARY captures the aggregate decision and the per-KS deliverable roster. Plan 11 PROMOTED (or BLOCKED + walk-back routed).</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| (n/a) | Aggregate validation only; no code changes (PROJECT.md is doc only). |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-01-11-01 | T (Tampering) | Phase 1 success criteria evaluation | mitigate | Task 2 spells out each criterion as a YES/NO checkbox tied to specific metric thresholds — no ambiguity. |
| T-01-11-02 | T (Tampering) | Walk-back order if criteria missed | mitigate | D-32 specifies "smallest-gain promotion candidate first"; Task 2 names the candidate explicitly. |
| T-01-11-03 | I (Information disclosure) | PROJECT.md baseline update | accept | PROJECT.md is a planning artifact; values are aggregated metrics, no PII. |
| T-01-11-04 | T (Tampering) | Phase-0 baseline ledger entry could be rewritten silently | mitigate | Task 1 preflight checks both PROJECT-PHASE0-FROZEN.md and the ledger entries; if either is missing, plan halts. The freeze doc records the SHA so accidental relabel is detectable. |
| T-01-11-05 | T (Tampering) | "I ran an aggregate validation" claim without actually computing the delta | mitigate | Task 2 emits an explicit `p1_vs_phase0_delta.log` file derived from the ledger JSON; the file's existence (and content) is the audit trail. |
</threat_model>

<verification>
- Plan 00 prerequisites confirmed (Task 1)
- p1.aggregate.full ledger entry exists (Task 2)
- p1_vs_phase0_delta.log file exists with differenced metrics (Task 2)
- PROMOTION-NOTES.md `## Phase 1 aggregate` section evaluates all 5 success criteria (Task 2)
- PROJECT.md TGT-XX `Current` values reflect post-Phase-1 baseline (Task 3)
- Plan 11 SUMMARY captures Phase 1 closure status with per-KS deliverable roster (Task 4)
- 1,200+ existing test suite still green
</verification>

<success_criteria>
- All 9 KS-XX requirements deliverable per REQUIREMENTS.md "delivered" definition (each has its own per-plan SUMMARY + per-KS PROMOTION-NOTES section)
- Phase 1 ROADMAP success criteria 1-5 evaluated and recorded against the differenced Phase-1-vs-Phase-0 delta
- Phase 2 baseline established (PROJECT.md updated; ledger entry p1.aggregate.full = canonical Phase-2 reference)
- If any criterion missed: walk-back candidate identified per D-32
- All 4 Codex HIGH-severity concerns from `01-REVIEWS.md` resolved (HIGH-1: --arm-b-base flag; HIGH-2: raw+parquet pipeline; HIGH-3: prior_* labels; HIGH-4: Phase-0 baseline pin + delta computation in this plan)
</success_criteria>

<output>
After completion, the SUMMARY at `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-11-SUMMARY.md` is the canonical Plan 11 closure document AND the Phase 1 closure report. STATE.md and ROADMAP.md updates draw from it.
</output>

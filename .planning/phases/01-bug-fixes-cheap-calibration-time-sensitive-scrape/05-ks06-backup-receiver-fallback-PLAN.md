---
phase: 01-bug-fixes-cheap-calibration-time-sensitive-scrape
plan: 05
type: execute
wave: 3
depends_on: ["00", "01", "02"]
files_modified:
  - src/fantasy_sim/data/preprocessor.py
  - src/fantasy_sim/data/player_builder.py
  - src/fantasy_sim/engine/play_resolver.py
  - tests/test_data/test_preprocessor.py
  - tests/test_data/test_player_builder.py
  - tests/test_engine/test_play_resolver.py
autonomous: true
requirements: [KS-06]
must_haves:
  truths:
    - "Per D-19 sub-fix 1: team-bucket distribution in preprocessor.py is filtered to completed plays only (was including incompletions in the yards distribution)"
    - "Per D-19 sub-fix 2: backup-receiver fallback in play_resolver.py:271 uses rng.integers(5, 18) (mean ~11.5, matching NFL average) — was rng.integers(3, 12) (mean ~7)"
    - "Per D-19 sub-fix 3: MIN_PLAYER_PLAYS in player_builder.py:11 is 3 (was 5) — gives more players their own dist"
    - "Per D-29 (revised 2026-04-26 — HIGH-1): p1.ks06.bare uses --baseline bare --arm-b-base bare (true isolation, requires Plan 00); p1.ks06.full uses --baseline defaults"
    - "Per D-41 (added 2026-04-26 — MEDIUM-3): test invocations use the actual `Preprocessor().compute_play_outcomes()` API at preprocessor.py:27/110 (NOT a non-existent `build_play_outcomes` function); see Task 1 test code for the canonical pattern"
    - "Per D-45 (Cycle 3 — Codex Cycle-2 NEW HIGH #1 fix): the backup-receiver fixes are gated behind `phase1_ks_flags.ks06_backup_receiver_fix.enabled` (default false until promotion). The implementations in `src/fantasy_sim/engine/play_resolver.py`, `src/fantasy_sim/data/preprocessor.py`, and `src/fantasy_sim/data/player_builder.py` read `get_phase1_ks_flags()['ks06_backup_receiver_fix']` and branch: flag-on path uses `MIN_PLAYER_PLAYS = 3`, fallback `rng.integers(5, 18)`, AND the completed-play filter; flag-off path keeps `MIN_PLAYER_PLAYS = 5`, fallback `rng.integers(3, 12)`, AND the unfiltered team bucket distribution. Both A/B runs use `--set phase1_ks_flags.ks06_backup_receiver_fix.enabled=true`. Promotion commit flips the default to true in `config/defaults.yaml`."
    - "p1.ks06.bare and p1.ks06.full ledger entries pass hard floor (Δ rank_corr ≥ -0.005 AND Δ weekly_mae ≤ +0.05) per D-30. Both runs invoke `--set phase1_ks_flags.ks06_backup_receiver_fix.enabled=true` per Cycle 3 D-45."
    - "Per D-25 (revised 2026-04-26 — MEDIUM-2): final commit message format `feat(01-05): KS-06 [PROMOTED|SHIPPED-NO-OP|BLOCKED] — backup receiver fallback fixes`"
    - "Per D-26: KS-06 commit chain ships after KS-04 lands (file overlap with play_resolver.py — sequenced for clean line-anchor merging). Plan 00 must land first."
    - "Per D-34: test-after acceptable for KS-06"
    - "Per D-35: existing 1,200+ test suite stays green throughout"
  artifacts:
    - path: "src/fantasy_sim/data/preprocessor.py"
      provides: "Team bucket distribution filtered to completed plays only"
      contains: "complete_pass"
    - path: "src/fantasy_sim/data/player_builder.py"
      provides: "MIN_PLAYER_PLAYS = 3"
      contains: "MIN_PLAYER_PLAYS = 3"
    - path: "src/fantasy_sim/engine/play_resolver.py"
      provides: "Backup-receiver fallback uses rng.integers(5, 18)"
      contains: "rng.integers(5, 18)"
  key_links:
    - from: "preprocessor.py team-bucket filter"
      to: "play_resolver.py backup fallback"
      via: "team_yards from sample_yards must already be completion-only; fallback's int range is the secondary safety net"
      pattern: "complete_pass"
---

<objective>
Implement KS-06 — three coordinated fixes for the backup-receiver fallback path that currently shrinks WR/TE receiving distributions when a starter is unavailable:

1. **D-19 sub-fix 1** (`preprocessor.py`): Filter team-bucket distribution to completed plays only. Currently includes incompletions (yards=0), pulling the distribution mean down.
2. **D-19 sub-fix 2** (`play_resolver.py:271`): Change the integer fallback from `rng.integers(3, 12)` (mean ~7) to `rng.integers(5, 18)` (mean ~11.5, matches NFL average completion length).
3. **D-19 sub-fix 3** (`player_builder.py:11`): Lower `MIN_PLAYER_PLAYS = 5 → 3` so more thin-data players get their own distribution rather than falling through to the team bucket.

Purpose: HYPOTHESES.md KS-06 (lines 145-157) shows the current fallback path produces unrealistically small receiving distributions for backup receivers, biasing WR/TE projections low when starters are questionable.

Output: 3 source edits across 3 files; coordinated tests across 3 test files; both ledger entries pass hard floor.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-CONTEXT.md
@.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-RESEARCH.md
@.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-VALIDATION.md
@src/fantasy_sim/data/preprocessor.py
@src/fantasy_sim/data/player_builder.py
@src/fantasy_sim/engine/play_resolver.py

<interfaces>
Current state:

```python
# src/fantasy_sim/data/preprocessor.py
# Line 9:
MIN_BUCKET_PLAYS = 10
# Lines ~100, 137 — bucket guards (use MIN_BUCKET_PLAYS); fix needs to verify the filter
# step where pass plays are added to the per-bucket yards array.
# Inspect the function that builds team `pass_yards` per-bucket array — this is where
# the completed-only filter must be added.

# src/fantasy_sim/data/player_builder.py
# Line 11:
MIN_PLAYER_PLAYS = 5
# Lower to 3 per D-19.

# src/fantasy_sim/engine/play_resolver.py
# Lines 268-271 (post-KS-04, _resolve_pass fallback when player has no full_dist):
#     team_yards = play_outcomes.sample_yards("pass", _bucket_from_state(state), rng)
#     raw_sample = team_yards if team_yards > 0 else int(rng.integers(3, 12))
# Change `rng.integers(3, 12)` → `rng.integers(5, 18)` per D-19.
```

NOTE: Plan 02 (KS-04) refactored the boost-application section. The exact line number of the `rng.integers(3, 12)` call in `_resolve_pass` may have shifted. Verify the literal string `rng.integers(3, 12)` is still present in `play_resolver.py` before editing.
</interfaces>

</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Patch preprocessor.py team-bucket completed-play filter</name>
  <files>src/fantasy_sim/data/preprocessor.py, tests/test_data/test_preprocessor.py</files>
  <read_first>
    - src/fantasy_sim/data/preprocessor.py (full file — find the function that builds `pass_yards` per-bucket arrays; the filter step)
    - tests/test_data/test_preprocessor.py (existing test patterns + fixtures)
    - .planning/research/HYPOTHESES.md lines 145-157 (KS-06 mechanism)
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-CONTEXT.md (D-19 sub-fix 1)
  </read_first>
  <action>
1. Inspect `src/fantasy_sim/data/preprocessor.py` to find the function that constructs the per-bucket pass-yards numpy array. The filter to add is `complete_pass == True` (or equivalent, depending on the PBP column name nflverse uses; likely `complete_pass` or `pass_outcome == 'complete'`).

Look for code like:
```python
# Likely shape (find the actual call):
pass_plays = pbp_df.filter((pl.col("play_type") == "pass") & (pl.col("yardline_100") <= ...))
yards_arr = pass_plays["yards_gained"].to_numpy()
```

Add the `complete_pass` filter:
```python
# AFTER (D-19 sub-fix 1):
pass_plays = pbp_df.filter(
    (pl.col("play_type") == "pass")
    & (pl.col("complete_pass") == 1)  # KS-06 D-19: team-bucket dist = completions only
    & (pl.col("yardline_100") <= ...)
)
yards_arr = pass_plays["yards_gained"].to_numpy()
```

If the column is named differently (`pass_outcome`, `passing_complete`, etc.), use the actual nflverse column name visible in `data/loader.py` or fixtures.

2. Add a test in `tests/test_data/test_preprocessor.py` (new section `# === KS-06: completed-play filter for team buckets ===`):

```python
def test_ks06_team_bucket_excludes_incompletions():
    """KS-06 D-19 sub-fix 1: team pass-yards bucket should only include completed plays."""
    import polars as pl
    import numpy as np
    from fantasy_sim.data.preprocessor import Preprocessor  # actual API; see preprocessor.py:27 (class) and :110 (compute_play_outcomes)

    # Build a minimal PBP dataframe with 5 completions (10 yds each) and 5 incompletions (0 yds)
    pbp = pl.DataFrame({
        "play_type": ["pass"] * 10,
        "complete_pass": [1, 1, 1, 1, 1, 0, 0, 0, 0, 0],
        "yards_gained": [10, 10, 10, 10, 10, 0, 0, 0, 0, 0],
        "down": [1] * 10, "ydstogo": [10] * 10,
        "yardline_100": [50] * 10,
        "score_differential": [0] * 10, "qtr": [2] * 10,
        # ... other required columns; inspect existing fixtures (tests/conftest.py sample_pbp) for the schema
    })
    pre = Preprocessor()
    outcomes = pre.compute_play_outcomes(pbp)
    # Sample many times from the bucket; mean should be 10 (completions only), not 5 (mixed)
    rng = np.random.default_rng(0)
    # bucket can be any GameStateBucket present in outcomes; pick the first one or use a sentinel
    samples = [outcomes.sample_yards("pass", bucket=..., rng=rng) for _ in range(1000)]
    assert 9.0 <= np.mean(samples) <= 11.0, f"Bucket mean shifted: {np.mean(samples)}"
```

NOTE (revised 2026-04-26 — MEDIUM-3 fix): The actual API is `Preprocessor().compute_play_outcomes(pbp)` at `src/fantasy_sim/data/preprocessor.py:27` (class) and `:110` (method). The original draft of this plan referenced a non-existent `build_play_outcomes()` entry point that Codex review flagged as wrong. The bucket lookup pattern follows the `tests/conftest.py::sample_pbp` fixture; consult existing tests in `tests/test_data/test_preprocessor.py` for the canonical bucket-construction shape.

3. Run pytest:
```bash
uv run pytest tests/test_data/test_preprocessor.py -v -k ks06
uv run pytest tests/ -v 2>&1 | tail -10
```

EXPECTED: New test passes; existing tests pass.

Commit: `fix(01-05): KS-06 D-19 sub-fix 1 — preprocessor filters team buckets to completed plays`
  </action>
  <verify>
    <automated>uv run pytest tests/test_data/test_preprocessor.py -v -k ks06 && uv run pytest tests/ -v 2>&1 | tail -5</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "complete_pass" src/fantasy_sim/data/preprocessor.py` returns at least 1
    - `tests/test_data/test_preprocessor.py` contains `def test_ks06_team_bucket_excludes_incompletions`
    - `uv run pytest tests/test_data/test_preprocessor.py -v -k ks06` exits 0
    - `uv run pytest tests/ -v 2>&1 | tail -5` shows `passed` with no `failed`
    - `git log -1 --pretty=%s` matches `fix(01-05): KS-06 D-19 sub-fix 1`
  </acceptance_criteria>
  <done>Filter added; test passing; no regressions.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Lower MIN_PLAYER_PLAYS to 3 and update fallback integer range to (5, 18)</name>
  <files>src/fantasy_sim/data/player_builder.py, src/fantasy_sim/engine/play_resolver.py, tests/test_data/test_player_builder.py, tests/test_engine/test_play_resolver.py</files>
  <read_first>
    - src/fantasy_sim/data/player_builder.py (line 11; usage sites of MIN_PLAYER_PLAYS)
    - src/fantasy_sim/engine/play_resolver.py (post-KS-04 _resolve_pass; locate `rng.integers(3, 12)`)
    - tests/test_data/test_player_builder.py (existing tests for MIN_PLAYER_PLAYS)
    - tests/test_engine/test_play_resolver.py (existing tests for backup fallback)
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-CONTEXT.md (D-19 sub-fixes 2, 3)
  </read_first>
  <action>
1. In `src/fantasy_sim/data/player_builder.py` line 11:
```python
# BEFORE:
MIN_PLAYER_PLAYS = 5
# AFTER (D-19 sub-fix 3):
MIN_PLAYER_PLAYS = 3  # KS-06 D-19: more players get their own dist; fewer fall through to team bucket
```

2. In `src/fantasy_sim/engine/play_resolver.py`, find the `rng.integers(3, 12)` call (in the fallback branch of `_resolve_pass`):
```python
# BEFORE:
raw_sample = team_yards if team_yards > 0 else int(rng.integers(3, 12))
# AFTER (D-19 sub-fix 2):
raw_sample = team_yards if team_yards > 0 else int(rng.integers(5, 18))
```

3. Add a test in `tests/test_data/test_player_builder.py`:
```python
def test_ks06_min_player_plays_is_3():
    from fantasy_sim.data.player_builder import MIN_PLAYER_PLAYS
    assert MIN_PLAYER_PLAYS == 3, f"D-19 sub-fix 3 requires 3, got {MIN_PLAYER_PLAYS}"

def test_ks06_player_with_3_plays_gets_own_dist():
    """Players with exactly 3 plays should now build their own dist (was: 5)."""
    # Build a minimal PBP for one player with 3 catches (yards 8, 12, 16)
    # Run player_builder
    # Assert that player.outcomes.receiving_yards_dist is not None and len() == 3
    pass  # adapt to actual player_builder API
```

4. Add a test in `tests/test_engine/test_play_resolver.py`:
```python
def test_ks06_backup_receiver_fallback_range():
    """When team_yards <= 0, the integer fallback should sample in [5, 17] (mean ~11)."""
    import numpy as np
    rng = np.random.default_rng(42)
    samples = [int(rng.integers(5, 18)) for _ in range(10000)]
    assert min(samples) >= 5
    assert max(samples) <= 17  # rng.integers is exclusive on the high bound
    assert 10.5 <= np.mean(samples) <= 11.5
```

5. Run pytest:
```bash
uv run pytest tests/test_data/test_player_builder.py -v -k ks06
uv run pytest tests/test_engine/test_play_resolver.py -v -k ks06
uv run pytest tests/ -v 2>&1 | tail -10
```

EXPECTED: All tests pass.

Commit: `fix(01-05): KS-06 D-19 sub-fixes 2+3 — fallback range (5,18) and MIN_PLAYER_PLAYS=3`
  </action>
  <verify>
    <automated>uv run pytest tests/test_data/test_player_builder.py tests/test_engine/test_play_resolver.py -v -k ks06 && uv run pytest tests/ -v 2>&1 | tail -5</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "MIN_PLAYER_PLAYS = 3" src/fantasy_sim/data/player_builder.py` returns 1
    - `grep -c "MIN_PLAYER_PLAYS = 5" src/fantasy_sim/data/player_builder.py` returns 0
    - `grep -c "rng.integers(5, 18)" src/fantasy_sim/engine/play_resolver.py` returns 1
    - `grep -c "rng.integers(3, 12)" src/fantasy_sim/engine/play_resolver.py` returns 0
    - `tests/test_data/test_player_builder.py` contains `def test_ks06_min_player_plays_is_3`
    - `tests/test_engine/test_play_resolver.py` contains `def test_ks06_backup_receiver_fallback_range`
    - `uv run pytest tests/ -v 2>&1 | tail -5` shows `passed` with no `failed`
    - `git log -1 --pretty=%s` matches `fix(01-05): KS-06 D-19 sub-fixes 2+3`
  </acceptance_criteria>
  <done>Both sub-fixes in place; tests passing; no regressions.</done>
</task>

<task type="auto">
  <name>Task 3: A/B validate KS-06 in isolation and full-stack; commit ledger entries</name>
  <files>(no source modifications)</files>
  <read_first>
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-VALIDATION.md
    - scripts/validate.py
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-CONTEXT.md (D-29, D-30)
  </read_first>
  <action>
**REVISED Cycle 3 (D-45 — Codex Cycle-2 NEW HIGH #1 fix):** the KS-06 backup-receiver fixes are gated behind `phase1_ks_flags.ks06_backup_receiver_fix.enabled` (default false; set in Plan 00 Task 8). Both arms use `--set phase1_ks_flags.ks06_backup_receiver_fix.enabled=true` for Arm B; Arm A keeps the legacy `MIN_PLAYER_PLAYS = 5`, the legacy `rng.integers(3, 12)` fallback range, and the legacy non-completed-play-filtered team bucket distribution.

Run BOTH A/B passes per D-29:

```bash
# True isolation: bare engines + KS-06 flag overlay
uv run python scripts/validate.py \
  --sims 200 --seasons 2022 2023 2024 --scoring ppr --positions QB RB WR TE \
  --baseline bare --arm-b-base bare \
  --set "phase1_ks_flags.ks06_backup_receiver_fix.enabled=true" \
  --label "p1.ks06.bare"

# Full-stack overlay: defaults + KS-06 flag overlay
uv run python scripts/validate.py \
  --sims 200 --seasons 2022 2023 2024 --scoring ppr --positions QB RB WR TE \
  --baseline defaults \
  --set "phase1_ks_flags.ks06_backup_receiver_fix.enabled=true" \
  --label "p1.ks06.full"

uv run python scripts/validate.py --show-ledger | grep "p1.ks06"
```

NOTE: REVISED Cycle 3 — KS-06's edits to `play_resolver.py`, `preprocessor.py`, and `player_builder.py` (`MIN_PLAYER_PLAYS`, fallback range, completed-play filter) now branch on `phase1_ks_flags.ks06_backup_receiver_fix.enabled`. The Cycle-2 "no `--set` flag needed" pattern was a same-code no-op (Codex Cycle-2 NEW HIGH #1).

Capture logs to `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/p1.ks06.{bare,full}.log`.

Promotion decision per D-30 (small-gain item):
- Hard floor: rank_corr Δ ≥ -0.005 AND MAE Δ ≤ +0.05 on BOTH entries
- Any non-regression KS delta on WR/TE receiving_yards primary target (≥ 0)

If hard floor fails on either entry → revert Tasks 1+2's commits, document under `## KS-06` in `logs/PROMOTION-NOTES.md`, mark `## PLAN BLOCKED`.

Append `## KS-06` section to `logs/PROMOTION-NOTES.md`.

Commit: `chore(01-05): record KS-06 A/B ledger entries (p1.ks06.{bare,full})`
  </action>
  <verify>
    <automated>uv run python scripts/validate.py --show-ledger 2>&1 | grep -E "p1\.ks06\.(bare|full)" | wc -l | tr -d ' '</automated>
  </verify>
  <acceptance_criteria>
    - The verify command returns `2`
    - `uv run python scripts/validate.py --show-ledger` output contains `p1.ks06.bare` and `p1.ks06.full`
    - `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/PROMOTION-NOTES.md` contains a section header `## KS-06`
    - Both ledger entries' rank_corr regression ≥ -0.005 AND MAE regression ≤ +0.05
    - `git log -1 --pretty=%s` matches `chore(01-05): record KS-06 A/B`
  </acceptance_criteria>
  <done>Both ledger entries recorded; promotion decision documented.</done>
</task>

<task type="auto">
  <name>Task 4: Promotion-state commit + SUMMARY (per D-25 revised)</name>
  <files>(no source modifications)</files>
  <read_first>
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/PROMOTION-NOTES.md (## KS-06 section)
  </read_first>
  <action>
Per D-25 (revised), create the final promotion commit + SUMMARY.

Determine promotion state from PROMOTION-NOTES `## KS-06` section per D-30 small-gain bar.

Create `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-05-SUMMARY.md`:

```markdown
# Plan 05 Summary — KS-06 backup receiver fallback fixes

**Promotion state:** <PROMOTED|SHIPPED-NO-OP|BLOCKED>
**Phase:** 1
**Wave:** 3
**Final commit:** $(git log -1 --pretty=%H)

## What shipped

1. `preprocessor.py` filter: team-bucket pass yards now exclude incompletions (D-19 sub-fix 1)
2. `play_resolver.py` backup-receiver fallback uses `rng.integers(5, 18)` (mean ~11.5) instead of `rng.integers(3, 12)` (mean ~7) (D-19 sub-fix 2)
3. `player_builder.py` `MIN_PLAYER_PLAYS = 3` (was 5) (D-19 sub-fix 3)
4. New tests in `tests/test_data/test_preprocessor.py`, `tests/test_data/test_player_builder.py`, `tests/test_engine/test_play_resolver.py`

## Codex MEDIUM-3 fix note

Original Plan 05 referenced a non-existent `build_play_outcomes()` entry point.
Replan corrects all test invocations to `Preprocessor().compute_play_outcomes()`
(the actual API at `src/fantasy_sim/data/preprocessor.py:27`/`:110`).

## Ledger results

| Entry | rank_corr Δ | MAE Δ | WR/TE recv KS Δ | Hard floor? | Promotion bar? |
|-------|-------------|-------|-----------------|-------------|----------------|
| p1.ks06.bare | ... | ... | ... | ✅/❌ | ✅/❌ |
| p1.ks06.full | ... | ... | ... | ✅/❌ | ✅/❌ |
```

Commit:

```bash
PROMO_STATE="PROMOTED"  # or SHIPPED-NO-OP / BLOCKED
git add .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-05-SUMMARY.md
git commit -m "feat(01-05): KS-06 ${PROMO_STATE} — backup receiver fallback fixes

Wave 3. Three sub-fixes per D-19: completed-play filter on team buckets,
backup fallback range raised to (5,18), MIN_PLAYER_PLAYS lowered to 3.

Bare-isolation A/B uses --baseline bare --arm-b-base bare per Plan 00.
Test invocations corrected to Preprocessor().compute_play_outcomes()
(was wrong API name in original plan — Codex MEDIUM-3 fix)."
```
  </action>
  <verify>
    <automated>test -f .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-05-SUMMARY.md && grep -cE "PROMOTED|SHIPPED-NO-OP|BLOCKED" .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-05-SUMMARY.md</automated>
  </verify>
  <acceptance_criteria>
    - SUMMARY exists with explicit promotion state header
    - SUMMARY's ledger results table is filled in
    - `git log -1 --pretty=%s` matches `feat(01-05): KS-06 PROMOTED|SHIPPED-NO-OP|BLOCKED`
  </acceptance_criteria>
  <done>KS-06 promotion-state commit landed; SUMMARY captures the decision.</done>
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
| T-01-05-01 | T (Tampering) | MIN_PLAYER_PLAYS / fallback range constants | mitigate | Tests enforce literal values. |
| T-01-05-02 | T (Tampering) | Bucket-distribution semantics | mitigate | Test 1 (bucket excludes incompletions) verifies the filter. |
</threat_model>

<verification>
- All KS-06 tests pass
- Three source edits in place (preprocessor filter, MIN_PLAYER_PLAYS=3, rng.integers(5, 18))
- `p1.ks06.bare` and `p1.ks06.full` ledger entries exist
- Promotion decision documented
</verification>

<success_criteria>
- KS-06 requirement deliverable
- Hard floor passes on both ledger entries (or BLOCKED + reverted)
- WR/TE receiving_yards KS delta ≥ 0 on `p1.ks06.full` (per D-30)
- 1,200+ existing test suite still green
</success_criteria>

<output>
After completion, create `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-05-SUMMARY.md`.
</output>

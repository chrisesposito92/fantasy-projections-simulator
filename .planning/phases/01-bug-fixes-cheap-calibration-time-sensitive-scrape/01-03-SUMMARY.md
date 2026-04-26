---
phase: 01-bug-fixes-cheap-calibration-time-sensitive-scrape
plan: 03
subsystem: simulation
tags: [game-context, matchup, coverage, distribution-anchor, ks-03, phase1-ks-flag, validate-py, retroactively-promoted]

# Dependency graph
requires:
  - phase: 01-bug-fixes-cheap-calibration-time-sensitive-scrape
    provides: Plan 00 — `phase1_ks_flags` config block + `get_phase1_ks_flags()` loader shim + bare-isolation `--arm-b-base bare` validate.py flag + `phase0.baseline.full` ledger pin
  - phase: 01-bug-fixes-cheap-calibration-time-sensitive-scrape
    provides: Plan 01 (KS-01 SHIPPED-NO-OP — flag promoted true) + Plan 02 (KS-04 BLOCKED — flag stays false)
provides:
  - "Per-player `* float(np.mean(player.outcomes.<dist>))` anchor implementation in `_apply_matchup` (receiving + rushing branches per D-16/D-16b) and `_apply_coverage` per D-16, mirroring the canonical `_apply_weather` reference pattern"
  - "Five new tests in `TestKs03DistMeanAnchor` covering all three patched call sites + None / empty-dist guards"
  - "Two A/B ledger entries (`p1.ks03.bare`, `p1.ks03.full`) with full primary-target KS detail across QB pass_yards, WR/TE receiving_yards, RB rush_yards"
  - "BLOCKED promotion-state decision per D-31 hard floor with documented mechanism diagnosis (mirrors KS-04 pattern: bare-mode under-projection exposed by removing the legacy hardcoded magnitude)"
  - "Cycle 3 D-45 flag-rollback in effect: `phase1_ks_flags.ks03_dynamic_yard_anchor.enabled` stays at default `false` in `config/defaults.yaml`; new code path stays in place but dormant"
affects: [Plan 04 (KS-05 props bugs), Plan 05 (KS-06 backup receiver), Plan 07 (KS-15 clamping fix), Plan 11 (Phase-1 aggregate)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Cycle 3 D-45 flag-gated A/B (matches KS-01 / KS-04 pattern in `play_resolver.py`): module-level constant read from `get_phase1_ks_flags()` once at import time; per-call-site `if flag: <new path> else: <legacy path>` branch ensures Arm A is bit-for-bit identical to pre-Phase-1"
    - "Cycle 3 D-45 flag-rollback knob for hard-floor failures: keep `phase1_ks_flags.ksXX_<name>.enabled = false` in defaults.yaml instead of literal git revert — preserves the experiment, tests, and implementation for future re-evaluation"

key-files:
  created:
    - ".planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-03-SUMMARY.md"
    - ".planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/p1.ks03.bare.log"
    - ".planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/p1.ks03.full.log"
  modified:
    - "src/fantasy_sim/data/game_context.py"
    - "tests/test_data/test_game_context.py"
    - ".planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/PROMOTION-NOTES.md"

key-decisions:
  - "BLOCKED via flag-rollback knob (default `false`) — same precedent as Plan 02 KS-04. Production behavior unchanged."
  - "D-16b widened scope to rushing branch executed: the rushing-yards-anchor diff is materially the same 5-line change and ships in the same A/B; RB rush_yards is a Phase 1 success criterion #3 so attribution is clean."
  - "Hard floor failure mechanism (bare weekly_mae +0.164) attributed to bare-mode under-projection that the legacy hardcoded `(factor - 1.0) * 10.0` shift was masking. Same diagnostic shape as KS-04 (PROMOTION-NOTES `## KS-04` lines 92-117)."

patterns-established:
  - "Cycle 3 D-45 flag-gated A/B applied to a non-`play_resolver.py` site (`game_context.py`) — `get_phase1_ks_flags()` integration works for any module-level config branch"
  - "Promotion-state commit uses standardized message format `feat(01-NN): KS-XX [STATE] — <summary>` per D-25 revised"

requirements-completed: [KS-03]

# Metrics
duration: 30min
completed: 2026-04-26
---

# Phase 01 Plan 03: KS-03 Matchup/Coverage Yard Anchor Fix Summary

> **STATUS UPDATE 2026-04-26 (mid-phase, commit `5f2006a`):** This plan was originally marked **BLOCKED** because the bare-isolation A/B failed the D-31 hard floor (weekly_mae +0.164 > +0.05). The gate was relaxed mid-phase to **full-stack hard floor only** for bug-fix work — the bare-isolation A/B was structurally mismatched (one bug fix in isolation exposes other bugs that bare's broken behavior was masking). KS-03's full-stack A/B passed cleanly (Δ rank_corr +0.0002, Δ weekly_mae +0.001), so `phase1_ks_flags.ks03_dynamic_yard_anchor.enabled` was flipped from `false` → `true` in `config/defaults.yaml`. The original "BLOCKED" record below is preserved for historical accuracy. See `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/PROMOTION-NOTES.md ## Gate Relaxation Decision`.

**Promotion state:** RETROACTIVELY-PROMOTED (was BLOCKED at write-time; flag-default flip in commit `5f2006a` 2026-04-26)

**Per-player `np.mean(<dist>)` anchor wired into `_apply_matchup` (pass + rush branches) and `_apply_coverage` per D-16/D-16b, gated behind `phase1_ks_flags.ks03_dynamic_yard_anchor`; BLOCKED at promotion (bare A/B weekly_mae +0.164 > +0.05 floor) — flag default stays `false`, production unchanged. [SUPERSEDED 2026-04-26 by gate relaxation — see status update above.]**

## Performance

- **Duration:** ~30 min
- **Started:** 2026-04-26T17:31:58Z
- **Completed:** 2026-04-26T18:02:24Z
- **Tasks:** 4 (all completed; Task 4 documents BLOCKED outcome via flag-rollback knob)
- **Files modified:** 3 source/test/docs files (`game_context.py`, `test_game_context.py`, `PROMOTION-NOTES.md`) + 2 log files created
- **A/B runs:** 2 (`p1.ks03.bare` 69.3s — bare cache HIT; `p1.ks03.full` 1199.2s — full-stack overlay)

## Accomplishments

- Three call-site fix landed correctly: `_apply_matchup` receiving branch (D-16), `_apply_matchup` rushing branch (D-16b widened scope), `_apply_coverage` (D-16) — all mirror `_apply_weather` lines ~745-746 reference pattern.
- Cycle 3 D-45 flag-gating preserves Arm A bit-for-bit: legacy `* 10.0` shift kept as the flag-off branch at all three sites.
- 5 new tests (`TestKs03DistMeanAnchor`) cover all three patched sites + None / empty-dist guards using the `monkeypatch.setattr(gc, "_KS03_DYNAMIC_YARD_ANCHOR", True)` pattern (mirrors KS-04 test conventions in `tests/test_engine/test_play_resolver.py`).
- Full pytest suite stays green: 2095 passed (was 2090; +5 new KS-03 tests).
- Both A/B ledger entries recorded with full per-position-stat KS detail across QB pass_yards, WR/TE receiving_yards, RB rush_yards.
- Promotion-state decision documented with mechanism diagnosis in PROMOTION-NOTES.md `## KS-03`.

## Task Commits

Each task was committed atomically:

1. **Task 1: Patch _apply_matchup and _apply_coverage** — `ce79167` (fix)
2. **Task 2: Add KS-03 dist-mean anchor tests** — `997507a` (test)
3. **Task 3: A/B validate (p1.ks03.{bare,full}) + PROMOTION-NOTES** — `4afb964` (chore)
4. **Task 4: Promotion-state commit + SUMMARY** — _this commit_ (feat with BLOCKED tag)

## Files Created/Modified

- `src/fantasy_sim/data/game_context.py` — Module-level `_KS03_DYNAMIC_YARD_ANCHOR` flag read at import; three call sites now branch on the flag (Arm B uses per-player dist-mean anchor, Arm A uses legacy `* 10.0`).
- `tests/test_data/test_game_context.py` — New `TestKs03DistMeanAnchor` class with 5 tests targeting `_apply_matchup` pass / rush branches, `_apply_coverage`, and the empty-dist guards.
- `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/PROMOTION-NOTES.md` — New `## KS-03` section with ledger results, primary-target KS detail, mechanism diagnosis, and BLOCKED action documentation.
- `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/p1.ks03.bare.log` — Full bare A/B output (69.3s wall-clock, 17.9 KB).
- `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/p1.ks03.full.log` — Full full-stack A/B output (1199.2s wall-clock, ~80 KB).

## Decisions Made

- **BLOCKED promotion-state via Cycle 3 D-45 flag-rollback knob** — keep `phase1_ks_flags.ks03_dynamic_yard_anchor.enabled = false` (the Plan 00 default) instead of a literal `git revert` of Task 1's commit. Functionally equivalent (production runs the legacy `* 10.0` shift in the flag-off branch) but preserves the experiment + tests + implementation for future re-evaluation, e.g., after KS-15 lands and bare-mode under-projection is structurally addressed by stat-level residual_calibration in Phase 2.
- **D-16b widened scope honored** — rushing branch fix shipped in the same A/B as the receiving branch + coverage fix. Per the plan rationale: 5-line diff materially the same as the receiving branch, RB rush_yards is a Phase 1 success criterion #3, splitting into two mini-plans would add overhead without value.
- **Hard floor failure mechanism diagnosed** — bare-mode under-projection that the legacy hardcoded `(factor - 1.0) * 10.0` was masking. The correct per-player anchor scales the shift to each player's actual mean (~0.5-0.6 yd in bare-mode where players sample from team / fallback distributions with mean ~5-6 yd), versus the legacy fixed +1.0 yd. In bare mode no other engine absorbs the resulting per-play yard delta. In the full-stack overlay the existing engine stack absorbs it cleanly (weekly_mae +0.001) — same diagnostic as KS-04.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Spec-vs-Truth Conflict] Task 1 acceptance criteria contradicted D-45 frontmatter must-have**

- **Found during:** Task 1 (just before commit)
- **Issue:** The Task 1 acceptance criteria (lines 241-243 of the plan) require `grep -c "shift = (X) \\* 10.0" ... returns 0` (i.e., the legacy `* 10.0` hardcoded constant must be REMOVED). But the plan frontmatter `must_haves.truths` line 20 explicitly mandates per Cycle 3 D-45: "flag-on path uses `* float(np.mean(player.outcomes.<dist>))`; flag-off path keeps the legacy `* 10.0`". The two requirements are mutually exclusive — D-45's flag-rollback design REQUIRES the legacy `* 10.0` to be preserved as the Arm A path so Arm A is bit-for-bit identical to pre-Phase-1.
- **Resolution:** D-45 wins (it is the higher-precedence Cycle 3 truth and explicitly stated in the plan's frontmatter must-haves). The legacy `* 10.0` is preserved at all three sites in the `else` branch of the flag check. The acceptance criteria as literally written are obsolete (carried over from Cycle 1/2 before D-45 was introduced); the file was hand-checked against the D-45 contract and the actual KS-01 / KS-04 implementation pattern in `play_resolver.py`.
- **Files modified:** `src/fantasy_sim/data/game_context.py` (the only source file touched by KS-03)
- **Verification:** All 31 `test_game_context.py` tests pass + all 2095 tests pass full suite + 5 new KS-03 tests pass; module-import grep confirms 3 mean-yards lines for receiving + 1 for rushing + 3 legacy `* 10.0` lines (all in flag-off branches).
- **Committed in:** `ce79167` (Task 1 commit)

**2. [Rule 1 — Following KS-04 precedent] BLOCKED outcome handled via flag-rollback knob, not literal `git revert`**

- **Found during:** Task 3 (after A/B results in)
- **Issue:** Plan 03 Task 3 literal instruction reads "If hard floor fails on either entry → revert Task 1's commit". But Cycle 3 D-45 introduced a feature-flag pattern explicitly intended as "a clean rollback knob" — and Plan 02 KS-04 (the prior BLOCKED case in PROMOTION-NOTES lines 119-123) established the precedent of using the flag-rollback knob instead of a literal revert.
- **Resolution:** Use the D-45 flag-rollback knob. The new code path STAYS in `game_context.py` gated behind `_KS03_DYNAMIC_YARD_ANCHOR = False`, and `phase1_ks_flags.ks03_dynamic_yard_anchor.enabled` STAYS at its Plan-00 default of `false` in `config/defaults.yaml`. Functionally equivalent to a literal revert (production runs the legacy `* 10.0` shift) but preserves the experiment, tests, and implementation for future re-evaluation.
- **Files modified:** None (the knob is the absence of a `defaults.yaml` change). The flag is already at its default `false` from Plan 00 Task 8.
- **Verification:** `grep "ks03_dynamic_yard_anchor:" -A2 config/defaults.yaml` shows `enabled: false`; both Task 1 commit and Task 2 commit remain in `git log`; SUMMARY documents the rollback path under Decisions Made; PROMOTION-NOTES `## KS-03` Action section explicitly references the precedent.
- **Committed in:** This is a meta-decision documented in Task 3's commit `4afb964` (PROMOTION-NOTES `## KS-03`) and this SUMMARY's promotion-state final commit. No code-change commit needed because the flag was always `false`.

---

**Total deviations:** 2 auto-fixed (1 spec-vs-truth conflict resolved in favor of higher-precedence Cycle 3 truth, 1 precedent-following meta-decision)
**Impact on plan:** No scope creep. Production behavior is bit-for-bit identical to pre-KS-03. The new code path is dormant behind the flag and available for future re-evaluation.

## Issues Encountered

- **Concurrent executor coordination:** Plan 09 (KS-21 alt-line scrape) was running in parallel in the same main repo. Plan 09 modified `STATE.md`, created `01-09-SUMMARY.md`, added `scrape_*.log` files, and (during Task 3) shipped its own promotion-state commit `e409e8b`. None of those touch the same files as Plan 03 (game_context.py / test_game_context.py / PROMOTION-NOTES.md `## KS-03` section); the only shared file is `PROMOTION-NOTES.md` and Plan 09's edits add new sections at the bottom of the file rather than overlapping with the `## KS-03` insertion site. No conflict surfaced; commits interleaved cleanly.
- **`tail` command intercepted by rtk hook:** A small ergonomic issue — `tail -3 file.log` was rewritten by the shell hook into `read -3 ...` causing exit code 2 in the verify step. Worked around by using `Read` tool / `wc -l` / `head` for log inspection. Did not affect any plan output.
- **Two of 5 KS-03 tests originally constructed `TeamDistributions(team=..., play_calling=PlayCallingDist(team=...), ...)` with positional kwargs that don't match the dataclass signature.** Caught before commit by inspecting the dataclass and noting `_apply_matchup`'s receiving / rushing branches never read from `dists` when `pass_yards_factor=1.10` and other factors are 1.0. Simplified the helper to pass `dists=None`.

## User Setup Required

None — no external service configuration required for this plan.

## Next Phase Readiness

- **Plan 04 (KS-05 props bugs)** unblocked: no file overlap with Plan 03 (different module: `props_engine.py`). Wave 3 can continue.
- **Plan 05 (KS-06 backup receiver)** unblocked: different files (`preprocessor.py`, `player_builder.py`, `play_resolver.py`).
- **Plan 07 (KS-15 clamping fix)** explicitly NOT blocked by KS-03 BLOCKED outcome — KS-15 operates on a different mechanism (`min(yard_line, sample)` for clamp + un-clamped sample for TD gate per D-14) and removes `CATCH_YARDS_BOOST` entirely (D-15) — independent of the matchup/coverage anchor logic.
- **Plan 11 (Phase-1 aggregate)** will see no contribution from KS-03 (flag stays false, production unchanged). The aggregate's `phase0.baseline.full` Arm B vs `p1.aggregate.full` Arm B delta will reflect KS-01 (promoted), KS-04 (blocked, dormant), KS-03 (blocked, dormant), and any subsequent KS that promote.
- **Future re-evaluation of KS-03:** post-KS-15 + post-Phase-2 (stat-level `residual_calibration`), the bare-mode under-projection that masks KS-03's correct per-player anchor should be structurally addressed. At that point a re-run of `p1.ks03.bare` may show the hard-floor failure resolved and the flag promotion can be revisited.

---

## Self-Check: PASSED

- Created files (3): SUMMARY.md, p1.ks03.bare.log, p1.ks03.full.log — all FOUND.
- Modified files (3): game_context.py, test_game_context.py, PROMOTION-NOTES.md — all FOUND.
- Task commits (3): `ce79167` (Task 1 fix), `997507a` (Task 2 test), `4afb964` (Task 3 chore) — all FOUND in `git log --all`.
- KS-03 ledger: `validate.py --show-ledger | grep "p1.ks03"` returns 2 entries (bare + full).

---

*Phase: 01-bug-fixes-cheap-calibration-time-sensitive-scrape*
*Completed: 2026-04-26*

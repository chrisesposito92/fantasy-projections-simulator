---
phase: 1
reviewers: [codex]
reviewed_at: 2026-04-26
plans_reviewed:
  - 01-ks01-rz-tdgate-fix-PLAN.md
  - 02-ks04-catch-yards-boost-PLAN.md
  - 03-ks03-matchup-coverage-anchor-PLAN.md
  - 04-ks05-props-engine-bugs-PLAN.md
  - 05-ks06-backup-receiver-fallback-PLAN.md
  - 06-ks07-positional-rz-catch-rate-PLAN.md
  - 07-ks15-clamping-fix-PLAN.md
  - 08-ks29-team-context-enable-PLAN.md
  - 09-ks21-altline-scrape-PLAN.md
  - 10-ks32-clock-runoff-measure-PLAN.md
  - 11-phase1-aggregate-validation-PLAN.md
model: gpt-5.4
---

# Cross-AI Plan Review — Phase 1: Bug Fixes, Cheap Calibration & Time-Sensitive Scrape

External reviewer: **OpenAI Codex CLI (gpt-5.4)**, invoked with the full Phase 1 bundle (PROJECT.md, REQUIREMENTS.md, ROADMAP.md, 01-CONTEXT.md, 01-RESEARCH.md, 01-VALIDATION.md, all 11 PLAN.md files).

---

## Codex Review

### Summary

The phase is well-scoped at the hypothesis level, and the RZ-stack ordering is mostly sensible. The problem is the execution machinery around it. A few assumptions in the plans do not match the current repo behavior, especially the A/B harness semantics, the Odds API raw-vs-processed pipeline, and the aggregate baseline comparison. Those are real blockers because they can produce misleading evidence or outright execution failure even if the underlying code fixes are correct.

### Strengths

- The phase boundary is clear. Bug fixes, cheap retunes, structural work, and new-signal work are separated cleanly.
- The RZ stack ordering, `KS-01 -> KS-04 -> KS-15`, is the right instinct and is called out explicitly.
- Promotion states are explicit. `PROMOTE`, `SHIPPED NO-OP`, `BLOCKED`, `SHIPPED OFF`, and `MEASURED-NO-CHANGE` are a good pattern for a calibration-heavy initiative.
- Most plans are grounded in concrete files and functions instead of vague architecture talk.
- The hard-floor discipline is strong in intent, even though the current validation wiring does not fully implement that intent.

### Concerns

#### HIGH severity

- **The "bare" A/B runs are not isolation runs** — This is the biggest issue in the whole set. The plans repeatedly treat `--baseline bare` as "bare + only this change", but the current harness defines Arm B as `defaults + overrides`, not `bare + overrides`. That is explicit in [scripts/validate.py](../../../scripts/validate.py) (around line 319) and reinforced by the parser shape (lines 324, 336). As written, every `p1.ksXX.bare` result is contaminated by all default-on engines, so the "isolation + full-stack" discipline in Plans 01-08 and 10 is not actually being satisfied. **Suggested fix:** either add a true Arm-B bare mode to `validate.py`, or make each isolation run explicitly disable every non-target engine in Arm B.
- **Plan 09 fetches raw snapshots, not processed parquet signals** — `fetch_market_history_props.py` writes raw JSON snapshots through `raw_props_path()` and `save_raw_props_snapshot()` ([scripts/fetch_market_history_props.py](../../../scripts/fetch_market_history_props.py) line ~79; [props_backfill.py](../../../src/fantasy_sim/data/market_history/props_backfill.py) line ~83). The processed parquet artifacts the plan wants come from a separate step, [scripts/build_market_history_player_markets.py](../../../scripts/build_market_history_player_markets.py), which calls [player_markets.py](../../../src/fantasy_sim/data/market_history/player_markets.py) line ~183. Plan 09's execution steps and acceptance criteria assume parquet appears directly from the fetch script, which is false today. **Suggested fix:** split Plan 09 into raw fetch and processed-build tasks, and gate acceptance on both.
- **The "Tuesday 12pm ET open snapshot" is not implemented by the current timestamp source** — The current event inventory is built from a gameday noon snapshot window in [events_inventory.py](../../../src/fantasy_sim/data/market_history/events_inventory.py) line ~84, and `previous_snapshot_timestamp` is just the API's prior timestamp relative to that crawl, not a persisted Tuesday line-release marker (events_inventory.py line ~245). Plan 09 treats `--date-source previous_snapshot_timestamp` as "Tuesday 12pm ET", but the current pipeline does not guarantee that. That means `open_core8` and `open_alt6` may be mislabeled. **Suggested fix:** either extend event inventory generation to store a real Tuesday snapshot reference, or rename the deliverable to what it actually is, "prior-available snapshot", and adjust Phase 4 expectations.
- **Plan 11 does not actually compare Phase 1 against a true Phase-0 baseline** — As written, `p1.aggregate.full` runs `validate.py --baseline defaults` with no overrides, so Arm A and Arm B are the same current defaults state. That only records a snapshot, it does not validate "post-Phase-1 defaults vs original Phase-0 baseline". The ledger model in [ledger.py](../../../src/fantasy_sim/validation/ledger.py) line ~56 stores A/B results for a single run, it does not magically recover an earlier baseline unless you have already pinned one. **Suggested fix:** before execution starts, create a frozen Phase-0 baseline artifact or label and make Plan 11 compare against that explicit artifact, not against doc text or a no-op A/B run.

#### MEDIUM severity

- **KS-03 quietly widens scope beyond the stated hypothesis** — The plan's stated requirement is about `_apply_matchup` and `_apply_coverage` on receiving yards, but Task 1 also changes the rushing branch in [game_context.py](../../../src/fantasy_sim/data/game_context.py) line ~546. That may be a good bug fix, but it is not the same deliverable, and it muddies attribution on RB rush_yards, which is already a tracked Phase 1 success criterion. **Suggested fix:** either split the rushing-anchor change into its own mini-plan or explicitly widen KS-03's scope and validation targets.
- **The commit model contradicts the "one commit per KS-XX" rule** — The phase-level rules say one commit per KS item, but several plans produce RED, GREEN, and ledger commits separately. That gets worse because Plan 09 runs in parallel in wave 1, so acceptance rules like "KS-01 commit is HEAD~3 after Plan 01 lands" are not stable. This is not fatal, but it breaks the stated bisect and rollback story. **Suggested fix:** keep task-level work local, then squash to one promotion commit per KS item once its A/B gate passes.
- **Several task instructions point at the wrong execution surface** — Examples: Plan 04 Task 1 runs `pytest` against `src/fantasy_sim/data/vegas/`, which is a source directory, not a test target; Plan 05's test sketch references a `build_play_outcomes` entrypoint that does not exist because the current API is `Preprocessor.compute_play_outcomes()` in [preprocessor.py](../../../src/fantasy_sim/data/preprocessor.py) line ~102. These are fixable, but they mean the executor will be repairing the plans while trying to follow them. **Suggested fix:** normalize each plan against the actual callable test and source surfaces before execution starts.
- **KS-15 leaves legacy pass/run paths ambiguous** — The plan thoroughly rewires the roster-aware paths, but it does not explicitly say whether the legacy no-roster paths in [play_resolver.py](../../../src/fantasy_sim/engine/play_resolver.py) lines ~301 and ~389 must stay behaviorally aligned. If validation or fallback flows ever hit those paths, you can end up with two different clamping semantics in the same codebase. **Suggested fix:** either patch them too, or declare and test that validation never uses them.

#### LOW severity

- **Acceptance checks are too string-fragile in places** — Several plans require exact helper names or exact grep strings. That makes harmless refactors fail the plan even when behavior is correct. Behavior-level assertions are better than literal-string assertions for most of these checks.
- **Plan 08's QB preflight is partially redundant** — The repo already has direct tests asserting `TierEngine.apply_team_context()` leaves QBs unchanged in [tests/test_data/test_pff/test_tier_engine.py](../../../tests/test_data/test_pff/test_tier_engine.py) line ~848. A one-off grep preflight is weaker than simply leaning on or extending that test coverage.
- **The log and summary path creation is assumed, not guaranteed** — Many tasks write to `.planning/.../logs/...` and summary files without first ensuring those directories exist. Small thing, but it is an easy source of avoidable shell noise.

### Suggestions

- Fix the validation semantics first. If you want true isolation, make the harness support true isolation. Everything else depends on that.
- Rewrite Plan 09 as `raw fetch -> processed parquet build -> schema/timing verification`. Right now it conflates those steps.
- Pin a real Phase-0 baseline artifact before Phase 1 starts. Then make Plan 11 compare against that exact artifact.
- Collapse each KS item to one promotion commit after its gate passes. Keep RED/GREEN churn out of the durable history.
- Trim KS-03 back to its stated receiving-yards scope, or explicitly widen the hypothesis and success criteria so attribution stays honest.

### Risk Assessment

**Overall risk level:** HIGH

The fixes themselves are mostly sensible. The blocking risk is that the plans will produce evidence that looks disciplined but is not actually answering the intended questions, especially around isolation A/B runs, the Odds API artifact pipeline, and the final baseline comparison. Those need to be corrected before execution starts.

---

## Consensus Summary

This review pass had a single external reviewer (Codex / gpt-5.4), so "consensus" here is just the synthesis of that single pass into actionable severity buckets. Cross-AI consensus would require a second reviewer; the planning loop can re-run with `--gemini` or `--claude` if desired.

### Agreed Strengths

(All from a single reviewer; carried as-is)

- Clear phase boundary separating bug fixes / calibration retunes / structural work / new signals.
- Correct RZ-stack dependency ordering (KS-01 → KS-04 → KS-15).
- Explicit promotion-state vocabulary (PROMOTE / SHIPPED NO-OP / BLOCKED / SHIPPED OFF / MEASURED-NO-CHANGE).
- Plans grounded in concrete file:line refs and verified mechanism descriptions.
- Strong hard-floor discipline in intent (rank_corr ≥ -0.005, weekly_mae ≤ +0.05).

### Agreed Concerns (HIGH severity — must address before execution)

The four HIGH-severity concerns from Codex are all genuine blockers that would corrupt Phase 1's evidence base. They cluster around two themes:

1. **Validation semantics mismatch** (HIGH-1, HIGH-4): the harness behavior in `scripts/validate.py` does not match what the plans claim it does. `--baseline bare` produces `defaults + overrides`, not `bare + overrides`, so the per-plan "isolation" runs are actually contaminated full-stack runs under a misleading label. The end-of-phase aggregate (Plan 11) compares defaults to defaults, which records a no-op snapshot rather than the post-Phase-1-vs-Phase-0 delta the plan claims.
2. **Odds API scrape pipeline mismatch** (HIGH-2, HIGH-3): the scrape script (`fetch_market_history_props.py`) writes raw JSON; the parquet that downstream code (and Plan 09's acceptance) needs is produced by a separate `build_market_history_player_markets.py` step that Plan 09 doesn't call. Additionally, the "Tuesday 12pm ET open snapshot" semantic is not implemented by the existing event inventory or the `previous_snapshot_timestamp` flag.

### MEDIUM-severity concerns to address (not blocking, but should not slip)

- KS-03 scope creep into the rushing branch (muddles RB rush_yards attribution that Phase 1 explicitly tracks).
- Multi-commit-per-plan model contradicts the documented "one commit per KS-XX" rule and breaks bisect cleanly across the parallel wave-1 plans.
- Several task instructions reference the wrong test/source paths or non-existent APIs (Plan 04 / Plan 05).
- KS-15 does not address the legacy non-roster `_resolve_pass`/`_resolve_run` paths.

### LOW-severity polish (optional)

- Tighten brittle string-grep acceptance checks in favor of behavior-level assertions.
- Use existing Tier engine tests rather than ad-hoc grep preflights in Plan 08.
- Ensure log and summary directories exist before tasks write to them.

### Divergent Views

Single-reviewer pass; no divergence to record. If a follow-up Gemini/Claude review is run, divergence between reviewers will surface here.

---

## Recommended Next Action

Per the GSD convergence pattern, the four HIGH-severity concerns should feed back into planning before Phase 1 execution starts:

```
gsd-plan-phase 1 --reviews
```

Specifically, the planner should:

1. **Decide the validation-semantics question** (HIGH-1, HIGH-4): either teach `validate.py` true isolation mode + a pinned Phase-0 baseline label, or rename the per-plan ledger labels to honestly describe the contaminated semantics. The first option preserves the intent of "isolation + full-stack" discipline; the second sacrifices it.
2. **Re-scope Plan 09** (HIGH-2, HIGH-3): split into raw-fetch → processed-parquet-build → schema/timing-verification tasks, and explicitly resolve the "Tuesday 12pm ET" naming question (either fix the timestamp source or rename the snapshot label).
3. **Address MEDIUM concerns** as part of the same planning revision (KS-03 scope, commit model, wrong execution surfaces, KS-15 legacy paths).
4. **Skip LOW concerns** unless they're cheap to fix in passing.

Phase 1 is **not safe to execute** as currently planned — the per-KS A/B evidence and the end-of-phase aggregate would both be misleading. Once the HIGH concerns are resolved and the planner refreshes the affected PLAN.md files, re-run `gsd-review --phase 1` to confirm convergence.

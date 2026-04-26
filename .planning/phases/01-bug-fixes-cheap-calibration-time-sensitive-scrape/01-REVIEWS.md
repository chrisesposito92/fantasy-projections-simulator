---
phase: 1
cycles:
  - cycle: 1
    reviewers: [codex]
    reviewed_at: 2026-04-26
    model: gpt-5.4
    bundle_commit: pre-93005e4
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
  - cycle: 2
    reviewers: [codex]
    reviewed_at: 2026-04-26
    model: gpt-5.4
    bundle_commit: 93005e4
    plans_reviewed:
      - 00-validation-harness-and-phase0-baseline-PLAN.md
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
  - cycle: 3
    reviewers: [codex]
    reviewed_at: 2026-04-26
    model: gpt-5.4
    bundle_commit: e641a06
    plans_reviewed:
      - 00-validation-harness-and-phase0-baseline-PLAN.md
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
---

# Cross-AI Plan Review — Phase 1: Bug Fixes, Cheap Calibration & Time-Sensitive Scrape

External reviewer: **OpenAI Codex CLI (gpt-5.4)**, invoked with the full Phase 1 bundle (PROJECT.md, REQUIREMENTS.md, ROADMAP.md, 01-CONTEXT.md, 01-RESEARCH.md, 01-VALIDATION.md, all 11 PLAN.md files).

---

# Cycle 1 (2026-04-26 — pre-replan)

## Codex Review (Cycle 1)

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

## Consensus Summary (Cycle 1)

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

## Recommended Next Action (Cycle 1)

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

---

# Cycle 2 (2026-04-26 — post-replan at commit `93005e4`)

External reviewer: **OpenAI Codex CLI (gpt-5.4)**, invoked with the FULL post-replan Phase 1 bundle (PROJECT.md, ROADMAP.md, REQUIREMENTS.md, the verbatim Cycle-1 `01-REVIEWS.md` for context, the updated `01-CONTEXT.md` / `01-RESEARCH.md` / `01-VALIDATION.md`, and all 12 PLAN.md files including the new Plan 00). Codex was explicitly instructed to verify whether each prior HIGH was actually resolved and to flag any new HIGHs introduced by the replan.

## Codex Review (Cycle 2)

> Reviewed at `93005e4`. The replan is better, but I do not think Phase 1 is safe to execute yet.

### Findings

- **HIGH** — The per-KS A/B plan is still invalid for the code-change plans. [`01-VALIDATION.md`](./01-VALIDATION.md) (line 53 / Per-Plan Verification Map) defines Plans 01-07 and the retune branch of 10 as plain `validate.py` runs with no `--set`, and [`01-ks01-rz-tdgate-fix-PLAN.md`](./01-ks01-rz-tdgate-fix-PLAN.md) (line 297, Task 3) says that is fine because "the change ships as the source code itself." It is not fine: both arms in a single `validate.py` run execute the same patched code, so `p1.ks01.*`, `p1.ks03.*`, `p1.ks04.*`, `p1.ks05.*`, `p1.ks06.*`, `p1.ks07.*`, `p1.ks15.*`, and the retuned `p1.ks32.*` cannot measure the marginal effect of the code change at all. The new `--arm-b-base bare` flag only fixes config-arm construction; it does NOT create a pre/post code-version comparison. Suggested fix: put each KS code change behind a feature flag and use `--set <flag>=true` for Arm B, OR pin pre-commit and post-commit ledger entries explicitly around each KS commit (no two-arm same-code runs).
- **HIGH** — The proposed `bare_config_dict()` is not actually equivalent to a bare arm. In [`00-validation-harness-and-phase0-baseline-PLAN.md`](./00-validation-harness-and-phase0-baseline-PLAN.md) (line 184, Task 1 helper definition), the helper turns off sub-engine leaves but omits top-level gates like `pff.enabled`, `vegas.enabled`, and `usage.enabled`. Meanwhile [`src/fantasy_sim/validation/config.py:94`](../../../src/fantasy_sim/validation/config.py), [`src/fantasy_sim/data/pff/config.py:308`](../../../src/fantasy_sim/data/pff/config.py), [`src/fantasy_sim/data/vegas/config.py:28`](../../../src/fantasy_sim/data/vegas/config.py), and [`src/fantasy_sim/data/usage/config.py:32`](../../../src/fantasy_sim/data/usage/config.py) all key off those top-level flags. Plan 00 then explicitly allows "loosen the test" if the end-to-end check disagrees ([`00-validation-harness-and-phase0-baseline-PLAN.md`](./00-validation-harness-and-phase0-baseline-PLAN.md) line 579, Task 4). That means HIGH-1 is not fully closed even for config-driven work like KS-29. Suggested fix: make `bare_config_dict()` exactly mirror `build_bare_engine_configs()` semantics (include the top-level gates) and remove the "loosen the test" escape hatch — the integration test should be a hard gate.
- **HIGH** — Plan 11 still cannot verify success criterion 1 as written. The delta script in [`11-phase1-aggregate-validation-PLAN.md`](./11-phase1-aggregate-validation-PLAN.md) (line 145, Task 2 delta-computation step) only extracts `rank_corr`, `MAE`, and `stat_ks`, and the ledger schema in [`src/fantasy_sim/validation/ledger.py:25`](../../../src/fantasy_sim/validation/ledger.py) has no mean-bias field anywhere. But the acceptance block still asks the plan to fill "QB pass_yards mean bias (yd/g)" and mark Phase 1 success criterion #1 YES/NO at [`11-phase1-aggregate-validation-PLAN.md`](./11-phase1-aggregate-validation-PLAN.md) line 232. That metric is not available from the planned artifact path. Suggested fix: extend `validate.py`/ledger to surface mean-bias per stat-position, OR change Plan 11 so criterion 1 is evaluated from a side artifact (e.g., a separate diagnostic script that consumes raw projection rows).
- **MEDIUM** — KS-21 is corrected in Plan 09, but the canonical bundle is still internally contradictory. The revised story is in [`01-CONTEXT.md`](./01-CONTEXT.md) (line 27, D-02 / D-06 revisions) and [`09-ks21-altline-scrape-PLAN.md`](./09-ks21-altline-scrape-PLAN.md) (line 304), but [`01-RESEARCH.md`](./01-RESEARCH.md) at lines 14, 206, and 653 still say `open_*`, "Tuesday 12pm ET," and "fetch_market_history_props.py … writes parquet." Since RESEARCH is listed as a canonical reference downstream agents must read, HIGH-2 and HIGH-3 are still partially reintroduced by the bundle itself. Suggested fix: reconcile `01-RESEARCH.md` with `01-CONTEXT.md` and Plan 09 so only the `prior_*` / raw→build pipeline story remains.
- **MEDIUM** — Plan 09's credit-balance logging cannot work as written. The raw scrape task greps `x-requests-remaining` from the run logs at [`09-ks21-altline-scrape-PLAN.md`](./09-ks21-altline-scrape-PLAN.md) line 370, but the current fetch script only prints `cost={x-requests-last}` at [`scripts/fetch_market_history_props.py:110`](../../../scripts/fetch_market_history_props.py). Unless that script is extended, the before/after credit tables in Plan 09 are not collectible from the proposed logs. Suggested fix: extend `fetch_market_history_props.py` to also log `x-requests-remaining` from the response headers, or change the credit-tracking acceptance to a manual check against the Odds API dashboard.

### Prior HIGHs — verification

| HIGH | Disposition | Reasoning |
|------|-------------|-----------|
| HIGH-1 | **PARTIALLY-RESOLVED** | The new `--arm-b-base bare` idea addresses the original defaults-vs-bare contamination in principle, but (a) the helper implementation is not truly bare (omits top-level engine gates) and (b) the code-change plans still use no-op A/Bs (both arms run the same patched code). |
| HIGH-2 | **PARTIALLY-RESOLVED** | Plan 09 now explicitly does raw fetch plus parquet build, but `01-RESEARCH.md` still repeats the old "fetch writes parquet" model in three places (lines 14, 206, 653). |
| HIGH-3 | **PARTIALLY-RESOLVED** | `01-CONTEXT.md` and Plan 09 renamed `open_*` to `prior_*`, but `01-RESEARCH.md` still contains the stale "Tuesday 12pm ET / open_*" instructions in the same three sections. |
| HIGH-4 | **RESOLVED** | [`11-phase1-aggregate-validation-PLAN.md`](./11-phase1-aggregate-validation-PLAN.md) line 128 now uses `phase0.baseline.full` plus `p1.aggregate.full`, so the original defaults-vs-defaults no-op problem is closed. (A separate new HIGH about mean-bias retrieval is logged above; that is a different gap.) |

### Recommended Replan (Cycle 2 → Cycle 3)

1. **Split validation strategy by change type.** For KS-01/03/04/05/06/07/15/32 (code-change plans), either put the code change behind a flag and use `--set`, OR use explicit pre/post ledger pins around the commit. Do not treat same-code two-arm runs as per-KS evidence.
2. **Make `bare_config_dict()` exactly mirror `build_bare_engine_configs()`** — include the top-level gates (`pff.enabled`, `vegas.enabled`, `usage.enabled`, etc.) and remove the "loosen the test" escape hatch.
3. **Reconcile `01-RESEARCH.md`** with `01-CONTEXT.md` and Plan 09 so only the `prior_*` / raw→build pipeline story remains.
4. **Add durable mean-bias output** to `validate.py` / ledger schema, OR change Plan 11 so success criterion 1 is evaluated from an artifact that actually contains the bias number.
5. Address Plan 09 credit-balance MEDIUM by extending `fetch_market_history_props.py` to surface `x-requests-remaining`.

### Recommendation

**NEEDS-CYCLE-3.** Three new HIGH-severity issues remain (per-KS code-change A/B is no-op; `bare_config_dict()` is incomplete; Plan 11 mean-bias not in ledger), and two of the prior HIGHs are still partially open via stale `01-RESEARCH.md` content. Phase 1 is **not safe to execute** until these are addressed.

---

## Consensus Summary (Cycle 2)

Single external reviewer (Codex / gpt-5.4) again, so "consensus" is the synthesis of that single pass into actionable severity buckets. The replan closed exactly one of the four prior HIGHs cleanly (HIGH-4 frozen Phase-0 baseline + delta computation), substantially advanced two more (HIGH-2, HIGH-3 via Plan 09 split + label rename in CONTEXT and Plan 09), and made structural progress on HIGH-1 (`--arm-b-base bare` + Plan 00) without finishing the work.

### Net Cycle-2 disposition (HIGH only)

| Concern source | Disposition | Counts toward CYCLE_SUMMARY? |
|----------------|-------------|------------------------------|
| Cycle 1 HIGH-1 (per-KS bare A/B contamination) | PARTIALLY-RESOLVED — superseded by two more-specific Cycle 2 HIGHs (no-op same-code A/B + incomplete `bare_config_dict`) | YES |
| Cycle 1 HIGH-2 (Plan 09 raw vs parquet) | PARTIALLY-RESOLVED — Plan 09 fixed; `01-RESEARCH.md` still stale | YES |
| Cycle 1 HIGH-3 (Tuesday-12pm-ET label honesty) | PARTIALLY-RESOLVED — `01-CONTEXT.md` and Plan 09 fixed; `01-RESEARCH.md` still stale | YES |
| Cycle 1 HIGH-4 (Plan 11 aggregate is no-op) | FULLY RESOLVED — `phase0.baseline.full` pinned by Plan 00, Plan 11 reads both ledger entries | NO |
| Cycle 2 NEW HIGH (per-KS code-change A/B is no-op) | NEW | YES |
| Cycle 2 NEW HIGH (`bare_config_dict()` omits top-level gates) | NEW | YES |
| Cycle 2 NEW HIGH (Plan 11 mean-bias not in ledger schema) | NEW | YES |

**Total unresolved HIGHs heading into Cycle 3: 6.**

(Note: NEW HIGH #1 — same-code two-arm A/B — and NEW HIGH #2 — `bare_config_dict()` incompleteness — are different facets of why Cycle-1 HIGH-1 is still open. They are counted separately because they require distinct fixes (flag-gating per-KS code changes vs. completing the bare-config helper). NEW HIGH #3 is wholly distinct and was not flagged in Cycle 1.)

### Cycle-1 → Cycle-2 progress (positive)

- Plan 00 (NEW, Wave 0) is a real piece of execution prerequisite work, not just documentation. Adds the `--arm-b-base` flag, ships unit + integration tests, pins the Phase-0 baseline ledger entry, writes the freeze doc.
- HIGH-4 went from "Plan 11 is a no-op snapshot" to "Plan 11 reads two pinned ledger entries and differs them" — clean fix.
- KS-21 Plan 09 is structurally correct now (raw fetch → parquet build), and the label-rename to `prior_*` is the right honesty move.
- All 4 MEDIUMs and 2 LOWs from Cycle 1 received explicit acknowledgement in CONTEXT D-39..D-43 and the VALIDATION sign-off table — auditable trail of changes.

### Surviving / new gaps

1. The biggest single residual issue is that **the per-KS A/B harness contract (D-29) is still incoherent for code-change plans**. `--arm-b-base bare` solves the config-arm construction question but leaves the code-version question unsolved. Cycle 1 implicitly assumed "the code change is the override" without examining whether the harness can express that; Cycle 2 confirms it cannot (single-process Python, single set of imports per `validate.py` run, no commit-aware caching of the comparison arm's binary state).
2. `01-RESEARCH.md` is the canonical research reference downstream agents (planner + executors) read first. Leaving stale `open_*` / "Tuesday 12pm ET" / "fetch writes parquet" wording in it means Cycle 1 HIGH-2 and HIGH-3 will silently leak back into Plan 09 task execution and Phase 4 expectations unless RESEARCH is reconciled with CONTEXT.
3. Mean-bias is a Phase 1 success criterion (#1: "QB pass_yards mean bias narrowed from ~−28 yd/game to within ±10 yd/game") but is not a ledger column — Plan 11 cannot evaluate the criterion from the artifact it claims to use. This needs either a ledger-schema extension or an alternate evaluation path.

### Divergent Views

Single-reviewer pass; no divergence to record. If a follow-up Gemini/Claude review is run for Cycle 3, divergence between reviewers will surface here.

---

## Recommended Next Action (Cycle 2)

Phase 1 is **not safe to execute** as currently planned. Three new HIGH issues remain and two prior HIGHs are still partially open through `01-RESEARCH.md` staleness.

The next step is `gsd-plan-phase 1 --reviews` to incorporate the Cycle-2 findings into another replan, then `gsd-review --phase 1 --codex` for Cycle 3. Specifically the Cycle-3 replan should:

1. **Resolve the per-KS code-change A/B no-op question** (NEW HIGH #1). Two viable paths:
   - **Path A (preferred for new code paths):** Add a feature flag for each KS code change (e.g., `engine.ks01_preserve_distribution.enabled`, default `false`). All KS changes ship under their flag. `validate.py --set <flag>=true` then drives a real two-arm comparison. Promotion = flip the default to `true` after the A/B passes.
   - **Path B (acceptable for trivial constant changes):** Pre-pin a ledger entry against the pre-commit code state, then run a post-commit ledger entry, and compute the delta from the two entries. Plan 00 already established this pattern for `phase0.baseline.full`; extend it to per-KS pre/post pins.
2. **Fix `bare_config_dict()` completeness** (NEW HIGH #2). Walk every `.enabled` truthiness check in `validation/config.py`, `pff/config.py`, `vegas/config.py`, `usage/config.py`, etc., and ensure every gate (top-level + sub-engine) is enumerated in the helper. Convert Task 4's "loosen the test" escape hatch into a hard gate.
3. **Fix Plan 11 mean-bias evaluation path** (NEW HIGH #3). Either extend `validate.py` to write a mean-bias-by-(position, stat) table to the ledger, or add a Phase 1 closure diagnostic script that derives mean-bias from raw projection rows produced during the aggregate run.
4. **Reconcile `01-RESEARCH.md`** with the post-replan CONTEXT and Plan 09. Targets: lines 14 (User Constraints D-02/D-06), line 206 (RESEARCH parallel-track diagram), line 653 (Code Examples script comments). Replace `open_*` → `prior_*`, "Tuesday 12pm ET" → "API previous_timestamp relative to gameday-noon UTC crawl", and "writes parquet" → "writes raw JSON; build_market_history_player_markets.py writes parquet".
5. **Address MEDIUM #2** (Plan 09 credit logging) — small change to `fetch_market_history_props.py`'s response-header logging.

Once Cycle 3 lands, re-run `gsd-review --phase 1 --codex` to confirm convergence.

---

# Cycle 3 (2026-04-26 — post-replan at commit `e641a06`)

External reviewer: **OpenAI Codex CLI (gpt-5.4)**, invoked with the FULL post-Cycle-3-replan Phase 1 bundle (PROJECT.md, ROADMAP.md, REQUIREMENTS.md, the Cycle 1 + Cycle 2 `01-REVIEWS.md`, the updated `01-CONTEXT.md` / `01-RESEARCH.md` / `01-VALIDATION.md`, and all 12 PLAN.md files). Codex was explicitly given the six unresolved HIGHs from Cycle 2 and asked to verify each against the Cycle-3 replan; reviewer was warned this is the LAST cycle before the workflow's max-cycles escalation gate fires.

## Codex Review (Cycle 3)

> Reviewed at `e641a06`. Five of six carry-over HIGHs are FULLY RESOLVED; one is PARTIALLY RESOLVED via a single stale "Tuesday 12pm ET" reference in `01-RESEARCH.md:98`.

### Summary

Cycle 3 closes the structural plan defects around true-isolation A/B, exhaustive bare-config construction, and ledger-backed mean-bias evaluation. The only carry-over HIGH that is not fully closed is the `01-RESEARCH.md` timing-language cleanup: the doc is mostly reconciled to `prior_*` / `previous_timestamp`, but one live bullet still anchors to `"Tuesday 12pm ET"`, so the documentation is not internally clean enough to count as fully resolved.

### Per-Concern Verification

#### Concern 1: per-KS code-change A/B no-op (D-45 feature-flag pattern) — FULLY RESOLVED

- **Evidence:** [`01-VALIDATION.md`](./01-VALIDATION.md) line 95; [`01-ks01-rz-tdgate-fix-PLAN.md`](./01-ks01-rz-tdgate-fix-PLAN.md) line 16; [`02-ks04-catch-yards-boost-PLAN.md`](./02-ks04-catch-yards-boost-PLAN.md) line 16; [`03-ks03-matchup-coverage-anchor-PLAN.md`](./03-ks03-matchup-coverage-anchor-PLAN.md) line 20; [`04-ks05-props-engine-bugs-PLAN.md`](./04-ks05-props-engine-bugs-PLAN.md) line 19; [`05-ks06-backup-receiver-fallback-PLAN.md`](./05-ks06-backup-receiver-fallback-PLAN.md) line 23; [`06-ks07-positional-rz-catch-rate-PLAN.md`](./06-ks07-positional-rz-catch-rate-PLAN.md) line 19; [`07-ks15-clamping-fix-PLAN.md`](./07-ks15-clamping-fix-PLAN.md) line 19; [`10-ks32-clock-runoff-measure-PLAN.md`](./10-ks32-clock-runoff-measure-PLAN.md) line 16.
- **Reasoning:** The Cycle-3 plans consistently switch from "source-code itself" behavior to explicit feature-gated behavior with default `false` and Arm B enabling the new path via `phase1_ks_flags`. That fixes the same-code/no-op A/B structure at the plan level.

#### Concern 2: `bare_config_dict()` completeness (D-44 helper enumeration + hard-gate test) — FULLY RESOLVED

- **Evidence:** [`00-validation-harness-and-phase0-baseline-PLAN.md`](./00-validation-harness-and-phase0-baseline-PLAN.md) lines 27, 81, 225, 256, 308, 640, 695, 809.
- **Reasoning:** The plan now explicitly enumerates top-level gates, sub-engine gates, and KS flags, and it hardens `test_bare_config_dict_produces_all_None_engines` into the enforcement point. The prior "loosen the test" escape hatch is explicitly removed.

#### Concern 3: Plan 11 mean-bias evaluation (D-46 ledger schema v5) — FULLY RESOLVED

- **Evidence:** [`00-validation-harness-and-phase0-baseline-PLAN.md`](./00-validation-harness-and-phase0-baseline-PLAN.md) lines 29, 83, 966, 1004; [`11-phase1-aggregate-validation-PLAN.md`](./11-phase1-aggregate-validation-PLAN.md) lines 14, 100, 106, 251, 287.
- **Reasoning:** Plan 00 now defines the schema bump and write path; Plan 11 explicitly reads `stat_mean_bias["QB"]["pass_yards"]["arm_b_bias"]` from persisted ledger entries. Success criterion 1 is now evaluable from the planned artifact, not from an external or ad-hoc computation.

#### Concern 4: `01-RESEARCH.md` raw vs parquet pipeline reconciliation — FULLY RESOLVED

- **Evidence:** [`01-RESEARCH.md`](./01-RESEARCH.md) lines 21, 217, 227, 403, 900, 1007.
- **Reasoning:** Active guidance now consistently describes a two-step pipeline: raw JSON fetch first, parquet build second, with acceptance gated on both artifacts. No remaining live instruction says the fetch script writes parquet directly.

#### Concern 5: `01-RESEARCH.md` `prior_*` / `previous_timestamp` reconciliation — PARTIALLY RESOLVED

- **Evidence:** [`01-RESEARCH.md`](./01-RESEARCH.md) lines 15, 19, 209, 411, 509, 962 (all reconciled), but **also line 98 (still stale).**
- **Reasoning:** Most of the document is reconciled correctly: `prior_*` labels are used, and `previous_timestamp` is described honestly as not being a true Tuesday line-release marker. But [`01-RESEARCH.md:98`](./01-RESEARCH.md) still contains a live discretion bullet referencing `"Tuesday 12pm ET"`:

  ```
  - Specific snapshot timestamps within "Tuesday 12pm ET" (timezone, DST).
  ```

  That preserves the stale semantic anchor inside the active guidance ("Claude's Discretion" section). By the strict bar (partial fixes do NOT count as fully resolved), this is PARTIALLY RESOLVED.

#### Concern 6: per-KS plans actually invoke `--set phase1_ks_flags.ksXX_*.enabled=true` — FULLY RESOLVED

- **Evidence:** [`01-ks01-rz-tdgate-fix-PLAN.md`](./01-ks01-rz-tdgate-fix-PLAN.md) lines 20, 354; [`02-ks04-catch-yards-boost-PLAN.md`](./02-ks04-catch-yards-boost-PLAN.md) lines 17, 273; [`03-ks03-matchup-coverage-anchor-PLAN.md`](./03-ks03-matchup-coverage-anchor-PLAN.md) lines 21, 326; [`04-ks05-props-engine-bugs-PLAN.md`](./04-ks05-props-engine-bugs-PLAN.md) lines 20, 320; [`05-ks06-backup-receiver-fallback-PLAN.md`](./05-ks06-backup-receiver-fallback-PLAN.md) lines 24, 285; [`06-ks07-positional-rz-catch-rate-PLAN.md`](./06-ks07-positional-rz-catch-rate-PLAN.md) lines 20, 248; [`07-ks15-clamping-fix-PLAN.md`](./07-ks15-clamping-fix-PLAN.md) lines 20, 423; [`10-ks32-clock-runoff-measure-PLAN.md`](./10-ks32-clock-runoff-measure-PLAN.md) lines 17, 208.
- **Reasoning:** All listed per-KS plans now show explicit Arm B `--set phase1_ks_flags...enabled=true` invocations in the actual command blocks, not just in prose.

### NEW Concerns Introduced by Cycle-3 Replan

None. The Cycle-3 replan did not introduce any new HIGH/MEDIUM/LOW issues that were not present in Cycle 2.

### Carry-Over MEDIUM/LOW Concerns

- **LOW:** [`01-RESEARCH.md:98`](./01-RESEARCH.md) still uses `"Tuesday 12pm ET"` in a live discretion bullet, which keeps Concern 5 from being fully closed. (Same finding as Concern 5; tracked here at LOW because it is documentation polish in a non-canonical bullet, but counted as 1 HIGH against `UNRESOLVED_HIGHS` per the strict-bar rule.)

### Strengths

- The plan bundle now has a coherent D-44 / D-45 / D-46 story across `01-VALIDATION.md`, Plan 00, Plan 11, and the per-KS plans.
- The bare-isolation contract is materially stronger because it now accounts for top-level gates, not just sub-engine toggles.
- The per-KS feature-flag pattern is applied consistently across all affected plans, including the conditional KS-32 retune branch.
- Plan 11 now has a real persisted data path for mean-bias evaluation instead of a narrative-only success criterion.

### Risk Assessment

**Overall risk level:** MEDIUM

The execution-critical plan defects are fixed, but one of the six carry-over HIGHs is still only partially resolved because the research doc retains stale timing language in active guidance. That is a documentation-consistency problem, not a harness-design problem, but by the stated strict bar it still blocks a clean convergence closeout.

### Recommendation

**NEEDS-CYCLE-4** (with the caveat that Cycle 4 is BLOCKED by the workflow's max-cycles gate — see Consensus Summary below for the escalation discussion).

Specific deltas needed:

1. Remove or rewrite [`01-RESEARCH.md:98`](./01-RESEARCH.md) so it no longer references `"Tuesday 12pm ET"` as a live semantic anchor. Replace with `"prior-snapshot timing within the API previous_timestamp window (timezone, DST)"` or remove the bullet entirely if Claude's discretion no longer applies.
2. Re-run the Cycle-3 sign-off after that doc cleanup so Concern 5 can be marked FULLY RESOLVED instead of PARTIALLY RESOLVED.

---

## Consensus Summary (Cycle 3)

Single external reviewer (Codex / gpt-5.4) again, so "consensus" is the synthesis of that single pass into actionable severity buckets.

### Net Cycle-3 disposition (HIGH only)

| Concern source | Disposition | Counts toward CYCLE_SUMMARY? |
|----------------|-------------|------------------------------|
| Cycle-2 NEW HIGH #1 (per-KS code-change A/B no-op) | FULLY RESOLVED — D-45 feature-flag pattern wired through Plan 00 Task 8 + 8 per-KS plans | NO |
| Cycle-2 NEW HIGH #2 (`bare_config_dict()` incomplete) | FULLY RESOLVED — D-44 enumerates all gates; Plan 00 Task 4 hard-gate test; escape hatch removed | NO |
| Cycle-2 NEW HIGH #3 (Plan 11 mean-bias not in ledger) | FULLY RESOLVED — D-46 schema v5 + `SeasonMetrics.stat_mean_bias` + Plan 11 reads it directly | NO |
| Cycle-1 HIGH-2 partial (RESEARCH.md raw vs parquet) | FULLY RESOLVED — two-step pipeline now consistent across active guidance | NO |
| Cycle-1 HIGH-3 partial (RESEARCH.md `open_*` / Tuesday 12pm ET) | PARTIALLY RESOLVED — most occurrences fixed, but [`01-RESEARCH.md:98`](./01-RESEARCH.md) "Claude's Discretion" bullet still references `"Tuesday 12pm ET"` | YES |
| Cycle-2 NEW HIGH #1 (sub-facet: per-KS plans actually use `--set`) | FULLY RESOLVED — every per-KS plan has the `--set phase1_ks_flags` command in its A/B block | NO |

**Total unresolved HIGHs heading into Cycle 4 / escalation: 1.**

### Cycle-2 → Cycle-3 progress (positive)

- All three NEW HIGHs from Cycle 2 are now FULLY RESOLVED (D-44, D-45, D-46 all landed coherently).
- Both partial-resolves of Cycle-1 HIGH-2 / HIGH-3 are now MOSTLY closed, with only one stale wording leak in `01-RESEARCH.md:98`.
- HIGH count went 4 (Cycle 1) → 6 (Cycle 2) → **1 (Cycle 3)**. Convergence is no longer stalled — it has resumed.

### Surviving / new gaps

The single remaining HIGH is a documentation-consistency issue, not a structural plan defect. The fix is mechanical (one-line edit to `01-RESEARCH.md:98`) and does not require a full replan cycle — it can be addressed via a small targeted edit and re-review.

### Divergent Views

Single-reviewer pass; no divergence to record.

---

## Recommended Next Action (Cycle 3)

Phase 1 is **NEAR safe to execute** — only one mechanical doc-edit blocks full convergence. Two viable paths from here:

1. **Path A (mechanical fix + targeted re-review):** Apply the one-line `01-RESEARCH.md:98` cleanup, commit, re-run `gsd-review --phase 1 --codex` for Cycle 4 (if the workflow allows a fourth cycle for a pure documentation correction), then Phase 1 is SAFE-TO-EXECUTE.
2. **Path B (escalate with conditional approval):** Escalate to the user with the explicit recommendation that Phase 1 is structurally safe to execute as-is, conditional on a one-line `01-RESEARCH.md:98` documentation cleanup before any executor reads that file. The cleanup is mechanical and does not affect any plan body or harness contract.

Per the workflow's max-cycles escalation gate: this is the third cycle, and the convergence loop has clearly resumed (HIGH count: 4 → 6 → 1). The user can decide whether the single remaining HIGH (a documentation-polish issue, not a plan-defect issue) warrants a fourth cycle or constitutes acceptable escalation criteria for SAFE-TO-EXECUTE.

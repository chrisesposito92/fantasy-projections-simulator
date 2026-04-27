---
phase: 2
reviewers: [codex]
reviewed_at: 2026-04-27T01:19:59Z
codex_model: gpt-5.4
plans_reviewed:
  - 01-phase2-scaffolding-and-entry-baseline-PLAN.md
  - 02-ks08-dynamic-blend-simulator-floor-PLAN.md
  - 03-ks09-per-stat-residual-calibration-PLAN.md
  - 04-ks14-thin-bucket-shrinkage-PLAN.md
  - 05-ks10-per-position-caps-te-elite-tier-PLAN.md
  - 06-ks11-tier-engine-position-reliability-PLAN.md
  - 07-ks13-ff-opportunity-prior-width-PLAN.md
  - 08-ks12-share-normalization-residual-PLAN.md
  - 09-phase2-aggregate-validation-PLAN.md
context_files:
  - 02-CONTEXT.md
  - 02-RESEARCH.md
  - 02-VALIDATION.md
  - .planning/PROJECT.md
  - .planning/ROADMAP.md
  - .planning/REQUIREMENTS.md
---

# Cross-AI Plan Review — Phase 2

## Codex Review

**Summary**

The Phase 2 plan set is thoughtfully decomposed, strongly evidence-driven, and mostly well ordered: it puts the main architectural lever first (`KS-08` then `KS-09`), defers the highest blast-radius normalization change (`KS-12`) to the end, and preserves a hard-floor A/B discipline throughout. The main problem is that a few core plans are internally inconsistent at exactly the places that matter most for success attribution: `KS-09` may not actually move the stat surfaces that `validate.py` scores, `KS-14` is not truly flag-gated as written, and Plan 09's rollback logic assumes additive effects across changes that are explicitly coupled. Those issues make the overall phase materially riskier than the planning prose suggests.

**Strengths**

- The phase has a clear thesis: fix structural compression first, then layer smaller calibration refinements around it.
- Hard-floor enforcement is explicit and repeated per change, not deferred to the end.
- The dependency ordering is mostly sensible: `KS-08` before `KS-09`, low-risk items before `KS-12`, and aggregate roll-up last.
- The plans reuse Phase 1 patterns well: flagging, bare-vs-full A/B, ledger labels, promotion notes, and end-of-phase roll-up.
- `KS-09` has a real rollback story via the two-stage layered design, which is pragmatic even if architecturally imperfect.
- The plans are unusually explicit about artifacts, schema bumps, and the need to re-fit training outputs alongside runtime changes.
- The risks are not hidden; several plans correctly call out their own danger zones.

**Concerns**

- `[HIGH] [Plan 03 Task 2, Plan 09]` `KS-09` may not actually satisfy the phase success criteria because it writes `corrected_<stat>` columns but does not clearly route those corrected values into the canonical stat fields that `scripts/validate.py` and the aggregate ledger evaluate. As written, this can devolve into "new columns exist" while `stat_ks` and `stat_mean_bias` still reflect the raw columns. That would make the main architectural plan observability-only instead of outcome-producing.
- `[HIGH] [Plan 04 Task 1]` `KS-14` is not truly feature-flagged in the implementation sketch. The plan says flag-off behavior should be byte-identical to legacy fallback, but the proposed code lowers `MIN_BUCKET_PLAYS` globally to `5` and still retains 5-9 play buckets even when the flag is off. That breaks isolation, contaminates attribution, and invalidates the claim that `phase2_ks_flags.ks14_thin_bucket_shrinkage.enabled=false` preserves pre-Phase-04 behavior.
- `[HIGH] [Plan 09]` The walk-back strategy is too naive for this phase. Reverting the "smallest-gain promoted candidate first" based on isolated per-KS deltas is unsafe when the biggest levers are coupled: `KS-08` and `KS-13` both change post-sim variance, `KS-09` depends on the post-`KS-08` stack, and `KS-10` re-fits artifacts on top of `KS-09`. Aggregate regressions here are not additive.
- `[MEDIUM] [Plan 07]` `KS-13` is under-specified where it matters operationally. Path B introduces a new fitted-std artifact concept, but the artifact path/schema, fitting workflow, and runtime loader contract are not fully nailed down. Several tests are placeholders rather than executable assertions, so the plan is not actually TDD-complete.
- `[MEDIUM] [Plan 07, Plan 03]` Stochastic sampling is introduced without a fully explicit reproducibility contract. The plans mention RNG seeding, but they do not clearly define how `validate.py` will guarantee deterministic comparisons once `ff_opportunity` starts sampling around priors.
- `[MEDIUM] [Plan 06]` `KS-11` claims Phase-2-style flag gating, but the runtime behavior appears to depend on whether `pff.tier_engine.position_reliability` is populated, not on the `ks11` flag itself. That weakens rollback/isolation discipline compared with the rest of the phase.
- `[MEDIUM] [Plan 05]` `KS-10` gating is ambiguous because Plan 01 already introduces a populated `max_abs_adjustment_by_position` placeholder. If the fitter/runtime keys off dict presence rather than the `ks10` flag, TE-specific behavior can leak on early. Also, the validation target should require a real `TE|elite|*` bucket, not merely "some TE bucket exists."
- `[MEDIUM] [Plan 08]` `KS-12` has the right risk framing but a weak success measurement. The plan talks about "WR target_share variance retention," yet no concrete ledger metric is added for that, and both integration tests are placeholders. That leaves acceptance overly dependent on indirect stat-KS movement.
- `[LOW] [Plan 02]` `KS-08` sweep selection is slightly misaligned with the phase-level success criteria. It optimizes for TE/WR `fpts` KS improvement, but Phase 2 ultimately cares about aggregate `fpts` KS plus specific stat-level targets. That can pick a floor that looks locally helpful but is not globally best.
- `[LOW] [Plan 01]` The `bare_config_dict()` treatment of non-boolean Phase 2 knobs is conceptually muddy. The plan mostly gets away with this because behavior is supposed to sit behind booleans, but `KS-11` and `KS-14` show that assumption is fragile.

**Suggestions**

- Make `KS-09` choose one canonical output contract up front: either overwrite the canonical stat fields after correction, or explicitly teach validation/export/projection consumers to prefer `corrected_<stat>` fields. Do not leave this implicit.
- Fix `KS-14` gating before execution. The threshold drop to `5` must only be active when the KS-14 flag is on, or there must be a second gate separating "threshold lowering" from "shrinkage."
- Replace Plan 09's rollback rule with reverse ablation from the final promoted stack. At minimum, treat `{KS-08, KS-13}` as a coupled cluster and evaluate rollback candidates against actual aggregate deltas, not isolated per-plan wins.
- Finish Plan 07 and Plan 08 tests with concrete assertions before execution. Placeholder tests are not enough for the two most behaviorally ambiguous plans outside `KS-09`.
- Make `KS-11` gating real in the loader: when the flag is off, pass `{}` for `position_reliability` even if defaults are populated.
- Tighten `KS-10` acceptance so it explicitly checks for a non-empty `TE|elite|*` bucket in the re-fit artifact, or else documents the fallback if 2024 data cannot populate it.
- Add an interaction checkpoint after `KS-08 + KS-09 + KS-13` are all in place, before waiting for Plan 09, because those three are the core compression/variance cluster driving TGT-08 and TGT-09.

**Risk Assessment**

**HIGH.** The phase is well reasoned, but the central success path still has unresolved architectural gaps. If `KS-09` does not feed the stats that validation actually scores, the phase misses its main objective. If `KS-14` is not truly gated, per-KS attribution becomes unreliable. If Plan 09 uses additive rollback logic on non-additive changes, final promotion decisions can be wrong even with good ledger hygiene. Tighten those three areas and the plan set drops to medium risk; without them, I would not trust the phase to cleanly prove success.

---

## Consensus Summary

Only one external reviewer (Codex / gpt-5.4) was invoked for this review per `--codex` flag, so "consensus" here reduces to that single reviewer's findings. Where multiple reviewers are added in a future cycle, this section will synthesize agreement / divergence across them.

### Agreed Strengths

- Architectural ordering puts the largest levers first (`KS-08` simulator-weight floor → `KS-09` per-stat residual_calibration) and the highest blast-radius normalization change (`KS-12`) last.
- Hard-floor enforcement (rank_corr Δ ≥ -0.005, MAE Δ ≤ +0.05) is repeated per change rather than deferred to the aggregate, mirroring the Phase 1 D-30/D-31 discipline.
- Phase 1 patterns (per-KS flag gating, bare-vs-full A/B, ledger labels, promotion-state commits, end-of-phase aggregate roll-up) are reused consistently.
- `KS-09`'s two-stage layered design (corrected stat columns alongside the existing fpts correction) gives a real rollback path, and artifact/schema bumps are explicit.

### Agreed Concerns (ranked by severity)

**HIGH** — three load-bearing architectural gaps that, if uncorrected, would let Phase 2 ship without proving its main objective:

1. **`KS-09` output contract ambiguity (Plan 03 + Plan 09).** Per-stat corrections write to *new* `corrected_<stat>` columns, but `validate.py` / `SeasonMetrics.stat_ks` / `SeasonMetrics.stat_mean_bias` continue to read the raw stat columns. Without an explicit downstream contract (overwrite the canonical fields, OR teach the validation harness to prefer `corrected_<stat>`), KS-09 risks becoming observability-only — visible in projection rows but invisible in the ledger metric we promote against.
2. **`KS-14` flag gate is leaky (Plan 04).** The Plan 04 sketch lowers `MIN_BUCKET_PLAYS` to 5 globally rather than gating the threshold change behind `phase2_ks_flags.ks14_thin_bucket_shrinkage.enabled`. As written, flag-off does NOT match pre-Plan-04 behavior, breaking the per-KS A/B isolation contract.
3. **Plan 09 walk-back logic assumes additivity that does not hold.** Reverting the "smallest-gain isolated KS" first is unsafe because `{KS-08, KS-13}` are a coupled variance cluster, `KS-09` is computed against the post-`KS-08` stack, and `KS-10` re-fits artifacts on top of `KS-09`. Rollback must be reverse-ablation against the final promoted stack, not by isolated per-KS Δs.

**MEDIUM** — five tightening items:

4. **`KS-13` (Plan 07) is operationally under-specified.** Path B introduces a fitted-std artifact concept without locking the artifact path/schema/loader contract; several tests are placeholders.
5. **Stochastic sampling reproducibility (Plan 07, Plan 03).** RNG seeding is mentioned but the determinism contract for `validate.py` once `ff_opportunity` and per-stat residuals begin sampling is not nailed down.
6. **`KS-11` (Plan 06) flag gate may be implicit.** Runtime behavior appears to key off the *populated* `pff.tier_engine.position_reliability` dict rather than the `ks11_*.enabled` flag.
7. **`KS-10` (Plan 05) gating ambiguity.** Plan 01 lands a populated `max_abs_adjustment_by_position` placeholder; if Plan 05's runtime/fitter keys off dict presence rather than the `ks10_*.enabled` flag, behavior can leak. Validation should also explicitly assert a populated `TE|elite|*` bucket in the re-fit artifact.
8. **`KS-12` (Plan 08) success measurement is weak.** "WR target_share variance retention" has no concrete ledger metric; integration tests are placeholders.

**LOW**:

9. `KS-08` sweep (Plan 02) optimizes a local objective (TE/WR fpts KS) that may not align with the phase-level aggregate fpts KS + per-stat-target objective.
10. `bare_config_dict()` (Plan 01) is conceptually clean for boolean flags but fragile for non-boolean knobs (`KS-11` and `KS-14` both expose this).

### Divergent Views

N/A — single reviewer.

### Recommended Pre-Execution Actions

Before executing Plan 02 onward, address the three HIGH items:

1. Lock the `KS-09` output contract: choose between (a) overwriting canonical stat columns post-correction, or (b) updating `validate.py` / ledger writers to prefer `corrected_<stat>`. Update Plan 03 + Plan 09 with the chosen contract and add a test that asserts the chosen field is what flows into `SeasonMetrics.stat_ks` / `stat_mean_bias`.
2. Re-spec `KS-14`'s flag gate: the `MIN_BUCKET_PLAYS` change must be gated behind `phase2_ks_flags.ks14_thin_bucket_shrinkage.enabled`. Update Plan 04 Task 1 (and add a flag-off-equals-baseline test).
3. Replace Plan 09's walk-back rule with reverse-ablation against the final stack, treating `{KS-08, KS-13}` as a coupled cluster and ordering rollback by *aggregate* Δ contribution rather than isolated per-KS Δ.

Medium items (KS-11 flag gate, KS-10 fitter gating, KS-13 artifact spec, KS-12 ledger metric, RNG determinism) should be resolved during their respective plan executions but do not necessarily block phase entry.

---

*Generated by `/gsd-review --phase 2 --codex` on 2026-04-27. To incorporate feedback into planning:*

```
/gsd-plan-phase 2 --reviews
```

---

## Cycle 2 — Codex Review (post-revision)

**Reviewed at:** 2026-04-27T01:52:07Z
**Reviewer:** Codex (gpt-5.4)
**Cycle:** 2 (post-revision after commit `ee58ff4` on `gsd/phase-2`)
**Plans reviewed:** all 9 Phase 2 PLAN.md files (revised set)
**Cycle 1 HIGH concerns asked about:**
1. KS-09 output contract ambiguity (Plan 03 + Plan 09)
2. KS-14 flag gate is leaky (Plan 04 Task 1)
3. Plan 09 walk-back logic assumes additivity that does not hold

**Summary**

The Cycle 1 revisions materially improved the Phase 2 plan set. HIGH 1 and HIGH 2 are now closed in the plan text, and the revised Plan 09 is directionally much better than the original additivity-based walk-back. But I would not sign off on Phase 2 execution yet. HIGH 3 is only partially resolved because Plan 09 still contains conflicting rollback instructions, and the revised set now has two new load-bearing execution blockers: Plan 07's probe/Path-B branch does not match the current ensemble code surface, and Plan 09's aggregate delta logic is written against a ledger interface that does not exist.

**Cycle 1 HIGH Resolution Status**

- **HIGH 1 (KS-09 output contract): FULLY RESOLVED** — Plan 03 (must_haves line 23) now explicitly says `scripts/validate.py::_compute_distribution_ks` must prefer `corrected_<stat>` when the KS-09 flag is on, and Task 3 adds concrete routing tests for flag-on and flag-off behavior (`test_ks09_validate_routes_corrected_stat_when_flag_on` / `..._raw_stat_when_flag_off`).
- **HIGH 2 (KS-14 flag gate): FULLY RESOLVED** — Plan 04 (must_haves line 17) now keeps `MIN_BUCKET_PLAYS = 10` as the legacy constant, introduces `_effective_min_bucket_plays()`, routes both `compute_play_outcomes` and `compute_play_calling` through it, and adds the required `test_ks14_legacy_min_bucket_plays_when_flag_off`.
- **HIGH 3 (Plan 09 walk-back additivity): PARTIALLY RESOLVED** — Plan 09 (must_haves line 18) now replaces isolated per-KS rollback with leave-one-out reverse ablation, which is the right conceptual fix. But it is not fully closed because the same file still says in the objective to "revert the smallest-gain promotion candidate first" (Plan 09 line 49), and the coupled-cluster trigger is inconsistent between the prose (`negative marginal_delta_rank_corr`) and the synthetic test case (`+0.001` near-zero positives in `test_reverse_ablation_coupled_cluster_pair_revert` Plan 09 line 218).

**Cycle 1 MEDIUM/LOW Resolution Status (briefly)**

- **KS-13 artifact spec:** PARTIALLY RESOLVED — the revised must-haves define a real Path B artifact contract, but the task body still never creates `scripts/fit_ff_opportunity_prior_width.py` or a concrete artifact loader path.
- **RNG determinism:** UNRESOLVED — the must-have promises per-row seeded deterministic sampling, but Plan 07 Task 2 (line ~302) still sketches a shared `self._rng.normal(...)` path and leaves determinism tests as `pass`.
- **KS-11 flag gate:** RESOLVED — Plan 06 Task 1b correctly gates `position_reliability` on `ks11_position_reliability.enabled` and adds flag-off / flag-on tests.
- **KS-10 fitter gating + `TE|elite|*` bucket assertion:** PARTIALLY RESOLVED — runtime gating is explicit, but the promised non-empty `TE|elite|*` assertion is not actually enforced; Plan 05 Task 2 only checks for any `TE|` bucket.
- **KS-12 success metric + concrete tests:** PARTIALLY RESOLVED — the success metric is now correctly tied to `Δ stat_ks[WR][receptions]`, but the two "concrete" integration tests in Plan 08 Task 1 (line ~240) are still literal `pass` placeholders.
- **KS-08 sweep alignment:** RESOLVED — Plan 02 (line ~722) now aligns sweep choice, defaults flip, and bundled artifact refit around the same chosen floor.
- **`bare_config_dict` non-boolean knob safety:** RESOLVED — Plan 01 (line ~330) now explicitly distinguishes scalar/dict knobs from boolean gates and keeps bare isolation on the parent `enabled` paths.

**New HIGH Concerns Introduced by the Revisions**

- **[HIGH] Plan 07 Task 1, `scripts/probe_ff_opportunity_quantiles.py`** — the revised probe script imports `EnsembleLoader` and calls `load_week_raw(...)` (Plan 07 Task 1 line ~169), but the current code surface only exposes `FfOpportunityLoader.load_weekly(...)` in `src/fantasy_sim/data/ensemble/loader.py` (line 24). As written, the probe cannot run, so the Path A / Path B decision is blocked.
- **[HIGH] Plan 07 Task 2, Path B branch** — the revised plan promises a concrete Path B artifact pipeline in the must-haves, but Task 2 (line ~258) never creates `scripts/fit_ff_opportunity_prior_width.py`, never defines the artifact loader, and still leaves several KS-13 tests as `pass`. If the probe selects Path B, the plan dead-ends.
- **[HIGH] Plan 09 Task 1/Task 2, aggregate delta + walk-back implementation** — the revised delta test and reverse-ablation scripts are written against a nonexistent ledger interface (`p1.arm_b.rank_corr`, `p2.arm_b.weekly_mae`, etc. in Task 1 line ~161 and Task 2 line ~289), but `src/fantasy_sim/validation/ledger.py` (line 70) stores per-season data under `season_results[*].arm_a_* / arm_b_*`, not a single `arm_b` object. On top of that, Task 1 hard-asserts the hard floor before Task 2's walk-back loop, so a real regression would fail the suite before reverse ablation could even run.

**New MEDIUM/LOW Concerns Worth Flagging**

- **[MEDIUM] Plan 09 objective text still contains stale pre-revision guidance** — line 49 still says "revert the smallest-gain promotion candidate first," which conflicts with the reverse-ablation protocol above it.
- **[MEDIUM] Plan 09 coupled-cluster trigger is internally inconsistent** — the prose says pair-revert when both KS-08 and KS-13 have negative marginal rank deltas, but the synthetic test models near-zero positive deltas instead; the executor does not have one unambiguous trigger rule.
- **[MEDIUM] Plan 08 still over-claims test concreteness** — the must-have says the integration tests "ARE concrete," but the task body still leaves them stubbed.

**Strengths of the Cycle 2 Plan Set**

- Plan 03 now closes the original KS-09 observability gap cleanly by wiring the corrected stat columns all the way into the canonical ledger metric.
- Plan 04 fixes the KS-14 leak the right way: the threshold, the shrinkage branch, and both consumer call sites are now tied to the same flag.
- Plan 01's hard-gate treatment of Phase 2 flags and sub-engine booleans makes the bare/full A/B contract much more credible than the original draft.
- Plan 06's loader-gate fix is a real improvement: it turns the KS-11 flag into an actual runtime gate instead of a comment-only contract.
- Plan 09's move away from isolated per-KS rollback toward marginal contribution testing is the correct conceptual direction.

**Risk Assessment**

**HIGH** — I would not sign off on Phase 2 execution yet. The revised set is much stronger on the original Cycle 1 issues, but it is still not execution-safe as a whole: Plan 07 has a broken probe surface and an incomplete Path B branch, and Plan 09's aggregate/walk-back implementation is written against the wrong ledger interface and still contains conflicting rollback rules. If those two plans are revised, and the remaining placeholder integration tests are replaced with concrete assertions, the set should be close to ready. As it stands, further revisions are needed before kickoff.

---

## Cycle 2 — Consensus Summary

Single-reviewer cycle (`--codex` only).

### Cycle-1 → Cycle-2 HIGH Resolution Audit

| # | Concern | Cycle-1 Finding | Cycle-2 Status | Counted as Unresolved? |
|---|---------|-----------------|----------------|-------------------------|
| 1 | KS-09 output contract ambiguity | HIGH | FULLY RESOLVED | No |
| 2 | KS-14 flag gate leaky | HIGH | FULLY RESOLVED | No |
| 3 | Plan 09 walk-back additivity | HIGH | PARTIALLY RESOLVED | Yes (1) |

### NEW HIGHs introduced in Cycle 2

| # | Concern | Plan / Site | Counted as Unresolved? |
|---|---------|-------------|-------------------------|
| 4 | Plan 07 probe script imports nonexistent `EnsembleLoader.load_week_raw(...)` (current code surface = `FfOpportunityLoader.load_weekly(...)`) | Plan 07 Task 1 | Yes (2) |
| 5 | Plan 07 Path B never creates `scripts/fit_ff_opportunity_prior_width.py` or the artifact loader; KS-13 dead-ends if probe → Path B | Plan 07 Task 2 | Yes (3) |
| 6 | Plan 09 aggregate delta + reverse-ablation are written against a nonexistent `p1.arm_b.rank_corr` / `p2.arm_b.weekly_mae` ledger object (real schema is `season_results[*].arm_a_* / arm_b_*`); Task 1 also hard-asserts hard floor before Task 2's walk-back loop runs | Plan 09 Task 1 + Task 2 | Yes (4) |

### Total unresolved HIGHs (Cycle 2): **4**

(1 partially-resolved Cycle-1 carryover + 3 newly raised in Cycle 2.)

### Recommended Pre-Execution Actions for Cycle 3

Before executing Plan 02 onward, address the 4 unresolved HIGHs:

1. **Plan 09 walk-back consistency** — delete the stale "revert smallest-gain promotion candidate first" sentence at line 49; align the coupled-cluster trigger prose with the synthetic test (pick ONE trigger sign convention — recommend `marginal_delta_rank_corr ≤ 0` so near-zero values qualify, then update the test accordingly).
2. **Plan 07 probe script surface** — rewrite `scripts/probe_ff_opportunity_quantiles.py` against the real `FfOpportunityLoader.load_weekly(...)` API (verify in `src/fantasy_sim/data/ensemble/loader.py` first), or extend the loader to expose `load_week_raw(...)` if the raw schema is needed.
3. **Plan 07 Path B artifact pipeline** — add a new task to Plan 07 that creates `scripts/fit_ff_opportunity_prior_width.py` mirroring `scripts/fit_residual_calibration.py`, defines `_load_ff_opportunity_prior_width_artifact(season)` in `EnsembleLayer`, and replaces `pass` test stubs with concrete assertions. Without this, Path B is unimplementable.
4. **Plan 09 ledger interface** — rewrite Task 1 / Task 2 ledger reads against the actual `LedgerEntry.season_results[season].arm_a_<metric>` / `arm_b_<metric>` schema (verify in `src/fantasy_sim/validation/ledger.py`). Move the hard-floor assertion AFTER the walk-back loop (or split into a "pre-walkback" advisory log + a "post-walkback" assert) so a regressing aggregate triggers the protocol instead of failing the test suite.

The 3 carry-forward MEDIUMs (Plan 07 RNG determinism, Plan 05 `TE|elite|*` assertion, Plan 08 stub integration tests) and the 3 new MEDIUMs (Plan 09 stale prose, Plan 09 coupled-cluster trigger sign, Plan 08 over-claim) should be folded into the Cycle 3 revision pass but do not necessarily block phase entry on their own.

---

*Generated by `/gsd-review --phase 2 --codex` on 2026-04-27 (cycle 2). To incorporate feedback into planning:*

```
/gsd-plan-phase 2 --reviews
```

---

## Cycle 3 — Codex Review (post-cycle-2 revision, FINAL CYCLE)

**Reviewed at:** 2026-04-27T05:24:00Z
**Reviewer:** Codex (gpt-5.4)
**Cycle:** 3 (FINAL — post-cycle-2 revision review at commit `5cc58d8` on `gsd/phase-2`)
**Plans reviewed:** all 9 Phase 2 PLAN.md files (revised set after cycle-2 fixes)
**Cycle 2 HIGH concerns asked about (4 unresolved):**
1. HIGH 1 (cycle-2 carry-forward, originally cycle-1 HIGH 3) — Plan 09 walk-back consistency (stale "smallest-gain" sentence + coupled-cluster trigger sign convention)
2. HIGH 2 (cycle-2 NEW) — Plan 07 probe imports (verified `FfOpportunityLoader.load_weekly` API)
3. HIGH 3 (cycle-2 NEW) — Plan 07 Path B artifact pipeline (Task 2.5: fitter script, loader, concrete tests)
4. HIGH 4 (cycle-2 NEW) — Plan 09 ledger-schema reads + Task 1 hard-floor split (`season_results`/`arm_b_*` correctness + walkback marker)

### Summary

Cycle 3 materially improved the Phase 2 plan: the Plan 07 probe now targets the real FF Opportunity loader surface, and Plan 09's detailed Task 1/2 blocks now read the real ledger schema and split the hard-floor assert behind a post-walkback marker. I still would not sign off on execution yet, because one cycle-2 HIGH is only partially cleaned up and Plan 07 now contains a new load-bearing contradiction in the main KS-13 implementation step. Biggest residual risk: the KS-13 plan can still drive the executor into broken code paths while claiming its tests are concrete.

### Cycle-2 HIGH Resolution Status

1. **HIGH 1 — Plan 09 walk-back consistency**
Status: **FULLY RESOLVED**
Plan 09 now makes reverse ablation the authoritative walk-back protocol in the actual execution plan text, not just in commentary (`09-phase2-aggregate-validation-PLAN.md` around lines 17-19, 50, 521-605). The coupled-cluster rule is also internally aligned now: prose uses `marginal_delta_rank_corr ≤ ε` with `ε = 0.005`, and the synthetic pair-revert test is described against the `+0.001` near-zero-positive case in the same file (around lines 19, 343-363, 603). The stale "smallest-gain" sentence appears removed from Plan 09 itself; the only remaining stale mention is in `02-VALIDATION.md`, which is supporting documentation, not the plan body.

2. **HIGH 2 — Plan 07 probe imports**
Status: **FULLY RESOLVED**
Plan 07 now explicitly anchors the probe to the verified loader/API surface: `FfOpportunityLoader(config: FfOpportunityConfig | None = None)` with `load_weekly(seasons: list[int]) -> pl.DataFrame` (`07-ks13-ff-opportunity-prior-width-PLAN.md` around lines 23-24, 196-225, 334-335). That matches the live code exactly in `src/fantasy_sim/data/ensemble/loader.py:24` and `src/fantasy_sim/data/ensemble/loader.py:43`, and the plan now explicitly rejects the fictional `EnsembleLoader` / `load_week_raw` surface.

3. **HIGH 3 — Plan 07 Path B artifact pipeline**
Status: **FULLY RESOLVED**
The specific cycle-2 gap is now present in the plan: Task 2.5 adds a fitter script, a bundled artifact location, a runtime loader `_load_ff_opportunity_prior_width_artifact`, a `_fitted_std_for(...)` helper, and concrete acceptance criteria for all of them (`07-ks13-ff-opportunity-prior-width-PLAN.md` around lines 27-29, 534-968). The concrete replacement tests are also spelled out, including the new `tests/test_scripts/test_fit_ff_opportunity_prior_width.py` coverage and the non-placeholder Path B assertions (around lines 789-968). That fully resolves the original "Path B pipeline never actually exists" finding.

4. **HIGH 4 — Plan 09 ledger-schema reads + Task 1 hard-floor split**
Status: **PARTIALLY RESOLVED**
The detailed implementation blocks are now corrected: the plan explicitly switches to `LedgerEntry.season_results` helpers and introduces the `p2_walkback_complete.marker` split so the hard-floor test asserts only after the walk-back loop (`09-phase2-aggregate-validation-PLAN.md` around lines 20-21, 144-227, 427-505, 619-635). But the same file still carries stale contradictory schema/protocol text: the reverse-ablation formula in the top truth block still uses nonexistent `p2.aggregate.full.arm_b.<metric>` notation (around line 18), and the "Verified code" interface excerpt still shows the old flat `SeasonMetrics` shape with `rank_corr` / `weekly_mae` fields instead of `arm_b_rank_corr` / `arm_b_weekly_mae` (around lines 81-90). What's still missing is a full cleanup of those stale snippets so the entire plan file, not just its helper sections, consistently matches the real ledger surface.

### New HIGH Concerns (introduced by cycle-2 revisions)

- **[HIGH] [Plan 07, Task 2 blend block + test block]** The main KS-13 implementation step still tells the executor to use nonexistent top-level config paths: `self.config.prior_width.enabled` / `self.config.prior_width.path` in `FfOpportunityProjectionEnsembler.blend_week` (`07-ks13-ff-opportunity-prior-width-PLAN.md` around lines 395-400), but the verified live config surface is nested under `self.config.ff_opportunity` and `EnsembleConfig` has no top-level `prior_width` (`src/fantasy_sim/data/ensemble/models.py:63`). The same task still leaves `test_ks13_path_a_uses_quantile_width_when_lo_hi_present` and `test_ks13_unchanged_when_flag_disabled` as `pass` placeholders (around lines 428-450), despite the plan header claiming all six KS-13 tests are concrete (around line 55). That is a real execution blocker for the Path A and flag-off branches.

### Carry-Forward MEDIUM Status (brief)

- Plan 07 RNG determinism contract: mostly strengthened; must-have text and the concrete seed test exist (`07-ks13-ff-opportunity-prior-width-PLAN.md` around line 32 and lines 835-861), but its practical value is gated by the new Task 2 KS-13 contradiction above.
- Plan 05 `TE|elite|*` bucket assertion: addressed; both the must-have and end-of-plan verification explicitly require a non-empty `TE|elite|*` bucket or downgrade to `SHIPPED-PARTIAL` (`05-ks10-per-position-caps-te-elite-tier-PLAN.md` around lines 21-22 and 583-587).
- Plan 08 stub integration tests at lines 242/247: still unresolved; both integration tests remain `pass` placeholders despite the top-of-plan claim that they are concrete (`08-ks12-share-normalization-residual-PLAN.md` around lines 21-22, 240-247).
- Plan 09 stale "smallest-gain" in `02-VALIDATION.md`: still stale at `02-VALIDATION.md:107`, but the executable Plan 09 now supersedes it with reverse ablation.

### Risk Assessment

**Final risk level**: HIGH

Cycle 3 clearly converged on the right architecture for two of the biggest cycle-2 failures, but it did not finish cleanup: one original HIGH remains partially resolved, and Plan 07 now has a new load-bearing contradiction in the main implementation snippet plus vacuous tests in the same task. I would not sign off on Phase 2 execution now. One more cleanup pass is needed to make Plan 07 internally consistent and to remove the stale ledger/schema snippets from Plan 09.

### Total Unresolved HIGHs Count

`TOTAL_UNRESOLVED_HIGHS: 2`

---

## Cycle 3 — Consensus Summary

Single-reviewer cycle (`--codex` only).

### Cycle-2 → Cycle-3 HIGH Resolution Audit

| # | Concern | Cycle-2 Finding | Cycle-3 Status | Counted as Unresolved? |
|---|---------|-----------------|----------------|-------------------------|
| 1 | Plan 09 walk-back consistency (stale sentence + trigger sign) | PARTIALLY RESOLVED (carry-forward of cycle-1 HIGH 3) | FULLY RESOLVED | No |
| 2 | Plan 07 probe imports (`FfOpportunityLoader.load_weekly` API) | NEW HIGH | FULLY RESOLVED | No |
| 3 | Plan 07 Path B artifact pipeline (Task 2.5) | NEW HIGH | FULLY RESOLVED | No |
| 4 | Plan 09 ledger-schema reads + Task 1 hard-floor split | NEW HIGH | PARTIALLY RESOLVED | Yes (1) |

### NEW HIGHs introduced in Cycle 3

| # | Concern | Plan / Site | Counted as Unresolved? |
|---|---------|-------------|-------------------------|
| 5 | Plan 07 Task 2 KS-13 implementation references nonexistent top-level `self.config.prior_width.{enabled,path}` (live surface is nested under `self.config.ff_opportunity.prior_width` per `src/fantasy_sim/data/ensemble/models.py:63`); same task leaves `test_ks13_path_a_uses_quantile_width_when_lo_hi_present` and `test_ks13_unchanged_when_flag_disabled` as `pass` placeholders despite plan header claiming all six KS-13 tests are concrete | Plan 07 Task 2 blend block + test block | Yes (2) |

### Total unresolved HIGHs (Cycle 3): **2**

(1 partially-resolved cycle-2 carryover + 1 newly raised in cycle 3.)

### Recommended Pre-Execution Actions for Cycle 4 / Escalation

Before executing Plan 02 onward, address the 2 unresolved HIGHs:

1. **Plan 09 stale schema snippets cleanup (HIGH 4 carryover)** — remove the nonexistent `p2.aggregate.full.arm_b.<metric>` notation in the must_haves truth block at line ~18 and update the "Verified code" interfaces excerpt at lines ~81-90 to match the real `SeasonMetrics` schema (`arm_b_rank_corr: dict[str, float]`, `arm_b_weekly_mae: float`, `stat_ks: dict[pos][stat][...]`, `stat_mean_bias: dict[pos][stat][...]`). The detailed Task 1/2 blocks already use the right shape — this is a cleanup of stale top-of-file documentation.

2. **Plan 07 Task 2 config-path correction + concrete Path A / flag-off tests (cycle-3 NEW HIGH)** — rewrite the blend-block snippet at Plan 07 Task 2 lines ~395-400 to use `self.config.ff_opportunity.prior_width.enabled` and `self.config.ff_opportunity.prior_width.path` (the actual nested config path in `EnsembleConfig` per `src/fantasy_sim/data/ensemble/models.py:63`) — NOT the fictional top-level `self.config.prior_width.*`. Replace the `pass` placeholders in `test_ks13_path_a_uses_quantile_width_when_lo_hi_present` (line ~428) and `test_ks13_unchanged_when_flag_disabled` (line ~448) with concrete assertions that exercise the Path A branch and the flag-off pre-Plan-07 byte-identical behavior. Without this, the Path A and flag-off branches are unimplementable from the plan as written, and the plan header's "all six tests concrete" claim is false.

The 1 carry-forward MEDIUM (Plan 08 stub integration tests at lines 242/247) and the cosmetic stale `02-VALIDATION.md:107` reference should also be folded into the next pass but do not block phase entry on their own.

### Cycle Trajectory Summary

| Cycle | Unresolved HIGHs | Notes |
|-------|------------------|-------|
| 1 | 3 | KS-09 output contract, KS-14 flag gate, Plan 09 walk-back additivity |
| 2 | 4 | 1 carry-forward partial + 3 new (Plan 07 probe, Plan 07 Path B, Plan 09 schema) |
| 3 | 2 | 1 carry-forward partial (Plan 09 stale schema snippets) + 1 new (Plan 07 Task 2 config path + placeholder tests) |

Cycle 3 is the FINAL convergence cycle; the orchestrator hits a max-cycles escalation gate after this review. The trajectory is converging (3 → 4 → 2) but has not zeroed out. Per the cycle-3 reviewer's risk assessment: HIGH risk, no go on execution until one more cleanup pass.

---

*Generated by `/gsd-review --phase 2 --codex` on 2026-04-27 (cycle 3, FINAL). To incorporate feedback into planning:*

```
/gsd-plan-phase 2 --reviews
```

---

## Cycle 4 — Codex Review (orchestrator-applied final fixes)

**Reviewed at:** 2026-04-27T02:44:20Z
**Reviewer:** Codex (gpt-5.4)
**Cycle:** 4 (user-requested extension after cycle 3's max-cycles escalation; orchestrator applied targeted manual fixes to the 2 cycle-3 unresolved HIGHs in commit `53c5050`)
**Plans reviewed:** all 9 Phase 2 PLAN.md files at commit `53c5050`
**Cycle 3 HIGH concerns asked about (2 unresolved):**
1. HIGH 1 (cycle-3 carry-forward, originally cycle-2 HIGH 4 partial) — Plan 09 stale ledger-schema documentation (top-of-file truth block + "Verified code" interface excerpt)
2. HIGH 2 (cycle-3 NEW) — Plan 07 Task 2 KS-13 config-path bug (`self.config.prior_width.*` vs nested `self.config.ff_opportunity.prior_width.*`) + 2 placeholder tests claimed concrete

### Summary

The two cycle-3 carry-forward HIGHs are now resolved in the revised plans at `53c5050`: Plan 09's ledger-schema references were corrected to the real `LedgerEntry.season_results -> SeasonMetrics.arm_b_*` shape, and Plan 07's KS-13 snippets no longer use the nonexistent `self.config.prior_width` path while the two specifically-called-out tests are now concrete. I did find one new HIGH in the revised KS-13 plan: the plan says the Phase-2 flag is the master gate, but the implementation path still keys runtime behavior off `ensemble.ff_opportunity.prior_width.enabled`, which breaks true A/B isolation and makes Plan 09's leave-one-out walk-back unreliable.

### Cycle-3 HIGH Resolution Status

- **HIGH 1 — Plan 09 stale ledger-schema documentation**: **FULLY RESOLVED**. The plan now uses helper-based Arm B aggregation instead of the nonexistent `entry.arm_b.<metric>` shape in both the top truth block and the executable examples, and the helper functions are actually defined in the test scaffold: `09-phase2-aggregate-validation-PLAN.md` line 18 (reverse-ablation prose now uses `_avg_arm_b_<metric>(p2.aggregate.full) - _avg_arm_b_<metric>(p2.aggregate.no_K{i})`), line 177 (`_avg_arm_b_rank_corr` helper definition), line 436 (downstream Task 2 reverse-ablation block uses helpers). Those references now match the live ledger schema in `src/fantasy_sim/validation/ledger.py:25` (`SeasonMetrics` with `arm_b_rank_corr: dict[str, float]`, `arm_b_weekly_mae: float`, `weekly_fpts_ks: dict[str, float | int]`, `stat_ks: dict[pos][stat][arm_a_ks/arm_b_ks/ks_delta/n]`, `stat_mean_bias: dict[pos][stat][arm_a_bias/arm_b_bias/bias_delta/n]`).

- **HIGH 2 — Plan 07 Task 2 KS-13 config-path bug + 2 placeholder tests**: **FULLY RESOLVED**. The bad top-level `self.config.prior_width.*` path is gone; both blend snippets now route through `self.config.ff_opportunity.prior_width`, and the two cited tests are concrete rather than `pass` placeholders: `07-ks13-ff-opportunity-prior-width-PLAN.md` line 140 (interfaces example uses `_pw = self.config.ff_opportunity.prior_width`), line 396 (Task 2 implementation uses `_pw = self.config.ff_opportunity.prior_width`), line 430 (`test_ks13_path_a_uses_quantile_width_when_lo_hi_present` is now a 500-seed Monte Carlo with concrete std-tolerance + RNG-determinism assertions), line 509 (`test_ks13_unchanged_when_flag_disabled` is now a concrete differential test with the explicit `0.5*12 + 0.5*20 = 16.0` legacy-path assertion). The live code does not yet have `PriorWidthConfig` in `src/fantasy_sim/data/ensemble/models.py:8`, but the plan now consistently treats that as a future-state addition to be created in Task 2 rather than reading from a nonexistent top-level config field.

### New HIGH Concerns

- **[HIGH] [Plan 07 + Plan 09] KS-13 is not actually master-gated by the Phase-2 flag, so A/B isolation and Plan 09 reverse-ablation can silently mis-measure it.** The plan explicitly says KS-13 is gated by `phase2_ks_flags.ks13_ff_opportunity_prior_width.enabled` (Plan 07 line 25 must_haves), but the runtime implementation block only samples when `_pw.enabled` is true, i.e. `self.config.ff_opportunity.prior_width.enabled` (Plan 07 line 396). The plan's own A/B commands turn BOTH switches on (Plan 07 line 1117 sets `phase2_ks_flags.ks13_ff_opportunity_prior_width.enabled=true` AND `ensemble.ff_opportunity.prior_width.enabled=true`), but Plan 09's leave-one-out walk-back disables only the phase flag (`09-phase2-aggregate-validation-PLAN.md` line 18 — `phase2_ks_flags.K{i}.enabled=false` only). Because there is no loader override or `phase2_flag AND prior_width.enabled` conjunction defined anywhere in Plan 07, a supposed `no_KS13` run can still leave KS-13 active if `ensemble.ff_opportunity.prior_width.enabled` remains true in defaults (which it will be after KS-13 promotion). That is a real implementation blocker: it invalidates per-KS isolation and can corrupt reverse-ablation rollback decisions for KS-13 specifically and the `{KS-08, KS-13}` coupled-cluster pair-revert generally.

### Carry-Forward MEDIUM/LOW Status

- Plan 07 still contains three placeholder tests in Task 2 (`test_ks13_path_b_uses_fitted_std_when_lo_hi_absent`, `test_ks13_path_a_seed_determinism`, `test_ks13_path_b_artifact_loader_graceful_when_missing`), but they are now explicitly deferred to Task 2.5 with concrete replacement bodies, so that is no longer a HIGH-level ambiguity.
- The top "After KS-13" interface example still uses provisional Path-B pseudocode (`self._fitted_std` / `bucket_key`) while Task 2.5 later standardizes on `_fitted_std_for(...)`; that is documentation drift, but the detailed implementation block is clear enough that I would keep it below HIGH.

### Risk Assessment

**Final risk level**: HIGH. The original two cycle-3 HIGHs are fixed, but the new KS-13 gating split is load-bearing: it can make both the per-KS A/B and the Phase-2 aggregate walk-back claim to disable KS-13 while leaving the behavior live. That undermines the trustworthiness of the promotion evidence, not just the prose. Recommended fix: either (a) add a conjunction in `FfOpportunityProjectionEnsembler.blend_week` that requires BOTH `get_phase2_ks_flags().get("ks13_ff_opportunity_prior_width", {}).get("enabled", False)` AND `_pw.enabled` to be true before sampling, OR (b) make the Phase-2 flag the SOLE runtime gate and treat `ensemble.ff_opportunity.prior_width.enabled` as a static schema field that is always true once promoted. Option (a) is more aligned with the Phase 1 D-45 pattern; option (b) is simpler but requires removing one config field. Either way, Plan 09's reverse-ablation walk-back must be able to disable KS-13 with a single flag flip.

### Total Unresolved HIGHs Count

`TOTAL_UNRESOLVED_HIGHS: 1`

---

## Cycle 4 — Consensus Summary

Single-reviewer cycle (`--codex` only).

### Cycle-3 → Cycle-4 HIGH Resolution Audit

| # | Concern | Cycle-3 Finding | Cycle-4 Status | Counted as Unresolved? |
|---|---------|-----------------|----------------|-------------------------|
| 1 | Plan 09 stale ledger-schema documentation (top truth block + interfaces excerpt + `entry.arm_b.<metric>` notation) | PARTIALLY RESOLVED (carry-forward of cycle-2 HIGH 4) | FULLY RESOLVED | No |
| 2 | Plan 07 Task 2 KS-13 config-path bug (`self.config.prior_width.*`) + 2 placeholder tests claimed concrete | STILL UNRESOLVED (cycle-3 NEW) | FULLY RESOLVED | No |

### NEW HIGHs introduced in Cycle 4

| # | Concern | Plan / Site | Counted as Unresolved? |
|---|---------|-------------|-------------------------|
| 3 | KS-13 dual-gate split: Plan 07 must_haves say `phase2_ks_flags.ks13_*` is the master gate, but runtime keys off `ensemble.ff_opportunity.prior_width.enabled` (Plan 07 line 396); Plan 09 walk-back only flips `phase2_ks_flags.K{i}.enabled` (Plan 09 line 18). No conjunction or override defined → a `no_KS13` reverse-ablation iteration can leave KS-13 behavior live. Invalidates per-KS A/B isolation and corrupts reverse-ablation rollback for KS-13 and `{KS-08, KS-13}` coupled-cluster | Plan 07 line 396 + Plan 09 line 18 | Yes (1) |

### Total unresolved HIGHs (Cycle 4): **1**

(0 carry-forward + 1 newly raised in cycle 4.)

### Recommended Pre-Execution Actions for Cycle 5 / Escalation

Before executing Plan 02 onward, address the 1 unresolved HIGH:

1. **KS-13 master-gate conjunction (cycle-4 NEW HIGH)** — pick ONE of:
   - **Option A (recommended, Phase 1 D-45 aligned):** add a conjunction in `FfOpportunityProjectionEnsembler.blend_week` so that the runtime check becomes `phase2_ks_enabled = get_phase2_ks_flags().get("ks13_ff_opportunity_prior_width", {}).get("enabled", False); if phase2_ks_enabled and _pw.enabled and ...`. Update Plan 07 Task 2 implementation snippet (line ~396) AND test scaffolding to mock the phase-2 flag. Update `test_ks13_unchanged_when_flag_disabled` to also cover the case where phase-2 flag is off but `_pw.enabled` is on (must still be byte-identical to legacy).
   - **Option B (simpler, less invariant-preserving):** remove `enabled` from `PriorWidthConfig` entirely; let the phase-2 flag be the SOLE runtime gate; `path` and `artifacts_dir` remain on `PriorWidthConfig` as static config. Update Plan 07 Task 2 + Task 2.5 tests + Plan 09 walk-back accordingly.

   Either option must result in Plan 09's `phase2_ks_flags.K13.enabled=false` override being SUFFICIENT to disable KS-13 in a `no_KS13` aggregate run, with no residual sampling behavior. Add a regression test in `tests/test_scoring/test_ensemble.py` named `test_ks13_phase2_flag_off_disables_sampling_even_with_prior_width_enabled` (or equivalent) that pins this invariant.

The 1 carry-forward MEDIUM (Plan 07 documentation drift between top "After KS-13" example and Task 2.5 standardization on `_fitted_std_for(...)`) can be folded into the cycle-5 revision pass but does not block phase entry on its own.

### Cycle Trajectory Summary

| Cycle | Unresolved HIGHs | Notes |
|-------|------------------|-------|
| 1 | 3 | KS-09 output contract, KS-14 flag gate, Plan 09 walk-back additivity |
| 2 | 4 | 1 carry-forward partial + 3 new (Plan 07 probe, Plan 07 Path B, Plan 09 schema) |
| 3 | 2 | 1 carry-forward partial (Plan 09 stale schema snippets) + 1 new (Plan 07 Task 2 config path + placeholder tests) |
| 4 | 1 | 0 carry-forward + 1 new (Plan 07 + Plan 09 KS-13 dual-gate split) |

Cycle 4 was a user-requested extension after cycle 3's max-cycles escalation; the orchestrator applied targeted manual fixes to both cycle-3 carry-forward HIGHs (commit `53c5050`), and the cycle-4 codex review confirms BOTH are now FULLY RESOLVED. The trajectory is sharply converging (3 → 4 → 2 → 1) with the cycle-4 reviewer surfacing one new previously-missed HIGH in the KS-13 dual-gate runtime semantics. One more cleanup pass is needed to make the Phase-2 KS-13 flag the deterministic master gate that Plan 09's walk-back protocol requires.

---

*Generated by `/gsd-review --phase 2 --codex` on 2026-04-27 (cycle 4, user-requested extension). To incorporate feedback into planning:*

```
/gsd-plan-phase 2 --reviews
```

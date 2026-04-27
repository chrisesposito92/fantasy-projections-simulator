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

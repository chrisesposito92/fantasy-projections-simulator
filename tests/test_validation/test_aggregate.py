"""Phase 2 aggregate validation: Phase-2-vs-Phase-1 delta computation.

Codex cycle-2 alignment (HIGH 4, 2026-04-27):
- Ledger schema: LedgerEntry.season_results is list[SeasonMetrics]
- SeasonMetrics.arm_b_rank_corr: dict[str, float] (keys QB/RB/WR/TE)
- SeasonMetrics.arm_b_weekly_mae: float
- SeasonMetrics.weekly_fpts_ks: dict[str, float | int] (key "arm_b_ks")
- SeasonMetrics.stat_ks: dict[pos][stat][{arm_a_ks, arm_b_ks, ks_delta, n}]
- SeasonMetrics.stat_mean_bias: dict[pos][stat][{arm_a_bias, arm_b_bias, bias_delta, n}]
There is NO entry.arm_b.<metric> object.
"""

from __future__ import annotations

import pytest

POSITIONS = ("QB", "RB", "WR", "TE")


def _read_ledger_entry(label: str):
    """Read a ledger entry by label, return the latest matching LedgerEntry."""
    from fantasy_sim.validation.ledger import load_ledger

    ledger = load_ledger()
    matching = [e for e in ledger if e.label == label]
    if not matching:
        pytest.skip(
            f"Ledger entry {label} not present (likely Plan 09 has not been run yet)"
        )
    return matching[-1]  # latest with this label


def _avg_arm_b_rank_corr(entry) -> float:
    """Average Arm B rank_corr across positions x season_results.

    Schema ref (codex cycle-2 alignment): SeasonMetrics.arm_b_rank_corr is
    dict[str, float] keyed by position. We average across positions then
    across seasons.
    """
    if not entry.season_results:
        pytest.skip(f"Ledger entry {entry.label} has empty season_results")
    per_season = []
    for sm in entry.season_results:
        vals = [sm.arm_b_rank_corr.get(pos, 0.0) for pos in POSITIONS]
        per_season.append(sum(vals) / len(vals))
    return sum(per_season) / len(per_season)


def _avg_arm_b_weekly_mae(entry) -> float:
    """Average Arm B weekly_mae across season_results."""
    if not entry.season_results:
        pytest.skip(f"Ledger entry {entry.label} has empty season_results")
    return (
        sum(sm.arm_b_weekly_mae for sm in entry.season_results)
        / len(entry.season_results)
    )


def _avg_arm_b_fpts_ks(entry) -> float | None:
    """Average Arm B weekly_fpts_ks across season_results.

    SeasonMetrics.weekly_fpts_ks is dict[str, float | int] with key 'arm_b_ks'
    after _normalize_weekly_fpts_ks. Returns None if any season is missing the key.
    """
    if not entry.season_results:
        pytest.skip(f"Ledger entry {entry.label} has empty season_results")
    vals = []
    for sm in entry.season_results:
        v = sm.weekly_fpts_ks.get("arm_b_ks")
        if not isinstance(v, (int, float)):
            return None
        vals.append(float(v))
    return sum(vals) / len(vals) if vals else None


def _avg_arm_b_stat_ks(entry, position: str, stat: str) -> float | None:
    """Average stat_ks[position][stat]['arm_b_ks'] across season_results."""
    vals = []
    for sm in entry.season_results:
        bucket = sm.stat_ks.get(position, {}).get(stat, {})
        v = bucket.get("arm_b_ks") if isinstance(bucket, dict) else None
        if isinstance(v, (int, float)):
            vals.append(float(v))
    return sum(vals) / len(vals) if vals else None


def _avg_arm_b_stat_mean_bias(entry, position: str, stat: str) -> float | None:
    """Average stat_mean_bias[position][stat]['arm_b_bias'] across season_results."""
    vals = []
    for sm in entry.season_results:
        bucket = sm.stat_mean_bias.get(position, {}).get(stat, {})
        v = bucket.get("arm_b_bias") if isinstance(bucket, dict) else None
        if isinstance(v, (int, float)):
            vals.append(float(v))
    return sum(vals) / len(vals) if vals else None


def test_phase2_vs_phase1_delta_within_hard_floor_post_walkback():
    """POST-walk-back hard-floor assertion (codex cycle-2 alignment, HIGH 4).

    This test asserts the hard floor on the FINAL p2.aggregate.full ledger
    entry - i.e. AFTER any reverse-ablation walk-back loops in Task 2 have
    completed. The contract is: Task 1 PINS the initial aggregate (no
    assertion); Task 2 runs the walk-back loop if needed and re-pins
    p2.aggregate.full; this test then asserts hard-floor on the final pinned
    entry. The intent is that a real regression triggers the walk-back protocol
    rather than failing the test suite before Task 2 can run.

    Skip semantics: if p2.aggregate.walkback_complete marker file is absent
    (i.e. Task 2 has not yet finalized), this test is INFORMATIONAL only -
    it logs the delta but does NOT assert. The hard assertion fires only after
    the marker indicates Task 2 is done.
    """
    import os

    marker = ".planning/phases/02-structural-per-stat-calibration/logs/p2_walkback_complete.marker"
    walkback_complete = os.path.exists(marker)

    p1 = _read_ledger_entry("p1.aggregate.full")
    p2 = _read_ledger_entry("p2.aggregate.full")
    p1_rank = _avg_arm_b_rank_corr(p1)
    p2_rank = _avg_arm_b_rank_corr(p2)
    p1_mae = _avg_arm_b_weekly_mae(p1)
    p2_mae = _avg_arm_b_weekly_mae(p2)
    delta_rank_corr = p2_rank - p1_rank
    delta_weekly_mae = p2_mae - p1_mae

    print(f"p1.aggregate.full avg arm_b rank_corr: {p1_rank:.4f}")
    print(f"p2.aggregate.full avg arm_b rank_corr: {p2_rank:.4f}")
    print(f"Delta rank_corr (Phase-2-vs-Phase-1): {delta_rank_corr:+.4f}")
    print(f"p1.aggregate.full avg arm_b weekly_mae: {p1_mae:.4f}")
    print(f"p2.aggregate.full avg arm_b weekly_mae: {p2_mae:.4f}")
    print(f"Delta weekly_mae (Phase-2-vs-Phase-1): {delta_weekly_mae:+.4f}")

    if not walkback_complete:
        pytest.skip(
            f"Walk-back marker absent at {marker}. Task 2 must finalize "
            "p2.aggregate.full (running reverse-ablation loop if needed) "
            "before the hard-floor assertion fires."
        )

    # POST-walk-back hard-floor assertion.
    assert delta_rank_corr >= -0.005, (
        f"hard-floor rank_corr regression: Delta={delta_rank_corr}"
    )
    assert delta_weekly_mae <= +0.05, (
        f"hard-floor MAE regression: Delta={delta_weekly_mae}"
    )


def test_phase2_qb_pass_yards_bias_d14_evaluation():
    """D-14 KS-09 promotion bar: |bias Delta| <= 5 yd/g for SHIPPED.

    Codex cycle-2 alignment: pulls arm_b_bias from
    SeasonMetrics.stat_mean_bias['QB']['pass_yards']['arm_b_bias'] averaged
    across season_results - NOT from a nonexistent entry.arm_b.stat_mean_bias.
    """
    p1 = _read_ledger_entry("p1.aggregate.full")
    p2 = _read_ledger_entry("p2.aggregate.full")
    p1_bias = _avg_arm_b_stat_mean_bias(p1, "QB", "pass_yards") or 0.0
    p2_bias = _avg_arm_b_stat_mean_bias(p2, "QB", "pass_yards") or 0.0
    # The per-stat mean bias should improve (smaller |bias| in p2 vs p1)
    # D-14 SHIPPED requires |p2_bias| <= 5 yd/g (TGT-09 target).
    # This is an INFORMATIONAL test - the actual decision is in Plan 09 PROMOTION-NOTES.md.
    print(f"p1.aggregate.full avg arm_b QB pass_yards bias: {p1_bias} yd/g")
    print(f"p2.aggregate.full avg arm_b QB pass_yards bias: {p2_bias} yd/g")
    print(f"|p2_bias|: {abs(p2_bias)} yd/g (target <= 5 yd/g per TGT-09)")
    # Test passes regardless of bias closure - the test exists to record the values, not to gate


# === Codex HIGH 3 - reverse-ablation walk-back unit tests (Plan 09 Task 2 protocol) ===


def test_reverse_ablation_marginal_delta_computation():
    """Unit-level test for the reverse-ablation marginal_delta formula used in Plan 09 Task 2.

    Codex HIGH 3 (2026-04-27): walk-back uses reverse ablation, NOT isolated per-KS Delta.
    Codex cycle-2 HIGH 4 alignment (2026-04-27): the actual ledger schema does NOT
    expose entry.arm_b.<metric>. The Task 2 inline script uses helper functions
    avg_rank_corr(entry) and avg_weekly_mae(entry) that iterate
    entry.season_results and average across positions/seasons. This test exercises
    the SUBTRACTION formula on synthetic averaged scalars (one float per arm,
    representing the post-aggregation result), so it's decoupled from the
    full schema while still validating the rule:

        marginal_delta_K{i} = avg_full - avg_no_K{i}

    Negative marginal_delta_rank_corr means: removing Ki INCREASED rank_corr (Ki
    was a net negative in the full stack). Positive marginal_delta_rank_corr means:
    removing Ki DECREASED rank_corr (Ki was a net positive - pulling its weight).
    """

    class _AggregatedArmB:
        """Synthetic stand-in for the AVERAGED Arm B scalars produced by
        avg_rank_corr(entry) and avg_weekly_mae(entry) in Task 2."""

        def __init__(self, rank_corr: float, weekly_mae: float):
            self.rank_corr = rank_corr
            self.weekly_mae = weekly_mae

    full = _AggregatedArmB(rank_corr=0.795, weekly_mae=6.10)
    no_ks08 = _AggregatedArmB(
        rank_corr=0.792, weekly_mae=6.05
    )  # KS-08 helped rank but hurt MAE
    no_ks13 = _AggregatedArmB(
        rank_corr=0.793, weekly_mae=6.08
    )  # KS-13 helped rank slightly
    marginal_ks08_rank = (
        full.rank_corr - no_ks08.rank_corr
    )  # +0.003 (KS-08 net positive on rank)
    marginal_ks08_mae = (
        full.weekly_mae - no_ks08.weekly_mae
    )  # +0.05  (KS-08 net negative on MAE)
    marginal_ks13_rank = full.rank_corr - no_ks13.rank_corr  # +0.002
    assert abs(marginal_ks08_rank - 0.003) < 1e-9
    assert abs(marginal_ks08_mae - 0.05) < 1e-9
    assert marginal_ks13_rank > 0
    # Harm score: -marginal_rank + marginal_mae (item is harmful -> high harm_score)
    harm_ks08 = -marginal_ks08_rank + marginal_ks08_mae  # -0.003 + 0.05 = 0.047
    harm_ks13 = -marginal_ks13_rank + (full.weekly_mae - no_ks13.weekly_mae)
    # KS-08 has higher harm_score -> would be reverted first if we needed to pick one
    assert harm_ks08 > harm_ks13


def test_reverse_ablation_coupled_cluster_pair_revert():
    """Codex HIGH 3 coupled-cluster handling (cycle-2 alignment, 2026-04-27):
    when both KS-08 and KS-13 satisfy marginal_delta_rank_corr <= epsilon (epsilon = 0.005)
    in the full-stack reverse ablation - i.e. removing either alone produces a
    near-zero or negative marginal - they must be reverted as a PAIR (single
    rollback unit), not iteratively (which would re-shuffle marginal signs).

    The trigger is <= epsilon, NOT strictly < 0. The coupled-cluster signature is
    *near-zero individual marginals masking a harmful joint effect*: removing
    either one alone leaves the other one's harm intact, so each leave-one-out
    looks individually "fine" while the joint stack is harmful. Synthetic case
    below: full is slightly worse than baseline, but removing either KS-08 or
    KS-13 alone moves rank_corr by only +0.001 (<= epsilon), because the cluster's
    *joint* contribution is what's harmful. The PAIR must be reverted together.
    """
    EPSILON = 0.005  # codex cycle-2 alignment - pair-revert threshold
    # Both KS-08 and KS-13 reshape post-sim variance. Synthetic case: full looks bad but
    # individually neither leave-one-out helps meaningfully, because the cluster's net
    # effect is what's harmful.
    full_rank = 0.788  # slightly worse than entry baseline
    no_ks08_rank = 0.787  # removing only KS-08 barely helps (KS-13 is still doing damage)
    no_ks13_rank = 0.787  # likewise - removing only KS-13 barely helps
    marginal_ks08 = full_rank - no_ks08_rank  # +0.001 (<= epsilon; near-zero)
    marginal_ks13 = full_rank - no_ks13_rank  # +0.001 (<= epsilon; near-zero)
    # Both <= epsilon -> individually each looks "barely-helpful," but the PAIR is harmful.
    # Plan 09 Step 2b.4 detects this case (both <= epsilon in the same iteration) and reverts both together.
    assert marginal_ks08 <= EPSILON and marginal_ks13 <= EPSILON, (
        "Both must satisfy marginal_delta <= epsilon; that is the coupled-cluster signature"
    )
    # Sanity check: pair-revert trigger fires only when BOTH are <= epsilon in the SAME iteration.
    pair_revert_triggered = (marginal_ks08 <= EPSILON) and (marginal_ks13 <= EPSILON)
    assert pair_revert_triggered, "Step 2b.4 must trigger pair revert in this scenario"

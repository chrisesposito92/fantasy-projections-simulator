# src/fantasy_sim/validation/metrics.py
from collections.abc import Sequence

import numpy as np
from scipy.stats import ks_2samp, spearmanr


def _finite_triplets(
    arm_a: Sequence[float],
    arm_b: Sequence[float],
    actual: Sequence[float],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    a_values: list[float] = []
    b_values: list[float] = []
    actual_values: list[float] = []
    for a_raw, b_raw, actual_raw in zip(arm_a, arm_b, actual):
        try:
            a_value = float(a_raw)
            b_value = float(b_raw)
            actual_value = float(actual_raw)
        except (TypeError, ValueError):
            continue
        if not (
            np.isfinite(a_value)
            and np.isfinite(b_value)
            and np.isfinite(actual_value)
        ):
            continue
        a_values.append(a_value)
        b_values.append(b_value)
        actual_values.append(actual_value)
    return (
        np.array(a_values, dtype=float),
        np.array(b_values, dtype=float),
        np.array(actual_values, dtype=float),
    )


def spearman_rank_correlation(
    projected: list[float], actual: list[float]
) -> float:
    """Compute Spearman rank correlation between projected and actual values."""
    if len(projected) < 3:
        return 0.0
    corr, _ = spearmanr(projected, actual)
    return float(corr)


def mean_absolute_error(
    projected: list[float], actual: list[float]
) -> float:
    """Compute mean absolute error between projected and actual per-week values."""
    proj = np.array(projected)
    act = np.array(actual)
    return float(np.mean(np.abs(proj - act)))


def season_total_mae(
    projected_weekly: dict[str, list[float]],
    actual_weekly: dict[str, list[float]],
) -> float:
    """Compute MAE on season totals (sum of weekly values per player)."""
    errors = []
    for pid in projected_weekly:
        if pid in actual_weekly:
            proj_total = sum(projected_weekly[pid])
            act_total = sum(actual_weekly[pid])
            errors.append(abs(proj_total - act_total))
    if not errors:
        return 0.0
    return float(np.mean(errors))


def boom_bust_calibration(
    predicted_boom_pcts: dict[str, float],
    actual_boom_pcts: dict[str, float],
) -> float:
    """Compute mean absolute calibration error for boom/bust predictions."""
    errors = []
    for pid in predicted_boom_pcts:
        if pid in actual_boom_pcts:
            errors.append(abs(predicted_boom_pcts[pid] - actual_boom_pcts[pid]))
    if not errors:
        return 0.0
    return float(np.mean(errors))


def ks_distribution_summary(
    arm_a: Sequence[float],
    arm_b: Sequence[float],
    actual: Sequence[float],
) -> dict[str, float | int]:
    """Compare two projection distributions to actuals with KS and means.

    The inputs should already be matched samples. Any triplet containing a
    missing, non-numeric, or non-finite value is skipped so both arm KS values
    use the same sample population.
    """
    a_values, b_values, actual_values = _finite_triplets(arm_a, arm_b, actual)
    n = int(len(actual_values))
    if n == 0:
        return {}

    arm_a_ks = float(ks_2samp(a_values, actual_values).statistic)
    arm_b_ks = float(ks_2samp(b_values, actual_values).statistic)
    arm_a_mean = float(np.mean(a_values))
    arm_b_mean = float(np.mean(b_values))
    actual_mean = float(np.mean(actual_values))
    return {
        "arm_a_ks": arm_a_ks,
        "arm_b_ks": arm_b_ks,
        "ks_delta": arm_b_ks - arm_a_ks,
        "arm_a_mean": arm_a_mean,
        "arm_b_mean": arm_b_mean,
        "actual_mean": actual_mean,
        "mean_delta_a": arm_a_mean - actual_mean,
        "mean_delta_b": arm_b_mean - actual_mean,
        "n": n,
    }

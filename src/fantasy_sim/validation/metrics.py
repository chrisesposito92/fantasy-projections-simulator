# src/fantasy_sim/validation/metrics.py
import numpy as np
from scipy.stats import spearmanr


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

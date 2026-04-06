# src/fantasy_sim/validation/weekly.py
"""Weekly validation metrics for per-game PFF signal evaluation."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from fantasy_sim.data.actuals import ActualPlayerWeek
from fantasy_sim.data.pff.models import CoverageModifiers
from fantasy_sim.validation.metrics import spearman_rank_correlation

logger = logging.getLogger(__name__)

WEEKLY_LEDGER_PATH = (
    Path(__file__).resolve().parents[3] / "results" / "weekly_ab_ledger.json"
)


@dataclass
class WeeklyPlayerRecord:
    """One player's projection + actual for one week."""

    player_id: str
    name: str
    position: str
    team: str
    week: int
    season: int
    projected_fpts_on: float
    projected_fpts_off: float
    actual_fpts: float
    matchup_factors: dict[str, float] = field(default_factory=dict)
    coverage_modifiers: CoverageModifiers | None = None


@dataclass
class WeeklyPositionSummary:
    """Aggregated weekly metrics for one position."""

    position: str
    weekly_rank_corr_on: float
    weekly_rank_corr_off: float
    weekly_mae_on: float
    weekly_mae_off: float
    mae_by_tercile: dict[str, float]
    n_player_weeks: int
    n_weeks: int


@dataclass
class DirectionalAccuracyResult:
    """WR coverage directional accuracy."""

    total_eligible: int
    correct_direction: int
    accuracy: float


@dataclass
class WeeklyLedgerEntry:
    """One run stored in the weekly ledger."""

    label: str
    timestamp: str
    mode: str
    sims: int
    test_seasons: list[int]
    training_years: int
    position_summaries: list[WeeklyPositionSummary]
    directional_accuracy: DirectionalAccuracyResult | None


def compute_weekly_rank_corr(
    records: list[WeeklyPlayerRecord],
    position: str,
    use_pff_on: bool = True,
) -> float:
    """Average Spearman rank correlation across weeks for one position.

    Groups records by week, computes Spearman per week between projected
    and actual fpts, averages across weeks. Skips weeks with < 5 players.
    """
    pos_records = [r for r in records if r.position == position]
    by_week: dict[int, list[WeeklyPlayerRecord]] = defaultdict(list)
    for r in pos_records:
        by_week[r.week].append(r)

    corrs = []
    for week_records in by_week.values():
        if len(week_records) < 5:
            continue
        projected = [
            r.projected_fpts_on if use_pff_on else r.projected_fpts_off
            for r in week_records
        ]
        actual = [r.actual_fpts for r in week_records]
        corrs.append(spearman_rank_correlation(projected, actual))

    return float(np.mean(corrs)) if corrs else 0.0


def compute_weekly_mae(
    records: list[WeeklyPlayerRecord],
    position: str,
    use_pff_on: bool = True,
) -> float:
    """Average MAE across weeks for one position.

    Groups records by week, computes MAE per week between projected
    and actual fpts, averages across weeks.
    """
    pos_records = [r for r in records if r.position == position]
    by_week: dict[int, list[WeeklyPlayerRecord]] = defaultdict(list)
    for r in pos_records:
        by_week[r.week].append(r)

    maes = []
    for week_records in by_week.values():
        projected = [
            r.projected_fpts_on if use_pff_on else r.projected_fpts_off
            for r in week_records
        ]
        actual = [r.actual_fpts for r in week_records]
        mae = float(np.mean(np.abs(np.array(projected) - np.array(actual))))
        maes.append(mae)

    return float(np.mean(maes)) if maes else 0.0


def _get_adjustment_magnitude(record: WeeklyPlayerRecord) -> float:
    """Max |factor - 1.0| across matchup_factors and coverage modifiers."""
    deviations = [abs(v - 1.0) for v in record.matchup_factors.values()]
    if record.coverage_modifiers is not None:
        deviations.append(abs(record.coverage_modifiers.catch_rate_modifier - 1.0))
        deviations.append(abs(record.coverage_modifiers.ypr_modifier - 1.0))
    return max(deviations) if deviations else 0.0


def compute_mae_by_difficulty(
    records: list[WeeklyPlayerRecord],
    position: str,
) -> dict[str, float]:
    """MAE split by PFF adjustment magnitude terciles.

    Sorts records by max |factor - 1.0| descending, splits into equal
    thirds. Returns MAE for each tercile using PFF-on projections.
    """
    pos_records = [r for r in records if r.position == position]
    if len(pos_records) < 3:
        return {}

    sorted_records = sorted(
        pos_records, key=_get_adjustment_magnitude, reverse=True
    )
    n = len(sorted_records)
    third = n // 3

    strong = sorted_records[:third]
    weak = sorted_records[n - third:]
    neutral = sorted_records[third : n - third]

    result: dict[str, float] = {}
    for label, group in [("strong", strong), ("neutral", neutral), ("weak", weak)]:
        if group:
            errors = [abs(r.projected_fpts_on - r.actual_fpts) for r in group]
            result[label] = float(np.mean(errors))
            if len(group) < 3:
                logger.warning(
                    "Tercile '%s' has only %d entries for %s",
                    label,
                    len(group),
                    position,
                )

    return result

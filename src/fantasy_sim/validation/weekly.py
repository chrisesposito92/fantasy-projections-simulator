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
    by_week: dict[tuple[int, int], list[WeeklyPlayerRecord]] = defaultdict(list)
    for r in pos_records:
        by_week[(r.season, r.week)].append(r)

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
    by_week: dict[tuple[int, int], list[WeeklyPlayerRecord]] = defaultdict(list)
    for r in pos_records:
        by_week[(r.season, r.week)].append(r)

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


def compute_directional_accuracy(
    records: list[WeeklyPlayerRecord],
    actuals_by_player: dict[str, list[ActualPlayerWeek]],
    min_weekly_targets: int = 4,
) -> DirectionalAccuracyResult:
    """WR directional accuracy: did actual catch rate move as coverage predicted?

    For each WR-week with a meaningful coverage modifier (|mod - 1.0| > 0.01),
    checks whether the actual catch rate moved in the predicted direction
    relative to the WR's leave-one-out season average.
    """
    total = 0
    correct = 0

    for record in records:
        if record.position != "WR":
            continue
        if record.coverage_modifiers is None:
            continue
        mod = record.coverage_modifiers.catch_rate_modifier
        if abs(mod - 1.0) <= 0.01:
            continue

        player_actuals = actuals_by_player.get(record.player_id, [])
        if not player_actuals:
            continue

        # Find this week's actual
        this_week = None
        for a in player_actuals:
            if a.week == record.week and a.season == record.season:
                this_week = a
                break
        if this_week is None or this_week.targets < min_weekly_targets:
            continue

        # Leave-one-out season average catch rate (same season only)
        other_weeks = [
            a for a in player_actuals
            if a.season == record.season and a.week != record.week
        ]
        baseline_targets = sum(a.targets for a in other_weeks)
        if baseline_targets == 0:
            continue
        baseline_receptions = sum(a.receptions for a in other_weeks)
        season_avg_cr = baseline_receptions / baseline_targets

        # This week's catch rate
        weekly_cr = this_week.receptions / this_week.targets

        # Check direction
        if mod < 1.0:
            if weekly_cr < season_avg_cr:
                correct += 1
        else:
            if weekly_cr > season_avg_cr:
                correct += 1

        total += 1

    accuracy = correct / total if total > 0 else 0.0
    return DirectionalAccuracyResult(
        total_eligible=total,
        correct_direction=correct,
        accuracy=accuracy,
    )


def load_weekly_ledger(
    path: Path = WEEKLY_LEDGER_PATH,
) -> list[WeeklyLedgerEntry]:
    """Load weekly ledger entries from JSON."""
    if not path.exists():
        return []
    with open(path) as f:
        raw = json.load(f)
    entries = []
    for item in raw:
        pos_summaries = [
            WeeklyPositionSummary(**ps) for ps in item.get("position_summaries", [])
        ]
        da_raw = item.get("directional_accuracy")
        da = DirectionalAccuracyResult(**da_raw) if da_raw else None
        item = dict(item)
        item["position_summaries"] = pos_summaries
        item["directional_accuracy"] = da
        entries.append(WeeklyLedgerEntry(**item))
    return entries


def save_weekly_ledger(
    path: Path,
    entries: list[WeeklyLedgerEntry],
) -> None:
    """Write weekly ledger entries to JSON."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump([asdict(e) for e in entries], f, indent=2)


def format_weekly_progression_table(
    entries: list[WeeklyLedgerEntry],
) -> str:
    """Return an ASCII table of weekly ledger entries."""
    if not entries:
        return "No entries in weekly ledger."

    positions = ("QB", "RB", "WR", "TE")
    header = f"{'#':>3}  {'Label':<25}  "
    header += "  ".join(f"{p}_rc" for p in positions)
    header += "  "
    header += "  ".join(f"{p}_mae" for p in positions)
    header += "  dir_acc"
    sep = "-" * len(header)
    lines = [sep, header, sep]

    for i, e in enumerate(entries, start=1):
        pos_data = {ps.position: ps for ps in e.position_summaries}
        parts = [f"{i:>3}  {e.label:<25}"]

        # Rank corr deltas
        for pos in positions:
            ps = pos_data.get(pos)
            if ps:
                delta = ps.weekly_rank_corr_on - ps.weekly_rank_corr_off
                parts.append(f"{delta:>+.4f}")
            else:
                parts.append(f"{'n/a':>7}")

        # MAE deltas
        for pos in positions:
            ps = pos_data.get(pos)
            if ps:
                delta = ps.weekly_mae_on - ps.weekly_mae_off
                parts.append(f"{delta:>+.3f}")
            else:
                parts.append(f"{'n/a':>7}")

        # Directional accuracy
        if e.directional_accuracy:
            parts.append(f"{e.directional_accuracy.accuracy:.1%}")
        else:
            parts.append("n/a")

        lines.append("  ".join(parts))

    lines.append(sep)
    return "\n".join(lines)

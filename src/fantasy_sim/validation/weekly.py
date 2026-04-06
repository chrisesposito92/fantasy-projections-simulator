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

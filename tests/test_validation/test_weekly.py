# tests/test_validation/test_weekly.py
import pytest
from fantasy_sim.data.pff.models import CoverageModifiers
from fantasy_sim.validation.weekly import (
    WeeklyPlayerRecord,
    WeeklyPositionSummary,
    DirectionalAccuracyResult,
    WeeklyLedgerEntry,
)


def _make_record(
    player_id: str = "P1",
    position: str = "WR",
    week: int = 1,
    season: int = 2024,
    projected_on: float = 10.0,
    projected_off: float = 10.0,
    actual: float = 10.0,
    matchup_factors: dict | None = None,
    coverage_modifiers: CoverageModifiers | None = None,
) -> WeeklyPlayerRecord:
    return WeeklyPlayerRecord(
        player_id=player_id,
        name=f"Player {player_id}",
        position=position,
        team="KC",
        week=week,
        season=season,
        projected_fpts_on=projected_on,
        projected_fpts_off=projected_off,
        actual_fpts=actual,
        matchup_factors=matchup_factors or {},
        coverage_modifiers=coverage_modifiers,
    )


class TestDataStructures:
    def test_weekly_player_record_defaults(self):
        r = _make_record()
        assert r.matchup_factors == {}
        assert r.coverage_modifiers is None

    def test_weekly_player_record_with_coverage(self):
        mods = CoverageModifiers(catch_rate_modifier=0.95, ypr_modifier=1.02)
        r = _make_record(coverage_modifiers=mods)
        assert r.coverage_modifiers.catch_rate_modifier == 0.95
        assert r.coverage_modifiers.ypr_modifier == 1.02

    def test_weekly_player_record_with_matchup_factors(self):
        factors = {"catch_rate_factor": 1.05, "pass_yards_factor": 0.97}
        r = _make_record(matchup_factors=factors)
        assert r.matchup_factors["catch_rate_factor"] == 1.05
        assert len(r.matchup_factors) == 2

    def test_directional_accuracy_result(self):
        dar = DirectionalAccuracyResult(total_eligible=20, correct_direction=12, accuracy=0.6)
        assert dar.accuracy == 0.6

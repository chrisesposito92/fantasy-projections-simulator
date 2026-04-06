# tests/test_validation/test_weekly.py
import pytest
from fantasy_sim.data.pff.models import CoverageModifiers
from fantasy_sim.validation.weekly import (
    WeeklyPlayerRecord,
    WeeklyPositionSummary,
    DirectionalAccuracyResult,
    WeeklyLedgerEntry,
    compute_weekly_rank_corr,
    compute_weekly_mae,
    compute_mae_by_difficulty,
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


class TestComputeWeeklyRankCorr:
    def test_perfect_correlation_two_weeks(self):
        """Two weeks with 5 WRs each, perfect rank preservation → avg 1.0."""
        records = [
            _make_record("P1", "WR", 1, projected_on=25.0, actual=24.0),
            _make_record("P2", "WR", 1, projected_on=20.0, actual=19.0),
            _make_record("P3", "WR", 1, projected_on=15.0, actual=16.0),
            _make_record("P4", "WR", 1, projected_on=10.0, actual=11.0),
            _make_record("P5", "WR", 1, projected_on=5.0, actual=6.0),
            _make_record("P1", "WR", 2, projected_on=22.0, actual=23.0),
            _make_record("P2", "WR", 2, projected_on=18.0, actual=17.0),
            _make_record("P3", "WR", 2, projected_on=14.0, actual=15.0),
            _make_record("P4", "WR", 2, projected_on=8.0, actual=9.0),
            _make_record("P5", "WR", 2, projected_on=4.0, actual=3.0),
        ]
        corr = compute_weekly_rank_corr(records, "WR", use_pff_on=True)
        assert corr == pytest.approx(1.0)

    def test_week_with_fewer_than_5_players_skipped(self):
        records = [
            _make_record("P1", "WR", 1, projected_on=20.0, actual=19.0),
            _make_record("P2", "WR", 1, projected_on=15.0, actual=14.0),
            _make_record("P3", "WR", 1, projected_on=10.0, actual=9.0),
            _make_record("P1", "WR", 2, projected_on=25.0, actual=24.0),
            _make_record("P2", "WR", 2, projected_on=20.0, actual=19.0),
            _make_record("P3", "WR", 2, projected_on=15.0, actual=14.0),
            _make_record("P4", "WR", 2, projected_on=10.0, actual=9.0),
            _make_record("P5", "WR", 2, projected_on=5.0, actual=4.0),
        ]
        corr = compute_weekly_rank_corr(records, "WR")
        assert corr == pytest.approx(1.0)

    def test_position_filtering(self):
        records = [
            _make_record("W1", "WR", 1, projected_on=25.0, actual=24.0),
            _make_record("W2", "WR", 1, projected_on=20.0, actual=19.0),
            _make_record("W3", "WR", 1, projected_on=15.0, actual=14.0),
            _make_record("W4", "WR", 1, projected_on=10.0, actual=9.0),
            _make_record("W5", "WR", 1, projected_on=5.0, actual=4.0),
            _make_record("Q1", "QB", 1, projected_on=30.0, actual=28.0),
            _make_record("Q2", "QB", 1, projected_on=20.0, actual=18.0),
            _make_record("Q3", "QB", 1, projected_on=10.0, actual=8.0),
        ]
        wr_corr = compute_weekly_rank_corr(records, "WR")
        assert wr_corr == pytest.approx(1.0)
        qb_corr = compute_weekly_rank_corr(records, "QB")
        assert qb_corr == 0.0

    def test_uses_pff_off_projection(self):
        records = [
            _make_record("P1", "WR", 1, projected_on=5.0, projected_off=25.0, actual=24.0),
            _make_record("P2", "WR", 1, projected_on=10.0, projected_off=20.0, actual=19.0),
            _make_record("P3", "WR", 1, projected_on=15.0, projected_off=15.0, actual=14.0),
            _make_record("P4", "WR", 1, projected_on=20.0, projected_off=10.0, actual=9.0),
            _make_record("P5", "WR", 1, projected_on=25.0, projected_off=5.0, actual=4.0),
        ]
        on_corr = compute_weekly_rank_corr(records, "WR", use_pff_on=True)
        off_corr = compute_weekly_rank_corr(records, "WR", use_pff_on=False)
        assert on_corr == pytest.approx(-1.0)
        assert off_corr == pytest.approx(1.0)

    def test_no_valid_weeks_returns_zero(self):
        records = [
            _make_record("P1", "WR", 1, projected_on=10.0, actual=9.0),
            _make_record("P2", "WR", 1, projected_on=5.0, actual=4.0),
        ]
        assert compute_weekly_rank_corr(records, "WR") == 0.0

    def test_empty_records_returns_zero(self):
        assert compute_weekly_rank_corr([], "WR") == 0.0


class TestComputeWeeklyMae:
    def test_known_mae_two_weeks(self):
        """Two weeks, known errors → verify averaged MAE."""
        records = [
            # Week 1: errors = |12-10|=2, |18-20|=2, |8-10|=2 → MAE=2.0
            _make_record("P1", "WR", 1, projected_on=12.0, actual=10.0),
            _make_record("P2", "WR", 1, projected_on=18.0, actual=20.0),
            _make_record("P3", "WR", 1, projected_on=8.0, actual=10.0),
            # Week 2: errors = |15-10|=5, |25-20|=5, |5-10|=5 → MAE=5.0
            _make_record("P1", "WR", 2, projected_on=15.0, actual=10.0),
            _make_record("P2", "WR", 2, projected_on=25.0, actual=20.0),
            _make_record("P3", "WR", 2, projected_on=5.0, actual=10.0),
        ]
        mae = compute_weekly_mae(records, "WR")
        assert mae == pytest.approx(3.5)  # (2.0 + 5.0) / 2

    def test_single_week(self):
        records = [
            _make_record("P1", "WR", 1, projected_on=12.0, actual=10.0),
            _make_record("P2", "WR", 1, projected_on=18.0, actual=20.0),
        ]
        mae = compute_weekly_mae(records, "WR")
        assert mae == pytest.approx(2.0)

    def test_position_filtering(self):
        records = [
            _make_record("W1", "WR", 1, projected_on=12.0, actual=10.0),
            _make_record("Q1", "QB", 1, projected_on=30.0, actual=10.0),
        ]
        mae = compute_weekly_mae(records, "WR")
        assert mae == pytest.approx(2.0)

    def test_uses_pff_off(self):
        records = [
            _make_record("P1", "WR", 1, projected_on=15.0, projected_off=12.0, actual=10.0),
        ]
        mae_on = compute_weekly_mae(records, "WR", use_pff_on=True)
        mae_off = compute_weekly_mae(records, "WR", use_pff_on=False)
        assert mae_on == pytest.approx(5.0)
        assert mae_off == pytest.approx(2.0)

    def test_empty_records(self):
        assert compute_weekly_mae([], "WR") == 0.0


class TestComputeMaeByDifficulty:
    def test_nine_records_tercile_split(self):
        """9 records with known magnitudes → 3 per tercile, verify MAE."""
        records = []
        # Strong tercile (mag 0.08, 0.07, 0.06): errors 2, 3, 1 → MAE=2.0
        records.append(_make_record("P1", "WR", 1, projected_on=12.0, actual=10.0,
                                    matchup_factors={"catch_rate_factor": 1.08}))
        records.append(_make_record("P2", "WR", 1, projected_on=13.0, actual=10.0,
                                    matchup_factors={"catch_rate_factor": 1.07}))
        records.append(_make_record("P3", "WR", 1, projected_on=11.0, actual=10.0,
                                    matchup_factors={"catch_rate_factor": 1.06}))
        # Neutral tercile (mag 0.05, 0.04, 0.03): errors 4, 5, 6 → MAE=5.0
        records.append(_make_record("P4", "WR", 2, projected_on=14.0, actual=10.0,
                                    matchup_factors={"catch_rate_factor": 1.05}))
        records.append(_make_record("P5", "WR", 2, projected_on=15.0, actual=10.0,
                                    matchup_factors={"catch_rate_factor": 1.04}))
        records.append(_make_record("P6", "WR", 2, projected_on=16.0, actual=10.0,
                                    matchup_factors={"catch_rate_factor": 1.03}))
        # Weak tercile (mag 0.02, 0.01, 0.00): errors 7, 8, 9 → MAE=8.0
        records.append(_make_record("P7", "WR", 3, projected_on=17.0, actual=10.0,
                                    matchup_factors={"catch_rate_factor": 1.02}))
        records.append(_make_record("P8", "WR", 3, projected_on=18.0, actual=10.0,
                                    matchup_factors={"catch_rate_factor": 1.01}))
        records.append(_make_record("P9", "WR", 3, projected_on=19.0, actual=10.0,
                                    matchup_factors={}))

        result = compute_mae_by_difficulty(records, "WR")
        assert result["strong"] == pytest.approx(2.0)
        assert result["neutral"] == pytest.approx(5.0)
        assert result["weak"] == pytest.approx(8.0)

    def test_coverage_modifiers_included_in_magnitude(self):
        """Coverage modifier with higher deviation should dominate magnitude.

        P1 has coverage catch_rate_modifier=0.90 → magnitude 0.10, which is
        the largest deviation. With 6 records and n//3=2, strong tercile
        contains P1 (err=2) and P6 (err=0) → MAE=1.0.
        """
        mods = CoverageModifiers(catch_rate_modifier=0.90, ypr_modifier=1.0)
        r = _make_record("P1", "WR", 1, projected_on=12.0, actual=10.0,
                         matchup_factors={"catch_rate_factor": 1.02},
                         coverage_modifiers=mods)
        records = [r]
        for i in range(5):
            records.append(_make_record(f"P{i+2}", "WR", 1, projected_on=10.0, actual=10.0,
                                        matchup_factors={"catch_rate_factor": 1.0 + i * 0.001}))
        result = compute_mae_by_difficulty(records, "WR")
        # P1 ranks first (highest magnitude 0.10 from coverage modifier).
        # Strong tercile = 2 records: P1 (err=2.0) + P6 (err=0.0) → MAE=1.0.
        assert result["strong"] == pytest.approx(1.0)

    def test_all_neutral_modifiers(self):
        """All modifiers at 1.0 → all records have magnitude 0, tercile MAEs equal."""
        records = [
            _make_record(f"P{i}", "WR", 1,
                         projected_on=10.0, actual=10.0,
                         matchup_factors={})
            for i in range(9)
        ]
        result = compute_mae_by_difficulty(records, "WR")
        assert result["strong"] == pytest.approx(result["weak"], abs=0.01)

    def test_fewer_than_3_records_returns_empty(self):
        records = [
            _make_record("P1", "WR", 1, projected_on=12.0, actual=10.0),
            _make_record("P2", "WR", 1, projected_on=15.0, actual=10.0),
        ]
        assert compute_mae_by_difficulty(records, "WR") == {}

    def test_empty_records(self):
        assert compute_mae_by_difficulty([], "WR") == {}

    def test_position_filtering(self):
        records = [
            _make_record(f"W{i}", "WR", 1, projected_on=10.0 + i, actual=10.0,
                         matchup_factors={"catch_rate_factor": 1.0 + i * 0.01})
            for i in range(6)
        ]
        records.append(_make_record("Q1", "QB", 1, projected_on=30.0, actual=10.0,
                                    matchup_factors={"sack_rate_factor": 1.10}))
        wr_result = compute_mae_by_difficulty(records, "WR")
        assert "strong" in wr_result
        qb_result = compute_mae_by_difficulty(records, "QB")
        assert qb_result == {}

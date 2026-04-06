# tests/test_validation/test_weekly.py
import pytest
from fantasy_sim.data.actuals import ActualPlayerWeek
from fantasy_sim.data.pff.models import CoverageModifiers
from fantasy_sim.validation.weekly import (
    WeeklyPlayerRecord,
    WeeklyPositionSummary,
    DirectionalAccuracyResult,
    WeeklyLedgerEntry,
    compute_weekly_rank_corr,
    compute_weekly_mae,
    compute_mae_by_difficulty,
    compute_directional_accuracy,
    load_weekly_ledger,
    save_weekly_ledger,
    format_weekly_progression_table,
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


def _make_actual(
    player_id: str = "P1",
    week: int = 1,
    receptions: int = 5,
    targets: int = 8,
) -> ActualPlayerWeek:
    return ActualPlayerWeek(
        player_id=player_id,
        name=f"Player {player_id}",
        position="WR",
        team="KC",
        season=2024,
        week=week,
        fpts=10.0,
        receptions=receptions,
        targets=targets,
    )


def _make_entry(label: str = "test-run") -> WeeklyLedgerEntry:
    return WeeklyLedgerEntry(
        label=label,
        timestamp="2026-04-06T12:00:00",
        mode="all",
        sims=50,
        test_seasons=[2023, 2024],
        training_years=2,
        position_summaries=[
            WeeklyPositionSummary(
                position="WR",
                weekly_rank_corr_on=0.85,
                weekly_rank_corr_off=0.82,
                weekly_mae_on=5.5,
                weekly_mae_off=5.8,
                mae_by_tercile={"strong": 4.0, "neutral": 5.5, "weak": 7.0},
                n_player_weeks=500,
                n_weeks=17,
            ),
        ],
        directional_accuracy=DirectionalAccuracyResult(
            total_eligible=200,
            correct_direction=120,
            accuracy=0.60,
        ),
    )


class TestWeeklyLedger:
    def test_round_trip(self, tmp_path):
        path = tmp_path / "test_ledger.json"
        entries = [_make_entry("run-1"), _make_entry("run-2")]
        save_weekly_ledger(path, entries)
        loaded = load_weekly_ledger(path)
        assert len(loaded) == 2
        assert loaded[0].label == "run-1"
        assert loaded[1].label == "run-2"
        ps = loaded[0].position_summaries[0]
        assert ps.position == "WR"
        assert ps.weekly_rank_corr_on == pytest.approx(0.85)
        assert ps.mae_by_tercile["strong"] == pytest.approx(4.0)
        da = loaded[0].directional_accuracy
        assert da is not None
        assert da.accuracy == pytest.approx(0.60)

    def test_load_nonexistent_returns_empty(self, tmp_path):
        path = tmp_path / "nonexistent.json"
        assert load_weekly_ledger(path) == []

    def test_round_trip_no_directional_accuracy(self, tmp_path):
        path = tmp_path / "test_ledger.json"
        entry = _make_entry()
        entry.directional_accuracy = None
        save_weekly_ledger(path, [entry])
        loaded = load_weekly_ledger(path)
        assert loaded[0].directional_accuracy is None

    def test_format_empty_ledger(self):
        output = format_weekly_progression_table([])
        assert "No entries" in output

    def test_format_one_entry(self):
        output = format_weekly_progression_table([_make_entry("baseline")])
        assert "baseline" in output

    def test_format_multiple_entries(self):
        entries = [_make_entry("run-1"), _make_entry("run-2")]
        output = format_weekly_progression_table(entries)
        assert "run-1" in output
        assert "run-2" in output


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

    def test_multi_season_weeks_not_merged(self):
        """Week 1 from season 2023 and week 1 from 2024 should be separate."""
        records = [
            # Season 2023 week 1: perfect correlation
            _make_record("P1", "WR", 1, 2023, projected_on=25.0, actual=24.0),
            _make_record("P2", "WR", 1, 2023, projected_on=20.0, actual=19.0),
            _make_record("P3", "WR", 1, 2023, projected_on=15.0, actual=14.0),
            _make_record("P4", "WR", 1, 2023, projected_on=10.0, actual=9.0),
            _make_record("P5", "WR", 1, 2023, projected_on=5.0, actual=4.0),
            # Season 2024 week 1: perfect correlation
            _make_record("P6", "WR", 1, 2024, projected_on=25.0, actual=24.0),
            _make_record("P7", "WR", 1, 2024, projected_on=20.0, actual=19.0),
            _make_record("P8", "WR", 1, 2024, projected_on=15.0, actual=14.0),
            _make_record("P9", "WR", 1, 2024, projected_on=10.0, actual=9.0),
            _make_record("P10", "WR", 1, 2024, projected_on=5.0, actual=4.0),
        ]
        corr = compute_weekly_rank_corr(records, "WR")
        # Each season-week has 5 players with perfect correlation
        # Average of two perfect correlations = 1.0
        assert corr == pytest.approx(1.0)


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


class TestComputeDirectionalAccuracy:
    def test_tough_cb_catch_rate_drops_correct(self):
        """Modifier < 1.0, actual catch rate below season avg → correct."""
        mods = CoverageModifiers(catch_rate_modifier=0.95, ypr_modifier=1.0)
        records = [_make_record("P1", "WR", 3, coverage_modifiers=mods)]
        actuals = {
            "P1": [
                _make_actual("P1", 1, receptions=6, targets=8),
                _make_actual("P1", 2, receptions=5, targets=8),
                _make_actual("P1", 3, receptions=3, targets=8),
            ],
        }
        # Leave-one-out avg: (6+5)/(8+8) = 11/16 = 0.6875
        # This week: 3/8 = 0.375 < 0.6875 → correct
        result = compute_directional_accuracy(records, actuals)
        assert result.total_eligible == 1
        assert result.correct_direction == 1
        assert result.accuracy == pytest.approx(1.0)

    def test_weak_cb_catch_rate_rises_correct(self):
        """Modifier > 1.0, actual catch rate above season avg → correct."""
        mods = CoverageModifiers(catch_rate_modifier=1.05, ypr_modifier=1.0)
        records = [_make_record("P1", "WR", 3, coverage_modifiers=mods)]
        actuals = {
            "P1": [
                _make_actual("P1", 1, receptions=4, targets=8),
                _make_actual("P1", 2, receptions=4, targets=8),
                _make_actual("P1", 3, receptions=7, targets=8),
            ],
        }
        result = compute_directional_accuracy(records, actuals)
        assert result.correct_direction == 1

    def test_tough_cb_catch_rate_rises_incorrect(self):
        """Modifier < 1.0, actual catch rate above season avg → incorrect."""
        mods = CoverageModifiers(catch_rate_modifier=0.95, ypr_modifier=1.0)
        records = [_make_record("P1", "WR", 3, coverage_modifiers=mods)]
        actuals = {
            "P1": [
                _make_actual("P1", 1, receptions=4, targets=8),
                _make_actual("P1", 2, receptions=4, targets=8),
                _make_actual("P1", 3, receptions=7, targets=8),
            ],
        }
        result = compute_directional_accuracy(records, actuals)
        assert result.total_eligible == 1
        assert result.correct_direction == 0

    def test_below_min_targets_excluded(self):
        """Weekly targets < 4 → excluded."""
        mods = CoverageModifiers(catch_rate_modifier=0.95, ypr_modifier=1.0)
        records = [_make_record("P1", "WR", 3, coverage_modifiers=mods)]
        actuals = {
            "P1": [
                _make_actual("P1", 1, receptions=4, targets=8),
                _make_actual("P1", 2, receptions=4, targets=8),
                _make_actual("P1", 3, receptions=1, targets=3),
            ],
        }
        result = compute_directional_accuracy(records, actuals, min_weekly_targets=4)
        assert result.total_eligible == 0

    def test_modifier_in_dead_zone_excluded(self):
        """Modifier within 0.01 of 1.0 → excluded."""
        mods = CoverageModifiers(catch_rate_modifier=1.005, ypr_modifier=1.0)
        records = [_make_record("P1", "WR", 3, coverage_modifiers=mods)]
        actuals = {
            "P1": [
                _make_actual("P1", 1, receptions=4, targets=8),
                _make_actual("P1", 2, receptions=4, targets=8),
                _make_actual("P1", 3, receptions=6, targets=8),
            ],
        }
        result = compute_directional_accuracy(records, actuals)
        assert result.total_eligible == 0

    def test_no_coverage_modifiers_excluded(self):
        """Records without coverage_modifiers → excluded."""
        records = [_make_record("P1", "WR", 1)]
        result = compute_directional_accuracy(records, {"P1": [_make_actual()]})
        assert result.total_eligible == 0

    def test_non_wr_excluded(self):
        """Non-WR records → excluded even with coverage_modifiers."""
        mods = CoverageModifiers(catch_rate_modifier=0.95, ypr_modifier=1.0)
        records = [_make_record("P1", "RB", 1, coverage_modifiers=mods)]
        result = compute_directional_accuracy(records, {"P1": [_make_actual()]})
        assert result.total_eligible == 0

    def test_zero_eligible_returns_zero_accuracy(self):
        result = compute_directional_accuracy([], {})
        assert result == DirectionalAccuracyResult(0, 0, 0.0)

    def test_leave_one_out_two_weeks(self):
        """WR with 2 total weeks: baseline is 1 week of data."""
        mods = CoverageModifiers(catch_rate_modifier=0.90, ypr_modifier=1.0)
        records = [_make_record("P1", "WR", 2, coverage_modifiers=mods)]
        actuals = {
            "P1": [
                _make_actual("P1", 1, receptions=6, targets=8),
                _make_actual("P1", 2, receptions=3, targets=8),
            ],
        }
        result = compute_directional_accuracy(records, actuals)
        assert result.total_eligible == 1
        assert result.correct_direction == 1

    def test_leave_one_out_one_week_skipped(self):
        """WR with only 1 total week: baseline has 0 targets → skipped."""
        mods = CoverageModifiers(catch_rate_modifier=0.90, ypr_modifier=1.0)
        records = [_make_record("P1", "WR", 1, coverage_modifiers=mods)]
        actuals = {
            "P1": [_make_actual("P1", 1, receptions=3, targets=8)],
        }
        result = compute_directional_accuracy(records, actuals)
        assert result.total_eligible == 0

    def test_leave_one_out_same_season_only(self):
        """Baseline uses same-season data only, excluding the current week."""
        mods = CoverageModifiers(catch_rate_modifier=0.90, ypr_modifier=1.0)
        # Record is for 2024 week 3
        records = [_make_record("P1", "WR", 3, 2024, coverage_modifiers=mods)]
        # Build actuals with cross-season data
        a_2023_wk1 = _make_actual("P1", 1, receptions=6, targets=8)
        a_2023_wk1.season = 2023
        a_2023_wk3 = _make_actual("P1", 3, receptions=6, targets=8)
        a_2023_wk3.season = 2023
        a_2024_wk1 = _make_actual("P1", 1, receptions=6, targets=8)
        a_2024_wk1.season = 2024
        a_2024_wk3 = _make_actual("P1", 3, receptions=2, targets=8)
        a_2024_wk3.season = 2024

        actuals = {"P1": [a_2023_wk1, a_2023_wk3, a_2024_wk1, a_2024_wk3]}
        result = compute_directional_accuracy(records, actuals)
        # Baseline: same-season only = 2024 wk1 (6/8) = 0.75
        # (2023 data excluded from baseline)
        # This week: 2024 wk3: 2/8 = 0.25 < 0.75, modifier < 1.0 → correct
        assert result.total_eligible == 1
        assert result.correct_direction == 1

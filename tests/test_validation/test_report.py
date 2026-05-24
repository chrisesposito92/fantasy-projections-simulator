from fantasy_sim.validation.report import format_backtest_report
from fantasy_sim.validation.backtester import BacktestResult


class TestFormatBacktestReport:
    def test_returns_string(self):
        result = BacktestResult(
            test_season=2024, weekly_mae=5.5, season_mae=22.0,
            rank_correlations={"QB": 0.85, "RB": 0.80, "WR": 0.82, "TE": 0.81},
            boom_bust_calibration=0.08,
            total_players_evaluated=96, total_weeks_evaluated=18,
        )
        report = format_backtest_report(result)
        assert isinstance(report, str)
        assert "2024" in report

    def test_shows_pass_fail(self):
        result = BacktestResult(
            test_season=2024, weekly_mae=5.5, season_mae=22.0,
            rank_correlations={"QB": 0.85, "RB": 0.80, "WR": 0.82, "TE": 0.81},
            boom_bust_calibration=0.08,
            total_players_evaluated=96, total_weeks_evaluated=18,
        )
        report = format_backtest_report(result)
        assert "PASS" in report

    def test_shows_fail_when_metrics_bad(self):
        result = BacktestResult(
            test_season=2024, weekly_mae=8.0, season_mae=30.0,
            rank_correlations={"QB": 0.70}, boom_bust_calibration=0.15,
            total_players_evaluated=24, total_weeks_evaluated=18,
        )
        report = format_backtest_report(result)
        assert "FAIL" in report

    def test_includes_all_positions(self):
        result = BacktestResult(
            test_season=2024, weekly_mae=5.0, season_mae=20.0,
            rank_correlations={"QB": 0.85, "RB": 0.82, "WR": 0.80, "TE": 0.81},
            boom_bust_calibration=0.07,
            total_players_evaluated=96, total_weeks_evaluated=18,
        )
        report = format_backtest_report(result)
        assert "QB" in report
        assert "RB" in report
        assert "WR" in report
        assert "TE" in report

    def test_includes_distribution_ks_when_present(self):
        result = BacktestResult(
            test_season=2024, weekly_mae=5.0, season_mae=20.0,
            rank_correlations={"QB": 0.85, "RB": 0.82, "WR": 0.80, "TE": 0.81},
            boom_bust_calibration=0.07,
            total_players_evaluated=96, total_weeks_evaluated=18,
            weekly_fpts_ks={
                "ks": 0.12,
                "projected_mean": 13.5,
                "actual_mean": 14.0,
                "mean_delta": -0.5,
                "n": 100,
            },
            stat_ks={
                "WR": {
                    "receiving_yards": {
                        "ks": 0.24,
                        "projected_mean": 43.0,
                        "actual_mean": 50.0,
                        "mean_delta": -7.0,
                        "n": 25,
                    }
                }
            },
        )
        report = format_backtest_report(result)
        assert "Distribution KS" in report
        assert "fpts" in report
        assert "receiving_yards" in report

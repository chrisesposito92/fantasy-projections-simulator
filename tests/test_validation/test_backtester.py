# tests/test_validation/test_backtester.py
import io
import sys

import polars as pl
import pytest
from unittest.mock import patch, MagicMock
from fantasy_sim.validation.backtester import Backtester, BacktestResult


class TestBacktester:
    def test_training_seasons_exclude_test_season(self):
        bt = Backtester(test_season=2024, n_sims=10)
        assert 2024 not in bt.training_seasons
        assert len(bt.training_seasons) > 0

    def test_training_seasons_use_prior_years(self):
        bt = Backtester(test_season=2024, n_sims=10, num_training_seasons=3)
        assert bt.training_seasons == [2021, 2022, 2023]

    def test_backtest_result_has_metrics(self):
        result = BacktestResult(
            test_season=2024,
            weekly_mae=5.5,
            season_mae=22.0,
            rank_correlations={"QB": 0.85, "RB": 0.80, "WR": 0.82, "TE": 0.81},
            boom_bust_calibration=0.08,
            total_players_evaluated=96,
            total_weeks_evaluated=18,
        )
        assert result.weekly_mae < 6.0
        assert result.rank_correlations["QB"] > 0.80
        assert result.passes_targets()

    def test_backtest_result_fails_when_metrics_bad(self):
        result = BacktestResult(
            test_season=2024,
            weekly_mae=8.0,
            season_mae=30.0,
            rank_correlations={"QB": 0.70},
            boom_bust_calibration=0.15,
            total_players_evaluated=24,
            total_weeks_evaluated=18,
        )
        assert not result.passes_targets()


class TestBacktesterRosterHandling:
    @patch("fantasy_sim.validation.backtester.build_games_parallel")
    @patch("fantasy_sim.validation.backtester.DataLoader")
    def test_build_game_receives_target_season_and_week(self, mock_loader_cls, mock_build_parallel):
        mock_loader = MagicMock()
        mock_loader_cls.return_value = mock_loader
        mock_loader.cache_dir = "/tmp/test"
        mock_loader.load_schedules.return_value = pl.DataFrame([
            {"season": 2024, "week": 1, "game_id": "2024_01_KC_BUF",
             "home_team": "KC", "away_team": "BUF"},
        ])
        mock_loader.load_player_stats.return_value = pl.DataFrame({"season": pl.Series([], dtype=pl.Int32)})
        mock_build_parallel.return_value = []

        from fantasy_sim.config.loader import load_defaults, resolve_scoring
        config = load_defaults()
        scoring_config = resolve_scoring(config["scoring"], "ppr")

        bt = Backtester(test_season=2024, n_sims=10)
        bt.loader = mock_loader
        bt.run(scoring_config)

        game_args = mock_build_parallel.call_args[0][0]
        home, away, ts, target, wk, gid, seed = game_args[0]
        assert ts == [2021, 2022, 2023]
        assert target == 2024
        assert wk == 1


class TestBacktesterPffConfig:
    @patch("fantasy_sim.validation.backtester.DataLoader")
    def test_pff_config_stored(self, mock_loader_cls):
        from fantasy_sim.data.pff.models import PffConfig, TalentConfig
        pff_cfg = PffConfig(enabled=True, talent=TalentConfig(enabled=True))
        mock_loader = MagicMock()
        mock_loader_cls.return_value = mock_loader
        mock_loader.cache_dir = "/tmp/test"
        bt = Backtester(test_season=2024, n_sims=10, pff_config=pff_cfg)
        assert bt._pff_config is pff_cfg

    @patch("fantasy_sim.validation.backtester.DataLoader")
    def test_no_pff_config_is_none(self, mock_loader_cls):
        mock_loader = MagicMock()
        mock_loader_cls.return_value = mock_loader
        mock_loader.cache_dir = "/tmp/test"
        bt = Backtester(test_season=2024, n_sims=10)
        assert bt._pff_config is None


class TestBacktesterParallelBuild:
    @patch("fantasy_sim.validation.backtester.build_games_parallel")
    @patch("fantasy_sim.validation.backtester.DataLoader")
    def test_phase1_uses_build_games_parallel(self, mock_loader_cls, mock_build_parallel):
        from pathlib import Path
        mock_loader = MagicMock()
        mock_loader_cls.return_value = mock_loader
        mock_loader.cache_dir = Path("/tmp/test")
        mock_loader.load_schedules.return_value = pl.DataFrame([
            {"season": 2024, "week": 1, "game_id": "2024_01_KC_BUF",
             "home_team": "KC", "away_team": "BUF"},
        ])
        mock_loader.load_player_stats.return_value = pl.DataFrame({"season": pl.Series([], dtype=pl.Int32)})
        mock_build_parallel.return_value = []

        from fantasy_sim.config.loader import load_defaults, resolve_scoring
        scoring_config = resolve_scoring(load_defaults()["scoring"], "ppr")

        bt = Backtester(test_season=2024, n_sims=10, max_workers=4)
        bt.loader = mock_loader
        bt.run(scoring_config)

        mock_build_parallel.assert_called_once()
        call_kwargs = mock_build_parallel.call_args[1]
        assert call_kwargs["max_workers"] == 4
        assert call_kwargs["dual_arm"] is False

    @patch("fantasy_sim.validation.backtester.build_games_parallel")
    @patch("fantasy_sim.validation.backtester.DataLoader")
    def test_phase1_passes_pff_and_weather_config(self, mock_loader_cls, mock_build_parallel):
        from pathlib import Path
        from fantasy_sim.data.pff.models import PffConfig, TalentConfig
        from fantasy_sim.data.weather.models import WeatherConfig

        mock_loader = MagicMock()
        mock_loader_cls.return_value = mock_loader
        mock_loader.cache_dir = Path("/tmp/test")
        mock_loader.load_schedules.return_value = pl.DataFrame(
            {"season": pl.Series([], dtype=pl.Int32), "week": pl.Series([], dtype=pl.Int32),
             "game_id": pl.Series([], dtype=pl.Utf8), "home_team": pl.Series([], dtype=pl.Utf8),
             "away_team": pl.Series([], dtype=pl.Utf8)}
        )
        mock_loader.load_player_stats.return_value = pl.DataFrame({"season": pl.Series([], dtype=pl.Int32)})
        mock_build_parallel.return_value = []

        pff_cfg = PffConfig(enabled=True, talent=TalentConfig(enabled=True))
        weather_cfg = WeatherConfig(enabled=True)

        from fantasy_sim.config.loader import load_defaults, resolve_scoring
        scoring_config = resolve_scoring(load_defaults()["scoring"], "ppr")

        bt = Backtester(test_season=2024, n_sims=10, pff_config=pff_cfg, weather_config=weather_cfg)
        bt.loader = mock_loader
        bt.run(scoring_config)

        call_kwargs = mock_build_parallel.call_args[1]
        assert call_kwargs["pff_config"] is pff_cfg
        assert call_kwargs["weather_config"] is weather_cfg

    @patch("fantasy_sim.validation.backtester.build_games_parallel")
    @patch("fantasy_sim.validation.backtester.DataLoader")
    def test_phase1_passes_tracking_config(self, mock_loader_cls, mock_build_parallel):
        from pathlib import Path
        from fantasy_sim.data.tracking.models import TrackingConfig

        mock_loader = MagicMock()
        mock_loader_cls.return_value = mock_loader
        mock_loader.cache_dir = Path("/tmp/test")
        mock_loader.load_schedules.return_value = pl.DataFrame(
            {
                "season": pl.Series([], dtype=pl.Int32),
                "week": pl.Series([], dtype=pl.Int32),
                "game_id": pl.Series([], dtype=pl.Utf8),
                "home_team": pl.Series([], dtype=pl.Utf8),
                "away_team": pl.Series([], dtype=pl.Utf8),
            }
        )
        mock_loader.load_player_stats.return_value = pl.DataFrame(
            {"season": pl.Series([], dtype=pl.Int32)}
        )
        mock_build_parallel.return_value = []

        tracking_cfg = TrackingConfig(enabled=True)

        from fantasy_sim.config.loader import load_defaults, resolve_scoring
        scoring_config = resolve_scoring(load_defaults()["scoring"], "ppr")

        bt = Backtester(test_season=2024, n_sims=10, tracking_config=tracking_cfg)
        bt.loader = mock_loader
        bt.run(scoring_config)

        call_kwargs = mock_build_parallel.call_args[1]
        assert call_kwargs["tracking_config"] is tracking_cfg

    @patch("fantasy_sim.validation.backtester.build_games_parallel")
    @patch("fantasy_sim.validation.backtester.DataLoader")
    def test_phase1_passes_qb_rushing_config(self, mock_loader_cls, mock_build_parallel):
        from pathlib import Path
        from fantasy_sim.data.qb_rushing import QbRushingConfig, QbScrambleModelConfig

        mock_loader = MagicMock()
        mock_loader_cls.return_value = mock_loader
        mock_loader.cache_dir = Path("/tmp/test")
        mock_loader.load_schedules.return_value = pl.DataFrame(
            {
                "season": pl.Series([], dtype=pl.Int32),
                "week": pl.Series([], dtype=pl.Int32),
                "game_id": pl.Series([], dtype=pl.Utf8),
                "home_team": pl.Series([], dtype=pl.Utf8),
                "away_team": pl.Series([], dtype=pl.Utf8),
            }
        )
        mock_loader.load_player_stats.return_value = pl.DataFrame(
            {"season": pl.Series([], dtype=pl.Int32)}
        )
        mock_build_parallel.return_value = []

        qb_rushing_cfg = QbRushingConfig(
            scramble=QbScrambleModelConfig(enabled=True)
        )

        from fantasy_sim.config.loader import load_defaults, resolve_scoring
        scoring_config = resolve_scoring(load_defaults()["scoring"], "ppr")

        bt = Backtester(test_season=2024, n_sims=10, qb_rushing_config=qb_rushing_cfg)
        bt.loader = mock_loader
        bt.run(scoring_config)

        call_kwargs = mock_build_parallel.call_args[1]
        assert bt._qb_rushing_config is qb_rushing_cfg
        assert call_kwargs["qb_rushing_config"] is qb_rushing_cfg

    @patch("fantasy_sim.validation.backtester.FfOpportunityProjectionEnsembler")
    @patch("fantasy_sim.validation.backtester.simulate_games_parallel")
    @patch("fantasy_sim.validation.backtester.build_games_parallel")
    @patch("fantasy_sim.validation.backtester.load_actual_scores")
    @patch("fantasy_sim.validation.backtester.DataLoader")
    def test_run_uses_blended_projection_metrics_when_ensemble_enabled(
        self,
        mock_loader_cls,
        mock_load_actual_scores,
        mock_build_parallel,
        mock_simulate_parallel,
        mock_ensembler_cls,
    ):
        from pathlib import Path

        from fantasy_sim.config.loader import load_defaults, resolve_scoring
        from fantasy_sim.data.ensemble.models import EnsembleConfig, FfOpportunityConfig

        mock_loader = MagicMock()
        mock_loader_cls.return_value = mock_loader
        mock_loader.cache_dir = Path("/tmp/test")
        mock_loader.load_schedules.return_value = pl.DataFrame([
            {
                "season": 2024,
                "week": 1,
                "game_id": "2024_01_KC_BUF",
                "home_team": "KC",
                "away_team": "BUF",
            }
        ])
        mock_loader.load_player_stats.return_value = pl.DataFrame(
            {"season": pl.Series([], dtype=pl.Int32)}
        )
        mock_build_parallel.return_value = [_make_ok_result("2024_01_KC_BUF")]
        mock_simulate_parallel.return_value = [
            MagicMock(
                game_id="2024_01_KC_BUF",
                projections=[
                    {
                        "player_id": "player-1",
                        "fpts": 12.0,
                        "position": "QB",
                        "team": "KC",
                        "name": "Patrick Example",
                    }
                ],
            )
        ]
        mock_load_actual_scores.return_value = [
            MagicMock(
                player_id="player-1",
                week=1,
                fpts=13.5,
                position="QB",
                team="KC",
                name="Patrick Example",
            )
        ]
        mock_ensembler = mock_ensembler_cls.return_value
        mock_ensembler.blend_week.return_value = (
            [{
                "player_id": "player-1",
                "fpts": 13.5,
                "position": "QB",
                "team": "KC",
                "name": "Patrick Example",
            }],
            MagicMock(total_rows=1, covered_rows=1, uncovered_rows=0),
        )

        scoring_config = resolve_scoring(load_defaults()["scoring"], "ppr")
        bt = Backtester(
            test_season=2024,
            n_sims=10,
            ensemble_config=EnsembleConfig(
                enabled=True,
                ff_opportunity=FfOpportunityConfig(enabled=True),
            ),
        )
        bt.loader = mock_loader

        result = bt.run(scoring_config)

        mock_ensembler_cls.assert_called_once()
        mock_ensembler.blend_week.assert_called_once_with(
            [{
                "player_id": "player-1",
                "fpts": 12.0,
                "position": "QB",
                "team": "KC",
                "name": "Patrick Example",
            }],
            season=2024,
            week=1,
        )
        assert result.weekly_mae == 0.0
        assert result.season_mae == 0.0

    @patch("fantasy_sim.validation.backtester.FfOpportunityProjectionEnsembler")
    @patch("fantasy_sim.validation.backtester.simulate_games_parallel")
    @patch("fantasy_sim.validation.backtester.build_games_parallel")
    @patch("fantasy_sim.validation.backtester.load_actual_scores")
    @patch("fantasy_sim.validation.backtester.DataLoader")
    def test_run_skips_ensembler_when_ff_opportunity_is_disabled(
        self,
        mock_loader_cls,
        mock_load_actual_scores,
        mock_build_parallel,
        mock_simulate_parallel,
        mock_ensembler_cls,
    ):
        from pathlib import Path

        from fantasy_sim.config.loader import load_defaults, resolve_scoring
        from fantasy_sim.data.ensemble.models import EnsembleConfig, FfOpportunityConfig

        mock_loader = MagicMock()
        mock_loader_cls.return_value = mock_loader
        mock_loader.cache_dir = Path("/tmp/test")
        mock_loader.load_schedules.return_value = pl.DataFrame([
            {
                "season": 2024,
                "week": 1,
                "game_id": "2024_01_KC_BUF",
                "home_team": "KC",
                "away_team": "BUF",
            }
        ])
        mock_loader.load_player_stats.return_value = pl.DataFrame(
            {"season": pl.Series([], dtype=pl.Int32)}
        )
        mock_build_parallel.return_value = [_make_ok_result("2024_01_KC_BUF")]
        mock_simulate_parallel.return_value = []
        mock_load_actual_scores.return_value = []

        scoring_config = resolve_scoring(load_defaults()["scoring"], "ppr")
        bt = Backtester(
            test_season=2024,
            n_sims=10,
            ensemble_config=EnsembleConfig(
                enabled=True,
                ff_opportunity=FfOpportunityConfig(enabled=False),
            ),
        )
        bt.loader = mock_loader
        bt.run(scoring_config)

        mock_ensembler_cls.assert_not_called()


def _make_ok_result(game_id: str, week: int = 1) -> dict:
    """Helper: build an 'ok' build result dict with minimal stub data."""
    return {
        "status": "ok",
        "game_id": game_id,
        "seed": 42,
        "week": week,
        "home": "KC",
        "away": "BUF",
        "home_dists": MagicMock(),
        "away_dists": MagicMock(),
        "home_roster": MagicMock(),
        "away_roster": MagicMock(),
    }


def _make_error_result(game_id: str, week: int = 1, error_type: str = "KeyError") -> dict:
    """Helper: build an 'error' build result dict."""
    return {
        "status": "error",
        "game_id": game_id,
        "seed": 42,
        "week": week,
        "home": "KC",
        "away": "BUF",
        "error": f"Some {error_type} occurred",
        "error_type": error_type,
    }


def _mock_loader():
    """Helper: create a mock DataLoader with minimal schedule data."""
    mock_loader = MagicMock()
    mock_loader.cache_dir = "/tmp/test"
    mock_loader.load_schedules.return_value = pl.DataFrame([
        {"season": 2024, "week": 1, "game_id": "2024_01_KC_BUF",
         "home_team": "KC", "away_team": "BUF"},
    ])
    mock_loader.load_player_stats.return_value = pl.DataFrame(
        {"season": pl.Series([], dtype=pl.Int32)}
    )
    return mock_loader


class TestBacktesterFailureSurfacing:
    """Tests for FIX-01 (failure counting) and FIX-03 (hold-out gate)."""

    def test_holdout_season_raises(self):
        """Backtester(test_season=2025) must raise ValueError with 'hold-out'."""
        with pytest.raises(ValueError, match="hold-out"):
            Backtester(test_season=2025)

    def test_holdout_season_2024_allowed(self):
        """Backtester(test_season=2024) must NOT raise."""
        bt = Backtester(test_season=2024, n_sims=10)
        assert bt.test_season == 2024

    def test_holdout_season_2026_raises(self):
        """Backtester(test_season=2026) must also raise (>= check)."""
        with pytest.raises(ValueError, match="hold-out"):
            Backtester(test_season=2026)

    @patch("fantasy_sim.validation.backtester.simulate_games_parallel")
    @patch("fantasy_sim.validation.backtester.build_games_parallel")
    @patch("fantasy_sim.validation.backtester.load_actual_scores")
    @patch("fantasy_sim.validation.backtester.DataLoader")
    def test_build_failures_counted_and_logged(
        self, mock_loader_cls, mock_load_actuals, mock_build, mock_sim
    ):
        """1 failure out of 20 games (5%) -- should complete without AssertionError.

        Strict < 0.05 means 1/20 = 5% is NOT below threshold. Use 1/21.
        """
        mock_loader_cls.return_value = _mock_loader()
        mock_load_actuals.return_value = []

        # 20 ok results + 1 error = 21 total, failure rate = 1/21 ~ 4.8% < 5%
        results = [_make_ok_result(f"game_{i}") for i in range(20)]
        results.append(_make_error_result("game_fail_1"))
        mock_build.return_value = results
        mock_sim.return_value = []

        from fantasy_sim.config.loader import load_defaults, resolve_scoring
        scoring_config = resolve_scoring(load_defaults()["scoring"], "ppr")

        bt = Backtester(test_season=2024, n_sims=10)
        bt.loader = _mock_loader()

        # Should NOT raise -- failure rate is below 5%
        bt.run(scoring_config)

    @patch("fantasy_sim.validation.backtester.simulate_games_parallel")
    @patch("fantasy_sim.validation.backtester.build_games_parallel")
    @patch("fantasy_sim.validation.backtester.load_actual_scores")
    @patch("fantasy_sim.validation.backtester.DataLoader")
    def test_build_failure_rate_above_threshold(
        self, mock_loader_cls, mock_load_actuals, mock_build, mock_sim
    ):
        """2 failures out of 20 games (10% > 5%) -- must raise AssertionError."""
        mock_loader_cls.return_value = _mock_loader()
        mock_load_actuals.return_value = []

        results = [_make_ok_result(f"game_{i}") for i in range(18)]
        results.append(_make_error_result("game_fail_1"))
        results.append(_make_error_result("game_fail_2"))
        mock_build.return_value = results
        mock_sim.return_value = []

        from fantasy_sim.config.loader import load_defaults, resolve_scoring
        scoring_config = resolve_scoring(load_defaults()["scoring"], "ppr")

        bt = Backtester(test_season=2024, n_sims=10)
        bt.loader = _mock_loader()

        with pytest.raises(AssertionError, match="failure rate"):
            bt.run(scoring_config)

    @patch("fantasy_sim.validation.backtester.simulate_games_parallel")
    @patch("fantasy_sim.validation.backtester.build_games_parallel")
    @patch("fantasy_sim.validation.backtester.load_actual_scores")
    @patch("fantasy_sim.validation.backtester.DataLoader")
    def test_error_type_in_failure_output(
        self, mock_loader_cls, mock_load_actuals, mock_build, mock_sim
    ):
        """Error result with error_type='KeyError' should appear in FAIL output."""
        mock_loader_cls.return_value = _mock_loader()
        mock_load_actuals.return_value = []

        # 20 ok + 1 error with KeyError type
        results = [_make_ok_result(f"game_{i}") for i in range(20)]
        results.append(_make_error_result("game_fail_key", error_type="KeyError"))
        mock_build.return_value = results
        mock_sim.return_value = []

        from fantasy_sim.config.loader import load_defaults, resolve_scoring
        scoring_config = resolve_scoring(load_defaults()["scoring"], "ppr")

        bt = Backtester(test_season=2024, n_sims=10)
        bt.loader = _mock_loader()

        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            bt.run(scoring_config)
        finally:
            sys.stdout = old_stdout

        output = captured.getvalue()
        assert "KeyError" in output
        assert "game_fail_key" in output

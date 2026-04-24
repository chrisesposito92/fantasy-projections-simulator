"""Focused regression tests for scripts/validate.py plumbing."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import polars as pl
import pytest

from fantasy_sim.validation.coverage import SignalCoverage


def _load_validate_module():
    validate_path = Path(__file__).resolve().parents[2] / "scripts" / "validate.py"
    spec = importlib.util.spec_from_file_location("validate_script_under_test", validate_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_run_season_threads_game_script_config_into_dual_arm_build():
    validate = _load_validate_module()

    with patch.object(validate, "simulate_games_parallel", return_value=[]), \
         patch.object(validate, "build_games_parallel", return_value=[]) as mock_build_games_parallel, \
         patch.object(validate, "load_actual_scores", return_value=[]), \
         patch.object(validate, "DataLoader") as mock_loader_cls:
        mock_loader = mock_loader_cls.return_value
        mock_loader.cache_dir = Path("/tmp/test-cache")
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

        game_script_config = object()
        arm_a_configs = {
            "pff_config": None,
            "weather_config": None,
            "vegas_config": None,
            "props_config": None,
            "usage_config": None,
            "tracking_config": None,
            "game_script_config": None,
            "goal_line_concentration_config": None,
            "td_tendency_config": None,
        }
        arm_b_configs = {
            "pff_config": None,
            "weather_config": None,
            "vegas_config": None,
            "props_config": None,
            "usage_config": None,
            "tracking_config": None,
            "game_script_config": game_script_config,
            "goal_line_concentration_config": None,
            "td_tendency_config": None,
        }

        validate.run_season(
            test_season=2024,
            n_sims=10,
            scoring_config={},
            num_training_seasons=3,
            arm_a_configs=arm_a_configs,
            arm_b_configs=arm_b_configs,
            positions=["QB"],
            max_workers=1,
        )

    call_kwargs = mock_build_games_parallel.call_args.kwargs
    assert call_kwargs["dual_arm"] is True
    assert call_kwargs["game_script_config"] is game_script_config


def test_run_season_threads_goal_line_concentration_config_into_dual_arm_build():
    validate = _load_validate_module()

    with patch.object(validate, "simulate_games_parallel", return_value=[]), \
         patch.object(validate, "build_games_parallel", return_value=[]) as mock_build_games_parallel, \
         patch.object(validate, "load_actual_scores", return_value=[]), \
         patch.object(validate, "DataLoader") as mock_loader_cls:
        mock_loader = mock_loader_cls.return_value
        mock_loader.cache_dir = Path("/tmp/test-cache")
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

        arm_b_goal_line_concentration_config = object()
        arm_a_configs = {
            "pff_config": None,
            "weather_config": None,
            "vegas_config": None,
            "props_config": None,
            "usage_config": None,
            "tracking_config": None,
            "game_script_config": None,
            "goal_line_concentration_config": None,
            "td_tendency_config": None,
        }
        arm_b_configs = {
            "pff_config": None,
            "weather_config": None,
            "vegas_config": None,
            "props_config": None,
            "usage_config": None,
            "tracking_config": None,
            "game_script_config": None,
            "goal_line_concentration_config": arm_b_goal_line_concentration_config,
            "td_tendency_config": None,
        }

        validate.run_season(
            test_season=2024,
            n_sims=10,
            scoring_config={},
            num_training_seasons=3,
            arm_a_configs=arm_a_configs,
            arm_b_configs=arm_b_configs,
            positions=["QB"],
            max_workers=1,
        )

    call_kwargs = mock_build_games_parallel.call_args.kwargs
    assert call_kwargs["dual_arm"] is True
    assert call_kwargs["goal_line_concentration_config"] is arm_b_goal_line_concentration_config


def test_run_season_threads_td_tendency_config_into_dual_arm_build():
    validate = _load_validate_module()

    with patch.object(validate, "simulate_games_parallel", return_value=[]), \
         patch.object(validate, "build_games_parallel", return_value=[]) as mock_build_games_parallel, \
         patch.object(validate, "load_actual_scores", return_value=[]), \
         patch.object(validate, "DataLoader") as mock_loader_cls:
        mock_loader = mock_loader_cls.return_value
        mock_loader.cache_dir = Path("/tmp/test-cache")
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

        arm_b_td_tendency_config = object()
        arm_a_configs = {
            "pff_config": None,
            "weather_config": None,
            "vegas_config": None,
            "props_config": None,
            "usage_config": None,
            "tracking_config": None,
            "game_script_config": None,
            "goal_line_concentration_config": None,
            "td_tendency_config": None,
        }
        arm_b_configs = {
            "pff_config": None,
            "weather_config": None,
            "vegas_config": None,
            "props_config": None,
            "usage_config": None,
            "tracking_config": None,
            "game_script_config": None,
            "goal_line_concentration_config": None,
            "td_tendency_config": arm_b_td_tendency_config,
        }

        validate.run_season(
            test_season=2024,
            n_sims=10,
            scoring_config={},
            num_training_seasons=3,
            arm_a_configs=arm_a_configs,
            arm_b_configs=arm_b_configs,
            positions=["QB"],
            max_workers=1,
        )

    call_kwargs = mock_build_games_parallel.call_args.kwargs
    assert call_kwargs["dual_arm"] is True
    assert call_kwargs["td_tendency_config"] is arm_b_td_tendency_config


def test_run_season_threads_tracking_config_into_bare_baseline_dual_arm_build():
    validate = _load_validate_module()

    with patch.object(validate, "simulate_games_parallel", return_value=[]), \
         patch.object(validate, "build_games_parallel", return_value=[]) as mock_build_games_parallel, \
         patch.object(validate, "load_actual_scores", return_value=[]), \
         patch.object(validate, "DataLoader") as mock_loader_cls:
        mock_loader = mock_loader_cls.return_value
        mock_loader.cache_dir = Path("/tmp/test-cache")
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

        tracking_config = object()
        arm_a_configs = {
            "pff_config": None,
            "weather_config": None,
            "vegas_config": None,
            "props_config": None,
            "usage_config": None,
            "tracking_config": None,
            "availability_config": None,
            "role_trend_config": None,
            "market_history_config": None,
            "game_script_config": None,
            "goal_line_concentration_config": None,
            "td_tendency_config": None,
        }
        arm_b_configs = {
            "pff_config": None,
            "weather_config": None,
            "vegas_config": None,
            "props_config": None,
            "usage_config": None,
            "tracking_config": tracking_config,
            "availability_config": None,
            "role_trend_config": None,
            "market_history_config": None,
            "game_script_config": None,
            "goal_line_concentration_config": None,
            "td_tendency_config": None,
        }

        validate.run_season(
            test_season=2024,
            n_sims=10,
            scoring_config={},
            num_training_seasons=3,
            arm_a_configs=arm_a_configs,
            arm_b_configs=arm_b_configs,
            positions=["QB"],
            max_workers=1,
        )

    call_kwargs = mock_build_games_parallel.call_args.kwargs
    assert call_kwargs["dual_arm"] is True
    assert call_kwargs["tracking_config"] is tracking_config


def test_run_season_does_not_thread_market_history_config_into_build_kwargs():
    validate = _load_validate_module()

    with patch.object(validate, "simulate_games_parallel", return_value=[]), \
         patch.object(validate, "build_games_parallel", return_value=[]) as mock_build_games_parallel, \
         patch.object(validate, "load_actual_scores", return_value=[]), \
         patch.object(validate, "DataLoader") as mock_loader_cls:
        mock_loader = mock_loader_cls.return_value
        mock_loader.cache_dir = Path("/tmp/test-cache")
        mock_loader.load_schedules.return_value = pl.DataFrame(
            [
                {
                    "season": 2024,
                    "week": 1,
                    "game_id": "2024_01_KC_BUF",
                    "home_team": "KC",
                    "away_team": "BUF",
                }
            ]
        )
        mock_loader.load_player_stats.return_value = pl.DataFrame(
            {"season": pl.Series([], dtype=pl.Int32)}
        )

        validate.run_season(
            test_season=2024,
            n_sims=10,
            scoring_config={},
            num_training_seasons=3,
            arm_a_configs={
                "pff_config": None,
                "weather_config": None,
                "vegas_config": None,
                "props_config": None,
                "usage_config": None,
                "tracking_config": None,
                "availability_config": None,
                "role_trend_config": None,
                "market_history_config": None,
                "game_script_config": None,
                "goal_line_concentration_config": None,
                "td_tendency_config": None,
            },
            arm_b_configs={
                "pff_config": None,
                "weather_config": None,
                "vegas_config": None,
                "props_config": None,
                "usage_config": None,
                "tracking_config": None,
                "availability_config": None,
                "role_trend_config": None,
                "market_history_config": object(),
                "game_script_config": None,
                "goal_line_concentration_config": None,
                "td_tendency_config": None,
            },
            positions=["QB"],
            max_workers=1,
        )

    call_kwargs = mock_build_games_parallel.call_args.kwargs
    assert "market_history_config" not in call_kwargs


def test_run_season_threads_scoring_config_into_market_history_adjusters():
    validate = _load_validate_module()
    scoring_config = {"reception": 0.5}

    with patch.object(validate, "simulate_games_parallel", return_value=[]), \
         patch.object(validate, "build_games_parallel", return_value=[]) as _mock_build_games_parallel, \
         patch.object(validate, "load_actual_scores", return_value=[]), \
         patch.object(validate, "DataLoader") as mock_loader_cls, \
         patch.object(validate, "MarketHistoryProjectionAdjuster") as mock_market_history:
        mock_loader = mock_loader_cls.return_value
        mock_loader.cache_dir = Path("/tmp/test-cache")
        mock_loader.load_schedules.return_value = pl.DataFrame(
            [
                {
                    "season": 2024,
                    "week": 1,
                    "game_id": "2024_01_KC_BUF",
                    "home_team": "KC",
                    "away_team": "BUF",
                }
            ]
        )
        mock_loader.load_player_stats.return_value = pl.DataFrame(
            {"season": pl.Series([], dtype=pl.Int32)}
        )

        validate.run_season(
            test_season=2024,
            n_sims=10,
            scoring_config=scoring_config,
            num_training_seasons=3,
            arm_a_configs={
                "pff_config": None,
                "weather_config": None,
                "vegas_config": None,
                "props_config": None,
                "usage_config": None,
                "tracking_config": None,
                "availability_config": None,
                "role_trend_config": None,
                "market_history_config": object(),
                "game_script_config": None,
                "goal_line_concentration_config": None,
                "td_tendency_config": None,
            },
            arm_b_configs={
                "pff_config": None,
                "weather_config": None,
                "vegas_config": None,
                "props_config": None,
                "usage_config": None,
                "tracking_config": None,
                "availability_config": None,
                "role_trend_config": None,
                "market_history_config": object(),
                "game_script_config": None,
                "goal_line_concentration_config": None,
                "td_tendency_config": None,
            },
            positions=["QB"],
            max_workers=1,
        )

    assert mock_market_history.call_count == 2
    for call in mock_market_history.call_args_list:
        assert call.kwargs["scoring_config"] is scoring_config


def test_run_season_prints_game_script_summary_when_profiles_are_collected():
    validate = _load_validate_module()

    home_profile = SimpleNamespace(team="KC")
    home_dists = SimpleNamespace(game_script_profile=home_profile)
    away_dists = SimpleNamespace(game_script_profile=None)
    build_results = [{
        "status": "ok",
        "game_id": "2024_01_KC_BUF",
        "seed": 7,
        "week": 1,
        "home": "KC",
        "away": "BUF",
        "results": {
            "off": (SimpleNamespace(game_script_profile=None), SimpleNamespace(game_script_profile=None), None, None),
            "on": (home_dists, away_dists, None, None),
        },
    }]

    with patch.object(validate, "simulate_games_parallel", return_value=[]), \
         patch.object(validate, "build_games_parallel", return_value=build_results), \
         patch.object(validate, "load_actual_scores", return_value=[]), \
         patch.object(validate, "collect_game_script_profiles", return_value={"KC": home_profile}) as mock_collect, \
         patch.object(validate, "format_game_script_summary", return_value="SUMMARY\n") as mock_format, \
         patch.object(validate, "print") as mock_print, \
         patch.object(validate, "DataLoader") as mock_loader_cls:
        mock_loader = mock_loader_cls.return_value
        mock_loader.cache_dir = Path("/tmp/test-cache")
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

        validate.run_season(
            test_season=2024,
            n_sims=10,
            scoring_config={},
            num_training_seasons=3,
            arm_a_configs={
                "pff_config": None,
                "weather_config": None,
                "vegas_config": None,
                "props_config": None,
                "usage_config": None,
                "tracking_config": None,
                "game_script_config": None,
                "goal_line_concentration_config": None,
                "td_tendency_config": None,
            },
            arm_b_configs={
                "pff_config": None,
                "weather_config": None,
                "vegas_config": None,
                "props_config": None,
                "usage_config": None,
                "tracking_config": None,
                "game_script_config": object(),
                "goal_line_concentration_config": None,
                "td_tendency_config": None,
            },
            positions=["QB"],
            max_workers=1,
        )

    collected_specs = mock_collect.call_args.args[0]
    assert len(collected_specs) == 1
    assert collected_specs[0].home_dists is home_dists
    mock_format.assert_called_once_with({"KC": home_profile})
    mock_print.assert_any_call("SUMMARY\n", end="", flush=True)


def test_print_header_renders_comparison_metadata_and_coverage_summary():
    validate = _load_validate_module()
    args = SimpleNamespace(
        baseline="defaults",
        overrides=[],
        sims=50,
        seasons=[2022, 2023, 2024],
        scoring="ppr",
        no_cache=False,
    )
    coverage_summary = {
        "pff": SignalCoverage(
            enabled=True,
            status="partial",
            covered_seasons=[2022, 2024],
            missing_seasons=[2023],
            note="Requires historical PFF coverage for 2023",
        ),
        "props": SignalCoverage(
            enabled=True,
            status="none",
            covered_seasons=[],
            missing_seasons=[2022, 2023, 2024],
            note="Forward-only unless season parquet files exist",
        ),
    }

    with patch.object(validate, "print") as mock_print:
        validate.print_header(
            args,
            {2024: True},
            comparison_mode="marginal_lift",
            seed_mode="deterministic_game_id_crc32_shared_between_arms",
            coverage_summary=coverage_summary,
        )

    printed = "\n".join(call.args[0] for call in mock_print.call_args_list)
    assert "marginal_lift" in printed
    assert "deterministic_game_id_crc32_shared_between_arms" in printed
    assert "coverage" in printed
    assert "coverage notes" in printed
    assert "pff" in printed
    assert "props" in printed
    assert "historical PFF coverage for 2023" in printed
    assert "Forward-only unless season parquet files exist" in printed


def test_print_market_history_results_uses_only_covered_seasons():
    validate = _load_validate_module()

    season_results = [
        validate.SeasonMetrics(
            test_season=2022,
            arm_a_rank_corr={"QB": 0.40, "RB": 0.40, "WR": 0.40, "TE": 0.40},
            arm_b_rank_corr={"QB": 0.40, "RB": 0.40, "WR": 0.40, "TE": 0.40},
            arm_a_weekly_mae=7.0,
            arm_b_weekly_mae=7.0,
            arm_a_season_mae=30.0,
            arm_b_season_mae=30.0,
            arm_a_calibration=0.1,
            arm_b_calibration=0.1,
        ),
        validate.SeasonMetrics(
            test_season=2023,
            arm_a_rank_corr={"QB": 0.40, "RB": 0.40, "WR": 0.40, "TE": 0.40},
            arm_b_rank_corr={"QB": 0.50, "RB": 0.50, "WR": 0.50, "TE": 0.50},
            arm_a_weekly_mae=7.0,
            arm_b_weekly_mae=6.5,
            arm_a_season_mae=30.0,
            arm_b_season_mae=29.0,
            arm_a_calibration=0.1,
            arm_b_calibration=0.1,
        ),
        validate.SeasonMetrics(
            test_season=2024,
            arm_a_rank_corr={"QB": 0.40, "RB": 0.40, "WR": 0.40, "TE": 0.40},
            arm_b_rank_corr={"QB": 0.60, "RB": 0.60, "WR": 0.60, "TE": 0.60},
            arm_a_weekly_mae=7.0,
            arm_b_weekly_mae=6.0,
            arm_a_season_mae=30.0,
            arm_b_season_mae=28.0,
            arm_a_calibration=0.1,
            arm_b_calibration=0.1,
        ),
    ]
    coverage_summary = {
        "market_history": SignalCoverage(
            enabled=True,
            status="partial",
            covered_seasons=[2023, 2024],
            missing_seasons=[2022],
            note="Requires processed season parquet at ~/.fantasy-sim/market-history/processed",
        )
    }

    with patch.object(validate, "print") as mock_print:
        validate.print_market_history_results(season_results, coverage_summary)

    printed = "\n".join(call.args[0] for call in mock_print.call_args_list)
    assert "covered seasons   : 2023, 2024" in printed
    assert "uncovered seasons : 2022" in printed
    assert "promotion scope   : covered_only" in printed
    assert "rank_corr delta:  +0.1500" in printed
    assert "weekly_mae delta: -0.750" in printed
    assert "season_mae delta: -1.500" in printed


def test_main_uses_top_level_market_history_coverage_for_promotion_scope():
    validate = _load_validate_module()

    class _FakeFuture:
        def __init__(self, result):
            self._result = result

        def result(self):
            return self._result

    class _FakeProcessPoolExecutor:
        def __init__(self, max_workers):
            self.max_workers = max_workers

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def submit(self, fn, **kwargs):
            return _FakeFuture(fn(**kwargs))

    args = SimpleNamespace(
        baseline="defaults",
        overrides=[],
        sims=50,
        seasons=[2023, 2024],
        scoring="ppr",
        training_years=4,
        positions=["QB"],
        label="market-history-partial-evidence",
        show_ledger=False,
        workers=1,
        no_cache=False,
    )
    defaults = {"scoring": {}}
    coverage_summary = {
        "market_history": SignalCoverage(
            enabled=True,
            status="partial",
            covered_seasons=[2024],
            missing_seasons=[2023],
            note=(
                "Requires player_markets_<season>_<snapshot_label>.parquet plus "
                "rosters_weekly cache to build the crosswalk"
            ),
        ),
        "market_history.crosswalk": SignalCoverage(
            enabled=True,
            status="full",
            covered_seasons=[2023, 2024],
            missing_seasons=[],
            note=None,
        ),
        "market_history.pass_yards": SignalCoverage(
            enabled=True,
            status="full",
            covered_seasons=[2023, 2024],
            missing_seasons=[],
            note=None,
        ),
        "market_history.pass_tds": SignalCoverage(
            enabled=True,
            status="full",
            covered_seasons=[2023, 2024],
            missing_seasons=[],
            note=None,
        ),
        "market_history.rush_yards": SignalCoverage(
            enabled=True,
            status="full",
            covered_seasons=[2023, 2024],
            missing_seasons=[],
            note=None,
        ),
        "market_history.receptions": SignalCoverage(
            enabled=True,
            status="full",
            covered_seasons=[2023, 2024],
            missing_seasons=[],
            note=None,
        ),
        "market_history.receiving_yards": SignalCoverage(
            enabled=True,
            status="full",
            covered_seasons=[2023, 2024],
            missing_seasons=[],
            note=None,
        ),
        "market_history.dispersion": SignalCoverage(
            enabled=True,
            status="full",
            covered_seasons=[2023, 2024],
            missing_seasons=[],
            note=None,
        ),
        "market_history.anytime_td": SignalCoverage(
            enabled=True,
            status="partial",
            covered_seasons=[2024],
            missing_seasons=[2023],
            note=None,
        ),
    }
    season_results = [
        validate.SeasonMetrics(
            test_season=2023,
            arm_a_rank_corr={"QB": 0.40, "RB": 0.40, "WR": 0.40, "TE": 0.40},
            arm_b_rank_corr={"QB": 0.50, "RB": 0.50, "WR": 0.50, "TE": 0.50},
            arm_a_weekly_mae=7.0,
            arm_b_weekly_mae=6.5,
            arm_a_season_mae=30.0,
            arm_b_season_mae=29.0,
            arm_a_calibration=0.1,
            arm_b_calibration=0.1,
        ),
        validate.SeasonMetrics(
            test_season=2024,
            arm_a_rank_corr={"QB": 0.40, "RB": 0.40, "WR": 0.40, "TE": 0.40},
            arm_b_rank_corr={"QB": 0.60, "RB": 0.60, "WR": 0.60, "TE": 0.60},
            arm_a_weekly_mae=7.0,
            arm_b_weekly_mae=6.0,
            arm_a_season_mae=30.0,
            arm_b_season_mae=28.0,
            arm_a_calibration=0.1,
            arm_b_calibration=0.1,
        ),
    ]

    with patch.object(validate, "build_cli", return_value=SimpleNamespace(parse_args=lambda: args)), \
         patch.object(validate, "load_defaults", return_value=defaults), \
         patch.object(validate, "resolve_scoring", return_value={}), \
         patch.object(
             validate,
             "build_engine_configs",
             return_value={"tracking_config": None, "td_tendency_config": object()},
         ), \
         patch.object(validate, "collect_signal_coverage", return_value=coverage_summary, create=True), \
         patch.object(validate, "print_header"), \
         patch.object(validate, "run_season", side_effect=[
             {
                 "season_metrics": season_results[0],
                 "weekly_records": [],
                 "arm_a_projections": None,
                 "arm_a_meta": None,
             },
             {
                 "season_metrics": season_results[1],
                 "weekly_records": [],
                 "arm_a_projections": None,
                 "arm_a_meta": None,
             },
         ]), \
         patch("concurrent.futures.ProcessPoolExecutor", _FakeProcessPoolExecutor), \
         patch("concurrent.futures.as_completed", side_effect=lambda futures: futures), \
         patch.object(validate, "print_season_results"), \
         patch.object(validate, "print_weekly_results", return_value=(None, None)), \
         patch.object(validate, "load_ledger", return_value=[]), \
         patch.object(validate, "save_ledger") as mock_save_ledger, \
         patch.object(validate, "format_ledger_table", return_value="table"), \
         patch.object(validate, "print") as mock_print:
        assert validate.main() == 0

    saved_entries = mock_save_ledger.call_args.args[1]
    entry = saved_entries[0]
    assert entry.promotion_evidence_scope == "covered_only"

    printed = "\n".join(call.args[0] for call in mock_print.call_args_list)
    assert "covered seasons   : 2024" in printed
    assert "uncovered seasons : 2023" in printed
    assert "rank_corr delta:  +0.2000" in printed
    assert "weekly_mae delta: -1.000" in printed
    assert "season_mae delta: -2.000" in printed


def test_print_header_renders_phase_two_coverage_families():
    validate = _load_validate_module()
    args = SimpleNamespace(
        baseline="defaults",
        overrides=[],
        sims=50,
        seasons=[2023, 2024],
        scoring="ppr",
        no_cache=False,
    )
    coverage_summary = {
        "availability": SignalCoverage(
            enabled=True,
            status="partial",
            covered_seasons=[2023],
            missing_seasons=[2024],
            note="Explicit coverage requires rosters_weekly plus depth_charts cache",
        ),
        "availability.injuries": SignalCoverage(
            enabled=True,
            status="none",
            covered_seasons=[],
            missing_seasons=[2023, 2024],
            note="Hard injury availability decisions require cached injuries parquet",
        ),
        "availability.depth_charts": SignalCoverage(
            enabled=True,
            status="partial",
            covered_seasons=[2023],
            missing_seasons=[2024],
            note="Hard starter and promotion decisions require cached depth_charts parquet",
        ),
        "availability.usage_fallback": SignalCoverage(
            enabled=True,
            status="partial",
            covered_seasons=[2023],
            missing_seasons=[2024],
            note="Soft-only fallback requires player_stats_week, snap_counts, and rosters_weekly parquet coverage",
        ),
        "role_trend": SignalCoverage(
            enabled=True,
            status="partial",
            covered_seasons=[2023],
            missing_seasons=[2024],
            note="Role trend uses weekly player_stats coverage",
        ),
    }

    with patch.object(validate, "print") as mock_print:
        validate.print_header(
            args,
            {2023: False, 2024: True},
            comparison_mode="marginal_lift",
            seed_mode="deterministic_game_id_crc32_shared_between_arms",
            coverage_summary=coverage_summary,
        )

    printed = "\n".join(call.args[0] for call in mock_print.call_args_list)
    assert "availability" in printed
    assert "availability.injuries" in printed
    assert "availability.depth_charts" in printed
    assert "availability.usage_fallback" in printed
    assert "role_trend" in printed
    assert "partial" in printed
    assert "none" in printed
    assert "coverage notes" in printed


def test_run_season_computes_distribution_ks_from_matched_rows():
    validate = _load_validate_module()

    build_results = [{
        "status": "ok",
        "game_id": "2024_01_KC_BUF",
        "seed": 7,
        "week": 1,
        "home": "KC",
        "away": "BUF",
        "results": {
            "off": (object(), object(), object(), object()),
            "on": (object(), object(), object(), object()),
        },
    }]
    arm_a_projection = {
        "player_id": "player-1",
        "fpts": 10.0,
        "position": "QB",
        "team": "KC",
        "name": "Patrick Example",
        "pass_yards": 240.0,
        "rush_yards": 12.0,
    }
    arm_b_projection = {
        "player_id": "player-1",
        "fpts": 14.0,
        "position": "QB",
        "team": "KC",
        "name": "Patrick Example",
        "pass_yards": 300.0,
        "rush_yards": 18.0,
    }
    actual = SimpleNamespace(
        player_id="player-1",
        week=1,
        fpts=14.0,
        position="QB",
        team="KC",
        name="Patrick Example",
        pass_yards=300.0,
        rush_yards=18.0,
    )

    with patch.object(validate, "build_games_parallel", return_value=build_results), \
         patch.object(
             validate,
             "simulate_games_parallel",
             return_value=[
                 SimpleNamespace(
                     game_id="2024_01_KC_BUF",
                     metadata={"arm": "a"},
                     projections=[arm_a_projection],
                 ),
                 SimpleNamespace(
                     game_id="2024_01_KC_BUF",
                     metadata={"arm": "b"},
                     projections=[arm_b_projection],
                 ),
             ],
         ), \
         patch.object(validate, "load_actual_scores", return_value=[actual]), \
         patch.object(validate, "DataLoader") as mock_loader_cls:
        mock_loader = mock_loader_cls.return_value
        mock_loader.cache_dir = Path("/tmp/test-cache")
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

        result = validate.run_season(
            test_season=2024,
            n_sims=10,
            scoring_config={},
            num_training_seasons=3,
            arm_a_configs={
                "pff_config": None,
                "weather_config": None,
                "vegas_config": None,
                "props_config": None,
                "usage_config": None,
                "tracking_config": None,
                "game_script_config": None,
                "goal_line_concentration_config": None,
                "td_tendency_config": None,
            },
            arm_b_configs={
                "pff_config": None,
                "weather_config": None,
                "vegas_config": None,
                "props_config": None,
                "usage_config": None,
                "tracking_config": None,
                "game_script_config": None,
                "goal_line_concentration_config": None,
                "td_tendency_config": None,
            },
            positions=["QB"],
            max_workers=1,
        )

    season_metrics = result["season_metrics"]
    assert season_metrics.weekly_fpts_ks["arm_a_ks"] == 1.0
    assert season_metrics.weekly_fpts_ks["arm_b_ks"] == 0.0
    assert season_metrics.weekly_fpts_ks["ks_delta"] == -1.0
    assert season_metrics.weekly_fpts_ks["n"] == 1
    assert season_metrics.stat_ks["QB"]["pass_yards"]["arm_a_ks"] == 1.0
    assert season_metrics.stat_ks["QB"]["pass_yards"]["arm_b_mean"] == 300.0
    assert season_metrics.stat_ks["QB"]["pass_yards"]["mean_delta_b"] == 0.0
    assert result["arm_a_projection_rows"]["player-1"][1]["pass_yards"] == 240.0


def test_store_projection_row_rejects_invalid_fpts():
    validate = _load_validate_module()
    projection = {
        "player_id": "player-1",
        "fpts": float("nan"),
        "position": "QB",
        "team": "KC",
        "name": "Patrick Example",
    }

    with pytest.raises(ValueError, match="Invalid projection fpts"):
        validate._store_projection_row(
            projection,
            1,
            {},
            {},
            {},
            {},
            {},
            {},
        )


def test_run_season_blends_arm_b_with_ensemble_when_enabled():
    validate = _load_validate_module()
    from fantasy_sim.data.ensemble.models import EnsembleConfig, FfOpportunityConfig

    build_a = [{
        "status": "ok",
        "game_id": "2024_01_KC_BUF",
        "seed": 7,
        "week": 1,
        "home": "KC",
        "away": "BUF",
        "home_dists": object(),
        "away_dists": object(),
        "home_roster": object(),
        "away_roster": object(),
    }]
    build_b = [{
        "status": "ok",
        "game_id": "2024_01_KC_BUF",
        "seed": 7,
        "week": 1,
        "home": "KC",
        "away": "BUF",
        "home_dists": object(),
        "away_dists": object(),
        "home_roster": object(),
        "away_roster": object(),
    }]
    arm_a_projection = {
        "player_id": "player-1",
        "fpts": 10.0,
        "position": "QB",
        "team": "KC",
        "name": "Patrick Example",
    }
    arm_b_projection = {
        "player_id": "player-1",
        "fpts": 12.0,
        "position": "QB",
        "team": "KC",
        "name": "Patrick Example",
    }
    actual = SimpleNamespace(
        player_id="player-1",
        week=1,
        fpts=13.5,
        position="QB",
        team="KC",
        name="Patrick Example",
    )

    with patch.object(validate, "build_games_parallel", side_effect=[build_a, build_b]), \
         patch.object(
             validate,
             "simulate_games_parallel",
             return_value=[
                 SimpleNamespace(
                     game_id="2024_01_KC_BUF",
                     metadata={"arm": "a"},
                     projections=[arm_a_projection],
                 ),
                 SimpleNamespace(
                     game_id="2024_01_KC_BUF",
                     metadata={"arm": "b"},
                     projections=[arm_b_projection],
                 ),
             ],
         ), \
         patch.object(validate, "FfOpportunityProjectionEnsembler") as mock_ensembler_cls, \
         patch.object(validate, "load_actual_scores", return_value=[actual]), \
         patch.object(validate, "DataLoader") as mock_loader_cls:
        mock_ensembler = mock_ensembler_cls.return_value
        mock_ensembler.blend_week.return_value = (
            [dict(arm_b_projection, fpts=13.5)],
            SimpleNamespace(total_rows=1, covered_rows=1, uncovered_rows=0),
        )

        mock_loader = mock_loader_cls.return_value
        mock_loader.cache_dir = Path("/tmp/test-cache")
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

        result = validate.run_season(
            test_season=2024,
            n_sims=10,
            scoring_config={},
            num_training_seasons=3,
            arm_a_configs={
                "pff_config": object(),
                "weather_config": None,
                "vegas_config": None,
                "props_config": None,
                "usage_config": None,
                "tracking_config": None,
                "game_script_config": None,
                "goal_line_concentration_config": None,
                "td_tendency_config": None,
            },
            arm_b_configs={
                "pff_config": object(),
                "weather_config": None,
                "vegas_config": None,
                "props_config": None,
                "usage_config": None,
                "tracking_config": None,
                "game_script_config": None,
                "goal_line_concentration_config": None,
                "td_tendency_config": None,
            },
            arm_a_ensemble_config=None,
            arm_b_ensemble_config=EnsembleConfig(
                enabled=True,
                ff_opportunity=FfOpportunityConfig(enabled=True),
            ),
            positions=["QB"],
            max_workers=1,
        )

    mock_ensembler_cls.assert_called_once()
    mock_ensembler.blend_week.assert_called_once_with(
        [arm_b_projection],
        season=2024,
        week=1,
    )
    assert result["season_metrics"].arm_a_weekly_mae == 3.5
    assert result["season_metrics"].arm_b_weekly_mae == 0.0
    assert result["weekly_records"][0].projected_fpts_on == 13.5


def test_run_season_blends_arm_b_with_ensemble_in_cached_arm_a_path():
    validate = _load_validate_module()
    from fantasy_sim.data.ensemble.models import EnsembleConfig, FfOpportunityConfig

    build_b = [{
        "status": "ok",
        "game_id": "2024_01_KC_BUF",
        "seed": 7,
        "week": 1,
        "home": "KC",
        "away": "BUF",
        "home_dists": object(),
        "away_dists": object(),
        "home_roster": object(),
        "away_roster": object(),
    }]
    arm_b_projection = {
        "player_id": "player-1",
        "fpts": 12.0,
        "position": "QB",
        "team": "KC",
        "name": "Patrick Example",
    }
    actual = SimpleNamespace(
        player_id="player-1",
        week=1,
        fpts=13.5,
        position="QB",
        team="KC",
        name="Patrick Example",
    )
    cached_arm_a = {
        "projections": {"player-1": {1: 10.0}},
        "player_meta": {
            "player-1": {
                "position": "QB",
                "team": "KC",
                "name": "Patrick Example",
            }
        },
    }

    with patch.object(validate, "build_games_parallel", return_value=build_b), \
         patch.object(
             validate,
             "simulate_games_parallel",
             return_value=[
                 SimpleNamespace(
                     game_id="2024_01_KC_BUF",
                     metadata={},
                     projections=[arm_b_projection],
                 )
             ],
         ), \
         patch.object(validate, "FfOpportunityProjectionEnsembler") as mock_ensembler_cls, \
         patch.object(validate, "load_actual_scores", return_value=[actual]), \
         patch.object(validate, "DataLoader") as mock_loader_cls:
        mock_ensembler = mock_ensembler_cls.return_value
        mock_ensembler.blend_week.return_value = (
            [dict(arm_b_projection, fpts=13.5)],
            SimpleNamespace(total_rows=1, covered_rows=1, uncovered_rows=0),
        )

        mock_loader = mock_loader_cls.return_value
        mock_loader.cache_dir = Path("/tmp/test-cache")
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

        result = validate.run_season(
            test_season=2024,
            n_sims=10,
            scoring_config={},
            num_training_seasons=3,
            arm_a_configs={
                "pff_config": None,
                "weather_config": None,
                "vegas_config": None,
                "props_config": None,
                "usage_config": None,
                "tracking_config": None,
                "game_script_config": None,
                "goal_line_concentration_config": None,
                "td_tendency_config": None,
            },
            arm_b_configs={
                "pff_config": object(),
                "weather_config": None,
                "vegas_config": None,
                "props_config": None,
                "usage_config": None,
                "tracking_config": None,
                "game_script_config": None,
                "goal_line_concentration_config": None,
                "td_tendency_config": None,
            },
            arm_a_ensemble_config=None,
            arm_b_ensemble_config=EnsembleConfig(
                enabled=True,
                ff_opportunity=FfOpportunityConfig(enabled=True),
            ),
            positions=["QB"],
            max_workers=1,
            cached_arm_a=cached_arm_a,
        )

    mock_ensembler_cls.assert_called_once()
    mock_ensembler.blend_week.assert_called_once_with(
        [arm_b_projection],
        season=2024,
        week=1,
    )
    assert result["season_metrics"].arm_b_weekly_mae == 0.0
    assert result["weekly_records"][0].projected_fpts_off == 10.0
    assert result["weekly_records"][0].projected_fpts_on == 13.5


def test_run_season_dynamic_blend_suppresses_fixed_market_and_ensemble_layers():
    validate = _load_validate_module()
    from fantasy_sim.data.ensemble.models import (
        DynamicBlendConfig,
        EnsembleConfig,
        FfOpportunityConfig,
    )
    from fantasy_sim.data.market_history.models import MarketHistoryConfig

    build_b = [{
        "status": "ok",
        "game_id": "2024_01_KC_BUF",
        "seed": 7,
        "week": 1,
        "home": "KC",
        "away": "BUF",
        "home_dists": object(),
        "away_dists": object(),
        "home_roster": object(),
        "away_roster": object(),
    }]
    arm_b_projection = {
        "player_id": "player-1",
        "fpts": 12.0,
        "position": "QB",
        "team": "KC",
        "name": "Patrick Example",
    }
    actual = SimpleNamespace(
        player_id="player-1",
        week=1,
        fpts=13.5,
        position="QB",
        team="KC",
        name="Patrick Example",
    )
    cached_arm_a = {
        "projections": {"player-1": {1: 10.0}},
        "player_meta": {
            "player-1": {
                "position": "QB",
                "team": "KC",
                "name": "Patrick Example",
            }
        },
    }

    with patch.object(validate, "build_games_parallel", return_value=build_b), \
         patch.object(
             validate,
             "simulate_games_parallel",
             return_value=[
                 SimpleNamespace(
                     game_id="2024_01_KC_BUF",
                     metadata={},
                     projections=[arm_b_projection],
                 )
             ],
         ), \
         patch.object(validate, "DynamicBlendProjectionBlender") as mock_dynamic_cls, \
         patch.object(validate, "FfOpportunityProjectionEnsembler") as mock_ensembler_cls, \
         patch.object(validate, "MarketHistoryProjectionAdjuster") as mock_market_cls, \
         patch.object(validate, "load_actual_scores", return_value=[actual]), \
         patch.object(validate, "DataLoader") as mock_loader_cls:
        mock_dynamic = mock_dynamic_cls.return_value
        mock_dynamic.blend_week.return_value = (
            [dict(arm_b_projection, fpts=13.5)],
            SimpleNamespace(total_rows=1, learned_rows=1, fallback_rows=0),
        )

        mock_loader = mock_loader_cls.return_value
        mock_loader.cache_dir = Path("/tmp/test-cache")
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

        result = validate.run_season(
            test_season=2024,
            n_sims=10,
            scoring_config={},
            num_training_seasons=3,
            arm_a_configs={
                "pff_config": None,
                "weather_config": None,
                "vegas_config": None,
                "props_config": None,
                "usage_config": None,
                "tracking_config": None,
                "game_script_config": None,
                "goal_line_concentration_config": None,
                "td_tendency_config": None,
                "market_history_config": None,
            },
            arm_b_configs={
                "pff_config": object(),
                "weather_config": None,
                "vegas_config": None,
                "props_config": None,
                "usage_config": None,
                "tracking_config": None,
                "game_script_config": None,
                "goal_line_concentration_config": None,
                "td_tendency_config": None,
                "market_history_config": MarketHistoryConfig(enabled=True),
            },
            arm_a_ensemble_config=None,
            arm_b_ensemble_config=EnsembleConfig(
                enabled=True,
                ff_opportunity=FfOpportunityConfig(enabled=True),
                dynamic_blend=DynamicBlendConfig(enabled=True),
            ),
            positions=["QB"],
            max_workers=1,
            cached_arm_a=cached_arm_a,
        )

    mock_dynamic_cls.assert_called_once()
    mock_dynamic.blend_week.assert_called_once_with(
        [arm_b_projection],
        season=2024,
        week=1,
    )
    mock_ensembler_cls.assert_not_called()
    mock_market_cls.assert_not_called()
    assert result["season_metrics"].arm_b_weekly_mae == 0.0
    assert result["weekly_records"][0].projected_fpts_on == 13.5


def test_run_season_residual_calibration_runs_after_dynamic_blend():
    validate = _load_validate_module()
    from fantasy_sim.data.ensemble.models import (
        DynamicBlendConfig,
        EnsembleConfig,
        FfOpportunityConfig,
        ResidualCalibrationConfig,
    )
    from fantasy_sim.data.market_history.models import MarketHistoryConfig

    build_b = [{
        "status": "ok",
        "game_id": "2024_01_KC_BUF",
        "seed": 7,
        "week": 1,
        "home": "KC",
        "away": "BUF",
        "home_dists": object(),
        "away_dists": object(),
        "home_roster": object(),
        "away_roster": object(),
    }]
    arm_b_projection = {
        "player_id": "player-1",
        "fpts": 12.0,
        "position": "QB",
        "team": "KC",
        "name": "Patrick Example",
    }
    dynamic_projection = dict(arm_b_projection, fpts=13.0)
    calibrated_projection = dict(arm_b_projection, fpts=14.0)
    actual = SimpleNamespace(
        player_id="player-1",
        week=1,
        fpts=14.0,
        position="QB",
        team="KC",
        name="Patrick Example",
    )
    cached_arm_a = {
        "projections": {"player-1": {1: 10.0}},
        "player_meta": {
            "player-1": {
                "position": "QB",
                "team": "KC",
                "name": "Patrick Example",
            }
        },
    }

    with patch.object(validate, "build_games_parallel", return_value=build_b), \
         patch.object(
             validate,
             "simulate_games_parallel",
             return_value=[
                 SimpleNamespace(
                     game_id="2024_01_KC_BUF",
                     metadata={},
                     projections=[arm_b_projection],
                 )
             ],
         ), \
         patch.object(validate, "DynamicBlendProjectionBlender") as mock_dynamic_cls, \
         patch.object(validate, "ResidualCalibrationProjectionAdjuster") as mock_residual_cls, \
         patch.object(validate, "FfOpportunityProjectionEnsembler") as mock_ensembler_cls, \
         patch.object(validate, "MarketHistoryProjectionAdjuster") as mock_market_cls, \
         patch.object(validate, "load_actual_scores", return_value=[actual]), \
         patch.object(validate, "DataLoader") as mock_loader_cls:
        mock_dynamic = mock_dynamic_cls.return_value
        mock_dynamic.blend_week.return_value = (
            [dynamic_projection],
            SimpleNamespace(total_rows=1, learned_rows=1, fallback_rows=0),
        )
        mock_residual = mock_residual_cls.return_value
        mock_residual.adjust_week.return_value = (
            [calibrated_projection],
            SimpleNamespace(total_rows=1, adjusted_rows=1, fallback_rows=0),
        )

        mock_loader = mock_loader_cls.return_value
        mock_loader.cache_dir = Path("/tmp/test-cache")
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

        result = validate.run_season(
            test_season=2024,
            n_sims=10,
            scoring_config={},
            num_training_seasons=3,
            arm_a_configs={
                "pff_config": None,
                "weather_config": None,
                "vegas_config": None,
                "props_config": None,
                "usage_config": None,
                "tracking_config": None,
                "game_script_config": None,
                "goal_line_concentration_config": None,
                "td_tendency_config": None,
                "market_history_config": None,
            },
            arm_b_configs={
                "pff_config": object(),
                "weather_config": None,
                "vegas_config": None,
                "props_config": None,
                "usage_config": None,
                "tracking_config": None,
                "game_script_config": None,
                "goal_line_concentration_config": None,
                "td_tendency_config": None,
                "market_history_config": MarketHistoryConfig(enabled=True),
            },
            arm_a_ensemble_config=None,
            arm_b_ensemble_config=EnsembleConfig(
                enabled=True,
                ff_opportunity=FfOpportunityConfig(enabled=True),
                dynamic_blend=DynamicBlendConfig(enabled=True),
                residual_calibration=ResidualCalibrationConfig(enabled=True),
            ),
            positions=["QB"],
            max_workers=1,
            cached_arm_a=cached_arm_a,
        )

    mock_dynamic.blend_week.assert_called_once_with(
        [arm_b_projection],
        season=2024,
        week=1,
    )
    mock_residual.adjust_week.assert_called_once_with(
        [dynamic_projection],
        season=2024,
        week=1,
    )
    mock_ensembler_cls.assert_not_called()
    mock_market_cls.assert_not_called()
    assert result["season_metrics"].arm_b_weekly_mae == 0.0
    assert result["weekly_records"][0].projected_fpts_on == 14.0


def test_run_season_skips_ensembler_when_ff_opportunity_subsignal_is_disabled():
    validate = _load_validate_module()

    with patch.object(validate, "simulate_games_parallel", return_value=[]), \
         patch.object(validate, "build_games_parallel", return_value=[]), \
         patch.object(validate, "load_actual_scores", return_value=[]), \
         patch.object(validate, "FfOpportunityProjectionEnsembler") as mock_ensembler_cls, \
         patch.object(validate, "DataLoader") as mock_loader_cls:
        mock_loader = mock_loader_cls.return_value
        mock_loader.cache_dir = Path("/tmp/test-cache")
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

        from fantasy_sim.data.ensemble.models import EnsembleConfig, FfOpportunityConfig

        validate.run_season(
            test_season=2024,
            n_sims=10,
            scoring_config={},
            num_training_seasons=3,
            arm_a_configs={
                "pff_config": object(),
                "weather_config": None,
                "vegas_config": None,
                "props_config": None,
                "usage_config": None,
                "tracking_config": None,
                "game_script_config": None,
                "goal_line_concentration_config": None,
                "td_tendency_config": None,
            },
            arm_b_configs={
                "pff_config": object(),
                "weather_config": None,
                "vegas_config": None,
                "props_config": None,
                "usage_config": None,
                "tracking_config": None,
                "game_script_config": None,
                "goal_line_concentration_config": None,
                "td_tendency_config": None,
            },
            arm_a_ensemble_config=None,
            arm_b_ensemble_config=EnsembleConfig(
                enabled=True,
                ff_opportunity=FfOpportunityConfig(enabled=False),
            ),
            positions=["QB"],
            max_workers=1,
        )

    mock_ensembler_cls.assert_not_called()


def test_main_records_schema_metadata_and_coverage_summary_for_defaults_baseline():
    validate = _load_validate_module()
    args = SimpleNamespace(
        baseline="defaults",
        overrides=[],
        sims=50,
        seasons=[2024],
        scoring="ppr",
        training_years=4,
        positions=["QB"],
        label="baseline-defaults",
        show_ledger=False,
        workers=1,
        no_cache=False,
    )
    defaults = {"scoring": {}}
    coverage_summary = {
        "market_history": SignalCoverage(
            enabled=True,
            status="partial",
            covered_seasons=[2024],
            missing_seasons=[],
            note="Requires processed season parquet at ~/.fantasy-sim/market-history/processed",
        ),
        "pff": SignalCoverage(
            enabled=True,
            status="full",
            covered_seasons=[2024],
            missing_seasons=[],
            note=None,
        )
    }
    season_result = validate.SeasonMetrics(
        test_season=2024,
        arm_a_rank_corr={"QB": 0.40, "RB": 0.40, "WR": 0.40, "TE": 0.40},
        arm_b_rank_corr={"QB": 0.50, "RB": 0.50, "WR": 0.50, "TE": 0.50},
        arm_a_weekly_mae=7.0,
        arm_b_weekly_mae=6.5,
        arm_a_season_mae=30.0,
        arm_b_season_mae=29.0,
        arm_a_calibration=0.1,
        arm_b_calibration=0.1,
    )

    with patch.object(validate, "build_cli", return_value=SimpleNamespace(parse_args=lambda: args)), \
         patch.object(validate, "load_defaults", return_value=defaults), \
         patch.object(validate, "resolve_scoring", return_value={}), \
         patch.object(
             validate,
             "build_engine_configs",
             return_value={"tracking_config": None, "td_tendency_config": object()},
         ), \
         patch.object(validate, "collect_signal_coverage", return_value=coverage_summary, create=True) as mock_collect_signal_coverage, \
         patch.object(validate, "print_header") as mock_print_header, \
         patch.object(validate, "run_season", return_value={
             "season_metrics": season_result,
             "weekly_records": [],
             "arm_a_projections": None,
             "arm_a_meta": None,
         }), \
         patch.object(validate, "print_season_results"), \
         patch.object(validate, "print_weekly_results", return_value=(None, None)), \
         patch.object(validate, "load_ledger", return_value=[]), \
         patch.object(validate, "save_ledger") as mock_save_ledger, \
         patch.object(validate, "format_ledger_table", return_value="table"), \
         patch.object(validate, "print"):
        assert validate.main() == 0

    mock_collect_signal_coverage.assert_called_once_with(defaults, [2024])
    mock_print_header.assert_called_once()
    assert mock_print_header.call_args.args[0] is args
    assert mock_print_header.call_args.kwargs["comparison_mode"] == "marginal_lift"
    assert mock_print_header.call_args.kwargs["seed_mode"] == "deterministic_game_id_crc32_shared_between_arms"
    assert mock_print_header.call_args.kwargs["coverage_summary"] is coverage_summary

    saved_entries = mock_save_ledger.call_args.args[1]
    entry = saved_entries[0]
    assert entry.sims == args.sims
    assert entry.schema_version == validate.CURRENT_LEDGER_SCHEMA_VERSION
    assert entry.comparison_mode == "marginal_lift"
    assert entry.seed_mode == "deterministic_game_id_crc32_shared_between_arms"
    assert entry.promotion_evidence_scope == "covered_only"
    assert entry.coverage_summary is coverage_summary

"""Focused regression tests for scripts/validate.py plumbing."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import patch

import polars as pl


def _load_validate_module():
    validate_path = Path(__file__).resolve().parents[2] / "scripts" / "validate.py"
    spec = importlib.util.spec_from_file_location("validate_script_under_test", validate_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
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
            "game_script_config": None,
            "td_tendency_config": None,
        }
        arm_b_configs = {
            "pff_config": None,
            "weather_config": None,
            "vegas_config": None,
            "props_config": None,
            "usage_config": None,
            "game_script_config": game_script_config,
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

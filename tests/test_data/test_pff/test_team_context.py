"""Tests for the PFF team context engine."""

import pytest
import numpy as np
import polars as pl
from unittest.mock import MagicMock

from fantasy_sim.data.pff.models import TeamContext, TeamContextConfig
from fantasy_sim.data.pff.team_context import TeamContextEngine


# ---------------------------------------------------------------------------
# PBP / OL / QB data builders shared across test classes
# ---------------------------------------------------------------------------

def _make_pbp(teams_data: dict[str, dict[str, int]], season: int, week: int) -> pl.DataFrame:
    """Build a minimal PBP DataFrame for testing."""
    rows = []
    game_idx = 0
    for team, counts in teams_data.items():
        game_idx += 1
        for _ in range(counts.get("pass", 0)):
            rows.append({"play_type": "pass", "posteam": team, "season": season, "week": week, "game_id": f"game_{game_idx}"})
        for _ in range(counts.get("run", 0)):
            rows.append({"play_type": "run", "posteam": team, "season": season, "week": week, "game_id": f"game_{game_idx}"})
    return pl.DataFrame(rows)


def _make_ol_data(teams: dict[str, list[tuple[float, int]]], season: int, week: int) -> pl.DataFrame:
    """Build mock offense_run_blocking data. teams: {team: [(grade, snap_count), ...]}"""
    rows = []
    pid = 100
    for team, linemen in teams.items():
        for grade, snaps in linemen:
            pid += 1
            rows.append({
                "player_id": pid, "player": f"OL_{pid}", "team": team,
                "position": "T", "grades_run_block": grade,
                "snap_counts_run_block": snaps,
                "season": season, "week": week, "game_id": f"game_{team}_{week}",
            })
    return pl.DataFrame(rows)


def _make_qb_data(teams: dict[str, list[tuple[float, int]]], season: int, week: int) -> pl.DataFrame:
    """Build mock passing_summary data. teams: {team: [(grade, passing_snaps), ...]}"""
    rows = []
    pid = 200
    for team, qbs in teams.items():
        for grade, snaps in qbs:
            pid += 1
            rows.append({
                "player_id": pid, "player": f"QB_{pid}", "team": team,
                "position": "QB", "grades_pass": grade,
                "passing_snaps": snaps,
                "season": season, "week": week, "game_id": f"game_{team}_{week}",
            })
    return pl.DataFrame(rows)


class TestTeamContextDataModel:
    def test_team_context_defaults(self):
        """All factors default to 1.0 (neutral), scale defaults to 10.0."""
        ctx = TeamContext()
        assert ctx.pass_rate_factor == 1.0
        assert ctx.ol_run_block_factor == 1.0
        assert ctx.qb_quality_factor == 1.0
        assert ctx.ol_run_yards_scale == 10.0

    def test_team_context_custom_values(self):
        """TeamContext can be constructed with custom factor values."""
        ctx = TeamContext(
            pass_rate_factor=1.08,
            ol_run_block_factor=0.94,
            qb_quality_factor=1.05,
            ol_run_yards_scale=12.0,
        )
        assert ctx.pass_rate_factor == 1.08
        assert ctx.ol_run_block_factor == 0.94
        assert ctx.qb_quality_factor == 1.05
        assert ctx.ol_run_yards_scale == 12.0

    def test_team_context_config_defaults(self):
        """TeamContextConfig has correct default values."""
        cfg = TeamContextConfig()
        assert cfg.enabled is True
        assert cfg.pass_rate_sensitivity == 0.08
        assert cfg.ol_run_sensitivity == 0.06
        assert cfg.qb_quality_sensitivity == 0.05
        assert cfg.factor_clamp == (0.90, 1.10)
        assert cfg.min_games == 4
        assert cfg.ol_run_yards_scale == 10.0

    def test_team_context_config_custom(self):
        """TeamContextConfig can be constructed with custom values."""
        cfg = TeamContextConfig(
            enabled=False,
            pass_rate_sensitivity=0.10,
            factor_clamp=(0.85, 1.15),
        )
        assert cfg.enabled is False
        assert cfg.pass_rate_sensitivity == 0.10
        assert cfg.factor_clamp == (0.85, 1.15)


# ---------------------------------------------------------------------------
# Task 4: Pass Rate Factor
# ---------------------------------------------------------------------------

class TestPassRateFactor:
    def _make_engine(self, **config_overrides) -> TeamContextEngine:
        cfg = TeamContextConfig(**config_overrides)
        return TeamContextEngine(config=cfg, pff_loader=MagicMock())

    def test_pass_heavy_team_above_one(self):
        engine = self._make_engine()
        pbp = _make_pbp({"KC": {"pass": 70, "run": 30}, "BUF": {"pass": 55, "run": 45}, "BAL": {"pass": 45, "run": 55}}, season=2024, week=5)
        factor = engine._compute_pass_rate_factor("KC", 2024, 6, pbp)
        assert factor > 1.0

    def test_run_heavy_team_below_one(self):
        engine = self._make_engine()
        pbp = _make_pbp({"KC": {"pass": 70, "run": 30}, "BUF": {"pass": 55, "run": 45}, "BAL": {"pass": 45, "run": 55}}, season=2024, week=5)
        factor = engine._compute_pass_rate_factor("BAL", 2024, 6, pbp)
        assert factor < 1.0

    def test_average_team_near_one(self):
        engine = self._make_engine()
        pbp = _make_pbp({"KC": {"pass": 70, "run": 30}, "BUF": {"pass": 57, "run": 43}, "BAL": {"pass": 45, "run": 55}}, season=2024, week=5)
        factor = engine._compute_pass_rate_factor("BUF", 2024, 6, pbp)
        assert 0.98 <= factor <= 1.02

    def test_factor_clamped_to_range(self):
        engine = self._make_engine(factor_clamp=(0.90, 1.10))
        pbp = _make_pbp({"KC": {"pass": 95, "run": 5}, "BUF": {"pass": 30, "run": 70}, "BAL": {"pass": 30, "run": 70}}, season=2024, week=5)
        factor = engine._compute_pass_rate_factor("KC", 2024, 6, pbp)
        assert factor <= 1.10

    def test_week_filter_applied(self):
        engine = self._make_engine()
        pbp_w5 = _make_pbp({"KC": {"pass": 70, "run": 30}, "BUF": {"pass": 50, "run": 50}}, season=2024, week=5)
        pbp_w8 = _make_pbp({"KC": {"pass": 20, "run": 80}, "BUF": {"pass": 50, "run": 50}}, season=2024, week=8)
        pbp = pl.concat([pbp_w5, pbp_w8])
        factor = engine._compute_pass_rate_factor("KC", 2024, 6, pbp)
        assert factor > 1.0

    def test_missing_team_returns_neutral(self):
        engine = self._make_engine()
        pbp = _make_pbp({"KC": {"pass": 50, "run": 50}, "BUF": {"pass": 50, "run": 50}}, season=2024, week=5)
        factor = engine._compute_pass_rate_factor("NYG", 2024, 6, pbp)
        assert factor == 1.0

    def test_empty_pbp_returns_neutral(self):
        engine = self._make_engine()
        factor = engine._compute_pass_rate_factor("KC", 2024, 6, pl.DataFrame())
        assert factor == 1.0

    def test_none_pbp_returns_neutral(self):
        engine = self._make_engine()
        factor = engine._compute_pass_rate_factor("KC", 2024, 6, None)
        assert factor == 1.0


# ---------------------------------------------------------------------------
# Task 5: OL Run Blocking Factor
# ---------------------------------------------------------------------------

class TestOlRunBlockFactor:
    def _make_engine(self, **config_overrides) -> TeamContextEngine:
        mock_loader = MagicMock()
        mock_loader.load_facet = MagicMock(return_value=pl.DataFrame())
        cfg = TeamContextConfig(**config_overrides)
        return TeamContextEngine(config=cfg, pff_loader=mock_loader)

    def _engine_with_ol_data(self, ol_data: pl.DataFrame, **config_overrides) -> TeamContextEngine:
        mock_loader = MagicMock()
        mock_loader.load_facet = MagicMock(return_value=ol_data)
        cfg = TeamContextConfig(**config_overrides)
        return TeamContextEngine(config=cfg, pff_loader=mock_loader)

    def test_good_ol_above_one(self):
        ol_data = _make_ol_data({"KC": [(80.0, 50), (78.0, 50)], "BUF": [(60.0, 50), (58.0, 50)], "BAL": [(50.0, 50), (48.0, 50)]}, season=2024, week=5)
        engine = self._engine_with_ol_data(ol_data)
        factor = engine._compute_ol_run_factor("KC", 2024, 6)
        assert factor > 1.0

    def test_bad_ol_below_one(self):
        ol_data = _make_ol_data({"KC": [(80.0, 50), (78.0, 50)], "BUF": [(60.0, 50), (58.0, 50)], "BAL": [(50.0, 50), (48.0, 50)]}, season=2024, week=5)
        engine = self._engine_with_ol_data(ol_data)
        factor = engine._compute_ol_run_factor("BAL", 2024, 6)
        assert factor < 1.0

    def test_snap_weighting(self):
        ol_good_starter = _make_ol_data({"KC": [(85.0, 90), (40.0, 10)], "BUF": [(60.0, 50), (60.0, 50)]}, season=2024, week=5)
        engine = self._engine_with_ol_data(ol_good_starter)
        factor = engine._compute_ol_run_factor("KC", 2024, 6)
        assert factor > 1.0

    def test_empty_pff_data_returns_neutral(self):
        engine = self._make_engine()
        factor = engine._compute_ol_run_factor("KC", 2024, 6)
        assert factor == 1.0

    def test_team_not_in_data_returns_neutral(self):
        ol_data = _make_ol_data({"KC": [(70.0, 50)], "BUF": [(60.0, 50)]}, season=2024, week=5)
        engine = self._engine_with_ol_data(ol_data)
        factor = engine._compute_ol_run_factor("NYG", 2024, 6)
        assert factor == 1.0


# ---------------------------------------------------------------------------
# Task 6: QB Quality Factor + Full compute()
# ---------------------------------------------------------------------------

class TestQbQualityFactor:
    def _engine_with_qb_data(self, qb_data: pl.DataFrame, **config_overrides) -> TeamContextEngine:
        mock_loader = MagicMock()
        mock_loader.load_facet = MagicMock(return_value=qb_data)
        cfg = TeamContextConfig(**config_overrides)
        return TeamContextEngine(config=cfg, pff_loader=mock_loader)

    def test_elite_qb_above_one(self):
        qb_data = _make_qb_data({"KC": [(90.0, 60)], "BUF": [(70.0, 60)], "BAL": [(55.0, 60)]}, season=2024, week=5)
        engine = self._engine_with_qb_data(qb_data)
        factor = engine._compute_qb_quality_factor("KC", 2024, 6)
        assert factor > 1.0

    def test_poor_qb_below_one(self):
        qb_data = _make_qb_data({"KC": [(90.0, 60)], "BUF": [(70.0, 60)], "BAL": [(55.0, 60)]}, season=2024, week=5)
        engine = self._engine_with_qb_data(qb_data)
        factor = engine._compute_qb_quality_factor("BAL", 2024, 6)
        assert factor < 1.0

    def test_snap_weighting_favors_starter(self):
        qb_data = _make_qb_data({"KC": [(85.0, 570), (45.0, 30)], "BUF": [(70.0, 600)]}, season=2024, week=5)
        engine = self._engine_with_qb_data(qb_data)
        factor = engine._compute_qb_quality_factor("KC", 2024, 6)
        assert factor > 1.0

    def test_empty_data_returns_neutral(self):
        mock_loader = MagicMock()
        mock_loader.load_facet = MagicMock(return_value=pl.DataFrame())
        engine = TeamContextEngine(config=TeamContextConfig(), pff_loader=mock_loader)
        factor = engine._compute_qb_quality_factor("KC", 2024, 6)
        assert factor == 1.0


# ---------------------------------------------------------------------------
# Task 7: Early-Season Blend Tests
# ---------------------------------------------------------------------------

class TestEarlySeasonBlend:
    def test_pass_rate_blends_with_previous_season(self):
        engine = TeamContextEngine(config=TeamContextConfig(min_games=4), pff_loader=MagicMock())
        prev = _make_pbp({"KC": {"pass": 80, "run": 20}, "BUF": {"pass": 50, "run": 50}, "BAL": {"pass": 50, "run": 50}}, season=2023, week=10)
        current_w1 = _make_pbp({"KC": {"pass": 50, "run": 50}, "BUF": {"pass": 50, "run": 50}, "BAL": {"pass": 50, "run": 50}}, season=2024, week=1)
        current_w2 = _make_pbp({"KC": {"pass": 50, "run": 50}, "BUF": {"pass": 50, "run": 50}, "BAL": {"pass": 50, "run": 50}}, season=2024, week=2)
        pbp = pl.concat([prev, current_w1, current_w2])
        factor = engine._compute_pass_rate_factor("KC", 2024, 3, pbp)
        assert factor > 1.0

    def test_zero_current_games_uses_previous_only(self):
        engine = TeamContextEngine(config=TeamContextConfig(min_games=4), pff_loader=MagicMock())
        prev = _make_pbp({"KC": {"pass": 80, "run": 20}, "BUF": {"pass": 50, "run": 50}, "BAL": {"pass": 50, "run": 50}}, season=2023, week=10)
        factor = engine._compute_pass_rate_factor("KC", 2024, 1, prev)
        assert factor > 1.0

    def test_enough_games_skips_blend(self):
        engine = TeamContextEngine(config=TeamContextConfig(min_games=2), pff_loader=MagicMock())
        prev = _make_pbp({"KC": {"pass": 30, "run": 70}, "BUF": {"pass": 50, "run": 50}, "BAL": {"pass": 50, "run": 50}}, season=2023, week=10)
        games = [_make_pbp({"KC": {"pass": 70, "run": 30}, "BUF": {"pass": 50, "run": 50}, "BAL": {"pass": 50, "run": 50}}, season=2024, week=w) for w in [1, 2, 3]]
        pbp = pl.concat([prev] + games)
        factor = engine._compute_pass_rate_factor("KC", 2024, 4, pbp)
        assert factor > 1.0

    def test_disabled_engine_returns_neutral(self):
        engine = TeamContextEngine(config=TeamContextConfig(enabled=False), pff_loader=MagicMock())
        ctx = engine.compute("KC", 2024, 8, pbp=pl.DataFrame())
        assert ctx.pass_rate_factor == 1.0
        assert ctx.ol_run_block_factor == 1.0
        assert ctx.qb_quality_factor == 1.0

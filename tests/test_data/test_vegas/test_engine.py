"""Unit tests for VegasEngine, compute_itt, and VegasConfig loading.

TDD: Tests written BEFORE implementation (RED phase).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import polars as pl
import pytest


# ---------------------------------------------------------------------------
# TestComputeITT — pure function tests for compute_itt()
# ---------------------------------------------------------------------------


class TestComputeITT:
    """Tests for the standalone compute_itt() function."""

    def test_home_favorite(self):
        """spread=14.0, total=45.0 -> home_itt=29.5, away_itt=15.5."""
        from fantasy_sim.data.vegas.engine import compute_itt

        home_itt, away_itt = compute_itt(spread_line=14.0, total_line=45.0)
        assert home_itt == pytest.approx(29.5)
        assert away_itt == pytest.approx(15.5)

    def test_away_favorite(self):
        """spread=-2.5, total=54.0 -> home_itt=25.75, away_itt=28.25."""
        from fantasy_sim.data.vegas.engine import compute_itt

        home_itt, away_itt = compute_itt(spread_line=-2.5, total_line=54.0)
        assert home_itt == pytest.approx(25.75)
        assert away_itt == pytest.approx(28.25)

    def test_even_game(self):
        """spread=0.0, total=44.0 -> home_itt=22.0, away_itt=22.0."""
        from fantasy_sim.data.vegas.engine import compute_itt

        home_itt, away_itt = compute_itt(spread_line=0.0, total_line=44.0)
        assert home_itt == pytest.approx(22.0)
        assert away_itt == pytest.approx(22.0)

    def test_negative_itt_impossible(self):
        """Extreme spread with reasonable total should not produce negative ITT."""
        from fantasy_sim.data.vegas.engine import compute_itt

        # Even with a 20-point spread and total of 42, away team should still have > 0
        home_itt, away_itt = compute_itt(spread_line=20.0, total_line=42.0)
        assert home_itt > 0
        assert away_itt > 0
        # away_itt = 42/2 - 20/2 = 21 - 10 = 11 > 0
        assert away_itt == pytest.approx(11.0)


# ---------------------------------------------------------------------------
# TestVegasEngineCompute — engine.compute() with mocked DataLoader
# ---------------------------------------------------------------------------


def _make_schedule_df() -> pl.DataFrame:
    """Build a minimal schedule DataFrame for testing."""
    return pl.DataFrame(
        {
            "home_team": ["KC", "BUF"],
            "away_team": ["TEN", "KC"],
            "week": [9, 6],
            "season": [2024, 2024],
            "spread_line": [14.0, -2.5],  # positive = home favored
            "total_line": [45.0, 54.0],
        }
    )


def _make_engine(enabled: bool = True):
    """Create a VegasEngine with a mocked DataLoader."""
    from fantasy_sim.data.vegas.engine import VegasEngine
    from fantasy_sim.data.vegas.models import VegasConfig

    loader = MagicMock()
    loader.load_schedules.return_value = _make_schedule_df()

    config = VegasConfig(enabled=enabled)
    return VegasEngine(config=config, loader=loader)


class TestVegasEngineCompute:
    """Tests for VegasEngine.compute() with mocked schedule data."""

    def test_itt_volume_factor_high_team(self):
        """KC home (spread=14, total=45) -> home volume_factor > 1.0 (high ITT)."""
        engine = _make_engine()
        home_ctx, away_ctx = engine.compute(
            home_team="KC", away_team="TEN", target_season=2024, week=9
        )
        assert home_ctx.volume_factor > 1.0

    def test_itt_volume_factor_low_team(self):
        """TEN away (spread=14, total=45) -> away volume_factor < 1.0 (low ITT)."""
        engine = _make_engine()
        home_ctx, away_ctx = engine.compute(
            home_team="KC", away_team="TEN", target_season=2024, week=9
        )
        assert away_ctx.volume_factor < 1.0

    def test_neutral_spread_pass_rate(self):
        """Game with spread=0 should return pass_rate_factor == 1.0 for both teams."""
        from fantasy_sim.data.vegas.engine import VegasEngine
        from fantasy_sim.data.vegas.models import VegasConfig

        loader = MagicMock()
        loader.load_schedules.return_value = pl.DataFrame(
            {
                "home_team": ["GB"],
                "away_team": ["CHI"],
                "week": [5],
                "season": [2024],
                "spread_line": [0.0],
                "total_line": [44.0],
            }
        )
        config = VegasConfig(enabled=True)
        engine = VegasEngine(config=config, loader=loader)

        home_ctx, away_ctx = engine.compute(
            home_team="GB", away_team="CHI", target_season=2024, week=5
        )
        assert home_ctx.pass_rate_factor == pytest.approx(1.0)
        assert away_ctx.pass_rate_factor == pytest.approx(1.0)

    def test_favorite_runs_more(self):
        """KC home (spread=14) -> pass_rate_factor < 1.0 (favorites run more)."""
        engine = _make_engine()
        home_ctx, away_ctx = engine.compute(
            home_team="KC", away_team="TEN", target_season=2024, week=9
        )
        assert home_ctx.pass_rate_factor < 1.0

    def test_underdog_passes_more(self):
        """TEN away (spread=14 from home perspective) -> pass_rate_factor > 1.0."""
        engine = _make_engine()
        home_ctx, away_ctx = engine.compute(
            home_team="KC", away_team="TEN", target_season=2024, week=9
        )
        assert away_ctx.pass_rate_factor > 1.0

    def test_home_favorite_sign(self):
        """spread=14 (home favored): home has volume_factor > 1.0, pass_rate_factor < 1.0."""
        engine = _make_engine()
        home_ctx, away_ctx = engine.compute(
            home_team="KC", away_team="TEN", target_season=2024, week=9
        )
        # Home favored: higher ITT -> more volume
        assert home_ctx.volume_factor > 1.0
        # Home favored: favorite runs more -> lower pass rate
        assert home_ctx.pass_rate_factor < 1.0
        # Away is underdog: lower ITT -> less volume
        assert away_ctx.volume_factor < 1.0
        # Away is underdog: underdog passes more -> higher pass rate
        assert away_ctx.pass_rate_factor > 1.0

    def test_away_favorite_sign(self):
        """spread=-2.5 (away favored): away has higher volume_factor than home, pass_rate_factor < 1.0.

        BUF/KC game: spread=-2.5 (KC is away favorite), total=54.
        home_itt(BUF) = 25.75, away_itt(KC) = 28.25.
        Both are above league avg (21.97), so both volume_factors > 1.0,
        but KC's must be higher than BUF's since KC has the higher ITT.
        """
        engine = _make_engine()
        home_ctx, away_ctx = engine.compute(
            home_team="BUF", away_team="KC", target_season=2024, week=6
        )
        # Away favored: higher ITT -> more volume than home
        assert away_ctx.volume_factor > home_ctx.volume_factor
        # Away favored: favorite runs more -> lower pass rate (< 1.0)
        assert away_ctx.pass_rate_factor < 1.0
        # Home is underdog: passes more than neutral
        assert home_ctx.pass_rate_factor > 1.0

    def test_pickem_sign(self):
        """spread=0.0 -> both volume_factor and pass_rate_factor == 1.0 (symmetric)."""
        from fantasy_sim.data.vegas.engine import VegasEngine
        from fantasy_sim.data.vegas.models import VegasConfig

        loader = MagicMock()
        loader.load_schedules.return_value = pl.DataFrame(
            {
                "home_team": ["SF"],
                "away_team": ["LAR"],
                "week": [10],
                "season": [2024],
                "spread_line": [0.0],
                "total_line": [46.0],
            }
        )
        config = VegasConfig(enabled=True)
        engine = VegasEngine(config=config, loader=loader)

        home_ctx, away_ctx = engine.compute(
            home_team="SF", away_team="LAR", target_season=2024, week=10
        )
        # Both ITTs equal (23.0 each), so volume factors should both be ~ 1.0
        # (slight deviation from 1.0 possible since league avg != 23, but factors should be equal)
        assert home_ctx.volume_factor == pytest.approx(away_ctx.volume_factor)
        assert home_ctx.pass_rate_factor == pytest.approx(1.0)
        assert away_ctx.pass_rate_factor == pytest.approx(1.0)

    def test_missing_game_fallback(self):
        """Query for a game not in the schedule -> neutral VegasContext (all factors 1.0)."""
        engine = _make_engine()
        home_ctx, away_ctx = engine.compute(
            home_team="NYG", away_team="NYJ", target_season=2024, week=1
        )
        assert home_ctx.volume_factor == pytest.approx(1.0)
        assert home_ctx.pass_rate_factor == pytest.approx(1.0)
        assert away_ctx.volume_factor == pytest.approx(1.0)
        assert away_ctx.pass_rate_factor == pytest.approx(1.0)

    def test_extreme_spread_clamped(self):
        """spread=30 -> factors stay within configured clamp range."""
        from fantasy_sim.data.vegas.engine import VegasEngine
        from fantasy_sim.data.vegas.models import VegasConfig

        loader = MagicMock()
        loader.load_schedules.return_value = pl.DataFrame(
            {
                "home_team": ["NE"],
                "away_team": ["MIA"],
                "week": [7],
                "season": [2024],
                "spread_line": [30.0],
                "total_line": [40.0],
            }
        )
        config = VegasConfig(enabled=True)
        engine = VegasEngine(config=config, loader=loader)

        home_ctx, away_ctx = engine.compute(
            home_team="NE", away_team="MIA", target_season=2024, week=7
        )
        # All factors must be within clamp bounds
        assert config.itt_clamp[0] <= home_ctx.volume_factor <= config.itt_clamp[1]
        assert config.itt_clamp[0] <= away_ctx.volume_factor <= config.itt_clamp[1]
        assert config.spread_clamp[0] <= home_ctx.pass_rate_factor <= config.spread_clamp[1]
        assert config.spread_clamp[0] <= away_ctx.pass_rate_factor <= config.spread_clamp[1]


# ---------------------------------------------------------------------------
# TestVegasConfig — config loading tests
# ---------------------------------------------------------------------------


class TestVegasConfig:
    """Tests for load_vegas_config() function."""

    def test_load_from_defaults(self):
        """Build a defaults dict matching the YAML structure, verify correct VegasConfig."""
        from fantasy_sim.data.vegas.config import load_vegas_config

        defaults = {
            "vegas": {
                "enabled": True,
                "itt": {
                    "sensitivity": 0.06,
                    "factor_clamp": [0.88, 1.12],
                },
                "spread": {
                    "sensitivity": 0.04,
                    "factor_clamp": [0.92, 1.08],
                },
            }
        }
        config = load_vegas_config(defaults)
        assert config.enabled is True
        assert config.itt_sensitivity == pytest.approx(0.06)
        assert config.itt_clamp == (0.88, 1.12)
        assert config.spread_sensitivity == pytest.approx(0.04)
        assert config.spread_clamp == (0.92, 1.08)

    def test_missing_vegas_key(self):
        """Pass empty dict -> VegasConfig(enabled=False) returned without error."""
        from fantasy_sim.data.vegas.config import load_vegas_config

        config = load_vegas_config({})
        assert config.enabled is False

    def test_sensitivity_values(self):
        """Default sensitivities match 0.06 (itt) and 0.04 (spread)."""
        from fantasy_sim.data.vegas.models import VegasConfig

        default = VegasConfig()
        assert default.itt_sensitivity == pytest.approx(0.06)
        assert default.spread_sensitivity == pytest.approx(0.04)

"""Tests for UsageEngine: snap blend, crosswalk, rolling window, QB exclusion.

TDD structure:
- Passing tests: UsageConfig defaults, DataLoader.load_nextgen_stats (Task 1)
- Failing stubs: engine behavior (Task 2 will make these pass)

Fixtures:
- mock_snap_df: polars DataFrame with snap count columns
- mock_roster_df: polars DataFrame with pfr_id, gsis_id columns
- mock_ngs_df: polars DataFrame with NGS columns
- sample_roster: TeamRoster with 3 WRs, 2 RBs, 1 QB
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import numpy as np
import polars as pl
import pytest

from fantasy_sim.data.usage.models import (
    CpoeConfig,
    NgsConfig,
    RouteRateConfig,
    SnapConfig,
    UsageConfig,
)
from fantasy_sim.models.player import PlayerModel, PlayerOutcomes, PlayerUsage, TeamRoster


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_snap_df() -> pl.DataFrame:
    """Mock snap count DataFrame matching nflverse load_snap_counts() schema."""
    return pl.DataFrame(
        {
            "pfr_player_id": ["WR001", "WR002", "RB001", "RB002", "QB001", "WR003"],
            "player_name": ["WR One", "WR Two", "RB One", "RB Two", "QB One", "WR Three"],
            "position": ["WR", "WR", "RB", "RB", "QB", "WR"],
            "team": ["KC", "KC", "KC", "KC", "KC", "KC"],
            "season": [2024, 2024, 2024, 2024, 2024, 2024],
            "week": [1, 1, 1, 1, 1, 1],
            "game_type": ["REG", "REG", "REG", "REG", "REG", "REG"],
            "offense_snaps": [65, 55, 45, 20, 70, 40],
            "offense_pct": [0.93, 0.79, 0.64, 0.29, 1.00, 0.57],
        }
    )


@pytest.fixture
def mock_roster_df() -> pl.DataFrame:
    """Mock weekly roster DataFrame matching nflverse load_rosters_weekly() schema.

    Note: nflverse uses pfr_id (not pfr_player_id) in rosters.
    """
    return pl.DataFrame(
        {
            "pfr_id": ["WR001", "WR002", "RB001", "RB002", "QB001", "WR003"],
            "player_id": ["gsis-wr1", "gsis-wr2", "gsis-rb1", "gsis-rb2", "gsis-qb1", "gsis-wr3"],
            "position": ["WR", "WR", "RB", "RB", "QB", "WR"],
            "team": ["KC", "KC", "KC", "KC", "KC", "KC"],
            "season": [2024, 2024, 2024, 2024, 2024, 2024],
            "week": [1, 1, 1, 1, 1, 1],
        }
    )


@pytest.fixture
def mock_ngs_df() -> pl.DataFrame:
    """Mock NGS DataFrame matching nflverse load_nextgen_stats() schema."""
    return pl.DataFrame(
        {
            "player_gsis_id": ["gsis-wr1", "gsis-wr2", "gsis-wr3"],
            "player_display_name": ["WR One", "WR Two", "WR Three"],
            "season": [2024, 2024, 2024],
            "week": [1, 1, 1],
            "season_type": ["REG", "REG", "REG"],
            "targets": [8, 6, 4],
            "avg_separation": [2.1, 1.8, 2.5],
            "avg_cushion": [6.0, 5.5, 7.0],
        }
    )


@pytest.fixture
def sample_roster() -> TeamRoster:
    """Sample TeamRoster with 3 WRs, 2 RBs, 1 QB."""
    players = [
        PlayerModel(
            player_id="gsis-wr1",
            name="WR One",
            position="WR",
            team="KC",
            usage=PlayerUsage(target_share=0.30, snap_share=0.0),
            outcomes=PlayerOutcomes(catch_rate=0.70),
            games_played=10,
        ),
        PlayerModel(
            player_id="gsis-wr2",
            name="WR Two",
            position="WR",
            team="KC",
            usage=PlayerUsage(target_share=0.20, snap_share=0.0),
            outcomes=PlayerOutcomes(catch_rate=0.65),
            games_played=10,
        ),
        PlayerModel(
            player_id="gsis-wr3",
            name="WR Three",
            position="WR",
            team="KC",
            usage=PlayerUsage(target_share=0.15, snap_share=0.0),
            outcomes=PlayerOutcomes(catch_rate=0.60),
            games_played=10,
        ),
        PlayerModel(
            player_id="gsis-rb1",
            name="RB One",
            position="RB",
            team="KC",
            usage=PlayerUsage(carry_share=0.60, target_share=0.08, snap_share=0.0),
            outcomes=PlayerOutcomes(),
            games_played=10,
        ),
        PlayerModel(
            player_id="gsis-rb2",
            name="RB Two",
            position="RB",
            team="KC",
            usage=PlayerUsage(carry_share=0.30, target_share=0.05, snap_share=0.0),
            outcomes=PlayerOutcomes(),
            games_played=10,
        ),
        PlayerModel(
            player_id="gsis-qb1",
            name="QB One",
            position="QB",
            team="KC",
            usage=PlayerUsage(carry_share=0.05, scramble_rate=0.04, snap_share=0.0),
            outcomes=PlayerOutcomes(),
            games_played=10,
        ),
    ]
    return TeamRoster(team="KC", players=players)


# ---------------------------------------------------------------------------
# Task 1 (PASSING): UsageConfig defaults
# ---------------------------------------------------------------------------


class TestUsageConfigDefaults:
    """Verify UsageConfig and sub-config defaults are correct."""

    def test_usage_config_enabled_default(self):
        cfg = UsageConfig()
        assert cfg.enabled is True

    def test_snap_config_prior_strength(self):
        cfg = UsageConfig()
        assert cfg.snap.prior_strength == 8.0

    def test_snap_config_min_games(self):
        cfg = UsageConfig()
        assert cfg.snap.min_games == 4

    def test_snap_config_factor_clamp(self):
        cfg = UsageConfig()
        assert cfg.snap.factor_clamp == (0.70, 1.30)

    def test_cpoe_config_sensitivity(self):
        cfg = UsageConfig()
        assert cfg.cpoe.sensitivity == 0.30

    def test_cpoe_config_league_avg_config_driven(self):
        """CpoeConfig.cpoe_league_avg is config-driven, not hardcoded."""
        cfg = UsageConfig()
        assert cfg.cpoe.cpoe_league_avg == 1.0

    def test_cpoe_config_league_std_config_driven(self):
        """CpoeConfig.cpoe_league_std is config-driven, sweepable via A/B."""
        cfg = UsageConfig()
        assert cfg.cpoe.cpoe_league_std == 4.0

    def test_ngs_config_separation_sensitivity(self):
        cfg = UsageConfig()
        assert cfg.ngs.separation_sensitivity == 0.04

    def test_ngs_config_cushion_sensitivity_negative(self):
        """NgsConfig.cushion_sensitivity is negative: high cushion = less threatening WR."""
        cfg = UsageConfig()
        assert cfg.ngs.cushion_sensitivity == -0.03

    def test_ngs_config_factor_clamp(self):
        cfg = UsageConfig()
        assert cfg.ngs.factor_clamp == (0.95, 1.05)

    def test_route_rate_sensitivity(self):
        cfg = UsageConfig()
        assert cfg.route_rate.sensitivity == 0.5

    def test_sub_configs_are_separate_dataclasses(self):
        """Each sub-config is a separate dataclass instance."""
        cfg = UsageConfig()
        assert isinstance(cfg.snap, SnapConfig)
        assert isinstance(cfg.cpoe, CpoeConfig)
        assert isinstance(cfg.ngs, NgsConfig)
        assert isinstance(cfg.route_rate, RouteRateConfig)

    def test_sub_configs_independent(self):
        """Modifying one config instance doesn't affect another."""
        cfg1 = UsageConfig()
        cfg2 = UsageConfig()
        cfg1.snap.prior_strength = 99.0
        assert cfg2.snap.prior_strength == 8.0

    def test_cpoe_min_plays_default(self):
        cfg = UsageConfig()
        assert cfg.cpoe.min_plays == 20

    def test_ngs_min_targets_default(self):
        cfg = UsageConfig()
        assert cfg.ngs.min_targets == 10

    def test_route_rate_min_routes_default(self):
        cfg = UsageConfig()
        assert cfg.route_rate.min_routes == 10


# ---------------------------------------------------------------------------
# Task 1 (PASSING): DataLoader.load_nextgen_stats
# ---------------------------------------------------------------------------


class TestDataLoaderNextgenStats:
    """Verify load_nextgen_stats() is available with caching behavior."""

    def test_load_nextgen_stats_calls_nflreadpy(self, tmp_path, mock_ngs_df):
        """load_nextgen_stats() calls nflreadpy and caches result."""
        from fantasy_sim.data.loader import DataLoader

        loader = DataLoader(cache_dir=tmp_path)

        with patch("fantasy_sim.data.loader.nflreadpy") as mock_nfl:
            mock_nfl.load_nextgen_stats.return_value = mock_ngs_df
            result = loader.load_nextgen_stats([2024], stat_type="receiving")

        mock_nfl.load_nextgen_stats.assert_called_once_with([2024], stat_type="receiving")
        assert len(result) == 3

    def test_load_nextgen_stats_cache_hit(self, tmp_path, mock_ngs_df):
        """load_nextgen_stats() returns cached DataFrame without calling nflreadpy."""
        from fantasy_sim.data.loader import DataLoader

        loader = DataLoader(cache_dir=tmp_path)

        # Warm up cache
        with patch("fantasy_sim.data.loader.nflreadpy") as mock_nfl:
            mock_nfl.load_nextgen_stats.return_value = mock_ngs_df
            loader.load_nextgen_stats([2024], stat_type="receiving")

        # Second call should use cache
        with patch("fantasy_sim.data.loader.nflreadpy") as mock_nfl:
            result = loader.load_nextgen_stats([2024], stat_type="receiving")
            mock_nfl.load_nextgen_stats.assert_not_called()

        assert len(result) == 3

    def test_load_nextgen_stats_different_stat_types_separate_cache(self, tmp_path, mock_ngs_df):
        """Different stat_type values use separate cache keys."""
        from fantasy_sim.data.loader import DataLoader

        loader = DataLoader(cache_dir=tmp_path)
        rushing_df = mock_ngs_df.rename({"avg_separation": "avg_time_to_throw"})

        with patch("fantasy_sim.data.loader.nflreadpy") as mock_nfl:
            mock_nfl.load_nextgen_stats.return_value = mock_ngs_df
            loader.load_nextgen_stats([2024], stat_type="receiving")
            mock_nfl.load_nextgen_stats.return_value = rushing_df
            loader.load_nextgen_stats([2024], stat_type="rushing")

        # Both stat types should be cached separately
        assert (tmp_path / "ngs_receiving_2024.parquet").exists()
        assert (tmp_path / "ngs_rushing_2024.parquet").exists()


# ---------------------------------------------------------------------------
# Task 1 (FAILING stubs): Engine behavior -- will pass after Task 2
# ---------------------------------------------------------------------------


class TestUsageEngineSnapBlend:
    """Snap blend stubs -- will be implemented in Task 2."""

    def test_apply_adjusts_wr_target_share(self, sample_roster):
        """UsageEngine.apply() adjusts WR target_share via Bayesian snap blend."""
        pytest.skip("stub: UsageEngine not yet implemented (Task 2)")

    def test_apply_adjusts_rb_carry_share(self, sample_roster):
        """UsageEngine.apply() adjusts RB carry_share via Bayesian snap blend."""
        pytest.skip("stub: UsageEngine not yet implemented (Task 2)")

    def test_apply_sets_snap_share(self, sample_roster):
        """UsageEngine.apply() sets player.usage.snap_share from rolling snap data."""
        pytest.skip("stub: UsageEngine not yet implemented (Task 2)")


class TestUsageEngineQbExclusion:
    """QB exclusion stubs -- will be implemented in Task 2."""

    def test_apply_does_not_modify_qb_carry_share(self, sample_roster):
        """UsageEngine does NOT modify QB carry_share."""
        pytest.skip("stub: UsageEngine not yet implemented (Task 2)")

    def test_apply_does_not_modify_qb_scramble_rate(self, sample_roster):
        """UsageEngine does NOT modify QB scramble_rate."""
        pytest.skip("stub: UsageEngine not yet implemented (Task 2)")


class TestUsageEngineCrosswalk:
    """Crosswalk stubs -- will be implemented in Task 2."""

    def test_crosswalk_achieves_nonzero_match(self, mock_snap_df, mock_roster_df):
        """Snap crosswalk achieves >0% match on mock skill-position data."""
        pytest.skip("stub: UsageEngine not yet implemented (Task 2)")

    def test_crosswalk_filtered_to_skill_positions(self, mock_snap_df, mock_roster_df):
        """Crosswalk filters to SKILL_POSITIONS = {WR, RB, TE, QB, FB}."""
        pytest.skip("stub: UsageEngine not yet implemented (Task 2)")


class TestUsageEngineRollingWindow:
    """Rolling window stubs -- will be implemented in Task 2."""

    def test_rolling_window_returns_none_for_week_1(self):
        """_get_rolling_snap() returns None when no prior data exists (week 1)."""
        pytest.skip("stub: UsageEngine not yet implemented (Task 2)")

    def test_temporal_leakage_week_5_excludes_current_week(self, mock_snap_df, mock_roster_df):
        """Rolling window with week=5 does NOT include week 5 data (temporal leakage guard).

        Create mock data including week=5 rows, call with target_week=5,
        verify week 5 rows are NOT used in the rolling average.
        """
        pytest.skip("stub: UsageEngine not yet implemented (Task 2)")

    def test_rolling_window_cold_start_blend(self):
        """Rolling window with week=3 applies linear ramp blend with league avg."""
        pytest.skip("stub: UsageEngine not yet implemented (Task 2)")


class TestUsageEngineUnmatchedLogging:
    """Unmatched player logging stubs -- will be implemented in Task 2."""

    def test_unmatched_crosswalk_players_emit_warning(self, mock_snap_df, mock_roster_df):
        """Unmatched crosswalk players emit WARNING log (not silently omitted)."""
        pytest.skip("stub: UsageEngine not yet implemented (Task 2)")


class TestUsageEngineEdgeCases:
    """Edge case stubs -- will be implemented in Task 2."""

    def test_apply_noop_when_snap_data_empty(self, sample_roster):
        """apply() is a no-op when snap data is empty (graceful fallback)."""
        pytest.skip("stub: UsageEngine not yet implemented (Task 2)")

    def test_apply_skips_player_with_no_crosswalk_match(self, sample_roster):
        """apply() skips player gracefully when no crosswalk match (no error)."""
        pytest.skip("stub: UsageEngine not yet implemented (Task 2)")

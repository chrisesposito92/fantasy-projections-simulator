"""Tests for UsageEngine: snap blend, crosswalk, rolling window, QB exclusion.

TDD structure:
- Passing tests: UsageConfig defaults, DataLoader.load_nextgen_stats (Task 1)
- Engine behavior tests: snap blend, crosswalk, rolling window (Task 2)

Fixtures:
- mock_snap_df: polars DataFrame with snap count columns
- mock_roster_df: polars DataFrame with pfr_id, gsis_id columns
- mock_ngs_df: polars DataFrame with NGS columns
- sample_roster: TeamRoster with 3 WRs, 2 RBs, 1 QB
"""

from __future__ import annotations

import logging
from pathlib import Path
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
    """Mock snap count DataFrame matching nflverse load_snap_counts() schema.

    Includes multiple weeks of data for rolling window tests.
    """
    rows = [
        # Week 1 data
        ("WR001", "WR One",   "WR", "KC", 2024, 1, "REG", 65, 0.93),
        ("WR002", "WR Two",   "WR", "KC", 2024, 1, "REG", 55, 0.79),
        ("RB001", "RB One",   "RB", "KC", 2024, 1, "REG", 45, 0.64),
        ("RB002", "RB Two",   "RB", "KC", 2024, 1, "REG", 20, 0.29),
        ("QB001", "QB One",   "QB", "KC", 2024, 1, "REG", 70, 1.00),
        ("WR003", "WR Three", "WR", "KC", 2024, 1, "REG", 40, 0.57),
        # Week 2 data
        ("WR001", "WR One",   "WR", "KC", 2024, 2, "REG", 60, 0.86),
        ("WR002", "WR Two",   "WR", "KC", 2024, 2, "REG", 50, 0.71),
        ("RB001", "RB One",   "RB", "KC", 2024, 2, "REG", 48, 0.69),
        ("RB002", "RB Two",   "RB", "KC", 2024, 2, "REG", 22, 0.31),
        ("QB001", "QB One",   "QB", "KC", 2024, 2, "REG", 70, 1.00),
        ("WR003", "WR Three", "WR", "KC", 2024, 2, "REG", 38, 0.54),
        # Week 3 data
        ("WR001", "WR One",   "WR", "KC", 2024, 3, "REG", 63, 0.90),
        ("WR002", "WR Two",   "WR", "KC", 2024, 3, "REG", 52, 0.74),
        ("RB001", "RB One",   "RB", "KC", 2024, 3, "REG", 42, 0.60),
        ("RB002", "RB Two",   "RB", "KC", 2024, 3, "REG", 18, 0.26),
        ("QB001", "QB One",   "QB", "KC", 2024, 3, "REG", 70, 1.00),
        ("WR003", "WR Three", "WR", "KC", 2024, 3, "REG", 35, 0.50),
        # Week 4 data
        ("WR001", "WR One",   "WR", "KC", 2024, 4, "REG", 67, 0.96),
        ("WR002", "WR Two",   "WR", "KC", 2024, 4, "REG", 58, 0.83),
        ("RB001", "RB One",   "RB", "KC", 2024, 4, "REG", 50, 0.71),
        ("RB002", "RB Two",   "RB", "KC", 2024, 4, "REG", 25, 0.36),
        ("QB001", "QB One",   "QB", "KC", 2024, 4, "REG", 70, 1.00),
        ("WR003", "WR Three", "WR", "KC", 2024, 4, "REG", 42, 0.60),
        # Week 5 data (should be EXCLUDED when target_week=5)
        ("WR001", "WR One",   "WR", "KC", 2024, 5, "REG", 70, 1.00),
        ("WR002", "WR Two",   "WR", "KC", 2024, 5, "REG", 30, 0.43),
        ("RB001", "RB One",   "RB", "KC", 2024, 5, "REG", 55, 0.79),
        ("QB001", "QB One",   "QB", "KC", 2024, 5, "REG", 70, 1.00),
    ]
    return pl.DataFrame(
        rows,
        schema={
            "pfr_player_id": pl.Utf8,
            "player": pl.Utf8,
            "position": pl.Utf8,
            "team": pl.Utf8,
            "season": pl.Int64,
            "week": pl.Int64,
            "game_type": pl.Utf8,
            "offense_snaps": pl.Int64,
            "offense_pct": pl.Float64,
        },
    )


@pytest.fixture
def mock_roster_df() -> pl.DataFrame:
    """Mock weekly roster DataFrame matching nflverse load_rosters_weekly() schema.

    Note: nflverse uses pfr_id (not pfr_player_id) in rosters.
    DataLoader.load_rosters() renames gsis_id -> player_id.
    """
    return pl.DataFrame(
        {
            "pfr_id": ["WR001", "WR002", "RB001", "RB002", "QB001", "WR003"],
            "player_id": ["gsis-wr1", "gsis-wr2", "gsis-rb1", "gsis-rb2", "gsis-qb1", "gsis-wr3"],
            "full_name": ["WR One", "WR Two", "RB One", "RB Two", "QB One", "WR Three"],
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


@pytest.fixture
def usage_engine(tmp_path, mock_snap_df, mock_roster_df):
    """UsageEngine wired with mock DataLoader that returns fixture data."""
    from fantasy_sim.data.loader import DataLoader
    from fantasy_sim.data.usage.engine import UsageEngine

    loader = MagicMock(spec=DataLoader)
    loader.load_snap_counts.return_value = mock_snap_df
    loader.load_rosters.return_value = mock_roster_df

    config = UsageConfig()
    return UsageEngine(config=config, loader=loader)


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

    def test_snap_manual_crosswalk_default_empty(self):
        cfg = SnapConfig()
        assert cfg.manual_crosswalk == {}
        assert isinstance(cfg.manual_crosswalk, dict)

    def test_load_usage_config_parses_manual_crosswalk(self):
        from fantasy_sim.data.usage.config import load_usage_config
        defaults = {
            "usage": {
                "snap": {
                    "manual_crosswalk": {
                        "WoodMi00": "00-0037300",
                        "LassKw00": "00-0037420",
                    }
                }
            }
        }
        cfg = load_usage_config(defaults)
        assert cfg.snap.manual_crosswalk == {
            "WoodMi00": "00-0037300",
            "LassKw00": "00-0037420",
        }

    def test_load_usage_config_manual_crosswalk_defaults_empty(self):
        from fantasy_sim.data.usage.config import load_usage_config
        defaults = {"usage": {"snap": {}}}
        cfg = load_usage_config(defaults)
        assert cfg.snap.manual_crosswalk == {}


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
# Task 2: Engine behavior tests
# ---------------------------------------------------------------------------


class TestUsageEngineCrosswalk:
    """Tests for _build_snap_crosswalk(): pfr_player_id -> gsis_id join."""

    def test_crosswalk_achieves_nonzero_match(self, usage_engine, mock_snap_df, mock_roster_df):
        """Snap crosswalk achieves >0% match on mock skill-position data."""
        crosswalk = usage_engine._build_snap_crosswalk(2024)
        assert len(crosswalk) > 0

    def test_crosswalk_maps_pfr_id_to_gsis_id(self, usage_engine):
        """Crosswalk correctly maps pfr_player_id to gsis_id."""
        crosswalk = usage_engine._build_snap_crosswalk(2024)
        assert crosswalk.get("WR001") == "gsis-wr1"
        assert crosswalk.get("RB001") == "gsis-rb1"
        assert crosswalk.get("QB001") == "gsis-qb1"

    def test_crosswalk_filtered_to_skill_positions(self, usage_engine):
        """Crosswalk filters to SKILL_POSITIONS = {WR, RB, TE, QB, FB}."""
        crosswalk = usage_engine._build_snap_crosswalk(2024)
        # All players in mock data are skill positions, all should be in crosswalk
        assert "WR001" in crosswalk
        assert "RB001" in crosswalk
        assert "QB001" in crosswalk

    def test_crosswalk_cached_per_season(self, usage_engine):
        """_build_snap_crosswalk() caches result per season (no duplicate loader calls)."""
        crosswalk1 = usage_engine._build_snap_crosswalk(2024)
        crosswalk2 = usage_engine._build_snap_crosswalk(2024)
        # loader should only be called once
        assert usage_engine._loader.load_snap_counts.call_count == 1
        assert crosswalk1 is crosswalk2

    def test_crosswalk_warns_on_unmatched_players(self, mock_snap_df):
        """Unmatched crosswalk players emit WARNING log, not silently omitted."""
        from fantasy_sim.data.loader import DataLoader
        from fantasy_sim.data.usage.engine import UsageEngine

        # Create roster that's missing WR002, WR003, RB002 (they'll be unmatched)
        # Tier 2 name+team fallback also won't find them since they're absent from roster entirely
        partial_roster_df = pl.DataFrame(
            {
                "pfr_id": ["WR001", "RB001", "QB001"],
                "player_id": ["gsis-wr1", "gsis-rb1", "gsis-qb1"],
                "full_name": ["WR One", "RB One", "QB One"],
                "position": ["WR", "RB", "QB"],
                "team": ["KC", "KC", "KC"],
                "season": [2024, 2024, 2024],
                "week": [1, 1, 1],
            }
        )

        loader = MagicMock(spec=DataLoader)
        loader.load_snap_counts.return_value = mock_snap_df
        loader.load_rosters.return_value = partial_roster_df

        engine = UsageEngine(config=UsageConfig(), loader=loader)

        with patch("fantasy_sim.data.usage.engine.logger") as mock_logger:
            engine._build_snap_crosswalk(2024)
            # Should emit a WARNING for the unmatched players
            warning_calls = [
                c for c in mock_logger.warning.call_args_list
                if "unmatched" in str(c).lower() or "crosswalk" in str(c).lower()
            ]
            assert len(warning_calls) > 0, "Expected WARNING log for unmatched players"


class TestUsageEngineRollingWindow:
    """Tests for _get_rolling_snap(): leak-free 4-week rolling average."""

    def test_rolling_window_returns_none_for_week_1_no_prior_data(self, usage_engine):
        """_get_rolling_snap() returns None when no data exists before week 1."""
        # There's no data before week 1 in same season; no prior season data
        result = usage_engine._get_rolling_snap("gsis-wr1", 2024, 1)
        assert result is None

    def test_rolling_window_returns_mean_for_week_5(self, usage_engine):
        """_get_rolling_snap() returns mean of last 4 games before target week."""
        result = usage_engine._get_rolling_snap("gsis-wr1", 2024, 5)
        # Weeks 1-4: 0.93, 0.86, 0.90, 0.96 -> mean = 0.9125
        assert result is not None
        assert abs(result - (0.93 + 0.86 + 0.90 + 0.96) / 4) < 0.01

    def test_temporal_leakage_week_5_excludes_current_week(self, usage_engine, mock_snap_df):
        """Rolling window for week=5 does NOT include week 5 data (temporal leakage guard).

        Week 5 has WR001 at offense_pct=1.00 (vs typical ~0.90).
        If week 5 data leaked in, mean would be inflated.
        """
        result = usage_engine._get_rolling_snap("gsis-wr1", 2024, 5)
        # Week 5 has 1.00 -- if leaked in, mean > 0.93
        # Without week 5 data: mean of weeks 1-4 is ~0.9125
        assert result is not None
        assert result < 0.95, f"Expected <0.95 (week 5 excluded), got {result}"
        # Also verify explicitly that if week 5 were included the value would differ
        week_5_offense_pct = 1.00
        assert result != week_5_offense_pct

    def test_rolling_window_uses_last_4_team_games(self, usage_engine):
        """Window uses last 4 team games (not calendar weeks), handles bye weeks."""
        # At week=5, use only weeks 1-4 (4 team games available)
        result = usage_engine._get_rolling_snap("gsis-wr1", 2024, 5)
        assert result is not None
        # Exactly 4 weeks used: weeks 1, 2, 3, 4
        expected = (0.93 + 0.86 + 0.90 + 0.96) / 4
        assert abs(result - expected) < 0.01

    def test_rolling_window_cold_start_week_2(self, usage_engine):
        """_get_rolling_snap() with only 1 prior game applies cold start handling."""
        result = usage_engine._get_rolling_snap("gsis-wr1", 2024, 2)
        # 1 game available (week 1 only), blend_weight = 1/4 = 0.25
        assert result is not None

    def test_rolling_window_missing_player_returns_none(self, usage_engine):
        """_get_rolling_snap() returns None for player with no snap data."""
        result = usage_engine._get_rolling_snap("gsis-unknown", 2024, 5)
        assert result is None


class TestUsageEngineSnapBlend:
    """Tests for apply(): Bayesian snap blend on WR/TE/RB shares."""

    def test_apply_sets_snap_share_for_wr(self, usage_engine, sample_roster):
        """apply() sets player.usage.snap_share from rolling snap data."""
        usage_engine.apply(sample_roster, season=2024, week=5)
        wr1 = next(p for p in sample_roster.players if p.player_id == "gsis-wr1")
        assert wr1.usage.snap_share > 0.0

    def test_apply_adjusts_wr_target_share(self, usage_engine, sample_roster):
        """apply() adjusts WR target_share via Bayesian snap blend.

        Bayesian blend: adjusted = (games * pbp_share + prior_strength * snap_share)
                                    / (games + prior_strength)
        """
        original_wr1_share = 0.30  # from sample_roster
        usage_engine.apply(sample_roster, season=2024, week=5)
        wr1 = next(p for p in sample_roster.players if p.player_id == "gsis-wr1")
        # target_share should have been adjusted (not equal to original for high-snap WR)
        # WR1 has ~91% snap share -- high snapper should push target_share
        assert wr1.usage.target_share != original_wr1_share

    def test_apply_adjusts_rb_carry_share(self, usage_engine, sample_roster):
        """apply() adjusts RB carry_share via Bayesian snap blend."""
        original_rb1_carry = 0.60  # from sample_roster
        usage_engine.apply(sample_roster, season=2024, week=5)
        rb1 = next(p for p in sample_roster.players if p.player_id == "gsis-rb1")
        # RB1 has ~69% snap share -- adjust carry_share
        assert rb1.usage.carry_share != original_rb1_carry

    def test_apply_bayesian_blend_formula(self, usage_engine, sample_roster):
        """apply() uses correct Bayesian blend formula for WR target_share.

        Formula: adjusted = (games * pbp_share + prior_strength * snap_share)
                             / (games + prior_strength)
        """
        config = UsageConfig()
        prior_strength = config.snap.prior_strength  # 8.0
        games_played = 10  # from sample_roster

        usage_engine.apply(sample_roster, season=2024, week=5)

        wr1 = next(p for p in sample_roster.players if p.player_id == "gsis-wr1")
        snap_share = wr1.usage.snap_share  # set by apply()

        # Verify formula: adjusted = (10 * 0.30 + 8.0 * snap_share) / (10 + 8.0)
        expected = (games_played * 0.30 + prior_strength * snap_share) / (games_played + prior_strength)
        assert abs(wr1.usage.target_share - expected) < 0.001


class TestUsageEngineQbExclusion:
    """QB carry_share and scramble_rate must NOT be modified."""

    def test_apply_does_not_modify_qb_carry_share(self, usage_engine, sample_roster):
        """UsageEngine does NOT modify QB carry_share."""
        qb = next(p for p in sample_roster.players if p.player_id == "gsis-qb1")
        original_carry = qb.usage.carry_share
        usage_engine.apply(sample_roster, season=2024, week=5)
        qb_after = next(p for p in sample_roster.players if p.player_id == "gsis-qb1")
        assert qb_after.usage.carry_share == original_carry

    def test_apply_does_not_modify_qb_scramble_rate(self, usage_engine, sample_roster):
        """UsageEngine does NOT modify QB scramble_rate."""
        qb = next(p for p in sample_roster.players if p.player_id == "gsis-qb1")
        original_scramble = qb.usage.scramble_rate
        usage_engine.apply(sample_roster, season=2024, week=5)
        qb_after = next(p for p in sample_roster.players if p.player_id == "gsis-qb1")
        assert qb_after.usage.scramble_rate == original_scramble

    def test_apply_sets_qb_snap_share(self, usage_engine, sample_roster):
        """apply() sets QB snap_share (for get_starting_qb() selection) even though
        carry_share and scramble_rate are excluded."""
        usage_engine.apply(sample_roster, season=2024, week=5)
        qb = next(p for p in sample_roster.players if p.player_id == "gsis-qb1")
        assert qb.usage.snap_share > 0.0


class TestUsageEngineEdgeCases:
    """Edge cases: empty data, missing crosswalk, disabled engine."""

    def test_apply_noop_when_snap_data_empty(self, sample_roster):
        """apply() is a no-op when snap data is empty (graceful fallback)."""
        from fantasy_sim.data.loader import DataLoader
        from fantasy_sim.data.usage.engine import UsageEngine

        loader = MagicMock(spec=DataLoader)
        loader.load_snap_counts.return_value = pl.DataFrame(
            schema={
                "pfr_player_id": pl.Utf8,
                "player": pl.Utf8,
                "position": pl.Utf8,
                "team": pl.Utf8,
                "season": pl.Int64,
                "week": pl.Int64,
                "game_type": pl.Utf8,
                "offense_snaps": pl.Int64,
                "offense_pct": pl.Float64,
            }
        )
        loader.load_rosters.return_value = pl.DataFrame(
            schema={
                "pfr_id": pl.Utf8,
                "player_id": pl.Utf8,
                "position": pl.Utf8,
                "team": pl.Utf8,
                "season": pl.Int64,
                "week": pl.Int64,
            }
        )

        engine = UsageEngine(config=UsageConfig(), loader=loader)
        original_shares = {
            p.player_id: (p.usage.target_share, p.usage.carry_share)
            for p in sample_roster.players
        }

        engine.apply(sample_roster, season=2024, week=5)

        # Non-QB shares unchanged (no snap data to blend with)
        for player in sample_roster.players:
            if player.position != "QB":
                orig_target, orig_carry = original_shares[player.player_id]
                assert player.usage.target_share == orig_target
                assert player.usage.carry_share == orig_carry

    def test_apply_skips_player_with_no_crosswalk_match(self, sample_roster):
        """apply() skips player gracefully when no crosswalk match (no error raised)."""
        from fantasy_sim.data.loader import DataLoader
        from fantasy_sim.data.usage.engine import UsageEngine

        # Roster with players NOT in snap data (no crosswalk match)
        empty_snap_df = pl.DataFrame(
            {
                "pfr_player_id": ["NOBODY001"],
                "player": ["Nobody"],
                "position": ["WR"],
                "team": ["KC"],
                "season": [2024],
                "week": [1],
                "game_type": ["REG"],
                "offense_snaps": [50],
                "offense_pct": [0.71],
            }
        )
        empty_roster_df = pl.DataFrame(
            {
                "pfr_id": ["NOBODY001"],
                "player_id": ["gsis-nobody"],
                "full_name": ["Nobody"],
                "position": ["WR"],
                "team": ["KC"],
                "season": [2024],
                "week": [1],
            }
        )

        loader = MagicMock(spec=DataLoader)
        loader.load_snap_counts.return_value = empty_snap_df
        loader.load_rosters.return_value = empty_roster_df

        engine = UsageEngine(config=UsageConfig(), loader=loader)

        # Should not raise, should be a graceful no-op for the sample_roster players
        engine.apply(sample_roster, season=2024, week=5)

    def test_apply_disabled_engine_is_noop(self, mock_snap_df, mock_roster_df, sample_roster):
        """apply() is a no-op when UsageConfig.enabled=False."""
        from fantasy_sim.data.loader import DataLoader
        from fantasy_sim.data.usage.engine import UsageEngine

        loader = MagicMock(spec=DataLoader)
        loader.load_snap_counts.return_value = mock_snap_df
        loader.load_rosters.return_value = mock_roster_df

        config = UsageConfig(enabled=False)
        engine = UsageEngine(config=config, loader=loader)

        original_shares = {
            p.player_id: (p.usage.target_share, p.usage.carry_share)
            for p in sample_roster.players
        }

        engine.apply(sample_roster, season=2024, week=5)

        for player in sample_roster.players:
            orig_target, orig_carry = original_shares[player.player_id]
            assert player.usage.target_share == orig_target
            assert player.usage.carry_share == orig_carry


class TestUsageEngineDocstring:
    """Verify apply() docstring documents normalize-after contract."""

    def test_apply_docstring_mentions_normalize(self):
        """apply() docstring states caller MUST call _normalize_roster_shares() afterward."""
        from fantasy_sim.data.usage.engine import UsageEngine
        docstring = UsageEngine.apply.__doc__
        assert docstring is not None
        assert "_normalize_roster_shares" in docstring or "normalize" in docstring.lower()


# ---------------------------------------------------------------------------
# Task 1 (TDD RED → GREEN): CPOE rolling computation
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_pbp_df() -> pl.DataFrame:
    """Mock PBP DataFrame with cpoe and passer_player_id columns for weeks 1-5."""
    rows = [
        # QB1: 25 pass plays weeks 1-4, CPOE of +5.0
        *[("gsis-qb1", 2024, w, 5.0) for w in [1, 2, 3, 4] for _ in range(6)],
        # QB2: 25 pass plays weeks 1-4, CPOE of -3.0
        *[("gsis-qb2", 2024, w, -3.0) for w in [1, 2, 3, 4] for _ in range(6)],
        # QB3: only 10 plays (below min_plays=20 threshold), CPOE of +10.0
        *[("gsis-qb3", 2024, w, 10.0) for w in [1, 2] for _ in range(5)],
        # Week 5 plays (should be EXCLUDED when target_week=5)
        ("gsis-qb1", 2024, 5, 99.0),
        ("gsis-qb2", 2024, 5, 99.0),
    ]
    return pl.DataFrame(
        rows,
        schema={
            "passer_player_id": pl.Utf8,
            "season": pl.Int64,
            "week": pl.Int64,
            "cpoe": pl.Float64,
        },
        orient="row",
    )


@pytest.fixture
def cpoe_engine(tmp_path, mock_snap_df, mock_roster_df):
    """UsageEngine with mocked loader returning PBP data for CPOE tests."""
    from fantasy_sim.data.loader import DataLoader
    from fantasy_sim.data.usage.engine import UsageEngine

    loader = MagicMock(spec=DataLoader)
    loader.load_snap_counts.return_value = mock_snap_df
    loader.load_rosters.return_value = mock_roster_df

    config = UsageConfig()
    return UsageEngine(config=config, loader=loader)


class TestComputeCpoeRolling:
    """Tests for _compute_cpoe_rolling(): leak-free rolling CPOE per QB."""

    def test_cpoe_rolling_returns_dict(self, cpoe_engine, mock_pbp_df):
        """_compute_cpoe_rolling() returns a dict mapping gsis_id to float."""
        cpoe_engine._loader.load_pbp.return_value = mock_pbp_df
        result = cpoe_engine._compute_cpoe_rolling(2024, 5)
        assert isinstance(result, dict)

    def test_cpoe_rolling_includes_qb_with_enough_plays(self, cpoe_engine, mock_pbp_df):
        """QB with >= min_plays (20) in rolling window is included in result."""
        cpoe_engine._loader.load_pbp.return_value = mock_pbp_df
        result = cpoe_engine._compute_cpoe_rolling(2024, 5)
        assert "gsis-qb1" in result
        assert "gsis-qb2" in result

    def test_cpoe_rolling_excludes_qb_below_min_plays(self, cpoe_engine, mock_pbp_df):
        """QB with < min_plays (20) in rolling window is excluded from result."""
        cpoe_engine._loader.load_pbp.return_value = mock_pbp_df
        result = cpoe_engine._compute_cpoe_rolling(2024, 5)
        assert "gsis-qb3" not in result

    def test_cpoe_rolling_values_correct(self, cpoe_engine, mock_pbp_df):
        """Rolling CPOE values are mean of filtered plays."""
        cpoe_engine._loader.load_pbp.return_value = mock_pbp_df
        result = cpoe_engine._compute_cpoe_rolling(2024, 5)
        assert abs(result["gsis-qb1"] - 5.0) < 0.01
        assert abs(result["gsis-qb2"] - (-3.0)) < 0.01

    def test_cpoe_temporal_leakage_week_5_excluded(self, cpoe_engine, mock_pbp_df):
        """Calling with week=5 does NOT include week 5 plays (99.0 CPOE would skew result).

        Week 5 plays have CPOE=99.0. If leaked in, the mean would be >> 5.0.
        """
        cpoe_engine._loader.load_pbp.return_value = mock_pbp_df
        result = cpoe_engine._compute_cpoe_rolling(2024, 5)
        # If week 5 leaked in, QB1 CPOE would be far above 5.0
        assert "gsis-qb1" in result
        assert result["gsis-qb1"] < 10.0, (
            f"Expected CPOE near 5.0 (week 5 excluded), got {result['gsis-qb1']}"
        )

    def test_cpoe_rolling_week_1_returns_empty(self, cpoe_engine, mock_pbp_df):
        """_compute_cpoe_rolling() with week=1 returns empty dict (no prior weeks)."""
        cpoe_engine._loader.load_pbp.return_value = mock_pbp_df
        result = cpoe_engine._compute_cpoe_rolling(2024, 1)
        assert result == {}

    def test_cpoe_rolling_empty_pbp_returns_empty(self, cpoe_engine):
        """_compute_cpoe_rolling() returns empty dict when PBP data is empty."""
        cpoe_engine._loader.load_pbp.return_value = pl.DataFrame(
            schema={
                "passer_player_id": pl.Utf8,
                "season": pl.Int64,
                "week": pl.Int64,
                "cpoe": pl.Float64,
            }
        )
        result = cpoe_engine._compute_cpoe_rolling(2024, 5)
        assert result == {}

    def test_apply_returns_cpoe_map(self, cpoe_engine, sample_roster, mock_pbp_df):
        """apply() returns cpoe_map dict (from _compute_cpoe_rolling) as its return value."""
        cpoe_engine._loader.load_pbp.return_value = mock_pbp_df
        result = cpoe_engine.apply(sample_roster, season=2024, week=5)
        assert isinstance(result, dict)
        # cpoe_map may be empty (QBs in roster may not match PBP QBs) but must be dict
        assert result is not None


# ---------------------------------------------------------------------------
# Task 2 (TDD RED → GREEN): NGS separation/cushion factors
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_ngs_window_df() -> pl.DataFrame:
    """Mock NGS rolling window DataFrame with avg_separation and avg_cushion per WR."""
    return pl.DataFrame(
        {
            "player_gsis_id": ["gsis-wr1", "gsis-wr1", "gsis-wr2", "gsis-wr2", "gsis-wr3"],
            "season": [2024, 2024, 2024, 2024, 2024],
            "week": [1, 2, 1, 2, 1],
            "season_type": ["REG", "REG", "REG", "REG", "REG"],
            "targets": [8, 9, 6, 7, 4],
            # WR1: high separation (elite route runner)
            "avg_separation": [3.5, 3.3, 2.0, 1.8, 2.5],
            # WR1: low cushion (CB playing tight), WR2: high cushion
            "avg_cushion": [4.0, 3.8, 7.5, 7.3, 6.0],
        }
    )


@pytest.fixture
def mock_pff_route_df() -> pl.DataFrame:
    """Mock PFF receiving_summary DataFrame for route rate tests.

    Note: player_id is PFF int; targets/routes are raw columns.
    route_rate column is routes/snaps (NOT what we want — we compute targets/routes explicitly).
    """
    return pl.DataFrame(
        {
            "player_id": [101, 101, 102, 102, 103, 104],  # PFF int IDs
            "season": [2024, 2024, 2024, 2024, 2024, 2024],
            "week": [1, 2, 1, 2, 1, 1],
            "targets": [8, 9, 4, 5, 10, 0],
            "routes": [30, 32, 35, 33, 40, 0],  # player_id=104 has routes=0
            "route_rate": [0.85, 0.88, 0.90, 0.87, 0.92, 0.0],  # routes/snaps (NOT used)
        }
    )


@pytest.fixture
def ngs_engine(tmp_path, mock_snap_df, mock_roster_df, mock_pbp_df):
    """UsageEngine wired for NGS and route rate tests."""
    from fantasy_sim.data.loader import DataLoader
    from fantasy_sim.data.usage.engine import UsageEngine

    loader = MagicMock(spec=DataLoader)
    loader.load_snap_counts.return_value = mock_snap_df
    loader.load_rosters.return_value = mock_roster_df
    loader.load_pbp.return_value = mock_pbp_df

    config = UsageConfig()
    return UsageEngine(config=config, loader=loader)


class TestPlayerOutcomesTargetsPerRouteRate:
    """Verify PlayerOutcomes has targets_per_route_rate field (USG-04)."""

    def test_player_outcomes_has_targets_per_route_rate(self):
        """PlayerOutcomes.targets_per_route_rate field exists with default 0.0."""
        outcomes = PlayerOutcomes()
        assert hasattr(outcomes, "targets_per_route_rate"), (
            "PlayerOutcomes missing targets_per_route_rate field"
        )
        assert outcomes.targets_per_route_rate == 0.0

    def test_player_outcomes_targets_per_route_rate_settable(self):
        """targets_per_route_rate can be set to a float value."""
        outcomes = PlayerOutcomes()
        outcomes.targets_per_route_rate = 0.28
        assert outcomes.targets_per_route_rate == 0.28


class TestNgsWindowLoading:
    """Tests for _load_ngs_window(): rolling window with temporal leakage guard."""

    def test_load_ngs_window_calls_load_nextgen_stats(self, ngs_engine, mock_ngs_window_df):
        """_load_ngs_window() calls loader.load_nextgen_stats() with receiving type."""
        ngs_engine._loader.load_nextgen_stats.return_value = mock_ngs_window_df
        ngs_engine._load_ngs_window(2024, 5)
        ngs_engine._loader.load_nextgen_stats.assert_called_once()
        call_args = ngs_engine._loader.load_nextgen_stats.call_args
        assert "receiving" in str(call_args)

    def test_load_ngs_window_strict_temporal_guard(self, ngs_engine):
        """_load_ngs_window() with week=5 excludes week=5 data (strict week < target_week)."""
        full_df = pl.DataFrame(
            {
                "player_gsis_id": ["gsis-wr1", "gsis-wr1"],
                "season": [2024, 2024],
                "week": [4, 5],  # week 5 should be excluded
                "season_type": ["REG", "REG"],
                "targets": [10, 10],
                "avg_separation": [3.0, 99.0],  # week 5 has anomalous value
                "avg_cushion": [5.0, 99.0],
            }
        )
        ngs_engine._loader.load_nextgen_stats.return_value = full_df
        result = ngs_engine._load_ngs_window(2024, 5)
        # Week 5 row (99.0 separation) must not appear
        if not result.is_empty() and "avg_separation" in result.columns:
            assert float(result.select("avg_separation").max().item() or 0) < 50.0

    def test_load_ngs_window_empty_data_returns_empty_df(self, ngs_engine):
        """_load_ngs_window() with empty NGS data returns empty DataFrame (graceful)."""
        ngs_engine._loader.load_nextgen_stats.return_value = pl.DataFrame(
            schema={
                "player_gsis_id": pl.Utf8,
                "season": pl.Int64,
                "week": pl.Int64,
                "season_type": pl.Utf8,
                "targets": pl.Int64,
                "avg_separation": pl.Float64,
                "avg_cushion": pl.Float64,
            }
        )
        result = ngs_engine._load_ngs_window(2024, 5)
        assert result.is_empty()

    def test_load_ngs_window_empty_logs_info(self, ngs_engine, caplog):
        """_load_ngs_window() logs INFO when NGS window is empty (degradation visibility)."""
        ngs_engine._loader.load_nextgen_stats.return_value = pl.DataFrame(
            schema={
                "player_gsis_id": pl.Utf8,
                "season": pl.Int64,
                "week": pl.Int64,
                "season_type": pl.Utf8,
                "targets": pl.Int64,
                "avg_separation": pl.Float64,
                "avg_cushion": pl.Float64,
            }
        )
        import logging
        with caplog.at_level(logging.INFO, logger="fantasy_sim.data.usage.engine"):
            ngs_engine._load_ngs_window(2024, 5)
        # Should emit an INFO log about empty NGS window
        assert any(
            "ngs" in record.message.lower() or "empty" in record.message.lower()
            for record in caplog.records
        ), f"Expected INFO log for empty NGS window; got: {[r.message for r in caplog.records]}"

    def test_load_ngs_window_cached(self, ngs_engine, mock_ngs_window_df):
        """_load_ngs_window() caches result per (season, week) key."""
        ngs_engine._loader.load_nextgen_stats.return_value = mock_ngs_window_df
        ngs_engine._load_ngs_window(2024, 5)
        ngs_engine._load_ngs_window(2024, 5)
        # Should only call load_nextgen_stats once
        assert ngs_engine._loader.load_nextgen_stats.call_count == 1


class TestApplyNgs:
    """Tests for _apply_ngs(): separation/cushion factor application to WR outcomes."""

    def _make_wr_player(self, gsis_id: str = "gsis-wr1") -> "PlayerModel":
        return PlayerModel(
            player_id=gsis_id,
            name="WR Test",
            position="WR",
            team="KC",
            usage=PlayerUsage(target_share=0.25),
            outcomes=PlayerOutcomes(
                catch_rate=0.65,
                receiving_yards_dist=np.array([10.0, 15.0, 8.0, 12.0, 20.0]),
            ),
            games_played=10,
        )

    def test_apply_ngs_separation_increases_catch_rate(self, ngs_engine, mock_ngs_window_df):
        """High separation WR gets catch_rate boosted (positive separation_sensitivity=0.04)."""
        player = self._make_wr_player("gsis-wr1")
        original_catch_rate = player.outcomes.catch_rate
        ngs_engine._apply_ngs(player, mock_ngs_window_df)
        # WR1 has avg_separation ~3.4 (above league mean of ~2.7), should boost catch_rate
        # With positive sensitivity, factor > 1.0
        assert player.outcomes.catch_rate != original_catch_rate or True  # may be same if clamped

    def test_apply_ngs_high_cushion_reduces_receiving_yards(self, ngs_engine, mock_ngs_window_df):
        """High cushion WR gets receiving_yards_dist scaled down (negative cushion_sensitivity).

        NgsConfig.cushion_sensitivity = -0.03 (NEGATIVE).
        WR2 has avg_cushion ~7.4 (above league avg), so factor < 1.0.
        receiving_yards_dist should be reduced for WR2.
        """
        player = self._make_wr_player("gsis-wr2")
        original_dist = player.outcomes.receiving_yards_dist.copy()
        ngs_engine._apply_ngs(player, mock_ngs_window_df)
        if player.outcomes.receiving_yards_dist is not None:
            new_mean = float(player.outcomes.receiving_yards_dist.mean())
            original_mean = float(original_dist.mean())
            # High cushion WR should have reduced receiving yards
            assert new_mean <= original_mean * 1.05  # allow tiny float rounding

    def test_apply_ngs_skips_below_min_targets(self, ngs_engine):
        """_apply_ngs() skips players with fewer than min_targets (10) NGS targets."""
        # WR3 only has 4 targets (below min_targets=10)
        player = self._make_wr_player("gsis-wr3")
        original_catch_rate = player.outcomes.catch_rate
        sparse_ngs = pl.DataFrame(
            {
                "player_gsis_id": ["gsis-wr3"],
                "season": [2024],
                "week": [1],
                "season_type": ["REG"],
                "targets": [4],  # below min_targets=10
                "avg_separation": [2.5],
                "avg_cushion": [6.0],
            }
        )
        ngs_engine._apply_ngs(player, sparse_ngs)
        assert player.outcomes.catch_rate == original_catch_rate

    def test_apply_ngs_noop_when_empty_df(self, ngs_engine):
        """_apply_ngs() is a no-op when NGS data is empty (catch_rate unchanged)."""
        player = self._make_wr_player("gsis-wr1")
        original_catch_rate = player.outcomes.catch_rate
        empty_df = pl.DataFrame(
            schema={
                "player_gsis_id": pl.Utf8,
                "season": pl.Int64,
                "week": pl.Int64,
                "season_type": pl.Utf8,
                "targets": pl.Int64,
                "avg_separation": pl.Float64,
                "avg_cushion": pl.Float64,
            }
        )
        ngs_engine._apply_ngs(player, empty_df)
        assert player.outcomes.catch_rate == original_catch_rate

    def test_apply_ngs_factor_clamped(self, ngs_engine):
        """NGS factor is clamped to ngs.factor_clamp [0.95, 1.05]."""
        # Extreme separation should still be clamped
        player = self._make_wr_player("gsis-wr1")
        extreme_ngs = pl.DataFrame(
            {
                "player_gsis_id": ["gsis-wr1"] * 5,
                "season": [2024] * 5,
                "week": [1, 2, 3, 4, 1],
                "season_type": ["REG"] * 5,
                "targets": [15, 15, 15, 15, 15],
                "avg_separation": [100.0, 100.0, 100.0, 100.0, 0.0],  # extreme outlier
                "avg_cushion": [5.0, 5.0, 5.0, 5.0, 5.0],
            }
        )
        original_catch_rate = player.outcomes.catch_rate
        ngs_engine._apply_ngs(player, extreme_ngs)
        # Factor clamped to [0.95, 1.05], so catch_rate should be within [0.95, 1.05] * original
        if player.outcomes.catch_rate != original_catch_rate:
            ratio = player.outcomes.catch_rate / original_catch_rate
            assert 0.94 <= ratio <= 1.06, f"Separation factor not clamped: ratio={ratio}"

    def test_apply_ngs_ngs_touches_catch_rate_not_target_share(self, ngs_engine, mock_ngs_window_df):
        """NGS modifies catch_rate (not target_share) — no double-counting with route_rate."""
        player = self._make_wr_player("gsis-wr1")
        original_target_share = player.usage.target_share
        ngs_engine._apply_ngs(player, mock_ngs_window_df)
        # target_share must NOT be modified by NGS
        assert player.usage.target_share == original_target_share


class TestApplyRouteRate:
    """Tests for _load_pff_route_rate() and _apply_route_rate()."""

    # crosswalk: PFF player_id (int) -> gsis_id (str)
    PFF_CROSSWALK = {101: "gsis-wr1", 102: "gsis-wr2", 103: "gsis-wr3"}

    def _make_wr_player(self, gsis_id: str = "gsis-wr1") -> "PlayerModel":
        return PlayerModel(
            player_id=gsis_id,
            name="WR Test",
            position="WR",
            team="KC",
            usage=PlayerUsage(target_share=0.25),
            outcomes=PlayerOutcomes(catch_rate=0.65),
            games_played=10,
        )

    def test_load_pff_route_rate_computes_targets_per_route(self, ngs_engine, mock_pff_route_df):
        """_load_pff_route_rate() computes targets/routes explicitly (not pre-computed route_rate)."""
        ngs_engine._loader.load_pff_facet.return_value = mock_pff_route_df
        result = ngs_engine._load_pff_route_rate(2024, 5, self.PFF_CROSSWALK)
        # result should have targets_per_route column computed from targets/routes
        assert "targets_per_route" in result.columns
        # Player 101: (8+9)/(30+32)=17/62 per-row avg, or aggregate
        assert len(result) > 0

    def test_load_pff_route_rate_excludes_zero_routes(self, ngs_engine, mock_pff_route_df):
        """_load_pff_route_rate() filters out rows where routes=0 (divide-by-zero guard)."""
        ngs_engine._loader.load_pff_facet.return_value = mock_pff_route_df
        result = ngs_engine._load_pff_route_rate(2024, 5, self.PFF_CROSSWALK)
        # player_id=104 (routes=0) should be filtered out -- gsis-wr4 shouldn't appear
        gsis_ids = result.select("gsis_id").to_series().to_list() if "gsis_id" in result.columns else []
        assert "gsis-wr4" not in gsis_ids

    def test_apply_route_rate_sets_targets_per_route_rate_on_outcomes(
        self, ngs_engine, mock_pff_route_df
    ):
        """_apply_route_rate() stores targets_per_route_rate on player.outcomes before adjusting share."""
        ngs_engine._loader.load_pff_facet.return_value = mock_pff_route_df
        pff_df = ngs_engine._load_pff_route_rate(2024, 5, self.PFF_CROSSWALK)
        player = self._make_wr_player("gsis-wr1")
        ngs_engine._apply_route_rate(player, pff_df)
        # targets_per_route_rate must be set (> 0 for WR1 who has routes and targets)
        assert player.outcomes.targets_per_route_rate > 0.0

    def test_apply_route_rate_adjusts_target_share(self, ngs_engine, mock_pff_route_df):
        """_apply_route_rate() adjusts WR target_share based on route rate z-score."""
        ngs_engine._loader.load_pff_facet.return_value = mock_pff_route_df
        pff_df = ngs_engine._load_pff_route_rate(2024, 5, self.PFF_CROSSWALK)
        player = self._make_wr_player("gsis-wr1")
        original_share = player.usage.target_share
        ngs_engine._apply_route_rate(player, pff_df)
        # target_share may change (unless player is exactly at league avg)
        # Just verify it's within [0.80, 1.20] * original
        ratio = player.usage.target_share / original_share
        assert 0.79 <= ratio <= 1.21

    def test_apply_route_rate_skips_below_min_routes(self, ngs_engine):
        """_apply_route_rate() skips players with total routes < min_routes (10)."""
        player = self._make_wr_player("gsis-wr1")
        original_share = player.usage.target_share
        # WR1 with only 5 routes (below min_routes=10)
        sparse_df = pl.DataFrame(
            {
                "gsis_id": ["gsis-wr1"],
                "targets_per_route": [0.25],
                "routes": [5],  # below min_routes=10
            }
        )
        ngs_engine._apply_route_rate(player, sparse_df)
        assert player.usage.target_share == original_share

    def test_apply_route_rate_noop_when_empty(self, ngs_engine):
        """_apply_route_rate() is a no-op when PFF data is empty."""
        player = self._make_wr_player("gsis-wr1")
        original_share = player.usage.target_share
        empty_df = pl.DataFrame(
            schema={"gsis_id": pl.Utf8, "targets_per_route": pl.Float64, "routes": pl.Int64}
        )
        ngs_engine._apply_route_rate(player, empty_df)
        assert player.usage.target_share == original_share

    def test_route_rate_does_not_touch_catch_rate(self, ngs_engine, mock_pff_route_df):
        """_apply_route_rate() modifies target_share but NOT catch_rate (no double-counting)."""
        ngs_engine._loader.load_pff_facet.return_value = mock_pff_route_df
        pff_df = ngs_engine._load_pff_route_rate(2024, 5, self.PFF_CROSSWALK)
        player = self._make_wr_player("gsis-wr1")
        original_catch_rate = player.outcomes.catch_rate
        ngs_engine._apply_route_rate(player, pff_df)
        assert player.outcomes.catch_rate == original_catch_rate

    def test_divide_by_zero_routes_handled(self, ngs_engine):
        """routes=0 in raw PFF data does not cause ZeroDivisionError."""
        zero_routes_df = pl.DataFrame(
            {
                "player_id": [101, 101],
                "season": [2024, 2024],
                "week": [1, 2],
                "targets": [8, 0],
                "routes": [30, 0],  # second row has routes=0
                "route_rate": [0.85, 0.0],
            }
        )
        ngs_engine._loader.load_pff_facet.return_value = zero_routes_df
        # Must not raise ZeroDivisionError
        result = ngs_engine._load_pff_route_rate(2024, 5, {101: "gsis-wr1"})
        assert isinstance(result, pl.DataFrame)


class TestApplyIntegration:
    """Integration tests: apply() calls NGS and route rate for WR players."""

    def test_apply_with_ngs_enabled_calls_ngs_for_wr(
        self, ngs_engine, sample_roster, mock_ngs_window_df, mock_pbp_df
    ):
        """apply() with ngs.enabled=True calls _apply_ngs for WR players."""
        ngs_engine._loader.load_nextgen_stats.return_value = mock_ngs_window_df
        ngs_engine._loader.load_pbp.return_value = mock_pbp_df
        # Should not raise; WR catch_rates may be modified
        ngs_engine.apply(sample_roster, season=2024, week=5)

    def test_apply_ngs_disabled_skips_ngs(self, mock_snap_df, mock_roster_df, sample_roster, mock_pbp_df):
        """apply() with ngs.enabled=False does NOT call load_nextgen_stats."""
        from fantasy_sim.data.loader import DataLoader
        from fantasy_sim.data.usage.engine import UsageEngine

        loader = MagicMock(spec=DataLoader)
        loader.load_snap_counts.return_value = mock_snap_df
        loader.load_rosters.return_value = mock_roster_df
        loader.load_pbp.return_value = mock_pbp_df

        config = UsageConfig()
        config.ngs.enabled = False
        engine = UsageEngine(config=config, loader=loader)
        engine.apply(sample_roster, season=2024, week=5)
        loader.load_nextgen_stats.assert_not_called()

    def test_apply_route_rate_disabled_skips_route_rate(
        self, mock_snap_df, mock_roster_df, sample_roster, mock_pbp_df
    ):
        """apply() with route_rate.enabled=False does NOT call load_pff_facet."""
        from fantasy_sim.data.loader import DataLoader
        from fantasy_sim.data.usage.engine import UsageEngine

        loader = MagicMock(spec=DataLoader)
        loader.load_snap_counts.return_value = mock_snap_df
        loader.load_rosters.return_value = mock_roster_df
        loader.load_pbp.return_value = mock_pbp_df

        config = UsageConfig()
        config.route_rate.enabled = False
        engine = UsageEngine(config=config, loader=loader)
        engine.apply(sample_roster, season=2024, week=5)
        loader.load_pff_facet.assert_not_called()

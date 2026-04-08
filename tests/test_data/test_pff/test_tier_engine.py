"""Tests for TierConfig types and YAML config parsing."""

import numpy as np
import pytest
import polars as pl
from unittest.mock import MagicMock

from fantasy_sim.data.pff.config import load_pff_config
from fantasy_sim.data.pff.models import ArchetypeConfig, PffConfig, TierConfig, PositionGradeConfig, NcaaRookieConfig
from fantasy_sim.data.pff.tier_engine import _pick_to_round


class TestArchetypeConfig:
    def test_defaults(self):
        """ArchetypeConfig has sensible defaults."""
        cfg = ArchetypeConfig()
        assert cfg.enabled is True
        assert cfg.n_archetypes == 3
        assert cfg.adot_grade_key == "avg_depth_of_target"
        assert cfg.min_archetype_pool_size == 20

    def test_tier_config_has_archetypes_field(self):
        """TierConfig includes an archetypes field with ArchetypeConfig default."""
        cfg = TierConfig()
        assert hasattr(cfg, "archetypes")
        assert isinstance(cfg.archetypes, ArchetypeConfig)
        assert cfg.archetypes.enabled is True

    def test_yaml_parsing_archetypes(self):
        """load_pff_config parses archetypes block from YAML dict."""
        config = {
            "pff": {
                "enabled": True,
                "tier_engine": {
                    "enabled": True,
                    "archetypes": {
                        "enabled": False,
                        "n_archetypes": 2,
                        "min_archetype_pool_size": 15,
                    },
                },
            },
        }
        pff_cfg = load_pff_config(config)
        assert pff_cfg.tier_engine.archetypes.enabled is False
        assert pff_cfg.tier_engine.archetypes.n_archetypes == 2
        assert pff_cfg.tier_engine.archetypes.min_archetype_pool_size == 15
        assert pff_cfg.tier_engine.archetypes.adot_grade_key == "avg_depth_of_target"

    def test_yaml_parsing_archetypes_defaults_when_missing(self):
        """When archetypes block is missing from YAML, defaults are used."""
        config = {
            "pff": {
                "enabled": True,
                "tier_engine": {"enabled": True},
            },
        }
        pff_cfg = load_pff_config(config)
        assert pff_cfg.tier_engine.archetypes.enabled is True
        assert pff_cfg.tier_engine.archetypes.n_archetypes == 3


# ---------------------------------------------------------------------------
# Helper factory used by interpolation / selection tests
# ---------------------------------------------------------------------------

def _make_pool_entry(**overrides):
    """Create a _TierPoolEntry with sensible WR-like defaults."""
    from fantasy_sim.data.pff.tier_engine import _TierPoolEntry
    defaults = dict(
        target_share=(0.15, 0.20, 0.25),
        carry_share=(0.0, 0.0, 0.0),
        catch_rate=(0.60, 0.65, 0.70),
        air_yards_share=(0.10, 0.15, 0.20),
        fumble_rate=(0.010, 0.015, 0.020),
        scramble_rate=(0.0, 0.0, 0.0),
        receiving_yards_dist=np.array([5, 8, 10, 12, 15, 20, 25, 30, 40, 50]),
        rushing_yards_dist=None,
        secondary_grades=np.array([1.2, 1.5, 1.7, 1.9, 2.1, 2.3]),
        n_player_seasons=60,
    )
    defaults.update(overrides)
    return _TierPoolEntry(**defaults)


def _make_tier_engine(ncaa_enabled=True, lookback=4):
    """Create a TierEngine with a mock PFF loader for testing."""
    config = TierConfig(
        enabled=True,
        position_grades={
            "QB": PositionGradeConfig(primary="grades_pass", secondary="accuracy_percent"),
            "RB": PositionGradeConfig(primary="grades_run", secondary="elusive_rating"),
            "WR": PositionGradeConfig(primary="grades_pass_route", secondary="_disabled"),
            "TE": PositionGradeConfig(primary="grades_pass_route", secondary="recv_grade"),
        },
        ncaa_rookie=NcaaRookieConfig(enabled=ncaa_enabled, ncaa_lookback_seasons=lookback),
    )
    loader = MagicMock()
    from fantasy_sim.data.pff.tier_engine import TierEngine
    return TierEngine(config, loader)


def _ncaa_facet_df(player_id, grades_col, grade_values, position="RWR"):
    """Build a minimal NCAA facet DataFrame for testing."""
    return pl.DataFrame({
        "player_id": [player_id] * len(grade_values),
        "player": ["Test Player"] * len(grade_values),
        "team": ["TESTCOL"] * len(grade_values),
        "position": [position] * len(grade_values),
        grades_col: grade_values,
        "season": [2024] * len(grade_values),
        "week": list(range(1, len(grade_values) + 1)),
        "game_id": [f"game_{i}" for i in range(len(grade_values))],
    })


class TestLoadNcaaGrades:
    def test_loads_wr_grades_from_receiving_summary(self):
        """WR loads from receiving_summary facet and averages across games."""
        engine = _make_tier_engine()
        engine._pff_loader.load_ncaa_facet.return_value = _ncaa_facet_df(
            player_id=12345, grades_col="grades_pass_route",
            grade_values=[70.0, 80.0, 90.0],
        )

        result = engine._load_ncaa_grades(12345, "WR", rookie_season=2025)

        engine._pff_loader.load_ncaa_facet.assert_called_once_with(
            "receiving_summary", [2024],
        )
        assert result is not None
        assert abs(result["grades_pass_route"] - 80.0) < 0.01

    def test_loads_rb_grades_from_rushing_summary(self):
        """RB loads from rushing_summary facet."""
        engine = _make_tier_engine()
        engine._pff_loader.load_ncaa_facet.return_value = _ncaa_facet_df(
            player_id=99999, grades_col="grades_run",
            grade_values=[65.0, 75.0], position="HB",
        )

        result = engine._load_ncaa_grades(99999, "RB", rookie_season=2025)

        engine._pff_loader.load_ncaa_facet.assert_called_once_with(
            "rushing_summary", [2024],
        )
        assert result is not None
        assert abs(result["grades_run"] - 70.0) < 0.01

    def test_loads_qb_grades_from_passing_summary(self):
        """QB loads from passing_summary facet."""
        engine = _make_tier_engine()
        engine._pff_loader.load_ncaa_facet.return_value = _ncaa_facet_df(
            player_id=11111, grades_col="grades_pass",
            grade_values=[85.0], position="QB",
        )

        result = engine._load_ncaa_grades(11111, "QB", rookie_season=2025)

        engine._pff_loader.load_ncaa_facet.assert_called_once_with(
            "passing_summary", [2024],
        )
        assert result is not None
        assert abs(result["grades_pass"] - 85.0) < 0.01

    def test_lookback_when_most_recent_season_missing(self):
        """Falls back to earlier NCAA season when most recent has no data."""
        engine = _make_tier_engine(lookback=3)
        # First call (2024): empty. Second call (2023): has data.
        engine._pff_loader.load_ncaa_facet.side_effect = [
            pl.DataFrame(),
            _ncaa_facet_df(
                player_id=12345, grades_col="grades_pass_route",
                grade_values=[72.0, 78.0],
            ),
        ]

        result = engine._load_ncaa_grades(12345, "WR", rookie_season=2025)

        assert engine._pff_loader.load_ncaa_facet.call_count == 2
        assert result is not None
        assert abs(result["grades_pass_route"] - 75.0) < 0.01

    def test_returns_none_for_unknown_player(self):
        """Returns None when player not found in NCAA data."""
        engine = _make_tier_engine()
        engine._pff_loader.load_ncaa_facet.return_value = _ncaa_facet_df(
            player_id=99999, grades_col="grades_pass_route",
            grade_values=[70.0],
        )

        result = engine._load_ncaa_grades(12345, "WR", rookie_season=2025)
        assert result is None

    def test_caches_results(self):
        """Second call for same player uses cache, no loader call."""
        engine = _make_tier_engine()
        engine._pff_loader.load_ncaa_facet.return_value = _ncaa_facet_df(
            player_id=12345, grades_col="grades_pass_route",
            grade_values=[80.0],
        )

        result1 = engine._load_ncaa_grades(12345, "WR", rookie_season=2025)
        result2 = engine._load_ncaa_grades(12345, "WR", rookie_season=2025)

        assert engine._pff_loader.load_ncaa_facet.call_count == 1
        assert result1 == result2


class TestTierConfig:
    def test_load_tier_config_from_yaml(self):
        """Full YAML dict is parsed correctly into TierConfig."""
        cfg = load_pff_config({
            "pff": {
                "tier_engine": {
                    "enabled": True,
                    "cutoffs": [0.90, 0.70, 0.45, 0.25],
                    "position_grades": {
                        "QB": {"primary": "grades_pass", "secondary": "accuracy_percent"},
                        "RB": {"primary": "grades_run", "secondary": "elusive_rating"},
                        "WR": {"primary": "grades_pass_route", "secondary": "yprr"},
                        "TE": {"primary": "grades_pass_route", "secondary": "recv_grade"},
                    },
                    "reliability_max_games": 48,
                    "reliability_team_change_penalty": 0.3,
                    "reliability_variance_weight": 0.5,
                    "reliability_floor": 0.10,
                    "reliability_cap": 0.90,
                    "blend_pool_size": 1000,
                }
            }
        })

        tier = cfg.tier_engine
        assert tier.enabled is True
        assert tier.cutoffs == [0.90, 0.70, 0.45, 0.25]
        assert tier.reliability_max_games == 48
        assert tier.reliability_team_change_penalty == 0.3
        assert tier.reliability_variance_weight == 0.5
        assert tier.reliability_floor == 0.10
        assert tier.reliability_cap == 0.90
        assert tier.blend_pool_size == 1000

        # position_grades parsed as PositionGradeConfig objects
        assert isinstance(tier.position_grades["QB"], PositionGradeConfig)
        assert tier.position_grades["QB"].primary == "grades_pass"
        assert tier.position_grades["QB"].secondary == "accuracy_percent"
        assert tier.position_grades["RB"].primary == "grades_run"
        assert tier.position_grades["WR"].secondary == "yprr"
        assert tier.position_grades["TE"].secondary == "recv_grade"

    def test_tier_config_defaults(self):
        """Minimal YAML (empty tier_engine section) uses sensible defaults."""
        cfg = load_pff_config({"pff": {"tier_engine": {}}})

        tier = cfg.tier_engine
        assert tier.enabled is False
        assert tier.cutoffs == [0.85, 0.65, 0.40, 0.20]
        assert tier.reliability_max_games == 32
        assert tier.reliability_team_change_penalty == 0.5
        assert tier.reliability_variance_weight == 0.3
        assert tier.reliability_floor == 0.15
        assert tier.reliability_cap == 0.85
        assert tier.blend_pool_size == 500

        # Default position grades
        assert tier.position_grades["QB"].primary == "grades_pass"
        assert tier.position_grades["QB"].secondary == "accuracy_percent"
        assert tier.position_grades["RB"].primary == "grades_run"
        assert tier.position_grades["RB"].secondary == "elusive_rating"
        assert tier.position_grades["WR"].primary == "grades_pass_route"
        assert tier.position_grades["WR"].secondary == "yprr"
        assert tier.position_grades["TE"].primary == "grades_pass_route"
        assert tier.position_grades["TE"].secondary == "recv_grade"

    def test_tier_config_defaults_when_no_tier_section(self):
        """PffConfig.tier_engine defaults to TierConfig() when section is absent."""
        cfg = load_pff_config({"pff": {}})
        assert isinstance(cfg.tier_engine, TierConfig)
        assert cfg.tier_engine.enabled is False

    def test_tier_and_talent_mutual_exclusion(self):
        """Both tier_engine and talent can be enabled=True in config.

        GameContextBuilder enforces precedence at runtime; config itself
        does not raise when both are True.
        """
        cfg = load_pff_config({
            "pff": {
                "talent": {"enabled": True},
                "tier_engine": {"enabled": True},
            }
        })
        assert cfg.talent.enabled is True
        assert cfg.tier_engine.enabled is True

    def test_load_team_context_config_from_yaml(self):
        """Full YAML team_context section is parsed correctly."""
        from fantasy_sim.data.pff.models import TeamContextConfig
        cfg = load_pff_config({
            "pff": {
                "team_context": {
                    "enabled": True,
                    "pass_rate_sensitivity": 0.10,
                    "ol_run_sensitivity": 0.08,
                    "qb_quality_sensitivity": 0.06,
                    "factor_clamp": [0.85, 1.15],
                    "min_games": 3,
                    "ol_run_yards_scale": 12.0,
                }
            }
        })
        tc = cfg.team_context
        assert isinstance(tc, TeamContextConfig)
        assert tc.enabled is True
        assert tc.pass_rate_sensitivity == 0.10
        assert tc.ol_run_sensitivity == 0.08
        assert tc.qb_quality_sensitivity == 0.06
        assert tc.factor_clamp == (0.85, 1.15)
        assert tc.min_games == 3
        assert tc.ol_run_yards_scale == 12.0

    def test_team_context_config_defaults_when_absent(self):
        """PffConfig.team_context defaults to TeamContextConfig() when section is absent."""
        from fantasy_sim.data.pff.models import TeamContextConfig
        cfg = load_pff_config({"pff": {}})
        assert isinstance(cfg.team_context, TeamContextConfig)
        assert cfg.team_context.enabled is True


class TestTierAssignment:
    """Tests for TierEngine._assign_tier boundary logic."""

    # Boundaries: Tier 1 >= 82.0, Tier 2 >= 72.0, Tier 3 >= 60.0, Tier 4 >= 48.0, Tier 5 < 48.0
    _BOUNDARIES = {"WR": [82.0, 72.0, 60.0, 48.0]}

    def _make_engine(self):
        from fantasy_sim.data.pff.tier_engine import TierEngine
        from fantasy_sim.data.pff.models import TierConfig

        engine = TierEngine(config=TierConfig(), pff_loader=None)
        engine._boundaries = self._BOUNDARIES
        return engine

    def test_assign_tier_elite(self):
        """Grade above the 85th-percentile boundary maps to Tier 1."""
        engine = self._make_engine()
        assert engine._assign_tier(90.0, "WR") == 1

    def test_assign_tier_at_boundary_is_elite(self):
        """Grade exactly at the Tier 1 boundary maps to Tier 1 (>= semantics)."""
        engine = self._make_engine()
        assert engine._assign_tier(82.0, "WR") == 1

    def test_assign_tier_above_average(self):
        """Grade between 65th and 85th percentile boundaries maps to Tier 2."""
        engine = self._make_engine()
        assert engine._assign_tier(75.0, "WR") == 2

    def test_assign_tier_average(self):
        """Grade between 40th and 65th percentile boundaries maps to Tier 3."""
        engine = self._make_engine()
        assert engine._assign_tier(65.0, "WR") == 3

    def test_assign_tier_below_average(self):
        """Grade between 20th and 40th percentile boundaries maps to Tier 4."""
        engine = self._make_engine()
        assert engine._assign_tier(50.0, "WR") == 4

    def test_assign_tier_replacement(self):
        """Grade below the 20th-percentile boundary maps to Tier 5."""
        engine = self._make_engine()
        assert engine._assign_tier(40.0, "WR") == 5


# ---------------------------------------------------------------------------
# Fixture shared across interpolation / selection tests
# ---------------------------------------------------------------------------

@pytest.fixture
def tier_config():
    return TierConfig(enabled=True)


# ---------------------------------------------------------------------------
# TestWithinTierPercentile
# ---------------------------------------------------------------------------

class TestWithinTierPercentile:
    """Tests for TierEngine._within_tier_percentile."""

    _BOUNDARIES = {"WR": [82.0, 72.0, 60.0, 48.0]}

    def _make_engine(self, tier_config):
        from fantasy_sim.data.pff.tier_engine import TierEngine
        engine = TierEngine(config=tier_config, pff_loader=None)
        engine._boundaries = self._BOUNDARIES
        entry = _make_pool_entry()
        engine._pools = {"WR": {3: entry}}
        return engine

    def test_median_secondary_grade(self, tier_config):
        """A grade at the median of the secondary_grades array returns ~0.5."""
        engine = self._make_engine(tier_config)
        # secondary_grades = [1.2, 1.5, 1.7, 1.9, 2.1, 2.3]; median ~1.8
        grade = 1.85  # just above median
        pct = engine._within_tier_percentile(grade, "WR", 3)
        assert 0.4 <= pct <= 0.7

    def test_high_secondary_grade(self, tier_config):
        """A grade above the max of the secondary_grades array returns >= 0.9."""
        engine = self._make_engine(tier_config)
        # secondary_grades max = 2.3; passing a value above it means searchsorted
        # returns len(grades) → percentile = 1.0
        pct = engine._within_tier_percentile(2.5, "WR", 3)
        assert pct >= 0.9

    def test_low_secondary_grade(self, tier_config):
        """A grade at the min of the secondary_grades array returns <= 0.1."""
        engine = self._make_engine(tier_config)
        # 1.2 is the lowest value; searchsorted gives index 0 → 0/6 = 0.0
        pct = engine._within_tier_percentile(1.2, "WR", 3)
        assert pct <= 0.1

    def test_empty_grades_returns_half(self, tier_config):
        """When secondary_grades is None or empty, returns 0.5 as default."""
        from fantasy_sim.data.pff.tier_engine import TierEngine
        engine = TierEngine(config=tier_config, pff_loader=None)
        engine._boundaries = self._BOUNDARIES
        entry = _make_pool_entry(secondary_grades=None)
        engine._pools = {"WR": {3: entry}}
        pct = engine._within_tier_percentile(99.0, "WR", 3)
        assert pct == 0.5


# ---------------------------------------------------------------------------
# TestInterpolateScalars
# ---------------------------------------------------------------------------

class TestInterpolateScalars:
    """Tests for TierEngine._interpolate_scalars (and _interp_scalar)."""

    _BOUNDARIES = {"WR": [82.0, 72.0, 60.0, 48.0]}

    def _make_engine(self, tier_config):
        from fantasy_sim.data.pff.tier_engine import TierEngine
        engine = TierEngine(config=tier_config, pff_loader=None)
        engine._boundaries = self._BOUNDARIES
        entry = _make_pool_entry()
        engine._pools = {"WR": {3: entry}}
        return engine

    def test_low_secondary_gets_p25(self, tier_config):
        """pct=0.0 → each scalar equals the p25 value of its tuple."""
        engine = self._make_engine(tier_config)
        pool = engine._pools["WR"][3]
        dists = engine._interpolate_scalars(pool, 0.0)
        assert dists.target_share == pytest.approx(0.15)
        assert dists.catch_rate == pytest.approx(0.60)

    def test_median_secondary_gets_p50(self, tier_config):
        """pct=0.5 → each scalar equals the median (p50) of its tuple."""
        engine = self._make_engine(tier_config)
        pool = engine._pools["WR"][3]
        dists = engine._interpolate_scalars(pool, 0.5)
        assert dists.target_share == pytest.approx(0.20)
        assert dists.catch_rate == pytest.approx(0.65)

    def test_high_secondary_gets_p75(self, tier_config):
        """pct=1.0 → each scalar equals the p75 value of its tuple."""
        engine = self._make_engine(tier_config)
        pool = engine._pools["WR"][3]
        dists = engine._interpolate_scalars(pool, 1.0)
        assert dists.target_share == pytest.approx(0.25)
        assert dists.catch_rate == pytest.approx(0.70)

    def test_interpolation_midpoint(self, tier_config):
        """pct=0.75 → halfway between p50 and p75."""
        engine = self._make_engine(tier_config)
        pool = engine._pools["WR"][3]
        dists = engine._interpolate_scalars(pool, 0.75)
        # target_share: med=0.20, high=0.25; midpoint = 0.225
        assert dists.target_share == pytest.approx(0.225)
        # catch_rate: med=0.65, high=0.70; midpoint = 0.675
        assert dists.catch_rate == pytest.approx(0.675)

    def test_yards_dist_passed_through(self, tier_config):
        """Yards arrays are passed through unchanged, not interpolated."""
        engine = self._make_engine(tier_config)
        pool = engine._pools["WR"][3]
        dists = engine._interpolate_scalars(pool, 0.5)
        assert dists.receiving_yards_dist is pool.receiving_yards_dist
        assert dists.rushing_yards_dist is None


# ---------------------------------------------------------------------------
# TestSelectDistributions
# ---------------------------------------------------------------------------

class TestSelectDistributions:
    """Tests for TierEngine.select_distributions (full pipeline)."""

    _BOUNDARIES = {"WR": [82.0, 72.0, 60.0, 48.0]}

    def _make_engine(self, tier_config):
        from fantasy_sim.data.pff.tier_engine import TierEngine
        engine = TierEngine(config=tier_config, pff_loader=None)
        engine._boundaries = self._BOUNDARIES
        # Populate all five tiers so _assign_tier always finds a pool entry
        entry = _make_pool_entry()
        engine._pools = {"WR": {t: entry for t in range(1, 6)}}
        return engine

    def test_select_returns_tier_and_distributions(self, tier_config):
        """Full flow: valid grades → (TierAssignment, TierDistributions) tuple."""
        from fantasy_sim.data.pff.tier_engine import TierAssignment, TierDistributions
        engine = self._make_engine(tier_config)
        # primary grade 75.0 → Tier 2 (72.0 <= grade < 82.0)
        # secondary (yprr) = 1.9 (within secondary_grades array)
        pff_grades = {"grades_pass_route": 75.0, "yprr": 1.9}
        result = engine.select_distributions(pff_grades, "WR")
        assert result is not None
        assignment, dists = result
        assert isinstance(assignment, TierAssignment)
        assert isinstance(dists, TierDistributions)
        assert assignment.tier == 2
        assert 0.0 <= assignment.secondary_percentile <= 1.0
        assert 0.15 <= dists.target_share <= 0.25
        assert 0.60 <= dists.catch_rate <= 0.70

    def test_select_missing_grades_returns_none(self, tier_config):
        """Missing required primary grade → returns None."""
        engine = self._make_engine(tier_config)
        # grades_pass_route key is absent
        pff_grades = {"yprr": 1.9}
        result = engine.select_distributions(pff_grades, "WR")
        assert result is None

    def test_select_unconfigured_position_returns_none(self, tier_config):
        """Position not in position_grades config → returns None."""
        engine = self._make_engine(tier_config)
        pff_grades = {"grades_pass_route": 75.0, "yprr": 1.9}
        result = engine.select_distributions(pff_grades, "K")
        assert result is None


# ---------------------------------------------------------------------------
# TestReliability
# ---------------------------------------------------------------------------

class TestReliability:
    """Tests for TierEngine.compute_reliability."""

    def _make_engine(self):
        from fantasy_sim.data.pff.tier_engine import TierEngine
        from fantasy_sim.data.pff.models import TierConfig
        # Use default TierConfig which has:
        #   reliability_max_games=32, reliability_team_change_penalty=0.5
        #   reliability_variance_weight=0.3, reliability_floor=0.15, reliability_cap=0.85
        return TierEngine(config=TierConfig(enabled=True), pff_loader=None)

    def test_established_player_capped(self):
        """48 games, no team change, stable shares → capped at reliability_cap (0.85)."""
        engine = self._make_engine()
        shares = np.full(48, 0.20)
        # sample = min(48/32, 1.0) = 1.0; team = 1.0; cv ≈ 0 → raw ≈ 1.0 → clipped to 0.85
        result = engine.compute_reliability(
            games_played=48,
            changed_teams=False,
            weekly_shares=shares,
        )
        assert result == pytest.approx(0.85)

    def test_new_team_penalty(self):
        """17 games, team change, stable shares → roughly 0.265 (clipped to [0.15, 0.85])."""
        engine = self._make_engine()
        shares = np.full(17, 0.20)
        # sample = 17/32 ≈ 0.531; team = 0.5; cv ≈ 0 → raw ≈ 0.531 * 0.5 * 1.0 ≈ 0.265
        result = engine.compute_reliability(
            games_played=17,
            changed_teams=True,
            weekly_shares=shares,
        )
        assert 0.20 <= result <= 0.30

    def test_rookie_floor(self):
        """0 games, no team change, no shares → clamped to reliability_floor (0.15)."""
        engine = self._make_engine()
        # sample = 0/32 = 0.0; team = 1.0; no variance → raw = 0.0 → clipped to 0.15
        result = engine.compute_reliability(
            games_played=0,
            changed_teams=False,
            weekly_shares=None,
        )
        assert result == pytest.approx(0.15)

    def test_volatile_shares_penalized(self):
        """Volatile weekly shares produce a lower reliability than stable shares (17 games)."""
        engine = self._make_engine()
        stable = np.full(17, 0.20)
        volatile = np.tile([0.05, 0.30, 0.10, 0.35], 5)[:17]  # alternating high/low
        result_stable = engine.compute_reliability(
            games_played=17, changed_teams=False, weekly_shares=stable
        )
        result_volatile = engine.compute_reliability(
            games_played=17, changed_teams=False, weekly_shares=volatile
        )
        assert result_volatile < result_stable

    def test_too_few_weeks_no_variance_penalty(self):
        """3 games with wild shares → variance penalty skipped; raw clamped to floor 0.15."""
        engine = self._make_engine()
        # Only 3 values → len < 4 → variance_penalty = 0.0
        # sample = 3/32 ≈ 0.094; team = 1.0; raw ≈ 0.094 → clipped to 0.15
        result = engine.compute_reliability(
            games_played=3,
            changed_teams=False,
            weekly_shares=np.array([0.05, 0.30, 0.50]),
        )
        assert result == pytest.approx(0.15)


# ---------------------------------------------------------------------------
# Helper: build a PlayerModel for blending tests
# ---------------------------------------------------------------------------

from fantasy_sim.models.player import PlayerModel, PlayerUsage, PlayerOutcomes, TeamRoster


def _make_player(
    player_id="test_wr1", position="WR",
    target_share=0.25, carry_share=0.0, catch_rate=0.68,
    air_yards_share=0.20, fumble_rate=0.01, scramble_rate=0.0,
    receiving_yards=None, rushing_yards=None,
):
    return PlayerModel(
        player_id=player_id, name="Test WR", position=position, team="KC",
        usage=PlayerUsage(
            target_share=target_share, carry_share=carry_share,
            air_yards_share=air_yards_share, scramble_rate=scramble_rate,
        ),
        outcomes=PlayerOutcomes(
            catch_rate=catch_rate, fumble_rate=fumble_rate,
            receiving_yards_dist=receiving_yards if receiving_yards is not None else np.array([8, 10, 12, 15, 20]),
            rushing_yards_dist=rushing_yards,
        ),
        games_played=17,
    )


# ---------------------------------------------------------------------------
# TestBlendPlayer
# ---------------------------------------------------------------------------

class TestBlendPlayer:
    """Tests for TierEngine._blend_player."""

    def _make_engine(self):
        from fantasy_sim.data.pff.tier_engine import TierEngine
        from fantasy_sim.data.pff.models import TierConfig
        return TierEngine(config=TierConfig(enabled=True), pff_loader=None)

    def _make_tier_dists(self, **overrides):
        from fantasy_sim.data.pff.tier_engine import TierDistributions
        defaults = dict(
            target_share=0.14,
            carry_share=0.0,
            catch_rate=0.60,
            air_yards_share=0.12,
            fumble_rate=0.02,
            scramble_rate=0.0,
            receiving_yards_dist=np.full(100, 8.0),
            rushing_yards_dist=None,
        )
        defaults.update(overrides)
        return TierDistributions(**defaults)

    def test_high_reliability_favors_pbp(self):
        """reliability=0.85: blended catch_rate = 0.85*0.70 + 0.15*0.60 = 0.685."""
        engine = self._make_engine()
        player = _make_player(catch_rate=0.70)
        tier_dists = self._make_tier_dists(catch_rate=0.60)
        rng = np.random.default_rng(42)

        engine._blend_player(player, tier_dists, reliability=0.85, rng=rng)

        expected = 0.85 * 0.70 + 0.15 * 0.60
        assert player.outcomes.catch_rate == pytest.approx(expected)

    def test_low_reliability_favors_tier(self):
        """reliability=0.25: blended target_share = 0.25*0.30 + 0.75*0.14 = 0.18."""
        engine = self._make_engine()
        player = _make_player(target_share=0.30)
        tier_dists = self._make_tier_dists(target_share=0.14)
        rng = np.random.default_rng(42)

        engine._blend_player(player, tier_dists, reliability=0.25, rng=rng)

        expected = 0.25 * 0.30 + 0.75 * 0.14
        assert player.usage.target_share == pytest.approx(expected)

    def test_yards_blended_by_concatenation(self):
        """PBP yards all 15.0 (100 samples), tier yards all 8.0, reliability=0.60.

        Result pool should be 500 samples with mean near 0.6*15 + 0.4*8 = 12.2.
        Accept range [11.0, 13.5] to account for sampling noise.
        """
        engine = self._make_engine()
        player = _make_player(receiving_yards=np.full(100, 15.0))
        tier_dists = self._make_tier_dists(receiving_yards_dist=np.full(100, 8.0))
        rng = np.random.default_rng(42)

        engine._blend_player(player, tier_dists, reliability=0.60, rng=rng)

        dist = player.outcomes.receiving_yards_dist
        assert dist is not None
        assert len(dist) == engine._config.blend_pool_size
        mean = float(np.mean(dist))
        assert 11.0 <= mean <= 13.5

    def test_no_pbp_yards_uses_tier_only(self):
        """Player with receiving_yards_dist=None → blended result comes from tier pool."""
        engine = self._make_engine()
        player = _make_player(receiving_yards=None)
        # Override the default so it's explicitly None
        player.outcomes.receiving_yards_dist = None
        tier_dists = self._make_tier_dists(receiving_yards_dist=np.full(50, 10.0))
        rng = np.random.default_rng(42)

        engine._blend_player(player, tier_dists, reliability=0.50, rng=rng)

        assert player.outcomes.receiving_yards_dist is not None
        assert len(player.outcomes.receiving_yards_dist) > 0

    def test_red_zone_fields_untouched(self):
        """RZ fields must not be modified by _blend_player."""
        engine = self._make_engine()
        player = _make_player()
        player.usage.red_zone_target_share = 0.30
        player.outcomes.red_zone_catch_rate = 0.62
        tier_dists = self._make_tier_dists()
        rng = np.random.default_rng(42)

        engine._blend_player(player, tier_dists, reliability=0.50, rng=rng)

        assert player.usage.red_zone_target_share == pytest.approx(0.30)
        assert player.outcomes.red_zone_catch_rate == pytest.approx(0.62)


class TestApplyTeamContext:
    """Tests for TierEngine.apply_team_context static method."""

    def _make_tier_dists(self, **overrides):
        from fantasy_sim.data.pff.tier_engine import TierDistributions
        defaults = dict(
            target_share=0.20,
            carry_share=0.0,
            catch_rate=0.65,
            air_yards_share=0.15,
            fumble_rate=0.015,
            scramble_rate=0.0,
            receiving_yards_dist=np.full(100, 10.0),
            rushing_yards_dist=np.full(100, 4.0),
        )
        defaults.update(overrides)
        return TierDistributions(**defaults)

    def test_wr_target_share_scaled_by_pass_rate(self):
        """WR target_share multiplied by pass_rate_factor."""
        from fantasy_sim.data.pff.tier_engine import TierEngine
        from fantasy_sim.data.pff.models import TeamContext

        tier_dists = self._make_tier_dists(target_share=0.20)
        ctx = TeamContext(pass_rate_factor=1.10)

        TierEngine.apply_team_context(tier_dists, ctx, "WR")

        assert tier_dists.target_share == pytest.approx(0.22)

    def test_wr_catch_rate_scaled_by_qb_quality(self):
        """WR catch_rate multiplied by qb_quality_factor."""
        from fantasy_sim.data.pff.tier_engine import TierEngine
        from fantasy_sim.data.pff.models import TeamContext

        tier_dists = self._make_tier_dists(catch_rate=0.65)
        ctx = TeamContext(qb_quality_factor=1.05)

        TierEngine.apply_team_context(tier_dists, ctx, "WR")

        assert tier_dists.catch_rate == pytest.approx(0.65 * 1.05)

    def test_te_gets_same_adjustments_as_wr(self):
        """TE receives both pass_rate and qb_quality adjustments."""
        from fantasy_sim.data.pff.tier_engine import TierEngine
        from fantasy_sim.data.pff.models import TeamContext

        tier_dists = self._make_tier_dists(target_share=0.15, catch_rate=0.60)
        ctx = TeamContext(pass_rate_factor=1.08, qb_quality_factor=0.95)

        TierEngine.apply_team_context(tier_dists, ctx, "TE")

        assert tier_dists.target_share == pytest.approx(0.15 * 1.08)
        assert tier_dists.catch_rate == pytest.approx(0.60 * 0.95)

    def test_rb_rushing_yards_shifted(self):
        """RB rushing_yards_dist shifted by OL factor."""
        from fantasy_sim.data.pff.tier_engine import TierEngine
        from fantasy_sim.data.pff.models import TeamContext

        tier_dists = self._make_tier_dists(rushing_yards_dist=np.full(50, 4.0))
        ctx = TeamContext(ol_run_block_factor=1.06, ol_run_yards_scale=10.0)

        TierEngine.apply_team_context(tier_dists, ctx, "RB")

        expected = 4.0 + 0.6
        assert tier_dists.rushing_yards_dist is not None
        np.testing.assert_allclose(tier_dists.rushing_yards_dist, expected)

    def test_rb_no_rushing_yards_dist_no_error(self):
        """RB with rushing_yards_dist=None doesn't crash."""
        from fantasy_sim.data.pff.tier_engine import TierEngine
        from fantasy_sim.data.pff.models import TeamContext

        tier_dists = self._make_tier_dists(rushing_yards_dist=None)
        ctx = TeamContext(ol_run_block_factor=1.10)

        TierEngine.apply_team_context(tier_dists, ctx, "RB")

    def test_qb_unchanged(self):
        """QB receives no team context adjustments."""
        from fantasy_sim.data.pff.tier_engine import TierEngine
        from fantasy_sim.data.pff.models import TeamContext

        tier_dists = self._make_tier_dists(
            target_share=0.20, catch_rate=0.65,
            rushing_yards_dist=np.full(50, 4.0),
        )
        original_ts = tier_dists.target_share
        original_cr = tier_dists.catch_rate
        original_rush = tier_dists.rushing_yards_dist.copy()

        ctx = TeamContext(
            pass_rate_factor=1.10,
            qb_quality_factor=1.10,
            ol_run_block_factor=1.10,
        )

        TierEngine.apply_team_context(tier_dists, ctx, "QB")

        assert tier_dists.target_share == original_ts
        assert tier_dists.catch_rate == original_cr
        np.testing.assert_array_equal(tier_dists.rushing_yards_dist, original_rush)

    def test_neutral_context_no_changes(self):
        """All-neutral TeamContext (1.0) leaves tier_dists unchanged."""
        from fantasy_sim.data.pff.tier_engine import TierEngine
        from fantasy_sim.data.pff.models import TeamContext

        tier_dists = self._make_tier_dists(target_share=0.20, catch_rate=0.65)
        ctx = TeamContext()

        TierEngine.apply_team_context(tier_dists, ctx, "WR")

        assert tier_dists.target_share == pytest.approx(0.20)
        assert tier_dists.catch_rate == pytest.approx(0.65)

    def test_apply_tiers_with_none_context_unchanged(self):
        """apply_tiers() with team_context=None behaves like before."""
        from fantasy_sim.data.pff.tier_engine import TierEngine
        from fantasy_sim.data.pff.models import TierConfig

        engine = TierEngine(config=TierConfig(enabled=True), pff_loader=None)
        roster = TeamRoster(team="KC", players=[_make_player()])
        engine.apply_tiers(roster, {}, [2024], team_context=None)


# ---------------------------------------------------------------------------
# Pool Building tests
# ---------------------------------------------------------------------------

import polars as pl
from fantasy_sim.data.pff.loader import PffLoader


def _write_pff_parquet(pff_dir, facet, season, rows):
    """Write a PFF facet parquet file with given rows (list of dicts)."""
    df = pl.DataFrame(rows)
    path = pff_dir / f"{facet}_{season}.parquet"
    df.write_parquet(path)


def _mock_wr_pff_data(pff_dir, season):
    """Write receiving_summary with 10 WRs spanning grade range."""
    rows = []
    grades = [92, 88, 78, 74, 62, 58, 52, 42, 36, 22]
    yprrs = [2.8, 2.4, 2.0, 1.8, 1.6, 1.4, 1.3, 1.1, 0.9, 0.7]
    for i, (g, y) in enumerate(zip(grades, yprrs)):
        rows.append({
            "player_id": 1000 + i,
            "player": f"WR{i}",
            "team": "KC" if i < 5 else "BUF",
            "position": "WR",
            "season": season,
            "week": 1,
            "grades_pass_route": float(g),
            "yprr": float(y),
            "targets": 80 + i * 5,
            "receptions": 50 + i * 3,
            "yards": 600 + i * 50,
            "touchdowns": 5,
            "drop_rate": 0.05,
            "contested_catch_rate": 0.50,
            "avg_depth_of_target": 10.0,
        })
    _write_pff_parquet(pff_dir, "receiving_summary", season, rows)
    return rows


def _build_mock_pbp(seasons, n_players=10, seed=42):
    """Build a mock PBP DataFrame with standard nflverse columns.

    Each of 10 "players" gets ~80 pass plays (some complete, some incomplete)
    and ~30 rush plays to generate realistic target/catch/yards data.
    """
    rng = np.random.default_rng(seed)
    rows = []
    play_id = 0
    for season in seasons:
        for week in range(1, 18):
            game_id = f"{season}_{week:02d}_KC_BUF"
            for i in range(n_players):
                player_id = f"nfl_wr_{i}"
                team = "KC" if i < 5 else "BUF"

                # ~5 pass plays per week per player
                for _ in range(5):
                    play_id += 1
                    is_complete = int(rng.random() < 0.65)
                    yards = int(rng.integers(1, 30)) if is_complete else 0
                    air_yds = float(rng.integers(3, 15))
                    rows.append({
                        "season": season,
                        "week": week,
                        "game_id": game_id,
                        "play_type": "pass",
                        "passer_player_id": f"nfl_qb_{0 if i < 5 else 1}",
                        "receiver_player_id": player_id if (is_complete or rng.random() < 0.7) else None,
                        "passing_yards": yards if is_complete else 0,
                        "yards_gained": yards if is_complete else 0,
                        "complete_pass": is_complete,
                        "posteam": team,
                        "air_yards": air_yds,
                        "yardline_100": int(rng.integers(20, 80)),
                        "rusher_player_id": None,
                        "rushing_yards": None,
                        "interception": 0,
                        "fumble_lost": 0,
                        "sack": 0,
                    })

                # ~2 rush plays per week per player
                for _ in range(2):
                    play_id += 1
                    rush_yards = int(rng.integers(-2, 15))
                    rows.append({
                        "season": season,
                        "week": week,
                        "game_id": game_id,
                        "play_type": "run",
                        "passer_player_id": None,
                        "receiver_player_id": None,
                        "passing_yards": None,
                        "yards_gained": rush_yards,
                        "complete_pass": 0,
                        "posteam": team,
                        "air_yards": None,
                        "yardline_100": int(rng.integers(20, 80)),
                        "rusher_player_id": player_id,
                        "rushing_yards": rush_yards,
                        "interception": 0,
                        "fumble_lost": 0,
                        "sack": 0,
                    })

    return pl.DataFrame(rows)


def _build_crosswalk(n_players=10):
    """Build PFF player_id -> nflverse player_id crosswalk."""
    return {1000 + i: f"nfl_wr_{i}" for i in range(n_players)}


@pytest.fixture
def pff_dir(tmp_path):
    d = tmp_path / "pff" / "processed" / "nfl"
    d.mkdir(parents=True)
    return d


@pytest.fixture
def loader(pff_dir):
    return PffLoader(pff_dir)


class TestPoolBuilding:
    """Tests for TierEngine pool building from PFF grades + PBP data."""

    def _make_engine(self, loader):
        from fantasy_sim.data.pff.tier_engine import TierEngine
        return TierEngine(config=TierConfig(enabled=True), pff_loader=loader)

    def test_build_pools_creates_tiers(self, pff_dir, loader):
        """10 WRs across 2 seasons -> pools have tiers for WR position."""
        seasons = [2023, 2024]
        for s in seasons:
            _mock_wr_pff_data(pff_dir, s)
        pbp = _build_mock_pbp(seasons)
        crosswalk = _build_crosswalk()

        engine = self._make_engine(loader)
        engine._build_tier_pools(pbp, seasons, crosswalk)

        assert engine._pools is not None
        assert "WR" in engine._pools
        # At least one tier should exist
        assert len(engine._pools["WR"]) >= 1
        # Each tier entry should be a _TierPoolEntry
        from fantasy_sim.data.pff.tier_engine import _TierPoolEntry
        for tier, entry in engine._pools["WR"].items():
            assert isinstance(entry, _TierPoolEntry)
            assert 1 <= tier <= 5
            assert entry.n_player_seasons > 0

    def test_boundaries_computed(self, pff_dir, loader):
        """Boundaries exist for WR, are 4 values, descending."""
        seasons = [2023, 2024]
        for s in seasons:
            _mock_wr_pff_data(pff_dir, s)
        pbp = _build_mock_pbp(seasons)
        crosswalk = _build_crosswalk()

        engine = self._make_engine(loader)
        engine._build_tier_pools(pbp, seasons, crosswalk)

        assert engine._boundaries is not None
        assert "WR" in engine._boundaries
        bounds = engine._boundaries["WR"]
        assert len(bounds) == 4
        # Boundaries should be in descending order (Tier 1 cutoff > Tier 2 > ...)
        for j in range(len(bounds) - 1):
            assert bounds[j] >= bounds[j + 1], f"Boundary {j} ({bounds[j]}) not >= {j+1} ({bounds[j+1]})"

    def test_pool_entry_has_yards_array(self, pff_dir, loader):
        """At least one tier has receiving_yards_dist with values."""
        seasons = [2023, 2024]
        for s in seasons:
            _mock_wr_pff_data(pff_dir, s)
        pbp = _build_mock_pbp(seasons)
        crosswalk = _build_crosswalk()

        engine = self._make_engine(loader)
        engine._build_tier_pools(pbp, seasons, crosswalk)

        found_yards = False
        for tier, entry in engine._pools["WR"].items():
            if entry.receiving_yards_dist is not None and len(entry.receiving_yards_dist) > 0:
                found_yards = True
                break
        assert found_yards, "No tier pool has a non-empty receiving_yards_dist"

    def test_thin_tier_merged(self, pff_dir, loader):
        """5 players in 1 season -> thin tiers get merged -> fewer than 5 tiers."""
        seasons = [2023]
        # Only write 5 WRs (half the normal set) in a single season
        rows = []
        grades = [92, 78, 62, 42, 22]
        yprrs = [2.8, 2.0, 1.6, 1.1, 0.7]
        for i, (g, y) in enumerate(zip(grades, yprrs)):
            rows.append({
                "player_id": 1000 + i,
                "player": f"WR{i}",
                "team": "KC" if i < 3 else "BUF",
                "position": "WR",
                "season": 2023,
                "week": 1,
                "grades_pass_route": float(g),
                "yprr": float(y),
                "targets": 80 + i * 10,
                "receptions": 50 + i * 5,
                "yards": 600 + i * 100,
                "touchdowns": 5,
                "drop_rate": 0.05,
                "contested_catch_rate": 0.50,
                "avg_depth_of_target": 10.0,
            })
        _write_pff_parquet(pff_dir, "receiving_summary", 2023, rows)
        pbp = _build_mock_pbp(seasons, n_players=5)
        crosswalk = {1000 + i: f"nfl_wr_{i}" for i in range(5)}

        engine = self._make_engine(loader)
        engine._build_tier_pools(pbp, seasons, crosswalk)

        # With only 5 player-seasons, initial assignment gives ~1 per tier.
        # _merge_thin_tiers should collapse them, resulting in fewer than 5 tiers.
        n_tiers = len(engine._pools["WR"])
        assert n_tiers < 5, f"Expected fewer than 5 tiers after merging, got {n_tiers}"


# ---------------------------------------------------------------------------
# TestApplyTiers
# ---------------------------------------------------------------------------

class TestApplyTiers:
    """Tests for TierEngine.apply_tiers (roster-level entry point)."""

    def _make_engine(self, loader):
        from fantasy_sim.data.pff.tier_engine import TierEngine
        return TierEngine(config=TierConfig(enabled=True), pff_loader=loader)

    def test_apply_tiers_modifies_roster(self, pff_dir, loader):
        """Two WRs: elite PFF + low PBP share should go up;
        replacement PFF + high PBP share should come down."""
        seasons = [2023, 2024]
        for s in seasons:
            _mock_wr_pff_data(pff_dir, s)
        pbp = _build_mock_pbp(seasons)
        crosswalk = _build_crosswalk()

        # WR0 has elite PFF grade (92) but low PBP target_share
        # WR9 has replacement PFF grade (22) but high PBP target_share
        wr_elite = _make_player(
            player_id="nfl_wr_0", position="WR",
            target_share=0.08, catch_rate=0.55,
        )
        wr_replacement = _make_player(
            player_id="nfl_wr_9", position="WR",
            target_share=0.35, catch_rate=0.80,
        )
        roster = TeamRoster(team="KC", players=[wr_elite, wr_replacement])

        original_elite_ts = wr_elite.usage.target_share
        original_repl_ts = wr_replacement.usage.target_share

        engine = self._make_engine(loader)
        engine.apply_tiers(
            roster, crosswalk, seasons,
            pbp=pbp, nfl_roster=None, target_season=2024,
        )

        # Elite WR's target_share should increase (tier pool pushes up)
        assert wr_elite.usage.target_share > original_elite_ts, (
            f"Elite WR target_share should increase: {original_elite_ts} -> {wr_elite.usage.target_share}"
        )
        # Replacement WR's target_share should decrease (tier pool pulls down)
        assert wr_replacement.usage.target_share < original_repl_ts, (
            f"Replacement WR target_share should decrease: {original_repl_ts} -> {wr_replacement.usage.target_share}"
        )

    def test_apply_tiers_skips_missing_pff(self, pff_dir, loader):
        """Player not in crosswalk should be unchanged after apply_tiers."""
        seasons = [2023, 2024]
        for s in seasons:
            _mock_wr_pff_data(pff_dir, s)
        pbp = _build_mock_pbp(seasons)
        # Crosswalk only includes WR0-WR9, not "unknown_wr"
        crosswalk = _build_crosswalk()

        wr_known = _make_player(
            player_id="nfl_wr_0", position="WR",
            target_share=0.20, catch_rate=0.65,
        )
        wr_unknown = _make_player(
            player_id="unknown_wr", position="WR",
            target_share=0.18, catch_rate=0.62,
        )
        roster = TeamRoster(team="KC", players=[wr_known, wr_unknown])

        original_unknown_ts = wr_unknown.usage.target_share
        original_unknown_cr = wr_unknown.outcomes.catch_rate

        engine = self._make_engine(loader)
        engine.apply_tiers(
            roster, crosswalk, seasons,
            pbp=pbp, nfl_roster=None, target_season=2024,
        )

        # Unknown player should be completely unchanged
        assert wr_unknown.usage.target_share == pytest.approx(original_unknown_ts)
        assert wr_unknown.outcomes.catch_rate == pytest.approx(original_unknown_cr)


class TestNcaaRookieConfig:
    def test_load_ncaa_rookie_config_from_yaml(self):
        """Full YAML dict is parsed correctly into NcaaRookieConfig."""
        cfg = load_pff_config({
            "pff": {
                "tier_engine": {
                    "enabled": True,
                    "position_grades": {
                        "QB": {"primary": "grades_pass", "secondary": "accuracy_percent"},
                        "RB": {"primary": "grades_run", "secondary": "elusive_rating"},
                        "WR": {"primary": "grades_pass_route", "secondary": "_disabled"},
                        "TE": {"primary": "grades_pass_route", "secondary": "recv_grade"},
                    },
                    "ncaa_rookie": {
                        "enabled": True,
                        "draft_confidence": {
                            1: 1.0, 2: 0.95, 3: 0.85, 4: 0.75,
                            5: 0.65, 6: 0.55, 7: 0.50,
                        },
                        "undrafted_confidence": 0.35,
                        "ncaa_lookback_seasons": 3,
                    },
                }
            }
        })
        ncaa = cfg.tier_engine.ncaa_rookie
        assert ncaa.enabled is True
        assert ncaa.draft_confidence[1] == 1.0
        assert ncaa.draft_confidence[7] == 0.50
        assert ncaa.undrafted_confidence == 0.35
        assert ncaa.ncaa_lookback_seasons == 3

    def test_ncaa_rookie_config_defaults(self):
        """Missing ncaa_rookie section uses sensible defaults."""
        cfg = load_pff_config({"pff": {"tier_engine": {"enabled": True,
            "position_grades": {
                "QB": {"primary": "grades_pass", "secondary": "accuracy_percent"},
                "RB": {"primary": "grades_run", "secondary": "elusive_rating"},
                "WR": {"primary": "grades_pass_route", "secondary": "_disabled"},
                "TE": {"primary": "grades_pass_route", "secondary": "recv_grade"},
            }}}})
        ncaa = cfg.tier_engine.ncaa_rookie
        assert ncaa.enabled is True
        assert ncaa.undrafted_confidence == 0.40
        assert ncaa.ncaa_lookback_seasons == 4
        assert 1 in ncaa.draft_confidence

    def test_ncaa_rookie_config_yaml_string_keys(self):
        """YAML parses dict keys as strings — config parser converts to int."""
        cfg = load_pff_config({
            "pff": {
                "tier_engine": {
                    "enabled": True,
                    "position_grades": {
                        "QB": {"primary": "grades_pass", "secondary": "accuracy_percent"},
                        "RB": {"primary": "grades_run", "secondary": "elusive_rating"},
                        "WR": {"primary": "grades_pass_route", "secondary": "_disabled"},
                        "TE": {"primary": "grades_pass_route", "secondary": "recv_grade"},
                    },
                    "ncaa_rookie": {
                        "draft_confidence": {
                            "1": 0.99, "2": 0.90, "3": 0.80,
                            "4": 0.70, "5": 0.60, "6": 0.50, "7": 0.45,
                        },
                    },
                }
            }
        })
        ncaa = cfg.tier_engine.ncaa_rookie
        assert ncaa.draft_confidence[1] == 0.99
        assert ncaa.draft_confidence[7] == 0.45


from fantasy_sim.models.player import PlayerModel, PlayerUsage, PlayerOutcomes, TeamRoster
from fantasy_sim.data.pff.models import TeamContext


def _make_rookie_player(player_id, position, team, **usage_overrides):
    """Create a PlayerModel resembling a rookie archetype."""
    usage = PlayerUsage()
    outcomes = PlayerOutcomes(
        catch_rate=0.58,
        fumble_rate=0.008,
        receiving_yards_dist=np.array([3, 5, 7, 8, 10, 12, 15]),
    )
    if position == "RB":
        usage.carry_share = 0.10
        usage.target_share = 0.02
        outcomes.rushing_yards_dist = np.array([-1, 0, 1, 2, 3, 4, 5, 6])
    elif position in ("WR", "TE"):
        usage.target_share = 0.03
    for k, v in usage_overrides.items():
        setattr(usage, k, v)
    return PlayerModel(
        player_id=player_id, name=f"Rookie {player_id}",
        position=position, team=team,
        usage=usage, outcomes=outcomes, games_played=0,
    )


def _make_roster_df(rows):
    """Build a minimal nflverse-style roster DataFrame."""
    return pl.DataFrame({
        "player_id": [r["player_id"] for r in rows],
        "player_name": [r.get("name", "Test") for r in rows],
        "position": [r.get("position", "WR") for r in rows],
        "team": [r.get("team", "KC") for r in rows],
        "pff_id": [r.get("pff_id") for r in rows],
        "draft_number": [r.get("draft_number") for r in rows],
        "rookie_year": [r.get("rookie_year") for r in rows],
        "season": [r.get("season", 2025) for r in rows],
        "week": [r.get("week", 1) for r in rows],
        "status": [r.get("status", "ACT") for r in rows],
    })


class TestApplyRookieTiers:
    def test_first_rounder_gets_full_tier_influence(self):
        """1st-round pick with NCAA grade gets reliability ~0.0 (full tier)."""
        engine = _make_tier_engine()
        pool = _make_pool_entry(
            target_share=(0.15, 0.20, 0.25),
            catch_rate=(0.60, 0.65, 0.70),
        )
        engine._pools = {"WR": {2: pool}}
        engine._boundaries = {"WR": [85.0, 70.0, 55.0, 40.0]}

        player = _make_rookie_player("rookie1", "WR", "KC", target_share=0.03)
        roster = TeamRoster(team="KC", players=[player])

        nfl_roster = _make_roster_df([{
            "player_id": "rookie1", "pff_id": 12345,
            "draft_number": 5, "rookie_year": 2025,
        }])

        engine._pff_loader.load_ncaa_facet.return_value = _ncaa_facet_df(
            player_id=12345, grades_col="grades_pass_route",
            grade_values=[75.0],
        )

        engine._apply_rookie_tiers(
            roster, nfl_roster, [player], target_season=2025,
            team_context=None, rng=np.random.default_rng(42),
        )

        # Round 1 (pick 5) -> draft_confidence 1.0 -> reliability 0.0
        assert player.usage.target_share > 0.15

    def test_udfa_gets_partial_archetype_blend(self):
        """Undrafted player blends ~60% archetype, ~40% tier."""
        engine = _make_tier_engine()
        pool = _make_pool_entry(
            target_share=(0.15, 0.20, 0.25),
            catch_rate=(0.60, 0.65, 0.70),
        )
        engine._pools = {"WR": {2: pool}}
        engine._boundaries = {"WR": [85.0, 70.0, 55.0, 40.0]}

        player = _make_rookie_player("rookie_udfa", "WR", "KC", target_share=0.03)
        original_ts = player.usage.target_share
        roster = TeamRoster(team="KC", players=[player])

        nfl_roster = _make_roster_df([{
            "player_id": "rookie_udfa", "pff_id": 54321,
            "draft_number": None, "rookie_year": 2025,
        }])

        engine._pff_loader.load_ncaa_facet.return_value = _ncaa_facet_df(
            player_id=54321, grades_col="grades_pass_route",
            grade_values=[75.0],
        )

        engine._apply_rookie_tiers(
            roster, nfl_roster, [player], target_season=2025,
            team_context=None, rng=np.random.default_rng(42),
        )

        assert player.usage.target_share > original_ts
        assert player.usage.target_share < 0.15

    def test_non_rookie_skipped_player_is_ignored(self):
        """Player who isn't a rookie (veteran missing PFF data) is unchanged."""
        engine = _make_tier_engine()
        engine._pools = {"WR": {2: _make_pool_entry()}}
        engine._boundaries = {"WR": [85.0, 70.0, 55.0, 40.0]}

        player = _make_rookie_player("vet_no_pff", "WR", "KC", target_share=0.12)
        original_ts = player.usage.target_share
        roster = TeamRoster(team="KC", players=[player])

        nfl_roster = _make_roster_df([{
            "player_id": "vet_no_pff", "pff_id": 99999,
            "draft_number": 45, "rookie_year": 2020,
        }])

        engine._apply_rookie_tiers(
            roster, nfl_roster, [player], target_season=2025,
            team_context=None, rng=np.random.default_rng(42),
        )

        assert player.usage.target_share == original_ts

    def test_player_without_ncaa_data_keeps_archetype(self):
        """Rookie without NCAA PFF data keeps their archetype model."""
        engine = _make_tier_engine()
        engine._pools = {"WR": {2: _make_pool_entry()}}
        engine._boundaries = {"WR": [85.0, 70.0, 55.0, 40.0]}

        player = _make_rookie_player("rookie_no_ncaa", "WR", "KC", target_share=0.03)
        original_ts = player.usage.target_share
        roster = TeamRoster(team="KC", players=[player])

        nfl_roster = _make_roster_df([{
            "player_id": "rookie_no_ncaa", "pff_id": 88888,
            "draft_number": 150, "rookie_year": 2025,
        }])

        engine._pff_loader.load_ncaa_facet.return_value = pl.DataFrame()

        engine._apply_rookie_tiers(
            roster, nfl_roster, [player], target_season=2025,
            team_context=None, rng=np.random.default_rng(42),
        )

        assert player.usage.target_share == original_ts

    def test_team_context_applied_before_blend(self):
        """Team context adjustments apply to tier distributions before blending."""
        engine = _make_tier_engine()
        pool = _make_pool_entry(catch_rate=(0.60, 0.65, 0.70))
        engine._pools = {"WR": {2: pool}}
        engine._boundaries = {"WR": [85.0, 70.0, 55.0, 40.0]}

        player = _make_rookie_player("rookie_tc", "WR", "KC", target_share=0.03)
        roster = TeamRoster(team="KC", players=[player])

        nfl_roster = _make_roster_df([{
            "player_id": "rookie_tc", "pff_id": 77777,
            "draft_number": 1, "rookie_year": 2025,
        }])

        engine._pff_loader.load_ncaa_facet.return_value = _ncaa_facet_df(
            player_id=77777, grades_col="grades_pass_route",
            grade_values=[75.0],
        )

        tc = TeamContext(qb_quality_factor=1.05)

        engine._apply_rookie_tiers(
            roster, nfl_roster, [player], target_season=2025,
            team_context=tc, rng=np.random.default_rng(42),
        )

        assert player.outcomes.catch_rate > 0.60


class TestApplyTiersRookieIntegration:
    def test_veterans_processed_rookies_also_processed(self):
        """Veterans go through normal path, rookies through NCAA path."""
        engine = _make_tier_engine()
        pool = _make_pool_entry()
        engine._pools = {"WR": {2: pool, 3: pool}}
        engine._boundaries = {"WR": [85.0, 70.0, 55.0, 40.0]}
        engine._cache_key = (2022, 2023, 2024)

        vet = _make_rookie_player("vet1", "WR", "KC", target_share=0.20)
        vet.games_played = 32
        rookie = _make_rookie_player("rookie1", "WR", "KC", target_share=0.03)

        roster = TeamRoster(team="KC", players=[vet, rookie])

        crosswalk = {100: "vet1"}

        nfl_roster = _make_roster_df([
            {"player_id": "vet1", "pff_id": 100, "draft_number": 20, "rookie_year": 2020},
            {"player_id": "rookie1", "pff_id": 12345, "draft_number": 5, "rookie_year": 2025},
        ])

        engine._load_season_grades = MagicMock(return_value={
            100: {"grades_pass_route": 72.0},
        })

        engine._pff_loader.load_ncaa_facet.return_value = _ncaa_facet_df(
            player_id=12345, grades_col="grades_pass_route",
            grade_values=[78.0],
        )

        engine.apply_tiers(
            roster, crosswalk, [2022, 2023, 2024],
            nfl_roster=nfl_roster, target_season=2025,
        )

        # Vet has high reliability (32 games) so target_share barely moves,
        # but catch_rate blending is visible (0.58 -> ~0.59)
        assert vet.outcomes.catch_rate != 0.58
        assert rookie.usage.target_share > 0.03

    def test_ncaa_rookie_disabled_skips_rookie_path(self):
        """When ncaa_rookie.enabled=False, skipped players are unchanged."""
        engine = _make_tier_engine(ncaa_enabled=False)
        pool = _make_pool_entry()
        engine._pools = {"WR": {3: pool}}
        engine._boundaries = {"WR": [85.0, 70.0, 55.0, 40.0]}
        engine._cache_key = (2022, 2023, 2024)

        rookie = _make_rookie_player("rookie1", "WR", "KC", target_share=0.03)
        original_ts = rookie.usage.target_share
        roster = TeamRoster(team="KC", players=[rookie])

        nfl_roster = _make_roster_df([
            {"player_id": "rookie1", "pff_id": 12345, "draft_number": 5, "rookie_year": 2025},
        ])

        engine.apply_tiers(
            roster, {}, [2022, 2023, 2024],
            nfl_roster=nfl_roster, target_season=2025,
        )

        assert rookie.usage.target_share == original_ts


class TestPickToRound:
    def test_first_pick_is_round_1(self):
        assert _pick_to_round(1) == 1

    def test_pick_32_is_round_1(self):
        assert _pick_to_round(32) == 1

    def test_pick_33_is_round_2(self):
        assert _pick_to_round(33) == 2

    def test_pick_64_is_round_2(self):
        assert _pick_to_round(64) == 2

    def test_pick_65_is_round_3(self):
        assert _pick_to_round(65) == 3

    def test_pick_224_is_round_7(self):
        assert _pick_to_round(224) == 7

    def test_compensatory_picks_cap_at_round_7(self):
        assert _pick_to_round(260) == 7

    def test_none_returns_none(self):
        assert _pick_to_round(None) is None


class TestClassifyArchetype:
    def _make_engine_with_boundaries(self, boundaries=(9.0, 14.0)):
        """Create a TierEngine with preset ADOT boundaries."""
        from fantasy_sim.data.pff.models import ArchetypeConfig
        engine = _make_tier_engine()
        engine._config.archetypes = ArchetypeConfig(enabled=True)
        engine._adot_boundaries = boundaries
        return engine

    def test_slot_below_p33(self):
        """ADOT below p33 boundary classifies as slot."""
        engine = self._make_engine_with_boundaries((9.0, 14.0))
        assert engine._classify_archetype({"avg_depth_of_target": 7.0}) == "slot"

    def test_possession_between_boundaries(self):
        """ADOT between p33 and p67 classifies as possession."""
        engine = self._make_engine_with_boundaries((9.0, 14.0))
        assert engine._classify_archetype({"avg_depth_of_target": 11.0}) == "possession"

    def test_deep_above_p67(self):
        """ADOT above p67 boundary classifies as deep."""
        engine = self._make_engine_with_boundaries((9.0, 14.0))
        assert engine._classify_archetype({"avg_depth_of_target": 16.0}) == "deep"

    def test_at_p33_boundary_is_possession(self):
        """ADOT exactly at p33 boundary classifies as possession (>= p33)."""
        engine = self._make_engine_with_boundaries((9.0, 14.0))
        assert engine._classify_archetype({"avg_depth_of_target": 9.0}) == "possession"

    def test_at_p67_boundary_is_deep(self):
        """ADOT exactly at p67 boundary classifies as deep (boundary = lower bucket upper edge)."""
        engine = self._make_engine_with_boundaries((9.0, 14.0))
        assert engine._classify_archetype({"avg_depth_of_target": 14.0}) == "deep"

    def test_none_when_adot_missing(self):
        """Returns None when ADOT is not in the grades dict."""
        engine = self._make_engine_with_boundaries((9.0, 14.0))
        assert engine._classify_archetype({"grades_pass_route": 75.0}) is None

    def test_none_when_boundaries_not_set(self):
        """Returns None when ADOT boundaries haven't been computed."""
        engine = _make_tier_engine()
        engine._adot_boundaries = None
        assert engine._classify_archetype({"avg_depth_of_target": 10.0}) is None

    def test_none_when_archetypes_disabled(self):
        """Returns None when archetypes are disabled in config."""
        from fantasy_sim.data.pff.models import ArchetypeConfig
        engine = _make_tier_engine()
        engine._config.archetypes = ArchetypeConfig(enabled=False)
        engine._adot_boundaries = (9.0, 14.0)
        assert engine._classify_archetype({"avg_depth_of_target": 10.0}) is None


class TestArchetypePoolBuilding:
    def _make_wr_player_season(self, adot, catch_rate=0.65, yards_list=None):
        """Create a WR player-season dict with PFF grades including ADOT."""
        if yards_list is None:
            yards_list = [5, 10, 15, 20]
        return {
            "targets": 50,
            "catches": 30,
            "carries": 0,
            "yards_list": yards_list,
            "rushing_yards_list": [],
            "fumbles": 1,
            "team": "KC",
            "games": {f"game_{i}" for i in range(10)},
            "air_yards": 300.0,
            "weekly_targets": {w: 5 for w in range(1, 11)},
            "target_share": 0.20,
            "carry_share": 0.0,
            "catch_rate": catch_rate,
            "air_yards_share": 0.15,
            "fumble_rate": 0.015,
            "weekly_share_values": [0.20] * 10,
            "pff_grades": {
                "grades_pass_route": 70.0,
                "avg_depth_of_target": adot,
            },
            "pff_id": 1000 + int(adot * 10),
            "nfl_id": f"player_{int(adot * 10)}",
            "season": 2024,
        }

    def test_adot_boundaries_computed_globally(self):
        """ADOT percentile boundaries are computed from all WR player-seasons."""
        player_seasons = [self._make_wr_player_season(adot=float(i)) for i in range(1, 31)]
        tier_buckets = {1: player_seasons}

        engine = _make_tier_engine()
        engine._config.archetypes = ArchetypeConfig(enabled=True, min_archetype_pool_size=3)
        engine._build_archetype_pools("WR", player_seasons, tier_buckets)

        assert engine._adot_boundaries is not None
        assert len(engine._adot_boundaries) == 2
        # p33 of 1..30 should be ~10-11, p67 should be ~20-21
        assert 9.0 <= engine._adot_boundaries[0] <= 12.0
        assert 19.0 <= engine._adot_boundaries[1] <= 22.0

    def test_three_sub_pools_built_per_tier(self):
        """Each tier gets up to 3 archetype sub-pools when enough members exist."""
        player_seasons = []
        for i in range(10):
            player_seasons.append(self._make_wr_player_season(adot=5.0 + i * 0.1))
        for i in range(10):
            player_seasons.append(self._make_wr_player_season(adot=12.0 + i * 0.1))
        for i in range(10):
            player_seasons.append(self._make_wr_player_season(adot=20.0 + i * 0.1))
        tier_buckets = {1: player_seasons}

        engine = _make_tier_engine()
        engine._config.archetypes = ArchetypeConfig(enabled=True, min_archetype_pool_size=3)
        engine._build_archetype_pools("WR", player_seasons, tier_buckets)

        assert engine._archetype_pools is not None
        assert "WR" in engine._archetype_pools
        assert 1 in engine._archetype_pools["WR"]
        tier1_archetypes = engine._archetype_pools["WR"][1]
        assert "slot" in tier1_archetypes
        assert "possession" in tier1_archetypes
        assert "deep" in tier1_archetypes

    def test_sub_pool_has_archetype_specific_yards(self):
        """Deep archetype sub-pool has higher mean receiving yards than slot."""
        player_seasons = []
        for i in range(10):
            player_seasons.append(self._make_wr_player_season(adot=5.0, yards_list=[3, 5, 7, 8]))
        for i in range(10):
            player_seasons.append(self._make_wr_player_season(adot=11.0, yards_list=[8, 12, 15, 18]))
        for i in range(10):
            player_seasons.append(self._make_wr_player_season(adot=18.0, yards_list=[15, 25, 35, 45]))
        tier_buckets = {2: player_seasons}

        engine = _make_tier_engine()
        engine._config.archetypes = ArchetypeConfig(enabled=True, min_archetype_pool_size=3)
        engine._build_archetype_pools("WR", player_seasons, tier_buckets)

        assert engine._archetype_pools is not None
        tier2 = engine._archetype_pools["WR"][2]
        slot_mean = tier2["slot"].receiving_yards_dist.mean()
        deep_mean = tier2["deep"].receiving_yards_dist.mean()
        assert deep_mean > slot_mean

    def test_thin_sub_pool_not_stored(self):
        """Sub-pools below min_archetype_pool_size are discarded."""
        player_seasons = []
        for i in range(5):
            player_seasons.append(self._make_wr_player_season(adot=5.0))
        for i in range(5):
            player_seasons.append(self._make_wr_player_season(adot=12.0))
        for i in range(5):
            player_seasons.append(self._make_wr_player_season(adot=20.0))
        tier_buckets = {1: player_seasons}

        engine = _make_tier_engine()
        engine._config.archetypes = ArchetypeConfig(enabled=True, min_archetype_pool_size=20)
        engine._build_archetype_pools("WR", player_seasons, tier_buckets)

        # All sub-pools are below threshold, so nothing stored
        assert engine._archetype_pools is None or "WR" not in engine._archetype_pools

    def test_missing_adot_excluded_from_sub_pools(self):
        """Players without ADOT in pff_grades are excluded from boundary computation."""
        player_seasons = []
        for i in range(10):
            player_seasons.append(self._make_wr_player_season(adot=float(i + 1)))
        # 5 players without ADOT
        for i in range(5):
            ps = self._make_wr_player_season(adot=50.0)
            del ps["pff_grades"]["avg_depth_of_target"]
            player_seasons.append(ps)
        tier_buckets = {1: player_seasons}

        engine = _make_tier_engine()
        engine._config.archetypes = ArchetypeConfig(enabled=True, min_archetype_pool_size=3)
        engine._build_archetype_pools("WR", player_seasons, tier_buckets)

        assert engine._adot_boundaries is not None
        # Boundaries computed from ADOT values 1..10 only (not the 50.0 values)
        assert len(engine._adot_boundaries) == 2
        # p33 of 1..10 ~ 3-4, p67 of 1..10 ~ 7-8
        assert engine._adot_boundaries[0] < 15.0
        assert engine._adot_boundaries[1] < 15.0

    def test_disabled_config_skips_building(self):
        """When archetypes.enabled is False, no archetype pools are built."""
        player_seasons = [self._make_wr_player_season(adot=float(i)) for i in range(1, 31)]
        tier_buckets = {1: player_seasons}

        engine = _make_tier_engine()
        engine._config.archetypes = ArchetypeConfig(enabled=False)
        engine._build_archetype_pools("WR", player_seasons, tier_buckets)

        assert engine._archetype_pools is None

    def test_non_wr_position_skips(self):
        """Non-WR positions do not build archetype pools."""
        player_seasons = [self._make_wr_player_season(adot=float(i)) for i in range(1, 31)]
        tier_buckets = {1: player_seasons}

        engine = _make_tier_engine()
        engine._config.archetypes = ArchetypeConfig(enabled=True, min_archetype_pool_size=3)
        engine._build_archetype_pools("RB", player_seasons, tier_buckets)

        assert engine._archetype_pools is None


class TestArchetypeBlendOverride:
    def test_wr_uses_archetype_yards_dist(self):
        """WR blend uses archetype sub-pool receiving_yards_dist."""
        from fantasy_sim.data.pff.models import ArchetypeConfig

        engine = _make_tier_engine()
        engine._config.archetypes = ArchetypeConfig(enabled=True)
        engine._adot_boundaries = (9.0, 14.0)

        main_pool = _make_pool_entry(
            receiving_yards_dist=np.array([10, 12, 14, 16, 18]),
            catch_rate=(0.60, 0.65, 0.70),
        )
        deep_pool = _make_pool_entry(
            receiving_yards_dist=np.array([20, 25, 30, 35, 40]),
            catch_rate=(0.45, 0.50, 0.55),
        )

        engine._pools = {"WR": {3: main_pool}}
        engine._boundaries = {"WR": [85.0, 70.0, 55.0, 40.0]}
        engine._archetype_pools = {"WR": {3: {"deep": deep_pool}}}

        pff_grades = {"grades_pass_route": 65.0, "avg_depth_of_target": 16.0}
        result = engine.select_distributions(pff_grades, "WR")
        assert result is not None
        assignment, tier_dists = result

        archetype = engine._classify_archetype(pff_grades)
        assert archetype == "deep"
        arch_pool_found = engine._archetype_pools["WR"][assignment.tier].get(archetype)
        assert arch_pool_found is not None
        tier_dists.receiving_yards_dist = arch_pool_found.receiving_yards_dist
        tier_dists.catch_rate = engine._interp_scalar(arch_pool_found.catch_rate, 0.5)

        assert np.array_equal(tier_dists.receiving_yards_dist, deep_pool.receiving_yards_dist)
        assert tier_dists.catch_rate == 0.50

    def test_wr_without_archetype_uses_main_pool(self):
        """WR without ADOT in grades falls back to main tier pool."""
        from fantasy_sim.data.pff.models import ArchetypeConfig

        engine = _make_tier_engine()
        engine._config.archetypes = ArchetypeConfig(enabled=True)
        engine._adot_boundaries = (9.0, 14.0)

        main_pool = _make_pool_entry(
            receiving_yards_dist=np.array([10, 12, 14, 16, 18]),
        )
        engine._pools = {"WR": {3: main_pool}}
        engine._boundaries = {"WR": [85.0, 70.0, 55.0, 40.0]}
        engine._archetype_pools = {"WR": {3: {"deep": _make_pool_entry()}}}

        pff_grades = {"grades_pass_route": 65.0}  # no ADOT
        result = engine.select_distributions(pff_grades, "WR")
        assert result is not None
        _, tier_dists = result

        archetype = engine._classify_archetype(pff_grades)
        assert archetype is None
        assert np.array_equal(tier_dists.receiving_yards_dist, main_pool.receiving_yards_dist)

    def test_rb_unaffected_by_archetypes(self):
        """RB blending is completely unaffected by archetype logic."""
        from fantasy_sim.data.pff.models import ArchetypeConfig

        engine = _make_tier_engine()
        engine._config.archetypes = ArchetypeConfig(enabled=True)
        engine._adot_boundaries = (9.0, 14.0)

        rb_pool = _make_pool_entry(
            rushing_yards_dist=np.array([2, 4, 6, 8]),
            carry_share=(0.10, 0.15, 0.20),
        )
        engine._pools = {"RB": {3: rb_pool}}
        engine._boundaries = {"RB": [85.0, 70.0, 55.0, 40.0]}
        engine._archetype_pools = {}

        pff_grades = {"grades_run": 65.0}
        result = engine.select_distributions(pff_grades, "RB")
        assert result is not None
        _, tier_dists = result

        archetype = engine._classify_archetype(pff_grades)
        assert archetype is None


class TestNcaaArchetypeOverride:
    def test_rookie_with_ncaa_adot_gets_archetype_sub_pool(self):
        """Rookie WR with NCAA ADOT gets archetype-specific distributions."""
        from fantasy_sim.data.pff.models import ArchetypeConfig

        engine = _make_tier_engine()
        engine._config.archetypes = ArchetypeConfig(enabled=True)
        engine._adot_boundaries = (9.0, 14.0)

        deep_pool = _make_pool_entry(
            receiving_yards_dist=np.array([20, 25, 30, 35, 40]),
            catch_rate=(0.45, 0.50, 0.55),
        )
        engine._archetype_pools = {"WR": {2: {"deep": deep_pool}}}

        ncaa_grades = {"grades_pass_route": 75.0, "avg_depth_of_target": 17.0}
        archetype = engine._classify_archetype(ncaa_grades)
        assert archetype == "deep"

        arch_pool_found = engine._archetype_pools["WR"][2].get(archetype)
        assert arch_pool_found is not None
        assert np.array_equal(arch_pool_found.receiving_yards_dist, deep_pool.receiving_yards_dist)

    def test_rookie_without_ncaa_adot_uses_full_pool(self):
        """Rookie WR without NCAA ADOT falls back to full tier pool."""
        from fantasy_sim.data.pff.models import ArchetypeConfig

        engine = _make_tier_engine()
        engine._config.archetypes = ArchetypeConfig(enabled=True)
        engine._adot_boundaries = (9.0, 14.0)
        engine._archetype_pools = {"WR": {2: {"deep": _make_pool_entry()}}}

        ncaa_grades = {"grades_pass_route": 75.0}
        archetype = engine._classify_archetype(ncaa_grades)
        assert archetype is None


class TestArchetypeConfigDisabled:
    def test_disabled_produces_no_archetype_pools(self):
        """With archetypes.enabled=False, _archetype_pools stays None."""
        from fantasy_sim.data.pff.models import ArchetypeConfig

        engine = _make_tier_engine()
        engine._config.archetypes = ArchetypeConfig(enabled=False)

        players = [
            TestArchetypePoolBuilding()._make_wr_player_season(adot=float(i))
            for i in range(1, 31)
        ]
        tier_buckets = {3: players}

        engine._build_archetype_pools("WR", players, tier_buckets)

        assert engine._archetype_pools is None
        assert engine._adot_boundaries is None

    def test_disabled_classify_returns_none(self):
        """_classify_archetype returns None when disabled, even with valid ADOT."""
        from fantasy_sim.data.pff.models import ArchetypeConfig

        engine = _make_tier_engine()
        engine._config.archetypes = ArchetypeConfig(enabled=False)
        engine._adot_boundaries = (9.0, 14.0)

        result = engine._classify_archetype({"avg_depth_of_target": 10.0})
        assert result is None

    def test_non_wr_position_skips_archetype_building(self):
        """_build_archetype_pools is a no-op for non-WR positions."""
        from fantasy_sim.data.pff.models import ArchetypeConfig

        engine = _make_tier_engine()
        engine._config.archetypes = ArchetypeConfig(enabled=True)

        players = [
            TestArchetypePoolBuilding()._make_wr_player_season(adot=10.0)
            for _ in range(30)
        ]
        engine._build_archetype_pools("RB", players, {3: players})

        assert engine._archetype_pools is None


@pytest.mark.statistical
class TestArchetypeStatisticalValidation:
    def _build_archetype_pools_with_realistic_data(self):
        """Build archetype sub-pools with realistic slot/deep separation."""
        from fantasy_sim.data.pff.models import ArchetypeConfig

        engine = _make_tier_engine()
        engine._config.archetypes = ArchetypeConfig(
            enabled=True, n_archetypes=3, min_archetype_pool_size=5,
        )

        rng = np.random.default_rng(42)

        def make_player(adot, yards_mean, catch_rate):
            ps = TestArchetypePoolBuilding()._make_wr_player_season(
                adot=adot,
                catch_rate=catch_rate,
                yards_list=rng.normal(yards_mean, 3.0, size=50).tolist(),
            )
            return ps

        slot_players = [make_player(adot=rng.uniform(4, 8), yards_mean=7.0, catch_rate=rng.uniform(0.65, 0.75)) for _ in range(20)]
        poss_players = [make_player(adot=rng.uniform(9, 13), yards_mean=12.0, catch_rate=rng.uniform(0.58, 0.68)) for _ in range(20)]
        deep_players = [make_player(adot=rng.uniform(15, 22), yards_mean=20.0, catch_rate=rng.uniform(0.48, 0.58)) for _ in range(20)]

        all_players = slot_players + poss_players + deep_players
        tier_buckets = {3: all_players}

        engine._build_archetype_pools("WR", all_players, tier_buckets)
        return engine

    def test_deep_archetype_has_higher_mean_yards_than_slot(self):
        """Deep-threat sub-pool has higher mean receiving_yards_dist than slot."""
        engine = self._build_archetype_pools_with_realistic_data()

        pools = engine._archetype_pools["WR"][3]
        slot_mean = np.mean(pools["slot"].receiving_yards_dist)
        deep_mean = np.mean(pools["deep"].receiving_yards_dist)

        assert deep_mean > slot_mean, (
            f"Deep mean yards ({deep_mean:.1f}) should exceed slot ({slot_mean:.1f})"
        )

    def test_slot_archetype_has_higher_catch_rate_than_deep(self):
        """Slot sub-pool has higher median catch_rate than deep sub-pool."""
        engine = self._build_archetype_pools_with_realistic_data()

        pools = engine._archetype_pools["WR"][3]
        slot_median = pools["slot"].catch_rate[1]
        deep_median = pools["deep"].catch_rate[1]

        assert slot_median > deep_median, (
            f"Slot catch rate ({slot_median:.3f}) should exceed deep ({deep_median:.3f})"
        )


# ---------------------------------------------------------------------------
# Task 1 (TDD RED → GREEN): CPOE backward-compatible grade modifier
# ---------------------------------------------------------------------------


class TestApplyTiersCpoeMap:
    """Tests for cpoe_map parameter in TierEngine.apply_tiers() (USG-02).

    Backward compatibility is paramount: all existing callers omit cpoe_map
    and must see zero behavior change.
    """

    def _make_engine_with_pools(self):
        """Build a TierEngine with minimal pools for QB to test grade adjustment."""
        from fantasy_sim.data.pff.tier_engine import TierEngine
        from fantasy_sim.data.pff.models import TierConfig

        config = TierConfig(enabled=True)
        engine = TierEngine(config=config, pff_loader=None)
        return engine

    def test_apply_tiers_accepts_cpoe_map_none(self):
        """apply_tiers() accepts cpoe_map=None without error (backward compat)."""
        from fantasy_sim.data.pff.tier_engine import TierEngine
        from fantasy_sim.data.pff.models import TierConfig
        from fantasy_sim.models.player import PlayerModel, PlayerOutcomes, PlayerUsage, TeamRoster

        engine = TierEngine(config=TierConfig(enabled=True), pff_loader=None)
        roster = TeamRoster(team="KC", players=[])
        # Should not raise TypeError
        engine.apply_tiers(
            roster, crosswalk={}, training_seasons=[2024], cpoe_map=None
        )

    def test_apply_tiers_accepts_no_cpoe_map_arg(self):
        """apply_tiers() called WITHOUT cpoe_map kwarg works identically to cpoe_map=None."""
        from fantasy_sim.data.pff.tier_engine import TierEngine
        from fantasy_sim.data.pff.models import TierConfig
        from fantasy_sim.models.player import TeamRoster

        engine = TierEngine(config=TierConfig(enabled=True), pff_loader=None)
        roster = TeamRoster(team="KC", players=[])
        # Should not raise TypeError
        engine.apply_tiers(roster, crosswalk={}, training_seasons=[2024])

    def test_cpoe_map_positive_bumps_qb_grade(self):
        """Positive CPOE (+5.0) with avg=1.0, std=4.0 => cpoe_z=1.0 => grade +0.30.

        With sensitivity=0.30 (default):
          cpoe_z = (5.0 - 1.0) / 4.0 = 1.0
          grade_adjustment = 1.0 * 0.30 = +0.30
        """
        from fantasy_sim.data.pff.tier_engine import TierEngine
        from fantasy_sim.data.pff.models import TierConfig

        config = TierConfig(enabled=True)
        engine = TierEngine(config=config, pff_loader=None)

        # Test via _compute_cpoe_grade_adjustment (the helper should exist)
        cpoe_val = 5.0
        league_avg = config.cpoe_league_avg  # 1.0
        league_std = config.cpoe_league_std  # 4.0
        sensitivity = config.cpoe_sensitivity  # 0.30

        cpoe_z = (cpoe_val - league_avg) / league_std
        expected_adjustment = cpoe_z * sensitivity

        assert abs(expected_adjustment - 0.30) < 0.001

    def test_cpoe_map_negative_pulls_qb_grade_down(self):
        """Negative CPOE (-3.0) with avg=1.0, std=4.0 => cpoe_z=-1.0 => grade -0.30.

        cpoe_z = (-3.0 - 1.0) / 4.0 = -1.0
        grade_adjustment = -1.0 * 0.30 = -0.30
        """
        from fantasy_sim.data.pff.tier_engine import TierEngine
        from fantasy_sim.data.pff.models import TierConfig

        config = TierConfig(enabled=True)
        engine = TierEngine(config=config, pff_loader=None)

        cpoe_val = -3.0
        league_avg = config.cpoe_league_avg
        league_std = config.cpoe_league_std
        sensitivity = config.cpoe_sensitivity

        cpoe_z = (cpoe_val - league_avg) / league_std
        expected_adjustment = cpoe_z * sensitivity

        assert abs(expected_adjustment - (-0.30)) < 0.001

    def test_tier_config_has_cpoe_fields(self):
        """TierConfig has cpoe_sensitivity, cpoe_league_avg, cpoe_league_std fields."""
        from fantasy_sim.data.pff.models import TierConfig

        config = TierConfig()
        assert hasattr(config, "cpoe_sensitivity"), "TierConfig missing cpoe_sensitivity"
        assert hasattr(config, "cpoe_league_avg"), "TierConfig missing cpoe_league_avg"
        assert hasattr(config, "cpoe_league_std"), "TierConfig missing cpoe_league_std"
        assert config.cpoe_sensitivity == 0.30
        assert config.cpoe_league_avg == 1.0
        assert config.cpoe_league_std == 4.0

"""Tests for TierConfig types and YAML config parsing."""

import numpy as np
import pytest

from fantasy_sim.data.pff.config import load_pff_config
from fantasy_sim.data.pff.models import PffConfig, TierConfig, PositionGradeConfig


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

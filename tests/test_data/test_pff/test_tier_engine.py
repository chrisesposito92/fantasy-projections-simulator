"""Tests for TierConfig types and YAML config parsing."""

import pytest

from fantasy_sim.data.pff.config import load_pff_config
from fantasy_sim.data.pff.models import PffConfig, TierConfig, PositionGradeConfig


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

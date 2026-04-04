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

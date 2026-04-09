"""Tests for TdTendencyEngine Bayesian factor computation."""

import numpy as np
import pytest
from fantasy_sim.data.td_tendency import TdTendencyConfig, TdTendencyEngine
from fantasy_sim.models.player import PlayerModel, PlayerUsage, PlayerOutcomes, TeamRoster


def _make_roster() -> TeamRoster:
    """Build a test roster with known RZ stats."""
    return TeamRoster(team="KC", players=[
        PlayerModel("wr1", "WR1", "WR", "KC",
                    PlayerUsage(target_share=0.25),
                    PlayerOutcomes(catch_rate=0.65)),
        PlayerModel("wr2", "WR2", "WR", "KC",
                    PlayerUsage(target_share=0.15),
                    PlayerOutcomes(catch_rate=0.60)),
        PlayerModel("rb1", "RB1", "RB", "KC",
                    PlayerUsage(carry_share=0.60),
                    PlayerOutcomes()),
        PlayerModel("qb1", "QB1", "QB", "KC",
                    PlayerUsage(snap_share=1.0),
                    PlayerOutcomes()),
    ])


class TestTdTendencyBayesianBlend:

    def test_bayesian_blend_formula(self):
        engine = TdTendencyEngine(TdTendencyConfig(enabled=True))
        blended = engine._bayesian_blend(0.30, 0.17, 10)
        expected = (10 * 0.30 + 15 * 0.17) / (10 + 15)
        assert abs(blended - expected) < 1e-9

    def test_zero_opportunities_returns_prior(self):
        engine = TdTendencyEngine(TdTendencyConfig(enabled=True))
        blended = engine._bayesian_blend(0.0, 0.17, 0)
        expected = (0 * 0.0 + 15 * 0.17) / (0 + 15)
        assert abs(blended - expected) < 1e-9
        assert abs(blended - 0.17) < 1e-9

    def test_clamp_enforced(self):
        engine = TdTendencyEngine(TdTendencyConfig(
            enabled=True, factor_clamp=(0.70, 1.30),
        ))
        assert engine._clamp(0.50) == 0.70
        assert engine._clamp(1.50) == 1.30
        assert engine._clamp(1.0) == 1.0

    def test_factor_centered_on_1(self):
        engine = TdTendencyEngine(TdTendencyConfig(enabled=True, prior_strength=15))
        blended = engine._bayesian_blend(0.17, 0.17, 30)
        factor = blended / 0.17
        assert abs(factor - 1.0) < 1e-9

    def test_above_average_gets_factor_above_1(self):
        engine = TdTendencyEngine(TdTendencyConfig(enabled=True, prior_strength=15))
        blended = engine._bayesian_blend(0.30, 0.17, 40)
        factor = blended / 0.17
        assert factor > 1.0

    def test_below_average_gets_factor_below_1(self):
        engine = TdTendencyEngine(TdTendencyConfig(enabled=True, prior_strength=15))
        blended = engine._bayesian_blend(0.05, 0.17, 40)
        factor = blended / 0.17
        assert factor < 1.0


class TestTdTendencyApplyFromPbp:

    def test_apply_sets_receiving_td_factor(self):
        config = TdTendencyConfig(enabled=True, prior_strength=15, min_opportunities=3)
        engine = TdTendencyEngine(config)
        roster = _make_roster()

        pbp_stats = {
            "receiving": {
                "wr1": {"rz_targets": 20, "rz_tds": 5, "team": "KC"},
                "wr2": {"rz_targets": 2, "rz_tds": 0, "team": "KC"},
            },
            "rushing": {
                "rb1": {"rz_carries": 30, "rz_tds": 9, "team": "KC"},
            },
        }

        engine.apply(roster, season=2024, week=10, pbp_stats=pbp_stats)

        assert roster.players[0].outcomes.receiving_td_factor > 1.0  # wr1: above avg
        assert roster.players[1].outcomes.receiving_td_factor == 1.0  # wr2: below min_opps
        assert roster.players[2].outcomes.rushing_td_factor > 1.0    # rb1: above avg

    def test_apply_disabled_is_noop(self):
        config = TdTendencyConfig(enabled=False)
        engine = TdTendencyEngine(config)
        roster = _make_roster()
        engine.apply(roster, season=2024, week=10, pbp_stats={"receiving": {}, "rushing": {}})
        for p in roster.players:
            assert p.outcomes.receiving_td_factor == 1.0
            assert p.outcomes.rushing_td_factor == 1.0

    def test_qb_gets_rushing_td_factor(self):
        config = TdTendencyConfig(enabled=True, prior_strength=15, min_opportunities=3)
        engine = TdTendencyEngine(config)
        roster = _make_roster()

        pbp_stats = {
            "receiving": {},
            "rushing": {
                "qb1": {"rz_carries": 20, "rz_tds": 8, "team": "KC"},
            },
        }
        engine.apply(roster, season=2024, week=10, pbp_stats=pbp_stats)
        assert roster.players[3].outcomes.rushing_td_factor > 1.0
        assert roster.players[3].outcomes.receiving_td_factor == 1.0


class TestTdTendencyI5PffLoading:

    def test_load_pff_rates_returns_i5_rush_rates(self):
        """_load_pff_rates returns 3-tuple with i5_rush_rates."""
        import polars as pl
        from unittest.mock import MagicMock

        rec_df = pl.DataFrame({
            "player_id": [100, 100, 200],
            "week": [1, 2, 1],
            "rz_rec_targ": [3, 2, 1],
            "rz_rec_tds": [1, 1, 0],
            "rz_rush_carries": [2, 1, 0],
            "rz_rush_tds": [1, 0, 0],
            "i5_rush_carries": [1, 1, 0],
            "i5_rush_tds": [1, 0, 0],
        })

        loader = MagicMock()
        loader.load_facet.side_effect = lambda facet, seasons: (
            rec_df if facet == "fantasy_receiving" else pl.DataFrame()
        )

        config = TdTendencyConfig(enabled=True, i5_enabled=True)
        engine = TdTendencyEngine(config, pff_loader=loader)
        crosswalk = {100: "gsis_rb1", 200: "gsis_wr1"}

        rec_rates, rush_rates, i5_rush_rates = engine._load_pff_rates(2024, 10, crosswalk)

        assert "gsis_rb1" in i5_rush_rates
        assert i5_rush_rates["gsis_rb1"] == (1, 2)  # 1 TD from 2 i5 carries
        assert "gsis_wr1" not in i5_rush_rates  # 0 i5 carries

    def test_load_pff_rates_i5_disabled_returns_empty(self):
        """When i5_enabled=False, i5_rush_rates is empty."""
        import polars as pl
        from unittest.mock import MagicMock

        rec_df = pl.DataFrame({
            "player_id": [100],
            "week": [1],
            "rz_rec_targ": [3],
            "rz_rec_tds": [1],
            "rz_rush_carries": [2],
            "rz_rush_tds": [1],
            "i5_rush_carries": [2],
            "i5_rush_tds": [1],
        })

        loader = MagicMock()
        loader.load_facet.side_effect = lambda facet, seasons: (
            rec_df if facet == "fantasy_receiving" else pl.DataFrame()
        )

        config = TdTendencyConfig(enabled=True, i5_enabled=False)
        engine = TdTendencyEngine(config, pff_loader=loader)
        crosswalk = {100: "gsis_rb1"}

        rec_rates, rush_rates, i5_rush_rates = engine._load_pff_rates(2024, 10, crosswalk)

        assert i5_rush_rates == {}

    def test_load_pff_rates_qb_i5_from_passing(self):
        """QB inside-5 data comes from fantasy_passing facet."""
        import polars as pl
        from unittest.mock import MagicMock

        pass_df = pl.DataFrame({
            "player_id": [300],
            "week": [1],
            "rz_rush_carries": [3],
            "rz_rush_tds": [1],
            "i5_rush_carries": [2],
            "i5_rush_tds": [1],
        })

        loader = MagicMock()
        loader.load_facet.side_effect = lambda facet, seasons: (
            pass_df if facet == "fantasy_passing" else pl.DataFrame()
        )

        config = TdTendencyConfig(enabled=True, i5_enabled=True)
        engine = TdTendencyEngine(config, pff_loader=loader)
        crosswalk = {300: "gsis_qb1"}

        rec_rates, rush_rates, i5_rush_rates = engine._load_pff_rates(2024, 10, crosswalk)

        assert "gsis_qb1" in i5_rush_rates
        assert i5_rush_rates["gsis_qb1"] == (1, 2)


class TestTdTendencyI5Factor:

    def test_i5_factor_computed_from_pbp(self):
        """Inside-5 factor is set when PBP data has i5 fields."""
        config = TdTendencyConfig(enabled=True, i5_enabled=True,
                                  prior_strength=15, i5_prior_strength=25,
                                  min_opportunities=3, i5_min_opportunities=3)
        engine = TdTendencyEngine(config)
        roster = _make_roster()

        pbp_stats = {
            "receiving": {},
            "rushing": {
                "rb1": {
                    "rz_carries": 30, "rz_tds": 9,
                    "i5_rush_carries": 10, "i5_rush_tds": 6,
                    "team": "KC",
                },
            },
        }

        engine.apply(roster, season=2024, week=10, pbp_stats=pbp_stats)

        rb = roster.players[2]  # rb1
        assert rb.outcomes.rushing_td_factor != 1.0  # general factor set
        assert rb.outcomes.i5_rushing_td_factor != 1.0  # i5 factor set
        # 6/10 = 0.60 observed vs ~0.50 prior => factor > 1.0
        assert rb.outcomes.i5_rushing_td_factor > 1.0

    def test_i5_factor_neutral_below_min_opportunities(self):
        """Players with fewer than i5_min_opportunities stay at 1.0."""
        config = TdTendencyConfig(enabled=True, i5_enabled=True,
                                  i5_min_opportunities=3)
        engine = TdTendencyEngine(config)
        roster = _make_roster()

        pbp_stats = {
            "receiving": {},
            "rushing": {
                "rb1": {
                    "rz_carries": 30, "rz_tds": 9,
                    "i5_rush_carries": 2, "i5_rush_tds": 1,
                    "team": "KC",
                },
            },
        }

        engine.apply(roster, season=2024, week=10, pbp_stats=pbp_stats)
        assert roster.players[2].outcomes.i5_rushing_td_factor == 1.0

    def test_i5_disabled_leaves_factor_neutral(self):
        """When i5_enabled=False, i5_rushing_td_factor stays 1.0."""
        config = TdTendencyConfig(enabled=True, i5_enabled=False)
        engine = TdTendencyEngine(config)
        roster = _make_roster()

        pbp_stats = {
            "receiving": {},
            "rushing": {
                "rb1": {
                    "rz_carries": 30, "rz_tds": 9,
                    "i5_rush_carries": 10, "i5_rush_tds": 6,
                    "team": "KC",
                },
            },
        }

        engine.apply(roster, season=2024, week=10, pbp_stats=pbp_stats)
        assert roster.players[2].outcomes.i5_rushing_td_factor == 1.0

    def test_i5_factor_wr_stays_neutral(self):
        """WR/TE never get i5_rushing_td_factor (rushing only for RB/QB/FB)."""
        config = TdTendencyConfig(enabled=True, i5_enabled=True,
                                  i5_min_opportunities=3)
        engine = TdTendencyEngine(config)
        roster = _make_roster()

        pbp_stats = {
            "receiving": {
                "wr1": {"rz_targets": 20, "rz_tds": 5, "team": "KC"},
            },
            "rushing": {},
        }

        engine.apply(roster, season=2024, week=10, pbp_stats=pbp_stats)
        assert roster.players[0].outcomes.i5_rushing_td_factor == 1.0

    def test_i5_bayesian_blend_exact_value(self):
        """Verify exact Bayesian blend for inside-5 with known inputs."""
        config = TdTendencyConfig(enabled=True, i5_enabled=True,
                                  i5_prior_strength=25, i5_min_opportunities=3,
                                  factor_clamp=(0.65, 1.35))
        engine = TdTendencyEngine(config)
        roster = _make_roster()

        pbp_stats = {
            "receiving": {},
            "rushing": {
                "rb1": {
                    "rz_carries": 30, "rz_tds": 9,
                    "i5_rush_carries": 10, "i5_rush_tds": 6,
                    "team": "KC",
                },
            },
        }

        engine.apply(roster, season=2024, week=10, pbp_stats=pbp_stats)

        # Verify exact computation:
        # observed = 6/10 = 0.60, prior = 0.50 (RB), prior_strength = 25
        # blended = (10 * 0.60 + 25 * 0.50) / (10 + 25) = 18.5 / 35 = 0.52857...
        # factor = 0.52857 / 0.50 = 1.05714...
        expected_blend = (10 * 0.60 + 25 * 0.50) / (10 + 25)
        expected_factor = expected_blend / 0.50
        assert abs(roster.players[2].outcomes.i5_rushing_td_factor - expected_factor) < 1e-6

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

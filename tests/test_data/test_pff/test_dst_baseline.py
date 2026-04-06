"""Tests for PFF DST baseline engine — fumble rate + defensive TD rates."""

import numpy as np
import polars as pl
import pytest

from fantasy_sim.data.pff.models import DstBaselineConfig, DstBaselineContext, PffConfig


class TestDstBaselineConfig:
    def test_default_values(self):
        cfg = DstBaselineConfig()
        assert cfg.enabled is True
        assert cfg.prior_strength == 10
        assert cfg.min_games == 4
        assert cfg.clamp == [0.85, 1.15]
        assert cfg.sensitivities == {"fumble_rate": 0.06}

    def test_pff_config_has_dst_baseline(self):
        pff = PffConfig()
        assert hasattr(pff, "dst_baseline")
        assert isinstance(pff.dst_baseline, DstBaselineConfig)


class TestDstBaselineContext:
    def test_default_neutral(self):
        ctx = DstBaselineContext()
        assert ctx.fumble_rate_factor == 1.0
        assert ctx.int_return_td_rate == 0.20
        assert ctx.fumble_return_td_rate == 0.10


from fantasy_sim.engine.types import DefensiveTdRates, TeamDistributions


class TestDefensiveTdRates:
    def test_default_matches_constants(self):
        rates = DefensiveTdRates()
        assert rates.int_return_td_rate == 0.20
        assert rates.fumble_return_td_rate == 0.10

    def test_team_distributions_has_defensive_td_rates(self):
        from fantasy_sim.models.distributions import (
            PlayCallingDist, PlayOutcomeDist, TurnoverRates, KickingModel, DriveStartModel,
        )
        dists = TeamDistributions(
            play_calling=PlayCallingDist(team="TST", distributions={}, default={"pass": 0.5, "run": 0.5}),
            play_outcomes=PlayOutcomeDist(distributions={}),
            turnover_rates=TurnoverRates(team="TST", int_rate=0.025, fumble_rate=0.012, sack_rate=0.065, sack_fumble_rate=0.10),
            kicking=KickingModel(fg_make_rate={"0_39": 0.90, "40_49": 0.84, "50_plus": 0.67}, xp_rate=0.95),
            drive_start=DriveStartModel(touchback_rate=0.6, touchback_yardline=75, return_yardlines=np.array([75])),
        )
        assert hasattr(dists, "defensive_td_rates")
        assert dists.defensive_td_rates.int_return_td_rate == 0.20
        assert dists.defensive_td_rates.fumble_return_td_rate == 0.10

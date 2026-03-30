import numpy as np
import pytest
from fantasy_sim.data.rookie_builder import build_rookie_model, POSITIONAL_ARCHETYPES
from fantasy_sim.models.player import PlayerModel


class TestBuildRookieModel:
    def test_creates_player_model(self):
        model = build_rookie_model(
            player_id="RK01", name="Rookie WR", position="WR",
            team="KC", draft_round=1,
        )
        assert isinstance(model, PlayerModel)
        assert model.player_id == "RK01"
        assert model.position == "WR"

    def test_first_round_wr_has_higher_target_share(self):
        r1 = build_rookie_model("R1", "First", "WR", "KC", draft_round=1)
        r5 = build_rookie_model("R5", "Fifth", "WR", "KC", draft_round=5)
        assert r1.usage.target_share > r5.usage.target_share

    def test_first_round_rb_has_higher_carry_share(self):
        r1 = build_rookie_model("R1", "First", "RB", "KC", draft_round=1)
        r5 = build_rookie_model("R5", "Fifth", "RB", "KC", draft_round=5)
        assert r1.usage.carry_share > r5.usage.carry_share

    def test_qb_has_snap_share(self):
        model = build_rookie_model("R1", "Rookie QB", "QB", "KC", draft_round=1)
        assert model.usage.snap_share > 0

    def test_has_outcome_distributions(self):
        model = build_rookie_model("R1", "Rookie", "WR", "KC", draft_round=1)
        assert model.outcomes.catch_rate > 0
        assert model.outcomes.receiving_yards_dist is not None

    def test_undrafted_gets_minimal_share(self):
        model = build_rookie_model("UD", "Undrafted", "WR", "KC", draft_round=7)
        assert model.usage.target_share < 0.05

    def test_archetypes_exist_for_all_positions(self):
        for pos in ["QB", "RB", "WR", "TE"]:
            assert pos in POSITIONAL_ARCHETYPES

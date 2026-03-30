import numpy as np
import pytest
from fantasy_sim.data.player_builder import build_player_models, build_team_roster
from fantasy_sim.models.player import TeamRoster


class TestBuildPlayerModels:
    def test_returns_dict_of_player_models(self, expanded_pbp, sample_rosters):
        models = build_player_models(expanded_pbp, sample_rosters, seasons=[2024])
        assert isinstance(models, dict)
        assert "PM15" in models
        assert "TK87" in models
        assert "JA17" in models

    def test_player_has_correct_metadata(self, expanded_pbp, sample_rosters):
        models = build_player_models(expanded_pbp, sample_rosters, seasons=[2024])
        pm = models["PM15"]
        assert pm.name == "P.Mahomes"
        assert pm.position == "QB"
        assert pm.team == "KC"

    def test_wr_has_target_share(self, expanded_pbp, sample_rosters):
        models = build_player_models(expanded_pbp, sample_rosters, seasons=[2024])
        tk = models["TK87"]
        assert tk.usage.target_share > 0

    def test_rb_has_carry_share(self, expanded_pbp, sample_rosters):
        models = build_player_models(expanded_pbp, sample_rosters, seasons=[2024])
        ip = models["IP01"]
        assert ip.usage.carry_share > 0

    def test_target_shares_per_team_sum_near_one(self, expanded_pbp, sample_rosters):
        models = build_player_models(expanded_pbp, sample_rosters, seasons=[2024])
        kc_players = [m for m in models.values() if m.team == "KC"]
        total_ts = sum(p.usage.target_share for p in kc_players)
        assert total_ts == pytest.approx(1.0, abs=0.05)

    def test_carry_shares_per_team_sum_near_one(self, expanded_pbp, sample_rosters):
        models = build_player_models(expanded_pbp, sample_rosters, seasons=[2024])
        kc_rbs = [m for m in models.values() if m.team == "KC" and m.usage.carry_share > 0]
        total_cs = sum(p.usage.carry_share for p in kc_rbs)
        assert total_cs == pytest.approx(1.0, abs=0.05)

    def test_receiver_has_outcome_distributions(self, expanded_pbp, sample_rosters):
        models = build_player_models(expanded_pbp, sample_rosters, seasons=[2024])
        tk = models["TK87"]
        assert tk.outcomes.catch_rate > 0
        assert tk.outcomes.receiving_yards_dist is not None
        assert len(tk.outcomes.receiving_yards_dist) > 0

    def test_rusher_has_outcome_distributions(self, expanded_pbp, sample_rosters):
        models = build_player_models(expanded_pbp, sample_rosters, seasons=[2024])
        ip = models["IP01"]
        assert ip.outcomes.rushing_yards_dist is not None
        assert len(ip.outcomes.rushing_yards_dist) > 0

    def test_qb_has_scramble_data(self, expanded_pbp, sample_rosters):
        models = build_player_models(expanded_pbp, sample_rosters, seasons=[2024])
        pm = models["PM15"]
        assert pm.usage.snap_share > 0


class TestBuildTeamRoster:
    def test_returns_roster(self, expanded_pbp, sample_rosters):
        models = build_player_models(expanded_pbp, sample_rosters, seasons=[2024])
        roster = build_team_roster("KC", models)
        assert isinstance(roster, TeamRoster)
        assert roster.team == "KC"

    def test_roster_has_all_team_players(self, expanded_pbp, sample_rosters):
        models = build_player_models(expanded_pbp, sample_rosters, seasons=[2024])
        roster = build_team_roster("KC", models)
        ids = {p.player_id for p in roster.players}
        assert "PM15" in ids
        assert "TK87" in ids
        assert "IP01" in ids

    def test_roster_can_select_players(self, expanded_pbp, sample_rosters):
        models = build_player_models(expanded_pbp, sample_rosters, seasons=[2024])
        roster = build_team_roster("KC", models)
        rng = np.random.default_rng(42)
        assert roster.get_starting_qb() is not None
        assert roster.select_receiver(rng) is not None
        assert roster.select_rusher(rng) is not None


class TestRedZoneMetrics:
    def test_red_zone_target_share_computed(self, rz_pbp, sample_rosters):
        models = build_player_models(rz_pbp, sample_rosters, seasons=[2024])
        # RE11 for KC: has 5 rz targets. KC has 5 rz pass attempts total.
        # SD14 for BUF: has 3 rz targets. BUF has 3 rz pass attempts total.
        sd = models.get("SD14")
        assert sd is not None
        assert sd.usage.red_zone_target_share > 0

    def test_red_zone_carry_share_computed(self, rz_pbp, sample_rosters):
        models = build_player_models(rz_pbp, sample_rosters, seasons=[2024])
        ip = models.get("IP01")
        assert ip is not None
        assert ip.usage.red_zone_carry_share > 0


class TestAirYardsShare:
    def test_air_yards_share_computed(self, air_yards_pbp, sample_rosters):
        models = build_player_models(air_yards_pbp, sample_rosters, seasons=[2024])
        tk = models.get("TK87")
        assert tk is not None
        assert tk.usage.air_yards_share > 0

    def test_air_yards_share_sums_near_one(self, air_yards_pbp, sample_rosters):
        models = build_player_models(air_yards_pbp, sample_rosters, seasons=[2024])
        kc_receivers = [m for m in models.values() if m.team == "KC" and m.usage.air_yards_share > 0]
        total = sum(p.usage.air_yards_share for p in kc_receivers)
        assert total == pytest.approx(1.0, abs=0.05)


class TestQBScrambleData:
    def test_qb_scramble_rate_from_pbp(self, scramble_pbp, sample_rosters):
        models = build_player_models(scramble_pbp, sample_rosters, seasons=[2024])
        ja = models.get("JA17")
        assert ja is not None
        assert ja.usage.scramble_rate > 0

    def test_qb_scramble_yards_dist(self, scramble_pbp, sample_rosters):
        models = build_player_models(scramble_pbp, sample_rosters, seasons=[2024])
        ja = models.get("JA17")
        assert ja is not None
        assert ja.outcomes.scramble_yards_dist is not None
        assert len(ja.outcomes.scramble_yards_dist) > 0

    def test_non_qb_has_no_scramble_rate(self, scramble_pbp, sample_rosters):
        models = build_player_models(scramble_pbp, sample_rosters, seasons=[2024])
        jc = models.get("JC02")
        assert jc is not None
        assert jc.usage.scramble_rate == 0.0

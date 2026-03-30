import numpy as np
import pytest
from fantasy_sim.data.player_builder import (
    build_player_models, build_team_roster, blend_with_archetype,
    _aggregate_pbp_stats, build_kicker_model, _assemble_models,
)
from fantasy_sim.data.rookie_builder import POSITIONAL_ARCHETYPES
from fantasy_sim.models.player import PlayerModel, PlayerUsage, PlayerOutcomes, TeamRoster


class TestBuildPlayerModels:
    def test_returns_dict_of_player_models(self, expanded_pbp, sample_rosters):
        models = build_player_models(expanded_pbp, sample_rosters, training_seasons=[2024])
        assert isinstance(models, dict)
        assert "PM15" in models
        assert "TK87" in models
        assert "JA17" in models

    def test_player_has_correct_metadata(self, expanded_pbp, sample_rosters):
        models = build_player_models(expanded_pbp, sample_rosters, training_seasons=[2024])
        pm = models["PM15"]
        assert pm.name == "P.Mahomes"
        assert pm.position == "QB"
        assert pm.team == "KC"

    def test_wr_has_target_share(self, expanded_pbp, sample_rosters):
        models = build_player_models(expanded_pbp, sample_rosters, training_seasons=[2024])
        tk = models["TK87"]
        assert tk.usage.target_share > 0

    def test_rb_has_carry_share(self, expanded_pbp, sample_rosters):
        models = build_player_models(expanded_pbp, sample_rosters, training_seasons=[2024])
        ip = models["IP01"]
        assert ip.usage.carry_share > 0

    def test_target_shares_per_team_sum_near_one(self, expanded_pbp, sample_rosters):
        models = build_player_models(expanded_pbp, sample_rosters, training_seasons=[2024])
        kc_players = [m for m in models.values() if m.team == "KC"]
        total_ts = sum(p.usage.target_share for p in kc_players)
        assert total_ts == pytest.approx(1.0, abs=0.05)

    def test_carry_shares_per_team_sum_near_one(self, expanded_pbp, sample_rosters):
        models = build_player_models(expanded_pbp, sample_rosters, training_seasons=[2024])
        kc_rbs = [m for m in models.values() if m.team == "KC" and m.usage.carry_share > 0]
        total_cs = sum(p.usage.carry_share for p in kc_rbs)
        assert total_cs == pytest.approx(1.0, abs=0.05)

    def test_receiver_has_outcome_distributions(self, expanded_pbp, sample_rosters):
        models = build_player_models(expanded_pbp, sample_rosters, training_seasons=[2024])
        tk = models["TK87"]
        assert tk.outcomes.catch_rate > 0
        assert tk.outcomes.receiving_yards_dist is not None
        assert len(tk.outcomes.receiving_yards_dist) > 0

    def test_rusher_has_outcome_distributions(self, expanded_pbp, sample_rosters):
        models = build_player_models(expanded_pbp, sample_rosters, training_seasons=[2024])
        ip = models["IP01"]
        assert ip.outcomes.rushing_yards_dist is not None
        assert len(ip.outcomes.rushing_yards_dist) > 0

    def test_qb_has_scramble_data(self, expanded_pbp, sample_rosters):
        models = build_player_models(expanded_pbp, sample_rosters, training_seasons=[2024])
        pm = models["PM15"]
        assert pm.usage.snap_share > 0


class TestBuildTeamRoster:
    def test_returns_roster(self, expanded_pbp, sample_rosters):
        models = build_player_models(expanded_pbp, sample_rosters, training_seasons=[2024])
        roster = build_team_roster("KC", models)
        assert isinstance(roster, TeamRoster)
        assert roster.team == "KC"

    def test_roster_has_all_team_players(self, expanded_pbp, sample_rosters):
        models = build_player_models(expanded_pbp, sample_rosters, training_seasons=[2024])
        roster = build_team_roster("KC", models)
        ids = {p.player_id for p in roster.players}
        assert "PM15" in ids
        assert "TK87" in ids
        assert "IP01" in ids

    def test_roster_can_select_players(self, expanded_pbp, sample_rosters):
        models = build_player_models(expanded_pbp, sample_rosters, training_seasons=[2024])
        roster = build_team_roster("KC", models)
        rng = np.random.default_rng(42)
        assert roster.get_starting_qb() is not None
        assert roster.select_receiver(rng) is not None
        assert roster.select_rusher(rng) is not None


class TestRedZoneMetrics:
    def test_red_zone_target_share_computed(self, rz_pbp, sample_rosters):
        models = build_player_models(rz_pbp, sample_rosters, training_seasons=[2024])
        # RE11 for KC: has 5 rz targets. KC has 5 rz pass attempts total.
        # SD14 for BUF: has 3 rz targets. BUF has 3 rz pass attempts total.
        sd = models.get("SD14")
        assert sd is not None
        assert sd.usage.red_zone_target_share > 0

    def test_red_zone_carry_share_computed(self, rz_pbp, sample_rosters):
        models = build_player_models(rz_pbp, sample_rosters, training_seasons=[2024])
        ip = models.get("IP01")
        assert ip is not None
        assert ip.usage.red_zone_carry_share > 0


class TestAirYardsShare:
    def test_air_yards_share_computed(self, air_yards_pbp, sample_rosters):
        models = build_player_models(air_yards_pbp, sample_rosters, training_seasons=[2024])
        tk = models.get("TK87")
        assert tk is not None
        assert tk.usage.air_yards_share > 0

    def test_air_yards_share_sums_near_one(self, air_yards_pbp, sample_rosters):
        models = build_player_models(air_yards_pbp, sample_rosters, training_seasons=[2024])
        kc_receivers = [m for m in models.values() if m.team == "KC" and m.usage.air_yards_share > 0]
        total = sum(p.usage.air_yards_share for p in kc_receivers)
        assert total == pytest.approx(1.0, abs=0.05)


class TestQBScrambleData:
    def test_qb_scramble_rate_from_pbp(self, scramble_pbp, sample_rosters):
        models = build_player_models(scramble_pbp, sample_rosters, training_seasons=[2024])
        ja = models.get("JA17")
        assert ja is not None
        assert ja.usage.scramble_rate > 0

    def test_qb_scramble_yards_dist(self, scramble_pbp, sample_rosters):
        models = build_player_models(scramble_pbp, sample_rosters, training_seasons=[2024])
        ja = models.get("JA17")
        assert ja is not None
        assert ja.outcomes.scramble_yards_dist is not None
        assert len(ja.outcomes.scramble_yards_dist) > 0

    def test_non_qb_has_no_scramble_rate(self, scramble_pbp, sample_rosters):
        models = build_player_models(scramble_pbp, sample_rosters, training_seasons=[2024])
        jc = models.get("JC02")
        assert jc is not None
        assert jc.usage.scramble_rate == 0.0


class TestRookieBlendSystem:
    def test_full_data_player_no_blend(self):
        """A player with 17 games should have no blending (all real data)."""
        usage = PlayerUsage(target_share=0.25, red_zone_target_share=0.20)
        outcomes = PlayerOutcomes(catch_rate=0.68, fumble_rate=0.005)
        model = PlayerModel(
            player_id="WR1", name="Vet WR", position="WR", team="KC",
            usage=usage, outcomes=outcomes, games_played=17,
        )
        blended = blend_with_archetype(model, rookie_blend_games=4)
        assert blended.usage.target_share == pytest.approx(0.25)
        assert blended.outcomes.catch_rate == pytest.approx(0.68)

    def test_zero_games_full_archetype(self):
        """A player with 0 games should be 100% archetype (tier3 fallback)."""
        usage = PlayerUsage(target_share=0.0)
        outcomes = PlayerOutcomes(catch_rate=0.0, fumble_rate=0.0)
        model = PlayerModel(
            player_id="WR1", name="New WR", position="WR", team="KC",
            usage=usage, outcomes=outcomes, games_played=0,
        )
        blended = blend_with_archetype(model, rookie_blend_games=4)
        arch = POSITIONAL_ARCHETYPES["WR"]["tier3"]
        assert blended.usage.target_share == pytest.approx(arch["target_share"])
        assert blended.outcomes.catch_rate == pytest.approx(arch["catch_rate"])

    def test_partial_blend(self):
        """A player with 2 of 4 blend games should be 50% real, 50% archetype."""
        usage = PlayerUsage(target_share=0.30)
        outcomes = PlayerOutcomes(catch_rate=0.70, fumble_rate=0.01)
        model = PlayerModel(
            player_id="WR1", name="Soph WR", position="WR", team="KC",
            usage=usage, outcomes=outcomes, games_played=2,
        )
        blended = blend_with_archetype(model, rookie_blend_games=4)
        arch = POSITIONAL_ARCHETYPES["WR"]["tier3"]
        expected_ts = 0.5 * 0.30 + 0.5 * arch["target_share"]
        assert blended.usage.target_share == pytest.approx(expected_ts, abs=0.01)

    def test_blend_doesnt_modify_original(self):
        """Blending should return a new model, not modify the original."""
        usage = PlayerUsage(target_share=0.30)
        outcomes = PlayerOutcomes(catch_rate=0.70)
        model = PlayerModel(
            player_id="WR1", name="WR", position="WR", team="KC",
            usage=usage, outcomes=outcomes, games_played=2,
        )
        blended = blend_with_archetype(model, rookie_blend_games=4)
        assert model.usage.target_share == 0.30
        assert blended is not model

    def test_qb_blend_includes_scramble_rate(self):
        """QB blending should include scramble_rate from archetype."""
        usage = PlayerUsage(snap_share=0.50, scramble_rate=0.10)
        outcomes = PlayerOutcomes(fumble_rate=0.02)
        model = PlayerModel(
            player_id="QB1", name="Rook QB", position="QB", team="KC",
            usage=usage, outcomes=outcomes, games_played=1,
        )
        blended = blend_with_archetype(model, rookie_blend_games=4)
        arch = POSITIONAL_ARCHETYPES["QB"]["tier3"]
        expected_sr = 0.25 * 0.10 + 0.75 * arch["scramble_rate"]
        assert blended.usage.scramble_rate == pytest.approx(expected_sr, abs=0.01)

    def test_rb_blend_includes_carry_share(self):
        """RB blending should include carry_share from archetype."""
        usage = PlayerUsage(carry_share=0.40, target_share=0.06)
        outcomes = PlayerOutcomes(catch_rate=0.60, fumble_rate=0.01)
        model = PlayerModel(
            player_id="RB1", name="Rook RB", position="RB", team="KC",
            usage=usage, outcomes=outcomes, games_played=2,
        )
        blended = blend_with_archetype(model, rookie_blend_games=4)
        arch = POSITIONAL_ARCHETYPES["RB"]["tier3"]
        expected_cs = 0.5 * 0.40 + 0.5 * arch["carry_share"]
        assert blended.usage.carry_share == pytest.approx(expected_cs, abs=0.01)


class TestAggregatePbpStats:
    def test_returns_receiving_stats(self, expanded_pbp):
        """TK87 should have targets > 0 from the expanded_pbp fixture."""
        result = _aggregate_pbp_stats(expanded_pbp, training_seasons=[2024])
        receiving = result["receiving"]
        assert "TK87" in receiving
        assert receiving["TK87"]["targets"] > 0

    def test_returns_rushing_stats(self, expanded_pbp):
        """IP01 should have carries > 0 from the expanded_pbp fixture."""
        result = _aggregate_pbp_stats(expanded_pbp, training_seasons=[2024])
        rushing = result["rushing"]
        assert "IP01" in rushing
        assert rushing["IP01"]["carries"] > 0

    def test_returns_qb_stats(self, expanded_pbp):
        """PM15 should have attempts > 0 from the expanded_pbp fixture."""
        result = _aggregate_pbp_stats(expanded_pbp, training_seasons=[2024])
        qb = result["qb"]
        assert "PM15" in qb
        assert qb["PM15"]["attempts"] > 0

    def test_returns_team_totals(self, expanded_pbp):
        """KC should have pass and rush attempts > 0."""
        result = _aggregate_pbp_stats(expanded_pbp, training_seasons=[2024])
        assert result["team_pass_attempts"]["KC"] > 0
        assert result["team_rush_attempts"]["KC"] > 0

    def test_filters_by_training_seasons(self, expanded_pbp):
        """Passing [2023] with expanded_pbp (only 2024 data) returns empty receiving dict."""
        result = _aggregate_pbp_stats(expanded_pbp, training_seasons=[2023])
        assert result["receiving"] == {}


class TestBuildKickerModel:
    def test_returns_player_model(self):
        model = build_kicker_model("KC_K", "H.Butker", "KC")
        assert isinstance(model, PlayerModel)

    def test_has_kicker_position(self):
        model = build_kicker_model("KC_K", "H.Butker", "KC")
        assert model.position == "K"
        assert model.team == "KC"
        assert model.name == "H.Butker"

    def test_has_default_usage_and_outcomes(self):
        model = build_kicker_model("KC_K", "H.Butker", "KC")
        assert model.usage.target_share == 0.0
        assert model.usage.carry_share == 0.0
        assert model.games_played == 17


class TestAssembleModels:
    def test_player_with_pbp_gets_historical_stats(self, traded_player_pbp, traded_player_rosters):
        """IP01 has rushing PBP data — carry_share should be > 0."""
        agg = _aggregate_pbp_stats(traded_player_pbp, training_seasons=[2024])
        models = _assemble_models(agg, traded_player_rosters)
        assert "IP01" in models
        assert models["IP01"].usage.carry_share > 0

    def test_traded_player_gets_current_team(self, traded_player_pbp, traded_player_rosters):
        """JM28 played for CIN in 2024 PBP but is on HOU roster in 2025."""
        agg = _aggregate_pbp_stats(traded_player_pbp, training_seasons=[2024])
        models = _assemble_models(agg, traded_player_rosters)
        assert "JM28" in models
        assert models["JM28"].team == "HOU"

    def test_retired_player_excluded(self, traded_player_pbp, traded_player_rosters):
        """RET99 has PBP data but is not on any 2025 roster."""
        agg = _aggregate_pbp_stats(traded_player_pbp, training_seasons=[2024])
        models = _assemble_models(agg, traded_player_rosters)
        assert "RET99" not in models

    def test_rookie_gets_archetype_model(self, traded_player_pbp, traded_player_rosters):
        """ROOK1 is on HOU roster but has no PBP data — should get rookie archetype."""
        agg = _aggregate_pbp_stats(traded_player_pbp, training_seasons=[2024])
        models = _assemble_models(agg, traded_player_rosters)
        assert "ROOK1" in models
        assert models["ROOK1"].team == "HOU"
        assert models["ROOK1"].position == "WR"
        assert models["ROOK1"].usage.target_share > 0

    def test_kicker_gets_placeholder_model(self, traded_player_pbp, traded_player_rosters):
        """KC_K and HOU_K should be kicker placeholder models."""
        agg = _aggregate_pbp_stats(traded_player_pbp, training_seasons=[2024])
        models = _assemble_models(agg, traded_player_rosters)
        assert "KC_K" in models
        assert models["KC_K"].position == "K"
        assert "HOU_K" in models
        assert models["HOU_K"].position == "K"

    def test_ir_player_excluded(self, traded_player_pbp, traded_player_rosters):
        """IR01 is on KC roster with IR status — should be excluded."""
        agg = _aggregate_pbp_stats(traded_player_pbp, training_seasons=[2024])
        models = _assemble_models(agg, traded_player_rosters)
        assert "IR01" not in models

    def test_punter_excluded(self, traded_player_pbp, traded_player_rosters):
        """PNT1 is on KC roster as punter — should be excluded (not a fantasy position)."""
        agg = _aggregate_pbp_stats(traded_player_pbp, training_seasons=[2024])
        models = _assemble_models(agg, traded_player_rosters)
        assert "PNT1" not in models


class TestScrambleRateFix:
    def test_scramble_rate_uses_qb_scramble_column(self, scramble_qb_pbp, sample_rosters):
        """When qb_scramble column exists, only scrambles count toward scramble_rate."""
        models = build_player_models(scramble_qb_pbp, sample_rosters, training_seasons=[2024])
        ja = models.get("JA17")
        assert ja is not None
        # 4 scrambles / (20 passes + 4 scrambles) = 0.1667
        assert ja.usage.scramble_rate == pytest.approx(4 / 24, abs=0.01)

    def test_scramble_yards_dist_excludes_designed_runs(self, scramble_qb_pbp, sample_rosters):
        """scramble_yards_dist should only contain yards from qb_scramble=1 plays."""
        models = build_player_models(scramble_qb_pbp, sample_rosters, training_seasons=[2024])
        ja = models.get("JA17")
        assert ja is not None
        assert ja.outcomes.scramble_yards_dist is not None
        # Only scramble yards: [5, 8, 12, 3]
        assert sorted(ja.outcomes.scramble_yards_dist.tolist()) == [3, 5, 8, 12]

    def test_fallback_when_no_qb_scramble_column(self, scramble_pbp, sample_rosters):
        """Without qb_scramble column, fall back to existing behavior (all QB rushes)."""
        models = build_player_models(scramble_pbp, sample_rosters, training_seasons=[2024])
        ja = models.get("JA17")
        assert ja is not None
        # Old behavior: 3 rushes / (10 passes + 3 rushes) = 0.2308
        assert ja.usage.scramble_rate == pytest.approx(3 / 13, abs=0.01)

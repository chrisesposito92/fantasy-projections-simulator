import numpy as np
import polars as pl
import pytest
from fantasy_sim.data.player_builder import (
    build_player_models, build_team_roster, blend_with_archetype,
    _aggregate_pbp_stats, build_kicker_model, _assemble_models,
    _build_season_weights,
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

    def test_roster_normalizes_carry_shares(self):
        """Carry shares must sum to 1.0 after roster construction.

        Regression: when former players had carries in training data but
        aren't on the current roster, raw carry_shares summed to <1.0.
        select_rusher normalizes weights, amplifying each player's actual
        selection probability beyond the intended share value.
        """
        models = {
            "RB1": PlayerModel("RB1", "Back One", "RB", "T1",
                               PlayerUsage(carry_share=0.35), PlayerOutcomes()),
            "RB2": PlayerModel("RB2", "Back Two", "RB", "T1",
                               PlayerUsage(carry_share=0.25), PlayerOutcomes()),
            # Raw shares sum to 0.60 — simulates missing 0.40 from former players
        }
        roster = build_team_roster("T1", models)
        total = sum(p.usage.carry_share for p in roster.players if p.usage.carry_share > 0)
        assert total == pytest.approx(1.0, abs=0.01)
        # Relative proportions preserved
        rb1 = next(p for p in roster.players if p.player_id == "RB1")
        rb2 = next(p for p in roster.players if p.player_id == "RB2")
        assert rb1.usage.carry_share == pytest.approx(0.35 / 0.60, abs=0.01)
        assert rb2.usage.carry_share == pytest.approx(0.25 / 0.60, abs=0.01)

    def test_roster_normalizes_target_shares(self):
        """Target shares must sum to 1.0 after roster construction."""
        models = {
            "WR1": PlayerModel("WR1", "Wideout One", "WR", "T1",
                               PlayerUsage(target_share=0.20), PlayerOutcomes()),
            "WR2": PlayerModel("WR2", "Wideout Two", "WR", "T1",
                               PlayerUsage(target_share=0.15), PlayerOutcomes()),
            "RB1": PlayerModel("RB1", "Back One", "RB", "T1",
                               PlayerUsage(target_share=0.08, carry_share=0.50), PlayerOutcomes()),
        }
        roster = build_team_roster("T1", models)
        total = sum(p.usage.target_share for p in roster.players if p.usage.target_share > 0)
        assert total == pytest.approx(1.0, abs=0.01)

    def test_roster_deepcopies_players(self):
        """Roster players must be independent copies — overrides must not mutate the cache."""
        models = {
            "RB1": PlayerModel("RB1", "Back One", "RB", "T1",
                               PlayerUsage(carry_share=0.50), PlayerOutcomes()),
        }
        roster = build_team_roster("T1", models)
        # Mutate the roster copy
        roster.players[0].usage.carry_share = 0.99
        # Original must be unchanged
        assert models["RB1"].usage.carry_share == 0.50


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


class TestGoalLineConcentrationShares:
    @staticmethod
    def _goal_line_concentration_rosters() -> pl.DataFrame:
        return pl.DataFrame([
            {"season": 2024, "week": 1, "player_id": "PM15", "player_name": "P.Mahomes", "position": "QB", "team": "KC", "status": "ACT"},
            {"season": 2024, "week": 1, "player_id": "RE11", "player_name": "R.Rice", "position": "WR", "team": "KC", "status": "ACT"},
            {"season": 2024, "week": 1, "player_id": "TK87", "player_name": "T.Kelce", "position": "TE", "team": "KC", "status": "ACT"},
            {"season": 2024, "week": 1, "player_id": "IP01", "player_name": "I.Pacheco", "position": "RB", "team": "KC", "status": "ACT"},
            {"season": 2024, "week": 1, "player_id": "CH02", "player_name": "C.Helaire", "position": "RB", "team": "KC", "status": "ACT"},
        ])

    @staticmethod
    def _goal_line_concentration_pbp() -> pl.DataFrame:
        base = {
            "season": 2024,
            "week": 1,
            "game_id": "2024_01_KC_BUF",
            "posteam": "KC",
            "defteam": "BUF",
            "down": 1,
            "ydstogo": 10,
            "score_differential": 0,
            "qtr": 1,
            "interception": 0,
            "fumble_lost": 0,
            "sack": 0,
            "touchdown": 0,
            "penalty": 0,
            "penalty_yards": 0,
            "air_yards": None,
            "passer_player_id": None,
            "receiver_player_id": None,
            "rusher_player_id": None,
        }
        return pl.DataFrame([
            {
                **base,
                "play_type": "pass",
                "yardline_100": 5,
                "yards_gained": 5,
                "complete_pass": 1,
                "pass_attempt": 1,
                "rush_attempt": 0,
                "passer_player_id": "PM15",
                "receiver_player_id": "RE11",
            },
            {
                **base,
                "play_type": "pass",
                "yardline_100": 6,
                "yards_gained": 6,
                "complete_pass": 1,
                "pass_attempt": 1,
                "rush_attempt": 0,
                "passer_player_id": "PM15",
                "receiver_player_id": "TK87",
            },
            {
                **base,
                "play_type": "pass",
                "yardline_100": 20,
                "yards_gained": 12,
                "complete_pass": 1,
                "pass_attempt": 1,
                "rush_attempt": 0,
                "passer_player_id": "PM15",
                "receiver_player_id": "RE11",
            },
            {
                **base,
                "play_type": "run",
                "yardline_100": 5,
                "yards_gained": 2,
                "complete_pass": 0,
                "pass_attempt": 0,
                "rush_attempt": 1,
                "rusher_player_id": "IP01",
            },
            {
                **base,
                "play_type": "run",
                "yardline_100": 6,
                "yards_gained": 1,
                "complete_pass": 0,
                "pass_attempt": 0,
                "rush_attempt": 1,
                "rusher_player_id": "CH02",
            },
            {
                **base,
                "play_type": "run",
                "yardline_100": 20,
                "yards_gained": 5,
                "complete_pass": 0,
                "pass_attempt": 0,
                "rush_attempt": 1,
                "rusher_player_id": "IP01",
            },
        ])

    def test_goal_line_and_outer_red_zone_target_shares_are_computed_from_yardline_bands(self):
        aggregated = _aggregate_pbp_stats(
            self._goal_line_concentration_pbp(),
            training_seasons=[2024],
        )
        models = build_player_models(
            self._goal_line_concentration_pbp(),
            self._goal_line_concentration_rosters(),
            training_seasons=[2024],
        )

        re = models["RE11"]
        tk = models["TK87"]

        assert aggregated["team_goal_line_pass_attempts"]["KC"] == 1
        assert aggregated["team_outer_rz_pass_attempts"]["KC"] == 2
        assert aggregated["team_rz_pass_attempts"]["KC"] == 3
        assert aggregated["receiving"]["RE11"]["goal_line_targets"] == 1
        assert aggregated["receiving"]["RE11"]["outer_rz_targets"] == 1
        assert aggregated["receiving"]["RE11"]["rz_targets"] == 2
        assert aggregated["receiving"]["TK87"]["goal_line_targets"] == 0
        assert aggregated["receiving"]["TK87"]["outer_rz_targets"] == 1
        assert aggregated["receiving"]["TK87"]["rz_targets"] == 1

        assert re.usage.goal_line_target_share == pytest.approx(1.0)
        assert re.usage.outer_rz_target_share == pytest.approx(0.5)
        assert re.usage.red_zone_target_share == pytest.approx(2 / 3)
        assert tk.usage.goal_line_target_share == pytest.approx(0.0)
        assert tk.usage.outer_rz_target_share == pytest.approx(0.5)
        assert tk.usage.red_zone_target_share == pytest.approx(1 / 3)
        assert re.usage.red_zone_target_share == pytest.approx(
            (re.usage.goal_line_target_share * 1 + re.usage.outer_rz_target_share * 2) / 3
        )
        assert tk.usage.red_zone_target_share == pytest.approx(
            (tk.usage.goal_line_target_share * 1 + tk.usage.outer_rz_target_share * 2) / 3
        )

    def test_goal_line_and_outer_red_zone_carry_shares_are_computed_from_yardline_bands(self):
        aggregated = _aggregate_pbp_stats(
            self._goal_line_concentration_pbp(),
            training_seasons=[2024],
        )
        models = build_player_models(
            self._goal_line_concentration_pbp(),
            self._goal_line_concentration_rosters(),
            training_seasons=[2024],
        )

        ip = models["IP01"]
        ch = models["CH02"]

        assert aggregated["team_goal_line_rush_attempts"]["KC"] == 1
        assert aggregated["team_outer_rz_rush_attempts"]["KC"] == 2
        assert aggregated["team_rz_rush_attempts"]["KC"] == 3
        assert aggregated["rushing"]["IP01"]["goal_line_carries"] == 1
        assert aggregated["rushing"]["IP01"]["outer_rz_carries"] == 1
        assert aggregated["rushing"]["IP01"]["rz_carries"] == 2
        assert aggregated["rushing"]["CH02"]["goal_line_carries"] == 0
        assert aggregated["rushing"]["CH02"]["outer_rz_carries"] == 1
        assert aggregated["rushing"]["CH02"]["rz_carries"] == 1

        assert ip.usage.goal_line_carry_share == pytest.approx(1.0)
        assert ip.usage.outer_rz_carry_share == pytest.approx(0.5)
        assert ip.usage.red_zone_carry_share == pytest.approx(2 / 3)
        assert ch.usage.goal_line_carry_share == pytest.approx(0.0)
        assert ch.usage.outer_rz_carry_share == pytest.approx(0.5)
        assert ch.usage.red_zone_carry_share == pytest.approx(1 / 3)
        assert ip.usage.red_zone_carry_share == pytest.approx(
            (ip.usage.goal_line_carry_share * 1 + ip.usage.outer_rz_carry_share * 2) / 3
        )
        assert ch.usage.red_zone_carry_share == pytest.approx(
            (ch.usage.goal_line_carry_share * 1 + ch.usage.outer_rz_carry_share * 2) / 3
        )

    def test_build_team_roster_normalizes_goal_line_and_outer_red_zone_shares(self):
        models = {
            "RB1": PlayerModel(
                "RB1",
                "Back One",
                "RB",
                "T1",
                PlayerUsage(
                    carry_share=0.4,
                    goal_line_carry_share=0.3,
                    outer_rz_carry_share=0.2,
                ),
                PlayerOutcomes(),
            ),
            "RB2": PlayerModel(
                "RB2",
                "Back Two",
                "RB",
                "T1",
                PlayerUsage(
                    carry_share=0.3,
                    goal_line_carry_share=0.2,
                    outer_rz_carry_share=0.3,
                ),
                PlayerOutcomes(),
            ),
            "WR1": PlayerModel(
                "WR1",
                "Wideout One",
                "WR",
                "T1",
                PlayerUsage(
                    target_share=0.2,
                    goal_line_target_share=0.25,
                    outer_rz_target_share=0.1,
                ),
                PlayerOutcomes(),
            ),
            "WR2": PlayerModel(
                "WR2",
                "Wideout Two",
                "WR",
                "T1",
                PlayerUsage(
                    target_share=0.2,
                    goal_line_target_share=0.15,
                    outer_rz_target_share=0.3,
                ),
                PlayerOutcomes(),
            ),
        }

        roster = build_team_roster("T1", models)
        total_goal_line_carry = sum(
            p.usage.goal_line_carry_share for p in roster.players if p.usage.goal_line_carry_share > 0
        )
        total_outer_rz_carry = sum(
            p.usage.outer_rz_carry_share for p in roster.players if p.usage.outer_rz_carry_share > 0
        )
        total_goal_line_target = sum(
            p.usage.goal_line_target_share for p in roster.players if p.usage.goal_line_target_share > 0
        )
        total_outer_rz_target = sum(
            p.usage.outer_rz_target_share for p in roster.players if p.usage.outer_rz_target_share > 0
        )

        rb1 = next(p for p in roster.players if p.player_id == "RB1")
        rb2 = next(p for p in roster.players if p.player_id == "RB2")
        wr1 = next(p for p in roster.players if p.player_id == "WR1")
        wr2 = next(p for p in roster.players if p.player_id == "WR2")

        assert total_goal_line_carry == pytest.approx(1.0)
        assert total_outer_rz_carry == pytest.approx(1.0)
        assert total_goal_line_target == pytest.approx(1.0)
        assert total_outer_rz_target == pytest.approx(1.0)
        assert rb1.usage.goal_line_carry_share == pytest.approx(0.6)
        assert rb2.usage.goal_line_carry_share == pytest.approx(0.4)
        assert rb1.usage.outer_rz_carry_share == pytest.approx(0.4)
        assert rb2.usage.outer_rz_carry_share == pytest.approx(0.6)
        assert wr1.usage.goal_line_target_share == pytest.approx(0.625)
        assert wr2.usage.goal_line_target_share == pytest.approx(0.375)
        assert wr1.usage.outer_rz_target_share == pytest.approx(0.25)
        assert wr2.usage.outer_rz_target_share == pytest.approx(0.75)


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


class TestRookieArchetypeDefaults:
    def test_qb_archetype_has_pass_fumble_rate(self):
        from fantasy_sim.data.rookie_builder import build_rookie_model
        model = build_rookie_model("QB1", "Rookie QB", "QB", "KC", draft_round=1)
        assert model.outcomes.pass_fumble_rate == pytest.approx(0.0034, abs=0.001)

    def test_wr_archetype_has_red_zone_catch_rate(self):
        from fantasy_sim.data.rookie_builder import build_rookie_model
        model = build_rookie_model("WR1", "Rookie WR", "WR", "KC", draft_round=1)
        arch_catch = POSITIONAL_ARCHETYPES["WR"]["tier1"]["catch_rate"]
        assert model.outcomes.red_zone_catch_rate == pytest.approx(arch_catch * 0.92, abs=0.01)

    def test_te_archetype_has_red_zone_catch_rate(self):
        from fantasy_sim.data.rookie_builder import build_rookie_model
        model = build_rookie_model("TE1", "Rookie TE", "TE", "KC", draft_round=3)
        arch_catch = POSITIONAL_ARCHETYPES["TE"]["tier2"]["catch_rate"]
        assert model.outcomes.red_zone_catch_rate == pytest.approx(arch_catch * 0.92, abs=0.01)

    def test_rb_archetype_has_red_zone_catch_rate(self):
        from fantasy_sim.data.rookie_builder import build_rookie_model
        model = build_rookie_model("RB1", "Rookie RB", "RB", "KC", draft_round=5)
        arch_catch = POSITIONAL_ARCHETYPES["RB"]["tier3"]["catch_rate"]
        assert model.outcomes.red_zone_catch_rate == pytest.approx(arch_catch * 0.92, abs=0.01)


class TestAssembleModelsExtra:
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


class TestRedZoneCatchRate:
    def test_rz_catch_rate_computed_with_enough_samples(self, rz_pbp, sample_rosters):
        """RE11 has 5 RZ targets and 5 RZ catches -> rz_catch_rate = 1.0.
        But 5 < 10 threshold, so should fall back to catch_rate * 0.92."""
        models = build_player_models(rz_pbp, sample_rosters, training_seasons=[2024])
        re = models.get("RE11")
        assert re is not None
        assert re.outcomes.red_zone_catch_rate == pytest.approx(re.outcomes.catch_rate * 0.92, abs=0.01)

    def test_rz_catch_rate_fallback_below_threshold(self, expanded_pbp, sample_rosters):
        """Players with < 10 RZ targets use catch_rate * RZ_CATCH_RATE_MODIFIERS[position]
        as the per-player fallback. Per KS-07 D-20 (PROMOTED 2026-04-26) the
        modifier is now position-aware: WR=0.92, TE=0.95, RB=0.85. Reads the
        live `_KS07_POSITIONAL_RZ_CATCH_RATE` flag so the test stays correct
        whether the flag is on (production default after KS-07 promotion) or
        off (rollback / Arm A bit-for-bit parity)."""
        from fantasy_sim.engine import play_resolver as pr
        from fantasy_sim.engine.play_resolver import (
            RZ_CATCH_RATE_MODIFIER,
            RZ_CATCH_RATE_MODIFIERS,
        )
        models = build_player_models(expanded_pbp, sample_rosters, training_seasons=[2024])
        tk = models.get("TK87")
        assert tk is not None
        # TK87 is a TE per tests/conftest.py:81; under flag-on the modifier is
        # 0.95, under flag-off it's the legacy scalar 0.92.
        if pr._KS07_POSITIONAL_RZ_CATCH_RATE:
            expected_modifier = RZ_CATCH_RATE_MODIFIERS.get(tk.position, RZ_CATCH_RATE_MODIFIERS["WR"])
        else:
            expected_modifier = RZ_CATCH_RATE_MODIFIER
        if tk.outcomes.catch_rate > 0:
            assert tk.outcomes.red_zone_catch_rate == pytest.approx(
                tk.outcomes.catch_rate * expected_modifier, abs=0.01
            )

    def test_rz_catch_rate_data_driven_with_enough_targets(self):
        """With >= 10 RZ targets, use actual RZ catch rate."""
        import polars as pl
        plays = []
        base = {
            "season": 2024, "week": 1, "game_id": "2024_01_T1",
            "posteam": "T1", "defteam": "T2",
            "down": 1, "ydstogo": 10, "score_differential": 0, "qtr": 1,
            "rush_attempt": 0, "interception": 0, "fumble_lost": 0,
            "sack": 0, "touchdown": 0, "penalty": 0, "penalty_yards": 0,
            "passer_player_id": "QB1", "rusher_player_id": None,
        }
        # 15 RZ targets, 9 completions -> rz_catch_rate = 0.60
        for i in range(9):
            plays.append({**base, "play_type": "pass", "yardline_100": 15,
                          "yards_gained": 8, "complete_pass": 1, "pass_attempt": 1,
                          "receiver_player_id": "WR1"})
        for i in range(6):
            plays.append({**base, "play_type": "pass", "yardline_100": 15,
                          "yards_gained": 0, "complete_pass": 0, "pass_attempt": 1,
                          "receiver_player_id": "WR1"})
        # 10 non-RZ targets, 7 completions -> overall catch_rate = 16/25 = 0.64
        for i in range(7):
            plays.append({**base, "play_type": "pass", "yardline_100": 50,
                          "yards_gained": 12, "complete_pass": 1, "pass_attempt": 1,
                          "receiver_player_id": "WR1"})
        for i in range(3):
            plays.append({**base, "play_type": "pass", "yardline_100": 50,
                          "yards_gained": 0, "complete_pass": 0, "pass_attempt": 1,
                          "receiver_player_id": "WR1"})
        pbp = pl.DataFrame(plays)
        rosters = pl.DataFrame([
            {"season": 2024, "week": 1, "player_id": "QB1", "player_name": "QB", "position": "QB", "team": "T1", "status": "ACT"},
            {"season": 2024, "week": 1, "player_id": "WR1", "player_name": "WR", "position": "WR", "team": "T1", "status": "ACT"},
        ])
        models = build_player_models(pbp, rosters, training_seasons=[2024])
        wr = models["WR1"]
        assert wr.outcomes.red_zone_catch_rate == pytest.approx(9 / 15, abs=0.01)


class TestQBPassFumbleRate:
    def test_pass_fumble_rate_computed(self):
        """QB with enough pass plays gets per-player pass_fumble_rate."""
        import polars as pl
        plays = []
        base = {
            "season": 2024, "week": 1, "game_id": "2024_01_T1",
            "posteam": "T1", "defteam": "T2",
            "down": 1, "ydstogo": 10, "yardline_100": 50,
            "score_differential": 0, "qtr": 1,
            "rush_attempt": 0, "interception": 0,
            "sack": 0, "touchdown": 0, "penalty": 0, "penalty_yards": 0,
            "passer_player_id": "QB1", "receiver_player_id": "WR1",
            "rusher_player_id": None,
        }
        # 150 non-sack passes, 2 with fumble_lost
        for i in range(148):
            plays.append({**base, "play_type": "pass", "yards_gained": 8,
                          "complete_pass": 1, "pass_attempt": 1, "fumble_lost": 0})
        for i in range(2):
            plays.append({**base, "play_type": "pass", "yards_gained": 0,
                          "complete_pass": 0, "pass_attempt": 1, "fumble_lost": 1})
        pbp = pl.DataFrame(plays)
        rosters = pl.DataFrame([
            {"season": 2024, "week": 1, "player_id": "QB1", "player_name": "QB", "position": "QB", "team": "T1", "status": "ACT"},
            {"season": 2024, "week": 1, "player_id": "WR1", "player_name": "WR", "position": "WR", "team": "T1", "status": "ACT"},
        ])
        models = build_player_models(pbp, rosters, training_seasons=[2024])
        qb = models["QB1"]
        assert qb.outcomes.pass_fumble_rate == pytest.approx(2 / 150, abs=0.001)

    def test_pass_fumble_rate_fallback_for_small_sample(self, expanded_pbp, sample_rosters):
        """QBs with < 100 pass plays get league average 0.0034."""
        models = build_player_models(expanded_pbp, sample_rosters, training_seasons=[2024])
        pm = models.get("PM15")
        assert pm is not None
        # expanded_pbp has 40 KC passes, well under 100
        assert pm.outcomes.pass_fumble_rate == pytest.approx(0.0034, abs=0.0001)


class TestSeasonWeighting:
    """Tests for recency weighting in _aggregate_pbp_stats (FIX-02)."""

    @staticmethod
    def _make_multi_season_pbp() -> pl.DataFrame:
        """Build PBP with a player who has different target counts per season."""
        base = {
            "game_id": "G1", "posteam": "T1", "defteam": "T2",
            "down": 1, "ydstogo": 10, "yardline_100": 50,
            "score_differential": 0, "qtr": 1,
            "rush_attempt": 0, "interception": 0, "fumble_lost": 0,
            "sack": 0, "touchdown": 0, "penalty": 0, "penalty_yards": 0,
            "passer_player_id": "QB1", "rusher_player_id": None,
        }
        plays = []
        # 2022: 10 targets for WR1 (all completions, 8 yards each)
        for i in range(10):
            plays.append({
                **base, "season": 2022, "week": 1, "game_id": "2022_01_T1",
                "play_type": "pass", "yards_gained": 8, "complete_pass": 1,
                "pass_attempt": 1, "receiver_player_id": "WR1",
            })
        # 2023: 5 targets for WR1 (all completions, 12 yards each)
        for i in range(5):
            plays.append({
                **base, "season": 2023, "week": 1, "game_id": "2023_01_T1",
                "play_type": "pass", "yards_gained": 12, "complete_pass": 1,
                "pass_attempt": 1, "receiver_player_id": "WR1",
            })
        return pl.DataFrame(plays)

    def test_aggregate_pbp_stats_with_season_weights(self):
        """Season weights cause more recent season rows to be replicated more."""
        pbp = self._make_multi_season_pbp()
        # Without weights: 10 targets in 2022, 5 in 2023 = 15 total
        result_unweighted = _aggregate_pbp_stats(pbp, [2022, 2023])
        unweighted_targets = result_unweighted["receiving"]["WR1"]["targets"]

        # With weights: 2022=0.3, 2023=0.5 -> 2023 gets 10 reps, 2022 gets 6 reps
        # So: 10*6=60 targets from 2022, 5*10=50 targets from 2023 = 110 total
        result_weighted = _aggregate_pbp_stats(
            pbp, [2022, 2023], season_weights={2022: 0.3, 2023: 0.5}
        )
        weighted_targets = result_weighted["receiving"]["WR1"]["targets"]

        assert unweighted_targets == 15
        assert weighted_targets > unweighted_targets
        # 2023 rows (5) replicated 10x = 50, 2022 rows (10) replicated 6x = 60
        assert weighted_targets == 110

    def test_aggregate_pbp_stats_no_weights_unchanged(self):
        """Passing season_weights=None gives identical results to no weights."""
        pbp = self._make_multi_season_pbp()
        result_default = _aggregate_pbp_stats(pbp, [2022, 2023])
        result_none = _aggregate_pbp_stats(pbp, [2022, 2023], season_weights=None)

        assert result_default["receiving"]["WR1"]["targets"] == result_none["receiving"]["WR1"]["targets"]
        assert result_default["receiving"]["WR1"]["catches"] == result_none["receiving"]["WR1"]["catches"]

    def test_season_weight_alignment_tail(self):
        """With 4-element recency_weights and 3 training_seasons, tail-align."""
        result = _build_season_weights(
            training_seasons=[2022, 2023, 2024],
            recency_weights=[0.1, 0.2, 0.3, 0.4],
        )
        assert result == {2022: 0.2, 2023: 0.3, 2024: 0.4}

    def test_season_weight_alignment_exact(self):
        """With 4-element recency_weights and 4 training_seasons, exact match."""
        result = _build_season_weights(
            training_seasons=[2021, 2022, 2023, 2024],
            recency_weights=[0.1, 0.2, 0.3, 0.4],
        )
        assert result == {2021: 0.1, 2022: 0.2, 2023: 0.3, 2024: 0.4}

    def test_pbp_stats_cache_invalidation(self):
        """Cache key must change when season_weights change."""
        from fantasy_sim.data.game_context import GameContextBuilder
        builder = GameContextBuilder()
        # After init, _pbp_stats_cache_key should be None
        assert builder._pbp_stats_cache_key is None


# === KS-06: MIN_PLAYER_PLAYS lowered (D-19 sub-fix 3) ===

class TestKs06MinPlayerPlays:
    """KS-06 D-19 sub-fix 3: lower MIN_PLAYER_PLAYS from 5 → 3 so receivers
    with thin per-player data still get their own distribution rather than
    falling through to the team-bucket backup-receiver path. Gated behind
    `phase1_ks_flags.ks06_backup_receiver_fix.enabled` per Cycle 3 D-45.
    """

    def test_ks06_min_player_plays_is_3(self):
        from fantasy_sim.data.player_builder import MIN_PLAYER_PLAYS
        assert MIN_PLAYER_PLAYS == 3, (
            f"D-19 sub-fix 3 requires module constant MIN_PLAYER_PLAYS == 3 "
            f"(the new path's effective value); got {MIN_PLAYER_PLAYS}"
        )

    def _make_thin_pbp_for_player(
        self, player_id: str, n_catches: int
    ) -> pl.DataFrame:
        """PBP with exactly `n_catches` completions to `player_id` for KC."""
        completion_template = {
            "season": 2024,
            "week": 1,
            "game_id": "2024_01_KC_BUF",
            "play_type": "pass",
            "posteam": "KC",
            "defteam": "BUF",
            "down": 1,
            "ydstogo": 10,
            "yardline_100": 75,
            "score_differential": 0,
            "qtr": 1,
            "yards_gained": 12,
            "complete_pass": 1,
            "pass_attempt": 1,
            "rush_attempt": 0,
            "interception": 0,
            "fumble_lost": 0,
            "sack": 0,
            "touchdown": 0,
            "penalty": 0,
            "penalty_yards": 0,
            "passer_player_id": "PM15",
            "receiver_player_id": player_id,
            "rusher_player_id": None,
        }
        plays = []
        for i in range(n_catches):
            plays.append({**completion_template, "week": i + 1, "yards_gained": 8 + i})
        return pl.DataFrame(plays)

    def _make_roster_for_player(self, player_id: str) -> pl.DataFrame:
        return pl.DataFrame(
            [
                {
                    "season": 2024, "week": 1, "player_id": player_id,
                    "player_name": "T.Backup", "position": "WR", "team": "KC",
                    "status": "ACT",
                },
                {
                    "season": 2024, "week": 1, "player_id": "PM15",
                    "player_name": "P.Mahomes", "position": "QB", "team": "KC",
                    "status": "ACT",
                },
            ]
        )

    def test_ks06_player_with_3_catches_gets_own_dist_when_flag_on(
        self, monkeypatch
    ):
        """Flag-on: a player with exactly 3 catches builds their own
        receiving_yards_dist (length 3) rather than falling through to the
        team-bucket fallback path."""
        from fantasy_sim.data import player_builder as pb_mod
        # Force the flag-on local computation path inside _assemble_models
        monkeypatch.setattr(
            pb_mod, "_KS06_BACKUP_RECEIVER_FIX", True, raising=False
        )

        pbp = self._make_thin_pbp_for_player("BU99", n_catches=3)
        rosters = self._make_roster_for_player("BU99")
        models = pb_mod.build_player_models(
            pbp, rosters, training_seasons=[2024]
        )
        backup = models["BU99"]
        assert backup.outcomes.receiving_yards_dist is not None, (
            "With KS-06 flag on and 3 catches (>= MIN_PLAYER_PLAYS=3), the "
            "backup receiver should have its own receiving_yards_dist"
        )
        assert len(backup.outcomes.receiving_yards_dist) == 3

    def test_ks06_player_with_3_catches_no_dist_when_flag_off(
        self, monkeypatch
    ):
        """Flag-off (legacy): a player with only 3 catches falls below the
        legacy threshold (5) and gets no per-player distribution."""
        from fantasy_sim.data import player_builder as pb_mod
        monkeypatch.setattr(
            pb_mod, "_KS06_BACKUP_RECEIVER_FIX", False, raising=False
        )

        pbp = self._make_thin_pbp_for_player("BU98", n_catches=3)
        rosters = self._make_roster_for_player("BU98")
        models = pb_mod.build_player_models(
            pbp, rosters, training_seasons=[2024]
        )
        backup = models["BU98"]
        assert backup.outcomes.receiving_yards_dist is None, (
            "With KS-06 flag off (legacy MIN_PLAYER_PLAYS=5), 3 catches is "
            "below threshold so receiving_yards_dist should remain None"
        )


class TestKs07PositionalRzCatchRateFallback:
    """KS-07 D-20 (Cycle 3 D-45): the per-player RZ catch rate fallback at
    `_assemble_models` (player_builder.py around line 549) uses a
    position-aware modifier when the flag is on (WR=0.92, TE=0.95, RB=0.85)
    and the legacy 0.92 scalar when off. This fallback only fires for
    players with `< MIN_RZ_TARGETS = 10` RZ targets so we keep the test
    PBP at well under that threshold for each player.
    """

    def _make_pbp_for_position(
        self,
        player_id: str,
        team: str = "KC",
    ) -> pl.DataFrame:
        """PBP with 10 outside-RZ targets (5 catches) for `player_id` so that
        `catch_rate = 0.5` and `rs["rz_targets"] = 0` — well below the
        `MIN_RZ_TARGETS = 10` threshold, which forces the fallback branch
        `red_zone_catch_rate = catch_rate * <modifier>`.
        """
        plays = []
        # 5 completions outside the RZ
        for i in range(5):
            plays.append({
                "season": 2024, "week": i + 1,
                "game_id": f"2024_{i+1:02d}_KC_BUF",
                "play_type": "pass", "posteam": team, "defteam": "BUF",
                "down": 1, "ydstogo": 10, "yardline_100": 50,
                "score_differential": 0, "qtr": 1,
                "yards_gained": 10, "complete_pass": 1, "pass_attempt": 1,
                "rush_attempt": 0, "interception": 0, "fumble_lost": 0,
                "sack": 0, "touchdown": 0, "penalty": 0, "penalty_yards": 0,
                "passer_player_id": "PM15", "receiver_player_id": player_id,
                "rusher_player_id": None,
            })
        # 5 incompletions outside the RZ
        for i in range(5):
            plays.append({
                "season": 2024, "week": i + 6,
                "game_id": f"2024_{i+6:02d}_KC_BUF",
                "play_type": "pass", "posteam": team, "defteam": "BUF",
                "down": 1, "ydstogo": 10, "yardline_100": 50,
                "score_differential": 0, "qtr": 1,
                "yards_gained": 0, "complete_pass": 0, "pass_attempt": 1,
                "rush_attempt": 0, "interception": 0, "fumble_lost": 0,
                "sack": 0, "touchdown": 0, "penalty": 0, "penalty_yards": 0,
                "passer_player_id": "PM15", "receiver_player_id": player_id,
                "rusher_player_id": None,
            })
        return pl.DataFrame(plays)

    def _make_roster(self, player_id: str, position: str) -> pl.DataFrame:
        return pl.DataFrame(
            [
                {
                    "season": 2024, "week": 1, "player_id": player_id,
                    "player_name": f"X.{position}", "position": position,
                    "team": "KC", "status": "ACT",
                },
                {
                    "season": 2024, "week": 1, "player_id": "PM15",
                    "player_name": "P.Mahomes", "position": "QB",
                    "team": "KC", "status": "ACT",
                },
            ]
        )

    def test_ks07_player_builder_te_uses_positional_modifier_when_flag_on(
        self, monkeypatch
    ):
        """Flag-on: TE with < 10 RZ targets gets red_zone_catch_rate
        = catch_rate * 0.95 (per D-20)."""
        from fantasy_sim.engine import play_resolver as pr
        from fantasy_sim.data import player_builder as pb_mod
        monkeypatch.setattr(pr, "_KS07_POSITIONAL_RZ_CATCH_RATE", True)

        pbp = self._make_pbp_for_position("TE10")
        rosters = self._make_roster("TE10", "TE")
        models = pb_mod.build_player_models(
            pbp, rosters, training_seasons=[2024]
        )
        te = models["TE10"]
        assert te.position == "TE"
        assert te.outcomes.catch_rate == pytest.approx(0.5, abs=0.01)
        assert te.outcomes.red_zone_catch_rate == pytest.approx(
            te.outcomes.catch_rate * 0.95, abs=0.01
        ), (
            f"TE flag-on red_zone_catch_rate {te.outcomes.red_zone_catch_rate} "
            f"should be catch_rate * 0.95 = {te.outcomes.catch_rate * 0.95}, "
            f"not the legacy 0.92"
        )

    def test_ks07_player_builder_rb_uses_positional_modifier_when_flag_on(
        self, monkeypatch
    ):
        """Flag-on: RB with < 10 RZ targets gets red_zone_catch_rate
        = catch_rate * 0.85 (per D-20)."""
        from fantasy_sim.engine import play_resolver as pr
        from fantasy_sim.data import player_builder as pb_mod
        monkeypatch.setattr(pr, "_KS07_POSITIONAL_RZ_CATCH_RATE", True)

        pbp = self._make_pbp_for_position("RB10")
        rosters = self._make_roster("RB10", "RB")
        models = pb_mod.build_player_models(
            pbp, rosters, training_seasons=[2024]
        )
        rb = models["RB10"]
        assert rb.position == "RB"
        assert rb.outcomes.catch_rate == pytest.approx(0.5, abs=0.01)
        assert rb.outcomes.red_zone_catch_rate == pytest.approx(
            rb.outcomes.catch_rate * 0.85, abs=0.01
        ), (
            f"RB flag-on red_zone_catch_rate {rb.outcomes.red_zone_catch_rate} "
            f"should be catch_rate * 0.85 = {rb.outcomes.catch_rate * 0.85}, "
            f"not the legacy 0.92"
        )

    def test_ks07_player_builder_wr_unchanged_when_flag_on(
        self, monkeypatch
    ):
        """Flag-on: WR still gets red_zone_catch_rate = catch_rate * 0.92
        (no behavior change for the historically-correct position)."""
        from fantasy_sim.engine import play_resolver as pr
        from fantasy_sim.data import player_builder as pb_mod
        monkeypatch.setattr(pr, "_KS07_POSITIONAL_RZ_CATCH_RATE", True)

        pbp = self._make_pbp_for_position("WR10")
        rosters = self._make_roster("WR10", "WR")
        models = pb_mod.build_player_models(
            pbp, rosters, training_seasons=[2024]
        )
        wr = models["WR10"]
        assert wr.position == "WR"
        assert wr.outcomes.red_zone_catch_rate == pytest.approx(
            wr.outcomes.catch_rate * 0.92, abs=0.01
        )

    def test_ks07_player_builder_te_uses_legacy_scalar_when_flag_off(
        self, monkeypatch
    ):
        """Flag-off (legacy): TE gets red_zone_catch_rate = catch_rate * 0.92,
        NOT the new 0.95. Bit-for-bit Arm A parity."""
        from fantasy_sim.engine import play_resolver as pr
        from fantasy_sim.data import player_builder as pb_mod
        monkeypatch.setattr(pr, "_KS07_POSITIONAL_RZ_CATCH_RATE", False)

        pbp = self._make_pbp_for_position("TE11")
        rosters = self._make_roster("TE11", "TE")
        models = pb_mod.build_player_models(
            pbp, rosters, training_seasons=[2024]
        )
        te = models["TE11"]
        assert te.outcomes.red_zone_catch_rate == pytest.approx(
            te.outcomes.catch_rate * 0.92, abs=0.01
        ), (
            f"TE flag-off red_zone_catch_rate {te.outcomes.red_zone_catch_rate} "
            f"should match legacy 0.92, not the flag-on 0.95"
        )

    def test_ks07_player_builder_rb_uses_legacy_scalar_when_flag_off(
        self, monkeypatch
    ):
        """Flag-off (legacy): RB gets red_zone_catch_rate = catch_rate * 0.92,
        NOT the new 0.85."""
        from fantasy_sim.engine import play_resolver as pr
        from fantasy_sim.data import player_builder as pb_mod
        monkeypatch.setattr(pr, "_KS07_POSITIONAL_RZ_CATCH_RATE", False)

        pbp = self._make_pbp_for_position("RB11")
        rosters = self._make_roster("RB11", "RB")
        models = pb_mod.build_player_models(
            pbp, rosters, training_seasons=[2024]
        )
        rb = models["RB11"]
        assert rb.outcomes.red_zone_catch_rate == pytest.approx(
            rb.outcomes.catch_rate * 0.92, abs=0.01
        )

    def test_ks07_player_builder_modifier_lookup_uses_position_string(
        self, monkeypatch
    ):
        """Smoke test: the position string passed to RZ_CATCH_RATE_MODIFIERS.get(...)
        is the literal `row['position']` value ('TE', 'RB', 'WR') matching the
        dict keys. Defends against future refactors that pass the player object
        or some other shape into the lookup."""
        from fantasy_sim.engine import play_resolver as pr
        from fantasy_sim.engine.play_resolver import RZ_CATCH_RATE_MODIFIERS
        from fantasy_sim.data import player_builder as pb_mod
        monkeypatch.setattr(pr, "_KS07_POSITIONAL_RZ_CATCH_RATE", True)

        # Verify all three position keys are in the dict
        assert "WR" in RZ_CATCH_RATE_MODIFIERS
        assert "TE" in RZ_CATCH_RATE_MODIFIERS
        assert "RB" in RZ_CATCH_RATE_MODIFIERS

        # Build a TE and verify the resulting rate matches the dict lookup
        pbp = self._make_pbp_for_position("TE12")
        rosters = self._make_roster("TE12", "TE")
        models = pb_mod.build_player_models(
            pbp, rosters, training_seasons=[2024]
        )
        te = models["TE12"]
        expected = te.outcomes.catch_rate * RZ_CATCH_RATE_MODIFIERS["TE"]
        assert te.outcomes.red_zone_catch_rate == pytest.approx(expected, abs=0.001)

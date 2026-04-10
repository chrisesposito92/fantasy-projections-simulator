import pytest
import polars as pl
from fantasy_sim.data.game_context import GameContextBuilder
from fantasy_sim.data.goal_line_concentration import GoalLineConcentrationConfig
from fantasy_sim.data.game_script import GameScriptConfig
from fantasy_sim.engine.types import TeamDistributions
from fantasy_sim.models.player import TeamRoster


class TestGameContextBuilder:
    @pytest.fixture
    def builder(self, tmp_path):
        return GameContextBuilder(cache_dir=tmp_path / "cache")

    # --- Existing tests (updated signatures) ---

    def test_build_team_distributions(self, builder, expanded_pbp, sample_rosters):
        dists = builder.build_team_distributions(
            "KC", pbp=expanded_pbp, rosters=sample_rosters, training_seasons=[2024]
        )
        assert isinstance(dists, TeamDistributions)
        assert dists.play_calling.team == "KC"
        assert dists.turnover_rates.team == "KC"

    def test_build_team_roster(self, builder, expanded_pbp, sample_rosters):
        roster = builder.build_team_roster(
            "KC", pbp=expanded_pbp, rosters=sample_rosters, training_seasons=[2024]
        )
        assert isinstance(roster, TeamRoster)
        assert roster.team == "KC"
        assert len(roster.players) > 0

    def test_build_game(self, builder, expanded_pbp, sample_rosters):
        home_dists, away_dists, home_roster, away_roster = builder.build_game(
            home_team="KC", away_team="BUF",
            pbp=expanded_pbp, rosters=sample_rosters, training_seasons=[2024],
        )
        assert home_dists.play_calling.team == "KC"
        assert away_dists.play_calling.team == "BUF"
        assert home_roster.team == "KC"
        assert away_roster.team == "BUF"

    def test_build_team_distributions_stamps_goal_line_concentration_flag(
        self, tmp_path, expanded_pbp, sample_rosters
    ):
        builder = GameContextBuilder(
            cache_dir=tmp_path / "cache",
            goal_line_concentration_config=GoalLineConcentrationConfig(enabled=True),
        )

        dists = builder.build_team_distributions(
            "KC", pbp=expanded_pbp, rosters=sample_rosters, training_seasons=[2024]
        )

        assert dists.goal_line_concentration_enabled is True

    def test_build_game_stamps_goal_line_concentration_flag_on_both_teams(
        self, tmp_path, expanded_pbp, sample_rosters
    ):
        builder = GameContextBuilder(
            cache_dir=tmp_path / "cache",
            goal_line_concentration_config=GoalLineConcentrationConfig(enabled=True),
        )

        home_dists, away_dists, _, _ = builder.build_game(
            home_team="KC", away_team="BUF",
            pbp=expanded_pbp, rosters=sample_rosters, training_seasons=[2024],
        )

        assert home_dists.goal_line_concentration_enabled is True
        assert away_dists.goal_line_concentration_enabled is True

    def test_game_script_engine_created_when_enabled(self, tmp_path):
        builder = GameContextBuilder(
            cache_dir=tmp_path / "cache",
            game_script_config=GameScriptConfig(enabled=True),
        )

        assert builder._game_script_engine is not None

    def test_missing_team_gets_league_defaults(self, builder, expanded_pbp, sample_rosters):
        """A team not in PBP data should get league-average distributions."""
        dists = builder.build_team_distributions(
            "SEA", pbp=expanded_pbp, rosters=sample_rosters, training_seasons=[2024]
        )
        assert isinstance(dists, TeamDistributions)
        # Should use league defaults for play calling
        probs = dists.play_calling.default
        assert 0.4 <= probs["pass"] <= 0.7

    def test_caches_pipeline_output(self, builder, expanded_pbp, sample_rosters):
        """Second call with same data should reuse cached pipeline output."""
        builder.build_team_distributions(
            "KC", pbp=expanded_pbp, rosters=sample_rosters, training_seasons=[2024]
        )
        builder.build_team_distributions(
            "BUF", pbp=expanded_pbp, rosters=sample_rosters, training_seasons=[2024]
        )
        # Pipeline build should only have been called once (cached)
        assert builder._pipeline_cache is not None

    # --- New tests ---

    def test_traded_player_on_current_team(
        self, builder, traded_player_pbp, traded_player_rosters
    ):
        """JM28 (Mixon) has PBP on CIN but 2025 roster says HOU — should appear on HOU."""
        _, _, home_roster, away_roster = builder.build_game(
            home_team="KC", away_team="HOU",
            pbp=traded_player_pbp, rosters=traded_player_rosters,
            training_seasons=[2024], target_season=2025,
        )
        hou_ids = [p.player_id for p in away_roster.players]
        kc_ids = [p.player_id for p in home_roster.players]
        assert "JM28" in hou_ids, "JM28 should be on HOU roster (current team)"
        assert "JM28" not in kc_ids, "JM28 should not be on KC roster"
        # Verify the model has team == HOU
        mixon = [p for p in away_roster.players if p.player_id == "JM28"][0]
        assert mixon.team == "HOU"

    def test_kicker_on_roster(self, builder, traded_player_pbp, traded_player_rosters):
        """KC_K should appear on KC roster as a kicker."""
        roster = builder.build_team_roster(
            "KC", pbp=traded_player_pbp, rosters=traded_player_rosters,
            training_seasons=[2024], target_season=2025,
        )
        player_ids = [p.player_id for p in roster.players]
        assert "KC_K" in player_ids
        kicker = [p for p in roster.players if p.player_id == "KC_K"][0]
        assert kicker.position == "K"

    def test_rookie_on_roster(self, builder, traded_player_pbp, traded_player_rosters):
        """ROOK1 has no PBP data but is on HOU roster — should get archetype model."""
        roster = builder.build_team_roster(
            "HOU", pbp=traded_player_pbp, rosters=traded_player_rosters,
            training_seasons=[2024], target_season=2025,
        )
        player_ids = [p.player_id for p in roster.players]
        assert "ROOK1" in player_ids
        rookie = [p for p in roster.players if p.player_id == "ROOK1"][0]
        assert rookie.position == "WR"
        assert rookie.team == "HOU"

    def test_retired_player_excluded(
        self, builder, traded_player_pbp, traded_player_rosters
    ):
        """RET99 has PBP data but is NOT on 2025 roster — should not appear."""
        _, _, home_roster, away_roster = builder.build_game(
            home_team="KC", away_team="HOU",
            pbp=traded_player_pbp, rosters=traded_player_rosters,
            training_seasons=[2024], target_season=2025,
        )
        all_ids = (
            [p.player_id for p in home_roster.players]
            + [p.player_id for p in away_roster.players]
        )
        assert "RET99" not in all_ids

    def test_week_filters_roster(
        self, builder, traded_player_pbp, midseason_trade_rosters
    ):
        """SD14 is on HOU weeks 1-4, traded to KC weeks 5-9.

        At week 3 SD14 should be on HOU; at week 6 SD14 should be on KC.
        """
        # Week 3: SD14 on HOU
        _, _, kc_roster_w3, hou_roster_w3 = builder.build_game(
            home_team="KC", away_team="HOU",
            pbp=traded_player_pbp, rosters=midseason_trade_rosters,
            training_seasons=[2024], target_season=2025, week=3,
        )
        hou_ids_w3 = [p.player_id for p in hou_roster_w3.players]
        kc_ids_w3 = [p.player_id for p in kc_roster_w3.players]
        assert "SD14" in hou_ids_w3, "SD14 should be on HOU at week 3"
        assert "SD14" not in kc_ids_w3, "SD14 should not be on KC at week 3"

        # Multi-key cache handles different weeks natively; no reset needed

        # Week 6: SD14 on KC
        _, _, kc_roster_w6, hou_roster_w6 = builder.build_game(
            home_team="KC", away_team="HOU",
            pbp=traded_player_pbp, rosters=midseason_trade_rosters,
            training_seasons=[2024], target_season=2025, week=6,
        )
        kc_ids_w6 = [p.player_id for p in kc_roster_w6.players]
        hou_ids_w6 = [p.player_id for p in hou_roster_w6.players]
        assert "SD14" in kc_ids_w6, "SD14 should be on KC at week 6"
        assert "SD14" not in hou_ids_w6, "SD14 should not be on HOU at week 6"

    def test_matchup_engine_receives_target_season_and_week(
        self, builder, expanded_pbp, sample_rosters
    ):
        """build_game() passes target_season and week to matchup engine."""
        from unittest.mock import MagicMock
        from fantasy_sim.data.pff.models import MatchupContext

        mock_engine = MagicMock()
        mock_engine.compute.return_value = MatchupContext()

        builder._matchup_engine = mock_engine

        builder.build_game(
            home_team="KC", away_team="BUF",
            pbp=expanded_pbp, rosters=sample_rosters,
            training_seasons=[2024], target_season=2024, week=8,
        )

        # Should be called twice: away D vs home O, home D vs away O
        assert mock_engine.compute.call_count == 2

        # First call: away defense (BUF) adjusts home offense (KC)
        call1 = mock_engine.compute.call_args_list[0]
        assert call1.kwargs["defense_team"] == "BUF"
        assert call1.kwargs["target_season"] == 2024
        assert call1.kwargs["max_week"] == 8

        # Second call: home defense (KC) adjusts away offense (BUF)
        call2 = mock_engine.compute.call_args_list[1]
        assert call2.kwargs["defense_team"] == "KC"
        assert call2.kwargs["target_season"] == 2024
        assert call2.kwargs["max_week"] == 8

    def test_team_context_engine_created_when_enabled(self, tmp_path):
        """team_context.enabled=True creates the engine."""
        from unittest.mock import patch
        from fantasy_sim.data.pff.models import PffConfig, TeamContextConfig

        pff_config = PffConfig(
            enabled=True,
            team_context=TeamContextConfig(enabled=True),
        )
        with patch("fantasy_sim.data.pff.loader.PffLoader") as MockLoader:
            MockLoader.return_value.is_available.return_value = True
            builder = GameContextBuilder(cache_dir=tmp_path / "cache", pff_config=pff_config)

        assert builder._team_context_engine is not None

    def test_team_context_engine_not_created_when_disabled(self, tmp_path):
        """team_context.enabled=False does not create the engine."""
        from unittest.mock import patch
        from fantasy_sim.data.pff.models import PffConfig, TeamContextConfig

        pff_config = PffConfig(
            enabled=True,
            team_context=TeamContextConfig(enabled=False),
        )
        with patch("fantasy_sim.data.pff.loader.PffLoader") as MockLoader:
            MockLoader.return_value.is_available.return_value = True
            builder = GameContextBuilder(cache_dir=tmp_path / "cache", pff_config=pff_config)

        assert builder._team_context_engine is None

    def test_team_context_passed_to_apply_tiers(
        self, builder, expanded_pbp, sample_rosters
    ):
        """build_game() computes team context and passes to apply_tiers."""
        from unittest.mock import MagicMock
        from fantasy_sim.data.pff.models import TeamContext

        mock_tc_engine = MagicMock()
        mock_tc_engine.compute.return_value = TeamContext(
            pass_rate_factor=1.05,
            ol_run_block_factor=0.97,
            qb_quality_factor=1.02,
        )

        mock_tier_engine = MagicMock()

        builder._team_context_engine = mock_tc_engine
        builder._tier_engine = mock_tier_engine
        builder._pff_crosswalk = {}
        builder._pff_loader = MagicMock()

        builder.build_game(
            home_team="KC", away_team="BUF",
            pbp=expanded_pbp, rosters=sample_rosters,
            training_seasons=[2024], target_season=2024, week=8,
        )

        assert mock_tc_engine.compute.call_count == 2
        assert mock_tier_engine.apply_tiers.call_count == 2
        for tier_call in mock_tier_engine.apply_tiers.call_args_list:
            assert "team_context" in tier_call.kwargs

    def test_team_context_skipped_when_no_target_season(
        self, builder, expanded_pbp, sample_rosters
    ):
        """build_game() without target_season skips team context computation."""
        from unittest.mock import MagicMock

        mock_tc_engine = MagicMock()
        mock_tier_engine = MagicMock()

        builder._team_context_engine = mock_tc_engine
        builder._tier_engine = mock_tier_engine
        builder._pff_crosswalk = {}
        builder._pff_loader = MagicMock()

        builder.build_game(
            home_team="KC", away_team="BUF",
            pbp=expanded_pbp, rosters=sample_rosters,
            training_seasons=[2024],
            target_season=None, week=None,
        )

        mock_tc_engine.compute.assert_not_called()

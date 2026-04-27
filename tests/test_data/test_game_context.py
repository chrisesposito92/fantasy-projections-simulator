import json

import pytest
import polars as pl
from fantasy_sim.data.game_context import GameContextBuilder
from fantasy_sim.data.goal_line_concentration import GoalLineConcentrationConfig
from fantasy_sim.data.game_script import GameScriptConfig
from fantasy_sim.data.play_call_model import (
    PLAY_CALL_MODEL_SCHEMA_VERSION,
    PLAY_CALL_MODEL_TYPE,
    PlayCallModelConfig,
)
from fantasy_sim.data.qb_rushing import (
    QB_DESIGNED_RUN_MODEL_TYPE,
    QB_DESIGNED_RUN_SCHEMA_VERSION,
    QB_SCRAMBLE_MODEL_TYPE,
    QB_SCRAMBLE_SCHEMA_VERSION,
    QbDesignedRunModelConfig,
    QbRushingConfig,
    QbScrambleModelConfig,
)
from fantasy_sim.data.vegas.models import VegasContext
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

    def test_play_call_model_created_when_enabled(self, tmp_path):
        builder = GameContextBuilder(
            cache_dir=tmp_path / "cache",
            play_call_model_config=PlayCallModelConfig(
                enabled=True,
                artifacts_dir=str(tmp_path),
            ),
        )

        assert builder._play_call_model is not None

    def test_play_call_context_attached_when_artifact_exists(
        self, tmp_path, expanded_pbp, sample_rosters
    ):
        artifact = {
            "schema_version": PLAY_CALL_MODEL_SCHEMA_VERSION,
            "model_type": PLAY_CALL_MODEL_TYPE,
            "target_season": 2024,
            "source_seasons": [2023],
            "feature_names": ["intercept"],
            "coefficients": {"intercept": 0.0},
        }
        (tmp_path / "play_call_model_2024.json").write_text(
            json.dumps(artifact),
            encoding="utf-8",
        )
        builder = GameContextBuilder(
            cache_dir=tmp_path / "cache",
            play_call_model_config=PlayCallModelConfig(
                enabled=True,
                artifacts_dir=str(tmp_path),
            ),
        )

        home_dists, away_dists, _, _ = builder.build_game(
            home_team="KC",
            away_team="BUF",
            pbp=expanded_pbp,
            rosters=sample_rosters,
            training_seasons=[2024],
            target_season=2024,
            week=1,
        )

        assert home_dists.play_call_context is not None
        assert away_dists.play_call_context is not None

    def test_qb_scramble_model_created_when_enabled(self, tmp_path):
        builder = GameContextBuilder(
            cache_dir=tmp_path / "cache",
            qb_rushing_config=QbRushingConfig(
                scramble=QbScrambleModelConfig(
                    enabled=True,
                    artifacts_dir=str(tmp_path),
                ),
            ),
        )

        assert builder._qb_scramble_model is not None

    def test_qb_scramble_context_attached_when_artifact_exists(
        self, tmp_path, expanded_pbp, sample_rosters
    ):
        artifact = {
            "schema_version": QB_SCRAMBLE_SCHEMA_VERSION,
            "model_type": QB_SCRAMBLE_MODEL_TYPE,
            "target_season": 2024,
            "source_seasons": [2023],
            "feature_names": ["intercept"],
            "coefficients": {"intercept": 0.0},
            "priors": {
                "qb": {},
                "team": {},
                "opponent_allowed": {},
                "league": 0.06,
            },
            "diagnostics": {"num_examples": 500, "scramble_rate": 0.06},
        }
        (tmp_path / "qb_scramble_model_2024.json").write_text(
            json.dumps(artifact),
            encoding="utf-8",
        )
        builder = GameContextBuilder(
            cache_dir=tmp_path / "cache",
            qb_rushing_config=QbRushingConfig(
                scramble=QbScrambleModelConfig(
                    enabled=True,
                    artifacts_dir=str(tmp_path),
                ),
            ),
        )
        builder.loader.load_schedules = lambda seasons: pl.DataFrame(
            [
                {
                    "season": 2024,
                    "week": 1,
                    "home_team": "KC",
                    "away_team": "BUF",
                    "spread_line": -3.0,
                    "total_line": 48.0,
                }
            ]
        )

        home_dists, away_dists, _, _ = builder.build_game(
            home_team="KC",
            away_team="BUF",
            pbp=expanded_pbp,
            rosters=sample_rosters,
            training_seasons=[2024],
            target_season=2024,
            week=1,
        )

        assert home_dists.qb_scramble_context is not None
        assert away_dists.qb_scramble_context is not None
        assert home_dists.qb_scramble_context.team == "KC"
        assert home_dists.qb_scramble_context.opponent == "BUF"
        assert home_dists.qb_scramble_context.home_team == "KC"
        assert home_dists.qb_scramble_context.away_team == "BUF"
        assert home_dists.qb_scramble_context.is_home is True
        assert home_dists.qb_scramble_context.spread_line == -3.0
        assert home_dists.qb_scramble_context.total_line == 48.0
        assert home_dists.qb_scramble_context.implied_team_total == 22.5
        assert away_dists.qb_scramble_context.team == "BUF"
        assert away_dists.qb_scramble_context.opponent == "KC"
        assert away_dists.qb_scramble_context.home_team == "KC"
        assert away_dists.qb_scramble_context.away_team == "BUF"
        assert away_dists.qb_scramble_context.is_home is False
        assert away_dists.qb_scramble_context.spread_line == 3.0
        assert away_dists.qb_scramble_context.total_line == 48.0
        assert away_dists.qb_scramble_context.implied_team_total == 25.5

    def test_qb_designed_run_model_created_when_enabled(self, tmp_path):
        builder = GameContextBuilder(
            cache_dir=tmp_path / "cache",
            qb_rushing_config=QbRushingConfig(
                designed_runs=QbDesignedRunModelConfig(
                    enabled=True,
                    artifacts_dir=str(tmp_path),
                ),
            ),
        )

        assert builder._qb_designed_run_model is not None

    def test_qb_designed_run_context_attached_when_artifact_exists(
        self, tmp_path, expanded_pbp, sample_rosters
    ):
        artifact = {
            "schema_version": QB_DESIGNED_RUN_SCHEMA_VERSION,
            "model_type": QB_DESIGNED_RUN_MODEL_TYPE,
            "target_season": 2024,
            "source_seasons": [2023],
            "feature_names": ["intercept"],
            "coefficients": {"intercept": 0.0},
            "priors": {
                "qb": {},
                "team": {},
                "opponent_allowed": {},
                "league": 0.06,
                "mobility_tiers": {},
            },
            "tail_buckets": {"global": [5, 8, 12]},
            "diagnostics": {"num_examples": 500, "designed_qb_run_rate": 0.06},
        }
        (tmp_path / "qb_designed_run_model_2024.json").write_text(
            json.dumps(artifact),
            encoding="utf-8",
        )
        builder = GameContextBuilder(
            cache_dir=tmp_path / "cache",
            qb_rushing_config=QbRushingConfig(
                designed_runs=QbDesignedRunModelConfig(
                    enabled=True,
                    artifacts_dir=str(tmp_path),
                ),
            ),
        )
        builder.loader.load_schedules = lambda seasons: pl.DataFrame(
            [
                {
                    "season": 2024,
                    "week": 1,
                    "home_team": "KC",
                    "away_team": "BUF",
                    "spread_line": -3.0,
                    "total_line": 48.0,
                }
            ]
        )

        home_dists, away_dists, _, _ = builder.build_game(
            home_team="KC",
            away_team="BUF",
            pbp=expanded_pbp,
            rosters=sample_rosters,
            training_seasons=[2024],
            target_season=2024,
            week=1,
        )

        assert home_dists.qb_designed_run_context is not None
        assert away_dists.qb_designed_run_context is not None
        assert home_dists.qb_designed_run_context.team == "KC"
        assert home_dists.qb_designed_run_context.opponent == "BUF"
        assert home_dists.qb_designed_run_context.spread_line == -3.0
        assert home_dists.qb_designed_run_context.total_line == 48.0
        assert home_dists.qb_designed_run_context.implied_team_total == 22.5
        assert away_dists.qb_designed_run_context.team == "BUF"
        assert away_dists.qb_designed_run_context.opponent == "KC"
        assert away_dists.qb_designed_run_context.spread_line == 3.0
        assert away_dists.qb_designed_run_context.total_line == 48.0
        assert away_dists.qb_designed_run_context.implied_team_total == 25.5

    def test_build_game_reuses_market_features_for_context_models(
        self, tmp_path, expanded_pbp, sample_rosters
    ):
        (tmp_path / "play_call_model_2024.json").write_text(
            json.dumps(
                {
                    "schema_version": PLAY_CALL_MODEL_SCHEMA_VERSION,
                    "model_type": PLAY_CALL_MODEL_TYPE,
                    "target_season": 2024,
                    "source_seasons": [2023],
                    "feature_names": ["intercept"],
                    "coefficients": {"intercept": 0.0},
                }
            ),
            encoding="utf-8",
        )
        (tmp_path / "qb_scramble_model_2024.json").write_text(
            json.dumps(
                {
                    "schema_version": QB_SCRAMBLE_SCHEMA_VERSION,
                    "model_type": QB_SCRAMBLE_MODEL_TYPE,
                    "target_season": 2024,
                    "source_seasons": [2023],
                    "feature_names": ["intercept"],
                    "coefficients": {"intercept": 0.0},
                    "priors": {"league": 0.06},
                    "diagnostics": {"num_examples": 500, "scramble_rate": 0.06},
                }
            ),
            encoding="utf-8",
        )
        (tmp_path / "qb_designed_run_model_2024.json").write_text(
            json.dumps(
                {
                    "schema_version": QB_DESIGNED_RUN_SCHEMA_VERSION,
                    "model_type": QB_DESIGNED_RUN_MODEL_TYPE,
                    "target_season": 2024,
                    "source_seasons": [2023],
                    "feature_names": ["intercept"],
                    "coefficients": {"intercept": 0.0},
                    "priors": {"league": 0.06, "mobility_tiers": {}},
                    "tail_buckets": {"global": [5, 8, 12]},
                    "diagnostics": {"num_examples": 500, "designed_qb_run_rate": 0.06},
                }
            ),
            encoding="utf-8",
        )
        builder = GameContextBuilder(
            cache_dir=tmp_path / "cache",
            play_call_model_config=PlayCallModelConfig(
                enabled=True,
                artifacts_dir=str(tmp_path),
            ),
            qb_rushing_config=QbRushingConfig(
                scramble=QbScrambleModelConfig(
                    enabled=True,
                    artifacts_dir=str(tmp_path),
                ),
                designed_runs=QbDesignedRunModelConfig(
                    enabled=True,
                    artifacts_dir=str(tmp_path),
                ),
            ),
        )
        builder.loader.load_schedules = lambda seasons: pl.DataFrame(
            [
                {
                    "season": 2024,
                    "week": 1,
                    "home_team": "KC",
                    "away_team": "BUF",
                    "spread_line": -3.0,
                    "total_line": 48.0,
                }
            ]
        )
        original_market_features = builder._play_call_market_features
        calls = {"count": 0}

        def counting_market_features(home_team, away_team, target_season, week):
            calls["count"] += 1
            return original_market_features(home_team, away_team, target_season, week)

        builder._play_call_market_features = counting_market_features

        builder.build_game(
            home_team="KC",
            away_team="BUF",
            pbp=expanded_pbp,
            rosters=sample_rosters,
            training_seasons=[2024],
            target_season=2024,
            week=1,
        )

        assert calls["count"] == 1

    def test_vegas_pass_rate_is_not_skipped_when_artifact_missing(
        self, tmp_path, expanded_pbp, sample_rosters
    ):
        builder = GameContextBuilder(
            cache_dir=tmp_path / "cache",
            play_call_model_config=PlayCallModelConfig(
                enabled=True,
                artifacts_dir=str(tmp_path),
            ),
        )
        dists = builder.build_team_distributions(
            "KC",
            pbp=expanded_pbp,
            rosters=sample_rosters,
            training_seasons=[2024],
            target_season=2024,
            week=1,
        )
        before = dists.play_calling.default["pass"]

        builder._apply_vegas(
            dists,
            VegasContext(team="KC", pass_rate_factor=1.05),
            apply_pass_rate=True,
        )

        assert dists.play_calling.default["pass"] > before

    def test_play_call_market_features_use_team_perspective_spread(self, builder):
        builder.loader.load_schedules = lambda seasons: pl.DataFrame(
            [
                {
                    "season": 2024,
                    "week": 1,
                    "home_team": "KC",
                    "away_team": "BUF",
                    "spread_line": -3.0,
                    "total_line": 48.0,
                }
            ]
        )

        home_market, away_market = builder._play_call_market_features(
            "KC", "BUF", 2024, 1
        )

        assert home_market == {
            "spread_line": -3.0,
            "total_line": 48.0,
            "implied_team_total": 22.5,
        }
        assert away_market == {
            "spread_line": 3.0,
            "total_line": 48.0,
            "implied_team_total": 25.5,
        }

    @pytest.mark.parametrize(
        "spread_line,total_line",
        [(None, 48.0), (-3.0, None)],
    )
    def test_play_call_market_features_fail_closed_for_incomplete_market_data(
        self, builder, spread_line, total_line
    ):
        builder.loader.load_schedules = lambda seasons: pl.DataFrame(
            [
                {
                    "season": 2024,
                    "week": 1,
                    "home_team": "KC",
                    "away_team": "BUF",
                    "spread_line": spread_line,
                    "total_line": total_line,
                }
            ]
        )

        home_market, away_market = builder._play_call_market_features(
            "KC", "BUF", 2024, 1
        )

        assert home_market == {
            "spread_line": None,
            "total_line": None,
            "implied_team_total": None,
        }
        assert away_market == {
            "spread_line": None,
            "total_line": None,
            "implied_team_total": None,
        }

    @pytest.mark.parametrize(
        "spread_line,total_line",
        [(float("nan"), 48.0), (-3.0, float("inf"))],
    )
    def test_play_call_market_features_fail_closed_for_non_finite_market_data(
        self, builder, spread_line, total_line
    ):
        builder.loader.load_schedules = lambda seasons: pl.DataFrame(
            [
                {
                    "season": 2024,
                    "week": 1,
                    "home_team": "KC",
                    "away_team": "BUF",
                    "spread_line": spread_line,
                    "total_line": total_line,
                }
            ]
        )

        home_market, away_market = builder._play_call_market_features(
            "KC", "BUF", 2024, 1
        )

        assert home_market == {
            "spread_line": None,
            "total_line": None,
            "implied_team_total": None,
        }
        assert away_market == {
            "spread_line": None,
            "total_line": None,
            "implied_team_total": None,
        }

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


# === KS-03: per-player dist-mean anchor ===
#
# These tests target the three call sites patched in Plan 01-03 (KS-03):
#   1. `GameContextBuilder._apply_matchup` receiving branch (D-16)
#   2. `GameContextBuilder._apply_matchup` rushing branch (D-16b)
#   3. `GameContextBuilder._apply_coverage` (D-16)
#
# Production default for `phase1_ks_flags.ks03_dynamic_yard_anchor.enabled`
# is `false`, so the tests monkeypatch the module-level
# `_KS03_DYNAMIC_YARD_ANCHOR` constant to True to exercise the new code path
# directly (mirrors the KS-01 / KS-04 test conventions in
# `tests/test_engine/test_play_resolver.py`).
class TestKs03DistMeanAnchor:
    @staticmethod
    def _make_player(
        player_id, position, *, target_share=0.0, carry_share=0.0,
        receiving_yards_dist=None, rushing_yards_dist=None,
    ):
        import numpy as np
        from fantasy_sim.models.player import (
            PlayerModel, PlayerUsage, PlayerOutcomes,
        )
        return PlayerModel(
            player_id=player_id,
            name=player_id,
            position=position,
            team="KC",
            usage=PlayerUsage(target_share=target_share, carry_share=carry_share),
            outcomes=PlayerOutcomes(
                receiving_yards_dist=(
                    np.asarray(receiving_yards_dist, dtype=float)
                    if receiving_yards_dist is not None
                    else None
                ),
                rushing_yards_dist=(
                    np.asarray(rushing_yards_dist, dtype=float)
                    if rushing_yards_dist is not None
                    else None
                ),
            ),
        )

    @staticmethod
    def _make_dists():
        """Sentinel `dists` object passed positionally to `_apply_matchup`.

        `_apply_matchup` only reads / writes `dists.turnover_rates.sack_rate`
        and `.int_rate`, and only when `combined_sack != 1.0` or
        `int_rate_factor != 1.0`. KS-03 tests use a MatchupContext with all
        non-target factors == 1.0, so the dists path is never reached.
        Passing `None` keeps the test focused on the receiver / rusher
        branches without a dependency on the heavy TeamDistributions
        constructor.
        """
        return None

    def test_ks03_apply_matchup_uses_dist_mean_for_pass_yards(self, monkeypatch):
        """WR (mean=10) shifts +1.0 and TE (mean=4) shifts +0.4 for a
        +10% `pass_yards_factor`. The distinct shifts prove the per-player
        anchor is in use (legacy hardcoded `*10.0` would shift both by +1.0).
        """
        import numpy as np
        from fantasy_sim.data import game_context as gc
        from fantasy_sim.data.pff.models import MatchupContext
        from fantasy_sim.models.player import TeamRoster

        monkeypatch.setattr(gc, "_KS03_DYNAMIC_YARD_ANCHOR", True)

        wr = self._make_player(
            "WR1", "WR",
            target_share=0.25,
            receiving_yards_dist=[5, 10, 15],  # mean = 10.0
        )
        te = self._make_player(
            "TE1", "TE",
            target_share=0.20,
            receiving_yards_dist=[2, 4, 6],  # mean = 4.0
        )
        roster = TeamRoster(team="KC", players=[wr, te])
        dists = self._make_dists()

        ctx = MatchupContext(pass_yards_factor=1.10)

        gc.GameContextBuilder._apply_matchup(dists, roster, ctx)

        # WR shift = (1.10 - 1.0) * 10.0 = +1.0
        np.testing.assert_allclose(
            wr.outcomes.receiving_yards_dist,
            np.array([6.0, 11.0, 16.0]),
        )
        # TE shift = (1.10 - 1.0) * 4.0 = +0.4
        np.testing.assert_allclose(
            te.outcomes.receiving_yards_dist,
            np.array([2.4, 4.4, 6.4]),
        )

    def test_ks03_apply_matchup_uses_dist_mean_for_rush_yards(self, monkeypatch):
        """RB (mean=5) shifts +0.5 for `combined_rush=1.10`."""
        import numpy as np
        from fantasy_sim.data import game_context as gc
        from fantasy_sim.data.pff.models import MatchupContext
        from fantasy_sim.models.player import TeamRoster

        monkeypatch.setattr(gc, "_KS03_DYNAMIC_YARD_ANCHOR", True)

        rb = self._make_player(
            "RB1", "RB",
            carry_share=0.6,
            rushing_yards_dist=[1, 5, 9],  # mean = 5.0
        )
        roster = TeamRoster(team="KC", players=[rb])
        dists = self._make_dists()

        # `combined_rush = rush_yards_factor * ol_run_block_factor`
        ctx = MatchupContext(rush_yards_factor=1.10, ol_run_block_factor=1.0)

        gc.GameContextBuilder._apply_matchup(dists, roster, ctx)

        # RB shift = (1.10 - 1.0) * 5.0 = +0.5
        np.testing.assert_allclose(
            rb.outcomes.rushing_yards_dist,
            np.array([1.5, 5.5, 9.5]),
        )

    def test_ks03_apply_coverage_uses_dist_mean_for_ypr(self, monkeypatch):
        """WR (mean=10) shifts +0.5 for a +5% `ypr_modifier`."""
        import numpy as np
        from fantasy_sim.data import game_context as gc
        from fantasy_sim.data.pff.models import CoverageModifiers
        from fantasy_sim.models.player import TeamRoster

        monkeypatch.setattr(gc, "_KS03_DYNAMIC_YARD_ANCHOR", True)

        wr = self._make_player(
            "WR1", "WR",
            target_share=0.25,
            receiving_yards_dist=[5, 10, 15],  # mean = 10.0
        )
        roster = TeamRoster(team="KC", players=[wr])
        modifiers = {
            "WR1": CoverageModifiers(
                catch_rate_modifier=1.0,
                ypr_modifier=1.05,
            )
        }

        gc.GameContextBuilder._apply_coverage(roster, modifiers)

        # WR shift = (1.05 - 1.0) * 10.0 = +0.5
        np.testing.assert_allclose(
            wr.outcomes.receiving_yards_dist,
            np.array([5.5, 10.5, 15.5]),
        )

    def test_ks03_apply_matchup_skips_empty_dist(self, monkeypatch):
        """Players with `receiving_yards_dist is None` or `len(...)==0`
        must NOT trigger the anchor computation (avoids `np.mean` on an
        empty array and preserves the empty-state). Same guard for the
        rushing branch.
        """
        import numpy as np
        from fantasy_sim.data import game_context as gc
        from fantasy_sim.data.pff.models import MatchupContext
        from fantasy_sim.models.player import TeamRoster

        monkeypatch.setattr(gc, "_KS03_DYNAMIC_YARD_ANCHOR", True)

        none_recv = self._make_player(
            "WR_NONE", "WR",
            target_share=0.25,
            receiving_yards_dist=None,
        )
        empty_recv = self._make_player(
            "WR_EMPTY", "WR",
            target_share=0.25,
            receiving_yards_dist=[],
        )
        none_rush = self._make_player(
            "RB_NONE", "RB",
            carry_share=0.5,
            rushing_yards_dist=None,
        )
        empty_rush = self._make_player(
            "RB_EMPTY", "RB",
            carry_share=0.5,
            rushing_yards_dist=[],
        )
        roster = TeamRoster(
            team="KC",
            players=[none_recv, empty_recv, none_rush, empty_rush],
        )
        dists = self._make_dists()

        ctx = MatchupContext(
            pass_yards_factor=1.10,
            rush_yards_factor=1.10,
            ol_run_block_factor=1.0,
        )

        # Must not raise on `np.mean` of empty / None.
        gc.GameContextBuilder._apply_matchup(dists, roster, ctx)

        assert none_recv.outcomes.receiving_yards_dist is None
        assert len(empty_recv.outcomes.receiving_yards_dist) == 0
        assert none_rush.outcomes.rushing_yards_dist is None
        assert len(empty_rush.outcomes.rushing_yards_dist) == 0

    def test_ks03_apply_coverage_skips_empty_dist(self, monkeypatch):
        """Coverage path: WR with `receiving_yards_dist is None` or
        `len(...)==0` must NOT trigger the anchor computation.
        """
        from fantasy_sim.data import game_context as gc
        from fantasy_sim.data.pff.models import CoverageModifiers
        from fantasy_sim.models.player import TeamRoster

        monkeypatch.setattr(gc, "_KS03_DYNAMIC_YARD_ANCHOR", True)

        none_wr = self._make_player(
            "WR_NONE", "WR",
            target_share=0.25,
            receiving_yards_dist=None,
        )
        empty_wr = self._make_player(
            "WR_EMPTY", "WR",
            target_share=0.25,
            receiving_yards_dist=[],
        )
        roster = TeamRoster(team="KC", players=[none_wr, empty_wr])
        modifiers = {
            "WR_NONE": CoverageModifiers(catch_rate_modifier=1.0, ypr_modifier=1.05),
            "WR_EMPTY": CoverageModifiers(catch_rate_modifier=1.0, ypr_modifier=1.05),
        }

        gc.GameContextBuilder._apply_coverage(roster, modifiers)

        assert none_wr.outcomes.receiving_yards_dist is None
        assert len(empty_wr.outcomes.receiving_yards_dist) == 0


# === KS-12: integration with _normalize_roster_shares ===

class TestKS12NormalizeRosterSharesIntegration:
    """Integration tests for KS-12 share-normalization residual.

    These tests exercise _normalize_roster_shares with the flag enabled and
    a multi-inactive roster (players with snap_share=0 simulating post-availability
    state), verifying that the factor < 1.0 path is used and share sums match
    the expected active fraction.
    """

    def _make_usage(self, snap_share=1.0, carry_share=0.0, target_share=0.0,
                    red_zone_carry_share=0.0, red_zone_target_share=0.0,
                    outer_rz_carry_share=0.0, outer_rz_target_share=0.0,
                    goal_line_carry_share=0.0, goal_line_target_share=0.0):
        from fantasy_sim.models.player import PlayerUsage
        u = PlayerUsage()
        u.snap_share = snap_share
        u.carry_share = carry_share
        u.target_share = target_share
        u.red_zone_carry_share = red_zone_carry_share
        u.red_zone_target_share = red_zone_target_share
        u.outer_rz_carry_share = outer_rz_carry_share
        u.outer_rz_target_share = outer_rz_target_share
        u.goal_line_carry_share = goal_line_carry_share
        u.goal_line_target_share = goal_line_target_share
        return u

    def _make_player(self, player_id, position, **usage_kwargs):
        from fantasy_sim.models.player import PlayerModel, PlayerOutcomes
        import numpy as np
        usage = self._make_usage(**usage_kwargs)
        outcomes = PlayerOutcomes()
        return PlayerModel(
            player_id=player_id,
            name=player_id,
            position=position,
            team="KC",
            usage=usage,
            outcomes=outcomes,
        )

    def test_ks12_select_receiver_handles_residual_factor(self, monkeypatch):
        """When KS-12 flag ON and 2 receivers inactive (snap_share=0),
        _normalize_roster_shares reduces target_share sum to active_factor < 1.0.

        Verifies availability-engine composition: inactive players (snap_share=0)
        are not counted as active, so the active_factor = 20/22 ≈ 0.909, and
        the sum of target_shares for active receivers ≈ active_factor ± 0.02.
        """
        from fantasy_sim.data import player_builder as pb_mod
        from fantasy_sim.data.player_builder import _normalize_roster_shares, _expected_active_share_factor
        from fantasy_sim.models.player import TeamRoster

        # Force KS-12 flag ON
        monkeypatch.setattr(pb_mod, "_KS12_SHARE_NORM_RESIDUAL", True)

        # 20 active WRs + 2 inactive (snap_share=0, target_share=0)
        # Simulate post-availability state: inactive players have zeroed shares
        active_receivers = [
            self._make_player(f"WR_{i}", "WR", snap_share=1.0, target_share=0.1)
            for i in range(20)
        ]
        inactive_receivers = [
            self._make_player(f"WR_INACTIVE_{j}", "WR", snap_share=0.0, target_share=0.0)
            for j in range(2)
        ]
        roster = TeamRoster(team="KC", players=active_receivers + inactive_receivers)

        # Compute expected factor before normalizing
        expected_factor = _expected_active_share_factor(roster, typical_roster_size=22)
        assert expected_factor < 1.0, "Expected factor < 1.0 for multi-inactive roster"

        _normalize_roster_shares(roster)

        active_target_sum = sum(p.usage.target_share for p in active_receivers)
        # After normalization with factor, sum should ≈ active_factor ± 0.02
        assert abs(active_target_sum - expected_factor) < 0.02, (
            f"target_share sum {active_target_sum:.4f} should ≈ "
            f"active_factor {expected_factor:.4f} ± 0.02"
        )

    def test_ks12_select_rusher_handles_residual_factor(self, monkeypatch):
        """When KS-12 flag ON and 2 RBs inactive (snap_share=0),
        _normalize_roster_shares reduces carry_share sum to active_factor < 1.0.

        Mirrors the receiver test for rushers: 20 active RBs + 2 inactive.
        Factor = 20/22 ≈ 0.909; sum of carry_shares for active RBs ≈ factor ± 0.02.
        """
        from fantasy_sim.data import player_builder as pb_mod
        from fantasy_sim.data.player_builder import _normalize_roster_shares, _expected_active_share_factor
        from fantasy_sim.models.player import TeamRoster

        # Force KS-12 flag ON
        monkeypatch.setattr(pb_mod, "_KS12_SHARE_NORM_RESIDUAL", True)

        # 20 active RBs + 2 inactive (snap_share=0, carry_share=0)
        active_rushers = [
            self._make_player(f"RB_{i}", "RB", snap_share=1.0, carry_share=0.1)
            for i in range(20)
        ]
        inactive_rushers = [
            self._make_player(f"RB_INACTIVE_{j}", "RB", snap_share=0.0, carry_share=0.0)
            for j in range(2)
        ]
        roster = TeamRoster(team="KC", players=active_rushers + inactive_rushers)

        expected_factor = _expected_active_share_factor(roster, typical_roster_size=22)
        assert expected_factor < 1.0

        _normalize_roster_shares(roster)

        active_carry_sum = sum(p.usage.carry_share for p in active_rushers)
        assert abs(active_carry_sum - expected_factor) < 0.02, (
            f"carry_share sum {active_carry_sum:.4f} should ≈ "
            f"active_factor {expected_factor:.4f} ± 0.02"
        )

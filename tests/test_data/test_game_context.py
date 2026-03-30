import pytest
from fantasy_sim.data.game_context import GameContextBuilder
from fantasy_sim.engine.types import TeamDistributions
from fantasy_sim.models.player import TeamRoster


class TestGameContextBuilder:
    @pytest.fixture
    def builder(self, tmp_path):
        return GameContextBuilder(cache_dir=tmp_path / "cache")

    def test_build_team_distributions(self, builder, expanded_pbp, sample_rosters):
        dists = builder.build_team_distributions(
            "KC", pbp=expanded_pbp, rosters=sample_rosters, seasons=[2024]
        )
        assert isinstance(dists, TeamDistributions)
        assert dists.play_calling.team == "KC"
        assert dists.turnover_rates.team == "KC"

    def test_build_team_roster(self, builder, expanded_pbp, sample_rosters):
        roster = builder.build_team_roster(
            "KC", pbp=expanded_pbp, rosters=sample_rosters, seasons=[2024]
        )
        assert isinstance(roster, TeamRoster)
        assert roster.team == "KC"
        assert len(roster.players) > 0

    def test_build_game(self, builder, expanded_pbp, sample_rosters):
        home_dists, away_dists, home_roster, away_roster = builder.build_game(
            home_team="KC", away_team="BUF",
            pbp=expanded_pbp, rosters=sample_rosters, seasons=[2024],
        )
        assert home_dists.play_calling.team == "KC"
        assert away_dists.play_calling.team == "BUF"
        assert home_roster.team == "KC"
        assert away_roster.team == "BUF"

    def test_missing_team_gets_league_defaults(self, builder, expanded_pbp, sample_rosters):
        """A team not in PBP data should get league-average distributions."""
        dists = builder.build_team_distributions(
            "SEA", pbp=expanded_pbp, rosters=sample_rosters, seasons=[2024]
        )
        assert isinstance(dists, TeamDistributions)
        # Should use league defaults for play calling
        probs = dists.play_calling.default
        assert 0.4 <= probs["pass"] <= 0.7

    def test_caches_pipeline_output(self, builder, expanded_pbp, sample_rosters):
        """Second call with same data should reuse cached pipeline output."""
        builder.build_team_distributions("KC", pbp=expanded_pbp, rosters=sample_rosters, seasons=[2024])
        builder.build_team_distributions("BUF", pbp=expanded_pbp, rosters=sample_rosters, seasons=[2024])
        # Pipeline build should only have been called once (cached)
        assert builder._pipeline_cache is not None

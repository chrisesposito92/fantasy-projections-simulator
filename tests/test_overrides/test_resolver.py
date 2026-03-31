import pytest
from fantasy_sim.overrides.resolver import PlayerResolver
from fantasy_sim.models.player import (
    PlayerModel, PlayerUsage, PlayerOutcomes, TeamRoster,
)


def make_roster() -> TeamRoster:
    return TeamRoster(team="KC", players=[
        PlayerModel("PM15", "Patrick Mahomes", "QB", "KC", PlayerUsage(), PlayerOutcomes()),
        PlayerModel("TK87", "Travis Kelce", "TE", "KC", PlayerUsage(), PlayerOutcomes()),
        PlayerModel("RE11", "Rashee Rice", "WR", "KC", PlayerUsage(), PlayerOutcomes()),
        PlayerModel("IP01", "Isiah Pacheco", "RB", "KC", PlayerUsage(), PlayerOutcomes()),
    ])


@pytest.fixture
def resolver():
    rosters = [make_roster()]
    return PlayerResolver(rosters)


class TestPlayerResolver:
    def test_exact_id_match(self, resolver):
        pid = resolver.resolve("PM15")
        assert pid == "PM15"

    def test_exact_name_match(self, resolver):
        pid = resolver.resolve("Patrick Mahomes")
        assert pid == "PM15"

    def test_fuzzy_name_match(self, resolver):
        pid = resolver.resolve("mahomes")
        assert pid == "PM15"

    def test_underscore_name(self, resolver):
        pid = resolver.resolve("patrick_mahomes")
        assert pid == "PM15"

    def test_partial_name(self, resolver):
        pid = resolver.resolve("kelce")
        assert pid == "TK87"

    def test_no_match_raises(self, resolver):
        with pytest.raises(KeyError):
            resolver.resolve("totally_unknown_player")

    def test_case_insensitive(self, resolver):
        pid = resolver.resolve("TRAVIS KELCE")
        assert pid == "TK87"


class TestResolveExact:
    """Test resolve_exact (steps 1-3 only, no fuzzy matching)."""

    def test_exact_id(self, resolver):
        assert resolver.resolve_exact("PM15") == "PM15"

    def test_exact_name(self, resolver):
        assert resolver.resolve_exact("Patrick Mahomes") == "PM15"

    def test_underscore_conversion(self, resolver):
        assert resolver.resolve_exact("patrick_mahomes") == "PM15"

    def test_no_fuzzy_fallback(self, resolver):
        """resolve_exact should NOT fuzzy-match partial names."""
        with pytest.raises(KeyError):
            resolver.resolve_exact("mahomes")

    def test_no_partial_match(self, resolver):
        """resolve_exact should NOT match 'kelce' to 'Travis Kelce'."""
        with pytest.raises(KeyError):
            resolver.resolve_exact("kelce")


class TestCrossGameContamination:
    """Regression tests for the fuzzy matching cross-game contamination bug.

    When applying overrides per-game, 'bijan_robinson' should NOT fuzzy-match
    to 'Wan'Dale Robinson' or any other 'Robinson' on a different team.
    """

    def test_no_cross_team_fuzzy_match(self):
        """resolve_exact prevents 'bijan_robinson' matching 'Wan'Dale Robinson'."""
        nyg_roster = TeamRoster(team="NYG", players=[
            PlayerModel("WR99", "Wan'Dale Robinson", "WR", "NYG",
                        PlayerUsage(), PlayerOutcomes()),
        ])
        resolver = PlayerResolver([nyg_roster])

        # Full fuzzy resolve WOULD match (this is the bug)
        pid = resolver.resolve("bijan_robinson")
        assert pid == "WR99"  # Bug behavior: wrong player matched

        # Exact resolve correctly rejects
        with pytest.raises(KeyError):
            resolver.resolve_exact("bijan_robinson")

    def test_correct_team_exact_match(self):
        """resolve_exact correctly matches when player IS on roster."""
        atl_roster = TeamRoster(team="ATL", players=[
            PlayerModel("BR01", "Bijan Robinson", "RB", "ATL",
                        PlayerUsage(), PlayerOutcomes()),
        ])
        resolver = PlayerResolver([atl_roster])
        assert resolver.resolve_exact("bijan_robinson") == "BR01"

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

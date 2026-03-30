import pytest
from fantasy_sim.overrides.resolver import PlayerResolver, AmbiguousMatchError
from fantasy_sim.models.player import (
    PlayerModel, PlayerUsage, PlayerOutcomes, TeamRoster,
)


def make_roster_with_similar_names() -> list[TeamRoster]:
    """Rosters with multiple players whose names are close enough to be ambiguous."""
    kc = TeamRoster(team="KC", players=[
        PlayerModel("DS01", "DeVonta Smith", "WR", "KC", PlayerUsage(), PlayerOutcomes()),
        PlayerModel("DS02", "Donovan Smith", "OT", "KC", PlayerUsage(), PlayerOutcomes()),
        PlayerModel("PM15", "Patrick Mahomes", "QB", "KC", PlayerUsage(), PlayerOutcomes()),
    ])
    buf = TeamRoster(team="BUF", players=[
        PlayerModel("NS03", "Nico Smith", "WR", "BUF", PlayerUsage(), PlayerOutcomes()),
        PlayerModel("JA17", "Josh Allen", "QB", "BUF", PlayerUsage(), PlayerOutcomes()),
    ])
    return [kc, buf]


def make_roster_unique_names() -> list[TeamRoster]:
    """Rosters where each player has a clearly distinct name."""
    kc = TeamRoster(team="KC", players=[
        PlayerModel("PM15", "Patrick Mahomes", "QB", "KC", PlayerUsage(), PlayerOutcomes()),
        PlayerModel("TK87", "Travis Kelce", "TE", "KC", PlayerUsage(), PlayerOutcomes()),
    ])
    return [kc]


class TestAmbiguousMatchError:
    def test_error_exists(self):
        """AmbiguousMatchError is importable and instantiable."""
        err = AmbiguousMatchError("test")
        assert isinstance(err, AmbiguousMatchError)

    def test_is_key_error_subclass(self):
        """AmbiguousMatchError inherits from KeyError so existing except-KeyError handlers still work."""
        assert issubclass(AmbiguousMatchError, KeyError)


class TestAmbiguousMatchDetection:
    def test_smith_query_raises_ambiguous(self):
        """'Smith' matches DeVonta Smith, Donovan Smith, Nico Smith -- should raise."""
        resolver = PlayerResolver(make_roster_with_similar_names())
        with pytest.raises(AmbiguousMatchError):
            resolver.resolve("Smith")

    def test_unique_name_resolves_cleanly(self):
        """When names are distinct, fuzzy match returns the single best result."""
        resolver = PlayerResolver(make_roster_unique_names())
        assert resolver.resolve("mahomes") == "PM15"
        assert resolver.resolve("kelce") == "TK87"

    def test_exact_match_bypasses_ambiguity_check(self):
        """Exact player_id lookup never triggers ambiguity."""
        resolver = PlayerResolver(make_roster_with_similar_names())
        assert resolver.resolve("DS01") == "DS01"

    def test_exact_name_bypasses_ambiguity_check(self):
        """Exact case-insensitive name lookup never triggers ambiguity."""
        resolver = PlayerResolver(make_roster_with_similar_names())
        assert resolver.resolve("DeVonta Smith") == "DS01"

    def test_ambiguous_match_lists_options(self):
        """The error message should contain the names of multiple matching players."""
        resolver = PlayerResolver(make_roster_with_similar_names())
        with pytest.raises(AmbiguousMatchError, match=r"(?s).*Smith.*Smith.*"):
            resolver.resolve("Smith")

    def test_clear_partial_does_not_trigger_ambiguity(self):
        """'devonta smith' is specific enough to pick DS01 without ambiguity."""
        resolver = PlayerResolver(make_roster_with_similar_names())
        assert resolver.resolve("devonta smith") == "DS01"

    def test_ambiguity_threshold(self):
        """Multiple Smiths within AMBIGUITY_THRESHOLD score points should raise."""
        resolver = PlayerResolver(make_roster_with_similar_names())
        with pytest.raises(AmbiguousMatchError) as exc_info:
            resolver.resolve("Smith")
        error_msg = str(exc_info.value)
        # Should list at least 2 players
        assert error_msg.count("Smith") >= 2

from thefuzz import fuzz
from fantasy_sim.models.player import TeamRoster

# Minimum fuzzy match score to accept (0-100)
MIN_MATCH_SCORE = 70

# If 2+ matches are within this many points of the best, it's ambiguous
AMBIGUITY_THRESHOLD = 5


class AmbiguousMatchError(KeyError):
    """Raised when a player query matches multiple players with similar scores."""
    pass


class PlayerResolver:
    """Resolve player names/IDs to nflverse player_id values."""

    def __init__(self, rosters: list[TeamRoster]):
        self._id_map: dict[str, str] = {}
        self._name_map: dict[str, str] = {}
        self._all_names: list[tuple[str, str]] = []

        for roster in rosters:
            for player in roster.players:
                self._id_map[player.player_id] = player.player_id
                name_lower = player.name.lower()
                self._name_map[name_lower] = player.player_id
                self._all_names.append((player.name, player.player_id))

    def resolve(self, query: str) -> str:
        """Resolve a player query to a player_id.

        Tries in order:
        1. Exact player_id match
        2. Exact name match (case-insensitive)
        3. Underscore-to-space conversion
        4. Fuzzy name match with ambiguity detection

        Raises KeyError if no match found.
        Raises AmbiguousMatchError if 2+ players match within AMBIGUITY_THRESHOLD.
        """
        # 1. Exact ID
        if query in self._id_map:
            return self._id_map[query]

        # 2. Exact name (case-insensitive)
        query_lower = query.lower()
        if query_lower in self._name_map:
            return self._name_map[query_lower]

        # 3. Underscore conversion
        query_spaces = query_lower.replace("_", " ")
        if query_spaces in self._name_map:
            return self._name_map[query_spaces]

        # 4. Fuzzy match with ambiguity detection
        scored_matches: list[tuple[int, str, str]] = []
        for name, pid in self._all_names:
            score = max(
                fuzz.ratio(query_lower, name.lower()),
                fuzz.partial_ratio(query_lower, name.lower()),
            )
            if score >= MIN_MATCH_SCORE:
                scored_matches.append((score, name, pid))

        if not scored_matches:
            best_score = 0
            for name, pid in self._all_names:
                score = max(
                    fuzz.ratio(query_lower, name.lower()),
                    fuzz.partial_ratio(query_lower, name.lower()),
                )
                if score > best_score:
                    best_score = score
            raise KeyError(
                f"No player found matching '{query}'. "
                f"Best match score: {best_score}/100 (need {MIN_MATCH_SCORE}+)"
            )

        scored_matches.sort(key=lambda x: x[0], reverse=True)
        best_score = scored_matches[0][0]

        close_matches = [
            (score, name, pid) for score, name, pid in scored_matches
            if best_score - score <= AMBIGUITY_THRESHOLD
        ]

        if len(close_matches) >= 2:
            options = "\n".join(
                f"  - {name} ({pid}, score={score})"
                for score, name, pid in close_matches
            )
            raise AmbiguousMatchError(
                f"Ambiguous match for '{query}'. Multiple players match with similar scores:\n"
                f"{options}\n"
                f"Please use a more specific name or the player_id directly."
            )

        return scored_matches[0][2]

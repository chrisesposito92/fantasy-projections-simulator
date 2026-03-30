from thefuzz import fuzz
from fantasy_sim.models.player import TeamRoster

# Minimum fuzzy match score to accept (0-100)
MIN_MATCH_SCORE = 70


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
        4. Fuzzy name match

        Raises KeyError if no match found.
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

        # 4. Fuzzy match
        best_score = 0
        best_id = None
        for name, pid in self._all_names:
            score = max(
                fuzz.ratio(query_lower, name.lower()),
                fuzz.partial_ratio(query_lower, name.lower()),
            )
            if score > best_score:
                best_score = score
                best_id = pid

        if best_score >= MIN_MATCH_SCORE and best_id is not None:
            return best_id

        raise KeyError(
            f"No player found matching '{query}'. "
            f"Best match score: {best_score}/100 (need {MIN_MATCH_SCORE}+)"
        )

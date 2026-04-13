from __future__ import annotations

from collections import defaultdict
from typing import Any

import polars as pl
from polars._typing import SchemaDict

from fantasy_sim.data.loader import DataLoader
from fantasy_sim.data.market_history.teams import TEAM_NAME_TO_ABBREV
from fantasy_sim.data.vegas.crosswalk import fuzzy_match, standardize_name

FANTASY_POSITIONS: tuple[str, ...] = ("QB", "RB", "WR", "TE")

ODDS_PLAYER_CROSSWALK_SCHEMA: SchemaDict = {
    "season": pl.Int64,
    "week": pl.Int64,
    "schedule_game_id": pl.Utf8,
    "player_name": pl.Utf8,
    "player_name_normalized": pl.Utf8,
    "player_id": pl.Utf8,
    "full_name": pl.Utf8,
    "team": pl.Utf8,
    "position": pl.Utf8,
    "match_source": pl.Utf8,
}


def _resolve_game_teams(row: dict[str, Any]) -> tuple[str | None, str | None]:
    schedule_game_id = row.get("schedule_game_id")
    if isinstance(schedule_game_id, str):
        parts = schedule_game_id.split("_")
        if len(parts) >= 4:
            return parts[-2], parts[-1]

    home_team = row.get("home_team")
    away_team = row.get("away_team")
    home_abbr = TEAM_NAME_TO_ABBREV.get(str(home_team)) if home_team is not None else None
    away_abbr = TEAM_NAME_TO_ABBREV.get(str(away_team)) if away_team is not None else None
    return home_abbr, away_abbr


class OddsPlayerCrosswalk:
    """Resolve The Odds API player names to nflverse player IDs for one season."""

    def __init__(
        self,
        loader: DataLoader | None = None,
        fuzzy_threshold: float = 0.85,
    ) -> None:
        self._loader = loader or DataLoader()
        self._fuzzy_threshold = fuzzy_threshold
        self._cache: dict[int, pl.DataFrame] = {}

    def build_for_season(self, market_frame: pl.DataFrame, season: int) -> pl.DataFrame:
        cached = self._cache.get(season)
        if cached is not None:
            return cached

        season_frame = (
            market_frame.filter(pl.col("season") == season)
            .select(
                [
                    "season",
                    "week",
                    "schedule_game_id",
                    "player_name",
                    "player_name_normalized",
                    "home_team",
                    "away_team",
                ]
            )
            .unique(
                subset=[
                    "season",
                    "week",
                    "schedule_game_id",
                    "player_name_normalized",
                ]
            )
        )
        if season_frame.is_empty():
            empty = pl.DataFrame(schema=ODDS_PLAYER_CROSSWALK_SCHEMA)
            self._cache[season] = empty
            return empty

        roster = self._loader.load_rosters([season])
        if roster.is_empty():
            empty = pl.DataFrame(schema=ODDS_PLAYER_CROSSWALK_SCHEMA)
            self._cache[season] = empty
            return empty

        player_name_col = "player_name" if "player_name" in roster.columns else "full_name"
        roster_rows: list[dict[str, Any]] = []
        for row in (
            roster.filter(pl.col("position").is_in(list(FANTASY_POSITIONS)))
            .select(["season", "week", "player_id", player_name_col, "position", "team"])
            .unique(subset=["week", "player_id"])
            .iter_rows(named=True)
        ):
            full_name = str(row.get(player_name_col) or "")
            roster_rows.append(
                {
                    "season": int(row["season"]),
                    "week": int(row["week"]),
                    "player_id": str(row["player_id"]),
                    "full_name": full_name,
                    "position": str(row["position"]),
                    "team": str(row["team"]),
                    "player_name_normalized": standardize_name(full_name),
                }
            )

        roster_by_week_team: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
        for row in roster_rows:
            roster_by_week_team[(int(row["week"]), str(row["team"]))].append(row)

        matched_rows: list[dict[str, Any]] = []
        for row in season_frame.iter_rows(named=True):
            week = int(row["week"])
            home_abbr, away_abbr = _resolve_game_teams(row)
            candidates: list[dict[str, Any]] = []
            for team in (home_abbr, away_abbr):
                if team is None:
                    continue
                candidates.extend(roster_by_week_team.get((week, team), []))

            if not candidates:
                continue

            query = str(row["player_name_normalized"] or standardize_name(str(row["player_name"])))
            exact_matches = [
                candidate
                for candidate in candidates
                if candidate["player_name_normalized"] == query
            ]
            if len(exact_matches) == 1:
                chosen = exact_matches[0]
                match_source = "exact"
            elif len(exact_matches) > 1:
                continue
            else:
                unique_candidates: dict[str, str] = {}
                candidate_by_id: dict[str, dict[str, Any]] = {}
                normalized_name_counts: dict[str, int] = defaultdict(int)
                for candidate in candidates:
                    normalized = str(candidate["player_name_normalized"])
                    normalized_name_counts[normalized] += 1
                for candidate in candidates:
                    normalized = str(candidate["player_name_normalized"])
                    if normalized_name_counts[normalized] > 1:
                        continue
                    player_id = str(candidate["player_id"])
                    unique_candidates[normalized] = player_id
                    candidate_by_id[player_id] = candidate
                matched_player_id = fuzzy_match(
                    query,
                    unique_candidates,
                    threshold=self._fuzzy_threshold,
                )
                if matched_player_id is None:
                    continue
                chosen = candidate_by_id[matched_player_id]
                match_source = "fuzzy"

            matched_rows.append(
                {
                    "season": int(row["season"]),
                    "week": week,
                    "schedule_game_id": str(row["schedule_game_id"]),
                    "player_name": str(row["player_name"]),
                    "player_name_normalized": query,
                    "player_id": str(chosen["player_id"]),
                    "full_name": str(chosen["full_name"]),
                    "team": str(chosen["team"]),
                    "position": str(chosen["position"]),
                    "match_source": match_source,
                }
            )

        frame = (
            pl.DataFrame(matched_rows, schema=ODDS_PLAYER_CROSSWALK_SCHEMA)
            if matched_rows
            else pl.DataFrame(schema=ODDS_PLAYER_CROSSWALK_SCHEMA)
        )
        self._cache[season] = frame
        return frame

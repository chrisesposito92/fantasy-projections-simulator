from dataclasses import dataclass
import polars as pl
from fantasy_sim.engine.types import PlayerBoxScore
from fantasy_sim.scoring.engine import score_player


@dataclass
class ActualPlayerWeek:
    """Actual fantasy points for one player in one week."""
    player_id: str
    name: str
    position: str
    team: str
    season: int
    week: int
    fpts: float
    pass_yards: int = 0
    pass_tds: int = 0
    interceptions: int = 0
    rush_yards: int = 0
    rush_tds: int = 0
    receptions: int = 0
    targets: int = 0
    receiving_yards: int = 0
    receiving_tds: int = 0
    fumbles_lost: int = 0


def load_actual_scores(
    player_stats: pl.DataFrame,
    scoring_config: dict,
    season: int,
    weeks: list[int] | None = None,
) -> list[ActualPlayerWeek]:
    """Convert nflverse player_stats into scored ActualPlayerWeek objects."""
    filtered = player_stats.filter(pl.col("season") == season)
    if weeks is not None:
        filtered = filtered.filter(pl.col("week").is_in(weeks))

    actuals = []
    for row in filtered.iter_rows(named=True):
        if row.get("position") is None:
            continue
        fumbles = (
            (row.get("receiving_fumbles_lost", 0) or 0) +
            (row.get("rushing_fumbles_lost", 0) or 0) +
            (row.get("sack_fumbles_lost", 0) or 0)
        )
        # Handle nflverse column name variations
        team = row.get("recent_team") or row.get("team") or ""
        name = row.get("player_name") or row.get("player_display_name") or ""
        interceptions = row.get("interceptions") or row.get("passing_interceptions") or 0
        sacks = row.get("sacks") or row.get("sacks_suffered") or 0
        box = PlayerBoxScore(
            player_id=row["player_id"],
            name=name,
            position=row["position"],
            team=team,
            pass_yards=row.get("passing_yards", 0) or 0,
            pass_tds=row.get("passing_tds", 0) or 0,
            completions=row.get("completions", 0) or 0,
            pass_attempts=row.get("attempts", 0) or 0,
            interceptions=interceptions,
            sacks=sacks,
            rush_yards=row.get("rushing_yards", 0) or 0,
            rush_tds=row.get("rushing_tds", 0) or 0,
            rush_attempts=row.get("carries", 0) or 0,
            receptions=row.get("receptions", 0) or 0,
            targets=row.get("targets", 0) or 0,
            receiving_yards=row.get("receiving_yards", 0) or 0,
            receiving_tds=row.get("receiving_tds", 0) or 0,
            fumbles_lost=fumbles,
        )
        fpts = score_player(box, scoring_config)

        actuals.append(ActualPlayerWeek(
            player_id=row["player_id"],
            name=name,
            position=row["position"],
            team=team,
            season=row["season"],
            week=row["week"],
            fpts=round(fpts, 1),
            pass_yards=box.pass_yards,
            pass_tds=box.pass_tds,
            interceptions=box.interceptions,
            rush_yards=box.rush_yards,
            rush_tds=box.rush_tds,
            receptions=box.receptions,
            targets=box.targets,
            receiving_yards=box.receiving_yards,
            receiving_tds=box.receiving_tds,
            fumbles_lost=box.fumbles_lost,
        ))

    return actuals

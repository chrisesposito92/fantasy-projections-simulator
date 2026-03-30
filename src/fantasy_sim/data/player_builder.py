"""Build PlayerModel objects from PBP and roster data."""

import polars as pl
import numpy as np
from fantasy_sim.models.player import PlayerModel, PlayerUsage, PlayerOutcomes, TeamRoster

MIN_PLAYER_PLAYS = 5


def build_player_models(
    pbp: pl.DataFrame,
    rosters: pl.DataFrame,
    seasons: list[int],
) -> dict[str, PlayerModel]:
    """Build PlayerModels from PBP and roster data. Returns dict keyed by player_id."""
    plays = pbp.filter(
        pl.col("play_type").is_in(["pass", "run"]) &
        pl.col("season").is_in(seasons)
    )

    player_meta = (
        rosters.filter(pl.col("season").is_in(seasons))
        .sort("week", descending=True)
        .group_by("player_id")
        .first()
        .select(["player_id", "player_name", "position", "team"])
    )
    meta_map = {
        row["player_id"]: row
        for row in player_meta.iter_rows(named=True)
    }

    team_pass_attempts = {}
    team_rush_attempts = {}
    for team in plays["posteam"].unique().to_list():
        tp = plays.filter(pl.col("posteam") == team)
        team_pass_attempts[team] = tp.filter(pl.col("play_type") == "pass").shape[0]
        team_rush_attempts[team] = tp.filter(pl.col("play_type") == "run").shape[0]

    pass_plays = plays.filter(pl.col("play_type") == "pass")
    receiving_stats = {}
    for row in pass_plays.iter_rows(named=True):
        rid = row.get("receiver_player_id")
        if rid is None:
            continue
        if rid not in receiving_stats:
            receiving_stats[rid] = {"targets": 0, "catches": 0, "yards": [], "team": row["posteam"]}
        receiving_stats[rid]["targets"] += 1
        if row["complete_pass"] == 1:
            receiving_stats[rid]["catches"] += 1
            receiving_stats[rid]["yards"].append(row["yards_gained"])

    rush_plays = plays.filter(pl.col("play_type") == "run")
    rushing_stats = {}
    for row in rush_plays.iter_rows(named=True):
        rid = row.get("rusher_player_id")
        if rid is None:
            continue
        if rid not in rushing_stats:
            rushing_stats[rid] = {"carries": 0, "yards": [], "team": row["posteam"]}
        rushing_stats[rid]["carries"] += 1
        rushing_stats[rid]["yards"].append(row["yards_gained"])

    qb_stats = {}
    for row in pass_plays.iter_rows(named=True):
        pid = row.get("passer_player_id")
        if pid is None:
            continue
        if pid not in qb_stats:
            qb_stats[pid] = {"attempts": 0, "team": row["posteam"]}
        qb_stats[pid]["attempts"] += 1

    models = {}
    all_player_ids = set()
    all_player_ids.update(receiving_stats.keys())
    all_player_ids.update(rushing_stats.keys())
    all_player_ids.update(qb_stats.keys())

    for pid in all_player_ids:
        meta = meta_map.get(pid)
        if meta is None:
            continue

        team = meta["team"]
        position = meta["position"]

        usage = PlayerUsage()
        if pid in receiving_stats:
            rs = receiving_stats[pid]
            team_pa = team_pass_attempts.get(team, 1)
            usage.target_share = rs["targets"] / team_pa
        if pid in rushing_stats:
            rs = rushing_stats[pid]
            team_ra = team_rush_attempts.get(team, 1)
            usage.carry_share = rs["carries"] / team_ra
        if position == "QB" and pid in qb_stats:
            qs = qb_stats[pid]
            team_pa = team_pass_attempts.get(team, 1)
            usage.snap_share = qs["attempts"] / team_pa

        outcomes = PlayerOutcomes()
        if pid in receiving_stats:
            rs = receiving_stats[pid]
            if rs["targets"] > 0:
                outcomes.catch_rate = rs["catches"] / rs["targets"]
            if len(rs["yards"]) >= MIN_PLAYER_PLAYS:
                outcomes.receiving_yards_dist = np.array(rs["yards"])
        if pid in rushing_stats:
            rs = rushing_stats[pid]
            if len(rs["yards"]) >= MIN_PLAYER_PLAYS:
                outcomes.rushing_yards_dist = np.array(rs["yards"])

        models[pid] = PlayerModel(
            player_id=pid,
            name=meta["player_name"],
            position=position,
            team=team,
            usage=usage,
            outcomes=outcomes,
        )

    return models


def build_team_roster(team: str, models: dict[str, PlayerModel]) -> TeamRoster:
    """Build a TeamRoster from a dict of PlayerModels."""
    team_players = [m for m in models.values() if m.team == team]
    return TeamRoster(team=team, players=team_players)

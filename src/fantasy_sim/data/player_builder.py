"""Build PlayerModel objects from PBP and roster data."""

from copy import deepcopy

import polars as pl
import numpy as np
from fantasy_sim.models.player import PlayerModel, PlayerUsage, PlayerOutcomes, TeamRoster
from fantasy_sim.data.rookie_builder import POSITIONAL_ARCHETYPES

MIN_PLAYER_PLAYS = 5


def blend_with_archetype(
    model: PlayerModel,
    rookie_blend_games: int = 4,
    draft_round: int = 7,
) -> PlayerModel:
    """Blend a player's real stats with positional archetype when data is sparse."""
    if model.games_played >= rookie_blend_games:
        return model

    if model.position not in POSITIONAL_ARCHETYPES:
        return model

    # Determine tier from draft round
    if draft_round <= 2:
        tier = "tier1"
    elif draft_round <= 4:
        tier = "tier2"
    else:
        tier = "tier3"

    archetype = POSITIONAL_ARCHETYPES[model.position][tier]
    real_weight = min(1.0, model.games_played / max(rookie_blend_games, 1))
    arch_weight = 1.0 - real_weight

    blended_model = deepcopy(model)

    # Blend usage rates by position
    if model.position == "QB":
        blended_model.usage.snap_share = _blend_float(
            model.usage.snap_share, archetype.get("snap_share", 0.0), real_weight, arch_weight)
        blended_model.usage.scramble_rate = _blend_float(
            model.usage.scramble_rate, archetype.get("scramble_rate", 0.0), real_weight, arch_weight)
    elif model.position == "RB":
        blended_model.usage.carry_share = _blend_float(
            model.usage.carry_share, archetype.get("carry_share", 0.0), real_weight, arch_weight)
        blended_model.usage.target_share = _blend_float(
            model.usage.target_share, archetype.get("target_share", 0.0), real_weight, arch_weight)
    elif model.position in ("WR", "TE"):
        blended_model.usage.target_share = _blend_float(
            model.usage.target_share, archetype.get("target_share", 0.0), real_weight, arch_weight)
        blended_model.usage.red_zone_target_share = _blend_float(
            model.usage.red_zone_target_share, archetype.get("red_zone_target_share", 0.0), real_weight, arch_weight)

    # Blend outcome rates
    blended_model.outcomes.catch_rate = _blend_float(
        model.outcomes.catch_rate, archetype.get("catch_rate", 0.0), real_weight, arch_weight)
    blended_model.outcomes.fumble_rate = _blend_float(
        model.outcomes.fumble_rate, archetype.get("fumble_rate", 0.0), real_weight, arch_weight)

    # Blend yards distributions
    if model.position == "QB" and "scramble_yards" in archetype:
        blended_model.outcomes.scramble_yards_dist = _blend_dist(
            model.outcomes.scramble_yards_dist, np.array(archetype["scramble_yards"]), real_weight, arch_weight)
    if model.position == "RB" and "rush_yards" in archetype:
        blended_model.outcomes.rushing_yards_dist = _blend_dist(
            model.outcomes.rushing_yards_dist, np.array(archetype["rush_yards"]), real_weight, arch_weight)
    if model.position in ("RB", "WR", "TE") and "rec_yards" in archetype:
        blended_model.outcomes.receiving_yards_dist = _blend_dist(
            model.outcomes.receiving_yards_dist, np.array(archetype["rec_yards"]), real_weight, arch_weight)

    return blended_model


def _blend_float(real: float, archetype: float, real_weight: float, arch_weight: float) -> float:
    return real * real_weight + archetype * arch_weight


def _blend_dist(real_dist, archetype_dist, real_weight, arch_weight):
    """Blend two yard distributions by concatenating proportional samples."""
    if real_dist is None or len(real_dist) == 0:
        return archetype_dist.copy()
    target_size = max(len(real_dist) + len(archetype_dist), 10)
    real_count = max(1, int(target_size * real_weight))
    arch_count = max(1, int(target_size * arch_weight))
    rng = np.random.default_rng(0)
    real_samples = rng.choice(real_dist, size=min(real_count, len(real_dist) * 3), replace=True)
    arch_samples = rng.choice(archetype_dist, size=min(arch_count, len(archetype_dist) * 3), replace=True)
    return np.concatenate([real_samples, arch_samples])


def _aggregate_pbp_stats(
    pbp: pl.DataFrame,
    training_seasons: list[int],
) -> dict:
    """Aggregate raw PBP data into per-player and per-team stat buckets.

    This is a pure data-extraction step — no PlayerModel objects are created.
    The result can be cached and reused across multiple roster merges.

    Returns a dict with keys:
        - receiving: dict[player_id -> {targets, catches, yards list, rz_targets, air_yards, team, game_ids set}]
        - rushing:   dict[player_id -> {carries, yards list, rz_carries, team, game_ids set}]
        - qb:        dict[player_id -> {attempts, team, game_ids set}]
        - team_pass_attempts:    dict[team -> int]
        - team_rush_attempts:    dict[team -> int]
        - team_rz_pass_attempts: dict[team -> int]
        - team_rz_rush_attempts: dict[team -> int]
        - team_air_yards:        dict[team -> float]
        - has_air_yards:         bool
    """
    plays = pbp.filter(
        pl.col("play_type").is_in(["pass", "run"]) &
        pl.col("season").is_in(training_seasons)
    )

    # --- Team-level totals ---
    team_pass_attempts: dict[str, int] = {}
    team_rush_attempts: dict[str, int] = {}
    team_rz_pass_attempts: dict[str, int] = {}
    team_rz_rush_attempts: dict[str, int] = {}
    team_air_yards: dict[str, float] = {}

    has_air_yards = "air_yards" in plays.columns

    for team in plays["posteam"].unique().to_list():
        tp = plays.filter(pl.col("posteam") == team)
        pass_plays_team = tp.filter(pl.col("play_type") == "pass")
        rush_plays_team = tp.filter(pl.col("play_type") == "run")

        team_pass_attempts[team] = pass_plays_team.shape[0]
        team_rush_attempts[team] = rush_plays_team.shape[0]

        # Red zone totals (yardline_100 <= 20)
        team_rz_pass_attempts[team] = pass_plays_team.filter(
            pl.col("yardline_100") <= 20
        ).shape[0]
        team_rz_rush_attempts[team] = rush_plays_team.filter(
            pl.col("yardline_100") <= 20
        ).shape[0]

        # Air yards total per team
        if has_air_yards:
            ay_series = pass_plays_team["air_yards"].drop_nulls()
            team_air_yards[team] = float(ay_series.sum()) if len(ay_series) > 0 else 0.0
        else:
            team_air_yards[team] = 0.0

    # --- Receiving stats (pass plays) ---
    pass_plays = plays.filter(pl.col("play_type") == "pass")
    receiving_stats: dict[str, dict] = {}
    for row in pass_plays.iter_rows(named=True):
        rid = row.get("receiver_player_id")
        if rid is None:
            continue
        if rid not in receiving_stats:
            receiving_stats[rid] = {
                "targets": 0, "catches": 0, "yards": [],
                "rz_targets": 0, "air_yards": 0.0,
                "team": row["posteam"], "game_ids": set(),
            }
        receiving_stats[rid]["targets"] += 1
        receiving_stats[rid]["game_ids"].add(row["game_id"])

        # Red zone target
        if row["yardline_100"] <= 20:
            receiving_stats[rid]["rz_targets"] += 1

        # Air yards
        if has_air_yards and row.get("air_yards") is not None:
            receiving_stats[rid]["air_yards"] += row["air_yards"]

        if row["complete_pass"] == 1:
            receiving_stats[rid]["catches"] += 1
            receiving_stats[rid]["yards"].append(row["yards_gained"])

    # --- Rushing stats (run plays) ---
    rush_plays = plays.filter(pl.col("play_type") == "run")
    rushing_stats: dict[str, dict] = {}
    for row in rush_plays.iter_rows(named=True):
        rid = row.get("rusher_player_id")
        if rid is None:
            continue
        if rid not in rushing_stats:
            rushing_stats[rid] = {
                "carries": 0, "yards": [], "rz_carries": 0,
                "team": row["posteam"], "game_ids": set(),
            }
        rushing_stats[rid]["carries"] += 1
        rushing_stats[rid]["yards"].append(row["yards_gained"])
        rushing_stats[rid]["game_ids"].add(row["game_id"])

        # Red zone carry
        if row["yardline_100"] <= 20:
            rushing_stats[rid]["rz_carries"] += 1

    # --- QB stats (passer on pass plays) ---
    qb_stats: dict[str, dict] = {}
    for row in pass_plays.iter_rows(named=True):
        pid = row.get("passer_player_id")
        if pid is None:
            continue
        if pid not in qb_stats:
            qb_stats[pid] = {
                "attempts": 0, "team": row["posteam"], "game_ids": set(),
            }
        qb_stats[pid]["attempts"] += 1
        qb_stats[pid]["game_ids"].add(row["game_id"])

    return {
        "receiving": receiving_stats,
        "rushing": rushing_stats,
        "qb": qb_stats,
        "team_pass_attempts": team_pass_attempts,
        "team_rush_attempts": team_rush_attempts,
        "team_rz_pass_attempts": team_rz_pass_attempts,
        "team_rz_rush_attempts": team_rz_rush_attempts,
        "team_air_yards": team_air_yards,
        "has_air_yards": has_air_yards,
    }


def build_player_models(
    pbp: pl.DataFrame,
    rosters: pl.DataFrame,
    seasons: list[int],
    rookie_blend_games: int = 0,
) -> dict[str, PlayerModel]:
    """Build PlayerModels from PBP and roster data. Returns dict keyed by player_id."""
    plays = pbp.filter(
        pl.col("play_type").is_in(["pass", "run"]) &
        pl.col("season").is_in(seasons)
    )

    # --- Player metadata from rosters ---
    player_meta = (
        rosters.filter(pl.col("season").is_in(seasons))
        .sort(["season", "week"], descending=True)
        .group_by("player_id")
        .first()
        .select(["player_id", "player_name", "position", "team"])
    )
    meta_map = {
        row["player_id"]: row
        for row in player_meta.iter_rows(named=True)
    }

    # --- Team-level totals ---
    team_pass_attempts: dict[str, int] = {}
    team_rush_attempts: dict[str, int] = {}
    team_rz_pass_attempts: dict[str, int] = {}
    team_rz_rush_attempts: dict[str, int] = {}
    team_air_yards: dict[str, float] = {}

    has_air_yards = "air_yards" in plays.columns

    for team in plays["posteam"].unique().to_list():
        tp = plays.filter(pl.col("posteam") == team)
        pass_plays_team = tp.filter(pl.col("play_type") == "pass")
        rush_plays_team = tp.filter(pl.col("play_type") == "run")

        team_pass_attempts[team] = pass_plays_team.shape[0]
        team_rush_attempts[team] = rush_plays_team.shape[0]

        # Red zone totals (yardline_100 <= 20)
        team_rz_pass_attempts[team] = pass_plays_team.filter(
            pl.col("yardline_100") <= 20
        ).shape[0]
        team_rz_rush_attempts[team] = rush_plays_team.filter(
            pl.col("yardline_100") <= 20
        ).shape[0]

        # Air yards total per team
        if has_air_yards:
            ay_series = pass_plays_team["air_yards"].drop_nulls()
            team_air_yards[team] = float(ay_series.sum()) if len(ay_series) > 0 else 0.0
        else:
            team_air_yards[team] = 0.0

    # --- Receiving stats (pass plays) ---
    pass_plays = plays.filter(pl.col("play_type") == "pass")
    receiving_stats: dict[str, dict] = {}
    for row in pass_plays.iter_rows(named=True):
        rid = row.get("receiver_player_id")
        if rid is None:
            continue
        if rid not in receiving_stats:
            receiving_stats[rid] = {
                "targets": 0, "catches": 0, "yards": [],
                "rz_targets": 0, "air_yards": 0.0,
                "team": row["posteam"], "game_ids": set(),
            }
        receiving_stats[rid]["targets"] += 1
        receiving_stats[rid]["game_ids"].add(row["game_id"])

        # Red zone target
        if row["yardline_100"] <= 20:
            receiving_stats[rid]["rz_targets"] += 1

        # Air yards
        if has_air_yards and row.get("air_yards") is not None:
            receiving_stats[rid]["air_yards"] += row["air_yards"]

        if row["complete_pass"] == 1:
            receiving_stats[rid]["catches"] += 1
            receiving_stats[rid]["yards"].append(row["yards_gained"])

    # --- Rushing stats (run plays) ---
    rush_plays = plays.filter(pl.col("play_type") == "run")
    rushing_stats: dict[str, dict] = {}
    for row in rush_plays.iter_rows(named=True):
        rid = row.get("rusher_player_id")
        if rid is None:
            continue
        if rid not in rushing_stats:
            rushing_stats[rid] = {
                "carries": 0, "yards": [], "rz_carries": 0,
                "team": row["posteam"], "game_ids": set(),
            }
        rushing_stats[rid]["carries"] += 1
        rushing_stats[rid]["yards"].append(row["yards_gained"])
        rushing_stats[rid]["game_ids"].add(row["game_id"])

        # Red zone carry
        if row["yardline_100"] <= 20:
            rushing_stats[rid]["rz_carries"] += 1

    # --- QB stats (passer on pass plays) ---
    qb_stats: dict[str, dict] = {}
    for row in pass_plays.iter_rows(named=True):
        pid = row.get("passer_player_id")
        if pid is None:
            continue
        if pid not in qb_stats:
            qb_stats[pid] = {
                "attempts": 0, "team": row["posteam"], "game_ids": set(),
            }
        qb_stats[pid]["attempts"] += 1
        qb_stats[pid]["game_ids"].add(row["game_id"])

    # --- Build PlayerModels ---
    models: dict[str, PlayerModel] = {}
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

        # Collect game_ids across all stat categories for this player
        game_ids: set[str] = set()
        if pid in receiving_stats:
            game_ids |= receiving_stats[pid]["game_ids"]
        if pid in rushing_stats:
            game_ids |= rushing_stats[pid]["game_ids"]
        if pid in qb_stats:
            game_ids |= qb_stats[pid]["game_ids"]

        usage = PlayerUsage()

        # Target share + red zone target share
        if pid in receiving_stats:
            rs = receiving_stats[pid]
            team_pa = team_pass_attempts.get(team, 0)
            usage.target_share = rs["targets"] / max(team_pa, 1)

            team_rz_pa = team_rz_pass_attempts.get(team, 0)
            if team_rz_pa > 0:
                usage.red_zone_target_share = rs["rz_targets"] / team_rz_pa

            # Air yards share
            if has_air_yards:
                team_ay = team_air_yards.get(team, 0.0)
                if team_ay > 0:
                    usage.air_yards_share = rs["air_yards"] / team_ay

        # Carry share + red zone carry share
        if pid in rushing_stats:
            rs = rushing_stats[pid]
            team_ra = team_rush_attempts.get(team, 0)
            usage.carry_share = rs["carries"] / max(team_ra, 1)

            team_rz_ra = team_rz_rush_attempts.get(team, 0)
            if team_rz_ra > 0:
                usage.red_zone_carry_share = rs["rz_carries"] / team_rz_ra

        # QB snap share and scramble rate
        if position == "QB" and pid in qb_stats:
            qs = qb_stats[pid]
            team_pa = team_pass_attempts.get(team, 0)
            usage.snap_share = qs["attempts"] / max(team_pa, 1)

            # Scramble rate: QB rush attempts / (QB pass attempts + QB rush attempts)
            qb_rush = rushing_stats[pid]["carries"] if pid in rushing_stats else 0
            qb_pass = qs["attempts"]
            total_qb_plays = qb_pass + qb_rush
            if total_qb_plays > 0:
                usage.scramble_rate = qb_rush / total_qb_plays

        # --- Outcomes ---
        outcomes = PlayerOutcomes()

        if pid in receiving_stats:
            rs = receiving_stats[pid]
            if rs["targets"] > 0:
                outcomes.catch_rate = rs["catches"] / rs["targets"]
            if len(rs["yards"]) >= MIN_PLAYER_PLAYS:
                outcomes.receiving_yards_dist = np.array(rs["yards"])

        if pid in rushing_stats:
            rs = rushing_stats[pid]
            if position == "QB":
                # QB rush yards -> scramble_yards_dist (not rushing_yards_dist)
                if len(rs["yards"]) >= 1:
                    outcomes.scramble_yards_dist = np.array(rs["yards"])
            else:
                if len(rs["yards"]) >= MIN_PLAYER_PLAYS:
                    outcomes.rushing_yards_dist = np.array(rs["yards"])

        models[pid] = PlayerModel(
            player_id=pid,
            name=meta["player_name"],
            position=position,
            team=team,
            usage=usage,
            outcomes=outcomes,
            games_played=len(game_ids) if game_ids else 17,
        )

    # Apply rookie blend if configured
    if rookie_blend_games > 0:
        for pid in list(models.keys()):
            model = models[pid]
            if model.games_played < rookie_blend_games:
                models[pid] = blend_with_archetype(model, rookie_blend_games=rookie_blend_games)

    return models


def build_team_roster(team: str, models: dict[str, PlayerModel]) -> TeamRoster:
    """Build a TeamRoster from a dict of PlayerModels."""
    team_players = [m for m in models.values() if m.team == team]
    return TeamRoster(team=team, players=team_players)

"""Build PlayerModel objects from PBP and roster data."""

from copy import deepcopy

import polars as pl
import numpy as np
from fantasy_sim.models.player import PlayerModel, PlayerUsage, PlayerOutcomes, TeamRoster
from fantasy_sim.data.rookie_builder import POSITIONAL_ARCHETYPES, build_rookie_model

MIN_PLAYER_PLAYS = 5
MIN_RZ_TARGETS = 10  # Minimum RZ targets for per-player RZ catch rate
FANTASY_POSITIONS = {"QB", "RB", "WR", "TE", "K"}
ACTIVE_STATUSES = {"ACT"}


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


def build_kicker_model(player_id: str, name: str, team: str) -> PlayerModel:
    """Build a placeholder PlayerModel for a kicker (name tag for scoring attribution)."""
    return PlayerModel(
        player_id=player_id,
        name=name,
        position="K",
        team=team,
        usage=PlayerUsage(),
        outcomes=PlayerOutcomes(),
        games_played=17,
    )


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
                "rz_targets": 0, "rz_catches": 0, "rz_yards": [],
                "air_yards": 0.0,
                "team": row["posteam"], "game_ids": set(),
            }
        receiving_stats[rid]["targets"] += 1
        receiving_stats[rid]["game_ids"].add(row["game_id"])

        # Red zone target
        if row["yardline_100"] <= 20:
            receiving_stats[rid]["rz_targets"] += 1
            if row["complete_pass"] == 1:
                receiving_stats[rid]["rz_catches"] += 1
                receiving_stats[rid]["rz_yards"].append(row["yards_gained"])

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
                "non_sack_attempts": 0, "non_sack_fumbles": 0,
            }
        qb_stats[pid]["attempts"] += 1
        qb_stats[pid]["game_ids"].add(row["game_id"])
        if row["sack"] != 1:
            qb_stats[pid]["non_sack_attempts"] += 1
            # Only count pre-throw fumbles (not receiver fumbles after catch)
            if row["fumble_lost"] == 1 and row["complete_pass"] != 1 and row["interception"] != 1:
                qb_stats[pid]["non_sack_fumbles"] += 1

    # --- QB scramble separation ---
    has_qb_scramble = "qb_scramble" in plays.columns
    qb_scrambles: dict[str, dict] = {}

    if has_qb_scramble:
        qb_passer_ids = set(qb_stats.keys())
        for row in rush_plays.iter_rows(named=True):
            rid = row.get("rusher_player_id")
            if rid is None or rid not in qb_passer_ids:
                continue
            if rid not in qb_scrambles:
                qb_scrambles[rid] = {"scramble_count": 0, "scramble_yards": [],
                                     "designed_count": 0}
            if row.get("qb_scramble") == 1:
                qb_scrambles[rid]["scramble_count"] += 1
                qb_scrambles[rid]["scramble_yards"].append(row["yards_gained"])
            else:
                qb_scrambles[rid]["designed_count"] += 1

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
        "qb_scrambles": qb_scrambles,
        "has_qb_scramble": has_qb_scramble,
    }


def _assemble_models(
    aggregated_stats: dict,
    current_rosters: pl.DataFrame,
    rookie_blend_games: int = 0,
) -> dict[str, PlayerModel]:
    """Merge pre-computed PBP stats with a current roster to produce PlayerModels.

    Players on the current roster get their team/position from the roster.
    Usage shares are computed against the player's HISTORICAL team totals
    (the team recorded in the PBP stats), not the current team.

    - Skill players with PBP data -> historical stats, current team
    - Skill players without PBP data -> rookie archetype (draft_round=7)
    - Kickers -> placeholder model via build_kicker_model
    - Players NOT on current roster -> excluded
    - Only status == "ACT" and position in FANTASY_POSITIONS are included
    """
    receiving_stats = aggregated_stats["receiving"]
    rushing_stats = aggregated_stats["rushing"]
    qb_stats = aggregated_stats["qb"]
    team_pass_attempts = aggregated_stats["team_pass_attempts"]
    team_rush_attempts = aggregated_stats["team_rush_attempts"]
    team_rz_pass_attempts = aggregated_stats["team_rz_pass_attempts"]
    team_rz_rush_attempts = aggregated_stats["team_rz_rush_attempts"]
    team_air_yards = aggregated_stats["team_air_yards"]
    has_air_yards = aggregated_stats["has_air_yards"]
    qb_scrambles = aggregated_stats.get("qb_scrambles", {})
    has_qb_scramble = aggregated_stats.get("has_qb_scramble", False)

    # Get latest roster entry per player FIRST, then filter by status/position.
    # This ensures a player who goes ACT→IR is correctly excluded (their
    # latest row is IR, not a stale ACT row from an earlier week).
    roster_latest = (
        current_rosters
        .sort(["season", "week"], descending=True)
        .group_by("player_id")
        .first()
    ).filter(
        pl.col("status").is_in(list(ACTIVE_STATUSES)) &
        pl.col("position").is_in(list(FANTASY_POSITIONS))
    )

    models: dict[str, PlayerModel] = {}

    for row in roster_latest.iter_rows(named=True):
        pid = row["player_id"]
        name = row["player_name"]
        position = row["position"]
        team = row["team"]

        # Kickers get a placeholder model
        if position == "K":
            models[pid] = build_kicker_model(pid, name, team)
            continue

        # Check if this player has any PBP data
        has_pbp = pid in receiving_stats or pid in rushing_stats or pid in qb_stats

        if not has_pbp:
            # No PBP history -> rookie archetype (tier 3, draft_round=7)
            models[pid] = build_rookie_model(pid, name, position, team, draft_round=7)
            continue

        # Player has PBP data — build model with historical stats, current team
        # Collect game_ids across all stat categories for games_played
        game_ids: set[str] = set()
        if pid in receiving_stats:
            game_ids |= receiving_stats[pid]["game_ids"]
        if pid in rushing_stats:
            game_ids |= rushing_stats[pid]["game_ids"]
        if pid in qb_stats:
            game_ids |= qb_stats[pid]["game_ids"]

        usage = PlayerUsage()

        # Target share + red zone target share (use hist_team for team totals)
        if pid in receiving_stats:
            rs = receiving_stats[pid]
            hist_team = rs["team"]
            team_pa = team_pass_attempts.get(hist_team, 0)
            usage.target_share = rs["targets"] / max(team_pa, 1)

            team_rz_pa = team_rz_pass_attempts.get(hist_team, 0)
            if team_rz_pa > 0:
                usage.red_zone_target_share = rs["rz_targets"] / team_rz_pa

            # Air yards share
            if has_air_yards:
                team_ay = team_air_yards.get(hist_team, 0.0)
                if team_ay > 0:
                    usage.air_yards_share = rs["air_yards"] / team_ay

        # Carry share + red zone carry share (use hist_team for team totals)
        if pid in rushing_stats:
            rs = rushing_stats[pid]
            hist_team = rs["team"]
            team_ra = team_rush_attempts.get(hist_team, 0)
            carries = rs["carries"]
            # For QBs, exclude scramble carries — scrambles are modeled
            # separately in _resolve_pass(), so including them here
            # double-counts QB rushing (designed runs + scrambles).
            if position == "QB" and has_qb_scramble and pid in qb_scrambles:
                carries = max(0, carries - qb_scrambles[pid]["scramble_count"])
            usage.carry_share = carries / max(team_ra, 1)

            team_rz_ra = team_rz_rush_attempts.get(hist_team, 0)
            if team_rz_ra > 0:
                usage.red_zone_carry_share = rs["rz_carries"] / team_rz_ra

        # --- Outcomes ---
        outcomes = PlayerOutcomes()

        if pid in receiving_stats:
            rs = receiving_stats[pid]
            if rs["targets"] > 0:
                outcomes.catch_rate = rs["catches"] / rs["targets"]
            # Red zone catch rate
            if rs["rz_targets"] >= MIN_RZ_TARGETS:
                outcomes.red_zone_catch_rate = rs["rz_catches"] / rs["rz_targets"]
            elif outcomes.catch_rate > 0:
                outcomes.red_zone_catch_rate = outcomes.catch_rate * 0.85
            if len(rs["yards"]) >= MIN_PLAYER_PLAYS:
                outcomes.receiving_yards_dist = np.array(rs["yards"])
            # Red zone receiving yards distribution (catches inside the 20)
            if len(rs["rz_yards"]) >= MIN_PLAYER_PLAYS:
                outcomes.rz_receiving_yards_dist = np.array(rs["rz_yards"])

        if pid in rushing_stats:
            rs = rushing_stats[pid]
            if position == "QB" and not has_qb_scramble and outcomes.scramble_yards_dist is None:
                # Fallback: no qb_scramble column, use all QB rush yards
                if len(rs["yards"]) >= 1:
                    outcomes.scramble_yards_dist = np.array(rs["yards"])
            elif position != "QB":
                if len(rs["yards"]) >= MIN_PLAYER_PLAYS:
                    outcomes.rushing_yards_dist = np.array(rs["yards"])

        # QB snap share and scramble rate (use hist_team for team totals)
        if position == "QB" and pid in qb_stats:
            qs = qb_stats[pid]
            hist_team = qs["team"]
            team_pa = team_pass_attempts.get(hist_team, 0)
            usage.snap_share = qs["attempts"] / max(team_pa, 1)

            if has_qb_scramble and pid in qb_scrambles:
                # Use qb_scramble column: only actual scrambles
                sc = qb_scrambles[pid]
                total_qb_plays = qs["attempts"] + sc["scramble_count"]
                if total_qb_plays > 0:
                    usage.scramble_rate = sc["scramble_count"] / total_qb_plays
                # Build scramble_yards_dist from scramble-only plays
                if len(sc["scramble_yards"]) >= 1:
                    outcomes.scramble_yards_dist = np.array(sc["scramble_yards"])
            else:
                # Fallback: no qb_scramble column, use all QB rushes (old behavior)
                qb_rush = rushing_stats[pid]["carries"] if pid in rushing_stats else 0
                qb_pass = qs["attempts"]
                total_qb_plays = qb_pass + qb_rush
                if total_qb_plays > 0:
                    usage.scramble_rate = qb_rush / total_qb_plays

            # QB pass fumble rate
            if qs["non_sack_attempts"] >= 100:
                outcomes.pass_fumble_rate = qs["non_sack_fumbles"] / qs["non_sack_attempts"]
            else:
                outcomes.pass_fumble_rate = 0.0034  # League average

        models[pid] = PlayerModel(
            player_id=pid,
            name=name,
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


def build_player_models(
    pbp: pl.DataFrame,
    current_rosters: pl.DataFrame,
    training_seasons: list[int],
    rookie_blend_games: int = 0,
) -> dict[str, PlayerModel]:
    """Build PlayerModels from PBP stats and current roster.

    Stats come from historical PBP (training_seasons). Team assignment
    comes from current_rosters. Players on the roster without PBP data
    get archetype (skill positions) or placeholder (kickers) models.
    """
    aggregated = _aggregate_pbp_stats(pbp, training_seasons)
    return _assemble_models(aggregated, current_rosters, rookie_blend_games)


def build_team_roster(team: str, models: dict[str, PlayerModel]) -> TeamRoster:
    """Build a TeamRoster from a dict of PlayerModels."""
    team_players = [m for m in models.values() if m.team == team]
    return TeamRoster(team=team, players=team_players)

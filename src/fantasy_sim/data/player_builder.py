"""Build PlayerModel objects from PBP and roster data."""

from copy import deepcopy

import polars as pl
import numpy as np
from fantasy_sim.config.loader import get_phase1_ks_flags
from fantasy_sim.models.player import PlayerModel, PlayerUsage, PlayerOutcomes, TeamRoster, MIN_QB_CARRY_SHARE
from fantasy_sim.data.rookie_builder import POSITIONAL_ARCHETYPES, build_rookie_model
from fantasy_sim.engine.play_resolver import RZ_CATCH_RATE_MODIFIERS, RZ_CATCH_RATE_MODIFIER

# KS-06 D-19 sub-fix 3 (Cycle 3 D-45 flag-gated): the canonical module
# constant is now 3 (the new path's value); the legacy threshold of 5 is
# preserved as `_KS06_LEGACY_MIN_PLAYER_PLAYS` so the flag-off path inside
# `_assemble_models` keeps Arm A bit-for-bit identical. Pre-Phase-1 callers
# that imported `MIN_PLAYER_PLAYS` directly will see 3, but the actual
# threshold used per call site is computed from the flag.
MIN_PLAYER_PLAYS = 3
_KS06_LEGACY_MIN_PLAYER_PLAYS = 5

# Phase 1 KS-06 feature flag (Cycle 3 D-45). Read once at module import; A/B
# arms are separate Python processes via fresh GameContextBuilder
# construction so this matches the rest of the Phase 1 KS flag-gated code
# paths.
_KS06_BACKUP_RECEIVER_FIX = (
    get_phase1_ks_flags()
    .get("ks06_backup_receiver_fix", {})
    .get("enabled", False)
)

MIN_RZ_TARGETS = 10  # Minimum RZ targets for per-player RZ catch rate
FANTASY_POSITIONS = {"QB", "RB", "WR", "TE", "K"}
ACTIVE_STATUSES = {"ACT"}
GOAL_LINE_MAX_YARDLINE = 5
OUTER_RZ_MIN_YARDLINE = 6
RED_ZONE_MAX_YARDLINE = 20


def _goal_line_expr() -> pl.Expr:
    return pl.col("yardline_100") <= GOAL_LINE_MAX_YARDLINE


def _outer_rz_expr() -> pl.Expr:
    return (
        (pl.col("yardline_100") >= OUTER_RZ_MIN_YARDLINE) &
        (pl.col("yardline_100") <= RED_ZONE_MAX_YARDLINE)
    )


def _red_zone_expr() -> pl.Expr:
    return pl.col("yardline_100") <= RED_ZONE_MAX_YARDLINE


def _is_goal_line_yardline(yardline_100: int | float | None) -> bool:
    return yardline_100 is not None and yardline_100 <= GOAL_LINE_MAX_YARDLINE


def _is_outer_rz_yardline(yardline_100: int | float | None) -> bool:
    return (
        yardline_100 is not None
        and OUTER_RZ_MIN_YARDLINE <= yardline_100 <= RED_ZONE_MAX_YARDLINE
    )


def _is_red_zone_yardline(yardline_100: int | float | None) -> bool:
    return yardline_100 is not None and yardline_100 <= RED_ZONE_MAX_YARDLINE


def _build_season_weights(
    training_seasons: list[int],
    recency_weights: list[float],
) -> dict[int, float]:
    """Align recency_weights list (oldest-to-newest) to training_seasons.

    Tail-aligns: takes last N weights where N = len(training_seasons).
    """
    n = len(training_seasons)
    aligned = recency_weights[-n:] if len(recency_weights) >= n else recency_weights
    return dict(zip(sorted(training_seasons), aligned))


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
    season_weights: dict[int, float] | None = None,
) -> dict:
    """Aggregate raw PBP data into per-player and per-team stat buckets.

    This is a pure data-extraction step — no PlayerModel objects are created.
    The result can be cached and reused across multiple roster merges.

    When *season_weights* is provided, rows are replicated proportional to
    weight (same pattern as ``Preprocessor._apply_season_weights``).  The max
    weight gets 10 replications; others are proportional (minimum 1).

    Returns a dict with keys:
        - receiving: dict[player_id -> {targets, catches, yards list, rz_targets, air_yards, team, game_ids set}]
        - rushing:   dict[player_id -> {carries, yards list, rz_carries, team, game_ids set}]
        - qb:        dict[player_id -> {attempts, team, game_ids set}]
        - team_pass_attempts:    dict[team -> int]
        - team_rush_attempts:    dict[team -> int]
        - team_rz_pass_attempts: dict[team -> int]
        - team_rz_rush_attempts: dict[team -> int]
        - team_outer_rz_pass_attempts: dict[team -> int]
        - team_goal_line_pass_attempts: dict[team -> int]
        - team_outer_rz_rush_attempts: dict[team -> int]
        - team_goal_line_rush_attempts: dict[team -> int]
        - team_air_yards:        dict[team -> float]
        - has_air_yards:         bool
    """
    plays = pbp.filter(
        pl.col("play_type").is_in(["pass", "run"]) &
        pl.col("season").is_in(training_seasons)
    )

    # Apply recency weighting via row replication (same pattern as Preprocessor)
    if season_weights:
        max_w = max(season_weights.values())
        if max_w > 0:
            frames: list[pl.DataFrame] = []
            for season in plays["season"].unique().to_list():
                sp = plays.filter(pl.col("season") == season)
                if sp.is_empty():
                    continue
                raw_w = season_weights.get(int(season), 0.0)
                reps = max(1, round((raw_w / max_w) * 10))
                frames.extend([sp] * reps)
            if frames:
                plays = pl.concat(frames)

    # --- Team-level totals ---
    team_pass_attempts: dict[str, int] = {}
    team_rush_attempts: dict[str, int] = {}
    team_rz_pass_attempts: dict[str, int] = {}
    team_rz_rush_attempts: dict[str, int] = {}
    team_outer_rz_pass_attempts: dict[str, int] = {}
    team_goal_line_pass_attempts: dict[str, int] = {}
    team_outer_rz_rush_attempts: dict[str, int] = {}
    team_goal_line_rush_attempts: dict[str, int] = {}
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
            _red_zone_expr()
        ).shape[0]
        team_rz_rush_attempts[team] = rush_plays_team.filter(
            _red_zone_expr()
        ).shape[0]
        team_goal_line_pass_attempts[team] = pass_plays_team.filter(
            _goal_line_expr()
        ).shape[0]
        team_outer_rz_pass_attempts[team] = pass_plays_team.filter(
            _outer_rz_expr()
        ).shape[0]
        team_goal_line_rush_attempts[team] = rush_plays_team.filter(
            _goal_line_expr()
        ).shape[0]
        team_outer_rz_rush_attempts[team] = rush_plays_team.filter(
            _outer_rz_expr()
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
                "outer_rz_targets": 0, "goal_line_targets": 0,
                "rz_tds": 0,
                "air_yards": 0.0,
                "team": row["posteam"], "game_ids": set(),
            }
        receiving_stats[rid]["targets"] += 1
        receiving_stats[rid]["game_ids"].add(row["game_id"])

        # Red zone target
        if _is_red_zone_yardline(row["yardline_100"]):
            receiving_stats[rid]["rz_targets"] += 1
            if row["complete_pass"] == 1:
                receiving_stats[rid]["rz_catches"] += 1
                receiving_stats[rid]["rz_yards"].append(row["yards_gained"])
            if row.get("pass_touchdown") == 1 or (row.get("touchdown") == 1 and row["complete_pass"] == 1):
                receiving_stats[rid]["rz_tds"] += 1
        if _is_goal_line_yardline(row["yardline_100"]):
            receiving_stats[rid]["goal_line_targets"] += 1
        elif _is_outer_rz_yardline(row["yardline_100"]):
            receiving_stats[rid]["outer_rz_targets"] += 1

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
                "carries": 0, "yards": [], "rz_carries": 0, "rz_tds": 0,
                "outer_rz_carries": 0, "goal_line_carries": 0,
                "i5_rush_carries": 0, "i5_rush_tds": 0,
                "team": row["posteam"], "game_ids": set(),
            }
        rushing_stats[rid]["carries"] += 1
        rushing_stats[rid]["yards"].append(row["yards_gained"])
        rushing_stats[rid]["game_ids"].add(row["game_id"])

        # Red zone carry
        if _is_red_zone_yardline(row["yardline_100"]):
            rushing_stats[rid]["rz_carries"] += 1
            if row.get("rush_touchdown") == 1:
                rushing_stats[rid]["rz_tds"] += 1
        if _is_goal_line_yardline(row["yardline_100"]):
            rushing_stats[rid]["goal_line_carries"] += 1
        elif _is_outer_rz_yardline(row["yardline_100"]):
            rushing_stats[rid]["outer_rz_carries"] += 1

        # Inside-5 carry
        if _is_goal_line_yardline(row["yardline_100"]):
            rushing_stats[rid]["i5_rush_carries"] += 1
            if row.get("rush_touchdown") == 1:
                rushing_stats[rid]["i5_rush_tds"] += 1

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
        "team_outer_rz_pass_attempts": team_outer_rz_pass_attempts,
        "team_goal_line_pass_attempts": team_goal_line_pass_attempts,
        "team_outer_rz_rush_attempts": team_outer_rz_rush_attempts,
        "team_goal_line_rush_attempts": team_goal_line_rush_attempts,
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
    team_outer_rz_pass_attempts = aggregated_stats["team_outer_rz_pass_attempts"]
    team_goal_line_pass_attempts = aggregated_stats["team_goal_line_pass_attempts"]
    team_outer_rz_rush_attempts = aggregated_stats["team_outer_rz_rush_attempts"]
    team_goal_line_rush_attempts = aggregated_stats["team_goal_line_rush_attempts"]
    team_air_yards = aggregated_stats["team_air_yards"]
    has_air_yards = aggregated_stats["has_air_yards"]
    qb_scrambles = aggregated_stats.get("qb_scrambles", {})
    has_qb_scramble = aggregated_stats.get("has_qb_scramble", False)

    # KS-06 D-19 sub-fix 3 (Cycle 3 D-45): pick the effective per-player-plays
    # threshold based on the flag. Module-level MIN_PLAYER_PLAYS = 3 is the
    # canonical new-path value; legacy is 5. Computing per-call ensures the
    # same Python process can host both arms without mutating the constant.
    effective_min_player_plays = (
        MIN_PLAYER_PLAYS
        if _KS06_BACKUP_RECEIVER_FIX
        else _KS06_LEGACY_MIN_PLAYER_PLAYS
    )

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
            team_outer_rz_pa = team_outer_rz_pass_attempts.get(hist_team, 0)
            if team_outer_rz_pa > 0:
                usage.outer_rz_target_share = rs["outer_rz_targets"] / team_outer_rz_pa
            team_goal_line_pa = team_goal_line_pass_attempts.get(hist_team, 0)
            if team_goal_line_pa > 0:
                usage.goal_line_target_share = rs["goal_line_targets"] / team_goal_line_pa

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
            team_outer_rz_ra = team_outer_rz_rush_attempts.get(hist_team, 0)
            if team_outer_rz_ra > 0:
                usage.outer_rz_carry_share = rs["outer_rz_carries"] / team_outer_rz_ra
            team_goal_line_ra = team_goal_line_rush_attempts.get(hist_team, 0)
            if team_goal_line_ra > 0:
                usage.goal_line_carry_share = rs["goal_line_carries"] / team_goal_line_ra

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
                # KS-07 D-20 (Cycle 3 D-45): when the flag is on, use the
                # position-aware modifier (WR=0.92, TE=0.95, RB=0.85);
                # unknown positions fall back to the WR rate. When the flag
                # is off, use the legacy scalar 0.92 for every position so
                # Arm A is bit-for-bit identical to pre-Phase-1 behavior.
                # The flag is read at module import in play_resolver.py
                # (`_KS07_POSITIONAL_RZ_CATCH_RATE`); we resolve it lazily
                # here so monkeypatch in tests applies cleanly to the live
                # value rather than a snapshot of the import-time bool.
                from fantasy_sim.engine import play_resolver as _pr
                if _pr._KS07_POSITIONAL_RZ_CATCH_RATE:
                    rz_modifier = RZ_CATCH_RATE_MODIFIERS.get(position, RZ_CATCH_RATE_MODIFIERS["WR"])
                else:
                    rz_modifier = RZ_CATCH_RATE_MODIFIER
                outcomes.red_zone_catch_rate = outcomes.catch_rate * rz_modifier
            if len(rs["yards"]) >= effective_min_player_plays:
                outcomes.receiving_yards_dist = np.array(rs["yards"])
            # Red zone receiving yards distribution (catches inside the 20)
            if len(rs["rz_yards"]) >= effective_min_player_plays:
                outcomes.rz_receiving_yards_dist = np.array(rs["rz_yards"])

        if pid in rushing_stats:
            rs = rushing_stats[pid]
            if position == "QB" and not has_qb_scramble and outcomes.scramble_yards_dist is None:
                # Fallback: no qb_scramble column, use all QB rush yards
                if len(rs["yards"]) >= 1:
                    outcomes.scramble_yards_dist = np.array(rs["yards"])
            elif position != "QB":
                if len(rs["yards"]) >= effective_min_player_plays:
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
    season_weights: dict[int, float] | None = None,
) -> dict[str, PlayerModel]:
    """Build PlayerModels from PBP stats and current roster.

    Stats come from historical PBP (training_seasons). Team assignment
    comes from current_rosters. Players on the roster without PBP data
    get archetype (skill positions) or placeholder (kickers) models.
    """
    aggregated = _aggregate_pbp_stats(pbp, training_seasons, season_weights=season_weights)
    return _assemble_models(aggregated, current_rosters, rookie_blend_games)


def build_team_roster(team: str, models: dict[str, PlayerModel]) -> TeamRoster:
    """Build a TeamRoster from a dict of PlayerModels.

    Players are deepcopied to prevent mutations (e.g. from overrides) from
    bleeding back into the shared model cache.  After copying, carry_shares
    and target_shares are normalized to sum to 1.0 among eligible players
    so that override values map directly to selection probability.
    """
    team_players = [deepcopy(m) for m in models.values() if m.team == team]
    roster = TeamRoster(team=team, players=team_players)
    _normalize_roster_shares(roster)
    return roster


def _normalize_roster_shares(roster: TeamRoster) -> None:
    """Normalize carry/target shares to sum to 1.0 among eligible players.

    Without this, shares computed from multi-season PBP data don't sum to 1.0
    (former players had carries/targets but aren't on the current roster).
    The gap causes ``select_rusher``/``select_receiver`` to amplify each
    player's selection probability beyond the intended share value.
    """
    # --- Carry shares ---
    eligible_rushers = [
        p for p in roster.players
        if p.usage.carry_share > 0
        and (p.position != "QB" or p.usage.carry_share >= MIN_QB_CARRY_SHARE)
    ]
    _scale_shares(eligible_rushers, "carry_share")

    # --- Red zone carry shares ---
    eligible_rz_rushers = [
        p for p in roster.players
        if p.usage.red_zone_carry_share > 0
        and (p.position != "QB" or p.usage.carry_share >= MIN_QB_CARRY_SHARE)
    ]
    _scale_shares(eligible_rz_rushers, "red_zone_carry_share")

    # --- Outer red zone carry shares ---
    eligible_outer_rz_rushers = [
        p for p in roster.players
        if p.usage.outer_rz_carry_share > 0
        and (p.position != "QB" or p.usage.carry_share >= MIN_QB_CARRY_SHARE)
    ]
    _scale_shares(eligible_outer_rz_rushers, "outer_rz_carry_share")

    # --- Goal line carry shares ---
    eligible_goal_line_rushers = [
        p for p in roster.players
        if p.usage.goal_line_carry_share > 0
        and (p.position != "QB" or p.usage.carry_share >= MIN_QB_CARRY_SHARE)
    ]
    _scale_shares(eligible_goal_line_rushers, "goal_line_carry_share")

    # --- Target shares ---
    eligible_receivers = [
        p for p in roster.players if p.usage.target_share > 0
    ]
    _scale_shares(eligible_receivers, "target_share")

    # --- Red zone target shares ---
    eligible_rz_receivers = [
        p for p in roster.players if p.usage.red_zone_target_share > 0
    ]
    _scale_shares(eligible_rz_receivers, "red_zone_target_share")

    # --- Outer red zone target shares ---
    eligible_outer_rz_receivers = [
        p for p in roster.players if p.usage.outer_rz_target_share > 0
    ]
    _scale_shares(eligible_outer_rz_receivers, "outer_rz_target_share")

    # --- Goal line target shares ---
    eligible_goal_line_receivers = [
        p for p in roster.players if p.usage.goal_line_target_share > 0
    ]
    _scale_shares(eligible_goal_line_receivers, "goal_line_target_share")


def _scale_shares(players: list[PlayerModel], attr: str) -> None:
    """Scale a usage share attribute so the values sum to 1.0."""
    if not players:
        return
    total = sum(getattr(p.usage, attr) for p in players)
    if total <= 0 or abs(total - 1.0) < 1e-9:
        return
    factor = 1.0 / total
    for p in players:
        setattr(p.usage, attr, getattr(p.usage, attr) * factor)

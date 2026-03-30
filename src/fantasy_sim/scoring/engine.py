from fantasy_sim.engine.types import PlayerBoxScore, TeamBoxScore

_YARDAGE_BONUSES = [
    ("rush_yards", "rushing_bonus_", [100, 200]),
    ("receiving_yards", "receiving_bonus_", [100, 200]),
    ("pass_yards", "passing_bonus_", [300, 400, 500]),
]


def score_player(box: PlayerBoxScore, config: dict) -> float:
    """Calculate fantasy points for an offensive player (QB/RB/WR/TE)."""
    points = 0.0
    points += box.pass_yards * config.get("passing_yard", 0)
    points += box.pass_tds * config.get("passing_td", 0)
    points += box.interceptions * config.get("interception", 0)
    points += box.rush_yards * config.get("rushing_yard", 0)
    points += box.rush_tds * config.get("rushing_td", 0)
    pos_key = f"reception_{box.position.lower()}"
    reception_value = config.get(pos_key, config.get("reception", 0))
    points += box.receptions * reception_value
    points += box.receiving_yards * config.get("receiving_yard", 0)
    points += box.receiving_tds * config.get("receiving_td", 0)
    points += box.fumbles_lost * config.get("fumble_lost", 0)
    points += box.two_point_conversions * config.get("two_point", 0)
    for stat_attr, config_prefix, thresholds in _YARDAGE_BONUSES:
        stat_value = getattr(box, stat_attr, 0)
        for threshold in thresholds:
            bonus_key = f"{config_prefix}{threshold}"
            if stat_value >= threshold and bonus_key in config:
                points += config[bonus_key]
    return points


def score_dst(box: TeamBoxScore, opponent_score: int, config: dict) -> float:
    """Calculate fantasy points for a team defense/special teams."""
    points = 0.0
    points += box.sacks_made * config.get("dst_sack", 0)
    # dst_td not yet tracked in TeamBoxScore (no defensive TD attribution in engine)
    points += box.interceptions_caught * config.get("dst_interception", 0)
    points += box.fumbles_recovered * config.get("dst_fumble_recovery", 0)
    points += box.safeties * config.get("dst_safety", 0)

    if opponent_score == 0:
        points += config.get("dst_points_allowed_0", 0)
    elif opponent_score <= 6:
        points += config.get("dst_points_allowed_1_6", 0)
    elif opponent_score <= 13:
        points += config.get("dst_points_allowed_7_13", 0)
    elif opponent_score <= 20:
        points += config.get("dst_points_allowed_14_20", 0)
    elif opponent_score <= 27:
        points += config.get("dst_points_allowed_21_27", 0)
    elif opponent_score <= 34:
        points += config.get("dst_points_allowed_28_34", 0)
    else:
        points += config.get("dst_points_allowed_35_plus", 0)

    return points


def score_kicker(box: TeamBoxScore, config: dict) -> float:
    """Calculate fantasy points for a kicker from team-level kicking stats."""
    points = 0.0
    points += box.fg_made_0_39 * config.get("fg_0_39", 0)
    points += box.fg_made_40_49 * config.get("fg_40_49", 0)
    points += box.fg_made_50_plus * config.get("fg_50_plus", 0)
    points += box.xp_made * config.get("xp_made", 0)
    points += box.fg_missed * config.get("fg_miss", 0)
    return points

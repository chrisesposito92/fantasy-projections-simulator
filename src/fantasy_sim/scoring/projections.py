from collections import defaultdict
import numpy as np
from fantasy_sim.engine.types import GameResult, PlayerBoxScore
from fantasy_sim.scoring.engine import score_player, score_dst


def build_player_projections(
    games: list[GameResult], scoring_config: dict
) -> list[dict]:
    """Aggregate player stats across games and compute fantasy points.

    Averages over total number of sims (not just sims where the player
    appeared), so players with fewer touches are not overstated.

    Returns list of projection dicts sorted by fpts descending.
    """
    if not games:
        return []

    n_games = len(games)
    player_games: dict[str, list[PlayerBoxScore]] = defaultdict(list)
    for game in games:
        for pid, box in game.player_stats.items():
            player_games[pid].append(box)

    projections = []
    for pid, boxes in player_games.items():
        if not boxes:
            continue
        first = boxes[0]

        # Average over ALL sims, treating missing appearances as zero
        fpts_total = sum(score_player(b, scoring_config) for b in boxes)

        proj = {
            "player_id": pid,
            "name": first.name,
            "position": first.position,
            "team": first.team,
            "fpts": round(float(fpts_total / n_games), 1),
            "pass_yards": round(float(sum(b.pass_yards for b in boxes) / n_games), 1),
            "pass_tds": round(float(sum(b.pass_tds for b in boxes) / n_games), 1),
            "interceptions": round(float(sum(b.interceptions for b in boxes) / n_games), 1),
            "sacks": round(float(sum(b.sacks for b in boxes) / n_games), 1),
            "rush_yards": round(float(sum(b.rush_yards for b in boxes) / n_games), 1),
            "rush_tds": round(float(sum(b.rush_tds for b in boxes) / n_games), 1),
            "targets": round(float(sum(b.targets for b in boxes) / n_games), 1),
            "receptions": round(float(sum(b.receptions for b in boxes) / n_games), 1),
            "receiving_yards": round(float(sum(b.receiving_yards for b in boxes) / n_games), 1),
            "receiving_tds": round(float(sum(b.receiving_tds for b in boxes) / n_games), 1),
            "fumbles_lost": round(float(sum(b.fumbles_lost for b in boxes) / n_games), 1),
        }
        projections.append(proj)

    projections.sort(key=lambda p: p["fpts"], reverse=True)

    for i, p in enumerate(projections, 1):
        p["rank"] = i

    return projections


def build_dst_projections(
    games: list[GameResult],
    scoring_config: dict,
    team_map: dict[str, str] | None = None,
) -> list[dict]:
    """Build DST projections from game results."""
    if not games:
        return []

    home_boxes = [g.home_box for g in games]
    away_boxes = [g.away_box for g in games]
    home_scores = [g.home_score for g in games]
    away_scores = [g.away_score for g in games]

    projections = []

    # Home DST (defends against away team)
    home_fpts = [score_dst(hb, as_, scoring_config) for hb, as_ in zip(home_boxes, away_scores)]
    home_name = team_map.get("HOME", "HOME") if team_map else "HOME"
    projections.append({
        "team": home_name,
        "fpts": round(float(np.mean(home_fpts)), 1),
        "sacks": round(float(np.mean([b.sacks_made for b in home_boxes])), 1),
        "interceptions": round(float(np.mean([b.interceptions_caught for b in home_boxes])), 1),
        "fumble_recoveries": round(float(np.mean([b.fumbles_recovered for b in home_boxes])), 1),
        "dst_tds": 0.0,  # Not tracked yet
        "safeties": round(float(np.mean([b.safeties for b in home_boxes])), 1),
        "points_allowed": round(float(np.mean(away_scores)), 1),
    })

    # Away DST
    away_fpts = [score_dst(ab, hs, scoring_config) for ab, hs in zip(away_boxes, home_scores)]
    away_name = team_map.get("AWAY", "AWAY") if team_map else "AWAY"
    projections.append({
        "team": away_name,
        "fpts": round(float(np.mean(away_fpts)), 1),
        "sacks": round(float(np.mean([b.sacks_made for b in away_boxes])), 1),
        "interceptions": round(float(np.mean([b.interceptions_caught for b in away_boxes])), 1),
        "fumble_recoveries": round(float(np.mean([b.fumbles_recovered for b in away_boxes])), 1),
        "dst_tds": 0.0,
        "safeties": round(float(np.mean([b.safeties for b in away_boxes])), 1),
        "points_allowed": round(float(np.mean(home_scores)), 1),
    })

    projections.sort(key=lambda p: p["fpts"], reverse=True)
    for i, p in enumerate(projections, 1):
        p["rank"] = i

    return projections

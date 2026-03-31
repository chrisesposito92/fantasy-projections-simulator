"""Build PlayerModel objects for rookies using draft-capital-based archetypes."""

import numpy as np
from fantasy_sim.models.player import PlayerModel, PlayerUsage, PlayerOutcomes

# Positional archetypes by draft round tier
# Tier 1: Rounds 1-2, Tier 2: Rounds 3-4, Tier 3: Rounds 5-7
POSITIONAL_ARCHETYPES = {
    "QB": {
        "tier1": {"snap_share": 0.70, "scramble_rate": 0.06,
                  "scramble_yards": [3, 5, 8, 12, -1, 2, 15],
                  "fumble_rate": 0.012},
        "tier2": {"snap_share": 0.20, "scramble_rate": 0.05,
                  "scramble_yards": [2, 4, 6, 8, -1, 1],
                  "fumble_rate": 0.015},
        "tier3": {"snap_share": 0.05, "scramble_rate": 0.04,
                  "scramble_yards": [1, 3, 5, -1],
                  "fumble_rate": 0.018},
    },
    "RB": {
        "tier1": {"carry_share": 0.45, "target_share": 0.08,
                  "rush_yards": [-2, 0, 1, 2, 3, 3, 4, 4, 5, 5, 6, 7, 8, 10, 15],
                  "rec_yards": [3, 5, 7, 10, 4, 6],
                  "catch_rate": 0.70, "fumble_rate": 0.012},
        "tier2": {"carry_share": 0.25, "target_share": 0.05,
                  "rush_yards": [-1, 0, 1, 2, 3, 3, 4, 4, 5, 6, 7, 8],
                  "rec_yards": [3, 4, 5, 7],
                  "catch_rate": 0.65, "fumble_rate": 0.015},
        "tier3": {"carry_share": 0.10, "target_share": 0.02,
                  "rush_yards": [-1, 0, 1, 2, 3, 4, 5, 6],
                  "rec_yards": [2, 4, 6],
                  "catch_rate": 0.60, "fumble_rate": 0.018},
    },
    "WR": {
        "tier1": {"target_share": 0.18, "red_zone_target_share": 0.15,
                  "rec_yards": [3, 5, 7, 8, 10, 12, 14, 15, 18, 20, 25, 30, 40],
                  "catch_rate": 0.60, "fumble_rate": 0.005},
        "tier2": {"target_share": 0.10, "red_zone_target_share": 0.08,
                  "rec_yards": [3, 5, 7, 8, 10, 12, 15, 18, 20],
                  "catch_rate": 0.58, "fumble_rate": 0.006},
        "tier3": {"target_share": 0.03, "red_zone_target_share": 0.02,
                  "rec_yards": [3, 5, 7, 8, 10, 12, 15],
                  "catch_rate": 0.55, "fumble_rate": 0.008},
    },
    "TE": {
        "tier1": {"target_share": 0.12, "red_zone_target_share": 0.15,
                  "rec_yards": [3, 5, 6, 8, 10, 12, 15, 18],
                  "catch_rate": 0.65, "fumble_rate": 0.005},
        "tier2": {"target_share": 0.06, "red_zone_target_share": 0.08,
                  "rec_yards": [3, 5, 6, 8, 10, 12],
                  "catch_rate": 0.62, "fumble_rate": 0.006},
        "tier3": {"target_share": 0.02, "red_zone_target_share": 0.03,
                  "rec_yards": [3, 4, 5, 7, 8],
                  "catch_rate": 0.58, "fumble_rate": 0.008},
    },
}


def _get_tier(draft_round: int) -> str:
    """Map draft round to archetype tier."""
    if draft_round <= 2:
        return "tier1"
    elif draft_round <= 4:
        return "tier2"
    return "tier3"


def build_rookie_model(
    player_id: str,
    name: str,
    position: str,
    team: str,
    draft_round: int,
) -> PlayerModel:
    """Generate a PlayerModel for a rookie based on draft capital archetypes."""
    tier = _get_tier(draft_round)
    archetype = POSITIONAL_ARCHETYPES[position][tier]

    usage = PlayerUsage()
    outcomes = PlayerOutcomes()

    if position == "QB":
        usage.snap_share = archetype["snap_share"]
        usage.scramble_rate = archetype["scramble_rate"]
        outcomes.scramble_yards_dist = np.array(archetype["scramble_yards"])
        outcomes.fumble_rate = archetype["fumble_rate"]
        outcomes.pass_fumble_rate = 0.0034  # League average
    elif position == "RB":
        usage.carry_share = archetype["carry_share"]
        usage.target_share = archetype["target_share"]
        outcomes.rushing_yards_dist = np.array(archetype["rush_yards"])
        outcomes.receiving_yards_dist = np.array(archetype["rec_yards"])
        outcomes.catch_rate = archetype["catch_rate"]
        outcomes.fumble_rate = archetype["fumble_rate"]
        outcomes.red_zone_catch_rate = archetype["catch_rate"] * 0.85
    elif position in ("WR", "TE"):
        usage.target_share = archetype["target_share"]
        usage.red_zone_target_share = archetype.get("red_zone_target_share", 0.0)
        outcomes.receiving_yards_dist = np.array(archetype["rec_yards"])
        outcomes.catch_rate = archetype["catch_rate"]
        outcomes.fumble_rate = archetype["fumble_rate"]
        outcomes.red_zone_catch_rate = archetype["catch_rate"] * 0.85

    return PlayerModel(
        player_id=player_id, name=name, position=position, team=team,
        usage=usage, outcomes=outcomes,
    )

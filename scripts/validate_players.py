"""Validate player-level simulation output is plausible.

Run: uv run python scripts/validate_players.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import numpy as np
from fantasy_sim.engine.monte_carlo import run_simulations
from fantasy_sim.engine.types import TeamDistributions
from fantasy_sim.models.distributions import (
    PlayCallingDist, PlayOutcomeDist, TurnoverRates, KickingModel, DriveStartModel,
)
from fantasy_sim.models.player import PlayerModel, PlayerUsage, PlayerOutcomes, TeamRoster


def make_roster(team):
    qb = PlayerModel(f"{team}_QB", "QB1", "QB", team,
                     PlayerUsage(snap_share=1.0, scramble_rate=0.06),
                     PlayerOutcomes(scramble_yards_dist=np.array([2, 4, 6, 8, 12, -2, 3, 5])))
    wr1 = PlayerModel(f"{team}_WR1", "WR1", "WR", team,
                      PlayerUsage(target_share=0.24),
                      PlayerOutcomes(catch_rate=0.63, receiving_yards_dist=np.array([5, 7, 8, 10, 12, 14, 16, 20, 25, 35])))
    wr2 = PlayerModel(f"{team}_WR2", "WR2", "WR", team,
                      PlayerUsage(target_share=0.18),
                      PlayerOutcomes(catch_rate=0.60, receiving_yards_dist=np.array([5, 7, 9, 11, 13, 17, 22])))
    te = PlayerModel(f"{team}_TE", "TE1", "TE", team,
                     PlayerUsage(target_share=0.16),
                     PlayerOutcomes(catch_rate=0.67, receiving_yards_dist=np.array([4, 6, 8, 10, 12, 15])))
    rb1 = PlayerModel(f"{team}_RB1", "RB1", "RB", team,
                      PlayerUsage(carry_share=0.60, target_share=0.10),
                      PlayerOutcomes(
                          rushing_yards_dist=np.array([-2, 0, 1, 2, 3, 3, 4, 4, 5, 5, 6, 7, 8, 10, 15, 20]),
                          catch_rate=0.72, receiving_yards_dist=np.array([3, 5, 7, 4]),
                          fumble_rate=0.008,
                      ))
    rb2 = PlayerModel(f"{team}_RB2", "RB2", "RB", team,
                      PlayerUsage(carry_share=0.30, target_share=0.05),
                      PlayerOutcomes(
                          rushing_yards_dist=np.array([0, 1, 2, 3, 4, 5, 6, 7]),
                          catch_rate=0.65, receiving_yards_dist=np.array([3, 5]),
                      ))
    return TeamRoster(team=team, players=[qb, wr1, wr2, te, rb1, rb2])


def main():
    n_sims = 1000
    print(f"Running {n_sims} simulated games with player models...")

    dists = TeamDistributions(
        play_calling=PlayCallingDist(team="T", distributions={}, default={"pass": 0.57, "run": 0.43}),
        play_outcomes=PlayOutcomeDist(distributions={}, defaults={
            "pass": np.array([0, 0, 0, 0, 5, 7, 8, 10, 12, 15, 20, 25, 30]),
            "run": np.array([-2, 0, 1, 2, 3, 3, 4, 4, 5, 6, 7, 8, 12]),
        }),
        turnover_rates=TurnoverRates(team="T", int_rate=0.025, fumble_rate=0.012, sack_rate=0.065, sack_fumble_rate=0.10),
        kicking=KickingModel(fg_make_rate={"0_39": 0.93, "40_49": 0.82, "50_plus": 0.65}, xp_rate=0.94),
        drive_start=DriveStartModel(touchback_rate=0.55, touchback_yardline=75, return_yardlines=np.array([72, 74, 76, 78, 80])),
    )

    results = run_simulations(dists, dists, n_sims=n_sims, seed=42,
                              home_roster=make_roster("H"), away_roster=make_roster("A"))
    ps = results.player_summary()

    print(f"\n--- Player Averages (Home Team, {n_sims} games) ---")
    for pid in ["H_QB", "H_WR1", "H_WR2", "H_TE", "H_RB1", "H_RB2"]:
        if pid not in ps:
            continue
        s = ps[pid]
        parts = []
        if s.get("pass_yards", {}).get("mean", 0) > 0:
            parts.append(f"PassYd={s['pass_yards']['mean']:.0f}")
            parts.append(f"PassTD={s['pass_tds']['mean']:.1f}")
        if s.get("rush_yards", {}).get("mean", 0) > 0:
            parts.append(f"RushYd={s['rush_yards']['mean']:.0f}")
            parts.append(f"RushTD={s['rush_tds']['mean']:.1f}")
        if s.get("targets", {}).get("mean", 0) > 0:
            parts.append(f"Tgt={s['targets']['mean']:.1f}")
            parts.append(f"Rec={s['receptions']['mean']:.1f}")
            parts.append(f"RecYd={s['receiving_yards']['mean']:.0f}")
            parts.append(f"RecTD={s['receiving_tds']['mean']:.1f}")
        print(f"  {pid:10s} {', '.join(parts)}")

    print("\n=== PLAYER VALIDATION COMPLETE ===")


if __name__ == "__main__":
    main()

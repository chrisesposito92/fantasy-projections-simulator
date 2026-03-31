"""Validate that the simulation engine produces realistic NFL game statistics.

Run: uv run python scripts/validate_sim.py
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


def make_league_avg_dists() -> TeamDistributions:
    return TeamDistributions(
        play_calling=PlayCallingDist(team="AVG", distributions={}, default={"pass": 0.57, "run": 0.43}),
        play_outcomes=PlayOutcomeDist(
            distributions={},
            defaults={
                "pass": np.array([0, 0, 0, 0, 0, 0, 3, 4, 5, 6, 7, 8, 9, 10, 12, 15, 18, 20, 25, 30, 40, 50]),
                "run": np.array([-3, -2, -1, 0, 1, 1, 2, 2, 3, 3, 3, 4, 4, 4, 5, 5, 6, 7, 8, 10, 12, 15, 20]),
            },
        ),
        turnover_rates=TurnoverRates(team="AVG", int_rate=0.025, fumble_rate=0.012, sack_rate=0.065, sack_fumble_rate=0.10),
        kicking=KickingModel(fg_make_rate={"0_39": 0.93, "40_49": 0.82, "50_plus": 0.65}, xp_rate=0.94),
        drive_start=DriveStartModel(touchback_rate=0.55, touchback_yardline=75, return_yardlines=np.array([72, 74, 76, 78, 80, 82])),
    )


def main():
    n_sims = 5000
    print(f"Running {n_sims} simulated games...")
    dists = make_league_avg_dists()
    results = run_simulations(dists, dists, n_sims=n_sims, seed=42)
    s = results.summary()

    print(f"\n--- Simulation Results ({n_sims} games) ---")
    print(f"  Avg total points:    {s['total_score_mean']:.1f} (±{s['total_score_std']:.1f})")
    print(f"  Avg home score:      {s['home_score_mean']:.1f}")
    print(f"  Avg away score:      {s['away_score_mean']:.1f}")
    print(f"  Home win %:          {s['home_win_pct']:.1%}")
    print(f"  Tie %:               {s['tie_pct']:.1%}")
    print(f"  Overtime %:          {s['overtime_pct']:.1%}")
    print(f"  Avg plays/game:      {s['plays_mean']:.0f} (±{s['plays_std']:.0f})")

    # Compute additional stats
    avg_pass_att = np.mean([g.home_box.pass_attempts + g.away_box.pass_attempts for g in results.games])
    avg_rush_att = np.mean([g.home_box.rush_attempts + g.away_box.rush_attempts for g in results.games])
    avg_pass_yds = np.mean([g.home_box.pass_yards + g.away_box.pass_yards for g in results.games])
    avg_rush_yds = np.mean([g.home_box.rush_yards + g.away_box.rush_yards for g in results.games])
    avg_turnovers = np.mean([
        g.home_box.interceptions_thrown + g.away_box.interceptions_thrown +
        g.home_box.fumbles_lost + g.away_box.fumbles_lost
        for g in results.games
    ])

    avg_completions = np.mean([g.home_box.completions + g.away_box.completions for g in results.games])
    avg_sacks = np.mean([g.home_box.sacks_taken + g.away_box.sacks_taken for g in results.games])
    nfl_att = avg_pass_att - avg_sacks  # NFL convention excludes sacks
    avg_comp_rate = avg_completions / nfl_att if nfl_att > 0 else 0
    avg_ypc = avg_pass_yds / avg_completions if avg_completions > 0 else 0

    print(f"\n--- Detailed Stats ---")
    print(f"  Avg pass attempts:   {avg_pass_att:.0f}")
    print(f"  Avg completions:     {avg_completions:.0f}")
    print(f"  Avg sacks:           {avg_sacks:.0f}")
    print(f"  Completion rate:     {avg_comp_rate:.1%}")
    print(f"  Yards/completion:    {avg_ypc:.1f}")
    print(f"  Avg rush attempts:   {avg_rush_att:.0f}")
    print(f"  Avg pass yards:      {avg_pass_yds:.0f}")
    print(f"  Avg rush yards:      {avg_rush_yds:.0f}")
    print(f"  Avg turnovers/game:  {avg_turnovers:.1f}")

    print(f"\n--- Sanity Checks ---")
    checks_passed = 0
    checks_total = 5

    if 30 <= s["total_score_mean"] <= 65:
        print(f"  PASS: Total points in range")
        checks_passed += 1
    else:
        print(f"  FAIL: Total points {s['total_score_mean']:.1f} out of range [30-65]")

    if 0.40 <= s["home_win_pct"] <= 0.60:
        print(f"  PASS: Home win rate in range")
        checks_passed += 1
    else:
        print(f"  FAIL: Home win rate {s['home_win_pct']:.1%} out of range [40-60%]")

    if 0.01 <= s["overtime_pct"] <= 0.15:
        print(f"  PASS: OT rate in range")
        checks_passed += 1
    else:
        print(f"  FAIL: OT rate {s['overtime_pct']:.1%} out of range [1-15%]")

    if 80 <= s["plays_mean"] <= 200:
        print(f"  PASS: Plays per game in range")
        checks_passed += 1
    else:
        print(f"  FAIL: Plays/game {s['plays_mean']:.0f} out of range [80-200]")

    if 1.0 <= avg_turnovers <= 8.0:
        print(f"  PASS: Turnovers in range")
        checks_passed += 1
    else:
        print(f"  FAIL: Turnovers {avg_turnovers:.1f} out of range [1-8]")

    print(f"\n=== {checks_passed}/{checks_total} SANITY CHECKS PASSED ===")


if __name__ == "__main__":
    main()

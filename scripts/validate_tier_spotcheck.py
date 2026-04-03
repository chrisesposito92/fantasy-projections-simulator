#!/usr/bin/env python
"""Spot-check 10 players: compare projections with tier engine ON vs OFF.

Usage:
    uv run python scripts/validate_tier_spotcheck.py --sims 100
"""

import argparse
import sys

import numpy as np

from fantasy_sim.config.loader import load_defaults
from fantasy_sim.data.game_context import GameContextBuilder
from fantasy_sim.data.pff.models import PffConfig, TalentConfig, TierConfig


# Volume-inflated players (expected to DROP in rank)
VOLUME_INFLATED = [
    "tony_pollard",
    "jerry_jeudy",
    "rachaad_white",
    "jakobi_meyers",
    "raheem_mostert",
]

# Talent-deflated players (expected to RISE in rank)
TALENT_DEFLATED = [
    "jahmyr_gibbs",
    # Identify 4 more during implementation by scanning for
    # players with pff_tier <= 2 but pbp_projected_rank >= 15
]


def run_projections(pff_config: PffConfig, season: int, n_sims: int) -> dict:
    """Run full-season projections and return {player_id: (rank, fpts_per_week)}.

    TODO: Implement using the backtest pipeline:
    1. Create GameContextBuilder with the given pff_config
    2. Iterate all real matchups for the test season
    3. Run monte_carlo_sim for each game
    4. Build player projections via build_player_projections
    5. Return ranked results as {player_id: (position_rank, avg_fpts)}
    """
    raise NotImplementedError(
        f"run_projections() is a stub — implement the backtest pipeline "
        f"(season={season}, n_sims={n_sims}, "
        f"tier_engine={'ON' if pff_config.tier_engine.enabled else 'OFF'})"
    )


def main():
    parser = argparse.ArgumentParser(description="Tier engine spot-check")
    parser.add_argument("--season", type=int, default=2024)
    parser.add_argument("--sims", type=int, default=100)
    args = parser.parse_args()

    print("=" * 88)
    print("  TIER ENGINE SPOT-CHECK")
    print(f"  season: {args.season}    sims: {args.sims}")
    print("=" * 88)

    print("\nRunning baseline (talent stabilizer)...")
    baseline_config = PffConfig(
        enabled=True,
        talent=TalentConfig(enabled=True),
        tier_engine=TierConfig(enabled=False),
    )
    baseline = run_projections(baseline_config, args.season, args.sims)

    print("Running tier engine...")
    tier_config = PffConfig(
        enabled=True,
        talent=TalentConfig(enabled=False),
        tier_engine=TierConfig(enabled=True),
    )
    tier_results = run_projections(tier_config, args.season, args.sims)

    # Print comparison table
    print()
    header = (f"{'Player':<20} {'Base Rank':<12} {'Base FPts':<12} "
              f"{'Tier Rank':<12} {'Tier FPts':<12} {'Delta Rank':<12} {'OK?'}")
    print(header)
    print("-" * len(header))

    correct = 0
    total = 0

    for label, players, expected_dir in [
        ("VOLUME-INFLATED (should drop):", VOLUME_INFLATED, "down"),
        ("TALENT-DEFLATED (should rise):", TALENT_DEFLATED, "up"),
    ]:
        print(f"\n{label}")
        for pid in players:
            b = baseline.get(pid, (999, 0.0))
            t = tier_results.get(pid, (999, 0.0))
            delta = t[0] - b[0]
            if expected_dir == "down":
                ok = delta > 0
            else:
                ok = delta < 0
            correct += ok
            total += 1
            mark = "Y" if ok else "N"
            print(f"  {pid:<18} {b[0]:<12} {b[1]:<12.1f} "
                  f"{t[0]:<12} {t[1]:<12.1f} {delta:>+10}    {mark}")

    print(f"\nResult: {correct}/{total} correct direction "
          f"{'-> PASS' if correct >= 8 else '-> FAIL'} (threshold: 8/10)")


if __name__ == "__main__":
    main()

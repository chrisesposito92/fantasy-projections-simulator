"""Sanity-check preprocessed distributions against known NFL averages.

Run: uv run python scripts/validate_data.py
Requires network access to download nflverse data on first run.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from fantasy_sim.data.loader import DataLoader
from fantasy_sim.data.preprocessor import Preprocessor


def main():
    seasons = [2022, 2023, 2024]
    print(f"Loading PBP data for seasons {seasons}...")
    loader = DataLoader()
    pbp = loader.load_pbp(seasons)
    print(f"  Loaded {pbp.shape[0]:,} plays")

    pre = Preprocessor()

    print("\n--- Play-Calling Distributions ---")
    dists = pre.compute_play_calling(pbp)
    pass_rates = [d.default["pass"] for d in dists.values()]
    avg_pass_rate = sum(pass_rates) / len(pass_rates)
    print(f"  League avg pass rate: {avg_pass_rate:.1%}")
    assert 0.50 <= avg_pass_rate <= 0.65, f"Pass rate {avg_pass_rate:.1%} out of expected range (50-65%)"
    print("  PASS: Pass rate in expected range (50-65%)")

    print("\n--- Play Outcome Distributions ---")
    outcomes = pre.compute_play_outcomes(pbp)
    avg_pass_yards = outcomes.defaults["pass"].mean()
    avg_run_yards = outcomes.defaults["run"].mean()
    print(f"  Avg yards per pass attempt: {avg_pass_yards:.1f}")
    print(f"  Avg yards per rush attempt: {avg_run_yards:.1f}")
    assert 4.0 <= avg_pass_yards <= 9.0, f"Pass yards {avg_pass_yards:.1f} out of range"
    assert 3.0 <= avg_run_yards <= 6.0, f"Run yards {avg_run_yards:.1f} out of range"
    print("  PASS: Yards per attempt in expected ranges")

    print("\n--- Turnover Rates ---")
    rates = pre.compute_turnover_rates(pbp)
    avg_int_rate = sum(r.int_rate for r in rates.values()) / len(rates)
    avg_sack_rate = sum(r.sack_rate for r in rates.values()) / len(rates)
    avg_fumble_rate = sum(r.fumble_rate for r in rates.values()) / len(rates)
    print(f"  League avg INT rate: {avg_int_rate:.1%}")
    print(f"  League avg sack rate: {avg_sack_rate:.1%}")
    print(f"  League avg fumble rate: {avg_fumble_rate:.1%}")
    assert 0.01 <= avg_int_rate <= 0.05, f"INT rate {avg_int_rate:.1%} out of range"
    assert 0.03 <= avg_sack_rate <= 0.10, f"Sack rate {avg_sack_rate:.1%} out of range"
    print("  PASS: Turnover rates in expected ranges")

    print("\n--- Kicking Model ---")
    fg_plays = pbp.filter(pbp["play_type"] == "field_goal")
    kicking = pre.compute_kicking_model(fg_plays)
    print(f"  FG make rate 0-39: {kicking.fg_make_rate['0_39']:.1%}")
    print(f"  FG make rate 40-49: {kicking.fg_make_rate['40_49']:.1%}")
    print(f"  FG make rate 50+: {kicking.fg_make_rate['50_plus']:.1%}")
    assert kicking.fg_make_rate["0_39"] > kicking.fg_make_rate["40_49"] > kicking.fg_make_rate["50_plus"]
    print("  PASS: FG rates decrease with distance")

    print("\n--- Drive Start Model ---")
    ko_plays = pbp.filter(pbp["play_type"] == "kickoff")
    drive_start = pre.compute_drive_start_model(ko_plays)
    print(f"  Touchback rate: {drive_start.touchback_rate:.1%}")
    print(f"  Touchback yardline: own {100 - drive_start.touchback_yardline}")
    print(f"  Avg return start: own {100 - drive_start.return_yardlines.mean():.0f}")
    assert 0.30 <= drive_start.touchback_rate <= 0.80
    print("  PASS: Touchback rate in expected range")

    print("\n=== ALL SANITY CHECKS PASSED ===")


if __name__ == "__main__":
    main()

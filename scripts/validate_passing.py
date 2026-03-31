"""Diagnose passing yards accuracy: measures completion rate, yards/completion,
pass volume, scrambles, sacks, and compares to real NFL targets.

Run (demo only, no network):  uv run python scripts/validate_passing.py
Run (with real data):         uv run python scripts/validate_passing.py --real
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import argparse
import numpy as np
from fantasy_sim.engine.monte_carlo import run_simulations
from fantasy_sim.engine.types import TeamDistributions, GameResult
from fantasy_sim.models.distributions import (
    PlayCallingDist, PlayOutcomeDist, TurnoverRates, KickingModel, DriveStartModel,
)
from fantasy_sim.models.player import PlayerModel, PlayerUsage, PlayerOutcomes, TeamRoster


# --- NFL target ranges (league average per team per game) ---
NFL_TARGETS = {
    "plays_per_team":       (63, 65,   "plays/team/game"),
    "called_passes":        (37, 40,   "called pass plays/team (inc scrambles)"),
    "scrambles":            (1.5, 3.5, "scrambles/team/game"),
    "sacks":                (1.5, 3.0, "sacks/team/game"),
    "nfl_pass_attempts":    (32, 37,   "NFL-conv pass attempts (excl sacks)"),
    "completions":          (20, 24,   "completions/team/game"),
    "completion_rate":      (0.62, 0.67, "completion rate (NFL conv)"),
    "yards_per_completion": (10.5, 12.5, "yards/completion"),
    "pass_yards":           (210, 250, "pass yards/team/game"),
}


def make_demo_roster(team: str) -> TeamRoster:
    return TeamRoster(team=team, players=[
        PlayerModel(f"{team}_QB", "QB1", "QB", team,
                    PlayerUsage(snap_share=1.0, scramble_rate=0.06),
                    PlayerOutcomes(scramble_yards_dist=np.array([2, 4, 6, 8, 12, -2, 3, 5]))),
        PlayerModel(f"{team}_WR1", "WR1", "WR", team,
                    PlayerUsage(target_share=0.24),
                    PlayerOutcomes(catch_rate=0.63, receiving_yards_dist=np.array([5, 7, 8, 10, 12, 14, 16, 20, 25, 35]))),
        PlayerModel(f"{team}_WR2", "WR2", "WR", team,
                    PlayerUsage(target_share=0.18),
                    PlayerOutcomes(catch_rate=0.60, receiving_yards_dist=np.array([5, 7, 9, 11, 13, 17, 22]))),
        PlayerModel(f"{team}_TE", "TE1", "TE", team,
                    PlayerUsage(target_share=0.16),
                    PlayerOutcomes(catch_rate=0.67, receiving_yards_dist=np.array([4, 6, 8, 10, 12, 15]))),
        PlayerModel(f"{team}_RB1", "RB1", "RB", team,
                    PlayerUsage(carry_share=0.60, target_share=0.10),
                    PlayerOutcomes(
                        rushing_yards_dist=np.array([-2, 0, 1, 2, 3, 3, 4, 4, 5, 5, 6, 7, 8, 10, 15, 20]),
                        catch_rate=0.72, receiving_yards_dist=np.array([3, 5, 7, 4]),
                        fumble_rate=0.008,
                    )),
        PlayerModel(f"{team}_RB2", "RB2", "RB", team,
                    PlayerUsage(carry_share=0.30, target_share=0.05),
                    PlayerOutcomes(
                        rushing_yards_dist=np.array([0, 1, 2, 3, 4, 5, 6, 7]),
                        catch_rate=0.65, receiving_yards_dist=np.array([3, 5]),
                    )),
    ])


def make_demo_dists(team: str) -> TeamDistributions:
    return TeamDistributions(
        play_calling=PlayCallingDist(team=team, distributions={}, default={"pass": 0.57, "run": 0.43}),
        play_outcomes=PlayOutcomeDist(distributions={}, defaults={
            "pass": np.array([0, 0, 0, 0, 5, 7, 8, 10, 12, 15, 20, 25, 30]),
            "run": np.array([-2, 0, 1, 2, 3, 3, 4, 4, 5, 6, 7, 8, 12]),
        }),
        turnover_rates=TurnoverRates(team=team, int_rate=0.025, fumble_rate=0.012,
                                     sack_rate=0.065, sack_fumble_rate=0.10),
        kicking=KickingModel(fg_make_rate={"0_39": 0.93, "40_49": 0.82, "50_plus": 0.65}, xp_rate=0.94),
        drive_start=DriveStartModel(touchback_rate=0.55, touchback_yardline=75,
                                    return_yardlines=np.array([72, 74, 76, 78, 80])),
    )


def extract_team_stats(games: list[GameResult], side: str) -> dict[str, float]:
    """Extract per-team-per-game averages from sim results."""
    box_attr = "home_box" if side == "home" else "away_box"

    pass_att = np.mean([getattr(g, box_attr).pass_attempts for g in games])
    completions = np.mean([getattr(g, box_attr).completions for g in games])
    pass_yards = np.mean([getattr(g, box_attr).pass_yards for g in games])
    sacks = np.mean([getattr(g, box_attr).sacks_taken for g in games])
    rush_att = np.mean([getattr(g, box_attr).rush_attempts for g in games])
    plays = np.mean([g.total_plays for g in games]) / 2  # per team

    # Scrambles: QB rush attempts from player stats
    qb_prefix = "H_" if side == "home" else "A_"
    scrambles_list = []
    for g in games:
        qb_rush = 0
        for pid, pbox in g.player_stats.items():
            if pid.startswith(qb_prefix) and pbox.position == "QB":
                qb_rush = pbox.rush_attempts
                break
        scrambles_list.append(qb_rush)
    scrambles = np.mean(scrambles_list)

    nfl_pass_att = pass_att - sacks  # NFL convention excludes sacks
    comp_rate = completions / nfl_pass_att if nfl_pass_att > 0 else 0
    ypc = pass_yards / completions if completions > 0 else 0

    return {
        "plays_per_team": plays,
        "called_passes": pass_att + scrambles,  # all called passes (before scramble decision)
        "scrambles": scrambles,
        "sacks": sacks,
        "nfl_pass_attempts": nfl_pass_att,
        "completions": completions,
        "completion_rate": comp_rate,
        "yards_per_completion": ypc,
        "pass_yards": pass_yards,
    }


def print_comparison(stats: dict[str, float], label: str):
    """Print stats vs NFL targets with PASS/FAIL."""
    print(f"\n{'='*70}")
    print(f"  {label}")
    print(f"{'='*70}")
    print(f"  {'Metric':<35} {'Sim':>8} {'NFL Lo':>8} {'NFL Hi':>8} {'Result':>8}")
    print(f"  {'-'*35} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")

    pass_count = 0
    total = 0
    for key, (lo, hi, desc) in NFL_TARGETS.items():
        val = stats.get(key, 0)
        total += 1
        if key == "completion_rate":
            val_str = f"{val:.1%}"
            lo_str = f"{lo:.0%}"
            hi_str = f"{hi:.0%}"
        else:
            val_str = f"{val:.1f}"
            lo_str = f"{lo:.1f}"
            hi_str = f"{hi:.1f}"

        in_range = lo <= val <= hi
        result = "PASS" if in_range else "FAIL"
        if in_range:
            pass_count += 1

        print(f"  {desc:<35} {val_str:>8} {lo_str:>8} {hi_str:>8} {result:>8}")

    print(f"\n  {pass_count}/{total} metrics in NFL range")


def print_distribution_analysis(roster: TeamRoster):
    """Report per-player receiving yards distribution means."""
    print(f"\n{'='*70}")
    print(f"  Distribution Shape Analysis — {roster.team}")
    print(f"{'='*70}")
    print(f"  {'Player':<12} {'TargetSh':>10} {'CatchRate':>10} {'DistMean':>10} {'DistLen':>8} {'Fallback':>10}")
    print(f"  {'-'*12} {'-'*10} {'-'*10} {'-'*10} {'-'*8} {'-'*10}")

    total_share = 0.0
    weighted_mean = 0.0

    for p in roster.players:
        if p.usage.target_share <= 0:
            continue
        ts = p.usage.target_share
        total_share += ts
        cr = p.outcomes.catch_rate
        dist = p.outcomes.receiving_yards_dist
        if dist is not None and len(dist) > 0:
            mean = float(np.mean(dist))
            dist_len = len(dist)
            fallback = "No"
            weighted_mean += ts * mean
        else:
            mean = 0.0
            dist_len = 0
            fallback = "YES"

        print(f"  {p.name:<12} {ts:>10.2f} {cr:>10.2f} {mean:>10.1f} {dist_len:>8} {fallback:>10}")

    if total_share > 0:
        avg = weighted_mean / total_share
        print(f"\n  Weighted avg yards/catch: {avg:.1f}  (NFL target: ~11.5)")
        print(f"  Total target share: {total_share:.2f}  (normalized to 1.0 by selector)")


def run_demo_diagnostic(n_sims: int = 1000):
    """Phase 1A+1B: Demo roster diagnostic."""
    print(f"\nRunning {n_sims} demo sims...")
    home_dists = make_demo_dists("H")
    away_dists = make_demo_dists("A")
    home_roster = make_demo_roster("H")
    away_roster = make_demo_roster("A")

    results = run_simulations(home_dists, away_dists, n_sims=n_sims, seed=42,
                              home_roster=home_roster, away_roster=away_roster)

    home_stats = extract_team_stats(results.games, "home")
    away_stats = extract_team_stats(results.games, "away")

    # Average both sides for a balanced view
    avg_stats = {}
    for key in home_stats:
        avg_stats[key] = (home_stats[key] + away_stats[key]) / 2

    print_comparison(avg_stats, "Demo Roster — League Average (both teams averaged)")
    print_comparison(home_stats, "Demo Roster — Home Team Only")

    # 1B: Distribution analysis
    print_distribution_analysis(home_roster)

    # QB-level stats
    print(f"\n{'='*70}")
    print(f"  QB Per-Game Averages (from PlayerBoxScore)")
    print(f"{'='*70}")
    for prefix, label in [("H_QB", "Home QB"), ("A_QB", "Away QB")]:
        yards_list = []
        comp_list = []
        att_list = []
        sack_list = []
        rush_att_list = []
        for g in results.games:
            if prefix in g.player_stats:
                pb = g.player_stats[prefix]
                yards_list.append(pb.pass_yards)
                comp_list.append(pb.completions)
                att_list.append(pb.pass_attempts)
                sack_list.append(pb.sacks)
                rush_att_list.append(pb.rush_attempts)
        if yards_list:
            avg_yards = np.mean(yards_list)
            avg_comp = np.mean(comp_list)
            avg_att = np.mean(att_list)
            avg_sacks = np.mean(sack_list)
            avg_rush = np.mean(rush_att_list)
            nfl_att = avg_att - avg_sacks
            cr = avg_comp / nfl_att if nfl_att > 0 else 0
            ypc = avg_yards / avg_comp if avg_comp > 0 else 0
            season = avg_yards * 17
            print(f"  {label}: {avg_yards:.0f} yd/g, {avg_comp:.1f} comp, "
                  f"{nfl_att:.1f} att (NFL), {cr:.1%} comp%, "
                  f"{ypc:.1f} yd/comp, {avg_rush:.1f} scrambles, "
                  f"~{season:.0f} season yards")


def run_real_diagnostic(n_sims: int = 200):
    """Phase 1C: Real data diagnostic (requires network)."""
    try:
        from fantasy_sim.data.loader import DataLoader
        from fantasy_sim.data.game_context import GameContextBuilder
    except ImportError:
        print("\nCannot import data modules — skipping real data diagnostic.")
        return

    print(f"\n\n{'#'*70}")
    print(f"  REAL DATA DIAGNOSTIC ({n_sims} sims)")
    print(f"{'#'*70}")

    loader = DataLoader()
    builder = GameContextBuilder(cache_dir=loader.cache_dir)

    # Pick a high-volume passing matchup
    matchups = [("KC", "BUF", 2024, 1), ("TB", "DAL", 2024, 1)]

    for home, away, season, week in matchups:
        print(f"\n--- {away} @ {home}, {season} Week {week} ---")
        try:
            home_dists, away_dists, home_roster, away_roster = builder.build_game(
                home_team=home, away_team=away,
                training_seasons=[season - 2, season - 1, season],
                target_season=season, week=week,
            )
        except Exception as e:
            print(f"  Error building game: {e}")
            continue

        # Report team pass rates
        print(f"  {home} pass rate: {home_dists.play_calling.default.get('pass', 0):.1%}")
        print(f"  {away} pass rate: {away_dists.play_calling.default.get('pass', 0):.1%}")

        results = run_simulations(home_dists, away_dists, n_sims=n_sims, seed=42,
                                  home_roster=home_roster, away_roster=away_roster,
                                  week=week)

        # Extract stats for each team
        for side, team, roster in [("home", home, home_roster), ("away", away, away_roster)]:
            stats = extract_team_stats_real(results.games, side, roster)
            print_comparison(stats, f"{team} ({side})")

            # Distribution analysis for this team
            print_distribution_analysis(roster)

            # Fallback path frequency
            report_fallback_frequency(roster)

            # QB stats
            report_qb_stats(results.games, roster)


def extract_team_stats_real(games: list[GameResult], side: str, roster: TeamRoster) -> dict[str, float]:
    """Extract per-team stats, finding QB by position in roster."""
    box_attr = "home_box" if side == "home" else "away_box"

    pass_att = np.mean([getattr(g, box_attr).pass_attempts for g in games])
    completions = np.mean([getattr(g, box_attr).completions for g in games])
    pass_yards = np.mean([getattr(g, box_attr).pass_yards for g in games])
    sacks = np.mean([getattr(g, box_attr).sacks_taken for g in games])
    plays = np.mean([g.total_plays for g in games]) / 2

    # Find QB player_id
    qb_ids = {p.player_id for p in roster.players if p.position == "QB"}
    scrambles_list = []
    for g in games:
        qb_rush = 0
        for pid in qb_ids:
            if pid in g.player_stats:
                qb_rush += g.player_stats[pid].rush_attempts
        scrambles_list.append(qb_rush)
    scrambles = np.mean(scrambles_list)

    nfl_pass_att = pass_att - sacks
    comp_rate = completions / nfl_pass_att if nfl_pass_att > 0 else 0
    ypc = pass_yards / completions if completions > 0 else 0

    return {
        "plays_per_team": plays,
        "called_passes": pass_att + scrambles,
        "scrambles": scrambles,
        "sacks": sacks,
        "nfl_pass_attempts": nfl_pass_att,
        "completions": completions,
        "completion_rate": comp_rate,
        "yards_per_completion": ypc,
        "pass_yards": pass_yards,
    }


def report_fallback_frequency(roster: TeamRoster):
    """Report how many receivers lack personal receiving_yards_dist."""
    receivers = [p for p in roster.players if p.usage.target_share > 0]
    total_share = sum(p.usage.target_share for p in receivers)
    fallback_share = 0.0
    fallback_count = 0
    for p in receivers:
        dist = p.outcomes.receiving_yards_dist
        if dist is None or len(dist) == 0:
            fallback_share += p.usage.target_share
            fallback_count += 1
    pct = (fallback_share / total_share * 100) if total_share > 0 else 0
    print(f"\n  Fallback path: {fallback_count}/{len(receivers)} receivers ({pct:.1f}% of target share) "
          f"lack personal receiving_yards_dist")


def report_qb_stats(games: list[GameResult], roster: TeamRoster):
    """Report QB per-game stats from player box scores."""
    qb_ids = {p.player_id: p.name for p in roster.players if p.position == "QB"}
    for qb_id, qb_name in qb_ids.items():
        yards_list = []
        comp_list = []
        att_list = []
        sack_list = []
        rush_list = []
        for g in games:
            if qb_id in g.player_stats:
                pb = g.player_stats[qb_id]
                yards_list.append(pb.pass_yards)
                comp_list.append(pb.completions)
                att_list.append(pb.pass_attempts)
                sack_list.append(pb.sacks)
                rush_list.append(pb.rush_attempts)
        if yards_list:
            avg_yd = np.mean(yards_list)
            avg_comp = np.mean(comp_list)
            avg_att = np.mean(att_list)
            avg_sk = np.mean(sack_list)
            avg_rush = np.mean(rush_list)
            nfl_att = avg_att - avg_sk
            cr = avg_comp / nfl_att if nfl_att > 0 else 0
            ypc = avg_yd / avg_comp if avg_comp > 0 else 0
            season = avg_yd * 17
            print(f"\n  QB {qb_name} ({qb_id}): {avg_yd:.0f} yd/g, {avg_comp:.1f} comp, "
                  f"{nfl_att:.1f} att, {cr:.1%} comp%, "
                  f"{ypc:.1f} yd/comp, {avg_rush:.1f} scrambles, "
                  f"~{season:.0f} projected season")


def main():
    parser = argparse.ArgumentParser(description="Passing yards diagnostic")
    parser.add_argument("--real", action="store_true", help="Also run real data diagnostic (requires network)")
    parser.add_argument("--sims", type=int, default=1000, help="Number of demo sims (default: 1000)")
    args = parser.parse_args()

    run_demo_diagnostic(n_sims=args.sims)

    if args.real:
        run_real_diagnostic(n_sims=min(args.sims, 200))

    print("\n\n=== PASSING DIAGNOSTIC COMPLETE ===")


if __name__ == "__main__":
    main()

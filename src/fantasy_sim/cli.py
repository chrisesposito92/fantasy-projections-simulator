import click
import numpy as np
from pathlib import Path
from fantasy_sim.config.loader import load_defaults, resolve_scoring
from fantasy_sim.engine.types import TeamDistributions
from fantasy_sim.engine.monte_carlo import run_simulations
from fantasy_sim.models.distributions import (
    PlayCallingDist, PlayOutcomeDist, TurnoverRates, KickingModel, DriveStartModel,
)
from fantasy_sim.models.player import PlayerModel, PlayerUsage, PlayerOutcomes, TeamRoster
from fantasy_sim.scoring.projections import build_player_projections, build_dst_projections, build_kicker_projections
from fantasy_sim.output.tables import (
    format_qb_table, format_rb_table, format_wr_table,
    format_te_table, format_kicker_table, format_dst_table,
)
from fantasy_sim.output.export import export_csv, export_json


def _make_demo_dists(team: str) -> TeamDistributions:
    """Create league-average distributions for demo mode."""
    return TeamDistributions(
        play_calling=PlayCallingDist(team=team, distributions={}, default={"pass": 0.57, "run": 0.43}),
        play_outcomes=PlayOutcomeDist(distributions={}, defaults={
            "pass": np.array([0, 0, 0, 0, 5, 7, 8, 10, 12, 15, 20, 25, 30]),
            "run": np.array([-2, 0, 1, 2, 3, 3, 4, 4, 5, 6, 7, 8, 12]),
        }),
        turnover_rates=TurnoverRates(team=team, int_rate=0.025, fumble_rate=0.012, sack_rate=0.065, sack_fumble_rate=0.10),
        kicking=KickingModel(fg_make_rate={"0_39": 0.93, "40_49": 0.82, "50_plus": 0.65}, xp_rate=0.94),
        drive_start=DriveStartModel(touchback_rate=0.55, touchback_yardline=75, return_yardlines=np.array([72, 74, 76, 78, 80])),
    )


def _make_demo_roster(team: str) -> TeamRoster:
    """Create a demo roster with realistic usage splits."""
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
                        fumble_rate=0.008)),
        PlayerModel(f"{team}_RB2", "RB2", "RB", team,
                    PlayerUsage(carry_share=0.30, target_share=0.05),
                    PlayerOutcomes(
                        rushing_yards_dist=np.array([0, 1, 2, 3, 4, 5, 6, 7]),
                        catch_rate=0.65, receiving_yards_dist=np.array([3, 5]),
                        fumble_rate=0.010)),
    ])


@click.group()
def main():
    """Fantasy football projections via play-by-play simulation."""
    pass


@main.command()
@click.option("--sims", default=100, type=click.IntRange(min=1), help="Number of simulations per game")
@click.option("--scoring", default="ppr", type=click.Choice(["ppr", "half_ppr", "standard"]), help="Scoring format")
@click.option("--format", "output_format", default="table", type=click.Choice(["table", "csv", "json"]), help="Output format")
@click.option("--output", "output_path", default=None, help="Output file path (for csv/json)")
def demo(sims, scoring, output_format, output_path):
    """Run a demo simulation with synthetic team data."""
    config = load_defaults()
    scoring_config = resolve_scoring(config["scoring"], scoring)

    click.echo(f"Running {sims} simulations ({scoring} scoring)...")

    home_dists = _make_demo_dists("HOME")
    away_dists = _make_demo_dists("AWAY")
    home_roster = _make_demo_roster("HOME")
    away_roster = _make_demo_roster("AWAY")

    results = run_simulations(
        home_dists, away_dists, n_sims=sims, seed=42,
        home_roster=home_roster, away_roster=away_roster,
    )

    game_summary = results.summary()
    click.echo(f"Avg Score: HOME {game_summary['home_score_mean']:.1f} - AWAY {game_summary['away_score_mean']:.1f}")
    click.echo(f"HOME Win%: {game_summary['home_win_pct']:.1%}\n")

    # Build projections
    player_projs = build_player_projections(results.games, scoring_config)
    team_map = {"HOME": "HOME", "AWAY": "AWAY"}
    dst_projs = build_dst_projections(results.games, scoring_config, team_map=team_map)
    kicker_projs = build_kicker_projections(results.games, scoring_config, team_map=team_map)

    if output_format == "table":
        # Group by position and display
        qbs = [p for p in player_projs if p["position"] == "QB"]
        rbs = [p for p in player_projs if p["position"] == "RB"]
        wrs = [p for p in player_projs if p["position"] == "WR"]
        tes = [p for p in player_projs if p["position"] == "TE"]

        if qbs:
            click.echo(format_qb_table(qbs))
        if rbs:
            click.echo(format_rb_table(rbs))
        if wrs:
            click.echo(format_wr_table(wrs))
        if tes:
            click.echo(format_te_table(tes))
        if kicker_projs:
            click.echo(format_kicker_table(kicker_projs))
        if dst_projs:
            click.echo(format_dst_table(dst_projs))

    elif output_format in ("csv", "json"):
        if output_path is None:
            output_path = f"projections.{output_format}"
        all_projs = player_projs + kicker_projs + dst_projs
        if output_format == "csv":
            export_csv(all_projs, Path(output_path))
        else:
            export_json(all_projs, Path(output_path))
        click.echo(f"Exported to {output_path}")


if __name__ == "__main__":
    main()

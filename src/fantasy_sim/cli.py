import zlib
import click
import numpy as np
import polars as pl
from pathlib import Path
from fantasy_sim.config.loader import load_defaults, resolve_scoring
from fantasy_sim.data.game_context import GameContextBuilder
from fantasy_sim.data.loader import DataLoader
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
from fantasy_sim.validation.backtester import Backtester
from fantasy_sim.validation.report import format_backtest_report


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


def _display_projections(player_projs, output_format, output_path):
    """Display or export projections."""
    if output_format == "table":
        qbs = [p for p in player_projs if p["position"] == "QB"]
        rbs = [p for p in player_projs if p["position"] == "RB"]
        wrs = [p for p in player_projs if p["position"] == "WR"]
        tes = [p for p in player_projs if p["position"] == "TE"]
        if qbs:
            click.echo(format_qb_table(qbs[:24]))
        if rbs:
            click.echo(format_rb_table(rbs[:24]))
        if wrs:
            click.echo(format_wr_table(wrs[:24]))
        if tes:
            click.echo(format_te_table(tes[:12]))
    elif output_format in ("csv", "json"):
        if output_path is None:
            output_path = f"projections.{output_format}"
        if output_format == "csv":
            export_csv(player_projs, Path(output_path))
        else:
            export_json(player_projs, Path(output_path))
        click.echo(f"Exported to {output_path}")


@main.command()
@click.argument("week_num", type=int)
@click.option("--season", default=2024, help="NFL season year")
@click.option("--sims", default=1000, type=click.IntRange(min=1))
@click.option("--scoring", default="ppr", type=click.Choice(["ppr", "half_ppr", "standard"]))
@click.option("--format", "output_format", default="table", type=click.Choice(["table", "csv", "json"]))
@click.option("--output", "output_path", default=None)
def week(week_num, season, sims, scoring, output_format, output_path):
    """Simulate all games in an NFL week using real nflverse data."""
    config = load_defaults()
    scoring_config = resolve_scoring(config["scoring"], scoring)
    training_seasons = [s for s in range(season - 3, season)]

    loader = DataLoader()
    builder = GameContextBuilder(cache_dir=loader.cache_dir)

    click.echo(f"Loading schedule for {season} Week {week_num}...")
    schedules = loader.load_schedules([season])
    week_games = schedules.filter(
        (pl.col("week") == week_num) & (pl.col("season") == season)
    )

    if week_games.shape[0] == 0:
        click.echo(f"No games found for {season} Week {week_num}")
        return

    click.echo(f"Found {week_games.shape[0]} games. Running {sims} sims each ({scoring})...\n")

    all_player_projs = []

    for game in week_games.iter_rows(named=True):
        home = game["home_team"]
        away = game["away_team"]
        click.echo(f"  Simulating {away} @ {home}...", nl=False)

        home_dists, away_dists, home_roster, away_roster = builder.build_game(
            home_team=home, away_team=away, seasons=training_seasons,
        )

        seed = zlib.crc32(game["game_id"].encode()) % (2**31)
        results = run_simulations(
            home_dists, away_dists, n_sims=sims, seed=seed,
            home_roster=home_roster, away_roster=away_roster,
        )

        summary = results.summary()
        click.echo(f" {home} {summary['home_score_mean']:.1f} - {away} {summary['away_score_mean']:.1f}")

        # Build projections per-game so each player's stats use correct denominator
        all_player_projs.extend(build_player_projections(results.games, scoring_config))

    # Re-sort and re-rank across all games
    all_player_projs.sort(key=lambda p: p["fpts"], reverse=True)
    for i, p in enumerate(all_player_projs, 1):
        p["rank"] = i
    player_projs = all_player_projs
    click.echo(f"\n{season} Week {week_num} Projections ({scoring.upper()}, {sims} sims/game)\n")

    _display_projections(player_projs, output_format, output_path)


@main.command()
@click.option("--season", "season_year", default=2024, help="NFL season year")
@click.option("--weeks", default="all", help="Weeks to simulate: 'all' or '1-5' or '1,3,5'")
@click.option("--sims", default=100, type=click.IntRange(min=1), help="Sims per game (lower for season)")
@click.option("--scoring", default="ppr", type=click.Choice(["ppr", "half_ppr", "standard"]))
@click.option("--format", "output_format", default="table", type=click.Choice(["table", "csv", "json"]))
@click.option("--output", "output_path", default=None)
def season(season_year, weeks, sims, scoring, output_format, output_path):
    """Simulate a full NFL season using real nflverse data."""
    config = load_defaults()
    scoring_config = resolve_scoring(config["scoring"], scoring)
    training_seasons = [s for s in range(season_year - 3, season_year)]

    loader = DataLoader()
    builder = GameContextBuilder(cache_dir=loader.cache_dir)

    schedules = loader.load_schedules([season_year])

    if weeks == "all":
        week_nums = sorted(schedules.filter(pl.col("season") == season_year)["week"].unique().to_list())
    elif "-" in weeks:
        start, end = weeks.split("-")
        week_nums = list(range(int(start), int(end) + 1))
    else:
        week_nums = [int(w) for w in weeks.split(",")]

    click.echo(f"Simulating {season_year} season, weeks {week_nums[0]}-{week_nums[-1]} ({sims} sims/game)...\n")

    all_player_projs = []
    for wk in week_nums:
        week_games = schedules.filter(
            (pl.col("week") == wk) & (pl.col("season") == season_year)
        )
        click.echo(f"Week {wk}: {week_games.shape[0]} games")
        for game in week_games.iter_rows(named=True):
            home, away = game["home_team"], game["away_team"]
            home_dists, away_dists, home_roster, away_roster = builder.build_game(
                home, away, seasons=training_seasons,
            )
            seed = zlib.crc32(game["game_id"].encode()) % (2**31)
            results = run_simulations(
                home_dists, away_dists, n_sims=sims,
                seed=seed,
                home_roster=home_roster, away_roster=away_roster,
            )
            all_player_projs.extend(build_player_projections(results.games, scoring_config))

    all_player_projs.sort(key=lambda p: p["fpts"], reverse=True)
    for i, p in enumerate(all_player_projs, 1):
        p["rank"] = i
    player_projs = all_player_projs
    click.echo(f"\n{season_year} Season Projections ({scoring.upper()})\n")
    _display_projections(player_projs, output_format, output_path)


@main.command()
@click.option("--season", default=2024, help="Season to backtest against")
@click.option("--sims", default=100, type=click.IntRange(min=1), help="Sims per game (lower = faster)")
@click.option("--scoring", default="ppr", type=click.Choice(["ppr", "half_ppr", "standard"]))
@click.option("--training-years", default=3, help="Number of prior seasons for model fitting")
def backtest(season, sims, scoring, training_years):
    """Run backtest validation against a historical season.

    Builds models using only prior-season data (no leakage), runs projections
    for every week, and compares to actual results.

    Requires nflverse data (will download on first run).
    """
    config = load_defaults()
    scoring_config = resolve_scoring(config["scoring"], scoring)

    click.echo(f"Backtesting {season} season ({scoring} scoring, {sims} sims/game)...")
    click.echo(f"Training data: {season - training_years}-{season - 1}\n")

    bt = Backtester(
        test_season=season,
        n_sims=sims,
        num_training_seasons=training_years,
        scoring_format=scoring,
    )
    result = bt.run(scoring_config)

    report = format_backtest_report(result)
    click.echo(report)


if __name__ == "__main__":
    main()

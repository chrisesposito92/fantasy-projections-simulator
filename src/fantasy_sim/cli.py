import zlib
import click
import numpy as np
import polars as pl
from pathlib import Path
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from fantasy_sim.config.loader import load_defaults, resolve_scoring
from fantasy_sim.data.game_context import GameContextBuilder
from fantasy_sim.data.loader import DataLoader
from fantasy_sim.data.pff.config import load_pff_config
from fantasy_sim.data.weather.config import load_weather_config
from fantasy_sim.data.vegas.config import load_vegas_config
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
from fantasy_sim.overrides.parser import parse_override_config, parse_cli_override, OverrideSet
from fantasy_sim.data.game_context import apply_overrides as apply_overrides_fn, pre_resolve_overrides


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


def _build_overrides(overrides: tuple[str, ...], config_path: str | None) -> OverrideSet:
    """Merge overrides from config file and CLI flags."""
    result = OverrideSet()

    # Load config file overrides first
    if config_path is not None:
        result = parse_override_config(Path(config_path))

    # CLI overrides take precedence
    for override_str in overrides:
        entity, field_name, value = parse_cli_override(override_str)
        # Determine if it's a team (all-caps, 2-3 chars) or player
        if entity.isupper() and len(entity) <= 3:
            if entity not in result.teams:
                result.teams[entity] = {}
            result.teams[entity][field_name] = value
        else:
            if entity not in result.players:
                result.players[entity] = {}
            result.players[entity][field_name] = value

    return result


def _make_builder(
    pff_flag: bool | None = None,
    weather_flag: bool | None = None,
    vegas_flag: bool | None = None,
) -> GameContextBuilder:
    """Create GameContextBuilder, optionally with PFF, weather, and Vegas enabled."""
    defaults = load_defaults()
    pff_config = load_pff_config(defaults)
    if pff_flag is True:
        pff_config.enabled = True
    elif pff_flag is False:
        pff_config.enabled = False
    weather_config = load_weather_config(defaults)
    if weather_flag is True:
        weather_config.enabled = True
    elif weather_flag is False:
        weather_config.enabled = False
    vegas_config = load_vegas_config(defaults)
    if vegas_flag is not None:
        vegas_config.enabled = vegas_flag
    loader = DataLoader()
    return GameContextBuilder(
        cache_dir=loader.cache_dir,
        pff_config=pff_config,
        weather_config=weather_config,
        vegas_config=vegas_config,
    )


def _resolve_config_chain(
    scoring_format: str,
    scoring_config_path: str | None,
    season_yaml_path: str | None = None,
) -> dict:
    """Resolve scoring config through the config chain.

    Resolution order:
    1. defaults.yaml -> resolve scoring preset (ppr/half_ppr/standard)
    2. If season.yaml exists at season_yaml_path, load scoring_format from it
    3. If --scoring-config is provided, load custom scoring (overrides preset)
    """
    from fantasy_sim.config.loader import load_custom_scoring

    defaults = load_defaults()
    scoring_presets = defaults["scoring"]

    effective_format = scoring_format
    if season_yaml_path:
        season_path = Path(season_yaml_path)
        if season_path.exists():
            import yaml
            with open(season_path) as f:
                season_config = yaml.safe_load(f) or {}
            if "scoring_format" in season_config:
                effective_format = season_config["scoring_format"]

    scoring_config = resolve_scoring(scoring_presets, effective_format)

    if scoring_config_path:
        scoring_config = load_custom_scoring(Path(scoring_config_path), scoring_presets)

    return scoring_config


def _effective_scoring_name(
    scoring_format: str,
    season_yaml_path: str | None = None,
) -> str:
    """Return the effective scoring format name after config chain resolution."""
    effective = scoring_format
    if season_yaml_path:
        season_path = Path(season_yaml_path)
        if season_path.exists():
            import yaml
            with open(season_path) as f:
                season_config = yaml.safe_load(f) or {}
            if "scoring_format" in season_config:
                effective = season_config["scoring_format"]
    return effective


def _get_training_seasons(season: int, training_years: int | None = None) -> list[int]:
    """Get training seasons for a target season.

    Args:
        season: The target season to project.
        training_years: Number of historical seasons to use. If None,
            reads ``simulation.training_years`` from defaults.yaml
            (falls back to len(historical_seasons) for backwards compat).
    """
    if training_years is None:
        defaults = load_defaults()
        sim_config = defaults.get("simulation", {})
        training_years = sim_config.get(
            "training_years",
            len(sim_config.get("historical_seasons", [1, 2, 3])),
        )
    return list(range(season - training_years, season))


def _auto_detect_season_yaml() -> str | None:
    """Auto-detect config/season.yaml if it exists."""
    candidates = [
        Path("config/season.yaml"),
        Path.cwd() / "config" / "season.yaml",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def _read_season_yaml_metadata(season_yaml_path: str | None) -> dict:
    """Read season and weeks from a season.yaml config file.

    Returns dict with optional 'season' (int) and 'weeks' (str) keys.
    """
    if not season_yaml_path:
        return {}
    path = Path(season_yaml_path)
    if not path.exists():
        return {}
    import yaml
    with open(path) as f:
        config = yaml.safe_load(f) or {}
    result = {}
    if "season" in config:
        result["season"] = int(config["season"])
    if "weeks" in config:
        result["weeks"] = str(config["weeks"])
    return result


def _parse_and_validate_weeks(weeks_str: str) -> list[int]:
    """Parse --weeks string and validate all week numbers are positive.

    Accepts: 'all', '1-5', '1,3,5,7', '19-22' (playoff weeks)
    Raises click.BadParameter for invalid week numbers.
    """
    if weeks_str == "all":
        return []  # Empty signals "all" to the caller

    if "-" in weeks_str and "," not in weeks_str:
        parts = weeks_str.split("-")
        if len(parts) != 2:
            raise click.BadParameter(f"Invalid week range: '{weeks_str}'. Use format: '1-5'")
        try:
            start, end = int(parts[0]), int(parts[1])
        except ValueError:
            raise click.BadParameter(f"Invalid week range: '{weeks_str}'. Week numbers must be integers.")
        if start > end:
            raise click.BadParameter(
                f"Invalid week range: '{weeks_str}'. Start week must be less than or equal to end week."
            )
        week_nums = list(range(start, end + 1))
    else:
        try:
            week_nums = [int(w.strip()) for w in weeks_str.split(",")]
        except ValueError:
            raise click.BadParameter(f"Invalid week list: '{weeks_str}'. Use format: '1,3,5'")

    invalid = [w for w in week_nums if w < 1]
    if invalid:
        raise click.BadParameter(
            f"Invalid week number(s): {invalid}. Week numbers must be positive."
        )

    return week_nums


@click.group()
def main():
    """Fantasy football projections via play-by-play simulation."""
    pass


@main.command()
@click.option("--sims", default=100, type=click.IntRange(min=1), help="Number of simulations per game")
@click.option("--scoring", default="ppr", type=click.Choice(["ppr", "half_ppr", "standard"]), help="Scoring format")
@click.option("--format", "output_format", default="table", type=click.Choice(["table", "csv", "json"]), help="Output format")
@click.option("--output", "output_path", default=None, help="Output file path (for csv/json)")
@click.option("--override", "overrides", multiple=True, help="Player/team override: 'name.field=value'")
@click.option("--config", "config_path", default=None, help="Path to season.yaml with overrides")
@click.option("--scoring-config", "scoring_config_path", default=None, help="Path to custom scoring YAML")
@click.option("--detail", is_flag=True, help="Show floor/ceiling/stddev distributions")
@click.pass_context
def demo(ctx, sims, scoring, output_format, output_path, overrides, config_path, scoring_config_path, detail):
    """Run a demo simulation with synthetic team data."""
    season_yaml_path = config_path or _auto_detect_season_yaml()
    scoring_config = _resolve_config_chain(scoring, scoring_config_path, season_yaml_path=season_yaml_path)

    click.echo(f"Running {sims} simulations ({scoring} scoring)...")

    home_dists = _make_demo_dists("HOME")
    away_dists = _make_demo_dists("AWAY")
    home_roster = _make_demo_roster("HOME")
    away_roster = _make_demo_roster("AWAY")

    override_set = _build_overrides(overrides, config_path)
    if override_set.players:
        override_set = pre_resolve_overrides(override_set, [home_roster, away_roster])
    if override_set.players or override_set.teams:
        apply_overrides_fn(override_set, home_dists, away_dists, home_roster, away_roster)

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

    output_format = _infer_format(output_format, output_path, ctx)

    if output_format == "table":
        qbs = [p for p in player_projs if p["position"] == "QB"]
        rbs = [p for p in player_projs if p["position"] == "RB"]
        wrs = [p for p in player_projs if p["position"] == "WR"]
        tes = [p for p in player_projs if p["position"] == "TE"]

        if detail:
            from fantasy_sim.scoring.projections import build_detailed_projections
            from fantasy_sim.output.tables import (
                format_qb_detail_table, format_rb_detail_table,
                format_wr_detail_table, format_te_detail_table,
            )
            player_projs = build_detailed_projections(results.games, scoring_config)
            qbs = [p for p in player_projs if p["position"] == "QB"]
            rbs = [p for p in player_projs if p["position"] == "RB"]
            wrs = [p for p in player_projs if p["position"] == "WR"]
            tes = [p for p in player_projs if p["position"] == "TE"]
            if qbs:
                click.echo(format_qb_detail_table(qbs))
            if rbs:
                click.echo(format_rb_detail_table(rbs))
            if wrs:
                click.echo(format_wr_detail_table(wrs))
            if tes:
                click.echo(format_te_detail_table(tes))
        else:
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


def _infer_format(output_format: str, output_path: str | None, ctx: click.Context) -> str:
    """Infer output format from file extension if --format was not explicitly set."""
    source = ctx.get_parameter_source("output_format")
    if source != click.core.ParameterSource.DEFAULT:
        return output_format  # User explicitly set --format
    if output_path is None:
        return output_format
    ext = Path(output_path).suffix.lower()
    if ext == ".json":
        return "json"
    elif ext == ".csv":
        return "csv"
    return output_format


# Stat fields to sum during season aggregation
_PLAYER_SUM_FIELDS = [
    "fpts", "pass_yards", "pass_tds", "interceptions", "sacks",
    "rush_yards", "rush_tds", "targets", "receptions",
    "receiving_yards", "receiving_tds", "fumbles_lost",
]

_DST_SUM_FIELDS = [
    "fpts", "sacks", "interceptions", "fumble_recoveries",
    "dst_tds", "safeties", "points_allowed",
]

_KICKER_SUM_FIELDS = [
    "fpts", "fg_attempts", "fg_made", "fg_50_plus",
    "xp_attempts", "xp_made",
]


def _aggregate_projections(
    projs: list[dict],
    key_fn,
    identity_fn,
    sum_fields: list[str],
) -> list[dict]:
    """Aggregate per-game projections into season totals.

    Groups by key_fn(row), initializes identity fields via identity_fn(row),
    sums sum_fields, re-ranks by fpts. Rounds once at the end.
    """
    grouped: dict[str, dict] = {}
    for p in projs:
        key = key_fn(p)
        if key not in grouped:
            grouped[key] = identity_fn(p)
            for field in sum_fields:
                grouped[key][field] = 0.0
        for field in sum_fields:
            if field in p:
                grouped[key][field] += p[field]

    result = list(grouped.values())
    for row in result:
        for field in sum_fields:
            row[field] = round(row[field], 1)
    result.sort(key=lambda p: p["fpts"], reverse=True)
    for i, p in enumerate(result, 1):
        p["rank"] = i
    return result


def _aggregate_player_projections(projs: list[dict]) -> list[dict]:
    return _aggregate_projections(
        projs,
        key_fn=lambda p: p["player_id"],
        identity_fn=lambda p: {
            "player_id": p["player_id"], "name": p["name"],
            "position": p["position"], "team": p["team"],
        },
        sum_fields=_PLAYER_SUM_FIELDS,
    )


def _aggregate_dst_projections(projs: list[dict]) -> list[dict]:
    return _aggregate_projections(
        projs,
        key_fn=lambda p: p["team"],
        identity_fn=lambda p: {"team": p["team"]},
        sum_fields=_DST_SUM_FIELDS,
    )


def _aggregate_kicker_projections(projs: list[dict]) -> list[dict]:
    def _kicker_identity(p):
        result = {"name": p["name"], "team": p["team"]}
        if "player_id" in p:
            result["player_id"] = p["player_id"]
        if "position" in p:
            result["position"] = p["position"]
        return result

    return _aggregate_projections(
        projs,
        key_fn=lambda p: p.get("player_id", p["name"]),
        identity_fn=_kicker_identity,
        sum_fields=_KICKER_SUM_FIELDS,
    )


def _display_projections(player_projs, output_format, output_path, detail=False,
                         kicker_projs=None, dst_projs=None):
    """Display or export projections."""
    if output_format == "table":
        qbs = [p for p in player_projs if p["position"] == "QB"]
        rbs = [p for p in player_projs if p["position"] == "RB"]
        wrs = [p for p in player_projs if p["position"] == "WR"]
        tes = [p for p in player_projs if p["position"] == "TE"]

        if detail:
            from fantasy_sim.output.tables import (
                format_qb_detail_table, format_rb_detail_table,
                format_wr_detail_table, format_te_detail_table,
            )
            if qbs:
                click.echo(format_qb_detail_table(qbs[:24]))
            if rbs:
                click.echo(format_rb_detail_table(rbs[:24]))
            if wrs:
                click.echo(format_wr_detail_table(wrs[:24]))
            if tes:
                click.echo(format_te_detail_table(tes[:12]))
        else:
            if qbs:
                click.echo(format_qb_table(qbs[:24]))
            if rbs:
                click.echo(format_rb_table(rbs[:24]))
            if wrs:
                click.echo(format_wr_table(wrs[:24]))
            if tes:
                click.echo(format_te_table(tes[:12]))
        if kicker_projs:
            click.echo(format_kicker_table(kicker_projs))
        if dst_projs:
            click.echo(format_dst_table(dst_projs))
    elif output_format in ("csv", "json"):
        if output_path is None:
            output_path = f"projections.{output_format}"
        all_projs = player_projs + (kicker_projs or []) + (dst_projs or [])
        if output_format == "csv":
            export_csv(all_projs, Path(output_path))
        else:
            export_json(all_projs, Path(output_path))
        click.echo(f"Exported to {output_path}")


@main.command()
@click.argument("week_num", type=int)
@click.option("--season", default=2024, help="NFL season year")
@click.option("--sims", default=None, type=click.IntRange(min=1))
@click.option("--scoring", default="ppr", type=click.Choice(["ppr", "half_ppr", "standard"]))
@click.option("--format", "output_format", default="table", type=click.Choice(["table", "csv", "json"]))
@click.option("--output", "output_path", default=None)
@click.option("--override", "overrides", multiple=True, help="Player/team override: 'name.field=value'")
@click.option("--config", "config_path", default=None, help="Path to season.yaml with overrides")
@click.option("--scoring-config", "scoring_config_path", default=None, help="Path to custom scoring YAML")
@click.option("--detail", is_flag=True, help="Show floor/ceiling/stddev distributions")
@click.option("--pff/--no-pff", default=None, help="Enable/disable PFF matchup + talent adjustments")
@click.option("--weather/--no-weather", default=None, help="Enable/disable weather adjustments")
@click.option("--vegas/--no-vegas", default=None, help="Enable/disable Vegas line adjustments")
@click.option("--training-years", type=int, default=None, help="Number of historical seasons for training data (default: from config)")
@click.pass_context
def week(ctx, week_num, season, sims, scoring, output_format, output_path, overrides, config_path, scoring_config_path, detail, pff, weather, vegas, training_years):
    """Simulate all games in an NFL week using real nflverse data."""
    season_yaml = config_path or _auto_detect_season_yaml()
    if ctx.get_parameter_source("season") == click.core.ParameterSource.DEFAULT:
        meta = _read_season_yaml_metadata(season_yaml)
        if "season" in meta:
            season = meta["season"]
    effective_scoring = _effective_scoring_name(scoring, season_yaml)
    scoring_config = _resolve_config_chain(scoring, scoring_config_path, season_yaml)
    training_seasons = _get_training_seasons(season, training_years)

    if sims is None:
        defaults = load_defaults()
        sims = defaults.get("simulation", {}).get("num_sims", 1000)

    builder = _make_builder(pff, weather, vegas)
    loader = DataLoader()

    click.echo(f"Loading schedule for {season} Week {week_num}...")
    schedules = loader.load_schedules([season])
    week_games = schedules.filter(
        (pl.col("week") == week_num) & (pl.col("season") == season)
    )

    if week_games.shape[0] == 0:
        click.echo(f"No games found for {season} Week {week_num}.", err=True)
        click.echo("Check the schedule data or try a different week.", err=True)
        raise SystemExit(1)

    click.echo(f"Found {week_games.shape[0]} games. Running {sims} sims each ({scoring})...\n")

    all_player_projs = []
    all_dst_projs = []
    all_kicker_projs = []
    override_set = _build_overrides(overrides, config_path)

    # Build all game data first so we can pre-resolve overrides against all rosters
    game_data = []
    all_rosters = []
    for game in week_games.iter_rows(named=True):
        home = game["home_team"]
        away = game["away_team"]
        home_dists, away_dists, home_roster, away_roster = builder.build_game(
            home_team=home, away_team=away, training_seasons=training_seasons,
            target_season=season, week=week_num,
        )
        all_rosters.extend([home_roster, away_roster])
        game_data.append((home_dists, away_dists, home_roster, away_roster, game))

    # Pre-resolve player override names to exact IDs against all rosters
    if override_set.players:
        override_set = pre_resolve_overrides(override_set, all_rosters)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
    ) as progress:
        task = progress.add_task("Simulating games...", total=len(game_data))
        for home_dists, away_dists, home_roster, away_roster, game in game_data:
            home = game["home_team"]
            away = game["away_team"]
            progress.update(task, description=f"{away} @ {home}")

            if override_set.players or override_set.teams:
                apply_overrides_fn(override_set, home_dists, away_dists, home_roster, away_roster)

            seed = zlib.crc32(game["game_id"].encode()) % (2**31)
            results = run_simulations(
                home_dists, away_dists, n_sims=sims, seed=seed,
                home_roster=home_roster, away_roster=away_roster,
                week=week_num,
            )

            team_map = {"HOME": home, "AWAY": away}

            # Build projections per-game so each player's stats use correct denominator
            if detail:
                from fantasy_sim.scoring.projections import build_detailed_projections
                all_player_projs.extend(build_detailed_projections(results.games, scoring_config))
            else:
                all_player_projs.extend(build_player_projections(results.games, scoring_config))

            all_dst_projs.extend(build_dst_projections(results.games, scoring_config, team_map=team_map))
            all_kicker_projs.extend(build_kicker_projections(
                results.games, scoring_config, team_map=team_map,
                home_roster=home_roster, away_roster=away_roster,
            ))
            progress.advance(task)

    # Re-sort and re-rank across all games
    all_player_projs.sort(key=lambda p: p["fpts"], reverse=True)
    for i, p in enumerate(all_player_projs, 1):
        p["rank"] = i
    all_dst_projs.sort(key=lambda p: p["fpts"], reverse=True)
    for i, p in enumerate(all_dst_projs, 1):
        p["rank"] = i
    all_kicker_projs.sort(key=lambda p: p["fpts"], reverse=True)
    for i, p in enumerate(all_kicker_projs, 1):
        p["rank"] = i

    player_projs = all_player_projs
    click.echo(f"\n{season} Week {week_num} Projections ({effective_scoring.upper()}, {sims} sims/game)\n")

    output_format = _infer_format(output_format, output_path, ctx)
    _display_projections(player_projs, output_format, output_path, detail=detail,
                         kicker_projs=all_kicker_projs, dst_projs=all_dst_projs)


@main.command()
@click.option("--season", "season_year", default=2024, help="NFL season year")
@click.option("--weeks", default="all", help="Weeks to simulate: 'all' or '1-5' or '1,3,5'")
@click.option("--sims", default=None, type=click.IntRange(min=1), help="Sims per game (lower for season)")
@click.option("--scoring", default="ppr", type=click.Choice(["ppr", "half_ppr", "standard"]))
@click.option("--format", "output_format", default="table", type=click.Choice(["table", "csv", "json"]))
@click.option("--output", "output_path", default=None)
@click.option("--override", "overrides", multiple=True, help="Player/team override: 'name.field=value'")
@click.option("--config", "config_path", default=None, help="Path to season.yaml with overrides")
@click.option("--scoring-config", "scoring_config_path", default=None, help="Path to custom scoring YAML")
@click.option("--detail", is_flag=True, help="Show floor/ceiling/stddev distributions")
@click.option("--by-week", is_flag=True, help="Output per-week breakdowns instead of season totals")
@click.option("--pff/--no-pff", default=None, help="Enable/disable PFF matchup + talent adjustments")
@click.option("--weather/--no-weather", default=None, help="Enable/disable weather adjustments")
@click.option("--vegas/--no-vegas", default=None, help="Enable/disable Vegas line adjustments")
@click.option("--training-years", type=int, default=None, help="Number of historical seasons for training data (default: from config)")
@click.pass_context
def season(ctx, season_year, weeks, sims, scoring, output_format, output_path, overrides, config_path, scoring_config_path, detail, by_week, pff, weather, vegas, training_years):
    """Simulate a full NFL season using real nflverse data."""
    season_yaml = config_path or _auto_detect_season_yaml()
    meta = _read_season_yaml_metadata(season_yaml)
    if ctx.get_parameter_source("season_year") == click.core.ParameterSource.DEFAULT:
        if "season" in meta:
            season_year = meta["season"]
    if ctx.get_parameter_source("weeks") == click.core.ParameterSource.DEFAULT:
        if "weeks" in meta:
            weeks = meta["weeks"]
    effective_scoring = _effective_scoring_name(scoring, season_yaml)
    scoring_config = _resolve_config_chain(scoring, scoring_config_path, season_yaml)
    training_seasons = _get_training_seasons(season_year, training_years)

    if sims is None:
        defaults = load_defaults()
        sims = defaults.get("simulation", {}).get("num_sims", 1000)

    try:
        parsed_weeks = _parse_and_validate_weeks(weeks)
    except click.BadParameter as e:
        click.echo(f"Error: {e.format_message()}", err=True)
        raise SystemExit(1)

    builder = _make_builder(pff, weather, vegas)
    loader = DataLoader()

    schedules = loader.load_schedules([season_year])

    if not parsed_weeks:
        # "all" — regular season only
        game_schedule = schedules.filter(
            (pl.col("season") == season_year) & (pl.col("game_type") == "REG")
        )
        week_nums = sorted(game_schedule["week"].unique().to_list())
    else:
        week_nums = parsed_weeks
        game_schedule = schedules.filter(pl.col("season") == season_year)

    if not week_nums:
        click.echo(f"No regular-season games found for {season_year}.", err=True)
        raise SystemExit(1)

    click.echo(f"Simulating {season_year} season, weeks {week_nums[0]}-{week_nums[-1]} ({sims} sims/game)...\n")

    all_player_projs = []
    all_dst_projs = []
    all_kicker_projs = []
    override_set = _build_overrides(overrides, config_path)

    # Pre-resolve player override names to exact IDs using first week's rosters
    if override_set.players:
        first_week_games = game_schedule.filter(pl.col("week") == week_nums[0])
        first_week_rosters = []
        for game in first_week_games.iter_rows(named=True):
            home, away = game["home_team"], game["away_team"]
            _, _, hr, ar = builder.build_game(
                home_team=home, away_team=away, training_seasons=training_seasons,
                target_season=season_year, week=week_nums[0],
            )
            first_week_rosters.extend([hr, ar])
        override_set = pre_resolve_overrides(override_set, first_week_rosters)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
    ) as progress:
        task = progress.add_task("Simulating season...", total=len(week_nums))
        for wk in week_nums:
            progress.update(task, description=f"Week {wk}")
            week_games = game_schedule.filter(pl.col("week") == wk)
            for game in week_games.iter_rows(named=True):
                home, away = game["home_team"], game["away_team"]
                home_dists, away_dists, home_roster, away_roster = builder.build_game(
                    home_team=home, away_team=away, training_seasons=training_seasons,
                    target_season=season_year, week=wk,
                )
                if override_set.players or override_set.teams:
                    apply_overrides_fn(override_set, home_dists, away_dists, home_roster, away_roster)
                seed = zlib.crc32(game["game_id"].encode()) % (2**31)
                results = run_simulations(
                    home_dists, away_dists, n_sims=sims,
                    seed=seed,
                    home_roster=home_roster, away_roster=away_roster,
                    week=wk,
                )
                team_map = {"HOME": home, "AWAY": away}
                if detail:
                    from fantasy_sim.scoring.projections import build_detailed_projections
                    player_batch = build_detailed_projections(results.games, scoring_config)
                else:
                    player_batch = build_player_projections(results.games, scoring_config)
                dst_batch = build_dst_projections(results.games, scoring_config, team_map=team_map)
                kicker_batch = build_kicker_projections(
                    results.games, scoring_config, team_map=team_map,
                    home_roster=home_roster, away_roster=away_roster,
                )
                for proj in player_batch:
                    proj["week"] = wk
                for proj in dst_batch:
                    proj["week"] = wk
                for proj in kicker_batch:
                    proj["week"] = wk

                all_player_projs.extend(player_batch)
                all_dst_projs.extend(dst_batch)
                all_kicker_projs.extend(kicker_batch)
            progress.advance(task)

    output_format = _infer_format(output_format, output_path, ctx)

    if by_week:
        # Sort by week, then fpts within each week
        all_player_projs.sort(key=lambda p: (p["week"], -p["fpts"]))
        all_dst_projs.sort(key=lambda p: (p["week"], -p["fpts"]))
        all_kicker_projs.sort(key=lambda p: (p["week"], -p["fpts"]))

        if output_format == "table":
            for wk in week_nums:
                wk_players = [p for p in all_player_projs if p["week"] == wk]
                wk_dst = [p for p in all_dst_projs if p["week"] == wk]
                wk_kickers = [p for p in all_kicker_projs if p["week"] == wk]
                # Re-rank within week
                for i, p in enumerate(wk_players, 1):
                    p["rank"] = i
                for i, p in enumerate(wk_dst, 1):
                    p["rank"] = i
                for i, p in enumerate(wk_kickers, 1):
                    p["rank"] = i
                click.echo(f"\n{season_year} Week {wk} Projections ({effective_scoring.upper()}, {sims} sims/game)\n")
                _display_projections(wk_players, "table", None, detail=detail,
                                     kicker_projs=wk_kickers, dst_projs=wk_dst)
        else:
            # Rank within each week before export
            for proj_list in (all_player_projs, all_dst_projs, all_kicker_projs):
                for wk in week_nums:
                    wk_projs = [p for p in proj_list if p["week"] == wk]
                    for i, p in enumerate(wk_projs, 1):
                        p["rank"] = i
            all_projs = all_player_projs + all_kicker_projs + all_dst_projs
            if output_path is None:
                output_path = f"projections.{output_format}"
            if output_format == "csv":
                export_csv(all_projs, Path(output_path))
            else:
                export_json(all_projs, Path(output_path))
            click.echo(f"Exported to {output_path}")
    else:
        # Aggregate into season totals
        all_player_projs = _aggregate_player_projections(all_player_projs)
        all_dst_projs = _aggregate_dst_projections(all_dst_projs)
        all_kicker_projs = _aggregate_kicker_projections(all_kicker_projs)

        if detail:
            click.echo(
                "Note: floor/ceiling/stddev are not available for aggregated season totals. "
                "Use --by-week --detail for weekly distributions."
            )
            detail = False

        click.echo(f"\n{season_year} Season Projections ({effective_scoring.upper()})\n")
        _display_projections(all_player_projs, output_format, output_path, detail=detail,
                             kicker_projs=all_kicker_projs, dst_projs=all_dst_projs)


@main.command()
@click.argument("home_team")
@click.argument("away_team")
@click.option("--week", "week_num", default=1, type=int, help="Week number for schedule lookup")
@click.option("--season", default=2024, help="NFL season year")
@click.option("--sims", default=None, type=click.IntRange(min=1), help="Number of simulations")
@click.option("--scoring", default="ppr", type=click.Choice(["ppr", "half_ppr", "standard"]))
@click.option("--scoring-config", "scoring_config_path", default=None, help="Path to custom_scoring.yaml")
@click.option("--demo", is_flag=True, help="Use synthetic data (no network needed)")
@click.option("--detail", is_flag=True, help="Show floor/ceiling/stddev distributions")
@click.option("--override", "overrides", multiple=True, help="Player/team override: 'name.field=value'")
@click.option("--config", "config_path", default=None, help="Path to season.yaml with overrides")
@click.option("--pff/--no-pff", default=None, help="Enable/disable PFF matchup + talent adjustments")
@click.option("--weather/--no-weather", default=None, help="Enable/disable weather adjustments")
@click.option("--vegas/--no-vegas", default=None, help="Enable/disable Vegas line adjustments")
@click.option("--training-years", type=int, default=None, help="Number of historical seasons for training data (default: from config)")
@click.pass_context
def game(ctx, home_team, away_team, week_num, season, sims, scoring, scoring_config_path, demo, detail, overrides, config_path, pff, weather, vegas, training_years):
    """Simulate a single game with deep-dive projections.

    Example: fantasy-sim game KC BUF --week 5
    """
    effective_config_path = config_path or _auto_detect_season_yaml()
    if ctx.get_parameter_source("season") == click.core.ParameterSource.DEFAULT:
        meta = _read_season_yaml_metadata(effective_config_path)
        if "season" in meta:
            season = meta["season"]
    scoring_config = _resolve_config_chain(
        scoring_format=scoring,
        scoring_config_path=scoring_config_path,
        season_yaml_path=effective_config_path,
    )

    if sims is None:
        defaults = load_defaults()
        sims = defaults.get("simulation", {}).get("num_sims", 1000)

    home_team = home_team.upper()
    away_team = away_team.upper()

    if demo:
        home_dists = _make_demo_dists(home_team)
        away_dists = _make_demo_dists(away_team)
        home_roster = _make_demo_roster(home_team)
        away_roster = _make_demo_roster(away_team)
    else:
        training_seasons = _get_training_seasons(season, training_years)
        builder = _make_builder(pff, weather, vegas)
        home_dists, away_dists, home_roster, away_roster = builder.build_game(
            home_team=home_team, away_team=away_team, training_seasons=training_seasons,
            target_season=season, week=week_num,
        )

    override_set = _build_overrides(overrides, effective_config_path)
    if override_set.players:
        override_set = pre_resolve_overrides(override_set, [home_roster, away_roster])
    if override_set.players or override_set.teams:
        apply_overrides_fn(override_set, home_dists, away_dists, home_roster, away_roster)

    click.echo(f"Simulating {away_team} @ {home_team} — Week {week_num} ({sims} sims)...\n")

    seed = 42 if demo else zlib.crc32(f"{season}_{week_num}_{home_team}_{away_team}".encode()) % (2**31)
    results = run_simulations(
        home_dists, away_dists, n_sims=sims, seed=seed,
        home_roster=home_roster, away_roster=away_roster,
        week=week_num,
    )

    # Game summary
    game_summary = results.summary()
    home_wins = sum(1 for g in results.games if g.home_score > g.away_score)
    away_wins = sum(1 for g in results.games if g.away_score > g.home_score)
    ties = len(results.games) - home_wins - away_wins

    click.echo(f"{home_team} vs {away_team} — Week {week_num} ({sims} sims)")
    click.echo(f"Avg Score: {home_team} {game_summary['home_score_mean']:.1f} - {away_team} {game_summary['away_score_mean']:.1f}")
    click.echo(f"{home_team} Win%: {home_wins/len(results.games):.1%}   {away_team} Win%: {away_wins/len(results.games):.1%}")
    if ties > 0:
        click.echo(f"Tie%: {ties/len(results.games):.1%}")
    click.echo()

    # Player projections — grouped by team
    team_map = {"HOME": home_team, "AWAY": away_team}
    if detail:
        from fantasy_sim.scoring.projections import build_detailed_projections
        player_projs = build_detailed_projections(results.games, scoring_config)
    else:
        player_projs = build_player_projections(results.games, scoring_config)

    dst_projs = build_dst_projections(results.games, scoring_config, team_map=team_map)
    kicker_projs = build_kicker_projections(
        results.games, scoring_config, team_map=team_map,
        home_roster=home_roster, away_roster=away_roster,
    )

    # Display by team
    for team_name in [home_team, away_team]:
        team_players = [p for p in player_projs if p["team"] == team_name]
        if not team_players:
            continue

        click.echo(f"{team_name} Key Players:")
        if detail:
            from fantasy_sim.output.tables import (
                format_qb_detail_table, format_rb_detail_table,
                format_wr_detail_table, format_te_detail_table,
            )
            qbs = [p for p in team_players if p["position"] == "QB"]
            rbs = [p for p in team_players if p["position"] == "RB"]
            wrs = [p for p in team_players if p["position"] == "WR"]
            tes = [p for p in team_players if p["position"] == "TE"]
            if qbs:
                click.echo(format_qb_detail_table(qbs))
            if rbs:
                click.echo(format_rb_detail_table(rbs))
            if wrs:
                click.echo(format_wr_detail_table(wrs))
            if tes:
                click.echo(format_te_detail_table(tes))
        else:
            qbs = [p for p in team_players if p["position"] == "QB"]
            rbs = [p for p in team_players if p["position"] == "RB"]
            wrs = [p for p in team_players if p["position"] == "WR"]
            tes = [p for p in team_players if p["position"] == "TE"]
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


@main.command()
@click.argument("player_query")
@click.option("--week", "week_num", default=1, type=int, help="Week number")
@click.option("--season", default=2024, help="NFL season year")
@click.option("--sims", default=None, type=click.IntRange(min=1), help="Number of simulations")
@click.option("--scoring", default="ppr", type=click.Choice(["ppr", "half_ppr", "standard"]))
@click.option("--scoring-config", "scoring_config_path", default=None, help="Path to custom_scoring.yaml")
@click.option("--demo", is_flag=True, help="Use synthetic data (no network needed)")
@click.option("--override", "overrides", multiple=True, help="Player/team override: 'name.field=value'")
@click.option("--config", "config_path", default=None, help="Path to season.yaml with overrides")
@click.option("--pff/--no-pff", default=None, help="Enable/disable PFF matchup + talent adjustments")
@click.option("--weather/--no-weather", default=None, help="Enable/disable weather adjustments")
@click.option("--vegas/--no-vegas", default=None, help="Enable/disable Vegas line adjustments")
@click.option("--training-years", type=int, default=None, help="Number of historical seasons for training data (default: from config)")
@click.pass_context
def player(ctx, player_query, week_num, season, sims, scoring, scoring_config_path, demo, overrides, config_path, pff, weather, vegas, training_years):
    """Show projection for a single player.

    Uses fuzzy name matching. Example: fantasy-sim player "nico_collins" --week 5
    """
    effective_config_path = config_path or _auto_detect_season_yaml()
    if ctx.get_parameter_source("season") == click.core.ParameterSource.DEFAULT:
        meta = _read_season_yaml_metadata(effective_config_path)
        if "season" in meta:
            season = meta["season"]
    scoring_config = _resolve_config_chain(
        scoring_format=scoring,
        scoring_config_path=scoring_config_path,
        season_yaml_path=effective_config_path,
    )

    if sims is None:
        defaults = load_defaults()
        sims = defaults.get("simulation", {}).get("num_sims", 1000)

    if demo:
        home_dists = _make_demo_dists("HOME")
        away_dists = _make_demo_dists("AWAY")
        home_roster = _make_demo_roster("HOME")
        away_roster = _make_demo_roster("AWAY")
        all_rosters = [home_roster, away_roster]
        game_configs = [(home_dists, away_dists, home_roster, away_roster, "HOME", "AWAY")]
    else:
        training_seasons = _get_training_seasons(season, training_years)
        builder = _make_builder(pff, weather, vegas)
        loader = DataLoader()

        click.echo(f"Loading schedule for {season} Week {week_num}...")
        schedules = loader.load_schedules([season])
        week_games = schedules.filter(
            (pl.col("week") == week_num) & (pl.col("season") == season)
        )

        if week_games.shape[0] == 0:
            click.echo(f"No games found for {season} Week {week_num}.", err=True)
            raise SystemExit(1)

        all_rosters = []
        game_configs = []
        for g in week_games.iter_rows(named=True):
            home, away = g["home_team"], g["away_team"]
            home_dists, away_dists, home_roster, away_roster = builder.build_game(
                home_team=home, away_team=away, training_seasons=training_seasons,
                target_season=season, week=week_num,
            )
            all_rosters.extend([home_roster, away_roster])
            game_configs.append((home_dists, away_dists, home_roster, away_roster, home, away))

    # Resolve player name
    from fantasy_sim.overrides.resolver import PlayerResolver
    resolver = PlayerResolver(all_rosters)
    try:
        player_id = resolver.resolve(player_query)
    except KeyError as e:
        click.echo(f"No player found matching '{player_query}'. {e}", err=True)
        raise SystemExit(1)

    # Find which game this player is in
    target_game = None
    for game_cfg in game_configs:
        hd, ad, hr, ar, home_name, away_name = game_cfg
        roster_ids = {p.player_id for p in hr.players} | {p.player_id for p in ar.players}
        if player_id in roster_ids:
            target_game = game_cfg
            break

    if target_game is None:
        click.echo(f"Player '{player_query}' not found in any Week {week_num} game.", err=True)
        raise SystemExit(1)

    hd, ad, hr, ar, home_name, away_name = target_game

    override_set = _build_overrides(overrides, effective_config_path)
    if override_set.players:
        override_set = pre_resolve_overrides(override_set, all_rosters)
    if override_set.players or override_set.teams:
        apply_overrides_fn(override_set, hd, ad, hr, ar)

    # Find player info
    player_info = None
    for roster in [hr, ar]:
        for p in roster.players:
            if p.player_id == player_id:
                player_info = p
                break

    click.echo(f"Simulating {away_name} @ {home_name} for {player_info.name} ({player_info.position}, {player_info.team})...\n")

    seed = 42 if demo else zlib.crc32(f"{season}_{week_num}_{home_name}_{away_name}".encode()) % (2**31)
    results = run_simulations(
        hd, ad, n_sims=sims, seed=seed,
        home_roster=hr, away_roster=ar,
        week=week_num,
    )

    # Build detailed projections for this player
    from fantasy_sim.scoring.projections import build_detailed_projections
    all_projs = build_detailed_projections(results.games, scoring_config)
    player_proj = next((p for p in all_projs if p["player_id"] == player_id), None)

    if player_proj is None:
        click.echo(f"No projection data for {player_info.name}.", err=True)
        raise SystemExit(1)

    # Display player card
    click.echo(f"{player_info.name} ({player_info.position}, {player_info.team}) — Week {week_num}")
    click.echo(f"Matchup: {away_name} @ {home_name} ({sims} sims)\n")

    from rich.table import Table as RichTable
    from rich.console import Console

    table = RichTable(title=f"{player_info.name} Projection")
    table.add_column("Stat", style="cyan")
    table.add_column("Avg", justify="right", style="green bold")
    table.add_column("Floor", justify="right", style="dim")
    table.add_column("Ceiling", justify="right", style="yellow")
    table.add_column("StdDev", justify="right", style="dim")

    # FPts row
    table.add_row(
        "FPts",
        f"{player_proj['fpts']:.1f}",
        f"{player_proj['fpts_floor']:.1f}",
        f"{player_proj['fpts_ceiling']:.1f}",
        f"{player_proj['fpts_stddev']:.1f}",
    )

    # Position-specific stat rows
    stat_labels = {
        "pass_yards": "Pass Yds", "pass_tds": "Pass TD",
        "interceptions": "INT",
        "rush_yards": "Rush Yds", "rush_tds": "Rush TD",
        "targets": "Targets", "receptions": "Rec",
        "receiving_yards": "Rec Yds", "receiving_tds": "Rec TD",
        "fumbles_lost": "Fum Lost",
    }
    for stat, label in stat_labels.items():
        mean_val = player_proj.get(stat, 0)
        if mean_val == 0 and stat not in ("fumbles_lost",):
            floor_val = player_proj.get(f"{stat}_floor", 0)
            ceil_val = player_proj.get(f"{stat}_ceiling", 0)
            if mean_val == 0 and floor_val == 0 and ceil_val == 0:
                continue

        table.add_row(
            label,
            f"{mean_val:.1f}",
            f"{player_proj.get(f'{stat}_floor', 0):.1f}",
            f"{player_proj.get(f'{stat}_ceiling', 0):.1f}",
            f"{player_proj.get(f'{stat}_stddev', 0):.1f}",
        )

    console = Console(width=120, force_terminal=True)
    with console.capture() as capture:
        console.print(table)
    click.echo(capture.get())


@main.command()
@click.option("--season", default=2024, help="Season to backtest against")
@click.option("--sims", default=100, type=click.IntRange(min=1), help="Sims per game (lower = faster)")
@click.option("--scoring", default="ppr", type=click.Choice(["ppr", "half_ppr", "standard"]))
@click.option("--training-years", default=3, help="Number of prior seasons for model fitting")
@click.option("--pff/--no-pff", default=None, help="Enable/disable PFF matchup + talent adjustments")
@click.option("--weather/--no-weather", default=None, help="Enable/disable weather adjustments")
@click.option("--vegas/--no-vegas", default=None, help="Enable/disable Vegas line adjustments")
def backtest(season, sims, scoring, training_years, pff, weather, vegas):
    """Run backtest validation against a historical season.

    Builds models using only prior-season data (no leakage), runs projections
    for every week, and compares to actual results.

    Requires nflverse data (will download on first run).
    """
    defaults = load_defaults()
    scoring_config = resolve_scoring(defaults["scoring"], scoring)
    pff_config = load_pff_config(defaults)
    if pff is True:
        pff_config.enabled = True
    elif pff is False:
        pff_config.enabled = False
    weather_config = load_weather_config(defaults)
    if weather is True:
        weather_config.enabled = True
    elif weather is False:
        weather_config.enabled = False
    vegas_config = load_vegas_config(defaults)
    if vegas is not None:
        vegas_config.enabled = vegas

    click.echo(f"Backtesting {season} season ({scoring} scoring, {sims} sims/game)...")
    click.echo(f"Training data: {season - training_years}-{season - 1}\n")

    bt = Backtester(
        test_season=season,
        n_sims=sims,
        num_training_seasons=training_years,
        scoring_format=scoring,
        pff_config=pff_config,
        weather_config=weather_config,
        vegas_config=vegas_config,
    )
    result = bt.run(scoring_config)

    report = format_backtest_report(result)
    click.echo(report)


if __name__ == "__main__":
    main()

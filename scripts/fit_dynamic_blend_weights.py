"""Fit learned post-simulation dynamic blend weights.

The fitter uses historical simulator output plus available external priors to
learn coarse convex weights for simulator, FF Opportunity, and market-history
sources. It does not change runtime defaults; it writes artifact JSON files
consumed by ensemble.dynamic_blend.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import zlib
from collections import defaultdict
from pathlib import Path

import polars as pl

from fantasy_sim.config.loader import load_defaults, resolve_scoring
from fantasy_sim.data.actuals import load_actual_scores
from fantasy_sim.data.ensemble import load_ensemble_config
from fantasy_sim.data.loader import DataLoader
from fantasy_sim.scoring.dynamic_blend import (
    DynamicBlendProjectionBlender,
    fit_dynamic_blend_artifact,
)
from fantasy_sim.scoring.role_trend import RoleTrendProjectionAdjuster
from fantasy_sim.validation.config import build_engine_configs, build_game_config_kwargs
from fantasy_sim.validation.parallel import (
    GameSpec,
    build_games_parallel,
    default_max_workers,
    simulate_games_parallel,
)

_HOLDOUT_SEASON = 2025


def build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fit dynamic post-sim blend weights from historical source rows.",
    )
    parser.add_argument("--test-seasons", type=int, nargs="+", required=True)
    parser.add_argument("--min-source-season", type=int, default=2022)
    parser.add_argument("--sims", type=int, default=50)
    parser.add_argument("--training-years", type=int, default=4)
    parser.add_argument("--scoring", default="ppr", choices=["ppr", "half_ppr", "standard"])
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=0)
    return parser


def _game_args_for_season(
    loader: DataLoader,
    *,
    season: int,
    training_years: int,
) -> list[tuple]:
    training_seasons = list(range(season - training_years, season))
    schedules = loader.load_schedules([season])
    weeks = sorted(
        schedules.filter(pl.col("season") == season)["week"].unique().to_list()
    )
    weeks = [week for week in weeks if 1 <= week <= 18]
    game_args = []
    for week in weeks:
        week_games = schedules.filter(
            (pl.col("season") == season) & (pl.col("week") == week)
        )
        for game in week_games.iter_rows(named=True):
            seed = zlib.crc32(game["game_id"].encode()) % (2**31)
            game_args.append(
                (
                    game["home_team"],
                    game["away_team"],
                    training_seasons,
                    season,
                    week,
                    game["game_id"],
                    seed,
                )
            )
    return game_args


def collect_source_rows_for_season(
    *,
    season: int,
    sims: int,
    training_years: int,
    scoring_config: dict[str, float],
    scoring: str,
    defaults: dict,
    max_workers: int,
) -> list[dict]:
    """Run default simulator contexts and collect source rows for fitting."""
    loader = DataLoader()
    configs = build_engine_configs(defaults)
    build_configs = build_game_config_kwargs(configs)
    role_trend = (
        RoleTrendProjectionAdjuster(configs["role_trend_config"])
        if configs.get("role_trend_config") is not None
        else None
    )
    ensemble_config = load_ensemble_config(defaults)
    market_history_config = configs.get("market_history_config")
    source_builder = DynamicBlendProjectionBlender(
        ensemble_config,
        market_history_config=market_history_config,
        scoring_config=scoring_config,
        scoring=scoring,
    )

    player_stats = loader.load_player_stats([season])
    actuals = load_actual_scores(player_stats, scoring_config, season)
    actual_by_player_week: dict[str, dict[int, float]] = defaultdict(dict)
    for actual in actuals:
        actual_by_player_week[actual.player_id][actual.week] = actual.fpts

    game_args = _game_args_for_season(
        loader,
        season=season,
        training_years=training_years,
    )
    print(f"  [{season}] Building {len(game_args)} game contexts...", flush=True)
    build_results = build_games_parallel(
        game_args,
        cache_dir=loader.cache_dir,
        max_workers=max_workers,
        dual_arm=False,
        **build_configs,
    )

    specs: list[GameSpec] = []
    for result in build_results:
        if result["status"] != "ok":
            print(
                f"  [{season}] Skipping failed game {result.get('game_id')}: "
                f"{result.get('error_type', 'Error')}",
                flush=True,
            )
            continue
        specs.append(
            GameSpec(
                game_id=result["game_id"],
                home_dists=result["home_dists"],
                away_dists=result["away_dists"],
                home_roster=result["home_roster"],
                away_roster=result["away_roster"],
                seed=result["seed"],
                week=result["week"],
            )
        )

    print(f"  [{season}] Simulating {len(specs)} games...", flush=True)
    sim_results = simulate_games_parallel(
        specs,
        n_sims=sims,
        scoring_config=scoring_config,
        max_workers=max_workers,
    )
    spec_by_id = {spec.game_id: spec for spec in specs}

    rows: list[dict] = []
    for result in sim_results:
        spec = spec_by_id[result.game_id]
        projections = result.projections
        if role_trend is not None:
            projections, _stats = role_trend.adjust_week(
                projections,
                season=season,
                week=spec.week,
            )
        rows.extend(
            source_builder.source_rows_for_week(
                projections,
                season=season,
                week=spec.week,
                actual_by_player_week=actual_by_player_week,
            )
        )

    rows = [row for row in rows if row["actual_fpts"] is not None]
    print(f"  [{season}] Collected {len(rows)} source rows.", flush=True)
    return rows


def main() -> int:
    parser = build_cli()
    args = parser.parse_args()

    if any(season >= _HOLDOUT_SEASON for season in args.test_seasons):
        print(
            f"ERROR: Season {_HOLDOUT_SEASON}+ is reserved as hold-out.",
            file=sys.stderr,
        )
        return 1

    defaults = load_defaults()
    scoring_config = resolve_scoring(defaults["scoring"], args.scoring)
    ensemble_config = load_ensemble_config(defaults)
    market_history_config = build_engine_configs(defaults).get("market_history_config")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    source_years = list(range(args.min_source_season, max(args.test_seasons)))
    if not source_years:
        print("No source seasons available for fitting.", flush=True)
        return 0

    per_season_workers = (
        args.workers
        if args.workers > 0
        else default_max_workers(batch_size=288, num_concurrent=1)
    )
    print(f"Using {per_season_workers} workers per source season.", flush=True)

    start = time.time()
    rows_by_season: dict[int, list[dict]] = {}
    for source_year in source_years:
        rows_by_season[source_year] = collect_source_rows_for_season(
            season=source_year,
            sims=args.sims,
            training_years=args.training_years,
            scoring_config=scoring_config,
            scoring=args.scoring,
            defaults=defaults,
            max_workers=per_season_workers,
        )

    for test_season in sorted(args.test_seasons):
        source_seasons = [
            season
            for season in sorted(rows_by_season)
            if args.min_source_season <= season < test_season
        ]
        if not source_seasons:
            print(
                f"  [{test_season}] No prior source seasons; no learned artifact written.",
                flush=True,
            )
            continue
        source_rows = [
            row
            for source_season in source_seasons
            for row in rows_by_season[source_season]
        ]
        artifact = fit_dynamic_blend_artifact(
            source_rows,
            test_season=test_season,
            source_seasons=source_seasons,
            sims=args.sims,
            scoring=args.scoring,
            ensemble_config=ensemble_config,
            market_history_config=market_history_config,
        )
        path = args.output_dir / f"weights_{test_season}.json"
        with path.open("w") as f:
            json.dump(artifact, f, indent=2)
        print(
            f"  [{test_season}] Wrote {path} "
            f"({len(artifact['buckets'])} learned buckets, "
            f"{len(artifact['fallback_buckets'])} fallback buckets).",
            flush=True,
        )

    print(f"Done in {time.time() - start:.1f}s.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

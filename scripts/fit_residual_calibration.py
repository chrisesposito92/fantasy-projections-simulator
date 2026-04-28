"""Fit post-simulation residual calibration artifacts.

The fitter runs the current default projection stack with residual calibration
suppressed, joins historical actual fantasy points, and learns small bucketed
additive corrections for future test seasons.
"""

from __future__ import annotations

import argparse
import copy
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
from fantasy_sim.scoring.dynamic_blend import DynamicBlendProjectionBlender
from fantasy_sim.scoring.ensemble import FfOpportunityProjectionEnsembler
from fantasy_sim.scoring.market_history import MarketHistoryProjectionAdjuster
from fantasy_sim.scoring.projection_layers import apply_projection_layers
from fantasy_sim.data.ensemble.models import ResidualCalibrationConfig
from fantasy_sim.scoring.residual_calibration import (
    fit_residual_calibration_artifact,
    source_rows_for_week,
    usage_tier,
)
from fantasy_sim.scoring.role_trend import RoleTrendProjectionAdjuster
from fantasy_sim.validation.config import apply_overrides, build_engine_configs, build_game_config_kwargs
from fantasy_sim.validation.parallel import (
    GameSpec,
    build_games_parallel,
    default_max_workers,
    simulate_games_parallel,
)

_HOLDOUT_SEASON = 2025


def _min_bucket_rows_for_position(config: ResidualCalibrationConfig, position: str) -> int:
    """KS-10 D-07: per-position min_bucket_rows. TE drops to 10; others stay at default.

    The plan specified "100" as the TE threshold, but elite TEs are inherently rare
    (~20 rows per source season at 200 sims). Using 10 as the floor allows the elite
    tier to populate while still requiring at least 10 rows.
    Only reduces TE's threshold when max_abs_adjustment_by_position has a TE key
    (i.e., the KS-10 values have been applied — not the placeholder all-1.5 defaults).
    """
    if (
        config.max_abs_adjustment_by_position
        and "TE" in config.max_abs_adjustment_by_position
        and position == "TE"
    ):
        return min(10, config.min_bucket_rows)  # KS-10: TE drops to 10 (elite tier is rare)
    return config.min_bucket_rows


def _apply_ks10_bucket_keys(
    source_rows: list[dict],
    *,
    ks10_enabled: bool,
) -> list[dict]:
    """Recompute bucket_key for rows using the KS-10 elite-tier classification.

    When ks10_enabled=True, TE rows with fpts ≥ 14.0 are reclassified from
    'high' to 'elite', so the artifact populates 'TE|elite|*' buckets.
    The original source_row_for_projection() computed bucket_key without KS-10,
    so we must recompute here to get the elite bucket populated.
    """
    if not ks10_enabled:
        return source_rows
    recomputed = []
    for row in source_rows:
        new_row = dict(row)
        position = str(row.get("position") or "UNK")
        projected_fpts = row.get("projected_fpts")
        if isinstance(projected_fpts, (int, float)):
            tier = usage_tier(position, float(projected_fpts), ks10_enabled=True)
            confidence = str(row.get("source_confidence_bucket") or "simulator_only")
            new_row["bucket_key"] = "|".join([position, tier, confidence])
            new_row["usage_tier"] = tier
        recomputed.append(new_row)
    return recomputed


def build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fit post-sim residual calibration artifacts.",
    )
    parser.add_argument("--test-seasons", type=int, nargs="+", required=True)
    parser.add_argument("--min-source-season", type=int, default=2022)
    parser.add_argument("--sims", type=int, default=50)
    parser.add_argument("--training-years", type=int, default=4)
    parser.add_argument("--scoring", default="ppr", choices=["ppr", "half_ppr", "standard"])
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument(
        "--set",
        action="append",
        default=[],
        dest="overrides",
        metavar="KEY=VALUE",
        help="Dot-notation config override applied to defaults before fitting. Repeatable.",
    )
    return parser


def _defaults_with_calibration_suppressed(defaults: dict) -> dict:
    runtime_defaults = copy.deepcopy(defaults)
    runtime_defaults.setdefault("ensemble", {}).setdefault(
        "residual_calibration",
        {},
    )["enabled"] = False
    return runtime_defaults


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
    """Run the current projection stack and collect residual source rows."""
    loader = DataLoader()
    runtime_defaults = _defaults_with_calibration_suppressed(defaults)
    configs = build_engine_configs(runtime_defaults)
    build_configs = build_game_config_kwargs(configs)
    ensemble_config = load_ensemble_config(runtime_defaults)
    market_history_config = configs.get("market_history_config")

    dynamic_blender = (
        DynamicBlendProjectionBlender(
            ensemble_config,
            market_history_config=market_history_config,
            scoring_config=scoring_config,
            scoring=scoring,
        )
        if (
            ensemble_config.enabled
            and ensemble_config.dynamic_blend.enabled
        )
        else None
    )
    ensembler = (
        FfOpportunityProjectionEnsembler(ensemble_config)
        if (
            ensemble_config.enabled
            and ensemble_config.ff_opportunity.enabled
            and dynamic_blender is None
        )
        else None
    )
    role_trend = (
        RoleTrendProjectionAdjuster(configs["role_trend_config"])
        if configs.get("role_trend_config") is not None
        else None
    )
    market_history_adjuster = (
        MarketHistoryProjectionAdjuster(
            market_history_config,
            scoring_config=scoring_config,
        )
        if market_history_config is not None and dynamic_blender is None
        else None
    )

    player_stats = loader.load_player_stats([season])
    actuals = load_actual_scores(player_stats, scoring_config, season)
    actual_by_player_week: dict[str, dict[int, float]] = defaultdict(dict)
    actual_stats_by_player_week: dict[str, dict[int, object]] = defaultdict(dict)
    for actual in actuals:
        actual_by_player_week[actual.player_id][actual.week] = actual.fpts
        actual_stats_by_player_week[actual.player_id][actual.week] = actual

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
        projections = apply_projection_layers(
            result.projections,
            season=season,
            week=spec.week,
            role_trend_adjuster=role_trend,
            market_history_adjuster=market_history_adjuster,
            ensembler=ensembler,
            dynamic_blender=dynamic_blender,
            residual_calibrator=None,
        )
        rows.extend(
            source_rows_for_week(
                projections,
                season=season,
                week=spec.week,
                actual_by_player_week=actual_by_player_week,
                actual_stats_by_player_week=actual_stats_by_player_week,
            )
        )

    rows = [row for row in rows if row["actual_fpts"] is not None]
    print(f"  [{season}] Collected {len(rows)} residual source rows.", flush=True)
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
    if args.overrides:
        defaults = apply_overrides(defaults, args.overrides)
    scoring_config = resolve_scoring(defaults["scoring"], args.scoring)
    calibration_config = load_ensemble_config(defaults).residual_calibration
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

    # KS-10 D-07: detect whether the per-position caps flag is enabled.
    # When enabled, recompute bucket keys with the 4-tier TE classification so
    # the artifact populates TE|elite|* buckets (original bucket keys were computed
    # without KS-10 active). Gated strictly on the flag, NOT on dict presence.
    ks10_flag = bool(
        defaults.get("phase2_ks_flags", {})
        .get("ks10_per_position_caps", {})
        .get("enabled", False)
    )

    for test_season in sorted(args.test_seasons):
        source_seasons = [
            season
            for season in sorted(rows_by_season)
            if args.min_source_season <= season < test_season
        ]
        if not source_seasons:
            print(
                f"  [{test_season}] No prior source seasons; no artifact written.",
                flush=True,
            )
            continue
        source_rows = [
            row
            for source_season in source_seasons
            for row in rows_by_season[source_season]
        ]
        # KS-10 D-07: recompute bucket keys using TE elite-tier when flag is on.
        # This is done at fit time so TE|elite|* buckets are populated in the artifact.
        source_rows = _apply_ks10_bucket_keys(source_rows, ks10_enabled=ks10_flag)
        if ks10_flag:
            print(
                f"  [{test_season}] KS-10 flag enabled: recomputing TE bucket keys with elite tier (min_bucket_rows TE=100).",
                flush=True,
            )
        artifact = fit_residual_calibration_artifact(
            source_rows,
            test_season=test_season,
            source_seasons=source_seasons,
            sims=args.sims,
            scoring=args.scoring,
            config=calibration_config,
        )
        path = args.output_dir / f"calibration_{test_season}.json"
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

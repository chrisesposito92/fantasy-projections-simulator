"""Fit learned receiver target-selection artifacts.

The model is an in-simulation conditional softmax over the same receiver
candidate pool the legacy selector already uses. It writes one JSON artifact
per test season and does not change runtime defaults.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
import time
import zlib
from pathlib import Path

import numpy as np
import polars as pl

from fantasy_sim.config.loader import load_defaults, resolve_scoring
from fantasy_sim.data.loader import DataLoader
from fantasy_sim.data.target_selection.models import (
    DEFAULT_TARGET_SELECTION_FEATURES,
    TARGET_SELECTION_MODEL_TYPE,
    TARGET_SELECTION_SCHEMA_VERSION,
    build_player_static_features,
    candidate_feature_values,
)
from fantasy_sim.data.target_selection.training import (
    TargetSelectionExample,
    fit_conditional_softmax,
)
from fantasy_sim.engine.game_script import resolve_game_script
from fantasy_sim.engine.player_selector import receiver_candidates_and_legacy_weights
from fantasy_sim.engine.types import GameState
from fantasy_sim.validation.config import build_engine_configs, build_game_config_kwargs
from fantasy_sim.validation.parallel import build_games_parallel, default_max_workers

_HOLDOUT_SEASON = 2025


def build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fit learned receiver target-selection artifacts.",
    )
    parser.add_argument("--test-seasons", type=int, nargs="+", required=True)
    parser.add_argument("--training-years", type=int, default=4)
    parser.add_argument(
        "--min-context-season",
        type=int,
        default=2018,
        help=(
            "Earliest season allowed when building leak-free source-game contexts. "
            "Source seasons with no prior context after this floor are skipped."
        ),
    )
    parser.add_argument("--scoring", default="ppr", choices=["ppr", "half_ppr", "standard"])
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--l2", type=float, default=1.0)
    parser.add_argument("--max-iter", type=int, default=200)
    parser.add_argument(
        "--max-examples-per-season",
        type=int,
        default=0,
        help="Deterministic cap per fitted artifact. 0 means use all eligible target events.",
    )
    parser.add_argument("--workers", type=int, default=0)
    return parser


def _is_pass_target_row(row: dict) -> bool:
    receiver_id = row.get("receiver_player_id")
    if receiver_id is None or receiver_id == "":
        return False
    if "pass_attempt" in row and row["pass_attempt"] not in (1, True):
        return False
    for flag in ("sack", "qb_spike", "qb_kneel", "no_play"):
        if flag in row and row[flag] in (1, True):
            return False
    return True


def _state_from_row(row: dict) -> GameState | None:
    try:
        home_team = str(row["home_team"])
        away_team = str(row["away_team"])
        posteam = str(row["posteam"])
        possession = "home" if posteam == home_team else "away"
        score_diff = int(row.get("score_differential") or 0)
        if possession == "home":
            home_score = score_diff
            away_score = 0
        else:
            home_score = 0
            away_score = score_diff

        quarter = max(1, min(5, int(row.get("qtr") or row.get("quarter") or 1)))
        if "quarter_seconds_remaining" in row and row["quarter_seconds_remaining"] is not None:
            clock = int(row["quarter_seconds_remaining"])
        elif "game_seconds_remaining" in row and row["game_seconds_remaining"] is not None:
            game_seconds_remaining = int(row["game_seconds_remaining"])
            if quarter <= 4:
                clock = game_seconds_remaining - ((4 - quarter) * 900)
            else:
                clock = game_seconds_remaining
        else:
            clock = 900

        return GameState(
            quarter=quarter,
            clock=max(0, min(900, clock)),
            possession=possession,
            down=max(1, min(4, int(row.get("down") or 1))),
            distance=max(1, int(row.get("ydstogo") or 10)),
            yard_line=max(1, min(99, int(row.get("yardline_100") or 75))),
            home_score=home_score,
            away_score=away_score,
            home_team=home_team,
            away_team=away_team,
            receiving_2nd_half="home",
            week=int(row.get("week") or 0),
        )
    except (TypeError, ValueError, KeyError):
        return None


def _examples_from_game(
    rows: list[dict],
    build_result: dict,
    *,
    feature_names: tuple[str, ...],
) -> list[TargetSelectionExample]:
    examples: list[TargetSelectionExample] = []
    if build_result["status"] != "ok":
        return examples

    for row in rows:
        if not _is_pass_target_row(row):
            continue
        state = _state_from_row(row)
        if state is None:
            continue

        if state.possession == "home":
            roster = build_result["home_roster"]
            dists = build_result["home_dists"]
        else:
            roster = build_result["away_roster"]
            dists = build_result["away_dists"]

        script = resolve_game_script(
            state,
            dists.game_script_config,
            dists.game_script_profile,
        )
        try:
            candidates, legacy_weights = receiver_candidates_and_legacy_weights(
                roster,
                state,
                goal_line_concentration_enabled=dists.goal_line_concentration_enabled,
                script=script,
            )
        except ValueError:
            continue

        receiver_id = str(row["receiver_player_id"])
        candidate_ids = [player.player_id for player in candidates]
        if receiver_id not in candidate_ids:
            continue
        label_index = candidate_ids.index(receiver_id)

        order = sorted(
            range(len(candidates)),
            key=lambda idx: float(legacy_weights[idx]),
            reverse=True,
        )
        ranks = np.empty(len(candidates), dtype=int)
        for rank, idx in enumerate(order, start=1):
            ranks[idx] = rank

        matrix_rows: list[list[float]] = []
        for idx, player in enumerate(candidates):
            static = build_player_static_features(player)
            values = candidate_feature_values(
                player,
                static,
                state,
                legacy_weight=float(legacy_weights[idx]),
                target_rank=int(ranks[idx]),
                script=script,
            )
            matrix_rows.append([float(values.get(name, 0.0)) for name in feature_names])

        examples.append(
            TargetSelectionExample(
                features=np.asarray(matrix_rows, dtype=float),
                legacy_weights=np.asarray(legacy_weights, dtype=float),
                label_index=label_index,
            )
        )

    return examples


def _context_training_seasons(
    *,
    label_season: int,
    training_years: int,
    min_context_season: int,
) -> list[int]:
    start = max(label_season - training_years, min_context_season)
    return list(range(start, label_season))


def _game_args_from_pbp(
    pbp: pl.DataFrame,
    *,
    label_season: int,
    training_years: int,
    min_context_season: int,
) -> list[tuple]:
    training_seasons = _context_training_seasons(
        label_season=label_season,
        training_years=training_years,
        min_context_season=min_context_season,
    )
    if not training_seasons:
        return []

    games = (
        pbp.filter(pl.col("season") == label_season)
        .select(["game_id", "home_team", "away_team", "week"])
        .unique()
        .sort(["week", "game_id"])
    )
    game_args = []
    for row in games.iter_rows(named=True):
        week = int(row["week"])
        if not 1 <= week <= 18:
            continue
        seed = zlib.crc32(str(row["game_id"]).encode()) % (2**31)
        game_args.append(
            (
                row["home_team"],
                row["away_team"],
                training_seasons,
                label_season,
                week,
                row["game_id"],
                seed,
            )
        )
    return game_args


def collect_examples_for_artifact(
    *,
    target_season: int,
    training_years: int,
    defaults: dict,
    max_workers: int,
    max_examples_per_season: int,
    min_context_season: int,
) -> list[TargetSelectionExample]:
    loader = DataLoader()
    source_seasons = list(range(target_season - training_years, target_season))
    feature_names = DEFAULT_TARGET_SELECTION_FEATURES
    runtime_defaults = copy.deepcopy(defaults)
    runtime_defaults.setdefault("target_selection", {})["enabled"] = False
    # Historical source seasons can precede the currently validated
    # availability-input window. Keep runtime validation on defaults; suppress
    # this hard-decision layer only while constructing training-label contexts.
    runtime_defaults.setdefault("availability", {})["enabled"] = False
    runtime_defaults.setdefault("weather", {})["enabled"] = False
    runtime_defaults.setdefault("pff", {}).setdefault("tier_engine", {}).setdefault(
        "ncaa_rookie", {}
    )["enabled"] = False
    configs = build_engine_configs(runtime_defaults)
    build_configs = build_game_config_kwargs(configs)

    all_examples: list[TargetSelectionExample] = []
    for source_season in source_seasons:
        pbp = loader.load_pbp([source_season])
        pbp = pbp.filter(pl.col("season") == source_season)
        game_args = _game_args_from_pbp(
            pbp,
            label_season=source_season,
            training_years=training_years,
            min_context_season=min_context_season,
        )
        if not game_args:
            print(
                f"  [{target_season}] Skipping {source_season}: "
                f"no prior context seasons >= {min_context_season}",
                flush=True,
            )
            continue

        print(f"  [{target_season}] Building {len(game_args)} source games from {source_season}...", flush=True)
        build_results = build_games_parallel(
            game_args,
            cache_dir=loader.cache_dir,
            max_workers=max_workers,
            dual_arm=False,
            **build_configs,
        )
        build_by_game = {result["game_id"]: result for result in build_results}
        rows_by_game: dict[str, list[dict]] = {}
        for row in pbp.iter_rows(named=True):
            if not _is_pass_target_row(row):
                continue
            rows_by_game.setdefault(str(row["game_id"]), []).append(row)

        season_examples: list[TargetSelectionExample] = []
        for game_id, rows in rows_by_game.items():
            build_result = build_by_game.get(game_id)
            if build_result is None:
                continue
            season_examples.extend(
                _examples_from_game(
                    rows,
                    build_result,
                    feature_names=feature_names,
                )
            )
            if max_examples_per_season and len(season_examples) >= max_examples_per_season:
                season_examples = season_examples[:max_examples_per_season]
                break

        print(
            f"  [{target_season}] Collected {len(season_examples)} examples from {source_season}",
            flush=True,
        )
        all_examples.extend(season_examples)

    return all_examples


def fit_artifact_for_season(
    *,
    target_season: int,
    training_years: int,
    scoring: str,
    defaults: dict,
    output_dir: Path,
    l2: float,
    max_iter: int,
    max_workers: int,
    max_examples_per_season: int,
    min_context_season: int,
) -> dict:
    examples = collect_examples_for_artifact(
        target_season=target_season,
        training_years=training_years,
        defaults=defaults,
        max_workers=max_workers,
        max_examples_per_season=max_examples_per_season,
        min_context_season=min_context_season,
    )
    fit = fit_conditional_softmax(
        examples,
        DEFAULT_TARGET_SELECTION_FEATURES,
        l2=l2,
        max_iter=max_iter,
    )
    artifact = {
        "schema_version": TARGET_SELECTION_SCHEMA_VERSION,
        "model_type": TARGET_SELECTION_MODEL_TYPE,
        "target_season": target_season,
        "training_seasons": list(range(target_season - training_years, target_season)),
        "training_years": training_years,
        "scoring": scoring,
        "feature_names": list(DEFAULT_TARGET_SELECTION_FEATURES),
        "coefficients": fit.coefficients,
        "diagnostics": {
            "objective": fit.objective,
            "converged": fit.converged,
            "iterations": fit.iterations,
            "num_examples": fit.num_examples,
            "l2": l2,
            "min_context_season": min_context_season,
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"target_selection_{target_season}.json"
    path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n")
    return artifact


def main(argv: list[str] | None = None) -> int:
    args = build_cli().parse_args(argv)
    invalid = [season for season in args.test_seasons if season >= _HOLDOUT_SEASON]
    if invalid:
        raise ValueError(f"Holdout seasons are not fit by this script: {invalid}")

    defaults = load_defaults()
    resolve_scoring(defaults["scoring"], args.scoring)
    max_workers = args.workers or default_max_workers(32)

    started = time.time()
    for season in args.test_seasons:
        print(f"Fitting target-selection artifact for {season}...", flush=True)
        artifact = fit_artifact_for_season(
            target_season=season,
            training_years=args.training_years,
            scoring=args.scoring,
            defaults=defaults,
            output_dir=args.output_dir,
            l2=args.l2,
            max_iter=args.max_iter,
            max_workers=max_workers,
            max_examples_per_season=args.max_examples_per_season,
            min_context_season=args.min_context_season,
        )
        diag = artifact["diagnostics"]
        print(
            f"  wrote target_selection_{season}.json "
            f"examples={diag['num_examples']} converged={diag['converged']}",
            flush=True,
        )

    print(f"Completed in {time.time() - started:.1f}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

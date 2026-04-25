"""Fit learned pass/run play-call artifacts.

The fitted artifact is off by default at runtime. This script writes one JSON
artifact per target season using leak-free prior seasons as labels.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import polars as pl

from fantasy_sim.data.loader import DataLoader
from fantasy_sim.data.play_call_model.models import (
    DEFAULT_PLAY_CALL_FEATURES,
    PLAY_CALL_MODEL_SCHEMA_VERSION,
    PLAY_CALL_MODEL_TYPE,
)
from fantasy_sim.data.play_call_model.training import (
    PlayCallTrainingExample,
    build_example_from_row,
    fit_logistic_play_call,
    source_seasons_for_artifact,
)

_REQUIRED_PBP_COLUMNS = frozenset(
    {
        "play_type",
        "posteam",
        "defteam",
        "home_team",
        "away_team",
        "down",
        "ydstogo",
        "yardline_100",
    }
)


def build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fit learned pass/run play-call artifacts.",
    )
    parser.add_argument("--test-seasons", type=int, nargs="+", required=True)
    parser.add_argument("--min-source-season", type=int, default=2018)
    parser.add_argument("--training-years", type=int, default=4)
    parser.add_argument("--l2", type=float, default=1.0)
    parser.add_argument("--max-iter", type=int, default=200)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def collect_examples_from_pbp(
    pbp: pl.DataFrame,
    feature_names: tuple[str, ...] = DEFAULT_PLAY_CALL_FEATURES,
) -> list[PlayCallTrainingExample]:
    if pbp.is_empty():
        return []

    missing = sorted(_REQUIRED_PBP_COLUMNS.difference(pbp.columns))
    if missing:
        raise ValueError(f"PBP data is missing required columns: {missing}")

    examples: list[PlayCallTrainingExample] = []
    for row in pbp.filter(pl.col("play_type").is_in(["pass", "run"])).iter_rows(named=True):
        example = build_example_from_row(row, feature_names)
        if example is not None:
            examples.append(example)
    return examples


def fit_artifact_for_season(
    loader: DataLoader,
    target_season: int,
    min_source_season: int,
    training_years: int,
    output_dir: Path,
    l2: float,
    max_iter: int,
) -> dict:
    source_seasons = source_seasons_for_artifact(
        target_season=target_season,
        min_source_season=min_source_season,
        training_years=training_years,
    )
    if not source_seasons:
        raise ValueError(f"No source seasons available for target season {target_season}")

    pbp = loader.load_pbp(source_seasons)
    examples = collect_examples_from_pbp(pbp, DEFAULT_PLAY_CALL_FEATURES)
    fit = fit_logistic_play_call(
        examples,
        DEFAULT_PLAY_CALL_FEATURES,
        l2=l2,
        max_iter=max_iter,
    )
    pass_rate = sum(example.label for example in examples) / len(examples)
    artifact = {
        "schema_version": PLAY_CALL_MODEL_SCHEMA_VERSION,
        "model_type": PLAY_CALL_MODEL_TYPE,
        "target_season": target_season,
        "source_seasons": source_seasons,
        "feature_names": list(DEFAULT_PLAY_CALL_FEATURES),
        "coefficients": fit.coefficients,
        "probability_clamp": [0.05, 0.95],
        "diagnostics": {
            "num_examples": fit.num_examples,
            "pass_rate": pass_rate,
            "objective": fit.objective,
            "converged": fit.converged,
            "iterations": fit.iterations,
            "l2": l2,
        },
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"play_call_model_{target_season}.json"
    path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n")
    return artifact


def main(argv: list[str] | None = None) -> int:
    args = build_cli().parse_args(argv)
    loader = DataLoader()
    started = time.time()

    for season in args.test_seasons:
        print(f"Fitting play-call artifact for {season}...", flush=True)
        artifact = fit_artifact_for_season(
            loader,
            season,
            args.min_source_season,
            args.training_years,
            args.output_dir,
            args.l2,
            args.max_iter,
        )
        diag = artifact["diagnostics"]
        print(
            f"  wrote play_call_model_{season}.json "
            f"examples={diag['num_examples']} "
            f"pass_rate={diag['pass_rate']:.3f} "
            f"converged={diag['converged']}",
            flush=True,
        )

    print(f"Completed in {time.time() - started:.1f}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

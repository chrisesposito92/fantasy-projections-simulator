"""Fit learned QB designed-run artifacts."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import polars as pl

from fantasy_sim.data.loader import DataLoader
from fantasy_sim.data.qb_rushing import (
    DEFAULT_QB_DESIGNED_RUN_FEATURES,
    QB_DESIGNED_RUN_MODEL_TYPE,
    QB_DESIGNED_RUN_SCHEMA_VERSION,
    annotate_rusher_positions,
    build_designed_run_example_from_row,
    build_designed_run_priors,
    build_designed_run_tail_buckets,
    fit_logistic_qb_designed_run,
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
        "rusher_player_id",
        "qb_scramble",
        "yards_gained",
    }
)


def build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fit learned QB designed-run artifacts.")
    parser.add_argument("--test-seasons", type=int, nargs="+", required=True)
    parser.add_argument("--min-source-season", type=int, default=2018)
    parser.add_argument("--training-years", type=int, default=4)
    parser.add_argument("--l2", type=float, default=1.0)
    parser.add_argument("--max-iter", type=int, default=200)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def _positions_from_rosters(rosters: pl.DataFrame) -> dict[str, str]:
    missing = sorted({"player_id", "position"}.difference(rosters.columns))
    if missing:
        raise ValueError(f"Roster data is missing required columns: {missing}")
    return {
        str(row["player_id"]): str(row["position"])
        for row in rosters.iter_rows(named=True)
        if row.get("player_id") not in (None, "") and row.get("position") not in (None, "")
    }


def _qb_ids_from_rosters(rosters: pl.DataFrame) -> tuple[dict[tuple[object, object, str], str], str | None]:
    team_column = next((name for name in ("team", "recent_team", "club") if name in rosters.columns), None)
    by_team_week: dict[tuple[object, object, str], str] = {}
    qb_ids: set[str] = set()
    for row in rosters.iter_rows(named=True):
        if row.get("position") != "QB" or row.get("player_id") in (None, ""):
            continue
        player_id = str(row["player_id"])
        qb_ids.add(player_id)
        if team_column is not None and row.get(team_column) not in (None, ""):
            by_team_week[(row.get("season"), row.get("week"), str(row[team_column]))] = player_id
    fallback = next(iter(qb_ids)) if len(qb_ids) == 1 else None
    return by_team_week, fallback


def _annotate_offense_qbs(rows: list[dict[str, object]], rosters: pl.DataFrame) -> list[dict[str, object]]:
    by_team_week, fallback = _qb_ids_from_rosters(rosters)
    for row in rows:
        if any(row.get(key) not in (None, "") for key in ("qb_player_id", "offense_qb_player_id", "posteam_qb_player_id", "passer_player_id")):
            continue
        row["offense_qb_player_id"] = by_team_week.get(
            (row.get("season"), row.get("week"), str(row.get("posteam"))),
            fallback,
        )
    return rows


def collect_examples_from_pbp(pbp: pl.DataFrame, rosters: pl.DataFrame):
    missing = sorted(_REQUIRED_PBP_COLUMNS.difference(pbp.columns))
    if missing:
        raise ValueError(f"PBP data is missing required columns: {missing}")
    rows = annotate_rusher_positions(list(pbp.iter_rows(named=True)), _positions_from_rosters(rosters))
    rows = _annotate_offense_qbs(rows, rosters)
    priors = build_designed_run_priors(rows)
    examples = []
    for row in rows:
        example = build_designed_run_example_from_row(row, DEFAULT_QB_DESIGNED_RUN_FEATURES, priors)
        if example is not None:
            examples.append(example)
    tail_buckets = build_designed_run_tail_buckets(rows, mobility_tiers=priors.mobility_tiers)
    return examples, priors, tail_buckets


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
    rosters = loader.load_rosters(source_seasons)
    examples, priors, tail_buckets = collect_examples_from_pbp(pbp, rosters)
    fit = fit_logistic_qb_designed_run(
        examples,
        DEFAULT_QB_DESIGNED_RUN_FEATURES,
        l2=l2,
        max_iter=max_iter,
    )
    designed_qb_rate = sum(example.label for example in examples) / len(examples)
    artifact = {
        "schema_version": QB_DESIGNED_RUN_SCHEMA_VERSION,
        "model_type": QB_DESIGNED_RUN_MODEL_TYPE,
        "target_season": target_season,
        "source_seasons": source_seasons,
        "feature_names": list(DEFAULT_QB_DESIGNED_RUN_FEATURES),
        "coefficients": fit.coefficients,
        "factor_clamp": [0.50, 2.00],
        "priors": {
            "qb": priors.qb,
            "team": priors.team,
            "opponent_allowed": priors.opponent_allowed,
            "league": priors.league,
            "mobility_tiers": priors.mobility_tiers,
        },
        "tail_buckets": {key: list(values) for key, values in tail_buckets.items()},
        "diagnostics": {
            "num_examples": fit.num_examples,
            "designed_qb_run_rate": designed_qb_rate,
            "objective": fit.objective,
            "converged": fit.converged,
            "iterations": fit.iterations,
            "l2": l2,
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"qb_designed_run_model_{target_season}.json"
    path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return artifact


def main(argv: list[str] | None = None) -> int:
    args = build_cli().parse_args(argv)
    loader = DataLoader()
    started = time.time()
    for season in args.test_seasons:
        print(f"Fitting QB designed-run artifact for {season}...", flush=True)
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
            f"  wrote qb_designed_run_model_{season}.json "
            f"examples={diag['num_examples']} "
            f"designed_qb_run_rate={diag['designed_qb_run_rate']:.3f} "
            f"converged={diag['converged']}",
            flush=True,
        )
    print(f"Completed in {time.time() - started:.1f}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

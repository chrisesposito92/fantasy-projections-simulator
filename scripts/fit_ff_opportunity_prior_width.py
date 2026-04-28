"""Fit per-position residual std for KS-13 Path B (ff_opportunity prior width).

Approach: for each (player, week) row in the training-season FF Opportunity
weekly frame, compute residual = actual_fpts - total_fantasy_points_exp.
Group residuals by position; per-group std = empirical residual std.
Bayesian-shrunk std toward league-wide std with PRIOR_N = 50 to avoid noisy
buckets when n is small.

This script mirrors scripts/fit_residual_calibration.py structure:
  --test-seasons, --min-source-season, --training-years, --scoring, --output-dir
Output: prior_width_<test_season>.json with schema_version=1 and per-position
  std_fpts buckets.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import polars as pl

from fantasy_sim.config.loader import load_defaults, resolve_scoring
from fantasy_sim.data.actuals import load_actual_scores
from fantasy_sim.data.ensemble.loader import FfOpportunityLoader
from fantasy_sim.data.ensemble.models import FfOpportunityConfig
from fantasy_sim.data.loader import DataLoader

ARTIFACT_SCHEMA_VERSION = 1
PRIOR_N = 50  # Bayesian shrinkage strength toward league-wide std


def _load_actuals_by_player_week(
    seasons: list[int],
    scoring: str,
) -> dict[tuple[str, int, int], float]:
    """Load actual weekly fantasy points keyed by (player_id, season, week).

    Uses the same DataLoader + load_actual_scores pattern as
    fit_residual_calibration.py (lines 210-216).
    """
    defaults = load_defaults()
    scoring_presets = defaults.get("scoring", {})
    scoring_config = resolve_scoring(scoring_presets, scoring)
    loader = DataLoader()

    actuals_by_key: dict[tuple[str, int, int], float] = {}
    for season in seasons:
        player_stats = loader.load_player_stats([season])
        actuals = load_actual_scores(player_stats, scoring_config, season)
        for actual in actuals:
            key = (actual.player_id, actual.season, actual.week)
            actuals_by_key[key] = actual.fpts

    return actuals_by_key


def fit_one_test_season(
    *,
    test_season: int,
    source_seasons: list[int],
    sims: int,
    scoring: str,
) -> dict:
    """Fit per-position std on training seasons; emit one artifact dict.

    Codex cycle-2 alignment: uses the REAL loader API
    (FfOpportunityLoader.load_weekly per src/fantasy_sim/data/ensemble/loader.py
    line 43). Earlier drafts referenced fictional EnsembleLoader.load_week_raw.
    """
    if not source_seasons:
        return {
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "scoring": scoring,
            "test_season": test_season,
            "source_seasons": list(source_seasons),
            "sims": sims,
            "buckets": {},
        }

    loader = FfOpportunityLoader(config=FfOpportunityConfig())
    raw_df = loader.load_weekly(source_seasons)

    if raw_df.is_empty() or "total_fantasy_points_exp" not in raw_df.columns:
        print(
            f"  [{test_season}] WARNING: FF Opportunity data empty or missing "
            f"'total_fantasy_points_exp' — skipping artifact.",
            file=sys.stderr,
            flush=True,
        )
        return {
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "scoring": scoring,
            "test_season": test_season,
            "source_seasons": list(source_seasons),
            "sims": sims,
            "buckets": {},
        }

    # Load actuals for training seasons
    actuals_by_key = _load_actuals_by_player_week(source_seasons, scoring)
    if not actuals_by_key:
        print(
            f"  [{test_season}] WARNING: No actual scores found for seasons "
            f"{source_seasons} — skipping artifact.",
            file=sys.stderr,
            flush=True,
        )
        return {
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "scoring": scoring,
            "test_season": test_season,
            "source_seasons": list(source_seasons),
            "sims": sims,
            "buckets": {},
        }

    # Join actuals to ff_opportunity raw frame, compute residuals per position
    residuals_by_position: dict[str, list[float]] = defaultdict(list)
    all_residuals: list[float] = []

    for row in raw_df.iter_rows(named=True):
        player_id = row.get("player_id")
        season = row.get("season")
        week = row.get("week")
        prior_fpts = row.get("total_fantasy_points_exp")
        position = row.get("position", "")

        if not player_id or season is None or week is None or prior_fpts is None:
            continue
        if position not in ("QB", "RB", "WR", "TE"):
            continue

        actual_fpts = actuals_by_key.get((player_id, int(season), int(week)))
        if actual_fpts is None:
            continue

        residual = float(actual_fpts) - float(prior_fpts)
        residuals_by_position[position].append(residual)
        all_residuals.append(residual)

    if not all_residuals:
        print(
            f"  [{test_season}] WARNING: No matched (player, season, week) rows "
            f"— check that FF Opportunity and player_stats cover the same seasons.",
            file=sys.stderr,
            flush=True,
        )
        return {
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "scoring": scoring,
            "test_season": test_season,
            "source_seasons": list(source_seasons),
            "sims": sims,
            "buckets": {},
        }

    # League-wide std (pooled across all positions)
    import statistics
    league_std = statistics.pstdev(all_residuals) if len(all_residuals) > 1 else 0.0

    buckets: dict[str, dict] = {}
    for position in ("QB", "RB", "WR", "TE"):
        resids = residuals_by_position.get(position, [])
        n = len(resids)
        if n == 0:
            continue
        empirical_std = statistics.pstdev(resids) if n > 1 else 0.0
        # Bayesian-shrunk std: weighted average toward league_std
        shrunk = (n * empirical_std + PRIOR_N * league_std) / (n + PRIOR_N)
        buckets[position] = {
            "std_fpts": round(float(shrunk), 4),
            "empirical_std_fpts": round(float(empirical_std), 4),
            "league_std_fpts": round(float(league_std), 4),
            "n": n,
        }

    print(
        f"  [{test_season}] Fitted {len(buckets)} buckets from {len(all_residuals)} residuals "
        f"(league_std={league_std:.3f})",
        flush=True,
    )

    return {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "scoring": scoring,
        "test_season": test_season,
        "source_seasons": list(source_seasons),
        "sims": sims,
        "buckets": buckets,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fit KS-13 Path B prior-width artifacts (ff_opportunity residual std per position)."
    )
    parser.add_argument(
        "--test-seasons", type=int, nargs="+", required=True,
        help="Test seasons to fit artifacts for (e.g. 2022 2023 2024).",
    )
    parser.add_argument(
        "--min-source-season", type=int, required=True,
        help="Earliest training season (e.g. 2020).",
    )
    parser.add_argument(
        "--training-years", type=int, default=4,
        help="Number of training years before test season (default 4).",
    )
    parser.add_argument(
        "--sims", type=int, default=200,
        help="Number of simulations used (recorded in artifact metadata; default 200).",
    )
    parser.add_argument(
        "--scoring", type=str, default="ppr",
        choices=["ppr", "half_ppr", "standard"],
        help="Scoring format (default ppr).",
    )
    parser.add_argument(
        "--output-dir", type=Path, required=True,
        help="Directory to write prior_width_<season>.json artifacts.",
    )
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    for test_season in args.test_seasons:
        source_seasons = list(range(
            max(args.min_source_season, test_season - args.training_years),
            test_season,
        ))
        print(
            f"Fitting prior_width_{test_season}.json "
            f"(source_seasons={source_seasons}, scoring={args.scoring})",
            flush=True,
        )
        artifact = fit_one_test_season(
            test_season=test_season,
            source_seasons=source_seasons,
            sims=args.sims,
            scoring=args.scoring,
        )
        out_path = args.output_dir / f"prior_width_{test_season}.json"
        with out_path.open("w") as f:
            json.dump(artifact, f, indent=2)
        n_buckets = len(artifact["buckets"])
        print(f"  -> Wrote {out_path} (n_buckets={n_buckets})", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

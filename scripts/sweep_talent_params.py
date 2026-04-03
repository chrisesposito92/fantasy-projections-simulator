"""Sensitivity sweep over TalentStabilizer prior_strength × min_divergence.

Runs an A/B backtest for each (prior_strength, min_divergence) combination
to find optimal PFF talent stabilizer hyperparameters.

Usage:
    uv run python scripts/sweep_talent_params.py
    uv run python scripts/sweep_talent_params.py --sims 50 --season 2024
    uv run python scripts/sweep_talent_params.py --apply
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running from the repo root without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from fantasy_sim.config.loader import load_defaults, resolve_scoring
from fantasy_sim.data.pff.models import MatchupConfig, PffConfig, TalentConfig
from fantasy_sim.validation.backtester import Backtester

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_PRIOR_STRENGTHS: list[float] = [20, 30, 40, 60, 80]
DEFAULT_MIN_DIVERGENCES: list[float] = [0.01, 0.02, 0.03, 0.05]

POSITIONS = ("QB", "RB", "WR", "TE")


# ---------------------------------------------------------------------------
# Grid builder
# ---------------------------------------------------------------------------

def build_sweep_grid(
    prior_strengths: list[float] = DEFAULT_PRIOR_STRENGTHS,
    min_divergences: list[float] = DEFAULT_MIN_DIVERGENCES,
) -> list[dict]:
    """Build the full Cartesian product sweep grid.

    Args:
        prior_strengths: List of prior_strength values to sweep.
        min_divergences: List of min_divergence values to sweep.

    Returns:
        List of dicts, each with keys ``prior_strength`` and ``min_divergence``.
        Ordered: prior_strength in outer loop, min_divergence in inner loop.
    """
    grid = []
    for ps in prior_strengths:
        for md in min_divergences:
            grid.append({"prior_strength": ps, "min_divergence": md})
    return grid


# ---------------------------------------------------------------------------
# Sweep runner
# ---------------------------------------------------------------------------

def run_sweep(
    grid: list[dict],
    test_season: int,
    n_sims: int,
    num_training_seasons: int,
    scoring_config: dict,
) -> list[dict]:
    """Run A/B backtests for each grid point.

    Runs the baseline (PFF off) once, then runs each grid point with PFF on
    and computes deltas vs the baseline.

    Args:
        grid: List of parameter dicts from ``build_sweep_grid()``.
        test_season: Season to backtest against.
        n_sims: Number of Monte Carlo simulations per game.
        num_training_seasons: Number of seasons of training data.
        scoring_config: Resolved scoring config dict.

    Returns:
        List of result dicts sorted by ``rank_corr_delta`` descending.
        Each dict contains: prior_strength, min_divergence, rank_corr,
        weekly_mae, season_mae, calibration, rank_corr_delta,
        weekly_mae_delta, season_mae_delta, calibration_delta.
    """
    # --- Baseline: PFF off ---
    print("Running baseline (PFF off)...")
    baseline_bt = Backtester(
        test_season=test_season,
        n_sims=n_sims,
        num_training_seasons=num_training_seasons,
        pff_config=PffConfig(enabled=False),
    )
    baseline = baseline_bt.run(scoring_config)
    baseline_rank_corr = _mean_rank_corr(baseline.rank_correlations)
    print(
        f"  Baseline: rank_corr={baseline_rank_corr:.4f}  "
        f"wk_mae={baseline.weekly_mae:.2f}  "
        f"szn_mae={baseline.season_mae:.2f}  "
        f"calibr={baseline.boom_bust_calibration:.4f}"
    )
    print()

    results: list[dict] = []

    total = len(grid)
    for i, params in enumerate(grid, 1):
        ps = params["prior_strength"]
        md = params["min_divergence"]
        print(f"[{i:>2}/{total}] prior_strength={ps}  min_divergence={md:.3f} ... ", end="", flush=True)

        pff_cfg = PffConfig(
            enabled=True,
            matchup=MatchupConfig(enabled=False),  # isolate talent stabilizer
            talent=TalentConfig(
                enabled=True,
                prior_strength=ps,
                min_divergence=md,
            ),
        )
        bt = Backtester(
            test_season=test_season,
            n_sims=n_sims,
            num_training_seasons=num_training_seasons,
            pff_config=pff_cfg,
        )
        result = bt.run(scoring_config)
        rc = _mean_rank_corr(result.rank_correlations)

        row = {
            "prior_strength": ps,
            "min_divergence": md,
            "rank_corr": rc,
            "weekly_mae": result.weekly_mae,
            "season_mae": result.season_mae,
            "calibration": result.boom_bust_calibration,
            "rank_corr_delta": rc - baseline_rank_corr,
            "weekly_mae_delta": result.weekly_mae - baseline.weekly_mae,
            "season_mae_delta": result.season_mae - baseline.season_mae,
            "calibration_delta": result.boom_bust_calibration - baseline.boom_bust_calibration,
        }
        results.append(row)
        print(
            f"rank_corr={rc:.4f} (Δ{row['rank_corr_delta']:+.4f})  "
            f"wk_mae={result.weekly_mae:.2f}  "
            f"szn_mae={result.season_mae:.2f}"
        )

    results.sort(key=lambda r: r["rank_corr_delta"], reverse=True)
    return results


def _mean_rank_corr(rank_correlations: dict[str, float]) -> float:
    """Return mean rank correlation across all tracked positions."""
    vals = [rank_correlations.get(pos, 0.0) for pos in POSITIONS]
    return sum(vals) / len(vals) if vals else 0.0


# ---------------------------------------------------------------------------
# Results table printer
# ---------------------------------------------------------------------------

def print_results_table(results: list[dict]) -> None:
    """Print an ASCII results table sorted by rank_corr_delta descending.

    Columns: #, prior_str, min_div, rank_corr, wk_mae, szn_mae, calibr.
    The top result is marked with "<-- BEST".

    Args:
        results: List of result dicts as returned by ``run_sweep()``.
    """
    if not results:
        print("No results to display.")
        return

    header = (
        f"{'#':>3}  {'prior_str':>9}  {'min_div':>7}  "
        f"{'rank_corr':>9}  {'wk_mae':>6}  {'szn_mae':>7}  {'calibr':>7}"
    )
    separator = "-" * len(header)

    print()
    print("=" * len(header))
    print("  TALENT PARAMETER SWEEP RESULTS  (sorted by rank_corr_delta)")
    print("=" * len(header))
    print(header)
    print(separator)

    for i, row in enumerate(results, 1):
        marker = "  <-- BEST" if i == 1 else ""
        line = (
            f"{i:>3}  "
            f"{row['prior_strength']:>9.0f}  "
            f"{row['min_divergence']:>7.3f}  "
            f"{row['rank_corr']:>9.4f}  "
            f"{row['weekly_mae']:>6.2f}  "
            f"{row['season_mae']:>7.1f}  "
            f"{row['calibration']:>7.4f}"
            f"{marker}"
        )
        print(line)

    print(separator)
    best = results[0]
    print(
        f"\nBest: prior_strength={best['prior_strength']:.0f}  "
        f"min_divergence={best['min_divergence']:.3f}  "
        f"rank_corr_delta={best['rank_corr_delta']:+.4f}"
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Grid search over TalentStabilizer prior_strength × min_divergence.\n\n"
            "Runs A/B backtests for each (prior_strength, min_divergence) pair\n"
            "and ranks by rank_corr improvement vs PFF-off baseline.\n\n"
            "Requires cached PBP/roster data in ~/.fantasy-sim/cache/.\n"
            "PFF parquet data is optional; talent stabilizer uses PBP-derived priors."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--sims",
        type=int,
        default=30,
        metavar="N",
        help="Number of Monte Carlo simulations per game (default: 30).",
    )
    parser.add_argument(
        "--season",
        type=int,
        default=2024,
        metavar="YYYY",
        help="Season to backtest against (default: 2024).",
    )
    parser.add_argument(
        "--training-years",
        type=int,
        default=2,
        dest="training_years",
        metavar="N",
        help="Number of training seasons before the test season (default: 2).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="After sweep, print best params formatted for defaults.yaml.",
    )
    parser.add_argument(
        "--prior-strengths",
        type=float,
        nargs="+",
        default=None,
        dest="prior_strengths",
        metavar="V",
        help=(
            "Override list of prior_strength values "
            f"(default: {DEFAULT_PRIOR_STRENGTHS})."
        ),
    )
    parser.add_argument(
        "--min-divergences",
        type=float,
        nargs="+",
        default=None,
        dest="min_divergences",
        metavar="V",
        help=(
            "Override list of min_divergence values "
            f"(default: {DEFAULT_MIN_DIVERGENCES})."
        ),
    )
    args = parser.parse_args()

    prior_strengths = args.prior_strengths or DEFAULT_PRIOR_STRENGTHS
    min_divergences = args.min_divergences or DEFAULT_MIN_DIVERGENCES

    grid = build_sweep_grid(
        prior_strengths=prior_strengths,
        min_divergences=min_divergences,
    )

    defaults = load_defaults()
    scoring_config = resolve_scoring(defaults["scoring"], "ppr")

    print("=" * 68)
    print("  TALENT PARAMETER SWEEP")
    print("=" * 68)
    print(f"  Season        : {args.season}")
    print(f"  Sims          : {args.sims}")
    print(f"  Training yrs  : {args.training_years}")
    print(f"  Grid points   : {len(grid)}")
    print(f"  prior_strengths : {prior_strengths}")
    print(f"  min_divergences : {min_divergences}")
    print("=" * 68)
    print()

    results = run_sweep(
        grid=grid,
        test_season=args.season,
        n_sims=args.sims,
        num_training_seasons=args.training_years,
        scoring_config=scoring_config,
    )

    print_results_table(results)

    if args.apply and results:
        best = results[0]
        print("\n" + "=" * 68)
        print("  APPLY TO config/defaults.yaml")
        print("=" * 68)
        print("""
  Update the pff.talent section:

  pff:
    talent:
      enabled: true
      prior_strength: {ps:.0f}
      min_divergence: {md:.3f}
""".format(ps=best["prior_strength"], md=best["min_divergence"]))

    return 0


if __name__ == "__main__":
    sys.exit(main())

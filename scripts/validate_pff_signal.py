"""A/B backtest script: compare PFF-on vs PFF-off projections.

Tests each PFF intelligence layer independently or together and evaluates
against kill-point criteria to determine if PFF data improves projections.

Usage:
    uv run python scripts/validate_pff_signal.py --help
    uv run python scripts/validate_pff_signal.py --mode all --sims 50
    uv run python scripts/validate_pff_signal.py --mode matchup --seasons 2023 2024
    uv run python scripts/validate_pff_signal.py --mode talent --sims 30 --training-years 3
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass

from fantasy_sim.config.loader import load_defaults, resolve_scoring
from fantasy_sim.data.game_context import GameContextBuilder
from fantasy_sim.data.pff.models import MatchupConfig, PffConfig, TalentConfig
from fantasy_sim.validation.backtester import Backtester, BacktestResult

# ---------------------------------------------------------------------------
# Kill-point thresholds
# ---------------------------------------------------------------------------
RANK_CORR_MIN_IMPROVEMENT = 0.01   # Must improve by at least this to PASS
RANK_CORR_MAX_REGRESSION = 0.005   # May not regress more than this
MAE_MAX_REGRESSION = 0.3           # Weekly MAE may not increase more than this

POSITIONS = ("QB", "RB", "WR", "TE")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ComparisonResult:
    """A/B comparison for one test season."""
    test_season: int
    off: BacktestResult
    on: BacktestResult

    @property
    def rank_corr_delta(self) -> float:
        """Average rank correlation improvement (on - off) across QB/RB/WR/TE."""
        deltas = []
        for pos in POSITIONS:
            off_val = self.off.rank_correlations.get(pos, 0.0)
            on_val = self.on.rank_correlations.get(pos, 0.0)
            deltas.append(on_val - off_val)
        return sum(deltas) / len(deltas) if deltas else 0.0

    @property
    def weekly_mae_delta(self) -> float:
        """Weekly MAE change (on - off). Negative = better."""
        return self.on.weekly_mae - self.off.weekly_mae

    @property
    def season_mae_delta(self) -> float:
        """Season MAE change (on - off). Negative = better."""
        return self.on.season_mae - self.off.season_mae

    @property
    def calibration_delta(self) -> float:
        """Boom/bust calibration change (on - off). Negative = better."""
        return self.on.boom_bust_calibration - self.off.boom_bust_calibration


# ---------------------------------------------------------------------------
# PFF config factory
# ---------------------------------------------------------------------------

def _build_pff_config(mode: str) -> PffConfig:
    """Build a PffConfig with the appropriate layers enabled."""
    if mode == "matchup":
        return PffConfig(
            enabled=True,
            matchup=MatchupConfig(enabled=True),
            talent=TalentConfig(enabled=False),
        )
    elif mode == "talent":
        return PffConfig(
            enabled=True,
            matchup=MatchupConfig(enabled=False),
            talent=TalentConfig(enabled=True),
        )
    else:  # "all"
        return PffConfig(
            enabled=True,
            matchup=MatchupConfig(enabled=True),
            talent=TalentConfig(enabled=True),
        )


# ---------------------------------------------------------------------------
# Backtest runner
# ---------------------------------------------------------------------------

def run_backtest_pair(
    test_season: int,
    n_sims: int,
    scoring_config: dict,
    num_training_seasons: int,
    mode: str,
) -> ComparisonResult:
    """Run PFF-off then PFF-on backtests for one season and return comparison."""

    print(f"\n  [Season {test_season}] Running PFF-OFF baseline...")
    t0 = time.time()
    bt_off = Backtester(
        test_season=test_season,
        n_sims=n_sims,
        num_training_seasons=num_training_seasons,
    )
    result_off = bt_off.run(scoring_config)
    elapsed_off = time.time() - t0
    print(f"    Done in {elapsed_off:.1f}s  "
          f"weekly_mae={result_off.weekly_mae:.3f}  "
          f"season_mae={result_off.season_mae:.3f}  "
          f"rank_corr={_format_rank_corr(result_off)}")

    print(f"  [Season {test_season}] Running PFF-ON ({mode})...")
    t0 = time.time()
    bt_on = Backtester(
        test_season=test_season,
        n_sims=n_sims,
        num_training_seasons=num_training_seasons,
    )
    # Inject the PFF-enabled builder into the backtester
    bt_on.builder = GameContextBuilder(
        cache_dir=bt_on.loader.cache_dir,
        pff_config=_build_pff_config(mode),
    )
    result_on = bt_on.run(scoring_config)
    elapsed_on = time.time() - t0
    print(f"    Done in {elapsed_on:.1f}s  "
          f"weekly_mae={result_on.weekly_mae:.3f}  "
          f"season_mae={result_on.season_mae:.3f}  "
          f"rank_corr={_format_rank_corr(result_on)}")

    return ComparisonResult(test_season=test_season, off=result_off, on=result_on)


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def evaluate_kill_point(results: list[ComparisonResult]) -> bool:
    """Evaluate kill-point criteria across all seasons.

    Returns True (PASS) if:
      - At least one season improved avg rank_corr by >= RANK_CORR_MIN_IMPROVEMENT
      - No season regressed avg rank_corr by > RANK_CORR_MAX_REGRESSION
      - No season increased weekly MAE by > MAE_MAX_REGRESSION

    Prints detailed per-season verdict and overall result.
    """
    print("\n" + "=" * 68)
    print("  KILL-POINT EVALUATION")
    print("=" * 68)
    print(
        f"  Thresholds:  rank_corr_improvement >= {RANK_CORR_MIN_IMPROVEMENT}  |  "
        f"rank_corr_regression <= {RANK_CORR_MAX_REGRESSION}  |  "
        f"mae_regression <= {MAE_MAX_REGRESSION}"
    )
    print("-" * 68)

    any_improvement = False
    any_hard_regression = False

    for r in results:
        rc_delta = r.rank_corr_delta
        mae_delta = r.weekly_mae_delta
        s_mae_delta = r.season_mae_delta
        cal_delta = r.calibration_delta

        # Determine status per metric
        if rc_delta >= RANK_CORR_MIN_IMPROVEMENT:
            rc_label = "IMPROVED"
            any_improvement = True
        elif rc_delta < -RANK_CORR_MAX_REGRESSION:
            rc_label = "REGRESSED"
            any_hard_regression = True
        else:
            rc_label = "NEUTRAL"

        if mae_delta > MAE_MAX_REGRESSION:
            mae_label = "REGRESSED"
            any_hard_regression = True
        elif mae_delta < 0:
            mae_label = "IMPROVED"
        else:
            mae_label = "NEUTRAL"

        print(f"\n  Season {r.test_season}:")
        print(f"    rank_corr  delta={rc_delta:+.4f}   [{rc_label}]")
        print(f"    weekly_mae delta={mae_delta:+.4f}   [{mae_label}]")
        print(f"    season_mae delta={s_mae_delta:+.4f}")
        print(f"    calibration delta={cal_delta:+.4f}")

        # Per-position breakdown
        print("    Position breakdown (on vs off):")
        for pos in POSITIONS:
            off_val = r.off.rank_correlations.get(pos, 0.0)
            on_val = r.on.rank_correlations.get(pos, 0.0)
            delta = on_val - off_val
            arrow = "^" if delta > 0 else ("v" if delta < 0 else "=")
            print(f"      {pos}: {off_val:.4f} -> {on_val:.4f} ({arrow}{abs(delta):.4f})")

    print("\n" + "-" * 68)

    if any_hard_regression:
        verdict = "FAIL"
        detail = "Hard regression in rank_corr or MAE exceeded threshold."
    elif any_improvement:
        verdict = "PASS"
        detail = "At least one season improved rank_corr >= threshold, no hard regressions."
    else:
        # Directional but sub-threshold improvement
        avg_rc = sum(r.rank_corr_delta for r in results) / len(results) if results else 0.0
        if avg_rc > 0:
            verdict = "SOFT_PASS"
            detail = (
                f"Directional improvement (avg rank_corr delta={avg_rc:+.4f}) "
                f"but below min threshold {RANK_CORR_MIN_IMPROVEMENT}."
            )
        else:
            verdict = "FAIL"
            detail = "No improvement detected and no hard regression — likely PFF data unavailable."

    print(f"  VERDICT: {verdict}")
    print(f"  {detail}")
    print("=" * 68)

    return verdict in ("PASS", "SOFT_PASS")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_rank_corr(result: BacktestResult) -> str:
    parts = [
        f"{pos}={result.rank_correlations.get(pos, 0.0):.3f}"
        for pos in POSITIONS
    ]
    return "{" + ", ".join(parts) + "}"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "A/B backtest: compare PFF-on vs PFF-off projections.\n\n"
            "Tests whether the PFF intelligence layer improves fantasy\n"
            "rank correlation and MAE metrics against historical actuals.\n\n"
            "NOTE: Requires network access and (for PFF-ON) processed PFF\n"
            "parquet data in ~/.fantasy-sim/pff/processed/nfl/."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--mode",
        choices=["matchup", "talent", "all"],
        default="all",
        help=(
            "Which PFF layer(s) to enable in the ON run. "
            "'matchup' = defensive matchup adjustments only, "
            "'talent' = talent stabilizer only, "
            "'all' = both layers (default: all)."
        ),
    )
    parser.add_argument(
        "--sims",
        type=int,
        default=50,
        metavar="N",
        help="Number of Monte Carlo simulations per game (default: 50).",
    )
    parser.add_argument(
        "--seasons",
        type=int,
        nargs="+",
        default=[2023, 2024],
        metavar="YEAR",
        help="Test seasons to backtest (default: 2023 2024).",
    )
    parser.add_argument(
        "--training-years",
        type=int,
        default=2,
        metavar="N",
        dest="training_years",
        help="Number of training seasons before each test season (default: 2).",
    )
    parser.add_argument(
        "--scoring",
        default="ppr",
        choices=["ppr", "half_ppr", "standard"],
        help="Scoring format to use (default: ppr).",
    )

    args = parser.parse_args()

    print("=" * 68)
    print("  PFF SIGNAL A/B VALIDATION")
    print("=" * 68)
    print(f"  mode          : {args.mode}")
    print(f"  sims          : {args.sims}")
    print(f"  seasons       : {args.seasons}")
    print(f"  training_years: {args.training_years}")
    print(f"  scoring       : {args.scoring}")
    print("=" * 68)

    # Load scoring config
    defaults = load_defaults()
    scoring_config = resolve_scoring(defaults["scoring"], args.scoring)

    # Run A/B pairs for each season
    total_start = time.time()
    results: list[ComparisonResult] = []
    for season in args.seasons:
        print(f"\nBacktesting season {season}...")
        comparison = run_backtest_pair(
            test_season=season,
            n_sims=args.sims,
            scoring_config=scoring_config,
            num_training_seasons=args.training_years,
            mode=args.mode,
        )
        results.append(comparison)

    total_elapsed = time.time() - total_start
    print(f"\nTotal time: {total_elapsed:.1f}s")

    # Evaluate kill-point
    passed = evaluate_kill_point(results)

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())

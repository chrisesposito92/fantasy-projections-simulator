"""A/B backtest script: compare PFF-on vs PFF-off projections.

Tests each PFF intelligence layer independently or together and evaluates
against kill-point criteria to determine if PFF data improves projections.

Usage:
    uv run python scripts/validate_pff_signal.py --help
    uv run python scripts/validate_pff_signal.py --mode all --sims 50
    uv run python scripts/validate_pff_signal.py --mode matchup --seasons 2023 2024
    uv run python scripts/validate_pff_signal.py --mode talent --sims 30 --training-years 3
    uv run python scripts/validate_pff_signal.py --label "baseline-v1" --mode all --sims 50
    uv run python scripts/validate_pff_signal.py --show-ledger
    uv run python scripts/validate_pff_signal.py --config-override '{"talent": {"prior_strength": 30}}'
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from fantasy_sim.config.loader import load_defaults, resolve_scoring
from fantasy_sim.data.pff.models import MatchupConfig, PffConfig, TalentConfig
from fantasy_sim.validation.backtester import Backtester, BacktestResult

# ---------------------------------------------------------------------------
# Kill-point thresholds
# ---------------------------------------------------------------------------
RANK_CORR_MIN_IMPROVEMENT = 0.01   # Must improve by at least this to PASS
RANK_CORR_MAX_REGRESSION = 0.005   # May not regress more than this
MAE_MAX_REGRESSION = 0.3           # Weekly MAE may not increase more than this

POSITIONS = ("QB", "RB", "WR", "TE")

LEDGER_PATH = Path(__file__).parent.parent / "results" / "pff_ab_ledger.json"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class SeasonResult:
    """One season's A/B comparison stored in the ledger."""
    test_season: int
    off_weekly_mae: float
    off_season_mae: float
    off_rank_corr: dict[str, float]
    off_calibration: float
    on_weekly_mae: float
    on_season_mae: float
    on_rank_corr: dict[str, float]
    on_calibration: float

    @property
    def rank_corr_delta(self) -> float:
        """Average rank correlation improvement (on - off) across QB/RB/WR/TE."""
        deltas = [
            self.on_rank_corr.get(pos, 0.0) - self.off_rank_corr.get(pos, 0.0)
            for pos in POSITIONS
        ]
        return sum(deltas) / len(deltas) if deltas else 0.0

    @property
    def weekly_mae_delta(self) -> float:
        """Weekly MAE change (on - off). Negative = better."""
        return self.on_weekly_mae - self.off_weekly_mae

    @property
    def season_mae_delta(self) -> float:
        """Season MAE change (on - off). Negative = better."""
        return self.on_season_mae - self.off_season_mae

    @property
    def calibration_delta(self) -> float:
        """Boom/bust calibration change (on - off). Negative = better."""
        return self.on_calibration - self.off_calibration


@dataclass
class LedgerEntry:
    """One A/B test run stored in the ledger."""
    label: str
    timestamp: str
    mode: str
    sims: int
    test_seasons: list[int]
    training_years: int
    pff_config: dict
    season_results: list[SeasonResult]
    verdict: str

    @property
    def avg_rank_corr_delta(self) -> float:
        if not self.season_results:
            return 0.0
        return sum(r.rank_corr_delta for r in self.season_results) / len(self.season_results)

    @property
    def avg_weekly_mae_delta(self) -> float:
        if not self.season_results:
            return 0.0
        return sum(r.weekly_mae_delta for r in self.season_results) / len(self.season_results)

    @property
    def avg_season_mae_delta(self) -> float:
        if not self.season_results:
            return 0.0
        return sum(r.season_mae_delta for r in self.season_results) / len(self.season_results)

    @property
    def avg_calibration_delta(self) -> float:
        if not self.season_results:
            return 0.0
        return sum(r.calibration_delta for r in self.season_results) / len(self.season_results)


# ---------------------------------------------------------------------------
# Ledger I/O
# ---------------------------------------------------------------------------

def load_ledger(path: Path = LEDGER_PATH) -> list[LedgerEntry]:
    """Load ledger entries from JSON. Returns empty list if file doesn't exist."""
    if not Path(path).exists():
        return []
    with open(path) as f:
        raw = json.load(f)
    entries = []
    for item in raw:
        season_results = [SeasonResult(**sr) for sr in item.get("season_results", [])]
        item = dict(item)
        item["season_results"] = season_results
        entries.append(LedgerEntry(**item))
    return entries


def save_ledger(path: Path, entries: list[LedgerEntry]) -> None:
    """Write entries to JSON. Creates parent directories if needed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump([asdict(e) for e in entries], f, indent=2)


def format_progression_table(entries: list[LedgerEntry]) -> str:
    """Return an ASCII table of ledger entries with key metrics."""
    if not entries:
        return "No entries in ledger."

    header = (
        f"{'#':>3}  {'Label':<30}  {'rank_corr':>9}  {'wk_mae':>7}  "
        f"{'szn_mae':>8}  {'calibr':>8}  Verdict"
    )
    sep = "-" * len(header)
    lines = [sep, header, sep]

    for i, e in enumerate(entries, start=1):
        row = (
            f"{i:>3}  {e.label:<30}  {e.avg_rank_corr_delta:>+.4f}    "
            f"{e.avg_weekly_mae_delta:>+.3f}  "
            f"{e.avg_season_mae_delta:>+.3f}    "
            f"{e.avg_calibration_delta:>+.4f}  {e.verdict}"
        )
        lines.append(row)

    lines.append(sep)
    return "\n".join(lines)


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

def _build_pff_config(mode: str, overrides: dict | None = None) -> PffConfig:
    """Build a PffConfig with the appropriate layers enabled.

    Args:
        mode: One of "matchup", "talent", or "all".
        overrides: Optional dict with "talent" and/or "matchup" sub-dicts
            of attribute overrides to apply via setattr.
    """
    if mode == "matchup":
        matchup_cfg = MatchupConfig(enabled=True)
        talent_cfg = TalentConfig(enabled=False)
    elif mode == "talent":
        matchup_cfg = MatchupConfig(enabled=False)
        talent_cfg = TalentConfig(enabled=True)
    else:  # "all"
        matchup_cfg = MatchupConfig(enabled=True)
        talent_cfg = TalentConfig(enabled=True)

    if overrides and "talent" in overrides:
        for key, val in overrides["talent"].items():
            if hasattr(talent_cfg, key):
                # Don't replace dataclass fields with plain dicts
                current = getattr(talent_cfg, key)
                if hasattr(current, '__dataclass_fields__') and isinstance(val, dict):
                    for k, v in val.items():
                        if hasattr(current, k):
                            setattr(current, k, v)
                else:
                    setattr(talent_cfg, key, val)
    if overrides and "matchup" in overrides:
        for key, val in overrides["matchup"].items():
            if hasattr(matchup_cfg, key):
                setattr(matchup_cfg, key, val)

    return PffConfig(enabled=True, matchup=matchup_cfg, talent=talent_cfg)


# ---------------------------------------------------------------------------
# Backtest runner
# ---------------------------------------------------------------------------

def run_backtest_pair(
    test_season: int,
    n_sims: int,
    scoring_config: dict,
    num_training_seasons: int,
    pff_config: PffConfig,
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

    mode_label = (
        "matchup" if pff_config.matchup.enabled and not pff_config.talent.enabled
        else "talent" if pff_config.talent.enabled and not pff_config.matchup.enabled
        else "all"
    )
    print(f"  [Season {test_season}] Running PFF-ON ({mode_label})...")
    t0 = time.time()
    bt_on = Backtester(
        test_season=test_season,
        n_sims=n_sims,
        num_training_seasons=num_training_seasons,
        pff_config=pff_config,
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

def evaluate_kill_point(results: list[ComparisonResult]) -> str:
    """Evaluate kill-point criteria across all seasons.

    Returns verdict string: "PASS", "SOFT_PASS", or "FAIL".

    PASS if:
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

    return verdict


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
    parser.add_argument(
        "--label",
        type=str,
        default=None,
        help="Label for this run in the ledger (required for ledger recording).",
    )
    parser.add_argument(
        "--show-ledger",
        action="store_true",
        help="Print the ledger progression table and exit.",
    )
    parser.add_argument(
        "--config-override",
        type=str,
        default=None,
        dest="config_override",
        metavar="JSON",
        help='PFF config overrides as JSON string. Example: \'{"talent": {"prior_strength": 30}}\'',
    )

    args = parser.parse_args()

    if args.show_ledger:
        entries = load_ledger()
        print(format_progression_table(entries))
        return 0

    # Parse config overrides
    overrides = json.loads(args.config_override) if args.config_override else None

    # Build PFF config once from mode + overrides
    pff_config = _build_pff_config(args.mode, overrides=overrides)

    print("=" * 68)
    print("  PFF SIGNAL A/B VALIDATION")
    print("=" * 68)
    print(f"  mode          : {args.mode}")
    print(f"  sims          : {args.sims}")
    print(f"  seasons       : {args.seasons}")
    print(f"  training_years: {args.training_years}")
    print(f"  scoring       : {args.scoring}")
    if args.label:
        print(f"  label         : {args.label}")
    if overrides:
        print(f"  config_override: {overrides}")
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
            pff_config=pff_config,
        )
        results.append(comparison)

    total_elapsed = time.time() - total_start
    print(f"\nTotal time: {total_elapsed:.1f}s")

    # Evaluate kill-point
    verdict = evaluate_kill_point(results)
    passed = verdict in ("PASS", "SOFT_PASS")

    # Append to ledger if label provided
    if args.label:
        season_results = []
        for r in results:
            season_results.append(SeasonResult(
                test_season=r.test_season,
                off_weekly_mae=r.off.weekly_mae,
                off_season_mae=r.off.season_mae,
                off_rank_corr=r.off.rank_correlations,
                off_calibration=r.off.boom_bust_calibration,
                on_weekly_mae=r.on.weekly_mae,
                on_season_mae=r.on.season_mae,
                on_rank_corr=r.on.rank_correlations,
                on_calibration=r.on.boom_bust_calibration,
            ))
        entry = LedgerEntry(
            label=args.label,
            timestamp=datetime.now().isoformat(timespec="seconds"),
            mode=args.mode,
            sims=args.sims,
            test_seasons=args.seasons,
            training_years=args.training_years,
            pff_config=asdict(pff_config),
            season_results=season_results,
            verdict=verdict,
        )
        ledger = load_ledger()
        ledger.append(entry)
        save_ledger(LEDGER_PATH, ledger)
        print(f"\n  Appended to ledger as #{len(ledger)}: {args.label}")
        print(format_progression_table(ledger))

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())

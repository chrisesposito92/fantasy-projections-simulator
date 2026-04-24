"""Unified A/B validation ledger.

Replaces pff_ab_ledger.json and weekly_ab_ledger.json with a single
results/ab_ledger.json file.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from fantasy_sim.validation.coverage import SignalCoverage
from fantasy_sim.validation.weekly import (
    DirectionalAccuracyResult,
    WeeklyPositionSummary,
)

DEFAULT_LEDGER_PATH = Path(__file__).resolve().parents[3] / "results" / "ab_ledger.json"
CURRENT_LEDGER_SCHEMA_VERSION = 4

POSITIONS = ("QB", "RB", "WR", "TE")


@dataclass
class SeasonMetrics:
    """Per-season, per-arm metrics."""

    test_season: int
    arm_a_rank_corr: dict[str, float]
    arm_b_rank_corr: dict[str, float]
    arm_a_weekly_mae: float
    arm_b_weekly_mae: float
    arm_a_season_mae: float
    arm_b_season_mae: float
    arm_a_calibration: float
    arm_b_calibration: float
    weekly_fpts_ks: dict[str, float | int] = field(default_factory=dict)
    stat_ks: dict[str, dict[str, dict[str, float | int]]] = field(default_factory=dict)

    @property
    def rank_corr_delta(self) -> float:
        """Average rank correlation improvement (B - A) across positions."""
        deltas = [
            self.arm_b_rank_corr.get(pos, 0.0) - self.arm_a_rank_corr.get(pos, 0.0)
            for pos in POSITIONS
        ]
        return sum(deltas) / len(deltas) if deltas else 0.0

    @property
    def weekly_mae_delta(self) -> float:
        """Weekly MAE change (B - A). Negative = better."""
        return self.arm_b_weekly_mae - self.arm_a_weekly_mae

    @property
    def season_mae_delta(self) -> float:
        """Season MAE change (B - A). Negative = better."""
        return self.arm_b_season_mae - self.arm_a_season_mae


@dataclass
class LedgerEntry:
    """One A/B validation run."""

    label: str
    timestamp: str
    sims: int
    test_seasons: list[int]
    training_years: int
    scoring: str
    baseline: str  # "bare" or "defaults"
    overrides: list[str]
    config_snapshot: dict
    season_results: list[SeasonMetrics]
    schema_version: int | None = None
    comparison_mode: str | None = None
    seed_mode: str | None = None
    promotion_evidence_scope: str | None = None
    coverage_summary: dict[str, SignalCoverage] | None = None
    weekly_summaries: list[WeeklyPositionSummary] | None = None
    directional_accuracy: DirectionalAccuracyResult | None = None

    @property
    def avg_rank_corr_delta(self) -> float:
        if not self.season_results:
            return 0.0
        return sum(r.rank_corr_delta for r in self.season_results) / len(
            self.season_results
        )

    @property
    def avg_weekly_mae_delta(self) -> float:
        if not self.season_results:
            return 0.0
        return sum(r.weekly_mae_delta for r in self.season_results) / len(
            self.season_results
        )

    @property
    def avg_season_mae_delta(self) -> float:
        if not self.season_results:
            return 0.0
        return sum(r.season_mae_delta for r in self.season_results) / len(
            self.season_results
        )

    @property
    def avg_weekly_fpts_ks_delta(self) -> float | None:
        values = [
            result.weekly_fpts_ks["delta"]
            for result in self.season_results
            if isinstance(result.weekly_fpts_ks.get("delta"), (int, float))
        ]
        if not values:
            return None
        return float(sum(values) / len(values))


def load_ledger(path: Path = DEFAULT_LEDGER_PATH) -> list[LedgerEntry]:
    """Load ledger entries from JSON. Returns empty list if file doesn't exist."""
    if not path.exists():
        return []
    with open(path) as f:
        raw = json.load(f)
    entries = []
    for item in raw:
        season_results = [SeasonMetrics(**sr) for sr in item.get("season_results", [])]
        ws_raw = item.get("weekly_summaries")
        weekly_summaries = (
            [WeeklyPositionSummary(**ws) for ws in ws_raw] if ws_raw else None
        )
        da_raw = item.get("directional_accuracy")
        da = DirectionalAccuracyResult(**da_raw) if da_raw else None
        coverage_raw = item.get("coverage_summary")
        coverage_summary = (
            {
                name: SignalCoverage(**coverage)
                for name, coverage in coverage_raw.items()
            }
            if coverage_raw
            else None
        )
        item = dict(item)
        item.setdefault("schema_version", None)
        item.setdefault("comparison_mode", None)
        item.setdefault("seed_mode", None)
        item.setdefault("promotion_evidence_scope", None)
        item["season_results"] = season_results
        item["weekly_summaries"] = weekly_summaries
        item["directional_accuracy"] = da
        item["coverage_summary"] = coverage_summary
        entries.append(LedgerEntry(**item))
    return entries


def save_ledger(path: Path, entries: list[LedgerEntry]) -> None:
    """Write ledger entries to JSON."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump([asdict(e) for e in entries], f, indent=2)


def format_ledger_table(entries: list[LedgerEntry]) -> str:
    """Return an ASCII table of ledger entries."""
    if not entries:
        return "No entries in ledger."

    header = (
        f"{'#':>3}  {'Label':<22}  {'baseline':<9}  {'mode':<11}  "
        f"{'overrides':<30}  {'rank_corr':>9}  {'wk_mae':>7}  {'szn_mae':>7}  {'fpts_ks':>7}"
    )
    sep = "=" * len(header)
    lines = [sep, header, "-" * len(header)]

    for i, e in enumerate(entries, start=1):
        overrides_str = ", ".join(e.overrides) if e.overrides else "(none)"
        if len(overrides_str) > 30:
            overrides_str = overrides_str[:27] + "..."
        mode = e.comparison_mode or "legacy"
        row = (
            f"{i:>3}  {e.label:<22}  {e.baseline:<9}  {mode:<11}  {overrides_str:<30}  "
            f"{e.avg_rank_corr_delta:>+.4f}    "
            f"{e.avg_weekly_mae_delta:>+.3f}  "
            f"{e.avg_season_mae_delta:>+.3f}  "
            f"{_format_optional_delta(e.avg_weekly_fpts_ks_delta):>7}"
        )
        lines.append(row)

    lines.append(sep)
    return "\n".join(lines)


def _format_optional_delta(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:+.3f}"

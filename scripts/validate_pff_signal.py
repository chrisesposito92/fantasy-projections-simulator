"""A/B backtest script: compare PFF-on vs PFF-off projections.

Tests each PFF intelligence layer independently or together and evaluates
against kill-point criteria to determine if PFF data improves projections.

Usage:
    uv run python scripts/validate_pff_signal.py --help
    uv run python scripts/validate_pff_signal.py --mode all --sims 50
    uv run python scripts/validate_pff_signal.py --mode matchup --seasons 2023 2024
    uv run python scripts/validate_pff_signal.py --mode talent --sims 30 --training-years 3
    uv run python scripts/validate_pff_signal.py --mode tier --sims 50 --label "tier-v1"
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
from fantasy_sim.data.pff.models import CoverageConfig, DstBaselineConfig, KickerConfig, MatchupConfig, PffConfig, TalentConfig, TeamContextConfig, TierConfig
from fantasy_sim.data.weather.config import load_weather_config
from fantasy_sim.data.weather.models import WeatherConfig
from fantasy_sim.data.vegas.config import load_props_config, load_vegas_config
from fantasy_sim.data.vegas.models import PropsConfig, VegasConfig
from fantasy_sim.data.usage.config import load_usage_config
from fantasy_sim.data.usage.models import UsageConfig, CpoeConfig, NgsConfig, RouteRateConfig
from fantasy_sim.validation.backtester import Backtester, BacktestResult
from fantasy_sim.validation.parallel import default_max_workers

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
        mode: PFF/weather layer combination (e.g. "all", "tier", "matchup+tier").
        overrides: Optional dict with "talent" and/or "matchup" sub-dicts
            of attribute overrides to apply via setattr.
    """
    if mode == "matchup":
        matchup_cfg = MatchupConfig(enabled=True)
        talent_cfg = TalentConfig(enabled=False)
        tier_cfg = TierConfig(enabled=False)
        tc_cfg = TeamContextConfig(enabled=False)
        cov_cfg = CoverageConfig(enabled=False)
        kicker_cfg = KickerConfig(enabled=False)
        dst_cfg = DstBaselineConfig(enabled=False)
    elif mode == "talent":
        matchup_cfg = MatchupConfig(enabled=False)
        talent_cfg = TalentConfig(enabled=True)
        tier_cfg = TierConfig(enabled=False)
        tc_cfg = TeamContextConfig(enabled=False)
        cov_cfg = CoverageConfig(enabled=False)
        kicker_cfg = KickerConfig(enabled=False)
        dst_cfg = DstBaselineConfig(enabled=False)
    elif mode == "tier":
        matchup_cfg = MatchupConfig(enabled=False)
        talent_cfg = TalentConfig(enabled=False)
        tier_cfg = TierConfig(enabled=True)
        tc_cfg = TeamContextConfig(enabled=False)
        cov_cfg = CoverageConfig(enabled=False)
        kicker_cfg = KickerConfig(enabled=False)
        dst_cfg = DstBaselineConfig(enabled=False)
    elif mode == "matchup+tier":
        matchup_cfg = MatchupConfig(enabled=True)
        talent_cfg = TalentConfig(enabled=False)
        tier_cfg = TierConfig(enabled=True)
        tc_cfg = TeamContextConfig(enabled=False)
        cov_cfg = CoverageConfig(enabled=False)
        kicker_cfg = KickerConfig(enabled=False)
        dst_cfg = DstBaselineConfig(enabled=False)
    elif mode == "team_context+tier":
        matchup_cfg = MatchupConfig(enabled=False)
        talent_cfg = TalentConfig(enabled=False)
        tier_cfg = TierConfig(enabled=True)
        tc_cfg = TeamContextConfig(enabled=True)
        cov_cfg = CoverageConfig(enabled=False)
        kicker_cfg = KickerConfig(enabled=False)
        dst_cfg = DstBaselineConfig(enabled=False)
    elif mode == "team_context+tier+matchup":
        matchup_cfg = MatchupConfig(enabled=True)
        talent_cfg = TalentConfig(enabled=False)
        tier_cfg = TierConfig(enabled=True)
        tc_cfg = TeamContextConfig(enabled=True)
        cov_cfg = CoverageConfig(enabled=False)
        kicker_cfg = KickerConfig(enabled=False)
        dst_cfg = DstBaselineConfig(enabled=False)
    elif mode == "ncaa_rookie+tier":
        matchup_cfg = MatchupConfig(enabled=False)
        talent_cfg = TalentConfig(enabled=False)
        tier_cfg = TierConfig(enabled=True)
        tc_cfg = TeamContextConfig(enabled=False)
        cov_cfg = CoverageConfig(enabled=False)
        kicker_cfg = KickerConfig(enabled=False)
        dst_cfg = DstBaselineConfig(enabled=False)
    elif mode == "ncaa_rookie+tier+matchup":
        matchup_cfg = MatchupConfig(enabled=True)
        talent_cfg = TalentConfig(enabled=False)
        tier_cfg = TierConfig(enabled=True)
        tc_cfg = TeamContextConfig(enabled=False)
        cov_cfg = CoverageConfig(enabled=False)
        kicker_cfg = KickerConfig(enabled=False)
        dst_cfg = DstBaselineConfig(enabled=False)
    elif mode == "coverage+tier":
        matchup_cfg = MatchupConfig(enabled=False)
        talent_cfg = TalentConfig(enabled=False)
        tier_cfg = TierConfig(enabled=True)
        tc_cfg = TeamContextConfig(enabled=False)
        cov_cfg = CoverageConfig(enabled=True)
        kicker_cfg = KickerConfig(enabled=False)
        dst_cfg = DstBaselineConfig(enabled=False)
    elif mode == "coverage+tier+matchup":
        matchup_cfg = MatchupConfig(enabled=True)
        talent_cfg = TalentConfig(enabled=False)
        tier_cfg = TierConfig(enabled=True)
        tc_cfg = TeamContextConfig(enabled=False)
        cov_cfg = CoverageConfig(enabled=True)
        kicker_cfg = KickerConfig(enabled=False)
        dst_cfg = DstBaselineConfig(enabled=False)
    elif mode == "kicker":
        matchup_cfg = MatchupConfig(enabled=False)
        talent_cfg = TalentConfig(enabled=False)
        tier_cfg = TierConfig(enabled=False)
        tc_cfg = TeamContextConfig(enabled=False)
        cov_cfg = CoverageConfig(enabled=False)
        kicker_cfg = KickerConfig(enabled=True)
        dst_cfg = DstBaselineConfig(enabled=False)
    elif mode == "dst_baseline":
        matchup_cfg = MatchupConfig(enabled=False)
        talent_cfg = TalentConfig(enabled=False)
        tier_cfg = TierConfig(enabled=False)
        tc_cfg = TeamContextConfig(enabled=False)
        cov_cfg = CoverageConfig(enabled=False)
        kicker_cfg = KickerConfig(enabled=False)
        dst_cfg = DstBaselineConfig(enabled=True)
    elif mode == "kicker+dst_baseline":
        matchup_cfg = MatchupConfig(enabled=False)
        talent_cfg = TalentConfig(enabled=False)
        tier_cfg = TierConfig(enabled=False)
        tc_cfg = TeamContextConfig(enabled=False)
        cov_cfg = CoverageConfig(enabled=False)
        kicker_cfg = KickerConfig(enabled=True)
        dst_cfg = DstBaselineConfig(enabled=True)
    elif mode == "kicker+dst_baseline+tier+matchup+coverage":
        matchup_cfg = MatchupConfig(enabled=True)
        talent_cfg = TalentConfig(enabled=False)
        tier_cfg = TierConfig(enabled=True)
        tc_cfg = TeamContextConfig(enabled=False)
        cov_cfg = CoverageConfig(enabled=True)
        kicker_cfg = KickerConfig(enabled=True)
        dst_cfg = DstBaselineConfig(enabled=True)
    elif mode == "weather":
        matchup_cfg = MatchupConfig(enabled=False)
        talent_cfg = TalentConfig(enabled=False)
        tier_cfg = TierConfig(enabled=False)
        tc_cfg = TeamContextConfig(enabled=False)
        cov_cfg = CoverageConfig(enabled=False)
        kicker_cfg = KickerConfig(enabled=False)
        dst_cfg = DstBaselineConfig(enabled=False)
    elif mode == "weather+tier":
        matchup_cfg = MatchupConfig(enabled=False)
        talent_cfg = TalentConfig(enabled=False)
        tier_cfg = TierConfig(enabled=True)
        tc_cfg = TeamContextConfig(enabled=False)
        cov_cfg = CoverageConfig(enabled=False)
        kicker_cfg = KickerConfig(enabled=False)
        dst_cfg = DstBaselineConfig(enabled=False)
    elif mode == "weather+tier+matchup":
        matchup_cfg = MatchupConfig(enabled=True)
        talent_cfg = TalentConfig(enabled=False)
        tier_cfg = TierConfig(enabled=True)
        tc_cfg = TeamContextConfig(enabled=False)
        cov_cfg = CoverageConfig(enabled=False)
        kicker_cfg = KickerConfig(enabled=False)
        dst_cfg = DstBaselineConfig(enabled=False)
    else:  # "all", "all+weather", "all+vegas", "all+weather+vegas+props", etc.
        matchup_cfg = MatchupConfig(enabled=True)
        talent_cfg = TalentConfig(enabled=False)
        tier_cfg = TierConfig(enabled=True)
        tc_cfg = TeamContextConfig(enabled=False)
        cov_cfg = CoverageConfig(enabled=True)
        kicker_cfg = KickerConfig(enabled=True)
        dst_cfg = DstBaselineConfig(enabled=True)

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
    if overrides and "tier_engine" in overrides:
        for key, val in overrides["tier_engine"].items():
            if not hasattr(tier_cfg, key):
                continue
            if key == "position_grades" and isinstance(val, dict):
                # Merge per-position: only update specified positions/fields
                for pos, grade_overrides in val.items():
                    if pos in tier_cfg.position_grades and isinstance(grade_overrides, dict):
                        for gk, gv in grade_overrides.items():
                            if hasattr(tier_cfg.position_grades[pos], gk):
                                setattr(tier_cfg.position_grades[pos], gk, gv)
            else:
                current = getattr(tier_cfg, key)
                if hasattr(current, '__dataclass_fields__') and isinstance(val, dict):
                    for k, v in val.items():
                        if hasattr(current, k):
                            setattr(current, k, v)
                else:
                    setattr(tier_cfg, key, val)
    if overrides and "team_context" in overrides:
        for key, val in overrides["team_context"].items():
            if hasattr(tc_cfg, key):
                setattr(tc_cfg, key, val)
    if overrides and "ncaa_rookie" in overrides:
        ncaa_cfg = tier_cfg.ncaa_rookie
        for key, val in overrides["ncaa_rookie"].items():
            if key == "draft_confidence" and isinstance(val, dict):
                ncaa_cfg.draft_confidence = {int(k): float(v) for k, v in val.items()}
            elif hasattr(ncaa_cfg, key):
                setattr(ncaa_cfg, key, val)
    if overrides and "coverage" in overrides:
        for key, val in overrides["coverage"].items():
            if hasattr(cov_cfg, key):
                if key == "factor_clamp" and isinstance(val, list):
                    setattr(cov_cfg, key, tuple(val))
                else:
                    setattr(cov_cfg, key, val)
    if overrides and "kicker" in overrides:
        for key, val in overrides["kicker"].items():
            if hasattr(kicker_cfg, key):
                setattr(kicker_cfg, key, val)
    if overrides and "dst_baseline" in overrides:
        for key, val in overrides["dst_baseline"].items():
            if hasattr(dst_cfg, key):
                setattr(dst_cfg, key, val)

    return PffConfig(enabled=True, matchup=matchup_cfg, talent=talent_cfg,
                     tier_engine=tier_cfg, team_context=tc_cfg, coverage=cov_cfg,
                     kicker=kicker_cfg, dst_baseline=dst_cfg)


def _build_weather_config(mode: str, overrides: dict | None = None) -> WeatherConfig | None:
    """Build a WeatherConfig if the mode includes weather.

    Returns None if weather is not part of the mode, or a WeatherConfig
    with enabled=True (and optional overrides applied) if it is.
    Enabled by: "all", "full", or any mode containing "weather".
    """
    if not (mode.startswith("all") or mode.startswith("full") or "weather" in mode):
        return None

    from fantasy_sim.config.loader import load_defaults
    defaults = load_defaults()
    weather_config = load_weather_config(defaults)
    weather_config.enabled = True

    if overrides and "weather" in overrides:
        weather_raw = overrides["weather"]
        for section in ("wind", "temperature", "precipitation"):
            if section in weather_raw:
                sub_config = getattr(weather_config, section)
                for k, v in weather_raw[section].items():
                    setattr(sub_config, k, v)
        if "factor_clamp" in weather_raw:
            weather_config.factor_clamp = tuple(weather_raw["factor_clamp"])
        if "forecast_ttl_hours" in weather_raw:
            weather_config.forecast_ttl_hours = weather_raw["forecast_ttl_hours"]

    return weather_config


def _build_vegas_config(mode: str, overrides: dict | None = None) -> VegasConfig | None:
    """Build a VegasConfig if the mode includes vegas.

    Returns None if Vegas is not part of the mode, or a VegasConfig
    with enabled=True (and optional overrides applied) if it is.
    Enabled by: "all", "full", or any mode containing "vegas".

    - mode "vegas": ITT volume factor only (spread_sensitivity=0).
    - mode "vegas+spread": both ITT and spread pass-rate factors active.
    """
    if not (mode.startswith("all") or mode.startswith("full") or "vegas" in mode):
        return None

    defaults = load_defaults()
    vegas_config = load_vegas_config(defaults)
    vegas_config.enabled = True

    if mode == "vegas":
        # ITT-only mode: disable spread conditioning
        vegas_config.spread_sensitivity = 0.0

    if overrides and "vegas" in overrides:
        vegas_raw = overrides["vegas"]
        for key in ("itt_sensitivity", "spread_sensitivity", "enabled"):
            if key in vegas_raw:
                setattr(vegas_config, key, vegas_raw[key])
        if "itt_clamp" in vegas_raw:
            vegas_config.itt_clamp = tuple(vegas_raw["itt_clamp"])
        if "spread_clamp" in vegas_raw:
            vegas_config.spread_clamp = tuple(vegas_raw["spread_clamp"])

    return vegas_config


def _build_props_config(mode: str, overrides: dict | None = None) -> PropsConfig | None:
    """Build a PropsConfig if the mode includes props.

    Returns None if props are not part of the mode, or a PropsConfig with
    enabled=True when mode contains "props".
    Enabled by: "all", "full", or any mode containing "props".
    """
    if not (mode.startswith("all") or mode.startswith("full") or "props" in mode):
        return None

    defaults = load_defaults()
    props_config = load_props_config(defaults)
    props_config.enabled = True
    return props_config


def _build_usage_config(mode: str, overrides: dict | None = None) -> UsageConfig | None:
    """Build UsageConfig if the mode includes usage signals.

    Returns None if usage is not part of the mode.
    Supports isolation modes (usage, usage+cpoe, usage+ngs, usage+cpoe+ngs)
    and full-stack modes (full+usage, full+usage+cpoe, etc.).
    """
    # Strip "all+"/"full+" prefix -- these enable all other engines, handled elsewhere
    mode_key = mode.replace("all+", "").replace("full+", "")

    # Default usage config for "all" mode: snap + cpoe (validated by A/B)
    default_usage = UsageConfig(
        enabled=True,
        cpoe=CpoeConfig(enabled=True),
        ngs=NgsConfig(enabled=False),
        route_rate=RouteRateConfig(enabled=False),
    )

    usage_modes = {
        "all": default_usage,
        "usage": UsageConfig(
            enabled=True,
            cpoe=CpoeConfig(enabled=False),
            ngs=NgsConfig(enabled=False),
            route_rate=RouteRateConfig(enabled=False),
        ),
        "usage+cpoe": default_usage,
        "usage+ngs": UsageConfig(
            enabled=True,
            cpoe=CpoeConfig(enabled=False),
            ngs=NgsConfig(enabled=True),
            route_rate=RouteRateConfig(enabled=False),
        ),
        "usage+cpoe+ngs": UsageConfig(
            enabled=True,
            cpoe=CpoeConfig(enabled=True),
            ngs=NgsConfig(enabled=True),
            route_rate=RouteRateConfig(enabled=True),
        ),
    }

    return usage_modes.get(mode_key)


# ---------------------------------------------------------------------------
# Backtest runner
# ---------------------------------------------------------------------------

def _run_backtest_off(
    test_season: int,
    n_sims: int,
    scoring_config: dict,
    num_training_seasons: int,
) -> BacktestResult:
    """Run PFF-OFF baseline for one season."""
    print(f"  [{test_season}] Running PFF-OFF baseline...", flush=True)
    t0 = time.time()
    bt = Backtester(
        test_season=test_season,
        n_sims=n_sims,
        num_training_seasons=num_training_seasons,
        max_workers=1,  # PFF-OFF is cheap (~0.4s/game), parallelism adds overhead
    )
    result = bt.run(scoring_config)
    elapsed = time.time() - t0
    print(f"    [{test_season}] PFF-OFF done in {elapsed:.1f}s  "
          f"weekly_mae={result.weekly_mae:.3f}  "
          f"season_mae={result.season_mae:.3f}  "
          f"rank_corr={_format_rank_corr(result)}", flush=True)
    return result


def _run_backtest_on(
    test_season: int,
    n_sims: int,
    scoring_config: dict,
    num_training_seasons: int,
    pff_config: PffConfig,
    weather_config: WeatherConfig | None,
    max_workers: int,
    mode_label: str,
    vegas_config: VegasConfig | None = None,
    props_config: PropsConfig | None = None,
    usage_config: UsageConfig | None = None,
) -> BacktestResult:
    """Run PFF-ON for one season."""
    print(f"  [{test_season}] Running PFF-ON ({mode_label})...", flush=True)
    t0 = time.time()
    bt = Backtester(
        test_season=test_season,
        n_sims=n_sims,
        num_training_seasons=num_training_seasons,
        pff_config=pff_config,
        weather_config=weather_config,
        vegas_config=vegas_config,
        props_config=props_config,
        usage_config=usage_config,
        max_workers=max_workers,
    )
    result = bt.run(scoring_config)
    elapsed = time.time() - t0
    print(f"    [{test_season}] PFF-ON done in {elapsed:.1f}s  "
          f"weekly_mae={result.weekly_mae:.3f}  "
          f"season_mae={result.season_mae:.3f}  "
          f"rank_corr={_format_rank_corr(result)}", flush=True)
    return result


def _get_mode_label(pff_config: PffConfig) -> str:
    """Derive a human-readable mode label from PFF config."""
    if hasattr(pff_config, 'coverage') and pff_config.coverage.enabled:
        if pff_config.matchup.enabled and pff_config.tier_engine.enabled:
            return "coverage+tier+matchup"
        elif pff_config.tier_engine.enabled:
            return "coverage+tier"
        return "coverage"
    if pff_config.team_context.enabled and pff_config.tier_engine.enabled and pff_config.matchup.enabled:
        return "team_context+tier+matchup"
    if pff_config.team_context.enabled and pff_config.tier_engine.enabled:
        return "team_context+tier"
    if pff_config.matchup.enabled and pff_config.tier_engine.enabled:
        return "matchup+tier"
    if pff_config.matchup.enabled and not pff_config.talent.enabled:
        return "matchup"
    if pff_config.talent.enabled and not pff_config.matchup.enabled:
        return "talent"
    if pff_config.tier_engine.enabled:
        return "tier"
    return "all"


def run_backtest_pair(
    test_season: int,
    n_sims: int,
    scoring_config: dict,
    num_training_seasons: int,
    pff_config: PffConfig,
    weather_config: WeatherConfig | None = None,
    vegas_config: VegasConfig | None = None,
    props_config: PropsConfig | None = None,
    usage_config: UsageConfig | None = None,
    max_workers: int = 1,
) -> ComparisonResult:
    """Run PFF-off then PFF-on backtests for one season and return comparison."""
    result_off = _run_backtest_off(
        test_season, n_sims, scoring_config, num_training_seasons,
    )
    mode_label = _get_mode_label(pff_config)
    result_on = _run_backtest_on(
        test_season, n_sims, scoring_config, num_training_seasons,
        pff_config, weather_config, max_workers, mode_label,
        vegas_config=vegas_config,
        props_config=props_config,
        usage_config=usage_config,
    )
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
    import warnings
    warnings.warn(
        "validate_pff_signal.py is deprecated. Use scripts/validate.py instead. "
        "See docs/AB-TESTING.md for usage.",
        DeprecationWarning,
        stacklevel=2,
    )
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
        choices=["matchup", "talent", "tier", "matchup+tier",
                 "team_context+tier", "team_context+tier+matchup",
                 "ncaa_rookie+tier", "ncaa_rookie+tier+matchup",
                 "coverage+tier", "coverage+tier+matchup",
                 "kicker", "dst_baseline", "kicker+dst_baseline",
                 "kicker+dst_baseline+tier+matchup+coverage",
                 "weather", "weather+tier", "weather+tier+matchup",
                 "vegas", "vegas+spread", "vegas+props",
                 "all",
                 "all+usage", "all+usage+cpoe", "all+usage+ngs", "all+usage+cpoe+ngs"],
        default="all",
        help=(
            "Which layer(s) to enable in the ON run. "
            "'all' = PFF (tier+matchup+coverage+kicker+dst) + weather + vegas + props, "
            "'all+usage' = all + snap blend, "
            "'all+usage+cpoe' = all + snap + CPOE, "
            "'all+usage+cpoe+ngs' = all + snap + CPOE + NGS + route rate, "
            "'vegas' = Vegas ITT only (no spread, no PFF), "
            "'vegas+spread' = Vegas ITT + spread (no PFF), "
            "'vegas+props' = Vegas + player props (no PFF), "
            "'usage' = snap-only usage engine (isolation), "
            "'usage+cpoe' = snap + CPOE (isolation), "
            "'usage+ngs' = snap + NGS (isolation), "
            "'usage+cpoe+ngs' = all usage signals (isolation), "
            "'full+usage' = all engines + snap-only usage, "
            "'full+usage+cpoe' = all engines + snap + CPOE, "
            "'full+usage+ngs' = all engines + snap + NGS, "
            "'full+usage+cpoe+ngs' = all engines + full usage."
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
        default=[2022, 2023, 2024],
        metavar="YEAR",
        help="Test seasons to backtest (default: 2022 2023 2024).",
    )
    parser.add_argument(
        "--training-years",
        type=int,
        default=4,
        metavar="N",
        dest="training_years",
        help="Number of training seasons before each test season (default: 4).",
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
        help='PFF config overrides as JSON. Keys: "talent", "matchup", "tier_engine", '
             '"team_context", "ncaa_rookie", "coverage", "kicker", "dst_baseline", "weather". '
             'Example: \'{"coverage": {"catch_rate_sensitivity": 0.06}}\'',
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=0,
        metavar="N",
        help="Worker processes for game simulation (0=auto, 1=sequential). Default: auto.",
    )

    args = parser.parse_args()

    if args.show_ledger:
        entries = load_ledger()
        print(format_progression_table(entries))
        return 0

    # Hold-out gate: block 2025+ seasons until milestone completion (FIX-03)
    if any(s >= 2025 for s in args.seasons):
        print(
            "ERROR: Season 2025+ is reserved as hold-out until milestone completion. "
            "Use --seasons 2022 2023 2024.",
            file=sys.stderr,
        )
        return 1

    # Parse config overrides
    overrides = json.loads(args.config_override) if args.config_override else None

    # Expand "full" alias to canonical mode string
    # "full" alone maps to all+weather+vegas+props
    # "full+usage*" modes keep the full+ prefix so _build_*_config functions
    # recognize it as "enable all engines plus the specified usage variant"
    if args.mode == "full":
        args.mode = "all+weather+vegas+props"

    # Build PFF config once from mode + overrides
    pff_config = _build_pff_config(args.mode, overrides=overrides)
    weather_config = _build_weather_config(args.mode, overrides=overrides)
    vegas_config = _build_vegas_config(args.mode, overrides=overrides)
    props_config = _build_props_config(args.mode, overrides=overrides)
    usage_config = _build_usage_config(args.mode, overrides=overrides)

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

    # Compute per-season worker count
    num_seasons = len(args.seasons)
    if args.workers == 1:
        per_season_workers = 1
    elif args.workers > 1:
        per_season_workers = args.workers
    else:
        per_season_workers = default_max_workers(batch_size=288, num_concurrent=num_seasons)
    build_workers = min(per_season_workers, 4)
    print(f"  workers       : {per_season_workers} sim, {build_workers} build per season")

    # Load scoring config
    defaults = load_defaults()
    scoring_config = resolve_scoring(defaults["scoring"], args.scoring)

    # Run A/B pairs for each season (parallel when multiple seasons)
    total_start = time.time()
    results: list[ComparisonResult] = []

    mode_label = _get_mode_label(pff_config)

    if len(args.seasons) > 1:
        from concurrent.futures import ProcessPoolExecutor, as_completed

        # Phase A: All PFF-OFF baselines (lightweight, no build workers)
        # Runs all seasons simultaneously without resource contention.
        print(f"\nPhase A: PFF-OFF baselines ({len(args.seasons)} seasons)...")
        off_results: dict[int, BacktestResult] = {}
        with ProcessPoolExecutor(max_workers=len(args.seasons)) as pool:
            futures = {
                pool.submit(
                    _run_backtest_off,
                    test_season=season,
                    n_sims=args.sims,
                    scoring_config=scoring_config,
                    num_training_seasons=args.training_years,
                ): season
                for season in args.seasons
            }
            for future in as_completed(futures):
                off_results[futures[future]] = future.result()

        # Phase B: All PFF-ON (heavy, with build workers)
        # Starts only after all PFF-OFF complete, preventing resource starvation.
        print(f"\nPhase B: PFF-ON {mode_label} ({len(args.seasons)} seasons)...")
        on_results: dict[int, BacktestResult] = {}
        with ProcessPoolExecutor(max_workers=len(args.seasons)) as pool:
            futures = {
                pool.submit(
                    _run_backtest_on,
                    test_season=season,
                    n_sims=args.sims,
                    scoring_config=scoring_config,
                    num_training_seasons=args.training_years,
                    pff_config=pff_config,
                    weather_config=weather_config,
                    max_workers=per_season_workers,
                    mode_label=mode_label,
                    vegas_config=vegas_config,
                    props_config=props_config,
                    usage_config=usage_config,
                ): season
                for season in args.seasons
            }
            for future in as_completed(futures):
                season = futures[future]
                on_results[season] = future.result()
                print(f"\n  Season {season} complete.")

        for season in sorted(args.seasons):
            results.append(ComparisonResult(
                test_season=season, off=off_results[season], on=on_results[season],
            ))
    else:
        for season in args.seasons:
            print(f"\nBacktesting season {season}...")
            comparison = run_backtest_pair(
                test_season=season,
                n_sims=args.sims,
                scoring_config=scoring_config,
                num_training_seasons=args.training_years,
                pff_config=pff_config,
                weather_config=weather_config,
                vegas_config=vegas_config,
                props_config=props_config,
                usage_config=usage_config,
                max_workers=per_season_workers,
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

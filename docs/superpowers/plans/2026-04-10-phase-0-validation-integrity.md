# Phase 0 Validation Integrity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the validation path so Phase 0 can cleanly distinguish total lift vs marginal lift, report historical signal coverage, and record schema-tagged run metadata without changing projections or model behavior.

**Architecture:** Add one validation-only coverage helper, extend the unified ledger with explicit schema and comparability metadata, and wire both into `scripts/validate.py`. Keep the blast radius limited to validation plumbing, ledger serialization, terminal output, and the two source-of-truth docs.

**Tech Stack:** Python 3.12+, polars, pathlib, dataclasses, pytest

**Spec:** `docs/superpowers/specs/2026-04-10-phase-0-validation-integrity-design.md`

---

### Task 1: Add Validation Coverage Helper

**Files:**
- Create: `src/fantasy_sim/validation/coverage.py`
- Test: `tests/test_validation/test_coverage.py`

- [ ] **Step 1: Write the failing coverage-helper tests**

Create `tests/test_validation/test_coverage.py`:

```python
"""Tests for validation signal coverage reporting."""

from __future__ import annotations

from pathlib import Path

from fantasy_sim.validation.coverage import SignalCoverage, collect_signal_coverage


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()


def _config() -> dict:
    return {
        "pff": {"enabled": True},
        "weather": {"enabled": True},
        "vegas": {"enabled": True, "props": {"enabled": True}},
        "usage": {
            "enabled": True,
            "cpoe": {"enabled": True},
            "ngs": {"enabled": True},
            "route_rate": {"enabled": True},
        },
    }


def test_collect_signal_coverage_reports_props_none_for_backtest_years(tmp_path):
    props_dir = tmp_path / "pff" / "props"
    _touch(props_dir / "props_2025_week01.parquet")

    summary = collect_signal_coverage(
        _config(),
        [2022, 2023, 2024],
        cache_dir=tmp_path / "cache",
        pff_dir=tmp_path / "pff" / "processed" / "nfl",
        props_dir=props_dir,
    )

    props = summary["props"]
    assert isinstance(props, SignalCoverage)
    assert props.enabled is True
    assert props.status == "none"
    assert props.covered_seasons == []
    assert props.missing_seasons == [2022, 2023, 2024]
    assert "2025" in (props.note or "")


def test_collect_signal_coverage_reports_full_pff_and_route_rate_when_facets_exist(tmp_path):
    pff_dir = tmp_path / "pff" / "processed" / "nfl"
    for season in [2022, 2023, 2024]:
        _touch(pff_dir / f"receiving_summary_{season}.parquet")
        _touch(pff_dir / f"rushing_summary_{season}.parquet")
        _touch(pff_dir / f"passing_summary_{season}.parquet")

    summary = collect_signal_coverage(
        _config(),
        [2022, 2023, 2024],
        cache_dir=tmp_path / "cache",
        pff_dir=pff_dir,
        props_dir=tmp_path / "pff" / "props",
    )

    assert summary["pff"].status == "full"
    assert summary["pff"].covered_seasons == [2022, 2023, 2024]
    assert summary["usage.route_rate"].status == "full"


def test_collect_signal_coverage_reports_partial_usage_when_pbp_or_snap_is_missing(tmp_path):
    cache_dir = tmp_path / "cache"
    for season in [2022, 2023]:
        _touch(cache_dir / f"snap_counts_{season}.parquet")
        _touch(cache_dir / f"pbp_{season}.parquet")
    _touch(cache_dir / "snap_counts_2024.parquet")

    summary = collect_signal_coverage(
        _config(),
        [2022, 2023, 2024],
        cache_dir=cache_dir,
        pff_dir=tmp_path / "pff" / "processed" / "nfl",
        props_dir=tmp_path / "pff" / "props",
    )

    usage = summary["usage"]
    assert usage.status == "partial"
    assert usage.covered_seasons == [2022, 2023]
    assert usage.missing_seasons == [2024]


def test_collect_signal_coverage_marks_disabled_signals_explicitly(tmp_path):
    config = _config()
    config["vegas"]["props"]["enabled"] = False
    config["usage"]["ngs"]["enabled"] = False

    summary = collect_signal_coverage(
        config,
        [2022, 2023],
        cache_dir=tmp_path / "cache",
        pff_dir=tmp_path / "pff" / "processed" / "nfl",
        props_dir=tmp_path / "pff" / "props",
    )

    assert summary["props"].status == "disabled"
    assert summary["usage.ngs"].status == "disabled"
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `uv run pytest tests/test_validation/test_coverage.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'fantasy_sim.validation.coverage'`

- [ ] **Step 3: Implement the minimal coverage helper**

Create `src/fantasy_sim/validation/coverage.py`:

```python
"""Coverage accounting for validation-only external signals."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fantasy_sim.data.loader import DEFAULT_CACHE_DIR

DEFAULT_PFF_DIR = Path.home() / ".fantasy-sim" / "pff" / "processed" / "nfl"
DEFAULT_PROPS_DIR = Path.home() / ".fantasy-sim" / "pff" / "props"


@dataclass
class SignalCoverage:
    enabled: bool
    status: str
    covered_seasons: list[int]
    missing_seasons: list[int]
    note: str | None = None


def _build_signal(enabled: bool, test_seasons: list[int], covered: list[int], note: str | None = None) -> SignalCoverage:
    missing = [season for season in test_seasons if season not in covered]
    if not enabled:
        return SignalCoverage(
            enabled=False,
            status="disabled",
            covered_seasons=[],
            missing_seasons=test_seasons,
            note=note or "signal disabled for this run",
        )
    if len(covered) == len(test_seasons):
        status = "full"
    elif covered:
        status = "partial"
    else:
        status = "none"
    return SignalCoverage(
        enabled=True,
        status=status,
        covered_seasons=covered,
        missing_seasons=missing,
        note=note,
    )


def _covered_seasons_from_paths(test_seasons: list[int], paths_by_season: dict[int, list[Path]]) -> list[int]:
    covered: list[int] = []
    for season in test_seasons:
        season_paths = paths_by_season.get(season, [])
        if season_paths and all(path.exists() for path in season_paths):
            covered.append(season)
    return covered


def collect_signal_coverage(
    config: dict,
    test_seasons: list[int],
    *,
    cache_dir: Path | None = None,
    pff_dir: Path | None = None,
    props_dir: Path | None = None,
) -> dict[str, SignalCoverage]:
    cache_dir = Path(cache_dir) if cache_dir is not None else DEFAULT_CACHE_DIR
    pff_dir = Path(pff_dir) if pff_dir is not None else DEFAULT_PFF_DIR
    props_dir = Path(props_dir) if props_dir is not None else DEFAULT_PROPS_DIR

    pff_enabled = bool(config.get("pff", {}).get("enabled", False))
    weather_enabled = bool(config.get("weather", {}).get("enabled", False))
    usage_cfg = config.get("usage", {})
    usage_enabled = bool(usage_cfg.get("enabled", False))
    ngs_enabled = usage_enabled and bool(usage_cfg.get("ngs", {}).get("enabled", False))
    route_rate_enabled = usage_enabled and bool(usage_cfg.get("route_rate", {}).get("enabled", False))
    props_enabled = (
        bool(config.get("vegas", {}).get("enabled", False))
        and bool(config.get("vegas", {}).get("props", {}).get("enabled", False))
    )

    pff_covered = _covered_seasons_from_paths(
        test_seasons,
        {
            season: [
                pff_dir / f"receiving_summary_{season}.parquet",
                pff_dir / f"rushing_summary_{season}.parquet",
                pff_dir / f"passing_summary_{season}.parquet",
            ]
            for season in test_seasons
        },
    )
    props_covered = [
        season
        for season in test_seasons
        if list(props_dir.glob(f"props_{season}_week*.parquet"))
    ]
    usage_covered = _covered_seasons_from_paths(
        test_seasons,
        {
            season: [
                cache_dir / f"snap_counts_{season}.parquet",
                cache_dir / f"pbp_{season}.parquet",
            ]
            for season in test_seasons
        },
    )
    ngs_covered = _covered_seasons_from_paths(
        test_seasons,
        {
            season: [cache_dir / f"ngs_receiving_{season}.parquet"]
            for season in test_seasons
        },
    )

    summary = {
        "props": _build_signal(
            props_enabled,
            test_seasons,
            props_covered,
            note="historical props are forward-only unless season parquet files exist in ~/.fantasy-sim/pff/props",
        ),
        "pff": _build_signal(
            pff_enabled,
            test_seasons,
            pff_covered,
            note="requires passing_summary, rushing_summary, and receiving_summary parquet coverage",
        ),
        "weather": _build_signal(
            weather_enabled,
            test_seasons,
            test_seasons if weather_enabled else [],
            note="historical coverage is API-backed through Open-Meteo",
        ),
        "usage": _build_signal(
            usage_enabled,
            test_seasons,
            usage_covered,
            note="requires snap_counts and PBP coverage for the tested seasons",
        ),
        "usage.ngs": _build_signal(
            ngs_enabled,
            test_seasons,
            ngs_covered,
            note="requires nflreadpy NGS receiving parquet coverage",
        ),
        "usage.route_rate": _build_signal(
            route_rate_enabled,
            test_seasons,
            pff_covered,
            note="uses PFF receiving_summary parquet coverage",
        ),
    }
    return summary
```

- [ ] **Step 4: Run the coverage tests to verify they pass**

Run: `uv run pytest tests/test_validation/test_coverage.py -v`

Expected: 4 PASS

- [ ] **Step 5: Commit the helper**

```bash
git add src/fantasy_sim/validation/coverage.py tests/test_validation/test_coverage.py
git commit -m "test: add validation coverage reporting helper"
```

---

### Task 2: Extend Ledger Schema And Backward Compatibility

**Files:**
- Modify: `src/fantasy_sim/validation/ledger.py:1-155`
- Modify: `tests/test_validation/test_ledger.py:1-83`

- [ ] **Step 1: Expand the ledger tests first**

Update `tests/test_validation/test_ledger.py` to add the new fields and a legacy-load case.

Replace `_make_entry()` with:

```python
import json

from fantasy_sim.validation.coverage import SignalCoverage
from fantasy_sim.validation.ledger import (
    CURRENT_LEDGER_SCHEMA_VERSION,
    LedgerEntry,
    SeasonMetrics,
    format_ledger_table,
    load_ledger,
    save_ledger,
)


def _make_entry(label: str = "test-run") -> LedgerEntry:
    return LedgerEntry(
        label=label,
        timestamp="2026-04-08T12:00:00",
        sims=50,
        test_seasons=[2022, 2023, 2024],
        training_years=4,
        scoring="ppr",
        baseline="bare",
        overrides=[],
        config_snapshot={"pff": {"enabled": True}},
        season_results=[
            SeasonMetrics(
                test_season=2024,
                arm_a_rank_corr={"QB": 0.40, "RB": 0.35, "WR": 0.30, "TE": 0.28},
                arm_b_rank_corr={"QB": 0.42, "RB": 0.37, "WR": 0.33, "TE": 0.30},
                arm_a_weekly_mae=7.0,
                arm_b_weekly_mae=6.8,
                arm_a_season_mae=2.5,
                arm_b_season_mae=2.3,
                arm_a_calibration=0.12,
                arm_b_calibration=0.10,
            ),
        ],
        weekly_summaries=None,
        directional_accuracy=None,
        schema_version=CURRENT_LEDGER_SCHEMA_VERSION,
        comparison_mode="total_lift",
        seed_mode="deterministic_game_id_crc32_shared_between_arms",
        coverage_summary={
            "props": SignalCoverage(
                enabled=True,
                status="none",
                covered_seasons=[],
                missing_seasons=[2022, 2023, 2024],
                note="historical props unavailable",
            ),
        },
    )
```

Add this test below `test_load_ledger_missing_file`:

```python
def test_load_legacy_ledger_entry_defaults_new_fields(tmp_path):
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps([{
        "label": "legacy-run",
        "timestamp": "2026-04-01T12:00:00",
        "sims": 50,
        "test_seasons": [2024],
        "training_years": 4,
        "scoring": "ppr",
        "baseline": "bare",
        "overrides": [],
        "config_snapshot": {"pff": {"enabled": True}},
        "season_results": [{
            "test_season": 2024,
            "arm_a_rank_corr": {"QB": 0.4, "RB": 0.3, "WR": 0.2, "TE": 0.1},
            "arm_b_rank_corr": {"QB": 0.5, "RB": 0.4, "WR": 0.3, "TE": 0.2},
            "arm_a_weekly_mae": 7.0,
            "arm_b_weekly_mae": 6.5,
            "arm_a_season_mae": 3.0,
            "arm_b_season_mae": 2.8,
            "arm_a_calibration": 0.2,
            "arm_b_calibration": 0.1,
        }],
    }], indent=2))

    loaded = load_ledger(path)
    assert len(loaded) == 1
    assert loaded[0].schema_version is None
    assert loaded[0].comparison_mode is None
    assert loaded[0].seed_mode is None
    assert loaded[0].coverage_summary is None
```

- [ ] **Step 2: Run the ledger tests to verify they fail**

Run: `uv run pytest tests/test_validation/test_ledger.py -v`

Expected: FAIL with `ImportError` or `TypeError` because `CURRENT_LEDGER_SCHEMA_VERSION`, `comparison_mode`, `seed_mode`, and `coverage_summary` do not exist yet.

- [ ] **Step 3: Implement schema-versioned ledger support**

Update `src/fantasy_sim/validation/ledger.py`:

```python
from dataclasses import asdict, dataclass

from fantasy_sim.validation.coverage import SignalCoverage
from fantasy_sim.validation.weekly import (
    DirectionalAccuracyResult,
    WeeklyPositionSummary,
)

CURRENT_LEDGER_SCHEMA_VERSION = 2


@dataclass
class LedgerEntry:
    label: str
    timestamp: str
    sims: int
    test_seasons: list[int]
    training_years: int
    scoring: str
    baseline: str
    overrides: list[str]
    config_snapshot: dict
    season_results: list[SeasonMetrics]
    weekly_summaries: list[WeeklyPositionSummary] | None = None
    directional_accuracy: DirectionalAccuracyResult | None = None
    schema_version: int | None = None
    comparison_mode: str | None = None
    seed_mode: str | None = None
    coverage_summary: dict[str, SignalCoverage] | None = None


def load_ledger(path: Path = DEFAULT_LEDGER_PATH) -> list[LedgerEntry]:
    if not path.exists():
        return []
    with open(path) as f:
        raw = json.load(f)
    entries = []
    for item in raw:
        season_results = [SeasonMetrics(**sr) for sr in item.get("season_results", [])]
        ws_raw = item.get("weekly_summaries")
        weekly_summaries = [WeeklyPositionSummary(**ws) for ws in ws_raw] if ws_raw else None
        da_raw = item.get("directional_accuracy")
        da = DirectionalAccuracyResult(**da_raw) if da_raw else None
        cov_raw = item.get("coverage_summary")
        coverage_summary = (
            {name: SignalCoverage(**payload) for name, payload in cov_raw.items()}
            if cov_raw
            else None
        )

        normalized = dict(item)
        normalized["season_results"] = season_results
        normalized["weekly_summaries"] = weekly_summaries
        normalized["directional_accuracy"] = da
        normalized["coverage_summary"] = coverage_summary
        normalized.setdefault("schema_version", None)
        normalized.setdefault("comparison_mode", None)
        normalized.setdefault("seed_mode", None)
        entries.append(LedgerEntry(**normalized))
    return entries


def format_ledger_table(entries: list[LedgerEntry]) -> str:
    if not entries:
        return "No entries in ledger."

    header = (
        f"{'#':>3}  {'Label':<22}  {'baseline':<9}  {'mode':<13}  {'overrides':<24}  "
        f"{'rank_corr':>9}  {'wk_mae':>7}  {'szn_mae':>7}"
    )
    sep = "=" * len(header)
    lines = [sep, header, "-" * len(header)]

    for i, e in enumerate(entries, start=1):
        overrides_str = ", ".join(e.overrides) if e.overrides else "(none)"
        if len(overrides_str) > 24:
            overrides_str = overrides_str[:21] + "..."
        mode = e.comparison_mode or "legacy"
        row = (
            f"{i:>3}  {e.label:<22}  {e.baseline:<9}  {mode:<13}  {overrides_str:<24}  "
            f"{e.avg_rank_corr_delta:>+.4f}    "
            f"{e.avg_weekly_mae_delta:>+.3f}  "
            f"{e.avg_season_mae_delta:>+.3f}"
        )
        lines.append(row)

    lines.append(sep)
    return "\n".join(lines)
```

- [ ] **Step 4: Run the ledger tests to verify they pass**

Run: `uv run pytest tests/test_validation/test_ledger.py -v`

Expected: all PASS

- [ ] **Step 5: Commit the ledger evolution**

```bash
git add src/fantasy_sim/validation/ledger.py tests/test_validation/test_ledger.py
git commit -m "feat: version validation ledger entries"
```

---

### Task 3: Wire Coverage And Comparison Metadata Into `validate.py`

**Files:**
- Modify: `scripts/validate.py:17-115`
- Modify: `scripts/validate.py:224-243`
- Modify: `scripts/validate.py:549-709`
- Modify: `tests/test_validation/test_validate_script.py:22-216`

- [ ] **Step 1: Add failing validate-script tests for td_tendency threading and marginal metadata**

Append to `tests/test_validation/test_validate_script.py`:

```python
import sys

from fantasy_sim.validation.coverage import SignalCoverage


def test_run_season_threads_td_tendency_config_into_dual_arm_build():
    validate = _load_validate_module()

    with patch.object(validate, "simulate_games_parallel", return_value=[]), \
         patch.object(validate, "build_games_parallel", return_value=[]) as mock_build_games_parallel, \
         patch.object(validate, "load_actual_scores", return_value=[]), \
         patch.object(validate, "DataLoader") as mock_loader_cls:
        mock_loader = mock_loader_cls.return_value
        mock_loader.cache_dir = Path("/tmp/test-cache")
        mock_loader.load_schedules.return_value = pl.DataFrame([{
            "season": 2024,
            "week": 1,
            "game_id": "2024_01_KC_BUF",
            "home_team": "KC",
            "away_team": "BUF",
        }])
        mock_loader.load_player_stats.return_value = pl.DataFrame(
            {"season": pl.Series([], dtype=pl.Int32)}
        )

        td_tendency_config = object()
        arm_a_configs = {
            "pff_config": None,
            "weather_config": None,
            "vegas_config": None,
            "props_config": None,
            "usage_config": None,
            "game_script_config": None,
            "goal_line_concentration_config": None,
            "td_tendency_config": None,
        }
        arm_b_configs = {
            "pff_config": None,
            "weather_config": None,
            "vegas_config": None,
            "props_config": None,
            "usage_config": None,
            "game_script_config": None,
            "goal_line_concentration_config": None,
            "td_tendency_config": td_tendency_config,
        }

        validate.run_season(
            test_season=2024,
            n_sims=10,
            scoring_config={},
            num_training_seasons=3,
            arm_a_configs=arm_a_configs,
            arm_b_configs=arm_b_configs,
            positions=["QB"],
            max_workers=1,
        )

    call_kwargs = mock_build_games_parallel.call_args.kwargs
    assert call_kwargs["dual_arm"] is True
    assert call_kwargs["td_tendency_config"] is td_tendency_config


def test_main_records_marginal_metadata_and_coverage_summary():
    validate = _load_validate_module()

    fake_result = {
        "season_metrics": validate.SeasonMetrics(
            test_season=2024,
            arm_a_rank_corr={"QB": 0.40, "RB": 0.35, "WR": 0.30, "TE": 0.28},
            arm_b_rank_corr={"QB": 0.42, "RB": 0.37, "WR": 0.33, "TE": 0.30},
            arm_a_weekly_mae=7.0,
            arm_b_weekly_mae=6.8,
            arm_a_season_mae=2.5,
            arm_b_season_mae=2.3,
            arm_a_calibration=0.12,
            arm_b_calibration=0.10,
        ),
        "weekly_records": [],
        "arm_a_projections": None,
        "arm_a_meta": None,
    }
    empty_engine_configs = {
        "pff_config": None,
        "weather_config": None,
        "vegas_config": None,
        "props_config": None,
        "usage_config": None,
        "game_script_config": None,
        "goal_line_concentration_config": None,
        "td_tendency_config": None,
    }
    defaults = {
        "scoring": {"ppr": {}},
        "pff": {"enabled": True},
        "weather": {"enabled": True},
        "vegas": {"enabled": True, "props": {"enabled": True}},
        "usage": {
            "enabled": True,
            "cpoe": {"enabled": True},
            "ngs": {"enabled": False},
            "route_rate": {"enabled": False},
        },
    }
    coverage_summary = {
        "props": SignalCoverage(
            enabled=True,
            status="none",
            covered_seasons=[],
            missing_seasons=[2024],
            note="historical props unavailable",
        ),
    }

    with patch.object(validate, "load_defaults", return_value=defaults), \
         patch.object(validate, "resolve_scoring", return_value={}), \
         patch.object(validate, "build_engine_configs", side_effect=[empty_engine_configs, empty_engine_configs]), \
         patch.object(validate, "run_season", return_value=fake_result), \
         patch.object(validate, "collect_signal_coverage", return_value=coverage_summary), \
         patch.object(validate, "load_ledger", return_value=[]), \
         patch.object(validate, "save_ledger") as mock_save, \
         patch.object(validate, "print"):
        with patch.object(
            sys,
            "argv",
            ["validate.py", "--baseline", "defaults", "--label", "marginal-check", "--seasons", "2024", "--workers", "1"],
        ):
            rc = validate.main()

    assert rc == 0
    saved_entries = mock_save.call_args.args[1]
    entry = saved_entries[0]
    assert entry.baseline == "defaults"
    assert entry.comparison_mode == "marginal_lift"
    assert entry.seed_mode == "deterministic_game_id_crc32_shared_between_arms"
    assert entry.coverage_summary == coverage_summary
```

- [ ] **Step 2: Run the validate-script tests to verify they fail**

Run: `uv run pytest tests/test_validation/test_validate_script.py -v`

Expected: FAIL because `td_tendency_config` is still missing from the dual-arm call and the new ledger metadata fields are not written yet.

- [ ] **Step 3: Update `scripts/validate.py` with the Phase 0 plumbing**

Apply these focused changes in `scripts/validate.py`:

```python
from fantasy_sim.validation.coverage import collect_signal_coverage
from fantasy_sim.validation.ledger import (
    CURRENT_LEDGER_SCHEMA_VERSION,
    DEFAULT_LEDGER_PATH,
    LedgerEntry,
    SeasonMetrics,
    format_ledger_table,
    load_ledger,
    save_ledger,
)

SEED_MODE = "deterministic_game_id_crc32_shared_between_arms"


def _comparison_mode(baseline: str) -> str:
    return "marginal_lift" if baseline == "defaults" else "total_lift"


def _format_coverage_line(coverage_summary: dict) -> str:
    ordered = ["props", "pff", "weather", "usage", "usage.ngs", "usage.route_rate"]
    parts = []
    for key in ordered:
        coverage = coverage_summary.get(key)
        if coverage is not None:
            parts.append(f"{key}={coverage.status}")
    return ", ".join(parts)


def print_header(args, cache_status: dict[int, bool], comparison_mode: str, seed_mode: str, coverage_summary: dict) -> None:
    overrides_str = " + [" + ", ".join(args.overrides) + "]" if args.overrides else ""
    cache_hits = [s for s, hit in cache_status.items() if hit]
    cache_misses = [s for s, hit in cache_status.items() if not hit]
    cache_str = ""
    if args.baseline == "bare" and not args.no_cache:
        parts = []
        if cache_hits:
            parts.append(f"HIT ({', '.join(str(s) for s in cache_hits)})")
        if cache_misses:
            parts.append(f"MISS ({', '.join(str(s) for s in cache_misses)})")
        cache_str = ", ".join(parts)

    print("=" * 68)
    print("  A/B VALIDATION")
    print("=" * 68)
    print(f"  baseline    : {args.baseline}")
    print(f"  arm B       : defaults{overrides_str}")
    print(f"  comparison  : {comparison_mode}")
    print(f"  seed mode   : {seed_mode}")
    print(f"  sims        : {args.sims}")
    print(f"  seasons     : {args.seasons}")
    print(f"  scoring     : {args.scoring}")
    print(f"  coverage    : {_format_coverage_line(coverage_summary)}")
    if cache_str:
        print(f"  bare cache  : {cache_str}")
    print("=" * 68)
    print(f"  comparison  : {comparison_mode}")
    print(f"  seed mode   : {seed_mode}")
    print(f"  coverage    : {_format_coverage_line(coverage_summary)}")
```

In the bare dual-arm branch of `run_season()`, add the missing config:

```python
            build_results = build_games_parallel(
                game_args, cache_dir=loader.cache_dir,
                max_workers=max_workers, dual_arm=True,
                pff_config=arm_b_configs.get("pff_config"),
                weather_config=arm_b_configs.get("weather_config"),
                vegas_config=arm_b_configs.get("vegas_config"),
                props_config=arm_b_configs.get("props_config"),
                usage_config=arm_b_configs.get("usage_config"),
                game_script_config=arm_b_configs.get("game_script_config"),
                goal_line_concentration_config=arm_b_configs.get("goal_line_concentration_config"),
                td_tendency_config=arm_b_configs.get("td_tendency_config"),
            )
```

In `main()`, compute the run metadata before printing the header:

```python
    comparison_mode = _comparison_mode(args.baseline)
    coverage_summary = collect_signal_coverage(arm_b_dict, args.seasons)

    print_header(
        args,
        cache_status,
        comparison_mode=comparison_mode,
        seed_mode=SEED_MODE,
        coverage_summary=coverage_summary,
    )
```

And extend the saved entry:

```python
        entry = LedgerEntry(
            label=args.label,
            timestamp=datetime.now().isoformat(timespec="seconds"),
            sims=args.sims,
            test_seasons=args.seasons,
            training_years=args.training_years,
            scoring=args.scoring,
            baseline=args.baseline,
            overrides=args.overrides,
            config_snapshot=arm_b_dict if args.overrides else defaults,
            season_results=all_season_metrics,
            weekly_summaries=weekly_summaries,
            directional_accuracy=dir_accuracy,
            schema_version=CURRENT_LEDGER_SCHEMA_VERSION,
            comparison_mode=comparison_mode,
            seed_mode=SEED_MODE,
            coverage_summary=coverage_summary,
        )
```

- [ ] **Step 4: Run the validate-script tests to verify they pass**

Run: `uv run pytest tests/test_validation/test_validate_script.py -v`

Expected: all PASS

- [ ] **Step 5: Run the three focused validation test modules together**

Run: `uv run pytest tests/test_validation/test_coverage.py tests/test_validation/test_ledger.py tests/test_validation/test_validate_script.py -v`

Expected: all PASS

- [ ] **Step 6: Commit the validation plumbing**

```bash
git add scripts/validate.py tests/test_validation/test_validate_script.py
git add tests/test_validation/test_coverage.py tests/test_validation/test_ledger.py
git add src/fantasy_sim/validation/coverage.py src/fantasy_sim/validation/ledger.py
git commit -m "feat: make validation runs schema-aware and comparable"
```

---

### Task 4: Update Accuracy Docs To Match The New Validation Contract

**Files:**
- Modify: `docs/accuracy-roadmap.md:83-125`
- Modify: `docs/accuracy-stack-audit.md:233-329`

- [ ] **Step 1: Update the roadmap Phase 0 deliverables and deferrals**

In `docs/accuracy-roadmap.md`, replace the current Phase 0 deliverables block with:

```md
### Deliverables

- Thread `td_tendency_config` through the bare dual-arm path in `validate.py`
- Promote `baseline=defaults` to a first-class marginal validation path
- Add explicit per-run coverage reporting for:
  - props
  - PFF inputs
  - weather
  - usage signals
- Record config-schema version and comparison metadata in the unified ledger:
  - comparison mode
  - baseline
  - seed mode
  - sim count
  - coverage summary
- Update both source-of-truth docs as part of the phase deliverables:
  - [`docs/accuracy-roadmap.md`](./accuracy-roadmap.md)
  - [`docs/accuracy-stack-audit.md`](./accuracy-stack-audit.md)

### Deferred From This Phase

- repeated seeds or multi-run confidence summaries
```

- [ ] **Step 2: Update the audit to reflect the new path and remaining caveats**

In `docs/accuracy-stack-audit.md`, add a new post-implementation summary near the evaluation caveats section:

```md
## Phase 0 Resolution Notes

Resolved in the current validation path:

- `td_tendency_config` now threads through bare dual-arm validation
- `baseline=defaults` now records marginal-lift entries as first-class runs
- validation output now reports per-run coverage for enabled external signals
- schema-versioned ledger entries now distinguish newer comparable runs from legacy ones

Remaining caveats:

- historical props are still absent for 2022-2024, so props evidence remains no-data or partial-data in those seasons
- `results/weekly_ab_ledger.json` is still sparse compared with the pre-2022-2024 weekly ledger
- older pre-schema ledger entries remain directional evidence, not clean apples-to-apples comparisons
```

Also fix the props-path description anywhere it still points to `~/.fantasy-sim/props` so it matches the real loader path `~/.fantasy-sim/pff/props`.

- [ ] **Step 3: Run the focused verification suite after the doc edits**

Run: `uv run pytest tests/test_validation/test_coverage.py tests/test_validation/test_ledger.py tests/test_validation/test_validate_script.py -v`

Expected: all PASS

- [ ] **Step 4: Review the final diff and commit**

Run: `git diff -- docs/accuracy-roadmap.md docs/accuracy-stack-audit.md`

Expected: the diff shows Phase 0 doc updates only, with repeated-seed work explicitly deferred.

Then commit:

```bash
git add docs/accuracy-roadmap.md docs/accuracy-stack-audit.md
git commit -m "docs: update Phase 0 validation accuracy docs"
```

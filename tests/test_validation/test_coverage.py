"""Tests for validation signal coverage reporting."""

from __future__ import annotations

from pathlib import Path

from fantasy_sim.config.loader import load_defaults
from fantasy_sim.validation.config import build_engine_configs
import fantasy_sim.validation.coverage as coverage_module
from fantasy_sim.validation.coverage import (
    SignalCoverage,
    collect_signal_coverage,
)
from fantasy_sim.data.usage.models import RouteRateConfig, NgsConfig, UsageConfig


def _write_parquet_placeholder(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")


def _base_config(
    *,
    props_enabled: bool = True,
    pff_enabled: bool = True,
    weather_enabled: bool = True,
    usage_enabled: bool = True,
    usage_ngs_enabled: bool = True,
    usage_route_rate_enabled: bool = True,
) -> dict:
    return {
        "vegas": {"props": {"enabled": props_enabled}},
        "pff": {"enabled": pff_enabled},
        "weather": {"enabled": weather_enabled},
        "usage": {
            "enabled": usage_enabled,
            "ngs": {"enabled": usage_ngs_enabled},
            "route_rate": {"enabled": usage_route_rate_enabled},
        },
    }


def _write_default_pff_stack(pff_dir: Path, seasons: tuple[int, ...]) -> None:
    facets = (
        "receiving_summary",
        "rushing_summary",
        "passing_summary",
        "defense_coverage",
        "defense_pass_rush",
        "defense_run",
        "offense_pass_blocking",
        "offense_run_blocking",
        "defense_coverage_matchup",
        "field_goal_summary",
        "defense_summary",
    )
    for season in seasons:
        for facet in facets:
            _write_parquet_placeholder(pff_dir / f"{facet}_{season}.parquet")


def _write_roster_cache(cache_dir: Path, seasons: tuple[int, ...]) -> None:
    for season in seasons:
        _write_parquet_placeholder(cache_dir / f"rosters_weekly_{season}.parquet")


def _default_engine_configs() -> dict:
    return build_engine_configs(load_defaults())


def test_props_reports_none_for_backtest_years_when_only_2025_props_exists(tmp_path):
    props_dir = tmp_path / "props"
    _write_parquet_placeholder(props_dir / "props_2025_week01.parquet")

    coverage = collect_signal_coverage(
        _base_config(),
        [2023, 2024],
        props_dir=props_dir,
    )

    assert coverage["props"] == SignalCoverage(
        enabled=True,
        status="none",
        covered_seasons=[],
        missing_seasons=[2023, 2024],
        note="Forward-only unless season parquet files exist in ~/.fantasy-sim/pff/props",
    )


def test_pff_reports_full_when_default_stack_is_present_for_all_test_seasons(tmp_path):
    pff_dir = tmp_path / "pff"
    _write_default_pff_stack(pff_dir, (2023, 2024))

    coverage = collect_signal_coverage(
        _default_engine_configs(),
        [2023, 2024],
        pff_dir=pff_dir,
    )

    assert coverage["pff"] == SignalCoverage(
        enabled=True,
        status="full",
        covered_seasons=[2023, 2024],
        missing_seasons=[],
        note=(
            "Requires the current default-on PFF stack: tier_engine, "
            "matchup, coverage, kicker, and dst_baseline inputs"
        ),
    )


def test_pff_and_route_rate_report_with_default_stack_and_crosswalk_inputs(tmp_path):
    pff_dir = tmp_path / "pff"
    cache_dir = tmp_path / "cache"
    route_rate_root = pff_dir.parent
    _write_default_pff_stack(pff_dir, (2023,))
    for facet in ("receiving_summary", "rushing_summary", "passing_summary"):
        _write_parquet_placeholder(route_rate_root / f"{facet}_2023.parquet")
        _write_parquet_placeholder(route_rate_root / f"{facet}_2024.parquet")
    _write_roster_cache(cache_dir, (2023, 2024))

    engine_configs = _default_engine_configs()
    engine_configs["usage_config"] = UsageConfig()

    coverage = collect_signal_coverage(
        engine_configs,
        [2023, 2024],
        cache_dir=cache_dir,
        pff_dir=pff_dir,
    )

    assert coverage["pff"] == SignalCoverage(
        enabled=True,
        status="partial",
        covered_seasons=[2023],
        missing_seasons=[2024],
        note=(
            "Requires the current default-on PFF stack: tier_engine, "
            "matchup, coverage, kicker, and dst_baseline inputs"
        ),
    )
    assert coverage["usage.route_rate"] == SignalCoverage(
        enabled=True,
        status="full",
        covered_seasons=[2023, 2024],
        missing_seasons=[],
        note=(
            "Requires the PFF summary trio from the processed PFF root "
            "plus rosters_weekly cache to build the crosswalk"
        ),
    )


def test_usage_route_rate_reports_partial_when_crosswalk_inputs_are_missing_for_one_season(tmp_path):
    pff_dir = tmp_path / "pff"
    cache_dir = tmp_path / "cache"
    route_rate_root = pff_dir.parent
    _write_default_pff_stack(pff_dir, (2023, 2024))
    for facet in ("receiving_summary", "rushing_summary", "passing_summary"):
        _write_parquet_placeholder(route_rate_root / f"{facet}_2023.parquet")
        _write_parquet_placeholder(route_rate_root / f"{facet}_2024.parquet")
    _write_roster_cache(cache_dir, (2023,))

    engine_configs = _default_engine_configs()
    engine_configs["usage_config"] = UsageConfig()

    coverage = collect_signal_coverage(
        engine_configs,
        [2023, 2024],
        cache_dir=cache_dir,
        pff_dir=pff_dir,
    )

    assert coverage["usage.route_rate"] == SignalCoverage(
        enabled=True,
        status="partial",
        covered_seasons=[2023],
        missing_seasons=[2024],
        note=(
            "Requires the PFF summary trio from the processed PFF root "
            "plus rosters_weekly cache to build the crosswalk"
        ),
    )


def test_usage_reports_partial_when_snap_counts_or_pbp_missing_for_one_season(tmp_path):
    cache_dir = tmp_path / "cache"
    _write_parquet_placeholder(cache_dir / "snap_counts_2023.parquet")
    _write_parquet_placeholder(cache_dir / "pbp_2023.parquet")
    _write_parquet_placeholder(cache_dir / "snap_counts_2024.parquet")

    coverage = collect_signal_coverage(
        _base_config(),
        [2023, 2024],
        cache_dir=cache_dir,
    )

    assert coverage["usage"] == SignalCoverage(
        enabled=True,
        status="partial",
        covered_seasons=[2023],
        missing_seasons=[2024],
        note="Requires snap_counts and PBP parquet coverage for each test season",
    )
    assert coverage["usage.ngs"] == SignalCoverage(
        enabled=True,
        status="none",
        covered_seasons=[],
        missing_seasons=[2023, 2024],
        note="Requires nflreadpy NGS receiving parquet coverage for each test season",
    )


def test_usage_nested_flags_honor_typed_config_objects(tmp_path):
    cache_dir = tmp_path / "cache"
    _write_parquet_placeholder(cache_dir / "snap_counts_2024.parquet")
    _write_parquet_placeholder(cache_dir / "pbp_2024.parquet")

    coverage = collect_signal_coverage(
        {
            "usage_config": UsageConfig(
                enabled=True,
                ngs=NgsConfig(enabled=False),
                route_rate=RouteRateConfig(enabled=False),
            )
        },
        [2024],
        cache_dir=cache_dir,
    )

    assert coverage["usage"] == SignalCoverage(
        enabled=True,
        status="full",
        covered_seasons=[2024],
        missing_seasons=[],
        note="Requires snap_counts and PBP parquet coverage for each test season",
    )
    assert coverage["usage.ngs"].status == "disabled"
    assert coverage["usage.route_rate"].status == "disabled"


def test_usage_route_rate_is_disabled_when_pff_is_disabled_even_if_inputs_exist(tmp_path):
    pff_dir = tmp_path / "pff" / "nfl"
    cache_dir = tmp_path / "cache"
    route_rate_root = pff_dir.parent

    for facet in ("receiving_summary", "rushing_summary", "passing_summary"):
        _write_parquet_placeholder(route_rate_root / f"{facet}_2024.parquet")
    _write_roster_cache(cache_dir, (2024,))

    coverage = collect_signal_coverage(
        _base_config(pff_enabled=False, usage_enabled=True, usage_route_rate_enabled=True),
        [2024],
        cache_dir=cache_dir,
        pff_dir=pff_dir,
    )

    assert coverage["usage.route_rate"].status == "disabled"


def test_ensemble_ff_opportunity_reports_full_runtime_coverage_when_enabled():
    coverage = collect_signal_coverage(
        {
            "ensemble": {
                "enabled": True,
                "ff_opportunity": {"enabled": True},
            }
        },
        [2022, 2023, 2024],
    )

    assert coverage["ensemble.ff_opportunity"] == SignalCoverage(
        enabled=True,
        status="full",
        covered_seasons=[2022, 2023, 2024],
        missing_seasons=[],
        note=(
            "nflreadpy historical ff_opportunity coverage is treated as available "
            "for requested test seasons; player mapping coverage is measured at runtime"
        ),
    )


def test_default_roots_for_pff_and_route_rate_remain_separate(monkeypatch, tmp_path):
    pff_root = tmp_path / "pff_processed_nfl"
    route_rate_root = tmp_path / "pff_processed"
    cache_dir = tmp_path / "cache"

    monkeypatch.setattr(coverage_module, "DEFAULT_PFF_DIR", pff_root)
    monkeypatch.setattr(coverage_module, "DEFAULT_PFF_ROUTE_RATE_DIR", route_rate_root)

    _write_default_pff_stack(pff_root, (2023, 2024))
    for facet in ("receiving_summary", "rushing_summary", "passing_summary"):
        _write_parquet_placeholder(route_rate_root / f"{facet}_2023.parquet")
    _write_roster_cache(cache_dir, (2023,))

    engine_configs = _default_engine_configs()
    engine_configs["usage_config"] = UsageConfig()

    coverage = collect_signal_coverage(
        engine_configs,
        [2023, 2024],
        cache_dir=cache_dir,
    )

    assert coverage["pff"] == SignalCoverage(
        enabled=True,
        status="full",
        covered_seasons=[2023, 2024],
        missing_seasons=[],
        note=(
            "Requires the current default-on PFF stack: tier_engine, "
            "matchup, coverage, kicker, and dst_baseline inputs"
        ),
    )
    assert coverage["usage.route_rate"] == SignalCoverage(
        enabled=True,
        status="partial",
        covered_seasons=[2023],
        missing_seasons=[2024],
        note=(
            "Requires the PFF summary trio from the processed PFF root "
            "plus rosters_weekly cache to build the crosswalk"
        ),
    )


def test_typed_config_paths_override_module_defaults(tmp_path, monkeypatch):
    pff_root = tmp_path / "custom" / "processed" / "nfl"
    route_rate_root = pff_root.parent
    props_root = tmp_path / "custom" / "props"
    cache_dir = tmp_path / "cache"

    monkeypatch.setattr(coverage_module, "DEFAULT_PFF_DIR", tmp_path / "wrong" / "nfl")
    monkeypatch.setattr(coverage_module, "DEFAULT_PFF_ROUTE_RATE_DIR", tmp_path / "wrong" / "processed")
    monkeypatch.setattr(coverage_module, "DEFAULT_PROPS_DIR", tmp_path / "wrong" / "props")

    engine_configs = _default_engine_configs()
    engine_configs["usage_config"] = UsageConfig()
    engine_configs["pff_config"].data_dir = str(pff_root)
    engine_configs["props_config"].cache_dir = str(props_root)

    _write_default_pff_stack(pff_root, (2023, 2024))
    for facet in ("receiving_summary", "rushing_summary", "passing_summary"):
        _write_parquet_placeholder(route_rate_root / f"{facet}_2023.parquet")
        _write_parquet_placeholder(route_rate_root / f"{facet}_2024.parquet")
    _write_roster_cache(cache_dir, (2023, 2024))
    for season in (2023, 2024):
        _write_parquet_placeholder(props_root / f"props_{season}_week01.parquet")

    coverage = collect_signal_coverage(
        engine_configs,
        [2023, 2024],
        cache_dir=cache_dir,
    )

    assert coverage["pff"] == SignalCoverage(
        enabled=True,
        status="full",
        covered_seasons=[2023, 2024],
        missing_seasons=[],
        note=(
            "Requires the current default-on PFF stack: tier_engine, "
            "matchup, coverage, kicker, and dst_baseline inputs"
        ),
    )
    assert coverage["props"] == SignalCoverage(
        enabled=True,
        status="full",
        covered_seasons=[2023, 2024],
        missing_seasons=[],
        note="Forward-only unless season parquet files exist in ~/.fantasy-sim/pff/props",
    )
    assert coverage["usage.route_rate"] == SignalCoverage(
        enabled=True,
        status="full",
        covered_seasons=[2023, 2024],
        missing_seasons=[],
        note=(
            "Requires the PFF summary trio from the processed PFF root "
            "plus rosters_weekly cache to build the crosswalk"
        ),
    )


def test_disabled_signals_report_disabled_explicitly():
    coverage = collect_signal_coverage(
        _base_config(
            props_enabled=False,
            pff_enabled=False,
            weather_enabled=False,
            usage_enabled=False,
            usage_ngs_enabled=False,
            usage_route_rate_enabled=False,
        ),
        [2023, 2024],
    )

    assert coverage["props"].status == "disabled"
    assert coverage["pff"].status == "disabled"
    assert coverage["weather"].status == "disabled"
    assert coverage["usage"].status == "disabled"
    assert coverage["usage.ngs"].status == "disabled"
    assert coverage["usage.route_rate"].status == "disabled"

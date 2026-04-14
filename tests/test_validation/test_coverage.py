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
from fantasy_sim.data.ensemble.models import EnsembleConfig, FfOpportunityConfig
from fantasy_sim.data.tracking.models import TrackingConfig
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
    tracking_enabled: bool = False,
    tracking_receiver_enabled: bool = True,
    tracking_rb_enabled: bool = True,
    tracking_qb_enabled: bool = True,
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
        "tracking": {
            "enabled": tracking_enabled,
            "receiver_participation": {"enabled": tracking_receiver_enabled},
            "rb_efficiency": {"enabled": tracking_rb_enabled},
            "qb_context": {"enabled": tracking_qb_enabled},
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


def _write_pff_summary_trio(pff_dir: Path, seasons: tuple[int, ...]) -> None:
    for season in seasons:
        for facet in ("receiving_summary", "rushing_summary", "passing_summary"):
            _write_parquet_placeholder(pff_dir / f"{facet}_{season}.parquet")


def _write_market_history_player_markets(
    market_dir: Path,
    season: int,
    *,
    include_anytime: bool = True,
) -> None:
    import polars as pl

    market_keys = [
        "player_pass_yds",
        "player_pass_tds",
        "player_rush_yds",
        "player_receptions",
        "player_reception_yds",
    ]
    if include_anytime:
        market_keys.append("player_anytime_td")

    size = len(market_keys)
    pl.DataFrame(
        {
            "season": [season] * size,
            "week": [1] * size,
            "event_id": ["event-1"] * size,
            "schedule_game_id": [f"{season}_01_ARI_BUF"] * size,
            "snapshot_label": ["close_core8"] * size,
            "snapshot_timestamp": ["2024-09-08T17:00:00Z"] * size,
            "market_key": market_keys,
            "player_name": ["Josh Allen"] * size,
            "player_name_normalized": ["josh allen"] * size,
            "home_team": ["Buffalo Bills"] * size,
            "away_team": ["Arizona Cardinals"] * size,
            "bookmaker_count": [3] * size,
            "line": [255.5, 2.0, 25.5, 5.5, 65.5] + ([None] if include_anytime else []),
            "line_stddev": [0.0, 0.0, 0.5, 0.0, 0.5] + ([None] if include_anytime else []),
            "over_price": [1.9] * size,
            "under_price": [1.9] * size,
            "yes_price": ([None] * (size - 1)) + ([2.2] if include_anytime else [None]),
            "implied_prob": ([None] * (size - 1)) + ([0.4545] if include_anytime else [None]),
        }
    ).write_parquet(market_dir / f"player_markets_{season}_close_core8.parquet")


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


def test_pff_depth_role_reports_full_when_crosswalk_inputs_exist(tmp_path):
    pff_dir = tmp_path / "pff"
    cache_dir = tmp_path / "cache"
    for season in (2023, 2024):
        _write_parquet_placeholder(pff_dir / f"receiving_depth_{season}.parquet")
        _write_parquet_placeholder(cache_dir / f"rosters_weekly_{season}.parquet")
    _write_pff_summary_trio(pff_dir, (2023, 2024))

    engine_configs = _default_engine_configs()
    engine_configs["pff_config"].depth_role.enabled = True

    coverage = collect_signal_coverage(
        engine_configs,
        [2023, 2024],
        pff_dir=pff_dir,
        cache_dir=cache_dir,
    )

    assert coverage["pff.depth_role"] == SignalCoverage(
        enabled=True,
        status="full",
        covered_seasons=[2023, 2024],
        missing_seasons=[],
        note=(
            "Requires receiving_depth parquet, the PFF summary trio, "
            "and rosters_weekly cache to build the PFF crosswalk"
        ),
    )
    assert coverage["pff.depth_role.wr"].status == "full"
    assert coverage["pff.depth_role.te"].status == "full"


def test_pff_depth_role_reports_partial_when_crosswalk_inputs_are_missing_for_one_season(tmp_path):
    pff_dir = tmp_path / "pff"
    cache_dir = tmp_path / "cache"
    _write_parquet_placeholder(pff_dir / "receiving_depth_2023.parquet")
    _write_parquet_placeholder(cache_dir / "rosters_weekly_2023.parquet")
    _write_parquet_placeholder(cache_dir / "rosters_weekly_2024.parquet")
    _write_pff_summary_trio(pff_dir, (2023, 2024))

    engine_configs = _default_engine_configs()
    engine_configs["pff_config"].depth_role.enabled = True

    coverage = collect_signal_coverage(
        engine_configs,
        [2023, 2024],
        pff_dir=pff_dir,
        cache_dir=cache_dir,
    )

    assert coverage["pff.depth_role"] == SignalCoverage(
        enabled=True,
        status="partial",
        covered_seasons=[2023],
        missing_seasons=[2024],
        note=(
            "Requires receiving_depth parquet, the PFF summary trio, "
            "and rosters_weekly cache to build the PFF crosswalk"
        ),
    )


def test_pff_depth_role_position_signals_respect_configured_positions(tmp_path):
    pff_dir = tmp_path / "pff"
    cache_dir = tmp_path / "cache"
    for season in (2024,):
        _write_parquet_placeholder(pff_dir / f"receiving_depth_{season}.parquet")
        _write_parquet_placeholder(cache_dir / f"rosters_weekly_{season}.parquet")
    _write_pff_summary_trio(pff_dir, (2024,))

    engine_configs = _default_engine_configs()
    engine_configs["pff_config"].depth_role.enabled = True
    engine_configs["pff_config"].depth_role.positions = ("WR",)

    coverage = collect_signal_coverage(
        engine_configs,
        [2024],
        pff_dir=pff_dir,
        cache_dir=cache_dir,
    )

    assert coverage["pff.depth_role.wr"].status == "full"
    assert coverage["pff.depth_role.te"].status == "disabled"


def test_pff_depth_role_reports_none_when_summary_trio_is_missing(tmp_path):
    pff_dir = tmp_path / "pff"
    cache_dir = tmp_path / "cache"
    _write_parquet_placeholder(pff_dir / "receiving_depth_2024.parquet")
    _write_parquet_placeholder(cache_dir / "rosters_weekly_2024.parquet")

    engine_configs = _default_engine_configs()
    engine_configs["pff_config"].depth_role.enabled = True

    coverage = collect_signal_coverage(
        engine_configs,
        [2024],
        pff_dir=pff_dir,
        cache_dir=cache_dir,
    )

    assert coverage["pff.depth_role"] == SignalCoverage(
        enabled=True,
        status="none",
        covered_seasons=[],
        missing_seasons=[2024],
        note=(
            "Requires receiving_depth parquet, the PFF summary trio, "
            "and rosters_weekly cache to build the PFF crosswalk"
        ),
    )


def test_pff_qb_split_reports_full_when_inputs_exist(tmp_path):
    pff_dir = tmp_path / "pff"
    cache_dir = tmp_path / "cache"
    for season in (2023, 2024):
        _write_parquet_placeholder(pff_dir / f"passing_detail_{season}.parquet")
        _write_parquet_placeholder(pff_dir / f"passing_summary_{season}.parquet")
        _write_parquet_placeholder(cache_dir / f"rosters_weekly_{season}.parquet")

    engine_configs = _default_engine_configs()
    engine_configs["pff_config"].qb_split.enabled = True

    coverage = collect_signal_coverage(
        engine_configs,
        [2023, 2024],
        pff_dir=pff_dir,
        cache_dir=cache_dir,
    )

    assert coverage["pff.qb_split"] == SignalCoverage(
        enabled=True,
        status="full",
        covered_seasons=[2023, 2024],
        missing_seasons=[],
        note=(
            "Requires passing_detail parquet, passing_summary parquet, "
            "and rosters_weekly cache to build the PFF QB crosswalk"
        ),
    )


def test_pff_qb_split_reports_partial_when_one_season_is_missing(tmp_path):
    pff_dir = tmp_path / "pff"
    cache_dir = tmp_path / "cache"
    _write_parquet_placeholder(pff_dir / "passing_detail_2023.parquet")
    _write_parquet_placeholder(pff_dir / "passing_summary_2023.parquet")
    _write_parquet_placeholder(cache_dir / "rosters_weekly_2023.parquet")
    _write_parquet_placeholder(cache_dir / "rosters_weekly_2024.parquet")

    engine_configs = _default_engine_configs()
    engine_configs["pff_config"].qb_split.enabled = True

    coverage = collect_signal_coverage(
        engine_configs,
        [2023, 2024],
        pff_dir=pff_dir,
        cache_dir=cache_dir,
    )

    assert coverage["pff.qb_split"] == SignalCoverage(
        enabled=True,
        status="partial",
        covered_seasons=[2023],
        missing_seasons=[2024],
        note=(
            "Requires passing_detail parquet, passing_summary parquet, "
            "and rosters_weekly cache to build the PFF QB crosswalk"
        ),
    )


def test_pff_qb_split_disabled_when_parent_pff_is_disabled(tmp_path):
    pff_dir = tmp_path / "pff"
    cache_dir = tmp_path / "cache"
    _write_parquet_placeholder(pff_dir / "passing_detail_2024.parquet")
    _write_parquet_placeholder(pff_dir / "passing_summary_2024.parquet")
    _write_parquet_placeholder(cache_dir / "rosters_weekly_2024.parquet")

    engine_configs = _default_engine_configs()
    engine_configs["pff_config"].enabled = False
    engine_configs["pff_config"].qb_split.enabled = True

    coverage = collect_signal_coverage(
        engine_configs,
        [2024],
        pff_dir=pff_dir,
        cache_dir=cache_dir,
    )

    assert coverage["pff.qb_split"] == SignalCoverage(
        enabled=False,
        status="disabled",
        covered_seasons=[],
        missing_seasons=[],
        note=(
            "Requires passing_detail parquet, passing_summary parquet, "
            "and rosters_weekly cache to build the PFF QB crosswalk"
        ),
    )


def test_pff_qb_split_disabled_when_matchup_is_disabled(tmp_path):
    pff_dir = tmp_path / "pff"
    cache_dir = tmp_path / "cache"
    _write_parquet_placeholder(pff_dir / "passing_detail_2024.parquet")
    _write_parquet_placeholder(pff_dir / "passing_summary_2024.parquet")
    _write_parquet_placeholder(cache_dir / "rosters_weekly_2024.parquet")

    engine_configs = _default_engine_configs()
    engine_configs["pff_config"].qb_split.enabled = True
    engine_configs["pff_config"].matchup.enabled = False

    coverage = collect_signal_coverage(
        engine_configs,
        [2024],
        pff_dir=pff_dir,
        cache_dir=cache_dir,
    )

    assert coverage["pff.qb_split"] == SignalCoverage(
        enabled=False,
        status="disabled",
        covered_seasons=[],
        missing_seasons=[],
        note=(
            "Requires passing_detail parquet, passing_summary parquet, "
            "and rosters_weekly cache to build the PFF QB crosswalk"
        ),
    )


def test_pff_depth_role_efficiency_reports_full_when_inputs_exist(tmp_path):
    pff_dir = tmp_path / "pff"
    cache_dir = tmp_path / "cache"
    for season in (2023, 2024):
        for facet in ("receiving_depth", "receiving_summary", "rushing_summary", "passing_summary"):
            _write_parquet_placeholder(pff_dir / f"{facet}_{season}.parquet")
        _write_parquet_placeholder(cache_dir / f"rosters_weekly_{season}.parquet")

    engine_configs = _default_engine_configs()
    engine_configs["pff_config"].depth_role.enabled = True
    engine_configs["pff_config"].depth_role.efficiency.enabled = True

    coverage = collect_signal_coverage(
        engine_configs,
        [2023, 2024],
        pff_dir=pff_dir,
        cache_dir=cache_dir,
    )

    assert coverage["pff.depth_role.efficiency"] == SignalCoverage(
        enabled=True,
        status="full",
        covered_seasons=[2023, 2024],
        missing_seasons=[],
        note="Requires receiving_depth, the PFF summary trio, and rosters_weekly cache to support the depth-role efficiency path",
    )


def test_pff_depth_role_efficiency_disabled_when_parent_depth_role_disabled(tmp_path):
    pff_dir = tmp_path / "pff"
    cache_dir = tmp_path / "cache"
    for facet in ("receiving_depth", "receiving_summary", "rushing_summary", "passing_summary"):
        _write_parquet_placeholder(pff_dir / f"{facet}_2024.parquet")
    _write_parquet_placeholder(cache_dir / "rosters_weekly_2024.parquet")

    engine_configs = _default_engine_configs()
    engine_configs["pff_config"].enabled = True
    engine_configs["pff_config"].depth_role.enabled = True
    engine_configs["pff_config"].depth_role.efficiency.enabled = True
    engine_configs["pff_config"].depth_role.enabled = False

    coverage = collect_signal_coverage(
        engine_configs,
        [2024],
        pff_dir=pff_dir,
        cache_dir=cache_dir,
    )

    assert coverage["pff.depth_role.efficiency"].status == "disabled"


def test_pff_depth_role_is_disabled_when_parent_pff_is_disabled(tmp_path):
    pff_dir = tmp_path / "pff"
    cache_dir = tmp_path / "cache"
    for season in (2024,):
        _write_parquet_placeholder(pff_dir / f"receiving_depth_{season}.parquet")
        _write_parquet_placeholder(cache_dir / f"rosters_weekly_{season}.parquet")
    _write_pff_summary_trio(pff_dir, (2024,))

    engine_configs = _default_engine_configs()
    engine_configs["pff_config"].enabled = False
    engine_configs["pff_config"].depth_role.enabled = True

    coverage = collect_signal_coverage(
        engine_configs,
        [2024],
        pff_dir=pff_dir,
        cache_dir=cache_dir,
    )

    assert coverage["pff.depth_role"].status == "disabled"
    assert coverage["pff.depth_role.wr"].status == "disabled"
    assert coverage["pff.depth_role.te"].status == "disabled"


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


def test_tracking_reports_slice_and_family_coverage_from_required_inputs(tmp_path):
    cache_dir = tmp_path / "cache"
    for season in (2023, 2024):
        _write_parquet_placeholder(cache_dir / f"pbp_{season}.parquet")
        _write_parquet_placeholder(cache_dir / f"ftn_charting_{season}.parquet")
        _write_parquet_placeholder(cache_dir / f"participation_{season}.parquet")
        _write_parquet_placeholder(cache_dir / f"ngs_passing_{season}.parquet")
    _write_parquet_placeholder(cache_dir / "ngs_rushing_2023.parquet")

    coverage = collect_signal_coverage(
        _base_config(tracking_enabled=True),
        [2023, 2024],
        cache_dir=cache_dir,
    )

    assert coverage["tracking.receiver_participation"] == SignalCoverage(
        enabled=True,
        status="full",
        covered_seasons=[2023, 2024],
        missing_seasons=[],
        note="Requires FTN charting plus season PBP parquet coverage for each test season",
    )
    assert coverage["tracking.rb_efficiency"] == SignalCoverage(
        enabled=True,
        status="partial",
        covered_seasons=[2023],
        missing_seasons=[2024],
        note="Requires FTN charting, NGS rushing, and season PBP parquet coverage for each test season",
    )
    assert coverage["tracking.qb_context"] == SignalCoverage(
        enabled=True,
        status="full",
        covered_seasons=[2023, 2024],
        missing_seasons=[],
        note="Requires participation, FTN charting, NGS passing, and season PBP parquet coverage for each test season",
    )
    assert coverage["tracking"] == SignalCoverage(
        enabled=True,
        status="partial",
        covered_seasons=[2023],
        missing_seasons=[2024],
        note="Tracking family coverage is the intersection of enabled tracking slices",
    )


def test_tracking_family_uses_intersection_of_enabled_slices_only(tmp_path):
    cache_dir = tmp_path / "cache"
    _write_parquet_placeholder(cache_dir / "pbp_2024.parquet")
    _write_parquet_placeholder(cache_dir / "ftn_charting_2024.parquet")

    coverage = collect_signal_coverage(
        {
            "tracking_config": TrackingConfig(
                enabled=True,
                rb_efficiency=TrackingConfig().rb_efficiency,
                receiver_participation=TrackingConfig().receiver_participation,
                qb_context=TrackingConfig().qb_context,
            )
        },
        [2024],
        cache_dir=cache_dir,
    )

    assert coverage["tracking"].status == "none"

    typed_config = TrackingConfig(enabled=True)
    typed_config.rb_efficiency.enabled = False
    typed_config.qb_context.enabled = False
    coverage = collect_signal_coverage(
        {"tracking_config": typed_config},
        [2024],
        cache_dir=cache_dir,
    )

    assert coverage["tracking.receiver_participation"].covered_seasons == [2024]
    assert coverage["tracking.rb_efficiency"].status == "disabled"
    assert coverage["tracking.qb_context"].status == "disabled"
    assert coverage["tracking"] == SignalCoverage(
        enabled=True,
        status="full",
        covered_seasons=[2024],
        missing_seasons=[],
        note="Tracking family coverage is the intersection of enabled tracking slices",
    )


def test_market_history_reports_partial_for_covered_2023_only(tmp_path):
    market_dir = tmp_path / "market-history"
    cache_dir = tmp_path / "cache"
    market_dir.mkdir()
    _write_market_history_player_markets(market_dir, 2023)
    _write_roster_cache(cache_dir, (2023,))

    coverage = collect_signal_coverage(
        {"market_history": {"enabled": True, "data_dir": str(market_dir)}},
        [2022, 2023, 2024],
        cache_dir=cache_dir,
    )

    assert coverage["market_history"] == SignalCoverage(
        enabled=True,
        status="partial",
        covered_seasons=[2023],
        missing_seasons=[2022, 2024],
        note=(
            "Requires player_markets_<season>_<snapshot_label>.parquet plus "
            "rosters_weekly cache to build the crosswalk"
        ),
    )
    assert coverage["market_history.crosswalk"].covered_seasons == [2023]
    assert coverage["market_history.pass_yards"].covered_seasons == [2023]
    assert coverage["market_history.pass_tds"].covered_seasons == [2023]
    assert coverage["market_history.rush_yards"].covered_seasons == [2023]
    assert coverage["market_history.receptions"].covered_seasons == [2023]
    assert coverage["market_history.receiving_yards"].covered_seasons == [2023]
    assert coverage["market_history.dispersion"].covered_seasons == [2023]
    assert coverage["market_history.anytime_td"].covered_seasons == [2023]


def test_market_history_top_level_excludes_season_missing_enabled_feature_columns(tmp_path):
    market_dir = tmp_path / "market-history"
    cache_dir = tmp_path / "cache"
    market_dir.mkdir()
    _write_market_history_player_markets(market_dir, 2023, include_anytime=False)
    _write_roster_cache(cache_dir, (2023,))

    coverage = collect_signal_coverage(
        {"market_history": {"enabled": True, "data_dir": str(market_dir)}},
        [2023],
        cache_dir=cache_dir,
    )

    assert coverage["market_history"] == SignalCoverage(
        enabled=True,
        status="none",
        covered_seasons=[],
        missing_seasons=[2023],
        note=(
            "Requires player_markets_<season>_<snapshot_label>.parquet plus "
            "rosters_weekly cache to build the crosswalk"
        ),
    )
    assert coverage["market_history.crosswalk"].covered_seasons == [2023]
    assert coverage["market_history.pass_yards"].covered_seasons == [2023]
    assert coverage["market_history.pass_tds"].covered_seasons == [2023]
    assert coverage["market_history.rush_yards"].covered_seasons == [2023]
    assert coverage["market_history.receptions"].covered_seasons == [2023]
    assert coverage["market_history.receiving_yards"].covered_seasons == [2023]
    assert coverage["market_history.dispersion"].covered_seasons == [2023]
    assert coverage["market_history.anytime_td"].covered_seasons == []


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
            "for requested test seasons; runtime player-week blend coverage is not "
            "yet summarized here"
        ),
    )


def test_ensemble_ff_opportunity_supports_typed_ensemble_config():
    coverage = collect_signal_coverage(
        {
            "ensemble_config": EnsembleConfig(
                enabled=True,
                ff_opportunity=FfOpportunityConfig(enabled=True),
            )
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
            "for requested test seasons; runtime player-week blend coverage is not "
            "yet summarized here"
        ),
    )


def test_availability_and_role_trend_report_partial_when_explicit_inputs_are_sparse(tmp_path):
    cache_dir = tmp_path / "cache"
    _write_parquet_placeholder(cache_dir / "player_stats_week_2023.parquet")
    _write_parquet_placeholder(cache_dir / "snap_counts_2023.parquet")
    _write_parquet_placeholder(cache_dir / "rosters_weekly_2023.parquet")
    _write_parquet_placeholder(cache_dir / "depth_charts_2023.parquet")

    config = {
        "availability": {
            "enabled": True,
            "positions": ["QB", "RB", "WR", "TE"],
            "injuries": {"enabled": True},
            "depth_charts": {"enabled": True},
            "usage_fallback": {"enabled": True},
        },
        "role_trend": {"enabled": True, "positions": ["QB", "RB", "WR", "TE"]},
    }

    coverage = collect_signal_coverage(config, [2023, 2024], cache_dir=cache_dir)

    assert coverage["availability"] == SignalCoverage(
        enabled=True,
        status="partial",
        covered_seasons=[2023],
        missing_seasons=[2024],
        note=(
            "Explicit coverage requires rosters_weekly plus depth_charts cache; "
            "injuries can further refine hard decisions when present"
        ),
    )
    assert coverage["availability.injuries"] == SignalCoverage(
        enabled=True,
        status="none",
        covered_seasons=[],
        missing_seasons=[2023, 2024],
        note="Hard injury availability decisions require cached injuries parquet for the tested season",
    )
    assert coverage["availability.depth_charts"] == SignalCoverage(
        enabled=True,
        status="partial",
        covered_seasons=[2023],
        missing_seasons=[2024],
        note="Hard starter and promotion decisions require cached depth_charts parquet for the tested season",
    )
    assert coverage["availability.usage_fallback"] == SignalCoverage(
        enabled=True,
        status="partial",
        covered_seasons=[2023],
        missing_seasons=[2024],
        note="Soft-only fallback requires player_stats_week, snap_counts, and rosters_weekly parquet coverage",
    )
    assert coverage["role_trend"] == SignalCoverage(
        enabled=True,
        status="partial",
        covered_seasons=[2023],
        missing_seasons=[2024],
        note="Role trend uses weekly player_stats coverage; snap_counts can augment but do not create hard decisions",
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

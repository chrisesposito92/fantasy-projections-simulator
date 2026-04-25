"""Tests for validation signal coverage reporting."""

from __future__ import annotations

import json
from pathlib import Path

from fantasy_sim.config.loader import load_defaults
from fantasy_sim.data.qb_rushing import (
    DEFAULT_QB_DESIGNED_RUN_ARTIFACT_DIR,
    QB_DESIGNED_RUN_MODEL_TYPE,
    QB_DESIGNED_RUN_SCHEMA_VERSION,
    QB_SCRAMBLE_MODEL_TYPE,
    QB_SCRAMBLE_SCHEMA_VERSION,
)
from fantasy_sim.data.play_call_model.models import (
    PLAY_CALL_MODEL_SCHEMA_VERSION,
    PLAY_CALL_MODEL_TYPE,
)
from fantasy_sim.data.target_selection.models import (
    TARGET_SELECTION_MODEL_TYPE,
    TARGET_SELECTION_SCHEMA_VERSION,
)
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


def _write_parquet(path: Path, data: dict[str, list[object]]) -> None:
    import polars as pl

    path.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(data).write_parquet(path)


def _write_target_selection_artifact(
    path: Path,
    *,
    schema_version: int = TARGET_SELECTION_SCHEMA_VERSION,
    model_type: str = TARGET_SELECTION_MODEL_TYPE,
    coefficients: dict[str, object] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": schema_version,
                "model_type": model_type,
                "target_season": 2024,
                "feature_names": ["is_te"],
                "coefficients": coefficients if coefficients is not None else {"is_te": 1.0},
            }
        )
    )


def _write_play_call_model_artifact(path: Path) -> None:
    _write_custom_play_call_model_artifact(path)


def _write_custom_play_call_model_artifact(
    path: Path,
    *,
    target_season: int = 2024,
    source_seasons: list[object] | None = None,
    feature_names: list[object] | None = None,
    coefficients: dict[str, object] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": PLAY_CALL_MODEL_SCHEMA_VERSION,
                "model_type": PLAY_CALL_MODEL_TYPE,
                "target_season": target_season,
                "source_seasons": source_seasons if source_seasons is not None else [2023],
                "feature_names": feature_names if feature_names is not None else ["intercept"],
                "coefficients": coefficients if coefficients is not None else {"intercept": 0.0},
            }
        )
    )


def _write_qb_scramble_artifact(
    path: Path,
    *,
    feature_names: list[object] | None = None,
    coefficients: dict[str, object] | None = None,
    diagnostics: dict[str, object] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": QB_SCRAMBLE_SCHEMA_VERSION,
                "model_type": QB_SCRAMBLE_MODEL_TYPE,
                "target_season": 2024,
                "source_seasons": [2023],
                "feature_names": feature_names if feature_names is not None else ["intercept"],
                "coefficients": coefficients if coefficients is not None else {"intercept": 0.0},
                "diagnostics": diagnostics
                if diagnostics is not None
                else {"num_examples": 500, "scramble_rate": 0.06},
            }
        ),
        encoding="utf-8",
    )


def _write_qb_designed_run_artifact(path: Path, **overrides) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    artifact = {
        "schema_version": QB_DESIGNED_RUN_SCHEMA_VERSION,
        "model_type": QB_DESIGNED_RUN_MODEL_TYPE,
        "target_season": 2024,
        "source_seasons": [2023],
        "feature_names": ["intercept"],
        "coefficients": {"intercept": 0.0},
        "factor_clamp": [0.50, 2.00],
        "priors": {"league": 0.06, "mobility_tiers": {}},
        "tail_buckets": {"global": [5, 8, 12]},
        "diagnostics": {"num_examples": 500, "designed_qb_run_rate": 0.06},
    }
    artifact.update(overrides)
    path.write_text(json.dumps(artifact), encoding="utf-8")


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


def _write_pff_summary_trio(
    pff_dir: Path,
    seasons: tuple[int, ...],
    *,
    columns_by_facet: dict[str, tuple[str, ...]] | None = None,
) -> None:
    for season in seasons:
        for facet in ("receiving_summary", "rushing_summary", "passing_summary"):
            columns = (
                columns_by_facet.get(facet)
                if columns_by_facet is not None and facet in columns_by_facet
                else ("player_id", "player", "team")
            )
            data: dict[str, list[object]] = {}
            for column in columns:
                if column == "player_id":
                    data[column] = [f"pff-{season}-{facet}"]
                elif column == "player":
                    data[column] = [f"Player {season}"]
                elif column == "team":
                    data[column] = ["BUF"]
                else:
                    data[column] = [1]
            _write_parquet(pff_dir / f"{facet}_{season}.parquet", data)


def _write_route_rate_crosswalk_inputs(
    pff_dir: Path,
    cache_dir: Path,
    seasons: tuple[int, ...],
    *,
    receiving_summary_columns: tuple[str, ...] = (
        "player_id",
        "player",
        "team",
        "targets",
        "routes",
        "week",
    ),
    rushing_summary_columns: tuple[str, ...] = ("player_id", "player", "team"),
    passing_summary_columns: tuple[str, ...] = ("player_id", "player", "team"),
) -> None:
    for season in seasons:
        receiving_data: dict[str, list[object]] = {}
        for column in receiving_summary_columns:
            if column == "player_id":
                receiving_data[column] = [f"pff-{season}"]
            elif column == "player":
                receiving_data[column] = [f"Player {season}"]
            elif column == "team":
                receiving_data[column] = ["BUF"]
            elif column == "targets":
                receiving_data[column] = [4]
            elif column == "routes":
                receiving_data[column] = [20]
            elif column == "week":
                receiving_data[column] = [1]
            else:
                receiving_data[column] = [1]
        _write_parquet(pff_dir / f"receiving_summary_{season}.parquet", receiving_data)
        _write_parquet(
            pff_dir / f"rushing_summary_{season}.parquet",
            {
                column: [f"pff-{season}" if column == "player_id" else f"Player {season}" if column == "player" else "BUF" if column == "team" else 1]
                for column in rushing_summary_columns
            },
        )
        _write_parquet(
            pff_dir / f"passing_summary_{season}.parquet",
            {
                column: [f"pff-{season}" if column == "player_id" else f"Player {season}" if column == "player" else "BUF" if column == "team" else 1]
                for column in passing_summary_columns
            },
        )
    _write_roster_cache(cache_dir, seasons)


def _write_team_context_inputs(
    pff_dir: Path,
    seasons: tuple[int, ...],
    *,
    offense_run_blocking_columns: tuple[str, ...] = (
        "team",
        "grades_run_block",
        "snap_counts_run_block",
        "week",
    ),
    passing_summary_columns: tuple[str, ...] = (
        "team",
        "grades_pass",
        "passing_snaps",
        "week",
    ),
) -> None:
    for season in seasons:
        offense_run_blocking_data: dict[str, list[object]] = {}
        for column in offense_run_blocking_columns:
            if column == "team":
                offense_run_blocking_data[column] = ["BUF"]
            elif column == "grades_run_block":
                offense_run_blocking_data[column] = [72.5]
            elif column == "snap_counts_run_block":
                offense_run_blocking_data[column] = [30]
            elif column == "week":
                offense_run_blocking_data[column] = [1]
            else:
                offense_run_blocking_data[column] = [1]
        _write_parquet(
            pff_dir / f"offense_run_blocking_{season}.parquet",
            offense_run_blocking_data,
        )

        passing_summary_data: dict[str, list[object]] = {}
        for column in passing_summary_columns:
            if column == "team":
                passing_summary_data[column] = ["BUF"]
            elif column == "grades_pass":
                passing_summary_data[column] = [75.0]
            elif column == "passing_snaps":
                passing_summary_data[column] = [35]
            elif column == "week":
                passing_summary_data[column] = [1]
            else:
                passing_summary_data[column] = [1]
        _write_parquet(
            pff_dir / f"passing_summary_{season}.parquet",
            passing_summary_data,
        )


def _write_team_context_pbp(
    cache_dir: Path,
    seasons: tuple[int, ...],
    *,
    columns: tuple[str, ...] = ("season", "posteam", "play_type", "week"),
) -> None:
    for season in seasons:
        pbp_data: dict[str, list[object]] = {}
        for column in columns:
            if column == "season":
                pbp_data[column] = [season, season]
            elif column == "posteam":
                pbp_data[column] = ["BUF", "KC"]
            elif column == "play_type":
                pbp_data[column] = ["pass", "run"]
            elif column == "week":
                pbp_data[column] = [1, 1]
            else:
                pbp_data[column] = [1, 1]
        _write_parquet(cache_dir / f"pbp_{season}.parquet", pbp_data)


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
    _write_default_pff_stack(pff_dir, (2023,))
    _write_route_rate_crosswalk_inputs(pff_dir, cache_dir, (2023, 2024))

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
            "Requires the PFF summary trio from the NFL processed PFF root "
            "plus rosters_weekly cache to build the crosswalk; "
            "receiving_summary must also include player_id, targets, routes, "
            "and week for the strict temporal leak guard"
        ),
    )


def test_usage_route_rate_reports_partial_when_crosswalk_inputs_are_missing_for_one_season(tmp_path):
    pff_dir = tmp_path / "pff"
    cache_dir = tmp_path / "cache"
    _write_default_pff_stack(pff_dir, (2023, 2024))
    _write_route_rate_crosswalk_inputs(pff_dir, cache_dir, (2023, 2024))
    (cache_dir / "rosters_weekly_2024.parquet").unlink()

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
            "Requires the PFF summary trio from the NFL processed PFF root "
            "plus rosters_weekly cache to build the crosswalk; "
            "receiving_summary must also include player_id, targets, routes, "
            "and week for the strict temporal leak guard"
        ),
    )


def test_usage_route_rate_requires_receiving_summary_route_rate_columns(tmp_path):
    pff_dir = tmp_path / "pff"
    cache_dir = tmp_path / "cache"
    _write_default_pff_stack(pff_dir, (2024,))
    _write_route_rate_crosswalk_inputs(
        pff_dir,
        cache_dir,
        (2024,),
        receiving_summary_columns=("player_id",),
    )

    engine_configs = _default_engine_configs()
    engine_configs["usage_config"] = UsageConfig()

    coverage = collect_signal_coverage(
        engine_configs,
        [2024],
        cache_dir=cache_dir,
        pff_dir=pff_dir,
    )

    assert coverage["usage.route_rate"] == SignalCoverage(
        enabled=True,
        status="none",
        covered_seasons=[],
        missing_seasons=[2024],
        note=(
            "Requires the PFF summary trio from the NFL processed PFF root "
            "plus rosters_weekly cache to build the crosswalk; "
            "receiving_summary must also include player_id, targets, routes, "
            "and week for the strict temporal leak guard"
        ),
    )


def test_usage_route_rate_requires_receiving_summary_week_for_strict_runtime_alignment(tmp_path):
    pff_dir = tmp_path / "pff"
    cache_dir = tmp_path / "cache"
    _write_default_pff_stack(pff_dir, (2024,))
    _write_route_rate_crosswalk_inputs(
        pff_dir,
        cache_dir,
        (2024,),
        receiving_summary_columns=("player_id", "player", "team", "targets", "routes"),
    )

    engine_configs = _default_engine_configs()
    engine_configs["usage_config"] = UsageConfig()

    coverage = collect_signal_coverage(
        engine_configs,
        [2024],
        cache_dir=cache_dir,
        pff_dir=pff_dir,
    )

    assert coverage["usage.route_rate"] == SignalCoverage(
        enabled=True,
        status="none",
        covered_seasons=[],
        missing_seasons=[2024],
        note=(
            "Requires the PFF summary trio from the NFL processed PFF root "
            "plus rosters_weekly cache to build the crosswalk; "
            "receiving_summary must also include player_id, targets, routes, "
            "and week for the strict temporal leak guard"
        ),
    )


def test_usage_route_rate_reports_none_when_summary_trio_lacks_crosswalk_columns(tmp_path):
    pff_dir = tmp_path / "pff"
    cache_dir = tmp_path / "cache"
    _write_default_pff_stack(pff_dir, (2024,))
    _write_route_rate_crosswalk_inputs(
        pff_dir,
        cache_dir,
        (2024,),
        receiving_summary_columns=("player_id", "targets", "routes"),
        rushing_summary_columns=("player_id",),
        passing_summary_columns=("player_id",),
    )

    engine_configs = _default_engine_configs()
    engine_configs["usage_config"] = UsageConfig()

    coverage = collect_signal_coverage(
        engine_configs,
        [2024],
        cache_dir=cache_dir,
        pff_dir=pff_dir,
    )

    assert coverage["usage.route_rate"] == SignalCoverage(
        enabled=True,
        status="none",
        covered_seasons=[],
        missing_seasons=[2024],
        note=(
            "Requires the PFF summary trio from the NFL processed PFF root "
            "plus rosters_weekly cache to build the crosswalk; "
            "receiving_summary must also include player_id, targets, routes, "
            "and week for the strict temporal leak guard"
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


def test_pff_rb_scheme_fit_reports_full_when_inputs_exist(tmp_path):
    pff_dir = tmp_path / "pff"
    cache_dir = tmp_path / "cache"
    for season in (2023, 2024):
        _write_parquet_placeholder(pff_dir / f"rushing_direction_{season}.parquet")
        _write_parquet_placeholder(pff_dir / f"offense_run_blocking_{season}.parquet")
        _write_parquet_placeholder(pff_dir / f"rushing_summary_{season}.parquet")
        _write_parquet_placeholder(cache_dir / f"rosters_weekly_{season}.parquet")

    engine_configs = _default_engine_configs()
    engine_configs["pff_config"].rb_scheme_fit.enabled = True

    coverage = collect_signal_coverage(
        engine_configs,
        [2023, 2024],
        pff_dir=pff_dir,
        cache_dir=cache_dir,
    )

    assert coverage["pff.rb_scheme_fit"] == SignalCoverage(
        enabled=True,
        status="full",
        covered_seasons=[2023, 2024],
        missing_seasons=[],
        note=(
            "Requires rushing_direction parquet, offense_run_blocking parquet, "
            "rushing_summary parquet, and rosters_weekly cache to build the RB scheme-fit signal"
        ),
    )


def test_pff_rb_scheme_fit_reports_partial_when_one_required_input_is_missing(tmp_path):
    pff_dir = tmp_path / "pff"
    cache_dir = tmp_path / "cache"
    _write_parquet_placeholder(pff_dir / "rushing_direction_2023.parquet")
    _write_parquet_placeholder(pff_dir / "offense_run_blocking_2023.parquet")
    _write_parquet_placeholder(pff_dir / "rushing_summary_2023.parquet")
    _write_parquet_placeholder(cache_dir / "rosters_weekly_2023.parquet")
    _write_parquet_placeholder(pff_dir / "rushing_direction_2024.parquet")
    _write_parquet_placeholder(pff_dir / "rushing_summary_2024.parquet")
    _write_parquet_placeholder(cache_dir / "rosters_weekly_2024.parquet")

    engine_configs = _default_engine_configs()
    engine_configs["pff_config"].rb_scheme_fit.enabled = True

    coverage = collect_signal_coverage(
        engine_configs,
        [2023, 2024],
        pff_dir=pff_dir,
        cache_dir=cache_dir,
    )

    assert coverage["pff.rb_scheme_fit"] == SignalCoverage(
        enabled=True,
        status="partial",
        covered_seasons=[2023],
        missing_seasons=[2024],
        note=(
            "Requires rushing_direction parquet, offense_run_blocking parquet, "
            "rushing_summary parquet, and rosters_weekly cache to build the RB scheme-fit signal"
        ),
    )


def test_pff_rb_scheme_fit_disabled_when_parent_pff_is_disabled(tmp_path):
    pff_dir = tmp_path / "pff"
    cache_dir = tmp_path / "cache"
    _write_parquet_placeholder(pff_dir / "rushing_direction_2024.parquet")
    _write_parquet_placeholder(pff_dir / "offense_run_blocking_2024.parquet")
    _write_parquet_placeholder(pff_dir / "rushing_summary_2024.parquet")
    _write_parquet_placeholder(cache_dir / "rosters_weekly_2024.parquet")

    engine_configs = _default_engine_configs()
    engine_configs["pff_config"].enabled = False
    engine_configs["pff_config"].rb_scheme_fit.enabled = True

    coverage = collect_signal_coverage(
        engine_configs,
        [2024],
        pff_dir=pff_dir,
        cache_dir=cache_dir,
    )

    assert coverage["pff.rb_scheme_fit"] == SignalCoverage(
        enabled=False,
        status="disabled",
        covered_seasons=[],
        missing_seasons=[],
        note=(
            "Requires rushing_direction parquet, offense_run_blocking parquet, "
            "rushing_summary parquet, and rosters_weekly cache to build the RB scheme-fit signal"
        ),
    )


def test_pff_team_context_requires_previous_season_fallback_inputs(tmp_path):
    pff_dir = tmp_path / "pff"
    _write_team_context_inputs(pff_dir, (2022, 2023, 2024))

    engine_configs = _default_engine_configs()
    engine_configs["pff_config"].team_context.enabled = True
    engine_configs["pff_config"].team_context.pass_rate_sensitivity = 0.0

    coverage = collect_signal_coverage(
        engine_configs,
        [2023, 2024],
        pff_dir=pff_dir,
    )

    assert coverage["pff.team_context"] == SignalCoverage(
        enabled=True,
        status="full",
        covered_seasons=[2023, 2024],
        missing_seasons=[],
        note=(
            "Requires offense_run_blocking(team, grades_run_block, "
            "snap_counts_run_block) and passing_summary(team, grades_pass, "
            "passing_snaps) parquet for the tested season plus target_season-1 "
            "fallback coverage; season PBP parquet must include play_type, "
            "posteam, and season for the tested season and fallback season when "
            "team_context.pass_rate_sensitivity is nonzero"
        ),
    )


def test_pff_team_context_reports_partial_when_previous_season_fallback_is_missing(tmp_path):
    pff_dir = tmp_path / "pff"
    _write_team_context_inputs(pff_dir, (2023, 2024))

    engine_configs = _default_engine_configs()
    engine_configs["pff_config"].team_context.enabled = True
    engine_configs["pff_config"].team_context.pass_rate_sensitivity = 0.0

    coverage = collect_signal_coverage(
        engine_configs,
        [2023, 2024],
        pff_dir=pff_dir,
    )

    assert coverage["pff.team_context"] == SignalCoverage(
        enabled=True,
        status="partial",
        covered_seasons=[2024],
        missing_seasons=[2023],
        note=(
            "Requires offense_run_blocking(team, grades_run_block, "
            "snap_counts_run_block) and passing_summary(team, grades_pass, "
            "passing_snaps) parquet for the tested season plus target_season-1 "
            "fallback coverage; season PBP parquet must include play_type, "
            "posteam, and season for the tested season and fallback season when "
            "team_context.pass_rate_sensitivity is nonzero"
        ),
    )


def test_pff_team_context_reports_partial_when_pbp_fallback_is_missing_and_pass_rate_is_nonzero(tmp_path):
    pff_dir = tmp_path / "pff"
    cache_dir = tmp_path / "cache"
    _write_team_context_inputs(pff_dir, (2022, 2023, 2024))
    _write_team_context_pbp(cache_dir, (2022, 2023))

    engine_configs = _default_engine_configs()
    engine_configs["pff_config"].team_context.enabled = True
    engine_configs["pff_config"].team_context.pass_rate_sensitivity = 0.08

    coverage = collect_signal_coverage(
        engine_configs,
        [2023, 2024],
        pff_dir=pff_dir,
        cache_dir=cache_dir,
    )

    assert coverage["pff.team_context"] == SignalCoverage(
        enabled=True,
        status="partial",
        covered_seasons=[2023],
        missing_seasons=[2024],
        note=(
            "Requires offense_run_blocking(team, grades_run_block, "
            "snap_counts_run_block) and passing_summary(team, grades_pass, "
            "passing_snaps) parquet for the tested season plus target_season-1 "
            "fallback coverage; season PBP parquet must include play_type, "
            "posteam, and season for the tested season and fallback season when "
            "team_context.pass_rate_sensitivity is nonzero"
        ),
    )


def test_pff_team_context_requires_runtime_schema_columns(tmp_path):
    pff_dir = tmp_path / "pff"
    _write_team_context_inputs(
        pff_dir,
        (2024,),
        offense_run_blocking_columns=("team", "snap_counts_run_block"),
    )

    engine_configs = _default_engine_configs()
    engine_configs["pff_config"].team_context.enabled = True
    engine_configs["pff_config"].team_context.min_games = 0
    engine_configs["pff_config"].team_context.pass_rate_sensitivity = 0.0

    coverage = collect_signal_coverage(
        engine_configs,
        [2024],
        pff_dir=pff_dir,
    )

    assert coverage["pff.team_context"] == SignalCoverage(
        enabled=True,
        status="none",
        covered_seasons=[],
        missing_seasons=[2024],
        note=(
            "Requires offense_run_blocking(team, grades_run_block, "
            "snap_counts_run_block) and passing_summary(team, grades_pass, "
            "passing_snaps) parquet for the tested season plus target_season-1 "
            "fallback coverage; season PBP parquet must include play_type, "
            "posteam, and season for the tested season and fallback season when "
            "team_context.pass_rate_sensitivity is nonzero"
        ),
    )


def test_goal_line_concentration_reports_full_without_external_inputs():
    coverage = collect_signal_coverage(
        {"goal_line_concentration": {"enabled": True}},
        [2023, 2024],
    )

    assert coverage["goal_line_concentration"] == SignalCoverage(
        enabled=True,
        status="full",
        covered_seasons=[2023, 2024],
        missing_seasons=[],
        note="Uses existing roster-share ordering only; no external historical store required",
    )


def test_td_tendency_and_i5_report_full_when_red_zone_inputs_and_crosswalk_exist(tmp_path):
    pff_dir = tmp_path / "pff"
    cache_dir = tmp_path / "cache"
    for season in (2023, 2024):
        _write_parquet(
            pff_dir / f"fantasy_receiving_{season}.parquet",
            {
                "player_id": ["p1"],
                "week": [1],
                "rz_rec_targ": [1],
                "rz_rec_tds": [1],
                "rz_rush_carries": [1],
                "rz_rush_tds": [1],
                "i5_rush_carries": [1],
                "i5_rush_tds": [1],
            },
        )
        _write_parquet(
            pff_dir / f"fantasy_passing_{season}.parquet",
            {
                "player_id": ["p1"],
                "week": [1],
                "rz_rush_carries": [1],
                "rz_rush_tds": [1],
                "i5_rush_carries": [1],
                "i5_rush_tds": [1],
            },
        )
    _write_pff_summary_trio(pff_dir, (2023, 2024))
    _write_roster_cache(cache_dir, (2023, 2024))

    coverage = collect_signal_coverage(
        {"td_tendency": {"enabled": True, "i5_enabled": True}},
        [2023, 2024],
        pff_dir=pff_dir,
        cache_dir=cache_dir,
    )

    assert coverage["td_tendency"] == SignalCoverage(
        enabled=True,
        status="full",
        covered_seasons=[2023, 2024],
        missing_seasons=[],
        note=(
            "Requires fantasy_receiving and fantasy_passing parquet with "
            "week plus red-zone TD columns, the PFF summary trio, and "
            "rosters_weekly cache for the tested season; PBP fallback remains "
            "a runtime backstop"
        ),
    )
    assert coverage["td_tendency.i5"] == SignalCoverage(
        enabled=True,
        status="full",
        covered_seasons=[2023, 2024],
        missing_seasons=[],
        note=(
            "Requires fantasy_receiving and fantasy_passing parquet with "
            "week plus inside-5 columns, the PFF summary trio, and "
            "rosters_weekly cache for the tested season; PBP fallback remains "
            "a runtime backstop"
        ),
    )


def test_td_tendency_and_i5_report_none_without_crosswalk_inputs(tmp_path):
    pff_dir = tmp_path / "pff"
    for season in (2023, 2024):
        _write_parquet(
            pff_dir / f"fantasy_receiving_{season}.parquet",
            {
                "player_id": ["p1"],
                "week": [1],
                "rz_rec_targ": [1],
                "rz_rec_tds": [1],
                "rz_rush_carries": [1],
                "rz_rush_tds": [1],
                "i5_rush_carries": [1],
                "i5_rush_tds": [1],
            },
        )
        _write_parquet(
            pff_dir / f"fantasy_passing_{season}.parquet",
            {
                "player_id": ["p1"],
                "week": [1],
                "rz_rush_carries": [1],
                "rz_rush_tds": [1],
                "i5_rush_carries": [1],
                "i5_rush_tds": [1],
            },
        )

    coverage = collect_signal_coverage(
        {"td_tendency": {"enabled": True, "i5_enabled": True}},
        [2023, 2024],
        pff_dir=pff_dir,
    )

    assert coverage["td_tendency"] == SignalCoverage(
        enabled=True,
        status="none",
        covered_seasons=[],
        missing_seasons=[2023, 2024],
        note=(
            "Requires fantasy_receiving and fantasy_passing parquet with "
            "week plus red-zone TD columns, the PFF summary trio, and "
            "rosters_weekly cache for the tested season; PBP fallback remains "
            "a runtime backstop"
        ),
    )
    assert coverage["td_tendency.i5"] == SignalCoverage(
        enabled=True,
        status="none",
        covered_seasons=[],
        missing_seasons=[2023, 2024],
        note=(
            "Requires fantasy_receiving and fantasy_passing parquet with "
            "week plus inside-5 columns, the PFF summary trio, and "
            "rosters_weekly cache for the tested season; PBP fallback remains "
            "a runtime backstop"
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


def test_td_tendency_reports_partial_when_one_season_lacks_required_data(tmp_path):
    pff_dir = tmp_path / "pff"
    cache_dir = tmp_path / "cache"
    _write_parquet(
        pff_dir / "fantasy_receiving_2023.parquet",
        {
            "player_id": ["p1"],
            "week": [1],
            "rz_rec_targ": [1],
            "rz_rec_tds": [1],
            "rz_rush_carries": [1],
            "rz_rush_tds": [1],
            "i5_rush_carries": [1],
            "i5_rush_tds": [1],
        },
    )
    _write_parquet(
        pff_dir / "fantasy_passing_2023.parquet",
        {
            "player_id": ["p1"],
            "week": [1],
            "rz_rush_carries": [1],
            "rz_rush_tds": [1],
            "i5_rush_carries": [1],
            "i5_rush_tds": [1],
        },
    )
    _write_parquet(
        pff_dir / "fantasy_receiving_2024.parquet",
        {
            "player_id": ["p1"],
            "week": [1],
            "rz_rec_targ": [1],
            "rz_rec_tds": [1],
            "rz_rush_carries": [1],
            "rz_rush_tds": [1],
            "i5_rush_carries": [1],
            "i5_rush_tds": [1],
        },
    )
    _write_pff_summary_trio(pff_dir, (2023, 2024))
    _write_roster_cache(cache_dir, (2023, 2024))

    coverage = collect_signal_coverage(
        {"td_tendency": {"enabled": True}},
        [2023, 2024],
        pff_dir=pff_dir,
        cache_dir=cache_dir,
    )

    assert coverage["td_tendency"] == SignalCoverage(
        enabled=True,
        status="partial",
        covered_seasons=[2023],
        missing_seasons=[2024],
        note=(
            "Requires fantasy_receiving and fantasy_passing parquet with "
            "week plus red-zone TD columns, the PFF summary trio, and "
            "rosters_weekly cache for the tested season; PBP fallback remains "
            "a runtime backstop"
        ),
    )


def test_td_tendency_and_i5_report_none_when_summary_trio_lacks_crosswalk_columns(tmp_path):
    pff_dir = tmp_path / "pff"
    cache_dir = tmp_path / "cache"
    for season in (2024,):
        _write_parquet(
            pff_dir / f"fantasy_receiving_{season}.parquet",
            {
                "player_id": ["p1"],
                "week": [1],
                "rz_rec_targ": [1],
                "rz_rec_tds": [1],
                "rz_rush_carries": [1],
                "rz_rush_tds": [1],
                "i5_rush_carries": [1],
                "i5_rush_tds": [1],
            },
        )
        _write_parquet(
            pff_dir / f"fantasy_passing_{season}.parquet",
            {
                "player_id": ["p1"],
                "week": [1],
                "rz_rush_carries": [1],
                "rz_rush_tds": [1],
                "i5_rush_carries": [1],
                "i5_rush_tds": [1],
            },
        )
    _write_pff_summary_trio(
        pff_dir,
        (2024,),
        columns_by_facet={
            "receiving_summary": ("player_id",),
            "rushing_summary": ("player_id",),
            "passing_summary": ("player_id",),
        },
    )
    _write_roster_cache(cache_dir, (2024,))

    coverage = collect_signal_coverage(
        {"td_tendency": {"enabled": True, "i5_enabled": True}},
        [2024],
        pff_dir=pff_dir,
        cache_dir=cache_dir,
    )

    assert coverage["td_tendency"] == SignalCoverage(
        enabled=True,
        status="none",
        covered_seasons=[],
        missing_seasons=[2024],
        note=(
            "Requires fantasy_receiving and fantasy_passing parquet with "
            "week plus red-zone TD columns, the PFF summary trio, and "
            "rosters_weekly cache for the tested season; PBP fallback remains "
            "a runtime backstop"
        ),
    )
    assert coverage["td_tendency.i5"] == SignalCoverage(
        enabled=True,
        status="none",
        covered_seasons=[],
        missing_seasons=[2024],
        note=(
            "Requires fantasy_receiving and fantasy_passing parquet with "
            "week plus inside-5 columns, the PFF summary trio, and "
            "rosters_weekly cache for the tested season; PBP fallback remains "
            "a runtime backstop"
        ),
    )


def test_td_tendency_reports_partial_when_files_exist_but_red_zone_columns_do_not(tmp_path):
    pff_dir = tmp_path / "pff"
    cache_dir = tmp_path / "cache"
    _write_parquet(
        pff_dir / "fantasy_receiving_2023.parquet",
        {
            "player_id": ["p1"],
            "week": [1],
            "rz_rec_targ": [1],
            "rz_rec_tds": [1],
            "rz_rush_carries": [1],
            "rz_rush_tds": [1],
            "i5_rush_carries": [1],
            "i5_rush_tds": [1],
        },
    )
    _write_parquet(
        pff_dir / "fantasy_passing_2023.parquet",
        {
            "player_id": ["p1"],
            "week": [1],
            "rz_rush_carries": [1],
            "rz_rush_tds": [1],
            "i5_rush_carries": [1],
            "i5_rush_tds": [1],
        },
    )
    _write_parquet(
        pff_dir / "fantasy_receiving_2024.parquet",
        {
            "player_id": ["p1"],
            "week": [1],
            "i5_rush_carries": [1],
            "i5_rush_tds": [1],
        },
    )
    _write_parquet(
        pff_dir / "fantasy_passing_2024.parquet",
        {
            "player_id": ["p1"],
            "week": [1],
            "i5_rush_carries": [1],
            "i5_rush_tds": [1],
        },
    )
    _write_pff_summary_trio(pff_dir, (2023, 2024))
    _write_roster_cache(cache_dir, (2023, 2024))

    coverage = collect_signal_coverage(
        {"td_tendency": {"enabled": True, "i5_enabled": True}},
        [2023, 2024],
        pff_dir=pff_dir,
        cache_dir=cache_dir,
    )

    assert coverage["td_tendency"] == SignalCoverage(
        enabled=True,
        status="partial",
        covered_seasons=[2023],
        missing_seasons=[2024],
        note=(
            "Requires fantasy_receiving and fantasy_passing parquet with "
            "week plus red-zone TD columns, the PFF summary trio, and "
            "rosters_weekly cache for the tested season; PBP fallback remains "
            "a runtime backstop"
        ),
    )
    assert coverage["td_tendency.i5"] == SignalCoverage(
        enabled=True,
        status="full",
        covered_seasons=[2023, 2024],
        missing_seasons=[],
        note=(
            "Requires fantasy_receiving and fantasy_passing parquet with "
            "week plus inside-5 columns, the PFF summary trio, and "
            "rosters_weekly cache for the tested season; PBP fallback remains "
            "a runtime backstop"
        ),
    )


def test_td_tendency_i5_requires_week_columns_as_well(tmp_path):
    pff_dir = tmp_path / "pff"
    cache_dir = tmp_path / "cache"
    _write_parquet(
        pff_dir / "fantasy_receiving_2023.parquet",
        {
            "player_id": ["p1"],
            "week": [1],
            "rz_rec_targ": [1],
            "rz_rec_tds": [1],
            "rz_rush_carries": [1],
            "rz_rush_tds": [1],
            "i5_rush_carries": [1],
            "i5_rush_tds": [1],
        },
    )
    _write_parquet(
        pff_dir / "fantasy_passing_2023.parquet",
        {
            "player_id": ["p1"],
            "week": [1],
            "rz_rush_carries": [1],
            "rz_rush_tds": [1],
            "i5_rush_carries": [1],
            "i5_rush_tds": [1],
        },
    )
    _write_parquet(
        pff_dir / "fantasy_receiving_2024.parquet",
        {
            "player_id": ["p1"],
            "rz_rec_targ": [1],
            "rz_rec_tds": [1],
            "rz_rush_carries": [1],
            "rz_rush_tds": [1],
            "i5_rush_carries": [1],
            "i5_rush_tds": [1],
        },
    )
    _write_parquet(
        pff_dir / "fantasy_passing_2024.parquet",
        {
            "player_id": ["p1"],
            "rz_rush_carries": [1],
            "rz_rush_tds": [1],
            "i5_rush_carries": [1],
            "i5_rush_tds": [1],
        },
    )
    _write_pff_summary_trio(pff_dir, (2023, 2024))
    _write_roster_cache(cache_dir, (2023, 2024))

    coverage = collect_signal_coverage(
        {"td_tendency": {"enabled": True, "i5_enabled": True}},
        [2023, 2024],
        pff_dir=pff_dir,
        cache_dir=cache_dir,
    )

    assert coverage["td_tendency"] == SignalCoverage(
        enabled=True,
        status="partial",
        covered_seasons=[2023],
        missing_seasons=[2024],
        note=(
            "Requires fantasy_receiving and fantasy_passing parquet with "
            "week plus red-zone TD columns, the PFF summary trio, and "
            "rosters_weekly cache for the tested season; PBP fallback remains "
            "a runtime backstop"
        ),
    )
    assert coverage["td_tendency.i5"] == SignalCoverage(
        enabled=True,
        status="partial",
        covered_seasons=[2023],
        missing_seasons=[2024],
        note=(
            "Requires fantasy_receiving and fantasy_passing parquet with "
            "week plus inside-5 columns, the PFF summary trio, and "
            "rosters_weekly cache for the tested season; PBP fallback remains "
            "a runtime backstop"
        ),
    )


def test_td_tendency_i5_reports_partial_when_columns_are_missing_for_one_season(tmp_path):
    pff_dir = tmp_path / "pff"
    cache_dir = tmp_path / "cache"
    for season in (2023,):
        _write_parquet(
            pff_dir / f"fantasy_receiving_{season}.parquet",
            {
                "player_id": ["p1"],
                "week": [1],
                "rz_rec_targ": [1],
                "rz_rec_tds": [1],
                "rz_rush_carries": [1],
                "rz_rush_tds": [1],
                "i5_rush_carries": [1],
                "i5_rush_tds": [1],
            },
        )
        _write_parquet(
            pff_dir / f"fantasy_passing_{season}.parquet",
            {
                "player_id": ["p1"],
                "week": [1],
                "rz_rush_carries": [1],
                "rz_rush_tds": [1],
                "i5_rush_carries": [1],
                "i5_rush_tds": [1],
            },
        )
    _write_parquet(
        pff_dir / "fantasy_receiving_2024.parquet",
        {
            "player_id": ["p1"],
            "week": [1],
            "rz_rec_targ": [1],
            "rz_rec_tds": [1],
            "rz_rush_carries": [1],
            "rz_rush_tds": [1],
        },
    )
    _write_parquet(
        pff_dir / "fantasy_passing_2024.parquet",
        {
            "player_id": ["p1"],
            "week": [1],
            "rz_rush_carries": [1],
            "rz_rush_tds": [1],
        },
    )
    _write_pff_summary_trio(pff_dir, (2023, 2024))
    _write_roster_cache(cache_dir, (2023, 2024))

    coverage = collect_signal_coverage(
        {"td_tendency": {"enabled": True, "i5_enabled": True}},
        [2023, 2024],
        pff_dir=pff_dir,
        cache_dir=cache_dir,
    )

    assert coverage["td_tendency"] == SignalCoverage(
        enabled=True,
        status="full",
        covered_seasons=[2023, 2024],
        missing_seasons=[],
        note=(
            "Requires fantasy_receiving and fantasy_passing parquet with "
            "week plus red-zone TD columns, the PFF summary trio, and "
            "rosters_weekly cache for the tested season; PBP fallback remains "
            "a runtime backstop"
        ),
    )
    assert coverage["td_tendency.i5"] == SignalCoverage(
        enabled=True,
        status="partial",
        covered_seasons=[2023],
        missing_seasons=[2024],
        note=(
            "Requires fantasy_receiving and fantasy_passing parquet with "
            "week plus inside-5 columns, the PFF summary trio, and "
            "rosters_weekly cache for the tested season; PBP fallback remains "
            "a runtime backstop"
        ),
    )


def test_phase6_signals_report_disabled_explicitly():
    coverage = collect_signal_coverage(
        {
            "pff": {"enabled": False, "team_context": {"enabled": True}},
            "goal_line_concentration": {"enabled": False},
            "td_tendency": {"enabled": False, "i5_enabled": False},
        },
        [2024],
    )

    assert coverage["pff.team_context"].status == "disabled"
    assert coverage["goal_line_concentration"].status == "disabled"
    assert coverage["td_tendency"].status == "disabled"
    assert coverage["td_tendency.i5"].status == "disabled"


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

    for facet in ("receiving_summary", "rushing_summary", "passing_summary"):
        _write_parquet_placeholder(pff_dir / f"{facet}_2024.parquet")
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


def test_default_route_rate_root_matches_nfl_pff_root(monkeypatch, tmp_path):
    pff_root = tmp_path / "pff_processed_nfl"
    cache_dir = tmp_path / "cache"

    monkeypatch.setattr(coverage_module, "DEFAULT_PFF_DIR", pff_root)

    _write_default_pff_stack(pff_root, (2023, 2024))
    _write_route_rate_crosswalk_inputs(pff_root, cache_dir, (2023, 2024))

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
        status="full",
        covered_seasons=[2023, 2024],
        missing_seasons=[],
        note=(
            "Requires the PFF summary trio from the NFL processed PFF root "
            "plus rosters_weekly cache to build the crosswalk; "
            "receiving_summary must also include player_id, targets, routes, "
            "and week for the strict temporal leak guard"
        ),
    )


def test_typed_config_paths_override_module_defaults(tmp_path, monkeypatch):
    pff_root = tmp_path / "custom" / "processed" / "nfl"
    props_root = tmp_path / "custom" / "props"
    cache_dir = tmp_path / "cache"

    monkeypatch.setattr(coverage_module, "DEFAULT_PFF_DIR", tmp_path / "wrong" / "nfl")
    monkeypatch.setattr(coverage_module, "DEFAULT_PROPS_DIR", tmp_path / "wrong" / "props")

    engine_configs = _default_engine_configs()
    engine_configs["usage_config"] = UsageConfig()
    engine_configs["pff_config"].data_dir = str(pff_root)
    engine_configs["props_config"].cache_dir = str(props_root)

    _write_default_pff_stack(pff_root, (2023, 2024))
    _write_route_rate_crosswalk_inputs(pff_root, cache_dir, (2023, 2024))
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
            "Requires the PFF summary trio from the NFL processed PFF root "
            "plus rosters_weekly cache to build the crosswalk; "
            "receiving_summary must also include player_id, targets, routes, "
            "and week for the strict temporal leak guard"
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
    assert coverage["target_selection"].status == "disabled"


def test_target_selection_reports_artifact_coverage(tmp_path):
    _write_target_selection_artifact(tmp_path / "target_selection_2024.json")

    coverage = collect_signal_coverage(
        {
            "target_selection": {
                "enabled": True,
                "artifacts_dir": str(tmp_path),
            }
        },
        [2023, 2024],
    )

    assert coverage["target_selection"] == SignalCoverage(
        enabled=True,
        status="partial",
        covered_seasons=[2024],
        missing_seasons=[2023],
        note=(
            "Requires target_selection_<season>.json artifacts fitted from "
            "prior-season PBP target labels; runtime falls back to legacy "
            "selection when an artifact is missing or invalid"
        ),
    )


def test_target_selection_ignores_invalid_artifact_coverage(tmp_path):
    _write_target_selection_artifact(
        tmp_path / "target_selection_2024.json",
        coefficients={"is_te": None},
    )

    coverage = collect_signal_coverage(
        {
            "target_selection": {
                "enabled": True,
                "artifacts_dir": str(tmp_path),
            }
        },
        [2024],
    )

    assert coverage["target_selection"] == SignalCoverage(
        enabled=True,
        status="none",
        covered_seasons=[],
        missing_seasons=[2024],
        note=(
            "Requires target_selection_<season>.json artifacts fitted from "
            "prior-season PBP target labels; runtime falls back to legacy "
            "selection when an artifact is missing or invalid"
        ),
    )


def test_play_call_model_reports_disabled_by_default():
    coverage = collect_signal_coverage(_default_engine_configs(), [2023, 2024])

    assert coverage["play_call_model"] == SignalCoverage(
        enabled=False,
        status="disabled",
        covered_seasons=[],
        missing_seasons=[],
        note=(
            "Requires play_call_model_<season>.json artifacts fitted from "
            "prior-season PBP pass/run labels"
        ),
    )


def test_qb_scramble_coverage_disabled_by_default(tmp_path):
    coverage = collect_signal_coverage(
        config={"qb_rushing": {"scramble": {"enabled": False}}},
        test_seasons=[2024],
        cache_dir=tmp_path,
    )

    assert coverage["qb_rushing.scramble"].enabled is False
    assert coverage["qb_rushing.scramble"].status == "disabled"


def test_qb_scramble_coverage_requires_valid_artifact(tmp_path):
    artifact_dir = tmp_path / "artifacts"
    _write_qb_scramble_artifact(artifact_dir / "qb_scramble_model_2024.json")

    coverage = collect_signal_coverage(
        config={
            "qb_rushing": {
                "scramble": {
                    "enabled": True,
                    "artifacts_dir": str(artifact_dir),
                }
            }
        },
        test_seasons=[2024],
        cache_dir=tmp_path,
    )

    assert coverage["qb_rushing.scramble"].enabled is True
    assert coverage["qb_rushing.scramble"].covered_seasons == [2024]
    assert coverage["qb_rushing.scramble"].missing_seasons == []


def test_qb_scramble_coverage_falls_back_to_raw_config_artifact_dir(tmp_path):
    artifact_dir = tmp_path / "artifacts"
    _write_qb_scramble_artifact(artifact_dir / "qb_scramble_model_2024.json")

    coverage = collect_signal_coverage(
        config={
            "qb_rushing_config": {},
            "qb_rushing": {
                "scramble": {
                    "enabled": True,
                    "artifacts_dir": str(artifact_dir),
                }
            },
        },
        test_seasons=[2024],
        cache_dir=tmp_path,
    )

    assert coverage["qb_rushing.scramble"].covered_seasons == [2024]
    assert coverage["qb_rushing.scramble"].missing_seasons == []


def test_qb_scramble_coverage_rejects_duplicate_feature_names(tmp_path):
    artifact_dir = tmp_path / "artifacts"
    _write_qb_scramble_artifact(
        artifact_dir / "qb_scramble_model_2024.json",
        feature_names=["intercept", "intercept"],
        coefficients={"intercept": 0.0},
    )

    coverage = collect_signal_coverage(
        config={
            "qb_rushing": {
                "scramble": {
                    "enabled": True,
                    "artifacts_dir": str(artifact_dir),
                }
            }
        },
        test_seasons=[2024],
        cache_dir=tmp_path,
    )

    assert coverage["qb_rushing.scramble"].covered_seasons == []
    assert coverage["qb_rushing.scramble"].missing_seasons == [2024]


def test_qb_scramble_coverage_rejects_artifact_below_min_examples(tmp_path):
    artifact_dir = tmp_path / "artifacts"
    _write_qb_scramble_artifact(
        artifact_dir / "qb_scramble_model_2024.json",
        diagnostics={"num_examples": 499, "scramble_rate": 0.06},
    )

    coverage = collect_signal_coverage(
        config={
            "qb_rushing": {
                "scramble": {
                    "enabled": True,
                    "artifacts_dir": str(artifact_dir),
                    "min_examples": 500,
                }
            }
        },
        test_seasons=[2024],
        cache_dir=tmp_path,
    )

    assert coverage["qb_rushing.scramble"].covered_seasons == []
    assert coverage["qb_rushing.scramble"].missing_seasons == [2024]


def test_qb_designed_run_coverage_disabled_by_default(tmp_path):
    coverage = collect_signal_coverage(
        config={"qb_rushing": {"designed_runs": {"enabled": False}}},
        test_seasons=[2024],
        cache_dir=tmp_path,
    )

    assert coverage["qb_rushing.designed_runs"].enabled is False
    assert coverage["qb_rushing.designed_runs"].status == "disabled"


def test_qb_designed_run_coverage_uses_runtime_default_artifact_path():
    assert (
        coverage_module._resolve_qb_designed_run_artifacts_path({})
        == DEFAULT_QB_DESIGNED_RUN_ARTIFACT_DIR
    )


def test_qb_designed_run_coverage_requires_valid_artifact(tmp_path):
    artifact_dir = tmp_path / "artifacts"
    _write_qb_designed_run_artifact(artifact_dir / "qb_designed_run_model_2024.json")

    coverage = collect_signal_coverage(
        config={
            "qb_rushing": {
                "designed_runs": {
                    "enabled": True,
                    "artifacts_dir": str(artifact_dir),
                }
            }
        },
        test_seasons=[2024],
        cache_dir=tmp_path,
    )

    assert coverage["qb_rushing.designed_runs"].enabled is True
    assert coverage["qb_rushing.designed_runs"].covered_seasons == [2024]
    assert coverage["qb_rushing.designed_runs"].missing_seasons == []


def test_qb_designed_run_coverage_rejects_missing_tail_buckets(tmp_path):
    artifact_dir = tmp_path / "artifacts"
    _write_qb_designed_run_artifact(
        artifact_dir / "qb_designed_run_model_2024.json",
        tail_buckets={},
    )

    coverage = collect_signal_coverage(
        config={
            "qb_rushing": {
                "designed_runs": {
                    "enabled": True,
                    "artifacts_dir": str(artifact_dir),
                }
            }
        },
        test_seasons=[2024],
        cache_dir=tmp_path,
    )

    assert coverage["qb_rushing.designed_runs"].covered_seasons == []
    assert coverage["qb_rushing.designed_runs"].missing_seasons == [2024]


def test_qb_designed_run_coverage_rejects_non_string_feature_names(tmp_path):
    artifact_dir = tmp_path / "artifacts"
    _write_qb_designed_run_artifact(
        artifact_dir / "qb_designed_run_model_2024.json",
        feature_names=["intercept", []],
        coefficients={"intercept": 0.0},
    )

    coverage = collect_signal_coverage(
        config={
            "qb_rushing": {
                "designed_runs": {
                    "enabled": True,
                    "artifacts_dir": str(artifact_dir),
                }
            }
        },
        test_seasons=[2024],
        cache_dir=tmp_path,
    )

    assert coverage["qb_rushing.designed_runs"].covered_seasons == []
    assert coverage["qb_rushing.designed_runs"].missing_seasons == [2024]


def test_qb_designed_run_coverage_rejects_malformed_tail_bucket_values(tmp_path):
    artifact_dir = tmp_path / "artifacts"
    _write_qb_designed_run_artifact(
        artifact_dir / "qb_designed_run_model_2024.json",
        tail_buckets={"global": [5, "not-a-yard"]},
    )

    coverage = collect_signal_coverage(
        config={
            "qb_rushing": {
                "designed_runs": {
                    "enabled": True,
                    "artifacts_dir": str(artifact_dir),
                }
            }
        },
        test_seasons=[2024],
        cache_dir=tmp_path,
    )

    assert coverage["qb_rushing.designed_runs"].covered_seasons == []
    assert coverage["qb_rushing.designed_runs"].missing_seasons == [2024]


def test_play_call_model_reports_partial_artifact_coverage(tmp_path):
    _write_play_call_model_artifact(tmp_path / "play_call_model_2024.json")

    coverage = collect_signal_coverage(
        {
            "play_call_model": {
                "enabled": True,
                "artifacts_dir": str(tmp_path),
            }
        },
        [2023, 2024],
    )

    assert coverage["play_call_model"] == SignalCoverage(
        enabled=True,
        status="partial",
        covered_seasons=[2024],
        missing_seasons=[2023],
        note=(
            "Requires play_call_model_<season>.json artifacts fitted from "
            "prior-season PBP pass/run labels"
        ),
    )


def test_play_call_model_ignores_runtime_rejected_artifacts(tmp_path):
    invalid_artifacts = {
        "target_season_mismatch": {"target_season": 2023},
        "missing_coefficient": {
            "feature_names": ["intercept", "down_1"],
            "coefficients": {"intercept": 0.0},
        },
        "extra_coefficient": {
            "feature_names": ["intercept"],
            "coefficients": {"intercept": 0.0, "down_1": 0.0},
        },
        "unsupported_feature": {
            "feature_names": ["intercept", "not_a_play_call_feature"],
            "coefficients": {"intercept": 0.0, "not_a_play_call_feature": 0.0},
        },
        "malformed_feature_name": {
            "feature_names": ["intercept", 1],
            "coefficients": {"intercept": 0.0, "1": 0.0},
        },
        "non_finite_coefficient": {
            "feature_names": ["intercept"],
            "coefficients": {"intercept": float("inf")},
        },
        "missing_source_seasons": {"source_seasons": []},
        "leaky_source_season": {"source_seasons": [2024]},
        "non_finite_source_season": {"source_seasons": [float("inf")]},
        "malformed_source_season": {"source_seasons": ["2023"]},
    }

    for name, overrides in invalid_artifacts.items():
        artifacts_dir = tmp_path / name
        _write_custom_play_call_model_artifact(
            artifacts_dir / "play_call_model_2024.json",
            **overrides,
        )

        coverage = collect_signal_coverage(
            {
                "play_call_model": {
                    "enabled": True,
                    "artifacts_dir": str(artifacts_dir),
                }
            },
            [2024],
        )

        assert coverage["play_call_model"] == SignalCoverage(
            enabled=True,
            status="none",
            covered_seasons=[],
            missing_seasons=[2024],
            note=(
                "Requires play_call_model_<season>.json artifacts fitted from "
                "prior-season PBP pass/run labels"
            ),
        ), name

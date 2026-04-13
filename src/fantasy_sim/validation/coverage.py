"""Validation-only signal coverage helpers."""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

import polars as pl

DEFAULT_PFF_DIR = Path.home() / ".fantasy-sim" / "pff" / "processed" / "nfl"
DEFAULT_PFF_ROUTE_RATE_DIR = Path.home() / ".fantasy-sim" / "pff" / "processed"
DEFAULT_PROPS_DIR = Path.home() / ".fantasy-sim" / "pff" / "props"
DEFAULT_CACHE_DIR = Path.home() / ".fantasy-sim" / "cache"
DEFAULT_MARKET_HISTORY_DIR = (
    Path.home() / ".fantasy-sim" / "market-history" / "processed"
)


@dataclass
class SignalCoverage:
    enabled: bool
    status: str
    covered_seasons: list[int]
    missing_seasons: list[int]
    note: str | None = None


def _config_get(config: object, *keys: str, default: object = None) -> object:
    """Read a nested config value from mappings or simple objects."""
    value = config
    for key in keys:
        if value is None:
            return default
        if isinstance(value, Mapping):
            value = value.get(key)
        else:
            value = getattr(value, key, None)
    return default if value is None else value


def _config_section(config: object, key: str) -> object:
    if isinstance(config, Mapping) and key in config:
        return config[key]
    return getattr(config, key, None)


def _enabled_value(value: object) -> bool | None:
    if value is None:
        return None
    if isinstance(value, Mapping):
        if "enabled" not in value:
            return None
        return bool(value["enabled"])
    enabled = getattr(value, "enabled", None)
    if enabled is None:
        return None
    return bool(enabled)


def _signal_enabled(
    config: object,
    config_keys: tuple[str, ...],
    raw_path: tuple[str, ...],
    *,
    nested_path: tuple[str, ...] = (),
) -> bool:
    for key in config_keys:
        section = _config_section(config, key)
        if section is None:
            continue
        target = _config_get(section, *nested_path, default=None) if nested_path else section
        if nested_path and target is None:
            continue
        enabled = _enabled_value(target)
        if enabled is not None:
            return enabled

    enabled = _enabled_value(_config_get(config, *raw_path, default=None))
    return enabled if enabled is not None else False


def _coerce_path(value: str | Path | None, default: Path) -> Path:
    return Path(value) if value is not None else default


def _path_or_default(value: object, default: Path) -> Path:
    if value is None:
        return default
    if isinstance(value, Path):
        return value
    if isinstance(value, (str, os.PathLike)):
        return Path(value)
    return default


def _resolve_pff_path(config: object, pff_dir: str | Path | None) -> Path:
    if pff_dir is not None:
        return _path_or_default(pff_dir, DEFAULT_PFF_DIR)

    pff_config = _config_section(config, "pff_config")
    if pff_config is None:
        pff_config = _config_section(config, "pff")
    data_dir = _config_get(pff_config, "data_dir", default=None) if pff_config is not None else None
    if data_dir is not None:
        return _path_or_default(data_dir, DEFAULT_PFF_DIR)
    return DEFAULT_PFF_DIR


def _resolve_route_rate_pff_path(config: object, pff_dir: str | Path | None) -> Path:
    if pff_dir is not None:
        return _path_or_default(pff_dir, DEFAULT_PFF_ROUTE_RATE_DIR).parent

    pff_config = _config_section(config, "pff_config")
    if pff_config is None:
        pff_config = _config_section(config, "pff")
    data_dir = _config_get(pff_config, "data_dir", default=None) if pff_config is not None else None
    if data_dir is not None:
        return _path_or_default(data_dir, DEFAULT_PFF_DIR).parent
    return DEFAULT_PFF_ROUTE_RATE_DIR


def _resolve_props_path(config: object, props_dir: str | Path | None) -> Path:
    if props_dir is not None:
        return _path_or_default(props_dir, DEFAULT_PROPS_DIR)

    props_config = _config_section(config, "props_config")
    if props_config is not None:
        cache_dir = _config_get(props_config, "cache_dir", default=None)
        if cache_dir is not None:
            return _path_or_default(cache_dir, DEFAULT_PROPS_DIR)

    vegas_props = _config_get(config, "vegas", "props", default=None)
    if vegas_props is not None:
        cache_dir = _config_get(vegas_props, "cache_dir", default=None)
        if cache_dir is not None:
            return _path_or_default(cache_dir, DEFAULT_PROPS_DIR)

    return DEFAULT_PROPS_DIR


def _resolve_market_history_path(
    config: object,
    market_history_dir: str | Path | None,
) -> Path:
    if market_history_dir is not None:
        return _path_or_default(market_history_dir, DEFAULT_MARKET_HISTORY_DIR)

    market_history_config = _config_section(config, "market_history_config")
    if market_history_config is None:
        market_history_config = _config_section(config, "market_history")
    data_dir = (
        _config_get(market_history_config, "data_dir", default=None)
        if market_history_config is not None
        else None
    )
    if data_dir is not None:
        return _path_or_default(data_dir, DEFAULT_MARKET_HISTORY_DIR)
    return DEFAULT_MARKET_HISTORY_DIR


def _resolve_market_history_snapshot_label(config: object) -> str:
    market_history_config = _config_section(config, "market_history_config")
    if market_history_config is None:
        market_history_config = _config_section(config, "market_history")
    snapshot_label = (
        _config_get(market_history_config, "snapshot_label", default=None)
        if market_history_config is not None
        else None
    )
    if snapshot_label is None:
        snapshot_label = _config_get(config, "market_history", "snapshot_label", default=None)
    return str(snapshot_label) if snapshot_label is not None else "close_core8"


def _config_flag(
    config: object,
    config_keys: tuple[str, ...],
    raw_path: tuple[str, ...],
    *,
    nested_path: tuple[str, ...],
    default: bool,
) -> bool:
    for key in config_keys:
        section = _config_section(config, key)
        if section is None:
            continue
        value = _config_get(section, *nested_path, default=None)
        if value is not None:
            return bool(value)

    value = _config_get(config, *raw_path, default=None)
    if value is not None:
        return bool(value)
    return default


def _parquet_columns(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return set(pl.read_parquet_schema(path).keys())


def _parquet_unique_values(path: Path, column: str) -> set[str]:
    if not path.exists():
        return set()
    schema = pl.read_parquet_schema(path)
    if column not in schema:
        return set()
    values = pl.read_parquet(path, columns=[column]).get_column(column).drop_nulls().unique()
    return {str(value) for value in values.to_list()}


def _intersect_enabled_coverage(
    seasons: Iterable[int],
    signals: Iterable[SignalCoverage],
) -> list[int]:
    season_list = list(seasons)
    enabled_signals = [signal for signal in signals if signal.enabled]
    if not enabled_signals:
        return []

    covered = set(season_list)
    for signal in enabled_signals:
        covered &= set(signal.covered_seasons)
    return [season for season in season_list if season in covered]


def _covered_seasons_from_any_paths(
    test_seasons: Iterable[int],
    paths_by_season: Mapping[int, Iterable[Path] | Path],
) -> list[int]:
    covered: list[int] = []
    for season in test_seasons:
        paths = paths_by_season.get(season)
        if paths is None:
            continue
        if isinstance(paths, Path):
            if paths.exists():
                covered.append(season)
            continue
        if any(Path(path).exists() for path in paths):
            covered.append(season)
    return covered


def _covered_seasons_from_required_paths(
    test_seasons: Iterable[int],
    paths_by_season: Mapping[int, Iterable[Path]],
) -> list[int]:
    covered: list[int] = []
    for season in test_seasons:
        paths = list(paths_by_season.get(season, []))
        if paths and all(path.exists() for path in paths):
            covered.append(season)
    return covered


def _build_signal(
    enabled: bool,
    test_seasons: Iterable[int],
    covered: Iterable[int],
    note: str | None = None,
) -> SignalCoverage:
    seasons = list(test_seasons)
    covered_set = set(covered)
    covered_list = [season for season in seasons if season in covered_set]
    missing_list = [season for season in seasons if season not in covered_set]

    if not enabled:
        return SignalCoverage(
            enabled=False,
            status="disabled",
            covered_seasons=[],
            missing_seasons=[],
            note=note,
        )

    if not covered_list:
        status = "none"
    elif len(covered_list) == len(seasons):
        status = "full"
    else:
        status = "partial"

    return SignalCoverage(
        enabled=True,
        status=status,
        covered_seasons=covered_list,
        missing_seasons=missing_list,
        note=note,
    )


def collect_signal_coverage(
    config: object,
    test_seasons: Iterable[int],
    *,
    cache_dir: str | Path | None = None,
    pff_dir: str | Path | None = None,
    props_dir: str | Path | None = None,
    market_history_dir: str | Path | None = None,
) -> dict[str, SignalCoverage]:
    """Collect coverage status for validation signals.

    Path precedence is explicit kwargs first, then typed config path fields,
    then module defaults.

    Route-rate follows the runtime processed-root convention:
    `pff_dir` is treated as the NFL root for top-level PFF coverage, while
    route-rate derives its processed-root parent from that same override.
    """

    seasons = list(test_seasons)
    cache_path = _coerce_path(cache_dir, DEFAULT_CACHE_DIR)
    pff_path = _resolve_pff_path(config, pff_dir)
    route_rate_pff_path = _resolve_route_rate_pff_path(config, pff_dir)
    props_path = _resolve_props_path(config, props_dir)
    market_history_path = _resolve_market_history_path(config, market_history_dir)
    market_history_snapshot_label = _resolve_market_history_snapshot_label(config)

    props_enabled = _signal_enabled(
        config,
        ("props_config",),
        ("vegas", "props"),
    )
    pff_enabled = _signal_enabled(
        config,
        ("pff_config", "pff"),
        ("pff",),
    )
    weather_enabled = _signal_enabled(
        config,
        ("weather_config", "weather"),
        ("weather",),
    )
    usage_enabled = _signal_enabled(
        config,
        ("usage_config", "usage"),
        ("usage",),
    )
    tracking_enabled = _signal_enabled(
        config,
        ("tracking_config", "tracking"),
        ("tracking",),
    )
    tracking_receiver_enabled = _signal_enabled(
        config,
        ("tracking_config", "tracking"),
        ("tracking", "receiver_participation"),
        nested_path=("receiver_participation",),
    )
    tracking_rb_enabled = _signal_enabled(
        config,
        ("tracking_config", "tracking"),
        ("tracking", "rb_efficiency"),
        nested_path=("rb_efficiency",),
    )
    tracking_qb_enabled = _signal_enabled(
        config,
        ("tracking_config", "tracking"),
        ("tracking", "qb_context"),
        nested_path=("qb_context",),
    )
    usage_ngs_enabled = _signal_enabled(
        config,
        ("usage_config", "usage"),
        ("usage", "ngs"),
        nested_path=("ngs",),
    )
    usage_route_rate_enabled = _signal_enabled(
        config,
        ("usage_config", "usage"),
        ("usage", "route_rate"),
        nested_path=("route_rate",),
    )
    availability_enabled = _signal_enabled(
        config,
        ("availability_config", "availability"),
        ("availability",),
    )
    availability_injuries_enabled = _signal_enabled(
        config,
        ("availability_config", "availability"),
        ("availability", "injuries"),
        nested_path=("injuries",),
    )
    availability_depth_enabled = _signal_enabled(
        config,
        ("availability_config", "availability"),
        ("availability", "depth_charts"),
        nested_path=("depth_charts",),
    )
    availability_usage_enabled = _signal_enabled(
        config,
        ("availability_config", "availability"),
        ("availability", "usage_fallback"),
        nested_path=("usage_fallback",),
    )
    role_trend_enabled = _signal_enabled(
        config,
        ("role_trend_config", "role_trend"),
        ("role_trend",),
    )
    ensemble_enabled = _signal_enabled(
        config,
        ("ensemble_config", "ensemble"),
        ("ensemble",),
    )
    ff_opp_enabled = _signal_enabled(
        config,
        ("ensemble_config", "ensemble"),
        ("ensemble", "ff_opportunity"),
        nested_path=("ff_opportunity",),
    )
    market_history_enabled = _signal_enabled(
        config,
        ("market_history_config", "market_history"),
        ("market_history",),
    )
    market_history_dispersion_enabled = _config_flag(
        config,
        ("market_history_config", "market_history"),
        ("market_history", "features", "dispersion"),
        nested_path=("features", "dispersion"),
        default=True,
    )
    market_history_anytime_td_enabled = _config_flag(
        config,
        ("market_history_config", "market_history"),
        ("market_history", "features", "anytime_td"),
        nested_path=("features", "anytime_td"),
        default=True,
    )

    props_paths: dict[int, list[Path]] = {
        season: list(props_path.glob(f"props_{season}_week*.parquet"))
        for season in seasons
    }
    market_history_paths: dict[int, Path] = {
        season: market_history_path / f"player_markets_{season}_{market_history_snapshot_label}.parquet"
        for season in seasons
    }
    market_history_columns_by_season: dict[int, set[str]] = {
        season: _parquet_columns(path)
        for season, path in market_history_paths.items()
    }
    market_history_keys_by_season: dict[int, set[str]] = {
        season: _parquet_unique_values(path, "market_key")
        for season, path in market_history_paths.items()
    }
    market_history_crosswalk_coverage = _covered_seasons_from_required_paths(
        seasons,
        {
            season: [
                market_history_paths[season],
                cache_path / f"rosters_weekly_{season}.parquet",
            ]
            for season in seasons
        },
    )
    pff_required_paths_by_season: dict[int, list[Path]] = {}
    for season in seasons:
        paths: list[Path] = []
        if _signal_enabled(
            config,
            ("pff_config", "pff"),
            ("pff", "matchup"),
            nested_path=("matchup",),
        ):
            paths.extend(
                [
                    pff_path / f"defense_coverage_{season}.parquet",
                    pff_path / f"defense_pass_rush_{season}.parquet",
                    pff_path / f"defense_run_{season}.parquet",
                    pff_path / f"offense_pass_blocking_{season}.parquet",
                    pff_path / f"offense_run_blocking_{season}.parquet",
                ]
            )
        if _signal_enabled(
            config,
            ("pff_config", "pff"),
            ("pff", "talent"),
            nested_path=("talent",),
        ) or _signal_enabled(
            config,
            ("pff_config", "pff"),
            ("pff", "tier_engine"),
            nested_path=("tier_engine",),
        ):
            paths.extend(
                [
                    pff_path / f"receiving_summary_{season}.parquet",
                    pff_path / f"rushing_summary_{season}.parquet",
                    pff_path / f"passing_summary_{season}.parquet",
                ]
            )
        if _signal_enabled(
            config,
            ("pff_config", "pff"),
            ("pff", "team_context"),
            nested_path=("team_context",),
        ):
            paths.extend(
                [
                    pff_path / f"offense_run_blocking_{season}.parquet",
                    pff_path / f"passing_summary_{season}.parquet",
                ]
            )
        if _signal_enabled(
            config,
            ("pff_config", "pff"),
            ("pff", "coverage"),
            nested_path=("coverage",),
        ):
            paths.append(pff_path / f"defense_coverage_matchup_{season}.parquet")
        if _signal_enabled(
            config,
            ("pff_config", "pff"),
            ("pff", "kicker"),
            nested_path=("kicker",),
        ):
            paths.append(pff_path / f"field_goal_summary_{season}.parquet")
        if _signal_enabled(
            config,
            ("pff_config", "pff"),
            ("pff", "dst_baseline"),
            nested_path=("dst_baseline",),
        ):
            paths.append(pff_path / f"defense_summary_{season}.parquet")
        pff_required_paths_by_season[season] = paths

    usage_required_paths_by_season: dict[int, list[Path]] = {
        season: [
            cache_path / f"snap_counts_{season}.parquet",
            cache_path / f"pbp_{season}.parquet",
        ]
        for season in seasons
    }
    ngs_required_paths_by_season: dict[int, list[Path]] = {
        season: [cache_path / f"ngs_receiving_{season}.parquet"]
        for season in seasons
    }
    tracking_receiver_paths_by_season: dict[int, list[Path]] = {
        season: [
            cache_path / f"ftn_charting_{season}.parquet",
            cache_path / f"pbp_{season}.parquet",
        ]
        for season in seasons
    }
    tracking_rb_paths_by_season: dict[int, list[Path]] = {
        season: [
            cache_path / f"ftn_charting_{season}.parquet",
            cache_path / f"ngs_rushing_{season}.parquet",
            cache_path / f"pbp_{season}.parquet",
        ]
        for season in seasons
    }
    tracking_qb_paths_by_season: dict[int, list[Path]] = {
        season: [
            cache_path / f"participation_{season}.parquet",
            cache_path / f"ftn_charting_{season}.parquet",
            cache_path / f"ngs_passing_{season}.parquet",
            cache_path / f"pbp_{season}.parquet",
        ]
        for season in seasons
    }

    market_history_signals = {
        "market_history.crosswalk": _build_signal(
            market_history_enabled,
            seasons,
            market_history_crosswalk_coverage,
            note=(
                "Requires player_markets_<season>_<snapshot_label>.parquet plus "
                "rosters_weekly cache to resolve The Odds players to nflverse IDs"
            ),
        ),
        "market_history.pass_yards": _build_signal(
            market_history_enabled,
            seasons,
            [
                season
                for season in seasons
                if season in market_history_crosswalk_coverage
                and "player_pass_yds" in market_history_keys_by_season.get(season, set())
            ],
        ),
        "market_history.pass_tds": _build_signal(
            market_history_enabled,
            seasons,
            [
                season
                for season in seasons
                if season in market_history_crosswalk_coverage
                and "player_pass_tds" in market_history_keys_by_season.get(season, set())
            ],
        ),
        "market_history.rush_yards": _build_signal(
            market_history_enabled,
            seasons,
            [
                season
                for season in seasons
                if season in market_history_crosswalk_coverage
                and "player_rush_yds" in market_history_keys_by_season.get(season, set())
            ],
        ),
        "market_history.receptions": _build_signal(
            market_history_enabled,
            seasons,
            [
                season
                for season in seasons
                if season in market_history_crosswalk_coverage
                and "player_receptions" in market_history_keys_by_season.get(season, set())
            ],
        ),
        "market_history.receiving_yards": _build_signal(
            market_history_enabled,
            seasons,
            [
                season
                for season in seasons
                if season in market_history_crosswalk_coverage
                and "player_reception_yds" in market_history_keys_by_season.get(season, set())
            ],
        ),
        "market_history.anytime_td": _build_signal(
            market_history_enabled and market_history_anytime_td_enabled,
            seasons,
            [
                season
                for season in seasons
                if season in market_history_crosswalk_coverage
                and "player_anytime_td" in market_history_keys_by_season.get(season, set())
            ],
        ),
        "market_history.dispersion": _build_signal(
            market_history_enabled and market_history_dispersion_enabled,
            seasons,
            [
                season
                for season in seasons
                if season in market_history_crosswalk_coverage
                and "line_stddev" in market_history_columns_by_season.get(season, set())
            ],
        ),
    }
    market_history_signals["market_history"] = _build_signal(
        market_history_enabled,
        seasons,
        _intersect_enabled_coverage(seasons, market_history_signals.values()),
        note=(
            "Requires player_markets_<season>_<snapshot_label>.parquet plus "
            "rosters_weekly cache to build the crosswalk"
        ),
    )
    tracking_signals = {
        "tracking.receiver_participation": _build_signal(
            tracking_enabled and tracking_receiver_enabled,
            seasons,
            _covered_seasons_from_required_paths(
                seasons,
                tracking_receiver_paths_by_season,
            ),
            note="Requires FTN charting plus season PBP parquet coverage for each test season",
        ),
        "tracking.rb_efficiency": _build_signal(
            tracking_enabled and tracking_rb_enabled,
            seasons,
            _covered_seasons_from_required_paths(seasons, tracking_rb_paths_by_season),
            note="Requires FTN charting, NGS rushing, and season PBP parquet coverage for each test season",
        ),
        "tracking.qb_context": _build_signal(
            tracking_enabled and tracking_qb_enabled,
            seasons,
            _covered_seasons_from_required_paths(seasons, tracking_qb_paths_by_season),
            note="Requires participation, FTN charting, NGS passing, and season PBP parquet coverage for each test season",
        ),
    }
    tracking_signals["tracking"] = _build_signal(
        tracking_enabled,
        seasons,
        _intersect_enabled_coverage(seasons, tracking_signals.values()),
        note="Tracking family coverage is the intersection of enabled tracking slices",
    )

    return {
        **tracking_signals,
        **market_history_signals,
        "props": _build_signal(
            props_enabled,
            seasons,
            _covered_seasons_from_any_paths(seasons, props_paths),
            note="Forward-only unless season parquet files exist in ~/.fantasy-sim/pff/props",
        ),
        "pff": _build_signal(
            pff_enabled,
            seasons,
            _covered_seasons_from_required_paths(seasons, pff_required_paths_by_season),
            note=(
                "Requires the current default-on PFF stack: tier_engine, "
                "matchup, coverage, kicker, and dst_baseline inputs"
            ),
        ),
        "weather": _build_signal(
            weather_enabled,
            seasons,
            seasons,
            note="Open-Meteo historical/API-backed coverage is treated as covered for requested test seasons",
        ),
        "usage": _build_signal(
            usage_enabled,
            seasons,
            _covered_seasons_from_required_paths(seasons, usage_required_paths_by_season),
            note="Requires snap_counts and PBP parquet coverage for each test season",
        ),
        "usage.ngs": _build_signal(
            usage_ngs_enabled and usage_enabled,
            seasons,
            _covered_seasons_from_required_paths(seasons, ngs_required_paths_by_season),
            note="Requires nflreadpy NGS receiving parquet coverage for each test season",
        ),
        "usage.route_rate": _build_signal(
            usage_route_rate_enabled and usage_enabled and pff_enabled,
            seasons,
            _covered_seasons_from_required_paths(
                seasons,
                {
                    season: [
                        route_rate_pff_path / f"receiving_summary_{season}.parquet",
                        route_rate_pff_path / f"rushing_summary_{season}.parquet",
                        route_rate_pff_path / f"passing_summary_{season}.parquet",
                        cache_path / f"rosters_weekly_{season}.parquet",
                    ]
                    for season in seasons
                },
            ),
            note=(
                "Requires the PFF summary trio from the processed PFF root "
                "plus rosters_weekly cache to build the crosswalk"
            ),
        ),
        "availability": _build_signal(
            availability_enabled,
            seasons,
            _covered_seasons_from_required_paths(
                seasons,
                {
                    season: [
                        cache_path / f"rosters_weekly_{season}.parquet",
                        cache_path / f"depth_charts_{season}.parquet",
                    ]
                    for season in seasons
                },
            ),
            note=(
                "Explicit coverage requires rosters_weekly plus depth_charts cache; "
                "injuries can further refine hard decisions when present"
            ),
        ),
        "availability.injuries": _build_signal(
            availability_enabled and availability_injuries_enabled,
            seasons,
            _covered_seasons_from_required_paths(
                seasons,
                {
                    season: [cache_path / f"injuries_{season}.parquet"]
                    for season in seasons
                },
            ),
            note="Hard injury availability decisions require cached injuries parquet for the tested season",
        ),
        "availability.depth_charts": _build_signal(
            availability_enabled and availability_depth_enabled,
            seasons,
            _covered_seasons_from_required_paths(
                seasons,
                {
                    season: [cache_path / f"depth_charts_{season}.parquet"]
                    for season in seasons
                },
            ),
            note="Hard starter and promotion decisions require cached depth_charts parquet for the tested season",
        ),
        "availability.usage_fallback": _build_signal(
            availability_enabled and availability_usage_enabled,
            seasons,
            _covered_seasons_from_required_paths(
                seasons,
                {
                    season: [
                        cache_path / f"player_stats_week_{season}.parquet",
                        cache_path / f"snap_counts_{season}.parquet",
                        cache_path / f"rosters_weekly_{season}.parquet",
                    ]
                    for season in seasons
                },
            ),
            note="Soft-only fallback requires player_stats_week, snap_counts, and rosters_weekly parquet coverage",
        ),
        "role_trend": _build_signal(
            role_trend_enabled,
            seasons,
            _covered_seasons_from_required_paths(
                seasons,
                {
                    season: [cache_path / f"player_stats_week_{season}.parquet"]
                    for season in seasons
                },
            ),
            note="Role trend uses weekly player_stats coverage; snap_counts can augment but do not create hard decisions",
        ),
        "ensemble.ff_opportunity": _build_signal(
            ensemble_enabled and ff_opp_enabled,
            seasons,
            seasons,
            note=(
                "nflreadpy historical ff_opportunity coverage is treated as available "
                "for requested test seasons; runtime player-week blend coverage is not "
                "yet summarized here"
            ),
        ),
    }

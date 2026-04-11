"""Validation-only signal coverage helpers."""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PFF_DIR = Path.home() / ".fantasy-sim" / "pff" / "processed" / "nfl"
DEFAULT_PFF_ROUTE_RATE_DIR = Path.home() / ".fantasy-sim" / "pff" / "processed"
DEFAULT_PROPS_DIR = Path.home() / ".fantasy-sim" / "pff" / "props"
DEFAULT_CACHE_DIR = Path.home() / ".fantasy-sim" / "cache"


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

    props_paths: dict[int, list[Path]] = {
        season: list(props_path.glob(f"props_{season}_week*.parquet"))
        for season in seasons
    }
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

    return {
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
            usage_route_rate_enabled and usage_enabled,
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
    }

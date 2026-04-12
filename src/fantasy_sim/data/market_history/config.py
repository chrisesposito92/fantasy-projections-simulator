from __future__ import annotations

from fantasy_sim.data.market_history.models import (
    MarketHistoryConfig,
    MarketHistoryFeatureFlags,
)


def load_market_history_config(defaults: dict) -> MarketHistoryConfig:
    raw = defaults.get("market_history")
    if not raw:
        return MarketHistoryConfig(enabled=False)

    feature_raw = raw.get("features", {})

    return MarketHistoryConfig(
        enabled=raw.get("enabled", False),
        data_dir=raw.get("data_dir"),
        positions=tuple(raw.get("positions", ["QB", "RB", "WR", "TE"])),
        weights=dict(
            raw.get(
                "weights",
                {"QB": 0.20, "RB": 0.15, "WR": 0.20, "TE": 0.15},
            )
        ),
        min_coverage_weeks=int(raw.get("min_coverage_weeks", 1)),
        min_books=int(raw.get("min_books", 2)),
        dispersion_scale=float(raw.get("dispersion_scale", 3.0)),
        features=MarketHistoryFeatureFlags(
            close_fpts=feature_raw.get("close_fpts", True),
            open_fpts=feature_raw.get("open_fpts", True),
            movement=feature_raw.get("movement", True),
            dispersion=feature_raw.get("dispersion", True),
            anytime_td=feature_raw.get("anytime_td", True),
        ),
    )

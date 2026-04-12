from __future__ import annotations

from fantasy_sim.data.market_history.models import (
    MarketHistoryConfig,
    MarketHistoryFeatureFlags,
)

DEFAULT_MARKET_HISTORY_CONFIG = MarketHistoryConfig()
DEFAULT_MARKET_HISTORY_FEATURE_FLAGS = MarketHistoryFeatureFlags()


def _build_default_market_history_config() -> MarketHistoryConfig:
    return MarketHistoryConfig(
        enabled=DEFAULT_MARKET_HISTORY_CONFIG.enabled,
        data_dir=DEFAULT_MARKET_HISTORY_CONFIG.data_dir,
        positions=tuple(DEFAULT_MARKET_HISTORY_CONFIG.positions),
        weights=dict(DEFAULT_MARKET_HISTORY_CONFIG.weights),
        min_coverage_weeks=DEFAULT_MARKET_HISTORY_CONFIG.min_coverage_weeks,
        min_books=DEFAULT_MARKET_HISTORY_CONFIG.min_books,
        dispersion_scale=DEFAULT_MARKET_HISTORY_CONFIG.dispersion_scale,
        features=MarketHistoryFeatureFlags(
            close_fpts=DEFAULT_MARKET_HISTORY_FEATURE_FLAGS.close_fpts,
            open_fpts=DEFAULT_MARKET_HISTORY_FEATURE_FLAGS.open_fpts,
            movement=DEFAULT_MARKET_HISTORY_FEATURE_FLAGS.movement,
            dispersion=DEFAULT_MARKET_HISTORY_FEATURE_FLAGS.dispersion,
            anytime_td=DEFAULT_MARKET_HISTORY_FEATURE_FLAGS.anytime_td,
        ),
    )


def load_market_history_config(defaults: dict) -> MarketHistoryConfig:
    raw = defaults.get("market_history")
    if not raw:
        return _build_default_market_history_config()

    feature_raw = raw.get("features", {})

    return MarketHistoryConfig(
        enabled=raw.get("enabled", DEFAULT_MARKET_HISTORY_CONFIG.enabled),
        data_dir=raw.get("data_dir"),
        positions=tuple(raw.get("positions", DEFAULT_MARKET_HISTORY_CONFIG.positions)),
        weights=dict(
            raw.get(
                "weights",
                DEFAULT_MARKET_HISTORY_CONFIG.weights,
            )
        ),
        min_coverage_weeks=int(
            raw.get("min_coverage_weeks", DEFAULT_MARKET_HISTORY_CONFIG.min_coverage_weeks)
        ),
        min_books=int(raw.get("min_books", DEFAULT_MARKET_HISTORY_CONFIG.min_books)),
        dispersion_scale=float(
            raw.get("dispersion_scale", DEFAULT_MARKET_HISTORY_CONFIG.dispersion_scale)
        ),
        features=MarketHistoryFeatureFlags(
            close_fpts=feature_raw.get(
                "close_fpts",
                DEFAULT_MARKET_HISTORY_FEATURE_FLAGS.close_fpts,
            ),
            open_fpts=feature_raw.get(
                "open_fpts",
                DEFAULT_MARKET_HISTORY_FEATURE_FLAGS.open_fpts,
            ),
            movement=feature_raw.get(
                "movement",
                DEFAULT_MARKET_HISTORY_FEATURE_FLAGS.movement,
            ),
            dispersion=feature_raw.get(
                "dispersion",
                DEFAULT_MARKET_HISTORY_FEATURE_FLAGS.dispersion,
            ),
            anytime_td=feature_raw.get(
                "anytime_td",
                DEFAULT_MARKET_HISTORY_FEATURE_FLAGS.anytime_td,
            ),
        ),
    )

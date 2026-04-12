from __future__ import annotations

from fantasy_sim.data.role_trend.models import PositionTrendConfig, RoleTrendConfig


def load_role_trend_config(defaults: dict) -> RoleTrendConfig:
    raw = defaults.get("role_trend")
    if not raw:
        return RoleTrendConfig(enabled=False)

    return RoleTrendConfig(
        enabled=raw.get("enabled", False),
        positions=tuple(raw.get("positions", ["QB", "RB", "WR", "TE"])),
        window_weeks=raw.get("window_weeks", 3),
        factor_clamp=tuple(raw.get("factor_clamp", [0.90, 1.10])),
        qb=PositionTrendConfig(sensitivity=raw.get("qb", {}).get("sensitivity", 0.12)),
        rb=PositionTrendConfig(sensitivity=raw.get("rb", {}).get("sensitivity", 0.10)),
        wr=PositionTrendConfig(sensitivity=raw.get("wr", {}).get("sensitivity", 0.10)),
        te=PositionTrendConfig(sensitivity=raw.get("te", {}).get("sensitivity", 0.08)),
    )

from __future__ import annotations

from fantasy_sim.data.availability.models import (
    AvailabilityConfig,
    DepthChartSignalConfig,
    InjurySignalConfig,
    UsageFallbackConfig,
)


def load_availability_config(defaults: dict) -> AvailabilityConfig:
    raw = defaults.get("availability")
    if not raw:
        return AvailabilityConfig(enabled=False)

    injury_raw = raw.get("injuries", {})
    depth_raw = raw.get("depth_charts", {})
    usage_raw = raw.get("usage_fallback", {})

    return AvailabilityConfig(
        enabled=raw.get("enabled", False),
        positions=tuple(raw.get("positions", ["QB", "RB", "WR", "TE"])),
        injuries=InjurySignalConfig(
            enabled=injury_raw.get("enabled", True),
            hard_out_statuses=tuple(
                injury_raw.get(
                    "hard_out_statuses",
                    ["Out", "Doubtful", "Suspended", "Injured Reserve"],
                )
            ),
            limited_statuses=tuple(injury_raw.get("limited_statuses", ["Questionable"])),
            limited_factor=injury_raw.get("limited_factor", 0.75),
        ),
        depth_charts=DepthChartSignalConfig(
            enabled=depth_raw.get("enabled", True),
            starter_slots=dict(
                depth_raw.get(
                    "starter_slots",
                    {"QB": "QB1", "RB": "RB1", "WR": "WR1", "TE": "TE1"},
                )
            ),
        ),
        usage_fallback=UsageFallbackConfig(
            enabled=usage_raw.get("enabled", True),
            lookback_weeks=usage_raw.get("lookback_weeks", 3),
            min_factor=usage_raw.get("min_factor", 0.85),
            qb_low_usage_factor=usage_raw.get("qb_low_usage_factor", 0.92),
            rb_low_usage_factor=usage_raw.get("rb_low_usage_factor", 0.90),
            wr_low_usage_factor=usage_raw.get("wr_low_usage_factor", 0.92),
            te_low_usage_factor=usage_raw.get("te_low_usage_factor", 0.92),
        ),
    )

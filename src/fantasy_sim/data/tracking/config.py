from __future__ import annotations

from fantasy_sim.data.tracking.models import (
    QbContextConfig,
    ReceiverParticipationConfig,
    RbEfficiencyConfig,
    TrackingConfig,
)


def load_tracking_config(defaults: dict) -> TrackingConfig:
    tracking = defaults.get("tracking")
    if not tracking:
        return TrackingConfig()

    receiver_participation = tracking.get("receiver_participation", {})
    rb_efficiency = tracking.get("rb_efficiency", {})
    qb_context = tracking.get("qb_context", {})

    return TrackingConfig(
        enabled=tracking.get("enabled", False),
        window_weeks=tracking.get("window_weeks", 4),
        receiver_participation=ReceiverParticipationConfig(
            enabled=receiver_participation.get("enabled", True),
            positions=tuple(receiver_participation.get("positions", ("WR", "TE"))),
            target_share_sensitivity=receiver_participation.get(
                "target_share_sensitivity",
                0.18,
            ),
            air_yards_sensitivity=receiver_participation.get(
                "air_yards_sensitivity",
                0.12,
            ),
            catchable_target_sensitivity=receiver_participation.get(
                "catchable_target_sensitivity",
                0.08,
            ),
            contested_target_sensitivity=receiver_participation.get(
                "contested_target_sensitivity",
                -0.04,
            ),
            factor_clamp=tuple(receiver_participation.get("factor_clamp", [0.92, 1.08])),
            min_targets=receiver_participation.get("min_targets", 8),
        ),
        rb_efficiency=RbEfficiencyConfig(
            enabled=rb_efficiency.get("enabled", True),
            carry_share_sensitivity=rb_efficiency.get("carry_share_sensitivity", 0.10),
            rush_yards_sensitivity=rb_efficiency.get("rush_yards_sensitivity", 0.08),
            factor_clamp=tuple(rb_efficiency.get("factor_clamp", [0.93, 1.07])),
            min_attempts=rb_efficiency.get("min_attempts", 12),
        ),
        qb_context=QbContextConfig(
            enabled=qb_context.get("enabled", True),
            pass_rate_sensitivity=qb_context.get("pass_rate_sensitivity", 0.04),
            pace_sensitivity=qb_context.get("pace_sensitivity", 0.03),
            scramble_sensitivity=qb_context.get("scramble_sensitivity", 0.06),
            sack_rate_sensitivity=qb_context.get("sack_rate_sensitivity", 0.05),
            factor_clamp=tuple(qb_context.get("factor_clamp", [0.94, 1.06])),
            min_dropbacks=qb_context.get("min_dropbacks", 20),
        ),
    )

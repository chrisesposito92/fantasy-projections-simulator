from __future__ import annotations

from fantasy_sim.data.tracking.models import (
    QbContextConfig,
    ReceiverParticipationConfig,
    RbEfficiencyConfig,
    TrackingConfig,
)

DEFAULT_TRACKING_CONFIG = TrackingConfig()


def _build_default_tracking_config() -> TrackingConfig:
    return TrackingConfig(
        enabled=DEFAULT_TRACKING_CONFIG.enabled,
        window_weeks=DEFAULT_TRACKING_CONFIG.window_weeks,
        receiver_participation=ReceiverParticipationConfig(
            enabled=DEFAULT_TRACKING_CONFIG.receiver_participation.enabled,
            positions=tuple(DEFAULT_TRACKING_CONFIG.receiver_participation.positions),
            target_share_sensitivity=(
                DEFAULT_TRACKING_CONFIG.receiver_participation.target_share_sensitivity
            ),
            air_yards_sensitivity=(
                DEFAULT_TRACKING_CONFIG.receiver_participation.air_yards_sensitivity
            ),
            catchable_target_sensitivity=(
                DEFAULT_TRACKING_CONFIG.receiver_participation.catchable_target_sensitivity
            ),
            contested_target_sensitivity=(
                DEFAULT_TRACKING_CONFIG.receiver_participation.contested_target_sensitivity
            ),
            factor_clamp=tuple(DEFAULT_TRACKING_CONFIG.receiver_participation.factor_clamp),
            min_targets=DEFAULT_TRACKING_CONFIG.receiver_participation.min_targets,
        ),
        rb_efficiency=RbEfficiencyConfig(
            enabled=DEFAULT_TRACKING_CONFIG.rb_efficiency.enabled,
            carry_share_sensitivity=(
                DEFAULT_TRACKING_CONFIG.rb_efficiency.carry_share_sensitivity
            ),
            rush_yards_sensitivity=(
                DEFAULT_TRACKING_CONFIG.rb_efficiency.rush_yards_sensitivity
            ),
            factor_clamp=tuple(DEFAULT_TRACKING_CONFIG.rb_efficiency.factor_clamp),
            min_attempts=DEFAULT_TRACKING_CONFIG.rb_efficiency.min_attempts,
        ),
        qb_context=QbContextConfig(
            enabled=DEFAULT_TRACKING_CONFIG.qb_context.enabled,
            pass_rate_sensitivity=DEFAULT_TRACKING_CONFIG.qb_context.pass_rate_sensitivity,
            pace_sensitivity=DEFAULT_TRACKING_CONFIG.qb_context.pace_sensitivity,
            scramble_sensitivity=DEFAULT_TRACKING_CONFIG.qb_context.scramble_sensitivity,
            sack_rate_sensitivity=DEFAULT_TRACKING_CONFIG.qb_context.sack_rate_sensitivity,
            factor_clamp=tuple(DEFAULT_TRACKING_CONFIG.qb_context.factor_clamp),
            min_dropbacks=DEFAULT_TRACKING_CONFIG.qb_context.min_dropbacks,
        ),
    )


def load_tracking_config(defaults: dict) -> TrackingConfig:
    tracking = defaults.get("tracking")
    if not tracking:
        return _build_default_tracking_config()

    receiver_participation = tracking.get("receiver_participation", {})
    rb_efficiency = tracking.get("rb_efficiency", {})
    qb_context = tracking.get("qb_context", {})

    return TrackingConfig(
        enabled=tracking.get("enabled", DEFAULT_TRACKING_CONFIG.enabled),
        window_weeks=tracking.get("window_weeks", DEFAULT_TRACKING_CONFIG.window_weeks),
        receiver_participation=ReceiverParticipationConfig(
            enabled=receiver_participation.get(
                "enabled",
                DEFAULT_TRACKING_CONFIG.receiver_participation.enabled,
            ),
            positions=tuple(
                receiver_participation.get(
                    "positions",
                    DEFAULT_TRACKING_CONFIG.receiver_participation.positions,
                )
            ),
            target_share_sensitivity=receiver_participation.get(
                "target_share_sensitivity",
                DEFAULT_TRACKING_CONFIG.receiver_participation.target_share_sensitivity,
            ),
            air_yards_sensitivity=receiver_participation.get(
                "air_yards_sensitivity",
                DEFAULT_TRACKING_CONFIG.receiver_participation.air_yards_sensitivity,
            ),
            catchable_target_sensitivity=receiver_participation.get(
                "catchable_target_sensitivity",
                DEFAULT_TRACKING_CONFIG.receiver_participation.catchable_target_sensitivity,
            ),
            contested_target_sensitivity=receiver_participation.get(
                "contested_target_sensitivity",
                DEFAULT_TRACKING_CONFIG.receiver_participation.contested_target_sensitivity,
            ),
            factor_clamp=tuple(
                receiver_participation.get(
                    "factor_clamp",
                    DEFAULT_TRACKING_CONFIG.receiver_participation.factor_clamp,
                )
            ),
            min_targets=receiver_participation.get(
                "min_targets",
                DEFAULT_TRACKING_CONFIG.receiver_participation.min_targets,
            ),
        ),
        rb_efficiency=RbEfficiencyConfig(
            enabled=rb_efficiency.get("enabled", DEFAULT_TRACKING_CONFIG.rb_efficiency.enabled),
            carry_share_sensitivity=rb_efficiency.get(
                "carry_share_sensitivity",
                DEFAULT_TRACKING_CONFIG.rb_efficiency.carry_share_sensitivity,
            ),
            rush_yards_sensitivity=rb_efficiency.get(
                "rush_yards_sensitivity",
                DEFAULT_TRACKING_CONFIG.rb_efficiency.rush_yards_sensitivity,
            ),
            factor_clamp=tuple(
                rb_efficiency.get(
                    "factor_clamp",
                    DEFAULT_TRACKING_CONFIG.rb_efficiency.factor_clamp,
                )
            ),
            min_attempts=rb_efficiency.get(
                "min_attempts",
                DEFAULT_TRACKING_CONFIG.rb_efficiency.min_attempts,
            ),
        ),
        qb_context=QbContextConfig(
            enabled=qb_context.get("enabled", DEFAULT_TRACKING_CONFIG.qb_context.enabled),
            pass_rate_sensitivity=qb_context.get(
                "pass_rate_sensitivity",
                DEFAULT_TRACKING_CONFIG.qb_context.pass_rate_sensitivity,
            ),
            pace_sensitivity=qb_context.get(
                "pace_sensitivity",
                DEFAULT_TRACKING_CONFIG.qb_context.pace_sensitivity,
            ),
            scramble_sensitivity=qb_context.get(
                "scramble_sensitivity",
                DEFAULT_TRACKING_CONFIG.qb_context.scramble_sensitivity,
            ),
            sack_rate_sensitivity=qb_context.get(
                "sack_rate_sensitivity",
                DEFAULT_TRACKING_CONFIG.qb_context.sack_rate_sensitivity,
            ),
            factor_clamp=tuple(
                qb_context.get(
                    "factor_clamp",
                    DEFAULT_TRACKING_CONFIG.qb_context.factor_clamp,
                )
            ),
            min_dropbacks=qb_context.get(
                "min_dropbacks",
                DEFAULT_TRACKING_CONFIG.qb_context.min_dropbacks,
            ),
        ),
    )

"""Configuration loader for the game-script feature."""

from __future__ import annotations

from fantasy_sim.data.game_script.models import (
    GameScriptConfig,
    LeadingLateRbConfig,
    TrailingLateConfig,
)


def load_game_script_config(defaults: dict) -> GameScriptConfig:
    """Extract GameScriptConfig from the full defaults config dict."""
    game_script = defaults.get("game_script")
    if not game_script:
        return GameScriptConfig(enabled=False)

    trailing_late = game_script.get("trailing_late", {})
    leading_late_rb = game_script.get("leading_late_rb", {})

    return GameScriptConfig(
        enabled=game_script.get("enabled", False),
        trailing_late=TrailingLateConfig(
            enabled=trailing_late.get("enabled", True),
            deficit_threshold=trailing_late.get("deficit_threshold", 8),
            final_five_minutes=trailing_late.get("final_five_minutes", 300),
            final_five_deficit_threshold=trailing_late.get("final_five_deficit_threshold", 4),
            pass_rate_prior_strength=trailing_late.get("pass_rate_prior_strength", 250.0),
            pace_prior_strength=trailing_late.get("pace_prior_strength", 250.0),
            target_prior_strength=trailing_late.get("target_prior_strength", 80.0),
            pass_rate_clamp=tuple(trailing_late.get("pass_rate_clamp", [1.00, 1.35])),
            pace_factor_clamp=tuple(trailing_late.get("pace_factor_clamp", [1.00, 1.20])),
            target_rank_factor_clamp=tuple(
                trailing_late.get("target_rank_factor_clamp", [0.85, 1.25])
            ),
        ),
        leading_late_rb=LeadingLateRbConfig(
            enabled=leading_late_rb.get("enabled", False),
            lead_threshold=leading_late_rb.get("lead_threshold", 14),
            late_minutes=leading_late_rb.get("late_minutes", 600),
            rb_carry_prior_strength=leading_late_rb.get("rb_carry_prior_strength", 100.0),
            rb_rank_factor_clamp=tuple(
                leading_late_rb.get("rb_rank_factor_clamp", [0.80, 1.20])
            ),
        ),
    )

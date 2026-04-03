"""Load PFF configuration from defaults.yaml."""

from __future__ import annotations

from fantasy_sim.data.pff.models import (
    MatchupConfig,
    PffConfig,
    TalentConfig,
)


def load_pff_config(config: dict) -> PffConfig:
    """Extract PFF config from the full defaults config dict.

    Args:
        config: The full defaults.yaml dict (or a subset with a "pff" key).

    Returns:
        PffConfig with all sub-configs populated.
    """
    pff = config.get("pff", {})
    if not pff:
        return PffConfig()

    matchup_raw = pff.get("matchup", {})
    talent_raw = pff.get("talent", {})

    clamp = matchup_raw.get("factor_clamp", [0.80, 1.20])

    matchup = MatchupConfig(
        enabled=matchup_raw.get("enabled", True),
        pass_defense_sensitivity=matchup_raw.get("pass_defense_sensitivity", 0.08),
        pass_rush_sensitivity=matchup_raw.get("pass_rush_sensitivity", 0.10),
        run_defense_sensitivity=matchup_raw.get("run_defense_sensitivity", 0.08),
        int_rate_sensitivity=matchup_raw.get("int_rate_sensitivity", 0.06),
        ol_pass_sensitivity=matchup_raw.get("ol_pass_sensitivity", 0.08),
        ol_run_sensitivity=matchup_raw.get("ol_run_sensitivity", 0.06),
        factor_clamp=tuple(clamp),
        min_games=matchup_raw.get("min_games", 4),
    )

    talent = TalentConfig(
        enabled=talent_raw.get("enabled", True),
        prior_strength=talent_raw.get("prior_strength", 40.0),
        min_divergence=talent_raw.get("min_divergence", 0.03),
        team_change_factor=talent_raw.get("team_change_factor", 1.0),
        catch_rate_coefficients=talent_raw.get("catch_rate_coefficients", {
            "drop_rate": -0.15,
            "contested_catch_rate": 0.10,
            "qb_accuracy": 0.08,
        }),
        rushing_yards_coefficients=talent_raw.get("rushing_yards_coefficients", {
            "yco_attempt": 0.6,
            "elusive_rating": 0.008,
        }),
        receiving_yards_coefficients=talent_raw.get("receiving_yards_coefficients", {
            "yprr": 0.5,
            "avg_depth_of_target": 0.03,
        }),
    )

    return PffConfig(
        enabled=pff.get("enabled", False),
        data_dir=pff.get("data_dir"),
        matchup=matchup,
        talent=talent,
    )

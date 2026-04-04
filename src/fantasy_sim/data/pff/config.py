"""Load PFF configuration from defaults.yaml."""

from __future__ import annotations

from fantasy_sim.data.pff.models import (
    MatchupConfig,
    NcaaPriorsConfig,
    PffConfig,
    PositionGradeConfig,
    ScheduleAdjustmentConfig,
    TalentConfig,
    TeamContextConfig,
    TierConfig,
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
        prior_strength=talent_raw.get("prior_strength", 30.0),
        min_divergence=talent_raw.get("min_divergence", 0.01),
        team_change_factor=talent_raw.get("team_change_factor", 0.5),
        catch_rate_coefficients=talent_raw.get("catch_rate_coefficients", {
            "drop_rate": 0.21,
            "contested_catch_rate": -0.25,
            "qb_accuracy": 0.03,
        }),
        rushing_yards_coefficients=talent_raw.get("rushing_yards_coefficients", {
            "yco_attempt": 0.02,
            "elusive_rating": 0.0005,
        }),
        receiving_yards_coefficients=talent_raw.get("receiving_yards_coefficients", {
            "yprr": 0.43,
            "avg_depth_of_target": 0.41,
        }),
        target_share_coefficients=talent_raw.get("target_share_coefficients", {
            "route_grade": 0.5,
            "yprr": 0.3,
        }),
        fumble_rate_coefficients=talent_raw.get("fumble_rate_coefficients", {
            "grades_hands_fumble": -0.002,
        }),
        scramble_rate_enabled=talent_raw.get("scramble_rate_enabled", True),
        schedule_adjustment=ScheduleAdjustmentConfig(
            **{
                k: v
                for k, v in talent_raw.get("schedule_adjustment", {}).items()
                if k in ("enabled", "weight", "catch_rate_sensitivity", "rush_yards_sensitivity")
            }
        ),
        ncaa_priors=NcaaPriorsConfig(
            **{
                k: v
                for k, v in talent_raw.get("ncaa_priors", {}).items()
                if k in ("enabled", "draft_weight", "ncaa_data_dir")
            }
        ),
    )

    tier_raw = pff.get("tier_engine", {})
    _default_position_grades = {
        "QB": PositionGradeConfig(primary="grades_pass", secondary="accuracy_percent"),
        "RB": PositionGradeConfig(primary="grades_run", secondary="elusive_rating"),
        "WR": PositionGradeConfig(primary="grades_pass_route", secondary="yprr"),
        "TE": PositionGradeConfig(primary="grades_pass_route", secondary="recv_grade"),
    }
    raw_pos_grades = tier_raw.get("position_grades", {})
    if raw_pos_grades:
        pos_grades: dict[str, PositionGradeConfig] = {}
        for pos, spec in raw_pos_grades.items():
            missing = [k for k in ("primary", "secondary") if k not in spec]
            if missing:
                raise ValueError(
                    f"Invalid tier_engine.position_grades config for {pos!r}: "
                    f"missing required keys: {', '.join(missing)}"
                )
            pos_grades[pos] = PositionGradeConfig(
                primary=spec["primary"], secondary=spec["secondary"],
            )
        position_grades = pos_grades
    else:
        position_grades = _default_position_grades

    tier_engine = TierConfig(
        enabled=tier_raw.get("enabled", False),
        cutoffs=tier_raw.get("cutoffs", [0.85, 0.65, 0.40, 0.20]),
        position_grades=position_grades,
        reliability_max_games=tier_raw.get("reliability_max_games", 32),
        reliability_team_change_penalty=tier_raw.get("reliability_team_change_penalty", 0.5),
        reliability_variance_weight=tier_raw.get("reliability_variance_weight", 0.3),
        reliability_floor=tier_raw.get("reliability_floor", 0.15),
        reliability_cap=tier_raw.get("reliability_cap", 0.85),
        blend_pool_size=tier_raw.get("blend_pool_size", 500),
    )

    tc_raw = pff.get("team_context", {})
    tc_clamp = tc_raw.get("factor_clamp", [0.90, 1.10])
    team_context = TeamContextConfig(
        enabled=tc_raw.get("enabled", True),
        pass_rate_sensitivity=tc_raw.get("pass_rate_sensitivity", 0.08),
        ol_run_sensitivity=tc_raw.get("ol_run_sensitivity", 0.06),
        qb_quality_sensitivity=tc_raw.get("qb_quality_sensitivity", 0.05),
        factor_clamp=tuple(tc_clamp),
        min_games=tc_raw.get("min_games", 4),
        ol_run_yards_scale=tc_raw.get("ol_run_yards_scale", 10.0),
    )

    return PffConfig(
        enabled=pff.get("enabled", False),
        data_dir=pff.get("data_dir"),
        matchup=matchup,
        talent=talent,
        tier_engine=tier_engine,
        team_context=team_context,
    )

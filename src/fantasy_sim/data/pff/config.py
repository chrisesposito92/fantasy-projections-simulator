"""Load PFF configuration from defaults.yaml."""

from __future__ import annotations

from fantasy_sim.data.pff.models import (
    ArchetypeConfig,
    CoverageConfig,
    DepthRoleConfig,
    DepthRoleEfficiencyConfig,
    DepthRoleEfficiencyPositionConfig,
    DepthRolePositionConfig,
    DstBaselineConfig,
    KickerConfig,
    MatchupConfig,
    NcaaPriorsConfig,
    NcaaRookieConfig,
    PffConfig,
    PositionGradeConfig,
    RbSchemeFitConfig,
    QbSplitConfig,
    ScheduleAdjustmentConfig,
    TalentConfig,
    TeamContextConfig,
    TierConfig,
)

_SUPPORTED_DEPTH_ROLE_POSITIONS = {"WR", "TE"}


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
                primary=spec["primary"],
                secondary=spec["secondary"],
                tertiary=spec.get("tertiary"),
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
        position_reliability=tier_raw.get("position_reliability", {}),
    )

    ncaa_raw = tier_raw.get("ncaa_rookie", {})
    raw_draft_conf = ncaa_raw.get("draft_confidence", {})
    # YAML may parse int keys as strings — convert to int
    draft_confidence = {int(k): float(v) for k, v in raw_draft_conf.items()} if raw_draft_conf else None

    ncaa_rookie = NcaaRookieConfig(
        enabled=ncaa_raw.get("enabled", True),
        undrafted_confidence=ncaa_raw.get("undrafted_confidence", 0.40),
        ncaa_lookback_seasons=ncaa_raw.get("ncaa_lookback_seasons", 4),
        **({"draft_confidence": draft_confidence} if draft_confidence else {}),
    )
    tier_engine.ncaa_rookie = ncaa_rookie

    arch_raw = tier_raw.get("archetypes", {})
    archetypes = ArchetypeConfig(
        enabled=arch_raw.get("enabled", True),
        n_archetypes=arch_raw.get("n_archetypes", 3),
        adot_grade_key=arch_raw.get("adot_grade_key", "avg_depth_of_target"),
        min_archetype_pool_size=arch_raw.get("min_archetype_pool_size", 20),
    )
    tier_engine.archetypes = archetypes

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

    cov_raw = pff.get("coverage", {})
    cov_clamp = cov_raw.get("factor_clamp", [0.97, 1.03])
    coverage = CoverageConfig(
        enabled=cov_raw.get("enabled", True),
        catch_rate_sensitivity=cov_raw.get("catch_rate_sensitivity", 0.04),
        ypr_sensitivity=cov_raw.get("ypr_sensitivity", 0.04),
        min_coverage_targets=cov_raw.get("min_coverage_targets", 20),
        min_z_score_targets=cov_raw.get("min_z_score_targets", 10),
        min_z_score_population=cov_raw.get("min_z_score_population", 8),
        factor_clamp=tuple(cov_clamp),
        min_games=cov_raw.get("min_games", 4),
    )

    depth_role_raw = pff.get("depth_role", {})
    depth_role_positions = tuple(depth_role_raw.get("positions", ["WR", "TE"]))
    efficiency_raw = depth_role_raw.get("efficiency", {})
    invalid_positions = [
        pos for pos in depth_role_positions if pos not in _SUPPORTED_DEPTH_ROLE_POSITIONS
    ]
    if invalid_positions:
        raise ValueError(
            "Invalid pff.depth_role.positions config: "
            f"{', '.join(invalid_positions)}. "
            "Supported positions: WR, TE"
        )
    depth_role = DepthRoleConfig(
        enabled=depth_role_raw.get("enabled", False),
        positions=depth_role_positions,
        wr=DepthRolePositionConfig(
            target_share_sensitivity=depth_role_raw.get("wr", {}).get(
                "target_share_sensitivity",
                0.10,
            ),
            air_yards_share_sensitivity=depth_role_raw.get("wr", {}).get(
                "air_yards_share_sensitivity",
                0.12,
            ),
            factor_clamp=tuple(
                depth_role_raw.get("wr", {}).get("factor_clamp", [0.94, 1.06])
            ),
        ),
        te=DepthRolePositionConfig(
            target_share_sensitivity=depth_role_raw.get("te", {}).get(
                "target_share_sensitivity",
                0.08,
            ),
            air_yards_share_sensitivity=depth_role_raw.get("te", {}).get(
                "air_yards_share_sensitivity",
                0.06,
            ),
            factor_clamp=tuple(
                depth_role_raw.get("te", {}).get("factor_clamp", [0.95, 1.05])
            ),
        ),
        min_routes=depth_role_raw.get("min_routes", 15),
        min_targets=depth_role_raw.get("min_targets", 6),
        min_games=depth_role_raw.get("min_games", 4),
        early_season_blend=depth_role_raw.get("early_season_blend", True),
        efficiency=DepthRoleEfficiencyConfig(
            enabled=efficiency_raw.get("enabled", False),
            min_routes=efficiency_raw.get("min_routes", 15),
            min_receptions=efficiency_raw.get("min_receptions", 6),
            min_games=efficiency_raw.get("min_games", 4),
            catch_rate_clamp=tuple(
                efficiency_raw.get("catch_rate_clamp", [0.94, 1.06])
            ),
            yards_scale_clamp=tuple(
                efficiency_raw.get("yards_scale_clamp", [0.92, 1.08])
            ),
            wr=DepthRoleEfficiencyPositionConfig(
                catch_rate_sensitivity=efficiency_raw.get("wr", {}).get(
                    "catch_rate_sensitivity",
                    0.08,
                ),
                yards_scale_sensitivity=efficiency_raw.get("wr", {}).get(
                    "yards_scale_sensitivity",
                    0.10,
                ),
            ),
            te=DepthRoleEfficiencyPositionConfig(
                catch_rate_sensitivity=efficiency_raw.get("te", {}).get(
                    "catch_rate_sensitivity",
                    0.06,
                ),
                yards_scale_sensitivity=efficiency_raw.get("te", {}).get(
                    "yards_scale_sensitivity",
                    0.08,
                ),
            ),
        ),
    )

    rb_scheme_fit_raw = pff.get("rb_scheme_fit", {})
    rb_scheme_fit = RbSchemeFitConfig(
        enabled=rb_scheme_fit_raw.get("enabled", False),
        rush_yards_sensitivity=rb_scheme_fit_raw.get("rush_yards_sensitivity", 0.10),
        factor_clamp=tuple(rb_scheme_fit_raw.get("factor_clamp", [0.94, 1.06])),
        min_attempts=rb_scheme_fit_raw.get("min_attempts", 20),
        min_games=rb_scheme_fit_raw.get("min_games", 4),
        early_season_blend=rb_scheme_fit_raw.get("early_season_blend", True),
        scheme_usage_weight=rb_scheme_fit_raw.get("scheme_usage_weight", 0.65),
        blocking_alignment_weight=rb_scheme_fit_raw.get("blocking_alignment_weight", 0.35),
    )

    qb_split_raw = pff.get("qb_split", {})
    qb_split = QbSplitConfig(
        enabled=qb_split_raw.get("enabled", False),
        completion_sensitivity=qb_split_raw.get("completion_sensitivity", 0.10),
        yards_sensitivity=qb_split_raw.get("yards_sensitivity", 0.12),
        catch_rate_clamp=tuple(qb_split_raw.get("catch_rate_clamp", [0.95, 1.05])),
        yards_scale_clamp=tuple(qb_split_raw.get("yards_scale_clamp", [0.94, 1.06])),
        min_pressure_dropbacks=qb_split_raw.get("min_pressure_dropbacks", 20),
        min_clean_dropbacks=qb_split_raw.get("min_clean_dropbacks", 40),
        min_games=qb_split_raw.get("min_games", 4),
        early_season_blend=qb_split_raw.get("early_season_blend", True),
    )

    kicker_raw = pff.get("kicker", {})
    kicker = KickerConfig(
        enabled=kicker_raw.get("enabled", True),
        prior_strength=kicker_raw.get("prior_strength", 20),
        min_attempts=kicker_raw.get("min_attempts", 5),
    )

    dst_raw = pff.get("dst_baseline", {})
    dst_baseline = DstBaselineConfig(
        enabled=dst_raw.get("enabled", True),
        sensitivities=dst_raw.get("sensitivities", {"fumble_rate": 0.06}),
        prior_strength=dst_raw.get("prior_strength", 10),
        min_games=dst_raw.get("min_games", 4),
        clamp=dst_raw.get("clamp", [0.85, 1.15]),
    )

    return PffConfig(
        enabled=pff.get("enabled", False),
        data_dir=pff.get("data_dir"),
        matchup=matchup,
        talent=talent,
        tier_engine=tier_engine,
        team_context=team_context,
        coverage=coverage,
        depth_role=depth_role,
        rb_scheme_fit=rb_scheme_fit,
        qb_split=qb_split,
        kicker=kicker,
        dst_baseline=dst_baseline,
    )

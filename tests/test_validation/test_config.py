"""Tests for validation config resolution."""
import copy

import pytest
from fantasy_sim.validation.config import (
    _parse_value,
    apply_overrides,
    bare_config_dict,
    build_game_config_kwargs,
    build_engine_configs,
    build_bare_engine_configs,
)
from fantasy_sim.config.loader import load_defaults
from fantasy_sim.validation.parallel import build_games_parallel


class TestParseValue:
    def test_true(self):
        assert _parse_value("true") is True

    def test_false(self):
        assert _parse_value("false") is False

    def test_true_case_insensitive(self):
        assert _parse_value("True") is True
        assert _parse_value("FALSE") is False

    def test_int(self):
        assert _parse_value("42") == 42
        assert isinstance(_parse_value("42"), int)

    def test_negative_int(self):
        assert _parse_value("-3") == -3

    def test_float(self):
        assert _parse_value("0.06") == 0.06
        assert isinstance(_parse_value("0.06"), float)

    def test_negative_float(self):
        assert _parse_value("-0.03") == -0.03

    def test_string(self):
        assert _parse_value("hello") == "hello"
        assert isinstance(_parse_value("hello"), str)

    def test_empty_string(self):
        assert _parse_value("") == ""

    def test_list_of_floats(self):
        result = _parse_value("[0.85,1.15]")
        assert result == [0.85, 1.15]

    def test_list_of_ints(self):
        result = _parse_value("[1,2,3]")
        assert result == [1, 2, 3]

    def test_empty_list(self):
        assert _parse_value("[]") == []

    def test_list_with_spaces(self):
        result = _parse_value("[0.60, 1.40]")
        assert result == [0.60, 1.40]


class TestApplyOverrides:
    def test_set_nested_bool(self):
        config = {"pff": {"matchup": {"enabled": True}}}
        result = apply_overrides(config, ["pff.matchup.enabled=false"])
        assert result["pff"]["matchup"]["enabled"] is False

    def test_set_nested_float(self):
        config = {"pff": {"matchup": {"pass_defense_sensitivity": 0.08}}}
        result = apply_overrides(config, ["pff.matchup.pass_defense_sensitivity=0.12"])
        assert result["pff"]["matchup"]["pass_defense_sensitivity"] == 0.12

    def test_multiple_overrides(self):
        config = {"pff": {"enabled": True, "matchup": {"enabled": True}}}
        result = apply_overrides(config, [
            "pff.enabled=false",
            "pff.matchup.enabled=false",
        ])
        assert result["pff"]["enabled"] is False
        assert result["pff"]["matchup"]["enabled"] is False

    def test_does_not_mutate_original(self):
        config = {"pff": {"matchup": {"enabled": True}}}
        apply_overrides(config, ["pff.matchup.enabled=false"])
        assert config["pff"]["matchup"]["enabled"] is True

    def test_top_level_key(self):
        config = {"scoring_format": "ppr"}
        result = apply_overrides(config, ["scoring_format=half_ppr"])
        assert result["scoring_format"] == "half_ppr"

    def test_invalid_key_raises(self):
        config = {"pff": {"matchup": {"enabled": True}}}
        with pytest.raises(KeyError):
            apply_overrides(config, ["pff.nonexistent.enabled=false"])

    def test_set_int(self):
        config = {"pff": {"kicker": {"prior_strength": 20}}}
        result = apply_overrides(config, ["pff.kicker.prior_strength=30"])
        assert result["pff"]["kicker"]["prior_strength"] == 30

    def test_set_list(self):
        config = {"usage": {"snap": {"factor_clamp": [0.70, 1.30]}}}
        result = apply_overrides(config, ["usage.snap.factor_clamp=[0.85,1.15]"])
        assert result["usage"]["snap"]["factor_clamp"] == [0.85, 1.15]

    def test_invalid_leaf_key_raises(self):
        config = {"pff": {"matchup": {"enabled": True}}}
        with pytest.raises(KeyError, match="enabledd"):
            apply_overrides(config, ["pff.matchup.enabledd=false"])


class TestBuildEngineConfigs:
    def test_defaults_produces_enabled_configs(self):
        defaults = load_defaults()
        configs = build_engine_configs(defaults)
        assert configs["pff_config"] is not None
        assert configs["pff_config"].enabled is True
        assert configs["weather_config"] is not None
        assert configs["weather_config"].enabled is True
        assert configs["vegas_config"] is not None
        assert configs["props_config"] is not None
        assert configs["usage_config"] is not None

    def test_defaults_include_enabled_game_script_config(self):
        defaults = load_defaults()

        configs = build_engine_configs(defaults)

        assert "game_script_config" in configs
        assert configs["game_script_config"] is not None
        assert configs["game_script_config"].enabled is True

    def test_defaults_enable_promoted_availability_and_market_history_but_keep_role_trend_disabled(self):
        defaults = load_defaults()
        configs = build_engine_configs(defaults)

        assert configs["availability_config"] is not None
        assert configs["availability_config"].enabled is True
        assert configs["availability_config"].injuries.enabled is False
        assert configs["role_trend_config"] is None
        assert configs["market_history_config"] is not None
        assert configs["market_history_config"].enabled is True

    def test_defaults_include_disabled_tracking_config_until_phase4_promotion(self):
        defaults = load_defaults()

        configs = build_engine_configs(defaults)

        assert "tracking_config" in configs
        assert configs["tracking_config"] is None

    def test_defaults_keep_target_selection_disabled(self):
        defaults = load_defaults()

        configs = build_engine_configs(defaults)

        assert "target_selection_config" in configs
        assert configs["target_selection_config"] is None

    def test_defaults_keep_play_call_model_disabled(self):
        defaults = load_defaults()

        configs = build_engine_configs(defaults)

        assert "play_call_model_config" in configs
        assert configs["play_call_model_config"] is None

    def test_defaults_keep_qb_rushing_disabled(self):
        defaults = load_defaults()

        configs = build_engine_configs(defaults)

        assert "qb_rushing_config" in configs
        assert configs["qb_rushing_config"] is None

    def test_enabled_target_selection_config_is_built(self):
        defaults = load_defaults()
        overridden = apply_overrides(
            defaults,
            [
                "target_selection.enabled=true",
                "target_selection.artifacts_dir=results/target_selection/test",
                "target_selection.max_logit_delta=2.25",
            ],
        )

        configs = build_engine_configs(overridden)

        assert configs["target_selection_config"] is not None
        assert configs["target_selection_config"].artifacts_dir == "results/target_selection/test"
        assert configs["target_selection_config"].max_logit_delta == 2.25

    def test_enabled_play_call_model_config_is_built(self):
        defaults = load_defaults()
        overridden = apply_overrides(
            defaults,
            [
                "play_call_model.enabled=true",
                "play_call_model.artifacts_dir=results/play_call_model/test",
                "play_call_model.probability_clamp=[0.10,0.90]",
            ],
        )

        configs = build_engine_configs(overridden)

        assert configs["play_call_model_config"] is not None
        assert configs["play_call_model_config"].artifacts_dir == "results/play_call_model/test"
        assert configs["play_call_model_config"].probability_clamp == (0.10, 0.90)

    def test_enabled_qb_rushing_config_is_built(self):
        defaults = load_defaults()
        overridden = apply_overrides(
            defaults,
            [
                "qb_rushing.scramble.enabled=true",
                "qb_rushing.scramble.artifacts_dir=results/qb_rushing/scramble/test",
                "qb_rushing.scramble.factor_clamp=[0.75,1.40]",
                "qb_rushing.scramble.probability_clamp=[0.01,0.20]",
            ],
        )

        configs = build_engine_configs(overridden)

        assert configs["qb_rushing_config"] is not None
        assert configs["qb_rushing_config"].scramble.artifacts_dir == "results/qb_rushing/scramble/test"
        assert configs["qb_rushing_config"].scramble.factor_clamp == (0.75, 1.40)
        assert configs["qb_rushing_config"].scramble.probability_clamp == (0.01, 0.20)

    def test_enabled_qb_designed_run_config_is_built_without_scramble(self):
        defaults = load_defaults()
        overridden = apply_overrides(
            defaults,
            [
                "qb_rushing.designed_runs.enabled=true",
                "qb_rushing.designed_runs.artifacts_dir=results/qb_rushing/designed/test",
            ],
        )

        configs = build_engine_configs(overridden)

        assert configs["qb_rushing_config"] is not None
        assert configs["qb_rushing_config"].scramble.enabled is False
        assert configs["qb_rushing_config"].designed_runs.enabled is True
        assert (
            configs["qb_rushing_config"].designed_runs.artifacts_dir
            == "results/qb_rushing/designed/test"
        )

    def test_build_game_config_kwargs_omits_post_sim_configs(self, tmp_path):
        defaults = load_defaults()
        configs = build_engine_configs(defaults)

        build_configs = build_game_config_kwargs(configs)

        assert "qb_rushing_config" in build_configs
        assert build_games_parallel([], cache_dir=tmp_path, **build_configs) == []

    def test_build_games_parallel_accepts_wired_qb_rushing_config(self, tmp_path):
        defaults = load_defaults()
        configs = build_engine_configs(defaults)
        build_configs = {
            key: value
            for key, value in configs.items()
            if key not in {"role_trend_config", "market_history_config"}
        }

        assert build_games_parallel([], cache_dir=tmp_path, **build_configs) == []

    def test_enabled_tracking_config_is_built_and_propagates_nested_values(self):
        defaults = load_defaults()
        overridden = apply_overrides(
            defaults,
            [
                "tracking.enabled=true",
                "tracking.window_weeks=6",
                "tracking.receiver_participation.min_targets=11",
            ],
        )

        configs = build_engine_configs(overridden)

        assert configs["tracking_config"] is not None
        assert configs["tracking_config"].window_weeks == 6
        assert configs["tracking_config"].receiver_participation.min_targets == 11

    def test_market_history_override_propagates(self):
        defaults = load_defaults()
        overridden = apply_overrides(defaults, ["market_history.enabled=false"])

        configs = build_engine_configs(overridden)

        assert configs["market_history_config"] is None

    def test_dynamic_blend_override_propagates_through_ensemble_config(self):
        from fantasy_sim.data.ensemble.config import load_ensemble_config

        defaults = load_defaults()
        overridden = apply_overrides(
            defaults,
            [
                "ensemble.dynamic_blend.enabled=true",
                "ensemble.dynamic_blend.weights_dir=results/dynamic_blend/test",
                "ensemble.dynamic_blend.grid_step=0.1",
            ],
        )

        config = load_ensemble_config(overridden)

        assert config.dynamic_blend.enabled is True
        assert config.dynamic_blend.weights_dir == "results/dynamic_blend/test"
        assert config.dynamic_blend.grid_step == 0.1

    def test_residual_calibration_override_propagates_through_ensemble_config(self):
        from fantasy_sim.data.ensemble.config import load_ensemble_config

        defaults = load_defaults()
        overridden = apply_overrides(
            defaults,
            [
                "ensemble.residual_calibration.enabled=true",
                "ensemble.residual_calibration.artifacts_dir=results/residual_calibration/test",
                "ensemble.residual_calibration.max_abs_adjustment=1.25",
            ],
        )

        config = load_ensemble_config(overridden)

        assert config.residual_calibration.enabled is True
        assert config.residual_calibration.artifacts_dir == "results/residual_calibration/test"
        assert config.residual_calibration.max_abs_adjustment == 1.25

    def test_defaults_enable_promoted_ensemble_layers(self):
        from fantasy_sim.data.ensemble.config import load_ensemble_config

        defaults = load_defaults()

        config = load_ensemble_config(defaults)

        assert config.enabled is True
        assert config.dynamic_blend.enabled is True
        assert config.dynamic_blend.weights_dir is None
        assert config.residual_calibration.enabled is True
        assert config.residual_calibration.artifacts_dir is None

    def test_disabled_engine_returns_none(self):
        defaults = load_defaults()
        overridden = apply_overrides(defaults, ["pff.enabled=false"])
        configs = build_engine_configs(overridden)
        assert configs["pff_config"] is None

    def test_sub_engine_override_propagates(self):
        defaults = load_defaults()
        overridden = apply_overrides(defaults, ["pff.matchup.enabled=false"])
        configs = build_engine_configs(overridden)
        assert configs["pff_config"] is not None
        assert configs["pff_config"].matchup.enabled is False

    def test_pff_depth_role_override_propagates(self):
        defaults = load_defaults()
        overridden = apply_overrides(
            defaults,
            [
                "pff.depth_role.enabled=true",
                "pff.depth_role.wr.target_share_sensitivity=0.14",
            ],
        )

        configs = build_engine_configs(overridden)

        assert configs["pff_config"] is not None
        assert configs["pff_config"].depth_role.enabled is True
        assert configs["pff_config"].depth_role.wr.target_share_sensitivity == 0.14

    def test_pff_rb_scheme_fit_override_propagates(self):
        defaults = load_defaults()
        overridden = apply_overrides(
            defaults,
            [
                "pff.rb_scheme_fit.enabled=true",
                "pff.rb_scheme_fit.rush_yards_sensitivity=0.14",
                "pff.rb_scheme_fit.min_attempts=28",
            ],
        )

        configs = build_engine_configs(overridden)

        assert configs["pff_config"] is not None
        assert configs["pff_config"].rb_scheme_fit.enabled is True
        assert configs["pff_config"].rb_scheme_fit.rush_yards_sensitivity == 0.14
        assert configs["pff_config"].rb_scheme_fit.min_attempts == 28

    def test_pff_qb_split_override_propagates(self):
        defaults = load_defaults()
        overridden = apply_overrides(
            defaults,
            [
                "pff.qb_split.enabled=true",
                "pff.qb_split.completion_sensitivity=0.17",
                "pff.qb_split.min_pressure_dropbacks=24",
            ],
        )

        configs = build_engine_configs(overridden)

        assert configs["pff_config"] is not None
        assert configs["pff_config"].qb_split.enabled is True
        assert configs["pff_config"].qb_split.completion_sensitivity == 0.17
        assert configs["pff_config"].qb_split.min_pressure_dropbacks == 24

    def test_pff_depth_role_efficiency_override_propagates(self):
        defaults = load_defaults()
        overridden = apply_overrides(
            defaults,
            [
                "pff.depth_role.efficiency.enabled=true",
                "pff.depth_role.efficiency.wr.catch_rate_sensitivity=0.11",
                "pff.depth_role.efficiency.te.yards_scale_sensitivity=0.07",
            ],
        )

        configs = build_engine_configs(overridden)

        assert configs["pff_config"] is not None
        eff = configs["pff_config"].depth_role.efficiency
        assert eff.enabled is True
        assert eff.wr.catch_rate_sensitivity == 0.11
        assert eff.te.yards_scale_sensitivity == 0.07

    def test_pff_depth_role_invalid_position_override_raises(self):
        defaults = load_defaults()
        overridden = apply_overrides(
            defaults,
            ["pff.depth_role.positions=[WR,QB]"],
        )

        with pytest.raises(ValueError, match="Invalid pff\\.depth_role\\.positions config"):
            build_engine_configs(overridden)


class TestBuildBareEngineConfigs:
    def test_all_none(self):
        configs = build_bare_engine_configs()
        assert configs["pff_config"] is None
        assert configs["weather_config"] is None
        assert configs["vegas_config"] is None
        assert configs["props_config"] is None
        assert configs["usage_config"] is None
        assert configs["tracking_config"] is None
        assert configs["availability_config"] is None
        assert configs["role_trend_config"] is None
        assert configs["market_history_config"] is None
        assert configs["game_script_config"] is None
        assert configs["target_selection_config"] is None


# === KS-Phase1 / D-29 (HIGH-1) + D-44 (Cycle 3 NEW HIGH #2):
# bare_config_dict for true-isolation A/B ===


class TestBareConfigDict:
    def test_bare_config_dict_disables_pff_team_context(self):
        defaults = load_defaults()
        bare = bare_config_dict(defaults)
        assert bare["pff"]["team_context"]["enabled"] is False

    def test_bare_config_dict_disables_all_engines(self):
        defaults = load_defaults()
        bare = bare_config_dict(defaults)
        enabled_keys_to_check = [
            ("pff", "tier_engine", "enabled"),
            ("pff", "team_context", "enabled"),
            ("pff", "matchup", "enabled"),
            ("pff", "coverage", "enabled"),
            ("pff", "kicker", "enabled"),
            ("pff", "dst_baseline", "enabled"),
            ("weather", "enabled"),
            ("vegas", "enabled"),
            ("vegas", "props", "enabled"),
        ]
        for path in enabled_keys_to_check:
            target = bare
            try:
                for k in path[:-1]:
                    target = target[k]
                assert target.get(path[-1], False) is False, (
                    f"key {'.'.join(path)} not disabled"
                )
            except (KeyError, TypeError):
                # Path missing in defaults — acceptable; bare_config_dict skips silently
                pass

    def test_bare_config_dict_preserves_non_enabled_keys(self):
        defaults = load_defaults()
        bare = bare_config_dict(defaults)
        # Pick a known non-enabled key that exists in the defaults tree.
        # If the test runs and the path is missing, defaults.yaml schema changed —
        # update the test.
        # We only compare SCALAR/list values at this level — nested sub-dicts may
        # themselves contain `enabled` flags (e.g., tier_engine.ncaa_rookie.enabled,
        # tier_engine.archetypes.enabled) that bare_config_dict legitimately flips.
        if "pff" in defaults and "tier_engine" in defaults["pff"]:
            tier_engine = defaults["pff"]["tier_engine"]
            bare_tier_engine = bare["pff"]["tier_engine"]
            for key, val in tier_engine.items():
                if key == "enabled":
                    continue  # this one IS supposed to flip
                if isinstance(val, dict):
                    continue  # nested sub-dicts may have their own .enabled flips
                assert bare_tier_engine[key] == val, (
                    f"non-enabled scalar key {key} was mutated"
                )

    def test_apply_overrides_on_bare_config_dict_enables_one_engine(self):
        defaults = load_defaults()
        bare = bare_config_dict(defaults)
        isolated = apply_overrides(bare, ["pff.team_context.enabled=true"])

        assert isolated["pff"]["team_context"]["enabled"] is True
        # Spot-check that other engines remain disabled
        if "pff" in isolated and "matchup" in isolated["pff"]:
            assert isolated["pff"]["matchup"].get("enabled", False) is False
        if "weather" in isolated:
            assert isolated["weather"].get("enabled", False) is False

    def test_bare_config_dict_does_not_mutate_input(self):
        defaults = load_defaults()
        snapshot = copy.deepcopy(defaults)
        bare_config_dict(defaults)
        assert defaults == snapshot, "bare_config_dict mutated its input"

    def test_arm_b_construction_bare_base_with_one_engine_override(self):
        """End-to-end: bare_config_dict + apply_overrides + build_engine_configs
        produces a one-engine config.

        REVISED Cycle 3: callers must flip BOTH the top-level gate (pff.enabled)
        AND the sub-engine flag (pff.team_context.enabled) because
        build_engine_configs at validation/config.py:118-138 keys off pff.enabled.
        This is the canonical contract for per-KS isolation A/Bs that need to
        enable a single PFF sub-engine.
        """
        defaults = load_defaults()
        bare = bare_config_dict(defaults)
        isolated = apply_overrides(
            bare,
            [
                "pff.enabled=true",
                "pff.tier_engine.enabled=true",
                "pff.team_context.enabled=true",
            ],
        )
        configs = build_engine_configs(isolated)

        # PFF config exists and reflects the sub-engine flip
        assert configs["pff_config"] is not None
        assert configs["pff_config"].team_context.enabled is True

        # All other engines should be None
        other_engine_keys = (
            "weather_config",
            "vegas_config",
            "props_config",
            "usage_config",
            "tracking_config",
            "availability_config",
            "role_trend_config",
            "market_history_config",
            "game_script_config",
            "goal_line_concentration_config",
            "td_tendency_config",
            "target_selection_config",
            "play_call_model_config",
            "qb_rushing_config",
        )
        for key in other_engine_keys:
            assert configs.get(key) is None, (
                f"engine {key} should be None on bare base, got {configs.get(key)}"
            )

    # === HARD GATE (Cycle 3 — Codex Cycle-2 NEW HIGH #2 fix) ===

    def test_bare_config_dict_produces_all_None_engines(self):
        """HARD GATE: bare_config_dict(load_defaults()) must produce a config where
        EVERY engine returns None from build_engine_configs.

        REVISED Cycle 3 (replaces Cycle-2 'loosen the test' escape hatch):
        if this test fails, bare_config_dict is incomplete. EXTEND THE HELPER
        (add the missing top-level gate or sub-engine flag to the
        enabled_keys_to_disable tuple), DO NOT loosen this test. The Cycle-2
        disposition explicitly allowed 'loosen the test' as a fallback; Codex
        Cycle-2 NEW HIGH #2 flagged that as the reason HIGH-1 wasn't actually
        closed. Cycle 3 forbids the escape hatch.
        """
        defaults = load_defaults()
        bare = bare_config_dict(defaults)
        configs = build_engine_configs(bare)

        # Every engine must be None — no exceptions
        all_engine_keys = (
            "pff_config",
            "weather_config",
            "vegas_config",
            "props_config",
            "usage_config",
            "tracking_config",
            "availability_config",
            "role_trend_config",
            "market_history_config",
            "game_script_config",
            "goal_line_concentration_config",
            "td_tendency_config",
            "target_selection_config",
            "play_call_model_config",
            "qb_rushing_config",
        )
        failures = []
        for key in all_engine_keys:
            if configs.get(key) is not None:
                failures.append(key)
        assert not failures, (
            f"bare_config_dict() is INCOMPLETE — engines still active after the "
            f"helper: {failures}. Fix bare_config_dict in "
            f"src/fantasy_sim/validation/config.py by adding the missing "
            f"top-level .enabled gate or sub-engine flag to the "
            f"enabled_keys_to_disable tuple. DO NOT loosen this test "
            f"(Cycle 3 acceptance contract; see plan 00 Task 4)."
        )

    # === NEW Cycle 3 — Phase-1 KS feature flag coverage ===

    def test_bare_config_dict_disables_all_phase1_ks_flags(self):
        """All 8 Phase-1 KS feature flags must be False after bare_config_dict()."""
        defaults = load_defaults()
        bare = bare_config_dict(defaults)
        ks_flags = bare.get("phase1_ks_flags", {})
        expected_flags = (
            "ks01_preserve_distribution",
            "ks03_dynamic_yard_anchor",
            "ks04_conditional_catch_boost",
            "ks05_props_recv_yds_fix",
            "ks06_backup_receiver_fix",
            "ks07_positional_rz_catch_rate",
            "ks15_unclamp_for_td_gate",
            "ks32_clock_pass_incomplete_3s",
        )
        for flag in expected_flags:
            block = ks_flags.get(flag, {})
            assert block.get("enabled", True) is False, (
                f"phase1_ks_flags.{flag}.enabled is {block.get('enabled')}, "
                f"expected False"
            )

    def test_apply_overrides_on_bare_config_dict_flips_one_phase1_ks_flag(self):
        """Per-KS bare-isolation A/B contract: bare base + one --set flips exactly
        one KS flag."""
        defaults = load_defaults()
        bare = bare_config_dict(defaults)
        isolated = apply_overrides(
            bare,
            ["phase1_ks_flags.ks01_preserve_distribution.enabled=true"],
        )
        assert (
            isolated["phase1_ks_flags"]["ks01_preserve_distribution"]["enabled"]
            is True
        )
        # Other 7 flags must still be False
        for flag in (
            "ks03_dynamic_yard_anchor",
            "ks04_conditional_catch_boost",
            "ks05_props_recv_yds_fix",
            "ks06_backup_receiver_fix",
            "ks07_positional_rz_catch_rate",
            "ks15_unclamp_for_td_gate",
            "ks32_clock_pass_incomplete_3s",
        ):
            assert isolated["phase1_ks_flags"][flag]["enabled"] is False, (
                f"phase1_ks_flags.{flag} should still be False, got "
                f"{isolated['phase1_ks_flags'][flag]}"
            )


# === Phase 2 KS feature flag tests (D-02 / D-44 pattern, Plan 01) ===


def test_phase2_ks_flags_present_and_default_false():
    """HARD GATE: every phase2_ks_flags entry must exist in defaults and default to enabled: false.

    Per Phase 2 D-02: per-KS plans land their code path behind `phase2_ks_flags.ksXX_<name>.enabled`
    with default false. The promotion commit per plan flips the default to true. This test
    catches the case where someone adds a KS code change behind a flag that doesn't exist in
    defaults (would silently behave as `False`, hiding the regression).

    Promoted flags (enabled: true by design — do not include in the "must be false" set):
      - ks08_dynamic_blend_simulator_floor: SHIPPED 2026-04-26 (Plan 02)
      - ks09_per_stat_residual_calibration: SHIPPED-PARTIAL 2026-04-27 (Plan 03)
      - ks14_thin_bucket_shrinkage: SHIPPED 2026-04-27 (Plan 04)
      - ks10_per_position_caps: SHIPPED 2026-04-27 (Plan 05)
      - ks11_position_reliability: SHIPPED 2026-04-27 (Plan 06)
    """
    from fantasy_sim.config.loader import get_phase2_ks_flags
    flags = get_phase2_ks_flags()
    expected_all = {
        "ks08_dynamic_blend_simulator_floor",
        "ks09_per_stat_residual_calibration",
        "ks10_per_position_caps",
        "ks11_position_reliability",
        "ks12_share_normalization_residual",
        "ks13_ff_opportunity_prior_width",
        "ks14_thin_bucket_shrinkage",
    }
    # Flags that have been promoted to enabled=true (excluded from "must be false" check)
    promoted = {
        "ks08_dynamic_blend_simulator_floor",  # SHIPPED 2026-04-26 (Plan 02)
        "ks09_per_stat_residual_calibration",  # SHIPPED-PARTIAL 2026-04-27 (Plan 03)
        "ks14_thin_bucket_shrinkage",           # SHIPPED 2026-04-27 (Plan 04)
        "ks10_per_position_caps",              # SHIPPED 2026-04-27 (Plan 05)
        "ks11_position_reliability",           # SHIPPED 2026-04-27 (Plan 06)
    }
    assert set(flags.keys()) >= expected_all, f"Missing phase2_ks_flags entries: {expected_all - set(flags.keys())}"
    for name in expected_all - promoted:
        assert flags[name].get("enabled") is False, f"phase2_ks_flags.{name}.enabled must default to False (got {flags[name].get('enabled')!r})"
    for name in promoted:
        assert flags[name].get("enabled") is True, f"phase2_ks_flags.{name}.enabled should be True (promoted flag)"


def test_phase2_bare_config_disables_all_new_flags():
    """HARD GATE: bare_config_dict() must enumerate every phase2_ks_flags.*.enabled key.

    Mirrors the Phase 1 hard-gate test pattern (D-44). If a Phase 2 KS plan adds a flag
    to defaults but forgets to add it to bare_config_dict(), the per-KS bare-isolation A/B
    silently runs both arms with the same flag value and produces a no-op A/B (the Cycle-2
    failure mode). This test refuses to merge a plan that does so.
    """
    from fantasy_sim.config.loader import load_defaults
    from fantasy_sim.validation.config import bare_config_dict
    bare = bare_config_dict(load_defaults())
    assert bare["phase2_ks_flags"]["ks08_dynamic_blend_simulator_floor"]["enabled"] is False
    assert bare["phase2_ks_flags"]["ks09_per_stat_residual_calibration"]["enabled"] is False
    assert bare["phase2_ks_flags"]["ks10_per_position_caps"]["enabled"] is False
    assert bare["phase2_ks_flags"]["ks11_position_reliability"]["enabled"] is False
    assert bare["phase2_ks_flags"]["ks12_share_normalization_residual"]["enabled"] is False
    assert bare["phase2_ks_flags"]["ks13_ff_opportunity_prior_width"]["enabled"] is False
    assert bare["phase2_ks_flags"]["ks14_thin_bucket_shrinkage"]["enabled"] is False
    # Sub-engine gates from Plan 01 Task 1
    assert bare["ensemble"]["residual_calibration"]["stat_level"]["enabled"] is False
    assert bare["ensemble"]["ff_opportunity"]["prior_width"]["enabled"] is False

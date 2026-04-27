"""Config resolution for A/B validation.

Replaces the mode-based config system with defaults.yaml + dot-notation overrides.
"""

from __future__ import annotations

import copy

from fantasy_sim.data.market_history.config import load_market_history_config
from fantasy_sim.data.pff.config import load_pff_config
from fantasy_sim.data.weather.config import load_weather_config
from fantasy_sim.data.vegas.config import load_vegas_config, load_props_config
from fantasy_sim.data.availability.config import load_availability_config
from fantasy_sim.data.role_trend.config import load_role_trend_config
from fantasy_sim.data.usage.config import load_usage_config
from fantasy_sim.data.tracking.config import load_tracking_config
from fantasy_sim.data.game_script import load_game_script_config
from fantasy_sim.data.goal_line_concentration import load_goal_line_concentration_config
from fantasy_sim.data.play_call_model import load_play_call_model_config
from fantasy_sim.data.qb_rushing import load_qb_rushing_config
from fantasy_sim.data.target_selection import load_target_selection_config
from fantasy_sim.data.td_tendency import load_td_tendency_config

BUILD_GAME_CONFIG_EXCLUDE_KEYS = frozenset(
    {
        "role_trend_config",
        "market_history_config",
    }
)


def build_game_config_kwargs(configs: dict) -> dict:
    """Return only engine configs accepted by build_games_parallel()."""
    return {
        key: value
        for key, value in configs.items()
        if key not in BUILD_GAME_CONFIG_EXCLUDE_KEYS
    }


def _parse_value(s: str) -> bool | int | float | str | list:
    """Parse a CLI string value to its Python type.

    Handles: 'true'/'false' -> bool, [a,b,...] -> list of parsed values,
    integers, floats, else str.
    """
    if s.lower() == "true":
        return True
    if s.lower() == "false":
        return False
    # List syntax: [0.85,1.15] or [1,2,3]
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        if not inner:
            return []
        return [_parse_value(item.strip()) for item in inner.split(",")]
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s


def apply_overrides(config: dict, overrides: list[str]) -> dict:
    """Apply dot-notation overrides to a config dict.

    Each override is 'dotted.key.path=value'. Deep-copies config first
    so the original is never mutated.

    Raises KeyError if any key in the path doesn't exist (including the leaf).
    """
    config = copy.deepcopy(config)
    for override in overrides:
        key_path, raw_value = override.split("=", 1)
        keys = key_path.split(".")
        target = config
        for k in keys[:-1]:
            target = target[k]
        leaf = keys[-1]
        if leaf not in target:
            raise KeyError(
                f"Unknown config key '{key_path}': "
                f"'{leaf}' not found in {'.'.join(keys[:-1]) or 'root'}"
            )
        target[leaf] = _parse_value(raw_value)
    return config


def build_engine_configs(config: dict) -> dict:
    """Build all engine config dataclasses from a full config dict.

    Returns a dict with keys: pff_config, weather_config, vegas_config,
    props_config, usage_config, tracking_config, availability_config,
    role_trend_config, market_history_config, game_script_config,
    goal_line_concentration_config, td_tendency_config.
    Each value is the config dataclass if enabled, or None if disabled.
    """
    pff = load_pff_config(config)
    weather = load_weather_config(config)
    vegas = load_vegas_config(config)
    props = load_props_config(config)
    usage = load_usage_config(config)
    tracking = load_tracking_config(config)
    availability = load_availability_config(config)
    role_trend = load_role_trend_config(config)
    market_history = load_market_history_config(config)
    game_script = load_game_script_config(config)
    goal_line_concentration = load_goal_line_concentration_config(config)
    td_tendency = load_td_tendency_config(config)
    target_selection = load_target_selection_config(config)
    play_call_model = load_play_call_model_config(config)
    qb_rushing = load_qb_rushing_config(config)
    return {
        "pff_config": pff if pff.enabled else None,
        "weather_config": weather if weather.enabled else None,
        "vegas_config": vegas if vegas.enabled else None,
        "props_config": props if props.enabled else None,
        "usage_config": usage if usage.enabled else None,
        "tracking_config": tracking if tracking.enabled else None,
        "availability_config": availability if availability.enabled else None,
        "role_trend_config": role_trend if role_trend.enabled else None,
        "market_history_config": market_history if market_history.enabled else None,
        "game_script_config": game_script if game_script.enabled else None,
        "goal_line_concentration_config": (
            goal_line_concentration if goal_line_concentration.enabled else None
        ),
        "td_tendency_config": td_tendency if td_tendency.enabled else None,
        "target_selection_config": target_selection if target_selection.enabled else None,
        "play_call_model_config": play_call_model if play_call_model.enabled else None,
        "qb_rushing_config": qb_rushing
        if (qb_rushing.scramble.enabled or qb_rushing.designed_runs.enabled)
        else None,
    }


def build_bare_engine_configs() -> dict:
    """Return engine configs dict with all engines disabled (None)."""
    return {
        "pff_config": None,
        "weather_config": None,
        "vegas_config": None,
        "props_config": None,
        "usage_config": None,
        "tracking_config": None,
        "availability_config": None,
        "role_trend_config": None,
        "market_history_config": None,
        "game_script_config": None,
        "goal_line_concentration_config": None,
        "td_tendency_config": None,
        "target_selection_config": None,
        "play_call_model_config": None,
        "qb_rushing_config": None,
    }


def bare_config_dict(defaults: dict) -> dict:
    """Return a deepcopy of defaults with every .enabled gate forced false.

    Used as the source dict for ``apply_overrides`` when ``--arm-b-base bare`` is set
    on validate.py. Preserves the dict structure so user-requested overrides like
    ``--set pff.team_context.enabled=true`` (or
    ``--set phase1_ks_flags.ks01_preserve_distribution.enabled=true``) can locate
    the same leaf paths.

    REVISED Cycle 3 (Codex 01-REVIEWS.md NEW HIGH #2 fix): includes BOTH the
    top-level engine gates that build_engine_configs at validation/config.py:118-138
    keys off AND the sub-engine flags. The earlier (Cycle 2) version omitted the
    top-level gates, which meant a 'bare' base still had pff.enabled=true (etc.),
    so any --set pff.X.enabled=true override gave a config where many other PFF
    sub-engines were still bound by their defaults. Cycle 3 makes this exhaustive.

    REVISED Cycle 3 (Codex 01-REVIEWS.md NEW HIGH #1 fix): also disables every
    phase1_ks_flags.ksXX_*.enabled flag so per-KS bare-isolation A/B can flip
    exactly one flag in Arm B via --set.

    Engines disabled here must match the truthiness checks in
    ``build_engine_configs()`` above. The Task 4 integration test asserts this
    exhaustively (every engine returns None from
    build_engine_configs(bare_config_dict(load_defaults()))).
    """
    config = copy.deepcopy(defaults)

    enabled_keys_to_disable = (
        # === Top-level engine gates (NEW Cycle 3 — fixes Codex Cycle-2 NEW HIGH #2) ===
        # Each of these is what build_engine_configs in validation/config.py:118-138
        # keys off.
        "pff.enabled",
        "weather.enabled",
        "vegas.enabled",
        "props.enabled",  # Top-level props block (sibling to vegas; distinct from vegas.props.enabled)
        "usage.enabled",
        "tracking.enabled",
        "availability.enabled",
        "role_trend.enabled",
        "market_history.enabled",
        "game_script.enabled",
        "goal_line_concentration.enabled",
        "td_tendency.enabled",
        "target_selection.enabled",
        "play_call_model.enabled",
        # qb_rushing: gate is `scramble.enabled OR designed_runs.enabled`,
        # so disable BOTH
        "qb_rushing.scramble.enabled",
        "qb_rushing.designed_runs.enabled",

        # === PFF sub-engines (Cycle 2 baseline; preserved) ===
        "pff.tier_engine.enabled",
        "pff.team_context.enabled",
        "pff.matchup.enabled",
        "pff.coverage.enabled",
        "pff.kicker.enabled",
        "pff.dst_baseline.enabled",
        "pff.rb_scheme_fit.enabled",
        "pff.qb_split.enabled",
        "pff.depth_role.enabled",
        "pff.depth_role.efficiency.enabled",
        "pff.talent.enabled",
        "pff.tier_engine.ncaa_rookie.enabled",
        "pff.tier_engine.archetypes.enabled",

        # === Vegas sub-engines (Cycle 2 baseline; preserved) ===
        # Note: vegas.props.enabled is the sub-engine flag for the Vegas props
        # integration, distinct from the top-level props.enabled block above.
        "vegas.props.enabled",

        # === Usage sub-engines (Cycle 2 baseline; preserved) ===
        "usage.cpoe.enabled",
        "usage.ngs.enabled",
        "usage.route_rate.enabled",

        # === Ensemble (Cycle 2 baseline; preserved) ===
        "ensemble.enabled",
        "ensemble.ff_opportunity.enabled",
        "ensemble.ff_rankings.enabled",
        "ensemble.dynamic_blend.enabled",
        "ensemble.residual_calibration.enabled",

        # === Tracking sub-engines (Cycle 2 baseline; preserved) ===
        "tracking.receiver_participation.enabled",
        "tracking.rb_efficiency.enabled",
        "tracking.qb_context.enabled",

        # === Availability sub-engines (Cycle 2 baseline; preserved) ===
        "availability.injuries.enabled",
        "availability.depth_charts.enabled",
        "availability.usage_fallback.enabled",

        # === Game-script sub-engines (Cycle 2 baseline; preserved) ===
        "game_script.trailing_late.enabled",
        "game_script.leading_late_rb.enabled",

        # === Phase-1 KS feature flags (NEW Cycle 3 — fixes Codex Cycle-2 NEW HIGH #1) ===
        # Each flag gates one per-KS code change; default false (Task 8 ships
        # defaults.yaml block). Disabling them in bare_config_dict means per-KS
        # bare A/B can flip exactly one in Arm B.
        "phase1_ks_flags.ks01_preserve_distribution.enabled",
        "phase1_ks_flags.ks03_dynamic_yard_anchor.enabled",
        "phase1_ks_flags.ks04_conditional_catch_boost.enabled",
        "phase1_ks_flags.ks05_props_recv_yds_fix.enabled",
        "phase1_ks_flags.ks06_backup_receiver_fix.enabled",
        "phase1_ks_flags.ks07_positional_rz_catch_rate.enabled",
        "phase1_ks_flags.ks15_unclamp_for_td_gate.enabled",
        "phase1_ks_flags.ks32_clock_pass_incomplete_3s.enabled",

        # Phase 2 KS code-change feature flags (added — see 02-CONTEXT.md D-02 / D-44 pattern).
        # Each flag gates one per-KS code change so per-KS A/B can perform a real (legacy)
        # vs (new) two-arm comparison via `--set phase2_ks_flags.ksXX_<name>.enabled=true`.
        # Disabling them in bare_config_dict means per-KS bare-isolation A/B can flip them
        # back on with the same --set syntax. Plans 02-08 reference these.
        "phase2_ks_flags.ks08_dynamic_blend_simulator_floor.enabled",
        "phase2_ks_flags.ks09_per_stat_residual_calibration.enabled",
        "phase2_ks_flags.ks10_per_position_caps.enabled",
        "phase2_ks_flags.ks11_position_reliability.enabled",
        "phase2_ks_flags.ks12_share_normalization_residual.enabled",
        "phase2_ks_flags.ks13_ff_opportunity_prior_width.enabled",
        "phase2_ks_flags.ks14_thin_bucket_shrinkage.enabled",
        # Phase 2 sub-engine gates (the 5 new top-level keys from Plan 01 Task 1)
        "ensemble.residual_calibration.stat_level.enabled",
        "ensemble.ff_opportunity.prior_width.enabled",
    )

    for key_path in enabled_keys_to_disable:
        keys = key_path.split(".")
        target = config
        try:
            for k in keys[:-1]:
                target = target[k]
            if keys[-1] in target:
                target[keys[-1]] = False
        except (KeyError, TypeError):
            # Leaf doesn't exist in this defaults snapshot — engine may not be
            # configured yet. Skip silently; the corresponding load_X_config will
            # produce a disabled instance anyway.
            continue

    return config

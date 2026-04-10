import pytest

from fantasy_sim.data.game_script import (
    GameScriptConfig,
    GameScriptProfile,
    LeadingLateRbConfig,
    TrailingLateConfig,
)
from fantasy_sim.engine.game_script import (
    apply_pass_rate_factor,
    effective_pace_factor,
    resolve_game_script,
)
from fantasy_sim.engine.types import GameState


def make_state(**overrides) -> GameState:
    defaults = dict(
        quarter=1,
        clock=900,
        possession="home",
        down=1,
        distance=10,
        yard_line=75,
        home_score=0,
        away_score=0,
        home_team="KC",
        away_team="BUF",
        receiving_2nd_half="away",
    )
    defaults.update(overrides)
    return GameState(**defaults)


def make_config(enabled: bool = True) -> GameScriptConfig:
    return GameScriptConfig(
        enabled=enabled,
        trailing_late=TrailingLateConfig(
            deficit_threshold=8,
            final_five_minutes=300,
            final_five_deficit_threshold=4,
        ),
        leading_late_rb=LeadingLateRbConfig(
            enabled=True,
            lead_threshold=10,
            late_minutes=600,
        ),
    )


def make_profile() -> GameScriptProfile:
    return GameScriptProfile(
        team="KC",
        trailing_late_pass_rate_factor=1.3,
        trailing_late_pace_factor=1.1,
    )


def test_resolve_game_script_returns_trailing_late_for_fourth_quarter_deficit():
    state = make_state(quarter=4, clock=720, home_score=10, away_score=20)

    script = resolve_game_script(state, make_config(), make_profile())

    assert script.regime == "trailing_late"


def test_resolve_game_script_returns_trailing_late_inside_final_five():
    state = make_state(quarter=4, clock=240, home_score=17, away_score=21)

    script = resolve_game_script(state, make_config(), make_profile())

    assert script.regime == "trailing_late"


def test_resolve_game_script_returns_leading_late_rb_for_late_lead():
    state = make_state(quarter=4, clock=300, home_score=24, away_score=10)

    script = resolve_game_script(state, make_config(), make_profile())

    assert script.regime == "leading_late_rb"


def test_resolve_game_script_respects_trailing_subconfig_enabled_gate():
    state = make_state(quarter=4, clock=720, home_score=10, away_score=20)
    config = make_config()
    config.trailing_late.enabled = False

    script = resolve_game_script(state, config, make_profile())

    assert script.regime == "neutral"


def test_resolve_game_script_respects_leading_subconfig_enabled_gate():
    state = make_state(quarter=4, clock=300, home_score=24, away_score=10)
    config = make_config()
    config.leading_late_rb.enabled = False

    script = resolve_game_script(state, config, make_profile())

    assert script.regime == "neutral"


def test_resolve_game_script_returns_neutral_when_disabled():
    state = make_state(quarter=4, clock=240, home_score=10, away_score=21)

    script = resolve_game_script(state, make_config(enabled=False), make_profile())

    assert script.regime == "neutral"


def test_effective_pace_factor_multiplies_base_and_script():
    script = resolve_game_script(
        make_state(quarter=4, clock=240, home_score=10, away_score=21),
        make_config(),
        make_profile(),
    )

    assert effective_pace_factor(1.05, script) == pytest.approx(1.05 * 1.1)


def test_apply_pass_rate_factor_preserves_deterministic_pass_bucket():
    probs = apply_pass_rate_factor({"pass": 1.0, "run": 0.0}, 1.3)

    assert probs == {"pass": 1.0, "run": 0.0}

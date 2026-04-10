import polars as pl

from fantasy_sim.data.game_script.engine import GameScriptEngine
from fantasy_sim.data.game_script.models import (
    GameScriptConfig,
    LeadingLateRbConfig,
    TrailingLateConfig,
)


def make_config() -> GameScriptConfig:
    return GameScriptConfig(
        enabled=True,
        trailing_late=TrailingLateConfig(
            deficit_threshold=8,
            final_five_minutes=300,
            final_five_deficit_threshold=4,
            pass_rate_prior_strength=1.0,
            pace_prior_strength=1.0,
            target_prior_strength=1.0,
            pass_rate_clamp=(0.80, 2.00),
            pace_factor_clamp=(0.80, 2.00),
            target_rank_factor_clamp=(0.50, 2.00),
        ),
        leading_late_rb=LeadingLateRbConfig(
            enabled=True,
            lead_threshold=14,
            late_minutes=600,
            rb_carry_prior_strength=1.0,
            rb_rank_factor_clamp=(0.20, 4.00),
        ),
    )


def make_game_script_pbp(include_clock: bool = True) -> pl.DataFrame:
    plays: list[dict] = []

    def append_play(
        week: int,
        play_type: str,
        *,
        receiver_player_id: str | None = None,
        rusher_player_id: str | None = None,
        score_differential: int = 0,
        qtr: int = 2,
        game_seconds_remaining: int = 2400,
    ) -> None:
        row = {
            "season": 2024,
            "week": week,
            "posteam": "KC",
            "play_type": play_type,
            "pass_attempt": 1 if play_type == "pass" else 0,
            "rush_attempt": 1 if play_type == "run" else 0,
            "receiver_player_id": receiver_player_id,
            "rusher_player_id": rusher_player_id,
            "score_differential": score_differential,
            "qtr": qtr,
        }
        if include_clock:
            row["game_seconds_remaining"] = game_seconds_remaining
        plays.append(row)

    for week in range(1, 5):
        for receiver in ["KC_WR1", "KC_WR1", "KC_WR1", "KC_WR2", "KC_WR2", "KC_TE1"]:
            append_play(week, "pass", receiver_player_id=receiver)
        for rusher in ["KC_RB1", "KC_RB1", "KC_RB1", "KC_RB1", "KC_RB1", "KC_RB2"]:
            append_play(week, "run", rusher_player_id=rusher)

    for week in range(5, 9):
        for receiver in ["KC_WR1", "KC_WR1", "KC_WR2"]:
            append_play(
                week,
                "pass",
                receiver_player_id=receiver,
                score_differential=-10,
                qtr=4,
                game_seconds_remaining=180,
            )
        append_play(
            week,
            "run",
            rusher_player_id="KC_RB1",
            score_differential=-10,
            qtr=4,
            game_seconds_remaining=180,
        )
        for rusher in ["KC_RB1", "KC_RB2", "KC_RB2", "KC_RB2"]:
            append_play(
                week,
                "run",
                rusher_player_id=rusher,
                score_differential=17,
                qtr=4,
                game_seconds_remaining=500,
            )

    for receiver in ["KC_WR1", "KC_WR1", "KC_WR1", "KC_WR2"]:
        append_play(
            9,
            "pass",
            receiver_player_id=receiver,
            score_differential=-10,
            qtr=4,
            game_seconds_remaining=120,
        )

    return pl.DataFrame(plays)


def make_rosters() -> pl.DataFrame:
    rows = []
    for week in range(1, 10):
        rows.extend(
            [
                {
                    "season": 2024,
                    "week": week,
                    "team": "KC",
                    "player_id": "KC_WR1",
                    "position": "WR",
                },
                {
                    "season": 2024,
                    "week": week,
                    "team": "KC",
                    "player_id": "KC_WR2",
                    "position": "WR",
                },
                {
                    "season": 2024,
                    "week": week,
                    "team": "KC",
                    "player_id": "KC_TE1",
                    "position": "TE",
                },
                {
                    "season": 2024,
                    "week": week,
                    "team": "KC",
                    "player_id": "KC_RB1",
                    "position": "RB",
                },
                {
                    "season": 2024,
                    "week": week,
                    "team": "KC",
                    "player_id": "KC_RB2",
                    "position": "RB",
                },
            ]
        )
    return pl.DataFrame(rows)


def test_compute_trailing_late_profile_moves_pass_rate_and_rank1():
    engine = GameScriptEngine(make_config())

    profile = engine.compute(
        team="KC",
        pbp=make_game_script_pbp(),
        training_seasons=[2024],
        rosters=make_rosters(),
    )

    assert profile.trailing_late_pass_rate_factor > 1.0
    assert profile.trailing_late_target_factors.rank1 > 1.0
    assert profile.trailing_late_target_factors.rank3_plus < 1.0


def test_compute_leading_late_rb_profile_shifts_to_rb2():
    engine = GameScriptEngine(make_config())

    profile = engine.compute(
        team="KC",
        pbp=make_game_script_pbp(),
        training_seasons=[2024],
        rosters=make_rosters(),
    )

    assert profile.leading_late_rb_factors.rb1 < 1.0
    assert profile.leading_late_rb_factors.rb2 > 1.0


def test_target_week_is_excluded():
    engine = GameScriptEngine(make_config())
    pbp = make_game_script_pbp()
    rosters = make_rosters()

    excluded = engine.compute(
        team="KC",
        pbp=pbp,
        training_seasons=[2024],
        target_season=2024,
        week=9,
        rosters=rosters,
    )
    included = engine.compute(
        team="KC",
        pbp=pbp,
        training_seasons=[2024],
        rosters=rosters,
    )

    assert getattr(excluded.diagnostics, "trailing_late_play_count") == 16
    assert getattr(included.diagnostics, "trailing_late_play_count") == 20
    assert excluded.trailing_late_pass_rate_factor < included.trailing_late_pass_rate_factor


def test_missing_clock_column_keeps_pace_neutral():
    engine = GameScriptEngine(make_config())

    profile = engine.compute(
        team="KC",
        pbp=make_game_script_pbp(include_clock=False),
        training_seasons=[2024],
        rosters=make_rosters(),
    )

    assert profile.trailing_late_pace_factor == 1.0

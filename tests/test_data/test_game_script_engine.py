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


def make_drive_local_pace_pbp() -> pl.DataFrame:
    rows = [
        {
            "season": 2024,
            "week": 1,
            "game_id": "2024_01_KC_BUF",
            "drive": 1,
            "posteam": "KC",
            "play_type": "pass",
            "pass_attempt": 1,
            "rush_attempt": 0,
            "receiver_player_id": "KC_WR1",
            "rusher_player_id": None,
            "score_differential": 0,
            "qtr": 2,
            "game_seconds_remaining": 1800,
        },
        {
            "season": 2024,
            "week": 1,
            "game_id": "2024_01_KC_BUF",
            "drive": 1,
            "posteam": "KC",
            "play_type": "run",
            "pass_attempt": 0,
            "rush_attempt": 1,
            "receiver_player_id": None,
            "rusher_player_id": "KC_RB1",
            "score_differential": 0,
            "qtr": 2,
            "game_seconds_remaining": 1770,
        },
        {
            "season": 2024,
            "week": 1,
            "game_id": "2024_01_KC_BUF",
            "drive": 2,
            "posteam": "KC",
            "play_type": "pass",
            "pass_attempt": 1,
            "rush_attempt": 0,
            "receiver_player_id": "KC_WR2",
            "rusher_player_id": None,
            "score_differential": 0,
            "qtr": 2,
            "game_seconds_remaining": 1500,
        },
        {
            "season": 2024,
            "week": 1,
            "game_id": "2024_01_KC_BUF",
            "drive": 2,
            "posteam": "KC",
            "play_type": "run",
            "pass_attempt": 0,
            "rush_attempt": 1,
            "receiver_player_id": None,
            "rusher_player_id": "KC_RB1",
            "score_differential": 0,
            "qtr": 2,
            "game_seconds_remaining": 1470,
        },
        {
            "season": 2024,
            "week": 1,
            "game_id": "2024_01_KC_BUF",
            "drive": 10,
            "posteam": "KC",
            "play_type": "pass",
            "pass_attempt": 1,
            "rush_attempt": 0,
            "receiver_player_id": "KC_WR1",
            "rusher_player_id": None,
            "score_differential": -10,
            "qtr": 4,
            "game_seconds_remaining": 300,
        },
        {
            "season": 2024,
            "week": 1,
            "game_id": "2024_01_KC_BUF",
            "drive": 10,
            "posteam": "KC",
            "play_type": "run",
            "pass_attempt": 0,
            "rush_attempt": 1,
            "receiver_player_id": None,
            "rusher_player_id": "KC_RB1",
            "score_differential": -10,
            "qtr": 4,
            "game_seconds_remaining": 270,
        },
        {
            "season": 2024,
            "week": 1,
            "game_id": "2024_01_KC_BUF",
            "drive": 11,
            "posteam": "KC",
            "play_type": "pass",
            "pass_attempt": 1,
            "rush_attempt": 0,
            "receiver_player_id": "KC_WR2",
            "rusher_player_id": None,
            "score_differential": -10,
            "qtr": 4,
            "game_seconds_remaining": 120,
        },
        {
            "season": 2024,
            "week": 1,
            "game_id": "2024_01_KC_BUF",
            "drive": 11,
            "posteam": "KC",
            "play_type": "run",
            "pass_attempt": 0,
            "rush_attempt": 1,
            "receiver_player_id": None,
            "rusher_player_id": "KC_RB1",
            "score_differential": -10,
            "qtr": 4,
            "game_seconds_remaining": 90,
        },
    ]
    return pl.DataFrame(rows)


def make_cache_regression_pbp(trailing_passes: int) -> pl.DataFrame:
    rows: list[dict] = []
    for idx in range(4):
        rows.append(
            {
                "season": 2024,
                "week": 1,
                "posteam": "KC",
                "play_type": "pass" if idx < 2 else "run",
                "pass_attempt": 1 if idx < 2 else 0,
                "rush_attempt": 0 if idx < 2 else 1,
                "receiver_player_id": "KC_WR1" if idx < 2 else None,
                "rusher_player_id": None if idx < 2 else "KC_RB1",
                "score_differential": 0,
                "qtr": 2,
                "game_seconds_remaining": 1800 - idx * 30,
            }
        )
    for idx in range(4):
        is_pass = idx < trailing_passes
        rows.append(
            {
                "season": 2024,
                "week": 1,
                "posteam": "KC",
                "play_type": "pass" if is_pass else "run",
                "pass_attempt": 1 if is_pass else 0,
                "rush_attempt": 0 if is_pass else 1,
                "receiver_player_id": "KC_WR1" if is_pass else None,
                "rusher_player_id": None if is_pass else "KC_RB1",
                "score_differential": -10,
                "qtr": 4,
                "game_seconds_remaining": 300 - idx * 30,
            }
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

    assert excluded.diagnostics.trailing_late_play_count == 16
    assert included.diagnostics.trailing_late_play_count == 20
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
    assert profile.diagnostics.trailing_late_pace_ratio == 1.0


def test_diagnostics_contract_is_typed_and_populated():
    engine = GameScriptEngine(make_config())

    profile = engine.compute(
        team="KC",
        pbp=make_game_script_pbp(),
        training_seasons=[2024],
        rosters=make_rosters(),
    )

    assert profile.diagnostics.trailing_late_play_count == 20
    assert profile.diagnostics.trailing_late_pass_rate_ratio > 1.0
    assert profile.diagnostics.trailing_late_pace_ratio == 1.0
    assert profile.diagnostics.trailing_late_rank1_ratio > 1.0
    assert profile.diagnostics.trailing_late_rank2_ratio < 1.0
    assert profile.diagnostics.trailing_late_rank3_plus_ratio < 1.0
    assert profile.diagnostics.leading_late_rb_play_count == 16
    assert profile.diagnostics.leading_late_rb1_ratio < 1.0
    assert profile.diagnostics.leading_late_rb2_ratio > 1.0
    assert profile.diagnostics.leading_late_rb3_plus_ratio == 1.0


def test_empty_data_returns_typed_default_diagnostics():
    engine = GameScriptEngine(make_config())
    empty_pbp = pl.DataFrame(
        {
            "season": [],
            "week": [],
            "posteam": [],
            "play_type": [],
            "pass_attempt": [],
            "rush_attempt": [],
            "receiver_player_id": [],
            "rusher_player_id": [],
            "score_differential": [],
            "qtr": [],
        },
        schema={
            "season": pl.Int64,
            "week": pl.Int64,
            "posteam": pl.Utf8,
            "play_type": pl.Utf8,
            "pass_attempt": pl.Int64,
            "rush_attempt": pl.Int64,
            "receiver_player_id": pl.Utf8,
            "rusher_player_id": pl.Utf8,
            "score_differential": pl.Int64,
            "qtr": pl.Int64,
        },
    )

    profile = engine.compute(team="KC", pbp=empty_pbp, training_seasons=[2024])

    assert profile.trailing_late_pass_rate_factor == 1.0
    assert profile.trailing_late_pace_factor == 1.0
    assert profile.diagnostics.trailing_late_play_count == 0
    assert profile.diagnostics.trailing_late_pass_rate_ratio == 1.0
    assert profile.diagnostics.trailing_late_pace_ratio == 1.0
    assert profile.diagnostics.trailing_late_rank1_ratio == 1.0
    assert profile.diagnostics.trailing_late_rank2_ratio == 1.0
    assert profile.diagnostics.trailing_late_rank3_plus_ratio == 1.0
    assert profile.diagnostics.leading_late_rb_play_count == 0
    assert profile.diagnostics.leading_late_rb1_ratio == 1.0
    assert profile.diagnostics.leading_late_rb2_ratio == 1.0
    assert profile.diagnostics.leading_late_rb3_plus_ratio == 1.0


def test_pace_learning_ignores_opponent_possession_gaps_between_drives():
    engine = GameScriptEngine(make_config())

    profile = engine.compute(
        team="KC",
        pbp=make_drive_local_pace_pbp(),
        training_seasons=[2024],
        rosters=make_rosters(),
    )

    assert profile.trailing_late_pace_factor == 1.0
    assert profile.diagnostics.trailing_late_pace_ratio == 1.0
    assert profile.diagnostics.trailing_late_pace_sample == 2


def test_compute_cache_does_not_reuse_stale_profile_for_different_explicit_frames():
    engine = GameScriptEngine(make_config())
    rosters = make_rosters()

    pass_heavy = engine.compute(
        team="KC",
        pbp=make_cache_regression_pbp(trailing_passes=4),
        training_seasons=[2024],
        target_season=2024,
        week=2,
        rosters=rosters,
    )
    run_heavy = engine.compute(
        team="KC",
        pbp=make_cache_regression_pbp(trailing_passes=0),
        training_seasons=[2024],
        target_season=2024,
        week=2,
        rosters=rosters,
    )

    assert pass_heavy.trailing_late_pass_rate_factor > run_heavy.trailing_late_pass_rate_factor
    assert pass_heavy.diagnostics.trailing_late_pass_rate_ratio > run_heavy.diagnostics.trailing_late_pass_rate_ratio

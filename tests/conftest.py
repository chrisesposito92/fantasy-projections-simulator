import polars as pl
import numpy as np
import pytest


@pytest.fixture
def sample_pbp() -> pl.DataFrame:
    """Minimal PBP data mimicking nflreadpy output.

    Contains 20 plays: 12 passes, 8 runs across 2 teams (KC, BUF).
    Enough to compute basic distributions but small enough to verify by hand.
    """
    plays = [
        # KC passing plays (8)
        {"season": 2024, "week": 1, "game_id": "2024_01_KC_BUF", "play_type": "pass", "posteam": "KC", "defteam": "BUF", "down": 1, "ydstogo": 10, "yardline_100": 75, "score_differential": 0, "qtr": 1, "yards_gained": 12, "complete_pass": 1, "pass_attempt": 1, "rush_attempt": 0, "interception": 0, "fumble_lost": 0, "sack": 0, "touchdown": 0, "penalty": 0, "penalty_yards": 0, "passer_player_id": "PM15", "receiver_player_id": "TK87", "rusher_player_id": None},
        {"season": 2024, "week": 1, "game_id": "2024_01_KC_BUF", "play_type": "pass", "posteam": "KC", "defteam": "BUF", "down": 2, "ydstogo": 7, "yardline_100": 60, "score_differential": 0, "qtr": 1, "yards_gained": 0, "complete_pass": 0, "pass_attempt": 1, "rush_attempt": 0, "interception": 0, "fumble_lost": 0, "sack": 0, "touchdown": 0, "penalty": 0, "penalty_yards": 0, "passer_player_id": "PM15", "receiver_player_id": "TK87", "rusher_player_id": None},
        {"season": 2024, "week": 1, "game_id": "2024_01_KC_BUF", "play_type": "pass", "posteam": "KC", "defteam": "BUF", "down": 1, "ydstogo": 10, "yardline_100": 45, "score_differential": 7, "qtr": 2, "yards_gained": 45, "complete_pass": 1, "pass_attempt": 1, "rush_attempt": 0, "interception": 0, "fumble_lost": 0, "sack": 0, "touchdown": 1, "penalty": 0, "penalty_yards": 0, "passer_player_id": "PM15", "receiver_player_id": "RE11", "rusher_player_id": None},
        {"season": 2024, "week": 1, "game_id": "2024_01_KC_BUF", "play_type": "pass", "posteam": "KC", "defteam": "BUF", "down": 3, "ydstogo": 5, "yardline_100": 50, "score_differential": -7, "qtr": 3, "yards_gained": 8, "complete_pass": 1, "pass_attempt": 1, "rush_attempt": 0, "interception": 0, "fumble_lost": 0, "sack": 0, "touchdown": 0, "penalty": 0, "penalty_yards": 0, "passer_player_id": "PM15", "receiver_player_id": "TK87", "rusher_player_id": None},
        {"season": 2024, "week": 1, "game_id": "2024_01_KC_BUF", "play_type": "pass", "posteam": "KC", "defteam": "BUF", "down": 2, "ydstogo": 10, "yardline_100": 30, "score_differential": -7, "qtr": 4, "yards_gained": -5, "complete_pass": 0, "pass_attempt": 1, "rush_attempt": 0, "interception": 0, "fumble_lost": 0, "sack": 1, "touchdown": 0, "penalty": 0, "penalty_yards": 0, "passer_player_id": "PM15", "receiver_player_id": None, "rusher_player_id": None},
        {"season": 2024, "week": 1, "game_id": "2024_01_KC_BUF", "play_type": "pass", "posteam": "KC", "defteam": "BUF", "down": 1, "ydstogo": 10, "yardline_100": 55, "score_differential": 0, "qtr": 2, "yards_gained": 0, "complete_pass": 0, "pass_attempt": 1, "rush_attempt": 0, "interception": 1, "fumble_lost": 0, "sack": 0, "touchdown": 0, "penalty": 0, "penalty_yards": 0, "passer_player_id": "PM15", "receiver_player_id": "TK87", "rusher_player_id": None},
        {"season": 2024, "week": 1, "game_id": "2024_01_KC_BUF", "play_type": "pass", "posteam": "KC", "defteam": "BUF", "down": 1, "ydstogo": 10, "yardline_100": 15, "score_differential": 3, "qtr": 3, "yards_gained": 15, "complete_pass": 1, "pass_attempt": 1, "rush_attempt": 0, "interception": 0, "fumble_lost": 0, "sack": 0, "touchdown": 1, "penalty": 0, "penalty_yards": 0, "passer_player_id": "PM15", "receiver_player_id": "RE11", "rusher_player_id": None},
        {"season": 2024, "week": 1, "game_id": "2024_01_KC_BUF", "play_type": "pass", "posteam": "KC", "defteam": "BUF", "down": 2, "ydstogo": 3, "yardline_100": 40, "score_differential": 10, "qtr": 4, "yards_gained": 6, "complete_pass": 1, "pass_attempt": 1, "rush_attempt": 0, "interception": 0, "fumble_lost": 0, "sack": 0, "touchdown": 0, "penalty": 0, "penalty_yards": 0, "passer_player_id": "PM15", "receiver_player_id": "TK87", "rusher_player_id": None},
        # KC rushing plays (4)
        {"season": 2024, "week": 1, "game_id": "2024_01_KC_BUF", "play_type": "run", "posteam": "KC", "defteam": "BUF", "down": 1, "ydstogo": 10, "yardline_100": 70, "score_differential": 0, "qtr": 1, "yards_gained": 5, "complete_pass": 0, "pass_attempt": 0, "rush_attempt": 1, "interception": 0, "fumble_lost": 0, "sack": 0, "touchdown": 0, "penalty": 0, "penalty_yards": 0, "passer_player_id": None, "receiver_player_id": None, "rusher_player_id": "IP01"},
        {"season": 2024, "week": 1, "game_id": "2024_01_KC_BUF", "play_type": "run", "posteam": "KC", "defteam": "BUF", "down": 2, "ydstogo": 5, "yardline_100": 35, "score_differential": 7, "qtr": 2, "yards_gained": -2, "complete_pass": 0, "pass_attempt": 0, "rush_attempt": 1, "interception": 0, "fumble_lost": 0, "sack": 0, "touchdown": 0, "penalty": 0, "penalty_yards": 0, "passer_player_id": None, "receiver_player_id": None, "rusher_player_id": "IP01"},
        {"season": 2024, "week": 1, "game_id": "2024_01_KC_BUF", "play_type": "run", "posteam": "KC", "defteam": "BUF", "down": 1, "ydstogo": 10, "yardline_100": 5, "score_differential": 3, "qtr": 3, "yards_gained": 5, "complete_pass": 0, "pass_attempt": 0, "rush_attempt": 1, "interception": 0, "fumble_lost": 1, "sack": 0, "touchdown": 1, "penalty": 0, "penalty_yards": 0, "passer_player_id": None, "receiver_player_id": None, "rusher_player_id": "IP01"},
        {"season": 2024, "week": 1, "game_id": "2024_01_KC_BUF", "play_type": "run", "posteam": "KC", "defteam": "BUF", "down": 1, "ydstogo": 10, "yardline_100": 50, "score_differential": 10, "qtr": 4, "yards_gained": 12, "complete_pass": 0, "pass_attempt": 0, "rush_attempt": 1, "interception": 0, "fumble_lost": 0, "sack": 0, "touchdown": 0, "penalty": 0, "penalty_yards": 0, "passer_player_id": None, "receiver_player_id": None, "rusher_player_id": "IP01"},
        # BUF passing plays (4)
        {"season": 2024, "week": 1, "game_id": "2024_01_KC_BUF", "play_type": "pass", "posteam": "BUF", "defteam": "KC", "down": 1, "ydstogo": 10, "yardline_100": 75, "score_differential": 0, "qtr": 1, "yards_gained": 18, "complete_pass": 1, "pass_attempt": 1, "rush_attempt": 0, "interception": 0, "fumble_lost": 0, "sack": 0, "touchdown": 0, "penalty": 0, "penalty_yards": 0, "passer_player_id": "JA17", "receiver_player_id": "SD14", "rusher_player_id": None},
        {"season": 2024, "week": 1, "game_id": "2024_01_KC_BUF", "play_type": "pass", "posteam": "BUF", "defteam": "KC", "down": 2, "ydstogo": 8, "yardline_100": 40, "score_differential": -7, "qtr": 2, "yards_gained": 5, "complete_pass": 1, "pass_attempt": 1, "rush_attempt": 0, "interception": 0, "fumble_lost": 0, "sack": 0, "touchdown": 0, "penalty": 0, "penalty_yards": 0, "passer_player_id": "JA17", "receiver_player_id": "SD14", "rusher_player_id": None},
        {"season": 2024, "week": 1, "game_id": "2024_01_KC_BUF", "play_type": "pass", "posteam": "BUF", "defteam": "KC", "down": 3, "ydstogo": 12, "yardline_100": 65, "score_differential": -14, "qtr": 4, "yards_gained": 20, "complete_pass": 1, "pass_attempt": 1, "rush_attempt": 0, "interception": 0, "fumble_lost": 0, "sack": 0, "touchdown": 0, "penalty": 0, "penalty_yards": 0, "passer_player_id": "JA17", "receiver_player_id": "SD14", "rusher_player_id": None},
        {"season": 2024, "week": 1, "game_id": "2024_01_KC_BUF", "play_type": "pass", "posteam": "BUF", "defteam": "KC", "down": 1, "ydstogo": 10, "yardline_100": 10, "score_differential": -7, "qtr": 3, "yards_gained": 10, "complete_pass": 1, "pass_attempt": 1, "rush_attempt": 0, "interception": 0, "fumble_lost": 0, "sack": 0, "touchdown": 1, "penalty": 0, "penalty_yards": 0, "passer_player_id": "JA17", "receiver_player_id": "SD14", "rusher_player_id": None},
        # BUF rushing plays (4)
        {"season": 2024, "week": 1, "game_id": "2024_01_KC_BUF", "play_type": "run", "posteam": "BUF", "defteam": "KC", "down": 1, "ydstogo": 10, "yardline_100": 60, "score_differential": 0, "qtr": 1, "yards_gained": 7, "complete_pass": 0, "pass_attempt": 0, "rush_attempt": 1, "interception": 0, "fumble_lost": 0, "sack": 0, "touchdown": 0, "penalty": 0, "penalty_yards": 0, "passer_player_id": None, "receiver_player_id": None, "rusher_player_id": "JC02"},
        {"season": 2024, "week": 1, "game_id": "2024_01_KC_BUF", "play_type": "run", "posteam": "BUF", "defteam": "KC", "down": 2, "ydstogo": 3, "yardline_100": 25, "score_differential": -7, "qtr": 2, "yards_gained": 3, "complete_pass": 0, "pass_attempt": 0, "rush_attempt": 1, "interception": 0, "fumble_lost": 0, "sack": 0, "touchdown": 0, "penalty": 0, "penalty_yards": 0, "passer_player_id": None, "receiver_player_id": None, "rusher_player_id": "JC02"},
        {"season": 2024, "week": 1, "game_id": "2024_01_KC_BUF", "play_type": "run", "posteam": "BUF", "defteam": "KC", "down": 1, "ydstogo": 10, "yardline_100": 45, "score_differential": -7, "qtr": 3, "yards_gained": 1, "complete_pass": 0, "pass_attempt": 0, "rush_attempt": 1, "interception": 0, "fumble_lost": 0, "sack": 0, "touchdown": 0, "penalty": 0, "penalty_yards": 0, "passer_player_id": None, "receiver_player_id": None, "rusher_player_id": "JC02"},
        {"season": 2024, "week": 1, "game_id": "2024_01_KC_BUF", "play_type": "run", "posteam": "BUF", "defteam": "KC", "down": 1, "ydstogo": 10, "yardline_100": 80, "score_differential": -14, "qtr": 4, "yards_gained": 4, "complete_pass": 0, "pass_attempt": 0, "rush_attempt": 1, "interception": 0, "fumble_lost": 0, "sack": 0, "touchdown": 0, "penalty": 0, "penalty_yards": 0, "passer_player_id": None, "receiver_player_id": None, "rusher_player_id": "JC02"},
    ]

    return pl.DataFrame(plays)


@pytest.fixture
def sample_schedules() -> pl.DataFrame:
    return pl.DataFrame([
        {"season": 2024, "week": 1, "game_id": "2024_01_KC_BUF", "home_team": "KC", "away_team": "BUF", "home_score": 27, "away_score": 20, "spread_line": -3.0, "total_line": 48.5},
        {"season": 2024, "week": 2, "game_id": "2024_02_KC_LV", "home_team": "KC", "away_team": "LV", "home_score": 31, "away_score": 17, "spread_line": -7.0, "total_line": 45.0},
    ])


@pytest.fixture
def sample_kickoffs() -> pl.DataFrame:
    return pl.DataFrame([
        {"season": 2024, "play_type": "kickoff", "posteam": "KC", "kick_distance": 65, "return_yards": 22, "touchback": 0, "yardline_100": 78},
        {"season": 2024, "play_type": "kickoff", "posteam": "KC", "kick_distance": 65, "return_yards": 0, "touchback": 1, "yardline_100": 75},
        {"season": 2024, "play_type": "kickoff", "posteam": "BUF", "kick_distance": 63, "return_yards": 28, "touchback": 0, "yardline_100": 72},
        {"season": 2024, "play_type": "kickoff", "posteam": "BUF", "kick_distance": 65, "return_yards": 0, "touchback": 1, "yardline_100": 75},
        {"season": 2024, "play_type": "kickoff", "posteam": "BUF", "kick_distance": 64, "return_yards": 0, "touchback": 1, "yardline_100": 75},
    ])


@pytest.fixture
def sample_field_goals() -> pl.DataFrame:
    return pl.DataFrame([
        {"season": 2024, "play_type": "field_goal", "posteam": "KC", "kick_distance": 32, "field_goal_result": "made"},
        {"season": 2024, "play_type": "field_goal", "posteam": "KC", "kick_distance": 48, "field_goal_result": "made"},
        {"season": 2024, "play_type": "field_goal", "posteam": "KC", "kick_distance": 55, "field_goal_result": "missed"},
        {"season": 2024, "play_type": "field_goal", "posteam": "BUF", "kick_distance": 27, "field_goal_result": "made"},
        {"season": 2024, "play_type": "field_goal", "posteam": "BUF", "kick_distance": 43, "field_goal_result": "made"},
        {"season": 2024, "play_type": "field_goal", "posteam": "BUF", "kick_distance": 51, "field_goal_result": "missed"},
    ])

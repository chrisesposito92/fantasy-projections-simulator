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


@pytest.fixture
def sample_rosters() -> pl.DataFrame:
    """Minimal weekly roster data for KC and BUF."""
    rows = []
    for week in range(1, 4):
        rows.extend([
            {"season": 2024, "week": week, "player_id": "PM15", "player_name": "P.Mahomes", "position": "QB", "team": "KC", "status": "ACT"},
            {"season": 2024, "week": week, "player_id": "TK87", "player_name": "T.Kelce", "position": "TE", "team": "KC", "status": "ACT"},
            {"season": 2024, "week": week, "player_id": "RE11", "player_name": "R.Rice", "position": "WR", "team": "KC", "status": "ACT"},
            {"season": 2024, "week": week, "player_id": "IP01", "player_name": "I.Pacheco", "position": "RB", "team": "KC", "status": "ACT"},
            {"season": 2024, "week": week, "player_id": "JA17", "player_name": "J.Allen", "position": "QB", "team": "BUF", "status": "ACT"},
            {"season": 2024, "week": week, "player_id": "SD14", "player_name": "S.Diggs", "position": "WR", "team": "BUF", "status": "ACT"},
            {"season": 2024, "week": week, "player_id": "JC02", "player_name": "J.Cook", "position": "RB", "team": "BUF", "status": "ACT"},
        ])
    return pl.DataFrame(rows)


@pytest.fixture
def expanded_pbp() -> pl.DataFrame:
    """Larger PBP sample for player builder tests — 60 plays per team."""
    rng = np.random.RandomState(42)
    plays = []

    # KC: 40 passes, 20 runs
    for i in range(40):
        receiver = rng.choice(["TK87", "RE11", "IP01"], p=[0.40, 0.35, 0.25])
        complete = int(rng.random() < 0.65)
        yards = int(rng.normal(8, 6)) if complete else 0
        plays.append({
            "season": 2024, "week": (i % 3) + 1, "game_id": f"2024_0{(i%3)+1}_KC",
            "play_type": "pass", "posteam": "KC", "defteam": "BUF",
            "down": rng.choice([1,2,3]), "ydstogo": 10, "yardline_100": rng.randint(20, 80),
            "score_differential": 0, "qtr": rng.choice([1,2,3,4]),
            "yards_gained": yards, "complete_pass": complete,
            "pass_attempt": 1, "rush_attempt": 0,
            "interception": 0, "fumble_lost": 0, "sack": 0,
            "touchdown": int(yards > 0 and rng.random() < 0.05),
            "penalty": 0, "penalty_yards": 0,
            "passer_player_id": "PM15", "receiver_player_id": receiver,
            "rusher_player_id": None,
        })
    for i in range(20):
        rusher = rng.choice(["IP01"], p=[1.0])
        yards = int(rng.normal(4.5, 3))
        plays.append({
            "season": 2024, "week": (i % 3) + 1, "game_id": f"2024_0{(i%3)+1}_KC",
            "play_type": "run", "posteam": "KC", "defteam": "BUF",
            "down": rng.choice([1,2,3]), "ydstogo": 10, "yardline_100": rng.randint(20, 80),
            "score_differential": 0, "qtr": rng.choice([1,2,3,4]),
            "yards_gained": yards, "complete_pass": 0,
            "pass_attempt": 0, "rush_attempt": 1,
            "interception": 0, "fumble_lost": 0, "sack": 0,
            "touchdown": int(rng.random() < 0.05),
            "penalty": 0, "penalty_yards": 0,
            "passer_player_id": None, "receiver_player_id": None,
            "rusher_player_id": rusher,
        })

    # BUF: 30 passes, 30 runs
    for i in range(30):
        receiver = rng.choice(["SD14", "JC02"], p=[0.70, 0.30])
        complete = int(rng.random() < 0.62)
        yards = int(rng.normal(9, 7)) if complete else 0
        plays.append({
            "season": 2024, "week": (i % 3) + 1, "game_id": f"2024_0{(i%3)+1}_BUF",
            "play_type": "pass", "posteam": "BUF", "defteam": "KC",
            "down": rng.choice([1,2,3]), "ydstogo": 10, "yardline_100": rng.randint(20, 80),
            "score_differential": 0, "qtr": rng.choice([1,2,3,4]),
            "yards_gained": yards, "complete_pass": complete,
            "pass_attempt": 1, "rush_attempt": 0,
            "interception": 0, "fumble_lost": 0, "sack": 0,
            "touchdown": int(yards > 0 and rng.random() < 0.05),
            "penalty": 0, "penalty_yards": 0,
            "passer_player_id": "JA17", "receiver_player_id": receiver,
            "rusher_player_id": None,
        })
    for i in range(30):
        yards = int(rng.normal(4.2, 3.5))
        plays.append({
            "season": 2024, "week": (i % 3) + 1, "game_id": f"2024_0{(i%3)+1}_BUF",
            "play_type": "run", "posteam": "BUF", "defteam": "KC",
            "down": rng.choice([1,2,3]), "ydstogo": 10, "yardline_100": rng.randint(20, 80),
            "score_differential": 0, "qtr": rng.choice([1,2,3,4]),
            "yards_gained": yards, "complete_pass": 0,
            "pass_attempt": 0, "rush_attempt": 1,
            "interception": 0, "fumble_lost": 0, "sack": 0,
            "touchdown": int(rng.random() < 0.05),
            "penalty": 0, "penalty_yards": 0,
            "passer_player_id": None, "receiver_player_id": None,
            "rusher_player_id": "JC02",
        })

    return pl.DataFrame(plays)


@pytest.fixture
def rz_pbp() -> pl.DataFrame:
    """PBP with red zone plays (yardline_100 <= 20) for testing red zone metrics."""
    plays = []
    base = {
        "season": 2024, "week": 1, "game_id": "2024_01_KC_BUF",
        "down": 1, "ydstogo": 10, "score_differential": 0, "qtr": 1,
        "pass_attempt": 0, "rush_attempt": 0,
        "interception": 0, "fumble_lost": 0, "sack": 0,
        "touchdown": 0, "penalty": 0, "penalty_yards": 0,
        "passer_player_id": None, "receiver_player_id": None,
        "rusher_player_id": None,
    }

    # KC: 5 non-rz passes (yardline_100=50, to TK87)
    for i in range(5):
        plays.append({
            **base, "play_type": "pass", "posteam": "KC", "defteam": "BUF",
            "yardline_100": 50, "yards_gained": 8, "complete_pass": 1,
            "pass_attempt": 1, "passer_player_id": "PM15",
            "receiver_player_id": "TK87", "air_yards": 6,
        })

    # KC: 5 rz passes (yardline_100=15, to RE11)
    for i in range(5):
        plays.append({
            **base, "play_type": "pass", "posteam": "KC", "defteam": "BUF",
            "yardline_100": 15, "yards_gained": 10, "complete_pass": 1,
            "pass_attempt": 1, "passer_player_id": "PM15",
            "receiver_player_id": "RE11", "air_yards": 8,
        })

    # KC: 5 non-rz runs (yardline_100=50, IP01)
    for i in range(5):
        plays.append({
            **base, "play_type": "run", "posteam": "KC", "defteam": "BUF",
            "yardline_100": 50, "yards_gained": 4, "complete_pass": 0,
            "rush_attempt": 1, "rusher_player_id": "IP01", "air_yards": None,
        })

    # KC: 3 rz runs (yardline_100=10, IP01)
    for i in range(3):
        plays.append({
            **base, "play_type": "run", "posteam": "KC", "defteam": "BUF",
            "yardline_100": 10, "yards_gained": 3, "complete_pass": 0,
            "rush_attempt": 1, "rusher_player_id": "IP01", "air_yards": None,
        })

    # BUF: 2 non-rz passes (yardline_100=40, to SD14)
    for i in range(2):
        plays.append({
            **base, "play_type": "pass", "posteam": "BUF", "defteam": "KC",
            "yardline_100": 40, "yards_gained": 12, "complete_pass": 1,
            "pass_attempt": 1, "passer_player_id": "JA17",
            "receiver_player_id": "SD14", "air_yards": 10,
        })

    # BUF: 3 rz passes (yardline_100=18, to SD14)
    for i in range(3):
        plays.append({
            **base, "play_type": "pass", "posteam": "BUF", "defteam": "KC",
            "yardline_100": 18, "yards_gained": 8, "complete_pass": 1,
            "pass_attempt": 1, "passer_player_id": "JA17",
            "receiver_player_id": "SD14", "air_yards": 7,
        })

    # BUF: 3 non-rz runs (yardline_100=50, JC02)
    for i in range(3):
        plays.append({
            **base, "play_type": "run", "posteam": "BUF", "defteam": "KC",
            "yardline_100": 50, "yards_gained": 5, "complete_pass": 0,
            "rush_attempt": 1, "rusher_player_id": "JC02", "air_yards": None,
        })

    # BUF: 2 rz runs (yardline_100=8, JC02)
    for i in range(2):
        plays.append({
            **base, "play_type": "run", "posteam": "BUF", "defteam": "KC",
            "yardline_100": 8, "yards_gained": 2, "complete_pass": 0,
            "rush_attempt": 1, "rusher_player_id": "JC02", "air_yards": None,
        })

    return pl.DataFrame(plays)


@pytest.fixture
def air_yards_pbp() -> pl.DataFrame:
    """PBP with air_yards data for testing air yards share computation."""
    plays = []
    base = {
        "season": 2024, "week": 1, "game_id": "2024_01_KC_BUF",
        "posteam": "KC", "defteam": "BUF",
        "down": 1, "ydstogo": 10, "yardline_100": 50,
        "score_differential": 0, "qtr": 1,
        "pass_attempt": 0, "rush_attempt": 0,
        "interception": 0, "fumble_lost": 0, "sack": 0,
        "touchdown": 0, "penalty": 0, "penalty_yards": 0,
        "passer_player_id": None, "receiver_player_id": None,
        "rusher_player_id": None,
    }

    # KC: 6 passes to TK87 with air_yards=10
    for i in range(6):
        plays.append({
            **base, "play_type": "pass", "yards_gained": 12,
            "complete_pass": 1, "pass_attempt": 1,
            "passer_player_id": "PM15", "receiver_player_id": "TK87",
            "air_yards": 10,
        })

    # KC: 3 passes to RE11 with air_yards=10
    for i in range(3):
        plays.append({
            **base, "play_type": "pass", "yards_gained": 15,
            "complete_pass": 1, "pass_attempt": 1,
            "passer_player_id": "PM15", "receiver_player_id": "RE11",
            "air_yards": 10,
        })

    # KC: 1 pass to IP01 with air_yards=10
    plays.append({
        **base, "play_type": "pass", "yards_gained": 5,
        "complete_pass": 1, "pass_attempt": 1,
        "passer_player_id": "PM15", "receiver_player_id": "IP01",
        "air_yards": 10,
    })

    # KC: 5 runs (no air_yards)
    for i in range(5):
        plays.append({
            **base, "play_type": "run", "yards_gained": 4,
            "complete_pass": 0, "rush_attempt": 1,
            "rusher_player_id": "IP01", "air_yards": None,
        })

    return pl.DataFrame(plays)


@pytest.fixture
def scramble_pbp() -> pl.DataFrame:
    """PBP for testing QB scramble rate and scramble yards distribution."""
    plays = []
    base = {
        "season": 2024, "week": 1, "game_id": "2024_01_KC_BUF",
        "posteam": "BUF", "defteam": "KC",
        "down": 1, "ydstogo": 10, "yardline_100": 50,
        "score_differential": 0, "qtr": 1,
        "pass_attempt": 0, "rush_attempt": 0,
        "interception": 0, "fumble_lost": 0, "sack": 0,
        "touchdown": 0, "penalty": 0, "penalty_yards": 0,
        "passer_player_id": None, "receiver_player_id": None,
        "rusher_player_id": None,
    }

    # BUF: JA17 10 pass plays
    for i in range(10):
        plays.append({
            **base, "play_type": "pass", "yards_gained": 8,
            "complete_pass": 1, "pass_attempt": 1,
            "passer_player_id": "JA17", "receiver_player_id": "SD14",
        })

    # BUF: JA17 3 rush plays (scrambles)
    for yards in [6, 8, 10]:
        plays.append({
            **base, "play_type": "run", "yards_gained": yards,
            "complete_pass": 0, "rush_attempt": 1,
            "rusher_player_id": "JA17",
        })

    # BUF: JC02 7 rush plays
    for i in range(7):
        plays.append({
            **base, "play_type": "run", "yards_gained": 5,
            "complete_pass": 0, "rush_attempt": 1,
            "rusher_player_id": "JC02",
        })

    return pl.DataFrame(plays)


@pytest.fixture
def traded_player_rosters() -> pl.DataFrame:
    """Season 2025 roster data for testing traded player team assignment.

    Contains:
    - KC standard players (QB, TE, WR, RB, K) — all ACT weeks 1-3
    - HOU players including JM28 (J.Mixon, traded from CIN) and ROOK1 (no PBP history)
    - IR01 (KC RB, IR status) — should be excluded by status filtering
    - PNT1 (KC P, ACT) — should be excluded by position filtering
    """
    rows = []
    for week in range(1, 4):
        rows.extend([
            # KC players
            {"season": 2025, "week": week, "player_id": "PM15", "player_name": "P.Mahomes", "position": "QB", "team": "KC", "status": "ACT"},
            {"season": 2025, "week": week, "player_id": "TK87", "player_name": "T.Kelce", "position": "TE", "team": "KC", "status": "ACT"},
            {"season": 2025, "week": week, "player_id": "RE11", "player_name": "R.Rice", "position": "WR", "team": "KC", "status": "ACT"},
            {"season": 2025, "week": week, "player_id": "IP01", "player_name": "I.Pacheco", "position": "RB", "team": "KC", "status": "ACT"},
            {"season": 2025, "week": week, "player_id": "KC_K", "player_name": "H.Butker", "position": "K", "team": "KC", "status": "ACT"},
            # KC IR and punter (should be excluded)
            {"season": 2025, "week": week, "player_id": "IR01", "player_name": "I.Injured", "position": "RB", "team": "KC", "status": "IR"},
            {"season": 2025, "week": week, "player_id": "PNT1", "player_name": "P.Punter", "position": "P", "team": "KC", "status": "ACT"},
            # HOU players
            {"season": 2025, "week": week, "player_id": "JA17", "player_name": "J.Allen", "position": "QB", "team": "HOU", "status": "ACT"},
            {"season": 2025, "week": week, "player_id": "SD14", "player_name": "S.Diggs", "position": "WR", "team": "HOU", "status": "ACT"},
            {"season": 2025, "week": week, "player_id": "JM28", "player_name": "J.Mixon", "position": "RB", "team": "HOU", "status": "ACT"},
            {"season": 2025, "week": week, "player_id": "HOU_K", "player_name": "K.Fairbairn", "position": "K", "team": "HOU", "status": "ACT"},
            {"season": 2025, "week": week, "player_id": "ROOK1", "player_name": "R.Rookie", "position": "WR", "team": "HOU", "status": "ACT"},
        ])
    return pl.DataFrame(rows)


@pytest.fixture
def traded_player_pbp() -> pl.DataFrame:
    """Season 2024 PBP training data for traded player tests.

    Contains:
    - KC: 20 passes (PM15 -> TK87/RE11 ~55/45 split), 10 runs (IP01)
    - CIN: 15 passes (JA17 -> SD14), 10 runs (JM28 on CIN — his OLD team),
           5 runs (RET99 — retired, not on any 2025 roster)
    Note: JM28 has CIN as posteam here; ROOK1 has no PBP history at all.
    """
    rng = np.random.RandomState(99)
    plays = []

    # KC: 20 passes (PM15 -> TK87/RE11, ~55/45 split)
    for i in range(20):
        receiver = rng.choice(["TK87", "RE11"], p=[0.55, 0.45])
        complete = int(rng.random() < 0.65)
        yards = int(rng.normal(8, 6)) if complete else 0
        plays.append({
            "season": 2024, "week": (i % 3) + 1, "game_id": f"2024_0{(i%3)+1}_KC_CIN",
            "play_type": "pass", "posteam": "KC", "defteam": "CIN",
            "down": int(rng.choice([1, 2, 3])), "ydstogo": 10, "yardline_100": int(rng.randint(20, 80)),
            "score_differential": 0, "qtr": int(rng.choice([1, 2, 3, 4])),
            "yards_gained": yards, "complete_pass": complete,
            "pass_attempt": 1, "rush_attempt": 0,
            "interception": 0, "fumble_lost": 0, "sack": 0,
            "touchdown": int(yards > 0 and rng.random() < 0.05),
            "penalty": 0, "penalty_yards": 0,
            "passer_player_id": "PM15", "receiver_player_id": receiver,
            "rusher_player_id": None,
        })

    # KC: 10 runs (IP01)
    for i in range(10):
        yards = int(rng.normal(4.5, 3))
        plays.append({
            "season": 2024, "week": (i % 3) + 1, "game_id": f"2024_0{(i%3)+1}_KC_CIN",
            "play_type": "run", "posteam": "KC", "defteam": "CIN",
            "down": int(rng.choice([1, 2, 3])), "ydstogo": 10, "yardline_100": int(rng.randint(20, 80)),
            "score_differential": 0, "qtr": int(rng.choice([1, 2, 3, 4])),
            "yards_gained": yards, "complete_pass": 0,
            "pass_attempt": 0, "rush_attempt": 1,
            "interception": 0, "fumble_lost": 0, "sack": 0,
            "touchdown": int(rng.random() < 0.05),
            "penalty": 0, "penalty_yards": 0,
            "passer_player_id": None, "receiver_player_id": None,
            "rusher_player_id": "IP01",
        })

    # CIN: 15 passes (JA17 -> SD14)
    for i in range(15):
        complete = int(rng.random() < 0.62)
        yards = int(rng.normal(9, 7)) if complete else 0
        plays.append({
            "season": 2024, "week": (i % 3) + 1, "game_id": f"2024_0{(i%3)+1}_CIN_KC",
            "play_type": "pass", "posteam": "CIN", "defteam": "KC",
            "down": int(rng.choice([1, 2, 3])), "ydstogo": 10, "yardline_100": int(rng.randint(20, 80)),
            "score_differential": 0, "qtr": int(rng.choice([1, 2, 3, 4])),
            "yards_gained": yards, "complete_pass": complete,
            "pass_attempt": 1, "rush_attempt": 0,
            "interception": 0, "fumble_lost": 0, "sack": 0,
            "touchdown": int(yards > 0 and rng.random() < 0.05),
            "penalty": 0, "penalty_yards": 0,
            "passer_player_id": "JA17", "receiver_player_id": "SD14",
            "rusher_player_id": None,
        })

    # CIN: 10 runs (JM28 — his old team before trade to HOU)
    for i in range(10):
        yards = int(rng.normal(4.2, 3.5))
        plays.append({
            "season": 2024, "week": (i % 3) + 1, "game_id": f"2024_0{(i%3)+1}_CIN_KC",
            "play_type": "run", "posteam": "CIN", "defteam": "KC",
            "down": int(rng.choice([1, 2, 3])), "ydstogo": 10, "yardline_100": int(rng.randint(20, 80)),
            "score_differential": 0, "qtr": int(rng.choice([1, 2, 3, 4])),
            "yards_gained": yards, "complete_pass": 0,
            "pass_attempt": 0, "rush_attempt": 1,
            "interception": 0, "fumble_lost": 0, "sack": 0,
            "touchdown": int(rng.random() < 0.05),
            "penalty": 0, "penalty_yards": 0,
            "passer_player_id": None, "receiver_player_id": None,
            "rusher_player_id": "JM28",
        })

    # CIN: 5 runs (RET99 — retired player not on any 2025 roster)
    for i in range(5):
        yards = int(rng.normal(3.8, 2.5))
        plays.append({
            "season": 2024, "week": (i % 3) + 1, "game_id": f"2024_0{(i%3)+1}_CIN_KC",
            "play_type": "run", "posteam": "CIN", "defteam": "KC",
            "down": int(rng.choice([1, 2, 3])), "ydstogo": 10, "yardline_100": int(rng.randint(20, 80)),
            "score_differential": 0, "qtr": int(rng.choice([1, 2, 3, 4])),
            "yards_gained": yards, "complete_pass": 0,
            "pass_attempt": 0, "rush_attempt": 1,
            "interception": 0, "fumble_lost": 0, "sack": 0,
            "touchdown": int(rng.random() < 0.05),
            "penalty": 0, "penalty_yards": 0,
            "passer_player_id": None, "receiver_player_id": None,
            "rusher_player_id": "RET99",
        })

    return pl.DataFrame(plays)


@pytest.fixture
def midseason_trade_rosters() -> pl.DataFrame:
    """Season 2025 roster data for testing mid-season trades (weeks 1-9).

    SD14 is on HOU for weeks 1-4, then traded to KC for weeks 5-9.
    KC and HOU base players are present all 9 weeks.
    """
    rows = []
    for week in range(1, 10):
        # KC core players — all weeks
        rows.extend([
            {"season": 2025, "week": week, "player_id": "PM15", "player_name": "P.Mahomes", "position": "QB", "team": "KC", "status": "ACT"},
            {"season": 2025, "week": week, "player_id": "TK87", "player_name": "T.Kelce", "position": "TE", "team": "KC", "status": "ACT"},
            {"season": 2025, "week": week, "player_id": "IP01", "player_name": "I.Pacheco", "position": "RB", "team": "KC", "status": "ACT"},
        ])
        # HOU core players — all weeks
        rows.extend([
            {"season": 2025, "week": week, "player_id": "JA17", "player_name": "J.Allen", "position": "QB", "team": "HOU", "status": "ACT"},
            {"season": 2025, "week": week, "player_id": "JM28", "player_name": "J.Mixon", "position": "RB", "team": "HOU", "status": "ACT"},
        ])
        # SD14 — HOU weeks 1-4, KC weeks 5-9
        if week <= 4:
            rows.append({"season": 2025, "week": week, "player_id": "SD14", "player_name": "S.Diggs", "position": "WR", "team": "HOU", "status": "ACT"})
        else:
            rows.append({"season": 2025, "week": week, "player_id": "SD14", "player_name": "S.Diggs", "position": "WR", "team": "KC", "status": "ACT"})
    return pl.DataFrame(rows)

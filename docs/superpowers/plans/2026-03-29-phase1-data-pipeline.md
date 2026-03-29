# Phase 1: Data Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a data pipeline that fetches NFL data from nflverse via nflreadpy, caches it locally, and preprocesses it into probability distributions the simulation engine will sample from.

**Architecture:** A `DataLoader` class wraps nflreadpy with filesystem caching (parquet). A `Preprocessor` class consumes raw data and produces distribution objects (stored as numpy arrays keyed by game-state buckets). Game-state bucketing is a shared module used by both preprocessing and the future sim engine.

**Tech Stack:** Python 3.14, nflreadpy, polars, numpy, scipy, pytest, uv

---

## File Structure

```
fantasy-projections-simulator/
├── pyproject.toml                          # Project metadata, dependencies
├── config/
│   └── defaults.yaml                       # Default simulation + scoring config
├── src/
│   └── fantasy_sim/
│       ├── __init__.py
│       ├── data/
│       │   ├── __init__.py
│       │   ├── loader.py                   # nflreadpy wrapper with filesystem cache
│       │   ├── preprocessor.py             # Distribution fitting from raw PBP
│       │   └── pipeline.py                 # Orchestrates loading + preprocessing + caching
│       └── models/
│           ├── __init__.py
│           ├── game_state.py               # GameStateBucket + bucketing functions
│           └── distributions.py            # Distribution dataclasses (PlayCallingDist, etc.)
├── tests/
│   ├── conftest.py                         # Shared fixtures (sample PBP data, etc.)
│   ├── test_data/
│   │   ├── test_loader.py
│   │   ├── test_preprocessor.py
│   │   ├── test_pipeline.py
│   │   └── test_validation_sanity.py
│   └── test_models/
│       ├── test_game_state.py
│       └── test_distributions.py
└── scripts/
    └── validate_data.py                    # Sanity check: verify distributions match NFL averages
```

---

### Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `src/fantasy_sim/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[project]
name = "fantasy-sim"
version = "0.1.0"
description = "NFL fantasy football projections via play-by-play simulation"
requires-python = ">=3.12"
dependencies = [
    "nflreadpy>=0.1.0",
    "polars>=1.0.0",
    "numpy>=2.0.0",
    "scipy>=1.14.0",
    "pyyaml>=6.0",
    "click>=8.0",
    "rich>=13.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-xdist>=3.0",
    "hypothesis>=6.0",
]

[project.scripts]
fantasy-sim = "fantasy_sim.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/fantasy_sim"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
markers = [
    "integration: tests that call nflreadpy (slow, requires network)",
    "statistical: tests that run bulk simulations (slow)",
]
```

- [ ] **Step 2: Create directory structure and init files**

```bash
mkdir -p src/fantasy_sim/data src/fantasy_sim/models src/fantasy_sim/engine src/fantasy_sim/scoring src/fantasy_sim/config src/fantasy_sim/output src/fantasy_sim/validation
mkdir -p tests/test_data tests/test_models tests/test_engine tests/test_scoring tests/test_config tests/test_output tests/test_validation
mkdir -p config scripts
touch src/fantasy_sim/__init__.py
touch src/fantasy_sim/data/__init__.py
touch src/fantasy_sim/models/__init__.py
touch src/fantasy_sim/engine/__init__.py
touch src/fantasy_sim/scoring/__init__.py
touch src/fantasy_sim/config/__init__.py
touch src/fantasy_sim/output/__init__.py
touch src/fantasy_sim/validation/__init__.py
```

- [ ] **Step 3: Create tests/conftest.py with sample PBP fixture**

This fixture provides a small, deterministic PBP DataFrame that mimics nflreadpy's `load_pbp()` output. Used across all preprocessing tests.

```python
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
    """Minimal schedules data."""
    return pl.DataFrame([
        {"season": 2024, "week": 1, "game_id": "2024_01_KC_BUF", "home_team": "KC", "away_team": "BUF", "home_score": 27, "away_score": 20, "spread_line": -3.0, "total_line": 48.5},
        {"season": 2024, "week": 2, "game_id": "2024_02_KC_LV", "home_team": "KC", "away_team": "LV", "home_score": 31, "away_score": 17, "spread_line": -7.0, "total_line": 45.0},
    ])


@pytest.fixture
def sample_kickoffs() -> pl.DataFrame:
    """PBP rows filtered to kickoff plays for drive start model tests."""
    return pl.DataFrame([
        {"season": 2024, "play_type": "kickoff", "posteam": "KC", "kick_distance": 65, "return_yards": 22, "touchback": 0, "yardline_100": 78},
        {"season": 2024, "play_type": "kickoff", "posteam": "KC", "kick_distance": 65, "return_yards": 0, "touchback": 1, "yardline_100": 75},
        {"season": 2024, "play_type": "kickoff", "posteam": "BUF", "kick_distance": 63, "return_yards": 28, "touchback": 0, "yardline_100": 72},
        {"season": 2024, "play_type": "kickoff", "posteam": "BUF", "kick_distance": 65, "return_yards": 0, "touchback": 1, "yardline_100": 75},
        {"season": 2024, "play_type": "kickoff", "posteam": "BUF", "kick_distance": 64, "return_yards": 0, "touchback": 1, "yardline_100": 75},
    ])


@pytest.fixture
def sample_field_goals() -> pl.DataFrame:
    """PBP rows filtered to field goal plays for kicking model tests."""
    return pl.DataFrame([
        {"season": 2024, "play_type": "field_goal", "posteam": "KC", "kick_distance": 32, "field_goal_result": "made"},
        {"season": 2024, "play_type": "field_goal", "posteam": "KC", "kick_distance": 48, "field_goal_result": "made"},
        {"season": 2024, "play_type": "field_goal", "posteam": "KC", "kick_distance": 55, "field_goal_result": "missed"},
        {"season": 2024, "play_type": "field_goal", "posteam": "BUF", "kick_distance": 27, "field_goal_result": "made"},
        {"season": 2024, "play_type": "field_goal", "posteam": "BUF", "kick_distance": 43, "field_goal_result": "made"},
        {"season": 2024, "play_type": "field_goal", "posteam": "BUF", "kick_distance": 51, "field_goal_result": "missed"},
    ])
```

- [ ] **Step 4: Set up virtual environment and install dependencies**

```bash
cd /Users/chrisesposito/Documents/github/fantasy-projections-simulator
uv venv
uv pip install -e ".[dev]"
```

- [ ] **Step 5: Verify pytest discovers tests**

Create a trivial test to confirm the setup works:

```python
# tests/test_smoke.py
def test_imports():
    import fantasy_sim
    assert fantasy_sim is not None
```

Run: `uv run pytest tests/test_smoke.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/ tests/ config/ scripts/
git commit -m "feat: scaffold project structure with dependencies and test fixtures"
```

---

### Task 2: Game State Bucket Definitions

**Files:**
- Create: `src/fantasy_sim/models/game_state.py`
- Test: `tests/test_models/test_game_state.py`

This is a shared module used by both preprocessing (to group PBP data into buckets) and the future sim engine (to look up distributions by game state). Getting this right now prevents mismatches later.

- [ ] **Step 1: Write failing tests for bucketing functions**

```python
# tests/test_models/test_game_state.py
from fantasy_sim.models.game_state import (
    bucket_distance,
    bucket_score_diff,
    bucket_yard_zone,
    bucket_play,
    GameStateBucket,
)


class TestBucketDistance:
    def test_short(self):
        assert bucket_distance(1) == "short"
        assert bucket_distance(3) == "short"

    def test_medium(self):
        assert bucket_distance(4) == "medium"
        assert bucket_distance(6) == "medium"

    def test_long(self):
        assert bucket_distance(7) == "long"
        assert bucket_distance(10) == "long"

    def test_very_long(self):
        assert bucket_distance(11) == "very_long"
        assert bucket_distance(20) == "very_long"


class TestBucketScoreDiff:
    def test_down_big(self):
        assert bucket_score_diff(-21) == "down_big"
        assert bucket_score_diff(-30) == "down_big"

    def test_down_medium(self):
        assert bucket_score_diff(-14) == "down_med"
        assert bucket_score_diff(-8) == "down_med"

    def test_down_small(self):
        assert bucket_score_diff(-7) == "down_small"
        assert bucket_score_diff(-1) == "down_small"

    def test_tied(self):
        assert bucket_score_diff(0) == "tied"

    def test_up_small(self):
        assert bucket_score_diff(1) == "up_small"
        assert bucket_score_diff(7) == "up_small"

    def test_up_medium(self):
        assert bucket_score_diff(8) == "up_med"
        assert bucket_score_diff(14) == "up_med"

    def test_up_big(self):
        assert bucket_score_diff(15) == "up_big"
        assert bucket_score_diff(35) == "up_big"


class TestBucketYardZone:
    def test_backed_up(self):
        # yardline_100 = 99 means own 1-yard line, 80 = own 20
        assert bucket_yard_zone(99) == "backed_up"
        assert bucket_yard_zone(80) == "backed_up"

    def test_own_territory(self):
        assert bucket_yard_zone(79) == "own_territory"
        assert bucket_yard_zone(50) == "own_territory"

    def test_opp_territory(self):
        assert bucket_yard_zone(49) == "opp_territory"
        assert bucket_yard_zone(21) == "opp_territory"

    def test_red_zone(self):
        assert bucket_yard_zone(20) == "red_zone"
        assert bucket_yard_zone(1) == "red_zone"


class TestBucketPlay:
    def test_creates_bucket(self):
        bucket = bucket_play(
            down=1, ydstogo=10, score_differential=0, qtr=1, yardline_100=75
        )
        assert isinstance(bucket, GameStateBucket)
        assert bucket.down == 1
        assert bucket.distance == "long"
        assert bucket.score_diff == "tied"
        assert bucket.quarter == 1
        assert bucket.yard_zone == "own_territory"

    def test_bucket_is_hashable(self):
        b1 = bucket_play(1, 10, 0, 1, 75)
        b2 = bucket_play(1, 10, 0, 1, 75)
        assert b1 == b2
        assert hash(b1) == hash(b2)
        # Can be used as dict key
        d = {b1: "test"}
        assert d[b2] == "test"

    def test_different_states_different_buckets(self):
        b1 = bucket_play(1, 10, 0, 1, 75)
        b2 = bucket_play(2, 10, 0, 1, 75)
        assert b1 != b2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_models/test_game_state.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fantasy_sim.models.game_state'`

- [ ] **Step 3: Implement game state bucketing**

```python
# src/fantasy_sim/models/game_state.py
from dataclasses import dataclass


@dataclass(frozen=True)
class GameStateBucket:
    """Discretized game state for indexing probability distributions.

    frozen=True makes it hashable so it can be used as a dict key.
    """

    down: int
    distance: str
    score_diff: str
    quarter: int
    yard_zone: str


def bucket_distance(ydstogo: int) -> str:
    if ydstogo <= 3:
        return "short"
    elif ydstogo <= 6:
        return "medium"
    elif ydstogo <= 10:
        return "long"
    else:
        return "very_long"


def bucket_score_diff(score_differential: int) -> str:
    if score_differential <= -21:
        return "down_big"
    elif score_differential <= -8:
        return "down_med"
    elif score_differential <= -1:
        return "down_small"
    elif score_differential == 0:
        return "tied"
    elif score_differential <= 7:
        return "up_small"
    elif score_differential <= 14:
        return "up_med"
    else:
        return "up_big"


def bucket_yard_zone(yardline_100: int) -> str:
    if yardline_100 >= 80:
        return "backed_up"
    elif yardline_100 >= 50:
        return "own_territory"
    elif yardline_100 >= 21:
        return "opp_territory"
    else:
        return "red_zone"


def bucket_play(
    down: int,
    ydstogo: int,
    score_differential: int,
    qtr: int,
    yardline_100: int,
) -> GameStateBucket:
    return GameStateBucket(
        down=down,
        distance=bucket_distance(ydstogo),
        score_diff=bucket_score_diff(score_differential),
        quarter=qtr,
        yard_zone=bucket_yard_zone(yardline_100),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_models/test_game_state.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/models/game_state.py tests/test_models/test_game_state.py
git commit -m "feat: add game state bucketing module"
```

---

### Task 3: Distribution Dataclasses

**Files:**
- Create: `src/fantasy_sim/models/distributions.py`
- Test: `tests/test_models/test_distributions.py`

These are the containers that hold preprocessed data. The sim engine will receive these and sample from them.

- [ ] **Step 1: Write failing tests for distribution types**

```python
# tests/test_models/test_distributions.py
import numpy as np
import pytest
from fantasy_sim.models.game_state import GameStateBucket
from fantasy_sim.models.distributions import (
    PlayCallingDist,
    PlayOutcomeDist,
    TurnoverRates,
    KickingModel,
    DriveStartModel,
)


class TestPlayCallingDist:
    def test_get_play_probs(self):
        bucket = GameStateBucket(1, "long", "tied", 1, "own_territory")
        dist = PlayCallingDist(
            team="KC",
            distributions={bucket: {"pass": 0.6, "run": 0.4}},
        )
        probs = dist.get_probs(bucket)
        assert probs["pass"] == pytest.approx(0.6)
        assert probs["run"] == pytest.approx(0.4)

    def test_missing_bucket_falls_back_to_default(self):
        known = GameStateBucket(1, "long", "tied", 1, "own_territory")
        unknown = GameStateBucket(3, "very_long", "down_big", 4, "backed_up")
        dist = PlayCallingDist(
            team="KC",
            distributions={known: {"pass": 0.6, "run": 0.4}},
            default={"pass": 0.55, "run": 0.45},
        )
        probs = dist.get_probs(unknown)
        assert probs["pass"] == pytest.approx(0.55)

    def test_probs_sum_to_one(self):
        bucket = GameStateBucket(1, "long", "tied", 1, "own_territory")
        dist = PlayCallingDist(
            team="KC",
            distributions={bucket: {"pass": 0.6, "run": 0.4}},
        )
        probs = dist.get_probs(bucket)
        assert sum(probs.values()) == pytest.approx(1.0)


class TestPlayOutcomeDist:
    def test_sample_yards(self):
        bucket = GameStateBucket(1, "long", "tied", 1, "own_territory")
        yards_history = np.array([5, 8, -2, 12, 3, 7, 0, 15, 4, 6])
        dist = PlayOutcomeDist(
            distributions={("pass", bucket): yards_history}
        )
        rng = np.random.default_rng(42)
        sampled = dist.sample_yards("pass", bucket, rng)
        assert sampled in yards_history

    def test_missing_bucket_falls_back_to_play_type_default(self):
        known = GameStateBucket(1, "long", "tied", 1, "own_territory")
        unknown = GameStateBucket(3, "short", "up_big", 4, "red_zone")
        yards_history = np.array([5, 8, 3])
        dist = PlayOutcomeDist(
            distributions={("pass", known): yards_history},
            defaults={"pass": np.array([4, 6, 2])},
        )
        rng = np.random.default_rng(42)
        sampled = dist.sample_yards("pass", unknown, rng)
        assert sampled in [4, 6, 2]


class TestTurnoverRates:
    def test_rates(self):
        rates = TurnoverRates(
            team="KC",
            int_rate=0.025,
            fumble_rate=0.01,
            sack_rate=0.06,
            sack_fumble_rate=0.10,
        )
        assert rates.int_rate == pytest.approx(0.025)
        assert rates.fumble_rate == pytest.approx(0.01)
        assert rates.sack_rate == pytest.approx(0.06)
        assert rates.sack_fumble_rate == pytest.approx(0.10)


class TestKickingModel:
    def test_fg_probability(self):
        model = KickingModel(
            fg_make_rate={"0_39": 0.95, "40_49": 0.82, "50_plus": 0.65},
            xp_rate=0.94,
        )
        assert model.fg_prob(32) == pytest.approx(0.95)
        assert model.fg_prob(45) == pytest.approx(0.82)
        assert model.fg_prob(55) == pytest.approx(0.65)

    def test_xp_rate(self):
        model = KickingModel(
            fg_make_rate={"0_39": 0.95, "40_49": 0.82, "50_plus": 0.65},
            xp_rate=0.94,
        )
        assert model.xp_rate == pytest.approx(0.94)


class TestDriveStartModel:
    def test_sample_start_yardline(self):
        model = DriveStartModel(
            touchback_rate=0.55,
            touchback_yardline=75,
            return_yardlines=np.array([78, 72, 68, 80, 74]),
        )
        rng = np.random.default_rng(42)
        yardline = model.sample_start_yardline(rng)
        assert 1 <= yardline <= 99
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_models/test_distributions.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement distribution dataclasses**

```python
# src/fantasy_sim/models/distributions.py
from dataclasses import dataclass, field
import numpy as np
from fantasy_sim.models.game_state import GameStateBucket


@dataclass
class PlayCallingDist:
    """P(play_type | game_state) for one team."""

    team: str
    distributions: dict[GameStateBucket, dict[str, float]]
    default: dict[str, float] = field(default_factory=lambda: {"pass": 0.57, "run": 0.43})

    def get_probs(self, bucket: GameStateBucket) -> dict[str, float]:
        return self.distributions.get(bucket, self.default)


@dataclass
class PlayOutcomeDist:
    """Empirical yards-gained distributions by (play_type, game_state).

    Each value is a numpy array of historical yards-gained values.
    Sampling draws uniformly from the array (empirical distribution).
    """

    distributions: dict[tuple[str, GameStateBucket], np.ndarray]
    defaults: dict[str, np.ndarray] = field(default_factory=dict)

    def sample_yards(
        self, play_type: str, bucket: GameStateBucket, rng: np.random.Generator
    ) -> int:
        key = (play_type, bucket)
        if key in self.distributions:
            arr = self.distributions[key]
        elif play_type in self.defaults:
            arr = self.defaults[play_type]
        else:
            return 0
        return int(rng.choice(arr))


@dataclass
class TurnoverRates:
    """Per-team turnover and sack rates (per-play probabilities)."""

    team: str
    int_rate: float
    fumble_rate: float
    sack_rate: float
    sack_fumble_rate: float


@dataclass
class KickingModel:
    """Field goal and extra point probabilities."""

    fg_make_rate: dict[str, float]
    xp_rate: float

    def fg_prob(self, distance: int) -> float:
        if distance < 40:
            return self.fg_make_rate["0_39"]
        elif distance < 50:
            return self.fg_make_rate["40_49"]
        else:
            return self.fg_make_rate["50_plus"]


@dataclass
class DriveStartModel:
    """Kickoff return model for determining drive starting field position."""

    touchback_rate: float
    touchback_yardline: int
    return_yardlines: np.ndarray

    def sample_start_yardline(self, rng: np.random.Generator) -> int:
        if rng.random() < self.touchback_rate:
            return self.touchback_yardline
        return int(rng.choice(self.return_yardlines))


@dataclass
class PenaltyRates:
    """Per-team penalty rates by penalty type."""

    team: str
    penalty_rate: float
    type_distribution: dict[str, float]
    avg_yards: dict[str, float]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_models/test_distributions.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/models/distributions.py tests/test_models/test_distributions.py
git commit -m "feat: add distribution dataclasses for sim engine"
```

---

### Task 4: Data Loader with Filesystem Caching

**Files:**
- Create: `src/fantasy_sim/data/loader.py`
- Test: `tests/test_data/test_loader.py`

- [ ] **Step 1: Write failing tests for the data loader**

```python
# tests/test_data/test_loader.py
import polars as pl
import pytest
from pathlib import Path
from unittest.mock import patch
from fantasy_sim.data.loader import DataLoader


@pytest.fixture
def cache_dir(tmp_path):
    return tmp_path / "cache"


@pytest.fixture
def loader(cache_dir):
    return DataLoader(cache_dir=cache_dir)


class TestDataLoaderCaching:
    def test_cache_dir_created(self, loader, cache_dir):
        assert cache_dir.exists()

    @patch("fantasy_sim.data.loader.nflreadpy")
    def test_load_pbp_caches_to_parquet(self, mock_nfl, loader, cache_dir):
        mock_df = pl.DataFrame({"play_type": ["pass", "run"], "yards_gained": [10, 5]})
        mock_nfl.load_pbp.return_value = mock_df

        result = loader.load_pbp(seasons=[2024])

        assert result.shape == mock_df.shape
        cache_file = cache_dir / "pbp_2024.parquet"
        assert cache_file.exists()

    @patch("fantasy_sim.data.loader.nflreadpy")
    def test_load_pbp_uses_cache_on_second_call(self, mock_nfl, loader):
        mock_df = pl.DataFrame({"play_type": ["pass"], "yards_gained": [10]})
        mock_nfl.load_pbp.return_value = mock_df

        loader.load_pbp(seasons=[2024])
        loader.load_pbp(seasons=[2024])

        mock_nfl.load_pbp.assert_called_once()

    @patch("fantasy_sim.data.loader.nflreadpy")
    def test_load_pbp_multiple_seasons(self, mock_nfl, loader):
        mock_df = pl.DataFrame({"play_type": ["pass"], "yards_gained": [10], "season": [2024]})
        mock_nfl.load_pbp.return_value = mock_df

        loader.load_pbp(seasons=[2023, 2024])
        mock_nfl.load_pbp.assert_called_once_with([2023, 2024])


class TestDataLoaderMethods:
    @patch("fantasy_sim.data.loader.nflreadpy")
    def test_load_schedules(self, mock_nfl, loader):
        mock_df = pl.DataFrame({"game_id": ["g1"], "home_team": ["KC"]})
        mock_nfl.load_schedules.return_value = mock_df
        result = loader.load_schedules(seasons=[2024])
        assert result.shape[0] == 1

    @patch("fantasy_sim.data.loader.nflreadpy")
    def test_load_rosters(self, mock_nfl, loader):
        mock_df = pl.DataFrame({"player_id": ["p1"], "position": ["QB"]})
        mock_nfl.load_rosters_weekly.return_value = mock_df
        result = loader.load_rosters(seasons=[2024])
        assert result.shape[0] == 1

    @patch("fantasy_sim.data.loader.nflreadpy")
    def test_load_player_stats(self, mock_nfl, loader):
        mock_df = pl.DataFrame({"player_id": ["p1"], "passing_yards": [300]})
        mock_nfl.load_player_stats.return_value = mock_df
        result = loader.load_player_stats(seasons=[2024])
        assert result.shape[0] == 1

    @patch("fantasy_sim.data.loader.nflreadpy")
    def test_clear_cache(self, mock_nfl, loader, cache_dir):
        mock_df = pl.DataFrame({"play_type": ["pass"], "yards_gained": [10]})
        mock_nfl.load_pbp.return_value = mock_df
        loader.load_pbp(seasons=[2024])
        assert any(cache_dir.iterdir())

        loader.clear_cache()
        assert not any(cache_dir.iterdir())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_loader.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement the data loader**

```python
# src/fantasy_sim/data/loader.py
from pathlib import Path
import polars as pl
import nflreadpy


DEFAULT_CACHE_DIR = Path.home() / ".fantasy-sim" / "cache"


class DataLoader:
    """Wraps nflreadpy with filesystem caching via parquet files."""

    def __init__(self, cache_dir: Path = DEFAULT_CACHE_DIR):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_key(self, name: str, seasons: list[int]) -> Path:
        season_str = "_".join(str(s) for s in sorted(seasons))
        return self.cache_dir / f"{name}_{season_str}.parquet"

    def _load_cached(self, cache_path: Path) -> pl.DataFrame | None:
        if cache_path.exists():
            return pl.read_parquet(cache_path)
        return None

    def _save_cache(self, df: pl.DataFrame, cache_path: Path) -> None:
        df.write_parquet(cache_path)

    def load_pbp(self, seasons: list[int]) -> pl.DataFrame:
        cache_path = self._cache_key("pbp", seasons)
        cached = self._load_cached(cache_path)
        if cached is not None:
            return cached
        df = nflreadpy.load_pbp(seasons)
        self._save_cache(df, cache_path)
        return df

    def load_player_stats(
        self, seasons: list[int], summary_level: str = "week"
    ) -> pl.DataFrame:
        cache_path = self._cache_key(f"player_stats_{summary_level}", seasons)
        cached = self._load_cached(cache_path)
        if cached is not None:
            return cached
        df = nflreadpy.load_player_stats(seasons, summary_level=summary_level)
        self._save_cache(df, cache_path)
        return df

    def load_rosters(self, seasons: list[int]) -> pl.DataFrame:
        cache_path = self._cache_key("rosters_weekly", seasons)
        cached = self._load_cached(cache_path)
        if cached is not None:
            return cached
        df = nflreadpy.load_rosters_weekly(seasons)
        self._save_cache(df, cache_path)
        return df

    def load_schedules(self, seasons: list[int]) -> pl.DataFrame:
        cache_path = self._cache_key("schedules", seasons)
        cached = self._load_cached(cache_path)
        if cached is not None:
            return cached
        df = nflreadpy.load_schedules(seasons)
        self._save_cache(df, cache_path)
        return df

    def load_snap_counts(self, seasons: list[int]) -> pl.DataFrame:
        cache_path = self._cache_key("snap_counts", seasons)
        cached = self._load_cached(cache_path)
        if cached is not None:
            return cached
        df = nflreadpy.load_snap_counts(seasons)
        self._save_cache(df, cache_path)
        return df

    def load_depth_charts(self, seasons: list[int]) -> pl.DataFrame:
        cache_path = self._cache_key("depth_charts", seasons)
        cached = self._load_cached(cache_path)
        if cached is not None:
            return cached
        df = nflreadpy.load_depth_charts(seasons)
        self._save_cache(df, cache_path)
        return df

    def load_draft_picks(self) -> pl.DataFrame:
        cache_path = self.cache_dir / "draft_picks.parquet"
        cached = self._load_cached(cache_path)
        if cached is not None:
            return cached
        df = nflreadpy.load_draft_picks()
        self._save_cache(df, cache_path)
        return df

    def clear_cache(self) -> None:
        for f in self.cache_dir.glob("*.parquet"):
            f.unlink()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_loader.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/loader.py tests/test_data/test_loader.py
git commit -m "feat: add nflreadpy data loader with filesystem caching"
```

---

### Task 5: Play-Calling Distribution Preprocessor

**Files:**
- Create: `src/fantasy_sim/data/preprocessor.py`
- Test: `tests/test_data/test_preprocessor.py`

- [ ] **Step 1: Write failing tests for play-calling distribution computation**

```python
# tests/test_data/test_preprocessor.py
import polars as pl
import numpy as np
import pytest
from fantasy_sim.data.preprocessor import Preprocessor
from fantasy_sim.models.game_state import GameStateBucket
from fantasy_sim.models.distributions import (
    PlayOutcomeDist,
    TurnoverRates,
    KickingModel,
    DriveStartModel,
)


class TestPlayCallingDistributions:
    def test_computes_pass_run_ratio_per_team(self, sample_pbp):
        pre = Preprocessor()
        dists = pre.compute_play_calling(sample_pbp)

        assert "KC" in dists
        assert "BUF" in dists

    def test_kc_has_correct_overall_ratio(self, sample_pbp):
        """KC has 8 passes and 4 runs = 66.7% pass rate."""
        pre = Preprocessor()
        dists = pre.compute_play_calling(sample_pbp)
        kc = dists["KC"]

        assert kc.default["pass"] == pytest.approx(8 / 12, abs=0.01)
        assert kc.default["run"] == pytest.approx(4 / 12, abs=0.01)

    def test_buf_has_correct_overall_ratio(self, sample_pbp):
        """BUF has 4 passes and 4 runs = 50% pass rate."""
        pre = Preprocessor()
        dists = pre.compute_play_calling(sample_pbp)
        buf = dists["BUF"]

        assert buf.default["pass"] == pytest.approx(0.5, abs=0.01)
        assert buf.default["run"] == pytest.approx(0.5, abs=0.01)

    def test_distributions_have_bucketed_entries(self, sample_pbp):
        pre = Preprocessor()
        dists = pre.compute_play_calling(sample_pbp)
        kc = dists["KC"]

        # With only 12 plays, most buckets won't meet the MIN_BUCKET_PLAYS threshold
        # but the default should still be set
        assert kc.default is not None

    def test_all_probs_sum_to_one(self, sample_pbp):
        pre = Preprocessor()
        dists = pre.compute_play_calling(sample_pbp)
        for team_dist in dists.values():
            for bucket, probs in team_dist.distributions.items():
                assert sum(probs.values()) == pytest.approx(1.0, abs=0.01)
            assert sum(team_dist.default.values()) == pytest.approx(1.0, abs=0.01)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_preprocessor.py::TestPlayCallingDistributions -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement play-calling distribution computation**

```python
# src/fantasy_sim/data/preprocessor.py
import polars as pl
import numpy as np
from fantasy_sim.models.game_state import GameStateBucket, bucket_play
from fantasy_sim.models.distributions import (
    PlayCallingDist,
    PlayOutcomeDist,
    TurnoverRates,
    KickingModel,
    DriveStartModel,
    PenaltyRates,
)

# Minimum plays in a bucket to use bucket-specific distribution
MIN_BUCKET_PLAYS = 10


class Preprocessor:
    """Computes probability distributions from raw PBP data."""

    def _filter_real_plays(self, pbp: pl.DataFrame) -> pl.DataFrame:
        """Filter to actual run/pass plays (no punts, kickoffs, etc.)."""
        return pbp.filter(pl.col("play_type").is_in(["pass", "run"]))

    def compute_play_calling(
        self, pbp: pl.DataFrame
    ) -> dict[str, PlayCallingDist]:
        """Compute P(run|state) and P(pass|state) per team."""
        plays = self._filter_real_plays(pbp)
        teams = plays["posteam"].unique().to_list()
        result = {}

        for team in teams:
            team_plays = plays.filter(pl.col("posteam") == team)
            total = team_plays.shape[0]
            if total == 0:
                continue

            pass_count = team_plays.filter(pl.col("play_type") == "pass").shape[0]
            run_count = total - pass_count
            default = {"pass": pass_count / total, "run": run_count / total}

            # Per-bucket ratios
            bucket_counts: dict[GameStateBucket, dict[str, int]] = {}
            for row in team_plays.iter_rows(named=True):
                bucket = bucket_play(
                    row["down"],
                    row["ydstogo"],
                    row["score_differential"],
                    row["qtr"],
                    row["yardline_100"],
                )
                if bucket not in bucket_counts:
                    bucket_counts[bucket] = {"pass": 0, "run": 0}
                bucket_counts[bucket][row["play_type"]] += 1

            # Convert counts to probabilities, drop sparse buckets
            distributions: dict[GameStateBucket, dict[str, float]] = {}
            for bucket, counts in bucket_counts.items():
                total_bucket = counts["pass"] + counts["run"]
                if total_bucket >= MIN_BUCKET_PLAYS:
                    distributions[bucket] = {
                        "pass": counts["pass"] / total_bucket,
                        "run": counts["run"] / total_bucket,
                    }

            result[team] = PlayCallingDist(
                team=team, distributions=distributions, default=default
            )

        return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_preprocessor.py::TestPlayCallingDistributions -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/preprocessor.py tests/test_data/test_preprocessor.py
git commit -m "feat: add play-calling distribution preprocessor"
```

---

### Task 6: Play Outcome Distribution Preprocessor

**Files:**
- Modify: `src/fantasy_sim/data/preprocessor.py`
- Modify: `tests/test_data/test_preprocessor.py`

- [ ] **Step 1: Write failing tests for play outcome distributions**

Add to `tests/test_data/test_preprocessor.py`:

```python
class TestPlayOutcomeDistributions:
    def test_computes_yards_arrays(self, sample_pbp):
        pre = Preprocessor()
        dist = pre.compute_play_outcomes(sample_pbp)

        assert isinstance(dist, PlayOutcomeDist)
        assert len(dist.distributions) > 0 or len(dist.defaults) > 0

    def test_defaults_contain_all_yards(self, sample_pbp):
        pre = Preprocessor()
        dist = pre.compute_play_outcomes(sample_pbp)

        assert "pass" in dist.defaults
        assert "run" in dist.defaults

    def test_run_defaults_contain_all_run_yards(self, sample_pbp):
        """All run yards in sample: KC=[5,-2,5,12], BUF=[7,3,1,4]"""
        pre = Preprocessor()
        dist = pre.compute_play_outcomes(sample_pbp)

        all_run_yards = sorted([5, -2, 5, 12, 7, 3, 1, 4])
        default_run = sorted(dist.defaults["run"].tolist())
        assert default_run == all_run_yards

    def test_can_sample_from_distribution(self, sample_pbp):
        pre = Preprocessor()
        dist = pre.compute_play_outcomes(sample_pbp)
        rng = np.random.default_rng(42)

        bucket = GameStateBucket(1, "long", "tied", 1, "own_territory")
        yards = dist.sample_yards("pass", bucket, rng)
        assert isinstance(yards, (int, np.integer))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_preprocessor.py::TestPlayOutcomeDistributions -v`
Expected: FAIL — `AttributeError: 'Preprocessor' object has no attribute 'compute_play_outcomes'`

- [ ] **Step 3: Implement play outcome distribution computation**

Add to `Preprocessor` class in `src/fantasy_sim/data/preprocessor.py`:

```python
    def compute_play_outcomes(self, pbp: pl.DataFrame) -> PlayOutcomeDist:
        """Compute empirical yards-gained distributions by play type and game state."""
        plays = self._filter_real_plays(pbp)

        bucket_yards: dict[tuple[str, GameStateBucket], list[int]] = {}
        defaults: dict[str, list[int]] = {"pass": [], "run": []}

        for row in plays.iter_rows(named=True):
            play_type = row["play_type"]
            yards = row["yards_gained"]
            defaults[play_type].append(yards)

            bucket = bucket_play(
                row["down"],
                row["ydstogo"],
                row["score_differential"],
                row["qtr"],
                row["yardline_100"],
            )
            key = (play_type, bucket)
            if key not in bucket_yards:
                bucket_yards[key] = []
            bucket_yards[key].append(yards)

        # Convert lists to numpy arrays, drop sparse buckets
        distributions = {}
        for key, yards_list in bucket_yards.items():
            if len(yards_list) >= MIN_BUCKET_PLAYS:
                distributions[key] = np.array(yards_list)

        final_defaults = {k: np.array(v) for k, v in defaults.items() if v}

        return PlayOutcomeDist(distributions=distributions, defaults=final_defaults)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_preprocessor.py::TestPlayOutcomeDistributions -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/preprocessor.py tests/test_data/test_preprocessor.py
git commit -m "feat: add play outcome distribution preprocessor"
```

---

### Task 7: Turnover, Kicking, and Drive Start Preprocessors

**Files:**
- Modify: `src/fantasy_sim/data/preprocessor.py`
- Modify: `tests/test_data/test_preprocessor.py`

- [ ] **Step 1: Write failing tests for all three preprocessors**

Add to `tests/test_data/test_preprocessor.py`:

```python
class TestTurnoverRatePreprocessor:
    def test_computes_per_team(self, sample_pbp):
        pre = Preprocessor()
        rates = pre.compute_turnover_rates(sample_pbp)

        assert "KC" in rates
        assert "BUF" in rates

    def test_kc_int_rate(self, sample_pbp):
        """KC has 1 INT on 8 pass attempts = 0.125."""
        pre = Preprocessor()
        rates = pre.compute_turnover_rates(sample_pbp)
        assert rates["KC"].int_rate == pytest.approx(1 / 8, abs=0.01)

    def test_kc_sack_rate(self, sample_pbp):
        """KC has 1 sack on 8 pass attempts = 0.125."""
        pre = Preprocessor()
        rates = pre.compute_turnover_rates(sample_pbp)
        assert rates["KC"].sack_rate == pytest.approx(1 / 8, abs=0.01)

    def test_kc_fumble_rate(self, sample_pbp):
        """KC has 1 fumble lost on 12 total plays = 0.0833."""
        pre = Preprocessor()
        rates = pre.compute_turnover_rates(sample_pbp)
        assert rates["KC"].fumble_rate == pytest.approx(1 / 12, abs=0.01)

    def test_buf_zero_turnovers(self, sample_pbp):
        """BUF has 0 INTs, 0 fumbles, 0 sacks in sample data."""
        pre = Preprocessor()
        rates = pre.compute_turnover_rates(sample_pbp)
        assert rates["BUF"].int_rate == pytest.approx(0.0)
        assert rates["BUF"].fumble_rate == pytest.approx(0.0)
        assert rates["BUF"].sack_rate == pytest.approx(0.0)

    def test_rates_are_probabilities(self, sample_pbp):
        pre = Preprocessor()
        rates = pre.compute_turnover_rates(sample_pbp)
        for team_rates in rates.values():
            assert 0.0 <= team_rates.int_rate <= 1.0
            assert 0.0 <= team_rates.fumble_rate <= 1.0
            assert 0.0 <= team_rates.sack_rate <= 1.0
            assert 0.0 <= team_rates.sack_fumble_rate <= 1.0


class TestKickingModelPreprocessor:
    def test_computes_fg_rates_by_distance(self, sample_field_goals):
        pre = Preprocessor()
        model = pre.compute_kicking_model(sample_field_goals)

        assert isinstance(model, KickingModel)
        assert model.fg_make_rate["0_39"] == pytest.approx(1.0)
        assert model.fg_make_rate["40_49"] == pytest.approx(1.0)
        assert model.fg_make_rate["50_plus"] == pytest.approx(0.0)

    def test_fg_prob_returns_correct_bucket(self, sample_field_goals):
        pre = Preprocessor()
        model = pre.compute_kicking_model(sample_field_goals)

        assert model.fg_prob(35) == model.fg_make_rate["0_39"]
        assert model.fg_prob(45) == model.fg_make_rate["40_49"]
        assert model.fg_prob(52) == model.fg_make_rate["50_plus"]

    def test_xp_rate_defaults_when_no_data(self, sample_field_goals):
        pre = Preprocessor()
        model = pre.compute_kicking_model(sample_field_goals)
        assert 0.90 <= model.xp_rate <= 0.98


class TestDriveStartModelPreprocessor:
    def test_computes_touchback_rate(self, sample_kickoffs):
        """Sample has 3 touchbacks out of 5 kickoffs = 0.6."""
        pre = Preprocessor()
        model = pre.compute_drive_start_model(sample_kickoffs)

        assert isinstance(model, DriveStartModel)
        assert model.touchback_rate == pytest.approx(3 / 5, abs=0.01)

    def test_touchback_yardline(self, sample_kickoffs):
        pre = Preprocessor()
        model = pre.compute_drive_start_model(sample_kickoffs)
        assert model.touchback_yardline == 75

    def test_return_yardlines_from_non_touchbacks(self, sample_kickoffs):
        """Non-touchback plays have yardline_100 = [78, 72]."""
        pre = Preprocessor()
        model = pre.compute_drive_start_model(sample_kickoffs)

        assert len(model.return_yardlines) == 2
        assert sorted(model.return_yardlines.tolist()) == [72, 78]

    def test_sample_produces_valid_yardline(self, sample_kickoffs):
        pre = Preprocessor()
        model = pre.compute_drive_start_model(sample_kickoffs)

        rng = np.random.default_rng(42)
        for _ in range(50):
            yl = model.sample_start_yardline(rng)
            assert 1 <= yl <= 99
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_preprocessor.py -k "Turnover or Kicking or DriveStart" -v`
Expected: FAIL — `AttributeError`

- [ ] **Step 3: Implement all three preprocessors**

Add to `Preprocessor` class in `src/fantasy_sim/data/preprocessor.py`:

```python
    def compute_turnover_rates(
        self, pbp: pl.DataFrame
    ) -> dict[str, TurnoverRates]:
        """Compute per-team turnover and sack rates from PBP data."""
        plays = self._filter_real_plays(pbp)
        teams = plays["posteam"].unique().to_list()
        result = {}

        for team in teams:
            team_plays = plays.filter(pl.col("posteam") == team)
            total_plays = team_plays.shape[0]
            pass_plays = team_plays.filter(pl.col("play_type") == "pass")
            total_passes = pass_plays.shape[0]

            if total_plays == 0:
                continue

            ints = team_plays.filter(pl.col("interception") == 1).shape[0]
            fumbles = team_plays.filter(pl.col("fumble_lost") == 1).shape[0]
            sacks = team_plays.filter(pl.col("sack") == 1).shape[0]

            int_rate = ints / total_passes if total_passes > 0 else 0.0
            fumble_rate = fumbles / total_plays
            sack_rate = sacks / total_passes if total_passes > 0 else 0.0

            sack_plays = team_plays.filter(pl.col("sack") == 1)
            if sack_plays.shape[0] > 0:
                sack_fumbles = sack_plays.filter(pl.col("fumble_lost") == 1).shape[0]
                sack_fumble_rate = sack_fumbles / sack_plays.shape[0]
            else:
                sack_fumble_rate = 0.10  # League average fallback

            result[team] = TurnoverRates(
                team=team,
                int_rate=int_rate,
                fumble_rate=fumble_rate,
                sack_rate=sack_rate,
                sack_fumble_rate=sack_fumble_rate,
            )

        return result

    def compute_kicking_model(
        self, pbp: pl.DataFrame, xp_data: pl.DataFrame | None = None
    ) -> KickingModel:
        """Compute FG make rates by distance bucket and XP rate."""
        fg_plays = pbp.filter(pl.col("play_type") == "field_goal")

        buckets = {
            "0_39": {"made": 0, "total": 0},
            "40_49": {"made": 0, "total": 0},
            "50_plus": {"made": 0, "total": 0},
        }

        for row in fg_plays.iter_rows(named=True):
            dist = row["kick_distance"]
            if dist < 40:
                bucket = "0_39"
            elif dist < 50:
                bucket = "40_49"
            else:
                bucket = "50_plus"

            buckets[bucket]["total"] += 1
            if row["field_goal_result"] == "made":
                buckets[bucket]["made"] += 1

        league_avg = {"0_39": 0.95, "40_49": 0.82, "50_plus": 0.65}
        fg_make_rate = {}
        for bucket, counts in buckets.items():
            if counts["total"] == 0:
                fg_make_rate[bucket] = league_avg[bucket]
            else:
                fg_make_rate[bucket] = counts["made"] / counts["total"]

        # XP rate
        if xp_data is not None and xp_data.shape[0] > 0:
            xp_plays = xp_data.filter(pl.col("play_type") == "extra_point")
            if xp_plays.shape[0] > 0:
                xp_made = xp_plays.filter(pl.col("extra_point_result") == "good").shape[0]
                xp_rate = xp_made / xp_plays.shape[0]
            else:
                xp_rate = 0.94
        else:
            xp_rate = 0.94

        return KickingModel(fg_make_rate=fg_make_rate, xp_rate=xp_rate)

    def compute_drive_start_model(self, pbp: pl.DataFrame) -> DriveStartModel:
        """Compute kickoff return / touchback distributions."""
        kickoffs = pbp.filter(pl.col("play_type") == "kickoff")

        if kickoffs.shape[0] == 0:
            return DriveStartModel(
                touchback_rate=0.55,
                touchback_yardline=75,
                return_yardlines=np.array([72, 74, 76, 78, 80]),
            )

        touchbacks = kickoffs.filter(pl.col("touchback") == 1)
        returns = kickoffs.filter(pl.col("touchback") == 0)

        touchback_rate = touchbacks.shape[0] / kickoffs.shape[0]

        if touchbacks.shape[0] > 0:
            touchback_yardline = int(touchbacks["yardline_100"].mean())
        else:
            touchback_yardline = 75

        if returns.shape[0] > 0:
            return_yardlines = returns["yardline_100"].to_numpy()
        else:
            return_yardlines = np.array([72, 74, 76, 78, 80])

        return DriveStartModel(
            touchback_rate=touchback_rate,
            touchback_yardline=touchback_yardline,
            return_yardlines=return_yardlines,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_preprocessor.py -k "Turnover or Kicking or DriveStart" -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/preprocessor.py tests/test_data/test_preprocessor.py
git commit -m "feat: add turnover, kicking, and drive start preprocessors"
```

---

### Task 8: Pipeline Orchestrator

**Files:**
- Create: `src/fantasy_sim/data/pipeline.py`
- Test: `tests/test_data/test_pipeline.py`

Ties the loader and preprocessor together into a single `build()` call. Caches the preprocessed distributions as JSON-serialized numpy arrays to avoid recomputation.

- [ ] **Step 1: Write failing tests for the pipeline**

```python
# tests/test_data/test_pipeline.py
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from fantasy_sim.data.pipeline import DataPipeline


@pytest.fixture
def pipeline(tmp_path):
    return DataPipeline(cache_dir=tmp_path / "cache", seasons=[2024])


class TestDataPipeline:
    def test_build_returns_all_distribution_types(self, pipeline, sample_pbp, sample_field_goals, sample_kickoffs):
        result = pipeline.build(pbp=sample_pbp, fg_data=sample_field_goals, kickoff_data=sample_kickoffs)

        assert "play_calling" in result
        assert "play_outcomes" in result
        assert "turnover_rates" in result
        assert "kicking" in result
        assert "drive_start" in result

    def test_play_calling_has_teams(self, pipeline, sample_pbp, sample_field_goals, sample_kickoffs):
        result = pipeline.build(pbp=sample_pbp, fg_data=sample_field_goals, kickoff_data=sample_kickoffs)

        assert "KC" in result["play_calling"]
        assert "BUF" in result["play_calling"]

    def test_turnover_rates_has_teams(self, pipeline, sample_pbp, sample_field_goals, sample_kickoffs):
        result = pipeline.build(pbp=sample_pbp, fg_data=sample_field_goals, kickoff_data=sample_kickoffs)

        assert "KC" in result["turnover_rates"]
        assert "BUF" in result["turnover_rates"]

    def test_kicking_model_has_rates(self, pipeline, sample_pbp, sample_field_goals, sample_kickoffs):
        result = pipeline.build(pbp=sample_pbp, fg_data=sample_field_goals, kickoff_data=sample_kickoffs)

        assert "0_39" in result["kicking"].fg_make_rate
        assert "40_49" in result["kicking"].fg_make_rate
        assert "50_plus" in result["kicking"].fg_make_rate
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_pipeline.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement the pipeline orchestrator**

```python
# src/fantasy_sim/data/pipeline.py
from pathlib import Path
import polars as pl
from fantasy_sim.data.loader import DataLoader
from fantasy_sim.data.preprocessor import Preprocessor


class DataPipeline:
    """Orchestrates data loading and preprocessing into distributions."""

    def __init__(self, cache_dir: Path, seasons: list[int]):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.seasons = seasons
        self.loader = DataLoader(cache_dir=self.cache_dir)
        self.preprocessor = Preprocessor()

    def build(
        self,
        pbp: pl.DataFrame | None = None,
        fg_data: pl.DataFrame | None = None,
        kickoff_data: pl.DataFrame | None = None,
    ) -> dict:
        """Build all distributions from raw data.

        Pass dataframes directly for testing, or leave None to load from nflreadpy.
        """
        if pbp is None:
            pbp = self.loader.load_pbp(self.seasons)
        if fg_data is None:
            fg_data = pbp.filter(pl.col("play_type") == "field_goal")
        if kickoff_data is None:
            kickoff_data = pbp.filter(pl.col("play_type") == "kickoff")

        return {
            "play_calling": self.preprocessor.compute_play_calling(pbp),
            "play_outcomes": self.preprocessor.compute_play_outcomes(pbp),
            "turnover_rates": self.preprocessor.compute_turnover_rates(pbp),
            "kicking": self.preprocessor.compute_kicking_model(fg_data),
            "drive_start": self.preprocessor.compute_drive_start_model(kickoff_data),
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_pipeline.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/pipeline.py tests/test_data/test_pipeline.py
git commit -m "feat: add data pipeline orchestrator"
```

---

### Task 9: Sanity Validation Script + Integration Test

**Files:**
- Create: `scripts/validate_data.py`
- Create: `tests/test_data/test_validation_sanity.py`

- [ ] **Step 1: Write sanity check tests using fixture data (fast, no network)**

```python
# tests/test_data/test_validation_sanity.py
import pytest
from fantasy_sim.data.preprocessor import Preprocessor


class TestSanityChecks:
    def test_play_calling_probs_are_valid(self, sample_pbp):
        pre = Preprocessor()
        dists = pre.compute_play_calling(sample_pbp)

        for team, dist in dists.items():
            assert sum(dist.default.values()) == pytest.approx(1.0, abs=0.01)
            for prob in dist.default.values():
                assert 0.0 <= prob <= 1.0

    def test_play_outcomes_have_data(self, sample_pbp):
        pre = Preprocessor()
        dist = pre.compute_play_outcomes(sample_pbp)

        assert len(dist.defaults) >= 2
        for play_type, arr in dist.defaults.items():
            assert len(arr) > 0

    def test_turnover_rates_are_valid_probabilities(self, sample_pbp):
        pre = Preprocessor()
        rates = pre.compute_turnover_rates(sample_pbp)

        for team, r in rates.items():
            assert 0.0 <= r.int_rate <= 1.0
            assert 0.0 <= r.fumble_rate <= 1.0
            assert 0.0 <= r.sack_rate <= 1.0
            assert 0.0 <= r.sack_fumble_rate <= 1.0

    def test_kicking_model_rates_are_valid(self, sample_field_goals):
        pre = Preprocessor()
        model = pre.compute_kicking_model(sample_field_goals)

        for bucket, rate in model.fg_make_rate.items():
            assert 0.0 <= rate <= 1.0
        assert 0.0 <= model.xp_rate <= 1.0

    def test_drive_start_yardlines_are_valid(self, sample_kickoffs):
        pre = Preprocessor()
        model = pre.compute_drive_start_model(sample_kickoffs)

        assert 0.0 <= model.touchback_rate <= 1.0
        assert 1 <= model.touchback_yardline <= 99
        for yl in model.return_yardlines:
            assert 1 <= yl <= 99
```

- [ ] **Step 2: Run sanity tests**

Run: `uv run pytest tests/test_data/test_validation_sanity.py -v`
Expected: All PASS

- [ ] **Step 3: Write the integration validation script**

```python
# scripts/validate_data.py
"""Sanity-check preprocessed distributions against known NFL averages.

Run: uv run python scripts/validate_data.py
Requires network access to download nflverse data on first run.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from fantasy_sim.data.loader import DataLoader
from fantasy_sim.data.preprocessor import Preprocessor


def main():
    seasons = [2022, 2023, 2024]
    print(f"Loading PBP data for seasons {seasons}...")
    loader = DataLoader()
    pbp = loader.load_pbp(seasons)
    print(f"  Loaded {pbp.shape[0]:,} plays")

    pre = Preprocessor()

    # 1. Play-calling distributions
    print("\n--- Play-Calling Distributions ---")
    dists = pre.compute_play_calling(pbp)
    pass_rates = [d.default["pass"] for d in dists.values()]
    avg_pass_rate = sum(pass_rates) / len(pass_rates)
    print(f"  League avg pass rate: {avg_pass_rate:.1%}")
    assert 0.50 <= avg_pass_rate <= 0.65, f"Pass rate {avg_pass_rate:.1%} out of expected range (50-65%)"
    print("  PASS: Pass rate in expected range (50-65%)")

    # 2. Play outcome distributions
    print("\n--- Play Outcome Distributions ---")
    outcomes = pre.compute_play_outcomes(pbp)
    avg_pass_yards = outcomes.defaults["pass"].mean()
    avg_run_yards = outcomes.defaults["run"].mean()
    print(f"  Avg yards per pass attempt: {avg_pass_yards:.1f}")
    print(f"  Avg yards per rush attempt: {avg_run_yards:.1f}")
    assert 4.0 <= avg_pass_yards <= 9.0, f"Pass yards {avg_pass_yards:.1f} out of range"
    assert 3.0 <= avg_run_yards <= 6.0, f"Run yards {avg_run_yards:.1f} out of range"
    print("  PASS: Yards per attempt in expected ranges")

    # 3. Turnover rates
    print("\n--- Turnover Rates ---")
    rates = pre.compute_turnover_rates(pbp)
    avg_int_rate = sum(r.int_rate for r in rates.values()) / len(rates)
    avg_sack_rate = sum(r.sack_rate for r in rates.values()) / len(rates)
    avg_fumble_rate = sum(r.fumble_rate for r in rates.values()) / len(rates)
    print(f"  League avg INT rate: {avg_int_rate:.1%}")
    print(f"  League avg sack rate: {avg_sack_rate:.1%}")
    print(f"  League avg fumble rate: {avg_fumble_rate:.1%}")
    assert 0.01 <= avg_int_rate <= 0.05, f"INT rate {avg_int_rate:.1%} out of range"
    assert 0.03 <= avg_sack_rate <= 0.10, f"Sack rate {avg_sack_rate:.1%} out of range"
    print("  PASS: Turnover rates in expected ranges")

    # 4. Kicking model
    print("\n--- Kicking Model ---")
    fg_plays = pbp.filter(pbp["play_type"] == "field_goal")
    kicking = pre.compute_kicking_model(fg_plays)
    print(f"  FG make rate 0-39: {kicking.fg_make_rate['0_39']:.1%}")
    print(f"  FG make rate 40-49: {kicking.fg_make_rate['40_49']:.1%}")
    print(f"  FG make rate 50+: {kicking.fg_make_rate['50_plus']:.1%}")
    assert kicking.fg_make_rate["0_39"] > kicking.fg_make_rate["40_49"] > kicking.fg_make_rate["50_plus"]
    print("  PASS: FG rates decrease with distance")

    # 5. Drive start model
    print("\n--- Drive Start Model ---")
    ko_plays = pbp.filter(pbp["play_type"] == "kickoff")
    drive_start = pre.compute_drive_start_model(ko_plays)
    print(f"  Touchback rate: {drive_start.touchback_rate:.1%}")
    print(f"  Touchback yardline: own {100 - drive_start.touchback_yardline}")
    print(f"  Avg return start: own {100 - drive_start.return_yardlines.mean():.0f}")
    assert 0.30 <= drive_start.touchback_rate <= 0.80
    print("  PASS: Touchback rate in expected range")

    print("\n=== ALL SANITY CHECKS PASSED ===")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Commit**

```bash
git add scripts/validate_data.py tests/test_data/test_validation_sanity.py
git commit -m "feat: add data sanity validation script and tests"
```

- [ ] **Step 5: Run full Phase 1 test suite**

Run: `uv run pytest tests/test_models/ tests/test_data/ -v`
Expected: All PASS

- [ ] **Step 6: Run integration validation (requires network, marked integration)**

Run: `uv run python scripts/validate_data.py`
Expected: All sanity checks pass. Output shows NFL-realistic averages.

---

## Phase 2-6 Roadmap

Detailed plans for subsequent phases will be written when starting each phase, as they depend on actual code from prior phases. Task outline:

### Phase 2: Game State Machine
1. `GameState` dataclass with transition methods
2. Coin toss and kickoff logic
3. Play selection (run/pass/4th-down decision) using `PlayCallingDist`
4. Play resolution (yards, completion, sack) using `PlayOutcomeDist`
5. Touchdown, field goal, and safety scoring
6. Possession change (turnover, punt, score, downs)
7. Clock management (runoff, two-minute warning)
8. PAT/2-point conversion
9. Overtime rules (current NFL format)
10. Full game loop (`GameSimulator.simulate_game()`)
11. Statistical validation: bulk-sim 10k games, verify averages

### Phase 3: Player Models
1. Player usage model (target/carry share by game state)
2. Player outcome distributions (catch rate, YAC, etc.)
3. Rookie archetype system (draft capital + depth chart)
4. Player selection integration into game sim
5. Box score accumulation (per-player stat tracking)
6. Statistical validation: player-level stat plausibility

### Phase 4: Scoring + Config + CLI
1. YAML config loader with inheritance
2. Scoring engine (stats -> fantasy points)
3. CLI framework (click subcommands: week/season/game/player)
4. Terminal table output (rich)
5. CSV/JSON export
6. End-to-end integration test

### Phase 5: Validation + Tuning
1. Backtest harness (hold-out season, no data leakage)
2. Accuracy metrics (Spearman correlation, MAE, calibration)
3. Validation report generator
4. Tuning loop: adjust distributions until benchmarks pass

### Phase 6: Overrides + Polish
1. Player override system (target share, games missed)
2. Team override system (pace, pass rate)
3. Override redistribution logic
4. CLI `--override` flag with fuzzy player name matching
5. Progress bars, error messages, README

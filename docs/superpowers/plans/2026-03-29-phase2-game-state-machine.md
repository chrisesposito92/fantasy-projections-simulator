# Phase 2: Game State Machine — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the core play-by-play simulation engine that takes team-level distributions (from Phase 1) and simulates full NFL games, producing team box scores. No individual player attribution yet — that's Phase 3.

**Architecture:** A `GameState` dataclass tracks mutable game state (quarter, clock, score, field position). Each play flows through: play caller (select run/pass or 4th-down decision) → play resolver (determine outcome: yards, sack, turnover, TD, safety) → game flow (apply scoring, possession changes, kickoffs) → clock manager (runoff, quarter transitions). A `simulate_game()` function orchestrates the loop, and `run_simulations()` runs N games for Monte Carlo output.

**Tech Stack:** Python 3.14, numpy (random sampling), pytest, existing Phase 1 distribution types

---

## File Structure

```
src/fantasy_sim/engine/
├── __init__.py              (already exists)
├── types.py                 # GameState, TeamBoxScore, PlayResult, GameResult, TeamDistributions
├── play_caller.py           # select_play_type, fourth_down_decision
├── play_resolver.py         # resolve_pass, resolve_run → PlayResult
├── game_flow.py             # Kickoff, punt, FG, PAT/2PT, scoring, possession changes, apply yards
├── clock.py                 # Clock runoff, quarter/half/game transitions, two-minute warning
├── game_sim.py              # simulate_game() → GameResult (main loop + OT)
└── monte_carlo.py           # run_simulations() → list[GameResult], aggregate stats

tests/test_engine/
├── test_types.py
├── test_play_caller.py
├── test_play_resolver.py
├── test_game_flow.py
├── test_clock.py
├── test_game_sim.py
└── test_monte_carlo.py
```

## Dependencies from Phase 1

These types are imported from Phase 1 and used throughout:

- `fantasy_sim.models.game_state.bucket_play` — Converts raw game state to a `GameStateBucket` for distribution lookups
- `fantasy_sim.models.distributions.PlayCallingDist` — `get_probs(bucket)` returns `{"pass": float, "run": float}`
- `fantasy_sim.models.distributions.PlayOutcomeDist` — `sample_yards(play_type, bucket, rng)` returns `int`
- `fantasy_sim.models.distributions.TurnoverRates` — `int_rate`, `fumble_rate`, `sack_rate`, `sack_fumble_rate` (all floats)
- `fantasy_sim.models.distributions.KickingModel` — `fg_prob(distance)` returns `float`, `xp_rate` is `float`
- `fantasy_sim.models.distributions.DriveStartModel` — `sample_start_yardline(rng)` returns `int` (yardline_100 format)

**yardline_100 convention** (used everywhere):
- 99 = own 1-yard line (backed up)
- 75 = own 25 (typical kickoff touchback)
- 50 = midfield
- 20 = opponent's 20 (red zone)
- 1 = opponent's 1 (goal line)
- After a play: `new_yard_line = yard_line - yards_gained` (positive yards decrease yardline_100)
- TD: `yard_line - yards <= 0`
- Safety: `yard_line - yards >= 100` (only when yards is negative)

---

### Task 1: Core Types

**Files:**
- Create: `src/fantasy_sim/engine/types.py`
- Create: `tests/test_engine/test_types.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_engine/test_types.py
import numpy as np
import pytest
from fantasy_sim.engine.types import (
    GameState, TeamBoxScore, PlayResult, GameResult, TeamDistributions,
)
from fantasy_sim.models.distributions import (
    PlayCallingDist, PlayOutcomeDist, TurnoverRates, KickingModel, DriveStartModel,
)
from fantasy_sim.models.game_state import GameStateBucket


class TestGameState:
    def test_initial_state(self):
        state = GameState(
            quarter=1, clock=900, possession="home",
            down=1, distance=10, yard_line=75,
            home_score=0, away_score=0,
            home_team="KC", away_team="BUF",
            receiving_2nd_half="away",
        )
        assert state.quarter == 1
        assert state.clock == 900
        assert not state.game_over

    def test_score_differential_home(self):
        state = GameState(
            quarter=1, clock=900, possession="home",
            down=1, distance=10, yard_line=75,
            home_score=14, away_score=7,
            home_team="KC", away_team="BUF",
            receiving_2nd_half="away",
        )
        assert state.score_differential == 7

    def test_score_differential_away(self):
        state = GameState(
            quarter=1, clock=900, possession="away",
            down=1, distance=10, yard_line=75,
            home_score=14, away_score=7,
            home_team="KC", away_team="BUF",
            receiving_2nd_half="away",
        )
        assert state.score_differential == -7

    def test_offense_defense(self):
        state = GameState(
            quarter=1, clock=900, possession="home",
            down=1, distance=10, yard_line=75,
            home_score=0, away_score=0,
            home_team="KC", away_team="BUF",
            receiving_2nd_half="away",
        )
        assert state.offense == "home"
        assert state.defense == "away"


class TestTeamBoxScore:
    def test_defaults_to_zero(self):
        box = TeamBoxScore()
        assert box.pass_attempts == 0
        assert box.rush_yards == 0
        assert box.points == 0
        assert box.sacks_made == 0

    def test_mutable(self):
        box = TeamBoxScore()
        box.pass_attempts += 1
        box.pass_yards += 250
        box.points += 7
        assert box.pass_attempts == 1
        assert box.pass_yards == 250


class TestPlayResult:
    def test_normal_completion(self):
        result = PlayResult(play_type="pass", yards=12, is_complete=True, clock_runoff=35)
        assert result.yards == 12
        assert result.is_complete
        assert not result.is_sack
        assert not result.is_touchdown

    def test_touchdown_run(self):
        result = PlayResult(play_type="run", yards=5, is_touchdown=True, clock_runoff=38)
        assert result.is_touchdown
        assert result.yards == 5


class TestTeamDistributions:
    def test_bundles_all_distributions(self):
        bucket = GameStateBucket(1, "long", "tied", 1, "own_territory")
        td = TeamDistributions(
            play_calling=PlayCallingDist(team="KC", distributions={bucket: {"pass": 0.6, "run": 0.4}}),
            play_outcomes=PlayOutcomeDist(distributions={}, defaults={"pass": np.array([5]), "run": np.array([3])}),
            turnover_rates=TurnoverRates(team="KC", int_rate=0.025, fumble_rate=0.01, sack_rate=0.06, sack_fumble_rate=0.10),
            kicking=KickingModel(fg_make_rate={"0_39": 0.95, "40_49": 0.82, "50_plus": 0.65}, xp_rate=0.94),
            drive_start=DriveStartModel(touchback_rate=0.55, touchback_yardline=75, return_yardlines=np.array([72, 78])),
        )
        assert td.play_calling.team == "KC"
        assert td.kicking.xp_rate == pytest.approx(0.94)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_engine/test_types.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement types**

```python
# src/fantasy_sim/engine/types.py
from dataclasses import dataclass, field
from fantasy_sim.models.distributions import (
    PlayCallingDist, PlayOutcomeDist, TurnoverRates, KickingModel, DriveStartModel,
)


@dataclass
class TeamDistributions:
    """All distributions needed to simulate one team."""
    play_calling: PlayCallingDist
    play_outcomes: PlayOutcomeDist
    turnover_rates: TurnoverRates
    kicking: KickingModel
    drive_start: DriveStartModel


@dataclass
class GameState:
    """Mutable game state updated on every play."""
    quarter: int            # 1-4 regulation, 5 = overtime
    clock: int              # seconds remaining in quarter (900 per quarter)
    possession: str         # "home" | "away"
    down: int               # 1-4
    distance: int           # yards to first down
    yard_line: int          # yardline_100: 99=own 1, 50=midfield, 1=opp 1
    home_score: int
    away_score: int
    home_team: str
    away_team: str
    receiving_2nd_half: str  # "home" | "away"
    game_over: bool = False

    @property
    def score_differential(self) -> int:
        """Score diff from perspective of possessing team (positive = winning)."""
        if self.possession == "home":
            return self.home_score - self.away_score
        return self.away_score - self.home_score

    @property
    def offense(self) -> str:
        return self.possession

    @property
    def defense(self) -> str:
        return "away" if self.possession == "home" else "home"


@dataclass
class PlayResult:
    """Outcome of a single play."""
    play_type: str          # "pass" | "run"
    yards: int
    is_complete: bool = False
    is_sack: bool = False
    is_interception: bool = False
    is_fumble: bool = False
    is_touchdown: bool = False
    is_safety: bool = False
    clock_runoff: int = 0


@dataclass
class TeamBoxScore:
    """Accumulated team-level stats for one game."""
    # Offensive
    pass_attempts: int = 0
    completions: int = 0
    pass_yards: int = 0
    pass_tds: int = 0
    interceptions_thrown: int = 0
    sacks_taken: int = 0
    sack_yards: int = 0
    rush_attempts: int = 0
    rush_yards: int = 0
    rush_tds: int = 0
    fumbles_lost: int = 0
    fg_attempts: int = 0
    fg_made: int = 0
    xp_attempts: int = 0
    xp_made: int = 0
    punts: int = 0
    points: int = 0
    # Defensive
    sacks_made: int = 0
    interceptions_caught: int = 0
    fumbles_recovered: int = 0
    safeties: int = 0


@dataclass
class GameResult:
    """Final result of one simulated game."""
    home_score: int
    away_score: int
    home_box: TeamBoxScore
    away_box: TeamBoxScore
    total_plays: int
    overtime: bool
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_engine/test_types.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/engine/types.py tests/test_engine/test_types.py
git commit -m "feat: add game engine core types"
```

---

### Task 2: Play Caller

**Files:**
- Create: `src/fantasy_sim/engine/play_caller.py`
- Create: `tests/test_engine/test_play_caller.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_engine/test_play_caller.py
import numpy as np
import pytest
from fantasy_sim.engine.play_caller import select_play_type, fourth_down_decision
from fantasy_sim.engine.types import GameState
from fantasy_sim.models.distributions import PlayCallingDist, KickingModel
from fantasy_sim.models.game_state import GameStateBucket


def make_state(**overrides) -> GameState:
    defaults = dict(
        quarter=1, clock=900, possession="home",
        down=1, distance=10, yard_line=75,
        home_score=0, away_score=0,
        home_team="KC", away_team="BUF",
        receiving_2nd_half="away",
    )
    defaults.update(overrides)
    return GameState(**defaults)


def make_play_calling(pass_rate: float = 0.6) -> PlayCallingDist:
    return PlayCallingDist(
        team="KC", distributions={},
        default={"pass": pass_rate, "run": 1 - pass_rate},
    )


def make_kicking() -> KickingModel:
    return KickingModel(
        fg_make_rate={"0_39": 0.95, "40_49": 0.82, "50_plus": 0.65},
        xp_rate=0.94,
    )


class TestSelectPlayType:
    def test_returns_pass_or_run(self):
        rng = np.random.default_rng(42)
        state = make_state()
        play_calling = make_play_calling()
        result = select_play_type(state, play_calling, rng)
        assert result in ("pass", "run")

    def test_respects_distribution(self):
        """With 100% pass rate, should always return pass."""
        rng = np.random.default_rng(42)
        state = make_state()
        play_calling = make_play_calling(pass_rate=1.0)
        results = [select_play_type(state, play_calling, rng) for _ in range(100)]
        assert all(r == "pass" for r in results)

    def test_uses_game_state_for_bucket(self):
        """Different game states should produce different buckets for lookup."""
        rng = np.random.default_rng(42)
        bucket = GameStateBucket(3, "long", "down_big", 4, "own_territory")
        play_calling = PlayCallingDist(
            team="KC",
            distributions={bucket: {"pass": 0.95, "run": 0.05}},
            default={"pass": 0.5, "run": 0.5},
        )
        state = make_state(down=3, distance=10, yard_line=60, quarter=4,
                          home_score=0, away_score=21)
        results = [select_play_type(state, play_calling, rng) for _ in range(100)]
        pass_rate = sum(1 for r in results if r == "pass") / 100
        assert pass_rate > 0.85


class TestFourthDownDecision:
    def test_punt_from_own_territory(self):
        state = make_state(down=4, distance=5, yard_line=70)
        assert fourth_down_decision(state, make_kicking()) == "punt"

    def test_fg_from_makeable_range(self):
        """yard_line=30 → FG distance = 30 + 17 = 47 yards. Should attempt."""
        state = make_state(down=4, distance=5, yard_line=30)
        assert fourth_down_decision(state, make_kicking()) == "field_goal"

    def test_go_for_it_short_yardage_in_opp_territory(self):
        """4th and 1 at opponent's 40."""
        state = make_state(down=4, distance=1, yard_line=40)
        assert fourth_down_decision(state, make_kicking()) == "go_for_it"

    def test_go_for_it_near_goal_line(self):
        """4th and 2 at the opponent's 3."""
        state = make_state(down=4, distance=2, yard_line=3)
        assert fourth_down_decision(state, make_kicking()) == "go_for_it"

    def test_punt_on_long_yardage(self):
        """4th and 15 at opponent's 40 — too long to go for it, too far for FG."""
        state = make_state(down=4, distance=15, yard_line=40)
        assert fourth_down_decision(state, make_kicking()) == "punt"

    def test_fg_attempt_at_long_range_declined(self):
        """yard_line=45 → FG distance = 62 yards. Too far, should punt."""
        state = make_state(down=4, distance=5, yard_line=45)
        assert fourth_down_decision(state, make_kicking()) == "punt"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_engine/test_play_caller.py -v`
Expected: FAIL

- [ ] **Step 3: Implement play caller**

```python
# src/fantasy_sim/engine/play_caller.py
import numpy as np
from fantasy_sim.engine.types import GameState
from fantasy_sim.models.distributions import PlayCallingDist, KickingModel
from fantasy_sim.models.game_state import bucket_play


def select_play_type(
    state: GameState, play_calling: PlayCallingDist, rng: np.random.Generator
) -> str:
    """Select run or pass based on game state and team tendencies."""
    bucket = bucket_play(
        state.down, state.distance, state.score_differential,
        state.quarter, state.yard_line,
    )
    probs = play_calling.get_probs(bucket)
    play_types = list(probs.keys())
    probabilities = list(probs.values())
    return rng.choice(play_types, p=probabilities)


def fourth_down_decision(state: GameState, kicking: KickingModel) -> str:
    """Decide punt, field_goal, or go_for_it on 4th down."""
    fg_distance = state.yard_line + 17  # 7yd snap + 10yd end zone

    # Attempt FG if distance is reasonable and probability is decent
    if fg_distance <= 55:
        if kicking.fg_prob(fg_distance) >= 0.40:
            return "field_goal"

    # Go for it on short yardage in opponent's half
    if state.distance <= 2 and state.yard_line <= 45:
        return "go_for_it"

    # Go for it near the goal line (inside the 5, short yardage)
    if state.yard_line <= 5 and state.distance <= 3:
        return "go_for_it"

    return "punt"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_engine/test_play_caller.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/engine/play_caller.py tests/test_engine/test_play_caller.py
git commit -m "feat: add play caller with 4th down decisions"
```

---

### Task 3: Play Resolver

**Files:**
- Create: `src/fantasy_sim/engine/play_resolver.py`
- Create: `tests/test_engine/test_play_resolver.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_engine/test_play_resolver.py
import numpy as np
import pytest
from fantasy_sim.engine.play_resolver import resolve_play
from fantasy_sim.engine.types import GameState, PlayResult
from fantasy_sim.models.distributions import PlayOutcomeDist, TurnoverRates
from fantasy_sim.models.game_state import GameStateBucket


def make_state(**overrides) -> GameState:
    defaults = dict(
        quarter=1, clock=900, possession="home",
        down=1, distance=10, yard_line=75,
        home_score=0, away_score=0,
        home_team="KC", away_team="BUF",
        receiving_2nd_half="away",
    )
    defaults.update(overrides)
    return GameState(**defaults)


def make_outcomes(pass_yards=None, run_yards=None) -> PlayOutcomeDist:
    defaults = {}
    if pass_yards is not None:
        defaults["pass"] = np.array(pass_yards)
    else:
        defaults["pass"] = np.array([5, 8, 10, 12, 0, 15, -2, 20, 7, 3])
    if run_yards is not None:
        defaults["run"] = np.array(run_yards)
    else:
        defaults["run"] = np.array([3, 4, 5, -1, 2, 7, 1, 6, 0, 8])
    return PlayOutcomeDist(distributions={}, defaults=defaults)


def make_turnover_rates(**overrides) -> TurnoverRates:
    defaults = dict(team="KC", int_rate=0.0, fumble_rate=0.0, sack_rate=0.0, sack_fumble_rate=0.0)
    defaults.update(overrides)
    return TurnoverRates(**defaults)


class TestResolvePass:
    def test_normal_completion(self):
        rng = np.random.default_rng(42)
        state = make_state()
        outcomes = make_outcomes(pass_yards=[10])  # Always 10 yards
        rates = make_turnover_rates()  # No turnovers
        result = resolve_play(state, "pass", outcomes, rates, rng)
        assert result.play_type == "pass"
        assert result.yards == 10
        assert result.is_complete
        assert not result.is_sack

    def test_incomplete_pass(self):
        rng = np.random.default_rng(42)
        state = make_state()
        outcomes = make_outcomes(pass_yards=[0])  # Always 0 yards = incomplete
        rates = make_turnover_rates()
        result = resolve_play(state, "pass", outcomes, rates, rng)
        assert result.yards == 0
        assert not result.is_complete

    def test_sack(self):
        rng = np.random.default_rng(42)
        state = make_state()
        outcomes = make_outcomes()
        rates = make_turnover_rates(sack_rate=1.0)  # Always sacked
        result = resolve_play(state, "pass", outcomes, rates, rng)
        assert result.is_sack
        assert result.yards < 0

    def test_interception(self):
        rng = np.random.default_rng(42)
        state = make_state()
        outcomes = make_outcomes()
        rates = make_turnover_rates(int_rate=1.0)  # Always INT
        result = resolve_play(state, "pass", outcomes, rates, rng)
        assert result.is_interception
        assert result.yards == 0

    def test_sack_checked_before_int(self):
        """If sack_rate=1.0 and int_rate=1.0, sack should take priority."""
        rng = np.random.default_rng(42)
        state = make_state()
        outcomes = make_outcomes()
        rates = make_turnover_rates(sack_rate=1.0, int_rate=1.0)
        result = resolve_play(state, "pass", outcomes, rates, rng)
        assert result.is_sack
        assert not result.is_interception

    def test_pass_touchdown(self):
        rng = np.random.default_rng(42)
        state = make_state(yard_line=5)  # 5 yards from end zone
        outcomes = make_outcomes(pass_yards=[10])  # Gain 10 = TD
        rates = make_turnover_rates()
        result = resolve_play(state, "pass", outcomes, rates, rng)
        assert result.is_touchdown
        assert result.yards == 5  # Clamped to end zone

    def test_safety_on_sack(self):
        rng = np.random.default_rng(42)
        state = make_state(yard_line=97)  # Own 3-yard line
        outcomes = make_outcomes()
        rates = make_turnover_rates(sack_rate=1.0)
        result = resolve_play(state, "pass", outcomes, rates, rng)
        assert result.is_sack
        assert result.is_safety


class TestResolveRun:
    def test_normal_run(self):
        rng = np.random.default_rng(42)
        state = make_state()
        outcomes = make_outcomes(run_yards=[5])
        rates = make_turnover_rates()
        result = resolve_play(state, "run", outcomes, rates, rng)
        assert result.play_type == "run"
        assert result.yards == 5
        assert not result.is_fumble

    def test_run_fumble(self):
        rng = np.random.default_rng(42)
        state = make_state()
        outcomes = make_outcomes(run_yards=[5])
        rates = make_turnover_rates(fumble_rate=1.0)
        result = resolve_play(state, "run", outcomes, rates, rng)
        assert result.is_fumble

    def test_run_touchdown(self):
        rng = np.random.default_rng(42)
        state = make_state(yard_line=3)
        outcomes = make_outcomes(run_yards=[5])
        rates = make_turnover_rates()
        result = resolve_play(state, "run", outcomes, rates, rng)
        assert result.is_touchdown
        assert result.yards == 3  # Clamped to end zone

    def test_fumble_cancels_td(self):
        rng = np.random.default_rng(42)
        state = make_state(yard_line=3)
        outcomes = make_outcomes(run_yards=[5])
        rates = make_turnover_rates(fumble_rate=1.0)
        result = resolve_play(state, "run", outcomes, rates, rng)
        assert result.is_fumble
        assert not result.is_touchdown

    def test_run_safety(self):
        rng = np.random.default_rng(42)
        state = make_state(yard_line=98)  # Own 2
        outcomes = make_outcomes(run_yards=[-5])
        rates = make_turnover_rates()
        result = resolve_play(state, "run", outcomes, rates, rng)
        assert result.is_safety

    def test_clock_runoff_pass_complete(self):
        rng = np.random.default_rng(42)
        state = make_state()
        outcomes = make_outcomes(pass_yards=[10])
        rates = make_turnover_rates()
        result = resolve_play(state, "pass", outcomes, rates, rng)
        assert result.clock_runoff > 0

    def test_clock_runoff_run(self):
        rng = np.random.default_rng(42)
        state = make_state()
        outcomes = make_outcomes(run_yards=[5])
        rates = make_turnover_rates()
        result = resolve_play(state, "run", outcomes, rates, rng)
        assert result.clock_runoff > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_engine/test_play_resolver.py -v`
Expected: FAIL

- [ ] **Step 3: Implement play resolver**

```python
# src/fantasy_sim/engine/play_resolver.py
import numpy as np
from fantasy_sim.engine.types import GameState, PlayResult
from fantasy_sim.models.distributions import PlayOutcomeDist, TurnoverRates
from fantasy_sim.models.game_state import bucket_play

# Average clock runoff in seconds
CLOCK_RUN = 38
CLOCK_PASS_COMPLETE = 35
CLOCK_PASS_INCOMPLETE = 7
CLOCK_SACK = 38

# Sack yardage loss distribution
SACK_YARDS = np.array([-3, -4, -5, -5, -6, -7, -7, -8, -8, -10])


def resolve_play(
    state: GameState,
    play_type: str,
    play_outcomes: PlayOutcomeDist,
    turnover_rates: TurnoverRates,
    rng: np.random.Generator,
) -> PlayResult:
    if play_type == "pass":
        return _resolve_pass(state, play_outcomes, turnover_rates, rng)
    return _resolve_run(state, play_outcomes, turnover_rates, rng)


def _resolve_pass(
    state: GameState,
    play_outcomes: PlayOutcomeDist,
    turnover_rates: TurnoverRates,
    rng: np.random.Generator,
) -> PlayResult:
    # Check for sack first
    if rng.random() < turnover_rates.sack_rate:
        yards = int(rng.choice(SACK_YARDS))
        is_fumble = rng.random() < turnover_rates.sack_fumble_rate
        new_yl = state.yard_line - yards  # yards is negative, so this increases
        is_safety = new_yl >= 100
        return PlayResult(
            play_type="pass", yards=yards, is_sack=True,
            is_fumble=is_fumble, is_safety=is_safety,
            clock_runoff=CLOCK_SACK,
        )

    # Check for interception
    if rng.random() < turnover_rates.int_rate:
        return PlayResult(
            play_type="pass", yards=0, is_interception=True,
            clock_runoff=CLOCK_PASS_INCOMPLETE,
        )

    # Normal pass
    bucket = bucket_play(
        state.down, state.distance, state.score_differential,
        state.quarter, state.yard_line,
    )
    yards = play_outcomes.sample_yards("pass", bucket, rng)
    yards = _clamp_yards(state.yard_line, yards)

    is_complete = yards > 0
    is_td = (state.yard_line - yards) <= 0

    # Fumble check on completions
    is_fumble = False
    if is_complete and rng.random() < turnover_rates.fumble_rate:
        is_fumble = True

    return PlayResult(
        play_type="pass", yards=yards,
        is_complete=is_complete,
        is_touchdown=is_td and not is_fumble,
        is_fumble=is_fumble,
        clock_runoff=CLOCK_PASS_COMPLETE if is_complete else CLOCK_PASS_INCOMPLETE,
    )


def _resolve_run(
    state: GameState,
    play_outcomes: PlayOutcomeDist,
    turnover_rates: TurnoverRates,
    rng: np.random.Generator,
) -> PlayResult:
    bucket = bucket_play(
        state.down, state.distance, state.score_differential,
        state.quarter, state.yard_line,
    )
    yards = play_outcomes.sample_yards("run", bucket, rng)
    yards = _clamp_yards(state.yard_line, yards)

    is_td = (state.yard_line - yards) <= 0
    is_safety = (state.yard_line - yards) >= 100
    is_fumble = rng.random() < turnover_rates.fumble_rate

    return PlayResult(
        play_type="run", yards=yards,
        is_touchdown=is_td and not is_fumble,
        is_fumble=is_fumble,
        is_safety=is_safety,
        clock_runoff=CLOCK_RUN,
    )


def _clamp_yards(yard_line: int, yards: int) -> int:
    """Clamp yards so play doesn't go past either end zone."""
    # Can't gain more than distance to opponent's end zone
    if yards > yard_line:
        yards = yard_line
    # Can't lose past own end zone (safety is handled separately)
    max_loss = -(99 - yard_line)
    if yards < max_loss:
        yards = max_loss
    return yards
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_engine/test_play_resolver.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/engine/play_resolver.py tests/test_engine/test_play_resolver.py
git commit -m "feat: add play resolver for pass and run outcomes"
```

---

### Task 4: Game Flow (Scoring, Possession, Special Plays)

**Files:**
- Create: `src/fantasy_sim/engine/game_flow.py`
- Create: `tests/test_engine/test_game_flow.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_engine/test_game_flow.py
import numpy as np
import pytest
from fantasy_sim.engine.game_flow import (
    apply_yards, change_possession, score_points,
    handle_turnover, perform_kickoff, perform_punt,
    attempt_field_goal, attempt_pat,
)
from fantasy_sim.engine.types import GameState, TeamBoxScore, PlayResult
from fantasy_sim.models.distributions import KickingModel, DriveStartModel


def make_state(**overrides) -> GameState:
    defaults = dict(
        quarter=1, clock=900, possession="home",
        down=1, distance=10, yard_line=75,
        home_score=0, away_score=0,
        home_team="KC", away_team="BUF",
        receiving_2nd_half="away",
    )
    defaults.update(overrides)
    return GameState(**defaults)


def make_drive_start() -> DriveStartModel:
    return DriveStartModel(
        touchback_rate=1.0, touchback_yardline=75,
        return_yardlines=np.array([75]),
    )


def make_kicking(**overrides) -> KickingModel:
    defaults = dict(
        fg_make_rate={"0_39": 0.95, "40_49": 0.82, "50_plus": 0.65},
        xp_rate=0.94,
    )
    defaults.update(overrides)
    return KickingModel(**defaults)


class TestApplyYards:
    def test_advances_down(self):
        state = make_state(down=1, distance=10, yard_line=75)
        apply_yards(state, 5)
        assert state.yard_line == 70
        assert state.down == 2
        assert state.distance == 5

    def test_first_down(self):
        state = make_state(down=2, distance=5, yard_line=70)
        apply_yards(state, 8)
        assert state.yard_line == 62
        assert state.down == 1
        assert state.distance == 10

    def test_loss_of_yards(self):
        state = make_state(down=1, distance=10, yard_line=70)
        apply_yards(state, -3)
        assert state.yard_line == 73
        assert state.down == 2
        assert state.distance == 13

    def test_turnover_on_downs(self):
        """4th down failed conversion flips possession."""
        state = make_state(down=4, distance=5, yard_line=50)
        apply_yards(state, 3)  # Not enough for first down
        assert state.possession == "away"
        assert state.down == 1
        assert state.distance == 10
        assert state.yard_line == 53  # Flipped: 100 - 47 = 53


class TestChangePossession:
    def test_flips_home_to_away(self):
        state = make_state(possession="home")
        change_possession(state)
        assert state.possession == "away"

    def test_flips_away_to_home(self):
        state = make_state(possession="away")
        change_possession(state)
        assert state.possession == "home"


class TestScorePoints:
    def test_home_scores(self):
        state = make_state(possession="home")
        score_points(state, 7)
        assert state.home_score == 7
        assert state.away_score == 0

    def test_away_scores(self):
        state = make_state(possession="away")
        score_points(state, 3)
        assert state.away_score == 3
        assert state.home_score == 0


class TestHandleTurnover:
    def test_interception_flips_possession(self):
        state = make_state(possession="home", yard_line=50)
        result = PlayResult(play_type="pass", yards=0, is_interception=True)
        handle_turnover(state, result)
        assert state.possession == "away"
        assert state.down == 1
        assert state.distance == 10
        assert state.yard_line == 50  # 100 - 50 = 50 (midfield)

    def test_fumble_flips_possession(self):
        state = make_state(possession="home", yard_line=30)
        result = PlayResult(play_type="run", yards=5, is_fumble=True)
        handle_turnover(state, result)
        assert state.possession == "away"
        assert state.down == 1
        assert state.distance == 10
        # Fumble at yard_line 30 - 5 = 25. Flip: 100 - 25 = 75
        assert state.yard_line == 75


class TestPerformKickoff:
    def test_sets_receiving_team_position(self):
        state = make_state(possession="home")
        rng = np.random.default_rng(42)
        perform_kickoff(state, make_drive_start(), rng)
        assert state.yard_line == 75
        assert state.down == 1
        assert state.distance == 10


class TestPerformPunt:
    def test_flips_possession(self):
        state = make_state(possession="home", yard_line=75)
        rng = np.random.default_rng(42)
        off_box = TeamBoxScore()
        perform_punt(state, rng, off_box)
        assert state.possession == "away"
        assert state.down == 1
        assert state.distance == 10
        assert off_box.punts == 1

    def test_touchback_on_deep_punt(self):
        state = make_state(possession="home", yard_line=30)
        # Use a fixed rng that will produce a long punt
        rng = np.random.default_rng(42)
        off_box = TeamBoxScore()
        perform_punt(state, rng, off_box)
        assert state.possession == "away"
        assert 70 <= state.yard_line <= 80  # Touchback at own 20-25


class TestAttemptFieldGoal:
    def test_made_fg(self):
        state = make_state(possession="home", yard_line=20)
        rng = np.random.default_rng(42)
        off_box = TeamBoxScore()
        kicking = make_kicking(fg_make_rate={"0_39": 1.0, "40_49": 1.0, "50_plus": 1.0})
        drive_start = make_drive_start()
        attempt_field_goal(state, kicking, drive_start, rng, off_box)
        assert state.home_score == 3
        assert off_box.fg_made == 1
        assert off_box.fg_attempts == 1
        assert off_box.points == 3

    def test_missed_fg_gives_opponent_ball(self):
        state = make_state(possession="home", yard_line=40)
        rng = np.random.default_rng(42)
        off_box = TeamBoxScore()
        kicking = make_kicking(fg_make_rate={"0_39": 0.0, "40_49": 0.0, "50_plus": 0.0})
        drive_start = make_drive_start()
        attempt_field_goal(state, kicking, drive_start, rng, off_box)
        assert state.home_score == 0
        assert state.possession == "away"
        assert off_box.fg_made == 0
        assert off_box.fg_attempts == 1


class TestAttemptPat:
    def test_xp_made(self):
        state = make_state(possession="home", home_score=6)
        rng = np.random.default_rng(42)
        off_box = TeamBoxScore(points=6)
        kicking = make_kicking(xp_rate=1.0)
        attempt_pat(state, kicking, rng, off_box)
        assert state.home_score >= 7  # Either XP (7) or 2PT (8)
        assert off_box.points >= 7
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_engine/test_game_flow.py -v`
Expected: FAIL

- [ ] **Step 3: Implement game flow**

```python
# src/fantasy_sim/engine/game_flow.py
import numpy as np
from fantasy_sim.engine.types import GameState, TeamBoxScore, PlayResult
from fantasy_sim.models.distributions import KickingModel, DriveStartModel

# Punt net yards distribution
PUNT_NET_YARDS = np.array([35, 38, 40, 42, 44, 45, 45, 46, 48, 50, 52, 55])

# PAT/2PT constants
TWO_POINT_ATTEMPT_RATE = 0.06
TWO_POINT_SUCCESS_RATE = 0.48


def apply_yards(state: GameState, yards: int) -> None:
    """Apply yards gained to game state. Handles first downs and turnover on downs."""
    state.yard_line -= yards

    if yards >= state.distance:
        # First down
        state.down = 1
        state.distance = min(10, state.yard_line)  # Can't need more than yards to goal
    elif state.down == 4:
        # Failed 4th down — turnover on downs
        change_possession(state)
        state.yard_line = 100 - state.yard_line
        state.down = 1
        state.distance = 10
    else:
        state.down += 1
        state.distance -= yards


def change_possession(state: GameState) -> None:
    """Flip possession between home and away."""
    state.possession = "away" if state.possession == "home" else "home"


def score_points(state: GameState, points: int) -> None:
    """Add points to the possessing team's score."""
    if state.possession == "home":
        state.home_score += points
    else:
        state.away_score += points


def handle_turnover(state: GameState, result: PlayResult) -> None:
    """Handle interception or fumble — flip possession at the spot."""
    # Determine the spot of the turnover
    spot = state.yard_line - result.yards
    change_possession(state)
    state.yard_line = 100 - spot
    state.down = 1
    state.distance = 10


def perform_kickoff(
    state: GameState, drive_start: DriveStartModel, rng: np.random.Generator
) -> None:
    """Set up receiving team's starting field position after a kickoff."""
    state.yard_line = drive_start.sample_start_yardline(rng)
    state.down = 1
    state.distance = 10


def perform_punt(
    state: GameState, rng: np.random.Generator, off_box: TeamBoxScore
) -> None:
    """Execute a punt and give the ball to the other team."""
    off_box.punts += 1
    net_yards = int(rng.choice(PUNT_NET_YARDS))
    landing_yl = state.yard_line - net_yards

    change_possession(state)

    if landing_yl <= 0:
        # Touchback — opponent starts at own 25
        state.yard_line = 75
    else:
        state.yard_line = 100 - landing_yl

    state.down = 1
    state.distance = 10


def attempt_field_goal(
    state: GameState,
    kicking: KickingModel,
    drive_start: DriveStartModel,
    rng: np.random.Generator,
    off_box: TeamBoxScore,
) -> None:
    """Attempt a field goal. Made = 3 points + kickoff. Missed = opponent takes over."""
    fg_distance = state.yard_line + 17
    off_box.fg_attempts += 1

    if rng.random() < kicking.fg_prob(fg_distance):
        # Made
        off_box.fg_made += 1
        score_points(state, 3)
        off_box.points += 3
        change_possession(state)
        perform_kickoff(state, drive_start, rng)
    else:
        # Missed — opponent takes over at spot of kick (or own 20, whichever better)
        spot = state.yard_line + 7  # Snap spot
        change_possession(state)
        state.yard_line = max(100 - spot, 80)  # At least own 20
        state.down = 1
        state.distance = 10


def attempt_pat(
    state: GameState,
    kicking: KickingModel,
    rng: np.random.Generator,
    off_box: TeamBoxScore,
) -> None:
    """Attempt PAT (extra point or 2-point conversion) after a touchdown."""
    if rng.random() < TWO_POINT_ATTEMPT_RATE:
        # 2-point attempt
        if rng.random() < TWO_POINT_SUCCESS_RATE:
            score_points(state, 2)
            off_box.points += 2
    else:
        # Extra point
        off_box.xp_attempts += 1
        if rng.random() < kicking.xp_rate:
            score_points(state, 1)
            off_box.points += 1
            off_box.xp_made += 1
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_engine/test_game_flow.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/engine/game_flow.py tests/test_engine/test_game_flow.py
git commit -m "feat: add game flow - scoring, possession, kickoff, punt, FG, PAT"
```

---

### Task 5: Clock Management

**Files:**
- Create: `src/fantasy_sim/engine/clock.py`
- Create: `tests/test_engine/test_clock.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_engine/test_clock.py
import numpy as np
import pytest
from fantasy_sim.engine.clock import apply_clock, check_quarter_end
from fantasy_sim.engine.types import GameState
from fantasy_sim.models.distributions import DriveStartModel


def make_state(**overrides) -> GameState:
    defaults = dict(
        quarter=1, clock=900, possession="home",
        down=1, distance=10, yard_line=75,
        home_score=0, away_score=0,
        home_team="KC", away_team="BUF",
        receiving_2nd_half="away",
    )
    defaults.update(overrides)
    return GameState(**defaults)


def make_drive_start() -> DriveStartModel:
    return DriveStartModel(
        touchback_rate=1.0, touchback_yardline=75,
        return_yardlines=np.array([75]),
    )


class TestApplyClock:
    def test_reduces_clock(self):
        state = make_state(clock=900)
        apply_clock(state, 38)
        assert state.clock == 862

    def test_clock_does_not_go_negative(self):
        state = make_state(clock=10)
        apply_clock(state, 38)
        assert state.clock == 0


class TestCheckQuarterEnd:
    def test_q1_to_q2(self):
        state = make_state(quarter=1, clock=0, possession="home")
        rng = np.random.default_rng(42)
        check_quarter_end(state, make_drive_start(), make_drive_start(), rng)
        assert state.quarter == 2
        assert state.clock == 900

    def test_q2_to_q3_halftime(self):
        """At halftime, the team that deferred receives."""
        state = make_state(quarter=2, clock=0, receiving_2nd_half="away")
        rng = np.random.default_rng(42)
        check_quarter_end(state, make_drive_start(), make_drive_start(), rng)
        assert state.quarter == 3
        assert state.clock == 900
        assert state.possession == "away"
        assert state.down == 1

    def test_q3_to_q4(self):
        state = make_state(quarter=3, clock=0)
        rng = np.random.default_rng(42)
        check_quarter_end(state, make_drive_start(), make_drive_start(), rng)
        assert state.quarter == 4
        assert state.clock == 900

    def test_q4_end_no_tie_game_over(self):
        state = make_state(quarter=4, clock=0, home_score=21, away_score=14)
        rng = np.random.default_rng(42)
        check_quarter_end(state, make_drive_start(), make_drive_start(), rng)
        assert state.game_over

    def test_q4_end_tie_goes_to_ot(self):
        state = make_state(quarter=4, clock=0, home_score=14, away_score=14)
        rng = np.random.default_rng(42)
        check_quarter_end(state, make_drive_start(), make_drive_start(), rng)
        assert state.quarter == 5
        assert not state.game_over

    def test_no_transition_when_clock_remaining(self):
        state = make_state(quarter=1, clock=100)
        rng = np.random.default_rng(42)
        check_quarter_end(state, make_drive_start(), make_drive_start(), rng)
        assert state.quarter == 1
        assert state.clock == 100
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_engine/test_clock.py -v`
Expected: FAIL

- [ ] **Step 3: Implement clock management**

```python
# src/fantasy_sim/engine/clock.py
import numpy as np
from fantasy_sim.engine.types import GameState
from fantasy_sim.engine.game_flow import perform_kickoff
from fantasy_sim.models.distributions import DriveStartModel

QUARTER_SECONDS = 900
OT_SECONDS = 600


def apply_clock(state: GameState, runoff: int) -> None:
    """Subtract clock runoff, clamping to zero."""
    state.clock = max(0, state.clock - runoff)


def check_quarter_end(
    state: GameState,
    home_drive_start: DriveStartModel,
    away_drive_start: DriveStartModel,
    rng: np.random.Generator,
) -> None:
    """Check if the quarter has ended and handle transitions."""
    if state.clock > 0:
        return

    if state.quarter == 1:
        # Q1 → Q2: teams switch ends, same possession continues
        state.quarter = 2
        state.clock = QUARTER_SECONDS

    elif state.quarter == 2:
        # Halftime → Q3: second-half receiving team gets kickoff
        state.quarter = 3
        state.clock = QUARTER_SECONDS
        state.possession = state.receiving_2nd_half
        recv_dists = home_drive_start if state.possession == "home" else away_drive_start
        perform_kickoff(state, recv_dists, rng)

    elif state.quarter == 3:
        # Q3 → Q4
        state.quarter = 4
        state.clock = QUARTER_SECONDS

    elif state.quarter == 4:
        # End of regulation
        if state.home_score != state.away_score:
            state.game_over = True
        else:
            # Overtime
            state.quarter = 5
            state.clock = OT_SECONDS
            # Coin toss for OT — random team receives
            ot_receiver = "home" if rng.random() < 0.5 else "away"
            state.possession = ot_receiver
            recv_dists = home_drive_start if ot_receiver == "home" else away_drive_start
            perform_kickoff(state, recv_dists, rng)

    elif state.quarter == 5:
        # OT period ended — in regular season, game ends as tie
        state.game_over = True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_engine/test_clock.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/engine/clock.py tests/test_engine/test_clock.py
git commit -m "feat: add clock management and quarter transitions"
```

---

### Task 6: Game Simulation Loop

**Files:**
- Create: `src/fantasy_sim/engine/game_sim.py`
- Create: `tests/test_engine/test_game_sim.py`

This is the main loop that ties all components together. It also handles overtime scoring rules.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_engine/test_game_sim.py
import numpy as np
import pytest
from fantasy_sim.engine.game_sim import simulate_game
from fantasy_sim.engine.types import GameResult, TeamDistributions
from fantasy_sim.models.distributions import (
    PlayCallingDist, PlayOutcomeDist, TurnoverRates, KickingModel, DriveStartModel,
)
from fantasy_sim.models.game_state import GameStateBucket


def make_team_dists(**overrides) -> TeamDistributions:
    defaults = dict(
        play_calling=PlayCallingDist(team="T", distributions={}, default={"pass": 0.55, "run": 0.45}),
        play_outcomes=PlayOutcomeDist(
            distributions={},
            defaults={
                "pass": np.array([0, 5, 7, 8, 10, 12, 0, 15, -2, 20, 0, 3, 6, 0, 9]),
                "run": np.array([3, 4, 5, -1, 2, 7, 1, 6, 0, 4, 3, 2, 5, -2, 8]),
            },
        ),
        turnover_rates=TurnoverRates(team="T", int_rate=0.025, fumble_rate=0.01, sack_rate=0.06, sack_fumble_rate=0.10),
        kicking=KickingModel(fg_make_rate={"0_39": 0.95, "40_49": 0.82, "50_plus": 0.65}, xp_rate=0.94),
        drive_start=DriveStartModel(touchback_rate=0.60, touchback_yardline=75, return_yardlines=np.array([72, 74, 78, 80])),
    )
    defaults.update(overrides)
    return TeamDistributions(**defaults)


class TestSimulateGame:
    def test_returns_game_result(self):
        rng = np.random.default_rng(42)
        result = simulate_game(make_team_dists(), make_team_dists(), rng)
        assert isinstance(result, GameResult)

    def test_scores_are_non_negative(self):
        rng = np.random.default_rng(42)
        result = simulate_game(make_team_dists(), make_team_dists(), rng)
        assert result.home_score >= 0
        assert result.away_score >= 0

    def test_box_scores_have_stats(self):
        rng = np.random.default_rng(42)
        result = simulate_game(make_team_dists(), make_team_dists(), rng)
        # At least some plays were run
        assert result.total_plays > 50
        assert result.home_box.pass_attempts + result.home_box.rush_attempts > 0
        assert result.away_box.pass_attempts + result.away_box.rush_attempts > 0

    def test_points_match_box_scores(self):
        rng = np.random.default_rng(42)
        result = simulate_game(make_team_dists(), make_team_dists(), rng)
        assert result.home_score == result.home_box.points
        assert result.away_score == result.away_box.points

    def test_different_seeds_different_results(self):
        r1 = simulate_game(make_team_dists(), make_team_dists(), np.random.default_rng(1))
        r2 = simulate_game(make_team_dists(), make_team_dists(), np.random.default_rng(2))
        # With different seeds, at least one stat should differ
        assert (r1.home_score != r2.home_score) or (r1.away_score != r2.away_score)

    def test_game_terminates(self):
        """Game should always finish (no infinite loops)."""
        rng = np.random.default_rng(42)
        result = simulate_game(make_team_dists(), make_team_dists(), rng)
        assert result.total_plays < 500  # Sanity check

    def test_realistic_play_count(self):
        """NFL games have ~120-160 total plays."""
        rng = np.random.default_rng(42)
        result = simulate_game(make_team_dists(), make_team_dists(), rng)
        assert 80 <= result.total_plays <= 250

    def test_realistic_score_range(self):
        """Most games score between 20-60 combined points."""
        rng = np.random.default_rng(42)
        result = simulate_game(make_team_dists(), make_team_dists(), rng)
        total = result.home_score + result.away_score
        assert 0 <= total <= 100
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_engine/test_game_sim.py -v`
Expected: FAIL

- [ ] **Step 3: Implement game simulation loop**

```python
# src/fantasy_sim/engine/game_sim.py
import numpy as np
from fantasy_sim.engine.types import GameState, GameResult, TeamBoxScore, TeamDistributions, PlayResult
from fantasy_sim.engine.play_caller import select_play_type, fourth_down_decision
from fantasy_sim.engine.play_resolver import resolve_play
from fantasy_sim.engine.game_flow import (
    apply_yards, change_possession, score_points,
    handle_turnover, perform_kickoff, perform_punt,
    attempt_field_goal, attempt_pat,
)
from fantasy_sim.engine.clock import apply_clock, check_quarter_end

# Safety valve to prevent infinite loops
MAX_PLAYS = 400


def simulate_game(
    home_dists: TeamDistributions,
    away_dists: TeamDistributions,
    rng: np.random.Generator,
) -> GameResult:
    """Simulate a complete NFL game play-by-play."""
    state = GameState(
        quarter=1, clock=900, possession="home",
        down=1, distance=10, yard_line=75,
        home_score=0, away_score=0,
        home_team=home_dists.play_calling.team,
        away_team=away_dists.play_calling.team,
        receiving_2nd_half="away",
    )
    home_box = TeamBoxScore()
    away_box = TeamBoxScore()

    # Coin toss
    if rng.random() < 0.5:
        state.possession = "home"
        state.receiving_2nd_half = "away"
    else:
        state.possession = "away"
        state.receiving_2nd_half = "home"

    # Opening kickoff
    recv_dists = home_dists if state.possession == "home" else away_dists
    perform_kickoff(state, recv_dists.drive_start, rng)

    total_plays = 0

    while not state.game_over and total_plays < MAX_PLAYS:
        off_dists = home_dists if state.possession == "home" else away_dists
        def_dists = away_dists if state.possession == "home" else home_dists
        off_box = home_box if state.possession == "home" else away_box
        def_box = away_box if state.possession == "home" else home_box

        # 4th down decision
        if state.down == 4:
            decision = fourth_down_decision(state, off_dists.kicking)
            if decision == "punt":
                perform_punt(state, rng, off_box)
                apply_clock(state, 5)
                check_quarter_end(state, home_dists.drive_start, away_dists.drive_start, rng)
                continue
            elif decision == "field_goal":
                recv_ds = home_dists.drive_start if state.possession == "home" else away_dists.drive_start
                attempt_field_goal(state, off_dists.kicking, recv_ds, rng, off_box)
                apply_clock(state, 5)
                check_quarter_end(state, home_dists.drive_start, away_dists.drive_start, rng)
                # Check OT walk-off FG
                if state.quarter == 5 and state.home_score != state.away_score:
                    state.game_over = True
                continue

        # Select and resolve play
        play_type = select_play_type(state, off_dists.play_calling, rng)
        result = resolve_play(
            state, play_type, off_dists.play_outcomes,
            off_dists.turnover_rates, rng,
        )
        total_plays += 1

        # Update box scores
        _update_box_scores(off_box, def_box, result)

        # Handle play outcome
        if result.is_safety:
            _handle_safety(state, off_box, def_box, def_dists.drive_start, rng)
        elif result.is_touchdown:
            _handle_touchdown(state, off_dists, off_box, def_dists.drive_start, rng)
            # OT walk-off TD
            if state.quarter == 5 and state.home_score != state.away_score:
                state.game_over = True
        elif result.is_interception or result.is_fumble:
            handle_turnover(state, result)
        else:
            apply_yards(state, result.yards)

        # Clock
        apply_clock(state, result.clock_runoff)
        check_quarter_end(state, home_dists.drive_start, away_dists.drive_start, rng)

    return GameResult(
        home_score=state.home_score,
        away_score=state.away_score,
        home_box=home_box,
        away_box=away_box,
        total_plays=total_plays,
        overtime=state.quarter >= 5,
    )


def _update_box_scores(off_box: TeamBoxScore, def_box: TeamBoxScore, result: PlayResult) -> None:
    """Update both offensive and defensive box scores from a play result."""
    if result.play_type == "pass":
        off_box.pass_attempts += 1
        if result.is_sack:
            off_box.sacks_taken += 1
            off_box.sack_yards += abs(result.yards)
            def_box.sacks_made += 1
        elif result.is_interception:
            off_box.interceptions_thrown += 1
            def_box.interceptions_caught += 1
        elif result.is_complete:
            off_box.completions += 1
            off_box.pass_yards += result.yards
            if result.is_touchdown:
                off_box.pass_tds += 1
        # Incomplete: nothing extra to track
    elif result.play_type == "run":
        off_box.rush_attempts += 1
        off_box.rush_yards += result.yards
        if result.is_touchdown:
            off_box.rush_tds += 1

    if result.is_fumble:
        off_box.fumbles_lost += 1
        def_box.fumbles_recovered += 1


def _handle_touchdown(
    state: GameState,
    off_dists: TeamDistributions,
    off_box: TeamBoxScore,
    recv_drive_start: DriveStartModel,
    rng: np.random.Generator,
) -> None:
    """Score a TD (6 points), attempt PAT, then kickoff."""
    score_points(state, 6)
    off_box.points += 6
    attempt_pat(state, off_dists.kicking, rng, off_box)
    change_possession(state)
    perform_kickoff(state, recv_drive_start, rng)


def _handle_safety(
    state: GameState,
    off_box: TeamBoxScore,
    def_box: TeamBoxScore,
    def_drive_start: DriveStartModel,
    rng: np.random.Generator,
) -> None:
    """Score a safety (2 points to defense), then free kick to defense."""
    # Defense scores 2 points
    defending = state.defense
    if defending == "home":
        state.home_score += 2
    else:
        state.away_score += 2
    def_box.points += 2
    def_box.safeties += 1

    # After safety: scoring team (defense) receives free kick
    change_possession(state)
    perform_kickoff(state, def_drive_start, rng)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_engine/test_game_sim.py -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests pass (Phase 1 + Phase 2)

- [ ] **Step 6: Commit**

```bash
git add src/fantasy_sim/engine/game_sim.py tests/test_engine/test_game_sim.py
git commit -m "feat: add full game simulation loop with OT support"
```

---

### Task 7: Monte Carlo Runner

**Files:**
- Create: `src/fantasy_sim/engine/monte_carlo.py`
- Create: `tests/test_engine/test_monte_carlo.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_engine/test_monte_carlo.py
import numpy as np
import pytest
from fantasy_sim.engine.monte_carlo import run_simulations, SimulationSummary
from fantasy_sim.engine.types import TeamDistributions, GameResult
from fantasy_sim.models.distributions import (
    PlayCallingDist, PlayOutcomeDist, TurnoverRates, KickingModel, DriveStartModel,
)


def make_team_dists() -> TeamDistributions:
    return TeamDistributions(
        play_calling=PlayCallingDist(team="T", distributions={}, default={"pass": 0.55, "run": 0.45}),
        play_outcomes=PlayOutcomeDist(
            distributions={},
            defaults={
                "pass": np.array([0, 5, 7, 8, 10, 12, 0, 15, -2, 20, 0, 3, 6, 0, 9]),
                "run": np.array([3, 4, 5, -1, 2, 7, 1, 6, 0, 4, 3, 2, 5, -2, 8]),
            },
        ),
        turnover_rates=TurnoverRates(team="T", int_rate=0.025, fumble_rate=0.01, sack_rate=0.06, sack_fumble_rate=0.10),
        kicking=KickingModel(fg_make_rate={"0_39": 0.95, "40_49": 0.82, "50_plus": 0.65}, xp_rate=0.94),
        drive_start=DriveStartModel(touchback_rate=0.60, touchback_yardline=75, return_yardlines=np.array([72, 74, 78, 80])),
    )


class TestRunSimulations:
    def test_returns_correct_number_of_results(self):
        results = run_simulations(make_team_dists(), make_team_dists(), n_sims=10, seed=42)
        assert len(results.games) == 10

    def test_all_results_are_game_results(self):
        results = run_simulations(make_team_dists(), make_team_dists(), n_sims=5, seed=42)
        for game in results.games:
            assert isinstance(game, GameResult)

    def test_summary_stats_computed(self):
        results = run_simulations(make_team_dists(), make_team_dists(), n_sims=20, seed=42)
        summary = results.summary()
        assert "home_score_mean" in summary
        assert "away_score_mean" in summary
        assert "home_win_pct" in summary
        assert "total_score_mean" in summary
        assert "overtime_pct" in summary

    def test_deterministic_with_same_seed(self):
        r1 = run_simulations(make_team_dists(), make_team_dists(), n_sims=5, seed=42)
        r2 = run_simulations(make_team_dists(), make_team_dists(), n_sims=5, seed=42)
        for g1, g2 in zip(r1.games, r2.games):
            assert g1.home_score == g2.home_score
            assert g1.away_score == g2.away_score

    def test_different_seeds_produce_variation(self):
        r1 = run_simulations(make_team_dists(), make_team_dists(), n_sims=10, seed=1)
        r2 = run_simulations(make_team_dists(), make_team_dists(), n_sims=10, seed=2)
        scores1 = [g.home_score for g in r1.games]
        scores2 = [g.home_score for g in r2.games]
        assert scores1 != scores2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_engine/test_monte_carlo.py -v`
Expected: FAIL

- [ ] **Step 3: Implement Monte Carlo runner**

```python
# src/fantasy_sim/engine/monte_carlo.py
from dataclasses import dataclass, field
import numpy as np
from fantasy_sim.engine.types import TeamDistributions, GameResult
from fantasy_sim.engine.game_sim import simulate_game


@dataclass
class SimulationSummary:
    """Aggregate statistics across N simulations."""
    games: list[GameResult]

    def summary(self) -> dict:
        n = len(self.games)
        home_scores = [g.home_score for g in self.games]
        away_scores = [g.away_score for g in self.games]
        total_scores = [h + a for h, a in zip(home_scores, away_scores)]
        home_wins = sum(1 for g in self.games if g.home_score > g.away_score)
        ties = sum(1 for g in self.games if g.home_score == g.away_score)
        ot_games = sum(1 for g in self.games if g.overtime)
        total_plays = [g.total_plays for g in self.games]

        return {
            "n_sims": n,
            "home_score_mean": np.mean(home_scores),
            "home_score_std": np.std(home_scores),
            "away_score_mean": np.mean(away_scores),
            "away_score_std": np.std(away_scores),
            "total_score_mean": np.mean(total_scores),
            "total_score_std": np.std(total_scores),
            "home_win_pct": home_wins / n,
            "tie_pct": ties / n,
            "overtime_pct": ot_games / n,
            "plays_mean": np.mean(total_plays),
            "plays_std": np.std(total_plays),
        }


def run_simulations(
    home_dists: TeamDistributions,
    away_dists: TeamDistributions,
    n_sims: int = 1000,
    seed: int = 42,
) -> SimulationSummary:
    """Run N game simulations and return all results."""
    rng = np.random.default_rng(seed)
    games = []
    for _ in range(n_sims):
        result = simulate_game(home_dists, away_dists, rng)
        games.append(result)
    return SimulationSummary(games=games)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_engine/test_monte_carlo.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/engine/monte_carlo.py tests/test_engine/test_monte_carlo.py
git commit -m "feat: add Monte Carlo simulation runner"
```

---

### Task 8: Statistical Validation

**Files:**
- Create: `tests/test_engine/test_statistical_validation.py`
- Create: `scripts/validate_sim.py`

This runs bulk simulations and verifies the outputs match known NFL averages.

- [ ] **Step 1: Write the statistical validation tests**

```python
# tests/test_engine/test_statistical_validation.py
import numpy as np
import pytest
from fantasy_sim.engine.monte_carlo import run_simulations
from fantasy_sim.engine.types import TeamDistributions
from fantasy_sim.models.distributions import (
    PlayCallingDist, PlayOutcomeDist, TurnoverRates, KickingModel, DriveStartModel,
)


def make_league_avg_dists() -> TeamDistributions:
    """Team distributions using league-average values."""
    return TeamDistributions(
        play_calling=PlayCallingDist(team="AVG", distributions={}, default={"pass": 0.57, "run": 0.43}),
        play_outcomes=PlayOutcomeDist(
            distributions={},
            defaults={
                # Realistic NFL pass yards distribution (includes incompletions as 0)
                "pass": np.array([
                    0, 0, 0, 0, 0, 0,        # ~40% incompletion
                    3, 4, 5, 6, 7, 8, 9, 10,  # Short completions
                    12, 15, 18, 20, 25,        # Medium
                    30, 40, 50,                # Deep
                ]),
                # Realistic NFL rush yards distribution
                "run": np.array([
                    -3, -2, -1, 0, 1, 1, 2, 2, 3, 3, 3, 4, 4, 4, 5, 5,
                    6, 7, 8, 10, 12, 15, 20,
                ]),
            },
        ),
        turnover_rates=TurnoverRates(team="AVG", int_rate=0.025, fumble_rate=0.012, sack_rate=0.065, sack_fumble_rate=0.10),
        kicking=KickingModel(fg_make_rate={"0_39": 0.93, "40_49": 0.82, "50_plus": 0.65}, xp_rate=0.94),
        drive_start=DriveStartModel(touchback_rate=0.55, touchback_yardline=75, return_yardlines=np.array([72, 74, 76, 78, 80, 82])),
    )


@pytest.mark.statistical
class TestStatisticalValidation:
    """Run 2000 simulated games and verify NFL-realistic averages.

    These tests use wide tolerances since we're comparing against league averages
    with simplified distributions. The goal is plausibility, not precision.
    """

    @pytest.fixture(scope="class")
    def sim_results(self):
        dists = make_league_avg_dists()
        return run_simulations(dists, dists, n_sims=2000, seed=42)

    def test_average_total_points(self, sim_results):
        """NFL average is ~45-48 points per game."""
        s = sim_results.summary()
        assert 30 <= s["total_score_mean"] <= 65, f"Total score {s['total_score_mean']:.1f} out of range"

    def test_home_win_rate(self, sim_results):
        """With identical teams, should be ~50% (no home advantage modeled yet)."""
        s = sim_results.summary()
        assert 0.40 <= s["home_win_pct"] <= 0.60, f"Home win rate {s['home_win_pct']:.1%} out of range"

    def test_overtime_rate(self, sim_results):
        """NFL OT rate is ~5%. With identical teams, could be slightly higher."""
        s = sim_results.summary()
        assert 0.01 <= s["overtime_pct"] <= 0.15, f"OT rate {s['overtime_pct']:.1%} out of range"

    def test_average_plays_per_game(self, sim_results):
        """NFL average is ~120-140 total plays per game."""
        s = sim_results.summary()
        assert 80 <= s["plays_mean"] <= 200, f"Plays per game {s['plays_mean']:.0f} out of range"

    def test_scores_have_variance(self, sim_results):
        """Games shouldn't all produce the same score."""
        s = sim_results.summary()
        assert s["total_score_std"] > 5, f"Score std {s['total_score_std']:.1f} too low"

    def test_no_absurd_scores(self, sim_results):
        """No game should have a team scoring >80 points."""
        for game in sim_results.games:
            assert game.home_score <= 80, f"Absurd home score: {game.home_score}"
            assert game.away_score <= 80, f"Absurd away score: {game.away_score}"

    def test_box_scores_consistent(self, sim_results):
        """Points in box score should match game score."""
        for game in sim_results.games:
            assert game.home_score == game.home_box.points
            assert game.away_score == game.away_box.points

    def test_turnovers_reasonable(self, sim_results):
        """Average turnovers per team should be 1-3 per game."""
        total_games = len(sim_results.games)
        total_ints = sum(g.home_box.interceptions_thrown + g.away_box.interceptions_thrown for g in sim_results.games)
        total_fumbles = sum(g.home_box.fumbles_lost + g.away_box.fumbles_lost for g in sim_results.games)
        avg_turnovers = (total_ints + total_fumbles) / total_games
        assert 1.0 <= avg_turnovers <= 8.0, f"Avg turnovers {avg_turnovers:.1f} out of range"
```

- [ ] **Step 2: Run statistical validation tests**

Run: `uv run pytest tests/test_engine/test_statistical_validation.py -v -m statistical`
Expected: All PASS (may take 30-60 seconds for 2000 sims)

- [ ] **Step 3: Write the validation script**

```python
# scripts/validate_sim.py
"""Validate that the simulation engine produces realistic NFL game statistics.

Run: uv run python scripts/validate_sim.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import numpy as np
from fantasy_sim.engine.monte_carlo import run_simulations
from fantasy_sim.engine.types import TeamDistributions
from fantasy_sim.models.distributions import (
    PlayCallingDist, PlayOutcomeDist, TurnoverRates, KickingModel, DriveStartModel,
)


def make_league_avg_dists() -> TeamDistributions:
    return TeamDistributions(
        play_calling=PlayCallingDist(team="AVG", distributions={}, default={"pass": 0.57, "run": 0.43}),
        play_outcomes=PlayOutcomeDist(
            distributions={},
            defaults={
                "pass": np.array([0, 0, 0, 0, 0, 0, 3, 4, 5, 6, 7, 8, 9, 10, 12, 15, 18, 20, 25, 30, 40, 50]),
                "run": np.array([-3, -2, -1, 0, 1, 1, 2, 2, 3, 3, 3, 4, 4, 4, 5, 5, 6, 7, 8, 10, 12, 15, 20]),
            },
        ),
        turnover_rates=TurnoverRates(team="AVG", int_rate=0.025, fumble_rate=0.012, sack_rate=0.065, sack_fumble_rate=0.10),
        kicking=KickingModel(fg_make_rate={"0_39": 0.93, "40_49": 0.82, "50_plus": 0.65}, xp_rate=0.94),
        drive_start=DriveStartModel(touchback_rate=0.55, touchback_yardline=75, return_yardlines=np.array([72, 74, 76, 78, 80, 82])),
    )


def main():
    n_sims = 5000
    print(f"Running {n_sims} simulated games...")
    dists = make_league_avg_dists()
    results = run_simulations(dists, dists, n_sims=n_sims, seed=42)
    s = results.summary()

    print(f"\n--- Simulation Results ({n_sims} games) ---")
    print(f"  Avg total points:    {s['total_score_mean']:.1f} (±{s['total_score_std']:.1f})")
    print(f"  Avg home score:      {s['home_score_mean']:.1f}")
    print(f"  Avg away score:      {s['away_score_mean']:.1f}")
    print(f"  Home win %:          {s['home_win_pct']:.1%}")
    print(f"  Tie %:               {s['tie_pct']:.1%}")
    print(f"  Overtime %:          {s['overtime_pct']:.1%}")
    print(f"  Avg plays/game:      {s['plays_mean']:.0f} (±{s['plays_std']:.0f})")

    # Compute additional stats
    total_games = len(results.games)
    avg_pass_att = np.mean([g.home_box.pass_attempts + g.away_box.pass_attempts for g in results.games])
    avg_rush_att = np.mean([g.home_box.rush_attempts + g.away_box.rush_attempts for g in results.games])
    avg_pass_yds = np.mean([g.home_box.pass_yards + g.away_box.pass_yards for g in results.games])
    avg_rush_yds = np.mean([g.home_box.rush_yards + g.away_box.rush_yards for g in results.games])
    avg_turnovers = np.mean([
        g.home_box.interceptions_thrown + g.away_box.interceptions_thrown +
        g.home_box.fumbles_lost + g.away_box.fumbles_lost
        for g in results.games
    ])

    print(f"\n--- Detailed Stats ---")
    print(f"  Avg pass attempts:   {avg_pass_att:.0f}")
    print(f"  Avg rush attempts:   {avg_rush_att:.0f}")
    print(f"  Avg pass yards:      {avg_pass_yds:.0f}")
    print(f"  Avg rush yards:      {avg_rush_yds:.0f}")
    print(f"  Avg turnovers/game:  {avg_turnovers:.1f}")

    print(f"\n--- Sanity Checks ---")
    checks_passed = 0
    checks_total = 5

    if 30 <= s["total_score_mean"] <= 65:
        print(f"  PASS: Total points in range")
        checks_passed += 1
    else:
        print(f"  FAIL: Total points {s['total_score_mean']:.1f} out of range [30-65]")

    if 0.40 <= s["home_win_pct"] <= 0.60:
        print(f"  PASS: Home win rate in range")
        checks_passed += 1
    else:
        print(f"  FAIL: Home win rate {s['home_win_pct']:.1%} out of range [40-60%]")

    if 0.01 <= s["overtime_pct"] <= 0.15:
        print(f"  PASS: OT rate in range")
        checks_passed += 1
    else:
        print(f"  FAIL: OT rate {s['overtime_pct']:.1%} out of range [1-15%]")

    if 80 <= s["plays_mean"] <= 200:
        print(f"  PASS: Plays per game in range")
        checks_passed += 1
    else:
        print(f"  FAIL: Plays/game {s['plays_mean']:.0f} out of range [80-200]")

    if 1.0 <= avg_turnovers <= 8.0:
        print(f"  PASS: Turnovers in range")
        checks_passed += 1
    else:
        print(f"  FAIL: Turnovers {avg_turnovers:.1f} out of range [1-8]")

    print(f"\n=== {checks_passed}/{checks_total} SANITY CHECKS PASSED ===")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the validation script**

Run: `uv run python scripts/validate_sim.py`
Expected: All 5 sanity checks pass. Output shows NFL-realistic averages.

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests pass (Phase 1 + Phase 2)

- [ ] **Step 6: Commit**

```bash
git add tests/test_engine/test_statistical_validation.py scripts/validate_sim.py
git commit -m "feat: add statistical validation for simulation engine"
```

---

## Phase 2 Completion Criteria

All of these must be true before Phase 2 is done:

1. All unit tests pass (play caller, resolver, game flow, clock, game sim, monte carlo)
2. Statistical validation passes (2000+ games produce NFL-realistic averages)
3. `simulate_game()` produces complete `GameResult` with team box scores
4. `run_simulations()` produces N results with aggregate statistics
5. Overtime works correctly
6. No infinite loops (MAX_PLAYS safety valve)
7. Box score points always match game score

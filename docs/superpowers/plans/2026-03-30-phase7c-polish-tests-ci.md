# Phase 7C: Polish + Tests + CI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close remaining gaps: fix games_missed to zero specific weeks, implement pace override, fix DST projection issues, expand test coverage for edge cases and missing features, add fuzzy matching disambiguation, and set up GitHub Actions CI.

**Architecture:** This phase touches six subsystems. (1) DST defensive TDs are modeled probabilistically in the game sim turnover path and surfaced through `TeamBoxScore` into DST projections. (2) The `weeks_missed` field on `PlayerModel` stores specific week numbers; the player selector skips unavailable players during those weeks. (3) A `pace_factor` on `TeamDistributions` scales clock runoff in the play resolver to control plays-per-game. (4) Fuzzy matching in `PlayerResolver` detects ambiguous matches (top 2+ within 5 points) and raises a descriptive error. (5) Comprehensive edge-case tests validate overrides, empty rosters, invalid inputs, and validation targets. (6) GitHub Actions CI runs pytest on push/PR across a Python version matrix with dependency caching.

**Tech Stack:** Python 3.14, pytest, GitHub Actions, numpy

---

## File Structure

```
.github/
└── workflows/
    └── ci.yml                              NEW: GitHub Actions CI pipeline

src/fantasy_sim/
├── engine/
│   ├── types.py                            MODIFY: Add defensive_tds to TeamBoxScore, pace_factor to TeamDistributions
│   ├── game_sim.py                         MODIFY: Probabilistic defensive TDs on turnovers, week awareness
│   ├── play_resolver.py                    MODIFY: Scale clock_runoff by pace_factor
│   └── player_selector.py                  MODIFY: Skip players with current week in weeks_missed
├── models/
│   └── player.py                           MODIFY: Add weeks_missed field to PlayerModel
├── overrides/
│   ├── engine.py                           MODIFY: Wire games_missed to weeks_missed, wire pace_plays_per_game
│   └── resolver.py                         MODIFY: Ambiguous match detection
└── scoring/
    ├── engine.py                           MODIFY: Use defensive_tds in score_dst
    └── projections.py                      MODIFY: Surface defensive_tds in DST projections

tests/
├── test_engine/
│   └── test_dst_defensive_tds.py           NEW: DST defensive TD modeling tests
├── test_overrides/
│   ├── test_weeks_missed.py                NEW: Per-week zero-out tests
│   ├── test_pace_override.py               NEW: Pace factor tests
│   └── test_fuzzy_disambiguation.py        NEW: Ambiguous match tests
├── test_validation/
│   └── test_backtester_verification.py     NEW: Verify targets, calibration, leakage
└── test_edge_cases.py                      NEW: Comprehensive edge case suite
```

## Dependencies from Phases 1-6

- `engine.types.TeamBoxScore` -- defensive stats: `sacks_made`, `interceptions_caught`, `fumbles_recovered`, `safeties`
- `engine.types.TeamDistributions` -- bundles all team distributions
- `engine.types.PlayResult` -- `is_interception`, `is_fumble`, `clock_runoff`
- `engine.game_sim._update_box_scores()` -- updates off_box and def_box from PlayResult
- `engine.game_sim.simulate_game()` -- main simulation loop; uses `GameState`, orchestrates plays
- `engine.play_resolver.resolve_play()` -- returns PlayResult with clock_runoff
- `engine.play_resolver.CLOCK_RUN`, `CLOCK_PASS_COMPLETE`, `CLOCK_PASS_INCOMPLETE`, `CLOCK_SACK` -- clock constants
- `engine.player_selector.select_receiver()`, `select_rusher()` -- delegates to TeamRoster methods
- `models.player.PlayerModel` -- `player_id`, `name`, `position`, `team`, `usage`, `outcomes`, `games_played`
- `models.player.TeamRoster` -- `select_receiver()`, `select_rusher()` with red zone awareness
- `overrides.engine.apply_player_override()` -- dispatches by field name, mutates roster in place
- `overrides.engine.PLAYER_META_FIELDS` -- set of valid meta override fields
- `overrides.resolver.PlayerResolver.resolve()` -- fuzzy match with `thefuzz`, returns player_id or raises KeyError
- `scoring.engine.score_dst()` -- calculates DST fantasy points from TeamBoxScore + opponent score
- `scoring.projections.build_dst_projections()` -- aggregates DST stats across games
- `validation.backtester.BacktestResult` -- has WEEKLY_MAE_TARGET, SEASON_MAE_TARGET, RANK_CORR_TARGET, CALIBRATION_TARGET
- `validation.backtester.Backtester` -- `training_seasons` excludes `test_season`
- `validation.metrics.boom_bust_calibration()` -- mean absolute calibration error

---

### Task 1: DST Defensive TD Modeling (Gaps 22, 23)

**Files:**
- Modify: `src/fantasy_sim/engine/types.py`
- Modify: `src/fantasy_sim/engine/game_sim.py`
- Modify: `src/fantasy_sim/scoring/engine.py`
- Modify: `src/fantasy_sim/scoring/projections.py`
- Create: `tests/test_engine/test_dst_defensive_tds.py`

- [ ] **Step 1: Write failing tests for defensive TD tracking**

```python
# tests/test_engine/test_dst_defensive_tds.py
import numpy as np
import pytest
from fantasy_sim.engine.types import TeamBoxScore, PlayResult
from fantasy_sim.engine.game_sim import _update_box_scores


class TestDefensiveTdTracking:
    """Verify that TeamBoxScore tracks defensive TDs."""

    def test_team_box_score_has_defensive_tds_field(self):
        box = TeamBoxScore()
        assert hasattr(box, "defensive_tds")
        assert box.defensive_tds == 0

    def test_interception_can_produce_defensive_td(self):
        """With a forced seed, an INT should sometimes produce a defensive TD."""
        off_box = TeamBoxScore()
        def_box = TeamBoxScore()
        # Simulate an interception play
        result = PlayResult(
            play_type="pass", yards=0, is_interception=True,
            clock_runoff=7,
        )
        # We need to call the updated _update_box_scores which now
        # accepts an rng parameter for defensive TD probability
        rng = np.random.default_rng(42)
        _update_box_scores(off_box, def_box, result, rng=rng)
        assert def_box.interceptions_caught == 1
        # defensive_tds may be 0 or 1 depending on RNG; just verify it's an int >= 0
        assert isinstance(def_box.defensive_tds, int)
        assert def_box.defensive_tds >= 0

    def test_fumble_recovery_can_produce_defensive_td(self):
        """With a forced seed, a fumble recovery should sometimes produce a defensive TD."""
        off_box = TeamBoxScore()
        def_box = TeamBoxScore()
        result = PlayResult(
            play_type="run", yards=3, is_fumble=True,
            clock_runoff=38,
        )
        rng = np.random.default_rng(12345)
        _update_box_scores(off_box, def_box, result, rng=rng)
        assert def_box.fumbles_recovered == 1
        assert isinstance(def_box.defensive_tds, int)
        assert def_box.defensive_tds >= 0

    def test_defensive_td_statistical_rate_on_interceptions(self):
        """Over many interceptions, ~20% should produce defensive TDs."""
        rng = np.random.default_rng(99)
        n_trials = 5000
        total_dst_tds = 0
        for _ in range(n_trials):
            off_box = TeamBoxScore()
            def_box = TeamBoxScore()
            result = PlayResult(
                play_type="pass", yards=0, is_interception=True,
                clock_runoff=7,
            )
            _update_box_scores(off_box, def_box, result, rng=rng)
            total_dst_tds += def_box.defensive_tds
        rate = total_dst_tds / n_trials
        # Expected ~0.20, allow range 0.15 to 0.25
        assert 0.15 <= rate <= 0.25, f"INT defensive TD rate {rate:.3f} outside expected range"

    def test_defensive_td_statistical_rate_on_fumbles(self):
        """Over many fumble recoveries, ~10% should produce defensive TDs."""
        rng = np.random.default_rng(77)
        n_trials = 5000
        total_dst_tds = 0
        for _ in range(n_trials):
            off_box = TeamBoxScore()
            def_box = TeamBoxScore()
            result = PlayResult(
                play_type="run", yards=3, is_fumble=True,
                clock_runoff=38,
            )
            _update_box_scores(off_box, def_box, result, rng=rng)
            total_dst_tds += def_box.defensive_tds
        rate = total_dst_tds / n_trials
        # Expected ~0.10, allow range 0.06 to 0.14
        assert 0.06 <= rate <= 0.14, f"Fumble defensive TD rate {rate:.3f} outside expected range"

    def test_no_defensive_td_on_normal_play(self):
        """Normal completions and runs should never produce defensive TDs."""
        rng = np.random.default_rng(42)
        off_box = TeamBoxScore()
        def_box = TeamBoxScore()
        result = PlayResult(
            play_type="pass", yards=12, is_complete=True,
            clock_runoff=35,
        )
        _update_box_scores(off_box, def_box, result, rng=rng)
        assert def_box.defensive_tds == 0

    def test_update_box_scores_backward_compatible_without_rng(self):
        """Calling _update_box_scores without rng should still work (no crash)."""
        off_box = TeamBoxScore()
        def_box = TeamBoxScore()
        result = PlayResult(
            play_type="pass", yards=0, is_interception=True,
            clock_runoff=7,
        )
        # No rng passed -- should not crash, just skip defensive TD roll
        _update_box_scores(off_box, def_box, result)
        assert def_box.interceptions_caught == 1
        assert def_box.defensive_tds == 0
```

Run: `cd /Users/chrisesposito/Documents/github/fantasy-projections-simulator && python -m pytest tests/test_engine/test_dst_defensive_tds.py -x` -- expect failures.

- [ ] **Step 2: Add `defensive_tds` field to `TeamBoxScore`**

```python
# src/fantasy_sim/engine/types.py
# In the TeamBoxScore dataclass, add after the "safeties" field (line 124):

    defensive_tds: int = 0
```

The full change: find the line `safeties: int = 0` in `TeamBoxScore` and add `defensive_tds: int = 0` immediately after it.

- [ ] **Step 3: Update `_update_box_scores` to probabilistically award defensive TDs**

```python
# src/fantasy_sim/engine/game_sim.py
# Replace the _update_box_scores function entirely:

# Defensive TD return probabilities (per-turnover)
INT_RETURN_TD_RATE = 0.20    # ~20% of INTs returned for TD
FUMBLE_RETURN_TD_RATE = 0.10  # ~10% of fumble recoveries returned for TD


def _update_box_scores(
    off_box: TeamBoxScore, def_box: TeamBoxScore, result: PlayResult,
    rng: np.random.Generator | None = None,
) -> None:
    """Update both offensive and defensive box scores from a play result.

    When rng is provided, turnovers may probabilistically produce a
    defensive touchdown (pick-six or fumble return TD).
    """
    if result.play_type == "pass":
        off_box.pass_attempts += 1
        if result.is_sack:
            off_box.sacks_taken += 1
            off_box.sack_yards += abs(result.yards)
            def_box.sacks_made += 1
        elif result.is_interception:
            off_box.interceptions_thrown += 1
            def_box.interceptions_caught += 1
            if rng is not None and rng.random() < INT_RETURN_TD_RATE:
                def_box.defensive_tds += 1
        elif result.is_complete:
            off_box.completions += 1
            off_box.pass_yards += result.yards
            if result.is_touchdown:
                off_box.pass_tds += 1
    elif result.play_type == "run":
        off_box.rush_attempts += 1
        off_box.rush_yards += result.yards
        if result.is_touchdown:
            off_box.rush_tds += 1

    if result.is_fumble:
        off_box.fumbles_lost += 1
        def_box.fumbles_recovered += 1
        if rng is not None and rng.random() < FUMBLE_RETURN_TD_RATE:
            def_box.defensive_tds += 1
```

- [ ] **Step 4: Pass `rng` into `_update_box_scores` from `simulate_game`**

In `src/fantasy_sim/engine/game_sim.py`, find the line:

```python
        _update_box_scores(off_box, def_box, result)
```

Replace with:

```python
        _update_box_scores(off_box, def_box, result, rng=rng)
```

Also add the two constants at the top of the file (after `MAX_PLAYS = 400`):

```python
# Defensive TD return probabilities (per-turnover)
INT_RETURN_TD_RATE = 0.20    # ~20% of INTs returned for TD
FUMBLE_RETURN_TD_RATE = 0.10  # ~10% of fumble recoveries returned for TD
```

(These constants are used by `_update_box_scores` which is defined in the same file.)

- [ ] **Step 5: Update `score_dst` to use `defensive_tds`**

```python
# src/fantasy_sim/scoring/engine.py
# In the score_dst function, find the comment line:
#     # dst_td not yet tracked in TeamBoxScore (no defensive TD attribution in engine)
# Replace it with:
    points += box.defensive_tds * config.get("dst_td", 0)
```

The full replacement: remove the comment line `# dst_td not yet tracked in TeamBoxScore (no defensive TD attribution in engine)` and replace with `points += box.defensive_tds * config.get("dst_td", 0)`.

- [ ] **Step 6: Update `build_dst_projections` to surface `defensive_tds`**

```python
# src/fantasy_sim/scoring/projections.py
# In build_dst_projections, replace both instances of:
#     "dst_tds": 0.0,  # Not tracked yet
# With (for home DST):
        "dst_tds": round(float(np.mean([b.defensive_tds for b in home_boxes])), 1),
# And for away DST:
        "dst_tds": round(float(np.mean([b.defensive_tds for b in away_boxes])), 1),
```

Specifically, find the first `"dst_tds": 0.0,  # Not tracked yet` (around line 88) and replace with:

```python
        "dst_tds": round(float(np.mean([b.defensive_tds for b in home_boxes])), 1),
```

Find the second `"dst_tds": 0.0,` (around line 102, in the away DST block) and replace with:

```python
        "dst_tds": round(float(np.mean([b.defensive_tds for b in away_boxes])), 1),
```

- [ ] **Step 7: Run tests and verify**

Run: `cd /Users/chrisesposito/Documents/github/fantasy-projections-simulator && python -m pytest tests/test_engine/test_dst_defensive_tds.py -v`

All 7 tests should pass. Then run the full suite to check for regressions:

Run: `cd /Users/chrisesposito/Documents/github/fantasy-projections-simulator && python -m pytest tests/ -x --ignore=tests/test_integration`

- [ ] **Step 8: Commit**

```
git add tests/test_engine/test_dst_defensive_tds.py src/fantasy_sim/engine/types.py src/fantasy_sim/engine/game_sim.py src/fantasy_sim/scoring/engine.py src/fantasy_sim/scoring/projections.py
git commit -m "Add probabilistic defensive TDs to DST projections

Model pick-sixes (~20% of INTs) and fumble return TDs (~10% of
recoveries) in _update_box_scores. Surface defensive_tds through
TeamBoxScore into score_dst and build_dst_projections."
```

---

### Task 2: games_missed Per-Week Zero-Out (Gap 27)

**Files:**
- Modify: `src/fantasy_sim/models/player.py`
- Modify: `src/fantasy_sim/overrides/engine.py`
- Modify: `src/fantasy_sim/engine/player_selector.py`
- Modify: `src/fantasy_sim/engine/game_sim.py`
- Modify: `src/fantasy_sim/engine/types.py`
- Create: `tests/test_overrides/test_weeks_missed.py`

- [ ] **Step 1: Write failing tests for per-week zero-out**

```python
# tests/test_overrides/test_weeks_missed.py
import numpy as np
import pytest
from fantasy_sim.models.player import (
    PlayerModel, PlayerUsage, PlayerOutcomes, TeamRoster,
)
from fantasy_sim.overrides.engine import apply_player_override
from fantasy_sim.engine.player_selector import select_receiver, select_rusher
from fantasy_sim.engine.types import GameState


def make_roster() -> TeamRoster:
    return TeamRoster(team="KC", players=[
        PlayerModel("QB1", "Mahomes", "QB", "KC",
                    PlayerUsage(snap_share=1.0), PlayerOutcomes()),
        PlayerModel("WR1", "Worthy", "WR", "KC",
                    PlayerUsage(target_share=0.30),
                    PlayerOutcomes(catch_rate=0.63,
                                   receiving_yards_dist=np.array([8, 12]))),
        PlayerModel("WR2", "Rice", "WR", "KC",
                    PlayerUsage(target_share=0.25),
                    PlayerOutcomes(catch_rate=0.60,
                                   receiving_yards_dist=np.array([7, 10]))),
        PlayerModel("RB1", "Pacheco", "RB", "KC",
                    PlayerUsage(carry_share=0.65, target_share=0.10),
                    PlayerOutcomes(rushing_yards_dist=np.array([3, 5, 7]),
                                   catch_rate=0.72,
                                   receiving_yards_dist=np.array([4, 6]))),
        PlayerModel("RB2", "Clyde", "RB", "KC",
                    PlayerUsage(carry_share=0.25, target_share=0.05),
                    PlayerOutcomes(rushing_yards_dist=np.array([2, 4]),
                                   catch_rate=0.65,
                                   receiving_yards_dist=np.array([3, 5]))),
    ])


def make_state(week: int = 1) -> GameState:
    return GameState(
        quarter=1, clock=900, possession="home",
        down=1, distance=10, yard_line=75,
        home_score=0, away_score=0,
        home_team="KC", away_team="BUF",
        receiving_2nd_half="away",
        week=week,
    )


class TestWeeksMissedField:
    def test_player_model_has_weeks_missed(self):
        p = PlayerModel("X1", "Test", "WR", "KC",
                        PlayerUsage(), PlayerOutcomes())
        assert hasattr(p, "weeks_missed")
        assert p.weeks_missed == []

    def test_games_missed_override_sets_weeks_missed(self):
        roster = make_roster()
        apply_player_override(roster, "WR1", {"games_missed": [4, 5, 6]})
        wr1 = next(p for p in roster.players if p.player_id == "WR1")
        assert wr1.weeks_missed == [4, 5, 6]
        assert wr1.games_played == 14  # 17 - 3

    def test_games_missed_empty_list(self):
        roster = make_roster()
        apply_player_override(roster, "WR1", {"games_missed": []})
        wr1 = next(p for p in roster.players if p.player_id == "WR1")
        assert wr1.weeks_missed == []
        assert wr1.games_played == 17


class TestGameStateHasWeek:
    def test_game_state_has_week_field(self):
        state = make_state(week=5)
        assert state.week == 5

    def test_game_state_week_defaults_to_zero(self):
        state = GameState(
            quarter=1, clock=900, possession="home",
            down=1, distance=10, yard_line=75,
            home_score=0, away_score=0,
            home_team="KC", away_team="BUF",
            receiving_2nd_half="away",
        )
        assert state.week == 0


class TestPlayerSelectorSkipsMissedWeeks:
    def test_receiver_skipped_during_missed_week(self):
        """WR1 misses week 5 -- should never be selected as receiver in week 5."""
        roster = make_roster()
        apply_player_override(roster, "WR1", {"games_missed": [5]})
        state = make_state(week=5)
        rng = np.random.default_rng(42)
        selected_ids = set()
        for _ in range(100):
            player = select_receiver(roster, state, rng)
            selected_ids.add(player.player_id)
        assert "WR1" not in selected_ids, "WR1 should not be selected during missed week"

    def test_receiver_available_during_non_missed_week(self):
        """WR1 misses week 5 but should be selectable in week 3."""
        roster = make_roster()
        apply_player_override(roster, "WR1", {"games_missed": [5]})
        state = make_state(week=3)
        rng = np.random.default_rng(42)
        selected_ids = set()
        for _ in range(100):
            player = select_receiver(roster, state, rng)
            selected_ids.add(player.player_id)
        assert "WR1" in selected_ids, "WR1 should be selectable during non-missed week"

    def test_rusher_skipped_during_missed_week(self):
        """RB1 misses week 10 -- should never be selected as rusher in week 10."""
        roster = make_roster()
        apply_player_override(roster, "RB1", {"games_missed": [10]})
        state = make_state(week=10)
        rng = np.random.default_rng(42)
        selected_ids = set()
        for _ in range(100):
            player = select_rusher(roster, state, rng)
            selected_ids.add(player.player_id)
        assert "RB1" not in selected_ids, "RB1 should not be selected during missed week"

    def test_week_zero_means_no_filtering(self):
        """When week=0 (unset), no filtering should occur even if weeks_missed is set."""
        roster = make_roster()
        apply_player_override(roster, "WR1", {"games_missed": [5]})
        state = make_state(week=0)
        rng = np.random.default_rng(42)
        selected_ids = set()
        for _ in range(100):
            player = select_receiver(roster, state, rng)
            selected_ids.add(player.player_id)
        assert "WR1" in selected_ids, "WR1 should be selectable when week=0 (unset)"
```

Run: `cd /Users/chrisesposito/Documents/github/fantasy-projections-simulator && python -m pytest tests/test_overrides/test_weeks_missed.py -x` -- expect failures.

- [ ] **Step 2: Add `weeks_missed` field to `PlayerModel`**

```python
# src/fantasy_sim/models/player.py
# In the PlayerModel dataclass, add after `games_played: int = 17`:
    weeks_missed: list[int] = field(default_factory=list)
```

This requires importing `field` from `dataclasses`. The file already imports `dataclass` but not `field`. Update the import:

```python
from dataclasses import dataclass, field
```

The full `PlayerModel` should look like:

```python
@dataclass
class PlayerModel:
    """Complete model for one player."""
    player_id: str
    name: str
    position: str
    team: str
    usage: PlayerUsage
    outcomes: PlayerOutcomes
    games_played: int = 17
    weeks_missed: list[int] = field(default_factory=list)
```

- [ ] **Step 3: Add `week` field to `GameState`**

```python
# src/fantasy_sim/engine/types.py
# In the GameState dataclass, add after `game_over: bool = False`:
    week: int = 0  # 0 = unset (no week-based filtering)
```

- [ ] **Step 4: Update `apply_player_override` to set `weeks_missed`**

```python
# src/fantasy_sim/overrides/engine.py
# In the apply_player_override function, find the elif block for "games_missed":
        elif field == "games_missed":
            # games_missed is a list of week numbers; convert to games_played
            player.games_played = 17 - len(value)

# Replace it with:
        elif field == "games_missed":
            # games_missed is a list of week numbers; store and convert to games_played
            player.weeks_missed = list(value)
            player.games_played = 17 - len(value)
```

- [ ] **Step 5: Update player selector to filter out players in missed weeks**

```python
# src/fantasy_sim/engine/player_selector.py
# Replace the entire file:

"""Player selection for play-by-play simulation.

Thin wrappers around TeamRoster selection methods that add
game-state awareness (e.g., red zone detection, week-based availability).
"""

import numpy as np
from fantasy_sim.engine.types import GameState
from fantasy_sim.models.player import PlayerModel, TeamRoster


def _filter_available(roster: TeamRoster, state: GameState) -> TeamRoster:
    """Return a filtered roster excluding players who have the current week
    in their weeks_missed list.

    If week is 0 (unset), no filtering is applied.
    Returns original roster if no players are filtered out.
    """
    if state.week == 0:
        return roster
    available = [
        p for p in roster.players
        if state.week not in p.weeks_missed
    ]
    if not available:
        # Safety: never return an empty roster; fall back to full roster
        return roster
    if len(available) == len(roster.players):
        return roster
    return TeamRoster(team=roster.team, players=available)


def select_passer(roster: TeamRoster, state: GameState | None = None) -> PlayerModel:
    """Select the starting QB.

    If state is provided, filters out QBs missing this week.
    Falls back to unfiltered roster if no QBs remain after filtering.
    """
    if state is not None and state.week > 0:
        filtered = _filter_available(roster, state)
        try:
            return filtered.get_starting_qb()
        except ValueError:
            pass  # Fall back to unfiltered
    return roster.get_starting_qb()


def select_receiver(
    roster: TeamRoster,
    state: GameState,
    rng: np.random.Generator,
) -> PlayerModel:
    """Select a receiver weighted by target share, filtering out missed-week players."""
    filtered = _filter_available(roster, state)
    is_red_zone = state.yard_line <= 20
    return filtered.select_receiver(rng, is_red_zone=is_red_zone)


def select_rusher(
    roster: TeamRoster,
    state: GameState,
    rng: np.random.Generator,
    is_scramble: bool = False,
) -> PlayerModel:
    """Select a ball carrier, filtering out missed-week players. If scramble, returns the QB."""
    if is_scramble:
        if state.week > 0:
            filtered = _filter_available(roster, state)
            try:
                return filtered.get_starting_qb()
            except ValueError:
                pass
        return roster.get_starting_qb()
    filtered = _filter_available(roster, state)
    is_red_zone = state.yard_line <= 20
    return filtered.select_rusher(rng, is_red_zone=is_red_zone)
```

- [ ] **Step 6: Update `select_passer` call site in `play_resolver.py`**

The current call in `_resolve_pass` (line 52 of `play_resolver.py`) is:

```python
        passer = select_passer(roster)
```

This needs to pass `state` now. Find this line and replace with:

```python
        passer = select_passer(roster, state)
```

- [ ] **Step 7: Pass `week` into `GameState` in `simulate_game`**

In `src/fantasy_sim/engine/game_sim.py`, update `simulate_game` to accept an optional `week` parameter and pass it to `GameState`:

Find the function signature:

```python
def simulate_game(
    home_dists: TeamDistributions,
    away_dists: TeamDistributions,
    rng: np.random.Generator,
    home_roster: TeamRoster | None = None,
    away_roster: TeamRoster | None = None,
) -> GameResult:
```

Replace with:

```python
def simulate_game(
    home_dists: TeamDistributions,
    away_dists: TeamDistributions,
    rng: np.random.Generator,
    home_roster: TeamRoster | None = None,
    away_roster: TeamRoster | None = None,
    week: int = 0,
) -> GameResult:
```

Find the `GameState(` constructor call and add `week=week` after `receiving_2nd_half="away",`:

```python
    state = GameState(
        quarter=1, clock=900, possession="home",
        down=1, distance=10, yard_line=75,
        home_score=0, away_score=0,
        home_team=home_dists.play_calling.team,
        away_team=away_dists.play_calling.team,
        receiving_2nd_half="away",
        week=week,
    )
```

- [ ] **Step 8: Run tests and verify**

Run: `cd /Users/chrisesposito/Documents/github/fantasy-projections-simulator && python -m pytest tests/test_overrides/test_weeks_missed.py -v`

All tests should pass. Then run full suite:

Run: `cd /Users/chrisesposito/Documents/github/fantasy-projections-simulator && python -m pytest tests/ -x --ignore=tests/test_integration`

- [ ] **Step 9: Commit**

```
git add src/fantasy_sim/models/player.py src/fantasy_sim/engine/types.py src/fantasy_sim/engine/player_selector.py src/fantasy_sim/engine/play_resolver.py src/fantasy_sim/engine/game_sim.py src/fantasy_sim/overrides/engine.py tests/test_overrides/test_weeks_missed.py
git commit -m "Implement per-week zero-out for games_missed override

Add weeks_missed list to PlayerModel, week field to GameState, and
filter unavailable players in player_selector. Players with the
current week in weeks_missed produce zero stats for that week."
```

---

### Task 3: Pace Override (Gaps 28, 29)

**Files:**
- Modify: `src/fantasy_sim/engine/types.py`
- Modify: `src/fantasy_sim/engine/play_resolver.py`
- Modify: `src/fantasy_sim/overrides/engine.py`
- Create: `tests/test_overrides/test_pace_override.py`

- [ ] **Step 1: Write failing tests for pace factor**

```python
# tests/test_overrides/test_pace_override.py
import numpy as np
import pytest
from fantasy_sim.engine.types import TeamDistributions, GameState, PlayResult
from fantasy_sim.engine.play_resolver import resolve_play, _scale_clock_runoff
from fantasy_sim.engine.game_sim import simulate_game
from fantasy_sim.overrides.engine import apply_team_override, TEAM_OVERRIDE_FIELDS
from fantasy_sim.models.distributions import (
    PlayCallingDist, PlayOutcomeDist, TurnoverRates, KickingModel, DriveStartModel,
)


def make_dists(team: str = "KC", pace_factor: float = 1.0) -> TeamDistributions:
    return TeamDistributions(
        play_calling=PlayCallingDist(
            team=team, distributions={}, default={"pass": 0.57, "run": 0.43}
        ),
        play_outcomes=PlayOutcomeDist(distributions={}, defaults={
            "pass": np.array([0, 0, 5, 7, 8, 10, 12, 15, 20]),
            "run": np.array([-2, 0, 1, 2, 3, 4, 5, 6, 7, 8]),
        }),
        turnover_rates=TurnoverRates(
            team=team, int_rate=0.025, fumble_rate=0.012,
            sack_rate=0.065, sack_fumble_rate=0.10,
        ),
        kicking=KickingModel(
            fg_make_rate={"0_39": 0.93, "40_49": 0.82, "50_plus": 0.65},
            xp_rate=0.94,
        ),
        drive_start=DriveStartModel(
            touchback_rate=0.55, touchback_yardline=75,
            return_yardlines=np.array([72, 74, 76, 78, 80]),
        ),
        pace_factor=pace_factor,
    )


class TestPaceFactorField:
    def test_team_distributions_has_pace_factor(self):
        dists = make_dists()
        assert hasattr(dists, "pace_factor")
        assert dists.pace_factor == 1.0

    def test_pace_factor_custom_value(self):
        dists = make_dists(pace_factor=1.15)
        assert dists.pace_factor == pytest.approx(1.15)


class TestScaleClockRunoff:
    def test_neutral_pace_no_change(self):
        assert _scale_clock_runoff(38, 1.0) == 38

    def test_fast_pace_reduces_runoff(self):
        # pace_factor > 1.0 means faster pace -> less clock consumed per play
        scaled = _scale_clock_runoff(38, 1.2)
        assert scaled < 38
        assert scaled == round(38 / 1.2)

    def test_slow_pace_increases_runoff(self):
        # pace_factor < 1.0 means slower pace -> more clock consumed per play
        scaled = _scale_clock_runoff(38, 0.85)
        assert scaled > 38
        assert scaled == round(38 / 0.85)

    def test_minimum_runoff_is_1(self):
        # Even with extremely fast pace, clock should still tick at least 1 second
        scaled = _scale_clock_runoff(5, 100.0)
        assert scaled >= 1


class TestPaceOverrideField:
    def test_pace_plays_per_game_in_valid_fields(self):
        assert "pace_plays_per_game" in TEAM_OVERRIDE_FIELDS

    def test_apply_pace_override(self):
        dists = make_dists()
        apply_team_override(dists, {"pace_plays_per_game": 66})
        # 66 plays/game vs baseline 65 -> pace_factor = 66/65 ≈ 1.015
        assert dists.pace_factor > 1.0

    def test_apply_high_pace_override(self):
        dists = make_dists()
        apply_team_override(dists, {"pace_plays_per_game": 72})
        # 72/65 ≈ 1.108
        assert dists.pace_factor == pytest.approx(72 / 65, abs=0.01)

    def test_apply_slow_pace_override(self):
        dists = make_dists()
        apply_team_override(dists, {"pace_plays_per_game": 58})
        # 58/65 ≈ 0.892
        assert dists.pace_factor == pytest.approx(58 / 65, abs=0.01)


class TestPaceAffectsPlayCount:
    def test_faster_pace_produces_more_plays(self):
        """A team with pace_factor > 1 should produce more total plays on average."""
        rng_normal = np.random.default_rng(42)
        rng_fast = np.random.default_rng(42)

        normal_dists = make_dists("HOME", pace_factor=1.0)
        fast_dists = make_dists("AWAY", pace_factor=1.3)

        # Run several games with neutral pace
        normal_plays = []
        for i in range(20):
            r = simulate_game(normal_dists, make_dists("AWAY", 1.0), rng_normal)
            normal_plays.append(r.total_plays)

        # Run same games with fast pace on home team
        fast_plays = []
        for i in range(20):
            r = simulate_game(fast_dists, make_dists("AWAY", 1.0), rng_fast)
            fast_plays.append(r.total_plays)

        avg_normal = np.mean(normal_plays)
        avg_fast = np.mean(fast_plays)
        # Fast pace should produce noticeably more plays
        assert avg_fast > avg_normal, (
            f"Fast pace ({avg_fast:.1f} plays) should exceed normal ({avg_normal:.1f} plays)"
        )
```

Run: `cd /Users/chrisesposito/Documents/github/fantasy-projections-simulator && python -m pytest tests/test_overrides/test_pace_override.py -x` -- expect failures.

- [ ] **Step 2: Add `pace_factor` to `TeamDistributions`**

```python
# src/fantasy_sim/engine/types.py
# In the TeamDistributions dataclass, add after the drive_start field:
    pace_factor: float = 1.0  # >1 = faster pace (more plays), <1 = slower pace
```

- [ ] **Step 3: Add `_scale_clock_runoff` to play_resolver and apply it**

```python
# src/fantasy_sim/engine/play_resolver.py
# Add this function after the SACK_YARDS constant (around line 20):

def _scale_clock_runoff(base_runoff: int, pace_factor: float) -> int:
    """Scale clock runoff by pace factor.

    pace_factor > 1.0: faster pace, less clock per play (more plays per game).
    pace_factor < 1.0: slower pace, more clock per play (fewer plays per game).
    pace_factor == 1.0: no change.

    Returns at least 1 second to prevent infinite games.
    """
    if pace_factor == 1.0:
        return base_runoff
    return max(1, round(base_runoff / pace_factor))
```

Now update `resolve_play` to accept pace_factor and scale clock_runoff. Change the signature:

```python
def resolve_play(
    state: GameState,
    play_type: str,
    play_outcomes: PlayOutcomeDist,
    turnover_rates: TurnoverRates,
    rng: np.random.Generator,
    roster: TeamRoster | None = None,
    pace_factor: float = 1.0,
) -> PlayResult:
    if play_type == "pass":
        return _resolve_pass(state, play_outcomes, turnover_rates, rng, roster, pace_factor)
    if play_type == "run":
        return _resolve_run(state, play_outcomes, turnover_rates, rng, roster, pace_factor)
    raise ValueError(f"Unexpected play_type: {play_type!r}")
```

Update `_resolve_pass` signature to accept `pace_factor: float = 1.0` and apply `_scale_clock_runoff` to every `clock_runoff` value in its return statements. The signature becomes:

```python
def _resolve_pass(
    state: GameState,
    play_outcomes: PlayOutcomeDist,
    turnover_rates: TurnoverRates,
    rng: np.random.Generator,
    roster: TeamRoster | None = None,
    pace_factor: float = 1.0,
) -> PlayResult:
```

In `_resolve_pass`, replace every `clock_runoff=CLOCK_RUN` with `clock_runoff=_scale_clock_runoff(CLOCK_RUN, pace_factor)`, every `clock_runoff=CLOCK_SACK` with `clock_runoff=_scale_clock_runoff(CLOCK_SACK, pace_factor)`, every `clock_runoff=CLOCK_PASS_INCOMPLETE` with `clock_runoff=_scale_clock_runoff(CLOCK_PASS_INCOMPLETE, pace_factor)`, and every `clock_runoff=CLOCK_PASS_COMPLETE` with `clock_runoff=_scale_clock_runoff(CLOCK_PASS_COMPLETE, pace_factor)`.

There are exactly these return statements in `_resolve_pass` to update:
1. QB scramble return (line ~82): `clock_runoff=CLOCK_RUN` -> `clock_runoff=_scale_clock_runoff(CLOCK_RUN, pace_factor)`
2. Sack return (line ~97): `clock_runoff=CLOCK_SACK` -> `clock_runoff=_scale_clock_runoff(CLOCK_SACK, pace_factor)`
3. Interception return (line ~105): `clock_runoff=CLOCK_PASS_INCOMPLETE` -> `clock_runoff=_scale_clock_runoff(CLOCK_PASS_INCOMPLETE, pace_factor)`
4. Player-aware pass return (line ~150): `clock_runoff=CLOCK_PASS_COMPLETE if is_complete else CLOCK_PASS_INCOMPLETE` -> `clock_runoff=_scale_clock_runoff(CLOCK_PASS_COMPLETE if is_complete else CLOCK_PASS_INCOMPLETE, pace_factor)`
5. Legacy pass return (line ~169): `clock_runoff=CLOCK_PASS_COMPLETE if is_complete else CLOCK_PASS_INCOMPLETE` -> `clock_runoff=_scale_clock_runoff(CLOCK_PASS_COMPLETE if is_complete else CLOCK_PASS_INCOMPLETE, pace_factor)`

Update `_resolve_run` similarly:

```python
def _resolve_run(
    state: GameState,
    play_outcomes: PlayOutcomeDist,
    turnover_rates: TurnoverRates,
    rng: np.random.Generator,
    roster: TeamRoster | None = None,
    pace_factor: float = 1.0,
) -> PlayResult:
```

Replace all `clock_runoff=CLOCK_RUN` in `_resolve_run` with `clock_runoff=_scale_clock_runoff(CLOCK_RUN, pace_factor)`. There are exactly 2: the player-aware path (line ~214) and the legacy path (line ~237).

- [ ] **Step 4: Pass `pace_factor` from `simulate_game` to `resolve_play`**

In `src/fantasy_sim/engine/game_sim.py`, find the `resolve_play` call:

```python
        result = resolve_play(
            state, play_type, off_dists.play_outcomes,
            off_dists.turnover_rates, rng, roster=roster,
        )
```

Replace with:

```python
        result = resolve_play(
            state, play_type, off_dists.play_outcomes,
            off_dists.turnover_rates, rng, roster=roster,
            pace_factor=off_dists.pace_factor,
        )
```

- [ ] **Step 5: Wire `pace_plays_per_game` override to `pace_factor`**

```python
# src/fantasy_sim/overrides/engine.py

# Add "pace_plays_per_game" to TEAM_OVERRIDE_FIELDS:
TEAM_OVERRIDE_FIELDS = {
    "pass_rate", "int_rate", "fumble_rate", "sack_rate", "sack_fumble_rate",
    "pace_plays_per_game",
}

# Baseline plays per team per game (league average ~65 offensive plays/team/game)
BASELINE_PLAYS_PER_GAME = 65
```

In the `apply_team_override` function, add a new `elif` branch before the `else` block:

```python
        elif field == "pace_plays_per_game":
            if value <= 0:
                raise ValueError(f"pace_plays_per_game must be positive, got {value}")
            dists.pace_factor = value / BASELINE_PLAYS_PER_GAME
```

- [ ] **Step 6: Run tests and verify**

Run: `cd /Users/chrisesposito/Documents/github/fantasy-projections-simulator && python -m pytest tests/test_overrides/test_pace_override.py -v`

All tests should pass. Then:

Run: `cd /Users/chrisesposito/Documents/github/fantasy-projections-simulator && python -m pytest tests/ -x --ignore=tests/test_integration`

- [ ] **Step 7: Commit**

```
git add src/fantasy_sim/engine/types.py src/fantasy_sim/engine/play_resolver.py src/fantasy_sim/engine/game_sim.py src/fantasy_sim/overrides/engine.py tests/test_overrides/test_pace_override.py
git commit -m "Implement pace_plays_per_game override via pace_factor

Add pace_factor to TeamDistributions (default 1.0). Scale all clock
runoff values in play_resolver by 1/pace_factor so faster-paced teams
consume less clock per play, producing more plays per game. Wire
pace_plays_per_game team override to compute pace_factor from a
baseline of 65 plays/team/game."
```

---

### Task 4: Fuzzy Matching Disambiguation (Gap 32)

**Files:**
- Modify: `src/fantasy_sim/overrides/resolver.py`
- Create: `tests/test_overrides/test_fuzzy_disambiguation.py`

- [ ] **Step 1: Write failing tests for ambiguous match detection**

```python
# tests/test_overrides/test_fuzzy_disambiguation.py
import pytest
from fantasy_sim.overrides.resolver import PlayerResolver, AmbiguousMatchError
from fantasy_sim.models.player import (
    PlayerModel, PlayerUsage, PlayerOutcomes, TeamRoster,
)


def make_roster_with_similar_names() -> list[TeamRoster]:
    """Create rosters with multiple players who could match 'Smith'."""
    return [
        TeamRoster(team="KC", players=[
            PlayerModel("DS01", "DeVonta Smith", "WR", "KC",
                        PlayerUsage(), PlayerOutcomes()),
            PlayerModel("DS02", "Donovan Smith", "OT", "KC",
                        PlayerUsage(), PlayerOutcomes()),
            PlayerModel("PM15", "Patrick Mahomes", "QB", "KC",
                        PlayerUsage(), PlayerOutcomes()),
        ]),
        TeamRoster(team="BUF", players=[
            PlayerModel("NS03", "Nico Smith", "WR", "BUF",
                        PlayerUsage(), PlayerOutcomes()),
            PlayerModel("JA17", "Josh Allen", "QB", "BUF",
                        PlayerUsage(), PlayerOutcomes()),
        ]),
    ]


def make_roster_unique_names() -> list[TeamRoster]:
    """Create rosters where names are easily distinguishable."""
    return [
        TeamRoster(team="KC", players=[
            PlayerModel("PM15", "Patrick Mahomes", "QB", "KC",
                        PlayerUsage(), PlayerOutcomes()),
            PlayerModel("TK87", "Travis Kelce", "TE", "KC",
                        PlayerUsage(), PlayerOutcomes()),
        ]),
    ]


class TestAmbiguousMatchError:
    def test_ambiguous_match_error_exists(self):
        """AmbiguousMatchError should be importable."""
        assert issubclass(AmbiguousMatchError, Exception)

    def test_ambiguous_match_error_is_key_error_subclass(self):
        """Should be a KeyError subclass for backward compatibility."""
        assert issubclass(AmbiguousMatchError, KeyError)


class TestAmbiguousMatchDetection:
    def test_smith_query_raises_ambiguous(self):
        """Searching for 'Smith' with multiple Smiths should raise AmbiguousMatchError."""
        resolver = PlayerResolver(make_roster_with_similar_names())
        with pytest.raises(AmbiguousMatchError) as exc_info:
            resolver.resolve("Smith")
        # Error message should list the ambiguous matches
        error_msg = str(exc_info.value)
        assert "DeVonta Smith" in error_msg or "DS01" in error_msg
        assert "Donovan Smith" in error_msg or "DS02" in error_msg

    def test_unique_name_resolves_cleanly(self):
        """Non-ambiguous names should resolve without error."""
        resolver = PlayerResolver(make_roster_unique_names())
        assert resolver.resolve("mahomes") == "PM15"
        assert resolver.resolve("kelce") == "TK87"

    def test_exact_match_bypasses_ambiguity_check(self):
        """Exact player_id match should never trigger ambiguity."""
        resolver = PlayerResolver(make_roster_with_similar_names())
        assert resolver.resolve("DS01") == "DS01"

    def test_exact_name_bypasses_ambiguity_check(self):
        """Exact full name match should never trigger ambiguity."""
        resolver = PlayerResolver(make_roster_with_similar_names())
        assert resolver.resolve("DeVonta Smith") == "DS01"

    def test_ambiguous_match_lists_options(self):
        """AmbiguousMatchError should list the conflicting players for disambiguation."""
        resolver = PlayerResolver(make_roster_with_similar_names())
        with pytest.raises(AmbiguousMatchError) as exc_info:
            resolver.resolve("Smith")
        error_msg = str(exc_info.value)
        # Should contain at least 2 player names or IDs
        match_count = sum(
            1 for name in ["DeVonta Smith", "Donovan Smith", "Nico Smith"]
            if name in error_msg
        )
        assert match_count >= 2, f"Expected 2+ player names in error, got: {error_msg}"

    def test_clear_partial_does_not_trigger_ambiguity(self):
        """'devonta' should match 'DeVonta Smith' without ambiguity."""
        resolver = PlayerResolver(make_roster_with_similar_names())
        # 'devonta' is close enough to 'DeVonta Smith' but not 'Donovan Smith'
        result = resolver.resolve("devonta smith")
        assert result == "DS01"

    def test_ambiguity_threshold(self):
        """Two matches within 5 points of each other should trigger ambiguity."""
        # This is tested implicitly by the 'Smith' test above, but let's be explicit:
        # 'Smith' matches 'DeVonta Smith', 'Donovan Smith', 'Nico Smith' all similarly
        resolver = PlayerResolver(make_roster_with_similar_names())
        with pytest.raises(AmbiguousMatchError):
            resolver.resolve("Smith")
```

Run: `cd /Users/chrisesposito/Documents/github/fantasy-projections-simulator && python -m pytest tests/test_overrides/test_fuzzy_disambiguation.py -x` -- expect failures.

- [ ] **Step 2: Implement `AmbiguousMatchError` and update `resolve()`**

```python
# src/fantasy_sim/overrides/resolver.py
# Replace the entire file:

from thefuzz import fuzz
from fantasy_sim.models.player import TeamRoster

# Minimum fuzzy match score to accept (0-100)
MIN_MATCH_SCORE = 70

# Maximum score difference between top matches to consider them ambiguous
AMBIGUITY_THRESHOLD = 5


class AmbiguousMatchError(KeyError):
    """Raised when a player query matches multiple players with similar scores."""
    pass


class PlayerResolver:
    """Resolve player names/IDs to nflverse player_id values."""

    def __init__(self, rosters: list[TeamRoster]):
        self._id_map: dict[str, str] = {}
        self._name_map: dict[str, str] = {}
        self._all_names: list[tuple[str, str]] = []

        for roster in rosters:
            for player in roster.players:
                self._id_map[player.player_id] = player.player_id
                name_lower = player.name.lower()
                self._name_map[name_lower] = player.player_id
                self._all_names.append((player.name, player.player_id))

    def resolve(self, query: str) -> str:
        """Resolve a player query to a player_id.

        Tries in order:
        1. Exact player_id match
        2. Exact name match (case-insensitive)
        3. Underscore-to-space conversion
        4. Fuzzy name match (with ambiguity detection)

        Raises KeyError if no match found.
        Raises AmbiguousMatchError if multiple players match with similar scores.
        """
        # 1. Exact ID
        if query in self._id_map:
            return self._id_map[query]

        # 2. Exact name (case-insensitive)
        query_lower = query.lower()
        if query_lower in self._name_map:
            return self._name_map[query_lower]

        # 3. Underscore conversion
        query_spaces = query_lower.replace("_", " ")
        if query_spaces in self._name_map:
            return self._name_map[query_spaces]

        # 4. Fuzzy match with ambiguity detection
        scored_matches: list[tuple[int, str, str]] = []  # (score, name, pid)
        for name, pid in self._all_names:
            score = max(
                fuzz.ratio(query_lower, name.lower()),
                fuzz.partial_ratio(query_lower, name.lower()),
            )
            if score >= MIN_MATCH_SCORE:
                scored_matches.append((score, name, pid))

        if not scored_matches:
            best_score = 0
            for name, pid in self._all_names:
                score = max(
                    fuzz.ratio(query_lower, name.lower()),
                    fuzz.partial_ratio(query_lower, name.lower()),
                )
                if score > best_score:
                    best_score = score
            raise KeyError(
                f"No player found matching '{query}'. "
                f"Best match score: {best_score}/100 (need {MIN_MATCH_SCORE}+)"
            )

        # Sort by score descending
        scored_matches.sort(key=lambda x: x[0], reverse=True)
        best_score = scored_matches[0][0]

        # Check for ambiguity: are there 2+ matches within AMBIGUITY_THRESHOLD of the best?
        close_matches = [
            (score, name, pid) for score, name, pid in scored_matches
            if best_score - score <= AMBIGUITY_THRESHOLD
        ]

        if len(close_matches) >= 2:
            options = "\n".join(
                f"  - {name} ({pid}, score={score})"
                for score, name, pid in close_matches
            )
            raise AmbiguousMatchError(
                f"Ambiguous match for '{query}'. Multiple players match with similar scores:\n"
                f"{options}\n"
                f"Please use a more specific name or the player_id directly."
            )

        return scored_matches[0][2]
```

- [ ] **Step 3: Run tests and verify**

Run: `cd /Users/chrisesposito/Documents/github/fantasy-projections-simulator && python -m pytest tests/test_overrides/test_fuzzy_disambiguation.py -v`

Also run the existing resolver tests to verify backward compatibility:

Run: `cd /Users/chrisesposito/Documents/github/fantasy-projections-simulator && python -m pytest tests/test_overrides/test_resolver.py -v`

Then full suite:

Run: `cd /Users/chrisesposito/Documents/github/fantasy-projections-simulator && python -m pytest tests/ -x --ignore=tests/test_integration`

- [ ] **Step 4: Commit**

```
git add src/fantasy_sim/overrides/resolver.py tests/test_overrides/test_fuzzy_disambiguation.py
git commit -m "Add fuzzy matching disambiguation for ambiguous player names

When 2+ players match a query within 5 points of each other (e.g.,
'Smith' matching 'DeVonta Smith' and 'Donovan Smith'), raise
AmbiguousMatchError listing all options. Exact ID and exact name
matches bypass the ambiguity check."
```

---

### Task 5: Validation Verification (Gaps 24, 25, 26)

**Files:**
- Create: `tests/test_validation/test_backtester_verification.py`

- [ ] **Step 1: Write verification tests for backtester targets, calibration, and leakage**

```python
# tests/test_validation/test_backtester_verification.py
import math
import pytest
from fantasy_sim.validation.backtester import BacktestResult, Backtester
from fantasy_sim.validation.metrics import boom_bust_calibration


class TestBacktestResultTargets:
    """Gap 24: Verify BacktestResult.passes_targets() uses all thresholds correctly."""

    def test_targets_are_defined(self):
        assert BacktestResult.WEEKLY_MAE_TARGET == 6.0
        assert BacktestResult.SEASON_MAE_TARGET == 25.0
        assert BacktestResult.RANK_CORR_TARGET == 0.80
        assert BacktestResult.CALIBRATION_TARGET == 0.10

    def test_passes_targets_when_all_good(self):
        result = BacktestResult(
            test_season=2024,
            weekly_mae=5.0,
            season_mae=20.0,
            rank_correlations={"QB": 0.85, "RB": 0.82, "WR": 0.81, "TE": 0.83},
            boom_bust_calibration=0.05,
            total_players_evaluated=100,
            total_weeks_evaluated=18,
        )
        assert result.passes_targets() is True

    def test_fails_on_high_weekly_mae(self):
        result = BacktestResult(
            test_season=2024,
            weekly_mae=7.0,  # Over 6.0 target
            season_mae=20.0,
            rank_correlations={"QB": 0.85, "RB": 0.82, "WR": 0.81, "TE": 0.83},
            boom_bust_calibration=0.05,
            total_players_evaluated=100,
            total_weeks_evaluated=18,
        )
        assert result.passes_targets() is False

    def test_fails_on_high_season_mae(self):
        result = BacktestResult(
            test_season=2024,
            weekly_mae=5.0,
            season_mae=30.0,  # Over 25.0 target
            rank_correlations={"QB": 0.85, "RB": 0.82, "WR": 0.81, "TE": 0.83},
            boom_bust_calibration=0.05,
            total_players_evaluated=100,
            total_weeks_evaluated=18,
        )
        assert result.passes_targets() is False

    def test_fails_on_low_rank_correlation(self):
        result = BacktestResult(
            test_season=2024,
            weekly_mae=5.0,
            season_mae=20.0,
            rank_correlations={"QB": 0.85, "RB": 0.75, "WR": 0.81, "TE": 0.83},
            boom_bust_calibration=0.05,
            total_players_evaluated=100,
            total_weeks_evaluated=18,
        )
        assert result.passes_targets() is False  # RB below 0.80

    def test_fails_on_missing_position_correlation(self):
        result = BacktestResult(
            test_season=2024,
            weekly_mae=5.0,
            season_mae=20.0,
            rank_correlations={"QB": 0.85, "RB": 0.82, "WR": 0.81},
            # Missing TE
            boom_bust_calibration=0.05,
            total_players_evaluated=100,
            total_weeks_evaluated=18,
        )
        assert result.passes_targets() is False  # TE defaults to 0.0

    def test_fails_on_nan_rank_correlation(self):
        result = BacktestResult(
            test_season=2024,
            weekly_mae=5.0,
            season_mae=20.0,
            rank_correlations={"QB": float("nan"), "RB": 0.82, "WR": 0.81, "TE": 0.83},
            boom_bust_calibration=0.05,
            total_players_evaluated=100,
            total_weeks_evaluated=18,
        )
        assert result.passes_targets() is False  # NaN check

    def test_fails_on_high_calibration(self):
        result = BacktestResult(
            test_season=2024,
            weekly_mae=5.0,
            season_mae=20.0,
            rank_correlations={"QB": 0.85, "RB": 0.82, "WR": 0.81, "TE": 0.83},
            boom_bust_calibration=0.15,  # Over 0.10 target
            total_players_evaluated=100,
            total_weeks_evaluated=18,
        )
        assert result.passes_targets() is False

    def test_passes_at_exact_boundary(self):
        """Targets use > and not >= for MAE/calibration."""
        result = BacktestResult(
            test_season=2024,
            weekly_mae=6.0,   # Exactly at target
            season_mae=25.0,  # Exactly at target
            rank_correlations={"QB": 0.80, "RB": 0.80, "WR": 0.80, "TE": 0.80},
            boom_bust_calibration=0.10,  # Exactly at target
            total_players_evaluated=100,
            total_weeks_evaluated=18,
        )
        assert result.passes_targets() is True  # Boundary values should pass


class TestBoomBustCalibration:
    """Gap 25: Verify boom_bust_calibration works correctly."""

    def test_perfect_calibration(self):
        predicted = {"p1": 0.3, "p2": 0.5}
        actual = {"p1": 0.3, "p2": 0.5}
        assert boom_bust_calibration(predicted, actual) == pytest.approx(0.0)

    def test_imperfect_calibration(self):
        predicted = {"p1": 0.4, "p2": 0.6}
        actual = {"p1": 0.3, "p2": 0.5}
        # MAE = (|0.4-0.3| + |0.6-0.5|) / 2 = 0.1
        assert boom_bust_calibration(predicted, actual) == pytest.approx(0.1)

    def test_mismatched_keys_only_uses_common(self):
        predicted = {"p1": 0.3, "p2": 0.5, "p3": 0.9}
        actual = {"p1": 0.3, "p2": 0.5}
        # Only p1 and p2 are common
        assert boom_bust_calibration(predicted, actual) == pytest.approx(0.0)

    def test_empty_inputs(self):
        assert boom_bust_calibration({}, {}) == pytest.approx(0.0)

    def test_no_common_keys(self):
        predicted = {"p1": 0.3}
        actual = {"p2": 0.5}
        assert boom_bust_calibration(predicted, actual) == pytest.approx(0.0)


class TestBacktestDataLeakage:
    """Gap 26: Verify training_seasons excludes test_season."""

    def test_training_seasons_excludes_test_season(self):
        bt = Backtester(test_season=2024, n_sims=10, num_training_seasons=3)
        assert bt.test_season == 2024
        assert bt.training_seasons == [2021, 2022, 2023]
        assert 2024 not in bt.training_seasons

    def test_training_seasons_with_different_window(self):
        bt = Backtester(test_season=2023, n_sims=10, num_training_seasons=2)
        assert bt.training_seasons == [2021, 2022]
        assert 2023 not in bt.training_seasons

    def test_single_training_season(self):
        bt = Backtester(test_season=2024, n_sims=10, num_training_seasons=1)
        assert bt.training_seasons == [2023]
        assert 2024 not in bt.training_seasons

    def test_training_seasons_are_contiguous(self):
        bt = Backtester(test_season=2024, n_sims=10, num_training_seasons=4)
        assert bt.training_seasons == [2020, 2021, 2022, 2023]
        # Verify contiguous
        for i in range(1, len(bt.training_seasons)):
            assert bt.training_seasons[i] == bt.training_seasons[i-1] + 1
```

Run: `cd /Users/chrisesposito/Documents/github/fantasy-projections-simulator && python -m pytest tests/test_validation/test_backtester_verification.py -v`

All tests should pass immediately (these are verification tests for existing code).

- [ ] **Step 2: Commit**

```
git add tests/test_validation/test_backtester_verification.py
git commit -m "Add verification tests for backtester targets, calibration, and leakage

Verify BacktestResult.passes_targets() checks all 4 thresholds
including NaN handling and boundary values. Verify
boom_bust_calibration works with perfect, imperfect, and edge inputs.
Verify training_seasons always excludes test_season (Gaps 24-26)."
```

---

### Task 6: Edge Case Tests (Gaps 30, 31)

**Files:**
- Create: `tests/test_edge_cases.py`

- [ ] **Step 1: Write comprehensive edge case tests**

```python
# tests/test_edge_cases.py
import numpy as np
import pytest
from click.testing import CliRunner

from fantasy_sim.engine.types import (
    TeamDistributions, TeamBoxScore, GameState, PlayerBoxScore, PlayResult,
)
from fantasy_sim.engine.game_sim import simulate_game
from fantasy_sim.engine.player_selector import select_receiver, select_rusher, select_passer
from fantasy_sim.engine.play_resolver import resolve_play
from fantasy_sim.models.distributions import (
    PlayCallingDist, PlayOutcomeDist, TurnoverRates, KickingModel, DriveStartModel,
)
from fantasy_sim.models.player import (
    PlayerModel, PlayerUsage, PlayerOutcomes, TeamRoster,
)
from fantasy_sim.overrides.engine import (
    apply_player_override, apply_team_override,
    PLAYER_USAGE_FIELDS, PLAYER_OUTCOME_FIELDS, PLAYER_META_FIELDS,
)
from fantasy_sim.overrides.resolver import PlayerResolver
from fantasy_sim.scoring.engine import score_player, score_dst, score_kicker
from fantasy_sim.scoring.projections import (
    build_player_projections, build_dst_projections, build_kicker_projections,
)
from fantasy_sim.config.loader import resolve_scoring, ConfigError
from fantasy_sim.cli import main


def make_dists(team: str = "TST") -> TeamDistributions:
    return TeamDistributions(
        play_calling=PlayCallingDist(
            team=team, distributions={}, default={"pass": 0.57, "run": 0.43}
        ),
        play_outcomes=PlayOutcomeDist(distributions={}, defaults={
            "pass": np.array([0, 5, 7, 10, 12, 15]),
            "run": np.array([-2, 0, 1, 3, 4, 5, 6, 7]),
        }),
        turnover_rates=TurnoverRates(
            team=team, int_rate=0.025, fumble_rate=0.012,
            sack_rate=0.065, sack_fumble_rate=0.10,
        ),
        kicking=KickingModel(
            fg_make_rate={"0_39": 0.93, "40_49": 0.82, "50_plus": 0.65},
            xp_rate=0.94,
        ),
        drive_start=DriveStartModel(
            touchback_rate=0.55, touchback_yardline=75,
            return_yardlines=np.array([72, 74, 76, 78, 80]),
        ),
    )


def make_minimal_roster(team: str = "TST") -> TeamRoster:
    return TeamRoster(team=team, players=[
        PlayerModel(f"{team}_QB", "QB1", "QB", team,
                    PlayerUsage(snap_share=1.0, scramble_rate=0.05),
                    PlayerOutcomes(scramble_yards_dist=np.array([3, 5, 7]))),
        PlayerModel(f"{team}_WR1", "WR1", "WR", team,
                    PlayerUsage(target_share=0.30),
                    PlayerOutcomes(catch_rate=0.65,
                                   receiving_yards_dist=np.array([5, 10, 15]))),
        PlayerModel(f"{team}_RB1", "RB1", "RB", team,
                    PlayerUsage(carry_share=0.70, target_share=0.10),
                    PlayerOutcomes(rushing_yards_dist=np.array([2, 3, 5, 7]),
                                   catch_rate=0.70,
                                   receiving_yards_dist=np.array([4, 6]))),
    ])


class TestEmptyRosterEdgeCases:
    """Gap 31: Empty roster handling."""

    def test_roster_with_only_qb(self):
        """A roster with only a QB should still handle pass plays via scramble."""
        roster = TeamRoster(team="TST", players=[
            PlayerModel("QB1", "Solo QB", "QB", "TST",
                        PlayerUsage(snap_share=1.0, scramble_rate=1.0),
                        PlayerOutcomes(scramble_yards_dist=np.array([3, 5]))),
        ])
        dists = make_dists()
        rng = np.random.default_rng(42)
        # Should not crash -- QB will scramble every pass play
        result = simulate_game(dists, make_dists("OPP"), rng,
                               home_roster=roster,
                               away_roster=make_minimal_roster("OPP"))
        assert result.total_plays > 0

    def test_select_receiver_no_eligible_raises(self):
        """Empty roster with no receivers should raise ValueError."""
        roster = TeamRoster(team="TST", players=[
            PlayerModel("QB1", "Only QB", "QB", "TST",
                        PlayerUsage(snap_share=1.0), PlayerOutcomes()),
        ])
        state = GameState(
            quarter=1, clock=900, possession="home",
            down=1, distance=10, yard_line=75,
            home_score=0, away_score=0,
            home_team="TST", away_team="OPP",
            receiving_2nd_half="away",
        )
        rng = np.random.default_rng(42)
        with pytest.raises(ValueError, match="No eligible receivers"):
            select_receiver(roster, state, rng)

    def test_select_rusher_no_eligible_raises(self):
        """Roster with no RBs and no carry_share should raise ValueError."""
        roster = TeamRoster(team="TST", players=[
            PlayerModel("QB1", "Only QB", "QB", "TST",
                        PlayerUsage(snap_share=1.0), PlayerOutcomes()),
            PlayerModel("WR1", "Only WR", "WR", "TST",
                        PlayerUsage(target_share=0.30), PlayerOutcomes()),
        ])
        state = GameState(
            quarter=1, clock=900, possession="home",
            down=1, distance=10, yard_line=75,
            home_score=0, away_score=0,
            home_team="TST", away_team="OPP",
            receiving_2nd_half="away",
        )
        rng = np.random.default_rng(42)
        with pytest.raises(ValueError, match="No eligible rushers"):
            select_rusher(roster, state, rng)


class TestInvalidOverrideValues:
    """Gap 31: Invalid override value handling."""

    def test_negative_carry_share_accepted(self):
        """Negative carry_share is technically set -- engine doesn't validate range.
        This test documents current behavior."""
        roster = make_minimal_roster()
        # This should not crash, but the value is nonsensical
        apply_player_override(roster, "TST_RB1", {"carry_share": -0.1})
        rb = next(p for p in roster.players if p.player_id == "TST_RB1")
        assert rb.usage.carry_share == -0.1

    def test_target_share_over_one_accepted(self):
        """target_share > 1.0 is set without validation.
        This test documents current behavior."""
        roster = make_minimal_roster()
        apply_player_override(roster, "TST_WR1", {"target_share": 1.5})
        wr = next(p for p in roster.players if p.player_id == "TST_WR1")
        assert wr.usage.target_share == 1.5

    def test_pass_rate_out_of_range_raises(self):
        """pass_rate must be between 0 and 1."""
        dists = make_dists()
        with pytest.raises(ValueError, match="pass_rate must be between"):
            apply_team_override(dists, {"pass_rate": 1.5})

    def test_pass_rate_negative_raises(self):
        dists = make_dists()
        with pytest.raises(ValueError, match="pass_rate must be between"):
            apply_team_override(dists, {"pass_rate": -0.1})

    def test_unknown_team_override_raises(self):
        dists = make_dists()
        with pytest.raises(ValueError, match="Unknown team override field"):
            apply_team_override(dists, {"nonexistent_field": 0.5})

    def test_unknown_player_override_raises(self):
        roster = make_minimal_roster()
        with pytest.raises(ValueError, match="Unknown override field"):
            apply_player_override(roster, "TST_WR1", {"fake_field": 0.5})


class TestOverrideForUnknownPlayer:
    """Gap 31: Override for player not on any roster."""

    def test_player_not_on_roster_raises(self):
        roster = make_minimal_roster()
        with pytest.raises(KeyError, match="not found"):
            apply_player_override(roster, "UNKNOWN_PLAYER_ID", {"target_share": 0.30})


class TestPlayerResolverEdgeCases:
    """Gap 31: PlayerResolver with edge case inputs."""

    def test_empty_rosters(self):
        resolver = PlayerResolver([])
        with pytest.raises(KeyError):
            resolver.resolve("anyone")

    def test_single_player_roster(self):
        roster = TeamRoster(team="TST", players=[
            PlayerModel("P1", "Only Player", "QB", "TST",
                        PlayerUsage(), PlayerOutcomes()),
        ])
        resolver = PlayerResolver([roster])
        assert resolver.resolve("P1") == "P1"
        assert resolver.resolve("Only Player") == "P1"

    def test_empty_query_raises(self):
        roster = make_minimal_roster()
        resolver = PlayerResolver([roster])
        with pytest.raises(KeyError):
            resolver.resolve("")


class TestScoringConfigEdgeCases:
    """Gap 31: Scoring config with missing keys."""

    def test_score_player_with_empty_config(self):
        """Missing keys should default to 0 points."""
        box = PlayerBoxScore(
            player_id="P1", name="Test", position="QB", team="TST",
            pass_yards=300, pass_tds=3, rush_yards=30,
        )
        # Empty config -- all .get() calls return 0
        assert score_player(box, {}) == 0.0

    def test_score_dst_with_empty_config(self):
        """DST scoring with empty config should return 0."""
        box = TeamBoxScore(sacks_made=3, interceptions_caught=2)
        assert score_dst(box, 14, {}) == 0.0

    def test_score_kicker_with_empty_config(self):
        box = TeamBoxScore(fg_made_0_39=2, xp_made=3)
        assert score_kicker(box, {}) == 0.0

    def test_score_player_with_partial_config(self):
        """Config with only some keys should score only those stats."""
        box = PlayerBoxScore(
            player_id="P1", name="Test", position="QB", team="TST",
            pass_yards=300, pass_tds=3, rush_yards=30,
        )
        config = {"passing_td": 4}  # Only passing TDs scored
        assert score_player(box, config) == 12.0  # 3 TDs * 4

    def test_resolve_scoring_unknown_format_raises(self):
        """Unknown scoring format should raise ConfigError."""
        presets = {"ppr": {"passing_td": 4}}
        with pytest.raises(ConfigError, match="Unknown scoring format"):
            resolve_scoring(presets, "fantasy_deluxe")

    def test_resolve_scoring_circular_inherit_raises(self):
        """Circular _inherit should raise ConfigError."""
        presets = {
            "a": {"_inherit": "b"},
            "b": {"_inherit": "a"},
        }
        with pytest.raises(ConfigError, match="Circular"):
            resolve_scoring(presets, "a")


class TestProjectionEdgeCases:
    """Gap 30: Projection building edge cases."""

    def test_build_player_projections_empty_games(self):
        assert build_player_projections([], {}) == []

    def test_build_dst_projections_empty_games(self):
        assert build_dst_projections([], {}) == []

    def test_build_kicker_projections_empty_games(self):
        assert build_kicker_projections([], {}) == []


class TestSimulationWithoutRoster:
    """Gap 30: Game simulation without rosters (legacy path)."""

    def test_simulate_game_without_rosters(self):
        """Legacy mode: no rosters, no player stats."""
        dists_home = make_dists("HOME")
        dists_away = make_dists("AWAY")
        rng = np.random.default_rng(42)
        result = simulate_game(dists_home, dists_away, rng)
        assert result.total_plays > 0
        assert result.home_score >= 0
        assert result.away_score >= 0
        assert len(result.player_stats) == 0  # No rosters = no player stats


class TestCLIEdgeCases:
    """Gap 31: CLI with invalid arguments."""

    def test_demo_with_zero_sims(self):
        runner = CliRunner()
        result = runner.invoke(main, ["demo", "--sims", "0"])
        assert result.exit_code != 0

    def test_demo_with_invalid_scoring(self):
        runner = CliRunner()
        result = runner.invoke(main, ["demo", "--scoring", "mega_ppr"])
        assert result.exit_code != 0

    def test_demo_with_invalid_format(self):
        runner = CliRunner()
        result = runner.invoke(main, ["demo", "--format", "xml"])
        assert result.exit_code != 0

    def test_demo_with_malformed_override(self):
        """Override without '=' should fail."""
        runner = CliRunner()
        result = runner.invoke(main, ["demo", "--override", "mahomes_target_share"])
        assert result.exit_code != 0

    def test_demo_with_override_missing_dot(self):
        """Override without '.' in key should fail."""
        runner = CliRunner()
        result = runner.invoke(main, ["demo", "--override", "mahomes=0.30"])
        assert result.exit_code != 0


class TestRedistributionFullValidation:
    """Gap 30: Full override redistribution validation."""

    def test_target_share_redistribution_preserves_total(self):
        """Total target share across team should be preserved after redistribution."""
        roster = make_minimal_roster()
        players = roster.players
        original_total = sum(
            p.usage.target_share for p in players if p.usage.target_share > 0
        )
        apply_player_override(roster, "TST_WR1", {"target_share": 0.50})
        new_total = sum(
            p.usage.target_share for p in players if p.usage.target_share > 0
        )
        assert new_total == pytest.approx(original_total, abs=0.01)

    def test_carry_share_redistribution_preserves_total(self):
        """Total carry share should be preserved after redistribution."""
        roster = make_minimal_roster()
        original_total = sum(
            p.usage.carry_share for p in roster.players if p.usage.carry_share > 0
        )
        apply_player_override(roster, "TST_RB1", {"carry_share": 0.90})
        new_total = sum(
            p.usage.carry_share for p in roster.players if p.usage.carry_share > 0
        )
        assert new_total == pytest.approx(original_total, abs=0.01)

    def test_shares_never_go_negative(self):
        """Redistribution should never produce negative shares."""
        roster = make_minimal_roster()
        apply_player_override(roster, "TST_WR1", {"target_share": 0.95})
        for p in roster.players:
            assert p.usage.target_share >= 0.0
            assert p.usage.carry_share >= 0.0
```

Run: `cd /Users/chrisesposito/Documents/github/fantasy-projections-simulator && python -m pytest tests/test_edge_cases.py -v`

- [ ] **Step 2: Commit**

```
git add tests/test_edge_cases.py
git commit -m "Add comprehensive edge case test suite

Cover empty rosters, invalid override values, unknown player/team
overrides, scoring config edge cases, empty projections, CLI
validation, redistribution preservation, and legacy simulation
mode (Gaps 30-31)."
```

---

### Task 7: GitHub Actions CI (Gap 33)

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Create the CI workflow file**

```bash
mkdir -p /Users/chrisesposito/Documents/github/fantasy-projections-simulator/.github/workflows
```

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.12", "3.13", "3.14"]

    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v4
        with:
          enable-cache: true
          cache-dependency-glob: "uv.lock"

      - name: Set up Python ${{ matrix.python-version }}
        run: uv python install ${{ matrix.python-version }}

      - name: Install dependencies
        run: uv sync --dev

      - name: Run tests
        run: |
          uv run python -m pytest tests/ \
            -m "not integration and not statistical" \
            --tb=short \
            -q \
            --no-header

  test-statistical:
    runs-on: ubuntu-latest
    if: contains(github.event.pull_request.labels.*.name, 'run-statistical-tests')
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v4
        with:
          enable-cache: true
          cache-dependency-glob: "uv.lock"

      - name: Set up Python
        run: uv python install 3.14

      - name: Install dependencies
        run: uv sync --dev

      - name: Run statistical tests
        run: |
          uv run python -m pytest tests/ \
            -m "statistical" \
            --tb=short \
            -q \
            --no-header
```

- [ ] **Step 2: Write a test that verifies the CI config file exists and is valid YAML**

```python
# Add to tests/test_edge_cases.py (append to the end of the file):

class TestCIConfiguration:
    """Gap 33: Verify CI workflow exists and is valid."""

    def test_ci_workflow_exists(self):
        from pathlib import Path
        ci_path = Path(__file__).parent.parent / ".github" / "workflows" / "ci.yml"
        assert ci_path.exists(), f"CI workflow not found at {ci_path}"

    def test_ci_workflow_is_valid_yaml(self):
        import yaml
        from pathlib import Path
        ci_path = Path(__file__).parent.parent / ".github" / "workflows" / "ci.yml"
        with open(ci_path) as f:
            config = yaml.safe_load(f)
        assert "on" in config
        assert "jobs" in config
        assert "test" in config["jobs"]

    def test_ci_excludes_integration_and_statistical(self):
        """CI should skip integration and statistical tests by default."""
        from pathlib import Path
        ci_path = Path(__file__).parent.parent / ".github" / "workflows" / "ci.yml"
        content = ci_path.read_text()
        assert "not integration" in content
        assert "not statistical" in content

    def test_ci_has_python_version_matrix(self):
        import yaml
        from pathlib import Path
        ci_path = Path(__file__).parent.parent / ".github" / "workflows" / "ci.yml"
        with open(ci_path) as f:
            config = yaml.safe_load(f)
        matrix = config["jobs"]["test"]["strategy"]["matrix"]
        versions = matrix["python-version"]
        assert "3.12" in versions
        assert "3.13" in versions
        assert "3.14" in versions
```

- [ ] **Step 3: Run tests to verify CI config**

Run: `cd /Users/chrisesposito/Documents/github/fantasy-projections-simulator && python -m pytest tests/test_edge_cases.py::TestCIConfiguration -v`

- [ ] **Step 4: Run full test suite one final time**

Run: `cd /Users/chrisesposito/Documents/github/fantasy-projections-simulator && python -m pytest tests/ -x --ignore=tests/test_integration -m "not statistical" -v --tb=short`

- [ ] **Step 5: Commit**

```
git add .github/workflows/ci.yml tests/test_edge_cases.py
git commit -m "Add GitHub Actions CI pipeline with Python version matrix

Run pytest on push/PR across Python 3.12, 3.13, 3.14. Cache uv
dependencies for fast installs. Skip integration and statistical
tests by default; statistical tests run only when PR has the
'run-statistical-tests' label."
```

---

## Summary of Changes by File

| File | Action | Gaps |
|------|--------|------|
| `src/fantasy_sim/engine/types.py` | Add `defensive_tds` to `TeamBoxScore`, `pace_factor` to `TeamDistributions`, `week` to `GameState` | 22, 27, 28 |
| `src/fantasy_sim/engine/game_sim.py` | Probabilistic defensive TDs in `_update_box_scores`, pass `rng` and `pace_factor`, add `week` param | 22, 27, 28 |
| `src/fantasy_sim/engine/play_resolver.py` | Add `_scale_clock_runoff`, scale all clock values by `pace_factor` | 28 |
| `src/fantasy_sim/engine/player_selector.py` | Add `_filter_available` for weeks_missed, update all selectors | 27 |
| `src/fantasy_sim/models/player.py` | Add `weeks_missed: list[int]` to `PlayerModel` | 27 |
| `src/fantasy_sim/overrides/engine.py` | Wire `games_missed` to `weeks_missed`, add `pace_plays_per_game` override | 27, 29 |
| `src/fantasy_sim/overrides/resolver.py` | Add `AmbiguousMatchError`, detect ambiguous fuzzy matches | 32 |
| `src/fantasy_sim/scoring/engine.py` | Use `defensive_tds` in `score_dst` | 22 |
| `src/fantasy_sim/scoring/projections.py` | Surface `defensive_tds` in DST projections | 22 |
| `.github/workflows/ci.yml` | New CI pipeline | 33 |
| `tests/test_engine/test_dst_defensive_tds.py` | New: DST defensive TD tests | 22 |
| `tests/test_overrides/test_weeks_missed.py` | New: Per-week zero-out tests | 27 |
| `tests/test_overrides/test_pace_override.py` | New: Pace factor tests | 28, 29 |
| `tests/test_overrides/test_fuzzy_disambiguation.py` | New: Ambiguous match tests | 32 |
| `tests/test_validation/test_backtester_verification.py` | New: Verification tests for targets, calibration, leakage | 24, 25, 26 |
| `tests/test_edge_cases.py` | New: Comprehensive edge case + CI config tests | 30, 31, 33 |

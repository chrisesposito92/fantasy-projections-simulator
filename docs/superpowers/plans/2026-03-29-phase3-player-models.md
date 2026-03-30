# Phase 3: Player Models — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build per-player usage and outcome models from historical nflverse data, integrate player selection into the game simulation engine so plays attribute to specific players, and track per-player box scores across Monte Carlo simulations.

**Architecture:** `PlayerModel` dataclasses hold per-player usage rates (target share, carry share) and empirical outcome distributions (yards per reception, yards per carry). A `TeamRoster` bundles players per team and handles weighted random selection. The play resolver gains an optional `roster` parameter — when provided, it selects specific players and uses their distributions instead of team-level ones. `PlayerBoxScore` tracks individual stats, aggregated across N sims by the Monte Carlo runner.

**Tech Stack:** Python 3.14, numpy, polars (for building models from PBP data), pytest

---

## File Structure

```
src/fantasy_sim/models/
├── game_state.py          (exists, no changes)
├── distributions.py       (exists, no changes)
└── player.py              NEW: PlayerModel, PlayerUsage, PlayerOutcomes, TeamRoster

src/fantasy_sim/data/
├── loader.py              (exists, no changes)
├── preprocessor.py        (exists, no changes)
├── pipeline.py            (exists, no changes)
└── player_builder.py      NEW: Build PlayerModels from PBP + roster data, rookie archetypes

src/fantasy_sim/engine/
├── types.py               MODIFY: Add PlayerBoxScore, update PlayResult, update GameResult
├── play_caller.py         (exists, no changes)
├── play_resolver.py       MODIFY: Add optional roster param, player-specific outcomes
├── player_selector.py     NEW: Select passer/receiver/rusher from roster
├── game_flow.py           (exists, no changes)
├── clock.py               (exists, no changes)
├── game_sim.py            MODIFY: Integrate player selection, track player stats
└── monte_carlo.py         MODIFY: Aggregate per-player stats across sims

tests/
├── conftest.py            MODIFY: Add player-related fixtures
├── test_models/
│   └── test_player.py     NEW
├── test_data/
│   └── test_player_builder.py  NEW
└── test_engine/
    ├── test_player_selector.py  NEW
    ├── test_play_resolver.py    MODIFY: Add player-aware tests
    ├── test_game_sim.py         MODIFY: Add player-tracking tests
    └── test_player_validation.py NEW: Statistical validation
```

## Dependencies from Phase 1 and Phase 2

**Phase 1 (used for building player models):**
- `data.loader.DataLoader` — `load_pbp()`, `load_player_stats()`, `load_rosters_weekly()`, `load_depth_charts()`, `load_draft_picks()`
- `models.game_state.bucket_play()` — Bucketing for per-state usage rates

**Phase 2 (engine integration):**
- `engine.types.GameState` — Current game state with `yard_line`, `down`, `quarter`, etc.
- `engine.types.PlayResult` — Play outcome (will gain player_id fields)
- `engine.types.TeamBoxScore` — Team stats (unchanged, still updated alongside player stats)
- `engine.types.GameResult` — Game result (will gain `player_stats` dict)
- `engine.types.TeamDistributions` — Team distributions bundle (unchanged, still used for sack/INT rates)
- `engine.play_resolver.resolve_play()` — Will gain optional `roster` parameter
- `engine.game_sim.simulate_game()` — Will gain optional roster parameters

**Key PBP columns used for player model building:**
- `passer_player_id`, `receiver_player_id`, `rusher_player_id` — Who was involved in each play
- `complete_pass`, `yards_gained`, `touchdown`, `fumble_lost` — Play outcomes
- `pass_attempt`, `rush_attempt` — Play type flags
- `posteam` — Possessing team
- `yardline_100` — For red zone analysis (yardline_100 <= 20)

---

### Task 1: Player Data Types

**Files:**
- Create: `src/fantasy_sim/models/player.py`
- Create: `tests/test_models/test_player.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_models/test_player.py
import numpy as np
import pytest
from fantasy_sim.models.player import (
    PlayerUsage, PlayerOutcomes, PlayerModel, TeamRoster,
)


class TestPlayerModel:
    def test_create_wr(self):
        model = PlayerModel(
            player_id="TK87", name="Travis Kelce", position="TE", team="KC",
            usage=PlayerUsage(target_share=0.22, red_zone_target_share=0.25),
            outcomes=PlayerOutcomes(
                catch_rate=0.68,
                receiving_yards_dist=np.array([5, 8, 12, 15, 20, 25, 7, 3]),
                fumble_rate=0.005,
            ),
        )
        assert model.player_id == "TK87"
        assert model.position == "TE"
        assert model.usage.target_share == pytest.approx(0.22)
        assert model.outcomes.catch_rate == pytest.approx(0.68)

    def test_create_rb(self):
        model = PlayerModel(
            player_id="IP01", name="Isiah Pacheco", position="RB", team="KC",
            usage=PlayerUsage(carry_share=0.55, target_share=0.08, red_zone_carry_share=0.60),
            outcomes=PlayerOutcomes(
                rushing_yards_dist=np.array([3, 5, -1, 7, 2, 4, 12, 1]),
                receiving_yards_dist=np.array([4, 6, 8]),
                catch_rate=0.75,
                fumble_rate=0.01,
            ),
        )
        assert model.usage.carry_share == pytest.approx(0.55)
        assert len(model.outcomes.rushing_yards_dist) == 8

    def test_create_qb(self):
        model = PlayerModel(
            player_id="PM15", name="Patrick Mahomes", position="QB", team="KC",
            usage=PlayerUsage(snap_share=1.0, scramble_rate=0.08),
            outcomes=PlayerOutcomes(
                scramble_yards_dist=np.array([5, 8, 12, -2, 3, 15]),
                fumble_rate=0.008,
            ),
        )
        assert model.usage.scramble_rate == pytest.approx(0.08)

    def test_games_played_default(self):
        model = PlayerModel(
            player_id="X", name="X", position="WR", team="T",
            usage=PlayerUsage(), outcomes=PlayerOutcomes(),
        )
        assert model.games_played == 17


class TestTeamRoster:
    @pytest.fixture
    def kc_roster(self):
        qb = PlayerModel("PM15", "Mahomes", "QB", "KC",
                         PlayerUsage(snap_share=1.0, scramble_rate=0.08),
                         PlayerOutcomes(scramble_yards_dist=np.array([5, 8, 12])))
        wr1 = PlayerModel("RE11", "Worthy", "WR", "KC",
                          PlayerUsage(target_share=0.25),
                          PlayerOutcomes(catch_rate=0.60, receiving_yards_dist=np.array([8, 12, 20])))
        wr2 = PlayerModel("TK87", "Kelce", "TE", "KC",
                          PlayerUsage(target_share=0.22),
                          PlayerOutcomes(catch_rate=0.68, receiving_yards_dist=np.array([5, 10, 15])))
        rb = PlayerModel("IP01", "Pacheco", "RB", "KC",
                         PlayerUsage(carry_share=0.60, target_share=0.10),
                         PlayerOutcomes(
                             rushing_yards_dist=np.array([3, 5, -1, 7]),
                             catch_rate=0.75, receiving_yards_dist=np.array([4, 6]),
                         ))
        rb2 = PlayerModel("CH02", "Clyde", "RB", "KC",
                          PlayerUsage(carry_share=0.30, target_share=0.05),
                          PlayerOutcomes(rushing_yards_dist=np.array([2, 4, 6])))
        return TeamRoster(team="KC", players=[qb, wr1, wr2, rb, rb2])

    def test_get_starting_qb(self, kc_roster):
        qb = kc_roster.get_starting_qb()
        assert qb.position == "QB"
        assert qb.player_id == "PM15"

    def test_select_receiver(self, kc_roster):
        rng = np.random.default_rng(42)
        receivers = [kc_roster.select_receiver(rng) for _ in range(100)]
        ids = [r.player_id for r in receivers]
        # All receivers should be from the roster
        assert all(pid in ("RE11", "TK87", "IP01", "CH02") for pid in ids)
        # WR1 and TE should appear most often (highest target shares)
        assert ids.count("RE11") > 15
        assert ids.count("TK87") > 10

    def test_select_rusher(self, kc_roster):
        rng = np.random.default_rng(42)
        rushers = [kc_roster.select_rusher(rng) for _ in range(100)]
        ids = [r.player_id for r in rushers]
        assert all(pid in ("IP01", "CH02") for pid in ids)
        # RB1 should appear ~60% of the time
        assert 40 <= ids.count("IP01") <= 80

    def test_target_shares_normalize(self, kc_roster):
        """Even if shares don't sum to 1.0, selection still works."""
        rng = np.random.default_rng(42)
        receiver = kc_roster.select_receiver(rng)
        assert receiver is not None

    def test_receiver_includes_rbs(self, kc_roster):
        """RBs with target_share > 0 should be selectable as receivers."""
        rng = np.random.default_rng(42)
        receivers = [kc_roster.select_receiver(rng) for _ in range(200)]
        ids = set(r.player_id for r in receivers)
        assert "IP01" in ids  # RB with target_share=0.10

    def test_select_receiver_red_zone(self, kc_roster):
        rng = np.random.default_rng(42)
        receiver = kc_roster.select_receiver(rng, is_red_zone=True)
        assert receiver is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_models/test_player.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement player types**

```python
# src/fantasy_sim/models/player.py
from dataclasses import dataclass, field
import numpy as np


@dataclass
class PlayerUsage:
    """How often a player is involved in plays."""
    # Rushing (RB)
    carry_share: float = 0.0
    red_zone_carry_share: float = 0.0
    # Receiving (WR/TE/RB)
    target_share: float = 0.0
    red_zone_target_share: float = 0.0
    # QB
    snap_share: float = 0.0
    scramble_rate: float = 0.0


@dataclass
class PlayerOutcomes:
    """What happens when a player is involved in a play."""
    # Receiving
    catch_rate: float = 0.0
    receiving_yards_dist: np.ndarray | None = None
    # Rushing
    rushing_yards_dist: np.ndarray | None = None
    # QB scramble
    scramble_yards_dist: np.ndarray | None = None
    # Misc
    fumble_rate: float = 0.0


@dataclass
class PlayerModel:
    """Complete model for one player."""
    player_id: str
    name: str
    position: str  # "QB", "RB", "WR", "TE", "K"
    team: str
    usage: PlayerUsage
    outcomes: PlayerOutcomes
    games_played: int = 17


@dataclass
class TeamRoster:
    """Collection of PlayerModels for one team, with selection methods."""
    team: str
    players: list[PlayerModel]

    def get_starting_qb(self) -> PlayerModel:
        """Return the QB with the highest snap share."""
        qbs = [p for p in self.players if p.position == "QB"]
        return max(qbs, key=lambda p: p.usage.snap_share)

    def select_receiver(
        self, rng: np.random.Generator, is_red_zone: bool = False
    ) -> PlayerModel:
        """Select a receiver weighted by target share."""
        eligible = [p for p in self.players if p.usage.target_share > 0]
        if not eligible:
            # Fallback: any non-QB
            eligible = [p for p in self.players if p.position != "QB"]

        if is_red_zone:
            weights = np.array([
                p.usage.red_zone_target_share if p.usage.red_zone_target_share > 0
                else p.usage.target_share
                for p in eligible
            ])
        else:
            weights = np.array([p.usage.target_share for p in eligible])

        weights = weights / weights.sum()
        idx = rng.choice(len(eligible), p=weights)
        return eligible[idx]

    def select_rusher(
        self, rng: np.random.Generator, is_red_zone: bool = False
    ) -> PlayerModel:
        """Select a ball carrier weighted by carry share."""
        eligible = [p for p in self.players if p.usage.carry_share > 0]
        if not eligible:
            # Fallback: any RB
            eligible = [p for p in self.players if p.position == "RB"]

        if is_red_zone:
            weights = np.array([
                p.usage.red_zone_carry_share if p.usage.red_zone_carry_share > 0
                else p.usage.carry_share
                for p in eligible
            ])
        else:
            weights = np.array([p.usage.carry_share for p in eligible])

        weights = weights / weights.sum()
        idx = rng.choice(len(eligible), p=weights)
        return eligible[idx]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_models/test_player.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/models/player.py tests/test_models/test_player.py
git commit -m "feat: add player model types and team roster with selection"
```

---

### Task 2: Engine Type Updates (PlayerBoxScore + PlayResult + GameResult)

**Files:**
- Modify: `src/fantasy_sim/engine/types.py`
- Modify: `tests/test_engine/test_types.py`

- [ ] **Step 1: Write failing tests for new types**

Add to `tests/test_engine/test_types.py`:

```python
from fantasy_sim.engine.types import PlayerBoxScore


class TestPlayerBoxScore:
    def test_defaults_to_zero(self):
        box = PlayerBoxScore(player_id="PM15", name="Mahomes", position="QB", team="KC")
        assert box.pass_attempts == 0
        assert box.rush_yards == 0
        assert box.targets == 0

    def test_tracks_passing(self):
        box = PlayerBoxScore(player_id="PM15", name="Mahomes", position="QB", team="KC")
        box.pass_attempts += 30
        box.completions += 22
        box.pass_yards += 280
        box.pass_tds += 2
        assert box.pass_attempts == 30
        assert box.completions == 22

    def test_tracks_receiving(self):
        box = PlayerBoxScore(player_id="TK87", name="Kelce", position="TE", team="KC")
        box.targets += 8
        box.receptions += 6
        box.receiving_yards += 78
        box.receiving_tds += 1
        assert box.targets == 8
        assert box.receptions == 6


class TestPlayResultWithPlayers:
    def test_play_result_with_player_ids(self):
        from fantasy_sim.engine.types import PlayResult
        result = PlayResult(
            play_type="pass", yards=12, is_complete=True,
            passer_id="PM15", receiver_id="TK87", clock_runoff=35,
        )
        assert result.passer_id == "PM15"
        assert result.receiver_id == "TK87"
        assert result.rusher_id is None


class TestGameResultWithPlayers:
    def test_game_result_has_player_stats(self):
        from fantasy_sim.engine.types import GameResult, TeamBoxScore
        result = GameResult(
            home_score=24, away_score=17,
            home_box=TeamBoxScore(), away_box=TeamBoxScore(),
            total_plays=120, overtime=False,
            player_stats={
                "PM15": PlayerBoxScore("PM15", "Mahomes", "QB", "KC"),
            },
        )
        assert "PM15" in result.player_stats
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_engine/test_types.py -v`
Expected: FAIL — `ImportError` for `PlayerBoxScore`

- [ ] **Step 3: Update engine types**

Add to `src/fantasy_sim/engine/types.py`:

```python
@dataclass
class PlayerBoxScore:
    """Per-player stats for one game."""
    player_id: str
    name: str
    position: str
    team: str
    # Passing
    pass_attempts: int = 0
    completions: int = 0
    pass_yards: int = 0
    pass_tds: int = 0
    interceptions: int = 0
    sacks: int = 0
    # Rushing
    rush_attempts: int = 0
    rush_yards: int = 0
    rush_tds: int = 0
    # Receiving
    targets: int = 0
    receptions: int = 0
    receiving_yards: int = 0
    receiving_tds: int = 0
    # Misc
    fumbles_lost: int = 0
```

Update the `PlayResult` dataclass to add player ID fields:

```python
@dataclass
class PlayResult:
    """Outcome of a single play."""
    play_type: str
    yards: int
    is_complete: bool = False
    is_sack: bool = False
    is_interception: bool = False
    is_fumble: bool = False
    is_touchdown: bool = False
    is_safety: bool = False
    clock_runoff: int = 0
    # Player attribution (Phase 3)
    passer_id: str | None = None
    receiver_id: str | None = None
    rusher_id: str | None = None
```

Update the `GameResult` dataclass:

```python
@dataclass
class GameResult:
    """Final result of one simulated game."""
    home_score: int
    away_score: int
    home_box: TeamBoxScore
    away_box: TeamBoxScore
    total_plays: int
    overtime: bool
    player_stats: dict[str, PlayerBoxScore] = field(default_factory=dict)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_engine/test_types.py -v`
Expected: All PASS (including existing tests — new fields have defaults)

- [ ] **Step 5: Run full test suite to verify no regressions**

Run: `uv run pytest tests/ -v`
Expected: All existing tests still pass

- [ ] **Step 6: Commit**

```bash
git add src/fantasy_sim/engine/types.py tests/test_engine/test_types.py
git commit -m "feat: add PlayerBoxScore and player IDs to PlayResult/GameResult"
```

---

### Task 3: Player Builder

**Files:**
- Create: `src/fantasy_sim/data/player_builder.py`
- Create: `tests/test_data/test_player_builder.py`
- Modify: `tests/conftest.py` (add player-building fixtures)

- [ ] **Step 1: Add player-building fixtures to conftest**

Add these fixtures to `tests/conftest.py`:

```python
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
```

- [ ] **Step 2: Write failing tests for player builder**

```python
# tests/test_data/test_player_builder.py
import numpy as np
import polars as pl
import pytest
from fantasy_sim.data.player_builder import build_player_models, build_team_roster
from fantasy_sim.models.player import PlayerModel, TeamRoster


class TestBuildPlayerModels:
    def test_returns_dict_of_player_models(self, expanded_pbp, sample_rosters):
        models = build_player_models(expanded_pbp, sample_rosters, seasons=[2024])
        assert isinstance(models, dict)
        assert "PM15" in models
        assert "TK87" in models
        assert "JA17" in models

    def test_player_has_correct_metadata(self, expanded_pbp, sample_rosters):
        models = build_player_models(expanded_pbp, sample_rosters, seasons=[2024])
        pm = models["PM15"]
        assert pm.name == "P.Mahomes"
        assert pm.position == "QB"
        assert pm.team == "KC"

    def test_wr_has_target_share(self, expanded_pbp, sample_rosters):
        models = build_player_models(expanded_pbp, sample_rosters, seasons=[2024])
        tk = models["TK87"]
        assert tk.usage.target_share > 0

    def test_rb_has_carry_share(self, expanded_pbp, sample_rosters):
        models = build_player_models(expanded_pbp, sample_rosters, seasons=[2024])
        ip = models["IP01"]
        assert ip.usage.carry_share > 0

    def test_target_shares_per_team_sum_near_one(self, expanded_pbp, sample_rosters):
        models = build_player_models(expanded_pbp, sample_rosters, seasons=[2024])
        kc_players = [m for m in models.values() if m.team == "KC"]
        total_ts = sum(p.usage.target_share for p in kc_players)
        assert total_ts == pytest.approx(1.0, abs=0.05)

    def test_carry_shares_per_team_sum_near_one(self, expanded_pbp, sample_rosters):
        models = build_player_models(expanded_pbp, sample_rosters, seasons=[2024])
        kc_rbs = [m for m in models.values() if m.team == "KC" and m.usage.carry_share > 0]
        total_cs = sum(p.usage.carry_share for p in kc_rbs)
        assert total_cs == pytest.approx(1.0, abs=0.05)

    def test_receiver_has_outcome_distributions(self, expanded_pbp, sample_rosters):
        models = build_player_models(expanded_pbp, sample_rosters, seasons=[2024])
        tk = models["TK87"]
        assert tk.outcomes.catch_rate > 0
        assert tk.outcomes.receiving_yards_dist is not None
        assert len(tk.outcomes.receiving_yards_dist) > 0

    def test_rusher_has_outcome_distributions(self, expanded_pbp, sample_rosters):
        models = build_player_models(expanded_pbp, sample_rosters, seasons=[2024])
        ip = models["IP01"]
        assert ip.outcomes.rushing_yards_dist is not None
        assert len(ip.outcomes.rushing_yards_dist) > 0

    def test_qb_has_scramble_data(self, expanded_pbp, sample_rosters):
        models = build_player_models(expanded_pbp, sample_rosters, seasons=[2024])
        pm = models["PM15"]
        assert pm.usage.snap_share > 0


class TestBuildTeamRoster:
    def test_returns_roster(self, expanded_pbp, sample_rosters):
        models = build_player_models(expanded_pbp, sample_rosters, seasons=[2024])
        roster = build_team_roster("KC", models)
        assert isinstance(roster, TeamRoster)
        assert roster.team == "KC"

    def test_roster_has_all_team_players(self, expanded_pbp, sample_rosters):
        models = build_player_models(expanded_pbp, sample_rosters, seasons=[2024])
        roster = build_team_roster("KC", models)
        ids = {p.player_id for p in roster.players}
        assert "PM15" in ids
        assert "TK87" in ids
        assert "IP01" in ids

    def test_roster_can_select_players(self, expanded_pbp, sample_rosters):
        models = build_player_models(expanded_pbp, sample_rosters, seasons=[2024])
        roster = build_team_roster("KC", models)
        rng = np.random.default_rng(42)
        assert roster.get_starting_qb() is not None
        assert roster.select_receiver(rng) is not None
        assert roster.select_rusher(rng) is not None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_player_builder.py -v`
Expected: FAIL

- [ ] **Step 4: Implement player builder**

```python
# src/fantasy_sim/data/player_builder.py
import polars as pl
import numpy as np
from fantasy_sim.models.player import PlayerModel, PlayerUsage, PlayerOutcomes, TeamRoster

# Minimum plays for a player to get their own distribution (else use positional average)
MIN_PLAYER_PLAYS = 5


def build_player_models(
    pbp: pl.DataFrame,
    rosters: pl.DataFrame,
    seasons: list[int],
) -> dict[str, PlayerModel]:
    """Build PlayerModels from PBP and roster data.

    Returns a dict keyed by player_id.
    """
    # Filter to real plays in the requested seasons
    plays = pbp.filter(
        pl.col("play_type").is_in(["pass", "run"]) &
        pl.col("season").is_in(seasons)
    )

    # Get player metadata from rosters (most recent entry per player)
    player_meta = (
        rosters.filter(pl.col("season").is_in(seasons))
        .sort("week", descending=True)
        .group_by("player_id")
        .first()
        .select(["player_id", "player_name", "position", "team"])
    )
    meta_map = {
        row["player_id"]: row
        for row in player_meta.iter_rows(named=True)
    }

    # Compute per-team totals
    team_pass_attempts = {}
    team_rush_attempts = {}
    for team in plays["posteam"].unique().to_list():
        tp = plays.filter(pl.col("posteam") == team)
        team_pass_attempts[team] = tp.filter(pl.col("play_type") == "pass").shape[0]
        team_rush_attempts[team] = tp.filter(pl.col("play_type") == "run").shape[0]

    # Build receiving stats per player
    pass_plays = plays.filter(pl.col("play_type") == "pass")
    receiving_stats = {}
    for row in pass_plays.iter_rows(named=True):
        rid = row.get("receiver_player_id")
        if rid is None:
            continue
        if rid not in receiving_stats:
            receiving_stats[rid] = {"targets": 0, "catches": 0, "yards": [], "team": row["posteam"]}
        receiving_stats[rid]["targets"] += 1
        if row["complete_pass"] == 1:
            receiving_stats[rid]["catches"] += 1
            receiving_stats[rid]["yards"].append(row["yards_gained"])

    # Build rushing stats per player
    rush_plays = plays.filter(pl.col("play_type") == "run")
    rushing_stats = {}
    for row in rush_plays.iter_rows(named=True):
        rid = row.get("rusher_player_id")
        if rid is None:
            continue
        if rid not in rushing_stats:
            rushing_stats[rid] = {"carries": 0, "yards": [], "team": row["posteam"]}
        rushing_stats[rid]["carries"] += 1
        rushing_stats[rid]["yards"].append(row["yards_gained"])

    # Build QB stats
    qb_stats = {}
    for row in pass_plays.iter_rows(named=True):
        pid = row.get("passer_player_id")
        if pid is None:
            continue
        if pid not in qb_stats:
            qb_stats[pid] = {"attempts": 0, "team": row["posteam"]}
        qb_stats[pid]["attempts"] += 1

    # Assemble PlayerModels
    models = {}
    all_player_ids = set()
    all_player_ids.update(receiving_stats.keys())
    all_player_ids.update(rushing_stats.keys())
    all_player_ids.update(qb_stats.keys())

    for pid in all_player_ids:
        meta = meta_map.get(pid)
        if meta is None:
            continue

        team = meta["team"]
        position = meta["position"]

        # Usage
        usage = PlayerUsage()
        if pid in receiving_stats:
            rs = receiving_stats[pid]
            team_pa = team_pass_attempts.get(team, 1)
            usage.target_share = rs["targets"] / team_pa
        if pid in rushing_stats:
            rs = rushing_stats[pid]
            team_ra = team_rush_attempts.get(team, 1)
            usage.carry_share = rs["carries"] / team_ra
        if position == "QB" and pid in qb_stats:
            qs = qb_stats[pid]
            team_pa = team_pass_attempts.get(team, 1)
            usage.snap_share = qs["attempts"] / team_pa

        # Outcomes
        outcomes = PlayerOutcomes()
        if pid in receiving_stats:
            rs = receiving_stats[pid]
            if rs["targets"] > 0:
                outcomes.catch_rate = rs["catches"] / rs["targets"]
            if len(rs["yards"]) >= MIN_PLAYER_PLAYS:
                outcomes.receiving_yards_dist = np.array(rs["yards"])
        if pid in rushing_stats:
            rs = rushing_stats[pid]
            if len(rs["yards"]) >= MIN_PLAYER_PLAYS:
                outcomes.rushing_yards_dist = np.array(rs["yards"])

        models[pid] = PlayerModel(
            player_id=pid,
            name=meta["player_name"],
            position=position,
            team=team,
            usage=usage,
            outcomes=outcomes,
        )

    return models


def build_team_roster(team: str, models: dict[str, PlayerModel]) -> TeamRoster:
    """Build a TeamRoster from a dict of PlayerModels."""
    team_players = [m for m in models.values() if m.team == team]
    return TeamRoster(team=team, players=team_players)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_player_builder.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/fantasy_sim/data/player_builder.py tests/test_data/test_player_builder.py tests/conftest.py
git commit -m "feat: add player builder from PBP and roster data"
```

---

### Task 4: Rookie Archetype System

**Files:**
- Create: `src/fantasy_sim/data/rookie_builder.py`
- Create: `tests/test_data/test_rookie_builder.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_data/test_rookie_builder.py
import numpy as np
import pytest
from fantasy_sim.data.rookie_builder import build_rookie_model, POSITIONAL_ARCHETYPES
from fantasy_sim.models.player import PlayerModel


class TestBuildRookieModel:
    def test_creates_player_model(self):
        model = build_rookie_model(
            player_id="RK01", name="Rookie WR", position="WR",
            team="KC", draft_round=1,
        )
        assert isinstance(model, PlayerModel)
        assert model.player_id == "RK01"
        assert model.position == "WR"

    def test_first_round_wr_has_higher_target_share(self):
        r1 = build_rookie_model("R1", "First", "WR", "KC", draft_round=1)
        r5 = build_rookie_model("R5", "Fifth", "WR", "KC", draft_round=5)
        assert r1.usage.target_share > r5.usage.target_share

    def test_first_round_rb_has_higher_carry_share(self):
        r1 = build_rookie_model("R1", "First", "RB", "KC", draft_round=1)
        r5 = build_rookie_model("R5", "Fifth", "RB", "KC", draft_round=5)
        assert r1.usage.carry_share > r5.usage.carry_share

    def test_qb_has_snap_share(self):
        model = build_rookie_model("R1", "Rookie QB", "QB", "KC", draft_round=1)
        assert model.usage.snap_share > 0

    def test_has_outcome_distributions(self):
        model = build_rookie_model("R1", "Rookie", "WR", "KC", draft_round=1)
        assert model.outcomes.catch_rate > 0
        assert model.outcomes.receiving_yards_dist is not None

    def test_undrafted_gets_minimal_share(self):
        model = build_rookie_model("UD", "Undrafted", "WR", "KC", draft_round=7)
        assert model.usage.target_share < 0.05

    def test_archetypes_exist_for_all_positions(self):
        for pos in ["QB", "RB", "WR", "TE"]:
            assert pos in POSITIONAL_ARCHETYPES
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_rookie_builder.py -v`
Expected: FAIL

- [ ] **Step 3: Implement rookie builder**

```python
# src/fantasy_sim/data/rookie_builder.py
import numpy as np
from fantasy_sim.models.player import PlayerModel, PlayerUsage, PlayerOutcomes

# Positional archetypes by draft round tier
# Tier 1: Rounds 1-2, Tier 2: Rounds 3-4, Tier 3: Rounds 5-7
POSITIONAL_ARCHETYPES = {
    "QB": {
        "tier1": {"snap_share": 0.70, "scramble_rate": 0.06,
                  "scramble_yards": [3, 5, 8, 12, -1, 2, 15],
                  "fumble_rate": 0.012},
        "tier2": {"snap_share": 0.20, "scramble_rate": 0.05,
                  "scramble_yards": [2, 4, 6, 8, -1, 1],
                  "fumble_rate": 0.015},
        "tier3": {"snap_share": 0.05, "scramble_rate": 0.04,
                  "scramble_yards": [1, 3, 5, -1],
                  "fumble_rate": 0.018},
    },
    "RB": {
        "tier1": {"carry_share": 0.45, "target_share": 0.08,
                  "rush_yards": [-2, 0, 1, 2, 3, 3, 4, 4, 5, 5, 6, 7, 8, 10, 15],
                  "rec_yards": [3, 5, 7, 10, 4, 6],
                  "catch_rate": 0.70, "fumble_rate": 0.012},
        "tier2": {"carry_share": 0.25, "target_share": 0.05,
                  "rush_yards": [-1, 0, 1, 2, 3, 3, 4, 4, 5, 6, 7, 8],
                  "rec_yards": [3, 4, 5, 7],
                  "catch_rate": 0.65, "fumble_rate": 0.015},
        "tier3": {"carry_share": 0.10, "target_share": 0.02,
                  "rush_yards": [-1, 0, 1, 2, 3, 4, 5, 6],
                  "rec_yards": [2, 4, 6],
                  "catch_rate": 0.60, "fumble_rate": 0.018},
    },
    "WR": {
        "tier1": {"target_share": 0.18, "red_zone_target_share": 0.15,
                  "rec_yards": [3, 5, 7, 8, 10, 12, 14, 15, 18, 20, 25, 30, 40],
                  "catch_rate": 0.60, "fumble_rate": 0.005},
        "tier2": {"target_share": 0.10, "red_zone_target_share": 0.08,
                  "rec_yards": [3, 5, 7, 8, 10, 12, 15, 18, 20],
                  "catch_rate": 0.58, "fumble_rate": 0.006},
        "tier3": {"target_share": 0.03, "red_zone_target_share": 0.02,
                  "rec_yards": [3, 5, 7, 8, 10, 12, 15],
                  "catch_rate": 0.55, "fumble_rate": 0.008},
    },
    "TE": {
        "tier1": {"target_share": 0.12, "red_zone_target_share": 0.15,
                  "rec_yards": [3, 5, 6, 8, 10, 12, 15, 18],
                  "catch_rate": 0.65, "fumble_rate": 0.005},
        "tier2": {"target_share": 0.06, "red_zone_target_share": 0.08,
                  "rec_yards": [3, 5, 6, 8, 10, 12],
                  "catch_rate": 0.62, "fumble_rate": 0.006},
        "tier3": {"target_share": 0.02, "red_zone_target_share": 0.03,
                  "rec_yards": [3, 4, 5, 7, 8],
                  "catch_rate": 0.58, "fumble_rate": 0.008},
    },
}


def _get_tier(draft_round: int) -> str:
    if draft_round <= 2:
        return "tier1"
    elif draft_round <= 4:
        return "tier2"
    return "tier3"


def build_rookie_model(
    player_id: str,
    name: str,
    position: str,
    team: str,
    draft_round: int,
) -> PlayerModel:
    """Generate a PlayerModel for a rookie based on draft capital archetypes."""
    tier = _get_tier(draft_round)
    archetype = POSITIONAL_ARCHETYPES[position][tier]

    usage = PlayerUsage()
    outcomes = PlayerOutcomes()

    if position == "QB":
        usage.snap_share = archetype["snap_share"]
        usage.scramble_rate = archetype["scramble_rate"]
        outcomes.scramble_yards_dist = np.array(archetype["scramble_yards"])
        outcomes.fumble_rate = archetype["fumble_rate"]
    elif position == "RB":
        usage.carry_share = archetype["carry_share"]
        usage.target_share = archetype["target_share"]
        outcomes.rushing_yards_dist = np.array(archetype["rush_yards"])
        outcomes.receiving_yards_dist = np.array(archetype["rec_yards"])
        outcomes.catch_rate = archetype["catch_rate"]
        outcomes.fumble_rate = archetype["fumble_rate"]
    elif position in ("WR", "TE"):
        usage.target_share = archetype["target_share"]
        usage.red_zone_target_share = archetype.get("red_zone_target_share", 0.0)
        outcomes.receiving_yards_dist = np.array(archetype["rec_yards"])
        outcomes.catch_rate = archetype["catch_rate"]
        outcomes.fumble_rate = archetype["fumble_rate"]

    return PlayerModel(
        player_id=player_id, name=name, position=position, team=team,
        usage=usage, outcomes=outcomes,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_rookie_builder.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/rookie_builder.py tests/test_data/test_rookie_builder.py
git commit -m "feat: add rookie archetype system for player model generation"
```

---

### Task 5: Player Selector + Play Resolver Update

**Files:**
- Create: `src/fantasy_sim/engine/player_selector.py`
- Create: `tests/test_engine/test_player_selector.py`
- Modify: `src/fantasy_sim/engine/play_resolver.py`
- Modify: `tests/test_engine/test_play_resolver.py`

- [ ] **Step 1: Write failing tests for player selector**

```python
# tests/test_engine/test_player_selector.py
import numpy as np
import pytest
from fantasy_sim.engine.player_selector import select_passer, select_receiver, select_rusher
from fantasy_sim.engine.types import GameState
from fantasy_sim.models.player import PlayerModel, PlayerUsage, PlayerOutcomes, TeamRoster


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


def make_roster() -> TeamRoster:
    qb = PlayerModel("QB1", "QB", "QB", "KC",
                     PlayerUsage(snap_share=1.0, scramble_rate=0.08),
                     PlayerOutcomes(scramble_yards_dist=np.array([5, 8])))
    wr1 = PlayerModel("WR1", "WR1", "WR", "KC",
                      PlayerUsage(target_share=0.28),
                      PlayerOutcomes(catch_rate=0.65, receiving_yards_dist=np.array([8, 12, 20])))
    te1 = PlayerModel("TE1", "TE1", "TE", "KC",
                      PlayerUsage(target_share=0.20),
                      PlayerOutcomes(catch_rate=0.70, receiving_yards_dist=np.array([5, 10])))
    rb1 = PlayerModel("RB1", "RB1", "RB", "KC",
                      PlayerUsage(carry_share=0.65, target_share=0.12),
                      PlayerOutcomes(
                          rushing_yards_dist=np.array([3, 5, 7]),
                          catch_rate=0.75, receiving_yards_dist=np.array([4, 6]),
                      ))
    return TeamRoster(team="KC", players=[qb, wr1, te1, rb1])


class TestSelectPasser:
    def test_returns_qb(self):
        roster = make_roster()
        qb = select_passer(roster)
        assert qb.position == "QB"


class TestSelectReceiver:
    def test_returns_player_with_target_share(self):
        rng = np.random.default_rng(42)
        roster = make_roster()
        state = make_state()
        receiver = select_receiver(roster, state, rng)
        assert receiver.usage.target_share > 0

    def test_wr1_most_frequent(self):
        rng = np.random.default_rng(42)
        roster = make_roster()
        state = make_state()
        ids = [select_receiver(roster, state, rng).player_id for _ in range(200)]
        assert ids.count("WR1") > ids.count("TE1")
        assert ids.count("WR1") > ids.count("RB1")


class TestSelectRusher:
    def test_returns_player_with_carry_share(self):
        rng = np.random.default_rng(42)
        roster = make_roster()
        state = make_state()
        rusher = select_rusher(roster, state, rng)
        assert rusher.usage.carry_share > 0

    def test_handles_qb_scramble(self):
        """When scramble=True, should return QB."""
        rng = np.random.default_rng(42)
        roster = make_roster()
        state = make_state()
        rusher = select_rusher(roster, state, rng, is_scramble=True)
        assert rusher.position == "QB"
```

- [ ] **Step 2: Write failing tests for player-aware play resolution**

Add to `tests/test_engine/test_play_resolver.py`:

```python
from fantasy_sim.models.player import PlayerModel, PlayerUsage, PlayerOutcomes, TeamRoster


def make_roster_for_resolver() -> TeamRoster:
    qb = PlayerModel("QB1", "QB", "QB", "T",
                     PlayerUsage(snap_share=1.0, scramble_rate=0.0),
                     PlayerOutcomes())
    wr1 = PlayerModel("WR1", "WR1", "WR", "T",
                      PlayerUsage(target_share=0.50),
                      PlayerOutcomes(
                          catch_rate=0.65,
                          receiving_yards_dist=np.array([8, 10, 12, 15, 20]),
                          fumble_rate=0.0,
                      ))
    rb1 = PlayerModel("RB1", "RB1", "RB", "T",
                      PlayerUsage(carry_share=1.0, target_share=0.50),
                      PlayerOutcomes(
                          rushing_yards_dist=np.array([3, 5, 7, 4, 6]),
                          catch_rate=0.80,
                          receiving_yards_dist=np.array([4, 6, 8]),
                          fumble_rate=0.0,
                      ))
    return TeamRoster(team="T", players=[qb, wr1, rb1])


class TestResolvePassWithPlayers:
    def test_pass_has_passer_and_receiver(self):
        rng = np.random.default_rng(42)
        state = make_state()
        outcomes = make_outcomes(pass_yards=[10])
        rates = make_turnover_rates()
        roster = make_roster_for_resolver()
        result = resolve_play(state, "pass", outcomes, rates, rng, roster=roster)
        assert result.passer_id == "QB1"
        assert result.receiver_id is not None
        assert result.receiver_id in ("WR1", "RB1")

    def test_pass_uses_player_catch_rate(self):
        """With catch_rate=0.65, we should see ~65% completions over many plays."""
        rng = np.random.default_rng(42)
        completions = 0
        n = 200
        for _ in range(n):
            state = make_state()
            outcomes = make_outcomes(pass_yards=[10])
            rates = make_turnover_rates()
            roster = make_roster_for_resolver()
            result = resolve_play(state, "pass", outcomes, rates, rng, roster=roster)
            if result.is_complete:
                completions += 1
        rate = completions / n
        assert 0.50 <= rate <= 0.85


class TestResolveRunWithPlayers:
    def test_run_has_rusher(self):
        rng = np.random.default_rng(42)
        state = make_state()
        outcomes = make_outcomes(run_yards=[5])
        rates = make_turnover_rates()
        roster = make_roster_for_resolver()
        result = resolve_play(state, "run", outcomes, rates, rng, roster=roster)
        assert result.rusher_id == "RB1"

    def test_run_uses_player_yards_dist(self):
        """Player's rushing_yards_dist=[3,5,7,4,6], so yards should be from that set."""
        rng = np.random.default_rng(42)
        state = make_state()
        outcomes = make_outcomes(run_yards=[100])  # Team dist says 100, but player dist overrides
        rates = make_turnover_rates()
        roster = make_roster_for_resolver()
        result = resolve_play(state, "run", outcomes, rates, rng, roster=roster)
        assert result.yards in [3, 4, 5, 6, 7]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_engine/test_player_selector.py tests/test_engine/test_play_resolver.py -v`
Expected: FAIL

- [ ] **Step 4: Implement player selector**

```python
# src/fantasy_sim/engine/player_selector.py
import numpy as np
from fantasy_sim.engine.types import GameState
from fantasy_sim.models.player import PlayerModel, TeamRoster


def select_passer(roster: TeamRoster) -> PlayerModel:
    """Select the starting QB."""
    return roster.get_starting_qb()


def select_receiver(
    roster: TeamRoster,
    state: GameState,
    rng: np.random.Generator,
) -> PlayerModel:
    """Select a receiver weighted by target share."""
    is_red_zone = state.yard_line <= 20
    return roster.select_receiver(rng, is_red_zone=is_red_zone)


def select_rusher(
    roster: TeamRoster,
    state: GameState,
    rng: np.random.Generator,
    is_scramble: bool = False,
) -> PlayerModel:
    """Select a ball carrier. If scramble, returns the QB."""
    if is_scramble:
        return roster.get_starting_qb()
    is_red_zone = state.yard_line <= 20
    return roster.select_rusher(rng, is_red_zone=is_red_zone)
```

- [ ] **Step 5: Update play resolver to support player models**

Modify `src/fantasy_sim/engine/play_resolver.py`:

Add `roster` parameter to `resolve_play`, `_resolve_pass`, and `_resolve_run`. When `roster` is provided, use player-specific selection and outcomes.

The updated `resolve_play` signature:

```python
def resolve_play(
    state: GameState,
    play_type: str,
    play_outcomes: PlayOutcomeDist,
    turnover_rates: TurnoverRates,
    rng: np.random.Generator,
    roster: "TeamRoster | None" = None,
) -> PlayResult:
    if play_type == "pass":
        return _resolve_pass(state, play_outcomes, turnover_rates, rng, roster)
    return _resolve_run(state, play_outcomes, turnover_rates, rng, roster)
```

Updated `_resolve_pass` — when roster is provided:
- Set passer_id from QB
- Check QB scramble rate — if scramble, resolve as a run by the QB
- Select a receiver and use their catch_rate
- If caught, sample yards from receiver's receiving_yards_dist (falling back to team dist)

Updated `_resolve_run` — when roster is provided:
- Select rusher and set rusher_id
- Sample yards from rusher's rushing_yards_dist (falling back to team dist)
- Use rusher's fumble_rate

Full updated functions:

```python
def _resolve_pass(state, play_outcomes, turnover_rates, rng, roster=None):
    from fantasy_sim.engine.player_selector import select_passer, select_receiver, select_rusher

    passer_id = None
    receiver_id = None
    rusher_id = None

    if roster is not None:
        passer = select_passer(roster)
        passer_id = passer.player_id

        # QB scramble check
        if rng.random() < passer.usage.scramble_rate:
            rusher = select_rusher(roster, state, rng, is_scramble=True)
            rusher_id = rusher.player_id
            if rusher.outcomes.scramble_yards_dist is not None:
                yards = int(rng.choice(rusher.outcomes.scramble_yards_dist))
            else:
                yards = int(rng.choice([3, 5, 8, -1, 2]))
            yards = _clamp_yards(state.yard_line, yards)
            is_td = (state.yard_line - yards) <= 0
            is_fumble = rng.random() < rusher.outcomes.fumble_rate
            return PlayResult(
                play_type="run", yards=yards, is_touchdown=is_td and not is_fumble,
                is_fumble=is_fumble, clock_runoff=CLOCK_RUN,
                passer_id=None, rusher_id=rusher_id,
            )

    # Check for sack (team-level rate)
    if rng.random() < turnover_rates.sack_rate:
        yards = int(rng.choice(SACK_YARDS))
        is_fumble = rng.random() < turnover_rates.sack_fumble_rate
        new_yl = state.yard_line - yards
        is_safety = new_yl >= 100
        return PlayResult(
            play_type="pass", yards=yards, is_sack=True,
            is_fumble=is_fumble, is_safety=is_safety,
            clock_runoff=CLOCK_SACK, passer_id=passer_id,
        )

    # Check for interception (team-level rate)
    if rng.random() < turnover_rates.int_rate:
        return PlayResult(
            play_type="pass", yards=0, is_interception=True,
            clock_runoff=CLOCK_PASS_INCOMPLETE, passer_id=passer_id,
        )

    # Normal pass — select receiver if roster available
    if roster is not None:
        receiver = select_receiver(roster, state, rng)
        receiver_id = receiver.player_id

        # Player catch rate
        is_complete = rng.random() < receiver.outcomes.catch_rate
        if is_complete and receiver.outcomes.receiving_yards_dist is not None:
            yards = int(rng.choice(receiver.outcomes.receiving_yards_dist))
        elif is_complete:
            bucket = bucket_play(state.down, state.distance, state.score_differential, state.quarter, state.yard_line)
            yards = play_outcomes.sample_yards("pass", bucket, rng)
            yards = max(yards, 1)  # Ensure completions have positive yards
        else:
            yards = 0
    else:
        # Team-level fallback (Phase 2 behavior)
        bucket = bucket_play(state.down, state.distance, state.score_differential, state.quarter, state.yard_line)
        yards = play_outcomes.sample_yards("pass", bucket, rng)
        is_complete = yards > 0

    yards = _clamp_yards(state.yard_line, yards)
    is_td = (state.yard_line - yards) <= 0

    # Fumble check
    is_fumble = False
    if is_complete:
        if roster is not None and receiver_id is not None:
            receiver = next(p for p in roster.players if p.player_id == receiver_id)
            is_fumble = rng.random() < receiver.outcomes.fumble_rate
        else:
            is_fumble = rng.random() < turnover_rates.fumble_rate

    return PlayResult(
        play_type="pass", yards=yards, is_complete=is_complete,
        is_touchdown=is_td and not is_fumble, is_fumble=is_fumble,
        clock_runoff=CLOCK_PASS_COMPLETE if is_complete else CLOCK_PASS_INCOMPLETE,
        passer_id=passer_id, receiver_id=receiver_id,
    )


def _resolve_run(state, play_outcomes, turnover_rates, rng, roster=None):
    from fantasy_sim.engine.player_selector import select_rusher

    rusher_id = None

    if roster is not None:
        rusher = select_rusher(roster, state, rng)
        rusher_id = rusher.player_id
        if rusher.outcomes.rushing_yards_dist is not None:
            yards = int(rng.choice(rusher.outcomes.rushing_yards_dist))
        else:
            bucket = bucket_play(state.down, state.distance, state.score_differential, state.quarter, state.yard_line)
            yards = play_outcomes.sample_yards("run", bucket, rng)
    else:
        bucket = bucket_play(state.down, state.distance, state.score_differential, state.quarter, state.yard_line)
        yards = play_outcomes.sample_yards("run", bucket, rng)

    yards = _clamp_yards(state.yard_line, yards)
    is_td = (state.yard_line - yards) <= 0
    is_safety = (state.yard_line - yards) >= 100

    if roster is not None and rusher_id is not None:
        rusher = next(p for p in roster.players if p.player_id == rusher_id)
        is_fumble = rng.random() < rusher.outcomes.fumble_rate
    else:
        is_fumble = rng.random() < turnover_rates.fumble_rate

    return PlayResult(
        play_type="run", yards=yards,
        is_touchdown=is_td and not is_fumble,
        is_fumble=is_fumble, is_safety=is_safety,
        clock_runoff=CLOCK_RUN, rusher_id=rusher_id,
    )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_engine/test_player_selector.py tests/test_engine/test_play_resolver.py -v`
Expected: All PASS (including existing Phase 2 tests — roster=None preserves old behavior)

- [ ] **Step 7: Run full test suite for regressions**

Run: `uv run pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 8: Commit**

```bash
git add src/fantasy_sim/engine/player_selector.py tests/test_engine/test_player_selector.py src/fantasy_sim/engine/play_resolver.py tests/test_engine/test_play_resolver.py
git commit -m "feat: add player selection and player-aware play resolution"
```

---

### Task 6: Game Sim + Monte Carlo with Player Tracking

**Files:**
- Modify: `src/fantasy_sim/engine/game_sim.py`
- Modify: `src/fantasy_sim/engine/monte_carlo.py`
- Modify: `tests/test_engine/test_game_sim.py`
- Modify: `tests/test_engine/test_monte_carlo.py`

- [ ] **Step 1: Write failing tests for player-tracked game sim**

Add to `tests/test_engine/test_game_sim.py`:

```python
from fantasy_sim.models.player import PlayerModel, PlayerUsage, PlayerOutcomes, TeamRoster


def make_roster_for_sim(team: str = "T") -> TeamRoster:
    qb = PlayerModel(f"{team}_QB", "QB", "QB", team,
                     PlayerUsage(snap_share=1.0, scramble_rate=0.05),
                     PlayerOutcomes(scramble_yards_dist=np.array([3, 5, 8, 12, -1])))
    wr1 = PlayerModel(f"{team}_WR1", "WR1", "WR", team,
                      PlayerUsage(target_share=0.25),
                      PlayerOutcomes(catch_rate=0.62, receiving_yards_dist=np.array([5, 8, 10, 12, 15, 20, 25])))
    wr2 = PlayerModel(f"{team}_WR2", "WR2", "WR", team,
                      PlayerUsage(target_share=0.20),
                      PlayerOutcomes(catch_rate=0.58, receiving_yards_dist=np.array([5, 7, 10, 14, 18])))
    te = PlayerModel(f"{team}_TE", "TE", "TE", team,
                     PlayerUsage(target_share=0.18),
                     PlayerOutcomes(catch_rate=0.68, receiving_yards_dist=np.array([4, 6, 8, 12])))
    rb1 = PlayerModel(f"{team}_RB1", "RB1", "RB", team,
                      PlayerUsage(carry_share=0.60, target_share=0.10),
                      PlayerOutcomes(
                          rushing_yards_dist=np.array([0, 1, 2, 3, 3, 4, 4, 5, 5, 6, 7, 8, 12]),
                          catch_rate=0.72, receiving_yards_dist=np.array([3, 5, 7]),
                          fumble_rate=0.01,
                      ))
    rb2 = PlayerModel(f"{team}_RB2", "RB2", "RB", team,
                      PlayerUsage(carry_share=0.30, target_share=0.05),
                      PlayerOutcomes(
                          rushing_yards_dist=np.array([1, 2, 3, 4, 5, 6]),
                          catch_rate=0.65, receiving_yards_dist=np.array([3, 4]),
                          fumble_rate=0.008,
                      ))
    return TeamRoster(team=team, players=[qb, wr1, wr2, te, rb1, rb2])


class TestSimulateGameWithPlayers:
    def test_returns_player_stats(self):
        rng = np.random.default_rng(42)
        home_roster = make_roster_for_sim("H")
        away_roster = make_roster_for_sim("A")
        result = simulate_game(
            make_team_dists(), make_team_dists(), rng,
            home_roster=home_roster, away_roster=away_roster,
        )
        assert len(result.player_stats) > 0

    def test_qb_has_passing_stats(self):
        rng = np.random.default_rng(42)
        home_roster = make_roster_for_sim("H")
        away_roster = make_roster_for_sim("A")
        result = simulate_game(
            make_team_dists(), make_team_dists(), rng,
            home_roster=home_roster, away_roster=away_roster,
        )
        qb = result.player_stats.get("H_QB")
        assert qb is not None
        assert qb.pass_attempts > 0

    def test_wr_has_receiving_stats(self):
        rng = np.random.default_rng(42)
        home_roster = make_roster_for_sim("H")
        away_roster = make_roster_for_sim("A")
        result = simulate_game(
            make_team_dists(), make_team_dists(), rng,
            home_roster=home_roster, away_roster=away_roster,
        )
        wr = result.player_stats.get("H_WR1")
        assert wr is not None
        assert wr.targets > 0

    def test_rb_has_rushing_stats(self):
        rng = np.random.default_rng(42)
        home_roster = make_roster_for_sim("H")
        away_roster = make_roster_for_sim("A")
        result = simulate_game(
            make_team_dists(), make_team_dists(), rng,
            home_roster=home_roster, away_roster=away_roster,
        )
        rb = result.player_stats.get("H_RB1")
        assert rb is not None
        assert rb.rush_attempts > 0

    def test_backward_compatible_without_rosters(self):
        """simulate_game still works without rosters (Phase 2 behavior)."""
        rng = np.random.default_rng(42)
        result = simulate_game(make_team_dists(), make_team_dists(), rng)
        assert len(result.player_stats) == 0
        assert result.total_plays > 50
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_engine/test_game_sim.py::TestSimulateGameWithPlayers -v`
Expected: FAIL

- [ ] **Step 3: Update game_sim.py to support player tracking**

Update `simulate_game` to accept optional roster parameters:

```python
def simulate_game(
    home_dists: TeamDistributions,
    away_dists: TeamDistributions,
    rng: np.random.Generator,
    home_roster: "TeamRoster | None" = None,
    away_roster: "TeamRoster | None" = None,
) -> GameResult:
```

In the main loop, pass the roster to `resolve_play`:

```python
        roster = home_roster if state.possession == "home" else away_roster
        result = resolve_play(
            state, play_type, off_dists.play_outcomes,
            off_dists.turnover_rates, rng, roster=roster,
        )
```

After each play, update player box scores:

```python
        if roster is not None:
            _update_player_stats(player_stats, result)
```

Add the `_update_player_stats` helper:

```python
def _update_player_stats(
    player_stats: dict[str, PlayerBoxScore],
    result: PlayResult,
) -> None:
    """Update per-player stats from a play result."""
    # QB passing stats
    if result.passer_id is not None:
        qb = player_stats.setdefault(result.passer_id, PlayerBoxScore(
            player_id=result.passer_id, name="", position="QB", team=""))
        if result.play_type == "pass":
            qb.pass_attempts += 1
            if result.is_sack:
                qb.sacks += 1
            elif result.is_interception:
                qb.interceptions += 1
            elif result.is_complete:
                qb.completions += 1
                qb.pass_yards += result.yards
                if result.is_touchdown:
                    qb.pass_tds += 1

    # Receiver stats
    if result.receiver_id is not None:
        rec = player_stats.setdefault(result.receiver_id, PlayerBoxScore(
            player_id=result.receiver_id, name="", position="", team=""))
        rec.targets += 1
        if result.is_complete:
            rec.receptions += 1
            rec.receiving_yards += result.yards
            if result.is_touchdown:
                rec.receiving_tds += 1
        if result.is_fumble and result.is_complete:
            rec.fumbles_lost += 1

    # Rusher stats
    if result.rusher_id is not None:
        rush = player_stats.setdefault(result.rusher_id, PlayerBoxScore(
            player_id=result.rusher_id, name="", position="", team=""))
        rush.rush_attempts += 1
        rush.rush_yards += result.yards
        if result.is_touchdown:
            rush.rush_tds += 1
        if result.is_fumble:
            rush.fumbles_lost += 1
```

Return player_stats in GameResult:

```python
    return GameResult(
        home_score=state.home_score,
        away_score=state.away_score,
        home_box=home_box,
        away_box=away_box,
        total_plays=total_plays,
        overtime=state.quarter >= 5,
        player_stats=player_stats,
    )
```

- [ ] **Step 4: Update monte_carlo.py summary to include player aggregation**

Update `run_simulations` to accept optional rosters and pass them through:

```python
def run_simulations(
    home_dists: TeamDistributions,
    away_dists: TeamDistributions,
    n_sims: int = 1000,
    seed: int = 42,
    home_roster: "TeamRoster | None" = None,
    away_roster: "TeamRoster | None" = None,
) -> SimulationSummary:
    """Run N game simulations and return all results."""
    rng = np.random.default_rng(seed)
    games = []
    for _ in range(n_sims):
        result = simulate_game(home_dists, away_dists, rng,
                              home_roster=home_roster, away_roster=away_roster)
        games.append(result)
    return SimulationSummary(games=games)
```

Add to `SimulationSummary`:

```python
    def player_summary(self) -> dict[str, dict]:
        """Aggregate per-player stats across all simulations."""
        from collections import defaultdict
        player_totals = defaultdict(lambda: defaultdict(list))

        for game in self.games:
            for pid, box in game.player_stats.items():
                player_totals[pid]["pass_yards"].append(box.pass_yards)
                player_totals[pid]["rush_yards"].append(box.rush_yards)
                player_totals[pid]["receiving_yards"].append(box.receiving_yards)
                player_totals[pid]["targets"].append(box.targets)
                player_totals[pid]["receptions"].append(box.receptions)
                player_totals[pid]["pass_tds"].append(box.pass_tds)
                player_totals[pid]["rush_tds"].append(box.rush_tds)
                player_totals[pid]["receiving_tds"].append(box.receiving_tds)

        result = {}
        for pid, stats in player_totals.items():
            result[pid] = {
                k: {"mean": np.mean(v), "std": np.std(v),
                     "floor": np.percentile(v, 10), "ceiling": np.percentile(v, 90)}
                for k, v in stats.items()
            }
        return result
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_engine/ -v`
Expected: All PASS (including all Phase 2 tests — backward compatible)

- [ ] **Step 6: Commit**

```bash
git add src/fantasy_sim/engine/game_sim.py src/fantasy_sim/engine/monte_carlo.py tests/test_engine/test_game_sim.py tests/test_engine/test_monte_carlo.py
git commit -m "feat: integrate player tracking into game sim and Monte Carlo runner"
```

---

### Task 7: Statistical Validation

**Files:**
- Create: `tests/test_engine/test_player_validation.py`
- Create: `scripts/validate_players.py`

- [ ] **Step 1: Write statistical validation tests**

```python
# tests/test_engine/test_player_validation.py
import numpy as np
import pytest
from fantasy_sim.engine.monte_carlo import run_simulations
from fantasy_sim.engine.types import TeamDistributions
from fantasy_sim.models.distributions import (
    PlayCallingDist, PlayOutcomeDist, TurnoverRates, KickingModel, DriveStartModel,
)
from fantasy_sim.models.player import PlayerModel, PlayerUsage, PlayerOutcomes, TeamRoster


def make_realistic_roster(team: str) -> TeamRoster:
    """Build a roster with realistic usage splits."""
    qb = PlayerModel(f"{team}_QB", "QB1", "QB", team,
                     PlayerUsage(snap_share=1.0, scramble_rate=0.06),
                     PlayerOutcomes(scramble_yards_dist=np.array([2, 4, 6, 8, 12, -2, 3, 5])))
    wr1 = PlayerModel(f"{team}_WR1", "WR1", "WR", team,
                      PlayerUsage(target_share=0.24, red_zone_target_share=0.22),
                      PlayerOutcomes(catch_rate=0.63, receiving_yards_dist=np.array([5, 7, 8, 10, 12, 14, 16, 20, 25, 35])))
    wr2 = PlayerModel(f"{team}_WR2", "WR2", "WR", team,
                      PlayerUsage(target_share=0.18, red_zone_target_share=0.15),
                      PlayerOutcomes(catch_rate=0.60, receiving_yards_dist=np.array([5, 7, 9, 11, 13, 17, 22])))
    wr3 = PlayerModel(f"{team}_WR3", "WR3", "WR", team,
                      PlayerUsage(target_share=0.10),
                      PlayerOutcomes(catch_rate=0.58, receiving_yards_dist=np.array([4, 6, 8, 10, 14])))
    te = PlayerModel(f"{team}_TE", "TE1", "TE", team,
                     PlayerUsage(target_share=0.16, red_zone_target_share=0.20),
                     PlayerOutcomes(catch_rate=0.67, receiving_yards_dist=np.array([4, 6, 8, 10, 12, 15])))
    rb1 = PlayerModel(f"{team}_RB1", "RB1", "RB", team,
                      PlayerUsage(carry_share=0.60, target_share=0.08, red_zone_carry_share=0.65),
                      PlayerOutcomes(
                          rushing_yards_dist=np.array([-2, 0, 1, 2, 3, 3, 4, 4, 5, 5, 6, 7, 8, 10, 15, 20]),
                          catch_rate=0.72, receiving_yards_dist=np.array([3, 5, 7, 4]),
                          fumble_rate=0.008,
                      ))
    rb2 = PlayerModel(f"{team}_RB2", "RB2", "RB", team,
                      PlayerUsage(carry_share=0.30, target_share=0.05),
                      PlayerOutcomes(
                          rushing_yards_dist=np.array([0, 1, 2, 3, 4, 5, 6, 7]),
                          catch_rate=0.65, receiving_yards_dist=np.array([3, 5]),
                          fumble_rate=0.010,
                      ))
    return TeamRoster(team=team, players=[qb, wr1, wr2, wr3, te, rb1, rb2])


def make_dists() -> TeamDistributions:
    return TeamDistributions(
        play_calling=PlayCallingDist(team="T", distributions={}, default={"pass": 0.57, "run": 0.43}),
        play_outcomes=PlayOutcomeDist(distributions={}, defaults={
            "pass": np.array([0, 0, 0, 0, 5, 7, 8, 10, 12, 15, 20, 25, 30]),
            "run": np.array([-2, 0, 1, 2, 3, 3, 4, 4, 5, 6, 7, 8, 12]),
        }),
        turnover_rates=TurnoverRates(team="T", int_rate=0.025, fumble_rate=0.012, sack_rate=0.065, sack_fumble_rate=0.10),
        kicking=KickingModel(fg_make_rate={"0_39": 0.93, "40_49": 0.82, "50_plus": 0.65}, xp_rate=0.94),
        drive_start=DriveStartModel(touchback_rate=0.55, touchback_yardline=75, return_yardlines=np.array([72, 74, 76, 78, 80])),
    )


@pytest.mark.statistical
class TestPlayerStatisticalValidation:
    """Run 500 sims and verify player-level stats are plausible."""

    @pytest.fixture(scope="class")
    def sim_results(self):
        dists = make_dists()
        home_roster = make_realistic_roster("H")
        away_roster = make_realistic_roster("A")
        return run_simulations(dists, dists, n_sims=500, seed=42,
                              home_roster=home_roster, away_roster=away_roster)

    def test_qb_pass_yards_plausible(self, sim_results):
        ps = sim_results.player_summary()
        qb = ps.get("H_QB", {})
        if "pass_yards" in qb:
            mean = qb["pass_yards"]["mean"]
            assert 150 <= mean <= 400, f"QB pass yards {mean:.0f} out of range"

    def test_wr1_targets_plausible(self, sim_results):
        ps = sim_results.player_summary()
        wr = ps.get("H_WR1", {})
        if "targets" in wr:
            mean = wr["targets"]["mean"]
            assert 3 <= mean <= 15, f"WR1 targets {mean:.1f} out of range"

    def test_rb1_rush_yards_plausible(self, sim_results):
        ps = sim_results.player_summary()
        rb = ps.get("H_RB1", {})
        if "rush_yards" in rb:
            mean = rb["rush_yards"]["mean"]
            assert 30 <= mean <= 120, f"RB1 rush yards {mean:.0f} out of range"

    def test_no_negative_averages(self, sim_results):
        ps = sim_results.player_summary()
        for pid, stats in ps.items():
            for stat, values in stats.items():
                if stat in ("rush_yards",):
                    continue  # Rush yards can be negative on individual games
                assert values["mean"] >= 0, f"{pid} {stat} mean is negative"

    def test_target_shares_consistent(self, sim_results):
        """WR1 should have more targets than WR3."""
        ps = sim_results.player_summary()
        wr1_targets = ps.get("H_WR1", {}).get("targets", {}).get("mean", 0)
        wr3_targets = ps.get("H_WR3", {}).get("targets", {}).get("mean", 0)
        if wr1_targets > 0 and wr3_targets > 0:
            assert wr1_targets > wr3_targets
```

- [ ] **Step 2: Run statistical validation**

Run: `uv run pytest tests/test_engine/test_player_validation.py -v -m statistical`
Expected: All PASS

- [ ] **Step 3: Write validation script**

```python
# scripts/validate_players.py
"""Validate player-level simulation output is plausible.

Run: uv run python scripts/validate_players.py
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
from fantasy_sim.models.player import PlayerModel, PlayerUsage, PlayerOutcomes, TeamRoster


def make_roster(team):
    qb = PlayerModel(f"{team}_QB", "QB1", "QB", team,
                     PlayerUsage(snap_share=1.0, scramble_rate=0.06),
                     PlayerOutcomes(scramble_yards_dist=np.array([2, 4, 6, 8, 12, -2, 3, 5])))
    wr1 = PlayerModel(f"{team}_WR1", "WR1", "WR", team,
                      PlayerUsage(target_share=0.24),
                      PlayerOutcomes(catch_rate=0.63, receiving_yards_dist=np.array([5, 7, 8, 10, 12, 14, 16, 20, 25, 35])))
    wr2 = PlayerModel(f"{team}_WR2", "WR2", "WR", team,
                      PlayerUsage(target_share=0.18),
                      PlayerOutcomes(catch_rate=0.60, receiving_yards_dist=np.array([5, 7, 9, 11, 13, 17, 22])))
    te = PlayerModel(f"{team}_TE", "TE1", "TE", team,
                     PlayerUsage(target_share=0.16),
                     PlayerOutcomes(catch_rate=0.67, receiving_yards_dist=np.array([4, 6, 8, 10, 12, 15])))
    rb1 = PlayerModel(f"{team}_RB1", "RB1", "RB", team,
                      PlayerUsage(carry_share=0.60, target_share=0.10),
                      PlayerOutcomes(
                          rushing_yards_dist=np.array([-2, 0, 1, 2, 3, 3, 4, 4, 5, 5, 6, 7, 8, 10, 15, 20]),
                          catch_rate=0.72, receiving_yards_dist=np.array([3, 5, 7, 4]),
                          fumble_rate=0.008,
                      ))
    rb2 = PlayerModel(f"{team}_RB2", "RB2", "RB", team,
                      PlayerUsage(carry_share=0.30, target_share=0.05),
                      PlayerOutcomes(
                          rushing_yards_dist=np.array([0, 1, 2, 3, 4, 5, 6, 7]),
                          catch_rate=0.65, receiving_yards_dist=np.array([3, 5]),
                      ))
    return TeamRoster(team=team, players=[qb, wr1, wr2, te, rb1, rb2])


def main():
    n_sims = 1000
    print(f"Running {n_sims} simulated games with player models...")

    dists = TeamDistributions(
        play_calling=PlayCallingDist(team="T", distributions={}, default={"pass": 0.57, "run": 0.43}),
        play_outcomes=PlayOutcomeDist(distributions={}, defaults={
            "pass": np.array([0, 0, 0, 0, 5, 7, 8, 10, 12, 15, 20, 25, 30]),
            "run": np.array([-2, 0, 1, 2, 3, 3, 4, 4, 5, 6, 7, 8, 12]),
        }),
        turnover_rates=TurnoverRates(team="T", int_rate=0.025, fumble_rate=0.012, sack_rate=0.065, sack_fumble_rate=0.10),
        kicking=KickingModel(fg_make_rate={"0_39": 0.93, "40_49": 0.82, "50_plus": 0.65}, xp_rate=0.94),
        drive_start=DriveStartModel(touchback_rate=0.55, touchback_yardline=75, return_yardlines=np.array([72, 74, 76, 78, 80])),
    )

    results = run_simulations(dists, dists, n_sims=n_sims, seed=42,
                              home_roster=make_roster("H"), away_roster=make_roster("A"))
    ps = results.player_summary()

    print(f"\n--- Player Averages (Home Team, {n_sims} games) ---")
    for pid in ["H_QB", "H_WR1", "H_WR2", "H_TE", "H_RB1", "H_RB2"]:
        if pid not in ps:
            continue
        s = ps[pid]
        parts = []
        if s.get("pass_yards", {}).get("mean", 0) > 0:
            parts.append(f"PassYd={s['pass_yards']['mean']:.0f}")
            parts.append(f"PassTD={s['pass_tds']['mean']:.1f}")
        if s.get("rush_yards", {}).get("mean", 0) > 0:
            parts.append(f"RushYd={s['rush_yards']['mean']:.0f}")
            parts.append(f"RushTD={s['rush_tds']['mean']:.1f}")
        if s.get("targets", {}).get("mean", 0) > 0:
            parts.append(f"Tgt={s['targets']['mean']:.1f}")
            parts.append(f"Rec={s['receptions']['mean']:.1f}")
            parts.append(f"RecYd={s['receiving_yards']['mean']:.0f}")
            parts.append(f"RecTD={s['receiving_tds']['mean']:.1f}")
        print(f"  {pid:10s} {', '.join(parts)}")

    print("\n=== PLAYER VALIDATION COMPLETE ===")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 5: Run validation script**

Run: `uv run python scripts/validate_players.py`
Expected: Player averages are plausible (QB ~200-300 pass yards, WR1 ~5-9 targets, RB1 ~50-80 rush yards)

- [ ] **Step 6: Commit**

```bash
git add tests/test_engine/test_player_validation.py scripts/validate_players.py
git commit -m "feat: add player-level statistical validation"
```

---

## Phase 3 Completion Criteria

All of these must be true before Phase 3 is done:

1. All unit tests pass (player models, player builder, player selector, resolver, game sim)
2. Statistical validation passes (500+ sims produce plausible player-level stats)
3. Target shares per team sum to ~1.0
4. Carry shares per team sum to ~1.0
5. QB has passing stats, WRs have receiving stats, RBs have rushing stats
6. Rookie archetype system generates plausible models by draft round
7. `simulate_game()` still works without rosters (backward compatible)
8. `run_simulations()` can aggregate per-player stats with floor/ceiling/mean
9. Player builder can create models from PBP + roster data

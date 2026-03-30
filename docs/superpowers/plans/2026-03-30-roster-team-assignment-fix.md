# Roster/Team Assignment Bug Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix player team assignments so they come from the current-season roster instead of historical PBP training data, enabling correct handling of trades, rookies, kickers, and retired players.

**Architecture:** Split `build_player_models` into two internal steps: `_aggregate_pbp_stats` (expensive PBP iteration, cached) and `_assemble_models` (cheap roster merge, per-week). Add `target_season` and `week` parameters to `GameContextBuilder.build_game`. Thread these through all CLI callers and the backtester.

**Tech Stack:** Python 3.12+, polars, numpy, pytest

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `src/fantasy_sim/data/player_builder.py` | Modify | Split into `_aggregate_pbp_stats` + `_assemble_models`, add `build_kicker_model`, change `build_player_models` signature |
| `src/fantasy_sim/data/game_context.py` | Modify | Add `target_season`/`week` params, split cache layers, load current roster |
| `src/fantasy_sim/validation/backtester.py` | Modify | Pass `target_season`/`week` to `build_game` |
| `src/fantasy_sim/cli.py` | Modify | Thread `target_season`/`week` through all real-data commands |
| `tests/test_data/test_player_builder.py` | Modify | Update all `build_player_models` calls to new signature, add new tests |
| `tests/test_data/test_game_context.py` | Modify | Update `build_game`/`build_team_*` calls to new signatures |
| `tests/test_cli.py` | Modify | Update mock `build_game` calls to expect new params |
| `tests/conftest.py` | Modify | Add fixtures for traded players, rookies, kickers, and multi-week rosters |

---

### Task 1: Add Test Fixtures for Roster Scenarios

**Files:**
- Modify: `tests/conftest.py`

These fixtures support all subsequent tasks. They create roster data with traded players, rookies, kickers, and per-week roster changes.

- [ ] **Step 1: Add `traded_player_rosters` fixture**

This fixture has a player (Joe Mixon "JM28") on HOU in the current roster but his PBP data was generated as a CIN player. Also includes a kicker and a rookie with no PBP data.

Add to the bottom of `tests/conftest.py`:

```python
@pytest.fixture
def traded_player_rosters() -> pl.DataFrame:
    """Roster where JM28 is on HOU (traded from CIN), plus a kicker and rookie."""
    rows = []
    for week in range(1, 4):
        rows.extend([
            # Standard KC players
            {"season": 2025, "week": week, "player_id": "PM15", "player_name": "P.Mahomes", "position": "QB", "team": "KC", "status": "ACT"},
            {"season": 2025, "week": week, "player_id": "TK87", "player_name": "T.Kelce", "position": "TE", "team": "KC", "status": "ACT"},
            {"season": 2025, "week": week, "player_id": "RE11", "player_name": "R.Rice", "position": "WR", "team": "KC", "status": "ACT"},
            {"season": 2025, "week": week, "player_id": "IP01", "player_name": "I.Pacheco", "position": "RB", "team": "KC", "status": "ACT"},
            {"season": 2025, "week": week, "player_id": "KC_K", "player_name": "H.Butker", "position": "K", "team": "KC", "status": "ACT"},
            # HOU players — JM28 traded from CIN
            {"season": 2025, "week": week, "player_id": "JA17", "player_name": "J.Allen", "position": "QB", "team": "HOU", "status": "ACT"},
            {"season": 2025, "week": week, "player_id": "SD14", "player_name": "S.Diggs", "position": "WR", "team": "HOU", "status": "ACT"},
            {"season": 2025, "week": week, "player_id": "JM28", "player_name": "J.Mixon", "position": "RB", "team": "HOU", "status": "ACT"},
            {"season": 2025, "week": week, "player_id": "HOU_K", "player_name": "K.Fairbairn", "position": "K", "team": "HOU", "status": "ACT"},
            # Rookie on HOU with no PBP history
            {"season": 2025, "week": week, "player_id": "ROOK1", "player_name": "R.Rookie", "position": "WR", "team": "HOU", "status": "ACT"},
            # Retired player NOT in this roster (only in PBP) — omitted by design
            # IR player — should be excluded
            {"season": 2025, "week": week, "player_id": "IR01", "player_name": "I.Injured", "position": "RB", "team": "KC", "status": "IR"},
            # Punter — should be excluded
            {"season": 2025, "week": week, "player_id": "PNT1", "player_name": "P.Punter", "position": "P", "team": "KC", "status": "ACT"},
        ])
    return pl.DataFrame(rows)
```

- [ ] **Step 2: Add `traded_player_pbp` fixture**

PBP data where JM28 played for CIN (old team), plus a retired player "RET99" who has PBP but is not on any 2025 roster.

Add below the previous fixture:

```python
@pytest.fixture
def traded_player_pbp() -> pl.DataFrame:
    """PBP where JM28 played for CIN and RET99 is a retired player."""
    rng = np.random.RandomState(99)
    plays = []

    # KC: 20 passes (PM15 -> TK87/RE11), 10 runs (IP01)
    for i in range(20):
        receiver = rng.choice(["TK87", "RE11"], p=[0.55, 0.45])
        complete = int(rng.random() < 0.65)
        yards = int(rng.normal(8, 5)) if complete else 0
        plays.append({
            "season": 2024, "week": (i % 3) + 1, "game_id": f"2024_0{(i%3)+1}_KC",
            "play_type": "pass", "posteam": "KC", "defteam": "CIN",
            "down": 1, "ydstogo": 10, "yardline_100": 50,
            "score_differential": 0, "qtr": 1,
            "yards_gained": yards, "complete_pass": complete,
            "pass_attempt": 1, "rush_attempt": 0,
            "interception": 0, "fumble_lost": 0, "sack": 0,
            "touchdown": 0, "penalty": 0, "penalty_yards": 0,
            "passer_player_id": "PM15", "receiver_player_id": receiver,
            "rusher_player_id": None,
        })
    for i in range(10):
        plays.append({
            "season": 2024, "week": (i % 3) + 1, "game_id": f"2024_0{(i%3)+1}_KC",
            "play_type": "run", "posteam": "KC", "defteam": "CIN",
            "down": 1, "ydstogo": 10, "yardline_100": 50,
            "score_differential": 0, "qtr": 1,
            "yards_gained": int(rng.normal(4, 3)), "complete_pass": 0,
            "pass_attempt": 0, "rush_attempt": 1,
            "interception": 0, "fumble_lost": 0, "sack": 0,
            "touchdown": 0, "penalty": 0, "penalty_yards": 0,
            "passer_player_id": None, "receiver_player_id": None,
            "rusher_player_id": "IP01",
        })

    # CIN: 15 passes (JA17 -> SD14), 15 runs (JM28 on CIN + RET99 retired player)
    for i in range(15):
        complete = int(rng.random() < 0.60)
        yards = int(rng.normal(9, 6)) if complete else 0
        plays.append({
            "season": 2024, "week": (i % 3) + 1, "game_id": f"2024_0{(i%3)+1}_CIN",
            "play_type": "pass", "posteam": "CIN", "defteam": "KC",
            "down": 1, "ydstogo": 10, "yardline_100": 50,
            "score_differential": 0, "qtr": 1,
            "yards_gained": yards, "complete_pass": complete,
            "pass_attempt": 1, "rush_attempt": 0,
            "interception": 0, "fumble_lost": 0, "sack": 0,
            "touchdown": 0, "penalty": 0, "penalty_yards": 0,
            "passer_player_id": "JA17", "receiver_player_id": "SD14",
            "rusher_player_id": None,
        })
    for i in range(10):
        plays.append({
            "season": 2024, "week": (i % 3) + 1, "game_id": f"2024_0{(i%3)+1}_CIN",
            "play_type": "run", "posteam": "CIN", "defteam": "KC",
            "down": 1, "ydstogo": 10, "yardline_100": 50,
            "score_differential": 0, "qtr": 1,
            "yards_gained": int(rng.normal(4.5, 3)), "complete_pass": 0,
            "pass_attempt": 0, "rush_attempt": 1,
            "interception": 0, "fumble_lost": 0, "sack": 0,
            "touchdown": 0, "penalty": 0, "penalty_yards": 0,
            "passer_player_id": None, "receiver_player_id": None,
            "rusher_player_id": "JM28",
        })
    # Retired player RET99 — has PBP data but NOT on any 2025 roster
    for i in range(5):
        plays.append({
            "season": 2024, "week": (i % 3) + 1, "game_id": f"2024_0{(i%3)+1}_CIN",
            "play_type": "run", "posteam": "CIN", "defteam": "KC",
            "down": 1, "ydstogo": 10, "yardline_100": 50,
            "score_differential": 0, "qtr": 1,
            "yards_gained": int(rng.normal(3, 2)), "complete_pass": 0,
            "pass_attempt": 0, "rush_attempt": 1,
            "interception": 0, "fumble_lost": 0, "sack": 0,
            "touchdown": 0, "penalty": 0, "penalty_yards": 0,
            "passer_player_id": None, "receiver_player_id": None,
            "rusher_player_id": "RET99",
        })

    return pl.DataFrame(plays)
```

- [ ] **Step 3: Add `midseason_trade_rosters` fixture**

Roster where a player changes teams mid-season (week 1-4 on team A, week 5+ on team B).

```python
@pytest.fixture
def midseason_trade_rosters() -> pl.DataFrame:
    """Roster where SD14 is traded from HOU to KC at week 5."""
    rows = []
    for week in range(1, 10):
        sd14_team = "HOU" if week <= 4 else "KC"
        rows.extend([
            {"season": 2025, "week": week, "player_id": "PM15", "player_name": "P.Mahomes", "position": "QB", "team": "KC", "status": "ACT"},
            {"season": 2025, "week": week, "player_id": "TK87", "player_name": "T.Kelce", "position": "TE", "team": "KC", "status": "ACT"},
            {"season": 2025, "week": week, "player_id": "IP01", "player_name": "I.Pacheco", "position": "RB", "team": "KC", "status": "ACT"},
            {"season": 2025, "week": week, "player_id": "SD14", "player_name": "S.Diggs", "position": "WR", "team": sd14_team, "status": "ACT"},
            {"season": 2025, "week": week, "player_id": "JA17", "player_name": "J.Allen", "position": "QB", "team": "HOU", "status": "ACT"},
            {"season": 2025, "week": week, "player_id": "JM28", "player_name": "J.Mixon", "position": "RB", "team": "HOU", "status": "ACT"},
        ])
    return pl.DataFrame(rows)
```

- [ ] **Step 4: Run existing tests to verify fixtures don't break anything**

Run: `uv run pytest tests/ -x -q 2>&1 | tail -5`
Expected: All 512 tests pass (new fixtures are unused, so no impact).

- [ ] **Step 5: Commit**

```bash
git add tests/conftest.py
git commit -m "test: add fixtures for traded players, rookies, kickers, and mid-season trades"
```

---

### Task 2: Extract `_aggregate_pbp_stats` from `build_player_models`

**Files:**
- Modify: `src/fantasy_sim/data/player_builder.py`
- Modify: `tests/test_data/test_player_builder.py`

Extract the expensive PBP iteration into a standalone function that returns a stats bundle. This is a pure refactor — `build_player_models` calls the new function internally, behavior is unchanged.

- [ ] **Step 1: Write tests for `_aggregate_pbp_stats`**

Add a new test class at the top of `tests/test_data/test_player_builder.py` (after imports):

```python
from fantasy_sim.data.player_builder import (
    build_player_models, build_team_roster, blend_with_archetype,
    _aggregate_pbp_stats, build_kicker_model,
)
```

Update the existing import line to include `_aggregate_pbp_stats` and `build_kicker_model`. Then add:

```python
class TestAggregatePbpStats:
    def test_returns_receiving_stats(self, expanded_pbp):
        stats = _aggregate_pbp_stats(expanded_pbp, training_seasons=[2024])
        assert "TK87" in stats["receiving"]
        assert stats["receiving"]["TK87"]["targets"] > 0

    def test_returns_rushing_stats(self, expanded_pbp):
        stats = _aggregate_pbp_stats(expanded_pbp, training_seasons=[2024])
        assert "IP01" in stats["rushing"]
        assert stats["rushing"]["IP01"]["carries"] > 0

    def test_returns_qb_stats(self, expanded_pbp):
        stats = _aggregate_pbp_stats(expanded_pbp, training_seasons=[2024])
        assert "PM15" in stats["qb"]
        assert stats["qb"]["PM15"]["attempts"] > 0

    def test_returns_team_totals(self, expanded_pbp):
        stats = _aggregate_pbp_stats(expanded_pbp, training_seasons=[2024])
        assert stats["team_pass_attempts"]["KC"] > 0
        assert stats["team_rush_attempts"]["KC"] > 0

    def test_filters_by_training_seasons(self, expanded_pbp):
        stats = _aggregate_pbp_stats(expanded_pbp, training_seasons=[2023])
        # expanded_pbp only has season=2024 data
        assert len(stats["receiving"]) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_player_builder.py::TestAggregatePbpStats -v 2>&1 | tail -10`
Expected: FAIL — `ImportError: cannot import name '_aggregate_pbp_stats'`

- [ ] **Step 3: Implement `_aggregate_pbp_stats`**

In `src/fantasy_sim/data/player_builder.py`, add this function before `build_player_models`:

```python
def _aggregate_pbp_stats(pbp: pl.DataFrame, training_seasons: list[int]) -> dict:
    """Aggregate PBP data into per-player stat dicts. Expensive — cache the result.

    Returns dict with keys: receiving, rushing, qb, team_pass_attempts,
    team_rush_attempts, team_rz_pass_attempts, team_rz_rush_attempts, team_air_yards.
    """
    plays = pbp.filter(
        pl.col("play_type").is_in(["pass", "run"]) &
        pl.col("season").is_in(training_seasons)
    )

    has_air_yards = "air_yards" in plays.columns

    # --- Team-level totals ---
    team_pass_attempts: dict[str, int] = {}
    team_rush_attempts: dict[str, int] = {}
    team_rz_pass_attempts: dict[str, int] = {}
    team_rz_rush_attempts: dict[str, int] = {}
    team_air_yards: dict[str, float] = {}

    for team in plays["posteam"].unique().to_list():
        tp = plays.filter(pl.col("posteam") == team)
        pass_plays_team = tp.filter(pl.col("play_type") == "pass")
        rush_plays_team = tp.filter(pl.col("play_type") == "run")

        team_pass_attempts[team] = pass_plays_team.shape[0]
        team_rush_attempts[team] = rush_plays_team.shape[0]

        team_rz_pass_attempts[team] = pass_plays_team.filter(
            pl.col("yardline_100") <= 20
        ).shape[0]
        team_rz_rush_attempts[team] = rush_plays_team.filter(
            pl.col("yardline_100") <= 20
        ).shape[0]

        if has_air_yards:
            ay_series = pass_plays_team["air_yards"].drop_nulls()
            team_air_yards[team] = float(ay_series.sum()) if len(ay_series) > 0 else 0.0
        else:
            team_air_yards[team] = 0.0

    # --- Receiving stats ---
    pass_plays = plays.filter(pl.col("play_type") == "pass")
    receiving_stats: dict[str, dict] = {}
    for row in pass_plays.iter_rows(named=True):
        rid = row.get("receiver_player_id")
        if rid is None:
            continue
        if rid not in receiving_stats:
            receiving_stats[rid] = {
                "targets": 0, "catches": 0, "yards": [],
                "rz_targets": 0, "air_yards": 0.0,
                "team": row["posteam"], "game_ids": set(),
            }
        receiving_stats[rid]["targets"] += 1
        receiving_stats[rid]["game_ids"].add(row["game_id"])
        if row["yardline_100"] <= 20:
            receiving_stats[rid]["rz_targets"] += 1
        if has_air_yards and row.get("air_yards") is not None:
            receiving_stats[rid]["air_yards"] += row["air_yards"]
        if row["complete_pass"] == 1:
            receiving_stats[rid]["catches"] += 1
            receiving_stats[rid]["yards"].append(row["yards_gained"])

    # --- Rushing stats ---
    rush_plays = plays.filter(pl.col("play_type") == "run")
    rushing_stats: dict[str, dict] = {}
    for row in rush_plays.iter_rows(named=True):
        rid = row.get("rusher_player_id")
        if rid is None:
            continue
        if rid not in rushing_stats:
            rushing_stats[rid] = {
                "carries": 0, "yards": [], "rz_carries": 0,
                "team": row["posteam"], "game_ids": set(),
            }
        rushing_stats[rid]["carries"] += 1
        rushing_stats[rid]["yards"].append(row["yards_gained"])
        rushing_stats[rid]["game_ids"].add(row["game_id"])
        if row["yardline_100"] <= 20:
            rushing_stats[rid]["rz_carries"] += 1

    # --- QB stats ---
    qb_stats: dict[str, dict] = {}
    for row in pass_plays.iter_rows(named=True):
        pid = row.get("passer_player_id")
        if pid is None:
            continue
        if pid not in qb_stats:
            qb_stats[pid] = {
                "attempts": 0, "team": row["posteam"], "game_ids": set(),
            }
        qb_stats[pid]["attempts"] += 1
        qb_stats[pid]["game_ids"].add(row["game_id"])

    return {
        "receiving": receiving_stats,
        "rushing": rushing_stats,
        "qb": qb_stats,
        "team_pass_attempts": team_pass_attempts,
        "team_rush_attempts": team_rush_attempts,
        "team_rz_pass_attempts": team_rz_pass_attempts,
        "team_rz_rush_attempts": team_rz_rush_attempts,
        "team_air_yards": team_air_yards,
        "has_air_yards": has_air_yards,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_player_builder.py::TestAggregatePbpStats -v`
Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/player_builder.py tests/test_data/test_player_builder.py
git commit -m "refactor: extract _aggregate_pbp_stats from build_player_models"
```

---

### Task 3: Add `build_kicker_model` and `_assemble_models`

**Files:**
- Modify: `src/fantasy_sim/data/player_builder.py`
- Modify: `tests/test_data/test_player_builder.py`

Add the kicker placeholder factory and the roster-merge function that replaces the model-assembly section of `build_player_models`.

- [ ] **Step 1: Write tests for `build_kicker_model`**

Add to `tests/test_data/test_player_builder.py`:

```python
class TestBuildKickerModel:
    def test_returns_player_model(self):
        model = build_kicker_model("KC_K", "H.Butker", "KC")
        assert isinstance(model, PlayerModel)

    def test_has_kicker_position(self):
        model = build_kicker_model("KC_K", "H.Butker", "KC")
        assert model.position == "K"
        assert model.team == "KC"
        assert model.name == "H.Butker"

    def test_has_default_usage_and_outcomes(self):
        model = build_kicker_model("KC_K", "H.Butker", "KC")
        assert model.usage.target_share == 0.0
        assert model.usage.carry_share == 0.0
        assert model.games_played == 17
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_player_builder.py::TestBuildKickerModel -v 2>&1 | tail -5`
Expected: FAIL — `ImportError: cannot import name 'build_kicker_model'`

- [ ] **Step 3: Implement `build_kicker_model`**

Add to `src/fantasy_sim/data/player_builder.py` after the `_blend_dist` function:

```python
def build_kicker_model(player_id: str, name: str, team: str) -> PlayerModel:
    """Build a placeholder PlayerModel for a kicker.

    Kickers are name tags for scoring attribution — actual kicking simulation
    uses the team-level KickingModel from the pipeline.
    """
    return PlayerModel(
        player_id=player_id,
        name=name,
        position="K",
        team=team,
        usage=PlayerUsage(),
        outcomes=PlayerOutcomes(),
        games_played=17,
    )
```

- [ ] **Step 4: Run kicker tests to verify they pass**

Run: `uv run pytest tests/test_data/test_player_builder.py::TestBuildKickerModel -v`
Expected: All 3 tests PASS.

- [ ] **Step 5: Write tests for `_assemble_models`**

Add to `tests/test_data/test_player_builder.py`. Import `_assemble_models` alongside the other imports:

```python
from fantasy_sim.data.player_builder import (
    build_player_models, build_team_roster, blend_with_archetype,
    _aggregate_pbp_stats, _assemble_models, build_kicker_model,
)
```

```python
class TestAssembleModels:
    def test_player_with_pbp_gets_historical_stats(self, traded_player_pbp, traded_player_rosters):
        stats = _aggregate_pbp_stats(traded_player_pbp, training_seasons=[2024])
        models = _assemble_models(stats, traded_player_rosters)
        # IP01 has PBP data and is on KC roster
        assert "IP01" in models
        assert models["IP01"].usage.carry_share > 0

    def test_traded_player_gets_current_team(self, traded_player_pbp, traded_player_rosters):
        stats = _aggregate_pbp_stats(traded_player_pbp, training_seasons=[2024])
        models = _assemble_models(stats, traded_player_rosters)
        # JM28 has PBP on CIN but current roster says HOU
        assert "JM28" in models
        assert models["JM28"].team == "HOU"

    def test_retired_player_excluded(self, traded_player_pbp, traded_player_rosters):
        stats = _aggregate_pbp_stats(traded_player_pbp, training_seasons=[2024])
        models = _assemble_models(stats, traded_player_rosters)
        # RET99 has PBP but is NOT on any 2025 roster
        assert "RET99" not in models

    def test_rookie_gets_archetype_model(self, traded_player_pbp, traded_player_rosters):
        stats = _aggregate_pbp_stats(traded_player_pbp, training_seasons=[2024])
        models = _assemble_models(stats, traded_player_rosters)
        # ROOK1 is on HOU roster but has no PBP
        assert "ROOK1" in models
        assert models["ROOK1"].team == "HOU"
        assert models["ROOK1"].position == "WR"
        assert models["ROOK1"].usage.target_share > 0  # archetype gives nonzero

    def test_kicker_gets_placeholder_model(self, traded_player_pbp, traded_player_rosters):
        stats = _aggregate_pbp_stats(traded_player_pbp, training_seasons=[2024])
        models = _assemble_models(stats, traded_player_rosters)
        assert "KC_K" in models
        assert models["KC_K"].position == "K"
        assert "HOU_K" in models
        assert models["HOU_K"].position == "K"

    def test_ir_player_excluded(self, traded_player_pbp, traded_player_rosters):
        stats = _aggregate_pbp_stats(traded_player_pbp, training_seasons=[2024])
        models = _assemble_models(stats, traded_player_rosters)
        assert "IR01" not in models

    def test_punter_excluded(self, traded_player_pbp, traded_player_rosters):
        stats = _aggregate_pbp_stats(traded_player_pbp, training_seasons=[2024])
        models = _assemble_models(stats, traded_player_rosters)
        assert "PNT1" not in models
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_player_builder.py::TestAssembleModels -v 2>&1 | tail -10`
Expected: FAIL — `ImportError: cannot import name '_assemble_models'`

- [ ] **Step 7: Implement `_assemble_models`**

Add to `src/fantasy_sim/data/player_builder.py` after `_aggregate_pbp_stats`:

```python
FANTASY_POSITIONS = {"QB", "RB", "WR", "TE", "K"}
ACTIVE_STATUSES = {"ACT"}


def _assemble_models(
    aggregated_stats: dict,
    current_rosters: pl.DataFrame,
    rookie_blend_games: int = 0,
) -> dict[str, PlayerModel]:
    """Build PlayerModels by merging pre-computed PBP stats with current roster.

    Players on current roster get team/position from roster data.
    Stats come from aggregated PBP. Players without PBP data get
    archetype (skill positions) or placeholder (kickers) models.
    """
    from fantasy_sim.data.rookie_builder import build_rookie_model

    receiving = aggregated_stats["receiving"]
    rushing = aggregated_stats["rushing"]
    qb = aggregated_stats["qb"]
    team_pass_attempts = aggregated_stats["team_pass_attempts"]
    team_rush_attempts = aggregated_stats["team_rush_attempts"]
    team_rz_pass_attempts = aggregated_stats["team_rz_pass_attempts"]
    team_rz_rush_attempts = aggregated_stats["team_rz_rush_attempts"]
    team_air_yards = aggregated_stats["team_air_yards"]
    has_air_yards = aggregated_stats["has_air_yards"]

    # Filter roster to active, fantasy-relevant positions
    filtered = current_rosters.filter(
        pl.col("status").is_in(list(ACTIVE_STATUSES)) &
        pl.col("position").is_in(list(FANTASY_POSITIONS))
    )

    # Get latest entry per player (highest season+week)
    roster_meta = (
        filtered.sort(["season", "week"], descending=True)
        .group_by("player_id")
        .first()
        .select(["player_id", "player_name", "position", "team"])
    )

    models: dict[str, PlayerModel] = {}

    for row in roster_meta.iter_rows(named=True):
        pid = row["player_id"]
        team = row["team"]
        position = row["position"]
        name = row["player_name"]

        # Kicker — always a placeholder
        if position == "K":
            models[pid] = build_kicker_model(pid, name, team)
            continue

        # Check if player has any PBP data
        has_pbp = pid in receiving or pid in rushing or pid in qb

        if not has_pbp:
            # Skill position with no history — use rookie archetype
            models[pid] = build_rookie_model(pid, name, position, team, draft_round=7)
            continue

        # --- Build from historical PBP stats ---
        # Find historical team for share computation
        hist_team = None
        if pid in receiving:
            hist_team = receiving[pid]["team"]
        elif pid in rushing:
            hist_team = rushing[pid]["team"]
        elif pid in qb:
            hist_team = qb[pid]["team"]

        game_ids: set[str] = set()
        if pid in receiving:
            game_ids |= receiving[pid]["game_ids"]
        if pid in rushing:
            game_ids |= rushing[pid]["game_ids"]
        if pid in qb:
            game_ids |= qb[pid]["game_ids"]

        usage = PlayerUsage()

        # Target share + red zone target share
        if pid in receiving:
            rs = receiving[pid]
            team_pa = team_pass_attempts.get(hist_team, 0)
            usage.target_share = rs["targets"] / max(team_pa, 1)

            team_rz_pa = team_rz_pass_attempts.get(hist_team, 0)
            if team_rz_pa > 0:
                usage.red_zone_target_share = rs["rz_targets"] / team_rz_pa

            if has_air_yards:
                team_ay = team_air_yards.get(hist_team, 0.0)
                if team_ay > 0:
                    usage.air_yards_share = rs["air_yards"] / team_ay

        # Carry share + red zone carry share
        if pid in rushing:
            rs = rushing[pid]
            team_ra = team_rush_attempts.get(hist_team, 0)
            usage.carry_share = rs["carries"] / max(team_ra, 1)

            team_rz_ra = team_rz_rush_attempts.get(hist_team, 0)
            if team_rz_ra > 0:
                usage.red_zone_carry_share = rs["rz_carries"] / team_rz_ra

        # QB snap share and scramble rate
        if position == "QB" and pid in qb:
            qs = qb[pid]
            team_pa = team_pass_attempts.get(hist_team, 0)
            usage.snap_share = qs["attempts"] / max(team_pa, 1)

            qb_rush = rushing[pid]["carries"] if pid in rushing else 0
            qb_pass = qs["attempts"]
            total_qb_plays = qb_pass + qb_rush
            if total_qb_plays > 0:
                usage.scramble_rate = qb_rush / total_qb_plays

        # Outcomes
        outcomes = PlayerOutcomes()

        if pid in receiving:
            rs = receiving[pid]
            if rs["targets"] > 0:
                outcomes.catch_rate = rs["catches"] / rs["targets"]
            if len(rs["yards"]) >= MIN_PLAYER_PLAYS:
                outcomes.receiving_yards_dist = np.array(rs["yards"])

        if pid in rushing:
            rs = rushing[pid]
            if position == "QB":
                if len(rs["yards"]) >= 1:
                    outcomes.scramble_yards_dist = np.array(rs["yards"])
            else:
                if len(rs["yards"]) >= MIN_PLAYER_PLAYS:
                    outcomes.rushing_yards_dist = np.array(rs["yards"])

        model = PlayerModel(
            player_id=pid,
            name=name,
            position=position,
            team=team,  # Current roster team, NOT historical
            usage=usage,
            outcomes=outcomes,
            games_played=len(game_ids) if game_ids else 17,
        )

        models[pid] = model

    # Apply rookie blend if configured
    if rookie_blend_games > 0:
        for pid in list(models.keys()):
            m = models[pid]
            if m.position != "K" and m.games_played < rookie_blend_games:
                models[pid] = blend_with_archetype(m, rookie_blend_games=rookie_blend_games)

    return models
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_player_builder.py::TestAssembleModels -v`
Expected: All 7 tests PASS.

- [ ] **Step 9: Commit**

```bash
git add src/fantasy_sim/data/player_builder.py tests/test_data/test_player_builder.py
git commit -m "feat: add build_kicker_model and _assemble_models for roster-based model assembly"
```

---

### Task 4: Rewire `build_player_models` to Use New Functions

**Files:**
- Modify: `src/fantasy_sim/data/player_builder.py`
- Modify: `tests/test_data/test_player_builder.py`

Replace the internals of `build_player_models` with calls to `_aggregate_pbp_stats` and `_assemble_models`. Change its signature from `(pbp, rosters, seasons)` to `(pbp, current_rosters, training_seasons)`. Update all existing tests.

- [ ] **Step 1: Update `build_player_models` implementation**

Replace the entire `build_player_models` function body in `src/fantasy_sim/data/player_builder.py`:

```python
def build_player_models(
    pbp: pl.DataFrame,
    current_rosters: pl.DataFrame,
    training_seasons: list[int],
    rookie_blend_games: int = 0,
) -> dict[str, PlayerModel]:
    """Build PlayerModels from PBP stats and current roster.

    Stats come from historical PBP (training_seasons). Team assignment
    comes from current_rosters. Players on the roster without PBP data
    get archetype (skill positions) or placeholder (kickers) models.
    """
    aggregated = _aggregate_pbp_stats(pbp, training_seasons)
    return _assemble_models(aggregated, current_rosters, rookie_blend_games)
```

- [ ] **Step 2: Update all existing test calls**

In `tests/test_data/test_player_builder.py`, update every call from `build_player_models(pbp, rosters, seasons=[2024])` to `build_player_models(pbp, rosters, training_seasons=[2024])`. The `sample_rosters` fixture already has `status` and `position` columns, so it works as a `current_rosters` parameter.

Use find-and-replace across the file: change `seasons=[2024]` to `training_seasons=[2024]` in every `build_player_models` call.

There are 17 occurrences in the following classes: `TestBuildPlayerModels`, `TestBuildTeamRoster`, `TestRedZoneMetrics`, `TestAirYardsShare`, `TestQBScrambleData`.

- [ ] **Step 3: Run all player_builder tests**

Run: `uv run pytest tests/test_data/test_player_builder.py -v`
Expected: All tests PASS. The `sample_rosters` fixture has `status: "ACT"` and positions `QB/TE/WR/RB` — all pass the roster filter.

- [ ] **Step 4: Run full test suite to check for breakage**

Run: `uv run pytest tests/ -x -q 2>&1 | tail -10`
Expected: Some tests in `test_game_context.py` and `test_cli.py` may fail due to the changed `build_player_models` signature being called internally by `GameContextBuilder`. These are fixed in Tasks 5 and 6.

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/player_builder.py tests/test_data/test_player_builder.py
git commit -m "refactor: rewire build_player_models to use _aggregate_pbp_stats + _assemble_models"
```

---

### Task 5: Update `GameContextBuilder` for Dual-Roster Support

**Files:**
- Modify: `src/fantasy_sim/data/game_context.py`
- Modify: `tests/test_data/test_game_context.py`

Add `target_season` and `week` parameters. Split caching. Load current roster separately.

- [ ] **Step 1: Write new tests for `GameContextBuilder`**

Update `tests/test_data/test_game_context.py`:

```python
import polars as pl
import pytest
from fantasy_sim.data.game_context import GameContextBuilder
from fantasy_sim.engine.types import TeamDistributions
from fantasy_sim.models.player import TeamRoster


class TestGameContextBuilder:
    @pytest.fixture
    def builder(self, tmp_path):
        return GameContextBuilder(cache_dir=tmp_path / "cache")

    def test_build_team_distributions(self, builder, expanded_pbp, sample_rosters):
        dists = builder.build_team_distributions(
            "KC", pbp=expanded_pbp, rosters=sample_rosters, training_seasons=[2024]
        )
        assert isinstance(dists, TeamDistributions)
        assert dists.play_calling.team == "KC"
        assert dists.turnover_rates.team == "KC"

    def test_build_team_roster(self, builder, expanded_pbp, sample_rosters):
        roster = builder.build_team_roster(
            "KC", pbp=expanded_pbp, rosters=sample_rosters, training_seasons=[2024]
        )
        assert isinstance(roster, TeamRoster)
        assert roster.team == "KC"
        assert len(roster.players) > 0

    def test_build_game(self, builder, expanded_pbp, sample_rosters):
        home_dists, away_dists, home_roster, away_roster = builder.build_game(
            home_team="KC", away_team="BUF",
            pbp=expanded_pbp, rosters=sample_rosters, training_seasons=[2024],
        )
        assert home_dists.play_calling.team == "KC"
        assert away_dists.play_calling.team == "BUF"
        assert home_roster.team == "KC"
        assert away_roster.team == "BUF"

    def test_missing_team_gets_league_defaults(self, builder, expanded_pbp, sample_rosters):
        dists = builder.build_team_distributions(
            "SEA", pbp=expanded_pbp, rosters=sample_rosters, training_seasons=[2024]
        )
        assert isinstance(dists, TeamDistributions)
        probs = dists.play_calling.default
        assert 0.4 <= probs["pass"] <= 0.7

    def test_caches_pipeline_output(self, builder, expanded_pbp, sample_rosters):
        builder.build_team_distributions("KC", pbp=expanded_pbp, rosters=sample_rosters, training_seasons=[2024])
        builder.build_team_distributions("BUF", pbp=expanded_pbp, rosters=sample_rosters, training_seasons=[2024])
        assert builder._pipeline_cache is not None

    def test_traded_player_on_current_team(self, builder, traded_player_pbp, traded_player_rosters):
        """Player with PBP on old team should appear on current roster team."""
        _, _, _, away_roster = builder.build_game(
            home_team="KC", away_team="HOU",
            pbp=traded_player_pbp, rosters=traded_player_rosters,
            training_seasons=[2024],
        )
        player_ids = {p.player_id for p in away_roster.players}
        assert "JM28" in player_ids
        jm = next(p for p in away_roster.players if p.player_id == "JM28")
        assert jm.team == "HOU"

    def test_kicker_on_roster(self, builder, traded_player_pbp, traded_player_rosters):
        """Kickers should appear on team rosters."""
        home_dists, _, home_roster, _ = builder.build_game(
            home_team="KC", away_team="HOU",
            pbp=traded_player_pbp, rosters=traded_player_rosters,
            training_seasons=[2024],
        )
        player_ids = {p.player_id for p in home_roster.players}
        assert "KC_K" in player_ids

    def test_rookie_on_roster(self, builder, traded_player_pbp, traded_player_rosters):
        """Rookies with no PBP data should appear with archetype models."""
        _, _, _, away_roster = builder.build_game(
            home_team="KC", away_team="HOU",
            pbp=traded_player_pbp, rosters=traded_player_rosters,
            training_seasons=[2024],
        )
        player_ids = {p.player_id for p in away_roster.players}
        assert "ROOK1" in player_ids

    def test_retired_player_excluded(self, builder, traded_player_pbp, traded_player_rosters):
        """Players with PBP but not on current roster should not appear."""
        _, _, home_roster, away_roster = builder.build_game(
            home_team="KC", away_team="HOU",
            pbp=traded_player_pbp, rosters=traded_player_rosters,
            training_seasons=[2024],
        )
        all_ids = {p.player_id for p in home_roster.players} | {p.player_id for p in away_roster.players}
        assert "RET99" not in all_ids

    def test_week_filters_roster(self, builder, traded_player_pbp, midseason_trade_rosters):
        """When week is specified, roster should reflect that week's state."""
        # Week 3: SD14 is on HOU
        _, _, _, away_roster = builder.build_game(
            home_team="KC", away_team="HOU",
            pbp=traded_player_pbp, rosters=midseason_trade_rosters,
            training_seasons=[2024], week=3,
        )
        hou_ids = {p.player_id for p in away_roster.players}
        assert "SD14" in hou_ids

        # Week 6: SD14 traded to KC
        builder._player_models_cache = None  # Clear cache for new week
        builder._player_cache_key = None
        home_dists2, _, home_roster2, _ = builder.build_game(
            home_team="KC", away_team="HOU",
            pbp=traded_player_pbp, rosters=midseason_trade_rosters,
            training_seasons=[2024], week=6,
        )
        kc_ids = {p.player_id for p in home_roster2.players}
        assert "SD14" in kc_ids
```

- [ ] **Step 2: Run new tests to verify they fail**

Run: `uv run pytest tests/test_data/test_game_context.py -v 2>&1 | tail -15`
Expected: Failures due to old `seasons=` parameter and missing `training_seasons`/`week` support.

- [ ] **Step 3: Update `GameContextBuilder` implementation**

Replace the full content of `src/fantasy_sim/data/game_context.py`:

```python
"""Build game context (TeamDistributions + TeamRoster) from nflverse data."""

from pathlib import Path
import polars as pl
import numpy as np
from fantasy_sim.data.loader import DataLoader, DEFAULT_CACHE_DIR
from fantasy_sim.data.pipeline import DataPipeline
from fantasy_sim.data.player_builder import (
    build_player_models, build_team_roster,
    _aggregate_pbp_stats, _assemble_models,
)
from fantasy_sim.engine.types import TeamDistributions
from fantasy_sim.models.distributions import (
    PlayCallingDist, TurnoverRates,
)
from fantasy_sim.models.player import TeamRoster, PlayerModel, PlayerUsage, PlayerOutcomes
from fantasy_sim.overrides.parser import OverrideSet
from fantasy_sim.overrides.engine import apply_player_override, apply_team_override
from fantasy_sim.overrides.resolver import PlayerResolver


# League average fallbacks for teams with no data
_DEFAULT_PLAY_CALLING = PlayCallingDist(
    team="LGA", distributions={}, default={"pass": 0.57, "run": 0.43}
)
_DEFAULT_TURNOVER_RATES = TurnoverRates(
    team="LGA", int_rate=0.025, fumble_rate=0.012,
    sack_rate=0.065, sack_fumble_rate=0.10,
)


class GameContextBuilder:
    """Builds TeamDistributions + TeamRoster from real nflverse data."""

    def __init__(self, cache_dir: Path = DEFAULT_CACHE_DIR):
        self.cache_dir = Path(cache_dir)
        self.loader = DataLoader(cache_dir=self.cache_dir)
        self._pipeline_cache: dict | None = None
        self._cached_training_seasons: list[int] | None = None
        self._pbp_stats_cache: dict | None = None
        self._player_models_cache: dict | None = None
        self._player_cache_key: tuple | None = None

    def _ensure_pipeline(
        self,
        training_seasons: list[int],
        pbp: pl.DataFrame | None = None,
        rosters: pl.DataFrame | None = None,
        target_season: int | None = None,
        week: int | None = None,
    ) -> tuple[dict, dict]:
        """Build and cache pipeline output + player models.

        Pipeline output is cached on training_seasons only.
        Player models are cached on (training_seasons, target_season, week).
        """
        # Load PBP if needed
        if pbp is None:
            pbp = self.loader.load_pbp(training_seasons)

        # --- Pipeline (team distributions) — cached on training_seasons ---
        if self._pipeline_cache is None or self._cached_training_seasons != training_seasons:
            pipeline = DataPipeline(cache_dir=self.cache_dir, seasons=training_seasons)
            self._pipeline_cache = pipeline.build(pbp=pbp)
            self._cached_training_seasons = training_seasons
            self._pbp_stats_cache = None  # Invalidate PBP stats on training season change

        # --- PBP stats — cached on training_seasons ---
        if self._pbp_stats_cache is None:
            self._pbp_stats_cache = _aggregate_pbp_stats(pbp, training_seasons)

        # --- Player models — cached on (training_seasons, target_season, week) ---
        cache_key = (tuple(training_seasons), target_season, week)
        if self._player_models_cache is None or self._player_cache_key != cache_key:
            # Determine current rosters
            if rosters is not None:
                current_rosters = rosters
            else:
                roster_season = target_season or (max(training_seasons) + 1)
                current_rosters = self.loader.load_rosters([roster_season])

            # Filter to specific week if provided
            if week is not None and "week" in current_rosters.columns:
                current_rosters = current_rosters.filter(pl.col("week") <= week)

            self._player_models_cache = _assemble_models(self._pbp_stats_cache, current_rosters)
            self._player_cache_key = cache_key

        return self._pipeline_cache, self._player_models_cache

    def build_team_distributions(
        self,
        team: str,
        training_seasons: list[int] | None = None,
        pbp: pl.DataFrame | None = None,
        rosters: pl.DataFrame | None = None,
        target_season: int | None = None,
        week: int | None = None,
    ) -> TeamDistributions:
        """Build TeamDistributions for a specific team."""
        training_seasons = training_seasons or [2022, 2023, 2024]
        pipeline_output, _ = self._ensure_pipeline(
            training_seasons, pbp, rosters, target_season, week,
        )

        play_calling = pipeline_output["play_calling"].get(team, _DEFAULT_PLAY_CALLING)
        if play_calling.team != team:
            play_calling = PlayCallingDist(
                team=team, distributions={}, default=play_calling.default
            )

        turnover_rates = pipeline_output["turnover_rates"].get(team, _DEFAULT_TURNOVER_RATES)
        if turnover_rates.team != team:
            turnover_rates = TurnoverRates(
                team=team, int_rate=turnover_rates.int_rate,
                fumble_rate=turnover_rates.fumble_rate,
                sack_rate=turnover_rates.sack_rate,
                sack_fumble_rate=turnover_rates.sack_fumble_rate,
            )

        return TeamDistributions(
            play_calling=play_calling,
            play_outcomes=pipeline_output["play_outcomes"],
            turnover_rates=turnover_rates,
            kicking=pipeline_output["kicking"],
            drive_start=pipeline_output["drive_start"],
        )

    def build_team_roster(
        self,
        team: str,
        training_seasons: list[int] | None = None,
        pbp: pl.DataFrame | None = None,
        rosters: pl.DataFrame | None = None,
        target_season: int | None = None,
        week: int | None = None,
    ) -> TeamRoster:
        """Build TeamRoster for a specific team."""
        training_seasons = training_seasons or [2022, 2023, 2024]
        _, player_models = self._ensure_pipeline(
            training_seasons, pbp, rosters, target_season, week,
        )
        roster = build_team_roster(team, player_models)
        if not roster.players:
            roster = TeamRoster(team=team, players=[
                PlayerModel(
                    f"{team}_QB", "QB", "QB", team,
                    PlayerUsage(snap_share=1.0), PlayerOutcomes(),
                ),
                PlayerModel(
                    f"{team}_RB", "RB", "RB", team,
                    PlayerUsage(carry_share=1.0, target_share=0.15),
                    PlayerOutcomes(
                        rushing_yards_dist=np.array([2, 3, 4, 5, 6]),
                        catch_rate=0.65,
                        receiving_yards_dist=np.array([3, 5, 7]),
                    ),
                ),
                PlayerModel(
                    f"{team}_WR", "WR", "WR", team,
                    PlayerUsage(target_share=0.85),
                    PlayerOutcomes(
                        catch_rate=0.60,
                        receiving_yards_dist=np.array([5, 8, 12, 15, 20]),
                    ),
                ),
            ])
        return roster

    def build_game(
        self,
        home_team: str,
        away_team: str,
        training_seasons: list[int] | None = None,
        target_season: int | None = None,
        week: int | None = None,
        pbp: pl.DataFrame | None = None,
        rosters: pl.DataFrame | None = None,
    ) -> tuple[TeamDistributions, TeamDistributions, TeamRoster, TeamRoster]:
        """Build all context needed to simulate one game."""
        home_dists = self.build_team_distributions(
            home_team, training_seasons, pbp, rosters, target_season, week,
        )
        away_dists = self.build_team_distributions(
            away_team, training_seasons, pbp, rosters, target_season, week,
        )
        home_roster = self.build_team_roster(
            home_team, training_seasons, pbp, rosters, target_season, week,
        )
        away_roster = self.build_team_roster(
            away_team, training_seasons, pbp, rosters, target_season, week,
        )
        return home_dists, away_dists, home_roster, away_roster


def apply_overrides(
    overrides: OverrideSet,
    home_dists: TeamDistributions,
    away_dists: TeamDistributions,
    home_roster: TeamRoster,
    away_roster: TeamRoster,
) -> None:
    """Apply player and team overrides to distributions and rosters. Mutates in place."""
    resolver = PlayerResolver([home_roster, away_roster])

    for team, team_overrides in overrides.teams.items():
        if team == home_roster.team:
            apply_team_override(home_dists, team_overrides)
        elif team == away_roster.team:
            apply_team_override(away_dists, team_overrides)

    for player_query, player_overrides in overrides.players.items():
        try:
            player_id = resolver.resolve(player_query)
        except KeyError:
            continue

        for roster in [home_roster, away_roster]:
            if any(p.player_id == player_id for p in roster.players):
                apply_player_override(roster, player_id, player_overrides)
                break
```

- [ ] **Step 4: Run game_context tests**

Run: `uv run pytest tests/test_data/test_game_context.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest tests/ -x -q 2>&1 | tail -10`
Expected: Some CLI tests may still fail (they mock `build_game` with old `seasons=` parameter). Fixed in Task 6.

- [ ] **Step 6: Commit**

```bash
git add src/fantasy_sim/data/game_context.py tests/test_data/test_game_context.py
git commit -m "feat: add target_season/week support to GameContextBuilder with split caching"
```

---

### Task 6: Update CLI Callers

**Files:**
- Modify: `src/fantasy_sim/cli.py`
- Modify: `tests/test_cli.py`

Thread `target_season` and `week` through all real-data CLI commands.

- [ ] **Step 1: Update `week` command**

In `src/fantasy_sim/cli.py`, find the `build_game` call inside the `week` function (around line 387). Change:

```python
home_team=home, away_team=away, seasons=training_seasons,
```

to:

```python
home_team=home, away_team=away, training_seasons=training_seasons,
target_season=season, week=week_num,
```

- [ ] **Step 2: Update `season` command**

Find the `build_game` call inside the `season` function (around line 494). Change:

```python
home, away, seasons=training_seasons,
```

to:

```python
home, away, training_seasons=training_seasons,
target_season=season_year, week=wk,
```

- [ ] **Step 3: Update `game` command**

Find the `build_game` call inside the `game` function (around line 574). Change:

```python
home_team=home_team, away_team=away_team, seasons=training_seasons,
```

to:

```python
home_team=home_team, away_team=away_team, training_seasons=training_seasons,
target_season=season, week=week_num,
```

- [ ] **Step 4: Update `player` command**

Find the `build_game` call inside the `player` function (around line 715). Change:

```python
home_team=home, away_team=away, seasons=training_seasons,
```

to:

```python
home_team=home, away_team=away, training_seasons=training_seasons,
target_season=season, week=week_num,
```

- [ ] **Step 5: Update CLI tests**

In `tests/test_cli.py`, the mock `build_game` calls use `seasons=` in their assertions. These tests mock `GameContextBuilder` so the actual parameter names matter for call verification. Update the mock setup if tests verify call arguments. Most CLI tests only check `result.exit_code == 0` and mock the return value, so they should pass once the code compiles. If any test explicitly checks `build_game.call_args`, update the expected keyword arguments.

- [ ] **Step 6: Run CLI tests**

Run: `uv run pytest tests/test_cli.py -v 2>&1 | tail -15`
Expected: All tests PASS.

- [ ] **Step 7: Run full test suite**

Run: `uv run pytest tests/ -x -q 2>&1 | tail -10`
Expected: All tests PASS except possibly the backtester (fixed in Task 7).

- [ ] **Step 8: Commit**

```bash
git add src/fantasy_sim/cli.py tests/test_cli.py
git commit -m "fix: thread target_season and week through all CLI commands"
```

---

### Task 7: Update Backtester for Per-Week Rosters

**Files:**
- Modify: `src/fantasy_sim/validation/backtester.py`
- Modify: `tests/test_validation/test_backtester.py`

- [ ] **Step 1: Write test for per-week roster passing**

Add to `tests/test_validation/test_backtester.py`:

```python
from unittest.mock import patch, MagicMock


class TestBacktesterRosterHandling:
    @patch("fantasy_sim.validation.backtester.GameContextBuilder")
    @patch("fantasy_sim.validation.backtester.DataLoader")
    def test_build_game_receives_target_season_and_week(self, mock_loader_cls, mock_builder_cls):
        """Backtester should pass target_season=test_season and week=wk to build_game."""
        mock_loader = MagicMock()
        mock_loader_cls.return_value = mock_loader
        mock_loader.cache_dir = "/tmp/test"

        # Return minimal schedule with one game in week 1
        mock_loader.load_schedules.return_value = pl.DataFrame([
            {"season": 2024, "week": 1, "game_id": "2024_01_KC_BUF",
             "home_team": "KC", "away_team": "BUF"},
        ])
        mock_loader.load_player_stats.return_value = pl.DataFrame([])

        mock_builder = MagicMock()
        mock_builder_cls.return_value = mock_builder
        # Make build_game raise to stop after first call
        mock_builder.build_game.side_effect = Exception("stop")

        import polars as pl
        bt = Backtester(test_season=2024, n_sims=10)
        bt.loader = mock_loader
        bt.builder = mock_builder

        from fantasy_sim.config.loader import load_defaults, resolve_scoring
        config = load_defaults()
        scoring_config = resolve_scoring(config, "ppr")

        bt.run(scoring_config)

        # Verify build_game was called with target_season and week
        call_kwargs = mock_builder.build_game.call_args
        assert call_kwargs[1].get("training_seasons") == [2021, 2022, 2023] or call_kwargs[0][2] == [2021, 2022, 2023]
        assert call_kwargs[1].get("target_season") == 2024
        assert call_kwargs[1].get("week") == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_validation/test_backtester.py::TestBacktesterRosterHandling -v 2>&1 | tail -10`
Expected: FAIL — backtester still passes `seasons=`.

- [ ] **Step 3: Update backtester**

In `src/fantasy_sim/validation/backtester.py`, find the `build_game` call (around line 100). Change:

```python
home_dists, away_dists, home_roster, away_roster = self.builder.build_game(
    home, away, seasons=self.training_seasons,
)
```

to:

```python
home_dists, away_dists, home_roster, away_roster = self.builder.build_game(
    home, away,
    training_seasons=self.training_seasons,
    target_season=self.test_season,
    week=wk,
)
```

- [ ] **Step 4: Run backtester tests**

Run: `uv run pytest tests/test_validation/test_backtester.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/validation/backtester.py tests/test_validation/test_backtester.py
git commit -m "fix: backtester passes target_season and week for per-week roster accuracy"
```

---

### Task 8: Full Regression and Cleanup

**Files:**
- All modified files
- Modify: `CLAUDE.md` (update architecture docs)

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest tests/ -v 2>&1 | tail -20`
Expected: All tests PASS. Count should be 512 + new tests (approximately 530+).

- [ ] **Step 2: Fix any remaining failures**

If any tests fail, read the error and fix. Common issues:
- Tests that pass `seasons=` to `build_team_distributions` or `build_team_roster` need updating to `training_seasons=`
- Tests that import from `game_context` with old parameter names
- Mock assertions checking old keyword arguments

- [ ] **Step 3: Run the demo command to verify synthetic mode unaffected**

Run: `uv run fantasy-sim demo --sims 10`
Expected: Produces projections output (demo uses synthetic data, not GameContextBuilder).

- [ ] **Step 4: Update CLAUDE.md architecture section**

Update the `player_builder` description in the Architecture section to reflect the new internal structure:

Change:
```
1. **Data Layer** (`data/loader.py`, `data/preprocessor.py`, `data/pipeline.py`, `data/player_builder.py`, ...
```

Add after the player_builder mention:
- `_aggregate_pbp_stats()` computes per-player stats from historical PBP (cached, expensive)
- `_assemble_models()` merges PBP stats with current roster for team assignment (cheap, per-week)
- `build_kicker_model()` creates placeholder kicker models for scoring attribution

Update the `GameContextBuilder` description to mention `target_season` and `week` parameters.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "docs: update CLAUDE.md for roster-based player model architecture"
```

- [ ] **Step 6: Run test count verification**

Run: `uv run pytest tests/ --co -q 2>&1 | tail -3`
Expected: Shows total test count (should be > 512).

---

## Summary of Changes

| Task | What | Tests Added |
|------|------|-------------|
| 1 | Test fixtures for roster scenarios | 0 (fixtures only) |
| 2 | Extract `_aggregate_pbp_stats` | 5 |
| 3 | Add `build_kicker_model` + `_assemble_models` | 10 |
| 4 | Rewire `build_player_models` signature | 0 (existing tests updated) |
| 5 | Update `GameContextBuilder` | 5 |
| 6 | Update CLI callers | 0 (existing tests updated) |
| 7 | Update backtester | 1 |
| 8 | Regression + docs | 0 |
| **Total** | | **~21 new tests** |

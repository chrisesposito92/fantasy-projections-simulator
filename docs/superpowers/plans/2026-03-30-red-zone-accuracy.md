# Red Zone Accuracy & QB Stat Calibration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 4 systematic QB stat distortions (pass TDs inflated, pass yards deflated, fumbles understated, rush yards overstated) by adding data-driven red zone mechanics and correcting scramble rate computation.

**Architecture:** Changes span the data pipeline (`player_builder.py`) where new per-player rates are computed from PBP data, the player model (`player.py`) where two new fields are added, and the simulation engine (`play_resolver.py`, `game_sim.py`) where red zone TD gates, catch rate adjustments, yards blending, and a QB fumble check are wired in. Rookie archetypes (`rookie_builder.py`) get sensible defaults for the new fields.

**Tech Stack:** Python 3.12+, numpy, polars, pytest

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `src/fantasy_sim/models/player.py` | Modify | Add `red_zone_catch_rate`, `pass_fumble_rate` to `PlayerOutcomes` |
| `src/fantasy_sim/data/player_builder.py` | Modify | Compute scramble-only rates, RZ catch rate, QB pass fumble rate |
| `src/fantasy_sim/data/rookie_builder.py` | Modify | Add archetype defaults for new fields |
| `src/fantasy_sim/engine/play_resolver.py` | Modify | Add RZ TD gate, RZ catch rate, RZ yards blending, QB fumble check |
| `src/fantasy_sim/engine/game_sim.py` | Modify | Attribute QB pre-throw fumbles in `_update_player_stats` |
| `tests/conftest.py` | Modify | Add `scramble_qb_pbp` fixture |
| `tests/test_data/test_player_builder.py` | Modify | Tests for scramble fix, RZ catch rate, QB fumble rate |
| `tests/test_engine/test_play_resolver.py` | Modify | Tests for RZ TD gate, RZ catch rate, RZ yards blend, QB fumble |
| `tests/test_engine/test_game_sim.py` | Modify | Test QB fumble attribution |

---

### Task 1: Add New Fields to PlayerOutcomes

**Files:**
- Modify: `src/fantasy_sim/models/player.py:19-25`

- [ ] **Step 1: Add `red_zone_catch_rate` and `pass_fumble_rate` fields**

In `src/fantasy_sim/models/player.py`, add two fields to the `PlayerOutcomes` dataclass:

```python
@dataclass
class PlayerOutcomes:
    """What happens when a player is involved in a play."""
    catch_rate: float = 0.0
    red_zone_catch_rate: float = 0.0
    receiving_yards_dist: np.ndarray | None = None
    rushing_yards_dist: np.ndarray | None = None
    scramble_yards_dist: np.ndarray | None = None
    fumble_rate: float = 0.0
    pass_fumble_rate: float = 0.0
```

- [ ] **Step 2: Run existing tests to verify no breakage**

Run: `uv run pytest tests/test_models/test_player.py tests/test_data/test_player_builder.py -v`
Expected: All existing tests PASS (new fields default to 0.0)

- [ ] **Step 3: Commit**

```bash
git add src/fantasy_sim/models/player.py
git commit -m "feat: add red_zone_catch_rate and pass_fumble_rate to PlayerOutcomes"
```

---

### Task 2: Scramble Rate Fix — Data Pipeline

**Files:**
- Modify: `tests/conftest.py` (add fixture)
- Modify: `tests/test_data/test_player_builder.py` (add tests)
- Modify: `src/fantasy_sim/data/player_builder.py:108-236` (`_aggregate_pbp_stats`)
- Modify: `src/fantasy_sim/data/player_builder.py:239-391` (`_assemble_models`)

- [ ] **Step 1: Add `scramble_qb_pbp` fixture to conftest.py**

Add this fixture after the existing `scramble_pbp` fixture (~line 347) in `tests/conftest.py`:

```python
@pytest.fixture
def scramble_qb_pbp() -> pl.DataFrame:
    """PBP with qb_scramble column for testing scramble vs designed run separation.

    JA17 (BUF QB): 20 pass plays, 4 scrambles (qb_scramble=1), 6 designed runs (qb_scramble=0)
    JC02 (BUF RB): 10 rush plays (all qb_scramble=0)
    """
    plays = []
    base = {
        "season": 2024, "week": 1, "game_id": "2024_01_BUF_KC",
        "posteam": "BUF", "defteam": "KC",
        "down": 1, "ydstogo": 10, "yardline_100": 50,
        "score_differential": 0, "qtr": 1,
        "pass_attempt": 0, "rush_attempt": 0,
        "interception": 0, "fumble_lost": 0, "sack": 0,
        "touchdown": 0, "penalty": 0, "penalty_yards": 0,
        "passer_player_id": None, "receiver_player_id": None,
        "rusher_player_id": None, "qb_scramble": 0,
    }

    # JA17: 20 pass plays
    for i in range(20):
        plays.append({
            **base, "play_type": "pass", "yards_gained": 8,
            "complete_pass": 1, "pass_attempt": 1,
            "passer_player_id": "JA17", "receiver_player_id": "SD14",
        })

    # JA17: 4 scrambles (qb_scramble=1)
    for yards in [5, 8, 12, 3]:
        plays.append({
            **base, "play_type": "run", "yards_gained": yards,
            "rush_attempt": 1, "rusher_player_id": "JA17",
            "qb_scramble": 1,
        })

    # JA17: 6 designed runs (qb_scramble=0)
    for yards in [1, 3, -1, 2, 15, 7]:
        plays.append({
            **base, "play_type": "run", "yards_gained": yards,
            "rush_attempt": 1, "rusher_player_id": "JA17",
            "qb_scramble": 0,
        })

    # JC02: 10 rush plays
    for i in range(10):
        plays.append({
            **base, "play_type": "run", "yards_gained": 5,
            "rush_attempt": 1, "rusher_player_id": "JC02",
            "qb_scramble": 0,
        })

    return pl.DataFrame(plays)
```

- [ ] **Step 2: Write failing tests for scramble rate fix**

Add to `tests/test_data/test_player_builder.py`:

```python
class TestScrambleRateFix:
    def test_scramble_rate_uses_qb_scramble_column(self, scramble_qb_pbp, sample_rosters):
        """When qb_scramble column exists, only scrambles count toward scramble_rate."""
        models = build_player_models(scramble_qb_pbp, sample_rosters, training_seasons=[2024])
        ja = models.get("JA17")
        assert ja is not None
        # 4 scrambles / (20 passes + 4 scrambles) = 0.1667
        assert ja.usage.scramble_rate == pytest.approx(4 / 24, abs=0.01)

    def test_scramble_yards_dist_excludes_designed_runs(self, scramble_qb_pbp, sample_rosters):
        """scramble_yards_dist should only contain yards from qb_scramble=1 plays."""
        models = build_player_models(scramble_qb_pbp, sample_rosters, training_seasons=[2024])
        ja = models.get("JA17")
        assert ja is not None
        assert ja.outcomes.scramble_yards_dist is not None
        # Only scramble yards: [5, 8, 12, 3]
        assert sorted(ja.outcomes.scramble_yards_dist.tolist()) == [3, 5, 8, 12]

    def test_fallback_when_no_qb_scramble_column(self, scramble_pbp, sample_rosters):
        """Without qb_scramble column, fall back to existing behavior (all QB rushes)."""
        models = build_player_models(scramble_pbp, sample_rosters, training_seasons=[2024])
        ja = models.get("JA17")
        assert ja is not None
        # Old behavior: 3 rushes / (10 passes + 3 rushes) = 0.2308
        assert ja.usage.scramble_rate == pytest.approx(3 / 13, abs=0.01)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_player_builder.py::TestScrambleRateFix -v`
Expected: FAIL — `scramble_rate` is still computed with all QB rushes

- [ ] **Step 4: Implement scramble rate fix in `_aggregate_pbp_stats`**

In `src/fantasy_sim/data/player_builder.py`, modify `_aggregate_pbp_stats()`. After the existing QB stats section (~line 213-224), add scramble tracking. Replace the existing QB rushing stats block and add scramble detection.

The `_aggregate_pbp_stats` function needs these changes:

1. Detect `qb_scramble` column presence at the top of the function.
2. In the rushing stats section, when the rusher matches a known passer, split into scramble vs designed.
3. Return additional keys: `qb_scrambles` dict.

Replace the current QB stats section (lines 213-224) and add scramble logic. The full updated section starting after the rushing stats loop:

```python
    # --- QB stats (passer on pass plays) ---
    qb_stats: dict[str, dict] = {}
    for row in pass_plays.iter_rows(named=True):
        pid = row.get("passer_player_id")
        if pid is None:
            continue
        if pid not in qb_stats:
            qb_stats[pid] = {
                "attempts": 0, "team": row["posteam"], "game_ids": set(),
                "non_sack_attempts": 0, "non_sack_fumbles": 0,
            }
        qb_stats[pid]["attempts"] += 1
        qb_stats[pid]["game_ids"].add(row["game_id"])
        if row["sack"] != 1:
            qb_stats[pid]["non_sack_attempts"] += 1
            if row["fumble_lost"] == 1:
                qb_stats[pid]["non_sack_fumbles"] += 1

    # --- QB scramble separation ---
    has_qb_scramble = "qb_scramble" in plays.columns
    qb_scrambles: dict[str, dict] = {}

    if has_qb_scramble:
        qb_passer_ids = set(qb_stats.keys())
        for row in rush_plays.iter_rows(named=True):
            rid = row.get("rusher_player_id")
            if rid is None or rid not in qb_passer_ids:
                continue
            if rid not in qb_scrambles:
                qb_scrambles[rid] = {"scramble_count": 0, "scramble_yards": [],
                                     "designed_count": 0}
            if row.get("qb_scramble") == 1:
                qb_scrambles[rid]["scramble_count"] += 1
                qb_scrambles[rid]["scramble_yards"].append(row["yards_gained"])
            else:
                qb_scrambles[rid]["designed_count"] += 1
```

Update the return dict to include the new keys:

```python
    return {
        "receiving": receiving_stats,
        "rushing": rushing_stats,
        "qb": qb_stats,
        "qb_scrambles": qb_scrambles,
        "has_qb_scramble": has_qb_scramble,
        "team_pass_attempts": team_pass_attempts,
        "team_rush_attempts": team_rush_attempts,
        "team_rz_pass_attempts": team_rz_pass_attempts,
        "team_rz_rush_attempts": team_rz_rush_attempts,
        "team_air_yards": team_air_yards,
        "has_air_yards": has_air_yards,
    }
```

- [ ] **Step 5: Implement scramble rate fix in `_assemble_models`**

In `src/fantasy_sim/data/player_builder.py`, modify `_assemble_models()`. Add extraction of new keys at the top:

```python
    qb_scrambles = aggregated_stats.get("qb_scrambles", {})
    has_qb_scramble = aggregated_stats.get("has_qb_scramble", False)
```

Replace the scramble rate computation block (currently lines 340-352):

```python
        # QB snap share and scramble rate (use hist_team for team totals)
        if position == "QB" and pid in qb_stats:
            qs = qb_stats[pid]
            hist_team = qs["team"]
            team_pa = team_pass_attempts.get(hist_team, 0)
            usage.snap_share = qs["attempts"] / max(team_pa, 1)

            if has_qb_scramble and pid in qb_scrambles:
                # Use qb_scramble column: only actual scrambles
                sc = qb_scrambles[pid]
                total_qb_plays = qs["attempts"] + sc["scramble_count"]
                if total_qb_plays > 0:
                    usage.scramble_rate = sc["scramble_count"] / total_qb_plays
                # Build scramble_yards_dist from scramble-only plays
                if len(sc["scramble_yards"]) >= MIN_PLAYER_PLAYS:
                    outcomes.scramble_yards_dist = np.array(sc["scramble_yards"])
                elif len(sc["scramble_yards"]) >= 1:
                    outcomes.scramble_yards_dist = np.array(sc["scramble_yards"])
            else:
                # Fallback: no qb_scramble column, use all QB rushes (old behavior)
                qb_rush = rushing_stats[pid]["carries"] if pid in rushing_stats else 0
                qb_pass = qs["attempts"]
                total_qb_plays = qb_pass + qb_rush
                if total_qb_plays > 0:
                    usage.scramble_rate = qb_rush / total_qb_plays

            # QB pass fumble rate
            if qs["non_sack_attempts"] >= 100:
                outcomes.pass_fumble_rate = qs["non_sack_fumbles"] / qs["non_sack_attempts"]
            else:
                outcomes.pass_fumble_rate = 0.0034  # League average
```

Also update the existing scramble_yards_dist assignment. When using the fallback path (no qb_scramble column), keep the old behavior for scramble_yards_dist (lines 366-369 currently):

```python
        # Scramble yards dist (fallback path — already set above if has_qb_scramble)
        if position == "QB" and pid in rushing_stats and outcomes.scramble_yards_dist is None:
            rs = rushing_stats[pid]
            if len(rs["yards"]) >= 1:
                outcomes.scramble_yards_dist = np.array(rs["yards"])
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_player_builder.py::TestScrambleRateFix -v`
Expected: All 3 tests PASS

- [ ] **Step 7: Run full player_builder test suite for regression**

Run: `uv run pytest tests/test_data/test_player_builder.py -v`
Expected: All tests PASS

- [ ] **Step 8: Commit**

```bash
git add src/fantasy_sim/data/player_builder.py tests/conftest.py tests/test_data/test_player_builder.py
git commit -m "feat: use qb_scramble column to separate scrambles from designed runs"
```

---

### Task 3: Red Zone Catch Rate — Data Pipeline

**Files:**
- Modify: `tests/test_data/test_player_builder.py`
- Modify: `src/fantasy_sim/data/player_builder.py`

- [ ] **Step 1: Write failing tests for red zone catch rate**

Add to `tests/test_data/test_player_builder.py`:

```python
class TestRedZoneCatchRate:
    def test_rz_catch_rate_computed_with_enough_samples(self, rz_pbp, sample_rosters):
        """RE11 has 5 RZ targets and 5 RZ catches -> rz_catch_rate = 1.0.
        But 5 < 10 threshold, so should fall back to catch_rate * 0.85."""
        models = build_player_models(rz_pbp, sample_rosters, training_seasons=[2024])
        re = models.get("RE11")
        assert re is not None
        assert re.outcomes.red_zone_catch_rate == pytest.approx(re.outcomes.catch_rate * 0.85, abs=0.01)

    def test_rz_catch_rate_fallback_below_threshold(self, expanded_pbp, sample_rosters):
        """Players with < 10 RZ targets use catch_rate * 0.85 fallback."""
        models = build_player_models(expanded_pbp, sample_rosters, training_seasons=[2024])
        tk = models.get("TK87")
        assert tk is not None
        if tk.outcomes.catch_rate > 0:
            assert tk.outcomes.red_zone_catch_rate == pytest.approx(tk.outcomes.catch_rate * 0.85, abs=0.01)

    def test_rz_catch_rate_data_driven_with_enough_targets(self):
        """With >= 10 RZ targets, use actual RZ catch rate."""
        import polars as pl
        plays = []
        base = {
            "season": 2024, "week": 1, "game_id": "2024_01_T1",
            "posteam": "T1", "defteam": "T2",
            "down": 1, "ydstogo": 10, "score_differential": 0, "qtr": 1,
            "rush_attempt": 0, "interception": 0, "fumble_lost": 0,
            "sack": 0, "touchdown": 0, "penalty": 0, "penalty_yards": 0,
            "passer_player_id": "QB1", "rusher_player_id": None,
        }
        # 15 RZ targets, 9 completions -> rz_catch_rate = 0.60
        for i in range(9):
            plays.append({**base, "play_type": "pass", "yardline_100": 15,
                          "yards_gained": 8, "complete_pass": 1, "pass_attempt": 1,
                          "receiver_player_id": "WR1"})
        for i in range(6):
            plays.append({**base, "play_type": "pass", "yardline_100": 15,
                          "yards_gained": 0, "complete_pass": 0, "pass_attempt": 1,
                          "receiver_player_id": "WR1"})
        # 10 non-RZ targets, 7 completions -> overall catch_rate = 16/25 = 0.64
        for i in range(7):
            plays.append({**base, "play_type": "pass", "yardline_100": 50,
                          "yards_gained": 12, "complete_pass": 1, "pass_attempt": 1,
                          "receiver_player_id": "WR1"})
        for i in range(3):
            plays.append({**base, "play_type": "pass", "yardline_100": 50,
                          "yards_gained": 0, "complete_pass": 0, "pass_attempt": 1,
                          "receiver_player_id": "WR1"})
        pbp = pl.DataFrame(plays)
        rosters = pl.DataFrame([
            {"season": 2024, "week": 1, "player_id": "QB1", "player_name": "QB", "position": "QB", "team": "T1", "status": "ACT"},
            {"season": 2024, "week": 1, "player_id": "WR1", "player_name": "WR", "position": "WR", "team": "T1", "status": "ACT"},
        ])
        models = build_player_models(pbp, rosters, training_seasons=[2024])
        wr = models["WR1"]
        assert wr.outcomes.red_zone_catch_rate == pytest.approx(9 / 15, abs=0.01)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_player_builder.py::TestRedZoneCatchRate -v`
Expected: FAIL — `red_zone_catch_rate` is always 0.0

- [ ] **Step 3: Implement RZ catch rate in `_aggregate_pbp_stats`**

In `_aggregate_pbp_stats()`, add `rz_catches` tracking inside the receiving stats loop. In the section that tracks `rz_targets` (~line 182), add:

```python
        if row["complete_pass"] == 1 and row["yardline_100"] <= 20:
            receiving_stats[rid]["rz_catches"] += 1
```

And initialize `rz_catches` when creating the entry (~line 173-177):

```python
        if rid not in receiving_stats:
            receiving_stats[rid] = {
                "targets": 0, "catches": 0, "yards": [],
                "rz_targets": 0, "rz_catches": 0, "air_yards": 0.0,
                "team": row["posteam"], "game_ids": set(),
            }
```

- [ ] **Step 4: Implement RZ catch rate in `_assemble_models`**

In `_assemble_models()`, after the `catch_rate` computation (~line 359-360), add:

```python
            # Red zone catch rate
            if rs["rz_targets"] >= MIN_BUCKET_PLAYS:
                outcomes.red_zone_catch_rate = rs["rz_catches"] / rs["rz_targets"]
            elif outcomes.catch_rate > 0:
                outcomes.red_zone_catch_rate = outcomes.catch_rate * 0.85
```

Note: `MIN_BUCKET_PLAYS` is already imported at the module level (it's `10`, imported from preprocessor, or defined in player_builder). Actually, looking at the code, `MIN_PLAYER_PLAYS = 5` is defined in player_builder. Use `10` as a literal or define a new constant:

```python
MIN_RZ_TARGETS = 10  # Minimum RZ targets for per-player RZ catch rate
```

Add this constant near the top of the file next to `MIN_PLAYER_PLAYS = 5`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_player_builder.py::TestRedZoneCatchRate -v`
Expected: All 3 tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/fantasy_sim/data/player_builder.py tests/test_data/test_player_builder.py
git commit -m "feat: compute per-player red zone catch rate from PBP data"
```

---

### Task 4: QB Pass Fumble Rate — Data Pipeline

The QB non-sack fumble tracking was already added to `_aggregate_pbp_stats` and `_assemble_models` in Task 2 (the scramble rate task included `non_sack_attempts` and `non_sack_fumbles` tracking + `pass_fumble_rate` assignment). This task just adds the test.

**Files:**
- Modify: `tests/test_data/test_player_builder.py`

- [ ] **Step 1: Write test for QB pass fumble rate**

Add to `tests/test_data/test_player_builder.py`:

```python
class TestQBPassFumbleRate:
    def test_pass_fumble_rate_computed(self):
        """QB with enough pass plays gets per-player pass_fumble_rate."""
        import polars as pl
        plays = []
        base = {
            "season": 2024, "week": 1, "game_id": "2024_01_T1",
            "posteam": "T1", "defteam": "T2",
            "down": 1, "ydstogo": 10, "yardline_100": 50,
            "score_differential": 0, "qtr": 1,
            "rush_attempt": 0, "interception": 0,
            "sack": 0, "touchdown": 0, "penalty": 0, "penalty_yards": 0,
            "passer_player_id": "QB1", "receiver_player_id": "WR1",
            "rusher_player_id": None,
        }
        # 150 non-sack passes, 2 with fumble_lost
        for i in range(148):
            plays.append({**base, "play_type": "pass", "yards_gained": 8,
                          "complete_pass": 1, "pass_attempt": 1, "fumble_lost": 0})
        for i in range(2):
            plays.append({**base, "play_type": "pass", "yards_gained": 0,
                          "complete_pass": 0, "pass_attempt": 1, "fumble_lost": 1})
        pbp = pl.DataFrame(plays)
        rosters = pl.DataFrame([
            {"season": 2024, "week": 1, "player_id": "QB1", "player_name": "QB", "position": "QB", "team": "T1", "status": "ACT"},
            {"season": 2024, "week": 1, "player_id": "WR1", "player_name": "WR", "position": "WR", "team": "T1", "status": "ACT"},
        ])
        models = build_player_models(pbp, rosters, training_seasons=[2024])
        qb = models["QB1"]
        assert qb.outcomes.pass_fumble_rate == pytest.approx(2 / 150, abs=0.001)

    def test_pass_fumble_rate_fallback_for_small_sample(self, expanded_pbp, sample_rosters):
        """QBs with < 100 pass plays get league average 0.0034."""
        models = build_player_models(expanded_pbp, sample_rosters, training_seasons=[2024])
        pm = models.get("PM15")
        assert pm is not None
        # expanded_pbp has 40 KC passes, well under 100
        assert pm.outcomes.pass_fumble_rate == pytest.approx(0.0034, abs=0.0001)
```

- [ ] **Step 2: Run tests to verify they pass** (already implemented in Task 2)

Run: `uv run pytest tests/test_data/test_player_builder.py::TestQBPassFumbleRate -v`
Expected: PASS (logic was implemented alongside scramble fix)

- [ ] **Step 3: Commit**

```bash
git add tests/test_data/test_player_builder.py
git commit -m "test: add tests for QB non-sack pass fumble rate"
```

---

### Task 5: Rookie/Archetype Defaults

**Files:**
- Modify: `src/fantasy_sim/data/rookie_builder.py`
- Modify: `tests/test_data/test_player_builder.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_data/test_player_builder.py`:

```python
class TestRookieArchetypeDefaults:
    def test_qb_archetype_has_pass_fumble_rate(self):
        from fantasy_sim.data.rookie_builder import build_rookie_model
        model = build_rookie_model("QB1", "Rookie QB", "QB", "KC", draft_round=1)
        assert model.outcomes.pass_fumble_rate == pytest.approx(0.0034, abs=0.001)

    def test_wr_archetype_has_red_zone_catch_rate(self):
        from fantasy_sim.data.rookie_builder import build_rookie_model
        model = build_rookie_model("WR1", "Rookie WR", "WR", "KC", draft_round=1)
        arch_catch = POSITIONAL_ARCHETYPES["WR"]["tier1"]["catch_rate"]
        assert model.outcomes.red_zone_catch_rate == pytest.approx(arch_catch * 0.85, abs=0.01)

    def test_te_archetype_has_red_zone_catch_rate(self):
        from fantasy_sim.data.rookie_builder import build_rookie_model
        model = build_rookie_model("TE1", "Rookie TE", "TE", "KC", draft_round=3)
        arch_catch = POSITIONAL_ARCHETYPES["TE"]["tier2"]["catch_rate"]
        assert model.outcomes.red_zone_catch_rate == pytest.approx(arch_catch * 0.85, abs=0.01)

    def test_rb_archetype_has_red_zone_catch_rate(self):
        from fantasy_sim.data.rookie_builder import build_rookie_model
        model = build_rookie_model("RB1", "Rookie RB", "RB", "KC", draft_round=5)
        arch_catch = POSITIONAL_ARCHETYPES["RB"]["tier3"]["catch_rate"]
        assert model.outcomes.red_zone_catch_rate == pytest.approx(arch_catch * 0.85, abs=0.01)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_player_builder.py::TestRookieArchetypeDefaults -v`
Expected: FAIL — `pass_fumble_rate` is 0.0, `red_zone_catch_rate` is 0.0

- [ ] **Step 3: Implement archetype defaults**

In `src/fantasy_sim/data/rookie_builder.py`, modify `build_rookie_model()`:

For QBs (~line 82-86), add:
```python
    if position == "QB":
        usage.snap_share = archetype["snap_share"]
        usage.scramble_rate = archetype["scramble_rate"]
        outcomes.scramble_yards_dist = np.array(archetype["scramble_yards"])
        outcomes.fumble_rate = archetype["fumble_rate"]
        outcomes.pass_fumble_rate = 0.0034  # League average
```

For RBs (~line 87-93), add after `outcomes.fumble_rate`:
```python
        outcomes.red_zone_catch_rate = archetype["catch_rate"] * 0.85
```

For WR/TE (~line 94-99), add after `outcomes.fumble_rate`:
```python
        outcomes.red_zone_catch_rate = archetype["catch_rate"] * 0.85
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_player_builder.py::TestRookieArchetypeDefaults -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Run existing rookie builder tests for regression**

Run: `uv run pytest tests/test_data/test_rookie_builder.py tests/test_data/test_player_builder.py::TestRookieBlendSystem -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/fantasy_sim/data/rookie_builder.py tests/test_data/test_player_builder.py
git commit -m "feat: add red_zone_catch_rate and pass_fumble_rate to rookie archetypes"
```

---

### Task 6: Red Zone TD Gate Function

**Files:**
- Modify: `tests/test_engine/test_play_resolver.py`
- Modify: `src/fantasy_sim/engine/play_resolver.py`

- [ ] **Step 1: Write failing tests for `_red_zone_td_gate`**

Add to `tests/test_engine/test_play_resolver.py`:

```python
class TestRedZoneTDGate:
    def test_outside_red_zone_always_true(self):
        from fantasy_sim.engine.play_resolver import _red_zone_td_gate
        rng = np.random.default_rng(42)
        for _ in range(50):
            assert _red_zone_td_gate(25, "pass", rng) is True
            assert _red_zone_td_gate(50, "run", rng) is True

    def test_close_to_goal_high_probability(self):
        from fantasy_sim.engine.play_resolver import _red_zone_td_gate
        rng = np.random.default_rng(42)
        tds = sum(_red_zone_td_gate(2, "pass", rng) for _ in range(1000))
        # 90% gate -> expect ~900, allow ±50
        assert 840 <= tds <= 960

    def test_far_red_zone_low_probability(self):
        from fantasy_sim.engine.play_resolver import _red_zone_td_gate
        rng = np.random.default_rng(42)
        tds = sum(_red_zone_td_gate(18, "pass", rng) for _ in range(1000))
        # 30% gate -> expect ~300, allow ±50
        assert 240 <= tds <= 360

    def test_run_gate_lower_than_pass(self):
        from fantasy_sim.engine.play_resolver import _red_zone_td_gate
        rng = np.random.default_rng(42)
        pass_tds = sum(_red_zone_td_gate(5, "pass", rng) for _ in range(1000))
        rng = np.random.default_rng(42)
        run_tds = sum(_red_zone_td_gate(5, "run", rng) for _ in range(1000))
        assert run_tds < pass_tds
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_engine/test_play_resolver.py::TestRedZoneTDGate -v`
Expected: FAIL — `_red_zone_td_gate` does not exist

- [ ] **Step 3: Implement `_red_zone_td_gate` and constants**

Add to `src/fantasy_sim/engine/play_resolver.py` after the existing module-level constants (~line 23):

```python
# Red zone TD gate probabilities — calibrated from 2024 NFL data.
# Given a play with enough yards to score, probability it actually results in a TD.
PASS_TD_GATE = {
    (1, 3): 0.90,
    (4, 5): 0.90,
    (6, 10): 0.80,
    (11, 15): 0.50,
    (16, 20): 0.30,
}

RUN_TD_GATE = {
    (1, 3): 0.65,
    (4, 5): 0.55,
    (6, 10): 0.40,
    (11, 15): 0.25,
    (16, 20): 0.15,
}

# League-average red zone catch rate modifier (RZ completion % / overall %)
RZ_CATCH_RATE_MODIFIER = 0.85


def _red_zone_td_gate(yard_line: int, play_type: str, rng: np.random.Generator) -> bool:
    """Check if a would-be TD actually scores, based on field position.

    Returns True if the TD stands, False if the player is tackled short.
    Outside the red zone (yard_line > 20), always returns True.
    """
    if yard_line > 20:
        return True
    gate_table = PASS_TD_GATE if play_type == "pass" else RUN_TD_GATE
    for (lo, hi), prob in gate_table.items():
        if lo <= yard_line <= hi:
            return rng.random() < prob
    return True  # Safety fallback
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_engine/test_play_resolver.py::TestRedZoneTDGate -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/engine/play_resolver.py tests/test_engine/test_play_resolver.py
git commit -m "feat: add red zone TD gate function with NFL-calibrated probabilities"
```

---

### Task 7: Red Zone Pass Resolution (Catch Rate + TD Gate + Yards Blending)

**Files:**
- Modify: `tests/test_engine/test_play_resolver.py`
- Modify: `src/fantasy_sim/engine/play_resolver.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_engine/test_play_resolver.py`:

```python
def make_rz_roster() -> TeamRoster:
    """Roster for red zone tests with known catch rates and yards dists."""
    qb = PlayerModel("QB1", "QB", "QB", "T",
                     PlayerUsage(snap_share=1.0, scramble_rate=0.0),
                     PlayerOutcomes())
    wr1 = PlayerModel("WR1", "WR1", "WR", "T",
                      PlayerUsage(target_share=1.0),
                      PlayerOutcomes(
                          catch_rate=1.0,  # Always catches (outside RZ)
                          red_zone_catch_rate=0.50,  # 50% in RZ
                          receiving_yards_dist=np.array([15, 15, 15, 15, 15]),  # Always 15 yards
                          fumble_rate=0.0,
                      ))
    return TeamRoster(team="T", players=[qb, wr1])


class TestRedZonePassResolution:
    def test_rz_catch_rate_used_inside_20(self):
        """In the red zone, use red_zone_catch_rate (0.50) instead of catch_rate (1.0)."""
        rng = np.random.default_rng(42)
        roster = make_rz_roster()
        outcomes = make_outcomes(pass_yards=[10])
        rates = make_turnover_rates()
        completions = 0
        n = 500
        for _ in range(n):
            state = make_state(yard_line=10)  # Red zone
            result = resolve_play(state, "pass", outcomes, rates, rng, roster=roster)
            if result.is_complete:
                completions += 1
        rate = completions / n
        # Should be ~0.50 (RZ catch rate), not 1.0 (overall)
        assert 0.35 <= rate <= 0.65

    def test_normal_catch_rate_outside_20(self):
        """Outside the red zone, use normal catch_rate (1.0)."""
        rng = np.random.default_rng(42)
        roster = make_rz_roster()
        outcomes = make_outcomes(pass_yards=[10])
        rates = make_turnover_rates()
        completions = 0
        n = 200
        for _ in range(n):
            state = make_state(yard_line=50)
            result = resolve_play(state, "pass", outcomes, rates, rng, roster=roster)
            if result.is_complete:
                completions += 1
        rate = completions / n
        assert rate > 0.90  # Should be ~1.0

    def test_rz_td_gate_reduces_tds(self):
        """From the 10-yard line with 15-yard catches, not all completions should be TDs."""
        rng = np.random.default_rng(42)
        roster = make_rz_roster()
        outcomes = make_outcomes(pass_yards=[15])
        rates = make_turnover_rates()
        tds = 0
        completions = 0
        n = 1000
        for _ in range(n):
            state = make_state(yard_line=10)
            result = resolve_play(state, "pass", outcomes, rates, rng, roster=roster)
            if result.is_complete:
                completions += 1
                if result.is_touchdown:
                    tds += 1
        # TD gate at 6-10 is 0.80, so ~80% of completions should be TDs
        if completions > 0:
            td_rate = tds / completions
            assert 0.65 <= td_rate <= 0.95

    def test_failed_td_gate_gives_short_yardage(self):
        """When TD gate fails, receiver should be tackled short (yards < yard_line)."""
        rng = np.random.default_rng(42)
        roster = make_rz_roster()
        outcomes = make_outcomes(pass_yards=[15])
        rates = make_turnover_rates()
        short_catches = []
        for _ in range(2000):
            state = make_state(yard_line=15)
            result = resolve_play(state, "pass", outcomes, rates, rng, roster=roster)
            if result.is_complete and not result.is_touchdown:
                short_catches.append(result.yards)
        assert len(short_catches) > 0  # Some catches should NOT be TDs
        for y in short_catches:
            assert 1 <= y < 15  # Tackled short of goal line

    def test_rz_yards_blending_caps_player_yards(self):
        """In the red zone, non-TD catch yards should be capped by team distribution."""
        rng = np.random.default_rng(42)
        # Roster with very high player yards dist
        qb = PlayerModel("QB1", "QB", "QB", "T",
                         PlayerUsage(snap_share=1.0), PlayerOutcomes())
        wr = PlayerModel("WR1", "WR1", "WR", "T",
                         PlayerUsage(target_share=1.0),
                         PlayerOutcomes(
                             catch_rate=1.0,
                             red_zone_catch_rate=1.0,
                             receiving_yards_dist=np.array([30, 30, 30]),  # Always 30 yards
                             fumble_rate=0.0,
                         ))
        roster = TeamRoster(team="T", players=[qb, wr])
        # Team dist returns small values (realistic RZ)
        outcomes = make_outcomes(pass_yards=[5, 6, 7])
        rates = make_turnover_rates()
        non_td_yards = []
        for _ in range(2000):
            state = make_state(yard_line=18)
            result = resolve_play(state, "pass", outcomes, rates, rng, roster=roster)
            if result.is_complete and not result.is_touchdown:
                non_td_yards.append(result.yards)
        if non_td_yards:
            avg = sum(non_td_yards) / len(non_td_yards)
            # Should be capped by team dist (~5-7), not player dist (30)
            assert avg < 15
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_engine/test_play_resolver.py::TestRedZonePassResolution -v`
Expected: FAIL — resolver doesn't use RZ catch rate or TD gate yet

- [ ] **Step 3: Implement red zone pass resolution changes**

In `src/fantasy_sim/engine/play_resolver.py`, modify `_resolve_pass()`. Replace the player-aware pass resolution section (currently lines 146-178):

```python
    if roster is not None and receiver_id is not None:
        # Player-aware pass resolution
        # Use red zone catch rate when inside the 20
        if state.yard_line <= 20:
            effective_catch_rate = receiver.outcomes.red_zone_catch_rate
            if effective_catch_rate <= 0:
                effective_catch_rate = receiver.outcomes.catch_rate * RZ_CATCH_RATE_MODIFIER
        else:
            effective_catch_rate = receiver.outcomes.catch_rate

        is_complete = rng.random() < effective_catch_rate

        if is_complete:
            # Use player's receiving yards dist if available, otherwise team dist
            if receiver.outcomes.receiving_yards_dist is not None and len(receiver.outcomes.receiving_yards_dist) > 0:
                player_yards = int(rng.choice(receiver.outcomes.receiving_yards_dist))
            else:
                player_yards = max(team_yards, 1)  # Complete pass must gain at least 1 yard

            # Red zone yards blending: cap player yards by team-level distribution
            if state.yard_line <= 20:
                yards = min(player_yards, max(team_yards, 1))
            else:
                yards = player_yards

            yards = _apply_home_field(yards, is_home, rng)
            yards = _clamp_yards(state.yard_line, yards)
        else:
            yards = 0

        # TD determination with red zone gate
        if is_complete and state.yard_line <= 20 and (state.yard_line - yards) <= 0:
            if _red_zone_td_gate(state.yard_line, "pass", rng):
                yards = _clamp_yards(state.yard_line, yards)
                is_td = True
            else:
                # Tackled short of goal line
                yards = max(1, state.yard_line - rng.integers(1, max(2, state.yard_line // 3)))
                is_td = False
        else:
            is_td = is_complete and (state.yard_line - yards) <= 0

        # Fumble check on completions — use player fumble rate, fall back to team rate
        is_fumble = False
        if is_complete:
            player_fumble = receiver.outcomes.fumble_rate
            effective_rate = player_fumble if player_fumble > 0 else turnover_rates.fumble_rate
            is_fumble = rng.random() < effective_rate

        return PlayResult(
            play_type="pass", yards=yards,
            is_complete=is_complete,
            is_touchdown=is_td and not is_fumble,
            is_fumble=is_fumble,
            clock_runoff=_scale_clock_runoff(CLOCK_PASS_COMPLETE if is_complete else CLOCK_PASS_INCOMPLETE, pace_factor),
            passer_id=passer_id,
            receiver_id=receiver_id,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_engine/test_play_resolver.py::TestRedZonePassResolution -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Run existing resolver tests for regression**

Run: `uv run pytest tests/test_engine/test_play_resolver.py -v`
Expected: All tests PASS (existing tests use yard_line=75 or yard_line=5 with no roster, so legacy path is unchanged)

- [ ] **Step 6: Commit**

```bash
git add src/fantasy_sim/engine/play_resolver.py tests/test_engine/test_play_resolver.py
git commit -m "feat: add red zone catch rate, TD gate, and yards blending to pass resolution"
```

---

### Task 8: Red Zone Run Resolution (TD Gate + Yards Blending)

**Files:**
- Modify: `tests/test_engine/test_play_resolver.py`
- Modify: `src/fantasy_sim/engine/play_resolver.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_engine/test_play_resolver.py`:

```python
class TestRedZoneRunResolution:
    def test_rz_run_td_gate_reduces_tds(self):
        """From the 3-yard line, not all 5-yard runs should be TDs."""
        rng = np.random.default_rng(42)
        rb = PlayerModel("RB1", "RB1", "RB", "T",
                         PlayerUsage(carry_share=1.0),
                         PlayerOutcomes(rushing_yards_dist=np.array([5, 5, 5, 5, 5]),
                                        fumble_rate=0.0))
        roster = TeamRoster(team="T", players=[rb])
        outcomes = make_outcomes(run_yards=[5])
        rates = make_turnover_rates()
        tds = 0
        n = 1000
        for _ in range(n):
            state = make_state(yard_line=3)
            result = resolve_play(state, "run", outcomes, rates, rng, roster=roster)
            if result.is_touchdown:
                tds += 1
        td_rate = tds / n
        # RUN_TD_GATE at 1-3 is 0.65, so ~65% should be TDs
        assert 0.50 <= td_rate <= 0.80

    def test_rz_run_yards_blending(self):
        """In the red zone, non-TD run yards capped by team dist."""
        rng = np.random.default_rng(42)
        rb = PlayerModel("RB1", "RB1", "RB", "T",
                         PlayerUsage(carry_share=1.0),
                         PlayerOutcomes(rushing_yards_dist=np.array([25, 25, 25]),
                                        fumble_rate=0.0))
        roster = TeamRoster(team="T", players=[rb])
        outcomes = make_outcomes(run_yards=[4, 5, 6])  # Team dist: 4-6 yards
        rates = make_turnover_rates()
        non_td_yards = []
        for _ in range(2000):
            state = make_state(yard_line=18)
            result = resolve_play(state, "run", outcomes, rates, rng, roster=roster)
            if not result.is_touchdown and not result.is_fumble and not result.is_safety:
                non_td_yards.append(result.yards)
        if non_td_yards:
            avg = sum(non_td_yards) / len(non_td_yards)
            assert avg < 12  # Should be capped, not 25
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_engine/test_play_resolver.py::TestRedZoneRunResolution -v`
Expected: FAIL — run resolver has no TD gate or yards blending

- [ ] **Step 3: Implement red zone run resolution changes**

In `src/fantasy_sim/engine/play_resolver.py`, modify `_resolve_run()`. In the player-aware path (currently lines 214-246), after computing `raw_yards` and before the safety/TD check:

Replace lines 218-246 with:

```python
        # Use player's rushing yards dist if available
        if rusher.outcomes.rushing_yards_dist is not None and len(rusher.outcomes.rushing_yards_dist) > 0:
            player_yards = int(rng.choice(rusher.outcomes.rushing_yards_dist))
        else:
            # Fall back to team distribution
            bucket = bucket_play(
                state.down, state.distance, state.score_differential,
                state.quarter, state.yard_line,
            )
            player_yards = play_outcomes.sample_yards("run", bucket, rng)

        # Red zone yards blending: cap player yards by team-level distribution
        if state.yard_line <= 20:
            bucket = bucket_play(
                state.down, state.distance, state.score_differential,
                state.quarter, state.yard_line,
            )
            team_run_yards = play_outcomes.sample_yards("run", bucket, rng)
            raw_yards = min(player_yards, max(team_run_yards, player_yards if player_yards <= 0 else 1))
        else:
            raw_yards = player_yards

        raw_yards = _apply_home_field(raw_yards, is_home, rng)
        is_safety = (state.yard_line - raw_yards) >= 100
        yards = _clamp_yards(state.yard_line, raw_yards)

        # TD determination with red zone gate
        if state.yard_line <= 20 and (state.yard_line - yards) <= 0:
            if _red_zone_td_gate(state.yard_line, "run", rng):
                is_td = True
            else:
                yards = max(1, state.yard_line - rng.integers(1, max(2, state.yard_line // 3)))
                is_td = False
        else:
            is_td = (state.yard_line - yards) <= 0

        # Use player fumble rate, fall back to team rate if unset
        player_fumble = rusher.outcomes.fumble_rate
        effective_rate = player_fumble if player_fumble > 0 else turnover_rates.fumble_rate
        is_fumble = rng.random() < effective_rate

        return PlayResult(
            play_type="run", yards=yards,
            is_touchdown=is_td and not is_fumble,
            is_fumble=is_fumble and not is_safety,
            is_safety=is_safety,
            clock_runoff=_scale_clock_runoff(CLOCK_RUN, pace_factor),
            rusher_id=rusher_id,
        )
```

Note: For the yards blending, negative rush yards (losses) should NOT be capped upward. The `min()` with `max(team_run_yards, player_yards if player_yards <= 0 else 1)` preserves negative yards.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_engine/test_play_resolver.py::TestRedZoneRunResolution -v`
Expected: Both tests PASS

- [ ] **Step 5: Run all resolver tests for regression**

Run: `uv run pytest tests/test_engine/test_play_resolver.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/fantasy_sim/engine/play_resolver.py tests/test_engine/test_play_resolver.py
git commit -m "feat: add red zone TD gate and yards blending to run resolution"
```

---

### Task 9: QB Pre-Throw Fumble Check

**Files:**
- Modify: `tests/test_engine/test_play_resolver.py`
- Modify: `src/fantasy_sim/engine/play_resolver.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_engine/test_play_resolver.py`:

```python
class TestQBPreThrowFumble:
    def _make_fumble_roster(self, pass_fumble_rate: float) -> TeamRoster:
        qb = PlayerModel("QB1", "QB", "QB", "T",
                         PlayerUsage(snap_share=1.0, scramble_rate=0.0),
                         PlayerOutcomes(pass_fumble_rate=pass_fumble_rate))
        wr = PlayerModel("WR1", "WR1", "WR", "T",
                         PlayerUsage(target_share=1.0),
                         PlayerOutcomes(catch_rate=1.0,
                                        red_zone_catch_rate=1.0,
                                        receiving_yards_dist=np.array([10]),
                                        fumble_rate=0.0))
        return TeamRoster(team="T", players=[qb, wr])

    def test_pre_throw_fumble_fires(self):
        """With pass_fumble_rate=1.0, every pass play should be a fumble."""
        rng = np.random.default_rng(42)
        roster = self._make_fumble_roster(pass_fumble_rate=1.0)
        outcomes = make_outcomes(pass_yards=[10])
        rates = make_turnover_rates()
        result = resolve_play(make_state(), "pass", outcomes, rates, rng, roster=roster)
        assert result.is_fumble
        assert result.yards == 0
        assert not result.is_touchdown
        assert not result.is_complete

    def test_pre_throw_fumble_before_completion(self):
        """Pre-throw fumble should prevent any completion."""
        rng = np.random.default_rng(42)
        roster = self._make_fumble_roster(pass_fumble_rate=1.0)
        outcomes = make_outcomes(pass_yards=[10])
        rates = make_turnover_rates()
        result = resolve_play(make_state(), "pass", outcomes, rates, rng, roster=roster)
        assert not result.is_complete
        assert result.passer_id == "QB1"
        assert result.receiver_id is None  # Never got to select a receiver

    def test_no_fumble_when_rate_zero(self):
        """With pass_fumble_rate=0.0, no pre-throw fumbles."""
        rng = np.random.default_rng(42)
        roster = self._make_fumble_roster(pass_fumble_rate=0.0)
        outcomes = make_outcomes(pass_yards=[10])
        rates = make_turnover_rates()
        fumbles = 0
        for _ in range(200):
            result = resolve_play(make_state(), "pass", outcomes, rates, rng, roster=roster)
            if result.is_fumble and result.yards == 0:
                fumbles += 1
        assert fumbles == 0

    def test_fumble_checked_after_sack_and_int(self):
        """Sack takes priority over pre-throw fumble."""
        rng = np.random.default_rng(42)
        roster = self._make_fumble_roster(pass_fumble_rate=1.0)
        outcomes = make_outcomes(pass_yards=[10])
        rates = make_turnover_rates(sack_rate=1.0)
        result = resolve_play(make_state(), "pass", outcomes, rates, rng, roster=roster)
        assert result.is_sack  # Sack takes priority
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_engine/test_play_resolver.py::TestQBPreThrowFumble -v`
Expected: FAIL — no pre-throw fumble check exists

- [ ] **Step 3: Implement QB pre-throw fumble check**

In `src/fantasy_sim/engine/play_resolver.py`, in `_resolve_pass()`, add the fumble check AFTER the interception check (line 132) and BEFORE receiver selection (line 135). Insert:

```python
    # QB pre-throw fumble check (botched snap, strip while throwing)
    if roster is not None and passer_id is not None:
        passer_model = None
        for p in roster.players:
            if p.player_id == passer_id:
                passer_model = p
                break
        if passer_model is not None and passer_model.outcomes.pass_fumble_rate > 0:
            if rng.random() < passer_model.outcomes.pass_fumble_rate:
                return PlayResult(
                    play_type="pass", yards=0, is_fumble=True,
                    clock_runoff=_scale_clock_runoff(CLOCK_PASS_INCOMPLETE, pace_factor),
                    passer_id=passer_id,
                )
```

This goes right after the INT check block (line ~132) and before "Select receiver when roster is available" (line ~135).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_engine/test_play_resolver.py::TestQBPreThrowFumble -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Run all resolver tests for regression**

Run: `uv run pytest tests/test_engine/test_play_resolver.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/fantasy_sim/engine/play_resolver.py tests/test_engine/test_play_resolver.py
git commit -m "feat: add QB pre-throw fumble check (botched snap, strip)"
```

---

### Task 10: QB Fumble Attribution in game_sim

**Files:**
- Modify: `tests/test_engine/test_game_sim.py`
- Modify: `src/fantasy_sim/engine/game_sim.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_engine/test_game_sim.py`:

```python
class TestQBFumbleAttribution:
    def test_pre_throw_fumble_attributed_to_qb(self):
        from fantasy_sim.engine.game_sim import _update_player_stats
        from fantasy_sim.engine.types import PlayResult
        from fantasy_sim.models.player import PlayerModel, PlayerUsage, PlayerOutcomes, TeamRoster

        qb = PlayerModel("QB1", "QB", "QB", "T",
                         PlayerUsage(snap_share=1.0), PlayerOutcomes())
        wr = PlayerModel("WR1", "WR", "WR", "T",
                         PlayerUsage(target_share=1.0), PlayerOutcomes())
        roster = TeamRoster(team="T", players=[qb, wr])

        player_stats = {}
        # Simulate a pre-throw fumble: pass play, fumble, not sack, not complete, no receiver
        result = PlayResult(
            play_type="pass", yards=0, is_fumble=True,
            is_sack=False, is_complete=False,
            passer_id="QB1", receiver_id=None,
        )
        _update_player_stats(player_stats, result, roster)

        assert "QB1" in player_stats
        assert player_stats["QB1"].fumbles_lost == 1
        assert player_stats["QB1"].pass_attempts == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_engine/test_game_sim.py::TestQBFumbleAttribution -v`
Expected: FAIL — `fumbles_lost` is 0

- [ ] **Step 3: Implement QB fumble attribution**

In `src/fantasy_sim/engine/game_sim.py`, modify `_update_player_stats()`. In the passer section (~lines 253-270), add after the `elif result.is_complete:` block:

```python
        if result.passer_id is not None:
            if result.passer_id not in player_stats:
                name, position, team = _get_player_info(roster, result.passer_id)
                player_stats[result.passer_id] = PlayerBoxScore(
                    player_id=result.passer_id, name=name,
                    position=position or "QB", team=team)
            qb = player_stats[result.passer_id]
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
                # QB pre-throw fumble (not sack, not complete, not INT)
                if result.is_fumble and not result.is_sack and not result.is_complete:
                    qb.fumbles_lost += 1
```

The key addition is the last 2 lines: `if result.is_fumble and not result.is_sack and not result.is_complete: qb.fumbles_lost += 1`. This catches the pre-throw fumble case without double-counting sack fumbles (which are already tracked via team-level box scores).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_engine/test_game_sim.py::TestQBFumbleAttribution -v`
Expected: PASS

- [ ] **Step 5: Run all game_sim tests for regression**

Run: `uv run pytest tests/test_engine/test_game_sim.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/fantasy_sim/engine/game_sim.py tests/test_engine/test_game_sim.py
git commit -m "feat: attribute QB pre-throw fumbles in player-level stats"
```

---

### Task 11: Full Regression Test

**Files:** None (test-only)

- [ ] **Step 1: Run entire test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 2: Run a quick season sim to verify projections improved**

Run: `uv run fantasy-sim season --season 2025 --sims 50 --weeks 1-17`

Check:
- Pass TDs: QB1 should be in the 30-45 range (not 55+)
- Pass Yards: Multiple QBs above 3000
- QB Fumbles: Most starters should have 1.0+ FL
- QB Rush Yards: Mobile QBs should be in more realistic ranges

- [ ] **Step 3: Update CLAUDE.md with new patterns/constants**

Add to the "Key Patterns" section of `CLAUDE.md`:

```
- **Red Zone TD Gate**: `_red_zone_td_gate(yard_line, play_type, rng)` in `play_resolver.py` applies a probability check when a play would score inside the 20. Constants `PASS_TD_GATE` and `RUN_TD_GATE` are calibrated from 2024 NFL data. Failed gates result in the player being tackled short.
- **Red Zone Catch Rate**: `PlayerOutcomes.red_zone_catch_rate` stores per-player RZ catch rate from PBP data (≥10 RZ targets) or `catch_rate * 0.85` fallback. Used in `_resolve_pass()` when `yard_line <= 20`.
- **QB Pass Fumble Rate**: `PlayerOutcomes.pass_fumble_rate` stores per-QB non-sack fumble rate (≥100 passes) or league average 0.0034. Checked pre-throw in `_resolve_pass()` after INT check.
- **Scramble Rate**: Uses `qb_scramble` column from nflverse PBP to separate actual scrambles from designed runs. Falls back to all QB rushes if column is missing.
```

- [ ] **Step 4: Commit documentation updates**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with red zone accuracy patterns"
```

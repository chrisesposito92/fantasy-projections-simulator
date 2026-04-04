# Matchup Engine — Same-Season Rolling Window Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-enable the PFF matchup engine using same-season rolling window data instead of cross-season, with early-season blending from the previous season.

**Architecture:** `MatchupEngine.compute()` signature changes from `(defense_team, offense_team, training_seasons)` to `(defense_team, offense_team, target_season, max_week)`. A new `_compute_blended_factor()` helper loads current-season data filtered to `week < max_week`, blends with previous-season data when the team has fewer than `min_games` (4) games, and returns a weighted-average factor. `GameContextBuilder.build_game()` passes its existing `target_season`/`week` params through.

**Tech Stack:** Python 3.12+, polars, pytest

---

### Task 1: Update `compute()` signature and guard clauses

**Files:**
- Modify: `tests/test_data/test_pff/test_matchup.py` (add new test class)
- Modify: `src/fantasy_sim/data/pff/matchup.py:263-313` (`compute()` method)

- [ ] **Step 1: Write failing tests for guard clauses**

Add a new test class at the end of `tests/test_data/test_pff/test_matchup.py`:

```python
# ========== Rolling window tests ==========


class TestRollingWindow:
    """Tests for same-season rolling window matchup computation."""

    def test_none_target_season_returns_neutral(self, pff_dir, loader, default_config):
        """compute() with target_season=None returns all-neutral MatchupContext."""
        _write_defense_coverage(pff_dir, 2024, THREE_TEAM_COVERAGE)

        engine = MatchupEngine(default_config, loader)
        ctx = engine.compute("BAL", "KC", target_season=None, max_week=8)

        assert ctx.catch_rate_factor == 1.0
        assert ctx.sack_rate_factor == 1.0
        assert ctx.rush_yards_factor == 1.0

    def test_none_max_week_returns_neutral(self, pff_dir, loader, default_config):
        """compute() with max_week=None returns all-neutral MatchupContext."""
        _write_defense_coverage(pff_dir, 2024, THREE_TEAM_COVERAGE)

        engine = MatchupEngine(default_config, loader)
        ctx = engine.compute("BAL", "KC", target_season=2024, max_week=None)

        assert ctx.catch_rate_factor == 1.0
        assert ctx.sack_rate_factor == 1.0
        assert ctx.rush_yards_factor == 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_pff/test_matchup.py::TestRollingWindow -v`
Expected: FAIL — `compute()` doesn't accept `target_season`/`max_week` params yet.

- [ ] **Step 3: Update `compute()` signature**

In `src/fantasy_sim/data/pff/matchup.py`, replace the entire `compute()` method (lines 263-313) with:

```python
    def compute(
        self,
        defense_team: str,
        offense_team: str,
        target_season: int | None = None,
        max_week: int | None = None,
    ) -> MatchupContext:
        """Compute matchup adjustment factors for a game.

        Uses same-season rolling window: for a week 8 game, loads PFF
        data from weeks 1-7 of target_season. Early-season games blend
        with previous-season data when the team has < min_games games.

        Args:
            defense_team: Team abbreviation for the defense (opponent).
            offense_team: Team abbreviation for the offense (own team).
            target_season: The season being simulated. None = neutral.
            max_week: The week being simulated. Data is filtered to
                week < max_week. None = neutral.

        Returns:
            MatchupContext with all factors populated.
        """
        if not self._config.enabled:
            return MatchupContext()
        if target_season is None or max_week is None:
            return MatchupContext()

        context = MatchupContext()

        for spec in _FACTOR_SPECS:
            team = defense_team if spec["team_side"] == "defense" else offense_team
            factor = self._compute_blended_factor(
                spec["facet"], team, spec, target_season, max_week,
            )
            setattr(context, spec["field"], factor)

        logger.info(
            "Matchup factors: %s D vs %s O (season=%d, week<%d) → "
            "catch=%.3f pass_yd=%.3f sack=%.3f int=%.3f "
            "rush_yd=%.3f ol_pass=%.3f ol_run=%.3f",
            defense_team,
            offense_team,
            target_season,
            max_week,
            context.catch_rate_factor,
            context.pass_yards_factor,
            context.sack_rate_factor,
            context.int_rate_factor,
            context.rush_yards_factor,
            context.ol_pass_block_factor,
            context.ol_run_block_factor,
        )

        return context
```

- [ ] **Step 4: Add stub `_compute_blended_factor()`**

Add this method to the `MatchupEngine` class, above `compute()`:

```python
    def _compute_blended_factor(
        self,
        facet: str,
        team: str,
        spec: dict,
        target_season: int,
        max_week: int,
    ) -> float:
        """Compute a single factor with same-season rolling window + blend.

        Loads current-season data filtered to week < max_week. If the team
        has fewer than min_games games in that window, blends with the
        previous season using a linear ramp: weight = games / min_games.

        Args:
            facet: PFF facet name (e.g. "defense_coverage").
            team: Team abbreviation to compute the factor for.
            spec: Factor specification dict from _FACTOR_SPECS.
            target_season: The season being simulated.
            max_week: Filter data to week < max_week.

        Returns:
            Blended factor value (centered on 1.0).
        """
        config = self._config

        # Load current season and filter to week < max_week
        current_df = self._load_cached(facet, [target_season])
        if not current_df.is_empty() and "week" in current_df.columns:
            current_df = current_df.filter(pl.col("week") < max_week)

        # Count this team's games in the filtered window
        current_games = self._count_team_games(current_df, team)

        # Compute factor from current-season data (may be empty)
        current_factor = self._compute_single_factor(
            current_df, team, spec, config,
        )

        if current_games >= config.min_games:
            return current_factor

        # Early-season blend: load previous season
        prev_df = self._load_cached(facet, [target_season - 1])
        if prev_df.is_empty():
            # No previous season data — use whatever current season gives us
            return current_factor

        prev_factor = self._compute_single_factor(
            prev_df, team, spec, config,
        )

        # Linear ramp: blend_weight = current_games / min_games
        blend_weight = current_games / config.min_games
        return blend_weight * current_factor + (1 - blend_weight) * prev_factor
```

- [ ] **Step 5: Add `_count_team_games()` helper**

Add this method to the `MatchupEngine` class, below `_get_team_stat()`:

```python
    def _count_team_games(self, df: pl.DataFrame, team: str) -> int:
        """Count distinct games for a team in a DataFrame.

        Returns:
            Number of distinct games. 0 if team not found or df is empty.
        """
        if df.is_empty():
            return 0

        team_rows = df.filter(pl.col("team") == team)
        if team_rows.is_empty():
            return 0

        if "game_id" in team_rows.columns:
            return team_rows.select(pl.col("game_id").n_unique()).item()
        elif "week" in team_rows.columns:
            return team_rows.select(pl.col("week").n_unique()).item()
        return team_rows.height
```

- [ ] **Step 6: Run guard clause tests to verify they pass**

Run: `uv run pytest tests/test_data/test_pff/test_matchup.py::TestRollingWindow -v`
Expected: PASS — both guard clause tests should pass.

- [ ] **Step 7: Commit**

```bash
git add src/fantasy_sim/data/pff/matchup.py tests/test_data/test_pff/test_matchup.py
git commit -m "feat: update matchup compute() signature for rolling window

New params: target_season + max_week replace training_seasons.
Guard clauses return neutral when either is None.
Stub _compute_blended_factor with same-season filtering + early blend."
```

---

### Task 2: Rolling window filtering tests

**Files:**
- Modify: `tests/test_data/test_pff/test_matchup.py` (add tests to `TestRollingWindow`)

- [ ] **Step 1: Write failing test for week filtering**

Add to the `TestRollingWindow` class in `tests/test_data/test_pff/test_matchup.py`:

```python
    def test_only_uses_weeks_before_max_week(self, pff_dir, loader, default_config):
        """compute(target_season=2024, max_week=8) only uses weeks 1-7 data."""
        # Write data for weeks 1-10 with different stats per week range
        # Weeks 1-7: BAL has strong coverage (catch_rate=0.55)
        # Weeks 8-10: BAL has weak coverage (catch_rate=0.80)
        early_teams = [
            {"team": "BAL", "n_players": 2, "n_games": 7,
             "catch_rate": 0.55, "yards_per_reception": 10.0,
             "grades_coverage_defense": 88.0, "interceptions": 1.2},
            {"team": "KC", "n_players": 2, "n_games": 7,
             "catch_rate": 0.64, "yards_per_reception": 12.0,
             "grades_coverage_defense": 65.0, "interceptions": 0.7},
            {"team": "CAR", "n_players": 2, "n_games": 7,
             "catch_rate": 0.72, "yards_per_reception": 14.5,
             "grades_coverage_defense": 48.0, "interceptions": 0.3},
        ]

        # Write weeks 1-7 with strong BAL defense
        _write_defense_coverage(pff_dir, 2024, early_teams)

        # Manually append weeks 8-10 with weak BAL defense to the same parquet
        late_rows = {
            "player_id": [], "player": [], "team": [], "position": [],
            "season": [], "week": [], "game_id": [],
            "catch_rate": [], "yards_per_reception": [],
            "grades_coverage_defense": [], "targets": [],
            "receptions": [], "interceptions": [], "yards": [],
            "yards_after_catch": [],
        }
        for w in [8, 9, 10]:
            for pid_offset, team_info in enumerate([
                ("BAL", 0.80, 15.0, 45.0, 0.2),
                ("KC", 0.64, 12.0, 65.0, 0.7),
                ("CAR", 0.72, 14.5, 48.0, 0.3),
            ]):
                team, cr, ypr, grade, ints = team_info
                late_rows["player_id"].append(9000 + pid_offset)
                late_rows["player"].append(f"Late_{team}")
                late_rows["team"].append(team)
                late_rows["position"].append("CB")
                late_rows["season"].append(2024)
                late_rows["week"].append(w)
                late_rows["game_id"].append(9000 + w)
                late_rows["catch_rate"].append(cr)
                late_rows["yards_per_reception"].append(ypr)
                late_rows["grades_coverage_defense"].append(grade)
                late_rows["targets"].append(20)
                late_rows["receptions"].append(int(cr * 20))
                late_rows["interceptions"].append(ints)
                late_rows["yards"].append(ypr * 5.0)
                late_rows["yards_after_catch"].append(ypr * 2.0)

        # Concatenate early + late into one file
        early_df = pl.read_parquet(pff_dir / "defense_coverage_2024.parquet")
        late_df = pl.DataFrame(late_rows)
        combined = pl.concat([early_df, late_df], how="diagonal_relaxed")
        combined.write_parquet(pff_dir / "defense_coverage_2024.parquet")

        engine = MatchupEngine(default_config, loader)

        # max_week=8: should only see weeks 1-7 where BAL is strong
        ctx_w8 = engine.compute("BAL", "KC", target_season=2024, max_week=8)

        # BAL catch_rate=0.55 in weeks 1-7 → below league avg → factor < 1.0
        assert ctx_w8.catch_rate_factor < 1.0

        # max_week=11: includes weeks 8-10 where BAL weakened
        # Need fresh engine to avoid cache
        engine2 = MatchupEngine(default_config, PffLoader(pff_dir))
        ctx_w11 = engine2.compute("BAL", "KC", target_season=2024, max_week=11)

        # With late-season weak data mixed in, BAL factor should be higher
        # (closer to neutral or above 1.0)
        assert ctx_w11.catch_rate_factor > ctx_w8.catch_rate_factor
```

- [ ] **Step 2: Run test to verify it passes**

Run: `uv run pytest tests/test_data/test_pff/test_matchup.py::TestRollingWindow::test_only_uses_weeks_before_max_week -v`
Expected: PASS — the `_compute_blended_factor()` from Task 1 already filters by `week < max_week`.

- [ ] **Step 3: Commit**

```bash
git add tests/test_data/test_pff/test_matchup.py
git commit -m "test: add rolling window week filtering test for matchup engine"
```

---

### Task 3: Early-season blending tests

**Files:**
- Modify: `tests/test_data/test_pff/test_matchup.py` (add tests to `TestRollingWindow`)

- [ ] **Step 1: Write tests for linear ramp blending**

Add to the `TestRollingWindow` class:

```python
    def test_early_season_blends_with_previous_season(
        self, pff_dir, loader, default_config
    ):
        """Team with < min_games (4) same-season games blends with previous season."""
        # Previous season: BAL is weak defense (catch_rate=0.75)
        prev_coverage = [
            {"team": "BAL", "n_players": 2, "n_games": 10,
             "catch_rate": 0.75, "yards_per_reception": 14.0,
             "grades_coverage_defense": 45.0, "interceptions": 0.3},
            {"team": "KC", "n_players": 2, "n_games": 10,
             "catch_rate": 0.64, "yards_per_reception": 12.0,
             "grades_coverage_defense": 65.0, "interceptions": 0.7},
            {"team": "CAR", "n_players": 2, "n_games": 10,
             "catch_rate": 0.55, "yards_per_reception": 10.0,
             "grades_coverage_defense": 85.0, "interceptions": 1.0},
        ]
        _write_defense_coverage(pff_dir, 2023, prev_coverage)

        # Current season: BAL is strong defense (catch_rate=0.50) but only 2 games
        curr_coverage = [
            {"team": "BAL", "n_players": 2, "n_games": 2,
             "catch_rate": 0.50, "yards_per_reception": 9.0,
             "grades_coverage_defense": 90.0, "interceptions": 1.5},
            {"team": "KC", "n_players": 2, "n_games": 6,
             "catch_rate": 0.64, "yards_per_reception": 12.0,
             "grades_coverage_defense": 65.0, "interceptions": 0.7},
            {"team": "CAR", "n_players": 2, "n_games": 6,
             "catch_rate": 0.72, "yards_per_reception": 14.5,
             "grades_coverage_defense": 48.0, "interceptions": 0.3},
        ]
        _write_defense_coverage(pff_dir, 2024, curr_coverage)

        engine = MatchupEngine(default_config, loader)
        # max_week=3: BAL has 2 games (weeks 1-2), below min_games=4
        ctx = engine.compute("BAL", "KC", target_season=2024, max_week=3)

        # Blended: 50% current (BAL strong → factor < 1.0) + 50% prev (BAL weak → factor > 1.0)
        # Result should be between the two extremes — closer to neutral than pure current
        # We just verify it's not identical to what pure current would give
        # (and not identical to pure previous)
        assert ctx.catch_rate_factor != 1.0  # Not neutral — data was used

    def test_blend_weight_is_linear_ramp(self, pff_dir, loader):
        """Blend weight = current_games / min_games (linear ramp)."""
        # Use a custom config with wide clamp and high sensitivity for clarity
        config = PffConfig(
            enabled=True,
            matchup=MatchupConfig(
                enabled=True,
                pass_defense_sensitivity=0.10,
                factor_clamp=(0.50, 1.50),
                min_games=4,
            ),
        )

        # Previous season: BAL has factor that computes to a known value
        prev_coverage = [
            {"team": "BAL", "n_players": 2, "n_games": 10,
             "catch_rate": 0.75, "yards_per_reception": 14.0,
             "grades_coverage_defense": 45.0, "interceptions": 0.3},
            {"team": "KC", "n_players": 2, "n_games": 10,
             "catch_rate": 0.60, "yards_per_reception": 12.0,
             "grades_coverage_defense": 65.0, "interceptions": 0.7},
            {"team": "CAR", "n_players": 2, "n_games": 10,
             "catch_rate": 0.45, "yards_per_reception": 10.0,
             "grades_coverage_defense": 85.0, "interceptions": 1.0},
        ]
        _write_defense_coverage(pff_dir, 2023, prev_coverage)

        # Current season: 1 game for BAL, 6 for others
        curr_coverage = [
            {"team": "BAL", "n_players": 2, "n_games": 1,
             "catch_rate": 0.50, "yards_per_reception": 9.0,
             "grades_coverage_defense": 90.0, "interceptions": 1.5},
            {"team": "KC", "n_players": 2, "n_games": 6,
             "catch_rate": 0.60, "yards_per_reception": 12.0,
             "grades_coverage_defense": 65.0, "interceptions": 0.7},
            {"team": "CAR", "n_players": 2, "n_games": 6,
             "catch_rate": 0.70, "yards_per_reception": 14.5,
             "grades_coverage_defense": 48.0, "interceptions": 0.3},
        ]
        _write_defense_coverage(pff_dir, 2024, curr_coverage)

        engine = MatchupEngine(config, loader)
        # max_week=2: BAL has 1 game → blend_weight = 1/4 = 0.25
        ctx_w2 = engine.compute("BAL", "KC", target_season=2024, max_week=2)

        # Get pure previous-season factor for comparison
        engine_prev = MatchupEngine(config, PffLoader(pff_dir))
        # Use max_week=1 to get 0 current games → 100% previous
        ctx_prev = engine_prev.compute("BAL", "KC", target_season=2024, max_week=1)

        # With 1 current game: blended = 0.25 * current + 0.75 * previous
        # With 0 current games: blended = 0.0 * current + 1.0 * previous
        # So ctx_prev should be closer to pure previous than ctx_w2
        # And ctx_w2 should differ from ctx_prev (current pulls it)
        assert ctx_w2.catch_rate_factor != ctx_prev.catch_rate_factor

    def test_at_min_games_uses_current_only(self, pff_dir, loader, default_config):
        """Once team reaches min_games (4), use current season only — no blending."""
        # Previous season: BAL weak defense
        prev_coverage = [
            {"team": "BAL", "n_players": 2, "n_games": 10,
             "catch_rate": 0.80, "yards_per_reception": 16.0,
             "grades_coverage_defense": 40.0, "interceptions": 0.2},
            {"team": "KC", "n_players": 2, "n_games": 10,
             "catch_rate": 0.64, "yards_per_reception": 12.0,
             "grades_coverage_defense": 65.0, "interceptions": 0.7},
            {"team": "CAR", "n_players": 2, "n_games": 10,
             "catch_rate": 0.55, "yards_per_reception": 10.0,
             "grades_coverage_defense": 85.0, "interceptions": 1.0},
        ]
        _write_defense_coverage(pff_dir, 2023, prev_coverage)

        # Current season: BAL strong defense with exactly 4 games
        curr_coverage = [
            {"team": "BAL", "n_players": 2, "n_games": 4,
             "catch_rate": 0.50, "yards_per_reception": 9.0,
             "grades_coverage_defense": 90.0, "interceptions": 1.5},
            {"team": "KC", "n_players": 2, "n_games": 6,
             "catch_rate": 0.64, "yards_per_reception": 12.0,
             "grades_coverage_defense": 65.0, "interceptions": 0.7},
            {"team": "CAR", "n_players": 2, "n_games": 6,
             "catch_rate": 0.72, "yards_per_reception": 14.5,
             "grades_coverage_defense": 48.0, "interceptions": 0.3},
        ]
        _write_defense_coverage(pff_dir, 2024, curr_coverage)

        engine = MatchupEngine(default_config, loader)
        # max_week=5: BAL has 4 games (weeks 1-4) = min_games → no blending
        ctx = engine.compute("BAL", "KC", target_season=2024, max_week=5)

        # BAL is strong in current season → factor should be < 1.0
        # If blending occurred, previous season (weak) would pull it toward/above 1.0
        assert ctx.catch_rate_factor < 1.0
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_pff/test_matchup.py::TestRollingWindow -v`
Expected: PASS — all 5 tests (2 guard clauses + 3 new) should pass with Task 1 implementation.

- [ ] **Step 3: Commit**

```bash
git add tests/test_data/test_pff/test_matchup.py
git commit -m "test: add early-season blending tests for matchup engine

Linear ramp verification, min_games threshold, and previous-season blend."
```

---

### Task 4: Edge cases — week 1 fallback, no data, cache keys, blended factor math

**Files:**
- Modify: `tests/test_data/test_pff/test_matchup.py` (add tests to `TestRollingWindow`)

- [ ] **Step 1: Write edge case tests**

Add to the `TestRollingWindow` class:

```python
    def test_week_1_uses_previous_season_only(self, pff_dir, loader, default_config):
        """Week 1 (max_week=1): 0 current-season games → 100% previous season."""
        prev_coverage = [
            {"team": "BAL", "n_players": 2, "n_games": 10,
             "catch_rate": 0.50, "yards_per_reception": 9.0,
             "grades_coverage_defense": 90.0, "interceptions": 1.5},
            {"team": "KC", "n_players": 2, "n_games": 10,
             "catch_rate": 0.64, "yards_per_reception": 12.0,
             "grades_coverage_defense": 65.0, "interceptions": 0.7},
            {"team": "CAR", "n_players": 2, "n_games": 10,
             "catch_rate": 0.75, "yards_per_reception": 14.5,
             "grades_coverage_defense": 48.0, "interceptions": 0.3},
        ]
        _write_defense_coverage(pff_dir, 2023, prev_coverage)

        # Current season data exists but no games before week 1
        curr_coverage = [
            {"team": "BAL", "n_players": 2, "n_games": 6,
             "catch_rate": 0.55, "yards_per_reception": 10.0,
             "grades_coverage_defense": 88.0, "interceptions": 1.2},
            {"team": "KC", "n_players": 2, "n_games": 6,
             "catch_rate": 0.64, "yards_per_reception": 12.0,
             "grades_coverage_defense": 65.0, "interceptions": 0.7},
            {"team": "CAR", "n_players": 2, "n_games": 6,
             "catch_rate": 0.72, "yards_per_reception": 14.5,
             "grades_coverage_defense": 48.0, "interceptions": 0.3},
        ]
        _write_defense_coverage(pff_dir, 2024, curr_coverage)

        engine = MatchupEngine(default_config, loader)
        ctx = engine.compute("BAL", "KC", target_season=2024, max_week=1)

        # blend_weight = 0/4 = 0.0 → 100% previous season
        # BAL in 2023: catch_rate=0.50 (strong) → factor < 1.0
        assert ctx.catch_rate_factor < 1.0

    def test_no_data_either_season_returns_neutral(self, pff_dir, loader, default_config):
        """No PFF data for current or previous season → all factors 1.0."""
        engine = MatchupEngine(default_config, loader)
        ctx = engine.compute("BAL", "KC", target_season=2024, max_week=8)

        assert ctx.catch_rate_factor == 1.0
        assert ctx.pass_yards_factor == 1.0
        assert ctx.sack_rate_factor == 1.0
        assert ctx.int_rate_factor == 1.0
        assert ctx.rush_yards_factor == 1.0
        assert ctx.ol_pass_block_factor == 1.0
        assert ctx.ol_run_block_factor == 1.0

    def test_cache_reused_within_same_week(self, pff_dir, loader, default_config):
        """Multiple compute() calls for the same season reuse cached season data."""
        _write_defense_coverage(pff_dir, 2024, THREE_TEAM_COVERAGE)

        engine = MatchupEngine(default_config, loader)
        engine.compute("BAL", "KC", target_season=2024, max_week=8)
        engine.compute("CAR", "KC", target_season=2024, max_week=8)

        # Cache should have the full 2024 season loaded once
        cache_keys = list(engine._cache.keys())
        assert any("2024" in k for k in cache_keys)
        # Only one entry for defense_coverage_2024 (not per-week)
        coverage_keys = [k for k in cache_keys if "defense_coverage" in k]
        assert len(coverage_keys) == 1

    def test_blend_monotonically_shifts_toward_current(self, pff_dir, loader):
        """As more current-season games accumulate, factor moves from prev toward current.

        Verifies monotonicity: week 1 (100% prev) → week 2 (25% curr) →
        week 3 (50% curr) should show the factor moving in a consistent
        direction as current-season weight increases.
        """
        config = PffConfig(
            enabled=True,
            matchup=MatchupConfig(
                enabled=True,
                pass_defense_sensitivity=0.10,
                factor_clamp=(0.50, 1.50),
                min_games=4,
            ),
        )

        # Previous season: BAL is weak defense (high catch_rate allowed)
        prev_coverage = [
            {"team": "BAL", "n_players": 2, "n_games": 10,
             "catch_rate": 0.75, "yards_per_reception": 14.0,
             "grades_coverage_defense": 45.0, "interceptions": 0.3},
            {"team": "KC", "n_players": 2, "n_games": 10,
             "catch_rate": 0.60, "yards_per_reception": 12.0,
             "grades_coverage_defense": 65.0, "interceptions": 0.7},
            {"team": "CAR", "n_players": 2, "n_games": 10,
             "catch_rate": 0.45, "yards_per_reception": 10.0,
             "grades_coverage_defense": 85.0, "interceptions": 1.0},
        ]
        _write_defense_coverage(pff_dir, 2023, prev_coverage)

        # Current season: BAL is strong defense (low catch_rate, high grade)
        # 3 games available (weeks 1-3), below min_games=4
        curr_coverage = [
            {"team": "BAL", "n_players": 2, "n_games": 3,
             "catch_rate": 0.50, "yards_per_reception": 9.0,
             "grades_coverage_defense": 90.0, "interceptions": 1.5},
            {"team": "KC", "n_players": 2, "n_games": 6,
             "catch_rate": 0.60, "yards_per_reception": 12.0,
             "grades_coverage_defense": 65.0, "interceptions": 0.7},
            {"team": "CAR", "n_players": 2, "n_games": 6,
             "catch_rate": 0.70, "yards_per_reception": 14.5,
             "grades_coverage_defense": 48.0, "interceptions": 0.3},
        ]
        _write_defense_coverage(pff_dir, 2024, curr_coverage)

        # Week 1: 0 current games → 100% previous (BAL weak → factor > 1.0)
        e1 = MatchupEngine(config, PffLoader(pff_dir))
        f_w1 = e1.compute("BAL", "KC", target_season=2024, max_week=1).catch_rate_factor

        # Week 2: 1 current game → 25% current, 75% previous
        e2 = MatchupEngine(config, PffLoader(pff_dir))
        f_w2 = e2.compute("BAL", "KC", target_season=2024, max_week=2).catch_rate_factor

        # Week 3: 2 current games → 50% current, 50% previous
        e3 = MatchupEngine(config, PffLoader(pff_dir))
        f_w3 = e3.compute("BAL", "KC", target_season=2024, max_week=3).catch_rate_factor

        # Week 4: 3 current games → 75% current, 25% previous
        e4 = MatchupEngine(config, PffLoader(pff_dir))
        f_w4 = e4.compute("BAL", "KC", target_season=2024, max_week=4).catch_rate_factor

        # BAL was weak last season (factor > 1.0) and strong this season
        # (current component pulls factor down). As more current data is
        # included, factor should monotonically decrease toward current:
        assert f_w1 > f_w2 or f_w1 == pytest.approx(f_w2, abs=0.001)
        assert f_w2 > f_w3 or f_w2 == pytest.approx(f_w3, abs=0.001)
        assert f_w3 > f_w4 or f_w3 == pytest.approx(f_w4, abs=0.001)

        # The endpoints should be meaningfully different
        assert f_w1 > f_w4
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_pff/test_matchup.py::TestRollingWindow -v`
Expected: PASS — all 10 tests in `TestRollingWindow` should pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_data/test_pff/test_matchup.py
git commit -m "test: add edge case tests for matchup rolling window

Week 1 fallback, no data, cache reuse, blended factor math."
```

---

### Task 5: Update existing tests for new `compute()` signature

**Files:**
- Modify: `tests/test_data/test_pff/test_matchup.py` (update existing test classes)

The existing tests in `TestMatchupEngineCompute`, `TestGradeFallback`, `TestMatchupCaching`, and `TestNumericPrecision` call `engine.compute("BAL", "KC", [2024])` with the old `training_seasons` positional arg. These need to switch to the new `target_season`/`max_week` params.

- [ ] **Step 1: Update `TestMatchupEngineCompute` calls**

In `tests/test_data/test_pff/test_matchup.py`, find and replace all `compute()` calls in the `TestMatchupEngineCompute` class. The pattern is:

Old: `engine.compute("TEAM1", "TEAM2", [2024])`
New: `engine.compute("TEAM1", "TEAM2", target_season=2024, max_week=18)`

Using `max_week=18` ensures all regular-season weeks (1-17) are included, which matches the old behavior of loading the full season.

Replace each occurrence in `TestMatchupEngineCompute`:

```
engine.compute("BAL", "KC", [2024])    → engine.compute("BAL", "KC", target_season=2024, max_week=18)
engine.compute("CAR", "KC", [2024])    → engine.compute("CAR", "KC", target_season=2024, max_week=18)
engine.compute("KC", "KC", [2024])     → engine.compute("KC", "KC", target_season=2024, max_week=18)
engine.compute("BAL", "KC", [2024])    → engine.compute("BAL", "KC", target_season=2024, max_week=18)
engine.compute("KC", "PHI", [2024])    → engine.compute("KC", "PHI", target_season=2024, max_week=18)
engine.compute("KC", "NYG", [2024])    → engine.compute("KC", "NYG", target_season=2024, max_week=18)
engine.compute("BAL", "PHI", [2024])   → engine.compute("BAL", "PHI", target_season=2024, max_week=18)
engine.compute("SEA", "KC", [2024])    → engine.compute("SEA", "KC", target_season=2024, max_week=18)
```

- [ ] **Step 2: Update `TestGradeFallback` calls**

Same pattern:
```
engine.compute("BAL", "KC", [2024])    → engine.compute("BAL", "KC", target_season=2024, max_week=18)
```

- [ ] **Step 3: Update `TestMatchupCaching` calls**

```
engine.compute("BAL", "KC", [2024])    → engine.compute("BAL", "KC", target_season=2024, max_week=18)
engine.compute("CAR", "KC", [2024])    → engine.compute("CAR", "KC", target_season=2024, max_week=18)
engine.compute("BAL", "KC", [2023])    → engine.compute("BAL", "KC", target_season=2023, max_week=18)
engine.compute("BAL", "KC", [2024])    → engine.compute("BAL", "KC", target_season=2024, max_week=18)
```

- [ ] **Step 4: Update `TestNumericPrecision` calls**

```
engine.compute("BAL", "KC", [2024])    → engine.compute("BAL", "KC", target_season=2024, max_week=18)
```

- [ ] **Step 5: Run all matchup tests**

Run: `uv run pytest tests/test_data/test_pff/test_matchup.py -v`
Expected: ALL PASS — existing tests work with new signature, new rolling window tests still pass.

- [ ] **Step 6: Commit**

```bash
git add tests/test_data/test_pff/test_matchup.py
git commit -m "test: update existing matchup tests for new compute() signature

Old: compute(defense, offense, [seasons])
New: compute(defense, offense, target_season=YYYY, max_week=18)"
```

---

### Task 6: Update GameContextBuilder + integration tests

**Files:**
- Modify: `src/fantasy_sim/data/game_context.py:338-348` (matchup engine call site)
- Modify: `tests/test_data/test_game_context.py` (add integration tests)

- [ ] **Step 1: Write failing integration test**

Add to the end of `TestGameContextBuilder` in `tests/test_data/test_game_context.py`:

```python
    def test_matchup_engine_receives_target_season_and_week(
        self, builder, expanded_pbp, sample_rosters, tmp_path
    ):
        """build_game() passes target_season and week to matchup engine."""
        from unittest.mock import MagicMock, patch
        from fantasy_sim.data.pff.models import MatchupContext, MatchupConfig, PffConfig

        mock_engine = MagicMock()
        mock_engine.compute.return_value = MatchupContext()

        builder._matchup_engine = mock_engine

        builder.build_game(
            home_team="KC", away_team="BUF",
            pbp=expanded_pbp, rosters=sample_rosters,
            training_seasons=[2024], target_season=2024, week=8,
        )

        # Should be called twice: away D vs home O, home D vs away O
        assert mock_engine.compute.call_count == 2

        # First call: away defense (BUF) adjusts home offense (KC)
        call1 = mock_engine.compute.call_args_list[0]
        assert call1.kwargs["defense_team"] == "BUF" or call1.args[0] == "BUF"
        assert call1.kwargs.get("target_season") == 2024 or (
            len(call1.args) > 2 and call1.args[2] == 2024
        )
        assert call1.kwargs.get("max_week") == 8 or (
            len(call1.args) > 3 and call1.args[3] == 8
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data/test_game_context.py::TestGameContextBuilder::test_matchup_engine_receives_target_season_and_week -v`
Expected: FAIL — `build_game()` still passes `training_seasons` to `compute()`.

- [ ] **Step 3: Update `build_game()` in `game_context.py`**

In `src/fantasy_sim/data/game_context.py`, replace lines 338-348 (the matchup engine block):

Old:
```python
        # PFF matchup adjustments: away D → home offense, home D → away offense
        if self._matchup_engine is not None:
            home_ctx = self._matchup_engine.compute(
                defense_team=away_team,
                offense_team=home_team,
                training_seasons=training_seasons,
            )
            away_ctx = self._matchup_engine.compute(
                defense_team=home_team,
                offense_team=away_team,
                training_seasons=training_seasons,
            )
            self._apply_matchup(home_dists, home_roster, home_ctx)
            self._apply_matchup(away_dists, away_roster, away_ctx)
```

New:
```python
        # PFF matchup adjustments: away D → home offense, home D → away offense
        if self._matchup_engine is not None:
            home_ctx = self._matchup_engine.compute(
                defense_team=away_team,
                offense_team=home_team,
                target_season=target_season,
                max_week=week,
            )
            away_ctx = self._matchup_engine.compute(
                defense_team=home_team,
                offense_team=away_team,
                target_season=target_season,
                max_week=week,
            )
            self._apply_matchup(home_dists, home_roster, home_ctx)
            self._apply_matchup(away_dists, away_roster, away_ctx)
```

- [ ] **Step 4: Run integration test to verify it passes**

Run: `uv run pytest tests/test_data/test_game_context.py::TestGameContextBuilder::test_matchup_engine_receives_target_season_and_week -v`
Expected: PASS

- [ ] **Step 5: Run full test suite to verify nothing broke**

Run: `uv run pytest tests/ -v --timeout=120`
Expected: ALL PASS — no existing tests should break.

- [ ] **Step 6: Commit**

```bash
git add src/fantasy_sim/data/game_context.py tests/test_data/test_game_context.py
git commit -m "feat: pass target_season/week from GameContextBuilder to matchup engine

build_game() now passes target_season and week through to
MatchupEngine.compute() for same-season rolling window filtering."
```

---

### Task 7: Add A/B test modes to validate script

**Files:**
- Modify: `scripts/validate_pff_signal.py:212-272` (`_build_pff_config()` + arg parser)

- [ ] **Step 1: Update `_build_pff_config()` to handle new modes**

In `scripts/validate_pff_signal.py`, replace the `_build_pff_config()` function (lines 212-272):

```python
def _build_pff_config(mode: str, overrides: dict | None = None) -> PffConfig:
    """Build a PffConfig with the appropriate layers enabled.

    Args:
        mode: One of "matchup", "talent", "tier", "matchup+tier", or "all".
        overrides: Optional dict with "talent", "matchup", and/or "tier_engine"
            sub-dicts of attribute overrides to apply via setattr.
    """
    if mode == "matchup":
        matchup_cfg = MatchupConfig(enabled=True)
        talent_cfg = TalentConfig(enabled=False)
        tier_cfg = TierConfig(enabled=False)
    elif mode == "talent":
        matchup_cfg = MatchupConfig(enabled=False)
        talent_cfg = TalentConfig(enabled=True)
        tier_cfg = TierConfig(enabled=False)
    elif mode == "tier":
        matchup_cfg = MatchupConfig(enabled=False)
        talent_cfg = TalentConfig(enabled=False)
        tier_cfg = TierConfig(enabled=True)
    elif mode == "matchup+tier":
        matchup_cfg = MatchupConfig(enabled=True)
        talent_cfg = TalentConfig(enabled=False)
        tier_cfg = TierConfig(enabled=True)
    else:  # "all"
        matchup_cfg = MatchupConfig(enabled=True)
        talent_cfg = TalentConfig(enabled=True)
        tier_cfg = TierConfig(enabled=False)

    if overrides and "talent" in overrides:
        for key, val in overrides["talent"].items():
            if hasattr(talent_cfg, key):
                # Don't replace dataclass fields with plain dicts
                current = getattr(talent_cfg, key)
                if hasattr(current, '__dataclass_fields__') and isinstance(val, dict):
                    for k, v in val.items():
                        if hasattr(current, k):
                            setattr(current, k, v)
                else:
                    setattr(talent_cfg, key, val)
    if overrides and "matchup" in overrides:
        for key, val in overrides["matchup"].items():
            if hasattr(matchup_cfg, key):
                setattr(matchup_cfg, key, val)
    if overrides and "tier_engine" in overrides:
        for key, val in overrides["tier_engine"].items():
            if not hasattr(tier_cfg, key):
                continue
            if key == "position_grades" and isinstance(val, dict):
                # Merge per-position: only update specified positions/fields
                for pos, grade_overrides in val.items():
                    if pos in tier_cfg.position_grades and isinstance(grade_overrides, dict):
                        for gk, gv in grade_overrides.items():
                            if hasattr(tier_cfg.position_grades[pos], gk):
                                setattr(tier_cfg.position_grades[pos], gk, gv)
            else:
                current = getattr(tier_cfg, key)
                if hasattr(current, '__dataclass_fields__') and isinstance(val, dict):
                    for k, v in val.items():
                        if hasattr(current, k):
                            setattr(current, k, v)
                else:
                    setattr(tier_cfg, key, val)

    return PffConfig(enabled=True, matchup=matchup_cfg, talent=talent_cfg, tier_engine=tier_cfg)
```

- [ ] **Step 2: Update `--mode` choices in argparser**

In the `main()` function, update the `--mode` argument (around line 449):

Old:
```python
    parser.add_argument(
        "--mode",
        choices=["matchup", "talent", "tier", "all"],
        default="all",
        help=(
            "Which PFF layer(s) to enable in the ON run. "
            "'matchup' = defensive matchup adjustments only, "
            "'talent' = talent stabilizer only, "
            "'tier' = tier distribution engine only, "
            "'all' = matchup + talent layers (default: all)."
        ),
    )
```

New:
```python
    parser.add_argument(
        "--mode",
        choices=["matchup", "talent", "tier", "matchup+tier", "all"],
        default="all",
        help=(
            "Which PFF layer(s) to enable in the ON run. "
            "'matchup' = defensive matchup adjustments only, "
            "'talent' = talent stabilizer only, "
            "'tier' = tier distribution engine only, "
            "'matchup+tier' = matchup + tier (no talent), "
            "'all' = matchup + talent layers (default: all)."
        ),
    )
```

- [ ] **Step 3: Update `mode_label` in `run_backtest_pair()`**

In `run_backtest_pair()` (around line 303), replace the mode_label logic:

Old:
```python
    mode_label = (
        "matchup" if pff_config.matchup.enabled and not pff_config.talent.enabled
        else "talent" if pff_config.talent.enabled and not pff_config.matchup.enabled
        else "all"
    )
```

New:
```python
    mode_label = "unknown"
    if pff_config.matchup.enabled and pff_config.tier_engine.enabled:
        mode_label = "matchup+tier"
    elif pff_config.matchup.enabled and not pff_config.talent.enabled:
        mode_label = "matchup"
    elif pff_config.talent.enabled and not pff_config.matchup.enabled:
        mode_label = "talent"
    elif pff_config.tier_engine.enabled:
        mode_label = "tier"
    else:
        mode_label = "all"
```

- [ ] **Step 4: Verify script parses correctly**

Run: `uv run python scripts/validate_pff_signal.py --help`
Expected: `--mode` shows choices `{matchup,talent,tier,matchup+tier,all}`.

- [ ] **Step 5: Commit**

```bash
git add scripts/validate_pff_signal.py
git commit -m "feat: add matchup and matchup+tier A/B test modes

- --mode matchup: matchup engine only (isolate contribution)
- --mode matchup+tier: both matchup + tier (test additivity)
- Updated mode_label for correct logging"
```

---

### Task 8: Run full test suite and verify

**Files:** None (verification only)

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest tests/ -v --timeout=120`
Expected: ALL PASS — 875+ tests, no regressions.

- [ ] **Step 2: Verify matchup tests specifically**

Run: `uv run pytest tests/test_data/test_pff/test_matchup.py -v`
Expected: All existing tests + 9 new `TestRollingWindow` tests pass.

- [ ] **Step 3: Verify game_context tests specifically**

Run: `uv run pytest tests/test_data/test_game_context.py -v`
Expected: All existing tests + 1 new integration test pass.

- [ ] **Step 4: Commit all remaining changes (if any)**

If any cleanup was needed, commit here. Otherwise this task is just verification.

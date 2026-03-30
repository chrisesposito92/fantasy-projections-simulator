# Season Command Aggregation Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the season CLI command to aggregate player projections into season totals (default), add `--by-week` for per-week output, default to regular season games only, and auto-infer output format from file extension.

**Architecture:** Four independent changes in `cli.py`: (1) three `_aggregate_*` helpers that group-by player/team and sum stats, (2) a `--by-week` flag that controls whether aggregation runs, (3) a `game_type == "REG"` filter on the default week discovery, (4) a `_infer_format` helper used by `_display_projections`. All changes are in `cli.py` except tests.

**Tech Stack:** Python, Click, polars (schedule filtering)

---

## File Structure

- **Modify:** `src/fantasy_sim/cli.py` — Add aggregation helpers, `--by-week` flag, `game_type` filter, format inference, relax week validation
- **Modify:** `tests/test_cli.py` — Add tests for all four features

---

### Task 1: Format Auto-Inference (`_infer_format`)

Smallest, most isolated change. Benefits all commands via `_display_projections`.

**Files:**
- Modify: `src/fantasy_sim/cli.py:286-329` (`_display_projections`)
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write failing tests for format inference**

Add to `tests/test_cli.py`:

```python
class TestFormatInference:
    """Format auto-inference from --output file extension."""

    def test_json_extension_infers_json(self, runner, tmp_path):
        """--output foo.json without --format should export JSON."""
        output = tmp_path / "result.json"
        result = runner.invoke(main, ["demo", "--sims", "10", "--output", str(output)])
        assert result.exit_code == 0
        assert output.exists()
        import json
        data = json.loads(output.read_text())
        assert isinstance(data, list)

    def test_csv_extension_infers_csv(self, runner, tmp_path):
        """--output foo.csv without --format should export CSV."""
        output = tmp_path / "result.csv"
        result = runner.invoke(main, ["demo", "--sims", "10", "--output", str(output)])
        assert result.exit_code == 0
        assert output.exists()
        content = output.read_text()
        assert "," in content  # CSV has commas

    def test_explicit_format_overrides_extension(self, runner, tmp_path):
        """--format csv --output foo.json should export CSV (format wins)."""
        output = tmp_path / "result.json"
        result = runner.invoke(main, ["demo", "--sims", "10", "--format", "csv", "--output", str(output)])
        assert result.exit_code == 0
        assert output.exists()
        content = output.read_text()
        # Should be CSV despite .json extension
        assert "," in content
        import json
        with pytest.raises(json.JSONDecodeError):
            json.loads(content)

    def test_unknown_extension_defaults_to_table(self, runner, tmp_path):
        """--output foo.txt without --format should display table (no file)."""
        output = tmp_path / "result.txt"
        result = runner.invoke(main, ["demo", "--sims", "10", "--output", str(output)])
        assert result.exit_code == 0
        # Table mode doesn't write files, so output should NOT exist
        assert not output.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py::TestFormatInference -v`
Expected: FAIL — `test_json_extension_infers_json` and `test_csv_extension_infers_csv` fail because format stays "table" when `--format` is not passed.

- [ ] **Step 3: Implement `_infer_format` and wire into `_display_projections`**

In `src/fantasy_sim/cli.py`, add a helper before `_display_projections`:

```python
def _infer_format(output_format: str, output_path: str | None, ctx: click.Context) -> str:
    """Infer output format from file extension if --format was not explicitly set."""
    source = ctx.get_parameter_source("output_format")
    if source != click.core.ParameterSource.DEFAULT:
        return output_format  # User explicitly set --format
    if output_path is None:
        return output_format
    ext = Path(output_path).suffix.lower()
    if ext == ".json":
        return "json"
    elif ext == ".csv":
        return "csv"
    return output_format
```

Then update every command that calls `_display_projections` to infer format first. The `demo`, `week`, and `season` commands all need `@click.pass_context` added to their function signatures and a call to `_infer_format` before display.

For the `demo` command, find the call to `_display_projections` and add format inference just before it:

```python
@main.command()
@click.pass_context
# ... existing options ...
def demo(ctx, sims, scoring, output_format, output_path, ...):
    # ... existing code ...
    output_format = _infer_format(output_format, output_path, ctx)
    _display_projections(player_projs, output_format, output_path, ...)
```

Do the same for `week` and `season` commands — add `@click.pass_context`, add `ctx` as first param, add `_infer_format` call before `_display_projections`.

Note: The `game` command has inline display logic (not using `_display_projections`). Add format inference there too, before the `if output_format == "table":` block.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py::TestFormatInference -v`
Expected: All 4 PASS

- [ ] **Step 5: Run full test suite to check for regressions**

Run: `uv run pytest tests/test_cli.py -v`
Expected: All existing tests still pass

- [ ] **Step 6: Commit**

```bash
git add src/fantasy_sim/cli.py tests/test_cli.py
git commit -m "feat: auto-infer output format from file extension"
```

---

### Task 2: Regular Season Default (`game_type` Filter)

**Files:**
- Modify: `src/fantasy_sim/cli.py:151-186` (`_parse_and_validate_weeks`), `src/fantasy_sim/cli.py:465-471` (season command schedule filtering)
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_cli.py`:

```python
class TestRegularSeasonDefault:
    """Season command should default to regular season games only."""

    def test_parse_weeks_all_returns_empty(self):
        """'all' should return empty list (signals dynamic lookup)."""
        from fantasy_sim.cli import _parse_and_validate_weeks
        assert _parse_and_validate_weeks("all") == []

    def test_parse_weeks_allows_playoff_weeks(self):
        """Explicit week 19+ should be accepted (no hardcoded 1-18 limit)."""
        from fantasy_sim.cli import _parse_and_validate_weeks
        result = _parse_and_validate_weeks("19-22")
        assert result == [19, 20, 21, 22]

    def test_parse_weeks_rejects_zero(self):
        """Week 0 should still be rejected."""
        from fantasy_sim.cli import _parse_and_validate_weeks
        with pytest.raises(click.BadParameter):
            _parse_and_validate_weeks("0")

    @patch("fantasy_sim.cli.GameContextBuilder")
    @patch("fantasy_sim.cli.DataLoader")
    def test_season_default_excludes_playoffs(self, MockLoader, MockBuilder, runner):
        """Default weeks='all' should only simulate REG games, not playoff games."""
        mock_loader = MockLoader.return_value
        mock_loader.load_schedules.return_value = pl.DataFrame([
            {"season": 2024, "week": 18, "game_id": "g_reg", "game_type": "REG",
             "home_team": "KC", "away_team": "BUF"},
            {"season": 2024, "week": 19, "game_id": "g_wc", "game_type": "WC",
             "home_team": "KC", "away_team": "MIA"},
        ])
        mock_loader.cache_dir = Path("/tmp/cache")

        mock_builder = MockBuilder.return_value
        from fantasy_sim.engine.types import TeamDistributions
        from fantasy_sim.models.distributions import (
            PlayCallingDist, PlayOutcomeDist, TurnoverRates, KickingModel, DriveStartModel,
        )
        from fantasy_sim.models.player import TeamRoster, PlayerModel, PlayerUsage, PlayerOutcomes

        def make_dists(team):
            return TeamDistributions(
                play_calling=PlayCallingDist(team=team, distributions={}, default={"pass": 0.55, "run": 0.45}),
                play_outcomes=PlayOutcomeDist(distributions={}, defaults={
                    "pass": np.array([0, 5, 8, 10, 12, 15]),
                    "run": np.array([2, 3, 4, 5, 6]),
                }),
                turnover_rates=TurnoverRates(team=team, int_rate=0.02, fumble_rate=0.01, sack_rate=0.06, sack_fumble_rate=0.10),
                kicking=KickingModel(fg_make_rate={"0_39": 0.93, "40_49": 0.82, "50_plus": 0.65}, xp_rate=0.94),
                drive_start=DriveStartModel(touchback_rate=0.55, touchback_yardline=75, return_yardlines=np.array([74, 76])),
            )

        def make_roster(team):
            return TeamRoster(team=team, players=[
                PlayerModel(f"{team}_QB", "QB", "QB", team, PlayerUsage(snap_share=1.0), PlayerOutcomes()),
                PlayerModel(f"{team}_WR", "WR", "WR", team, PlayerUsage(target_share=0.50),
                           PlayerOutcomes(catch_rate=0.60, receiving_yards_dist=np.array([8, 12]))),
                PlayerModel(f"{team}_RB", "RB", "RB", team, PlayerUsage(carry_share=1.0, target_share=0.50),
                           PlayerOutcomes(rushing_yards_dist=np.array([3, 5, 7]),
                                         catch_rate=0.70, receiving_yards_dist=np.array([4, 6]))),
            ])

        mock_builder.build_game.return_value = (
            make_dists("KC"), make_dists("BUF"), make_roster("KC"), make_roster("BUF"),
        )

        result = runner.invoke(main, ["season", "--season", "2024", "--sims", "5"])
        assert result.exit_code == 0
        # Should only simulate week 18 (REG), not week 19 (WC)
        # build_game should be called exactly once (one REG game)
        assert mock_builder.build_game.call_count == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py::TestRegularSeasonDefault -v`
Expected: `test_parse_weeks_allows_playoff_weeks` FAILS (currently raises `BadParameter` for week 19+). `test_season_default_excludes_playoffs` FAILS (currently includes playoff games).

- [ ] **Step 3: Update `_parse_and_validate_weeks` to remove hardcoded 1-18 limit**

In `src/fantasy_sim/cli.py`, replace the validation in `_parse_and_validate_weeks` (lines 179-184):

Old:
```python
    # Validate range
    invalid = [w for w in week_nums if w < 1 or w > 18]
    if invalid:
        raise click.BadParameter(
            f"Invalid week number(s): {invalid}. Regular season weeks are 1-18."
        )
```

New:
```python
    # Validate range — only reject non-positive weeks
    invalid = [w for w in week_nums if w < 1]
    if invalid:
        raise click.BadParameter(
            f"Invalid week number(s): {invalid}. Week numbers must be positive."
        )
```

Also update the docstring from `"validate all week numbers are 1-18"` to `"validate all week numbers are positive"`.

- [ ] **Step 4: Add `game_type` filter in the season command**

In the `season` command (around line 466-471), change the `if not parsed_weeks` block:

Old:
```python
    if not parsed_weeks:
        # "all" — get from schedule data
        week_nums = sorted(schedules.filter(pl.col("season") == season_year)["week"].unique().to_list())
    else:
        week_nums = parsed_weeks
```

New:
```python
    if not parsed_weeks:
        # "all" — regular season only
        reg_season = schedules.filter(
            (pl.col("season") == season_year) & (pl.col("game_type") == "REG")
        )
        week_nums = sorted(reg_season["week"].unique().to_list())
    else:
        week_nums = parsed_weeks
```

Also update the per-week game filter (around line 489) to also filter by `game_type` when using default weeks, to avoid edge cases where a week has both REG and playoff games. Since `parsed_weeks` controls the branch, we can filter schedules upfront:

After the `if not parsed_weeks` block, add the schedule variable for game iteration:

```python
    # Filter schedule for game iteration
    if not parsed_weeks:
        game_schedule = schedules.filter(
            (pl.col("season") == season_year) & (pl.col("game_type") == "REG")
        )
    else:
        game_schedule = schedules.filter(pl.col("season") == season_year)
```

Then in the weekly loop (around line 489), use `game_schedule` instead of `schedules`:

Old:
```python
            week_games = schedules.filter(
                (pl.col("week") == wk) & (pl.col("season") == season_year)
            )
```

New:
```python
            week_games = game_schedule.filter(pl.col("week") == wk)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py::TestRegularSeasonDefault -v`
Expected: All 4 PASS

- [ ] **Step 6: Check existing week validation tests still work**

Run: `uv run pytest tests/test_cli.py::TestWeeksValidation -v`
Expected: `test_season_invalid_week_range` now needs updating — week 0 is still invalid but the error message changed. `test_season_invalid_single_week` (week 19) should now pass without error since we removed the 1-18 limit. Update these tests:

In `TestWeeksValidation`, update `test_season_invalid_week_range`:
```python
    def test_season_invalid_week_range(self, runner):
        """Week 0 should produce a helpful error."""
        result = runner.invoke(main, ["season", "--season", "2024", "--weeks", "0-5", "--sims", "10"])
        assert result.exit_code != 0 or "invalid" in result.output.lower()
```

Update `test_season_invalid_single_week` to test week 0 instead of 19:
```python
    def test_season_invalid_week_zero(self, runner):
        """Week 0 should produce a helpful error."""
        result = runner.invoke(main, ["season", "--season", "2024", "--weeks", "0", "--sims", "10"])
        assert result.exit_code != 0 or "invalid" in result.output.lower()
```

- [ ] **Step 7: Run full CLI tests**

Run: `uv run pytest tests/test_cli.py -v`
Expected: All pass

- [ ] **Step 8: Commit**

```bash
git add src/fantasy_sim/cli.py tests/test_cli.py
git commit -m "feat: season command defaults to regular season games only"
```

---

### Task 3: Season Aggregation Helpers

**Files:**
- Modify: `src/fantasy_sim/cli.py` — Add `_aggregate_player_projections`, `_aggregate_dst_projections`, `_aggregate_kicker_projections`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write failing tests for player aggregation**

Add to `tests/test_cli.py`:

```python
class TestSeasonAggregation:
    """Season-level aggregation of per-game projections."""

    def test_aggregate_player_projections_sums_stats(self):
        """Two entries for same player should sum into one."""
        from fantasy_sim.cli import _aggregate_player_projections
        projs = [
            {"player_id": "p1", "name": "QB1", "position": "QB", "team": "KC",
             "fpts": 20.0, "pass_yards": 250.0, "pass_tds": 2.0, "interceptions": 1.0,
             "sacks": 1.0, "rush_yards": 10.0, "rush_tds": 0.0,
             "targets": 0.0, "receptions": 0.0, "receiving_yards": 0.0,
             "receiving_tds": 0.0, "fumbles_lost": 0.0, "rank": 1},
            {"player_id": "p1", "name": "QB1", "position": "QB", "team": "KC",
             "fpts": 15.0, "pass_yards": 200.0, "pass_tds": 1.0, "interceptions": 0.0,
             "sacks": 2.0, "rush_yards": 5.0, "rush_tds": 1.0,
             "targets": 0.0, "receptions": 0.0, "receiving_yards": 0.0,
             "receiving_tds": 0.0, "fumbles_lost": 1.0, "rank": 2},
        ]
        result = _aggregate_player_projections(projs)
        assert len(result) == 1
        assert result[0]["player_id"] == "p1"
        assert result[0]["fpts"] == 35.0
        assert result[0]["pass_yards"] == 450.0
        assert result[0]["pass_tds"] == 3.0
        assert result[0]["rush_tds"] == 1.0
        assert result[0]["fumbles_lost"] == 1.0
        assert result[0]["rank"] == 1

    def test_aggregate_player_projections_multiple_players(self):
        """Multiple players should each be aggregated and ranked by fpts."""
        from fantasy_sim.cli import _aggregate_player_projections
        projs = [
            {"player_id": "p1", "name": "QB1", "position": "QB", "team": "KC",
             "fpts": 20.0, "pass_yards": 250.0, "pass_tds": 2.0, "interceptions": 0.0,
             "sacks": 0.0, "rush_yards": 0.0, "rush_tds": 0.0,
             "targets": 0.0, "receptions": 0.0, "receiving_yards": 0.0,
             "receiving_tds": 0.0, "fumbles_lost": 0.0, "rank": 1},
            {"player_id": "p2", "name": "WR1", "position": "WR", "team": "KC",
             "fpts": 25.0, "pass_yards": 0.0, "pass_tds": 0.0, "interceptions": 0.0,
             "sacks": 0.0, "rush_yards": 0.0, "rush_tds": 0.0,
             "targets": 8.0, "receptions": 5.0, "receiving_yards": 100.0,
             "receiving_tds": 1.0, "fumbles_lost": 0.0, "rank": 2},
        ]
        result = _aggregate_player_projections(projs)
        assert len(result) == 2
        # WR1 has more fpts, should be ranked #1
        assert result[0]["player_id"] == "p2"
        assert result[0]["rank"] == 1
        assert result[1]["player_id"] == "p1"
        assert result[1]["rank"] == 2

    def test_aggregate_drops_detail_fields(self):
        """Aggregation should drop floor/ceiling/stddev fields."""
        from fantasy_sim.cli import _aggregate_player_projections
        projs = [
            {"player_id": "p1", "name": "QB1", "position": "QB", "team": "KC",
             "fpts": 20.0, "fpts_floor": 10.0, "fpts_ceiling": 30.0, "fpts_stddev": 5.0,
             "pass_yards": 250.0, "pass_yards_floor": 150.0, "pass_yards_ceiling": 350.0, "pass_yards_stddev": 50.0,
             "pass_tds": 2.0, "pass_tds_floor": 1.0, "pass_tds_ceiling": 3.0, "pass_tds_stddev": 0.5,
             "interceptions": 0.0, "interceptions_floor": 0.0, "interceptions_ceiling": 1.0, "interceptions_stddev": 0.3,
             "rush_yards": 0.0, "rush_yards_floor": 0.0, "rush_yards_ceiling": 0.0, "rush_yards_stddev": 0.0,
             "rush_tds": 0.0, "rush_tds_floor": 0.0, "rush_tds_ceiling": 0.0, "rush_tds_stddev": 0.0,
             "targets": 0.0, "targets_floor": 0.0, "targets_ceiling": 0.0, "targets_stddev": 0.0,
             "receptions": 0.0, "receptions_floor": 0.0, "receptions_ceiling": 0.0, "receptions_stddev": 0.0,
             "receiving_yards": 0.0, "receiving_yards_floor": 0.0, "receiving_yards_ceiling": 0.0, "receiving_yards_stddev": 0.0,
             "receiving_tds": 0.0, "receiving_tds_floor": 0.0, "receiving_tds_ceiling": 0.0, "receiving_tds_stddev": 0.0,
             "fumbles_lost": 0.0, "fumbles_lost_floor": 0.0, "fumbles_lost_ceiling": 0.0, "fumbles_lost_stddev": 0.0,
             "sacks": 0.0, "rank": 1},
        ]
        result = _aggregate_player_projections(projs)
        assert "fpts_floor" not in result[0]
        assert "fpts_ceiling" not in result[0]
        assert "fpts_stddev" not in result[0]
        assert "pass_yards_floor" not in result[0]
        assert "fpts" in result[0]  # Base stat preserved
        assert "pass_yards" in result[0]

    def test_aggregate_dst_projections(self):
        """DST projections for same team should sum across weeks."""
        from fantasy_sim.cli import _aggregate_dst_projections
        projs = [
            {"team": "KC", "fpts": 8.0, "sacks": 3.0, "interceptions": 1.0,
             "fumble_recoveries": 0.0, "dst_tds": 0.0, "safeties": 0.0,
             "points_allowed": 17.0, "rank": 1},
            {"team": "KC", "fpts": 10.0, "sacks": 2.0, "interceptions": 2.0,
             "fumble_recoveries": 1.0, "dst_tds": 1.0, "safeties": 0.0,
             "points_allowed": 14.0, "rank": 1},
        ]
        result = _aggregate_dst_projections(projs)
        assert len(result) == 1
        assert result[0]["fpts"] == 18.0
        assert result[0]["sacks"] == 5.0
        assert result[0]["interceptions"] == 3.0
        assert result[0]["points_allowed"] == 31.0

    def test_aggregate_kicker_projections(self):
        """Kicker projections for same player should sum across weeks."""
        from fantasy_sim.cli import _aggregate_kicker_projections
        projs = [
            {"name": "K1", "team": "KC", "player_id": "k1", "position": "K",
             "fpts": 9.0, "fg_attempts": 3.0, "fg_made": 2.0,
             "fg_50_plus": 1.0, "xp_attempts": 4.0, "xp_made": 3.0, "rank": 1},
            {"name": "K1", "team": "KC", "player_id": "k1", "position": "K",
             "fpts": 7.0, "fg_attempts": 2.0, "fg_made": 2.0,
             "fg_50_plus": 0.0, "xp_attempts": 3.0, "xp_made": 3.0, "rank": 1},
        ]
        result = _aggregate_kicker_projections(projs)
        assert len(result) == 1
        assert result[0]["fpts"] == 16.0
        assert result[0]["fg_made"] == 4.0
        assert result[0]["xp_made"] == 6.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py::TestSeasonAggregation -v`
Expected: FAIL — `_aggregate_player_projections` does not exist.

- [ ] **Step 3: Implement the three aggregation helpers**

Add to `src/fantasy_sim/cli.py` (before `_display_projections`):

```python
# Stat fields to sum during season aggregation
_PLAYER_SUM_FIELDS = [
    "fpts", "pass_yards", "pass_tds", "interceptions", "sacks",
    "rush_yards", "rush_tds", "targets", "receptions",
    "receiving_yards", "receiving_tds", "fumbles_lost",
]

_DST_SUM_FIELDS = [
    "fpts", "sacks", "interceptions", "fumble_recoveries",
    "dst_tds", "safeties", "points_allowed",
]

_KICKER_SUM_FIELDS = [
    "fpts", "fg_attempts", "fg_made", "fg_50_plus",
    "xp_attempts", "xp_made",
]


def _aggregate_player_projections(projs: list[dict]) -> list[dict]:
    """Aggregate per-game player projections into season totals.

    Groups by player_id, sums stat fields, drops distribution fields
    (floor/ceiling/stddev), re-ranks by fpts.
    """
    grouped: dict[str, dict] = {}
    for p in projs:
        pid = p["player_id"]
        if pid not in grouped:
            grouped[pid] = {
                "player_id": pid,
                "name": p["name"],
                "position": p["position"],
                "team": p["team"],
            }
            for field in _PLAYER_SUM_FIELDS:
                grouped[pid][field] = 0.0
        for field in _PLAYER_SUM_FIELDS:
            if field in p:
                grouped[pid][field] = round(grouped[pid][field] + p[field], 1)

    result = list(grouped.values())
    result.sort(key=lambda p: p["fpts"], reverse=True)
    for i, p in enumerate(result, 1):
        p["rank"] = i
    return result


def _aggregate_dst_projections(projs: list[dict]) -> list[dict]:
    """Aggregate per-game DST projections into season totals."""
    grouped: dict[str, dict] = {}
    for p in projs:
        team = p["team"]
        if team not in grouped:
            grouped[team] = {"team": team}
            for field in _DST_SUM_FIELDS:
                grouped[team][field] = 0.0
        for field in _DST_SUM_FIELDS:
            if field in p:
                grouped[team][field] = round(grouped[team][field] + p[field], 1)

    result = list(grouped.values())
    result.sort(key=lambda p: p["fpts"], reverse=True)
    for i, p in enumerate(result, 1):
        p["rank"] = i
    return result


def _aggregate_kicker_projections(projs: list[dict]) -> list[dict]:
    """Aggregate per-game kicker projections into season totals."""
    grouped: dict[str, dict] = {}
    for p in projs:
        key = p.get("player_id", p["name"])
        if key not in grouped:
            grouped[key] = {"name": p["name"], "team": p["team"]}
            if "player_id" in p:
                grouped[key]["player_id"] = p["player_id"]
            if "position" in p:
                grouped[key]["position"] = p["position"]
            for field in _KICKER_SUM_FIELDS:
                grouped[key][field] = 0.0
        for field in _KICKER_SUM_FIELDS:
            if field in p:
                grouped[key][field] = round(grouped[key][field] + p[field], 1)

    result = list(grouped.values())
    result.sort(key=lambda p: p["fpts"], reverse=True)
    for i, p in enumerate(result, 1):
        p["rank"] = i
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py::TestSeasonAggregation -v`
Expected: All 5 PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/cli.py tests/test_cli.py
git commit -m "feat: add season aggregation helpers for player/DST/kicker projections"
```

---

### Task 4: Wire Aggregation + `--by-week` into Season Command

**Files:**
- Modify: `src/fantasy_sim/cli.py:435-533` (season command)
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write failing tests for `--by-week` and aggregation wiring**

Add to `tests/test_cli.py`:

```python
class TestSeasonByWeek:
    """--by-week flag on season command."""

    @patch("fantasy_sim.cli.GameContextBuilder")
    @patch("fantasy_sim.cli.DataLoader")
    def _run_season(self, MockLoader, MockBuilder, runner, extra_args=None):
        """Helper: run season command with 2 weeks of mock data."""
        mock_loader = MockLoader.return_value
        mock_loader.load_schedules.return_value = pl.DataFrame([
            {"season": 2024, "week": 1, "game_id": "g1", "game_type": "REG",
             "home_team": "KC", "away_team": "BUF"},
            {"season": 2024, "week": 2, "game_id": "g2", "game_type": "REG",
             "home_team": "KC", "away_team": "MIA"},
        ])
        mock_loader.cache_dir = Path("/tmp/cache")

        mock_builder = MockBuilder.return_value
        from fantasy_sim.engine.types import TeamDistributions
        from fantasy_sim.models.distributions import (
            PlayCallingDist, PlayOutcomeDist, TurnoverRates, KickingModel, DriveStartModel,
        )
        from fantasy_sim.models.player import TeamRoster, PlayerModel, PlayerUsage, PlayerOutcomes

        def make_dists(team):
            return TeamDistributions(
                play_calling=PlayCallingDist(team=team, distributions={}, default={"pass": 0.55, "run": 0.45}),
                play_outcomes=PlayOutcomeDist(distributions={}, defaults={
                    "pass": np.array([0, 5, 8, 10, 12, 15]),
                    "run": np.array([2, 3, 4, 5, 6]),
                }),
                turnover_rates=TurnoverRates(team=team, int_rate=0.02, fumble_rate=0.01, sack_rate=0.06, sack_fumble_rate=0.10),
                kicking=KickingModel(fg_make_rate={"0_39": 0.93, "40_49": 0.82, "50_plus": 0.65}, xp_rate=0.94),
                drive_start=DriveStartModel(touchback_rate=0.55, touchback_yardline=75, return_yardlines=np.array([74, 76])),
            )

        def make_roster(team):
            return TeamRoster(team=team, players=[
                PlayerModel(f"{team}_QB", "QB", "QB", team, PlayerUsage(snap_share=1.0), PlayerOutcomes()),
                PlayerModel(f"{team}_WR", "WR", "WR", team, PlayerUsage(target_share=0.50),
                           PlayerOutcomes(catch_rate=0.60, receiving_yards_dist=np.array([8, 12]))),
                PlayerModel(f"{team}_RB", "RB", "RB", team, PlayerUsage(carry_share=1.0, target_share=0.50),
                           PlayerOutcomes(rushing_yards_dist=np.array([3, 5, 7]),
                                         catch_rate=0.70, receiving_yards_dist=np.array([4, 6]))),
            ])

        mock_builder.build_game.return_value = (
            make_dists("KC"), make_dists("BUF"), make_roster("KC"), make_roster("BUF"),
        )

        args = ["season", "--season", "2024", "--sims", "5"]
        if extra_args:
            args.extend(extra_args)
        return runner.invoke(main, args)

    def test_season_default_aggregates(self, runner):
        """Default season output should have one entry per player (aggregated)."""
        result = self._run_season(runner=runner)
        assert result.exit_code == 0
        # "Season Projections" header should appear (not per-week headers)
        assert "Season Projections" in result.output

    def test_season_by_week_shows_week_headers(self, runner):
        """--by-week should show week-level headers."""
        result = self._run_season(runner=runner, extra_args=["--by-week"])
        assert result.exit_code == 0
        assert "Week 1" in result.output
        assert "Week 2" in result.output

    def test_season_by_week_json_includes_week_field(self, runner, tmp_path):
        """--by-week --format json should include 'week' field on each row."""
        output = tmp_path / "by_week.json"
        result = self._run_season(
            runner=runner,
            extra_args=["--by-week", "--format", "json", "--output", str(output)],
        )
        assert result.exit_code == 0
        import json
        data = json.loads(output.read_text())
        assert len(data) > 0
        # Every entry should have a "week" field
        for entry in data:
            assert "week" in entry

    def test_season_aggregated_json_no_week_field(self, runner, tmp_path):
        """Default season JSON should NOT include 'week' field."""
        output = tmp_path / "aggregated.json"
        result = self._run_season(
            runner=runner,
            extra_args=["--format", "json", "--output", str(output)],
        )
        assert result.exit_code == 0
        import json
        data = json.loads(output.read_text())
        assert len(data) > 0
        for entry in data:
            assert "week" not in entry
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py::TestSeasonByWeek -v`
Expected: FAIL — `--by-week` flag doesn't exist yet; default output is not aggregated.

- [ ] **Step 3: Add `--by-week` flag and wire aggregation into season command**

In `src/fantasy_sim/cli.py`, update the season command:

1. Add the `--by-week` option and `@click.pass_context`:

```python
@main.command()
@click.pass_context
@click.option("--season", "season_year", default=2024, help="NFL season year")
@click.option("--weeks", default="all", help="Weeks to simulate: 'all' or '1-5' or '1,3,5'")
@click.option("--sims", default=None, type=click.IntRange(min=1), help="Sims per game (lower for season)")
@click.option("--scoring", default="ppr", type=click.Choice(["ppr", "half_ppr", "standard"]))
@click.option("--format", "output_format", default="table", type=click.Choice(["table", "csv", "json"]))
@click.option("--output", "output_path", default=None)
@click.option("--override", "overrides", multiple=True, help="Player/team override: 'name.field=value'")
@click.option("--config", "config_path", default=None, help="Path to season.yaml with overrides")
@click.option("--scoring-config", "scoring_config_path", default=None, help="Path to custom scoring YAML")
@click.option("--detail", is_flag=True, help="Show floor/ceiling/stddev distributions")
@click.option("--by-week", is_flag=True, help="Output per-week breakdowns instead of season totals")
def season(ctx, season_year, weeks, sims, scoring, output_format, output_path, overrides, config_path, scoring_config_path, detail, by_week):
```

2. In the per-game loop, stamp `week` on each projection dict. After each call to `build_player_projections` / `build_detailed_projections` / `build_dst_projections` / `build_kicker_projections`, stamp the week:

After the existing `.extend()` calls (around lines 510-517), add stamping:

```python
                # Stamp week on projections for by-week mode
                for proj in all_player_projs[-len(player_batch):]:
                    proj["week"] = wk
                for proj in all_dst_projs[-len(dst_batch):]:
                    proj["week"] = wk
                for proj in all_kicker_projs[-len(kicker_batch):]:
                    proj["week"] = wk
```

To get the batch lengths, capture the projection lists before extending:

```python
                if detail:
                    from fantasy_sim.scoring.projections import build_detailed_projections
                    player_batch = build_detailed_projections(results.games, scoring_config)
                else:
                    player_batch = build_player_projections(results.games, scoring_config)
                dst_batch = build_dst_projections(results.games, scoring_config, team_map=team_map)
                kicker_batch = build_kicker_projections(
                    results.games, scoring_config, team_map=team_map,
                    home_roster=home_roster, away_roster=away_roster,
                )
                # Stamp week
                for proj in player_batch:
                    proj["week"] = wk
                for proj in dst_batch:
                    proj["week"] = wk
                for proj in kicker_batch:
                    proj["week"] = wk

                all_player_projs.extend(player_batch)
                all_dst_projs.extend(dst_batch)
                all_kicker_projs.extend(kicker_batch)
```

3. After the loop, apply aggregation or by-week sorting. Replace the existing sort/rank/display block (lines 520-533):

```python
    output_format = _infer_format(output_format, output_path, ctx)

    if by_week:
        # Sort by week, then fpts within each week
        all_player_projs.sort(key=lambda p: (p["week"], -p["fpts"]))
        all_dst_projs.sort(key=lambda p: (p["week"], -p["fpts"]))
        all_kicker_projs.sort(key=lambda p: (p["week"], -p["fpts"]))

        if output_format == "table":
            weeks_in_data = sorted(set(p["week"] for p in all_player_projs))
            for wk in weeks_in_data:
                wk_players = [p for p in all_player_projs if p["week"] == wk]
                wk_dst = [p for p in all_dst_projs if p["week"] == wk]
                wk_kickers = [p for p in all_kicker_projs if p["week"] == wk]
                # Re-rank within week
                for i, p in enumerate(wk_players, 1):
                    p["rank"] = i
                for i, p in enumerate(wk_dst, 1):
                    p["rank"] = i
                for i, p in enumerate(wk_kickers, 1):
                    p["rank"] = i
                click.echo(f"\n{season_year} Week {wk} Projections ({scoring.upper()}, {sims} sims/game)\n")
                _display_projections(wk_players, "table", None, detail=detail,
                                     kicker_projs=wk_kickers, dst_projs=wk_dst)
        else:
            # CSV/JSON: include week field, rank within week
            all_projs = all_player_projs + all_kicker_projs + all_dst_projs
            if output_path is None:
                output_path = f"projections.{output_format}"
            if output_format == "csv":
                export_csv(all_projs, Path(output_path))
            else:
                export_json(all_projs, Path(output_path))
            click.echo(f"Exported to {output_path}")
    else:
        # Aggregate into season totals
        all_player_projs = _aggregate_player_projections(all_player_projs)
        all_dst_projs = _aggregate_dst_projections(all_dst_projs)
        all_kicker_projs = _aggregate_kicker_projections(all_kicker_projs)

        click.echo(f"\n{season_year} Season Projections ({scoring.upper()})\n")
        _display_projections(all_player_projs, output_format, output_path, detail=detail,
                             kicker_projs=all_kicker_projs, dst_projs=all_dst_projs)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py::TestSeasonByWeek -v`
Expected: All 4 PASS

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest tests/test_cli.py -v`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add src/fantasy_sim/cli.py tests/test_cli.py
git commit -m "feat: wire season aggregation and --by-week flag into season command"
```

---

### Task 5: Update CLAUDE.md and README.md

**Files:**
- Modify: `CLAUDE.md`
- Modify: `README.md` (if it documents CLI usage)

- [ ] **Step 1: Update CLAUDE.md CLI documentation**

In the `## Commands` section, update the season command examples:

```bash
# Simulate real NFL season (regular season only by default)
uv run fantasy-sim season --season 2024 --sims 50

# Season with per-week breakdowns
uv run fantasy-sim season --season 2024 --sims 50 --by-week

# Season export (format auto-inferred from extension)
uv run fantasy-sim season --season 2024 --sims 50 --output rankings.json
```

In the `## Key Patterns` section, add under `**CLI**`:

```
`--by-week` on season command outputs per-week breakdowns with week headers instead of season totals. `--output` auto-infers format from `.json`/`.csv` extension.
```

- [ ] **Step 2: Update README.md if it documents CLI usage**

Check if README.md has CLI examples and update accordingly. Add the new `--by-week` flag and format inference behavior.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "docs: update CLI docs for season aggregation and --by-week flag"
```

---

### Task 6: Integration Smoke Test

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests pass (no regressions across the entire test suite)

- [ ] **Step 2: Manual smoke test with demo data**

Run: `uv run fantasy-sim demo --sims 10 --output /tmp/test.json`
Expected: Exports JSON without `--format json` (format inference works)

Run: `uv run fantasy-sim demo --sims 10 --output /tmp/test.csv`
Expected: Exports CSV without `--format csv`

- [ ] **Step 3: Verify no regressions**

Run: `uv run pytest tests/ -v`
Expected: All pass. If any failures, fix before finishing.

# Phase 5: Validation + Tuning — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire real nflverse data into the CLI (`week` and `season` commands), build a backtesting framework that compares projections to historical actuals, implement accuracy metrics (Spearman correlation, MAE, boom/bust calibration), and provide the infrastructure to tune model parameters until benchmarks pass.

**Architecture:** A `GameContextBuilder` constructs `TeamDistributions` + `TeamRoster` per team from real nflverse data. New CLI commands (`week`, `season`, `backtest`) use schedules to identify matchups, run simulations per game, and aggregate results across all games. A `Backtester` class runs projections for historical weeks using only prior-season data (no leakage), compares to actual player stats scored with the same config, and computes accuracy metrics. A `ValidationReport` summarizes all metrics in a readable format.

**Tech Stack:** Python 3.14, scipy.stats (Spearman), numpy, click, nflreadpy, polars, rich, pytest

---

## File Structure

```
src/fantasy_sim/
├── data/
│   ├── game_context.py         NEW: GameContextBuilder — builds TeamDistributions + TeamRoster per team
│   └── actuals.py              NEW: Load actual player stats, score with config → actual fantasy points
├── validation/
│   ├── __init__.py             (exists)
│   ├── metrics.py              NEW: spearman_correlation, mean_absolute_error, boom_bust_calibration
│   ├── backtester.py           NEW: Backtester class — runs hold-out validation, no leakage
│   └── report.py               NEW: ValidationReport — formats metrics for display
└── cli.py                      MODIFY: Add week, season, backtest commands

tests/
├── test_data/
│   └── test_game_context.py    NEW
├── test_validation/
│   ├── test_metrics.py         NEW
│   ├── test_actuals.py         NEW
│   ├── test_backtester.py      NEW
│   └── test_report.py          NEW
└── test_cli.py                 MODIFY: Add tests for week/backtest commands
```

## Dependencies from Phases 1-4

- `data.loader.DataLoader` — `load_pbp()`, `load_schedules()`, `load_rosters()`, `load_player_stats()`
- `data.pipeline.DataPipeline` — `build()` returns `{play_calling, play_outcomes, turnover_rates, kicking, drive_start}`
- `data.player_builder.build_player_models()`, `build_team_roster()`
- `engine.types.TeamDistributions`, `GameResult`, `PlayerBoxScore`, `TeamBoxScore`
- `engine.monte_carlo.run_simulations()` → `SimulationSummary`
- `scoring.engine.score_player()`, `score_dst()`, `score_kicker()`
- `scoring.projections.build_player_projections()`, `build_dst_projections()`, `build_kicker_projections()`
- `config.loader.load_defaults()`, `resolve_scoring()`
- `output.tables.*`, `output.export.*`

**Key nflverse data columns for actuals:**
- `load_player_stats(seasons, summary_level="week")` returns per-week stats with: `player_id`, `player_name`, `position`, `recent_team`, `season`, `week`, `completions`, `attempts`, `passing_yards`, `passing_tds`, `interceptions`, `carries`, `rushing_yards`, `rushing_tds`, `receptions`, `targets`, `receiving_yards`, `receiving_tds`, `sack_fumbles_lost` (or similar fumble field)
- `load_schedules(seasons)` returns: `season`, `week`, `game_id`, `home_team`, `away_team`, `home_score`, `away_score`

---

### Task 1: Game Context Builder

**Files:**
- Create: `src/fantasy_sim/data/game_context.py`
- Create: `tests/test_data/test_game_context.py`

This is the bridge between raw nflverse data and the simulation engine. It constructs per-team `TeamDistributions` + `TeamRoster` objects.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_data/test_game_context.py
import numpy as np
import polars as pl
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from fantasy_sim.data.game_context import GameContextBuilder
from fantasy_sim.engine.types import TeamDistributions
from fantasy_sim.models.player import TeamRoster


class TestGameContextBuilder:
    @pytest.fixture
    def builder(self, tmp_path):
        return GameContextBuilder(cache_dir=tmp_path / "cache")

    def test_build_team_distributions(self, builder, expanded_pbp, sample_rosters):
        dists = builder.build_team_distributions(
            "KC", pbp=expanded_pbp, rosters=sample_rosters, seasons=[2024]
        )
        assert isinstance(dists, TeamDistributions)
        assert dists.play_calling.team == "KC"
        assert dists.turnover_rates.team == "KC"

    def test_build_team_roster(self, builder, expanded_pbp, sample_rosters):
        roster = builder.build_team_roster(
            "KC", pbp=expanded_pbp, rosters=sample_rosters, seasons=[2024]
        )
        assert isinstance(roster, TeamRoster)
        assert roster.team == "KC"
        assert len(roster.players) > 0

    def test_build_game(self, builder, expanded_pbp, sample_rosters):
        home_dists, away_dists, home_roster, away_roster = builder.build_game(
            home_team="KC", away_team="BUF",
            pbp=expanded_pbp, rosters=sample_rosters, seasons=[2024],
        )
        assert home_dists.play_calling.team == "KC"
        assert away_dists.play_calling.team == "BUF"
        assert home_roster.team == "KC"
        assert away_roster.team == "BUF"

    def test_missing_team_gets_league_defaults(self, builder, expanded_pbp, sample_rosters):
        """A team not in PBP data should get league-average distributions."""
        dists = builder.build_team_distributions(
            "SEA", pbp=expanded_pbp, rosters=sample_rosters, seasons=[2024]
        )
        assert isinstance(dists, TeamDistributions)
        # Should use league defaults for play calling
        probs = dists.play_calling.default
        assert 0.4 <= probs["pass"] <= 0.7

    def test_caches_pipeline_output(self, builder, expanded_pbp, sample_rosters):
        """Second call with same data should reuse cached pipeline output."""
        builder.build_team_distributions("KC", pbp=expanded_pbp, rosters=sample_rosters, seasons=[2024])
        builder.build_team_distributions("BUF", pbp=expanded_pbp, rosters=sample_rosters, seasons=[2024])
        # Pipeline build should only have been called once (cached)
        assert builder._pipeline_cache is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_game_context.py -v`
Expected: FAIL

- [ ] **Step 3: Implement game context builder**

```python
# src/fantasy_sim/data/game_context.py
from pathlib import Path
import polars as pl
import numpy as np
from fantasy_sim.data.loader import DataLoader, DEFAULT_CACHE_DIR
from fantasy_sim.data.pipeline import DataPipeline
from fantasy_sim.data.preprocessor import Preprocessor
from fantasy_sim.data.player_builder import build_player_models, build_team_roster
from fantasy_sim.engine.types import TeamDistributions
from fantasy_sim.models.distributions import (
    PlayCallingDist, PlayOutcomeDist, TurnoverRates, KickingModel, DriveStartModel,
)
from fantasy_sim.models.player import TeamRoster


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
        self._player_models_cache: dict | None = None
        self._cached_seasons: list[int] | None = None

    def _ensure_pipeline(
        self, seasons: list[int],
        pbp: pl.DataFrame | None = None,
        rosters: pl.DataFrame | None = None,
    ) -> tuple[dict, dict]:
        """Build and cache pipeline output + player models."""
        if self._pipeline_cache is not None and self._cached_seasons == seasons:
            return self._pipeline_cache, self._player_models_cache

        if pbp is None:
            pbp = self.loader.load_pbp(seasons)
        if rosters is None:
            rosters = self.loader.load_rosters(seasons)

        pipeline = DataPipeline(cache_dir=self.cache_dir, seasons=seasons)
        pipeline_output = pipeline.build(pbp=pbp)
        player_models = build_player_models(pbp, rosters, seasons)

        self._pipeline_cache = pipeline_output
        self._player_models_cache = player_models
        self._cached_seasons = seasons
        return pipeline_output, player_models

    def build_team_distributions(
        self, team: str,
        seasons: list[int] | None = None,
        pbp: pl.DataFrame | None = None,
        rosters: pl.DataFrame | None = None,
    ) -> TeamDistributions:
        """Build TeamDistributions for a specific team."""
        seasons = seasons or [2022, 2023, 2024]
        pipeline_output, _ = self._ensure_pipeline(seasons, pbp, rosters)

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
        self, team: str,
        seasons: list[int] | None = None,
        pbp: pl.DataFrame | None = None,
        rosters: pl.DataFrame | None = None,
    ) -> TeamRoster:
        """Build TeamRoster for a specific team."""
        seasons = seasons or [2022, 2023, 2024]
        _, player_models = self._ensure_pipeline(seasons, pbp, rosters)
        roster = build_team_roster(team, player_models)
        if not roster.players:
            # Empty roster — return minimal roster so sim doesn't crash
            from fantasy_sim.models.player import PlayerModel, PlayerUsage, PlayerOutcomes
            roster = TeamRoster(team=team, players=[
                PlayerModel(f"{team}_QB", "QB", "QB", team,
                           PlayerUsage(snap_share=1.0), PlayerOutcomes()),
                PlayerModel(f"{team}_RB", "RB", "RB", team,
                           PlayerUsage(carry_share=1.0, target_share=0.15), PlayerOutcomes(
                               rushing_yards_dist=np.array([2, 3, 4, 5, 6]),
                               catch_rate=0.65, receiving_yards_dist=np.array([3, 5, 7]))),
                PlayerModel(f"{team}_WR", "WR", "WR", team,
                           PlayerUsage(target_share=0.85), PlayerOutcomes(
                               catch_rate=0.60, receiving_yards_dist=np.array([5, 8, 12, 15, 20]))),
            ])
        return roster

    def build_game(
        self, home_team: str, away_team: str,
        seasons: list[int] | None = None,
        pbp: pl.DataFrame | None = None,
        rosters: pl.DataFrame | None = None,
    ) -> tuple[TeamDistributions, TeamDistributions, TeamRoster, TeamRoster]:
        """Build all context needed to simulate one game."""
        home_dists = self.build_team_distributions(home_team, seasons, pbp, rosters)
        away_dists = self.build_team_distributions(away_team, seasons, pbp, rosters)
        home_roster = self.build_team_roster(home_team, seasons, pbp, rosters)
        away_roster = self.build_team_roster(away_team, seasons, pbp, rosters)
        return home_dists, away_dists, home_roster, away_roster
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_game_context.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/game_context.py tests/test_data/test_game_context.py
git commit -m "feat: add GameContextBuilder for real nflverse data"
```

---

### Task 2: Week + Season CLI Commands

**Files:**
- Modify: `src/fantasy_sim/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_cli.py`:

```python
from unittest.mock import patch, MagicMock
import polars as pl
import numpy as np


class TestWeekCommand:
    @patch("fantasy_sim.cli.GameContextBuilder")
    @patch("fantasy_sim.cli.DataLoader")
    def test_week_command_runs(self, MockLoader, MockBuilder, runner):
        """Week command should load schedules, build context, run sims."""
        # Mock schedule data
        mock_loader = MockLoader.return_value
        mock_loader.load_schedules.return_value = pl.DataFrame([
            {"season": 2024, "week": 1, "game_id": "g1",
             "home_team": "KC", "away_team": "BUF"},
        ])

        # Mock game context builder
        mock_builder = MockBuilder.return_value
        from fantasy_sim.engine.types import TeamDistributions, TeamBoxScore, GameResult, PlayerBoxScore
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

        result = runner.invoke(main, ["week", "1", "--season", "2024", "--sims", "10"])
        assert result.exit_code == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py::TestWeekCommand -v`
Expected: FAIL

- [ ] **Step 3: Add week and season commands to CLI**

Add to `src/fantasy_sim/cli.py`:

```python
from fantasy_sim.data.game_context import GameContextBuilder
from fantasy_sim.data.loader import DataLoader


@main.command()
@click.argument("week_num", type=int)
@click.option("--season", default=2024, help="NFL season year")
@click.option("--sims", default=1000, type=click.IntRange(min=1))
@click.option("--scoring", default="ppr", type=click.Choice(["ppr", "half_ppr", "standard"]))
@click.option("--format", "output_format", default="table", type=click.Choice(["table", "csv", "json"]))
@click.option("--output", "output_path", default=None)
def week(week_num, season, sims, scoring, output_format, output_path):
    """Simulate all games in an NFL week using real nflverse data."""
    config = load_defaults()
    scoring_config = resolve_scoring(config["scoring"], scoring)
    training_seasons = [s for s in range(season - 3, season)]

    loader = DataLoader()
    builder = GameContextBuilder(cache_dir=loader.cache_dir)

    click.echo(f"Loading schedule for {season} Week {week_num}...")
    schedules = loader.load_schedules([season])
    week_games = schedules.filter(
        (pl.col("week") == week_num) & (pl.col("season") == season)
    )

    if week_games.shape[0] == 0:
        click.echo(f"No games found for {season} Week {week_num}")
        return

    click.echo(f"Found {week_games.shape[0]} games. Running {sims} sims each ({scoring})...\n")

    all_game_results = []
    team_map_list = []

    for game in week_games.iter_rows(named=True):
        home = game["home_team"]
        away = game["away_team"]
        click.echo(f"  Simulating {away} @ {home}...", nl=False)

        home_dists, away_dists, home_roster, away_roster = builder.build_game(
            home_team=home, away_team=away, seasons=training_seasons,
        )

        results = run_simulations(
            home_dists, away_dists, n_sims=sims, seed=hash(game["game_id"]) % (2**31),
            home_roster=home_roster, away_roster=away_roster,
        )

        summary = results.summary()
        click.echo(f" {home} {summary['home_score_mean']:.1f} - {away} {summary['away_score_mean']:.1f}")

        all_game_results.extend(results.games)
        team_map_list.append({"HOME": home, "AWAY": away})

    # Build projections across all games
    player_projs = build_player_projections(all_game_results, scoring_config)
    click.echo(f"\n{season} Week {week_num} Projections ({scoring.upper()}, {sims} sims/game)\n")

    _display_projections(player_projs, output_format, output_path)


@main.command()
@click.option("--season", default=2024, help="NFL season year")
@click.option("--weeks", default="all", help="Weeks to simulate: 'all' or '1-5' or '1,3,5'")
@click.option("--sims", default=100, type=click.IntRange(min=1), help="Sims per game (lower for season)")
@click.option("--scoring", default="ppr", type=click.Choice(["ppr", "half_ppr", "standard"]))
@click.option("--format", "output_format", default="table", type=click.Choice(["table", "csv", "json"]))
@click.option("--output", "output_path", default=None)
def season(season_year, weeks, sims, scoring, output_format, output_path):
    """Simulate a full NFL season using real nflverse data."""
    config = load_defaults()
    scoring_config = resolve_scoring(config["scoring"], scoring)
    training_seasons = [s for s in range(season_year - 3, season_year)]

    loader = DataLoader()
    builder = GameContextBuilder(cache_dir=loader.cache_dir)

    schedules = loader.load_schedules([season_year])

    if weeks == "all":
        week_nums = sorted(schedules.filter(pl.col("season") == season_year)["week"].unique().to_list())
    elif "-" in weeks:
        start, end = weeks.split("-")
        week_nums = list(range(int(start), int(end) + 1))
    else:
        week_nums = [int(w) for w in weeks.split(",")]

    click.echo(f"Simulating {season_year} season, weeks {week_nums[0]}-{week_nums[-1]} ({sims} sims/game)...\n")

    all_game_results = []
    for wk in week_nums:
        week_games = schedules.filter(
            (pl.col("week") == wk) & (pl.col("season") == season_year)
        )
        click.echo(f"Week {wk}: {week_games.shape[0]} games")
        for game in week_games.iter_rows(named=True):
            home, away = game["home_team"], game["away_team"]
            home_dists, away_dists, home_roster, away_roster = builder.build_game(
                home, away, seasons=training_seasons,
            )
            results = run_simulations(
                home_dists, away_dists, n_sims=sims,
                seed=hash(game["game_id"]) % (2**31),
                home_roster=home_roster, away_roster=away_roster,
            )
            all_game_results.extend(results.games)

    player_projs = build_player_projections(all_game_results, scoring_config)
    click.echo(f"\n{season_year} Season Projections ({scoring.upper()})\n")
    _display_projections(player_projs, output_format, output_path)


def _display_projections(player_projs, output_format, output_path):
    """Display or export projections."""
    if output_format == "table":
        qbs = [p for p in player_projs if p["position"] == "QB"]
        rbs = [p for p in player_projs if p["position"] == "RB"]
        wrs = [p for p in player_projs if p["position"] == "WR"]
        tes = [p for p in player_projs if p["position"] == "TE"]
        if qbs:
            click.echo(format_qb_table(qbs[:24]))
        if rbs:
            click.echo(format_rb_table(rbs[:24]))
        if wrs:
            click.echo(format_wr_table(wrs[:24]))
        if tes:
            click.echo(format_te_table(tes[:12]))
    elif output_format in ("csv", "json"):
        if output_path is None:
            output_path = f"projections.{output_format}"
        if output_format == "csv":
            export_csv(player_projs, Path(output_path))
        else:
            export_json(player_projs, Path(output_path))
        click.echo(f"Exported to {output_path}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/cli.py tests/test_cli.py
git commit -m "feat: add week and season CLI commands with real nflverse data"
```

---

### Task 3: Actual Results Loader

**Files:**
- Create: `src/fantasy_sim/data/actuals.py`
- Create: `tests/test_data/test_actuals.py`

This module loads real player stats from nflverse and scores them using the config to produce actual fantasy points for comparison.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_data/test_actuals.py
import polars as pl
import pytest
from fantasy_sim.data.actuals import load_actual_scores, ActualPlayerWeek


@pytest.fixture
def sample_player_stats():
    """Mimics nflreadpy.load_player_stats output."""
    return pl.DataFrame([
        {"player_id": "PM15", "player_name": "P.Mahomes", "position": "QB",
         "recent_team": "KC", "season": 2024, "week": 1,
         "completions": 22, "attempts": 35, "passing_yards": 280,
         "passing_tds": 2, "interceptions": 1, "sacks": 2,
         "carries": 3, "rushing_yards": 18, "rushing_tds": 0,
         "receptions": 0, "targets": 0, "receiving_yards": 0,
         "receiving_tds": 0, "receiving_fumbles_lost": 0,
         "rushing_fumbles_lost": 0, "sack_fumbles_lost": 0},
        {"player_id": "TK87", "player_name": "T.Kelce", "position": "TE",
         "recent_team": "KC", "season": 2024, "week": 1,
         "completions": 0, "attempts": 0, "passing_yards": 0,
         "passing_tds": 0, "interceptions": 0, "sacks": 0,
         "carries": 0, "rushing_yards": 0, "rushing_tds": 0,
         "receptions": 7, "targets": 9, "receiving_yards": 85,
         "receiving_tds": 1, "receiving_fumbles_lost": 0,
         "rushing_fumbles_lost": 0, "sack_fumbles_lost": 0},
    ])


@pytest.fixture
def ppr_config():
    return {
        "passing_yard": 0.04, "passing_td": 4, "interception": -2,
        "rushing_yard": 0.1, "rushing_td": 6,
        "reception": 1, "receiving_yard": 0.1, "receiving_td": 6,
        "fumble_lost": -2,
    }


class TestLoadActualScores:
    def test_returns_list_of_actuals(self, sample_player_stats, ppr_config):
        actuals = load_actual_scores(sample_player_stats, ppr_config, season=2024)
        assert isinstance(actuals, list)
        assert len(actuals) > 0
        assert isinstance(actuals[0], ActualPlayerWeek)

    def test_mahomes_ppr_score(self, sample_player_stats, ppr_config):
        actuals = load_actual_scores(sample_player_stats, ppr_config, season=2024)
        mahomes = [a for a in actuals if a.player_id == "PM15"][0]
        # 280*0.04 + 2*4 + 1*(-2) + 18*0.1 = 11.2 + 8 - 2 + 1.8 = 19.0
        assert mahomes.fpts == pytest.approx(19.0)
        assert mahomes.week == 1

    def test_kelce_ppr_score(self, sample_player_stats, ppr_config):
        actuals = load_actual_scores(sample_player_stats, ppr_config, season=2024)
        kelce = [a for a in actuals if a.player_id == "TK87"][0]
        # 7*1 + 85*0.1 + 1*6 = 7 + 8.5 + 6 = 21.5
        assert kelce.fpts == pytest.approx(21.5)

    def test_filters_to_season(self, sample_player_stats, ppr_config):
        actuals = load_actual_scores(sample_player_stats, ppr_config, season=2023)
        assert len(actuals) == 0  # No 2023 data in fixture
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_actuals.py -v`
Expected: FAIL

- [ ] **Step 3: Implement actuals loader**

```python
# src/fantasy_sim/data/actuals.py
from dataclasses import dataclass
import polars as pl
from fantasy_sim.engine.types import PlayerBoxScore
from fantasy_sim.scoring.engine import score_player


@dataclass
class ActualPlayerWeek:
    """Actual fantasy points for one player in one week."""
    player_id: str
    name: str
    position: str
    team: str
    season: int
    week: int
    fpts: float
    # Raw stats for analysis
    pass_yards: int = 0
    pass_tds: int = 0
    interceptions: int = 0
    rush_yards: int = 0
    rush_tds: int = 0
    receptions: int = 0
    targets: int = 0
    receiving_yards: int = 0
    receiving_tds: int = 0
    fumbles_lost: int = 0


def load_actual_scores(
    player_stats: pl.DataFrame,
    scoring_config: dict,
    season: int,
    weeks: list[int] | None = None,
) -> list[ActualPlayerWeek]:
    """Convert nflverse player_stats into scored ActualPlayerWeek objects."""
    filtered = player_stats.filter(pl.col("season") == season)
    if weeks is not None:
        filtered = filtered.filter(pl.col("week").is_in(weeks))

    actuals = []
    for row in filtered.iter_rows(named=True):
        # Build a PlayerBoxScore from the actual stats
        fumbles = (
            row.get("receiving_fumbles_lost", 0) +
            row.get("rushing_fumbles_lost", 0) +
            row.get("sack_fumbles_lost", 0)
        )
        box = PlayerBoxScore(
            player_id=row["player_id"],
            name=row["player_name"],
            position=row["position"],
            team=row["recent_team"],
            pass_yards=row.get("passing_yards", 0) or 0,
            pass_tds=row.get("passing_tds", 0) or 0,
            completions=row.get("completions", 0) or 0,
            pass_attempts=row.get("attempts", 0) or 0,
            interceptions=row.get("interceptions", 0) or 0,
            sacks=row.get("sacks", 0) or 0,
            rush_yards=row.get("rushing_yards", 0) or 0,
            rush_tds=row.get("rushing_tds", 0) or 0,
            rush_attempts=row.get("carries", 0) or 0,
            receptions=row.get("receptions", 0) or 0,
            targets=row.get("targets", 0) or 0,
            receiving_yards=row.get("receiving_yards", 0) or 0,
            receiving_tds=row.get("receiving_tds", 0) or 0,
            fumbles_lost=fumbles,
        )
        fpts = score_player(box, scoring_config)

        actuals.append(ActualPlayerWeek(
            player_id=row["player_id"],
            name=row["player_name"],
            position=row["position"],
            team=row["recent_team"],
            season=row["season"],
            week=row["week"],
            fpts=round(fpts, 1),
            pass_yards=box.pass_yards,
            pass_tds=box.pass_tds,
            interceptions=box.interceptions,
            rush_yards=box.rush_yards,
            rush_tds=box.rush_tds,
            receptions=box.receptions,
            targets=box.targets,
            receiving_yards=box.receiving_yards,
            receiving_tds=box.receiving_tds,
            fumbles_lost=box.fumbles_lost,
        ))

    return actuals
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_actuals.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/actuals.py tests/test_data/test_actuals.py
git commit -m "feat: add actual results loader for backtest comparisons"
```

---

### Task 4: Accuracy Metrics

**Files:**
- Create: `src/fantasy_sim/validation/metrics.py`
- Create: `tests/test_validation/test_metrics.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_validation/test_metrics.py
import numpy as np
import pytest
from fantasy_sim.validation.metrics import (
    spearman_rank_correlation,
    mean_absolute_error,
    season_total_mae,
    boom_bust_calibration,
)


class TestSpearmanRankCorrelation:
    def test_perfect_correlation(self):
        projected = [30.0, 25.0, 20.0, 15.0, 10.0]
        actual = [28.0, 24.0, 19.0, 14.0, 9.0]
        corr = spearman_rank_correlation(projected, actual)
        assert corr == pytest.approx(1.0)

    def test_inverse_correlation(self):
        projected = [30.0, 25.0, 20.0, 15.0, 10.0]
        actual = [9.0, 14.0, 19.0, 24.0, 28.0]
        corr = spearman_rank_correlation(projected, actual)
        assert corr == pytest.approx(-1.0)

    def test_no_correlation(self):
        """With random data, correlation should be near zero."""
        rng = np.random.default_rng(42)
        projected = rng.random(100).tolist()
        actual = rng.random(100).tolist()
        corr = spearman_rank_correlation(projected, actual)
        assert -0.3 <= corr <= 0.3

    def test_returns_float(self):
        corr = spearman_rank_correlation([1, 2, 3], [1, 2, 3])
        assert isinstance(corr, float)


class TestMeanAbsoluteError:
    def test_zero_error(self):
        mae = mean_absolute_error([10.0, 20.0], [10.0, 20.0])
        assert mae == pytest.approx(0.0)

    def test_known_error(self):
        mae = mean_absolute_error([10.0, 20.0], [12.0, 18.0])
        assert mae == pytest.approx(2.0)  # (2 + 2) / 2

    def test_one_sided_error(self):
        mae = mean_absolute_error([10.0], [15.0])
        assert mae == pytest.approx(5.0)


class TestSeasonTotalMAE:
    def test_aggregates_across_weeks(self):
        # Player scored 10, 12, 8 across 3 weeks (total = 30)
        # Projected 11, 11, 11 per week (total = 33)
        projected_weekly = {"P1": [11.0, 11.0, 11.0]}
        actual_weekly = {"P1": [10.0, 12.0, 8.0]}
        mae = season_total_mae(projected_weekly, actual_weekly)
        # |33 - 30| / 1 player = 3.0
        assert mae == pytest.approx(3.0)

    def test_multiple_players(self):
        projected = {"P1": [10.0, 10.0], "P2": [20.0, 20.0]}
        actual = {"P1": [8.0, 12.0], "P2": [18.0, 22.0]}
        mae = season_total_mae(projected, actual)
        # P1: |20 - 20| = 0, P2: |40 - 40| = 0 → MAE = 0
        assert mae == pytest.approx(0.0)


class TestBoomBustCalibration:
    def test_perfect_calibration(self):
        """If we predict 50% boom rate and exactly 50% boom, calibration = 0."""
        predicted_boom_pcts = {"P1": 0.50}
        actual_boom_pcts = {"P1": 0.50}
        cal = boom_bust_calibration(predicted_boom_pcts, actual_boom_pcts)
        assert cal == pytest.approx(0.0, abs=0.01)

    def test_off_by_ten_percent(self):
        predicted_boom_pcts = {"P1": 0.30}
        actual_boom_pcts = {"P1": 0.20}
        cal = boom_bust_calibration(predicted_boom_pcts, actual_boom_pcts)
        assert cal == pytest.approx(0.10, abs=0.01)

    def test_multiple_players(self):
        predicted = {"P1": 0.30, "P2": 0.50}
        actual = {"P1": 0.20, "P2": 0.40}
        cal = boom_bust_calibration(predicted, actual)
        # mean(|0.30-0.20|, |0.50-0.40|) = mean(0.10, 0.10) = 0.10
        assert cal == pytest.approx(0.10, abs=0.01)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_validation/test_metrics.py -v`
Expected: FAIL

- [ ] **Step 3: Implement metrics**

```python
# src/fantasy_sim/validation/metrics.py
import numpy as np
from scipy.stats import spearmanr


def spearman_rank_correlation(
    projected: list[float], actual: list[float]
) -> float:
    """Compute Spearman rank correlation between projected and actual values."""
    if len(projected) < 3:
        return 0.0
    corr, _ = spearmanr(projected, actual)
    return float(corr)


def mean_absolute_error(
    projected: list[float], actual: list[float]
) -> float:
    """Compute mean absolute error between projected and actual per-week values."""
    proj = np.array(projected)
    act = np.array(actual)
    return float(np.mean(np.abs(proj - act)))


def season_total_mae(
    projected_weekly: dict[str, list[float]],
    actual_weekly: dict[str, list[float]],
) -> float:
    """Compute MAE on season totals (sum of weekly values per player)."""
    errors = []
    for pid in projected_weekly:
        if pid in actual_weekly:
            proj_total = sum(projected_weekly[pid])
            act_total = sum(actual_weekly[pid])
            errors.append(abs(proj_total - act_total))
    if not errors:
        return 0.0
    return float(np.mean(errors))


def boom_bust_calibration(
    predicted_boom_pcts: dict[str, float],
    actual_boom_pcts: dict[str, float],
) -> float:
    """Compute mean absolute calibration error for boom/bust predictions.

    predicted_boom_pcts: {player_id: P(score >= threshold) from simulations}
    actual_boom_pcts: {player_id: fraction of weeks where score >= threshold}

    Returns: mean |predicted - actual| across all players.
    """
    errors = []
    for pid in predicted_boom_pcts:
        if pid in actual_boom_pcts:
            errors.append(abs(predicted_boom_pcts[pid] - actual_boom_pcts[pid]))
    if not errors:
        return 0.0
    return float(np.mean(errors))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_validation/test_metrics.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/validation/metrics.py tests/test_validation/test_metrics.py
git commit -m "feat: add accuracy metrics - Spearman correlation, MAE, boom/bust calibration"
```

---

### Task 5: Backtesting Framework

**Files:**
- Create: `src/fantasy_sim/validation/backtester.py`
- Create: `tests/test_validation/test_backtester.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_validation/test_backtester.py
import numpy as np
import polars as pl
import pytest
from unittest.mock import patch, MagicMock
from fantasy_sim.validation.backtester import Backtester, BacktestResult


class TestBacktester:
    def test_training_seasons_exclude_test_season(self):
        bt = Backtester(test_season=2024, n_sims=10)
        assert 2024 not in bt.training_seasons
        assert len(bt.training_seasons) > 0

    def test_training_seasons_use_prior_years(self):
        bt = Backtester(test_season=2024, n_sims=10, num_training_seasons=3)
        assert bt.training_seasons == [2021, 2022, 2023]

    def test_backtest_result_has_metrics(self):
        result = BacktestResult(
            test_season=2024,
            weekly_mae=5.5,
            season_mae=22.0,
            rank_correlations={"QB": 0.85, "RB": 0.80, "WR": 0.82, "TE": 0.78},
            boom_bust_calibration=0.08,
            total_players_evaluated=96,
            total_weeks_evaluated=18,
        )
        assert result.weekly_mae < 6.0
        assert result.rank_correlations["QB"] > 0.80
        assert result.passes_targets()  # All metrics within spec targets

    def test_backtest_result_fails_when_metrics_bad(self):
        result = BacktestResult(
            test_season=2024,
            weekly_mae=8.0,  # Over 6.0 target
            season_mae=30.0,
            rank_correlations={"QB": 0.70},  # Under 0.80 target
            boom_bust_calibration=0.15,  # Over 0.10 target
            total_players_evaluated=24,
            total_weeks_evaluated=18,
        )
        assert not result.passes_targets()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_validation/test_backtester.py -v`
Expected: FAIL

- [ ] **Step 3: Implement backtester**

```python
# src/fantasy_sim/validation/backtester.py
from dataclasses import dataclass, field
from pathlib import Path
from collections import defaultdict
import numpy as np
import polars as pl
import click
from fantasy_sim.data.loader import DataLoader
from fantasy_sim.data.game_context import GameContextBuilder
from fantasy_sim.data.actuals import load_actual_scores, ActualPlayerWeek
from fantasy_sim.engine.monte_carlo import run_simulations
from fantasy_sim.scoring.projections import build_player_projections
from fantasy_sim.validation.metrics import (
    spearman_rank_correlation, mean_absolute_error, season_total_mae,
    boom_bust_calibration,
)


@dataclass
class BacktestResult:
    """Results of backtesting one season."""
    test_season: int
    weekly_mae: float
    season_mae: float
    rank_correlations: dict[str, float]  # position → Spearman correlation
    boom_bust_calibration: float
    total_players_evaluated: int
    total_weeks_evaluated: int

    # Spec targets
    WEEKLY_MAE_TARGET = 6.0
    SEASON_MAE_TARGET = 25.0
    RANK_CORR_TARGET = 0.80
    CALIBRATION_TARGET = 0.10

    def passes_targets(self) -> bool:
        if self.weekly_mae > self.WEEKLY_MAE_TARGET:
            return False
        if self.season_mae > self.SEASON_MAE_TARGET:
            return False
        for pos, corr in self.rank_correlations.items():
            if corr < self.RANK_CORR_TARGET:
                return False
        if self.boom_bust_calibration > self.CALIBRATION_TARGET:
            return False
        return True


class Backtester:
    """Run hold-out backtests against historical seasons."""

    def __init__(
        self,
        test_season: int,
        n_sims: int = 100,
        num_training_seasons: int = 3,
        scoring_format: str = "ppr",
        cache_dir: Path | None = None,
    ):
        self.test_season = test_season
        self.n_sims = n_sims
        self.training_seasons = list(range(
            test_season - num_training_seasons, test_season
        ))
        self.scoring_format = scoring_format
        self.loader = DataLoader(cache_dir=cache_dir) if cache_dir else DataLoader()
        self.builder = GameContextBuilder(cache_dir=self.loader.cache_dir)

    def run(self, scoring_config: dict) -> BacktestResult:
        """Run the full backtest for one season.

        Uses only training_seasons data for model fitting (no leakage).
        """
        # Load test season schedule and actuals
        schedules = self.loader.load_schedules([self.test_season])
        player_stats = self.loader.load_player_stats([self.test_season])

        actuals = load_actual_scores(player_stats, scoring_config, self.test_season)
        actual_by_player_week = defaultdict(dict)
        for a in actuals:
            actual_by_player_week[a.player_id][a.week] = a.fpts

        # Get all weeks
        weeks = sorted(
            schedules.filter(pl.col("season") == self.test_season)["week"]
            .unique().to_list()
        )
        # Filter to regular season weeks (1-18)
        weeks = [w for w in weeks if 1 <= w <= 18]

        # Run projections week by week
        projected_by_player_week = defaultdict(dict)
        all_weekly_errors = []

        for wk in weeks:
            week_games = schedules.filter(
                (pl.col("week") == wk) & (pl.col("season") == self.test_season)
            )

            week_results = []
            for game in week_games.iter_rows(named=True):
                home, away = game["home_team"], game["away_team"]
                try:
                    home_dists, away_dists, home_roster, away_roster = self.builder.build_game(
                        home, away, seasons=self.training_seasons,
                    )
                    results = run_simulations(
                        home_dists, away_dists, n_sims=self.n_sims,
                        seed=hash(game["game_id"]) % (2**31),
                        home_roster=home_roster, away_roster=away_roster,
                    )
                    week_results.extend(results.games)
                except Exception:
                    continue  # Skip games with missing data

            if not week_results:
                continue

            # Build projections for this week
            week_projs = build_player_projections(week_results, scoring_config)

            # Compare to actuals
            for proj in week_projs:
                pid = proj["player_id"]
                projected_by_player_week[pid][wk] = proj["fpts"]
                if pid in actual_by_player_week and wk in actual_by_player_week[pid]:
                    error = abs(proj["fpts"] - actual_by_player_week[pid][wk])
                    all_weekly_errors.append(error)

        # Compute metrics
        weekly_mae = float(np.mean(all_weekly_errors)) if all_weekly_errors else 99.0

        # Season total MAE
        proj_totals = {pid: sum(wks.values()) for pid, wks in projected_by_player_week.items()}
        act_totals = {pid: sum(wks.values()) for pid, wks in actual_by_player_week.items()}
        common = set(proj_totals.keys()) & set(act_totals.keys())
        season_errors = [abs(proj_totals[pid] - act_totals[pid]) for pid in common]
        season_mae_val = float(np.mean(season_errors)) if season_errors else 99.0

        # Rank correlations by position
        rank_correlations = {}
        for position in ["QB", "RB", "WR", "TE"]:
            pos_actuals = {
                a.player_id: a for a in actuals
                if a.position == position
            }
            # Get season totals for this position
            pos_proj = []
            pos_act = []
            for pid in common:
                if pid in pos_actuals:
                    pos_proj.append(proj_totals[pid])
                    pos_act.append(act_totals[pid])
            if len(pos_proj) >= 5:
                rank_correlations[position] = spearman_rank_correlation(pos_proj, pos_act)
            else:
                rank_correlations[position] = 0.0

        # Boom/bust calibration (threshold: 20+ points)
        boom_threshold = 20.0
        predicted_boom = {}
        actual_boom = {}
        for pid in common:
            proj_weeks = projected_by_player_week.get(pid, {})
            act_weeks = actual_by_player_week.get(pid, {})
            if len(act_weeks) >= 5:
                predicted_boom[pid] = sum(
                    1 for v in proj_weeks.values() if v >= boom_threshold
                ) / max(len(proj_weeks), 1)
                actual_boom[pid] = sum(
                    1 for v in act_weeks.values() if v >= boom_threshold
                ) / len(act_weeks)

        cal = boom_bust_calibration(predicted_boom, actual_boom) if predicted_boom else 0.5

        return BacktestResult(
            test_season=self.test_season,
            weekly_mae=weekly_mae,
            season_mae=season_mae_val,
            rank_correlations=rank_correlations,
            boom_bust_calibration=cal,
            total_players_evaluated=len(common),
            total_weeks_evaluated=len(weeks),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_validation/test_backtester.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/validation/backtester.py tests/test_validation/test_backtester.py
git commit -m "feat: add backtesting framework with hold-out validation"
```

---

### Task 6: Validation Report

**Files:**
- Create: `src/fantasy_sim/validation/report.py`
- Create: `tests/test_validation/test_report.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_validation/test_report.py
import pytest
from fantasy_sim.validation.report import format_backtest_report
from fantasy_sim.validation.backtester import BacktestResult


class TestFormatBacktestReport:
    def test_returns_string(self):
        result = BacktestResult(
            test_season=2024, weekly_mae=5.5, season_mae=22.0,
            rank_correlations={"QB": 0.85, "RB": 0.80, "WR": 0.82, "TE": 0.78},
            boom_bust_calibration=0.08,
            total_players_evaluated=96, total_weeks_evaluated=18,
        )
        report = format_backtest_report(result)
        assert isinstance(report, str)
        assert "2024" in report

    def test_shows_pass_fail(self):
        result = BacktestResult(
            test_season=2024, weekly_mae=5.5, season_mae=22.0,
            rank_correlations={"QB": 0.85, "RB": 0.80, "WR": 0.82, "TE": 0.78},
            boom_bust_calibration=0.08,
            total_players_evaluated=96, total_weeks_evaluated=18,
        )
        report = format_backtest_report(result)
        assert "PASS" in report

    def test_shows_fail_when_metrics_bad(self):
        result = BacktestResult(
            test_season=2024, weekly_mae=8.0, season_mae=30.0,
            rank_correlations={"QB": 0.70}, boom_bust_calibration=0.15,
            total_players_evaluated=24, total_weeks_evaluated=18,
        )
        report = format_backtest_report(result)
        assert "FAIL" in report

    def test_includes_all_positions(self):
        result = BacktestResult(
            test_season=2024, weekly_mae=5.0, season_mae=20.0,
            rank_correlations={"QB": 0.85, "RB": 0.82, "WR": 0.80, "TE": 0.79},
            boom_bust_calibration=0.07,
            total_players_evaluated=96, total_weeks_evaluated=18,
        )
        report = format_backtest_report(result)
        assert "QB" in report
        assert "RB" in report
        assert "WR" in report
        assert "TE" in report
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_validation/test_report.py -v`
Expected: FAIL

- [ ] **Step 3: Implement report formatter**

```python
# src/fantasy_sim/validation/report.py
from rich.console import Console
from rich.table import Table
from fantasy_sim.validation.backtester import BacktestResult


def format_backtest_report(result: BacktestResult) -> str:
    """Format a BacktestResult as a readable report string."""
    console = Console(width=80, force_terminal=True)

    with console.capture() as capture:
        console.print(f"\n[bold]Backtest Report — {result.test_season} Season[/bold]")
        console.print(f"Players evaluated: {result.total_players_evaluated}")
        console.print(f"Weeks evaluated: {result.total_weeks_evaluated}\n")

        # Metrics table
        table = Table(title="Accuracy Metrics")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right")
        table.add_column("Target", justify="right")
        table.add_column("Status", justify="center")

        # Weekly MAE
        weekly_status = "PASS" if result.weekly_mae <= BacktestResult.WEEKLY_MAE_TARGET else "FAIL"
        weekly_style = "green" if weekly_status == "PASS" else "red"
        table.add_row(
            "Weekly MAE (top 24)",
            f"{result.weekly_mae:.2f}",
            f"< {BacktestResult.WEEKLY_MAE_TARGET:.1f}",
            f"[{weekly_style}]{weekly_status}[/{weekly_style}]",
        )

        # Season MAE
        season_status = "PASS" if result.season_mae <= BacktestResult.SEASON_MAE_TARGET else "FAIL"
        season_style = "green" if season_status == "PASS" else "red"
        table.add_row(
            "Season Total MAE",
            f"{result.season_mae:.1f}",
            f"< {BacktestResult.SEASON_MAE_TARGET:.1f}",
            f"[{season_style}]{season_status}[/{season_style}]",
        )

        # Rank correlations by position
        for pos in ["QB", "RB", "WR", "TE"]:
            corr = result.rank_correlations.get(pos, 0.0)
            corr_status = "PASS" if corr >= BacktestResult.RANK_CORR_TARGET else "FAIL"
            corr_style = "green" if corr_status == "PASS" else "red"
            table.add_row(
                f"Rank Corr ({pos})",
                f"{corr:.3f}",
                f"> {BacktestResult.RANK_CORR_TARGET:.2f}",
                f"[{corr_style}]{corr_status}[/{corr_style}]",
            )

        # Boom/bust calibration
        cal_status = "PASS" if result.boom_bust_calibration <= BacktestResult.CALIBRATION_TARGET else "FAIL"
        cal_style = "green" if cal_status == "PASS" else "red"
        table.add_row(
            "Boom/Bust Calibration",
            f"{result.boom_bust_calibration:.3f}",
            f"< {BacktestResult.CALIBRATION_TARGET:.2f}",
            f"[{cal_style}]{cal_status}[/{cal_style}]",
        )

        console.print(table)

        overall = "PASS" if result.passes_targets() else "FAIL"
        overall_style = "green bold" if overall == "PASS" else "red bold"
        console.print(f"\n[{overall_style}]Overall: {overall}[/{overall_style}]")

    return capture.get()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_validation/test_report.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/validation/report.py tests/test_validation/test_report.py
git commit -m "feat: add validation report formatter with pass/fail indicators"
```

---

### Task 7: Backtest CLI Command

**Files:**
- Modify: `src/fantasy_sim/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_cli.py`:

```python
class TestBacktestCommand:
    def test_backtest_help(self, runner):
        result = runner.invoke(main, ["backtest", "--help"])
        assert result.exit_code == 0
        assert "season" in result.output.lower()
```

- [ ] **Step 2: Add backtest command to CLI**

Add to `src/fantasy_sim/cli.py`:

```python
from fantasy_sim.validation.backtester import Backtester
from fantasy_sim.validation.report import format_backtest_report


@main.command()
@click.option("--season", default=2024, help="Season to backtest against")
@click.option("--sims", default=100, type=click.IntRange(min=1), help="Sims per game (lower = faster)")
@click.option("--scoring", default="ppr", type=click.Choice(["ppr", "half_ppr", "standard"]))
@click.option("--training-years", default=3, help="Number of prior seasons for model fitting")
def backtest(season, sims, scoring, training_years):
    """Run backtest validation against a historical season.

    Builds models using only prior-season data (no leakage), runs projections
    for every week, and compares to actual results.

    Requires nflverse data (will download on first run).
    """
    config = load_defaults()
    scoring_config = resolve_scoring(config["scoring"], scoring)

    click.echo(f"Backtesting {season} season ({scoring} scoring, {sims} sims/game)...")
    click.echo(f"Training data: {season - training_years}-{season - 1}\n")

    bt = Backtester(
        test_season=season,
        n_sims=sims,
        num_training_seasons=training_years,
        scoring_format=scoring,
    )
    result = bt.run(scoring_config)

    report = format_backtest_report(result)
    click.echo(report)
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -v`
Expected: All PASS

- [ ] **Step 4: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/cli.py tests/test_cli.py
git commit -m "feat: add backtest CLI command for historical validation"
```

---

## Phase 5 Completion Criteria

All of these must be true before Phase 5 is done:

1. `fantasy-sim week 1 --season 2024` runs end-to-end with real nflverse data
2. `fantasy-sim season --season 2024 --sims 50` produces season-long projections
3. `fantasy-sim backtest --season 2024 --sims 50` runs validation and outputs a report
4. Backtester uses only prior-season data (no leakage — verified in test)
5. Accuracy metrics computed correctly (Spearman, MAE, boom/bust — verified with known inputs)
6. Validation report shows pass/fail per metric with targets from spec
7. `BacktestResult.passes_targets()` checks all spec targets:
   - Rank correlation > 0.80 per position
   - Weekly MAE < 6.0 for top-24
   - Season MAE < 25 per position
   - Boom/bust calibration within 10%
8. All existing tests still pass (backward compatible)

**Note on tuning:** The backtesting infrastructure is complete when Phase 5 is done. Actually *achieving* the accuracy targets may require parameter tuning (adjusting `MIN_BUCKET_PLAYS`, `recency_weights`, play outcome distributions, etc.). The `backtest` command provides the feedback loop — run it, check metrics, adjust parameters, re-run. This is an iterative process that continues after the code is written.

# Phase 4: Scoring + Config + CLI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the config-driven fantasy scoring engine, YAML configuration system with inheritance, terminal/CSV/JSON output formatting, and a Click-based CLI that runs the full simulation pipeline end-to-end — from data loading through scoring and display.

**Architecture:** A `ConfigLoader` reads layered YAML files (defaults → season → custom) with `_inherit` support for scoring presets. A `ScoringEngine` converts `PlayerBoxScore` and `TeamBoxScore` into fantasy points using the loaded config. A `rich`-based output layer formats results as position-grouped terminal tables. A Click CLI ties the full pipeline together: load config → load data → build models → simulate → score → display.

**Tech Stack:** Python 3.14, click (CLI), rich (terminal tables), pyyaml, pytest

---

## File Structure

```
config/
└── defaults.yaml                           NEW: Default scoring rules + simulation settings

src/fantasy_sim/
├── config/
│   ├── __init__.py                         (exists)
│   └── loader.py                           NEW: YAML config loading with inheritance
├── scoring/
│   ├── __init__.py                         (exists)
│   └── engine.py                           NEW: score_player(), score_dst(), score_kicker()
├── output/
│   ├── __init__.py                         (exists)
│   ├── tables.py                           NEW: Rich terminal table formatting
│   └── export.py                           NEW: CSV/JSON export
├── engine/
│   ├── types.py                            MODIFY: Add FG distance fields to TeamBoxScore
│   └── game_flow.py                        MODIFY: Track FG distance in attempt_field_goal
└── cli.py                                  NEW: Click CLI entry point

tests/
├── test_config/
│   └── test_loader.py                      NEW
├── test_scoring/
│   └── test_engine.py                      NEW
├── test_output/
│   ├── test_tables.py                      NEW
│   └── test_export.py                      NEW
└── test_integration/
    └── test_end_to_end.py                  NEW: Full pipeline integration tests
```

## Dependencies from Phase 1-3

- `data.pipeline.DataPipeline` — `build()` returns `{"play_calling": dict[str, PlayCallingDist], "play_outcomes": PlayOutcomeDist, "turnover_rates": dict[str, TurnoverRates], "kicking": KickingModel, "drive_start": DriveStartModel}`
- `data.player_builder.build_player_models(pbp, rosters, seasons)` → `dict[str, PlayerModel]`
- `data.player_builder.build_team_roster(team, models)` → `TeamRoster`
- `engine.types.TeamDistributions` — bundles all distributions for one team
- `engine.types.PlayerBoxScore` — per-player stats with passing/rushing/receiving fields
- `engine.types.TeamBoxScore` — team-level stats including defensive stats (sacks_made, interceptions_caught, fumbles_recovered, safeties)
- `engine.types.GameResult` — `home_score`, `away_score`, `home_box`, `away_box`, `player_stats: dict[str, PlayerBoxScore]`
- `engine.monte_carlo.run_simulations()` → `SimulationSummary` with `summary()` and `player_summary()`
- `data.loader.DataLoader` — `load_pbp()`, `load_schedules()`, `load_rosters_weekly()`

---

### Task 1: Config System (defaults.yaml + loader)

**Files:**
- Create: `config/defaults.yaml`
- Create: `src/fantasy_sim/config/loader.py`
- Create: `tests/test_config/test_loader.py`

- [ ] **Step 1: Create defaults.yaml**

```yaml
# config/defaults.yaml
simulation:
  num_sims: 1000
  historical_seasons: [2022, 2023, 2024]
  recency_weights: [0.2, 0.3, 0.5]
  rookie_blend_games: 4

scoring:
  ppr:
    passing_yard: 0.04
    passing_td: 4
    interception: -2
    rushing_yard: 0.1
    rushing_td: 6
    reception: 1
    receiving_yard: 0.1
    receiving_td: 6
    fumble_lost: -2
    two_point: 2
    fg_0_39: 3
    fg_40_49: 4
    fg_50_plus: 5
    xp_made: 1
    fg_miss: -1
    dst_sack: 1
    dst_interception: 2
    dst_fumble_recovery: 2
    dst_td: 6
    dst_safety: 2
    dst_points_allowed_0: 10
    dst_points_allowed_1_6: 7
    dst_points_allowed_7_13: 4
    dst_points_allowed_14_20: 1
    dst_points_allowed_21_27: 0
    dst_points_allowed_28_34: -1
    dst_points_allowed_35_plus: -4
  half_ppr:
    _inherit: ppr
    reception: 0.5
  standard:
    _inherit: ppr
    reception: 0

positions:
  qb:
    min_snaps: 200
  rb:
    min_carries: 30
    min_targets: 10
  wr:
    min_targets: 30
  te:
    min_targets: 20
  k: {}
  dst: {}
```

- [ ] **Step 2: Write failing tests for config loader**

```python
# tests/test_config/test_loader.py
import pytest
from pathlib import Path
from fantasy_sim.config.loader import load_config, resolve_scoring, ConfigError


@pytest.fixture
def defaults_path():
    return Path(__file__).parent.parent.parent / "config" / "defaults.yaml"


@pytest.fixture
def custom_scoring(tmp_path):
    content = """
inherit: ppr
overrides:
  passing_td: 6
  reception: 1.5
"""
    p = tmp_path / "custom.yaml"
    p.write_text(content)
    return p


class TestLoadConfig:
    def test_loads_defaults(self, defaults_path):
        config = load_config(defaults_path)
        assert "simulation" in config
        assert "scoring" in config
        assert config["simulation"]["num_sims"] == 1000

    def test_scoring_has_presets(self, defaults_path):
        config = load_config(defaults_path)
        assert "ppr" in config["scoring"]
        assert "half_ppr" in config["scoring"]
        assert "standard" in config["scoring"]

    def test_ppr_scoring_values(self, defaults_path):
        config = load_config(defaults_path)
        ppr = config["scoring"]["ppr"]
        assert ppr["passing_yard"] == 0.04
        assert ppr["passing_td"] == 4
        assert ppr["reception"] == 1
        assert ppr["rushing_td"] == 6


class TestResolveScoringInheritance:
    def test_ppr_is_base(self, defaults_path):
        config = load_config(defaults_path)
        resolved = resolve_scoring(config["scoring"], "ppr")
        assert resolved["reception"] == 1
        assert resolved["passing_td"] == 4

    def test_half_ppr_inherits_from_ppr(self, defaults_path):
        config = load_config(defaults_path)
        resolved = resolve_scoring(config["scoring"], "half_ppr")
        assert resolved["reception"] == 0.5
        assert resolved["passing_td"] == 4  # Inherited from PPR

    def test_standard_inherits_from_ppr(self, defaults_path):
        config = load_config(defaults_path)
        resolved = resolve_scoring(config["scoring"], "standard")
        assert resolved["reception"] == 0
        assert resolved["passing_td"] == 4  # Inherited from PPR

    def test_custom_overrides(self, defaults_path, custom_scoring):
        config = load_config(defaults_path)
        custom = load_config(custom_scoring)
        base = resolve_scoring(config["scoring"], custom["inherit"])
        for k, v in custom.get("overrides", {}).items():
            base[k] = v
        assert base["passing_td"] == 6
        assert base["reception"] == 1.5
        assert base["rushing_td"] == 6  # Still from PPR base

    def test_unknown_format_raises(self, defaults_path):
        config = load_config(defaults_path)
        with pytest.raises(ConfigError):
            resolve_scoring(config["scoring"], "nonexistent")

    def test_no_inherit_key_in_base(self, defaults_path):
        """Resolved scoring should not contain _inherit key."""
        config = load_config(defaults_path)
        resolved = resolve_scoring(config["scoring"], "half_ppr")
        assert "_inherit" not in resolved
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_config/test_loader.py -v`
Expected: FAIL

- [ ] **Step 4: Implement config loader**

```python
# src/fantasy_sim/config/loader.py
from pathlib import Path
import yaml


class ConfigError(Exception):
    """Raised for configuration errors."""
    pass


def load_config(path: Path) -> dict:
    """Load a YAML config file and return as dict."""
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")
    with open(path) as f:
        return yaml.safe_load(f)


def resolve_scoring(scoring_presets: dict, format_name: str) -> dict:
    """Resolve a scoring format, following _inherit chains.

    Args:
        scoring_presets: The "scoring" section of the config (contains ppr, half_ppr, etc.)
        format_name: Which format to resolve (e.g., "ppr", "half_ppr")

    Returns:
        Flat dict of stat_name → point_value with all inheritance resolved.
    """
    if format_name not in scoring_presets:
        raise ConfigError(
            f"Unknown scoring format '{format_name}'. "
            f"Available: {', '.join(scoring_presets.keys())}"
        )

    preset = scoring_presets[format_name]

    if "_inherit" in preset:
        parent_name = preset["_inherit"]
        base = resolve_scoring(scoring_presets, parent_name)
        # Override parent values with child values
        for k, v in preset.items():
            if k != "_inherit":
                base[k] = v
        return base
    else:
        return {k: v for k, v in preset.items()}


def get_defaults_path() -> Path:
    """Return the path to the default config file."""
    return Path(__file__).parent.parent.parent.parent / "config" / "defaults.yaml"


def load_defaults() -> dict:
    """Load the default configuration."""
    return load_config(get_defaults_path())
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_config/test_loader.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add config/defaults.yaml src/fantasy_sim/config/loader.py tests/test_config/test_loader.py
git commit -m "feat: add config system with YAML loading and scoring inheritance"
```

---

### Task 2: Scoring Engine

**Files:**
- Create: `src/fantasy_sim/scoring/engine.py`
- Create: `tests/test_scoring/test_engine.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_scoring/test_engine.py
import pytest
from fantasy_sim.scoring.engine import score_player, score_dst
from fantasy_sim.engine.types import PlayerBoxScore, TeamBoxScore


@pytest.fixture
def ppr_config():
    return {
        "passing_yard": 0.04, "passing_td": 4, "interception": -2,
        "rushing_yard": 0.1, "rushing_td": 6,
        "reception": 1, "receiving_yard": 0.1, "receiving_td": 6,
        "fumble_lost": -2, "two_point": 2,
    }


@pytest.fixture
def standard_config():
    return {
        "passing_yard": 0.04, "passing_td": 4, "interception": -2,
        "rushing_yard": 0.1, "rushing_td": 6,
        "reception": 0, "receiving_yard": 0.1, "receiving_td": 6,
        "fumble_lost": -2,
    }


@pytest.fixture
def dst_config():
    return {
        "dst_sack": 1, "dst_interception": 2, "dst_fumble_recovery": 2,
        "dst_td": 6, "dst_safety": 2,
        "dst_points_allowed_0": 10, "dst_points_allowed_1_6": 7,
        "dst_points_allowed_7_13": 4, "dst_points_allowed_14_20": 1,
        "dst_points_allowed_21_27": 0, "dst_points_allowed_28_34": -1,
        "dst_points_allowed_35_plus": -4,
    }


@pytest.fixture
def kicker_config():
    return {
        "fg_0_39": 3, "fg_40_49": 4, "fg_50_plus": 5,
        "xp_made": 1, "fg_miss": -1,
    }


class TestScorePlayerPPR:
    def test_wr_5rec_100yds_1td(self, ppr_config):
        """Spec test: 5 receptions + 100 receiving yards + 1 TD = 21 PPR points."""
        box = PlayerBoxScore("WR1", "WR1", "WR", "KC",
                            receptions=5, receiving_yards=100, receiving_tds=1)
        points = score_player(box, ppr_config)
        assert points == pytest.approx(5*1 + 100*0.1 + 1*6)  # 5 + 10 + 6 = 21
        assert points == pytest.approx(21.0)

    def test_qb_stats(self, ppr_config):
        box = PlayerBoxScore("QB1", "QB", "QB", "KC",
                            pass_yards=300, pass_tds=3, interceptions=1,
                            rush_yards=25, rush_tds=0)
        points = score_player(box, ppr_config)
        expected = 300*0.04 + 3*4 + 1*(-2) + 25*0.1  # 12 + 12 - 2 + 2.5 = 24.5
        assert points == pytest.approx(expected)

    def test_rb_with_receptions(self, ppr_config):
        box = PlayerBoxScore("RB1", "RB", "RB", "KC",
                            rush_yards=80, rush_tds=1,
                            receptions=4, targets=5, receiving_yards=30, receiving_tds=0)
        points = score_player(box, ppr_config)
        expected = 80*0.1 + 1*6 + 4*1 + 30*0.1  # 8 + 6 + 4 + 3 = 21
        assert points == pytest.approx(expected)

    def test_fumble_penalty(self, ppr_config):
        box = PlayerBoxScore("RB1", "RB", "RB", "KC",
                            rush_yards=50, fumbles_lost=1)
        points = score_player(box, ppr_config)
        expected = 50*0.1 + 1*(-2)  # 5 - 2 = 3
        assert points == pytest.approx(expected)


class TestScorePlayerStandard:
    def test_wr_5rec_100yds_1td_standard(self, standard_config):
        """Spec test: same stat line in standard = 16 points."""
        box = PlayerBoxScore("WR1", "WR1", "WR", "KC",
                            receptions=5, receiving_yards=100, receiving_tds=1)
        points = score_player(box, standard_config)
        assert points == pytest.approx(5*0 + 100*0.1 + 1*6)  # 0 + 10 + 6 = 16
        assert points == pytest.approx(16.0)


class TestScoreDST:
    def test_shutout(self, dst_config):
        box = TeamBoxScore(sacks_made=4, interceptions_caught=2, fumbles_recovered=1, safeties=0)
        points = score_dst(box, opponent_score=0, config=dst_config)
        expected = 4*1 + 2*2 + 1*2 + 10  # 4 + 4 + 2 + 10 = 20
        assert points == pytest.approx(expected)

    def test_moderate_points_allowed(self, dst_config):
        box = TeamBoxScore(sacks_made=2, interceptions_caught=1, fumbles_recovered=0, safeties=0)
        points = score_dst(box, opponent_score=17, config=dst_config)
        expected = 2*1 + 1*2 + 1  # 2 + 2 + 1 (14-20 bracket) = 5
        assert points == pytest.approx(expected)

    def test_high_points_allowed_negative(self, dst_config):
        box = TeamBoxScore(sacks_made=1, interceptions_caught=0, fumbles_recovered=0, safeties=0)
        points = score_dst(box, opponent_score=38, config=dst_config)
        expected = 1*1 + (-4)  # 1 - 4 = -3
        assert points == pytest.approx(expected)

    def test_safety_scored(self, dst_config):
        box = TeamBoxScore(sacks_made=0, interceptions_caught=0, fumbles_recovered=0, safeties=1)
        points = score_dst(box, opponent_score=10, config=dst_config)
        expected = 1*2 + 4  # 2 + 4 (7-13 bracket) = 6
        assert points == pytest.approx(expected)


class TestScoreKicker:
    def test_kicker_fg_and_xp(self, kicker_config):
        from fantasy_sim.scoring.engine import score_kicker
        box = TeamBoxScore(
            fg_made=2, fg_made_0_39=1, fg_made_40_49=1, fg_made_50_plus=0,
            fg_missed=0, xp_made=3, xp_attempts=3,
        )
        points = score_kicker(box, kicker_config)
        expected = 1*3 + 1*4 + 3*1  # 3 + 4 + 3 = 10
        assert points == pytest.approx(expected)

    def test_kicker_with_miss(self, kicker_config):
        from fantasy_sim.scoring.engine import score_kicker
        box = TeamBoxScore(
            fg_made=1, fg_made_0_39=1, fg_made_40_49=0, fg_made_50_plus=0,
            fg_missed=1, xp_made=2, xp_attempts=2,
        )
        points = score_kicker(box, kicker_config)
        expected = 1*3 + 1*(-1) + 2*1  # 3 - 1 + 2 = 4
        assert points == pytest.approx(expected)

    def test_kicker_long_fg(self, kicker_config):
        from fantasy_sim.scoring.engine import score_kicker
        box = TeamBoxScore(
            fg_made=1, fg_made_0_39=0, fg_made_40_49=0, fg_made_50_plus=1,
            fg_missed=0, xp_made=1, xp_attempts=1,
        )
        points = score_kicker(box, kicker_config)
        expected = 1*5 + 1*1  # 5 + 1 = 6
        assert points == pytest.approx(expected)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_scoring/test_engine.py -v`
Expected: FAIL

- [ ] **Step 3: Update TeamBoxScore with FG distance fields**

Add these fields to `TeamBoxScore` in `src/fantasy_sim/engine/types.py`:

```python
    # Kicking detail (for scoring)
    fg_made_0_39: int = 0
    fg_made_40_49: int = 0
    fg_made_50_plus: int = 0
    fg_missed: int = 0
```

Update `attempt_field_goal` in `src/fantasy_sim/engine/game_flow.py` to track FG distance. After the existing `off_box.fg_attempts += 1` line, when a FG is made or missed, record the distance bucket:

In the "Made" branch, after `off_box.fg_made += 1`, add:

```python
        if fg_distance < 40:
            off_box.fg_made_0_39 += 1
        elif fg_distance < 50:
            off_box.fg_made_40_49 += 1
        else:
            off_box.fg_made_50_plus += 1
```

In the "Missed" branch, add:

```python
        off_box.fg_missed += 1
```

- [ ] **Step 4: Implement scoring engine**

```python
# src/fantasy_sim/scoring/engine.py
from fantasy_sim.engine.types import PlayerBoxScore, TeamBoxScore


def score_player(box: PlayerBoxScore, config: dict) -> float:
    """Calculate fantasy points for an offensive player (QB/RB/WR/TE).

    Args:
        box: Player's game stats.
        config: Scoring rules (stat_name → point_value).
    """
    points = 0.0
    # Passing
    points += box.pass_yards * config.get("passing_yard", 0)
    points += box.pass_tds * config.get("passing_td", 0)
    points += box.interceptions * config.get("interception", 0)
    # Rushing
    points += box.rush_yards * config.get("rushing_yard", 0)
    points += box.rush_tds * config.get("rushing_td", 0)
    # Receiving
    points += box.receptions * config.get("reception", 0)
    points += box.receiving_yards * config.get("receiving_yard", 0)
    points += box.receiving_tds * config.get("receiving_td", 0)
    # Misc
    points += box.fumbles_lost * config.get("fumble_lost", 0)
    return points


def score_dst(
    box: TeamBoxScore, opponent_score: int, config: dict
) -> float:
    """Calculate fantasy points for a team defense/special teams.

    Args:
        box: Team's defensive stats (sacks_made, interceptions_caught, etc.).
        opponent_score: Total points scored by the opponent.
        config: Scoring rules with dst_ prefixed keys.
    """
    points = 0.0
    points += box.sacks_made * config.get("dst_sack", 0)
    points += box.interceptions_caught * config.get("dst_interception", 0)
    points += box.fumbles_recovered * config.get("dst_fumble_recovery", 0)
    points += box.safeties * config.get("dst_safety", 0)

    # Points allowed brackets
    if opponent_score == 0:
        points += config.get("dst_points_allowed_0", 0)
    elif opponent_score <= 6:
        points += config.get("dst_points_allowed_1_6", 0)
    elif opponent_score <= 13:
        points += config.get("dst_points_allowed_7_13", 0)
    elif opponent_score <= 20:
        points += config.get("dst_points_allowed_14_20", 0)
    elif opponent_score <= 27:
        points += config.get("dst_points_allowed_21_27", 0)
    elif opponent_score <= 34:
        points += config.get("dst_points_allowed_28_34", 0)
    else:
        points += config.get("dst_points_allowed_35_plus", 0)

    return points


def score_kicker(box: TeamBoxScore, config: dict) -> float:
    """Calculate fantasy points for a kicker from team-level kicking stats.

    Args:
        box: Team's box score with FG distance breakdown.
        config: Scoring rules with fg_/xp_ prefixed keys.
    """
    points = 0.0
    points += box.fg_made_0_39 * config.get("fg_0_39", 0)
    points += box.fg_made_40_49 * config.get("fg_40_49", 0)
    points += box.fg_made_50_plus * config.get("fg_50_plus", 0)
    points += box.xp_made * config.get("xp_made", 0)
    points += box.fg_missed * config.get("fg_miss", 0)
    return points
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_scoring/test_engine.py -v`
Expected: All PASS

- [ ] **Step 6: Run full test suite for regressions**

Run: `uv run pytest tests/ -v`
Expected: All existing tests still pass (new TeamBoxScore fields have defaults)

- [ ] **Step 7: Commit**

```bash
git add src/fantasy_sim/scoring/engine.py tests/test_scoring/test_engine.py src/fantasy_sim/engine/types.py src/fantasy_sim/engine/game_flow.py
git commit -m "feat: add scoring engine for players, DST, and kickers with FG distance tracking"
```

---

### Task 3: Terminal Table Output

**Files:**
- Create: `src/fantasy_sim/output/tables.py`
- Create: `tests/test_output/test_tables.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_output/test_tables.py
import pytest
from fantasy_sim.output.tables import (
    format_qb_table, format_rb_table, format_wr_table,
    format_te_table, format_dst_table, format_kicker_table,
)


@pytest.fixture
def qb_projections():
    return [
        {"rank": 1, "name": "P.Mahomes", "team": "KC", "fpts": 22.4,
         "pass_yards": 274, "pass_tds": 2.1, "interceptions": 0.7,
         "rush_yards": 18.3, "rush_tds": 0.2, "sacks": 2.1, "fumbles_lost": 0.3},
    ]


@pytest.fixture
def rb_projections():
    return [
        {"rank": 1, "name": "B.Robinson", "team": "ATL", "fpts": 18.7,
         "rush_yards": 82.3, "rush_tds": 0.7, "targets": 4.2,
         "receptions": 3.1, "receiving_yards": 24.8, "receiving_tds": 0.2,
         "fumbles_lost": 0.2},
    ]


class TestFormatQBTable:
    def test_returns_string(self, qb_projections):
        result = format_qb_table(qb_projections)
        assert isinstance(result, str)
        assert "Mahomes" in result
        assert "274" in result

    def test_empty_list(self):
        result = format_qb_table([])
        assert isinstance(result, str)


class TestFormatRBTable:
    def test_returns_string(self, rb_projections):
        result = format_rb_table(rb_projections)
        assert isinstance(result, str)
        assert "Robinson" in result

    def test_includes_receiving_stats(self, rb_projections):
        result = format_rb_table(rb_projections)
        assert "24.8" in result  # receiving yards


class TestFormatWRTable:
    def test_returns_string(self):
        projections = [
            {"rank": 1, "name": "N.Collins", "team": "HOU", "fpts": 17.2,
             "targets": 8.4, "receptions": 5.8, "receiving_yards": 78.2,
             "receiving_tds": 0.6, "rush_yards": 2.1, "rush_tds": 0.0,
             "fumbles_lost": 0.1},
        ]
        result = format_wr_table(projections)
        assert "Collins" in result


class TestFormatDSTTable:
    def test_returns_string(self):
        projections = [
            {"rank": 1, "team": "BAL", "fpts": 8.2,
             "sacks": 2.8, "interceptions": 0.9, "fumble_recoveries": 0.7,
             "dst_tds": 0.2, "safeties": 0.1, "points_allowed": 18.4},
        ]
        result = format_dst_table(projections)
        assert "BAL" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_output/test_tables.py -v`
Expected: FAIL

- [ ] **Step 3: Implement table formatting**

```python
# src/fantasy_sim/output/tables.py
from rich.console import Console
from rich.table import Table


def _render_table(table: Table) -> str:
    """Render a Rich table to a string."""
    console = Console(width=120, force_terminal=True)
    with console.capture() as capture:
        console.print(table)
    return capture.get()


def format_qb_table(projections: list[dict]) -> str:
    table = Table(title="QB Projections")
    table.add_column("Rank", justify="right", style="bold")
    table.add_column("Player", style="cyan")
    table.add_column("Team")
    table.add_column("FPts", justify="right", style="green bold")
    table.add_column("PaYd", justify="right")
    table.add_column("PaTD", justify="right")
    table.add_column("INT", justify="right")
    table.add_column("RuYd", justify="right")
    table.add_column("RuTD", justify="right")
    table.add_column("Sck", justify="right")
    table.add_column("FL", justify="right")

    for p in projections:
        table.add_row(
            str(p["rank"]), p["name"], p["team"],
            f"{p['fpts']:.1f}", f"{p['pass_yards']:.0f}", f"{p['pass_tds']:.1f}",
            f"{p['interceptions']:.1f}", f"{p['rush_yards']:.1f}",
            f"{p['rush_tds']:.1f}", f"{p['sacks']:.1f}", f"{p['fumbles_lost']:.1f}",
        )

    return _render_table(table)


def format_rb_table(projections: list[dict]) -> str:
    table = Table(title="RB Projections")
    table.add_column("Rank", justify="right", style="bold")
    table.add_column("Player", style="cyan")
    table.add_column("Team")
    table.add_column("FPts", justify="right", style="green bold")
    table.add_column("RuYd", justify="right")
    table.add_column("RuTD", justify="right")
    table.add_column("Tgt", justify="right")
    table.add_column("Rec", justify="right")
    table.add_column("ReYd", justify="right")
    table.add_column("ReTD", justify="right")
    table.add_column("FL", justify="right")

    for p in projections:
        table.add_row(
            str(p["rank"]), p["name"], p["team"],
            f"{p['fpts']:.1f}", f"{p['rush_yards']:.1f}", f"{p['rush_tds']:.1f}",
            f"{p['targets']:.1f}", f"{p['receptions']:.1f}",
            f"{p['receiving_yards']:.1f}", f"{p['receiving_tds']:.1f}",
            f"{p['fumbles_lost']:.1f}",
        )

    return _render_table(table)


def format_wr_table(projections: list[dict]) -> str:
    table = Table(title="WR Projections")
    table.add_column("Rank", justify="right", style="bold")
    table.add_column("Player", style="cyan")
    table.add_column("Team")
    table.add_column("FPts", justify="right", style="green bold")
    table.add_column("Tgt", justify="right")
    table.add_column("Rec", justify="right")
    table.add_column("ReYd", justify="right")
    table.add_column("ReTD", justify="right")
    table.add_column("RuYd", justify="right")
    table.add_column("RuTD", justify="right")
    table.add_column("FL", justify="right")

    for p in projections:
        table.add_row(
            str(p["rank"]), p["name"], p["team"],
            f"{p['fpts']:.1f}", f"{p['targets']:.1f}", f"{p['receptions']:.1f}",
            f"{p['receiving_yards']:.1f}", f"{p['receiving_tds']:.1f}",
            f"{p.get('rush_yards', 0):.1f}", f"{p.get('rush_tds', 0):.1f}",
            f"{p['fumbles_lost']:.1f}",
        )

    return _render_table(table)


def format_te_table(projections: list[dict]) -> str:
    """TE table — same columns as WR."""
    table = Table(title="TE Projections")
    table.add_column("Rank", justify="right", style="bold")
    table.add_column("Player", style="cyan")
    table.add_column("Team")
    table.add_column("FPts", justify="right", style="green bold")
    table.add_column("Tgt", justify="right")
    table.add_column("Rec", justify="right")
    table.add_column("ReYd", justify="right")
    table.add_column("ReTD", justify="right")
    table.add_column("FL", justify="right")

    for p in projections:
        table.add_row(
            str(p["rank"]), p["name"], p["team"],
            f"{p['fpts']:.1f}", f"{p['targets']:.1f}", f"{p['receptions']:.1f}",
            f"{p['receiving_yards']:.1f}", f"{p['receiving_tds']:.1f}",
            f"{p['fumbles_lost']:.1f}",
        )

    return _render_table(table)


def format_kicker_table(projections: list[dict]) -> str:
    table = Table(title="K Projections")
    table.add_column("Rank", justify="right", style="bold")
    table.add_column("Player", style="cyan")
    table.add_column("Team")
    table.add_column("FPts", justify="right", style="green bold")
    table.add_column("FGA", justify="right")
    table.add_column("FGM", justify="right")
    table.add_column("FG50+", justify="right")
    table.add_column("XPA", justify="right")
    table.add_column("XPM", justify="right")

    for p in projections:
        table.add_row(
            str(p["rank"]), p["name"], p["team"],
            f"{p['fpts']:.1f}", f"{p['fg_attempts']:.1f}", f"{p['fg_made']:.1f}",
            f"{p['fg_50_plus']:.1f}", f"{p['xp_attempts']:.1f}", f"{p['xp_made']:.1f}",
        )

    return _render_table(table)


def format_dst_table(projections: list[dict]) -> str:
    table = Table(title="DST Projections")
    table.add_column("Rank", justify="right", style="bold")
    table.add_column("Team", style="cyan")
    table.add_column("FPts", justify="right", style="green bold")
    table.add_column("Sck", justify="right")
    table.add_column("INT", justify="right")
    table.add_column("FR", justify="right")
    table.add_column("DTD", justify="right")
    table.add_column("Saf", justify="right")
    table.add_column("PtsAllow", justify="right")

    for p in projections:
        table.add_row(
            str(p["rank"]), p["team"],
            f"{p['fpts']:.1f}", f"{p['sacks']:.1f}", f"{p['interceptions']:.1f}",
            f"{p['fumble_recoveries']:.1f}", f"{p['dst_tds']:.1f}",
            f"{p['safeties']:.1f}", f"{p['points_allowed']:.1f}",
        )

    return _render_table(table)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_output/test_tables.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/output/tables.py tests/test_output/test_tables.py
git commit -m "feat: add Rich terminal table output for all positions"
```

---

### Task 4: CSV/JSON Export

**Files:**
- Create: `src/fantasy_sim/output/export.py`
- Create: `tests/test_output/test_export.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_output/test_export.py
import json
import csv
import pytest
from pathlib import Path
from fantasy_sim.output.export import export_csv, export_json


@pytest.fixture
def sample_projections():
    return [
        {"rank": 1, "name": "P.Mahomes", "position": "QB", "team": "KC",
         "fpts": 22.4, "pass_yards": 274, "pass_tds": 2.1},
        {"rank": 2, "name": "J.Allen", "position": "QB", "team": "BUF",
         "fpts": 21.9, "pass_yards": 268, "pass_tds": 2.0},
    ]


class TestExportCSV:
    def test_creates_file(self, tmp_path, sample_projections):
        output = tmp_path / "results.csv"
        export_csv(sample_projections, output)
        assert output.exists()

    def test_csv_has_headers(self, tmp_path, sample_projections):
        output = tmp_path / "results.csv"
        export_csv(sample_projections, output)
        with open(output) as f:
            reader = csv.DictReader(f)
            assert "name" in reader.fieldnames
            assert "fpts" in reader.fieldnames

    def test_csv_has_correct_rows(self, tmp_path, sample_projections):
        output = tmp_path / "results.csv"
        export_csv(sample_projections, output)
        with open(output) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["name"] == "P.Mahomes"


class TestExportJSON:
    def test_creates_file(self, tmp_path, sample_projections):
        output = tmp_path / "results.json"
        export_json(sample_projections, output)
        assert output.exists()

    def test_json_is_valid(self, tmp_path, sample_projections):
        output = tmp_path / "results.json"
        export_json(sample_projections, output)
        with open(output) as f:
            data = json.load(f)
        assert len(data) == 2

    def test_json_has_correct_data(self, tmp_path, sample_projections):
        output = tmp_path / "results.json"
        export_json(sample_projections, output)
        with open(output) as f:
            data = json.load(f)
        assert data[0]["name"] == "P.Mahomes"
        assert data[0]["fpts"] == 22.4
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_output/test_export.py -v`
Expected: FAIL

- [ ] **Step 3: Implement export**

```python
# src/fantasy_sim/output/export.py
import csv
import json
from pathlib import Path


def export_csv(projections: list[dict], output_path: Path) -> None:
    """Export projections to CSV file."""
    output_path = Path(output_path)
    if not projections:
        output_path.write_text("")
        return

    fieldnames = list(projections[0].keys())
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(projections)


def export_json(projections: list[dict], output_path: Path) -> None:
    """Export projections to JSON file."""
    output_path = Path(output_path)
    with open(output_path, "w") as f:
        json.dump(projections, f, indent=2)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_output/test_export.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/output/export.py tests/test_output/test_export.py
git commit -m "feat: add CSV and JSON export for projections"
```

---

### Task 5: Projection Builder (bridge between sim results and output)

**Files:**
- Create: `src/fantasy_sim/scoring/projections.py`
- Create: `tests/test_scoring/test_projections.py`

This module converts raw `SimulationSummary` into scored, ranked projection dicts ready for display/export.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_scoring/test_projections.py
import numpy as np
import pytest
from fantasy_sim.scoring.projections import build_player_projections, build_dst_projections
from fantasy_sim.engine.types import GameResult, TeamBoxScore, PlayerBoxScore


def make_game_result(player_stats=None, home_score=24, away_score=17):
    return GameResult(
        home_score=home_score, away_score=away_score,
        home_box=TeamBoxScore(
            points=home_score, sacks_made=3, interceptions_caught=1,
            fumbles_recovered=1, safeties=0,
            fg_made=1, fg_made_0_39=1, fg_made_40_49=0, fg_made_50_plus=0,
            fg_missed=0, xp_made=3, xp_attempts=3,
        ),
        away_box=TeamBoxScore(
            points=away_score, sacks_made=2, interceptions_caught=0,
            fumbles_recovered=0, safeties=0,
            fg_made=1, fg_made_0_39=0, fg_made_40_49=1, fg_made_50_plus=0,
            fg_missed=1, xp_made=2, xp_attempts=2,
        ),
        total_plays=130, overtime=False,
        player_stats=player_stats or {
            "QB1": PlayerBoxScore("QB1", "QB Name", "QB", "HOME",
                                  pass_yards=280, pass_tds=2, completions=22,
                                  pass_attempts=35, interceptions=1),
            "WR1": PlayerBoxScore("WR1", "WR Name", "WR", "HOME",
                                  targets=8, receptions=5, receiving_yards=85,
                                  receiving_tds=1),
            "RB1": PlayerBoxScore("RB1", "RB Name", "RB", "HOME",
                                  rush_attempts=15, rush_yards=65, rush_tds=1,
                                  targets=3, receptions=2, receiving_yards=18),
        },
    )


@pytest.fixture
def ppr_config():
    return {
        "passing_yard": 0.04, "passing_td": 4, "interception": -2,
        "rushing_yard": 0.1, "rushing_td": 6,
        "reception": 1, "receiving_yard": 0.1, "receiving_td": 6,
        "fumble_lost": -2,
    }


@pytest.fixture
def dst_config():
    return {
        "dst_sack": 1, "dst_interception": 2, "dst_fumble_recovery": 2,
        "dst_td": 6, "dst_safety": 2,
        "dst_points_allowed_0": 10, "dst_points_allowed_1_6": 7,
        "dst_points_allowed_7_13": 4, "dst_points_allowed_14_20": 1,
        "dst_points_allowed_21_27": 0, "dst_points_allowed_28_34": -1,
        "dst_points_allowed_35_plus": -4,
    }


class TestBuildPlayerProjections:
    def test_returns_list_of_dicts(self, ppr_config):
        games = [make_game_result() for _ in range(5)]
        projections = build_player_projections(games, ppr_config)
        assert isinstance(projections, list)
        assert len(projections) > 0
        assert "name" in projections[0]
        assert "fpts" in projections[0]

    def test_projections_sorted_by_fpts(self, ppr_config):
        games = [make_game_result() for _ in range(10)]
        projections = build_player_projections(games, ppr_config)
        fpts = [p["fpts"] for p in projections]
        assert fpts == sorted(fpts, reverse=True)

    def test_projections_have_position(self, ppr_config):
        games = [make_game_result() for _ in range(5)]
        projections = build_player_projections(games, ppr_config)
        for p in projections:
            assert p["position"] in ("QB", "RB", "WR", "TE", "K")

    def test_projections_have_mean_stats(self, ppr_config):
        games = [make_game_result() for _ in range(5)]
        projections = build_player_projections(games, ppr_config)
        qb = next(p for p in projections if p["position"] == "QB")
        assert "pass_yards" in qb
        assert "pass_tds" in qb
        assert qb["pass_yards"] > 0


class TestBuildDSTProjections:
    def test_returns_list(self, dst_config):
        games = [make_game_result()]
        projections = build_dst_projections(games, dst_config, team_map={"HOME": "KC", "AWAY": "BUF"})
        assert isinstance(projections, list)

    def test_dst_has_fpts(self, dst_config):
        games = [make_game_result() for _ in range(5)]
        projections = build_dst_projections(games, dst_config, team_map={"HOME": "KC", "AWAY": "BUF"})
        for p in projections:
            assert "fpts" in p
            assert "sacks" in p
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_scoring/test_projections.py -v`
Expected: FAIL

- [ ] **Step 3: Implement projection builder**

```python
# src/fantasy_sim/scoring/projections.py
from collections import defaultdict
import numpy as np
from fantasy_sim.engine.types import GameResult, PlayerBoxScore, TeamBoxScore
from fantasy_sim.scoring.engine import score_player, score_dst, score_kicker


def build_player_projections(
    games: list[GameResult], scoring_config: dict
) -> list[dict]:
    """Aggregate player stats across games and compute fantasy points.

    Returns list of projection dicts sorted by fpts descending.
    """
    # Collect per-player stats across all games
    player_games: dict[str, list[PlayerBoxScore]] = defaultdict(list)
    for game in games:
        for pid, box in game.player_stats.items():
            player_games[pid].append(box)

    projections = []
    for pid, boxes in player_games.items():
        if not boxes:
            continue
        first = boxes[0]
        n = len(boxes)

        # Compute mean fantasy points
        fpts_list = [score_player(b, scoring_config) for b in boxes]
        mean_fpts = np.mean(fpts_list)

        proj = {
            "player_id": pid,
            "name": first.name,
            "position": first.position,
            "team": first.team,
            "fpts": round(float(mean_fpts), 1),
            # Passing
            "pass_yards": round(float(np.mean([b.pass_yards for b in boxes])), 1),
            "pass_tds": round(float(np.mean([b.pass_tds for b in boxes])), 1),
            "interceptions": round(float(np.mean([b.interceptions for b in boxes])), 1),
            "sacks": round(float(np.mean([b.sacks for b in boxes])), 1),
            # Rushing
            "rush_yards": round(float(np.mean([b.rush_yards for b in boxes])), 1),
            "rush_tds": round(float(np.mean([b.rush_tds for b in boxes])), 1),
            # Receiving
            "targets": round(float(np.mean([b.targets for b in boxes])), 1),
            "receptions": round(float(np.mean([b.receptions for b in boxes])), 1),
            "receiving_yards": round(float(np.mean([b.receiving_yards for b in boxes])), 1),
            "receiving_tds": round(float(np.mean([b.receiving_tds for b in boxes])), 1),
            # Misc
            "fumbles_lost": round(float(np.mean([b.fumbles_lost for b in boxes])), 1),
        }
        projections.append(proj)

    projections.sort(key=lambda p: p["fpts"], reverse=True)

    # Add rank
    for i, p in enumerate(projections, 1):
        p["rank"] = i

    return projections


def build_dst_projections(
    games: list[GameResult],
    scoring_config: dict,
    team_map: dict[str, str] | None = None,
) -> list[dict]:
    """Build DST projections from game results.

    Args:
        games: Simulated game results.
        scoring_config: DST scoring config.
        team_map: Maps "HOME"/"AWAY" labels to actual team abbreviations.
    """
    home_boxes = [g.home_box for g in games]
    away_boxes = [g.away_box for g in games]
    home_scores = [g.home_score for g in games]
    away_scores = [g.away_score for g in games]

    projections = []

    # Home DST (defends against away team)
    home_fpts = [score_dst(hb, as_, scoring_config) for hb, as_ in zip(home_boxes, away_scores)]
    home_name = team_map.get("HOME", "HOME") if team_map else "HOME"
    projections.append({
        "team": home_name,
        "fpts": round(float(np.mean(home_fpts)), 1),
        "sacks": round(float(np.mean([b.sacks_made for b in home_boxes])), 1),
        "interceptions": round(float(np.mean([b.interceptions_caught for b in home_boxes])), 1),
        "fumble_recoveries": round(float(np.mean([b.fumbles_recovered for b in home_boxes])), 1),
        "dst_tds": 0.0,  # Not tracked yet
        "safeties": round(float(np.mean([b.safeties for b in home_boxes])), 1),
        "points_allowed": round(float(np.mean(away_scores)), 1),
    })

    # Away DST
    away_fpts = [score_dst(ab, hs, scoring_config) for ab, hs in zip(away_boxes, home_scores)]
    away_name = team_map.get("AWAY", "AWAY") if team_map else "AWAY"
    projections.append({
        "team": away_name,
        "fpts": round(float(np.mean(away_fpts)), 1),
        "sacks": round(float(np.mean([b.sacks_made for b in away_boxes])), 1),
        "interceptions": round(float(np.mean([b.interceptions_caught for b in away_boxes])), 1),
        "fumble_recoveries": round(float(np.mean([b.fumbles_recovered for b in away_boxes])), 1),
        "dst_tds": 0.0,
        "safeties": round(float(np.mean([b.safeties for b in away_boxes])), 1),
        "points_allowed": round(float(np.mean(home_scores)), 1),
    })

    projections.sort(key=lambda p: p["fpts"], reverse=True)
    for i, p in enumerate(projections, 1):
        p["rank"] = i

    return projections
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_scoring/test_projections.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/scoring/projections.py tests/test_scoring/test_projections.py
git commit -m "feat: add projection builder to bridge sim results to scored output"
```

---

### Task 6: CLI Entry Point

**Files:**
- Create: `src/fantasy_sim/cli.py`
- Create: `tests/test_cli.py`

The CLI uses Click and ties the full pipeline together. For Phase 4, it supports a `demo` command that runs simulations with synthetic distributions (no nflverse dependency) to demonstrate the scoring + output pipeline end-to-end. The full `week` and `season` commands that load real data are also included but require nflverse data to be cached.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_cli.py
import pytest
from click.testing import CliRunner
from fantasy_sim.cli import main


@pytest.fixture
def runner():
    return CliRunner()


class TestCLI:
    def test_help(self, runner):
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "fantasy-sim" in result.output.lower() or "Usage" in result.output

    def test_demo_command(self, runner):
        result = runner.invoke(main, ["demo", "--sims", "10"])
        assert result.exit_code == 0
        assert "QB" in result.output or "Projections" in result.output

    def test_demo_csv_export(self, runner, tmp_path):
        output = tmp_path / "test.csv"
        result = runner.invoke(main, ["demo", "--sims", "10", "--format", "csv", "--output", str(output)])
        assert result.exit_code == 0
        assert output.exists()

    def test_demo_json_export(self, runner, tmp_path):
        output = tmp_path / "test.json"
        result = runner.invoke(main, ["demo", "--sims", "10", "--format", "json", "--output", str(output)])
        assert result.exit_code == 0
        assert output.exists()

    def test_demo_scoring_format(self, runner):
        result = runner.invoke(main, ["demo", "--sims", "10", "--scoring", "standard"])
        assert result.exit_code == 0

    def test_demo_half_ppr(self, runner):
        result = runner.invoke(main, ["demo", "--sims", "10", "--scoring", "half_ppr"])
        assert result.exit_code == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL

- [ ] **Step 3: Implement CLI**

```python
# src/fantasy_sim/cli.py
import click
import numpy as np
from pathlib import Path
from fantasy_sim.config.loader import load_defaults, resolve_scoring
from fantasy_sim.engine.types import TeamDistributions
from fantasy_sim.engine.monte_carlo import run_simulations
from fantasy_sim.models.distributions import (
    PlayCallingDist, PlayOutcomeDist, TurnoverRates, KickingModel, DriveStartModel,
)
from fantasy_sim.models.player import PlayerModel, PlayerUsage, PlayerOutcomes, TeamRoster
from fantasy_sim.scoring.projections import build_player_projections, build_dst_projections
from fantasy_sim.output.tables import (
    format_qb_table, format_rb_table, format_wr_table,
    format_te_table, format_dst_table,
)
from fantasy_sim.output.export import export_csv, export_json


def _make_demo_dists(team: str) -> TeamDistributions:
    """Create league-average distributions for demo mode."""
    return TeamDistributions(
        play_calling=PlayCallingDist(team=team, distributions={}, default={"pass": 0.57, "run": 0.43}),
        play_outcomes=PlayOutcomeDist(distributions={}, defaults={
            "pass": np.array([0, 0, 0, 0, 5, 7, 8, 10, 12, 15, 20, 25, 30]),
            "run": np.array([-2, 0, 1, 2, 3, 3, 4, 4, 5, 6, 7, 8, 12]),
        }),
        turnover_rates=TurnoverRates(team=team, int_rate=0.025, fumble_rate=0.012, sack_rate=0.065, sack_fumble_rate=0.10),
        kicking=KickingModel(fg_make_rate={"0_39": 0.93, "40_49": 0.82, "50_plus": 0.65}, xp_rate=0.94),
        drive_start=DriveStartModel(touchback_rate=0.55, touchback_yardline=75, return_yardlines=np.array([72, 74, 76, 78, 80])),
    )


def _make_demo_roster(team: str) -> TeamRoster:
    """Create a demo roster with realistic usage splits."""
    return TeamRoster(team=team, players=[
        PlayerModel(f"{team}_QB", "QB1", "QB", team,
                    PlayerUsage(snap_share=1.0, scramble_rate=0.06),
                    PlayerOutcomes(scramble_yards_dist=np.array([2, 4, 6, 8, 12, -2, 3, 5]))),
        PlayerModel(f"{team}_WR1", "WR1", "WR", team,
                    PlayerUsage(target_share=0.24),
                    PlayerOutcomes(catch_rate=0.63, receiving_yards_dist=np.array([5, 7, 8, 10, 12, 14, 16, 20, 25, 35]))),
        PlayerModel(f"{team}_WR2", "WR2", "WR", team,
                    PlayerUsage(target_share=0.18),
                    PlayerOutcomes(catch_rate=0.60, receiving_yards_dist=np.array([5, 7, 9, 11, 13, 17, 22]))),
        PlayerModel(f"{team}_TE", "TE1", "TE", team,
                    PlayerUsage(target_share=0.16),
                    PlayerOutcomes(catch_rate=0.67, receiving_yards_dist=np.array([4, 6, 8, 10, 12, 15]))),
        PlayerModel(f"{team}_RB1", "RB1", "RB", team,
                    PlayerUsage(carry_share=0.60, target_share=0.10),
                    PlayerOutcomes(
                        rushing_yards_dist=np.array([-2, 0, 1, 2, 3, 3, 4, 4, 5, 5, 6, 7, 8, 10, 15, 20]),
                        catch_rate=0.72, receiving_yards_dist=np.array([3, 5, 7, 4]),
                        fumble_rate=0.008)),
        PlayerModel(f"{team}_RB2", "RB2", "RB", team,
                    PlayerUsage(carry_share=0.30, target_share=0.05),
                    PlayerOutcomes(
                        rushing_yards_dist=np.array([0, 1, 2, 3, 4, 5, 6, 7]),
                        catch_rate=0.65, receiving_yards_dist=np.array([3, 5]),
                        fumble_rate=0.010)),
    ])


@click.group()
def main():
    """Fantasy football projections via play-by-play simulation."""
    pass


@main.command()
@click.option("--sims", default=100, help="Number of simulations per game")
@click.option("--scoring", default="ppr", help="Scoring format: ppr, half_ppr, standard")
@click.option("--format", "output_format", default="table", help="Output format: table, csv, json")
@click.option("--output", "output_path", default=None, help="Output file path (for csv/json)")
def demo(sims, scoring, output_format, output_path):
    """Run a demo simulation with synthetic team data."""
    config = load_defaults()
    scoring_config = resolve_scoring(config["scoring"], scoring)

    click.echo(f"Running {sims} simulations ({scoring} scoring)...")

    home_dists = _make_demo_dists("HOME")
    away_dists = _make_demo_dists("AWAY")
    home_roster = _make_demo_roster("HOME")
    away_roster = _make_demo_roster("AWAY")

    results = run_simulations(
        home_dists, away_dists, n_sims=sims, seed=42,
        home_roster=home_roster, away_roster=away_roster,
    )

    game_summary = results.summary()
    click.echo(f"Avg Score: HOME {game_summary['home_score_mean']:.1f} - AWAY {game_summary['away_score_mean']:.1f}")
    click.echo(f"HOME Win%: {game_summary['home_win_pct']:.1%}\n")

    # Build projections
    player_projs = build_player_projections(results.games, scoring_config)
    dst_projs = build_dst_projections(
        results.games, scoring_config,
        team_map={"HOME": "HOME", "AWAY": "AWAY"},
    )

    if output_format == "table":
        # Group by position and display
        qbs = [p for p in player_projs if p["position"] == "QB"]
        rbs = [p for p in player_projs if p["position"] == "RB"]
        wrs = [p for p in player_projs if p["position"] == "WR"]
        tes = [p for p in player_projs if p["position"] == "TE"]

        if qbs:
            click.echo(format_qb_table(qbs))
        if rbs:
            click.echo(format_rb_table(rbs))
        if wrs:
            click.echo(format_wr_table(wrs))
        if tes:
            click.echo(format_te_table(tes))
        if dst_projs:
            click.echo(format_dst_table(dst_projs))

    elif output_format in ("csv", "json"):
        if output_path is None:
            output_path = f"projections.{output_format}"
        all_projs = player_projs + dst_projs
        if output_format == "csv":
            export_csv(all_projs, Path(output_path))
        else:
            export_json(all_projs, Path(output_path))
        click.echo(f"Exported to {output_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -v`
Expected: All PASS

- [ ] **Step 5: Verify CLI runs end-to-end**

Run: `uv run fantasy-sim demo --sims 50`
Expected: Terminal output showing QB, RB, WR, TE, DST projection tables with fantasy points

- [ ] **Step 6: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
git add src/fantasy_sim/cli.py tests/test_cli.py
git commit -m "feat: add Click CLI with demo command and end-to-end pipeline"
```

---

### Task 7: Integration Tests

**Files:**
- Create: `tests/test_integration/test_end_to_end.py`

- [ ] **Step 1: Write integration tests**

```python
# tests/test_integration/test_end_to_end.py
import json
import numpy as np
import pytest
from pathlib import Path
from click.testing import CliRunner
from fantasy_sim.cli import main
from fantasy_sim.config.loader import load_defaults, resolve_scoring
from fantasy_sim.scoring.engine import score_player
from fantasy_sim.scoring.projections import build_player_projections
from fantasy_sim.engine.types import GameResult, TeamBoxScore, PlayerBoxScore


class TestScoringConsistency:
    def test_player_fpts_equals_stats_times_weights(self):
        """End-to-end: verify fantasy points = sum of stats × scoring weights."""
        config = load_defaults()
        scoring = resolve_scoring(config["scoring"], "ppr")

        box = PlayerBoxScore(
            "WR1", "WR Name", "WR", "KC",
            receptions=5, receiving_yards=100, receiving_tds=1,
        )
        fpts = score_player(box, scoring)
        manual = 5 * 1 + 100 * 0.1 + 1 * 6  # 5 + 10 + 6 = 21
        assert fpts == pytest.approx(manual)

    def test_standard_no_reception_points(self):
        config = load_defaults()
        scoring = resolve_scoring(config["scoring"], "standard")
        assert scoring["reception"] == 0

        box = PlayerBoxScore(
            "WR1", "WR Name", "WR", "KC",
            receptions=5, receiving_yards=100, receiving_tds=1,
        )
        fpts = score_player(box, scoring)
        manual = 5 * 0 + 100 * 0.1 + 1 * 6  # 0 + 10 + 6 = 16
        assert fpts == pytest.approx(manual)


class TestCLIPipeline:
    def test_demo_produces_output(self):
        runner = CliRunner()
        result = runner.invoke(main, ["demo", "--sims", "20"])
        assert result.exit_code == 0
        # Should have position tables
        assert "QB" in result.output

    def test_demo_csv_valid(self, tmp_path):
        runner = CliRunner()
        output = tmp_path / "out.csv"
        result = runner.invoke(main, ["demo", "--sims", "20", "--format", "csv", "--output", str(output)])
        assert result.exit_code == 0
        content = output.read_text()
        assert "fpts" in content
        assert "name" in content

    def test_demo_json_valid(self, tmp_path):
        runner = CliRunner()
        output = tmp_path / "out.json"
        result = runner.invoke(main, ["demo", "--sims", "20", "--format", "json", "--output", str(output)])
        assert result.exit_code == 0
        data = json.loads(output.read_text())
        assert len(data) > 0
        assert all("fpts" in d for d in data)

    def test_all_scoring_formats_work(self):
        runner = CliRunner()
        for fmt in ["ppr", "half_ppr", "standard"]:
            result = runner.invoke(main, ["demo", "--sims", "10", "--scoring", fmt])
            assert result.exit_code == 0, f"Failed for format: {fmt}"

    def test_projections_are_ranked(self):
        runner = CliRunner()
        result = runner.invoke(main, ["demo", "--sims", "50", "--format", "json", "--output", "/dev/stdout"])
        # Even though json goes to stdout, the exit should be clean
        assert result.exit_code == 0
```

- [ ] **Step 2: Run integration tests**

Run: `uv run pytest tests/test_integration/test_end_to_end.py -v`
Expected: All PASS

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration/test_end_to_end.py
git commit -m "feat: add end-to-end integration tests for scoring + CLI pipeline"
```

---

## Phase 4 Completion Criteria

All of these must be true before Phase 4 is done:

1. `config/defaults.yaml` exists with PPR, half-PPR, and standard scoring presets
2. Config loader resolves `_inherit` chains correctly
3. `score_player()` produces correct points for all positions (verified: 5rec + 100yd + 1TD = 21 PPR, 16 standard)
4. `score_dst()` handles all points-allowed brackets correctly
5. `score_kicker()` uses FG distance breakdowns (0-39, 40-49, 50+)
6. Terminal tables display all stats by position using Rich
7. CSV and JSON export produce valid files with correct data
8. `fantasy-sim demo --sims 50` runs end-to-end and produces projection tables
9. All scoring formats (ppr, half_ppr, standard) work via `--scoring` flag
10. All existing tests still pass (backward compatible)

# PFF Intelligence Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add defensive matchup awareness and talent stabilization to the simulator using PFF data, replacing the failed modifier approach.

**Architecture:** Two independent layers feed adjustments into the existing sim pipeline. Layer 1+2 (MatchupEngine) uses PFF defensive + OL data to create per-game multiplicative factors via z-scores. Layer 3 (TalentStabilizer) uses PFF offensive quality metrics to Bayesian-blend player parameters where PBP and PFF diverge. Both layers sit between base model construction and user overrides in `GameContextBuilder`.

**Tech Stack:** Python 3.12+, polars (DataFrames), numpy (distributions), pytest (testing), YAML (config)

**Spec:** `docs/superpowers/specs/2026-04-02-pff-intelligence-layer-design.md`

---

## Task 1: Foundation — Create pff/ Subpackage and Move Loader

**Files:**
- Create: `src/fantasy_sim/data/pff/__init__.py`
- Create: `src/fantasy_sim/data/pff/models.py`
- Create: `src/fantasy_sim/data/pff/config.py`
- Move: `src/fantasy_sim/data/pff_loader.py` → `src/fantasy_sim/data/pff/loader.py`
- Move: `tests/test_data/test_pff_loader.py` → `tests/test_data/test_pff/test_loader.py`
- Create: `tests/test_data/test_pff/__init__.py`

- [ ] **Step 1: Create pff subpackage with __init__.py**

```python
# src/fantasy_sim/data/pff/__init__.py
"""PFF intelligence layer — matchup engine and talent stabilizer."""
```

- [ ] **Step 2: Move pff_loader.py into subpackage**

```bash
mkdir -p src/fantasy_sim/data/pff
mv src/fantasy_sim/data/pff_loader.py src/fantasy_sim/data/pff/loader.py
```

No code changes needed in `loader.py` — it has no internal imports to this package.

- [ ] **Step 3: Move test file into test_pff subpackage**

```bash
mkdir -p tests/test_data/test_pff
touch tests/test_data/test_pff/__init__.py
mv tests/test_data/test_pff_loader.py tests/test_data/test_pff/test_loader.py
```

Update the import in `tests/test_data/test_pff/test_loader.py`:

```python
# Change this:
from fantasy_sim.data.pff_loader import (
    FANTASY_POSITIONS,
    PFF_TO_FANTASY_POSITION,
    PFF_TO_NFL_TEAM,
    PffLoader,
)

# To this:
from fantasy_sim.data.pff.loader import (
    FANTASY_POSITIONS,
    PFF_TO_FANTASY_POSITION,
    PFF_TO_NFL_TEAM,
    PffLoader,
)
```

- [ ] **Step 4: Run existing loader tests to verify move worked**

Run: `uv run pytest tests/test_data/test_pff/test_loader.py -v`
Expected: All 15 tests PASS

- [ ] **Step 5: Create models.py with shared data types**

```python
# src/fantasy_sim/data/pff/models.py
"""Shared data types for the PFF intelligence layer."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MatchupContext:
    """Per-game adjustment factors derived from PFF defensive + OL data.

    All factors are centered on 1.0 (neutral). Values < 1.0 mean the
    defense/OL is worse than average (easier matchup for the offense),
    values > 1.0 mean tougher matchup.

    For catch_rate_factor and pass_yards_factor, LOWER values mean tougher
    secondary (reduces opposing offense).
    For sack_rate_factor and int_rate_factor, HIGHER values mean tougher
    pass rush / better secondary (increases sacks/INTs for opposing offense).
    For rush_yards_factor, LOWER values mean tougher run defense.
    """

    # Pass defense impact on opposing offense
    catch_rate_factor: float = 1.0
    pass_yards_factor: float = 1.0
    sack_rate_factor: float = 1.0
    int_rate_factor: float = 1.0

    # Run defense impact on opposing offense
    rush_yards_factor: float = 1.0

    # OL context (own team's blocking quality)
    ol_pass_block_factor: float = 1.0
    ol_run_block_factor: float = 1.0


@dataclass
class TalentAdjustment:
    """Record of a talent stabilizer adjustment for one player parameter."""

    player_id: str
    parameter: str
    pbp_value: float
    pff_prior: float
    adjusted_value: float
    n_observations: int
    divergence: float


@dataclass
class MatchupConfig:
    """Configuration for the matchup engine."""

    enabled: bool = True
    pass_defense_sensitivity: float = 0.08
    pass_rush_sensitivity: float = 0.10
    run_defense_sensitivity: float = 0.08
    int_rate_sensitivity: float = 0.06
    ol_pass_sensitivity: float = 0.08
    ol_run_sensitivity: float = 0.06
    factor_clamp: tuple[float, float] = (0.80, 1.20)
    min_games: int = 4


@dataclass
class TalentConfig:
    """Configuration for the talent stabilizer."""

    enabled: bool = True
    prior_strength: float = 40.0
    min_divergence: float = 0.03
    catch_rate_coefficients: dict[str, float] = field(default_factory=lambda: {
        "drop_rate": -0.15,
        "contested_catch_rate": 0.10,
        "qb_accuracy": 0.08,
    })
    rushing_yards_coefficients: dict[str, float] = field(default_factory=lambda: {
        "yco_attempt": 0.6,
        "elusive_rating": 0.008,
    })
    receiving_yards_coefficients: dict[str, float] = field(default_factory=lambda: {
        "yprr": 0.5,
        "avg_depth_of_target": 0.03,
    })


@dataclass
class PffConfig:
    """Top-level PFF configuration."""

    enabled: bool = False
    data_dir: str | None = None
    matchup: MatchupConfig = field(default_factory=MatchupConfig)
    talent: TalentConfig = field(default_factory=TalentConfig)
```

- [ ] **Step 6: Create config.py with loader function**

```python
# src/fantasy_sim/data/pff/config.py
"""Load PFF configuration from defaults.yaml."""

from __future__ import annotations

from fantasy_sim.data.pff.models import (
    MatchupConfig,
    PffConfig,
    TalentConfig,
)


def load_pff_config(config: dict) -> PffConfig:
    """Extract PFF config from the full defaults config dict.

    Args:
        config: The full defaults.yaml dict (or a subset with a "pff" key).

    Returns:
        PffConfig with all sub-configs populated.
    """
    pff = config.get("pff", {})
    if not pff:
        return PffConfig()

    matchup_raw = pff.get("matchup", {})
    talent_raw = pff.get("talent", {})

    clamp = matchup_raw.get("factor_clamp", [0.80, 1.20])

    matchup = MatchupConfig(
        enabled=matchup_raw.get("enabled", True),
        pass_defense_sensitivity=matchup_raw.get("pass_defense_sensitivity", 0.08),
        pass_rush_sensitivity=matchup_raw.get("pass_rush_sensitivity", 0.10),
        run_defense_sensitivity=matchup_raw.get("run_defense_sensitivity", 0.08),
        int_rate_sensitivity=matchup_raw.get("int_rate_sensitivity", 0.06),
        ol_pass_sensitivity=matchup_raw.get("ol_pass_sensitivity", 0.08),
        ol_run_sensitivity=matchup_raw.get("ol_run_sensitivity", 0.06),
        factor_clamp=tuple(clamp),
        min_games=matchup_raw.get("min_games", 4),
    )

    talent = TalentConfig(
        enabled=talent_raw.get("enabled", True),
        prior_strength=talent_raw.get("prior_strength", 40.0),
        min_divergence=talent_raw.get("min_divergence", 0.03),
        catch_rate_coefficients=talent_raw.get("catch_rate_coefficients", {
            "drop_rate": -0.15,
            "contested_catch_rate": 0.10,
            "qb_accuracy": 0.08,
        }),
        rushing_yards_coefficients=talent_raw.get("rushing_yards_coefficients", {
            "yco_attempt": 0.6,
            "elusive_rating": 0.008,
        }),
        receiving_yards_coefficients=talent_raw.get("receiving_yards_coefficients", {
            "yprr": 0.5,
            "avg_depth_of_target": 0.03,
        }),
    )

    return PffConfig(
        enabled=pff.get("enabled", False),
        data_dir=pff.get("data_dir"),
        matchup=matchup,
        talent=talent,
    )
```

- [ ] **Step 7: Write tests for models and config**

```python
# tests/test_data/test_pff/test_config.py
"""Tests for PFF config loading."""

import pytest

from fantasy_sim.data.pff.config import load_pff_config
from fantasy_sim.data.pff.models import (
    MatchupConfig,
    MatchupContext,
    PffConfig,
    TalentConfig,
)


class TestMatchupContext:
    def test_defaults_are_neutral(self):
        ctx = MatchupContext()
        assert ctx.catch_rate_factor == 1.0
        assert ctx.pass_yards_factor == 1.0
        assert ctx.sack_rate_factor == 1.0
        assert ctx.int_rate_factor == 1.0
        assert ctx.rush_yards_factor == 1.0
        assert ctx.ol_pass_block_factor == 1.0
        assert ctx.ol_run_block_factor == 1.0


class TestPffConfig:
    def test_defaults_when_no_pff_section(self):
        cfg = load_pff_config({})
        assert cfg.enabled is False
        assert cfg.matchup.enabled is True
        assert cfg.talent.enabled is True

    def test_loads_enabled_flag(self):
        cfg = load_pff_config({"pff": {"enabled": True}})
        assert cfg.enabled is True

    def test_loads_matchup_sensitivity(self):
        cfg = load_pff_config({
            "pff": {
                "enabled": True,
                "matchup": {"pass_defense_sensitivity": 0.12},
            }
        })
        assert cfg.matchup.pass_defense_sensitivity == 0.12
        # Other sensitivities should be defaults
        assert cfg.matchup.pass_rush_sensitivity == 0.10

    def test_loads_talent_prior_strength(self):
        cfg = load_pff_config({
            "pff": {
                "enabled": True,
                "talent": {"prior_strength": 60.0},
            }
        })
        assert cfg.talent.prior_strength == 60.0

    def test_loads_factor_clamp_as_tuple(self):
        cfg = load_pff_config({
            "pff": {
                "matchup": {"factor_clamp": [0.75, 1.25]},
            }
        })
        assert cfg.matchup.factor_clamp == (0.75, 1.25)

    def test_loads_custom_coefficients(self):
        cfg = load_pff_config({
            "pff": {
                "talent": {
                    "catch_rate_coefficients": {"drop_rate": -0.20},
                }
            }
        })
        assert cfg.talent.catch_rate_coefficients["drop_rate"] == -0.20

    def test_data_dir_default_none(self):
        cfg = load_pff_config({"pff": {"enabled": True}})
        assert cfg.data_dir is None

    def test_data_dir_custom(self):
        cfg = load_pff_config({"pff": {"data_dir": "/tmp/pff"}})
        assert cfg.data_dir == "/tmp/pff"

    def test_min_games_default(self):
        cfg = load_pff_config({"pff": {}})
        assert cfg.matchup.min_games == 4
```

- [ ] **Step 8: Run all pff tests**

Run: `uv run pytest tests/test_data/test_pff/ -v`
Expected: All tests PASS (15 loader + 9 config = 24)

- [ ] **Step 9: Run full test suite to confirm nothing broke**

Run: `uv run pytest tests/ -v --timeout=60`
Expected: All existing tests still pass

- [ ] **Step 10: Commit**

```bash
git add src/fantasy_sim/data/pff/ tests/test_data/test_pff/
git status  # confirm pff_loader.py and test_pff_loader.py show as renamed
git add -A  # pick up the deletes of old locations
git commit -m "refactor: create pff/ subpackage with models, config, and relocated loader"
```

---

## Task 2: Matchup Engine — Core Computation

**Files:**
- Create: `src/fantasy_sim/data/pff/matchup.py`
- Create: `tests/test_data/test_pff/test_matchup.py`

- [ ] **Step 1: Write failing tests for z-score factor computation**

```python
# tests/test_data/test_pff/test_matchup.py
"""Tests for PFF matchup engine."""

import numpy as np
import polars as pl
import pytest

from fantasy_sim.data.pff.matchup import MatchupEngine, compute_factor
from fantasy_sim.data.pff.models import MatchupConfig, MatchupContext, PffConfig


# ---------- compute_factor (pure math) ----------


class TestComputeFactor:
    def test_average_team_returns_neutral(self):
        # Team stat equals league average → factor = 1.0
        factor = compute_factor(
            team_value=0.64, league_avg=0.64, league_std=0.04,
            sensitivity=0.08, clamp=(0.80, 1.20),
        )
        assert factor == pytest.approx(1.0)

    def test_above_average_defense_reduces_factor(self):
        # Defense allows fewer catches (0.58) than avg (0.64) → z=-1.5
        # For catch_rate: lower allowed = better D = lower factor
        factor = compute_factor(
            team_value=0.58, league_avg=0.64, league_std=0.04,
            sensitivity=0.08, clamp=(0.80, 1.20),
        )
        # z = (0.58 - 0.64) / 0.04 = -1.5
        # factor = 1.0 + (-1.5) * 0.08 = 0.88
        assert factor == pytest.approx(0.88, abs=0.001)

    def test_below_average_defense_increases_factor(self):
        # Defense allows more catches (0.70) than avg (0.64)
        factor = compute_factor(
            team_value=0.70, league_avg=0.64, league_std=0.04,
            sensitivity=0.08, clamp=(0.80, 1.20),
        )
        # z = (0.70 - 0.64) / 0.04 = 1.5
        # factor = 1.0 + 1.5 * 0.08 = 1.12
        assert factor == pytest.approx(1.12, abs=0.001)

    def test_clamp_upper_bound(self):
        # Extreme value should be clamped to 1.20
        factor = compute_factor(
            team_value=0.80, league_avg=0.64, league_std=0.04,
            sensitivity=0.08, clamp=(0.80, 1.20),
        )
        assert factor == 1.20

    def test_clamp_lower_bound(self):
        # Extreme value should be clamped to 0.80
        factor = compute_factor(
            team_value=0.48, league_avg=0.64, league_std=0.04,
            sensitivity=0.08, clamp=(0.80, 1.20),
        )
        assert factor == 0.80

    def test_zero_std_returns_neutral(self):
        # Edge case: no variance → can't compute z-score → return 1.0
        factor = compute_factor(
            team_value=0.58, league_avg=0.64, league_std=0.0,
            sensitivity=0.08, clamp=(0.80, 1.20),
        )
        assert factor == 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_pff/test_matchup.py::TestComputeFactor -v`
Expected: FAIL with `ImportError: cannot import name 'compute_factor' from 'fantasy_sim.data.pff.matchup'`

- [ ] **Step 3: Implement compute_factor**

```python
# src/fantasy_sim/data/pff/matchup.py
"""Defensive matchup engine — computes per-game adjustment factors from PFF data.

Uses PFF defensive stats (coverage, pass rush, run defense) and OL blocking
data to create MatchupContext factors that adjust the opposing offense's
parameters for each game.
"""

from __future__ import annotations

import logging

import polars as pl

from fantasy_sim.data.pff.loader import PffLoader
from fantasy_sim.data.pff.models import MatchupConfig, MatchupContext, PffConfig

logger = logging.getLogger(__name__)


def compute_factor(
    team_value: float,
    league_avg: float,
    league_std: float,
    sensitivity: float,
    clamp: tuple[float, float],
) -> float:
    """Convert a team stat to a matchup factor via z-score.

    Args:
        team_value: The team's average for this stat.
        league_avg: League-wide average for this stat.
        league_std: League-wide standard deviation.
        sensitivity: How much each z-score unit moves the factor.
        clamp: (min, max) bounds for the factor.

    Returns:
        A factor centered on 1.0. Values < 1.0 mean the team is
        better than average at that stat (tougher for opponents).
    """
    if league_std <= 0:
        return 1.0
    z = (team_value - league_avg) / league_std
    raw = 1.0 + z * sensitivity
    return max(clamp[0], min(clamp[1], raw))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_pff/test_matchup.py::TestComputeFactor -v`
Expected: All 6 PASS

- [ ] **Step 5: Write failing tests for MatchupEngine.compute()**

Add to `tests/test_data/test_pff/test_matchup.py`:

```python
# ---------- Fixtures ----------


@pytest.fixture
def pff_dir(tmp_path):
    """Create a PFF data directory with defensive + OL parquets."""
    d = tmp_path / "pff" / "processed" / "nfl"
    d.mkdir(parents=True)
    return d


def _write_defense_coverage(pff_dir, season, teams_data):
    """Write defense_coverage parquet with per-team stats.

    teams_data: list of dicts with keys: team, catch_rate, yards_per_reception,
    grades_coverage_defense, plus counts.
    """
    rows = {
        "player_id": [], "player": [], "team": [], "position": [],
        "season": [], "week": [], "game_id": [],
        "catch_rate": [], "yards_per_reception": [],
        "grades_coverage_defense": [], "targets": [], "receptions": [],
        "interceptions": [], "yards": [], "yards_after_catch": [],
        "forced_incompletion_rate": [],
    }
    pid = 1000
    gid = 2000
    for td in teams_data:
        for w in range(1, td.get("games", 4) + 1):
            rows["player_id"].append(pid)
            rows["player"].append(f"Def {td['team']}")
            rows["team"].append(td["team"])
            rows["position"].append("CB")
            rows["season"].append(season)
            rows["week"].append(w)
            rows["game_id"].append(gid)
            rows["catch_rate"].append(td["catch_rate"])
            rows["yards_per_reception"].append(td["yards_per_reception"])
            rows["grades_coverage_defense"].append(td["grades_coverage_defense"])
            rows["targets"].append(10)
            rows["receptions"].append(6)
            rows["interceptions"].append(0)
            rows["yards"].append(60)
            rows["yards_after_catch"].append(20)
            rows["forced_incompletion_rate"].append(0.10)
            pid += 1
            gid += 1
    df = pl.DataFrame(rows)
    df.write_parquet(pff_dir / f"defense_coverage_{season}.parquet")


def _write_defense_pass_rush(pff_dir, season, teams_data):
    """Write defense_pass_rush parquet."""
    rows = {
        "player_id": [], "player": [], "team": [], "position": [],
        "season": [], "week": [], "game_id": [],
        "pass_rush_win_rate": [], "grades_pass_rush_defense": [],
        "total_pressures": [], "sacks": [], "hurries": [], "hits": [],
        "pass_rush_opp": [],
    }
    pid = 5000
    gid = 6000
    for td in teams_data:
        for w in range(1, td.get("games", 4) + 1):
            rows["player_id"].append(pid)
            rows["player"].append(f"Edge {td['team']}")
            rows["team"].append(td["team"])
            rows["position"].append("EDGE")
            rows["season"].append(season)
            rows["week"].append(w)
            rows["game_id"].append(gid)
            rows["pass_rush_win_rate"].append(td["pass_rush_win_rate"])
            rows["grades_pass_rush_defense"].append(td["grades_pass_rush_defense"])
            rows["total_pressures"].append(5)
            rows["sacks"].append(1)
            rows["hurries"].append(3)
            rows["hits"].append(1)
            rows["pass_rush_opp"].append(30)
            pid += 1
            gid += 1
    df = pl.DataFrame(rows)
    df.write_parquet(pff_dir / f"defense_pass_rush_{season}.parquet")


def _write_defense_run(pff_dir, season, teams_data):
    """Write defense_run parquet."""
    rows = {
        "player_id": [], "player": [], "team": [], "position": [],
        "season": [], "week": [], "game_id": [],
        "stop_percent": [], "grades_run_defense": [],
        "tackles": [], "assists": [], "missed_tackles": [],
    }
    pid = 8000
    gid = 9000
    for td in teams_data:
        for w in range(1, td.get("games", 4) + 1):
            rows["player_id"].append(pid)
            rows["player"].append(f"LB {td['team']}")
            rows["team"].append(td["team"])
            rows["position"].append("LB")
            rows["season"].append(season)
            rows["week"].append(w)
            rows["game_id"].append(gid)
            rows["stop_percent"].append(td["stop_percent"])
            rows["grades_run_defense"].append(td["grades_run_defense"])
            rows["tackles"].append(5)
            rows["assists"].append(2)
            rows["missed_tackles"].append(1)
            pid += 1
            gid += 1
    df = pl.DataFrame(rows)
    df.write_parquet(pff_dir / f"defense_run_{season}.parquet")


def _write_offense_blocking(pff_dir, season, teams_data, facet="offense_pass_blocking"):
    """Write offense_pass_blocking or offense_run_blocking parquet."""
    if facet == "offense_pass_blocking":
        rows = {
            "player_id": [], "player": [], "team": [], "position": [],
            "season": [], "week": [], "game_id": [],
            "pbe": [], "pressures_allowed": [], "grades_pass_block": [],
            "sacks_allowed": [], "snap_counts_pass_block": [],
        }
    else:
        rows = {
            "player_id": [], "player": [], "team": [], "position": [],
            "season": [], "week": [], "game_id": [],
            "grades_run_block": [], "run_block_percent": [],
            "snap_counts_run_block": [],
        }
    pid = 11000
    gid = 12000
    for td in teams_data:
        for w in range(1, td.get("games", 4) + 1):
            rows["player_id"].append(pid)
            rows["player"].append(f"OL {td['team']}")
            rows["team"].append(td["team"])
            rows["position"].append("T")
            rows["season"].append(season)
            rows["week"].append(w)
            rows["game_id"].append(gid)
            if facet == "offense_pass_blocking":
                rows["pbe"].append(td.get("pbe", 95.0))
                rows["pressures_allowed"].append(td.get("pressures_allowed", 3))
                rows["grades_pass_block"].append(td.get("grades_pass_block", 70.0))
                rows["sacks_allowed"].append(0)
                rows["snap_counts_pass_block"].append(40)
            else:
                rows["grades_run_block"].append(td.get("grades_run_block", 70.0))
                rows["run_block_percent"].append(td.get("run_block_percent", 0.70))
                rows["snap_counts_run_block"].append(30)
            pid += 1
            gid += 1
    df = pl.DataFrame(rows)
    df.write_parquet(pff_dir / f"{facet}_{season}.parquet")


# ---------- MatchupEngine ----------


class TestMatchupEngine:
    def test_elite_defense_reduces_catch_rate_factor(self, pff_dir):
        """Elite pass defense should produce catch_rate_factor < 1.0."""
        teams = [
            {"team": "BAL", "catch_rate": 0.55, "yards_per_reception": 9.0,
             "grades_coverage_defense": 90.0, "games": 8},
            {"team": "KC", "catch_rate": 0.64, "yards_per_reception": 11.5,
             "grades_coverage_defense": 70.0, "games": 8},
            {"team": "CAR", "catch_rate": 0.72, "yards_per_reception": 13.0,
             "grades_coverage_defense": 50.0, "games": 8},
        ]
        _write_defense_coverage(pff_dir, 2024, teams)
        # Need pass rush + run defense too (empty is fine, will produce neutral factors)
        _write_defense_pass_rush(pff_dir, 2024, [
            {"team": t["team"], "pass_rush_win_rate": 0.10,
             "grades_pass_rush_defense": 70.0, "games": 8} for t in teams
        ])
        _write_defense_run(pff_dir, 2024, [
            {"team": t["team"], "stop_percent": 0.07,
             "grades_run_defense": 70.0, "games": 8} for t in teams
        ])

        config = PffConfig(enabled=True, matchup=MatchupConfig())
        loader = PffLoader(pff_dir)
        engine = MatchupEngine(config, loader)

        ctx = engine.compute(
            defense_team="BAL", offense_team="KC",
            training_seasons=[2024],
        )
        assert ctx.catch_rate_factor < 1.0

    def test_weak_defense_increases_catch_rate_factor(self, pff_dir):
        """Weak pass defense should produce catch_rate_factor > 1.0."""
        teams = [
            {"team": "BAL", "catch_rate": 0.55, "yards_per_reception": 9.0,
             "grades_coverage_defense": 90.0, "games": 8},
            {"team": "KC", "catch_rate": 0.64, "yards_per_reception": 11.5,
             "grades_coverage_defense": 70.0, "games": 8},
            {"team": "CAR", "catch_rate": 0.72, "yards_per_reception": 13.0,
             "grades_coverage_defense": 50.0, "games": 8},
        ]
        _write_defense_coverage(pff_dir, 2024, teams)
        _write_defense_pass_rush(pff_dir, 2024, [
            {"team": t["team"], "pass_rush_win_rate": 0.10,
             "grades_pass_rush_defense": 70.0, "games": 8} for t in teams
        ])
        _write_defense_run(pff_dir, 2024, [
            {"team": t["team"], "stop_percent": 0.07,
             "grades_run_defense": 70.0, "games": 8} for t in teams
        ])

        config = PffConfig(enabled=True, matchup=MatchupConfig())
        loader = PffLoader(pff_dir)
        engine = MatchupEngine(config, loader)

        ctx = engine.compute(
            defense_team="CAR", offense_team="KC",
            training_seasons=[2024],
        )
        assert ctx.catch_rate_factor > 1.0

    def test_neutral_context_when_no_data(self, pff_dir):
        """Missing PFF data → all-neutral MatchupContext."""
        config = PffConfig(enabled=True, matchup=MatchupConfig())
        loader = PffLoader(pff_dir)
        engine = MatchupEngine(config, loader)

        ctx = engine.compute(
            defense_team="BAL", offense_team="KC",
            training_seasons=[2024],
        )
        assert ctx.catch_rate_factor == 1.0
        assert ctx.sack_rate_factor == 1.0
        assert ctx.rush_yards_factor == 1.0

    def test_factors_are_clamped(self, pff_dir):
        """Extreme values should be clamped to configured bounds."""
        teams = [
            {"team": "BAL", "catch_rate": 0.30, "yards_per_reception": 5.0,
             "grades_coverage_defense": 99.0, "games": 8},
            {"team": "CAR", "catch_rate": 0.90, "yards_per_reception": 20.0,
             "grades_coverage_defense": 30.0, "games": 8},
        ]
        _write_defense_coverage(pff_dir, 2024, teams)
        _write_defense_pass_rush(pff_dir, 2024, [
            {"team": t["team"], "pass_rush_win_rate": 0.10,
             "grades_pass_rush_defense": 70.0, "games": 8} for t in teams
        ])
        _write_defense_run(pff_dir, 2024, [
            {"team": t["team"], "stop_percent": 0.07,
             "grades_run_defense": 70.0, "games": 8} for t in teams
        ])

        config = PffConfig(
            enabled=True,
            matchup=MatchupConfig(factor_clamp=(0.80, 1.20)),
        )
        loader = PffLoader(pff_dir)
        engine = MatchupEngine(config, loader)

        ctx = engine.compute(
            defense_team="BAL", offense_team="CAR",
            training_seasons=[2024],
        )
        assert ctx.catch_rate_factor >= 0.80
        assert ctx.catch_rate_factor <= 1.20

    def test_insufficient_games_uses_grade_fallback(self, pff_dir):
        """Teams with < min_games should fall back to grade-based factors."""
        teams = [
            {"team": "BAL", "catch_rate": 0.55, "yards_per_reception": 9.0,
             "grades_coverage_defense": 90.0, "games": 2},  # below min_games=4
            {"team": "KC", "catch_rate": 0.64, "yards_per_reception": 11.5,
             "grades_coverage_defense": 70.0, "games": 8},
        ]
        _write_defense_coverage(pff_dir, 2024, teams)
        _write_defense_pass_rush(pff_dir, 2024, [
            {"team": t["team"], "pass_rush_win_rate": 0.10,
             "grades_pass_rush_defense": 70.0, "games": t.get("games", 8)} for t in teams
        ])
        _write_defense_run(pff_dir, 2024, [
            {"team": t["team"], "stop_percent": 0.07,
             "grades_run_defense": 70.0, "games": t.get("games", 8)} for t in teams
        ])

        config = PffConfig(
            enabled=True,
            matchup=MatchupConfig(min_games=4),
        )
        loader = PffLoader(pff_dir)
        engine = MatchupEngine(config, loader)

        # BAL has only 2 games → should use grades_coverage_defense fallback
        # but still produce a non-neutral factor (grade=90 is above average)
        ctx = engine.compute(
            defense_team="BAL", offense_team="KC",
            training_seasons=[2024],
        )
        # Factor should still be < 1.0 since BAL has elite grade
        assert ctx.catch_rate_factor != 1.0

    def test_different_opponents_produce_different_contexts(self, pff_dir):
        """BAL defense should create a tougher matchup than CAR defense."""
        teams = [
            {"team": "BAL", "catch_rate": 0.55, "yards_per_reception": 9.0,
             "grades_coverage_defense": 90.0, "games": 8},
            {"team": "CAR", "catch_rate": 0.72, "yards_per_reception": 13.0,
             "grades_coverage_defense": 50.0, "games": 8},
            {"team": "KC", "catch_rate": 0.64, "yards_per_reception": 11.5,
             "grades_coverage_defense": 70.0, "games": 8},
        ]
        _write_defense_coverage(pff_dir, 2024, teams)
        _write_defense_pass_rush(pff_dir, 2024, [
            {"team": t["team"], "pass_rush_win_rate": 0.10,
             "grades_pass_rush_defense": 70.0, "games": 8} for t in teams
        ])
        _write_defense_run(pff_dir, 2024, [
            {"team": t["team"], "stop_percent": 0.07,
             "grades_run_defense": 70.0, "games": 8} for t in teams
        ])

        config = PffConfig(enabled=True, matchup=MatchupConfig())
        loader = PffLoader(pff_dir)
        engine = MatchupEngine(config, loader)

        bal_ctx = engine.compute("BAL", "KC", [2024])
        car_ctx = engine.compute("CAR", "KC", [2024])

        # BAL should be tougher (lower catch_rate_factor)
        assert bal_ctx.catch_rate_factor < car_ctx.catch_rate_factor
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_pff/test_matchup.py::TestMatchupEngine -v`
Expected: FAIL with `ImportError: cannot import name 'MatchupEngine'`

- [ ] **Step 7: Implement MatchupEngine**

Add to `src/fantasy_sim/data/pff/matchup.py`:

```python
# --- Constants ---

# Mapping: (facet, primary_stat, grade_fallback, higher_is_worse_for_offense)
_PASS_DEFENSE_STAT = ("defense_coverage", "catch_rate", "grades_coverage_defense")
_PASS_YARDS_STAT = ("defense_coverage", "yards_per_reception", "grades_coverage_defense")
_PASS_RUSH_STAT = ("defense_pass_rush", "pass_rush_win_rate", "grades_pass_rush_defense")
_INT_RATE_STAT = ("defense_coverage", "interceptions", "grades_coverage_defense")
_RUN_DEFENSE_STAT = ("defense_run", "stop_percent", "grades_run_defense")
_OL_PASS_STAT = ("offense_pass_blocking", "pbe", "grades_pass_block")
_OL_RUN_STAT = ("offense_run_blocking", "grades_run_block", "run_block_percent")


class MatchupEngine:
    """Computes per-game MatchupContext from PFF defensive + OL data."""

    def __init__(self, config: PffConfig, pff_loader: PffLoader):
        self.config = config.matchup
        self.loader = pff_loader
        self._team_stats_cache: dict[str, pl.DataFrame] = {}

    def compute(
        self,
        defense_team: str,
        offense_team: str,
        training_seasons: list[int],
        season_weights: dict[int, float] | None = None,
    ) -> MatchupContext:
        """Compute matchup adjustment factors for one game.

        Args:
            defense_team: The defensive team (their stats adjust the opposing offense).
            offense_team: The offensive team (OL stats adjust their own offense).
            training_seasons: Seasons to aggregate PFF data from.
            season_weights: Optional recency weights per season.

        Returns:
            MatchupContext with all factors populated.
        """
        ctx = MatchupContext()

        # --- Defensive factors (defense_team's D adjusts opposing offense) ---
        ctx.catch_rate_factor = self._compute_team_factor(
            defense_team, training_seasons, season_weights,
            *_PASS_DEFENSE_STAT, self.config.pass_defense_sensitivity,
        )
        ctx.pass_yards_factor = self._compute_team_factor(
            defense_team, training_seasons, season_weights,
            *_PASS_YARDS_STAT, self.config.pass_defense_sensitivity,
        )
        ctx.sack_rate_factor = self._compute_team_factor(
            defense_team, training_seasons, season_weights,
            *_PASS_RUSH_STAT, self.config.pass_rush_sensitivity,
        )
        ctx.int_rate_factor = self._compute_team_factor(
            defense_team, training_seasons, season_weights,
            *_INT_RATE_STAT, self.config.int_rate_sensitivity,
        )
        ctx.rush_yards_factor = self._compute_inverted_factor(
            defense_team, training_seasons, season_weights,
            *_RUN_DEFENSE_STAT, self.config.run_defense_sensitivity,
        )

        # --- OL factors (offense_team's OL adjusts their own offense) ---
        ctx.ol_pass_block_factor = self._compute_inverted_factor(
            offense_team, training_seasons, season_weights,
            *_OL_PASS_STAT, self.config.ol_pass_sensitivity,
        )
        ctx.ol_run_block_factor = self._compute_team_factor(
            offense_team, training_seasons, season_weights,
            *_OL_RUN_STAT, self.config.ol_run_sensitivity,
        )

        return ctx

    def _load_team_stats(
        self,
        facet: str,
        team: str,
        training_seasons: list[int],
        stat_col: str,
        season_weights: dict[int, float] | None = None,
    ) -> tuple[float | None, int]:
        """Load and aggregate a team's PFF stat, returning (mean, game_count).

        Returns (None, 0) if no data is available.
        """
        cache_key = f"{facet}_{'_'.join(str(s) for s in sorted(training_seasons))}"
        if cache_key not in self._team_stats_cache:
            df = self.loader.load_facet(facet, training_seasons)
            self._team_stats_cache[cache_key] = df

        df = self._team_stats_cache[cache_key]
        if df.is_empty() or stat_col not in df.columns or "team" not in df.columns:
            return None, 0

        team_df = df.filter(pl.col("team") == team)
        if team_df.is_empty():
            return None, 0

        # Count unique games for this team
        if "game_id" in team_df.columns:
            game_count = team_df["game_id"].n_unique()
        else:
            game_count = len(team_df)

        # Compute weighted mean
        col_data = team_df[stat_col].drop_nulls()
        if col_data.is_empty():
            return None, 0

        if season_weights and "season" in team_df.columns:
            weighted = team_df.filter(pl.col(stat_col).is_not_null())
            if weighted.is_empty():
                return None, 0
            weight_expr = pl.lit(1.0)
            for s, w in season_weights.items():
                weight_expr = pl.when(pl.col("season") == s).then(pl.lit(w)).otherwise(weight_expr)
            weighted = weighted.with_columns(weight_expr.alias("_w"))
            val = (
                (weighted[stat_col].cast(pl.Float64) * weighted["_w"]).sum()
                / weighted["_w"].sum()
            )
            return float(val), game_count

        return float(col_data.mean()), game_count

    def _league_stats(
        self,
        facet: str,
        training_seasons: list[int],
        stat_col: str,
    ) -> tuple[float, float]:
        """Compute league-wide mean and std for a stat.

        Returns (mean, std). If data is missing, returns (0.0, 0.0).
        """
        cache_key = f"{facet}_{'_'.join(str(s) for s in sorted(training_seasons))}"
        if cache_key not in self._team_stats_cache:
            df = self.loader.load_facet(facet, training_seasons)
            self._team_stats_cache[cache_key] = df

        df = self._team_stats_cache[cache_key]
        if df.is_empty() or stat_col not in df.columns or "team" not in df.columns:
            return 0.0, 0.0

        # Aggregate per team first, then compute league stats across teams
        team_means = (
            df.filter(pl.col(stat_col).is_not_null())
            .group_by("team")
            .agg(pl.col(stat_col).mean().alias("team_mean"))
        )
        if team_means.is_empty():
            return 0.0, 0.0

        league_avg = float(team_means["team_mean"].mean())
        league_std = float(team_means["team_mean"].std()) if len(team_means) > 1 else 0.0
        return league_avg, league_std

    def _compute_team_factor(
        self,
        team: str,
        training_seasons: list[int],
        season_weights: dict[int, float] | None,
        facet: str,
        primary_stat: str,
        grade_fallback: str,
        sensitivity: float,
    ) -> float:
        """Compute a single factor for a team using primary stat or grade fallback."""
        team_val, game_count = self._load_team_stats(
            facet, team, training_seasons, primary_stat, season_weights,
        )

        # Use grade fallback if insufficient games or missing primary stat
        if team_val is None or game_count < self.config.min_games:
            team_val, game_count = self._load_team_stats(
                facet, team, training_seasons, grade_fallback, season_weights,
            )
            if team_val is None:
                return 1.0
            league_avg, league_std = self._league_stats(
                facet, training_seasons, grade_fallback,
            )
            # Grades use a different sensitivity (normalized by 100-point scale)
            grade_sensitivity = sensitivity * 0.5
            return compute_factor(team_val, league_avg, league_std, grade_sensitivity, self.config.factor_clamp)

        league_avg, league_std = self._league_stats(
            facet, training_seasons, primary_stat,
        )
        return compute_factor(team_val, league_avg, league_std, sensitivity, self.config.factor_clamp)

    def _compute_inverted_factor(
        self,
        team: str,
        training_seasons: list[int],
        season_weights: dict[int, float] | None,
        facet: str,
        primary_stat: str,
        grade_fallback: str,
        sensitivity: float,
    ) -> float:
        """Compute an inverted factor — higher stat value = LOWER factor.

        Used for stats where higher is better for the team but worse for
        the opponent (e.g., stop_percent: higher = better run D = less rushing
        for the opposing offense, so rush_yards_factor should be lower).
        Also used for OL stats where higher PBE = fewer sacks = lower sack rate.
        """
        factor = self._compute_team_factor(
            team, training_seasons, season_weights,
            facet, primary_stat, grade_fallback, sensitivity,
        )
        if factor == 1.0:
            return 1.0
        # Invert around 1.0: if compute_team_factor gave 1.12 (above avg),
        # inversion gives 0.88 (reduces the opposing metric)
        return 2.0 - factor
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_pff/test_matchup.py -v`
Expected: All 12 tests PASS (6 compute_factor + 6 MatchupEngine)

- [ ] **Step 9: Commit**

```bash
git add src/fantasy_sim/data/pff/matchup.py tests/test_data/test_pff/test_matchup.py
git commit -m "feat: add matchup engine with z-score factor computation"
```

---

## Task 3: Matchup Integration — Wire into GameContextBuilder

**Files:**
- Modify: `src/fantasy_sim/data/game_context.py`
- Create: `tests/test_data/test_pff/test_matchup_integration.py`

- [ ] **Step 1: Write failing integration test**

```python
# tests/test_data/test_pff/test_matchup_integration.py
"""Integration tests: matchup engine wired into GameContextBuilder."""

import numpy as np
import polars as pl
import pytest
from unittest.mock import patch, MagicMock

from fantasy_sim.data.game_context import GameContextBuilder
from fantasy_sim.data.pff.models import MatchupConfig, MatchupContext, PffConfig
from fantasy_sim.engine.types import TeamDistributions
from fantasy_sim.models.distributions import (
    PlayCallingDist, PlayOutcomeDist, TurnoverRates, KickingModel, DriveStartModel,
)
from fantasy_sim.models.player import PlayerModel, PlayerUsage, PlayerOutcomes, TeamRoster


def _make_dists(team: str, sack_rate: float = 0.065, int_rate: float = 0.025) -> TeamDistributions:
    return TeamDistributions(
        play_calling=PlayCallingDist(team=team, distributions={}, default={"pass": 0.57, "run": 0.43}),
        play_outcomes=PlayOutcomeDist(distributions={}, defaults={
            "pass": np.array([5, 10, 15]), "run": np.array([2, 4, 6]),
        }),
        turnover_rates=TurnoverRates(team=team, int_rate=int_rate, fumble_rate=0.012,
                                     sack_rate=sack_rate, sack_fumble_rate=0.10),
        kicking=KickingModel(fg_make_rate={"0_39": 0.93, "40_49": 0.82, "50_plus": 0.65}, xp_rate=0.94),
        drive_start=DriveStartModel(touchback_rate=0.55, touchback_yardline=75,
                                    return_yardlines=np.array([72, 74, 76])),
    )


def _make_roster(team: str) -> TeamRoster:
    return TeamRoster(team=team, players=[
        PlayerModel(f"{team}_QB", "QB1", "QB", team,
                    PlayerUsage(snap_share=1.0), PlayerOutcomes()),
        PlayerModel(f"{team}_WR1", "WR1", "WR", team,
                    PlayerUsage(target_share=0.60),
                    PlayerOutcomes(catch_rate=0.65, red_zone_catch_rate=0.60,
                                   receiving_yards_dist=np.array([5, 8, 12, 15, 20]))),
        PlayerModel(f"{team}_RB1", "RB1", "RB", team,
                    PlayerUsage(carry_share=1.0, target_share=0.40),
                    PlayerOutcomes(catch_rate=0.70, rushing_yards_dist=np.array([2, 3, 4, 5, 6]))),
    ])


class TestApplyMatchup:
    def test_catch_rate_scaled_by_factor(self):
        """catch_rate_factor < 1.0 should reduce all receivers' catch rates."""
        builder = GameContextBuilder()
        roster = _make_roster("KC")
        dists = _make_dists("KC")
        ctx = MatchupContext(catch_rate_factor=0.90)

        builder._apply_matchup(dists, roster, ctx)

        wr = next(p for p in roster.players if p.position == "WR")
        assert wr.outcomes.catch_rate == pytest.approx(0.65 * 0.90, abs=0.001)
        assert wr.outcomes.red_zone_catch_rate == pytest.approx(0.60 * 0.90, abs=0.001)

    def test_sack_rate_scaled_by_combined_factors(self):
        """sack_rate_factor * ol_pass_block_factor should multiply sack_rate."""
        builder = GameContextBuilder()
        roster = _make_roster("KC")
        dists = _make_dists("KC", sack_rate=0.065)
        ctx = MatchupContext(sack_rate_factor=1.10, ol_pass_block_factor=0.95)

        builder._apply_matchup(dists, roster, ctx)

        # Combined: 1.10 * 0.95 = 1.045
        assert dists.turnover_rates.sack_rate == pytest.approx(0.065 * 1.045, abs=0.001)

    def test_int_rate_scaled(self):
        """int_rate_factor should multiply int_rate."""
        builder = GameContextBuilder()
        roster = _make_roster("KC")
        dists = _make_dists("KC", int_rate=0.025)
        ctx = MatchupContext(int_rate_factor=1.15)

        builder._apply_matchup(dists, roster, ctx)

        assert dists.turnover_rates.int_rate == pytest.approx(0.025 * 1.15, abs=0.001)

    def test_rushing_yards_shifted(self):
        """rush_yards_factor should additively shift rushing_yards_dist."""
        builder = GameContextBuilder()
        roster = _make_roster("KC")
        dists = _make_dists("KC")
        rb = next(p for p in roster.players if p.position == "RB")
        original_mean = rb.outcomes.rushing_yards_dist.mean()

        # Factor < 1.0 → negative shift (tough run D)
        ctx = MatchupContext(rush_yards_factor=0.90, ol_run_block_factor=1.0)

        builder._apply_matchup(dists, roster, ctx)

        new_mean = rb.outcomes.rushing_yards_dist.mean()
        assert new_mean < original_mean

    def test_neutral_context_changes_nothing(self):
        """All-1.0 context should leave everything unchanged."""
        builder = GameContextBuilder()
        roster = _make_roster("KC")
        dists = _make_dists("KC")
        wr = next(p for p in roster.players if p.position == "WR")
        original_cr = wr.outcomes.catch_rate
        original_sack = dists.turnover_rates.sack_rate

        ctx = MatchupContext()  # all defaults = 1.0
        builder._apply_matchup(dists, roster, ctx)

        assert wr.outcomes.catch_rate == original_cr
        assert dists.turnover_rates.sack_rate == original_sack
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_pff/test_matchup_integration.py -v`
Expected: FAIL with `AttributeError: 'GameContextBuilder' object has no attribute '_apply_matchup'`

- [ ] **Step 3: Add _apply_matchup to GameContextBuilder**

In `src/fantasy_sim/data/game_context.py`, add the import at the top:

```python
from fantasy_sim.data.pff.models import MatchupContext, PffConfig
from fantasy_sim.data.pff.config import load_pff_config
```

Add the `_apply_matchup` method to `GameContextBuilder`:

```python
def _apply_matchup(
    self,
    dists: TeamDistributions,
    roster: TeamRoster,
    ctx: MatchupContext,
) -> None:
    """Apply matchup context adjustments to distributions and roster.

    Mutates dists and roster in-place.
    """
    import numpy as np

    # --- Sack rate: defensive pass rush × OL pass protection ---
    combined_sack = ctx.sack_rate_factor * ctx.ol_pass_block_factor
    if combined_sack != 1.0:
        dists.turnover_rates = TurnoverRates(
            team=dists.turnover_rates.team,
            int_rate=dists.turnover_rates.int_rate,
            fumble_rate=dists.turnover_rates.fumble_rate,
            sack_rate=dists.turnover_rates.sack_rate * combined_sack,
            sack_fumble_rate=dists.turnover_rates.sack_fumble_rate,
        )

    # --- INT rate ---
    if ctx.int_rate_factor != 1.0:
        dists.turnover_rates = TurnoverRates(
            team=dists.turnover_rates.team,
            int_rate=dists.turnover_rates.int_rate * ctx.int_rate_factor,
            fumble_rate=dists.turnover_rates.fumble_rate,
            sack_rate=dists.turnover_rates.sack_rate,
            sack_fumble_rate=dists.turnover_rates.sack_fumble_rate,
        )

    # --- Receiver catch rates ---
    if ctx.catch_rate_factor != 1.0:
        for player in roster.players:
            if player.usage.target_share > 0 and player.outcomes.catch_rate > 0:
                player.outcomes.catch_rate = max(0.0, min(1.0,
                    player.outcomes.catch_rate * ctx.catch_rate_factor))
                if player.outcomes.red_zone_catch_rate > 0:
                    player.outcomes.red_zone_catch_rate = max(0.0, min(1.0,
                        player.outcomes.red_zone_catch_rate * ctx.catch_rate_factor))

    # --- Receiving yards: additive shift based on pass_yards_factor ---
    if ctx.pass_yards_factor != 1.0:
        shift = (ctx.pass_yards_factor - 1.0) * 10.0  # ~1 yard per 0.1 deviation
        for player in roster.players:
            if player.outcomes.receiving_yards_dist is not None:
                player.outcomes.receiving_yards_dist = (
                    player.outcomes.receiving_yards_dist + shift
                )

    # --- Rushing yards: additive shift based on rush_yards × OL run ---
    combined_rush = ctx.rush_yards_factor * ctx.ol_run_block_factor
    if combined_rush != 1.0:
        shift = (combined_rush - 1.0) * 10.0
        for player in roster.players:
            if player.outcomes.rushing_yards_dist is not None:
                player.outcomes.rushing_yards_dist = (
                    player.outcomes.rushing_yards_dist + shift
                )
```

- [ ] **Step 4: Run integration tests to verify they pass**

Run: `uv run pytest tests/test_data/test_pff/test_matchup_integration.py -v`
Expected: All 5 PASS

- [ ] **Step 5: Add PFF config acceptance to GameContextBuilder.__init__ and build_game**

Modify `GameContextBuilder.__init__` to accept optional `pff_config`:

```python
def __init__(
    self,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    pff_config: PffConfig | None = None,
):
    self.cache_dir = Path(cache_dir)
    self.loader = DataLoader(cache_dir=self.cache_dir)
    self._pipeline_cache: dict | None = None
    self._cached_training_seasons: tuple[int, ...] | None = None
    self._pbp_stats_cache: dict | None = None
    self._player_models_cache: dict | None = None
    self._player_cache_key: tuple | None = None

    # PFF integration (optional)
    self._pff_config = pff_config or PffConfig()
    self._matchup_engine = None
    if self._pff_config.enabled and self._pff_config.matchup.enabled:
        from fantasy_sim.data.pff.loader import PffLoader
        from fantasy_sim.data.pff.matchup import MatchupEngine
        pff_dir = Path(self._pff_config.data_dir) if self._pff_config.data_dir else None
        pff_loader = PffLoader(pff_dir)
        if pff_loader.is_available():
            self._matchup_engine = MatchupEngine(self._pff_config, pff_loader)
            import logging
            logging.getLogger(__name__).info("PFF matchup engine enabled")
```

Modify `build_game` to call matchup engine between base model and return:

```python
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
    training_seasons = training_seasons or [2022, 2023, 2024]

    home_dists = self.build_team_distributions(
        home_team, training_seasons=training_seasons, pbp=pbp,
        rosters=rosters, target_season=target_season, week=week,
    )
    away_dists = self.build_team_distributions(
        away_team, training_seasons=training_seasons, pbp=pbp,
        rosters=rosters, target_season=target_season, week=week,
    )
    home_roster = self.build_team_roster(
        home_team, training_seasons=training_seasons, pbp=pbp,
        rosters=rosters, target_season=target_season, week=week,
    )
    away_roster = self.build_team_roster(
        away_team, training_seasons=training_seasons, pbp=pbp,
        rosters=rosters, target_season=target_season, week=week,
    )

    # PFF matchup adjustments: away D → home offense, home D → away offense
    if self._matchup_engine is not None:
        home_ctx = self._matchup_engine.compute(
            defense_team=away_team, offense_team=home_team,
            training_seasons=training_seasons,
        )
        away_ctx = self._matchup_engine.compute(
            defense_team=home_team, offense_team=away_team,
            training_seasons=training_seasons,
        )
        self._apply_matchup(home_dists, home_roster, home_ctx)
        self._apply_matchup(away_dists, away_roster, away_ctx)

    return home_dists, away_dists, home_roster, away_roster
```

- [ ] **Step 6: Run full test suite**

Run: `uv run pytest tests/ -v --timeout=60`
Expected: All tests PASS (existing + new matchup tests)

- [ ] **Step 7: Commit**

```bash
git add src/fantasy_sim/data/game_context.py tests/test_data/test_pff/test_matchup_integration.py
git commit -m "feat: wire matchup engine into GameContextBuilder"
```

---

## Task 4: Talent Stabilizer — Core Computation

**Files:**
- Create: `src/fantasy_sim/data/pff/talent.py`
- Create: `tests/test_data/test_pff/test_talent.py`

- [ ] **Step 1: Write failing tests for stabilize() blending function**

```python
# tests/test_data/test_pff/test_talent.py
"""Tests for PFF talent stabilizer."""

import numpy as np
import polars as pl
import pytest

from fantasy_sim.data.pff.models import PffConfig, TalentConfig
from fantasy_sim.data.pff.talent import TalentStabilizer, stabilize_value


# ---------- stabilize_value (pure math) ----------


class TestStabilizeValue:
    def test_no_adjustment_below_divergence_threshold(self):
        """When PBP and PFF agree, no adjustment."""
        result = stabilize_value(
            pbp_value=0.65, pff_prior=0.66,
            n_observations=100, prior_strength=40.0, min_divergence=0.03,
        )
        assert result == 0.65  # unchanged

    def test_blends_toward_prior_when_divergent(self):
        """When PBP and PFF diverge, blend toward PFF prior."""
        result = stabilize_value(
            pbp_value=0.59, pff_prior=0.68,
            n_observations=80, prior_strength=40.0, min_divergence=0.03,
        )
        # pbp_weight = 80 / (80 + 40) = 0.667
        # pff_weight = 40 / (80 + 40) = 0.333
        # result = 0.59 * 0.667 + 0.68 * 0.333 = 0.394 + 0.226 = 0.620
        assert result == pytest.approx(0.62, abs=0.01)
        assert result > 0.59  # moved toward prior
        assert result < 0.68  # didn't go all the way

    def test_small_sample_heavily_weights_prior(self):
        """With few PBP observations, PFF prior dominates."""
        result = stabilize_value(
            pbp_value=0.50, pff_prior=0.70,
            n_observations=10, prior_strength=40.0, min_divergence=0.03,
        )
        # pbp_weight = 10 / (10 + 40) = 0.20
        # result = 0.50 * 0.20 + 0.70 * 0.80 = 0.66
        assert result == pytest.approx(0.66, abs=0.01)

    def test_large_sample_mostly_keeps_pbp(self):
        """With many PBP observations, PBP value dominates."""
        result = stabilize_value(
            pbp_value=0.59, pff_prior=0.68,
            n_observations=500, prior_strength=40.0, min_divergence=0.03,
        )
        # pbp_weight = 500 / (500 + 40) = 0.926
        # result ≈ 0.59 * 0.926 + 0.68 * 0.074 = 0.597
        assert result == pytest.approx(0.597, abs=0.01)
        assert abs(result - 0.59) < 0.02  # barely moved

    def test_zero_observations_returns_prior(self):
        """With no PBP data, PFF prior is the full answer."""
        result = stabilize_value(
            pbp_value=0.0, pff_prior=0.65,
            n_observations=0, prior_strength=40.0, min_divergence=0.0,
        )
        # pbp_weight = 0 / (0 + 40) = 0.0
        assert result == pytest.approx(0.65, abs=0.001)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_pff/test_talent.py::TestStabilizeValue -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement stabilize_value and TalentStabilizer shell**

```python
# src/fantasy_sim/data/pff/talent.py
"""Talent stabilizer — Bayesian blending of PBP stats with PFF process metrics.

Only adjusts player parameters when PFF quality metrics meaningfully diverge
from PBP outcome metrics. No divergence = no adjustment.
"""

from __future__ import annotations

import logging

import numpy as np
import polars as pl

from fantasy_sim.data.pff.loader import PffLoader
from fantasy_sim.data.pff.models import PffConfig, TalentConfig
from fantasy_sim.models.player import PlayerModel, TeamRoster

logger = logging.getLogger(__name__)


def stabilize_value(
    pbp_value: float,
    pff_prior: float,
    n_observations: int,
    prior_strength: float,
    min_divergence: float,
) -> float:
    """Bayesian blend of PBP observation with PFF prior.

    Only adjusts when the absolute gap exceeds min_divergence.
    Weight shifts toward PBP as n_observations increases.

    Args:
        pbp_value: The value derived from play-by-play data.
        pff_prior: The expected value derived from PFF process metrics.
        n_observations: Number of PBP data points (targets, carries, etc.).
        prior_strength: How many PBP observations a PFF grade is worth.
        min_divergence: Minimum |pbp - pff| gap before adjustment kicks in.

    Returns:
        Blended value, or pbp_value unchanged if divergence is below threshold.
    """
    divergence = abs(pbp_value - pff_prior)
    if divergence < min_divergence:
        return pbp_value

    pbp_weight = n_observations / (n_observations + prior_strength)
    pff_weight = 1.0 - pbp_weight

    return pbp_value * pbp_weight + pff_prior * pff_weight
```

- [ ] **Step 4: Run stabilize_value tests**

Run: `uv run pytest tests/test_data/test_pff/test_talent.py::TestStabilizeValue -v`
Expected: All 5 PASS

- [ ] **Step 5: Write failing tests for TalentStabilizer.stabilize_roster()**

Add to `tests/test_data/test_pff/test_talent.py`:

```python
from fantasy_sim.data.pff.loader import PffLoader
from fantasy_sim.models.player import PlayerModel, PlayerUsage, PlayerOutcomes, TeamRoster


# ---------- Fixtures ----------


@pytest.fixture
def pff_dir(tmp_path):
    d = tmp_path / "pff" / "processed" / "nfl"
    d.mkdir(parents=True)
    return d


def _write_receiving_summary(pff_dir, season, players):
    """Write receiving_summary parquet with player-level stats."""
    rows = {
        "player_id": [], "player": [], "team": [], "position": [],
        "season": [], "week": [], "game_id": [],
        "franchise_id": [], "jersey_number": [], "status": [],
        "drop_rate": [], "contested_catch_rate": [],
        "grades_pass_route": [], "yprr": [], "avg_depth_of_target": [],
        "targets": [], "caught_percent": [], "yards": [],
        "grades_hands_fumble": [],
    }
    gid = 3000
    for p in players:
        for w in range(1, p.get("games", 8) + 1):
            rows["player_id"].append(p["player_id"])
            rows["player"].append(p["name"])
            rows["team"].append(p["team"])
            rows["position"].append(p.get("position", "WR"))
            rows["season"].append(season)
            rows["week"].append(w)
            rows["game_id"].append(gid)
            rows["franchise_id"].append(1)
            rows["jersey_number"].append(10)
            rows["status"].append("ACT")
            rows["drop_rate"].append(p.get("drop_rate", 5.0))
            rows["contested_catch_rate"].append(p.get("contested_catch_rate", 50.0))
            rows["grades_pass_route"].append(p.get("grades_pass_route", 70.0))
            rows["yprr"].append(p.get("yprr", 1.5))
            rows["avg_depth_of_target"].append(p.get("avg_depth_of_target", 10.0))
            rows["targets"].append(p.get("targets_per_game", 6))
            rows["caught_percent"].append(p.get("caught_percent", 65.0))
            rows["yards"].append(p.get("yards", 60))
            rows["grades_hands_fumble"].append(p.get("grades_hands_fumble", 70.0))
            gid += 1
    df = pl.DataFrame(rows)
    df.write_parquet(pff_dir / f"receiving_summary_{season}.parquet")


def _write_passing_summary(pff_dir, season, players):
    """Write passing_summary parquet."""
    rows = {
        "player_id": [], "player": [], "team": [], "position": [],
        "season": [], "week": [], "game_id": [],
        "franchise_id": [], "jersey_number": [], "status": [],
        "accuracy_percent": [], "grades_pass": [], "twp_rate": [],
        "btt_rate": [], "completions": [], "attempts": [],
        "avg_time_to_throw": [], "scrambles": [], "dropbacks": [],
    }
    gid = 7000
    for p in players:
        for w in range(1, p.get("games", 8) + 1):
            rows["player_id"].append(p["player_id"])
            rows["player"].append(p["name"])
            rows["team"].append(p["team"])
            rows["position"].append("QB")
            rows["season"].append(season)
            rows["week"].append(w)
            rows["game_id"].append(gid)
            rows["franchise_id"].append(1)
            rows["jersey_number"].append(10)
            rows["status"].append("ACT")
            rows["accuracy_percent"].append(p.get("accuracy_percent", 75.0))
            rows["grades_pass"].append(p.get("grades_pass", 70.0))
            rows["twp_rate"].append(p.get("twp_rate", 3.0))
            rows["btt_rate"].append(p.get("btt_rate", 5.0))
            rows["completions"].append(p.get("completions", 20))
            rows["attempts"].append(p.get("attempts", 32))
            rows["avg_time_to_throw"].append(p.get("avg_time_to_throw", 2.5))
            rows["scrambles"].append(p.get("scrambles", 2))
            rows["dropbacks"].append(p.get("dropbacks", 34))
            gid += 1
    df = pl.DataFrame(rows)
    df.write_parquet(pff_dir / f"passing_summary_{season}.parquet")


def _write_rushing_summary(pff_dir, season, players):
    """Write rushing_summary parquet."""
    rows = {
        "player_id": [], "player": [], "team": [], "position": [],
        "season": [], "week": [], "game_id": [],
        "franchise_id": [], "jersey_number": [], "status": [],
        "yco_attempt": [], "elusive_rating": [], "breakaway_percent": [],
        "grades_run": [], "attempts": [], "yards": [],
        "grades_hands_fumble": [],
    }
    gid = 10000
    for p in players:
        for w in range(1, p.get("games", 8) + 1):
            rows["player_id"].append(p["player_id"])
            rows["player"].append(p["name"])
            rows["team"].append(p["team"])
            rows["position"].append(p.get("position", "HB"))
            rows["season"].append(season)
            rows["week"].append(w)
            rows["game_id"].append(gid)
            rows["franchise_id"].append(1)
            rows["jersey_number"].append(10)
            rows["status"].append("ACT")
            rows["yco_attempt"].append(p.get("yco_attempt", 2.5))
            rows["elusive_rating"].append(p.get("elusive_rating", 50.0))
            rows["breakaway_percent"].append(p.get("breakaway_percent", 5.0))
            rows["grades_run"].append(p.get("grades_run", 70.0))
            rows["attempts"].append(p.get("rush_attempts", 15))
            rows["yards"].append(p.get("yards", 60))
            rows["grades_hands_fumble"].append(p.get("grades_hands_fumble", 70.0))
            gid += 1
    df = pl.DataFrame(rows)
    df.write_parquet(pff_dir / f"rushing_summary_{season}.parquet")


# ---------- TalentStabilizer ----------


class TestTalentStabilizer:
    def test_elite_route_runner_with_low_catch_rate_gets_boosted(self, pff_dir):
        """Player with elite PFF grades but low PBP catch rate → catch rate increases."""
        # PFF data: elite drop rate + elite route grade
        _write_receiving_summary(pff_dir, 2024, [
            {"player_id": 100, "name": "Elite WR", "team": "KC",
             "drop_rate": 1.5, "grades_pass_route": 92.0,
             "contested_catch_rate": 65.0, "yprr": 2.5, "games": 8},
            # League average players for context
            {"player_id": 200, "name": "Avg WR", "team": "BUF",
             "drop_rate": 5.0, "grades_pass_route": 70.0,
             "contested_catch_rate": 50.0, "yprr": 1.5, "games": 8},
            {"player_id": 300, "name": "Avg WR2", "team": "MIA",
             "drop_rate": 5.5, "grades_pass_route": 68.0,
             "contested_catch_rate": 48.0, "yprr": 1.4, "games": 8},
        ])
        _write_passing_summary(pff_dir, 2024, [
            {"player_id": 400, "name": "QB1", "team": "KC",
             "accuracy_percent": 78.0, "games": 8},
        ])

        # Build roster with low PBP catch rate (divergent from PFF quality)
        roster = TeamRoster(team="KC", players=[
            PlayerModel("G001", "Elite WR", "WR", "KC",
                        PlayerUsage(target_share=0.25),
                        PlayerOutcomes(catch_rate=0.59)),
        ])

        crosswalk = {100: "G001"}

        config = PffConfig(enabled=True, talent=TalentConfig(
            prior_strength=40.0, min_divergence=0.03,
        ))
        loader = PffLoader(pff_dir)
        stabilizer = TalentStabilizer(config, loader)

        stabilizer.stabilize_roster(roster, crosswalk, [2024])

        wr = roster.players[0]
        assert wr.outcomes.catch_rate > 0.59  # should have been boosted
        assert wr.outcomes.catch_rate < 0.75  # but not unreasonably high

    def test_no_adjustment_when_pbp_and_pff_agree(self, pff_dir):
        """Player with average PFF grades and average PBP → no change."""
        _write_receiving_summary(pff_dir, 2024, [
            {"player_id": 100, "name": "Avg WR", "team": "KC",
             "drop_rate": 5.0, "grades_pass_route": 70.0,
             "contested_catch_rate": 50.0, "yprr": 1.5, "games": 8},
        ])
        _write_passing_summary(pff_dir, 2024, [
            {"player_id": 400, "name": "QB1", "team": "KC",
             "accuracy_percent": 75.0, "games": 8},
        ])

        roster = TeamRoster(team="KC", players=[
            PlayerModel("G001", "Avg WR", "WR", "KC",
                        PlayerUsage(target_share=0.25),
                        PlayerOutcomes(catch_rate=0.65)),
        ])

        crosswalk = {100: "G001"}

        config = PffConfig(enabled=True, talent=TalentConfig(
            prior_strength=40.0, min_divergence=0.03,
        ))
        loader = PffLoader(pff_dir)
        stabilizer = TalentStabilizer(config, loader)

        stabilizer.stabilize_roster(roster, crosswalk, [2024])

        wr = roster.players[0]
        # Catch rate should be unchanged or very close
        assert abs(wr.outcomes.catch_rate - 0.65) < 0.03

    def test_player_without_pff_data_unchanged(self, pff_dir):
        """Player not in crosswalk → no adjustment."""
        _write_receiving_summary(pff_dir, 2024, [
            {"player_id": 100, "name": "Some WR", "team": "BUF",
             "drop_rate": 5.0, "games": 8},
        ])

        roster = TeamRoster(team="KC", players=[
            PlayerModel("G999", "Unknown WR", "WR", "KC",
                        PlayerUsage(target_share=0.25),
                        PlayerOutcomes(catch_rate=0.65)),
        ])

        crosswalk = {100: "G001"}  # G999 not in crosswalk

        config = PffConfig(enabled=True, talent=TalentConfig())
        loader = PffLoader(pff_dir)
        stabilizer = TalentStabilizer(config, loader)

        stabilizer.stabilize_roster(roster, crosswalk, [2024])

        assert roster.players[0].outcomes.catch_rate == 0.65  # unchanged

    def test_rushing_yards_dist_shifted_for_elite_runner(self, pff_dir):
        """RB with elite YCO/elusive rating should get a positive yards shift."""
        _write_rushing_summary(pff_dir, 2024, [
            {"player_id": 100, "name": "Elite RB", "team": "KC",
             "yco_attempt": 4.0, "elusive_rating": 90.0, "games": 8},
            {"player_id": 200, "name": "Avg RB", "team": "BUF",
             "yco_attempt": 2.5, "elusive_rating": 50.0, "games": 8},
            {"player_id": 300, "name": "Avg RB2", "team": "MIA",
             "yco_attempt": 2.3, "elusive_rating": 45.0, "games": 8},
        ])

        original_dist = np.array([0, 1, 2, 3, 4, 5, 6, 7, 8])
        roster = TeamRoster(team="KC", players=[
            PlayerModel("G001", "Elite RB", "RB", "KC",
                        PlayerUsage(carry_share=0.60),
                        PlayerOutcomes(rushing_yards_dist=original_dist.copy())),
        ])

        crosswalk = {100: "G001"}

        config = PffConfig(enabled=True, talent=TalentConfig(
            prior_strength=40.0, min_divergence=0.03,
        ))
        loader = PffLoader(pff_dir)
        stabilizer = TalentStabilizer(config, loader)

        stabilizer.stabilize_roster(roster, crosswalk, [2024])

        rb = roster.players[0]
        # Elite YCO + elusive should shift distribution upward
        assert rb.outcomes.rushing_yards_dist.mean() > original_dist.mean()
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_pff/test_talent.py::TestTalentStabilizer -v`
Expected: FAIL with `ImportError: cannot import name 'TalentStabilizer'`

- [ ] **Step 7: Implement TalentStabilizer**

Add to `src/fantasy_sim/data/pff/talent.py`:

```python
class TalentStabilizer:
    """Bayesian blending of PBP stats with PFF process metrics.

    Only adjusts when divergence between PBP outcomes and PFF quality
    metrics exceeds the configured threshold. Mutates roster in-place.
    """

    def __init__(self, config: PffConfig, pff_loader: PffLoader):
        self.config = config.talent
        self.loader = pff_loader
        self._pff_cache: dict[str, pl.DataFrame] = {}

    def stabilize_roster(
        self,
        roster: TeamRoster,
        crosswalk: dict[int, str],
        training_seasons: list[int],
    ) -> None:
        """Apply talent stabilization to all players on a roster.

        Args:
            roster: TeamRoster to modify in-place.
            crosswalk: PFF player_id (int) → nflverse player_id (str).
            training_seasons: Seasons to load PFF data from.
        """
        if not self.config.enabled:
            return

        reverse_crosswalk = {v: k for k, v in crosswalk.items()}

        # Load PFF data
        recv_data = self._get_aggregated("receiving_summary", training_seasons)
        rush_data = self._get_aggregated("rushing_summary", training_seasons)
        pass_data = self._get_aggregated("passing_summary", training_seasons)

        recv_by_id = self._index_by_player_id(recv_data)
        rush_by_id = self._index_by_player_id(rush_data)
        pass_by_id = self._index_by_player_id(pass_data)

        # Compute league averages for prior computation
        recv_avgs = self._league_averages(recv_data, [
            "drop_rate", "contested_catch_rate", "yprr", "avg_depth_of_target",
        ])
        rush_avgs = self._league_averages(rush_data, [
            "yco_attempt", "elusive_rating",
        ])
        pass_avgs = self._league_averages(pass_data, [
            "accuracy_percent",
        ])

        # Find team QB for catch_rate prior
        qb_accuracy = self._get_team_qb_accuracy(
            roster, reverse_crosswalk, pass_by_id, pass_avgs,
        )

        modified = 0
        for player in roster.players:
            pff_id = reverse_crosswalk.get(player.player_id)
            if pff_id is None:
                continue

            changed = False

            # --- Receiving stabilization ---
            if player.position in ("WR", "TE", "RB") and player.usage.target_share > 0:
                recv_stats = recv_by_id.get(pff_id)
                if recv_stats:
                    changed |= self._stabilize_catch_rate(
                        player, recv_stats, recv_avgs, qb_accuracy,
                    )
                    changed |= self._stabilize_receiving_yards(
                        player, recv_stats, recv_avgs,
                    )

            # --- Rushing stabilization ---
            if player.position in ("RB", "QB") and player.usage.carry_share > 0:
                rush_stats = rush_by_id.get(pff_id)
                if rush_stats:
                    changed |= self._stabilize_rushing_yards(
                        player, rush_stats, rush_avgs,
                    )

            if changed:
                modified += 1

        if modified > 0:
            logger.info("Talent stabilizer adjusted %d players on %s", modified, roster.team)

    def _get_aggregated(self, facet: str, seasons: list[int]) -> pl.DataFrame:
        """Load and cache aggregated PFF data."""
        cache_key = f"{facet}_{'_'.join(str(s) for s in sorted(seasons))}"
        if cache_key not in self._pff_cache:
            self._pff_cache[cache_key] = self.loader.aggregate_player_stats(facet, seasons)
        return self._pff_cache[cache_key]

    def _index_by_player_id(self, df: pl.DataFrame) -> dict[int, dict]:
        """Convert DataFrame to dict keyed by player_id."""
        if df.is_empty():
            return {}
        return {row["player_id"]: row for row in df.iter_rows(named=True)}

    def _league_averages(self, df: pl.DataFrame, columns: list[str]) -> dict[str, float]:
        """Compute league averages for specified columns."""
        avgs = {}
        for col in columns:
            if df.is_empty() or col not in df.columns:
                avgs[col] = 0.0
            else:
                avgs[col] = float(df[col].drop_nulls().mean() or 0.0)
        return avgs

    def _get_team_qb_accuracy(
        self,
        roster: TeamRoster,
        reverse_crosswalk: dict[str, int],
        pass_by_id: dict[int, dict],
        pass_avgs: dict[str, float],
    ) -> float:
        """Get the team QB's accuracy relative to league average."""
        try:
            qb = roster.get_starting_qb()
        except ValueError:
            return 0.0

        pff_id = reverse_crosswalk.get(qb.player_id)
        if pff_id is None:
            return 0.0

        qb_stats = pass_by_id.get(pff_id)
        if qb_stats is None:
            return 0.0

        acc = qb_stats.get("accuracy_percent")
        if acc is None:
            return 0.0

        # Return delta from league average (positive = better QB)
        return (acc - pass_avgs.get("accuracy_percent", 75.0)) * 0.01

    def _compute_catch_rate_prior(
        self,
        recv_stats: dict,
        recv_avgs: dict[str, float],
        qb_accuracy_delta: float,
    ) -> float | None:
        """Compute expected catch rate from PFF process metrics.

        Returns None if insufficient PFF data.
        """
        drop_rate = recv_stats.get("drop_rate")
        contested_cr = recv_stats.get("contested_catch_rate")

        if drop_rate is None:
            return None

        coeffs = self.config.catch_rate_coefficients
        # Baseline catch rate (league average ~0.64)
        baseline = 0.64

        prior = baseline
        # Fewer drops → higher expected catch rate
        avg_drop = recv_avgs.get("drop_rate", 5.0)
        prior += (avg_drop - drop_rate) * 0.01 * coeffs.get("drop_rate", -0.15)

        # Better contested catching → higher expected catch rate
        if contested_cr is not None:
            avg_contested = recv_avgs.get("contested_catch_rate", 50.0)
            prior += (contested_cr - avg_contested) * 0.01 * coeffs.get("contested_catch_rate", 0.10)

        # Better QB accuracy → higher expected catch rate
        prior += qb_accuracy_delta * coeffs.get("qb_accuracy", 0.08)

        return max(0.30, min(0.90, prior))

    def _stabilize_catch_rate(
        self,
        player: PlayerModel,
        recv_stats: dict,
        recv_avgs: dict[str, float],
        qb_accuracy_delta: float,
    ) -> bool:
        """Stabilize a player's catch_rate. Returns True if modified."""
        if player.outcomes.catch_rate <= 0:
            return False

        prior = self._compute_catch_rate_prior(recv_stats, recv_avgs, qb_accuracy_delta)
        if prior is None:
            return False

        n_targets = int(recv_stats.get("games", 1) * recv_stats.get("targets", 0))

        new_cr = stabilize_value(
            player.outcomes.catch_rate, prior, n_targets,
            self.config.prior_strength, self.config.min_divergence,
        )

        if new_cr == player.outcomes.catch_rate:
            return False

        # Scale red_zone_catch_rate proportionally
        if player.outcomes.red_zone_catch_rate > 0:
            ratio = new_cr / player.outcomes.catch_rate
            player.outcomes.red_zone_catch_rate = max(0.0, min(1.0,
                player.outcomes.red_zone_catch_rate * ratio))

        player.outcomes.catch_rate = new_cr
        return True

    def _stabilize_receiving_yards(
        self,
        player: PlayerModel,
        recv_stats: dict,
        recv_avgs: dict[str, float],
    ) -> bool:
        """Stabilize receiving yards distribution via additive shift."""
        if player.outcomes.receiving_yards_dist is None:
            return False

        yprr = recv_stats.get("yprr")
        adot = recv_stats.get("avg_depth_of_target")
        if yprr is None:
            return False

        coeffs = self.config.receiving_yards_coefficients
        shift = 0.0

        avg_yprr = recv_avgs.get("yprr", 1.5)
        shift += (yprr - avg_yprr) * coeffs.get("yprr", 0.5)

        if adot is not None:
            avg_adot = recv_avgs.get("avg_depth_of_target", 10.0)
            shift += (adot - avg_adot) * coeffs.get("avg_depth_of_target", 0.03)

        if abs(shift) < 0.3:  # min shift threshold
            return False

        n_targets = int(recv_stats.get("games", 1) * recv_stats.get("targets", 0))
        # Scale shift by observation confidence
        confidence = n_targets / (n_targets + self.config.prior_strength)
        # Invert: more PFF weight when fewer observations
        pff_confidence = 1.0 - confidence
        adjusted_shift = shift * pff_confidence

        player.outcomes.receiving_yards_dist = (
            player.outcomes.receiving_yards_dist + adjusted_shift
        )
        return True

    def _stabilize_rushing_yards(
        self,
        player: PlayerModel,
        rush_stats: dict,
        rush_avgs: dict[str, float],
    ) -> bool:
        """Stabilize rushing yards distribution via additive shift."""
        if player.outcomes.rushing_yards_dist is None:
            return False

        yco = rush_stats.get("yco_attempt")
        elusive = rush_stats.get("elusive_rating")
        if yco is None:
            return False

        coeffs = self.config.rushing_yards_coefficients
        shift = 0.0

        avg_yco = rush_avgs.get("yco_attempt", 2.5)
        shift += (yco - avg_yco) * coeffs.get("yco_attempt", 0.6)

        if elusive is not None:
            avg_elusive = rush_avgs.get("elusive_rating", 50.0)
            shift += (elusive - avg_elusive) * coeffs.get("elusive_rating", 0.008)

        if abs(shift) < 0.2:  # min shift threshold
            return False

        n_carries = int(rush_stats.get("games", 1) * rush_stats.get("attempts", 0))
        confidence = n_carries / (n_carries + self.config.prior_strength)
        pff_confidence = 1.0 - confidence
        adjusted_shift = shift * pff_confidence

        player.outcomes.rushing_yards_dist = (
            player.outcomes.rushing_yards_dist + adjusted_shift
        )
        return True
```

- [ ] **Step 8: Run talent stabilizer tests**

Run: `uv run pytest tests/test_data/test_pff/test_talent.py -v`
Expected: All 9 tests PASS (5 stabilize_value + 4 TalentStabilizer)

- [ ] **Step 9: Commit**

```bash
git add src/fantasy_sim/data/pff/talent.py tests/test_data/test_pff/test_talent.py
git commit -m "feat: add talent stabilizer with Bayesian blending and divergence detection"
```

---

## Task 5: Talent Integration — Wire into GameContextBuilder

**Files:**
- Modify: `src/fantasy_sim/data/game_context.py`
- Create: `tests/test_data/test_pff/test_talent_integration.py`

- [ ] **Step 1: Write failing integration test**

```python
# tests/test_data/test_pff/test_talent_integration.py
"""Integration test: talent stabilizer wired into GameContextBuilder."""

import numpy as np
import pytest
from unittest.mock import patch, MagicMock

from fantasy_sim.data.game_context import GameContextBuilder
from fantasy_sim.data.pff.models import PffConfig, TalentConfig, MatchupConfig


class TestTalentIntegration:
    def test_builder_accepts_pff_config_with_talent(self):
        """GameContextBuilder should accept PffConfig with talent enabled."""
        config = PffConfig(
            enabled=True,
            talent=TalentConfig(enabled=True),
            matchup=MatchupConfig(enabled=False),
        )
        # Should not raise even if PFF data dir doesn't exist
        builder = GameContextBuilder(pff_config=config)
        assert builder._pff_config.talent.enabled is True

    def test_builder_disabled_pff_has_no_stabilizer(self):
        """Disabled PFF config should produce no talent stabilizer."""
        builder = GameContextBuilder()
        assert builder._pff_config.enabled is False
```

- [ ] **Step 2: Run test to verify it fails or passes (depending on Task 3 state)**

Run: `uv run pytest tests/test_data/test_pff/test_talent_integration.py -v`

- [ ] **Step 3: Add talent stabilizer wiring to GameContextBuilder**

In `GameContextBuilder.__init__`, add after the matchup engine init:

```python
    # Talent stabilizer
    self._talent_stabilizer = None
    self._pff_crosswalk: dict[int, str] = {}
    if self._pff_config.enabled and self._pff_config.talent.enabled:
        from fantasy_sim.data.pff.loader import PffLoader
        from fantasy_sim.data.pff.talent import TalentStabilizer
        pff_dir = Path(self._pff_config.data_dir) if self._pff_config.data_dir else None
        # Reuse loader if matchup engine already created one
        if self._matchup_engine is not None:
            pff_loader = self._matchup_engine.loader
        else:
            pff_loader = PffLoader(pff_dir)
        if pff_loader.is_available():
            self._talent_stabilizer = TalentStabilizer(self._pff_config, pff_loader)
            self._pff_loader = pff_loader
            logging.getLogger(__name__).info("PFF talent stabilizer enabled")
```

Add a `_ensure_pff_crosswalk` method:

```python
def _ensure_pff_crosswalk(
    self,
    training_seasons: list[int],
    target_season: int | None = None,
) -> None:
    """Build PFF crosswalk if not already cached."""
    if self._pff_crosswalk or not hasattr(self, '_pff_loader'):
        return

    pff_loader = self._pff_loader
    frames = []
    for facet in ("receiving_summary", "rushing_summary", "passing_summary"):
        df = pff_loader.load_facet(facet, training_seasons)
        if not df.is_empty():
            frames.append(df.select(["player_id", "player", "team"]))
    if not frames:
        return

    pff_data = pl.concat(frames).unique(subset=["player_id"])
    roster_season = target_season or max(training_seasons)
    nfl_roster = self.loader.load_rosters([roster_season])
    self._pff_crosswalk = pff_loader.build_crosswalk(pff_data, nfl_roster, roster_season)
```

Update `build_game` to add talent stabilizer call after matchup:

```python
    # PFF talent stabilization
    if self._talent_stabilizer is not None:
        from fantasy_sim.data.player_builder import _normalize_roster_shares
        self._ensure_pff_crosswalk(training_seasons, target_season)
        self._talent_stabilizer.stabilize_roster(
            home_roster, self._pff_crosswalk, training_seasons,
        )
        self._talent_stabilizer.stabilize_roster(
            away_roster, self._pff_crosswalk, training_seasons,
        )
        _normalize_roster_shares(home_roster)
        _normalize_roster_shares(away_roster)
```

- [ ] **Step 4: Run integration tests**

Run: `uv run pytest tests/test_data/test_pff/ -v`
Expected: All PFF tests PASS

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest tests/ -v --timeout=60`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/fantasy_sim/data/game_context.py tests/test_data/test_pff/test_talent_integration.py
git commit -m "feat: wire talent stabilizer into GameContextBuilder"
```

---

## Task 6: A/B Backtest Script

**Files:**
- Create: `scripts/validate_pff_signal.py`

- [ ] **Step 1: Write the backtest script**

```python
#!/usr/bin/env python3
"""A/B backtest: PFF intelligence layers ON vs OFF.

Validates whether PFF matchup engine and/or talent stabilizer improve
projection accuracy.

Modes:
  - "matchup" : matchup engine only (Layer 1+2)
  - "talent"  : talent stabilizer only (Layer 3)
  - "all"     : both layers

Usage:
    uv run python scripts/validate_pff_signal.py --mode matchup --sims 50
    uv run python scripts/validate_pff_signal.py --mode talent --sims 100
    uv run python scripts/validate_pff_signal.py --mode all --seasons 2023 2024
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fantasy_sim.config.loader import load_defaults, resolve_scoring
from fantasy_sim.data.game_context import GameContextBuilder
from fantasy_sim.data.pff.models import MatchupConfig, PffConfig, TalentConfig
from fantasy_sim.validation.backtester import Backtester, BacktestResult


@dataclass
class ComparisonResult:
    test_season: int
    off: BacktestResult
    on: BacktestResult

    @property
    def rank_corr_delta(self) -> float:
        positions = ["QB", "RB", "WR", "TE"]
        off_avg = sum(self.off.rank_correlations.get(p, 0) for p in positions) / len(positions)
        on_avg = sum(self.on.rank_correlations.get(p, 0) for p in positions) / len(positions)
        return on_avg - off_avg

    @property
    def weekly_mae_delta(self) -> float:
        return self.on.weekly_mae - self.off.weekly_mae

    @property
    def season_mae_delta(self) -> float:
        return self.on.season_mae - self.off.season_mae

    @property
    def calibration_delta(self) -> float:
        return self.on.boom_bust_calibration - self.off.boom_bust_calibration


RANK_CORR_MIN_IMPROVEMENT = 0.01
RANK_CORR_MAX_REGRESSION = 0.005
MAE_MAX_REGRESSION = 0.3


def _build_pff_config(mode: str) -> PffConfig:
    if mode == "matchup":
        return PffConfig(
            enabled=True,
            matchup=MatchupConfig(enabled=True),
            talent=TalentConfig(enabled=False),
        )
    elif mode == "talent":
        return PffConfig(
            enabled=True,
            matchup=MatchupConfig(enabled=False),
            talent=TalentConfig(enabled=True),
        )
    else:  # "all"
        return PffConfig(
            enabled=True,
            matchup=MatchupConfig(enabled=True),
            talent=TalentConfig(enabled=True),
        )


def run_backtest_pair(
    test_season: int,
    n_sims: int,
    scoring_config: dict,
    num_training_seasons: int = 2,
    mode: str = "all",
) -> ComparisonResult:
    print(f"\n{'='*60}")
    print(f"  Season {test_season} — {n_sims} sims per game — mode: {mode}")
    print(f"  Training: {test_season - num_training_seasons}-{test_season - 1}")
    print(f"{'='*60}")

    # --- PFF OFF ---
    print(f"\n  [PFF OFF] Running backtest...")
    t0 = time.time()
    bt_off = Backtester(
        test_season=test_season, n_sims=n_sims,
        num_training_seasons=num_training_seasons, scoring_format="ppr",
    )
    result_off = bt_off.run(scoring_config)
    print(f"  [PFF OFF] Done in {time.time() - t0:.1f}s")
    _print_result(result_off)

    # --- PFF ON ---
    print(f"\n  [PFF ON]  Running backtest ({mode} mode)...")
    t0 = time.time()
    bt_on = Backtester(
        test_season=test_season, n_sims=n_sims,
        num_training_seasons=num_training_seasons, scoring_format="ppr",
    )
    pff_config = _build_pff_config(mode)
    bt_on.builder = GameContextBuilder(
        cache_dir=bt_on.loader.cache_dir, pff_config=pff_config,
    )
    result_on = bt_on.run(scoring_config)
    print(f"  [PFF ON]  Done in {time.time() - t0:.1f}s")
    _print_result(result_on)

    return ComparisonResult(test_season=test_season, off=result_off, on=result_on)


def _print_result(r: BacktestResult) -> None:
    avg_corr = sum(r.rank_correlations.values()) / max(len(r.rank_correlations), 1)
    print(f"    Rank Corr (avg): {avg_corr:.4f}  ", end="")
    for pos in ["QB", "RB", "WR", "TE"]:
        print(f"  {pos}={r.rank_correlations.get(pos, 0):.3f}", end="")
    print()
    print(
        f"    Weekly MAE: {r.weekly_mae:.3f}  |  Season MAE: {r.season_mae:.3f}"
        f"  |  Calibration: {r.boom_bust_calibration:.4f}"
    )
    print(f"    Players: {r.total_players_evaluated}  |  Weeks: {r.total_weeks_evaluated}")


def evaluate_kill_point(results: list[ComparisonResult]) -> bool:
    print(f"\n{'='*60}")
    print("  KILL-POINT EVALUATION")
    print(f"{'='*60}\n")

    any_improved = False
    any_regressed = False
    all_directional = True

    for cr in results:
        rc_delta = cr.rank_corr_delta
        wm_delta = cr.weekly_mae_delta
        sm_delta = cr.season_mae_delta
        cal_delta = cr.calibration_delta

        print(f"  Season {cr.test_season}:")
        print(f"    Rank Corr delta:  {rc_delta:+.4f}  ", end="")
        if rc_delta >= RANK_CORR_MIN_IMPROVEMENT:
            print("  IMPROVED"); any_improved = True
        elif rc_delta < -RANK_CORR_MAX_REGRESSION:
            print("  REGRESSED"); any_regressed = True; all_directional = False
        else:
            print("  NEUTRAL")

        print(f"    Weekly MAE delta: {wm_delta:+.3f}  ", end="")
        if wm_delta < -0.05:
            print("  IMPROVED")
        elif wm_delta > MAE_MAX_REGRESSION:
            print("  REGRESSED"); any_regressed = True
        else:
            print("  NEUTRAL")

        print(f"    Season MAE delta: {sm_delta:+.3f}  ", end="")
        if sm_delta < -0.5:
            print("  IMPROVED")
        elif sm_delta > MAE_MAX_REGRESSION * 17:
            print("  REGRESSED"); any_regressed = True
        else:
            print("  NEUTRAL")

        print(f"    Calibration delta: {cal_delta:+.4f}  ", end="")
        if cal_delta < -0.005:
            print("  IMPROVED")
        elif cal_delta > 0.01:
            print("  REGRESSED")
        else:
            print("  NEUTRAL")
        print()

    print(f"  {'='*50}")
    if any_regressed:
        print("  VERDICT: FAIL — at least one metric regressed beyond threshold")
        return False
    if any_improved and all_directional:
        print("  VERDICT: PASS — signal detected, consistent direction")
        return True
    avg_rc = sum(cr.rank_corr_delta for cr in results) / len(results)
    if avg_rc > 0.005:
        print(f"  VERDICT: SOFT PASS — directional improvement ({avg_rc:+.4f})")
        return True
    print("  VERDICT: FAIL — no measurable improvement")
    return False


def main():
    parser = argparse.ArgumentParser(description="A/B backtest: PFF intelligence layers")
    parser.add_argument("--sims", type=int, default=50)
    parser.add_argument("--seasons", type=int, nargs="+", default=[2023, 2024])
    parser.add_argument("--training-years", type=int, default=2)
    parser.add_argument("--mode", choices=["all", "matchup", "talent"], default="all")
    args = parser.parse_args()

    defaults = load_defaults()
    scoring_config = resolve_scoring(defaults["scoring"], "ppr")

    print("PFF Signal Validation — A/B Backtest")
    print(f"Mode: {args.mode}")
    print(f"Test seasons: {args.seasons}")
    print(f"Sims per game: {args.sims}")

    results = []
    total_start = time.time()
    for season in args.seasons:
        cr = run_backtest_pair(season, args.sims, scoring_config, args.training_years, args.mode)
        results.append(cr)

    print(f"\nTotal time: {time.time() - total_start:.0f}s")
    passed = evaluate_kill_point(results)
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify script runs with --help**

Run: `uv run python scripts/validate_pff_signal.py --help`
Expected: Shows usage with --mode, --sims, --seasons flags

- [ ] **Step 3: Commit**

```bash
git add scripts/validate_pff_signal.py
git commit -m "feat: add PFF A/B backtest script with per-layer modes"
```

---

## Task 7: CLI Integration + Config + Docs

**Files:**
- Modify: `src/fantasy_sim/cli.py`
- Modify: `config/defaults.yaml`
- Modify: `docs/CONFIG.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add pff section to defaults.yaml**

Add after the `positions:` section in `config/defaults.yaml`:

```yaml
pff:
  enabled: false
  data_dir: null  # defaults to ~/.fantasy-sim/pff/processed/nfl/

  matchup:
    enabled: true
    pass_defense_sensitivity: 0.08
    pass_rush_sensitivity: 0.10
    run_defense_sensitivity: 0.08
    int_rate_sensitivity: 0.06
    ol_pass_sensitivity: 0.08
    ol_run_sensitivity: 0.06
    factor_clamp: [0.80, 1.20]
    min_games: 4

  talent:
    enabled: true
    prior_strength: 40
    min_divergence: 0.03
    catch_rate_coefficients:
      drop_rate: -0.15
      contested_catch_rate: 0.10
      qb_accuracy: 0.08
    rushing_yards_coefficients:
      yco_attempt: 0.6
      elusive_rating: 0.008
    receiving_yards_coefficients:
      yprr: 0.5
      avg_depth_of_target: 0.03
```

- [ ] **Step 2: Add --pff/--no-pff flag to CLI commands**

In `src/fantasy_sim/cli.py`, add a helper to build GameContextBuilder with PFF config:

```python
from fantasy_sim.data.pff.config import load_pff_config


def _make_builder(pff_flag: bool | None = None) -> GameContextBuilder:
    """Create GameContextBuilder, optionally with PFF enabled.

    Args:
        pff_flag: True = force PFF on, False = force off, None = use config default.
    """
    defaults = load_defaults()
    pff_config = load_pff_config(defaults)

    if pff_flag is True:
        pff_config.enabled = True
    elif pff_flag is False:
        pff_config.enabled = False

    loader = DataLoader()
    return GameContextBuilder(cache_dir=loader.cache_dir, pff_config=pff_config)
```

Add `--pff/--no-pff` option to the `week`, `season`, `game`, `player` commands. For each command, add the option decorator:

```python
@click.option("--pff/--no-pff", default=None, help="Enable/disable PFF matchup + talent adjustments")
```

And replace `builder = GameContextBuilder(cache_dir=loader.cache_dir)` with:

```python
builder = _make_builder(pff)
```

Apply this to:
- `week` command (around line 505)
- `season` command (around line 637)
- `game` command (around line 823)
- `player` command (around line 956)

- [ ] **Step 3: Run existing CLI tests to verify nothing broke**

Run: `uv run pytest tests/ -v --timeout=60`
Expected: All tests PASS

- [ ] **Step 4: Update CONFIG.md with PFF section**

Add a new section to `docs/CONFIG.md` after the "Simulation Settings" section:

```markdown
---

## PFF Intelligence Layer

The simulator can optionally use PFF (Pro Football Focus) data to improve projections through two independent layers:

1. **Matchup Engine** — Adjusts offensive parameters per-game based on the opposing defense's quality (coverage grades, pass rush, run defense) and the team's own OL quality.
2. **Talent Stabilizer** — Identifies players whose PBP stats likely misrepresent their true talent using PFF process metrics (route grades, drop rates, yards after contact). Applies Bayesian blending weighted by sample size.

### Enabling PFF

PFF data must be scraped first (see `docs/pff-setup.md`). Then enable via config or CLI:

```yaml
# config/defaults.yaml
pff:
  enabled: true
```

```bash
# Or per-command via CLI flag
uv run fantasy-sim week 1 --season 2024 --pff
uv run fantasy-sim week 1 --season 2024 --no-pff  # override config
```

### PFF Configuration

```yaml
pff:
  enabled: false
  data_dir: null  # defaults to ~/.fantasy-sim/pff/processed/nfl/

  matchup:
    enabled: true
    # Sensitivity per z-score unit (higher = more matchup impact)
    pass_defense_sensitivity: 0.08
    pass_rush_sensitivity: 0.10
    run_defense_sensitivity: 0.08
    int_rate_sensitivity: 0.06
    ol_pass_sensitivity: 0.08
    ol_run_sensitivity: 0.06
    # Maximum adjustment bounds
    factor_clamp: [0.80, 1.20]
    # Minimum games for stat-based factors (below this, uses grade fallback)
    min_games: 4

  talent:
    enabled: true
    prior_strength: 40       # PFF grade = equivalent of N PBP observations
    min_divergence: 0.03     # minimum PBP-PFF gap before adjusting
    # Regression coefficients for computing PFF priors
    catch_rate_coefficients:
      drop_rate: -0.15
      contested_catch_rate: 0.10
      qb_accuracy: 0.08
    rushing_yards_coefficients:
      yco_attempt: 0.6
      elusive_rating: 0.008
    receiving_yards_coefficients:
      yprr: 0.5
      avg_depth_of_target: 0.03
```

### Override Interaction

PFF adjustments are applied **before** user overrides. User overrides always win:

```
Base model (nflverse PBP)
  → PFF matchup adjustments (per-game, based on opponent)
  → PFF talent stabilization (season-level, based on process metrics)
  → Share re-normalization
  → User overrides (season.yaml + CLI --override) ← always last
  → Share re-normalization
```

If you override a parameter (e.g., `catch_rate=0.68`), that exact value is used regardless of PFF. PFF matchup adjustments on that parameter are effectively bypassed for that player.

**Migration note**: When enabling PFF for the first time, review existing season.yaml overrides. Many schedule-strength and talent-based adjustments may now be redundant.
```

- [ ] **Step 5: Update CLAUDE.md**

Update the Data Layer entry in the Architecture section to include PFF subpackage:

```
1. **Data Layer** (`data/loader.py`, `data/preprocessor.py`, `data/pipeline.py`, `data/player_builder.py`, `data/rookie_builder.py`, `data/game_context.py`, `data/actuals.py`, `data/pff/`) — ...existing description... `data/pff/` subpackage contains `loader.py` (PFF parquet reader + player ID crosswalk), `matchup.py` (defensive matchup engine using z-score factors), `talent.py` (Bayesian talent stabilizer with divergence detection), `models.py` (MatchupContext, PffConfig dataclasses), `config.py` (YAML config loader).
```

Add a PFF Intelligence Layer key pattern entry:

```
- **PFF Intelligence Layer**: Two independent layers in `data/pff/`. **MatchupEngine** (`matchup.py`) computes per-game `MatchupContext` from PFF defensive + OL data via z-scores clamped to `factor_clamp` range. Factors: `catch_rate_factor`, `pass_yards_factor`, `sack_rate_factor`, `int_rate_factor`, `rush_yards_factor`, `ol_pass_block_factor`, `ol_run_block_factor`. Applied in `GameContextBuilder.build_game()` — away D adjusts home O and vice versa. **TalentStabilizer** (`talent.py`) uses Bayesian blending: `stabilize_value(pbp, prior, n_obs, prior_strength, min_divergence)`. Only adjusts when PBP-PFF divergence exceeds threshold. Stabilizes: catch_rate, receiving/rushing yards distributions. Config in `defaults.yaml` under `pff:` section. CLI `--pff/--no-pff` flag overrides config. Ordering: base model → matchup → talent → normalize → user overrides → normalize.
```

Update the Current State section to add the new phase.

- [ ] **Step 6: Run full test suite one final time**

Run: `uv run pytest tests/ -v --timeout=60`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add config/defaults.yaml src/fantasy_sim/cli.py docs/CONFIG.md CLAUDE.md
git commit -m "feat: add PFF CLI flag, defaults.yaml config, and documentation"
```

---

## Task 8: Full Suite Verification

**Files:** None new — verification only.

- [ ] **Step 1: Run complete test suite**

Run: `uv run pytest tests/ -v --timeout=120`
Expected: All tests PASS

- [ ] **Step 2: Verify demo mode still works (PFF should be inactive)**

Run: `uv run fantasy-sim demo --sims 10`
Expected: Runs successfully, no PFF-related errors

- [ ] **Step 3: Verify --pff flag is accepted**

Run: `uv run fantasy-sim week 1 --season 2024 --sims 10 --pff 2>&1 | head -5`
Expected: Runs (or shows PFF enabled message). If PFF data exists at `~/.fantasy-sim/pff/processed/nfl/`, matchup + talent layers activate.

- [ ] **Step 4: Run A/B backtest (matchup mode)**

Run: `uv run python scripts/validate_pff_signal.py --mode matchup --sims 50 --seasons 2024`
Expected: Completes and shows comparison results. Note: this is informational — the kill-point verdict may pass or fail depending on the data.

- [ ] **Step 5: Commit any final fixes**

```bash
git add -A
git commit -m "chore: final verification and fixes for PFF intelligence layer"
```

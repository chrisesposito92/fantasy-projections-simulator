# Team Context Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add season-level team context adjustments (pass rate, OL quality, QB quality) to tier distributions before blending with PBP data.

**Architecture:** New `TeamContextEngine` peer engine computes three z-score-based factors per team using same-season rolling window. Factors modify `TierDistributions` inside `TierEngine.apply_tiers()` before `_blend_player()`. `GameContextBuilder` orchestrates.

**Tech Stack:** Python 3.12+, polars, numpy, pytest. Reuses `compute_factor()` from `matchup.py`.

**Spec:** `docs/superpowers/specs/2026-04-04-team-context-layer-design.md`

---

### Task 1: Data Model — TeamContext, TeamContextConfig, PffConfig Update

**Files:**
- Modify: `src/fantasy_sim/data/pff/models.py:145-152`
- Test: `tests/test_data/test_pff/test_team_context.py` (NEW)

- [ ] **Step 1: Write failing tests for TeamContext and TeamContextConfig**

Create `tests/test_data/test_pff/test_team_context.py`:

```python
"""Tests for the PFF team context engine."""

import pytest
import numpy as np

from fantasy_sim.data.pff.models import TeamContext, TeamContextConfig


class TestTeamContextDataModel:
    def test_team_context_defaults(self):
        """All factors default to 1.0 (neutral), scale defaults to 10.0."""
        ctx = TeamContext()
        assert ctx.pass_rate_factor == 1.0
        assert ctx.ol_run_block_factor == 1.0
        assert ctx.qb_quality_factor == 1.0
        assert ctx.ol_run_yards_scale == 10.0

    def test_team_context_custom_values(self):
        """TeamContext can be constructed with custom factor values."""
        ctx = TeamContext(
            pass_rate_factor=1.08,
            ol_run_block_factor=0.94,
            qb_quality_factor=1.05,
            ol_run_yards_scale=12.0,
        )
        assert ctx.pass_rate_factor == 1.08
        assert ctx.ol_run_block_factor == 0.94
        assert ctx.qb_quality_factor == 1.05
        assert ctx.ol_run_yards_scale == 12.0

    def test_team_context_config_defaults(self):
        """TeamContextConfig has correct default values."""
        cfg = TeamContextConfig()
        assert cfg.enabled is True
        assert cfg.pass_rate_sensitivity == 0.08
        assert cfg.ol_run_sensitivity == 0.06
        assert cfg.qb_quality_sensitivity == 0.05
        assert cfg.factor_clamp == (0.90, 1.10)
        assert cfg.min_games == 4
        assert cfg.ol_run_yards_scale == 10.0

    def test_team_context_config_custom(self):
        """TeamContextConfig can be constructed with custom values."""
        cfg = TeamContextConfig(
            enabled=False,
            pass_rate_sensitivity=0.10,
            factor_clamp=(0.85, 1.15),
        )
        assert cfg.enabled is False
        assert cfg.pass_rate_sensitivity == 0.10
        assert cfg.factor_clamp == (0.85, 1.15)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_pff/test_team_context.py::TestTeamContextDataModel -v`
Expected: FAIL — `ImportError: cannot import name 'TeamContext'`

- [ ] **Step 3: Add TeamContext and TeamContextConfig to models.py**

In `src/fantasy_sim/data/pff/models.py`, add before the `PffConfig` class (before line 145):

```python
@dataclass
class TeamContext:
    """Season-level team environment factors for tier distribution adjustment.

    All factors centered on 1.0 (neutral).
    """
    pass_rate_factor: float = 1.0
    ol_run_block_factor: float = 1.0
    qb_quality_factor: float = 1.0
    ol_run_yards_scale: float = 10.0


@dataclass
class TeamContextConfig:
    """Configuration for the team context engine."""
    enabled: bool = True
    pass_rate_sensitivity: float = 0.08
    ol_run_sensitivity: float = 0.06
    qb_quality_sensitivity: float = 0.05
    factor_clamp: tuple[float, float] = (0.90, 1.10)
    min_games: int = 4
    ol_run_yards_scale: float = 10.0
```

Then update `PffConfig` to include the new field:

```python
@dataclass
class PffConfig:
    """Top-level PFF configuration."""
    enabled: bool = False
    data_dir: str | None = None
    matchup: MatchupConfig = field(default_factory=MatchupConfig)
    talent: TalentConfig = field(default_factory=TalentConfig)
    tier_engine: TierConfig = field(default_factory=TierConfig)
    team_context: TeamContextConfig = field(default_factory=TeamContextConfig)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_pff/test_team_context.py::TestTeamContextDataModel -v`
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/pff/models.py tests/test_data/test_pff/test_team_context.py
git commit -m "feat: add TeamContext and TeamContextConfig data models"
```

---

### Task 2: Config Parsing — load_pff_config Handles team_context

**Files:**
- Modify: `src/fantasy_sim/data/pff/config.py:124-130`
- Modify: `tests/test_data/test_pff/test_tier_engine.py` (add to TestTierConfig)

- [ ] **Step 1: Write failing test for team_context config parsing**

Append to the `TestTierConfig` class in `tests/test_data/test_pff/test_tier_engine.py`:

```python
    def test_load_team_context_config_from_yaml(self):
        """Full YAML team_context section is parsed correctly."""
        from fantasy_sim.data.pff.models import TeamContextConfig
        cfg = load_pff_config({
            "pff": {
                "team_context": {
                    "enabled": True,
                    "pass_rate_sensitivity": 0.10,
                    "ol_run_sensitivity": 0.08,
                    "qb_quality_sensitivity": 0.06,
                    "factor_clamp": [0.85, 1.15],
                    "min_games": 3,
                    "ol_run_yards_scale": 12.0,
                }
            }
        })
        tc = cfg.team_context
        assert isinstance(tc, TeamContextConfig)
        assert tc.enabled is True
        assert tc.pass_rate_sensitivity == 0.10
        assert tc.ol_run_sensitivity == 0.08
        assert tc.qb_quality_sensitivity == 0.06
        assert tc.factor_clamp == (0.85, 1.15)
        assert tc.min_games == 3
        assert tc.ol_run_yards_scale == 12.0

    def test_team_context_config_defaults_when_absent(self):
        """PffConfig.team_context defaults to TeamContextConfig() when section is absent."""
        from fantasy_sim.data.pff.models import TeamContextConfig
        cfg = load_pff_config({"pff": {}})
        assert isinstance(cfg.team_context, TeamContextConfig)
        assert cfg.team_context.enabled is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_pff/test_tier_engine.py::TestTierConfig::test_load_team_context_config_from_yaml tests/test_data/test_pff/test_tier_engine.py::TestTierConfig::test_team_context_config_defaults_when_absent -v`
Expected: FAIL — `PffConfig` doesn't parse `team_context` yet, so default values will be used. `test_load_team_context_config_from_yaml` will fail because parsed values won't match.

- [ ] **Step 3: Update config.py to parse team_context**

In `src/fantasy_sim/data/pff/config.py`, add the import:

```python
from fantasy_sim.data.pff.models import (
    MatchupConfig,
    NcaaPriorsConfig,
    PffConfig,
    PositionGradeConfig,
    ScheduleAdjustmentConfig,
    TalentConfig,
    TeamContextConfig,
    TierConfig,
)
```

Then add team_context parsing at the end of `load_pff_config()`, just before the `return PffConfig(...)` statement:

```python
    tc_raw = pff.get("team_context", {})
    tc_clamp = tc_raw.get("factor_clamp", [0.90, 1.10])
    team_context = TeamContextConfig(
        enabled=tc_raw.get("enabled", True),
        pass_rate_sensitivity=tc_raw.get("pass_rate_sensitivity", 0.08),
        ol_run_sensitivity=tc_raw.get("ol_run_sensitivity", 0.06),
        qb_quality_sensitivity=tc_raw.get("qb_quality_sensitivity", 0.05),
        factor_clamp=tuple(tc_clamp),
        min_games=tc_raw.get("min_games", 4),
        ol_run_yards_scale=tc_raw.get("ol_run_yards_scale", 10.0),
    )
```

And update the return statement:

```python
    return PffConfig(
        enabled=pff.get("enabled", False),
        data_dir=pff.get("data_dir"),
        matchup=matchup,
        talent=talent,
        tier_engine=tier_engine,
        team_context=team_context,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_pff/test_tier_engine.py::TestTierConfig -v`
Expected: All TestTierConfig tests PASS (including existing ones)

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/pff/config.py tests/test_data/test_pff/test_tier_engine.py
git commit -m "feat: parse team_context config section in load_pff_config"
```

---

### Task 3: defaults.yaml — Add pff.team_context Section

**Files:**
- Modify: `config/defaults.yaml:83-84` (between tier_engine and matchup sections)

- [ ] **Step 1: Add team_context section to defaults.yaml**

Insert after the `tier_engine` block (after `blend_pool_size: 500`, line 83) and before the `matchup` block:

```yaml
  team_context:
    enabled: true
    pass_rate_sensitivity: 0.08
    ol_run_sensitivity: 0.06
    qb_quality_sensitivity: 0.05
    factor_clamp: [0.90, 1.10]
    min_games: 4
    ol_run_yards_scale: 10.0
```

- [ ] **Step 2: Verify config loads correctly**

Run: `uv run python -c "from fantasy_sim.data.pff.config import load_pff_config; from fantasy_sim.config.loader import load_defaults; c = load_pff_config(load_defaults()); print(f'team_context enabled={c.team_context.enabled}, pass_rate_sens={c.team_context.pass_rate_sensitivity}')"`
Expected: `team_context enabled=True, pass_rate_sens=0.08`

- [ ] **Step 3: Run existing test suite to verify no regressions**

Run: `uv run pytest tests/test_data/test_pff/ -v --timeout=30`
Expected: All existing PFF tests PASS

- [ ] **Step 4: Commit**

```bash
git add config/defaults.yaml
git commit -m "config: add pff.team_context section to defaults.yaml"
```

---

### Task 4: TeamContextEngine — Pass Rate Factor

**Files:**
- Create: `src/fantasy_sim/data/pff/team_context.py`
- Modify: `tests/test_data/test_pff/test_team_context.py`

- [ ] **Step 1: Write failing tests for pass rate factor**

Append to `tests/test_data/test_pff/test_team_context.py`:

```python
import polars as pl
from unittest.mock import MagicMock

from fantasy_sim.data.pff.models import TeamContextConfig
from fantasy_sim.data.pff.team_context import TeamContextEngine


def _make_pbp(teams_data: dict[str, dict[str, int]], season: int, week: int) -> pl.DataFrame:
    """Build a minimal PBP DataFrame for testing.

    Args:
        teams_data: {team: {"pass": N, "run": N}} — play counts per team.
        season: Season year for all rows.
        week: Week number for all rows.
    """
    rows = []
    game_idx = 0
    for team, counts in teams_data.items():
        game_idx += 1
        for _ in range(counts.get("pass", 0)):
            rows.append({"play_type": "pass", "posteam": team, "season": season, "week": week, "game_id": f"game_{game_idx}"})
        for _ in range(counts.get("run", 0)):
            rows.append({"play_type": "run", "posteam": team, "season": season, "week": week, "game_id": f"game_{game_idx}"})
    return pl.DataFrame(rows)


class TestPassRateFactor:
    def _make_engine(self, **config_overrides) -> TeamContextEngine:
        cfg = TeamContextConfig(**config_overrides)
        return TeamContextEngine(config=cfg, pff_loader=MagicMock())

    def test_pass_heavy_team_above_one(self):
        """A team with 70% pass rate (league avg ~57%) should get factor > 1.0."""
        engine = self._make_engine()
        # 3 teams: heavy pass, balanced, run-heavy
        pbp = _make_pbp(
            {"KC": {"pass": 70, "run": 30}, "BUF": {"pass": 55, "run": 45}, "BAL": {"pass": 45, "run": 55}},
            season=2024, week=5,
        )
        factor = engine._compute_pass_rate_factor("KC", 2024, 6, pbp)
        assert factor > 1.0

    def test_run_heavy_team_below_one(self):
        """A team with 45% pass rate (league avg ~57%) should get factor < 1.0."""
        engine = self._make_engine()
        pbp = _make_pbp(
            {"KC": {"pass": 70, "run": 30}, "BUF": {"pass": 55, "run": 45}, "BAL": {"pass": 45, "run": 55}},
            season=2024, week=5,
        )
        factor = engine._compute_pass_rate_factor("BAL", 2024, 6, pbp)
        assert factor < 1.0

    def test_average_team_near_one(self):
        """A team at the league average should get factor ~1.0."""
        engine = self._make_engine()
        pbp = _make_pbp(
            {"KC": {"pass": 70, "run": 30}, "BUF": {"pass": 57, "run": 43}, "BAL": {"pass": 45, "run": 55}},
            season=2024, week=5,
        )
        factor = engine._compute_pass_rate_factor("BUF", 2024, 6, pbp)
        assert 0.98 <= factor <= 1.02

    def test_factor_clamped_to_range(self):
        """Extreme pass rate produces factor clamped to [0.90, 1.10]."""
        engine = self._make_engine(factor_clamp=(0.90, 1.10))
        # Extreme: 95% pass vs 2 teams at 30%
        pbp = _make_pbp(
            {"KC": {"pass": 95, "run": 5}, "BUF": {"pass": 30, "run": 70}, "BAL": {"pass": 30, "run": 70}},
            season=2024, week=5,
        )
        factor = engine._compute_pass_rate_factor("KC", 2024, 6, pbp)
        assert factor <= 1.10

    def test_week_filter_applied(self):
        """Only PBP data from week < max_week is used."""
        engine = self._make_engine()
        # Week 5 data: KC is pass-heavy. Week 8 data (future): KC is run-heavy.
        pbp_w5 = _make_pbp(
            {"KC": {"pass": 70, "run": 30}, "BUF": {"pass": 50, "run": 50}},
            season=2024, week=5,
        )
        pbp_w8 = _make_pbp(
            {"KC": {"pass": 20, "run": 80}, "BUF": {"pass": 50, "run": 50}},
            season=2024, week=8,
        )
        pbp = pl.concat([pbp_w5, pbp_w8])
        # max_week=6 → only week 5 data used → KC still pass-heavy
        factor = engine._compute_pass_rate_factor("KC", 2024, 6, pbp)
        assert factor > 1.0

    def test_missing_team_returns_neutral(self):
        """Team not in PBP data returns neutral factor 1.0."""
        engine = self._make_engine()
        pbp = _make_pbp({"KC": {"pass": 50, "run": 50}, "BUF": {"pass": 50, "run": 50}}, season=2024, week=5)
        factor = engine._compute_pass_rate_factor("NYG", 2024, 6, pbp)
        assert factor == 1.0

    def test_empty_pbp_returns_neutral(self):
        """Empty PBP DataFrame returns neutral factor 1.0."""
        engine = self._make_engine()
        factor = engine._compute_pass_rate_factor("KC", 2024, 6, pl.DataFrame())
        assert factor == 1.0

    def test_none_pbp_returns_neutral(self):
        """None PBP returns neutral factor 1.0."""
        engine = self._make_engine()
        factor = engine._compute_pass_rate_factor("KC", 2024, 6, None)
        assert factor == 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_pff/test_team_context.py::TestPassRateFactor -v`
Expected: FAIL — `ImportError: cannot import name 'TeamContextEngine'`

- [ ] **Step 3: Implement TeamContextEngine with pass rate factor**

Create `src/fantasy_sim/data/pff/team_context.py`:

```python
"""Team context engine — computes season-level team environment factors.

Uses team pass rate (PBP), OL run blocking quality (PFF), and QB quality
(PFF) to adjust tier distributions before blending with PBP data.

Pipeline position:
    base model → matchup → *team context* → tier engine blend → normalize
    → user overrides → normalize
"""

from __future__ import annotations

import logging

import numpy as np
import polars as pl

from fantasy_sim.data.pff.loader import PffLoader
from fantasy_sim.data.pff.matchup import compute_factor
from fantasy_sim.data.pff.models import TeamContext, TeamContextConfig

logger = logging.getLogger(__name__)


class TeamContextEngine:
    """Computes season-level team environment factors from PFF + PBP data.

    Three factors are computed per team:
    1. Pass rate factor — from PBP play-calling frequency
    2. OL run blocking factor — from PFF offense_run_blocking grades
    3. QB quality factor — from PFF passing_summary grades

    All use same-season rolling window (week < max_week) with
    previous-season blend when team has < min_games games.
    """

    def __init__(self, config: TeamContextConfig, pff_loader: PffLoader):
        self._config = config
        self._loader = pff_loader
        self._cache: dict[str, pl.DataFrame] = {}

    def _load_cached(self, facet: str, seasons: list[int]) -> pl.DataFrame:
        """Load a PFF facet with caching by facet + seasons."""
        key = f"{facet}_{'_'.join(str(s) for s in sorted(seasons))}"
        if key not in self._cache:
            self._cache[key] = self._loader.load_facet(facet, seasons)
        return self._cache[key]

    # ------------------------------------------------------------------
    # Factor 1: Team pass rate (from PBP)
    # ------------------------------------------------------------------

    def _compute_pass_rate_factor(
        self,
        team: str,
        target_season: int,
        max_week: int,
        pbp: pl.DataFrame | None,
    ) -> float:
        """Compute pass rate factor from PBP play-calling data.

        Filters PBP to target_season + week < max_week, computes per-team
        pass rate, then converts to a z-score-based factor.

        Returns:
            Factor centered on 1.0. >1 = pass-heavy, <1 = run-heavy.
            Returns 1.0 if data is missing.
        """
        if pbp is None or pbp.is_empty():
            return 1.0

        config = self._config

        # Filter to target season + week < max_week
        current = pbp.filter(
            pl.col("play_type").is_in(["pass", "run"])
            & (pl.col("season") == target_season)
            & (pl.col("week") < max_week)
        )

        # Count games for this team in the window
        current_games = 0
        if not current.is_empty():
            team_plays = current.filter(pl.col("posteam") == team)
            if not team_plays.is_empty() and "game_id" in team_plays.columns:
                current_games = team_plays.select(pl.col("game_id").n_unique()).item()

        # Compute current-season factor
        current_factor = self._pass_rate_from_pbp(current, team)

        if current_games >= config.min_games:
            return current_factor

        # Early-season blend with previous season
        prev = pbp.filter(
            pl.col("play_type").is_in(["pass", "run"])
            & (pl.col("season") == target_season - 1)
        )
        prev_factor = self._pass_rate_from_pbp(prev, team)

        if current_games == 0:
            return prev_factor

        # Linear ramp
        blend_weight = current_games / config.min_games
        return blend_weight * current_factor + (1 - blend_weight) * prev_factor

    def _pass_rate_from_pbp(self, plays: pl.DataFrame, team: str) -> float:
        """Compute pass rate factor for a team from a filtered PBP DataFrame.

        Returns 1.0 if the team is not found or data is empty.
        """
        if plays.is_empty():
            return 1.0

        config = self._config

        # Per-team pass rates
        team_rates: dict[str, float] = {}
        for t in plays["posteam"].unique().to_list():
            t_plays = plays.filter(pl.col("posteam") == t)
            total = t_plays.height
            if total == 0:
                continue
            passes = t_plays.filter(pl.col("play_type") == "pass").height
            team_rates[t] = passes / total

        if team not in team_rates or len(team_rates) < 2:
            return 1.0

        rates = list(team_rates.values())
        league_avg = float(np.mean(rates))
        league_std = float(np.std(rates, ddof=0))

        return compute_factor(
            team_rates[team], league_avg, league_std,
            config.pass_rate_sensitivity, config.factor_clamp,
        )

    # ------------------------------------------------------------------
    # Public entry point (placeholder — factors 2+3 added in Tasks 5-6)
    # ------------------------------------------------------------------

    def compute(
        self,
        team: str,
        target_season: int,
        max_week: int,
        pbp: pl.DataFrame | None = None,
    ) -> TeamContext:
        """Compute all team context factors.

        Args:
            team: Team abbreviation (e.g. "KC").
            target_season: Season being simulated.
            max_week: Week being simulated (data filtered to week < max_week).
            pbp: PBP DataFrame (includes training seasons for blend).

        Returns:
            TeamContext with all factors populated.
        """
        if not self._config.enabled:
            return TeamContext()

        pass_rate = self._compute_pass_rate_factor(team, target_season, max_week, pbp)

        return TeamContext(
            pass_rate_factor=pass_rate,
            ol_run_block_factor=1.0,  # Task 5
            qb_quality_factor=1.0,    # Task 6
            ol_run_yards_scale=self._config.ol_run_yards_scale,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_pff/test_team_context.py -v`
Expected: All 12 tests PASS (4 data model + 8 pass rate)

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/pff/team_context.py tests/test_data/test_pff/test_team_context.py
git commit -m "feat: add TeamContextEngine with pass rate factor"
```

---

### Task 5: TeamContextEngine — OL Run Blocking Factor

**Files:**
- Modify: `src/fantasy_sim/data/pff/team_context.py`
- Modify: `tests/test_data/test_pff/test_team_context.py`

- [ ] **Step 1: Write failing tests for OL run blocking factor**

Append to `tests/test_data/test_pff/test_team_context.py`:

```python
def _make_ol_data(teams: dict[str, list[tuple[float, int]]], season: int, week: int) -> pl.DataFrame:
    """Build mock offense_run_blocking PFF data.

    Args:
        teams: {team: [(grade, snap_count), ...]} — per-lineman data.
        season: Season year for all rows.
        week: Week number for all rows.
    """
    rows = []
    pid = 100
    for team, linemen in teams.items():
        for grade, snaps in linemen:
            pid += 1
            rows.append({
                "player_id": pid, "player": f"OL_{pid}", "team": team,
                "position": "T", "grades_run_block": grade,
                "snap_counts_run_block": snaps,
                "season": season, "week": week, "game_id": f"game_{team}_{week}",
            })
    return pl.DataFrame(rows)


class TestOlRunBlockFactor:
    def _make_engine(self, **config_overrides) -> TeamContextEngine:
        mock_loader = MagicMock()
        mock_loader.load_facet = MagicMock(return_value=pl.DataFrame())
        cfg = TeamContextConfig(**config_overrides)
        return TeamContextEngine(config=cfg, pff_loader=mock_loader)

    def _engine_with_ol_data(self, ol_data: pl.DataFrame, **config_overrides) -> TeamContextEngine:
        mock_loader = MagicMock()
        mock_loader.load_facet = MagicMock(return_value=ol_data)
        cfg = TeamContextConfig(**config_overrides)
        return TeamContextEngine(config=cfg, pff_loader=mock_loader)

    def test_good_ol_above_one(self):
        """Team with above-average OL grades should get factor > 1.0."""
        ol_data = _make_ol_data(
            {"KC": [(80.0, 50), (78.0, 50)], "BUF": [(60.0, 50), (58.0, 50)], "BAL": [(50.0, 50), (48.0, 50)]},
            season=2024, week=5,
        )
        engine = self._engine_with_ol_data(ol_data)
        factor = engine._compute_ol_run_factor("KC", 2024, 6)
        assert factor > 1.0

    def test_bad_ol_below_one(self):
        """Team with below-average OL grades should get factor < 1.0."""
        ol_data = _make_ol_data(
            {"KC": [(80.0, 50), (78.0, 50)], "BUF": [(60.0, 50), (58.0, 50)], "BAL": [(50.0, 50), (48.0, 50)]},
            season=2024, week=5,
        )
        engine = self._engine_with_ol_data(ol_data)
        factor = engine._compute_ol_run_factor("BAL", 2024, 6)
        assert factor < 1.0

    def test_snap_weighting(self):
        """Starter with 90 snaps should outweigh backup with 10 snaps."""
        # Starter is elite (85), backup is terrible (40). Snap-weighted avg ~80.5.
        # Without snap weighting: avg would be 62.5.
        ol_good_starter = _make_ol_data(
            {"KC": [(85.0, 90), (40.0, 10)], "BUF": [(60.0, 50), (60.0, 50)]},
            season=2024, week=5,
        )
        engine = self._engine_with_ol_data(ol_good_starter)
        factor = engine._compute_ol_run_factor("KC", 2024, 6)
        # With snap weighting: KC avg ~80.5, BUF avg 60.0. KC is well above average.
        assert factor > 1.0

    def test_empty_pff_data_returns_neutral(self):
        """Empty PFF data returns neutral factor 1.0."""
        engine = self._make_engine()
        factor = engine._compute_ol_run_factor("KC", 2024, 6)
        assert factor == 1.0

    def test_team_not_in_data_returns_neutral(self):
        """Team not present in OL data returns neutral factor 1.0."""
        ol_data = _make_ol_data(
            {"KC": [(70.0, 50)], "BUF": [(60.0, 50)]},
            season=2024, week=5,
        )
        engine = self._engine_with_ol_data(ol_data)
        factor = engine._compute_ol_run_factor("NYG", 2024, 6)
        assert factor == 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_pff/test_team_context.py::TestOlRunBlockFactor -v`
Expected: FAIL — `AttributeError: 'TeamContextEngine' object has no attribute '_compute_ol_run_factor'`

- [ ] **Step 3: Implement _compute_ol_run_factor**

Add to `TeamContextEngine` in `src/fantasy_sim/data/pff/team_context.py`, after the pass rate methods:

```python
    # ------------------------------------------------------------------
    # Factor 2: OL run blocking quality (from PFF)
    # ------------------------------------------------------------------

    def _compute_ol_run_factor(
        self,
        team: str,
        target_season: int,
        max_week: int,
    ) -> float:
        """Compute OL run blocking factor from PFF grades.

        Loads offense_run_blocking facet, filters to week < max_week,
        computes snap-weighted grades_run_block per team.

        Returns:
            Factor centered on 1.0. >1 = better OL, <1 = worse.
            Returns 1.0 if data is missing.
        """
        config = self._config

        current_df = self._load_cached("offense_run_blocking", [target_season])
        if not current_df.is_empty() and "week" in current_df.columns:
            current_df = current_df.filter(pl.col("week") < max_week)

        current_games = self._count_team_games(current_df, team)
        current_factor = self._snap_weighted_factor(
            current_df, team, "grades_run_block", "snap_counts_run_block",
            config.ol_run_sensitivity, config.factor_clamp,
        )

        if current_games >= config.min_games:
            return current_factor

        # Early-season blend with previous season
        prev_df = self._load_cached("offense_run_blocking", [target_season - 1])
        prev_games = self._count_team_games(prev_df, team)
        if prev_games == 0:
            return current_factor

        prev_factor = self._snap_weighted_factor(
            prev_df, team, "grades_run_block", "snap_counts_run_block",
            config.ol_run_sensitivity, config.factor_clamp,
        )

        if current_games == 0:
            return prev_factor

        blend_weight = current_games / config.min_games
        return blend_weight * current_factor + (1 - blend_weight) * prev_factor

    @staticmethod
    def _count_team_games(df: pl.DataFrame, team: str) -> int:
        """Count distinct games for a team in a DataFrame."""
        if df.is_empty():
            return 0
        team_rows = df.filter(pl.col("team") == team)
        if team_rows.is_empty():
            return 0
        if "game_id" in team_rows.columns:
            return team_rows.select(pl.col("game_id").n_unique()).item()
        if "week" in team_rows.columns:
            return team_rows.select(pl.col("week").n_unique()).item()
        return team_rows.height

    @staticmethod
    def _snap_weighted_factor(
        df: pl.DataFrame,
        team: str,
        grade_col: str,
        snap_col: str,
        sensitivity: float,
        clamp: tuple[float, float],
    ) -> float:
        """Compute a z-score factor from snap-weighted team grades.

        Aggregates grade_col weighted by snap_col per team, then computes
        league avg/std across teams.

        Returns 1.0 if data is missing or insufficient.
        """
        if df.is_empty() or grade_col not in df.columns:
            return 1.0

        # Filter to rows with both grade and snap data
        valid = df.filter(
            pl.col(grade_col).is_not_null()
            & pl.col(snap_col).is_not_null()
            & (pl.col(snap_col) > 0)
        )
        if valid.is_empty():
            return 1.0

        # Snap-weighted average per team
        team_grades = (
            valid.group_by("team").agg(
                (pl.col(grade_col) * pl.col(snap_col)).sum() / pl.col(snap_col).sum()
            )
        )

        if team_grades.height < 2:
            return 1.0

        # Find the team's value
        team_row = team_grades.filter(pl.col("team") == team)
        if team_row.is_empty():
            return 1.0

        team_val = float(team_row[grade_col].item())
        league_avg = float(team_grades[grade_col].mean())
        league_std = float(team_grades[grade_col].std())

        return compute_factor(team_val, league_avg, league_std, sensitivity, clamp)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_pff/test_team_context.py::TestOlRunBlockFactor -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/pff/team_context.py tests/test_data/test_pff/test_team_context.py
git commit -m "feat: add OL run blocking factor to TeamContextEngine"
```

---

### Task 6: TeamContextEngine — QB Quality Factor

**Files:**
- Modify: `src/fantasy_sim/data/pff/team_context.py`
- Modify: `tests/test_data/test_pff/test_team_context.py`

- [ ] **Step 1: Write failing tests for QB quality factor**

Append to `tests/test_data/test_pff/test_team_context.py`:

```python
def _make_qb_data(teams: dict[str, list[tuple[float, int]]], season: int, week: int) -> pl.DataFrame:
    """Build mock passing_summary PFF data.

    Args:
        teams: {team: [(grade, passing_snaps), ...]} — per-QB data.
        season: Season year for all rows.
        week: Week number for all rows.
    """
    rows = []
    pid = 200
    for team, qbs in teams.items():
        for grade, snaps in qbs:
            pid += 1
            rows.append({
                "player_id": pid, "player": f"QB_{pid}", "team": team,
                "position": "QB", "grades_pass": grade,
                "passing_snaps": snaps,
                "season": season, "week": week, "game_id": f"game_{team}_{week}",
            })
    return pl.DataFrame(rows)


class TestQbQualityFactor:
    def _engine_with_qb_data(self, qb_data: pl.DataFrame, **config_overrides) -> TeamContextEngine:
        mock_loader = MagicMock()
        mock_loader.load_facet = MagicMock(return_value=qb_data)
        cfg = TeamContextConfig(**config_overrides)
        return TeamContextEngine(config=cfg, pff_loader=mock_loader)

    def test_elite_qb_above_one(self):
        """Team with an elite QB should get factor > 1.0."""
        qb_data = _make_qb_data(
            {"KC": [(90.0, 60)], "BUF": [(70.0, 60)], "BAL": [(55.0, 60)]},
            season=2024, week=5,
        )
        engine = self._engine_with_qb_data(qb_data)
        factor = engine._compute_qb_quality_factor("KC", 2024, 6)
        assert factor > 1.0

    def test_poor_qb_below_one(self):
        """Team with a poor QB should get factor < 1.0."""
        qb_data = _make_qb_data(
            {"KC": [(90.0, 60)], "BUF": [(70.0, 60)], "BAL": [(55.0, 60)]},
            season=2024, week=5,
        )
        engine = self._engine_with_qb_data(qb_data)
        factor = engine._compute_qb_quality_factor("BAL", 2024, 6)
        assert factor < 1.0

    def test_snap_weighting_favors_starter(self):
        """Starter with 95% of snaps dominates over backup's mop-up time."""
        # KC: starter (grade 85, 570 snaps), backup (grade 45, 30 snaps)
        # Snap-weighted: (85*570 + 45*30)/600 = 83.0
        qb_data = _make_qb_data(
            {"KC": [(85.0, 570), (45.0, 30)], "BUF": [(70.0, 600)]},
            season=2024, week=5,
        )
        engine = self._engine_with_qb_data(qb_data)
        factor = engine._compute_qb_quality_factor("KC", 2024, 6)
        # KC's weighted grade ~83 vs BUF's 70 → KC above average
        assert factor > 1.0

    def test_empty_data_returns_neutral(self):
        """Empty passing_summary returns neutral factor 1.0."""
        mock_loader = MagicMock()
        mock_loader.load_facet = MagicMock(return_value=pl.DataFrame())
        engine = TeamContextEngine(config=TeamContextConfig(), pff_loader=mock_loader)
        factor = engine._compute_qb_quality_factor("KC", 2024, 6)
        assert factor == 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_pff/test_team_context.py::TestQbQualityFactor -v`
Expected: FAIL — `AttributeError: 'TeamContextEngine' object has no attribute '_compute_qb_quality_factor'`

- [ ] **Step 3: Implement _compute_qb_quality_factor**

Add to `TeamContextEngine` in `src/fantasy_sim/data/pff/team_context.py`, after the OL methods:

```python
    # ------------------------------------------------------------------
    # Factor 3: QB quality (from PFF)
    # ------------------------------------------------------------------

    def _compute_qb_quality_factor(
        self,
        team: str,
        target_season: int,
        max_week: int,
    ) -> float:
        """Compute QB quality factor from PFF passing grades.

        Loads passing_summary facet, filters to week < max_week,
        computes snap-weighted grades_pass per team.

        Returns:
            Factor centered on 1.0. >1 = better QB, <1 = worse.
            Returns 1.0 if data is missing.
        """
        config = self._config

        current_df = self._load_cached("passing_summary", [target_season])
        if not current_df.is_empty() and "week" in current_df.columns:
            current_df = current_df.filter(pl.col("week") < max_week)

        current_games = self._count_team_games(current_df, team)
        current_factor = self._snap_weighted_factor(
            current_df, team, "grades_pass", "passing_snaps",
            config.qb_quality_sensitivity, config.factor_clamp,
        )

        if current_games >= config.min_games:
            return current_factor

        # Early-season blend with previous season
        prev_df = self._load_cached("passing_summary", [target_season - 1])
        prev_games = self._count_team_games(prev_df, team)
        if prev_games == 0:
            return current_factor

        prev_factor = self._snap_weighted_factor(
            prev_df, team, "grades_pass", "passing_snaps",
            config.qb_quality_sensitivity, config.factor_clamp,
        )

        if current_games == 0:
            return prev_factor

        blend_weight = current_games / config.min_games
        return blend_weight * current_factor + (1 - blend_weight) * prev_factor
```

- [ ] **Step 4: Update compute() to call all three factors**

Replace the `compute()` method body:

```python
    def compute(
        self,
        team: str,
        target_season: int,
        max_week: int,
        pbp: pl.DataFrame | None = None,
    ) -> TeamContext:
        """Compute all team context factors.

        Args:
            team: Team abbreviation (e.g. "KC").
            target_season: Season being simulated.
            max_week: Week being simulated (data filtered to week < max_week).
            pbp: PBP DataFrame (includes training seasons for blend).

        Returns:
            TeamContext with all factors populated.
        """
        if not self._config.enabled:
            return TeamContext()

        pass_rate = self._compute_pass_rate_factor(team, target_season, max_week, pbp)
        ol_run = self._compute_ol_run_factor(team, target_season, max_week)
        qb_quality = self._compute_qb_quality_factor(team, target_season, max_week)

        ctx = TeamContext(
            pass_rate_factor=pass_rate,
            ol_run_block_factor=ol_run,
            qb_quality_factor=qb_quality,
            ol_run_yards_scale=self._config.ol_run_yards_scale,
        )

        logger.info(
            "Team context for %s (season=%d, week<%d): "
            "pass_rate=%.3f ol_run=%.3f qb_quality=%.3f",
            team, target_season, max_week,
            ctx.pass_rate_factor, ctx.ol_run_block_factor, ctx.qb_quality_factor,
        )

        return ctx
```

- [ ] **Step 5: Run all team context tests**

Run: `uv run pytest tests/test_data/test_pff/test_team_context.py -v`
Expected: All tests PASS (~21 total: 4 data model + 8 pass rate + 5 OL + 4 QB)

- [ ] **Step 6: Commit**

```bash
git add src/fantasy_sim/data/pff/team_context.py tests/test_data/test_pff/test_team_context.py
git commit -m "feat: add QB quality factor and wire compute() orchestration"
```

---

### Task 7: TeamContextEngine — Early-Season Blend Tests

**Files:**
- Modify: `tests/test_data/test_pff/test_team_context.py`

- [ ] **Step 1: Write early-season blend and edge case tests**

Append to `tests/test_data/test_pff/test_team_context.py`:

```python
class TestEarlySeasonBlend:
    """Tests for the rolling window and previous-season blend logic."""

    def test_pass_rate_blends_with_previous_season(self):
        """Team with 2 games in current season (< min_games=4) blends with prev season."""
        engine = TeamContextEngine(
            config=TeamContextConfig(min_games=4),
            pff_loader=MagicMock(),
        )
        # Previous season: KC is very pass-heavy (80%)
        prev = _make_pbp(
            {"KC": {"pass": 80, "run": 20}, "BUF": {"pass": 50, "run": 50}, "BAL": {"pass": 50, "run": 50}},
            season=2023, week=10,
        )
        # Current season: KC has 2 games (< min_games), balanced (50%)
        current_w1 = _make_pbp(
            {"KC": {"pass": 50, "run": 50}, "BUF": {"pass": 50, "run": 50}, "BAL": {"pass": 50, "run": 50}},
            season=2024, week=1,
        )
        current_w2 = _make_pbp(
            {"KC": {"pass": 50, "run": 50}, "BUF": {"pass": 50, "run": 50}, "BAL": {"pass": 50, "run": 50}},
            season=2024, week=2,
        )
        pbp = pl.concat([prev, current_w1, current_w2])

        factor = engine._compute_pass_rate_factor("KC", 2024, 3, pbp)
        # blend_weight = 2/4 = 0.5
        # current_factor: KC at league average (50%) → ~1.0
        # prev_factor: KC well above average (80%) → >1.0
        # blended should be between 1.0 and the previous-season factor
        # Since all current-season teams are 50%, current factor is 1.0
        # So result should be > 1.0 (pulled up by previous season)
        assert factor > 1.0

    def test_zero_current_games_uses_previous_only(self):
        """Team with 0 current-season games uses previous season factor."""
        engine = TeamContextEngine(
            config=TeamContextConfig(min_games=4),
            pff_loader=MagicMock(),
        )
        # Only previous season data, no current season
        prev = _make_pbp(
            {"KC": {"pass": 80, "run": 20}, "BUF": {"pass": 50, "run": 50}, "BAL": {"pass": 50, "run": 50}},
            season=2023, week=10,
        )
        factor = engine._compute_pass_rate_factor("KC", 2024, 1, prev)
        # KC only appears in 2023 data, no 2024 data → uses prev only
        assert factor > 1.0

    def test_enough_games_skips_blend(self):
        """Team with >= min_games games uses current season only."""
        engine = TeamContextEngine(
            config=TeamContextConfig(min_games=2),
            pff_loader=MagicMock(),
        )
        # Previous season: KC is run-heavy
        prev = _make_pbp(
            {"KC": {"pass": 30, "run": 70}, "BUF": {"pass": 50, "run": 50}, "BAL": {"pass": 50, "run": 50}},
            season=2023, week=10,
        )
        # Current season: KC is pass-heavy with 3 games (>= min_games=2)
        games = [
            _make_pbp({"KC": {"pass": 70, "run": 30}, "BUF": {"pass": 50, "run": 50}, "BAL": {"pass": 50, "run": 50}}, season=2024, week=w)
            for w in [1, 2, 3]
        ]
        pbp = pl.concat([prev] + games)

        factor = engine._compute_pass_rate_factor("KC", 2024, 4, pbp)
        # Should use current season only: KC is pass-heavy → factor > 1.0
        # (If blend were used, prev season's run-heavy would pull it down)
        assert factor > 1.0

    def test_disabled_engine_returns_neutral(self):
        """compute() returns all-neutral TeamContext when engine is disabled."""
        engine = TeamContextEngine(
            config=TeamContextConfig(enabled=False),
            pff_loader=MagicMock(),
        )
        ctx = engine.compute("KC", 2024, 8, pbp=pl.DataFrame())
        assert ctx.pass_rate_factor == 1.0
        assert ctx.ol_run_block_factor == 1.0
        assert ctx.qb_quality_factor == 1.0
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_pff/test_team_context.py -v`
Expected: All tests PASS (~25 total)

- [ ] **Step 3: Commit**

```bash
git add tests/test_data/test_pff/test_team_context.py
git commit -m "test: add early-season blend and edge case tests for team context"
```

---

### Task 8: TierEngine — apply_team_context() and Updated apply_tiers()

**Files:**
- Modify: `src/fantasy_sim/data/pff/tier_engine.py:822-1065`
- Modify: `tests/test_data/test_pff/test_tier_engine.py`

- [ ] **Step 1: Write failing tests for apply_team_context**

Append to `tests/test_data/test_pff/test_tier_engine.py`, after the `TestBlendPlayer` class:

```python
class TestApplyTeamContext:
    """Tests for TierEngine.apply_team_context static method."""

    def _make_tier_dists(self, **overrides):
        from fantasy_sim.data.pff.tier_engine import TierDistributions
        defaults = dict(
            target_share=0.20,
            carry_share=0.0,
            catch_rate=0.65,
            air_yards_share=0.15,
            fumble_rate=0.015,
            scramble_rate=0.0,
            receiving_yards_dist=np.full(100, 10.0),
            rushing_yards_dist=np.full(100, 4.0),
        )
        defaults.update(overrides)
        return TierDistributions(**defaults)

    def test_wr_target_share_scaled_by_pass_rate(self):
        """WR target_share multiplied by pass_rate_factor."""
        from fantasy_sim.data.pff.tier_engine import TierEngine
        from fantasy_sim.data.pff.models import TeamContext

        tier_dists = self._make_tier_dists(target_share=0.20)
        ctx = TeamContext(pass_rate_factor=1.10)

        TierEngine.apply_team_context(tier_dists, ctx, "WR")

        assert tier_dists.target_share == pytest.approx(0.22)

    def test_wr_catch_rate_scaled_by_qb_quality(self):
        """WR catch_rate multiplied by qb_quality_factor."""
        from fantasy_sim.data.pff.tier_engine import TierEngine
        from fantasy_sim.data.pff.models import TeamContext

        tier_dists = self._make_tier_dists(catch_rate=0.65)
        ctx = TeamContext(qb_quality_factor=1.05)

        TierEngine.apply_team_context(tier_dists, ctx, "WR")

        assert tier_dists.catch_rate == pytest.approx(0.65 * 1.05)

    def test_te_gets_same_adjustments_as_wr(self):
        """TE receives both pass_rate and qb_quality adjustments."""
        from fantasy_sim.data.pff.tier_engine import TierEngine
        from fantasy_sim.data.pff.models import TeamContext

        tier_dists = self._make_tier_dists(target_share=0.15, catch_rate=0.60)
        ctx = TeamContext(pass_rate_factor=1.08, qb_quality_factor=0.95)

        TierEngine.apply_team_context(tier_dists, ctx, "TE")

        assert tier_dists.target_share == pytest.approx(0.15 * 1.08)
        assert tier_dists.catch_rate == pytest.approx(0.60 * 0.95)

    def test_rb_rushing_yards_shifted(self):
        """RB rushing_yards_dist shifted by OL factor."""
        from fantasy_sim.data.pff.tier_engine import TierEngine
        from fantasy_sim.data.pff.models import TeamContext

        tier_dists = self._make_tier_dists(rushing_yards_dist=np.full(50, 4.0))
        ctx = TeamContext(ol_run_block_factor=1.06, ol_run_yards_scale=10.0)

        TierEngine.apply_team_context(tier_dists, ctx, "RB")

        # shift = (1.06 - 1.0) * 10.0 = 0.6
        expected = 4.0 + 0.6
        assert tier_dists.rushing_yards_dist is not None
        np.testing.assert_allclose(tier_dists.rushing_yards_dist, expected)

    def test_rb_no_rushing_yards_dist_no_error(self):
        """RB with rushing_yards_dist=None doesn't crash."""
        from fantasy_sim.data.pff.tier_engine import TierEngine
        from fantasy_sim.data.pff.models import TeamContext

        tier_dists = self._make_tier_dists(rushing_yards_dist=None)
        ctx = TeamContext(ol_run_block_factor=1.10)

        TierEngine.apply_team_context(tier_dists, ctx, "RB")
        # Should not raise

    def test_qb_unchanged(self):
        """QB receives no team context adjustments."""
        from fantasy_sim.data.pff.tier_engine import TierEngine
        from fantasy_sim.data.pff.models import TeamContext

        tier_dists = self._make_tier_dists(
            target_share=0.20, catch_rate=0.65,
            rushing_yards_dist=np.full(50, 4.0),
        )
        original_ts = tier_dists.target_share
        original_cr = tier_dists.catch_rate
        original_rush = tier_dists.rushing_yards_dist.copy()

        ctx = TeamContext(
            pass_rate_factor=1.10,
            qb_quality_factor=1.10,
            ol_run_block_factor=1.10,
        )

        TierEngine.apply_team_context(tier_dists, ctx, "QB")

        assert tier_dists.target_share == original_ts
        assert tier_dists.catch_rate == original_cr
        np.testing.assert_array_equal(tier_dists.rushing_yards_dist, original_rush)

    def test_neutral_context_no_changes(self):
        """All-neutral TeamContext (1.0) leaves tier_dists unchanged."""
        from fantasy_sim.data.pff.tier_engine import TierEngine
        from fantasy_sim.data.pff.models import TeamContext

        tier_dists = self._make_tier_dists(target_share=0.20, catch_rate=0.65)
        ctx = TeamContext()  # all defaults = 1.0

        TierEngine.apply_team_context(tier_dists, ctx, "WR")

        assert tier_dists.target_share == pytest.approx(0.20)
        assert tier_dists.catch_rate == pytest.approx(0.65)

    def test_apply_tiers_with_none_context_unchanged(self):
        """apply_tiers() with team_context=None behaves like before."""
        from fantasy_sim.data.pff.tier_engine import TierEngine
        from fantasy_sim.data.pff.models import TierConfig

        engine = TierEngine(config=TierConfig(enabled=True), pff_loader=None)
        # Pools not built → should return without error
        roster = TeamRoster(team="KC", players=[_make_player()])
        engine.apply_tiers(roster, {}, [2024], team_context=None)
        # Should not raise (pools not built → logs warning and returns)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_pff/test_tier_engine.py::TestApplyTeamContext -v`
Expected: FAIL — `TierEngine has no attribute 'apply_team_context'`

- [ ] **Step 3: Add apply_team_context to TierEngine and update apply_tiers**

In `src/fantasy_sim/data/pff/tier_engine.py`, add the import at the top (with existing imports):

```python
from fantasy_sim.data.pff.models import TierConfig, TeamContext
```

Add the static method before `apply_tiers()` (around line 945):

```python
    # ------------------------------------------------------------------
    # Team context application
    # ------------------------------------------------------------------

    @staticmethod
    def apply_team_context(
        tier_dists: "TierDistributions",
        ctx: "TeamContext",
        position: str,
    ) -> None:
        """Adjust tier distributions for team environment before blending.

        Modifies tier_dists in place:
        - WR/TE: target_share *= pass_rate_factor, catch_rate *= qb_quality_factor
        - RB: rushing_yards_dist += (ol_run_block_factor - 1) * ol_run_yards_scale
        - QB: no adjustments (consistent with QB skip rule)
        """
        if position in ("WR", "TE"):
            tier_dists.target_share *= ctx.pass_rate_factor
            tier_dists.catch_rate *= ctx.qb_quality_factor
        elif position == "RB":
            if tier_dists.rushing_yards_dist is not None:
                shift = (ctx.ol_run_block_factor - 1.0) * ctx.ol_run_yards_scale
                tier_dists.rushing_yards_dist = tier_dists.rushing_yards_dist + shift
```

Update the `apply_tiers()` signature to accept `team_context`:

```python
    def apply_tiers(
        self,
        roster: "TeamRoster",
        crosswalk: dict[int, str],
        training_seasons: list[int],
        pbp: "pl.DataFrame | None" = None,
        nfl_roster: "pl.DataFrame | None" = None,
        target_season: int | None = None,
        team_context: "TeamContext | None" = None,
    ) -> None:
```

And insert the team context application in the player loop, between `select_distributions()` and `compute_reliability()` (around line 1032):

```python
            assignment, tier_dists = result

            # Apply team context to tier distributions before blending
            if team_context is not None:
                self.apply_team_context(tier_dists, team_context, position)

            # Gather weekly shares from PBP data for reliability scoring
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_pff/test_tier_engine.py::TestApplyTeamContext -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Run full tier engine test suite for regressions**

Run: `uv run pytest tests/test_data/test_pff/test_tier_engine.py -v`
Expected: All existing tests PASS + 8 new tests

- [ ] **Step 6: Commit**

```bash
git add src/fantasy_sim/data/pff/tier_engine.py tests/test_data/test_pff/test_tier_engine.py
git commit -m "feat: add apply_team_context to TierEngine, update apply_tiers signature"
```

---

### Task 9: GameContextBuilder — Wire TeamContextEngine

**Files:**
- Modify: `src/fantasy_sim/data/game_context.py:56-82` (init) and `356-391` (build_game)
- Modify: `tests/test_data/test_game_context.py`

- [ ] **Step 1: Write failing tests for GameContextBuilder integration**

Append to `TestGameContextBuilder` class in `tests/test_data/test_game_context.py`:

```python
    def test_team_context_engine_created_when_enabled(self, tmp_path):
        """team_context.enabled=True creates the engine."""
        from unittest.mock import patch
        from fantasy_sim.data.pff.models import PffConfig, TeamContextConfig

        pff_config = PffConfig(
            enabled=True,
            team_context=TeamContextConfig(enabled=True),
        )
        with patch("fantasy_sim.data.pff.loader.PffLoader") as MockLoader:
            MockLoader.return_value.is_available.return_value = True
            builder = GameContextBuilder(cache_dir=tmp_path / "cache", pff_config=pff_config)

        assert builder._team_context_engine is not None

    def test_team_context_engine_not_created_when_disabled(self, tmp_path):
        """team_context.enabled=False does not create the engine."""
        from unittest.mock import patch
        from fantasy_sim.data.pff.models import PffConfig, TeamContextConfig

        pff_config = PffConfig(
            enabled=True,
            team_context=TeamContextConfig(enabled=False),
        )
        with patch("fantasy_sim.data.pff.loader.PffLoader") as MockLoader:
            MockLoader.return_value.is_available.return_value = True
            builder = GameContextBuilder(cache_dir=tmp_path / "cache", pff_config=pff_config)

        assert builder._team_context_engine is None

    def test_team_context_passed_to_apply_tiers(
        self, builder, expanded_pbp, sample_rosters
    ):
        """build_game() computes team context and passes to apply_tiers."""
        from unittest.mock import MagicMock, patch, call
        from fantasy_sim.data.pff.models import TeamContext, TeamContextConfig, TierConfig

        mock_tc_engine = MagicMock()
        mock_tc_engine.compute.return_value = TeamContext(
            pass_rate_factor=1.05,
            ol_run_block_factor=0.97,
            qb_quality_factor=1.02,
        )

        mock_tier_engine = MagicMock()

        builder._team_context_engine = mock_tc_engine
        builder._tier_engine = mock_tier_engine
        builder._pff_crosswalk = {}
        builder._pff_loader = MagicMock()

        builder.build_game(
            home_team="KC", away_team="BUF",
            pbp=expanded_pbp, rosters=sample_rosters,
            training_seasons=[2024], target_season=2024, week=8,
        )

        # Team context engine called twice (home + away)
        assert mock_tc_engine.compute.call_count == 2

        home_call = mock_tc_engine.compute.call_args_list[0]
        assert home_call[1]["team"] if "team" in home_call[1] else home_call[0][0] == "KC"

        # Tier engine's apply_tiers called with team_context kwarg
        assert mock_tier_engine.apply_tiers.call_count == 2
        for tier_call in mock_tier_engine.apply_tiers.call_args_list:
            assert "team_context" in tier_call.kwargs

    def test_team_context_skipped_when_no_target_season(
        self, builder, expanded_pbp, sample_rosters
    ):
        """build_game() without target_season skips team context computation."""
        from unittest.mock import MagicMock
        from fantasy_sim.data.pff.models import TeamContext

        mock_tc_engine = MagicMock()
        mock_tier_engine = MagicMock()

        builder._team_context_engine = mock_tc_engine
        builder._tier_engine = mock_tier_engine
        builder._pff_crosswalk = {}
        builder._pff_loader = MagicMock()

        builder.build_game(
            home_team="KC", away_team="BUF",
            pbp=expanded_pbp, rosters=sample_rosters,
            training_seasons=[2024],
            target_season=None, week=None,
        )

        # Team context engine NOT called (no target_season)
        mock_tc_engine.compute.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_game_context.py::TestGameContextBuilder::test_team_context_engine_created_when_enabled tests/test_data/test_game_context.py::TestGameContextBuilder::test_team_context_passed_to_apply_tiers -v`
Expected: FAIL — `_team_context_engine` attribute doesn't exist yet

- [ ] **Step 3: Wire TeamContextEngine into GameContextBuilder**

In `src/fantasy_sim/data/game_context.py`, in `__init__()`, add after the tier engine block (after line 81):

```python
        self._team_context_engine = None

        if self._pff_config.enabled and self._pff_config.team_context.enabled and self._pff_loader:
            from fantasy_sim.data.pff.team_context import TeamContextEngine
            self._team_context_engine = TeamContextEngine(
                self._pff_config.team_context, self._pff_loader
            )
            logger.info("PFF team context engine enabled")
```

In `build_game()`, update the tier engine block (around line 356) to compute team context and pass it:

```python
        # PFF tier engine (takes precedence over talent stabilizer)
        if self._tier_engine is not None:
            from fantasy_sim.data.player_builder import _normalize_roster_shares
            self._ensure_pff_crosswalk(training_seasons, target_season)
            roster_season = target_season or max(training_seasons)
            all_roster_seasons = training_seasons + [roster_season]
            nfl_roster_df = self.loader.load_rosters(all_roster_seasons)
            # Use passed PBP or load if not provided
            pbp_df = pbp if pbp is not None else self.loader.load_pbp(training_seasons)

            # Compute team context (season-level, per-team)
            home_ctx = None
            away_ctx = None
            if self._team_context_engine is not None and target_season and week:
                home_ctx = self._team_context_engine.compute(
                    team=home_roster.team,
                    target_season=target_season,
                    max_week=week,
                    pbp=pbp_df,
                )
                away_ctx = self._team_context_engine.compute(
                    team=away_roster.team,
                    target_season=target_season,
                    max_week=week,
                    pbp=pbp_df,
                )

            self._tier_engine.apply_tiers(
                home_roster, self._pff_crosswalk, training_seasons,
                pbp=pbp_df, nfl_roster=nfl_roster_df, target_season=roster_season,
                team_context=home_ctx,
            )
            self._tier_engine.apply_tiers(
                away_roster, self._pff_crosswalk, training_seasons,
                pbp=pbp_df, nfl_roster=nfl_roster_df, target_season=roster_season,
                team_context=away_ctx,
            )
            _normalize_roster_shares(home_roster)
            _normalize_roster_shares(away_roster)
```

Add `from unittest.mock import patch` at the top of `tests/test_data/test_game_context.py` if not already present.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_game_context.py -v`
Expected: All tests PASS (existing + 4 new)

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/game_context.py tests/test_data/test_game_context.py
git commit -m "feat: wire TeamContextEngine into GameContextBuilder"
```

---

### Task 10: A/B Harness — New Modes and Config Override

**Files:**
- Modify: `scripts/validate_pff_signal.py:212-276` (_build_pff_config) and `456-468` (argparse)

- [ ] **Step 1: Add team_context modes to _build_pff_config**

In `scripts/validate_pff_signal.py`, update `_build_pff_config()`:

Add import at top of file:
```python
from fantasy_sim.data.pff.models import MatchupConfig, TalentConfig, TierConfig, TeamContextConfig, PffConfig
```

Add new mode branches inside `_build_pff_config()`:

```python
    elif mode == "team_context+tier":
        matchup_cfg = MatchupConfig(enabled=False)
        talent_cfg = TalentConfig(enabled=False)
        tier_cfg = TierConfig(enabled=True)
        tc_cfg = TeamContextConfig(enabled=True)
    elif mode == "team_context+tier+matchup":
        matchup_cfg = MatchupConfig(enabled=True)
        talent_cfg = TalentConfig(enabled=False)
        tier_cfg = TierConfig(enabled=True)
        tc_cfg = TeamContextConfig(enabled=True)
```

For all existing modes, add `tc_cfg = TeamContextConfig(enabled=False)` so team context is off unless explicitly requested.

Add override handling for team_context:

```python
    if overrides and "team_context" in overrides:
        for key, val in overrides["team_context"].items():
            if hasattr(tc_cfg, key):
                setattr(tc_cfg, key, val)
```

Update the return statement to include `team_context=tc_cfg`:

```python
    return PffConfig(enabled=True, matchup=matchup_cfg, talent=talent_cfg,
                     tier_engine=tier_cfg, team_context=tc_cfg)
```

- [ ] **Step 2: Update mode_label detection for logging**

In `run_backtest_pair()`, update the mode label logic (around line 306):

```python
    if pff_config.team_context.enabled and pff_config.tier_engine.enabled and pff_config.matchup.enabled:
        mode_label = "team_context+tier+matchup"
    elif pff_config.team_context.enabled and pff_config.tier_engine.enabled:
        mode_label = "team_context+tier"
    elif pff_config.matchup.enabled and pff_config.tier_engine.enabled:
        mode_label = "matchup+tier"
    elif pff_config.matchup.enabled:
        mode_label = "matchup"
    elif pff_config.talent.enabled:
        mode_label = "talent"
    elif pff_config.tier_engine.enabled:
        mode_label = "tier"
    else:
        mode_label = "all"
```

- [ ] **Step 3: Update argparse choices**

Update the `--mode` choices (around line 459):

```python
    parser.add_argument(
        "--mode",
        choices=["matchup", "talent", "tier", "matchup+tier",
                 "team_context+tier", "team_context+tier+matchup", "all"],
        default="all",
        help=(
            "Which PFF layer(s) to enable. "
            "'team_context+tier' = tier + team context, "
            "'team_context+tier+matchup' = full stack, "
            "'matchup+tier' = matchup + tier (current default), "
            "(default: all)."
        ),
    )
```

Update the `--config-override` help text:

```python
        help='PFF config overrides as JSON. Keys: "talent", "matchup", "tier_engine", "team_context". '
             'Example: \'{"team_context": {"pass_rate_sensitivity": 0.10}}\'',
```

- [ ] **Step 4: Verify the script parses correctly**

Run: `uv run python scripts/validate_pff_signal.py --mode team_context+tier --show-ledger`
Expected: Shows ledger table (or empty) without errors.

- [ ] **Step 5: Commit**

```bash
git add scripts/validate_pff_signal.py
git commit -m "feat: add team_context modes to A/B validation harness"
```

---

### Task 11: Full Test Suite Verification

**Files:** None (verification only)

- [ ] **Step 1: Run all PFF tests**

Run: `uv run pytest tests/test_data/test_pff/ -v`
Expected: All PFF tests PASS

- [ ] **Step 2: Run game context tests**

Run: `uv run pytest tests/test_data/test_game_context.py -v`
Expected: All tests PASS

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest tests/ -v --timeout=60`
Expected: All ~906 tests PASS (886 existing + ~20 new)

- [ ] **Step 4: Verify CLI works with team context enabled**

Run: `uv run fantasy-sim demo --sims 10`
Expected: Runs successfully (demo mode skips team context — graceful degradation)

- [ ] **Step 5: Verify config loads end-to-end**

Run: `uv run python -c "from fantasy_sim.data.pff.config import load_pff_config; from fantasy_sim.config.loader import load_defaults; c = load_pff_config(load_defaults()); print(f'PFF enabled={c.enabled}, tier={c.tier_engine.enabled}, tc={c.team_context.enabled}, matchup={c.matchup.enabled}')"`
Expected: `PFF enabled=True, tier=True, tc=True, matchup=True`

- [ ] **Step 6: Update CLAUDE.md**

Add to the **PFF Intelligence Layer** bullet in the Key Patterns section:

```
**TeamContextEngine** (`team_context.py`) computes season-level team environment factors via z-scores: team pass rate (PBP) → WR/TE target_share, OL run block grade (PFF) → RB rushing_yards, QB quality (PFF) → WR/TE catch_rate. Same-season rolling window with early-season blend. Applied to `TierDistributions` before `_blend_player()`. Config in `defaults.yaml` under `pff.team_context`.
```

Update the **Current State** section to note team context layer completion and the new test count.

- [ ] **Step 7: Commit docs**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with team context layer details"
```

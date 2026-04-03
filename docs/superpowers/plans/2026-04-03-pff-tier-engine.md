# PFF Talent-Tier Distribution Engine — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the PFF talent stabilizer's mean-nudging with a tier engine that uses PFF grades to SELECT which tier of distributions a player draws from.

**Architecture:** Drop-in replacement at the same GameContextBuilder hook point (lines 346-361 of `game_context.py`). PBP-built PlayerModels are adjusted by tier-derived distributions blended via a reliability score. The talent stabilizer stays as a config-toggled fallback.

**Tech Stack:** Python 3.12+, polars, numpy, pytest, YAML config

**Spec:** `docs/superpowers/specs/2026-04-02-pff-tier-engine-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `src/fantasy_sim/data/pff/models.py` | Modify | Add TierConfig, TierDistributions, TierAssignment, PositionGradeConfig, _TierPoolEntry |
| `src/fantasy_sim/data/pff/config.py` | Modify | Parse `tier_engine:` YAML section into TierConfig |
| `config/defaults.yaml` | Modify | Add `tier_engine:` config block |
| `src/fantasy_sim/data/pff/tier_engine.py` | Create | TierEngine class — pool building, assignment, selection, reliability, blending |
| `src/fantasy_sim/data/game_context.py` | Modify | Wire TierEngine at talent stabilizer hook point |
| `scripts/validate_pff_signal.py` | Modify | Add `--mode tier` option |
| `scripts/validate_tier_spotcheck.py` | Create | 10-player before/after spot-check script |
| `tests/test_data/test_pff/test_tier_engine.py` | Create | All tier engine tests |

---

### Task 1: Config Types & YAML

**Files:**
- Modify: `src/fantasy_sim/data/pff/models.py`
- Modify: `src/fantasy_sim/data/pff/config.py`
- Modify: `config/defaults.yaml`
- Test: `tests/test_data/test_pff/test_tier_engine.py`

- [ ] **Step 1: Create test file with config parsing test**

Create `tests/test_data/test_pff/test_tier_engine.py`:

```python
"""Tests for PFF talent-tier distribution engine."""

import numpy as np
import pytest

from fantasy_sim.data.pff.models import (
    PffConfig,
    PositionGradeConfig,
    TierConfig,
)
from fantasy_sim.data.pff.config import load_pff_config


# ========== Task 1: Config ==========


class TestTierConfig:
    def test_load_tier_config_from_yaml(self):
        """TierConfig is parsed from a YAML-like dict."""
        raw = {
            "pff": {
                "enabled": True,
                "tier_engine": {
                    "enabled": True,
                    "cutoffs": [0.85, 0.65, 0.40, 0.20],
                    "position_grades": {
                        "WR": {"primary": "grades_pass_route", "secondary": "yprr"},
                        "RB": {"primary": "grades_run", "secondary": "elusive_rating"},
                    },
                    "reliability": {
                        "max_games": 32,
                        "team_change_penalty": 0.5,
                        "variance_weight": 0.3,
                        "floor": 0.15,
                        "cap": 0.85,
                    },
                    "blend_pool_size": 500,
                },
                "talent": {"enabled": False},
            }
        }
        cfg = load_pff_config(raw)

        assert cfg.tier_engine.enabled is True
        assert cfg.tier_engine.cutoffs == [0.85, 0.65, 0.40, 0.20]
        assert cfg.tier_engine.position_grades["WR"].primary == "grades_pass_route"
        assert cfg.tier_engine.position_grades["WR"].secondary == "yprr"
        assert cfg.tier_engine.reliability_floor == 0.15
        assert cfg.tier_engine.reliability_cap == 0.85
        assert cfg.tier_engine.blend_pool_size == 500
        assert cfg.talent.enabled is False

    def test_tier_config_defaults(self):
        """TierConfig uses sensible defaults when YAML is minimal."""
        raw = {"pff": {"enabled": True}}
        cfg = load_pff_config(raw)

        assert cfg.tier_engine.enabled is False
        assert cfg.tier_engine.cutoffs == [0.85, 0.65, 0.40, 0.20]
        assert len(cfg.tier_engine.position_grades) == 4

    def test_tier_and_talent_mutual_exclusion(self):
        """When tier_engine is enabled, talent should be disabled in config."""
        raw = {
            "pff": {
                "enabled": True,
                "tier_engine": {"enabled": True},
                "talent": {"enabled": True},
            }
        }
        cfg = load_pff_config(raw)
        # Both can be True in config — GameContextBuilder enforces precedence
        assert cfg.tier_engine.enabled is True
        assert cfg.talent.enabled is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data/test_pff/test_tier_engine.py::TestTierConfig -v`
Expected: ImportError — `PositionGradeConfig` and `TierConfig` don't exist yet.

- [ ] **Step 3: Add data types to models.py**

Add after the `TalentConfig` class in `src/fantasy_sim/data/pff/models.py` (before `PffConfig`):

```python
@dataclass
class PositionGradeConfig:
    """Which PFF grades define tiers for a position."""
    primary: str
    secondary: str


@dataclass
class TierConfig:
    """Configuration for the talent-tier distribution engine."""
    enabled: bool = False
    cutoffs: list[float] = field(default_factory=lambda: [0.85, 0.65, 0.40, 0.20])
    position_grades: dict[str, PositionGradeConfig] = field(default_factory=lambda: {
        "QB": PositionGradeConfig(primary="grades_pass", secondary="accuracy_percent"),
        "RB": PositionGradeConfig(primary="grades_run", secondary="elusive_rating"),
        "WR": PositionGradeConfig(primary="grades_pass_route", secondary="yprr"),
        "TE": PositionGradeConfig(primary="grades_pass_route", secondary="recv_grade"),
    })
    reliability_max_games: int = 32
    reliability_team_change_penalty: float = 0.5
    reliability_variance_weight: float = 0.3
    reliability_floor: float = 0.15
    reliability_cap: float = 0.85
    blend_pool_size: int = 500
```

Then add `tier_engine` field to `PffConfig`:

```python
@dataclass
class PffConfig:
    """Top-level PFF configuration."""
    enabled: bool = False
    data_dir: str | None = None
    matchup: MatchupConfig = field(default_factory=MatchupConfig)
    talent: TalentConfig = field(default_factory=TalentConfig)
    tier_engine: TierConfig = field(default_factory=TierConfig)
```

- [ ] **Step 4: Add config parsing to config.py**

Add `TierConfig` and `PositionGradeConfig` to the imports from `models`:

```python
from fantasy_sim.data.pff.models import (
    MatchupConfig,
    NcaaPriorsConfig,
    PffConfig,
    PositionGradeConfig,
    ScheduleAdjustmentConfig,
    TalentConfig,
    TierConfig,
)
```

Add tier engine parsing inside `load_pff_config()`, after the `talent = TalentConfig(...)` block:

```python
    tier_raw = pff.get("tier_engine", {})
    reliability_raw = tier_raw.get("reliability", {})
    pos_grades_raw = tier_raw.get("position_grades", {})
    pos_grades = {}
    for pos, grade_dict in pos_grades_raw.items():
        pos_grades[pos] = PositionGradeConfig(
            primary=grade_dict["primary"],
            secondary=grade_dict["secondary"],
        )

    tier_engine = TierConfig(
        enabled=tier_raw.get("enabled", False),
        cutoffs=tier_raw.get("cutoffs", [0.85, 0.65, 0.40, 0.20]),
        position_grades=pos_grades if pos_grades else TierConfig().position_grades,
        reliability_max_games=reliability_raw.get("max_games", 32),
        reliability_team_change_penalty=reliability_raw.get("team_change_penalty", 0.5),
        reliability_variance_weight=reliability_raw.get("variance_weight", 0.3),
        reliability_floor=reliability_raw.get("floor", 0.15),
        reliability_cap=reliability_raw.get("cap", 0.85),
        blend_pool_size=tier_raw.get("blend_pool_size", 500),
    )
```

Update the `return PffConfig(...)` to include `tier_engine=tier_engine`.

- [ ] **Step 5: Add tier_engine section to defaults.yaml**

In `config/defaults.yaml`, add under the `pff:` section (after `data_dir: null`, before `matchup:`):

```yaml
  tier_engine:
    enabled: false
    cutoffs: [0.85, 0.65, 0.40, 0.20]
    position_grades:
      QB:
        primary: grades_pass
        secondary: accuracy_percent
      RB:
        primary: grades_run
        secondary: elusive_rating
      WR:
        primary: grades_pass_route
        secondary: yprr
      TE:
        primary: grades_pass_route
        secondary: recv_grade
    reliability:
      max_games: 32
      team_change_penalty: 0.5
      variance_weight: 0.3
      floor: 0.15
      cap: 0.85
    blend_pool_size: 500
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_pff/test_tier_engine.py::TestTierConfig -v`
Expected: All 3 tests PASS.

- [ ] **Step 7: Run full test suite to check for regressions**

Run: `uv run pytest tests/ -x -q`
Expected: All existing tests still pass — the new `tier_engine` field on `PffConfig` has a default.

- [ ] **Step 8: Commit**

```bash
git add src/fantasy_sim/data/pff/models.py src/fantasy_sim/data/pff/config.py \
       config/defaults.yaml tests/test_data/test_pff/test_tier_engine.py
git commit -m "feat(pff): add TierConfig types and YAML config parsing"
```

---

### Task 2: TierEngine — Tier Assignment

**Files:**
- Create: `src/fantasy_sim/data/pff/tier_engine.py`
- Test: `tests/test_data/test_pff/test_tier_engine.py`

- [ ] **Step 1: Write tier assignment tests**

Append to `tests/test_data/test_pff/test_tier_engine.py`:

```python
from fantasy_sim.data.pff.tier_engine import TierEngine
from fantasy_sim.data.pff.models import TierConfig, PositionGradeConfig


# ========== Task 2: Tier Assignment ==========


@pytest.fixture
def tier_config():
    return TierConfig(enabled=True)


class TestTierAssignment:
    def test_assign_tier_elite(self, tier_config):
        """Player above 85th percentile -> Tier 1."""
        engine = TierEngine(tier_config, pff_loader=None)
        # Manually set boundaries for WR: 85th=82.0, 65th=72.0, 40th=60.0, 20th=48.0
        engine._boundaries = {"WR": [82.0, 72.0, 60.0, 48.0]}
        assert engine._assign_tier(90.0, "WR") == 1
        assert engine._assign_tier(82.0, "WR") == 1  # at boundary = higher tier

    def test_assign_tier_above_average(self, tier_config):
        """Player between 65th-85th percentile -> Tier 2."""
        engine = TierEngine(tier_config, pff_loader=None)
        engine._boundaries = {"WR": [82.0, 72.0, 60.0, 48.0]}
        assert engine._assign_tier(75.0, "WR") == 2
        assert engine._assign_tier(72.0, "WR") == 2  # at boundary

    def test_assign_tier_average(self, tier_config):
        engine = TierEngine(tier_config, pff_loader=None)
        engine._boundaries = {"WR": [82.0, 72.0, 60.0, 48.0]}
        assert engine._assign_tier(65.0, "WR") == 3

    def test_assign_tier_below_average(self, tier_config):
        engine = TierEngine(tier_config, pff_loader=None)
        engine._boundaries = {"WR": [82.0, 72.0, 60.0, 48.0]}
        assert engine._assign_tier(55.0, "WR") == 4

    def test_assign_tier_replacement(self, tier_config):
        """Player below 20th percentile -> Tier 5."""
        engine = TierEngine(tier_config, pff_loader=None)
        engine._boundaries = {"WR": [82.0, 72.0, 60.0, 48.0]}
        assert engine._assign_tier(40.0, "WR") == 5
        assert engine._assign_tier(10.0, "WR") == 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_pff/test_tier_engine.py::TestTierAssignment -v`
Expected: ImportError — `TierEngine` doesn't exist yet.

- [ ] **Step 3: Create TierEngine skeleton with _assign_tier**

Create `src/fantasy_sim/data/pff/tier_engine.py`:

```python
"""PFF Talent-Tier Distribution Engine.

Uses PFF grades to select which tier of distributions a player draws from,
rather than nudging means. Drop-in replacement for TalentStabilizer at the
GameContextBuilder hook point.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from fantasy_sim.data.pff.models import (
    PositionGradeConfig,
    TierConfig,
)

logger = logging.getLogger(__name__)


@dataclass
class _TierPoolEntry:
    """Internal: stored in tier pools, not exposed to callers."""
    # Scalars: (p25, median, p75) for secondary interpolation
    target_share: tuple[float, float, float] = (0.0, 0.0, 0.0)
    carry_share: tuple[float, float, float] = (0.0, 0.0, 0.0)
    catch_rate: tuple[float, float, float] = (0.0, 0.0, 0.0)
    air_yards_share: tuple[float, float, float] = (0.0, 0.0, 0.0)
    fumble_rate: tuple[float, float, float] = (0.0, 0.0, 0.0)
    scramble_rate: tuple[float, float, float] = (0.0, 0.0, 0.0)
    # Yards: full tier pool arrays
    receiving_yards_dist: np.ndarray | None = None
    rushing_yards_dist: np.ndarray | None = None
    # Secondary grade values for percentile computation
    secondary_grades: np.ndarray | None = None
    # Metadata
    n_player_seasons: int = 0


@dataclass
class TierDistributions:
    """Interpolated distributions for a specific player from their tier."""
    target_share: float = 0.0
    carry_share: float = 0.0
    catch_rate: float = 0.0
    air_yards_share: float = 0.0
    fumble_rate: float = 0.0
    scramble_rate: float = 0.0
    receiving_yards_dist: np.ndarray | None = None
    rushing_yards_dist: np.ndarray | None = None


@dataclass
class TierAssignment:
    """Result of tier assignment for one player."""
    tier: int = 3
    primary_percentile: float = 0.5
    secondary_percentile: float = 0.5
    reliability: float = 0.5


# Minimum player-seasons per tier before merging with adjacent tier
MIN_TIER_POOL_SIZE = 20


class TierEngine:
    """PFF talent-tier distribution engine.

    Uses PFF grades to assign players to talent tiers (1-5) and select
    tier-appropriate distributions. Drop-in replacement for TalentStabilizer.
    """

    def __init__(self, config: TierConfig, pff_loader):
        self._config = config
        self._pff_loader = pff_loader
        # Lazy-built caches
        self._pools: dict[str, dict[int, _TierPoolEntry]] | None = None
        self._boundaries: dict[str, list[float]] | None = None
        self._cache_key: tuple | None = None

    def _assign_tier(self, primary_grade: float, position: str) -> int:
        """Map a primary PFF grade to tier 1-5 via precomputed boundaries.

        Grades at or above a boundary get the higher (better) tier.
        """
        boundaries = self._boundaries[position]
        for tier_idx, boundary in enumerate(boundaries):
            if primary_grade >= boundary:
                return tier_idx + 1
        return 5
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_pff/test_tier_engine.py::TestTierAssignment -v`
Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/pff/tier_engine.py tests/test_data/test_pff/test_tier_engine.py
git commit -m "feat(pff): add TierEngine skeleton with tier assignment"
```

---

### Task 3: Distribution Selection & Interpolation

**Files:**
- Modify: `src/fantasy_sim/data/pff/tier_engine.py`
- Test: `tests/test_data/test_pff/test_tier_engine.py`

- [ ] **Step 1: Write interpolation and selection tests**

Append to test file:

```python
from fantasy_sim.data.pff.tier_engine import (
    TierEngine,
    TierDistributions,
    TierAssignment,
    _TierPoolEntry,
)


# ========== Task 3: Distribution Selection ==========


def _make_pool_entry(**overrides):
    """Create a _TierPoolEntry with sensible WR-like defaults."""
    defaults = dict(
        target_share=(0.15, 0.20, 0.25),
        carry_share=(0.0, 0.0, 0.0),
        catch_rate=(0.60, 0.65, 0.70),
        air_yards_share=(0.10, 0.15, 0.20),
        fumble_rate=(0.010, 0.015, 0.020),
        scramble_rate=(0.0, 0.0, 0.0),
        receiving_yards_dist=np.array([5, 8, 10, 12, 15, 20, 25, 30, 40, 50]),
        rushing_yards_dist=None,
        secondary_grades=np.array([1.2, 1.5, 1.7, 1.9, 2.1, 2.3]),
        n_player_seasons=60,
    )
    defaults.update(overrides)
    return _TierPoolEntry(**defaults)


class TestWithinTierPercentile:
    def test_median_secondary_grade(self, tier_config):
        """Secondary grade at median of tier -> 0.5 percentile."""
        engine = TierEngine(tier_config, pff_loader=None)
        engine._pools = {"WR": {2: _make_pool_entry(
            secondary_grades=np.array([1.0, 1.5, 2.0, 2.5, 3.0]),
        )}}
        pct = engine._within_tier_percentile(2.0, "WR", 2)
        assert 0.45 <= pct <= 0.55  # approximately median

    def test_high_secondary_grade(self, tier_config):
        engine = TierEngine(tier_config, pff_loader=None)
        engine._pools = {"WR": {2: _make_pool_entry(
            secondary_grades=np.array([1.0, 1.5, 2.0, 2.5, 3.0]),
        )}}
        pct = engine._within_tier_percentile(3.0, "WR", 2)
        assert pct >= 0.9

    def test_low_secondary_grade(self, tier_config):
        engine = TierEngine(tier_config, pff_loader=None)
        engine._pools = {"WR": {2: _make_pool_entry(
            secondary_grades=np.array([1.0, 1.5, 2.0, 2.5, 3.0]),
        )}}
        pct = engine._within_tier_percentile(1.0, "WR", 2)
        assert pct <= 0.1


class TestInterpolateScalars:
    def test_low_secondary_gets_p25(self, tier_config):
        """Secondary pct=0.0 -> p25 values."""
        engine = TierEngine(tier_config, pff_loader=None)
        pool = _make_pool_entry(target_share=(0.15, 0.20, 0.25))
        result = engine._interpolate_scalars(pool, 0.0)
        assert result.target_share == pytest.approx(0.15)

    def test_median_secondary_gets_p50(self, tier_config):
        """Secondary pct=0.5 -> median values."""
        engine = TierEngine(tier_config, pff_loader=None)
        pool = _make_pool_entry(target_share=(0.15, 0.20, 0.25))
        result = engine._interpolate_scalars(pool, 0.5)
        assert result.target_share == pytest.approx(0.20)

    def test_high_secondary_gets_p75(self, tier_config):
        """Secondary pct=1.0 -> p75 values."""
        engine = TierEngine(tier_config, pff_loader=None)
        pool = _make_pool_entry(target_share=(0.15, 0.20, 0.25))
        result = engine._interpolate_scalars(pool, 1.0)
        assert result.target_share == pytest.approx(0.25)

    def test_interpolation_midpoint(self, tier_config):
        """Secondary pct=0.75 -> halfway between median and p75."""
        engine = TierEngine(tier_config, pff_loader=None)
        pool = _make_pool_entry(catch_rate=(0.60, 0.65, 0.70))
        result = engine._interpolate_scalars(pool, 0.75)
        assert result.catch_rate == pytest.approx(0.675)

    def test_yards_dist_passed_through(self, tier_config):
        """Yards distributions are copied from pool, not interpolated."""
        engine = TierEngine(tier_config, pff_loader=None)
        yards = np.array([5, 10, 15, 20])
        pool = _make_pool_entry(receiving_yards_dist=yards)
        result = engine._interpolate_scalars(pool, 0.7)
        np.testing.assert_array_equal(result.receiving_yards_dist, yards)


class TestSelectDistributions:
    def test_select_returns_tier_and_distributions(self, tier_config):
        """select_distributions returns (TierAssignment, TierDistributions)."""
        engine = TierEngine(tier_config, pff_loader=None)
        engine._boundaries = {"WR": [82.0, 72.0, 60.0, 48.0]}
        engine._pools = {
            "WR": {
                1: _make_pool_entry(target_share=(0.22, 0.26, 0.30)),
                2: _make_pool_entry(target_share=(0.15, 0.20, 0.25)),
                3: _make_pool_entry(target_share=(0.10, 0.14, 0.18)),
                4: _make_pool_entry(target_share=(0.06, 0.10, 0.14)),
                5: _make_pool_entry(target_share=(0.03, 0.06, 0.09)),
            },
        }
        # Tier 2 WR (grade 75 is between 72-82 boundary)
        assignment, dists = engine.select_distributions(
            pff_grades={"grades_pass_route": 75.0, "yprr": 1.9},
            position="WR",
        )
        assert assignment.tier == 2
        assert 0.15 <= dists.target_share <= 0.25

    def test_select_missing_grades_returns_none(self, tier_config):
        """Player without required PFF grades -> None."""
        engine = TierEngine(tier_config, pff_loader=None)
        engine._boundaries = {"WR": [82.0, 72.0, 60.0, 48.0]}
        engine._pools = {"WR": {i: _make_pool_entry() for i in range(1, 6)}}
        result = engine.select_distributions(
            pff_grades={"some_other_grade": 75.0},
            position="WR",
        )
        assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_pff/test_tier_engine.py::TestWithinTierPercentile tests/test_data/test_pff/test_tier_engine.py::TestInterpolateScalars tests/test_data/test_pff/test_tier_engine.py::TestSelectDistributions -v`
Expected: AttributeError — methods don't exist yet.

- [ ] **Step 3: Implement _within_tier_percentile, _interpolate_scalars, select_distributions**

Add to `TierEngine` class in `tier_engine.py`:

```python
    def _within_tier_percentile(
        self, secondary_grade: float, position: str, tier: int,
    ) -> float:
        """Compute percentile of a secondary grade within a tier's range."""
        pool = self._pools[position][tier]
        grades = pool.secondary_grades
        if grades is None or len(grades) == 0:
            return 0.5
        # Fraction of tier members with secondary grade <= this value
        return float(np.searchsorted(np.sort(grades), secondary_grade) / len(grades))

    @staticmethod
    def _interp_scalar(low_med_high: tuple[float, float, float], pct: float) -> float:
        """Piecewise linear interpolation through (p25, p50, p75)."""
        low, med, high = low_med_high
        if pct <= 0.5:
            t = pct / 0.5
            return low + t * (med - low)
        else:
            t = (pct - 0.5) / 0.5
            return med + t * (high - med)

    def _interpolate_scalars(
        self, pool: _TierPoolEntry, secondary_pct: float,
    ) -> TierDistributions:
        """Interpolate scalar fields by secondary percentile; pass through yards."""
        return TierDistributions(
            target_share=self._interp_scalar(pool.target_share, secondary_pct),
            carry_share=self._interp_scalar(pool.carry_share, secondary_pct),
            catch_rate=self._interp_scalar(pool.catch_rate, secondary_pct),
            air_yards_share=self._interp_scalar(pool.air_yards_share, secondary_pct),
            fumble_rate=self._interp_scalar(pool.fumble_rate, secondary_pct),
            scramble_rate=self._interp_scalar(pool.scramble_rate, secondary_pct),
            receiving_yards_dist=pool.receiving_yards_dist,
            rushing_yards_dist=pool.rushing_yards_dist,
        )

    def select_distributions(
        self,
        pff_grades: dict[str, float],
        position: str,
    ) -> tuple[TierAssignment, TierDistributions] | None:
        """Assign talent tier and return interpolated distributions.

        Returns None if required grades are missing for the position.
        """
        grade_config = self._config.position_grades.get(position)
        if grade_config is None:
            return None

        primary_val = pff_grades.get(grade_config.primary)
        secondary_val = pff_grades.get(grade_config.secondary)
        if primary_val is None:
            return None

        tier = self._assign_tier(primary_val, position)

        # Compute primary percentile (overall, not within tier)
        all_boundaries = self._boundaries[position]
        # Approximate percentile from boundaries
        if tier == 1:
            primary_pct = 0.85 + 0.15 * min((primary_val - all_boundaries[0]) /
                max(all_boundaries[0] * 0.2, 1.0), 1.0)
        elif tier == 5:
            primary_pct = max(0.0, all_boundaries[-1] - primary_val) / max(all_boundaries[-1], 1.0)
            primary_pct = 0.20 * (1.0 - min(primary_pct, 1.0))
        else:
            cutoff_high = self._config.cutoffs[tier - 2]
            cutoff_low = self._config.cutoffs[tier - 1]
            range_size = cutoff_high - cutoff_low
            position_in_tier = (primary_val - all_boundaries[tier - 1]) / max(
                all_boundaries[tier - 2] - all_boundaries[tier - 1], 1.0
            )
            primary_pct = cutoff_low + position_in_tier * range_size

        # Secondary percentile within tier
        if secondary_val is not None:
            secondary_pct = self._within_tier_percentile(secondary_val, position, tier)
        else:
            secondary_pct = 0.5  # default to tier median

        dists = self._interpolate_scalars(self._pools[position][tier], secondary_pct)
        assignment = TierAssignment(
            tier=tier,
            primary_percentile=primary_pct,
            secondary_percentile=secondary_pct,
            reliability=0.0,  # filled in by blend step
        )
        return assignment, dists
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_pff/test_tier_engine.py::TestWithinTierPercentile tests/test_data/test_pff/test_tier_engine.py::TestInterpolateScalars tests/test_data/test_pff/test_tier_engine.py::TestSelectDistributions -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/pff/tier_engine.py tests/test_data/test_pff/test_tier_engine.py
git commit -m "feat(pff): add distribution selection with tier interpolation"
```

---

### Task 4: Reliability Scoring

**Files:**
- Modify: `src/fantasy_sim/data/pff/tier_engine.py`
- Test: `tests/test_data/test_pff/test_tier_engine.py`

- [ ] **Step 1: Write reliability tests**

Append to test file:

```python
# ========== Task 4: Reliability ==========


class TestReliability:
    def test_established_player_capped(self, tier_config):
        """3-year stable player hits reliability cap (0.85)."""
        engine = TierEngine(tier_config, pff_loader=None)
        r = engine.compute_reliability(
            games_played=48, changed_teams=False, weekly_shares=np.full(48, 0.20),
        )
        assert r == pytest.approx(0.85)

    def test_new_team_penalty(self, tier_config):
        """Team change halves the sample factor."""
        engine = TierEngine(tier_config, pff_loader=None)
        r = engine.compute_reliability(
            games_played=17, changed_teams=True, weekly_shares=np.full(17, 0.20),
        )
        # sample=17/32=0.53, team=0.5, cv~0 -> raw=0.53*0.5*1.0=0.265
        assert 0.20 <= r <= 0.30

    def test_rookie_floor(self, tier_config):
        """Zero games -> floor reliability (0.15)."""
        engine = TierEngine(tier_config, pff_loader=None)
        r = engine.compute_reliability(
            games_played=0, changed_teams=False, weekly_shares=None,
        )
        assert r == pytest.approx(0.15)

    def test_volatile_shares_penalized(self, tier_config):
        """High week-to-week share variance reduces reliability."""
        engine = TierEngine(tier_config, pff_loader=None)
        stable = engine.compute_reliability(
            games_played=17, changed_teams=False,
            weekly_shares=np.full(17, 0.20),
        )
        volatile = engine.compute_reliability(
            games_played=17, changed_teams=False,
            weekly_shares=np.array([0.05, 0.30, 0.10, 0.35, 0.05, 0.30,
                                    0.10, 0.35, 0.05, 0.30, 0.10, 0.35,
                                    0.05, 0.30, 0.10, 0.35, 0.05]),
        )
        assert volatile < stable

    def test_too_few_weeks_no_variance_penalty(self, tier_config):
        """Fewer than 4 weeks -> variance penalty is skipped."""
        engine = TierEngine(tier_config, pff_loader=None)
        r = engine.compute_reliability(
            games_played=3, changed_teams=False,
            weekly_shares=np.array([0.05, 0.30, 0.50]),  # wild but <4 weeks
        )
        # sample=3/32=0.09, no variance penalty -> raw=0.09, clamped to floor
        assert r == pytest.approx(0.15)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_pff/test_tier_engine.py::TestReliability -v`
Expected: AttributeError — `compute_reliability` doesn't exist.

- [ ] **Step 3: Implement compute_reliability**

Add to `TierEngine` class:

```python
    def compute_reliability(
        self,
        games_played: int,
        changed_teams: bool,
        weekly_shares: np.ndarray | None,
    ) -> float:
        """Compute PBP reliability score.

        Returns PBP weight in [floor, cap]. Tier weight = 1 - reliability.

        Factors:
            1. Sample size: games_played / max_games (capped at 1.0)
            2. Team change: penalty multiplier if player changed teams
            3. Share variance: coefficient of variation of weekly shares
        """
        cfg = self._config

        # Factor 1: sample size
        sample = min(games_played / cfg.reliability_max_games, 1.0)

        # Factor 2: team change
        team = cfg.reliability_team_change_penalty if changed_teams else 1.0

        # Factor 3: share variance (needs >= 4 weeks)
        variance_penalty = 0.0
        if weekly_shares is not None and len(weekly_shares) >= 4:
            mean = np.mean(weekly_shares)
            if mean > 0.01:
                cv = float(np.std(weekly_shares) / mean)
                variance_penalty = min(cv, 1.0)

        raw = sample * team * (1.0 - variance_penalty * cfg.reliability_variance_weight)
        return float(np.clip(raw, cfg.reliability_floor, cfg.reliability_cap))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_pff/test_tier_engine.py::TestReliability -v`
Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/pff/tier_engine.py tests/test_data/test_pff/test_tier_engine.py
git commit -m "feat(pff): add PBP reliability scoring"
```

---

### Task 5: Player Blending

**Files:**
- Modify: `src/fantasy_sim/data/pff/tier_engine.py`
- Test: `tests/test_data/test_pff/test_tier_engine.py`

- [ ] **Step 1: Write blending tests**

Append to test file:

```python
from fantasy_sim.models.player import PlayerModel, PlayerUsage, PlayerOutcomes


# ========== Task 5: Blending ==========


def _make_player(
    player_id="test_wr1", position="WR",
    target_share=0.25, carry_share=0.0, catch_rate=0.68,
    air_yards_share=0.20, fumble_rate=0.01, scramble_rate=0.0,
    receiving_yards=None, rushing_yards=None,
):
    return PlayerModel(
        player_id=player_id,
        name="Test WR",
        position=position,
        team="KC",
        usage=PlayerUsage(
            target_share=target_share,
            carry_share=carry_share,
            air_yards_share=air_yards_share,
            scramble_rate=scramble_rate,
        ),
        outcomes=PlayerOutcomes(
            catch_rate=catch_rate,
            fumble_rate=fumble_rate,
            receiving_yards_dist=receiving_yards if receiving_yards is not None else np.array([8, 10, 12, 15, 20]),
            rushing_yards_dist=rushing_yards,
        ),
        games_played=17,
    )


class TestBlendPlayer:
    def test_high_reliability_favors_pbp(self, tier_config):
        """At 0.85 reliability, scalars are 85% PBP + 15% tier."""
        engine = TierEngine(tier_config, pff_loader=None)
        player = _make_player(catch_rate=0.70)
        tier_dists = TierDistributions(
            target_share=0.15, carry_share=0.0, catch_rate=0.60,
            air_yards_share=0.10, fumble_rate=0.015, scramble_rate=0.0,
            receiving_yards_dist=np.array([5, 8, 10, 12, 15]),
            rushing_yards_dist=None,
        )
        rng = np.random.default_rng(42)
        engine._blend_player(player, tier_dists, reliability=0.85, rng=rng)
        # 0.85 * 0.70 + 0.15 * 0.60 = 0.595 + 0.090 = 0.685
        assert player.outcomes.catch_rate == pytest.approx(0.685)

    def test_low_reliability_favors_tier(self, tier_config):
        """At 0.25 reliability, scalars are 25% PBP + 75% tier."""
        engine = TierEngine(tier_config, pff_loader=None)
        player = _make_player(target_share=0.30)
        tier_dists = TierDistributions(
            target_share=0.14, carry_share=0.0, catch_rate=0.65,
            air_yards_share=0.12, fumble_rate=0.015, scramble_rate=0.0,
            receiving_yards_dist=np.array([5, 8, 10, 12, 15]),
            rushing_yards_dist=None,
        )
        rng = np.random.default_rng(42)
        engine._blend_player(player, tier_dists, reliability=0.25, rng=rng)
        # 0.25 * 0.30 + 0.75 * 0.14 = 0.075 + 0.105 = 0.18
        assert player.usage.target_share == pytest.approx(0.18)

    def test_yards_blended_by_concatenation(self, tier_config):
        """Yards distributions use proportional resampling."""
        engine = TierEngine(tier_config, pff_loader=None)
        pbp_yards = np.full(100, 15.0)  # personal PBP: all 15-yard catches
        tier_yards = np.full(100, 8.0)  # tier pool: all 8-yard catches
        player = _make_player(receiving_yards=pbp_yards)
        tier_dists = TierDistributions(
            target_share=0.15, carry_share=0.0, catch_rate=0.65,
            air_yards_share=0.12, fumble_rate=0.015, scramble_rate=0.0,
            receiving_yards_dist=tier_yards,
            rushing_yards_dist=None,
        )
        rng = np.random.default_rng(42)
        engine._blend_player(player, tier_dists, reliability=0.60, rng=rng)
        # Blended pool should be 500 samples, ~60% from PBP (15s), ~40% from tier (8s)
        blended = player.outcomes.receiving_yards_dist
        assert len(blended) == tier_config.blend_pool_size
        mean = np.mean(blended)
        # Expected: 0.6*15 + 0.4*8 = 9.0 + 3.2 = 12.2 (approximately)
        assert 11.0 <= mean <= 13.5

    def test_no_pbp_yards_uses_tier_only(self, tier_config):
        """Rookie with no yards dist gets 100% tier pool."""
        engine = TierEngine(tier_config, pff_loader=None)
        player = _make_player(receiving_yards=None)
        tier_yards = np.array([5, 8, 10, 12, 15])
        tier_dists = TierDistributions(
            target_share=0.15, carry_share=0.0, catch_rate=0.65,
            air_yards_share=0.12, fumble_rate=0.015, scramble_rate=0.0,
            receiving_yards_dist=tier_yards,
            rushing_yards_dist=None,
        )
        rng = np.random.default_rng(42)
        engine._blend_player(player, tier_dists, reliability=0.15, rng=rng)
        assert player.outcomes.receiving_yards_dist is not None
        assert len(player.outcomes.receiving_yards_dist) > 0

    def test_red_zone_fields_untouched(self, tier_config):
        """RZ shares and catch rate are not modified by blending."""
        engine = TierEngine(tier_config, pff_loader=None)
        player = _make_player()
        player.usage.red_zone_target_share = 0.30
        player.outcomes.red_zone_catch_rate = 0.62
        tier_dists = TierDistributions(
            target_share=0.15, carry_share=0.0, catch_rate=0.60,
            air_yards_share=0.10, fumble_rate=0.015, scramble_rate=0.0,
            receiving_yards_dist=np.array([5, 10, 15]),
            rushing_yards_dist=None,
        )
        rng = np.random.default_rng(42)
        engine._blend_player(player, tier_dists, reliability=0.50, rng=rng)
        assert player.usage.red_zone_target_share == 0.30
        assert player.outcomes.red_zone_catch_rate == 0.62
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_pff/test_tier_engine.py::TestBlendPlayer -v`
Expected: AttributeError — `_blend_player` doesn't exist.

- [ ] **Step 3: Implement _blend_player**

Add to `TierEngine` class:

```python
    def _blend_player(
        self,
        player: 'PlayerModel',
        tier_dists: TierDistributions,
        reliability: float,
        rng: np.random.Generator,
    ) -> None:
        """Blend tier distributions into a PlayerModel in place.

        Scalars: weighted average (reliability * PBP + tier_weight * tier).
        Yards: concatenation with proportional resampling.
        RZ fields, scramble_yards_dist, pass_fumble_rate: untouched.
        """
        tier_weight = 1.0 - reliability
        pool_size = self._config.blend_pool_size

        # --- Scalar blending ---
        player.usage.target_share = (
            reliability * player.usage.target_share + tier_weight * tier_dists.target_share
        )
        player.usage.carry_share = (
            reliability * player.usage.carry_share + tier_weight * tier_dists.carry_share
        )
        player.usage.air_yards_share = (
            reliability * player.usage.air_yards_share + tier_weight * tier_dists.air_yards_share
        )
        player.usage.scramble_rate = (
            reliability * player.usage.scramble_rate + tier_weight * tier_dists.scramble_rate
        )
        player.outcomes.catch_rate = (
            reliability * player.outcomes.catch_rate + tier_weight * tier_dists.catch_rate
        )
        player.outcomes.fumble_rate = (
            reliability * player.outcomes.fumble_rate + tier_weight * tier_dists.fumble_rate
        )

        # --- Yards blending: proportional resampling ---
        def _blend_yards(
            personal: np.ndarray | None, tier_pool: np.ndarray | None,
        ) -> np.ndarray | None:
            if tier_pool is None:
                return personal
            if personal is None or len(personal) == 0:
                return tier_pool
            n_pbp = max(1, int(reliability * pool_size))
            n_tier = pool_size - n_pbp
            pbp_sample = rng.choice(personal, size=n_pbp, replace=True)
            tier_sample = rng.choice(tier_pool, size=n_tier, replace=True)
            return np.concatenate([pbp_sample, tier_sample])

        player.outcomes.receiving_yards_dist = _blend_yards(
            player.outcomes.receiving_yards_dist, tier_dists.receiving_yards_dist,
        )
        player.outcomes.rushing_yards_dist = _blend_yards(
            player.outcomes.rushing_yards_dist, tier_dists.rushing_yards_dist,
        )
```

Add the `PlayerModel` import at the top of `tier_engine.py` (use `TYPE_CHECKING` to avoid circular imports):

```python
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fantasy_sim.models.player import PlayerModel, TeamRoster
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_pff/test_tier_engine.py::TestBlendPlayer -v`
Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/pff/tier_engine.py tests/test_data/test_pff/test_tier_engine.py
git commit -m "feat(pff): add player blending (scalars + yards concatenation)"
```

---

### Task 6: Tier Pool Building

**Files:**
- Modify: `src/fantasy_sim/data/pff/tier_engine.py`
- Test: `tests/test_data/test_pff/test_tier_engine.py`

This is the most complex task. The pool builder needs PFF grades + PBP data cross-referenced per-season.

- [ ] **Step 1: Write pool building tests**

Append to test file:

```python
import polars as pl
from fantasy_sim.data.pff.loader import PffLoader


# ========== Task 6: Pool Building ==========


def _write_pff_parquet(pff_dir, facet, season, rows):
    """Write a PFF facet parquet file with given rows (list of dicts)."""
    if not rows:
        return
    df = pl.DataFrame(rows)
    path = pff_dir / f"{facet}_{season}.parquet"
    df.write_parquet(path)


@pytest.fixture
def pff_dir(tmp_path):
    d = tmp_path / "pff" / "processed" / "nfl"
    d.mkdir(parents=True)
    return d


@pytest.fixture
def loader(pff_dir):
    return PffLoader(pff_dir)


def _mock_wr_pff_data(pff_dir, season):
    """Write receiving_summary with 10 WRs spanning tiers 1-5."""
    rows = []
    grades = [92, 88, 78, 74, 62, 58, 52, 42, 36, 22]
    yprrs = [2.8, 2.4, 2.0, 1.8, 1.6, 1.4, 1.3, 1.1, 0.9, 0.7]
    for i, (g, y) in enumerate(zip(grades, yprrs)):
        rows.append({
            "player_id": 1000 + i,
            "player": f"WR{i}",
            "team": "KC" if i < 5 else "BUF",
            "position": "WR",
            "season": season,
            "week": 1,
            "grades_pass_route": float(g),
            "yprr": float(y),
            "targets": 80 + i * 5,
            "receptions": 50 + i * 3,
            "yards": 600 + i * 50,
            "touchdowns": 5,
            "drop_rate": 0.05,
            "contested_catch_rate": 0.50,
            "avg_depth_of_target": 10.0,
        })
    _write_pff_parquet(pff_dir, "receiving_summary", season, rows)
    return rows


def _mock_pbp_data(n_players=10, season=2023):
    """Create a minimal PBP DataFrame for pool building.

    Returns a polars DataFrame with columns matching what _aggregate_pbp_per_season needs.
    """
    rows = []
    for i in range(n_players):
        pid = f"nfl_wr_{i}"
        team = "KC" if i < 5 else "BUF"
        # Each player gets ~80 targets
        for play_idx in range(80):
            is_complete = play_idx % 5 != 0  # ~80% completion
            yards = float(np.random.default_rng(i * 100 + play_idx).integers(2, 30)) if is_complete else 0.0
            rows.append({
                "season": season,
                "week": (play_idx % 17) + 1,
                "game_id": f"{season}_{play_idx // 10}",
                "play_type": "pass",
                "passer_player_id": f"nfl_qb_{team}",
                "receiver_player_id": pid if is_complete else None,
                "passing_yards": yards if is_complete else 0.0,
                "yards_gained": yards if is_complete else 0.0,
                "complete_pass": 1 if is_complete else 0,
                "posteam": team,
                "air_yards": 10.0,
                "yardline_100": 50,
                "rusher_player_id": None,
                "rushing_yards": None,
                "interception": 0,
                "fumble_lost": 0,
                "sack": 0,
                "qb_scramble": 0,
            })
    return pl.DataFrame(rows)


class TestPoolBuilding:
    def test_build_pools_creates_5_tiers(self, pff_dir, loader, tier_config):
        """Pool building produces tiers 1-5 for each position."""
        _mock_wr_pff_data(pff_dir, 2023)
        _mock_wr_pff_data(pff_dir, 2024)
        crosswalk = {1000 + i: f"nfl_wr_{i}" for i in range(10)}
        pbp = _mock_pbp_data(n_players=10, season=2023)
        pbp2 = _mock_pbp_data(n_players=10, season=2024)
        pbp_all = pl.concat([pbp, pbp2])

        engine = TierEngine(tier_config, pff_loader=loader)
        engine._build_tier_pools(
            pbp=pbp_all,
            training_seasons=[2023, 2024],
            crosswalk=crosswalk,
        )
        assert "WR" in engine._pools
        # With 10 players * 2 seasons = 20 player-seasons, some tiers may merge
        # but at least some tiers should exist
        assert len(engine._pools["WR"]) >= 3

    def test_boundaries_computed(self, pff_dir, loader, tier_config):
        """Percentile boundaries are computed for each position."""
        _mock_wr_pff_data(pff_dir, 2023)
        crosswalk = {1000 + i: f"nfl_wr_{i}" for i in range(10)}
        pbp = _mock_pbp_data(n_players=10, season=2023)

        engine = TierEngine(tier_config, pff_loader=loader)
        engine._build_tier_pools(
            pbp=pbp, training_seasons=[2023], crosswalk=crosswalk,
        )
        assert "WR" in engine._boundaries
        bounds = engine._boundaries["WR"]
        assert len(bounds) == 4
        # Boundaries should be descending
        assert bounds[0] > bounds[1] > bounds[2] > bounds[3]

    def test_pool_entry_has_yards_array(self, pff_dir, loader, tier_config):
        """Each tier pool entry includes a receiving_yards_dist array."""
        _mock_wr_pff_data(pff_dir, 2023)
        crosswalk = {1000 + i: f"nfl_wr_{i}" for i in range(10)}
        pbp = _mock_pbp_data(n_players=10, season=2023)

        engine = TierEngine(tier_config, pff_loader=loader)
        engine._build_tier_pools(
            pbp=pbp, training_seasons=[2023], crosswalk=crosswalk,
        )
        # Check at least one tier has yards
        for tier, pool in engine._pools["WR"].items():
            if pool.n_player_seasons > 0:
                assert pool.receiving_yards_dist is not None
                assert len(pool.receiving_yards_dist) > 0
                break

    def test_thin_tier_merged(self, pff_dir, loader):
        """Tiers with < MIN_TIER_POOL_SIZE player-seasons merge with neighbor."""
        # With only 5 players in 1 season, each tier has ~1 player -> all thin
        _mock_wr_pff_data(pff_dir, 2023)
        crosswalk = {1000 + i: f"nfl_wr_{i}" for i in range(5)}
        pbp = _mock_pbp_data(n_players=5, season=2023)

        config = TierConfig(enabled=True)
        engine = TierEngine(config, pff_loader=loader)
        engine._build_tier_pools(
            pbp=pbp, training_seasons=[2023], crosswalk=crosswalk,
        )
        # All thin tiers should be merged — fewer than 5 tiers
        assert len(engine._pools.get("WR", {})) < 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_pff/test_tier_engine.py::TestPoolBuilding -v`
Expected: AttributeError — `_build_tier_pools` doesn't exist.

- [ ] **Step 3: Implement _aggregate_pbp_per_season**

Add to `TierEngine` class. This method extracts per-player stats from PBP data for a single season:

```python
    @staticmethod
    def _aggregate_pbp_per_season(
        pbp: 'pl.DataFrame', season: int,
    ) -> dict[str, dict]:
        """Aggregate PBP data for one season into per-player stat dicts.

        Returns dict[player_id -> {targets, catches, yards_list, carries,
        rushing_yards_list, team, games, weekly_target_counts, weekly_team_targets}]
        """
        import polars as pl

        season_pbp = pbp.filter(pl.col("season") == season)
        if season_pbp.is_empty():
            return {}

        stats: dict[str, dict] = {}

        # --- Receiving ---
        passes = season_pbp.filter(pl.col("play_type") == "pass")
        if not passes.is_empty():
            # Team-level pass attempts per week (for share computation)
            team_targets_weekly: dict[str, dict[int, int]] = {}
            for row in passes.select(["posteam", "week"]).iter_rows(named=True):
                team = row["posteam"]
                week = row["week"]
                team_targets_weekly.setdefault(team, {})
                team_targets_weekly[team][week] = team_targets_weekly[team].get(week, 0) + 1

            # Team total targets
            team_total_targets: dict[str, int] = {}
            team_total_air_yards: dict[str, float] = {}
            for row in passes.select(["posteam", "air_yards"]).iter_rows(named=True):
                t = row["posteam"]
                team_total_targets[t] = team_total_targets.get(t, 0) + 1
                ay = row["air_yards"] if row["air_yards"] is not None else 0.0
                team_total_air_yards[t] = team_total_air_yards.get(t, 0.0) + ay

            completions = passes.filter(pl.col("complete_pass") == 1)
            for row in completions.iter_rows(named=True):
                rid = row.get("receiver_player_id")
                if rid is None:
                    continue
                if rid not in stats:
                    stats[rid] = {
                        "targets": 0, "catches": 0, "yards_list": [],
                        "carries": 0, "rushing_yards_list": [],
                        "team": row["posteam"], "games": set(),
                        "air_yards": 0.0,
                        "weekly_targets": {},
                    }
                s = stats[rid]
                s["catches"] += 1
                yd = row.get("passing_yards") or row.get("yards_gained") or 0.0
                s["yards_list"].append(float(yd))
                s["games"].add(row.get("game_id", ""))
                ay = row.get("air_yards") or 0.0
                s["air_yards"] += float(ay)

            # Count targets (including incompletions)
            for row in passes.iter_rows(named=True):
                rid = row.get("receiver_player_id")
                if rid is None:
                    # Incomplete without receiver_player_id — can't attribute
                    continue
                if rid not in stats:
                    stats[rid] = {
                        "targets": 0, "catches": 0, "yards_list": [],
                        "carries": 0, "rushing_yards_list": [],
                        "team": row["posteam"], "games": set(),
                        "air_yards": 0.0,
                        "weekly_targets": {},
                    }
                stats[rid]["targets"] += 1
                w = row["week"]
                stats[rid]["weekly_targets"][w] = stats[rid]["weekly_targets"].get(w, 0) + 1

            # Compute shares
            for pid, s in stats.items():
                team = s["team"]
                total = team_total_targets.get(team, 1)
                s["target_share"] = s["targets"] / max(total, 1)
                total_ay = team_total_air_yards.get(team, 1.0)
                s["air_yards_share"] = s["air_yards"] / max(total_ay, 1.0)
                s["catch_rate"] = s["catches"] / max(s["targets"], 1)
                # Weekly target share for variance computation
                weekly_shares = []
                for w, cnt in s["weekly_targets"].items():
                    team_wk = team_targets_weekly.get(team, {}).get(w, 1)
                    weekly_shares.append(cnt / max(team_wk, 1))
                s["weekly_share_values"] = np.array(weekly_shares) if weekly_shares else None

        # --- Rushing ---
        rushes = season_pbp.filter(
            (pl.col("play_type") == "run")
            & (pl.col("rusher_player_id").is_not_null())
        )
        if not rushes.is_empty():
            team_rush_totals: dict[str, int] = {}
            for row in rushes.iter_rows(named=True):
                t = row["posteam"]
                team_rush_totals[t] = team_rush_totals.get(t, 0) + 1

            for row in rushes.iter_rows(named=True):
                rid = row["rusher_player_id"]
                if rid not in stats:
                    stats[rid] = {
                        "targets": 0, "catches": 0, "yards_list": [],
                        "carries": 0, "rushing_yards_list": [],
                        "team": row["posteam"], "games": set(),
                        "air_yards": 0.0,
                        "weekly_targets": {},
                    }
                s = stats[rid]
                s["carries"] += 1
                yd = row.get("rushing_yards") or row.get("yards_gained") or 0.0
                s["rushing_yards_list"].append(float(yd))
                s["games"].add(row.get("game_id", ""))
                team = s["team"]
                total = team_rush_totals.get(team, 1)
                s["carry_share"] = s["carries"] / max(total, 1)

        # Finalize
        for pid, s in stats.items():
            s["n_games"] = len(s["games"])
            s.setdefault("target_share", 0.0)
            s.setdefault("carry_share", 0.0)
            s.setdefault("catch_rate", 0.0)
            s.setdefault("air_yards_share", 0.0)
            s.setdefault("weekly_share_values", None)

        return stats
```

- [ ] **Step 4: Implement _load_season_grades**

Add to `TierEngine` class:

```python
    def _load_season_grades(
        self, season: int, position: str,
    ) -> dict[int, dict[str, float]]:
        """Load PFF grades for a position from a single season.

        Returns dict[pff_player_id -> {grade_name: season_average_value}].
        """
        grade_config = self._config.position_grades.get(position)
        if grade_config is None:
            return {}

        # Determine which PFF facet to load
        facet_map = {
            "QB": "passing_summary",
            "RB": "rushing_summary",
            "WR": "receiving_summary",
            "TE": "receiving_summary",
        }
        facet = facet_map.get(position)
        if facet is None:
            return {}

        df = self._pff_loader.load_facet(facet, [season])
        if df.is_empty():
            return {}

        # Filter to position (PFF data may have multiple positions in one facet)
        if "position" in df.columns:
            df = df.filter(pl.col("position") == position)

        # Average grades across weeks/games for each player
        grade_cols = [grade_config.primary, grade_config.secondary]
        available_cols = [c for c in grade_cols if c in df.columns]
        if not available_cols:
            logger.warning(
                "PFF facet %s missing grade columns %s for %s",
                facet, grade_cols, position,
            )
            return {}

        agg_exprs = [pl.col(c).mean().alias(c) for c in available_cols]
        grouped = df.group_by("player_id").agg(agg_exprs)

        result = {}
        for row in grouped.iter_rows(named=True):
            pid = row["player_id"]
            grades = {c: row[c] for c in available_cols if row[c] is not None}
            if grades:
                result[pid] = grades
        return result
```

Add `import polars as pl` at the top of `tier_engine.py` (not just inside the method).

- [ ] **Step 5: Implement _build_tier_pools**

Add to `TierEngine` class:

```python
    def _build_tier_pools(
        self,
        pbp: 'pl.DataFrame',
        training_seasons: list[int],
        crosswalk: dict[int, str],
    ) -> None:
        """Build tier distribution pools from PFF grades + PBP outcomes.

        Sets self._pools and self._boundaries. Cached by training_seasons.
        """
        import polars as pl

        self._pools = {}
        self._boundaries = {}
        self._weekly_shares = {}

        for position in self._config.position_grades:
            grade_config = self._config.position_grades[position]
            primary_key = grade_config.primary

            # Collect (pff_player_id, season, grades, pbp_stats) tuples
            player_seasons = []

            for season in training_seasons:
                pff_grades = self._load_season_grades(season, position)
                pbp_stats = self._aggregate_pbp_per_season(pbp, season)

                for pff_id, grades in pff_grades.items():
                    nfl_id = crosswalk.get(pff_id)
                    if nfl_id is None or nfl_id not in pbp_stats:
                        continue
                    if primary_key not in grades:
                        continue

                    ps = pbp_stats[nfl_id]
                    # Skip players with very few plays
                    if ps["targets"] + ps["carries"] < 10:
                        continue

                    player_seasons.append({
                        "pff_id": pff_id,
                        "nfl_id": nfl_id,
                        "season": season,
                        "grades": grades,
                        "pbp": ps,
                    })

            if not player_seasons:
                logger.warning("No player-seasons for %s tier pools", position)
                continue

            # Compute percentile boundaries on primary grade
            primary_values = np.array([
                ps["grades"][primary_key] for ps in player_seasons
            ])
            cutoffs = self._config.cutoffs  # [0.85, 0.65, 0.40, 0.20]
            boundaries = [
                float(np.percentile(primary_values, pct * 100))
                for pct in cutoffs
            ]
            self._boundaries[position] = boundaries

            # Assign each player-season to a tier
            tier_buckets: dict[int, list] = {t: [] for t in range(1, 6)}
            for ps in player_seasons:
                grade_val = ps["grades"][primary_key]
                tier = self._assign_tier(grade_val, position)
                tier_buckets[tier].append(ps)

            # Merge thin tiers
            tier_buckets = self._merge_thin_tiers(tier_buckets)

            # Build pool entries
            pos_pools = {}
            for tier, members in tier_buckets.items():
                if not members:
                    continue
                pos_pools[tier] = self._build_pool_entry(
                    members, grade_config.secondary,
                )
            self._pools[position] = pos_pools

        self._cache_key = tuple(training_seasons)
        logger.info(
            "Built tier pools: %s",
            {pos: {t: p.n_player_seasons for t, p in tiers.items()}
             for pos, tiers in self._pools.items()},
        )

    @staticmethod
    def _merge_thin_tiers(
        tier_buckets: dict[int, list],
    ) -> dict[int, list]:
        """Merge tiers with < MIN_TIER_POOL_SIZE into adjacent tiers."""
        for tier in [1, 5, 2, 4]:  # extremes first, then inner
            if len(tier_buckets.get(tier, [])) < MIN_TIER_POOL_SIZE:
                neighbor = tier + 1 if tier < 3 else tier - 1
                if neighbor in tier_buckets:
                    tier_buckets[neighbor].extend(tier_buckets.pop(tier, []))
                    logger.info("Merged thin tier %d into tier %d", tier, neighbor)
        return tier_buckets

    @staticmethod
    def _build_pool_entry(
        members: list[dict], secondary_key: str,
    ) -> _TierPoolEntry:
        """Build a _TierPoolEntry from a list of player-season dicts."""
        target_shares = [m["pbp"].get("target_share", 0.0) for m in members]
        carry_shares = [m["pbp"].get("carry_share", 0.0) for m in members]
        catch_rates = [m["pbp"].get("catch_rate", 0.0) for m in members]
        air_yards_shares = [m["pbp"].get("air_yards_share", 0.0) for m in members]
        fumble_rates = [m["pbp"].get("fumble_rate", 0.015) for m in members]

        def pct_tuple(vals):
            a = np.array(vals)
            return (
                float(np.percentile(a, 25)),
                float(np.median(a)),
                float(np.percentile(a, 75)),
            )

        # Pool all play-level yards
        all_recv_yards = []
        all_rush_yards = []
        secondary_grades = []
        for m in members:
            all_recv_yards.extend(m["pbp"].get("yards_list", []))
            all_rush_yards.extend(m["pbp"].get("rushing_yards_list", []))
            sec = m["grades"].get(secondary_key)
            if sec is not None:
                secondary_grades.append(sec)

        return _TierPoolEntry(
            target_share=pct_tuple(target_shares),
            carry_share=pct_tuple(carry_shares),
            catch_rate=pct_tuple(catch_rates),
            air_yards_share=pct_tuple(air_yards_shares),
            fumble_rate=pct_tuple(fumble_rates),
            scramble_rate=(0.0, 0.0, 0.0),  # only for QBs, filled separately
            receiving_yards_dist=np.array(all_recv_yards) if all_recv_yards else None,
            rushing_yards_dist=np.array(all_rush_yards) if all_rush_yards else None,
            secondary_grades=np.array(sorted(secondary_grades)) if secondary_grades else None,
            n_player_seasons=len(members),
        )

    def _ensure_pools(
        self,
        pbp: 'pl.DataFrame',
        training_seasons: list[int],
        crosswalk: dict[int, str],
    ) -> None:
        """Build pools if not cached for these training seasons."""
        key = tuple(training_seasons)
        if self._cache_key == key and self._pools is not None:
            return
        self._build_tier_pools(pbp, training_seasons, crosswalk)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_pff/test_tier_engine.py::TestPoolBuilding -v`
Expected: All 4 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add src/fantasy_sim/data/pff/tier_engine.py tests/test_data/test_pff/test_tier_engine.py
git commit -m "feat(pff): add tier pool building from PFF grades + PBP data"
```

---

### Task 7: apply_tiers & GameContextBuilder Integration

**Files:**
- Modify: `src/fantasy_sim/data/pff/tier_engine.py`
- Modify: `src/fantasy_sim/data/game_context.py`
- Test: `tests/test_data/test_pff/test_tier_engine.py`

- [ ] **Step 1: Write apply_tiers test**

Append to test file:

```python
# ========== Task 7: apply_tiers + Integration ==========


class TestApplyTiers:
    def test_apply_tiers_modifies_roster(self, pff_dir, loader):
        """apply_tiers modifies player models in a roster."""
        _mock_wr_pff_data(pff_dir, 2023)
        crosswalk = {1000 + i: f"nfl_wr_{i}" for i in range(10)}
        pbp = _mock_pbp_data(n_players=10, season=2023)

        from fantasy_sim.models.player import TeamRoster

        # Create a roster with 2 WRs (one elite PFF, one replacement)
        elite = _make_player(
            player_id="nfl_wr_0", target_share=0.10,  # underused in PBP
            catch_rate=0.55,
        )
        replacement = _make_player(
            player_id="nfl_wr_9", target_share=0.30,  # overused in PBP
            catch_rate=0.75,
        )
        roster = TeamRoster(team="KC", players=[elite, replacement])

        config = TierConfig(enabled=True)
        engine = TierEngine(config, pff_loader=loader)
        engine.apply_tiers(
            roster=roster,
            crosswalk=crosswalk,
            training_seasons=[2023],
            pbp=pbp,
        )
        # Elite WR should have target_share pulled UP from PBP's 0.10
        # Replacement WR should have target_share pulled DOWN from PBP's 0.30
        # (Exact values depend on tier pool, but direction should be correct)
        assert elite.usage.target_share > 0.10 or elite.usage.target_share == pytest.approx(0.10, abs=0.001)
        assert replacement.usage.target_share < 0.30 or replacement.usage.target_share == pytest.approx(0.30, abs=0.001)

    def test_apply_tiers_skips_missing_pff(self, pff_dir, loader):
        """Players not in crosswalk are unchanged."""
        _mock_wr_pff_data(pff_dir, 2023)
        crosswalk = {1000: "nfl_wr_0"}  # only one player mapped
        pbp = _mock_pbp_data(n_players=10, season=2023)

        from fantasy_sim.models.player import TeamRoster

        known = _make_player(player_id="nfl_wr_0", target_share=0.20)
        unknown = _make_player(player_id="nfl_wr_unknown", target_share=0.25)
        roster = TeamRoster(team="KC", players=[known, unknown])

        config = TierConfig(enabled=True)
        engine = TierEngine(config, pff_loader=loader)
        engine.apply_tiers(
            roster=roster, crosswalk=crosswalk,
            training_seasons=[2023], pbp=pbp,
        )
        # Unknown player should be untouched
        assert unknown.usage.target_share == 0.25
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_pff/test_tier_engine.py::TestApplyTiers -v`
Expected: AttributeError — `apply_tiers` doesn't exist.

- [ ] **Step 3: Implement apply_tiers**

Add to `TierEngine` class:

```python
    def apply_tiers(
        self,
        roster: 'TeamRoster',
        crosswalk: dict[int, str],
        training_seasons: list[int],
        pbp: 'pl.DataFrame | None' = None,
        nfl_roster: 'pl.DataFrame | None' = None,
        target_season: int | None = None,
    ) -> None:
        """Apply tier-based distribution adjustments to all players in a roster.

        Mutates player models in place. Players without PFF data are unchanged.
        """
        if pbp is None:
            logger.warning("No PBP data for tier pool building — skipping")
            return

        self._ensure_pools(pbp, training_seasons, crosswalk)
        if not self._pools:
            return

        # Reverse crosswalk: nfl_id -> pff_id
        nfl_to_pff = {nfl_id: pff_id for pff_id, nfl_id in crosswalk.items()}

        # Detect team changes for reliability scoring
        changed_teams_set = set()
        if nfl_roster is not None and target_season is not None:
            changed_teams_set = self._detect_team_changes(
                nfl_roster, training_seasons, target_season,
            )

        # Get per-season PBP for weekly share variance
        pbp_per_season = {}
        for season in training_seasons:
            pbp_per_season[season] = self._aggregate_pbp_per_season(pbp, season)

        rng = np.random.default_rng(42)

        for player in roster.players:
            pff_id = nfl_to_pff.get(player.player_id)
            if pff_id is None:
                continue

            position = player.position
            if position not in self._pools:
                continue

            # Load this player's PFF grades (latest season average)
            latest_season = max(training_seasons)
            grades = self._load_season_grades(latest_season, position).get(pff_id)
            if grades is None:
                # Try earlier seasons
                for s in sorted(training_seasons, reverse=True):
                    grades = self._load_season_grades(s, position).get(pff_id)
                    if grades:
                        break
            if grades is None:
                continue

            result = self.select_distributions(grades, position)
            if result is None:
                continue
            assignment, tier_dists = result

            # Compute reliability
            weekly_shares = None
            for s in sorted(training_seasons, reverse=True):
                ps = pbp_per_season.get(s, {}).get(player.player_id)
                if ps and ps.get("weekly_share_values") is not None:
                    weekly_shares = ps["weekly_share_values"]
                    break

            changed = player.player_id in changed_teams_set
            reliability = self.compute_reliability(
                player.games_played, changed, weekly_shares,
            )
            assignment.reliability = reliability

            self._blend_player(player, tier_dists, reliability, rng)
            logger.debug(
                "Tier %d (%s) for %s: reliability=%.2f, tier_weight=%.2f",
                assignment.tier, position, player.name,
                reliability, 1.0 - reliability,
            )

    @staticmethod
    def _detect_team_changes(
        nfl_roster: 'pl.DataFrame',
        training_seasons: list[int],
        target_season: int,
    ) -> set[str]:
        """Detect players who changed teams between training and target season."""
        import polars as pl

        changed = set()
        if "season" not in nfl_roster.columns or "gsis_id" not in nfl_roster.columns:
            return changed

        current = nfl_roster.filter(pl.col("season") == target_season)
        historical = nfl_roster.filter(pl.col("season").is_in(training_seasons))

        if current.is_empty() or historical.is_empty():
            return changed

        for row in current.select(["gsis_id", "team"]).iter_rows(named=True):
            pid = row["gsis_id"]
            current_team = row["team"]
            hist = historical.filter(pl.col("gsis_id") == pid)
            if not hist.is_empty():
                hist_teams = hist["team"].unique().to_list()
                if current_team not in hist_teams:
                    changed.add(pid)
        return changed
```

- [ ] **Step 4: Run apply_tiers tests**

Run: `uv run pytest tests/test_data/test_pff/test_tier_engine.py::TestApplyTiers -v`
Expected: All 2 tests PASS.

- [ ] **Step 5: Wire TierEngine into GameContextBuilder**

Modify `src/fantasy_sim/data/game_context.py`:

**In `__init__`**, add tier engine import and initialization after the talent stabilizer block (line 74):

```python
        self._tier_engine = None

        if self._pff_config.enabled and self._pff_config.tier_engine.enabled and self._pff_loader:
            from fantasy_sim.data.pff.tier_engine import TierEngine
            self._tier_engine = TierEngine(self._pff_config.tier_engine, self._pff_loader)
            logger.info("PFF tier engine enabled")
```

**In `build_game()`**, replace the talent stabilization block (lines 346-361) with:

```python
        # PFF tier engine (takes precedence over talent stabilizer)
        if self._tier_engine is not None:
            from fantasy_sim.data.player_builder import _normalize_roster_shares
            self._ensure_pff_crosswalk(training_seasons, target_season)
            roster_season = target_season or max(training_seasons)
            nfl_roster_df = self.loader.load_rosters([roster_season])
            # Get PBP for pool building
            pbp_df = self.loader.load_pbp(training_seasons)
            self._tier_engine.apply_tiers(
                home_roster, self._pff_crosswalk, training_seasons,
                pbp=pbp_df, nfl_roster=nfl_roster_df,
                target_season=roster_season,
            )
            self._tier_engine.apply_tiers(
                away_roster, self._pff_crosswalk, training_seasons,
                pbp=pbp_df, nfl_roster=nfl_roster_df,
                target_season=roster_season,
            )
            _normalize_roster_shares(home_roster)
            _normalize_roster_shares(away_roster)
        elif self._talent_stabilizer is not None:
            from fantasy_sim.data.player_builder import _normalize_roster_shares
            self._ensure_pff_crosswalk(training_seasons, target_season)
            roster_season = target_season or max(training_seasons)
            nfl_roster_df = self.loader.load_rosters([roster_season])
            self._talent_stabilizer.stabilize_roster(
                home_roster, self._pff_crosswalk, training_seasons,
                nfl_roster=nfl_roster_df, target_season=roster_season,
            )
            self._talent_stabilizer.stabilize_roster(
                away_roster, self._pff_crosswalk, training_seasons,
                nfl_roster=nfl_roster_df, target_season=roster_season,
            )
            _normalize_roster_shares(home_roster)
            _normalize_roster_shares(away_roster)
```

Also add `TierConfig` to the import from `models` if not already imported (it's used transitively via PffConfig).

- [ ] **Step 6: Run full test suite**

Run: `uv run pytest tests/ -x -q`
Expected: All tests pass. The tier engine is disabled by default (`enabled: false`), so existing behavior is unchanged.

- [ ] **Step 7: Commit**

```bash
git add src/fantasy_sim/data/pff/tier_engine.py src/fantasy_sim/data/game_context.py \
       tests/test_data/test_pff/test_tier_engine.py
git commit -m "feat(pff): add apply_tiers and wire into GameContextBuilder"
```

---

### Task 8: Validation Scripts

**Files:**
- Modify: `scripts/validate_pff_signal.py`
- Create: `scripts/validate_tier_spotcheck.py`

- [ ] **Step 1: Check validate_pff_signal.py for --mode argument structure**

Read `scripts/validate_pff_signal.py` to understand the existing `--mode` argument and A/B harness structure. The script already has `--mode talent`. We need to add `--mode tier`.

- [ ] **Step 2: Add --mode tier to A/B harness**

In `scripts/validate_pff_signal.py`, extend the `--mode` choices to include `"tier"`. In the run logic where the mode is used to toggle PFF config, add a branch for tier mode:

```python
# In the config setup section:
if args.mode == "tier":
    pff_config = PffConfig(
        enabled=True,
        tier_engine=TierConfig(enabled=True),
        talent=TalentConfig(enabled=False),
    )
elif args.mode == "talent":
    pff_config = PffConfig(
        enabled=True,
        talent=TalentConfig(enabled=True),
        tier_engine=TierConfig(enabled=False),
    )
```

Add the necessary imports at the top:

```python
from fantasy_sim.data.pff.models import TierConfig
```

- [ ] **Step 3: Create spot-check script**

Create `scripts/validate_tier_spotcheck.py`:

```python
#!/usr/bin/env python
"""Spot-check 10 players: compare projections with tier engine ON vs OFF.

Usage:
    uv run python scripts/validate_tier_spotcheck.py --sims 100
"""

import argparse
import sys
from pathlib import Path

import numpy as np

from fantasy_sim.config.loader import load_config, load_defaults
from fantasy_sim.data.game_context import GameContextBuilder
from fantasy_sim.data.pff.models import PffConfig, TalentConfig, TierConfig
from fantasy_sim.engine.monte_carlo import monte_carlo_sim
from fantasy_sim.scoring.engine import ScoringEngine
from fantasy_sim.scoring.projections import build_player_projections


# Volume-inflated players (expected to DROP)
VOLUME_INFLATED = [
    "tony_pollard",
    "jerry_jeudy",
    "rachaad_white",
    "jakobi_meyers",
    "raheem_mostert",
]

# Talent-deflated players (expected to RISE)
# Gibbs is the anchor; others identified from PFF-vs-PBP rank mismatch
TALENT_DEFLATED = [
    "jahmyr_gibbs",
    # TODO: Identify 4 more during implementation by scanning for
    # players with pff_tier <= 2 but pbp_projected_rank >= 15
]


def run_projections(pff_config, season, n_sims, scoring_config):
    """Run full-season projections and return {player_id: (rank, fpts_per_week)}."""
    ctx = GameContextBuilder(pff_config=pff_config)
    defaults = load_defaults()
    # Run week-by-week to get per-player projections
    # This is a simplified version — adapt to match the actual backtest flow
    all_results = []
    for week in range(1, 18):
        try:
            home_d, away_d, home_r, away_r = ctx.build_game(
                "KC", "BUF",  # placeholder — real script iterates all matchups
                training_seasons=[2022, 2023, 2024],
                target_season=season,
                week=week,
            )
        except Exception:
            continue
    # Placeholder for full implementation — the actual script will:
    # 1. Iterate all real matchups for the season
    # 2. Run monte_carlo_sim for each
    # 3. Build projections
    # 4. Return ranked results
    return {}


def main():
    parser = argparse.ArgumentParser(description="Tier engine spot-check")
    parser.add_argument("--season", type=int, default=2024)
    parser.add_argument("--sims", type=int, default=100)
    parser.add_argument("--scoring", default="half_ppr")
    args = parser.parse_args()

    defaults = load_defaults()
    scoring_config = defaults  # simplified

    print("Running baseline (tier engine OFF)...")
    baseline_config = PffConfig(
        enabled=True,
        talent=TalentConfig(enabled=True),
        tier_engine=TierConfig(enabled=False),
    )
    baseline = run_projections(baseline_config, args.season, args.sims, scoring_config)

    print("Running tier engine (tier engine ON)...")
    tier_config = PffConfig(
        enabled=True,
        talent=TalentConfig(enabled=False),
        tier_engine=TierConfig(enabled=True),
    )
    tier_results = run_projections(tier_config, args.season, args.sims, scoring_config)

    # Print comparison table
    print()
    print(f"{'Player':<20} {'PFF Tier':<10} {'Base Rank':<10} {'Base FPts':<10} "
          f"{'Tier Rank':<10} {'Tier FPts':<10} {'Δ Rank':<8} {'✓/✗'}")
    print("─" * 88)

    correct = 0
    total = 0
    for label, players, expected_dir in [
        ("VOLUME-INFLATED (should drop):", VOLUME_INFLATED, "down"),
        ("TALENT-DEFLATED (should rise):", TALENT_DEFLATED, "up"),
    ]:
        print(f"\n{label}")
        for pid in players:
            b = baseline.get(pid, (999, 0.0))
            t = tier_results.get(pid, (999, 0.0))
            delta = t[0] - b[0]
            if expected_dir == "down":
                ok = delta > 0  # rank number increases = dropped
            else:
                ok = delta < 0  # rank number decreases = rose
            correct += ok
            total += 1
            mark = "✓" if ok else "✗"
            print(f"  {pid:<18} {'T?':<10} {b[0]:<10} {b[1]:<10.1f} "
                  f"{t[0]:<10} {t[1]:<10.1f} {delta:>+6}    {mark}")

    print(f"\nResult: {correct}/{total} correct direction "
          f"{'→ PASS' if correct >= 8 else '→ FAIL'} (threshold: 8/10)")


if __name__ == "__main__":
    main()
```

Note: This script is a scaffold. During implementation, adapt `run_projections()` to use the actual backtest flow from `validation/backtester.py`. The structure and output format are final.

- [ ] **Step 4: Run the full test suite to confirm no regressions**

Run: `uv run pytest tests/ -x -q`
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/validate_pff_signal.py scripts/validate_tier_spotcheck.py \
       tests/test_data/test_pff/test_tier_engine.py
git commit -m "feat(pff): add tier engine A/B mode and spot-check script"
```

---

## Post-Implementation Checklist

After all 8 tasks are complete:

1. **Run full test suite**: `uv run pytest tests/ -v` — all tests pass
2. **Run A/B validation**: `uv run python scripts/validate_pff_signal.py --mode tier --sims 50 --label "tier-v1"`
3. **Run spot-check**: `uv run python scripts/validate_tier_spotcheck.py --sims 100`
4. **Compare against talent stabilizer**: `uv run python scripts/validate_pff_signal.py --show-ledger`
5. **Update CLAUDE.md** with tier engine documentation (new commands, architecture notes)
6. **Update docs/pff-future-improvements.md** to mark tier engine as complete

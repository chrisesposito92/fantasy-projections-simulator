# Phase 2 Role And Availability Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a hybrid Phase 2 layer where `availability` makes conservative pre-sim eligibility/share decisions from explicit signals and `role_trend` applies bounded post-sim weekly projection corrections across QB/RB/WR/TE with per-position config gates.

**Architecture:** Add two new config families, a shared weekly role-input loader keyed by nflverse `player_id`, a pre-sim `AvailabilityEngine` inserted between vegas and usage, and a post-sim `RoleTrendProjectionAdjuster` applied before ensemble. Keep hard availability decisions explicit-signal-only in v1, keep usage-only evidence soft-only, and wire the same typed configs and coverage reporting through CLI, validation, and backtester paths.

**Tech Stack:** Python 3.12+, polars, pathlib, dataclasses, nflreadpy, pytest

**Spec:** `docs/superpowers/specs/2026-04-11-phase-2-role-and-availability-engine-design.md`

---

## File Map

- `config/defaults.yaml`
  - add disabled-by-default `availability` and `role_trend` families with all four positions enabled in config lists
- `src/fantasy_sim/data/loader.py`
  - add cached `load_injuries()` support; keep `load_depth_charts()` as the shared depth source
- `src/fantasy_sim/data/availability/__init__.py`
  - package export surface
- `src/fantasy_sim/data/availability/models.py`
  - config dataclasses plus decision/evidence dataclasses used by the engine
- `src/fantasy_sim/data/availability/config.py`
  - YAML-to-dataclass loader for `availability`
- `src/fantasy_sim/data/availability/loader.py`
  - shared `WeeklyRoleInputLoader` that normalizes weekly player stats, rosters, injuries, depth charts, and snap percentages into one player-week table
- `src/fantasy_sim/data/availability/engine.py`
  - pre-sim explicit-signal-first availability mutations
- `src/fantasy_sim/data/role_trend/__init__.py`
  - package export surface
- `src/fantasy_sim/data/role_trend/models.py`
  - `role_trend` config dataclasses
- `src/fantasy_sim/data/role_trend/config.py`
  - YAML-to-dataclass loader for `role_trend`
- `src/fantasy_sim/data/game_context.py`
  - instantiate and apply `AvailabilityEngine` between vegas and usage
- `src/fantasy_sim/scoring/role_trend.py`
  - post-sim soft-only trend adjuster
- `src/fantasy_sim/scoring/projection_layers.py`
  - single helper that applies `role_trend` then `ensemble`
- `src/fantasy_sim/cli.py`
  - load typed configs, pass `availability_config` into `GameContextBuilder`, and reuse `projection_layers` for non-detail weekly outputs
- `src/fantasy_sim/validation/config.py`
  - include typed `availability_config` and `role_trend_config`
- `src/fantasy_sim/validation/parallel.py`
  - thread `availability_config` into single-arm builders and on-arm dual builders
- `src/fantasy_sim/validation/backtester.py`
  - apply role trend before ensemble
- `scripts/validate.py`
  - build typed configs and apply role trend before ensemble in both arms
- `src/fantasy_sim/validation/coverage.py`
  - add `availability`, `availability.injuries`, `availability.depth_charts`, `availability.usage_fallback`, and `role_trend`
- `tests/test_data/test_availability/`
  - config, loader, engine, and game-context integration tests
- `tests/test_data/test_role_trend/`
  - config tests
- `tests/test_scoring/test_role_trend.py`
  - trend adjuster and projection-layer order tests
- `tests/test_validation/`
  - config, coverage, and parallel threading tests
- `docs/accuracy-roadmap.md`
  - phase status and next priority
- `docs/accuracy-stack-audit.md`
  - defaults, runtime order, corrected cache notes, and remaining caveats

### Task 1: Add Phase 2 Config Families And Shared Loader Surface

**Files:**
- Create: `src/fantasy_sim/data/availability/__init__.py`
- Create: `src/fantasy_sim/data/availability/models.py`
- Create: `src/fantasy_sim/data/availability/config.py`
- Create: `src/fantasy_sim/data/role_trend/__init__.py`
- Create: `src/fantasy_sim/data/role_trend/models.py`
- Create: `src/fantasy_sim/data/role_trend/config.py`
- Modify: `config/defaults.yaml`
- Modify: `src/fantasy_sim/data/loader.py`
- Modify: `src/fantasy_sim/validation/config.py`
- Create: `tests/test_data/test_availability/test_config.py`
- Create: `tests/test_data/test_role_trend/test_config.py`
- Modify: `tests/test_validation/test_config.py`

- [ ] **Step 1: Write the failing config tests**

Create `tests/test_data/test_availability/test_config.py`:

```python
from fantasy_sim.data.availability.config import load_availability_config


def test_load_availability_config_defaults_disabled():
    cfg = load_availability_config({})

    assert cfg.enabled is False
    assert cfg.positions == ("QB", "RB", "WR", "TE")
    assert cfg.injuries.enabled is True
    assert cfg.depth_charts.enabled is True
    assert cfg.usage_fallback.enabled is True
    assert cfg.usage_fallback.min_factor == 0.85
    assert cfg.usage_fallback.qb_low_usage_factor == 0.92


def test_load_availability_config_reads_yaml_values():
    cfg = load_availability_config(
        {
            "availability": {
                "enabled": True,
                "positions": ["QB", "WR"],
                "injuries": {"enabled": True, "hard_out_statuses": ["Out", "Doubtful"]},
                "depth_charts": {"enabled": True, "starter_slots": {"QB": "QB1"}},
                "usage_fallback": {
                    "enabled": True,
                    "lookback_weeks": 3,
                    "min_factor": 0.90,
                    "qb_low_usage_factor": 0.95,
                },
            }
        }
    )

    assert cfg.enabled is True
    assert cfg.positions == ("QB", "WR")
    assert cfg.injuries.hard_out_statuses == ("Out", "Doubtful")
    assert cfg.depth_charts.starter_slots["QB"] == "QB1"
    assert cfg.usage_fallback.lookback_weeks == 3
    assert cfg.usage_fallback.min_factor == 0.90
```

Create `tests/test_data/test_role_trend/test_config.py`:

```python
from fantasy_sim.data.role_trend.config import load_role_trend_config


def test_load_role_trend_config_defaults_disabled():
    cfg = load_role_trend_config({})

    assert cfg.enabled is False
    assert cfg.positions == ("QB", "RB", "WR", "TE")
    assert cfg.window_weeks == 3
    assert cfg.factor_clamp == (0.90, 1.10)
    assert cfg.qb.sensitivity == 0.12
    assert cfg.wr.sensitivity == 0.10


def test_load_role_trend_config_reads_yaml_values():
    cfg = load_role_trend_config(
        {
            "role_trend": {
                "enabled": True,
                "positions": ["RB", "WR", "TE"],
                "window_weeks": 4,
                "factor_clamp": [0.92, 1.08],
                "rb": {"sensitivity": 0.08},
            }
        }
    )

    assert cfg.enabled is True
    assert cfg.positions == ("RB", "WR", "TE")
    assert cfg.window_weeks == 4
    assert cfg.factor_clamp == (0.92, 1.08)
    assert cfg.rb.sensitivity == 0.08
```

Add to `tests/test_validation/test_config.py`:

```python
    def test_defaults_keep_availability_and_role_trend_disabled(self):
        defaults = load_defaults()
        configs = build_engine_configs(defaults)

        assert configs["availability_config"] is None
        assert configs["role_trend_config"] is None
```

- [ ] **Step 2: Run the config tests to verify they fail**

Run: `uv run pytest tests/test_data/test_availability/test_config.py tests/test_data/test_role_trend/test_config.py tests/test_validation/test_config.py -v`

Expected: FAIL with `ModuleNotFoundError` for the new config packages and `KeyError` for the missing `availability_config` / `role_trend_config` entries.

- [ ] **Step 3: Implement the config families, defaults, and cached injuries loader**

Create `src/fantasy_sim/data/availability/__init__.py`:

```python
"""Availability intelligence layer."""

from fantasy_sim.data.availability.config import load_availability_config
from fantasy_sim.data.availability.models import AvailabilityConfig

__all__ = ["AvailabilityConfig", "load_availability_config"]
```

Create `src/fantasy_sim/data/availability/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class InjurySignalConfig:
    enabled: bool = True
    hard_out_statuses: tuple[str, ...] = ("Out", "Doubtful", "Suspended", "Injured Reserve")
    limited_statuses: tuple[str, ...] = ("Questionable",)
    limited_factor: float = 0.75


@dataclass
class DepthChartSignalConfig:
    enabled: bool = True
    starter_slots: dict[str, str] = field(
        default_factory=lambda: {"QB": "QB1", "RB": "RB1", "WR": "WR1", "TE": "TE1"}
    )


@dataclass
class UsageFallbackConfig:
    enabled: bool = True
    lookback_weeks: int = 3
    min_factor: float = 0.85
    qb_low_usage_factor: float = 0.92
    rb_low_usage_factor: float = 0.90
    wr_low_usage_factor: float = 0.92
    te_low_usage_factor: float = 0.92


@dataclass
class AvailabilityConfig:
    enabled: bool = False
    positions: tuple[str, ...] = ("QB", "RB", "WR", "TE")
    injuries: InjurySignalConfig = field(default_factory=InjurySignalConfig)
    depth_charts: DepthChartSignalConfig = field(default_factory=DepthChartSignalConfig)
    usage_fallback: UsageFallbackConfig = field(default_factory=UsageFallbackConfig)
```

Create `src/fantasy_sim/data/availability/config.py`:

```python
from __future__ import annotations

from fantasy_sim.data.availability.models import (
    AvailabilityConfig,
    DepthChartSignalConfig,
    InjurySignalConfig,
    UsageFallbackConfig,
)


def load_availability_config(defaults: dict) -> AvailabilityConfig:
    raw = defaults.get("availability")
    if not raw:
        return AvailabilityConfig(enabled=False)

    injury_raw = raw.get("injuries", {})
    depth_raw = raw.get("depth_charts", {})
    usage_raw = raw.get("usage_fallback", {})

    return AvailabilityConfig(
        enabled=raw.get("enabled", False),
        positions=tuple(raw.get("positions", ["QB", "RB", "WR", "TE"])),
        injuries=InjurySignalConfig(
            enabled=injury_raw.get("enabled", True),
            hard_out_statuses=tuple(
                injury_raw.get(
                    "hard_out_statuses",
                    ["Out", "Doubtful", "Suspended", "Injured Reserve"],
                )
            ),
            limited_statuses=tuple(injury_raw.get("limited_statuses", ["Questionable"])),
            limited_factor=injury_raw.get("limited_factor", 0.75),
        ),
        depth_charts=DepthChartSignalConfig(
            enabled=depth_raw.get("enabled", True),
            starter_slots=dict(
                depth_raw.get(
                    "starter_slots",
                    {"QB": "QB1", "RB": "RB1", "WR": "WR1", "TE": "TE1"},
                )
            ),
        ),
        usage_fallback=UsageFallbackConfig(
            enabled=usage_raw.get("enabled", True),
            lookback_weeks=usage_raw.get("lookback_weeks", 3),
            min_factor=usage_raw.get("min_factor", 0.85),
            qb_low_usage_factor=usage_raw.get("qb_low_usage_factor", 0.92),
            rb_low_usage_factor=usage_raw.get("rb_low_usage_factor", 0.90),
            wr_low_usage_factor=usage_raw.get("wr_low_usage_factor", 0.92),
            te_low_usage_factor=usage_raw.get("te_low_usage_factor", 0.92),
        ),
    )
```

Create `src/fantasy_sim/data/role_trend/__init__.py`:

```python
"""Same-season role trend configuration."""

from fantasy_sim.data.role_trend.config import load_role_trend_config
from fantasy_sim.data.role_trend.models import RoleTrendConfig

__all__ = ["RoleTrendConfig", "load_role_trend_config"]
```

Create `src/fantasy_sim/data/role_trend/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PositionTrendConfig:
    sensitivity: float


@dataclass
class RoleTrendConfig:
    enabled: bool = False
    positions: tuple[str, ...] = ("QB", "RB", "WR", "TE")
    window_weeks: int = 3
    factor_clamp: tuple[float, float] = (0.90, 1.10)
    qb: PositionTrendConfig = field(default_factory=lambda: PositionTrendConfig(sensitivity=0.12))
    rb: PositionTrendConfig = field(default_factory=lambda: PositionTrendConfig(sensitivity=0.10))
    wr: PositionTrendConfig = field(default_factory=lambda: PositionTrendConfig(sensitivity=0.10))
    te: PositionTrendConfig = field(default_factory=lambda: PositionTrendConfig(sensitivity=0.08))
```

Create `src/fantasy_sim/data/role_trend/config.py`:

```python
from __future__ import annotations

from fantasy_sim.data.role_trend.models import PositionTrendConfig, RoleTrendConfig


def load_role_trend_config(defaults: dict) -> RoleTrendConfig:
    raw = defaults.get("role_trend")
    if not raw:
        return RoleTrendConfig(enabled=False)

    return RoleTrendConfig(
        enabled=raw.get("enabled", False),
        positions=tuple(raw.get("positions", ["QB", "RB", "WR", "TE"])),
        window_weeks=raw.get("window_weeks", 3),
        factor_clamp=tuple(raw.get("factor_clamp", [0.90, 1.10])),
        qb=PositionTrendConfig(sensitivity=raw.get("qb", {}).get("sensitivity", 0.12)),
        rb=PositionTrendConfig(sensitivity=raw.get("rb", {}).get("sensitivity", 0.10)),
        wr=PositionTrendConfig(sensitivity=raw.get("wr", {}).get("sensitivity", 0.10)),
        te=PositionTrendConfig(sensitivity=raw.get("te", {}).get("sensitivity", 0.08)),
    )
```

Add to `config/defaults.yaml` after `ensemble`:

```yaml
availability:
  enabled: false
  positions: [QB, RB, WR, TE]
  injuries:
    enabled: true
    hard_out_statuses: [Out, Doubtful, Suspended, Injured Reserve]
    limited_statuses: [Questionable]
    limited_factor: 0.75
  depth_charts:
    enabled: true
    starter_slots:
      QB: QB1
      RB: RB1
      WR: WR1
      TE: TE1
  usage_fallback:
    enabled: true
    lookback_weeks: 3
    min_factor: 0.85
    qb_low_usage_factor: 0.92
    rb_low_usage_factor: 0.90
    wr_low_usage_factor: 0.92
    te_low_usage_factor: 0.92

role_trend:
  enabled: false
  positions: [QB, RB, WR, TE]
  window_weeks: 3
  factor_clamp: [0.90, 1.10]
  qb:
    sensitivity: 0.12
  rb:
    sensitivity: 0.10
  wr:
    sensitivity: 0.10
  te:
    sensitivity: 0.08
```

Add to `src/fantasy_sim/data/loader.py`:

```python
    def load_injuries(self, seasons: list[int]) -> pl.DataFrame:
        cache_path = self._cache_key("injuries", seasons)
        cached = self._load_cached(cache_path)
        if cached is not None:
            return cached

        df = nflreadpy.load_injuries(seasons)
        rename_map = {}
        if "gsis_id" in df.columns and "player_id" not in df.columns:
            rename_map["gsis_id"] = "player_id"
        if "full_name" in df.columns and "player_name" not in df.columns:
            rename_map["full_name"] = "player_name"
        if rename_map:
            df = df.rename(rename_map)
        self._save_cache(df, cache_path)
        return df
```

Modify `src/fantasy_sim/validation/config.py`:

```python
from fantasy_sim.data.availability.config import load_availability_config
from fantasy_sim.data.role_trend.config import load_role_trend_config
...
    availability = load_availability_config(config)
    role_trend = load_role_trend_config(config)
    return {
        "pff_config": pff if pff.enabled else None,
        "weather_config": weather if weather.enabled else None,
        "vegas_config": vegas if vegas.enabled else None,
        "props_config": props if props.enabled else None,
        "usage_config": usage if usage.enabled else None,
        "availability_config": availability if availability.enabled else None,
        "role_trend_config": role_trend if role_trend.enabled else None,
        "game_script_config": game_script if game_script.enabled else None,
        "goal_line_concentration_config": (
            goal_line_concentration if goal_line_concentration.enabled else None
        ),
        "td_tendency_config": td_tendency if td_tendency.enabled else None,
    }
...
    return {
        "pff_config": None,
        "weather_config": None,
        "vegas_config": None,
        "props_config": None,
        "usage_config": None,
        "availability_config": None,
        "role_trend_config": None,
        "game_script_config": None,
        "goal_line_concentration_config": None,
        "td_tendency_config": None,
    }
```

- [ ] **Step 4: Run the config tests and validation-config smoke**

Run: `uv run pytest tests/test_data/test_availability/test_config.py tests/test_data/test_role_trend/test_config.py tests/test_validation/test_config.py -v`

Expected: PASS for the new config loaders and the new validation-config keys.

- [ ] **Step 5: Commit**

```bash
git add config/defaults.yaml src/fantasy_sim/data/loader.py src/fantasy_sim/data/availability/__init__.py src/fantasy_sim/data/availability/models.py src/fantasy_sim/data/availability/config.py src/fantasy_sim/data/role_trend/__init__.py src/fantasy_sim/data/role_trend/models.py src/fantasy_sim/data/role_trend/config.py src/fantasy_sim/validation/config.py tests/test_data/test_availability/test_config.py tests/test_data/test_role_trend/test_config.py tests/test_validation/test_config.py
git commit -m "feat: add phase 2 config families"
```

### Task 2: Build The Shared Weekly Role Input Loader

**Files:**
- Create: `src/fantasy_sim/data/availability/loader.py`
- Create: `tests/test_data/test_availability/test_loader.py`

- [ ] **Step 1: Write the failing loader tests**

Create `tests/test_data/test_availability/test_loader.py`:

```python
from __future__ import annotations

import polars as pl

from fantasy_sim.data.availability.loader import WeeklyRoleInputLoader


class _StubDataLoader:
    def load_rosters(self, seasons):
        return pl.DataFrame(
            {
                "season": [2024],
                "week": [5],
                "team": ["KC"],
                "position": ["WR"],
                "player_id": ["00-001"],
                "player_name": ["Wide One"],
                "pfr_id": ["W/One00"],
                "depth_chart_position": ["WR1"],
                "status_description_abbr": ["ACT"],
            }
        )

    def load_player_stats(self, seasons, summary_level="week"):
        return pl.DataFrame(
            {
                "season": [2024],
                "week": [5],
                "team": ["KC"],
                "player_id": ["00-001"],
                "player_name": ["Wide One"],
                "position": ["WR"],
                "targets": [8],
                "receptions": [5],
                "target_share": [0.24],
                "carries": [0],
                "attempts": [0],
            }
        )

    def load_snap_counts(self, seasons):
        return pl.DataFrame(
            {
                "season": [2024],
                "week": [5],
                "team": ["KC"],
                "pfr_player_id": ["W/One00"],
                "offense_pct": [0.72],
            }
        )

    def load_injuries(self, seasons):
        return pl.DataFrame(
            {
                "season": [2024],
                "week": [5],
                "team": ["KC"],
                "player_id": ["00-001"],
                "player_name": ["Wide One"],
                "position": ["WR"],
                "report_status": ["Questionable"],
                "practice_status": ["Limited"],
            }
        )

    def load_depth_charts(self, seasons):
        return pl.DataFrame(
            {
                "season": [2024],
                "week": [5],
                "club_code": ["KC"],
                "gsis_id": ["00-001"],
                "position": ["WR"],
                "depth_position": ["WR1"],
                "full_name": ["Wide One"],
            }
        )


def test_load_weekly_merges_explicit_and_fallback_inputs():
    loader = WeeklyRoleInputLoader(loader=_StubDataLoader())
    frame = loader.load_weekly([2024])

    row = frame.filter(pl.col("player_id") == "00-001").row(0, named=True)

    assert row["team"] == "KC"
    assert row["position"] == "WR"
    assert row["targets"] == 8
    assert row["offense_pct"] == 0.72
    assert row["report_status"] == "Questionable"
    assert row["depth_position"] == "WR1"


def test_load_weekly_handles_missing_injuries_with_null_columns():
    stub = _StubDataLoader()
    stub.load_injuries = lambda seasons: pl.DataFrame()

    loader = WeeklyRoleInputLoader(loader=stub)
    frame = loader.load_weekly([2024])

    row = frame.filter(pl.col("player_id") == "00-001").row(0, named=True)
    assert row["report_status"] is None
    assert row["practice_status"] is None
```

- [ ] **Step 2: Run the loader tests to verify they fail**

Run: `uv run pytest tests/test_data/test_availability/test_loader.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'fantasy_sim.data.availability.loader'`

- [ ] **Step 3: Implement the weekly role input loader**

Create `src/fantasy_sim/data/availability/loader.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from fantasy_sim.data.loader import DataLoader


@dataclass
class WeeklyRoleInputLoader:
    loader: DataLoader | None = None

    def __post_init__(self) -> None:
        if self.loader is None:
            self.loader = DataLoader()
        self._cache: dict[tuple[int, ...], pl.DataFrame] = {}

    def load_weekly(self, seasons: list[int]) -> pl.DataFrame:
        key = tuple(sorted(seasons))
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        rosters = self.loader.load_rosters(seasons).select(
            [
                "season",
                "week",
                "team",
                "position",
                "player_id",
                "player_name",
                "pfr_id",
                "depth_chart_position",
                "status_description_abbr",
            ]
        )

        stats = self.loader.load_player_stats(seasons).select(
            [
                "season",
                "week",
                "team",
                "player_id",
                "player_name",
                "position",
                "attempts",
                "carries",
                "targets",
                "receptions",
                "target_share",
            ]
        )

        snap = self.loader.load_snap_counts(seasons)
        if not snap.is_empty():
            snap = (
                snap.select(["season", "week", "team", "pfr_player_id", "offense_pct"])
                .join(
                    rosters.select(["season", "week", "team", "pfr_id", "player_id"]).unique(),
                    left_on=["season", "week", "team", "pfr_player_id"],
                    right_on=["season", "week", "team", "pfr_id"],
                    how="left",
                )
                .select(["season", "week", "team", "player_id", "offense_pct"])
            )
        else:
            snap = pl.DataFrame(schema={"season": pl.Int64, "week": pl.Int64, "team": pl.Utf8, "player_id": pl.Utf8, "offense_pct": pl.Float64})

        injuries = self.loader.load_injuries(seasons)
        if not injuries.is_empty():
            injuries = injuries.select(
                [
                    "season",
                    "week",
                    "team",
                    "player_id",
                    "report_status",
                    "practice_status",
                ]
            )
        else:
            injuries = pl.DataFrame(
                schema={
                    "season": pl.Int64,
                    "week": pl.Int64,
                    "team": pl.Utf8,
                    "player_id": pl.Utf8,
                    "report_status": pl.Utf8,
                    "practice_status": pl.Utf8,
                }
            )

        depth = self.loader.load_depth_charts(seasons)
        if not depth.is_empty():
            depth = (
                depth.rename({"club_code": "team", "gsis_id": "player_id", "full_name": "player_name"})
                .select(["season", "week", "team", "player_id", "depth_position"])
            )
        else:
            depth = pl.DataFrame(
                schema={
                    "season": pl.Int64,
                    "week": pl.Int64,
                    "team": pl.Utf8,
                    "player_id": pl.Utf8,
                    "depth_position": pl.Utf8,
                }
            )

        frame = (
            rosters.join(
                stats,
                on=["season", "week", "team", "player_id", "player_name", "position"],
                how="left",
            )
            .join(snap, on=["season", "week", "team", "player_id"], how="left")
            .join(injuries, on=["season", "week", "team", "player_id"], how="left")
            .join(depth, on=["season", "week", "team", "player_id"], how="left")
        )

        self._cache[key] = frame
        return frame
```

- [ ] **Step 4: Run the loader tests**

Run: `uv run pytest tests/test_data/test_availability/test_loader.py -v`

Expected: PASS with merged player-week rows and null-safe missing injuries behavior.

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/availability/loader.py tests/test_data/test_availability/test_loader.py
git commit -m "feat: add weekly role input loader"
```

### Task 3: Implement The Conservative Availability Engine

**Files:**
- Modify: `src/fantasy_sim/data/availability/models.py`
- Create: `src/fantasy_sim/data/availability/engine.py`
- Create: `tests/test_data/test_availability/test_engine.py`

- [ ] **Step 1: Write the failing availability-engine tests**

Create `tests/test_data/test_availability/test_engine.py`:

```python
from __future__ import annotations

import numpy as np
import polars as pl

from fantasy_sim.data.availability.engine import AvailabilityEngine
from fantasy_sim.data.availability.models import AvailabilityConfig
from fantasy_sim.models.player import PlayerModel, PlayerOutcomes, PlayerUsage, TeamRoster


def _roster() -> TeamRoster:
    return TeamRoster(
        team="KC",
        players=[
            PlayerModel(
                "QB1",
                "Starter QB",
                "QB",
                "KC",
                PlayerUsage(snap_share=1.0),
                PlayerOutcomes(),
            ),
            PlayerModel(
                "QB2",
                "Backup QB",
                "QB",
                "KC",
                PlayerUsage(snap_share=0.2),
                PlayerOutcomes(),
            ),
            PlayerModel(
                "WR1",
                "Wide One",
                "WR",
                "KC",
                PlayerUsage(target_share=0.30),
                PlayerOutcomes(catch_rate=0.60, receiving_yards_dist=np.array([8.0, 12.0])),
            ),
        ],
    )


class _StubRoleInputs:
    def __init__(self, frame: pl.DataFrame) -> None:
        self.frame = frame

    def load_weekly(self, seasons):
        return self.frame


def _config() -> AvailabilityConfig:
    return AvailabilityConfig(enabled=True)


def test_explicit_out_zeroes_receiver_share():
    frame = pl.DataFrame(
        {
            "season": [2024],
            "week": [5],
            "team": ["KC"],
            "player_id": ["WR1"],
            "position": ["WR"],
            "attempts": [0],
            "carries": [0],
            "targets": [7],
            "offense_pct": [0.75],
            "report_status": ["Out"],
            "practice_status": ["Did Not Participate"],
            "depth_position": ["WR1"],
        }
    )
    roster = _roster()
    engine = AvailabilityEngine(_config(), role_inputs_loader=_StubRoleInputs(frame))

    engine.apply(roster, season=2024, week=5)

    wr = next(player for player in roster.players if player.player_id == "WR1")
    assert wr.usage.target_share == 0.0


def test_usage_only_low_usage_soft_dampens_but_does_not_bench_qb():
    frame = pl.DataFrame(
        {
            "season": [2024, 2024, 2024],
            "week": [2, 3, 4],
            "team": ["KC", "KC", "KC"],
            "player_id": ["QB1", "QB1", "QB1"],
            "position": ["QB", "QB", "QB"],
            "attempts": [10, 11, 9],
            "carries": [1, 0, 1],
            "targets": [0, 0, 0],
            "offense_pct": [0.61, 0.59, 0.58],
            "report_status": [None, None, None],
            "practice_status": [None, None, None],
            "depth_position": [None, None, None],
        }
    )
    roster = _roster()
    engine = AvailabilityEngine(_config(), role_inputs_loader=_StubRoleInputs(frame))

    engine.apply(roster, season=2024, week=5)

    qb = next(player for player in roster.players if player.player_id == "QB1")
    assert 0.0 < qb.usage.snap_share < 1.0


def test_explicit_qb1_depth_chart_demotes_backup():
    frame = pl.DataFrame(
        {
            "season": [2024, 2024],
            "week": [5, 5],
            "team": ["KC", "KC"],
            "player_id": ["QB1", "QB2"],
            "position": ["QB", "QB"],
            "attempts": [0, 0],
            "carries": [0, 0],
            "targets": [0, 0],
            "offense_pct": [0.70, 0.20],
            "report_status": [None, None],
            "practice_status": [None, None],
            "depth_position": ["QB1", "QB2"],
        }
    )
    roster = _roster()
    engine = AvailabilityEngine(_config(), role_inputs_loader=_StubRoleInputs(frame))

    engine.apply(roster, season=2024, week=5)

    qb1 = next(player for player in roster.players if player.player_id == "QB1")
    qb2 = next(player for player in roster.players if player.player_id == "QB2")
    assert qb1.usage.snap_share == 1.0
    assert qb2.usage.snap_share == 0.0
```

- [ ] **Step 2: Run the availability-engine tests to verify they fail**

Run: `uv run pytest tests/test_data/test_availability/test_engine.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'fantasy_sim.data.availability.engine'`

- [ ] **Step 3: Implement the soft-only fallback engine**

Extend `src/fantasy_sim/data/availability/models.py` with:

```python
@dataclass
class AvailabilityDecision:
    hard_inactive: bool = False
    factor: float = 1.0
    reason: str | None = None
```

Create `src/fantasy_sim/data/availability/engine.py`:

```python
from __future__ import annotations

import polars as pl

from fantasy_sim.data.availability.loader import WeeklyRoleInputLoader
from fantasy_sim.data.availability.models import AvailabilityConfig, AvailabilityDecision
from fantasy_sim.models.player import TeamRoster


class AvailabilityEngine:
    def __init__(
        self,
        config: AvailabilityConfig,
        role_inputs_loader: WeeklyRoleInputLoader | None = None,
    ) -> None:
        self._config = config
        self._loader = role_inputs_loader or WeeklyRoleInputLoader()
        self._cache: dict[int, pl.DataFrame] = {}

    def _season_inputs(self, season: int) -> pl.DataFrame:
        cached = self._cache.get(season)
        if cached is not None:
            return cached
        frame = self._loader.load_weekly([season])
        self._cache[season] = frame
        return frame

    def _soft_usage_factor(self, position: str) -> float:
        cfg = self._config.usage_fallback
        if position == "QB":
            return cfg.qb_low_usage_factor
        if position == "RB":
            return cfg.rb_low_usage_factor
        if position == "WR":
            return cfg.wr_low_usage_factor
        return cfg.te_low_usage_factor

    def _decision_for_player(
        self,
        player_id: str,
        position: str,
        team: str,
        season: int,
        week: int,
    ) -> AvailabilityDecision:
        rows = self._season_inputs(season).filter(
            (pl.col("player_id") == player_id)
            & (pl.col("team") == team)
            & (pl.col("week") <= week)
        )
        current = rows.filter(pl.col("week") == week)

        if not current.is_empty() and self._config.injuries.enabled:
            status = current.select("report_status").to_series().to_list()[0]
            if status in self._config.injuries.hard_out_statuses:
                return AvailabilityDecision(hard_inactive=True, factor=0.0, reason=f"injury:{status}")
            if status in self._config.injuries.limited_statuses:
                return AvailabilityDecision(
                    hard_inactive=False,
                    factor=self._config.injuries.limited_factor,
                    reason=f"injury:{status}",
                )

        if position == "QB" and self._config.depth_charts.enabled and not current.is_empty():
            depth = current.select("depth_position").to_series().to_list()[0]
            if depth == self._config.depth_charts.starter_slots["QB"]:
                return AvailabilityDecision(hard_inactive=False, factor=1.0, reason="depth:starter")
            if depth is not None and depth.startswith("QB"):
                return AvailabilityDecision(hard_inactive=True, factor=0.0, reason=f"depth:{depth}")

        history = rows.filter(pl.col("week") < week).tail(self._config.usage_fallback.lookback_weeks)
        if history.is_empty() or not self._config.usage_fallback.enabled:
            return AvailabilityDecision()

        recent_targets = float(history.select(pl.col("targets").fill_null(0).sum()).item() or 0.0)
        recent_carries = float(history.select(pl.col("carries").fill_null(0).sum()).item() or 0.0)
        recent_attempts = float(history.select(pl.col("attempts").fill_null(0).sum()).item() or 0.0)

        if position == "QB" and recent_attempts <= 12:
            return AvailabilityDecision(factor=self._soft_usage_factor(position), reason="usage:soft")
        if position == "RB" and recent_carries + recent_targets <= 8:
            return AvailabilityDecision(factor=self._soft_usage_factor(position), reason="usage:soft")
        if position in {"WR", "TE"} and recent_targets <= 6:
            return AvailabilityDecision(factor=self._soft_usage_factor(position), reason="usage:soft")
        return AvailabilityDecision()

    def apply(self, roster: TeamRoster, season: int, week: int) -> None:
        if not self._config.enabled:
            return

        for player in roster.players:
            if player.position not in self._config.positions:
                continue
            decision = self._decision_for_player(player.player_id, player.position, roster.team, season, week)
            if decision.hard_inactive:
                player.usage.snap_share = 0.0
                player.usage.target_share = 0.0
                player.usage.carry_share = 0.0
                continue
            player.usage.snap_share *= decision.factor
            player.usage.target_share *= decision.factor
            player.usage.carry_share *= decision.factor
```

- [ ] **Step 4: Run the availability-engine tests**

Run: `uv run pytest tests/test_data/test_availability/test_engine.py -v`

Expected: PASS for explicit-out, explicit-QB-starter, and usage-only soft-damp behavior.

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/availability/models.py src/fantasy_sim/data/availability/engine.py tests/test_data/test_availability/test_engine.py
git commit -m "feat: add conservative availability engine"
```

### Task 4: Thread Availability Through GameContext, CLI, And Parallel Builders

**Files:**
- Modify: `src/fantasy_sim/data/game_context.py:58-205`
- Modify: `src/fantasy_sim/data/game_context.py:698-741`
- Modify: `src/fantasy_sim/cli.py:105-148`
- Modify: `src/fantasy_sim/validation/parallel.py:159-520`
- Create: `tests/test_data/test_availability/test_game_context.py`
- Modify: `tests/test_validation/test_parallel.py`

- [ ] **Step 1: Write the failing integration tests**

Create `tests/test_data/test_availability/test_game_context.py`:

```python
from __future__ import annotations

import numpy as np

from fantasy_sim.data.game_context import GameContextBuilder
from fantasy_sim.engine.types import TeamDistributions
from fantasy_sim.models.distributions import DriveStartModel, KickingModel, PlayCallingDist, PlayOutcomeDist, TurnoverRates
from fantasy_sim.models.player import PlayerModel, PlayerOutcomes, PlayerUsage, TeamRoster


def _dists(team: str) -> TeamDistributions:
    return TeamDistributions(
        play_calling=PlayCallingDist(team=team, distributions={}, default={"pass": 0.55, "run": 0.45}),
        play_outcomes=PlayOutcomeDist(distributions={}, defaults={"run": np.array([3, 5]), "pass": np.array([6, 9])}),
        turnover_rates=TurnoverRates(team=team, int_rate=0.02, fumble_rate=0.01, sack_rate=0.06, sack_fumble_rate=0.10),
        kicking=KickingModel(fg_make_rate={"0_39": 0.93, "40_49": 0.82, "50_plus": 0.65}, xp_rate=0.94),
        drive_start=DriveStartModel(touchback_rate=0.55, touchback_yardline=75, return_yardlines=np.array([74, 76])),
    )


def _roster(team: str) -> TeamRoster:
    return TeamRoster(
        team=team,
        players=[
            PlayerModel(f"{team}_QB", "QB", "QB", team, PlayerUsage(snap_share=1.0), PlayerOutcomes()),
            PlayerModel(f"{team}_WR", "WR", "WR", team, PlayerUsage(target_share=0.50), PlayerOutcomes(catch_rate=0.60, receiving_yards_dist=np.array([8, 12]))),
        ],
    )


def test_build_game_applies_availability_before_usage(monkeypatch):
    calls = []
    builder = object.__new__(GameContextBuilder)
    builder.build_team_distributions = lambda *args, **kwargs: _dists(args[0])
    builder.build_team_roster = lambda *args, **kwargs: _roster(args[0])
    builder._vegas_engine = object()
    builder._usage_engine = object()
    builder._props_engine = None
    builder._matchup_engine = None
    builder._tier_engine = None
    builder._talent_stabilizer = None
    builder._coverage_engine = None
    builder._dst_baseline_engine = None
    builder._kicker_engine = None
    builder._td_tendency_engine = None
    builder._weather_engine = None
    builder._game_script_engine = None
    builder._availability_engine = type("AvailabilityStub", (), {"apply": lambda self, roster, season, week: calls.append(f"availability:{roster.team}")})()
    builder._ensure_pff_crosswalk = lambda *args, **kwargs: None
    builder._apply_vegas = lambda dists, ctx: calls.append(f"vegas:{dists.play_calling.team}")
    builder._vegas_engine = type("VegasStub", (), {"compute": lambda self, **kwargs: (object(), object())})()
    builder._usage_engine = type("UsageStub", (), {"apply": lambda self, roster, season, week, pff_crosswalk=None: calls.append(f"usage:{roster.team}") or {}})()
    builder._pff_crosswalk = None
    builder._usage_config = type("UsageConfig", (), {"enabled": True})()

    GameContextBuilder.build_game(
        builder,
        "KC",
        "BUF",
        training_seasons=[2022, 2023, 2024],
        target_season=2024,
        week=5,
    )

    assert calls[:6] == [
        "vegas:KC",
        "vegas:BUF",
        "availability:KC",
        "availability:BUF",
        "usage:KC",
        "usage:BUF",
    ]
```

Add to `tests/test_validation/test_parallel.py`:

```python
    @patch("fantasy_sim.validation.parallel.GameContextBuilder")
    def test_build_games_parallel_accepts_availability_config(self, mock_builder_cls):
        from fantasy_sim.validation.parallel import build_games_parallel

        mock_builder_cls.return_value = self._mock_builder()
        config = object()

        build_games_parallel(
            [("KC", "BUF", [2022, 2023], 2024, 1, "game_1", 42)],
            cache_dir=Path("/tmp"),
            availability_config=config,
            max_workers=1,
        )

        assert mock_builder_cls.call_args.kwargs["availability_config"] is config

    @patch("fantasy_sim.validation.parallel.GameContextBuilder")
    def test_dual_arm_only_threads_availability_to_on_builder(self, mock_builder_cls):
        from fantasy_sim.validation.parallel import build_games_parallel

        config = object()

        build_games_parallel(
            [("KC", "BUF", [2022, 2023], 2024, 1, "game_1", 42)],
            cache_dir=Path("/tmp"),
            availability_config=config,
            max_workers=1,
            dual_arm=True,
        )

        assert mock_builder_cls.call_count == 2
        assert "availability_config" not in mock_builder_cls.call_args_list[0].kwargs
        assert mock_builder_cls.call_args_list[1].kwargs["availability_config"] is config
```

- [ ] **Step 2: Run the integration tests to verify they fail**

Run: `uv run pytest tests/test_data/test_availability/test_game_context.py tests/test_validation/test_parallel.py -v`

Expected: FAIL because `GameContextBuilder` and `build_games_parallel()` do not yet accept `availability_config` or call the availability engine.

- [ ] **Step 3: Thread `availability_config` through the build path**

Modify `src/fantasy_sim/data/game_context.py`:

```python
from fantasy_sim.data.availability.models import AvailabilityConfig
...
        availability_config: AvailabilityConfig | None = None,
...
        self._availability_engine = None
        self._availability_config = availability_config or AvailabilityConfig(enabled=False)
        if self._availability_config.enabled:
            from fantasy_sim.data.availability.engine import AvailabilityEngine
            self._availability_engine = AvailabilityEngine(self._availability_config)
            logger.info("Availability engine enabled")
...
        if self._vegas_engine is not None and target_season and week:
            home_vegas_ctx, away_vegas_ctx = self._vegas_engine.compute(
                home_team=home_team, away_team=away_team, target_season=target_season, week=week,
            )
            self._apply_vegas(home_dists, home_vegas_ctx)
            self._apply_vegas(away_dists, away_vegas_ctx)

        if self._availability_engine is not None and target_season and week:
            self._availability_engine.apply(home_roster, target_season, week)
            self._availability_engine.apply(away_roster, target_season, week)
            from fantasy_sim.data.player_builder import _normalize_roster_shares
            _normalize_roster_shares(home_roster)
            _normalize_roster_shares(away_roster)
```

Modify `src/fantasy_sim/cli.py`:

```python
from fantasy_sim.data.availability.config import load_availability_config
...
    availability_config = load_availability_config(defaults)
...
        availability_config=availability_config if availability_config.enabled else None,
```

Modify `src/fantasy_sim/validation/parallel.py` in every builder factory and worker initializer that currently accepts `usage_config` / `game_script_config`:

```python
    availability_config: "AvailabilityConfig | None" = None,
...
        availability_config=availability_config,
```

In dual-arm builder creation, pass `availability_config` only to the `"on"` builder, matching the existing pattern used for `game_script_config` and `goal_line_concentration_config`.

- [ ] **Step 4: Run the availability integration tests**

Run: `uv run pytest tests/test_data/test_availability/test_game_context.py tests/test_validation/test_parallel.py -v`

Expected: PASS with verified call order and verified single-arm / dual-arm threading behavior.

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/game_context.py src/fantasy_sim/cli.py src/fantasy_sim/validation/parallel.py tests/test_data/test_availability/test_game_context.py tests/test_validation/test_parallel.py
git commit -m "feat: thread availability through build paths"
```

### Task 5: Implement Role Trend And Shared Projection-Layer Ordering

**Files:**
- Create: `src/fantasy_sim/scoring/role_trend.py`
- Create: `src/fantasy_sim/scoring/projection_layers.py`
- Create: `tests/test_scoring/test_role_trend.py`

- [ ] **Step 1: Write the failing role-trend tests**

Create `tests/test_scoring/test_role_trend.py`:

```python
from __future__ import annotations

import polars as pl

from fantasy_sim.data.role_trend.models import RoleTrendConfig
from fantasy_sim.scoring.projection_layers import apply_projection_layers
from fantasy_sim.scoring.role_trend import RoleTrendProjectionAdjuster


class _StubRoleInputs:
    def __init__(self, frame: pl.DataFrame) -> None:
        self.frame = frame

    def load_weekly(self, seasons):
        return self.frame


def _config() -> RoleTrendConfig:
    return RoleTrendConfig(enabled=True)


def test_adjust_week_softly_boosts_wr_projection_and_recomputes_rank():
    frame = pl.DataFrame(
        {
            "season": [2024, 2024, 2024, 2024],
            "week": [1, 2, 3, 4],
            "team": ["KC", "KC", "KC", "KC"],
            "player_id": ["WR1", "WR1", "WR1", "WR1"],
            "position": ["WR", "WR", "WR", "WR"],
            "attempts": [0, 0, 0, 0],
            "carries": [0, 0, 0, 0],
            "targets": [5, 6, 10, 11],
            "offense_pct": [0.68, 0.69, 0.80, 0.82],
        }
    )
    adjuster = RoleTrendProjectionAdjuster(_config(), role_inputs_loader=_StubRoleInputs(frame))

    adjusted, stats = adjuster.adjust_week(
        [
            {"player_id": "WR1", "name": "Wide One", "team": "KC", "position": "WR", "fpts": 10.0, "rank": 2},
            {"player_id": "RB1", "name": "Back One", "team": "KC", "position": "RB", "fpts": 10.2, "rank": 1},
        ],
        season=2024,
        week=5,
    )

    wr = next(row for row in adjusted if row["player_id"] == "WR1")
    assert wr["fpts"] > 10.0
    assert wr["role_trend_applied"] is True
    assert stats.adjusted_rows == 1
    assert adjusted[0]["rank"] == 1


def test_apply_projection_layers_runs_role_trend_before_ensemble():
    order = []

    class _Trend:
        def adjust_week(self, projections, season, week):
            order.append("trend")
            return projections, object()

    class _Ensemble:
        def blend_week(self, projections, season, week):
            order.append("ensemble")
            return projections, object()

    apply_projection_layers(
        [{"player_id": "WR1", "position": "WR", "team": "KC", "fpts": 10.0, "rank": 1}],
        season=2024,
        week=5,
        role_trend_adjuster=_Trend(),
        ensembler=_Ensemble(),
    )

    assert order == ["trend", "ensemble"]
```

- [ ] **Step 2: Run the role-trend tests to verify they fail**

Run: `uv run pytest tests/test_scoring/test_role_trend.py -v`

Expected: FAIL with `ModuleNotFoundError` for the new role-trend and projection-layer modules.

- [ ] **Step 3: Implement the adjuster and ordered projection-layer helper**

Create `src/fantasy_sim/scoring/role_trend.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from fantasy_sim.data.availability.loader import WeeklyRoleInputLoader
from fantasy_sim.data.role_trend.models import RoleTrendConfig


@dataclass
class TrendStats:
    total_rows: int
    adjusted_rows: int
    neutral_rows: int


class RoleTrendProjectionAdjuster:
    def __init__(
        self,
        config: RoleTrendConfig,
        role_inputs_loader: WeeklyRoleInputLoader | None = None,
    ) -> None:
        self.config = config
        self.loader = role_inputs_loader or WeeklyRoleInputLoader()
        self._cache: dict[int, pl.DataFrame] = {}

    def _season_inputs(self, season: int) -> pl.DataFrame:
        cached = self._cache.get(season)
        if cached is not None:
            return cached
        frame = self.loader.load_weekly([season])
        self._cache[season] = frame
        return frame

    def _position_sensitivity(self, position: str) -> float:
        if position == "QB":
            return self.config.qb.sensitivity
        if position == "RB":
            return self.config.rb.sensitivity
        if position == "WR":
            return self.config.wr.sensitivity
        return self.config.te.sensitivity

    def _opportunity(self, frame: pl.DataFrame, position: str) -> float:
        if frame.is_empty():
            return 0.0
        if position == "QB":
            return float(frame.select((pl.col("attempts").fill_null(0) + (pl.col("carries").fill_null(0) * 0.5)).mean()).item() or 0.0)
        if position == "RB":
            return float(frame.select((pl.col("carries").fill_null(0) + (pl.col("targets").fill_null(0) * 1.5)).mean()).item() or 0.0)
        return float(frame.select(pl.col("targets").fill_null(0).mean()).item() or 0.0)

    def adjust_week(self, projections: list[dict], *, season: int, week: int) -> tuple[list[dict], TrendStats]:
        total_rows = len(projections)
        if not projections or not self.config.enabled or week <= 1:
            return [dict(row) for row in projections], TrendStats(total_rows=total_rows, adjusted_rows=0, neutral_rows=total_rows)

        season_inputs = self._season_inputs(season)
        adjusted_rows = 0
        out: list[dict] = []

        for projection in projections:
            row = dict(projection)
            position = row.get("position", "")
            if position not in self.config.positions:
                row["role_trend_applied"] = False
                row["role_trend_factor"] = 1.0
                out.append(row)
                continue

            player_history = season_inputs.filter(
                (pl.col("player_id") == row["player_id"]) & (pl.col("week") < week)
            )
            recent = player_history.tail(self.config.window_weeks)
            baseline = player_history.head(max(0, player_history.height - self.config.window_weeks))
            if recent.is_empty():
                row["role_trend_applied"] = False
                row["role_trend_factor"] = 1.0
                out.append(row)
                continue

            recent_opp = self._opportunity(recent, position)
            baseline_opp = self._opportunity(baseline, position) or recent_opp
            ratio = recent_opp / max(baseline_opp, 1.0)
            sensitivity = self._position_sensitivity(position)
            raw_factor = 1.0 + (ratio - 1.0) * sensitivity
            factor = max(self.config.factor_clamp[0], min(self.config.factor_clamp[1], raw_factor))

            row["fpts"] = round(float(row["fpts"]) * factor, 1)
            row["role_trend_applied"] = factor != 1.0
            row["role_trend_factor"] = round(factor, 4)
            if factor != 1.0:
                adjusted_rows += 1
            out.append(row)

        out.sort(key=lambda item: item["fpts"], reverse=True)
        for index, row in enumerate(out, start=1):
            row["rank"] = index

        return out, TrendStats(total_rows=total_rows, adjusted_rows=adjusted_rows, neutral_rows=total_rows - adjusted_rows)
```

Create `src/fantasy_sim/scoring/projection_layers.py`:

```python
from __future__ import annotations


def apply_projection_layers(
    projections: list[dict],
    *,
    season: int,
    week: int,
    role_trend_adjuster=None,
    ensembler=None,
) -> list[dict]:
    rows = [dict(row) for row in projections]
    if role_trend_adjuster is not None:
        rows, _ = role_trend_adjuster.adjust_week(rows, season=season, week=week)
    if ensembler is not None:
        rows, _ = ensembler.blend_week(rows, season=season, week=week)
    return rows
```

- [ ] **Step 4: Run the role-trend tests**

Run: `uv run pytest tests/test_scoring/test_role_trend.py -v`

Expected: PASS with soft-only trend behavior and verified ordering of `role_trend` before `ensemble`.

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/scoring/role_trend.py src/fantasy_sim/scoring/projection_layers.py tests/test_scoring/test_role_trend.py
git commit -m "feat: add post-sim role trend adjuster"
```

### Task 6: Wire Role Trend And Coverage Through CLI, Validation, And Backtester

**Files:**
- Modify: `src/fantasy_sim/cli.py:151-175`
- Modify: `src/fantasy_sim/validation/backtester.py:56-205`
- Modify: `scripts/validate.py:168-416`
- Modify: `src/fantasy_sim/validation/coverage.py:222-423`
- Modify: `tests/test_validation/test_coverage.py`
- Create: `tests/test_validation/test_role_trend_pipeline.py`

- [ ] **Step 1: Write the failing pipeline and coverage tests**

Create `tests/test_validation/test_role_trend_pipeline.py`:

```python
from fantasy_sim.scoring.projection_layers import apply_projection_layers


def test_apply_projection_layers_handles_missing_layers():
    rows = [{"player_id": "WR1", "position": "WR", "team": "KC", "fpts": 10.0, "rank": 1}]
    out = apply_projection_layers(rows, season=2024, week=5)
    assert out == rows
```

Add to `tests/test_validation/test_coverage.py`:

```python
def test_availability_and_role_trend_report_partial_when_explicit_inputs_are_sparse(tmp_path):
    cache_dir = tmp_path / "cache"
    _write_parquet_placeholder(cache_dir / "player_stats_week_2023.parquet")
    _write_parquet_placeholder(cache_dir / "snap_counts_2023.parquet")
    _write_parquet_placeholder(cache_dir / "rosters_weekly_2023.parquet")
    _write_parquet_placeholder(cache_dir / "depth_charts_2023.parquet")

    config = {
        "availability": {
            "enabled": True,
            "positions": ["QB", "RB", "WR", "TE"],
            "injuries": {"enabled": True},
            "depth_charts": {"enabled": True},
            "usage_fallback": {"enabled": True},
        },
        "role_trend": {"enabled": True, "positions": ["QB", "RB", "WR", "TE"]},
    }

    coverage = collect_signal_coverage(config, [2023, 2024], cache_dir=cache_dir)

    assert coverage["availability"].status == "partial"
    assert coverage["availability.depth_charts"].covered_seasons == [2023]
    assert coverage["role_trend"].covered_seasons == [2023]
```

- [ ] **Step 2: Run the pipeline and coverage tests to verify they fail**

Run: `uv run pytest tests/test_validation/test_role_trend_pipeline.py tests/test_validation/test_coverage.py -v`

Expected: FAIL because coverage does not yet know about the Phase 2 families and the shared projection-layer helper is not yet wired into validation callers.

- [ ] **Step 3: Integrate `role_trend` before ensemble and extend coverage**

Modify `src/fantasy_sim/cli.py`:

```python
from fantasy_sim.data.role_trend.config import load_role_trend_config
from fantasy_sim.scoring.projection_layers import apply_projection_layers
from fantasy_sim.scoring.role_trend import RoleTrendProjectionAdjuster
...
def _make_role_trend_adjuster(defaults: dict) -> RoleTrendProjectionAdjuster | None:
    cfg = load_role_trend_config(defaults)
    if not cfg.enabled:
        return None
    return RoleTrendProjectionAdjuster(cfg)
...
def _maybe_blend_player_projs(...):
    return apply_projection_layers(
        player_projs,
        season=season,
        week=week,
        role_trend_adjuster=role_trend_adjuster,
        ensembler=ensembler,
    )
```

Only use the helper in non-detail `week`, `season`, and `game` flows. Leave the detailed `player` flow neutral in v1.

Modify `src/fantasy_sim/validation/backtester.py`:

```python
from fantasy_sim.data.role_trend.models import RoleTrendConfig
from fantasy_sim.scoring.projection_layers import apply_projection_layers
from fantasy_sim.scoring.role_trend import RoleTrendProjectionAdjuster
...
        role_trend_config: RoleTrendConfig | None = None,
...
        self._role_trend_config = role_trend_config
...
        role_trend = (
            RoleTrendProjectionAdjuster(self._role_trend_config)
            if self._role_trend_config is not None and self._role_trend_config.enabled
            else None
        )
...
            projections = apply_projection_layers(
                projections,
                season=self.test_season,
                week=wk,
                role_trend_adjuster=role_trend,
                ensembler=ensembler,
            )
```

Modify `scripts/validate.py`:

```python
from fantasy_sim.data.role_trend.config import load_role_trend_config
from fantasy_sim.scoring.projection_layers import apply_projection_layers
from fantasy_sim.scoring.role_trend import RoleTrendProjectionAdjuster
...
    arm_a_role_trend = (
        RoleTrendProjectionAdjuster(arm_a_configs["role_trend_config"])
        if arm_a_configs.get("role_trend_config") is not None
        else None
    )
    arm_b_role_trend = (
        RoleTrendProjectionAdjuster(arm_b_configs["role_trend_config"])
        if arm_b_configs.get("role_trend_config") is not None
        else None
    )
...
            projections = apply_projection_layers(
                projections,
                season=test_season,
                week=spec.week,
                role_trend_adjuster=arm_b_role_trend,
                ensembler=arm_b_ensembler,
            )
...
            projections = apply_projection_layers(
                projections,
                season=test_season,
                week=spec.week,
                role_trend_adjuster=arm_a_role_trend if is_arm_a else arm_b_role_trend,
                ensembler=ensembler,
            )
```

Modify `src/fantasy_sim/validation/coverage.py`:

```python
    availability_enabled = _signal_enabled(
        config,
        ("availability_config", "availability"),
        ("availability",),
    )
    availability_injuries_enabled = _signal_enabled(
        config,
        ("availability_config", "availability"),
        ("availability", "injuries"),
        nested_path=("injuries",),
    )
    availability_depth_enabled = _signal_enabled(
        config,
        ("availability_config", "availability"),
        ("availability", "depth_charts"),
        nested_path=("depth_charts",),
    )
    availability_usage_enabled = _signal_enabled(
        config,
        ("availability_config", "availability"),
        ("availability", "usage_fallback"),
        nested_path=("usage_fallback",),
    )
    role_trend_enabled = _signal_enabled(
        config,
        ("role_trend_config", "role_trend"),
        ("role_trend",),
    )
...
        "availability": _build_signal(
            availability_enabled,
            seasons,
            _covered_seasons_from_required_paths(
                seasons,
                {
                    season: [
                        cache_path / f"rosters_weekly_{season}.parquet",
                        cache_path / f"depth_charts_{season}.parquet",
                    ]
                    for season in seasons
                },
            ),
            note="Explicit coverage requires rosters_weekly plus depth_charts cache; injuries can further refine hard decisions when present",
        ),
        "availability.injuries": _build_signal(
            availability_enabled and availability_injuries_enabled,
            seasons,
            _covered_seasons_from_required_paths(
                seasons,
                {season: [cache_path / f"injuries_{season}.parquet"] for season in seasons},
            ),
            note="Hard injury availability decisions require cached injuries parquet for the tested season",
        ),
        "availability.depth_charts": _build_signal(
            availability_enabled and availability_depth_enabled,
            seasons,
            _covered_seasons_from_required_paths(
                seasons,
                {season: [cache_path / f"depth_charts_{season}.parquet"] for season in seasons},
            ),
            note="Hard starter and promotion decisions require cached depth_charts parquet for the tested season",
        ),
        "availability.usage_fallback": _build_signal(
            availability_enabled and availability_usage_enabled,
            seasons,
            _covered_seasons_from_required_paths(
                seasons,
                {
                    season: [
                        cache_path / f"player_stats_week_{season}.parquet",
                        cache_path / f"snap_counts_{season}.parquet",
                        cache_path / f"rosters_weekly_{season}.parquet",
                    ]
                    for season in seasons
                },
            ),
            note="Soft-only fallback requires player_stats_week, snap_counts, and rosters_weekly parquet coverage",
        ),
        "role_trend": _build_signal(
            role_trend_enabled,
            seasons,
            _covered_seasons_from_required_paths(
                seasons,
                {season: [cache_path / f"player_stats_week_{season}.parquet"] for season in seasons},
            ),
            note="Role trend uses weekly player_stats coverage; snap_counts can augment but do not create hard decisions",
        ),
```

- [ ] **Step 4: Run the role-trend pipeline and coverage tests**

Run: `uv run pytest tests/test_scoring/test_role_trend.py tests/test_validation/test_role_trend_pipeline.py tests/test_validation/test_coverage.py tests/test_validation/test_backtester.py -v`

Expected: PASS with verified projection-layer order and new Phase 2 coverage statuses.

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/cli.py src/fantasy_sim/validation/backtester.py scripts/validate.py src/fantasy_sim/validation/coverage.py tests/test_scoring/test_role_trend.py tests/test_validation/test_role_trend_pipeline.py tests/test_validation/test_coverage.py
git commit -m "feat: wire role trend through projection layers"
```

### Task 7: Update The Canonical Docs And Prepare Manual Validation Handoff

**Files:**
- Modify: `docs/accuracy-roadmap.md`
- Modify: `docs/accuracy-stack-audit.md`

- [ ] **Step 1: Write the doc assertions first**

Before editing the docs, add this checklist to the top of your scratchpad for the task and verify each item against the code you just shipped:

```text
Roadmap must reflect:
- Phase 2 implementation status
- hybrid availability + role_trend design
- per-position gating via positions lists
- next priority after Phase 2
- any deferred scope for participation/tracking

Audit must reflect:
- current defaults for availability and role_trend
- runtime order includes availability before usage and role_trend before ensemble
- ff_opportunity local cache correction for 2022-2024
- props path correction to ~/.fantasy-sim/pff/props
- verified-loader vs locally-cached distinction for injuries / depth charts / participation
- v1 rule: usage-only evidence is soft-only and cannot create inactive/starter-out decisions
```

- [ ] **Step 2: Update the roadmap with implementation status and manual-validation ownership**

Modify `docs/accuracy-roadmap.md` so Phase 2 explicitly says:

```markdown
### Status

Implemented in code, pending manual A/B validation by the user before any
default-promotion decision.

### Phase 2 v1 shape

- hybrid design:
  - `availability` pre-sim
  - `role_trend` post-sim
- QB/RB/WR/TE all modeled
- per-position gating through config `positions` lists
- hard availability changes require explicit signals
- usage-only evidence can only soften confidence or damp projections in v1

### Validation ownership

All Phase 2 A/B runs are executed manually by the user.
This repo change adds the implementation and the validation plumbing, but the
promotion artifact is created only after user-run validation.
```

- [ ] **Step 3: Update the audit with corrected cache notes and Phase 2 caveats**

Modify `docs/accuracy-stack-audit.md` so the relevant sections say:

```markdown
- `ff_opportunity` local cache exists for 2022-2024 under
  `~/.fantasy-sim/cache/ff_opportunity_weekly_<season>.parquet`
- props historical parquet exists only for 2025 under
  `~/.fantasy-sim/pff/props`
- `load_injuries()`, `load_depth_charts()`, and `load_participation()` are
  verified upstream loaders, but local historical trust differs by source

### Phase 2 Runtime Order

1. base team distributions and player models
2. vegas
3. availability
4. usage
5. props
6. matchup
7. tier / team context
8. coverage
9. DST baseline
10. kicker
11. TD tendency
12. weather
13. runtime game script
14. overrides
15. post-sim role_trend
16. post-sim ensemble

### Phase 2 Caveat

Hard availability changes require explicit signals.
Usage-only evidence can down-weight confidence or slightly damp projections,
but it does not create inactive or starter-out decisions by itself in v1.
```

- [ ] **Step 4: Hand the manual validation commands to the user without running them**

Do **not** execute these commands. Add them to your final handoff message after implementation:

```bash
uv run python scripts/validate.py --baseline defaults --set availability.enabled=true --label "phase-2-availability-only"
uv run python scripts/validate.py --baseline defaults --set role_trend.enabled=true --label "phase-2-role-trend-only"
uv run python scripts/validate.py --baseline defaults --set availability.enabled=true --set role_trend.enabled=true --label "phase-2-combined"
uv run python scripts/validate.py --baseline defaults --set availability.enabled=true --set availability.positions=[QB] --label "phase-2-availability-qb-only"
uv run python scripts/validate.py --baseline defaults --set role_trend.enabled=true --set role_trend.positions=[WR] --label "phase-2-role-trend-wr-only"
```

The user owns all of these runs.

- [ ] **Step 5: Commit the doc updates**

```bash
git add docs/accuracy-roadmap.md docs/accuracy-stack-audit.md
git commit -m "docs: update phase 2 roadmap and audit state"
```

## Self-Review

- Spec coverage:
  - hybrid split is implemented in Tasks 3-6
  - hard explicit-signal rule is implemented in Task 3
  - all four positions with `positions` gating are implemented in Tasks 1, 3, and 5
  - validation coverage additions are implemented in Task 6
  - roadmap/audit updates are implemented in Task 7
  - manual A/B ownership is implemented in Task 7
- Placeholder scan:
  - no placeholder markers remain
- Type consistency:
  - `availability_config` and `role_trend_config` are the names used consistently in config loading, builder threading, and pipeline integration

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-11-phase-2-role-and-availability-engine.md`. Two execution options:

1. Subagent-Driven (recommended) - I dispatch a fresh subagent per task, review between tasks, fast iteration

2. Inline Execution - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?

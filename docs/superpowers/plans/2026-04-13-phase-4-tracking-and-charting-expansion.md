# Phase 4 Tracking And Charting Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a new pre-sim `tracking` family for QB/RB/WR/TE, backfill its required `2022-2024` inputs, validate each slice marginally, and update the roadmap/audit docs so they remain the canonical handoff for future accuracy work.

**Architecture:** Add a top-level `tracking` config family, explicit `DataLoader` wrappers for participation / FTN charting / NGS passing / NGS rushing, and a `TrackingInputLoader` that creates leak-free player-week aggregates by joining play-level sources to PBP on game/play IDs. Keep tracking pre-sim inside `GameContextBuilder` between `usage` and `props`, implement the three slices as separate modules (`receiver_participation`, `rb_efficiency`, `qb_context`), and extend validation coverage so each slice can be promoted or parked independently.

**Tech Stack:** Python 3.12+, polars, dataclasses, pathlib, Click, pytest

**Spec:** `docs/superpowers/specs/2026-04-13-phase-4-tracking-and-charting-expansion-design.md`

---

### Task 1: Add The `tracking` Config Family

**Files:**
- Create: `src/fantasy_sim/data/tracking/__init__.py`
- Create: `src/fantasy_sim/data/tracking/models.py`
- Create: `src/fantasy_sim/data/tracking/config.py`
- Modify: `config/defaults.yaml`
- Modify: `src/fantasy_sim/validation/config.py`
- Test: `tests/test_data/test_tracking/test_config.py`
- Test: `tests/test_validation/test_config.py`

- [ ] **Step 1: Write the failing config tests**

Create `tests/test_data/test_tracking/test_config.py`:

```python
"""Tests for tracking config loading."""

from fantasy_sim.data.tracking.config import load_tracking_config


def test_load_tracking_config_defaults_when_missing():
    cfg = load_tracking_config({})

    assert cfg.enabled is False
    assert cfg.window_weeks == 4
    assert cfg.receiver_participation.enabled is True
    assert cfg.receiver_participation.positions == ("WR", "TE")
    assert cfg.rb_efficiency.enabled is True
    assert cfg.qb_context.enabled is True


def test_load_tracking_config_reads_nested_values():
    cfg = load_tracking_config(
        {
            "tracking": {
                "enabled": True,
                "window_weeks": 5,
                "receiver_participation": {
                    "enabled": True,
                    "positions": ["WR", "TE"],
                    "target_share_sensitivity": 0.18,
                    "air_yards_sensitivity": 0.12,
                    "catchable_target_sensitivity": 0.08,
                    "contested_target_sensitivity": -0.04,
                    "factor_clamp": [0.92, 1.08],
                    "min_targets": 8,
                },
                "rb_efficiency": {
                    "enabled": True,
                    "carry_share_sensitivity": 0.10,
                    "rush_yards_sensitivity": 0.08,
                    "factor_clamp": [0.93, 1.07],
                    "min_attempts": 12,
                },
                "qb_context": {
                    "enabled": True,
                    "pass_rate_sensitivity": 0.04,
                    "pace_sensitivity": 0.03,
                    "scramble_sensitivity": 0.06,
                    "sack_rate_sensitivity": 0.05,
                    "factor_clamp": [0.94, 1.06],
                    "min_dropbacks": 20,
                },
            }
        }
    )

    assert cfg.enabled is True
    assert cfg.window_weeks == 5
    assert cfg.receiver_participation.target_share_sensitivity == 0.18
    assert cfg.receiver_participation.factor_clamp == (0.92, 1.08)
    assert cfg.rb_efficiency.min_attempts == 12
    assert cfg.qb_context.min_dropbacks == 20
```

Add this test to `tests/test_validation/test_config.py`:

```python
def test_defaults_include_disabled_tracking_config_until_phase4_promotion():
    defaults = load_defaults()

    configs = build_engine_configs(defaults)

    assert "tracking_config" in configs
    assert configs["tracking_config"] is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_data/test_tracking/test_config.py tests/test_validation/test_config.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'fantasy_sim.data.tracking'`

- [ ] **Step 3: Implement the config models, loader, and validation wiring**

Create `src/fantasy_sim/data/tracking/__init__.py`:

```python
"""Tracking/charting configuration and engines."""

from fantasy_sim.data.tracking.config import load_tracking_config
from fantasy_sim.data.tracking.models import (
    QbContextConfig,
    RbEfficiencyConfig,
    ReceiverParticipationConfig,
    TrackingConfig,
)

__all__ = [
    "TrackingConfig",
    "ReceiverParticipationConfig",
    "RbEfficiencyConfig",
    "QbContextConfig",
    "load_tracking_config",
]
```

Create `src/fantasy_sim/data/tracking/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ReceiverParticipationConfig:
    enabled: bool = True
    positions: tuple[str, ...] = ("WR", "TE")
    target_share_sensitivity: float = 0.18
    air_yards_sensitivity: float = 0.12
    catchable_target_sensitivity: float = 0.08
    contested_target_sensitivity: float = -0.04
    factor_clamp: tuple[float, float] = (0.92, 1.08)
    min_targets: int = 8


@dataclass
class RbEfficiencyConfig:
    enabled: bool = True
    carry_share_sensitivity: float = 0.10
    rush_yards_sensitivity: float = 0.08
    factor_clamp: tuple[float, float] = (0.93, 1.07)
    min_attempts: int = 12


@dataclass
class QbContextConfig:
    enabled: bool = True
    pass_rate_sensitivity: float = 0.04
    pace_sensitivity: float = 0.03
    scramble_sensitivity: float = 0.06
    sack_rate_sensitivity: float = 0.05
    factor_clamp: tuple[float, float] = (0.94, 1.06)
    min_dropbacks: int = 20


@dataclass
class TrackingConfig:
    enabled: bool = False
    window_weeks: int = 4
    receiver_participation: ReceiverParticipationConfig = field(
        default_factory=ReceiverParticipationConfig
    )
    rb_efficiency: RbEfficiencyConfig = field(default_factory=RbEfficiencyConfig)
    qb_context: QbContextConfig = field(default_factory=QbContextConfig)
```

Create `src/fantasy_sim/data/tracking/config.py`:

```python
from __future__ import annotations

from fantasy_sim.data.tracking.models import (
    QbContextConfig,
    RbEfficiencyConfig,
    ReceiverParticipationConfig,
    TrackingConfig,
)


def load_tracking_config(defaults: dict) -> TrackingConfig:
    raw = defaults.get("tracking")
    if not raw:
        return TrackingConfig(enabled=False)

    receiver_raw = raw.get("receiver_participation", {})
    rb_raw = raw.get("rb_efficiency", {})
    qb_raw = raw.get("qb_context", {})

    return TrackingConfig(
        enabled=raw.get("enabled", False),
        window_weeks=int(raw.get("window_weeks", 4)),
        receiver_participation=ReceiverParticipationConfig(
            enabled=receiver_raw.get("enabled", True),
            positions=tuple(receiver_raw.get("positions", ["WR", "TE"])),
            target_share_sensitivity=float(
                receiver_raw.get("target_share_sensitivity", 0.18)
            ),
            air_yards_sensitivity=float(
                receiver_raw.get("air_yards_sensitivity", 0.12)
            ),
            catchable_target_sensitivity=float(
                receiver_raw.get("catchable_target_sensitivity", 0.08)
            ),
            contested_target_sensitivity=float(
                receiver_raw.get("contested_target_sensitivity", -0.04)
            ),
            factor_clamp=tuple(receiver_raw.get("factor_clamp", [0.92, 1.08])),
            min_targets=int(receiver_raw.get("min_targets", 8)),
        ),
        rb_efficiency=RbEfficiencyConfig(
            enabled=rb_raw.get("enabled", True),
            carry_share_sensitivity=float(
                rb_raw.get("carry_share_sensitivity", 0.10)
            ),
            rush_yards_sensitivity=float(
                rb_raw.get("rush_yards_sensitivity", 0.08)
            ),
            factor_clamp=tuple(rb_raw.get("factor_clamp", [0.93, 1.07])),
            min_attempts=int(rb_raw.get("min_attempts", 12)),
        ),
        qb_context=QbContextConfig(
            enabled=qb_raw.get("enabled", True),
            pass_rate_sensitivity=float(qb_raw.get("pass_rate_sensitivity", 0.04)),
            pace_sensitivity=float(qb_raw.get("pace_sensitivity", 0.03)),
            scramble_sensitivity=float(qb_raw.get("scramble_sensitivity", 0.06)),
            sack_rate_sensitivity=float(qb_raw.get("sack_rate_sensitivity", 0.05)),
            factor_clamp=tuple(qb_raw.get("factor_clamp", [0.94, 1.06])),
            min_dropbacks=int(qb_raw.get("min_dropbacks", 20)),
        ),
    )
```

Add this block to `config/defaults.yaml` immediately after `usage`:

```yaml
tracking:
  enabled: false
  window_weeks: 4
  receiver_participation:
    enabled: true
    positions: [WR, TE]
    target_share_sensitivity: 0.18
    air_yards_sensitivity: 0.12
    catchable_target_sensitivity: 0.08
    contested_target_sensitivity: -0.04
    factor_clamp: [0.92, 1.08]
    min_targets: 8
  rb_efficiency:
    enabled: true
    carry_share_sensitivity: 0.10
    rush_yards_sensitivity: 0.08
    factor_clamp: [0.93, 1.07]
    min_attempts: 12
  qb_context:
    enabled: true
    pass_rate_sensitivity: 0.04
    pace_sensitivity: 0.03
    scramble_sensitivity: 0.06
    sack_rate_sensitivity: 0.05
    factor_clamp: [0.94, 1.06]
    min_dropbacks: 20
```

Modify `src/fantasy_sim/validation/config.py`:

```python
from fantasy_sim.data.tracking.config import load_tracking_config
```

and inside `build_engine_configs()`:

```python
    tracking = load_tracking_config(config)
```

and include it in the return dict:

```python
        "tracking_config": tracking if tracking.enabled else None,
```

and in `build_bare_engine_configs()`:

```python
        "tracking_config": None,
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_data/test_tracking/test_config.py tests/test_validation/test_config.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add config/defaults.yaml src/fantasy_sim/data/tracking/__init__.py src/fantasy_sim/data/tracking/models.py src/fantasy_sim/data/tracking/config.py src/fantasy_sim/validation/config.py tests/test_data/test_tracking/test_config.py tests/test_validation/test_config.py
git commit -m "feat: add tracking config family"
```

### Task 2: Add Source Loaders And An Explicit Backfill Script

**Files:**
- Modify: `src/fantasy_sim/data/loader.py`
- Create: `scripts/backfill_tracking_data.py`
- Test: `tests/test_data/test_tracking/test_source_loader.py`
- Test: `tests/test_scripts/test_backfill_tracking_data.py`

- [ ] **Step 1: Write the failing loader and script tests**

Create `tests/test_data/test_tracking/test_source_loader.py`:

```python
from pathlib import Path
from unittest.mock import patch

import polars as pl

from fantasy_sim.data.loader import DataLoader


def _sample_df() -> pl.DataFrame:
    return pl.DataFrame({"season": [2024], "week": [1]})


@patch("fantasy_sim.data.loader.nflreadpy")
def test_load_participation_caches_by_season(mock_nfl, tmp_path):
    mock_nfl.load_participation.return_value = _sample_df()
    loader = DataLoader(cache_dir=tmp_path)

    first = loader.load_participation([2024])
    second = loader.load_participation([2024])

    assert first.shape == (1, 2)
    assert second.shape == (1, 2)
    mock_nfl.load_participation.assert_called_once_with([2024])
    assert (tmp_path / "participation_2024.parquet").exists()


@patch("fantasy_sim.data.loader.nflreadpy")
def test_load_ftn_charting_caches_by_season(mock_nfl, tmp_path):
    mock_nfl.load_ftn_charting.return_value = _sample_df()
    loader = DataLoader(cache_dir=tmp_path)

    loader.load_ftn_charting([2024])

    mock_nfl.load_ftn_charting.assert_called_once_with([2024])
    assert (tmp_path / "ftn_charting_2024.parquet").exists()
```

Create `tests/test_scripts/test_backfill_tracking_data.py`:

```python
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch


def _load_script_module():
    script_path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "backfill_tracking_data.py"
    )
    spec = importlib.util.spec_from_file_location(
        "backfill_tracking_data_under_test",
        script_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_backfill_tracking_data_loads_all_required_sources():
    module = _load_script_module()
    loader = MagicMock()

    with patch.object(module, "DataLoader", return_value=loader):
        module.main(["--seasons", "2022", "2023"])

    loader.load_participation.assert_any_call([2022])
    loader.load_participation.assert_any_call([2023])
    loader.load_ftn_charting.assert_any_call([2022])
    loader.load_ftn_charting.assert_any_call([2023])
    loader.load_nextgen_stats.assert_any_call([2022], stat_type="passing")
    loader.load_nextgen_stats.assert_any_call([2022], stat_type="rushing")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_data/test_tracking/test_source_loader.py tests/test_scripts/test_backfill_tracking_data.py -v`

Expected: FAIL with `AttributeError: 'DataLoader' object has no attribute 'load_participation'`

- [ ] **Step 3: Implement the new `DataLoader` methods and backfill script**

Add these methods to `src/fantasy_sim/data/loader.py`:

```python
    def load_participation(self, seasons: list[int]) -> pl.DataFrame:
        cache_path = self._cache_key("participation", seasons)
        cached = self._load_cached(cache_path)
        if cached is not None:
            return cached
        df = nflreadpy.load_participation(seasons)
        self._save_cache(df, cache_path)
        return df

    def load_ftn_charting(self, seasons: list[int]) -> pl.DataFrame:
        cache_path = self._cache_key("ftn_charting", seasons)
        cached = self._load_cached(cache_path)
        if cached is not None:
            return cached
        df = nflreadpy.load_ftn_charting(seasons)
        self._save_cache(df, cache_path)
        return df
```

Create `scripts/backfill_tracking_data.py`:

```python
from __future__ import annotations

import argparse

from fantasy_sim.data.loader import DataLoader


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seasons", nargs="+", type=int, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    loader = DataLoader()

    for season in args.seasons:
        print(f"[tracking] backfilling season {season}")
        loader.load_participation([season])
        print(f"[tracking] wrote participation_{season}.parquet")
        loader.load_ftn_charting([season])
        print(f"[tracking] wrote ftn_charting_{season}.parquet")
        loader.load_nextgen_stats([season], stat_type="passing")
        print(f"[tracking] wrote ngs_passing_{season}.parquet")
        loader.load_nextgen_stats([season], stat_type="rushing")
        print(f"[tracking] wrote ngs_rushing_{season}.parquet")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_data/test_tracking/test_source_loader.py tests/test_scripts/test_backfill_tracking_data.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/loader.py scripts/backfill_tracking_data.py tests/test_data/test_tracking/test_source_loader.py tests/test_scripts/test_backfill_tracking_data.py
git commit -m "feat: add tracking data loaders and backfill script"
```

### Task 3: Build The Canonical `TrackingInputLoader`

**Files:**
- Create: `src/fantasy_sim/data/tracking/loader.py`
- Test: `tests/test_data/test_tracking/test_inputs_loader.py`

- [ ] **Step 1: Write the failing aggregate-loader tests**

Create `tests/test_data/test_tracking/test_inputs_loader.py`:

```python
from unittest.mock import MagicMock

import polars as pl

from fantasy_sim.data.tracking.loader import TrackingInputLoader


def test_receiver_features_join_ftn_flags_to_targeted_receiver():
    loader = MagicMock()
    loader.load_pbp.return_value = pl.DataFrame(
        {
            "season": [2024, 2024],
            "week": [1, 2],
            "game_id": ["g1", "g2"],
            "play_id": [11, 22],
            "posteam": ["KC", "KC"],
            "receiver_player_id": ["wr1", "wr1"],
            "air_yards": [12.0, 18.0],
            "pass_attempt": [1, 1],
            "complete_pass": [1, 0],
        }
    )
    loader.load_ftn_charting.return_value = pl.DataFrame(
        {
            "nflverse_game_id": ["g1", "g2"],
            "nflverse_play_id": [11, 22],
            "is_catchable_ball": [True, False],
            "is_contested_ball": [False, True],
            "is_no_huddle": [False, True],
        }
    )
    tracking = TrackingInputLoader(loader=loader, window_weeks=4)

    result = tracking.load_receiver_features(season=2024, week=3)

    row = result.row(0, named=True)
    assert row["player_id"] == "wr1"
    assert row["team"] == "KC"
    assert row["targets"] == 2
    assert row["catchable_rate"] == 0.5
    assert row["contested_rate"] == 0.5


def test_qb_features_use_strict_week_less_than_target_week():
    loader = MagicMock()
    loader.load_pbp.return_value = pl.DataFrame(
        {
            "season": [2024, 2024],
            "week": [4, 5],
            "game_id": ["g4", "g5"],
            "play_id": [40, 50],
            "posteam": ["BUF", "BUF"],
            "passer_player_id": ["qb1", "qb1"],
            "pass_attempt": [1, 1],
        }
    )
    loader.load_participation.return_value = pl.DataFrame(
        {
            "nflverse_game_id": ["g4", "g5"],
            "play_id": [40, 50],
            "was_pressure": [True, False],
            "number_of_pass_rushers": [5, 4],
        }
    )
    loader.load_ftn_charting.return_value = pl.DataFrame(
        {
            "nflverse_game_id": ["g4", "g5"],
            "nflverse_play_id": [40, 50],
            "is_no_huddle": [True, False],
            "is_play_action": [False, True],
            "n_blitzers": [5, 4],
        }
    )
    loader.load_nextgen_stats.return_value = pl.DataFrame(
        {
            "season": [2024],
            "week": [4],
            "player_gsis_id": ["qb1"],
            "avg_time_to_throw": [2.7],
            "aggressiveness": [0.18],
            "completion_percentage_above_expectation": [4.5],
            "attempts": [30],
        }
    )
    tracking = TrackingInputLoader(loader=loader, window_weeks=4)

    result = tracking.load_qb_features(season=2024, week=5)

    assert result.select("dropbacks").item() == 1
    assert result.select("pressure_rate").item() == 1.0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_data/test_tracking/test_inputs_loader.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'fantasy_sim.data.tracking.loader'`

- [ ] **Step 3: Implement the canonical feature loader**

Create `src/fantasy_sim/data/tracking/loader.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field

import polars as pl

from fantasy_sim.data.loader import DataLoader


@dataclass
class TrackingInputLoader:
    loader: DataLoader = field(default_factory=DataLoader)
    window_weeks: int = 4
    _cache: dict[tuple[str, int, int], pl.DataFrame] = field(default_factory=dict)

    def _joined_pbp_ftn(self, season: int) -> pl.DataFrame:
        pbp = self.loader.load_pbp([season])
        ftn = self.loader.load_ftn_charting([season]).rename(
            {
                "nflverse_game_id": "game_id",
                "nflverse_play_id": "play_id",
            }
        )
        return pbp.join(ftn, on=["game_id", "play_id"], how="left")

    def load_receiver_features(self, season: int, week: int) -> pl.DataFrame:
        joined = self._joined_pbp_ftn(season).filter(
            (pl.col("season") == season)
            & (pl.col("week") < week)
            & pl.col("receiver_player_id").is_not_null()
            & (pl.col("pass_attempt") == 1)
        )
        if joined.is_empty():
            return pl.DataFrame(
                schema={
                    "team": pl.Utf8,
                    "player_id": pl.Utf8,
                    "targets": pl.Int64,
                    "catchable_rate": pl.Float64,
                    "contested_rate": pl.Float64,
                    "mean_air_yards": pl.Float64,
                }
            )

        return (
            joined.group_by(["posteam", "receiver_player_id"])
            .agg(
                [
                    pl.len().alias("targets"),
                    pl.col("is_catchable_ball").cast(pl.Float64).mean().alias("catchable_rate"),
                    pl.col("is_contested_ball").cast(pl.Float64).mean().alias("contested_rate"),
                    pl.col("air_yards").fill_null(0.0).mean().alias("mean_air_yards"),
                ]
            )
            .rename({"posteam": "team", "receiver_player_id": "player_id"})
        )

    def load_rb_features(self, season: int, week: int) -> pl.DataFrame:
        joined = self._joined_pbp_ftn(season).filter(
            (pl.col("season") == season)
            & (pl.col("week") < week)
            & pl.col("rusher_player_id").is_not_null()
            & (pl.col("rush_attempt") == 1)
        )
        ngs = self.loader.load_nextgen_stats([season], stat_type="rushing").filter(
            (pl.col("season") == season) & (pl.col("week") < week)
        )
        rb_base = (
            joined.group_by(["posteam", "rusher_player_id"])
            .agg(
                [
                    pl.len().alias("attempts"),
                    pl.col("is_no_huddle").cast(pl.Float64).mean().alias("no_huddle_rate"),
                    pl.col("is_play_action").cast(pl.Float64).mean().alias("play_action_rate"),
                ]
            )
            .rename({"posteam": "team", "rusher_player_id": "player_id"})
        )
        if ngs.is_empty():
            return rb_base.with_columns(
                pl.lit(0.0).alias("rush_yoe_per_att")
            )

        ngs_agg = (
            ngs.group_by("player_gsis_id")
            .agg(
                [
                    pl.col("rush_yards_over_expected_per_att").mean().alias(
                        "rush_yoe_per_att"
                    ),
                ]
            )
            .rename({"player_gsis_id": "player_id"})
        )
        return rb_base.join(ngs_agg, on="player_id", how="left").with_columns(
            pl.col("rush_yoe_per_att").fill_null(0.0)
        )

    def load_qb_features(self, season: int, week: int) -> pl.DataFrame:
        pbp = self.loader.load_pbp([season]).filter(
            (pl.col("season") == season)
            & (pl.col("week") < week)
            & pl.col("passer_player_id").is_not_null()
            & (pl.col("pass_attempt") == 1)
        )
        participation = self.loader.load_participation([season]).rename(
            {"nflverse_game_id": "game_id"}
        )
        joined = pbp.join(
            participation.select(["game_id", "play_id", "was_pressure", "number_of_pass_rushers"]),
            on=["game_id", "play_id"],
            how="left",
        )
        joined = joined.join(
            self.loader.load_ftn_charting([season]).rename(
                {"nflverse_game_id": "game_id", "nflverse_play_id": "play_id"}
            ),
            on=["game_id", "play_id"],
            how="left",
        )
        ngs = self.loader.load_nextgen_stats([season], stat_type="passing").filter(
            (pl.col("season") == season) & (pl.col("week") < week)
        )

        qb_base = (
            joined.group_by(["posteam", "passer_player_id"])
            .agg(
                [
                    pl.len().alias("dropbacks"),
                    pl.col("was_pressure").cast(pl.Float64).mean().alias("pressure_rate"),
                    pl.col("is_no_huddle").cast(pl.Float64).mean().alias("no_huddle_rate"),
                    pl.col("is_play_action").cast(pl.Float64).mean().alias("play_action_rate"),
                    (pl.col("n_blitzers").fill_null(0) >= 5).cast(pl.Float64).mean().alias("blitz_rate"),
                ]
            )
            .rename({"posteam": "team", "passer_player_id": "player_id"})
        )
        if ngs.is_empty():
            return qb_base.with_columns(
                [
                    pl.lit(0.0).alias("avg_time_to_throw"),
                    pl.lit(0.0).alias("aggressiveness"),
                    pl.lit(0.0).alias("cpoe"),
                ]
            )

        ngs_agg = (
            ngs.group_by("player_gsis_id")
            .agg(
                [
                    pl.col("avg_time_to_throw").mean().alias("avg_time_to_throw"),
                    pl.col("aggressiveness").mean().alias("aggressiveness"),
                    pl.col("completion_percentage_above_expectation").mean().alias("cpoe"),
                ]
            )
            .rename({"player_gsis_id": "player_id"})
        )
        return qb_base.join(ngs_agg, on="player_id", how="left").with_columns(
            [
                pl.col("avg_time_to_throw").fill_null(0.0),
                pl.col("aggressiveness").fill_null(0.0),
                pl.col("cpoe").fill_null(0.0),
            ]
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_data/test_tracking/test_inputs_loader.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/tracking/loader.py tests/test_data/test_tracking/test_inputs_loader.py
git commit -m "feat: add tracking input aggregates"
```

### Task 4: Implement The WR/TE `receiver_participation` Slice

**Files:**
- Create: `src/fantasy_sim/data/tracking/receiver_participation.py`
- Test: `tests/test_data/test_tracking/test_receiver_participation.py`

- [ ] **Step 1: Write the failing receiver-slice tests**

Create `tests/test_data/test_tracking/test_receiver_participation.py`:

```python
import numpy as np
import polars as pl

from fantasy_sim.data.tracking.models import ReceiverParticipationConfig
from fantasy_sim.data.tracking.receiver_participation import ReceiverParticipationEngine
from fantasy_sim.models.player import PlayerModel, PlayerOutcomes, PlayerUsage, TeamRoster


def _receiver(player_id: str, position: str) -> PlayerModel:
    return PlayerModel(
        player_id=player_id,
        name=player_id,
        position=position,
        team="KC",
        usage=PlayerUsage(target_share=0.20, air_yards_share=0.18),
        outcomes=PlayerOutcomes(catch_rate=0.65, receiving_yards_dist=np.array([8.0, 12.0])),
    )


def test_receiver_engine_boosts_wr_target_share_and_catch_rate():
    roster = TeamRoster(team="KC", players=[_receiver("wr1", "WR")])
    features = pl.DataFrame(
        {
            "team": ["KC"],
            "player_id": ["wr1"],
            "targets": [12],
            "catchable_rate": [0.80],
            "contested_rate": [0.10],
            "mean_air_yards": [14.0],
        }
    )
    engine = ReceiverParticipationEngine(ReceiverParticipationConfig())

    engine.apply(roster, features)

    player = roster.players[0]
    assert player.usage.target_share > 0.20
    assert player.usage.air_yards_share > 0.18
    assert player.outcomes.catch_rate > 0.65


def test_receiver_engine_respects_te_position_and_min_targets():
    roster = TeamRoster(team="KC", players=[_receiver("te1", "TE")])
    features = pl.DataFrame(
        {
            "team": ["KC"],
            "player_id": ["te1"],
            "targets": [4],
            "catchable_rate": [0.90],
            "contested_rate": [0.20],
            "mean_air_yards": [7.0],
        }
    )
    config = ReceiverParticipationConfig(min_targets=8)
    engine = ReceiverParticipationEngine(config)

    engine.apply(roster, features)

    player = roster.players[0]
    assert player.usage.target_share == 0.20
    assert player.outcomes.catch_rate == 0.65
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_data/test_tracking/test_receiver_participation.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'fantasy_sim.data.tracking.receiver_participation'`

- [ ] **Step 3: Implement the WR/TE slice**

Create `src/fantasy_sim/data/tracking/receiver_participation.py`:

```python
from __future__ import annotations

import numpy as np
import polars as pl

from fantasy_sim.data.tracking.models import ReceiverParticipationConfig
from fantasy_sim.models.player import TeamRoster


def _bounded_factor(value: float, baseline: float, sensitivity: float, clamp: tuple[float, float]) -> float:
    if baseline <= 0:
        return 1.0
    factor = 1.0 + ((value / baseline) - 1.0) * sensitivity
    return max(clamp[0], min(clamp[1], factor))


class ReceiverParticipationEngine:
    def __init__(self, config: ReceiverParticipationConfig) -> None:
        self._config = config

    def apply(self, roster: TeamRoster, features: pl.DataFrame) -> None:
        if not self._config.enabled or features.is_empty():
            return

        baseline_catchable = float(features.select(pl.col("catchable_rate").mean()).item() or 0.0)
        baseline_contested = float(features.select(pl.col("contested_rate").mean()).item() or 0.0)
        baseline_air = float(features.select(pl.col("mean_air_yards").mean()).item() or 0.0)

        for player in roster.players:
            if player.position not in self._config.positions:
                continue

            row = features.filter(
                (pl.col("team") == roster.team) & (pl.col("player_id") == player.player_id)
            )
            if row.is_empty():
                continue
            target_count = int(row.select(pl.col("targets")).item())
            if target_count < self._config.min_targets:
                continue

            catchable = float(row.select(pl.col("catchable_rate")).item())
            contested = float(row.select(pl.col("contested_rate")).item())
            air = float(row.select(pl.col("mean_air_yards")).item())

            target_factor = _bounded_factor(
                catchable,
                baseline_catchable,
                self._config.target_share_sensitivity,
                self._config.factor_clamp,
            )
            air_factor = _bounded_factor(
                air,
                baseline_air,
                self._config.air_yards_sensitivity,
                self._config.factor_clamp,
            )
            catch_factor = _bounded_factor(
                contested,
                baseline_contested if baseline_contested > 0 else 1.0,
                self._config.contested_target_sensitivity,
                self._config.factor_clamp,
            ) * _bounded_factor(
                catchable,
                baseline_catchable,
                self._config.catchable_target_sensitivity,
                self._config.factor_clamp,
            )

            player.usage.target_share *= target_factor
            player.usage.air_yards_share *= air_factor
            player.outcomes.catch_rate *= catch_factor
            if player.outcomes.receiving_yards_dist is not None:
                player.outcomes.receiving_yards_dist = np.round(
                    player.outcomes.receiving_yards_dist * air_factor
                ).astype(float)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_data/test_tracking/test_receiver_participation.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/tracking/receiver_participation.py tests/test_data/test_tracking/test_receiver_participation.py
git commit -m "feat: add tracking receiver participation slice"
```

### Task 5: Implement The RB `rb_efficiency` Slice

**Files:**
- Create: `src/fantasy_sim/data/tracking/rb_efficiency.py`
- Test: `tests/test_data/test_tracking/test_rb_efficiency.py`

- [ ] **Step 1: Write the failing RB-slice tests**

Create `tests/test_data/test_tracking/test_rb_efficiency.py`:

```python
import numpy as np
import polars as pl

from fantasy_sim.data.tracking.models import RbEfficiencyConfig
from fantasy_sim.data.tracking.rb_efficiency import RbEfficiencyEngine
from fantasy_sim.models.player import PlayerModel, PlayerOutcomes, PlayerUsage, TeamRoster


def test_rb_efficiency_boosts_carry_share_and_rush_yards_dist():
    rb = PlayerModel(
        player_id="rb1",
        name="RB 1",
        position="RB",
        team="BUF",
        usage=PlayerUsage(carry_share=0.55),
        outcomes=PlayerOutcomes(rushing_yards_dist=np.array([3.0, 5.0, 7.0])),
    )
    roster = TeamRoster(team="BUF", players=[rb])
    features = pl.DataFrame(
        {
            "team": ["BUF"],
            "player_id": ["rb1"],
            "attempts": [18],
            "rush_yoe_per_att": [1.4],
            "no_huddle_rate": [0.22],
            "play_action_rate": [0.28],
        }
    )

    engine = RbEfficiencyEngine(RbEfficiencyConfig())
    engine.apply(roster, features)

    assert rb.usage.carry_share > 0.55
    assert rb.outcomes.rushing_yards_dist.mean() > 5.0


def test_rb_efficiency_skips_players_below_min_attempts():
    rb = PlayerModel(
        player_id="rb2",
        name="RB 2",
        position="RB",
        team="BUF",
        usage=PlayerUsage(carry_share=0.25),
        outcomes=PlayerOutcomes(rushing_yards_dist=np.array([2.0, 4.0])),
    )
    roster = TeamRoster(team="BUF", players=[rb])
    features = pl.DataFrame(
        {
            "team": ["BUF"],
            "player_id": ["rb2"],
            "attempts": [6],
            "rush_yoe_per_att": [2.0],
            "no_huddle_rate": [0.10],
            "play_action_rate": [0.12],
        }
    )

    engine = RbEfficiencyEngine(RbEfficiencyConfig(min_attempts=12))
    engine.apply(roster, features)

    assert rb.usage.carry_share == 0.25
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_data/test_tracking/test_rb_efficiency.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'fantasy_sim.data.tracking.rb_efficiency'`

- [ ] **Step 3: Implement the RB slice**

Create `src/fantasy_sim/data/tracking/rb_efficiency.py`:

```python
from __future__ import annotations

import numpy as np
import polars as pl

from fantasy_sim.data.tracking.models import RbEfficiencyConfig
from fantasy_sim.models.player import TeamRoster


def _bounded_factor(value: float, baseline: float, sensitivity: float, clamp: tuple[float, float]) -> float:
    if baseline == 0:
        return 1.0
    factor = 1.0 + ((value / baseline) - 1.0) * sensitivity
    return max(clamp[0], min(clamp[1], factor))


class RbEfficiencyEngine:
    def __init__(self, config: RbEfficiencyConfig) -> None:
        self._config = config

    def apply(self, roster: TeamRoster, features: pl.DataFrame) -> None:
        if not self._config.enabled or features.is_empty():
            return

        baseline_yoe = float(features.select(pl.col("rush_yoe_per_att").mean()).item() or 0.0)

        for player in roster.players:
            if player.position != "RB":
                continue
            row = features.filter(
                (pl.col("team") == roster.team) & (pl.col("player_id") == player.player_id)
            )
            if row.is_empty():
                continue
            attempts = int(row.select(pl.col("attempts")).item())
            if attempts < self._config.min_attempts:
                continue

            rush_yoe = float(row.select(pl.col("rush_yoe_per_att")).item())
            carry_factor = _bounded_factor(
                rush_yoe,
                baseline_yoe if baseline_yoe != 0 else 1.0,
                self._config.carry_share_sensitivity,
                self._config.factor_clamp,
            )
            yards_factor = _bounded_factor(
                rush_yoe,
                baseline_yoe if baseline_yoe != 0 else 1.0,
                self._config.rush_yards_sensitivity,
                self._config.factor_clamp,
            )

            player.usage.carry_share *= carry_factor
            if player.outcomes.rushing_yards_dist is not None:
                player.outcomes.rushing_yards_dist = np.round(
                    player.outcomes.rushing_yards_dist * yards_factor
                ).astype(float)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_data/test_tracking/test_rb_efficiency.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/tracking/rb_efficiency.py tests/test_data/test_tracking/test_rb_efficiency.py
git commit -m "feat: add tracking rb efficiency slice"
```

### Task 6: Implement The QB `qb_context` Slice

**Files:**
- Create: `src/fantasy_sim/data/tracking/qb_context.py`
- Test: `tests/test_data/test_tracking/test_qb_context.py`

- [ ] **Step 1: Write the failing QB-slice tests**

Create `tests/test_data/test_tracking/test_qb_context.py`:

```python
import numpy as np
import polars as pl

from fantasy_sim.data.tracking.models import QbContextConfig
from fantasy_sim.data.tracking.qb_context import QbContextEngine
from fantasy_sim.engine.types import TeamDistributions
from fantasy_sim.models.distributions import DriveStartModel, KickingModel, PlayCallingDist, PlayOutcomeDist, TurnoverRates
from fantasy_sim.models.player import PlayerModel, PlayerOutcomes, PlayerUsage, TeamRoster


def _team_dists() -> TeamDistributions:
    return TeamDistributions(
        play_calling=PlayCallingDist(team="KC", distributions={}, default={"pass": 0.57, "run": 0.43}),
        play_outcomes=PlayOutcomeDist(distributions={}, defaults={"pass": np.array([6.0, 8.0]), "run": np.array([3.0])}),
        turnover_rates=TurnoverRates(team="KC", int_rate=0.025, fumble_rate=0.01, sack_rate=0.07, sack_fumble_rate=0.10),
        kicking=KickingModel(fg_make_rate={"0_39": 0.9, "40_49": 0.8, "50_plus": 0.7}, xp_rate=0.95),
        drive_start=DriveStartModel(touchback_rate=0.6, touchback_yardline=75, return_yardlines=np.array([72.0])),
    )


def test_qb_context_updates_pass_rate_pace_and_scramble():
    qb = PlayerModel(
        player_id="qb1",
        name="QB 1",
        position="QB",
        team="KC",
        usage=PlayerUsage(snap_share=1.0, scramble_rate=0.06),
        outcomes=PlayerOutcomes(scramble_yards_dist=np.array([3.0, 5.0, 8.0])),
    )
    roster = TeamRoster(team="KC", players=[qb])
    dists = _team_dists()
    features = pl.DataFrame(
        {
            "team": ["KC"],
            "player_id": ["qb1"],
            "dropbacks": [28],
            "pressure_rate": [0.22],
            "blitz_rate": [0.30],
            "no_huddle_rate": [0.18],
            "play_action_rate": [0.27],
            "avg_time_to_throw": [2.9],
            "aggressiveness": [0.17],
            "cpoe": [4.2],
        }
    )

    engine = QbContextEngine(QbContextConfig())
    engine.apply(roster, dists, features)

    assert dists.pace_factor != 1.0
    assert dists.play_calling.default["pass"] != 0.57
    assert dists.turnover_rates.sack_rate != 0.07
    assert qb.usage.scramble_rate != 0.06


def test_qb_context_skips_below_min_dropbacks():
    qb = PlayerModel(
        player_id="qb2",
        name="QB 2",
        position="QB",
        team="KC",
        usage=PlayerUsage(snap_share=1.0, scramble_rate=0.05),
        outcomes=PlayerOutcomes(scramble_yards_dist=np.array([4.0])),
    )
    roster = TeamRoster(team="KC", players=[qb])
    dists = _team_dists()
    features = pl.DataFrame(
        {
            "team": ["KC"],
            "player_id": ["qb2"],
            "dropbacks": [10],
            "pressure_rate": [0.30],
            "blitz_rate": [0.34],
            "no_huddle_rate": [0.12],
            "play_action_rate": [0.15],
            "avg_time_to_throw": [3.0],
            "aggressiveness": [0.20],
            "cpoe": [1.0],
        }
    )

    engine = QbContextEngine(QbContextConfig(min_dropbacks=20))
    engine.apply(roster, dists, features)

    assert dists.play_calling.default["pass"] == 0.57
    assert qb.usage.scramble_rate == 0.05
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_data/test_tracking/test_qb_context.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'fantasy_sim.data.tracking.qb_context'`

- [ ] **Step 3: Implement the QB slice**

Create `src/fantasy_sim/data/tracking/qb_context.py`:

```python
from __future__ import annotations

import polars as pl

from fantasy_sim.data.tracking.models import QbContextConfig
from fantasy_sim.engine.types import TeamDistributions
from fantasy_sim.models.player import TeamRoster


def _bounded_factor(value: float, baseline: float, sensitivity: float, clamp: tuple[float, float]) -> float:
    if baseline == 0:
        return 1.0
    factor = 1.0 + ((value / baseline) - 1.0) * sensitivity
    return max(clamp[0], min(clamp[1], factor))


class QbContextEngine:
    def __init__(self, config: QbContextConfig) -> None:
        self._config = config

    def apply(self, roster: TeamRoster, team_dists: TeamDistributions, features: pl.DataFrame) -> None:
        if not self._config.enabled or features.is_empty():
            return

        row = features.filter(pl.col("team") == roster.team)
        if row.is_empty():
            return
        dropbacks = int(row.select(pl.col("dropbacks")).item())
        if dropbacks < self._config.min_dropbacks:
            return

        pressure = float(row.select(pl.col("pressure_rate")).item())
        blitz = float(row.select(pl.col("blitz_rate")).item())
        no_huddle = float(row.select(pl.col("no_huddle_rate")).item())
        play_action = float(row.select(pl.col("play_action_rate")).item())

        pace_factor = _bounded_factor(
            no_huddle + play_action,
            0.25,
            self._config.pace_sensitivity,
            self._config.factor_clamp,
        )
        pass_factor = _bounded_factor(
            play_action,
            0.20,
            self._config.pass_rate_sensitivity,
            self._config.factor_clamp,
        )
        scramble_factor = _bounded_factor(
            pressure + blitz,
            0.45,
            self._config.scramble_sensitivity,
            self._config.factor_clamp,
        )
        sack_factor = _bounded_factor(
            pressure,
            0.20,
            self._config.sack_rate_sensitivity,
            self._config.factor_clamp,
        )

        team_dists.pace_factor *= pace_factor
        team_dists.play_calling.default["pass"] *= pass_factor
        team_dists.play_calling.default["run"] = max(
            0.0,
            1.0 - team_dists.play_calling.default["pass"],
        )
        team_dists.turnover_rates.sack_rate *= sack_factor

        qb = roster.get_starting_qb()
        qb.usage.scramble_rate *= scramble_factor
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_data/test_tracking/test_qb_context.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/tracking/qb_context.py tests/test_data/test_tracking/test_qb_context.py
git commit -m "feat: add tracking qb context slice"
```

### Task 7: Wire The Tracking Family Through Runtime And Validation

**Files:**
- Create: `src/fantasy_sim/data/tracking/engine.py`
- Modify: `src/fantasy_sim/data/game_context.py`
- Modify: `src/fantasy_sim/cli.py`
- Modify: `src/fantasy_sim/validation/parallel.py`
- Modify: `src/fantasy_sim/validation/backtester.py`
- Modify: `src/fantasy_sim/validation/coverage.py`
- Modify: `tests/test_data/test_tracking/test_game_context.py`
- Modify: `tests/test_validation/test_config.py`
- Modify: `tests/test_validation/test_parallel.py`
- Modify: `tests/test_validation/test_backtester.py`
- Modify: `tests/test_validation/test_validate_script.py`
- Modify: `tests/test_validation/test_market_history_pipeline.py`
- Modify: `tests/test_validation/test_role_trend_pipeline.py`
- Modify: `tests/test_validation/test_coverage.py`

- [ ] **Step 1: Write the failing integration and coverage tests**

Create `tests/test_data/test_tracking/test_game_context.py`:

```python
from unittest.mock import MagicMock, patch

import numpy as np

from fantasy_sim.data.game_context import GameContextBuilder
from fantasy_sim.data.tracking.models import TrackingConfig
from fantasy_sim.data.usage.models import UsageConfig
from fantasy_sim.engine.types import TeamDistributions
from fantasy_sim.models.distributions import DriveStartModel, KickingModel, PlayCallingDist, PlayOutcomeDist, TurnoverRates
from fantasy_sim.models.player import PlayerModel, PlayerOutcomes, PlayerUsage, TeamRoster


def _dists(team: str) -> TeamDistributions:
    return TeamDistributions(
        play_calling=PlayCallingDist(team=team, distributions={}, default={"pass": 0.57, "run": 0.43}),
        play_outcomes=PlayOutcomeDist(distributions={}, defaults={"pass": np.array([7.0]), "run": np.array([4.0])}),
        turnover_rates=TurnoverRates(team=team, int_rate=0.02, fumble_rate=0.01, sack_rate=0.06, sack_fumble_rate=0.1),
        kicking=KickingModel(fg_make_rate={"0_39": 0.9, "40_49": 0.8, "50_plus": 0.7}, xp_rate=0.95),
        drive_start=DriveStartModel(touchback_rate=0.6, touchback_yardline=75, return_yardlines=np.array([72.0])),
    )


def _roster(team: str) -> TeamRoster:
    return TeamRoster(
        team=team,
        players=[PlayerModel(f"{team}_QB", "QB", "QB", team, PlayerUsage(snap_share=1.0), PlayerOutcomes())],
    )


def test_build_game_applies_tracking_between_usage_and_props(tmp_path):
    builder = GameContextBuilder(
        cache_dir=tmp_path / "cache",
        usage_config=UsageConfig(enabled=True),
        tracking_config=TrackingConfig(enabled=True),
    )
    builder.build_team_distributions = MagicMock(side_effect=[_dists("KC"), _dists("BUF")])
    builder.build_team_roster = MagicMock(side_effect=[_roster("KC"), _roster("BUF")])
    builder._usage_engine = MagicMock()
    builder._tracking_engine = MagicMock()
    builder._props_engine = MagicMock()

    events: list[str] = []
    builder._usage_engine.apply.side_effect = lambda *args, **kwargs: events.append("usage") or {}
    builder._tracking_engine.apply.side_effect = lambda *args, **kwargs: events.append("tracking")
    builder._props_engine.apply.side_effect = lambda *args, **kwargs: events.append("props")

    with patch("fantasy_sim.data.player_builder._normalize_roster_shares"):
        builder.build_game("KC", "BUF", training_seasons=[2024], target_season=2024, week=1)

    assert events == ["usage", "usage", "tracking", "tracking", "props", "props"]
```

Add this assertion to `tests/test_validation/test_coverage.py`:

```python
    assert coverage["tracking.receiver_participation"].status == "full"
    assert coverage["tracking.rb_efficiency"].status == "full"
    assert coverage["tracking.qb_context"].status == "full"
```

In `tests/test_validation/test_market_history_pipeline.py`,
`tests/test_validation/test_role_trend_pipeline.py`, and
`tests/test_validation/test_validate_script.py`, add `'tracking_config': None`
to each hardcoded engine-config dict used in validation-path tests.

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
uv run pytest tests/test_data/test_tracking/test_game_context.py tests/test_validation/test_coverage.py tests/test_validation/test_parallel.py tests/test_validation/test_backtester.py tests/test_validation/test_validate_script.py tests/test_validation/test_market_history_pipeline.py tests/test_validation/test_role_trend_pipeline.py -v
```

Expected: FAIL with `TypeError` about unexpected `tracking_config` arguments or missing `tracking` coverage keys

- [ ] **Step 3: Implement the family orchestrator, runtime wiring, and coverage**

Create `src/fantasy_sim/data/tracking/engine.py`:

```python
from __future__ import annotations

from fantasy_sim.data.tracking.loader import TrackingInputLoader
from fantasy_sim.data.tracking.models import TrackingConfig
from fantasy_sim.data.tracking.qb_context import QbContextEngine
from fantasy_sim.data.tracking.rb_efficiency import RbEfficiencyEngine
from fantasy_sim.data.tracking.receiver_participation import ReceiverParticipationEngine


class TrackingEngine:
    def __init__(self, config: TrackingConfig, loader: TrackingInputLoader | None = None) -> None:
        self._config = config
        self._loader = loader or TrackingInputLoader(window_weeks=config.window_weeks)
        self._receiver_engine = ReceiverParticipationEngine(config.receiver_participation)
        self._rb_engine = RbEfficiencyEngine(config.rb_efficiency)
        self._qb_engine = QbContextEngine(config.qb_context)

    def apply(self, roster, team_dists, season: int, week: int) -> None:
        if not self._config.enabled or week <= 1:
            return
        if self._config.receiver_participation.enabled:
            receiver_df = self._loader.load_receiver_features(season, week)
            self._receiver_engine.apply(roster, receiver_df)
        if self._config.rb_efficiency.enabled:
            rb_df = self._loader.load_rb_features(season, week)
            self._rb_engine.apply(roster, rb_df)
        if self._config.qb_context.enabled:
            qb_df = self._loader.load_qb_features(season, week)
            self._qb_engine.apply(roster, team_dists, qb_df)
```

Modify `src/fantasy_sim/data/game_context.py`:

```python
from fantasy_sim.data.tracking.models import TrackingConfig
```

Add the new constructor parameter:

```python
        tracking_config: TrackingConfig | None = None,
```

Add engine setup:

```python
        self._tracking_engine = None
        self._tracking_config = tracking_config or TrackingConfig(enabled=False)
        if self._tracking_config.enabled:
            from fantasy_sim.data.tracking.engine import TrackingEngine
            self._tracking_engine = TrackingEngine(self._tracking_config)
```

Insert this block between usage and props:

```python
        if getattr(self, "_tracking_engine", None) is not None and target_season and week:
            from fantasy_sim.data.player_builder import _normalize_roster_shares

            self._tracking_engine.apply(home_roster, home_dists, target_season, week)
            self._tracking_engine.apply(away_roster, away_dists, target_season, week)
            _normalize_roster_shares(home_roster)
            _normalize_roster_shares(away_roster)
```

Modify `src/fantasy_sim/cli.py`:

```python
from fantasy_sim.data.tracking.config import load_tracking_config
```

In `_make_builder()`:

```python
    tracking_config = load_tracking_config(defaults)
```

and pass it into `GameContextBuilder(...)`:

```python
        tracking_config=tracking_config,
```

In `backtest(...)`, load the config from defaults and pass it into `Backtester(...)`:

```python
    tracking_config = load_tracking_config(defaults)
```

```python
        tracking_config=tracking_config,
```

Modify `src/fantasy_sim/validation/backtester.py`:

```python
from fantasy_sim.data.tracking.models import TrackingConfig
```

Add the constructor parameter and store it:

```python
        tracking_config: TrackingConfig | None = None,
```

```python
        self._tracking_config = tracking_config
```

and pass it into `build_games_parallel(...)`:

```python
            tracking_config=self._tracking_config,
```

Modify `src/fantasy_sim/validation/parallel.py`:

- import `TrackingConfig` in the `TYPE_CHECKING` block
- add `tracking_config` to:
  - `_init_build_worker_single`
  - `_init_build_worker_dual`
  - `_create_builders`
  - `_build_games_sequential`
  - `build_games_parallel`
- forward it into every `GameContextBuilder(...)` call

Modify `src/fantasy_sim/validation/coverage.py`:

- add a `DEFAULT_CACHE_DIR`-based coverage check for:
  - `participation_<season>.parquet`
  - `ftn_charting_<season>.parquet`
  - `ngs_passing_<season>.parquet`
  - `ngs_rushing_<season>.parquet`
- add three slice keys:

```python
        "tracking.receiver_participation": _build_signal(
            tracking_enabled and receiver_enabled,
            _covered_seasons_from_required_paths(
                seasons,
                {
                    season: [
                        cache_dir / f"ftn_charting_{season}.parquet",
                        cache_dir / f"pbp_{season}.parquet",
                    ]
                    for season in seasons
                },
            ),
            seasons,
            note="Requires FTN charting plus season PBP for targeted-receiver joins",
        ),
```

```python
        "tracking.rb_efficiency": _build_signal(
            tracking_enabled and rb_enabled,
            _covered_seasons_from_required_paths(
                seasons,
                {
                    season: [
                        cache_dir / f"ftn_charting_{season}.parquet",
                        cache_dir / f"ngs_rushing_{season}.parquet",
                        cache_dir / f"pbp_{season}.parquet",
                    ]
                    for season in seasons
                },
            ),
            seasons,
            note="Requires FTN charting, rushing NGS, and season PBP",
        ),
```

```python
        "tracking.qb_context": _build_signal(
            tracking_enabled and qb_enabled,
            _covered_seasons_from_required_paths(
                seasons,
                {
                    season: [
                        cache_dir / f"participation_{season}.parquet",
                        cache_dir / f"ftn_charting_{season}.parquet",
                        cache_dir / f"ngs_passing_{season}.parquet",
                        cache_dir / f"pbp_{season}.parquet",
                    ]
                    for season in seasons
                },
            ),
            seasons,
            note="Requires participation, FTN charting, passing NGS, and season PBP",
        ),
```

and a family-level signal:

```python
    tracking_signals["tracking"] = _build_signal(
        tracking_enabled,
        _intersect_enabled_coverage(seasons, tracking_signals.values()),
        seasons,
        note="Phase 4 family-level coverage is the intersection of enabled tracking slices",
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```bash
uv run pytest tests/test_data/test_tracking/test_game_context.py tests/test_validation/test_config.py tests/test_validation/test_coverage.py tests/test_validation/test_parallel.py tests/test_validation/test_backtester.py tests/test_validation/test_validate_script.py tests/test_validation/test_market_history_pipeline.py tests/test_validation/test_role_trend_pipeline.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/tracking/engine.py src/fantasy_sim/data/game_context.py src/fantasy_sim/cli.py src/fantasy_sim/validation/parallel.py src/fantasy_sim/validation/backtester.py src/fantasy_sim/validation/coverage.py tests/test_data/test_tracking/test_game_context.py tests/test_validation/test_config.py tests/test_validation/test_coverage.py tests/test_validation/test_parallel.py tests/test_validation/test_backtester.py tests/test_validation/test_validate_script.py tests/test_validation/test_market_history_pipeline.py tests/test_validation/test_role_trend_pipeline.py
git commit -m "feat: wire tracking through runtime and validation"
```

### Task 8: Run The Phase 4 Slice Artifacts And Update The Roadmap/Audit

**Files:**
- Modify: `docs/accuracy-roadmap.md`
- Modify: `docs/accuracy-stack-audit.md`

- [ ] **Step 1: Backfill the required `2022-2024` tracking inputs**

Run:

```bash
uv run python scripts/backfill_tracking_data.py --seasons 2022 2023 2024
```

Expected lines:

```text
[tracking] wrote participation_2022.parquet
[tracking] wrote ftn_charting_2022.parquet
[tracking] wrote ngs_passing_2022.parquet
[tracking] wrote ngs_rushing_2022.parquet
```

and equivalent lines for `2023` and `2024`.

- [ ] **Step 2: Run the three isolated marginal validation artifacts**

Run the WR/TE slice:

```bash
uv run python scripts/validate.py \
  --baseline defaults \
  --set tracking.enabled=true \
  --set tracking.receiver_participation.enabled=true \
  --set tracking.rb_efficiency.enabled=false \
  --set tracking.qb_context.enabled=false \
  --sims 50 \
  --label "phase-4-receiver-participation-v1"
```

Run the RB slice:

```bash
uv run python scripts/validate.py \
  --baseline defaults \
  --set tracking.enabled=true \
  --set tracking.receiver_participation.enabled=false \
  --set tracking.rb_efficiency.enabled=true \
  --set tracking.qb_context.enabled=false \
  --sims 50 \
  --label "phase-4-rb-efficiency-v1"
```

Run the QB slice:

```bash
uv run python scripts/validate.py \
  --baseline defaults \
  --set tracking.enabled=true \
  --set tracking.receiver_participation.enabled=false \
  --set tracking.rb_efficiency.enabled=false \
  --set tracking.qb_context.enabled=true \
  --sims 50 \
  --label "phase-4-qb-context-v1"
```

Expected coverage lines:

```text
tracking.receiver_participation=full(2022,2023,2024)
tracking.rb_efficiency=full(2022,2023,2024)
tracking.qb_context=full(2022,2023,2024)
```

- [ ] **Step 3: Only if the isolated slices are positive or neutral without interaction-risk regressions, run the optional combined bundle**

Run:

```bash
uv run python scripts/validate.py \
  --baseline defaults \
  --set tracking.enabled=true \
  --set tracking.receiver_participation.enabled=true \
  --set tracking.rb_efficiency.enabled=true \
  --set tracking.qb_context.enabled=true \
  --sims 50 \
  --label "phase-4-tracking-bundle-v1"
```

Expected:

- the standard marginal-lift summary
- coverage lines showing `tracking=full(2022,2023,2024)` if all three slices are covered

- [ ] **Step 4: Update `docs/accuracy-roadmap.md` with the cumulative Phase 4 state**

Replace the Phase 4 section so it records:

```markdown
## Phase 4: Tracking And Charting Expansion

### Status

Implemented in staged v1 slices with explicit marginal validation artifacts.

Current Phase 4 artifacts:

- `phase-4-receiver-participation-v1`
- `phase-4-rb-efficiency-v1`
- `phase-4-qb-context-v1`
```

If the bundle was run, add:

```markdown
- `phase-4-tracking-bundle-v1`
```

Add this exact promotion rule text:

```markdown
Phase 4 promotion rule:

- promote only if at least one of QB/RB/WR/TE improves materially
- require the other core positions to hold without material regression
- do not promote on flat "everything merely held" evidence
```

Then paste under each artifact:

- the line that starts with `rank_corr delta:`
- the line that starts with `weekly_mae delta:`
- the line that starts with `season_mae delta:`

Update the next-priority note so the roadmap says:

```markdown
If the isolated Phase 4 slices are positive but the combined bundle regresses,
keep the slices independent and move next to Phase 5 only after the final
Phase 4 default set is explicit.
```

- [ ] **Step 5: Update `docs/accuracy-stack-audit.md` with the new defaults, data coverage, and fixed caveats**

Make these exact content changes:

1. In `## Current Defaults`, add the tracking family:

```markdown
- `tracking.enabled: false`
- `tracking.receiver_participation.enabled: true`
- `tracking.rb_efficiency.enabled: true`
- `tracking.qb_context.enabled: true`
```

If any slice is promoted default-on, change `tracking.enabled: false` to
`tracking.enabled: true` and add the exact promoted slice state.

2. In `## Runtime Order`, insert:

```markdown
4. Tracking engine
```

so the order reads:

```markdown
2. Vegas game environment
3. Availability engine
4. Usage engine
5. Tracking engine
6. Player props
```

and add:

```markdown
- `tracking` is pre-sim only and runs after `usage` but before `props`
- `tracking` is coverage-aware and degrades slice-by-slice to neutral when
  required inputs are missing
```

3. In `## Local Data Inventory`, add:

```markdown
- tracking cache files under `~/.fantasy-sim/cache/`:
  - `participation_<season>.parquet`
  - `ftn_charting_<season>.parquet`
  - `ngs_passing_<season>.parquet`
  - `ngs_rushing_<season>.parquet`
```

4. In `## Verified Loaders Vs Local Cache State`, replace the old future-only
wording for participation / FTN with:

```markdown
- participation: wrapped in `DataLoader` and cached locally by season
- FTN charting: wrapped in `DataLoader` and cached locally by season
- NGS passing/rushing: wrapped through `load_nextgen_stats(..., stat_type=...)`
  and cached locally by season
```

5. In the caveats section, remove the stale caveat that participation and FTN
are verified-only surfaces, and replace it with:

```markdown
### Tracking evidence must be interpreted slice-by-slice

Phase 4 is intentionally staged:

- `tracking.receiver_participation`
- `tracking.rb_efficiency`
- `tracking.qb_context`

The combined `tracking` verdict should only be trusted if the isolated slice
artifacts are already understood.
```

- [ ] **Step 6: Run the focused verification and commit the docs**

Run:

```bash
uv run pytest tests/test_data/test_tracking tests/test_validation/test_config.py tests/test_validation/test_coverage.py tests/test_validation/test_parallel.py tests/test_validation/test_backtester.py tests/test_validation/test_validate_script.py tests/test_validation/test_market_history_pipeline.py tests/test_validation/test_role_trend_pipeline.py -v
```

Expected: PASS

Then commit:

```bash
git add docs/accuracy-roadmap.md docs/accuracy-stack-audit.md
git commit -m "docs: record phase 4 tracking status"
```

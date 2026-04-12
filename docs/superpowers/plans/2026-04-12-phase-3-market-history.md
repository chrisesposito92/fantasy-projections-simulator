# Phase 3 Market History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a coverage-gated `market_history` post-sim layer for `2023-2024` historical market inputs, wire it through validation/backtest/non-detail CLI flows, and make market-specific evaluation explicitly covered-season-only so uncovered `2022` is reported as no-data rather than treated as neutral.

**Architecture:** Add a new `market_history` config family, a processed local store under `~/.fantasy-sim/market-history/processed`, a small importer/loader/normalizer keyed by nflverse `player_id`, and a post-sim projection adjuster inserted between `role_trend` and `ensemble.ff_opportunity`. Keep `GameContextBuilder` unchanged, keep `vegas.props` intact, and extend validation/ledger coverage reporting so Phase 3 promotion decisions are based only on covered-season evidence.

**Tech Stack:** Python 3.12+, polars, pathlib, dataclasses, argparse, pytest

**Spec:** `docs/superpowers/specs/2026-04-12-phase-3-market-history-design.md`

---

### Task 1: Add The `market_history` Config Family

**Files:**
- Create: `src/fantasy_sim/data/market_history/__init__.py`
- Create: `src/fantasy_sim/data/market_history/models.py`
- Create: `src/fantasy_sim/data/market_history/config.py`
- Modify: `config/defaults.yaml:241-257`
- Test: `tests/test_data/test_market_history/test_config.py`

- [ ] **Step 1: Write the failing config tests**

Create `tests/test_data/test_market_history/test_config.py`:

```python
"""Tests for market-history config loading."""

from fantasy_sim.data.market_history.config import load_market_history_config


def test_load_market_history_config_defaults_when_missing():
    cfg = load_market_history_config({})

    assert cfg.enabled is False
    assert cfg.data_dir is None
    assert cfg.positions == ("QB", "RB", "WR", "TE")
    assert cfg.weights == {
        "QB": 0.20,
        "RB": 0.15,
        "WR": 0.20,
        "TE": 0.15,
    }
    assert cfg.min_coverage_weeks == 1
    assert cfg.min_books == 2
    assert cfg.dispersion_scale == 3.0
    assert cfg.features.close_fpts is True
    assert cfg.features.open_fpts is True
    assert cfg.features.movement is True
    assert cfg.features.dispersion is True
    assert cfg.features.anytime_td is True


def test_load_market_history_config_reads_nested_values():
    cfg = load_market_history_config(
        {
            "market_history": {
                "enabled": True,
                "data_dir": "/tmp/market-history",
                "positions": ["QB", "WR", "TE"],
                "weights": {
                    "QB": 0.30,
                    "RB": 0.10,
                    "WR": 0.25,
                    "TE": 0.20,
                },
                "min_coverage_weeks": 2,
                "min_books": 3,
                "dispersion_scale": 4.5,
                "features": {
                    "close_fpts": True,
                    "open_fpts": False,
                    "movement": True,
                    "dispersion": False,
                    "anytime_td": True,
                },
            }
        }
    )

    assert cfg.enabled is True
    assert cfg.data_dir == "/tmp/market-history"
    assert cfg.positions == ("QB", "WR", "TE")
    assert cfg.weights == {
        "QB": 0.30,
        "RB": 0.10,
        "WR": 0.25,
        "TE": 0.20,
    }
    assert cfg.min_coverage_weeks == 2
    assert cfg.min_books == 3
    assert cfg.dispersion_scale == 4.5
    assert cfg.features.close_fpts is True
    assert cfg.features.open_fpts is False
    assert cfg.features.movement is True
    assert cfg.features.dispersion is False
    assert cfg.features.anytime_td is True


def test_default_positions_all_have_default_weights():
    cfg = load_market_history_config({})
    assert all(position in cfg.weights for position in cfg.positions)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_data/test_market_history/test_config.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'fantasy_sim.data.market_history'`

- [ ] **Step 3: Implement the config models and loader**

Create `src/fantasy_sim/data/market_history/__init__.py`:

```python
"""Historical market-intelligence configuration models and loaders."""

from fantasy_sim.data.market_history.config import load_market_history_config
from fantasy_sim.data.market_history.models import (
    MarketHistoryConfig,
    MarketHistoryFeatureFlags,
)

__all__ = [
    "MarketHistoryConfig",
    "MarketHistoryFeatureFlags",
    "load_market_history_config",
]
```

Create `src/fantasy_sim/data/market_history/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MarketHistoryFeatureFlags:
    close_fpts: bool = True
    open_fpts: bool = True
    movement: bool = True
    dispersion: bool = True
    anytime_td: bool = True


@dataclass
class MarketHistoryConfig:
    enabled: bool = False
    data_dir: str | None = None
    positions: tuple[str, ...] = ("QB", "RB", "WR", "TE")
    weights: dict[str, float] = field(
        default_factory=lambda: {
            "QB": 0.20,
            "RB": 0.15,
            "WR": 0.20,
            "TE": 0.15,
        }
    )
    min_coverage_weeks: int = 1
    min_books: int = 2
    dispersion_scale: float = 3.0
    features: MarketHistoryFeatureFlags = field(
        default_factory=MarketHistoryFeatureFlags
    )
```

Create `src/fantasy_sim/data/market_history/config.py`:

```python
from __future__ import annotations

from fantasy_sim.data.market_history.models import (
    MarketHistoryConfig,
    MarketHistoryFeatureFlags,
)


def load_market_history_config(defaults: dict) -> MarketHistoryConfig:
    raw = defaults.get("market_history")
    if not raw:
        return MarketHistoryConfig(enabled=False)

    feature_raw = raw.get("features", {})

    return MarketHistoryConfig(
        enabled=raw.get("enabled", False),
        data_dir=raw.get("data_dir"),
        positions=tuple(raw.get("positions", ["QB", "RB", "WR", "TE"])),
        weights=dict(
            raw.get(
                "weights",
                {"QB": 0.20, "RB": 0.15, "WR": 0.20, "TE": 0.15},
            )
        ),
        min_coverage_weeks=int(raw.get("min_coverage_weeks", 1)),
        min_books=int(raw.get("min_books", 2)),
        dispersion_scale=float(raw.get("dispersion_scale", 3.0)),
        features=MarketHistoryFeatureFlags(
            close_fpts=feature_raw.get("close_fpts", True),
            open_fpts=feature_raw.get("open_fpts", True),
            movement=feature_raw.get("movement", True),
            dispersion=feature_raw.get("dispersion", True),
            anytime_td=feature_raw.get("anytime_td", True),
        ),
    )
```

Add this block to `config/defaults.yaml` immediately after `ensemble`:

```yaml
market_history:
  enabled: false
  data_dir: null
  positions: [QB, RB, WR, TE]
  weights:
    QB: 0.20
    RB: 0.15
    WR: 0.20
    TE: 0.15
  min_coverage_weeks: 1
  min_books: 2
  dispersion_scale: 3.0
  features:
    close_fpts: true
    open_fpts: true
    movement: true
    dispersion: true
    anytime_td: true
```

- [ ] **Step 4: Run the config tests**

Run: `uv run pytest tests/test_data/test_market_history/test_config.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add config/defaults.yaml src/fantasy_sim/data/market_history/__init__.py src/fantasy_sim/data/market_history/models.py src/fantasy_sim/data/market_history/config.py tests/test_data/test_market_history/test_config.py
git commit -m "feat: add market history config family"
```

### Task 2: Add The Historical Market Cache, Importer, Loader, And Feature Normalizer

**Files:**
- Create: `src/fantasy_sim/data/market_history/importer.py`
- Create: `src/fantasy_sim/data/market_history/loader.py`
- Create: `src/fantasy_sim/data/market_history/features.py`
- Create: `scripts/import_market_history.py`
- Test: `tests/test_data/test_market_history/test_loader.py`
- Test: `tests/test_data/test_market_history/test_features.py`

- [ ] **Step 1: Write the failing importer, loader, and feature tests**

Create `tests/test_data/test_market_history/test_loader.py`:

```python
from pathlib import Path

import polars as pl

from fantasy_sim.data.market_history.importer import build_market_history_cache
from fantasy_sim.data.market_history.loader import (
    MarketHistoryLoader,
    PROCESSED_WEEKLY_SCHEMA,
)
from fantasy_sim.data.market_history.models import MarketHistoryConfig


def _raw_week_frame(season: int, week: int, *, player_id: str = "QB1") -> pl.DataFrame:
    return pl.DataFrame(
        {
            "season": [season],
            "week": [week],
            "player_id": [player_id],
            "full_name": ["QB One"],
            "position": ["QB"],
            "team": ["KC"],
            "open_fpts": [18.0],
            "close_fpts": [19.0],
            "books": [3],
            "line_stddev": [1.0],
            "anytime_td_prob": [0.10],
        }
    )


def test_build_market_history_cache_combines_weeks_into_one_season_file(tmp_path):
    raw_root = tmp_path / "raw" / "2023"
    raw_root.mkdir(parents=True)
    _raw_week_frame(2023, 1).write_parquet(raw_root / "week01.parquet")
    _raw_week_frame(2023, 2).write_parquet(raw_root / "week02.parquet")

    output_path = build_market_history_cache(
        2023,
        raw_dir=tmp_path / "raw",
        processed_dir=tmp_path / "processed",
    )

    frame = pl.read_parquet(output_path)

    assert output_path.name == "market_history_weekly_2023.parquet"
    assert frame["week"].to_list() == [1, 2]
    assert frame["player_id"].to_list() == ["QB1", "QB1"]


def test_loader_returns_empty_processed_schema_when_file_is_missing(tmp_path):
    loader = MarketHistoryLoader(
        MarketHistoryConfig(enabled=True, data_dir=str(tmp_path))
    )

    frame = loader.load_weekly([2023])

    assert frame.schema == PROCESSED_WEEKLY_SCHEMA
    assert frame.is_empty()


def test_loader_reads_multiple_seasons_from_processed_store(tmp_path):
    processed = tmp_path / "processed"
    processed.mkdir()
    _raw_week_frame(2023, 1).write_parquet(
        processed / "market_history_weekly_2023.parquet"
    )
    _raw_week_frame(2024, 1, player_id="QB2").write_parquet(
        processed / "market_history_weekly_2024.parquet"
    )

    loader = MarketHistoryLoader(
        MarketHistoryConfig(enabled=True, data_dir=str(processed))
    )
    frame = loader.load_weekly([2023, 2024]).sort(["season", "player_id"])

    assert frame["season"].to_list() == [2023, 2024]
    assert frame["player_id"].to_list() == ["QB1", "QB2"]
```

Create `tests/test_data/test_market_history/test_features.py`:

```python
import polars as pl

from fantasy_sim.data.market_history.features import normalize_market_history
from fantasy_sim.data.market_history.models import MarketHistoryConfig


def test_normalize_market_history_builds_adjusted_prior_and_confidence():
    frame = pl.DataFrame(
        {
            "season": [2024],
            "week": [1],
            "player_id": ["QB1"],
            "full_name": ["QB One"],
            "position": ["QB"],
            "team": ["KC"],
            "open_fpts": [16.0],
            "close_fpts": [18.0],
            "books": [4],
            "line_stddev": [1.0],
            "anytime_td_prob": [0.50],
        }
    )

    normalized = normalize_market_history(frame, MarketHistoryConfig(enabled=True))
    row = normalized.row(0, named=True)

    assert row["prior_fpts"] == 18.0
    assert row["line_move"] == 2.0
    assert round(row["adjusted_prior_fpts"], 2) == 18.5
    assert round(row["confidence_factor"], 4) == 0.7667


def test_normalize_market_history_filters_positions_not_in_scope():
    frame = pl.DataFrame(
        {
            "season": [2024],
            "week": [1],
            "player_id": ["K1"],
            "full_name": ["K One"],
            "position": ["K"],
            "team": ["KC"],
            "open_fpts": [8.0],
            "close_fpts": [8.5],
            "books": [3],
            "line_stddev": [0.2],
            "anytime_td_prob": [None],
        }
    )

    normalized = normalize_market_history(frame, MarketHistoryConfig(enabled=True))

    assert normalized.is_empty()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_data/test_market_history/test_loader.py tests/test_data/test_market_history/test_features.py -v`

Expected: FAIL with missing importer, loader, and feature modules

- [ ] **Step 3: Implement the importer, loader, and normalizer**

Create `src/fantasy_sim/data/market_history/loader.py`:

```python
from __future__ import annotations

from pathlib import Path

import polars as pl

from fantasy_sim.data.market_history.models import MarketHistoryConfig

DEFAULT_MARKET_HISTORY_PROCESSED_DIR = (
    Path.home() / ".fantasy-sim" / "market-history" / "processed"
)

PROCESSED_WEEKLY_SCHEMA: dict[str, pl.DataType] = {
    "season": pl.Int64,
    "week": pl.Int64,
    "player_id": pl.Utf8,
    "full_name": pl.Utf8,
    "position": pl.Utf8,
    "team": pl.Utf8,
    "open_fpts": pl.Float64,
    "close_fpts": pl.Float64,
    "books": pl.Int64,
    "line_stddev": pl.Float64,
    "anytime_td_prob": pl.Float64,
}


class MarketHistoryLoader:
    """Load processed historical market snapshots from per-season parquet."""

    def __init__(
        self,
        config: MarketHistoryConfig | None = None,
        data_dir: Path | None = None,
    ) -> None:
        self.config = config or MarketHistoryConfig()
        if data_dir is not None:
            self.data_dir = Path(data_dir)
        elif self.config.data_dir:
            self.data_dir = Path(self.config.data_dir)
        else:
            self.data_dir = DEFAULT_MARKET_HISTORY_PROCESSED_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def load_weekly(self, seasons: list[int]) -> pl.DataFrame:
        frames: list[pl.DataFrame] = []
        for season in seasons:
            path = self.data_dir / f"market_history_weekly_{season}.parquet"
            if path.exists():
                frames.append(pl.read_parquet(path))
        if not frames:
            return pl.DataFrame(schema=PROCESSED_WEEKLY_SCHEMA)
        return pl.concat(frames, how="diagonal_relaxed")
```

Create `src/fantasy_sim/data/market_history/importer.py`:

```python
from __future__ import annotations

from pathlib import Path

import polars as pl

from fantasy_sim.data.market_history.loader import (
    DEFAULT_MARKET_HISTORY_PROCESSED_DIR,
    PROCESSED_WEEKLY_SCHEMA,
)

DEFAULT_MARKET_HISTORY_RAW_DIR = Path.home() / ".fantasy-sim" / "market-history" / "raw"


def build_market_history_cache(
    season: int,
    *,
    raw_dir: Path | None = None,
    processed_dir: Path | None = None,
) -> Path:
    """Combine week-level raw snapshots into one processed season parquet."""
    raw_root = Path(raw_dir or DEFAULT_MARKET_HISTORY_RAW_DIR) / str(season)
    processed_root = Path(processed_dir or DEFAULT_MARKET_HISTORY_PROCESSED_DIR)
    output_path = processed_root / f"market_history_weekly_{season}.parquet"

    frames: list[pl.DataFrame] = []
    for path in sorted(raw_root.glob("week*.parquet")):
        frame = pl.read_parquet(path).select(list(PROCESSED_WEEKLY_SCHEMA))
        frame = frame.with_columns(
            [
                pl.col("season").cast(pl.Int64),
                pl.col("week").cast(pl.Int64),
                pl.col("player_id").cast(pl.Utf8),
                pl.col("full_name").cast(pl.Utf8),
                pl.col("position").cast(pl.Utf8),
                pl.col("team").cast(pl.Utf8),
                pl.col("open_fpts").cast(pl.Float64),
                pl.col("close_fpts").cast(pl.Float64),
                pl.col("books").cast(pl.Int64),
                pl.col("line_stddev").cast(pl.Float64),
                pl.col("anytime_td_prob").cast(pl.Float64),
            ]
        ).unique(subset=["season", "week", "player_id"], keep="last")
        frames.append(frame)

    processed_root.mkdir(parents=True, exist_ok=True)
    if frames:
        combined = pl.concat(frames, how="diagonal_relaxed").sort(
            ["season", "week", "player_id"]
        )
    else:
        combined = pl.DataFrame(schema=PROCESSED_WEEKLY_SCHEMA)
    combined.write_parquet(output_path)
    return output_path
```

Create `src/fantasy_sim/data/market_history/features.py`:

```python
from __future__ import annotations

import polars as pl

from fantasy_sim.data.market_history.loader import PROCESSED_WEEKLY_SCHEMA
from fantasy_sim.data.market_history.models import MarketHistoryConfig

_MOVEMENT_WEIGHT = 0.25
_MIN_ANYTIME_CONFIDENCE = 0.85
_MAX_ANYTIME_CONFIDENCE = 1.15

NORMALIZED_MARKET_HISTORY_SCHEMA: dict[str, pl.DataType] = {
    **PROCESSED_WEEKLY_SCHEMA,
    "line_move": pl.Float64,
    "prior_fpts": pl.Float64,
    "adjusted_prior_fpts": pl.Float64,
    "confidence_factor": pl.Float64,
}


def normalize_market_history(
    frame: pl.DataFrame,
    config: MarketHistoryConfig,
) -> pl.DataFrame:
    """Build normalized per-player market priors and confidence signals."""
    if frame.is_empty():
        return pl.DataFrame(schema=NORMALIZED_MARKET_HISTORY_SCHEMA)

    normalized = (
        frame.filter(pl.col("position").is_in(list(config.positions)))
        .with_columns(
            [
                (
                    (pl.col("close_fpts") - pl.col("open_fpts"))
                    .fill_null(0.0)
                    .cast(pl.Float64)
                ).alias("line_move"),
                pl.coalesce([pl.col("close_fpts"), pl.col("open_fpts")])
                .cast(pl.Float64)
                .alias("prior_fpts"),
                (
                    (pl.col("books").fill_null(0) / max(config.min_books, 1))
                    .clip(0.0, 1.0)
                ).alias("book_confidence"),
                pl.when(
                    pl.lit(config.features.dispersion) & pl.col("line_stddev").is_not_null()
                )
                .then(
                    (1.0 - (pl.col("line_stddev") / config.dispersion_scale)).clip(0.0, 1.0)
                )
                .otherwise(1.0)
                .alias("dispersion_confidence"),
                pl.when(
                    pl.lit(config.features.anytime_td) & pl.col("anytime_td_prob").is_not_null()
                )
                .then(
                    (0.85 + pl.col("anytime_td_prob")).clip(
                        _MIN_ANYTIME_CONFIDENCE,
                        _MAX_ANYTIME_CONFIDENCE,
                    )
                )
                .otherwise(1.0)
                .alias("anytime_confidence"),
            ]
        )
        .with_columns(
            [
                pl.when(pl.lit(config.features.movement))
                .then(pl.col("line_move") * _MOVEMENT_WEIGHT)
                .otherwise(0.0)
                .alias("movement_adjustment"),
                (
                    pl.col("book_confidence")
                    * pl.col("dispersion_confidence")
                    * pl.col("anytime_confidence")
                )
                .clip(0.0, 1.0)
                .alias("confidence_factor"),
            ]
        )
        .with_columns(
            [
                (pl.col("prior_fpts") + pl.col("movement_adjustment"))
                .cast(pl.Float64)
                .alias("adjusted_prior_fpts")
            ]
        )
        .drop(
            [
                "book_confidence",
                "dispersion_confidence",
                "anytime_confidence",
                "movement_adjustment",
            ]
        )
    )

    return normalized.select(list(NORMALIZED_MARKET_HISTORY_SCHEMA))
```

Create `scripts/import_market_history.py`:

```python
from __future__ import annotations

import argparse

from fantasy_sim.data.market_history.importer import build_market_history_cache


def build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build processed historical market-history parquet from raw week files."
    )
    parser.add_argument("--season", type=int, nargs="+", required=True)
    return parser


def main() -> int:
    args = build_cli().parse_args()
    for season in args.season:
        output_path = build_market_history_cache(season)
        print(f"built {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the focused tests**

Run: `uv run pytest tests/test_data/test_market_history/test_loader.py tests/test_data/test_market_history/test_features.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/market_history/importer.py src/fantasy_sim/data/market_history/loader.py src/fantasy_sim/data/market_history/features.py scripts/import_market_history.py tests/test_data/test_market_history/test_loader.py tests/test_data/test_market_history/test_features.py
git commit -m "feat: add market history cache and normalizer"
```

### Task 3: Add The Post-Sim `market_history` Projection Adjuster

**Files:**
- Create: `src/fantasy_sim/scoring/market_history.py`
- Modify: `src/fantasy_sim/scoring/projection_layers.py:1-47`
- Test: `tests/test_scoring/test_market_history.py`

- [ ] **Step 1: Write the failing scoring tests**

Create `tests/test_scoring/test_market_history.py`:

```python
from types import SimpleNamespace

import polars as pl

from fantasy_sim.data.market_history.models import MarketHistoryConfig
from fantasy_sim.scoring.projection_layers import apply_projection_layers
from fantasy_sim.scoring.market_history import MarketHistoryProjectionAdjuster


class _StubLoader:
    def __init__(self, frame: pl.DataFrame) -> None:
        self.frame = frame
        self.calls: list[list[int]] = []

    def load_weekly(self, seasons: list[int]) -> pl.DataFrame:
        self.calls.append(list(seasons))
        return self.frame


def _config(*, enabled: bool = True) -> MarketHistoryConfig:
    return MarketHistoryConfig(
        enabled=enabled,
        weights={"QB": 0.50, "RB": 0.15, "WR": 0.25, "TE": 0.15},
    )


def test_adjust_week_blends_covered_rows_and_recomputes_rank():
    loader = _StubLoader(
        pl.DataFrame(
            {
                "season": [2024, 2024],
                "week": [1, 1],
                "player_id": ["QB1", "WR1"],
                "full_name": ["QB One", "WR One"],
                "position": ["QB", "WR"],
                "team": ["KC", "MIN"],
                "open_fpts": [19.0, 12.0],
                "close_fpts": [20.0, 12.0],
                "books": [2, 2],
                "line_stddev": [0.0, 0.0],
                "anytime_td_prob": [None, None],
            }
        )
    )
    adjuster = MarketHistoryProjectionAdjuster(_config(), loader=loader)

    adjusted, stats = adjuster.adjust_week(
        [
            {
                "player_id": "WR1",
                "name": "WR One",
                "position": "WR",
                "team": "MIN",
                "fpts": 11.0,
                "rank": 1,
            },
            {
                "player_id": "QB1",
                "name": "QB One",
                "position": "QB",
                "team": "KC",
                "fpts": 10.0,
                "rank": 2,
            },
        ],
        season=2024,
        week=1,
    )

    qb = next(row for row in adjusted if row["player_id"] == "QB1")
    wr = next(row for row in adjusted if row["player_id"] == "WR1")

    assert qb["fpts"] == 15.0
    assert qb["rank"] == 1
    assert qb["market_history_source"] == "market_history"
    assert qb["market_history_weight"] == 0.5
    assert qb["market_history_covered"] is True
    assert qb["market_history_prior_fpts"] == 20.0
    assert wr["fpts"] == 11.2
    assert wr["market_history_weight"] == 0.25
    assert stats.covered_rows == 2
    assert stats.uncovered_rows == 0


def test_adjust_week_marks_uncovered_rows_without_changing_fpts():
    loader = _StubLoader(
        pl.DataFrame(
            {
                "season": [2024],
                "week": [1],
                "player_id": ["WR1"],
                "full_name": ["WR One"],
                "position": ["WR"],
                "team": ["MIN"],
                "open_fpts": [12.0],
                "close_fpts": [12.0],
                "books": [2],
                "line_stddev": [0.0],
                "anytime_td_prob": [None],
            }
        )
    )
    adjuster = MarketHistoryProjectionAdjuster(_config(), loader=loader)

    adjusted, stats = adjuster.adjust_week(
        [
            {
                "player_id": "RB1",
                "name": "RB One",
                "position": "RB",
                "team": "SF",
                "fpts": 13.0,
                "rank": 1,
            }
        ],
        season=2024,
        week=1,
    )

    row = adjusted[0]
    assert row["fpts"] == 13.0
    assert row["market_history_source"] is None
    assert row["market_history_weight"] == 0.0
    assert row["market_history_covered"] is False
    assert stats.covered_rows == 0
    assert stats.uncovered_rows == 1


def test_apply_projection_layers_runs_market_history_between_role_trend_and_ensemble():
    order: list[str] = []

    class _Trend:
        def adjust_week(self, projections, *, season, week):
            order.append("trend")
            return ([dict(projections[0], fpts=13.0)], SimpleNamespace())

    class _Market:
        def adjust_week(self, projections, *, season, week):
            order.append("market")
            assert projections[0]["fpts"] == 13.0
            return ([dict(projections[0], fpts=14.0)], SimpleNamespace())

    class _Ensemble:
        def blend_week(self, projections, *, season, week):
            order.append("ensemble")
            assert projections[0]["fpts"] == 14.0
            return ([dict(projections[0], fpts=15.0)], SimpleNamespace())

    rows = [{"player_id": "QB1", "position": "QB", "team": "KC", "fpts": 12.0, "rank": 1}]

    adjusted = apply_projection_layers(
        rows,
        season=2024,
        week=1,
        role_trend_adjuster=_Trend(),
        market_history_adjuster=_Market(),
        ensembler=_Ensemble(),
    )

    assert adjusted[0]["fpts"] == 15.0
    assert order == ["trend", "market", "ensemble"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_scoring/test_market_history.py -v`

Expected: FAIL with missing market-history scoring module and unsupported `market_history_adjuster` argument in `apply_projection_layers()`

- [ ] **Step 3: Implement the adjuster and layer ordering**

Create `src/fantasy_sim/scoring/market_history.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from fantasy_sim.data.market_history.features import normalize_market_history
from fantasy_sim.data.market_history.loader import MarketHistoryLoader
from fantasy_sim.data.market_history.models import MarketHistoryConfig


@dataclass
class MarketHistoryStats:
    total_rows: int
    covered_rows: int
    uncovered_rows: int


class MarketHistoryProjectionAdjuster:
    """Blend simulation outputs with historical market priors."""

    def __init__(
        self,
        config: MarketHistoryConfig,
        loader: MarketHistoryLoader | None = None,
    ) -> None:
        self.config = config
        self.loader = loader
        self._prior_cache: dict[int, pl.DataFrame] = {}

    def _season_priors(self, season: int) -> pl.DataFrame:
        cached = self._prior_cache.get(season)
        if cached is not None:
            return cached

        if self.loader is None:
            self.loader = MarketHistoryLoader(self.config)

        raw = self.loader.load_weekly([season])
        normalized = normalize_market_history(raw, self.config)
        self._prior_cache[season] = normalized
        return normalized

    @staticmethod
    def _mark_uncovered(row: dict) -> dict:
        row["market_history_source"] = None
        row["market_history_weight"] = 0.0
        row["market_history_covered"] = False
        row.pop("market_history_prior_fpts", None)
        row.pop("market_history_confidence", None)
        row.pop("market_history_line_move", None)
        return row

    def adjust_week(
        self,
        projections: list[dict],
        *,
        season: int,
        week: int,
    ) -> tuple[list[dict], MarketHistoryStats]:
        total_rows = len(projections)
        if not projections or not self.config.enabled:
            rows = [self._mark_uncovered(dict(projection)) for projection in projections]
            return rows, MarketHistoryStats(
                total_rows=total_rows,
                covered_rows=0,
                uncovered_rows=total_rows,
            )

        priors = self._season_priors(season).filter(pl.col("week") == week)
        prior_map = {
            prior["player_id"]: prior
            for prior in priors.iter_rows(named=True)
        }

        adjusted: list[dict] = []
        covered_rows = 0
        uncovered_rows = 0

        for projection in projections:
            row = dict(projection)
            position = str(row.get("position", ""))
            prior = prior_map.get(row.get("player_id"))
            base_weight = float(self.config.weights.get(position, 0.0))

            if prior is None or base_weight <= 0:
                self._mark_uncovered(row)
                uncovered_rows += 1
                adjusted.append(row)
                continue

            confidence = float(prior["confidence_factor"])
            effective_weight = round(base_weight * confidence, 4)
            if effective_weight <= 0:
                self._mark_uncovered(row)
                uncovered_rows += 1
                adjusted.append(row)
                continue

            prior_fpts = float(prior["adjusted_prior_fpts"])
            row["market_history_source"] = "market_history"
            row["market_history_weight"] = effective_weight
            row["market_history_covered"] = True
            row["market_history_prior_fpts"] = round(prior_fpts, 2)
            row["market_history_confidence"] = round(confidence, 4)
            row["market_history_line_move"] = round(float(prior["line_move"]), 2)
            row["fpts"] = round(
                float(row["fpts"]) * (1.0 - effective_weight)
                + prior_fpts * effective_weight,
                1,
            )
            covered_rows += 1
            adjusted.append(row)

        adjusted.sort(key=lambda item: item["fpts"], reverse=True)
        for rank, row in enumerate(adjusted, start=1):
            row["rank"] = rank

        return adjusted, MarketHistoryStats(
            total_rows=total_rows,
            covered_rows=covered_rows,
            uncovered_rows=uncovered_rows,
        )
```

Modify `src/fantasy_sim/scoring/projection_layers.py` so the protocols and ordering become:

```python
from typing import Protocol, TypeVar

from fantasy_sim.scoring.ensemble import BlendStats
from fantasy_sim.scoring.market_history import MarketHistoryStats
from fantasy_sim.scoring.role_trend import ProjectionRow, TrendStats


ProjectionLayerRowT = TypeVar("ProjectionLayerRowT", bound=ProjectionRow)


class RoleTrendAdjusterProtocol(Protocol[ProjectionLayerRowT]):
    def adjust_week(
        self,
        projections: list[ProjectionLayerRowT],
        *,
        season: int,
        week: int,
    ) -> tuple[list[ProjectionLayerRowT], TrendStats]: ...


class MarketHistoryAdjusterProtocol(Protocol[ProjectionLayerRowT]):
    def adjust_week(
        self,
        projections: list[ProjectionLayerRowT],
        *,
        season: int,
        week: int,
    ) -> tuple[list[ProjectionLayerRowT], MarketHistoryStats]: ...


class ProjectionEnsemblerProtocol(Protocol[ProjectionLayerRowT]):
    def blend_week(
        self,
        projections: list[ProjectionLayerRowT],
        *,
        season: int,
        week: int,
    ) -> tuple[list[ProjectionLayerRowT], BlendStats]: ...


def apply_projection_layers(
    projections: list[ProjectionLayerRowT],
    *,
    season: int,
    week: int,
    role_trend_adjuster: RoleTrendAdjusterProtocol[ProjectionLayerRowT] | None = None,
    market_history_adjuster: MarketHistoryAdjusterProtocol[ProjectionLayerRowT] | None = None,
    ensembler: ProjectionEnsemblerProtocol[ProjectionLayerRowT] | None = None,
) -> list[ProjectionLayerRowT]:
    rows = projections.copy()
    if role_trend_adjuster is not None:
        rows, _trend_stats = role_trend_adjuster.adjust_week(rows, season=season, week=week)
    if market_history_adjuster is not None:
        rows, _market_stats = market_history_adjuster.adjust_week(rows, season=season, week=week)
    if ensembler is not None:
        rows, _blend_stats = ensembler.blend_week(rows, season=season, week=week)
    return rows
```

- [ ] **Step 4: Run the scoring tests**

Run: `uv run pytest tests/test_scoring/test_market_history.py tests/test_scoring/test_ensemble.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/scoring/market_history.py src/fantasy_sim/scoring/projection_layers.py tests/test_scoring/test_market_history.py
git commit -m "feat: add market history projection adjuster"
```

### Task 4: Wire `market_history` Through Validation, Backtest, And Non-Detail CLI Flows

**Files:**
- Modify: `src/fantasy_sim/validation/config.py:10-120`
- Modify: `src/fantasy_sim/validation/backtester.py:8-206`
- Modify: `src/fantasy_sim/cli.py:160-191, 635-721, 791-885, 994-1067, 1328-1361`
- Test: `tests/test_validation/test_market_history_pipeline.py`

- [ ] **Step 1: Write the failing pipeline-order and wiring tests**

Create `tests/test_validation/test_market_history_pipeline.py`:

```python
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import polars as pl

from fantasy_sim.data.ensemble.models import EnsembleConfig, FfOpportunityConfig
from fantasy_sim.data.market_history.models import MarketHistoryConfig
from fantasy_sim.data.role_trend.models import RoleTrendConfig
from fantasy_sim.validation.backtester import Backtester


def _load_validate_module():
    import importlib.util

    validate_path = Path(__file__).resolve().parents[2] / "scripts" / "validate.py"
    spec = importlib.util.spec_from_file_location(
        "validate_script_market_history_test",
        validate_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_backtester_applies_role_trend_then_market_history_then_ensemble():
    mock_loader = MagicMock()
    mock_loader.cache_dir = Path("/tmp/test-cache")
    mock_loader.load_schedules.return_value = pl.DataFrame(
        [
            {
                "season": 2024,
                "week": 1,
                "game_id": "2024_01_KC_BUF",
                "home_team": "KC",
                "away_team": "BUF",
            }
        ]
    )
    mock_loader.load_player_stats.return_value = pl.DataFrame(
        {"season": pl.Series([], dtype=pl.Int32)}
    )

    build_results = [
        {
            "status": "ok",
            "game_id": "2024_01_KC_BUF",
            "seed": 7,
            "week": 1,
            "home": "KC",
            "away": "BUF",
            "home_dists": object(),
            "away_dists": object(),
            "home_roster": object(),
            "away_roster": object(),
        }
    ]
    sim_results = [
        SimpleNamespace(
            game_id="2024_01_KC_BUF",
            projections=[
                {
                    "player_id": "player-1",
                    "fpts": 12.0,
                    "position": "QB",
                    "team": "KC",
                    "name": "Patrick Example",
                }
            ],
        )
    ]
    actuals = [
        SimpleNamespace(
            player_id="player-1",
            week=1,
            fpts=15.0,
            position="QB",
            team="KC",
            name="Patrick Example",
        )
    ]

    order: list[str] = []

    class _Trend:
        def adjust_week(self, projections, *, season, week):
            order.append("trend")
            return ([dict(projections[0], fpts=13.0)], SimpleNamespace())

    class _Market:
        def adjust_week(self, projections, *, season, week):
            order.append("market")
            assert projections[0]["fpts"] == 13.0
            return ([dict(projections[0], fpts=14.0)], SimpleNamespace())

    class _Ensemble:
        def blend_week(self, projections, *, season, week):
            order.append("ensemble")
            assert projections[0]["fpts"] == 14.0
            return ([dict(projections[0], fpts=15.0)], SimpleNamespace())

    with patch("fantasy_sim.validation.backtester.build_games_parallel", return_value=build_results), \
         patch("fantasy_sim.validation.backtester.simulate_games_parallel", return_value=sim_results), \
         patch("fantasy_sim.validation.backtester.load_actual_scores", return_value=actuals), \
         patch("fantasy_sim.validation.backtester.RoleTrendProjectionAdjuster", return_value=_Trend()), \
         patch("fantasy_sim.validation.backtester.MarketHistoryProjectionAdjuster", return_value=_Market()), \
         patch("fantasy_sim.validation.backtester.FfOpportunityProjectionEnsembler", return_value=_Ensemble()):
        bt = Backtester(
            test_season=2024,
            n_sims=10,
            role_trend_config=RoleTrendConfig(enabled=True),
            market_history_config=MarketHistoryConfig(enabled=True),
            ensemble_config=EnsembleConfig(
                enabled=True,
                ff_opportunity=FfOpportunityConfig(enabled=True),
            ),
        )
        bt.loader = mock_loader

        result = bt.run(scoring_config={})

    assert result.weekly_mae == 0.0
    assert order == ["trend", "market", "ensemble"]


def test_run_season_applies_role_trend_then_market_history_then_ensemble():
    validate = _load_validate_module()

    build_b = [
        {
            "status": "ok",
            "game_id": "2024_01_KC_BUF",
            "seed": 7,
            "week": 1,
            "home": "KC",
            "away": "BUF",
            "home_dists": object(),
            "away_dists": object(),
            "home_roster": object(),
            "away_roster": object(),
        }
    ]
    actual = SimpleNamespace(
        player_id="player-1",
        week=1,
        fpts=15.0,
        position="QB",
        team="KC",
        name="Patrick Example",
    )
    cached_arm_a = {
        "projections": {"player-1": {1: 10.0}},
        "player_meta": {
            "player-1": {
                "position": "QB",
                "team": "KC",
                "name": "Patrick Example",
            }
        },
    }
    order: list[str] = []

    class _Trend:
        def adjust_week(self, projections, *, season, week):
            order.append("trend")
            return ([dict(projections[0], fpts=13.0)], SimpleNamespace())

    class _Market:
        def adjust_week(self, projections, *, season, week):
            order.append("market")
            assert projections[0]["fpts"] == 13.0
            return ([dict(projections[0], fpts=14.0)], SimpleNamespace())

    class _Ensemble:
        def blend_week(self, projections, *, season, week):
            order.append("ensemble")
            assert projections[0]["fpts"] == 14.0
            return ([dict(projections[0], fpts=15.0)], SimpleNamespace())

    with patch.object(validate, "build_games_parallel", return_value=build_b), \
         patch.object(
             validate,
             "simulate_games_parallel",
             return_value=[
                 SimpleNamespace(
                     game_id="2024_01_KC_BUF",
                     metadata={},
                     projections=[
                         {
                             "player_id": "player-1",
                             "fpts": 12.0,
                             "position": "QB",
                             "team": "KC",
                             "name": "Patrick Example",
                         }
                     ],
                 )
             ],
         ), \
         patch.object(validate, "load_actual_scores", return_value=[actual]), \
         patch.object(validate, "DataLoader") as mock_loader_cls, \
         patch.object(validate, "RoleTrendProjectionAdjuster", return_value=_Trend()), \
         patch.object(validate, "MarketHistoryProjectionAdjuster", return_value=_Market()), \
         patch.object(validate, "FfOpportunityProjectionEnsembler", return_value=_Ensemble()):
        mock_loader = mock_loader_cls.return_value
        mock_loader.cache_dir = Path("/tmp/test-cache")
        mock_loader.load_schedules.return_value = pl.DataFrame(
            [
                {
                    "season": 2024,
                    "week": 1,
                    "game_id": "2024_01_KC_BUF",
                    "home_team": "KC",
                    "away_team": "BUF",
                }
            ]
        )
        mock_loader.load_player_stats.return_value = pl.DataFrame(
            {"season": pl.Series([], dtype=pl.Int32)}
        )

        result = validate.run_season(
            test_season=2024,
            n_sims=10,
            scoring_config={},
            num_training_seasons=3,
            arm_a_configs={
                "pff_config": None,
                "weather_config": None,
                "vegas_config": None,
                "props_config": None,
                "usage_config": None,
                "availability_config": None,
                "role_trend_config": None,
                "market_history_config": None,
                "game_script_config": None,
                "goal_line_concentration_config": None,
                "td_tendency_config": None,
            },
            arm_b_configs={
                "pff_config": object(),
                "weather_config": None,
                "vegas_config": None,
                "props_config": None,
                "usage_config": None,
                "availability_config": None,
                "role_trend_config": RoleTrendConfig(enabled=True),
                "market_history_config": MarketHistoryConfig(enabled=True),
                "game_script_config": None,
                "goal_line_concentration_config": None,
                "td_tendency_config": None,
            },
            arm_a_ensemble_config=None,
            arm_b_ensemble_config=EnsembleConfig(
                enabled=True,
                ff_opportunity=FfOpportunityConfig(enabled=True),
            ),
            positions=["QB"],
            max_workers=1,
            cached_arm_a=cached_arm_a,
        )

    assert result["season_metrics"].arm_b_weekly_mae == 0.0
    assert result["weekly_records"][0].projected_fpts_on == 15.0
    assert order == ["trend", "market", "ensemble"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_validation/test_market_history_pipeline.py -v`

Expected: FAIL because `market_history_config` is not threaded through the runtime and the new adjuster is never instantiated

- [ ] **Step 3: Wire the new config family into the runtime**

Modify `src/fantasy_sim/validation/config.py`:

```python
from fantasy_sim.data.market_history.config import load_market_history_config
from fantasy_sim.data.pff.config import load_pff_config
from fantasy_sim.data.weather.config import load_weather_config
from fantasy_sim.data.vegas.config import load_vegas_config, load_props_config
from fantasy_sim.data.availability.config import load_availability_config
from fantasy_sim.data.role_trend.config import load_role_trend_config
from fantasy_sim.data.usage.config import load_usage_config
from fantasy_sim.data.game_script import load_game_script_config
from fantasy_sim.data.goal_line_concentration import load_goal_line_concentration_config
from fantasy_sim.data.td_tendency import load_td_tendency_config


def build_engine_configs(config: dict) -> dict:
    pff = load_pff_config(config)
    weather = load_weather_config(config)
    vegas = load_vegas_config(config)
    props = load_props_config(config)
    usage = load_usage_config(config)
    availability = load_availability_config(config)
    role_trend = load_role_trend_config(config)
    market_history = load_market_history_config(config)
    game_script = load_game_script_config(config)
    goal_line_concentration = load_goal_line_concentration_config(config)
    td_tendency = load_td_tendency_config(config)
    return {
        "pff_config": pff if pff.enabled else None,
        "weather_config": weather if weather.enabled else None,
        "vegas_config": vegas if vegas.enabled else None,
        "props_config": props if props.enabled else None,
        "usage_config": usage if usage.enabled else None,
        "availability_config": availability if availability.enabled else None,
        "role_trend_config": role_trend if role_trend.enabled else None,
        "market_history_config": market_history if market_history.enabled else None,
        "game_script_config": game_script if game_script.enabled else None,
        "goal_line_concentration_config": (
            goal_line_concentration if goal_line_concentration.enabled else None
        ),
        "td_tendency_config": td_tendency if td_tendency.enabled else None,
    }


def build_bare_engine_configs() -> dict:
    return {
        "pff_config": None,
        "weather_config": None,
        "vegas_config": None,
        "props_config": None,
        "usage_config": None,
        "availability_config": None,
        "role_trend_config": None,
        "market_history_config": None,
        "game_script_config": None,
        "goal_line_concentration_config": None,
        "td_tendency_config": None,
    }
```

Modify `src/fantasy_sim/validation/backtester.py`:

```python
from fantasy_sim.data.ensemble.models import EnsembleConfig
from fantasy_sim.data.loader import DataLoader
from fantasy_sim.data.market_history.models import MarketHistoryConfig
from fantasy_sim.data.pff.models import PffConfig
from fantasy_sim.data.role_trend.models import RoleTrendConfig
from fantasy_sim.data.weather.models import WeatherConfig
from fantasy_sim.data.vegas.models import PropsConfig, VegasConfig
from fantasy_sim.data.usage.models import UsageConfig
from fantasy_sim.data.actuals import load_actual_scores
from fantasy_sim.scoring.ensemble import FfOpportunityProjectionEnsembler
from fantasy_sim.scoring.market_history import MarketHistoryProjectionAdjuster
from fantasy_sim.scoring.projection_layers import apply_projection_layers
from fantasy_sim.scoring.role_trend import RoleTrendProjectionAdjuster


class Backtester:
    def __init__(
        self,
        test_season: int,
        n_sims: int = 100,
        num_training_seasons: int = 3,
        scoring_format: str = "ppr",
        cache_dir: Path | None = None,
        pff_config: PffConfig | None = None,
        weather_config: WeatherConfig | None = None,
        vegas_config: VegasConfig | None = None,
        props_config: PropsConfig | None = None,
        usage_config: UsageConfig | None = None,
        role_trend_config: RoleTrendConfig | None = None,
        market_history_config: MarketHistoryConfig | None = None,
        ensemble_config: EnsembleConfig | None = None,
        max_workers: int = 1,
    ):
        if test_season >= _HOLDOUT_SEASON:
            raise ValueError(
                f"Season {test_season} is reserved as hold-out until milestone completion. "
                f"Use seasons 2022-2024 for A/B validation."
            )
        self.test_season = test_season
        self.n_sims = n_sims
        self.training_seasons = list(range(
            test_season - num_training_seasons, test_season
        ))
        self.scoring_format = scoring_format
        self.loader = DataLoader(cache_dir=cache_dir) if cache_dir else DataLoader()
        self._pff_config = pff_config
        self._weather_config = weather_config
        self._vegas_config = vegas_config
        self._props_config = props_config
        self._usage_config = usage_config
        self._role_trend_config = role_trend_config
        self._market_history_config = market_history_config
        self._ensemble_config = ensemble_config
        self.max_workers = max_workers

    def run(self, scoring_config: dict) -> BacktestResult:
        market_history_adjuster = None
        if self._market_history_config is not None and self._market_history_config.enabled:
            market_history_adjuster = MarketHistoryProjectionAdjuster(
                self._market_history_config
            )
        projections = apply_projection_layers(
            result.projections,
            season=self.test_season,
            week=wk,
            role_trend_adjuster=role_trend_adjuster,
            market_history_adjuster=market_history_adjuster,
            ensembler=ensembler,
        )
```

Modify `src/fantasy_sim/cli.py`:

```python
from fantasy_sim.data.ensemble import load_ensemble_config
from fantasy_sim.data.market_history import load_market_history_config
from fantasy_sim.data.role_trend.config import load_role_trend_config
from fantasy_sim.scoring.ensemble import FfOpportunityProjectionEnsembler
from fantasy_sim.scoring.market_history import MarketHistoryProjectionAdjuster
from fantasy_sim.scoring.projection_layers import apply_projection_layers
from fantasy_sim.scoring.role_trend import RoleTrendProjectionAdjuster


def _make_ensembler(defaults: dict) -> FfOpportunityProjectionEnsembler | None:
    ensemble_config = load_ensemble_config(defaults)
    if not ensemble_config.enabled or not ensemble_config.ff_opportunity.enabled:
        return None
    return FfOpportunityProjectionEnsembler(ensemble_config)


def _make_role_trend_adjuster(defaults: dict) -> RoleTrendProjectionAdjuster | None:
    role_trend_config = load_role_trend_config(defaults)
    if not role_trend_config.enabled:
        return None
    return RoleTrendProjectionAdjuster(role_trend_config)


def _make_market_history_adjuster(defaults: dict) -> MarketHistoryProjectionAdjuster | None:
    market_history_config = load_market_history_config(defaults)
    if not market_history_config.enabled:
        return None
    return MarketHistoryProjectionAdjuster(market_history_config)


def _maybe_blend_player_projs(
    player_projs: list[dict],
    *,
    role_trend_adjuster: RoleTrendProjectionAdjuster | None = None,
    market_history_adjuster: MarketHistoryProjectionAdjuster | None = None,
    ensembler: FfOpportunityProjectionEnsembler | None,
    season: int,
    week: int,
) -> list[dict]:
    return apply_projection_layers(
        player_projs,
        season=season,
        week=week,
        role_trend_adjuster=role_trend_adjuster,
        market_history_adjuster=market_history_adjuster,
        ensembler=ensembler,
    )
```

In the non-detail `week`, `season`, and `game` commands, add:

```python
market_history_adjuster = None if detail else _make_market_history_adjuster(defaults)
```

and pass it through:

```python
player_batch = _maybe_blend_player_projs(
    player_batch,
    role_trend_adjuster=role_trend_adjuster,
    market_history_adjuster=market_history_adjuster,
    ensembler=ensembler,
    season=season,
    week=week_num,
)
```

In the `backtest` command, load and pass the config:

```python
market_history_config = load_market_history_config(defaults)

bt = Backtester(
    test_season=season,
    n_sims=sims,
    num_training_seasons=training_years,
    scoring_format=scoring,
    pff_config=pff_config,
    weather_config=weather_config,
    vegas_config=vegas_config,
    usage_config=usage_config,
    role_trend_config=role_trend_config,
    market_history_config=market_history_config,
    ensemble_config=ensemble_config,
)
```

- [ ] **Step 4: Run the pipeline tests**

Run: `uv run pytest tests/test_validation/test_market_history_pipeline.py tests/test_validation/test_backtester.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/validation/config.py src/fantasy_sim/validation/backtester.py src/fantasy_sim/cli.py tests/test_validation/test_market_history_pipeline.py
git commit -m "feat: wire market history through projection flows"
```

### Task 5: Add Partial-Coverage Reporting, Covered-Season Readouts, And Ledger Metadata

**Files:**
- Modify: `src/fantasy_sim/validation/coverage.py:1-280`
- Modify: `src/fantasy_sim/validation/ledger.py:19-175`
- Modify: `scripts/validate.py:27-130, 170-544, 547-867`
- Modify: `tests/test_validation/test_coverage.py`
- Modify: `tests/test_validation/test_validate_script.py`
- Modify: `tests/test_validation/test_ledger.py`

- [ ] **Step 1: Write the failing validation and ledger tests**

Add this test to `tests/test_validation/test_coverage.py`:

```python
def test_market_history_reports_partial_for_covered_2023_only(tmp_path):
    import polars as pl

    market_dir = tmp_path / "market-history"
    market_dir.mkdir()
    pl.DataFrame(
        {
            "season": [2023],
            "week": [1],
            "player_id": ["QB1"],
            "full_name": ["QB One"],
            "position": ["QB"],
            "team": ["KC"],
            "open_fpts": [18.0],
            "close_fpts": [19.0],
            "books": [3],
            "line_stddev": [1.0],
            "anytime_td_prob": [0.10],
        }
    ).write_parquet(market_dir / "market_history_weekly_2023.parquet")

    coverage = collect_signal_coverage(
        {"market_history": {"enabled": True, "data_dir": str(market_dir)}},
        [2022, 2023, 2024],
    )

    assert coverage["market_history"] == SignalCoverage(
        enabled=True,
        status="partial",
        covered_seasons=[2023],
        missing_seasons=[2022, 2024],
        note="Requires processed season parquet at ~/.fantasy-sim/market-history/processed",
    )
    assert coverage["market_history.open_fpts"].covered_seasons == [2023]
    assert coverage["market_history.close_fpts"].covered_seasons == [2023]
    assert coverage["market_history.dispersion"].covered_seasons == [2023]
    assert coverage["market_history.anytime_td"].covered_seasons == [2023]
```

Add these tests to `tests/test_validation/test_validate_script.py`:

```python
def test_run_season_does_not_thread_market_history_config_into_build_kwargs():
    validate = _load_validate_module()

    with patch.object(validate, "simulate_games_parallel", return_value=[]), \
         patch.object(validate, "build_games_parallel", return_value=[]) as mock_build_games_parallel, \
         patch.object(validate, "load_actual_scores", return_value=[]), \
         patch.object(validate, "DataLoader") as mock_loader_cls:
        mock_loader = mock_loader_cls.return_value
        mock_loader.cache_dir = Path("/tmp/test-cache")
        mock_loader.load_schedules.return_value = pl.DataFrame(
            [
                {
                    "season": 2024,
                    "week": 1,
                    "game_id": "2024_01_KC_BUF",
                    "home_team": "KC",
                    "away_team": "BUF",
                }
            ]
        )
        mock_loader.load_player_stats.return_value = pl.DataFrame(
            {"season": pl.Series([], dtype=pl.Int32)}
        )

        validate.run_season(
            test_season=2024,
            n_sims=10,
            scoring_config={},
            num_training_seasons=3,
            arm_a_configs={
                "pff_config": None,
                "weather_config": None,
                "vegas_config": None,
                "props_config": None,
                "usage_config": None,
                "availability_config": None,
                "role_trend_config": None,
                "market_history_config": None,
                "game_script_config": None,
                "goal_line_concentration_config": None,
                "td_tendency_config": None,
            },
            arm_b_configs={
                "pff_config": None,
                "weather_config": None,
                "vegas_config": None,
                "props_config": None,
                "usage_config": None,
                "availability_config": None,
                "role_trend_config": None,
                "market_history_config": object(),
                "game_script_config": None,
                "goal_line_concentration_config": None,
                "td_tendency_config": None,
            },
            positions=["QB"],
            max_workers=1,
        )

    call_kwargs = mock_build_games_parallel.call_args.kwargs
    assert "market_history_config" not in call_kwargs


def test_print_market_history_results_uses_only_covered_seasons():
    validate = _load_validate_module()

    season_results = [
        validate.SeasonMetrics(
            test_season=2022,
            arm_a_rank_corr={"QB": 0.40, "RB": 0.40, "WR": 0.40, "TE": 0.40},
            arm_b_rank_corr={"QB": 0.40, "RB": 0.40, "WR": 0.40, "TE": 0.40},
            arm_a_weekly_mae=7.0,
            arm_b_weekly_mae=7.0,
            arm_a_season_mae=30.0,
            arm_b_season_mae=30.0,
            arm_a_calibration=0.1,
            arm_b_calibration=0.1,
        ),
        validate.SeasonMetrics(
            test_season=2023,
            arm_a_rank_corr={"QB": 0.40, "RB": 0.40, "WR": 0.40, "TE": 0.40},
            arm_b_rank_corr={"QB": 0.50, "RB": 0.50, "WR": 0.50, "TE": 0.50},
            arm_a_weekly_mae=7.0,
            arm_b_weekly_mae=6.5,
            arm_a_season_mae=30.0,
            arm_b_season_mae=29.0,
            arm_a_calibration=0.1,
            arm_b_calibration=0.1,
        ),
        validate.SeasonMetrics(
            test_season=2024,
            arm_a_rank_corr={"QB": 0.40, "RB": 0.40, "WR": 0.40, "TE": 0.40},
            arm_b_rank_corr={"QB": 0.60, "RB": 0.60, "WR": 0.60, "TE": 0.60},
            arm_a_weekly_mae=7.0,
            arm_b_weekly_mae=6.0,
            arm_a_season_mae=30.0,
            arm_b_season_mae=28.0,
            arm_a_calibration=0.1,
            arm_b_calibration=0.1,
        ),
    ]
    coverage_summary = {
        "market_history": SignalCoverage(
            enabled=True,
            status="partial",
            covered_seasons=[2023, 2024],
            missing_seasons=[2022],
            note="Requires processed season parquet at ~/.fantasy-sim/market-history/processed",
        )
    }

    with patch.object(validate, "print") as mock_print:
        validate.print_market_history_results(season_results, coverage_summary)

    printed = "\n".join(call.args[0] for call in mock_print.call_args_list)
    assert "covered seasons   : 2023, 2024" in printed
    assert "uncovered seasons : 2022" in printed
    assert "promotion scope   : covered_only" in printed
    assert "rank_corr delta:  +0.1500" in printed
    assert "weekly_mae delta: -0.750" in printed
    assert "season_mae delta: -1.500" in printed
```

Add this test to `tests/test_validation/test_ledger.py`:

```python
def test_ledger_roundtrip_preserves_promotion_evidence_scope(tmp_path):
    path = tmp_path / "test_ledger.json"
    entry = _make_entry("phase-3-market-history-v1")
    entry.promotion_evidence_scope = "covered_only"

    save_ledger(path, [entry])
    loaded = load_ledger(path)

    assert loaded[0].promotion_evidence_scope == "covered_only"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_validation/test_coverage.py tests/test_validation/test_validate_script.py tests/test_validation/test_ledger.py -v`

Expected: FAIL because market-history coverage, covered-season readouts, and ledger schema fields do not exist yet

- [ ] **Step 3: Implement coverage summary, validate readout, and ledger metadata**

Modify `src/fantasy_sim/validation/coverage.py`:

```python
import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

import polars as pl

DEFAULT_PFF_DIR = Path.home() / ".fantasy-sim" / "pff" / "processed" / "nfl"
DEFAULT_PFF_ROUTE_RATE_DIR = Path.home() / ".fantasy-sim" / "pff" / "processed"
DEFAULT_PROPS_DIR = Path.home() / ".fantasy-sim" / "pff" / "props"
DEFAULT_MARKET_HISTORY_DIR = Path.home() / ".fantasy-sim" / "market-history" / "processed"
DEFAULT_CACHE_DIR = Path.home() / ".fantasy-sim" / "cache"


def _resolve_market_history_path(
    config: object,
    market_history_dir: str | Path | None,
) -> Path:
    if market_history_dir is not None:
        return _path_or_default(market_history_dir, DEFAULT_MARKET_HISTORY_DIR)

    market_history_config = _config_section(config, "market_history_config")
    if market_history_config is None:
        market_history_config = _config_section(config, "market_history")
    data_dir = (
        _config_get(market_history_config, "data_dir", default=None)
        if market_history_config is not None
        else None
    )
    if data_dir is not None:
        return _path_or_default(data_dir, DEFAULT_MARKET_HISTORY_DIR)
    return DEFAULT_MARKET_HISTORY_DIR


def _parquet_columns(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return set(pl.read_parquet(path).columns)
```

Update `collect_signal_coverage(...)` signature and body:

```python
def collect_signal_coverage(
    config: object,
    test_seasons: Iterable[int],
    *,
    cache_dir: str | Path | None = None,
    pff_dir: str | Path | None = None,
    props_dir: str | Path | None = None,
    market_history_dir: str | Path | None = None,
) -> dict[str, SignalCoverage]:
    seasons = list(test_seasons)
    cache_path = _coerce_path(cache_dir, DEFAULT_CACHE_DIR)
    pff_path = _resolve_pff_path(config, pff_dir)
    route_rate_pff_path = _resolve_route_rate_pff_path(config, pff_dir)
    props_path = _resolve_props_path(config, props_dir)
    market_history_path = _resolve_market_history_path(config, market_history_dir)
    market_history_enabled = _signal_enabled(
        config,
        ("market_history_config", "market_history"),
        ("market_history",),
    )
    market_history_paths = {
        season: market_history_path / f"market_history_weekly_{season}.parquet"
        for season in seasons
    }

    def _market_history_column_signal(column_name: str, note: str) -> SignalCoverage:
        covered = [
            season
            for season, path in market_history_paths.items()
            if path.exists() and column_name in _parquet_columns(path)
        ]
        return _build_signal(
            market_history_enabled,
            seasons,
            covered,
            note=note,
        )
```

Then append these exact entries to the existing return dict in the same function:

```python
        "market_history": _build_signal(
            market_history_enabled,
            seasons,
            _covered_seasons_from_any_paths(seasons, market_history_paths),
            note="Requires processed season parquet at ~/.fantasy-sim/market-history/processed",
        ),
        "market_history.open_fpts": _market_history_column_signal(
            "open_fpts",
            "Requires open_fpts column in processed market-history parquet",
        ),
        "market_history.close_fpts": _market_history_column_signal(
            "close_fpts",
            "Requires close_fpts column in processed market-history parquet",
        ),
        "market_history.dispersion": _build_signal(
            market_history_enabled,
            seasons,
            [
                season
                for season, path in market_history_paths.items()
                if path.exists()
                and {"books", "line_stddev"}.issubset(_parquet_columns(path))
            ],
            note="Requires books and line_stddev columns in processed market-history parquet",
        ),
        "market_history.anytime_td": _market_history_column_signal(
            "anytime_td_prob",
            "Requires anytime_td_prob column in processed market-history parquet",
        ),
```

Modify `src/fantasy_sim/validation/ledger.py`:

```python
DEFAULT_LEDGER_PATH = Path(__file__).resolve().parents[3] / "results" / "ab_ledger.json"
CURRENT_LEDGER_SCHEMA_VERSION = 3


@dataclass
class LedgerEntry:
    label: str
    timestamp: str
    sims: int
    test_seasons: list[int]
    training_years: int
    scoring: str
    baseline: str
    overrides: list[str]
    config_snapshot: dict
    season_results: list[SeasonMetrics]
    schema_version: int | None = None
    comparison_mode: str | None = None
    seed_mode: str | None = None
    coverage_summary: dict[str, SignalCoverage] | None = None
    weekly_summaries: list[WeeklyPositionSummary] | None = None
    directional_accuracy: DirectionalAccuracyResult | None = None
    promotion_evidence_scope: str | None = None
```

and in `load_ledger(...)`:

```python
        item.setdefault("promotion_evidence_scope", None)
```

Modify `scripts/validate.py`:

```python
from fantasy_sim.data.ensemble import EnsembleConfig, load_ensemble_config
from fantasy_sim.data.actuals import load_actual_scores
from fantasy_sim.data.loader import DataLoader
from fantasy_sim.scoring.ensemble import FfOpportunityProjectionEnsembler
from fantasy_sim.scoring.market_history import MarketHistoryProjectionAdjuster
from fantasy_sim.scoring.projection_layers import apply_projection_layers
from fantasy_sim.scoring.role_trend import RoleTrendProjectionAdjuster
```

In `run_season(...)`, instantiate and strip the config:

```python
    arm_a_market_history = (
        MarketHistoryProjectionAdjuster(arm_a_configs["market_history_config"])
        if arm_a_configs.get("market_history_config") is not None
        else None
    )
    arm_b_market_history = (
        MarketHistoryProjectionAdjuster(arm_b_configs["market_history_config"])
        if arm_b_configs.get("market_history_config") is not None
        else None
    )

    arm_a_build_configs = {
        key: value
        for key, value in arm_a_configs.items()
        if key not in {"role_trend_config", "market_history_config"}
    }
    arm_b_build_configs = {
        key: value
        for key, value in arm_b_configs.items()
        if key not in {"role_trend_config", "market_history_config"}
    }
```

and pass the adjuster in all `apply_projection_layers(...)` calls:

```python
            projections = apply_projection_layers(
                result.projections,
                season=test_season,
                week=spec.week,
                role_trend_adjuster=arm_b_role_trend,
                market_history_adjuster=arm_b_market_history,
                ensembler=arm_b_ensembler,
            )
```

Add the market-history readout helper:

```python
def print_market_history_results(
    season_results: list[SeasonMetrics],
    coverage_summary: Mapping[str, SignalCoverage] | None,
) -> None:
    signal = (coverage_summary or {}).get("market_history")
    if signal is None or not signal.enabled:
        return

    covered = signal.covered_seasons
    uncovered = signal.missing_seasons

    print("\n" + "=" * 68)
    print("  MARKET HISTORY COVERED-SEASON READOUT")
    print("=" * 68)
    print(f"  covered seasons   : {', '.join(str(season) for season in covered) or '(none)'}")
    print(f"  uncovered seasons : {', '.join(str(season) for season in uncovered) or '(none)'}")
    print("  promotion scope   : covered_only")

    covered_results = [
        season_result
        for season_result in season_results
        if season_result.test_season in covered
    ]
    if not covered_results:
        print("  no covered seasons; market-specific averages skipped")
        return

    avg_rc = sum(r.rank_corr_delta for r in covered_results) / len(covered_results)
    avg_wm = sum(r.weekly_mae_delta for r in covered_results) / len(covered_results)
    avg_sm = sum(r.season_mae_delta for r in covered_results) / len(covered_results)
    print(f"  rank_corr delta:  {avg_rc:+.4f}")
    print(f"  weekly_mae delta: {avg_wm:+.3f}")
    print(f"  season_mae delta: {avg_sm:+.3f}")
```

Call it in `main()` immediately after `print_season_results(all_season_metrics)`:

```python
    print_market_history_results(all_season_metrics, coverage_summary)
```

and set the new ledger field:

```python
        entry = LedgerEntry(
            schema_version=CURRENT_LEDGER_SCHEMA_VERSION,
            label=args.label,
            timestamp=datetime.now().isoformat(timespec="seconds"),
            sims=args.sims,
            test_seasons=args.seasons,
            training_years=args.training_years,
            scoring=args.scoring,
            baseline=args.baseline,
            comparison_mode=comparison_mode,
            overrides=args.overrides,
            seed_mode=SEED_MODE,
            coverage_summary=coverage_summary,
            config_snapshot=arm_b_dict if args.overrides else defaults,
            season_results=all_season_metrics,
            weekly_summaries=weekly_summaries,
            directional_accuracy=dir_accuracy,
            promotion_evidence_scope=(
                "covered_only"
                if coverage_summary.get("market_history") is not None
                and coverage_summary["market_history"].enabled
                else None
            ),
        )
```

- [ ] **Step 4: Run the validation and ledger tests**

Run: `uv run pytest tests/test_validation/test_coverage.py tests/test_validation/test_validate_script.py tests/test_validation/test_ledger.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/validation/coverage.py src/fantasy_sim/validation/ledger.py scripts/validate.py tests/test_validation/test_coverage.py tests/test_validation/test_validate_script.py tests/test_validation/test_ledger.py
git commit -m "feat: add covered-season market validation reporting"
```

### Task 6: Run The Phase 3 Validation Artifact And Update The Roadmap/Audit Docs

**Files:**
- Modify: `docs/accuracy-roadmap.md:347-389, 562-568`
- Modify: `docs/accuracy-stack-audit.md:24-60, 80-100, 102-120, 255-376`

- [ ] **Step 1: Build the processed market-history cache for the covered seasons**

Run:

```bash
uv run python scripts/import_market_history.py --season 2023 2024
```

Expected:

- one line that ends with `market_history_weekly_2023.parquet`
- one line that ends with `market_history_weekly_2024.parquet`

- [ ] **Step 2: Run the labeled marginal validation artifact**

Run:

```bash
uv run python scripts/validate.py \
  --baseline defaults \
  --set market_history.enabled=true \
  --sims 50 \
  --label "phase-3-market-history-v1"
```

Expected header lines:

```text
coverage   : [contains `market_history=partial(2023,2024)`]
coverage notes: [contains `market_history:partial processed season parquet`]
```

Expected market-specific readout lines:

```text
MARKET HISTORY COVERED-SEASON READOUT
covered seasons   : 2023, 2024
uncovered seasons : 2022
promotion scope   : covered_only
```

- [ ] **Step 3: Update `docs/accuracy-roadmap.md` with the Phase 3 result**

Replace the Phase 3 section so it records:

```markdown
## Phase 3: Historical Market Intelligence

### Status

Implemented in v1 with covered-season promotion evidence.

Promotion artifact:

- label: `phase-3-market-history-v1`
- baseline: `defaults`
- comparison mode: `marginal_lift`
- coverage:
  - `market_history=partial(2023,2024)`
  - `market_history.open_fpts=partial(2023,2024)`
  - `market_history.close_fpts=partial(2023,2024)`
  - `market_history.dispersion=partial(2023,2024)`
  - `market_history.anytime_td=partial(2023,2024)`
- promotion evidence scope: `covered_only`
- uncovered season:
  - `2022` reported as no-data / uncovered and excluded from market-specific averages

### Implemented v1 Scope

- new top-level `market_history` config family
- processed historical market parquet for `2023-2024`
- post-sim `market_history` layer between `role_trend` and `ensemble.ff_opportunity`
- covered-season-only market readout in validation output
- ledger metadata recording covered-only promotion scope

### Follow-On Work

- `2022` backfill if a credible historical source is found
- richer market columns or alternate-line structure only after v1 evidence is settled
```

Then paste the exact three metric lines from the labeled validation output under the promotion artifact:

- the line that starts with `rank_corr delta:`
- the line that starts with `weekly_mae delta:`
- the line that starts with `season_mae delta:`

Update `## Immediate Next Planning Targets` so the next item after Phase 3 is Phase 4.

- [ ] **Step 4: Update `docs/accuracy-stack-audit.md` with the new defaults, runtime order, and caveats**

Make these exact content changes:

1. In `## Current Defaults`, add:

```markdown
- `availability.depth_charts.enabled: true`
- `availability.usage_fallback.enabled: true`
- `market_history.enabled: true`
```

2. In `## Runtime Order`, change the end-to-end projection flow to:

```markdown
15. Post-sim `role_trend` adjustment
16. Post-sim `market_history` adjustment
17. Post-sim `ensemble.ff_opportunity` blend
```

and add:

```markdown
- `market_history` is a post-sim layer and is not part of `GameContextBuilder`
- `market_history` participates in validation, `Backtester`, and the non-detail `week` / `season` / `game` CLI flows
- `player` and `--detail` CLI output still bypass post-sim layers
```

3. In `## Local Data Inventory`, add the new store:

```markdown
- historical market processed cache: `~/.fantasy-sim/market-history/processed/`
```

4. In `## Remaining Evaluation Caveats`, replace the old props-only caveat with:

```markdown
### 1. Historical market coverage is partial by season

Phase 3 v1 covers `2023-2024` only.

Implication:

- `2022` is explicitly uncovered for `market_history`
- market-specific promotion evidence must use covered seasons only
- stack-wide summaries may still show `2022`, but it must not be folded into market-layer averages as neutral evidence
```

5. In the audit inventory wording, update the PFF file-count note to:

```markdown
- processed PFF inventory currently observed locally:
  - `190` NFL parquet files
  - `105` NCAA parquet files
  - one stray `.DS_Store`
```

- [ ] **Step 5: Run the focused verification and commit**

Run:

```bash
uv run pytest tests/test_data/test_market_history tests/test_scoring/test_market_history.py tests/test_validation/test_market_history_pipeline.py tests/test_validation/test_coverage.py tests/test_validation/test_validate_script.py tests/test_validation/test_ledger.py -v
```

Expected: PASS

Then commit:

```bash
git add docs/accuracy-roadmap.md docs/accuracy-stack-audit.md
git commit -m "docs: record phase 3 market history status"
```

# Phase 1 FF Opportunity Ensemble Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a post-sim `ff_opportunity` ensemble layer that blends historical expected fantasy points into weekly player projections across QB/RB/WR/TE by default, validates it marginally against defaults, and closes the phase with roadmap/audit updates that reflect actual coverage and outcome.

**Architecture:** Add a new `ensemble` config family, a small `ff_opportunity` loader/normalizer keyed by nflverse `player_id`, and a post-projection blender reused by validation, backtester, and CLI. Keep `GameContextBuilder` unchanged, keep `ff_rankings` present only as a disabled future hook, make Phase 1 v1 cover QB/RB/WR/TE by default, and keep weekly QB/WR metrics as the primary success tie-breaker for the first decision.

**Tech Stack:** Python 3.12+, polars, pathlib, dataclasses, nflreadpy, pytest

**Spec:** `docs/superpowers/specs/2026-04-11-phase-1-ff-opportunity-ensemble-design.md`

---

### Task 1: Add Ensemble Config Family

**Files:**
- Create: `src/fantasy_sim/data/ensemble/__init__.py`
- Create: `src/fantasy_sim/data/ensemble/models.py`
- Create: `src/fantasy_sim/data/ensemble/config.py`
- Modify: `config/defaults.yaml`
- Test: `tests/test_data/test_ensemble/test_config.py`

- [ ] **Step 1: Write the failing config tests**

Create `tests/test_data/test_ensemble/test_config.py`:

```python
"""Tests for ensemble config loading."""

from fantasy_sim.data.ensemble.config import load_ensemble_config


def test_load_ensemble_config_defaults_disabled():
    cfg = load_ensemble_config({})
    assert cfg.enabled is False
    assert cfg.ff_opportunity.enabled is False
    assert cfg.ff_rankings.enabled is False
    assert cfg.ff_opportunity.feature == "total_fantasy_points_exp"
    assert cfg.ff_opportunity.positions == ("QB", "RB", "WR", "TE")
    assert cfg.ff_opportunity.weights == {
        "QB": 0.35,
        "RB": 0.15,
        "WR": 0.25,
        "TE": 0.15,
    }


def test_load_ensemble_config_reads_yaml_values():
    cfg = load_ensemble_config(
        {
            "ensemble": {
                "enabled": True,
                "ff_opportunity": {
                    "enabled": True,
                    "cache_dir": "/tmp/ensemble-cache",
                    "positions": ["QB", "RB", "WR", "TE"],
                    "feature": "total_fantasy_points_exp",
                    "weights": {"QB": 0.35, "RB": 0.15, "WR": 0.25, "TE": 0.15},
                    "min_coverage_weeks": 1,
                },
                "ff_rankings": {"enabled": False},
            }
        }
    )

    assert cfg.enabled is True
    assert cfg.ff_opportunity.enabled is True
    assert cfg.ff_opportunity.cache_dir == "/tmp/ensemble-cache"
    assert cfg.ff_opportunity.positions == ("QB", "RB", "WR", "TE")
    assert cfg.ff_opportunity.weights["QB"] == 0.35
    assert cfg.ff_opportunity.min_coverage_weeks == 1
    assert cfg.ff_rankings.enabled is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_data/test_ensemble/test_config.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'fantasy_sim.data.ensemble'`

- [ ] **Step 3: Implement the config models and loader**

Create `src/fantasy_sim/data/ensemble/__init__.py`:

```python
"""External-prior ensemble package."""
```

Create `src/fantasy_sim/data/ensemble/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FfOpportunityConfig:
    enabled: bool = False
    cache_dir: str | None = None
    positions: tuple[str, ...] = ("QB", "RB", "WR", "TE")
    feature: str = "total_fantasy_points_exp"
    weights: dict[str, float] = field(
        default_factory=lambda: {
            "QB": 0.35,
            "RB": 0.15,
            "WR": 0.25,
            "TE": 0.15,
        }
    )
    min_coverage_weeks: int = 1


@dataclass
class FfRankingsConfig:
    enabled: bool = False


@dataclass
class EnsembleConfig:
    enabled: bool = False
    ff_opportunity: FfOpportunityConfig = field(default_factory=FfOpportunityConfig)
    ff_rankings: FfRankingsConfig = field(default_factory=FfRankingsConfig)
```

Create `src/fantasy_sim/data/ensemble/config.py`:

```python
from __future__ import annotations

from fantasy_sim.data.ensemble.models import (
    EnsembleConfig,
    FfOpportunityConfig,
    FfRankingsConfig,
)


def load_ensemble_config(defaults: dict) -> EnsembleConfig:
    raw = defaults.get("ensemble", {})
    if not raw:
        return EnsembleConfig(enabled=False)

    opp_raw = raw.get("ff_opportunity", {})
    rankings_raw = raw.get("ff_rankings", {})

    return EnsembleConfig(
        enabled=raw.get("enabled", False),
        ff_opportunity=FfOpportunityConfig(
            enabled=opp_raw.get("enabled", False),
            cache_dir=opp_raw.get("cache_dir"),
            positions=tuple(opp_raw.get("positions", ["QB", "RB", "WR", "TE"])),
            feature=opp_raw.get("feature", "total_fantasy_points_exp"),
            weights=opp_raw.get(
                "weights",
                {"QB": 0.35, "WR": 0.25, "RB": 0.15, "TE": 0.15},
            ),
            min_coverage_weeks=opp_raw.get("min_coverage_weeks", 1),
        ),
        ff_rankings=FfRankingsConfig(
            enabled=rankings_raw.get("enabled", False),
        ),
    )
```

Add this block to `config/defaults.yaml` after `td_tendency`:

```yaml
ensemble:
  enabled: false
  ff_opportunity:
    enabled: false
    cache_dir: null
    positions: [QB, RB, WR, TE]
    feature: total_fantasy_points_exp
    weights:
      QB: 0.35
      RB: 0.15
      WR: 0.25
      TE: 0.15
    min_coverage_weeks: 1
  ff_rankings:
    enabled: false
```

- [ ] **Step 4: Run the config tests and the existing config smoke**

Run: `uv run pytest tests/test_data/test_ensemble/test_config.py tests/test_config -v`

Expected: PASS for the new ensemble config tests and no regressions in the existing config suite

- [ ] **Step 5: Commit**

```bash
git add config/defaults.yaml src/fantasy_sim/data/ensemble/__init__.py src/fantasy_sim/data/ensemble/models.py src/fantasy_sim/data/ensemble/config.py tests/test_data/test_ensemble/test_config.py
git commit -m "feat: add ensemble config family"
```

### Task 2: Add FF Opportunity Loader And Normalizer

**Files:**
- Create: `src/fantasy_sim/data/ensemble/loader.py`
- Create: `src/fantasy_sim/data/ensemble/normalizer.py`
- Test: `tests/test_data/test_ensemble/test_loader.py`
- Test: `tests/test_data/test_ensemble/test_normalizer.py`

- [ ] **Step 1: Write the failing loader and normalizer tests**

Create `tests/test_data/test_ensemble/test_loader.py`:

```python
from pathlib import Path
from unittest.mock import patch

import polars as pl

from fantasy_sim.data.ensemble.loader import FfOpportunityLoader
from fantasy_sim.data.ensemble.models import FfOpportunityConfig


def test_loader_fetches_and_caches_per_season(tmp_path):
    sample = pl.DataFrame(
        {
            "season": ["2024"],
            "week": [1.0],
            "player_id": ["00-0035228"],
            "full_name": ["Kyler Murray"],
            "position": ["QB"],
            "posteam": ["ARI"],
            "total_fantasy_points_exp": [14.91],
        }
    )
    config = FfOpportunityConfig(enabled=True, cache_dir=str(tmp_path))

    with patch("fantasy_sim.data.ensemble.loader.nflreadpy.load_ff_opportunity", return_value=sample) as mock_load:
        loader = FfOpportunityLoader(config)
        first = loader.load_weekly([2024])
        second = loader.load_weekly([2024])

    assert first.shape == (1, 7)
    assert second.shape == (1, 7)
    assert mock_load.call_count == 1
    assert (Path(tmp_path) / "ff_opportunity_weekly_2024.parquet").exists()
```

Create `tests/test_data/test_ensemble/test_normalizer.py`:

```python
import polars as pl

from fantasy_sim.data.ensemble.models import FfOpportunityConfig
from fantasy_sim.data.ensemble.normalizer import normalize_ff_opportunity


def test_normalizer_casts_keys_and_filters_positions():
    raw = pl.DataFrame(
        {
            "season": ["2024", "2024"],
            "week": [1.0, 1.0],
            "player_id": ["00-0035228", "00-0031234"],
            "full_name": ["Kyler Murray", "A Tight End"],
            "position": ["QB", "TE"],
            "posteam": ["ARI", "KC"],
            "total_fantasy_points_exp": [14.91, 8.10],
        }
    )

    cfg = FfOpportunityConfig(enabled=True, positions=("QB", "RB", "WR", "TE"))
    normalized = normalize_ff_opportunity(raw, cfg)

    assert normalized.columns == [
        "season",
        "week",
        "player_id",
        "name",
        "position",
        "team",
        "prior_fpts",
    ]
    assert normalized.shape == (2, 7)
    assert normalized.row(0) == (2024, 1, "00-0035228", "Kyler Murray", "QB", "ARI", 14.91)


def test_normalizer_drops_rows_missing_player_id_or_prior():
    raw = pl.DataFrame(
        {
            "season": ["2024", "2024"],
            "week": [1.0, 1.0],
            "player_id": [None, "00-0031234"],
            "full_name": ["Bad Row", "Also Bad"],
            "position": ["QB", "WR"],
            "posteam": ["ARI", "BUF"],
            "total_fantasy_points_exp": [10.0, None],
        }
    )

    normalized = normalize_ff_opportunity(raw, FfOpportunityConfig(enabled=True))
    assert normalized.is_empty()
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `uv run pytest tests/test_data/test_ensemble/test_loader.py tests/test_data/test_ensemble/test_normalizer.py -v`

Expected: FAIL with `ModuleNotFoundError` for the new loader and normalizer modules

- [ ] **Step 3: Implement the loader and normalizer**

Create `src/fantasy_sim/data/ensemble/loader.py`:

```python
from __future__ import annotations

from pathlib import Path

import nflreadpy
import polars as pl

from fantasy_sim.data.ensemble.models import FfOpportunityConfig
from fantasy_sim.data.loader import DEFAULT_CACHE_DIR


class FfOpportunityLoader:
    """Load and cache nflreadpy ff_opportunity weekly data."""

    def __init__(self, config: FfOpportunityConfig, cache_dir: Path | None = None) -> None:
        if cache_dir is not None:
            self.cache_dir = Path(cache_dir)
        elif config.cache_dir is not None:
            self.cache_dir = Path(config.cache_dir)
        else:
            self.cache_dir = DEFAULT_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, season: int) -> Path:
        return self.cache_dir / f"ff_opportunity_weekly_{season}.parquet"

    def load_weekly(self, seasons: list[int]) -> pl.DataFrame:
        frames: list[pl.DataFrame] = []
        for season in sorted(seasons):
            path = self._cache_path(season)
            if path.exists():
                frames.append(pl.read_parquet(path))
                continue
            df = nflreadpy.load_ff_opportunity(seasons=[season], stat_type="weekly")
            df.write_parquet(path)
            frames.append(df)
        if not frames:
            return pl.DataFrame()
        return pl.concat(frames, how="diagonal_relaxed")
```

Create `src/fantasy_sim/data/ensemble/normalizer.py`:

```python
from __future__ import annotations

import polars as pl

from fantasy_sim.data.ensemble.models import FfOpportunityConfig


def normalize_ff_opportunity(
    raw: pl.DataFrame,
    config: FfOpportunityConfig,
) -> pl.DataFrame:
    if raw.is_empty():
        return pl.DataFrame(
            schema={
                "season": pl.Int64,
                "week": pl.Int64,
                "player_id": pl.Utf8,
                "name": pl.Utf8,
                "position": pl.Utf8,
                "team": pl.Utf8,
                "prior_fpts": pl.Float64,
            }
        )

    feature = config.feature
    return (
        raw.with_columns(
            [
                pl.col("season").cast(pl.Int64, strict=False),
                pl.col("week").cast(pl.Int64, strict=False),
                pl.col("player_id").cast(pl.Utf8),
                pl.col("full_name").cast(pl.Utf8).alias("name"),
                pl.col("position").cast(pl.Utf8),
                pl.col("posteam").cast(pl.Utf8).alias("team"),
                pl.col(feature).cast(pl.Float64).alias("prior_fpts"),
            ]
        )
        .filter(pl.col("position").is_in(list(config.positions)))
        .filter(pl.col("player_id").is_not_null())
        .filter(pl.col("prior_fpts").is_not_null())
        .select(["season", "week", "player_id", "name", "position", "team", "prior_fpts"])
        .unique(subset=["season", "week", "player_id"], keep="first")
        .sort(["season", "week", "player_id"])
    )
```

- [ ] **Step 4: Run the focused ensemble data tests**

Run: `uv run pytest tests/test_data/test_ensemble/test_loader.py tests/test_data/test_ensemble/test_normalizer.py -v`

Expected: PASS and the loader writes `ff_opportunity_weekly_<season>.parquet` into the configured cache directory

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/ensemble/loader.py src/fantasy_sim/data/ensemble/normalizer.py tests/test_data/test_ensemble/test_loader.py tests/test_data/test_ensemble/test_normalizer.py
git commit -m "feat: add ff_opportunity loader and normalizer"
```

### Task 3: Add Post-Sim Projection Blender

**Files:**
- Create: `src/fantasy_sim/scoring/ensemble.py`
- Test: `tests/test_scoring/test_ensemble.py`

- [ ] **Step 1: Write the failing blender tests**

Create `tests/test_scoring/test_ensemble.py`:

```python
import polars as pl

from fantasy_sim.data.ensemble.models import EnsembleConfig, FfOpportunityConfig
from fantasy_sim.scoring.ensemble import FfOpportunityProjectionEnsembler


class _StubLoader:
    def __init__(self, df: pl.DataFrame):
        self._df = df
        self.calls = 0

    def load_weekly(self, seasons: list[int]) -> pl.DataFrame:
        self.calls += 1
        return self._df


def _config() -> EnsembleConfig:
    return EnsembleConfig(
        enabled=True,
        ff_opportunity=FfOpportunityConfig(
            enabled=True,
            positions=("QB", "RB", "WR", "TE"),
            weights={"QB": 0.5, "WR": 0.25, "RB": 0.15, "TE": 0.15},
        ),
    )


def test_blend_week_updates_fpts_and_recomputes_rank():
    raw = pl.DataFrame(
        {
            "season": [2024, 2024],
            "week": [1, 1],
            "player_id": ["QB1", "WR1"],
            "name": ["QB One", "WR One"],
            "position": ["QB", "WR"],
            "team": ["KC", "KC"],
            "prior_fpts": [20.0, 12.0],
        }
    )
    ensembler = FfOpportunityProjectionEnsembler(_config(), loader=_StubLoader(raw))
    projections = [
        {"player_id": "QB1", "name": "QB One", "position": "QB", "team": "KC", "fpts": 10.0, "rank": 2},
        {"player_id": "WR1", "name": "WR One", "position": "WR", "team": "KC", "fpts": 11.0, "rank": 1},
    ]

    blended, stats = ensembler.blend_week(projections, season=2024, week=1)

    assert blended[0]["player_id"] == "QB1"
    assert blended[0]["fpts"] == 15.0
    assert blended[0]["rank"] == 1
    assert blended[1]["player_id"] == "WR1"
    assert blended[1]["fpts"] == 11.2
    assert stats.covered_rows == 2
    assert stats.uncovered_rows == 0


def test_blend_week_leaves_uncovered_rows_unchanged():
    raw = pl.DataFrame(
        {
            "season": [2024],
            "week": [1],
            "player_id": ["QB1"],
            "name": ["QB One"],
            "position": ["QB"],
            "team": ["KC"],
            "prior_fpts": [20.0],
        }
    )
    ensembler = FfOpportunityProjectionEnsembler(_config(), loader=_StubLoader(raw))
    projections = [
        {"player_id": "QB1", "name": "QB One", "position": "QB", "team": "KC", "fpts": 10.0, "rank": 2},
        {"player_id": "RB1", "name": "RB One", "position": "RB", "team": "KC", "fpts": 13.0, "rank": 1, "rush_yards": 70.0},
    ]

    blended, stats = ensembler.blend_week(projections, season=2024, week=1)

    rb = next(row for row in blended if row["player_id"] == "RB1")
    assert rb["fpts"] == 13.0
    assert rb["rush_yards"] == 70.0
    assert stats.covered_rows == 1
    assert stats.uncovered_rows == 1
```

- [ ] **Step 2: Run the new scoring tests to verify they fail**

Run: `uv run pytest tests/test_scoring/test_ensemble.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'fantasy_sim.scoring.ensemble'`

- [ ] **Step 3: Implement the ensemble blender**

Create `src/fantasy_sim/scoring/ensemble.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from fantasy_sim.data.ensemble.loader import FfOpportunityLoader
from fantasy_sim.data.ensemble.models import EnsembleConfig
from fantasy_sim.data.ensemble.normalizer import normalize_ff_opportunity


@dataclass
class BlendStats:
    total_rows: int = 0
    covered_rows: int = 0
    uncovered_rows: int = 0


class FfOpportunityProjectionEnsembler:
    """Blend ff_opportunity priors onto final projection rows."""

    def __init__(
        self,
        config: EnsembleConfig,
        *,
        loader: FfOpportunityLoader | None = None,
    ) -> None:
        self._config = config
        self._loader = loader or FfOpportunityLoader(config.ff_opportunity)
        self._prior_cache: dict[int, pl.DataFrame] = {}

    def _season_priors(self, season: int) -> pl.DataFrame:
        if season not in self._prior_cache:
            raw = self._loader.load_weekly([season])
            self._prior_cache[season] = normalize_ff_opportunity(
                raw,
                self._config.ff_opportunity,
            )
        return self._prior_cache[season]

    def blend_week(
        self,
        projections: list[dict],
        *,
        season: int,
        week: int,
    ) -> tuple[list[dict], BlendStats]:
        stats = BlendStats(total_rows=len(projections))
        if (
            not self._config.enabled
            or not self._config.ff_opportunity.enabled
            or not projections
        ):
            stats.uncovered_rows = len(projections)
            return projections, stats

        priors = self._season_priors(season).filter(pl.col("week") == week)
        prior_map = {
            row["player_id"]: row
            for row in priors.iter_rows(named=True)
        }

        blended: list[dict] = []
        for proj in projections:
            row = dict(proj)
            prior = prior_map.get(row["player_id"])
            weight = self._config.ff_opportunity.weights.get(row["position"], 0.0)
            if prior is None or weight <= 0:
                row["ensemble_source"] = None
                row["ensemble_weight"] = 0.0
                row["ensemble_covered"] = False
                blended.append(row)
                stats.uncovered_rows += 1
                continue

            row["ensemble_source"] = "ff_opportunity"
            row["ensemble_weight"] = weight
            row["ensemble_covered"] = True
            row["ensemble_prior_fpts"] = round(float(prior["prior_fpts"]), 2)
            row["fpts"] = round(float(row["fpts"] * (1.0 - weight) + prior["prior_fpts"] * weight), 1)
            blended.append(row)
            stats.covered_rows += 1

        blended.sort(key=lambda item: item["fpts"], reverse=True)
        for idx, row in enumerate(blended, start=1):
            row["rank"] = idx
        return blended, stats
```

- [ ] **Step 4: Run the new scoring tests and the projection regression suite**

Run: `uv run pytest tests/test_scoring/test_ensemble.py tests/test_scoring/test_projections.py -v`

Expected: PASS for the new blender tests and no regression in the existing projection builders

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/scoring/ensemble.py tests/test_scoring/test_ensemble.py
git commit -m "feat: add ff_opportunity projection blender"
```

### Task 4: Wire Ensemble Into Validation And Backtester

**Files:**
- Modify: `scripts/validate.py`
- Modify: `src/fantasy_sim/validation/coverage.py`
- Modify: `src/fantasy_sim/validation/backtester.py`
- Modify: `tests/test_validation/test_coverage.py`
- Modify: `tests/test_validation/test_validate_script.py`
- Modify: `tests/test_validation/test_backtester.py`

- [ ] **Step 1: Write the failing validation and backtester tests**

Add this test to `tests/test_validation/test_coverage.py`:

```python
def test_ensemble_ff_opportunity_reports_full_when_enabled():
    coverage = collect_signal_coverage(
        {
            "ensemble": {
                "enabled": True,
                "ff_opportunity": {"enabled": True},
                "ff_rankings": {"enabled": False},
            }
        },
        [2022, 2023, 2024],
    )

    assert coverage["ensemble.ff_opportunity"] == SignalCoverage(
        enabled=True,
        status="full",
        covered_seasons=[2022, 2023, 2024],
        missing_seasons=[],
        note=(
            "nflreadpy historical ff_opportunity coverage is treated as available "
            "for requested test seasons; player mapping coverage is measured at runtime"
        ),
    )
```

Add this test to `tests/test_validation/test_validate_script.py`:

```python
def test_run_season_applies_ff_opportunity_ensemble_to_arm_b_only():
    validate = _load_validate_module()

    build_a = [
        {
            "status": "ok",
            "game_id": "2024_01_KC_BUF",
            "seed": 42,
            "week": 1,
            "home": "KC",
            "away": "BUF",
            "home_dists": object(),
            "away_dists": object(),
            "home_roster": object(),
            "away_roster": object(),
        }
    ]
    build_b = [
        {
            "status": "ok",
            "game_id": "2024_01_KC_BUF",
            "seed": 42,
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
                    "player_id": "QB0",
                    "name": "QB Zero",
                    "position": "QB",
                    "team": "KC",
                    "fpts": 9.0,
                }
            ],
            metadata={"arm": "a"},
        ),
        SimpleNamespace(
            game_id="2024_01_KC_BUF",
            projections=[
                {
                    "player_id": "QB1",
                    "name": "QB One",
                    "position": "QB",
                    "team": "KC",
                    "fpts": 10.0,
                }
            ],
            metadata={"arm": "b"},
        )
    ]

    with patch.object(validate, "build_games_parallel", side_effect=[build_a, build_b]), \
         patch.object(validate, "simulate_games_parallel", return_value=sim_results), \
         patch.object(validate, "load_actual_scores", return_value=[]), \
         patch.object(validate, "DataLoader") as mock_loader_cls, \
         patch.object(validate, "FfOpportunityProjectionEnsembler") as mock_ensembler_cls:
        mock_loader = mock_loader_cls.return_value
        mock_loader.cache_dir = Path("/tmp/cache")
        mock_loader.load_schedules.return_value = pl.DataFrame([
            {"season": 2024, "week": 1, "game_id": "2024_01_KC_BUF", "home_team": "KC", "away_team": "BUF"}
        ])
        mock_loader.load_player_stats.return_value = pl.DataFrame({"season": pl.Series([], dtype=pl.Int32)})

        mock_ensembler = mock_ensembler_cls.return_value
        mock_ensembler.blend_week.return_value = (
            [
                {
                    "player_id": "QB1",
                    "name": "QB One",
                    "position": "QB",
                    "team": "KC",
                    "fpts": 12.0,
                }
            ],
            SimpleNamespace(covered_rows=1, uncovered_rows=0),
        )

        validate.run_season(
            test_season=2024,
            n_sims=10,
            scoring_config={},
            num_training_seasons=3,
            arm_a_configs={
                "pff_config": object(),
                "weather_config": None,
                "vegas_config": None,
                "props_config": None,
                "usage_config": None,
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
                "game_script_config": None,
                "goal_line_concentration_config": None,
                "td_tendency_config": None,
            },
            arm_a_ensemble_config=None,
            arm_b_ensemble_config=object(),
            positions=["QB"],
            max_workers=1,
        )

    mock_ensembler_cls.assert_called_once()
    mock_ensembler.blend_week.assert_called_once_with(
        sim_results[1].projections,
        season=2024,
        week=1,
    )
```

Add this test to `tests/test_validation/test_backtester.py`:

```python
@patch("fantasy_sim.validation.backtester.FfOpportunityProjectionEnsembler")
@patch("fantasy_sim.validation.backtester.simulate_games_parallel")
@patch("fantasy_sim.validation.backtester.build_games_parallel")
@patch("fantasy_sim.validation.backtester.DataLoader")
def test_backtester_applies_ensemble_when_config_present(
    mock_loader_cls,
    mock_build_parallel,
    mock_simulate,
    mock_ensembler_cls,
):
    mock_loader = MagicMock()
    mock_loader_cls.return_value = mock_loader
    mock_loader.cache_dir = "/tmp/test"
    mock_loader.load_schedules.return_value = pl.DataFrame([
        {"season": 2024, "week": 1, "game_id": "2024_01_KC_BUF", "home_team": "KC", "away_team": "BUF"},
    ])
    mock_loader.load_player_stats.return_value = pl.DataFrame({"season": pl.Series([], dtype=pl.Int32)})
    mock_build_parallel.return_value = [_make_ok_result("2024_01_KC_BUF")]
    mock_simulate.return_value = [
        MagicMock(
            game_id="2024_01_KC_BUF",
            projections=[{"player_id": "QB1", "name": "QB One", "position": "QB", "team": "KC", "fpts": 10.0}],
        )
    ]
    mock_ensembler_cls.return_value.blend_week.return_value = (
        [{"player_id": "QB1", "name": "QB One", "position": "QB", "team": "KC", "fpts": 12.0}],
        MagicMock(covered_rows=1, uncovered_rows=0),
    )

    from fantasy_sim.data.ensemble.models import EnsembleConfig, FfOpportunityConfig

    bt = Backtester(
        test_season=2024,
        n_sims=10,
        ensemble_config=EnsembleConfig(enabled=True, ff_opportunity=FfOpportunityConfig(enabled=True)),
    )
    bt.loader = mock_loader
    from fantasy_sim.config.loader import load_defaults, resolve_scoring
    scoring_config = resolve_scoring(load_defaults()["scoring"], "ppr")
    bt.run(scoring_config)

    mock_ensembler_cls.assert_called_once()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_validation/test_coverage.py tests/test_validation/test_validate_script.py tests/test_validation/test_backtester.py -v`

Expected: FAIL because the coverage helper does not expose `ensemble.ff_opportunity` yet and validation/backtester do not import or apply the new ensembler

- [ ] **Step 3: Implement validation and backtester integration**

Update `src/fantasy_sim/validation/coverage.py` by adding this entry to the
`return { ... }` mapping inside `collect_signal_coverage()`:

```python
    ensemble_enabled = _signal_enabled(
        config,
        ("ensemble",),
        ("ensemble",),
    )
    ff_opp_enabled = _signal_enabled(
        config,
        ("ensemble",),
        ("ensemble", "ff_opportunity"),
        nested_path=("ff_opportunity",),
    )
```

```python
        "ensemble.ff_opportunity": _build_signal(
            ensemble_enabled and ff_opp_enabled,
            seasons,
            seasons,
            note=(
                "nflreadpy historical ff_opportunity coverage is treated as available "
                "for requested test seasons; player mapping coverage is measured at runtime"
            ),
        ),
```

Update the imports and config resolution in `scripts/validate.py`:

```python
from fantasy_sim.data.ensemble.config import load_ensemble_config
from fantasy_sim.scoring.ensemble import FfOpportunityProjectionEnsembler
```

```python
    arm_a_ensemble_config = (
        load_ensemble_config(defaults) if args.baseline == "defaults" else None
    )
    if arm_a_ensemble_config is not None and not arm_a_ensemble_config.enabled:
        arm_a_ensemble_config = None

    arm_b_ensemble_config = load_ensemble_config(arm_b_dict)
    if not arm_b_ensemble_config.enabled:
        arm_b_ensemble_config = None
```

Update the `run_season()` signature:

```python
def run_season(
    test_season: int,
    n_sims: int,
    scoring_config: dict,
    num_training_seasons: int,
    arm_a_configs: dict,
    arm_b_configs: dict,
    arm_a_ensemble_config: object | None,
    arm_b_ensemble_config: object | None,
    positions: list[str],
    max_workers: int,
    cached_arm_a: dict | None = None,
) -> dict:
```

Instantiate the ensemblers near the top of `run_season()`:

```python
    arm_a_ensembler = (
        FfOpportunityProjectionEnsembler(arm_a_ensemble_config)
        if arm_a_ensemble_config is not None
        else None
    )
    arm_b_ensembler = (
        FfOpportunityProjectionEnsembler(arm_b_ensemble_config)
        if arm_b_ensemble_config is not None
        else None
    )
```

Apply the blend before indexing projection rows in each simulation branch:

```python
        for result in sim_b:
            spec = spec_by_id_b[result.game_id]
            projections = result.projections
            if arm_b_ensembler is not None:
                projections, _ = arm_b_ensembler.blend_week(
                    projections,
                    season=test_season,
                    week=spec.week,
                )
            for proj in projections:
                pid = proj["player_id"]
                arm_b_proj[pid][spec.week] = proj["fpts"]
```

```python
        for result in sim_all:
            is_arm_a = result.metadata.get("arm") == "a"
            spec = spec_by_id_a[result.game_id] if is_arm_a else spec_by_id_b[result.game_id]
            ensembler = arm_a_ensembler if is_arm_a else arm_b_ensembler
            projections = result.projections
            if ensembler is not None:
                projections, _ = ensembler.blend_week(
                    projections,
                    season=test_season,
                    week=spec.week,
                )
            proj_dict = arm_a_proj if is_arm_a else arm_b_proj
            meta_dict = arm_a_meta if is_arm_a else arm_b_meta
            for proj in projections:
                pid = proj["player_id"]
                proj_dict[pid][spec.week] = proj["fpts"]
```

Pass the new args from `main()` into every `run_season()` call:

```python
                    arm_a_ensemble_config=arm_a_ensemble_config,
                    arm_b_ensemble_config=arm_b_ensemble_config,
```

Update `src/fantasy_sim/validation/backtester.py` imports and constructor:

```python
from fantasy_sim.data.ensemble.models import EnsembleConfig
from fantasy_sim.scoring.ensemble import FfOpportunityProjectionEnsembler
```

```python
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
        ensemble_config: EnsembleConfig | None = None,
        max_workers: int = 1,
    ):
        # existing assignments...
        self._ensemble_config = ensemble_config
```

Blend projections in `Backtester.run()` before indexing:

```python
        ensembler = (
            FfOpportunityProjectionEnsembler(self._ensemble_config)
            if self._ensemble_config is not None and self._ensemble_config.enabled
            else None
        )

        for result in sim_results:
            spec = spec_by_id[result.game_id]
            wk = spec.week
            projections = result.projections
            if ensembler is not None:
                projections, _ = ensembler.blend_week(
                    projections,
                    season=self.test_season,
                    week=wk,
                )
            for proj in projections:
                pid = proj["player_id"]
                projected_by_player_week[pid][wk] = proj["fpts"]
```

- [ ] **Step 4: Run the validation and backtester tests**

Run: `uv run pytest tests/test_validation/test_coverage.py tests/test_validation/test_validate_script.py tests/test_validation/test_backtester.py -v`

Expected: PASS, including the new `ensemble.ff_opportunity` coverage assertion and the new ensembler plumbing checks

- [ ] **Step 5: Commit**

```bash
git add scripts/validate.py src/fantasy_sim/validation/coverage.py src/fantasy_sim/validation/backtester.py tests/test_validation/test_coverage.py tests/test_validation/test_validate_script.py tests/test_validation/test_backtester.py
git commit -m "feat: wire ensemble into validation and backtester"
```

### Task 5: Wire Ensemble Into CLI Projection Commands

**Files:**
- Modify: `src/fantasy_sim/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write the failing CLI tests**

Add this test to `tests/test_cli.py`:

```python
    @patch("fantasy_sim.cli.FfOpportunityProjectionEnsembler")
    @patch("fantasy_sim.cli.load_ensemble_config")
    @patch("fantasy_sim.cli.GameContextBuilder")
    @patch("fantasy_sim.cli.DataLoader")
    def test_week_command_applies_ensemble_when_enabled(
        self,
        MockLoader,
        MockBuilder,
        mock_load_ensemble_config,
        mock_ensembler_cls,
        runner,
    ):
        from fantasy_sim.data.ensemble.models import EnsembleConfig, FfOpportunityConfig

        _wire_mocks(MockLoader, MockBuilder, [
            {"season": 2024, "week": 1, "game_id": "g1", "home_team": "KC", "away_team": "BUF"},
        ])
        mock_load_ensemble_config.return_value = EnsembleConfig(
            enabled=True,
            ff_opportunity=FfOpportunityConfig(enabled=True),
        )
        mock_ensembler_cls.return_value.blend_week.return_value = (
            [{"player_id": "KC_QB", "name": "QB", "position": "QB", "team": "KC", "fpts": 99.0, "rank": 1}],
            MagicMock(covered_rows=1, uncovered_rows=0),
        )

        result = runner.invoke(main, ["week", "1", "--season", "2024", "--sims", "10"])
        assert result.exit_code == 0
        mock_ensembler_cls.return_value.blend_week.assert_called()
```

- [ ] **Step 2: Run the CLI test to verify it fails**

Run: `uv run pytest tests/test_cli.py -k ensemble -v`

Expected: FAIL because `cli.py` does not yet import the ensemble config loader or call an ensembler helper

- [ ] **Step 3: Implement a shared CLI ensemble hook**

Update the imports in `src/fantasy_sim/cli.py`:

```python
from fantasy_sim.data.ensemble.config import load_ensemble_config
from fantasy_sim.scoring.ensemble import FfOpportunityProjectionEnsembler
```

Add these helpers near `_make_builder()`:

```python
def _make_ensembler(defaults: dict) -> FfOpportunityProjectionEnsembler | None:
    ensemble_config = load_ensemble_config(defaults)
    if not ensemble_config.enabled or not ensemble_config.ff_opportunity.enabled:
        return None
    return FfOpportunityProjectionEnsembler(ensemble_config)


def _maybe_blend_player_projs(
    player_projs: list[dict],
    *,
    ensembler: FfOpportunityProjectionEnsembler | None,
    season: int,
    week: int,
) -> list[dict]:
    if ensembler is None:
        return player_projs
    blended, _ = ensembler.blend_week(
        player_projs,
        season=season,
        week=week,
    )
    return blended
```

In `week()`, load defaults once and create the ensembler before the game loop:

```python
    defaults = load_defaults()
    ensembler = _make_ensembler(defaults)
```

Blend each game batch before appending:

```python
            if detail:
                from fantasy_sim.scoring.projections import build_detailed_projections
                player_batch = build_detailed_projections(results.games, scoring_config)
            else:
                player_batch = build_player_projections(results.games, scoring_config)
            player_batch = _maybe_blend_player_projs(
                player_batch,
                ensembler=ensembler,
                season=season,
                week=week_num,
            )
```

In `season()`, create the ensembler once and blend each weekly batch before assigning `week`:

```python
    defaults = load_defaults()
    ensembler = _make_ensembler(defaults)
```

```python
                if detail:
                    from fantasy_sim.scoring.projections import build_detailed_projections
                    player_batch = build_detailed_projections(results.games, scoring_config)
                else:
                    player_batch = build_player_projections(results.games, scoring_config)
                player_batch = _maybe_blend_player_projs(
                    player_batch,
                    ensembler=ensembler,
                    season=season_year,
                    week=wk,
                )
```

In `game()` and `player()`, apply the same helper after building `player_projs` / `all_projs`:

```python
    defaults = load_defaults()
    ensembler = _make_ensembler(defaults)
```

```python
    player_projs = _maybe_blend_player_projs(
        player_projs,
        ensembler=ensembler,
        season=season,
        week=week_num,
    )
```

```python
    all_projs = _maybe_blend_player_projs(
        all_projs,
        ensembler=ensembler,
        season=season,
        week=week_num,
    )
```

In `backtest()`, pass the ensemble config through to the backtester:

```python
    ensemble_config = load_ensemble_config(defaults)
```

```python
    bt = Backtester(
        test_season=season,
        n_sims=sims,
        num_training_seasons=training_years,
        scoring_format=scoring,
        pff_config=pff_config,
        weather_config=weather_config,
        vegas_config=vegas_config,
        usage_config=usage_config,
        ensemble_config=ensemble_config,
    )
```

- [ ] **Step 4: Run the CLI suite**

Run: `uv run pytest tests/test_cli.py -v`

Expected: PASS, including the new ensemble-enabled week command regression test

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/cli.py tests/test_cli.py
git commit -m "feat: apply ensemble in cli projection flows"
```

### Task 6: Run Phase 1 A/B, Update Roadmap/Audit, And Verify

**Files:**
- Modify: `docs/accuracy-roadmap.md`
- Modify: `docs/accuracy-stack-audit.md`

- [ ] **Step 1: Run the focused regression suite before the A/B**

Run:

```bash
uv run pytest \
  tests/test_data/test_ensemble/test_config.py \
  tests/test_data/test_ensemble/test_loader.py \
  tests/test_data/test_ensemble/test_normalizer.py \
  tests/test_scoring/test_ensemble.py \
  tests/test_validation/test_coverage.py \
  tests/test_validation/test_validate_script.py \
  tests/test_validation/test_backtester.py \
  tests/test_cli.py -v
```

Expected: PASS with the new ensemble tests and no regressions in the touched validation/CLI paths

- [ ] **Step 2: Run the Phase 1 marginal A/B**

Run:

```bash
uv run python scripts/validate.py \
  --baseline defaults \
  --set ensemble.enabled=true \
  --set ensemble.ff_opportunity.enabled=true \
  --sims 50 \
  --label "phase-1-ff-opportunity-v1"
```

Expected:

- the header shows `baseline=defaults`
- coverage includes `ensemble.ff_opportunity`
- the ledger appends a new labeled run
- the run yields a clean marginal comparison for `ff_opportunity` only

- [ ] **Step 3: Update `docs/accuracy-roadmap.md` with the actual Phase 1 outcome**

If the run passes the promotion gate, replace the Phase 1 section opener with:

```markdown
## Phase 1: External Fantasy Priors And Opportunity Ensemble

### Status

Implemented and promoted around `ff_opportunity` v1.

Phase 1 v1 scope was intentionally narrow:

- `ff_opportunity` only
- QB/RB/WR/TE covered by default
- post-sim weekly projection blend only
- no upstream usage/share mutation
- weekly QB/WR metrics kept as the primary promotion tie-breaker
- `ff_rankings` kept as a future plug-in, not part of the v1 gate

### Implemented v1 Design

- new `ensemble` config family
- `ff_opportunity` loader/cache and normalized player-week priors
- final-layer fantasy-point blend with position-specific weights
- explicit coverage-aware marginal validation against `baseline=defaults`

### Next Priority

Phase 2 remains the next implementation priority.

`ff_rankings` is still available as a future extension of the same ensemble family,
but it is not required to interpret the Phase 1 result.
```

If the run fails the promotion gate, replace the Phase 1 section opener with:

```markdown
## Phase 1: External Fantasy Priors And Opportunity Ensemble

### Status

Implemented but not promoted from the first `ff_opportunity` v1 run.

The phase still delivered the intended evaluation artifact:

- `ff_opportunity` isolated as the only v1 external prior
- QB/RB/WR/TE covered by default
- post-sim weekly projection blend only
- no upstream usage/share mutation
- weekly QB/WR metrics kept as the primary promotion tie-breaker
- `ff_rankings` kept out of the first gate

### Outcome

The first marginal A/B result did not clear the weekly QB/WR improvement gate
without material season regression, so the implementation should remain available
behind config while follow-up tuning is evaluated.

### Next Priority

Phase 2 remains the next implementation priority unless a narrower Phase 1 follow-up
is explicitly approved.
```

- [ ] **Step 4: Update `docs/accuracy-stack-audit.md` with current defaults, coverage, and caveats**

If Phase 1 is promoted, add or update these bullets under `Current Defaults`:

```markdown
- `ensemble.enabled: true`
- `ensemble.ff_opportunity.enabled: true`
- `ensemble.ff_rankings.enabled: false`
```

If Phase 1 is not promoted, add or update these bullets under `Built but currently parked or disabled`:

```markdown
- `ensemble.enabled: false`
- `ensemble.ff_opportunity.enabled: false`
- `ensemble.ff_rankings.enabled: false`
```

In the local data / evaluation caveats sections, add this exact note:

```markdown
### FF Opportunity Coverage

Verified for Phase 1 v1:

- `nflreadpy.load_ff_opportunity(..., stat_type="weekly")` is the required v1 source
- the Phase 1 gate used `total_fantasy_points_exp` as the prior feature
- player-week joins used nflverse `player_id` directly
- uncovered rows remained neutral instead of forcing a fallback match

`ff_rankings` remains intentionally out of the v1 success criteria pending a clean
historical coverage, schema stability, and backtest-year availability check.
```

- [ ] **Step 5: Final verification and commit**

Run a quick CLI smoke after the docs update:

```bash
uv run fantasy-sim week 1 --season 2024 --sims 10
uv run fantasy-sim backtest --season 2024 --sims 10
```

Expected: both commands complete without crashing and honor the current defaults stack

Then commit:

```bash
git add docs/accuracy-roadmap.md docs/accuracy-stack-audit.md
git commit -m "docs: close Phase 1 ff_opportunity ensemble"
```

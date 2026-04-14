# Phase 5 RB Scheme-Fit Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a default-off PFF `rb_scheme_fit` engine that converts RB directional fit from `rushing_direction` plus offense scheme/blocking context from `offense_run_blocking` into bounded pre-sim `rushing_yards_dist` adjustments, with explicit validation coverage and Phase 5 documentation updates.

**Architecture:** Add a new `pff.rb_scheme_fit` config family and typed model, implement `RbSchemeFitEngine.compute()` to flatten nested `rushing_direction` rows into RB runner profiles, combine those profiles with team gap-versus-zone context from `offense_run_blocking`, and return per-RB rushing factors. Wire `GameContextBuilder` to apply those factors after matchup/tier and before qb-split, while keeping the runtime surface narrow: mutate only RB `rushing_yards_dist`, never carry shares, TD factors, or team play-calling.

**Tech Stack:** Python 3.13/3.14, polars, numpy, pytest, YAML config, Click validation CLI

---

## File Structure

- `config/defaults.yaml`
  - shipped default-off `pff.rb_scheme_fit` settings
- `src/fantasy_sim/data/pff/models.py`
  - `RbSchemeFitConfig` and `RbSchemeFitFactors`
- `src/fantasy_sim/data/pff/config.py`
  - parse `pff.rb_scheme_fit` into `PffConfig`
- `src/fantasy_sim/data/pff/rb_scheme_fit.py`
  - `RbSchemeFitEngine`, direction flattening, runner-profile helpers, team-scheme helpers, fit-factor calculation
- `src/fantasy_sim/data/game_context.py`
  - engine construction, runtime ordering, `_apply_rb_scheme_fit()` helper
- `src/fantasy_sim/validation/coverage.py`
  - `pff.rb_scheme_fit` coverage reporting
- `tests/test_data/test_pff/test_config.py`
  - direct config loader tests for `pff.rb_scheme_fit`
- `tests/test_validation/test_config.py`
  - override propagation tests for `pff.rb_scheme_fit`
- `tests/test_validation/test_coverage.py`
  - `pff.rb_scheme_fit` coverage tests
- `tests/test_data/test_pff/test_rb_scheme_fit.py`
  - engine unit tests
- `tests/test_data/test_pff/test_rb_scheme_fit_integration.py`
  - builder wiring and mutation-boundary tests
- `docs/accuracy-roadmap.md`
  - Phase 5 status/result update after validation
- `docs/accuracy-stack-audit.md`
  - defaults/runtime/result update after validation

### Task 1: Add The `pff.rb_scheme_fit` Config Family

**Files:**
- Modify: `config/defaults.yaml`
- Modify: `src/fantasy_sim/data/pff/models.py`
- Modify: `src/fantasy_sim/data/pff/config.py`
- Test: `tests/test_data/test_pff/test_config.py`
- Test: `tests/test_validation/test_config.py`

- [ ] **Step 1: Write the failing config tests**

Add these tests near the existing `qb_split` config tests in `tests/test_data/test_pff/test_config.py` and `tests/test_validation/test_config.py`:

```python
def test_load_pff_config_rb_scheme_fit_defaults():
    cfg = load_pff_config({"pff": {"enabled": True}})

    assert isinstance(cfg.rb_scheme_fit, RbSchemeFitConfig)
    assert cfg.rb_scheme_fit.enabled is False
    assert cfg.rb_scheme_fit.rush_yards_sensitivity == 0.10
    assert cfg.rb_scheme_fit.factor_clamp == (0.94, 1.06)
    assert cfg.rb_scheme_fit.min_attempts == 20
    assert cfg.rb_scheme_fit.min_games == 4
    assert cfg.rb_scheme_fit.early_season_blend is True
    assert cfg.rb_scheme_fit.scheme_usage_weight == 0.65
    assert cfg.rb_scheme_fit.blocking_alignment_weight == 0.35


def test_load_pff_config_rb_scheme_fit_custom_values():
    cfg = load_pff_config(
        {
            "pff": {
                "enabled": True,
                "rb_scheme_fit": {
                    "enabled": True,
                    "rush_yards_sensitivity": 0.14,
                    "factor_clamp": [0.95, 1.05],
                    "min_attempts": 24,
                    "min_games": 5,
                    "early_season_blend": False,
                    "scheme_usage_weight": 0.70,
                    "blocking_alignment_weight": 0.30,
                },
            }
        }
    )

    assert cfg.rb_scheme_fit.enabled is True
    assert cfg.rb_scheme_fit.rush_yards_sensitivity == 0.14
    assert cfg.rb_scheme_fit.factor_clamp == (0.95, 1.05)
    assert cfg.rb_scheme_fit.min_attempts == 24
    assert cfg.rb_scheme_fit.min_games == 5
    assert cfg.rb_scheme_fit.early_season_blend is False
    assert cfg.rb_scheme_fit.scheme_usage_weight == 0.70
    assert cfg.rb_scheme_fit.blocking_alignment_weight == 0.30


def test_pff_rb_scheme_fit_override_propagates():
    defaults = load_defaults()
    overridden = apply_overrides(
        defaults,
        [
            "pff.rb_scheme_fit.enabled=true",
            "pff.rb_scheme_fit.rush_yards_sensitivity=0.13",
            "pff.rb_scheme_fit.min_attempts=26",
            "pff.rb_scheme_fit.scheme_usage_weight=0.60",
        ],
    )

    configs = build_engine_configs(overridden)

    assert configs["pff_config"] is not None
    assert configs["pff_config"].rb_scheme_fit.enabled is True
    assert configs["pff_config"].rb_scheme_fit.rush_yards_sensitivity == 0.13
    assert configs["pff_config"].rb_scheme_fit.min_attempts == 26
    assert configs["pff_config"].rb_scheme_fit.scheme_usage_weight == 0.60
```

- [ ] **Step 2: Run the config tests to verify they fail**

Run:

```bash
uv run pytest tests/test_data/test_pff/test_config.py tests/test_validation/test_config.py -k "rb_scheme_fit" -v
```

Expected: FAIL with `AttributeError: 'PffConfig' object has no attribute 'rb_scheme_fit'` or equivalent parser/override failures.

- [ ] **Step 3: Write the minimal config implementation**

Add this block under `pff:` in `config/defaults.yaml` after `depth_role` and before `qb_split`:

```yaml
  rb_scheme_fit:
    enabled: false
    rush_yards_sensitivity: 0.10
    factor_clamp: [0.94, 1.06]
    min_attempts: 20
    min_games: 4
    early_season_blend: true
    scheme_usage_weight: 0.65
    blocking_alignment_weight: 0.35
```

Add these dataclasses in `src/fantasy_sim/data/pff/models.py` above `QbSplitConfig`:

```python
@dataclass
class RbSchemeFitConfig:
    """Configuration for RB scheme-fit adjustments."""
    enabled: bool = False
    rush_yards_sensitivity: float = 0.10
    factor_clamp: tuple[float, float] = (0.94, 1.06)
    min_attempts: int = 20
    min_games: int = 4
    early_season_blend: bool = True
    scheme_usage_weight: float = 0.65
    blocking_alignment_weight: float = 0.35


@dataclass
class RbSchemeFitFactors:
    """Per-RB bounded rushing-efficiency adjustment."""
    rushing_yards_factor: float = 1.0
```

Thread the field into `PffConfig`:

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
    coverage: CoverageConfig = field(default_factory=CoverageConfig)
    depth_role: DepthRoleConfig = field(default_factory=DepthRoleConfig)
    rb_scheme_fit: RbSchemeFitConfig = field(default_factory=RbSchemeFitConfig)
    qb_split: QbSplitConfig = field(default_factory=QbSplitConfig)
    kicker: KickerConfig = field(default_factory=KickerConfig)
    dst_baseline: DstBaselineConfig = field(default_factory=DstBaselineConfig)
```

Import and parse it in `src/fantasy_sim/data/pff/config.py`:

```python
from fantasy_sim.data.pff.models import (
    ArchetypeConfig,
    CoverageConfig,
    DepthRoleConfig,
    DepthRoleEfficiencyConfig,
    DepthRoleEfficiencyPositionConfig,
    DepthRolePositionConfig,
    DstBaselineConfig,
    KickerConfig,
    MatchupConfig,
    NcaaPriorsConfig,
    NcaaRookieConfig,
    PffConfig,
    PositionGradeConfig,
    QbSplitConfig,
    RbSchemeFitConfig,
    ScheduleAdjustmentConfig,
    TalentConfig,
    TeamContextConfig,
    TierConfig,
)
```

```python
    rb_scheme_fit_raw = pff.get("rb_scheme_fit", {})
    rb_scheme_fit = RbSchemeFitConfig(
        enabled=rb_scheme_fit_raw.get("enabled", False),
        rush_yards_sensitivity=rb_scheme_fit_raw.get("rush_yards_sensitivity", 0.10),
        factor_clamp=tuple(rb_scheme_fit_raw.get("factor_clamp", [0.94, 1.06])),
        min_attempts=rb_scheme_fit_raw.get("min_attempts", 20),
        min_games=rb_scheme_fit_raw.get("min_games", 4),
        early_season_blend=rb_scheme_fit_raw.get("early_season_blend", True),
        scheme_usage_weight=rb_scheme_fit_raw.get("scheme_usage_weight", 0.65),
        blocking_alignment_weight=rb_scheme_fit_raw.get("blocking_alignment_weight", 0.35),
    )
```

```python
    return PffConfig(
        enabled=pff.get("enabled", False),
        data_dir=pff.get("data_dir"),
        matchup=matchup,
        talent=talent,
        tier_engine=tier_engine,
        team_context=team_context,
        coverage=coverage,
        depth_role=depth_role,
        rb_scheme_fit=rb_scheme_fit,
        qb_split=qb_split,
        kicker=kicker,
        dst_baseline=dst_baseline,
    )
```

- [ ] **Step 4: Run the config tests to verify they pass**

Run:

```bash
uv run pytest tests/test_data/test_pff/test_config.py tests/test_validation/test_config.py -k "rb_scheme_fit" -v
```

Expected: PASS for the new loader and override tests.

- [ ] **Step 5: Commit**

```bash
git add config/defaults.yaml src/fantasy_sim/data/pff/models.py src/fantasy_sim/data/pff/config.py tests/test_data/test_pff/test_config.py tests/test_validation/test_config.py
git commit -m "feat: add rb scheme fit config scaffolding"
```

### Task 2: Add Validation Coverage For `pff.rb_scheme_fit`

**Files:**
- Modify: `src/fantasy_sim/validation/coverage.py`
- Test: `tests/test_validation/test_coverage.py`

- [ ] **Step 1: Write the failing coverage tests**

Add these tests near the existing `pff.qb_split` coverage tests in `tests/test_validation/test_coverage.py`:

```python
def test_pff_rb_scheme_fit_reports_full_when_inputs_exist(tmp_path):
    pff_dir = tmp_path / "pff"
    cache_dir = tmp_path / "cache"
    for season in (2023, 2024):
        _write_parquet_placeholder(pff_dir / f"rushing_direction_{season}.parquet")
        _write_parquet_placeholder(pff_dir / f"offense_run_blocking_{season}.parquet")
        _write_parquet_placeholder(pff_dir / f"rushing_summary_{season}.parquet")
        _write_parquet_placeholder(cache_dir / f"rosters_weekly_{season}.parquet")

    engine_configs = _default_engine_configs()
    engine_configs["pff_config"].rb_scheme_fit.enabled = True

    coverage = collect_signal_coverage(
        engine_configs,
        [2023, 2024],
        pff_dir=pff_dir,
        cache_dir=cache_dir,
    )

    assert coverage["pff.rb_scheme_fit"] == SignalCoverage(
        enabled=True,
        status="full",
        covered_seasons=[2023, 2024],
        missing_seasons=[],
        note=(
            "Requires rushing_direction parquet, offense_run_blocking parquet, "
            "rushing_summary parquet, and rosters_weekly cache to build the RB scheme-fit signal"
        ),
    )


def test_pff_rb_scheme_fit_reports_partial_when_one_required_input_is_missing(tmp_path):
    pff_dir = tmp_path / "pff"
    cache_dir = tmp_path / "cache"
    _write_parquet_placeholder(pff_dir / "rushing_direction_2023.parquet")
    _write_parquet_placeholder(pff_dir / "offense_run_blocking_2023.parquet")
    _write_parquet_placeholder(pff_dir / "rushing_summary_2023.parquet")
    _write_parquet_placeholder(cache_dir / "rosters_weekly_2023.parquet")

    _write_parquet_placeholder(pff_dir / "rushing_direction_2024.parquet")
    _write_parquet_placeholder(pff_dir / "rushing_summary_2024.parquet")
    _write_parquet_placeholder(cache_dir / "rosters_weekly_2024.parquet")

    engine_configs = _default_engine_configs()
    engine_configs["pff_config"].rb_scheme_fit.enabled = True

    coverage = collect_signal_coverage(
        engine_configs,
        [2023, 2024],
        pff_dir=pff_dir,
        cache_dir=cache_dir,
    )

    assert coverage["pff.rb_scheme_fit"].status == "partial"
    assert coverage["pff.rb_scheme_fit"].covered_seasons == [2023]
    assert coverage["pff.rb_scheme_fit"].missing_seasons == [2024]


def test_pff_rb_scheme_fit_disabled_when_parent_pff_is_disabled(tmp_path):
    pff_dir = tmp_path / "pff"
    cache_dir = tmp_path / "cache"
    _write_parquet_placeholder(pff_dir / "rushing_direction_2024.parquet")
    _write_parquet_placeholder(pff_dir / "offense_run_blocking_2024.parquet")
    _write_parquet_placeholder(pff_dir / "rushing_summary_2024.parquet")
    _write_parquet_placeholder(cache_dir / "rosters_weekly_2024.parquet")

    engine_configs = _default_engine_configs()
    engine_configs["pff_config"].enabled = False
    engine_configs["pff_config"].rb_scheme_fit.enabled = True

    coverage = collect_signal_coverage(
        engine_configs,
        [2024],
        pff_dir=pff_dir,
        cache_dir=cache_dir,
    )

    assert coverage["pff.rb_scheme_fit"].status == "disabled"
```

- [ ] **Step 2: Run the coverage tests to verify they fail**

Run:

```bash
uv run pytest tests/test_validation/test_coverage.py -k "rb_scheme_fit" -v
```

Expected: FAIL with `KeyError: 'pff.rb_scheme_fit'` or equivalent missing-signal failures.

- [ ] **Step 3: Implement `pff.rb_scheme_fit` coverage**

Add a new enabled flag near the other PFF signal flags in `src/fantasy_sim/validation/coverage.py`:

```python
    rb_scheme_fit_enabled = _signal_enabled(
        config,
        ("pff_config", "pff"),
        ("pff", "rb_scheme_fit"),
        nested_path=("rb_scheme_fit",),
    )
```

Add required paths by season:

```python
    rb_scheme_fit_paths_by_season: dict[int, list[Path]] = {
        season: [
            pff_path / f"rushing_direction_{season}.parquet",
            pff_path / f"offense_run_blocking_{season}.parquet",
            pff_path / f"rushing_summary_{season}.parquet",
            cache_path / f"rosters_weekly_{season}.parquet",
        ]
        for season in seasons
    }
```

Return the new signal alongside the existing `pff.depth_role` and `pff.qb_split` block:

```python
        "pff.rb_scheme_fit": _build_signal(
            pff_enabled and rb_scheme_fit_enabled,
            seasons,
            _covered_seasons_from_required_paths(seasons, rb_scheme_fit_paths_by_season),
            note=(
                "Requires rushing_direction parquet, offense_run_blocking parquet, "
                "rushing_summary parquet, and rosters_weekly cache to build the RB scheme-fit signal"
            ),
        ),
```

- [ ] **Step 4: Run the coverage tests to verify they pass**

Run:

```bash
uv run pytest tests/test_validation/test_coverage.py -k "rb_scheme_fit" -v
```

Expected: PASS with `pff.rb_scheme_fit` reporting full/partial/disabled correctly.

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/validation/coverage.py tests/test_validation/test_coverage.py
git commit -m "feat: add rb scheme fit coverage reporting"
```

### Task 3: Implement `RbSchemeFitEngine`

**Files:**
- Create: `src/fantasy_sim/data/pff/rb_scheme_fit.py`
- Test: `tests/test_data/test_pff/test_rb_scheme_fit.py`

- [ ] **Step 1: Write the failing engine tests**

Create `tests/test_data/test_pff/test_rb_scheme_fit.py`:

```python
from unittest.mock import MagicMock

import numpy as np
import polars as pl

from fantasy_sim.data.pff.models import RbSchemeFitConfig, RbSchemeFitFactors
from fantasy_sim.data.pff.rb_scheme_fit import RbSchemeFitEngine
from fantasy_sim.models.player import PlayerModel, PlayerOutcomes, PlayerUsage, TeamRoster


def _make_roster(team: str, rb_id: str = "RB1") -> TeamRoster:
    return TeamRoster(
        team=team,
        players=[
            PlayerModel(
                "QB1",
                "QB One",
                "QB",
                team,
                PlayerUsage(snap_share=1.0),
                PlayerOutcomes(),
            ),
            PlayerModel(
                rb_id,
                "RB One",
                "RB",
                team,
                PlayerUsage(carry_share=0.55),
                PlayerOutcomes(rushing_yards_dist=np.array([3, 4, 5, 6])),
            ),
        ],
    )


def _rushing_direction_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "season": [2023, 2024],
            "week": [9, 3],
            "team": ["TEN", "TEN"],
            "player_id": [101, 101],
            "position": ["RB", "RB"],
            "game_id": [1, 2],
            "directions": [
                [
                    {"direction": "ML", "attempts": 8, "yards": 40, "ypa": 5.0},
                    {"direction": "MR", "attempts": 6, "yards": 30, "ypa": 5.0},
                    {"direction": "LE", "attempts": 2, "yards": 4, "ypa": 2.0},
                ],
                [
                    {"direction": "ML", "attempts": 4, "yards": 18, "ypa": 4.5},
                    {"direction": "MR", "attempts": 3, "yards": 12, "ypa": 4.0},
                ],
            ],
        }
    )


def _offense_run_blocking_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "season": [2023, 2024],
            "week": [9, 3],
            "team": ["TEN", "TEN"],
            "game_id": [1, 2],
            "gap_snap_counts_run_play": [18, 15],
            "zone_snap_counts_run_play": [8, 7],
            "gap_snap_counts_run_block": [18, 15],
            "zone_snap_counts_run_block": [8, 7],
            "gap_grades_run_block": [67.0, 66.0],
            "zone_grades_run_block": [58.0, 57.0],
        }
    )


def test_compute_returns_empty_when_crosswalk_is_missing():
    loader = MagicMock()
    loader.load_facet.side_effect = lambda facet, seasons: (
        _rushing_direction_df() if facet == "rushing_direction" else _offense_run_blocking_df()
    )
    engine = RbSchemeFitEngine(loader, RbSchemeFitConfig(enabled=True))

    factors = engine.compute(
        roster=_make_roster("TEN"),
        pff_crosswalk={},
        training_seasons=[2023, 2024],
        target_season=2024,
        max_week=4,
    )

    assert factors == {}


def test_compute_rewards_interior_back_on_gap_heavy_team():
    loader = MagicMock()
    loader.load_facet.side_effect = lambda facet, seasons: (
        _rushing_direction_df() if facet == "rushing_direction" else _offense_run_blocking_df()
    )
    engine = RbSchemeFitEngine(
        loader,
        RbSchemeFitConfig(
            enabled=True,
            rush_yards_sensitivity=0.50,
            min_attempts=10,
            min_games=1,
            factor_clamp=(0.90, 1.10),
        ),
    )

    factors = engine.compute(
        roster=_make_roster("TEN", rb_id="ten_rb"),
        pff_crosswalk={101: "ten_rb"},
        training_seasons=[2023, 2024],
        target_season=2024,
        max_week=4,
    )

    assert "ten_rb" in factors
    assert factors["ten_rb"].rushing_yards_factor > 1.0


def test_compute_ignores_rare_buckets_and_returns_neutral_when_no_classified_attempts():
    loader = MagicMock()
    loader.load_facet.side_effect = lambda facet, seasons: (
        pl.DataFrame(
            {
                "season": [2024],
                "week": [3],
                "team": ["TEN"],
                "player_id": [101],
                "position": ["RB"],
                "game_id": [2],
                "directions": [[
                    {"direction": "JS-L", "attempts": 4, "yards": 20, "ypa": 5.0},
                    {"direction": "EA-R", "attempts": 3, "yards": 12, "ypa": 4.0},
                ]],
            }
        )
        if facet == "rushing_direction"
        else _offense_run_blocking_df()
    )
    engine = RbSchemeFitEngine(
        loader,
        RbSchemeFitConfig(enabled=True, min_attempts=5, min_games=1),
    )

    factors = engine.compute(
        roster=_make_roster("TEN", rb_id="ten_rb"),
        pff_crosswalk={101: "ten_rb"},
        training_seasons=[2024],
        target_season=2024,
        max_week=4,
    )

    assert factors == {}


def test_compute_uses_previous_season_for_early_blend():
    loader = MagicMock()
    loader.load_facet.side_effect = lambda facet, seasons: (
        _rushing_direction_df() if facet == "rushing_direction" else _offense_run_blocking_df()
    )
    engine = RbSchemeFitEngine(
        loader,
        RbSchemeFitConfig(
            enabled=True,
            rush_yards_sensitivity=0.50,
            min_attempts=20,
            min_games=4,
            early_season_blend=True,
            factor_clamp=(0.90, 1.10),
        ),
    )

    factors = engine.compute(
        roster=_make_roster("TEN", rb_id="ten_rb"),
        pff_crosswalk={101: "ten_rb"},
        training_seasons=[2023, 2024],
        target_season=2024,
        max_week=4,
    )

    assert factors["ten_rb"].rushing_yards_factor > 1.0
```

- [ ] **Step 2: Run the engine tests to verify they fail**

Run:

```bash
uv run pytest tests/test_data/test_pff/test_rb_scheme_fit.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'fantasy_sim.data.pff.rb_scheme_fit'`.

- [ ] **Step 3: Write the engine implementation**

Create `src/fantasy_sim/data/pff/rb_scheme_fit.py`:

```python
from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import polars as pl

from fantasy_sim.data.pff.loader import PffLoader
from fantasy_sim.data.pff.models import RbSchemeFitConfig, RbSchemeFitFactors
from fantasy_sim.models.player import TeamRoster

_INTERIOR_DIRECTIONS = {"ML", "MR", "LG", "RG"}
_EDGE_DIRECTIONS = {"LE", "RE", "LT", "RT"}


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0 or not np.isfinite(numerator) or not np.isfinite(denominator):
        return 0.0
    return float(numerator / denominator)


class RbSchemeFitEngine:
    def __init__(self, loader: PffLoader, config: RbSchemeFitConfig):
        self._loader = loader
        self._config = config
        self._cache: dict[str, pl.DataFrame] = {}

    def _load_cached(self, facet: str, seasons: list[int]) -> pl.DataFrame:
        key = f"{facet}_{'_'.join(str(season) for season in sorted(seasons))}"
        if key not in self._cache:
            self._cache[key] = self._loader.load_facet(facet, seasons)
        return self._cache[key]

    def _flatten_direction_rows(
        self,
        seasons: list[int],
        target_season: int,
        max_week: int,
        pff_crosswalk: Mapping[int, str],
    ) -> pl.DataFrame:
        df = self._load_cached("rushing_direction", seasons)
        if df.is_empty() or "directions" not in df.columns:
            return pl.DataFrame()

        filtered = (
            df.filter(pl.col("position") == "RB")
            .filter(pl.col("season").is_in(seasons))
            .filter(
                (pl.col("season") < target_season)
                | ((pl.col("season") == target_season) & (pl.col("week") < max_week))
            )
        )
        if filtered.is_empty():
            return pl.DataFrame()

        reverse_crosswalk = pl.DataFrame(
            {
                "pff_player_id": list(pff_crosswalk.keys()),
                "player_id": list(pff_crosswalk.values()),
            }
        )
        if reverse_crosswalk.is_empty():
            return pl.DataFrame()

        exploded = (
            filtered.explode("directions")
            .unnest("directions")
            .with_columns(
                pl.when(pl.col("direction").is_in(list(_INTERIOR_DIRECTIONS)))
                .then(pl.lit("interior"))
                .when(pl.col("direction").is_in(list(_EDGE_DIRECTIONS)))
                .then(pl.lit("edge"))
                .otherwise(pl.lit(None))
                .alias("family")
            )
            .filter(pl.col("family").is_not_null())
            .rename({"player_id": "pff_player_id"})
            .join(reverse_crosswalk, on="pff_player_id", how="inner")
        )
        if exploded.is_empty():
            return pl.DataFrame()

        return exploded.select(
            [
                "season",
                "team",
                "player_id",
                "game_id",
                "family",
                pl.col("attempts").cast(pl.Float64),
                pl.col("yards").cast(pl.Float64),
            ]
        )

    def _aggregate_team_blocking(
        self,
        seasons: list[int],
        target_season: int,
        max_week: int,
    ) -> pl.DataFrame:
        df = self._load_cached("offense_run_blocking", seasons)
        if df.is_empty():
            return pl.DataFrame()

        filtered = df.filter(pl.col("season").is_in(seasons)).filter(
            (pl.col("season") < target_season)
            | ((pl.col("season") == target_season) & (pl.col("week") < max_week))
        )
        if filtered.is_empty():
            return pl.DataFrame()

        return filtered.group_by(["season", "team"]).agg(
            pl.col("game_id").n_unique().alias("games"),
            pl.col("gap_snap_counts_run_play").sum().cast(pl.Float64).alias("gap_run_play"),
            pl.col("zone_snap_counts_run_play").sum().cast(pl.Float64).alias("zone_run_play"),
            pl.col("gap_snap_counts_run_block").sum().cast(pl.Float64).alias("gap_run_block_snaps"),
            pl.col("zone_snap_counts_run_block").sum().cast(pl.Float64).alias("zone_run_block_snaps"),
            (
                (pl.col("gap_grades_run_block") * pl.col("gap_snap_counts_run_block")).sum()
                / pl.col("gap_snap_counts_run_block").sum()
            ).alias("gap_grade"),
            (
                (pl.col("zone_grades_run_block") * pl.col("zone_snap_counts_run_block")).sum()
                / pl.col("zone_snap_counts_run_block").sum()
            ).alias("zone_grade"),
        )

    def _player_profile(self, rows: pl.DataFrame) -> dict[str, float] | None:
        if rows.is_empty():
            return None

        interior = rows.filter(pl.col("family") == "interior")
        edge = rows.filter(pl.col("family") == "edge")
        total_attempts = float(rows["attempts"].sum())
        if total_attempts <= 0:
            return None

        interior_attempts = float(interior["attempts"].sum()) if not interior.is_empty() else 0.0
        edge_attempts = float(edge["attempts"].sum()) if not edge.is_empty() else 0.0
        interior_yards = float(interior["yards"].sum()) if not interior.is_empty() else 0.0
        edge_yards = float(edge["yards"].sum()) if not edge.is_empty() else 0.0

        return {
            "games": float(rows.select(pl.col("game_id").n_unique()).item()),
            "classified_attempts": total_attempts,
            "interior_attempt_share": _safe_ratio(interior_attempts, total_attempts),
            "edge_attempt_share": _safe_ratio(edge_attempts, total_attempts),
            "interior_ypa": _safe_ratio(interior_yards, interior_attempts),
            "edge_ypa": _safe_ratio(edge_yards, edge_attempts),
            "overall_ypa": _safe_ratio(float(rows["yards"].sum()), total_attempts),
        }

    def _team_profile(self, rows: pl.DataFrame) -> dict[str, float] | None:
        if rows.is_empty():
            return None

        gap_run_play = float(rows["gap_run_play"].sum())
        zone_run_play = float(rows["zone_run_play"].sum())
        total_run_play = gap_run_play + zone_run_play
        if total_run_play <= 0:
            return None

        latest = rows.sort("season")
        return {
            "games": float(rows["games"].sum()),
            "gap_share": _safe_ratio(gap_run_play, total_run_play),
            "zone_share": _safe_ratio(zone_run_play, total_run_play),
            "gap_grade": float(latest["gap_grade"].tail(1).item()),
            "zone_grade": float(latest["zone_grade"].tail(1).item()),
        }

    def _passes_player_gates(self, profile: dict[str, float] | None) -> bool:
        if profile is None:
            return False
        return (
            profile["classified_attempts"] >= self._config.min_attempts
            and profile["games"] >= self._config.min_games
        )

    def _passes_team_gates(self, profile: dict[str, float] | None) -> bool:
        if profile is None:
            return False
        return profile["games"] >= self._config.min_games

    def _blend_profile(
        self,
        current_profile: dict[str, float] | None,
        previous_profile: dict[str, float] | None,
        current_games: float,
    ) -> dict[str, float] | None:
        if current_profile is None and previous_profile is None:
            return None
        if current_profile is None:
            return previous_profile
        if previous_profile is None:
            return current_profile
        if not self._config.early_season_blend or current_games >= self._config.min_games:
            return current_profile

        weight = current_games / max(float(self._config.min_games), 1.0)
        return {
            key: (weight * current_profile[key]) + ((1.0 - weight) * previous_profile[key])
            for key in current_profile
        }

    def _normalized_weights(self) -> tuple[float, float]:
        usage_weight = max(float(self._config.scheme_usage_weight), 0.0)
        blocking_weight = max(float(self._config.blocking_alignment_weight), 0.0)
        total = usage_weight + blocking_weight
        if total <= 0:
            return 0.0, 0.0
        return usage_weight / total, blocking_weight / total

    def compute(
        self,
        roster: TeamRoster,
        pff_crosswalk: Mapping[int, str] | None,
        training_seasons: list[int],
        target_season: int,
        max_week: int,
    ) -> dict[str, RbSchemeFitFactors]:
        if not self._config.enabled or not pff_crosswalk:
            return {}

        direction_rows = self._flatten_direction_rows(
            training_seasons,
            target_season,
            max_week,
            pff_crosswalk,
        )
        if direction_rows.is_empty():
            return {}

        blocking_rows = self._aggregate_team_blocking(training_seasons, target_season, max_week)
        if blocking_rows.is_empty():
            return {}

        usage_weight, blocking_weight = self._normalized_weights()
        if usage_weight == 0.0 and blocking_weight == 0.0:
            return {}

        current_team_rows = blocking_rows.filter(
            (pl.col("team") == roster.team) & (pl.col("season") == target_season)
        )
        previous_team_rows = blocking_rows.filter(
            (pl.col("team") == roster.team) & (pl.col("season") == (target_season - 1))
        )
        team_profile = self._blend_profile(
            self._team_profile(current_team_rows),
            self._team_profile(previous_team_rows),
            float(current_team_rows["games"].sum()) if not current_team_rows.is_empty() else 0.0,
        )
        if not self._passes_team_gates(team_profile):
            return {}

        results: dict[str, RbSchemeFitFactors] = {}
        for player in roster.players:
            if (
                player.position != "RB"
                or player.usage.carry_share <= 0
                or player.outcomes.rushing_yards_dist is None
                or len(player.outcomes.rushing_yards_dist) == 0
            ):
                continue

            current_player_rows = direction_rows.filter(
                (pl.col("player_id") == player.player_id) & (pl.col("season") == target_season)
            )
            previous_player_rows = direction_rows.filter(
                (pl.col("player_id") == player.player_id) & (pl.col("season") == (target_season - 1))
            )

            player_profile = self._blend_profile(
                self._player_profile(current_player_rows),
                self._player_profile(previous_player_rows),
                float(current_player_rows.select(pl.col("game_id").n_unique()).item()) if not current_player_rows.is_empty() else 0.0,
            )
            if not self._passes_player_gates(player_profile):
                continue

            runner_usage_score = (
                (team_profile["gap_share"] * player_profile["interior_ypa"])
                + (team_profile["zone_share"] * player_profile["edge_ypa"])
            )
            runner_baseline_score = player_profile["overall_ypa"]
            usage_delta = _safe_ratio(runner_usage_score, runner_baseline_score) - 1.0

            family_preference = (
                player_profile["interior_attempt_share"] - player_profile["edge_attempt_share"]
            )
            blocking_delta = family_preference * (
                (team_profile["gap_grade"] - team_profile["zone_grade"]) / 100.0
            )

            combined_delta = (usage_weight * usage_delta) + (blocking_weight * blocking_delta)
            factor = 1.0 + (combined_delta * self._config.rush_yards_sensitivity)
            factor = float(np.clip(factor, *self._config.factor_clamp))

            results[player.player_id] = RbSchemeFitFactors(rushing_yards_factor=factor)

        return results
```

- [ ] **Step 4: Run the engine tests to verify they pass**

Run:

```bash
uv run pytest tests/test_data/test_pff/test_rb_scheme_fit.py -v
```

Expected: PASS with neutral fallback, rare-bucket ignore behavior, early-season blending, and positive fit translation working.

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/pff/rb_scheme_fit.py tests/test_data/test_pff/test_rb_scheme_fit.py
git commit -m "feat: add rb scheme fit engine"
```

### Task 4: Wire `RbSchemeFitEngine` Into `GameContextBuilder`

**Files:**
- Modify: `src/fantasy_sim/data/game_context.py`
- Test: `tests/test_data/test_pff/test_rb_scheme_fit_integration.py`

- [ ] **Step 1: Write the failing integration tests**

Create `tests/test_data/test_pff/test_rb_scheme_fit_integration.py`:

```python
from unittest.mock import MagicMock, patch

import numpy as np

from fantasy_sim.data.game_context import GameContextBuilder
from fantasy_sim.data.pff.models import PffConfig, RbSchemeFitConfig, RbSchemeFitFactors
from fantasy_sim.engine.types import TeamDistributions
from fantasy_sim.models.distributions import DriveStartModel, KickingModel, PlayCallingDist, PlayOutcomeDist, TurnoverRates
from fantasy_sim.models.player import PlayerModel, PlayerOutcomes, PlayerUsage, TeamRoster


def _make_dists(team: str) -> TeamDistributions:
    return TeamDistributions(
        play_calling=PlayCallingDist(team=team, distributions={}, default={"pass": 0.57, "run": 0.43}),
        play_outcomes=PlayOutcomeDist(distributions={}, defaults={"pass": np.array([5.0]), "run": np.array([3.0])}),
        turnover_rates=TurnoverRates(team=team, int_rate=0.02, fumble_rate=0.01, sack_rate=0.06, sack_fumble_rate=0.1),
        kicking=KickingModel(fg_make_rate={"0_39": 0.9, "40_49": 0.8, "50_plus": 0.7}, xp_rate=0.95),
        drive_start=DriveStartModel(touchback_rate=0.6, touchback_yardline=75, return_yardlines=np.array([72.0])),
    )


def _make_roster(team: str) -> TeamRoster:
    return TeamRoster(
        team=team,
        players=[
            PlayerModel(
                f"{team}_QB",
                "QB One",
                "QB",
                team,
                PlayerUsage(snap_share=1.0),
                PlayerOutcomes(),
            ),
            PlayerModel(
                f"{team}_RB1",
                "RB One",
                "RB",
                team,
                PlayerUsage(carry_share=0.55, red_zone_carry_share=0.50),
                PlayerOutcomes(rushing_yards_dist=np.array([3, 4, 5, 6])),
            ),
            PlayerModel(
                f"{team}_WR1",
                "WR One",
                "WR",
                team,
                PlayerUsage(target_share=0.30),
                PlayerOutcomes(receiving_yards_dist=np.array([8, 12, 14])),
            ),
        ],
    )


def test_rb_scheme_fit_engine_created_when_enabled(tmp_path):
    pff_config = PffConfig(enabled=True, rb_scheme_fit=RbSchemeFitConfig(enabled=True))

    with patch("fantasy_sim.data.pff.loader.PffLoader") as mock_loader:
        mock_loader.return_value.is_available.return_value = True
        builder = GameContextBuilder(cache_dir=tmp_path / "cache", pff_config=pff_config)

    assert builder._rb_scheme_fit_engine is not None


def test_build_game_applies_rb_scheme_fit_after_tier_before_qb_split(tmp_path):
    builder = GameContextBuilder(cache_dir=tmp_path / "cache")
    builder.build_team_distributions = MagicMock(side_effect=[_make_dists("TEN"), _make_dists("HOU")])
    builder.build_team_roster = MagicMock(side_effect=[_make_roster("TEN"), _make_roster("HOU")])
    builder.loader.load_rosters = MagicMock(return_value=MagicMock())
    builder.loader.load_pbp = MagicMock(return_value=MagicMock())
    builder._availability_engine = None
    builder._usage_engine = None
    builder._tracking_engine = None
    builder._props_engine = None
    builder._vegas_engine = None
    builder._weather_engine = None
    builder._dst_baseline_engine = None
    builder._kicker_engine = None
    builder._team_context_engine = None
    builder._talent_stabilizer = None
    builder._ensure_pff_crosswalk = MagicMock()
    builder._pff_crosswalk = {101: "TEN_RB1", 202: "HOU_RB1"}

    events: list[str] = []

    builder._matchup_engine = MagicMock()
    builder._matchup_engine.compute.side_effect = [MagicMock(), MagicMock()]

    builder._tier_engine = MagicMock()
    builder._tier_engine.apply_tiers.side_effect = lambda *args, **kwargs: events.append("tier")

    builder._rb_scheme_fit_engine = MagicMock()
    builder._rb_scheme_fit_engine.compute.side_effect = (
        lambda *args, **kwargs: events.append("rb_scheme_compute")
        or {kwargs["roster"].players[1].player_id: RbSchemeFitFactors(rushing_yards_factor=1.05)}
    )

    builder._apply_rb_scheme_fit = MagicMock(side_effect=lambda *args, **kwargs: events.append("rb_scheme_apply"))

    builder._qb_split_engine = MagicMock()
    builder._qb_split_engine.compute.side_effect = lambda *args, **kwargs: events.append("qb_split_compute") or MagicMock(catch_rate_factor=1.0, yards_scale_factor=1.0)
    builder._apply_qb_split = MagicMock(side_effect=lambda *args, **kwargs: events.append("qb_split_apply"))

    with patch("fantasy_sim.data.player_builder._normalize_roster_shares") as mock_normalize:
        mock_normalize.side_effect = lambda roster: events.append(f"normalize:{roster.team}")
        builder.build_game("TEN", "HOU", training_seasons=[2024], target_season=2024, week=8)

    assert events == [
        "tier",
        "tier",
        "normalize:TEN",
        "normalize:HOU",
        "rb_scheme_compute",
        "rb_scheme_compute",
        "rb_scheme_apply",
        "rb_scheme_apply",
        "qb_split_compute",
        "qb_split_compute",
        "qb_split_apply",
        "qb_split_apply",
    ]


def test_apply_rb_scheme_fit_only_mutates_rb_rushing_yards():
    roster = _make_roster("TEN")
    rb = next(player for player in roster.players if player.position == "RB")
    wr = next(player for player in roster.players if player.position == "WR")

    original_rb_carry_share = rb.usage.carry_share
    original_rb_red_zone = rb.usage.red_zone_carry_share
    original_rb_dist = rb.outcomes.rushing_yards_dist.copy()
    original_wr_dist = wr.outcomes.receiving_yards_dist.copy()

    GameContextBuilder._apply_rb_scheme_fit(
        roster,
        {"TEN_RB1": RbSchemeFitFactors(rushing_yards_factor=1.10)},
    )

    assert rb.usage.carry_share == original_rb_carry_share
    assert rb.usage.red_zone_carry_share == original_rb_red_zone
    assert float(rb.outcomes.rushing_yards_dist.mean()) > float(original_rb_dist.mean())
    np.testing.assert_allclose(wr.outcomes.receiving_yards_dist, original_wr_dist)
```

- [ ] **Step 2: Run the integration tests to verify they fail**

Run:

```bash
uv run pytest tests/test_data/test_pff/test_rb_scheme_fit_integration.py -v
```

Expected: FAIL because `GameContextBuilder` has no `_rb_scheme_fit_engine` wiring or `_apply_rb_scheme_fit()` helper yet.

- [ ] **Step 3: Write the runtime wiring**

In `src/fantasy_sim/data/game_context.py`, add engine construction in `__init__` before `qb_split`:

```python
        self._depth_role_engine = None
        self._rb_scheme_fit_engine = None
        self._qb_split_engine = None
```

```python
        if self._pff_config.enabled and self._pff_config.rb_scheme_fit.enabled and self._pff_loader:
            from fantasy_sim.data.pff.rb_scheme_fit import RbSchemeFitEngine

            self._rb_scheme_fit_engine = RbSchemeFitEngine(
                self._pff_loader,
                self._pff_config.rb_scheme_fit,
            )
            logger.info("PFF RB scheme-fit engine enabled")
```

Add a helper near `_apply_qb_split()`:

```python
    @staticmethod
    def _apply_rb_scheme_fit(
        roster: TeamRoster,
        factors: dict[str, RbSchemeFitFactors] | None,
    ) -> None:
        if not factors:
            return

        for player in roster.players:
            if player.position != "RB":
                continue

            fit = factors.get(player.player_id)
            if fit is None:
                continue

            if (
                fit.rushing_yards_factor != 1.0
                and player.outcomes.rushing_yards_dist is not None
                and len(player.outcomes.rushing_yards_dist) > 0
            ):
                adjusted = np.asarray(player.outcomes.rushing_yards_dist, dtype=float) * fit.rushing_yards_factor
                player.outcomes.rushing_yards_dist = np.rint(adjusted).astype(np.int64)
```

Add the import near the other PFF model imports:

```python
from fantasy_sim.data.pff.models import (
    PffConfig,
    MatchupContext,
    CoverageModifiers,
    QbSplitFactors,
    RbSchemeFitFactors,
)
```

Insert the runtime step after tier normalization and before `qb_split`:

```python
        if self._rb_scheme_fit_engine is not None and target_season and week:
            self._ensure_pff_crosswalk(training_seasons, target_season)
            rb_scheme_seasons = _seasons_with_target(training_seasons, target_season)

            home_rb_scheme = self._rb_scheme_fit_engine.compute(
                roster=home_roster,
                pff_crosswalk=self._pff_crosswalk,
                training_seasons=rb_scheme_seasons,
                target_season=target_season,
                max_week=week,
            )
            away_rb_scheme = self._rb_scheme_fit_engine.compute(
                roster=away_roster,
                pff_crosswalk=self._pff_crosswalk,
                training_seasons=rb_scheme_seasons,
                target_season=target_season,
                max_week=week,
            )
            self._apply_rb_scheme_fit(home_roster, home_rb_scheme)
            self._apply_rb_scheme_fit(away_roster, away_rb_scheme)
```

- [ ] **Step 4: Run the integration tests to verify they pass**

Run:

```bash
uv run pytest tests/test_data/test_pff/test_rb_scheme_fit_integration.py -v
```

Expected: PASS with RB scheme-fit created when enabled and ordered between tier and qb-split.

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/game_context.py tests/test_data/test_pff/test_rb_scheme_fit_integration.py
git commit -m "feat: wire rb scheme fit into game context"
```

### Task 5: Run The Focused Test Slice, Validate The Feature, And Update Docs

**Files:**
- Modify: `docs/accuracy-roadmap.md`
- Modify: `docs/accuracy-stack-audit.md`

- [ ] **Step 1: Run the full RB scheme-fit implementation test slice**

Run:

```bash
uv run pytest \
  tests/test_data/test_pff/test_config.py \
  tests/test_validation/test_config.py \
  tests/test_validation/test_coverage.py \
  tests/test_data/test_pff/test_rb_scheme_fit.py \
  tests/test_data/test_pff/test_rb_scheme_fit_integration.py -k "rb_scheme_fit" -v
```

Expected: PASS for config, coverage, engine, and integration coverage added in Tasks 1-4.

- [ ] **Step 2: Run the marginal validation artifact**

Run:

```bash
uv run python scripts/validate.py \
  --baseline defaults \
  --set pff.rb_scheme_fit.enabled=true \
  --sims 50 \
  --label "phase-5-rb-scheme-fit-v1"
```

Expected:

- validation header prints explicit `pff.rb_scheme_fit=...` coverage
- output records a new marginal-lift artifact against the current defaults stack

- [ ] **Step 3: Update `docs/accuracy-roadmap.md` with the real Phase 5D artifact**

Edit the Phase 5 section so it records:

- `RB scheme-fit engine` as implemented and validated
- the exact artifact label `phase-5-rb-scheme-fit-v1`
- baseline `defaults`
- comparison mode `marginal_lift`
- the exact `pff.rb_scheme_fit=...` coverage string printed by the run
- the exact top-line deltas from the run
- the final verdict:
  - keep `pff.rb_scheme_fit.enabled: false` if the result is flat or regressive
  - promote only if the result clears the spec gate

Do not round or restate the numbers; copy the exact run output values into the existing Phase 5 format already used for Phase 5A, 5B, and 5C.

- [ ] **Step 4: Update `docs/accuracy-stack-audit.md` with the real current-state note**

Edit the Phase 5 section and current defaults readout so it records:

- `pff.rb_scheme_fit.enabled: false` if the slice is not promoted, or `true` only if it is promoted
- that `rushing_direction` is now consumed by the runtime through `pff.rb_scheme_fit`
- the exact artifact label, coverage string, and top-line deltas
- the current verdict and whether Phase 5 follow-on work is finished or still has a deferred tail

Keep the wording consistent with the existing audit style: built state, data coverage, verdict, and next follow-on.

- [ ] **Step 5: Commit**

```bash
git add docs/accuracy-roadmap.md docs/accuracy-stack-audit.md
git commit -m "docs: record rb scheme fit validation result"
```

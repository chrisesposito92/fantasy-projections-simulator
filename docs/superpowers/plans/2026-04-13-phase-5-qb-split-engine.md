# Phase 5 QB Split Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a default-off PFF `qb_split` engine that converts opponent-aware starter-QB pressure response from `passing_detail` into bounded pre-sim pass-catcher efficiency adjustments, with validation coverage and Phase 5 documentation updates.

**Architecture:** Add a new `pff.qb_split` config family and typed model, implement `QbSplitEngine.compute()` to derive league-relative pressure resilience traits from `passing_detail`, and wire `GameContextBuilder` to apply returned factors after matchup/tier and before depth-role/coverage. Keep the runtime surface narrow: mutate only eligible pass-catcher `catch_rate`, proportional `red_zone_catch_rate`, and base `receiving_yards_dist`, while leaving play-calling, turnover rates, QB rushing, and target shares untouched.

**Tech Stack:** Python 3.14, polars, numpy, pytest, YAML config, Click validation CLI

---

## File Structure

- `config/defaults.yaml`
  - shipped default-off `pff.qb_split` settings
- `src/fantasy_sim/data/pff/models.py`
  - `QbSplitConfig` and `QbSplitFactors`
- `src/fantasy_sim/data/pff/config.py`
  - parse `pff.qb_split` into `PffConfig`
- `src/fantasy_sim/data/pff/qb_split.py`
  - `QbSplitEngine`, split aggregation, early-season blending, factor translation
- `src/fantasy_sim/data/game_context.py`
  - engine construction, runtime ordering, `_apply_qb_split()` helper
- `src/fantasy_sim/validation/coverage.py`
  - `pff.qb_split` coverage reporting
- `tests/test_data/test_pff/test_config.py`
  - direct config loader tests for `pff.qb_split`
- `tests/test_validation/test_config.py`
  - override propagation tests for `pff.qb_split`
- `tests/test_validation/test_coverage.py`
  - `pff.qb_split` coverage tests
- `tests/test_data/test_pff/test_qb_split.py`
  - engine unit tests
- `tests/test_data/test_pff/test_qb_split_integration.py`
  - builder wiring and mutation-boundary tests
- `docs/accuracy-roadmap.md`
  - Phase 5 status/result update after validation
- `docs/accuracy-stack-audit.md`
  - defaults/runtime/result update after validation

### Task 1: Add The `pff.qb_split` Config Family

**Files:**
- Modify: `config/defaults.yaml`
- Modify: `src/fantasy_sim/data/pff/models.py`
- Modify: `src/fantasy_sim/data/pff/config.py`
- Test: `tests/test_data/test_pff/test_config.py`
- Test: `tests/test_validation/test_config.py`

- [ ] **Step 1: Write the failing config tests**

```python
def test_load_pff_config_qb_split_defaults():
    cfg = load_pff_config({"pff": {"enabled": True}})

    assert isinstance(cfg.qb_split, QbSplitConfig)
    assert cfg.qb_split.enabled is False
    assert cfg.qb_split.completion_sensitivity == 0.10
    assert cfg.qb_split.yards_sensitivity == 0.12
    assert cfg.qb_split.catch_rate_clamp == (0.95, 1.05)
    assert cfg.qb_split.yards_scale_clamp == (0.94, 1.06)
    assert cfg.qb_split.min_pressure_dropbacks == 20
    assert cfg.qb_split.min_clean_dropbacks == 40
    assert cfg.qb_split.min_games == 4
    assert cfg.qb_split.early_season_blend is True


def test_load_pff_config_qb_split_custom_values():
    cfg = load_pff_config(
        {
            "pff": {
                "enabled": True,
                "qb_split": {
                    "enabled": True,
                    "completion_sensitivity": 0.18,
                    "yards_sensitivity": 0.16,
                    "catch_rate_clamp": [0.96, 1.04],
                    "yards_scale_clamp": [0.95, 1.05],
                    "min_pressure_dropbacks": 28,
                    "min_clean_dropbacks": 55,
                    "min_games": 5,
                    "early_season_blend": False,
                },
            }
        }
    )

    assert cfg.qb_split.enabled is True
    assert cfg.qb_split.completion_sensitivity == 0.18
    assert cfg.qb_split.yards_sensitivity == 0.16
    assert cfg.qb_split.catch_rate_clamp == (0.96, 1.04)
    assert cfg.qb_split.yards_scale_clamp == (0.95, 1.05)
    assert cfg.qb_split.min_pressure_dropbacks == 28
    assert cfg.qb_split.min_clean_dropbacks == 55
    assert cfg.qb_split.min_games == 5
    assert cfg.qb_split.early_season_blend is False


def test_pff_qb_split_override_propagates():
    defaults = load_defaults()
    overridden = apply_overrides(
        defaults,
        [
            "pff.qb_split.enabled=true",
            "pff.qb_split.completion_sensitivity=0.17",
            "pff.qb_split.min_pressure_dropbacks=24",
        ],
    )

    configs = build_engine_configs(overridden)

    assert configs["pff_config"] is not None
    assert configs["pff_config"].qb_split.enabled is True
    assert configs["pff_config"].qb_split.completion_sensitivity == 0.17
    assert configs["pff_config"].qb_split.min_pressure_dropbacks == 24
```

- [ ] **Step 2: Run the config tests to verify they fail**

Run:

```bash
uv run pytest tests/test_data/test_pff/test_config.py tests/test_validation/test_config.py -k "qb_split" -v
```

Expected: FAIL with `AttributeError: 'PffConfig' object has no attribute 'qb_split'` or equivalent parser/override failures.

- [ ] **Step 3: Write the minimal config implementation**

Add this block under `pff:` in `config/defaults.yaml` after `depth_role` and before `kicker`:

```yaml
  qb_split:
    enabled: false
    completion_sensitivity: 0.10
    yards_sensitivity: 0.12
    catch_rate_clamp: [0.95, 1.05]
    yards_scale_clamp: [0.94, 1.06]
    min_pressure_dropbacks: 20
    min_clean_dropbacks: 40
    min_games: 4
    early_season_blend: true
```

Add these dataclasses in `src/fantasy_sim/data/pff/models.py` above `KickerConfig`:

```python
@dataclass
class QbSplitConfig:
    """Configuration for the PFF QB pressure-split engine."""
    enabled: bool = False
    completion_sensitivity: float = 0.10
    yards_sensitivity: float = 0.12
    catch_rate_clamp: tuple[float, float] = (0.95, 1.05)
    yards_scale_clamp: tuple[float, float] = (0.94, 1.06)
    min_pressure_dropbacks: int = 20
    min_clean_dropbacks: int = 40
    min_games: int = 4
    early_season_blend: bool = True


@dataclass
class QbSplitFactors:
    """Per-offense passing-efficiency factors from QB pressure splits."""
    catch_rate_factor: float = 1.0
    yards_scale_factor: float = 1.0
```

Then thread the field into `PffConfig`:

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
    ScheduleAdjustmentConfig,
    TalentConfig,
    TeamContextConfig,
    TierConfig,
)
```

```python
    qb_split_raw = pff.get("qb_split", {})
    qb_split = QbSplitConfig(
        enabled=qb_split_raw.get("enabled", False),
        completion_sensitivity=qb_split_raw.get("completion_sensitivity", 0.10),
        yards_sensitivity=qb_split_raw.get("yards_sensitivity", 0.12),
        catch_rate_clamp=tuple(qb_split_raw.get("catch_rate_clamp", [0.95, 1.05])),
        yards_scale_clamp=tuple(qb_split_raw.get("yards_scale_clamp", [0.94, 1.06])),
        min_pressure_dropbacks=qb_split_raw.get("min_pressure_dropbacks", 20),
        min_clean_dropbacks=qb_split_raw.get("min_clean_dropbacks", 40),
        min_games=qb_split_raw.get("min_games", 4),
        early_season_blend=qb_split_raw.get("early_season_blend", True),
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
        qb_split=qb_split,
        kicker=kicker,
        dst_baseline=dst_baseline,
    )
```

- [ ] **Step 4: Run the config tests to verify they pass**

Run:

```bash
uv run pytest tests/test_data/test_pff/test_config.py tests/test_validation/test_config.py -k "qb_split" -v
```

Expected: PASS for the new loader and override tests.

- [ ] **Step 5: Commit**

```bash
git add config/defaults.yaml src/fantasy_sim/data/pff/models.py src/fantasy_sim/data/pff/config.py tests/test_data/test_pff/test_config.py tests/test_validation/test_config.py
git commit -m "feat: add qb split config scaffolding"
```

### Task 2: Add Validation Coverage For `pff.qb_split`

**Files:**
- Modify: `src/fantasy_sim/validation/coverage.py`
- Test: `tests/test_validation/test_coverage.py`

- [ ] **Step 1: Write the failing coverage tests**

Add these tests near the existing `pff.depth_role` coverage tests:

```python
def test_pff_qb_split_reports_full_when_inputs_exist(tmp_path):
    pff_dir = tmp_path / "pff"
    cache_dir = tmp_path / "cache"
    for season in (2023, 2024):
        _write_parquet_placeholder(pff_dir / f"passing_detail_{season}.parquet")
        _write_parquet_placeholder(pff_dir / f"passing_summary_{season}.parquet")
        _write_parquet_placeholder(cache_dir / f"rosters_weekly_{season}.parquet")

    engine_configs = _default_engine_configs()
    engine_configs["pff_config"].qb_split.enabled = True

    coverage = collect_signal_coverage(
        engine_configs,
        [2023, 2024],
        pff_dir=pff_dir,
        cache_dir=cache_dir,
    )

    assert coverage["pff.qb_split"] == SignalCoverage(
        enabled=True,
        status="full",
        covered_seasons=[2023, 2024],
        missing_seasons=[],
        note=(
            "Requires passing_detail parquet, passing_summary parquet, "
            "and rosters_weekly cache to build the PFF QB crosswalk"
        ),
    )


def test_pff_qb_split_reports_partial_when_one_season_is_missing(tmp_path):
    pff_dir = tmp_path / "pff"
    cache_dir = tmp_path / "cache"
    _write_parquet_placeholder(pff_dir / "passing_detail_2023.parquet")
    _write_parquet_placeholder(pff_dir / "passing_summary_2023.parquet")
    _write_parquet_placeholder(cache_dir / "rosters_weekly_2023.parquet")
    _write_parquet_placeholder(cache_dir / "rosters_weekly_2024.parquet")

    engine_configs = _default_engine_configs()
    engine_configs["pff_config"].qb_split.enabled = True

    coverage = collect_signal_coverage(
        engine_configs,
        [2023, 2024],
        pff_dir=pff_dir,
        cache_dir=cache_dir,
    )

    assert coverage["pff.qb_split"].status == "partial"
    assert coverage["pff.qb_split"].covered_seasons == [2023]
    assert coverage["pff.qb_split"].missing_seasons == [2024]


def test_pff_qb_split_disabled_when_parent_pff_is_disabled(tmp_path):
    pff_dir = tmp_path / "pff"
    cache_dir = tmp_path / "cache"
    _write_parquet_placeholder(pff_dir / "passing_detail_2024.parquet")
    _write_parquet_placeholder(pff_dir / "passing_summary_2024.parquet")
    _write_parquet_placeholder(cache_dir / "rosters_weekly_2024.parquet")

    engine_configs = _default_engine_configs()
    engine_configs["pff_config"].enabled = False
    engine_configs["pff_config"].qb_split.enabled = True

    coverage = collect_signal_coverage(
        engine_configs,
        [2024],
        pff_dir=pff_dir,
        cache_dir=cache_dir,
    )

    assert coverage["pff.qb_split"].status == "disabled"
```

- [ ] **Step 2: Run the coverage tests to verify they fail**

Run:

```bash
uv run pytest tests/test_validation/test_coverage.py -k "qb_split" -v
```

Expected: FAIL with `KeyError: 'pff.qb_split'` or equivalent missing-signal failures.

- [ ] **Step 3: Implement `pff.qb_split` coverage**

Add a new enabled flag near the other PFF signal flags in `src/fantasy_sim/validation/coverage.py`:

```python
    qb_split_enabled = _signal_enabled(
        config,
        ("pff_config", "pff"),
        ("pff", "qb_split"),
        nested_path=("qb_split",),
    )
```

Add required paths by season:

```python
    qb_split_paths_by_season: dict[int, list[Path]] = {
        season: [
            pff_path / f"passing_detail_{season}.parquet",
            pff_path / f"passing_summary_{season}.parquet",
            cache_path / f"rosters_weekly_{season}.parquet",
        ]
        for season in seasons
    }
```

Return the new signal alongside the existing `pff.depth_role` block:

```python
        "pff.qb_split": _build_signal(
            pff_enabled and qb_split_enabled,
            seasons,
            _covered_seasons_from_required_paths(seasons, qb_split_paths_by_season),
            note=(
                "Requires passing_detail parquet, passing_summary parquet, "
                "and rosters_weekly cache to build the PFF QB crosswalk"
            ),
        ),
```

- [ ] **Step 4: Run the coverage tests to verify they pass**

Run:

```bash
uv run pytest tests/test_validation/test_coverage.py -k "qb_split" -v
```

Expected: PASS with `pff.qb_split` reporting full/partial/disabled correctly.

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/validation/coverage.py tests/test_validation/test_coverage.py
git commit -m "feat: add qb split coverage reporting"
```

### Task 3: Implement `QbSplitEngine`

**Files:**
- Create: `src/fantasy_sim/data/pff/qb_split.py`
- Test: `tests/test_data/test_pff/test_qb_split.py`

- [ ] **Step 1: Write the failing engine tests**

Create `tests/test_data/test_pff/test_qb_split.py` with these targeted cases:

```python
from unittest.mock import MagicMock

import numpy as np
import polars as pl

from fantasy_sim.data.pff.qb_split import QbSplitEngine
from fantasy_sim.data.pff.models import MatchupContext, QbSplitConfig, QbSplitFactors
from fantasy_sim.models.player import PlayerModel, PlayerOutcomes, PlayerUsage, TeamRoster


def _make_roster(team: str, qb_id: str = "00-0031234") -> TeamRoster:
    return TeamRoster(
        team=team,
        players=[
            PlayerModel(
                qb_id,
                "Starter QB",
                "QB",
                team,
                PlayerUsage(snap_share=1.0),
                PlayerOutcomes(),
            ),
            PlayerModel(
                f"{team}_WR1",
                "WR One",
                "WR",
                team,
                PlayerUsage(target_share=0.30),
                PlayerOutcomes(catch_rate=0.65, red_zone_catch_rate=0.60, receiving_yards_dist=np.array([8.0, 12.0])),
            ),
        ],
    )


def _passing_detail_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "season": [2023, 2023, 2024],
            "week": [10, 11, 3],
            "team": ["KC", "KC", "KC"],
            "player_id": [101, 101, 101],
            "game_id": [1, 2, 3],
            "pressure_dropbacks": [15, 14, 8],
            "no_pressure_dropbacks": [35, 32, 20],
            "pressure_completion_percent": [48.0, 50.0, 51.0],
            "no_pressure_completion_percent": [74.0, 75.0, 76.0],
            "pressure_ypa": [5.5, 5.8, 6.0],
            "no_pressure_ypa": [8.6, 8.4, 8.7],
        }
    )


def test_compute_returns_neutral_when_qb_crosswalk_is_missing():
    loader = MagicMock()
    loader.load_facet.return_value = _passing_detail_df()
    engine = QbSplitEngine(loader, QbSplitConfig(enabled=True))

    factors = engine.compute(
        roster=_make_roster("KC"),
        pff_crosswalk={},
        training_seasons=[2023, 2024],
        target_season=2024,
        max_week=4,
        matchup_context=MatchupContext(sack_rate_factor=1.10, ol_pass_block_factor=1.05),
    )

    assert factors == QbSplitFactors()


def test_compute_penalizes_pressure_sensitive_qb_in_tough_matchup():
    loader = MagicMock()
    loader.load_facet.return_value = _passing_detail_df()
    engine = QbSplitEngine(
        loader,
        QbSplitConfig(
            enabled=True,
            completion_sensitivity=0.75,
            yards_sensitivity=0.75,
            min_pressure_dropbacks=10,
            min_clean_dropbacks=20,
        ),
    )

    factors = engine.compute(
        roster=_make_roster("KC"),
        pff_crosswalk={101: "00-0031234"},
        training_seasons=[2023, 2024],
        target_season=2024,
        max_week=4,
        matchup_context=MatchupContext(sack_rate_factor=1.10, ol_pass_block_factor=1.08),
    )

    assert factors.catch_rate_factor < 1.0
    assert factors.yards_scale_factor < 1.0


def test_compute_returns_neutral_for_neutral_pressure_environment():
    loader = MagicMock()
    loader.load_facet.return_value = _passing_detail_df()
    engine = QbSplitEngine(
        loader,
        QbSplitConfig(enabled=True, min_pressure_dropbacks=10, min_clean_dropbacks=20),
    )

    factors = engine.compute(
        roster=_make_roster("KC"),
        pff_crosswalk={101: "00-0031234"},
        training_seasons=[2023, 2024],
        target_season=2024,
        max_week=4,
        matchup_context=MatchupContext(sack_rate_factor=1.0, ol_pass_block_factor=1.0),
    )

    assert factors == QbSplitFactors()


def test_compute_blends_current_and_previous_season_rows_early():
    loader = MagicMock()
    loader.load_facet.return_value = _passing_detail_df()
    engine = QbSplitEngine(
        loader,
        QbSplitConfig(
            enabled=True,
            completion_sensitivity=0.75,
            yards_sensitivity=0.75,
            min_pressure_dropbacks=20,
            min_clean_dropbacks=40,
            min_games=4,
            early_season_blend=True,
        ),
    )

    factors = engine.compute(
        roster=_make_roster("KC"),
        pff_crosswalk={101: "00-0031234"},
        training_seasons=[2023, 2024],
        target_season=2024,
        max_week=4,
        matchup_context=MatchupContext(sack_rate_factor=1.12, ol_pass_block_factor=1.06),
    )

    assert factors.catch_rate_factor < 1.0
    assert factors.yards_scale_factor < 1.0
```

- [ ] **Step 2: Run the engine tests to verify they fail**

Run:

```bash
uv run pytest tests/test_data/test_pff/test_qb_split.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'fantasy_sim.data.pff.qb_split'`.

- [ ] **Step 3: Write the engine implementation**

Create `src/fantasy_sim/data/pff/qb_split.py`:

```python
from __future__ import annotations

import numpy as np
import polars as pl

from fantasy_sim.data.pff.loader import PffLoader
from fantasy_sim.data.pff.models import MatchupContext, QbSplitConfig, QbSplitFactors
from fantasy_sim.models.player import TeamRoster

_REQUIRED_COLUMNS = {
    "season",
    "week",
    "team",
    "player_id",
    "game_id",
    "pressure_dropbacks",
    "no_pressure_dropbacks",
    "pressure_completion_percent",
    "no_pressure_completion_percent",
    "pressure_ypa",
    "no_pressure_ypa",
}


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0 or not np.isfinite(numerator) or not np.isfinite(denominator):
        return 1.0
    return float(numerator / denominator)


class QbSplitEngine:
    """Derive QB pressure-response factors from PFF passing-detail splits."""

    def __init__(self, loader: PffLoader, config: QbSplitConfig):
        self._loader = loader
        self._config = config
        self._cache: dict[str, pl.DataFrame] = {}

    def _load_cached(self, seasons: list[int]) -> pl.DataFrame:
        key = f"passing_detail_{'_'.join(str(season) for season in sorted(seasons))}"
        if key not in self._cache:
            self._cache[key] = self._loader.load_facet("passing_detail", seasons)
        return self._cache[key]

    def _aggregate_rows(
        self,
        seasons: list[int],
        target_season: int,
        max_week: int,
    ) -> pl.DataFrame:
        df = self._load_cached(seasons)
        if df.is_empty() or not _REQUIRED_COLUMNS.issubset(df.columns):
            return pl.DataFrame()

        filtered = df.filter(
            pl.col("season").is_in(seasons)
            & (
                (pl.col("season") < target_season)
                | ((pl.col("season") == target_season) & (pl.col("week") < max_week))
            )
        )
        if filtered.is_empty():
            return pl.DataFrame()

        return filtered.group_by(["season", "team", "player_id"]).agg(
            pl.col("game_id").n_unique().alias("games"),
            pl.col("pressure_dropbacks").sum().alias("pressure_dropbacks"),
            pl.col("no_pressure_dropbacks").sum().alias("no_pressure_dropbacks"),
            (
                (pl.col("pressure_completion_percent") * pl.col("pressure_dropbacks")).sum()
                / pl.col("pressure_dropbacks").sum()
            ).alias("pressure_completion_percent"),
            (
                (pl.col("no_pressure_completion_percent") * pl.col("no_pressure_dropbacks")).sum()
                / pl.col("no_pressure_dropbacks").sum()
            ).alias("no_pressure_completion_percent"),
            (
                (pl.col("pressure_ypa") * pl.col("pressure_dropbacks")).sum()
                / pl.col("pressure_dropbacks").sum()
            ).alias("pressure_ypa"),
            (
                (pl.col("no_pressure_ypa") * pl.col("no_pressure_dropbacks")).sum()
                / pl.col("no_pressure_dropbacks").sum()
            ).alias("no_pressure_ypa"),
        )

    def _blended_row(
        self,
        qb_rows: pl.DataFrame,
        target_season: int,
    ) -> dict | None:
        current = qb_rows.filter(pl.col("season") == target_season)
        previous = qb_rows.filter(pl.col("season") < target_season)

        current_row = current.row(0, named=True) if current.height == 1 else None
        previous_row = previous.group_by("player_id").agg(
            pl.col("games").sum().alias("games"),
            pl.col("pressure_dropbacks").sum().alias("pressure_dropbacks"),
            pl.col("no_pressure_dropbacks").sum().alias("no_pressure_dropbacks"),
            (
                (pl.col("pressure_completion_percent") * pl.col("pressure_dropbacks")).sum()
                / pl.col("pressure_dropbacks").sum()
            ).alias("pressure_completion_percent"),
            (
                (pl.col("no_pressure_completion_percent") * pl.col("no_pressure_dropbacks")).sum()
                / pl.col("no_pressure_dropbacks").sum()
            ).alias("no_pressure_completion_percent"),
            (
                (pl.col("pressure_ypa") * pl.col("pressure_dropbacks")).sum()
                / pl.col("pressure_dropbacks").sum()
            ).alias("pressure_ypa"),
            (
                (pl.col("no_pressure_ypa") * pl.col("no_pressure_dropbacks")).sum()
                / pl.col("no_pressure_dropbacks").sum()
            ).alias("no_pressure_ypa"),
        )
        previous_row = previous_row.row(0, named=True) if previous_row.height == 1 else None

        if current_row is None:
            return previous_row
        if (
            not self._config.early_season_blend
            or previous_row is None
            or current_row["games"] >= self._config.min_games
        ):
            return current_row

        weight = current_row["games"] / max(self._config.min_games, 1)
        return {
            "games": current_row["games"],
            "pressure_dropbacks": current_row["pressure_dropbacks"] + previous_row["pressure_dropbacks"],
            "no_pressure_dropbacks": current_row["no_pressure_dropbacks"] + previous_row["no_pressure_dropbacks"],
            "pressure_completion_percent": (
                weight * current_row["pressure_completion_percent"]
                + (1.0 - weight) * previous_row["pressure_completion_percent"]
            ),
            "no_pressure_completion_percent": (
                weight * current_row["no_pressure_completion_percent"]
                + (1.0 - weight) * previous_row["no_pressure_completion_percent"]
            ),
            "pressure_ypa": (
                weight * current_row["pressure_ypa"]
                + (1.0 - weight) * previous_row["pressure_ypa"]
            ),
            "no_pressure_ypa": (
                weight * current_row["no_pressure_ypa"]
                + (1.0 - weight) * previous_row["no_pressure_ypa"]
            ),
        }

    def compute(
        self,
        roster: TeamRoster,
        pff_crosswalk: dict[int, str],
        training_seasons: list[int],
        target_season: int,
        max_week: int,
        matchup_context: MatchupContext,
    ) -> QbSplitFactors:
        if not self._config.enabled or matchup_context is None:
            return QbSplitFactors()

        try:
            starter = roster.get_starting_qb()
        except ValueError:
            return QbSplitFactors()

        reverse_crosswalk = {nfl_id: pff_id for pff_id, nfl_id in pff_crosswalk.items()}
        pff_player_id = reverse_crosswalk.get(starter.player_id)
        if pff_player_id is None:
            return QbSplitFactors()

        aggregated = self._aggregate_rows(training_seasons, target_season, max_week)
        if aggregated.is_empty():
            return QbSplitFactors()

        qb_rows = aggregated.filter(pl.col("player_id") == pff_player_id)
        if qb_rows.is_empty():
            return QbSplitFactors()

        selected = self._blended_row(qb_rows.sort(["season"]), target_season)
        if selected is None:
            return QbSplitFactors()
        if (
            selected["games"] < self._config.min_games
            or selected["pressure_dropbacks"] < self._config.min_pressure_dropbacks
            or selected["no_pressure_dropbacks"] < self._config.min_clean_dropbacks
        ):
            return QbSplitFactors()

        qb_completion = _safe_ratio(
            selected["pressure_completion_percent"],
            selected["no_pressure_completion_percent"],
        )
        qb_yards = _safe_ratio(selected["pressure_ypa"], selected["no_pressure_ypa"])

        league_completion = (
            aggregated.select(
                (
                    pl.col("pressure_completion_percent")
                    / pl.col("no_pressure_completion_percent")
                ).mean()
            ).item()
            or 1.0
        )
        league_yards = (
            aggregated.select((pl.col("pressure_ypa") / pl.col("no_pressure_ypa")).mean()).item()
            or 1.0
        )

        completion_trait = _safe_ratio(qb_completion, league_completion)
        yards_trait = _safe_ratio(qb_yards, league_yards)
        pressure_environment = (
            matchup_context.sack_rate_factor * matchup_context.ol_pass_block_factor
        )
        if pressure_environment == 1.0:
            return QbSplitFactors()

        completion_factor = 1.0 + (
            (completion_trait - 1.0)
            * (pressure_environment - 1.0)
            * self._config.completion_sensitivity
        )
        yards_factor = 1.0 + (
            (yards_trait - 1.0)
            * (pressure_environment - 1.0)
            * self._config.yards_sensitivity
        )

        return QbSplitFactors(
            catch_rate_factor=float(np.clip(completion_factor, *self._config.catch_rate_clamp)),
            yards_scale_factor=float(np.clip(yards_factor, *self._config.yards_scale_clamp)),
        )
```

- [ ] **Step 4: Run the engine tests to verify they pass**

Run:

```bash
uv run pytest tests/test_data/test_pff/test_qb_split.py -v
```

Expected: PASS with neutral fallback and tough-matchup translation working.

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/pff/qb_split.py tests/test_data/test_pff/test_qb_split.py
git commit -m "feat: add qb split engine"
```

### Task 4: Wire `QbSplitEngine` Into `GameContextBuilder`

**Files:**
- Modify: `src/fantasy_sim/data/game_context.py`
- Test: `tests/test_data/test_pff/test_qb_split_integration.py`

- [ ] **Step 1: Write the failing integration tests**

Create `tests/test_data/test_pff/test_qb_split_integration.py`:

```python
from unittest.mock import MagicMock, patch

import numpy as np

from fantasy_sim.data.game_context import GameContextBuilder
from fantasy_sim.data.pff.models import MatchupContext, PffConfig, QbSplitConfig
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
                f"{team}_WR1",
                "WR One",
                "WR",
                team,
                PlayerUsage(target_share=0.40),
                PlayerOutcomes(catch_rate=0.65, red_zone_catch_rate=0.60, receiving_yards_dist=np.array([10.0, 14.0])),
            ),
        ],
    )


def test_qb_split_engine_created_when_enabled(tmp_path):
    pff_config = PffConfig(enabled=True, qb_split=QbSplitConfig(enabled=True))

    with patch("fantasy_sim.data.pff.loader.PffLoader") as mock_loader:
        mock_loader.return_value.is_available.return_value = True
        builder = GameContextBuilder(cache_dir=tmp_path / "cache", pff_config=pff_config)

    assert builder._qb_split_engine is not None


def test_build_game_applies_qb_split_after_tier_before_depth_role(tmp_path):
    builder = GameContextBuilder(cache_dir=tmp_path / "cache")
    builder.build_team_distributions = MagicMock(side_effect=[_make_dists("KC"), _make_dists("BUF")])
    builder.build_team_roster = MagicMock(side_effect=[_make_roster("KC"), _make_roster("BUF")])
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
    builder._pff_crosswalk = {101: "KC_QB", 202: "BUF_QB"}

    events: list[str] = []

    builder._matchup_engine = MagicMock()
    builder._matchup_engine.compute.side_effect = [
        MatchupContext(sack_rate_factor=1.05, ol_pass_block_factor=1.02),
        MatchupContext(sack_rate_factor=1.03, ol_pass_block_factor=1.01),
    ]

    builder._tier_engine = MagicMock()
    builder._tier_engine.apply_tiers.side_effect = lambda *args, **kwargs: events.append("tier")

    builder._qb_split_engine = MagicMock()
    builder._qb_split_engine.compute.side_effect = lambda *args, **kwargs: events.append("qb_split") or MagicMock(catch_rate_factor=1.0, yards_scale_factor=1.0)

    builder._depth_role_engine = MagicMock()
    builder._depth_role_engine.apply.side_effect = lambda *args, **kwargs: events.append("depth")

    builder._coverage_engine = MagicMock()
    builder._coverage_engine.compute.side_effect = lambda *args, **kwargs: events.append("coverage") or {}

    with patch("fantasy_sim.data.player_builder._normalize_roster_shares") as mock_normalize:
        mock_normalize.side_effect = lambda roster: events.append(f"normalize:{roster.team}")
        builder.build_game("KC", "BUF", training_seasons=[2024], target_season=2024, week=8)

    assert events == [
        "tier",
        "tier",
        "normalize:KC",
        "normalize:BUF",
        "qb_split",
        "qb_split",
        "depth",
        "depth",
        "normalize:KC",
        "normalize:BUF",
        "coverage",
        "coverage",
    ]


def test_apply_qb_split_only_mutates_pass_catcher_efficiency_fields():
    roster = _make_roster("KC")
    original_target_share = roster.players[1].usage.target_share
    original_red_zone = roster.players[1].outcomes.red_zone_catch_rate

    GameContextBuilder._apply_qb_split(
        roster,
        MagicMock(catch_rate_factor=0.97, yards_scale_factor=0.95),
    )

    assert roster.players[1].outcomes.catch_rate < 0.65
    assert roster.players[1].outcomes.red_zone_catch_rate < original_red_zone
    assert float(roster.players[1].outcomes.receiving_yards_dist.mean()) < 12.0
    assert roster.players[1].usage.target_share == original_target_share
    assert roster.players[0].usage.scramble_rate == 0.0
```

- [ ] **Step 2: Run the integration tests to verify they fail**

Run:

```bash
uv run pytest tests/test_data/test_pff/test_qb_split_integration.py -v
```

Expected: FAIL because `GameContextBuilder` has no `_qb_split_engine` wiring or qb-split runtime step yet.

- [ ] **Step 3: Write the runtime wiring**

In `src/fantasy_sim/data/game_context.py`, add engine construction in `__init__`:

```python
        self._qb_split_engine = None

        if self._pff_config.enabled and self._pff_config.qb_split.enabled and self._pff_loader:
            from fantasy_sim.data.pff.qb_split import QbSplitEngine

            self._qb_split_engine = QbSplitEngine(
                self._pff_loader,
                self._pff_config.qb_split,
            )
            logger.info("PFF QB split engine enabled")
```

Add a helper near `_apply_coverage`:

```python
    @staticmethod
    def _apply_qb_split(
        roster: TeamRoster,
        factors,
    ) -> None:
        if factors is None:
            return

        for player in roster.players:
            if player.position == "QB" or player.usage.target_share <= 0:
                continue

            if factors.catch_rate_factor != 1.0 and player.outcomes.catch_rate > 0:
                old_catch_rate = player.outcomes.catch_rate
                player.outcomes.catch_rate = max(
                    0.0,
                    min(1.0, player.outcomes.catch_rate * factors.catch_rate_factor),
                )
                if old_catch_rate > 0 and player.outcomes.red_zone_catch_rate > 0:
                    ratio = player.outcomes.catch_rate / old_catch_rate
                    player.outcomes.red_zone_catch_rate = max(
                        0.0,
                        min(1.0, player.outcomes.red_zone_catch_rate * ratio),
                    )

            if (
                factors.yards_scale_factor != 1.0
                and player.outcomes.receiving_yards_dist is not None
                and len(player.outcomes.receiving_yards_dist) > 0
            ):
                player.outcomes.receiving_yards_dist = (
                    player.outcomes.receiving_yards_dist * factors.yards_scale_factor
                )
```

Rename the matchup and team-context locals so qb-split reads the real
`MatchupContext` instead of the later team-context object:

```python
        home_matchup_ctx = MatchupContext()
        away_matchup_ctx = MatchupContext()
        if self._matchup_engine is not None and target_season and week:
            home_matchup_ctx = self._matchup_engine.compute(
                defense_team=away_team,
                offense_team=home_team,
                target_season=target_season,
                max_week=week,
            )
            away_matchup_ctx = self._matchup_engine.compute(
                defense_team=home_team,
                offense_team=away_team,
                target_season=target_season,
                max_week=week,
            )
            self._apply_matchup(home_dists, home_roster, home_matchup_ctx)
            self._apply_matchup(away_dists, away_roster, away_matchup_ctx)
```

```python
            home_team_ctx = None
            away_team_ctx = None
            if self._team_context_engine is not None and target_season and week:
                home_team_ctx = self._team_context_engine.compute(
                    team=home_roster.team,
                    target_season=target_season,
                    max_week=week,
                    pbp=pbp_df,
                )
                away_team_ctx = self._team_context_engine.compute(
                    team=away_roster.team,
                    target_season=target_season,
                    max_week=week,
                    pbp=pbp_df,
                )
```

```python
            self._tier_engine.apply_tiers(
                home_roster,
                self._pff_crosswalk,
                training_seasons,
                pbp=pbp_df,
                nfl_roster=nfl_roster_df,
                target_season=roster_season,
                team_context=home_team_ctx,
                cpoe_map=combined_cpoe_map if combined_cpoe_map else None,
            )
            self._tier_engine.apply_tiers(
                away_roster,
                self._pff_crosswalk,
                training_seasons,
                pbp=pbp_df,
                nfl_roster=nfl_roster_df,
                target_season=roster_season,
                team_context=away_team_ctx,
                cpoe_map=combined_cpoe_map if combined_cpoe_map else None,
            )
```

Insert the runtime step after tier normalization and before `depth_role`:

```python
        if self._qb_split_engine is not None and target_season and week:
            self._ensure_pff_crosswalk(training_seasons, target_season)

            home_qb_split = self._qb_split_engine.compute(
                roster=home_roster,
                pff_crosswalk=self._pff_crosswalk,
                training_seasons=training_seasons,
                target_season=target_season,
                max_week=week,
                matchup_context=home_matchup_ctx,
            )
            away_qb_split = self._qb_split_engine.compute(
                roster=away_roster,
                pff_crosswalk=self._pff_crosswalk,
                training_seasons=training_seasons,
                target_season=target_season,
                max_week=week,
                matchup_context=away_matchup_ctx,
            )
            self._apply_qb_split(home_roster, home_qb_split)
            self._apply_qb_split(away_roster, away_qb_split)
```

- [ ] **Step 4: Run the integration tests to verify they pass**

Run:

```bash
uv run pytest tests/test_data/test_pff/test_qb_split_integration.py -v
```

Expected: PASS with qb-split created when enabled and ordered between tier and depth-role.

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/game_context.py tests/test_data/test_pff/test_qb_split_integration.py
git commit -m "feat: wire qb split into game context"
```

### Task 5: Run The Focused Test Slice, Validate The Feature, And Update Docs

**Files:**
- Modify: `docs/accuracy-roadmap.md`
- Modify: `docs/accuracy-stack-audit.md`

- [ ] **Step 1: Run the full qb-split implementation test slice**

Run:

```bash
uv run pytest \
  tests/test_data/test_pff/test_config.py \
  tests/test_validation/test_config.py \
  tests/test_validation/test_coverage.py \
  tests/test_data/test_pff/test_qb_split.py \
  tests/test_data/test_pff/test_qb_split_integration.py -k "qb_split" -v
```

Expected: PASS for config, coverage, engine, and integration coverage added in Tasks 1-4.

- [ ] **Step 2: Run the marginal validation artifact**

Run:

```bash
uv run python scripts/validate.py \
  --baseline defaults \
  --set pff.qb_split.enabled=true \
  --sims 50 \
  --label "phase-5-qb-split-v1"
```

Expected:

- validation header prints explicit `pff.qb_split=...` coverage
- output records a new marginal-lift artifact against the current defaults stack

- [ ] **Step 3: Update `docs/accuracy-roadmap.md` with the real Phase 5C artifact**

Edit the Phase 5 section so it records:

- `QB split engine` as implemented and validated
- the exact artifact label `phase-5-qb-split-v1`
- baseline `defaults`
- comparison mode `marginal_lift`
- the exact `pff.qb_split=...` coverage string printed by the run
- the exact top-line deltas from the run
- the final verdict:
  - keep `pff.qb_split.enabled: false` if the result is flat or regressive
  - promote only if the result clears the spec gate

Do not round or restate the numbers; copy the exact run output values into the existing Phase 5 format already used for Phase 5A and 5B.

- [ ] **Step 4: Update `docs/accuracy-stack-audit.md` with the real current-state note**

Edit the Phase 5 section and current defaults readout so it records:

- `pff.qb_split.enabled: false` if the slice is not promoted, or `true` only if it is promoted
- that `passing_detail` is now used by the runtime through `pff.qb_split`
- the exact artifact label, coverage string, and top-line deltas
- the current verdict and whether the next follow-on priority remains `RB scheme-fit engine`

Keep the wording consistent with the existing audit style: built state, data coverage, verdict, and next follow-on.

- [ ] **Step 5: Commit**

```bash
git add docs/accuracy-roadmap.md docs/accuracy-stack-audit.md
git commit -m "docs: record qb split validation result"
```

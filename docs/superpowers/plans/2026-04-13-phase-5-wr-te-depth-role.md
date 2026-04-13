# Phase 5 WR/TE Depth-Role V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new pre-sim PFF `depth_role` engine that uses `receiving_depth` to nudge WR/TE `target_share` and `air_yards_share`, validate it as an isolated marginal-lift experiment, and keep the deferred QB, RB, and WR/TE-efficiency work visible in the roadmap and audit.

**Architecture:** Extend the existing PFF config family with a new nested `depth_role` section, implement a `DepthRoleEngine` that computes team-relative WR/TE role signals from `receiving_depth`, and wire it into `GameContextBuilder` after `tier_engine` and before `coverage`. Keep the first slice narrow: role/volume only, no catch-rate or yards-efficiency mutation, and add explicit validation coverage so Phase 5 evidence stays attributable.

**Tech Stack:** Python 3.12+, polars, dataclasses, numpy, pytest, YAML

**Spec:** `docs/superpowers/specs/2026-04-13-phase-5-wr-te-depth-role-design.md`

---

## File Map

- `config/defaults.yaml`
  - Add the new `pff.depth_role` section with conservative WR and TE defaults.
- `src/fantasy_sim/data/pff/models.py`
  - Add typed config/data classes for the new engine.
- `src/fantasy_sim/data/pff/config.py`
  - Parse the new `pff.depth_role` block into `PffConfig`.
- `src/fantasy_sim/data/pff/depth_role.py`
  - New engine: load `receiving_depth`, compute player role factors, apply bounded WR/TE share mutations.
- `src/fantasy_sim/data/game_context.py`
  - Instantiate the engine and run it after tier/team-context and before coverage.
- `src/fantasy_sim/validation/coverage.py`
  - Add `pff.depth_role`, `pff.depth_role.wr`, and `pff.depth_role.te` coverage signals.
- `tests/test_data/test_pff/test_config.py`
  - Add config-parsing tests for `pff.depth_role`.
- `tests/test_data/test_pff/test_depth_role.py`
  - Add focused engine tests for factor computation, early-season blending, and neutral fallback.
- `tests/test_data/test_pff/test_depth_role_integration.py`
  - Add builder creation and runtime-order tests for the new engine.
- `tests/test_validation/test_config.py`
  - Add override-propagation coverage for `pff.depth_role`.
- `tests/test_validation/test_coverage.py`
  - Add coverage tests for the new signal family.
- `docs/accuracy-roadmap.md`
  - Mark Phase 5 status, current priority, next priority, and deferrals.
- `docs/accuracy-stack-audit.md`
  - Update current defaults, local data coverage, fixed caveats, and explicit Phase 5 deferrals.

### Task 1: Add The `pff.depth_role` Config Family

**Files:**
- Modify: `config/defaults.yaml`
- Modify: `src/fantasy_sim/data/pff/models.py`
- Modify: `src/fantasy_sim/data/pff/config.py`
- Modify: `tests/test_data/test_pff/test_config.py`
- Modify: `tests/test_validation/test_config.py`

- [ ] **Step 1: Write the failing config tests**

Add these tests to `tests/test_data/test_pff/test_config.py`:

```python
from fantasy_sim.data.pff.models import DepthRoleConfig, DepthRolePositionConfig


def test_load_pff_config_depth_role_defaults():
    cfg = load_pff_config({"pff": {"enabled": True}})

    assert isinstance(cfg.depth_role, DepthRoleConfig)
    assert cfg.depth_role.enabled is False
    assert cfg.depth_role.positions == ("WR", "TE")
    assert cfg.depth_role.min_routes == 15
    assert cfg.depth_role.min_targets == 6
    assert cfg.depth_role.min_games == 4
    assert cfg.depth_role.early_season_blend is True
    assert cfg.depth_role.wr == DepthRolePositionConfig(
        target_share_sensitivity=0.10,
        air_yards_share_sensitivity=0.12,
        factor_clamp=(0.94, 1.06),
    )
    assert cfg.depth_role.te == DepthRolePositionConfig(
        target_share_sensitivity=0.08,
        air_yards_share_sensitivity=0.06,
        factor_clamp=(0.95, 1.05),
    )


def test_load_pff_config_depth_role_custom_values():
    cfg = load_pff_config(
        {
            "pff": {
                "enabled": True,
                "depth_role": {
                    "enabled": True,
                    "positions": ["WR"],
                    "min_routes": 22,
                    "min_targets": 9,
                    "min_games": 5,
                    "early_season_blend": False,
                    "wr": {
                        "target_share_sensitivity": 0.14,
                        "air_yards_share_sensitivity": 0.16,
                        "factor_clamp": [0.92, 1.08],
                    },
                    "te": {
                        "target_share_sensitivity": 0.07,
                        "air_yards_share_sensitivity": 0.05,
                        "factor_clamp": [0.96, 1.04],
                    },
                },
            }
        }
    )

    assert cfg.depth_role.enabled is True
    assert cfg.depth_role.positions == ("WR",)
    assert cfg.depth_role.min_routes == 22
    assert cfg.depth_role.min_targets == 9
    assert cfg.depth_role.min_games == 5
    assert cfg.depth_role.early_season_blend is False
    assert cfg.depth_role.wr.factor_clamp == (0.92, 1.08)
    assert cfg.depth_role.te.factor_clamp == (0.96, 1.04)
```

Add this test to `tests/test_validation/test_config.py`:

```python
def test_pff_depth_role_override_propagates():
    defaults = load_defaults()
    overridden = apply_overrides(
        defaults,
        [
            "pff.depth_role.enabled=true",
            "pff.depth_role.wr.target_share_sensitivity=0.14",
        ],
    )

    configs = build_engine_configs(overridden)

    assert configs["pff_config"] is not None
    assert configs["pff_config"].depth_role.enabled is True
    assert configs["pff_config"].depth_role.wr.target_share_sensitivity == 0.14
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_data/test_pff/test_config.py tests/test_validation/test_config.py -v`

Expected: FAIL with `ImportError` or `AttributeError` because `DepthRoleConfig`,
`DepthRolePositionConfig`, and `PffConfig.depth_role` do not exist yet.

- [ ] **Step 3: Add the new config dataclasses, parser support, and defaults**

Add these dataclasses to `src/fantasy_sim/data/pff/models.py` just above
`PffConfig`:

```python
@dataclass
class DepthRolePositionConfig:
    """Position-specific sensitivity and clamps for PFF depth-role adjustments."""
    target_share_sensitivity: float
    air_yards_share_sensitivity: float
    factor_clamp: tuple[float, float]


@dataclass
class DepthRoleConfig:
    """Configuration for the PFF WR/TE depth-role engine."""
    enabled: bool = False
    positions: tuple[str, ...] = ("WR", "TE")
    wr: DepthRolePositionConfig = field(
        default_factory=lambda: DepthRolePositionConfig(
            target_share_sensitivity=0.10,
            air_yards_share_sensitivity=0.12,
            factor_clamp=(0.94, 1.06),
        )
    )
    te: DepthRolePositionConfig = field(
        default_factory=lambda: DepthRolePositionConfig(
            target_share_sensitivity=0.08,
            air_yards_share_sensitivity=0.06,
            factor_clamp=(0.95, 1.05),
        )
    )
    min_routes: int = 15
    min_targets: int = 6
    min_games: int = 4
    early_season_blend: bool = True
```

Extend `PffConfig` in the same file:

```python
depth_role: DepthRoleConfig = field(default_factory=DepthRoleConfig)
```

Update the import list and parser in `src/fantasy_sim/data/pff/config.py`:

```python
from fantasy_sim.data.pff.models import (
    ArchetypeConfig,
    CoverageConfig,
    DepthRoleConfig,
    DepthRolePositionConfig,
    DstBaselineConfig,
    KickerConfig,
    MatchupConfig,
    NcaaPriorsConfig,
    NcaaRookieConfig,
    PffConfig,
    PositionGradeConfig,
    ScheduleAdjustmentConfig,
    TalentConfig,
    TeamContextConfig,
    TierConfig,
)
```

```python
    depth_role_raw = pff.get("depth_role", {})
    depth_role = DepthRoleConfig(
        enabled=depth_role_raw.get("enabled", False),
        positions=tuple(depth_role_raw.get("positions", ["WR", "TE"])),
        wr=DepthRolePositionConfig(
            target_share_sensitivity=depth_role_raw.get("wr", {}).get(
                "target_share_sensitivity",
                0.10,
            ),
            air_yards_share_sensitivity=depth_role_raw.get("wr", {}).get(
                "air_yards_share_sensitivity",
                0.12,
            ),
            factor_clamp=tuple(
                depth_role_raw.get("wr", {}).get("factor_clamp", [0.94, 1.06])
            ),
        ),
        te=DepthRolePositionConfig(
            target_share_sensitivity=depth_role_raw.get("te", {}).get(
                "target_share_sensitivity",
                0.08,
            ),
            air_yards_share_sensitivity=depth_role_raw.get("te", {}).get(
                "air_yards_share_sensitivity",
                0.06,
            ),
            factor_clamp=tuple(
                depth_role_raw.get("te", {}).get("factor_clamp", [0.95, 1.05])
            ),
        ),
        min_routes=depth_role_raw.get("min_routes", 15),
        min_targets=depth_role_raw.get("min_targets", 6),
        min_games=depth_role_raw.get("min_games", 4),
        early_season_blend=depth_role_raw.get("early_season_blend", True),
    )
```

And return it from `load_pff_config()`:

```python
        depth_role=depth_role,
```

Add this block to `config/defaults.yaml` inside the `pff:` section after
`coverage` and before `kicker`:

```yaml
  depth_role:
    enabled: false
    positions: [WR, TE]
    wr:
      target_share_sensitivity: 0.10
      air_yards_share_sensitivity: 0.12
      factor_clamp: [0.94, 1.06]
    te:
      target_share_sensitivity: 0.08
      air_yards_share_sensitivity: 0.06
      factor_clamp: [0.95, 1.05]
    min_routes: 15
    min_targets: 6
    min_games: 4
    early_season_blend: true
```

- [ ] **Step 4: Run the config tests**

Run: `uv run pytest tests/test_data/test_pff/test_config.py tests/test_validation/test_config.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add config/defaults.yaml src/fantasy_sim/data/pff/models.py src/fantasy_sim/data/pff/config.py tests/test_data/test_pff/test_config.py tests/test_validation/test_config.py
git commit -m "feat: add PFF depth role config family"
```

### Task 2: Implement The WR/TE Depth-Role Engine

**Files:**
- Create: `src/fantasy_sim/data/pff/depth_role.py`
- Modify: `src/fantasy_sim/data/pff/models.py`
- Create: `tests/test_data/test_pff/test_depth_role.py`

- [ ] **Step 1: Write the failing engine tests**

Create `tests/test_data/test_pff/test_depth_role.py`:

```python
"""Tests for the PFF WR/TE depth-role engine."""

from __future__ import annotations

import numpy as np
import polars as pl

from fantasy_sim.data.pff.depth_role import DepthRoleEngine
from fantasy_sim.data.pff.loader import PffLoader
from fantasy_sim.data.pff.models import DepthRoleConfig, DepthRolePositionConfig
from fantasy_sim.models.player import PlayerModel, PlayerOutcomes, PlayerUsage, TeamRoster


def _make_roster() -> TeamRoster:
    return TeamRoster(
        team="KC",
        players=[
            PlayerModel(
                "WR_A",
                "WR A",
                "WR",
                "KC",
                PlayerUsage(target_share=0.28, air_yards_share=0.34),
                PlayerOutcomes(),
            ),
            PlayerModel(
                "WR_B",
                "WR B",
                "WR",
                "KC",
                PlayerUsage(target_share=0.22, air_yards_share=0.24),
                PlayerOutcomes(),
            ),
            PlayerModel(
                "TE_A",
                "TE A",
                "TE",
                "KC",
                PlayerUsage(target_share=0.18, air_yards_share=0.12),
                PlayerOutcomes(),
            ),
            PlayerModel(
                "RB_A",
                "RB A",
                "RB",
                "KC",
                PlayerUsage(target_share=0.10, air_yards_share=0.04),
                PlayerOutcomes(),
            ),
        ],
    )


def _write_receiving_depth(pff_dir, season: int, rows: list[dict]) -> None:
    pff_dir.mkdir(parents=True, exist_ok=True)
    schema = {
        "player_id": pl.Int64,
        "player": pl.Utf8,
        "team": pl.Utf8,
        "position": pl.Utf8,
        "season": pl.Int64,
        "week": pl.Int64,
        "game_id": pl.Utf8,
        "routes": pl.Float64,
        "targets": pl.Float64,
        "short_targets": pl.Float64,
        "medium_targets": pl.Float64,
        "deep_targets": pl.Float64,
        "behind_los_targets": pl.Float64,
        "short_avg_depth_of_target": pl.Float64,
        "medium_avg_depth_of_target": pl.Float64,
        "deep_avg_depth_of_target": pl.Float64,
        "behind_los_avg_depth_of_target": pl.Float64,
    }
    df = pl.DataFrame(rows, schema=schema, infer_schema_length=None) if rows else pl.DataFrame(schema=schema)
    df.write_parquet(pff_dir / f"receiving_depth_{season}.parquet")


def _engine(pff_dir) -> DepthRoleEngine:
    config = DepthRoleConfig(
        enabled=True,
        positions=("WR", "TE"),
        wr=DepthRolePositionConfig(0.10, 0.12, (0.94, 1.06)),
        te=DepthRolePositionConfig(0.08, 0.06, (0.95, 1.05)),
        min_routes=15,
        min_targets=6,
        min_games=4,
        early_season_blend=True,
    )
    return DepthRoleEngine(PffLoader(pff_dir), config)


def test_apply_adjusts_wr_and_te_role_volume_only(tmp_path):
    pff_dir = tmp_path / "pff" / "processed" / "nfl"
    _write_receiving_depth(
        pff_dir,
        2024,
        [
            {
                "player_id": 101,
                "player": "WR A",
                "team": "KC",
                "position": "LWR",
                "season": 2024,
                "week": 1,
                "game_id": "g1",
                "routes": 30,
                "targets": 10,
                "short_targets": 2,
                "medium_targets": 3,
                "deep_targets": 5,
                "behind_los_targets": 0,
                "short_avg_depth_of_target": 4.0,
                "medium_avg_depth_of_target": 11.0,
                "deep_avg_depth_of_target": 24.0,
                "behind_los_avg_depth_of_target": -1.0,
            },
            {
                "player_id": 102,
                "player": "WR B",
                "team": "KC",
                "position": "RWR",
                "season": 2024,
                "week": 1,
                "game_id": "g1",
                "routes": 28,
                "targets": 6,
                "short_targets": 4,
                "medium_targets": 2,
                "deep_targets": 0,
                "behind_los_targets": 0,
                "short_avg_depth_of_target": 5.0,
                "medium_avg_depth_of_target": 10.0,
                "deep_avg_depth_of_target": 0.0,
                "behind_los_avg_depth_of_target": -1.0,
            },
            {
                "player_id": 103,
                "player": "TE A",
                "team": "KC",
                "position": "TE-L",
                "season": 2024,
                "week": 1,
                "game_id": "g1",
                "routes": 24,
                "targets": 8,
                "short_targets": 5,
                "medium_targets": 2,
                "deep_targets": 1,
                "behind_los_targets": 0,
                "short_avg_depth_of_target": 4.0,
                "medium_avg_depth_of_target": 8.0,
                "deep_avg_depth_of_target": 18.0,
                "behind_los_avg_depth_of_target": -1.0,
            },
        ],
    )
    roster = _make_roster()
    engine = _engine(pff_dir)

    engine.apply(
        roster,
        pff_crosswalk={101: "WR_A", 102: "WR_B", 103: "TE_A"},
        target_season=2024,
        max_week=18,
    )

    wr_a = next(player for player in roster.players if player.player_id == "WR_A")
    wr_b = next(player for player in roster.players if player.player_id == "WR_B")
    te_a = next(player for player in roster.players if player.player_id == "TE_A")
    rb_a = next(player for player in roster.players if player.player_id == "RB_A")

    assert wr_a.usage.target_share > 0.28
    assert wr_a.usage.air_yards_share > 0.34
    assert wr_b.usage.air_yards_share < 0.24
    assert te_a.usage.target_share > 0.18
    assert rb_a.usage.target_share == 0.10


def test_low_sample_players_stay_neutral(tmp_path):
    pff_dir = tmp_path / "pff" / "processed" / "nfl"
    _write_receiving_depth(
        pff_dir,
        2024,
        [
            {
                "player_id": 101,
                "player": "WR A",
                "team": "KC",
                "position": "LWR",
                "season": 2024,
                "week": 1,
                "game_id": "g1",
                "routes": 6,
                "targets": 2,
                "short_targets": 1,
                "medium_targets": 1,
                "deep_targets": 0,
                "behind_los_targets": 0,
                "short_avg_depth_of_target": 5.0,
                "medium_avg_depth_of_target": 11.0,
                "deep_avg_depth_of_target": 0.0,
                "behind_los_avg_depth_of_target": -1.0,
            },
        ],
    )
    roster = _make_roster()
    engine = _engine(pff_dir)

    engine.apply(roster, {101: "WR_A"}, 2024, 18)

    wr_a = next(player for player in roster.players if player.player_id == "WR_A")
    assert wr_a.usage.target_share == 0.28
    assert wr_a.usage.air_yards_share == 0.34


def test_early_season_blend_uses_previous_season_when_current_sample_is_thin(tmp_path):
    pff_dir = tmp_path / "pff" / "processed" / "nfl"
    _write_receiving_depth(
        pff_dir,
        2023,
        [
            {
                "player_id": 101,
                "player": "WR A",
                "team": "KC",
                "position": "LWR",
                "season": 2023,
                "week": 10,
                "game_id": "old",
                "routes": 34,
                "targets": 11,
                "short_targets": 2,
                "medium_targets": 3,
                "deep_targets": 6,
                "behind_los_targets": 0,
                "short_avg_depth_of_target": 5.0,
                "medium_avg_depth_of_target": 11.0,
                "deep_avg_depth_of_target": 23.0,
                "behind_los_avg_depth_of_target": -1.0,
            }
        ],
    )
    _write_receiving_depth(
        pff_dir,
        2024,
        [
            {
                "player_id": 101,
                "player": "WR A",
                "team": "KC",
                "position": "LWR",
                "season": 2024,
                "week": 1,
                "game_id": "new",
                "routes": 10,
                "targets": 2,
                "short_targets": 2,
                "medium_targets": 0,
                "deep_targets": 0,
                "behind_los_targets": 0,
                "short_avg_depth_of_target": 3.0,
                "medium_avg_depth_of_target": 0.0,
                "deep_avg_depth_of_target": 0.0,
                "behind_los_avg_depth_of_target": -1.0,
            }
        ],
    )
    roster = _make_roster()
    engine = _engine(pff_dir)

    engine.apply(roster, {101: "WR_A"}, 2024, 2)

    wr_a = next(player for player in roster.players if player.player_id == "WR_A")
    assert wr_a.usage.air_yards_share > 0.34


def test_missing_crosswalk_stays_neutral(tmp_path):
    pff_dir = tmp_path / "pff" / "processed" / "nfl"
    _write_receiving_depth(pff_dir, 2024, [])
    roster = _make_roster()
    engine = _engine(pff_dir)

    engine.apply(roster, {}, 2024, 18)

    wr_a = next(player for player in roster.players if player.player_id == "WR_A")
    assert wr_a.usage.target_share == 0.28
    assert wr_a.usage.air_yards_share == 0.34
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_data/test_pff/test_depth_role.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'fantasy_sim.data.pff.depth_role'`

- [ ] **Step 3: Implement the new engine and factor dataclass**

Add this helper dataclass to `src/fantasy_sim/data/pff/models.py`:

```python
@dataclass
class DepthRoleFactors:
    """Per-player bounded role adjustments from PFF receiving-depth data."""
    target_share_factor: float = 1.0
    air_yards_share_factor: float = 1.0
```

Create `src/fantasy_sim/data/pff/depth_role.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import polars as pl

from fantasy_sim.data.pff.loader import PffLoader
from fantasy_sim.data.pff.models import (
    DepthRoleConfig,
    DepthRoleFactors,
    DepthRolePositionConfig,
)
from fantasy_sim.models.player import TeamRoster

_BUCKETS = ("behind_los", "short", "medium", "deep")


def _bounded_ratio_factor(
    observed: float,
    baseline: float,
    sensitivity: float,
    clamp: tuple[float, float],
) -> float:
    lower, upper = clamp
    if baseline <= 0 or not np.isfinite(observed) or not np.isfinite(baseline):
        return 1.0
    factor = 1.0 + ((observed / baseline) - 1.0) * sensitivity
    return float(np.clip(factor, lower, upper))


def _safe_bucket_target(column: str) -> pl.Expr:
    return pl.coalesce([pl.col(column).cast(pl.Float64), pl.lit(0.0)])


def _air_proxy_expr() -> pl.Expr:
    expr = pl.lit(0.0)
    for bucket in _BUCKETS:
        expr = expr + (
            _safe_bucket_target(f"{bucket}_targets")
            * pl.coalesce([pl.col(f"{bucket}_avg_depth_of_target").cast(pl.Float64), pl.lit(0.0)])
        )
    return expr.alias("_air_proxy")


class DepthRoleEngine:
    """Compute bounded WR/TE role-volume factors from PFF receiving-depth data."""

    def __init__(self, loader: PffLoader, config: DepthRoleConfig):
        self._loader = loader
        self._config = config
        self._cache: dict[str, pl.DataFrame] = {}

    def _load_cached(self, seasons: list[int]) -> pl.DataFrame:
        key = f"receiving_depth_{'_'.join(str(season) for season in sorted(seasons))}"
        if key not in self._cache:
            self._cache[key] = self._loader.load_facet("receiving_depth", seasons)
        return self._cache[key]

    def _aggregate_team_roles(
        self,
        seasons: list[int],
        target_season: int,
        max_week: int,
        pff_crosswalk: dict[int, str],
    ) -> pl.DataFrame:
        df = self._load_cached(seasons)
        if df.is_empty():
            return pl.DataFrame()

        reverse_crosswalk = pl.DataFrame(
            {
                "pff_player_id": list(pff_crosswalk.keys()),
                "player_id": list(pff_crosswalk.values()),
            }
        )
        if reverse_crosswalk.is_empty():
            return pl.DataFrame()

        df = (
            df.rename({"player_id": "pff_player_id"})
            .join(reverse_crosswalk, on="pff_player_id", how="inner")
            .filter(pl.col("position").is_in(list(self._config.positions)))
            .filter(pl.col("season").is_in(seasons))
            .filter(pl.col("week") < max_week)
            .with_columns(
                pl.coalesce([pl.col("routes").cast(pl.Float64), pl.lit(0.0)]).alias("_routes"),
                pl.coalesce([pl.col("targets").cast(pl.Float64), pl.lit(0.0)]).alias("_targets"),
                _air_proxy_expr(),
            )
        )
        if df.is_empty():
            return pl.DataFrame()

        player_roles = (
            df.group_by(["season", "team", "player_id", "position"])
            .agg(
                pl.col("_routes").sum().alias("routes"),
                pl.col("_targets").sum().alias("targets"),
                pl.col("_air_proxy").sum().alias("air_proxy"),
                pl.col("game_id").n_unique().alias("games"),
            )
        )
        team_totals = (
            player_roles.group_by(["season", "team"])
            .agg(
                pl.col("targets").sum().alias("team_targets"),
                pl.col("air_proxy").sum().alias("team_air_proxy"),
            )
        )
        return player_roles.join(team_totals, on=["season", "team"], how="left").with_columns(
            pl.when(pl.col("team_targets") > 0)
            .then(pl.col("targets") / pl.col("team_targets"))
            .otherwise(pl.lit(0.0))
            .alias("target_role"),
            pl.when(pl.col("team_air_proxy") > 0)
            .then(pl.col("air_proxy") / pl.col("team_air_proxy"))
            .otherwise(pl.lit(0.0))
            .alias("air_role"),
        )

    def _position_config(self, position: str) -> DepthRolePositionConfig:
        return self._config.wr if position == "WR" else self._config.te

    def _blended_role_row(
        self,
        current_row: dict | None,
        previous_row: dict | None,
    ) -> dict | None:
        if current_row is None and previous_row is None:
            return None
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
            "target_role": weight * current_row["target_role"] + (1.0 - weight) * previous_row["target_role"],
            "air_role": weight * current_row["air_role"] + (1.0 - weight) * previous_row["air_role"],
            "routes": current_row["routes"],
            "targets": current_row["targets"],
            "games": current_row["games"],
        }

    def apply(
        self,
        roster: TeamRoster,
        pff_crosswalk: dict[int, str],
        target_season: int,
        max_week: int,
    ) -> None:
        if not self._config.enabled or max_week is None or target_season is None:
            return
        role_rows = self._aggregate_team_roles(
            [target_season - 1, target_season],
            target_season,
            max_week,
            pff_crosswalk,
        )
        if role_rows.is_empty():
            return

        team_rows = role_rows.filter(pl.col("team") == roster.team)
        if team_rows.is_empty():
            return

        current_rows = {
            row["player_id"]: row
            for row in team_rows.filter(pl.col("season") == target_season).iter_rows(named=True)
        }
        previous_rows = {
            row["player_id"]: row
            for row in team_rows.filter(pl.col("season") == target_season - 1).iter_rows(named=True)
        }

        for player in roster.players:
            if player.position not in self._config.positions:
                continue
            row = self._blended_role_row(
                current_rows.get(player.player_id),
                previous_rows.get(player.player_id),
            )
            if row is None:
                continue
            if row["routes"] < self._config.min_routes or row["targets"] < self._config.min_targets:
                continue

            position_cfg = self._position_config(player.position)
            factors = DepthRoleFactors(
                target_share_factor=_bounded_ratio_factor(
                    row["target_role"],
                    player.usage.target_share,
                    position_cfg.target_share_sensitivity,
                    position_cfg.factor_clamp,
                ),
                air_yards_share_factor=_bounded_ratio_factor(
                    row["air_role"],
                    player.usage.air_yards_share,
                    position_cfg.air_yards_share_sensitivity,
                    position_cfg.factor_clamp,
                ),
            )
            player.usage.target_share *= factors.target_share_factor
            player.usage.air_yards_share *= factors.air_yards_share_factor
```

- [ ] **Step 4: Run the engine tests**

Run: `uv run pytest tests/test_data/test_pff/test_depth_role.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/pff/models.py src/fantasy_sim/data/pff/depth_role.py tests/test_data/test_pff/test_depth_role.py
git commit -m "feat: implement PFF depth role engine"
```

### Task 3: Wire Depth-Role Into `GameContextBuilder`

**Files:**
- Modify: `src/fantasy_sim/data/game_context.py`
- Create: `tests/test_data/test_pff/test_depth_role_integration.py`

- [ ] **Step 1: Write the failing builder wiring tests**

Create `tests/test_data/test_pff/test_depth_role_integration.py`:

```python
from unittest.mock import MagicMock, patch

import numpy as np

from fantasy_sim.data.game_context import GameContextBuilder
from fantasy_sim.engine.types import TeamDistributions
from fantasy_sim.models.distributions import (
    DriveStartModel,
    KickingModel,
    PlayCallingDist,
    PlayOutcomeDist,
    TurnoverRates,
)
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
                f"{team}_WR1",
                "WR One",
                "WR",
                team,
                PlayerUsage(target_share=0.50, air_yards_share=0.50),
                PlayerOutcomes(),
            ),
            PlayerModel(
                f"{team}_TE1",
                "TE One",
                "TE",
                team,
                PlayerUsage(target_share=0.20, air_yards_share=0.12),
                PlayerOutcomes(),
            ),
        ],
    )


def test_depth_role_engine_created_when_enabled(tmp_path):
    from fantasy_sim.data.pff.models import DepthRoleConfig, PffConfig

    pff_config = PffConfig(
        enabled=True,
        depth_role=DepthRoleConfig(enabled=True),
    )

    with patch("fantasy_sim.data.pff.loader.PffLoader") as MockLoader:
        MockLoader.return_value.is_available.return_value = True
        builder = GameContextBuilder(cache_dir=tmp_path / "cache", pff_config=pff_config)

    assert builder._depth_role_engine is not None


def test_build_game_applies_depth_role_after_tier_before_coverage(tmp_path):
    builder = GameContextBuilder(cache_dir=tmp_path / "cache")
    builder.build_team_distributions = MagicMock(side_effect=[_make_dists("KC"), _make_dists("BUF")])
    builder.build_team_roster = MagicMock(side_effect=[_make_roster("KC"), _make_roster("BUF")])
    builder._availability_engine = None
    builder._usage_engine = None
    builder._tracking_engine = None
    builder._props_engine = None
    builder._matchup_engine = None
    builder._team_context_engine = None
    builder._dst_baseline_engine = None
    builder._kicker_engine = None
    builder._weather_engine = None
    builder._vegas_engine = None
    builder._ensure_pff_crosswalk = MagicMock()
    builder._pff_crosswalk = {}

    events: list[str] = []

    builder._tier_engine = MagicMock()
    builder._tier_engine.apply_tiers.side_effect = lambda *args, **kwargs: events.append("tier")
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
        "depth",
        "depth",
        "normalize:KC",
        "normalize:BUF",
        "coverage",
        "coverage",
    ]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_data/test_pff/test_depth_role_integration.py -v`

Expected: FAIL because `GameContextBuilder` has no `_depth_role_engine`
attribute and `build_game()` does not call the new engine yet.

- [ ] **Step 3: Wire the engine into the builder**

Add this block in `src/fantasy_sim/data/game_context.py` near the existing PFF
engine setup:

```python
        self._depth_role_engine = None
        if self._pff_config.enabled and self._pff_config.depth_role.enabled and self._pff_loader:
            from fantasy_sim.data.pff.depth_role import DepthRoleEngine

            self._depth_role_engine = DepthRoleEngine(
                self._pff_loader,
                self._pff_config.depth_role,
            )
            logger.info("PFF depth-role engine enabled")
```

Add this block in `build_game()` immediately after the tier/team-context block
and before coverage:

```python
        if self._depth_role_engine is not None and target_season and week:
            from fantasy_sim.data.player_builder import _normalize_roster_shares

            self._ensure_pff_crosswalk(training_seasons, target_season)
            self._depth_role_engine.apply(
                home_roster,
                pff_crosswalk=self._pff_crosswalk,
                target_season=target_season,
                max_week=week,
            )
            self._depth_role_engine.apply(
                away_roster,
                pff_crosswalk=self._pff_crosswalk,
                target_season=target_season,
                max_week=week,
            )
            _normalize_roster_shares(home_roster)
            _normalize_roster_shares(away_roster)
```

- [ ] **Step 4: Run the builder wiring tests**

Run: `uv run pytest tests/test_data/test_pff/test_depth_role_integration.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/game_context.py tests/test_data/test_pff/test_depth_role_integration.py
git commit -m "feat: wire depth role into game context"
```

### Task 4: Add Validation Coverage For `pff.depth_role`

**Files:**
- Modify: `src/fantasy_sim/validation/coverage.py`
- Modify: `tests/test_validation/test_coverage.py`

- [ ] **Step 1: Write the failing coverage tests**

Add these tests to `tests/test_validation/test_coverage.py`:

```python
def test_pff_depth_role_reports_full_when_receiving_depth_and_rosters_exist(tmp_path):
    pff_dir = tmp_path / "pff"
    cache_dir = tmp_path / "cache"
    for season in (2023, 2024):
        _write_parquet_placeholder(pff_dir / f"receiving_depth_{season}.parquet")
        _write_parquet_placeholder(cache_dir / f"rosters_weekly_{season}.parquet")

    engine_configs = _default_engine_configs()
    engine_configs["pff_config"].depth_role.enabled = True

    coverage = collect_signal_coverage(
        engine_configs,
        [2023, 2024],
        pff_dir=pff_dir,
        cache_dir=cache_dir,
    )

    assert coverage["pff.depth_role"] == SignalCoverage(
        enabled=True,
        status="full",
        covered_seasons=[2023, 2024],
        missing_seasons=[],
        note="Requires receiving_depth parquet plus rosters_weekly cache to build the PFF crosswalk",
    )
    assert coverage["pff.depth_role.wr"].status == "full"
    assert coverage["pff.depth_role.te"].status == "full"


def test_pff_depth_role_reports_partial_when_one_season_is_missing(tmp_path):
    pff_dir = tmp_path / "pff"
    cache_dir = tmp_path / "cache"
    _write_parquet_placeholder(pff_dir / "receiving_depth_2023.parquet")
    _write_parquet_placeholder(cache_dir / "rosters_weekly_2023.parquet")
    _write_parquet_placeholder(cache_dir / "rosters_weekly_2024.parquet")

    engine_configs = _default_engine_configs()
    engine_configs["pff_config"].depth_role.enabled = True

    coverage = collect_signal_coverage(
        engine_configs,
        [2023, 2024],
        pff_dir=pff_dir,
        cache_dir=cache_dir,
    )

    assert coverage["pff.depth_role"] == SignalCoverage(
        enabled=True,
        status="partial",
        covered_seasons=[2023],
        missing_seasons=[2024],
        note="Requires receiving_depth parquet plus rosters_weekly cache to build the PFF crosswalk",
    )


def test_pff_depth_role_position_signals_respect_configured_positions(tmp_path):
    pff_dir = tmp_path / "pff"
    cache_dir = tmp_path / "cache"
    for season in (2024,):
        _write_parquet_placeholder(pff_dir / f"receiving_depth_{season}.parquet")
        _write_parquet_placeholder(cache_dir / f"rosters_weekly_{season}.parquet")

    engine_configs = _default_engine_configs()
    engine_configs["pff_config"].depth_role.enabled = True
    engine_configs["pff_config"].depth_role.positions = ("WR",)

    coverage = collect_signal_coverage(
        engine_configs,
        [2024],
        pff_dir=pff_dir,
        cache_dir=cache_dir,
    )

    assert coverage["pff.depth_role.wr"].status == "full"
    assert coverage["pff.depth_role.te"].status == "disabled"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_validation/test_coverage.py -k "depth_role" -v`

Expected: FAIL because `collect_signal_coverage()` does not yet return any
`pff.depth_role*` keys.

- [ ] **Step 3: Add the new coverage signals**

In `src/fantasy_sim/validation/coverage.py`, compute the new flags and required
paths:

```python
    depth_role_enabled = _signal_enabled(
        config,
        ("pff_config", "pff"),
        ("pff", "depth_role"),
        nested_path=("depth_role",),
    )
    depth_role_positions = tuple(
        _config_get(_config_section(config, "pff_config") or _config_section(config, "pff"), "depth_role", "positions", default=("WR", "TE"))
        if _config_section(config, "pff_config") is not None or _config_section(config, "pff") is not None
        else ("WR", "TE")
    )
```

Add a required-path map:

```python
    depth_role_paths_by_season: dict[int, list[Path]] = {
        season: [
            pff_path / f"receiving_depth_{season}.parquet",
            cache_path / f"rosters_weekly_{season}.parquet",
        ]
        for season in seasons
    }
```

And include these signals in the returned dict:

```python
        "pff.depth_role": _build_signal(
            depth_role_enabled,
            seasons,
            _covered_seasons_from_required_paths(seasons, depth_role_paths_by_season),
            note="Requires receiving_depth parquet plus rosters_weekly cache to build the PFF crosswalk",
        ),
        "pff.depth_role.wr": _build_signal(
            depth_role_enabled and "WR" in depth_role_positions,
            seasons,
            _covered_seasons_from_required_paths(seasons, depth_role_paths_by_season),
            note="Requires receiving_depth parquet plus rosters_weekly cache to build the PFF crosswalk",
        ),
        "pff.depth_role.te": _build_signal(
            depth_role_enabled and "TE" in depth_role_positions,
            seasons,
            _covered_seasons_from_required_paths(seasons, depth_role_paths_by_season),
            note="Requires receiving_depth parquet plus rosters_weekly cache to build the PFF crosswalk",
        ),
```

- [ ] **Step 4: Run the coverage tests**

Run: `uv run pytest tests/test_validation/test_coverage.py -k "depth_role" -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/validation/coverage.py tests/test_validation/test_coverage.py
git commit -m "feat: report depth role validation coverage"
```

### Task 5: Run The Focused Verification Suite And Marginal Validation

**Files:**
- Modify: `docs/accuracy-roadmap.md`
- Modify: `docs/accuracy-stack-audit.md`

- [ ] **Step 1: Run the focused code verification suite**

Run:

```bash
uv run pytest \
  tests/test_data/test_pff/test_config.py \
  tests/test_data/test_pff/test_depth_role.py \
  tests/test_data/test_game_context.py \
  tests/test_validation/test_config.py \
  tests/test_validation/test_coverage.py -v
```

Expected: PASS

- [ ] **Step 2: Run the isolated marginal validation arm**

Run:

```bash
uv run python scripts/validate.py \
  --baseline defaults \
  --set pff.depth_role.enabled=true \
  --sims 50 \
  --label "phase-5-depth-role-v1"
```

Expected:

- the run completes without schema or coverage errors
- the header prints `pff.depth_role` coverage explicitly
- the artifact is interpretable as a clean `defaults` vs `defaults + depth_role`
  comparison

- [ ] **Step 3: Update the roadmap with status, next priority, and deferrals**

Edit `docs/accuracy-roadmap.md` and make the Phase 5 section reflect the actual
Phase 5A verdict.

Use this exact structure, filling in the validation artifact details from the
command you just ran:

```md
## Phase 5: PFF Granularity V2

### Status

Implemented for `WR/TE Depth-Role V1`.

- current Phase 5 priority: `WR/TE Depth-Role V1`
- next Phase 5 priority: `WR/TE efficiency v2`
- explicitly deferred:
  - `QB split engine`
  - `RB scheme-fit engine`

### Phase 5A Scope

- `receiving_depth` only
- `WR` and `TE` only
- pre-sim role/volume only
- `target_share` and `air_yards_share` only
- no catch-rate or receiving-efficiency mutation

### Validation Artifact

- label: `phase-5-depth-role-v1`
- baseline: `defaults`
- comparison mode: `marginal_lift`
- coverage: copy the exact `pff.depth_role`, `pff.depth_role.wr`, and `pff.depth_role.te` coverage readouts from the run
- result: copy the exact top-line deltas from the run
```

- [ ] **Step 4: Update the audit with defaults, data coverage, fixed caveats, and deferrals**

Edit `docs/accuracy-stack-audit.md` and add these concrete updates:

```md
## Phase 5 Depth-Role Notes

- `pff.depth_role` is now implemented in code
- current local `receiving_depth` NFL coverage is `2018-2025`
- `pff.depth_role` uses `receiving_depth` plus `rosters_weekly` crosswalk inputs
- local `injuries_2022-2024.parquet` exists
- legacy `market_history_weekly_2023.parquet` and `market_history_weekly_2024.parquet` exist locally
- `rushing_direction` is present locally but stored as nested `directions` rows, so RB scheme-fit remains deferred

### Explicit Phase 5 Deferrals

- `WR/TE efficiency v2`
- `QB split engine`
- `RB scheme-fit engine`
```

Also update the `Current Defaults` section to reflect the actual default state
after validation:

- if the engine remains default-off, keep `pff.depth_role.enabled: false`
- if it is promoted, change that line to `pff.depth_role.enabled: true`

- [ ] **Step 5: Commit the validation verdict and docs**

If validation is mixed or negative:

```bash
git add docs/accuracy-roadmap.md docs/accuracy-stack-audit.md
git commit -m "docs: record phase 5 depth role status"
```

If validation is clearly positive and you are promoting immediately, skip this
commit and fold the doc changes into Task 6.

### Task 6: Conditional Promotion If The Validation Gate Clears

**Files:**
- Modify: `config/defaults.yaml`
- Modify: `tests/test_validation/test_config.py`
- Modify: `docs/accuracy-roadmap.md`
- Modify: `docs/accuracy-stack-audit.md`

- [ ] **Step 1: Only proceed if the Phase 5A promotion gate is clearly satisfied**

Promotion precondition:

- at least one of WR or TE improved materially
- the other of WR or TE held without material regression
- overall weekly MAE did not regress materially
- QB and RB did not regress materially

If the run does not clear that bar, do not execute this task.

- [ ] **Step 2: Flip the default on and lock in the promoted state**

In `config/defaults.yaml`, change:

```yaml
  depth_role:
    enabled: false
```

to:

```yaml
  depth_role:
    enabled: true
```

Add this assertion to `tests/test_validation/test_config.py` inside
`test_defaults_produces_enabled_configs` or a new dedicated test:

```python
def test_defaults_include_enabled_depth_role_when_phase5_is_promoted():
    defaults = load_defaults()
    configs = build_engine_configs(defaults)

    assert configs["pff_config"] is not None
    assert configs["pff_config"].depth_role.enabled is True
```

- [ ] **Step 3: Update the docs from “implemented” to “implemented and promoted”**

Change the Phase 5 wording in both docs from “implemented” to “implemented and
promoted”, and keep the deferral ledger intact:

```md
- current Phase 5 priority completed: `WR/TE Depth-Role V1`
- next Phase 5 priority: `WR/TE efficiency v2`
- explicitly deferred:
  - `QB split engine`
  - `RB scheme-fit engine`
```

- [ ] **Step 4: Run the final verification**

Run:

```bash
uv run pytest \
  tests/test_data/test_pff/test_config.py \
  tests/test_data/test_pff/test_depth_role.py \
  tests/test_data/test_game_context.py \
  tests/test_validation/test_config.py \
  tests/test_validation/test_coverage.py -v
```

Expected: PASS

- [ ] **Step 5: Commit the promotion**

```bash
git add config/defaults.yaml tests/test_validation/test_config.py docs/accuracy-roadmap.md docs/accuracy-stack-audit.md
git commit -m "feat: promote phase 5 depth role defaults"
```

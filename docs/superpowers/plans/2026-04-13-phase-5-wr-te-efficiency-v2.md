# Phase 5 WR/TE Efficiency V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the existing PFF `depth_role` family with a separate WR/TE efficiency branch that nudges `catch_rate`, proportional `red_zone_catch_rate`, and base `receiving_yards_dist`, then validate it as an isolated marginal-lift slice and record the actual verdict in the roadmap and audit.

**Architecture:** Keep a single `DepthRoleEngine` and add a nested `pff.depth_role.efficiency` config branch so the engine can compute volume and efficiency features from the same aggregated `receiving_depth` rows without duplicating crosswalk or early-season blending logic. The new v2 branch must stay strictly efficiency-only: no `target_share`, no `air_yards_share`, no red-zone receiving-yard distribution work, and no bundle test with the existing Phase 5A volume branch unless a later task explicitly asks for that.

**Tech Stack:** Python 3.12+, polars, dataclasses, numpy, pytest, YAML

**Spec:** `docs/superpowers/specs/2026-04-13-phase-5-wr-te-efficiency-v2-design.md`

---

## File Map

- `config/defaults.yaml`
  - Add the nested `pff.depth_role.efficiency` section with conservative WR/TE defaults and keep it disabled by default.
- `src/fantasy_sim/data/pff/models.py`
  - Add typed efficiency config/dataclasses under the existing depth-role family.
- `src/fantasy_sim/data/pff/config.py`
  - Parse the nested efficiency block into `PffConfig.depth_role`.
- `src/fantasy_sim/data/pff/depth_role.py`
  - Extend the existing engine with efficiency feature extraction and bounded mutation helpers for `catch_rate`, `red_zone_catch_rate`, and `receiving_yards_dist`.
- `tests/test_data/test_pff/test_config.py`
  - Add config parsing tests for `pff.depth_role.efficiency`.
- `tests/test_validation/test_config.py`
  - Add override-propagation coverage for the nested efficiency config.
- `tests/test_data/test_pff/test_depth_role.py`
  - Add behavior tests for the efficiency branch, including catch-rate bounds, proportional red-zone scaling, yardage distribution scaling, and non-volume guarantees.
- `src/fantasy_sim/validation/coverage.py`
  - Add explicit efficiency-slice coverage reporting under the existing depth-role family.
- `tests/test_validation/test_coverage.py`
  - Add validation coverage tests for the efficiency-specific signals.
- `docs/accuracy-roadmap.md`
  - Record the actual v2 artifact and move the current Phase 5 priority to `WR/TE efficiency v2`.
- `docs/accuracy-stack-audit.md`
  - Record the new config state, coverage requirements, and the updated next-slice/deferral language.

### Task 1: Add The Nested `pff.depth_role.efficiency` Config Family

**Files:**
- Modify: `config/defaults.yaml`
- Modify: `src/fantasy_sim/data/pff/models.py`
- Modify: `src/fantasy_sim/data/pff/config.py`
- Modify: `tests/test_data/test_pff/test_config.py`
- Modify: `tests/test_validation/test_config.py`

- [ ] **Step 1: Write the failing config tests**

Add these tests to `tests/test_data/test_pff/test_config.py`:

```python
from fantasy_sim.data.pff.models import (
    DepthRoleEfficiencyConfig,
    DepthRoleEfficiencyPositionConfig,
)


def test_load_pff_config_depth_role_efficiency_defaults():
    cfg = load_pff_config({"pff": {"enabled": True}})

    eff = cfg.depth_role.efficiency
    assert isinstance(eff, DepthRoleEfficiencyConfig)
    assert eff.enabled is False
    assert eff.min_routes == 15
    assert eff.min_receptions == 6
    assert eff.min_games == 4
    assert eff.catch_rate_clamp == (0.94, 1.06)
    assert eff.yards_scale_clamp == (0.92, 1.08)
    assert eff.wr == DepthRoleEfficiencyPositionConfig(
        catch_rate_sensitivity=0.08,
        yards_scale_sensitivity=0.10,
    )
    assert eff.te == DepthRoleEfficiencyPositionConfig(
        catch_rate_sensitivity=0.06,
        yards_scale_sensitivity=0.08,
    )


def test_load_pff_config_depth_role_efficiency_custom_values():
    cfg = load_pff_config(
        {
            "pff": {
                "enabled": True,
                "depth_role": {
                    "efficiency": {
                        "enabled": True,
                        "min_routes": 18,
                        "min_receptions": 8,
                        "min_games": 5,
                        "catch_rate_clamp": [0.95, 1.05],
                        "yards_scale_clamp": [0.93, 1.07],
                        "wr": {
                            "catch_rate_sensitivity": 0.11,
                            "yards_scale_sensitivity": 0.13,
                        },
                        "te": {
                            "catch_rate_sensitivity": 0.09,
                            "yards_scale_sensitivity": 0.07,
                        },
                    }
                },
            }
        }
    )

    eff = cfg.depth_role.efficiency
    assert eff.enabled is True
    assert eff.min_routes == 18
    assert eff.min_receptions == 8
    assert eff.min_games == 5
    assert eff.catch_rate_clamp == (0.95, 1.05)
    assert eff.yards_scale_clamp == (0.93, 1.07)
    assert eff.wr.catch_rate_sensitivity == 0.11
    assert eff.wr.yards_scale_sensitivity == 0.13
    assert eff.te.catch_rate_sensitivity == 0.09
    assert eff.te.yards_scale_sensitivity == 0.07
```

Add this test to `tests/test_validation/test_config.py`:

```python
def test_pff_depth_role_efficiency_override_propagates():
    defaults = load_defaults()
    overridden = apply_overrides(
        defaults,
        [
            "pff.depth_role.efficiency.enabled=true",
            "pff.depth_role.efficiency.wr.catch_rate_sensitivity=0.11",
            "pff.depth_role.efficiency.te.yards_scale_sensitivity=0.07",
        ],
    )

    configs = build_engine_configs(overridden)

    assert configs["pff_config"] is not None
    eff = configs["pff_config"].depth_role.efficiency
    assert eff.enabled is True
    assert eff.wr.catch_rate_sensitivity == 0.11
    assert eff.te.yards_scale_sensitivity == 0.07
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_data/test_pff/test_config.py tests/test_validation/test_config.py -v`

Expected: FAIL because `DepthRoleEfficiencyConfig`,
`DepthRoleEfficiencyPositionConfig`, and
`cfg.depth_role.efficiency` do not exist yet.

- [ ] **Step 3: Add the new config dataclasses, parser support, and defaults**

Add these dataclasses to `src/fantasy_sim/data/pff/models.py` beneath the
existing depth-role config types:

```python
@dataclass
class DepthRoleEfficiencyPositionConfig:
    """Position-specific efficiency sensitivities for WR/TE depth-role v2."""
    catch_rate_sensitivity: float
    yards_scale_sensitivity: float


@dataclass
class DepthRoleEfficiencyConfig:
    """Configuration for WR/TE efficiency-only depth-role adjustments."""
    enabled: bool = False
    min_routes: int = 15
    min_receptions: int = 6
    min_games: int = 4
    catch_rate_clamp: tuple[float, float] = (0.94, 1.06)
    yards_scale_clamp: tuple[float, float] = (0.92, 1.08)
    wr: DepthRoleEfficiencyPositionConfig = field(
        default_factory=lambda: DepthRoleEfficiencyPositionConfig(
            catch_rate_sensitivity=0.08,
            yards_scale_sensitivity=0.10,
        )
    )
    te: DepthRoleEfficiencyPositionConfig = field(
        default_factory=lambda: DepthRoleEfficiencyPositionConfig(
            catch_rate_sensitivity=0.06,
            yards_scale_sensitivity=0.08,
        )
    )
```

Extend the existing `DepthRoleConfig` in the same file:

```python
    efficiency: DepthRoleEfficiencyConfig = field(
        default_factory=DepthRoleEfficiencyConfig
    )
```

Update the import list in `src/fantasy_sim/data/pff/config.py`:

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
    ScheduleAdjustmentConfig,
    TalentConfig,
    TeamContextConfig,
    TierConfig,
)
```

Add nested parser support inside the existing depth-role parse block:

```python
    efficiency_raw = depth_role_raw.get("efficiency", {})
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
        efficiency=DepthRoleEfficiencyConfig(
            enabled=efficiency_raw.get("enabled", False),
            min_routes=efficiency_raw.get("min_routes", 15),
            min_receptions=efficiency_raw.get("min_receptions", 6),
            min_games=efficiency_raw.get("min_games", 4),
            catch_rate_clamp=tuple(
                efficiency_raw.get("catch_rate_clamp", [0.94, 1.06])
            ),
            yards_scale_clamp=tuple(
                efficiency_raw.get("yards_scale_clamp", [0.92, 1.08])
            ),
            wr=DepthRoleEfficiencyPositionConfig(
                catch_rate_sensitivity=efficiency_raw.get("wr", {}).get(
                    "catch_rate_sensitivity",
                    0.08,
                ),
                yards_scale_sensitivity=efficiency_raw.get("wr", {}).get(
                    "yards_scale_sensitivity",
                    0.10,
                ),
            ),
            te=DepthRoleEfficiencyPositionConfig(
                catch_rate_sensitivity=efficiency_raw.get("te", {}).get(
                    "catch_rate_sensitivity",
                    0.06,
                ),
                yards_scale_sensitivity=efficiency_raw.get("te", {}).get(
                    "yards_scale_sensitivity",
                    0.08,
                ),
            ),
        ),
    )
```

Add this block to `config/defaults.yaml` inside `pff.depth_role`:

```yaml
    efficiency:
      enabled: false
      min_routes: 15
      min_receptions: 6
      min_games: 4
      catch_rate_clamp: [0.94, 1.06]
      yards_scale_clamp: [0.92, 1.08]
      wr:
        catch_rate_sensitivity: 0.08
        yards_scale_sensitivity: 0.10
      te:
        catch_rate_sensitivity: 0.06
        yards_scale_sensitivity: 0.08
```

- [ ] **Step 4: Run the config tests**

Run: `uv run pytest tests/test_data/test_pff/test_config.py tests/test_validation/test_config.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add config/defaults.yaml src/fantasy_sim/data/pff/models.py src/fantasy_sim/data/pff/config.py tests/test_data/test_pff/test_config.py tests/test_validation/test_config.py
git commit -m "feat: add depth role efficiency config"
```

### Task 2: Extend `DepthRoleEngine` With Efficiency Features And Mutations

**Files:**
- Modify: `src/fantasy_sim/data/pff/depth_role.py`
- Modify: `tests/test_data/test_pff/test_depth_role.py`

- [ ] **Step 1: Write the failing efficiency tests**

Add these tests to `tests/test_data/test_pff/test_depth_role.py`:

```python
def _efficiency_enabled_engine(
    pff_dir,
    *,
    early_season_blend: bool = True,
) -> DepthRoleEngine:
    config = DepthRoleConfig(
        enabled=True,
        positions=("WR", "TE"),
        wr=DepthRolePositionConfig(0.10, 0.12, (0.94, 1.06)),
        te=DepthRolePositionConfig(0.08, 0.06, (0.95, 1.05)),
        min_routes=15,
        min_targets=6,
        min_games=4,
        early_season_blend=early_season_blend,
        efficiency=DepthRoleEfficiencyConfig(
            enabled=True,
            min_routes=15,
            min_receptions=6,
            min_games=4,
            catch_rate_clamp=(0.94, 1.06),
            yards_scale_clamp=(0.92, 1.08),
            wr=DepthRoleEfficiencyPositionConfig(0.08, 0.10),
            te=DepthRoleEfficiencyPositionConfig(0.06, 0.08),
        ),
    )
    return DepthRoleEngine(PffLoader(pff_dir), config)


def test_efficiency_apply_adjusts_catch_rate_and_receiving_yards_dist_only(tmp_path):
    pff_dir = tmp_path / "pff" / "processed" / "nfl"
    _write_receiving_depth(
        pff_dir,
        2024,
        [
            _receiving_depth_row(
                player_id=101,
                player="WR A",
                team="KC",
                position="LWR",
                season=2024,
                week=1,
                game_id=1,
                side_routes={
                    "left_short_routes": 8,
                    "center_short_routes": 4,
                    "left_medium_routes": 5,
                    "center_medium_routes": 3,
                    "left_deep_routes": 4,
                    "right_deep_routes": 4,
                },
                targets={"short": 4, "medium": 3, "deep": 3},
                adots={"behind_los": -1.0, "short": 4.0, "medium": 11.0, "deep": 20.0},
                extras={
                    "short_receptions": 4,
                    "medium_receptions": 3,
                    "deep_receptions": 2,
                    "short_yards": 32,
                    "medium_yards": 39,
                    "deep_yards": 46,
                },
            ),
            _receiving_depth_row(
                player_id=103,
                player="TE A",
                team="KC",
                position="TE-L",
                season=2024,
                week=1,
                game_id=1,
                side_routes={
                    "center_short_routes": 7,
                    "left_short_routes": 5,
                    "center_medium_routes": 4,
                    "left_medium_routes": 2,
                    "center_deep_routes": 1,
                },
                targets={"short": 5, "medium": 2, "deep": 1},
                adots={"behind_los": -1.0, "short": 4.0, "medium": 8.0, "deep": 16.0},
                extras={
                    "short_receptions": 5,
                    "medium_receptions": 2,
                    "deep_receptions": 1,
                    "short_yards": 30,
                    "medium_yards": 18,
                    "deep_yards": 16,
                },
            ),
        ],
    )
    roster = _make_roster()
    wr_a = next(player for player in roster.players if player.player_id == "WR_A")
    te_a = next(player for player in roster.players if player.player_id == "TE_A")
    wr_a.outcomes.catch_rate = 0.60
    wr_a.outcomes.red_zone_catch_rate = 0.54
    wr_a.outcomes.receiving_yards_dist = np.array([8.0, 10.0, 12.0])
    te_a.outcomes.catch_rate = 0.68
    te_a.outcomes.red_zone_catch_rate = 0.62
    te_a.outcomes.receiving_yards_dist = np.array([6.0, 8.0, 10.0])

    original_wr_target_share = wr_a.usage.target_share
    original_wr_air_share = wr_a.usage.air_yards_share

    engine = _efficiency_enabled_engine(pff_dir)
    engine.apply(
        roster,
        pff_crosswalk={101: "WR_A", 103: "TE_A"},
        target_season=2024,
        max_week=18,
    )

    assert wr_a.usage.target_share == original_wr_target_share
    assert wr_a.usage.air_yards_share == original_wr_air_share
    assert wr_a.outcomes.catch_rate > 0.60
    assert wr_a.outcomes.red_zone_catch_rate > 0.54
    assert wr_a.outcomes.receiving_yards_dist.mean() > np.array([8.0, 10.0, 12.0]).mean()
    assert te_a.outcomes.catch_rate > 0.68


def test_efficiency_scales_red_zone_catch_rate_proportionally(tmp_path):
    pff_dir = tmp_path / "pff" / "processed" / "nfl"
    _write_receiving_depth(
        pff_dir,
        2024,
        [
            _receiving_depth_row(
                player_id=101,
                player="WR A",
                team="KC",
                position="LWR",
                season=2024,
                week=1,
                game_id=1,
                side_routes={"left_short_routes": 8, "left_medium_routes": 6, "left_deep_routes": 6},
                targets={"short": 4, "medium": 3, "deep": 3},
                adots={"short": 4.0, "medium": 11.0, "deep": 20.0, "behind_los": -1.0},
                extras={
                    "short_receptions": 4,
                    "medium_receptions": 3,
                    "deep_receptions": 2,
                    "short_yards": 32,
                    "medium_yards": 39,
                    "deep_yards": 46,
                },
            ),
        ],
    )
    roster = _make_roster()
    wr_a = next(player for player in roster.players if player.player_id == "WR_A")
    wr_a.outcomes.catch_rate = 0.60
    wr_a.outcomes.red_zone_catch_rate = 0.54
    wr_a.outcomes.receiving_yards_dist = np.array([8.0, 10.0, 12.0])

    engine = _efficiency_enabled_engine(pff_dir)
    engine.apply(roster, {101: "WR_A"}, 2024, 18)

    catch_ratio = wr_a.outcomes.catch_rate / 0.60
    rz_ratio = wr_a.outcomes.red_zone_catch_rate / 0.54
    assert rz_ratio == pytest.approx(catch_ratio, rel=1e-6)


def test_efficiency_stays_neutral_when_reception_sample_is_thin(tmp_path):
    pff_dir = tmp_path / "pff" / "processed" / "nfl"
    _write_receiving_depth(
        pff_dir,
        2024,
        [
            _receiving_depth_row(
                player_id=101,
                player="WR A",
                team="KC",
                position="LWR",
                season=2024,
                week=1,
                game_id=1,
                side_routes={"left_short_routes": 8, "left_medium_routes": 6, "left_deep_routes": 6},
                targets={"short": 3, "medium": 2, "deep": 1},
                adots={"short": 4.0, "medium": 11.0, "deep": 20.0, "behind_los": -1.0},
                extras={
                    "short_receptions": 2,
                    "medium_receptions": 1,
                    "deep_receptions": 0,
                    "short_yards": 14,
                    "medium_yards": 9,
                    "deep_yards": 0,
                },
            ),
        ],
    )
    roster = _make_roster()
    wr_a = next(player for player in roster.players if player.player_id == "WR_A")
    wr_a.outcomes.catch_rate = 0.60
    wr_a.outcomes.red_zone_catch_rate = 0.54
    wr_a.outcomes.receiving_yards_dist = np.array([8.0, 10.0, 12.0])
    original_dist = wr_a.outcomes.receiving_yards_dist.copy()

    engine = _efficiency_enabled_engine(pff_dir)
    engine.apply(roster, {101: "WR_A"}, 2024, 18)

    assert wr_a.outcomes.catch_rate == 0.60
    assert wr_a.outcomes.red_zone_catch_rate == 0.54
    assert np.array_equal(wr_a.outcomes.receiving_yards_dist, original_dist)


def test_efficiency_clamps_catch_rate_and_yards_scale(tmp_path):
    pff_dir = tmp_path / "pff" / "processed" / "nfl"
    _write_receiving_depth(
        pff_dir,
        2024,
        [
            _receiving_depth_row(
                player_id=101,
                player="WR A",
                team="KC",
                position="LWR",
                season=2024,
                week=1,
                game_id=1,
                side_routes={"left_short_routes": 10, "left_medium_routes": 8, "left_deep_routes": 8},
                targets={"short": 5, "medium": 4, "deep": 3},
                adots={"short": 4.0, "medium": 12.0, "deep": 25.0, "behind_los": -1.0},
                extras={
                    "short_receptions": 5,
                    "medium_receptions": 4,
                    "deep_receptions": 3,
                    "short_yards": 100,
                    "medium_yards": 120,
                    "deep_yards": 120,
                },
            ),
            _receiving_depth_row(
                player_id=103,
                player="TE A",
                team="KC",
                position="TE-L",
                season=2024,
                week=1,
                game_id=1,
                side_routes={"center_short_routes": 10, "center_medium_routes": 8, "center_deep_routes": 8},
                targets={"short": 5, "medium": 4, "deep": 3},
                adots={"short": 3.0, "medium": 7.0, "deep": 10.0, "behind_los": -1.0},
                extras={
                    "short_receptions": 1,
                    "medium_receptions": 1,
                    "deep_receptions": 0,
                    "short_yards": 5,
                    "medium_yards": 5,
                    "deep_yards": 0,
                },
            ),
        ],
    )
    roster = _make_roster()
    wr_a = next(player for player in roster.players if player.player_id == "WR_A")
    wr_a.outcomes.catch_rate = 0.60
    wr_a.outcomes.red_zone_catch_rate = 0.54
    wr_a.outcomes.receiving_yards_dist = np.array([8.0, 10.0, 12.0])

    engine = _efficiency_enabled_engine(pff_dir)
    engine.apply(roster, {101: "WR_A", 103: "TE_A"}, 2024, 18)

    assert wr_a.outcomes.catch_rate <= 0.60 * 1.06 + 1e-9
    assert wr_a.outcomes.receiving_yards_dist.mean() <= (
        np.array([8.0, 10.0, 12.0]).mean() * 1.08 + 1e-9
    )
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_data/test_pff/test_depth_role.py -k "efficiency" -v`

Expected: FAIL because the nested efficiency config does not exist yet and the
engine does not yet mutate any efficiency fields.

- [ ] **Step 3: Implement the efficiency branch in `DepthRoleEngine`**

Add these helpers to `src/fantasy_sim/data/pff/depth_role.py` near the existing
aggregation helpers:

```python
def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0 or not np.isfinite(numerator) or not np.isfinite(denominator):
        return 0.0
    return float(numerator / denominator)


def _bounded_delta_factor(
    observed: float,
    baseline: float,
    sensitivity: float,
    clamp: tuple[float, float],
) -> float:
    lower, upper = clamp
    if baseline <= 0 or not np.isfinite(observed) or not np.isfinite(baseline):
        return 1.0
    factor = 1.0 + (observed - baseline) * sensitivity
    return float(np.clip(factor, lower, upper))
```

Extend `_aggregate_team_roles()` so it also aggregates reception and yardage
efficiency fields from bucketed columns:

```python
                _sum_available_columns(
                    df.columns,
                    [f"{bucket}_receptions" for bucket in _BUCKETS],
                    "_receptions",
                ),
                _sum_available_columns(
                    df.columns,
                    [f"{bucket}_yards" for bucket in _BUCKETS],
                    "_yards",
                ),
```

Add per-player derived fields after aggregation:

```python
            .with_columns(
                pl.when(pl.col("targets") > 0)
                .then(pl.col("receptions") / pl.col("targets"))
                .otherwise(pl.lit(0.0))
                .alias("catch_efficiency"),
                pl.when(pl.col("receptions") > 0)
                .then(pl.col("yards") / pl.col("receptions"))
                .otherwise(pl.lit(0.0))
                .alias("yards_per_reception"),
            )
```

Add helpers inside `DepthRoleEngine`:

```python
    def _efficiency_position_config(self, position: str):
        return self._config.efficiency.wr if position == "WR" else self._config.efficiency.te

    def _apply_efficiency(
        self,
        player,
        row: dict,
    ) -> None:
        if not self._config.efficiency.enabled:
            return
        if row["routes"] < self._config.efficiency.min_routes:
            return
        if row["receptions"] < self._config.efficiency.min_receptions:
            return

        pos_cfg = self._efficiency_position_config(player.position)

        catch_factor = _bounded_ratio_factor(
            row["catch_efficiency"],
            player.outcomes.catch_rate,
            pos_cfg.catch_rate_sensitivity,
            self._config.efficiency.catch_rate_clamp,
        )
        yards_factor = _bounded_ratio_factor(
            row["yards_per_reception"],
            float(np.mean(player.outcomes.receiving_yards_dist))
            if player.outcomes.receiving_yards_dist is not None and len(player.outcomes.receiving_yards_dist) > 0
            else 0.0,
            pos_cfg.yards_scale_sensitivity,
            self._config.efficiency.yards_scale_clamp,
        )

        player.outcomes.catch_rate = float(np.clip(player.outcomes.catch_rate * catch_factor, 0.0, 1.0))
        if player.outcomes.red_zone_catch_rate > 0:
            player.outcomes.red_zone_catch_rate = float(
                np.clip(player.outcomes.red_zone_catch_rate * catch_factor, 0.0, 1.0)
            )
        if player.outcomes.receiving_yards_dist is not None:
            player.outcomes.receiving_yards_dist = (
                np.asarray(player.outcomes.receiving_yards_dist, dtype=float) * yards_factor
            )
```

Call `_apply_efficiency()` inside `apply()` after the existing volume-factor
logic for the player:

```python
            self._apply_efficiency(player, row)
```

Important constraints:

- do not touch `target_share` or `air_yards_share` inside `_apply_efficiency()`
- do not touch `rz_receiving_yards_dist`
- scale `red_zone_catch_rate` proportionally to the base catch-rate factor

- [ ] **Step 4: Run the efficiency tests**

Run: `uv run pytest tests/test_data/test_pff/test_depth_role.py -k "efficiency" -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/pff/models.py src/fantasy_sim/data/pff/depth_role.py tests/test_data/test_pff/test_depth_role.py
git commit -m "feat: add depth role efficiency adjustments"
```

### Task 3: Add Validation Coverage For The Efficiency Sub-Slice

**Files:**
- Modify: `src/fantasy_sim/validation/coverage.py`
- Modify: `tests/test_validation/test_coverage.py`

- [ ] **Step 1: Write the failing coverage tests**

Add these tests to `tests/test_validation/test_coverage.py`:

```python
def test_pff_depth_role_efficiency_reports_full_when_inputs_exist(tmp_path):
    pff_dir = tmp_path / "pff"
    cache_dir = tmp_path / "cache"
    for season in (2023, 2024):
        for facet in ("receiving_depth", "receiving_summary", "rushing_summary", "passing_summary"):
            _write_parquet_placeholder(pff_dir / f"{facet}_{season}.parquet")
        _write_parquet_placeholder(cache_dir / f"rosters_weekly_{season}.parquet")

    engine_configs = _default_engine_configs()
    engine_configs["pff_config"].depth_role.efficiency.enabled = True

    coverage = collect_signal_coverage(
        engine_configs,
        [2023, 2024],
        pff_dir=pff_dir,
        cache_dir=cache_dir,
    )

    assert coverage["pff.depth_role.efficiency"] == SignalCoverage(
        enabled=True,
        status="full",
        covered_seasons=[2023, 2024],
        missing_seasons=[],
        note="Requires receiving_depth, the PFF summary trio, and rosters_weekly cache to support the depth-role efficiency path",
    )


def test_pff_depth_role_efficiency_disabled_when_parent_family_disabled(tmp_path):
    pff_dir = tmp_path / "pff"
    cache_dir = tmp_path / "cache"
    for facet in ("receiving_depth", "receiving_summary", "rushing_summary", "passing_summary"):
        _write_parquet_placeholder(pff_dir / f"{facet}_2024.parquet")
    _write_parquet_placeholder(cache_dir / "rosters_weekly_2024.parquet")

    engine_configs = _default_engine_configs()
    engine_configs["pff_config"].enabled = False
    engine_configs["pff_config"].depth_role.efficiency.enabled = True

    coverage = collect_signal_coverage(
        engine_configs,
        [2024],
        pff_dir=pff_dir,
        cache_dir=cache_dir,
    )

    assert coverage["pff.depth_role.efficiency"].status == "disabled"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_validation/test_coverage.py -k "depth_role_efficiency" -v`

Expected: FAIL because the new coverage key does not exist yet.

- [ ] **Step 3: Add the efficiency coverage signal**

In `src/fantasy_sim/validation/coverage.py`, add a runtime-accurate required
path map using the same dependency set as the parent depth-role family:

```python
    depth_role_efficiency_enabled = (
        pff_enabled
        and depth_role_enabled
        and bool(_config_get(config, "pff_config", "depth_role", "efficiency", "enabled", default=None)
                 if _config_section(config, "pff_config") is not None
                 else _config_get(config, "pff", "depth_role", "efficiency", "enabled", default=False))
    )
```

```python
    depth_role_efficiency_paths_by_season: dict[int, list[Path]] = {
        season: [
            pff_path / f"receiving_depth_{season}.parquet",
            pff_path / f"receiving_summary_{season}.parquet",
            pff_path / f"rushing_summary_{season}.parquet",
            pff_path / f"passing_summary_{season}.parquet",
            cache_path / f"rosters_weekly_{season}.parquet",
        ]
        for season in seasons
    }
```

Return this signal from `collect_signal_coverage()`:

```python
        "pff.depth_role.efficiency": _build_signal(
            depth_role_efficiency_enabled,
            seasons,
            _covered_seasons_from_required_paths(
                seasons,
                depth_role_efficiency_paths_by_season,
            ),
            note="Requires receiving_depth, the PFF summary trio, and rosters_weekly cache to support the depth-role efficiency path",
        ),
```

- [ ] **Step 4: Run the coverage tests**

Run: `uv run pytest tests/test_validation/test_coverage.py -k "depth_role_efficiency" -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/validation/coverage.py tests/test_validation/test_coverage.py
git commit -m "feat: add depth role efficiency coverage reporting"
```

### Task 4: Run Focused Verification, Isolated Marginal Validation, And Update Docs

**Files:**
- Modify: `docs/accuracy-roadmap.md`
- Modify: `docs/accuracy-stack-audit.md`

- [ ] **Step 1: Run the focused verification suite**

Run:

```bash
uv run pytest \
  tests/test_data/test_pff/test_config.py \
  tests/test_data/test_pff/test_depth_role.py \
  tests/test_data/test_pff/test_depth_role_integration.py \
  tests/test_validation/test_config.py \
  tests/test_validation/test_coverage.py -v
```

Expected: PASS

- [ ] **Step 2: Run the isolated marginal validation arm**

Run:

```bash
uv run python scripts/validate.py \
  --baseline defaults \
  --set pff.depth_role.efficiency.enabled=true \
  --sims 50 \
  --label "phase-5-depth-role-efficiency-v2"
```

Expected:
- the run completes without schema or coverage errors
- the header prints `pff.depth_role.efficiency` coverage explicitly
- the artifact is interpretable as a clean `defaults` vs `defaults + efficiency v2` comparison

- [ ] **Step 3: Update the roadmap**

Edit `docs/accuracy-roadmap.md` so Phase 5 reflects the actual v2 result.

Add/update these points:

```md
### Status

- Phase 5A `WR/TE Depth-Role V1`: implemented, validated, not promoted
- current Phase 5 priority: `WR/TE efficiency v2`
- explicitly deferred:
  - `QB split engine`
  - `RB scheme-fit engine`

### Phase 5B Scope

- `receiving_depth` only
- `WR` and `TE` only
- pre-sim efficiency only
- `catch_rate`
- proportional `red_zone_catch_rate`
- base `receiving_yards_dist`
- no volume changes

### Validation Artifact

- label: `phase-5-depth-role-efficiency-v2`
- baseline: `defaults`
- comparison mode: `marginal_lift`
- coverage: copy the exact `pff.depth_role.efficiency` readout from the run
- result: copy the exact top-line deltas from the run
```

- [ ] **Step 4: Update the audit**

Edit `docs/accuracy-stack-audit.md` and add/update:

```md
## Phase 5 Efficiency Notes

- `pff.depth_role.efficiency` is now implemented in code
- it remains nested under the existing `pff.depth_role` family
- it uses `receiving_depth`, the PFF summary trio, and `rosters_weekly` crosswalk inputs
- it currently adjusts:
  - `catch_rate`
  - proportional `red_zone_catch_rate`
  - base `receiving_yards_dist`
- it does not adjust:
  - `target_share`
  - `air_yards_share`
  - `rz_receiving_yards_dist`
```

Also update the Phase 5 next-slice wording and defaults section to reflect the
actual v2 validation outcome:

- keep `pff.depth_role.enabled: false`
- keep `pff.depth_role.efficiency.enabled: false` in this task
- if v2 is flat or negative, record that clearly and leave the next follow-on
  as a decision point rather than auto-promoting or auto-bundling

- [ ] **Step 5: Commit the docs**

Use:

```bash
git add docs/accuracy-roadmap.md docs/accuracy-stack-audit.md
git commit -m "docs: record phase 5 efficiency status"
```

## Execution Notes

- Do not bundle Phase 5A and Phase 5B in this plan.
- Do not change `config/defaults.yaml` to enable the efficiency slice in this plan.
- If the isolated v2 result is positive enough to consider promotion, that should
  become a separate small follow-up task after the docs are updated.

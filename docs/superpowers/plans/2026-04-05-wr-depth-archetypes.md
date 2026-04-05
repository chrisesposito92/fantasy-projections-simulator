# WR Depth-of-Target Archetypes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create 3 archetype sub-pools (slot/possession/deep) within each WR tier based on ADOT, overriding `receiving_yards_dist` and `catch_rate` with archetype-specific distributions.

**Architecture:** Parallel archetype sub-pool structure alongside existing tier pools. ADOT from `receiving_summary` (already loaded) classifies WRs into archetypes. Sub-pools override only yards + catch_rate; all other scalars come from the main tier pool. Thin sub-pools fall back to the full tier pool.

**Tech Stack:** Python 3.14, polars, numpy, pytest, dataclasses, YAML config

**Spec:** `docs/superpowers/specs/2026-04-05-wr-depth-archetypes-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/fantasy_sim/data/pff/models.py` | Modify | Add `ArchetypeConfig` dataclass, add field to `TierConfig` |
| `src/fantasy_sim/data/pff/config.py` | Modify | Parse `archetypes` block from YAML into `ArchetypeConfig` |
| `src/fantasy_sim/data/pff/tier_engine.py` | Modify | Add archetype state, classification, pool building, blend override |
| `config/defaults.yaml` | Modify | Add `archetypes` config block |
| `tests/test_data/test_pff/test_tier_engine.py` | Modify | 10 new tests |
| `docs/pff-improvement-roadmap.md` | Modify | Mark item #4 complete |
| `CLAUDE.md` | Modify | Update PFF Intelligence Layer description |

---

### Task 1: Add ArchetypeConfig dataclass and config parsing

**Files:**
- Modify: `src/fantasy_sim/data/pff/models.py:116-153`
- Modify: `src/fantasy_sim/data/pff/config.py:114-137`
- Modify: `config/defaults.yaml:62-95`
- Test: `tests/test_data/test_pff/test_tier_engine.py`

- [ ] **Step 1: Write test for ArchetypeConfig defaults and YAML parsing**

Add to `tests/test_data/test_pff/test_tier_engine.py`:

```python
from fantasy_sim.data.pff.models import ArchetypeConfig


class TestArchetypeConfig:
    def test_defaults(self):
        """ArchetypeConfig has sensible defaults."""
        cfg = ArchetypeConfig()
        assert cfg.enabled is True
        assert cfg.n_archetypes == 3
        assert cfg.adot_grade_key == "avg_depth_of_target"
        assert cfg.min_archetype_pool_size == 20

    def test_tier_config_has_archetypes_field(self):
        """TierConfig includes an archetypes field with ArchetypeConfig default."""
        cfg = TierConfig()
        assert hasattr(cfg, "archetypes")
        assert isinstance(cfg.archetypes, ArchetypeConfig)
        assert cfg.archetypes.enabled is True

    def test_yaml_parsing_archetypes(self):
        """load_pff_config parses archetypes block from YAML dict."""
        config = {
            "pff": {
                "enabled": True,
                "tier_engine": {
                    "enabled": True,
                    "archetypes": {
                        "enabled": False,
                        "n_archetypes": 2,
                        "min_archetype_pool_size": 15,
                    },
                },
            },
        }
        pff_cfg = load_pff_config(config)
        assert pff_cfg.tier_engine.archetypes.enabled is False
        assert pff_cfg.tier_engine.archetypes.n_archetypes == 2
        assert pff_cfg.tier_engine.archetypes.min_archetype_pool_size == 15
        # adot_grade_key should keep default
        assert pff_cfg.tier_engine.archetypes.adot_grade_key == "avg_depth_of_target"

    def test_yaml_parsing_archetypes_defaults_when_missing(self):
        """When archetypes block is missing from YAML, defaults are used."""
        config = {
            "pff": {
                "enabled": True,
                "tier_engine": {"enabled": True},
            },
        }
        pff_cfg = load_pff_config(config)
        assert pff_cfg.tier_engine.archetypes.enabled is True
        assert pff_cfg.tier_engine.archetypes.n_archetypes == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_pff/test_tier_engine.py::TestArchetypeConfig -v`
Expected: FAIL — `ArchetypeConfig` not importable, `TierConfig` has no `archetypes` field.

- [ ] **Step 3: Add ArchetypeConfig dataclass to models.py**

In `src/fantasy_sim/data/pff/models.py`, add before `PositionGradeConfig` (before line 117):

```python
@dataclass
class ArchetypeConfig:
    """Configuration for WR depth-of-target archetypes within tiers."""
    enabled: bool = True
    n_archetypes: int = 3
    adot_grade_key: str = "avg_depth_of_target"
    min_archetype_pool_size: int = 20
```

Add `archetypes` field to `TierConfig` (after `ncaa_rookie` field, line 153):

```python
    archetypes: ArchetypeConfig = field(default_factory=ArchetypeConfig)
```

- [ ] **Step 4: Add config parsing in config.py**

In `src/fantasy_sim/data/pff/config.py`, add import of `ArchetypeConfig`:

```python
from fantasy_sim.data.pff.models import (
    ArchetypeConfig,
    MatchupConfig,
    # ... existing imports
)
```

After `tier_engine.ncaa_rookie = ncaa_rookie` (line 137), add:

```python
    arch_raw = tier_raw.get("archetypes", {})
    archetypes = ArchetypeConfig(
        enabled=arch_raw.get("enabled", True),
        n_archetypes=arch_raw.get("n_archetypes", 3),
        adot_grade_key=arch_raw.get("adot_grade_key", "avg_depth_of_target"),
        min_archetype_pool_size=arch_raw.get("min_archetype_pool_size", 20),
    )
    tier_engine.archetypes = archetypes
```

- [ ] **Step 5: Add config to defaults.yaml**

In `config/defaults.yaml`, add after `ncaa_rookie` block (after line 95):

```yaml
    archetypes:
      enabled: true
      n_archetypes: 3
      adot_grade_key: avg_depth_of_target
      min_archetype_pool_size: 20
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_pff/test_tier_engine.py::TestArchetypeConfig -v`
Expected: All 4 tests PASS.

- [ ] **Step 7: Run full test suite to verify no regressions**

Run: `uv run pytest tests/ -x -q`
Expected: All tests pass (949+).

- [ ] **Step 8: Commit**

```bash
git add src/fantasy_sim/data/pff/models.py src/fantasy_sim/data/pff/config.py \
  config/defaults.yaml tests/test_data/test_pff/test_tier_engine.py
git commit -m "feat: add ArchetypeConfig dataclass and YAML parsing for WR depth archetypes"
```

---

### Task 2: Add _classify_archetype() method with tests

**Files:**
- Modify: `src/fantasy_sim/data/pff/tier_engine.py:141-164`
- Test: `tests/test_data/test_pff/test_tier_engine.py`

- [ ] **Step 1: Write tests for _classify_archetype()**

Add to `tests/test_data/test_pff/test_tier_engine.py`:

```python
class TestClassifyArchetype:
    def _make_engine_with_boundaries(self, boundaries=(9.0, 14.0)):
        """Create a TierEngine with preset ADOT boundaries."""
        from fantasy_sim.data.pff.models import ArchetypeConfig
        engine = _make_tier_engine()
        engine._config.archetypes = ArchetypeConfig(enabled=True)
        engine._adot_boundaries = boundaries
        return engine

    def test_slot_below_p33(self):
        """ADOT below p33 boundary classifies as slot."""
        engine = self._make_engine_with_boundaries((9.0, 14.0))
        assert engine._classify_archetype({"avg_depth_of_target": 7.0}) == "slot"

    def test_possession_between_boundaries(self):
        """ADOT between p33 and p67 classifies as possession."""
        engine = self._make_engine_with_boundaries((9.0, 14.0))
        assert engine._classify_archetype({"avg_depth_of_target": 11.0}) == "possession"

    def test_deep_above_p67(self):
        """ADOT above p67 boundary classifies as deep."""
        engine = self._make_engine_with_boundaries((9.0, 14.0))
        assert engine._classify_archetype({"avg_depth_of_target": 16.0}) == "deep"

    def test_at_p33_boundary_is_possession(self):
        """ADOT exactly at p33 boundary classifies as possession (>= p33)."""
        engine = self._make_engine_with_boundaries((9.0, 14.0))
        assert engine._classify_archetype({"avg_depth_of_target": 9.0}) == "possession"

    def test_at_p67_boundary_is_possession(self):
        """ADOT exactly at p67 boundary classifies as possession (<= p67)."""
        engine = self._make_engine_with_boundaries((9.0, 14.0))
        assert engine._classify_archetype({"avg_depth_of_target": 14.0}) == "possession"

    def test_none_when_adot_missing(self):
        """Returns None when ADOT is not in the grades dict."""
        engine = self._make_engine_with_boundaries((9.0, 14.0))
        assert engine._classify_archetype({"grades_pass_route": 75.0}) is None

    def test_none_when_boundaries_not_set(self):
        """Returns None when ADOT boundaries haven't been computed."""
        engine = _make_tier_engine()
        engine._adot_boundaries = None
        assert engine._classify_archetype({"avg_depth_of_target": 10.0}) is None

    def test_none_when_archetypes_disabled(self):
        """Returns None when archetypes are disabled in config."""
        from fantasy_sim.data.pff.models import ArchetypeConfig
        engine = _make_tier_engine()
        engine._config.archetypes = ArchetypeConfig(enabled=False)
        engine._adot_boundaries = (9.0, 14.0)
        assert engine._classify_archetype({"avg_depth_of_target": 10.0}) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_pff/test_tier_engine.py::TestClassifyArchetype -v`
Expected: FAIL — `_classify_archetype` not defined, `_adot_boundaries` not on TierEngine.

- [ ] **Step 3: Add instance state and _classify_archetype() to TierEngine**

In `src/fantasy_sim/data/pff/tier_engine.py`, add new instance state in `__init__()` (after line 163):

```python
        # Archetype sub-pools: {position: {tier: {archetype_name: _TierPoolEntry}}}
        self._archetype_pools: dict[str, dict[int, dict[str, _TierPoolEntry]]] | None = None

        # Global ADOT boundaries for archetype classification
        self._adot_boundaries: tuple[float, ...] | None = None
```

Add the `_classify_archetype()` method (after `_assign_tier`, around line 698):

```python
    # ------------------------------------------------------------------
    # Archetype classification
    # ------------------------------------------------------------------

    _ARCHETYPE_NAMES_3 = ("slot", "possession", "deep")
    _ARCHETYPE_NAMES_2 = ("short", "deep")

    def _classify_archetype(self, pff_grades: dict[str, float]) -> str | None:
        """Classify a WR into a depth archetype based on ADOT.

        Uses precomputed global ADOT percentile boundaries to assign one of
        N archetype labels.  Returns ``None`` when archetypes are disabled,
        boundaries haven't been computed, or ADOT is missing from
        ``pff_grades``.

        Args:
            pff_grades: PFF grade dict (must include the configured
                ``adot_grade_key`` for classification to succeed).

        Returns:
            Archetype name string, or ``None``.
        """
        if not self._config.archetypes.enabled:
            return None
        if self._adot_boundaries is None:
            return None
        adot = pff_grades.get(self._config.archetypes.adot_grade_key)
        if adot is None:
            return None

        n = self._config.archetypes.n_archetypes
        names = self._ARCHETYPE_NAMES_3 if n == 3 else self._ARCHETYPE_NAMES_2

        # Walk boundaries: values below first boundary get names[0],
        # values above last boundary get names[-1], otherwise names[i].
        for i, boundary in enumerate(self._adot_boundaries):
            if adot < boundary:
                return names[i]
        return names[-1]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_pff/test_tier_engine.py::TestClassifyArchetype -v`
Expected: All 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/pff/tier_engine.py tests/test_data/test_pff/test_tier_engine.py
git commit -m "feat: add _classify_archetype() for WR depth-of-target classification"
```

---

### Task 3: Build archetype sub-pools in _build_tier_pools()

**Files:**
- Modify: `src/fantasy_sim/data/pff/tier_engine.py:546-651`
- Test: `tests/test_data/test_pff/test_tier_engine.py`

- [ ] **Step 1: Write tests for archetype sub-pool building**

Add to `tests/test_data/test_pff/test_tier_engine.py`:

```python
class TestArchetypePoolBuilding:
    def _make_wr_player_season(self, adot, catch_rate=0.65, yards_list=None):
        """Create a WR player-season dict with PFF grades including ADOT."""
        if yards_list is None:
            yards_list = [5, 10, 15, 20]
        return {
            "targets": 50,
            "catches": 30,
            "carries": 0,
            "yards_list": yards_list,
            "rushing_yards_list": [],
            "fumbles": 1,
            "team": "KC",
            "games": {f"game_{i}" for i in range(10)},
            "air_yards": 300.0,
            "weekly_targets": {w: 5 for w in range(1, 11)},
            "target_share": 0.20,
            "carry_share": 0.0,
            "catch_rate": catch_rate,
            "air_yards_share": 0.15,
            "fumble_rate": 0.015,
            "weekly_share_values": [0.20] * 10,
            "pff_grades": {
                "grades_pass_route": 70.0,
                "avg_depth_of_target": adot,
            },
            "pff_id": 1000 + int(adot * 10),
            "nfl_id": f"player_{int(adot * 10)}",
            "season": 2024,
        }

    def test_adot_boundaries_computed_globally(self):
        """ADOT boundaries are p33/p67 across all WR player-seasons."""
        from fantasy_sim.data.pff.tier_engine import TierEngine
        from fantasy_sim.data.pff.models import ArchetypeConfig

        engine = _make_tier_engine()
        engine._config.archetypes = ArchetypeConfig(enabled=True, n_archetypes=3)

        # 30 WR player-seasons with ADOT from 1.0 to 30.0
        player_seasons = [self._make_wr_player_season(adot=float(i)) for i in range(1, 31)]

        engine._build_archetype_pools("WR", player_seasons, {t: [] for t in range(1, 6)})

        assert engine._adot_boundaries is not None
        assert len(engine._adot_boundaries) == 2  # p33 and p67
        p33, p67 = engine._adot_boundaries
        assert 9.0 < p33 < 12.0  # ~33rd percentile of 1-30
        assert 19.0 < p67 < 22.0  # ~67th percentile of 1-30

    def test_three_sub_pools_built_per_tier(self):
        """Each tier gets up to 3 archetype sub-pool entries."""
        from fantasy_sim.data.pff.tier_engine import TierEngine
        from fantasy_sim.data.pff.models import ArchetypeConfig

        engine = _make_tier_engine()
        engine._config.archetypes = ArchetypeConfig(
            enabled=True, n_archetypes=3, min_archetype_pool_size=3,
        )

        # 30 players spread across a single tier bucket
        player_seasons = [self._make_wr_player_season(adot=float(i)) for i in range(1, 31)]
        tier_buckets = {3: player_seasons}

        engine._build_archetype_pools("WR", player_seasons, tier_buckets)

        assert engine._archetype_pools is not None
        assert "WR" in engine._archetype_pools
        assert 3 in engine._archetype_pools["WR"]
        tier3_archetypes = engine._archetype_pools["WR"][3]
        assert "slot" in tier3_archetypes
        assert "possession" in tier3_archetypes
        assert "deep" in tier3_archetypes

    def test_sub_pool_has_archetype_specific_yards(self):
        """Deep archetype sub-pool has different yards than slot."""
        from fantasy_sim.data.pff.models import ArchetypeConfig

        engine = _make_tier_engine()
        engine._config.archetypes = ArchetypeConfig(
            enabled=True, n_archetypes=3, min_archetype_pool_size=3,
        )

        # Slot players: short yards. Deep players: long yards.
        slot_players = [
            self._make_wr_player_season(adot=5.0, yards_list=[3, 5, 7, 8]) for _ in range(10)
        ]
        poss_players = [
            self._make_wr_player_season(adot=11.0, yards_list=[8, 12, 15, 18]) for _ in range(10)
        ]
        deep_players = [
            self._make_wr_player_season(adot=18.0, yards_list=[15, 25, 35, 45]) for _ in range(10)
        ]
        all_players = slot_players + poss_players + deep_players
        tier_buckets = {3: all_players}

        engine._build_archetype_pools("WR", all_players, tier_buckets)

        pools = engine._archetype_pools["WR"][3]
        assert np.mean(pools["deep"].receiving_yards_dist) > np.mean(pools["slot"].receiving_yards_dist)

    def test_thin_sub_pool_not_stored(self):
        """Sub-pool with fewer than min_archetype_pool_size members is not stored."""
        from fantasy_sim.data.pff.models import ArchetypeConfig

        engine = _make_tier_engine()
        engine._config.archetypes = ArchetypeConfig(
            enabled=True, n_archetypes=3, min_archetype_pool_size=20,
        )

        # Only 5 slot players, 5 possession, 5 deep — all below threshold
        players = (
            [self._make_wr_player_season(adot=5.0) for _ in range(5)]
            + [self._make_wr_player_season(adot=11.0) for _ in range(5)]
            + [self._make_wr_player_season(adot=18.0) for _ in range(5)]
        )
        tier_buckets = {3: players}

        engine._build_archetype_pools("WR", players, tier_buckets)

        # All sub-pools should be missing (below threshold)
        assert engine._archetype_pools is not None
        # Tier 3 should either be empty or not have any sub-pools
        tier3 = engine._archetype_pools.get("WR", {}).get(3, {})
        assert len(tier3) == 0

    def test_missing_adot_excluded_from_sub_pools(self):
        """Players without ADOT are excluded from archetype sub-pools."""
        from fantasy_sim.data.pff.models import ArchetypeConfig

        engine = _make_tier_engine()
        engine._config.archetypes = ArchetypeConfig(
            enabled=True, n_archetypes=3, min_archetype_pool_size=3,
        )

        # 10 players with ADOT, 5 without
        with_adot = [self._make_wr_player_season(adot=10.0) for _ in range(10)]
        without_adot = []
        for _ in range(5):
            ps = self._make_wr_player_season(adot=10.0)
            del ps["pff_grades"]["avg_depth_of_target"]
            without_adot.append(ps)

        all_players = with_adot + without_adot
        tier_buckets = {3: all_players}

        engine._build_archetype_pools("WR", all_players, tier_buckets)

        # Boundaries should be computed from only the 10 players with ADOT
        assert engine._adot_boundaries is not None

    def test_disabled_config_skips_building(self):
        """When archetypes.enabled is False, no archetype pools are built."""
        from fantasy_sim.data.pff.models import ArchetypeConfig

        engine = _make_tier_engine()
        engine._config.archetypes = ArchetypeConfig(enabled=False)

        players = [self._make_wr_player_season(adot=10.0) for _ in range(30)]
        tier_buckets = {3: players}

        engine._build_archetype_pools("WR", players, tier_buckets)

        assert engine._archetype_pools is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_pff/test_tier_engine.py::TestArchetypePoolBuilding -v`
Expected: FAIL — `_build_archetype_pools` not defined.

- [ ] **Step 3: Implement _build_archetype_pools()**

In `src/fantasy_sim/data/pff/tier_engine.py`, add after `_classify_archetype()`:

```python
    # ------------------------------------------------------------------
    # Archetype sub-pool building
    # ------------------------------------------------------------------

    def _build_archetype_pools(
        self,
        position: str,
        player_seasons: list[dict],
        tier_buckets: dict[int, list],
    ) -> None:
        """Build archetype sub-pools for WR depth-of-target classification.

        Computes global ADOT percentile boundaries from all WR player-seasons,
        classifies each player-season into an archetype, and builds per-
        (tier, archetype) pool entries for yards and catch_rate.

        Only builds pools when ``archetypes.enabled`` is ``True`` and the
        position is ``"WR"``.  Sub-pools with fewer than
        ``min_archetype_pool_size`` members are discarded (blend-time falls
        back to the main tier pool).

        Args:
            position: Position key (only ``"WR"`` is processed).
            player_seasons: All WR player-season dicts (across tiers).
            tier_buckets: Tier assignment dict (after thin-tier merging).
        """
        cfg = self._config.archetypes
        if not cfg.enabled or position != "WR":
            return

        # Collect ADOT values from all WR player-seasons
        adot_key = cfg.adot_grade_key
        adot_values = [
            ps["pff_grades"][adot_key]
            for ps in player_seasons
            if ps.get("pff_grades") and adot_key in ps["pff_grades"]
        ]

        if len(adot_values) < cfg.n_archetypes:
            logger.warning(
                "Too few WR player-seasons with ADOT (%d) for %d archetypes",
                len(adot_values), cfg.n_archetypes,
            )
            return

        # Compute N-1 evenly-spaced percentile boundaries
        adot_arr = np.array(adot_values, dtype=np.float64)
        n = cfg.n_archetypes
        percentiles = [100.0 * (i + 1) / n for i in range(n - 1)]
        self._adot_boundaries = tuple(
            float(np.percentile(adot_arr, p)) for p in percentiles
        )

        logger.info(
            "ADOT boundaries for %d archetypes: %s",
            n, self._adot_boundaries,
        )

        # Build archetype sub-pools per tier
        if self._archetype_pools is None:
            self._archetype_pools = {}

        secondary_key = self._config.position_grades["WR"].secondary
        position_archetype_pools: dict[int, dict[str, _TierPoolEntry]] = {}

        for tier, members in tier_buckets.items():
            # Classify each member by archetype
            archetype_buckets: dict[str, list] = {}
            for ps in members:
                archetype = self._classify_archetype(ps.get("pff_grades", {}))
                if archetype is None:
                    continue
                archetype_buckets.setdefault(archetype, []).append(ps)

            # Build sub-pool entries for archetypes with enough members
            tier_archetypes: dict[str, _TierPoolEntry] = {}
            for arch_name, arch_members in archetype_buckets.items():
                if len(arch_members) >= cfg.min_archetype_pool_size:
                    tier_archetypes[arch_name] = self._build_pool_entry(
                        arch_members, secondary_key,
                    )
                    logger.info(
                        "Built WR archetype sub-pool: tier=%d, archetype=%s, n=%d",
                        tier, arch_name, len(arch_members),
                    )

            if tier_archetypes:
                position_archetype_pools[tier] = tier_archetypes

        if position_archetype_pools:
            self._archetype_pools["WR"] = position_archetype_pools
```

- [ ] **Step 4: Wire _build_archetype_pools into _build_tier_pools()**

In `_build_tier_pools()`, after the main pool is built for a position (after line 648, before `self._pools = pools`), add:

```python
            # Build archetype sub-pools for WR
            if position == "WR":
                self._build_archetype_pools(position, player_seasons, tier_buckets)
```

Also reset archetype state at the top of `_build_tier_pools()` (after line 566):

```python
        self._archetype_pools = None
        self._adot_boundaries = None
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_pff/test_tier_engine.py::TestArchetypePoolBuilding -v`
Expected: All 7 tests PASS.

- [ ] **Step 6: Run full test suite**

Run: `uv run pytest tests/ -x -q`
Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/fantasy_sim/data/pff/tier_engine.py tests/test_data/test_pff/test_tier_engine.py
git commit -m "feat: build WR archetype sub-pools by ADOT within tier pools"
```

---

### Task 4: Blend-time archetype override in apply_tiers()

**Files:**
- Modify: `src/fantasy_sim/data/pff/tier_engine.py:1228-1260`
- Test: `tests/test_data/test_pff/test_tier_engine.py`

- [ ] **Step 1: Write tests for blend-time override**

Add to `tests/test_data/test_pff/test_tier_engine.py`:

```python
class TestArchetypeBlendOverride:
    def test_wr_uses_archetype_yards_dist(self):
        """WR blend uses archetype sub-pool receiving_yards_dist."""
        from fantasy_sim.data.pff.tier_engine import TierEngine, TierDistributions
        from fantasy_sim.data.pff.models import ArchetypeConfig
        from fantasy_sim.models.player import PlayerModel, PlayerUsage, PlayerOutcomes

        engine = _make_tier_engine()
        engine._config.archetypes = ArchetypeConfig(enabled=True)
        engine._adot_boundaries = (9.0, 14.0)

        # Set up main tier pool and archetype sub-pool
        main_pool = _make_pool_entry(
            receiving_yards_dist=np.array([10, 12, 14, 16, 18]),
            catch_rate=(0.60, 0.65, 0.70),
        )
        deep_pool = _make_pool_entry(
            receiving_yards_dist=np.array([20, 25, 30, 35, 40]),
            catch_rate=(0.45, 0.50, 0.55),
        )

        engine._pools = {"WR": {3: main_pool}}
        engine._boundaries = {"WR": [85.0, 70.0, 55.0, 40.0]}
        engine._archetype_pools = {"WR": {3: {"deep": deep_pool}}}

        # Create a deep-threat WR player
        player = PlayerModel(
            player_id="deep_wr_1",
            name="Test Deep WR",
            position="WR",
            team="KC",
            usage=PlayerUsage(target_share=0.20, carry_share=0.0, air_yards_share=0.15),
            outcomes=PlayerOutcomes(
                catch_rate=0.62,
                receiving_yards_dist=np.array([10, 15, 20]),
                fumble_rate=0.015,
            ),
            games_played=16,
        )

        pff_grades = {"grades_pass_route": 65.0, "avg_depth_of_target": 16.0}
        result = engine.select_distributions(pff_grades, "WR")
        assert result is not None
        assignment, tier_dists = result

        # Apply archetype override
        archetype = engine._classify_archetype(pff_grades)
        assert archetype == "deep"
        arch_pool = engine._archetype_pools["WR"][assignment.tier].get(archetype)
        assert arch_pool is not None
        tier_dists.receiving_yards_dist = arch_pool.receiving_yards_dist
        tier_dists.catch_rate = engine._interp_scalar(arch_pool.catch_rate, 0.5)

        # Verify overridden values come from deep sub-pool
        assert np.array_equal(tier_dists.receiving_yards_dist, deep_pool.receiving_yards_dist)
        assert tier_dists.catch_rate == 0.50  # median of deep pool catch_rate

    def test_wr_without_archetype_uses_main_pool(self):
        """WR without ADOT in grades falls back to main tier pool."""
        from fantasy_sim.data.pff.models import ArchetypeConfig

        engine = _make_tier_engine()
        engine._config.archetypes = ArchetypeConfig(enabled=True)
        engine._adot_boundaries = (9.0, 14.0)

        main_pool = _make_pool_entry(
            receiving_yards_dist=np.array([10, 12, 14, 16, 18]),
        )
        engine._pools = {"WR": {3: main_pool}}
        engine._boundaries = {"WR": [85.0, 70.0, 55.0, 40.0]}
        engine._archetype_pools = {"WR": {3: {"deep": _make_pool_entry()}}}

        pff_grades = {"grades_pass_route": 65.0}  # no ADOT
        result = engine.select_distributions(pff_grades, "WR")
        assert result is not None
        _, tier_dists = result

        archetype = engine._classify_archetype(pff_grades)
        assert archetype is None
        # tier_dists should have main pool values (unchanged)
        assert np.array_equal(tier_dists.receiving_yards_dist, main_pool.receiving_yards_dist)

    def test_rb_unaffected_by_archetypes(self):
        """RB blending is completely unaffected by archetype logic."""
        from fantasy_sim.data.pff.models import ArchetypeConfig

        engine = _make_tier_engine()
        engine._config.archetypes = ArchetypeConfig(enabled=True)
        engine._adot_boundaries = (9.0, 14.0)

        rb_pool = _make_pool_entry(
            rushing_yards_dist=np.array([2, 4, 6, 8]),
            carry_share=(0.10, 0.15, 0.20),
        )
        engine._pools = {"RB": {3: rb_pool}}
        engine._boundaries = {"RB": [85.0, 70.0, 55.0, 40.0]}
        engine._archetype_pools = {}

        pff_grades = {"grades_run": 65.0}
        result = engine.select_distributions(pff_grades, "RB")
        assert result is not None
        _, tier_dists = result

        # RB should never go through archetype classification
        archetype = engine._classify_archetype(pff_grades)
        assert archetype is None  # no ADOT key in grades
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_pff/test_tier_engine.py::TestArchetypeBlendOverride -v`
Expected: FAIL — missing import `ArchetypeConfig` in second/third test (add import at top of class or test).

- [ ] **Step 3: Add archetype override in apply_tiers()**

In `src/fantasy_sim/data/pff/tier_engine.py`, in `apply_tiers()`, after line 1237 (`self.apply_team_context(tier_dists, team_context, position)`) and before the weekly shares gathering (line 1239), add:

```python
            # Apply archetype sub-pool override for WR
            if position == "WR" and self._archetype_pools:
                archetype = self._classify_archetype(pff_grades)
                if archetype:
                    arch_pool = (
                        self._archetype_pools
                        .get("WR", {}).get(assignment.tier, {}).get(archetype)
                    )
                    if arch_pool:
                        tier_dists.receiving_yards_dist = arch_pool.receiving_yards_dist
                        tier_dists.catch_rate = self._interp_scalar(
                            arch_pool.catch_rate, 0.5,
                        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_pff/test_tier_engine.py::TestArchetypeBlendOverride -v`
Expected: All 3 tests PASS.

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest tests/ -x -q`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/fantasy_sim/data/pff/tier_engine.py tests/test_data/test_pff/test_tier_engine.py
git commit -m "feat: apply WR archetype sub-pool override at blend time in apply_tiers()"
```

---

### Task 5: NCAA rookie archetype override in _apply_rookie_tiers()

**Files:**
- Modify: `src/fantasy_sim/data/pff/tier_engine.py:1114-1139`
- Test: `tests/test_data/test_pff/test_tier_engine.py`

- [ ] **Step 1: Write tests for NCAA archetype override**

Add to `tests/test_data/test_pff/test_tier_engine.py`:

```python
class TestNcaaArchetypeOverride:
    def test_rookie_with_ncaa_adot_gets_archetype_sub_pool(self):
        """Rookie WR with NCAA ADOT gets archetype-specific distributions."""
        from fantasy_sim.data.pff.models import ArchetypeConfig

        engine = _make_tier_engine()
        engine._config.archetypes = ArchetypeConfig(enabled=True)
        engine._adot_boundaries = (9.0, 14.0)

        deep_pool = _make_pool_entry(
            receiving_yards_dist=np.array([20, 25, 30, 35, 40]),
            catch_rate=(0.45, 0.50, 0.55),
        )
        engine._archetype_pools = {"WR": {2: {"deep": deep_pool}}}

        # NCAA grades with high ADOT → deep archetype
        ncaa_grades = {"grades_pass_route": 75.0, "avg_depth_of_target": 17.0}

        archetype = engine._classify_archetype(ncaa_grades)
        assert archetype == "deep"

        arch_pool = engine._archetype_pools["WR"][2].get(archetype)
        assert arch_pool is not None
        assert np.array_equal(arch_pool.receiving_yards_dist, deep_pool.receiving_yards_dist)

    def test_rookie_without_ncaa_adot_uses_full_pool(self):
        """Rookie WR without NCAA ADOT falls back to full tier pool."""
        from fantasy_sim.data.pff.models import ArchetypeConfig

        engine = _make_tier_engine()
        engine._config.archetypes = ArchetypeConfig(enabled=True)
        engine._adot_boundaries = (9.0, 14.0)
        engine._archetype_pools = {"WR": {2: {"deep": _make_pool_entry()}}}

        # NCAA grades without ADOT
        ncaa_grades = {"grades_pass_route": 75.0}

        archetype = engine._classify_archetype(ncaa_grades)
        assert archetype is None
```

- [ ] **Step 2: Run tests to verify they pass** (these test classification logic already implemented)

Run: `uv run pytest tests/test_data/test_pff/test_tier_engine.py::TestNcaaArchetypeOverride -v`
Expected: PASS — these tests verify classification behavior that already works from Task 2.

- [ ] **Step 3: Add archetype override in _apply_rookie_tiers()**

In `src/fantasy_sim/data/pff/tier_engine.py`, in `_apply_rookie_tiers()`, after line 1118 (`self.apply_team_context(tier_dists, team_context, position)`) and before the draft confidence calculation (line 1120), add:

```python
            # Apply archetype sub-pool override for WR rookies
            if position == "WR" and self._archetype_pools:
                archetype = self._classify_archetype(ncaa_grades)
                if archetype:
                    arch_pool = (
                        self._archetype_pools
                        .get("WR", {}).get(assignment.tier, {}).get(archetype)
                    )
                    if arch_pool:
                        tier_dists.receiving_yards_dist = arch_pool.receiving_yards_dist
                        tier_dists.catch_rate = self._interp_scalar(
                            arch_pool.catch_rate, 0.5,
                        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_pff/test_tier_engine.py::TestNcaaArchetypeOverride -v`
Expected: All 2 tests PASS.

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest tests/ -x -q`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/fantasy_sim/data/pff/tier_engine.py tests/test_data/test_pff/test_tier_engine.py
git commit -m "feat: apply WR archetype override in NCAA rookie tier assignment"
```

---

### Task 6: Config disabled and non-WR passthrough tests

**Files:**
- Test: `tests/test_data/test_pff/test_tier_engine.py`

- [ ] **Step 1: Write config disabled integration test**

Add to `tests/test_data/test_pff/test_tier_engine.py`:

```python
class TestArchetypeConfigDisabled:
    def test_disabled_produces_no_archetype_pools(self):
        """With archetypes.enabled=False, _archetype_pools stays None."""
        from fantasy_sim.data.pff.models import ArchetypeConfig

        engine = _make_tier_engine()
        engine._config.archetypes = ArchetypeConfig(enabled=False)

        players = [
            TestArchetypePoolBuilding()._make_wr_player_season(adot=float(i))
            for i in range(1, 31)
        ]
        tier_buckets = {3: players}

        engine._build_archetype_pools("WR", players, tier_buckets)

        assert engine._archetype_pools is None
        assert engine._adot_boundaries is None

    def test_disabled_classify_returns_none(self):
        """_classify_archetype returns None when disabled, even with valid ADOT."""
        from fantasy_sim.data.pff.models import ArchetypeConfig

        engine = _make_tier_engine()
        engine._config.archetypes = ArchetypeConfig(enabled=False)
        engine._adot_boundaries = (9.0, 14.0)

        result = engine._classify_archetype({"avg_depth_of_target": 10.0})
        assert result is None

    def test_non_wr_position_skips_archetype_building(self):
        """_build_archetype_pools is a no-op for non-WR positions."""
        from fantasy_sim.data.pff.models import ArchetypeConfig

        engine = _make_tier_engine()
        engine._config.archetypes = ArchetypeConfig(enabled=True)

        # Try building for RB — should be skipped
        players = [
            TestArchetypePoolBuilding()._make_wr_player_season(adot=10.0)
            for _ in range(30)
        ]
        engine._build_archetype_pools("RB", players, {3: players})

        assert engine._archetype_pools is None
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/test_data/test_pff/test_tier_engine.py::TestArchetypeConfigDisabled -v`
Expected: All 3 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_data/test_pff/test_tier_engine.py
git commit -m "test: add config disabled and non-WR passthrough tests for archetypes"
```

---

### Task 7: Statistical validation tests

**Files:**
- Test: `tests/test_data/test_pff/test_tier_engine.py`

- [ ] **Step 1: Write statistical tests**

Add to `tests/test_data/test_pff/test_tier_engine.py`:

```python
@pytest.mark.statistical
class TestArchetypeStatisticalValidation:
    def _build_archetype_pools_with_realistic_data(self):
        """Build archetype sub-pools with realistic slot/deep separation."""
        from fantasy_sim.data.pff.models import ArchetypeConfig

        engine = _make_tier_engine()
        engine._config.archetypes = ArchetypeConfig(
            enabled=True, n_archetypes=3, min_archetype_pool_size=5,
        )

        rng = np.random.default_rng(42)

        def make_player(adot, yards_mean, catch_rate):
            ps = TestArchetypePoolBuilding()._make_wr_player_season(
                adot=adot,
                catch_rate=catch_rate,
                yards_list=rng.normal(yards_mean, 3.0, size=50).tolist(),
            )
            return ps

        # Slot: low ADOT, short yards, high catch rate
        slot_players = [make_player(adot=rng.uniform(4, 8), yards_mean=7.0, catch_rate=rng.uniform(0.65, 0.75)) for _ in range(20)]
        # Possession: mid ADOT, mid yards, mid catch rate
        poss_players = [make_player(adot=rng.uniform(9, 13), yards_mean=12.0, catch_rate=rng.uniform(0.58, 0.68)) for _ in range(20)]
        # Deep: high ADOT, long yards, low catch rate
        deep_players = [make_player(adot=rng.uniform(15, 22), yards_mean=20.0, catch_rate=rng.uniform(0.48, 0.58)) for _ in range(20)]

        all_players = slot_players + poss_players + deep_players
        tier_buckets = {3: all_players}

        engine._build_archetype_pools("WR", all_players, tier_buckets)
        return engine

    def test_deep_archetype_has_higher_mean_yards_than_slot(self):
        """Deep-threat sub-pool has higher mean receiving_yards_dist than slot."""
        engine = self._build_archetype_pools_with_realistic_data()

        pools = engine._archetype_pools["WR"][3]
        slot_mean = np.mean(pools["slot"].receiving_yards_dist)
        deep_mean = np.mean(pools["deep"].receiving_yards_dist)

        assert deep_mean > slot_mean, (
            f"Deep mean yards ({deep_mean:.1f}) should exceed slot ({slot_mean:.1f})"
        )

    def test_slot_archetype_has_higher_catch_rate_than_deep(self):
        """Slot sub-pool has higher median catch_rate than deep sub-pool."""
        engine = self._build_archetype_pools_with_realistic_data()

        pools = engine._archetype_pools["WR"][3]
        # catch_rate is stored as (p25, median, p75) tuple
        slot_median = pools["slot"].catch_rate[1]
        deep_median = pools["deep"].catch_rate[1]

        assert slot_median > deep_median, (
            f"Slot catch rate ({slot_median:.3f}) should exceed deep ({deep_median:.3f})"
        )
```

- [ ] **Step 2: Run statistical tests**

Run: `uv run pytest tests/test_data/test_pff/test_tier_engine.py::TestArchetypeStatisticalValidation -v -m statistical`
Expected: All 2 tests PASS.

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest tests/ -x -q`
Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add tests/test_data/test_pff/test_tier_engine.py
git commit -m "test: add statistical validation tests for WR archetype separation"
```

---

### Task 8: Documentation updates

**Files:**
- Modify: `docs/pff-improvement-roadmap.md:139-148`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update roadmap item #4**

In `docs/pff-improvement-roadmap.md`, replace the item #4 section (lines 139-148) with:

```markdown
### 4. ~~Depth-of-Target Archetypes Within Tiers~~ — COMPLETE

**Result:** 3 archetype sub-pools (slot/possession/deep) within each WR tier, classified by ADOT from `receiving_summary`. Overrides `receiving_yards_dist` and `catch_rate` from archetype sub-pool when available (>= 20 members); falls back to full tier pool otherwise. Global ADOT percentile boundaries (p33/p67) computed across all WR player-seasons. NCAA rookies also get archetype assignment via NCAA ADOT. Deep-threat sub-pools have higher mean yards and lower catch rates than slot sub-pools within the same tier, matching NFL reality.

Config in `defaults.yaml` under `pff.tier_engine.archetypes`. A/B override: `--config-override '{"tier_engine": {"archetypes": {"enabled": false}}}'`.
```

- [ ] **Step 2: Update CLAUDE.md PFF Intelligence Layer section**

In `CLAUDE.md`, update the PFF Intelligence Layer bullet to include archetype information. Add after the TierEngine description:

```
WR archetype sub-pooling: 3 depth archetypes (slot/possession/deep) within each WR tier based on ADOT from `receiving_summary`. Overrides `receiving_yards_dist` and `catch_rate` per archetype. Falls back to full tier pool when sub-pool < `min_archetype_pool_size` (20). NCAA rookies get archetype assignment via NCAA ADOT. Config in `defaults.yaml` under `pff.tier_engine.archetypes`.
```

Also update the Current State section to reflect the new test count and feature.

- [ ] **Step 3: Commit**

```bash
git add docs/pff-improvement-roadmap.md CLAUDE.md
git commit -m "docs: mark depth-of-target archetypes complete, update CLAUDE.md"
```

---

## Summary

| Task | Description | Tests Added |
|------|-------------|-------------|
| 1 | ArchetypeConfig + config parsing + YAML | 4 |
| 2 | _classify_archetype() method | 8 |
| 3 | Archetype sub-pool building | 7 |
| 4 | Blend-time override in apply_tiers() | 3 |
| 5 | NCAA rookie archetype override | 2 |
| 6 | Config disabled + non-WR passthrough | 3 |
| 7 | Statistical validation | 2 |
| 8 | Documentation | 0 |
| **Total** | | **29** |

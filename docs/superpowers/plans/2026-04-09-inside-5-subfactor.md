# Inside-5 Goal-Line Sub-Factor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-player inside-5 rushing TD factor that replaces the general rushing_td_factor for gate bands (1,3) and (4,5) when sufficient goal-line data exists.

**Architecture:** Extends TdTendencyEngine with a third factor dimension (`i5_rushing_td_factor`) using the same Bayesian blend pattern. PFF `i5_rush_carries`/`i5_rush_tds` columns (already scraped) are consumed as primary data, with PBP fallback via `yardline_100 <= 5`. Gate logic in `_resolve_run()` selects the more granular factor when available.

**Tech Stack:** Python 3.12+, polars, numpy, pytest

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `src/fantasy_sim/data/td_tendency.py` | Modify | Add i5 priors, extend `_load_pff_rates()` and `_rates_from_pbp()` to 3-tuple, compute i5 factor in `apply()` |
| `src/fantasy_sim/models/player.py` | Modify | Add `i5_rushing_td_factor` field to `PlayerOutcomes` |
| `src/fantasy_sim/data/player_builder.py` | Modify | Add `i5_rush_carries`/`i5_rush_tds` counters to `_aggregate_pbp_stats()` |
| `src/fantasy_sim/engine/play_resolver.py` | Modify | Select i5 factor for yard_line <= 5 in `_resolve_run()` |
| `config/defaults.yaml` | Modify | Add `i5_enabled`, `i5_prior_strength`, `i5_min_opportunities` under `td_tendency:` |
| `tests/test_data/test_td_tendency_config.py` | Modify | Test i5 config fields |
| `tests/test_data/test_td_tendency_engine.py` | Modify | Test i5 Bayesian blend and apply |
| `tests/test_data/test_td_tendency_pbp.py` | Modify | Test PBP inside-5 counting |
| `tests/test_engine/test_td_tendency_gate.py` | Modify | Test i5 factor selection at yard_line <= 5 |
| `tests/test_validation/test_td_tendency_config_resolution.py` | Modify | Test i5 config flows through validation |

---

### Task 1: Config & Model — Add i5 fields

**Files:**
- Modify: `src/fantasy_sim/data/td_tendency.py:24-48`
- Modify: `src/fantasy_sim/models/player.py:24-36`
- Modify: `config/defaults.yaml:241-245`
- Test: `tests/test_data/test_td_tendency_config.py`

- [ ] **Step 1: Write failing tests for i5 config fields**

Add to `tests/test_data/test_td_tendency_config.py`:

```python
def test_default_config_i5_fields(self):
    config = TdTendencyConfig()
    assert config.i5_enabled is False
    assert config.i5_prior_strength == 25.0
    assert config.i5_min_opportunities == 3

def test_load_i5_fields_from_dict(self):
    raw = {
        "td_tendency": {
            "enabled": True,
            "i5_enabled": True,
            "i5_prior_strength": 30.0,
            "i5_min_opportunities": 4,
        }
    }
    config = load_td_tendency_config(raw)
    assert config.i5_enabled is True
    assert config.i5_prior_strength == 30.0
    assert config.i5_min_opportunities == 4

def test_load_partial_i5_uses_defaults(self):
    raw = {"td_tendency": {"enabled": True, "i5_enabled": True}}
    config = load_td_tendency_config(raw)
    assert config.i5_prior_strength == 25.0
    assert config.i5_min_opportunities == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_td_tendency_config.py -v`
Expected: FAIL — `TdTendencyConfig` has no `i5_enabled` attribute

- [ ] **Step 3: Add i5 fields to TdTendencyConfig**

In `src/fantasy_sim/data/td_tendency.py`, modify the `TdTendencyConfig` dataclass (line 24-31):

```python
@dataclass
class TdTendencyConfig:
    """Configuration for TD tendency engine."""

    enabled: bool = False
    prior_strength: float = 15.0
    min_opportunities: int = 5
    factor_clamp: tuple[float, float] = (0.70, 1.30)
    i5_enabled: bool = False
    i5_prior_strength: float = 25.0
    i5_min_opportunities: int = 3
```

Update `load_td_tendency_config()` (line 34-48) to parse the new fields:

```python
def load_td_tendency_config(defaults: dict) -> TdTendencyConfig:
    """Extract TdTendencyConfig from the full defaults config dict."""
    td = defaults.get("td_tendency")
    if not td:
        return TdTendencyConfig(enabled=False)
    return TdTendencyConfig(
        enabled=td.get("enabled", False),
        prior_strength=td.get("prior_strength", 15.0),
        min_opportunities=td.get("min_opportunities", 5),
        factor_clamp=tuple(td.get("factor_clamp", [0.70, 1.30])),
        i5_enabled=td.get("i5_enabled", False),
        i5_prior_strength=td.get("i5_prior_strength", 25.0),
        i5_min_opportunities=td.get("i5_min_opportunities", 3),
    )
```

- [ ] **Step 4: Add i5_rushing_td_factor to PlayerOutcomes**

In `src/fantasy_sim/models/player.py`, add one field to `PlayerOutcomes` (after line 36):

```python
@dataclass
class PlayerOutcomes:
    """What happens when a player is involved in a play."""
    catch_rate: float = 0.0
    red_zone_catch_rate: float = 0.0
    receiving_yards_dist: np.ndarray | None = None
    rz_receiving_yards_dist: np.ndarray | None = None
    rushing_yards_dist: np.ndarray | None = None
    scramble_yards_dist: np.ndarray | None = None
    fumble_rate: float = 0.0
    pass_fumble_rate: float = 0.0
    targets_per_route_rate: float = 0.0
    receiving_td_factor: float = 1.0
    rushing_td_factor: float = 1.0
    i5_rushing_td_factor: float = 1.0   # inside-5 goal-line rushing
```

- [ ] **Step 5: Add i5 config to defaults.yaml**

In `config/defaults.yaml`, extend the `td_tendency:` section (after line 245):

```yaml
td_tendency:
  enabled: true
  prior_strength: 20
  min_opportunities: 5
  factor_clamp: [0.65, 1.35]
  i5_enabled: false             # flip after A/B validation
  i5_prior_strength: 25
  i5_min_opportunities: 3
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_td_tendency_config.py -v`
Expected: All PASS

- [ ] **Step 7: Run full test suite for regression**

Run: `uv run pytest tests/ -x -q`
Expected: All existing tests pass (default `i5_rushing_td_factor=1.0` is inert)

- [ ] **Step 8: Commit**

```bash
git add src/fantasy_sim/data/td_tendency.py src/fantasy_sim/models/player.py config/defaults.yaml tests/test_data/test_td_tendency_config.py
git commit -m "feat: add i5 config fields and i5_rushing_td_factor to PlayerOutcomes"
```

---

### Task 2: PFF Data Loading — Extend _load_pff_rates() to 3-tuple

**Files:**
- Modify: `src/fantasy_sim/data/td_tendency.py:130-193`
- Test: `tests/test_data/test_td_tendency_engine.py`

- [ ] **Step 1: Write failing test for i5 PFF data loading**

Add to `tests/test_data/test_td_tendency_engine.py`:

```python
class TestTdTendencyI5PffLoading:

    def test_load_pff_rates_returns_i5_rush_rates(self):
        """_load_pff_rates returns 3-tuple with i5_rush_rates."""
        import polars as pl
        from unittest.mock import MagicMock

        # Build mock PFF data with i5 columns
        rec_df = pl.DataFrame({
            "player_id": [100, 100, 200],
            "week": [1, 2, 1],
            "rz_rec_targ": [3, 2, 1],
            "rz_rec_tds": [1, 1, 0],
            "rz_rush_carries": [2, 1, 0],
            "rz_rush_tds": [1, 0, 0],
            "i5_rush_carries": [1, 1, 0],
            "i5_rush_tds": [1, 0, 0],
        })

        loader = MagicMock()
        loader.load_facet.side_effect = lambda facet, seasons: (
            rec_df if facet == "fantasy_receiving" else pl.DataFrame()
        )

        config = TdTendencyConfig(enabled=True, i5_enabled=True)
        engine = TdTendencyEngine(config, pff_loader=loader)
        crosswalk = {100: "gsis_rb1", 200: "gsis_wr1"}

        rec_rates, rush_rates, i5_rush_rates = engine._load_pff_rates(2024, 10, crosswalk)

        assert "gsis_rb1" in i5_rush_rates
        assert i5_rush_rates["gsis_rb1"] == (1, 2)  # 1 TD from 2 i5 carries
        assert "gsis_wr1" not in i5_rush_rates  # 0 i5 carries

    def test_load_pff_rates_i5_disabled_returns_empty(self):
        """When i5_enabled=False, i5_rush_rates is empty."""
        import polars as pl
        from unittest.mock import MagicMock

        rec_df = pl.DataFrame({
            "player_id": [100],
            "week": [1],
            "rz_rec_targ": [3],
            "rz_rec_tds": [1],
            "rz_rush_carries": [2],
            "rz_rush_tds": [1],
            "i5_rush_carries": [2],
            "i5_rush_tds": [1],
        })

        loader = MagicMock()
        loader.load_facet.side_effect = lambda facet, seasons: (
            rec_df if facet == "fantasy_receiving" else pl.DataFrame()
        )

        config = TdTendencyConfig(enabled=True, i5_enabled=False)
        engine = TdTendencyEngine(config, pff_loader=loader)
        crosswalk = {100: "gsis_rb1"}

        rec_rates, rush_rates, i5_rush_rates = engine._load_pff_rates(2024, 10, crosswalk)

        assert i5_rush_rates == {}

    def test_load_pff_rates_qb_i5_from_passing(self):
        """QB inside-5 data comes from fantasy_passing facet."""
        import polars as pl
        from unittest.mock import MagicMock

        pass_df = pl.DataFrame({
            "player_id": [300],
            "week": [1],
            "rz_rush_carries": [3],
            "rz_rush_tds": [1],
            "i5_rush_carries": [2],
            "i5_rush_tds": [1],
        })

        loader = MagicMock()
        loader.load_facet.side_effect = lambda facet, seasons: (
            pass_df if facet == "fantasy_passing" else pl.DataFrame()
        )

        config = TdTendencyConfig(enabled=True, i5_enabled=True)
        engine = TdTendencyEngine(config, pff_loader=loader)
        crosswalk = {300: "gsis_qb1"}

        rec_rates, rush_rates, i5_rush_rates = engine._load_pff_rates(2024, 10, crosswalk)

        assert "gsis_qb1" in i5_rush_rates
        assert i5_rush_rates["gsis_qb1"] == (1, 2)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_td_tendency_engine.py::TestTdTendencyI5PffLoading -v`
Expected: FAIL — `_load_pff_rates` returns 2-tuple, not 3-tuple

- [ ] **Step 3: Extend _load_pff_rates() to return i5_rush_rates**

In `src/fantasy_sim/data/td_tendency.py`, modify `_load_pff_rates()` (line 130-193):

```python
def _load_pff_rates(self, season: int, week: int,
                    pff_crosswalk: dict[int, str] | None,
                    ) -> tuple[dict[str, tuple[int, int]], dict[str, tuple[int, int]], dict[str, tuple[int, int]]]:
    """Load RZ TD rates from PFF fantasy stats parquet files.
    Returns (receiving_rates, rushing_rates, i5_rushing_rates) where
    each is {gsis_id: (tds, opportunities)}.
    """
    if self._pff_loader is None or pff_crosswalk is None:
        return {}, {}, {}

    rec_rates: dict[str, tuple[int, int]] = {}
    rush_rates: dict[str, tuple[int, int]] = {}
    i5_rush_rates: dict[str, tuple[int, int]] = {}

    try:
        rec_df = self._pff_loader.load_facet("fantasy_receiving", [season])
    except Exception:
        rec_df = pl.DataFrame()

    if not rec_df.is_empty() and "week" in rec_df.columns:
        rec_df = rec_df.filter(pl.col("week") < week)
        if not rec_df.is_empty():
            required = {"player_id", "rz_rec_targ", "rz_rec_tds", "rz_rush_carries", "rz_rush_tds"}
            if required.issubset(set(rec_df.columns)):
                agg_cols = [
                    pl.col("rz_rec_targ").sum().alias("rz_rec_targ"),
                    pl.col("rz_rec_tds").sum().alias("rz_rec_tds"),
                    pl.col("rz_rush_carries").sum().alias("rz_rush_carries"),
                    pl.col("rz_rush_tds").sum().alias("rz_rush_tds"),
                ]
                # Add i5 columns if present and enabled
                has_i5 = self._config.i5_enabled and {"i5_rush_carries", "i5_rush_tds"}.issubset(set(rec_df.columns))
                if has_i5:
                    agg_cols.extend([
                        pl.col("i5_rush_carries").sum().alias("i5_rush_carries"),
                        pl.col("i5_rush_tds").sum().alias("i5_rush_tds"),
                    ])

                agg = rec_df.group_by("player_id").agg(agg_cols)
                for row in agg.iter_rows(named=True):
                    pff_id = row["player_id"]
                    gsis_id = pff_crosswalk.get(pff_id)
                    if gsis_id is None:
                        continue
                    if row["rz_rec_targ"] > 0:
                        rec_rates[gsis_id] = (row["rz_rec_tds"], row["rz_rec_targ"])
                    if row["rz_rush_carries"] > 0:
                        rush_rates[gsis_id] = (row["rz_rush_tds"], row["rz_rush_carries"])
                    if has_i5 and row["i5_rush_carries"] > 0:
                        i5_rush_rates[gsis_id] = (row["i5_rush_tds"], row["i5_rush_carries"])

    try:
        pass_df = self._pff_loader.load_facet("fantasy_passing", [season])
    except Exception:
        pass_df = pl.DataFrame()

    if not pass_df.is_empty() and "week" in pass_df.columns:
        pass_df = pass_df.filter(pl.col("week") < week)
        if not pass_df.is_empty():
            rush_cols = {"player_id", "rz_rush_carries", "rz_rush_tds"}
            if rush_cols.issubset(set(pass_df.columns)):
                agg_cols = [
                    pl.col("rz_rush_carries").sum().alias("rz_rush_carries"),
                    pl.col("rz_rush_tds").sum().alias("rz_rush_tds"),
                ]
                has_i5 = self._config.i5_enabled and {"i5_rush_carries", "i5_rush_tds"}.issubset(set(pass_df.columns))
                if has_i5:
                    agg_cols.extend([
                        pl.col("i5_rush_carries").sum().alias("i5_rush_carries"),
                        pl.col("i5_rush_tds").sum().alias("i5_rush_tds"),
                    ])

                agg = pass_df.group_by("player_id").agg(agg_cols)
                for row in agg.iter_rows(named=True):
                    pff_id = row["player_id"]
                    gsis_id = pff_crosswalk.get(pff_id)
                    if gsis_id is None:
                        continue
                    if row["rz_rush_carries"] > 0:
                        rush_rates[gsis_id] = (row["rz_rush_tds"], row["rz_rush_carries"])
                    if has_i5 and row["i5_rush_carries"] > 0:
                        i5_rush_rates[gsis_id] = (row["i5_rush_tds"], row["i5_rush_carries"])

    if rec_rates or rush_rates:
        logger.info("TdTendency PFF: %d receiving, %d rushing, %d i5 rushing rates (season=%d, week<%d)",
                    len(rec_rates), len(rush_rates), len(i5_rush_rates), season, week)
    return rec_rates, rush_rates, i5_rush_rates
```

- [ ] **Step 4: Update callers of _load_pff_rates in apply()**

In `apply()` (line 83), update the destructuring:

```python
rec_rates, rush_rates, i5_rush_rates = self._load_pff_rates(season, week, pff_crosswalk)
```

And the PBP fallback block (line 86-92) — also destructure the third element (will be wired in Task 3):

```python
if pbp_stats:
    if not rec_rates or not rush_rates:
        pbp_rec, pbp_rush, pbp_i5 = self._rates_from_pbp(pbp_stats)
        if not rec_rates:
            rec_rates = pbp_rec
        if not rush_rates:
            rush_rates = pbp_rush
        if not i5_rush_rates:
            i5_rush_rates = pbp_i5
```

- [ ] **Step 5: Update _rates_from_pbp return signature (stub)**

In `_rates_from_pbp()` (line 195-216), update to return a 3-tuple. For now, the third dict is empty (actual PBP counting added in Task 3):

```python
@staticmethod
def _rates_from_pbp(pbp_stats: dict) -> tuple[dict[str, tuple[int, int]], dict[str, tuple[int, int]], dict[str, tuple[int, int]]]:
    """Extract RZ TD rates from PBP aggregated stats (fallback)."""
    rec_rates: dict[str, tuple[int, int]] = {}
    rush_rates: dict[str, tuple[int, int]] = {}
    i5_rush_rates: dict[str, tuple[int, int]] = {}

    for pid, rs in pbp_stats.get("receiving", {}).items():
        rz_targ = rs.get("rz_targets", 0)
        rz_tds = rs.get("rz_tds", 0)
        if rz_targ > 0:
            rec_rates[pid] = (rz_tds, rz_targ)

    for pid, rs in pbp_stats.get("rushing", {}).items():
        rz_carries = rs.get("rz_carries", 0)
        rz_tds = rs.get("rz_tds", 0)
        if rz_carries > 0:
            rush_rates[pid] = (rz_tds, rz_carries)

        i5_carries = rs.get("i5_rush_carries", 0)
        i5_tds = rs.get("i5_rush_tds", 0)
        if i5_carries > 0:
            i5_rush_rates[pid] = (i5_tds, i5_carries)

    if rec_rates or rush_rates:
        logger.info("TdTendency PBP fallback: %d receiving, %d rushing, %d i5 rushing rates",
                    len(rec_rates), len(rush_rates), len(i5_rush_rates))
    return rec_rates, rush_rates, i5_rush_rates
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_td_tendency_engine.py -v`
Expected: All PASS (new and existing)

- [ ] **Step 7: Commit**

```bash
git add src/fantasy_sim/data/td_tendency.py tests/test_data/test_td_tendency_engine.py
git commit -m "feat: extend _load_pff_rates to return i5_rush_rates 3-tuple"
```

---

### Task 3: PBP Fallback — Add inside-5 counting to _aggregate_pbp_stats

**Files:**
- Modify: `src/fantasy_sim/data/player_builder.py:241-255`
- Test: `tests/test_data/test_td_tendency_pbp.py`

- [ ] **Step 1: Write failing tests for PBP inside-5 counting**

Add to `tests/test_data/test_td_tendency_pbp.py`:

```python
class TestPbpI5Counting:

    def test_rushing_i5_carries_counted(self):
        """Rushing plays at yardline_100 <= 5 are counted as inside-5."""
        pbp = _make_pbp_with_rz_tds()
        stats = _aggregate_pbp_stats(pbp, [2024])
        # rb1 has carries at yardline_100=4 and yardline_100=2 (both <= 5)
        assert stats["rushing"]["rb1"]["i5_rush_carries"] == 2

    def test_rushing_i5_tds_counted(self):
        """Inside-5 rushing TDs counted correctly."""
        pbp = _make_pbp_with_rz_tds()
        stats = _aggregate_pbp_stats(pbp, [2024])
        # rb1 has a TD at yardline_100=2 (inside 5)
        assert stats["rushing"]["rb1"]["i5_rush_tds"] == 1

    def test_rushing_outside_i5_not_counted(self):
        """Rushing plays at yardline_100 > 5 are not inside-5."""
        pbp = pl.DataFrame({
            "play_type": ["run"],
            "season": [2024],
            "game_id": ["g1"],
            "posteam": ["KC"],
            "passer_player_id": [None],
            "receiver_player_id": [None],
            "rusher_player_id": ["rb2"],
            "complete_pass": [0],
            "yards_gained": [8],
            "yardline_100": [10],
            "touchdown": [1],
            "pass_touchdown": [0],
            "rush_touchdown": [1],
            "sack": [0],
            "interception": [0],
            "fumble_lost": [0],
        })
        stats = _aggregate_pbp_stats(pbp, [2024])
        assert stats["rushing"]["rb2"]["i5_rush_carries"] == 0
        assert stats["rushing"]["rb2"]["i5_rush_tds"] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_td_tendency_pbp.py::TestPbpI5Counting -v`
Expected: FAIL — `i5_rush_carries` key not in rushing stats dict

- [ ] **Step 3: Add inside-5 counters to _aggregate_pbp_stats**

In `src/fantasy_sim/data/player_builder.py`, modify the rushing stats initialization (line 243-244):

```python
        if rid not in rushing_stats:
            rushing_stats[rid] = {
                "carries": 0, "yards": [], "rz_carries": 0, "rz_tds": 0,
                "i5_rush_carries": 0, "i5_rush_tds": 0,
                "team": row["posteam"], "game_ids": set(),
            }
```

Add inside-5 counting after the red zone carry block (after line 255):

```python
        # Inside-5 carry
        if row["yardline_100"] <= 5:
            rushing_stats[rid]["i5_rush_carries"] += 1
            if row.get("rush_touchdown") == 1:
                rushing_stats[rid]["i5_rush_tds"] += 1
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_td_tendency_pbp.py -v`
Expected: All PASS (new and existing)

- [ ] **Step 5: Run full test suite for regression**

Run: `uv run pytest tests/ -x -q`
Expected: All pass — new dict keys are additive and untouched by existing code

- [ ] **Step 6: Commit**

```bash
git add src/fantasy_sim/data/player_builder.py tests/test_data/test_td_tendency_pbp.py
git commit -m "feat: add inside-5 rush counters to _aggregate_pbp_stats"
```

---

### Task 4: Engine Apply — Compute i5_rushing_td_factor

**Files:**
- Modify: `src/fantasy_sim/data/td_tendency.py:51-120`
- Test: `tests/test_data/test_td_tendency_engine.py`

- [ ] **Step 1: Write failing tests for i5 factor computation**

Add to `tests/test_data/test_td_tendency_engine.py`:

```python
class TestTdTendencyI5Factor:

    def test_i5_factor_computed_from_pbp(self):
        """Inside-5 factor is set when PBP data has i5 fields."""
        config = TdTendencyConfig(enabled=True, i5_enabled=True,
                                  prior_strength=15, i5_prior_strength=25,
                                  min_opportunities=3, i5_min_opportunities=3)
        engine = TdTendencyEngine(config)
        roster = _make_roster()

        pbp_stats = {
            "receiving": {},
            "rushing": {
                "rb1": {
                    "rz_carries": 30, "rz_tds": 9,
                    "i5_rush_carries": 10, "i5_rush_tds": 6,
                    "team": "KC",
                },
            },
        }

        engine.apply(roster, season=2024, week=10, pbp_stats=pbp_stats)

        rb = roster.players[2]  # rb1
        assert rb.outcomes.rushing_td_factor != 1.0  # general factor set
        assert rb.outcomes.i5_rushing_td_factor != 1.0  # i5 factor set
        # 6/10 = 0.60 observed vs ~0.50 prior => factor > 1.0
        assert rb.outcomes.i5_rushing_td_factor > 1.0

    def test_i5_factor_neutral_below_min_opportunities(self):
        """Players with fewer than i5_min_opportunities stay at 1.0."""
        config = TdTendencyConfig(enabled=True, i5_enabled=True,
                                  i5_min_opportunities=3)
        engine = TdTendencyEngine(config)
        roster = _make_roster()

        pbp_stats = {
            "receiving": {},
            "rushing": {
                "rb1": {
                    "rz_carries": 30, "rz_tds": 9,
                    "i5_rush_carries": 2, "i5_rush_tds": 1,
                    "team": "KC",
                },
            },
        }

        engine.apply(roster, season=2024, week=10, pbp_stats=pbp_stats)
        assert roster.players[2].outcomes.i5_rushing_td_factor == 1.0

    def test_i5_disabled_leaves_factor_neutral(self):
        """When i5_enabled=False, i5_rushing_td_factor stays 1.0."""
        config = TdTendencyConfig(enabled=True, i5_enabled=False)
        engine = TdTendencyEngine(config)
        roster = _make_roster()

        pbp_stats = {
            "receiving": {},
            "rushing": {
                "rb1": {
                    "rz_carries": 30, "rz_tds": 9,
                    "i5_rush_carries": 10, "i5_rush_tds": 6,
                    "team": "KC",
                },
            },
        }

        engine.apply(roster, season=2024, week=10, pbp_stats=pbp_stats)
        assert roster.players[2].outcomes.i5_rushing_td_factor == 1.0

    def test_i5_factor_wr_stays_neutral(self):
        """WR/TE never get i5_rushing_td_factor (rushing only for RB/QB/FB)."""
        config = TdTendencyConfig(enabled=True, i5_enabled=True,
                                  i5_min_opportunities=3)
        engine = TdTendencyEngine(config)
        roster = _make_roster()

        pbp_stats = {
            "receiving": {
                "wr1": {"rz_targets": 20, "rz_tds": 5, "team": "KC"},
            },
            "rushing": {},
        }

        engine.apply(roster, season=2024, week=10, pbp_stats=pbp_stats)
        assert roster.players[0].outcomes.i5_rushing_td_factor == 1.0

    def test_i5_bayesian_blend_exact_value(self):
        """Verify exact Bayesian blend for inside-5 with known inputs."""
        config = TdTendencyConfig(enabled=True, i5_enabled=True,
                                  i5_prior_strength=25, i5_min_opportunities=3,
                                  factor_clamp=(0.65, 1.35))
        engine = TdTendencyEngine(config)
        roster = _make_roster()

        pbp_stats = {
            "receiving": {},
            "rushing": {
                "rb1": {
                    "rz_carries": 30, "rz_tds": 9,
                    "i5_rush_carries": 10, "i5_rush_tds": 6,
                    "team": "KC",
                },
            },
        }

        engine.apply(roster, season=2024, week=10, pbp_stats=pbp_stats)

        # Verify exact computation:
        # observed = 6/10 = 0.60, prior = 0.50 (RB), prior_strength = 25
        # blended = (10 * 0.60 + 25 * 0.50) / (10 + 25) = 18.5 / 35 = 0.52857...
        # factor = 0.52857 / 0.50 = 1.05714...
        expected_blend = (10 * 0.60 + 25 * 0.50) / (10 + 25)
        expected_factor = expected_blend / 0.50
        assert abs(roster.players[2].outcomes.i5_rushing_td_factor - expected_factor) < 1e-6
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_td_tendency_engine.py::TestTdTendencyI5Factor -v`
Expected: FAIL — `i5_rushing_td_factor` stays at 1.0

- [ ] **Step 3: Add inside-5 priors and computation to apply()**

In `src/fantasy_sim/data/td_tendency.py`, add the inside-5 priors after the existing priors (after line 61):

```python
_DEFAULT_I5_RUSHING_TD_PRIORS: dict[str, float] = {
    "RB": 0.50,
    "QB": 0.40,
    "FB": 0.55,
}
```

In the `apply()` method, after the existing rushing_td_factor computation in the player loop (after line 120), add the inside-5 computation:

```python
        for player in roster.players:
            gsis_id = player.player_id

            if gsis_id in rec_rates:
                tds, opps = rec_rates[gsis_id]
                if opps >= self._config.min_opportunities:
                    prior = rec_priors.get(player.position, 0.15)
                    if prior > 0:
                        observed = tds / opps
                        blended = self._bayesian_blend(observed, prior, opps)
                        player.outcomes.receiving_td_factor = self._clamp(blended / prior)

            if gsis_id in rush_rates:
                tds, opps = rush_rates[gsis_id]
                if opps >= self._config.min_opportunities:
                    prior = rush_priors.get(player.position, 0.25)
                    if prior > 0:
                        observed = tds / opps
                        blended = self._bayesian_blend(observed, prior, opps)
                        player.outcomes.rushing_td_factor = self._clamp(blended / prior)

            # Inside-5 rushing factor
            if self._config.i5_enabled and gsis_id in i5_rush_rates:
                tds, opps = i5_rush_rates[gsis_id]
                if opps >= self._config.i5_min_opportunities:
                    prior = i5_priors.get(player.position)
                    if prior is not None and prior > 0:
                        observed = tds / opps
                        blended = self._i5_bayesian_blend(observed, prior, opps)
                        player.outcomes.i5_rushing_td_factor = self._clamp(blended / prior)
```

Add the `i5_priors` dict alongside existing priors in `apply()`:

```python
        i5_priors = dict(_DEFAULT_I5_RUSHING_TD_PRIORS)
```

Add `_i5_bayesian_blend()` method (uses i5_prior_strength):

```python
    def _i5_bayesian_blend(self, observed: float, prior: float, n_obs: int) -> float:
        ps = self._config.i5_prior_strength
        return (n_obs * observed + ps * prior) / (n_obs + ps)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_td_tendency_engine.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/td_tendency.py tests/test_data/test_td_tendency_engine.py
git commit -m "feat: compute i5_rushing_td_factor in TdTendencyEngine.apply()"
```

---

### Task 5: Gate Factor Selection — Use i5 factor at yard_line <= 5

**Files:**
- Modify: `src/fantasy_sim/engine/play_resolver.py:300-306`
- Test: `tests/test_engine/test_td_tendency_gate.py`

- [ ] **Step 1: Write failing tests for i5 gate factor selection**

Add to `tests/test_engine/test_td_tendency_gate.py`:

```python
from fantasy_sim.models.player import PlayerModel, PlayerUsage, PlayerOutcomes, TeamRoster


class TestI5GateFactorSelection:
    """Verify i5_rushing_td_factor is used at yard_line <= 5."""

    def test_i5_factor_used_at_yard_line_3(self):
        """At yard_line=3, i5 factor should be used when available."""
        # We test indirectly: i5_factor=1.3 should produce more TDs
        # than rushing_td_factor=0.7 at yard_line=3
        n = 5000
        import numpy as np

        td_count_i5 = 0
        td_count_general = 0

        for _ in range(n):
            rng = np.random.default_rng()
            # Simulate i5 factor selection: yard_line=3, i5_factor=1.3
            factor = 1.3  # would be selected because yard_line <= 5 and i5 != 1.0
            if _red_zone_td_gate(3, "run", rng, factor):
                td_count_i5 += 1

        for _ in range(n):
            rng = np.random.default_rng()
            factor = 0.7  # general factor if i5 were neutral
            if _red_zone_td_gate(3, "run", rng, factor):
                td_count_general += 1

        assert td_count_i5 > td_count_general

    def test_i5_factor_used_at_yard_line_5(self):
        """At yard_line=5, i5 factor should still be used (boundary)."""
        n = 5000
        import numpy as np

        td_count_high = sum(
            _red_zone_td_gate(5, "run", np.random.default_rng(i), 1.3)
            for i in range(n)
        )
        td_count_low = sum(
            _red_zone_td_gate(5, "run", np.random.default_rng(i + n), 0.7)
            for i in range(n)
        )
        assert td_count_high > td_count_low

    def test_general_factor_used_at_yard_line_10(self):
        """At yard_line=10, general rushing_td_factor is always used (outside i5)."""
        # This test verifies the gate still works at yard_line > 5
        n = 5000
        import numpy as np

        td_count = sum(
            _red_zone_td_gate(10, "run", np.random.default_rng(i), 1.0)
            for i in range(n)
        )
        # RUN_TD_GATE for (6,10) is 0.20, so ~1000/5000 expected
        assert 500 < td_count < 1500
```

- [ ] **Step 2: Run tests to verify they pass (gate itself already works)**

Run: `uv run pytest tests/test_engine/test_td_tendency_gate.py -v`
Expected: PASS — these tests verify the gate works with different factors; the gate itself is unchanged

- [ ] **Step 3: Modify _resolve_run() to select i5 factor**

In `src/fantasy_sim/engine/play_resolver.py`, modify the TD determination block in `_resolve_run()` (lines 300-306):

Replace:
```python
        # TD determination with red zone gate
        if state.yard_line <= 20 and (state.yard_line - yards) <= 0:
            if _red_zone_td_gate(state.yard_line, "run", rng, rusher.outcomes.rushing_td_factor):
                is_td = True
            else:
                yards = _tackled_short(state.yard_line, rng)
                is_td = False
```

With:
```python
        # TD determination with red zone gate
        if state.yard_line <= 20 and (state.yard_line - yards) <= 0:
            # Use inside-5 factor at goal line when available
            if state.yard_line <= 5 and rusher.outcomes.i5_rushing_td_factor != 1.0:
                td_factor = rusher.outcomes.i5_rushing_td_factor
            else:
                td_factor = rusher.outcomes.rushing_td_factor
            if _red_zone_td_gate(state.yard_line, "run", rng, td_factor):
                is_td = True
            else:
                yards = _tackled_short(state.yard_line, rng)
                is_td = False
```

- [ ] **Step 4: Run full test suite for regression**

Run: `uv run pytest tests/ -x -q`
Expected: All pass — default `i5_rushing_td_factor=1.0` means the new conditional always takes the `else` branch in existing tests

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/engine/play_resolver.py tests/test_engine/test_td_tendency_gate.py
git commit -m "feat: select i5_rushing_td_factor at yard_line <= 5 in _resolve_run"
```

---

### Task 6: Validation Config — Wire i5 config through validation pipeline

**Files:**
- Test: `tests/test_validation/test_td_tendency_config_resolution.py`

- [ ] **Step 1: Write test for i5 config resolution**

Add to `tests/test_validation/test_td_tendency_config_resolution.py`:

```python
def test_i5_config_flows_through(self):
    config = {
        "pff": {"enabled": False},
        "weather": {"enabled": False},
        "vegas": {"enabled": False},
        "usage": {"enabled": False},
        "td_tendency": {
            "enabled": True,
            "i5_enabled": True,
            "i5_prior_strength": 30,
            "i5_min_opportunities": 4,
        },
    }
    result = build_engine_configs(config)
    td_config = result["td_tendency_config"]
    assert td_config.i5_enabled is True
    assert td_config.i5_prior_strength == 30
    assert td_config.i5_min_opportunities == 4
```

- [ ] **Step 2: Run test to verify it passes**

Run: `uv run pytest tests/test_validation/test_td_tendency_config_resolution.py -v`
Expected: PASS — `build_engine_configs` calls `load_td_tendency_config()` which already parses i5 fields (from Task 1)

- [ ] **Step 3: Commit**

```bash
git add tests/test_validation/test_td_tendency_config_resolution.py
git commit -m "test: add i5 config resolution validation test"
```

---

### Task 7: Final Regression & Cleanup

**Files:**
- All modified files

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All pass (existing + new tests)

- [ ] **Step 2: Run ruff linter**

Run: `uv run ruff check src/fantasy_sim/data/td_tendency.py src/fantasy_sim/models/player.py src/fantasy_sim/data/player_builder.py src/fantasy_sim/engine/play_resolver.py`
Expected: No errors

- [ ] **Step 3: Verify test count increased**

Run: `uv run pytest tests/ -q 2>&1 | tail -1`
Expected: Test count should be ~1447 + 12 new tests = ~1459

- [ ] **Step 4: Final commit if any lint fixes**

Only if ruff required changes:

```bash
git add -u
git commit -m "fix: ruff lint fixes for inside-5 sub-factor"
```

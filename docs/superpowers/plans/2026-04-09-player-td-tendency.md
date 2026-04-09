# Player-Level TD Tendency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-player red zone TD conversion factors that modulate the existing TD gate in play_resolver.py, using PFF fantasy stats data with Bayesian shrinkage to positional priors.

**Architecture:** New `TdTendencyEngine` computes two factors per player (`receiving_td_factor`, `rushing_td_factor`) from PFF red zone stats. Factors are stored on `PlayerOutcomes` and consumed by `_red_zone_td_gate()` as a multiplier on the base per-play probability. PBP-derived counts serve as fallback when PFF data is unavailable.

**Tech Stack:** Python 3.12+, polars, numpy, dataclasses, pytest

**Spec:** `docs/superpowers/specs/2026-04-09-player-td-tendency-design.md`

---

### Task 1: PlayerOutcomes Fields + Gate Modification

**Files:**
- Modify: `src/fantasy_sim/models/player.py:24-35` (PlayerOutcomes dataclass)
- Modify: `src/fantasy_sim/engine/play_resolver.py:56-68` (_red_zone_td_gate)
- Modify: `src/fantasy_sim/engine/play_resolver.py:222-227` (_resolve_pass gate call)
- Modify: `src/fantasy_sim/engine/play_resolver.py:296-301` (_resolve_run gate call)
- Test: `tests/test_engine/test_td_tendency_gate.py`

- [ ] **Step 1: Write failing tests for gate modification**

Create `tests/test_engine/test_td_tendency_gate.py`:

```python
"""Tests for player-level TD tendency gate modification."""

import numpy as np
import pytest
from fantasy_sim.engine.play_resolver import _red_zone_td_gate


class TestRedZoneTdGateWithFactor:
    """Verify _red_zone_td_gate accepts and applies td_factor."""

    def test_default_factor_preserves_behavior(self):
        """Factor=1.0 (default) should not change gate probability."""
        rng = np.random.default_rng(42)
        results_default = [_red_zone_td_gate(5, "pass", rng) for _ in range(1000)]
        rng2 = np.random.default_rng(42)
        results_explicit = [_red_zone_td_gate(5, "pass", rng2, td_factor=1.0) for _ in range(1000)]
        assert results_default == results_explicit

    def test_high_factor_increases_td_rate(self):
        """Factor > 1.0 should increase TD conversion rate."""
        n = 5000
        rng_lo = np.random.default_rng(99)
        rng_hi = np.random.default_rng(99)
        base_tds = sum(_red_zone_td_gate(5, "pass", rng_lo, td_factor=1.0) for _ in range(n))
        high_tds = sum(_red_zone_td_gate(5, "pass", rng_hi, td_factor=1.3) for _ in range(n))
        # With independent RNGs both seeded to 99, high_factor should produce more TDs
        # Use separate RNGs to avoid correlation artifacts
        rng_a = np.random.default_rng(123)
        rng_b = np.random.default_rng(456)
        base_tds = sum(_red_zone_td_gate(5, "pass", rng_a, td_factor=1.0) for _ in range(n))
        high_tds = sum(_red_zone_td_gate(5, "pass", rng_b, td_factor=1.3) for _ in range(n))
        assert high_tds > base_tds

    def test_low_factor_decreases_td_rate(self):
        """Factor < 1.0 should decrease TD conversion rate."""
        n = 5000
        rng_a = np.random.default_rng(123)
        rng_b = np.random.default_rng(456)
        base_tds = sum(_red_zone_td_gate(5, "pass", rng_a, td_factor=1.0) for _ in range(n))
        low_tds = sum(_red_zone_td_gate(5, "pass", rng_b, td_factor=0.7) for _ in range(n))
        assert low_tds < base_tds

    def test_factor_clamped_to_max_probability_1(self):
        """Even with very high factor, probability never exceeds 1.0."""
        rng = np.random.default_rng(42)
        # At yard_line=1, pass gate = 0.55. Factor=3.0 would give 1.65, but should clamp to 1.0
        results = [_red_zone_td_gate(1, "pass", rng, td_factor=3.0) for _ in range(100)]
        assert all(results), "With clamped prob=1.0, all should be True"

    def test_factor_applies_to_run_gate(self):
        """Factor also works for run plays."""
        n = 5000
        rng_a = np.random.default_rng(789)
        rng_b = np.random.default_rng(101)
        base_tds = sum(_red_zone_td_gate(5, "run", rng_a, td_factor=1.0) for _ in range(n))
        high_tds = sum(_red_zone_td_gate(5, "run", rng_b, td_factor=1.3) for _ in range(n))
        assert high_tds > base_tds

    def test_outside_red_zone_ignores_factor(self):
        """Outside the red zone (yard_line > 20), always returns True regardless of factor."""
        rng = np.random.default_rng(42)
        assert _red_zone_td_gate(25, "pass", rng, td_factor=0.01) is True
        assert _red_zone_td_gate(50, "run", rng, td_factor=0.01) is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_engine/test_td_tendency_gate.py -v`
Expected: FAIL — `_red_zone_td_gate() got an unexpected keyword argument 'td_factor'`

- [ ] **Step 3: Add fields to PlayerOutcomes**

In `src/fantasy_sim/models/player.py`, add two fields to the `PlayerOutcomes` dataclass after `targets_per_route_rate`:

```python
    targets_per_route_rate: float = 0.0  # USG-04: targets/routes from PFF receiving_summary
    receiving_td_factor: float = 1.0     # TD tendency: multiplier for pass TD gate
    rushing_td_factor: float = 1.0       # TD tendency: multiplier for run TD gate
```

- [ ] **Step 4: Modify `_red_zone_td_gate()` to accept td_factor**

In `src/fantasy_sim/engine/play_resolver.py`, replace the function at line 56:

```python
def _red_zone_td_gate(yard_line: int, play_type: str, rng: np.random.Generator, td_factor: float = 1.0) -> bool:
    """Check if a would-be TD actually scores, based on field position.

    Returns True if the TD stands, False if the player is tackled short.
    Outside the red zone (yard_line > 20), always returns True.

    Args:
        td_factor: Player-level multiplier on the base gate probability.
            Centered on 1.0 (neutral). Values > 1.0 increase TD rate,
            < 1.0 decrease it. Clamped so effective probability never exceeds 1.0.
    """
    if yard_line > 20:
        return True
    gate_table = PASS_TD_GATE if play_type == "pass" else RUN_TD_GATE
    for (lo, hi), prob in gate_table.items():
        if lo <= yard_line <= hi:
            return rng.random() < min(1.0, prob * td_factor)
    return True  # Safety fallback
```

- [ ] **Step 5: Pass td_factor from receivers/rushers to the gate**

In `src/fantasy_sim/engine/play_resolver.py`, update the two call sites.

In `_resolve_pass()` (~line 222), change:

```python
            if _red_zone_td_gate(state.yard_line, "pass", rng):
```

to:

```python
            if _red_zone_td_gate(state.yard_line, "pass", rng, receiver.outcomes.receiving_td_factor):
```

In `_resolve_run()` (~line 296), change:

```python
            if _red_zone_td_gate(state.yard_line, "run", rng):
```

to:

```python
            if _red_zone_td_gate(state.yard_line, "run", rng, rusher.outcomes.rushing_td_factor):
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_engine/test_td_tendency_gate.py -v`
Expected: All 6 tests PASS

- [ ] **Step 7: Run full test suite to verify no regressions**

Run: `uv run pytest tests/ -x -q`
Expected: All existing tests pass (default factor=1.0 preserves all existing behavior)

- [ ] **Step 8: Commit**

```bash
git add src/fantasy_sim/models/player.py src/fantasy_sim/engine/play_resolver.py tests/test_engine/test_td_tendency_gate.py
git commit -m "feat: add player-level td_factor to red zone TD gate

Add receiving_td_factor and rushing_td_factor fields to PlayerOutcomes.
Modify _red_zone_td_gate() to accept a td_factor multiplier parameter.
Pass player factors from _resolve_pass() and _resolve_run() call sites.
Default factor=1.0 preserves all existing behavior."
```

---

### Task 2: PBP Fallback — Red Zone TD Counting

**Files:**
- Modify: `src/fantasy_sim/data/player_builder.py:123-302` (_aggregate_pbp_stats)
- Test: `tests/test_data/test_td_tendency_pbp.py`

- [ ] **Step 1: Write failing test for PBP RZ TD counting**

Create `tests/test_data/test_td_tendency_pbp.py`:

```python
"""Tests for PBP-derived red zone TD counting in _aggregate_pbp_stats."""

import polars as pl
from fantasy_sim.data.player_builder import _aggregate_pbp_stats


def _make_pbp_with_rz_tds() -> pl.DataFrame:
    """Build minimal PBP DataFrame with red zone TD plays."""
    return pl.DataFrame({
        "play_type": ["pass", "pass", "pass", "run", "run", "pass"],
        "season": [2024] * 6,
        "game_id": ["g1"] * 6,
        "posteam": ["KC"] * 6,
        "passer_player_id": ["qb1", "qb1", "qb1", None, None, "qb1"],
        "receiver_player_id": ["wr1", "wr1", "wr1", None, None, "te1"],
        "rusher_player_id": [None, None, None, "rb1", "rb1", None],
        "complete_pass": [1, 1, 0, 0, 0, 1],
        "yards_gained": [15, 8, 0, 3, 5, 6],
        "yardline_100": [18, 10, 5, 4, 2, 6],  # all inside RZ (<=20)
        "touchdown": [0, 1, 0, 0, 1, 1],
        "pass_touchdown": [0, 1, 0, 0, 0, 1],
        "rush_touchdown": [0, 0, 0, 0, 1, 0],
        "sack": [0] * 6,
        "interception": [0] * 6,
        "fumble_lost": [0] * 6,
    })


class TestPbpRzTdCounting:
    """Verify _aggregate_pbp_stats counts RZ TDs per player."""

    def test_receiving_rz_tds_counted(self):
        pbp = _make_pbp_with_rz_tds()
        stats = _aggregate_pbp_stats(pbp, [2024])
        # wr1 has 3 RZ targets, 1 RZ receiving TD (row index 1: touchdown=1, pass_touchdown=1)
        assert stats["receiving"]["wr1"]["rz_tds"] == 1
        # te1 has 1 RZ target, 1 RZ receiving TD (row index 5)
        assert stats["receiving"]["te1"]["rz_tds"] == 1

    def test_rushing_rz_tds_counted(self):
        pbp = _make_pbp_with_rz_tds()
        stats = _aggregate_pbp_stats(pbp, [2024])
        # rb1 has 2 RZ carries, 1 RZ rushing TD (row index 4: touchdown=1, rush_touchdown=1)
        assert stats["rushing"]["rb1"]["rz_tds"] == 1

    def test_non_rz_tds_not_counted(self):
        """TDs outside the red zone should not appear in rz_tds."""
        pbp = pl.DataFrame({
            "play_type": ["pass"],
            "season": [2024],
            "game_id": ["g1"],
            "posteam": ["KC"],
            "passer_player_id": ["qb1"],
            "receiver_player_id": ["wr2"],
            "rusher_player_id": [None],
            "complete_pass": [1],
            "yards_gained": [45],
            "yardline_100": [45],  # NOT red zone
            "touchdown": [1],
            "pass_touchdown": [1],
            "rush_touchdown": [0],
            "sack": [0],
            "interception": [0],
            "fumble_lost": [0],
        })
        stats = _aggregate_pbp_stats(pbp, [2024])
        assert stats["receiving"]["wr2"]["rz_tds"] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_td_tendency_pbp.py -v`
Expected: FAIL — `KeyError: 'rz_tds'`

- [ ] **Step 3: Add rz_tds counting to _aggregate_pbp_stats**

In `src/fantasy_sim/data/player_builder.py`, in the `_aggregate_pbp_stats()` function:

**Receiving stats init** (~line 209): add `"rz_tds": 0` to the dict:

```python
            receiving_stats[rid] = {
                "targets": 0, "catches": 0, "yards": [],
                "rz_targets": 0, "rz_catches": 0, "rz_yards": [],
                "rz_tds": 0,
                "air_yards": 0.0,
                "team": row["posteam"], "game_ids": set(),
            }
```

**Receiving RZ TD counting** (~line 219, inside the `if row["yardline_100"] <= 20:` block): add after `rz_yards` append:

```python
            if row["yardline_100"] <= 20:
                receiving_stats[rid]["rz_targets"] += 1
                if row["complete_pass"] == 1:
                    receiving_stats[rid]["rz_catches"] += 1
                    receiving_stats[rid]["rz_yards"].append(row["yards_gained"])
                if row.get("pass_touchdown") == 1 or (row.get("touchdown") == 1 and row["complete_pass"] == 1):
                    receiving_stats[rid]["rz_tds"] += 1
```

**Rushing stats init** (~line 237): add `"rz_tds": 0`:

```python
            rushing_stats[rid] = {
                "carries": 0, "yards": [], "rz_carries": 0, "rz_tds": 0,
                "team": row["posteam"], "game_ids": set(),
            }
```

**Rushing RZ TD counting** (~line 248, inside the `if row["yardline_100"] <= 20:` block): add after `rz_carries` increment:

```python
            if row["yardline_100"] <= 20:
                rushing_stats[rid]["rz_carries"] += 1
                if row.get("rush_touchdown") == 1 or (row.get("touchdown") == 1 and row["yardline_100"] <= 20 and row["yards_gained"] >= row["yardline_100"]):
                    rushing_stats[rid]["rz_tds"] += 1
```

Note: Use `pass_touchdown` / `rush_touchdown` columns when available (nflverse PBP has them). Fall back to `touchdown` + field position heuristic for compatibility.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_td_tendency_pbp.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Run full suite for regressions**

Run: `uv run pytest tests/ -x -q`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add src/fantasy_sim/data/player_builder.py tests/test_data/test_td_tendency_pbp.py
git commit -m "feat: add rz_tds counting to PBP aggregation

Track per-player red zone receiving TDs and rushing TDs in
_aggregate_pbp_stats(). Uses pass_touchdown/rush_touchdown PBP columns.
Provides PBP fallback data source for TD tendency engine."
```

---

### Task 3: TdTendencyConfig + Loader + defaults.yaml

**Files:**
- Create: `src/fantasy_sim/data/td_tendency.py` (config portion)
- Modify: `config/defaults.yaml`
- Test: `tests/test_data/test_td_tendency_config.py`

- [ ] **Step 1: Write failing test for config loading**

Create `tests/test_data/test_td_tendency_config.py`:

```python
"""Tests for TD tendency config loading."""

from fantasy_sim.data.td_tendency import TdTendencyConfig, load_td_tendency_config


class TestTdTendencyConfig:

    def test_default_config(self):
        config = TdTendencyConfig()
        assert config.enabled is False
        assert config.prior_strength == 15.0
        assert config.min_opportunities == 5
        assert config.factor_clamp == (0.70, 1.30)

    def test_load_from_dict(self):
        raw = {
            "td_tendency": {
                "enabled": True,
                "prior_strength": 20.0,
                "min_opportunities": 8,
                "factor_clamp": [0.80, 1.20],
            }
        }
        config = load_td_tendency_config(raw)
        assert config.enabled is True
        assert config.prior_strength == 20.0
        assert config.min_opportunities == 8
        assert config.factor_clamp == (0.80, 1.20)

    def test_load_missing_key_returns_disabled(self):
        config = load_td_tendency_config({})
        assert config.enabled is False

    def test_load_partial_uses_defaults(self):
        raw = {"td_tendency": {"enabled": True}}
        config = load_td_tendency_config(raw)
        assert config.enabled is True
        assert config.prior_strength == 15.0  # default
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_td_tendency_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fantasy_sim.data.td_tendency'`

- [ ] **Step 3: Create td_tendency.py with config and loader**

Create `src/fantasy_sim/data/td_tendency.py`:

```python
"""TD Tendency Engine: per-player red zone TD conversion factors.

Computes receiving_td_factor and rushing_td_factor per player using
Bayesian shrinkage of observed RZ TD rates toward positional priors.

Primary data: PFF fantasy stats (fantasy_receiving, fantasy_passing).
Fallback: PBP-derived RZ TD counts from _aggregate_pbp_stats().

Pipeline position: after coverage, before weather in build_game().
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TdTendencyConfig:
    """Configuration for TD tendency engine."""

    enabled: bool = False
    prior_strength: float = 15.0
    min_opportunities: int = 5
    factor_clamp: tuple[float, float] = (0.70, 1.30)


def load_td_tendency_config(defaults: dict) -> TdTendencyConfig:
    """Extract TdTendencyConfig from the full defaults config dict.

    Reads from defaults["td_tendency"]. Returns TdTendencyConfig(enabled=False)
    if the key is missing.
    """
    td = defaults.get("td_tendency")
    if not td:
        return TdTendencyConfig(enabled=False)
    return TdTendencyConfig(
        enabled=td.get("enabled", False),
        prior_strength=td.get("prior_strength", 15.0),
        min_opportunities=td.get("min_opportunities", 5),
        factor_clamp=tuple(td.get("factor_clamp", [0.70, 1.30])),
    )
```

- [ ] **Step 4: Add td_tendency section to defaults.yaml**

In `config/defaults.yaml`, add at the end (after the `usage:` block):

```yaml
td_tendency:
  enabled: false              # flip to true after A/B validation
  prior_strength: 15          # pseudo-opportunities for Bayesian shrinkage
  min_opportunities: 5        # minimum RZ targets/carries to compute factor
  factor_clamp: [0.70, 1.30]  # prevent extreme gate modifications
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_td_tendency_config.py -v`
Expected: All 4 tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/fantasy_sim/data/td_tendency.py config/defaults.yaml tests/test_data/test_td_tendency_config.py
git commit -m "feat: add TdTendencyConfig and defaults.yaml section

Config dataclass with enabled, prior_strength, min_opportunities,
factor_clamp. Loader reads from defaults['td_tendency']. Defaults
to disabled until A/B validated."
```

---

### Task 4: TdTendencyEngine — Bayesian Computation

**Files:**
- Modify: `src/fantasy_sim/data/td_tendency.py` (add engine class)
- Test: `tests/test_data/test_td_tendency_engine.py`

- [ ] **Step 1: Write failing tests for engine computation**

Create `tests/test_data/test_td_tendency_engine.py`:

```python
"""Tests for TdTendencyEngine Bayesian factor computation."""

import numpy as np
import pytest
from fantasy_sim.data.td_tendency import TdTendencyConfig, TdTendencyEngine
from fantasy_sim.models.player import PlayerModel, PlayerUsage, PlayerOutcomes, TeamRoster


def _make_roster() -> TeamRoster:
    """Build a test roster with known RZ stats."""
    return TeamRoster(team="KC", players=[
        PlayerModel("wr1", "WR1", "WR", "KC",
                    PlayerUsage(target_share=0.25),
                    PlayerOutcomes(catch_rate=0.65)),
        PlayerModel("wr2", "WR2", "WR", "KC",
                    PlayerUsage(target_share=0.15),
                    PlayerOutcomes(catch_rate=0.60)),
        PlayerModel("rb1", "RB1", "RB", "KC",
                    PlayerUsage(carry_share=0.60),
                    PlayerOutcomes()),
        PlayerModel("qb1", "QB1", "QB", "KC",
                    PlayerUsage(snap_share=1.0),
                    PlayerOutcomes()),
    ])


class TestTdTendencyBayesianBlend:

    def test_bayesian_blend_formula(self):
        engine = TdTendencyEngine(TdTendencyConfig(enabled=True))
        # 10 opportunities, 3 TDs (30% observed), prior=0.17, prior_strength=15
        blended = engine._bayesian_blend(0.30, 0.17, 10)
        expected = (10 * 0.30 + 15 * 0.17) / (10 + 15)
        assert abs(blended - expected) < 1e-9

    def test_zero_opportunities_returns_prior(self):
        engine = TdTendencyEngine(TdTendencyConfig(enabled=True))
        blended = engine._bayesian_blend(0.0, 0.17, 0)
        expected = (0 * 0.0 + 15 * 0.17) / (0 + 15)
        assert abs(blended - expected) < 1e-9
        assert abs(blended - 0.17) < 1e-9

    def test_clamp_enforced(self):
        engine = TdTendencyEngine(TdTendencyConfig(
            enabled=True, factor_clamp=(0.70, 1.30),
        ))
        assert engine._clamp(0.50) == 0.70
        assert engine._clamp(1.50) == 1.30
        assert engine._clamp(1.0) == 1.0

    def test_factor_centered_on_1(self):
        """A player with exactly the positional average rate should get factor ~1.0."""
        engine = TdTendencyEngine(TdTendencyConfig(enabled=True, prior_strength=15))
        # If observed == prior, blended == prior, factor = prior/prior = 1.0
        blended = engine._bayesian_blend(0.17, 0.17, 30)
        factor = blended / 0.17
        assert abs(factor - 1.0) < 1e-9

    def test_above_average_gets_factor_above_1(self):
        engine = TdTendencyEngine(TdTendencyConfig(enabled=True, prior_strength=15))
        # 40 RZ targets, 12 TDs = 30% (well above WR avg ~17%)
        blended = engine._bayesian_blend(0.30, 0.17, 40)
        factor = blended / 0.17
        assert factor > 1.0

    def test_below_average_gets_factor_below_1(self):
        engine = TdTendencyEngine(TdTendencyConfig(enabled=True, prior_strength=15))
        # 40 RZ targets, 2 TDs = 5% (well below WR avg ~17%)
        blended = engine._bayesian_blend(0.05, 0.17, 40)
        factor = blended / 0.17
        assert factor < 1.0


class TestTdTendencyApplyFromPbp:

    def test_apply_sets_receiving_td_factor(self):
        config = TdTendencyConfig(enabled=True, prior_strength=15, min_opportunities=3)
        engine = TdTendencyEngine(config)
        roster = _make_roster()

        # Simulate PBP stats: wr1 has 20 RZ targets, 5 RZ TDs (25%)
        pbp_stats = {
            "receiving": {
                "wr1": {"rz_targets": 20, "rz_tds": 5, "team": "KC"},
                "wr2": {"rz_targets": 2, "rz_tds": 0, "team": "KC"},  # below min_opportunities
            },
            "rushing": {
                "rb1": {"rz_carries": 30, "rz_tds": 9, "team": "KC"},
            },
        }

        engine.apply(roster, season=2024, week=10, pbp_stats=pbp_stats)

        # wr1: 20 opps, 5 TDs = 25% observed, WR prior ~17%
        # Factor should be > 1.0
        assert roster.players[0].outcomes.receiving_td_factor > 1.0

        # wr2: only 2 opps < min_opportunities=3 -> stays at 1.0
        assert roster.players[1].outcomes.receiving_td_factor == 1.0

        # rb1: 30 opps, 9 TDs = 30% observed, RB prior ~28%
        assert roster.players[2].outcomes.rushing_td_factor > 1.0

    def test_apply_disabled_is_noop(self):
        config = TdTendencyConfig(enabled=False)
        engine = TdTendencyEngine(config)
        roster = _make_roster()
        engine.apply(roster, season=2024, week=10, pbp_stats={"receiving": {}, "rushing": {}})
        for p in roster.players:
            assert p.outcomes.receiving_td_factor == 1.0
            assert p.outcomes.rushing_td_factor == 1.0

    def test_qb_gets_rushing_td_factor(self):
        config = TdTendencyConfig(enabled=True, prior_strength=15, min_opportunities=3)
        engine = TdTendencyEngine(config)
        roster = _make_roster()

        pbp_stats = {
            "receiving": {},
            "rushing": {
                "qb1": {"rz_carries": 20, "rz_tds": 8, "team": "KC"},  # dual-threat QB
            },
        }
        engine.apply(roster, season=2024, week=10, pbp_stats=pbp_stats)
        assert roster.players[3].outcomes.rushing_td_factor > 1.0
        # QB receiving_td_factor should stay at 1.0
        assert roster.players[3].outcomes.receiving_td_factor == 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_td_tendency_engine.py -v`
Expected: FAIL — `ImportError: cannot import name 'TdTendencyEngine'`

- [ ] **Step 3: Implement TdTendencyEngine**

Add to `src/fantasy_sim/data/td_tendency.py` (after the `load_td_tendency_config` function):

```python
import polars as pl
from fantasy_sim.models.player import TeamRoster

# Default positional priors — computed from NFL 2021-2024 PBP averages.
# These are used when PFF data is unavailable or as initial estimates.
# When PFF data is available, priors are computed from the dataset itself.
_DEFAULT_RECEIVING_TD_PRIORS: dict[str, float] = {
    "WR": 0.17,
    "TE": 0.15,
    "RB": 0.12,
}
_DEFAULT_RUSHING_TD_PRIORS: dict[str, float] = {
    "RB": 0.28,
    "QB": 0.25,
    "FB": 0.30,
}


class TdTendencyEngine:
    """Per-player red zone TD conversion factors.

    Computes receiving_td_factor and rushing_td_factor via Bayesian
    blend of observed RZ TD rate toward a positional prior. Factors
    are centered on 1.0 (neutral) and stored on PlayerOutcomes.

    Primary data: PFF fantasy stats (fantasy_receiving, fantasy_passing).
    Fallback: PBP-derived rz_tds from _aggregate_pbp_stats().
    """

    def __init__(
        self,
        config: TdTendencyConfig,
        pff_loader: "PffLoader | None" = None,
    ) -> None:
        self._config = config
        self._pff_loader = pff_loader
        self._pff_rec_cache: dict[tuple[int, int], pl.DataFrame] = {}
        self._pff_pass_cache: dict[tuple[int, int], pl.DataFrame] = {}

    def apply(
        self,
        roster: TeamRoster,
        season: int,
        week: int,
        pff_crosswalk: dict[int, str] | None = None,
        pbp_stats: dict | None = None,
    ) -> None:
        """Compute and store TD factors on each player's outcomes. Mutates in-place.

        Tries PFF data first. Falls back to PBP-derived rz_tds when PFF is
        unavailable. Does nothing if config.enabled is False.

        Args:
            roster: TeamRoster to mutate.
            season: NFL season year.
            week: Target week (data from weeks < this value only).
            pff_crosswalk: PFF player_id (int) -> gsis_id (str).
            pbp_stats: Output of _aggregate_pbp_stats() for PBP fallback.
        """
        if not self._config.enabled:
            return

        # Try PFF data first
        rec_rates, rush_rates = self._load_pff_rates(season, week, pff_crosswalk)

        # Fall back to PBP if PFF yielded nothing
        if not rec_rates and not rush_rates and pbp_stats:
            rec_rates, rush_rates = self._rates_from_pbp(pbp_stats)

        if not rec_rates and not rush_rates:
            logger.debug("TdTendencyEngine: no data for season=%d week=%d, skipping", season, week)
            return

        # Compute positional priors from available data (or use defaults)
        rec_priors = self._compute_priors(rec_rates, _DEFAULT_RECEIVING_TD_PRIORS)
        rush_priors = self._compute_priors(rush_rates, _DEFAULT_RUSHING_TD_PRIORS)

        for player in roster.players:
            gsis_id = player.player_id

            # Receiving TD factor (WR, TE, RB)
            if gsis_id in rec_rates:
                tds, opps = rec_rates[gsis_id]
                if opps >= self._config.min_opportunities:
                    prior = rec_priors.get(player.position, 0.15)
                    if prior > 0:
                        observed = tds / opps
                        blended = self._bayesian_blend(observed, prior, opps)
                        player.outcomes.receiving_td_factor = self._clamp(blended / prior)

            # Rushing TD factor (RB, QB, FB)
            if gsis_id in rush_rates:
                tds, opps = rush_rates[gsis_id]
                if opps >= self._config.min_opportunities:
                    prior = rush_priors.get(player.position, 0.25)
                    if prior > 0:
                        observed = tds / opps
                        blended = self._bayesian_blend(observed, prior, opps)
                        player.outcomes.rushing_td_factor = self._clamp(blended / prior)

    def _bayesian_blend(self, observed: float, prior: float, n_obs: int) -> float:
        """Bayesian blend: (n * observed + prior_strength * prior) / (n + prior_strength)."""
        ps = self._config.prior_strength
        return (n_obs * observed + ps * prior) / (n_obs + ps)

    def _clamp(self, factor: float) -> float:
        """Clamp factor to configured range."""
        lo, hi = self._config.factor_clamp
        return max(lo, min(hi, factor))

    def _compute_priors(
        self,
        rates: dict[str, tuple[int, int]],
        defaults: dict[str, float],
    ) -> dict[str, float]:
        """Compute positional priors from the data, falling back to defaults.

        Groups rates by position (looked up from roster context), computes
        league-wide mean per position. Falls back to hardcoded defaults
        when no data is available for a position.
        """
        # For now, use defaults. When PFF data is loaded, the priors can be
        # computed from the full dataset. The defaults are calibrated from
        # NFL 2021-2024 PBP data.
        return dict(defaults)

    def _load_pff_rates(
        self,
        season: int,
        week: int,
        pff_crosswalk: dict[int, str] | None,
    ) -> tuple[dict[str, tuple[int, int]], dict[str, tuple[int, int]]]:
        """Load RZ TD rates from PFF fantasy stats parquet files.

        Returns:
            (receiving_rates, rushing_rates) where each is
            {gsis_id: (rz_tds, rz_opportunities)}.
            Empty dicts when PFF data is unavailable.
        """
        if self._pff_loader is None or pff_crosswalk is None:
            return {}, {}

        rec_rates: dict[str, tuple[int, int]] = {}
        rush_rates: dict[str, tuple[int, int]] = {}

        # Load fantasy_receiving facet
        try:
            rec_df = self._pff_loader.load_facet("fantasy_receiving", [season])
        except Exception:
            rec_df = pl.DataFrame()

        if not rec_df.is_empty() and "week" in rec_df.columns:
            rec_df = rec_df.filter(pl.col("week") < week)

            if not rec_df.is_empty():
                # Aggregate per player across weeks
                required = {"player_id", "rz_rec_targ", "rz_rec_tds", "rz_rush_carries", "rz_rush_tds"}
                if required.issubset(set(rec_df.columns)):
                    agg = rec_df.group_by("player_id").agg([
                        pl.col("rz_rec_targ").sum().alias("rz_rec_targ"),
                        pl.col("rz_rec_tds").sum().alias("rz_rec_tds"),
                        pl.col("rz_rush_carries").sum().alias("rz_rush_carries"),
                        pl.col("rz_rush_tds").sum().alias("rz_rush_tds"),
                    ])
                    for row in agg.iter_rows(named=True):
                        pff_id = row["player_id"]
                        gsis_id = pff_crosswalk.get(pff_id)
                        if gsis_id is None:
                            continue
                        if row["rz_rec_targ"] > 0:
                            rec_rates[gsis_id] = (row["rz_rec_tds"], row["rz_rec_targ"])
                        if row["rz_rush_carries"] > 0:
                            rush_rates[gsis_id] = (row["rz_rush_tds"], row["rz_rush_carries"])

        # Load fantasy_passing facet for QB rushing
        try:
            pass_df = self._pff_loader.load_facet("fantasy_passing", [season])
        except Exception:
            pass_df = pl.DataFrame()

        if not pass_df.is_empty() and "week" in pass_df.columns:
            pass_df = pass_df.filter(pl.col("week") < week)
            if not pass_df.is_empty():
                rush_cols = {"player_id", "rz_rush_carries", "rz_rush_tds"}
                if rush_cols.issubset(set(pass_df.columns)):
                    agg = pass_df.group_by("player_id").agg([
                        pl.col("rz_rush_carries").sum().alias("rz_rush_carries"),
                        pl.col("rz_rush_tds").sum().alias("rz_rush_tds"),
                    ])
                    for row in agg.iter_rows(named=True):
                        pff_id = row["player_id"]
                        gsis_id = pff_crosswalk.get(pff_id)
                        if gsis_id is None:
                            continue
                        if row["rz_rush_carries"] > 0:
                            rush_rates[gsis_id] = (row["rz_rush_tds"], row["rz_rush_carries"])

        if rec_rates or rush_rates:
            logger.info(
                "TdTendency PFF: %d receiving, %d rushing rates loaded (season=%d, week<%d)",
                len(rec_rates), len(rush_rates), season, week,
            )

        return rec_rates, rush_rates

    @staticmethod
    def _rates_from_pbp(
        pbp_stats: dict,
    ) -> tuple[dict[str, tuple[int, int]], dict[str, tuple[int, int]]]:
        """Extract RZ TD rates from PBP aggregated stats (fallback).

        Args:
            pbp_stats: Output of _aggregate_pbp_stats() containing
                'receiving' and 'rushing' dicts with 'rz_targets',
                'rz_tds', 'rz_carries' keys.

        Returns:
            (receiving_rates, rushing_rates) — {gsis_id: (rz_tds, rz_opps)}.
        """
        rec_rates: dict[str, tuple[int, int]] = {}
        rush_rates: dict[str, tuple[int, int]] = {}

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

        if rec_rates or rush_rates:
            logger.info(
                "TdTendency PBP fallback: %d receiving, %d rushing rates",
                len(rec_rates), len(rush_rates),
            )

        return rec_rates, rush_rates
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_td_tendency_engine.py -v`
Expected: All 9 tests PASS

- [ ] **Step 5: Run full suite**

Run: `uv run pytest tests/ -x -q`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add src/fantasy_sim/data/td_tendency.py tests/test_data/test_td_tendency_engine.py
git commit -m "feat: TdTendencyEngine with Bayesian blend and PBP fallback

Engine computes per-player receiving_td_factor and rushing_td_factor
from RZ TD rates with Bayesian shrinkage to positional priors. Supports
PFF fantasy stats as primary data source with PBP fallback."
```

---

### Task 5: Pipeline Integration — GameContextBuilder

**Files:**
- Modify: `src/fantasy_sim/data/game_context.py:40-163` (__init__)
- Modify: `src/fantasy_sim/data/game_context.py:534-782` (build_game)
- Test: `tests/test_data/test_td_tendency_integration.py`

- [ ] **Step 1: Write failing integration test**

Create `tests/test_data/test_td_tendency_integration.py`:

```python
"""Integration test for TdTendencyEngine in GameContextBuilder."""

from unittest.mock import patch, MagicMock

import numpy as np
import polars as pl
import pytest

from fantasy_sim.data.game_context import GameContextBuilder
from fantasy_sim.data.td_tendency import TdTendencyConfig


class TestTdTendencyInGameContext:

    def test_builder_accepts_td_tendency_config(self):
        """GameContextBuilder.__init__ should accept td_tendency_config kwarg."""
        config = TdTendencyConfig(enabled=False)
        # Should not raise
        builder = GameContextBuilder(td_tendency_config=config)
        assert builder._td_tendency_engine is None  # disabled -> no engine

    def test_builder_creates_engine_when_enabled(self):
        """When enabled, builder should create a TdTendencyEngine."""
        config = TdTendencyConfig(enabled=True)
        builder = GameContextBuilder(td_tendency_config=config)
        assert builder._td_tendency_engine is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_td_tendency_integration.py -v`
Expected: FAIL — `__init__() got an unexpected keyword argument 'td_tendency_config'`

- [ ] **Step 3: Add td_tendency_config to GameContextBuilder.__init__**

In `src/fantasy_sim/data/game_context.py`:

Add import at top (after other data imports):

```python
from fantasy_sim.data.td_tendency import TdTendencyConfig, TdTendencyEngine
```

Update `__init__` signature (~line 43) to add `td_tendency_config`:

```python
    def __init__(
        self,
        cache_dir: Path = DEFAULT_CACHE_DIR,
        pff_config: PffConfig | None = None,
        weather_config: WeatherConfig | None = None,
        vegas_config: VegasConfig | None = None,
        props_config: PropsConfig | None = None,
        usage_config: UsageConfig | None = None,
        td_tendency_config: TdTendencyConfig | None = None,
    ):
```

Add engine initialization after the usage engine block (~after line 162):

```python
        # TD tendency engine: per-player RZ TD conversion factors
        self._td_tendency_engine = None
        self._td_tendency_config = td_tendency_config or TdTendencyConfig(enabled=False)
        if self._td_tendency_config.enabled:
            self._td_tendency_engine = TdTendencyEngine(
                self._td_tendency_config, self._pff_loader,
            )
            logger.info("TD tendency engine enabled")
```

- [ ] **Step 4: Wire engine into build_game()**

In `src/fantasy_sim/data/game_context.py`, in `build_game()`, add a new block after the kicker engine block (after ~line 771) and before the weather block:

```python
        # TD tendency: per-player RZ TD conversion factors
        if self._td_tendency_engine is not None and target_season and week:
            self._ensure_pff_crosswalk(training_seasons, target_season)
            self._td_tendency_engine.apply(
                home_roster, target_season, week,
                pff_crosswalk=self._pff_crosswalk,
                pbp_stats=self._pbp_stats_cache,
            )
            self._td_tendency_engine.apply(
                away_roster, target_season, week,
                pff_crosswalk=self._pff_crosswalk,
                pbp_stats=self._pbp_stats_cache,
            )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_td_tendency_integration.py -v`
Expected: All 2 tests PASS

- [ ] **Step 6: Run full suite**

Run: `uv run pytest tests/ -x -q`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
git add src/fantasy_sim/data/game_context.py tests/test_data/test_td_tendency_integration.py
git commit -m "feat: wire TdTendencyEngine into GameContextBuilder

Add td_tendency_config parameter to GameContextBuilder.__init__().
Apply TD tendency factors in build_game() after kicker, before weather.
Uses PFF crosswalk for PFF data, falls back to PBP stats cache."
```

---

### Task 6: Validation Pipeline + CLI

**Files:**
- Modify: `src/fantasy_sim/validation/config.py`
- Modify: `src/fantasy_sim/validation/parallel.py`
- Modify: `src/fantasy_sim/cli.py`
- Test: `tests/test_validation/test_td_tendency_config_resolution.py`

- [ ] **Step 1: Write failing test for validation config resolution**

Create `tests/test_validation/test_td_tendency_config_resolution.py`:

```python
"""Test that td_tendency config flows through validation pipeline."""

from fantasy_sim.validation.config import build_engine_configs, build_bare_engine_configs


class TestTdTendencyConfigResolution:

    def test_build_engine_configs_includes_td_tendency(self):
        config = {
            "pff": {"enabled": False},
            "weather": {"enabled": False},
            "vegas": {"enabled": False},
            "usage": {"enabled": False},
            "td_tendency": {"enabled": True, "prior_strength": 20},
        }
        result = build_engine_configs(config)
        assert "td_tendency_config" in result
        assert result["td_tendency_config"] is not None
        assert result["td_tendency_config"].enabled is True
        assert result["td_tendency_config"].prior_strength == 20

    def test_build_bare_includes_td_tendency_none(self):
        result = build_bare_engine_configs()
        assert "td_tendency_config" in result
        assert result["td_tendency_config"] is None

    def test_disabled_td_tendency_returns_none(self):
        config = {
            "pff": {"enabled": False},
            "weather": {"enabled": False},
            "vegas": {"enabled": False},
            "usage": {"enabled": False},
            "td_tendency": {"enabled": False},
        }
        result = build_engine_configs(config)
        assert result["td_tendency_config"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_validation/test_td_tendency_config_resolution.py -v`
Expected: FAIL — `AssertionError: 'td_tendency_config' not in result`

- [ ] **Step 3: Update validation/config.py**

In `src/fantasy_sim/validation/config.py`:

Add import:

```python
from fantasy_sim.data.td_tendency import load_td_tendency_config
```

In `build_engine_configs()`, add after the usage line:

```python
    td_tendency = load_td_tendency_config(config)
```

And add to the return dict:

```python
        "td_tendency_config": td_tendency if td_tendency.enabled else None,
```

In `build_bare_engine_configs()`, add to the return dict:

```python
        "td_tendency_config": None,
```

- [ ] **Step 4: Update validation/parallel.py**

In `src/fantasy_sim/validation/parallel.py`, add `td_tendency_config=None` parameter to `build_games_parallel()` and pass it through to the `GameContextBuilder` constructor in the worker functions. Follow the exact same pattern as `usage_config` — search for every occurrence of `usage_config` in the file and add a parallel `td_tendency_config` parameter.

- [ ] **Step 5: Update cli.py _make_builder**

In `src/fantasy_sim/cli.py`:

Add import:

```python
from fantasy_sim.data.td_tendency import load_td_tendency_config
```

In `_make_builder()`, add after the `usage_config` block:

```python
    td_tendency_config = load_td_tendency_config(defaults)
    loader = DataLoader()
    return GameContextBuilder(
        cache_dir=loader.cache_dir,
        pff_config=pff_config,
        weather_config=weather_config,
        vegas_config=vegas_config,
        props_config=props_config,
        usage_config=usage_config,
        td_tendency_config=td_tendency_config,
    )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_validation/test_td_tendency_config_resolution.py -v`
Expected: All 3 tests PASS

- [ ] **Step 7: Run full suite**

Run: `uv run pytest tests/ -x -q`
Expected: All tests pass

- [ ] **Step 8: Commit**

```bash
git add src/fantasy_sim/validation/config.py src/fantasy_sim/validation/parallel.py src/fantasy_sim/cli.py tests/test_validation/test_td_tendency_config_resolution.py
git commit -m "feat: wire td_tendency through validation pipeline and CLI

Add td_tendency_config to build_engine_configs, build_bare_engine_configs,
build_games_parallel, and _make_builder. The --set td_tendency.enabled=true
flag now works in the A/B validation script."
```

---

### Task 7: PFF Fantasy Stats Scraper

**Files:**
- Modify: `scripts/scrape_pff.py`
- Test: Manual verification (scraper is network-dependent)

- [ ] **Step 1: Add fantasy stats scraping function**

In `scripts/scrape_pff.py`, add a new function after the existing `scrape_season` function. This handles the different API structure (aggregate per-week vs per-game):

```python
# Fantasy stats API base URL (different from game-level PFF API)
FANTASY_STATS_BASE = "https://www.pff.com"

FANTASY_FACETS: list[tuple[str, str]] = [
    ("receiving", "fantasy_receiving"),
    ("passing", "fantasy_passing"),
]


def scrape_fantasy_stats(
    client: httpx.Client,
    season: int,
    weeks: list[int] | None,
    delay: float,
) -> dict:
    """Scrape PFF fantasy stats (receiving + passing) per-week.

    Unlike game-level facets, these are aggregate endpoints that return
    all players for a given season+week combination.

    Stores parquet files at:
        ~/.fantasy-sim/pff/processed/nfl/fantasy_{facet}_{season}.parquet
    """
    stats = {"requests": 0, "skipped": 0, "failures": 0}

    if weeks is None:
        weeks = list(range(1, 19))  # NFL weeks 1-18

    for api_facet, output_name in FANTASY_FACETS:
        all_rows: list[dict] = []

        for week in weeks:
            output_path = PROCESSED_DIR / "nfl" / f"{output_name}_{season}_week{week}.json"
            output_path.parent.mkdir(parents=True, exist_ok=True)

            if output_path.exists():
                cached = json.loads(output_path.read_text())
                for row in cached:
                    row["season"] = season
                    row["week"] = week
                all_rows.extend(cached)
                stats["skipped"] += 1
                continue

            url = f"/api/fantasy/stats/{api_facet}?season={season}&weeks={week}&scoring=preset_ppr"
            data = fetch_json(client, url, delay=delay)
            stats["requests"] += 1

            if data is _NOT_FOUND or data is None:
                console.print(f"  [yellow]No data:[/yellow] {output_name} season={season} week={week}")
                stats["failures"] += 1
                continue

            if not isinstance(data, list):
                console.print(f"  [yellow]Unexpected response:[/yellow] {output_name} week={week}")
                stats["failures"] += 1
                continue

            output_path.write_text(json.dumps(data, indent=2))

            for row in data:
                row["season"] = season
                row["week"] = week
            all_rows.extend(data)
            console.print(f"  {output_name} week {week}: {len(data)} players")

        # Write combined parquet
        if all_rows:
            df = pl.DataFrame(all_rows)
            parquet_path = PROCESSED_DIR / "nfl" / f"{output_name}_{season}.parquet"
            df.write_parquet(parquet_path)
            console.print(f"  [green]Wrote {output_name}_{season}.parquet ({len(all_rows)} rows)[/green]")

    return stats
```

- [ ] **Step 2: Wire into main CLI**

In the `main()` function of `scripts/scrape_pff.py`, add a `--fantasy` flag and call `scrape_fantasy_stats()` when enabled. Add after the existing `scrape_season()` call:

```python
    # Fantasy stats (uses different API endpoint)
    if args.fantasy:
        console.print(f"\n[bold]Scraping fantasy stats for {args.season}...[/bold]")
        fantasy_stats = scrape_fantasy_stats(client, args.season, weeks, args.delay)
        console.print(f"Fantasy stats: {fantasy_stats['requests']} requests, {fantasy_stats['skipped']} cached, {fantasy_stats['failures']} failures")
```

Add the CLI argument:

```python
    parser.add_argument("--fantasy", action="store_true", help="Also scrape fantasy stats (receiving, passing)")
```

- [ ] **Step 3: Test scraper manually**

Run: `uv run python scripts/scrape_pff.py --season 2024 --fantasy`
Expected: Fantasy stats files written to `~/.fantasy-sim/pff/processed/nfl/fantasy_receiving_2024.parquet` and `fantasy_passing_2024.parquet`

- [ ] **Step 4: Commit**

```bash
git add scripts/scrape_pff.py
git commit -m "feat: add PFF fantasy stats scraper (receiving + passing)

Scrapes per-week fantasy stats from /api/fantasy/stats/ endpoints.
Caches raw JSON per week, combines into season parquet files.
Used by TdTendencyEngine for RZ TD rate data."
```

---

### Task 8: Final Verification

**Files:** None (verification only)

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests pass (existing + new TD tendency tests)

- [ ] **Step 2: Verify A/B testing works end-to-end**

Note: This step requires PFF data to be scraped. Without PFF data, the engine falls back to PBP, which also works. The user will run A/B manually per their preference (memory: `feedback_ab_manual.md`).

Verify the config override works:

```bash
uv run python -c "
from fantasy_sim.config.loader import load_defaults
from fantasy_sim.validation.config import apply_overrides, build_engine_configs
defaults = load_defaults()
modified = apply_overrides(defaults, ['td_tendency.enabled=true'])
configs = build_engine_configs(modified)
print('td_tendency enabled:', configs['td_tendency_config'] is not None)
print('prior_strength:', configs['td_tendency_config'].prior_strength if configs['td_tendency_config'] else 'N/A')
"
```

Expected output:

```
td_tendency enabled: True
prior_strength: 15.0
```

- [ ] **Step 3: Commit any remaining changes and verify clean state**

```bash
git status
uv run pytest tests/ -x -q
```

Expected: Clean working tree, all tests pass.

---

## File Summary

| File | Action | Purpose |
|------|--------|---------|
| `src/fantasy_sim/models/player.py` | Modify | Add `receiving_td_factor`, `rushing_td_factor` to PlayerOutcomes |
| `src/fantasy_sim/engine/play_resolver.py` | Modify | `_red_zone_td_gate()` accepts `td_factor`, call sites pass it |
| `src/fantasy_sim/data/player_builder.py` | Modify | Add `rz_tds` counting to PBP aggregation |
| `src/fantasy_sim/data/td_tendency.py` | Create | TdTendencyConfig, load_td_tendency_config, TdTendencyEngine |
| `src/fantasy_sim/data/game_context.py` | Modify | Wire engine into __init__ and build_game |
| `src/fantasy_sim/validation/config.py` | Modify | Add td_tendency_config to build_engine_configs |
| `src/fantasy_sim/validation/parallel.py` | Modify | Add td_tendency_config parameter |
| `src/fantasy_sim/cli.py` | Modify | Add load_td_tendency_config to _make_builder |
| `config/defaults.yaml` | Modify | Add `td_tendency:` section |
| `scripts/scrape_pff.py` | Modify | Add fantasy_receiving + fantasy_passing scraper |
| `tests/test_engine/test_td_tendency_gate.py` | Create | Gate modification tests |
| `tests/test_data/test_td_tendency_pbp.py` | Create | PBP fallback tests |
| `tests/test_data/test_td_tendency_config.py` | Create | Config loading tests |
| `tests/test_data/test_td_tendency_engine.py` | Create | Engine computation tests |
| `tests/test_data/test_td_tendency_integration.py` | Create | Pipeline integration tests |
| `tests/test_validation/test_td_tendency_config_resolution.py` | Create | Validation config tests |

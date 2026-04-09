# Validation Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `validate_pff_signal.py` + `validate_weekly_signal.py` with a single `scripts/validate.py` that uses defaults.yaml as the source of truth, dot-notation `--set` overrides, bare baseline caching, dual-arm parallelism, and a unified ledger.

**Architecture:** Config-first approach. Both arms are built by loading `defaults.yaml` through existing config loaders, with Arm A either bare (all None) or defaults, and Arm B as defaults + `--set` overrides. Eliminates the 160-line `_build_pff_config()` if/elif chain entirely. Reuses all existing parallelism (`build_games_parallel`, `simulate_games_parallel`), metric functions (`spearman_rank_correlation`, `compute_weekly_rank_corr`, etc.), and data loading (`DataLoader`, `load_actual_scores`).

**Tech Stack:** Python 3.12+, argparse, polars, numpy, existing validation module

**Spec:** `docs/superpowers/specs/2026-04-08-validation-redesign-design.md`

---

### Task 1: Fix `load_pff_config` to handle kicker and dst_baseline

The existing `load_pff_config()` in `src/fantasy_sim/data/pff/config.py` doesn't parse `kicker` or `dst_baseline` sections from the config dict. The `PffConfig` dataclass has these fields (with defaults), so they silently get default values instead of what's in `defaults.yaml`. This must be fixed before the new validation script can correctly build PffConfig from the YAML.

**Files:**
- Modify: `src/fantasy_sim/data/pff/config.py:178-186`
- Test: `tests/test_data/test_pff_config_loader.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_data/test_pff_config_loader.py`:

```python
"""Tests for PFF config loader — kicker and DST baseline parsing."""
from fantasy_sim.data.pff.config import load_pff_config


def test_load_pff_config_parses_kicker():
    config = {
        "pff": {
            "enabled": True,
            "kicker": {
                "enabled": True,
                "prior_strength": 25,
                "min_attempts": 8,
            },
        },
    }
    result = load_pff_config(config)
    assert result.kicker.enabled is True
    assert result.kicker.prior_strength == 25
    assert result.kicker.min_attempts == 8


def test_load_pff_config_parses_dst_baseline():
    config = {
        "pff": {
            "enabled": True,
            "dst_baseline": {
                "enabled": True,
                "sensitivities": {"fumble_rate": 0.08},
                "prior_strength": 15,
                "min_games": 5,
                "clamp": [0.80, 1.20],
            },
        },
    }
    result = load_pff_config(config)
    assert result.dst_baseline.enabled is True
    assert result.dst_baseline.sensitivities == {"fumble_rate": 0.08}
    assert result.dst_baseline.prior_strength == 15
    assert result.dst_baseline.min_games == 5
    assert result.dst_baseline.clamp == [0.80, 1.20]


def test_load_pff_config_kicker_dst_defaults_when_missing():
    """When kicker/dst_baseline sections are absent, defaults are used."""
    config = {"pff": {"enabled": True}}
    result = load_pff_config(config)
    # Should get dataclass defaults, not crash
    assert result.kicker.enabled is True  # KickerConfig default
    assert result.dst_baseline.enabled is True  # DstBaselineConfig default
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_pff_config_loader.py -v`
Expected: `test_load_pff_config_parses_kicker` FAILS (kicker gets default values, not the ones in config)

- [ ] **Step 3: Add kicker and dst_baseline parsing to load_pff_config**

In `src/fantasy_sim/data/pff/config.py`, add these imports at the top (alongside existing ones):

```python
from fantasy_sim.data.pff.models import (
    # ... existing imports ...
    DstBaselineConfig,
    KickerConfig,
)
```

Then before the `return PffConfig(...)` statement (line ~178), add:

```python
    kicker_raw = pff.get("kicker", {})
    kicker = KickerConfig(
        enabled=kicker_raw.get("enabled", True),
        prior_strength=kicker_raw.get("prior_strength", 20),
        min_attempts=kicker_raw.get("min_attempts", 5),
    )

    dst_raw = pff.get("dst_baseline", {})
    dst_baseline = DstBaselineConfig(
        enabled=dst_raw.get("enabled", True),
        sensitivities=dst_raw.get("sensitivities", {"fumble_rate": 0.06}),
        prior_strength=dst_raw.get("prior_strength", 10),
        min_games=dst_raw.get("min_games", 4),
        clamp=dst_raw.get("clamp", [0.85, 1.15]),
    )
```

Then update the return statement to include them:

```python
    return PffConfig(
        enabled=pff.get("enabled", False),
        data_dir=pff.get("data_dir"),
        matchup=matchup,
        talent=talent,
        tier_engine=tier_engine,
        team_context=team_context,
        coverage=coverage,
        kicker=kicker,
        dst_baseline=dst_baseline,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_pff_config_loader.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Run full test suite to check for regressions**

Run: `uv run pytest tests/ -x -q`
Expected: All existing tests still pass

- [ ] **Step 6: Commit**

```bash
git add src/fantasy_sim/data/pff/config.py tests/test_data/test_pff_config_loader.py
git commit -m "fix: add kicker and dst_baseline parsing to load_pff_config"
```

---

### Task 2: Config resolution module

New module that replaces the entire mode-based config system. Provides dot-notation override parsing and builds engine configs from a plain dict (using existing loaders).

**Files:**
- Create: `src/fantasy_sim/validation/config.py`
- Create: `tests/test_validation/test_config.py`

- [ ] **Step 1: Write failing tests for `_parse_value`**

Create `tests/test_validation/test_config.py`:

```python
"""Tests for validation config resolution."""
import copy
import pytest
from fantasy_sim.validation.config import (
    _parse_value,
    apply_overrides,
    build_engine_configs,
    build_bare_engine_configs,
)


class TestParseValue:
    def test_true(self):
        assert _parse_value("true") is True

    def test_false(self):
        assert _parse_value("false") is False

    def test_true_case_insensitive(self):
        assert _parse_value("True") is True
        assert _parse_value("FALSE") is False

    def test_int(self):
        assert _parse_value("42") == 42
        assert isinstance(_parse_value("42"), int)

    def test_negative_int(self):
        assert _parse_value("-3") == -3

    def test_float(self):
        assert _parse_value("0.06") == 0.06
        assert isinstance(_parse_value("0.06"), float)

    def test_negative_float(self):
        assert _parse_value("-0.03") == -0.03

    def test_string(self):
        assert _parse_value("hello") == "hello"
        assert isinstance(_parse_value("hello"), str)

    def test_empty_string(self):
        assert _parse_value("") == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_validation/test_config.py::TestParseValue -v`
Expected: ImportError — `config` module doesn't exist yet

- [ ] **Step 3: Implement `_parse_value`**

Create `src/fantasy_sim/validation/config.py`:

```python
"""Config resolution for A/B validation.

Replaces the mode-based config system with defaults.yaml + dot-notation overrides.
"""

from __future__ import annotations

import copy


def _parse_value(s: str) -> bool | int | float | str:
    """Parse a CLI string value to its Python type.

    Handles: 'true'/'false' -> bool, integers, floats, else str.
    """
    if s.lower() == "true":
        return True
    if s.lower() == "false":
        return False
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s
```

- [ ] **Step 4: Run `_parse_value` tests**

Run: `uv run pytest tests/test_validation/test_config.py::TestParseValue -v`
Expected: All PASS

- [ ] **Step 5: Write failing tests for `apply_overrides`**

Add to `tests/test_validation/test_config.py`:

```python
class TestApplyOverrides:
    def test_set_nested_bool(self):
        config = {"pff": {"matchup": {"enabled": True}}}
        result = apply_overrides(config, ["pff.matchup.enabled=false"])
        assert result["pff"]["matchup"]["enabled"] is False

    def test_set_nested_float(self):
        config = {"pff": {"matchup": {"pass_defense_sensitivity": 0.08}}}
        result = apply_overrides(config, ["pff.matchup.pass_defense_sensitivity=0.12"])
        assert result["pff"]["matchup"]["pass_defense_sensitivity"] == 0.12

    def test_multiple_overrides(self):
        config = {"pff": {"enabled": True, "matchup": {"enabled": True}}}
        result = apply_overrides(config, [
            "pff.enabled=false",
            "pff.matchup.enabled=false",
        ])
        assert result["pff"]["enabled"] is False
        assert result["pff"]["matchup"]["enabled"] is False

    def test_does_not_mutate_original(self):
        config = {"pff": {"matchup": {"enabled": True}}}
        apply_overrides(config, ["pff.matchup.enabled=false"])
        assert config["pff"]["matchup"]["enabled"] is True

    def test_top_level_key(self):
        config = {"scoring_format": "ppr"}
        result = apply_overrides(config, ["scoring_format=half_ppr"])
        assert result["scoring_format"] == "half_ppr"

    def test_invalid_key_raises(self):
        config = {"pff": {"matchup": {"enabled": True}}}
        with pytest.raises(KeyError):
            apply_overrides(config, ["pff.nonexistent.enabled=false"])

    def test_set_int(self):
        config = {"pff": {"kicker": {"prior_strength": 20}}}
        result = apply_overrides(config, ["pff.kicker.prior_strength=30"])
        assert result["pff"]["kicker"]["prior_strength"] == 30
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `uv run pytest tests/test_validation/test_config.py::TestApplyOverrides -v`
Expected: FAIL — `apply_overrides` not defined yet

- [ ] **Step 7: Implement `apply_overrides`**

Add to `src/fantasy_sim/validation/config.py`:

```python
def apply_overrides(config: dict, overrides: list[str]) -> dict:
    """Apply dot-notation overrides to a config dict.

    Each override is 'dotted.key.path=value'. Deep-copies config first
    so the original is never mutated.

    Raises KeyError if an intermediate key doesn't exist.
    """
    config = copy.deepcopy(config)
    for override in overrides:
        key_path, raw_value = override.split("=", 1)
        keys = key_path.split(".")
        target = config
        for k in keys[:-1]:
            target = target[k]
        target[keys[-1]] = _parse_value(raw_value)
    return config
```

- [ ] **Step 8: Run `apply_overrides` tests**

Run: `uv run pytest tests/test_validation/test_config.py::TestApplyOverrides -v`
Expected: All PASS

- [ ] **Step 9: Write failing tests for `build_engine_configs` and `build_bare_engine_configs`**

Add to `tests/test_validation/test_config.py`:

```python
from fantasy_sim.config.loader import load_defaults


class TestBuildEngineConfigs:
    def test_defaults_produces_enabled_configs(self):
        defaults = load_defaults()
        configs = build_engine_configs(defaults)
        # defaults.yaml has pff.enabled=true, weather.enabled=true, etc.
        assert configs["pff_config"] is not None
        assert configs["pff_config"].enabled is True
        assert configs["weather_config"] is not None
        assert configs["weather_config"].enabled is True
        assert configs["vegas_config"] is not None
        assert configs["props_config"] is not None
        assert configs["usage_config"] is not None

    def test_disabled_engine_returns_none(self):
        defaults = load_defaults()
        overridden = apply_overrides(defaults, ["pff.enabled=false"])
        configs = build_engine_configs(overridden)
        assert configs["pff_config"] is None

    def test_sub_engine_override_propagates(self):
        defaults = load_defaults()
        overridden = apply_overrides(defaults, ["pff.matchup.enabled=false"])
        configs = build_engine_configs(overridden)
        assert configs["pff_config"] is not None
        assert configs["pff_config"].matchup.enabled is False


class TestBuildBareEngineConfigs:
    def test_all_none(self):
        configs = build_bare_engine_configs()
        assert configs["pff_config"] is None
        assert configs["weather_config"] is None
        assert configs["vegas_config"] is None
        assert configs["props_config"] is None
        assert configs["usage_config"] is None
```

- [ ] **Step 10: Run tests to verify they fail**

Run: `uv run pytest tests/test_validation/test_config.py -k "BuildEngine or BuildBare" -v`
Expected: FAIL — functions not defined yet

- [ ] **Step 11: Implement `build_engine_configs` and `build_bare_engine_configs`**

Add to `src/fantasy_sim/validation/config.py`:

```python
from fantasy_sim.data.pff.config import load_pff_config
from fantasy_sim.data.weather.config import load_weather_config
from fantasy_sim.data.vegas.config import load_vegas_config, load_props_config
from fantasy_sim.data.usage.config import load_usage_config


def build_engine_configs(config: dict) -> dict:
    """Build all engine config dataclasses from a full config dict.

    Returns a dict with keys: pff_config, weather_config, vegas_config,
    props_config, usage_config. Each value is the config dataclass if
    enabled, or None if disabled.
    """
    pff = load_pff_config(config)
    weather = load_weather_config(config)
    vegas = load_vegas_config(config)
    props = load_props_config(config)
    usage = load_usage_config(config)
    return {
        "pff_config": pff if pff.enabled else None,
        "weather_config": weather if weather.enabled else None,
        "vegas_config": vegas if vegas.enabled else None,
        "props_config": props if props.enabled else None,
        "usage_config": usage if usage.enabled else None,
    }


def build_bare_engine_configs() -> dict:
    """Return engine configs dict with all engines disabled (None)."""
    return {
        "pff_config": None,
        "weather_config": None,
        "vegas_config": None,
        "props_config": None,
        "usage_config": None,
    }
```

- [ ] **Step 12: Run all config tests**

Run: `uv run pytest tests/test_validation/test_config.py -v`
Expected: All PASS

- [ ] **Step 13: Commit**

```bash
git add src/fantasy_sim/validation/config.py tests/test_validation/test_config.py
git commit -m "feat: add config resolution module with dot-notation overrides"
```

---

### Task 3: Bare baseline cache

Caches bare arm simulation results to disk so repeat runs skip Arm A entirely.

**Files:**
- Create: `src/fantasy_sim/validation/cache.py`
- Create: `tests/test_validation/test_cache.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_validation/test_cache.py`:

```python
"""Tests for bare baseline cache."""
from pathlib import Path
from fantasy_sim.validation.cache import cache_path, load_cache, save_cache


def test_cache_path_format():
    p = cache_path(2024, 50, "ppr", 4, cache_dir=Path("/tmp/test"))
    assert p == Path("/tmp/test/bare_2024_50_ppr_4.json")


def test_cache_path_different_params():
    p1 = cache_path(2023, 50, "ppr", 4, cache_dir=Path("/tmp/test"))
    p2 = cache_path(2024, 50, "ppr", 4, cache_dir=Path("/tmp/test"))
    assert p1 != p2


def test_load_cache_missing_file():
    result = load_cache(Path("/tmp/nonexistent_cache_xyz.json"))
    assert result is None


def test_cache_roundtrip(tmp_path):
    projections = {
        "player1": {1: 15.2, 2: 8.4, 3: 22.1},
        "player2": {1: 6.0, 2: 12.3},
    }
    meta = {
        "player1": {"position": "WR", "team": "KC", "name": "Test Player"},
        "player2": {"position": "RB", "team": "BUF", "name": "Other Player"},
    }
    p = tmp_path / "test_cache.json"
    save_cache(p, projections, meta)
    loaded = load_cache(p)
    assert loaded is not None
    assert loaded["projections"]["player1"][1] == 15.2
    assert loaded["projections"]["player2"][2] == 12.3
    assert loaded["player_meta"]["player1"]["position"] == "WR"


def test_cache_roundtrip_preserves_week_int_keys(tmp_path):
    """JSON serializes int keys as strings — verify they're restored."""
    projections = {"p1": {10: 5.0, 18: 12.0}}
    meta = {"p1": {"position": "QB", "team": "KC", "name": "QB1"}}
    p = tmp_path / "test_cache.json"
    save_cache(p, projections, meta)
    loaded = load_cache(p)
    assert 10 in loaded["projections"]["p1"]
    assert 18 in loaded["projections"]["p1"]
    assert isinstance(list(loaded["projections"]["p1"].keys())[0], int)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_validation/test_cache.py -v`
Expected: ImportError

- [ ] **Step 3: Implement cache module**

Create `src/fantasy_sim/validation/cache.py`:

```python
"""Bare baseline cache for A/B validation.

Caches bare arm (all engines off) simulation results to disk, keyed by
(season, sims, scoring, training_years). Cache is valid regardless of
defaults.yaml engine config changes since bare = all engines off.
"""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[3] / "results" / "cache"


def cache_path(
    season: int,
    sims: int,
    scoring: str,
    training_years: int,
    cache_dir: Path = DEFAULT_CACHE_DIR,
) -> Path:
    """Generate cache file path for a bare baseline run."""
    return cache_dir / f"bare_{season}_{sims}_{scoring}_{training_years}.json"


def load_cache(path: Path) -> dict | None:
    """Load cached bare baseline results.

    Returns None if cache file doesn't exist. Converts JSON string week
    keys back to int.

    Returns:
        Dict with 'projections' (player_id -> {week: fpts}) and
        'player_meta' (player_id -> {position, team, name}), or None.
    """
    if not path.exists():
        return None
    with open(path) as f:
        raw = json.load(f)
    projections: dict[str, dict[int, float]] = {}
    for pid, weeks in raw["projections"].items():
        projections[pid] = {int(w): v for w, v in weeks.items()}
    return {"projections": projections, "player_meta": raw["player_meta"]}


def save_cache(
    path: Path,
    projections: dict[str, dict[int, float]],
    player_meta: dict[str, dict],
) -> None:
    """Write bare baseline results to cache.

    Args:
        projections: player_id -> {week: fpts} mapping.
        player_meta: player_id -> {position, team, name} mapping.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # Convert int week keys to strings for JSON
    serializable = {
        pid: {str(w): v for w, v in weeks.items()}
        for pid, weeks in projections.items()
    }
    with open(path, "w") as f:
        json.dump({"projections": serializable, "player_meta": player_meta}, f)
```

- [ ] **Step 4: Run cache tests**

Run: `uv run pytest tests/test_validation/test_cache.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/validation/cache.py tests/test_validation/test_cache.py
git commit -m "feat: add bare baseline cache for A/B validation"
```

---

### Task 4: Unified ledger

Single ledger replacing `pff_ab_ledger.json` and `weekly_ab_ledger.json`.

**Files:**
- Create: `src/fantasy_sim/validation/ledger.py`
- Create: `tests/test_validation/test_ledger.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_validation/test_ledger.py`:

```python
"""Tests for unified A/B validation ledger."""
from fantasy_sim.validation.ledger import (
    LedgerEntry,
    SeasonMetrics,
    format_ledger_table,
    load_ledger,
    save_ledger,
)


def _make_entry(label: str = "test-run", rank_corr_delta: float = 0.05) -> LedgerEntry:
    """Create a minimal LedgerEntry for testing."""
    return LedgerEntry(
        label=label,
        timestamp="2026-04-08T12:00:00",
        sims=50,
        test_seasons=[2022, 2023, 2024],
        training_years=4,
        scoring="ppr",
        baseline="bare",
        overrides=[],
        config_snapshot={"pff": {"enabled": True}},
        season_results=[
            SeasonMetrics(
                test_season=2024,
                arm_a_rank_corr={"QB": 0.40, "RB": 0.35, "WR": 0.30, "TE": 0.28},
                arm_b_rank_corr={"QB": 0.42, "RB": 0.37, "WR": 0.33, "TE": 0.30},
                arm_a_weekly_mae=7.0,
                arm_b_weekly_mae=6.8,
                arm_a_season_mae=2.5,
                arm_b_season_mae=2.3,
                arm_a_calibration=0.12,
                arm_b_calibration=0.10,
            ),
        ],
        weekly_summaries=None,
        directional_accuracy=None,
    )


def test_ledger_roundtrip(tmp_path):
    path = tmp_path / "test_ledger.json"
    entries = [_make_entry("run-1"), _make_entry("run-2")]
    save_ledger(path, entries)
    loaded = load_ledger(path)
    assert len(loaded) == 2
    assert loaded[0].label == "run-1"
    assert loaded[1].label == "run-2"


def test_load_ledger_missing_file(tmp_path):
    path = tmp_path / "nonexistent.json"
    assert load_ledger(path) == []


def test_season_metrics_rank_corr_delta():
    sm = SeasonMetrics(
        test_season=2024,
        arm_a_rank_corr={"QB": 0.40, "RB": 0.35, "WR": 0.30, "TE": 0.28},
        arm_b_rank_corr={"QB": 0.42, "RB": 0.37, "WR": 0.33, "TE": 0.30},
        arm_a_weekly_mae=7.0,
        arm_b_weekly_mae=6.8,
        arm_a_season_mae=2.5,
        arm_b_season_mae=2.3,
        arm_a_calibration=0.12,
        arm_b_calibration=0.10,
    )
    # avg delta = (0.02 + 0.02 + 0.03 + 0.02) / 4 = 0.0225
    assert abs(sm.rank_corr_delta - 0.0225) < 1e-6


def test_format_ledger_table_empty():
    result = format_ledger_table([])
    assert "No entries" in result


def test_format_ledger_table_with_entries():
    entry = _make_entry("baseline-v1")
    entry.overrides = ["usage.ngs.enabled=true"]
    table = format_ledger_table([entry])
    assert "baseline-v1" in table
    assert "bare" in table
    assert "usage.ngs.enabled=true" in table
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_validation/test_ledger.py -v`
Expected: ImportError

- [ ] **Step 3: Implement ledger module**

Create `src/fantasy_sim/validation/ledger.py`:

```python
"""Unified A/B validation ledger.

Replaces pff_ab_ledger.json and weekly_ab_ledger.json with a single
results/ab_ledger.json file.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from fantasy_sim.validation.weekly import (
    DirectionalAccuracyResult,
    WeeklyPositionSummary,
)

DEFAULT_LEDGER_PATH = Path(__file__).resolve().parents[3] / "results" / "ab_ledger.json"

POSITIONS = ("QB", "RB", "WR", "TE")


@dataclass
class SeasonMetrics:
    """Per-season, per-arm metrics."""

    test_season: int
    arm_a_rank_corr: dict[str, float]
    arm_b_rank_corr: dict[str, float]
    arm_a_weekly_mae: float
    arm_b_weekly_mae: float
    arm_a_season_mae: float
    arm_b_season_mae: float
    arm_a_calibration: float
    arm_b_calibration: float

    @property
    def rank_corr_delta(self) -> float:
        """Average rank correlation improvement (B - A) across positions."""
        deltas = [
            self.arm_b_rank_corr.get(pos, 0.0) - self.arm_a_rank_corr.get(pos, 0.0)
            for pos in POSITIONS
        ]
        return sum(deltas) / len(deltas) if deltas else 0.0

    @property
    def weekly_mae_delta(self) -> float:
        """Weekly MAE change (B - A). Negative = better."""
        return self.arm_b_weekly_mae - self.arm_a_weekly_mae

    @property
    def season_mae_delta(self) -> float:
        """Season MAE change (B - A). Negative = better."""
        return self.arm_b_season_mae - self.arm_a_season_mae


@dataclass
class LedgerEntry:
    """One A/B validation run."""

    label: str
    timestamp: str
    sims: int
    test_seasons: list[int]
    training_years: int
    scoring: str
    baseline: str  # "bare" or "defaults"
    overrides: list[str]
    config_snapshot: dict
    season_results: list[SeasonMetrics]
    weekly_summaries: list[WeeklyPositionSummary] | None = None
    directional_accuracy: DirectionalAccuracyResult | None = None

    @property
    def avg_rank_corr_delta(self) -> float:
        if not self.season_results:
            return 0.0
        return sum(r.rank_corr_delta for r in self.season_results) / len(
            self.season_results
        )

    @property
    def avg_weekly_mae_delta(self) -> float:
        if not self.season_results:
            return 0.0
        return sum(r.weekly_mae_delta for r in self.season_results) / len(
            self.season_results
        )

    @property
    def avg_season_mae_delta(self) -> float:
        if not self.season_results:
            return 0.0
        return sum(r.season_mae_delta for r in self.season_results) / len(
            self.season_results
        )


def load_ledger(path: Path = DEFAULT_LEDGER_PATH) -> list[LedgerEntry]:
    """Load ledger entries from JSON. Returns empty list if file doesn't exist."""
    if not path.exists():
        return []
    with open(path) as f:
        raw = json.load(f)
    entries = []
    for item in raw:
        season_results = [SeasonMetrics(**sr) for sr in item.get("season_results", [])]
        ws_raw = item.get("weekly_summaries")
        weekly_summaries = (
            [WeeklyPositionSummary(**ws) for ws in ws_raw] if ws_raw else None
        )
        da_raw = item.get("directional_accuracy")
        da = DirectionalAccuracyResult(**da_raw) if da_raw else None
        item = dict(item)
        item["season_results"] = season_results
        item["weekly_summaries"] = weekly_summaries
        item["directional_accuracy"] = da
        entries.append(LedgerEntry(**item))
    return entries


def save_ledger(path: Path, entries: list[LedgerEntry]) -> None:
    """Write ledger entries to JSON."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump([asdict(e) for e in entries], f, indent=2)


def format_ledger_table(entries: list[LedgerEntry]) -> str:
    """Return an ASCII table of ledger entries."""
    if not entries:
        return "No entries in ledger."

    header = (
        f"{'#':>3}  {'Label':<22}  {'baseline':<9}  {'overrides':<30}  "
        f"{'rank_corr':>9}  {'wk_mae':>7}  {'szn_mae':>7}"
    )
    sep = "=" * len(header)
    lines = [sep, header, "-" * len(header)]

    for i, e in enumerate(entries, start=1):
        overrides_str = ", ".join(e.overrides) if e.overrides else "(none)"
        if len(overrides_str) > 30:
            overrides_str = overrides_str[:27] + "..."
        row = (
            f"{i:>3}  {e.label:<22}  {e.baseline:<9}  {overrides_str:<30}  "
            f"{e.avg_rank_corr_delta:>+.4f}    "
            f"{e.avg_weekly_mae_delta:>+.3f}  "
            f"{e.avg_season_mae_delta:>+.3f}"
        )
        lines.append(row)

    lines.append(sep)
    return "\n".join(lines)
```

- [ ] **Step 4: Run ledger tests**

Run: `uv run pytest tests/test_validation/test_ledger.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/validation/ledger.py tests/test_validation/test_ledger.py
git commit -m "feat: add unified A/B validation ledger"
```

---

### Task 5: Main validation script

The big task — `scripts/validate.py` replaces both existing scripts. Includes CLI, season runner, output formatting, and multi-season parallelism.

**Files:**
- Create: `scripts/validate.py`

**Dependencies:** Tasks 1-4 must be complete.

- [ ] **Step 1: Create CLI skeleton with argparse**

Create `scripts/validate.py`:

```python
"""Unified A/B validation script.

Replaces validate_pff_signal.py and validate_weekly_signal.py.
Runs Arm A (bare baseline or defaults) vs Arm B (defaults + overrides)
and reports season-level and/or weekly metrics.

Usage:
    uv run python scripts/validate.py --help
    uv run python scripts/validate.py --sims 50 --label "baseline-v1"
    uv run python scripts/validate.py --sims 50 --set usage.ngs.enabled=true --label "test-ngs"
    uv run python scripts/validate.py --sims 50 --baseline defaults --set usage.ngs.enabled=true
    uv run python scripts/validate.py --show-ledger
"""

from __future__ import annotations

import argparse
import sys
import time
import zlib
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np
import polars as pl

from fantasy_sim.config.loader import load_defaults, resolve_scoring
from fantasy_sim.data.actuals import load_actual_scores
from fantasy_sim.data.loader import DataLoader
from fantasy_sim.validation.cache import cache_path, load_cache, save_cache
from fantasy_sim.validation.config import (
    apply_overrides,
    build_bare_engine_configs,
    build_engine_configs,
)
from fantasy_sim.validation.ledger import (
    DEFAULT_LEDGER_PATH,
    LedgerEntry,
    SeasonMetrics,
    format_ledger_table,
    load_ledger,
    save_ledger,
)
from fantasy_sim.validation.metrics import boom_bust_calibration, spearman_rank_correlation
from fantasy_sim.validation.parallel import (
    GameSpec,
    build_games_parallel,
    default_max_workers,
    simulate_games_parallel,
)
from fantasy_sim.validation.weekly import (
    WeeklyPlayerRecord,
    WeeklyPositionSummary,
    compute_directional_accuracy,
    compute_mae_by_difficulty,
    compute_weekly_mae,
    compute_weekly_rank_corr,
)

POSITIONS = ("QB", "RB", "WR", "TE")
_HOLDOUT_SEASON = 2025


def build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "A/B validation: compare Arm A (bare baseline or defaults) vs "
            "Arm B (defaults + overrides)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--set",
        action="append",
        default=[],
        dest="overrides",
        metavar="KEY=VALUE",
        help=(
            "Dot-notation config override applied to Arm B. Repeatable. "
            "Example: --set pff.matchup.enabled=false --set usage.ngs.enabled=true"
        ),
    )
    parser.add_argument(
        "--baseline",
        choices=["bare", "defaults"],
        default="bare",
        help="Arm A config: 'bare' (all engines off, default) or 'defaults' (defaults.yaml as-is).",
    )
    parser.add_argument("--sims", type=int, default=50, metavar="N", help="Sims per game (default: 50).")
    parser.add_argument("--seasons", type=int, nargs="+", default=[2022, 2023, 2024], metavar="YEAR")
    parser.add_argument("--training-years", type=int, default=4, dest="training_years", metavar="N")
    parser.add_argument("--scoring", default="ppr", choices=["ppr", "half_ppr", "standard"])
    parser.add_argument("--positions", nargs="+", default=list(POSITIONS))
    parser.add_argument("--label", type=str, default=None, help="Label for ledger entry.")
    parser.add_argument("--show-ledger", action="store_true", help="Print ledger and exit.")
    parser.add_argument("--workers", type=int, default=0, metavar="N", help="Workers (0=auto, 1=sequential).")
    parser.add_argument("--no-cache", action="store_true", dest="no_cache", help="Skip bare baseline cache.")
    return parser
```

- [ ] **Step 2: Verify CLI skeleton works**

Run: `uv run python scripts/validate.py --help`
Expected: Help text prints with all flags

- [ ] **Step 3: Add `run_season` function — the core dual-arm runner**

This is the heart of the script. Add below the CLI builder:

```python
def run_season(
    test_season: int,
    n_sims: int,
    scoring_config: dict,
    num_training_seasons: int,
    arm_a_configs: dict,
    arm_b_configs: dict,
    positions: list[str],
    max_workers: int,
    cached_arm_a: dict | None = None,
) -> dict:
    """Run A/B comparison for one season.

    Args:
        arm_a_configs: Dict of engine config kwargs (pff_config, weather_config, etc.) or all None.
        arm_b_configs: Dict of engine config kwargs for Arm B.
        cached_arm_a: Pre-loaded cache dict with 'projections' and 'player_meta', or None.

    Returns:
        Dict with 'season_metrics', 'weekly_records' (if applicable),
        and 'arm_a_projections'/'arm_a_meta' (for cache saving).
    """
    training_seasons = list(range(test_season - num_training_seasons, test_season))

    loader = DataLoader()
    schedules = loader.load_schedules([test_season])
    player_stats = loader.load_player_stats([test_season])
    actuals = load_actual_scores(player_stats, scoring_config, test_season)

    # Index actuals
    actual_by_pw: dict[str, dict[int, float]] = defaultdict(dict)
    actual_pos: dict[str, str] = {}
    actual_team: dict[str, str] = {}
    actual_name: dict[str, str] = {}
    for a in actuals:
        actual_by_pw[a.player_id][a.week] = a.fpts
        actual_pos[a.player_id] = a.position
        actual_team[a.player_id] = a.team
        actual_name[a.player_id] = a.name

    weeks = sorted(
        schedules.filter(pl.col("season") == test_season)["week"].unique().to_list()
    )
    weeks = [w for w in weeks if 1 <= w <= 18]

    # Build game args
    game_args = []
    for wk in weeks:
        week_games = schedules.filter(
            (pl.col("week") == wk) & (pl.col("season") == test_season)
        )
        for game in week_games.iter_rows(named=True):
            home, away = game["home_team"], game["away_team"]
            seed = zlib.crc32(game["game_id"].encode()) % (2**31)
            game_args.append((home, away, training_seasons, test_season, wk, game["game_id"], seed))

    # --- Build + simulate ---
    arm_a_proj: dict[str, dict[int, float]] = {}
    arm_a_meta: dict[str, dict] = {}

    if cached_arm_a is not None:
        # Arm A from cache — only build and simulate Arm B
        arm_a_proj = cached_arm_a["projections"]
        arm_a_meta = cached_arm_a["player_meta"]
        print(f"  [{test_season}] Arm A loaded from cache", flush=True)

        print(f"  [{test_season}] Building {len(game_args)} Arm B game contexts...", flush=True)
        build_results = build_games_parallel(
            game_args, cache_dir=loader.cache_dir,
            max_workers=max_workers, dual_arm=False,
            **arm_b_configs,
        )
        specs_b: list[GameSpec] = []
        for r in build_results:
            if r["status"] != "ok":
                continue
            specs_b.append(GameSpec(
                game_id=r["game_id"], home_dists=r["home_dists"],
                away_dists=r["away_dists"], home_roster=r["home_roster"],
                away_roster=r["away_roster"], seed=r["seed"], week=r["week"],
            ))

        print(f"  [{test_season}] Simulating {len(specs_b)} Arm B games...", flush=True)
        sim_b = simulate_games_parallel(
            specs_b, n_sims=n_sims, scoring_config=scoring_config,
            max_workers=max_workers,
        )

        # Index Arm B projections
        arm_b_proj: dict[str, dict[int, float]] = defaultdict(dict)
        arm_b_meta: dict[str, dict] = {}
        for result in sim_b:
            spec = next(s for s in specs_b if s.game_id == result.game_id)
            for proj in result.projections:
                pid = proj["player_id"]
                arm_b_proj[pid][spec.week] = proj["fpts"]
                if pid not in arm_b_meta:
                    arm_b_meta[pid] = {
                        "position": proj.get("position", actual_pos.get(pid, "")),
                        "team": proj.get("team", actual_team.get(pid, "")),
                        "name": proj.get("name", actual_name.get(pid, "")),
                    }

    else:
        # No cache — determine build strategy
        arm_a_is_bare = all(v is None for v in arm_a_configs.values())

        if arm_a_is_bare:
            # Bare baseline: use dual-arm build (shares data loading)
            print(f"  [{test_season}] Building {len(game_args)} game pairs (dual-arm)...", flush=True)
            build_results = build_games_parallel(
                game_args, cache_dir=loader.cache_dir,
                max_workers=max_workers, dual_arm=True,
                pff_config=arm_b_configs.get("pff_config"),
                weather_config=arm_b_configs.get("weather_config"),
                vegas_config=arm_b_configs.get("vegas_config"),
                props_config=arm_b_configs.get("props_config"),
                usage_config=arm_b_configs.get("usage_config"),
            )

            specs_a: list[GameSpec] = []
            specs_b: list[GameSpec] = []
            for r in build_results:
                if r["status"] != "ok":
                    continue
                off = r["results"]["off"]
                on = r["results"]["on"]
                specs_a.append(GameSpec(
                    game_id=r["game_id"], home_dists=off[0], away_dists=off[1],
                    home_roster=off[2], away_roster=off[3],
                    seed=r["seed"], week=r["week"], metadata={"arm": "a"},
                ))
                specs_b.append(GameSpec(
                    game_id=r["game_id"], home_dists=on[0], away_dists=on[1],
                    home_roster=on[2], away_roster=on[3],
                    seed=r["seed"], week=r["week"], metadata={"arm": "b"},
                ))

            all_specs = specs_a + specs_b

        else:
            # --baseline defaults: two separate single-arm builds
            print(f"  [{test_season}] Building {len(game_args)} Arm A game contexts...", flush=True)
            build_a = build_games_parallel(
                game_args, cache_dir=loader.cache_dir,
                max_workers=max_workers, dual_arm=False, **arm_a_configs,
            )
            print(f"  [{test_season}] Building {len(game_args)} Arm B game contexts...", flush=True)
            build_b = build_games_parallel(
                game_args, cache_dir=loader.cache_dir,
                max_workers=max_workers, dual_arm=False, **arm_b_configs,
            )

            specs_a = []
            for r in build_a:
                if r["status"] != "ok":
                    continue
                specs_a.append(GameSpec(
                    game_id=r["game_id"], home_dists=r["home_dists"],
                    away_dists=r["away_dists"], home_roster=r["home_roster"],
                    away_roster=r["away_roster"],
                    seed=r["seed"], week=r["week"], metadata={"arm": "a"},
                ))
            specs_b = []
            for r in build_b:
                if r["status"] != "ok":
                    continue
                specs_b.append(GameSpec(
                    game_id=r["game_id"], home_dists=r["home_dists"],
                    away_dists=r["away_dists"], home_roster=r["home_roster"],
                    away_roster=r["away_roster"],
                    seed=r["seed"], week=r["week"], metadata={"arm": "b"},
                ))

            all_specs = specs_a + specs_b

        print(f"  [{test_season}] Simulating {len(all_specs)} game-arms...", flush=True)
        sim_all = simulate_games_parallel(
            all_specs, n_sims=n_sims, scoring_config=scoring_config,
            max_workers=max_workers,
        )

        # Split results by arm
        arm_a_proj = defaultdict(dict)
        arm_b_proj = defaultdict(dict)
        arm_a_meta = {}
        arm_b_meta = {}

        spec_by_id_a = {s.game_id: s for s in specs_a}
        spec_by_id_b = {s.game_id: s for s in specs_b}

        for result in sim_all:
            is_arm_a = result.metadata.get("arm") == "a"
            spec = spec_by_id_a[result.game_id] if is_arm_a else spec_by_id_b[result.game_id]
            proj_dict = arm_a_proj if is_arm_a else arm_b_proj
            meta_dict = arm_a_meta if is_arm_a else arm_b_meta
            for proj in result.projections:
                pid = proj["player_id"]
                proj_dict[pid][spec.week] = proj["fpts"]
                if pid not in meta_dict:
                    meta_dict[pid] = {
                        "position": proj.get("position", actual_pos.get(pid, "")),
                        "team": proj.get("team", actual_team.get(pid, "")),
                        "name": proj.get("name", actual_name.get(pid, "")),
                    }

    # --- Compute season-level metrics ---
    def _compute_arm_metrics(
        proj_by_pw: dict[str, dict[int, float]],
    ) -> tuple[float, float, dict[str, float], float]:
        """Returns (weekly_mae, season_mae, rank_corr_by_pos, calibration)."""
        all_errors = []
        for pid, pw in proj_by_pw.items():
            for wk, fpts in pw.items():
                if pid in actual_by_pw and wk in actual_by_pw[pid]:
                    all_errors.append(abs(fpts - actual_by_pw[pid][wk]))
        weekly_mae = float(np.mean(all_errors)) if all_errors else 99.0

        proj_totals = {pid: sum(wks.values()) for pid, wks in proj_by_pw.items()}
        act_totals = {pid: sum(wks.values()) for pid, wks in actual_by_pw.items()}
        common = set(proj_totals.keys()) & set(act_totals.keys())
        season_errors = [abs(proj_totals[pid] - act_totals[pid]) for pid in common]
        season_mae = float(np.mean(season_errors)) if season_errors else 99.0

        rank_corr = {}
        for pos in POSITIONS:
            pos_pids = [pid for pid in common if actual_pos.get(pid) == pos]
            if len(pos_pids) >= 5:
                p = [proj_totals[pid] for pid in pos_pids]
                a = [act_totals[pid] for pid in pos_pids]
                rank_corr[pos] = spearman_rank_correlation(p, a)
            else:
                rank_corr[pos] = 0.0

        boom_threshold = 20.0
        pred_boom, act_boom = {}, {}
        for pid in common:
            pw = proj_by_pw.get(pid, {})
            aw = actual_by_pw.get(pid, {})
            if len(aw) >= 5:
                pred_boom[pid] = sum(1 for v in pw.values() if v >= boom_threshold) / max(len(pw), 1)
                act_boom[pid] = sum(1 for v in aw.values() if v >= boom_threshold) / len(aw)
        cal = boom_bust_calibration(pred_boom, act_boom) if pred_boom else 0.5

        return weekly_mae, season_mae, rank_corr, cal

    a_wm, a_sm, a_rc, a_cal = _compute_arm_metrics(dict(arm_a_proj))
    b_wm, b_sm, b_rc, b_cal = _compute_arm_metrics(dict(arm_b_proj))

    season_metrics = SeasonMetrics(
        test_season=test_season,
        arm_a_rank_corr=a_rc, arm_b_rank_corr=b_rc,
        arm_a_weekly_mae=a_wm, arm_b_weekly_mae=b_wm,
        arm_a_season_mae=a_sm, arm_b_season_mae=b_sm,
        arm_a_calibration=a_cal, arm_b_calibration=b_cal,
    )

    # --- Compute weekly records (if needed) ---
    weekly_records = None
    # --- Compute weekly records ---
    records: list[WeeklyPlayerRecord] = []
    common_pids = set(arm_a_proj.keys()) & set(arm_b_proj.keys())
    for pid in common_pids:
        pos = actual_pos.get(pid, arm_b_meta.get(pid, {}).get("position", ""))
        if pos not in positions:
            continue
        name = actual_name.get(pid, arm_b_meta.get(pid, {}).get("name", ""))
        team = actual_team.get(pid, arm_b_meta.get(pid, {}).get("team", ""))
        common_weeks = set(arm_a_proj[pid].keys()) & set(arm_b_proj[pid].keys())
        for wk in common_weeks:
            if pid not in actual_by_pw or wk not in actual_by_pw[pid]:
                continue
            records.append(WeeklyPlayerRecord(
                player_id=pid, name=name, position=pos, team=team,
                week=wk, season=test_season,
                projected_fpts_on=arm_b_proj[pid][wk],
                projected_fpts_off=arm_a_proj[pid][wk],
                actual_fpts=actual_by_pw[pid][wk],
            ))
    weekly_records = records

    return {
        "season_metrics": season_metrics,
        "weekly_records": weekly_records,
        "arm_a_projections": dict(arm_a_proj) if cached_arm_a is None else None,
        "arm_a_meta": arm_a_meta if cached_arm_a is None else None,
    }
```

- [ ] **Step 4: Add output formatting functions**

```python
def print_header(args, cache_status: dict[int, bool]) -> None:
    overrides_str = " + [" + ", ".join(args.overrides) + "]" if args.overrides else ""
    cache_hits = [s for s, hit in cache_status.items() if hit]
    cache_misses = [s for s, hit in cache_status.items() if not hit]
    cache_str = ""
    if args.baseline == "bare" and not args.no_cache:
        parts = []
        if cache_hits:
            parts.append(f"HIT ({', '.join(str(s) for s in cache_hits)})")
        if cache_misses:
            parts.append(f"MISS ({', '.join(str(s) for s in cache_misses)})")
        cache_str = ", ".join(parts)

    print("=" * 68)
    print("  A/B VALIDATION")
    print("=" * 68)
    print(f"  baseline    : {args.baseline}")
    print(f"  arm B       : defaults{overrides_str}")
    print(f"  sims        : {args.sims}")
    print(f"  seasons     : {args.seasons}")
    print(f"  scoring     : {args.scoring}")
    if cache_str:
        print(f"  bare cache  : {cache_str}")
    print("=" * 68)


def print_season_results(season_results: list[SeasonMetrics]) -> None:
    print("\n" + "=" * 68)
    print("  SEASON-LEVEL RESULTS")
    print("=" * 68)

    for sm in season_results:
        print(f"\n  Season {sm.test_season}:")
        rc_parts = []
        for pos in POSITIONS:
            a_val = sm.arm_a_rank_corr.get(pos, 0.0)
            b_val = sm.arm_b_rank_corr.get(pos, 0.0)
            delta = b_val - a_val
            rc_parts.append(f"{pos} {a_val:.3f}->{b_val:.3f} ({delta:+.3f})")
        print(f"    rank_corr:  {rc_parts[0]}  {rc_parts[1]}")
        print(f"                {rc_parts[2]}  {rc_parts[3]}")
        wm_delta = sm.weekly_mae_delta
        sm_delta = sm.season_mae_delta
        print(f"    weekly_mae: {sm.arm_a_weekly_mae:.2f} -> {sm.arm_b_weekly_mae:.2f} ({wm_delta:+.2f})")
        print(f"    season_mae: {sm.arm_a_season_mae:.2f} -> {sm.arm_b_season_mae:.2f} ({sm_delta:+.2f})")

    if len(season_results) > 1:
        avg_rc = sum(r.rank_corr_delta for r in season_results) / len(season_results)
        avg_wm = sum(r.weekly_mae_delta for r in season_results) / len(season_results)
        avg_sm = sum(r.season_mae_delta for r in season_results) / len(season_results)
        print(f"\n  AVERAGES:")
        print(f"    rank_corr delta:  {avg_rc:+.4f}")
        print(f"    weekly_mae delta: {avg_wm:+.3f}")
        print(f"    season_mae delta: {avg_sm:+.3f}")


def print_weekly_results(
    all_records: list[WeeklyPlayerRecord],
    positions: list[str],
    seasons: list[int],
    scoring_config: dict,
) -> tuple[list[WeeklyPositionSummary], object | None]:
    """Print weekly metrics and return summaries + directional accuracy."""
    print("\n" + "=" * 68)
    print("  WEEKLY RESULTS")
    print("=" * 68)

    summaries: list[WeeklyPositionSummary] = []
    for pos in positions:
        pos_records = [r for r in all_records if r.position == pos]
        if not pos_records:
            continue
        rc_on = compute_weekly_rank_corr(all_records, pos, use_pff_on=True)
        rc_off = compute_weekly_rank_corr(all_records, pos, use_pff_on=False)
        mae_on = compute_weekly_mae(all_records, pos, use_pff_on=True)
        mae_off = compute_weekly_mae(all_records, pos, use_pff_on=False)
        tercile = compute_mae_by_difficulty(all_records, pos)
        n_weeks = len({(r.season, r.week) for r in pos_records})

        summary = WeeklyPositionSummary(
            position=pos,
            weekly_rank_corr_on=rc_on, weekly_rank_corr_off=rc_off,
            weekly_mae_on=mae_on, weekly_mae_off=mae_off,
            mae_by_tercile=tercile,
            n_player_weeks=len(pos_records), n_weeks=n_weeks,
        )
        summaries.append(summary)

        rc_delta = rc_on - rc_off
        mae_delta = mae_on - mae_off
        print(f"\n  {pos}  ({len(pos_records)} player-weeks, {n_weeks} weeks)")
        print(f"    rank_corr: {rc_off:.4f} -> {rc_on:.4f} ({rc_delta:+.4f})")
        print(f"    weekly_mae: {mae_off:.3f} -> {mae_on:.3f} ({mae_delta:+.3f})")
        if tercile:
            print(f"    mae_by_difficulty: strong={tercile.get('strong', 0):.3f}  "
                  f"neutral={tercile.get('neutral', 0):.3f}  "
                  f"weak={tercile.get('weak', 0):.3f}")

    dir_accuracy = None
    if "WR" in positions:
        loader = DataLoader()
        actuals_by_player: dict[str, list] = defaultdict(list)
        for season in seasons:
            ps = loader.load_player_stats([season])
            from fantasy_sim.config.loader import load_defaults, resolve_scoring
            defaults = load_defaults()
            sc = resolve_scoring(defaults["scoring"], "ppr")
            season_actuals = load_actual_scores(ps, sc, season)
            for a in season_actuals:
                actuals_by_player[a.player_id].append(a)
        dir_accuracy = compute_directional_accuracy(all_records, actuals_by_player)
        print(f"\n  WR Directional Accuracy: {dir_accuracy.correct_direction}/{dir_accuracy.total_eligible} "
              f"= {dir_accuracy.accuracy:.1%}")

    return summaries, dir_accuracy
```

- [ ] **Step 5: Add `main()` function — orchestration**

```python
def main() -> int:
    parser = build_cli()
    args = parser.parse_args()

    if args.show_ledger:
        entries = load_ledger()
        print(format_ledger_table(entries))
        return 0

    # Hold-out gate
    if any(s >= _HOLDOUT_SEASON for s in args.seasons):
        print(
            f"ERROR: Season {_HOLDOUT_SEASON}+ is reserved as hold-out. "
            "Use --seasons 2022 2023 2024.",
            file=sys.stderr,
        )
        return 1

    # Resolve configs
    defaults = load_defaults()
    scoring_config = resolve_scoring(defaults["scoring"], args.scoring)

    if args.baseline == "bare":
        arm_a_configs = build_bare_engine_configs()
    else:
        arm_a_configs = build_engine_configs(defaults)

    if args.overrides:
        arm_b_dict = apply_overrides(defaults, args.overrides)
    else:
        arm_b_dict = defaults
    arm_b_configs = build_engine_configs(arm_b_dict)

    # Check cache
    cache_status: dict[int, bool] = {}
    cached_results: dict[int, dict | None] = {}
    for season in args.seasons:
        if args.baseline == "bare" and not args.no_cache:
            cp = cache_path(season, args.sims, args.scoring, args.training_years)
            cached = load_cache(cp)
            cache_status[season] = cached is not None
            cached_results[season] = cached
        else:
            cache_status[season] = False
            cached_results[season] = None

    print_header(args, cache_status)

    # Compute workers
    num_seasons = len(args.seasons)
    if args.workers == 1:
        per_season_workers = 1
    elif args.workers > 1:
        per_season_workers = args.workers
    else:
        per_season_workers = default_max_workers(batch_size=288, num_concurrent=num_seasons)
    print(f"  workers     : {per_season_workers} per season")

    # Run seasons
    total_start = time.time()
    all_season_metrics: list[SeasonMetrics] = []
    all_weekly_records: list[WeeklyPlayerRecord] = []
    cache_to_save: list[tuple[int, dict, dict]] = []  # (season, projections, meta)

    if len(args.seasons) > 1:
        from concurrent.futures import ProcessPoolExecutor, as_completed

        print(f"\nRunning {len(args.seasons)} seasons in parallel...")
        with ProcessPoolExecutor(max_workers=len(args.seasons)) as pool:
            futures = {
                pool.submit(
                    run_season,
                    test_season=season,
                    n_sims=args.sims,
                    scoring_config=scoring_config,
                    num_training_seasons=args.training_years,
                    arm_a_configs=arm_a_configs,
                    arm_b_configs=arm_b_configs,
                    positions=args.positions,
                    max_workers=per_season_workers,
                    cached_arm_a=cached_results[season],
                ): season
                for season in args.seasons
            }
            for future in as_completed(futures):
                season = futures[future]
                result = future.result()
                all_season_metrics.append(result["season_metrics"])
                if result["weekly_records"]:
                    all_weekly_records.extend(result["weekly_records"])
                if result["arm_a_projections"] is not None:
                    cache_to_save.append((
                        season, result["arm_a_projections"], result["arm_a_meta"],
                    ))
                print(f"  Season {season} complete.")
    else:
        for season in args.seasons:
            result = run_season(
                test_season=season,
                n_sims=args.sims,
                scoring_config=scoring_config,
                num_training_seasons=args.training_years,
                arm_a_configs=arm_a_configs,
                arm_b_configs=arm_b_configs,
                positions=args.positions,
                max_workers=per_season_workers,
                cached_arm_a=cached_results[season],
            )
            all_season_metrics.append(result["season_metrics"])
            if result["weekly_records"]:
                all_weekly_records.extend(result["weekly_records"])
            if result["arm_a_projections"] is not None:
                cache_to_save.append((
                    season, result["arm_a_projections"], result["arm_a_meta"],
                ))

    # Sort season results
    all_season_metrics.sort(key=lambda sm: sm.test_season)

    total_elapsed = time.time() - total_start
    print(f"\nTotal time: {total_elapsed:.1f}s")

    # Print results
    print_season_results(all_season_metrics)

    weekly_summaries = None
    dir_accuracy = None
    if all_weekly_records:
        weekly_summaries, dir_accuracy = print_weekly_results(
            all_weekly_records, args.positions, args.seasons, scoring_config,
        )

    print("\n" + "=" * 68)

    # Save cache
    if args.baseline == "bare" and not args.no_cache:
        for season, proj, meta in cache_to_save:
            cp = cache_path(season, args.sims, args.scoring, args.training_years)
            save_cache(cp, proj, meta)
            print(f"  Cached bare baseline for {season}")

    # Save to ledger
    if args.label:
        entry = LedgerEntry(
            label=args.label,
            timestamp=datetime.now().isoformat(timespec="seconds"),
            sims=args.sims,
            test_seasons=args.seasons,
            training_years=args.training_years,
            scoring=args.scoring,
            baseline=args.baseline,
            overrides=args.overrides,
            config_snapshot=arm_b_dict if args.overrides else defaults,
            season_results=all_season_metrics,
            weekly_summaries=weekly_summaries,
            directional_accuracy=dir_accuracy,
        )
        ledger = load_ledger()
        ledger.append(entry)
        save_ledger(DEFAULT_LEDGER_PATH, ledger)
        print(f"\n  Appended to ledger as #{len(ledger)}: {args.label}")
        print(format_ledger_table(ledger))

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 6: Verify script runs with `--help`**

Run: `uv run python scripts/validate.py --help`
Expected: Full help text with all flags

- [ ] **Step 7: Verify `--show-ledger` works on empty ledger**

Run: `uv run python scripts/validate.py --show-ledger`
Expected: "No entries in ledger."

- [ ] **Step 8: Run full test suite for regressions**

Run: `uv run pytest tests/ -x -q`
Expected: All existing tests pass

- [ ] **Step 9: Commit**

```bash
git add scripts/validate.py
git commit -m "feat: add unified validate.py replacing both A/B validation scripts"
```

---

### Task 6: AB-TESTING.md documentation

Usage guide with examples and config reference.

**Files:**
- Create: `docs/AB-TESTING.md`

- [ ] **Step 1: Write the documentation**

Create `docs/AB-TESTING.md`:

```markdown
# A/B Testing Guide

Unified validation script for testing engine changes against a baseline.

## Quick Start

```bash
# Run your current defaults vs bare baseline
uv run python scripts/validate.py --sims 50 --label "my-defaults"

# Test a change: add NGS signal
uv run python scripts/validate.py --sims 50 --set usage.ngs.enabled=true --label "add-ngs"

# Measure marginal impact of a change
uv run python scripts/validate.py --sims 50 --baseline defaults \
    --set usage.ngs.enabled=true --label "ngs-marginal"

# View results history
uv run python scripts/validate.py --show-ledger
```

## How It Works

The script runs two arms in parallel and compares their projection accuracy against historical actuals:

- **Arm A** (baseline): Either `bare` (all engines off) or `defaults` (your defaults.yaml)
- **Arm B** (test): Your defaults.yaml + any `--set` overrides

### Bare vs Defaults Baseline

| Baseline | Arm A is... | Use when... |
|----------|------------|-------------|
| `bare` (default) | All engines off | Measuring total lift of your config |
| `defaults` | Your current defaults.yaml | Isolating marginal impact of a single change |

## CLI Reference

### Core Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--set KEY=VALUE` | (none) | Dot-notation config override for Arm B. Repeatable. |
| `--baseline bare\|defaults` | `bare` | What Arm A runs. |
| `--sims N` | 50 | Monte Carlo sims per game. |
| `--label TEXT` | (none) | Label for ledger entry. Required to save results. |

### Other Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--seasons YEAR...` | 2022 2023 2024 | Test seasons to backtest. |
| `--training-years N` | 4 | Training seasons before each test season. |
| `--scoring FORMAT` | ppr | Scoring format (ppr/half_ppr/standard). |
| `--positions POS...` | QB RB WR TE | Positions to evaluate. |
| `--workers N` | 0 (auto) | Worker processes (0=auto, 1=sequential). |
| `--no-cache` | false | Force fresh bare baseline (skip cache). |
| `--show-ledger` | false | Print ledger and exit. |

## Override Examples

```bash
# Toggle an engine off
--set pff.matchup.enabled=false

# Tune a sensitivity parameter
--set pff.coverage.catch_rate_sensitivity=0.06

# Enable a disabled engine
--set usage.ngs.enabled=true

# Multiple overrides
--set pff.matchup.enabled=false --set weather.enabled=false

# Disable all PFF
--set pff.enabled=false
```

Dot paths follow the structure of `config/defaults.yaml`. Any nested key
can be overridden.

## Bare Baseline Caching

When `--baseline bare`, the script caches Arm A results to `results/cache/`.
On subsequent runs with the same `(season, sims, scoring, training_years)`,
Arm A is loaded from cache — cutting runtime roughly in half.

Cache is valid regardless of defaults.yaml changes (bare = all engines off).

Use `--no-cache` to force a fresh bare baseline.

## Metrics

### Season-Level

- **rank_corr**: Spearman correlation of season-total fantasy points vs actuals, per position
- **weekly_mae**: Mean absolute error of weekly projections
- **season_mae**: Mean absolute error of season totals
- **calibration**: Boom/bust prediction accuracy

### Weekly

- **weekly rank_corr**: Average per-week Spearman correlation
- **weekly MAE**: Average per-week mean absolute error
- **MAE by difficulty**: MAE split by PFF adjustment magnitude (strong/neutral/weak matchups)
- **WR Directional Accuracy**: How often coverage predictions match actual catch rate direction

## Ledger

Results are saved to `results/ab_ledger.json` when `--label` is provided.
View with `--show-ledger`.

Previous results in `results/pff_ab_ledger.json` and `results/weekly_ab_ledger.json`
are preserved but no longer written to.
```

- [ ] **Step 2: Commit**

```bash
git add docs/AB-TESTING.md
git commit -m "docs: add AB-TESTING.md usage guide"
```

---

### Task 7: Update CLAUDE.md

Add the new `validate.py` commands and remove/update references to the old scripts.

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update the Commands section**

In `CLAUDE.md`, find the "Validation scripts" section and replace the old validation commands with:

```markdown
# Validation (A/B testing)
uv run python scripts/validate.py --sims 50 --label "run-name"
uv run python scripts/validate.py --sims 50 --set usage.ngs.enabled=true --label "test-ngs"
uv run python scripts/validate.py --sims 50 --baseline defaults --set usage.ngs.enabled=true
uv run python scripts/validate.py --show-ledger

# Legacy validation scripts (deprecated — use scripts/validate.py)
uv run python scripts/validate_pff_signal.py --mode all --sims 50
uv run python scripts/validate_weekly_signal.py --mode all --sims 50
```

- [ ] **Step 2: Update Architecture section**

Add to the Architecture section under Validation:

```
8. **Validation** (`validation/`) — A/B backtesting with config resolution (`config.py`), bare baseline caching (`cache.py`), unified ledger (`ledger.py`), and metric computation
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with new validate.py commands"
```

---

### Task 8: Deprecation notices in old scripts

Add deprecation warnings to the old scripts so anyone running them knows to switch.

**Files:**
- Modify: `scripts/validate_pff_signal.py` (top of file)
- Modify: `scripts/validate_weekly_signal.py` (top of file)

- [ ] **Step 1: Add deprecation warning to validate_pff_signal.py**

Add at the very top of `main()` in `scripts/validate_pff_signal.py`:

```python
    import warnings
    warnings.warn(
        "validate_pff_signal.py is deprecated. Use scripts/validate.py instead. "
        "See docs/AB-TESTING.md for usage.",
        DeprecationWarning,
        stacklevel=2,
    )
```

- [ ] **Step 2: Add deprecation warning to validate_weekly_signal.py**

Add at the very top of `main()` in `scripts/validate_weekly_signal.py`:

```python
    import warnings
    warnings.warn(
        "validate_weekly_signal.py is deprecated. Use scripts/validate.py instead. "
        "See docs/AB-TESTING.md for usage.",
        DeprecationWarning,
        stacklevel=2,
    )
```

- [ ] **Step 3: Run existing tests to verify no breakage**

Run: `uv run pytest tests/ -x -q`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add scripts/validate_pff_signal.py scripts/validate_weekly_signal.py
git commit -m "chore: add deprecation warnings to old validation scripts"
```

---

### Task 9: Integration smoke test

Verify the full pipeline works end-to-end with a small run.

**Files:** None (manual testing)

- [ ] **Step 1: Run a minimal validation**

Run: `uv run python scripts/validate.py --sims 10 --seasons 2024 --workers 1`

Expected: Script completes without error, prints season-level and weekly results for 2024.

- [ ] **Step 2: Run with cache (second run should be faster)**

Run: `uv run python scripts/validate.py --sims 10 --seasons 2024 --workers 1`

Expected: "bare cache : HIT (2024)" in header. Arm A skipped.

- [ ] **Step 3: Run with an override**

Run: `uv run python scripts/validate.py --sims 10 --seasons 2024 --workers 1 --set pff.matchup.enabled=false --label "no-matchup"`

Expected: Completes, appends to ledger.

- [ ] **Step 4: Verify ledger**

Run: `uv run python scripts/validate.py --show-ledger`

Expected: Table showing the "no-matchup" entry with rank_corr/mae deltas.

- [ ] **Step 5: Run with `--baseline defaults`**

Run: `uv run python scripts/validate.py --sims 10 --seasons 2024 --workers 1 --baseline defaults --set pff.matchup.enabled=false --label "matchup-marginal"`

Expected: Completes. Ledger shows "defaults" baseline for this entry.

- [ ] **Step 6: Run full test suite one final time**

Run: `uv run pytest tests/ -x -q`
Expected: All tests pass (including new tests from Tasks 1-4).

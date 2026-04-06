# Weekly Validation Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a per-week, per-player validation harness that measures whether PFF layers add value at weekly granularity for all positions.

**Architecture:** Validation module (`src/fantasy_sim/validation/weekly.py`) with data structures + metrics + ledger I/O. Standalone script (`scripts/validate_weekly_signal.py`) handles CLI, simulation loop, output. Tests in `tests/test_validation/test_weekly.py`.

**Tech Stack:** Python 3.12+, numpy, scipy (via existing `spearman_rank_correlation`), polars (data loading), argparse (CLI)

**Spec:** `docs/superpowers/specs/2026-04-06-weekly-validation-harness-design.md`

---

## File Map

| File | Responsibility |
|------|---------------|
| `src/fantasy_sim/validation/weekly.py` | **New.** Data structures (`WeeklyPlayerRecord`, `WeeklyPositionSummary`, `DirectionalAccuracyResult`, `WeeklyLedgerEntry`), metric functions (4), ledger I/O (3), 1 internal helper |
| `scripts/validate_weekly_signal.py` | **New.** CLI, PFF config factory, simulation loop, modifier capture, position-factor filtering, output formatting |
| `tests/test_validation/test_weekly.py` | **New.** ~25 unit tests for metrics + ledger. Synthetic data, no network |
| `CLAUDE.md` | **Modify.** Add script usage to Commands section |
| `docs/weekly-validation-notes.md` | **Modify.** Mark as implemented |

---

### Task 1: Data Structures + Construction Tests

**Files:**
- Create: `src/fantasy_sim/validation/weekly.py`
- Create: `tests/test_validation/test_weekly.py`

- [ ] **Step 1: Create weekly.py with all data structures**

```python
# src/fantasy_sim/validation/weekly.py
"""Weekly validation metrics for per-game PFF signal evaluation."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from fantasy_sim.data.actuals import ActualPlayerWeek
from fantasy_sim.data.pff.models import CoverageModifiers
from fantasy_sim.validation.metrics import spearman_rank_correlation

logger = logging.getLogger(__name__)

WEEKLY_LEDGER_PATH = (
    Path(__file__).resolve().parents[3] / "results" / "weekly_ab_ledger.json"
)


@dataclass
class WeeklyPlayerRecord:
    """One player's projection + actual for one week."""

    player_id: str
    name: str
    position: str
    team: str
    week: int
    season: int
    projected_fpts_on: float
    projected_fpts_off: float
    actual_fpts: float
    matchup_factors: dict[str, float] = field(default_factory=dict)
    coverage_modifiers: CoverageModifiers | None = None


@dataclass
class WeeklyPositionSummary:
    """Aggregated weekly metrics for one position."""

    position: str
    weekly_rank_corr_on: float
    weekly_rank_corr_off: float
    weekly_mae_on: float
    weekly_mae_off: float
    mae_by_tercile: dict[str, float]
    n_player_weeks: int
    n_weeks: int


@dataclass
class DirectionalAccuracyResult:
    """WR coverage directional accuracy."""

    total_eligible: int
    correct_direction: int
    accuracy: float


@dataclass
class WeeklyLedgerEntry:
    """One run stored in the weekly ledger."""

    label: str
    timestamp: str
    mode: str
    sims: int
    test_seasons: list[int]
    training_years: int
    position_summaries: list[WeeklyPositionSummary]
    directional_accuracy: DirectionalAccuracyResult | None
```

- [ ] **Step 2: Write construction tests**

```python
# tests/test_validation/test_weekly.py
import pytest
from fantasy_sim.data.pff.models import CoverageModifiers
from fantasy_sim.validation.weekly import (
    WeeklyPlayerRecord,
    WeeklyPositionSummary,
    DirectionalAccuracyResult,
    WeeklyLedgerEntry,
)


def _make_record(
    player_id: str = "P1",
    position: str = "WR",
    week: int = 1,
    season: int = 2024,
    projected_on: float = 10.0,
    projected_off: float = 10.0,
    actual: float = 10.0,
    matchup_factors: dict | None = None,
    coverage_modifiers: CoverageModifiers | None = None,
) -> WeeklyPlayerRecord:
    return WeeklyPlayerRecord(
        player_id=player_id,
        name=f"Player {player_id}",
        position=position,
        team="KC",
        week=week,
        season=season,
        projected_fpts_on=projected_on,
        projected_fpts_off=projected_off,
        actual_fpts=actual,
        matchup_factors=matchup_factors or {},
        coverage_modifiers=coverage_modifiers,
    )


class TestDataStructures:
    def test_weekly_player_record_defaults(self):
        r = _make_record()
        assert r.matchup_factors == {}
        assert r.coverage_modifiers is None

    def test_weekly_player_record_with_coverage(self):
        mods = CoverageModifiers(catch_rate_modifier=0.95, ypr_modifier=1.02)
        r = _make_record(coverage_modifiers=mods)
        assert r.coverage_modifiers.catch_rate_modifier == 0.95
        assert r.coverage_modifiers.ypr_modifier == 1.02

    def test_weekly_player_record_with_matchup_factors(self):
        factors = {"catch_rate_factor": 1.05, "pass_yards_factor": 0.97}
        r = _make_record(matchup_factors=factors)
        assert r.matchup_factors["catch_rate_factor"] == 1.05
        assert len(r.matchup_factors) == 2

    def test_directional_accuracy_result(self):
        dar = DirectionalAccuracyResult(total_eligible=20, correct_direction=12, accuracy=0.6)
        assert dar.accuracy == 0.6
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `uv run pytest tests/test_validation/test_weekly.py -v`
Expected: 4 tests PASS

- [ ] **Step 4: Commit**

```bash
git add src/fantasy_sim/validation/weekly.py tests/test_validation/test_weekly.py
git commit -m "feat(weekly-harness): add data structures and construction tests"
```

---

### Task 2: compute_weekly_rank_corr + Tests

**Files:**
- Modify: `tests/test_validation/test_weekly.py`
- Modify: `src/fantasy_sim/validation/weekly.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_validation/test_weekly.py`:

```python
from fantasy_sim.validation.weekly import compute_weekly_rank_corr


class TestComputeWeeklyRankCorr:
    def test_perfect_correlation_two_weeks(self):
        """Two weeks with 5 WRs each, perfect rank preservation → avg 1.0."""
        records = [
            # Week 1: proj order = actual order
            _make_record("P1", "WR", 1, projected_on=25.0, actual=24.0),
            _make_record("P2", "WR", 1, projected_on=20.0, actual=19.0),
            _make_record("P3", "WR", 1, projected_on=15.0, actual=16.0),
            _make_record("P4", "WR", 1, projected_on=10.0, actual=11.0),
            _make_record("P5", "WR", 1, projected_on=5.0, actual=6.0),
            # Week 2: proj order = actual order
            _make_record("P1", "WR", 2, projected_on=22.0, actual=23.0),
            _make_record("P2", "WR", 2, projected_on=18.0, actual=17.0),
            _make_record("P3", "WR", 2, projected_on=14.0, actual=15.0),
            _make_record("P4", "WR", 2, projected_on=8.0, actual=9.0),
            _make_record("P5", "WR", 2, projected_on=4.0, actual=3.0),
        ]
        corr = compute_weekly_rank_corr(records, "WR", use_pff_on=True)
        assert corr == pytest.approx(1.0)

    def test_week_with_fewer_than_5_players_skipped(self):
        """Weeks with < 5 players should be skipped entirely."""
        records = [
            # Week 1: only 3 players → skipped
            _make_record("P1", "WR", 1, projected_on=20.0, actual=19.0),
            _make_record("P2", "WR", 1, projected_on=15.0, actual=14.0),
            _make_record("P3", "WR", 1, projected_on=10.0, actual=9.0),
            # Week 2: 5 players → included, perfect correlation
            _make_record("P1", "WR", 2, projected_on=25.0, actual=24.0),
            _make_record("P2", "WR", 2, projected_on=20.0, actual=19.0),
            _make_record("P3", "WR", 2, projected_on=15.0, actual=14.0),
            _make_record("P4", "WR", 2, projected_on=10.0, actual=9.0),
            _make_record("P5", "WR", 2, projected_on=5.0, actual=4.0),
        ]
        corr = compute_weekly_rank_corr(records, "WR")
        assert corr == pytest.approx(1.0)

    def test_position_filtering(self):
        """Only records matching the requested position are used."""
        records = [
            # 5 WRs in week 1
            _make_record("W1", "WR", 1, projected_on=25.0, actual=24.0),
            _make_record("W2", "WR", 1, projected_on=20.0, actual=19.0),
            _make_record("W3", "WR", 1, projected_on=15.0, actual=14.0),
            _make_record("W4", "WR", 1, projected_on=10.0, actual=9.0),
            _make_record("W5", "WR", 1, projected_on=5.0, actual=4.0),
            # 3 QBs in week 1 — not enough for QB rank_corr
            _make_record("Q1", "QB", 1, projected_on=30.0, actual=28.0),
            _make_record("Q2", "QB", 1, projected_on=20.0, actual=18.0),
            _make_record("Q3", "QB", 1, projected_on=10.0, actual=8.0),
        ]
        wr_corr = compute_weekly_rank_corr(records, "WR")
        assert wr_corr == pytest.approx(1.0)
        qb_corr = compute_weekly_rank_corr(records, "QB")
        assert qb_corr == 0.0  # no valid weeks → default

    def test_uses_pff_off_projection(self):
        """use_pff_on=False should use projected_fpts_off."""
        records = [
            # PFF-on has wrong order, PFF-off has right order
            _make_record("P1", "WR", 1, projected_on=5.0, projected_off=25.0, actual=24.0),
            _make_record("P2", "WR", 1, projected_on=10.0, projected_off=20.0, actual=19.0),
            _make_record("P3", "WR", 1, projected_on=15.0, projected_off=15.0, actual=14.0),
            _make_record("P4", "WR", 1, projected_on=20.0, projected_off=10.0, actual=9.0),
            _make_record("P5", "WR", 1, projected_on=25.0, projected_off=5.0, actual=4.0),
        ]
        on_corr = compute_weekly_rank_corr(records, "WR", use_pff_on=True)
        off_corr = compute_weekly_rank_corr(records, "WR", use_pff_on=False)
        assert on_corr == pytest.approx(-1.0)
        assert off_corr == pytest.approx(1.0)

    def test_no_valid_weeks_returns_zero(self):
        """No weeks with >= 5 players → 0.0."""
        records = [
            _make_record("P1", "WR", 1, projected_on=10.0, actual=9.0),
            _make_record("P2", "WR", 1, projected_on=5.0, actual=4.0),
        ]
        assert compute_weekly_rank_corr(records, "WR") == 0.0

    def test_empty_records_returns_zero(self):
        assert compute_weekly_rank_corr([], "WR") == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_validation/test_weekly.py::TestComputeWeeklyRankCorr -v`
Expected: FAIL with `ImportError` (function not defined yet)

- [ ] **Step 3: Implement compute_weekly_rank_corr**

Add to `src/fantasy_sim/validation/weekly.py` after the data structures:

```python
def compute_weekly_rank_corr(
    records: list[WeeklyPlayerRecord],
    position: str,
    use_pff_on: bool = True,
) -> float:
    """Average Spearman rank correlation across weeks for one position.

    Groups records by week, computes Spearman per week between projected
    and actual fpts, averages across weeks. Skips weeks with < 5 players.
    """
    pos_records = [r for r in records if r.position == position]
    by_week: dict[int, list[WeeklyPlayerRecord]] = defaultdict(list)
    for r in pos_records:
        by_week[r.week].append(r)

    corrs = []
    for week_records in by_week.values():
        if len(week_records) < 5:
            continue
        projected = [
            r.projected_fpts_on if use_pff_on else r.projected_fpts_off
            for r in week_records
        ]
        actual = [r.actual_fpts for r in week_records]
        corrs.append(spearman_rank_correlation(projected, actual))

    return float(np.mean(corrs)) if corrs else 0.0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_validation/test_weekly.py::TestComputeWeeklyRankCorr -v`
Expected: 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/validation/weekly.py tests/test_validation/test_weekly.py
git commit -m "feat(weekly-harness): add compute_weekly_rank_corr with tests"
```

---

### Task 3: compute_weekly_mae + Tests

**Files:**
- Modify: `tests/test_validation/test_weekly.py`
- Modify: `src/fantasy_sim/validation/weekly.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_validation/test_weekly.py`:

```python
from fantasy_sim.validation.weekly import compute_weekly_mae


class TestComputeWeeklyMae:
    def test_known_mae_two_weeks(self):
        """Two weeks, known errors → verify averaged MAE."""
        records = [
            # Week 1: errors = |12-10|=2, |18-20|=2, |8-10|=2 → MAE=2.0
            _make_record("P1", "WR", 1, projected_on=12.0, actual=10.0),
            _make_record("P2", "WR", 1, projected_on=18.0, actual=20.0),
            _make_record("P3", "WR", 1, projected_on=8.0, actual=10.0),
            # Week 2: errors = |15-10|=5, |25-20|=5, |5-10|=5 → MAE=5.0
            _make_record("P1", "WR", 2, projected_on=15.0, actual=10.0),
            _make_record("P2", "WR", 2, projected_on=25.0, actual=20.0),
            _make_record("P3", "WR", 2, projected_on=5.0, actual=10.0),
        ]
        mae = compute_weekly_mae(records, "WR")
        assert mae == pytest.approx(3.5)  # (2.0 + 5.0) / 2

    def test_single_week(self):
        records = [
            _make_record("P1", "WR", 1, projected_on=12.0, actual=10.0),
            _make_record("P2", "WR", 1, projected_on=18.0, actual=20.0),
        ]
        mae = compute_weekly_mae(records, "WR")
        assert mae == pytest.approx(2.0)

    def test_position_filtering(self):
        records = [
            _make_record("W1", "WR", 1, projected_on=12.0, actual=10.0),
            _make_record("Q1", "QB", 1, projected_on=30.0, actual=10.0),  # QB, ignored for WR
        ]
        mae = compute_weekly_mae(records, "WR")
        assert mae == pytest.approx(2.0)  # only WR's error

    def test_uses_pff_off(self):
        records = [
            _make_record("P1", "WR", 1, projected_on=15.0, projected_off=12.0, actual=10.0),
        ]
        mae_on = compute_weekly_mae(records, "WR", use_pff_on=True)
        mae_off = compute_weekly_mae(records, "WR", use_pff_on=False)
        assert mae_on == pytest.approx(5.0)
        assert mae_off == pytest.approx(2.0)

    def test_empty_records(self):
        assert compute_weekly_mae([], "WR") == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_validation/test_weekly.py::TestComputeWeeklyMae -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement compute_weekly_mae**

Add to `src/fantasy_sim/validation/weekly.py`:

```python
def compute_weekly_mae(
    records: list[WeeklyPlayerRecord],
    position: str,
    use_pff_on: bool = True,
) -> float:
    """Average MAE across weeks for one position.

    Groups records by week, computes MAE per week between projected
    and actual fpts, averages across weeks.
    """
    pos_records = [r for r in records if r.position == position]
    by_week: dict[int, list[WeeklyPlayerRecord]] = defaultdict(list)
    for r in pos_records:
        by_week[r.week].append(r)

    maes = []
    for week_records in by_week.values():
        projected = [
            r.projected_fpts_on if use_pff_on else r.projected_fpts_off
            for r in week_records
        ]
        actual = [r.actual_fpts for r in week_records]
        mae = float(np.mean(np.abs(np.array(projected) - np.array(actual))))
        maes.append(mae)

    return float(np.mean(maes)) if maes else 0.0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_validation/test_weekly.py::TestComputeWeeklyMae -v`
Expected: 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/validation/weekly.py tests/test_validation/test_weekly.py
git commit -m "feat(weekly-harness): add compute_weekly_mae with tests"
```

---

### Task 4: compute_mae_by_difficulty + Tests

**Files:**
- Modify: `tests/test_validation/test_weekly.py`
- Modify: `src/fantasy_sim/validation/weekly.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_validation/test_weekly.py`:

```python
from fantasy_sim.validation.weekly import compute_mae_by_difficulty


class TestComputeMaeByDifficulty:
    def test_nine_records_tercile_split(self):
        """9 records with known magnitudes → 3 per tercile, verify MAE."""
        records = []
        # Strong tercile (mag 0.08, 0.07, 0.06): errors 2, 3, 1 → MAE=2.0
        records.append(_make_record("P1", "WR", 1, projected_on=12.0, actual=10.0,
                                    matchup_factors={"catch_rate_factor": 1.08}))
        records.append(_make_record("P2", "WR", 1, projected_on=13.0, actual=10.0,
                                    matchup_factors={"catch_rate_factor": 1.07}))
        records.append(_make_record("P3", "WR", 1, projected_on=11.0, actual=10.0,
                                    matchup_factors={"catch_rate_factor": 1.06}))
        # Neutral tercile (mag 0.05, 0.04, 0.03): errors 4, 5, 6 → MAE=5.0
        records.append(_make_record("P4", "WR", 2, projected_on=14.0, actual=10.0,
                                    matchup_factors={"catch_rate_factor": 1.05}))
        records.append(_make_record("P5", "WR", 2, projected_on=15.0, actual=10.0,
                                    matchup_factors={"catch_rate_factor": 1.04}))
        records.append(_make_record("P6", "WR", 2, projected_on=16.0, actual=10.0,
                                    matchup_factors={"catch_rate_factor": 1.03}))
        # Weak tercile (mag 0.02, 0.01, 0.00): errors 7, 8, 9 → MAE=8.0
        records.append(_make_record("P7", "WR", 3, projected_on=17.0, actual=10.0,
                                    matchup_factors={"catch_rate_factor": 1.02}))
        records.append(_make_record("P8", "WR", 3, projected_on=18.0, actual=10.0,
                                    matchup_factors={"catch_rate_factor": 1.01}))
        records.append(_make_record("P9", "WR", 3, projected_on=19.0, actual=10.0,
                                    matchup_factors={}))

        result = compute_mae_by_difficulty(records, "WR")
        assert result["strong"] == pytest.approx(2.0)
        assert result["neutral"] == pytest.approx(5.0)
        assert result["weak"] == pytest.approx(8.0)

    def test_coverage_modifiers_included_in_magnitude(self):
        """Coverage modifier with higher deviation should dominate magnitude."""
        mods = CoverageModifiers(catch_rate_modifier=0.90, ypr_modifier=1.0)
        r = _make_record("P1", "WR", 1, projected_on=12.0, actual=10.0,
                         matchup_factors={"catch_rate_factor": 1.02},
                         coverage_modifiers=mods)
        # mag = max(|1.02-1|=0.02, |0.90-1|=0.10, |1.0-1|=0.0) = 0.10
        # We verify indirectly by placing this record among others
        records = [r]
        # Add 5 more with lower magnitude to ensure we have enough for terciles
        for i in range(5):
            records.append(_make_record(f"P{i+2}", "WR", 1, projected_on=10.0, actual=10.0,
                                        matchup_factors={"catch_rate_factor": 1.0 + i * 0.001}))
        result = compute_mae_by_difficulty(records, "WR")
        # P1 (mag=0.10) should be in "strong" tercile
        assert result["strong"] == pytest.approx(2.0)

    def test_all_neutral_modifiers(self):
        """All modifiers at 1.0 → equal terciles with same MAE."""
        records = [
            _make_record(f"P{i}", "WR", 1,
                         projected_on=10.0 + i, actual=10.0,
                         matchup_factors={})
            for i in range(9)
        ]
        result = compute_mae_by_difficulty(records, "WR")
        # All magnitudes 0.0, split arbitrarily → same MAE in each tercile
        assert result["strong"] == pytest.approx(result["weak"], abs=0.01)

    def test_fewer_than_3_records_returns_empty(self):
        records = [
            _make_record("P1", "WR", 1, projected_on=12.0, actual=10.0),
            _make_record("P2", "WR", 1, projected_on=15.0, actual=10.0),
        ]
        assert compute_mae_by_difficulty(records, "WR") == {}

    def test_empty_records(self):
        assert compute_mae_by_difficulty([], "WR") == {}

    def test_position_filtering(self):
        records = [
            _make_record(f"W{i}", "WR", 1, projected_on=10.0 + i, actual=10.0,
                         matchup_factors={"catch_rate_factor": 1.0 + i * 0.01})
            for i in range(6)
        ]
        records.append(_make_record("Q1", "QB", 1, projected_on=30.0, actual=10.0,
                                    matchup_factors={"sack_rate_factor": 1.10}))
        wr_result = compute_mae_by_difficulty(records, "WR")
        assert "strong" in wr_result
        qb_result = compute_mae_by_difficulty(records, "QB")
        assert qb_result == {}  # only 1 QB, < 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_validation/test_weekly.py::TestComputeMaeByDifficulty -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement _get_adjustment_magnitude and compute_mae_by_difficulty**

Add to `src/fantasy_sim/validation/weekly.py`:

```python
def _get_adjustment_magnitude(record: WeeklyPlayerRecord) -> float:
    """Max |factor - 1.0| across matchup_factors and coverage modifiers."""
    deviations = [abs(v - 1.0) for v in record.matchup_factors.values()]
    if record.coverage_modifiers is not None:
        deviations.append(abs(record.coverage_modifiers.catch_rate_modifier - 1.0))
        deviations.append(abs(record.coverage_modifiers.ypr_modifier - 1.0))
    return max(deviations) if deviations else 0.0


def compute_mae_by_difficulty(
    records: list[WeeklyPlayerRecord],
    position: str,
) -> dict[str, float]:
    """MAE split by PFF adjustment magnitude terciles.

    Sorts records by max |factor - 1.0| descending, splits into equal
    thirds. Returns MAE for each tercile using PFF-on projections.
    """
    pos_records = [r for r in records if r.position == position]
    if len(pos_records) < 3:
        return {}

    sorted_records = sorted(
        pos_records, key=_get_adjustment_magnitude, reverse=True
    )
    n = len(sorted_records)
    third = n // 3

    strong = sorted_records[:third]
    weak = sorted_records[n - third:]
    neutral = sorted_records[third : n - third]

    result: dict[str, float] = {}
    for label, group in [("strong", strong), ("neutral", neutral), ("weak", weak)]:
        if group:
            errors = [abs(r.projected_fpts_on - r.actual_fpts) for r in group]
            result[label] = float(np.mean(errors))
            if len(group) < 3:
                logger.warning(
                    "Tercile '%s' has only %d entries for %s",
                    label,
                    len(group),
                    position,
                )

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_validation/test_weekly.py::TestComputeMaeByDifficulty -v`
Expected: 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/validation/weekly.py tests/test_validation/test_weekly.py
git commit -m "feat(weekly-harness): add compute_mae_by_difficulty with tests"
```

---

### Task 5: compute_directional_accuracy + Tests

**Files:**
- Modify: `tests/test_validation/test_weekly.py`
- Modify: `src/fantasy_sim/validation/weekly.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_validation/test_weekly.py`:

```python
from fantasy_sim.data.actuals import ActualPlayerWeek
from fantasy_sim.validation.weekly import compute_directional_accuracy


def _make_actual(
    player_id: str = "P1",
    week: int = 1,
    receptions: int = 5,
    targets: int = 8,
) -> ActualPlayerWeek:
    return ActualPlayerWeek(
        player_id=player_id,
        name=f"Player {player_id}",
        position="WR",
        team="KC",
        season=2024,
        week=week,
        fpts=10.0,
        receptions=receptions,
        targets=targets,
    )


class TestComputeDirectionalAccuracy:
    def test_tough_cb_catch_rate_drops_correct(self):
        """Modifier < 1.0, actual catch rate below season avg → correct."""
        mods = CoverageModifiers(catch_rate_modifier=0.95, ypr_modifier=1.0)
        records = [_make_record("P1", "WR", 3, coverage_modifiers=mods)]
        actuals = {
            "P1": [
                _make_actual("P1", 1, receptions=6, targets=8),   # 0.750
                _make_actual("P1", 2, receptions=5, targets=8),   # 0.625
                _make_actual("P1", 3, receptions=3, targets=8),   # 0.375 (this week)
            ],
        }
        # Leave-one-out avg: (6+5)/(8+8) = 11/16 = 0.6875
        # This week: 3/8 = 0.375 < 0.6875 → correct
        result = compute_directional_accuracy(records, actuals)
        assert result.total_eligible == 1
        assert result.correct_direction == 1
        assert result.accuracy == pytest.approx(1.0)

    def test_weak_cb_catch_rate_rises_correct(self):
        """Modifier > 1.0, actual catch rate above season avg → correct."""
        mods = CoverageModifiers(catch_rate_modifier=1.05, ypr_modifier=1.0)
        records = [_make_record("P1", "WR", 3, coverage_modifiers=mods)]
        actuals = {
            "P1": [
                _make_actual("P1", 1, receptions=4, targets=8),   # 0.500
                _make_actual("P1", 2, receptions=4, targets=8),   # 0.500
                _make_actual("P1", 3, receptions=7, targets=8),   # 0.875 (this week)
            ],
        }
        # Leave-one-out avg: (4+4)/(8+8) = 8/16 = 0.500
        # This week: 7/8 = 0.875 > 0.500 → correct
        result = compute_directional_accuracy(records, actuals)
        assert result.correct_direction == 1

    def test_tough_cb_catch_rate_rises_incorrect(self):
        """Modifier < 1.0, actual catch rate above season avg → incorrect."""
        mods = CoverageModifiers(catch_rate_modifier=0.95, ypr_modifier=1.0)
        records = [_make_record("P1", "WR", 3, coverage_modifiers=mods)]
        actuals = {
            "P1": [
                _make_actual("P1", 1, receptions=4, targets=8),
                _make_actual("P1", 2, receptions=4, targets=8),
                _make_actual("P1", 3, receptions=7, targets=8),   # rose despite tough CB
            ],
        }
        result = compute_directional_accuracy(records, actuals)
        assert result.total_eligible == 1
        assert result.correct_direction == 0

    def test_below_min_targets_excluded(self):
        """Weekly targets < 4 → excluded."""
        mods = CoverageModifiers(catch_rate_modifier=0.95, ypr_modifier=1.0)
        records = [_make_record("P1", "WR", 3, coverage_modifiers=mods)]
        actuals = {
            "P1": [
                _make_actual("P1", 1, receptions=4, targets=8),
                _make_actual("P1", 2, receptions=4, targets=8),
                _make_actual("P1", 3, receptions=1, targets=3),   # only 3 targets
            ],
        }
        result = compute_directional_accuracy(records, actuals, min_weekly_targets=4)
        assert result.total_eligible == 0

    def test_modifier_in_dead_zone_excluded(self):
        """Modifier within 0.01 of 1.0 → excluded."""
        mods = CoverageModifiers(catch_rate_modifier=1.005, ypr_modifier=1.0)
        records = [_make_record("P1", "WR", 3, coverage_modifiers=mods)]
        actuals = {
            "P1": [
                _make_actual("P1", 1, receptions=4, targets=8),
                _make_actual("P1", 2, receptions=4, targets=8),
                _make_actual("P1", 3, receptions=6, targets=8),
            ],
        }
        result = compute_directional_accuracy(records, actuals)
        assert result.total_eligible == 0

    def test_no_coverage_modifiers_excluded(self):
        """Records without coverage_modifiers → excluded."""
        records = [_make_record("P1", "WR", 1)]
        result = compute_directional_accuracy(records, {"P1": [_make_actual()]})
        assert result.total_eligible == 0

    def test_non_wr_excluded(self):
        """Non-WR records → excluded even with coverage_modifiers."""
        mods = CoverageModifiers(catch_rate_modifier=0.95, ypr_modifier=1.0)
        records = [_make_record("P1", "RB", 1, coverage_modifiers=mods)]
        result = compute_directional_accuracy(records, {"P1": [_make_actual()]})
        assert result.total_eligible == 0

    def test_zero_eligible_returns_zero_accuracy(self):
        result = compute_directional_accuracy([], {})
        assert result == DirectionalAccuracyResult(0, 0, 0.0)

    def test_leave_one_out_two_weeks(self):
        """WR with 2 total weeks: baseline is 1 week of data."""
        mods = CoverageModifiers(catch_rate_modifier=0.90, ypr_modifier=1.0)
        records = [_make_record("P1", "WR", 2, coverage_modifiers=mods)]
        actuals = {
            "P1": [
                _make_actual("P1", 1, receptions=6, targets=8),   # baseline: 0.750
                _make_actual("P1", 2, receptions=3, targets=8),   # this week: 0.375
            ],
        }
        # 0.375 < 0.750, modifier < 1.0 → correct
        result = compute_directional_accuracy(records, actuals)
        assert result.total_eligible == 1
        assert result.correct_direction == 1

    def test_leave_one_out_one_week_skipped(self):
        """WR with only 1 total week: baseline has 0 targets → skipped."""
        mods = CoverageModifiers(catch_rate_modifier=0.90, ypr_modifier=1.0)
        records = [_make_record("P1", "WR", 1, coverage_modifiers=mods)]
        actuals = {
            "P1": [_make_actual("P1", 1, receptions=3, targets=8)],
        }
        result = compute_directional_accuracy(records, actuals)
        assert result.total_eligible == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_validation/test_weekly.py::TestComputeDirectionalAccuracy -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement compute_directional_accuracy**

Add to `src/fantasy_sim/validation/weekly.py`:

```python
def compute_directional_accuracy(
    records: list[WeeklyPlayerRecord],
    actuals_by_player: dict[str, list[ActualPlayerWeek]],
    min_weekly_targets: int = 4,
) -> DirectionalAccuracyResult:
    """WR directional accuracy: did actual catch rate move as coverage predicted?

    For each WR-week with a meaningful coverage modifier (|mod - 1.0| > 0.01),
    checks whether the actual catch rate moved in the predicted direction
    relative to the WR's leave-one-out season average.
    """
    total = 0
    correct = 0

    for record in records:
        if record.position != "WR":
            continue
        if record.coverage_modifiers is None:
            continue
        mod = record.coverage_modifiers.catch_rate_modifier
        if abs(mod - 1.0) <= 0.01:
            continue

        player_actuals = actuals_by_player.get(record.player_id, [])
        if not player_actuals:
            continue

        # Find this week's actual
        this_week = None
        for a in player_actuals:
            if a.week == record.week:
                this_week = a
                break
        if this_week is None or this_week.targets < min_weekly_targets:
            continue

        # Leave-one-out season average catch rate
        other_weeks = [a for a in player_actuals if a.week != record.week]
        baseline_targets = sum(a.targets for a in other_weeks)
        if baseline_targets == 0:
            continue
        baseline_receptions = sum(a.receptions for a in other_weeks)
        season_avg_cr = baseline_receptions / baseline_targets

        # This week's catch rate
        weekly_cr = this_week.receptions / this_week.targets

        # Check direction
        if mod < 1.0:
            if weekly_cr < season_avg_cr:
                correct += 1
        else:
            if weekly_cr > season_avg_cr:
                correct += 1

        total += 1

    accuracy = correct / total if total > 0 else 0.0
    return DirectionalAccuracyResult(
        total_eligible=total,
        correct_direction=correct,
        accuracy=accuracy,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_validation/test_weekly.py::TestComputeDirectionalAccuracy -v`
Expected: 10 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/validation/weekly.py tests/test_validation/test_weekly.py
git commit -m "feat(weekly-harness): add compute_directional_accuracy with tests"
```

---

### Task 6: Ledger I/O + Tests

**Files:**
- Modify: `tests/test_validation/test_weekly.py`
- Modify: `src/fantasy_sim/validation/weekly.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_validation/test_weekly.py`:

```python
from fantasy_sim.validation.weekly import (
    WeeklyLedgerEntry,
    WeeklyPositionSummary,
    load_weekly_ledger,
    save_weekly_ledger,
    format_weekly_progression_table,
)


def _make_entry(label: str = "test-run") -> WeeklyLedgerEntry:
    return WeeklyLedgerEntry(
        label=label,
        timestamp="2026-04-06T12:00:00",
        mode="all",
        sims=50,
        test_seasons=[2023, 2024],
        training_years=2,
        position_summaries=[
            WeeklyPositionSummary(
                position="WR",
                weekly_rank_corr_on=0.85,
                weekly_rank_corr_off=0.82,
                weekly_mae_on=5.5,
                weekly_mae_off=5.8,
                mae_by_tercile={"strong": 4.0, "neutral": 5.5, "weak": 7.0},
                n_player_weeks=500,
                n_weeks=17,
            ),
        ],
        directional_accuracy=DirectionalAccuracyResult(
            total_eligible=200,
            correct_direction=120,
            accuracy=0.60,
        ),
    )


class TestWeeklyLedger:
    def test_round_trip(self, tmp_path):
        path = tmp_path / "test_ledger.json"
        entries = [_make_entry("run-1"), _make_entry("run-2")]
        save_weekly_ledger(path, entries)
        loaded = load_weekly_ledger(path)
        assert len(loaded) == 2
        assert loaded[0].label == "run-1"
        assert loaded[1].label == "run-2"
        ps = loaded[0].position_summaries[0]
        assert ps.position == "WR"
        assert ps.weekly_rank_corr_on == pytest.approx(0.85)
        assert ps.mae_by_tercile["strong"] == pytest.approx(4.0)
        da = loaded[0].directional_accuracy
        assert da is not None
        assert da.accuracy == pytest.approx(0.60)

    def test_load_nonexistent_returns_empty(self, tmp_path):
        path = tmp_path / "nonexistent.json"
        assert load_weekly_ledger(path) == []

    def test_round_trip_no_directional_accuracy(self, tmp_path):
        path = tmp_path / "test_ledger.json"
        entry = _make_entry()
        entry.directional_accuracy = None
        save_weekly_ledger(path, [entry])
        loaded = load_weekly_ledger(path)
        assert loaded[0].directional_accuracy is None

    def test_format_empty_ledger(self):
        output = format_weekly_progression_table([])
        assert "No entries" in output

    def test_format_one_entry(self):
        output = format_weekly_progression_table([_make_entry("baseline")])
        assert "baseline" in output
        assert "WR" not in output or "0.60" in output or "60" in output

    def test_format_multiple_entries(self):
        entries = [_make_entry("run-1"), _make_entry("run-2")]
        output = format_weekly_progression_table(entries)
        assert "run-1" in output
        assert "run-2" in output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_validation/test_weekly.py::TestWeeklyLedger -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement ledger I/O functions**

Add to `src/fantasy_sim/validation/weekly.py`:

```python
def load_weekly_ledger(
    path: Path = WEEKLY_LEDGER_PATH,
) -> list[WeeklyLedgerEntry]:
    """Load weekly ledger entries from JSON."""
    if not path.exists():
        return []
    with open(path) as f:
        raw = json.load(f)
    entries = []
    for item in raw:
        pos_summaries = [
            WeeklyPositionSummary(**ps) for ps in item.get("position_summaries", [])
        ]
        da_raw = item.get("directional_accuracy")
        da = DirectionalAccuracyResult(**da_raw) if da_raw else None
        item = dict(item)
        item["position_summaries"] = pos_summaries
        item["directional_accuracy"] = da
        entries.append(WeeklyLedgerEntry(**item))
    return entries


def save_weekly_ledger(
    path: Path,
    entries: list[WeeklyLedgerEntry],
) -> None:
    """Write weekly ledger entries to JSON."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump([asdict(e) for e in entries], f, indent=2)


def format_weekly_progression_table(
    entries: list[WeeklyLedgerEntry],
) -> str:
    """Return an ASCII table of weekly ledger entries."""
    if not entries:
        return "No entries in weekly ledger."

    positions = ("QB", "RB", "WR", "TE")
    header = f"{'#':>3}  {'Label':<25}  "
    header += "  ".join(f"{p}_rc" for p in positions)
    header += "  "
    header += "  ".join(f"{p}_mae" for p in positions)
    header += "  dir_acc"
    sep = "-" * len(header)
    lines = [sep, header, sep]

    for i, e in enumerate(entries, start=1):
        pos_data = {ps.position: ps for ps in e.position_summaries}
        parts = [f"{i:>3}  {e.label:<25}"]

        # Rank corr deltas
        for pos in positions:
            ps = pos_data.get(pos)
            if ps:
                delta = ps.weekly_rank_corr_on - ps.weekly_rank_corr_off
                parts.append(f"{delta:>+.4f}")
            else:
                parts.append(f"{'n/a':>7}")

        # MAE deltas
        for pos in positions:
            ps = pos_data.get(pos)
            if ps:
                delta = ps.weekly_mae_on - ps.weekly_mae_off
                parts.append(f"{delta:>+.3f}")
            else:
                parts.append(f"{'n/a':>7}")

        # Directional accuracy
        if e.directional_accuracy:
            parts.append(f"{e.directional_accuracy.accuracy:.1%}")
        else:
            parts.append("n/a")

        lines.append("  ".join(parts))

    lines.append(sep)
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_validation/test_weekly.py::TestWeeklyLedger -v`
Expected: 6 tests PASS

- [ ] **Step 5: Run full test suite for weekly.py**

Run: `uv run pytest tests/test_validation/test_weekly.py -v`
Expected: All tests PASS (~31 tests)

- [ ] **Step 6: Commit**

```bash
git add src/fantasy_sim/validation/weekly.py tests/test_validation/test_weekly.py
git commit -m "feat(weekly-harness): add ledger I/O with tests"
```

---

### Task 7: Script Orchestration

**Files:**
- Create: `scripts/validate_weekly_signal.py`

This task creates the standalone CLI script. No automated tests — validated by running with `--help` and reviewing output structure.

- [ ] **Step 1: Create script with imports, constants, and PFF config factory**

Create `scripts/validate_weekly_signal.py`. The `_build_pff_config` function is copied from `scripts/validate_pff_signal.py` (scripts are standalone, not importable packages).

```python
"""Weekly A/B validation: per-week, per-player PFF signal evaluation.

Retains weekly granularity instead of aggregating to season-level metrics.
Measures per-position rank_corr, MAE, MAE by matchup difficulty, and
WR directional accuracy for coverage signal.

Usage:
    uv run python scripts/validate_weekly_signal.py --help
    uv run python scripts/validate_weekly_signal.py --mode all --sims 50
    uv run python scripts/validate_weekly_signal.py --mode coverage+tier --positions WR
    uv run python scripts/validate_weekly_signal.py --show-ledger
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import zlib
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from fantasy_sim.config.loader import load_defaults, resolve_scoring
from fantasy_sim.data.actuals import load_actual_scores
from fantasy_sim.data.game_context import GameContextBuilder
from fantasy_sim.data.loader import DataLoader
from fantasy_sim.data.pff.models import (
    CoverageConfig,
    MatchupConfig,
    MatchupContext,
    PffConfig,
    TalentConfig,
    TeamContextConfig,
    TierConfig,
)
from fantasy_sim.engine.monte_carlo import run_simulations
from fantasy_sim.scoring.projections import build_player_projections
from fantasy_sim.validation.weekly import (
    DirectionalAccuracyResult,
    WeeklyLedgerEntry,
    WeeklyPlayerRecord,
    WeeklyPositionSummary,
    compute_directional_accuracy,
    compute_mae_by_difficulty,
    compute_weekly_mae,
    compute_weekly_rank_corr,
    format_weekly_progression_table,
    load_weekly_ledger,
    save_weekly_ledger,
)

import polars as pl

POSITIONS = ("QB", "RB", "WR", "TE")

WEEKLY_LEDGER_PATH = Path(__file__).parent.parent / "results" / "weekly_ab_ledger.json"

# Position -> applicable MatchupContext fields
POSITION_MATCHUP_FACTORS: dict[str, tuple[str, ...]] = {
    "QB": ("sack_rate_factor", "int_rate_factor", "ol_pass_block_factor"),
    "RB": ("rush_yards_factor", "ol_run_block_factor"),
    "WR": ("catch_rate_factor", "pass_yards_factor"),
    "TE": ("catch_rate_factor", "pass_yards_factor"),
}
```

Copy `_build_pff_config` from `scripts/validate_pff_signal.py` verbatim (lines 212-341). This is the mode-to-PffConfig mapping function with all override handling.

- [ ] **Step 2: Add the matchup factor filter helper**

```python
def _filter_matchup_factors(
    position: str, ctx: MatchupContext
) -> dict[str, float]:
    """Filter MatchupContext to position-relevant factors."""
    fields = POSITION_MATCHUP_FACTORS.get(position, ())
    return {f: getattr(ctx, f) for f in fields}
```

- [ ] **Step 3: Implement run_weekly_comparison**

```python
def run_weekly_comparison(
    test_season: int,
    n_sims: int,
    scoring_config: dict,
    num_training_seasons: int,
    pff_config: PffConfig,
    positions: list[str],
) -> list[WeeklyPlayerRecord]:
    """Run PFF-on vs PFF-off for every game in a season, collect per-player records."""

    training_seasons = list(range(
        test_season - num_training_seasons, test_season
    ))
    loader = DataLoader()
    schedules = loader.load_schedules([test_season])
    player_stats = loader.load_player_stats([test_season])

    actuals = load_actual_scores(player_stats, scoring_config, test_season)
    actual_by_pw: dict[str, dict[int, float]] = defaultdict(dict)
    actual_pos: dict[str, str] = {}
    actual_team: dict[str, str] = {}
    actual_name: dict[str, str] = {}
    for a in actuals:
        actual_by_pw[a.player_id][a.week] = a.fpts
        actual_pos[a.player_id] = a.position
        actual_team[a.player_id] = a.team
        actual_name[a.player_id] = a.name

    builder_off = GameContextBuilder(cache_dir=loader.cache_dir)
    builder_on = GameContextBuilder(cache_dir=loader.cache_dir, pff_config=pff_config)

    weeks = sorted(
        schedules.filter(pl.col("season") == test_season)["week"]
        .unique().to_list()
    )
    weeks = [w for w in weeks if 1 <= w <= 18]

    records: list[WeeklyPlayerRecord] = []

    for wk in weeks:
        week_games = schedules.filter(
            (pl.col("week") == wk) & (pl.col("season") == test_season)
        )
        print(f"    Week {wk}: {week_games.height} games...", end="", flush=True)

        for game in week_games.iter_rows(named=True):
            home, away = game["home_team"], game["away_team"]
            try:
                seed = zlib.crc32(game["game_id"].encode()) % (2**31)

                # PFF-off
                hd_off, ad_off, hr_off, ar_off = builder_off.build_game(
                    home, away,
                    training_seasons=training_seasons,
                    target_season=test_season, week=wk,
                )
                results_off = run_simulations(
                    hd_off, ad_off, n_sims=n_sims, seed=seed,
                    home_roster=hr_off, away_roster=ar_off, week=wk,
                )
                projs_off = build_player_projections(results_off.games, scoring_config)

                # PFF-on
                hd_on, ad_on, hr_on, ar_on = builder_on.build_game(
                    home, away,
                    training_seasons=training_seasons,
                    target_season=test_season, week=wk,
                )
                results_on = run_simulations(
                    hd_on, ad_on, n_sims=n_sims, seed=seed,
                    home_roster=hr_on, away_roster=ar_on, week=wk,
                )
                projs_on = build_player_projections(results_on.games, scoring_config)

                # Capture modifiers from PFF-on builder (cached, cheap)
                home_matchup_ctx = MatchupContext()
                away_matchup_ctx = MatchupContext()
                if builder_on._matchup_engine is not None:
                    home_matchup_ctx = builder_on._matchup_engine.compute(
                        defense_team=away, offense_team=home,
                        target_season=test_season, max_week=wk,
                    )
                    away_matchup_ctx = builder_on._matchup_engine.compute(
                        defense_team=home, offense_team=away,
                        target_season=test_season, max_week=wk,
                    )

                home_coverage: dict[str, object] = {}
                away_coverage: dict[str, object] = {}
                if builder_on._coverage_engine is not None:
                    home_coverage = builder_on._coverage_engine.compute(
                        defense_team=away, offense_roster=hr_on,
                        target_season=test_season, max_week=wk,
                        pff_crosswalk=builder_on._pff_crosswalk,
                    )
                    away_coverage = builder_on._coverage_engine.compute(
                        defense_team=home, offense_roster=ar_on,
                        target_season=test_season, max_week=wk,
                        pff_crosswalk=builder_on._pff_crosswalk,
                    )

                # Index PFF-off projections by player_id
                off_by_pid = {p["player_id"]: p["fpts"] for p in projs_off}

                # Build records from PFF-on projections
                for proj in projs_on:
                    pid = proj["player_id"]
                    pos = proj.get("position") or actual_pos.get(pid, "")
                    if pos not in positions:
                        continue
                    if pid not in actual_by_pw or wk not in actual_by_pw[pid]:
                        continue

                    team = proj.get("team") or actual_team.get(pid, "")
                    is_home = team == home

                    matchup_ctx = home_matchup_ctx if is_home else away_matchup_ctx
                    cov_map = home_coverage if is_home else away_coverage

                    records.append(WeeklyPlayerRecord(
                        player_id=pid,
                        name=proj.get("name") or actual_name.get(pid, ""),
                        position=pos,
                        team=team,
                        week=wk,
                        season=test_season,
                        projected_fpts_on=proj["fpts"],
                        projected_fpts_off=off_by_pid.get(pid, 0.0),
                        actual_fpts=actual_by_pw[pid][wk],
                        matchup_factors=_filter_matchup_factors(pos, matchup_ctx),
                        coverage_modifiers=cov_map.get(pid) if pos == "WR" else None,
                    ))

            except Exception:
                continue

        print(f" {len(records)} records total")

    return records
```

- [ ] **Step 4: Implement main() with CLI parsing and output**

```python
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Weekly A/B validation: per-week PFF signal evaluation.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--mode",
        choices=[
            "matchup", "talent", "tier", "matchup+tier",
            "team_context+tier", "team_context+tier+matchup",
            "ncaa_rookie+tier", "ncaa_rookie+tier+matchup",
            "coverage+tier", "coverage+tier+matchup", "all",
        ],
        default="all",
        help="Which PFF layer(s) to enable (default: all).",
    )
    parser.add_argument("--sims", type=int, default=50, help="Sims per game (default: 50).")
    parser.add_argument("--seasons", type=int, nargs="+", default=[2023, 2024], help="Test seasons.")
    parser.add_argument("--training-years", type=int, default=2, dest="training_years")
    parser.add_argument("--scoring", default="ppr", choices=["ppr", "half_ppr", "standard"])
    parser.add_argument("--positions", nargs="+", default=list(POSITIONS), help="Positions to evaluate.")
    parser.add_argument("--label", type=str, default=None, help="Label for ledger entry.")
    parser.add_argument("--show-ledger", action="store_true", help="Print ledger and exit.")
    parser.add_argument("--config-override", type=str, default=None, dest="config_override")

    args = parser.parse_args()

    if args.show_ledger:
        entries = load_weekly_ledger(WEEKLY_LEDGER_PATH)
        print(format_weekly_progression_table(entries))
        return 0

    overrides = json.loads(args.config_override) if args.config_override else None
    pff_config = _build_pff_config(args.mode, overrides=overrides)

    print("=" * 68)
    print("  WEEKLY PFF SIGNAL VALIDATION")
    print("=" * 68)
    print(f"  mode          : {args.mode}")
    print(f"  sims          : {args.sims}")
    print(f"  seasons       : {args.seasons}")
    print(f"  positions     : {args.positions}")
    print(f"  training_years: {args.training_years}")
    if args.label:
        print(f"  label         : {args.label}")
    print("=" * 68)

    defaults = load_defaults()
    scoring_config = resolve_scoring(defaults["scoring"], args.scoring)

    total_start = time.time()
    all_records: list[WeeklyPlayerRecord] = []

    if len(args.seasons) > 1:
        from concurrent.futures import ProcessPoolExecutor, as_completed

        print(f"\nRunning {len(args.seasons)} seasons in parallel...")
        with ProcessPoolExecutor(max_workers=len(args.seasons)) as pool:
            futures = {
                pool.submit(
                    run_weekly_comparison,
                    test_season=season,
                    n_sims=args.sims,
                    scoring_config=scoring_config,
                    num_training_seasons=args.training_years,
                    pff_config=pff_config,
                    positions=args.positions,
                ): season
                for season in args.seasons
            }
            for future in as_completed(futures):
                season_records = future.result()
                all_records.extend(season_records)
                print(f"  Season {futures[future]}: {len(season_records)} records")
    else:
        for season in args.seasons:
            print(f"\n  [Season {season}]")
            season_records = run_weekly_comparison(
                test_season=season,
                n_sims=args.sims,
                scoring_config=scoring_config,
                num_training_seasons=args.training_years,
                pff_config=pff_config,
                positions=args.positions,
            )
            all_records.extend(season_records)

    total_elapsed = time.time() - total_start
    print(f"\nTotal time: {total_elapsed:.1f}s  |  {len(all_records)} player-week records")

    # Compute summaries
    print("\n" + "=" * 68)
    print("  WEEKLY RESULTS")
    print("=" * 68)

    summaries: list[WeeklyPositionSummary] = []
    for pos in args.positions:
        pos_records = [r for r in all_records if r.position == pos]
        if not pos_records:
            continue

        rc_on = compute_weekly_rank_corr(all_records, pos, use_pff_on=True)
        rc_off = compute_weekly_rank_corr(all_records, pos, use_pff_on=False)
        mae_on = compute_weekly_mae(all_records, pos, use_pff_on=True)
        mae_off = compute_weekly_mae(all_records, pos, use_pff_on=False)
        tercile = compute_mae_by_difficulty(all_records, pos)
        n_weeks = len({r.week for r in pos_records})

        summary = WeeklyPositionSummary(
            position=pos,
            weekly_rank_corr_on=rc_on,
            weekly_rank_corr_off=rc_off,
            weekly_mae_on=mae_on,
            weekly_mae_off=mae_off,
            mae_by_tercile=tercile,
            n_player_weeks=len(pos_records),
            n_weeks=n_weeks,
        )
        summaries.append(summary)

        rc_delta = rc_on - rc_off
        mae_delta = mae_on - mae_off
        print(f"\n  {pos}  ({len(pos_records)} player-weeks, {n_weeks} weeks)")
        print(f"    rank_corr: {rc_off:.4f} -> {rc_on:.4f}  (delta={rc_delta:+.4f})")
        print(f"    weekly_mae: {mae_off:.3f} -> {mae_on:.3f}  (delta={mae_delta:+.3f})")
        if tercile:
            print(f"    mae_by_difficulty: strong={tercile.get('strong', 0):.3f}  "
                  f"neutral={tercile.get('neutral', 0):.3f}  "
                  f"weak={tercile.get('weak', 0):.3f}")

    # Directional accuracy (WR only)
    dir_accuracy = None
    if "WR" in args.positions:
        actuals_by_player: dict[str, list] = defaultdict(list)
        for season in args.seasons:
            loader = DataLoader()
            player_stats = loader.load_player_stats([season])
            season_actuals = load_actual_scores(player_stats, scoring_config, season)
            for a in season_actuals:
                actuals_by_player[a.player_id].append(a)

        dir_accuracy = compute_directional_accuracy(all_records, actuals_by_player)
        print(f"\n  WR Directional Accuracy: {dir_accuracy.correct_direction}/{dir_accuracy.total_eligible} "
              f"= {dir_accuracy.accuracy:.1%}")

    print("\n" + "=" * 68)

    # Save to ledger
    if args.label:
        entry = WeeklyLedgerEntry(
            label=args.label,
            timestamp=datetime.now().isoformat(timespec="seconds"),
            mode=args.mode,
            sims=args.sims,
            test_seasons=args.seasons,
            training_years=args.training_years,
            position_summaries=summaries,
            directional_accuracy=dir_accuracy,
        )
        ledger = load_weekly_ledger(WEEKLY_LEDGER_PATH)
        ledger.append(entry)
        save_weekly_ledger(WEEKLY_LEDGER_PATH, ledger)
        print(f"\n  Appended to weekly ledger as #{len(ledger)}: {args.label}")
        print(format_weekly_progression_table(ledger))

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Verify script runs with --help**

Run: `uv run python scripts/validate_weekly_signal.py --help`
Expected: Help text with all flags listed

- [ ] **Step 6: Verify --show-ledger works (empty ledger)**

Run: `uv run python scripts/validate_weekly_signal.py --show-ledger`
Expected: "No entries in weekly ledger."

- [ ] **Step 7: Commit**

```bash
git add scripts/validate_weekly_signal.py
git commit -m "feat(weekly-harness): add validation script with CLI and simulation loop"
```

---

### Task 8: Documentation Updates

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/weekly-validation-notes.md`

- [ ] **Step 1: Add script commands to CLAUDE.md**

In the `## Commands` section, after the existing `validate_pff_signal.py` entries, add:

```bash
# Weekly PFF validation (per-week granularity, all positions)
uv run python scripts/validate_weekly_signal.py --mode all --sims 50
uv run python scripts/validate_weekly_signal.py --mode coverage+tier --positions WR --sims 50
uv run python scripts/validate_weekly_signal.py --show-ledger
uv run python scripts/validate_weekly_signal.py --mode all --sims 50 --label "weekly-baseline"
```

- [ ] **Step 2: Update CLAUDE.md Current State section**

Add to the end of the Current State list:

```
- **Weekly Validation Harness**: Complete — scripts/validate_weekly_signal.py with per-week metrics (rank_corr, MAE, MAE by difficulty, WR directional accuracy). Separate ledger at results/weekly_ab_ledger.json.
```

Update the test count to reflect the new tests added.

- [ ] **Step 3: Update weekly-validation-notes.md**

Add at the top of `docs/weekly-validation-notes.md`:

```markdown
**Status:** Implemented — see `scripts/validate_weekly_signal.py`

**Validation module:** `src/fantasy_sim/validation/weekly.py`
**Tests:** `tests/test_validation/test_weekly.py`
**Ledger:** `results/weekly_ab_ledger.json`
```

- [ ] **Step 4: Run full test suite**

Run: `uv run pytest tests/ -v --tb=short`
Expected: All existing tests + ~31 new tests PASS

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md docs/weekly-validation-notes.md
git commit -m "docs: add weekly validation harness commands and mark notes as implemented"
```

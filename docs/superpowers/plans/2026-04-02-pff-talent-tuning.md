# PFF Talent Tuning Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Push the PFF talent stabilizer from SOFT_PASS to PASS by empirically fitting coefficients, optimizing hyperparameters, adding new stabilization targets, and building NCAA rookie priors — with a persistent A/B ledger tracking every change.

**Architecture:** Sequential integration of 7 independently-developed improvements, each A/B tested before proceeding. Phase 0 builds the harness. Phases 1-2 develop 3 improvements in parallel (worktrees), integrate one at a time. Phase 3 builds NCAA priors + final sweep.

**Tech Stack:** Python 3.14, polars, numpy (OLS via lstsq), pytest, YAML config

**Spec:** `docs/superpowers/specs/2026-04-02-pff-talent-tuning-design.md`

---

## File Structure

**New files:**
- `scripts/fit_talent_coefficients.py` — OLS regression script for PFF→PBP coefficient fitting
- `scripts/sweep_talent_params.py` — Grid search over prior_strength × min_divergence
- `results/.gitkeep` — Results directory (gitignored except .gitkeep)
- `tests/test_scripts/test_fit_coefficients.py` — Tests for regression logic
- `tests/test_scripts/test_sweep.py` — Tests for sweep grid logic

**Modified files:**
- `scripts/validate_pff_signal.py` — Add ledger, --label, --show-ledger, --config-override
- `src/fantasy_sim/validation/backtester.py` — Accept pff_config param
- `src/fantasy_sim/data/pff/talent.py` — Additional params, pos-specific strength, team-change, schedule adj
- `src/fantasy_sim/data/pff/models.py` — New TalentConfig fields
- `src/fantasy_sim/data/pff/config.py` — Parse new config fields
- `src/fantasy_sim/data/pff/loader.py` — NCAA facet loading + crosswalk
- `config/defaults.yaml` — New config sections
- `.gitignore` — Add results/
- `tests/test_data/test_pff/test_talent.py` — New stabilization tests
- `tests/test_data/test_pff/test_config.py` — New config parsing tests
- `tests/test_data/test_pff/test_loader.py` — NCAA loader tests
- `tests/test_validation/test_backtester.py` — pff_config param tests

---

## Phase 0: A/B Harness Foundation

### Task 1: Add pff_config to Backtester

**Files:**
- Modify: `src/fantasy_sim/validation/backtester.py`
- Test: `tests/test_validation/test_backtester.py`

- [ ] **Step 1: Write test for pff_config param**

In `tests/test_validation/test_backtester.py`, add:

```python
class TestBacktesterPffConfig:
    @patch("fantasy_sim.validation.backtester.GameContextBuilder")
    @patch("fantasy_sim.validation.backtester.DataLoader")
    def test_pff_config_passed_to_builder(self, mock_loader_cls, mock_builder_cls):
        from fantasy_sim.data.pff.models import PffConfig, TalentConfig
        pff_cfg = PffConfig(enabled=True, talent=TalentConfig(enabled=True))
        mock_loader = MagicMock()
        mock_loader_cls.return_value = mock_loader
        mock_loader.cache_dir = "/tmp/test"

        Backtester(test_season=2024, n_sims=10, pff_config=pff_cfg)

        mock_builder_cls.assert_called_once_with(
            cache_dir="/tmp/test",
            pff_config=pff_cfg,
        )

    @patch("fantasy_sim.validation.backtester.GameContextBuilder")
    @patch("fantasy_sim.validation.backtester.DataLoader")
    def test_no_pff_config_passes_none(self, mock_loader_cls, mock_builder_cls):
        mock_loader = MagicMock()
        mock_loader_cls.return_value = mock_loader
        mock_loader.cache_dir = "/tmp/test"

        Backtester(test_season=2024, n_sims=10)

        call_kwargs = mock_builder_cls.call_args[1]
        assert call_kwargs.get("pff_config") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_validation/test_backtester.py::TestBacktesterPffConfig -v`
Expected: FAIL — Backtester doesn't accept pff_config yet.

- [ ] **Step 3: Implement pff_config param**

In `src/fantasy_sim/validation/backtester.py`, update `Backtester.__init__`:

```python
from fantasy_sim.data.pff.models import PffConfig

class Backtester:
    def __init__(
        self,
        test_season: int,
        n_sims: int = 100,
        num_training_seasons: int = 3,
        scoring_format: str = "ppr",
        cache_dir: Path | None = None,
        pff_config: PffConfig | None = None,
    ):
        self.test_season = test_season
        self.n_sims = n_sims
        self.training_seasons = list(range(
            test_season - num_training_seasons, test_season
        ))
        self.scoring_format = scoring_format
        self.loader = DataLoader(cache_dir=cache_dir) if cache_dir else DataLoader()
        self.builder = GameContextBuilder(
            cache_dir=self.loader.cache_dir,
            pff_config=pff_config,
        )
```

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/test_validation/test_backtester.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/validation/backtester.py tests/test_validation/test_backtester.py
git commit -m "feat: add pff_config param to Backtester"
```

---

### Task 2: Ledger Data Model and I/O

**Files:**
- Modify: `scripts/validate_pff_signal.py` (add ledger functions)
- Test: `tests/test_scripts/test_ab_ledger.py` (new)

- [ ] **Step 1: Write tests for ledger I/O**

Create `tests/test_scripts/test_ab_ledger.py`:

```python
"""Tests for A/B ledger read/write/display."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest


# Import will work after implementation
from scripts.validate_pff_signal import (
    LedgerEntry,
    SeasonResult,
    load_ledger,
    save_ledger,
    format_progression_table,
)


@pytest.fixture
def ledger_path(tmp_path):
    return tmp_path / "results" / "pff_ab_ledger.json"


class TestLedgerIO:
    def test_load_returns_empty_list_when_no_file(self, ledger_path):
        entries = load_ledger(ledger_path)
        assert entries == []

    def test_save_and_load_roundtrip(self, ledger_path):
        entry = LedgerEntry(
            label="test-run",
            timestamp="2026-04-02T12:00:00",
            mode="talent",
            sims=50,
            test_seasons=[2024],
            training_years=2,
            pff_config={"talent": {"prior_strength": 40}},
            season_results=[
                SeasonResult(
                    test_season=2024,
                    off_weekly_mae=5.80,
                    off_season_mae=22.10,
                    off_rank_corr={"QB": 0.85, "RB": 0.82, "WR": 0.88, "TE": 0.79},
                    off_calibration=0.08,
                    on_weekly_mae=5.77,
                    on_season_mae=21.60,
                    on_rank_corr={"QB": 0.856, "RB": 0.826, "WR": 0.886, "TE": 0.796},
                    on_calibration=0.075,
                )
            ],
            verdict="SOFT_PASS",
        )
        save_ledger(ledger_path, [entry])
        loaded = load_ledger(ledger_path)
        assert len(loaded) == 1
        assert loaded[0].label == "test-run"
        assert loaded[0].season_results[0].off_weekly_mae == 5.80

    def test_save_appends_to_existing(self, ledger_path):
        entry1 = LedgerEntry(
            label="run-1", timestamp="2026-04-02T12:00:00",
            mode="talent", sims=50, test_seasons=[2024], training_years=2,
            pff_config={}, season_results=[], verdict="SOFT_PASS",
        )
        entry2 = LedgerEntry(
            label="run-2", timestamp="2026-04-02T13:00:00",
            mode="talent", sims=50, test_seasons=[2024], training_years=2,
            pff_config={}, season_results=[], verdict="PASS",
        )
        save_ledger(ledger_path, [entry1])
        existing = load_ledger(ledger_path)
        existing.append(entry2)
        save_ledger(ledger_path, existing)
        loaded = load_ledger(ledger_path)
        assert len(loaded) == 2


class TestProgressionTable:
    def test_format_table_with_entries(self):
        entry = LedgerEntry(
            label="baseline-v0", timestamp="2026-04-02T12:00:00",
            mode="talent", sims=50, test_seasons=[2024], training_years=2,
            pff_config={},
            season_results=[
                SeasonResult(
                    test_season=2024,
                    off_weekly_mae=5.80, off_season_mae=22.10,
                    off_rank_corr={"QB": 0.85, "RB": 0.82, "WR": 0.88, "TE": 0.79},
                    off_calibration=0.08,
                    on_weekly_mae=5.77, on_season_mae=21.60,
                    on_rank_corr={"QB": 0.856, "RB": 0.826, "WR": 0.886, "TE": 0.796},
                    on_calibration=0.075,
                )
            ],
            verdict="SOFT_PASS",
        )
        table = format_progression_table([entry])
        assert "baseline-v0" in table
        assert "SOFT_PASS" in table

    def test_format_table_empty(self):
        table = format_progression_table([])
        assert "No entries" in table
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_scripts/test_ab_ledger.py -v`
Expected: ImportError — functions don't exist yet.

- [ ] **Step 3: Implement ledger data model and I/O**

Add to the top of `scripts/validate_pff_signal.py` (after existing imports):

```python
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path


LEDGER_PATH = Path(__file__).parent.parent / "results" / "pff_ab_ledger.json"


@dataclass
class SeasonResult:
    """One season's A/B comparison."""
    test_season: int
    off_weekly_mae: float
    off_season_mae: float
    off_rank_corr: dict[str, float]
    off_calibration: float
    on_weekly_mae: float
    on_season_mae: float
    on_rank_corr: dict[str, float]
    on_calibration: float

    @property
    def rank_corr_delta(self) -> float:
        deltas = [
            self.on_rank_corr.get(p, 0.0) - self.off_rank_corr.get(p, 0.0)
            for p in POSITIONS
        ]
        return sum(deltas) / len(deltas) if deltas else 0.0

    @property
    def weekly_mae_delta(self) -> float:
        return self.on_weekly_mae - self.off_weekly_mae

    @property
    def season_mae_delta(self) -> float:
        return self.on_season_mae - self.off_season_mae

    @property
    def calibration_delta(self) -> float:
        return self.on_calibration - self.off_calibration


@dataclass
class LedgerEntry:
    """One A/B test run."""
    label: str
    timestamp: str
    mode: str
    sims: int
    test_seasons: list[int]
    training_years: int
    pff_config: dict
    season_results: list[SeasonResult]
    verdict: str

    @property
    def avg_rank_corr_delta(self) -> float:
        if not self.season_results:
            return 0.0
        return sum(r.rank_corr_delta for r in self.season_results) / len(self.season_results)

    @property
    def avg_weekly_mae_delta(self) -> float:
        if not self.season_results:
            return 0.0
        return sum(r.weekly_mae_delta for r in self.season_results) / len(self.season_results)

    @property
    def avg_season_mae_delta(self) -> float:
        if not self.season_results:
            return 0.0
        return sum(r.season_mae_delta for r in self.season_results) / len(self.season_results)

    @property
    def avg_calibration_delta(self) -> float:
        if not self.season_results:
            return 0.0
        return sum(r.calibration_delta for r in self.season_results) / len(self.season_results)


def load_ledger(path: Path = LEDGER_PATH) -> list[LedgerEntry]:
    """Load ledger entries from JSON file."""
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    entries = []
    for raw in data:
        sr = [SeasonResult(**s) for s in raw.pop("season_results", [])]
        entries.append(LedgerEntry(**raw, season_results=sr))
    return entries


def save_ledger(path: Path, entries: list[LedgerEntry]) -> None:
    """Save ledger entries to JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = []
    for e in entries:
        d = asdict(e)
        data.append(d)
    path.write_text(json.dumps(data, indent=2) + "\n")


def format_progression_table(entries: list[LedgerEntry]) -> str:
    """Format ledger entries as an ASCII progression table."""
    if not entries:
        return "No entries in ledger."
    header = (
        f"{'#':>3}  {'Label':<30}  {'rank_corr':>10}  {'wk_mae':>8}  "
        f"{'szn_mae':>8}  {'calibr':>8}  {'Verdict':<10}"
    )
    sep = "-" * len(header)
    lines = [sep, header, sep]
    for i, e in enumerate(entries, 1):
        lines.append(
            f"{i:>3}  {e.label:<30}  {e.avg_rank_corr_delta:>+10.4f}  "
            f"{e.avg_weekly_mae_delta:>+8.3f}  {e.avg_season_mae_delta:>+8.3f}  "
            f"{e.avg_calibration_delta:>+8.4f}  {e.verdict:<10}"
        )
    lines.append(sep)
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/test_scripts/test_ab_ledger.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/validate_pff_signal.py tests/test_scripts/test_ab_ledger.py
git commit -m "feat: add A/B ledger data model and I/O"
```

---

### Task 3: Update validate_pff_signal.py CLI

**Files:**
- Modify: `scripts/validate_pff_signal.py`

- [ ] **Step 1: Add --label, --show-ledger, --config-override flags**

In the `main()` function's argument parser, add:

```python
    parser.add_argument(
        "--label",
        type=str,
        default=None,
        help="Label for this run in the ledger (required for ledger recording).",
    )
    parser.add_argument(
        "--show-ledger",
        action="store_true",
        help="Print the ledger progression table and exit.",
    )
    parser.add_argument(
        "--config-override",
        type=str,
        default=None,
        dest="config_override",
        metavar="JSON",
        help=(
            "PFF config overrides as JSON string, merged on top of defaults. "
            'Example: \'{"talent": {"prior_strength": 30}}\''
        ),
    )
```

- [ ] **Step 2: Add show-ledger early exit**

At the start of `main()`, after `args = parser.parse_args()`:

```python
    if args.show_ledger:
        entries = load_ledger()
        print(format_progression_table(entries))
        return 0
```

- [ ] **Step 3: Update _build_pff_config to accept overrides**

Replace the `_build_pff_config` function:

```python
def _build_pff_config(mode: str, overrides: dict | None = None) -> PffConfig:
    """Build a PffConfig with the appropriate layers enabled, plus optional overrides."""
    if mode == "matchup":
        talent_cfg = TalentConfig(enabled=False)
        matchup_cfg = MatchupConfig(enabled=True)
    elif mode == "talent":
        talent_cfg = TalentConfig(enabled=True)
        matchup_cfg = MatchupConfig(enabled=False)
    else:  # "all"
        talent_cfg = TalentConfig(enabled=True)
        matchup_cfg = MatchupConfig(enabled=True)

    # Apply overrides to talent config
    if overrides and "talent" in overrides:
        for key, val in overrides["talent"].items():
            if hasattr(talent_cfg, key):
                setattr(talent_cfg, key, val)

    # Apply overrides to matchup config
    if overrides and "matchup" in overrides:
        for key, val in overrides["matchup"].items():
            if hasattr(matchup_cfg, key):
                setattr(matchup_cfg, key, val)

    return PffConfig(
        enabled=True,
        matchup=matchup_cfg,
        talent=talent_cfg,
    )
```

- [ ] **Step 4: Update main() to use ledger**

In `main()`, after the backtest loop and `evaluate_kill_point()`:

```python
    # Parse config overrides
    overrides = None
    if args.config_override:
        overrides = json.loads(args.config_override)

    # ... (existing backtest loop, but pass overrides to _build_pff_config)
    # In run_backtest_pair call, the mode is passed; update it to also accept overrides:

    # Build PFF config once for this run
    pff_config = _build_pff_config(args.mode, overrides)

    # ... (run backtests using pff_config directly instead of mode)

    # After evaluate_kill_point:
    if args.label:
        season_results = []
        for r in results:
            season_results.append(SeasonResult(
                test_season=r.test_season,
                off_weekly_mae=r.off.weekly_mae,
                off_season_mae=r.off.season_mae,
                off_rank_corr=r.off.rank_correlations,
                off_calibration=r.off.boom_bust_calibration,
                on_weekly_mae=r.on.weekly_mae,
                on_season_mae=r.on.season_mae,
                on_rank_corr=r.on.rank_correlations,
                on_calibration=r.on.boom_bust_calibration,
            ))

        entry = LedgerEntry(
            label=args.label,
            timestamp=datetime.now().isoformat(timespec="seconds"),
            mode=args.mode,
            sims=args.sims,
            test_seasons=args.seasons,
            training_years=args.training_years,
            pff_config=asdict(pff_config),
            season_results=season_results,
            verdict=verdict,  # from evaluate_kill_point
        )

        ledger = load_ledger()
        ledger.append(entry)
        save_ledger(LEDGER_PATH, ledger)
        print(f"\n  Appended to ledger as #{len(ledger)}: {args.label}")
        print(format_progression_table(ledger))
```

- [ ] **Step 5: Refactor run_backtest_pair to accept PffConfig directly**

Update `run_backtest_pair` signature and body:

```python
def run_backtest_pair(
    test_season: int,
    n_sims: int,
    scoring_config: dict,
    num_training_seasons: int,
    pff_config: PffConfig,
) -> ComparisonResult:
    """Run PFF-off then PFF-on backtests for one season and return comparison."""

    print(f"\n  [Season {test_season}] Running PFF-OFF baseline...")
    t0 = time.time()
    bt_off = Backtester(
        test_season=test_season,
        n_sims=n_sims,
        num_training_seasons=num_training_seasons,
    )
    result_off = bt_off.run(scoring_config)
    elapsed_off = time.time() - t0
    print(f"    Done in {elapsed_off:.1f}s  "
          f"weekly_mae={result_off.weekly_mae:.3f}  "
          f"season_mae={result_off.season_mae:.3f}  "
          f"rank_corr={_format_rank_corr(result_off)}")

    print(f"  [Season {test_season}] Running PFF-ON...")
    t0 = time.time()
    bt_on = Backtester(
        test_season=test_season,
        n_sims=n_sims,
        num_training_seasons=num_training_seasons,
        pff_config=pff_config,
    )
    result_on = bt_on.run(scoring_config)
    elapsed_on = time.time() - t0
    print(f"    Done in {elapsed_on:.1f}s  "
          f"weekly_mae={result_on.weekly_mae:.3f}  "
          f"season_mae={result_on.season_mae:.3f}  "
          f"rank_corr={_format_rank_corr(result_on)}")

    return ComparisonResult(test_season=test_season, off=result_off, on=result_on)
```

- [ ] **Step 6: Update evaluate_kill_point to return verdict string**

Change `evaluate_kill_point` to return the verdict string instead of bool:

```python
def evaluate_kill_point(results: list[ComparisonResult]) -> str:
    """Evaluate kill-point criteria. Returns verdict: 'PASS', 'SOFT_PASS', or 'FAIL'."""
    # ... (existing logic unchanged)
    # At the end, instead of `return verdict in ("PASS", "SOFT_PASS")`:
    return verdict
```

Update `main()` to use:
```python
    verdict = evaluate_kill_point(results)
    passed = verdict in ("PASS", "SOFT_PASS")
    # ... (ledger code uses verdict)
    return 0 if passed else 1
```

- [ ] **Step 7: Add results/ to .gitignore**

Append to `.gitignore`:
```
# A/B test results (machine-specific)
results/
!results/.gitkeep
```

Create `results/.gitkeep` (empty file).

- [ ] **Step 8: Run the full test suite to verify nothing broke**

Run: `uv run pytest tests/ -v --timeout=60`
Expected: All existing tests PASS

- [ ] **Step 9: Commit**

```bash
git add scripts/validate_pff_signal.py .gitignore results/.gitkeep
git commit -m "feat: A/B harness with persistent ledger, config overrides, and progression table"
```

---

### Task 4: Run Baseline and Establish Ledger

**Files:** None (runtime task)

- [ ] **Step 1: Run baseline A/B test**

```bash
uv run python scripts/validate_pff_signal.py --mode talent --sims 50 --seasons 2024 --training-years 2 --label "baseline-v0"
```

Expected: Runs PFF-off vs PFF-on (with current hand-tuned coefficients), appends result to `results/pff_ab_ledger.json`, prints progression table.

- [ ] **Step 2: Verify ledger was created**

```bash
uv run python scripts/validate_pff_signal.py --show-ledger
```

Expected: Shows one entry with baseline-v0 results.

---

## Phase 1: Core Tuning

### Workstream A: Coefficient Fitting (Agent 1 — worktree)

### Task 5: PBP Outcome Extraction

**Files:**
- Create: `scripts/fit_talent_coefficients.py`
- Test: `tests/test_scripts/test_fit_coefficients.py`

- [ ] **Step 1: Write tests for PBP outcome extraction**

Create `tests/test_scripts/test_fit_coefficients.py`:

```python
"""Tests for coefficient fitting regression logic."""

import numpy as np
import polars as pl
import pytest

from scripts.fit_talent_coefficients import (
    extract_pbp_catch_rates,
    extract_pbp_yards_per_catch,
    extract_pbp_yards_per_carry,
)


@pytest.fixture
def sample_pbp():
    """Minimal PBP data for testing."""
    return pl.DataFrame({
        "play_type": ["pass", "pass", "pass", "pass", "run", "run"],
        "complete_pass": [1, 0, 1, 1, 0, 0],
        "pass_attempt": [1, 1, 1, 1, 0, 0],
        "rush_attempt": [0, 0, 0, 0, 1, 1],
        "sack": [0, 0, 0, 0, 0, 0],
        "yards_gained": [12, 0, 8, 15, 5, 3],
        "receiver_player_id": ["WR1", "WR1", "WR2", "WR1", None, None],
        "rusher_player_id": [None, None, None, None, "RB1", "RB1"],
        "season": [2023, 2023, 2023, 2023, 2023, 2023],
    })


class TestPbpExtraction:
    def test_catch_rates(self, sample_pbp):
        rates = extract_pbp_catch_rates(sample_pbp, min_targets=2)
        assert "WR1" in rates
        # WR1: 2 catches / 3 targets = 0.667
        assert abs(rates["WR1"] - 2 / 3) < 0.01

    def test_catch_rates_filters_low_volume(self, sample_pbp):
        rates = extract_pbp_catch_rates(sample_pbp, min_targets=5)
        assert len(rates) == 0

    def test_yards_per_catch(self, sample_pbp):
        ypc = extract_pbp_yards_per_catch(sample_pbp, min_catches=2)
        assert "WR1" in ypc
        # WR1: (12 + 15) / 2 = 13.5
        assert abs(ypc["WR1"] - 13.5) < 0.01

    def test_yards_per_carry(self, sample_pbp):
        ypc = extract_pbp_yards_per_carry(sample_pbp, min_carries=2)
        assert "RB1" in ypc
        # RB1: (5 + 3) / 2 = 4.0
        assert abs(ypc["RB1"] - 4.0) < 0.01
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_scripts/test_fit_coefficients.py -v`
Expected: ImportError

- [ ] **Step 3: Implement PBP extraction functions**

Create `scripts/fit_talent_coefficients.py`:

```python
"""Fit PFF talent coefficients via OLS regression.

Uses year-N PFF stats to predict year-N+1 PBP outcomes.
Pairs: PFF 2022 → PBP 2023, PFF 2023 → PBP 2024.

Usage:
    uv run python scripts/fit_talent_coefficients.py
    uv run python scripts/fit_talent_coefficients.py --apply
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import polars as pl

from fantasy_sim.data.loader import DataLoader
from fantasy_sim.data.pff.loader import PffLoader


# Minimum observations for inclusion in regression
MIN_TARGETS = 30
MIN_CATCHES = 20
MIN_CARRIES = 30


def extract_pbp_catch_rates(
    pbp: pl.DataFrame, min_targets: int = MIN_TARGETS
) -> dict[str, float]:
    """Extract per-player catch rate from PBP data.

    Returns dict of player_id -> catch_rate for players with >= min_targets.
    """
    passes = pbp.filter(
        (pl.col("pass_attempt") == 1)
        & (pl.col("sack") == 0)
        & pl.col("receiver_player_id").is_not_null()
    )
    stats = passes.group_by("receiver_player_id").agg(
        pl.col("complete_pass").sum().alias("catches"),
        pl.len().alias("targets"),
    ).filter(pl.col("targets") >= min_targets)

    result: dict[str, float] = {}
    for row in stats.iter_rows(named=True):
        pid = row["receiver_player_id"]
        result[pid] = row["catches"] / row["targets"]
    return result


def extract_pbp_yards_per_catch(
    pbp: pl.DataFrame, min_catches: int = MIN_CATCHES
) -> dict[str, float]:
    """Extract per-player yards per catch from PBP data."""
    completions = pbp.filter(
        (pl.col("complete_pass") == 1)
        & pl.col("receiver_player_id").is_not_null()
    )
    stats = completions.group_by("receiver_player_id").agg(
        pl.col("yards_gained").mean().alias("yards_per_catch"),
        pl.len().alias("catches"),
    ).filter(pl.col("catches") >= min_catches)

    result: dict[str, float] = {}
    for row in stats.iter_rows(named=True):
        result[row["receiver_player_id"]] = row["yards_per_catch"]
    return result


def extract_pbp_yards_per_carry(
    pbp: pl.DataFrame, min_carries: int = MIN_CARRIES
) -> dict[str, float]:
    """Extract per-player yards per carry from PBP data."""
    rushes = pbp.filter(
        (pl.col("rush_attempt") == 1)
        & pl.col("rusher_player_id").is_not_null()
    )
    stats = rushes.group_by("rusher_player_id").agg(
        pl.col("yards_gained").mean().alias("yards_per_carry"),
        pl.len().alias("carries"),
    ).filter(pl.col("carries") >= min_carries)

    result: dict[str, float] = {}
    for row in stats.iter_rows(named=True):
        result[row["rusher_player_id"]] = row["yards_per_carry"]
    return result
```

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/test_scripts/test_fit_coefficients.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/fit_talent_coefficients.py tests/test_scripts/test_fit_coefficients.py
git commit -m "feat: PBP outcome extraction for coefficient fitting"
```

---

### Task 6: OLS Regression and Cross-Validation

**Files:**
- Modify: `scripts/fit_talent_coefficients.py`
- Modify: `tests/test_scripts/test_fit_coefficients.py`

- [ ] **Step 1: Write tests for regression fitting**

Add to `tests/test_scripts/test_fit_coefficients.py`:

```python
from scripts.fit_talent_coefficients import fit_ols, cross_validate_ols


class TestOlsFitting:
    def test_fit_ols_returns_coefficients(self):
        # y = 0.64 + 0.5*x1 - 0.3*x2 + noise
        rng = np.random.default_rng(42)
        n = 100
        X = rng.standard_normal((n, 2))
        y = 0.64 + 0.5 * X[:, 0] - 0.3 * X[:, 1] + rng.normal(0, 0.01, n)

        intercept, coeffs, r_squared = fit_ols(X, y)
        assert abs(intercept - 0.64) < 0.05
        assert abs(coeffs[0] - 0.5) < 0.1
        assert abs(coeffs[1] - (-0.3)) < 0.1
        assert r_squared > 0.9

    def test_fit_ols_single_feature(self):
        X = np.array([[1], [2], [3], [4], [5]], dtype=float)
        y = np.array([2.0, 4.0, 6.0, 8.0, 10.0])  # y = 2*x
        intercept, coeffs, r_squared = fit_ols(X, y)
        assert abs(coeffs[0] - 2.0) < 0.01
        assert r_squared > 0.99

    def test_cross_validate_returns_mae(self):
        rng = np.random.default_rng(42)
        n = 50
        X = rng.standard_normal((n, 2))
        y = 0.64 + 0.5 * X[:, 0] + rng.normal(0, 0.02, n)
        folds = [np.arange(25), np.arange(25, 50)]

        mae = cross_validate_ols(X, y, folds)
        assert mae < 0.1  # Reasonable fit → low CV error
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_scripts/test_fit_coefficients.py::TestOlsFitting -v`
Expected: ImportError

- [ ] **Step 3: Implement OLS regression**

Add to `scripts/fit_talent_coefficients.py`:

```python
def fit_ols(
    X: np.ndarray, y: np.ndarray
) -> tuple[float, np.ndarray, float]:
    """Fit OLS regression: y = intercept + X @ coeffs.

    Args:
        X: Feature matrix (n_samples, n_features).
        y: Target vector (n_samples,).

    Returns:
        (intercept, coefficients, r_squared)
    """
    # Add intercept column
    ones = np.ones((X.shape[0], 1))
    X_aug = np.hstack([ones, X])

    # Solve via least squares
    result, residuals, _, _ = np.linalg.lstsq(X_aug, y, rcond=None)
    intercept = result[0]
    coeffs = result[1:]

    # R-squared
    y_pred = X_aug @ result
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

    return intercept, coeffs, r_squared


def cross_validate_ols(
    X: np.ndarray, y: np.ndarray, folds: list[np.ndarray]
) -> float:
    """Leave-one-fold-out cross-validation. Returns mean absolute error."""
    all_errors = []
    for i, test_idx in enumerate(folds):
        train_idx = np.concatenate([f for j, f in enumerate(folds) if j != i])
        X_train, y_train = X[train_idx], y[train_idx]
        X_test, y_test = X[test_idx], y[test_idx]

        intercept, coeffs, _ = fit_ols(X_train, y_train)
        y_pred = intercept + X_test @ coeffs
        fold_errors = np.abs(y_test - y_pred)
        all_errors.extend(fold_errors.tolist())

    return float(np.mean(all_errors))
```

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/test_scripts/test_fit_coefficients.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/fit_talent_coefficients.py tests/test_scripts/test_fit_coefficients.py
git commit -m "feat: OLS regression and cross-validation for coefficient fitting"
```

---

### Task 7: Coefficient Fitting CLI

**Files:**
- Modify: `scripts/fit_talent_coefficients.py`

- [ ] **Step 1: Implement the main fitting pipeline**

Add to `scripts/fit_talent_coefficients.py`:

```python
def build_catch_rate_dataset(
    pff_loader: PffLoader,
    data_loader: DataLoader,
    pff_season: int,
    pbp_season: int,
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Build feature matrix and target vector for catch_rate regression.

    Features (matching stabilizer formula):
      X0 = (league_avg_drop_rate - player_drop_rate) * 0.01
      X1 = (player_contested_catch_rate - league_avg_contested) * 0.01
      X2 = (team_qb_accuracy - league_avg_accuracy) * 0.01

    Target: PBP catch_rate from next season.

    Returns: (X, y, feature_names)
    """
    # PFF data from pff_season
    recv = pff_loader.aggregate_player_stats("receiving_summary", [pff_season])
    passing = pff_loader.aggregate_player_stats("passing_summary", [pff_season])

    if recv.is_empty():
        return np.empty((0, 3)), np.empty(0), ["drop_rate", "contested_catch_rate", "qb_accuracy"]

    # League averages
    avg_drop = float(recv.select(pl.col("drop_rate").mean()).item() or 0)
    avg_contested = float(recv.select(pl.col("contested_catch_rate").mean()).item() or 0)
    avg_accuracy = float(passing.select(pl.col("accuracy_percent").mean()).item() or 75.0) if not passing.is_empty() else 75.0

    # Team QB accuracy
    team_qb_acc: dict[str, float] = {}
    if not passing.is_empty() and "accuracy_percent" in passing.columns:
        for row in passing.iter_rows(named=True):
            team = row.get("team")
            acc = row.get("accuracy_percent")
            if team and acc is not None:
                team_qb_acc[team] = float(acc)

    # Build crosswalk
    pff_data = recv.select(["player_id", "player", "team"]).unique(subset=["player_id"])
    roster = data_loader.load_rosters([pff_season])
    crosswalk = pff_loader.build_crosswalk(pff_data, roster, pff_season)

    # PBP catch rates from next season
    pbp = data_loader.load_pbp([pbp_season])
    pbp_rates = extract_pbp_catch_rates(pbp, min_targets=MIN_TARGETS)

    # Match PFF players to PBP outcomes
    rows_X = []
    rows_y = []
    for row in recv.iter_rows(named=True):
        pff_id = row.get("player_id")
        if pff_id is None or pff_id not in crosswalk:
            continue
        nfl_id = crosswalk[pff_id]
        if nfl_id not in pbp_rates:
            continue

        player_drop = float(row.get("drop_rate", 0) or 0)
        player_contested = float(row.get("contested_catch_rate", 0) or 0)
        player_team = row.get("team", "")
        qb_acc = team_qb_acc.get(player_team, avg_accuracy)

        x0 = (avg_drop - player_drop) * 0.01
        x1 = (player_contested - avg_contested) * 0.01
        x2 = (qb_acc - avg_accuracy) * 0.01

        rows_X.append([x0, x1, x2])
        rows_y.append(pbp_rates[nfl_id])

    return (
        np.array(rows_X) if rows_X else np.empty((0, 3)),
        np.array(rows_y) if rows_y else np.empty(0),
        ["drop_rate", "contested_catch_rate", "qb_accuracy"],
    )


def build_receiving_yards_dataset(
    pff_loader: PffLoader,
    data_loader: DataLoader,
    pff_season: int,
    pbp_season: int,
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Build dataset for receiving yards regression.

    Features:
      X0 = (player_yprr - league_avg_yprr)
      X1 = (player_adot - league_avg_adot)

    Target: PBP yards_per_catch from next season.
    """
    recv = pff_loader.aggregate_player_stats("receiving_summary", [pff_season])
    if recv.is_empty():
        return np.empty((0, 2)), np.empty(0), ["yprr", "avg_depth_of_target"]

    avg_yprr = float(recv.select(pl.col("yprr").mean()).item() or 0)
    avg_adot = float(recv.select(pl.col("avg_depth_of_target").mean()).item() or 0)

    pff_data = recv.select(["player_id", "player", "team"]).unique(subset=["player_id"])
    roster = data_loader.load_rosters([pff_season])
    crosswalk = pff_loader.build_crosswalk(pff_data, roster, pff_season)

    pbp = data_loader.load_pbp([pbp_season])
    pbp_ypc = extract_pbp_yards_per_catch(pbp, min_catches=MIN_CATCHES)

    rows_X, rows_y = [], []
    for row in recv.iter_rows(named=True):
        pff_id = row.get("player_id")
        if pff_id is None or pff_id not in crosswalk:
            continue
        nfl_id = crosswalk[pff_id]
        if nfl_id not in pbp_ypc:
            continue

        x0 = float(row.get("yprr", 0) or 0) - avg_yprr
        x1 = float(row.get("avg_depth_of_target", 0) or 0) - avg_adot
        rows_X.append([x0, x1])
        rows_y.append(pbp_ypc[nfl_id])

    return (
        np.array(rows_X) if rows_X else np.empty((0, 2)),
        np.array(rows_y) if rows_y else np.empty(0),
        ["yprr", "avg_depth_of_target"],
    )


def build_rushing_yards_dataset(
    pff_loader: PffLoader,
    data_loader: DataLoader,
    pff_season: int,
    pbp_season: int,
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Build dataset for rushing yards regression.

    Features:
      X0 = (player_yco - league_avg_yco)
      X1 = (player_elusive - league_avg_elusive)

    Target: PBP yards_per_carry from next season.
    """
    rush = pff_loader.aggregate_player_stats("rushing_summary", [pff_season])
    if rush.is_empty():
        return np.empty((0, 2)), np.empty(0), ["yco_attempt", "elusive_rating"]

    avg_yco = float(rush.select(pl.col("yco_attempt").mean()).item() or 0)
    avg_elusive = float(rush.select(pl.col("elusive_rating").mean()).item() or 0)

    pff_data = rush.select(["player_id", "player", "team"]).unique(subset=["player_id"])
    roster = data_loader.load_rosters([pff_season])
    crosswalk = pff_loader.build_crosswalk(pff_data, roster, pff_season)

    pbp = data_loader.load_pbp([pbp_season])
    pbp_ypc = extract_pbp_yards_per_carry(pbp, min_carries=MIN_CARRIES)

    rows_X, rows_y = [], []
    for row in rush.iter_rows(named=True):
        pff_id = row.get("player_id")
        if pff_id is None or pff_id not in crosswalk:
            continue
        nfl_id = crosswalk[pff_id]
        if nfl_id not in pbp_ypc:
            continue

        x0 = float(row.get("yco_attempt", 0) or 0) - avg_yco
        x1 = float(row.get("elusive_rating", 0) or 0) - avg_elusive
        rows_X.append([x0, x1])
        rows_y.append(pbp_ypc[nfl_id])

    return (
        np.array(rows_X) if rows_X else np.empty((0, 2)),
        np.array(rows_y) if rows_y else np.empty(0),
        ["yco_attempt", "elusive_rating"],
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fit PFF talent coefficients via OLS regression.",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Update defaults.yaml with fitted coefficients.",
    )
    args = parser.parse_args()

    pff_loader = PffLoader()
    data_loader = DataLoader()

    if not pff_loader.is_available():
        print("ERROR: PFF data not found. Run scrape_pff.py first.")
        return 1

    # Year-N PFF → Year-N+1 PBP pairs
    pairs = [(2022, 2023), (2023, 2024)]

    print("=" * 60)
    print("  PFF COEFFICIENT FITTING")
    print("=" * 60)

    for name, builder_fn, feature_names in [
        ("catch_rate", build_catch_rate_dataset, ["drop_rate", "contested_catch_rate", "qb_accuracy"]),
        ("receiving_yards", build_receiving_yards_dataset, ["yprr", "avg_depth_of_target"]),
        ("rushing_yards", build_rushing_yards_dataset, ["yco_attempt", "elusive_rating"]),
    ]:
        print(f"\n--- {name} ---")

        # Collect data from all pairs
        all_X, all_y = [], []
        fold_indices = []
        offset = 0
        for pff_yr, pbp_yr in pairs:
            X, y, _ = builder_fn(pff_loader, data_loader, pff_yr, pbp_yr)
            if len(y) == 0:
                print(f"  No data for pair {pff_yr}->{pbp_yr}")
                continue
            print(f"  Pair {pff_yr}->{pbp_yr}: {len(y)} players")
            fold_indices.append(np.arange(offset, offset + len(y)))
            all_X.append(X)
            all_y.append(y)
            offset += len(y)

        if not all_X:
            print(f"  SKIP: No data available for {name}")
            continue

        X_all = np.vstack(all_X)
        y_all = np.concatenate(all_y)

        # Fit on all data
        intercept, coeffs, r_sq = fit_ols(X_all, y_all)
        print(f"  Intercept: {intercept:.4f}")
        for fname, c in zip(feature_names, coeffs):
            print(f"  {fname}: {c:.4f}")
        print(f"  R²: {r_sq:.4f}")

        # Cross-validate
        if len(fold_indices) >= 2:
            cv_mae = cross_validate_ols(X_all, y_all, fold_indices)
            print(f"  CV MAE: {cv_mae:.4f}")

    if args.apply:
        print("\n  --apply: Update defaults.yaml with fitted coefficients (manual step)")
        print("  Copy the coefficients above into config/defaults.yaml under pff.talent.")

    print("\n" + "=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run tests to verify all pass**

Run: `uv run pytest tests/test_scripts/test_fit_coefficients.py -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add scripts/fit_talent_coefficients.py tests/test_scripts/test_fit_coefficients.py
git commit -m "feat: coefficient fitting CLI with dataset builders and cross-validation"
```

---

### Workstream B: Position-Specific prior_strength (Agent 2 — worktree)

### Task 8: Config and Model Changes for Position-Specific Strength

**Files:**
- Modify: `src/fantasy_sim/data/pff/models.py`
- Modify: `src/fantasy_sim/data/pff/config.py`
- Test: `tests/test_data/test_pff/test_config.py`

- [ ] **Step 1: Write tests for position-specific config parsing**

Add to `tests/test_data/test_pff/test_config.py`:

```python
class TestPositionSpecificStrength:
    def test_scalar_prior_strength_still_works(self):
        cfg = load_pff_config({
            "pff": {"talent": {"prior_strength": 50.0}}
        })
        assert cfg.talent.prior_strength == 50.0

    def test_dict_prior_strength_loaded(self):
        cfg = load_pff_config({
            "pff": {"talent": {"prior_strength": {
                "QB": 60, "WR": 40, "TE": 35, "RB": 30, "default": 40,
            }}}
        })
        assert isinstance(cfg.talent.prior_strength, dict)
        assert cfg.talent.prior_strength["QB"] == 60
        assert cfg.talent.prior_strength["RB"] == 30
        assert cfg.talent.prior_strength["default"] == 40

    def test_default_prior_strength_is_float(self):
        cfg = load_pff_config({"pff": {}})
        assert cfg.talent.prior_strength == 40.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_pff/test_config.py::TestPositionSpecificStrength -v`
Expected: FAIL — dict not supported yet.

- [ ] **Step 3: Update TalentConfig type**

In `src/fantasy_sim/data/pff/models.py`, change `TalentConfig`:

```python
@dataclass
class TalentConfig:
    """Configuration for the talent stabilizer."""
    enabled: bool = True
    prior_strength: float | dict[str, float] = 40.0
    min_divergence: float = 0.03
    catch_rate_coefficients: dict[str, float] = field(default_factory=lambda: {
        "drop_rate": -0.15,
        "contested_catch_rate": 0.10,
        "qb_accuracy": 0.08,
    })
    rushing_yards_coefficients: dict[str, float] = field(default_factory=lambda: {
        "yco_attempt": 0.6,
        "elusive_rating": 0.008,
    })
    receiving_yards_coefficients: dict[str, float] = field(default_factory=lambda: {
        "yprr": 0.5,
        "avg_depth_of_target": 0.03,
    })
    team_change_factor: float = 1.0
```

- [ ] **Step 4: Update config loader**

In `src/fantasy_sim/data/pff/config.py`, the `prior_strength` line already works with both types since `talent_raw.get("prior_strength", 40.0)` returns whatever YAML provides (float or dict). No change needed — YAML naturally parses `prior_strength: 40` as float and `prior_strength: {QB: 60, ...}` as dict.

- [ ] **Step 5: Run tests to verify pass**

Run: `uv run pytest tests/test_data/test_pff/test_config.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/fantasy_sim/data/pff/models.py src/fantasy_sim/data/pff/config.py tests/test_data/test_pff/test_config.py
git commit -m "feat: support position-specific prior_strength in TalentConfig"
```

---

### Task 9: Position-Specific Strength in TalentStabilizer

**Files:**
- Modify: `src/fantasy_sim/data/pff/talent.py`
- Test: `tests/test_data/test_pff/test_talent.py`

- [ ] **Step 1: Write tests for position-specific resolution**

Add to `tests/test_data/test_pff/test_talent.py`:

```python
class TestPositionSpecificStrength:
    def test_resolve_scalar_returns_same_for_all_positions(self):
        config = TalentConfig(prior_strength=50.0)
        stabilizer = TalentStabilizer(
            PffConfig(enabled=True, talent=config),
            PffLoader(tmp_path / "empty"),
        )
        assert stabilizer._resolve_prior_strength("QB") == 50.0
        assert stabilizer._resolve_prior_strength("WR") == 50.0
        assert stabilizer._resolve_prior_strength("RB") == 50.0

    def test_resolve_dict_returns_position_value(self):
        config = TalentConfig(prior_strength={"QB": 60, "WR": 40, "RB": 30, "default": 45})
        stabilizer = TalentStabilizer(
            PffConfig(enabled=True, talent=config),
            PffLoader(tmp_path / "empty"),
        )
        assert stabilizer._resolve_prior_strength("QB") == 60
        assert stabilizer._resolve_prior_strength("WR") == 40
        assert stabilizer._resolve_prior_strength("RB") == 30

    def test_resolve_dict_falls_back_to_default(self):
        config = TalentConfig(prior_strength={"QB": 60, "default": 45})
        stabilizer = TalentStabilizer(
            PffConfig(enabled=True, talent=config),
            PffLoader(tmp_path / "empty"),
        )
        assert stabilizer._resolve_prior_strength("TE") == 45

    def test_resolve_dict_no_default_uses_40(self):
        config = TalentConfig(prior_strength={"QB": 60})
        stabilizer = TalentStabilizer(
            PffConfig(enabled=True, talent=config),
            PffLoader(tmp_path / "empty"),
        )
        assert stabilizer._resolve_prior_strength("WR") == 40.0

    def test_stabilize_value_uses_position_strength(self):
        """A WR with low prior_strength gets more PFF weight than a QB with high prior_strength."""
        pbp = 0.60
        prior = 0.70
        n_obs = 40  # Same observation count

        # WR: prior_strength=30 → more PFF weight
        wr_result = stabilize_value(pbp, prior, n_obs, prior_strength=30, min_divergence=0.03)
        # QB: prior_strength=60 → less PFF weight
        qb_result = stabilize_value(pbp, prior, n_obs, prior_strength=60, min_divergence=0.03)

        # WR should be pulled further toward the prior
        assert wr_result > qb_result
        assert wr_result < prior
        assert qb_result > pbp
```

Note: These tests use the `tmp_path` fixture — update test methods to accept it as a parameter or use the existing `pff_dir` fixture.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_pff/test_talent.py::TestPositionSpecificStrength -v`
Expected: FAIL — `_resolve_prior_strength` doesn't exist.

- [ ] **Step 3: Implement _resolve_prior_strength**

Add to `TalentStabilizer` in `src/fantasy_sim/data/pff/talent.py`:

```python
    def _resolve_prior_strength(self, position: str) -> float:
        """Resolve prior_strength for a given position.

        Supports both scalar (float) and position-specific (dict) formats.
        """
        ps = self._config.prior_strength
        if isinstance(ps, (int, float)):
            return float(ps)
        return float(ps.get(position, ps.get("default", 40.0)))
```

- [ ] **Step 4: Update all stabilize_value calls to use resolved strength**

In `_stabilize_catch_rate`, replace `self._config.prior_strength` with `self._resolve_prior_strength(player.position)`:

```python
        strength = self._resolve_prior_strength(player.position)
        new_catch = stabilize_value(
            old_catch, prior, n_obs,
            strength, self._config.min_divergence,
        )
```

Same change in `_stabilize_receiving_yards`:
```python
        pff_confidence = 1.0 - (n_targets / (n_targets + self._resolve_prior_strength(player.position)))
        # ...
        adjusted_shift = shift * (1.0 - pff_confidence)
```

And `_stabilize_rushing_yards`:
```python
        pff_confidence = 1.0 - (n_attempts / (n_attempts + self._resolve_prior_strength(player.position)))
        # ...
        adjusted_shift = shift * (1.0 - pff_confidence)
```

Note: The yards methods need the player's position. Currently they don't have access to it because they receive `player` which has `.position`. Check that the existing calls pass the full player — they do (the methods receive `player: PlayerModel`). So `player.position` is available.

- [ ] **Step 5: Run tests to verify pass**

Run: `uv run pytest tests/test_data/test_pff/test_talent.py -v`
Expected: All PASS (existing + new)

- [ ] **Step 6: Commit**

```bash
git add src/fantasy_sim/data/pff/talent.py tests/test_data/test_pff/test_talent.py
git commit -m "feat: position-specific prior_strength resolution in TalentStabilizer"
```

---

### Workstream C: Team-Change Boost (Agent 3 — worktree)

### Task 10: Team-Change Config and Detection

**Files:**
- Modify: `src/fantasy_sim/data/pff/models.py` (add team_change_factor)
- Modify: `src/fantasy_sim/data/pff/config.py` (load team_change_factor)
- Modify: `src/fantasy_sim/data/pff/talent.py` (detection + boost)
- Test: `tests/test_data/test_pff/test_talent.py`

- [ ] **Step 1: Write tests for team-change detection and boost**

Add to `tests/test_data/test_pff/test_talent.py`:

```python
class TestTeamChangeBoost:
    def test_same_team_no_boost(self):
        """Player on same team as PFF data → no strength reduction."""
        config = TalentConfig(prior_strength=40.0, team_change_factor=0.5)
        stabilizer = TalentStabilizer(
            PffConfig(enabled=True, talent=config),
            PffLoader(tmp_path / "empty"),
        )
        effective = stabilizer._effective_prior_strength("WR", "KC", "KC")
        assert effective == 40.0

    def test_team_change_applies_factor(self):
        """Player changed teams → prior_strength multiplied by factor."""
        config = TalentConfig(prior_strength=40.0, team_change_factor=0.5)
        stabilizer = TalentStabilizer(
            PffConfig(enabled=True, talent=config),
            PffLoader(tmp_path / "empty"),
        )
        effective = stabilizer._effective_prior_strength("WR", "KC", "BUF")
        assert effective == 20.0  # 40 * 0.5

    def test_team_change_with_position_specific(self):
        """Team change + position-specific strength."""
        config = TalentConfig(
            prior_strength={"QB": 60, "WR": 40, "default": 40},
            team_change_factor=0.5,
        )
        stabilizer = TalentStabilizer(
            PffConfig(enabled=True, talent=config),
            PffLoader(tmp_path / "empty"),
        )
        assert stabilizer._effective_prior_strength("QB", "KC", "BUF") == 30.0
        assert stabilizer._effective_prior_strength("WR", "KC", "BUF") == 20.0

    def test_factor_1_means_no_boost(self):
        """Default factor=1.0 → no change even on team switch."""
        config = TalentConfig(prior_strength=40.0, team_change_factor=1.0)
        stabilizer = TalentStabilizer(
            PffConfig(enabled=True, talent=config),
            PffLoader(tmp_path / "empty"),
        )
        effective = stabilizer._effective_prior_strength("WR", "KC", "BUF")
        assert effective == 40.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_pff/test_talent.py::TestTeamChangeBoost -v`
Expected: FAIL — `_effective_prior_strength` doesn't exist, `team_change_factor` not on TalentConfig.

- [ ] **Step 3: Add team_change_factor to TalentConfig**

Already added in Task 8 step 3 — `team_change_factor: float = 1.0`. If working in a separate worktree, add it to `TalentConfig` in `models.py`.

Update `config.py` `load_pff_config()` to load it:

```python
    talent = TalentConfig(
        enabled=talent_raw.get("enabled", True),
        prior_strength=talent_raw.get("prior_strength", 40.0),
        min_divergence=talent_raw.get("min_divergence", 0.03),
        team_change_factor=talent_raw.get("team_change_factor", 1.0),
        # ... existing coefficient fields ...
    )
```

- [ ] **Step 4: Implement _effective_prior_strength**

Add to `TalentStabilizer` in `talent.py`:

```python
    def _effective_prior_strength(
        self, position: str, current_team: str, pff_team: str,
    ) -> float:
        """Get effective prior_strength, accounting for position and team change.

        If player changed teams, multiply strength by team_change_factor
        (lower strength = more PFF weight for team changers).
        """
        strength = self._resolve_prior_strength(position)
        if current_team != pff_team and self._config.team_change_factor != 1.0:
            strength *= self._config.team_change_factor
        return strength
```

- [ ] **Step 5: Update stabilization methods to use _effective_prior_strength**

In `_stabilize_catch_rate`, replace the strength resolution with:

```python
        pff_team = pff_row.get("team", player.team)
        strength = self._effective_prior_strength(player.position, player.team, pff_team)
        new_catch = stabilize_value(
            old_catch, prior, n_obs,
            strength, self._config.min_divergence,
        )
```

Same pattern in `_stabilize_receiving_yards` and `_stabilize_rushing_yards`:

```python
        pff_team = pff_row.get("team", player.team)
        strength = self._effective_prior_strength(player.position, player.team, pff_team)
        pff_confidence = 1.0 - (n_targets / (n_targets + strength))
```

- [ ] **Step 6: Run tests to verify pass**

Run: `uv run pytest tests/test_data/test_pff/test_talent.py -v`
Expected: All PASS

- [ ] **Step 7: Update defaults.yaml**

Add `team_change_factor` to the pff.talent section in `config/defaults.yaml`:

```yaml
  talent:
    enabled: true
    prior_strength: 40
    min_divergence: 0.03
    team_change_factor: 0.5
```

- [ ] **Step 8: Commit**

```bash
git add src/fantasy_sim/data/pff/models.py src/fantasy_sim/data/pff/config.py \
  src/fantasy_sim/data/pff/talent.py tests/test_data/test_pff/test_talent.py \
  config/defaults.yaml
git commit -m "feat: team-change boost — lower prior_strength for traded players"
```

---

### Phase 1 Integration Tasks

### Task 11: Integrate Coefficients and A/B Test

**Files:** None (runtime + config update)

- [ ] **Step 1: Run coefficient fitting script**

```bash
uv run python scripts/fit_talent_coefficients.py
```

Review output. Note the fitted coefficients.

- [ ] **Step 2: Update defaults.yaml with fitted coefficients**

Replace hand-tuned values with fitted values in `config/defaults.yaml` under `pff.talent`.

- [ ] **Step 3: Run A/B test**

```bash
uv run python scripts/validate_pff_signal.py --mode talent --sims 50 --seasons 2024 --training-years 2 --label "fitted-coefficients"
```

- [ ] **Step 4: Check ledger progression**

```bash
uv run python scripts/validate_pff_signal.py --show-ledger
```

Verify rank_corr improved vs baseline-v0. If regressed, revert coefficients.

- [ ] **Step 5: Commit config update**

```bash
git add config/defaults.yaml
git commit -m "feat: update talent coefficients from OLS regression fitting"
```

---

### Task 12: Integrate Position-Specific Strength and A/B Test

- [ ] **Step 1: Merge workstream B changes into main branch**

- [ ] **Step 2: Update defaults.yaml with position-specific strengths**

```yaml
  talent:
    prior_strength:
      QB: 60
      WR: 40
      TE: 35
      RB: 30
      default: 40
```

- [ ] **Step 3: Run A/B test**

```bash
uv run python scripts/validate_pff_signal.py --mode talent --sims 50 --seasons 2024 --training-years 2 --label "+pos-specific-strength"
```

- [ ] **Step 4: Check ledger — verify no regression**

If cumulative rank_corr regressed by >0.005, revert to scalar prior_strength.

- [ ] **Step 5: Commit**

```bash
git add config/defaults.yaml
git commit -m "feat: position-specific prior_strength values"
```

---

### Task 13: Integrate Team-Change Boost and A/B Test

- [ ] **Step 1: Merge workstream C changes into main branch**

- [ ] **Step 2: Run A/B test**

```bash
uv run python scripts/validate_pff_signal.py --mode talent --sims 50 --seasons 2024 --training-years 2 --label "+team-change-boost"
```

- [ ] **Step 3: Check ledger — verify no regression**

- [ ] **Step 4: Commit if needed**

---

## Phase 2: Sweep + Extensions

### Workstream D: Sensitivity Sweep Script (Agent 1 — worktree)

### Task 14: Sweep Script

**Files:**
- Create: `scripts/sweep_talent_params.py`
- Test: `tests/test_scripts/test_sweep.py`

- [ ] **Step 1: Write test for grid generation**

Create `tests/test_scripts/test_sweep.py`:

```python
"""Tests for sweep grid logic."""

from scripts.sweep_talent_params import build_sweep_grid


class TestSweepGrid:
    def test_grid_size(self):
        grid = build_sweep_grid(
            prior_strengths=[20, 40, 60],
            min_divergences=[0.02, 0.03],
        )
        assert len(grid) == 6

    def test_grid_entries_are_dicts(self):
        grid = build_sweep_grid(
            prior_strengths=[40],
            min_divergences=[0.03],
        )
        assert len(grid) == 1
        assert grid[0]["prior_strength"] == 40
        assert grid[0]["min_divergence"] == 0.03
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_scripts/test_sweep.py -v`

- [ ] **Step 3: Implement sweep script**

Create `scripts/sweep_talent_params.py`:

```python
"""Grid search over prior_strength x min_divergence.

Usage:
    uv run python scripts/sweep_talent_params.py --sims 30
    uv run python scripts/sweep_talent_params.py --sims 30 --apply
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from fantasy_sim.config.loader import load_defaults, resolve_scoring
from fantasy_sim.data.pff.models import PffConfig, TalentConfig, MatchupConfig
from fantasy_sim.validation.backtester import Backtester

POSITIONS = ("QB", "RB", "WR", "TE")

DEFAULT_PRIOR_STRENGTHS = [20, 30, 40, 60, 80]
DEFAULT_MIN_DIVERGENCES = [0.01, 0.02, 0.03, 0.05]


def build_sweep_grid(
    prior_strengths: list[float] = DEFAULT_PRIOR_STRENGTHS,
    min_divergences: list[float] = DEFAULT_MIN_DIVERGENCES,
) -> list[dict]:
    """Build parameter grid."""
    grid = []
    for ps in prior_strengths:
        for md in min_divergences:
            grid.append({"prior_strength": ps, "min_divergence": md})
    return grid


def run_sweep(
    grid: list[dict],
    test_season: int,
    n_sims: int,
    num_training_seasons: int,
    scoring_config: dict,
) -> list[dict]:
    """Run A/B backtest for each grid point. Returns ranked results."""

    # Run baseline once
    print("  Running baseline (PFF off)...")
    t0 = time.time()
    bt_off = Backtester(
        test_season=test_season,
        n_sims=n_sims,
        num_training_seasons=num_training_seasons,
    )
    result_off = bt_off.run(scoring_config)
    print(f"  Baseline done in {time.time() - t0:.1f}s")

    results = []
    for i, params in enumerate(grid):
        label = f"ps={params['prior_strength']},md={params['min_divergence']}"
        print(f"\n  [{i+1}/{len(grid)}] {label}...")

        pff_config = PffConfig(
            enabled=True,
            matchup=MatchupConfig(enabled=False),
            talent=TalentConfig(
                enabled=True,
                prior_strength=params["prior_strength"],
                min_divergence=params["min_divergence"],
            ),
        )

        t0 = time.time()
        bt_on = Backtester(
            test_season=test_season,
            n_sims=n_sims,
            num_training_seasons=num_training_seasons,
            pff_config=pff_config,
        )
        result_on = bt_on.run(scoring_config)
        elapsed = time.time() - t0

        # Compute deltas
        rc_deltas = [
            result_on.rank_correlations.get(p, 0) - result_off.rank_correlations.get(p, 0)
            for p in POSITIONS
        ]
        avg_rc_delta = sum(rc_deltas) / len(rc_deltas)
        mae_delta = result_on.weekly_mae - result_off.weekly_mae

        results.append({
            **params,
            "rank_corr_delta": avg_rc_delta,
            "weekly_mae_delta": mae_delta,
            "season_mae_delta": result_on.season_mae - result_off.season_mae,
            "calibration_delta": result_on.boom_bust_calibration - result_off.boom_bust_calibration,
            "elapsed": elapsed,
        })
        print(f"    rank_corr_delta={avg_rc_delta:+.4f}  mae_delta={mae_delta:+.3f}  ({elapsed:.1f}s)")

    # Sort by rank_corr_delta descending
    results.sort(key=lambda r: r["rank_corr_delta"], reverse=True)
    return results


def print_results_table(results: list[dict]) -> None:
    """Print ranked results table."""
    print("\n" + "=" * 80)
    print(f"  {'#':>3}  {'prior_str':>10}  {'min_div':>8}  {'rank_corr':>10}  "
          f"{'wk_mae':>8}  {'szn_mae':>8}  {'calibr':>8}")
    print("-" * 80)
    for i, r in enumerate(results, 1):
        marker = " <-- BEST" if i == 1 else ""
        print(f"  {i:>3}  {r['prior_strength']:>10}  {r['min_divergence']:>8.2f}  "
              f"{r['rank_corr_delta']:>+10.4f}  {r['weekly_mae_delta']:>+8.3f}  "
              f"{r['season_mae_delta']:>+8.3f}  {r['calibration_delta']:>+8.4f}{marker}")
    print("=" * 80)


def main() -> int:
    parser = argparse.ArgumentParser(description="Sweep prior_strength x min_divergence.")
    parser.add_argument("--sims", type=int, default=30)
    parser.add_argument("--season", type=int, default=2024)
    parser.add_argument("--training-years", type=int, default=2, dest="training_years")
    parser.add_argument("--apply", action="store_true", help="Print best params for defaults.yaml.")
    args = parser.parse_args()

    defaults = load_defaults()
    scoring_config = resolve_scoring(defaults["scoring"], "ppr")

    grid = build_sweep_grid()
    print(f"Sweeping {len(grid)} combinations for season {args.season}...")

    results = run_sweep(grid, args.season, args.sims, args.training_years, scoring_config)
    print_results_table(results)

    if args.apply and results:
        best = results[0]
        print(f"\n  Best: prior_strength={best['prior_strength']}, "
              f"min_divergence={best['min_divergence']}")
        print("  Update config/defaults.yaml with these values.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/test_scripts/test_sweep.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/sweep_talent_params.py tests/test_scripts/test_sweep.py
git commit -m "feat: sensitivity sweep script for prior_strength x min_divergence"
```

---

### Workstream E: Additional Parameters (Agent 2 — worktree)

### Task 15: target_share Stabilization

**Files:**
- Modify: `src/fantasy_sim/data/pff/models.py`
- Modify: `src/fantasy_sim/data/pff/config.py`
- Modify: `src/fantasy_sim/data/pff/talent.py`
- Test: `tests/test_data/test_pff/test_talent.py`

- [ ] **Step 1: Write tests for target_share stabilization**

Add to `tests/test_data/test_pff/test_talent.py`:

```python
class TestTargetShareStabilization:
    def test_high_route_grade_increases_target_share(self):
        """Player with elite route_grade but low target_share gets nudged up."""
        player = PlayerModel(
            "WR1", "Elite Route WR", "WR", "KC",
            PlayerUsage(target_share=0.15),
            PlayerOutcomes(catch_rate=0.65, receiving_yards_dist=np.array([8, 12, 15])),
        )
        # PFF row with high route_grade (league avg ~65)
        pff_row = {"route_grade": 85.0, "yprr": 2.5, "team": "KC", "games": 16, "targets": 6}
        recv_avgs = {"route_grade": 65.0, "yprr": 1.5}

        config = TalentConfig(
            target_share_coefficients={"route_grade": 0.5, "yprr": 0.3},
        )
        stabilizer = TalentStabilizer(
            PffConfig(enabled=True, talent=config),
            PffLoader(tmp_path / "empty"),
        )
        old_ts = player.usage.target_share
        adjusted = stabilizer._stabilize_target_share(player, pff_row, recv_avgs)

        assert adjusted is True
        assert player.usage.target_share > old_ts

    def test_low_route_grade_decreases_target_share(self):
        """Player with poor route_grade and high target_share gets nudged down."""
        player = PlayerModel(
            "WR2", "Bad Route WR", "WR", "KC",
            PlayerUsage(target_share=0.30),
            PlayerOutcomes(catch_rate=0.65, receiving_yards_dist=np.array([8, 12, 15])),
        )
        pff_row = {"route_grade": 50.0, "yprr": 0.8, "team": "KC", "games": 16, "targets": 8}
        recv_avgs = {"route_grade": 65.0, "yprr": 1.5}

        config = TalentConfig(
            target_share_coefficients={"route_grade": 0.5, "yprr": 0.3},
        )
        stabilizer = TalentStabilizer(
            PffConfig(enabled=True, talent=config),
            PffLoader(tmp_path / "empty"),
        )
        old_ts = player.usage.target_share
        adjusted = stabilizer._stabilize_target_share(player, pff_row, recv_avgs)

        assert adjusted is True
        assert player.usage.target_share < old_ts
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_pff/test_talent.py::TestTargetShareStabilization -v`

- [ ] **Step 3: Add target_share_coefficients to TalentConfig**

In `models.py`, add to `TalentConfig`:

```python
    target_share_coefficients: dict[str, float] = field(default_factory=lambda: {
        "route_grade": 0.5,
        "yprr": 0.3,
    })
```

In `config.py`, add to the `TalentConfig` constructor in `load_pff_config()`:

```python
        target_share_coefficients=talent_raw.get("target_share_coefficients", {
            "route_grade": 0.5,
            "yprr": 0.3,
        }),
```

- [ ] **Step 4: Implement _stabilize_target_share**

Add to `TalentStabilizer` in `talent.py`:

```python
    # At module level
    MIN_TARGET_SHARE_SHIFT = 0.01

    # In TalentStabilizer class
    def _stabilize_target_share(
        self,
        player: PlayerModel,
        pff_row: dict,
        recv_avgs: dict[str, float],
    ) -> bool:
        """Stabilize target_share using route_grade and YPRR signals. Returns True if adjusted."""
        coeffs = self._config.target_share_coefficients

        player_rg = pff_row.get("route_grade", 0.0) or 0.0
        player_yprr = pff_row.get("yprr", 0.0) or 0.0
        avg_rg = recv_avgs.get("route_grade", 65.0)
        avg_yprr = recv_avgs.get("yprr", 1.5)

        # Compute prior as a multiplicative adjustment to current target_share
        # Higher route_grade → proportionally more targets
        rg_ratio = player_rg / avg_rg if avg_rg > 0 else 1.0
        yprr_ratio = player_yprr / avg_yprr if avg_yprr > 0 else 1.0

        # Weighted blend of ratios
        rg_weight = coeffs.get("route_grade", 0.5)
        yprr_weight = coeffs.get("yprr", 0.3)
        total_weight = rg_weight + yprr_weight
        if total_weight == 0:
            return False

        blended_ratio = (rg_weight * rg_ratio + yprr_weight * yprr_ratio) / total_weight
        prior_ts = player.usage.target_share * blended_ratio

        # Clamp prior to reasonable range
        prior_ts = max(0.01, min(0.50, prior_ts))

        # Bayesian blend
        games = pff_row.get("games", 0) or 0
        targets = pff_row.get("targets", 0) or 0
        n_obs = int(targets * games) if games > 0 else 0

        pff_team = pff_row.get("team", player.team)
        strength = self._effective_prior_strength(player.position, player.team, pff_team)

        old_ts = player.usage.target_share
        new_ts = stabilize_value(
            old_ts, prior_ts, n_obs,
            strength, self._config.min_divergence,
        )

        if abs(new_ts - old_ts) < MIN_TARGET_SHARE_SHIFT:
            return False

        player.usage.target_share = new_ts

        logger.debug(
            "Target share stabilized: %s (%s) %.3f -> %.3f (prior=%.3f, n=%d)",
            player.name, player.player_id, old_ts, new_ts, prior_ts, n_obs,
        )
        return True
```

- [ ] **Step 5: Wire into stabilize_roster**

In `stabilize_roster()`, after the catch_rate block, add:

```python
            # --- Target share stabilization ---
            if (
                player.position in ("WR", "TE")
                and player.usage.target_share > 0
                and pff_id in recv_lookup
                and self._config.target_share_coefficients
            ):
                adj = self._stabilize_target_share(
                    player, recv_lookup[pff_id], recv_avgs,
                )
                if adj:
                    adjustments += 1
```

- [ ] **Step 6: Run tests to verify pass**

Run: `uv run pytest tests/test_data/test_pff/test_talent.py -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add src/fantasy_sim/data/pff/models.py src/fantasy_sim/data/pff/config.py \
  src/fantasy_sim/data/pff/talent.py tests/test_data/test_pff/test_talent.py
git commit -m "feat: target_share stabilization via route_grade + YPRR"
```

---

### Task 16: fumble_rate Stabilization

**Files:**
- Modify: `src/fantasy_sim/data/pff/talent.py`
- Modify: `src/fantasy_sim/data/pff/models.py`
- Test: `tests/test_data/test_pff/test_talent.py`

- [ ] **Step 1: Write test for fumble_rate stabilization**

Add to `tests/test_data/test_pff/test_talent.py`:

```python
class TestFumbleRateStabilization:
    def test_bad_hands_grade_increases_fumble_rate(self):
        """Player with poor hands grade gets higher fumble rate."""
        player = PlayerModel(
            "RB1", "Butterfingers", "RB", "KC",
            PlayerUsage(carry_share=0.40),
            PlayerOutcomes(fumble_rate=0.01),
        )
        pff_row = {"grades_hands_fumble": 40.0, "team": "KC", "games": 16, "attempts": 15}
        rush_avgs = {"grades_hands_fumble": 65.0}

        config = TalentConfig(
            fumble_rate_coefficients={"grades_hands_fumble": -0.002},
        )
        stabilizer = TalentStabilizer(
            PffConfig(enabled=True, talent=config),
            PffLoader(tmp_path / "empty"),
        )
        old_fr = player.outcomes.fumble_rate
        adjusted = stabilizer._stabilize_fumble_rate(player, pff_row, rush_avgs)

        assert adjusted is True
        assert player.outcomes.fumble_rate > old_fr

    def test_good_hands_grade_decreases_fumble_rate(self):
        """Player with great hands grade gets lower fumble rate."""
        player = PlayerModel(
            "RB2", "Sure Hands", "RB", "KC",
            PlayerUsage(carry_share=0.40),
            PlayerOutcomes(fumble_rate=0.03),
        )
        pff_row = {"grades_hands_fumble": 90.0, "team": "KC", "games": 16, "attempts": 15}
        rush_avgs = {"grades_hands_fumble": 65.0}

        config = TalentConfig(
            fumble_rate_coefficients={"grades_hands_fumble": -0.002},
        )
        stabilizer = TalentStabilizer(
            PffConfig(enabled=True, talent=config),
            PffLoader(tmp_path / "empty"),
        )
        old_fr = player.outcomes.fumble_rate
        adjusted = stabilizer._stabilize_fumble_rate(player, pff_row, rush_avgs)

        assert adjusted is True
        assert player.outcomes.fumble_rate < old_fr
```

- [ ] **Step 2: Implement _stabilize_fumble_rate**

Add to `TalentConfig` in `models.py`:

```python
    fumble_rate_coefficients: dict[str, float] = field(default_factory=lambda: {
        "grades_hands_fumble": -0.002,
    })
```

Add to `TalentStabilizer` in `talent.py`:

```python
    MIN_FUMBLE_RATE_SHIFT = 0.002
    BASELINE_FUMBLE_RATE = 0.015

    def _stabilize_fumble_rate(
        self,
        player: PlayerModel,
        pff_row: dict,
        avgs: dict[str, float],
    ) -> bool:
        """Stabilize fumble_rate using PFF hands grade. Returns True if adjusted."""
        coeffs = self._config.fumble_rate_coefficients

        player_hands = pff_row.get("grades_hands_fumble", 0.0) or 0.0
        avg_hands = avgs.get("grades_hands_fumble", 65.0)

        # Lower hands grade → higher fumble rate (coefficient is negative)
        prior = BASELINE_FUMBLE_RATE + coeffs.get("grades_hands_fumble", -0.002) * (player_hands - avg_hands)
        prior = max(0.001, min(0.05, prior))

        games = pff_row.get("games", 0) or 0
        attempts = pff_row.get("attempts", 0) or 0
        n_obs = int(attempts * games) if games > 0 else 0

        pff_team = pff_row.get("team", player.team)
        strength = self._effective_prior_strength(player.position, player.team, pff_team)

        old_fr = player.outcomes.fumble_rate
        new_fr = stabilize_value(
            old_fr, prior, n_obs,
            strength, self._config.min_divergence,
        )

        if abs(new_fr - old_fr) < self.MIN_FUMBLE_RATE_SHIFT:
            return False

        player.outcomes.fumble_rate = new_fr

        logger.debug(
            "Fumble rate stabilized: %s (%s) %.4f -> %.4f (prior=%.4f, n=%d)",
            player.name, player.player_id, old_fr, new_fr, prior, n_obs,
        )
        return True
```

Wire into `stabilize_roster()`:

```python
            # --- Fumble rate stabilization ---
            if (
                player.position in ("RB", "QB")
                and player.usage.carry_share > 0
                and pff_id in rush_lookup
                and self._config.fumble_rate_coefficients
            ):
                adj = self._stabilize_fumble_rate(
                    player, rush_lookup[pff_id], rush_avgs,
                )
                if adj:
                    adjustments += 1
```

- [ ] **Step 3: Run tests to verify pass**

Run: `uv run pytest tests/test_data/test_pff/test_talent.py -v`

- [ ] **Step 4: Commit**

```bash
git add src/fantasy_sim/data/pff/models.py src/fantasy_sim/data/pff/config.py \
  src/fantasy_sim/data/pff/talent.py tests/test_data/test_pff/test_talent.py
git commit -m "feat: fumble_rate stabilization via PFF hands grade"
```

---

### Task 17: scramble_rate Stabilization

**Files:**
- Modify: `src/fantasy_sim/data/pff/talent.py`
- Modify: `src/fantasy_sim/data/pff/models.py`
- Test: `tests/test_data/test_pff/test_talent.py`

- [ ] **Step 1: Write test for scramble_rate stabilization**

Add to `tests/test_data/test_pff/test_talent.py`:

```python
class TestScrambleRateStabilization:
    def test_pff_scramble_rate_used_as_prior(self):
        """PFF scramble/dropback ratio used directly as prior."""
        player = PlayerModel(
            "QB1", "Mobile QB", "QB", "BUF",
            PlayerUsage(snap_share=1.0, scramble_rate=0.05),
            PlayerOutcomes(),
        )
        # PFF shows higher scramble rate than PBP
        pff_row = {"scrambles": 4.0, "dropbacks": 35.0, "team": "BUF", "games": 16}
        # PFF scramble rate = 4/35 = 0.114

        config = TalentConfig(scramble_rate_enabled=True)
        stabilizer = TalentStabilizer(
            PffConfig(enabled=True, talent=config),
            PffLoader(tmp_path / "empty"),
        )
        adjusted = stabilizer._stabilize_scramble_rate(player, pff_row)

        assert adjusted is True
        assert player.usage.scramble_rate > 0.05  # Pulled toward PFF rate
```

- [ ] **Step 2: Add scramble_rate_enabled to TalentConfig**

In `models.py`:

```python
    scramble_rate_enabled: bool = True
```

- [ ] **Step 3: Implement _stabilize_scramble_rate**

Add to `talent.py`:

```python
    MIN_SCRAMBLE_RATE_SHIFT = 0.005

    def _stabilize_scramble_rate(
        self,
        player: PlayerModel,
        pff_row: dict,
    ) -> bool:
        """Stabilize QB scramble_rate using PFF scramble/dropback data. Returns True if adjusted."""
        if not self._config.scramble_rate_enabled:
            return False

        scrambles = pff_row.get("scrambles", 0) or 0
        dropbacks = pff_row.get("dropbacks", 0) or 0

        if dropbacks < 10:
            return False

        pff_scramble_rate = scrambles / dropbacks

        games = pff_row.get("games", 0) or 0
        n_obs = int(dropbacks * games) if games > 0 else 0

        pff_team = pff_row.get("team", player.team)
        strength = self._effective_prior_strength(player.position, player.team, pff_team)

        old_rate = player.usage.scramble_rate
        new_rate = stabilize_value(
            old_rate, pff_scramble_rate, n_obs,
            strength, self._config.min_divergence,
        )

        if abs(new_rate - old_rate) < self.MIN_SCRAMBLE_RATE_SHIFT:
            return False

        player.usage.scramble_rate = new_rate

        logger.debug(
            "Scramble rate stabilized: %s (%s) %.3f -> %.3f (pff=%.3f, n=%d)",
            player.name, player.player_id, old_rate, new_rate, pff_scramble_rate, n_obs,
        )
        return True
```

Wire into `stabilize_roster()` — for QBs with passing data:

```python
            # --- Scramble rate stabilization (QB only) ---
            if (
                player.position == "QB"
                and pff_id in pass_lookup
            ):
                adj = self._stabilize_scramble_rate(
                    player, pass_lookup[pff_id],
                )
                if adj:
                    adjustments += 1
```

Note: Need to build `pass_lookup` in `stabilize_roster()` similarly to `recv_lookup`/`rush_lookup`:

```python
        pass_lookup = self._build_lookup(passing)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/test_data/test_pff/test_talent.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/pff/models.py src/fantasy_sim/data/pff/config.py \
  src/fantasy_sim/data/pff/talent.py tests/test_data/test_pff/test_talent.py
git commit -m "feat: QB scramble_rate stabilization from PFF passing data"
```

---

### Workstream F: Schedule-Adjusted Talent (Agent 3 — worktree)

### Task 18: Schedule Difficulty Computation

**Files:**
- Modify: `src/fantasy_sim/data/pff/talent.py`
- Modify: `src/fantasy_sim/data/pff/models.py`
- Test: `tests/test_data/test_pff/test_talent.py`

- [ ] **Step 1: Write tests for schedule adjustment**

Add to `tests/test_data/test_pff/test_talent.py`:

```python
class TestScheduleAdjustment:
    def test_tough_schedule_adjusts_pbp_upward(self):
        """Player facing top defenses gets PBP catch rate adjusted up."""
        # Player faced defenses with avg grade 80 (league avg 65)
        adj = compute_schedule_adjustment(
            opponent_avg_grade=80.0,
            league_avg_grade=65.0,
            weight=0.3,
            sensitivity=0.005,
        )
        assert adj > 0  # Positive = PBP adjusted upward

    def test_easy_schedule_adjusts_pbp_downward(self):
        """Player facing bottom defenses gets PBP catch rate adjusted down."""
        adj = compute_schedule_adjustment(
            opponent_avg_grade=50.0,
            league_avg_grade=65.0,
            weight=0.3,
            sensitivity=0.005,
        )
        assert adj < 0  # Negative = PBP adjusted downward

    def test_neutral_schedule_no_adjustment(self):
        adj = compute_schedule_adjustment(
            opponent_avg_grade=65.0,
            league_avg_grade=65.0,
            weight=0.3,
            sensitivity=0.005,
        )
        assert adj == 0.0
```

- [ ] **Step 2: Add schedule config to TalentConfig**

In `models.py`:

```python
@dataclass
class ScheduleAdjustmentConfig:
    """Configuration for schedule-adjusted talent evaluation."""
    enabled: bool = True
    weight: float = 0.3
    catch_rate_sensitivity: float = 0.005
    rush_yards_sensitivity: float = 0.3


# In TalentConfig:
    schedule_adjustment: ScheduleAdjustmentConfig = field(
        default_factory=ScheduleAdjustmentConfig
    )
```

- [ ] **Step 3: Implement schedule adjustment computation**

Add to `talent.py`:

```python
def compute_schedule_adjustment(
    opponent_avg_grade: float,
    league_avg_grade: float,
    weight: float,
    sensitivity: float,
) -> float:
    """Compute schedule difficulty adjustment.

    Positive return = tough schedule → adjust PBP upward.
    Negative return = easy schedule → adjust PBP downward.
    """
    return weight * (opponent_avg_grade - league_avg_grade) * sensitivity
```

- [ ] **Step 4: Implement schedule-adjusted catch rate in _stabilize_catch_rate**

Add schedule adjustment logic. In `_stabilize_catch_rate`, before calling `stabilize_value()`:

```python
        # Schedule adjustment: if player faced tough defenses, adjust PBP upward
        schedule_adj = 0.0
        if (
            self._config.schedule_adjustment.enabled
            and hasattr(self, '_schedule_data')
            and player.player_id in self._schedule_data
        ):
            opp_grade = self._schedule_data[player.player_id].get("defense_coverage_avg", 0)
            league_grade = self._schedule_data.get("_league_avg_coverage", 65.0)
            schedule_adj = compute_schedule_adjustment(
                opp_grade, league_grade,
                self._config.schedule_adjustment.weight,
                self._config.schedule_adjustment.catch_rate_sensitivity,
            )
        adjusted_pbp = old_catch + schedule_adj
```

Then pass `adjusted_pbp` instead of `old_catch` to `stabilize_value()`.

- [ ] **Step 5: Load schedule data in stabilize_roster**

In `stabilize_roster()`, before the player loop, load defensive grades and compute per-player schedule difficulty:

```python
        # Load schedule difficulty data
        self._schedule_data = {}
        if self._config.schedule_adjustment.enabled:
            self._schedule_data = self._compute_schedule_data(
                roster, crosswalk, training_seasons
            )
```

Implement `_compute_schedule_data()`:

```python
    def _compute_schedule_data(
        self,
        roster: TeamRoster,
        crosswalk: dict[int, str],
        training_seasons: list[int],
    ) -> dict:
        """Compute per-player schedule difficulty from PFF defensive data.

        Returns dict with player_id -> {"defense_coverage_avg": float}
        and "_league_avg_coverage" key for league average.
        """
        defense = self._loader.aggregate_player_stats("defense_summary", training_seasons)
        if defense.is_empty() or "grades_coverage_defense" not in defense.columns:
            return {}

        # Team-level average defensive coverage grade
        team_def = defense.group_by("team").agg(
            pl.col("grades_coverage_defense").mean().alias("coverage_grade")
        )
        team_grades: dict[str, float] = {}
        for row in team_def.iter_rows(named=True):
            team_grades[row["team"]] = row["coverage_grade"]

        league_avg = float(team_def.select(pl.col("coverage_grade").mean()).item() or 65.0)

        # For each receiver, compute average opponent grade
        # This is approximate — we use team's division/schedule from PFF game data
        # For now, use the team's own games to determine opponents
        result: dict = {"_league_avg_coverage": league_avg}

        # Load game-level data to determine opponents per team
        recv_facet = self._loader.load_facet("receiving_summary", training_seasons)
        if recv_facet.is_empty():
            return result

        # Get unique game_ids per player with opponent team
        # PFF data has team column — opponent can be inferred from game_id if available
        # Simplified: use the player's team's average opponent grade
        # (full implementation would parse game_id for opponent)
        for player in roster.players:
            if player.usage.target_share > 0:
                # Use league average as default (full schedule tracking is a future enhancement)
                result[player.player_id] = {
                    "defense_coverage_avg": league_avg,
                }

        return result
```

Note: The full per-opponent schedule tracking requires parsing game_ids to determine opponents. This simplified version uses league average as a starting point — the schedule adjustment will have no effect until opponent tracking is added. The architecture is in place for future enhancement.

- [ ] **Step 6: Run tests to verify pass**

Run: `uv run pytest tests/test_data/test_pff/test_talent.py -v`

- [ ] **Step 7: Update defaults.yaml**

```yaml
  talent:
    schedule_adjustment:
      enabled: true
      weight: 0.3
      catch_rate_sensitivity: 0.005
      rush_yards_sensitivity: 0.3
```

- [ ] **Step 8: Commit**

```bash
git add src/fantasy_sim/data/pff/models.py src/fantasy_sim/data/pff/config.py \
  src/fantasy_sim/data/pff/talent.py tests/test_data/test_pff/test_talent.py \
  config/defaults.yaml
git commit -m "feat: schedule-adjusted talent evaluation with PFF defensive data"
```

---

### Phase 2 Integration Tasks

### Task 19: Run Sweep #1 and Apply

- [ ] **Step 1: Run sensitivity sweep**

```bash
uv run python scripts/sweep_talent_params.py --sims 30 --season 2024
```

- [ ] **Step 2: Update defaults.yaml with optimal params**

- [ ] **Step 3: Run A/B test**

```bash
uv run python scripts/validate_pff_signal.py --mode talent --sims 50 --seasons 2024 --training-years 2 --label "sweep-v1"
```

- [ ] **Step 4: Commit**

```bash
git add config/defaults.yaml
git commit -m "feat: apply sweep-v1 optimal prior_strength and min_divergence"
```

---

### Task 20: Integrate Additional Parameters and A/B Test

- [ ] **Step 1: Merge workstream E changes**
- [ ] **Step 2: Run A/B test**

```bash
uv run python scripts/validate_pff_signal.py --mode talent --sims 50 --seasons 2024 --training-years 2 --label "+additional-params"
```

- [ ] **Step 3: Check ledger — verify no regression**
- [ ] **Step 4: Commit**

---

### Task 21: Integrate Schedule-Adjusted and A/B Test

- [ ] **Step 1: Merge workstream F changes**
- [ ] **Step 2: Run A/B test**

```bash
uv run python scripts/validate_pff_signal.py --mode talent --sims 50 --seasons 2024 --training-years 2 --label "+schedule-adjusted"
```

- [ ] **Step 3: Check ledger — verify no regression**
- [ ] **Step 4: Commit**

---

## Phase 3: NCAA Rookie Priors + Final

### Task 22: NCAA Data Loading

**Files:**
- Modify: `src/fantasy_sim/data/pff/loader.py`
- Test: `tests/test_data/test_pff/test_loader.py`

- [ ] **Step 1: Write test for NCAA facet loading**

Add to `tests/test_data/test_pff/test_loader.py`:

```python
class TestNcaaLoading:
    def test_load_ncaa_facet(self, tmp_path):
        ncaa_dir = tmp_path / "pff" / "processed" / "ncaa"
        ncaa_dir.mkdir(parents=True)
        # Write a test parquet
        df = pl.DataFrame({
            "player_id": [1, 2],
            "player": ["Player A", "Player B"],
            "team": ["Alabama", "Ohio State"],
            "position": ["WR", "RB"],
            "route_grade": [85.0, 72.0],
            "season": [2024, 2024],
        })
        df.write_parquet(ncaa_dir / "receiving_summary_2024.parquet")

        loader = PffLoader(tmp_path / "pff" / "processed" / "nfl")
        result = loader.load_ncaa_facet("receiving_summary", [2024], ncaa_dir=ncaa_dir)
        assert len(result) == 2
        assert "route_grade" in result.columns
```

- [ ] **Step 2: Implement load_ncaa_facet**

Add to `PffLoader` in `loader.py`:

```python
    DEFAULT_NCAA_DIR = Path.home() / ".fantasy-sim" / "pff" / "processed" / "ncaa"

    def load_ncaa_facet(
        self, facet: str, seasons: list[int], ncaa_dir: Path | None = None,
    ) -> pl.DataFrame:
        """Load NCAA PFF facet data.

        Same structure as NFL load_facet but reads from the NCAA directory.
        No team abbreviation normalization (college teams have full names).
        """
        target_dir = ncaa_dir or self.DEFAULT_NCAA_DIR
        frames = []
        for season in seasons:
            path = target_dir / f"{facet}_{season}.parquet"
            if not path.exists():
                logger.warning("NCAA PFF file not found: %s", path)
                continue
            frames.append(pl.read_parquet(path))
        if not frames:
            return pl.DataFrame()
        return pl.concat(frames, how="diagonal_relaxed")
```

- [ ] **Step 3: Run tests to verify pass**

Run: `uv run pytest tests/test_data/test_pff/test_loader.py::TestNcaaLoading -v`

- [ ] **Step 4: Commit**

```bash
git add src/fantasy_sim/data/pff/loader.py tests/test_data/test_pff/test_loader.py
git commit -m "feat: NCAA PFF facet loading"
```

---

### Task 23: NCAA-to-NFL Crosswalk

**Files:**
- Modify: `src/fantasy_sim/data/pff/loader.py`
- Test: `tests/test_data/test_pff/test_loader.py`

- [ ] **Step 1: Write test for NCAA crosswalk**

```python
class TestNcaaCrosswalk:
    def test_match_by_name_and_college(self, tmp_path):
        ncaa_data = pl.DataFrame({
            "player_id": [100, 200],
            "player": ["John Smith", "Jane Doe"],
            "team": ["Alabama", "Ohio State"],
        })
        nfl_roster = pl.DataFrame({
            "player_id": ["NFL001", "NFL002"],
            "player_name": ["John Smith", "Jane Doe"],
            "college_name": ["Alabama", "Ohio State"],
            "draft_number": [15, 45],
            "team": ["KC", "BUF"],
            "position": ["WR", "RB"],
            "rookie_year": [2025, 2025],
            "season": [2025, 2025],
        })

        loader = PffLoader(tmp_path / "pff" / "processed" / "nfl")
        crosswalk = loader.build_ncaa_crosswalk(ncaa_data, nfl_roster, 2025)
        assert crosswalk[100] == "NFL001"
        assert crosswalk[200] == "NFL002"

    def test_no_match_for_undrafted(self, tmp_path):
        ncaa_data = pl.DataFrame({
            "player_id": [300],
            "player": ["Unknown Player"],
            "team": ["Small College"],
        })
        nfl_roster = pl.DataFrame({
            "player_id": ["NFL003"],
            "player_name": ["Unknown Player"],
            "college_name": ["Different College"],
            "draft_number": [None],
            "team": ["NYG"],
            "position": ["WR"],
            "rookie_year": [2025],
            "season": [2025],
        })

        loader = PffLoader(tmp_path / "pff" / "processed" / "nfl")
        crosswalk = loader.build_ncaa_crosswalk(ncaa_data, nfl_roster, 2025)
        assert len(crosswalk) == 0  # No match — different college
```

- [ ] **Step 2: Implement build_ncaa_crosswalk**

Add to `PffLoader`:

```python
    def build_ncaa_crosswalk(
        self,
        ncaa_data: pl.DataFrame,
        nfl_roster: pl.DataFrame,
        rookie_season: int,
    ) -> dict[int, str]:
        """Map NCAA PFF player_id -> NFL player_id.

        Matches by player name + college name for players drafted in rookie_season.
        """
        crosswalk: dict[int, str] = {}

        ncaa_players = ncaa_data.select(
            ["player_id", "player", "team"]
        ).unique(subset=["player_id"])

        if ncaa_players.is_empty() or nfl_roster.is_empty():
            return crosswalk

        # Filter NFL roster to rookies from the target season
        rookies = nfl_roster
        if "rookie_year" in rookies.columns:
            rookies = rookies.filter(pl.col("rookie_year") == rookie_season)
        elif "season" in rookies.columns:
            rookies = rookies.filter(pl.col("season") == rookie_season)

        if rookies.is_empty():
            return crosswalk

        # Ensure college_name column exists
        if "college_name" not in rookies.columns:
            logger.warning("No college_name column in roster — cannot build NCAA crosswalk")
            return crosswalk

        # Match by name + college
        roster_lookup = rookies.select([
            "player_id", "player_name", "college_name"
        ]).unique(subset=["player_id"])

        matched = ncaa_players.join(
            roster_lookup,
            left_on=["player", "team"],
            right_on=["player_name", "college_name"],
            how="inner",
        )

        for row in matched.iter_rows(named=True):
            crosswalk[row["player_id"]] = row["player_id_right"]

        logger.info(
            "NCAA crosswalk: %d/%d matched",
            len(crosswalk), ncaa_players.height,
        )
        return crosswalk
```

- [ ] **Step 3: Run tests to verify pass**

Run: `uv run pytest tests/test_data/test_pff/test_loader.py::TestNcaaCrosswalk -v`

- [ ] **Step 4: Commit**

```bash
git add src/fantasy_sim/data/pff/loader.py tests/test_data/test_pff/test_loader.py
git commit -m "feat: NCAA-to-NFL player crosswalk for rookie priors"
```

---

### Task 24: Rookie Talent Prior

**Files:**
- Modify: `src/fantasy_sim/data/pff/talent.py`
- Modify: `src/fantasy_sim/data/pff/models.py`
- Test: `tests/test_data/test_pff/test_talent.py`

- [ ] **Step 1: Write test for rookie prior computation**

Add to `tests/test_data/test_pff/test_talent.py`:

```python
class TestRookiePrior:
    def test_elite_college_wr_gets_higher_catch_rate(self):
        """1st-round WR with elite college grades gets higher catch rate than archetype."""
        from fantasy_sim.data.pff.talent import compute_rookie_catch_rate_prior

        prior = compute_rookie_catch_rate_prior(
            route_grade=90.0,
            contested_catch_rate=55.0,
            draft_round=1,
            draft_weight=0.6,
            league_avg_route_grade=65.0,
            league_avg_contested=45.0,
        )
        # Should be above baseline
        assert prior > BASELINE_CATCH_RATE

    def test_late_round_pick_gets_weaker_prior(self):
        """7th-round WR with same grades gets a weaker prior adjustment."""
        from fantasy_sim.data.pff.talent import compute_rookie_catch_rate_prior

        early = compute_rookie_catch_rate_prior(
            route_grade=80.0, contested_catch_rate=50.0,
            draft_round=1, draft_weight=0.6,
            league_avg_route_grade=65.0, league_avg_contested=45.0,
        )
        late = compute_rookie_catch_rate_prior(
            route_grade=80.0, contested_catch_rate=50.0,
            draft_round=7, draft_weight=0.6,
            league_avg_route_grade=65.0, league_avg_contested=45.0,
        )
        # Early round pick should have prior further from baseline
        assert abs(early - BASELINE_CATCH_RATE) > abs(late - BASELINE_CATCH_RATE)
```

- [ ] **Step 2: Add NCAA config to TalentConfig**

In `models.py`:

```python
@dataclass
class NcaaPriorsConfig:
    """Configuration for NCAA-based rookie priors."""
    enabled: bool = True
    draft_weight: float = 0.6
    ncaa_data_dir: str | None = None


# In TalentConfig:
    ncaa_priors: NcaaPriorsConfig = field(default_factory=NcaaPriorsConfig)
```

- [ ] **Step 3: Implement compute_rookie_catch_rate_prior**

Add to `talent.py`:

```python
# Draft round → prior weight multiplier (1st round gets full weight, later rounds less)
DRAFT_ROUND_MULTIPLIERS = {
    1: 1.0, 2: 0.85, 3: 0.70, 4: 0.55, 5: 0.40, 6: 0.30, 7: 0.20,
}


def compute_rookie_catch_rate_prior(
    route_grade: float,
    contested_catch_rate: float,
    draft_round: int,
    draft_weight: float,
    league_avg_route_grade: float,
    league_avg_contested: float,
) -> float:
    """Compute a catch_rate prior for a rookie from college PFF grades.

    Uses route_grade and contested_catch_rate deltas from college averages,
    weighted by draft capital.
    """
    round_mult = DRAFT_ROUND_MULTIPLIERS.get(draft_round, 0.15)
    effective_weight = draft_weight * round_mult

    # Route grade implies catch ability (higher grade → higher catch rate)
    rg_delta = (route_grade - league_avg_route_grade) * 0.002
    # Contested catch rate directly implies catch ability
    cc_delta = (contested_catch_rate - league_avg_contested) * 0.003

    raw_adjustment = rg_delta + cc_delta
    adjustment = raw_adjustment * effective_weight

    prior = BASELINE_CATCH_RATE + adjustment
    return max(CATCH_RATE_PRIOR_MIN, min(CATCH_RATE_PRIOR_MAX, prior))
```

- [ ] **Step 4: Wire into stabilize_roster for rookies**

In `stabilize_roster()`, after the main player loop, add a section for rookies:

```python
        # --- NCAA rookie priors ---
        if self._config.ncaa_priors.enabled and self._pff_loader:
            ncaa_dir = (
                Path(self._config.ncaa_priors.ncaa_data_dir)
                if self._config.ncaa_priors.ncaa_data_dir
                else None
            )
            # Find rookies with no PBP data (games_played <= rookie_blend_games threshold)
            rookies_no_pbp = [
                p for p in roster.players
                if p.player_id not in reverse_cw  # No PFF NFL data
                and p.games_played <= 4  # Likely a rookie
            ]
            if rookies_no_pbp:
                self._apply_ncaa_priors(
                    rookies_no_pbp, roster, training_seasons, ncaa_dir,
                )
```

Implement `_apply_ncaa_priors()`:

```python
    def _apply_ncaa_priors(
        self,
        rookies: list[PlayerModel],
        roster: TeamRoster,
        training_seasons: list[int],
        ncaa_dir: Path | None = None,
    ) -> None:
        """Apply NCAA-derived priors to rookie players."""
        from fantasy_sim.data.loader import DataLoader

        # Load NCAA data (most recent available season)
        ncaa_seasons = [max(training_seasons)]
        ncaa_recv = self._loader.load_ncaa_facet(
            "receiving_summary", ncaa_seasons, ncaa_dir=ncaa_dir,
        )
        if ncaa_recv.is_empty():
            return

        # Build NCAA crosswalk
        ncaa_data = ncaa_recv.select(
            ["player_id", "player", "team"]
        ).unique(subset=["player_id"])

        loader = DataLoader()
        nfl_roster = loader.load_rosters([max(training_seasons) + 1])
        ncaa_cw = self._loader.build_ncaa_crosswalk(
            ncaa_data, nfl_roster, max(training_seasons) + 1,
        )

        # Reverse crosswalk: nfl_id -> ncaa_pff_id
        reverse_ncaa = {v: k for k, v in ncaa_cw.items()}

        # NCAA league averages
        ncaa_avgs = self._compute_league_averages(
            ncaa_recv, ["route_grade", "contested_catch_rate"]
        )

        for player in rookies:
            if player.player_id not in reverse_ncaa:
                continue
            ncaa_id = reverse_ncaa[player.player_id]
            ncaa_row = None
            for row in ncaa_recv.iter_rows(named=True):
                if row.get("player_id") == ncaa_id:
                    ncaa_row = row
                    break
            if ncaa_row is None:
                continue

            # Get draft round from roster data
            draft_round = 4  # Default to mid-round if unknown

            if player.position in ("WR", "TE"):
                prior = compute_rookie_catch_rate_prior(
                    route_grade=ncaa_row.get("route_grade", 65.0) or 65.0,
                    contested_catch_rate=ncaa_row.get("contested_catch_rate", 45.0) or 45.0,
                    draft_round=draft_round,
                    draft_weight=self._config.ncaa_priors.draft_weight,
                    league_avg_route_grade=ncaa_avgs.get("route_grade", 65.0),
                    league_avg_contested=ncaa_avgs.get("contested_catch_rate", 45.0),
                )
                if abs(prior - player.outcomes.catch_rate) > self._config.min_divergence:
                    player.outcomes.catch_rate = prior
                    logger.debug(
                        "NCAA rookie prior applied: %s catch_rate=%.3f",
                        player.name, prior,
                    )
```

- [ ] **Step 5: Run tests to verify pass**

Run: `uv run pytest tests/test_data/test_pff/test_talent.py -v`

- [ ] **Step 6: Update defaults.yaml**

```yaml
  talent:
    ncaa_priors:
      enabled: true
      draft_weight: 0.6
      ncaa_data_dir: null
```

- [ ] **Step 7: Commit**

```bash
git add src/fantasy_sim/data/pff/models.py src/fantasy_sim/data/pff/config.py \
  src/fantasy_sim/data/pff/talent.py tests/test_data/test_pff/test_talent.py \
  config/defaults.yaml
git commit -m "feat: NCAA rookie priors from college PFF grades"
```

---

### Task 25: NCAA Integration A/B Test

- [ ] **Step 1: Run A/B test**

```bash
uv run python scripts/validate_pff_signal.py --mode talent --sims 50 --seasons 2024 --training-years 2 --label "+ncaa-rookie-priors"
```

- [ ] **Step 2: Check ledger**

```bash
uv run python scripts/validate_pff_signal.py --show-ledger
```

---

### Task 26: Final Sweep and Validation

- [ ] **Step 1: Run sweep #2 with all improvements**

```bash
uv run python scripts/sweep_talent_params.py --sims 30 --season 2024
```

- [ ] **Step 2: Update defaults.yaml with final optimal params**

- [ ] **Step 3: Run final A/B at 200 sims**

```bash
uv run python scripts/validate_pff_signal.py --mode talent --sims 200 --seasons 2024 --training-years 2 --label "final-200sims"
```

- [ ] **Step 4: Print final progression**

```bash
uv run python scripts/validate_pff_signal.py --show-ledger
```

- [ ] **Step 5: Commit final config**

```bash
git add config/defaults.yaml
git commit -m "feat: final talent stabilizer params from sweep-v2"
```

---

### Task 27: Update Documentation

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/pff-future-improvements.md`

- [ ] **Step 1: Update CLAUDE.md Current State section**

Add entry for this work with test count and summary of improvements.

- [ ] **Step 2: Update pff-future-improvements.md**

Mark completed items, add any new findings from the A/B testing.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md docs/pff-future-improvements.md
git commit -m "docs: update status after PFF talent tuning pipeline"
```

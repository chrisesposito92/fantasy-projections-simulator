# Phase 6 Parked Levers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Phase 6 evidence trustworthy by fixing the parked-lever measurement path, aligning route-rate with the real NFL PFF store, and then retesting the still-parked default-off levers one at a time against the current default stack.

**Architecture:** Keep the runtime surface narrow. Slice A changes only validation coverage, route-rate data-path resolution, and canonical docs; it does not change default projection behavior. Slice B reuses the existing `scripts/validate.py` marginal-lift path for four isolated levers (`pff.team_context`, `usage.ngs`, `goal_line_concentration`, and `usage.route_rate`), with the roadmap and audit updated from the exact run output after each artifact.

**Tech Stack:** Python 3.14, polars, pathlib, pytest, YAML config, Click validation CLI

**Spec:** `docs/superpowers/specs/2026-04-14-phase-6-parked-levers-design.md`

---

## File Structure

- `src/fantasy_sim/validation/coverage.py`
  - add explicit coverage signals for the Phase 6 candidate levers and align route-rate with the same NFL PFF root used by runtime
- `src/fantasy_sim/data/loader.py`
  - make `load_pff_facet()` default to `~/.fantasy-sim/pff/processed/nfl/` so route-rate reads the real local NFL store
- `tests/test_validation/test_coverage.py`
  - assert full/partial/disabled reporting for `pff.team_context`, `goal_line_concentration`, `td_tendency`, `td_tendency.i5`, and the corrected route-rate path
- `tests/test_data/test_loader.py`
  - regression-test the default `load_pff_facet()` root
- `docs/accuracy-roadmap.md`
  - mark Phase 6 as current priority, remove stale parked-lever queue members, and then record the exact retest artifacts
- `docs/accuracy-stack-audit.md`
  - capture the corrected defaults, current local coverage, route-rate caveat/fix, and the exact retest artifacts

### Task 1: Add Explicit Phase 6 Coverage Signals

**Files:**
- Modify: `src/fantasy_sim/validation/coverage.py`
- Test: `tests/test_validation/test_coverage.py`

- [ ] **Step 1: Write the failing coverage tests**

Add these tests near the existing `pff.rb_scheme_fit`, `availability`, and disabled-signal tests in `tests/test_validation/test_coverage.py`:

```python
def test_pff_team_context_reports_full_when_pbp_and_pff_inputs_exist(tmp_path):
    pff_dir = tmp_path / "pff"
    cache_dir = tmp_path / "cache"
    for season in (2023, 2024):
        _write_parquet_placeholder(pff_dir / f"offense_run_blocking_{season}.parquet")
        _write_parquet_placeholder(pff_dir / f"passing_summary_{season}.parquet")
        _write_parquet_placeholder(cache_dir / f"pbp_{season}.parquet")

    engine_configs = _default_engine_configs()
    engine_configs["pff_config"].team_context.enabled = True

    coverage = collect_signal_coverage(
        engine_configs,
        [2023, 2024],
        pff_dir=pff_dir,
        cache_dir=cache_dir,
    )

    assert coverage["pff.team_context"] == SignalCoverage(
        enabled=True,
        status="full",
        covered_seasons=[2023, 2024],
        missing_seasons=[],
        note=(
            "Requires season PBP parquet plus offense_run_blocking and "
            "passing_summary parquet for the tested season"
        ),
    )


def test_goal_line_concentration_reports_full_without_external_inputs():
    coverage = collect_signal_coverage(
        {"goal_line_concentration": {"enabled": True}},
        [2023, 2024],
    )

    assert coverage["goal_line_concentration"] == SignalCoverage(
        enabled=True,
        status="full",
        covered_seasons=[2023, 2024],
        missing_seasons=[],
        note="Uses existing roster-share ordering only; no external historical store required",
    )


def test_td_tendency_and_i5_report_full_when_red_zone_inputs_exist(tmp_path):
    pff_dir = tmp_path / "pff"
    for season in (2023, 2024):
        _write_parquet_placeholder(pff_dir / f"fantasy_receiving_{season}.parquet")
        _write_parquet_placeholder(pff_dir / f"fantasy_passing_{season}.parquet")

    coverage = collect_signal_coverage(
        {"td_tendency": {"enabled": True, "i5_enabled": True}},
        [2023, 2024],
        pff_dir=pff_dir,
    )

    assert coverage["td_tendency"] == SignalCoverage(
        enabled=True,
        status="full",
        covered_seasons=[2023, 2024],
        missing_seasons=[],
        note=(
            "Requires fantasy_receiving and fantasy_passing parquet for the "
            "tested season; PBP fallback remains a runtime backstop"
        ),
    )
    assert coverage["td_tendency.i5"] == SignalCoverage(
        enabled=True,
        status="full",
        covered_seasons=[2023, 2024],
        missing_seasons=[],
        note=(
            "Requires fantasy_receiving and fantasy_passing parquet with inside-5 "
            "columns for the tested season; PBP fallback remains a runtime backstop"
        ),
    )


def test_phase6_signals_report_disabled_explicitly():
    coverage = collect_signal_coverage(
        {
            "pff": {"enabled": False, "team_context": {"enabled": True}},
            "goal_line_concentration": {"enabled": False},
            "td_tendency": {"enabled": False, "i5_enabled": False},
        },
        [2024],
    )

    assert coverage["pff.team_context"].status == "disabled"
    assert coverage["goal_line_concentration"].status == "disabled"
    assert coverage["td_tendency"].status == "disabled"
    assert coverage["td_tendency.i5"].status == "disabled"
```

- [ ] **Step 2: Run the coverage tests to verify they fail**

Run:

```bash
uv run pytest tests/test_validation/test_coverage.py -k "team_context or goal_line_concentration or td_tendency" -v
```

Expected: FAIL with missing-signal `KeyError`s such as `pff.team_context`,
`goal_line_concentration`, `td_tendency`, or `td_tendency.i5`.

- [ ] **Step 3: Implement the new coverage signals**

In `src/fantasy_sim/validation/coverage.py`, add the new enabled flags near the
other Phase 4/5 feature flags:

```python
    team_context_enabled = _signal_enabled(
        config,
        ("pff_config", "pff"),
        ("pff", "team_context"),
        nested_path=("team_context",),
    )
    goal_line_concentration_enabled = _signal_enabled(
        config,
        ("goal_line_concentration_config", "goal_line_concentration"),
        ("goal_line_concentration",),
    )
    td_tendency_enabled = _signal_enabled(
        config,
        ("td_tendency_config", "td_tendency"),
        ("td_tendency",),
    )
    td_tendency_i5_enabled = (
        td_tendency_enabled
        and _config_flag(
            config,
            ("td_tendency_config", "td_tendency"),
            ("td_tendency", "i5_enabled"),
            nested_path=("i5_enabled",),
            default=False,
        )
    )
```

Add required-path maps near the existing `qb_split_paths_by_season` and
`rb_scheme_fit_paths_by_season` blocks:

```python
    team_context_paths_by_season: dict[int, list[Path]] = {
        season: [
            cache_path / f"pbp_{season}.parquet",
            pff_path / f"offense_run_blocking_{season}.parquet",
            pff_path / f"passing_summary_{season}.parquet",
        ]
        for season in seasons
    }
    td_tendency_paths_by_season: dict[int, list[Path]] = {
        season: [
            pff_path / f"fantasy_receiving_{season}.parquet",
            pff_path / f"fantasy_passing_{season}.parquet",
        ]
        for season in seasons
    }
```

Return these explicit signals near the existing `pff.depth_role`,
`pff.qb_split`, `pff.rb_scheme_fit`, `usage.ngs`, and `availability.*` signals:

```python
        "pff.team_context": _build_signal(
            pff_enabled and team_context_enabled,
            seasons,
            _covered_seasons_from_required_paths(seasons, team_context_paths_by_season),
            note=(
                "Requires season PBP parquet plus offense_run_blocking and "
                "passing_summary parquet for the tested season"
            ),
        ),
        "goal_line_concentration": _build_signal(
            goal_line_concentration_enabled,
            seasons,
            seasons,
            note="Uses existing roster-share ordering only; no external historical store required",
        ),
        "td_tendency": _build_signal(
            td_tendency_enabled,
            seasons,
            _covered_seasons_from_required_paths(seasons, td_tendency_paths_by_season),
            note=(
                "Requires fantasy_receiving and fantasy_passing parquet for the "
                "tested season; PBP fallback remains a runtime backstop"
            ),
        ),
        "td_tendency.i5": _build_signal(
            td_tendency_i5_enabled,
            seasons,
            _covered_seasons_from_required_paths(seasons, td_tendency_paths_by_season),
            note=(
                "Requires fantasy_receiving and fantasy_passing parquet with inside-5 "
                "columns for the tested season; PBP fallback remains a runtime backstop"
            ),
        ),
```

Directive: use the nested signal name `td_tendency.i5`, not
`td_tendency.i5_enabled`, so the coverage helper stays consistent with existing
signal naming conventions like `usage.ngs` and `availability.injuries`.

- [ ] **Step 4: Run the coverage tests to verify they pass**

Run:

```bash
uv run pytest tests/test_validation/test_coverage.py -k "team_context or goal_line_concentration or td_tendency" -v
```

Expected: PASS with all four new Phase 6 signals reporting full/disabled
correctly.

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/validation/coverage.py tests/test_validation/test_coverage.py
git commit -m "feat: add phase 6 coverage signals"
```

### Task 2: Align Route-Rate With The Real NFL PFF Root

**Files:**
- Modify: `src/fantasy_sim/data/loader.py`
- Modify: `src/fantasy_sim/validation/coverage.py`
- Test: `tests/test_data/test_loader.py`
- Test: `tests/test_validation/test_coverage.py`

- [ ] **Step 1: Write the failing runtime and coverage regression tests**

Add this regression test to `tests/test_data/test_loader.py`:

```python
import fantasy_sim.data.loader as loader_module


def test_load_pff_facet_defaults_to_nfl_processed_root(loader, monkeypatch, tmp_path):
    pff_root = tmp_path / "pff" / "processed" / "nfl"
    pff_root.mkdir(parents=True, exist_ok=True)
    pl.DataFrame({"player_id": [101], "targets": [8]}).write_parquet(
        pff_root / "receiving_summary_2024.parquet"
    )
    monkeypatch.setattr(loader_module, "DEFAULT_PFF_DIR", pff_root)

    result = loader.load_pff_facet("receiving_summary", [2024])

    assert result.shape == (1, 2)
    assert result["player_id"].to_list() == [101]
```

Replace `test_default_roots_for_pff_and_route_rate_remain_separate` in
`tests/test_validation/test_coverage.py` with:

```python
def test_default_route_rate_root_matches_nfl_pff_root(monkeypatch, tmp_path):
    pff_root = tmp_path / "pff_processed_nfl"
    cache_dir = tmp_path / "cache"

    monkeypatch.setattr(coverage_module, "DEFAULT_PFF_DIR", pff_root)
    monkeypatch.setattr(coverage_module, "DEFAULT_PFF_ROUTE_RATE_DIR", pff_root)

    _write_default_pff_stack(pff_root, (2023, 2024))
    _write_roster_cache(cache_dir, (2023, 2024))

    engine_configs = _default_engine_configs()
    engine_configs["usage_config"] = UsageConfig()

    coverage = collect_signal_coverage(
        engine_configs,
        [2023, 2024],
        cache_dir=cache_dir,
    )

    assert coverage["pff"].status == "full"
    assert coverage["usage.route_rate"] == SignalCoverage(
        enabled=True,
        status="full",
        covered_seasons=[2023, 2024],
        missing_seasons=[],
        note=(
            "Requires the PFF summary trio from the NFL processed PFF root "
            "plus rosters_weekly cache to build the crosswalk"
        ),
    )
```

Update `test_typed_config_paths_override_module_defaults` so it writes the
route-rate trio into `pff_root` itself instead of `pff_root.parent`, and expect
the same note text ending with `NFL processed PFF root`.

- [ ] **Step 2: Run the regression tests to verify they fail**

Run:

```bash
uv run pytest tests/test_data/test_loader.py tests/test_validation/test_coverage.py -k "load_pff_facet_defaults_to_nfl_processed_root or route_rate_root_matches or typed_config_paths_override_module_defaults" -v
```

Expected: FAIL because `load_pff_facet()` still defaults to the processed parent
directory and the coverage helper still treats route-rate as a separate root.

- [ ] **Step 3: Implement the root alignment**

In `src/fantasy_sim/data/loader.py`, promote the default PFF root to a module
constant and point it at the NFL directory:

```python
DEFAULT_CACHE_DIR = Path.home() / ".fantasy-sim" / "cache"
DEFAULT_PFF_DIR = Path.home() / ".fantasy-sim" / "pff" / "processed" / "nfl"
```

Then update `load_pff_facet()`:

```python
    def load_pff_facet(
        self,
        facet: str,
        seasons: list[int],
        pff_dir: Path | None = None,
    ) -> pl.DataFrame:
        """Load a PFF processed facet from the NFL parquet cache."""
        target_dir = pff_dir or DEFAULT_PFF_DIR
        frames: list[pl.DataFrame] = []
        for season in seasons:
            path = target_dir / f"{facet}_{season}.parquet"
            if path.exists():
                frames.append(pl.read_parquet(path))
        if not frames:
            return pl.DataFrame()
        return pl.concat(frames, how="diagonal_relaxed")
```

In `src/fantasy_sim/validation/coverage.py`, make route-rate follow the same
NFL root:

```python
DEFAULT_PFF_ROUTE_RATE_DIR = DEFAULT_PFF_DIR
```

```python
def _resolve_route_rate_pff_path(config: object, pff_dir: str | Path | None) -> Path:
    return _resolve_pff_path(config, pff_dir)
```

Update the `collect_signal_coverage()` docstring and route-rate note text:

```python
    Route-rate follows the same NFL processed PFF root as the rest of the
    runtime PFF feature set.
```

```python
            "Requires the PFF summary trio from the NFL processed PFF root "
            "plus rosters_weekly cache to build the crosswalk"
```

- [ ] **Step 4: Run the regression tests to verify they pass**

Run:

```bash
uv run pytest tests/test_data/test_loader.py tests/test_validation/test_coverage.py -k "load_pff_facet_defaults_to_nfl_processed_root or route_rate_root_matches or typed_config_paths_override_module_defaults" -v
```

Expected: PASS with runtime and coverage both resolving route-rate from the
same NFL processed PFF root.

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/loader.py src/fantasy_sim/validation/coverage.py tests/test_data/test_loader.py tests/test_validation/test_coverage.py
git commit -m "fix: align route rate with nfl pff root"
```

### Task 3: Update The Canonical Docs For Phase 6 Slice A

**Files:**
- Modify: `docs/accuracy-roadmap.md`
- Modify: `docs/accuracy-stack-audit.md`

- [ ] **Step 1: Update `docs/accuracy-roadmap.md` to make Phase 6 the active priority**

Replace the current Phase 6 section and immediate-next-priority wording with
this exact structure:

```markdown
## Phase 6: Re-open Parked Levers Under The New Data Regime

### Status

In progress.

Slice A measurement cleanup is complete. The next work is isolated marginal
retests of the still-parked default-off levers.

### Phase 6 Queue

- `pff.team_context`
- `usage.ngs`
- `goal_line_concentration`
- `usage.route_rate`

### Not Part Of The Phase 6 Queue

- `td_tendency`
- `i5`

Reason:

- `td_tendency.enabled: true`
- `td_tendency.i5_enabled: true`

### Execution Rule

- finish the Phase 6 measurement cleanup first
- then retest one parked lever at a time against `baseline=defaults`
- do not bundle Phase 6 levers before an isolated retest wins
```

Update `## Immediate Next Planning Targets` so it reads:

```markdown
## Immediate Next Planning Targets

1. Phase 6 Slice B1: `pff.team_context` marginal retest
2. Phase 6 Slice B2: `usage.ngs` marginal retest
3. Phase 6 Slice B3+: remaining parked-lever retests one at a time
```

- [ ] **Step 2: Update `docs/accuracy-stack-audit.md` to reflect the verified Phase 6 starting point**

Make these exact content changes:

1. Change the opening snapshot line to:

```markdown
Research snapshot updated through the Phase 6 measurement-cleanup pass.
```

2. Add this section after the Phase 5 notes:

```markdown
## Phase 6 Current Priority

Phase 6 now targets only the still-parked default-off levers:

- `pff.team_context`
- `usage.ngs`
- `goal_line_concentration`
- `usage.route_rate`

Not part of the parked queue anymore:

- `td_tendency`
- `td_tendency.i5_enabled`

Slice A is now the current baseline:

- explicit coverage signals now exist for `pff.team_context`
- explicit coverage signals now exist for `goal_line_concentration`
- explicit coverage signals now exist for `td_tendency` and nested `td_tendency.i5`
- `usage.route_rate` now points at the NFL processed PFF root used by runtime
```

3. In the `Remaining Evaluation Caveats` area, remove any implication that
`td_tendency` or `i5` are still parked Phase 6 candidates.

- [ ] **Step 3: Verify the doc pass**

Run:

```bash
rg -n "td_tendency|i5|Phase 6|usage.route_rate|goal_line_concentration|pff.team_context" docs/accuracy-roadmap.md docs/accuracy-stack-audit.md
```

Expected:

- the roadmap Phase 6 queue contains only the four still-parked default-off levers
- `td_tendency` and `i5` remain documented as current defaults, not parked retest items
- the audit explicitly calls out the Phase 6 measurement cleanup work

- [ ] **Step 4: Commit**

```bash
git add docs/accuracy-roadmap.md docs/accuracy-stack-audit.md
git commit -m "docs: reset phase 6 parked lever queue"
```

### Task 4: Run And Record The `pff.team_context` Retest

**Files:**
- Modify: `docs/accuracy-roadmap.md`
- Modify: `docs/accuracy-stack-audit.md`

- [ ] **Step 1: Run the targeted verification suite**

Run:

```bash
uv run pytest \
  tests/test_validation/test_coverage.py \
  tests/test_data/test_pff/test_team_context.py \
  tests/test_data/test_pff/test_tier_engine.py -k "team_context" -v
```

Expected: PASS for the explicit coverage signal and the existing team-context
runtime behavior.

- [ ] **Step 2: Run the marginal validation artifact**

Run:

```bash
uv run python scripts/validate.py \
  --baseline defaults \
  --set pff.team_context.enabled=true \
  --sims 50 \
  --label "phase-6-pff-team-context-v1"
```

Expected coverage line:

```text
pff.team_context=full(2022,2023,2024)
```

- [ ] **Step 3: Update the roadmap with the exact artifact**

Add a Phase 6 subsection in `docs/accuracy-roadmap.md` using this exact shape:

```markdown
### `pff.team_context` Retest Artifact

- label: `phase-6-pff-team-context-v1`
- baseline: `defaults`
- comparison mode: `marginal_lift`
- coverage: copy the exact `pff.team_context=...` readout from the run
- result: copy the exact lines that start with:
  - `rank_corr delta:`
  - `weekly_mae delta:`
  - `season_mae delta:`
- verdict:
  - keep `pff.team_context.enabled: false` unless the isolated retest clearly improves weekly QB/WR ordering and avoids material season regression
```

Do not round or restate the numbers; copy the exact run output values.

- [ ] **Step 4: Update the audit with the exact artifact**

Add the same artifact to `docs/accuracy-stack-audit.md` in the Phase 6 area,
recording:

- the exact label
- the exact coverage line
- the exact top-line deltas
- the final keep-off or promote verdict

Keep the audit style consistent with the existing Phase 4 and Phase 5 sections:
built state, coverage, result, and verdict.

- [ ] **Step 5: Commit**

```bash
git add docs/accuracy-roadmap.md docs/accuracy-stack-audit.md
git commit -m "docs: record phase 6 team context retest"
```

### Task 5: Run And Record The `usage.ngs` Retest

**Files:**
- Modify: `docs/accuracy-roadmap.md`
- Modify: `docs/accuracy-stack-audit.md`

- [ ] **Step 1: Run the targeted verification suite**

Run:

```bash
uv run pytest \
  tests/test_validation/test_coverage.py \
  tests/test_data/test_usage/test_usage_engine.py \
  tests/test_data/test_usage/test_usage_integration.py -k "ngs" -v
```

Expected: PASS for NGS coverage reporting and the existing parked NGS runtime
path.

- [ ] **Step 2: Run the marginal validation artifact**

Run:

```bash
uv run python scripts/validate.py \
  --baseline defaults \
  --set usage.ngs.enabled=true \
  --sims 50 \
  --label "phase-6-usage-ngs-v1"
```

Expected coverage line:

```text
usage.ngs=full(2022,2023,2024)
```

- [ ] **Step 3: Update the roadmap with the exact artifact**

Add this subsection under Phase 6 in `docs/accuracy-roadmap.md`:

```markdown
### `usage.ngs` Retest Artifact

- label: `phase-6-usage-ngs-v1`
- baseline: `defaults`
- comparison mode: `marginal_lift`
- coverage: copy the exact `usage.ngs=...` readout from the run
- result: copy the exact lines that start with:
  - `rank_corr delta:`
  - `weekly_mae delta:`
  - `season_mae delta:`
- verdict:
  - keep `usage.ngs.enabled: false` unless the isolated retest clearly improves weekly QB/WR ordering and avoids material season regression
```

- [ ] **Step 4: Update the audit with the exact artifact**

Mirror the same artifact in `docs/accuracy-stack-audit.md`, preserving the
exact label, coverage, deltas, and verdict from the run output.

- [ ] **Step 5: Commit**

```bash
git add docs/accuracy-roadmap.md docs/accuracy-stack-audit.md
git commit -m "docs: record phase 6 usage ngs retest"
```

### Task 6: Run And Record The `goal_line_concentration` Retest

**Files:**
- Modify: `docs/accuracy-roadmap.md`
- Modify: `docs/accuracy-stack-audit.md`

- [ ] **Step 1: Run the targeted verification suite**

Run:

```bash
uv run pytest \
  tests/test_validation/test_coverage.py \
  tests/test_engine/test_player_selector.py \
  tests/test_engine/test_game_sim.py \
  tests/test_data/test_game_context.py -k "goal_line_concentration" -v
```

Expected: PASS for the explicit coverage signal and the existing runtime toggle.

- [ ] **Step 2: Run the marginal validation artifact**

Run:

```bash
uv run python scripts/validate.py \
  --baseline defaults \
  --set goal_line_concentration.enabled=true \
  --sims 50 \
  --label "phase-6-goal-line-concentration-v1"
```

Expected coverage line:

```text
goal_line_concentration=full(2022,2023,2024)
```

- [ ] **Step 3: Update the roadmap with the exact artifact**

Add this subsection under Phase 6 in `docs/accuracy-roadmap.md`:

```markdown
### `goal_line_concentration` Retest Artifact

- label: `phase-6-goal-line-concentration-v1`
- baseline: `defaults`
- comparison mode: `marginal_lift`
- coverage: copy the exact `goal_line_concentration=...` readout from the run
- result: copy the exact lines that start with:
  - `rank_corr delta:`
  - `weekly_mae delta:`
  - `season_mae delta:`
- verdict:
  - keep `goal_line_concentration.enabled: false` unless the isolated retest clearly improves weekly QB/WR ordering and avoids material season regression
```

- [ ] **Step 4: Update the audit with the exact artifact**

Mirror the same artifact in `docs/accuracy-stack-audit.md`, preserving the
exact label, coverage, deltas, and verdict from the run output.

- [ ] **Step 5: Commit**

```bash
git add docs/accuracy-roadmap.md docs/accuracy-stack-audit.md
git commit -m "docs: record phase 6 goal line retest"
```

### Task 7: Run And Record The `usage.route_rate` Retest

**Files:**
- Modify: `docs/accuracy-roadmap.md`
- Modify: `docs/accuracy-stack-audit.md`

- [ ] **Step 1: Run the targeted verification suite**

Run:

```bash
uv run pytest \
  tests/test_data/test_loader.py \
  tests/test_validation/test_coverage.py \
  tests/test_data/test_usage/test_usage_engine.py \
  tests/test_data/test_usage/test_usage_integration.py -k "route_rate or pff_facet" -v
```

Expected: PASS for the corrected route-rate data path, coverage reporting, and
runtime route-rate loader behavior.

- [ ] **Step 2: Run the marginal validation artifact**

Run:

```bash
uv run python scripts/validate.py \
  --baseline defaults \
  --set usage.route_rate.enabled=true \
  --sims 50 \
  --label "phase-6-usage-route-rate-v1"
```

Expected coverage line:

```text
usage.route_rate=full(2022,2023,2024)
```

- [ ] **Step 3: Update the roadmap with the exact artifact**

Add this subsection under Phase 6 in `docs/accuracy-roadmap.md`:

```markdown
### `usage.route_rate` Retest Artifact

- label: `phase-6-usage-route-rate-v1`
- baseline: `defaults`
- comparison mode: `marginal_lift`
- coverage: copy the exact `usage.route_rate=...` readout from the run
- result: copy the exact lines that start with:
  - `rank_corr delta:`
  - `weekly_mae delta:`
  - `season_mae delta:`
- verdict:
  - keep `usage.route_rate.enabled: false` unless the isolated retest clearly improves weekly QB/WR ordering and avoids material season regression
```

- [ ] **Step 4: Update the audit with the exact artifact**

Mirror the same artifact in `docs/accuracy-stack-audit.md`, preserving the
exact label, coverage, deltas, and verdict from the run output.

- [ ] **Step 5: Commit**

```bash
git add docs/accuracy-roadmap.md docs/accuracy-stack-audit.md
git commit -m "docs: record phase 6 route rate retest"
```

### Task 8: Reconcile Final Phase 6 Priority And Stop Conditions

**Files:**
- Modify: `docs/accuracy-roadmap.md`
- Modify: `docs/accuracy-stack-audit.md`

- [ ] **Step 1: Review the four isolated artifacts together**

Read the new ledger rows:

```bash
uv run python - <<'PY'
from fantasy_sim.validation.ledger import load_ledger

labels = {
    "phase-6-pff-team-context-v1",
    "phase-6-usage-ngs-v1",
    "phase-6-goal-line-concentration-v1",
    "phase-6-usage-route-rate-v1",
}

for entry in load_ledger():
    if entry.label in labels:
        print(entry.label)
        print("  avg_rank_corr_delta =", f"{entry.avg_rank_corr_delta:+.4f}")
        print("  avg_weekly_mae_delta =", f"{entry.avg_weekly_mae_delta:+.3f}")
        print("  avg_season_mae_delta =", f"{entry.avg_season_mae_delta:+.3f}")
PY
```

Expected: one block per completed Phase 6 retest.

- [ ] **Step 2: Update the roadmap’s next-priority note from the real results**

Use this exact rule in `docs/accuracy-roadmap.md`:

```markdown
### Next Priority

- if none of the isolated Phase 6 retests produce a clear marginal win, keep the
  parked levers off and move the next planning priority to a narrower redesign
  rather than a bundle retry
- if exactly one lever produces a clear marginal win, promote only that lever
  and keep the rest parked
- do not run a Phase 6 bundle unless an isolated winner first exists
```

- [ ] **Step 3: Update the audit’s final caveat section from the real results**

Use this exact rule in `docs/accuracy-stack-audit.md`:

```markdown
### Phase 6 Interpretation Rule

- treat each Phase 6 artifact as isolated marginal evidence
- do not infer bundle value from multiple flat isolated results
- if route-rate coverage is fixed, retire the old route-rate path caveat
- keep any non-winning lever parked by default until a narrower redesign exists
```

- [ ] **Step 4: Verify the final doc state**

Run:

```bash
rg -n "phase-6-|Next Priority|Interpretation Rule|usage.route_rate|goal_line_concentration|pff.team_context|usage.ngs" docs/accuracy-roadmap.md docs/accuracy-stack-audit.md
```

Expected:

- all completed Phase 6 artifact labels are present
- the final next-priority note matches the actual isolated results
- the docs do not reintroduce `td_tendency` or `i5` as parked-lever candidates

- [ ] **Step 5: Commit**

```bash
git add docs/accuracy-roadmap.md docs/accuracy-stack-audit.md
git commit -m "docs: finalize phase 6 isolated retest results"
```

# A/B Testing Guide

Unified validation script for testing engine changes against a baseline.

## Quick Start

```bash
# Run your current defaults vs bare baseline (total lift)
uv run python scripts/validate.py --sims 50 --label "my-defaults"

# Test a change against bare baseline
uv run python scripts/validate.py --sims 50 --set usage.ngs.enabled=true --label "add-ngs"

# Measure marginal impact of a change against current defaults
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

The validation header now makes that explicit:

- `comparison: total_lift` for `--baseline bare`
- `comparison: marginal_lift` for `--baseline defaults`

It also prints:

- `seed mode` so runs are comparable
- `coverage` by signal and season
- `coverage notes` when a signal is enabled but not historically exercised

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

Dot paths follow the structure of `config/defaults.yaml`. Any nested key can be overridden.

## Bare Baseline Caching

When `--baseline bare`, the script caches Arm A results to `results/cache/`. On subsequent runs with the same `(season, sims, scoring, training_years)`, Arm A is loaded from cache — cutting runtime roughly in half.

Cache is valid regardless of defaults.yaml changes (bare = all engines off).

Use `--no-cache` to force a fresh bare baseline.

When `--baseline defaults`, both arms are full feature-rich builds, so those runs are materially slower. Use them for decision-grade marginal tests, not broad sweeps.

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

## Coverage-Aware Interpretation

Phase 0 added explicit signal coverage reporting so validation output can distinguish:

- a real historical test
- a partial-data test
- a no-data / not-exercised test

Example:

- `props=none` for `2022 2023 2024` is an expected result today because historical props parquet only exists for 2025

That means:

- `baseline=defaults` runs are the right evidence for “should this remain on by default?”
- but only when the relevant signal shows historical coverage for the tested seasons
- small deltas from `--sims 50` are smoke-test signals, not decision-grade evidence

Recommended workflow:

1. Run a low-sim smoke test to confirm plumbing and coverage.
2. If the signal is historically covered and the result looks interesting, rerun at higher sims.
3. Do not over-interpret results for signals that show `none` or `partial` coverage.

## Ledger

Results are saved to `results/ab_ledger.json` when `--label` is provided. View with `--show-ledger`.

New rows can now carry:

- `schema_version`
- `comparison_mode`
- `seed_mode`
- `coverage_summary`

Older ledgers such as `results/pff_ab_ledger.json` and `results/weekly_ab_ledger.json` are preserved as historical references only. They are not the primary source of truth for the current validation path.

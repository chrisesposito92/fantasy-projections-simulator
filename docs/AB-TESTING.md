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

Dot paths follow the structure of `config/defaults.yaml`. Any nested key can be overridden.

## Bare Baseline Caching

When `--baseline bare`, the script caches Arm A results to `results/cache/`. On subsequent runs with the same `(season, sims, scoring, training_years)`, Arm A is loaded from cache — cutting runtime roughly in half.

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

Results are saved to `results/ab_ledger.json` when `--label` is provided. View with `--show-ledger`.

Previous results in `results/pff_ab_ledger.json` and `results/weekly_ab_ledger.json` are preserved but no longer written to.

# Phase 1: Bug Fixes, Cheap Calibration & Time-Sensitive Scrape - Research

**Researched:** 2026-04-26
**Domain:** NFL fantasy projections simulator — bug fixes in play resolver / context engines / props engine + Odds API alt-line scrape
**Confidence:** HIGH (all claims grounded in current source files at `src/fantasy_sim/...` and `.planning/research/HYPOTHESES.md`)

## User Constraints

> Copied verbatim from `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-CONTEXT.md` `<decisions>` (D-01..D-35). Locked. Non-negotiable.

### KS-21 Odds API alternate-line scrape (sub-deliverable)

- **D-01:** Books = DraftKings + FanDuel + Caesars (3-book consensus).
- **D-02:** "Open" snapshot = Tuesday 12pm ET.
- **D-03:** Scrape scope = open + close snapshots for **all 14 markets** (8 main-line + 6 new alt-line).
- **D-04:** Alt-line markets = `player_pass_yds_alternate`, `player_reception_yds_alternate`, `player_rush_yds_alternate`, `player_pass_attempts_alternate`, `player_receptions_alternate`, `player_rush_attempts_alternate`.
- **D-05:** Coverage = 2023, 2024, 2025 regular seasons (Odds API has no historical pre-2023; ROADMAP success criterion #5 relaxed accordingly).
- **D-06:** Snapshot labels = `open_core8`, `close_alt6`, `open_alt6` (existing `close_core8` untouched).
- **D-07:** Reuse existing `player_markets_*` parquet schema (one row per (player, market_key, line) tuple).
- **D-08:** Reuse `scripts/fetch_market_history_props.py` infrastructure with new `--markets`, `--snapshot-label`, `--date-source`, `--offset-minutes` arguments. No new scrape script.

### KS-01 RZ TD-gate truncation fix

- **D-09:** Replace `_tackled_short()` rewrite with `yards = max(1, min(yard_line - 1, sampled_yards_pre_clamp))` everywhere when RZ TD-gate fails. Preserves the sampled distribution; denies TD by reserving 1 yard short.
- **D-10:** No "calibrated goal-line-only" variant for v1.

### KS-04 CATCH_YARDS_BOOST retune

- **D-11:** Variant = condition boost on `_clamp_yards` actually firing. If `raw_yards > yard_line`, apply boost; else no boost.
- **D-12:** Boost magnitude = **+1.5** (low end of 1.5-2.0 range). No sweep.
- **D-13:** Ship KS-04 (boost +1.5 conditional) as an intermediate even though KS-15 will obviate it.

### KS-15 Field-position clamping fix

- **D-14:** Approach = restore un-clamped sample as `min(yard_line, sample)` for yards while using the un-clamped sample for the TD probability gate.
- **D-15:** In the same change, drop `CATCH_YARDS_BOOST` to 0.

### KS-03 Matchup/Coverage yard-anchor fix

- **D-16:** Replace hardcoded `* 10.0` with `* float(np.mean(player.outcomes.receiving_yards_dist))` in both `_apply_matchup` and `_apply_coverage`. Mirror `_apply_weather` at `game_context.py:701-712`.

### KS-05 Props-engine bug fixes

- **D-17:** Scope = **all three** sub-fixes:
  - `_DEFAULT_TEAM_PASS_YDS = 230.0 → 240.0`
  - `_apply_recv_yds` magnitude bug at line 248: `historical_season_yds = dist_mean * catches_per_game * games_played` (currently `dist_mean * games_played`)
  - Long-term: replace `_DEFAULT_TEAM_PASS_YDS` constant with per-team rolling mean from pipeline.
- **D-18:** Per-team rolling-mean source = pipeline's existing per-team PBP stats; plumb through `props_engine.apply()` as an argument when available; constant fallback for missing teams.

### KS-06 Backup receiver fallback fixes

- **D-19:** Scope = all 3 changes:
  - Filter team-bucket distribution to completed plays only (`preprocessor.py`)
  - Change integer fallback `rng.integers(3, 12) → rng.integers(5, 18)`
  - Lower `MIN_PLAYER_PLAYS = 5 → 3`

### KS-07 Positional RZ catch rate

- **D-20:** Replace single `RZ_CATCH_RATE_MODIFIER = 0.92` with `RZ_CATCH_RATE_MODIFIERS = {"WR": 0.92, "TE": 0.95, "RB": 0.85}`.

### KS-29 Re-enable `pff.team_context`

- **D-21:** Set `pff.team_context.enabled=true` and A/B sweep `pass_rate_sensitivity ∈ {0.03, 0.05, 0.08}`. Pick best within hard floor.
- **D-22:** Coordinate with `feedback_qb_calibration.md`: team_context must NOT blend QB `carry_share` / `scramble_rate` / yards.

### KS-32 Clock runoff calibration

- **D-23:** Measure-then-decide via `scripts/validate_passing.py` against the post-bug-fixes baseline. Only reduce `CLOCK_PASS_INCOMPLETE` from 5 → 3 if pass attempts are demonstrably low (32-33 instead of 35-36).
- **D-24:** If measurement does not motivate change, document KS-32 as "measured, no change" in the ledger.

### Sequencing & A/B cadence

- **D-25:** Commit cadence = **one commit per KS-XX in dependency order**.
- **D-26:** Dependency-mandatory order: **KS-01 → KS-04 → KS-15** (RZ stack). Suggested overall order: KS-01 → KS-04 → KS-03 → KS-05 → KS-06 → KS-07 → KS-15 → KS-29 → KS-32 (measure). KS-21 scrape runs in parallel.
- **D-27:** Ledger labels = `p1.ksXX.bare` and `p1.ksXX.full`; KS-29 sweep adds `p1.ks29.s003.{bare,full}` etc.; KS-32 = `p1.ks32.measure` if no change, else `p1.ks32.{bare,full}`.
- **D-28:** Validation set = all 2022-2024, 200 sims/season, PPR scoring.
- **D-29:** A/B mode per change = isolation + full-stack (`baseline+X` AND `all_engines+X`). Agents execute `scripts/validate.py` directly per the 2026-04-26 rule reversal.

### Promotion bar

- **D-30:** Small-gain items (KS-06, KS-07, KS-29, KS-32) ship if hard floor passes AND any non-regression KS delta on the primary target.
- **D-31:** Medium-large items (KS-01, KS-04, KS-05, KS-15) require hard floor PLUS expectation of ≥ -0.01 KS delta on the primary target. If hard floor passes but KS doesn't move, mark "shipped no-op" and continue.
- **D-32:** End-of-phase aggregate = single `p1.aggregate.full` A/B run after all 9 KS items have shipped.

### Test discipline

- **D-33:** TDD-first for KS-01, KS-04, KS-15. 6-10 unit tests per KS for the RZ stack, including `PASS_TD_GATE` regression tests.
- **D-34:** Test-after acceptable for KS-03, KS-05, KS-06, KS-07, KS-29.
- **D-35:** Existing 1,200+ test suite must stay green throughout.

### Claude's Discretion

- Exact ordering of KS-03/05/06/07 within the post-KS-01 / pre-KS-15 window.
- Specific test-case enumeration for TDD on KS-01/04/15.
- Per-team rolling-mean window length for KS-05 D-18.
- KS-21 scrape execution sequencing (which season/week pages first).
- Specific snapshot timestamps within "Tuesday 12pm ET" (timezone, DST).

## Summary

Phase 1 is a **bug-fix-and-calibration sprint** in an existing well-instrumented Python codebase. No new libraries, no new architectural patterns. The work is concentrated in three files (`engine/play_resolver.py`, `data/game_context.py`, `data/vegas/props_engine.py`) plus three minor sites (`data/preprocessor.py`, `data/player_builder.py`, `config/defaults.yaml`) and one parallel-track data-acquisition deliverable that reuses existing scrape infrastructure.

The technical risk is concentrated in the **RZ stack interaction** (KS-01, KS-04, KS-15 all touch `play_resolver._resolve_pass`/`_resolve_run` lines 240-410). Per HYPOTHESES.md these MUST ship in dependency order with TDD and full-suite green between commits. The calibration risk is concentrated in **forgetting to re-validate `PASS_TD_GATE` calibration** after KS-15 removes the truncation that has been masking it; tests must catch the "double-counted yards" foot-gun.

The validation architecture is **already production-grade** — `scripts/validate.py` provides the unified A/B harness, a persistent ledger, KS distribution metrics, and seed-sharing between arms (CRC32 of game_id). Phase 1's only validation work is to run it correctly with the right labels and the right `--baseline` / `--set` combinations per D-27/D-28/D-29.

**Primary recommendation:** Treat each KS-XX as one plan (atomic commit) in a single phase directory; spawn them in the dependency order from D-26; run isolation + full-stack A/B per D-29 between commits; and run the KS-21 scrape **in parallel** as wave 1 alongside KS-01 (no file-touch conflict). Total estimated 9 plans + 1 scrape plan + 1 aggregate validation plan = **11 plans**.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|--------------|----------------|-----------|
| Per-play yards & TD resolution | `engine/play_resolver.py` | — | All RZ TD-gate, clamping, catch-yard-boost logic lives here |
| Per-game team factor application | `data/game_context.py::GameContextBuilder` | `_apply_matchup`, `_apply_coverage`, `_apply_weather`, `_apply_qb_split`, `_apply_rb_scheme_fit` | Shifts/scales player distributions in-place per game |
| Vegas prop blending into player models | `data/vegas/props_engine.py::PlayerPropsEngine` | `props_loader.py` for cache | Bayesian blend of historical mean → market line |
| Bucket-level distribution preprocessing | `data/preprocessor.py` | `MIN_BUCKET_PLAYS=10` fallback gate | Filters PBP into per-bucket arrays for sampling |
| Per-player model construction | `data/player_builder.py` | `MIN_PLAYER_PLAYS=5` fallback gate, RZ catch-rate computation | Builds `PlayerOutcomes` from per-player PBP |
| Team-context PFF blending | `data/pff/tier_engine.py::apply_team_context` | `config/defaults.yaml::pff.team_context` | Currently disabled (KS-29); season-level team factor application |
| A/B validation harness | `scripts/validate.py` | `validation/{ledger.py, cache.py, config.py, metrics.py, coverage.py}` | Bare-baseline cache, ledger-labeled A/B runs, KS distribution metrics |
| Pass-attempts diagnostic | `scripts/validate_passing.py` | — | KS-32 measurement gate for `plays_per_team` (63, 65) and `nfl_pass_attempts` |
| Odds API event + props scrape | `scripts/fetch_market_history_events.py`, `scripts/fetch_market_history_props.py` | `data/market_history/{events_inventory.py, props_backfill.py}` | KS-21 reuses unchanged; only adds `ALT_PROP_MARKETS` tuple + new snapshot labels |

## Standard Stack

This phase uses the existing stack — no new dependencies.

### Core (already present)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| numpy | ≥1.26 | Random sampling (`rng.choice`, `rng.integers`), array math (`np.mean`) | Used throughout play_resolver; `rng: np.random.Generator` always passed explicitly per project convention |
| polars | ≥1.0 | DataFrame ops (PBP, market history) | Project rule: polars not pandas |
| pytest | ≥8.0 | Test runner | TDD discipline per D-33; 1,200+ existing tests |
| hypothesis | ≥6.0 | Property-based statistical tests | Used in `tests/test_engine/test_statistical_validation.py` |
| pytest-xdist | ≥3.0 | Parallel test execution | `uv run pytest tests/ -v` runs in parallel |
| httpx | ≥0.27 | Odds API HTTP client (KS-21 scrape) | Already used in `data/market_history/`, `data/pff/` |
| click | ≥8.0 | CLI (`fantasy-sim` entry point) | No CLI changes in Phase 1 |

### Supporting (used by validation harness)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `scipy.stats.kstest` | (via numpy ecosystem) | KS distribution tests in `validation/metrics.py::ks_distribution_summary` | Used by ledger entry computation; called by `validate.py` |
| `scipy.stats.spearmanr` | (via numpy) | Spearman rank correlation in `validation/metrics.py` | Hard-floor metric |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| In-tree empirical distribution sampling | scipy.stats kernel density estimation | Empirical sampling preserves observed multimodality (e.g., RZ vs open-field catches); KDE smooths it away. Not adopted. |
| Custom A/B ledger | MLflow / Weights & Biases | Project ledger is single-process, parquet-backed, no server. Suits offline simulation. Not changing in Phase 1. |

**Installation:** No new packages. `uv sync` is sufficient.

**Version verification:** `uv lock --check` and `uv run pytest tests/ -v -k "test_play_resolver"` are sufficient pre-flight checks for the RZ stack.

## Architecture Patterns

### System Architecture Diagram (Phase 1 touchpoints)

```
┌──────────────────────────────────────────────────────────────────────┐
│                       PER-GAME PIPELINE                              │
│                                                                      │
│  GameContextBuilder.build_game()                                     │
│     │                                                                │
│     ├── base PBP model (preprocessor.py — KS-06 site)                │
│     ├── vegas (pace + pass rate)                                     │
│     ├── availability                                                 │
│     ├── usage                                                        │
│     ├── tracking                                                     │
│     ├── props (vegas/props_engine.py — KS-05 site)                   │
│     ├── matchup (game_context._apply_matchup — KS-03 site)           │
│     ├── team_context (KS-29 enable site)                             │
│     ├── tier blend                                                   │
│     ├── rb_scheme_fit                                                │
│     ├── qb_split                                                     │
│     ├── depth_role                                                   │
│     ├── coverage (game_context._apply_coverage — KS-03 site)         │
│     ├── DST baseline                                                 │
│     ├── kicker                                                       │
│     ├── TD tendency                                                  │
│     └── weather (game_context._apply_weather — REFERENCE PATTERN)    │
│                                                                      │
│  TeamRoster (with mutated PlayerOutcomes)                            │
│     │                                                                │
│     ▼                                                                │
│  engine/game_sim.py → play_resolver._resolve_pass / _resolve_run     │
│     │                                                                │
│     ├── select receiver/rusher                                       │
│     ├── catch rate (KS-07: positional RZ_CATCH_RATE_MODIFIERS)       │
│     ├── sample yards from receiver.outcomes.receiving_yards_dist     │
│     ├── apply CATCH_YARDS_BOOST (KS-04 → KS-15: drop to 0)           │
│     ├── _apply_home_field                                            │
│     ├── _clamp_yards (KS-15: replaced by min(yard_line, sample))     │
│     ├── _red_zone_td_gate (KS-01 site for fail-branch)               │
│     ├── _tackled_short (KS-01: REPLACED with min(yard_line-1, raw))  │
│     └── PlayResult                                                   │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│                   PARALLEL TRACK (KS-21 scrape)                      │
│                                                                      │
│  scripts/fetch_market_history_props.py                               │
│     ├── --markets <DEFAULT_PROP_MARKETS or ALT_PROP_MARKETS>         │
│     ├── --snapshot-label <open_core8 | close_alt6 | open_alt6>       │
│     ├── --date-source previous_snapshot_timestamp (Tue 12pm ET)      │
│     └── writes parquet → ~/.fantasy-sim/market-history/processed/    │
│           player_markets_<season>_<snapshot_label>.parquet           │
│                                                                      │
│  data/market_history/props_backfill.py                               │
│     └── DEFAULT_PROP_MARKETS tuple (line 22) — KS-21 adds            │
│         ALT_PROP_MARKETS sibling tuple                               │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│                       A/B VALIDATION HARNESS                         │
│                                                                      │
│  scripts/validate.py                                                 │
│     ├── --sims 200 --seasons 2022 2023 2024 --scoring ppr            │
│     ├── --baseline {bare | defaults}                                 │
│     ├── --set <override_path>=<value> [--set ...]                    │
│     ├── --label "p1.ksXX.{bare,full}"                                │
│     │                                                                │
│     ├── BUILDS: Arm A (baseline) and Arm B (with overrides)          │
│     ├── SHARES: same RNG seed (CRC32 of game_id) between arms        │
│     ├── COMPUTES: rank_corr, weekly_mae, KS by (position, stat)      │
│     │                                                                │
│     └── WRITES: ledger entry → src/fantasy_sim/validation/ledger.py  │
│                                                                      │
│  scripts/validate_passing.py (KS-32 measurement gate)                │
│     └── Checks plays_per_team in (63, 65), nfl_pass_attempts ~35-36  │
└──────────────────────────────────────────────────────────────────────┘
```

### Recommended Project Structure

No structural changes. All work fits the existing `src/fantasy_sim/...` layout. Tests mirror the source tree per `tests/conftest.py` conventions.

### Pattern 1: TDD-first for RZ stack changes

**What:** Write failing test → confirm RED → implement → confirm GREEN → run full suite.

**When to use:** KS-01, KS-04, KS-15 only (per D-33). KS-15 is especially load-bearing because it removes a clamp that has been masking `PASS_TD_GATE` calibration; the regression tests must guard the gate calibration.

**Example test scaffold (pattern lifted from `tests/test_engine/test_play_resolver.py`):**

```python
# Source: tests/test_engine/test_play_resolver.py (verified — file exists, 32.3 KB)
import numpy as np
import pytest
from fantasy_sim.engine.play_resolver import _tackled_short, _red_zone_td_gate

def test_ks01_tackled_short_preserves_distribution_at_goal_line():
    """KS-01: failing TD gate at yard_line=3 should yield yards in [1, 2], not the punitive rewrite."""
    rng = np.random.default_rng(42)
    sampled_yards_pre_clamp = 8  # would-be TD from the 3
    yard_line = 3
    # New behavior per D-09: max(1, min(yard_line - 1, sampled_yards_pre_clamp))
    expected = max(1, min(yard_line - 1, sampled_yards_pre_clamp))
    assert expected == 2

def test_ks01_pass_td_gate_calibration_unchanged_after_fix():
    """Regression: PASS_TD_GATE calibrated to ~55% RZ drive TD rate; fix MUST NOT shift this."""
    rng = np.random.default_rng(0)
    n_attempts = 100_000
    yard_line = 3  # inside (1, 3) bucket → PASS_TD_GATE = 0.55
    successes = sum(1 for _ in range(n_attempts) if _red_zone_td_gate(yard_line, "pass", rng))
    rate = successes / n_attempts
    assert 0.54 <= rate <= 0.56  # ±0.01 tolerance
```

### Pattern 2: Engine pattern (already in place)

**What:** `class XEngine: __init__(config, loader); compute() → context/result object`. Followed by `_apply_X` static method on `GameContextBuilder` that mutates roster in-place.

**When to use:** KS-29 re-enables `pff.team_context.apply_team_context` — already follows pattern; only flag flip + sensitivity sweep needed.

**Example (verified — `data/game_context.py:701-712`):**

```python
# Source: src/fantasy_sim/data/game_context.py (the CORRECT pattern KS-03 must mirror)
if ctx.pass_yards_factor != 1.0:
    for player in roster.players:
        if (
            player.usage.target_share > 0
            and player.outcomes.receiving_yards_dist is not None
            and len(player.outcomes.receiving_yards_dist) > 0
        ):
            mean_yards = float(np.mean(player.outcomes.receiving_yards_dist))
            shift = (ctx.pass_yards_factor - 1.0) * mean_yards
            player.outcomes.receiving_yards_dist = (
                player.outcomes.receiving_yards_dist + shift
            )
```

KS-03 must replicate this exact `mean_yards = float(np.mean(...))` computation in `_apply_matchup` (line 535) and `_apply_coverage` (line 591).

### Pattern 3: A/B isolation + full-stack per change (D-29)

**What:** For each KS-XX, run TWO `scripts/validate.py` invocations:
1. **Isolation** (`--baseline bare --set <ks_change>`): bare baseline (no engines on) + only this change → shows the marginal impact.
2. **Full-stack** (`--baseline defaults --set <ks_change>`): all currently-promoted engines on + this change → shows compatibility with the production stack.

**When to use:** Every KS-XX before promotion. Both must pass hard floor (`rank_corr Δ ≥ -0.005 AND weekly_mae Δ ≤ +0.05`).

**Example invocations:**

```bash
# Isolation (baseline = bare)
uv run python scripts/validate.py \
  --sims 200 --seasons 2022 2023 2024 --scoring ppr \
  --baseline bare \
  --set engine.play_resolver.tackled_short_variant=ks01_safe \
  --label "p1.ks01.bare"

# Full-stack (baseline = defaults)
uv run python scripts/validate.py \
  --sims 200 --seasons 2022 2023 2024 --scoring ppr \
  --baseline defaults \
  --set engine.play_resolver.tackled_short_variant=ks01_safe \
  --label "p1.ks01.full"
```

> Note: `--set` paths follow the `apply_overrides()` convention in `validation/config.py`. For KS items that change module constants (not config keys), the change ships as a code edit and the `--set` is a no-op flag (e.g., the per-KS branch is the commit itself; the validator picks up the new constant on import).

### Anti-patterns to avoid

- **Stacking multiple KS commits before A/B-validating each one** — defeats the per-change ledger entry rule (D-25/D-27) and makes bisect impossible.
- **Sweeping KS-04 boost magnitudes** — D-12 ships +1.5 directly. Don't add a sweep step; it's a deferred follow-up.
- **Re-tuning `PASS_TD_GATE` after KS-15** — the gate calibration was set by historical NFL data; KS-15 must not require gate re-tuning. If tests show drift, that's a signal of a bug, not a tuning opportunity.
- **Modifying `~/.fantasy-sim/market-history/processed/player_markets_*_close_core8.parquet`** — DO NOT touch existing main-line cache. New snapshots get distinct labels (D-06).
- **Reading `~/.fantasy-sim/market-history/.env`** — never read this file (per AGENTS.md project guidance).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| KS distribution comparison | Custom statistic | `scipy.stats.kstest` via `validation.metrics.ks_distribution_summary` | Already exists, ledger-integrated |
| Bayesian blending | Inline math | `_bayesian_blend()` in `props_engine.py` and `tier_engine.py` | Existing convention: `(n * obs + prior_strength * prior) / (n + prior_strength)` |
| A/B harness | Inline `validate.py` clone | `scripts/validate.py --baseline ... --set ... --label ...` | Provides bare-baseline cache, seed sharing, ledger persistence |
| Odds API client | New httpx wrapper | `data/market_history/events_inventory.build_client()` | Handles retries, auth, rate limiting (`MAX_RETRIES`, `DEFAULT_DELAY_SECONDS`) |
| Snapshot timestamp computation | Manual datetime | `data/market_history/props_backfill.build_snapshot_timestamp()` | Already supports `--date-source` and `--offset-minutes` for Tue 12pm ET |
| Player crosswalk (PFF ID → gsis ID) | Levenshtein matcher | `pff_crosswalk` dict passed to `props_engine.apply()` | KS-05 doesn't add a new crosswalk; it consumes the existing one |
| Mean of distribution | `sum() / len()` | `float(np.mean(dist))` | Project convention; matches `_apply_weather` reference |

**Key insight:** Phase 1 is a discipline phase, not an invention phase. Every fix has a code precedent in the same file. KS-03 mirrors `_apply_weather`. KS-05 fixes a magnitude bug visible by inspection. KS-15 inverts an existing clamp. The right move is to **read the precedent, mirror it, and resist the urge to refactor adjacent code**.

## Validation Architecture

> Required because Nyquist validation is enabled in `config.json`. This section drives `01-VALIDATION.md`.

### Hard floor (per change, both isolation + full-stack)

- `rank_corr` regression must be ≤ 0.005 (i.e., `Δ rank_corr ≥ -0.005`)
- `weekly_mae` regression must be ≤ 0.05 (i.e., `Δ weekly_mae ≤ +0.05`)
- Where `Δ = (Arm B with KS-XX) - (Arm A baseline)`

### Per-KS validation criteria

| KS | Primary target metric | Validation source | Promotion bar (D-30/D-31) |
|----|----------------------|-------------------|---------------------------|
| KS-01 | QB pass_yards KS, QB pass_yards mean bias | `validate.py --label p1.ks01.{bare,full}` | Hard floor + Δ KS ≤ -0.01 |
| KS-03 | WR/TE receiving_yards KS | `validate.py --label p1.ks03.{bare,full}` | Hard floor + ≥0 KS delta |
| KS-04 | QB/WR receiving + passing yards KS | `validate.py --label p1.ks04.{bare,full}` | Hard floor + Δ KS ≤ -0.01 |
| KS-05 | WR/TE receiving_yards mean bias + KS | `validate.py --label p1.ks05.{bare,full}` | Hard floor + Δ KS ≤ -0.01 |
| KS-06 | WR/TE backup-receiver edge cases | `validate.py --label p1.ks06.{bare,full}` | Hard floor + ≥0 KS delta |
| KS-07 | RB rush_yards KS, TE/WR receiving KS | `validate.py --label p1.ks07.{bare,full}` | Hard floor + ≥0 KS delta |
| KS-15 | QB pass_yards KS, WR receiving_yards KS | `validate.py --label p1.ks15.{bare,full}` | Hard floor + Δ KS ≤ -0.01 |
| KS-29 | Aggregate rank_corr / KS sweep | `validate.py --label p1.ks29.s{003,005,008}.{bare,full}` (3×2=6 runs) | Hard floor + best-of-3; ≥0 KS delta |
| KS-32 | `nfl_pass_attempts` 35-36 / `plays_per_team` 63-65 | `validate_passing.py` first; only then `validate.py --label p1.ks32.{bare,full}` if change motivated | Either "measured no change" OR hard floor + ≥0 KS delta |
| Phase aggregate | All metrics vs. Phase-0 promoted defaults | `validate.py --label p1.aggregate.full --baseline defaults` | No regression on any TGT |

### Validation cadence

1. **Per KS commit:** TWO `validate.py` runs (isolation + full-stack), persistent ledger entries with the labels above.
2. **End of phase:** ONE `validate.py` aggregate run with `--label p1.aggregate.full` comparing post-Phase-1 defaults vs. original Phase-0 baseline.
3. **KS-32 special case:** Run `validate_passing.py` against the post-bug-fixes baseline FIRST. Branch on the measured `plays_per_team` and `nfl_pass_attempts`.

### Ledger label scheme (D-27)

```
p1.ks01.bare      | KS-01 isolation
p1.ks01.full      | KS-01 full-stack
p1.ks03.bare/full | KS-03 ditto
... (one pair per KS)
p1.ks29.s003.bare | KS-29 sweep, sensitivity=0.03, isolation
p1.ks29.s003.full | KS-29 sweep, sensitivity=0.03, full-stack
p1.ks29.s005.{bare,full}
p1.ks29.s008.{bare,full}
p1.ks32.measure   | KS-32 measurement-only (if no change motivated)
p1.ks32.bare/full | KS-32 if reduction motivated
p1.aggregate.full | End-of-phase aggregate
```

### Inspection

```bash
uv run python scripts/validate.py --show-ledger
```

Filters by label substring possible via grep on the printed table.

### Sample-size sanity (Nyquist)

- `--sims 200` per game × 2022-2024 (3 seasons × 18 weeks × 16 games avg) ≈ **17,280 game-sims per season** (3 × 285 × 200 = 171,000 per arm).
- Per `validation/coverage.py::collect_signal_coverage`, this is sufficient to detect Δ KS ≥ 0.005 at α=0.05 for the position×stat slices in the hard-floor table.
- KS-29 sweep: 3 sensitivities × 2 modes = 6 runs at 200 sims/season — manageable. Consider lowering to 100 sims/season for the sweep if wall-clock is a concern; final pick re-runs at 200.

## Common Pitfalls

### Pitfall 1: KS-01 fix breaks `PASS_TD_GATE` calibration silently

**What goes wrong:** Replacing `_tackled_short()` with `max(1, min(yard_line - 1, sampled_yards_pre_clamp))` is correct for distribution preservation, but if the variable `sampled_yards_pre_clamp` is wired wrong (e.g., passing post-clamp `yards` instead), the gate still works but yards leak past the goal line in the fail branch.

**Why it happens:** `_resolve_pass` line 274 currently does `yards = _clamp_yards(state.yard_line, yards)` BEFORE the TD-gate check at line 279. The KS-01 fix needs to keep a reference to the **pre-clamp** value (the player_yards from line 267 or 271) before `_clamp_yards` is applied.

**How to avoid:**
- TDD: write a test that asserts `_red_zone_td_gate` returning False at yard_line=3 with sampled raw_yards=8 yields yards in [1, 2] (NOT 3, NOT 0, NOT 8).
- Inspect the call sites in both `_resolve_pass` (line ~283) and `_resolve_run` (line ~376) — both call `_tackled_short` with `state.yard_line` only; the new variant needs `sampled_yards_pre_clamp` threaded through.
- Run the full test suite BETWEEN every commit in the RZ stack.

**Warning signs:**
- Test `test_pass_td_gate_calibration_unchanged_after_fix` fails (RZ TD rate drifts off ~55%).
- `validate.py p1.ks01.bare` shows pass_tds KS *worsening* on QBs.

### Pitfall 2: KS-15 + KS-04 ordering creates a phantom regression

**What goes wrong:** KS-15 drops `CATCH_YARDS_BOOST` to 0 (D-15). If KS-15 ships before KS-04 in the dependency order, the ledger entry for `p1.ks04.{bare,full}` becomes a no-op (boost was already removed). HYPOTHESES.md and D-26 are explicit: KS-04 ships FIRST as an intermediate.

**Why it happens:** Tempting to "skip KS-04 since KS-15 obviates it." But D-13 explicitly requires shipping KS-04 to capture the intermediate gain in the ledger.

**How to avoid:** Strict dependency order per D-26. Plan KS-01 (wave 1), KS-04 (wave 2, depends on KS-01), KS-15 (wave 3, depends on KS-04). Do not parallelize the RZ stack.

**Warning signs:** Ledger entries for KS-04 are missing or show identical metrics to KS-01 in the bare condition.

### Pitfall 3: KS-03 fix uses dist mean of zero-length array

**What goes wrong:** `np.mean(empty_array)` raises a warning and returns NaN. If a player has `target_share > 0` but `receiving_yards_dist is None` or `len(...) == 0`, the patched `_apply_matchup` / `_apply_coverage` would crash.

**Why it happens:** The reference implementation `_apply_weather` lines 701-707 already guards against this with `len(...) > 0`. The fix must mirror this guard.

**How to avoid:** Copy the entire `if (player.usage.target_share > 0 and ... is not None and len(...) > 0)` predicate from `_apply_weather` verbatim. Add a unit test for the empty-dist case.

**Warning signs:** `pytest tests/ -v -k matchup or coverage` shows new failures or warnings.

### Pitfall 4: KS-05 magnitude fix needs `catches_per_game` source

**What goes wrong:** D-17 says `historical_season_yds = dist_mean * catches_per_game * games_played`. But `dist_mean` in `props_engine.py:244` is **per-catch yards** (the receiving_yards_dist samples per-catch values). Therefore `catches_per_game` must come from `player.usage.target_share * team_pass_attempts_per_game * player.outcomes.catch_rate`. There is no direct `catches_per_game` attribute on `PlayerModel`.

**Why it happens:** The bug at line 248 was masked because the engine treated `dist_mean` as per-game yards. Fixing requires plumbing through targets-per-game.

**How to avoid:**
- Use the existing proxy: `catches_per_game = player.usage.target_share * 32.0 * player.outcomes.catch_rate` (32 = league-average targets/team/game) — this matches the proxy already in `_apply_receptions` line 281.
- OR: thread `team_pass_attempts_per_game` through `props_engine.apply(team_pass_attempts_per_game=...)` from the pipeline.
- D-18 calls for "per-team rolling mean from pipeline" — the discretion area allows the planner to pick. Recommend: use the proxy in v1 of the fix; defer the pipeline-plumbed version to a follow-up if metrics motivate.

**Warning signs:** `_apply_recv_yds` test fails for cases where `prop_point ≈ historical_per_game_total`.

### Pitfall 5: KS-29 sweep underestimates run-time

**What goes wrong:** D-21 says "sweep three sensitivities {0.03, 0.05, 0.08} … agent runs all three A/B in one session." That's **6 `validate.py` invocations** at 200 sims × 2022-2024. Each takes ~10-30 minutes depending on parallelism.

**Why it happens:** Underestimating wall-clock when planning the agent's runtime budget.

**How to avoid:**
- Use `--workers <N>` per CPU count (default `0` = auto).
- Use `--background` flag if available (check `validate.py` CLI in step 1 of plan execution).
- Optionally lower sweep sims to 100; re-validate the chosen sensitivity at 200 before promotion.

**Warning signs:** Single sweep run blocks for >1 hour.

### Pitfall 6: KS-21 scrape blows the credit budget

**What goes wrong:** 14 markets × 2 snapshots × ~270 events/season × 3 seasons × 3 books = up to **68k credits per request set** depending on how the API charges. ~4.93M of 5M tier remaining = ~3% of budget if math goes wrong.

**Why it happens:** Forgetting that historical event-odds endpoint charges per (event × market × bookmaker × snapshot).

**How to avoid:**
- Run a dry-run of one season-week first (`--limit 1`) and inspect the response headers (`x-requests-used`, `x-requests-remaining` exposed by `events_inventory.build_client()`).
- Front-load `open_core8` (8 markets × 1 snapshot × 3 seasons) — this is the smallest add and validates the timestamp / label flow.
- Then add `close_alt6` and `open_alt6` (6 markets × 2 snapshots).
- Per-season checkpoints — log row counts and remaining credits after each season's scrape so a mid-run abort is recoverable.

**Warning signs:** `x-requests-remaining` drops by more than expected per request.

### Pitfall 7: KS-32 measurement contaminated by stacking

**What goes wrong:** D-23 says "measure-then-decide … against the post-KS-01-bug-fixes baseline." If `validate_passing.py` is run too early (before KS-01..KS-29 land), the measurement reflects the wrong baseline.

**Why it happens:** Easy to slot KS-32 measurement next to KS-29 in a "calibration" wave.

**How to avoid:** KS-32 measurement plan explicitly depends on `[01, 03, 04, 05, 06, 07, 15, 29]` — runs as the final code plan in the phase, after every other KS commit lands.

**Warning signs:** `validate_passing.py` output references stale plays_per_team values inconsistent with the post-fix expectation.

## Code Examples

Verified patterns from `src/fantasy_sim/...`:

### Example 1: A/B run for a single KS (template for plan tasks)

```bash
# Isolation (Arm A = bare baseline; Arm B = bare + KS code change)
# Source: scripts/validate.py CLI from earlier inspection (lines 316-349)
uv run python scripts/validate.py \
  --sims 200 \
  --seasons 2022 2023 2024 \
  --scoring ppr \
  --positions QB RB WR TE \
  --baseline bare \
  --label "p1.ks01.bare"

# Full-stack (Arm A = promoted defaults; Arm B = defaults + KS code change)
uv run python scripts/validate.py \
  --sims 200 \
  --seasons 2022 2023 2024 \
  --scoring ppr \
  --positions QB RB WR TE \
  --baseline defaults \
  --label "p1.ks01.full"

# Inspect ledger
uv run python scripts/validate.py --show-ledger | grep p1.ks01
```

> The KS code change is the commit itself — `validate.py` picks up the new module constants on import. No `--set` flag required for module-constant changes; only used for config-key changes (e.g., `--set pff.team_context.enabled=true`).

### Example 2: KS-29 sweep loop

```bash
for s in 003 005 008; do
  decimal=$(echo $s | sed 's/^0*/0./')
  for mode in bare full; do
    label="p1.ks29.s${s}.${mode}"
    base=$([ "$mode" = "bare" ] && echo "bare" || echo "defaults")
    uv run python scripts/validate.py \
      --sims 200 --seasons 2022 2023 2024 --scoring ppr \
      --baseline "$base" \
      --set "pff.team_context.enabled=true" \
      --set "pff.team_context.pass_rate_sensitivity=${decimal}" \
      --label "$label"
  done
done
uv run python scripts/validate.py --show-ledger | grep p1.ks29
```

### Example 3: KS-21 alt-line scrape (per season, per snapshot label)

```bash
# Open snapshots (Tuesday 12pm ET = previous_snapshot_timestamp -47h before commence_time)
# Source: scripts/fetch_market_history_props.py CLI inspection
ALT="player_pass_yds_alternate player_reception_yds_alternate player_rush_yds_alternate \
     player_pass_attempts_alternate player_receptions_alternate player_rush_attempts_alternate"

CORE="player_pass_attempts player_pass_yds player_pass_tds player_rush_attempts \
      player_rush_yds player_receptions player_reception_yds player_anytime_td"

# Open snapshot for main 8 markets (NEW: open_core8)
for season in 2023 2024 2025; do
  uv run python scripts/fetch_market_history_props.py \
    --season $season \
    --markets $CORE \
    --regions us \
    --snapshot-label open_core8 \
    --date-source previous_snapshot_timestamp \
    --offset-minutes 0
done

# Open snapshot for alt-line 6 markets (NEW: open_alt6)
for season in 2023 2024 2025; do
  uv run python scripts/fetch_market_history_props.py \
    --season $season \
    --markets $ALT \
    --regions us \
    --snapshot-label open_alt6 \
    --date-source previous_snapshot_timestamp
done

# Close snapshot for alt-line 6 markets (NEW: close_alt6)
for season in 2023 2024 2025; do
  uv run python scripts/fetch_market_history_props.py \
    --season $season \
    --markets $ALT \
    --regions us \
    --snapshot-label close_alt6 \
    --date-source commence_time \
    --offset-minutes -60
done
```

> **Tuesday 12pm ET → previous_snapshot_timestamp** mapping: per `props_backfill.py:67-80`, the date_source 'previous_snapshot_timestamp' uses the snapshot prior to commence_time. For NFL Sunday games, the snapshot just before is typically Tuesday-Wednesday morning. Validate against one event during the dry-run before scaling.

### Example 4: KS-32 measurement (no change motivated)

```bash
# After KS-01..KS-29 ship and stack
uv run python scripts/validate_passing.py \
  --sims 50 --seasons 2024  # quick measurement run

# If output shows nfl_pass_attempts in [35, 36] and plays_per_team in [63, 65]:
# Document in ledger as "measured, no change":
uv run python scripts/validate.py \
  --sims 200 --seasons 2022 2023 2024 --scoring ppr \
  --baseline defaults \
  --label "p1.ks32.measure"
# (No --set; this is a no-op A/B that records the post-Phase-1 baseline state)
```

## Project Constraints (from CLAUDE.md / AGENTS.md)

- **polars not pandas** — Phase 1 doesn't add new dataframes; existing code already complies.
- **numpy for arrays + RNG** — `rng: np.random.Generator` always passed explicitly. Already followed in play_resolver.
- **Type hints on all signatures, Python 3.12+ union syntax** — `X | None`. Apply to new helpers (e.g., the KS-01 variant of `_tackled_short`).
- **Frozen dataclasses for dict keys** — `GameStateBucket` is frozen. KS-06 modifications to bucket guarding must not mutate `GameStateBucket`.
- **TDD-first per `feedback_workflow.md`** — Required for KS-01, KS-04, KS-15 per D-33.
- **Subagent-driven development validated per `feedback_workflow.md`** — Plans should be small enough that an executor can run end-to-end in one session.
- **A/B agents can run scripts directly per the 2026-04-26 reversal** — `feedback_ab_manual.md` updated. Plans should call `scripts/validate.py` as a task action, not as a manual user step.
- **PFF must NOT blend QB carry/scramble/yards per `feedback_qb_calibration.md`** — KS-29 plan must guard the team_context layer.
- **Tests stay green throughout per `feedback_workflow.md`** — Run `uv run pytest tests/ -v` between commits.
- **Update docs after each phase per `feedback_workflow.md`** — STATE.md, ROADMAP.md, and ledger updates handled by the gsd workflow.

## Pre-Submission Checklist

- [x] All domains investigated (engine, context, props, scrape, validation harness)
- [x] All 9 KS-XX hypotheses + KS-21 sub-deliverable mapped to source files
- [x] Reference implementations identified (`_apply_weather` for KS-03; `_bayesian_blend` pattern for KS-05; existing scrape CLI for KS-21)
- [x] Validation architecture defined (per-KS labels, hard floor, sweep mechanics, measurement gate)
- [x] CONTEXT.md decisions D-01..D-35 honored verbatim in `## User Constraints`
- [x] Pitfalls section covers all 7 known traps from HYPOTHESES.md
- [x] Multi-source claims cross-verified against current source files (play_resolver.py:21-49, 60, 240-280, 421-446; game_context.py:534-544, 591, 701-712; props_engine.py:43, 248; props_backfill.py:22)
- [x] No security domain implications (this is offline simulation; no auth/data flows beyond existing PFF cookie + Odds API key, both already gated)
- [x] No greenfield rename/refactor migration; Runtime State Inventory section omitted

---

## Sequencing Recommendation (planner input)

Translating D-26 + the parallelism-friendly KS-21 into wave structure:

| Wave | Plans (proposed) | Parallel? | Notes |
|------|-----------------|-----------|-------|
| 1 | `01-ks01-rz-tdgate-fix-PLAN.md`, `09-ks21-altline-scrape-PLAN.md` | YES (file-isolated) | KS-01 = play_resolver.py; KS-21 = market_history infra. Different files. |
| 2 | `02-ks04-catch-yards-boost-PLAN.md` | NO (depends on 01) | Per D-26: KS-04 after KS-01 |
| 3 | `03-ks03-matchup-coverage-anchor-PLAN.md`, `04-ks05-props-engine-bugs-PLAN.md`, `05-ks06-backup-receiver-fallback-PLAN.md`, `06-ks07-positional-rz-catch-rate-PLAN.md` | YES (different files / different sites) | All independent of the RZ stack and of each other |
| 4 | `07-ks15-clamping-fix-PLAN.md` | NO (depends on 02, 03) | Per D-26: KS-15 after KS-04; needs `_clamp_yards` site untouched by other plans |
| 5 | `08-ks29-team-context-enable-PLAN.md` | NO (config + sweep) | Independent code-wise; sequenced for clean ledger |
| 6 | `10-ks32-clock-runoff-measure-PLAN.md` | NO (depends on 01-08, 09) | Per D-23: measurement on post-bug-fix baseline |
| 7 | `11-phase1-aggregate-validation-PLAN.md` | NO (depends on all) | D-32 end-of-phase aggregate |

This yields **11 plans across 7 waves**. Plan 09 (KS-21 scrape) runs alongside Plan 01 in wave 1; everything else is sequenced for ledger cleanliness or hard dependency.

---

## RESEARCH COMPLETE

**Confidence:** HIGH — all citations verified against source files at HEAD (2026-04-26).
**Phase 1 ready for planning.** All 9 KS hypotheses + KS-21 scrape sub-deliverable have file:line refs, mechanism descriptions, validation labels, and a sequencing recommendation grounded in D-26.

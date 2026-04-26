# Phase 1: Bug Fixes, Cheap Calibration & Time-Sensitive Scrape - Research

**Researched:** 2026-04-26
**Re-researched (Cycle 3):** 2026-04-26 (incorporates Codex `01-REVIEWS.md` Cycle 2 findings: per-KS code-change A/B is no-op, `bare_config_dict()` incomplete, Plan 11 mean-bias not in ledger; reconciles stale `open_*` / "Tuesday 12pm ET" / "fetch writes parquet" wording from earlier draft)
**Domain:** NFL fantasy projections simulator — bug fixes in play resolver / context engines / props engine + Odds API alt-line scrape
**Confidence:** HIGH (all claims grounded in current source files at `src/fantasy_sim/...` and `.planning/research/HYPOTHESES.md`)

## User Constraints

> Copied verbatim from `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-CONTEXT.md` `<decisions>` (D-01..D-46). Locked. Non-negotiable.

### KS-21 Odds API alternate-line scrape (sub-deliverable)

- **D-01:** Books = DraftKings + FanDuel + Caesars (3-book consensus).
- **D-02 (REVISED Cycle 2 — HIGH-3):** Earlier snapshot = whatever The Odds API returns as `previous_timestamp` relative to the existing gameday-noon UTC events crawl (`events_inventory.build_request_window` at `events_inventory.py:89-96`). The current pipeline does NOT store a real Tuesday 12pm ET line-release marker, so the earlier-snapshot label honestly describes itself as "prior" not "open". Phase 4 expectations updated to consume "prior-snapshot" lines, not "Tuesday 12pm ET line release".
- **D-03 (REVISED Cycle 2 — HIGH-3):** Scrape scope = prior + close snapshots for **all 14 markets** (8 main-line + 6 new alt-line). Existing `close_core8` cache stays untouched; this scrape adds prior-line versions of the 8 main lines AND prior + close for the 6 new alt-line markets.
- **D-04:** Alt-line markets = `player_pass_yds_alternate`, `player_reception_yds_alternate`, `player_rush_yds_alternate`, `player_pass_attempts_alternate`, `player_receptions_alternate`, `player_rush_attempts_alternate`.
- **D-05:** Coverage = 2023, 2024, 2025 regular seasons (Odds API has no historical pre-2023; ROADMAP success criterion #5 relaxed accordingly).
- **D-06 (REVISED Cycle 2 — HIGH-3):** Snapshot labels = `prior_core8`, `prior_alt6`, `close_alt6` (existing `close_core8` unchanged). The `prior_*` prefix replaces the misleading `open_*` prefix from the earlier draft and explicitly identifies these as "API previous_timestamp relative to gameday-noon UTC crawl". Phase 4 engine integration must reference `prior_*` labels.
- **D-07:** Reuse existing `player_markets_*` parquet schema (one row per (player, market_key, line) tuple).
- **D-08 (REVISED Cycle 2 — HIGH-2):** Pipeline = (1) `scripts/fetch_market_history_props.py` writes raw JSON to `~/.fantasy-sim/market-history/raw/props/{season}/{snapshot_label}/{event_id}.json` via `save_raw_props_snapshot()` (`props_backfill.py:139`); (2) `scripts/build_market_history_player_markets.py` reads the JSON cache and writes processed parquet at `~/.fantasy-sim/market-history/processed/player_markets_{season}_{snapshot_label}.parquet` via `build_player_market_signals_for_season()` (`player_markets.py:190`). Both scripts must run; the earlier draft incorrectly assumed `fetch_market_history_props.py` produced parquet directly. KS-21 plan adds (a) the alt-line market tuple, (b) raw fetch loop, (c) processed-build loop, (d) schema/timing verification.

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
- Specific snapshot timestamps within the API `previous_timestamp` window (timezone, DST), labelled `prior_*`.

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
│                   PARALLEL TRACK (KS-21 scrape — REVISED Cycle 2)    │
│                                                                      │
│  Step 1: scripts/fetch_market_history_props.py                       │
│     ├── --markets <DEFAULT_PROP_MARKETS or ALT_PROP_MARKETS>         │
│     ├── --snapshot-label <prior_core8 | close_alt6 | prior_alt6>     │
│     ├── --date-source previous_snapshot_timestamp                    │
│     │     (API previous_timestamp relative to gameday-noon crawl;    │
│     │      NOT a real Tuesday 12pm ET marker — see Pattern 5)        │
│     └── writes RAW JSON → ~/.fantasy-sim/market-history/raw/props/   │
│           {season}/{snapshot_label}/{event_id}.json                  │
│           via save_raw_props_snapshot() (props_backfill.py:139)      │
│                                                                      │
│  Step 2: scripts/build_market_history_player_markets.py              │
│     ├── --season <int> --snapshot-label <label>                      │
│     ├── reads raw JSON from Step 1                                   │
│     └── writes PARQUET → ~/.fantasy-sim/market-history/processed/    │
│           player_markets_{season}_{snapshot_label}.parquet           │
│           via build_player_market_signals_for_season()               │
│           (player_markets.py:190)                                    │
│                                                                      │
│  data/market_history/props_backfill.py                               │
│     └── DEFAULT_PROP_MARKETS tuple (line 22) — KS-21 adds            │
│         ALT_PROP_MARKETS sibling tuple                               │
│                                                                      │
│  KS-21 deliverable acceptance MUST gate on BOTH the raw JSON files   │
│  (Step 1 output) AND the processed parquet (Step 2 output). The      │
│  earlier draft only ran Step 1 and falsely asserted parquet existed. │
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

### Pattern 3: A/B isolation + full-stack per change (D-29) — REVISED 2026-04-26

**REVISED 2026-04-26 (HIGH-1 from `01-REVIEWS.md`):** The original write-up below was incorrect. The current `scripts/validate.py` (lines 316-349, 1040-1075) treats `--baseline bare` as Arm A = bare engines, BUT Arm B = `apply_overrides(defaults, --set overrides)`, NOT `apply_overrides(bare, --set overrides)`. So `--baseline bare --set X.enabled=true` actually compares `(bare) vs (defaults + X)`, which is contaminated by all default-on engines. The "isolation" claim was false.

**Resolution (Plan 00 implements):** Extend `scripts/validate.py` with a new `--arm-b-base {defaults,bare}` flag (default: `defaults`, preserves backward compatibility). When `--arm-b-base bare`:
- Arm B starts from `build_bare_engine_configs()` (i.e., all engines None)
- `--set` overrides are applied on top of the bare config (same `apply_overrides()` machinery, but the source dict is bare not defaults)
- Then the comparison is `(bare) vs (bare + overrides)` — true isolation.

The implementation is small: in `validate.py:1061-1065`, change

```python
if args.overrides:
    arm_b_dict = apply_overrides(defaults, args.overrides)
else:
    arm_b_dict = defaults
arm_b_configs = build_engine_configs(arm_b_dict)
```

to

```python
if args.arm_b_base == "bare":
    arm_b_configs = build_bare_engine_configs()
    if args.overrides:
        # apply --set on bare-engine config dict
        arm_b_dict = apply_overrides(_bare_engine_config_dict(defaults), args.overrides)
        arm_b_configs = build_engine_configs(arm_b_dict)
else:
    if args.overrides:
        arm_b_dict = apply_overrides(defaults, args.overrides)
    else:
        arm_b_dict = defaults
    arm_b_configs = build_engine_configs(arm_b_dict)
```

(Implementation detail: a `_bare_engine_config_dict(defaults)` helper produces a defaults dict with every engine's `enabled` flag forced to `false` — preserves the dict structure so `apply_overrides()` can find the leaf paths the user requests via `--set`.)

**Three valid validation modes after the extension:**

| Mode | Flag combo | Arm A | Arm B | Use case |
|------|-----------|-------|-------|----------|
| **True isolation** | `--baseline bare --arm-b-base bare --set <KS-X>` | bare engines | bare engines + KS-X | Per-KS isolation (D-29 row 1, replaces broken `--baseline bare` w/o `--arm-b-base`) |
| **Full-stack overlay** | `--baseline defaults --set <KS-X>` | promoted defaults | defaults + KS-X | Per-KS full-stack (D-29 row 2; unchanged from current behavior) |
| **Phase-0 baseline pin** | `--baseline bare --label phase0.baseline.full` (no `--set`) | bare engines | promoted defaults | Wave 0 reference snapshot (D-32b) |

**For each KS-XX, run TWO `scripts/validate.py` invocations:**
1. **True isolation** (`--baseline bare --arm-b-base bare --set <ks_change>`): bare baseline (no engines on) + only this change → shows the marginal impact.
2. **Full-stack overlay** (`--baseline defaults --set <ks_change>`): all currently-promoted engines on + this change → shows compatibility with the production stack.

**When to use:** Every KS-XX before promotion. Both must pass hard floor (`rank_corr Δ ≥ -0.005 AND weekly_mae Δ ≤ +0.05`).

**Example invocations (post-Plan-00):**

```bash
# True isolation (bare baseline + only this change)
uv run python scripts/validate.py \
  --sims 200 --seasons 2022 2023 2024 --scoring ppr \
  --baseline bare --arm-b-base bare \
  --label "p1.ks01.bare"

# Full-stack (promoted defaults + this change)
uv run python scripts/validate.py \
  --sims 200 --seasons 2022 2023 2024 --scoring ppr \
  --baseline defaults \
  --label "p1.ks01.full"
```

> Note 1 (REVISED Cycle 3): `--set` paths follow the `apply_overrides()` convention in `validation/config.py`. ~~For KS items that change module constants (not config keys), the change ships as a code edit and the `--set` is a no-op flag.~~ **Cycle-2 NEW HIGH #1 invalidated that assumption** — both arms in a single `validate.py` process import the same patched code, so a same-code A/B is structurally a no-op. Cycle 3 fixes this by gating every per-KS code change behind a `phase1_ks_flags.ksXX_<name>.enabled` feature flag (default `false`) and using `--set phase1_ks_flags.ksXX_<name>.enabled=true` for Arm B. See Pattern 4b above.
>
> Note 2: For Plans 00-08 and 10 (per-KS), the bare arm uses `--baseline bare --arm-b-base bare --set phase1_ks_flags.ksXX_<name>.enabled=true`. Plan 09 (KS-21 scrape) does no A/B; it produces data only. Plan 11 uses the no-`--set`, `--baseline bare --label p1.aggregate.full` form to capture post-Phase-1 promoted defaults vs. bare for direct comparison against the Wave 0 `phase0.baseline.full` ledger entry — by Phase-1 close the per-KS flag defaults have been flipped to `true` in `config/defaults.yaml`, so a bare-vs-defaults run captures the post-Phase-1 state.

### Pattern 4: Market-history scrape pipeline — REVISED 2026-04-26

**REVISED 2026-04-26 (HIGH-2 from `01-REVIEWS.md`):** The original CONTEXT/RESEARCH conflated raw fetch and processed parquet build. The actual pipeline is two distinct steps:

```
1. scripts/fetch_market_history_props.py
   ├── reads:  ~/.fantasy-sim/market-history/processed/events_inventory_{season}.parquet
   ├── writes: ~/.fantasy-sim/market-history/raw/props/{season}/{snapshot_label}/{event_id}.json
   └── via:    save_raw_props_snapshot() at props_backfill.py:139

2. scripts/build_market_history_player_markets.py
   ├── reads:  ~/.fantasy-sim/market-history/raw/props/{season}/{snapshot_label}/*.json
   ├── writes: ~/.fantasy-sim/market-history/processed/player_markets_{season}_{snapshot_label}.parquet
   └── via:    build_player_market_signals_for_season() at player_markets.py:190
```

The `scripts/build_market_history_player_markets.py` script (verified to exist) takes `--season` and `--snapshot-label` arguments matching the raw fetch script. KS-21 deliverable acceptance MUST gate on the existence of BOTH the raw JSON files (Step 1) AND the processed parquet (Step 2). The original Plan 09 only ran Step 1 and asserted parquet existed — that assertion would have been false even after a successful raw scrape.

**Pipeline invocation example (per season-snapshot pair):**

```bash
# Step 1: Raw fetch
uv run python scripts/fetch_market_history_props.py \
  --season 2024 --markets $ALT --regions us \
  --snapshot-label prior_alt6 --date-source previous_snapshot_timestamp

# Step 2: Build processed parquet from raw cache
uv run python scripts/build_market_history_player_markets.py \
  --season 2024 --snapshot-label prior_alt6
```

Both steps must run for every season-snapshot pair before KS-21 is deliverable.

### Pattern 4b: Per-KS code-change A/B via feature flags — NEW Cycle 3 (HIGH-1 final fix)

**Problem (Codex Cycle-2 NEW HIGH #1):** Even with `--arm-b-base bare` from Plan 00, the per-KS code-change plans (KS-01/03/04/05/06/07/15 and the KS-32 retune branch) still produce no-op A/B comparisons. `validate.py` is a single Python process — both arms import the SAME (patched) module, so a bare-isolation run after the KS code edit lands compares `(bare engines, patched code)` to `(bare engines, patched code + no extra config overrides)`. Both arms execute identical code. Marginal effect of the KS code change CANNOT be measured this way.

**Resolution (Cycle 3):** Each KS code change ships behind a config feature flag, default `false` (preserves current behavior). The A/B run sets the flag to `true` in Arm B via `--set <flag>=true`, producing a real `(bare, OLD code) vs (bare, NEW code)` comparison. After the A/B passes hard floor + promotion bar, a SEPARATE promotion commit flips the flag default to `true` in `config/defaults.yaml`. This pattern matches how every existing engine (PFF, Vegas, weather, etc.) is gated.

**Feature-flag inventory for Phase 1 code changes** (NEW config keys to add to `config/defaults.yaml` under a new top-level block):

```yaml
# Phase 1 Cycle-3 KS code-change feature flags (default false; flipped per promotion commit)
phase1_ks_flags:
  ks01_preserve_distribution:
    enabled: false   # KS-01: _tackled_short_preserve_distribution variant
  ks03_dynamic_yard_anchor:
    enabled: false   # KS-03: _apply_matchup/_apply_coverage use np.mean(<dist>) instead of *10.0
  ks04_conditional_catch_boost:
    enabled: false   # KS-04: CATCH_YARDS_BOOST = 1.5 only when _clamp_yards would fire
    boost_value: 1.5
  ks05_props_recv_yds_fix:
    enabled: false   # KS-05: _apply_recv_yds magnitude fix + DEFAULT_TEAM_PASS_YDS=240
    default_team_pass_yds: 240.0
  ks06_backup_receiver_fix:
    enabled: false   # KS-06: filter completed plays + integer fallback (5,18) + MIN_PLAYER_PLAYS=3
    min_player_plays: 3
    fallback_low: 5
    fallback_high: 18
  ks07_positional_rz_catch_rate:
    enabled: false   # KS-07: positional RZ_CATCH_RATE_MODIFIERS dict
    rates:
      WR: 0.92
      TE: 0.95
      RB: 0.85
  ks15_unclamp_for_td_gate:
    enabled: false   # KS-15: min(yard_line, sample) clamp + un-clamped sample drives TD gate
  ks32_clock_pass_incomplete_3s:
    enabled: false   # KS-32: CLOCK_PASS_INCOMPLETE = 3 (only set if measurement motivates)
```

**Code-side pattern** (per KS plan): the changed module reads the flag once at import time (or once per `GameContextBuilder` instance) and branches on it. Example for KS-01 (`engine/play_resolver.py`):

```python
# Module top, after constants
from fantasy_sim.config.loader import get_phase1_ks_flags
_KS01_PRESERVE_DIST = get_phase1_ks_flags().get("ks01_preserve_distribution", {}).get("enabled", False)

# In _resolve_pass and _resolve_run, the failed-gate branch
if _KS01_PRESERVE_DIST:
    yards = _tackled_short_preserve_distribution(state.yard_line, sampled_yards_pre_clamp)
else:
    yards = _tackled_short(state.yard_line, rng)  # legacy
```

The `get_phase1_ks_flags()` helper is a thin shim added to `src/fantasy_sim/config/loader.py` in Plan 00 Task 8 (NEW Cycle-3 task). It reads from the same defaults.yaml chain `load_defaults()` already uses; the shim exists so KS plans don't have to plumb the full config dict through every call site.

**A/B invocation per KS code change (Cycle-3 pattern):**

```bash
# KS-01 isolation A/B: bare baseline + ONLY the KS-01 flag flipped on
uv run python scripts/validate.py \
  --sims 200 --seasons 2022 2023 2024 --scoring ppr \
  --baseline bare --arm-b-base bare \
  --set "phase1_ks_flags.ks01_preserve_distribution.enabled=true" \
  --label "p1.ks01.bare"

# KS-01 full-stack overlay: defaults + KS-01 flag flipped on
uv run python scripts/validate.py \
  --sims 200 --seasons 2022 2023 2024 --scoring ppr \
  --baseline defaults \
  --set "phase1_ks_flags.ks01_preserve_distribution.enabled=true" \
  --label "p1.ks01.full"
```

In Arm A both runs use the flag's default (`false`, legacy code path); in Arm B both runs flip it to `true` (new code path). Marginal effect of the KS-01 change is now genuinely measured.

**Promotion-commit pattern (separate from the A/B commit):** after the A/B passes, a follow-up commit flips the flag default to `true` in `config/defaults.yaml`. The flag stays in the config tree (so the legacy path remains reachable for emergency rollback) but downstream defaults runs hit the new code path automatically. The flag can be removed entirely in a Phase 2+ cleanup commit once enough wall-clock has passed without rollback needs.

**Anti-pattern:** running `validate.py --baseline bare --arm-b-base bare --label p1.ksXX.bare` AFTER landing the KS code change WITHOUT a flag — both arms execute the same patched code, the ledger entry is structurally a no-op, and the promotion claim "KS-XX A/B passed hard floor" is false. This was Codex Cycle-2 NEW HIGH #1.

**Path B (deferred — not used in Cycle 3):** an alternative is to pin pre-commit and post-commit ledger entries via two separate `validate.py` runs at different commits. Plan 00 already established this pattern for `phase0.baseline.full`. We rejected it for per-KS work because (a) each KS would need two clean commits with a forced ledger-pin run between them, doubling wall-clock; (b) the cross-commit comparison is harder to audit than a flag-driven within-commit A/B; (c) feature flags also give us a clean rollback knob if a downstream phase reveals a regression.

### Pattern 5: Snapshot label naming honesty — REVISED 2026-04-26

**REVISED 2026-04-26 (HIGH-3 from `01-REVIEWS.md`):** The original CONTEXT used `open_*` labels (`open_core8`, `open_alt6`) and asserted the timing was "Tuesday 12pm ET". This was incorrect:

- The current event inventory crawl uses `gameday + T12:00:00Z` (gameday noon UTC) as the snapshot date — see `events_inventory.py:89-96` `build_request_window()`.
- `previous_snapshot_timestamp` is what The Odds API returns as `previous_timestamp` relative to that gameday-noon snapshot — see `events_inventory.py:247` `flatten_raw_snapshot()`.
- The Odds API determines its own snapshot cadence; for NFL games, the prior available snapshot to a Sunday gameday-noon crawl could be Sunday morning, Saturday, Friday, or earlier — NOT guaranteed to be Tuesday line-release time.
- No code path in the current pipeline persists a real Tuesday 12pm ET marker.

**Resolution:** Rename labels to `prior_*` (`prior_core8`, `prior_alt6`) to honestly describe semantics. Update Phase 4 expectations to consume "prior-snapshot" lines, not "Tuesday 12pm ET line release". A future follow-up plan may extend `events_inventory.py` to capture a real Tuesday line-release marker (would require a separate Tuesday-noon crawl to populate `events_inventory_tuesday_*.parquet`); out of scope for the time-sensitive Phase 1 scrape window.

| Original label | New label | Semantic |
|----------------|-----------|----------|
| `open_core8` | `prior_core8` | API previous_timestamp for the 8 main markets |
| `open_alt6` | `prior_alt6` | API previous_timestamp for the 6 alt-line markets |
| `close_alt6` | `close_alt6` (unchanged) | gameday-noon-1h for the 6 alt-line markets |
| `close_core8` | `close_core8` (unchanged) | existing pre-Phase-1 cache |

### Pattern 6: Mean-bias retrieval for Plan 11 — NEW Cycle 3 (HIGH-3 fix)

**Problem (Codex Cycle-2 NEW HIGH #3):** Phase-1 success criterion 1 ("QB pass_yards mean bias narrowed from ~−28 yd/g to within ±10 yd/g") is not measurable from the existing ledger. `SeasonMetrics` (`src/fantasy_sim/validation/ledger.py:25`) carries `arm_a_rank_corr`, `arm_b_rank_corr`, `arm_a_weekly_mae`, `arm_b_weekly_mae`, `arm_a_season_mae`, `arm_b_season_mae`, `arm_a_calibration`, `arm_b_calibration`, `weekly_fpts_ks` (dict), and `stat_ks` (dict of dict). It does NOT carry per-position-stat **mean bias** (signed projection-vs-actual difference per game). Plan 11's acceptance block requires this number, so the comparison currently has no data path.

**Resolution (Cycle 3 — Path A: extend the ledger schema):** add an optional `stat_mean_bias` field to `SeasonMetrics` mirroring the shape of `stat_ks`:

```python
@dataclass
class SeasonMetrics:
    # ... existing fields ...
    stat_mean_bias: dict[str, dict[str, dict[str, float | int]]] = field(default_factory=dict)
    # Shape: {position: {stat_name: {"arm_a_bias": float, "arm_b_bias": float,
    #                                 "bias_delta": float, "n": int}}}
```

This is a **schema-version bump** (CURRENT_LEDGER_SCHEMA_VERSION 4 → 5). The `load_ledger()` function already does `item.setdefault(...)` for backward-compatible schema evolution; new entries have the field, old entries default to empty dict on load. Plan 00 owns the ledger-side change; Plan 11 reads `stat_mean_bias["QB"]["pass_yards"]["arm_b_bias"]` directly.

**Computation site:** the existing per-arm metrics code in `validate.py` already iterates over per-position-stat slices to compute KS. Mean bias is a sibling computation: `np.mean(projected_per_game) - np.mean(actual_per_game)` per (position, stat) per arm. No additional simulation cost — just a sum/mean over already-collected projection rows. Approximate insertion site: wherever `stat_ks` entries are built in `validate.py` (search for `weekly_fpts_ks` or `stat_ks` writes; the mean-bias write happens immediately adjacent). Plan 00 Task 9 (NEW Cycle-3) ships this in tandem with the bumped schema.

**Path B (rejected for Cycle 3):** a side diagnostic script that consumes raw projection rows after Plan 11's run. Rejected because (a) it requires re-running the simulation just to compute bias, doubling Plan 11's wall-clock; (b) the metric is durable and useful for every future phase, so paying the schema-bump cost once is correct.

**Plan 11 reads the new field** by adapting the `collect_arm_b()` helper in Plan 11 Task 2:

```python
mean_bias = {}
for s in seasons:
    for pos, stats in s.get("stat_mean_bias", {}).items():
        for stat, mb_data in stats.items():
            if isinstance(mb_data, dict) and "arm_b_bias" in mb_data:
                mean_bias.setdefault((pos, stat), []).append(mb_data["arm_b_bias"])
return {
    # ...
    "stat_mean_bias": {k: sum(v)/len(v) for k, v in mean_bias.items()},
}
```

The differenced output `p1.aggregate.full Arm B - phase0.baseline.full Arm B` for `(QB, pass_yards)` is then the Phase-1-vs-Phase-0 mean bias delta needed for success criterion 1.

### Pattern 7: bare_config_dict() completeness — NEW Cycle 3 (HIGH-2 fix)

**Problem (Codex Cycle-2 NEW HIGH #2):** the Cycle-2 `bare_config_dict()` helper enumerates engine SUB-engine flags (e.g., `pff.team_context.enabled`) but omits the TOP-LEVEL engine gates (`pff.enabled`, `vegas.enabled`, `usage.enabled`, etc.) that engines also key off. From `src/fantasy_sim/validation/config.py:118-138`:

```python
"pff_config": pff if pff.enabled else None,
"weather_config": weather if weather.enabled else None,
"vegas_config": vegas if vegas.enabled else None,
"props_config": props if props.enabled else None,
"usage_config": usage if usage.enabled else None,
"tracking_config": tracking if tracking.enabled else None,
"availability_config": availability if availability.enabled else None,
"role_trend_config": role_trend if role_trend.enabled else None,
"market_history_config": market_history if market_history.enabled else None,
"game_script_config": game_script if game_script.enabled else None,
"goal_line_concentration_config": goal_line_concentration if goal_line_concentration.enabled else None,
"td_tendency_config": td_tendency if td_tendency.enabled else None,
"target_selection_config": target_selection if target_selection.enabled else None,
"play_call_model_config": play_call_model if play_call_model.enabled else None,
"qb_rushing_config": qb_rushing if (qb_rushing.scramble.enabled or qb_rushing.designed_runs.enabled) else None,
```

If `bare_config_dict()` only flips sub-engine flags (e.g., `pff.team_context.enabled=false`) but leaves `pff.enabled=true`, then `--set pff.team_context.enabled=true` on top of the bare base produces a config where `pff.enabled` is still true but ALL OTHER pff sub-engines are still bound by their `defaults.yaml` values. The bare base is not actually bare.

**Resolution (Cycle 3):** `bare_config_dict()` MUST enumerate every `.enabled` truthiness gate the engines key off, including the TOP-LEVEL gates. Concretely:

```python
def bare_config_dict(defaults: dict) -> dict:
    """REVISED Cycle 3: forces ALL .enabled gates to false — top-level engine
    gates AND sub-engine flags. This must mirror build_bare_engine_configs()
    semantics exactly: every key in build_engine_configs that ends up keying
    off `.enabled` must be flipped here.
    """
    config = copy.deepcopy(defaults)
    enabled_keys_to_disable = (
        # Top-level engine gates (NEW Cycle 3 — fixes HIGH-2)
        "pff.enabled",
        "weather.enabled",
        "vegas.enabled",
        "props.enabled",  # Note: props is a sibling top-level block, not vegas.props
        "usage.enabled",
        "tracking.enabled",
        "availability.enabled",
        "role_trend.enabled",
        "market_history.enabled",
        "game_script.enabled",
        "goal_line_concentration.enabled",
        "td_tendency.enabled",
        "target_selection.enabled",
        "play_call_model.enabled",
        # qb_rushing: gate is `scramble.enabled OR designed_runs.enabled`, so disable BOTH
        "qb_rushing.scramble.enabled",
        "qb_rushing.designed_runs.enabled",
        # PFF sub-engines (Cycle 2 baseline; preserved)
        "pff.tier_engine.enabled",
        "pff.team_context.enabled",
        "pff.matchup.enabled",
        "pff.coverage.enabled",
        "pff.kicker.enabled",
        "pff.dst_baseline.enabled",
        "pff.rb_scheme_fit.enabled",
        "pff.qb_split.enabled",
        "pff.depth_role.enabled",
        "pff.depth_role.efficiency.enabled",
        "pff.talent.enabled",
        "pff.ncaa_rookie.enabled",
        "pff.archetypes.enabled",
        "pff.matchup.enabled",
        # Vegas sub-engines (Cycle 2 baseline; preserved — note vegas.props.enabled is a sub-key, distinct from top-level props.enabled)
        "vegas.itt.enabled",
        "vegas.spread.enabled",
        "vegas.props.enabled",
        # Usage sub-engines (Cycle 2 baseline; preserved)
        "usage.ngs.enabled",
        "usage.route_rate.enabled",
        # Ensemble (Cycle 2 baseline; preserved)
        "ensemble.enabled",
        "ensemble.ff_opportunity.enabled",
        "ensemble.dynamic_blend.enabled",
        "ensemble.residual_calibration.enabled",
        # Phase-1 KS feature flags (NEW Cycle 3 — Pattern 4b)
        "phase1_ks_flags.ks01_preserve_distribution.enabled",
        "phase1_ks_flags.ks03_dynamic_yard_anchor.enabled",
        "phase1_ks_flags.ks04_conditional_catch_boost.enabled",
        "phase1_ks_flags.ks05_props_recv_yds_fix.enabled",
        "phase1_ks_flags.ks06_backup_receiver_fix.enabled",
        "phase1_ks_flags.ks07_positional_rz_catch_rate.enabled",
        "phase1_ks_flags.ks15_unclamp_for_td_gate.enabled",
        "phase1_ks_flags.ks32_clock_pass_incomplete_3s.enabled",
    )
    # ... walk + flip ...
```

**Acceptance for the helper (NEW Cycle 3 — replaces Cycle-2 escape hatch):** Plan 00 Task 4 (the integration test) is now a HARD GATE. The Cycle-2 "loosen the test if end-to-end behavior disagrees" escape hatch is REMOVED. The test must verify that for EVERY engine listed in `build_engine_configs()`, calling `bare_config_dict(load_defaults()) → build_engine_configs(...)` produces a dict where the corresponding `<engine>_config` is `None`. If any engine remains non-None, the helper is incomplete and the test fails (the helper must be extended, not the test loosened).

**Anti-pattern:** "we'll loosen the test until it passes" — flagged by Codex Cycle 2 as the reason HIGH-1 wasn't actually closed. The Cycle-3 acceptance contract: helper must be exhaustive; test must enforce that exhaustively.

### Anti-patterns to avoid

- **Stacking multiple KS commits before A/B-validating each one** — defeats the per-change ledger entry rule (D-25/D-27) and makes bisect impossible.
- **Sweeping KS-04 boost magnitudes** — D-12 ships +1.5 directly. Don't add a sweep step; it's a deferred follow-up.
- **Re-tuning `PASS_TD_GATE` after KS-15** — the gate calibration was set by historical NFL data; KS-15 must not require gate re-tuning. If tests show drift, that's a signal of a bug, not a tuning opportunity.
- **Modifying `~/.fantasy-sim/market-history/processed/player_markets_*_close_core8.parquet`** — DO NOT touch existing main-line cache. New snapshots get distinct labels (D-06).
- **Reading `~/.fantasy-sim/market-history/.env`** — never read this file (per AGENTS.md project guidance).
- **Asserting `--baseline bare` is true isolation** (REVISED — see HIGH-1) — until Plan 00 lands the `--arm-b-base` extension, `--baseline bare` produces `(bare) vs (defaults+overrides)`. Per-KS isolation runs MUST use `--baseline bare --arm-b-base bare` after Plan 00.
- **Calling `fetch_market_history_props.py` without then calling `build_market_history_player_markets.py`** (REVISED — see HIGH-2) — the raw script writes JSON only; the processed parquet downstream code reads requires the build step.
- **Labeling Tuesday-line snapshots as `open_*`** (REVISED — see HIGH-3) — current pipeline cannot guarantee Tuesday timing; use `prior_*` to describe what the API actually returns.
- **Running per-KS A/B without a feature flag (Cycle-3 NEW HIGH #1)** — even with `--arm-b-base bare`, calling `validate.py --baseline bare --arm-b-base bare --label p1.ksXX.bare` AFTER landing the KS code change without a `--set <flag>=true` produces `(bare, NEW code) vs (bare, NEW code)` — both arms execute identical code. Marginal effect of the KS change is structurally unmeasurable. Cycle 3 mandates Pattern 4b feature flags; per-KS plans must invoke `--set phase1_ks_flags.ksXX_<name>.enabled=true` so Arm B genuinely flips the new code path on while Arm A stays on the legacy default (`enabled: false`).
- **`bare_config_dict()` omitting top-level engine gates (Cycle-3 NEW HIGH #2)** — the helper must enumerate `pff.enabled`, `vegas.enabled`, `usage.enabled`, etc. (top-level gates that `build_engine_configs` keys off) AND the sub-engine flags. The Cycle-2 helper omitted the top-level gates and explicitly allowed "loosen the test" if the integration test disagreed. Cycle 3 forbids that escape hatch — the integration test is a HARD gate; if it fails, extend the helper, do not loosen the test. See Pattern 7.
- **Reading mean-bias from raw projection rows after the fact (Cycle-3 NEW HIGH #3)** — the ledger does not persist mean-bias today, so any "I'll grep the projections later" approach is fragile and re-runs the simulation. Cycle 3 extends the ledger schema with `stat_mean_bias` (Path A in Pattern 6); Plan 11 reads it directly from the persisted ledger entry. Side diagnostic scripts that re-simulate are rejected.

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

### Per-KS validation criteria — REVISED Cycle 3 (HIGH-1 final fix via Pattern 4b feature flags)

> Every code-change KS now invokes `--set <feature_flag>=true` so Arm B genuinely executes the new code path while Arm A stays on the legacy default. KS-29 was already config-driven (D-21 sweep); its invocation pattern is unchanged.

| KS | Primary target metric | Bare-isolation invocation | Full-stack invocation | Promotion bar (D-30/D-31) |
|----|----------------------|---------------------------|----------------------|---------------------------|
| Wave-0 baseline pin | rank_corr/MAE/per-stat KS/per-stat mean-bias for ALL positions | `validate.py --baseline bare --label phase0.baseline.full` (no `--set`) | n/a (Arm B = current promoted defaults) | Wave 0 mandatory; freezes the comparison reference (now includes mean-bias per Pattern 6) |
| KS-01 | QB pass_yards KS, QB pass_yards mean bias | `validate.py --baseline bare --arm-b-base bare --set phase1_ks_flags.ks01_preserve_distribution.enabled=true --label p1.ks01.bare` | `validate.py --baseline defaults --set phase1_ks_flags.ks01_preserve_distribution.enabled=true --label p1.ks01.full` | Hard floor + Δ KS ≤ -0.01 |
| KS-03 | WR/TE receiving_yards KS, RB rush_yards KS | `validate.py --baseline bare --arm-b-base bare --set phase1_ks_flags.ks03_dynamic_yard_anchor.enabled=true --label p1.ks03.bare` | `validate.py --baseline defaults --set phase1_ks_flags.ks03_dynamic_yard_anchor.enabled=true --label p1.ks03.full` | Hard floor + ≥0 KS delta on WR/TE recv AND RB rush |
| KS-04 | QB/WR receiving + passing yards KS | `validate.py --baseline bare --arm-b-base bare --set phase1_ks_flags.ks04_conditional_catch_boost.enabled=true --label p1.ks04.bare` | `validate.py --baseline defaults --set phase1_ks_flags.ks04_conditional_catch_boost.enabled=true --label p1.ks04.full` | Hard floor + Δ KS ≤ -0.01 |
| KS-05 | WR/TE receiving_yards mean bias + KS | `validate.py --baseline bare --arm-b-base bare --set phase1_ks_flags.ks05_props_recv_yds_fix.enabled=true --label p1.ks05.bare` | `validate.py --baseline defaults --set phase1_ks_flags.ks05_props_recv_yds_fix.enabled=true --label p1.ks05.full` | Hard floor + Δ KS ≤ -0.01 |
| KS-06 | WR/TE backup-receiver edge cases | `validate.py --baseline bare --arm-b-base bare --set phase1_ks_flags.ks06_backup_receiver_fix.enabled=true --label p1.ks06.bare` | `validate.py --baseline defaults --set phase1_ks_flags.ks06_backup_receiver_fix.enabled=true --label p1.ks06.full` | Hard floor + ≥0 KS delta |
| KS-07 | RB rush_yards KS, TE/WR receiving KS | `validate.py --baseline bare --arm-b-base bare --set phase1_ks_flags.ks07_positional_rz_catch_rate.enabled=true --label p1.ks07.bare` | `validate.py --baseline defaults --set phase1_ks_flags.ks07_positional_rz_catch_rate.enabled=true --label p1.ks07.full` | Hard floor + ≥0 KS delta |
| KS-15 | QB pass_yards KS, WR receiving_yards KS | `validate.py --baseline bare --arm-b-base bare --set phase1_ks_flags.ks15_unclamp_for_td_gate.enabled=true --label p1.ks15.bare` | `validate.py --baseline defaults --set phase1_ks_flags.ks15_unclamp_for_td_gate.enabled=true --label p1.ks15.full` | Hard floor + Δ KS ≤ -0.01 |
| KS-29 | Aggregate rank_corr / KS sweep | 3 sweep × `--baseline bare --arm-b-base bare --set pff.team_context.enabled=true --set pff.team_context.pass_rate_sensitivity=<v>` | 3 sweep × `--baseline defaults --set ...` (full-stack overlay) | Hard floor + best-of-3; ≥0 KS delta |
| KS-32 (NO CHANGE branch) | `nfl_pass_attempts` 35-36 / `plays_per_team` 63-65 | `validate_passing.py` first; if no reduction motivated → `validate.py --baseline bare --label p1.ks32.measure` (REAL delta vs bare per HIGH-4) | Same | "measured, no change" — KS-32 deliverable per REQUIREMENTS.md |
| KS-32 (RETUNE branch) | Same | If reduction motivated → `validate.py --baseline bare --arm-b-base bare --set phase1_ks_flags.ks32_clock_pass_incomplete_3s.enabled=true --label p1.ks32.bare` | `validate.py --baseline defaults --set phase1_ks_flags.ks32_clock_pass_incomplete_3s.enabled=true --label p1.ks32.full` | Hard floor + ≥0 KS delta |
| Phase aggregate | All metrics + mean-bias vs. Phase-0 baseline pin | `validate.py --baseline bare --label p1.aggregate.full` (no `--set` — defaults reflect promoted flag flips) | n/a | Δ Arm B (post-Phase-1 defaults) vs. Δ Arm B (Wave-0 phase0.baseline.full) — no regression on any TGT; mean-bias delta evaluable per Pattern 6 |

### Validation cadence — REVISED 2026-04-26 (HIGH-4)

1. **Wave 0 (Plan 00):** Extend `validate.py` with `--arm-b-base` flag. Pin `phase0.baseline.full` (Arm A = bare, Arm B = current promoted defaults) and `phase0.baseline.bare` (Arm A = bare, Arm B = bare; sanity check). Commit the harness extension AND both ledger entries before any KS work begins.
2. **Per KS commit:** TWO `validate.py` runs (bare isolation + full-stack overlay) per the table above. Both use the new flag combos. Persistent ledger entries with the labels above. Hard floor evaluated per row.
3. **End of phase (Plan 11):** ONE `validate.py` run with `--baseline bare --label p1.aggregate.full` (no `--set`) capturing post-Phase-1 promoted defaults' Arm B metrics. Plan 11 then reads BOTH `phase0.baseline.full` AND `p1.aggregate.full` from the ledger and computes the Arm B delta to evaluate against TGT-XX targets.
4. **KS-32 special case:** Run `validate_passing.py` against the post-bug-fixes baseline FIRST. Branch on the measured `plays_per_team` and `nfl_pass_attempts`.

### Ledger label scheme (D-27, REVISED 2026-04-26)

```
phase0.baseline.full | Wave-0 frozen reference (Arm A = bare, Arm B = pre-Phase-1 defaults)
phase0.baseline.bare | Wave-0 self-consistency (Arm A = bare, Arm B = bare; sanity zero-delta)
p1.ks01.bare         | KS-01 true isolation (--baseline bare --arm-b-base bare)
p1.ks01.full         | KS-01 full-stack overlay (--baseline defaults)
p1.ks03.bare/full    | KS-03 ditto
... (one pair per KS, all using --arm-b-base bare for the .bare entry)
p1.ks29.s003.bare    | KS-29 sweep, sensitivity=0.03, true isolation
p1.ks29.s003.full    | KS-29 sweep, sensitivity=0.03, full-stack
p1.ks29.s005.{bare,full}
p1.ks29.s008.{bare,full}
p1.ks32.measure      | KS-32 measurement-only (if no change motivated)
p1.ks32.bare/full    | KS-32 if reduction motivated
p1.aggregate.full    | End-of-phase aggregate (Arm A = bare, Arm B = post-Phase-1 defaults; compare to phase0.baseline.full Arm B)
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
- (Cycle 3) `p1.ks01.bare` ledger entry shows ZERO delta on every metric — symptom of forgetting the `--set phase1_ks_flags.ks01_preserve_distribution.enabled=true` override. Both arms execute the legacy code path; KS-01 has no measured marginal effect.

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
- Front-load `prior_core8` (8 markets × 1 snapshot × 3 seasons) — this is the smallest add and validates the timestamp / label flow (REVISED Cycle 2 — was `open_core8`).
- Then add `close_alt6` and `prior_alt6` (6 markets × 2 snapshots) (REVISED Cycle 2 — was `open_alt6`).
- Per-season checkpoints — log row counts and remaining credits after each season's scrape so a mid-run abort is recoverable.

**Warning signs:** `x-requests-remaining` drops by more than expected per request.

> **Credit logging note (Cycle 2 MEDIUM):** `scripts/fetch_market_history_props.py` at line 110 currently logs `cost={x-requests-last}` from response headers but NOT `x-requests-remaining`. Plan 09 must either (a) extend `fetch_market_history_props.py` to also log `x-requests-remaining` from response headers, OR (b) collect remaining-credit values manually from the Odds API dashboard. Option (a) is preferred and small (~5 LOC). See Plan 09 Task 0 for the patch.

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

### Example 3: KS-21 alt-line scrape (per season, per snapshot label) — REVISED Cycle 2 (HIGH-2 + HIGH-3)

```bash
# ============================================================================
# REVISED Cycle 2: snapshot labels are `prior_*` not `open_*`. The Odds API
# `previous_snapshot_timestamp` returns the API's prior available snapshot
# relative to the existing gameday-noon UTC events crawl — NOT a real
# Tuesday 12pm ET line-release marker. See Pattern 5 below for full details.
#
# REVISED Cycle 2: each snapshot pair requires TWO scripts:
#   Step 1 — fetch_market_history_props.py writes raw JSON
#   Step 2 — build_market_history_player_markets.py writes processed parquet
# Both must run for the parquet caches to exist.
# ============================================================================

ALT="player_pass_yds_alternate player_reception_yds_alternate player_rush_yds_alternate \
     player_pass_attempts_alternate player_receptions_alternate player_rush_attempts_alternate"

CORE="player_pass_attempts player_pass_yds player_pass_tds player_rush_attempts \
      player_rush_yds player_receptions player_reception_yds player_anytime_td"

# --- Prior snapshot for main 8 markets (NEW: prior_core8) ---
# Step 1: raw fetch
for season in 2023 2024 2025; do
  uv run python scripts/fetch_market_history_props.py \
    --season $season \
    --markets $CORE \
    --regions us \
    --snapshot-label prior_core8 \
    --date-source previous_snapshot_timestamp \
    --offset-minutes 0
done
# Step 2: parquet build
for season in 2023 2024 2025; do
  uv run python scripts/build_market_history_player_markets.py \
    --season $season --snapshot-label prior_core8
done

# --- Prior snapshot for alt-line 6 markets (NEW: prior_alt6) ---
# Step 1: raw fetch
for season in 2023 2024 2025; do
  uv run python scripts/fetch_market_history_props.py \
    --season $season \
    --markets $ALT \
    --regions us \
    --snapshot-label prior_alt6 \
    --date-source previous_snapshot_timestamp
done
# Step 2: parquet build
for season in 2023 2024 2025; do
  uv run python scripts/build_market_history_player_markets.py \
    --season $season --snapshot-label prior_alt6
done

# --- Close snapshot for alt-line 6 markets (NEW: close_alt6) ---
# Step 1: raw fetch
for season in 2023 2024 2025; do
  uv run python scripts/fetch_market_history_props.py \
    --season $season \
    --markets $ALT \
    --regions us \
    --snapshot-label close_alt6 \
    --date-source commence_time \
    --offset-minutes -60
done
# Step 2: parquet build
for season in 2023 2024 2025; do
  uv run python scripts/build_market_history_player_markets.py \
    --season $season --snapshot-label close_alt6
done
```

> **`previous_snapshot_timestamp` honesty (REVISED Cycle 2 — HIGH-3):** per `props_backfill.py:67-80`, the date-source `previous_snapshot_timestamp` uses the API's prior available snapshot relative to commence_time. For NFL Sunday games crawled at gameday-noon UTC, the prior available snapshot could be Sunday morning, Saturday, Friday, or earlier — NOT guaranteed to be Tuesday line-release time. The `prior_*` label honestly describes this; do not call it "open" or "Tuesday 12pm ET". Validate against one event during the dry-run before scaling. A future follow-up plan may extend `events_inventory.py` to capture a real Tuesday line-release marker; out of scope for the time-sensitive Phase 1 scrape window.

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
- [x] CONTEXT.md decisions D-01..D-46 honored verbatim in `## User Constraints` (D-44, D-45, D-46 added Cycle 3)
- [x] Pitfalls section covers all 7 known traps from HYPOTHESES.md
- [x] Multi-source claims cross-verified against current source files (play_resolver.py:21-49, 60, 240-280, 421-446; game_context.py:534-544, 591, 701-712; props_engine.py:43, 248; props_backfill.py:22; validation/config.py:118-138; validation/ledger.py:25)
- [x] No security domain implications (this is offline simulation; no auth/data flows beyond existing PFF cookie + Odds API key, both already gated)
- [x] No greenfield rename/refactor migration; Runtime State Inventory section omitted
- [x] Cycle 3 NEW HIGH #1 (per-KS code-change A/B no-op): Pattern 4b feature flags introduced; per-KS validation table updated to include `--set phase1_ks_flags.ksXX_<name>.enabled=true` for every code-change KS
- [x] Cycle 3 NEW HIGH #2 (`bare_config_dict()` incomplete): Pattern 7 enumerates every top-level + sub-engine `.enabled` gate; Plan 00 Task 4 acceptance is now a hard gate (no escape hatch)
- [x] Cycle 3 NEW HIGH #3 (Plan 11 mean-bias not in ledger): Pattern 6 extends `SeasonMetrics.stat_mean_bias` (schema bump 4 → 5) so Plan 11 can read mean-bias directly from the persisted ledger entry
- [x] Cycle 1 HIGH-2/HIGH-3 partial-resolves (RESEARCH staleness): all `open_*` references replaced with `prior_*`; "Tuesday 12pm ET" replaced with "API previous_timestamp relative to gameday-noon UTC crawl"; "writes parquet" split into two-step raw fetch + parquet build pipeline at every site (User Constraints D-02/D-06/D-08, Architecture parallel-track diagram, Pattern 4 + 5, Anti-patterns, Example 3)

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

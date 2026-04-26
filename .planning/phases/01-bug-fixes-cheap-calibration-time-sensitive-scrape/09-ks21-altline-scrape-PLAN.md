---
phase: 01-bug-fixes-cheap-calibration-time-sensitive-scrape
plan: 09
type: execute
wave: 1
depends_on: ["00"]
files_modified:
  - src/fantasy_sim/data/market_history/props_backfill.py
autonomous: false
requirements: [KS-21]
user_setup:
  - service: the-odds-api
    why: "KS-21 sub-deliverable: alt-line + prior-snapshot scrape consumes The Odds API historical credits"
    env_vars:
      - name: THE_ODDS_API_KEY
        source: "~/.fantasy-sim/market-history/.env (already set; do not read this file directly per AGENTS.md project guidance)"
    dashboard_config:
      - task: "Verify ~4.93M of 5M-credit tier remaining before scrape (~2 weeks tier window per PROJECT.md)"
        location: "https://the-odds-api.com (account dashboard)"
must_haves:
  truths:
    - "Per D-04: ALT_PROP_MARKETS tuple contains the 6 alternate-line markets: player_pass_yds_alternate, player_reception_yds_alternate, player_rush_yds_alternate, player_pass_attempts_alternate, player_receptions_alternate, player_rush_attempts_alternate"
    - "Per D-06 (revised 2026-04-26 — HIGH-3): three new snapshot caches written for 2023, 2024, 2025: prior_core8, prior_alt6, close_alt6 — under ~/.fantasy-sim/market-history/processed/. Note: the prior_* prefix replaces the misleading open_* prefix from the original plan; see RESEARCH.md Pattern 5 for the timing-honesty rationale."
    - "Per D-07: parquet schema reuses existing player_markets_*; one row per (player, market_key, line) tuple — no list-typed columns"
    - "Per D-08 (revised 2026-04-26 — HIGH-2): pipeline = (1) scripts/fetch_market_history_props.py writes raw JSON to ~/.fantasy-sim/market-history/raw/props/{season}/{snapshot_label}/{event_id}.json via save_raw_props_snapshot() at props_backfill.py:139; (2) scripts/build_market_history_player_markets.py reads the JSON cache and writes processed parquet via build_player_market_signals_for_season() at player_markets.py:190. BOTH steps must run for every season-snapshot pair before KS-21 is deliverable."
    - "Per D-01: scrape regions=us (DraftKings + FanDuel + Caesars consensus); 3-book pricing per row"
    - "Per D-02 (revised 2026-04-26 — HIGH-3): 'earlier' snapshot timing = whatever The Odds API returns as previous_timestamp relative to the existing gameday-noon UTC events crawl. The current pipeline does NOT store a real Tuesday line-release marker; the prior_* labels honestly describe the API semantics. Phase 4 expectations updated."
    - "Per D-03: scrape scope = prior + close snapshots for all 14 markets (8 main-line + 6 alt-line); existing close_core8 cache untouched"
    - "Per D-05: coverage = 2023, 2024, 2025 regular seasons (Odds API has no historical pre-2023; ROADMAP success criterion #5 relaxed)"
    - "Per D-25 (revised): final commit message format `feat(01-09): KS-21 PROMOTED — scrape + parquet build complete (3 seasons × 3 snapshot labels)`"
  artifacts:
    - path: "src/fantasy_sim/data/market_history/props_backfill.py"
      provides: "ALT_PROP_MARKETS tuple alongside existing DEFAULT_PROP_MARKETS"
      contains: "ALT_PROP_MARKETS:"
    - path: "~/.fantasy-sim/market-history/raw/props/2023/prior_core8/"
      provides: "Raw JSON snapshot files for 8 main-line markets, prior-timestamp, 2023 season"
    - path: "~/.fantasy-sim/market-history/raw/props/2023/prior_alt6/"
      provides: "Raw JSON snapshot files for 6 alt-line markets, prior-timestamp, 2023 season"
    - path: "~/.fantasy-sim/market-history/raw/props/2023/close_alt6/"
      provides: "Raw JSON snapshot files for 6 alt-line markets, gameday-noon-1h, 2023 season"
    - path: "~/.fantasy-sim/market-history/processed/player_markets_2023_prior_core8.parquet"
      provides: "Built parquet for 8 main-line markets, prior-timestamp, 2023 season"
    - path: "~/.fantasy-sim/market-history/processed/player_markets_2024_prior_core8.parquet"
      provides: "Built parquet for 8 main-line markets, prior-timestamp, 2024 season"
    - path: "~/.fantasy-sim/market-history/processed/player_markets_2025_prior_core8.parquet"
      provides: "Built parquet for 8 main-line markets, prior-timestamp, 2025 season"
    - path: "~/.fantasy-sim/market-history/processed/player_markets_2023_prior_alt6.parquet"
      provides: "Built parquet for 6 alt-line markets, prior-timestamp, 2023 season"
    - path: "~/.fantasy-sim/market-history/processed/player_markets_2024_prior_alt6.parquet"
      provides: "Built parquet for 6 alt-line markets, prior-timestamp, 2024 season"
    - path: "~/.fantasy-sim/market-history/processed/player_markets_2025_prior_alt6.parquet"
      provides: "Built parquet for 6 alt-line markets, prior-timestamp, 2025 season"
    - path: "~/.fantasy-sim/market-history/processed/player_markets_2023_close_alt6.parquet"
      provides: "Built parquet for 6 alt-line markets, close, 2023 season"
    - path: "~/.fantasy-sim/market-history/processed/player_markets_2024_close_alt6.parquet"
      provides: "Built parquet for 6 alt-line markets, close, 2024 season"
    - path: "~/.fantasy-sim/market-history/processed/player_markets_2025_close_alt6.parquet"
      provides: "Built parquet for 6 alt-line markets, close, 2025 season"
  key_links:
    - from: "scripts/fetch_market_history_props.py CLI"
      to: "props_backfill.ALT_PROP_MARKETS"
      via: "--markets $(python -c \"from fantasy_sim.data.market_history.props_backfill import ALT_PROP_MARKETS; print(' '.join(ALT_PROP_MARKETS))\")"
      pattern: "ALT_PROP_MARKETS"
    - from: "scripts/fetch_market_history_props.py"
      to: "scripts/build_market_history_player_markets.py"
      via: "shared --season + --snapshot-label conventions; both must run per pair"
      pattern: "build_market_history_player_markets"
---

<objective>
Implement KS-21 sub-deliverable — execute The Odds API historical scrape for the 6 alternate-line markets (D-04) plus the prior-line snapshot for the existing 8 main markets (D-03), across 2023, 2024, 2025 regular seasons (D-05). Use the existing `scripts/fetch_market_history_props.py` for raw fetch AND `scripts/build_market_history_player_markets.py` for processed parquet build (D-08 revised — see RESEARCH.md Pattern 4). This adds 9 new processed parquet caches under `~/.fantasy-sim/market-history/processed/` plus the corresponding raw JSON tree under `~/.fantasy-sim/market-history/raw/props/`, without modifying the existing `close_core8` cache.

Per the 2026-04-26 replan addressing Codex `01-REVIEWS.md` HIGH-2 and HIGH-3:
- **HIGH-2 fix:** Plan 09 now explicitly invokes BOTH the raw-fetch script (`fetch_market_history_props.py` writes JSON) AND the processed-build script (`build_market_history_player_markets.py` writes parquet). The original plan only ran the raw-fetch script and falsely asserted parquet appeared directly.
- **HIGH-3 fix:** Snapshot labels renamed `open_*` → `prior_*` to honestly describe the Odds API's `previous_timestamp` semantics. Current pipeline does NOT capture a Tuesday line-release marker; `prior_*` describes "API previous-available snapshot relative to gameday-noon UTC crawl". Phase 4 must reference `prior_*` labels.

Purpose: KS-21 the *requirement* (engine integration) is mapped to Phase 4. KS-21 the *scrape sub-deliverable* runs in Phase 1 because the high-credit Odds API tier (~4.93M of 5M remaining, ~2 weeks window per PROJECT.md) is time-sensitive. Phase 4's `OddsApiCdfLoader` consumer needs this data ready when it ships.

Output: 9 new processed parquet files (3 seasons × 3 snapshot labels: `prior_core8`, `prior_alt6`, `close_alt6`); ALT_PROP_MARKETS tuple in source code; per-season row-count + parquet-row-count log entries; remaining-credit balance verified.

**checkpoint:human-action gate before scrape execution** — operator must confirm credit balance > 4.0M before the scrape kicks off (Task 2). Plan is `autonomous: false` for this reason.

**Dependency on Plan 00:** This plan depends on Plan 00 only for the phase logs directory (Task 5 in Plan 00). The scrape itself is independent of the validate.py harness extension; it runs in parallel with the per-KS A/B work (which also depends on Plan 00 for true isolation).
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-CONTEXT.md
@.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-RESEARCH.md
@.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-VALIDATION.md
@scripts/fetch_market_history_props.py
@scripts/build_market_history_player_markets.py
@src/fantasy_sim/data/market_history/props_backfill.py
@src/fantasy_sim/data/market_history/player_markets.py
@src/fantasy_sim/data/market_history/events_inventory.py

<interfaces>
From src/fantasy_sim/data/market_history/props_backfill.py (current):

```python
DEFAULT_PROP_MARKETS: tuple[str, ...] = (
    "player_pass_attempts",
    "player_pass_yds",
    "player_pass_tds",
    "player_rush_attempts",
    "player_rush_yds",
    "player_receptions",
    "player_reception_yds",
    "player_anytime_td",
)
```

KS-21 adds (D-04):

```python
ALT_PROP_MARKETS: tuple[str, ...] = (
    "player_pass_yds_alternate",
    "player_reception_yds_alternate",
    "player_rush_yds_alternate",
    "player_pass_attempts_alternate",
    "player_receptions_alternate",
    "player_rush_attempts_alternate",
)
```

From scripts/fetch_market_history_props.py CLI (raw fetch — writes JSON):
- `--season` (int, nargs+, required)
- `--markets` (default: list(DEFAULT_PROP_MARKETS))
- `--regions` (default: us)
- `--snapshot-label` (default: close_core8)
- `--date-source` ∈ {commence_time, snapshot_date, previous_snapshot_timestamp, next_snapshot_timestamp} (default: commence_time)
- `--offset-minutes` (int, default: 0)
- `--delay` (float, default: DEFAULT_DELAY_SECONDS)
- `--limit` (int, default: None)
- `--force` (action store_true)

Writes: `~/.fantasy-sim/market-history/raw/props/{season}/{snapshot_label}/{event_id}.json` via `save_raw_props_snapshot()` at props_backfill.py:139.

From scripts/build_market_history_player_markets.py CLI (parquet build — reads JSON, writes parquet):
- `--season` (int, nargs+, required)
- `--snapshot-label` (default: close_core8)

Reads: `~/.fantasy-sim/market-history/raw/props/{season}/{snapshot_label}/*.json`
Writes: `~/.fantasy-sim/market-history/processed/player_markets_{season}_{snapshot_label}.parquet` via `build_player_market_signals_for_season()` at player_markets.py:190.

Both scripts MUST run for every (season, snapshot_label) pair to produce a usable parquet artifact.
</interfaces>

</context>

<tasks>

<task type="auto">
  <name>Task 1: Add ALT_PROP_MARKETS tuple to props_backfill.py</name>
  <files>src/fantasy_sim/data/market_history/props_backfill.py</files>
  <read_first>
    - src/fantasy_sim/data/market_history/props_backfill.py (current DEFAULT_PROP_MARKETS at line 22)
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-CONTEXT.md (D-04)
  </read_first>
  <action>
Edit `src/fantasy_sim/data/market_history/props_backfill.py`. Add the new tuple immediately after `DEFAULT_PROP_MARKETS` (around line 31):

```python
DEFAULT_PROP_MARKETS: tuple[str, ...] = (
    "player_pass_attempts",
    "player_pass_yds",
    "player_pass_tds",
    "player_rush_attempts",
    "player_rush_yds",
    "player_receptions",
    "player_reception_yds",
    "player_anytime_td",
)

# KS-21 D-04: alternate-line markets — multi-line over/under markets that define
# an empirical CDF directly. Phase 1 scrapes these as time-sensitive infrastructure;
# Phase 4 OddsApiCdfLoader consumes them.
ALT_PROP_MARKETS: tuple[str, ...] = (
    "player_pass_yds_alternate",
    "player_reception_yds_alternate",
    "player_rush_yds_alternate",
    "player_pass_attempts_alternate",
    "player_receptions_alternate",
    "player_rush_attempts_alternate",
)
```

Run pytest:
```bash
uv run pytest tests/test_data/test_market_history -v 2>&1 | tail -10
```

EXPECTED: All existing tests pass (the new tuple is additive, no semantic change).

Commit: `feat(01-09): add ALT_PROP_MARKETS tuple per KS-21 D-04`
  </action>
  <verify>
    <automated>grep -c "ALT_PROP_MARKETS:" src/fantasy_sim/data/market_history/props_backfill.py && grep -c "player_pass_yds_alternate" src/fantasy_sim/data/market_history/props_backfill.py</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "ALT_PROP_MARKETS: tuple\\[str, \\.\\.\\.\\] = (" src/fantasy_sim/data/market_history/props_backfill.py` returns 1
    - `grep -c "player_pass_yds_alternate" src/fantasy_sim/data/market_history/props_backfill.py` returns 1
    - All 6 alt-line market keys present
    - `uv run pytest tests/test_data/test_market_history -v 2>&1 | tail -5` shows `passed` with no `failed`
    - `git log -1 --pretty=%s` matches `feat(01-09): add ALT_PROP_MARKETS`
  </acceptance_criteria>
  <done>ALT_PROP_MARKETS tuple in source; existing tests still pass.</done>
</task>

<task type="checkpoint:human-action" gate="blocking">
  <name>Task 2: Operator confirms Odds API credit balance > 4.0M before scrape</name>
  <what-built>ALT_PROP_MARKETS tuple is in source. Scrape will consume historical credits — risk of blowing the budget per RESEARCH.md Pitfall 6.</what-built>
  <how-to-verify>
    1. Visit https://the-odds-api.com and sign in
    2. Check "Requests remaining" or equivalent field on the account dashboard
    3. Confirm > 4.0M remaining (PROJECT.md and CLAUDE.md note ~4.93M out of 5M-tier as of 2026-04-26 with ~2-week window)
    4. If < 4.0M: STOP. Document in PROMOTION-NOTES.md and re-evaluate scope (e.g., drop 2025 season, drop alt-line scope)
    5. If ≥ 4.0M: type "approved — credit balance ${BALANCE}M" to proceed to Task 3
  </how-to-verify>
  <resume-signal>Type "approved — credit balance NM" or describe blockers</resume-signal>
</task>

<task type="auto">
  <name>Task 3: Dry-run RAW fetch + PARQUET BUILD for one season-week to validate full pipeline</name>
  <files>(no source modifications — runs both scripts with --limit 1)</files>
  <read_first>
    - scripts/fetch_market_history_props.py (raw fetch CLI)
    - scripts/build_market_history_player_markets.py (parquet build CLI)
    - src/fantasy_sim/data/market_history/props_backfill.py (post-Task 1, with ALT_PROP_MARKETS)
    - src/fantasy_sim/data/market_history/player_markets.py (build_player_market_signals_for_season at line 190)
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-CONTEXT.md (D-02 prior-snapshot semantics, D-06 revised labels, D-08 revised pipeline)
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-RESEARCH.md (Pattern 4 pipeline, Pattern 5 label naming)
  </read_first>
  <action>
Run a single-event dry run for 2024 with `--limit 1` to validate the full pipeline (raw fetch THEN parquet build) and inspect the response headers (`x-requests-remaining`):

```bash
ALT="player_pass_yds_alternate player_reception_yds_alternate player_rush_yds_alternate player_pass_attempts_alternate player_receptions_alternate player_rush_attempts_alternate"
CORE="player_pass_attempts player_pass_yds player_pass_tds player_rush_attempts player_rush_yds player_receptions player_reception_yds player_anytime_td"

LOG_DIR=".planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs"

# === STEP 1a: Raw fetch — prior_core8 (1 event) ===
uv run python scripts/fetch_market_history_props.py \
  --season 2024 \
  --markets $CORE \
  --regions us \
  --snapshot-label prior_core8 \
  --date-source previous_snapshot_timestamp \
  --offset-minutes 0 \
  --limit 1 \
  2>&1 | tee "${LOG_DIR}/dry_run_prior_core8_raw.log"

# Inspect remaining credits
grep -E "x-requests-remaining|requests-remaining|cost|saved" "${LOG_DIR}/dry_run_prior_core8_raw.log" | head -5

# Verify raw JSON exists
ls ~/.fantasy-sim/market-history/raw/props/2024/prior_core8/ | head -3

# === STEP 1b: Build processed parquet from prior_core8 raw ===
uv run python scripts/build_market_history_player_markets.py \
  --season 2024 \
  --snapshot-label prior_core8 \
  2>&1 | tee "${LOG_DIR}/dry_run_prior_core8_build.log"

# Verify parquet exists with rows
ls -la ~/.fantasy-sim/market-history/processed/player_markets_2024_prior_core8.parquet
uv run python -c "import polars as pl; df = pl.read_parquet('${HOME}/.fantasy-sim/market-history/processed/player_markets_2024_prior_core8.parquet'); print(f'rows={df.height}, snapshot_labels={df[\"snapshot_label\"].unique().to_list()}')"

# === STEP 2a: Raw fetch — prior_alt6 (1 event) ===
uv run python scripts/fetch_market_history_props.py \
  --season 2024 \
  --markets $ALT \
  --regions us \
  --snapshot-label prior_alt6 \
  --date-source previous_snapshot_timestamp \
  --offset-minutes 0 \
  --limit 1 \
  2>&1 | tee "${LOG_DIR}/dry_run_prior_alt6_raw.log"

# === STEP 2b: Build processed parquet from prior_alt6 raw ===
uv run python scripts/build_market_history_player_markets.py \
  --season 2024 \
  --snapshot-label prior_alt6 \
  2>&1 | tee "${LOG_DIR}/dry_run_prior_alt6_build.log"

uv run python -c "import polars as pl; df = pl.read_parquet('${HOME}/.fantasy-sim/market-history/processed/player_markets_2024_prior_alt6.parquet'); print(f'rows={df.height}, snapshot_labels={df[\"snapshot_label\"].unique().to_list()}, market_keys={df[\"market_key\"].unique().to_list()}')"

# === STEP 3a: Raw fetch — close_alt6 (1 event) ===
uv run python scripts/fetch_market_history_props.py \
  --season 2024 \
  --markets $ALT \
  --regions us \
  --snapshot-label close_alt6 \
  --date-source commence_time \
  --offset-minutes -60 \
  --limit 1 \
  2>&1 | tee "${LOG_DIR}/dry_run_close_alt6_raw.log"

# === STEP 3b: Build processed parquet from close_alt6 raw ===
uv run python scripts/build_market_history_player_markets.py \
  --season 2024 \
  --snapshot-label close_alt6 \
  2>&1 | tee "${LOG_DIR}/dry_run_close_alt6_build.log"

uv run python -c "import polars as pl; df = pl.read_parquet('${HOME}/.fantasy-sim/market-history/processed/player_markets_2024_close_alt6.parquet'); print(f'rows={df.height}, snapshot_labels={df[\"snapshot_label\"].unique().to_list()}')"
```

Inspect the dry-run outputs:
- The 3 raw-fetch runs together should consume on the order of 100-300 credits (3 events × markets × books × snapshots; varies by API pricing).
- Each parquet must have > 0 rows, and the `snapshot_label` column must contain only the requested label string (e.g., `prior_core8`).
- For `prior_alt6`, the `market_key` column should contain ONLY the 6 alt-line market keys (verifies the right markets were scraped).

Append to `.../logs/PROMOTION-NOTES.md` under `## KS-21 dry-run`:
- The 3 snapshot labels' raw JSON file counts (from `ls ~/.fantasy-sim/market-history/raw/props/2024/<label>/`)
- The 3 snapshot labels' parquet paths and row counts
- Estimated full-scrape credit cost (extrapolated from --limit 1)
- Decision: proceed to full scrape (Task 4) or abort

Commit: `chore(01-09): KS-21 dry-run — raw fetch + parquet build verified for 3 labels (1 event each, 2024)`
  </action>
  <verify>
    <automated>ls ~/.fantasy-sim/market-history/processed/player_markets_2024_prior_core8.parquet ~/.fantasy-sim/market-history/processed/player_markets_2024_prior_alt6.parquet ~/.fantasy-sim/market-history/processed/player_markets_2024_close_alt6.parquet 2>&1 | wc -l | tr -d ' '</automated>
  </verify>
  <acceptance_criteria>
    - The verify command returns `3` (all 3 dry-run parquet files exist)
    - 3 raw-fetch log files AND 3 build log files exist under the phase logs directory
    - PROMOTION-NOTES.md contains a section `## KS-21 dry-run` with raw-file counts, parquet row counts, and credit-cost estimate
    - Per-season full-scrape credit estimate is documented (extrapolated from dry-run)
    - Decision to proceed to Task 4 (or abort) is recorded
    - The `prior_alt6` parquet's `market_key` column contains ONLY the 6 alt-line market keys (no main-line leak)
    - `git log -1 --pretty=%s` matches `chore(01-09): KS-21 dry-run`
  </acceptance_criteria>
  <done>Dry-run validated; 3 snapshot labels write to BOTH raw JSON tree AND processed parquet; full-scrape credit estimate documented.</done>
</task>

<task type="auto">
  <name>Task 4: Execute full RAW fetch — 3 seasons × 3 snapshot labels = 9 raw-cache trees</name>
  <files>(no source modifications — runs scripts/fetch_market_history_props.py for full seasons)</files>
  <read_first>
    - scripts/fetch_market_history_props.py
    - src/fantasy_sim/data/market_history/props_backfill.py (post-Task 1)
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/PROMOTION-NOTES.md (Task 3 dry-run estimate)
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-CONTEXT.md (D-05 coverage, D-06 revised labels)
  </read_first>
  <action>
Execute the full raw fetch — 3 seasons × 3 snapshot labels = 9 runs. Front-load `prior_core8` (smallest add) per RESEARCH.md Pitfall 6 strategy.

```bash
ALT="player_pass_yds_alternate player_reception_yds_alternate player_rush_yds_alternate player_pass_attempts_alternate player_receptions_alternate player_rush_attempts_alternate"
CORE="player_pass_attempts player_pass_yds player_pass_tds player_rush_attempts player_rush_yds player_receptions player_reception_yds player_anytime_td"

LOG_DIR=".planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs"

# === Phase 1: prior_core8 (smallest — 8 markets × 1 snapshot × 3 seasons) ===
for season in 2023 2024 2025; do
  echo "=== prior_core8 ${season} ===" >&2
  uv run python scripts/fetch_market_history_props.py \
    --season $season \
    --markets $CORE \
    --regions us \
    --snapshot-label prior_core8 \
    --date-source previous_snapshot_timestamp \
    --offset-minutes 0 \
    2>&1 | tee "${LOG_DIR}/scrape_${season}_prior_core8.log"
  echo "--- prior_core8 ${season} complete; remaining credits:" >&2
  grep "x-requests-remaining" "${LOG_DIR}/scrape_${season}_prior_core8.log" | tail -1
done

# === Phase 2: prior_alt6 (6 markets × 1 snapshot × 3 seasons) ===
for season in 2023 2024 2025; do
  echo "=== prior_alt6 ${season} ===" >&2
  uv run python scripts/fetch_market_history_props.py \
    --season $season \
    --markets $ALT \
    --regions us \
    --snapshot-label prior_alt6 \
    --date-source previous_snapshot_timestamp \
    --offset-minutes 0 \
    2>&1 | tee "${LOG_DIR}/scrape_${season}_prior_alt6.log"
  echo "--- prior_alt6 ${season} complete; remaining credits:" >&2
  grep "x-requests-remaining" "${LOG_DIR}/scrape_${season}_prior_alt6.log" | tail -1
done

# === Phase 3: close_alt6 (6 markets × 1 snapshot × 3 seasons) ===
for season in 2023 2024 2025; do
  echo "=== close_alt6 ${season} ===" >&2
  uv run python scripts/fetch_market_history_props.py \
    --season $season \
    --markets $ALT \
    --regions us \
    --snapshot-label close_alt6 \
    --date-source commence_time \
    --offset-minutes -60 \
    2>&1 | tee "${LOG_DIR}/scrape_${season}_close_alt6.log"
  echo "--- close_alt6 ${season} complete; remaining credits:" >&2
  grep "x-requests-remaining" "${LOG_DIR}/scrape_${season}_close_alt6.log" | tail -1
done

# Verify all 9 raw-tree directories exist with > 0 JSON files each
for season in 2023 2024 2025; do
  for label in prior_core8 prior_alt6 close_alt6; do
    count=$(ls ~/.fantasy-sim/market-history/raw/props/${season}/${label}/ 2>/dev/null | wc -l | tr -d ' ')
    echo "${season} ${label}: ${count} JSON files"
  done
done
```

Append a per-season raw-file-count + credit-balance log to `.../logs/PROMOTION-NOTES.md` under `## KS-21 raw scrape`:

```markdown
## KS-21 raw scrape

| Season | Snapshot | Raw JSON files | Credits before | Credits after | Δ |
|--------|----------|---------------|----------------|---------------|---|
| 2023 | prior_core8 | ... | ... | ... | ... |
| 2024 | prior_core8 | ... | ... | ... | ... |
| 2025 | prior_core8 | ... | ... | ... | ... |
| 2023 | prior_alt6  | ... | ... | ... | ... |
| 2024 | prior_alt6  | ... | ... | ... | ... |
| 2025 | prior_alt6  | ... | ... | ... | ... |
| 2023 | close_alt6 | ... | ... | ... | ... |
| 2024 | close_alt6 | ... | ... | ... | ... |
| 2025 | close_alt6 | ... | ... | ... | ... |
```

Commit: `chore(01-09): KS-21 raw fetch — 9 JSON cache trees (prior_core8, prior_alt6, close_alt6 × 2023, 2024, 2025)`
  </action>
  <verify>
    <automated>for s in 2023 2024 2025; do for l in prior_core8 prior_alt6 close_alt6; do ls ~/.fantasy-sim/market-history/raw/props/${s}/${l}/ 2>/dev/null | head -1 | wc -l; done; done | awk '{s+=$1} END {print s}'</automated>
  </verify>
  <acceptance_criteria>
    - The verify command returns `9` (all 9 raw-tree directories have at least 1 JSON file each)
    - The existing `~/.fantasy-sim/market-history/processed/player_markets_*_close_core8.parquet` files are UNCHANGED — verify with `find ~/.fantasy-sim/market-history/processed -name "player_markets_*_close_core8.parquet" -newer .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-CONTEXT.md` returns 0 hits (none modified after CONTEXT was written)
    - PROMOTION-NOTES.md contains the per-season raw-count + credit table under `## KS-21 raw scrape`
    - Per-season scrape log files exist (9 total)
    - Final remaining credit balance is documented (must be > 0; ideally > 3.5M)
    - `git log -1 --pretty=%s` matches `chore(01-09): KS-21 raw fetch`
  </acceptance_criteria>
  <done>9 raw cache trees written; existing main-line cache untouched; credit balance documented.</done>
</task>

<task type="auto">
  <name>Task 5: Build processed parquet from raw cache — 9 parquet files</name>
  <files>(no source modifications — runs scripts/build_market_history_player_markets.py per pair)</files>
  <read_first>
    - scripts/build_market_history_player_markets.py
    - src/fantasy_sim/data/market_history/player_markets.py (build_player_market_signals_for_season at line 190)
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/PROMOTION-NOTES.md (Task 4 raw-fetch results)
  </read_first>
  <action>
Build the 9 processed parquet files from the raw JSON cache populated by Task 4. This step requires NO API credits — it's a local file transformation.

```bash
LOG_DIR=".planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs"

for season in 2023 2024 2025; do
  for label in prior_core8 prior_alt6 close_alt6; do
    echo "=== build ${season}_${label} ===" >&2
    uv run python scripts/build_market_history_player_markets.py \
      --season $season \
      --snapshot-label $label \
      2>&1 | tee "${LOG_DIR}/build_${season}_${label}.log"
  done
done

# Verify all 9 processed parquet files exist with > 0 rows
for season in 2023 2024 2025; do
  for label in prior_core8 prior_alt6 close_alt6; do
    parquet=~/.fantasy-sim/market-history/processed/player_markets_${season}_${label}.parquet
    rows=$(uv run python -c "import polars as pl; print(pl.read_parquet('${parquet}').height)")
    echo "${season} ${label}: ${rows} rows"
  done
done | tee "${LOG_DIR}/build_verification.log"
```

Append a per-season parquet-row-count log to `.../logs/PROMOTION-NOTES.md` under `## KS-21 processed parquet build`:

```markdown
## KS-21 processed parquet build

| Season | Snapshot | Parquet rows | Distinct players | Distinct markets |
|--------|----------|--------------|------------------|------------------|
| 2023 | prior_core8 | ... | ... | 8 |
| 2024 | prior_core8 | ... | ... | 8 |
| 2025 | prior_core8 | ... | ... | 8 |
| 2023 | prior_alt6  | ... | ... | 6 |
| 2024 | prior_alt6  | ... | ... | 6 |
| 2025 | prior_alt6  | ... | ... | 6 |
| 2023 | close_alt6 | ... | ... | 6 |
| 2024 | close_alt6 | ... | ... | 6 |
| 2025 | close_alt6 | ... | ... | 6 |
```

Commit: `chore(01-09): KS-21 build processed parquet — 9 player_markets files (prior_core8, prior_alt6, close_alt6 × 2023, 2024, 2025)`
  </action>
  <verify>
    <automated>ls ~/.fantasy-sim/market-history/processed/player_markets_2023_prior_core8.parquet ~/.fantasy-sim/market-history/processed/player_markets_2024_prior_core8.parquet ~/.fantasy-sim/market-history/processed/player_markets_2025_prior_core8.parquet ~/.fantasy-sim/market-history/processed/player_markets_2023_prior_alt6.parquet ~/.fantasy-sim/market-history/processed/player_markets_2024_prior_alt6.parquet ~/.fantasy-sim/market-history/processed/player_markets_2025_prior_alt6.parquet ~/.fantasy-sim/market-history/processed/player_markets_2023_close_alt6.parquet ~/.fantasy-sim/market-history/processed/player_markets_2024_close_alt6.parquet ~/.fantasy-sim/market-history/processed/player_markets_2025_close_alt6.parquet 2>&1 | wc -l | tr -d ' '</automated>
  </verify>
  <acceptance_criteria>
    - The verify command returns `9` (all 9 processed parquet files exist)
    - Each new parquet file has > 0 rows
    - The `snapshot_label` column in each parquet matches the file's label suffix
    - PROMOTION-NOTES.md contains the per-season parquet-row table under `## KS-21 processed parquet build`
    - 9 build log files exist under the phase logs directory
    - The existing `*_close_core8.parquet` files are UNCHANGED (D-06 invariant from Task 4 still holds)
    - `git log -1 --pretty=%s` matches `chore(01-09): KS-21 build processed parquet`
  </acceptance_criteria>
  <done>9 processed parquet files built; row counts logged.</done>
</task>

<task type="auto">
  <name>Task 6: Schema and timing verification — confirm parquet conforms to existing player_markets schema and prior_* labels carry sensible timestamps</name>
  <files>(no source modifications — read-only inspection)</files>
  <read_first>
    - src/fantasy_sim/data/market_history/player_markets.py (PLAYER_MARKET_SIGNAL_SCHEMA)
    - ~/.fantasy-sim/market-history/processed/player_markets_2024_close_core8.parquet (existing reference schema)
    - one of the new parquet files (Task 5 output)
  </read_first>
  <action>
Run schema and timing-sanity checks on the new parquet files:

```bash
LOG_DIR=".planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs"

# Schema check: new parquet columns must match existing close_core8 reference
uv run python <<'EOF'
import polars as pl
ref = pl.read_parquet(f"{__import__('os').path.expanduser('~')}/.fantasy-sim/market-history/processed/player_markets_2024_close_core8.parquet")
print(f"Reference (close_core8) columns: {ref.columns}")

for season in (2023, 2024, 2025):
    for label in ("prior_core8", "prior_alt6", "close_alt6"):
        path = f"{__import__('os').path.expanduser('~')}/.fantasy-sim/market-history/processed/player_markets_{season}_{label}.parquet"
        try:
            df = pl.read_parquet(path)
            cols_match = sorted(df.columns) == sorted(ref.columns)
            label_uniform = df["snapshot_label"].n_unique() == 1 and df["snapshot_label"].unique().to_list() == [label]
            ts_present = df["snapshot_timestamp"].null_count() == 0
            sample_ts = df["snapshot_timestamp"].head(3).to_list()
            print(f"{season} {label}: rows={df.height} cols_match={cols_match} label_uniform={label_uniform} ts_no_nulls={ts_present}")
            print(f"  sample timestamps: {sample_ts}")
        except FileNotFoundError:
            print(f"{season} {label}: MISSING")
EOF
```

Pipe the output to a verification log:

```bash
uv run python <<'EOF' | tee "${LOG_DIR}/schema_and_timing_verification.log"
import polars as pl, os
ref = pl.read_parquet(f"{os.path.expanduser('~')}/.fantasy-sim/market-history/processed/player_markets_2024_close_core8.parquet")
print(f"Reference (close_core8) columns: {sorted(ref.columns)}")
print()

results = []
for season in (2023, 2024, 2025):
    for label in ("prior_core8", "prior_alt6", "close_alt6"):
        path = f"{os.path.expanduser('~')}/.fantasy-sim/market-history/processed/player_markets_{season}_{label}.parquet"
        try:
            df = pl.read_parquet(path)
            cols_match = sorted(df.columns) == sorted(ref.columns)
            label_uniform = df["snapshot_label"].n_unique() == 1 and df["snapshot_label"].unique().to_list() == [label]
            ts_present = df["snapshot_timestamp"].null_count() == 0
            sample_ts = df["snapshot_timestamp"].head(3).to_list()
            print(f"{season} {label}: rows={df.height} cols_match={cols_match} label_uniform={label_uniform} ts_no_nulls={ts_present}")
            print(f"  sample timestamps: {sample_ts}")
            results.append((season, label, df.height, cols_match, label_uniform, ts_present))
        except FileNotFoundError:
            print(f"{season} {label}: MISSING")
            results.append((season, label, 0, False, False, False))
print()
print(f"Total parquet files verified: {sum(1 for r in results if r[2] > 0)}/9")
print(f"All schemas match reference: {all(r[3] for r in results if r[2] > 0)}")
print(f"All snapshot_label uniform: {all(r[4] for r in results if r[2] > 0)}")
print(f"All snapshot_timestamp non-null: {all(r[5] for r in results if r[2] > 0)}")
EOF
```

Append `## KS-21 schema and timing verification` to PROMOTION-NOTES.md with the inspection results.

Specifically check:
1. **Schema match:** all 9 parquet files have the same column set as the reference `close_core8` parquet (existing schema invariant per D-07).
2. **Label uniformity:** each parquet's `snapshot_label` column contains ONLY the file's label suffix (e.g., `prior_core8` parquet has only the value `prior_core8` in that column).
3. **Timestamp sanity:** each parquet's `snapshot_timestamp` column has no nulls. For `prior_*` labels, sample timestamps should differ from the corresponding `close_alt6` / `close_core8` row timestamps (proves the prior-snapshot semantic is being captured, not just a duplicate of close).

For prior-vs-close timing comparison (sanity that they're actually different snapshots):

```bash
uv run python <<'EOF' | tee -a "${LOG_DIR}/schema_and_timing_verification.log"
import polars as pl, os
prior = pl.read_parquet(f"{os.path.expanduser('~')}/.fantasy-sim/market-history/processed/player_markets_2024_prior_alt6.parquet")
close = pl.read_parquet(f"{os.path.expanduser('~')}/.fantasy-sim/market-history/processed/player_markets_2024_close_alt6.parquet")
# Same event, prior vs close — timestamps should differ by hours-to-days
sample_event = prior["event_id"].head(1).to_list()[0] if prior.height > 0 else None
if sample_event:
    p_ts = prior.filter(pl.col("event_id") == sample_event)["snapshot_timestamp"].head(1).to_list()
    c_ts = close.filter(pl.col("event_id") == sample_event)["snapshot_timestamp"].head(1).to_list()
    print(f"Event {sample_event}: prior_alt6 ts={p_ts}, close_alt6 ts={c_ts}")
    print(f"  → these MUST differ if prior_* semantic is correctly captured")
EOF
```

Commit: `chore(01-09): KS-21 schema and timing verification (9 parquet files conform to player_markets schema; prior_* timestamps differ from close_*)`
  </action>
  <verify>
    <automated>grep -c "All schemas match reference: True" .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/schema_and_timing_verification.log</automated>
  </verify>
  <acceptance_criteria>
    - Schema verification log contains "All schemas match reference: True"
    - Schema verification log contains "All snapshot_label uniform: True"
    - Schema verification log contains "All snapshot_timestamp non-null: True"
    - For at least one event, prior_alt6 and close_alt6 timestamps differ (sanity check that prior_* is not a label-only rename of close_*)
    - PROMOTION-NOTES.md contains `## KS-21 schema and timing verification` section
    - `git log -1 --pretty=%s` matches `chore(01-09): KS-21 schema and timing verification`
  </acceptance_criteria>
  <done>9 parquet files conform to schema and timing invariants; prior_* and close_* are demonstrably different snapshots.</done>
</task>

<task type="auto">
  <name>Task 7: Promotion-state commit — KS-21 PROMOTED</name>
  <files>(no source modifications)</files>
  <read_first>
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/PROMOTION-NOTES.md (all KS-21 sections)
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/schema_and_timing_verification.log
  </read_first>
  <action>
Per D-25 (revised — promotion-state commit per KS plan), create the final promotion commit + SUMMARY.

Create `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-09-SUMMARY.md`:

```markdown
# Plan 09 Summary — KS-21 alt-line scrape (raw + processed parquet)

**Promotion state:** PROMOTED
**Phase:** 1 (Bug Fixes, Cheap Calibration & Time-Sensitive Scrape)
**Wave:** 1 (parallel with KS-01)
**Final commit:** $(git log -1 --pretty=%H)

## What shipped

1. `ALT_PROP_MARKETS` tuple in `src/fantasy_sim/data/market_history/props_backfill.py`
2. 9 raw JSON cache trees under `~/.fantasy-sim/market-history/raw/props/{season}/{label}/`
3. 9 processed parquet files at `~/.fantasy-sim/market-history/processed/player_markets_{season}_{label}.parquet`
4. Schema and timing verification confirming parity with the existing `close_core8` reference and demonstrating prior-vs-close timestamp difference

## Why this matters (Codex review HIGH-2, HIGH-3)

The original Plan 09 had two correctness problems flagged by Codex:
- **HIGH-2:** It called only `fetch_market_history_props.py` (which writes RAW JSON) and then asserted parquet appeared. The processed parquet downstream code requires comes from a separate `build_market_history_player_markets.py` step. The replan invokes BOTH scripts per (season, label) pair.
- **HIGH-3:** It labeled the prior-timestamp snapshots as `open_*` and asserted the timing was "Tuesday 12pm ET line release". The current pipeline does NOT capture a Tuesday line-release marker; the API's `previous_timestamp` is whatever the API returns relative to the existing gameday-noon UTC events crawl. The replan renamed labels to `prior_*` to honestly describe semantics, with a documented follow-up to extend `events_inventory.py` if a real Tuesday marker is wanted.

Both fixes are now reflected in the deliverable.

## Phase 4 contract update

Phase 4's `OddsApiCdfLoader` consumer references the new parquet files via the
`prior_*` snapshot labels. The loader interface should accept a `snapshot_label`
parameter that defaults to `prior_alt6` (the alt-line CDF source) with `close_alt6`
as the close-snapshot fallback.

## Credit budget

Final remaining credits: <fill in from PROMOTION-NOTES.md ## KS-21 raw scrape>
Δ from pre-Phase-1: <fill in>

## Coverage gap acknowledgment

Per D-05: scrape covers 2023, 2024, 2025 only (Odds API has no historical pre-2023).
ROADMAP success criterion #5 ("2022-2024 weeks 1-18") is relaxed accordingly. The
2022 season has no alt-line history available from this provider; alternative sources
deferred as a long-tail follow-up.
```

Then commit:

```bash
git add .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-09-SUMMARY.md
git commit -m "feat(01-09): KS-21 PROMOTED — scrape + parquet build complete (3 seasons × 3 snapshot labels)

Wave 1 KS-21 sub-deliverable. 9 raw JSON cache trees + 9 processed
parquet files written for prior_core8, prior_alt6, close_alt6 × 2023,
2024, 2025. Existing close_core8 cache untouched.

Closes Codex review HIGH-2 (raw vs parquet pipeline split) and HIGH-3
(snapshot label timing-honesty: open_* renamed to prior_*).

Phase 4 OddsApiCdfLoader consumer references the new prior_* labels."
```
  </action>
  <verify>
    <automated>test -f .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-09-SUMMARY.md && grep -c "PROMOTED" .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-09-SUMMARY.md</automated>
  </verify>
  <acceptance_criteria>
    - SUMMARY file exists with "Promotion state: PROMOTED"
    - `git log -1 --pretty=%s` matches `feat(01-09): KS-21 PROMOTED`
    - SUMMARY captures the credit-budget delta and coverage-gap acknowledgment
  </acceptance_criteria>
  <done>KS-21 PROMOTED; SUMMARY captures the wave 1 deliverable.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| The Odds API → local raw cache | External HTTP boundary. Already gated by httpx + API key in `~/.fantasy-sim/market-history/.env` (per AGENTS.md, never read this file directly). |
| Local raw cache → processed parquet | Internal — same project; idempotent build via `build_market_history_player_markets.py`. |
| Processed parquet → downstream Phase 4 engine | Internal — same project. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-01-09-01 | D (Denial of service via credit exhaustion) | The Odds API credit budget | mitigate | Task 2 operator gate confirms ≥ 4.0M before scrape; Task 3 dry-run extrapolates full cost; per-season logging (Task 4) catches budget burn early. |
| T-01-09-02 | T (Tampering) | Existing close_core8 parquet cache | mitigate | D-06: new snapshots use distinct labels; verify command in Tasks 4 and 5 acceptance asserts close_core8 files unchanged. |
| T-01-09-03 | I (Information disclosure) | API key in `~/.fantasy-sim/market-history/.env` | accept | Per AGENTS.md project guidance: never read this file directly. The `events_inventory.build_client()` reads it internally; orchestrator does not. |
| T-01-09-04 | S (Spoofing — wrong snapshot timing claim) | "Tuesday 12pm ET" original D-02 claim | mitigate | HIGH-3 fix: labels renamed `prior_*` to honestly describe API semantics. PROJECT-PHASE0-FROZEN.md and 01-09-SUMMARY.md both document the rename rationale. Phase 4 contract updated. |
| T-01-09-05 | T (Tampering) | Plan 09 acceptance gating only on raw JSON | mitigate | HIGH-2 fix: Tasks 4 AND 5 both required; Task 5 acceptance gates on parquet existence + non-zero row count + schema match. Cannot pass Task 5 without Task 4 having produced the raw JSON. |
| T-01-09-06 | I (Information disclosure) | Parquet snapshot_label or market_key column leak | mitigate | Task 6 schema verification asserts label uniformity per file and column set match against the reference close_core8 parquet. |
</threat_model>

<verification>
- ALT_PROP_MARKETS tuple in source (Task 1 commit)
- Operator credit gate cleared (Task 2)
- 3 dry-run raw + 3 dry-run parquet files exist with proper labels and timestamps (Task 3 commit)
- 9 raw JSON cache trees populated (Task 4 commit)
- 9 processed parquet files built (Task 5 commit)
- Schema and timing verification passes (Task 6 commit)
- Existing close_core8 cache untouched throughout
- PROMOTION-NOTES contains all KS-21 sections (dry-run, raw scrape, processed build, schema verification)
- Plan 09 SUMMARY captures PROMOTED state with HIGH-2 / HIGH-3 fix rationale (Task 7 commit)
</verification>

<success_criteria>
- KS-21 sub-deliverable complete per ROADMAP success criterion #5 (relaxed coverage to 2023-2024 + 2025 per D-05)
- 9 new processed parquet caches at `~/.fantasy-sim/market-history/processed/`
- 9 new raw JSON cache trees at `~/.fantasy-sim/market-history/raw/props/`
- Per-season raw-count, parquet-row-count, and credit-balance logs preserved in PROMOTION-NOTES
- ALT_PROP_MARKETS tuple available for Phase 4 OddsApiCdfLoader consumer
- Existing main-line cache (`*_close_core8.parquet`) unchanged
- Remaining credit balance ≥ 3.0M for downstream Phase 4 work
- Snapshot labels use `prior_*` prefix (HIGH-3 honesty fix)
- Both raw fetch and processed build steps explicitly invoked (HIGH-2 pipeline fix)
</success_criteria>

<output>
After completion, the SUMMARY at `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-09-SUMMARY.md` is the canonical Plan 09 closure document.
</output>

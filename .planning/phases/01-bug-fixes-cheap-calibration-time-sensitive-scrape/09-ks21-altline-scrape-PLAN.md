---
phase: 01-bug-fixes-cheap-calibration-time-sensitive-scrape
plan: 09
type: execute
wave: 1
depends_on: []
files_modified:
  - src/fantasy_sim/data/market_history/props_backfill.py
autonomous: false
requirements: [KS-21]
user_setup:
  - service: the-odds-api
    why: "KS-21 sub-deliverable: alt-line + open-snapshot scrape consumes The Odds API historical credits"
    env_vars:
      - name: THE_ODDS_API_KEY
        source: "~/.fantasy-sim/market-history/.env (already set; do not read this file directly per AGENTS.md project guidance)"
    dashboard_config:
      - task: "Verify ~4.93M of 5M-credit tier remaining before scrape (~2 weeks tier window per PROJECT.md)"
        location: "https://the-odds-api.com (account dashboard)"
must_haves:
  truths:
    - "Per D-04: ALT_PROP_MARKETS tuple contains the 6 alternate-line markets: player_pass_yds_alternate, player_reception_yds_alternate, player_rush_yds_alternate, player_pass_attempts_alternate, player_receptions_alternate, player_rush_attempts_alternate"
    - "Per D-06: three new snapshot caches written for 2023, 2024, 2025: open_core8, open_alt6, close_alt6 — under ~/.fantasy-sim/market-history/processed/"
    - "Per D-07: parquet schema reuses existing player_markets_*; one row per (player, market_key, line) tuple — no list-typed columns"
    - "Per D-08: scrape uses scripts/fetch_market_history_props.py with new --markets and --snapshot-label values; no new scrape script"
    - "Per D-01: scrape regions=us (DraftKings + FanDuel + Caesars consensus); 3-book pricing per row"
    - "Per D-02: open snapshot timing = Tuesday 12pm ET (line release), implemented via --date-source previous_snapshot_timestamp + UTC conversion in build_snapshot_timestamp"
    - "Per D-03: scrape scope = open + close snapshots for all 14 markets (8 main-line + 6 alt-line); existing close_core8 cache untouched"
    - "Per D-05: coverage = 2023, 2024, 2025 regular seasons (Odds API has no historical pre-2023; ROADMAP success criterion #5 relaxed)"
  artifacts:
    - path: "src/fantasy_sim/data/market_history/props_backfill.py"
      provides: "ALT_PROP_MARKETS tuple alongside existing DEFAULT_PROP_MARKETS"
      contains: "ALT_PROP_MARKETS:"
    - path: "~/.fantasy-sim/market-history/processed/player_markets_2023_open_core8.parquet"
      provides: "Open snapshot for 8 main-line markets, 2023 season"
    - path: "~/.fantasy-sim/market-history/processed/player_markets_2024_open_core8.parquet"
      provides: "Open snapshot for 8 main-line markets, 2024 season"
    - path: "~/.fantasy-sim/market-history/processed/player_markets_2025_open_core8.parquet"
      provides: "Open snapshot for 8 main-line markets, 2025 season"
    - path: "~/.fantasy-sim/market-history/processed/player_markets_2023_open_alt6.parquet"
      provides: "Open snapshot for 6 alt-line markets, 2023 season"
    - path: "~/.fantasy-sim/market-history/processed/player_markets_2024_open_alt6.parquet"
      provides: "Open snapshot for 6 alt-line markets, 2024 season"
    - path: "~/.fantasy-sim/market-history/processed/player_markets_2025_open_alt6.parquet"
      provides: "Open snapshot for 6 alt-line markets, 2025 season"
    - path: "~/.fantasy-sim/market-history/processed/player_markets_2023_close_alt6.parquet"
      provides: "Close snapshot for 6 alt-line markets, 2023 season"
    - path: "~/.fantasy-sim/market-history/processed/player_markets_2024_close_alt6.parquet"
      provides: "Close snapshot for 6 alt-line markets, 2024 season"
    - path: "~/.fantasy-sim/market-history/processed/player_markets_2025_close_alt6.parquet"
      provides: "Close snapshot for 6 alt-line markets, 2025 season"
  key_links:
    - from: "scripts/fetch_market_history_props.py CLI"
      to: "props_backfill.ALT_PROP_MARKETS"
      via: "--markets $(python -c \"from fantasy_sim.data.market_history.props_backfill import ALT_PROP_MARKETS; print(' '.join(ALT_PROP_MARKETS))\")"
      pattern: "ALT_PROP_MARKETS"
---

<objective>
Implement KS-21 sub-deliverable — execute The Odds API historical scrape for the 6 alternate-line markets (D-04) plus the open-line snapshot for the existing 8 main markets (D-03), across 2023, 2024, 2025 regular seasons (D-05) using the existing `scripts/fetch_market_history_props.py` infrastructure (D-08). This adds 9 new parquet caches under `~/.fantasy-sim/market-history/processed/` without modifying the existing `close_core8` cache.

Purpose: KS-21 the *requirement* (engine integration) is mapped to Phase 4. KS-21 the *scrape sub-deliverable* runs in Phase 1 because the high-credit Odds API tier (~4.93M of 5M remaining, ~2 weeks window per PROJECT.md) is time-sensitive. Phase 4's `OddsApiCdfLoader` consumer needs this data ready when it ships.

Output: 9 new parquet files (3 seasons × 3 snapshot labels: `open_core8`, `open_alt6`, `close_alt6`); ALT_PROP_MARKETS tuple in source code; per-season row-count log entries; remaining-credit balance verified.

**checkpoint:human-action gate before scrape execution** — operator must confirm credit balance > 4.0M before the scrape kicks off (Task 2). Plan is `autonomous: false` for this reason.
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
@src/fantasy_sim/data/market_history/props_backfill.py
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

From scripts/fetch_market_history_props.py CLI:
- `--season` (int, nargs+, required)
- `--markets` (default: list(DEFAULT_PROP_MARKETS))
- `--regions` (default: us)
- `--snapshot-label` (default: close_core8)
- `--date-source` ∈ {commence_time, snapshot_date, previous_snapshot_timestamp, next_snapshot_timestamp} (default: commence_time)
- `--offset-minutes` (int, default: 0)
- `--delay` (float, default: DEFAULT_DELAY_SECONDS)
- `--limit` (int, default: None)
- `--force` (action store_true)
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
    - `grep -c "player_reception_yds_alternate" src/fantasy_sim/data/market_history/props_backfill.py` returns 1
    - `grep -c "player_rush_yds_alternate" src/fantasy_sim/data/market_history/props_backfill.py` returns 1
    - `grep -c "player_pass_attempts_alternate" src/fantasy_sim/data/market_history/props_backfill.py` returns 1
    - `grep -c "player_receptions_alternate" src/fantasy_sim/data/market_history/props_backfill.py` returns 1
    - `grep -c "player_rush_attempts_alternate" src/fantasy_sim/data/market_history/props_backfill.py` returns 1
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
  <name>Task 3: Dry-run one season-week to validate snapshot timing and credit usage</name>
  <files>(no source modifications — runs scripts/fetch_market_history_props.py with --limit 1)</files>
  <read_first>
    - scripts/fetch_market_history_props.py (CLI)
    - src/fantasy_sim/data/market_history/props_backfill.py (post-Task 1, with ALT_PROP_MARKETS)
    - src/fantasy_sim/data/market_history/events_inventory.py (build_client + DEFAULT_DELAY_SECONDS)
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-CONTEXT.md (D-02 Tuesday 12pm ET, D-06 snapshot labels, D-08 reuse infra)
  </read_first>
  <action>
Run a single-event dry run for 2024 with `--limit 1` to validate the snapshot timing logic and inspect the response headers (`x-requests-remaining`):

```bash
# Dry run: open_core8 for 2024, single event
ALT="player_pass_yds_alternate player_reception_yds_alternate player_rush_yds_alternate player_pass_attempts_alternate player_receptions_alternate player_rush_attempts_alternate"
CORE="player_pass_attempts player_pass_yds player_pass_tds player_rush_attempts player_rush_yds player_receptions player_reception_yds player_anytime_td"

# 1. Dry-run open_core8 (1 event)
uv run python scripts/fetch_market_history_props.py \
  --season 2024 \
  --markets $CORE \
  --regions us \
  --snapshot-label open_core8 \
  --date-source previous_snapshot_timestamp \
  --offset-minutes 0 \
  --limit 1 \
  2>&1 | tee .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/dry_run_open_core8.log

# Inspect output for x-requests-remaining and row count
grep -E "x-requests-remaining|requests-remaining|rows|saved" \
  .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/dry_run_open_core8.log

# 2. Dry-run open_alt6 (1 event)
uv run python scripts/fetch_market_history_props.py \
  --season 2024 \
  --markets $ALT \
  --regions us \
  --snapshot-label open_alt6 \
  --date-source previous_snapshot_timestamp \
  --offset-minutes 0 \
  --limit 1 \
  2>&1 | tee .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/dry_run_open_alt6.log

# 3. Dry-run close_alt6 (1 event)
uv run python scripts/fetch_market_history_props.py \
  --season 2024 \
  --markets $ALT \
  --regions us \
  --snapshot-label close_alt6 \
  --date-source commence_time \
  --offset-minutes -60 \
  --limit 1 \
  2>&1 | tee .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/dry_run_close_alt6.log
```

Inspect the dry-run outputs:
- The 3 dry-run runs together should consume on the order of 100-300 credits (3 events × markets × books × snapshots; varies by API pricing).
- Verify each run produced a parquet file at `~/.fantasy-sim/market-history/processed/player_markets_2024_<label>.parquet`. The file may have only a few rows from --limit 1.
- Verify the `snapshot_label` column in the parquet matches the new label.

Append to `.../logs/PROMOTION-NOTES.md` under `## KS-21 dry-run`:
- The 3 snapshot labels' parquet paths and row counts
- Estimated full-scrape credit cost (extrapolated from --limit 1)
- Decision: proceed to full scrape (Task 4) or abort

Commit: `chore(01-09): KS-21 dry-run logs (open_core8, open_alt6, close_alt6 × 1 event 2024)`
  </action>
  <verify>
    <automated>ls ~/.fantasy-sim/market-history/processed/player_markets_2024_open_core8.parquet ~/.fantasy-sim/market-history/processed/player_markets_2024_open_alt6.parquet ~/.fantasy-sim/market-history/processed/player_markets_2024_close_alt6.parquet 2>&1</automated>
  </verify>
  <acceptance_criteria>
    - The verify command shows all 3 parquet files exist (or returns 0 if any missing — investigate)
    - 3 dry-run log files exist under `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/`
    - PROMOTION-NOTES.md contains a section `## KS-21 dry-run` with row counts and credit-cost estimate
    - Per-season full-scrape credit estimate is documented (extrapolated from dry-run)
    - Decision to proceed to Task 4 (or abort) is recorded
    - `git log -1 --pretty=%s` matches `chore(01-09): KS-21 dry-run`
  </acceptance_criteria>
  <done>Dry-run validated; 3 snapshot labels write to parquet; full-scrape credit estimate documented.</done>
</task>

<task type="auto">
  <name>Task 4: Execute full scrape — 3 seasons × 3 snapshot labels = 9 parquet outputs</name>
  <files>(no source modifications — runs scripts/fetch_market_history_props.py for full seasons)</files>
  <read_first>
    - scripts/fetch_market_history_props.py
    - src/fantasy_sim/data/market_history/props_backfill.py (post-Task 1)
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/PROMOTION-NOTES.md (Task 3 dry-run estimate)
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-CONTEXT.md (D-05 coverage, D-06 labels)
  </read_first>
  <action>
Execute the full scrape — 3 seasons × 3 snapshot labels = 9 runs. Front-load `open_core8` (smallest add) per RESEARCH.md Pitfall 6 strategy.

```bash
ALT="player_pass_yds_alternate player_reception_yds_alternate player_rush_yds_alternate player_pass_attempts_alternate player_receptions_alternate player_rush_attempts_alternate"
CORE="player_pass_attempts player_pass_yds player_pass_tds player_rush_attempts player_rush_yds player_receptions player_reception_yds player_anytime_td"

# === Phase 1: open_core8 (smallest — 8 markets × 1 snapshot × 3 seasons) ===
for season in 2023 2024 2025; do
  echo "=== open_core8 ${season} ===" >&2
  uv run python scripts/fetch_market_history_props.py \
    --season $season \
    --markets $CORE \
    --regions us \
    --snapshot-label open_core8 \
    --date-source previous_snapshot_timestamp \
    --offset-minutes 0 \
    2>&1 | tee ".planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/scrape_${season}_open_core8.log"
  echo "--- open_core8 ${season} complete; remaining credits:" >&2
  grep "x-requests-remaining" ".planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/scrape_${season}_open_core8.log" | tail -1
done

# === Phase 2: open_alt6 (6 markets × 1 snapshot × 3 seasons) ===
for season in 2023 2024 2025; do
  echo "=== open_alt6 ${season} ===" >&2
  uv run python scripts/fetch_market_history_props.py \
    --season $season \
    --markets $ALT \
    --regions us \
    --snapshot-label open_alt6 \
    --date-source previous_snapshot_timestamp \
    --offset-minutes 0 \
    2>&1 | tee ".planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/scrape_${season}_open_alt6.log"
  echo "--- open_alt6 ${season} complete; remaining credits:" >&2
  grep "x-requests-remaining" ".planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/scrape_${season}_open_alt6.log" | tail -1
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
    2>&1 | tee ".planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/scrape_${season}_close_alt6.log"
  echo "--- close_alt6 ${season} complete; remaining credits:" >&2
  grep "x-requests-remaining" ".planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/scrape_${season}_close_alt6.log" | tail -1
done

# Verify all 9 outputs
ls -la ~/.fantasy-sim/market-history/processed/player_markets_*_open_core8.parquet \
       ~/.fantasy-sim/market-history/processed/player_markets_*_open_alt6.parquet \
       ~/.fantasy-sim/market-history/processed/player_markets_*_close_alt6.parquet
```

Append a per-season row-count + credit-balance log to `.../logs/PROMOTION-NOTES.md` under `## KS-21 full scrape`:

```markdown
## KS-21 full scrape

| Season | Snapshot | Rows | Credits before | Credits after | Δ |
|--------|----------|------|---------------|---------------|---|
| 2023 | open_core8 | ... | ... | ... | ... |
| 2024 | open_core8 | ... | ... | ... | ... |
| 2025 | open_core8 | ... | ... | ... | ... |
| 2023 | open_alt6  | ... | ... | ... | ... |
| 2024 | open_alt6  | ... | ... | ... | ... |
| 2025 | open_alt6  | ... | ... | ... | ... |
| 2023 | close_alt6 | ... | ... | ... | ... |
| 2024 | close_alt6 | ... | ... | ... | ... |
| 2025 | close_alt6 | ... | ... | ... | ... |
```

Commit: `chore(01-09): KS-21 full scrape — 9 parquet caches (open_core8, open_alt6, close_alt6 × 2023, 2024, 2025)`
  </action>
  <verify>
    <automated>ls ~/.fantasy-sim/market-history/processed/player_markets_2023_open_core8.parquet ~/.fantasy-sim/market-history/processed/player_markets_2024_open_core8.parquet ~/.fantasy-sim/market-history/processed/player_markets_2025_open_core8.parquet ~/.fantasy-sim/market-history/processed/player_markets_2023_open_alt6.parquet ~/.fantasy-sim/market-history/processed/player_markets_2024_open_alt6.parquet ~/.fantasy-sim/market-history/processed/player_markets_2025_open_alt6.parquet ~/.fantasy-sim/market-history/processed/player_markets_2023_close_alt6.parquet ~/.fantasy-sim/market-history/processed/player_markets_2024_close_alt6.parquet ~/.fantasy-sim/market-history/processed/player_markets_2025_close_alt6.parquet 2>&1 | wc -l | tr -d ' '</automated>
  </verify>
  <acceptance_criteria>
    - The verify command returns `9` (all 9 parquet files exist)
    - The existing `~/.fantasy-sim/market-history/processed/player_markets_*_close_core8.parquet` files are UNCHANGED (D-06: existing main-line cache untouched) — verify with `find ~/.fantasy-sim/market-history/processed -name "player_markets_*_close_core8.parquet" -newer .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-CONTEXT.md` returns 0 hits (none modified after CONTEXT was written)
    - PROMOTION-NOTES.md contains the per-season row-count + credit table under `## KS-21 full scrape`
    - Final remaining credit balance is documented in PROMOTION-NOTES (must be > 0; ideally > 3.5M)
    - Each new parquet file has > 0 rows (sanity check via `python -c "import polars as pl; print(pl.read_parquet('~/.fantasy-sim/market-history/processed/player_markets_2024_open_core8.parquet').height)"`)
    - `git log -1 --pretty=%s` matches `chore(01-09): KS-21 full scrape`
  </acceptance_criteria>
  <done>9 parquet caches written; existing cache untouched; credit balance documented; PROMOTION-NOTES updated.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| The Odds API → local cache | External HTTP boundary. Already gated by httpx + API key in `~/.fantasy-sim/market-history/.env` (per AGENTS.md, never read this file directly). |
| Local cache → downstream Phase 4 engine | Internal — same project. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-01-09-01 | D (Denial of service via credit exhaustion) | The Odds API credit budget | mitigate | Task 2 operator gate confirms ≥ 4.0M before scrape; Task 3 dry-run extrapolates full cost; per-season logging (Task 4) catches budget burn early. |
| T-01-09-02 | T (Tampering) | Existing close_core8 parquet cache | mitigate | D-06: new snapshots use distinct labels; verify command in Task 4 acceptance asserts close_core8 files unchanged. |
| T-01-09-03 | I (Information disclosure) | API key in `~/.fantasy-sim/market-history/.env` | accept | Per AGENTS.md project guidance: never read this file directly. The `events_inventory.build_client()` reads it internally; orchestrator does not. |
| T-01-09-04 | S (Spoofing — wrong snapshot timing) | Tuesday 12pm ET = previous_snapshot_timestamp | mitigate | Task 3 dry-run inspects the snapshot_timestamp column in the parquet; operator verifies before Task 4. DST transitions handled by `build_snapshot_timestamp` UTC conversion. |
</threat_model>

<verification>
- ALT_PROP_MARKETS tuple in source (Task 1 commit)
- Operator credit gate cleared (Task 2)
- 3 dry-run parquet files exist (Task 3 commit)
- 9 full-scrape parquet files exist (Task 4 commit)
- Existing close_core8 cache untouched
- PROMOTION-NOTES contains all KS-21 sections (dry-run, full scrape, credit balance)
</verification>

<success_criteria>
- KS-21 sub-deliverable complete per ROADMAP success criterion #5 (relaxed coverage to 2023-2024 + 2025 per D-05)
- 9 new parquet caches at `~/.fantasy-sim/market-history/processed/`
- Per-season row-count and credit-balance logs preserved
- ALT_PROP_MARKETS tuple available for Phase 4 OddsApiCdfLoader consumer
- Existing main-line cache (`*_close_core8.parquet`) unchanged
- Remaining credit balance ≥ 3.0M for downstream Phase 4 work
</success_criteria>

<output>
After completion, create `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-09-SUMMARY.md`.
</output>

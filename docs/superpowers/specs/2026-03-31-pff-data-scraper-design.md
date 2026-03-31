# PFF Data Scraper — Design Spec

**Date:** 2026-03-31
**Status:** Draft
**Scope:** Data extraction only (no sim integration)

## Problem

The simulator currently relies exclusively on nflverse play-by-play data. PFF premium data (player grades, yards after contact, pressure rates, depth of target, coverage scheme stats) would significantly enrich player modeling — but it's locked behind a premium subscription with no bulk export.

## Discovery

PFF's frontend renders tables client-side from a REST API. We identified the full API surface by inspecting network requests:

**Reference endpoints:**
- `GET /api/v1/teams?league=nfl&season={YYYY}` — team metadata
- `GET /api/v1/games?league=nfl&season={YYYY}&week={N}` — game list with `game_id`s
- `GET /api/v1/facet/{category}/{subfacet}?game_id={N}` — per-game player data (JSON)

**All 21 game-level facets:**

| Category | Sub-facets |
|----------|-----------|
| `offense` | `summary`, `blocking`, `pass_blocking`, `run_blocking` |
| `passing` | `summary`, `detail` |
| `rushing` | `summary`, `direction` |
| `receiving` | `summary`, `depth`, `coverage` |
| `defense` | `summary`, `run`, `pass_rush`, `coverage`, `coverage_matchup` |
| `special` | `summary` |
| `field_goal` | `summary` |
| `kickoff` | `summary` |
| `return` | `summary` |
| `punting` | `summary` |

Authentication is cookie-based (premium subscription session).

## Solution

A standalone Python script (`scripts/scrape_pff.py`) that:
1. Fetches game-level PFF data via the REST API
2. Stores raw JSON as an immutable archive
3. Processes raw JSON into per-facet-per-season parquet files

## CLI Interface

```bash
# Full season scrape (completed season)
uv run python scripts/scrape_pff.py --season 2024

# Specific weeks (mid-season or targeted re-scrape)
uv run python scripts/scrape_pff.py --season 2026 --weeks 1-8

# Single week (weekly update during season)
uv run python scripts/scrape_pff.py --season 2026 --weeks 12

# Re-generate parquet from existing raw JSON (no network)
uv run python scripts/scrape_pff.py --season 2024 --process-only

# Override rate limit delay (default 0.3s)
uv run python scripts/scrape_pff.py --season 2024 --delay 0.5
```

## Storage Layout

All data lives at `~/.fantasy-sim/pff/`, separate from the nflverse cache at `~/.fantasy-sim/cache/`.

```
~/.fantasy-sim/pff/
├── .env                          # PFF_COOKIE value (manual paste)
├── raw/                          # Immutable JSON archive
│   ├── teams/
│   │   └── {season}.json
│   ├── games/
│   │   └── {season}_week{NN}.json
│   └── facets/
│       └── {season}/
│           └── week_{NN}/
│               └── {game_id}_{category}_{subfacet}.json
├── processed/                    # Derived parquet files
│   └── {category}_{subfacet}_{season}.parquet
└── state/
    └── progress.json             # Resume tracking
```

### Raw JSON

One file per game per facet. Filenames encode `{game_id}_{category}_{subfacet}.json`, flat within each week directory. Files are never modified after creation — the raw API response is preserved exactly.

### Processed Parquet

One file per facet per season (21 files per season). Each row is one player in one game. Metadata columns injected during processing:
- `season` (int)
- `week` (int)
- `game_id` (int)
- `team` (str, resolved from `franchise_id` via teams JSON)

### Progress State

`progress.json` tracks which `(season, week, game_id, facet)` combos have been scraped. Enables resume after interruption without re-fetching.

```json
{
  "2024": {
    "week_01": {
      "28418": ["offense_summary", "passing_summary", "passing_detail", "..."],
      "28419": ["offense_summary", "passing_summary"]
    }
  }
}
```

## Authentication

Cookie-based, manually extracted from Chrome.

**Cookie file:** `~/.fantasy-sim/pff/.env`
```
PFF_COOKIE=your_cookie_value_here
```

**Script behavior on startup:**
1. Check for `.env` file — if missing, print setup instructions and exit
2. Validate cookie with a lightweight test request (`/api/v1/teams?league=nfl&season=2025`)
3. If validation fails (401/403), print message to refresh cookie and exit

Setup instructions are documented in `docs/pff-setup.md` and printed by `--help`.

## Scrape Workflow

For a given `--season` (and optional `--weeks`):

1. **Load cookie** from `~/.fantasy-sim/pff/.env`
2. **Validate cookie** with test request
3. **Fetch teams** for season → save to `raw/teams/{season}.json`
4. **Determine weeks** — if `--weeks` provided, use those; otherwise iterate weeks 1-22 (reg season + postseason) and keep any that return games from the games endpoint
5. **Fetch game list** for each week → save to `raw/games/{season}_week{NN}.json`
6. **For each game, for each of the 21 facets:**
   - Check `progress.json` — skip if already scraped
   - `GET /api/v1/facet/{category}/{subfacet}?game_id={game_id}`
   - Save raw JSON to `raw/facets/{season}/week_{NN}/{game_id}_{category}_{subfacet}.json`
   - Update `progress.json`
   - Wait `delay` seconds (default 0.3s)
7. **Process** all raw JSON for the season into parquet files
8. **Print summary** — games scraped, facets collected, failures

## Processing Pipeline

For each of the 21 facets:

1. Glob all matching JSON files: `raw/facets/{season}/week_*/*_{category}_{subfacet}.json`
2. Parse each file — API returns `{"{category}_{subfacet}": [player_rows...]}`
3. For each player row, inject: `season`, `week`, `game_id`, `team`
4. Concatenate into a single polars DataFrame
5. Write to `processed/{category}_{subfacet}_{season}.parquet`

The `--process-only` flag runs only this step (no network requests).

## Error Handling

| Status | Action |
|--------|--------|
| 200 | Save JSON, update progress |
| 401/403 | Stop immediately, tell user to refresh cookie |
| 404 | Skip and log (expected — some facets don't exist for every game) |
| 429 | Exponential backoff (1s, 2s, 4s), retry up to 3 times, then skip and log |
| Network error | Retry up to 3 times, then skip and log |
| Interruption (Ctrl+C) | Progress.json ensures next run resumes where it left off |

## Output During Run

Rich progress bars (using the `rich` library already in the project):
- Top-level: week progress (e.g., `Week 3/18`)
- Per-week: game progress (e.g., `Game 5/16`)
- Per-game: facet progress (e.g., `Facet 12/21`)
- Running totals: requests made, skipped (404), failures, elapsed time

## Dependencies

**New:**
- `httpx` — HTTP client for API requests

**Existing (no changes):**
- `polars` — parquet I/O and DataFrame processing
- `rich` — progress bars and terminal output
- `python-dotenv` or manual `.env` parsing — cookie loading

## File Changes

| File | Change |
|------|--------|
| `scripts/scrape_pff.py` | New — the scraper script |
| `docs/pff-setup.md` | New — cookie setup instructions |
| `pyproject.toml` | Add `httpx` to dependencies |

## Volume Estimates

- 21 facets x ~267 games/season = ~5,607 API calls per season
- At 0.3s delay: ~28 minutes per season
- 4 seasons (2022-2025): ~112 minutes total for initial backfill
- Raw JSON: estimated ~200-500 MB per season (varies by facet response size)
- Processed parquet: estimated ~50-100 MB per season (compressed columnar)

## Future Integration (out of scope)

The processed parquet files are designed to be consumed by a future `PFFLoader` class in `src/fantasy_sim/data/`. Potential uses:
- Quality-weighted player distributions (PFF grades as confidence signals)
- Per-QB pressure rate / time-in-pocket for sack/INT modeling
- Yards-after-contact for rushing distribution enrichment
- Receiving depth-of-target for air yards modeling
- Defensive coverage grades for matchup adjustments

This is a separate design effort. The sim continues to work with nflverse data alone.

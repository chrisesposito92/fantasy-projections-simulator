# Handoff: PFF College Stats Scraper

## Context

We just built a PFF NFL data scraper (`scripts/scrape_pff.py`) on the `feat/pff-data-scraper` branch (PR #15). It extracts game-level player data from PFF's premium REST API, stores raw JSON at `~/.fantasy-sim/pff/raw/`, and processes into per-facet-per-season parquet at `~/.fantasy-sim/pff/processed/`.

## Goal

Extend the scraper to also pull **college (NCAA) data** from PFF. This gives us a college stats baseline since nflverse has zero college data. College data will be critical for rookie modeling — draft capital alone is a weak signal compared to actual college production + PFF grades.

## What We Know

From Chris's investigation, the PFF college endpoints are **identical** to NFL:

- Same API pattern: `premium.pff.com/api/v1/facet/{category}/{subfacet}?game_id={N}`
- Same 21 facets (offense, passing, rushing, receiving, defense, special teams, etc.)
- Same response structure (JSON with player rows, same `"restricted"` key for expired cookies)
- **Differences:**
  - College `game_id`s instead of NFL `game_id`s
  - Weeks 0-16 (not 1-18 like NFL)
  - Presumably `league=ncaa` (or similar) for the games/teams endpoints — needs verification

## Existing Scraper Architecture

The NFL scraper (`scripts/scrape_pff.py`) has these key components:

- **Constants:** `PFF_BASE_URL`, `PFF_DIR`, `ALL_FACETS` (21 facets), `MAX_WEEK = 22`
- **ProgressTracker:** Resumes interrupted scrapes via `progress.json`
- **fetch_json():** HTTP client with retry/backoff, `_NOT_FOUND` sentinel for 404, `AuthError` for 401/403
- **Cookie detection:** Checks for `"restricted"` key in API response (PFF returns 200 with degraded data when cookie expires instead of 401)
- **scrape_season():** Iterates weeks → games → facets, Rich progress bars
- **process_season():** Raw JSON → parquet with metadata columns (season, week, game_id, team)
- **_extract_player_rows():** Handles both flat lists and nested dicts (coverage matchups)
- **CLI:** `--season`, `--weeks`, `--process-only`, `--delay`

## Design Decision: Extend vs Separate Script

Two approaches:

**A) Extend existing script** — Add a `--league` flag (`nfl` default, `ncaa` option). Adjust `MAX_WEEK`, games endpoint, and storage paths (`~/.fantasy-sim/pff/raw/ncaa/` vs `~/.fantasy-sim/pff/raw/nfl/`). Most code is shared.

**B) Separate script** — `scripts/scrape_pff_college.py`. Duplicates some code but keeps concerns clean.

**Recommendation: A** — The scraping logic is identical. The only differences are the league parameter, week range, and storage subdirectory. A `--league` flag keeps it DRY.

## Storage Layout Change

Current:
```
~/.fantasy-sim/pff/
├── raw/facets/{season}/week_{NN}/{game_id}_{facet}.json
├── processed/{facet}_{season}.parquet
```

Proposed (add league subdirectory):
```
~/.fantasy-sim/pff/
├── raw/nfl/facets/{season}/week_{NN}/{game_id}_{facet}.json
├── raw/ncaa/facets/{season}/week_{NN}/{game_id}_{facet}.json
├── processed/nfl/{facet}_{season}.parquet
├── processed/ncaa/{facet}_{season}.parquet
```

**Migration needed** for existing NFL data (move files into `nfl/` subdirectory).

## Things to Verify in Chrome

Before coding, confirm in Chrome DevTools:
1. The exact `league` parameter for college: `ncaa`? `college`? `cfb`?
2. The teams endpoint: `GET /api/v1/teams?league={???}&season=2024`
3. The games endpoint: `GET /api/v1/games?league={???}&season=2024&week=1`
4. That the facet endpoints work with college game_ids
5. Week range (Chris says 0-16)

## Existing Issues / Learnings from NFL Scraper

These are already handled but worth noting:
- API response keys don't match facet naming (e.g., `defense_coverage` → `coverage_summary`). Handled by `_extract_player_rows()`.
- Coverage matchup facets have nested dict structure. Handled.
- PFF returns inconsistent types (int vs float). Handled via `infer_schema_length=None`.
- Some response lists contain non-dict items. Handled with `isinstance` guard.
- Cookie expires after ~1 hour. Detected via `"restricted"` key.
- Transient failures are NOT marked as done in progress tracker (retryable).

## Relevant Files

- `scripts/scrape_pff.py` — the scraper to extend
- `tests/test_scripts/test_scrape_pff.py` — 25 existing tests
- `docs/pff-setup.md` — cookie setup docs
- `docs/superpowers/specs/2026-03-31-pff-data-scraper-design.md` — original design spec
- `CLAUDE.md` — project docs (scraper section at bottom of Commands)

## Seasons to Scrape

For college, the most useful seasons would be recent ones that overlap with current NFL rookies:
- 2022, 2023, 2024 (covers players drafted 2023-2025)
- 2025 college season for upcoming 2026 draft class

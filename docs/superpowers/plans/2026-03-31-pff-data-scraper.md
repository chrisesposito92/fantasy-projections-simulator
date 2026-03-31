# PFF Data Scraper — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone Python script that extracts game-level player data from PFF's premium REST API, stores raw JSON as an immutable archive, and processes it into polars-queryable parquet files.

**Architecture:** A single script (`scripts/scrape_pff.py`) with three modules of logic: (1) an HTTP client that handles auth, rate limiting, retries, and error classification, (2) a scraper that iterates seasons/weeks/games/facets and manages progress state, and (3) a processor that normalizes raw JSON into per-facet-per-season parquet. A companion doc (`docs/pff-setup.md`) explains cookie extraction. The script uses `argparse` for CLI (matching existing scripts pattern — no Click dependency for a standalone script).

**Tech Stack:** Python 3.12+, httpx, polars, rich, argparse, json, pathlib

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `scripts/scrape_pff.py` | Create | Main script — CLI, HTTP client, scraper, processor |
| `docs/pff-setup.md` | Create | Cookie extraction instructions |
| `pyproject.toml` | Modify | Add `httpx` dependency |
| `tests/test_scripts/test_scrape_pff.py` | Create | Unit tests for parsing, progress, processing logic |

---

### Task 1: Add httpx Dependency

**Files:**
- Modify: `pyproject.toml:6-15`

- [ ] **Step 1: Add httpx to dependencies**

In `pyproject.toml`, add `httpx` to the `dependencies` list:

```toml
dependencies = [
    "nflreadpy>=0.1.0",
    "polars>=1.0.0",
    "numpy>=2.0.0",
    "scipy>=1.14.0",
    "pyyaml>=6.0",
    "click>=8.0",
    "rich>=13.0",
    "thefuzz>=0.22.0",
    "httpx>=0.27.0",
]
```

- [ ] **Step 2: Install updated dependencies**

Run: `uv pip install -e ".[dev]"`
Expected: Successfully installs httpx

- [ ] **Step 3: Verify httpx is importable**

Run: `uv run python -c "import httpx; print(httpx.__version__)"`
Expected: Prints version number (0.27.x or newer)

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add httpx dependency for PFF scraper"
```

---

### Task 2: Write Cookie Setup Documentation

**Files:**
- Create: `docs/pff-setup.md`

- [ ] **Step 1: Create the setup doc**

Create `docs/pff-setup.md`:

```markdown
# PFF Data Scraper — Setup

## Prerequisites

- Active PFF Premium subscription
- Google Chrome (for cookie extraction)

## Cookie Setup

The scraper authenticates using your PFF session cookie. You need to extract it from Chrome and save it to a config file.

### Step 1: Log into PFF

1. Open Chrome and navigate to https://premium.pff.com
2. Log in with your PFF Premium credentials

### Step 2: Extract the Cookie

1. Open Chrome DevTools (Cmd+Option+I on macOS, F12 on Windows)
2. Go to the **Network** tab
3. Click on any page within premium.pff.com (e.g., a game report)
4. In the Network tab, click on any request to `premium.pff.com`
5. In the request headers, find the `Cookie` header
6. Copy the **entire value** of the Cookie header

### Step 3: Save the Cookie

Create the file `~/.fantasy-sim/pff/.env` and paste the cookie value:

```
PFF_COOKIE=paste_your_cookie_value_here
```

To create the directory and file:

```bash
mkdir -p ~/.fantasy-sim/pff
echo "PFF_COOKIE=your_cookie_here" > ~/.fantasy-sim/pff/.env
```

Then open `~/.fantasy-sim/pff/.env` in your editor and replace `your_cookie_here` with the actual cookie value.

### Cookie Expiration

PFF session cookies expire periodically. If the scraper reports a 401/403 error, repeat the extraction steps above to get a fresh cookie.

## Usage

```bash
# Scrape a full season
uv run python scripts/scrape_pff.py --season 2024

# Scrape specific weeks (mid-season)
uv run python scripts/scrape_pff.py --season 2026 --weeks 1-8

# Scrape a single week
uv run python scripts/scrape_pff.py --season 2026 --weeks 12

# Re-process existing raw data into parquet (no network)
uv run python scripts/scrape_pff.py --season 2024 --process-only

# Custom rate limit delay (default 0.3s)
uv run python scripts/scrape_pff.py --season 2024 --delay 0.5
```
```

- [ ] **Step 2: Commit**

```bash
git add docs/pff-setup.md
git commit -m "docs: add PFF scraper cookie setup instructions"
```

---

### Task 3: Script Skeleton — CLI Parsing and Constants

**Files:**
- Create: `scripts/scrape_pff.py`

- [ ] **Step 1: Create the script with CLI parsing, constants, and directory setup**

Create `scripts/scrape_pff.py`:

```python
"""PFF Premium Data Scraper.

Extracts game-level player data from PFF's REST API, stores raw JSON,
and processes into parquet files for analysis.

Run: uv run python scripts/scrape_pff.py --season 2024
Setup: See docs/pff-setup.md for cookie extraction instructions.
"""

import argparse
import json
import sys
import time
from pathlib import Path

import httpx
import polars as pl
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PFF_BASE_URL = "https://premium.pff.com"
PFF_DIR = Path.home() / ".fantasy-sim" / "pff"
RAW_DIR = PFF_DIR / "raw"
PROCESSED_DIR = PFF_DIR / "processed"
STATE_DIR = PFF_DIR / "state"
ENV_FILE = PFF_DIR / ".env"
PROGRESS_FILE = STATE_DIR / "progress.json"

DEFAULT_DELAY = 0.3
MAX_RETRIES = 3
MAX_WEEK = 22  # reg season (1-18) + postseason (19-22)

ALL_FACETS: list[tuple[str, str]] = [
    ("offense", "summary"),
    ("offense", "blocking"),
    ("offense", "pass_blocking"),
    ("offense", "run_blocking"),
    ("passing", "summary"),
    ("passing", "detail"),
    ("rushing", "summary"),
    ("rushing", "direction"),
    ("receiving", "summary"),
    ("receiving", "depth"),
    ("receiving", "coverage"),
    ("defense", "summary"),
    ("defense", "run"),
    ("defense", "pass_rush"),
    ("defense", "coverage"),
    ("defense", "coverage_matchup"),
    ("special", "summary"),
    ("field_goal", "summary"),
    ("kickoff", "summary"),
    ("return", "summary"),
    ("punting", "summary"),
]

console = Console()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="PFF Premium Data Scraper",
        epilog="Setup: See docs/pff-setup.md for cookie extraction instructions.",
    )
    parser.add_argument("--season", type=int, required=True, help="NFL season year (e.g., 2024)")
    parser.add_argument("--weeks", type=str, default=None, help="Week range (e.g., '1-8' or '12')")
    parser.add_argument("--process-only", action="store_true", help="Re-process raw JSON to parquet without scraping")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY, help=f"Delay between API requests in seconds (default: {DEFAULT_DELAY})")
    return parser.parse_args()


def parse_weeks(weeks_str: str | None) -> list[int] | None:
    """Parse --weeks argument into a list of week numbers, or None for all."""
    if weeks_str is None:
        return None
    if "-" in weeks_str:
        start, end = weeks_str.split("-", 1)
        return list(range(int(start), int(end) + 1))
    return [int(weeks_str)]


def ensure_directories() -> None:
    """Create the PFF data directory structure."""
    for d in [RAW_DIR / "teams", RAW_DIR / "games", PROCESSED_DIR, STATE_DIR]:
        d.mkdir(parents=True, exist_ok=True)


if __name__ == "__main__":
    args = parse_args()
    weeks = parse_weeks(args.weeks)
    console.print(f"[bold]PFF Scraper[/bold] — Season {args.season}")
    if weeks:
        console.print(f"  Weeks: {weeks}")
    console.print(f"  Delay: {args.delay}s")
    ensure_directories()
```

- [ ] **Step 2: Verify the script runs and parses arguments**

Run: `uv run python scripts/scrape_pff.py --season 2024`
Expected: Prints "PFF Scraper — Season 2024" and "Delay: 0.3s"

Run: `uv run python scripts/scrape_pff.py --season 2026 --weeks 1-8`
Expected: Prints "Weeks: [1, 2, 3, 4, 5, 6, 7, 8]"

Run: `uv run python scripts/scrape_pff.py --help`
Expected: Shows help text including the setup instructions epilog

- [ ] **Step 3: Commit**

```bash
git add scripts/scrape_pff.py
git commit -m "feat: add PFF scraper skeleton with CLI parsing and constants"
```

---

### Task 4: Cookie Loading and Validation

**Files:**
- Modify: `scripts/scrape_pff.py`
- Create: `tests/test_scripts/test_scrape_pff.py`

- [ ] **Step 1: Write tests for cookie loading**

Create `tests/test_scripts/__init__.py` (empty) and `tests/test_scripts/test_scrape_pff.py`:

```python
"""Tests for PFF scraper utilities."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

import pytest
from unittest.mock import patch, MagicMock
from scrape_pff import parse_weeks, load_cookie


class TestParseWeeks:
    def test_none_returns_none(self):
        assert parse_weeks(None) is None

    def test_single_week(self):
        assert parse_weeks("12") == [12]

    def test_week_range(self):
        assert parse_weeks("1-8") == [1, 2, 3, 4, 5, 6, 7, 8]

    def test_single_digit_range(self):
        assert parse_weeks("3-5") == [3, 4, 5]


class TestLoadCookie:
    def test_loads_cookie_from_env_file(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("PFF_COOKIE=abc123xyz\n")
        cookie = load_cookie(env_file)
        assert cookie == "abc123xyz"

    def test_strips_whitespace_and_quotes(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text('PFF_COOKIE="abc123xyz"\n')
        cookie = load_cookie(env_file)
        assert cookie == "abc123xyz"

    def test_returns_none_if_file_missing(self, tmp_path):
        env_file = tmp_path / ".env"
        cookie = load_cookie(env_file)
        assert cookie is None

    def test_returns_none_if_key_missing(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("OTHER_KEY=value\n")
        cookie = load_cookie(env_file)
        assert cookie is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_scripts/test_scrape_pff.py -v`
Expected: FAIL — `load_cookie` not yet defined

- [ ] **Step 3: Implement load_cookie and validate_cookie**

Add to `scripts/scrape_pff.py`, after `ensure_directories()`:

```python
def load_cookie(env_path: Path = ENV_FILE) -> str | None:
    """Load PFF_COOKIE from .env file."""
    if not env_path.exists():
        return None
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line.startswith("PFF_COOKIE="):
            value = line[len("PFF_COOKIE="):]
            return value.strip().strip('"').strip("'")
    return None


def build_client(cookie: str) -> httpx.Client:
    """Create an httpx client with PFF auth headers."""
    return httpx.Client(
        base_url=PFF_BASE_URL,
        headers={
            "Cookie": cookie,
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "application/json",
            "Referer": f"{PFF_BASE_URL}/nfl/games",
        },
        timeout=30.0,
    )


def validate_cookie(client: httpx.Client, season: int) -> bool:
    """Validate the cookie by making a lightweight API request."""
    try:
        resp = client.get(f"/api/v1/teams?league=nfl&season={season}")
        if resp.status_code in (401, 403):
            return False
        resp.raise_for_status()
        return True
    except httpx.HTTPError:
        return False
```

- [ ] **Step 4: Wire cookie loading into main block**

Replace the `if __name__ == "__main__"` block with:

```python
def main() -> None:
    args = parse_args()
    weeks = parse_weeks(args.weeks)
    ensure_directories()

    console.print(f"\n[bold]PFF Scraper[/bold] — Season {args.season}")
    if weeks:
        console.print(f"  Weeks: {weeks}")
    console.print(f"  Delay: {args.delay}s\n")

    if args.process_only:
        console.print("[bold]Process-only mode[/bold] — skipping scrape\n")
        # Processing will be added in Task 7
        return

    # Load and validate cookie
    cookie = load_cookie()
    if cookie is None:
        console.print("[bold red]Error:[/bold red] No PFF cookie found.")
        console.print("Create ~/.fantasy-sim/pff/.env with your PFF_COOKIE.")
        console.print("See docs/pff-setup.md for instructions.")
        sys.exit(1)

    client = build_client(cookie)
    if not validate_cookie(client, args.season):
        console.print("[bold red]Error:[/bold red] PFF cookie is invalid or expired.")
        console.print("Refresh your cookie — see docs/pff-setup.md")
        client.close()
        sys.exit(1)

    console.print("[green]Cookie validated[/green]\n")
    client.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_scripts/test_scrape_pff.py -v`
Expected: All 6 tests PASS

- [ ] **Step 6: Commit**

```bash
git add scripts/scrape_pff.py tests/test_scripts/__init__.py tests/test_scripts/test_scrape_pff.py
git commit -m "feat: add cookie loading and validation for PFF scraper"
```

---

### Task 5: Progress State Management

**Files:**
- Modify: `scripts/scrape_pff.py`
- Modify: `tests/test_scripts/test_scrape_pff.py`

- [ ] **Step 1: Write tests for progress tracking**

Add to `tests/test_scripts/test_scrape_pff.py`:

```python
from scrape_pff import ProgressTracker


class TestProgressTracker:
    def test_new_tracker_is_empty(self, tmp_path):
        tracker = ProgressTracker(tmp_path / "progress.json")
        assert not tracker.is_done("2024", "week_01", "28418", "passing_summary")

    def test_mark_done_and_check(self, tmp_path):
        tracker = ProgressTracker(tmp_path / "progress.json")
        tracker.mark_done("2024", "week_01", "28418", "passing_summary")
        assert tracker.is_done("2024", "week_01", "28418", "passing_summary")
        assert not tracker.is_done("2024", "week_01", "28418", "rushing_summary")

    def test_persists_to_disk(self, tmp_path):
        path = tmp_path / "progress.json"
        tracker = ProgressTracker(path)
        tracker.mark_done("2024", "week_01", "28418", "passing_summary")
        tracker.save()

        tracker2 = ProgressTracker(path)
        assert tracker2.is_done("2024", "week_01", "28418", "passing_summary")

    def test_multiple_facets_per_game(self, tmp_path):
        tracker = ProgressTracker(tmp_path / "progress.json")
        tracker.mark_done("2024", "week_01", "28418", "passing_summary")
        tracker.mark_done("2024", "week_01", "28418", "rushing_summary")
        assert tracker.is_done("2024", "week_01", "28418", "passing_summary")
        assert tracker.is_done("2024", "week_01", "28418", "rushing_summary")
        assert not tracker.is_done("2024", "week_01", "28418", "defense_summary")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_scripts/test_scrape_pff.py::TestProgressTracker -v`
Expected: FAIL — `ProgressTracker` not yet defined

- [ ] **Step 3: Implement ProgressTracker**

Add to `scripts/scrape_pff.py`, after the constants:

```python
class ProgressTracker:
    """Tracks which (season, week, game, facet) combos have been scraped."""

    def __init__(self, path: Path = PROGRESS_FILE):
        self.path = path
        self.data: dict = {}
        if path.exists():
            self.data = json.loads(path.read_text())

    def is_done(self, season: str, week: str, game_id: str, facet: str) -> bool:
        return facet in self.data.get(season, {}).get(week, {}).get(game_id, [])

    def mark_done(self, season: str, week: str, game_id: str, facet: str) -> None:
        self.data.setdefault(season, {}).setdefault(week, {}).setdefault(game_id, [])
        if facet not in self.data[season][week][game_id]:
            self.data[season][week][game_id].append(facet)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_scripts/test_scrape_pff.py::TestProgressTracker -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/scrape_pff.py tests/test_scripts/test_scrape_pff.py
git commit -m "feat: add progress tracker for PFF scraper resume support"
```

---

### Task 6: HTTP Client with Retries and Rate Limiting

**Files:**
- Modify: `scripts/scrape_pff.py`
- Modify: `tests/test_scripts/test_scrape_pff.py`

- [ ] **Step 1: Write tests for the fetch function**

Add to `tests/test_scripts/test_scrape_pff.py`:

```python
from scrape_pff import fetch_json, AuthError


class TestFetchJson:
    def test_successful_fetch(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [1, 2, 3]}
        mock_client = MagicMock()
        mock_client.get.return_value = mock_response

        result = fetch_json(mock_client, "/api/v1/test", delay=0)
        assert result == {"data": [1, 2, 3]}

    def test_404_returns_none(self):
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_client = MagicMock()
        mock_client.get.return_value = mock_response

        result = fetch_json(mock_client, "/api/v1/test", delay=0)
        assert result is None

    def test_401_raises_auth_error(self):
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_client = MagicMock()
        mock_client.get.return_value = mock_response

        with pytest.raises(AuthError):
            fetch_json(mock_client, "/api/v1/test", delay=0)

    def test_403_raises_auth_error(self):
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_client = MagicMock()
        mock_client.get.return_value = mock_response

        with pytest.raises(AuthError):
            fetch_json(mock_client, "/api/v1/test", delay=0)

    def test_429_retries(self):
        resp_429 = MagicMock()
        resp_429.status_code = 429
        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.json.return_value = {"ok": True}
        mock_client = MagicMock()
        mock_client.get.side_effect = [resp_429, resp_200]

        result = fetch_json(mock_client, "/api/v1/test", delay=0)
        assert result == {"ok": True}
        assert mock_client.get.call_count == 2

    def test_network_error_retries(self):
        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.json.return_value = {"ok": True}
        mock_client = MagicMock()
        mock_client.get.side_effect = [httpx.ConnectError("fail"), resp_200]

        result = fetch_json(mock_client, "/api/v1/test", delay=0)
        assert result == {"ok": True}

    def test_exhausted_retries_returns_none(self):
        mock_client = MagicMock()
        mock_client.get.side_effect = httpx.ConnectError("fail")

        result = fetch_json(mock_client, "/api/v1/test", delay=0, max_retries=2)
        assert result is None
        assert mock_client.get.call_count == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_scripts/test_scrape_pff.py::TestFetchJson -v`
Expected: FAIL — `fetch_json` and `AuthError` not defined

- [ ] **Step 3: Implement fetch_json and AuthError**

Add to `scripts/scrape_pff.py`, after `ProgressTracker`:

```python
class AuthError(Exception):
    """Raised when PFF returns 401/403 — cookie is invalid or expired."""
    pass


def fetch_json(
    client: httpx.Client,
    path: str,
    delay: float = DEFAULT_DELAY,
    max_retries: int = MAX_RETRIES,
) -> dict | None:
    """Fetch JSON from PFF API with retry logic.

    Returns None for 404 (expected) or exhausted retries.
    Raises AuthError for 401/403.
    """
    for attempt in range(max_retries):
        try:
            resp = client.get(path)

            if resp.status_code in (401, 403):
                raise AuthError(f"Authentication failed: {resp.status_code}")

            if resp.status_code == 404:
                return None

            if resp.status_code == 429:
                backoff = 2 ** attempt
                time.sleep(backoff)
                continue

            resp.raise_for_status()
            time.sleep(delay)
            return resp.json()

        except httpx.HTTPError as e:
            if isinstance(e, httpx.HTTPStatusError) and e.response.status_code in (401, 403):
                raise AuthError(f"Authentication failed: {e.response.status_code}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            return None

    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_scripts/test_scrape_pff.py::TestFetchJson -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/scrape_pff.py tests/test_scripts/test_scrape_pff.py
git commit -m "feat: add PFF API fetch with retries, backoff, and auth error handling"
```

---

### Task 7: Core Scrape Loop

**Files:**
- Modify: `scripts/scrape_pff.py`

- [ ] **Step 1: Implement the scrape functions**

Add to `scripts/scrape_pff.py`, after `fetch_json`:

```python
def fetch_teams(client: httpx.Client, season: int, delay: float) -> dict:
    """Fetch and cache team metadata for a season."""
    cache_path = RAW_DIR / "teams" / f"{season}.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text())
    data = fetch_json(client, f"/api/v1/teams?league=nfl&season={season}", delay=delay)
    if data is None:
        console.print(f"[bold red]Error:[/bold red] Could not fetch teams for {season}")
        sys.exit(1)
    cache_path.write_text(json.dumps(data, indent=2))
    return data


def fetch_games_for_week(client: httpx.Client, season: int, week: int, delay: float) -> list[dict]:
    """Fetch game list for a specific week. Returns empty list if no games."""
    cache_path = RAW_DIR / "games" / f"{season}_week{week:02d}.json"
    if cache_path.exists():
        data = json.loads(cache_path.read_text())
    else:
        data = fetch_json(client, f"/api/v1/games?league=nfl&season={season}&week={week}", delay=delay)
        if data is None:
            return []
        cache_path.write_text(json.dumps(data, indent=2))
    return data.get("games", [])


def discover_weeks(client: httpx.Client, season: int, delay: float) -> list[int]:
    """Find all weeks that have games for a season."""
    weeks_with_games = []
    for week in range(1, MAX_WEEK + 1):
        games = fetch_games_for_week(client, season, week, delay)
        if games:
            weeks_with_games.append(week)
    return weeks_with_games


def scrape_season(
    client: httpx.Client,
    season: int,
    weeks: list[int] | None,
    delay: float,
) -> dict:
    """Scrape all facets for all games in the given season/weeks.

    Returns stats dict with counts of requests, skips, failures.
    """
    stats = {"requests": 0, "skipped_done": 0, "skipped_404": 0, "failures": 0}
    tracker = ProgressTracker()
    season_str = str(season)

    # Fetch teams
    console.print("Fetching teams...")
    fetch_teams(client, season, delay)

    # Determine weeks
    if weeks is None:
        console.print("Discovering weeks with games...")
        weeks = discover_weeks(client, season, delay)
    console.print(f"Weeks to scrape: {weeks}\n")

    if not weeks:
        console.print("[yellow]No weeks found with games.[/yellow]")
        return stats

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        week_task = progress.add_task("Weeks", total=len(weeks))

        for week in weeks:
            week_str = f"week_{week:02d}"
            progress.update(week_task, description=f"Week {week}")

            games = fetch_games_for_week(client, season, week, delay)
            if not games:
                progress.advance(week_task)
                continue

            # Ensure week directory exists
            week_dir = RAW_DIR / "facets" / str(season) / week_str
            week_dir.mkdir(parents=True, exist_ok=True)

            game_task = progress.add_task(f"  Games (wk {week})", total=len(games))

            for game in games:
                game_id = game["id"]
                game_id_str = str(game_id)

                facet_task = progress.add_task(f"    Facets (g{game_id})", total=len(ALL_FACETS))

                for category, subfacet in ALL_FACETS:
                    facet_key = f"{category}_{subfacet}"

                    if tracker.is_done(season_str, week_str, game_id_str, facet_key):
                        stats["skipped_done"] += 1
                        progress.advance(facet_task)
                        continue

                    try:
                        data = fetch_json(
                            client,
                            f"/api/v1/facet/{category}/{subfacet}?game_id={game_id}",
                            delay=delay,
                        )
                    except AuthError:
                        console.print("\n[bold red]Auth error — cookie expired. Stopping.[/bold red]")
                        console.print("Refresh your cookie — see docs/pff-setup.md")
                        tracker.save()
                        sys.exit(1)

                    if data is None:
                        stats["skipped_404"] += 1
                    else:
                        out_path = week_dir / f"{game_id}_{facet_key}.json"
                        out_path.write_text(json.dumps(data, indent=2))
                        stats["requests"] += 1

                    tracker.mark_done(season_str, week_str, game_id_str, facet_key)
                    progress.advance(facet_task)

                # Save progress after each game
                tracker.save()
                progress.remove_task(facet_task)
                progress.advance(game_task)

            progress.remove_task(game_task)
            progress.advance(week_task)

    tracker.save()
    return stats
```

- [ ] **Step 2: Wire scrape_season into main()**

In `main()`, replace the `console.print("[green]Cookie validated[/green]\n")` and `client.close()` lines with:

```python
    console.print("[green]Cookie validated[/green]\n")

    try:
        stats = scrape_season(client, args.season, weeks, args.delay)
        console.print(f"\n[bold]Scrape complete:[/bold]")
        console.print(f"  Requests made: {stats['requests']}")
        console.print(f"  Skipped (already done): {stats['skipped_done']}")
        console.print(f"  Skipped (404): {stats['skipped_404']}")
        console.print(f"  Failures: {stats['failures']}")

        # Processing will be added in Task 8
        console.print(f"\n[bold]Processing raw data...[/bold]")
    finally:
        client.close()
```

- [ ] **Step 3: Verify the script structure is correct**

Run: `uv run python scripts/scrape_pff.py --help`
Expected: Shows help text without errors

- [ ] **Step 4: Commit**

```bash
git add scripts/scrape_pff.py
git commit -m "feat: implement core PFF scrape loop with progress tracking"
```

---

### Task 8: Processing Pipeline (Raw JSON → Parquet)

**Files:**
- Modify: `scripts/scrape_pff.py`
- Modify: `tests/test_scripts/test_scrape_pff.py`

- [ ] **Step 1: Write tests for the processing pipeline**

Add to `tests/test_scripts/test_scrape_pff.py`:

```python
from scrape_pff import process_season, build_team_lookup


class TestBuildTeamLookup:
    def test_builds_lookup_from_teams_json(self, tmp_path):
        teams_dir = tmp_path / "raw" / "teams"
        teams_dir.mkdir(parents=True)
        teams_data = {
            "teams": [
                {"franchise_id": 9, "abbreviation": "DAL"},
                {"franchise_id": 24, "abbreviation": "PHI"},
            ]
        }
        (teams_dir / "2024.json").write_text(json.dumps(teams_data))
        lookup = build_team_lookup(tmp_path, 2024)
        assert lookup == {9: "DAL", 24: "PHI"}


class TestProcessSeason:
    def _setup_raw_data(self, tmp_path):
        """Create minimal raw JSON fixture data."""
        # Teams
        teams_dir = tmp_path / "raw" / "teams"
        teams_dir.mkdir(parents=True)
        teams_data = {"teams": [{"franchise_id": 9, "abbreviation": "DAL"}]}
        (teams_dir / "2024.json").write_text(json.dumps(teams_data))

        # Facet data
        week_dir = tmp_path / "raw" / "facets" / "2024" / "week_01"
        week_dir.mkdir(parents=True)

        rushing_data = {
            "rushing_summary": [
                {
                    "player": "Saquon Barkley",
                    "player_id": 45791,
                    "franchise_id": 9,
                    "position": "HB",
                    "attempts": 18,
                    "yards": 60,
                    "grades_run": 58.4,
                },
            ]
        }
        (week_dir / "28418_rushing_summary.json").write_text(json.dumps(rushing_data))
        return tmp_path

    def test_produces_parquet_file(self, tmp_path):
        base = self._setup_raw_data(tmp_path)
        processed_dir = tmp_path / "processed"
        processed_dir.mkdir(parents=True)
        process_season(base, 2024)
        parquet_path = processed_dir / "rushing_summary_2024.parquet"
        assert parquet_path.exists()

    def test_parquet_has_metadata_columns(self, tmp_path):
        base = self._setup_raw_data(tmp_path)
        processed_dir = tmp_path / "processed"
        processed_dir.mkdir(parents=True)
        process_season(base, 2024)
        df = pl.read_parquet(processed_dir / "rushing_summary_2024.parquet")
        assert "season" in df.columns
        assert "week" in df.columns
        assert "game_id" in df.columns
        assert "team" in df.columns

    def test_parquet_has_correct_data(self, tmp_path):
        base = self._setup_raw_data(tmp_path)
        processed_dir = tmp_path / "processed"
        processed_dir.mkdir(parents=True)
        process_season(base, 2024)
        df = pl.read_parquet(processed_dir / "rushing_summary_2024.parquet")
        assert len(df) == 1
        row = df.row(0, named=True)
        assert row["player"] == "Saquon Barkley"
        assert row["season"] == 2024
        assert row["week"] == 1
        assert row["game_id"] == 28418
        assert row["team"] == "DAL"
        assert row["grades_run"] == 58.4
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_scripts/test_scrape_pff.py::TestProcessSeason -v`
Expected: FAIL — `process_season` and `build_team_lookup` not defined

- [ ] **Step 3: Implement build_team_lookup and process_season**

Add to `scripts/scrape_pff.py`, after `scrape_season`:

```python
def build_team_lookup(base_dir: Path, season: int) -> dict[int, str]:
    """Build franchise_id → abbreviation mapping from teams JSON."""
    teams_path = base_dir / "raw" / "teams" / f"{season}.json"
    if not teams_path.exists():
        return {}
    data = json.loads(teams_path.read_text())
    return {t["franchise_id"]: t["abbreviation"] for t in data.get("teams", [])}


def process_season(base_dir: Path, season: int) -> None:
    """Process raw JSON files into per-facet parquet files for a season."""
    team_lookup = build_team_lookup(base_dir, season)
    facets_dir = base_dir / "raw" / "facets" / str(season)
    processed_dir = base_dir / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)

    if not facets_dir.exists():
        console.print(f"[yellow]No raw data found for {season}[/yellow]")
        return

    facet_keys = set()
    for category, subfacet in ALL_FACETS:
        facet_keys.add(f"{category}_{subfacet}")

    for facet_key in sorted(facet_keys):
        rows: list[dict] = []

        # Glob all matching files across weeks
        for week_dir in sorted(facets_dir.iterdir()):
            if not week_dir.is_dir():
                continue
            # Extract week number from directory name (week_01 → 1)
            week_num = int(week_dir.name.replace("week_", ""))

            for json_file in sorted(week_dir.glob(f"*_{facet_key}.json")):
                # Extract game_id from filename (28418_passing_summary.json → 28418)
                game_id = int(json_file.name.split("_")[0])
                data = json.loads(json_file.read_text())

                # The API wraps data in a key like "rushing_summary": [...]
                player_rows = data.get(facet_key, [])
                for player_row in player_rows:
                    player_row["season"] = season
                    player_row["week"] = week_num
                    player_row["game_id"] = game_id
                    player_row["team"] = team_lookup.get(player_row.get("franchise_id"), "UNK")
                    rows.append(player_row)

        if rows:
            df = pl.DataFrame(rows)
            out_path = processed_dir / f"{facet_key}_{season}.parquet"
            df.write_parquet(out_path)
            console.print(f"  [green]{facet_key}[/green]: {len(rows)} rows → {out_path.name}")
        else:
            console.print(f"  [dim]{facet_key}[/dim]: no data")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_scripts/test_scrape_pff.py::TestProcessSeason tests/test_scripts/test_scrape_pff.py::TestBuildTeamLookup -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/scrape_pff.py tests/test_scripts/test_scrape_pff.py
git commit -m "feat: add processing pipeline to convert PFF raw JSON to parquet"
```

---

### Task 9: Wire Processing into Main and Handle process-only

**Files:**
- Modify: `scripts/scrape_pff.py`

- [ ] **Step 1: Update main() to call process_season**

In `main()`, replace the processing placeholder comment with the actual call. The updated end of `main()` should be:

```python
    if args.process_only:
        console.print("[bold]Process-only mode[/bold] — skipping scrape\n")
        console.print(f"[bold]Processing raw data for {args.season}...[/bold]")
        process_season(PFF_DIR, args.season)
        console.print("\n[bold green]Done.[/bold green]")
        return

    # Load and validate cookie
    cookie = load_cookie()
    if cookie is None:
        console.print("[bold red]Error:[/bold red] No PFF cookie found.")
        console.print("Create ~/.fantasy-sim/pff/.env with your PFF_COOKIE.")
        console.print("See docs/pff-setup.md for instructions.")
        sys.exit(1)

    client = build_client(cookie)
    if not validate_cookie(client, args.season):
        console.print("[bold red]Error:[/bold red] PFF cookie is invalid or expired.")
        console.print("Refresh your cookie — see docs/pff-setup.md")
        client.close()
        sys.exit(1)

    console.print("[green]Cookie validated[/green]\n")

    try:
        stats = scrape_season(client, args.season, weeks, args.delay)
        console.print(f"\n[bold]Scrape complete:[/bold]")
        console.print(f"  Requests made: {stats['requests']}")
        console.print(f"  Skipped (already done): {stats['skipped_done']}")
        console.print(f"  Skipped (404): {stats['skipped_404']}")
        console.print(f"  Failures: {stats['failures']}")

        console.print(f"\n[bold]Processing raw data for {args.season}...[/bold]")
        process_season(PFF_DIR, args.season)
        console.print("\n[bold green]Done.[/bold green]")
    finally:
        client.close()
```

- [ ] **Step 2: Verify process-only works with no crash**

Run: `uv run python scripts/scrape_pff.py --season 2024 --process-only`
Expected: Prints "Process-only mode" then "No raw data found for 2024" or processes any existing data. No crash.

- [ ] **Step 3: Run all tests**

Run: `uv run pytest tests/test_scripts/test_scrape_pff.py -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add scripts/scrape_pff.py
git commit -m "feat: wire processing pipeline into PFF scraper main flow"
```

---

### Task 10: Update Docs and Final Verification

**Files:**
- Modify: `README.md` (if PFF scraper should be mentioned)
- Verify: full test suite still passes

- [ ] **Step 1: Run the full test suite**

Run: `uv run pytest tests/ -v`
Expected: All existing tests PASS, plus the new test_scrape_pff tests

- [ ] **Step 2: Run the script with --help to verify complete output**

Run: `uv run python scripts/scrape_pff.py --help`
Expected: Shows usage with all flags documented

- [ ] **Step 3: Verify process-only mode works end-to-end**

Run: `uv run python scripts/scrape_pff.py --season 2024 --process-only`
Expected: Runs without error (prints "no raw data" if nothing has been scraped yet)

- [ ] **Step 4: Add PFF scraper section to README.md**

Add a brief section to README.md under the commands or scripts section:

```markdown
### PFF Data Scraper

Extracts game-level player data from PFF Premium. Requires an active subscription.

```bash
# Setup: See docs/pff-setup.md for cookie extraction
uv run python scripts/scrape_pff.py --season 2024
uv run python scripts/scrape_pff.py --season 2026 --weeks 1-8
uv run python scripts/scrape_pff.py --season 2024 --process-only
```
```

- [ ] **Step 5: Final commit**

```bash
git add README.md
git commit -m "docs: add PFF scraper usage to README"
```

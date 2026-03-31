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


def build_team_lookup(base_dir: Path, season: int) -> dict[int, str]:
    """Build franchise_id -> abbreviation mapping from teams JSON."""
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
            # Extract week number from directory name (week_01 -> 1)
            week_num = int(week_dir.name.replace("week_", ""))

            for json_file in sorted(week_dir.glob(f"*_{facet_key}.json")):
                # Extract game_id from filename (28418_passing_summary.json -> 28418)
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
            console.print(f"  [green]{facet_key}[/green]: {len(rows)} rows -> {out_path.name}")
        else:
            console.print(f"  [dim]{facet_key}[/dim]: no data")


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

        console.print(f"\n[bold]Processing raw data...[/bold]")
    finally:
        client.close()


if __name__ == "__main__":
    main()

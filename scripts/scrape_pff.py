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
    client.close()


if __name__ == "__main__":
    main()

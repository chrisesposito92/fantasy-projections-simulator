"""PFF Player Props Scraper.

Fetches consensus betting lines from the PFF consumer API and caches them
as parquet files for downstream use by PropsLoader.

Run: uv run python scripts/scrape_pff_props.py --season 2025
     uv run python scripts/scrape_pff_props.py --season 2025 --weeks 1 2 3

Auth: Requires PFF_API_KEY in ~/.fantasy-sim/pff/.env or as env var.
"""

import json
import os
import sys
import time
from pathlib import Path

import click
import httpx
import polars as pl
from rich.console import Console

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PFF_PROPS_BASE_URL = "https://consumer-api.pff.com/football/v3/betting/nfl"
PFF_DIR = Path.home() / ".fantasy-sim" / "pff"
PROPS_CACHE_DIR = PFF_DIR / "props"
ENV_FILE = PFF_DIR / ".env"

DEFAULT_DELAY = 0.3
MAX_RETRIES = 3
DEFAULT_TIMEOUT = 30.0
DEFAULT_WEEKS = list(range(1, 19))  # weeks 1-18 regular season
SPORTSBOOK = "FanDuel"

console = Console()


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class AuthError(Exception):
    """Raised when PFF returns 401/403 -- API key is invalid or expired."""
    pass


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def load_api_key(env_path: Path = ENV_FILE) -> str | None:
    """Load PFF_API_KEY from environment variable or .env file.

    Precedence: PFF_API_KEY env var > .env file value.
    Returns None if not found anywhere.
    """
    # Check env var first (takes precedence per D-02)
    env_val = os.environ.get("PFF_API_KEY")
    if env_val:
        return env_val

    # Fall back to .env file
    if not env_path.exists():
        return None

    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line.startswith("PFF_API_KEY="):
            value = line[len("PFF_API_KEY="):]
            return value.strip().strip('"').strip("'")

    return None


def build_client(api_key: str) -> httpx.Client:
    """Create an httpx client with PFF Api-Key auth header."""
    return httpx.Client(
        base_url=PFF_PROPS_BASE_URL,
        headers={
            "Api-Key": api_key,
            "Accept": "application/json",
        },
        timeout=DEFAULT_TIMEOUT,
    )


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def fetch_props_page(
    client: httpx.Client,
    season: int,
    week: int,
    page: int,
    max_retries: int = MAX_RETRIES,
) -> list[dict] | None:
    """Fetch one page of player props from PFF consumer API.

    Returns:
        list[dict]: playerProps array from response on success
        []: empty list when page has no props (pagination end signal)
        None: after exhausted retries on transient errors

    Raises:
        AuthError: on 401/403 (API key invalid)
    """
    url = f"/{season}/player-props/{week}"
    params = {"sportsbooks": SPORTSBOOK, "page": page}

    for attempt in range(max_retries):
        try:
            resp = client.get(url, params=params)

            if resp.status_code in (401, 403):
                raise AuthError(
                    f"Authentication failed (HTTP {resp.status_code}). "
                    "Check your PFF_API_KEY."
                )

            if resp.status_code == 429:
                backoff = 2 ** attempt
                time.sleep(backoff)
                continue

            if resp.status_code >= 500:
                backoff = 2 ** attempt
                time.sleep(backoff)
                continue

            resp.raise_for_status()
            data = resp.json()
            return data.get("playerProps", [])

        except AuthError:
            raise
        except httpx.HTTPError:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            return None

    return None


def paginate_week(
    client: httpx.Client,
    season: int,
    week: int,
    delay: float = DEFAULT_DELAY,
) -> list[dict]:
    """Fetch all props for a week by paginating until playerProps is empty.

    Returns flat list of all prop dicts across all pages.
    """
    all_props: list[dict] = []
    page = 1

    while True:
        props = fetch_props_page(client, season, week, page)

        if props is None:
            # Transient failure after retries -- return what we have so far
            console.print(
                f"  [yellow]Warning: page {page} failed after retries, "
                f"collected {len(all_props)} props so far[/yellow]"
            )
            break

        if not props:
            # Empty page -- pagination complete
            break

        all_props.extend(props)
        page += 1
        if delay > 0:
            time.sleep(delay)

    return all_props


# ---------------------------------------------------------------------------
# Data transformation
# ---------------------------------------------------------------------------

def _flatten_props(props: list[dict], season: int, week: int) -> pl.DataFrame:
    """Flatten raw prop dicts into a polars DataFrame.

    Extracts player fields to top-level columns. Stores complex nested
    objects (projections, averages, matchup, lastTen, option) as JSON
    strings for future research.
    """
    rows: list[dict] = []
    for prop in props:
        player = prop.get("player", {})
        row = {
            "prop_key": prop.get("propKey"),
            "consensus_line": prop.get("consensusLine"),
            "player_id": player.get("playerId"),
            "first_name": player.get("firstName"),
            "last_name": player.get("lastName"),
            "team_id": player.get("teamId"),
            "position": player.get("position"),
            "season": season,
            "week": week,
            # Complex nested fields serialized as JSON
            "projections_json": json.dumps(prop.get("projections")),
            "averages_json": json.dumps(prop.get("averages")),
            "matchup_json": json.dumps(prop.get("matchup")),
            "last_ten_json": json.dumps(prop.get("lastTen")),
            "option_json": json.dumps(prop.get("option")),
        }
        rows.append(row)

    if not rows:
        # Return empty DataFrame with correct schema
        return pl.DataFrame(
            schema={
                "prop_key": pl.Utf8,
                "consensus_line": pl.Float64,
                "player_id": pl.Int64,
                "first_name": pl.Utf8,
                "last_name": pl.Utf8,
                "team_id": pl.Int64,
                "position": pl.Utf8,
                "season": pl.Int64,
                "week": pl.Int64,
                "projections_json": pl.Utf8,
                "averages_json": pl.Utf8,
                "matchup_json": pl.Utf8,
                "last_ten_json": pl.Utf8,
                "option_json": pl.Utf8,
            }
        )

    return pl.DataFrame(rows, infer_schema_length=None)


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------

def scrape_week(
    client: httpx.Client,
    season: int,
    week: int,
    cache_dir: Path = PROPS_CACHE_DIR,
    delay: float = DEFAULT_DELAY,
) -> bool | None:
    """Scrape and cache all props for a single week.

    Returns:
        True: successfully scraped and cached
        False: skipped (cache already exists)
        None: error during scrape
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"props_{season}_week{week:02d}.parquet"

    # Skip if already cached (D-09)
    if cache_file.exists():
        console.print(f"  [dim]Week {week}: cached, skipping[/dim]")
        return False

    start = time.time()
    props = paginate_week(client, season, week, delay=delay)
    elapsed = time.time() - start

    pages = (len(props) // 30) + 1 if props else 1
    console.print(
        f"  Week {week}: {len(props)} props across ~{pages} pages "
        f"({elapsed:.1f}s)"
    )

    # Write parquet (even if empty, so re-run skips it)
    df = _flatten_props(props, season, week)
    df.write_parquet(cache_file)

    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.command()
@click.option("--season", required=True, type=int, help="Season year (e.g., 2025)")
@click.option(
    "--weeks",
    type=int,
    multiple=True,
    default=None,
    help="Specific weeks to scrape (default: 1-18)",
)
@click.option(
    "--delay",
    type=float,
    default=DEFAULT_DELAY,
    help=f"Delay between requests in seconds (default: {DEFAULT_DELAY})",
)
def cli(season: int, weeks: tuple[int, ...], delay: float) -> None:
    """PFF Player Props Scraper.

    Fetches consensus betting lines from PFF consumer API and caches
    as parquet files for downstream use by PropsLoader.
    """
    # Resolve weeks
    week_list = list(weeks) if weeks else DEFAULT_WEEKS

    console.print(f"\n[bold]PFF Props Scraper[/bold] -- Season {season}")
    console.print(f"  Weeks: {week_list}")
    console.print(f"  Delay: {delay}s")
    console.print(f"  Cache: {PROPS_CACHE_DIR}\n")

    # Load API key (D-02)
    api_key = load_api_key()
    if api_key is None:
        console.print(
            "[bold red]Error:[/bold red] No PFF API key found.\n"
            "Set PFF_API_KEY in ~/.fantasy-sim/pff/.env or as an environment variable."
        )
        sys.exit(1)

    # Build client -- key goes in header, never in URL (T-06-01)
    client = build_client(api_key)
    total_props = 0
    weeks_scraped = 0
    weeks_skipped = 0
    start = time.time()

    try:
        for week in week_list:
            try:
                result = scrape_week(client, season, week, delay=delay)
                if result is True:
                    weeks_scraped += 1
                    # Read back to count props
                    cache_file = PROPS_CACHE_DIR / f"props_{season}_week{week:02d}.parquet"
                    if cache_file.exists():
                        df = pl.read_parquet(cache_file)
                        total_props += len(df)
                elif result is False:
                    weeks_skipped += 1
            except AuthError as e:
                console.print(f"\n[bold red]{e}[/bold red]")
                console.print(
                    "Check your PFF_API_KEY in ~/.fantasy-sim/pff/.env"
                )
                sys.exit(1)

        elapsed = time.time() - start
        console.print(f"\n[bold]Scrape complete:[/bold]")
        console.print(f"  Weeks scraped: {weeks_scraped}")
        console.print(f"  Weeks skipped (cached): {weeks_skipped}")
        console.print(f"  Total props: {total_props}")
        console.print(f"  Time: {elapsed:.1f}s")
        console.print(f"  Cache: {PROPS_CACHE_DIR}")
        console.print("[bold green]Done.[/bold green]")

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
        sys.exit(1)
    finally:
        client.close()


if __name__ == "__main__":
    cli()

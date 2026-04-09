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
from dataclasses import dataclass
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


@dataclass(frozen=True)
class LeagueConfig:
    """League-specific configuration for scraping."""
    name: str       # "nfl" or "ncaa"
    min_week: int   # first week number (NFL: 1, NCAA: 0)
    max_week: int   # last week number (NFL: 22, NCAA: 16)


LEAGUES: dict[str, LeagueConfig] = {
    "nfl": LeagueConfig(name="nfl", min_week=1, max_week=22),
    "ncaa": LeagueConfig(name="ncaa", min_week=0, max_week=16),
}

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

# PFF Fantasy Stats endpoints (different API from game-level facets)
# These are aggregate per-player stats, not per-game.
FANTASY_FACETS: list[tuple[str, str]] = [
    ("receiving", "fantasy_receiving"),   # WR/RB/TE rushing+receiving
    ("passing", "fantasy_passing"),       # QB passing+rushing
]


console = Console()


class ProgressTracker:
    """Tracks which (season, week, game, facet) combos have been scraped."""

    def __init__(self, path: Path | None = None):
        self.path = path or PROGRESS_FILE
        self.data: dict = {}
        if self.path.exists():
            self.data = json.loads(self.path.read_text())

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


_NOT_FOUND = object()  # sentinel for 404 responses


def fetch_json(
    client: httpx.Client,
    path: str,
    delay: float = DEFAULT_DELAY,
    max_retries: int = MAX_RETRIES,
) -> dict | object | None:
    """Fetch JSON from PFF API with retry logic.

    Returns dict on success, _NOT_FOUND sentinel for 404, None for exhausted retries.
    Raises AuthError for 401/403.
    """
    for attempt in range(max_retries):
        try:
            resp = client.get(path)

            if resp.status_code in (401, 403):
                raise AuthError(f"Authentication failed: {resp.status_code}")

            if resp.status_code == 404:
                return _NOT_FOUND

            if resp.status_code == 429:
                backoff = 2 ** attempt
                time.sleep(backoff)
                continue

            resp.raise_for_status()
            time.sleep(delay)
            return resp.json()

        except httpx.HTTPError:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            return None

    return None


def fetch_teams(client: httpx.Client, season: int, delay: float, league: LeagueConfig) -> dict:
    """Fetch and cache team metadata for a season."""
    cache_path = RAW_DIR / league.name / "teams" / f"{season}.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    if cache_path.exists():
        return json.loads(cache_path.read_text())
    data = fetch_json(client, f"/api/v1/teams?league={league.name}&season={season}", delay=delay)
    if not isinstance(data, dict):
        console.print(f"[bold red]Error:[/bold red] Could not fetch teams for {season}")
        sys.exit(1)
    cache_path.write_text(json.dumps(data, indent=2))
    return data


def fetch_games_for_week(client: httpx.Client, season: int, week: int, delay: float, league: LeagueConfig) -> list[dict]:
    """Fetch game list for a specific week. Returns empty list if no games."""
    cache_path = RAW_DIR / league.name / "games" / f"{season}_week{week:02d}.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    if cache_path.exists():
        data = json.loads(cache_path.read_text())
    else:
        data = fetch_json(client, f"/api/v1/games?league={league.name}&season={season}&week={week}", delay=delay)
        if not isinstance(data, dict):
            return []
        cache_path.write_text(json.dumps(data, indent=2))
    return data.get("games", [])


def discover_weeks(client: httpx.Client, season: int, delay: float, league: LeagueConfig) -> list[int]:
    """Find all weeks that have games for a season."""
    weeks_with_games = []
    for week in range(league.min_week, league.max_week + 1):
        games = fetch_games_for_week(client, season, week, delay, league)
        if games:
            weeks_with_games.append(week)
    return weeks_with_games


def scrape_season(
    client: httpx.Client,
    season: int,
    weeks: list[int] | None,
    delay: float,
    league: LeagueConfig,
) -> dict:
    """Scrape all facets for all games in the given season/weeks.

    Returns stats dict with counts of requests, skips, failures.
    """
    stats = {"requests": 0, "skipped_done": 0, "skipped_404": 0, "failures": 0}
    progress_path = STATE_DIR / f"progress_{league.name}.json"
    tracker = ProgressTracker(progress_path)
    season_str = str(season)

    # Fetch teams
    console.print("Fetching teams...")
    try:
        fetch_teams(client, season, delay, league)
    except AuthError:
        console.print("[bold red]Auth error fetching teams — cookie expired. Stopping.[/bold red]")
        console.print("Refresh your cookie — see docs/pff-setup.md")
        tracker.save()
        return stats

    # Determine weeks
    if weeks is None:
        console.print("Discovering weeks with games...")
        try:
            weeks = discover_weeks(client, season, delay, league)
        except AuthError:
            console.print("[bold red]Auth error discovering weeks — cookie expired. Stopping.[/bold red]")
            console.print("Refresh your cookie — see docs/pff-setup.md")
            tracker.save()
            return stats
    console.print(f"Weeks to scrape: {weeks}\n")

    if not weeks:
        console.print("[yellow]No weeks found with games.[/yellow]")
        return stats

    try:
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

                games = fetch_games_for_week(client, season, week, delay, league)
                if not games:
                    progress.advance(week_task)
                    continue

                # Ensure week directory exists
                week_dir = RAW_DIR / league.name / "facets" / str(season) / week_str
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

                        if data is _NOT_FOUND:
                            stats["skipped_404"] += 1
                            tracker.mark_done(season_str, week_str, game_id_str, facet_key)
                        elif data is None:
                            # Transient failure — do NOT mark done so it retries next run
                            stats["failures"] += 1
                        else:
                            # PFF returns a "restricted" key listing premium
                            # fields that were stripped when the cookie expires.
                            if "restricted" in data:
                                console.print(f"\n[bold red]Cookie expired — response contains restricted fields. Stopping.[/bold red]")
                                console.print("Refresh your cookie — see docs/pff-setup.md")
                                tracker.save()
                                sys.exit(1)
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

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted — saving progress...[/yellow]")
        tracker.save()
        console.print("[green]Progress saved. Re-run to resume.[/green]")
        return stats

    tracker.save()
    return stats


def scrape_fantasy_stats(
    client: httpx.Client,
    season: int,
    weeks: list[int] | None,
    delay: float,
) -> dict:
    """Scrape PFF fantasy stats (receiving + passing) per-week.

    Unlike game-level facets, these are aggregate endpoints that return
    all players for a given season+week combination.

    Stores:
      - Raw JSON per week: ~/.fantasy-sim/pff/raw/nfl/fantasy/{facet}_{season}_week{wk}.json
      - Combined parquet: ~/.fantasy-sim/pff/processed/nfl/{facet}_{season}.parquet
    """
    stats = {"requests": 0, "skipped": 0, "failures": 0}

    if weeks is None:
        weeks = list(range(1, 19))

    for api_facet, output_name in FANTASY_FACETS:
        all_rows: list[dict] = []

        for week in weeks:
            raw_path = RAW_DIR / "nfl" / "fantasy" / f"{output_name}_{season}_week{week}.json"
            raw_path.parent.mkdir(parents=True, exist_ok=True)

            if raw_path.exists():
                cached = json.loads(raw_path.read_text())
                for row in cached:
                    row["season"] = season
                    row["week"] = week
                all_rows.extend(cached)
                stats["skipped"] += 1
                continue

            # Fantasy stats use www.pff.com, not premium.pff.com
            url = f"https://www.pff.com/api/fantasy/stats/{api_facet}?season={season}&weeks={week}&scoring=preset_ppr"
            try:
                resp = client.get(url)
                if resp.status_code in (401, 403):
                    raise AuthError(f"Fantasy stats auth failed: {resp.status_code}")
                if resp.status_code == 404:
                    console.print(f"  [yellow]No data:[/yellow] {output_name} week {week}")
                    stats["failures"] += 1
                    continue
                resp.raise_for_status()
                data = resp.json()
                time.sleep(delay)
            except httpx.HTTPError as exc:
                console.print(f"  [yellow]Error:[/yellow] {output_name} week {week}: {exc}")
                stats["failures"] += 1
                continue

            stats["requests"] += 1

            if not isinstance(data, list):
                console.print(f"  [yellow]Unexpected response:[/yellow] {output_name} week {week}")
                stats["failures"] += 1
                continue

            raw_path.write_text(json.dumps(data, indent=2))

            for row in data:
                row["season"] = season
                row["week"] = week
            all_rows.extend(data)
            console.print(f"  {output_name} week {week}: {len(data)} players")

        # Write combined parquet
        if all_rows:
            import polars as pl_local
            df = pl_local.DataFrame(all_rows)
            parquet_path = PROCESSED_DIR / "nfl" / f"{output_name}_{season}.parquet"
            parquet_path.parent.mkdir(parents=True, exist_ok=True)
            df.write_parquet(parquet_path)
            console.print(f"  [green]Wrote {output_name}_{season}.parquet ({len(all_rows)} rows)[/green]")

    return stats


def build_team_lookup(base_dir: Path, season: int, league: LeagueConfig) -> dict[int, str]:
    """Build franchise_id -> abbreviation mapping from teams JSON."""
    teams_path = base_dir / "raw" / league.name / "teams" / f"{season}.json"
    if not teams_path.exists():
        return {}
    data = json.loads(teams_path.read_text())
    return {t["franchise_id"]: t["abbreviation"] for t in data.get("teams", [])}


def _extract_player_rows(data: dict) -> list[dict]:
    """Extract player rows from an API response, handling nested structures.

    Most facets return {"key": [player_dicts...]}.
    Coverage matchup facets return {"key": {"defenders": [...], "receivers": [...], "versus": [...]}}.
    """
    rows: list[dict] = []
    for v in data.values():
        if isinstance(v, list):
            rows.extend(v)
            return rows
        if isinstance(v, dict):
            # Nested structure — collect all sub-lists
            for sub_v in v.values():
                if isinstance(sub_v, list):
                    rows.extend(sub_v)
            if rows:
                return rows
    return rows


def process_season(base_dir: Path, season: int, league: LeagueConfig) -> None:
    """Process raw JSON files into per-facet parquet files for a season."""
    team_lookup = build_team_lookup(base_dir, season, league)
    facets_dir = base_dir / "raw" / league.name / "facets" / str(season)
    processed_dir = base_dir / "processed" / league.name
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

                # Extract player rows from API response. The response shape
                # varies: sometimes a flat list, sometimes nested dicts
                # with sub-lists (e.g., coverage matchups have defenders/
                # receivers/versus sub-keys).
                player_rows = _extract_player_rows(data)
                for player_row in player_rows:
                    if not isinstance(player_row, dict):
                        continue
                    player_row["season"] = season
                    player_row["week"] = week_num
                    player_row["game_id"] = game_id
                    player_row["team"] = team_lookup.get(player_row.get("franchise_id"), "UNK")
                    rows.append(player_row)

        if rows:
            df = pl.DataFrame(rows, infer_schema_length=None)
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
    parser.add_argument("--season", type=int, required=True, help="Season year (e.g., 2024)")
    parser.add_argument("--league", type=str, choices=list(LEAGUES.keys()), default="nfl", help="League to scrape (default: nfl)")
    parser.add_argument("--weeks", type=str, default=None, help="Week range (e.g., '1-8' or '12')")
    parser.add_argument("--process-only", action="store_true", help="Re-process raw JSON to parquet without scraping")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY, help=f"Delay between API requests in seconds (default: {DEFAULT_DELAY})")
    parser.add_argument("--fantasy", action="store_true", help="Also scrape fantasy stats (receiving, passing)")
    return parser.parse_args()


def parse_weeks(weeks_str: str | None) -> list[int] | None:
    """Parse --weeks argument into a list of week numbers, or None for all."""
    if weeks_str is None:
        return None
    try:
        if "-" in weeks_str:
            start, end = weeks_str.split("-", 1)
            start_int, end_int = int(start), int(end)
            if start_int > end_int:
                raise ValueError(f"start ({start_int}) > end ({end_int})")
            return list(range(start_int, end_int + 1))
        return [int(weeks_str)]
    except ValueError as e:
        raise SystemExit(f"Invalid --weeks value '{weeks_str}': {e}")


def ensure_directories() -> None:
    """Create the PFF base directory structure."""
    for d in [RAW_DIR, PROCESSED_DIR, STATE_DIR]:
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


def build_client(cookie: str, league: LeagueConfig) -> httpx.Client:
    """Create an httpx client with PFF auth headers."""
    return httpx.Client(
        base_url=PFF_BASE_URL,
        headers={
            "Cookie": cookie,
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "application/json",
            "Referer": f"{PFF_BASE_URL}/{league.name}/games",
        },
        timeout=30.0,
    )


def validate_cookie(client: httpx.Client, season: int, league: LeagueConfig) -> bool:
    """Validate the cookie by making a lightweight API request."""
    try:
        resp = client.get(f"/api/v1/teams?league={league.name}&season={season}")
        if resp.status_code in (401, 403):
            return False
        resp.raise_for_status()
        return True
    except httpx.HTTPError:
        return False


def main() -> None:
    args = parse_args()
    league = LEAGUES[args.league]
    weeks = parse_weeks(args.weeks)
    ensure_directories()

    console.print(f"\n[bold]PFF Scraper[/bold] — {league.name.upper()} Season {args.season}")
    if weeks:
        console.print(f"  Weeks: {weeks}")
    console.print(f"  Delay: {args.delay}s\n")

    if args.process_only:
        console.print("[bold]Process-only mode[/bold] — skipping scrape\n")
        console.print(f"[bold]Processing raw data for {args.season}...[/bold]")
        process_season(PFF_DIR, args.season, league)
        console.print("\n[bold green]Done.[/bold green]")
        return

    # Load and validate cookie
    cookie = load_cookie()
    if cookie is None:
        console.print("[bold red]Error:[/bold red] No PFF cookie found.")
        console.print("Create ~/.fantasy-sim/pff/.env with your PFF_COOKIE.")
        console.print("See docs/pff-setup.md for instructions.")
        sys.exit(1)

    client = build_client(cookie, league)
    if not validate_cookie(client, args.season, league):
        console.print("[bold red]Error:[/bold red] PFF cookie is invalid or expired.")
        console.print("Refresh your cookie — see docs/pff-setup.md")
        client.close()
        sys.exit(1)

    console.print("[green]Cookie validated[/green]\n")

    try:
        stats = scrape_season(client, args.season, weeks, args.delay, league)
        console.print(f"\n[bold]Scrape complete:[/bold]")
        console.print(f"  Requests made: {stats['requests']}")
        console.print(f"  Skipped (already done): {stats['skipped_done']}")
        console.print(f"  Skipped (404): {stats['skipped_404']}")
        console.print(f"  Failures: {stats['failures']}")

        console.print(f"\n[bold]Processing raw data for {args.season}...[/bold]")
        process_season(PFF_DIR, args.season, league)

        if args.fantasy:
            console.print(f"\n[bold]Scraping fantasy stats for {args.season}...[/bold]")
            fantasy_stats = scrape_fantasy_stats(client, args.season, weeks, args.delay)
            console.print(
                f"Fantasy stats: {fantasy_stats['requests']} requests, "
                f"{fantasy_stats['skipped']} cached, {fantasy_stats['failures']} failures"
            )

        console.print("\n[bold green]Done.[/bold green]")
    finally:
        client.close()


if __name__ == "__main__":
    main()

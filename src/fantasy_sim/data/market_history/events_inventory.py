from __future__ import annotations

from datetime import date, timedelta
import json
import os
from pathlib import Path
import time
from typing import TypeAlias, cast

import httpx
import polars as pl
from polars._typing import SchemaDict

from fantasy_sim.data.loader import DataLoader
from fantasy_sim.data.market_history.loader import DEFAULT_MARKET_HISTORY_PROCESSED_DIR

DEFAULT_MARKET_HISTORY_DIR = Path.home() / ".fantasy-sim" / "market-history"
DEFAULT_MARKET_HISTORY_ENV_FILE = DEFAULT_MARKET_HISTORY_DIR / ".env"
DEFAULT_MARKET_HISTORY_RAW_EVENTS_DIR = DEFAULT_MARKET_HISTORY_DIR / "raw" / "events"
DEFAULT_EVENTS_INVENTORY_DIR = DEFAULT_MARKET_HISTORY_PROCESSED_DIR

THE_ODDS_API_BASE_URL = "https://api.the-odds-api.com"
SPORT_KEY = "americanfootball_nfl"
DEFAULT_DELAY_SECONDS = 0.5
DEFAULT_TIMEOUT_SECONDS = 30.0
MAX_RETRIES = 3

TEAM_ABBREV_TO_NAME: dict[str, str] = {
    "ARI": "Arizona Cardinals",
    "ATL": "Atlanta Falcons",
    "BAL": "Baltimore Ravens",
    "BUF": "Buffalo Bills",
    "CAR": "Carolina Panthers",
    "CHI": "Chicago Bears",
    "CIN": "Cincinnati Bengals",
    "CLE": "Cleveland Browns",
    "DAL": "Dallas Cowboys",
    "DEN": "Denver Broncos",
    "DET": "Detroit Lions",
    "GB": "Green Bay Packers",
    "HOU": "Houston Texans",
    "IND": "Indianapolis Colts",
    "JAX": "Jacksonville Jaguars",
    "KC": "Kansas City Chiefs",
    "LAC": "Los Angeles Chargers",
    "LV": "Las Vegas Raiders",
    "LAR": "Los Angeles Rams",
    "LA": "Los Angeles Rams",
    "MIA": "Miami Dolphins",
    "MIN": "Minnesota Vikings",
    "NE": "New England Patriots",
    "NO": "New Orleans Saints",
    "NYG": "New York Giants",
    "NYJ": "New York Jets",
    "PHI": "Philadelphia Eagles",
    "PIT": "Pittsburgh Steelers",
    "SEA": "Seattle Seahawks",
    "SF": "San Francisco 49ers",
    "TB": "Tampa Bay Buccaneers",
    "TEN": "Tennessee Titans",
    "WAS": "Washington Commanders",
}

TEAM_NAME_TO_ABBREV: dict[str, str] = {
    name: abbr for abbr, name in TEAM_ABBREV_TO_NAME.items()
}

ScheduleRow: TypeAlias = dict[str, str | int]

EVENT_INVENTORY_SCHEMA: SchemaDict = {
    "season": pl.Int64,
    "week": pl.Int64,
    "gameday": pl.Utf8,
    "snapshot_date": pl.Utf8,
    "snapshot_timestamp": pl.Utf8,
    "previous_snapshot_timestamp": pl.Utf8,
    "next_snapshot_timestamp": pl.Utf8,
    "event_id": pl.Utf8,
    "commence_time": pl.Utf8,
    "home_team": pl.Utf8,
    "away_team": pl.Utf8,
    "home_team_abbr": pl.Utf8,
    "away_team_abbr": pl.Utf8,
    "sport_key": pl.Utf8,
    "sport_title": pl.Utf8,
    "schedule_game_id": pl.Utf8,
}


class OddsApiAuthError(Exception):
    """Raised when The Odds API rejects the supplied API key."""


def load_the_odds_api_key(env_path: Path = DEFAULT_MARKET_HISTORY_ENV_FILE) -> str | None:
    """Load THE_ODDS_API_KEY/THE_ODDS_API from env or ~/.fantasy-sim/market-history/.env."""
    for env_key in ("THE_ODDS_API_KEY", "THE_ODDS_API"):
        env_val = os.environ.get(env_key)
        if env_val:
            return env_val

    if not env_path.exists():
        return None

    values: dict[str, str] = {}
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")

    return values.get("THE_ODDS_API_KEY") or values.get("THE_ODDS_API")


def build_client(api_key: str) -> httpx.Client:
    """Create a The Odds API client."""
    return httpx.Client(
        base_url=THE_ODDS_API_BASE_URL,
        timeout=DEFAULT_TIMEOUT_SECONDS,
        params={"apiKey": api_key},
        headers={"Accept": "application/json"},
    )


def build_request_window(gameday: str) -> tuple[str, str, str]:
    """Return snapshot date plus commence-time filters for one NFL gameday."""
    day = date.fromisoformat(gameday)
    next_day = day + timedelta(days=1)
    snapshot_date = f"{gameday}T12:00:00Z"
    commence_time_from = f"{gameday}T00:00:00Z"
    commence_time_to = f"{next_day.isoformat()}T12:00:00Z"
    return snapshot_date, commence_time_from, commence_time_to


def build_schedule_day_frame(schedules: pl.DataFrame) -> pl.DataFrame:
    """Build unique regular-season gamedays to crawl from the nflverse schedule."""
    return (
        schedules.filter(pl.col("game_type") == "REG")
        .select(["season", "week", "gameday"])
        .unique(maintain_order=True)
        .sort(["season", "week", "gameday"])
        .with_columns(
            [
                pl.col("gameday").map_elements(
                    lambda gameday: build_request_window(gameday)[0],
                    return_dtype=pl.Utf8,
                ).alias("snapshot_date"),
                pl.col("gameday").map_elements(
                    lambda gameday: build_request_window(gameday)[1],
                    return_dtype=pl.Utf8,
                ).alias("commence_time_from"),
                pl.col("gameday").map_elements(
                    lambda gameday: build_request_window(gameday)[2],
                    return_dtype=pl.Utf8,
                ).alias("commence_time_to"),
            ]
        )
    )


def fetch_historical_events_snapshot(
    client: httpx.Client,
    *,
    snapshot_date: str,
    commence_time_from: str,
    commence_time_to: str,
    sport: str = SPORT_KEY,
    max_retries: int = MAX_RETRIES,
) -> dict:
    """Fetch one historical events snapshot for the given date window."""
    path = f"/v4/historical/sports/{sport}/events"
    params = {
        "date": snapshot_date,
        "dateFormat": "iso",
        "commenceTimeFrom": commence_time_from,
        "commenceTimeTo": commence_time_to,
    }

    for attempt in range(max_retries):
        response = client.get(path, params=params)

        if response.status_code in (401, 403):
            raise OddsApiAuthError(
                f"Authentication failed (HTTP {response.status_code}). Check THE_ODDS_API_KEY."
            )
        if response.status_code == 429 or response.status_code >= 500:
            if attempt < max_retries - 1:
                time.sleep(2**attempt)
                continue
            response.raise_for_status()

        response.raise_for_status()
        return response.json()

    raise RuntimeError("unreachable")


def raw_snapshot_path(
    season: int,
    gameday: str,
    *,
    raw_events_dir: Path | None = None,
) -> Path:
    base_dir = Path(raw_events_dir or DEFAULT_MARKET_HISTORY_RAW_EVENTS_DIR)
    return base_dir / str(season) / f"{gameday}.json"


def save_raw_snapshot(
    path: Path,
    *,
    season: int,
    week: int,
    gameday: str,
    snapshot_date: str,
    commence_time_from: str,
    commence_time_to: str,
    payload: dict,
) -> None:
    """Persist one historical events snapshot and the request metadata."""
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "season": season,
        "week": week,
        "gameday": gameday,
        "snapshot_date": snapshot_date,
        "commence_time_from": commence_time_from,
        "commence_time_to": commence_time_to,
        "payload": payload,
    }
    path.write_text(json.dumps(record, indent=2, sort_keys=True))


def inventory_path(
    season: int,
    *,
    processed_dir: Path | None = None,
) -> Path:
    base_dir = Path(processed_dir or DEFAULT_EVENTS_INVENTORY_DIR)
    return base_dir / f"events_inventory_{season}.parquet"


def _schedule_lookup(schedule: pl.DataFrame) -> dict[tuple[str, str, str], ScheduleRow]:
    season_schedule = schedule.filter(pl.col("game_type") == "REG").select(
        ["game_id", "season", "week", "gameday", "home_team", "away_team"]
    )
    return {
        (
            str(row["gameday"]),
            str(row["home_team"]),
            str(row["away_team"]),
        ): row
        for row in season_schedule.iter_rows(named=True)
    }


def flatten_raw_snapshot(
    record: dict,
    schedule_lookup: dict[tuple[str, str, str], ScheduleRow],
) -> pl.DataFrame:
    """Flatten one saved raw historical-events snapshot into inventory rows."""
    payload = record.get("payload", {})
    rows: list[dict[str, object]] = []
    record_season = cast(int | str, record["season"])
    record_week = cast(int | str, record["week"])
    for event in payload.get("data", []):
        home_team = str(event.get("home_team") or "")
        away_team = str(event.get("away_team") or "")
        home_abbr = TEAM_NAME_TO_ABBREV.get(home_team)
        away_abbr = TEAM_NAME_TO_ABBREV.get(away_team)
        schedule_row = (
            schedule_lookup.get((str(record["gameday"]), home_abbr or "", away_abbr or ""))
            if home_abbr and away_abbr
            else None
        )
        week_value = schedule_row["week"] if schedule_row is not None else record_week
        rows.append(
            {
                "season": int(str(record_season)),
                "week": int(str(week_value)),
                "gameday": str(record["gameday"]),
                "snapshot_date": str(record["snapshot_date"]),
                "snapshot_timestamp": payload.get("timestamp"),
                "previous_snapshot_timestamp": payload.get("previous_timestamp"),
                "next_snapshot_timestamp": payload.get("next_timestamp"),
                "event_id": event.get("id"),
                "commence_time": event.get("commence_time"),
                "home_team": home_team,
                "away_team": away_team,
                "home_team_abbr": home_abbr,
                "away_team_abbr": away_abbr,
                "sport_key": event.get("sport_key"),
                "sport_title": event.get("sport_title"),
                "schedule_game_id": (
                    str(schedule_row["game_id"]) if schedule_row is not None else None
                ),
            }
        )

    if not rows:
        return pl.DataFrame(schema=EVENT_INVENTORY_SCHEMA)
    return pl.DataFrame(rows, schema=EVENT_INVENTORY_SCHEMA)


def build_events_inventory_for_season(
    season: int,
    *,
    raw_events_dir: Path | None = None,
    processed_dir: Path | None = None,
    schedules: pl.DataFrame | None = None,
) -> Path:
    """Build one season-level event inventory parquet from saved raw snapshots."""
    loader = DataLoader()
    season_schedule = schedules if schedules is not None else loader.load_schedules([season])
    schedule_lookup = _schedule_lookup(season_schedule)
    base_dir = Path(raw_events_dir or DEFAULT_MARKET_HISTORY_RAW_EVENTS_DIR) / str(season)
    frames: list[pl.DataFrame] = []

    for path in sorted(base_dir.glob("*.json")):
        record = json.loads(path.read_text())
        frames.append(flatten_raw_snapshot(record, schedule_lookup))

    if frames:
        inventory = (
            pl.concat(frames, how="diagonal_relaxed")
            .unique(subset=["event_id"], keep="first")
            .sort(["week", "gameday", "commence_time", "home_team", "away_team"])
        )
    else:
        inventory = pl.DataFrame(schema=EVENT_INVENTORY_SCHEMA)

    output_path = inventory_path(season, processed_dir=processed_dir)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    inventory.write_parquet(output_path)
    return output_path

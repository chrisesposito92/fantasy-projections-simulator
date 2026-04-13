from __future__ import annotations

from datetime import datetime, timedelta, UTC
import json
from pathlib import Path
import time
from typing import cast

import httpx
import polars as pl

from fantasy_sim.data.market_history.events_inventory import (
    DEFAULT_MARKET_HISTORY_DIR,
    DEFAULT_TIMEOUT_SECONDS,
    MAX_RETRIES,
    OddsApiAuthError,
    SPORT_KEY,
)

DEFAULT_MARKET_HISTORY_RAW_PROPS_DIR = DEFAULT_MARKET_HISTORY_DIR / "raw" / "props"

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

EVENT_INVENTORY_REQUIRED_COLUMNS: tuple[str, ...] = (
    "season",
    "week",
    "event_id",
    "commence_time",
    "snapshot_date",
)


def load_events_inventory(
    seasons: list[int],
    *,
    processed_dir: Path | None = None,
    weeks: list[int] | None = None,
) -> pl.DataFrame:
    """Load cached event inventory parquet for the requested seasons."""
    base_dir = Path(processed_dir or (DEFAULT_MARKET_HISTORY_DIR / "processed"))
    frames: list[pl.DataFrame] = []
    for season in seasons:
        path = base_dir / f"events_inventory_{season}.parquet"
        if path.exists():
            frames.append(pl.read_parquet(path))
    if not frames:
        return pl.DataFrame()

    inventory = pl.concat(frames, how="diagonal_relaxed")
    for column in EVENT_INVENTORY_REQUIRED_COLUMNS:
        if column not in inventory.columns:
            raise ValueError(f"events inventory is missing required column: {column}")
    if weeks:
        inventory = inventory.filter(pl.col("week").is_in(weeks))
    return inventory.sort(["season", "week", "commence_time", "event_id"])


def build_snapshot_timestamp(
    event_row: dict[str, object],
    *,
    date_source: str,
    offset_minutes: int = 0,
) -> str:
    """Build the historical snapshot timestamp to query for one event."""
    raw_value = event_row.get(date_source)
    if raw_value is None:
        raise ValueError(f"event row is missing date source '{date_source}'")

    timestamp = datetime.fromisoformat(str(raw_value).replace("Z", "+00:00"))
    adjusted = timestamp + timedelta(minutes=offset_minutes)
    return adjusted.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def raw_props_path(
    season: int,
    event_id: str,
    *,
    snapshot_label: str,
    raw_props_dir: Path | None = None,
) -> Path:
    """Return the raw cache path for one event snapshot."""
    base_dir = Path(raw_props_dir or DEFAULT_MARKET_HISTORY_RAW_PROPS_DIR)
    return base_dir / str(season) / snapshot_label / f"{event_id}.json"


def fetch_historical_event_props(
    client: httpx.Client,
    *,
    event_id: str,
    date: str,
    markets: tuple[str, ...],
    regions: str = "us",
    sport: str = SPORT_KEY,
    max_retries: int = MAX_RETRIES,
) -> tuple[dict, dict[str, str | None]]:
    """Fetch one historical event-odds snapshot from The Odds API."""
    path = f"/v4/historical/sports/{sport}/events/{event_id}/odds"
    params = {
        "date": date,
        "dateFormat": "iso",
        "oddsFormat": "decimal",
        "regions": regions,
        "markets": ",".join(markets),
    }

    for attempt in range(max_retries):
        response = client.get(path, params=params, timeout=DEFAULT_TIMEOUT_SECONDS)

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
        headers = {
            "x-requests-remaining": response.headers.get("x-requests-remaining"),
            "x-requests-used": response.headers.get("x-requests-used"),
            "x-requests-last": response.headers.get("x-requests-last"),
        }
        return response.json(), headers

    raise RuntimeError("unreachable")


def save_raw_props_snapshot(
    path: Path,
    *,
    event_row: dict[str, object],
    snapshot_label: str,
    snapshot_timestamp: str,
    markets: tuple[str, ...],
    regions: str,
    payload: dict,
    headers: dict[str, str | None],
) -> None:
    """Persist one raw historical props snapshot and request metadata."""
    path.parent.mkdir(parents=True, exist_ok=True)
    season = cast(int | str, event_row["season"])
    week = cast(int | str, event_row["week"])
    record = {
        "season": int(str(season)),
        "week": int(str(week)),
        "event_id": str(event_row["event_id"]),
        "schedule_game_id": event_row.get("schedule_game_id"),
        "snapshot_label": snapshot_label,
        "snapshot_timestamp": snapshot_timestamp,
        "regions": regions,
        "markets": list(markets),
        "headers": headers,
        "payload": payload,
    }
    path.write_text(json.dumps(record, indent=2, sort_keys=True))

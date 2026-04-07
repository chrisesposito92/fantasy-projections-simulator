"""PropsLoader: fetches player props from The Odds API and caches as parquet.

VEG-03 implementation. Handles:
- Game-aware Thursday-open timestamp logic (not a hardcoded gameday-4 rule)
- Parquet cache keyed by (season, week)
- Graceful fallback when API key is missing
- Pre-2023 gap: props not available before May 2023

Security:
- API key read from env var only (never hardcoded, never logged)
- T-02-11: Thursday-open timestamp per game prevents look-ahead bias
- T-02-08: 0.5s sleep between calls + fallback on HTTP errors
"""

from __future__ import annotations

import logging
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
import polars as pl

from fantasy_sim.data.vegas.models import PropsConfig

logger = logging.getLogger(__name__)

# Football season uses EDT (UTC-4); Sep through Feb
_ET = timezone(timedelta(hours=-4))

# The Odds API base URL
_API_BASE = "https://api.the-odds-api.com/v4"

# First season with player props coverage on The Odds API (May 2023+)
_MIN_PROPS_SEASON = 2023


class PropsLoader:
    """Fetch and cache player props from The Odds API.

    Caches fetched data as parquet at ~/.fantasy-sim/props/ (or config.cache_dir)
    keyed by (season, week). On cache hit, no HTTP request is made.

    All HTTP errors are logged and result in an empty DataFrame (graceful
    degradation). Missing API key returns empty DataFrame with a warning.

    Args:
        config: PropsConfig with enabled flag, API key env var, markets, etc.
        cache_dir: Override cache directory (for testing). If None, uses
            config.cache_dir or ~/.fantasy-sim/props/.
    """

    def __init__(
        self,
        config: PropsConfig,
        cache_dir: Path | None = None,
    ) -> None:
        self.config = config

        if cache_dir is not None:
            self.cache_dir = Path(cache_dir)
        elif config.cache_dir:
            self.cache_dir = Path(config.cache_dir)
        else:
            self.cache_dir = Path.home() / ".fantasy-sim" / "props"

        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Read API key: env var first, then .env file in cache dir
        env_key = os.environ.get(config.api_key_env)
        if not env_key:
            env_key = self._load_env_file(config.api_key_env)
        if env_key:
            self._api_key: str | None = env_key
        else:
            logger.warning(
                "No Odds API key found in env var '%s' or %s/.env -- props disabled",
                config.api_key_env,
                self.cache_dir,
            )
            self._api_key = None

    def _redact(self, text: str) -> str:
        """Remove the API key from error messages to prevent leaking secrets."""
        if self._api_key:
            return text.replace(self._api_key, "***REDACTED***")
        return text

    def _load_env_file(self, key_name: str) -> str | None:
        """Load an API key from .env file in the cache directory."""
        env_path = self.cache_dir / ".env"
        if not env_path.exists():
            return None
        prefix = f"{key_name}="
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith(prefix):
                return line[len(prefix):].strip().strip('"').strip("'")
        return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_props(
        self,
        season: int,
        week: int,
        game_dates: dict[str, date] | None = None,
    ) -> pl.DataFrame:
        """Load player props for a given (season, week).

        Returns a polars DataFrame with columns:
            player_name: str, market: str, point: float,
            season: int, week: int

        Player ID mapping happens in PlayerPropsEngine (not here) -- this
        loader returns raw names from The Odds API.

        Args:
            season: NFL season year (e.g. 2024).
            week: NFL week number (1-18).
            game_dates: Optional dict of game_id -> gameday for Thursday-open
                timestamp computation. When None, defaults are used.

        Returns:
            DataFrame with props data, or empty DataFrame on any failure.
        """
        # --- Cache check ---
        cache_path = self.cache_dir / f"props_{season}_week{week:02d}.parquet"
        if cache_path.exists():
            logger.debug("Props cache hit: %s", cache_path)
            return pl.read_parquet(cache_path)

        # --- Graceful fallbacks ---
        if self._api_key is None:
            logger.warning("No Odds API key -- props disabled, returning empty")
            return self._empty_df()

        if season < _MIN_PROPS_SEASON:
            if not getattr(self, "_warned_min_season", False):
                logger.warning(
                    "Player props not available before season %d — skipping all earlier seasons",
                    _MIN_PROPS_SEASON,
                )
                self._warned_min_season = True
            return self._empty_df()

        # --- Fetch from API ---
        records: list[dict] = []
        try:
            events = self._fetch_events(season, week)
            for event in events:
                event_id = event.get("id", "")
                # Compute game-aware Thursday-open timestamp
                game_date = self._extract_game_date(event, game_dates)
                snapshot_date: str | None = None
                if game_date is not None:
                    snapshot_date = self._compute_thursday_open(game_date)

                event_props = self._fetch_event_props(event_id, snapshot_date)
                if not event_props:
                    continue

                parsed = self._parse_event_props(event_props, season, week)
                records.extend(parsed)

                # Rate limit: 0.5s between API calls (T-02-08)
                time.sleep(0.5)

        except Exception as exc:
            logger.warning("Failed to fetch props for %d week %d: %s", season, week, exc)
            return self._empty_df()

        if not records:
            return self._empty_df()

        df = pl.DataFrame(records, schema={
            "player_name": pl.Utf8,
            "market": pl.Utf8,
            "point": pl.Float64,
            "season": pl.Int64,
            "week": pl.Int64,
        })

        # Write cache
        df.write_parquet(cache_path)
        logger.info("Cached %d prop lines to %s", len(df), cache_path)
        return df

    # ------------------------------------------------------------------
    # Timing logic (game-aware Thursday-open)
    # ------------------------------------------------------------------

    def _compute_thursday_open(self, gameday: date) -> str:
        """Compute the Thursday-open snapshot timestamp for a game.

        Game-aware logic (addresses MEDIUM review concern T-02-11):
        - Thursday games: use Wednesday morning (gameday - 1)
        - All other games (Fri/Sat/Sun/Mon): use Thursday of game week at 12:00 ET

        This prevents look-ahead bias by using odds that were open before the
        game -- not closing lines, which contain information unavailable when
        projections are generated.

        Args:
            gameday: The date of the game.

        Returns:
            ISO 8601 timestamp string with ET offset.
        """
        weekday = gameday.weekday()  # 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat, 6=Sun

        if weekday == 3:
            # Thursday game: use Wednesday (gameday - 1)
            snapshot_day = gameday - timedelta(days=1)
        else:
            # All other games: use Thursday of game week
            # days_since_thursday: how many days back to reach the most recent Thursday
            days_since_thursday = (weekday - 3) % 7
            snapshot_day = gameday - timedelta(days=days_since_thursday)

        snapshot_dt = datetime(
            snapshot_day.year, snapshot_day.month, snapshot_day.day,
            12, 0, 0, tzinfo=_ET,
        )
        return snapshot_dt.strftime("%Y-%m-%dT%H:%M:%S%z")

    # ------------------------------------------------------------------
    # API helpers
    # ------------------------------------------------------------------

    def _fetch_events(self, season: int, week: int) -> list[dict]:
        """Fetch the list of NFL events for a given season/week.

        Returns a list of event dicts from The Odds API, or empty list on error.
        """
        url = f"{_API_BASE}/sports/americanfootball_nfl/events"
        params = {
            "apiKey": self._api_key,
            "dateFormat": "iso",
        }
        try:
            with httpx.Client(timeout=30) as client:
                resp = client.get(url, params=params)
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:
            logger.warning("Failed to fetch NFL events: %s", self._redact(str(exc)))
            return []

    def _fetch_event_props(
        self,
        event_id: str,
        snapshot_date: str | None = None,
    ) -> dict:
        """Fetch props for one event from The Odds API.

        Uses the historical endpoint when snapshot_date is provided,
        otherwise uses the live endpoint.

        Args:
            event_id: The Odds API event ID.
            snapshot_date: ISO 8601 timestamp for historical query (Thursday-open).

        Returns:
            Event props dict, or empty dict on HTTP error.
        """
        markets_param = ",".join(self.config.markets)

        if snapshot_date:
            url = f"{_API_BASE}/historical/sports/americanfootball_nfl/events/{event_id}/odds"
            params = {
                "apiKey": self._api_key,
                "markets": markets_param,
                "date": snapshot_date,
                "regions": "us",
                "oddsFormat": "american",
            }
        else:
            url = f"{_API_BASE}/sports/americanfootball_nfl/events/{event_id}/odds"
            params = {
                "apiKey": self._api_key,
                "markets": markets_param,
                "regions": "us",
                "oddsFormat": "american",
            }

        try:
            with httpx.Client(timeout=30) as client:
                resp = client.get(url, params=params)
                if resp.status_code in (429, 402):
                    logger.warning("API rate limit or quota exceeded (status %d)", resp.status_code)
                    return {}
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as exc:
            logger.warning("HTTP error fetching props for event %s: %s", event_id, self._redact(str(exc)))
            return {}
        except Exception as exc:
            logger.warning("Error fetching props for event %s: %s", event_id, self._redact(str(exc)))
            return {}

    def _parse_event_props(
        self,
        event_data: dict,
        season: int,
        week: int,
    ) -> list[dict]:
        """Parse event props JSON into flat records.

        Extracts player name, market, and consensus line (median across bookmakers).

        Args:
            event_data: Raw event dict from The Odds API.
            season: NFL season year.
            week: NFL week.

        Returns:
            List of record dicts with keys: player_name, market, point, season, week.
        """
        bookmakers = event_data.get("bookmakers", [])
        if not bookmakers:
            return []

        # Collect all lines per (player_name, market) across bookmakers
        lines: dict[tuple[str, str], list[float]] = {}

        for bm in bookmakers:
            for market in bm.get("markets", []):
                market_key = market.get("key", "")
                if market_key not in self.config.markets:
                    continue
                for outcome in market.get("outcomes", []):
                    player_name = outcome.get("name", "")
                    point = outcome.get("point")
                    if not player_name or point is None:
                        continue
                    key = (player_name, market_key)
                    if key not in lines:
                        lines[key] = []
                    lines[key].append(float(point))

        if not lines:
            return []

        records = []
        for (player_name, market_key), points in lines.items():
            # Use median for consensus line (robust to outliers)
            points_sorted = sorted(points)
            n = len(points_sorted)
            if n % 2 == 1:
                median_point = points_sorted[n // 2]
            else:
                median_point = (points_sorted[n // 2 - 1] + points_sorted[n // 2]) / 2.0

            records.append({
                "player_name": player_name,
                "market": market_key,
                "point": median_point,
                "season": season,
                "week": week,
            })

        return records

    def _extract_game_date(
        self,
        event: dict,
        game_dates: dict[str, date] | None,
    ) -> date | None:
        """Extract game date from event dict or game_dates lookup.

        Args:
            event: Event dict from The Odds API (may have 'commence_time').
            game_dates: Optional override dict.

        Returns:
            date object, or None if unavailable.
        """
        if game_dates:
            event_id = event.get("id", "")
            if event_id in game_dates:
                return game_dates[event_id]

        commence_time = event.get("commence_time")
        if commence_time:
            try:
                dt = datetime.fromisoformat(commence_time.replace("Z", "+00:00"))
                return dt.date()
            except (ValueError, AttributeError):
                pass

        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _empty_df() -> pl.DataFrame:
        """Return an empty DataFrame with the expected schema."""
        return pl.DataFrame(schema={
            "player_name": pl.Utf8,
            "market": pl.Utf8,
            "point": pl.Float64,
            "season": pl.Int64,
            "week": pl.Int64,
        })

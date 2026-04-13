from __future__ import annotations

import argparse
import time

from rich.console import Console

from fantasy_sim.data.loader import DataLoader
from fantasy_sim.data.market_history.events_inventory import (
    DEFAULT_DELAY_SECONDS,
    OddsApiAuthError,
    build_client,
    build_events_inventory_for_season,
    build_schedule_day_frame,
    fetch_historical_events_snapshot,
    load_the_odds_api_key,
    raw_snapshot_path,
    save_raw_snapshot,
)

console = Console()


def build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch historical NFL event ids from The Odds API and cache them locally."
    )
    parser.add_argument("--season", type=int, nargs="+", required=True)
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY_SECONDS)
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--rebuild-only",
        action="store_true",
        help="Skip network fetch and rebuild season inventory parquet from cached raw JSON.",
    )
    return parser


def main() -> int:
    args = build_cli().parse_args()

    loader = DataLoader()
    schedules = loader.load_schedules(args.season)
    season_days = build_schedule_day_frame(
        schedules.filter(
            (schedules["season"].is_in(args.season))
            & (schedules["game_type"] == "REG")
        )
    )

    if not args.rebuild_only:
        api_key = load_the_odds_api_key()
        if not api_key:
            console.print(
                "[red]Missing THE_ODDS_API_KEY/THE_ODDS_API.[/red] "
                "Set it in ~/.fantasy-sim/market-history/.env or your shell environment."
            )
            return 1

        client = build_client(api_key)
        try:
            for row in season_days.iter_rows(named=True):
                path = raw_snapshot_path(int(row["season"]), str(row["gameday"]))
                if path.exists() and not args.force:
                    console.print(f"[dim]skip[/dim] {path}")
                    continue

                payload = fetch_historical_events_snapshot(
                    client,
                    snapshot_date=str(row["snapshot_date"]),
                    commence_time_from=str(row["commence_time_from"]),
                    commence_time_to=str(row["commence_time_to"]),
                )
                save_raw_snapshot(
                    path,
                    season=int(row["season"]),
                    week=int(row["week"]),
                    gameday=str(row["gameday"]),
                    snapshot_date=str(row["snapshot_date"]),
                    commence_time_from=str(row["commence_time_from"]),
                    commence_time_to=str(row["commence_time_to"]),
                    payload=payload,
                )
                count = len(payload.get("data", []))
                console.print(
                    f"[green]saved[/green] season={row['season']} week={row['week']} "
                    f"gameday={row['gameday']} events={count}"
                )
                if args.delay > 0:
                    time.sleep(args.delay)
        except OddsApiAuthError as exc:
            console.print(f"[red]{exc}[/red]")
            return 1
        finally:
            client.close()

    for season in args.season:
        output_path = build_events_inventory_for_season(
            season,
            schedules=schedules.filter(schedules["season"] == season),
        )
        console.print(f"[blue]inventory[/blue] {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

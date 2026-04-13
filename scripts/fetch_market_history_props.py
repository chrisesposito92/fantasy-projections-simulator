from __future__ import annotations

import argparse
import time

from rich.console import Console

from fantasy_sim.data.market_history.events_inventory import (
    DEFAULT_DELAY_SECONDS,
    OddsApiAuthError,
    build_client,
    load_the_odds_api_key,
)
from fantasy_sim.data.market_history.props_backfill import (
    DEFAULT_PROP_MARKETS,
    build_snapshot_timestamp,
    fetch_historical_event_props,
    load_events_inventory,
    raw_props_path,
    save_raw_props_snapshot,
)

console = Console()


def build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch historical player props from The Odds API for cached NFL event inventory."
    )
    parser.add_argument("--season", type=int, nargs="+", required=True)
    parser.add_argument("--week", type=int, nargs="+")
    parser.add_argument("--markets", nargs="+", default=list(DEFAULT_PROP_MARKETS))
    parser.add_argument("--regions", default="us")
    parser.add_argument("--snapshot-label", default="close")
    parser.add_argument(
        "--date-source",
        choices=(
            "commence_time",
            "snapshot_date",
            "previous_snapshot_timestamp",
            "next_snapshot_timestamp",
        ),
        default="commence_time",
    )
    parser.add_argument("--offset-minutes", type=int, default=0)
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY_SECONDS)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    return parser


def main() -> int:
    args = build_cli().parse_args()

    api_key = load_the_odds_api_key()
    if not api_key:
        console.print(
            "[red]Missing THE_ODDS_API_KEY/THE_ODDS_API.[/red] "
            "Set it in ~/.fantasy-sim/market-history/.env or your shell environment."
        )
        return 1

    inventory = load_events_inventory(args.season, weeks=args.week)
    if inventory.is_empty():
        console.print(
            "[red]No cached event inventory found for the requested seasons/weeks.[/red] "
            "Run `scripts/fetch_market_history_events.py` first."
        )
        return 1

    if args.limit is not None:
        inventory = inventory.head(args.limit)

    client = build_client(api_key)
    try:
        for row in inventory.iter_rows(named=True):
            season = int(row["season"])
            event_id = str(row["event_id"])
            path = raw_props_path(
                season,
                event_id,
                snapshot_label=args.snapshot_label,
            )
            if path.exists() and not args.force:
                console.print(f"[dim]skip[/dim] {path}")
                continue

            snapshot_timestamp = build_snapshot_timestamp(
                row,
                date_source=args.date_source,
                offset_minutes=args.offset_minutes,
            )
            payload, headers = fetch_historical_event_props(
                client,
                event_id=event_id,
                date=snapshot_timestamp,
                markets=tuple(args.markets),
                regions=args.regions,
            )
            save_raw_props_snapshot(
                path,
                event_row=row,
                snapshot_label=args.snapshot_label,
                snapshot_timestamp=snapshot_timestamp,
                markets=tuple(args.markets),
                regions=args.regions,
                payload=payload,
                headers=headers,
            )
            bookmakers = len(payload.get("data", {}).get("bookmakers", []))
            console.print(
                f"[green]saved[/green] season={season} week={row['week']} "
                f"event={event_id} snapshot={args.snapshot_label} bookmakers={bookmakers} "
                f"cost={headers.get('x-requests-last')}"
            )
            if args.delay > 0:
                time.sleep(args.delay)
    except OddsApiAuthError as exc:
        console.print(f"[red]{exc}[/red]")
        return 1
    finally:
        client.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

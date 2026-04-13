from __future__ import annotations

import argparse

from fantasy_sim.data.market_history.player_markets import (
    build_player_market_signals_for_season,
)


def build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build processed player-week market signals from cached The Odds API raw props."
    )
    parser.add_argument("--season", type=int, nargs="+", required=True)
    parser.add_argument("--snapshot-label", default="close_core8")
    return parser


def main() -> int:
    args = build_cli().parse_args()
    for season in args.season:
        output_path = build_player_market_signals_for_season(
            season,
            snapshot_label=args.snapshot_label,
        )
        print(f"built {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

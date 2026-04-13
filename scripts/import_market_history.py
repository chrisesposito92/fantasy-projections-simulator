from __future__ import annotations

import argparse

from fantasy_sim.data.market_history.importer import build_market_history_cache


def build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build processed historical market-history parquet from raw week files."
    )
    parser.add_argument("--season", type=int, nargs="+", required=True)
    return parser


def main() -> int:
    args = build_cli().parse_args()
    for season in args.season:
        output_path = build_market_history_cache(season)
        print(f"built {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

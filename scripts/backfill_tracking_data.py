from __future__ import annotations

import argparse

from fantasy_sim.data.loader import DataLoader


def _season_type(value: str) -> int:
    season = int(value)
    if season < 2022:
        raise argparse.ArgumentTypeError("season must be 2022 or later")
    return season


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seasons", nargs="+", type=_season_type, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    loader = DataLoader()

    for season in args.seasons:
        print(f"[tracking] backfilling season {season}")
        loader.load_participation([season])
        print(f"[tracking] wrote participation_{season}.parquet")
        loader.load_ftn_charting([season])
        print(f"[tracking] wrote ftn_charting_{season}.parquet")
        loader.load_nextgen_stats([season], stat_type="passing")
        print(f"[tracking] wrote ngs_passing_{season}.parquet")
        loader.load_nextgen_stats([season], stat_type="rushing")
        print(f"[tracking] wrote ngs_rushing_{season}.parquet")


if __name__ == "__main__":
    main()

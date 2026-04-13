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


def _require_non_empty(df, feed_name: str, season: int) -> None:
    if df.is_empty():
        raise ValueError(f"{feed_name} backfill returned no rows for season {season}")


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    loader = DataLoader()

    for season in args.seasons:
        print(f"[tracking] backfilling season {season}")
        participation = loader.load_participation([season])
        _require_non_empty(participation, "participation", season)
        print(f"[tracking] wrote participation_{season}.parquet")
        ftn_charting = loader.load_ftn_charting([season])
        _require_non_empty(ftn_charting, "ftn_charting", season)
        print(f"[tracking] wrote ftn_charting_{season}.parquet")
        ngs_passing = loader.load_nextgen_stats([season], stat_type="passing")
        _require_non_empty(ngs_passing, "ngs_passing", season)
        print(f"[tracking] wrote ngs_passing_{season}.parquet")
        ngs_rushing = loader.load_nextgen_stats([season], stat_type="rushing")
        _require_non_empty(ngs_rushing, "ngs_rushing", season)
        print(f"[tracking] wrote ngs_rushing_{season}.parquet")


if __name__ == "__main__":
    main()

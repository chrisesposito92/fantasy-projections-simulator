#!/usr/bin/env python3
"""KS-13 D-10: probe FF Opportunity raw schema for lo/hi quantile columns.

Outputs JSON to stdout:
  {"path": "A" | "B", "lo_present": bool, "hi_present": bool, "non_null_fraction": float}

Path A: both columns present AND non_null_fraction >= 0.80 -> use quantile width
Path B: either missing OR non_null_fraction < 0.80 -> fit residual variance
"""

from __future__ import annotations

import argparse
import json
import sys

import polars as pl

from fantasy_sim.data.ensemble.loader import FfOpportunityLoader
from fantasy_sim.data.ensemble.models import FfOpportunityConfig


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe FF Opportunity raw schema for KS-13 lo/hi columns.")
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument(
        "--week",
        type=int,
        default=None,
        help=(
            "Optional week filter applied to the raw weekly frame after load. "
            "FfOpportunityLoader.load_weekly returns the full season; we filter "
            "to the requested week if provided. Omit for full-season probe."
        ),
    )
    parser.add_argument("--threshold", type=float, default=0.80, help="Non-null fraction required for Path A.")
    args = parser.parse_args()

    # Codex cycle-2 alignment (HIGH 2): the real loader API is
    # `FfOpportunityLoader(config: FfOpportunityConfig | None = None)` with
    # `load_weekly(seasons: list[int]) -> pl.DataFrame`. There is NO
    # `EnsembleLoader` and NO `load_week_raw(...)` — earlier drafts of this
    # plan invented those names. Verified against
    # `src/fantasy_sim/data/ensemble/loader.py` (current code surface).
    loader = FfOpportunityLoader(config=FfOpportunityConfig())

    try:
        df = loader.load_weekly([args.season])
    except Exception as exc:
        result = {
            "path": "B",
            "error": str(exc),
            "lo_present": False,
            "hi_present": False,
            "non_null_fraction": 0.0,
        }
        print(json.dumps(result), flush=True)
        return 0

    if not isinstance(df, pl.DataFrame) or df.is_empty():
        result = {
            "path": "B",
            "error": "empty_df",
            "lo_present": False,
            "hi_present": False,
            "non_null_fraction": 0.0,
        }
        print(json.dumps(result), flush=True)
        return 0

    if args.week is not None and "week" in df.columns:
        df = df.filter(pl.col("week") == args.week)
        if df.is_empty():
            result = {
                "path": "B",
                "error": f"empty_week_filter season={args.season} week={args.week}",
                "lo_present": False,
                "hi_present": False,
                "non_null_fraction": 0.0,
            }
            print(json.dumps(result), flush=True)
            return 0

    cols = set(df.columns)
    lo_present = "total_fantasy_points_exp_lo" in cols
    hi_present = "total_fantasy_points_exp_hi" in cols

    if not (lo_present and hi_present):
        result = {
            "path": "B",
            "lo_present": lo_present,
            "hi_present": hi_present,
            "non_null_fraction": 0.0,
        }
        print(json.dumps(result), flush=True)
        return 0

    lo_non_null = df.filter(pl.col("total_fantasy_points_exp_lo").is_not_null()).height
    hi_non_null = df.filter(pl.col("total_fantasy_points_exp_hi").is_not_null()).height
    total = df.height
    fraction = min(lo_non_null, hi_non_null) / total if total > 0 else 0.0

    path = "A" if fraction >= args.threshold else "B"
    result = {
        "path": path,
        "lo_present": lo_present,
        "hi_present": hi_present,
        "non_null_fraction": round(fraction, 4),
        "rows": total,
    }
    print(json.dumps(result), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

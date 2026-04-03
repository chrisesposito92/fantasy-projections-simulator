"""Fit PFF → PBP talent coefficients via OLS regression.

Uses year-N PFF features to predict year-N+1 PBP outcomes, fitting
the coefficients that the TalentStabilizer uses for its priors.

Usage:
    uv run python scripts/fit_talent_coefficients.py
    uv run python scripts/fit_talent_coefficients.py --apply
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import NamedTuple

import numpy as np
import polars as pl

# Allow running from the repo root without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from fantasy_sim.data.loader import DataLoader
from fantasy_sim.data.pff.loader import PffLoader


# ---------------------------------------------------------------------------
# PBP outcome extraction
# ---------------------------------------------------------------------------

def extract_pbp_catch_rates(
    pbp: pl.DataFrame,
    min_targets: int = 30,
) -> dict[str, float]:
    """Compute per-player catch rate from play-by-play data.

    Filters to pass attempts (pass_attempt==1) excluding sacks (sack==0)
    and plays with a non-null receiver_player_id.

    Args:
        pbp: Play-by-play DataFrame with columns:
             pass_attempt, sack, complete_pass, receiver_player_id.
        min_targets: Minimum number of targets required to include a player.

    Returns:
        Dict mapping receiver_player_id -> catch_rate.
    """
    filtered = pbp.filter(
        (pl.col("pass_attempt") == 1)
        & (pl.col("sack") == 0)
        & (pl.col("receiver_player_id").is_not_null())
    )

    if filtered.is_empty():
        return {}

    agg = filtered.group_by("receiver_player_id").agg([
        pl.len().alias("targets"),
        pl.col("complete_pass").sum().alias("catches"),
    ])

    agg = agg.filter(pl.col("targets") >= min_targets)

    result: dict[str, float] = {}
    for row in agg.iter_rows(named=True):
        player_id = row["receiver_player_id"]
        if player_id is not None:
            result[str(player_id)] = row["catches"] / row["targets"]

    return result


def extract_pbp_yards_per_catch(
    pbp: pl.DataFrame,
    min_catches: int = 20,
) -> dict[str, float]:
    """Compute per-player receiving yards per completion from PBP data.

    Filters to complete passes (complete_pass==1) with a non-null
    receiver_player_id.

    Args:
        pbp: Play-by-play DataFrame with columns:
             complete_pass, yards_gained, receiver_player_id.
        min_catches: Minimum completions required to include a player.

    Returns:
        Dict mapping receiver_player_id -> mean yards per completion.
    """
    filtered = pbp.filter(
        (pl.col("complete_pass") == 1)
        & (pl.col("receiver_player_id").is_not_null())
    )

    if filtered.is_empty():
        return {}

    agg = filtered.group_by("receiver_player_id").agg([
        pl.len().alias("catches"),
        pl.col("yards_gained").mean().alias("yards_per_catch"),
    ])

    agg = agg.filter(pl.col("catches") >= min_catches)

    result: dict[str, float] = {}
    for row in agg.iter_rows(named=True):
        player_id = row["receiver_player_id"]
        if player_id is not None:
            result[str(player_id)] = float(row["yards_per_catch"])

    return result


def extract_pbp_yards_per_carry(
    pbp: pl.DataFrame,
    min_carries: int = 30,
) -> dict[str, float]:
    """Compute per-player rushing yards per carry from PBP data.

    Filters to rush attempts (rush_attempt==1) with a non-null
    rusher_player_id.

    Args:
        pbp: Play-by-play DataFrame with columns:
             rush_attempt, yards_gained, rusher_player_id.
        min_carries: Minimum carries required to include a player.

    Returns:
        Dict mapping rusher_player_id -> mean yards per carry.
    """
    filtered = pbp.filter(
        (pl.col("rush_attempt") == 1)
        & (pl.col("rusher_player_id").is_not_null())
    )

    if filtered.is_empty():
        return {}

    agg = filtered.group_by("rusher_player_id").agg([
        pl.len().alias("carries"),
        pl.col("yards_gained").mean().alias("yards_per_carry"),
    ])

    agg = agg.filter(pl.col("carries") >= min_carries)

    result: dict[str, float] = {}
    for row in agg.iter_rows(named=True):
        player_id = row["rusher_player_id"]
        if player_id is not None:
            result[str(player_id)] = float(row["yards_per_carry"])

    return result


# ---------------------------------------------------------------------------
# OLS regression
# ---------------------------------------------------------------------------

def fit_ols(
    X: np.ndarray,
    y: np.ndarray,
) -> tuple[float, np.ndarray, float]:
    """Fit ordinary least squares regression.

    Args:
        X: Feature matrix of shape (n_samples, n_features).
        y: Target vector of shape (n_samples,).

    Returns:
        Tuple of (intercept, coefficients, r_squared).
        - intercept: float
        - coefficients: np.ndarray of shape (n_features,)
        - r_squared: float in [0, 1]
    """
    n = X.shape[0]
    # Add intercept column
    X_aug = np.column_stack([np.ones(n), X])

    # Solve via least squares
    params, _, _, _ = np.linalg.lstsq(X_aug, y, rcond=None)
    intercept = float(params[0])
    coefficients = params[1:]

    # Compute R²
    y_pred = X_aug @ params
    ss_res = float(np.sum((y - y_pred) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

    return intercept, coefficients, r_squared


def cross_validate_ols(
    X: np.ndarray,
    y: np.ndarray,
    folds: list[np.ndarray],
) -> float:
    """Leave-one-fold-out cross-validation for OLS.

    For each fold, trains on the union of all other folds and predicts
    on the held-out fold. Returns mean absolute error across all folds.

    Args:
        X: Feature matrix of shape (n_samples, n_features).
        y: Target vector of shape (n_samples,).
        folds: List of index arrays, one per fold.

    Returns:
        Mean absolute error averaged across all held-out predictions.
    """
    all_errors: list[float] = []

    for i, val_idx in enumerate(folds):
        # Train on all other folds
        train_idx = np.concatenate([f for j, f in enumerate(folds) if j != i])

        X_train, y_train = X[train_idx], y[train_idx]
        X_val, y_val = X[val_idx], y[val_idx]

        intercept, coeffs, _ = fit_ols(X_train, y_train)

        # Predict on validation fold
        y_pred = intercept + X_val @ coeffs
        errors = np.abs(y_val - y_pred)
        all_errors.extend(errors.tolist())

    return float(np.mean(all_errors)) if all_errors else 0.0


# ---------------------------------------------------------------------------
# Dataset builders
# ---------------------------------------------------------------------------

class Dataset(NamedTuple):
    X: np.ndarray
    y: np.ndarray
    feature_names: list[str]
    pair_label: str  # e.g. "2022→2023"


def build_catch_rate_dataset(
    pff_loader: PffLoader,
    data_loader: DataLoader,
    pff_season: int,
    pbp_season: int,
) -> Dataset | None:
    """Build a catch rate regression dataset.

    PFF year-N features → PBP year-N+1 catch rates.

    Features:
      X0 = (league_avg_drop_rate - player_drop_rate) * 0.01
      X1 = (player_contested_catch_rate - league_avg_contested) * 0.01
      X2 = (team_qb_accuracy - league_avg_accuracy) * 0.01

    Args:
        pff_loader: Loaded PffLoader instance.
        data_loader: DataLoader for PBP.
        pff_season: Season to load PFF features from.
        pbp_season: Season to load PBP targets from.

    Returns:
        Dataset namedtuple or None if insufficient data.
    """
    # Load PFF receiving summary for pff_season
    recv = pff_loader.aggregate_player_stats("receiving_summary", [pff_season])
    passing = pff_loader.aggregate_player_stats("passing_summary", [pff_season])

    if recv.is_empty():
        print(f"  [catch_rate] No PFF receiving data for {pff_season}, skipping.")
        return None

    # League averages
    def _col_mean(df: pl.DataFrame, col: str, default: float = 0.0) -> float:
        if col not in df.columns or df.is_empty():
            return default
        val = df.select(pl.col(col).mean()).item()
        return float(val) if val is not None else default

    avg_drop = _col_mean(recv, "drop_rate")
    avg_contested = _col_mean(recv, "contested_catch_rate")
    avg_accuracy = _col_mean(passing, "accuracy_percent", default=75.0)

    # Per-team QB accuracy
    team_qb_accuracy: dict[str, float] = {}
    if not passing.is_empty() and "accuracy_percent" in passing.columns:
        qbs = passing.filter(pl.col("position") == "QB") if "position" in passing.columns else passing
        if not qbs.is_empty() and "team" in qbs.columns:
            for row in qbs.iter_rows(named=True):
                team = row.get("team")
                acc = row.get("accuracy_percent")
                if team and acc is not None:
                    team_qb_accuracy[team] = float(acc)

    # Build crosswalk for pff_season to map PFF player_id → nflverse player_id
    try:
        rosters = data_loader.load_rosters([pbp_season])
    except Exception as e:
        print(f"  [catch_rate] Could not load rosters for {pbp_season}: {e}")
        return None

    crosswalk = pff_loader.build_crosswalk(recv, rosters, pff_season)
    if not crosswalk:
        print(f"  [catch_rate] Empty crosswalk for {pff_season}, skipping.")
        return None

    # PBP outcomes for pbp_season
    try:
        pbp = data_loader.load_pbp([pbp_season])
    except Exception as e:
        print(f"  [catch_rate] Could not load PBP for {pbp_season}: {e}")
        return None

    pbp_rates = extract_pbp_catch_rates(pbp, min_targets=30)

    # Build PFF lookup keyed by PFF player_id
    recv_lookup: dict[int, dict] = {}
    for row in recv.iter_rows(named=True):
        pid = row.get("player_id")
        if pid is not None:
            recv_lookup[int(pid)] = row

    rows_X: list[list[float]] = []
    rows_y: list[float] = []

    for pff_id, nflverse_id in crosswalk.items():
        if nflverse_id not in pbp_rates:
            continue
        if pff_id not in recv_lookup:
            continue

        pff_row = recv_lookup[pff_id]
        player_drop = float(pff_row.get("drop_rate") or 0.0)
        player_contested = float(pff_row.get("contested_catch_rate") or 0.0)
        team = str(pff_row.get("team") or "")
        qb_acc = team_qb_accuracy.get(team, avg_accuracy)

        x0 = (avg_drop - player_drop) * 0.01
        x1 = (player_contested - avg_contested) * 0.01
        x2 = (qb_acc - avg_accuracy) * 0.01

        rows_X.append([x0, x1, x2])
        rows_y.append(pbp_rates[nflverse_id])

    if len(rows_y) < 5:
        print(f"  [catch_rate] Only {len(rows_y)} matched players for {pff_season}→{pbp_season}, skipping.")
        return None

    return Dataset(
        X=np.array(rows_X, dtype=float),
        y=np.array(rows_y, dtype=float),
        feature_names=["drop_rate", "contested_catch_rate", "qb_accuracy"],
        pair_label=f"{pff_season}→{pbp_season}",
    )


def build_receiving_yards_dataset(
    pff_loader: PffLoader,
    data_loader: DataLoader,
    pff_season: int,
    pbp_season: int,
) -> Dataset | None:
    """Build a receiving yards-per-catch regression dataset.

    PFF year-N features → PBP year-N+1 yards per completion.

    Features:
      X0 = player_yprr - avg_yprr
      X1 = player_adot - avg_adot

    Args:
        pff_loader: Loaded PffLoader instance.
        data_loader: DataLoader for PBP.
        pff_season: Season to load PFF features from.
        pbp_season: Season to load PBP targets from.

    Returns:
        Dataset namedtuple or None if insufficient data.
    """
    recv = pff_loader.aggregate_player_stats("receiving_summary", [pff_season])

    if recv.is_empty():
        print(f"  [recv_yards] No PFF receiving data for {pff_season}, skipping.")
        return None

    def _col_mean(df: pl.DataFrame, col: str, default: float = 0.0) -> float:
        if col not in df.columns or df.is_empty():
            return default
        val = df.select(pl.col(col).mean()).item()
        return float(val) if val is not None else default

    avg_yprr = _col_mean(recv, "yprr")
    avg_adot = _col_mean(recv, "avg_depth_of_target")

    try:
        rosters = data_loader.load_rosters([pbp_season])
    except Exception as e:
        print(f"  [recv_yards] Could not load rosters for {pbp_season}: {e}")
        return None

    crosswalk = pff_loader.build_crosswalk(recv, rosters, pff_season)
    if not crosswalk:
        print(f"  [recv_yards] Empty crosswalk for {pff_season}, skipping.")
        return None

    try:
        pbp = data_loader.load_pbp([pbp_season])
    except Exception as e:
        print(f"  [recv_yards] Could not load PBP for {pbp_season}: {e}")
        return None

    pbp_ypc = extract_pbp_yards_per_catch(pbp, min_catches=20)

    recv_lookup: dict[int, dict] = {}
    for row in recv.iter_rows(named=True):
        pid = row.get("player_id")
        if pid is not None:
            recv_lookup[int(pid)] = row

    rows_X: list[list[float]] = []
    rows_y: list[float] = []

    for pff_id, nflverse_id in crosswalk.items():
        if nflverse_id not in pbp_ypc:
            continue
        if pff_id not in recv_lookup:
            continue

        pff_row = recv_lookup[pff_id]
        player_yprr = float(pff_row.get("yprr") or 0.0)
        player_adot = float(pff_row.get("avg_depth_of_target") or 0.0)

        x0 = player_yprr - avg_yprr
        x1 = player_adot - avg_adot

        rows_X.append([x0, x1])
        rows_y.append(pbp_ypc[nflverse_id])

    if len(rows_y) < 5:
        print(f"  [recv_yards] Only {len(rows_y)} matched players for {pff_season}→{pbp_season}, skipping.")
        return None

    return Dataset(
        X=np.array(rows_X, dtype=float),
        y=np.array(rows_y, dtype=float),
        feature_names=["yprr", "avg_depth_of_target"],
        pair_label=f"{pff_season}→{pbp_season}",
    )


def build_rushing_yards_dataset(
    pff_loader: PffLoader,
    data_loader: DataLoader,
    pff_season: int,
    pbp_season: int,
) -> Dataset | None:
    """Build a rushing yards-per-carry regression dataset.

    PFF year-N features → PBP year-N+1 yards per carry.

    Features:
      X0 = player_yco - avg_yco
      X1 = player_elusive - avg_elusive

    Args:
        pff_loader: Loaded PffLoader instance.
        data_loader: DataLoader for PBP.
        pff_season: Season to load PFF features from.
        pbp_season: Season to load PBP targets from.

    Returns:
        Dataset namedtuple or None if insufficient data.
    """
    rushing = pff_loader.aggregate_player_stats("rushing_summary", [pff_season])

    if rushing.is_empty():
        print(f"  [rush_yards] No PFF rushing data for {pff_season}, skipping.")
        return None

    def _col_mean(df: pl.DataFrame, col: str, default: float = 0.0) -> float:
        if col not in df.columns or df.is_empty():
            return default
        val = df.select(pl.col(col).mean()).item()
        return float(val) if val is not None else default

    avg_yco = _col_mean(rushing, "yco_attempt")
    avg_elusive = _col_mean(rushing, "elusive_rating")

    try:
        rosters = data_loader.load_rosters([pbp_season])
    except Exception as e:
        print(f"  [rush_yards] Could not load rosters for {pbp_season}: {e}")
        return None

    crosswalk = pff_loader.build_crosswalk(rushing, rosters, pff_season)
    if not crosswalk:
        print(f"  [rush_yards] Empty crosswalk for {pff_season}, skipping.")
        return None

    try:
        pbp = data_loader.load_pbp([pbp_season])
    except Exception as e:
        print(f"  [rush_yards] Could not load PBP for {pbp_season}: {e}")
        return None

    pbp_ypc = extract_pbp_yards_per_carry(pbp, min_carries=30)

    rush_lookup: dict[int, dict] = {}
    for row in rushing.iter_rows(named=True):
        pid = row.get("player_id")
        if pid is not None:
            rush_lookup[int(pid)] = row

    rows_X: list[list[float]] = []
    rows_y: list[float] = []

    for pff_id, nflverse_id in crosswalk.items():
        if nflverse_id not in pbp_ypc:
            continue
        if pff_id not in rush_lookup:
            continue

        pff_row = rush_lookup[pff_id]
        player_yco = float(pff_row.get("yco_attempt") or 0.0)
        player_elusive = float(pff_row.get("elusive_rating") or 0.0)

        x0 = player_yco - avg_yco
        x1 = player_elusive - avg_elusive

        rows_X.append([x0, x1])
        rows_y.append(pbp_ypc[nflverse_id])

    if len(rows_y) < 5:
        print(f"  [rush_yards] Only {len(rows_y)} matched players for {pff_season}→{pbp_season}, skipping.")
        return None

    return Dataset(
        X=np.array(rows_X, dtype=float),
        y=np.array(rows_y, dtype=float),
        feature_names=["yco_attempt", "elusive_rating"],
        pair_label=f"{pff_season}→{pbp_season}",
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

SEASON_PAIRS = [(2022, 2023), (2023, 2024)]

DATASET_BUILDERS = {
    "catch_rate": build_catch_rate_dataset,
    "receiving_yards": build_receiving_yards_dataset,
    "rushing_yards": build_rushing_yards_dataset,
}


def _print_separator(char: str = "-", width: int = 68) -> None:
    print(char * width)


def _run_metric(
    metric_name: str,
    build_fn,
    pff_loader: PffLoader,
    data_loader: DataLoader,
    season_pairs: list[tuple[int, int]],
) -> None:
    """Collect datasets across season pairs, fit OLS, and print results."""
    print(f"\n{'=' * 68}")
    print(f"  {metric_name.upper()}")
    print("=" * 68)

    datasets: list[Dataset] = []
    for pff_season, pbp_season in season_pairs:
        print(f"  Building dataset: {pff_season} PFF → {pbp_season} PBP ...")
        ds = build_fn(pff_loader, data_loader, pff_season, pbp_season)
        if ds is not None:
            datasets.append(ds)
            print(f"    {len(ds.y)} players matched")

    if not datasets:
        print("  No data available — skipping.")
        return

    # Concatenate all pairs
    X_all = np.vstack([ds.X for ds in datasets])
    y_all = np.concatenate([ds.y for ds in datasets])
    feature_names = datasets[0].feature_names

    print(f"\n  Combined: {len(y_all)} samples, {X_all.shape[1]} features")
    _print_separator()

    # Fit on combined data
    intercept, coeffs, r_sq = fit_ols(X_all, y_all)
    print(f"  Intercept : {intercept:.6f}")
    for fname, coeff in zip(feature_names, coeffs):
        print(f"  {fname:<30}: {coeff:.6f}")
    print(f"  R²        : {r_sq:.4f}")

    # Cross-validate (leave-one-pair-out)
    if len(datasets) >= 2:
        _print_separator()
        # Build fold index arrays on the combined data
        folds: list[np.ndarray] = []
        offset = 0
        for ds in datasets:
            n = len(ds.y)
            folds.append(np.arange(offset, offset + n))
            offset += n

        cv_mae = cross_validate_ols(X_all, y_all, folds)
        print(f"  CV MAE (leave-one-pair-out): {cv_mae:.4f}")
    else:
        print("  CV skipped (only 1 season pair available).")

    _print_separator()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Fit PFF → PBP talent coefficients via OLS regression.\n\n"
            "For each metric (catch_rate, receiving_yards, rushing_yards),\n"
            "pairs year-N PFF features with year-N+1 PBP outcomes and fits\n"
            "coefficients using ordinary least squares.\n\n"
            "Requires PFF parquet data in ~/.fantasy-sim/pff/processed/nfl/\n"
            "and cached PBP data in ~/.fantasy-sim/cache/."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "After printing fitted coefficients, print instructions for "
            "updating config/defaults.yaml with the new values."
        ),
    )
    parser.add_argument(
        "--pff-dir",
        type=Path,
        default=None,
        dest="pff_dir",
        metavar="PATH",
        help="Path to PFF processed parquet directory (default: ~/.fantasy-sim/pff/processed/nfl/).",
    )
    args = parser.parse_args()

    pff_loader = PffLoader(pff_dir=args.pff_dir)
    data_loader = DataLoader()

    if not pff_loader.is_available():
        print(
            "ERROR: No PFF data found in "
            f"{pff_loader.pff_dir}\n"
            "Run scripts/scrape_pff.py first. See docs/pff-setup.md for details."
        )
        return 1

    print("=" * 68)
    print("  PFF → PBP TALENT COEFFICIENT FITTER")
    print("=" * 68)
    print(f"  PFF dir   : {pff_loader.pff_dir}")
    print(f"  Pairs     : {', '.join(f'{a}→{b}' for a, b in SEASON_PAIRS)}")
    print("=" * 68)

    for metric_name, build_fn in DATASET_BUILDERS.items():
        _run_metric(metric_name, build_fn, pff_loader, data_loader, SEASON_PAIRS)

    if args.apply:
        print("\n" + "=" * 68)
        print("  HOW TO APPLY FITTED COEFFICIENTS")
        print("=" * 68)
        print("""
  Open config/defaults.yaml and update the `pff.talent` section:

  pff:
    talent:
      catch_rate_coefficients:
        drop_rate: <fitted value for drop_rate>
        contested_catch_rate: <fitted value for contested_catch_rate>
        qb_accuracy: <fitted value for qb_accuracy>
      receiving_yards_coefficients:
        yprr: <fitted value for yprr>
        avg_depth_of_target: <fitted value for avg_depth_of_target>
      rushing_yards_coefficients:
        yco_attempt: <fitted value for yco_attempt>
        elusive_rating: <fitted value for elusive_rating>

  Replace each <fitted value> with the coefficient printed above.
  The intercept is absorbed into the BASELINE_CATCH_RATE constant
  in src/fantasy_sim/data/pff/talent.py (currently 0.64).
""")

    return 0


if __name__ == "__main__":
    sys.exit(main())

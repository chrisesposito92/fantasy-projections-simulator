"""PFF data loader and player ID crosswalk builder.

Reads processed PFF parquet files from ~/.fantasy-sim/pff/processed/nfl/
and builds a mapping from PFF player_id (int) to nflverse player_id (str).
"""

from __future__ import annotations

import logging
from pathlib import Path

import polars as pl

logger = logging.getLogger(__name__)

DEFAULT_PFF_DIR = Path.home() / ".fantasy-sim" / "pff" / "processed" / "nfl"
DEFAULT_NCAA_DIR = Path.home() / ".fantasy-sim" / "pff" / "processed" / "ncaa"

# PFF uses non-standard team abbreviations for 4 teams
PFF_TO_NFL_TEAM: dict[str, str] = {
    "ARZ": "ARI",
    "BLT": "BAL",
    "CLV": "CLE",
    "HST": "HOU",
}

# PFF positions → standard fantasy positions
PFF_TO_FANTASY_POSITION: dict[str, str] = {
    "LWR": "WR",
    "RWR": "WR",
    "SLWR": "WR",
    "SRWR": "WR",
    "HB": "RB",
    "FB": "RB",
    "TE-L": "TE",
    "TE-R": "TE",
    "QB": "QB",
}

# Fantasy-relevant positions for crosswalk matching
FANTASY_POSITIONS = {"QB", "RB", "WR", "TE"}


class PffLoader:
    """Loads processed PFF parquet data and builds player ID crosswalks."""

    def __init__(self, pff_dir: Path | None = None):
        self.pff_dir = pff_dir or DEFAULT_PFF_DIR
        self._crosswalk_cache: dict[int, dict[int, str]] = {}

    def is_available(self) -> bool:
        """Check if PFF data directory exists and contains parquet files."""
        if not self.pff_dir.exists():
            return False
        return any(self.pff_dir.glob("*.parquet"))

    def load_facet(
        self, facet: str, seasons: list[int]
    ) -> pl.DataFrame:
        """Read and concatenate {facet}_{season}.parquet files.

        Normalizes team abbreviations and maps positions to fantasy positions.
        Returns empty DataFrame if no data found.
        """
        frames = []
        for season in seasons:
            path = self.pff_dir / f"{facet}_{season}.parquet"
            if not path.exists():
                logger.warning("PFF file not found: %s", path)
                continue
            df = pl.read_parquet(path)
            frames.append(df)

        if not frames:
            return pl.DataFrame()

        combined = pl.concat(frames, how="diagonal_relaxed")

        # Normalize team abbreviations
        if "team" in combined.columns:
            combined = combined.with_columns(
                pl.col("team").replace(PFF_TO_NFL_TEAM)
            )

        # Map positions to fantasy positions (keep original in pff_position)
        if "position" in combined.columns:
            combined = combined.with_columns(
                pl.col("position").alias("pff_position"),
                pl.col("position").replace(PFF_TO_FANTASY_POSITION).alias("position"),
            )

        return combined

    def aggregate_player_stats(
        self,
        facet: str,
        seasons: list[int],
        season_weights: dict[int, float] | None = None,
    ) -> pl.DataFrame:
        """Aggregate game-level PFF data to per-player summaries.

        Computes weighted means across games. If season_weights is provided,
        games from higher-weight seasons contribute more.
        """
        df = self.load_facet(facet, seasons)
        if df.is_empty():
            return df

        # Identify numeric columns for aggregation (exclude metadata)
        meta_cols = {
            "player_id", "player", "team", "position", "pff_position",
            "season", "week", "game_id", "franchise_id", "jersey_number",
            "status",
        }
        numeric_cols = [
            c for c in df.columns
            if c not in meta_cols and df[c].dtype in (pl.Float64, pl.Int64, pl.Float32, pl.Int32)
        ]

        if not numeric_cols:
            return pl.DataFrame()

        # Apply season weights via weight column
        if season_weights and "season" in df.columns:
            weight_expr = pl.lit(1.0)
            for s, w in season_weights.items():
                weight_expr = pl.when(pl.col("season") == s).then(pl.lit(w)).otherwise(weight_expr)
            df = df.with_columns(weight_expr.alias("_weight"))
        else:
            df = df.with_columns(pl.lit(1.0).alias("_weight"))

        # Weighted mean per player
        agg_exprs = [
            (pl.col(c) * pl.col("_weight")).sum() / pl.col("_weight").sum()
            for c in numeric_cols
        ]
        agg_exprs.extend([
            pl.col("player").first(),
            pl.col("team").last(),  # most recent team
            pl.col("position").first(),
            pl.col("_weight").sum().alias("total_weight"),
            pl.len().alias("games"),
        ])

        result = df.group_by("player_id").agg(agg_exprs)
        return result.rename({c: c for c in result.columns})

    def build_crosswalk(
        self,
        pff_data: pl.DataFrame,
        roster: pl.DataFrame,
        season: int,
    ) -> dict[int, str]:
        """Map PFF player_id (int) → nflverse player_id (str).

        Layer 1: nflverse pff_id → player_id (gsis_id) direct match.
        Layer 2: Exact name + team match for remaining players.

        Args:
            pff_data: PFF DataFrame with player_id, player, team columns.
            roster: nflverse roster DataFrame (from DataLoader.load_rosters).
                    Expected columns: player_id (gsis_id), player_name (full_name),
                    team, position, pff_id.
            season: Season year (for caching).

        Returns:
            Dict mapping PFF player_id (int) to nflverse player_id (str).
        """
        if season in self._crosswalk_cache:
            return self._crosswalk_cache[season]

        crosswalk: dict[int, str] = {}

        # Get unique PFF players
        pff_players = pff_data.select(
            ["player_id", "player", "team"]
        ).unique(subset=["player_id"])

        if pff_players.is_empty() or roster.is_empty():
            self._crosswalk_cache[season] = crosswalk
            return crosswalk

        # --- Layer 1: pff_id direct match ---
        # Roster may have pff_id column (renamed from nflverse raw)
        pff_id_col = "pff_id" if "pff_id" in roster.columns else None

        if pff_id_col:
            roster_with_pff = (
                roster
                .filter(pl.col(pff_id_col).is_not_null())
                .with_columns(
                    pl.col(pff_id_col).cast(pl.Utf8).cast(pl.Int64, strict=False).alias("_pff_id_int")
                )
                .filter(pl.col("_pff_id_int").is_not_null())
                .select(["player_id", "_pff_id_int"])
                .unique(subset=["_pff_id_int"])
            )

            matched = pff_players.join(
                roster_with_pff,
                left_on="player_id",
                right_on="_pff_id_int",
                how="inner",
            )

            for row in matched.iter_rows(named=True):
                crosswalk[row["player_id"]] = row["player_id_right"]

        layer1_count = len(crosswalk)

        # --- Layer 2: exact name + team match ---
        unmatched_pff = pff_players.filter(
            ~pl.col("player_id").is_in(list(crosswalk.keys()))
        )

        if not unmatched_pff.is_empty():
            # Roster name + team lookup
            roster_lookup = (
                roster
                .filter(pl.col("position").is_in(list(FANTASY_POSITIONS)))
                .select(["player_id", "player_name", "team"])
                .unique(subset=["player_id"])
            )

            name_matched = unmatched_pff.join(
                roster_lookup,
                left_on=["player", "team"],
                right_on=["player_name", "team"],
                how="inner",
            )

            for row in name_matched.iter_rows(named=True):
                crosswalk[row["player_id"]] = row["player_id_right"]

        layer2_count = len(crosswalk) - layer1_count
        total = pff_players.height
        coverage = len(crosswalk) / total * 100 if total > 0 else 0

        logger.info(
            "PFF crosswalk %d: %d/%d matched (%.0f%%) — Layer 1: %d, Layer 2: %d",
            season, len(crosswalk), total, coverage, layer1_count, layer2_count,
        )

        self._crosswalk_cache[season] = crosswalk
        return crosswalk

    def load_ncaa_facet(
        self,
        facet: str,
        seasons: list[int],
        ncaa_dir: Path | None = None,
    ) -> pl.DataFrame:
        """Load NCAA PFF facet data from the NCAA directory.

        Unlike :meth:`load_facet`, this does **not** normalise team
        abbreviations or map positions (NCAA teams/positions are different
        from NFL).

        Args:
            facet: PFF facet name (e.g. ``"receiving_summary"``).
            seasons: List of seasons to load.
            ncaa_dir: Override directory; defaults to
                ``~/.fantasy-sim/pff/processed/ncaa/``.

        Returns:
            Concatenated DataFrame, or empty DataFrame if no data found.
        """
        target_dir = ncaa_dir or DEFAULT_NCAA_DIR
        frames: list[pl.DataFrame] = []
        for season in seasons:
            path = target_dir / f"{facet}_{season}.parquet"
            if not path.exists():
                logger.warning("NCAA PFF file not found: %s", path)
                continue
            frames.append(pl.read_parquet(path))

        if not frames:
            return pl.DataFrame()

        return pl.concat(frames, how="diagonal_relaxed")

    def build_ncaa_crosswalk(
        self,
        ncaa_data: pl.DataFrame,
        nfl_roster: pl.DataFrame,
        rookie_season: int,
    ) -> dict[int, str]:
        """Map NCAA PFF player_id -> NFL player_id.

        Matches by player name + college name for players whose
        ``rookie_year`` (or ``season``) equals *rookie_season*.

        Args:
            ncaa_data: NCAA PFF DataFrame with ``player_id``, ``player``,
                ``team`` (college name) columns.
            nfl_roster: nflverse roster DataFrame with ``player_id``,
                ``player_name``, ``college_name``, and optionally
                ``rookie_year`` / ``season`` columns.
            rookie_season: Target NFL season year — only roster entries
                whose ``rookie_year`` (or ``season``) matches are
                considered.

        Returns:
            Dict mapping NCAA PFF player_id (int) to nflverse player_id
            (str).
        """
        crosswalk: dict[int, str] = {}

        ncaa_players = ncaa_data.select(
            ["player_id", "player", "team"]
        ).unique(subset=["player_id"])

        if ncaa_players.is_empty() or nfl_roster.is_empty():
            return crosswalk

        # Filter roster to target season
        rookies = nfl_roster
        if "rookie_year" in rookies.columns:
            rookies = rookies.filter(pl.col("rookie_year") == rookie_season)
        elif "season" in rookies.columns:
            rookies = rookies.filter(pl.col("season") == rookie_season)

        if rookies.is_empty():
            return crosswalk

        if "college_name" not in rookies.columns:
            logger.debug("No college_name column in roster — skipping NCAA crosswalk")
            return crosswalk

        # Match by name + college
        roster_lookup = rookies.select([
            "player_id", "player_name", "college_name",
        ]).unique(subset=["player_id"])

        matched = ncaa_players.join(
            roster_lookup,
            left_on=["player", "team"],
            right_on=["player_name", "college_name"],
            how="inner",
        )

        for row in matched.iter_rows(named=True):
            crosswalk[row["player_id"]] = row["player_id_right"]

        logger.info(
            "NCAA crosswalk: %d/%d matched",
            len(crosswalk), ncaa_players.height,
        )
        return crosswalk

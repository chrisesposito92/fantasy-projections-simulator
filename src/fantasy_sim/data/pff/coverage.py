"""Coverage engine — builds CB profiles from PFF coverage matchup data.

Uses the defense_coverage_matchup facet which contains two row types:
- Type 1 (coverage_player_id IS NULL): per-game player aggregates
- Type 2 (coverage_player_id IS NOT NULL): per-matchup-pair rows

CB profiles aggregate Type 2 matchup stats for each starting CB
(identified from Type 1 rows by alignment and target volume).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import polars as pl

from fantasy_sim.data.pff.loader import PffLoader
from fantasy_sim.data.pff.models import CoverageConfig

logger = logging.getLogger(__name__)

# CB alignment positions in PFF data (Type 1 rows)
CB_ALIGNMENTS = {"LCB", "RCB", "SCB"}

# Maps WR alignment to the CB alignment they typically face
_ALIGNMENT_MAP = {"RWR": "LCB", "LWR": "RCB", "SLWR": "SCB", "SRWR": "SCB"}

_FACET = "defense_coverage_matchup"


@dataclass
class _CbProfile:
    """Aggregated stats for one starting cornerback."""

    player_id: int
    team: str
    alignment: str  # LCB, RCB, SCB
    catch_rate_allowed: float
    ypr_allowed: float
    coverage_grade: float
    total_targets: int
    games_played: int


class CoverageEngine:
    """Builds CB profiles and computes per-WR coverage modifiers.

    Uses PFF defense_coverage_matchup data to identify starting CBs
    by alignment and aggregate their coverage stats.
    """

    def __init__(self, loader: PffLoader, config: CoverageConfig):
        self._loader = loader
        self._config = config
        self._cache: dict[str, pl.DataFrame] = {}

    def _load_cached(self, seasons: list[int]) -> pl.DataFrame:
        """Load defense_coverage_matchup with caching by seasons key."""
        key = f"{_FACET}_{'_'.join(str(s) for s in sorted(seasons))}"
        if key not in self._cache:
            self._cache[key] = self._loader.load_facet(_FACET, seasons)
        return self._cache[key]

    def _build_season_profiles(
        self,
        defense_team: str,
        target_season: int,
        max_week: int,
    ) -> dict[str, _CbProfile]:
        """Build per-alignment CB profiles for a defense from a single season.

        Algorithm:
        1. Load defense_coverage_matchup for target_season, filter week < max_week
        2. Get Type 1 rows (coverage_player_id IS NULL) for defense_team
           where position in CB_ALIGNMENTS
        3. Build CB player_id -> alignment mapping from Type 1
        4. Get Type 2 rows (coverage_player_id IS NOT NULL) where
           coverage_player_id is one of the CBs found in step 2
        5. Aggregate per CB: sum(targets), sum(receptions), sum(yards),
           n_unique(game_id), target-weighted coverage grade
        6. Join with CB info to get alignment
        7. Compute catch_rate_allowed = receptions/targets,
           ypr_allowed = yards/receptions
        8. At each alignment, pick the starter (most targets)
        9. Return dict mapping alignment -> _CbProfile

        Args:
            defense_team: Team abbreviation for the defense.
            target_season: The season to load data from.
            max_week: Filter data to week < max_week.

        Returns:
            Dict mapping alignment (LCB/RCB/SCB) to _CbProfile for
            the starting CB at that alignment.
        """
        df = self._load_cached([target_season])
        if df.is_empty():
            return {}

        # Filter to rolling window
        if "week" in df.columns:
            df = df.filter(pl.col("week") < max_week)
        if df.is_empty():
            return {}

        # Step 2: Type 1 rows — CBs on the defense team
        # Type 1 rows have coverage_player_id as null
        # After load_facet, CB positions (LCB/RCB/SCB) stay as-is in position
        # because they are not in PFF_TO_FANTASY_POSITION.
        # However, load_facet renames position -> pff_position and maps position.
        # CB positions not in the map stay unchanged in position column.
        pos_col = "pff_position" if "pff_position" in df.columns else "position"
        type1_cbs = df.filter(
            pl.col("coverage_player_id").is_null()
            & (pl.col("team") == defense_team)
            & pl.col(pos_col).is_in(list(CB_ALIGNMENTS))
        )
        if type1_cbs.is_empty():
            return {}

        # Step 3: Build CB player_id -> alignment mapping
        # Use the most frequent alignment per CB (handles mid-season moves)
        cb_alignment = (
            type1_cbs.group_by("player_id")
            .agg(
                pl.col(pos_col).mode().first().alias("alignment"),
                pl.col("team").first().alias("team"),
            )
        )
        cb_ids = cb_alignment["player_id"].to_list()
        if not cb_ids:
            return {}

        # Step 4: Type 2 rows — matchup pairs for our CBs
        type2 = df.filter(
            pl.col("coverage_player_id").is_not_null()
            & pl.col("coverage_player_id").is_in(cb_ids)
        )
        if type2.is_empty():
            return {}

        # Step 5: Aggregate per CB
        # Target-weighted coverage grade: use grades_coverage_defense with
        # grades_overall fallback when coverage grade is null
        type2 = type2.with_columns(
            pl.when(pl.col("grades_coverage_defense").is_not_null())
            .then(pl.col("grades_coverage_defense"))
            .otherwise(pl.col("grades_overall"))
            .alias("_grade_effective")
        )

        cb_stats = type2.group_by("coverage_player_id").agg(
            pl.col("targets").sum().alias("total_targets"),
            pl.col("receptions").sum().alias("total_receptions"),
            pl.col("yards").sum().alias("total_yards"),
            pl.col("game_id").n_unique().alias("games_played"),
            # Target-weighted grade
            (pl.col("_grade_effective") * pl.col("targets")).sum().alias("_weighted_grade"),
        )

        # Compute weighted average grade
        cb_stats = cb_stats.with_columns(
            (pl.col("_weighted_grade") / pl.col("total_targets")).alias("coverage_grade"),
        )

        # Step 6: Join with alignment info
        cb_stats = cb_stats.join(
            cb_alignment,
            left_on="coverage_player_id",
            right_on="player_id",
            how="inner",
        )

        # Step 7: Compute rates
        cb_stats = cb_stats.with_columns(
            (pl.col("total_receptions") / pl.col("total_targets")).alias("catch_rate_allowed"),
            pl.when(pl.col("total_receptions") > 0)
            .then(pl.col("total_yards") / pl.col("total_receptions"))
            .otherwise(pl.lit(0.0))
            .alias("ypr_allowed"),
        )

        # Step 8: Pick starter at each alignment (most targets)
        starters = (
            cb_stats.sort("total_targets", descending=True)
            .group_by("alignment")
            .first()
        )

        # Step 9: Build profiles
        profiles: dict[str, _CbProfile] = {}
        for row in starters.iter_rows(named=True):
            alignment = row["alignment"]
            profiles[alignment] = _CbProfile(
                player_id=row["coverage_player_id"],
                team=row["team"],
                alignment=alignment,
                catch_rate_allowed=float(row["catch_rate_allowed"]),
                ypr_allowed=float(row["ypr_allowed"]),
                coverage_grade=float(row["coverage_grade"]),
                total_targets=int(row["total_targets"]),
                games_played=int(row["games_played"]),
            )

        return profiles

    def _build_cb_profiles(
        self,
        defense_team: str,
        target_season: int,
        max_week: int,
    ) -> dict[str, _CbProfile]:
        """Build per-alignment CB profiles with early-season blending.

        Calls _build_season_profiles for the current season. If any CB has
        fewer than min_games games, blends with the previous season using a
        linear ramp: weight = current_games / min_games.

        Args:
            defense_team: Team abbreviation for the defense.
            target_season: The season being simulated.
            max_week: Filter data to week < max_week.

        Returns:
            Dict mapping alignment (LCB/RCB/SCB) to _CbProfile for
            the starting CB at that alignment (blended if early season).
        """
        current_profiles = self._build_season_profiles(defense_team, target_season, max_week)

        if not current_profiles:
            return current_profiles

        # Check if any CB has fewer than min_games
        min_games = self._config.min_games
        min_current_games = min(p.games_played for p in current_profiles.values())

        logger.info(
            "CB profiles for %s (season=%d, week<%d): %s",
            defense_team,
            target_season,
            max_week,
            {a: f"#{p.player_id} tgt={p.total_targets}" for a, p in current_profiles.items()},
        )

        if min_current_games >= min_games:
            return current_profiles

        # Early-season blend: load previous season (max_week=99 to get all weeks)
        prev_profiles = self._build_season_profiles(defense_team, target_season - 1, max_week=99)
        if not prev_profiles:
            return current_profiles

        # Linear ramp: blend_weight = current_games / min_games
        blend_weight = min_current_games / min_games

        blended: dict[str, _CbProfile] = {}
        for alignment, current in current_profiles.items():
            prev = prev_profiles.get(alignment)
            if prev is None:
                # No previous-season data for this alignment — use current only
                blended[alignment] = current
                continue

            blended[alignment] = _CbProfile(
                player_id=current.player_id,
                team=current.team,
                alignment=alignment,
                catch_rate_allowed=(
                    blend_weight * current.catch_rate_allowed
                    + (1 - blend_weight) * prev.catch_rate_allowed
                ),
                ypr_allowed=(
                    blend_weight * current.ypr_allowed
                    + (1 - blend_weight) * prev.ypr_allowed
                ),
                coverage_grade=(
                    blend_weight * current.coverage_grade
                    + (1 - blend_weight) * prev.coverage_grade
                ),
                total_targets=current.total_targets + prev.total_targets,
                games_played=current.games_played,
            )

        return blended

    def _determine_wr_alignments(
        self,
        wr_player_ids: list[str],
        offense_team: str,
        target_season: int,
        max_week: int,
        pff_player_id_map: dict[str, int],
    ) -> dict[str, str]:
        """Determine each WR's primary alignment from PFF matchup data.

        For each WR, looks up their Type 1 rows (coverage_player_id IS NULL)
        in the defense_coverage_matchup facet and takes the plurality pff_position.
        WRs not resolved fall back to index-based alignment:
          index 0 → RWR, index 1 → LWR, index 2+ → SLWR.

        Args:
            wr_player_ids: nflverse player_ids for WRs, pre-sorted by
                target_share descending.
            offense_team: Team abbreviation for the offense.
            target_season: The season to load data from.
            max_week: Filter data to week < max_week.
            pff_player_id_map: Maps nflverse player_id → PFF player_id.

        Returns:
            Dict mapping nflverse player_id → pff_position alignment
            (RWR/LWR/SLWR/SRWR).
        """
        _FALLBACK = ["RWR", "LWR", "SLWR"]

        # Load and filter to rolling window
        df = self._load_cached([target_season])
        type1_wrs = pl.DataFrame()

        if not df.is_empty():
            if "week" in df.columns:
                df = df.filter(pl.col("week") < max_week)

            if not df.is_empty():
                # Type 1 WR rows for the offense team
                # After load_facet: position="WR", pff_position="RWR"/"LWR"/etc.
                pos_col = "pff_position" if "pff_position" in df.columns else "position"
                type1_wrs = df.filter(
                    pl.col("coverage_player_id").is_null()
                    & (pl.col("team") == offense_team)
                    & (pl.col("position") == "WR")
                )

        alignments: dict[str, str] = {}

        for idx, nfl_id in enumerate(wr_player_ids):
            pff_id = pff_player_id_map.get(nfl_id)
            resolved = False

            if pff_id is not None and not type1_wrs.is_empty():
                player_rows = type1_wrs.filter(pl.col("player_id") == pff_id)
                if not player_rows.is_empty():
                    # Take plurality pff_position
                    pos_col = "pff_position" if "pff_position" in player_rows.columns else "position"
                    counts = (
                        player_rows
                        .group_by(pos_col)
                        .agg(pl.len().alias("n"))
                        .sort("n", descending=True)
                    )
                    alignments[nfl_id] = counts[pos_col][0]
                    resolved = True

            if not resolved:
                fallback = _FALLBACK[idx] if idx < len(_FALLBACK) else "SLWR"
                alignments[nfl_id] = fallback

        return alignments

    def compute(
        self,
        defense_team: str,
        roster: object | None = None,
        target_season: int | None = None,
        max_week: int | None = None,
    ) -> dict:
        """Compute per-WR coverage modifiers.

        Stub — returns empty dict. Will be completed in Task 6.

        Args:
            defense_team: Team abbreviation for the defense.
            roster: TeamRoster for the offense (unused in stub).
            target_season: The season being simulated.
            max_week: The week being simulated.

        Returns:
            Empty dict (stub).
        """
        return {}

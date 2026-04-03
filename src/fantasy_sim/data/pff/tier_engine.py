"""PFF Talent-Tier Distribution Engine.

Assigns players to talent tiers (1–5) based on PFF grades and selects
per-tier distributions (target_share, carry_share, catch_rate, yards
distributions) to use as Bayesian priors in player model construction.

This module is a drop-in replacement for TalentStabilizer.  Instead of
blending individual PBP observations with a single league-wide prior, it
groups historical player-seasons into five percentile-based tiers and pulls
distributions from the appropriate tier pool.

Pipeline position (same ordering as TalentStabilizer):
    base model → matchup → schedule-adjust → *tier engine* → normalize
    → user overrides → normalize
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
import polars as pl

from fantasy_sim.data.pff.models import TierConfig

if TYPE_CHECKING:
    from fantasy_sim.models.player import PlayerModel, TeamRoster

logger = logging.getLogger(__name__)

# Minimum number of player-seasons required to populate a tier pool entry.
# Pools with fewer samples fall back to the next-closest tier or league average.
MIN_TIER_POOL_SIZE = 20


# ---------------------------------------------------------------------------
# Internal pool entry (stores the full percentile summary for a position-tier)
# ---------------------------------------------------------------------------

@dataclass
class _TierPoolEntry:
    """Internal storage for one (position, tier) pool.

    Scalar fields hold (p25, median, p75) tuples derived from historical
    player-seasons that belong to this tier.  Array fields hold concatenated
    empirical distributions for direct sampling.
    """

    # Scalars: (p25, median, p75) tuples
    target_share: tuple[float, float, float] = (0.0, 0.0, 0.0)
    carry_share: tuple[float, float, float] = (0.0, 0.0, 0.0)
    catch_rate: tuple[float, float, float] = (0.0, 0.0, 0.0)
    air_yards_share: tuple[float, float, float] = (0.0, 0.0, 0.0)
    fumble_rate: tuple[float, float, float] = (0.0, 0.0, 0.0)
    scramble_rate: tuple[float, float, float] = (0.0, 0.0, 0.0)

    # Empirical distributions (numpy arrays) for yards sampling
    receiving_yards_dist: np.ndarray | None = None
    rushing_yards_dist: np.ndarray | None = None

    # Secondary grade distribution for within-tier interpolation
    secondary_grades: np.ndarray | None = None

    # Number of player-seasons that contributed to this pool
    n_player_seasons: int = 0


# ---------------------------------------------------------------------------
# Public return type for distribution selection
# ---------------------------------------------------------------------------

@dataclass
class TierDistributions:
    """Player distributions selected from a tier pool.

    Returned by :meth:`TierEngine.select_distributions` and consumed by
    the player model construction pipeline.
    """

    target_share: float = 0.0
    carry_share: float = 0.0
    catch_rate: float = 0.0
    air_yards_share: float = 0.0
    fumble_rate: float = 0.0
    scramble_rate: float = 0.0
    receiving_yards_dist: np.ndarray | None = None
    rushing_yards_dist: np.ndarray | None = None


# ---------------------------------------------------------------------------
# Tier assignment result
# ---------------------------------------------------------------------------

@dataclass
class TierAssignment:
    """Result of assigning a player to a talent tier.

    Attributes:
        tier: Tier number 1 (elite) through 5 (replacement level).
        primary_percentile: Player's percentile rank on the primary PFF grade
            column (0.0–1.0).
        secondary_percentile: Player's percentile rank on the secondary PFF
            grade column (0.0–1.0).  Used for within-tier interpolation.
        reliability: Confidence weight (0.0–1.0) reflecting data quantity and
            stability.  Higher = more trust in the tier assignment.
    """

    tier: int = 3
    primary_percentile: float = 0.5
    secondary_percentile: float = 0.5
    reliability: float = 0.5


# ---------------------------------------------------------------------------
# TierEngine
# ---------------------------------------------------------------------------

class TierEngine:
    """Assign players to PFF talent tiers and select per-tier distributions.

    Args:
        config: Tier engine configuration (cutoffs, grade columns, pool size,
            reliability parameters).
        pff_loader: PffLoader instance used to fetch historical grade data.
            May be ``None`` during testing or when the engine is disabled.
    """

    def __init__(self, config: TierConfig, pff_loader) -> None:
        self._config = config
        self._pff_loader = pff_loader

        # Populated lazily by _build_pools()
        # Structure: {position: {tier_number: _TierPoolEntry}}
        self._pools: dict[str, dict[int, _TierPoolEntry]] | None = None

        # Precomputed grade boundaries per position
        # Structure: {position: [boundary_tier1, boundary_tier2, boundary_tier3, boundary_tier4]}
        # Grades >= boundary_tier1 → Tier 1; ...; grades < boundary_tier4 → Tier 5
        self._boundaries: dict[str, list[float]] | None = None

        # Cache key: tuple of (data_dir, cutoffs, blend_pool_size) that the
        # current pools were built from.  Stale when config changes.
        self._cache_key: tuple | None = None

    # ------------------------------------------------------------------
    # PBP aggregation (per-season)
    # ------------------------------------------------------------------

    @staticmethod
    def _aggregate_pbp_per_season(
        pbp: pl.DataFrame, season: int
    ) -> dict[str, dict]:
        """Extract per-player stats from PBP data for one season.

        Filters the PBP DataFrame to the given season and computes per-player
        receiving and rushing stats along with team-level totals needed for
        share computation.

        Returns:
            dict[player_id -> stats_dict] where each stats_dict contains:
              targets, catches, yards_list, carries, rushing_yards_list,
              team, games (set of game_ids), weekly_targets (dict[week->count]),
              target_share, carry_share, catch_rate, air_yards_share,
              weekly_share_values (list of per-week target shares).
        """
        plays = pbp.filter(
            pl.col("play_type").is_in(["pass", "run"])
            & (pl.col("season") == season)
        )
        if plays.is_empty():
            return {}

        # --- Team-level totals ---
        team_pass_attempts: dict[str, int] = {}
        team_rush_attempts: dict[str, int] = {}
        team_air_yards: dict[str, float] = {}

        has_air_yards = "air_yards" in plays.columns

        for team in plays["posteam"].unique().to_list():
            tp = plays.filter(pl.col("posteam") == team)
            pass_plays_team = tp.filter(pl.col("play_type") == "pass")
            rush_plays_team = tp.filter(pl.col("play_type") == "run")
            team_pass_attempts[team] = pass_plays_team.height
            team_rush_attempts[team] = rush_plays_team.height
            if has_air_yards:
                ay = pass_plays_team["air_yards"].drop_nulls()
                team_air_yards[team] = float(ay.sum()) if len(ay) > 0 else 0.0
            else:
                team_air_yards[team] = 0.0

        # --- Per-player accumulation ---
        players: dict[str, dict] = {}

        # Helper to initialise a player entry
        def _init(pid, team):
            return {
                "targets": 0,
                "catches": 0,
                "yards_list": [],
                "carries": 0,
                "rushing_yards_list": [],
                "team": team,
                "games": set(),
                "air_yards": 0.0,
                "weekly_targets": {},
            }

        # -- Pass plays (receiving) --
        pass_plays = plays.filter(pl.col("play_type") == "pass")
        for row in pass_plays.iter_rows(named=True):
            rid = row.get("receiver_player_id")
            if rid is None:
                continue
            team = row["posteam"]
            if rid not in players:
                players[rid] = _init(rid, team)
            p = players[rid]
            p["targets"] += 1
            p["games"].add(row["game_id"])
            week = row["week"]
            p["weekly_targets"][week] = p["weekly_targets"].get(week, 0) + 1
            if has_air_yards and row.get("air_yards") is not None:
                p["air_yards"] += row["air_yards"]
            if row["complete_pass"] == 1:
                p["catches"] += 1
                p["yards_list"].append(row["yards_gained"])

        # -- Run plays (rushing) --
        rush_plays = plays.filter(pl.col("play_type") == "run")
        for row in rush_plays.iter_rows(named=True):
            rid = row.get("rusher_player_id")
            if rid is None:
                continue
            team = row["posteam"]
            if rid not in players:
                players[rid] = _init(rid, team)
            p = players[rid]
            p["carries"] += 1
            p["games"].add(row["game_id"])
            p["rushing_yards_list"].append(row["yards_gained"])

        # --- Compute derived share/rate stats ---
        # Team-level weekly pass attempts for weekly share calculation
        team_weekly_pa: dict[str, dict[int, int]] = {}
        for row in pass_plays.iter_rows(named=True):
            team = row["posteam"]
            week = row["week"]
            if team not in team_weekly_pa:
                team_weekly_pa[team] = {}
            team_weekly_pa[team][week] = team_weekly_pa[team].get(week, 0) + 1

        for pid, p in players.items():
            team = p["team"]
            tpa = team_pass_attempts.get(team, 0)
            tra = team_rush_attempts.get(team, 0)
            tay = team_air_yards.get(team, 0.0)

            p["target_share"] = p["targets"] / max(tpa, 1)
            p["carry_share"] = p["carries"] / max(tra, 1)
            p["catch_rate"] = p["catches"] / max(p["targets"], 1)
            p["air_yards_share"] = p["air_yards"] / max(tay, 1.0)

            # Weekly target shares for reliability scoring
            weekly_shares = []
            weekly_pa = team_weekly_pa.get(team, {})
            for week, tgts in sorted(p["weekly_targets"].items()):
                wpa = weekly_pa.get(week, 0)
                if wpa > 0:
                    weekly_shares.append(tgts / wpa)
            p["weekly_share_values"] = weekly_shares

        return players

    # ------------------------------------------------------------------
    # PFF grade loading (per-season, per-position)
    # ------------------------------------------------------------------

    # Mapping from position to PFF facet name
    _POSITION_FACETS: dict[str, str] = {
        "QB": "passing_summary",
        "RB": "rushing_summary",
        "WR": "receiving_summary",
        "TE": "receiving_summary",
    }

    def _load_season_grades(
        self, season: int, position: str
    ) -> dict[int, dict[str, float]]:
        """Load PFF grades for a position from a single season.

        Loads the appropriate PFF facet, optionally filters by position
        column, and averages numeric grade columns across games per
        player_id.

        Returns:
            dict[pff_player_id -> {grade_name: season_avg_value}]
        """
        facet = self._POSITION_FACETS.get(position)
        if facet is None or self._pff_loader is None:
            return {}

        df = self._pff_loader.load_facet(facet, [season])
        if df.is_empty():
            return {}

        # Filter to position if column exists (e.g. receiving_summary has
        # both WR and TE rows)
        if "position" in df.columns:
            df = df.filter(pl.col("position") == position)

        if df.is_empty():
            return {}

        # Identify numeric grade columns
        meta_cols = {
            "player_id", "player", "team", "position", "pff_position",
            "season", "week", "game_id", "franchise_id", "jersey_number",
            "status",
        }
        numeric_cols = [
            c for c in df.columns
            if c not in meta_cols
            and df[c].dtype in (pl.Float64, pl.Int64, pl.Float32, pl.Int32)
        ]

        if not numeric_cols:
            return {}

        # Average grades per player across games
        agg_exprs = [pl.col(c).mean().alias(c) for c in numeric_cols]
        averaged = df.group_by("player_id").agg(agg_exprs)

        result: dict[int, dict[str, float]] = {}
        for row in averaged.iter_rows(named=True):
            pid = row["player_id"]
            grades = {c: float(row[c]) for c in numeric_cols if row[c] is not None}
            result[pid] = grades

        return result

    # ------------------------------------------------------------------
    # Thin tier merging
    # ------------------------------------------------------------------

    @staticmethod
    def _merge_thin_tiers(
        tier_buckets: dict[int, list],
    ) -> dict[int, list]:
        """Merge tiers with fewer than MIN_TIER_POOL_SIZE player-seasons.

        Strategy: merge extremes first (1->2, 5->4), then inner (2->3, 4->3).
        Continues until no thin tiers remain or further merging is impossible.

        Args:
            tier_buckets: dict[tier_number -> list of player-season dicts]

        Returns:
            Merged dict with the same structure.
        """
        result = {k: list(v) for k, v in tier_buckets.items()}

        # Merge pairs: (source, destination)
        merge_order = [(1, 2), (5, 4), (2, 3), (4, 3)]

        for src, dst in merge_order:
            if src in result and len(result[src]) < MIN_TIER_POOL_SIZE:
                if dst in result:
                    logger.info(
                        "Merging thin tier %d (%d members) into tier %d",
                        src, len(result[src]), dst,
                    )
                    result[dst].extend(result[src])
                    del result[src]
                elif src in result:
                    # dst doesn't exist; keep src as-is
                    pass

        # Remove any remaining empty tiers
        return {k: v for k, v in result.items() if v}

    # ------------------------------------------------------------------
    # Pool entry construction
    # ------------------------------------------------------------------

    @staticmethod
    def _build_pool_entry(
        members: list[dict], secondary_key: str
    ) -> _TierPoolEntry:
        """Compute a _TierPoolEntry from a list of player-season stat dicts.

        Scalars are summarised as (p25, median, p75) tuples.  Yards arrays
        are concatenated across all members into pool-level empirical
        distributions.  Secondary grades are collected and sorted for
        within-tier percentile computation.

        Args:
            members: List of player-season dicts (from _aggregate_pbp_per_season
                merged with PFF grades).
            secondary_key: Name of the secondary grade column.

        Returns:
            A populated _TierPoolEntry.
        """

        def _pct(values):
            """Compute (p25, median, p75) from a list of floats."""
            if not values:
                return (0.0, 0.0, 0.0)
            arr = np.array(values, dtype=np.float64)
            return (
                float(np.percentile(arr, 25)),
                float(np.percentile(arr, 50)),
                float(np.percentile(arr, 75)),
            )

        target_shares = [m["target_share"] for m in members if m.get("target_share") is not None]
        carry_shares = [m["carry_share"] for m in members if m.get("carry_share") is not None]
        catch_rates = [m["catch_rate"] for m in members if m.get("catch_rate") is not None]
        air_yards_shares = [m["air_yards_share"] for m in members if m.get("air_yards_share") is not None]

        # Concatenate all play-level yards into pool arrays
        all_recv_yards = []
        all_rush_yards = []
        for m in members:
            all_recv_yards.extend(m.get("yards_list", []))
            all_rush_yards.extend(m.get("rushing_yards_list", []))

        recv_dist = np.array(all_recv_yards, dtype=np.float64) if all_recv_yards else None
        rush_dist = np.array(all_rush_yards, dtype=np.float64) if all_rush_yards else None

        # Collect secondary grades
        sec_grades = [
            m["pff_grades"].get(secondary_key)
            for m in members
            if m.get("pff_grades") and m["pff_grades"].get(secondary_key) is not None
        ]
        sec_arr = np.sort(np.array(sec_grades, dtype=np.float64)) if sec_grades else None

        return _TierPoolEntry(
            target_share=_pct(target_shares),
            carry_share=_pct(carry_shares),
            catch_rate=_pct(catch_rates),
            air_yards_share=_pct(air_yards_shares),
            fumble_rate=(0.0, 0.0, 0.0),  # not computed from PBP in pool building
            scramble_rate=(0.0, 0.0, 0.0),
            receiving_yards_dist=recv_dist,
            rushing_yards_dist=rush_dist,
            secondary_grades=sec_arr,
            n_player_seasons=len(members),
        )

    # ------------------------------------------------------------------
    # Full pool-building pipeline
    # ------------------------------------------------------------------

    def _build_tier_pools(
        self,
        pbp: pl.DataFrame,
        training_seasons: list[int],
        crosswalk: dict[int, str],
    ) -> None:
        """Build tier pools from PFF grades and PBP data.

        For each position in config.position_grades:
          1. Load PFF grades + aggregate PBP per-season
          2. Cross-reference via crosswalk (pff_id -> nfl_id)
          3. Skip players with < 10 total touches
          4. Compute percentile boundaries on primary grade
          5. Assign each player-season to tier 1-5
          6. Merge thin tiers
          7. Build pool entries

        Sets self._pools and self._boundaries.
        """
        pools: dict[str, dict[int, _TierPoolEntry]] = {}
        boundaries: dict[str, list[float]] = {}

        # Invert crosswalk: nfl_id -> pff_id for fast lookup
        nfl_to_pff: dict[str, int] = {v: k for k, v in crosswalk.items()}

        for position, grade_cfg in self._config.position_grades.items():
            # Collect player-season data points with both PFF and PBP data
            player_seasons: list[dict] = []

            for season in training_seasons:
                # Load PFF grades for this season/position
                pff_grades = self._load_season_grades(season, position)

                # Aggregate PBP stats for this season
                pbp_stats = self._aggregate_pbp_per_season(pbp, season)

                # Cross-reference: find players with both PFF and PBP data
                for pff_id, grades in pff_grades.items():
                    nfl_id = crosswalk.get(pff_id)
                    if nfl_id is None:
                        continue
                    pbp_player = pbp_stats.get(nfl_id)
                    if pbp_player is None:
                        continue

                    # Skip players with < 10 total touches
                    total_touches = pbp_player["targets"] + pbp_player["carries"]
                    if total_touches < 10:
                        continue

                    # Merge PBP stats with PFF grades
                    entry = dict(pbp_player)
                    entry["pff_grades"] = grades
                    entry["pff_id"] = pff_id
                    entry["nfl_id"] = nfl_id
                    entry["season"] = season
                    player_seasons.append(entry)

            if not player_seasons:
                logger.warning(
                    "No player-seasons found for position %s — skipping", position,
                )
                continue

            # Compute percentile boundaries on primary grade
            primary_key = grade_cfg.primary
            primary_grades = [
                ps["pff_grades"].get(primary_key, 0.0) for ps in player_seasons
            ]
            primary_arr = np.array(primary_grades, dtype=np.float64)
            cutoffs = self._config.cutoffs  # e.g. [0.85, 0.65, 0.40, 0.20]
            pos_boundaries = [
                float(np.percentile(primary_arr, pct * 100)) for pct in cutoffs
            ]
            boundaries[position] = pos_boundaries

            # Assign each player-season to a tier
            tier_buckets: dict[int, list] = {t: [] for t in range(1, 6)}
            for ps in player_seasons:
                grade = ps["pff_grades"].get(primary_key, 0.0)
                tier = 5
                for tier_idx, boundary in enumerate(pos_boundaries):
                    if grade >= boundary:
                        tier = tier_idx + 1
                        break
                tier_buckets[tier].append(ps)

            # Merge thin tiers
            tier_buckets = self._merge_thin_tiers(tier_buckets)

            # Build pool entries
            secondary_key = grade_cfg.secondary
            position_pools: dict[int, _TierPoolEntry] = {}
            for tier, members in tier_buckets.items():
                position_pools[tier] = self._build_pool_entry(members, secondary_key)

            pools[position] = position_pools
            logger.info(
                "Built %d tier pools for %s: %s",
                len(position_pools),
                position,
                {t: e.n_player_seasons for t, e in position_pools.items()},
            )

        self._pools = pools
        self._boundaries = boundaries

    # ------------------------------------------------------------------
    # Cache-aware pool building
    # ------------------------------------------------------------------

    def _ensure_pools(
        self,
        pbp: pl.DataFrame,
        training_seasons: list[int],
        crosswalk: dict[int, str],
    ) -> None:
        """Build tier pools if not already cached for the given seasons.

        Checks whether ``self._cache_key`` matches the current
        ``training_seasons``.  If so, the existing pools are reused.
        Otherwise, :meth:`_build_tier_pools` is called and the cache key
        is updated.
        """
        key = tuple(training_seasons)
        if self._cache_key == key and self._pools is not None:
            return
        self._build_tier_pools(pbp, training_seasons, crosswalk)
        self._cache_key = key

    # ------------------------------------------------------------------
    # Tier assignment
    # ------------------------------------------------------------------

    def _assign_tier(self, primary_grade: float, position: str) -> int:
        """Map a primary PFF grade to a tier 1–5 via precomputed boundaries.

        The boundaries list has four values corresponding to the grade
        thresholds for tiers 1–4.  A grade *at or above* a boundary receives
        the better (lower-numbered) tier.

        Args:
            primary_grade: The player's primary PFF grade (0–100 scale).
            position: Position key (e.g. ``"WR"``, ``"QB"``).

        Returns:
            Integer tier in the range [1, 5].
        """
        boundaries = self._boundaries[position]
        for tier_idx, boundary in enumerate(boundaries):
            if primary_grade >= boundary:
                return tier_idx + 1
        return 5

    # ------------------------------------------------------------------
    # Within-tier percentile
    # ------------------------------------------------------------------

    def _within_tier_percentile(
        self, secondary_grade: float, position: str, tier: int
    ) -> float:
        """Compute percentile of a secondary grade within a tier's grade array.

        Uses ``np.searchsorted`` on the sorted array so that the result is the
        fraction of historical secondary grades *below* the supplied value.

        Args:
            secondary_grade: The player's secondary PFF grade value.
            position: Position key (e.g. ``"WR"``).
            tier: Tier number 1–5.

        Returns:
            Percentile in [0.0, 1.0].  Returns 0.5 when the grades array is
            missing or empty.
        """
        pool = self._pools[position][tier]
        grades = pool.secondary_grades
        if grades is None or len(grades) == 0:
            return 0.5
        return float(np.searchsorted(np.sort(grades), secondary_grade) / len(grades))

    # ------------------------------------------------------------------
    # Piecewise linear scalar interpolation
    # ------------------------------------------------------------------

    @staticmethod
    def _interp_scalar(low_med_high: tuple[float, float, float], pct: float) -> float:
        """Piecewise linear interpolation through (p25, p50, p75).

        The interpolation is split at pct=0.5:
          - pct in [0, 0.5]: linearly from p25 to p50
          - pct in (0.5, 1.0]: linearly from p50 to p75

        Args:
            low_med_high: Tuple of (p25, median, p75) values.
            pct: Percentile in [0.0, 1.0].

        Returns:
            Interpolated scalar value.
        """
        low, med, high = low_med_high
        if pct <= 0.5:
            return low + (pct / 0.5) * (med - low)
        return med + ((pct - 0.5) / 0.5) * (high - med)

    # ------------------------------------------------------------------
    # Full scalar interpolation across all TierDistributions fields
    # ------------------------------------------------------------------

    def _interpolate_scalars(
        self, pool: _TierPoolEntry, secondary_pct: float
    ) -> "TierDistributions":
        """Build a TierDistributions by interpolating each scalar field.

        Scalar fields (target_share, carry_share, etc.) are interpolated via
        :meth:`_interp_scalar`.  Yards arrays are passed through unchanged
        from the pool entry.

        Args:
            pool: The tier pool entry for a (position, tier) pair.
            secondary_pct: Within-tier percentile on the secondary grade.

        Returns:
            A :class:`TierDistributions` instance ready for downstream use.
        """
        interp = self._interp_scalar
        return TierDistributions(
            target_share=interp(pool.target_share, secondary_pct),
            carry_share=interp(pool.carry_share, secondary_pct),
            catch_rate=interp(pool.catch_rate, secondary_pct),
            air_yards_share=interp(pool.air_yards_share, secondary_pct),
            fumble_rate=interp(pool.fumble_rate, secondary_pct),
            scramble_rate=interp(pool.scramble_rate, secondary_pct),
            receiving_yards_dist=pool.receiving_yards_dist,
            rushing_yards_dist=pool.rushing_yards_dist,
        )

    # ------------------------------------------------------------------
    # Reliability scoring
    # ------------------------------------------------------------------

    def compute_reliability(
        self,
        games_played: int,
        changed_teams: bool,
        weekly_shares: "np.ndarray | None",
    ) -> float:
        """Compute PBP reliability score.

        Returns PBP weight in [floor, cap]. Tier weight = 1 - reliability.

        Factors:
            1. Sample size: games_played / max_games (capped at 1.0)
            2. Team change: penalty multiplier if player changed teams
            3. Share variance: coefficient of variation of weekly shares (needs >= 4 weeks)
        """
        cfg = self._config

        # Factor 1: sample size
        sample = min(games_played / cfg.reliability_max_games, 1.0)

        # Factor 2: team change
        team = cfg.reliability_team_change_penalty if changed_teams else 1.0

        # Factor 3: share variance (needs >= 4 weeks)
        variance_penalty = 0.0
        if weekly_shares is not None and len(weekly_shares) >= 4:
            mean = np.mean(weekly_shares)
            if mean > 0.01:
                cv = float(np.std(weekly_shares) / mean)
                variance_penalty = min(cv, 1.0)

        raw = sample * team * (1.0 - variance_penalty * cfg.reliability_variance_weight)
        return float(np.clip(raw, cfg.reliability_floor, cfg.reliability_cap))

    # ------------------------------------------------------------------
    # Player blending
    # ------------------------------------------------------------------

    def _blend_player(
        self,
        player: "PlayerModel",
        tier_dists: TierDistributions,
        reliability: float,
        rng: np.random.Generator,
    ) -> None:
        """Blend tier distributions into a PlayerModel in place.

        Scalars: weighted average (reliability * PBP + tier_weight * tier).
        Yards: concatenation with proportional resampling.
        RZ fields, scramble_yards_dist, pass_fumble_rate: untouched.
        """
        tier_weight = 1.0 - reliability
        pool_size = self._config.blend_pool_size

        # --- Scalar blending ---
        player.usage.target_share = (
            reliability * player.usage.target_share + tier_weight * tier_dists.target_share
        )
        player.usage.carry_share = (
            reliability * player.usage.carry_share + tier_weight * tier_dists.carry_share
        )
        player.usage.air_yards_share = (
            reliability * player.usage.air_yards_share + tier_weight * tier_dists.air_yards_share
        )
        player.usage.scramble_rate = (
            reliability * player.usage.scramble_rate + tier_weight * tier_dists.scramble_rate
        )
        player.outcomes.catch_rate = (
            reliability * player.outcomes.catch_rate + tier_weight * tier_dists.catch_rate
        )
        player.outcomes.fumble_rate = (
            reliability * player.outcomes.fumble_rate + tier_weight * tier_dists.fumble_rate
        )

        # --- Yards blending: proportional resampling ---
        def _blend_yards(personal, tier_pool):
            if tier_pool is None:
                return personal
            if personal is None or len(personal) == 0:
                return tier_pool
            n_pbp = max(1, int(reliability * pool_size))
            n_tier = pool_size - n_pbp
            pbp_sample = rng.choice(personal, size=n_pbp, replace=True)
            tier_sample = rng.choice(tier_pool, size=n_tier, replace=True)
            return np.concatenate([pbp_sample, tier_sample])

        player.outcomes.receiving_yards_dist = _blend_yards(
            player.outcomes.receiving_yards_dist, tier_dists.receiving_yards_dist,
        )
        player.outcomes.rushing_yards_dist = _blend_yards(
            player.outcomes.rushing_yards_dist, tier_dists.rushing_yards_dist,
        )

    # ------------------------------------------------------------------
    # Public entry point: full distribution selection pipeline
    # ------------------------------------------------------------------

    def select_distributions(
        self, pff_grades: dict[str, float], position: str
    ) -> "tuple[TierAssignment, TierDistributions] | None":
        """Select tier distributions for a player based on their PFF grades.

        Pipeline:
          1. Look up grade column names for the position.
          2. Extract primary and secondary grades from ``pff_grades``.
          3. Assign to a tier via :meth:`_assign_tier`.
          4. Compute within-tier percentile via :meth:`_within_tier_percentile`.
          5. Interpolate scalars via :meth:`_interpolate_scalars`.
          6. Return ``(TierAssignment, TierDistributions)``.

        Args:
            pff_grades: Mapping from PFF grade column name to numeric value.
            position: Position key (e.g. ``"WR"``).

        Returns:
            A ``(TierAssignment, TierDistributions)`` tuple, or ``None`` when
            the position is not configured or the primary grade is missing.
        """
        grade_cfg = self._config.position_grades.get(position)
        if grade_cfg is None:
            return None

        primary_grade = pff_grades.get(grade_cfg.primary)
        if primary_grade is None:
            return None

        secondary_grade = pff_grades.get(grade_cfg.secondary)

        tier = self._assign_tier(primary_grade, position)

        if secondary_grade is not None:
            secondary_pct = self._within_tier_percentile(secondary_grade, position, tier)
        else:
            secondary_pct = 0.5

        # Approximate primary_percentile from tier number (tier 1 = top, tier 5 = bottom)
        # Map tier 1→0.9, 2→0.7, 3→0.5, 4→0.3, 5→0.1
        primary_pct = max(0.0, min(1.0, 1.0 - (tier - 1) * 0.2))

        assignment = TierAssignment(
            tier=tier,
            primary_percentile=primary_pct,
            secondary_percentile=secondary_pct,
            reliability=0.5,
        )

        pool = self._pools[position][tier]
        dists = self._interpolate_scalars(pool, secondary_pct)

        return assignment, dists

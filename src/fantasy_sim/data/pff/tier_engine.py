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

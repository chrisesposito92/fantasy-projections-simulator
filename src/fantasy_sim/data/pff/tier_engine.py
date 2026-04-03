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

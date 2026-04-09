"""TD Tendency Engine: per-player red zone TD conversion factors.

Computes receiving_td_factor and rushing_td_factor per player using
Bayesian shrinkage of observed RZ TD rates toward positional priors.

Primary data: PFF fantasy stats (fantasy_receiving, fantasy_passing).
Fallback: PBP-derived RZ TD counts from _aggregate_pbp_stats().

Pipeline position: after coverage, before weather in build_game().
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TdTendencyConfig:
    """Configuration for TD tendency engine."""

    enabled: bool = False
    prior_strength: float = 15.0
    min_opportunities: int = 5
    factor_clamp: tuple[float, float] = (0.70, 1.30)


def load_td_tendency_config(defaults: dict) -> TdTendencyConfig:
    """Extract TdTendencyConfig from the full defaults config dict.

    Reads from defaults["td_tendency"]. Returns TdTendencyConfig(enabled=False)
    if the key is missing.
    """
    td = defaults.get("td_tendency")
    if not td:
        return TdTendencyConfig(enabled=False)
    return TdTendencyConfig(
        enabled=td.get("enabled", False),
        prior_strength=td.get("prior_strength", 15.0),
        min_opportunities=td.get("min_opportunities", 5),
        factor_clamp=tuple(td.get("factor_clamp", [0.70, 1.30])),
    )

"""Usage intelligence layer for the fantasy projections simulator (USG-01).

Provides snap-count-based share blending, CPOE, NGS, and route rate signals
to anchor volatile PBP-derived target_share and carry_share estimates.

Pipeline position: after Vegas, before props (D-03).
"""

from fantasy_sim.data.usage.engine import UsageEngine
from fantasy_sim.data.usage.models import UsageConfig
from fantasy_sim.data.usage.config import load_usage_config

__all__ = ["UsageEngine", "UsageConfig", "load_usage_config"]

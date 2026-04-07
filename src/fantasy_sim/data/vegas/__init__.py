"""Vegas lines intelligence layer.

Provides ITT-based volume factors (VEG-01) and spread-based pass rate
conditioning (VEG-02) as multiplicative adjustment factors.
"""

from fantasy_sim.data.vegas.engine import VegasEngine, compute_itt
from fantasy_sim.data.vegas.models import VegasConfig, VegasContext

__all__ = ["VegasEngine", "VegasContext", "VegasConfig", "compute_itt"]

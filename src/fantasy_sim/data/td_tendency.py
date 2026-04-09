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

import polars as pl

from fantasy_sim.models.player import TeamRoster

logger = logging.getLogger(__name__)


@dataclass
class TdTendencyConfig:
    """Configuration for TD tendency engine."""

    enabled: bool = False
    prior_strength: float = 15.0
    min_opportunities: int = 5
    factor_clamp: tuple[float, float] = (0.70, 1.30)
    i5_enabled: bool = False
    i5_prior_strength: float = 25.0
    i5_min_opportunities: int = 3


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
        i5_enabled=td.get("i5_enabled", False),
        i5_prior_strength=td.get("i5_prior_strength", 25.0),
        i5_min_opportunities=td.get("i5_min_opportunities", 3),
    )


# Default positional priors from NFL 2021-2024 PBP averages.
_DEFAULT_RECEIVING_TD_PRIORS: dict[str, float] = {
    "WR": 0.17,
    "TE": 0.15,
    "RB": 0.12,
}
_DEFAULT_RUSHING_TD_PRIORS: dict[str, float] = {
    "RB": 0.28,
    "QB": 0.25,
    "FB": 0.30,
}


class TdTendencyEngine:
    """Per-player red zone TD conversion factors.

    Computes receiving_td_factor and rushing_td_factor via Bayesian
    blend of observed RZ TD rate toward a positional prior.
    """

    def __init__(self, config: TdTendencyConfig, pff_loader=None) -> None:
        self._config = config
        self._pff_loader = pff_loader

    def apply(self, roster: TeamRoster, season: int, week: int,
              pff_crosswalk: dict[int, str] | None = None,
              pbp_stats: dict | None = None) -> None:
        """Compute and store TD factors on each player's outcomes. Mutates in-place."""
        if not self._config.enabled:
            return

        # Try PFF data first
        rec_rates, rush_rates, i5_rush_rates = self._load_pff_rates(season, week, pff_crosswalk)

        # Fall back to PBP for any missing channel (not just when both are empty)
        if pbp_stats:
            if not rec_rates or not rush_rates:
                pbp_rec, pbp_rush, pbp_i5 = self._rates_from_pbp(pbp_stats)
                if not rec_rates:
                    rec_rates = pbp_rec
                if not rush_rates:
                    rush_rates = pbp_rush
                if not i5_rush_rates:
                    i5_rush_rates = pbp_i5

        if not rec_rates and not rush_rates:
            logger.debug("TdTendencyEngine: no data for season=%d week=%d", season, week)
            return

        rec_priors = dict(_DEFAULT_RECEIVING_TD_PRIORS)
        rush_priors = dict(_DEFAULT_RUSHING_TD_PRIORS)

        for player in roster.players:
            gsis_id = player.player_id

            if gsis_id in rec_rates:
                tds, opps = rec_rates[gsis_id]
                if opps >= self._config.min_opportunities:
                    prior = rec_priors.get(player.position, 0.15)
                    if prior > 0:
                        observed = tds / opps
                        blended = self._bayesian_blend(observed, prior, opps)
                        player.outcomes.receiving_td_factor = self._clamp(blended / prior)

            if gsis_id in rush_rates:
                tds, opps = rush_rates[gsis_id]
                if opps >= self._config.min_opportunities:
                    prior = rush_priors.get(player.position, 0.25)
                    if prior > 0:
                        observed = tds / opps
                        blended = self._bayesian_blend(observed, prior, opps)
                        player.outcomes.rushing_td_factor = self._clamp(blended / prior)

    def _bayesian_blend(self, observed: float, prior: float, n_obs: int) -> float:
        ps = self._config.prior_strength
        return (n_obs * observed + ps * prior) / (n_obs + ps)

    def _clamp(self, factor: float) -> float:
        lo, hi = self._config.factor_clamp
        return max(lo, min(hi, factor))

    def _load_pff_rates(self, season: int, week: int,
                        pff_crosswalk: dict[int, str] | None,
                        ) -> tuple[dict[str, tuple[int, int]], dict[str, tuple[int, int]], dict[str, tuple[int, int]]]:
        """Load RZ TD rates from PFF fantasy stats parquet files.
        Returns (receiving_rates, rushing_rates, i5_rush_rates) where each is {gsis_id: (tds, opportunities)}.
        """
        if self._pff_loader is None or pff_crosswalk is None:
            return {}, {}, {}

        rec_rates: dict[str, tuple[int, int]] = {}
        rush_rates: dict[str, tuple[int, int]] = {}
        i5_rush_rates: dict[str, tuple[int, int]] = {}

        try:
            rec_df = self._pff_loader.load_facet("fantasy_receiving", [season])
        except Exception:
            rec_df = pl.DataFrame()

        if not rec_df.is_empty() and "week" in rec_df.columns:
            rec_df = rec_df.filter(pl.col("week") < week)
            if not rec_df.is_empty():
                required = {"player_id", "rz_rec_targ", "rz_rec_tds", "rz_rush_carries", "rz_rush_tds"}
                if required.issubset(set(rec_df.columns)):
                    has_i5 = (self._config.i5_enabled
                               and "i5_rush_carries" in rec_df.columns
                               and "i5_rush_tds" in rec_df.columns)
                    agg_exprs = [
                        pl.col("rz_rec_targ").sum().alias("rz_rec_targ"),
                        pl.col("rz_rec_tds").sum().alias("rz_rec_tds"),
                        pl.col("rz_rush_carries").sum().alias("rz_rush_carries"),
                        pl.col("rz_rush_tds").sum().alias("rz_rush_tds"),
                    ]
                    if has_i5:
                        agg_exprs += [
                            pl.col("i5_rush_carries").sum().alias("i5_rush_carries"),
                            pl.col("i5_rush_tds").sum().alias("i5_rush_tds"),
                        ]
                    agg = rec_df.group_by("player_id").agg(agg_exprs)
                    for row in agg.iter_rows(named=True):
                        pff_id = row["player_id"]
                        gsis_id = pff_crosswalk.get(pff_id)
                        if gsis_id is None:
                            continue
                        if row["rz_rec_targ"] > 0:
                            rec_rates[gsis_id] = (row["rz_rec_tds"], row["rz_rec_targ"])
                        if row["rz_rush_carries"] > 0:
                            rush_rates[gsis_id] = (row["rz_rush_tds"], row["rz_rush_carries"])
                        if has_i5 and row["i5_rush_carries"] > 0:
                            i5_rush_rates[gsis_id] = (row["i5_rush_tds"], row["i5_rush_carries"])

        try:
            pass_df = self._pff_loader.load_facet("fantasy_passing", [season])
        except Exception:
            pass_df = pl.DataFrame()

        if not pass_df.is_empty() and "week" in pass_df.columns:
            pass_df = pass_df.filter(pl.col("week") < week)
            if not pass_df.is_empty():
                rush_cols = {"player_id", "rz_rush_carries", "rz_rush_tds"}
                if rush_cols.issubset(set(pass_df.columns)):
                    has_i5 = (self._config.i5_enabled
                               and "i5_rush_carries" in pass_df.columns
                               and "i5_rush_tds" in pass_df.columns)
                    agg_exprs = [
                        pl.col("rz_rush_carries").sum().alias("rz_rush_carries"),
                        pl.col("rz_rush_tds").sum().alias("rz_rush_tds"),
                    ]
                    if has_i5:
                        agg_exprs += [
                            pl.col("i5_rush_carries").sum().alias("i5_rush_carries"),
                            pl.col("i5_rush_tds").sum().alias("i5_rush_tds"),
                        ]
                    agg = pass_df.group_by("player_id").agg(agg_exprs)
                    for row in agg.iter_rows(named=True):
                        pff_id = row["player_id"]
                        gsis_id = pff_crosswalk.get(pff_id)
                        if gsis_id is None:
                            continue
                        if row["rz_rush_carries"] > 0:
                            rush_rates[gsis_id] = (row["rz_rush_tds"], row["rz_rush_carries"])
                        if has_i5 and row["i5_rush_carries"] > 0:
                            i5_rush_rates[gsis_id] = (row["i5_rush_tds"], row["i5_rush_carries"])

        if rec_rates or rush_rates or i5_rush_rates:
            logger.info("TdTendency PFF: %d receiving, %d rushing, %d i5_rush rates (season=%d, week<%d)",
                        len(rec_rates), len(rush_rates), len(i5_rush_rates), season, week)
        return rec_rates, rush_rates, i5_rush_rates

    @staticmethod
    def _rates_from_pbp(pbp_stats: dict) -> tuple[dict[str, tuple[int, int]], dict[str, tuple[int, int]], dict[str, tuple[int, int]]]:
        """Extract RZ TD rates from PBP aggregated stats (fallback)."""
        rec_rates: dict[str, tuple[int, int]] = {}
        rush_rates: dict[str, tuple[int, int]] = {}
        i5_rush_rates: dict[str, tuple[int, int]] = {}

        for pid, rs in pbp_stats.get("receiving", {}).items():
            rz_targ = rs.get("rz_targets", 0)
            rz_tds = rs.get("rz_tds", 0)
            if rz_targ > 0:
                rec_rates[pid] = (rz_tds, rz_targ)

        for pid, rs in pbp_stats.get("rushing", {}).items():
            rz_carries = rs.get("rz_carries", 0)
            rz_tds = rs.get("rz_tds", 0)
            if rz_carries > 0:
                rush_rates[pid] = (rz_tds, rz_carries)

            i5_carries = rs.get("i5_rush_carries", 0)
            i5_tds = rs.get("i5_rush_tds", 0)
            if i5_carries > 0:
                i5_rush_rates[pid] = (i5_tds, i5_carries)

        if rec_rates or rush_rates or i5_rush_rates:
            logger.info("TdTendency PBP fallback: %d receiving, %d rushing, %d i5_rush rates",
                        len(rec_rates), len(rush_rates), len(i5_rush_rates))
        return rec_rates, rush_rates, i5_rush_rates

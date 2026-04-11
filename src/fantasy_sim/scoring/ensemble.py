"""Post-simulation projection blending for ensemble priors."""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from fantasy_sim.data.ensemble.loader import FfOpportunityLoader
from fantasy_sim.data.ensemble.models import EnsembleConfig
from fantasy_sim.data.ensemble.normalizer import normalize_ff_opportunity


@dataclass
class BlendStats:
    total_rows: int
    covered_rows: int
    uncovered_rows: int


class FfOpportunityProjectionEnsembler:
    """Blend simulation outputs with FF Opportunity weekly priors."""

    def __init__(
        self,
        config: EnsembleConfig,
        loader: FfOpportunityLoader | None = None,
    ) -> None:
        self.config = config
        self.loader = loader
        self._prior_cache: dict[int, pl.DataFrame] = {}

    def _season_priors(self, season: int) -> pl.DataFrame:
        """Load and cache normalized priors for a season."""
        cached = self._prior_cache.get(season)
        if cached is not None:
            return cached

        if self.loader is None:
            self.loader = FfOpportunityLoader(config=self.config.ff_opportunity)

        raw = self.loader.load_weekly([season])
        normalized = normalize_ff_opportunity(raw, self.config.ff_opportunity)
        self._prior_cache[season] = normalized
        return normalized

    @staticmethod
    def _mark_uncovered(row: dict) -> dict:
        """Stamp a projection row as not covered by ensemble priors."""
        row["ensemble_source"] = None
        row["ensemble_weight"] = 0.0
        row["ensemble_covered"] = False
        row.pop("ensemble_prior_fpts", None)
        return row

    def blend_week(
        self,
        projections: list[dict],
        *,
        season: int,
        week: int,
    ) -> tuple[list[dict], BlendStats]:
        """Blend simulation projections with weekly prior fantasy points."""
        total_rows = len(projections)
        if (
            not projections
            or not self.config.enabled
            or not self.config.ff_opportunity.enabled
        ):
            return [self._mark_uncovered(dict(projection)) for projection in projections], BlendStats(
                total_rows=total_rows,
                covered_rows=0,
                uncovered_rows=total_rows,
            )

        priors = self._season_priors(season).filter(pl.col("week") == week)
        prior_map = {
            prior["player_id"]: prior
            for prior in priors.iter_rows(named=True)
        }

        blended: list[dict] = []
        covered_rows = 0
        uncovered_rows = 0

        for projection in projections:
            row = dict(projection)
            prior = prior_map.get(row.get("player_id"))
            weight = float(self.config.ff_opportunity.weights.get(row.get("position", ""), 0.0))

            if prior is None or weight <= 0:
                self._mark_uncovered(row)
                uncovered_rows += 1
                blended.append(row)
                continue

            prior_fpts = float(prior["prior_fpts"])
            row["ensemble_source"] = "ff_opportunity"
            row["ensemble_weight"] = weight
            row["ensemble_covered"] = True
            row["ensemble_prior_fpts"] = round(prior_fpts, 2)
            row["fpts"] = round(
                float(row["fpts"] * (1.0 - weight) + prior_fpts * weight),
                1,
            )
            covered_rows += 1
            blended.append(row)

        blended.sort(key=lambda row: row["fpts"], reverse=True)
        for rank, row in enumerate(blended, start=1):
            row["rank"] = rank

        return blended, BlendStats(
            total_rows=total_rows,
            covered_rows=covered_rows,
            uncovered_rows=uncovered_rows,
        )

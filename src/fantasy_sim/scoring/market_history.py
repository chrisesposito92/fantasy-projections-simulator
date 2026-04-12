from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from fantasy_sim.data.market_history.features import normalize_market_history
from fantasy_sim.data.market_history.loader import MarketHistoryLoader
from fantasy_sim.data.market_history.models import MarketHistoryConfig


@dataclass
class MarketHistoryStats:
    total_rows: int
    covered_rows: int
    uncovered_rows: int


class MarketHistoryProjectionAdjuster:
    """Blend simulation outputs with historical market priors."""

    def __init__(
        self,
        config: MarketHistoryConfig,
        loader: MarketHistoryLoader | None = None,
    ) -> None:
        self.config = config
        self.loader = loader
        self._prior_cache: dict[int, pl.DataFrame] = {}

    def _season_priors(self, season: int) -> pl.DataFrame:
        cached = self._prior_cache.get(season)
        if cached is not None:
            return cached

        if self.loader is None:
            self.loader = MarketHistoryLoader(self.config)

        raw = self.loader.load_weekly([season])
        normalized = normalize_market_history(raw, self.config)
        self._prior_cache[season] = normalized
        return normalized

    @staticmethod
    def _mark_uncovered(row: dict) -> dict:
        row["market_history_source"] = None
        row["market_history_weight"] = 0.0
        row["market_history_covered"] = False
        row.pop("market_history_prior_fpts", None)
        row.pop("market_history_confidence", None)
        row.pop("market_history_line_move", None)
        return row

    def adjust_week(
        self,
        projections: list[dict],
        *,
        season: int,
        week: int,
    ) -> tuple[list[dict], MarketHistoryStats]:
        total_rows = len(projections)
        if not projections or not self.config.enabled:
            rows = [self._mark_uncovered(dict(projection)) for projection in projections]
            return rows, MarketHistoryStats(
                total_rows=total_rows,
                covered_rows=0,
                uncovered_rows=total_rows,
            )

        priors = self._season_priors(season).filter(pl.col("week") == week)
        prior_map = {
            prior["player_id"]: prior
            for prior in priors.iter_rows(named=True)
        }

        adjusted: list[dict] = []
        covered_rows = 0
        uncovered_rows = 0

        for projection in projections:
            row = dict(projection)
            position = str(row.get("position", ""))
            prior = prior_map.get(row.get("player_id"))
            base_weight = float(self.config.weights.get(position, 0.0))

            if prior is None or base_weight <= 0:
                self._mark_uncovered(row)
                uncovered_rows += 1
                adjusted.append(row)
                continue

            confidence = float(prior["confidence_factor"])
            effective_weight = round(base_weight * confidence, 4)
            if effective_weight <= 0:
                self._mark_uncovered(row)
                uncovered_rows += 1
                adjusted.append(row)
                continue

            prior_fpts = float(prior["prior_fpts"])
            row["market_history_source"] = "market_history"
            row["market_history_weight"] = effective_weight
            row["market_history_covered"] = True
            row["market_history_prior_fpts"] = round(prior_fpts, 2)
            row["market_history_confidence"] = round(confidence, 4)
            row["market_history_line_move"] = round(float(prior["line_move"]), 2)
            row["fpts"] = round(
                float(row["fpts"]) * (1.0 - effective_weight)
                + prior_fpts * effective_weight,
                1,
            )
            covered_rows += 1
            adjusted.append(row)

        adjusted.sort(key=lambda item: item["fpts"], reverse=True)
        for rank, row in enumerate(adjusted, start=1):
            row["rank"] = rank

        return adjusted, MarketHistoryStats(
            total_rows=total_rows,
            covered_rows=covered_rows,
            uncovered_rows=uncovered_rows,
        )

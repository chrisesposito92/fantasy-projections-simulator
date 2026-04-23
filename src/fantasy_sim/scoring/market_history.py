from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Protocol

import polars as pl

from fantasy_sim.config.loader import load_defaults, resolve_scoring
from fantasy_sim.data.market_history.features import normalize_market_history
from fantasy_sim.data.market_history.loader import MarketHistoryLoader
from fantasy_sim.data.market_history.models import MarketHistoryConfig


@dataclass
class MarketHistoryStats:
    total_rows: int
    covered_rows: int
    uncovered_rows: int


class MarketHistoryLoaderProtocol(Protocol):
    def load_weekly(self, seasons: list[int]) -> pl.DataFrame: ...


class MarketHistoryProjectionAdjuster:
    """Blend simulation outputs with historical market priors."""

    def __init__(
        self,
        config: MarketHistoryConfig,
        loader: MarketHistoryLoaderProtocol | None = None,
        scoring_config: dict[str, float] | None = None,
    ) -> None:
        self.config = config
        self.loader: MarketHistoryLoaderProtocol | None = loader
        if scoring_config is None:
            defaults = load_defaults()
            scoring_config = resolve_scoring(defaults["scoring"], "ppr")
        self.scoring_config = scoring_config
        self._prior_cache: dict[int, pl.DataFrame] = {}

    def season_priors(self, season: int) -> pl.DataFrame:
        """Load and cache normalized market priors for a season."""
        cached = self._prior_cache.get(season)
        if cached is not None:
            return cached

        if self.loader is None:
            self.loader = MarketHistoryLoader(self.config)

        raw = self.loader.load_weekly([season])
        normalized = normalize_market_history(raw, self.config)
        self._prior_cache[season] = normalized
        return normalized

    def _season_priors(self, season: int) -> pl.DataFrame:
        return self.season_priors(season)

    @staticmethod
    def _mark_uncovered(row: dict) -> dict:
        row["market_history_source"] = None
        row["market_history_weight"] = 0.0
        row["market_history_covered"] = False
        row.pop("market_history_prior_fpts", None)
        row.pop("market_history_confidence", None)
        row.pop("market_history_market_count", None)
        row.pop("market_history_markets_used", None)
        row.pop("market_history_anytime_td_prob", None)
        return row

    @staticmethod
    def _numeric_value(row: dict, key: str) -> float | None:
        value = row.get(key)
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        return None

    def _reception_value(self, position: str) -> float:
        return float(
            self.scoring_config.get(
                f"reception_{position.lower()}",
                self.scoring_config.get("reception", 0.0),
            )
        )

    def _non_passing_td_points(self) -> float:
        return float(
            max(
                self.scoring_config.get("rushing_td", 0.0),
                self.scoring_config.get("receiving_td", 0.0),
            )
        )

    @staticmethod
    def _at_least_one_to_expected_tds(probability: float) -> float:
        clipped = min(max(probability, 0.0), 1.0 - 1e-9)
        return -math.log1p(-clipped)

    def market_target(self, row: dict, prior: dict) -> tuple[float, list[str]]:
        """Return market-implied fantasy target and markets usable for this row."""
        current_fpts = float(row["fpts"])
        markets_used: list[str] = []
        delta_fpts = 0.0

        pass_yards = self._numeric_value(row, "pass_yards")
        pass_yards_line = prior.get("pass_yards_line")
        if pass_yards is not None and isinstance(pass_yards_line, (int, float)):
            delta_fpts += (
                float(pass_yards_line) - pass_yards
            ) * float(self.scoring_config.get("passing_yard", 0.0))
            markets_used.append("player_pass_yds")

        pass_tds = self._numeric_value(row, "pass_tds")
        pass_tds_line = prior.get("pass_tds_line")
        if pass_tds is not None and isinstance(pass_tds_line, (int, float)):
            delta_fpts += (
                float(pass_tds_line) - pass_tds
            ) * float(self.scoring_config.get("passing_td", 0.0))
            markets_used.append("player_pass_tds")

        rush_yards = self._numeric_value(row, "rush_yards")
        rush_yards_line = prior.get("rush_yards_line")
        if rush_yards is not None and isinstance(rush_yards_line, (int, float)):
            delta_fpts += (
                float(rush_yards_line) - rush_yards
            ) * float(self.scoring_config.get("rushing_yard", 0.0))
            markets_used.append("player_rush_yds")

        receptions = self._numeric_value(row, "receptions")
        receptions_line = prior.get("receptions_line")
        position = str(row.get("position", ""))
        if receptions is not None and isinstance(receptions_line, (int, float)):
            delta_fpts += (
                float(receptions_line) - receptions
            ) * self._reception_value(position)
            markets_used.append("player_receptions")

        receiving_yards = self._numeric_value(row, "receiving_yards")
        receiving_yards_line = prior.get("receiving_yards_line")
        if receiving_yards is not None and isinstance(receiving_yards_line, (int, float)):
            delta_fpts += (
                float(receiving_yards_line) - receiving_yards
            ) * float(self.scoring_config.get("receiving_yard", 0.0))
            markets_used.append("player_reception_yds")

        anytime_td_prob = prior.get("anytime_td_prob")
        if isinstance(anytime_td_prob, (int, float)):
            current_non_pass_tds = (
                (self._numeric_value(row, "rush_tds") or 0.0)
                + (self._numeric_value(row, "receiving_tds") or 0.0)
            )
            delta_fpts += (
                self._at_least_one_to_expected_tds(float(anytime_td_prob))
                - current_non_pass_tds
            ) * self._non_passing_td_points()
            markets_used.append("player_anytime_td")

        return current_fpts + delta_fpts, markets_used

    def _market_target(self, row: dict, prior: dict) -> tuple[float, list[str]]:
        return self.market_target(row, prior)

    def blend_supported_stats(self, row: dict, prior: dict, weight: float) -> None:
        """Blend stat columns that have compatible market lines."""
        stat_columns = (
            ("pass_attempts_line", "pass_attempts"),
            ("pass_yards_line", "pass_yards"),
            ("pass_tds_line", "pass_tds"),
            ("rush_attempts_line", "rush_attempts"),
            ("rush_yards_line", "rush_yards"),
            ("receptions_line", "receptions"),
            ("receiving_yards_line", "receiving_yards"),
        )
        for prior_key, row_key in stat_columns:
            if row_key not in row:
                continue
            current_value = self._numeric_value(row, row_key)
            target_value = prior.get(prior_key)
            if current_value is None or not isinstance(target_value, (int, float)):
                continue
            row[row_key] = round(
                current_value * (1.0 - weight) + float(target_value) * weight,
                1,
            )

    def _blend_supported_stats(self, row: dict, prior: dict, weight: float) -> None:
        self.blend_supported_stats(row, prior, weight)

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

        priors = self.season_priors(season).filter(pl.col("week") == week)
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

            prior_fpts, markets_used = self.market_target(row, prior)
            if not markets_used:
                self._mark_uncovered(row)
                uncovered_rows += 1
                adjusted.append(row)
                continue

            self.blend_supported_stats(row, prior, effective_weight)
            row["market_history_source"] = "market_history"
            row["market_history_weight"] = effective_weight
            row["market_history_covered"] = True
            row["market_history_prior_fpts"] = round(prior_fpts, 2)
            row["market_history_confidence"] = round(confidence, 4)
            row["market_history_market_count"] = len(markets_used)
            row["market_history_markets_used"] = ",".join(markets_used)
            anytime_td_prob = prior.get("anytime_td_prob")
            if isinstance(anytime_td_prob, (int, float)):
                row["market_history_anytime_td_prob"] = round(
                    float(anytime_td_prob),
                    4,
                )
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

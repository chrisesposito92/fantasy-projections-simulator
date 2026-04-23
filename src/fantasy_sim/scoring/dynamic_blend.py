"""Learned post-simulation blend of simulator, FF, and market sources."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Mapping

import numpy as np
import polars as pl

from fantasy_sim.data.ensemble.loader import FfOpportunityLoader
from fantasy_sim.data.ensemble.models import DynamicBlendConfig, EnsembleConfig
from fantasy_sim.data.ensemble.normalizer import normalize_ff_opportunity
from fantasy_sim.data.market_history.models import MarketHistoryConfig
from fantasy_sim.scoring.market_history import (
    MarketHistoryLoaderProtocol,
    MarketHistoryProjectionAdjuster,
)
from fantasy_sim.scoring.role_trend import ProjectionRow

SIMULATOR_SOURCE = "simulator"
FF_OPPORTUNITY_SOURCE = "ff_opportunity"
MARKET_HISTORY_SOURCE = "market_history"
SOURCE_ORDER = (SIMULATOR_SOURCE, FF_OPPORTUNITY_SOURCE, MARKET_HISTORY_SOURCE)
ARTIFACT_SCHEMA_VERSION = 1
BUNDLED_WEIGHTS_DIR = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "ensemble"
    / "artifacts"
    / "dynamic_blend"
    / "decision_s200"
)


@dataclass
class DynamicBlendStats:
    total_rows: int
    learned_rows: int
    fallback_rows: int
    simulator_only_rows: int
    ff_opportunity_rows: int
    market_history_rows: int


@dataclass
class SourceContext:
    row: dict
    sources: dict[str, float]
    bucket_key: str
    week_bucket: str
    source_mask: str
    market_confidence_bucket: str
    market_prior: dict | None
    market_confidence: float | None
    market_count: int | None
    markets_used: list[str]


def parse_week_bucket(bucket: str) -> tuple[int, int]:
    """Parse an inclusive week-bucket string such as '1-4'."""
    start_raw, end_raw = bucket.split("-", 1)
    start = int(start_raw)
    end = int(end_raw)
    if start > end:
        raise ValueError(f"Invalid week bucket '{bucket}': start > end")
    return start, end


def week_bucket_label(week: int, buckets: tuple[str, ...]) -> str:
    """Return the configured bucket label for a week."""
    for bucket in buckets:
        start, end = parse_week_bucket(bucket)
        if start <= week <= end:
            return bucket
    return "other"


def market_confidence_bucket(confidence: float | None) -> str:
    """Coarse confidence bucket used for learned-weight lookup."""
    if confidence is None:
        return "none"
    if confidence < 0.50:
        return "low"
    if confidence < 0.85:
        return "medium"
    return "high"


def source_mask(sources: Mapping[str, float]) -> str:
    """Return a stable source-mask string for available sources."""
    return "+".join(source for source in SOURCE_ORDER if source in sources)


def bucket_key(
    *,
    position: str,
    week_bucket: str,
    source_mask_value: str,
    market_confidence_bucket_value: str,
) -> str:
    return "|".join(
        [
            position or "UNK",
            week_bucket,
            source_mask_value,
            market_confidence_bucket_value,
        ]
    )


def clamp_weight(value: float) -> float:
    return min(max(float(value), 0.0), 1.0)


def fixed_default_weights(
    *,
    position: str,
    ff_available: bool,
    market_available: bool,
    market_confidence: float | None,
    ensemble_config: EnsembleConfig,
    market_history_config: MarketHistoryConfig | None,
) -> dict[str, float]:
    """Compute the current sequential fixed-blend weights as one convex blend."""
    ff_weight, market_weight = fixed_default_layer_weights(
        position=position,
        ff_available=ff_available,
        market_available=market_available,
        market_confidence=market_confidence,
        ensemble_config=ensemble_config,
        market_history_config=market_history_config,
    )

    return {
        SIMULATOR_SOURCE: round((1.0 - market_weight) * (1.0 - ff_weight), 6),
        MARKET_HISTORY_SOURCE: round(market_weight * (1.0 - ff_weight), 6),
        FF_OPPORTUNITY_SOURCE: round(ff_weight, 6),
    }


def fixed_default_layer_weights(
    *,
    position: str,
    ff_available: bool,
    market_available: bool,
    market_confidence: float | None,
    ensemble_config: EnsembleConfig,
    market_history_config: MarketHistoryConfig | None,
) -> tuple[float, float]:
    """Return legacy FF and market layer weights before they are collapsed."""
    ff_weight = 0.0
    if ff_available and ensemble_config.enabled and ensemble_config.ff_opportunity.enabled:
        ff_weight = clamp_weight(
            ensemble_config.ff_opportunity.weights.get(position, 0.0)
        )

    market_weight = 0.0
    if (
        market_available
        and market_history_config is not None
        and market_history_config.enabled
    ):
        confidence = market_confidence if market_confidence is not None else 0.0
        market_weight = clamp_weight(
            round(
                float(market_history_config.weights.get(position, 0.0))
                * float(confidence),
                4,
            )
        )

    return ff_weight, market_weight


def fixed_default_projection_value(
    *,
    sources: Mapping[str, float],
    position: str,
    market_confidence: float | None,
    ensemble_config: EnsembleConfig,
    market_history_config: MarketHistoryConfig | None,
) -> float:
    """Replay the legacy market-history then FF-opportunity rounded pipeline."""
    ff_weight, market_weight = fixed_default_layer_weights(
        position=position,
        ff_available=FF_OPPORTUNITY_SOURCE in sources,
        market_available=MARKET_HISTORY_SOURCE in sources,
        market_confidence=market_confidence,
        ensemble_config=ensemble_config,
        market_history_config=market_history_config,
    )

    value = float(sources[SIMULATOR_SOURCE])
    if MARKET_HISTORY_SOURCE in sources and market_weight > 0:
        value = round(
            value * (1.0 - market_weight)
            + float(sources[MARKET_HISTORY_SOURCE]) * market_weight,
            1,
        )
    if FF_OPPORTUNITY_SOURCE in sources and ff_weight > 0:
        value = round(
            value * (1.0 - ff_weight)
            + float(sources[FF_OPPORTUNITY_SOURCE]) * ff_weight,
            1,
        )
    return value


def normalize_weights(
    raw_weights: Mapping[str, float],
    available_sources: Mapping[str, float],
) -> dict[str, float] | None:
    """Normalize non-negative artifact weights across currently available sources."""
    weights = {
        source: max(float(raw_weights.get(source, 0.0)), 0.0)
        for source in SOURCE_ORDER
        if source in available_sources
    }
    total = sum(weights.values())
    if total <= 0:
        return None
    return {source: weight / total for source, weight in weights.items()}


def source_values_from_training_row(row: Mapping[str, object]) -> dict[str, float]:
    """Extract available blend-source values from a training row."""
    sources = {SIMULATOR_SOURCE: float(row["simulator_fpts"])}
    ff_value = row.get("ff_opportunity_fpts")
    if isinstance(ff_value, (int, float)):
        sources[FF_OPPORTUNITY_SOURCE] = float(ff_value)
    market_value = row.get("market_history_fpts")
    if isinstance(market_value, (int, float)):
        sources[MARKET_HISTORY_SOURCE] = float(market_value)
    return sources


def bucket_key_for_training_row(
    row: Mapping[str, object],
    config: DynamicBlendConfig,
) -> str:
    """Compute the learned-weight bucket key for a source training row."""
    sources = source_values_from_training_row(row)
    confidence = row.get("market_history_confidence")
    market_confidence = (
        float(confidence)
        if isinstance(confidence, (int, float))
        and MARKET_HISTORY_SOURCE in sources
        else None
    )
    return bucket_key(
        position=str(row.get("position", "")),
        week_bucket=week_bucket_label(int(row["week"]), config.week_buckets),
        source_mask_value=source_mask(sources),
        market_confidence_bucket_value=market_confidence_bucket(market_confidence),
    )


def _weight_compositions(parts: int, total: int) -> list[list[int]]:
    if parts == 1:
        return [[total]]
    compositions: list[list[int]] = []
    for head in range(total + 1):
        for tail in _weight_compositions(parts - 1, total - head):
            compositions.append([head, *tail])
    return compositions


def candidate_weight_grid(
    sources: tuple[str, ...],
    grid_step: float,
) -> list[dict[str, float]]:
    """Generate a convex weight grid for available sources."""
    if not sources:
        return []
    total = max(int(round(1.0 / max(grid_step, 1e-9))), 1)
    return [
        {
            source: value / total
            for source, value in zip(sources, composition, strict=True)
        }
        for composition in _weight_compositions(len(sources), total)
    ]


def _prediction_mae(
    rows: list[Mapping[str, object]],
    weights: Mapping[str, float],
) -> float:
    errors = []
    for row in rows:
        sources = source_values_from_training_row(row)
        actual = row.get("actual_fpts")
        if not isinstance(actual, (int, float)):
            continue
        pred = sum(sources[source] * float(weights.get(source, 0.0)) for source in sources)
        errors.append(abs(pred - float(actual)))
    return float(np.mean(errors)) if errors else 99.0


def _fixed_training_prediction(
    row: Mapping[str, object],
    *,
    ensemble_config: EnsembleConfig,
    market_history_config: MarketHistoryConfig | None,
) -> float:
    sources = source_values_from_training_row(row)
    confidence = row.get("market_history_confidence")
    return fixed_default_projection_value(
        sources=sources,
        position=str(row.get("position", "")),
        market_confidence=(
            float(confidence)
            if isinstance(confidence, (int, float))
            and MARKET_HISTORY_SOURCE in sources
            else None
        ),
        ensemble_config=ensemble_config,
        market_history_config=market_history_config,
    )


def fit_dynamic_blend_artifact(
    source_rows: list[Mapping[str, object]],
    *,
    test_season: int,
    source_seasons: list[int],
    sims: int,
    scoring: str,
    ensemble_config: EnsembleConfig,
    market_history_config: MarketHistoryConfig | None,
) -> dict:
    """Fit coarse learned blend weights against historical source rows."""
    config = ensemble_config.dynamic_blend
    grouped: dict[str, list[Mapping[str, object]]] = {}
    for row in source_rows:
        if not isinstance(row.get("actual_fpts"), (int, float)):
            continue
        key = bucket_key_for_training_row(row, config)
        grouped.setdefault(key, []).append(row)

    buckets: dict[str, dict] = {}
    fallback_buckets: dict[str, dict] = {}
    for key, rows in sorted(grouped.items()):
        week_count = len({(int(row["season"]), int(row["week"])) for row in rows})
        if len(rows) < config.min_bucket_rows or week_count < config.min_bucket_weeks:
            fallback_buckets[key] = {
                "reason": "sparse_bucket",
                "n_rows": len(rows),
                "n_weeks": week_count,
            }
            continue

        sources = tuple(
            source
            for source in SOURCE_ORDER
            if all(source in source_values_from_training_row(row) for row in rows)
        )
        if sources == (SIMULATOR_SOURCE,):
            fallback_buckets[key] = {
                "reason": "simulator_only",
                "n_rows": len(rows),
                "n_weeks": week_count,
            }
            continue

        fixed_errors = []
        for row in rows:
            actual = float(row["actual_fpts"])
            fixed_errors.append(
                abs(
                    _fixed_training_prediction(
                        row,
                        ensemble_config=ensemble_config,
                        market_history_config=market_history_config,
                    )
                    - actual
                )
            )
        fixed_mae = float(np.mean(fixed_errors)) if fixed_errors else 99.0

        best_weights: dict[str, float] | None = None
        best_mae = 99.0
        for candidate in candidate_weight_grid(sources, config.grid_step):
            mae = _prediction_mae(rows, candidate)
            if mae < best_mae:
                best_mae = mae
                best_weights = candidate

        if best_weights is None or best_mae >= fixed_mae - 1e-9:
            fallback_buckets[key] = {
                "reason": "no_training_lift",
                "n_rows": len(rows),
                "n_weeks": week_count,
                "training_mae": round(best_mae, 6),
                "fixed_mae": round(fixed_mae, 6),
            }
            continue

        buckets[key] = {
            "weights": {
                source: round(float(best_weights.get(source, 0.0)), 6)
                for source in SOURCE_ORDER
            },
            "n_rows": len(rows),
            "n_weeks": week_count,
            "source_mask": key.split("|")[2],
            "training_mae": round(best_mae, 6),
            "fixed_mae": round(fixed_mae, 6),
            "mae_delta": round(best_mae - fixed_mae, 6),
        }

    return {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "test_season": test_season,
        "source_seasons": source_seasons,
        "sims": sims,
        "scoring": scoring,
        "week_buckets": list(config.week_buckets),
        "grid_step": config.grid_step,
        "min_bucket_rows": config.min_bucket_rows,
        "min_bucket_weeks": config.min_bucket_weeks,
        "fallback": config.fallback,
        "buckets": buckets,
        "fallback_buckets": fallback_buckets,
    }


class DynamicBlendProjectionBlender:
    """Blend projection rows with learned source weights."""

    def __init__(
        self,
        ensemble_config: EnsembleConfig,
        *,
        market_history_config: MarketHistoryConfig | None = None,
        scoring_config: dict[str, float] | None = None,
        scoring: str = "ppr",
        ff_loader: object | None = None,
        market_loader: MarketHistoryLoaderProtocol | None = None,
    ) -> None:
        self.ensemble_config = ensemble_config
        self.config: DynamicBlendConfig = ensemble_config.dynamic_blend
        self.scoring = scoring
        self.market_history_config = market_history_config
        self._ff_loader = ff_loader
        self._market_adjuster = (
            MarketHistoryProjectionAdjuster(
                market_history_config,
                loader=market_loader,
                scoring_config=scoring_config,
            )
            if market_history_config is not None and market_history_config.enabled
            else None
        )
        self._ff_prior_cache: dict[int, pl.DataFrame] = {}
        self._artifact_cache: dict[int, dict | None] = {}

    def _ff_priors(self, season: int) -> pl.DataFrame:
        cached = self._ff_prior_cache.get(season)
        if cached is not None:
            return cached
        if not (
            self.ensemble_config.enabled
            and self.ensemble_config.ff_opportunity.enabled
        ):
            frame = pl.DataFrame()
            self._ff_prior_cache[season] = frame
            return frame
        if self._ff_loader is None:
            self._ff_loader = FfOpportunityLoader(
                config=self.ensemble_config.ff_opportunity
            )
        raw = self._ff_loader.load_weekly([season])
        normalized = normalize_ff_opportunity(raw, self.ensemble_config.ff_opportunity)
        self._ff_prior_cache[season] = normalized
        return normalized

    def _ff_prior_map(self, season: int, week: int) -> dict[str, dict]:
        priors = self._ff_priors(season)
        if priors.is_empty() or "week" not in priors.columns:
            return {}
        return {
            prior["player_id"]: prior
            for prior in priors.filter(pl.col("week") == week).iter_rows(named=True)
        }

    def _market_prior_map(self, season: int, week: int) -> dict[str, dict]:
        if self._market_adjuster is None:
            return {}
        priors = self._market_adjuster.season_priors(season)
        if priors.is_empty():
            return {}
        return {
            prior["player_id"]: prior
            for prior in priors.filter(pl.col("week") == week).iter_rows(named=True)
        }

    def _artifact(self, season: int) -> dict | None:
        if season in self._artifact_cache:
            return self._artifact_cache[season]

        weights_dir = (
            Path(self.config.weights_dir)
            if self.config.weights_dir
            else BUNDLED_WEIGHTS_DIR
        )
        path = weights_dir / f"weights_{season}.json"
        if not path.exists():
            self._artifact_cache[season] = None
            return None
        try:
            with path.open() as f:
                artifact = json.load(f)
        except (OSError, json.JSONDecodeError):
            self._artifact_cache[season] = None
            return None
        if artifact.get("schema_version") != ARTIFACT_SCHEMA_VERSION:
            self._artifact_cache[season] = None
            return None
        if artifact.get("scoring") != self.scoring:
            self._artifact_cache[season] = None
            return None
        self._artifact_cache[season] = artifact
        return artifact

    def _artifact_weights(
        self,
        artifact: dict | None,
        context: SourceContext,
    ) -> dict[str, float] | None:
        if artifact is None:
            return None
        bucket = artifact.get("buckets", {}).get(context.bucket_key)
        if not isinstance(bucket, dict):
            return None
        raw_weights = bucket.get("weights")
        if not isinstance(raw_weights, dict):
            return None
        return normalize_weights(raw_weights, context.sources)

    def source_contexts_for_week(
        self,
        projections: list[ProjectionRow],
        *,
        season: int,
        week: int,
    ) -> list[SourceContext]:
        ff_map = self._ff_prior_map(season, week)
        market_map = self._market_prior_map(season, week)
        contexts: list[SourceContext] = []

        for projection in projections:
            row = dict(projection)
            sim_value = float(row.get("fpts", 0.0))
            position = str(row.get("position", ""))
            pid = row.get("player_id")
            sources = {SIMULATOR_SOURCE: sim_value}

            ff_prior = ff_map.get(pid)
            if ff_prior is not None:
                sources[FF_OPPORTUNITY_SOURCE] = float(ff_prior["prior_fpts"])

            market_prior = market_map.get(pid)
            market_confidence: float | None = None
            market_count: int | None = None
            markets_used: list[str] = []
            if market_prior is not None and self._market_adjuster is not None:
                market_target, markets_used = self._market_adjuster.market_target(
                    row,
                    market_prior,
                )
                if markets_used:
                    sources[MARKET_HISTORY_SOURCE] = float(market_target)
                    market_confidence = float(market_prior["confidence_factor"])
                    market_count = len(markets_used)

            week_bucket = week_bucket_label(week, self.config.week_buckets)
            source_mask_value = source_mask(sources)
            confidence_bucket = market_confidence_bucket(market_confidence)
            contexts.append(
                SourceContext(
                    row=row,
                    sources=sources,
                    bucket_key=bucket_key(
                        position=position,
                        week_bucket=week_bucket,
                        source_mask_value=source_mask_value,
                        market_confidence_bucket_value=confidence_bucket,
                    ),
                    week_bucket=week_bucket,
                    source_mask=source_mask_value,
                    market_confidence_bucket=confidence_bucket,
                    market_prior=market_prior if MARKET_HISTORY_SOURCE in sources else None,
                    market_confidence=market_confidence,
                    market_count=market_count,
                    markets_used=markets_used,
                )
            )
        return contexts

    def source_rows_for_week(
        self,
        projections: list[ProjectionRow],
        *,
        season: int,
        week: int,
        actual_by_player_week: Mapping[str, Mapping[int, float]] | None = None,
    ) -> list[dict]:
        rows: list[dict] = []
        for context in self.source_contexts_for_week(
            projections,
            season=season,
            week=week,
        ):
            pid = context.row.get("player_id")
            actual_fpts = None
            if actual_by_player_week is not None and pid in actual_by_player_week:
                actual_fpts = actual_by_player_week[pid].get(week)
            rows.append(
                {
                    "season": season,
                    "week": week,
                    "player_id": pid,
                    "position": context.row.get("position", ""),
                    "team": context.row.get("team", ""),
                    "name": context.row.get("name", ""),
                    "bucket_key": context.bucket_key,
                    "week_bucket": context.week_bucket,
                    "source_mask": context.source_mask,
                    "market_confidence_bucket": context.market_confidence_bucket,
                    "simulator_fpts": context.sources.get(SIMULATOR_SOURCE),
                    "ff_opportunity_fpts": context.sources.get(FF_OPPORTUNITY_SOURCE),
                    "market_history_fpts": context.sources.get(MARKET_HISTORY_SOURCE),
                    "market_history_confidence": context.market_confidence,
                    "market_history_market_count": context.market_count,
                    "actual_fpts": actual_fpts,
                }
            )
        return rows

    def _fallback_weights(self, context: SourceContext) -> dict[str, float]:
        if self.config.fallback == "simulator_only":
            return {SIMULATOR_SOURCE: 1.0}
        weights = fixed_default_weights(
            position=str(context.row.get("position", "")),
            ff_available=FF_OPPORTUNITY_SOURCE in context.sources,
            market_available=MARKET_HISTORY_SOURCE in context.sources,
            market_confidence=context.market_confidence,
            ensemble_config=self.ensemble_config,
            market_history_config=self.market_history_config,
        )
        return normalize_weights(weights, context.sources) or {SIMULATOR_SOURCE: 1.0}

    def _fixed_default_fallback_fpts(self, context: SourceContext) -> float:
        if self.config.fallback == "simulator_only":
            return float(context.sources[SIMULATOR_SOURCE])
        return fixed_default_projection_value(
            sources=context.sources,
            position=str(context.row.get("position", "")),
            market_confidence=context.market_confidence,
            ensemble_config=self.ensemble_config,
            market_history_config=self.market_history_config,
        )

    def _fixed_default_market_stat_weight(self, context: SourceContext) -> float:
        if self.config.fallback == "simulator_only":
            return 0.0
        _, market_weight = fixed_default_layer_weights(
            position=str(context.row.get("position", "")),
            ff_available=FF_OPPORTUNITY_SOURCE in context.sources,
            market_available=MARKET_HISTORY_SOURCE in context.sources,
            market_confidence=context.market_confidence,
            ensemble_config=self.ensemble_config,
            market_history_config=self.market_history_config,
        )
        return market_weight

    @staticmethod
    def _apply_weights(sources: Mapping[str, float], weights: Mapping[str, float]) -> float:
        return sum(float(sources[source]) * float(weight) for source, weight in weights.items())

    @staticmethod
    def _stamp_metadata(
        row: dict,
        *,
        context: SourceContext,
        weights: Mapping[str, float],
        fallback_reason: str | None,
    ) -> None:
        row["dynamic_blend_source"] = "dynamic_blend"
        row["dynamic_blend_source_mask"] = context.source_mask
        row["dynamic_blend_bucket"] = context.bucket_key
        row["dynamic_blend_week_bucket"] = context.week_bucket
        row["dynamic_blend_market_confidence_bucket"] = context.market_confidence_bucket
        row["dynamic_blend_fallback_reason"] = fallback_reason
        row["dynamic_blend_covered"] = len(context.sources) > 1
        row["dynamic_blend_simulator_weight"] = round(
            float(weights.get(SIMULATOR_SOURCE, 0.0)),
            6,
        )
        row["dynamic_blend_ff_opportunity_weight"] = round(
            float(weights.get(FF_OPPORTUNITY_SOURCE, 0.0)),
            6,
        )
        row["dynamic_blend_market_history_weight"] = round(
            float(weights.get(MARKET_HISTORY_SOURCE, 0.0)),
            6,
        )
        if FF_OPPORTUNITY_SOURCE in context.sources:
            row["dynamic_blend_ff_opportunity_prior_fpts"] = round(
                context.sources[FF_OPPORTUNITY_SOURCE],
                2,
            )
        if MARKET_HISTORY_SOURCE in context.sources:
            row["dynamic_blend_market_history_prior_fpts"] = round(
                context.sources[MARKET_HISTORY_SOURCE],
                2,
            )
            row["dynamic_blend_market_history_confidence"] = round(
                float(context.market_confidence or 0.0),
                4,
            )
            row["dynamic_blend_market_history_market_count"] = context.market_count
            row["dynamic_blend_market_history_markets_used"] = ",".join(
                context.markets_used
            )

    def blend_week(
        self,
        projections: list[ProjectionRow],
        *,
        season: int,
        week: int,
    ) -> tuple[list[ProjectionRow], DynamicBlendStats]:
        total_rows = len(projections)
        if not projections or not self.config.enabled:
            return [dict(projection) for projection in projections], DynamicBlendStats(
                total_rows=total_rows,
                learned_rows=0,
                fallback_rows=0,
                simulator_only_rows=total_rows,
                ff_opportunity_rows=0,
                market_history_rows=0,
            )

        artifact = self._artifact(season)
        blended: list[ProjectionRow] = []
        learned_rows = 0
        fallback_rows = 0
        simulator_only_rows = 0
        ff_opportunity_rows = 0
        market_history_rows = 0

        for context in self.source_contexts_for_week(
            projections,
            season=season,
            week=week,
        ):
            row = dict(context.row)
            learned_weights = self._artifact_weights(artifact, context)
            fallback_reason: str | None = None
            if learned_weights is None:
                fallback_reason = (
                    "simulator_only"
                    if len(context.sources) == 1
                    else "missing_artifact"
                    if artifact is None
                    else "missing_bucket"
                )
                weights = self._fallback_weights(context)
                fallback_rows += 1
            else:
                weights = learned_weights
                learned_rows += 1

            market_weight = (
                self._fixed_default_market_stat_weight(context)
                if learned_weights is None
                else float(weights.get(MARKET_HISTORY_SOURCE, 0.0))
            )
            if (
                market_weight > 0
                and context.market_prior is not None
                and self._market_adjuster is not None
            ):
                self._market_adjuster.blend_supported_stats(
                    row,
                    context.market_prior,
                    market_weight,
                )

            row["fpts"] = (
                self._fixed_default_fallback_fpts(context)
                if learned_weights is None
                else round(self._apply_weights(context.sources, weights), 1)
            )
            self._stamp_metadata(
                row,
                context=context,
                weights=weights,
                fallback_reason=fallback_reason,
            )
            if len(context.sources) == 1:
                simulator_only_rows += 1
            if FF_OPPORTUNITY_SOURCE in context.sources:
                ff_opportunity_rows += 1
            if MARKET_HISTORY_SOURCE in context.sources:
                market_history_rows += 1
            blended.append(row)

        blended.sort(key=lambda row: row["fpts"], reverse=True)
        for rank, row in enumerate(blended, start=1):
            row["rank"] = rank

        return blended, DynamicBlendStats(
            total_rows=total_rows,
            learned_rows=learned_rows,
            fallback_rows=fallback_rows,
            simulator_only_rows=simulator_only_rows,
            ff_opportunity_rows=ff_opportunity_rows,
            market_history_rows=market_history_rows,
        )

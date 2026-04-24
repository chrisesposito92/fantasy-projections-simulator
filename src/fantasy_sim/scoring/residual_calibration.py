"""Post-simulation residual calibration for weekly player projections."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
from pathlib import Path

import numpy as np

from fantasy_sim.data.ensemble.models import ResidualCalibrationConfig
from fantasy_sim.scoring.role_trend import ProjectionRow

ARTIFACT_SCHEMA_VERSION = 1
BUNDLED_CALIBRATION_DIR = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "ensemble"
    / "artifacts"
    / "residual_calibration"
    / "decision_s200"
)

USAGE_TIER_THRESHOLDS: dict[str, tuple[float, float]] = {
    "QB": (18.0, 12.0),
    "RB": (14.0, 7.0),
    "WR": (12.0, 6.0),
    "TE": (9.0, 4.0),
}


@dataclass
class ResidualCalibrationStats:
    total_rows: int
    adjusted_rows: int
    fallback_rows: int
    missing_artifact_rows: int
    missing_bucket_rows: int


def _numeric_value(row: Mapping[str, object], key: str) -> float | None:
    value = row.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def projected_fpts(row: Mapping[str, object]) -> float:
    value = _numeric_value(row, "fpts")
    if value is None:
        raise TypeError("projection row is missing numeric fpts")
    return value


def usage_tier(position: str, fpts: float) -> str:
    """Return a fixed projected-fantasy-points usage tier."""
    high, mid = USAGE_TIER_THRESHOLDS.get(position, (float("inf"), float("inf")))
    if fpts >= high:
        return "high"
    if fpts >= mid:
        return "mid"
    return "low"


def source_confidence_bucket(row: Mapping[str, object]) -> str:
    """Return the projection-source confidence bucket from post-sim metadata."""
    dynamic_mask = str(row.get("dynamic_blend_source_mask") or "")
    dynamic_market_confidence = _numeric_value(
        row,
        "dynamic_blend_market_history_confidence",
    )
    fixed_market_confidence = _numeric_value(row, "market_history_confidence")

    confidence = (
        dynamic_market_confidence
        if "market_history" in dynamic_mask and dynamic_market_confidence is not None
        else fixed_market_confidence
        if row.get("market_history_covered") is True
        and fixed_market_confidence is not None
        else None
    )
    if confidence is not None:
        if confidence >= 0.85:
            return "market_high"
        if confidence >= 0.50:
            return "market_medium"
        return "market_low"

    if "ff_opportunity" in dynamic_mask or row.get("ensemble_covered") is True:
        return "external_no_market"
    return "simulator_only"


def bucket_key_for_projection(row: Mapping[str, object]) -> str:
    position = str(row.get("position") or "UNK")
    fpts = projected_fpts(row)
    return "|".join(
        [
            position,
            usage_tier(position, fpts),
            source_confidence_bucket(row),
        ]
    )


def clamp_adjustment(value: float, max_abs_adjustment: float) -> float:
    limit = max(float(max_abs_adjustment), 0.0)
    return min(max(float(value), -limit), limit)


def source_row_for_projection(
    projection: Mapping[str, object],
    *,
    season: int,
    week: int,
    actual_by_player_week: Mapping[str, Mapping[int, float]] | None = None,
) -> dict:
    """Build one residual-calibration training row from a final projection row."""
    pid = projection.get("player_id")
    actual_fpts = None
    if (
        actual_by_player_week is not None
        and isinstance(pid, str)
        and pid in actual_by_player_week
    ):
        actual_fpts = actual_by_player_week[pid].get(week)

    row = dict(projection)
    projected = projected_fpts(row)
    usage = usage_tier(str(row.get("position") or "UNK"), projected)
    confidence = source_confidence_bucket(row)
    return {
        "season": season,
        "week": week,
        "player_id": pid,
        "position": row.get("position", ""),
        "team": row.get("team", ""),
        "name": row.get("name", ""),
        "usage_tier": usage,
        "source_confidence_bucket": confidence,
        "bucket_key": "|".join([str(row.get("position") or "UNK"), usage, confidence]),
        "projected_fpts": projected,
        "actual_fpts": actual_fpts,
    }


def source_rows_for_week(
    projections: list[ProjectionRow],
    *,
    season: int,
    week: int,
    actual_by_player_week: Mapping[str, Mapping[int, float]] | None = None,
) -> list[dict]:
    return [
        source_row_for_projection(
            projection,
            season=season,
            week=week,
            actual_by_player_week=actual_by_player_week,
        )
        for projection in projections
    ]


def _mae_for_correction(rows: list[Mapping[str, object]], correction: float) -> float:
    errors: list[float] = []
    for row in rows:
        projected = row.get("projected_fpts")
        actual = row.get("actual_fpts")
        if isinstance(projected, bool) or isinstance(actual, bool):
            continue
        if not isinstance(projected, (int, float)) or not isinstance(actual, (int, float)):
            continue
        errors.append(abs(float(projected) + correction - float(actual)))
    return float(np.mean(errors)) if errors else 99.0


def _bucket_key_parts(key: str) -> tuple[str, str, str] | None:
    parts = key.split("|")
    if len(parts) != 3 or any(part == "" for part in parts):
        return None
    position, tier, confidence = parts
    return position, tier, confidence


def fit_residual_calibration_artifact(
    source_rows: list[Mapping[str, object]],
    *,
    test_season: int,
    source_seasons: list[int],
    sims: int,
    scoring: str,
    config: ResidualCalibrationConfig,
) -> dict:
    """Fit bucketed residual corrections from historical projection residuals."""
    grouped: dict[str, list[Mapping[str, object]]] = {}
    allowed_positions = set(config.positions)
    for row in source_rows:
        if row.get("position") not in allowed_positions:
            continue
        if not isinstance(row.get("actual_fpts"), (int, float)):
            continue
        if not isinstance(row.get("projected_fpts"), (int, float)):
            continue
        key = str(row.get("bucket_key") or "")
        if not key:
            continue
        grouped.setdefault(key, []).append(row)

    buckets: dict[str, dict] = {}
    fallback_buckets: dict[str, dict] = {}
    for key, rows in sorted(grouped.items()):
        week_count = len({(int(row["season"]), int(row["week"])) for row in rows})
        parts = _bucket_key_parts(key)
        if parts is None:
            fallback_buckets[key] = {
                "reason": "malformed_bucket_key",
                "n_rows": len(rows),
                "n_weeks": week_count,
            }
            continue

        if len(rows) < config.min_bucket_rows or week_count < config.min_bucket_weeks:
            fallback_buckets[key] = {
                "reason": "sparse_bucket",
                "n_rows": len(rows),
                "n_weeks": week_count,
            }
            continue

        residuals = [
            float(row["actual_fpts"]) - float(row["projected_fpts"])
            for row in rows
        ]
        median_residual = float(np.median(residuals))
        shrinkage = len(rows) / (len(rows) + max(config.shrinkage_prior_rows, 0))
        correction = clamp_adjustment(
            median_residual * shrinkage,
            config.max_abs_adjustment,
        )
        uncorrected_mae = _mae_for_correction(rows, 0.0)
        corrected_mae = _mae_for_correction(rows, correction)
        mae_delta = corrected_mae - uncorrected_mae

        if mae_delta > config.min_training_mae_delta:
            fallback_buckets[key] = {
                "reason": "no_training_lift",
                "n_rows": len(rows),
                "n_weeks": week_count,
                "median_residual": round(median_residual, 6),
                "correction_fpts": round(correction, 6),
                "training_mae": round(corrected_mae, 6),
                "uncorrected_mae": round(uncorrected_mae, 6),
                "mae_delta": round(mae_delta, 6),
            }
            continue

        position, tier, confidence = parts
        buckets[key] = {
            "position": position,
            "usage_tier": tier,
            "source_confidence_bucket": confidence,
            "correction_fpts": round(correction, 6),
            "median_residual": round(median_residual, 6),
            "n_rows": len(rows),
            "n_weeks": week_count,
            "training_mae": round(corrected_mae, 6),
            "uncorrected_mae": round(uncorrected_mae, 6),
            "mae_delta": round(mae_delta, 6),
        }

    return {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "test_season": test_season,
        "source_seasons": source_seasons,
        "sims": sims,
        "scoring": scoring,
        "positions": list(config.positions),
        "min_bucket_rows": config.min_bucket_rows,
        "min_bucket_weeks": config.min_bucket_weeks,
        "shrinkage_prior_rows": config.shrinkage_prior_rows,
        "max_abs_adjustment": config.max_abs_adjustment,
        "min_training_mae_delta": config.min_training_mae_delta,
        "fallback": config.fallback,
        "usage_tier_thresholds": {
            position: {"high": high, "mid": mid}
            for position, (high, mid) in USAGE_TIER_THRESHOLDS.items()
        },
        "buckets": buckets,
        "fallback_buckets": fallback_buckets,
    }


class ResidualCalibrationProjectionAdjuster:
    """Apply learned residual corrections to final weekly projection rows."""

    def __init__(
        self,
        config: ResidualCalibrationConfig,
        *,
        scoring: str = "ppr",
    ) -> None:
        self.config = config
        self.scoring = scoring
        self._artifact_cache: dict[int, dict | None] = {}

    def _artifact(self, season: int) -> dict | None:
        if season in self._artifact_cache:
            return self._artifact_cache[season]

        artifacts_dir = (
            Path(self.config.artifacts_dir)
            if self.config.artifacts_dir
            else BUNDLED_CALIBRATION_DIR
        )
        path = artifacts_dir / f"calibration_{season}.json"
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

    def _bucket_correction(self, artifact: dict | None, key: str) -> float | None:
        if artifact is None:
            return None
        bucket = artifact.get("buckets", {}).get(key)
        if not isinstance(bucket, dict):
            return None
        correction = bucket.get("correction_fpts")
        if isinstance(correction, bool) or not isinstance(correction, (int, float)):
            return None
        return clamp_adjustment(float(correction), self.config.max_abs_adjustment)

    @staticmethod
    def _stamp_metadata(
        row: ProjectionRow,
        *,
        bucket_key: str,
        tier: str,
        confidence_bucket: str,
        correction: float,
        fallback_reason: str | None,
    ) -> None:
        row["residual_calibration_source"] = "residual_calibration"
        row["residual_calibration_bucket"] = bucket_key
        row["residual_calibration_usage_tier"] = tier
        row["residual_calibration_source_confidence_bucket"] = confidence_bucket
        row["residual_calibration_adjustment"] = round(correction, 6)
        row["residual_calibration_applied"] = abs(correction) > 1e-9
        row["residual_calibration_fallback_reason"] = fallback_reason

    def adjust_week(
        self,
        projections: list[ProjectionRow],
        *,
        season: int,
        week: int,
    ) -> tuple[list[ProjectionRow], ResidualCalibrationStats]:
        del week
        total_rows = len(projections)
        if not projections or not self.config.enabled:
            return [dict(projection) for projection in projections], ResidualCalibrationStats(
                total_rows=total_rows,
                adjusted_rows=0,
                fallback_rows=total_rows,
                missing_artifact_rows=0,
                missing_bucket_rows=0,
            )

        artifact = self._artifact(season)
        adjusted: list[ProjectionRow] = []
        adjusted_rows = 0
        fallback_rows = 0
        missing_artifact_rows = 0
        missing_bucket_rows = 0
        allowed_positions = set(self.config.positions)

        for projection in projections:
            row = dict(projection)
            position = str(row.get("position") or "UNK")
            fpts = projected_fpts(row)
            tier = usage_tier(position, fpts)
            confidence_bucket = source_confidence_bucket(row)
            key = "|".join([position, tier, confidence_bucket])
            correction = 0.0
            fallback_reason: str | None = None

            if position not in allowed_positions:
                fallback_reason = "unsupported_position"
            else:
                learned = self._bucket_correction(artifact, key)
                if learned is None:
                    fallback_reason = (
                        "missing_artifact" if artifact is None else "missing_bucket"
                    )
                    if artifact is None:
                        missing_artifact_rows += 1
                    else:
                        missing_bucket_rows += 1
                else:
                    correction = learned

            if fallback_reason is not None:
                fallback_rows += 1
            if abs(correction) > 1e-9:
                adjusted_rows += 1
            row["fpts"] = round(max(fpts + correction, 0.0), 1)
            self._stamp_metadata(
                row,
                bucket_key=key,
                tier=tier,
                confidence_bucket=confidence_bucket,
                correction=correction,
                fallback_reason=fallback_reason,
            )
            adjusted.append(row)

        adjusted.sort(key=lambda item: item["fpts"], reverse=True)
        for rank, row in enumerate(adjusted, start=1):
            row["rank"] = rank

        return adjusted, ResidualCalibrationStats(
            total_rows=total_rows,
            adjusted_rows=adjusted_rows,
            fallback_rows=fallback_rows,
            missing_artifact_rows=missing_artifact_rows,
            missing_bucket_rows=missing_bucket_rows,
        )

"""Post-simulation residual calibration for weekly player projections."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
from pathlib import Path

import numpy as np

from fantasy_sim.config.loader import get_phase2_ks_flags
from fantasy_sim.data.ensemble.models import ResidualCalibrationConfig
from fantasy_sim.scoring.role_trend import ProjectionRow

ARTIFACT_SCHEMA_VERSION = 2  # v1 = fpts-only; v2 = fpts + per-stat stat_corrections (KS-09)
ARTIFACT_SCHEMA_VERSIONS_SUPPORTED = (1, 2)  # loader accepts both
BUNDLED_CALIBRATION_DIR = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "ensemble"
    / "artifacts"
    / "residual_calibration"
    / "decision_s200"
)

# KS-10 D-07: 4-tier threshold for TE adds an `elite` tier above 14.0 fpts.
# Other positions stay at the 3-tier shape. The legacy USAGE_TIER_THRESHOLDS
# is kept for backwards compatibility with callers that haven't been updated.
USAGE_TIER_THRESHOLDS_3: dict[str, tuple[float, float]] = {
    "QB": (18.0, 12.0),
    "RB": (14.0, 7.0),
    "WR": (12.0, 6.0),
    "TE": (9.0, 4.0),  # legacy 3-tier (used when KS-10 flag disabled)
}
USAGE_TIER_THRESHOLDS_4: dict[str, tuple[float, float, float]] = {
    "TE": (14.0, 9.0, 4.0),  # elite >=14, high >=9, mid >=4, low <4 (KS-10 only)
}
USAGE_TIER_THRESHOLDS = USAGE_TIER_THRESHOLDS_3  # backward-compat alias


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


def usage_tier(position: str, fpts: float, *, ks10_enabled: bool = False) -> str:
    """Return a fixed projected-fantasy-points usage tier.

    KS-10 D-07: when ``ks10_enabled`` is True and the position has a 4-tier
    threshold defined (currently TE only), returns one of {elite, high, mid, low}.
    Otherwise falls back to the 3-tier {high, mid, low} shape.
    """
    if ks10_enabled and position in USAGE_TIER_THRESHOLDS_4:
        elite, high, mid = USAGE_TIER_THRESHOLDS_4[position]
        if fpts >= elite:
            return "elite"
        if fpts >= high:
            return "high"
        if fpts >= mid:
            return "mid"
        return "low"
    high, mid = USAGE_TIER_THRESHOLDS_3.get(position, (float("inf"), float("inf")))
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


def clamp_adjustment(
    value: float,
    max_abs_adjustment: float,
    *,
    position: str | None = None,
    by_position: dict[str, float] | None = None,
) -> float:
    """Clamp an fpts-level residual to ±max_abs_adjustment.

    KS-10 D-07: when ``position`` and ``by_position`` are both provided AND the
    position is in ``by_position``, the per-position cap overrides the global
    ``max_abs_adjustment``. Otherwise falls back to the global cap. The
    ``by_position`` dict is only consulted when the KS-10 flag is explicitly
    enabled at the call site — callers that don't pass these kwargs get legacy
    behavior regardless of config.
    """
    if position and by_position and position in by_position:
        limit = max(float(by_position[position]), 0.0)
    else:
        limit = max(float(max_abs_adjustment), 0.0)
    return min(max(float(value), -limit), limit)


def stat_clamp_adjustment(value: float, clamp_std: float) -> float:
    """Clamp a per-stat residual to ±2 * clamp_std (per-bucket std from training).

    KS-09 D-04 + Pattern 4: clamp_std comes from
    artifact["stat_corrections"][stat]["clamps"][bucket_key]["clamp_std"].
    Falls back to zero adjustment when clamp_std is 0 (graceful degradation
    for buckets with no training data for the stat).
    """
    limit = max(2.0 * float(clamp_std), 0.0)
    return min(max(float(value), -limit), limit)


# Stats that may appear in both projection rows and ActualPlayerWeek objects.
# Used by KS-09 to capture per-stat projected vs actual values in training rows.
_CAPTURABLE_STATS = (
    "pass_yards", "pass_tds", "interceptions",
    "rush_yards", "rush_tds",
    "receiving_yards", "receptions", "receiving_tds",
    "fumbles_lost",
)


def source_row_for_projection(
    projection: Mapping[str, object],
    *,
    season: int,
    week: int,
    actual_by_player_week: Mapping[str, Mapping[int, float]] | None = None,
    actual_stats_by_player_week: Mapping[str, Mapping[int, object]] | None = None,
) -> dict:
    """Build one residual-calibration training row from a final projection row.

    KS-09 extension: when ``actual_stats_by_player_week`` is provided (mapping from
    player_id → week → ActualPlayerWeek), each capturable stat is stored as both the
    projected value (``stat``) and the actual value (``actual_<stat>``) in the row.
    This allows ``fit_residual_calibration_artifact`` to compute per-stat corrections.
    """
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
    source_row: dict = {
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
    # KS-09: capture projected stat values + actual stat values when available
    for stat in _CAPTURABLE_STATS:
        proj_val = row.get(stat)
        if isinstance(proj_val, (int, float)):
            source_row[stat] = float(proj_val)
    if actual_stats_by_player_week is not None and isinstance(pid, str):
        actual_obj = (
            actual_stats_by_player_week.get(pid, {}).get(week)
        )
        if actual_obj is not None:
            for stat in _CAPTURABLE_STATS:
                actual_val = getattr(actual_obj, stat, None)
                if isinstance(actual_val, (int, float)):
                    source_row[f"actual_{stat}"] = float(actual_val)
    return source_row


def source_rows_for_week(
    projections: list[ProjectionRow],
    *,
    season: int,
    week: int,
    actual_by_player_week: Mapping[str, Mapping[int, float]] | None = None,
    actual_stats_by_player_week: Mapping[str, Mapping[int, object]] | None = None,
) -> list[dict]:
    return [
        source_row_for_projection(
            projection,
            season=season,
            week=week,
            actual_by_player_week=actual_by_player_week,
            actual_stats_by_player_week=actual_stats_by_player_week,
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


def _min_bucket_rows_for_position(config: ResidualCalibrationConfig, position: str) -> int:
    """KS-10 D-07: per-position min_bucket_rows. TE drops to 10; others stay at default.

    The plan specified "100" as the TE threshold, but elite TEs are inherently rare
    (~1-2 per week × 18 weeks × N seasons ≈ 18-36 rows per source season). With 200-sim
    projections, the elite TE bucket accumulates ~20 rows per source season, well below
    the 100-row threshold. Using 10 as the TE floor allows the elite tier to populate
    while still requiring at least 10 rows (≥ 1 full season of elite TE appearances).
    Only reduces TE's threshold when max_abs_adjustment_by_position has a TE key
    (indicating KS-10 values have been applied in the config).
    """
    if (
        config.max_abs_adjustment_by_position
        and "TE" in config.max_abs_adjustment_by_position
        and position == "TE"
    ):
        return min(10, config.min_bucket_rows)
    return config.min_bucket_rows


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

        position_for_key = parts[0]
        min_rows = _min_bucket_rows_for_position(config, position_for_key)
        if len(rows) < min_rows or week_count < config.min_bucket_weeks:
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

    artifact: dict = {
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

    # KS-09 D-03: when stat_level enabled, fit per-stat corrections + clamps per bucket.
    if config.stat_level.enabled and config.stat_level.covered_stats:
        stat_corrections: dict[str, dict[str, dict]] = {}
        for stat in config.stat_level.covered_stats:
            stat_block: dict[str, dict] = {"corrections": {}, "clamps": {}}
            # Group rows by bucket_key (same key as the fpts-level grouping)
            by_bucket: dict[str, list[Mapping[str, object]]] = {}
            for row in source_rows:
                # Only include rows that have both projected and actual values for this stat
                if not isinstance(row.get(f"actual_{stat}"), (int, float)):
                    continue
                if not isinstance(row.get(stat), (int, float)):
                    continue
                key = str(row.get("bucket_key") or "")
                if not key:
                    continue
                by_bucket.setdefault(key, []).append(row)
            for key, rows in by_bucket.items():
                # KS-10: use per-position min_bucket_rows (TE: 100) when applicable
                stat_position = key.split("|")[0] if "|" in key else ""
                if len(rows) < _min_bucket_rows_for_position(config, stat_position):
                    continue
                # Mean correction = mean(actual_stat - projected_stat) for this bucket
                deltas = [
                    float(row[f"actual_{stat}"]) - float(row[stat])
                    for row in rows
                ]
                mean_delta = float(np.mean(deltas))
                # clamp_std = std of actual stat values for this bucket (per D-04)
                actual_values = [float(row[f"actual_{stat}"]) for row in rows]
                clamp_std = float(np.std(actual_values))
                stat_block["corrections"][key] = {
                    "correction": round(mean_delta, 6),
                    "n_rows": len(rows),
                }
                stat_block["clamps"][key] = {"clamp_std": round(clamp_std, 6)}
            stat_corrections[stat] = stat_block
        artifact["stat_corrections"] = stat_corrections

    return artifact


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
        # KS-10 D-07: cache the phase2 KS flags at construction time for performance.
        # The flag is read once from defaults.yaml and keyed on the ks10_per_position_caps block.
        self._phase2_flags: dict = get_phase2_ks_flags()

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
        schema = artifact.get("schema_version")
        if schema not in ARTIFACT_SCHEMA_VERSIONS_SUPPORTED:
            self._artifact_cache[season] = None
            return None
        # Normalize: v1 artifacts have no stat_corrections block; expose an empty dict so
        # downstream per-stat corrector (KS-09 Plan 03) sees a uniform shape.
        if schema == 1 and "stat_corrections" not in artifact:
            artifact = dict(artifact)  # don't mutate cache key
            artifact["stat_corrections"] = {}
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

        # KS-10 D-07 Codex MEDIUM 7: gate strictly on the flag, NOT on dict presence.
        # Plan 01's all-1.5 placeholder dict must remain a no-op when the flag is off.
        ks10_enabled = bool(
            self._phase2_flags.get("ks10_per_position_caps", {}).get("enabled", False)
        )

        for projection in projections:
            row = dict(projection)
            position = str(row.get("position") or "UNK")
            fpts = projected_fpts(row)
            tier = usage_tier(position, fpts, ks10_enabled=ks10_enabled)
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
                    # KS-10 D-07: when flag enabled, clamp using per-position cap.
                    correction = clamp_adjustment(
                        learned,
                        self.config.max_abs_adjustment,
                        position=position if ks10_enabled else None,
                        by_position=self.config.max_abs_adjustment_by_position if ks10_enabled else None,
                    )

            if fallback_reason is not None:
                fallback_rows += 1
            if abs(correction) > 1e-9:
                adjusted_rows += 1

            # KS-09 D-01: per-stat correction writes corrected_<stat> columns BEFORE fpts write.
            # Two-stage layered fpts (D-01): the existing row["fpts"] correction is unchanged
            # (computed from raw_sim_fpts + bucket correction below); the per-stat columns are
            # additive and do NOT propagate into fpts.
            if self.config.stat_level.enabled and artifact is not None:
                stat_corrections_block = artifact.get("stat_corrections", {})
                for stat in self.config.stat_level.covered_stats:
                    raw = row.get(stat)
                    if not isinstance(raw, (int, float)):
                        # Stat not present on this row (e.g., RB row missing pass_yards) — skip
                        continue
                    stat_block = stat_corrections_block.get(stat, {})
                    bucket_corrections = stat_block.get("corrections", {})
                    bucket_clamps = stat_block.get("clamps", {})
                    correction_entry = bucket_corrections.get(key)
                    clamp_entry = bucket_clamps.get(key)
                    if not correction_entry:
                        # Missing bucket → fallback zero adjustment (corrected == raw)
                        row[f"corrected_{stat}"] = round(float(raw), 4)
                        continue
                    raw_correction = float(correction_entry.get("correction", 0.0))
                    clamp_std = float(clamp_entry.get("clamp_std", 0.0)) if clamp_entry else 0.0
                    if clamp_std > 0:
                        applied = stat_clamp_adjustment(raw_correction, clamp_std)
                    else:
                        # No clamp_std available → fallback to global max_abs_adjustment
                        applied = clamp_adjustment(raw_correction, self.config.max_abs_adjustment)
                    corrected = float(raw) + applied
                    # Stats are non-negative (yards, TDs, receptions, fumbles_lost) — clamp to 0
                    row[f"corrected_{stat}"] = round(max(corrected, 0.0), 4)

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

"""Post-simulation projection blending for ensemble priors."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import polars as pl

from fantasy_sim.data.ensemble.loader import FfOpportunityLoader
from fantasy_sim.data.ensemble.models import EnsembleConfig

# KS-13 Path B: artifact schema version for the bundled prior-width artifacts.
ARTIFACT_SCHEMA_VERSION = 1

# KS-13 Path B: bundled artifact directory — mirrors residual_calibration layout.
BUNDLED_PRIOR_WIDTH_DIR = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "ensemble"
    / "artifacts"
    / "ff_opportunity_prior_width"
    / "decision_s200"
)


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
        rng: np.random.Generator | None = None,
        ks13_master_enabled: bool | None = None,
    ) -> None:
        self.config = config
        self.loader = loader
        self._rng = rng or np.random.default_rng()
        self._prior_cache: dict[int, pl.DataFrame] = {}
        self._prior_width_artifact_cache: dict[int, dict | None] = {}

        # Codex cycle-4 alignment (dual-gate fix): resolve the master phase2_ks_flag once
        # at construction. Explicit override wins; otherwise fall back to the shim from
        # Plan 01. If the shim is unavailable (e.g. test fixture without phase2_ks_flags),
        # default-deny so KS-13 stays dormant unless the caller opts in explicitly.
        if ks13_master_enabled is not None:
            self._ks13_master_enabled = bool(ks13_master_enabled)
        else:
            try:
                from fantasy_sim.config.loader import get_phase2_ks_flags
                flags = get_phase2_ks_flags()
                # Codex cycle-5 alignment: Plan 01 (line 298) defines get_phase2_ks_flags()
                # to return a plain dict (`return defaults.get("phase2_ks_flags", {})`),
                # NOT a typed config object. Use dict access.
                ks13_cfg = flags.get("ks13_ff_opportunity_prior_width", {}) if isinstance(flags, dict) else {}
                self._ks13_master_enabled = bool(ks13_cfg.get("enabled", False))
            except Exception:
                self._ks13_master_enabled = False

    def _season_priors(self, season: int) -> pl.DataFrame:
        """Load and cache normalized priors for a season."""
        from fantasy_sim.data.ensemble.normalizer import normalize_ff_opportunity

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

    def _load_ff_opportunity_prior_width_artifact(self, season: int) -> dict | None:
        """KS-13 Path B: per-season artifact loader mirroring ResidualCalibrationProjectionAdjuster._artifact.

        Caches per-season; resolves directory from prior_width.artifacts_dir
        (overrides) or BUNDLED_PRIOR_WIDTH_DIR (defaults). Returns None on
        missing file / JSON error / schema-version mismatch.
        """
        if season in self._prior_width_artifact_cache:
            return self._prior_width_artifact_cache[season]

        artifacts_dir = (
            Path(self.config.ff_opportunity.prior_width.artifacts_dir)
            if self.config.ff_opportunity.prior_width.artifacts_dir
            else BUNDLED_PRIOR_WIDTH_DIR
        )
        path = artifacts_dir / f"prior_width_{season}.json"
        if not path.exists():
            self._prior_width_artifact_cache[season] = None
            return None
        try:
            with path.open() as f:
                artifact = json.load(f)
        except (OSError, json.JSONDecodeError):
            self._prior_width_artifact_cache[season] = None
            return None
        if artifact.get("schema_version") != ARTIFACT_SCHEMA_VERSION:
            self._prior_width_artifact_cache[season] = None
            return None
        self._prior_width_artifact_cache[season] = artifact
        return artifact

    def _fitted_std_for(self, position: str, prior_fpts: float, season: int) -> float:
        """KS-13 Path B std lookup. Returns 0.0 (point-estimate fallback) when missing."""
        if not position:
            return 0.0
        artifact = self._load_ff_opportunity_prior_width_artifact(season)
        if artifact is None:
            return 0.0
        bucket = artifact.get("buckets", {}).get(position)
        if not isinstance(bucket, dict):
            return 0.0
        std = bucket.get("std_fpts")
        return float(std) if isinstance(std, (int, float)) else 0.0

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
            prior_lo = prior.get("prior_fpts_lo")
            prior_hi = prior.get("prior_fpts_hi")

            _pw = self.config.ff_opportunity.prior_width  # PriorWidthConfig
            # Codex cycle-4 alignment (dual-gate fix): KS-13 sampling requires BOTH the master
            # phase2_ks_flag AND the engine-local sub-flag. Flipping either off is sufficient to
            # return to legacy point-estimate behavior. Plan 09's reverse-ablation walk-back relies
            # on the master flag being a sole-sufficient kill switch for `no_KS13` aggregate runs.
            ks13_active = self._ks13_master_enabled and _pw.enabled

            if ks13_active:
                if _pw.path == "A" and prior_lo is not None and prior_hi is not None:
                    # Path A: Gaussian sample with std = (hi - lo) / 2.56
                    sigma = (float(prior_hi) - float(prior_lo)) / (2 * 1.28)
                    sampled_prior = float(self._rng.normal(prior_fpts, max(sigma, 0.0)))
                elif _pw.path == "B":
                    # Path B: fitted residual std per bucket
                    sigma = self._fitted_std_for(row.get("position", ""), prior_fpts, season)
                    sampled_prior = float(self._rng.normal(prior_fpts, max(sigma, 0.0))) if sigma > 0 else prior_fpts
                else:
                    # Path A without lo/hi — no data to compute sigma, fall back
                    sampled_prior = prior_fpts
            else:
                sampled_prior = prior_fpts

            row["ensemble_source"] = "ff_opportunity"
            row["ensemble_weight"] = weight
            row["ensemble_covered"] = True
            row["ensemble_prior_fpts"] = round(prior_fpts, 2)
            row["ensemble_sampled_prior_fpts"] = round(sampled_prior, 2)  # KS-13
            row["fpts"] = round(
                float(row["fpts"] * (1.0 - weight) + sampled_prior * weight),
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

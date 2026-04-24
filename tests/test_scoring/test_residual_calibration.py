import json
from types import SimpleNamespace

from fantasy_sim.data.ensemble.models import ResidualCalibrationConfig
from fantasy_sim.scoring.projection_layers import apply_projection_layers
from fantasy_sim.scoring.residual_calibration import (
    ARTIFACT_SCHEMA_VERSION,
    BUNDLED_CALIBRATION_DIR,
    ResidualCalibrationProjectionAdjuster,
    fit_residual_calibration_artifact,
    source_confidence_bucket,
    usage_tier,
)


def _config(tmp_path, **overrides) -> ResidualCalibrationConfig:
    values = {
        "enabled": True,
        "artifacts_dir": str(tmp_path),
        "positions": ("QB", "RB", "WR", "TE"),
        "min_bucket_rows": 2,
        "min_bucket_weeks": 1,
        "shrinkage_prior_rows": 0,
        "max_abs_adjustment": 1.5,
        "min_training_mae_delta": -0.01,
        "fallback": "zero",
    }
    values.update(overrides)
    return ResidualCalibrationConfig(**values)


def test_usage_tier_thresholds_are_position_specific():
    assert usage_tier("QB", 18.0) == "high"
    assert usage_tier("QB", 12.0) == "mid"
    assert usage_tier("QB", 11.9) == "low"
    assert usage_tier("RB", 14.0) == "high"
    assert usage_tier("WR", 6.0) == "mid"
    assert usage_tier("TE", 3.9) == "low"


def test_source_confidence_bucket_uses_market_then_external_sources():
    assert (
        source_confidence_bucket(
            {
                "dynamic_blend_source_mask": "simulator+ff_opportunity+market_history",
                "dynamic_blend_market_history_confidence": 0.90,
            }
        )
        == "market_high"
    )
    assert (
        source_confidence_bucket(
            {"market_history_covered": True, "market_history_confidence": 0.50}
        )
        == "market_medium"
    )
    assert (
        source_confidence_bucket(
            {"dynamic_blend_source_mask": "simulator+ff_opportunity"}
        )
        == "external_no_market"
    )
    assert source_confidence_bucket({"fpts": 10.0}) == "simulator_only"


def test_adjust_week_applies_artifact_corrections_and_recomputes_rank(tmp_path):
    artifact = {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "scoring": "ppr",
        "buckets": {
            "QB|high|market_high": {"correction_fpts": -1.0},
            "WR|mid|external_no_market": {"correction_fpts": 1.5},
        },
    }
    (tmp_path / "calibration_2024.json").write_text(json.dumps(artifact))
    adjuster = ResidualCalibrationProjectionAdjuster(_config(tmp_path))

    adjusted, stats = adjuster.adjust_week(
        [
            {
                "player_id": "QB1",
                "position": "QB",
                "fpts": 19.0,
                "rank": 1,
                "dynamic_blend_source_mask": "simulator+ff_opportunity+market_history",
                "dynamic_blend_market_history_confidence": 0.90,
            },
            {
                "player_id": "WR1",
                "position": "WR",
                "fpts": 11.0,
                "rank": 2,
                "ensemble_covered": True,
            },
        ],
        season=2024,
        week=1,
    )

    qb = next(row for row in adjusted if row["player_id"] == "QB1")
    wr = next(row for row in adjusted if row["player_id"] == "WR1")

    assert qb["fpts"] == 18.0
    assert qb["rank"] == 1
    assert qb["residual_calibration_adjustment"] == -1.0
    assert qb["residual_calibration_fallback_reason"] is None
    assert wr["fpts"] == 12.5
    assert wr["rank"] == 2
    assert wr["residual_calibration_bucket"] == "WR|mid|external_no_market"
    assert stats.adjusted_rows == 2
    assert stats.fallback_rows == 0


def test_adjust_week_missing_or_invalid_artifact_falls_back_to_zero(tmp_path):
    artifact = {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "scoring": "half_ppr",
        "buckets": {"QB|high|simulator_only": {"correction_fpts": 1.0}},
    }
    (tmp_path / "calibration_2024.json").write_text(json.dumps(artifact))
    adjuster = ResidualCalibrationProjectionAdjuster(_config(tmp_path), scoring="ppr")

    adjusted, stats = adjuster.adjust_week(
        [{"player_id": "QB1", "position": "QB", "fpts": 20.0, "rank": 1}],
        season=2024,
        week=1,
    )

    assert adjusted[0]["fpts"] == 20.0
    assert adjusted[0]["residual_calibration_fallback_reason"] == "missing_artifact"
    assert stats.adjusted_rows == 0
    assert stats.missing_artifact_rows == 1


def test_fit_residual_calibration_artifact_learns_shrunken_median_correction(tmp_path):
    rows = [
        {
            "season": 2022,
            "week": 1,
            "player_id": "QB1",
            "position": "QB",
            "bucket_key": "QB|high|simulator_only",
            "projected_fpts": 20.0,
            "actual_fpts": 21.0,
        },
        {
            "season": 2022,
            "week": 2,
            "player_id": "QB1",
            "position": "QB",
            "bucket_key": "QB|high|simulator_only",
            "projected_fpts": 19.0,
            "actual_fpts": 20.0,
        },
    ]

    artifact = fit_residual_calibration_artifact(
        rows,
        test_season=2023,
        source_seasons=[2022],
        sims=50,
        scoring="ppr",
        config=_config(tmp_path),
    )

    bucket = artifact["buckets"]["QB|high|simulator_only"]
    assert bucket["correction_fpts"] == 1.0
    assert bucket["mae_delta"] == -1.0


def test_fit_residual_calibration_artifact_falls_back_without_training_lift(tmp_path):
    rows = [
        {
            "season": 2022,
            "week": 1,
            "player_id": "WR1",
            "position": "WR",
            "bucket_key": "WR|mid|external_no_market",
            "projected_fpts": 10.0,
            "actual_fpts": 10.0,
        },
        {
            "season": 2022,
            "week": 2,
            "player_id": "WR1",
            "position": "WR",
            "bucket_key": "WR|mid|external_no_market",
            "projected_fpts": 11.0,
            "actual_fpts": 11.0,
        },
    ]

    artifact = fit_residual_calibration_artifact(
        rows,
        test_season=2023,
        source_seasons=[2022],
        sims=50,
        scoring="ppr",
        config=_config(tmp_path),
    )

    assert artifact["buckets"] == {}
    assert (
        artifact["fallback_buckets"]["WR|mid|external_no_market"]["reason"]
        == "no_training_lift"
    )


def test_bundled_decision_artifacts_are_available():
    seasons = [2023, 2024]

    for season in seasons:
        path = BUNDLED_CALIBRATION_DIR / f"calibration_{season}.json"
        artifact = json.loads(path.read_text())

        assert artifact["schema_version"] == ARTIFACT_SCHEMA_VERSION
        assert artifact["test_season"] == season
        assert artifact["buckets"]


def test_apply_projection_layers_runs_residual_after_dynamic_and_skips_fixed_layers():
    order: list[str] = []

    class _Trend:
        def adjust_week(self, projections, *, season, week):
            order.append("trend")
            return [dict(projections[0], fpts=12.0)], SimpleNamespace()

    class _Dynamic:
        def blend_week(self, projections, *, season, week):
            order.append("dynamic")
            assert projections[0]["fpts"] == 12.0
            return [dict(projections[0], fpts=13.0)], SimpleNamespace()

    class _Residual:
        def adjust_week(self, projections, *, season, week):
            order.append("residual")
            assert projections[0]["fpts"] == 13.0
            return [dict(projections[0], fpts=14.0)], SimpleNamespace()

    class _Fixed:
        def adjust_week(self, projections, *, season, week):
            raise AssertionError("fixed market layer should be skipped")

        def blend_week(self, projections, *, season, week):
            raise AssertionError("fixed ensemble layer should be skipped")

    adjusted = apply_projection_layers(
        [{"player_id": "QB1", "position": "QB", "fpts": 10.0}],
        season=2024,
        week=1,
        role_trend_adjuster=_Trend(),
        market_history_adjuster=_Fixed(),
        ensembler=_Fixed(),
        dynamic_blender=_Dynamic(),
        residual_calibrator=_Residual(),
    )

    assert adjusted[0]["fpts"] == 14.0
    assert order == ["trend", "dynamic", "residual"]

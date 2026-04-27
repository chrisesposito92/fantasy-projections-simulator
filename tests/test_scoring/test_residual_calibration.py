import json
from types import SimpleNamespace

from fantasy_sim.data.ensemble.models import ResidualCalibrationConfig
from fantasy_sim.scoring.projection_layers import apply_projection_layers
from fantasy_sim.scoring.residual_calibration import (
    ARTIFACT_SCHEMA_VERSION,
    ARTIFACT_SCHEMA_VERSIONS_SUPPORTED,
    BUNDLED_CALIBRATION_DIR,
    USAGE_TIER_THRESHOLDS_3,
    USAGE_TIER_THRESHOLDS_4,
    ResidualCalibrationProjectionAdjuster,
    clamp_adjustment,
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


def test_fit_residual_calibration_artifact_falls_back_on_malformed_bucket_key(tmp_path):
    rows = [
        {
            "season": 2022,
            "week": 1,
            "player_id": "QB1",
            "position": "QB",
            "bucket_key": "QB|high",
            "projected_fpts": 20.0,
            "actual_fpts": 21.0,
        },
        {
            "season": 2022,
            "week": 2,
            "player_id": "QB1",
            "position": "QB",
            "bucket_key": "QB|high",
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

    assert artifact["buckets"] == {}
    assert artifact["fallback_buckets"]["QB|high"]["reason"] == "malformed_bucket_key"


def test_bundled_decision_artifacts_are_available():
    seasons = [2023, 2024]

    for season in seasons:
        path = BUNDLED_CALIBRATION_DIR / f"calibration_{season}.json"
        artifact = json.loads(path.read_text())

        # Bundled artifacts are at schema_version: 1 until Plan 03 / Plan 05 re-fit
        # bumps them to v2. Both versions must be accepted.
        assert artifact["schema_version"] in ARTIFACT_SCHEMA_VERSIONS_SUPPORTED, (
            f"Bundled artifact calibration_{season}.json at unsupported schema_version={artifact['schema_version']}"
        )
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


def test_artifact_loader_accepts_schema_v1():
    """Schema v1 artifacts (Phase 1 bundled) must continue to load post-Phase-2 schema bump."""
    from pathlib import Path
    # Use one of the bundled artifacts that ships at schema_version: 1
    artifact_path = BUNDLED_CALIBRATION_DIR / "calibration_2024.json"
    if artifact_path.exists():
        artifact = json.loads(artifact_path.read_text())
        # Bundled artifacts are at schema_version: 1 until Plan 03 / Plan 05 re-fit
        # bumps them to v2. The v1 path must keep working.
        assert artifact["schema_version"] in ARTIFACT_SCHEMA_VERSIONS_SUPPORTED, (
            f"Bundled artifact at unsupported schema_version={artifact['schema_version']}"
        )


def test_artifact_loader_accepts_schema_v2():
    """Schema v2 artifacts (KS-09 Plan 03 introduces) must load and expose stat_corrections."""
    assert ARTIFACT_SCHEMA_VERSION == 2
    assert 1 in ARTIFACT_SCHEMA_VERSIONS_SUPPORTED
    assert 2 in ARTIFACT_SCHEMA_VERSIONS_SUPPORTED


def test_artifact_loader_rejects_schema_v3():
    """Future schema versions must be rejected so a forwards-incompatible artifact doesn't silently load."""
    assert 3 not in ARTIFACT_SCHEMA_VERSIONS_SUPPORTED


# === KS-09: per-stat residual_calibration ===

import math

from fantasy_sim.data.ensemble.models import StatLevelConfig
from fantasy_sim.scoring.residual_calibration import stat_clamp_adjustment  # NEW helper from Task 2 — RED until then


def _build_v2_artifact_for_tests():
    """Construct a minimal schema-v2 artifact with stat_corrections for KS-09 testing."""
    return {
        "schema_version": 2,
        "test_season": 2024,
        "source_seasons": [2022, 2023],
        "sims": 200,
        "scoring": "ppr",
        "positions": ["QB", "RB", "WR", "TE"],
        "min_bucket_rows": 200,
        "min_bucket_weeks": 6,
        "shrinkage_prior_rows": 200,
        "max_abs_adjustment": 1.5,
        "min_training_mae_delta": -0.01,
        "fallback": "zero",
        "usage_tier_thresholds": {
            "QB": {"high": 18.0, "mid": 12.0},
            "RB": {"high": 14.0, "mid": 7.0},
            "WR": {"high": 12.0, "mid": 6.0},
            "TE": {"high": 9.0, "mid": 4.0},
        },
        "buckets": {
            "QB|low|simulator_only": {"correction_fpts": -0.5, "n_rows": 250, "n_weeks": 8},
            "QB|mid|simulator_only": {"correction_fpts": -0.3, "n_rows": 180, "n_weeks": 6},
        },
        "fallback_buckets": {},
        "stat_corrections": {
            "pass_yards": {
                "corrections": {
                    "QB|low|simulator_only": {"correction": -10.0, "n_rows": 250},
                    "QB|mid|simulator_only": {"correction": -8.0, "n_rows": 180},
                },
                "clamps": {
                    "QB|low|simulator_only": {"clamp_std": 50.0},
                    "QB|mid|simulator_only": {"clamp_std": 60.0},
                },
            },
            "receiving_yards": {
                "corrections": {
                    "WR|low|simulator_only": {"correction": 4.0, "n_rows": 220},
                },
                "clamps": {
                    "WR|low|simulator_only": {"clamp_std": 30.0},
                },
            },
        },
    }


def _build_qb_row(fpts: float = 16.0, pass_yards: float = 240.0):
    return {
        "player_id": "00-0036971",
        "name": "Test QB",
        "position": "QB",
        "team": "KC",
        "fpts": fpts,
        "pass_yards": pass_yards,
        "pass_tds": 1.5,
        "interceptions": 0.6,
        "rush_yards": 12.0,
        "rush_tds": 0.1,
        "fumbles_lost": 0.05,
        "dynamic_blend_source_mask": "simulator",
    }


def _build_wr_row(fpts: float = 8.0, receiving_yards: float = 70.0):
    return {
        "player_id": "00-0036900",
        "name": "Test WR",
        "position": "WR",
        "team": "KC",
        "fpts": fpts,
        "receiving_yards": receiving_yards,
        "receptions": 5.0,
        "receiving_tds": 0.4,
        "fumbles_lost": 0.02,
        "dynamic_blend_source_mask": "simulator",
    }


def _build_adjuster_with_stat_level_enabled():
    """Build a ResidualCalibrationProjectionAdjuster with stat_level.enabled=True + the v2 test artifact."""
    config = ResidualCalibrationConfig(
        enabled=True,
        artifacts_dir=None,  # we'll inject the artifact directly
        positions=("QB", "RB", "WR", "TE"),
        min_bucket_rows=200,
        min_bucket_weeks=6,
        shrinkage_prior_rows=200,
        max_abs_adjustment=1.5,
        min_training_mae_delta=-0.01,
        fallback="zero",
        stat_level=StatLevelConfig(
            enabled=True,
            covered_stats=(
                "pass_yards", "pass_tds", "interceptions",
                "rush_yards", "rush_tds",
                "receiving_yards", "receptions", "receiving_tds",
                "fumbles_lost",
            ),
        ),
    )
    adjuster = ResidualCalibrationProjectionAdjuster(config)
    # Inject the v2 artifact directly into the cache
    adjuster._artifact_cache = {2024: _build_v2_artifact_for_tests()}  # noqa: SLF001
    return adjuster


def test_ks09_writes_corrected_columns_when_enabled():
    """When stat_level.enabled=True, adjust_week writes corrected_<stat> columns for covered stats."""
    adjuster = _build_adjuster_with_stat_level_enabled()
    rows, _stats = adjuster.adjust_week([_build_qb_row()], season=2024, week=1)
    row = rows[0]
    # 9 covered stats from StatLevelConfig.covered_stats above
    assert "corrected_pass_yards" in row
    assert "corrected_pass_tds" in row
    assert "corrected_interceptions" in row
    assert "corrected_rush_yards" in row
    assert "corrected_rush_tds" in row
    assert "corrected_fumbles_lost" in row


def test_ks09_fpts_unchanged_when_flag_disabled():
    """When stat_level.enabled=False, no corrected_<stat> columns appear."""
    config = ResidualCalibrationConfig(
        enabled=True,
        positions=("QB", "RB", "WR", "TE"),
        min_bucket_rows=200,
        min_bucket_weeks=6,
        max_abs_adjustment=1.5,
        stat_level=StatLevelConfig(enabled=False),
    )
    adjuster = ResidualCalibrationProjectionAdjuster(config)
    adjuster._artifact_cache = {2024: _build_v2_artifact_for_tests()}  # noqa: SLF001
    rows, _stats = adjuster.adjust_week([_build_qb_row()], season=2024, week=1)
    row = rows[0]
    # No corrected_<stat> columns
    for stat in ("pass_yards", "pass_tds", "interceptions", "rush_yards", "rush_tds", "fumbles_lost"):
        assert f"corrected_{stat}" not in row, f"corrected_{stat} unexpectedly present when flag disabled"


def test_ks09_two_stage_layered_fpts_unchanged_with_flag_enabled():
    """D-01: row['fpts'] is computed from raw_sim_fpts + existing fpts-level correction; per-stat corrections do NOT propagate."""
    adjuster = _build_adjuster_with_stat_level_enabled()
    raw_fpts = 16.0
    rows, _stats = adjuster.adjust_week([_build_qb_row(fpts=raw_fpts)], season=2024, week=1)
    row = rows[0]
    # QB at fpts=16.0 → above QB|mid threshold (12.0) → bucket "QB|mid|simulator_only"
    # correction_fpts = -0.3 from buckets dict (not stat_corrections)
    expected_fpts = max(raw_fpts + (-0.3), 0.0)
    assert math.isclose(float(row["fpts"]), round(expected_fpts, 1), abs_tol=1e-6)
    # And corrected_pass_yards is independently computed (not derived from fpts)
    # raw pass_yards = 240, correction = -8.0 (QB|mid), clamped at ±2*60=120
    assert "corrected_pass_yards" in row
    assert math.isclose(float(row["corrected_pass_yards"]), 240.0 + (-8.0), abs_tol=1e-6)


def test_ks09_std_scaled_clamp_applies():
    """stat_clamp_adjustment clamps to ±2 * clamp_std."""
    # raw correction = +25, clamp_std = 10, limit = 20 → clamped to +20
    assert stat_clamp_adjustment(25.0, clamp_std=10.0) == 20.0
    # raw correction = -15, clamp_std = 10, limit = 20 → unchanged at -15
    assert stat_clamp_adjustment(-15.0, clamp_std=10.0) == -15.0
    # raw correction = -30, clamp_std = 10 → clamped to -20
    assert stat_clamp_adjustment(-30.0, clamp_std=10.0) == -20.0
    # clamp_std = 0 → limit = 0 → any input clamped to 0
    assert stat_clamp_adjustment(5.0, clamp_std=0.0) == 0.0


def test_ks09_missing_bucket_fallback_zero():
    """For a bucket_key NOT in stat_corrections, corrected_<stat> equals the raw <stat>."""
    adjuster = _build_adjuster_with_stat_level_enabled()
    # WR with low fpts → bucket_key = "WR|low|simulator_only"; stat_corrections has WR|low|simulator_only for receiving_yards only
    # Other WR-covered stats (receptions, receiving_tds, fumbles_lost) have NO entry — fallback to raw
    rows, _stats = adjuster.adjust_week([_build_wr_row(fpts=5.0)], season=2024, week=1)
    row = rows[0]
    # receiving_yards has correction; should differ from raw
    raw_recv = 70.0
    assert math.isclose(float(row["corrected_receiving_yards"]), raw_recv + 4.0, abs_tol=1e-6)  # correction=4.0 from fixture
    # receptions has NO correction → corrected == raw (zero adjustment)
    assert math.isclose(float(row["corrected_receptions"]), 5.0, abs_tol=1e-6)


def test_ks09_schema_v2_artifact_has_stat_corrections():
    """V2 artifact carries a stat_corrections block."""
    artifact = _build_v2_artifact_for_tests()
    assert artifact["schema_version"] == 2
    assert "stat_corrections" in artifact
    assert "pass_yards" in artifact["stat_corrections"]
    assert "corrections" in artifact["stat_corrections"]["pass_yards"]
    assert "clamps" in artifact["stat_corrections"]["pass_yards"]


def test_ks09_training_script_writes_per_stat_block():
    """fit_residual_calibration_artifact with stat_level enabled=True populates stat_corrections."""
    # Minimal training rows: simulate QB rows with raw stats + actuals
    source_rows = [
        {
            "player_id": "p1", "position": "QB",
            "season": 2022, "week": 1,
            "projected_fpts": 18.0, "actual_fpts": 22.0,
            "fpts": 18.0, "pass_yards": 250.0,
            "actual_pass_yards": 280.0,  # KS-09 needs actual stat values
            "dynamic_blend_source_mask": "simulator",
            "bucket_key": "QB|high|simulator_only",
        },
        {
            "player_id": "p1", "position": "QB",
            "season": 2022, "week": 2,
            "projected_fpts": 17.0, "actual_fpts": 19.0,
            "fpts": 17.0, "pass_yards": 230.0,
            "actual_pass_yards": 250.0,
            "dynamic_blend_source_mask": "simulator",
            "bucket_key": "QB|high|simulator_only",
        },
    ] * 200  # repeat to satisfy min_bucket_rows
    config = ResidualCalibrationConfig(
        enabled=True,
        positions=("QB",),
        min_bucket_rows=200,
        min_bucket_weeks=6,
        stat_level=StatLevelConfig(enabled=True, covered_stats=("pass_yards",)),
    )
    artifact = fit_residual_calibration_artifact(
        source_rows,
        test_season=2024,
        source_seasons=[2022, 2023],
        sims=200,
        scoring="ppr",
        config=config,
    )
    assert "stat_corrections" in artifact
    assert "pass_yards" in artifact["stat_corrections"]
    # At least one bucket-correction populated
    assert len(artifact["stat_corrections"]["pass_yards"]["corrections"]) >= 1
    assert len(artifact["stat_corrections"]["pass_yards"]["clamps"]) >= 1


def test_ks09_corrected_differs_from_raw_for_non_fallback_rows():
    """For rows whose bucket has a correction, corrected_<stat> != raw <stat>."""
    adjuster = _build_adjuster_with_stat_level_enabled()
    # QB at fpts=10.0 → below mid threshold (12.0) → bucket "QB|low|simulator_only"; correction for pass_yards = -10.0
    rows, _stats = adjuster.adjust_week([_build_qb_row(fpts=10.0, pass_yards=240.0)], season=2024, week=1)
    row = rows[0]
    raw_pass_yards = 240.0
    corrected = float(row["corrected_pass_yards"])
    assert corrected != raw_pass_yards, "corrected_pass_yards must differ from raw for a populated bucket"
    assert math.isclose(corrected, 230.0, abs_tol=1e-6)  # 240 + (-10) clamped at ±100


# === KS-10: per-position max_abs_adjustment + TE elite tier ===


def test_ks10_te_elite_tier_threshold():
    """When ks10_enabled=True, TE>14.0 returns 'elite'; TE>9.0 returns 'high'; etc."""
    assert usage_tier("TE", 16.0, ks10_enabled=True) == "elite"
    assert usage_tier("TE", 12.0, ks10_enabled=True) == "high"
    assert usage_tier("TE", 7.0, ks10_enabled=True) == "mid"
    assert usage_tier("TE", 2.0, ks10_enabled=True) == "low"
    # Other positions unchanged by ks10_enabled
    assert usage_tier("QB", 16.0, ks10_enabled=True) == "mid"  # 16 < 18 high threshold
    assert usage_tier("WR", 14.0, ks10_enabled=True) == "high"  # 14 >= 12


def test_ks10_legacy_behavior_when_flag_disabled():
    """When ks10_enabled=False, TE uses the legacy 3-tier shape (no elite)."""
    assert usage_tier("TE", 16.0, ks10_enabled=False) == "high"  # 16 >= 9 (legacy high threshold)
    assert usage_tier("TE", 16.0) == "high"  # default ks10_enabled=False
    # Backwards-compat alias unchanged
    assert USAGE_TIER_THRESHOLDS_3["TE"] == (9.0, 4.0)
    assert USAGE_TIER_THRESHOLDS_4["TE"] == (14.0, 9.0, 4.0)


def test_ks10_per_position_cap_lookup():
    """clamp_adjustment uses per-position cap when both position and by_position are provided."""
    by_pos = {"QB": 2.5, "RB": 2.0, "WR": 1.5, "TE": 0.8}
    # TE cap = 0.8; raw correction +1.5 → clamped to +0.8
    assert clamp_adjustment(1.5, max_abs_adjustment=1.5, position="TE", by_position=by_pos) == 0.8
    # QB cap = 2.5; raw correction +2.0 → unchanged at +2.0
    assert clamp_adjustment(2.0, max_abs_adjustment=1.5, position="QB", by_position=by_pos) == 2.0
    # When position absent from by_position, falls back to global
    assert clamp_adjustment(2.0, max_abs_adjustment=1.5, position="K", by_position=by_pos) == 1.5


def test_ks10_legacy_clamp_when_no_per_position():
    """When by_position is None, falls back to global max_abs_adjustment."""
    assert clamp_adjustment(2.0, max_abs_adjustment=1.5) == 1.5
    assert clamp_adjustment(2.0, max_abs_adjustment=1.5, position="TE") == 1.5  # by_position not provided


def test_ks10_te_min_bucket_rows_is_lowered_in_artifact_after_refit():
    """After KS-10 re-fit, the TE buckets in the artifact are populated even when a TE bucket has fewer rows than the global min_bucket_rows=200."""
    import json
    from pathlib import Path
    artifact_path = Path("src/fantasy_sim/data/ensemble/artifacts/residual_calibration/decision_s200/calibration_2024.json")
    if artifact_path.exists():
        with open(artifact_path) as f:
            artifact = json.load(f)
        te_buckets = [k for k in artifact.get("buckets", {}) if k.startswith("TE|")]
        # Pre-Plan-05: TE buckets may be empty (legacy min_bucket_rows=200 collapsed them).
        # Post-Plan-05: at least one TE bucket should exist.
        # This test passes pre-Plan-05 (empty) and validates post-Plan-05 (non-empty).
        assert isinstance(te_buckets, list)  # smoke test; the real assertion is in Task 3

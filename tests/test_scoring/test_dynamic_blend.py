import json
from types import SimpleNamespace

import polars as pl

from fantasy_sim.data.ensemble.models import (
    DynamicBlendConfig,
    EnsembleConfig,
    FfOpportunityConfig,
)
from fantasy_sim.data.market_history.models import MarketHistoryConfig
from fantasy_sim.scoring.dynamic_blend import (
    ARTIFACT_SCHEMA_VERSION,
    BUNDLED_WEIGHTS_DIR,
    DynamicBlendProjectionBlender,
    fit_dynamic_blend_artifact,
)
from fantasy_sim.scoring.projection_layers import apply_projection_layers


class _FfLoader:
    def load_weekly(self, seasons: list[int]) -> pl.DataFrame:
        return pl.DataFrame(
            {
                "season": [2024],
                "week": [1],
                "player_id": ["QB1"],
                "full_name": ["QB One"],
                "position": ["QB"],
                "posteam": ["KC"],
                "total_fantasy_points_exp": [20.0],
            }
        )


class _MarketAdjuster:
    def season_priors(self, season: int) -> pl.DataFrame:
        return pl.DataFrame(
            {
                "season": [season],
                "week": [1],
                "player_id": ["QB1"],
                "prior_fpts": [18.0],
                "confidence_factor": [1.0],
                "covered_market_count": [2],
            }
        )

    def market_target(self, row: dict, prior: dict) -> tuple[float, list[str]]:
        return float(prior["prior_fpts"]), ["player_pass_yds"]

    def blend_supported_stats(self, row: dict, prior: dict, weight: float) -> None:
        row["pass_yards"] = round(float(row["pass_yards"]) * (1.0 - weight) + 300.0 * weight, 1)


def _ensemble_config(tmp_path, *, weights_dir: str | None = None) -> EnsembleConfig:
    return EnsembleConfig(
        enabled=True,
        ff_opportunity=FfOpportunityConfig(
            enabled=True,
            weights={"QB": 0.35, "RB": 0.15, "WR": 0.25, "TE": 0.15},
        ),
        dynamic_blend=DynamicBlendConfig(
            enabled=True,
            weights_dir=weights_dir or str(tmp_path),
            min_bucket_rows=2,
            min_bucket_weeks=1,
            grid_step=0.5,
        ),
    )


def _market_config() -> MarketHistoryConfig:
    return MarketHistoryConfig(
        enabled=True,
        weights={"QB": 0.20, "RB": 0.15, "WR": 0.20, "TE": 0.15},
    )


def test_dynamic_blend_missing_artifact_falls_back_to_fixed_equivalent(tmp_path):
    blender = DynamicBlendProjectionBlender(
        _ensemble_config(tmp_path),
        market_history_config=_market_config(),
        ff_loader=_FfLoader(),
    )
    blender._market_adjuster = _MarketAdjuster()

    blended, stats = blender.blend_week(
        [
            {
                "player_id": "QB1",
                "position": "QB",
                "team": "KC",
                "name": "QB One",
                "fpts": 10.0,
                "pass_yards": 200.0,
                "rank": 1,
            }
        ],
        season=2024,
        week=1,
    )

    row = blended[0]
    assert row["fpts"] == 14.5
    assert row["pass_yards"] == 220.0
    assert row["dynamic_blend_fallback_reason"] == "missing_artifact"
    assert row["dynamic_blend_simulator_weight"] == 0.52
    assert row["dynamic_blend_market_history_weight"] == 0.13
    assert row["dynamic_blend_ff_opportunity_weight"] == 0.35
    assert row["dynamic_blend_market_history_market_count"] == 1
    assert stats.learned_rows == 0
    assert stats.fallback_rows == 1


def test_dynamic_blend_uses_learned_artifact_weights(tmp_path):
    artifact = {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "scoring": "ppr",
        "buckets": {
            "QB|1-4|simulator+ff_opportunity+market_history|high": {
                "weights": {
                    "simulator": 0.1,
                    "ff_opportunity": 0.7,
                    "market_history": 0.2,
                }
            }
        },
    }
    (tmp_path / "weights_2024.json").write_text(json.dumps(artifact))
    blender = DynamicBlendProjectionBlender(
        _ensemble_config(tmp_path),
        market_history_config=_market_config(),
        ff_loader=_FfLoader(),
    )
    blender._market_adjuster = _MarketAdjuster()

    blended, stats = blender.blend_week(
        [
            {
                "player_id": "QB1",
                "position": "QB",
                "team": "KC",
                "name": "QB One",
                "fpts": 10.0,
                "pass_yards": 200.0,
                "rank": 1,
            }
        ],
        season=2024,
        week=1,
    )

    assert blended[0]["fpts"] == 18.6
    assert blended[0]["pass_yards"] == 220.0
    assert blended[0]["dynamic_blend_fallback_reason"] is None
    assert stats.learned_rows == 1
    assert stats.fallback_rows == 0


def test_dynamic_blend_rejects_artifact_with_different_scoring(tmp_path):
    artifact = {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "scoring": "half_ppr",
        "buckets": {
            "QB|1-4|simulator+ff_opportunity+market_history|high": {
                "weights": {
                    "simulator": 0.1,
                    "ff_opportunity": 0.7,
                    "market_history": 0.2,
                }
            }
        },
    }
    (tmp_path / "weights_2024.json").write_text(json.dumps(artifact))
    blender = DynamicBlendProjectionBlender(
        _ensemble_config(tmp_path),
        market_history_config=_market_config(),
        ff_loader=_FfLoader(),
        scoring="ppr",
    )
    blender._market_adjuster = _MarketAdjuster()

    blended, stats = blender.blend_week(
        [
            {
                "player_id": "QB1",
                "position": "QB",
                "team": "KC",
                "name": "QB One",
                "fpts": 10.0,
                "pass_yards": 200.0,
                "rank": 1,
            }
        ],
        season=2024,
        week=1,
    )

    assert blended[0]["fpts"] == 14.5
    assert blended[0]["dynamic_blend_fallback_reason"] == "missing_artifact"
    assert stats.learned_rows == 0
    assert stats.fallback_rows == 1


def test_dynamic_blend_fixed_fallback_preserves_legacy_rounding(tmp_path):
    class _BoundaryFfLoader:
        def load_weekly(self, seasons: list[int]) -> pl.DataFrame:
            return pl.DataFrame(
                {
                    "season": [2024],
                    "week": [1],
                    "player_id": ["QB1"],
                    "full_name": ["QB One"],
                    "position": ["QB"],
                    "posteam": ["KC"],
                    "total_fantasy_points_exp": [5.4],
                }
            )

    class _BoundaryMarketAdjuster:
        def season_priors(self, season: int) -> pl.DataFrame:
            return pl.DataFrame(
                {
                    "season": [season],
                    "week": [1],
                    "player_id": ["QB1"],
                    "prior_fpts": [5.1],
                    "confidence_factor": [1.0],
                    "covered_market_count": [8],
                }
            )

        def market_target(self, row: dict, prior: dict) -> tuple[float, list[str]]:
            return float(prior["prior_fpts"]), ["player_pass_yds"]

        def blend_supported_stats(self, row: dict, prior: dict, weight: float) -> None:
            return None

    blender = DynamicBlendProjectionBlender(
        _ensemble_config(tmp_path),
        market_history_config=_market_config(),
        ff_loader=_BoundaryFfLoader(),
    )
    blender._market_adjuster = _BoundaryMarketAdjuster()

    blended, _ = blender.blend_week(
        [
            {
                "player_id": "QB1",
                "position": "QB",
                "team": "KC",
                "name": "QB One",
                "fpts": 5.0,
                "rank": 1,
            }
        ],
        season=2024,
        week=1,
    )

    assert blended[0]["fpts"] == 5.1


def test_bundled_decision_artifacts_are_available():
    seasons = [2023, 2024]

    for season in seasons:
        path = BUNDLED_WEIGHTS_DIR / f"weights_{season}.json"
        artifact = json.loads(path.read_text())

        assert artifact["schema_version"] == ARTIFACT_SCHEMA_VERSION
        assert artifact["test_season"] == season
        assert artifact["buckets"]


def test_apply_projection_layers_runs_dynamic_after_role_trend_and_skips_fixed_layers():
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
    )

    assert adjusted[0]["fpts"] == 13.0
    assert order == ["trend", "dynamic"]


def test_fit_dynamic_blend_artifact_learns_known_best_source(tmp_path):
    ensemble_config = _ensemble_config(tmp_path)
    rows = [
        {
            "season": 2022,
            "week": 1,
            "player_id": "QB1",
            "position": "QB",
            "simulator_fpts": 10.0,
            "ff_opportunity_fpts": 20.0,
            "actual_fpts": 20.0,
        },
        {
            "season": 2022,
            "week": 2,
            "player_id": "QB1",
            "position": "QB",
            "simulator_fpts": 12.0,
            "ff_opportunity_fpts": 18.0,
            "actual_fpts": 18.0,
        },
    ]

    artifact = fit_dynamic_blend_artifact(
        rows,
        test_season=2023,
        source_seasons=[2022],
        sims=50,
        scoring="ppr",
        ensemble_config=ensemble_config,
        market_history_config=_market_config(),
    )

    bucket = artifact["buckets"]["QB|1-4|simulator+ff_opportunity|none"]
    assert bucket["weights"]["ff_opportunity"] == 1.0
    assert bucket["weights"]["simulator"] == 0.0
    assert bucket["mae_delta"] < 0


def test_fit_dynamic_blend_artifact_falls_back_on_sparse_bucket(tmp_path):
    ensemble_config = _ensemble_config(tmp_path)
    ensemble_config.dynamic_blend.min_bucket_rows = 3
    rows = [
        {
            "season": 2022,
            "week": 1,
            "player_id": "QB1",
            "position": "QB",
            "simulator_fpts": 10.0,
            "ff_opportunity_fpts": 20.0,
            "actual_fpts": 20.0,
        },
        {
            "season": 2022,
            "week": 2,
            "player_id": "QB1",
            "position": "QB",
            "simulator_fpts": 12.0,
            "ff_opportunity_fpts": 18.0,
            "actual_fpts": 18.0,
        },
    ]

    artifact = fit_dynamic_blend_artifact(
        rows,
        test_season=2023,
        source_seasons=[2022],
        sims=50,
        scoring="ppr",
        ensemble_config=ensemble_config,
        market_history_config=_market_config(),
    )

    assert artifact["buckets"] == {}
    assert artifact["fallback_buckets"]["QB|1-4|simulator+ff_opportunity|none"]["reason"] == "sparse_bucket"

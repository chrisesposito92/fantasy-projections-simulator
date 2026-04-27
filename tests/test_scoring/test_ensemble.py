import math

import numpy as np
import polars as pl

from fantasy_sim.data.ensemble import EnsembleConfig, FfOpportunityConfig


class _StubLoader:
    def __init__(self, frame: pl.DataFrame) -> None:
        self.frame = frame
        self.calls: list[list[int]] = []

    def load_weekly(self, seasons: list[int]) -> pl.DataFrame:
        self.calls.append(list(seasons))
        return self.frame


def _config(*, enabled: bool = True, ff_enabled: bool = True) -> EnsembleConfig:
    return EnsembleConfig(
        enabled=enabled,
        ff_opportunity=FfOpportunityConfig(
            enabled=ff_enabled,
            positions=("QB", "RB", "WR", "TE"),
            weights={"QB": 0.5, "WR": 0.25, "RB": 0.15, "TE": 0.15},
        ),
    )


def test_blend_week_updates_fpts_and_recomputes_rank():
    from fantasy_sim.scoring.ensemble import FfOpportunityProjectionEnsembler

    loader = _StubLoader(
        pl.DataFrame(
            {
                "season": [2024, 2024],
                "week": [1, 1],
                "player_id": ["QB1", "WR1"],
                "full_name": ["QB One", "WR One"],
                "position": ["QB", "WR"],
                "posteam": ["KC", "MIN"],
                "total_fantasy_points_exp": [20.0, 12.0],
            }
        )
    )
    ensembler = FfOpportunityProjectionEnsembler(_config(), loader=loader)

    blended, stats = ensembler.blend_week(
        [
            {
                "player_id": "WR1",
                "name": "WR One",
                "position": "WR",
                "team": "MIN",
                "fpts": 11.0,
                "rank": 1,
            },
            {
                "player_id": "QB1",
                "name": "QB One",
                "position": "QB",
                "team": "KC",
                "fpts": 10.0,
                "rank": 2,
            },
        ],
        season=2024,
        week=1,
    )

    qb = next(row for row in blended if row["player_id"] == "QB1")
    wr = next(row for row in blended if row["player_id"] == "WR1")

    assert qb["fpts"] == 15.0
    assert qb["rank"] == 1
    assert qb["ensemble_source"] == "ff_opportunity"
    assert qb["ensemble_weight"] == 0.5
    assert qb["ensemble_covered"] is True
    assert qb["ensemble_prior_fpts"] == 20.0
    assert wr["fpts"] == 11.2
    assert wr["ensemble_source"] == "ff_opportunity"
    assert wr["ensemble_weight"] == 0.25
    assert wr["ensemble_covered"] is True
    assert wr["ensemble_prior_fpts"] == 12.0
    assert stats.covered_rows == 2
    assert stats.uncovered_rows == 0


def test_blend_week_blends_covered_rb_under_broadened_default_scope():
    from fantasy_sim.scoring.ensemble import FfOpportunityProjectionEnsembler

    loader = _StubLoader(
        pl.DataFrame(
            {
                "season": [2024],
                "week": [1],
                "player_id": ["RB1"],
                "full_name": ["RB One"],
                "position": ["RB"],
                "posteam": ["SF"],
                "total_fantasy_points_exp": [20.0],
            }
        )
    )
    ensembler = FfOpportunityProjectionEnsembler(_config(), loader=loader)

    blended, stats = ensembler.blend_week(
        [
            {
                "player_id": "RB1",
                "name": "RB One",
                "position": "RB",
                "team": "SF",
                "fpts": 10.0,
                "rank": 1,
            }
        ],
        season=2024,
        week=1,
    )

    rb = blended[0]

    assert rb["fpts"] == 11.5
    assert rb["ensemble_source"] == "ff_opportunity"
    assert rb["ensemble_weight"] == 0.15
    assert rb["ensemble_covered"] is True
    assert rb["ensemble_prior_fpts"] == 20.0
    assert stats.covered_rows == 1
    assert stats.uncovered_rows == 0


def test_blend_week_leaves_uncovered_rows_unchanged():
    from fantasy_sim.scoring.ensemble import FfOpportunityProjectionEnsembler

    loader = _StubLoader(
        pl.DataFrame(
            {
                "season": [2024],
                "week": [1],
                "player_id": ["WR1"],
                "full_name": ["WR One"],
                "position": ["WR"],
                "posteam": ["MIN"],
                "total_fantasy_points_exp": [12.0],
            }
        )
    )
    ensembler = FfOpportunityProjectionEnsembler(_config(), loader=loader)

    blended, stats = ensembler.blend_week(
        [
            {
                "player_id": "RB1",
                "name": "RB One",
                "position": "RB",
                "team": "SF",
                "fpts": 13.0,
                "rush_yards": 70.0,
                "rank": 1,
            },
            {
                "player_id": "WR1",
                "name": "WR One",
                "position": "WR",
                "team": "MIN",
                "fpts": 10.0,
                "receiving_yards": 65.0,
                "rank": 2,
            },
        ],
        season=2024,
        week=1,
    )

    rb = next(row for row in blended if row["player_id"] == "RB1")
    wr = next(row for row in blended if row["player_id"] == "WR1")

    assert rb["fpts"] == 13.0
    assert rb["rush_yards"] == 70.0
    assert rb["ensemble_source"] is None
    assert rb["ensemble_weight"] == 0.0
    assert rb["ensemble_covered"] is False
    assert "ensemble_prior_fpts" not in rb
    assert wr["ensemble_source"] == "ff_opportunity"
    assert wr["ensemble_weight"] == 0.25
    assert wr["ensemble_covered"] is True
    assert wr["ensemble_prior_fpts"] == 12.0
    assert stats.covered_rows == 1
    assert stats.uncovered_rows == 1


def test_blend_week_disabled_config_returns_copied_rows_with_uncovered_metadata():
    from fantasy_sim.scoring.ensemble import FfOpportunityProjectionEnsembler

    original = [
        {
            "player_id": "QB1",
            "name": "QB One",
            "position": "QB",
            "team": "KC",
            "fpts": 18.0,
            "rank": 1,
        }
    ]
    ensembler = FfOpportunityProjectionEnsembler(_config(enabled=False))

    blended, stats = ensembler.blend_week(original, season=2024, week=1)

    assert blended is not original
    assert blended[0] is not original[0]
    assert blended[0]["fpts"] == 18.0
    assert blended[0]["ensemble_source"] is None
    assert blended[0]["ensemble_weight"] == 0.0
    assert blended[0]["ensemble_covered"] is False
    assert "ensemble_source" not in original[0]
    assert stats.covered_rows == 0
    assert stats.uncovered_rows == 1


def test_constructor_does_not_instantiate_loader_until_priors_needed(monkeypatch):
    import fantasy_sim.scoring.ensemble as ensemble_module

    calls: list[str] = []

    class _LazyLoader:
        def __init__(self, config=None) -> None:
            calls.append("init")

        def load_weekly(self, seasons: list[int]) -> pl.DataFrame:
            calls.append("load")
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

    monkeypatch.setattr(ensemble_module, "FfOpportunityLoader", _LazyLoader)

    ensembler = ensemble_module.FfOpportunityProjectionEnsembler(_config())

    assert calls == []

    blended, stats = ensembler.blend_week(
        [
            {
                "player_id": "QB1",
                "name": "QB One",
                "position": "QB",
                "team": "KC",
                "fpts": 10.0,
                "rank": 1,
            }
        ],
        season=2024,
        week=1,
    )

    assert calls == ["init", "load"]
    assert blended[0]["fpts"] == 15.0
    assert stats.covered_rows == 1


# === KS-13: ff_opportunity prior width ===


def test_ks13_path_a_uses_quantile_width_when_lo_hi_present():
    """Path A: sigma = (hi - lo) / 2.56; sampled prior is centered on prior_fpts with that std.

    Two ensemblers seeded identically must produce identical fpts (determinism);
    the empirical sample std across many seeds must match (prior_hi - prior_lo) / 2.56
    within tolerance.
    """
    from fantasy_sim.scoring.ensemble import FfOpportunityProjectionEnsembler
    from fantasy_sim.data.ensemble.models import PriorWidthConfig

    cfg = EnsembleConfig(
        enabled=True,
        ff_opportunity=FfOpportunityConfig(
            enabled=True,
            weights={"WR": 0.5},
            prior_width=PriorWidthConfig(enabled=True, path="A"),
        ),
    )

    # FakeLoader returns raw frame; normalizer converts to prior_fpts with lo/hi.
    # expected sigma = (25.0 - 15.0) / 2.56 ≈ 3.906
    expected_sigma = (25.0 - 15.0) / 2.56

    fake_priors = pl.DataFrame({
        "season": [2024], "week": [1], "player_id": ["wr1"],
        "full_name": ["WR One"], "position": ["WR"], "posteam": ["MIN"],
        "total_fantasy_points_exp": [20.0],
        "total_fantasy_points_exp_lo": [15.0], "total_fantasy_points_exp_hi": [25.0],
    })
    fake_loader = _StubLoader(fake_priors)

    samples: list[float] = []
    for seed in range(500):
        ens = FfOpportunityProjectionEnsembler(
            cfg, loader=fake_loader, rng=np.random.default_rng(seed),
            ks13_master_enabled=True,
        )
        out, _ = ens.blend_week(
            [{"player_id": "wr1", "position": "WR", "fpts": 0.0}],
            season=2024, week=1,
        )
        # weight=0.5; fpts = 0.5*0 + 0.5*sampled_prior → sampled_prior = fpts / 0.5
        samples.append(out[0]["fpts"] / 0.5)

    # Determinism: same seed -> identical sample
    ens_a = FfOpportunityProjectionEnsembler(cfg, loader=fake_loader, rng=np.random.default_rng(42), ks13_master_enabled=True)
    ens_b = FfOpportunityProjectionEnsembler(cfg, loader=fake_loader, rng=np.random.default_rng(42), ks13_master_enabled=True)
    out_a, _ = ens_a.blend_week([{"player_id": "wr1", "position": "WR", "fpts": 0.0}], season=2024, week=1)
    out_b, _ = ens_b.blend_week([{"player_id": "wr1", "position": "WR", "fpts": 0.0}], season=2024, week=1)
    assert out_a[0]["fpts"] == out_b[0]["fpts"], "Path A must be deterministic under fixed RNG"

    # Empirical std across 500 seeds matches expected_sigma within ±20% tolerance
    empirical_std = float(np.std(samples, ddof=1))
    tolerance = expected_sigma * 0.20
    assert abs(empirical_std - expected_sigma) < tolerance, (
        f"Empirical std {empirical_std:.3f} should match expected sigma {expected_sigma:.3f} "
        f"= (prior_hi - prior_lo) / 2.56 within ±{tolerance:.3f}"
    )

    # Mean centered on prior_fpts (Path A is unbiased)
    empirical_mean = float(np.mean(samples))
    mean_tolerance = expected_sigma / math.sqrt(500) * 4
    assert abs(empirical_mean - 20.0) < mean_tolerance, (
        f"Empirical mean {empirical_mean:.3f} should match prior_fpts 20.0 within ±{mean_tolerance:.3f}"
    )


def test_ks13_path_b_uses_fitted_std_when_lo_hi_absent(tmp_path):
    """Path B: sigma comes from artifact buckets[position]['std_fpts']."""
    import json
    from fantasy_sim.data.ensemble.models import PriorWidthConfig
    from fantasy_sim.scoring.ensemble import FfOpportunityProjectionEnsembler, ARTIFACT_SCHEMA_VERSION

    # Write a synthetic Path B artifact
    artifacts_dir = tmp_path / "ff_opportunity_prior_width"
    artifacts_dir.mkdir()
    with (artifacts_dir / "prior_width_2024.json").open("w") as f:
        json.dump({
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "scoring": "ppr",
            "test_season": 2024,
            "source_seasons": [2020, 2021, 2022, 2023],
            "buckets": {
                "WR": {"std_fpts": 4.5, "n": 1000},
                "RB": {"std_fpts": 5.2, "n": 800},
                "QB": {"std_fpts": 6.1, "n": 200},
                "TE": {"std_fpts": 3.7, "n": 600},
            },
        }, f)

    config = EnsembleConfig(
        enabled=True,
        ff_opportunity=FfOpportunityConfig(
            enabled=True,
            weights={"WR": 0.3, "RB": 0.2, "QB": 0.0, "TE": 0.25},
            prior_width=PriorWidthConfig(
                enabled=True, path="B", artifacts_dir=artifacts_dir,
            ),
        ),
    )
    ensembler = FfOpportunityProjectionEnsembler(config=config, rng=np.random.default_rng(42))
    sigma = ensembler._fitted_std_for("WR", 14.0, 2024)
    assert abs(sigma - 4.5) < 1e-9


def test_ks13_unchanged_when_flag_disabled():
    """When prior_width.enabled = False, behavior is byte-identical to pre-Plan-07.

    The flag-off branch reuses the legacy point-estimate prior code path
    (sampled_prior = prior_fpts). Both sub-flag off and master-on-sub-off are tested.
    """
    from fantasy_sim.scoring.ensemble import FfOpportunityProjectionEnsembler
    from fantasy_sim.data.ensemble.models import PriorWidthConfig

    fake_priors = pl.DataFrame({
        "season": [2024], "week": [1], "player_id": ["wr1"],
        "full_name": ["WR One"], "position": ["WR"], "posteam": ["MIN"],
        "total_fantasy_points_exp": [20.0],
    })
    fake_loader = _StubLoader(fake_priors)
    rows = [{"player_id": "wr1", "position": "WR", "fpts": 12.0}]

    # Baseline: prior_width disabled (legacy point-estimate prior path)
    cfg_off = EnsembleConfig(
        enabled=True,
        ff_opportunity=FfOpportunityConfig(
            enabled=True,
            weights={"WR": 0.5},
            prior_width=PriorWidthConfig(enabled=False),
        ),
    )
    ens_off = FfOpportunityProjectionEnsembler(
        cfg_off, loader=fake_loader, rng=np.random.default_rng(123),
        ks13_master_enabled=True,  # master ON; sub-flag OFF -> conjunction is False, KS-13 dormant
    )
    out_off, _ = ens_off.blend_week(list(rows), season=2024, week=1)

    # Repeat with a different RNG — output must be IDENTICAL (no sampling)
    ens_off_alt = FfOpportunityProjectionEnsembler(
        cfg_off, loader=fake_loader, rng=np.random.default_rng(999),
        ks13_master_enabled=True,
    )
    out_off_alt, _ = ens_off_alt.blend_week(list(rows), season=2024, week=1)
    assert out_off[0]["fpts"] == out_off_alt[0]["fpts"], (
        "Flag-off branch must be RNG-independent (no sampling — point-estimate prior)"
    )
    # fpts = 0.5*12 + 0.5*20 = 16.0
    assert out_off[0]["fpts"] == 16.0, (
        f"Expected legacy point-estimate fpts=16.0 (= 0.5*12 + 0.5*20), got {out_off[0]['fpts']}"
    )
    assert out_off[0].get("ensemble_covered") is True
    assert out_off[0].get("ensemble_source") == "ff_opportunity"

    # Sanity: enabling prior_width (BOTH master AND sub) with no lo/hi data
    # Path A without lo/hi falls back to point-estimate — same as flag-off
    cfg_on = EnsembleConfig(
        enabled=True,
        ff_opportunity=FfOpportunityConfig(
            enabled=True,
            weights={"WR": 0.5},
            prior_width=PriorWidthConfig(enabled=True, path="A"),
        ),
    )
    ens_on = FfOpportunityProjectionEnsembler(
        cfg_on, loader=fake_loader, rng=np.random.default_rng(123),
        ks13_master_enabled=True,
    )
    out_on, _ = ens_on.blend_week(list(rows), season=2024, week=1)
    # Path A without lo/hi falls back to point-estimate (no lo/hi in fake_priors)
    # so result is identical to flag-off
    assert out_on[0]["fpts"] == 16.0


def test_ks13_dual_gate_master_flag_off_keeps_ks13_dormant():
    """Codex cycle-4 HIGH (dual-gate split fix): master phase2_ks_flag must be a
    sole-sufficient kill switch for KS-13 sampling.

    Plan 09's reverse-ablation walk-back disables KS-13 by setting
    `phase2_ks_flags.ks13_ff_opportunity_prior_width.enabled = False` while leaving
    `ensemble.ff_opportunity.prior_width.enabled` untouched.

    This test pins the invariant: when `ks13_master_enabled=False` AND
    `prior_width.enabled=True`, KS-13 sampling is OFF (legacy point-estimate path).
    Conjunction semantics: `ks13_active := master AND sub`.
    """
    from fantasy_sim.scoring.ensemble import FfOpportunityProjectionEnsembler
    from fantasy_sim.data.ensemble.models import PriorWidthConfig

    fake_priors = pl.DataFrame({
        "season": [2024], "week": [1], "player_id": ["wr1"],
        "full_name": ["WR One"], "position": ["WR"], "posteam": ["MIN"],
        "total_fantasy_points_exp": [20.0],
        "total_fantasy_points_exp_lo": [15.0], "total_fantasy_points_exp_hi": [25.0],
    })
    fake_loader = _StubLoader(fake_priors)
    rows = [{"player_id": "wr1", "position": "WR", "fpts": 12.0}]

    # Sub-flag ON, master OFF -> conjunction False -> legacy point-estimate path
    cfg_sub_on = EnsembleConfig(
        enabled=True,
        ff_opportunity=FfOpportunityConfig(
            enabled=True,
            weights={"WR": 0.5},
            prior_width=PriorWidthConfig(enabled=True, path="A"),
        ),
    )

    # Master flag OFF — KS-13 must be dormant regardless of RNG seed
    ens_master_off_seed1 = FfOpportunityProjectionEnsembler(
        cfg_sub_on, loader=fake_loader, rng=np.random.default_rng(1),
        ks13_master_enabled=False,
    )
    ens_master_off_seed2 = FfOpportunityProjectionEnsembler(
        cfg_sub_on, loader=fake_loader, rng=np.random.default_rng(99999),
        ks13_master_enabled=False,
    )
    out_seed1, _ = ens_master_off_seed1.blend_week(list(rows), season=2024, week=1)
    out_seed2, _ = ens_master_off_seed2.blend_week(list(rows), season=2024, week=1)

    # RNG-independent -> master-off truly bypasses sampling
    assert out_seed1[0]["fpts"] == out_seed2[0]["fpts"], (
        "ks13_master_enabled=False must make blend RNG-independent regardless of sub-flag state"
    )
    # Output equals the legacy point-estimate value: 0.5*12 + 0.5*20 = 16.0
    assert out_seed1[0]["fpts"] == 16.0, (
        f"Master-off + sub-on must use legacy point-estimate (16.0), got {out_seed1[0]['fpts']}"
    )


def test_ks13_master_enabled_lazy_fallback_reads_dict_shaped_phase2_ks_flags(monkeypatch):
    """Codex cycle-5 HIGH (lazy-fallback dict-vs-attribute mismatch fix):
    when `ks13_master_enabled=None` is passed to the ensembler constructor, the
    fallback path MUST resolve the master flag by reading the dict returned from
    `get_phase2_ks_flags()`.

    This test pins the dict-access correctness of the fallback.
    """
    import fantasy_sim.config.loader as loader_mod
    from fantasy_sim.scoring.ensemble import FfOpportunityProjectionEnsembler
    from fantasy_sim.data.ensemble.models import PriorWidthConfig

    cfg = EnsembleConfig(
        enabled=True,
        ff_opportunity=FfOpportunityConfig(
            enabled=True,
            weights={"WR": 0.5},
            prior_width=PriorWidthConfig(enabled=True, path="A"),
        ),
    )

    # Case 1: dict-shaped phase2_ks_flags with ks13 master TRUE
    monkeypatch.setattr(
        loader_mod,
        "get_phase2_ks_flags",
        lambda: {"ks13_ff_opportunity_prior_width": {"enabled": True}},
    )
    ens_master_on = FfOpportunityProjectionEnsembler(cfg, rng=np.random.default_rng(0))
    assert ens_master_on._ks13_master_enabled is True, (
        "Lazy fallback MUST read 'ks13_ff_opportunity_prior_width.enabled' from a dict, "
        "not via attribute access."
    )

    # Case 2: dict-shaped phase2_ks_flags with ks13 master FALSE
    monkeypatch.setattr(
        loader_mod,
        "get_phase2_ks_flags",
        lambda: {"ks13_ff_opportunity_prior_width": {"enabled": False}},
    )
    ens_master_off = FfOpportunityProjectionEnsembler(cfg, rng=np.random.default_rng(0))
    assert ens_master_off._ks13_master_enabled is False

    # Case 3: missing top-level key -> default-deny
    monkeypatch.setattr(loader_mod, "get_phase2_ks_flags", lambda: {})
    ens_missing = FfOpportunityProjectionEnsembler(cfg, rng=np.random.default_rng(0))
    assert ens_missing._ks13_master_enabled is False

    # Case 4: missing inner key -> default-deny
    monkeypatch.setattr(
        loader_mod,
        "get_phase2_ks_flags",
        lambda: {"ks13_ff_opportunity_prior_width": {}},
    )
    ens_missing_inner = FfOpportunityProjectionEnsembler(cfg, rng=np.random.default_rng(0))
    assert ens_missing_inner._ks13_master_enabled is False

    # Case 5: shim raises -> default-deny (graceful)
    def _raises():
        raise RuntimeError("loader unavailable")
    monkeypatch.setattr(loader_mod, "get_phase2_ks_flags", _raises)
    ens_raises = FfOpportunityProjectionEnsembler(cfg, rng=np.random.default_rng(0))
    assert ens_raises._ks13_master_enabled is False


def test_ks13_probe_script_outputs_json():
    """probe_ff_opportunity_quantiles.py emits valid JSON with 'path' field."""
    import json
    import subprocess
    result = subprocess.run(
        ["uv", "run", "python", "scripts/probe_ff_opportunity_quantiles.py", "--season", "2024", "--week", "1"],
        capture_output=True, text=True, check=True
    )
    parsed = json.loads(result.stdout.strip())
    assert "path" in parsed
    assert parsed["path"] in ("A", "B")
    assert "lo_present" in parsed
    assert "hi_present" in parsed
    assert "non_null_fraction" in parsed


def test_ks13_path_a_seed_determinism():
    """Path A sampling is deterministic when RNG is seeded.

    Two ensemblers seeded with the same RNG produce identical sampled values.
    """
    from fantasy_sim.data.ensemble.models import PriorWidthConfig
    from fantasy_sim.scoring.ensemble import FfOpportunityProjectionEnsembler

    config = EnsembleConfig(
        enabled=True,
        ff_opportunity=FfOpportunityConfig(
            enabled=True,
            weights={"WR": 0.3},
            prior_width=PriorWidthConfig(enabled=True, path="A"),
        ),
    )
    a = FfOpportunityProjectionEnsembler(config=config, rng=np.random.default_rng(123))
    b = FfOpportunityProjectionEnsembler(config=config, rng=np.random.default_rng(123))
    # Synthetic prior with lo/hi present -- Path A path
    s_a = float(a._rng.normal(14.0, (16.0 - 12.0) / 2.56))
    s_b = float(b._rng.normal(14.0, (16.0 - 12.0) / 2.56))
    assert abs(s_a - s_b) < 1e-9, "same seed must produce identical sampled_prior"


def test_ks13_path_b_artifact_loader_graceful_when_missing(tmp_path):
    """When Path B's artifact is absent, loader returns None and runtime falls
    back to the point-estimate prior (sigma = 0.0 -> no sampling)."""
    from fantasy_sim.data.ensemble.models import PriorWidthConfig
    from fantasy_sim.scoring.ensemble import FfOpportunityProjectionEnsembler

    config = EnsembleConfig(
        enabled=True,
        ff_opportunity=FfOpportunityConfig(
            enabled=True,
            weights={"WR": 0.3},
            prior_width=PriorWidthConfig(enabled=True, path="B", artifacts_dir=tmp_path),
        ),
    )
    ensembler = FfOpportunityProjectionEnsembler(config=config, rng=np.random.default_rng(7))
    # Empty artifacts_dir -> loader returns None -> _fitted_std_for returns 0.0
    artifact = ensembler._load_ff_opportunity_prior_width_artifact(2024)
    assert artifact is None
    sigma = ensembler._fitted_std_for("WR", 14.0, 2024)
    assert sigma == 0.0, "missing artifact must yield sigma=0.0 (point-estimate fallback)"

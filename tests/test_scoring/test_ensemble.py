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
            positions=("QB", "WR"),
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

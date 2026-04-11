import polars as pl

from fantasy_sim.data.ensemble import EnsembleConfig, FfOpportunityConfig


class _StubLoader:
    def __init__(self, frame: pl.DataFrame) -> None:
        self.frame = frame
        self.calls: list[list[int]] = []

    def load_weekly(self, seasons: list[int]) -> pl.DataFrame:
        self.calls.append(list(seasons))
        return self.frame


def _config() -> EnsembleConfig:
    return EnsembleConfig(
        enabled=True,
        ff_opportunity=FfOpportunityConfig(
            enabled=True,
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
    assert wr["fpts"] == 11.2
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

    assert rb["fpts"] == 13.0
    assert rb["rush_yards"] == 70.0
    assert stats.covered_rows == 1
    assert stats.uncovered_rows == 1

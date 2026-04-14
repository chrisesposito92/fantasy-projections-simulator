from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import polars as pl
import pytest

from fantasy_sim.data.pff.models import MatchupContext, QbSplitConfig, QbSplitFactors
from fantasy_sim.data.pff.qb_split import QbSplitEngine
from fantasy_sim.models.player import PlayerModel, PlayerOutcomes, PlayerUsage, TeamRoster


def _make_roster(team: str, qb_id: str = "00-0031234") -> TeamRoster:
    return TeamRoster(
        team=team,
        players=[
            PlayerModel(
                qb_id,
                "Starter QB",
                "QB",
                team,
                PlayerUsage(snap_share=1.0),
                PlayerOutcomes(),
            ),
            PlayerModel(
                f"{team}_WR1",
                "WR One",
                "WR",
                team,
                PlayerUsage(target_share=0.30),
                PlayerOutcomes(
                    catch_rate=0.65,
                    red_zone_catch_rate=0.60,
                    receiving_yards_dist=np.array([8.0, 12.0]),
                ),
            ),
        ],
    )


def _passing_detail_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "season": [2023, 2023, 2024, 2023, 2023, 2024],
            "week": [10, 11, 3, 10, 11, 3],
            "team": ["KC", "KC", "KC", "BUF", "BUF", "BUF"],
            "player_id": [101, 101, 101, 202, 202, 202],
            "game_id": [1, 2, 3, 4, 5, 6],
            "pressure_dropbacks": [15, 14, 8, 18, 17, 10],
            "no_pressure_dropbacks": [35, 32, 20, 36, 34, 24],
            "pressure_completion_percent": [48.0, 50.0, 51.0, 62.0, 60.0, 63.0],
            "no_pressure_completion_percent": [74.0, 75.0, 76.0, 75.0, 74.0, 76.0],
            "pressure_ypa": [5.5, 5.8, 6.0, 7.2, 7.0, 7.3],
            "no_pressure_ypa": [8.6, 8.4, 8.7, 8.4, 8.2, 8.5],
        }
    )


def _early_blend_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "season": [
                2023,
                2023,
                2023,
                2023,
                2024,
                2023,
                2023,
                2023,
                2023,
                2024,
            ],
            "week": [8, 9, 10, 11, 3, 8, 9, 10, 11, 3],
            "team": ["KC", "KC", "KC", "KC", "KC", "BUF", "BUF", "BUF", "BUF", "BUF"],
            "player_id": [101, 101, 101, 101, 101, 202, 202, 202, 202, 202],
            "game_id": [10, 11, 12, 13, 14, 20, 21, 22, 23, 24],
            "pressure_dropbacks": [10, 10, 10, 10, 10, 10, 10, 10, 10, 10],
            "no_pressure_dropbacks": [20, 20, 20, 20, 20, 20, 20, 20, 20, 20],
            "pressure_completion_percent": [50.0, 50.0, 50.0, 50.0, 70.0, 65.0, 65.0, 65.0, 65.0, 65.0],
            "no_pressure_completion_percent": [80.0, 80.0, 80.0, 80.0, 80.0, 80.0, 80.0, 80.0, 80.0, 80.0],
            "pressure_ypa": [5.0, 5.0, 5.0, 5.0, 8.0, 7.0, 7.0, 7.0, 7.0, 7.0],
            "no_pressure_ypa": [8.0, 8.0, 8.0, 8.0, 8.0, 8.0, 8.0, 8.0, 8.0, 8.0],
        }
    )


def _engine(
    data: pl.DataFrame,
    *,
    min_pressure_dropbacks: int = 1,
    min_clean_dropbacks: int = 1,
    min_games: int = 1,
    early_season_blend: bool = True,
) -> QbSplitEngine:
    loader = MagicMock()
    loader.load_facet.return_value = data
    config = QbSplitConfig(
        enabled=True,
        completion_sensitivity=0.10,
        yards_sensitivity=0.12,
        catch_rate_clamp=(0.95, 1.05),
        yards_scale_clamp=(0.94, 1.06),
        min_pressure_dropbacks=min_pressure_dropbacks,
        min_clean_dropbacks=min_clean_dropbacks,
        min_games=min_games,
        early_season_blend=early_season_blend,
    )
    return QbSplitEngine(loader, config)


def test_compute_returns_neutral_when_qb_crosswalk_is_missing():
    engine = _engine(_passing_detail_df())

    factors = engine.compute(
        roster=_make_roster("KC"),
        pff_crosswalk={202: "00-0039999"},
        training_seasons=[2023, 2024],
        target_season=2024,
        max_week=4,
        matchup_context=MatchupContext(sack_rate_factor=1.15, ol_pass_block_factor=0.90),
    )

    assert factors == QbSplitFactors()


def test_compute_penalizes_pressure_sensitive_qb_in_tough_matchup():
    engine = _engine(_passing_detail_df())

    factors = engine.compute(
        roster=_make_roster("KC"),
        pff_crosswalk={101: "00-0031234", 202: "00-0039999"},
        training_seasons=[2023, 2024],
        target_season=2024,
        max_week=4,
        matchup_context=MatchupContext(sack_rate_factor=1.20, ol_pass_block_factor=0.90),
    )

    assert factors.catch_rate_factor < 1.0
    assert factors.yards_scale_factor < 1.0
    assert factors.catch_rate_factor >= 0.95
    assert factors.yards_scale_factor >= 0.94


def test_compute_returns_neutral_for_neutral_pressure_environment():
    engine = _engine(_passing_detail_df())

    factors = engine.compute(
        roster=_make_roster("KC"),
        pff_crosswalk={101: "00-0031234", 202: "00-0039999"},
        training_seasons=[2023, 2024],
        target_season=2024,
        max_week=4,
        matchup_context=MatchupContext(sack_rate_factor=1.0, ol_pass_block_factor=1.0),
    )

    assert factors == QbSplitFactors()


def test_compute_blends_current_and_previous_season_rows_early():
    engine = _engine(
        _early_blend_df(),
        min_pressure_dropbacks=20,
        min_clean_dropbacks=40,
        min_games=4,
        early_season_blend=True,
    )

    factors = engine.compute(
        roster=_make_roster("KC"),
        pff_crosswalk={101: "00-0031234", 202: "00-0039999"},
        training_seasons=[2023, 2024],
        target_season=2024,
        max_week=4,
        matchup_context=MatchupContext(sack_rate_factor=1.20, ol_pass_block_factor=0.90),
    )

    assert factors.catch_rate_factor == pytest.approx(0.9989295410471881)
    assert factors.yards_scale_factor == pytest.approx(0.9983706959706959)

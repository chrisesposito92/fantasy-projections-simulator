from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from fantasy_sim.data.tracking.models import QbContextConfig
from fantasy_sim.data.tracking.qb_context import QbContextEngine, _bounded_factor
from fantasy_sim.engine.types import TeamDistributions
from fantasy_sim.models.distributions import (
    DriveStartModel,
    KickingModel,
    PlayCallingDist,
    PlayOutcomeDist,
    TurnoverRates,
)
from fantasy_sim.models.player import PlayerModel, PlayerOutcomes, PlayerUsage, TeamRoster


def _make_qb(
    player_id: str,
    snap_share: float,
    scramble_rate: float,
) -> PlayerModel:
    return PlayerModel(
        player_id=player_id,
        name=player_id,
        position="QB",
        team="BUF",
        usage=PlayerUsage(
            snap_share=snap_share,
            scramble_rate=scramble_rate,
        ),
        outcomes=PlayerOutcomes(),
    )


def _make_team_distributions() -> TeamDistributions:
    return TeamDistributions(
        play_calling=PlayCallingDist(
            team="BUF",
            distributions={},
            default={"pass": 0.55, "run": 0.45},
        ),
        play_outcomes=PlayOutcomeDist(distributions={}, defaults={}),
        turnover_rates=TurnoverRates(
            team="BUF",
            int_rate=0.02,
            fumble_rate=0.01,
            sack_rate=0.06,
            sack_fumble_rate=0.10,
        ),
        kicking=KickingModel(
            fg_make_rate={"0_39": 0.95, "40_49": 0.82, "50_plus": 0.62},
            xp_rate=0.98,
        ),
        drive_start=DriveStartModel(
            touchback_rate=0.65,
            touchback_yardline=75,
            return_yardlines=np.array([72, 75, 78], dtype=int),
        ),
    )


def test_qb_context_updates_team_context_and_starting_qb():
    roster = TeamRoster(
        team="BUF",
        players=[
            _make_qb("qb-starter", snap_share=0.75, scramble_rate=0.08),
            _make_qb("qb-backup", snap_share=0.25, scramble_rate=0.03),
        ],
    )
    team_dists = _make_team_distributions()
    features = pl.DataFrame(
        {
            "team": ["BUF", "BUF", "MIA"],
            "player_id": ["qb-starter", "qb-backup", "mia-qb"],
            "dropbacks": [34, 30, 36],
            "no_huddle_rate": [0.18, 0.05, 0.10],
            "play_action_rate": [0.30, 0.12, 0.20],
            "pressure_rate": [0.22, 0.15, 0.18],
            "blitz_rate": [0.31, 0.18, 0.24],
        }
    )
    engine = QbContextEngine(QbContextConfig())

    engine.apply(roster, team_dists, features)

    pace_baseline = features.get_column("no_huddle_rate").mean() + features.get_column(
        "play_action_rate"
    ).mean()
    pass_baseline = features.get_column("play_action_rate").mean()
    sack_baseline = features.get_column("pressure_rate").mean()
    scramble_baseline = features.get_column("pressure_rate").mean() + features.get_column(
        "blitz_rate"
    ).mean()

    pace_factor = _bounded_factor(
        0.18 + 0.30,
        pace_baseline,
        engine.config.pace_sensitivity,
        engine.config.factor_clamp,
    )
    pass_factor = _bounded_factor(
        0.30,
        pass_baseline,
        engine.config.pass_rate_sensitivity,
        engine.config.factor_clamp,
    )
    sack_factor = _bounded_factor(
        0.22,
        sack_baseline,
        engine.config.sack_rate_sensitivity,
        engine.config.factor_clamp,
    )
    scramble_factor = _bounded_factor(
        0.22 + 0.31,
        scramble_baseline,
        engine.config.scramble_sensitivity,
        engine.config.factor_clamp,
    )

    starter = roster.players[0]
    backup = roster.players[1]
    assert team_dists.pace_factor == pytest.approx(1.0 * pace_factor)
    assert team_dists.play_calling.default["pass"] == pytest.approx(0.55 * pass_factor)
    assert team_dists.play_calling.default["run"] == pytest.approx(0.45)
    assert team_dists.turnover_rates.sack_rate == pytest.approx(0.06 * sack_factor)
    assert starter.usage.scramble_rate == pytest.approx(0.08 * scramble_factor)
    assert backup.usage.scramble_rate == pytest.approx(0.03)


def test_qb_context_skips_qb_below_min_dropbacks():
    roster = TeamRoster(
        team="BUF",
        players=[_make_qb("qb-starter", snap_share=0.80, scramble_rate=0.08)],
    )
    team_dists = _make_team_distributions()
    features = pl.DataFrame(
        {
            "team": ["BUF"],
            "player_id": ["qb-starter"],
            "dropbacks": [19],
            "no_huddle_rate": [0.24],
            "play_action_rate": [0.34],
            "pressure_rate": [0.28],
            "blitz_rate": [0.35],
        }
    )
    engine = QbContextEngine(QbContextConfig(min_dropbacks=20))

    engine.apply(roster, team_dists, features)

    starter = roster.players[0]
    assert team_dists.pace_factor == pytest.approx(1.0)
    assert team_dists.play_calling.default["pass"] == pytest.approx(0.55)
    assert team_dists.play_calling.default["run"] == pytest.approx(0.45)
    assert team_dists.turnover_rates.sack_rate == pytest.approx(0.06)
    assert starter.usage.scramble_rate == pytest.approx(0.08)

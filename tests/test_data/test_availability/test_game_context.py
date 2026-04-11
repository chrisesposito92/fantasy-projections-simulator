from unittest.mock import MagicMock, patch

import numpy as np

from fantasy_sim.data.availability.models import AvailabilityConfig
from fantasy_sim.data.game_context import GameContextBuilder
from fantasy_sim.data.usage.models import UsageConfig
from fantasy_sim.engine.types import TeamDistributions
from fantasy_sim.models.distributions import (
    DriveStartModel,
    KickingModel,
    PlayCallingDist,
    PlayOutcomeDist,
    TurnoverRates,
)
from fantasy_sim.models.player import PlayerModel, PlayerOutcomes, PlayerUsage, TeamRoster


def _make_dists(team: str) -> TeamDistributions:
    return TeamDistributions(
        play_calling=PlayCallingDist(team=team, distributions={}, default={"pass": 0.57, "run": 0.43}),
        play_outcomes=PlayOutcomeDist(distributions={}, defaults={"pass": np.array([5.0]), "run": np.array([3.0])}),
        turnover_rates=TurnoverRates(team=team, int_rate=0.02, fumble_rate=0.01, sack_rate=0.06, sack_fumble_rate=0.1),
        kicking=KickingModel(fg_make_rate={"0_39": 0.9, "40_49": 0.8, "50_plus": 0.7}, xp_rate=0.95),
        drive_start=DriveStartModel(touchback_rate=0.6, touchback_yardline=75, return_yardlines=np.array([72.0])),
    )


def _make_roster(team: str) -> TeamRoster:
    return TeamRoster(
        team=team,
        players=[
            PlayerModel(
                f"{team}_RB1",
                "RB One",
                "RB",
                team,
                PlayerUsage(carry_share=0.6, target_share=0.2),
                PlayerOutcomes(),
            ),
            PlayerModel(
                f"{team}_WR1",
                "WR One",
                "WR",
                team,
                PlayerUsage(carry_share=0.0, target_share=0.5),
                PlayerOutcomes(catch_rate=0.65, receiving_yards_dist=np.array([8.0])),
            ),
        ],
    )


def test_builder_creates_availability_engine_when_enabled(tmp_path):
    builder = GameContextBuilder(
        cache_dir=tmp_path / "cache",
        availability_config=AvailabilityConfig(enabled=True),
    )

    assert builder._availability_engine is not None


def test_build_game_applies_availability_before_usage(tmp_path):
    builder = GameContextBuilder(
        cache_dir=tmp_path / "cache",
        availability_config=AvailabilityConfig(enabled=True),
        usage_config=UsageConfig(enabled=True),
    )
    builder._vegas_engine = None

    home_roster = _make_roster("KC")
    away_roster = _make_roster("BUF")
    builder.build_team_distributions = MagicMock(side_effect=[_make_dists("KC"), _make_dists("BUF")])
    builder.build_team_roster = MagicMock(side_effect=[home_roster, away_roster])

    events: list[str] = []

    def availability_apply(roster, season, week):
        events.append(f"availability:{roster.team}")

    def usage_apply(roster, season, week, pff_crosswalk=None):
        events.append(f"usage:{roster.team}")
        return {}

    builder._availability_engine = MagicMock()
    builder._availability_engine.apply.side_effect = availability_apply
    builder._usage_engine = MagicMock()
    builder._usage_engine.apply.side_effect = usage_apply

    with patch("fantasy_sim.data.player_builder._normalize_roster_shares") as mock_normalize:
        def normalize_side_effect(roster):
            events.append(f"normalize:{roster.team}")

        mock_normalize.side_effect = normalize_side_effect

        builder.build_game(
            "KC",
            "BUF",
            training_seasons=[2024],
            target_season=2024,
            week=1,
        )

    assert events == [
        "availability:KC",
        "availability:BUF",
        "normalize:KC",
        "normalize:BUF",
        "usage:KC",
        "usage:BUF",
        "normalize:KC",
        "normalize:BUF",
    ]

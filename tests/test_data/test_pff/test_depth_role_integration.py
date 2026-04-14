from unittest.mock import MagicMock, patch

import numpy as np

from fantasy_sim.data.game_context import GameContextBuilder
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
                f"{team}_WR1",
                "WR One",
                "WR",
                team,
                PlayerUsage(target_share=0.50, air_yards_share=0.50),
                PlayerOutcomes(),
            ),
            PlayerModel(
                f"{team}_TE1",
                "TE One",
                "TE",
                team,
                PlayerUsage(target_share=0.20, air_yards_share=0.12),
                PlayerOutcomes(),
            ),
        ],
    )


def test_depth_role_engine_created_when_enabled(tmp_path):
    from fantasy_sim.data.pff.models import DepthRoleConfig, PffConfig

    pff_config = PffConfig(
        enabled=True,
        depth_role=DepthRoleConfig(enabled=True),
    )

    with patch("fantasy_sim.data.pff.loader.PffLoader") as mock_loader:
        mock_loader.return_value.is_available.return_value = True
        builder = GameContextBuilder(cache_dir=tmp_path / "cache", pff_config=pff_config)

    assert builder._depth_role_engine is not None


def test_build_game_applies_depth_role_after_tier_before_coverage(tmp_path):
    builder = GameContextBuilder(cache_dir=tmp_path / "cache")
    builder.build_team_distributions = MagicMock(side_effect=[_make_dists("KC"), _make_dists("BUF")])
    builder.build_team_roster = MagicMock(side_effect=[_make_roster("KC"), _make_roster("BUF")])
    builder.loader.load_rosters = MagicMock(return_value=MagicMock())
    builder.loader.load_pbp = MagicMock(return_value=MagicMock())
    builder._availability_engine = None
    builder._usage_engine = None
    builder._tracking_engine = None
    builder._props_engine = None
    builder._matchup_engine = None
    builder._team_context_engine = None
    builder._talent_stabilizer = None
    builder._dst_baseline_engine = None
    builder._kicker_engine = None
    builder._weather_engine = None
    builder._vegas_engine = None
    builder._ensure_pff_crosswalk = MagicMock()
    builder._pff_crosswalk = {}

    events: list[str] = []

    builder._tier_engine = MagicMock()
    builder._tier_engine.apply_tiers.side_effect = lambda *args, **kwargs: events.append("tier")
    builder._depth_role_engine = MagicMock()
    builder._depth_role_engine.apply.side_effect = lambda *args, **kwargs: events.append("depth")
    builder._coverage_engine = MagicMock()
    builder._coverage_engine.compute.side_effect = lambda *args, **kwargs: events.append("coverage") or {}

    with patch("fantasy_sim.data.player_builder._normalize_roster_shares") as mock_normalize:
        mock_normalize.side_effect = lambda roster: events.append(f"normalize:{roster.team}")
        builder.build_game("KC", "BUF", training_seasons=[2024], target_season=2024, week=8)

    assert events == [
        "tier",
        "tier",
        "normalize:KC",
        "normalize:BUF",
        "depth",
        "depth",
        "normalize:KC",
        "normalize:BUF",
        "coverage",
        "coverage",
    ]

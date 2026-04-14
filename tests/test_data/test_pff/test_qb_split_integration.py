from unittest.mock import MagicMock, patch

import numpy as np
import polars as pl

from fantasy_sim.data.game_context import GameContextBuilder
from fantasy_sim.data.pff.models import (
    MatchupConfig,
    MatchupContext,
    PffConfig,
    QbSplitConfig,
    QbSplitFactors,
)
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
                f"{team}_QB",
                "QB One",
                "QB",
                team,
                PlayerUsage(snap_share=1.0, scramble_rate=0.18),
                PlayerOutcomes(),
            ),
            PlayerModel(
                f"{team}_WR1",
                "WR One",
                "WR",
                team,
                PlayerUsage(target_share=0.40, air_yards_share=0.52),
                PlayerOutcomes(catch_rate=0.65, red_zone_catch_rate=0.60, receiving_yards_dist=np.array([10.0, 14.0])),
            ),
        ],
    )


def test_qb_split_engine_created_when_enabled(tmp_path):
    pff_config = PffConfig(
        enabled=True,
        qb_split=QbSplitConfig(enabled=True),
    )

    with patch("fantasy_sim.data.pff.loader.PffLoader") as mock_loader:
        mock_loader.return_value.is_available.return_value = True
        with patch("fantasy_sim.data.pff.qb_split.QbSplitEngine") as mock_engine:
            builder = GameContextBuilder(cache_dir=tmp_path / "cache", pff_config=pff_config)

    assert builder._qb_split_engine is mock_engine.return_value
    mock_engine.assert_called_once_with(mock_loader.return_value, pff_config.qb_split)


def test_qb_split_engine_not_created_without_matchup_dependency(tmp_path):
    pff_config = PffConfig(
        enabled=True,
        matchup=MatchupConfig(enabled=False),
        qb_split=QbSplitConfig(enabled=True),
    )

    with patch("fantasy_sim.data.pff.loader.PffLoader") as mock_loader:
        mock_loader.return_value.is_available.return_value = True
        with patch("fantasy_sim.data.game_context.logger") as mock_logger:
            builder = GameContextBuilder(cache_dir=tmp_path / "cache", pff_config=pff_config)

    assert builder._matchup_engine is None
    assert builder._qb_split_engine is None
    mock_logger.info.assert_any_call("PFF QB split requested but matchup engine unavailable; qb split disabled")


def test_ensure_pff_crosswalk_includes_target_season_summaries_for_target_only_qb(tmp_path):
    builder = GameContextBuilder(cache_dir=tmp_path / "cache")
    builder._pff_loader = MagicMock()
    builder.loader.load_rosters = MagicMock(
        return_value=pl.DataFrame(
            {
                "player_id": ["KC_QB"],
                "player_name": ["QB One"],
                "team": ["KC"],
                "position": ["QB"],
                "pff_id": [101],
            }
        )
    )

    empty_summary = pl.DataFrame({"player_id": [], "player": [], "team": []})
    target_only_passing = pl.DataFrame(
        {
            "player_id": [101],
            "player": ["QB One"],
            "team": ["KC"],
        }
    )

    def _load_facet(facet: str, seasons: list[int]) -> pl.DataFrame:
        if facet != "passing_summary":
            return empty_summary
        if seasons == [2023]:
            return empty_summary
        if seasons == [2023, 2024]:
            return target_only_passing
        raise AssertionError(f"Unexpected seasons for {facet}: {seasons}")

    builder._pff_loader.load_facet.side_effect = _load_facet
    builder._pff_loader.build_crosswalk.return_value = {101: "KC_QB"}

    builder._ensure_pff_crosswalk(training_seasons=[2023], target_season=2024)

    assert builder._pff_crosswalk == {101: "KC_QB"}
    builder._pff_loader.build_crosswalk.assert_called_once()
    pff_data, nfl_roster, roster_season = builder._pff_loader.build_crosswalk.call_args.args
    assert pff_data.to_dicts() == [{"player_id": 101, "player": "QB One", "team": "KC"}]
    assert nfl_roster.to_dicts() == [
        {
            "player_id": "KC_QB",
            "player_name": "QB One",
            "team": "KC",
            "position": "QB",
            "pff_id": 101,
        }
    ]
    assert roster_season == 2024
    assert [call.args for call in builder._pff_loader.load_facet.call_args_list] == [
        ("receiving_summary", [2023, 2024]),
        ("rushing_summary", [2023, 2024]),
        ("passing_summary", [2023, 2024]),
    ]


def test_build_game_applies_qb_split_after_tier_before_depth_role(tmp_path):
    builder = GameContextBuilder(cache_dir=tmp_path / "cache")
    builder.build_team_distributions = MagicMock(side_effect=[_make_dists("KC"), _make_dists("BUF")])
    builder.build_team_roster = MagicMock(side_effect=[_make_roster("KC"), _make_roster("BUF")])
    builder.loader.load_rosters = MagicMock(return_value=MagicMock())
    builder.loader.load_pbp = MagicMock(return_value=MagicMock())
    builder._availability_engine = None
    builder._usage_engine = None
    builder._tracking_engine = None
    builder._props_engine = None
    builder._talent_stabilizer = None
    builder._dst_baseline_engine = None
    builder._kicker_engine = None
    builder._weather_engine = None
    builder._vegas_engine = None
    builder._pff_crosswalk = {}

    home_matchup_ctx = MatchupContext(catch_rate_factor=1.03, sack_rate_factor=1.08)
    away_matchup_ctx = MatchupContext(catch_rate_factor=0.97, sack_rate_factor=0.92)
    home_team_ctx = object()
    away_team_ctx = object()
    events: list[str] = []

    builder._ensure_pff_crosswalk = MagicMock(side_effect=lambda *args, **kwargs: None)
    builder._matchup_engine = MagicMock()
    builder._matchup_engine.compute.side_effect = [home_matchup_ctx, away_matchup_ctx]
    builder._apply_matchup = MagicMock(side_effect=lambda *args, **kwargs: events.append("matchup_apply"))

    builder._team_context_engine = MagicMock()
    builder._team_context_engine.compute.side_effect = [home_team_ctx, away_team_ctx]

    builder._tier_engine = MagicMock()
    builder._tier_engine.apply_tiers.side_effect = lambda *args, **kwargs: events.append("tier")

    builder._qb_split_engine = MagicMock()

    def _record_qb_split(*args, **kwargs):
        events.append("qb_split_compute")
        return QbSplitFactors(catch_rate_factor=0.98, yards_scale_factor=1.02)

    builder._qb_split_engine.compute.side_effect = _record_qb_split
    builder._apply_qb_split = MagicMock(side_effect=lambda *args, **kwargs: events.append("qb_split_apply"))

    builder._depth_role_engine = MagicMock()
    builder._depth_role_engine.apply.side_effect = lambda *args, **kwargs: events.append("depth")

    builder._coverage_engine = MagicMock()
    builder._coverage_engine.compute.side_effect = lambda *args, **kwargs: events.append("coverage") or {}

    with patch("fantasy_sim.data.player_builder._normalize_roster_shares") as mock_normalize:
        mock_normalize.side_effect = lambda roster: events.append(f"normalize:{roster.team}")
        builder.build_game("KC", "BUF", training_seasons=[2024], target_season=2024, week=8)

    assert events == [
        "matchup_apply",
        "matchup_apply",
        "tier",
        "tier",
        "normalize:KC",
        "normalize:BUF",
        "qb_split_compute",
        "qb_split_compute",
        "qb_split_apply",
        "qb_split_apply",
        "depth",
        "depth",
        "normalize:KC",
        "normalize:BUF",
        "coverage",
        "coverage",
    ]
    assert builder._qb_split_engine.compute.call_args_list[0].kwargs["matchup_context"] is home_matchup_ctx
    assert builder._qb_split_engine.compute.call_args_list[1].kwargs["matchup_context"] is away_matchup_ctx
    assert builder._tier_engine.apply_tiers.call_args_list[0].kwargs["team_context"] is home_team_ctx
    assert builder._tier_engine.apply_tiers.call_args_list[1].kwargs["team_context"] is away_team_ctx


def test_apply_qb_split_only_mutates_pass_catcher_efficiency_fields():
    roster = _make_roster("KC")
    roster.players.append(
        PlayerModel(
            "KC_TE1",
            "TE One",
            "TE",
            "KC",
            PlayerUsage(target_share=0.18, air_yards_share=0.14),
            PlayerOutcomes(
                catch_rate=0.70,
                red_zone_catch_rate=0.0,
                receiving_yards_dist=np.array([7.0, 9.0]),
            ),
        )
    )
    qb = next(player for player in roster.players if player.position == "QB")
    wr = next(player for player in roster.players if player.position == "WR")
    te = next(player for player in roster.players if player.position == "TE")

    original_qb_catch_rate = qb.outcomes.catch_rate
    original_qb_scramble_rate = qb.usage.scramble_rate
    original_target_share = wr.usage.target_share
    original_air_yards_share = wr.usage.air_yards_share
    original_catch_rate = wr.outcomes.catch_rate
    original_rz_catch_rate = wr.outcomes.red_zone_catch_rate
    original_receiving_yards = wr.outcomes.receiving_yards_dist.copy()
    original_te_target_share = te.usage.target_share
    original_te_rz_catch_rate = te.outcomes.red_zone_catch_rate
    original_te_receiving_yards = te.outcomes.receiving_yards_dist.copy()

    GameContextBuilder._apply_qb_split(roster, None)
    assert qb.outcomes.catch_rate == original_qb_catch_rate
    assert qb.usage.scramble_rate == original_qb_scramble_rate
    assert wr.usage.target_share == original_target_share
    assert wr.usage.air_yards_share == original_air_yards_share
    np.testing.assert_allclose(wr.outcomes.receiving_yards_dist, original_receiving_yards)
    assert te.usage.target_share == original_te_target_share
    assert te.outcomes.red_zone_catch_rate == original_te_rz_catch_rate
    np.testing.assert_allclose(te.outcomes.receiving_yards_dist, original_te_receiving_yards)

    GameContextBuilder._apply_qb_split(
        roster,
        QbSplitFactors(catch_rate_factor=0.90, yards_scale_factor=1.10),
    )

    assert qb.outcomes.catch_rate == original_qb_catch_rate
    assert qb.usage.scramble_rate == original_qb_scramble_rate
    assert wr.usage.target_share == original_target_share
    assert wr.usage.air_yards_share == original_air_yards_share
    assert wr.outcomes.catch_rate == original_catch_rate * 0.90
    assert wr.outcomes.red_zone_catch_rate == original_rz_catch_rate * 0.90
    np.testing.assert_allclose(wr.outcomes.receiving_yards_dist, original_receiving_yards * 1.10)
    assert te.usage.target_share == original_te_target_share
    assert te.outcomes.catch_rate == 0.70 * 0.90
    assert te.outcomes.red_zone_catch_rate == original_te_rz_catch_rate
    np.testing.assert_allclose(te.outcomes.receiving_yards_dist, original_te_receiving_yards * 1.10)

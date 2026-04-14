from unittest.mock import MagicMock, patch

import numpy as np

from fantasy_sim.data.game_context import GameContextBuilder
from fantasy_sim.data.pff.models import (
    PffConfig,
    QbSplitFactors,
    RbSchemeFitConfig,
    RbSchemeFitFactors,
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
                PlayerUsage(snap_share=1.0, carry_share=0.12, scramble_rate=0.18),
                PlayerOutcomes(
                    rushing_yards_dist=np.array([4.0, 7.0]),
                    rushing_td_factor=1.19,
                    i5_rushing_td_factor=1.27,
                ),
            ),
            PlayerModel(
                f"{team}_RB1",
                "RB One",
                "RB",
                team,
                PlayerUsage(
                    carry_share=0.58,
                    target_share=0.10,
                    red_zone_carry_share=0.55,
                    outer_rz_carry_share=0.52,
                    goal_line_carry_share=0.65,
                ),
                PlayerOutcomes(
                    rushing_yards_dist=np.array([3.0, 5.0, 8.0]),
                    receiving_td_factor=0.91,
                    rushing_td_factor=1.14,
                    i5_rushing_td_factor=1.31,
                ),
            ),
            PlayerModel(
                f"{team}_RB2",
                "RB Two",
                "RB",
                team,
                PlayerUsage(
                    carry_share=0.22,
                    target_share=0.06,
                    red_zone_carry_share=0.18,
                    outer_rz_carry_share=0.16,
                    goal_line_carry_share=0.10,
                ),
                PlayerOutcomes(
                    rushing_yards_dist=np.array([2.0, 4.0, 6.0]),
                    receiving_td_factor=1.08,
                    rushing_td_factor=0.87,
                    i5_rushing_td_factor=1.22,
                ),
            ),
            PlayerModel(
                f"{team}_WR1",
                "WR One",
                "WR",
                team,
                PlayerUsage(target_share=0.32, air_yards_share=0.44),
                PlayerOutcomes(
                    catch_rate=0.66,
                    red_zone_catch_rate=0.61,
                    receiving_yards_dist=np.array([9.0, 14.0]),
                    receiving_td_factor=1.17,
                    rushing_td_factor=0.95,
                    i5_rushing_td_factor=0.89,
                ),
            ),
        ],
    )


def test_rb_scheme_fit_engine_created_when_enabled(tmp_path):
    pff_config = PffConfig(
        enabled=True,
        rb_scheme_fit=RbSchemeFitConfig(enabled=True),
    )

    with patch("fantasy_sim.data.pff.loader.PffLoader") as mock_loader:
        mock_loader.return_value.is_available.return_value = True
        with patch("fantasy_sim.data.pff.rb_scheme_fit.RbSchemeFitEngine") as mock_engine:
            builder = GameContextBuilder(cache_dir=tmp_path / "cache", pff_config=pff_config)

    assert builder._rb_scheme_fit_engine is mock_engine.return_value
    mock_engine.assert_called_once_with(mock_loader.return_value, pff_config.rb_scheme_fit)


def test_build_game_applies_rb_scheme_fit_after_tier_before_qb_split(tmp_path):
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
    builder._depth_role_engine = None
    builder._coverage_engine = None
    builder._dst_baseline_engine = None
    builder._kicker_engine = None
    builder._weather_engine = None
    builder._vegas_engine = None
    builder._ensure_pff_crosswalk = MagicMock()
    builder._pff_crosswalk = {}

    events: list[str] = []

    builder._tier_engine = MagicMock()
    builder._tier_engine.apply_tiers.side_effect = lambda *args, **kwargs: events.append("tier")

    builder._rb_scheme_fit_engine = MagicMock()

    def _record_rb_scheme_fit(*args, **kwargs):
        events.append("rb_scheme_fit_compute")
        roster = kwargs["roster"]
        return {
            f"{roster.team}_RB1": RbSchemeFitFactors(rushing_yards_factor=1.04),
        }

    builder._rb_scheme_fit_engine.compute.side_effect = _record_rb_scheme_fit
    builder._apply_rb_scheme_fit = MagicMock(
        side_effect=lambda *args, **kwargs: events.append("rb_scheme_fit_apply")
    )

    builder._qb_split_engine = MagicMock()
    builder._qb_split_engine.compute.side_effect = (
        lambda *args, **kwargs: events.append("qb_split_compute")
        or QbSplitFactors(catch_rate_factor=0.98, yards_scale_factor=1.02)
    )
    builder._apply_qb_split = MagicMock(side_effect=lambda *args, **kwargs: events.append("qb_split_apply"))

    with patch("fantasy_sim.data.player_builder._normalize_roster_shares") as mock_normalize:
        mock_normalize.side_effect = lambda roster: events.append(f"normalize:{roster.team}")
        builder.build_game("KC", "BUF", training_seasons=[2024], target_season=2025, week=8)

    assert events == [
        "tier",
        "tier",
        "normalize:KC",
        "normalize:BUF",
        "rb_scheme_fit_compute",
        "rb_scheme_fit_compute",
        "rb_scheme_fit_apply",
        "rb_scheme_fit_apply",
        "qb_split_compute",
        "qb_split_compute",
        "qb_split_apply",
        "qb_split_apply",
    ]
    assert builder._rb_scheme_fit_engine.compute.call_args_list[0].kwargs["training_seasons"] == [2024, 2025]
    assert builder._rb_scheme_fit_engine.compute.call_args_list[1].kwargs["training_seasons"] == [2024, 2025]


def test_apply_rb_scheme_fit_only_mutates_rb_rushing_yards_dist():
    roster = _make_roster("KC")
    qb = next(player for player in roster.players if player.position == "QB")
    rb1 = next(player for player in roster.players if player.player_id == "KC_RB1")
    rb2 = next(player for player in roster.players if player.player_id == "KC_RB2")
    wr = next(player for player in roster.players if player.position == "WR")

    original_qb_carry_share = qb.usage.carry_share
    original_qb_scramble_rate = qb.usage.scramble_rate
    original_qb_rushing_yards = qb.outcomes.rushing_yards_dist.copy()
    original_qb_rushing_td_factor = qb.outcomes.rushing_td_factor
    original_qb_i5_rushing_td_factor = qb.outcomes.i5_rushing_td_factor
    original_rb1_carry_share = rb1.usage.carry_share
    original_rb1_rz_carry_share = rb1.usage.red_zone_carry_share
    original_rb1_outer_rz_carry_share = rb1.usage.outer_rz_carry_share
    original_rb1_goal_line_carry_share = rb1.usage.goal_line_carry_share
    original_rb1_rushing_yards = rb1.outcomes.rushing_yards_dist.copy()
    original_rb1_receiving_td_factor = rb1.outcomes.receiving_td_factor
    original_rb1_rushing_td_factor = rb1.outcomes.rushing_td_factor
    original_rb1_i5_rushing_td_factor = rb1.outcomes.i5_rushing_td_factor
    original_rb2_carry_share = rb2.usage.carry_share
    original_rb2_goal_line_carry_share = rb2.usage.goal_line_carry_share
    original_rb2_rushing_yards = rb2.outcomes.rushing_yards_dist.copy()
    original_rb2_receiving_td_factor = rb2.outcomes.receiving_td_factor
    original_rb2_rushing_td_factor = rb2.outcomes.rushing_td_factor
    original_rb2_i5_rushing_td_factor = rb2.outcomes.i5_rushing_td_factor
    original_wr_target_share = wr.usage.target_share
    original_wr_air_yards_share = wr.usage.air_yards_share
    original_wr_catch_rate = wr.outcomes.catch_rate
    original_wr_rz_catch_rate = wr.outcomes.red_zone_catch_rate
    original_wr_receiving_yards = wr.outcomes.receiving_yards_dist.copy()
    original_wr_receiving_td_factor = wr.outcomes.receiving_td_factor
    original_wr_rushing_td_factor = wr.outcomes.rushing_td_factor
    original_wr_i5_rushing_td_factor = wr.outcomes.i5_rushing_td_factor

    GameContextBuilder._apply_rb_scheme_fit(roster, None)

    assert qb.usage.carry_share == original_qb_carry_share
    assert qb.usage.scramble_rate == original_qb_scramble_rate
    np.testing.assert_allclose(qb.outcomes.rushing_yards_dist, original_qb_rushing_yards)
    assert qb.outcomes.rushing_td_factor == original_qb_rushing_td_factor
    assert qb.outcomes.i5_rushing_td_factor == original_qb_i5_rushing_td_factor
    assert rb1.usage.carry_share == original_rb1_carry_share
    assert rb1.usage.red_zone_carry_share == original_rb1_rz_carry_share
    assert rb1.usage.outer_rz_carry_share == original_rb1_outer_rz_carry_share
    assert rb1.usage.goal_line_carry_share == original_rb1_goal_line_carry_share
    np.testing.assert_allclose(rb1.outcomes.rushing_yards_dist, original_rb1_rushing_yards)
    assert rb1.outcomes.receiving_td_factor == original_rb1_receiving_td_factor
    assert rb1.outcomes.rushing_td_factor == original_rb1_rushing_td_factor
    assert rb1.outcomes.i5_rushing_td_factor == original_rb1_i5_rushing_td_factor
    assert rb2.usage.carry_share == original_rb2_carry_share
    assert rb2.usage.goal_line_carry_share == original_rb2_goal_line_carry_share
    np.testing.assert_allclose(rb2.outcomes.rushing_yards_dist, original_rb2_rushing_yards)
    assert rb2.outcomes.receiving_td_factor == original_rb2_receiving_td_factor
    assert rb2.outcomes.rushing_td_factor == original_rb2_rushing_td_factor
    assert rb2.outcomes.i5_rushing_td_factor == original_rb2_i5_rushing_td_factor
    assert wr.usage.target_share == original_wr_target_share
    assert wr.usage.air_yards_share == original_wr_air_yards_share
    assert wr.outcomes.catch_rate == original_wr_catch_rate
    assert wr.outcomes.red_zone_catch_rate == original_wr_rz_catch_rate
    np.testing.assert_allclose(wr.outcomes.receiving_yards_dist, original_wr_receiving_yards)
    assert wr.outcomes.receiving_td_factor == original_wr_receiving_td_factor
    assert wr.outcomes.rushing_td_factor == original_wr_rushing_td_factor
    assert wr.outcomes.i5_rushing_td_factor == original_wr_i5_rushing_td_factor

    GameContextBuilder._apply_rb_scheme_fit(
        roster,
        {"KC_RB1": RbSchemeFitFactors(rushing_yards_factor=1.10)},
    )

    assert qb.usage.carry_share == original_qb_carry_share
    assert qb.usage.scramble_rate == original_qb_scramble_rate
    np.testing.assert_allclose(qb.outcomes.rushing_yards_dist, original_qb_rushing_yards)
    assert qb.outcomes.rushing_td_factor == original_qb_rushing_td_factor
    assert qb.outcomes.i5_rushing_td_factor == original_qb_i5_rushing_td_factor
    assert rb1.usage.carry_share == original_rb1_carry_share
    assert rb1.usage.red_zone_carry_share == original_rb1_rz_carry_share
    assert rb1.usage.outer_rz_carry_share == original_rb1_outer_rz_carry_share
    assert rb1.usage.goal_line_carry_share == original_rb1_goal_line_carry_share
    np.testing.assert_allclose(rb1.outcomes.rushing_yards_dist, original_rb1_rushing_yards * 1.10)
    assert rb1.outcomes.receiving_td_factor == original_rb1_receiving_td_factor
    assert rb1.outcomes.rushing_td_factor == original_rb1_rushing_td_factor
    assert rb1.outcomes.i5_rushing_td_factor == original_rb1_i5_rushing_td_factor
    assert rb2.usage.carry_share == original_rb2_carry_share
    assert rb2.usage.goal_line_carry_share == original_rb2_goal_line_carry_share
    np.testing.assert_allclose(rb2.outcomes.rushing_yards_dist, original_rb2_rushing_yards)
    assert rb2.outcomes.receiving_td_factor == original_rb2_receiving_td_factor
    assert rb2.outcomes.rushing_td_factor == original_rb2_rushing_td_factor
    assert rb2.outcomes.i5_rushing_td_factor == original_rb2_i5_rushing_td_factor
    assert wr.usage.target_share == original_wr_target_share
    assert wr.usage.air_yards_share == original_wr_air_yards_share
    assert wr.outcomes.catch_rate == original_wr_catch_rate
    assert wr.outcomes.red_zone_catch_rate == original_wr_rz_catch_rate
    np.testing.assert_allclose(wr.outcomes.receiving_yards_dist, original_wr_receiving_yards)
    assert wr.outcomes.receiving_td_factor == original_wr_receiving_td_factor
    assert wr.outcomes.rushing_td_factor == original_wr_rushing_td_factor
    assert wr.outcomes.i5_rushing_td_factor == original_wr_i5_rushing_td_factor

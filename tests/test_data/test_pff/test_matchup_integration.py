"""Integration tests for MatchupEngine wired into GameContextBuilder._apply_matchup."""

from __future__ import annotations

import numpy as np
import pytest

from fantasy_sim.data.game_context import GameContextBuilder
from fantasy_sim.data.pff.models import MatchupContext, PffConfig, MatchupConfig
from fantasy_sim.engine.types import TeamDistributions
from fantasy_sim.models.distributions import (
    PlayCallingDist,
    PlayOutcomeDist,
    TurnoverRates,
    KickingModel,
    DriveStartModel,
)
from fantasy_sim.models.player import PlayerModel, PlayerOutcomes, PlayerUsage, TeamRoster


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_dists(
    int_rate: float = 0.025,
    sack_rate: float = 0.065,
) -> TeamDistributions:
    """Build a minimal TeamDistributions for testing."""
    play_calling = PlayCallingDist(
        team="TST", distributions={}, default={"pass": 0.57, "run": 0.43}
    )
    play_outcomes = PlayOutcomeDist(distributions={}, defaults={})
    turnover_rates = TurnoverRates(
        team="TST",
        int_rate=int_rate,
        fumble_rate=0.012,
        sack_rate=sack_rate,
        sack_fumble_rate=0.10,
    )
    kicking = KickingModel(
        fg_make_rate={"0_39": 0.95, "40_49": 0.85, "50_plus": 0.70},
        xp_rate=0.99,
    )
    drive_start = DriveStartModel(
        touchback_rate=0.60,
        touchback_yardline=75,
        return_yardlines=np.array([70, 72, 74, 76, 78]),
    )
    return TeamDistributions(
        play_calling=play_calling,
        play_outcomes=play_outcomes,
        turnover_rates=turnover_rates,
        kicking=kicking,
        drive_start=drive_start,
    )


def _make_roster(
    catch_rate: float = 0.65,
    rz_catch_rate: float = 0.60,
    recv_yards: np.ndarray | None = None,
    rush_yards: np.ndarray | None = None,
) -> TeamRoster:
    """Build a minimal TeamRoster with one receiver and one rusher."""
    if recv_yards is None:
        recv_yards = np.array([5.0, 8.0, 12.0, 15.0, 20.0])
    if rush_yards is None:
        rush_yards = np.array([2.0, 3.0, 4.0, 5.0, 6.0])

    qb = PlayerModel(
        player_id="TST_QB",
        name="QB",
        position="QB",
        team="TST",
        usage=PlayerUsage(snap_share=1.0),
        outcomes=PlayerOutcomes(),
    )
    wr = PlayerModel(
        player_id="TST_WR",
        name="WR",
        position="WR",
        team="TST",
        usage=PlayerUsage(target_share=0.85),
        outcomes=PlayerOutcomes(
            catch_rate=catch_rate,
            red_zone_catch_rate=rz_catch_rate,
            receiving_yards_dist=recv_yards.copy(),
        ),
    )
    rb = PlayerModel(
        player_id="TST_RB",
        name="RB",
        position="RB",
        team="TST",
        usage=PlayerUsage(carry_share=1.0, target_share=0.15),
        outcomes=PlayerOutcomes(
            catch_rate=0.70,
            red_zone_catch_rate=0.65,
            receiving_yards_dist=np.array([3.0, 5.0, 7.0]),
            rushing_yards_dist=rush_yards.copy(),
        ),
    )
    return TeamRoster(team="TST", players=[qb, wr, rb])


# ---------------------------------------------------------------------------
# TestApplyMatchup
# ---------------------------------------------------------------------------

class TestApplyMatchup:
    def test_catch_rate_scaled_by_factor(self):
        """catch_rate_factor=0.90 reduces every receiver's catch_rate by 10%."""
        dists = _make_dists()
        roster = _make_roster(catch_rate=0.65, rz_catch_rate=0.60)
        ctx = MatchupContext(catch_rate_factor=0.90)

        GameContextBuilder._apply_matchup(dists, roster, ctx)

        wr = next(p for p in roster.players if p.player_id == "TST_WR")
        assert abs(wr.outcomes.catch_rate - 0.65 * 0.90) < 1e-9
        assert abs(wr.outcomes.red_zone_catch_rate - 0.60 * 0.90) < 1e-9

    def test_catch_rate_clamped_to_one(self):
        """catch_rate_factor > 1.0 never pushes catch_rate above 1.0."""
        dists = _make_dists()
        roster = _make_roster(catch_rate=0.99, rz_catch_rate=0.98)
        ctx = MatchupContext(catch_rate_factor=1.20)

        GameContextBuilder._apply_matchup(dists, roster, ctx)

        wr = next(p for p in roster.players if p.player_id == "TST_WR")
        assert wr.outcomes.catch_rate <= 1.0
        assert wr.outcomes.red_zone_catch_rate <= 1.0

    def test_catch_rate_clamped_to_zero(self):
        """catch_rate_factor very small never gives negative catch_rate."""
        dists = _make_dists()
        roster = _make_roster(catch_rate=0.01, rz_catch_rate=0.01)
        ctx = MatchupContext(catch_rate_factor=0.01)

        GameContextBuilder._apply_matchup(dists, roster, ctx)

        wr = next(p for p in roster.players if p.player_id == "TST_WR")
        assert wr.outcomes.catch_rate >= 0.0
        assert wr.outcomes.red_zone_catch_rate >= 0.0

    def test_sack_rate_scaled_by_combined_factors(self):
        """sack_rate_factor * ol_pass_block_factor both multiply sack_rate."""
        dists = _make_dists(sack_rate=0.065)
        roster = _make_roster()
        ctx = MatchupContext(sack_rate_factor=1.10, ol_pass_block_factor=0.95)

        GameContextBuilder._apply_matchup(dists, roster, ctx)

        expected = 0.065 * 1.10 * 0.95
        assert abs(dists.turnover_rates.sack_rate - expected) < 1e-9

    def test_int_rate_scaled(self):
        """int_rate_factor=1.15 increases int_rate by 15%."""
        dists = _make_dists(int_rate=0.025)
        roster = _make_roster()
        ctx = MatchupContext(int_rate_factor=1.15)

        GameContextBuilder._apply_matchup(dists, roster, ctx)

        expected = 0.025 * 1.15
        assert abs(dists.turnover_rates.int_rate - expected) < 1e-9

    def test_receiving_yards_shifted_up(self):
        """pass_yards_factor > 1.0 shifts receiving_yards_dist upward."""
        base = np.array([5.0, 10.0, 15.0])
        dists = _make_dists()
        roster = _make_roster(recv_yards=base)
        ctx = MatchupContext(pass_yards_factor=1.10)

        GameContextBuilder._apply_matchup(dists, roster, ctx)

        wr = next(p for p in roster.players if p.player_id == "TST_WR")
        shift = (1.10 - 1.0) * 10.0  # +1.0
        np.testing.assert_allclose(wr.outcomes.receiving_yards_dist, base + shift)

    def test_rushing_yards_shifted(self):
        """rush_yards_factor=0.90 produces a negative shift on rushing_yards_dist."""
        base = np.array([2.0, 3.0, 4.0, 5.0, 6.0])
        dists = _make_dists()
        roster = _make_roster(rush_yards=base)
        ctx = MatchupContext(rush_yards_factor=0.90)

        GameContextBuilder._apply_matchup(dists, roster, ctx)

        rb = next(p for p in roster.players if p.player_id == "TST_RB")
        shift = (0.90 - 1.0) * 10.0  # -1.0
        np.testing.assert_allclose(rb.outcomes.rushing_yards_dist, base + shift)

    def test_rushing_yards_combined_ol_factor(self):
        """rush_yards_factor and ol_run_block_factor combine multiplicatively."""
        base = np.array([3.0, 5.0, 7.0])
        dists = _make_dists()
        roster = _make_roster(rush_yards=base)
        ctx = MatchupContext(rush_yards_factor=0.95, ol_run_block_factor=1.05)

        GameContextBuilder._apply_matchup(dists, roster, ctx)

        rb = next(p for p in roster.players if p.player_id == "TST_RB")
        combined = 0.95 * 1.05
        shift = (combined - 1.0) * 10.0
        np.testing.assert_allclose(rb.outcomes.rushing_yards_dist, base + shift, rtol=1e-9)

    def test_neutral_context_changes_nothing(self):
        """All-1.0 MatchupContext leaves dists and roster completely unchanged."""
        dists = _make_dists(int_rate=0.025, sack_rate=0.065)
        recv_base = np.array([5.0, 10.0, 15.0])
        rush_base = np.array([2.0, 4.0, 6.0])
        roster = _make_roster(
            catch_rate=0.65, rz_catch_rate=0.60,
            recv_yards=recv_base, rush_yards=rush_base,
        )
        ctx = MatchupContext()  # all defaults = 1.0

        GameContextBuilder._apply_matchup(dists, roster, ctx)

        wr = next(p for p in roster.players if p.player_id == "TST_WR")
        rb = next(p for p in roster.players if p.player_id == "TST_RB")
        assert wr.outcomes.catch_rate == 0.65
        assert wr.outcomes.red_zone_catch_rate == 0.60
        assert dists.turnover_rates.sack_rate == 0.065
        assert dists.turnover_rates.int_rate == 0.025
        np.testing.assert_array_equal(wr.outcomes.receiving_yards_dist, recv_base)
        np.testing.assert_array_equal(rb.outcomes.rushing_yards_dist, rush_base)

    def test_qb_not_affected_by_catch_rate(self):
        """QB (target_share=0) is not modified by catch_rate_factor."""
        dists = _make_dists()
        roster = _make_roster()
        ctx = MatchupContext(catch_rate_factor=0.80)

        GameContextBuilder._apply_matchup(dists, roster, ctx)

        qb = next(p for p in roster.players if p.player_id == "TST_QB")
        # QB has target_share=0, so catch_rate (0.0) should remain 0.0
        assert qb.outcomes.catch_rate == 0.0

    def test_builder_accepts_pff_config(self):
        """GameContextBuilder(pff_config=PffConfig(...)) constructs without error."""
        cfg = PffConfig(enabled=False)
        builder = GameContextBuilder(pff_config=cfg)
        assert builder._pff_config is cfg
        assert builder._matchup_engine is None

    def test_builder_without_pff_has_no_engine(self):
        """Default GameContextBuilder has _matchup_engine = None."""
        builder = GameContextBuilder()
        assert builder._matchup_engine is None

    def test_builder_enabled_but_pff_unavailable_has_no_engine(self):
        """When PFF is enabled but data is unavailable, engine stays None."""
        cfg = PffConfig(
            enabled=True,
            data_dir="/nonexistent/path/that/does/not/exist",
            matchup=MatchupConfig(enabled=True),
        )
        builder = GameContextBuilder(pff_config=cfg)
        # PffLoader.is_available() returns False → engine stays None
        assert builder._matchup_engine is None

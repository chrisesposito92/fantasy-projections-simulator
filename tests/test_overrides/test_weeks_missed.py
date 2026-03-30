"""Tests for per-week zero-out via weeks_missed on PlayerModel."""

import numpy as np
import pytest
from fantasy_sim.models.player import (
    PlayerModel, PlayerUsage, PlayerOutcomes, TeamRoster,
)
from fantasy_sim.engine.types import GameState
from fantasy_sim.engine.player_selector import (
    _filter_available, select_passer, select_receiver, select_rusher,
)
from fantasy_sim.overrides.engine import apply_player_override


def make_roster() -> TeamRoster:
    """Build a small roster with a QB, two WRs, and an RB."""
    return TeamRoster(team="TST", players=[
        PlayerModel("QB1", "TestQB", "QB", "TST",
                    PlayerUsage(snap_share=1.0), PlayerOutcomes()),
        PlayerModel("WR1", "TestWR1", "WR", "TST",
                    PlayerUsage(target_share=0.30), PlayerOutcomes(catch_rate=0.65)),
        PlayerModel("WR2", "TestWR2", "WR", "TST",
                    PlayerUsage(target_share=0.20), PlayerOutcomes(catch_rate=0.60)),
        PlayerModel("RB1", "TestRB1", "RB", "TST",
                    PlayerUsage(carry_share=0.70), PlayerOutcomes()),
    ])


def make_state(week: int = 0) -> GameState:
    """Build a minimal GameState with a specific week."""
    return GameState(
        quarter=1, clock=900, possession="home",
        down=1, distance=10, yard_line=75,
        home_score=0, away_score=0,
        home_team="TST", away_team="OPP",
        receiving_2nd_half="away",
        week=week,
    )


class TestWeeksMissedField:
    """Verify the weeks_missed field on PlayerModel."""

    def test_weeks_missed_defaults_empty(self):
        player = PlayerModel(
            "p1", "Test", "WR", "TST",
            PlayerUsage(), PlayerOutcomes(),
        )
        assert hasattr(player, "weeks_missed")
        assert player.weeks_missed == []

    def test_games_missed_override_sets_weeks_missed_and_games_played(self):
        roster = make_roster()
        apply_player_override(roster, "WR1", {"games_missed": [3, 7, 12]})
        wr1 = next(p for p in roster.players if p.player_id == "WR1")
        assert wr1.weeks_missed == [3, 7, 12]
        assert wr1.games_played == 14  # 17 - 3

    def test_games_missed_override_empty_list(self):
        roster = make_roster()
        apply_player_override(roster, "WR1", {"games_missed": []})
        wr1 = next(p for p in roster.players if p.player_id == "WR1")
        assert wr1.weeks_missed == []
        assert wr1.games_played == 17


class TestGameStateHasWeek:
    """Verify the week field on GameState."""

    def test_week_defaults_to_zero(self):
        state = GameState(
            quarter=1, clock=900, possession="home",
            down=1, distance=10, yard_line=75,
            home_score=0, away_score=0,
            home_team="A", away_team="B",
            receiving_2nd_half="away",
        )
        assert state.week == 0

    def test_week_can_be_set(self):
        state = make_state(week=5)
        assert state.week == 5


class TestPlayerSelectorSkipsMissedWeeks:
    """Test that player_selector filters out players missing the current week."""

    def test_receiver_skipped_during_missed_week(self):
        """WR1 with weeks_missed=[5] should never be selected in week 5."""
        roster = make_roster()
        wr1 = next(p for p in roster.players if p.player_id == "WR1")
        wr1.weeks_missed = [5]
        state = make_state(week=5)
        rng = np.random.default_rng(42)

        selected_ids = set()
        for _ in range(100):
            receiver = select_receiver(roster, state, rng)
            selected_ids.add(receiver.player_id)

        assert "WR1" not in selected_ids

    def test_receiver_available_during_non_missed_week(self):
        """WR1 with weeks_missed=[5] should be available in week 6."""
        roster = make_roster()
        wr1 = next(p for p in roster.players if p.player_id == "WR1")
        wr1.weeks_missed = [5]
        state = make_state(week=6)
        rng = np.random.default_rng(42)

        selected_ids = set()
        for _ in range(100):
            receiver = select_receiver(roster, state, rng)
            selected_ids.add(receiver.player_id)

        assert "WR1" in selected_ids

    def test_rusher_skipped_during_missed_week(self):
        """RB1 with weeks_missed=[3] should never be selected as rusher in week 3."""
        roster = make_roster()
        rb1 = next(p for p in roster.players if p.player_id == "RB1")
        rb1.weeks_missed = [3]
        state = make_state(week=3)
        rng = np.random.default_rng(42)

        # Need a second rusher to avoid ValueError
        roster.players.append(
            PlayerModel("RB2", "TestRB2", "RB", "TST",
                        PlayerUsage(carry_share=0.30), PlayerOutcomes())
        )

        selected_ids = set()
        for _ in range(100):
            rusher = select_rusher(roster, state, rng)
            selected_ids.add(rusher.player_id)

        assert "RB1" not in selected_ids

    def test_week_zero_means_no_filtering(self):
        """When week=0, all players should be available regardless of weeks_missed."""
        roster = make_roster()
        wr1 = next(p for p in roster.players if p.player_id == "WR1")
        wr1.weeks_missed = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        state = make_state(week=0)
        rng = np.random.default_rng(42)

        selected_ids = set()
        for _ in range(100):
            receiver = select_receiver(roster, state, rng)
            selected_ids.add(receiver.player_id)

        assert "WR1" in selected_ids

    def test_filter_available_returns_original_if_no_filtering(self):
        """If no players are filtered, should return the original roster object."""
        roster = make_roster()
        state = make_state(week=5)
        result = _filter_available(roster, state)
        assert result is roster

    def test_filter_available_returns_original_if_week_zero(self):
        """If week is 0, should return the original roster object."""
        roster = make_roster()
        state = make_state(week=0)
        result = _filter_available(roster, state)
        assert result is roster

    def test_filter_available_never_returns_empty(self):
        """If all players would be filtered, return original roster (safety)."""
        roster = make_roster()
        for p in roster.players:
            p.weeks_missed = [5]
        state = make_state(week=5)
        result = _filter_available(roster, state)
        assert result is roster
        assert len(result.players) > 0

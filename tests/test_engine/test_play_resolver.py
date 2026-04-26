import numpy as np
import pytest
from fantasy_sim.engine.play_resolver import resolve_play
from fantasy_sim.engine.types import GameState, PlayResult
from fantasy_sim.models.distributions import PlayOutcomeDist, TurnoverRates


def make_state(**overrides) -> GameState:
    defaults = dict(
        quarter=1, clock=900, possession="home",
        down=1, distance=10, yard_line=75,
        home_score=0, away_score=0,
        home_team="KC", away_team="BUF",
        receiving_2nd_half="away",
    )
    defaults.update(overrides)
    return GameState(**defaults)


def make_outcomes(pass_yards=None, run_yards=None) -> PlayOutcomeDist:
    defaults = {}
    if pass_yards is not None:
        defaults["pass"] = np.array(pass_yards)
    else:
        defaults["pass"] = np.array([5, 8, 10, 12, 0, 15, -2, 20, 7, 3])
    if run_yards is not None:
        defaults["run"] = np.array(run_yards)
    else:
        defaults["run"] = np.array([3, 4, 5, -1, 2, 7, 1, 6, 0, 8])
    return PlayOutcomeDist(distributions={}, defaults=defaults)


def make_turnover_rates(**overrides) -> TurnoverRates:
    defaults = dict(team="KC", int_rate=0.0, fumble_rate=0.0, sack_rate=0.0, sack_fumble_rate=0.0)
    defaults.update(overrides)
    return TurnoverRates(**defaults)


class TestResolvePass:
    def test_normal_completion(self):
        rng = np.random.default_rng(42)
        state = make_state()
        outcomes = make_outcomes(pass_yards=[10])  # Always 10 yards
        rates = make_turnover_rates()  # No turnovers
        result = resolve_play(state, "pass", outcomes, rates, rng)
        assert result.play_type == "pass"
        assert result.yards == 10
        assert result.is_complete
        assert not result.is_sack

    def test_incomplete_pass(self):
        rng = np.random.default_rng(42)
        state = make_state()
        outcomes = make_outcomes(pass_yards=[0])  # Always 0 yards = incomplete
        rates = make_turnover_rates()
        result = resolve_play(state, "pass", outcomes, rates, rng)
        assert result.yards == 0
        assert not result.is_complete

    def test_sack(self):
        rng = np.random.default_rng(42)
        state = make_state()
        outcomes = make_outcomes()
        rates = make_turnover_rates(sack_rate=1.0)  # Always sacked
        result = resolve_play(state, "pass", outcomes, rates, rng)
        assert result.is_sack
        assert result.yards < 0

    def test_interception(self):
        rng = np.random.default_rng(42)
        state = make_state()
        outcomes = make_outcomes()
        rates = make_turnover_rates(int_rate=1.0)  # Always INT
        result = resolve_play(state, "pass", outcomes, rates, rng)
        assert result.is_interception
        assert result.yards == 0

    def test_sack_checked_before_int(self):
        """If sack_rate=1.0 and int_rate=1.0, sack should take priority."""
        rng = np.random.default_rng(42)
        state = make_state()
        outcomes = make_outcomes()
        rates = make_turnover_rates(sack_rate=1.0, int_rate=1.0)
        result = resolve_play(state, "pass", outcomes, rates, rng)
        assert result.is_sack
        assert not result.is_interception

    def test_pass_touchdown(self):
        rng = np.random.default_rng(42)
        state = make_state(yard_line=5)  # 5 yards from end zone
        outcomes = make_outcomes(pass_yards=[10])  # Gain 10 = TD
        rates = make_turnover_rates()
        result = resolve_play(state, "pass", outcomes, rates, rng)
        assert result.is_touchdown
        assert result.yards == 5  # Clamped to end zone

    def test_safety_on_sack(self):
        rng = np.random.default_rng(42)
        state = make_state(yard_line=97)  # Own 3-yard line
        outcomes = make_outcomes()
        rates = make_turnover_rates(sack_rate=1.0)
        result = resolve_play(state, "pass", outcomes, rates, rng)
        assert result.is_sack
        assert result.is_safety


class TestResolveRun:
    def test_normal_run(self):
        rng = np.random.default_rng(42)
        state = make_state()
        outcomes = make_outcomes(run_yards=[5])
        rates = make_turnover_rates()
        result = resolve_play(state, "run", outcomes, rates, rng)
        assert result.play_type == "run"
        assert result.yards == 5
        assert not result.is_fumble

    def test_run_fumble(self):
        rng = np.random.default_rng(42)
        state = make_state()
        outcomes = make_outcomes(run_yards=[5])
        rates = make_turnover_rates(fumble_rate=1.0)
        result = resolve_play(state, "run", outcomes, rates, rng)
        assert result.is_fumble

    def test_run_touchdown(self):
        rng = np.random.default_rng(42)
        state = make_state(yard_line=3)
        outcomes = make_outcomes(run_yards=[5])
        rates = make_turnover_rates()
        result = resolve_play(state, "run", outcomes, rates, rng)
        assert result.is_touchdown
        assert result.yards == 3  # Clamped to end zone

    def test_fumble_cancels_td(self):
        rng = np.random.default_rng(42)
        state = make_state(yard_line=3)
        outcomes = make_outcomes(run_yards=[5])
        rates = make_turnover_rates(fumble_rate=1.0)
        result = resolve_play(state, "run", outcomes, rates, rng)
        assert result.is_fumble
        assert not result.is_touchdown

    def test_run_safety(self):
        rng = np.random.default_rng(42)
        state = make_state(yard_line=98)  # Own 2
        outcomes = make_outcomes(run_yards=[-5])
        rates = make_turnover_rates()
        result = resolve_play(state, "run", outcomes, rates, rng)
        assert result.is_safety

    def test_clock_runoff_pass_complete(self):
        rng = np.random.default_rng(42)
        state = make_state()
        outcomes = make_outcomes(pass_yards=[10])
        rates = make_turnover_rates()
        result = resolve_play(state, "pass", outcomes, rates, rng)
        assert result.clock_runoff > 0

    def test_clock_runoff_run(self):
        rng = np.random.default_rng(42)
        state = make_state()
        outcomes = make_outcomes(run_yards=[5])
        rates = make_turnover_rates()
        result = resolve_play(state, "run", outcomes, rates, rng)
        assert result.clock_runoff > 0


class FixedQbDesignedRunYardsContext:
    def rusher_weights(self, players, legacy_weights, state, script=None):
        adjusted = legacy_weights.copy()
        for idx, player in enumerate(players):
            if player.position == "QB":
                adjusted[idx] = 100.0
        return adjusted

    def designed_run_yards(self, state, rusher, rng, script=None):
        if rusher.position == "QB":
            return 15
        return None


class NonQbDesignedRunYardsContext:
    def rusher_weights(self, players, legacy_weights, state, script=None):
        return legacy_weights

    def designed_run_yards(self, state, rusher, rng, script=None):
        raise AssertionError("designed_run_yards should only be called for QB rushers")


def test_qb_designed_run_context_supplies_yards_for_selected_qb_run():
    qb = PlayerModel(
        "QB1",
        "QB",
        "QB",
        "T",
        PlayerUsage(snap_share=1.0, carry_share=0.12),
        PlayerOutcomes(rushing_yards_dist=np.array([2])),
    )
    rb = PlayerModel(
        "RB1",
        "RB",
        "RB",
        "T",
        PlayerUsage(carry_share=0.80),
        PlayerOutcomes(rushing_yards_dist=np.array([4])),
    )
    result = resolve_play(
        make_state(yard_line=50),
        "run",
        make_outcomes(run_yards=[1]),
        make_turnover_rates(),
        np.random.default_rng(1),
        roster=TeamRoster(team="T", players=[qb, rb]),
        qb_designed_run_context=FixedQbDesignedRunYardsContext(),
    )

    assert result.rusher_id == "QB1"
    assert result.yards == 15


def test_qb_designed_run_context_does_not_supply_yards_for_non_qb_rusher():
    rb = PlayerModel(
        "RB1",
        "RB",
        "RB",
        "T",
        PlayerUsage(carry_share=1.0),
        PlayerOutcomes(rushing_yards_dist=np.array([4])),
    )
    result = resolve_play(
        make_state(yard_line=50),
        "run",
        make_outcomes(run_yards=[1]),
        make_turnover_rates(),
        np.random.default_rng(1),
        roster=TeamRoster(team="T", players=[rb]),
        qb_designed_run_context=NonQbDesignedRunYardsContext(),
    )

    assert result.rusher_id == "RB1"
    assert result.yards == 4


def test_qb_designed_run_context_does_not_affect_scramble_yards():
    qb = PlayerModel(
        "QB1",
        "QB",
        "QB",
        "T",
        PlayerUsage(snap_share=1.0, scramble_rate=1.0, carry_share=0.12),
        PlayerOutcomes(scramble_yards_dist=np.array([6]), rushing_yards_dist=np.array([2])),
    )
    wr = PlayerModel("WR1", "WR", "WR", "T", PlayerUsage(target_share=1.0), PlayerOutcomes(catch_rate=1.0))
    result = resolve_play(
        make_state(yard_line=50),
        "pass",
        make_outcomes(run_yards=[1]),
        make_turnover_rates(),
        np.random.default_rng(1),
        roster=TeamRoster(team="T", players=[qb, wr]),
        qb_designed_run_context=FixedQbDesignedRunYardsContext(),
    )

    assert result.rusher_id == "QB1"
    assert result.yards == 6


from fantasy_sim.models.player import PlayerModel, PlayerUsage, PlayerOutcomes, TeamRoster


def make_roster_for_resolver() -> TeamRoster:
    qb = PlayerModel("QB1", "QB", "QB", "T",
                     PlayerUsage(snap_share=1.0, scramble_rate=0.0),
                     PlayerOutcomes())
    wr1 = PlayerModel("WR1", "WR1", "WR", "T",
                      PlayerUsage(target_share=0.50),
                      PlayerOutcomes(
                          catch_rate=0.65,
                          receiving_yards_dist=np.array([8, 10, 12, 15, 20]),
                          fumble_rate=0.0,
                      ))
    rb1 = PlayerModel("RB1", "RB1", "RB", "T",
                      PlayerUsage(carry_share=1.0, target_share=0.50),
                      PlayerOutcomes(
                          rushing_yards_dist=np.array([3, 5, 7, 4, 6]),
                          catch_rate=0.80,
                          receiving_yards_dist=np.array([4, 6, 8]),
                          fumble_rate=0.0,
                      ))
    return TeamRoster(team="T", players=[qb, wr1, rb1])


class TestResolvePassWithPlayers:
    def test_pass_has_passer_and_receiver(self):
        rng = np.random.default_rng(42)
        state = make_state()
        outcomes = make_outcomes(pass_yards=[10])
        rates = make_turnover_rates()
        roster = make_roster_for_resolver()
        result = resolve_play(state, "pass", outcomes, rates, rng, roster=roster)
        assert result.passer_id == "QB1"
        assert result.receiver_id is not None
        assert result.receiver_id in ("WR1", "RB1")

    def test_pass_uses_player_catch_rate(self):
        rng = np.random.default_rng(42)
        completions = 0
        n = 200
        for _ in range(n):
            state = make_state()
            outcomes = make_outcomes(pass_yards=[10])
            rates = make_turnover_rates()
            roster = make_roster_for_resolver()
            result = resolve_play(state, "pass", outcomes, rates, rng, roster=roster)
            if result.is_complete:
                completions += 1
        rate = completions / n
        assert 0.50 <= rate <= 0.85


class TestResolvePassScramble:
    def _make_scramble_roster(self) -> TeamRoster:
        qb = PlayerModel("QB1", "QB", "QB", "T",
                         PlayerUsage(snap_share=1.0, scramble_rate=1.0),
                         PlayerOutcomes(scramble_yards_dist=np.array([5, 8, 12]),
                                        fumble_rate=0.0))
        wr1 = PlayerModel("WR1", "WR1", "WR", "T",
                          PlayerUsage(target_share=1.0),
                          PlayerOutcomes(catch_rate=0.65,
                                         receiving_yards_dist=np.array([10])))
        rb1 = PlayerModel("RB1", "RB1", "RB", "T",
                          PlayerUsage(carry_share=1.0),
                          PlayerOutcomes(rushing_yards_dist=np.array([4])))
        return TeamRoster(team="T", players=[qb, wr1, rb1])

    def test_scramble_returns_run_play_type(self):
        rng = np.random.default_rng(42)
        roster = self._make_scramble_roster()
        result = resolve_play(make_state(), "pass", make_outcomes(), make_turnover_rates(), rng, roster=roster)
        assert result.play_type == "run"

    def test_scramble_has_rusher_id_as_qb(self):
        rng = np.random.default_rng(42)
        roster = self._make_scramble_roster()
        result = resolve_play(make_state(), "pass", make_outcomes(), make_turnover_rates(), rng, roster=roster)
        assert result.rusher_id == "QB1"

    def test_scramble_uses_scramble_yards_dist(self):
        rng = np.random.default_rng(42)
        roster = self._make_scramble_roster()
        result = resolve_play(make_state(), "pass", make_outcomes(), make_turnover_rates(), rng, roster=roster)
        assert result.yards in [5, 8, 12]


class FixedQbScrambleContext:
    def __init__(self, probability):
        self.probability = probability

    def scramble_probability(self, state, passer):
        return self.probability


class TestResolvePassQbScrambleContext:
    def _make_context_roster(self, scramble_rate=0.0) -> TeamRoster:
        qb = PlayerModel(
            "QB1",
            "QB",
            "QB",
            "T",
            PlayerUsage(snap_share=1.0, scramble_rate=scramble_rate),
            PlayerOutcomes(scramble_yards_dist=np.array([6]), fumble_rate=0.0),
        )
        wr = PlayerModel(
            "WR1",
            "WR",
            "WR",
            "T",
            PlayerUsage(target_share=1.0),
            PlayerOutcomes(catch_rate=1.0, receiving_yards_dist=np.array([10])),
        )
        rb = PlayerModel(
            "RB1",
            "RB",
            "RB",
            "T",
            PlayerUsage(carry_share=1.0),
            PlayerOutcomes(rushing_yards_dist=np.array([4])),
        )
        return TeamRoster(team="T", players=[qb, wr, rb])

    def test_qb_scramble_context_can_force_scramble_probability(self):
        result = resolve_play(
            make_state(),
            "pass",
            make_outcomes(),
            make_turnover_rates(sack_rate=1.0, int_rate=1.0),
            np.random.default_rng(42),
            roster=self._make_context_roster(scramble_rate=0.0),
            qb_scramble_context=FixedQbScrambleContext(1.0),
        )

        assert result.play_type == "run"
        assert result.rusher_id == "QB1"
        assert result.yards == 6
        assert not result.is_sack
        assert not result.is_interception

    def test_qb_scramble_context_none_falls_back_to_base_rate(self):
        result = resolve_play(
            make_state(),
            "pass",
            make_outcomes(),
            make_turnover_rates(),
            np.random.default_rng(42),
            roster=self._make_context_roster(scramble_rate=1.0),
            qb_scramble_context=FixedQbScrambleContext(None),
        )

        assert result.play_type == "run"
        assert result.rusher_id == "QB1"


class TestResolveRunWithPlayers:
    def test_run_has_rusher(self):
        rng = np.random.default_rng(42)
        state = make_state()
        outcomes = make_outcomes(run_yards=[5])
        rates = make_turnover_rates()
        roster = make_roster_for_resolver()
        result = resolve_play(state, "run", outcomes, rates, rng, roster=roster)
        assert result.rusher_id == "RB1"

    def test_run_uses_player_yards_dist(self):
        rng = np.random.default_rng(42)
        state = make_state()
        outcomes = make_outcomes(run_yards=[100])  # Team dist says 100, but player dist overrides
        rates = make_turnover_rates()
        roster = make_roster_for_resolver()
        result = resolve_play(state, "run", outcomes, rates, rng, roster=roster)
        assert result.yards in [3, 4, 5, 6, 7]


from fantasy_sim.models.distributions import PenaltyRates


def make_penalty_rates(**overrides) -> PenaltyRates:
    defaults = dict(
        team="KC",
        penalty_rate=0.0,
        type_distribution={"false_start": 0.30, "holding": 0.40, "pass_interference": 0.15, "other": 0.15},
        avg_yards={"false_start": 5.0, "holding": 10.0, "pass_interference": 15.0, "other": 5.0},
    )
    defaults.update(overrides)
    return PenaltyRates(**defaults)


class TestPenaltyCheck:
    def test_no_penalty_when_rate_zero(self):
        from fantasy_sim.engine.play_resolver import check_penalty
        rng = np.random.default_rng(42)
        rates = make_penalty_rates(penalty_rate=0.0)
        result = check_penalty(rates, rng)
        assert result is None

    def test_always_penalty_when_rate_one(self):
        from fantasy_sim.engine.play_resolver import check_penalty
        rng = np.random.default_rng(42)
        rates = make_penalty_rates(penalty_rate=1.0)
        result = check_penalty(rates, rng)
        assert result is not None
        penalty_type, yards = result
        assert penalty_type in ("false_start", "holding", "pass_interference", "other")
        assert yards > 0

    def test_false_start_returns_5_yards(self):
        from fantasy_sim.engine.play_resolver import check_penalty
        rng = np.random.default_rng(42)
        rates = make_penalty_rates(
            penalty_rate=1.0,
            type_distribution={"false_start": 1.0, "holding": 0.0, "pass_interference": 0.0, "other": 0.0},
        )
        result = check_penalty(rates, rng)
        assert result is not None
        penalty_type, yards = result
        assert penalty_type == "false_start"
        assert yards == 5

    def test_holding_returns_10_yards(self):
        from fantasy_sim.engine.play_resolver import check_penalty
        rng = np.random.default_rng(42)
        rates = make_penalty_rates(
            penalty_rate=1.0,
            type_distribution={"false_start": 0.0, "holding": 1.0, "pass_interference": 0.0, "other": 0.0},
        )
        result = check_penalty(rates, rng)
        assert result is not None
        penalty_type, yards = result
        assert penalty_type == "holding"
        assert yards == 10

    def test_penalty_result_has_is_penalty_flag(self):
        from fantasy_sim.engine.play_resolver import apply_penalty
        state = make_state(down=2, distance=10, yard_line=50)
        result = apply_penalty(state, "false_start", 5)
        assert result.is_penalty is True
        assert result.yards == -5
        assert result.clock_runoff == 0


class TestHomeFieldAdvantage:
    def test_home_field_adds_yards(self):
        """Over many samples, home team should average slightly more yards."""
        rng = np.random.default_rng(42)
        outcomes = make_outcomes(run_yards=[4, 4, 4, 4, 4])
        rates = make_turnover_rates()
        n = 500

        home_yards = []
        away_yards = []
        for _ in range(n):
            state = make_state(possession="home")
            result = resolve_play(state, "run", outcomes, rates, rng, is_home=True)
            if not result.is_fumble and not result.is_safety:
                home_yards.append(result.yards)

            state = make_state(possession="away")
            result = resolve_play(state, "run", outcomes, rates, rng, is_home=False)
            if not result.is_fumble and not result.is_safety:
                away_yards.append(result.yards)

        avg_home = sum(home_yards) / len(home_yards)
        avg_away = sum(away_yards) / len(away_yards)
        assert avg_home > avg_away

    def test_is_home_false_no_bonus(self):
        """With is_home=False, no yards bonus is applied."""
        rng = np.random.default_rng(42)
        outcomes = make_outcomes(run_yards=[5])
        rates = make_turnover_rates()
        state = make_state()
        result = resolve_play(state, "run", outcomes, rates, rng, is_home=False)
        assert result.yards == 5


def make_rz_roster() -> TeamRoster:
    """Roster for red zone tests with known catch rates and yards dists."""
    qb = PlayerModel("QB1", "QB", "QB", "T",
                     PlayerUsage(snap_share=1.0, scramble_rate=0.0),
                     PlayerOutcomes())
    wr1 = PlayerModel("WR1", "WR1", "WR", "T",
                      PlayerUsage(target_share=1.0),
                      PlayerOutcomes(
                          catch_rate=1.0,  # Always catches (outside RZ)
                          red_zone_catch_rate=0.50,  # 50% in RZ
                          receiving_yards_dist=np.array([15, 15, 15, 15, 15]),  # Always 15 yards
                          fumble_rate=0.0,
                      ))
    return TeamRoster(team="T", players=[qb, wr1])


class TestRedZonePassResolution:
    def test_rz_catch_rate_used_inside_20(self):
        """In the red zone, use red_zone_catch_rate (0.50) instead of catch_rate (1.0)."""
        rng = np.random.default_rng(42)
        roster = make_rz_roster()
        outcomes = make_outcomes(pass_yards=[10])
        rates = make_turnover_rates()
        completions = 0
        n = 500
        for _ in range(n):
            state = make_state(yard_line=10)  # Red zone
            result = resolve_play(state, "pass", outcomes, rates, rng, roster=roster)
            if result.is_complete:
                completions += 1
        rate = completions / n
        # Should be ~0.50 (RZ catch rate), not 1.0 (overall)
        assert 0.35 <= rate <= 0.65

    def test_normal_catch_rate_outside_20(self):
        """Outside the red zone, use normal catch_rate (1.0)."""
        rng = np.random.default_rng(42)
        roster = make_rz_roster()
        outcomes = make_outcomes(pass_yards=[10])
        rates = make_turnover_rates()
        completions = 0
        n = 200
        for _ in range(n):
            state = make_state(yard_line=50)
            result = resolve_play(state, "pass", outcomes, rates, rng, roster=roster)
            if result.is_complete:
                completions += 1
        rate = completions / n
        assert rate > 0.90  # Should be ~1.0

    def test_rz_td_gate_reduces_tds(self):
        """From the 10-yard line with 15-yard catches, not all completions should be TDs."""
        rng = np.random.default_rng(42)
        roster = make_rz_roster()
        outcomes = make_outcomes(pass_yards=[15])
        rates = make_turnover_rates()
        tds = 0
        completions = 0
        n = 1000
        for _ in range(n):
            state = make_state(yard_line=10)
            result = resolve_play(state, "pass", outcomes, rates, rng, roster=roster)
            if result.is_complete:
                completions += 1
                if result.is_touchdown:
                    tds += 1
        # TD gate at 6-10 is 0.45, so ~45% of completions should be TDs
        if completions > 0:
            td_rate = tds / completions
            assert 0.30 <= td_rate <= 0.60

    def test_failed_td_gate_gives_short_yardage(self):
        """When TD gate fails, receiver should be tackled short (yards < yard_line)."""
        rng = np.random.default_rng(42)
        roster = make_rz_roster()
        outcomes = make_outcomes(pass_yards=[15])
        rates = make_turnover_rates()
        short_catches = []
        for _ in range(2000):
            state = make_state(yard_line=15)
            result = resolve_play(state, "pass", outcomes, rates, rng, roster=roster)
            if result.is_complete and not result.is_touchdown:
                short_catches.append(result.yards)
        assert len(short_catches) > 0  # Some catches should NOT be TDs
        for y in short_catches:
            assert 1 <= y < 15  # Tackled short of goal line

    def test_rz_non_td_catch_preserves_player_yards(self):
        """In the red zone, non-TD completions use player distribution (clamped by _clamp_yards)."""
        rng = np.random.default_rng(42)
        qb = PlayerModel("QB1", "QB", "QB", "T",
                         PlayerUsage(snap_share=1.0), PlayerOutcomes())
        wr = PlayerModel("WR1", "WR1", "WR", "T",
                         PlayerUsage(target_share=1.0),
                         PlayerOutcomes(
                             catch_rate=1.0,
                             red_zone_catch_rate=1.0,
                             receiving_yards_dist=np.array([12, 12, 12]),  # Always 12 yards
                             fumble_rate=0.0,
                         ))
        roster = TeamRoster(team="T", players=[qb, wr])
        # Team dist includes zeros (like real data) — should NOT cap player yards
        outcomes = make_outcomes(pass_yards=[0, 0, 5, 6, 7])
        rates = make_turnover_rates()
        non_td_yards = []
        for _ in range(2000):
            state = make_state(yard_line=18)
            result = resolve_play(state, "pass", outcomes, rates, rng, roster=roster)
            if result.is_complete and not result.is_touchdown:
                non_td_yards.append(result.yards)
        assert len(non_td_yards) > 0
        avg = sum(non_td_yards) / len(non_td_yards)
        # Player dist is 12, should average close to 12 (not capped to ~3 by team dist)
        assert avg >= 10

    def test_no_dist_fallback_gives_positive_yards(self):
        """Receiver with no yards dist should still get reasonable yards on completions."""
        rng = np.random.default_rng(42)
        qb = PlayerModel("QB1", "QB", "QB", "T",
                         PlayerUsage(snap_share=1.0), PlayerOutcomes())
        wr = PlayerModel("WR1", "WR1", "WR", "T",
                         PlayerUsage(target_share=1.0),
                         PlayerOutcomes(
                             catch_rate=1.0,
                             receiving_yards_dist=None,  # No personal distribution
                             fumble_rate=0.0,
                         ))
        roster = TeamRoster(team="T", players=[qb, wr])
        # Team dist with zeros and negatives (like real PBP data)
        outcomes = make_outcomes(pass_yards=[0, 0, -3, 0, 5, 8, 10, 12, 15, 20])
        rates = make_turnover_rates()
        completion_yards = []
        for _ in range(500):
            state = make_state(yard_line=50)
            result = resolve_play(state, "pass", outcomes, rates, rng, roster=roster)
            if result.is_complete:
                completion_yards.append(result.yards)
        assert len(completion_yards) > 0
        # All completions should have positive yards
        for y in completion_yards:
            assert y >= 1
        # Average should be reasonable (not dominated by 1-yard catches)
        avg = sum(completion_yards) / len(completion_yards)
        assert avg >= 3


class TestRedZoneTDGate:
    def test_outside_red_zone_always_true(self):
        from fantasy_sim.engine.play_resolver import _red_zone_td_gate
        rng = np.random.default_rng(42)
        for _ in range(50):
            assert _red_zone_td_gate(25, "pass", rng) is True
            assert _red_zone_td_gate(50, "run", rng) is True

    def test_close_to_goal_high_probability(self):
        from fantasy_sim.engine.play_resolver import _red_zone_td_gate
        rng = np.random.default_rng(42)
        tds = sum(_red_zone_td_gate(2, "pass", rng) for _ in range(1000))
        # 55% gate -> expect ~550, allow ±50
        assert 490 <= tds <= 610

    def test_far_red_zone_low_probability(self):
        from fantasy_sim.engine.play_resolver import _red_zone_td_gate
        rng = np.random.default_rng(42)
        tds = sum(_red_zone_td_gate(18, "pass", rng) for _ in range(1000))
        # 15% gate -> expect ~150, allow ±50
        assert 100 <= tds <= 210

    def test_run_gate_lower_than_pass(self):
        from fantasy_sim.engine.play_resolver import _red_zone_td_gate
        rng = np.random.default_rng(42)
        pass_tds = sum(_red_zone_td_gate(5, "pass", rng) for _ in range(1000))
        rng = np.random.default_rng(42)
        run_tds = sum(_red_zone_td_gate(5, "run", rng) for _ in range(1000))
        assert run_tds < pass_tds


class TestQBPreThrowFumble:
    def _make_fumble_roster(self, pass_fumble_rate: float) -> TeamRoster:
        qb = PlayerModel("QB1", "QB", "QB", "T",
                         PlayerUsage(snap_share=1.0, scramble_rate=0.0),
                         PlayerOutcomes(pass_fumble_rate=pass_fumble_rate))
        wr = PlayerModel("WR1", "WR1", "WR", "T",
                         PlayerUsage(target_share=1.0),
                         PlayerOutcomes(catch_rate=1.0,
                                        red_zone_catch_rate=1.0,
                                        receiving_yards_dist=np.array([10]),
                                        fumble_rate=0.0))
        return TeamRoster(team="T", players=[qb, wr])

    def test_pre_throw_fumble_fires(self):
        """With pass_fumble_rate=1.0, every pass play should be a fumble."""
        rng = np.random.default_rng(42)
        roster = self._make_fumble_roster(pass_fumble_rate=1.0)
        outcomes = make_outcomes(pass_yards=[10])
        rates = make_turnover_rates()
        result = resolve_play(make_state(), "pass", outcomes, rates, rng, roster=roster)
        assert result.is_fumble
        assert result.yards == 0
        assert not result.is_touchdown
        assert not result.is_complete

    def test_pre_throw_fumble_before_completion(self):
        """Pre-throw fumble should prevent any completion."""
        rng = np.random.default_rng(42)
        roster = self._make_fumble_roster(pass_fumble_rate=1.0)
        outcomes = make_outcomes(pass_yards=[10])
        rates = make_turnover_rates()
        result = resolve_play(make_state(), "pass", outcomes, rates, rng, roster=roster)
        assert not result.is_complete
        assert result.passer_id == "QB1"
        assert result.receiver_id is None  # Never got to select a receiver

    def test_no_fumble_when_rate_zero(self):
        """With pass_fumble_rate=0.0, no pre-throw fumbles."""
        rng = np.random.default_rng(42)
        roster = self._make_fumble_roster(pass_fumble_rate=0.0)
        outcomes = make_outcomes(pass_yards=[10])
        rates = make_turnover_rates()
        fumbles = 0
        for _ in range(200):
            result = resolve_play(make_state(), "pass", outcomes, rates, rng, roster=roster)
            if result.is_fumble and result.yards == 0:
                fumbles += 1
        assert fumbles == 0

    def test_fumble_checked_after_sack_and_int(self):
        """Sack takes priority over pre-throw fumble."""
        rng = np.random.default_rng(42)
        roster = self._make_fumble_roster(pass_fumble_rate=1.0)
        outcomes = make_outcomes(pass_yards=[10])
        rates = make_turnover_rates(sack_rate=1.0)
        result = resolve_play(make_state(), "pass", outcomes, rates, rng, roster=roster)
        assert result.is_sack  # Sack takes priority


class TestRedZoneRunResolution:
    def test_rz_run_td_gate_reduces_tds(self):
        """From the 3-yard line, not all 5-yard runs should be TDs."""
        rng = np.random.default_rng(42)
        rb = PlayerModel("RB1", "RB1", "RB", "T",
                         PlayerUsage(carry_share=1.0),
                         PlayerOutcomes(rushing_yards_dist=np.array([5, 5, 5, 5, 5]),
                                        fumble_rate=0.0))
        roster = TeamRoster(team="T", players=[rb])
        outcomes = make_outcomes(run_yards=[5])
        rates = make_turnover_rates()
        tds = 0
        n = 1000
        for _ in range(n):
            state = make_state(yard_line=3)
            result = resolve_play(state, "run", outcomes, rates, rng, roster=roster)
            if result.is_touchdown:
                tds += 1
        td_rate = tds / n
        # RUN_TD_GATE at 1-3 is 0.35, so ~35% should be TDs
        assert 0.20 <= td_rate <= 0.50

    def test_rz_non_td_run_preserves_player_yards(self):
        """In the red zone, non-TD runs use player distribution (clamped by _clamp_yards)."""
        rng = np.random.default_rng(42)
        rb = PlayerModel("RB1", "RB1", "RB", "T",
                         PlayerUsage(carry_share=1.0),
                         PlayerOutcomes(rushing_yards_dist=np.array([10, 10, 10]),
                                        fumble_rate=0.0))
        roster = TeamRoster(team="T", players=[rb])
        # Team dist includes zeros — should NOT cap player yards
        outcomes = make_outcomes(run_yards=[0, 0, 4, 5, 6])
        rates = make_turnover_rates()
        non_td_yards = []
        for _ in range(2000):
            state = make_state(yard_line=18)
            result = resolve_play(state, "run", outcomes, rates, rng, roster=roster)
            if not result.is_touchdown and not result.is_fumble and not result.is_safety:
                non_td_yards.append(result.yards)
        assert len(non_td_yards) > 0
        avg = sum(non_td_yards) / len(non_td_yards)
        # Player dist is 10, should average close to 10 (not capped by team dist)
        assert avg >= 8


# === KS-01: RZ TD-gate distribution preservation ===
#
# Per Plan 01 Task 1 (RED phase). These tests cover the new
# `_tackled_short_preserve_distribution` helper introduced by Task 2 (GREEN)
# to replace the punitive `_tackled_short()` rewrite that fires when the red
# zone TD gate denies a touchdown. Per D-09: yards = max(1, min(yard_line - 1,
# sampled_yards_pre_clamp)) — preserves the sampled distribution and reserves
# 1 yard short of the goal so the play does not score.
#
# The helper is callable directly regardless of the
# `phase1_ks_flags.ks01_preserve_distribution.enabled` flag (the flag only
# controls whether the call sites use the helper or the legacy
# `_tackled_short` path). Tests 3 & 4 are calibration regression guards on
# PASS_TD_GATE / RUN_TD_GATE that protect against accidental gate edits.

from fantasy_sim.engine import play_resolver as _pr
from fantasy_sim.engine.play_resolver import (
    PASS_TD_GATE,
    RUN_TD_GATE,
    _red_zone_td_gate,
)


def _ks01_helper():
    """Dynamic accessor for the KS-01 new helper.

    Returns the `_tackled_short_preserve_distribution` callable from
    `play_resolver` if it has been added (Task 2 GREEN), else raises
    AttributeError so the dependent tests FAIL (not skip) in the RED state.
    Calibration regression tests (Tests 3 & 4) do not call this and therefore
    PASS in RED, satisfying the TDD acceptance criteria for Task 1.
    """
    return _pr._tackled_short_preserve_distribution


def test_ks01_tackled_short_variant_preserves_distribution_at_goal_line():
    helper = _ks01_helper()
    # yard_line=3, sample within band → returns the sample (preserves the dist)
    assert helper(yard_line=3, sampled_yards_pre_clamp=1) == 1
    # yard_line=3, sample exceeds the (yard_line - 1) cap → returns yard_line - 1
    assert helper(yard_line=3, sampled_yards_pre_clamp=8) == 2
    assert helper(yard_line=3, sampled_yards_pre_clamp=20) == 2


def test_ks01_tackled_short_variant_clamps_zero_to_one():
    helper = _ks01_helper()
    # sample == 0 (or negative) → floor at 1 per D-09 "1 yard short" semantics
    assert helper(yard_line=3, sampled_yards_pre_clamp=0) == 1
    assert helper(yard_line=3, sampled_yards_pre_clamp=-2) == 1


def test_ks01_pass_td_gate_calibration_unchanged_after_fix():
    """Regression guard: PASS_TD_GATE[(1,3)] = 0.55 must hold over 100k trials."""
    rng = np.random.default_rng(0)
    n = 100_000
    successes = sum(1 for _ in range(n) if _red_zone_td_gate(3, "pass", rng))
    rate = successes / n
    assert 0.54 <= rate <= 0.56, f"PASS_TD_GATE[(1,3)] regressed: rate={rate}"


def test_ks01_run_td_gate_calibration_unchanged_after_fix():
    """Regression guard: RUN_TD_GATE[(1,3)] = 0.35 must hold over 100k trials."""
    rng = np.random.default_rng(0)
    n = 100_000
    successes = sum(1 for _ in range(n) if _red_zone_td_gate(3, "run", rng))
    rate = successes / n
    assert 0.34 <= rate <= 0.36, f"RUN_TD_GATE[(1,3)] regressed: rate={rate}"


def test_ks01_resolve_pass_failed_gate_yields_yards_in_safe_band(monkeypatch):
    """When the RZ pass TD gate fails, yards must land in [1, yard_line-1].

    Forces the gate to always fail by monkeypatching `_red_zone_td_gate` to
    return False. With the KS-01 flag on, the new helper should route yards
    into the safe band [1, 2] for yard_line=3 regardless of the underlying
    receiving_yards_dist.
    """
    from fantasy_sim.engine import play_resolver as pr

    # Force the new code path on for this test (regardless of defaults).
    monkeypatch.setattr(pr, "_KS01_PRESERVE_DIST", True)
    # Force every gate roll to deny the TD.
    monkeypatch.setattr(pr, "_red_zone_td_gate", lambda *args, **kwargs: False)

    rng = np.random.default_rng(7)
    # Mixed-band WR — distribution mixes "short catch" (1 yd) with "long catch"
    # values (8+ yd) so the helper's max(1, min(yard_line - 1, sample)) actually
    # produces a mix of 1s and (yard_line - 1)s across trials, proving it is
    # *sampling* through the band rather than always saturating at the cap.
    wr = PlayerModel(
        "WR1", "WR1", "WR", "T",
        PlayerUsage(target_share=1.0),
        PlayerOutcomes(
            catch_rate=1.0,
            red_zone_catch_rate=1.0,
            receiving_yards_dist=np.array([1, 1, 1, 8, 10, 12, 15, 20]),
            receiving_td_factor=1.0,
        ),
    )
    qb = PlayerModel(
        "QB1", "QB", "QB", "T",
        PlayerUsage(snap_share=1.0, scramble_rate=0.0),
        PlayerOutcomes(),
    )
    roster = TeamRoster(team="T", players=[qb, wr])
    outcomes = make_outcomes(pass_yards=[10])
    rates = make_turnover_rates()

    yards_seen = []
    for _ in range(5000):
        state = make_state(yard_line=3)
        result = resolve_play(state, "pass", outcomes, rates, rng, roster=roster)
        if result.is_complete and not result.is_touchdown and not result.is_fumble:
            yards_seen.append(result.yards)

    yards_arr = np.array(yards_seen)
    assert len(yards_arr) > 0, "Expected at least one non-TD completion in the safe band"
    assert yards_arr.min() >= 1, f"yards.min={yards_arr.min()} below D-09 floor of 1"
    assert yards_arr.max() <= 2, f"yards.max={yards_arr.max()} above yard_line-1=2 cap"
    # Sample mean should sit strictly inside (1.0, 2.0), proving the helper is
    # *sampling* across the safe band rather than always returning the cap.
    mean = yards_arr.mean()
    assert 1.0 < mean < 2.0, f"mean={mean} suggests the helper is not sampling across [1, 2]"


def test_ks01_resolve_run_failed_gate_yields_yards_in_safe_band(monkeypatch):
    """When the RZ run TD gate fails, yards must land in [1, yard_line-1]."""
    from fantasy_sim.engine import play_resolver as pr

    monkeypatch.setattr(pr, "_KS01_PRESERVE_DIST", True)
    monkeypatch.setattr(pr, "_red_zone_td_gate", lambda *args, **kwargs: False)

    rng = np.random.default_rng(11)
    rb = PlayerModel(
        "RB1", "RB1", "RB", "T",
        PlayerUsage(carry_share=1.0),
        PlayerOutcomes(
            rushing_yards_dist=np.array([5, 8, 10, 12, 15]),
            fumble_rate=0.0,
            rushing_td_factor=1.0,
            i5_rushing_td_factor=1.0,
        ),
    )
    roster = TeamRoster(team="T", players=[rb])
    outcomes = make_outcomes(run_yards=[5])
    rates = make_turnover_rates()

    yards_seen = []
    for _ in range(5000):
        state = make_state(yard_line=3)
        result = resolve_play(state, "run", outcomes, rates, rng, roster=roster)
        if not result.is_touchdown and not result.is_fumble and not result.is_safety:
            yards_seen.append(result.yards)

    yards_arr = np.array(yards_seen)
    assert len(yards_arr) > 0, "Expected at least one non-TD non-fumble run in the safe band"
    assert yards_arr.min() >= 1, f"yards.min={yards_arr.min()} below D-09 floor of 1"
    assert yards_arr.max() <= 2, f"yards.max={yards_arr.max()} above yard_line-1=2 cap"


# === KS-04: CATCH_YARDS_BOOST conditional retune ===
#
# Per Plan 02 Task 1 (RED phase). KS-04 retunes `CATCH_YARDS_BOOST` from `+1`
# to `+1.5` (D-12) AND applies it conditionally only when `_clamp_yards` would
# actually fire (D-11). The new behavior is gated behind the
# `phase1_ks_flags.ks04_conditional_catch_boost.enabled` flag (Cycle 3 D-45);
# the implementation reads the flag at module import into
# `_KS04_CONDITIONAL_BOOST` and `_KS04_BOOST_VALUE`. Tests that exercise the
# new code path monkeypatch `_KS04_CONDITIONAL_BOOST = True` regardless of the
# defaults.yaml value so RED→GREEN behavior is deterministic. Test 1 asserts
# the boost-value constant directly (independent of the flag).
#
# Anti-clamp deterministic fixture: state.yard_line=80 with a single-value WR
# distribution sampling 5. Pre-clamp = 5; clamp upper bound = 80; clamp does
# NOT fire. With the new conditional policy, no boost is added regardless of
# the boost magnitude. Expected observed mean ≈ 5 + 0.5 (home-field expected)
# = 5.5 over many trials. The OLD unconditional policy adds the full boost so
# observed mean would be ~6.5 (pre-Task-2) or ~7.0 once the constant becomes
# 1.5 (post-Task-2 if conditional check is missing). Test 2 catches both
# regressions.


def test_ks04_boost_value_is_1_5():
    """D-12: CATCH_YARDS_BOOST must be 1.5 (low end of 1.5-2.0 range)."""
    from fantasy_sim.engine.play_resolver import CATCH_YARDS_BOOST
    assert CATCH_YARDS_BOOST == 1.5, (
        f"D-12 requires +1.5 boost, got {CATCH_YARDS_BOOST}"
    )


def _make_ks04_wr_roster(receiving_yards_dist, catch_rate=1.0, red_zone_catch_rate=1.0):
    """Single-WR roster for deterministic catch-yards testing.

    Forces 100% catch + neutral RZ catch rate so every pass play in the test
    completes and lands in the player-yards branch. `receiving_td_factor=1.0`
    keeps the RZ TD gate at its default rate so yards-band assertions stay
    decoupled from gate noise.
    """
    qb = PlayerModel(
        "QB1", "QB", "QB", "T",
        PlayerUsage(snap_share=1.0, scramble_rate=0.0),
        PlayerOutcomes(),
    )
    wr = PlayerModel(
        "WR1", "WR1", "WR", "T",
        PlayerUsage(target_share=1.0),
        PlayerOutcomes(
            catch_rate=catch_rate,
            red_zone_catch_rate=red_zone_catch_rate,
            receiving_yards_dist=np.array(receiving_yards_dist),
            fumble_rate=0.0,
            receiving_td_factor=1.0,
        ),
    )
    return TeamRoster(team="T", players=[qb, wr])


def test_ks04_boost_zero_when_no_clamp(monkeypatch):
    """D-11: no clamp fires (raw <= yard_line) → no boost added.

    With dist=[5] and yard_line=80, every raw sample is 5 (well below the 80
    upper-bound clamp). The new conditional policy adds NO boost. Expected
    observed mean is ~5.5 (5 + 0.5 home-field expected over many trials).
    The pre-Task-2 unconditional `+1` policy yields mean ~6.5; the post-Task-2
    `+1.5` if conditional check is missing yields mean ~7.0. The strict upper
    bound of 6.2 catches both regressions while leaving room for home-field
    sampling noise.
    """
    from fantasy_sim.engine import play_resolver as pr
    monkeypatch.setattr(pr, "_KS04_CONDITIONAL_BOOST", True)
    monkeypatch.setattr(pr, "_KS04_BOOST_VALUE", 1.5)

    rng = np.random.default_rng(13)
    roster = _make_ks04_wr_roster(receiving_yards_dist=[5, 5, 5, 5, 5])
    outcomes = make_outcomes(pass_yards=[10])
    rates = make_turnover_rates()

    yards_seen = []
    for _ in range(2000):
        state = make_state(yard_line=80)  # plenty of field; no clamp
        result = resolve_play(state, "pass", outcomes, rates, rng, roster=roster, is_home=True)
        if result.is_complete and not result.is_touchdown and not result.is_fumble:
            yards_seen.append(result.yards)

    yards_arr = np.array(yards_seen)
    assert len(yards_arr) > 0, "Expected non-TD completions to count yards"
    mean = yards_arr.mean()
    # Tight band around 5.5 catches both pre-Task-2 (`+1` unconditional → ~6.5)
    # and a missing-conditional regression on the new `+1.5` constant (~7.0).
    assert 5.3 <= mean <= 6.0, (
        f"mean={mean:.3f} suggests boost was applied when no clamp fires "
        f"(D-11 violation). Expected ~5.5 (5 + 0.5 home-field expected)."
    )


def test_ks04_boost_zero_in_red_zone(monkeypatch):
    """RZ branch (yard_line ≤ 20): boost stays 0 (preserved KS-04 behavior).

    KS-04 keeps the RZ no-boost rule from the original code (line 278:
    `boost = CATCH_YARDS_BOOST if state.yard_line > 20 else 0`). Inside the
    20, the TD gate controls scoring; adding yards there would inflate TDs.
    With dist=[5] and yard_line=15, raw sample is 5; clamp does NOT fire (5
    <= 15) AND we're in the RZ — both gates keep boost = 0. Expected mean
    ~5.5 (5 + 0.5 home-field).
    """
    from fantasy_sim.engine import play_resolver as pr
    monkeypatch.setattr(pr, "_KS04_CONDITIONAL_BOOST", True)
    monkeypatch.setattr(pr, "_KS04_BOOST_VALUE", 1.5)

    rng = np.random.default_rng(17)
    roster = _make_ks04_wr_roster(receiving_yards_dist=[5, 5, 5, 5, 5])
    outcomes = make_outcomes(pass_yards=[10])
    rates = make_turnover_rates()

    yards_seen = []
    for _ in range(3000):
        state = make_state(yard_line=15)  # RZ
        result = resolve_play(state, "pass", outcomes, rates, rng, roster=roster, is_home=True)
        if result.is_complete and not result.is_touchdown and not result.is_fumble:
            yards_seen.append(result.yards)

    yards_arr = np.array(yards_seen)
    assert len(yards_arr) > 0, "Expected non-TD completions inside the 20"
    mean = yards_arr.mean()
    assert 5.3 <= mean <= 6.0, (
        f"mean={mean:.3f} suggests RZ branch is no longer boost-zero "
        f"(KS-04 must preserve RZ no-boost rule). Expected ~5.5."
    )


def test_ks04_boost_conditional_when_clamp_fires(monkeypatch):
    """D-11: when raw_sample > yard_line (and outside RZ), boost IS applied
    before _clamp_yards.

    Captures the input to `_clamp_yards` via monkeypatch and verifies the
    BRANCH was taken. With dist=[35] and yard_line=30 (outside the RZ so the
    `state.yard_line > 20` half of the conditional fires):
    - raw_sample = 35
    - 35 > 30 → clamp WOULD fire; AND yard_line > 20 → outside RZ check
      passes; so boost fires. player_yards = 35 + 1.5 = 36.5; coerced to int
      via `round` (banker's rounding) → 36.
    - is_home=False removes home-field +1 noise so every clamp call sees
      exactly the post-boost integer.
    - _clamp_yards receives 36 (boost fired) instead of 35 (no boost).

    Without the new conditional branch (i.e., if the boost-on-clamp-fires
    semantics were missing on the flag-on path), every recorded input would
    be exactly 35.
    """
    from fantasy_sim.engine import play_resolver as pr
    monkeypatch.setattr(pr, "_KS04_CONDITIONAL_BOOST", True)
    monkeypatch.setattr(pr, "_KS04_BOOST_VALUE", 1.5)

    captured_clamp_inputs: list[int] = []
    real_clamp = pr._clamp_yards

    def _spy_clamp(yard_line, yards):
        captured_clamp_inputs.append(yards)
        return real_clamp(yard_line, yards)

    monkeypatch.setattr(pr, "_clamp_yards", _spy_clamp)

    rng = np.random.default_rng(23)
    roster = _make_ks04_wr_roster(receiving_yards_dist=[35, 35, 35, 35, 35])
    outcomes = make_outcomes(pass_yards=[10])
    rates = make_turnover_rates()

    for _ in range(200):
        state = make_state(yard_line=30)  # outside RZ; raw 35 > 30 → boost fires
        # is_home=False to remove home-field noise — every clamp input is
        # exactly raw + boost (or raw if no boost).
        resolve_play(state, "pass", outcomes, rates, rng, roster=roster, is_home=False)

    assert captured_clamp_inputs, "Expected at least one _clamp_yards call"
    # All raw samples are 35; boost adds 1.5 → 36 or 37 after coercion.
    # Without the conditional branch (i.e., if boost never fires when it
    # should), every recorded input would be exactly 35.
    boosted = [v for v in captured_clamp_inputs if v > 35]
    assert len(boosted) > 0, (
        f"_clamp_yards inputs = {sorted(set(captured_clamp_inputs))}; "
        f"expected at least some > 35 proving boost fired before clamp "
        f"(D-11). All inputs ≤ 35 means the conditional boost branch was "
        f"never taken."
    )


# === KS-06: Backup-receiver fallback range (D-19 sub-fix 2) ===

def test_ks06_backup_receiver_fallback_range_when_flag_on():
    """KS-06 D-19 sub-fix 2: the integer fallback in _resolve_pass — used when
    the receiver has no receiving_yards_dist AND the team-bucket sample is
    <= 0 — should sample in [5, 17] (mean ~11.5, NFL-realistic per-completion
    yards) when phase1_ks_flags.ks06_backup_receiver_fix.enabled is true.

    The test checks the literal bounds of the new range; the legacy bounds
    are [3, 11] (mean ~7).
    """
    rng = np.random.default_rng(42)
    samples = [int(rng.integers(5, 18)) for _ in range(20000)]
    assert min(samples) >= 5, f"min sample {min(samples)} below new lower bound 5"
    assert max(samples) <= 17, (
        f"max sample {max(samples)} above new upper bound 17 "
        f"(rng.integers high is exclusive)"
    )
    mean = float(np.mean(samples))
    assert 10.5 <= mean <= 12.0, (
        f"mean {mean} outside expected ~11.5 for [5,18) uniform"
    )


def test_ks06_backup_receiver_fallback_branch_uses_new_range_when_flag_on(
    monkeypatch,
):
    """Behavioural test: when the player has no receiving_yards_dist and the
    team bucket samples <= 0, the resulting yards before clamping should fall
    in [5, 17] when the KS-06 flag is on. Stub the team bucket to always
    return 0 so the integer fallback fires deterministically.
    """
    from fantasy_sim.engine import play_resolver as pr
    monkeypatch.setattr(pr, "_KS06_BACKUP_RECEIVER_FIX", True, raising=False)
    # Force the KS-04 conditional path off so the fallback path's output is
    # not perturbed by an extra `+1.5` boost (this test only exercises the
    # raw_sample range, not the post-boost arithmetic).
    monkeypatch.setattr(pr, "_KS04_CONDITIONAL_BOOST", False)

    captured: list[int] = []
    real_clamp = pr._clamp_yards

    def _spy_clamp(yard_line, yards):
        captured.append(yards)
        return real_clamp(yard_line, yards)

    monkeypatch.setattr(pr, "_clamp_yards", _spy_clamp)

    # Build a roster whose receiver has NO receiving_yards_dist (forces the
    # fallback). Then provide an outcomes object whose `pass` default yields
    # 0 yards every time (forces the integer-fallback branch within the
    # fallback path).
    from fantasy_sim.engine.play_resolver import resolve_play
    from fantasy_sim.models.distributions import PlayOutcomeDist
    from fantasy_sim.models.player import (
        PlayerModel, PlayerOutcomes, PlayerUsage, TeamRoster,
    )

    qb = PlayerModel(
        player_id="QB1", name="QB One", position="QB", team="KC",
        usage=PlayerUsage(snap_share=1.0, scramble_rate=0.0),
        outcomes=PlayerOutcomes(catch_rate=0.0, fumble_rate=0.0, pass_fumble_rate=0.0),
        games_played=10,
    )
    wr = PlayerModel(
        player_id="WR1", name="WR Backup", position="WR", team="KC",
        usage=PlayerUsage(target_share=1.0),
        outcomes=PlayerOutcomes(
            catch_rate=1.0, red_zone_catch_rate=1.0, fumble_rate=0.0,
            receiving_yards_dist=None,  # critical: forces the fallback branch
        ),
        games_played=10,
    )
    roster = TeamRoster(team="KC", players=[qb, wr])

    # Outcomes whose `pass` defaults always yield 0 (so the team_yards <= 0
    # branch always triggers and the integer fallback fires).
    outcomes = PlayOutcomeDist(distributions={}, defaults={"pass": np.array([0])})

    rates = TurnoverRates(team="KC", int_rate=0.0, fumble_rate=0.0,
                          sack_rate=0.0, sack_fumble_rate=0.0)
    rng = np.random.default_rng(7)

    for _ in range(500):
        state = make_state(yard_line=50)  # outside RZ
        resolve_play(state, "pass", outcomes, rates, rng, roster=roster, is_home=False)

    assert captured, "Expected at least one clamp call"
    # Strip 0s — those come from incomplete passes, but catch_rate=1.0 so all
    # captured values came from completions where raw_sample fell in [5, 17].
    nonzero = [v for v in captured if v != 0]
    assert nonzero, "Expected at least one nonzero clamp input from the fallback"
    # The KS-04 conditional boost is off (monkeypatched), so the legacy
    # `legacy_boost = 1 if state.yard_line > 20 else 0` outside-RZ +1
    # boost still fires inside _resolve_pass. yard_line=50 > 20 → every
    # captured value = raw_sample + 1. New range raw [5, 17] → captured
    # [6, 18].
    assert min(nonzero) >= 6, (
        f"min clamp input {min(nonzero)} below KS-06 new lower bound 6 "
        f"(raw 5 + legacy outside-RZ +1 boost)"
    )
    assert max(nonzero) <= 18, (
        f"max clamp input {max(nonzero)} above KS-06 new upper bound 18 "
        f"(raw 17 + legacy outside-RZ +1 boost)"
    )
    mean = float(np.mean(nonzero))
    # raw mean ~11.5 + 1 boost → ~12.5
    assert 11.0 <= mean <= 14.0, (
        f"mean {mean} outside expected ~12.5 for fallback [5,18) sampling + boost"
    )


def test_ks06_backup_receiver_fallback_branch_uses_legacy_range_when_flag_off(
    monkeypatch,
):
    """Mirror of the above with the flag off — proves Arm A keeps the legacy
    [3, 11] range so the per-KS A/B is genuinely two-arm."""
    from fantasy_sim.engine import play_resolver as pr
    monkeypatch.setattr(pr, "_KS06_BACKUP_RECEIVER_FIX", False, raising=False)
    monkeypatch.setattr(pr, "_KS04_CONDITIONAL_BOOST", False)

    captured: list[int] = []
    real_clamp = pr._clamp_yards

    def _spy_clamp(yard_line, yards):
        captured.append(yards)
        return real_clamp(yard_line, yards)

    monkeypatch.setattr(pr, "_clamp_yards", _spy_clamp)

    from fantasy_sim.engine.play_resolver import resolve_play
    from fantasy_sim.models.distributions import PlayOutcomeDist
    from fantasy_sim.models.player import (
        PlayerModel, PlayerOutcomes, PlayerUsage, TeamRoster,
    )

    qb = PlayerModel(
        player_id="QB1", name="QB One", position="QB", team="KC",
        usage=PlayerUsage(snap_share=1.0, scramble_rate=0.0),
        outcomes=PlayerOutcomes(catch_rate=0.0, fumble_rate=0.0, pass_fumble_rate=0.0),
        games_played=10,
    )
    wr = PlayerModel(
        player_id="WR1", name="WR Backup", position="WR", team="KC",
        usage=PlayerUsage(target_share=1.0),
        outcomes=PlayerOutcomes(
            catch_rate=1.0, red_zone_catch_rate=1.0, fumble_rate=0.0,
            receiving_yards_dist=None,
        ),
        games_played=10,
    )
    roster = TeamRoster(team="KC", players=[qb, wr])
    outcomes = PlayOutcomeDist(distributions={}, defaults={"pass": np.array([0])})
    rates = TurnoverRates(team="KC", int_rate=0.0, fumble_rate=0.0,
                          sack_rate=0.0, sack_fumble_rate=0.0)
    rng = np.random.default_rng(7)

    for _ in range(500):
        state = make_state(yard_line=50)  # outside RZ
        resolve_play(state, "pass", outcomes, rates, rng, roster=roster, is_home=False)

    nonzero = [v for v in captured if v != 0]
    assert nonzero, "Expected at least one nonzero clamp input from the fallback"
    # Legacy [3, 11] range; the unconditional outside-RZ +1 boost (legacy
    # KS-04 path) adds 1, so observed values fall in [4, 12]. The boost is
    # disabled in this test (KS04_CONDITIONAL_BOOST=False) but the legacy
    # `legacy_boost = 1 if state.yard_line > 20 else 0` still fires inside
    # _resolve_pass. yard_line=50 > 20 so each value gets +1.
    # Effective observed range: [3+1, 11+1] = [4, 12].
    assert min(nonzero) >= 4, (
        f"min clamp input {min(nonzero)} below legacy lower bound 4 (3+1 boost)"
    )
    assert max(nonzero) <= 12, (
        f"max clamp input {max(nonzero)} above legacy upper bound 12 (11+1 boost)"
    )
    mean = float(np.mean(nonzero))
    # raw [3, 11) uniform mean ~ 6, +1 boost → ~7
    assert 6.0 <= mean <= 8.5, (
        f"mean {mean} outside expected ~7 for legacy fallback [3,12) sampling"
    )


# === KS-07: positional RZ catch rate modifiers (D-20, Cycle 3 D-45) ===
#
# RZ_CATCH_RATE_MODIFIERS replaces the single 0.92 scalar with per-position
# rates: WR=0.92, TE=0.95, RB=0.85. Real NFL data: TEs catch RZ targets at
# slightly higher rates than WRs (~95% vs ~92% of overall rate); RBs at lower
# rates (~85%, due to checkdowns under pressure). Single 0.92 modifier
# under-estimates TE RZ production and over-estimates RB RZ production.
# Gated behind `phase1_ks_flags.ks07_positional_rz_catch_rate.enabled` so the
# legacy scalar 0.92 path stays as Arm A for the per-KS A/B until promotion.


def test_ks07_rz_catch_rate_modifiers_dict():
    """D-20: RZ_CATCH_RATE_MODIFIERS literal contents per KS-07 hypothesis."""
    from fantasy_sim.engine.play_resolver import RZ_CATCH_RATE_MODIFIERS
    assert RZ_CATCH_RATE_MODIFIERS == {"WR": 0.92, "TE": 0.95, "RB": 0.85}


def test_ks07_backward_compat_scalar_unchanged():
    """Legacy RZ_CATCH_RATE_MODIFIER must equal RZ_CATCH_RATE_MODIFIERS['WR']."""
    from fantasy_sim.engine.play_resolver import (
        RZ_CATCH_RATE_MODIFIER,
        RZ_CATCH_RATE_MODIFIERS,
    )
    assert RZ_CATCH_RATE_MODIFIER == RZ_CATCH_RATE_MODIFIERS["WR"] == 0.92


def _make_ks07_roster(receiver_position: str, *, catch_rate: float = 1.0) -> TeamRoster:
    """Single-receiver roster with RZ catch rate UNSET (forces fallback path).

    `red_zone_catch_rate=0.0` triggers the `effective_catch_rate <= 0` branch
    inside `_resolve_pass`, which then computes the fallback as
    `catch_rate * RZ_CATCH_RATE_MODIFIERS.get(receiver.position, ...)` (flag-on)
    or `catch_rate * RZ_CATCH_RATE_MODIFIER` (flag-off).
    """
    qb = PlayerModel(
        "QB1", "QB", "QB", "T",
        PlayerUsage(snap_share=1.0, scramble_rate=0.0),
        PlayerOutcomes(),
    )
    receiver = PlayerModel(
        "RX1", "RX1", receiver_position, "T",
        PlayerUsage(target_share=1.0),
        PlayerOutcomes(
            catch_rate=catch_rate,
            red_zone_catch_rate=0.0,  # forces fallback to position-aware modifier
            receiving_yards_dist=np.array([5, 5, 5]),
            fumble_rate=0.0,
            receiving_td_factor=1.0,
        ),
    )
    return TeamRoster(team="T", players=[qb, receiver])


def _measure_rz_catch_rate(roster: TeamRoster, *, n: int = 4000, seed: int = 17) -> float:
    """Run N RZ pass plays and return observed completion rate.

    Uses yard_line=15 (in RZ for the catch-rate branch) and a deterministic
    pass distribution so any rate variation comes from the catch_rate gate.
    """
    rng = np.random.default_rng(seed)
    outcomes = make_outcomes(pass_yards=[5])
    rates = make_turnover_rates()
    completions = 0
    for _ in range(n):
        state = make_state(yard_line=15)
        result = resolve_play(state, "pass", outcomes, rates, rng, roster=roster)
        if result.is_complete:
            completions += 1
    return completions / n


def test_ks07_flag_on_te_uses_higher_rate(monkeypatch):
    """Flag-on path: TE receiver gets RZ rate of 0.95 * catch_rate.

    With `catch_rate=1.0` and the TE modifier of 0.95, the observed rate
    should center on 0.95 (95% completion). The legacy WR-only modifier 0.92
    yields 0.92. The 4000-trial standard error is ~0.0035, so the [0.93, 0.97]
    band cleanly separates the two hypotheses (3 σ from 0.92).
    """
    from fantasy_sim.engine import play_resolver as pr
    monkeypatch.setattr(pr, "_KS07_POSITIONAL_RZ_CATCH_RATE", True)
    roster = _make_ks07_roster("TE")
    rate = _measure_rz_catch_rate(roster)
    assert 0.93 <= rate <= 0.97, (
        f"TE RZ catch rate {rate:.3f} not within [0.93, 0.97] expected for "
        f"position-aware modifier 0.95 (would be ~0.92 under legacy scalar)"
    )


def test_ks07_flag_on_rb_uses_lower_rate(monkeypatch):
    """Flag-on path: RB receiver gets RZ rate of 0.85 * catch_rate.

    With `catch_rate=1.0` and the RB modifier of 0.85, the observed rate
    should center on 0.85 (85% completion). The [0.83, 0.87] band cleanly
    separates from the legacy 0.92 (~20 σ at n=4000).
    """
    from fantasy_sim.engine import play_resolver as pr
    monkeypatch.setattr(pr, "_KS07_POSITIONAL_RZ_CATCH_RATE", True)
    roster = _make_ks07_roster("RB")
    rate = _measure_rz_catch_rate(roster)
    assert 0.83 <= rate <= 0.87, (
        f"RB RZ catch rate {rate:.3f} not within [0.83, 0.87] expected for "
        f"position-aware modifier 0.85 (would be ~0.92 under legacy scalar)"
    )


def test_ks07_flag_on_wr_unchanged_from_legacy(monkeypatch):
    """Flag-on path: WR receiver still gets RZ rate of 0.92 * catch_rate (no change)."""
    from fantasy_sim.engine import play_resolver as pr
    monkeypatch.setattr(pr, "_KS07_POSITIONAL_RZ_CATCH_RATE", True)
    roster = _make_ks07_roster("WR")
    rate = _measure_rz_catch_rate(roster)
    assert 0.90 <= rate <= 0.94, (
        f"WR RZ catch rate {rate:.3f} should match legacy 0.92 under flag-on"
    )


def test_ks07_flag_off_te_uses_legacy_scalar(monkeypatch):
    """Flag-off path: TE receiver gets the legacy 0.92 * catch_rate (Arm A parity).

    This is the bit-for-bit pre-Phase-1 behavior — TE specifically should NOT
    pick up the new 0.95 rate when the flag is off, even though the dict
    constant exists in the module namespace.
    """
    from fantasy_sim.engine import play_resolver as pr
    monkeypatch.setattr(pr, "_KS07_POSITIONAL_RZ_CATCH_RATE", False)
    roster = _make_ks07_roster("TE")
    rate = _measure_rz_catch_rate(roster)
    assert 0.90 <= rate <= 0.94, (
        f"TE RZ catch rate under flag-off {rate:.3f} should match legacy 0.92, "
        f"not the flag-on 0.95"
    )


def test_ks07_flag_off_rb_uses_legacy_scalar(monkeypatch):
    """Flag-off path: RB receiver gets the legacy 0.92 * catch_rate (Arm A parity)."""
    from fantasy_sim.engine import play_resolver as pr
    monkeypatch.setattr(pr, "_KS07_POSITIONAL_RZ_CATCH_RATE", False)
    roster = _make_ks07_roster("RB")
    rate = _measure_rz_catch_rate(roster)
    assert 0.90 <= rate <= 0.94, (
        f"RB RZ catch rate under flag-off {rate:.3f} should match legacy 0.92, "
        f"not the flag-on 0.85"
    )


# === KS-15: field-position clamping fix (D-14 + D-15 + D-15b, Cycle 3 D-45) ===
#
# Per Plan 07. KS-15 fixes the field-position clamping bug that drops upper-tail
# values from QB pass_yards and WR receiving_yards distributions. Per D-14:
# detect would-be-TD from the un-clamped sample BEFORE clamping; if it would
# have crossed the goal, route through the TD gate (inside the 20) or score
# unconditionally (outside the 20). Per D-15: in the same code path, drop
# `CATCH_YARDS_BOOST` to 0 — the boost was a band-aid for clamping-induced
# under-counting that KS-15 obviates at the mechanism level. Per D-15b: apply
# the same `min(yard_line, sample)` + would-be-TD detection pattern to the
# legacy non-roster paths in `_resolve_pass` (lines 461-480) and `_resolve_run`
# (lines 558-575) so the two divergent clamping semantics inside the same
# module are unified.
#
# All tests force the new code path on via `monkeypatch.setattr(pr,
# "_KS15_UNCLAMP_FOR_TD_GATE", True)` so RED→GREEN is deterministic regardless
# of the defaults.yaml value. Test 5 is a calibration regression guard that
# does NOT depend on the flag (PASS_TD_GATE values are policy constants, not
# behavioral wiring).


def test_ks15_catch_yards_boost_zeroed_in_ks15_path(monkeypatch):
    """D-15: when the KS-15 flag is on, the effective per-catch boost is 0.

    Behavioral assertion (not a constant check, because per Cycle 3 D-45 the
    legacy `CATCH_YARDS_BOOST = 1.5` constant stays in module scope as the
    Arm A / flag-off path — it is the FLAG-ON path that zeroes the boost).
    yard_line=80, dist samples 5; raw=5 < 80 (no clamp); KS-15 path adds 0
    boost → observed mean ~5.5 (5 + 0.5 home-field expected).
    """
    from fantasy_sim.engine import play_resolver as pr
    monkeypatch.setattr(pr, "_KS15_UNCLAMP_FOR_TD_GATE", True)
    # Ensure KS-04 conditional path stays off so the test isolates the KS-15
    # boost-zeroing behavior.
    monkeypatch.setattr(pr, "_KS04_CONDITIONAL_BOOST", False)

    rng = np.random.default_rng(31)
    roster = _make_ks04_wr_roster(receiving_yards_dist=[5, 5, 5, 5, 5])
    outcomes = make_outcomes(pass_yards=[10])
    rates = make_turnover_rates()

    yards_seen = []
    for _ in range(2000):
        state = make_state(yard_line=80)
        result = resolve_play(state, "pass", outcomes, rates, rng, roster=roster, is_home=True)
        if result.is_complete and not result.is_touchdown and not result.is_fumble:
            yards_seen.append(result.yards)

    yards_arr = np.array(yards_seen)
    assert len(yards_arr) > 0, "Expected non-TD completions"
    mean = yards_arr.mean()
    # Tight band catches both the legacy unconditional `+1` (~6.5) and the
    # KS-04 conditional `+1.5` if either leaks into the KS-15 code path.
    assert 5.3 <= mean <= 6.0, (
        f"mean={mean:.3f} suggests boost was applied in the KS-15 code path "
        f"(D-15 violation). Expected ~5.5 (5 + 0.5 home-field expected)."
    )


def _make_ks15_wr_roster(receiving_yards_dist, *, catch_rate=1.0, red_zone_catch_rate=1.0,
                          receiving_td_factor=1.0):
    """Single-WR roster for deterministic KS-15 yards/TD-gate testing."""
    qb = PlayerModel(
        "QB1", "QB", "QB", "T",
        PlayerUsage(snap_share=1.0, scramble_rate=0.0),
        PlayerOutcomes(),
    )
    wr = PlayerModel(
        "WR1", "WR1", "WR", "T",
        PlayerUsage(target_share=1.0),
        PlayerOutcomes(
            catch_rate=catch_rate,
            red_zone_catch_rate=red_zone_catch_rate,
            receiving_yards_dist=np.array(receiving_yards_dist),
            fumble_rate=0.0,
            receiving_td_factor=receiving_td_factor,
        ),
    )
    return TeamRoster(team="T", players=[qb, wr])


def _make_ks15_rb_roster(rushing_yards_dist, *, fumble_rate=0.0,
                         rushing_td_factor=1.0, i5_rushing_td_factor=1.0):
    """Single-RB roster for deterministic KS-15 run/safety testing."""
    rb = PlayerModel(
        "RB1", "RB1", "RB", "T",
        PlayerUsage(carry_share=1.0),
        PlayerOutcomes(
            rushing_yards_dist=np.array(rushing_yards_dist),
            fumble_rate=fumble_rate,
            rushing_td_factor=rushing_td_factor,
            i5_rushing_td_factor=i5_rushing_td_factor,
        ),
    )
    return TeamRoster(team="T", players=[rb])


def test_ks15_pass_long_catch_outside_rz_yields_td_when_flag_on(monkeypatch):
    """D-14: yard_line=30, raw=35 (would-be TD outside RZ) → unconditional TD.

    Outside the 20, the TD gate does not apply; any would-be TD scores. The
    legacy clamp-then-check path also produced TDs here (clamping 35→30 still
    triggers `state.yard_line - yards <= 0`), but this test pins the new
    semantic explicitly so any future refactor cannot regress it.
    """
    from fantasy_sim.engine import play_resolver as pr
    monkeypatch.setattr(pr, "_KS15_UNCLAMP_FOR_TD_GATE", True)
    monkeypatch.setattr(pr, "_KS04_CONDITIONAL_BOOST", False)

    rng = np.random.default_rng(37)
    roster = _make_ks15_wr_roster(receiving_yards_dist=[35, 35, 35, 35, 35])
    outcomes = make_outcomes(pass_yards=[10])
    rates = make_turnover_rates()

    td_count = 0
    n = 1000
    for _ in range(n):
        state = make_state(yard_line=30)
        result = resolve_play(state, "pass", outcomes, rates, rng, roster=roster, is_home=False)
        if result.is_complete and result.is_touchdown:
            td_count += 1
    rate = td_count / n
    assert rate >= 0.99, (
        f"Outside-RZ would-be-TD rate {rate:.3f} not ~1.0; KS-15 D-14 requires "
        f"unconditional TD when raw_sample > yard_line and yard_line > 20."
    )


def test_ks15_pass_long_catch_inside_rz_routes_through_gate_when_flag_on(monkeypatch):
    """D-14: yard_line=10, raw=25 (would-be TD inside RZ) → routed through gate.

    Inside the 20, the TD gate decides whether the would-be TD scores. With
    yard_line=10, PASS_TD_GATE[(6,10)] = 0.45. With receiving_td_factor=1.0
    and 5000 trials, observed TD rate should center on 0.45 ± ~0.014 (3 σ
    band). Band [0.42, 0.48] separates cleanly from the legacy clamp-only
    semantics (which would have produced ~1.0 TD rate because clamping 25→10
    triggers `state.yard_line - yards <= 0` then proceeds to the gate anyway —
    so this test is more about pinning the GATE rate after KS-15 than about
    flag-on vs flag-off semantics; if the would-be detection is wrong, the
    rate will skew sharply).
    """
    from fantasy_sim.engine import play_resolver as pr
    monkeypatch.setattr(pr, "_KS15_UNCLAMP_FOR_TD_GATE", True)
    monkeypatch.setattr(pr, "_KS04_CONDITIONAL_BOOST", False)

    rng = np.random.default_rng(41)
    roster = _make_ks15_wr_roster(receiving_yards_dist=[25, 25, 25, 25, 25])
    outcomes = make_outcomes(pass_yards=[10])
    rates = make_turnover_rates()

    td_count = 0
    n = 5000
    for _ in range(n):
        state = make_state(yard_line=10)
        result = resolve_play(state, "pass", outcomes, rates, rng, roster=roster, is_home=False)
        if result.is_complete and result.is_touchdown:
            td_count += 1
    rate = td_count / n
    # PASS_TD_GATE[(6,10)] = 0.45. ± 0.03 covers RNG noise at n=5000.
    assert 0.42 <= rate <= 0.48, (
        f"Inside-RZ TD gate rate {rate:.3f} not within [0.42, 0.48] expected "
        f"for PASS_TD_GATE[(6,10)] = 0.45. KS-15 D-14: would-be TDs in RZ "
        f"must be routed through the gate."
    )


def test_ks15_pass_short_catch_no_double_counted_yards_when_flag_on(monkeypatch):
    """yard_line=80, raw=5; no clamp, no boost → mean ~5.5 (home-field expected).

    Sister of test_ks15_catch_yards_boost_zeroed_in_ks15_path but with the
    explicit framing of "no double-counted yards from boost stacking on top
    of un-clamped sample". Tight upper bound 6.0 catches both `+1` and `+1.5`
    leakage.
    """
    from fantasy_sim.engine import play_resolver as pr
    monkeypatch.setattr(pr, "_KS15_UNCLAMP_FOR_TD_GATE", True)
    monkeypatch.setattr(pr, "_KS04_CONDITIONAL_BOOST", False)

    rng = np.random.default_rng(43)
    roster = _make_ks15_wr_roster(receiving_yards_dist=[5, 5, 5, 5, 5])
    outcomes = make_outcomes(pass_yards=[10])
    rates = make_turnover_rates()

    yards_seen = []
    for _ in range(2000):
        state = make_state(yard_line=80)
        result = resolve_play(state, "pass", outcomes, rates, rng, roster=roster, is_home=True)
        if result.is_complete and not result.is_touchdown and not result.is_fumble:
            yards_seen.append(result.yards)

    arr = np.array(yards_seen)
    assert len(arr) > 0, "Expected non-TD completions"
    mean = arr.mean()
    assert 5.3 <= mean <= 6.0, (
        f"mean={mean:.3f} suggests boost double-count in KS-15 path. Expected ~5.5."
    )


def test_ks15_pass_td_gate_calibration_unchanged():
    """Regression guard: PASS_TD_GATE[(1,3)] = 0.55 over 100k trials.

    Independent of the KS-15 flag — this guards the gate constants themselves,
    which KS-15 must not perturb during the refactor. Mirrors the KS-01 guard.
    """
    rng = np.random.default_rng(0)
    n = 100_000
    successes = sum(1 for _ in range(n) if _red_zone_td_gate(3, "pass", rng))
    rate = successes / n
    assert 0.54 <= rate <= 0.56, f"PASS_TD_GATE[(1,3)] regressed: rate={rate}"


def test_ks15_run_long_carry_outside_rz_yields_td_when_flag_on(monkeypatch):
    """D-14: yard_line=25, raw=30 (would-be TD outside RZ) → unconditional TD."""
    from fantasy_sim.engine import play_resolver as pr
    monkeypatch.setattr(pr, "_KS15_UNCLAMP_FOR_TD_GATE", True)

    rng = np.random.default_rng(47)
    roster = _make_ks15_rb_roster(rushing_yards_dist=[30, 30, 30, 30, 30])
    outcomes = make_outcomes(run_yards=[5])
    rates = make_turnover_rates()

    td_count = 0
    n = 1000
    for _ in range(n):
        state = make_state(yard_line=25)
        result = resolve_play(state, "run", outcomes, rates, rng, roster=roster, is_home=False)
        if result.is_touchdown:
            td_count += 1
    rate = td_count / n
    assert rate >= 0.99, (
        f"Outside-RZ would-be-TD rate {rate:.3f} not ~1.0 for runs; KS-15 D-14 "
        f"requires unconditional TD when raw_yards > yard_line and yard_line > 20."
    )


def test_ks15_run_safety_branch_preserved_when_flag_on(monkeypatch):
    """yard_line=98 (own 2), raw_yards=-100 → is_safety=True must still fire.

    Critical regression guard: the safety branch detects a massive backward
    play (yard_line - raw_yards >= 100) BEFORE any clamping. The KS-15
    refactor must not mask this detection. Per the existing safety semantics
    in `_resolve_run`, raw_yards is the home-field-adjusted sample; a
    distribution sampling -100 with yard_line=98 hits 98 - (-100) = 198 >= 100
    → safety.

    Note: real PBP rushing distributions almost never sample -100, but the
    safety branch must remain reachable as a defensive guard. Use a
    deterministic distribution to force the path.
    """
    from fantasy_sim.engine import play_resolver as pr
    monkeypatch.setattr(pr, "_KS15_UNCLAMP_FOR_TD_GATE", True)

    rng = np.random.default_rng(53)
    # Deterministic large negative loss; is_home=False removes home-field +1
    # so raw_yards == player_yards == -100 every play.
    roster = _make_ks15_rb_roster(rushing_yards_dist=[-100])
    outcomes = make_outcomes(run_yards=[-100])
    rates = make_turnover_rates()

    safety_count = 0
    n = 200
    for _ in range(n):
        state = make_state(yard_line=98)
        result = resolve_play(state, "run", outcomes, rates, rng, roster=roster, is_home=False)
        if result.is_safety:
            safety_count += 1
    # Every play should fire is_safety=True (deterministic distribution).
    assert safety_count == n, (
        f"is_safety fired on {safety_count}/{n} plays; KS-15 must preserve the "
        f"safety detection on raw_yards before clamping."
    )


def test_ks15_legacy_pass_path_preserves_distribution_when_flag_on(monkeypatch):
    """D-15b (MEDIUM-4): legacy non-roster `_resolve_pass` path also uses the
    KS-15 would-be-TD detection pattern. With roster=None, yard_line=30, and
    `play_outcomes` returning 35-yard pass samples: TD rate ~100% AND yards
    saturate at 30 (the goal — NOT silently truncated to a smaller value).

    Pre-fix legacy path also produced TDs (clamping 35→30 then `yard_line -
    yards <= 0`), so this test pins the post-fix yards == yard_line saturation
    AND TD rate, both of which would survive a wrong refactor only if the
    legacy semantics were carefully preserved. Without `roster=None`, the
    test would route through the roster path covered by Tests 2-7.
    """
    from fantasy_sim.engine import play_resolver as pr
    monkeypatch.setattr(pr, "_KS15_UNCLAMP_FOR_TD_GATE", True)

    rng = np.random.default_rng(59)
    # Deterministic 35-yd pass sample regardless of bucket.
    outcomes = make_outcomes(pass_yards=[35, 35, 35, 35, 35])
    rates = make_turnover_rates()  # no sacks, no INTs, no fumbles

    td_count = 0
    yards_seen = []
    n = 1000
    for _ in range(n):
        state = make_state(yard_line=30)
        # roster=None forces the legacy non-roster branch at lines 461-480.
        result = resolve_play(state, "pass", outcomes, rates, rng, roster=None, is_home=False)
        if result.is_complete:
            yards_seen.append(result.yards)
            if result.is_touchdown:
                td_count += 1
    rate = td_count / n
    arr = np.array(yards_seen)
    assert len(arr) > 0, "Expected at least one completion in legacy path"
    assert rate >= 0.99, (
        f"Legacy pass path TD rate {rate:.3f} not ~1.0 for raw 35 > yard_line 30."
    )
    # Yards must saturate at yard_line=30 (the TD), never silently truncated
    # below 30 by a wrong refactor.
    assert arr.max() == 30, f"Legacy pass path yards.max={arr.max()} != 30"
    assert arr.min() == 30, (
        f"Legacy pass path yards.min={arr.min()} != 30 — distribution should "
        f"saturate at goal for would-be TDs."
    )


def test_ks15_legacy_run_path_preserves_distribution_when_flag_on(monkeypatch):
    """D-15b (MEDIUM-4): legacy non-roster `_resolve_run` path symmetric test.

    yard_line=25, sampler returns 30 → TD rate ~100% AND yards saturate at 25.
    Also tests that yard_line=98 + raw=-100 still triggers is_safety=True via
    the legacy path.
    """
    from fantasy_sim.engine import play_resolver as pr
    monkeypatch.setattr(pr, "_KS15_UNCLAMP_FOR_TD_GATE", True)

    rng = np.random.default_rng(61)
    outcomes = make_outcomes(run_yards=[30, 30, 30, 30, 30])
    rates = make_turnover_rates()

    td_count = 0
    yards_seen = []
    n = 500
    for _ in range(n):
        state = make_state(yard_line=25)
        result = resolve_play(state, "run", outcomes, rates, rng, roster=None, is_home=False)
        yards_seen.append(result.yards)
        if result.is_touchdown:
            td_count += 1
    rate = td_count / n
    arr = np.array(yards_seen)
    assert rate >= 0.99, (
        f"Legacy run path TD rate {rate:.3f} not ~1.0 for raw 30 > yard_line 25."
    )
    assert arr.max() == 25, f"Legacy run path yards.max={arr.max()} != 25"
    assert arr.min() == 25, (
        f"Legacy run path yards.min={arr.min()} != 25 — distribution should "
        f"saturate at goal for would-be TDs."
    )

    # Safety branch on the legacy path
    safety_outcomes = make_outcomes(run_yards=[-100])
    safety_count = 0
    for _ in range(200):
        state = make_state(yard_line=98)
        result = resolve_play(state, "run", safety_outcomes, rates, rng, roster=None, is_home=False)
        if result.is_safety:
            safety_count += 1
    assert safety_count == 200, (
        f"Legacy run path is_safety fired {safety_count}/200; KS-15 D-15b must "
        f"preserve the safety branch on the legacy path."
    )

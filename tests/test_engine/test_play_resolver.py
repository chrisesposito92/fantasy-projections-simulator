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

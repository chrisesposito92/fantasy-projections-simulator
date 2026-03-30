import polars as pl
import numpy as np
import pytest
from fantasy_sim.data.preprocessor import Preprocessor
from fantasy_sim.models.game_state import GameStateBucket
from fantasy_sim.models.distributions import (
    PlayOutcomeDist, TurnoverRates, KickingModel, DriveStartModel, PenaltyRates,
)


class TestPlayCallingDistributions:
    def test_computes_pass_run_ratio_per_team(self, sample_pbp):
        pre = Preprocessor()
        dists = pre.compute_play_calling(sample_pbp)
        assert "KC" in dists
        assert "BUF" in dists

    def test_kc_has_correct_overall_ratio(self, sample_pbp):
        """KC has 8 passes and 4 runs = 66.7% pass rate."""
        pre = Preprocessor()
        dists = pre.compute_play_calling(sample_pbp)
        kc = dists["KC"]
        assert kc.default["pass"] == pytest.approx(8 / 12, abs=0.01)
        assert kc.default["run"] == pytest.approx(4 / 12, abs=0.01)

    def test_buf_has_correct_overall_ratio(self, sample_pbp):
        """BUF has 4 passes and 4 runs = 50% pass rate."""
        pre = Preprocessor()
        dists = pre.compute_play_calling(sample_pbp)
        buf = dists["BUF"]
        assert buf.default["pass"] == pytest.approx(0.5, abs=0.01)
        assert buf.default["run"] == pytest.approx(0.5, abs=0.01)

    def test_distributions_have_bucketed_entries(self, sample_pbp):
        pre = Preprocessor()
        dists = pre.compute_play_calling(sample_pbp)
        kc = dists["KC"]
        assert kc.default is not None

    def test_all_probs_sum_to_one(self, sample_pbp):
        pre = Preprocessor()
        dists = pre.compute_play_calling(sample_pbp)
        for team_dist in dists.values():
            for bucket, probs in team_dist.distributions.items():
                assert sum(probs.values()) == pytest.approx(1.0, abs=0.01)
            assert sum(team_dist.default.values()) == pytest.approx(1.0, abs=0.01)


class TestPlayOutcomeDistributions:
    def test_computes_yards_arrays(self, sample_pbp):
        pre = Preprocessor()
        dist = pre.compute_play_outcomes(sample_pbp)
        assert isinstance(dist, PlayOutcomeDist)
        assert len(dist.distributions) > 0 or len(dist.defaults) > 0

    def test_defaults_contain_all_yards(self, sample_pbp):
        pre = Preprocessor()
        dist = pre.compute_play_outcomes(sample_pbp)
        assert "pass" in dist.defaults
        assert "run" in dist.defaults

    def test_run_defaults_contain_all_run_yards(self, sample_pbp):
        """All run yards in sample: KC=[5,-2,5,12], BUF=[7,3,1,4]"""
        pre = Preprocessor()
        dist = pre.compute_play_outcomes(sample_pbp)
        all_run_yards = sorted([5, -2, 5, 12, 7, 3, 1, 4])
        default_run = sorted(dist.defaults["run"].tolist())
        assert default_run == all_run_yards

    def test_can_sample_from_distribution(self, sample_pbp):
        pre = Preprocessor()
        dist = pre.compute_play_outcomes(sample_pbp)
        rng = np.random.default_rng(42)
        bucket = GameStateBucket(1, "long", "tied", 1, "own_territory")
        yards = dist.sample_yards("pass", bucket, rng)
        assert isinstance(yards, (int, np.integer))


class TestTurnoverRatePreprocessor:
    def test_computes_per_team(self, sample_pbp):
        pre = Preprocessor()
        rates = pre.compute_turnover_rates(sample_pbp)
        assert "KC" in rates
        assert "BUF" in rates

    def test_kc_int_rate(self, sample_pbp):
        """KC has 1 INT on 8 pass attempts = 0.125."""
        pre = Preprocessor()
        rates = pre.compute_turnover_rates(sample_pbp)
        assert rates["KC"].int_rate == pytest.approx(1 / 8, abs=0.01)

    def test_kc_sack_rate(self, sample_pbp):
        """KC has 1 sack on 8 pass attempts = 0.125."""
        pre = Preprocessor()
        rates = pre.compute_turnover_rates(sample_pbp)
        assert rates["KC"].sack_rate == pytest.approx(1 / 8, abs=0.01)

    def test_kc_fumble_rate(self, sample_pbp):
        """KC has 1 fumble lost on 12 total plays = 0.0833."""
        pre = Preprocessor()
        rates = pre.compute_turnover_rates(sample_pbp)
        assert rates["KC"].fumble_rate == pytest.approx(1 / 12, abs=0.01)

    def test_buf_zero_turnovers(self, sample_pbp):
        """BUF has 0 INTs, 0 fumbles, 0 sacks in sample data."""
        pre = Preprocessor()
        rates = pre.compute_turnover_rates(sample_pbp)
        assert rates["BUF"].int_rate == pytest.approx(0.0)
        assert rates["BUF"].fumble_rate == pytest.approx(0.0)
        assert rates["BUF"].sack_rate == pytest.approx(0.0)

    def test_rates_are_probabilities(self, sample_pbp):
        pre = Preprocessor()
        rates = pre.compute_turnover_rates(sample_pbp)
        for team_rates in rates.values():
            assert 0.0 <= team_rates.int_rate <= 1.0
            assert 0.0 <= team_rates.fumble_rate <= 1.0
            assert 0.0 <= team_rates.sack_rate <= 1.0
            assert 0.0 <= team_rates.sack_fumble_rate <= 1.0


class TestKickingModelPreprocessor:
    def test_computes_fg_rates_by_distance(self, sample_field_goals):
        pre = Preprocessor()
        model = pre.compute_kicking_model(sample_field_goals)
        assert isinstance(model, KickingModel)
        assert model.fg_make_rate["0_39"] == pytest.approx(1.0)
        assert model.fg_make_rate["40_49"] == pytest.approx(1.0)
        assert model.fg_make_rate["50_plus"] == pytest.approx(0.0)

    def test_fg_prob_returns_correct_bucket(self, sample_field_goals):
        pre = Preprocessor()
        model = pre.compute_kicking_model(sample_field_goals)
        assert model.fg_prob(35) == model.fg_make_rate["0_39"]
        assert model.fg_prob(45) == model.fg_make_rate["40_49"]
        assert model.fg_prob(52) == model.fg_make_rate["50_plus"]

    def test_xp_rate_defaults_when_no_data(self, sample_field_goals):
        pre = Preprocessor()
        model = pre.compute_kicking_model(sample_field_goals)
        assert 0.90 <= model.xp_rate <= 0.98


class TestDriveStartModelPreprocessor:
    def test_computes_touchback_rate(self, sample_kickoffs):
        """Sample has 3 touchbacks out of 5 kickoffs = 0.6."""
        pre = Preprocessor()
        model = pre.compute_drive_start_model(sample_kickoffs)
        assert isinstance(model, DriveStartModel)
        assert model.touchback_rate == pytest.approx(3 / 5, abs=0.01)

    def test_touchback_yardline(self, sample_kickoffs):
        pre = Preprocessor()
        model = pre.compute_drive_start_model(sample_kickoffs)
        assert model.touchback_yardline == 75

    def test_return_yardlines_from_non_touchbacks(self, sample_kickoffs):
        """Non-touchback plays have yardline_100 = [78, 72]."""
        pre = Preprocessor()
        model = pre.compute_drive_start_model(sample_kickoffs)
        assert len(model.return_yardlines) == 2
        assert sorted(model.return_yardlines.tolist()) == [72, 78]

    def test_sample_produces_valid_yardline(self, sample_kickoffs):
        pre = Preprocessor()
        model = pre.compute_drive_start_model(sample_kickoffs)
        rng = np.random.default_rng(42)
        for _ in range(50):
            yl = model.sample_start_yardline(rng)
            assert 1 <= yl <= 99


def _make_multi_season_pbp() -> pl.DataFrame:
    """Create a 3-season PBP dataset for recency-weighting tests.

    - 2022: 10 run plays (all runs)
    - 2023: 5 pass + 5 run (mixed)
    - 2024: 10 pass plays (all passes)

    Without weights: 15 pass / 30 total = 50% pass rate.
    With weights {2022: 0.2, 2023: 0.3, 2024: 0.5}, recent passes dominate.
    """
    base = {
        "game_id": "test_game",
        "posteam": "KC",
        "defteam": "BUF",
        "down": 1,
        "ydstogo": 10,
        "yardline_100": 75,
        "score_differential": 0,
        "qtr": 1,
        "yards_gained": 5,
        "complete_pass": 0,
        "pass_attempt": 0,
        "rush_attempt": 1,
        "interception": 0,
        "fumble_lost": 0,
        "sack": 0,
        "touchdown": 0,
        "penalty": 0,
        "penalty_yards": 0,
        "passer_player_id": None,
        "receiver_player_id": None,
        "rusher_player_id": "RB01",
    }
    plays = []
    # 2022: 10 run plays
    for i in range(10):
        plays.append({**base, "season": 2022, "week": i + 1, "play_type": "run"})
    # 2023: 5 pass + 5 run
    for i in range(5):
        plays.append({**base, "season": 2023, "week": i + 1, "play_type": "run"})
    for i in range(5):
        plays.append({
            **base,
            "season": 2023,
            "week": i + 6,
            "play_type": "pass",
            "pass_attempt": 1,
            "rush_attempt": 0,
            "complete_pass": 1,
            "rusher_player_id": None,
            "passer_player_id": "QB01",
            "receiver_player_id": "WR01",
        })
    # 2024: 10 pass plays
    for i in range(10):
        plays.append({
            **base,
            "season": 2024,
            "week": i + 1,
            "play_type": "pass",
            "pass_attempt": 1,
            "rush_attempt": 0,
            "complete_pass": 1,
            "rusher_player_id": None,
            "passer_player_id": "QB01",
            "receiver_player_id": "WR01",
        })
    return pl.DataFrame(plays)


class TestRecencyWeighting:
    def test_without_weights_equal_treatment(self):
        """Without weights, 30 plays (15 pass, 15 run) => ~50% pass rate."""
        pbp = _make_multi_season_pbp()
        pre = Preprocessor()
        dists = pre.compute_play_calling(pbp, season_weights=None)
        kc = dists["KC"]
        assert kc.default["pass"] == pytest.approx(0.5, abs=0.01)
        assert kc.default["run"] == pytest.approx(0.5, abs=0.01)

    def test_with_recency_weights_biases_recent(self):
        """With weights {2022: 0.2, 2023: 0.3, 2024: 0.5}, recent passes dominate.

        Replications (max=10):
          2024 weight 0.5 -> 10 reps  -> 10*10 = 100 pass plays
          2023 weight 0.3 -> 6 reps   -> 6*5=30 pass + 6*5=30 run
          2022 weight 0.2 -> 4 reps   -> 4*10=40 run plays
        Totals: 130 pass / 200 total = 65% pass rate.
        """
        pbp = _make_multi_season_pbp()
        pre = Preprocessor()
        weights = {2022: 0.2, 2023: 0.3, 2024: 0.5}
        dists = pre.compute_play_calling(pbp, season_weights=weights)
        kc = dists["KC"]
        # Expect clearly more than 50% pass (the unweighted baseline)
        assert kc.default["pass"] > 0.55

    def test_play_outcomes_with_recency_weights(self):
        """Weighted play outcomes return a valid PlayOutcomeDist without error."""
        pbp = _make_multi_season_pbp()
        pre = Preprocessor()
        weights = {2022: 0.2, 2023: 0.3, 2024: 0.5}
        dist = pre.compute_play_outcomes(pbp, season_weights=weights)
        assert isinstance(dist, PlayOutcomeDist)
        assert "pass" in dist.defaults or "run" in dist.defaults

    def test_turnover_rates_with_recency_weights(self):
        """compute_turnover_rates accepts season_weights without error."""
        pbp = _make_multi_season_pbp()
        pre = Preprocessor()
        weights = {2022: 0.2, 2023: 0.3, 2024: 0.5}
        rates = pre.compute_turnover_rates(pbp, season_weights=weights)
        assert "KC" in rates
        assert 0.0 <= rates["KC"].int_rate <= 1.0

    def test_no_weights_backward_compatible(self):
        """compute_play_calling() == compute_play_calling(season_weights=None)."""
        pbp = _make_multi_season_pbp()
        pre = Preprocessor()
        dists_default = pre.compute_play_calling(pbp)
        dists_none = pre.compute_play_calling(pbp, season_weights=None)
        kc_default = dists_default["KC"]
        kc_none = dists_none["KC"]
        assert kc_default.default["pass"] == pytest.approx(kc_none.default["pass"])
        assert kc_default.default["run"] == pytest.approx(kc_none.default["run"])


class TestComputePenaltyRates:
    def _make_penalty_pbp(self) -> pl.DataFrame:
        """PBP data with some penalty plays for KC and BUF."""
        base_run = {
            "play_type": "run",
            "posteam": "KC",
            "defteam": "BUF",
            "down": 1,
            "ydstogo": 10,
            "yardline_100": 50,
            "score_differential": 0,
            "qtr": 1,
            "yards_gained": 5,
            "complete_pass": 0,
            "pass_attempt": 0,
            "rush_attempt": 1,
            "interception": 0,
            "fumble_lost": 0,
            "sack": 0,
            "touchdown": 0,
        }
        plays = []
        # KC: 10 plays, 3 with penalties (mix of yards)
        for i in range(10):
            p = {
                **base_run,
                "season": 2024,
                "week": i + 1,
                "game_id": f"2024_W{i+1}_KC_BUF",
                "passer_player_id": None,
                "receiver_player_id": None,
                "rusher_player_id": "RB01",
                "penalty": 0,
                "penalty_yards": 0,
            }
            if i < 3:
                p["penalty"] = 1
                p["penalty_yards"] = [5, 10, 15][i]
            plays.append(p)
        # BUF: 10 plays, 0 penalties (tests league-avg fallback)
        for i in range(10):
            plays.append({
                **base_run,
                "season": 2024,
                "week": i + 1,
                "game_id": f"2024_W{i+1}_KC_BUF",
                "posteam": "BUF",
                "defteam": "KC",
                "passer_player_id": None,
                "receiver_player_id": None,
                "rusher_player_id": "RB02",
                "penalty": 0,
                "penalty_yards": 0,
            })
        return pl.DataFrame(plays)

    def test_returns_dict_of_penalty_rates(self):
        pbp = self._make_penalty_pbp()
        pre = Preprocessor()
        result = pre.compute_penalty_rates(pbp)
        assert isinstance(result, dict)
        assert "KC" in result
        assert "BUF" in result

    def test_penalty_rates_are_penalty_rates_instances(self):
        pbp = self._make_penalty_pbp()
        pre = Preprocessor()
        result = pre.compute_penalty_rates(pbp)
        for team, pr in result.items():
            assert isinstance(pr, PenaltyRates)

    def test_kc_penalty_rate(self):
        """KC has 3 penalties on 10 plays => 0.3."""
        pbp = self._make_penalty_pbp()
        pre = Preprocessor()
        result = pre.compute_penalty_rates(pbp)
        assert result["KC"].penalty_rate == pytest.approx(0.3, abs=0.01)

    def test_kc_type_distribution_sums_to_one(self):
        pbp = self._make_penalty_pbp()
        pre = Preprocessor()
        result = pre.compute_penalty_rates(pbp)
        total = sum(result["KC"].type_distribution.values())
        assert total == pytest.approx(1.0, abs=0.01)

    def test_buf_uses_league_avg_fallback(self):
        """BUF has 0 penalties => uses league average fallback rate of 0.07."""
        pbp = self._make_penalty_pbp()
        pre = Preprocessor()
        result = pre.compute_penalty_rates(pbp)
        assert result["BUF"].penalty_rate == pytest.approx(0.07, abs=0.001)

    def test_avg_yards_present(self):
        pbp = self._make_penalty_pbp()
        pre = Preprocessor()
        result = pre.compute_penalty_rates(pbp)
        for team, pr in result.items():
            assert "false_start" in pr.avg_yards
            assert "holding" in pr.avg_yards
            assert "pass_interference" in pr.avg_yards

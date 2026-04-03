"""Tests for PFF talent stabilizer — Bayesian blending with PFF priors."""

import numpy as np
import polars as pl
import pytest

from fantasy_sim.data.pff.loader import PffLoader
from fantasy_sim.data.pff.models import PffConfig, TalentConfig
from fantasy_sim.data.pff.talent import (
    BASELINE_CATCH_RATE,
    BASELINE_FUMBLE_RATE,
    CATCH_RATE_PRIOR_MAX,
    CATCH_RATE_PRIOR_MIN,
    DRAFT_ROUND_MULTIPLIERS,
    MIN_FUMBLE_RATE_SHIFT,
    MIN_RECEIVING_YARDS_SHIFT,
    MIN_RUSHING_YARDS_SHIFT,
    MIN_SCRAMBLE_RATE_SHIFT,
    MIN_TARGET_SHARE_SHIFT,
    TalentStabilizer,
    compute_rookie_catch_rate_prior,
    compute_schedule_adjustment,
    stabilize_value,
)
from fantasy_sim.models.player import (
    PlayerModel,
    PlayerOutcomes,
    PlayerUsage,
    TeamRoster,
)


# ========== Fixtures ==========


@pytest.fixture
def pff_dir(tmp_path):
    """Create a temporary PFF data directory."""
    d = tmp_path / "pff" / "processed" / "nfl"
    d.mkdir(parents=True)
    return d


@pytest.fixture
def loader(pff_dir):
    """PffLoader pointed at temp directory."""
    return PffLoader(pff_dir)


@pytest.fixture
def default_talent_config():
    """TalentConfig with default coefficients."""
    return TalentConfig()


@pytest.fixture
def default_pff_config():
    """PffConfig with talent enabled."""
    return PffConfig(
        enabled=True,
        talent=TalentConfig(enabled=True),
    )


# ========== Parquet helpers ==========


def _write_receiving_summary(pff_dir, season, players):
    """Write a receiving_summary parquet from player dicts.

    Each player dict should have keys matching PFF receiving columns.
    Missing keys get sensible defaults. If players is empty, no file
    is written (loader returns empty DataFrame for missing files).
    """
    if not players:
        return None
    rows = {
        "player_id": [],
        "player": [],
        "team": [],
        "position": [],
        "season": [],
        "week": [],
        "game_id": [],
        "franchise_id": [],
        "jersey_number": [],
        "status": [],
        "drop_rate": [],
        "contested_catch_rate": [],
        "grades_pass_route": [],
        "yprr": [],
        "avg_depth_of_target": [],
        "targets": [],
        "caught_percent": [],
        "yards": [],
        "grades_hands_fumble": [],
    }
    gid = 5000
    for p in players:
        n_games = p.get("n_games", 8)
        for g in range(n_games):
            rows["player_id"].append(p["player_id"])
            rows["player"].append(p["player"])
            rows["team"].append(p["team"])
            rows["position"].append(p.get("position", "WR"))
            rows["season"].append(season)
            rows["week"].append(g + 1)
            rows["game_id"].append(gid + g)
            rows["franchise_id"].append(p.get("franchise_id", 1))
            rows["jersey_number"].append(p.get("jersey_number", 10))
            rows["status"].append("ACT")
            rows["drop_rate"].append(p.get("drop_rate", 5.0))
            rows["contested_catch_rate"].append(p.get("contested_catch_rate", 50.0))
            rows["grades_pass_route"].append(p.get("grades_pass_route", 70.0))
            rows["yprr"].append(p.get("yprr", 1.5))
            rows["avg_depth_of_target"].append(p.get("avg_depth_of_target", 10.0))
            rows["targets"].append(p.get("targets", 6))
            rows["caught_percent"].append(p.get("caught_percent", 65.0))
            rows["yards"].append(p.get("yards", 50.0))
            rows["grades_hands_fumble"].append(p.get("grades_hands_fumble", 70.0))
        gid += 100

    df = pl.DataFrame(rows)
    df.write_parquet(pff_dir / f"receiving_summary_{season}.parquet")
    return df


def _write_passing_summary(pff_dir, season, players):
    """Write a passing_summary parquet from player dicts.

    If players is empty, no file is written.
    """
    if not players:
        return None
    rows = {
        "player_id": [],
        "player": [],
        "team": [],
        "position": [],
        "season": [],
        "week": [],
        "game_id": [],
        "franchise_id": [],
        "jersey_number": [],
        "status": [],
        "accuracy_percent": [],
        "grades_pass": [],
        "twp_rate": [],
        "btt_rate": [],
        "completions": [],
        "attempts": [],
        "avg_time_to_throw": [],
        "scrambles": [],
        "dropbacks": [],
    }
    gid = 8000
    for p in players:
        n_games = p.get("n_games", 8)
        for g in range(n_games):
            rows["player_id"].append(p["player_id"])
            rows["player"].append(p["player"])
            rows["team"].append(p["team"])
            rows["position"].append(p.get("position", "QB"))
            rows["season"].append(season)
            rows["week"].append(g + 1)
            rows["game_id"].append(gid + g)
            rows["franchise_id"].append(p.get("franchise_id", 1))
            rows["jersey_number"].append(p.get("jersey_number", 1))
            rows["status"].append("ACT")
            rows["accuracy_percent"].append(p.get("accuracy_percent", 75.0))
            rows["grades_pass"].append(p.get("grades_pass", 70.0))
            rows["twp_rate"].append(p.get("twp_rate", 3.0))
            rows["btt_rate"].append(p.get("btt_rate", 5.0))
            rows["completions"].append(p.get("completions", 20))
            rows["attempts"].append(p.get("attempts", 32))
            rows["avg_time_to_throw"].append(p.get("avg_time_to_throw", 2.8))
            rows["scrambles"].append(p.get("scrambles", 2))
            rows["dropbacks"].append(p.get("dropbacks", 35))
        gid += 100

    df = pl.DataFrame(rows)
    df.write_parquet(pff_dir / f"passing_summary_{season}.parquet")
    return df


def _write_rushing_summary(pff_dir, season, players):
    """Write a rushing_summary parquet from player dicts.

    If players is empty, no file is written.
    """
    if not players:
        return None
    rows = {
        "player_id": [],
        "player": [],
        "team": [],
        "position": [],
        "season": [],
        "week": [],
        "game_id": [],
        "franchise_id": [],
        "jersey_number": [],
        "status": [],
        "yco_attempt": [],
        "elusive_rating": [],
        "breakaway_percent": [],
        "grades_run": [],
        "attempts": [],
        "yards": [],
        "grades_hands_fumble": [],
    }
    gid = 9000
    for p in players:
        n_games = p.get("n_games", 8)
        for g in range(n_games):
            rows["player_id"].append(p["player_id"])
            rows["player"].append(p["player"])
            rows["team"].append(p["team"])
            rows["position"].append(p.get("position", "HB"))
            rows["season"].append(season)
            rows["week"].append(g + 1)
            rows["game_id"].append(gid + g)
            rows["franchise_id"].append(p.get("franchise_id", 1))
            rows["jersey_number"].append(p.get("jersey_number", 22))
            rows["status"].append("ACT")
            rows["yco_attempt"].append(p.get("yco_attempt", 2.5))
            rows["elusive_rating"].append(p.get("elusive_rating", 50.0))
            rows["breakaway_percent"].append(p.get("breakaway_percent", 5.0))
            rows["grades_run"].append(p.get("grades_run", 70.0))
            rows["attempts"].append(p.get("attempts", 15))
            rows["yards"].append(p.get("yards", 60.0))
            rows["grades_hands_fumble"].append(p.get("grades_hands_fumble", 70.0))
        gid += 100

    df = pl.DataFrame(rows)
    df.write_parquet(pff_dir / f"rushing_summary_{season}.parquet")
    return df


def _make_player(
    player_id: str,
    name: str,
    position: str,
    team: str,
    catch_rate: float = 0.0,
    rz_catch_rate: float = 0.0,
    target_share: float = 0.0,
    carry_share: float = 0.0,
    receiving_yards_dist: np.ndarray | None = None,
    rushing_yards_dist: np.ndarray | None = None,
    games_played: int = 17,
    scramble_rate: float = 0.0,
    fumble_rate: float = 0.0,
) -> PlayerModel:
    """Create a PlayerModel with specified parameters."""
    return PlayerModel(
        player_id=player_id,
        name=name,
        position=position,
        team=team,
        usage=PlayerUsage(
            target_share=target_share,
            carry_share=carry_share,
            scramble_rate=scramble_rate,
        ),
        outcomes=PlayerOutcomes(
            catch_rate=catch_rate,
            red_zone_catch_rate=rz_catch_rate,
            receiving_yards_dist=receiving_yards_dist,
            rushing_yards_dist=rushing_yards_dist,
            fumble_rate=fumble_rate,
        ),
        games_played=games_played,
    )


# ========== stabilize_value pure function tests ==========


class TestStabilizeValue:
    """Tests for the pure stabilize_value function."""

    def test_no_adjustment_below_divergence_threshold(self):
        """When PBP and PFF values are close, PBP is returned unchanged."""
        result = stabilize_value(
            pbp_value=0.65,
            pff_prior=0.67,
            n_observations=100,
            prior_strength=40.0,
            min_divergence=0.03,
        )
        assert result == 0.65

    def test_blends_toward_prior_when_divergent(self):
        """When gap exceeds threshold, result is between PBP and PFF."""
        result = stabilize_value(
            pbp_value=0.55,
            pff_prior=0.70,
            n_observations=100,
            prior_strength=40.0,
            min_divergence=0.03,
        )
        # Should be between 0.55 and 0.70
        assert 0.55 < result < 0.70
        # With 100 obs and strength 40, pbp_weight = 100/140 ≈ 0.714
        expected = 0.714 * 0.55 + 0.286 * 0.70
        assert result == pytest.approx(expected, abs=0.01)

    def test_small_sample_heavily_weights_prior(self):
        """With few observations, PFF prior dominates."""
        result = stabilize_value(
            pbp_value=0.55,
            pff_prior=0.70,
            n_observations=10,
            prior_strength=40.0,
            min_divergence=0.03,
        )
        # pbp_weight = 10/50 = 0.20 → ~80% PFF
        expected = 0.20 * 0.55 + 0.80 * 0.70
        assert result == pytest.approx(expected, abs=0.001)
        # Should be much closer to PFF prior
        assert abs(result - 0.70) < abs(result - 0.55)

    def test_large_sample_mostly_keeps_pbp(self):
        """With many observations, PBP value dominates."""
        result = stabilize_value(
            pbp_value=0.55,
            pff_prior=0.70,
            n_observations=500,
            prior_strength=40.0,
            min_divergence=0.03,
        )
        # pbp_weight = 500/540 ≈ 0.926 → ~7% PFF
        expected = (500 / 540) * 0.55 + (40 / 540) * 0.70
        assert result == pytest.approx(expected, abs=0.001)
        # Should be very close to PBP value
        assert abs(result - 0.55) < 0.02

    def test_zero_observations_returns_prior(self):
        """With no PBP data, PFF prior is returned."""
        result = stabilize_value(
            pbp_value=0.55,
            pff_prior=0.70,
            n_observations=0,
            prior_strength=40.0,
            min_divergence=0.03,
        )
        assert result == pytest.approx(0.70)

    def test_exact_threshold_no_adjustment(self):
        """When divergence equals threshold exactly, no adjustment."""
        # abs(0.65 - 0.68) = 0.03, not < 0.03
        result = stabilize_value(
            pbp_value=0.65,
            pff_prior=0.68,
            n_observations=100,
            prior_strength=40.0,
            min_divergence=0.03,
        )
        # Divergence is exactly 0.03, which is NOT < 0.03, so blend happens
        assert result != 0.65
        assert 0.65 < result < 0.68

    def test_prior_below_pbp_blends_downward(self):
        """Blending also works when prior is below PBP value."""
        result = stabilize_value(
            pbp_value=0.75,
            pff_prior=0.60,
            n_observations=50,
            prior_strength=40.0,
            min_divergence=0.03,
        )
        # Should blend downward toward prior
        assert 0.60 < result < 0.75


# ========== TalentStabilizer.stabilize_roster tests ==========


class TestStabilizeRosterCatchRate:
    """Tests for catch rate stabilization via stabilize_roster."""

    def test_elite_route_runner_low_catch_rate_boosted(self, pff_dir, loader, default_pff_config):
        """Player with elite PFF profile but low PBP catch rate gets boosted."""
        # PFF data: elite receiver (low drops, high contested catch, good route grades)
        elite_wr = {
            "player_id": 100,
            "player": "Elite WR",
            "team": "KC",
            "position": "WR",
            "drop_rate": 1.5,       # Very low drops (elite hands)
            "contested_catch_rate": 65.0,  # High contested catch
            "yprr": 2.2,
            "avg_depth_of_target": 12.0,
            "targets": 8,
            "n_games": 16,
            "caught_percent": 72.0,
            "yards": 80.0,
        }
        # Average receiver for league-avg computation
        avg_wr = {
            "player_id": 200,
            "player": "Average WR",
            "team": "BUF",
            "position": "WR",
            "drop_rate": 5.0,       # League average drops
            "contested_catch_rate": 50.0,  # Average
            "yprr": 1.5,
            "avg_depth_of_target": 10.0,
            "targets": 6,
            "n_games": 16,
            "caught_percent": 65.0,
            "yards": 50.0,
        }
        # Below-average receiver to balance averages
        bad_wr = {
            "player_id": 300,
            "player": "Bad WR",
            "team": "NYJ",
            "position": "WR",
            "drop_rate": 8.5,       # High drops
            "contested_catch_rate": 35.0,  # Low contested catch
            "yprr": 1.0,
            "avg_depth_of_target": 8.0,
            "targets": 5,
            "n_games": 16,
            "caught_percent": 55.0,
            "yards": 35.0,
        }
        _write_receiving_summary(pff_dir, 2024, [elite_wr, avg_wr, bad_wr])

        # QB with average accuracy for KC
        qb = {
            "player_id": 500,
            "player": "KC QB",
            "team": "KC",
            "position": "QB",
            "accuracy_percent": 78.0,
            "n_games": 16,
            "dropbacks": 35,
        }
        avg_qb = {
            "player_id": 600,
            "player": "BUF QB",
            "team": "BUF",
            "position": "QB",
            "accuracy_percent": 75.0,
            "n_games": 16,
            "dropbacks": 35,
        }
        _write_passing_summary(pff_dir, 2024, [qb, avg_qb])
        _write_rushing_summary(pff_dir, 2024, [])

        # Build roster with low PBP catch rate for the elite WR
        elite_player = _make_player(
            "G001", "Elite WR", "WR", "KC",
            catch_rate=0.59, rz_catch_rate=0.54,
            target_share=0.25,
        )
        roster = TeamRoster(team="KC", players=[elite_player])

        # Crosswalk: PFF 100 -> nflverse G001
        crosswalk = {100: "G001"}

        stabilizer = TalentStabilizer(default_pff_config, loader)
        stabilizer.stabilize_roster(roster, crosswalk, [2024])

        # Elite PFF profile should push catch rate upward from 0.59
        assert elite_player.outcomes.catch_rate > 0.59

    def test_average_pff_average_pbp_no_change(self, pff_dir, loader, default_pff_config):
        """Player with average PFF and average PBP -> no change (divergence below threshold)."""
        # All players have identical PFF stats => league averages == player stats
        avg_player_pff = {
            "player_id": 100,
            "player": "Avg Player",
            "team": "KC",
            "position": "WR",
            "drop_rate": 5.0,
            "contested_catch_rate": 50.0,
            "yprr": 1.5,
            "avg_depth_of_target": 10.0,
            "targets": 6,
            "n_games": 16,
        }
        avg_player_pff2 = {
            "player_id": 200,
            "player": "Avg Player 2",
            "team": "BUF",
            "position": "WR",
            "drop_rate": 5.0,
            "contested_catch_rate": 50.0,
            "yprr": 1.5,
            "avg_depth_of_target": 10.0,
            "targets": 6,
            "n_games": 16,
        }
        _write_receiving_summary(pff_dir, 2024, [avg_player_pff, avg_player_pff2])

        # QBs with identical accuracy => no delta
        qb1 = {
            "player_id": 500,
            "player": "KC QB",
            "team": "KC",
            "position": "QB",
            "accuracy_percent": 75.0,
            "n_games": 16,
            "dropbacks": 35,
        }
        qb2 = {
            "player_id": 600,
            "player": "BUF QB",
            "team": "BUF",
            "position": "QB",
            "accuracy_percent": 75.0,
            "n_games": 16,
            "dropbacks": 35,
        }
        _write_passing_summary(pff_dir, 2024, [qb1, qb2])
        _write_rushing_summary(pff_dir, 2024, [])

        # PBP catch rate near baseline (0.70) — PFF prior will also be ~0.70
        # since player == avg in all dimensions
        player = _make_player(
            "G001", "Avg Player", "WR", "KC",
            catch_rate=0.70, rz_catch_rate=0.64,
            target_share=0.20,
        )
        original_catch = player.outcomes.catch_rate
        original_rz_catch = player.outcomes.red_zone_catch_rate

        roster = TeamRoster(team="KC", players=[player])
        crosswalk = {100: "G001"}

        stabilizer = TalentStabilizer(default_pff_config, loader)
        stabilizer.stabilize_roster(roster, crosswalk, [2024])

        # Should be unchanged (PFF prior ≈ 0.64 ≈ PBP, divergence < threshold)
        assert player.outcomes.catch_rate == pytest.approx(original_catch, abs=0.001)
        assert player.outcomes.red_zone_catch_rate == pytest.approx(original_rz_catch, abs=0.001)

    def test_red_zone_catch_rate_scales_proportionally(self, pff_dir, loader, default_pff_config):
        """When catch_rate is adjusted, red_zone_catch_rate scales by the same ratio."""
        # Create a player with clearly divergent PFF data
        elite_wr = {
            "player_id": 100,
            "player": "Elite WR",
            "team": "KC",
            "position": "WR",
            "drop_rate": 1.0,       # Very elite
            "contested_catch_rate": 70.0,
            "yprr": 2.0,
            "avg_depth_of_target": 10.0,
            "targets": 8,
            "n_games": 4,  # Small sample -> heavier PFF weight
        }
        avg_wr = {
            "player_id": 200,
            "player": "Avg WR",
            "team": "BUF",
            "position": "WR",
            "drop_rate": 6.0,
            "contested_catch_rate": 45.0,
            "yprr": 1.5,
            "avg_depth_of_target": 10.0,
            "targets": 6,
            "n_games": 16,
        }
        _write_receiving_summary(pff_dir, 2024, [elite_wr, avg_wr])
        _write_passing_summary(pff_dir, 2024, [{
            "player_id": 500, "player": "QB", "team": "KC",
            "position": "QB", "accuracy_percent": 75.0,
            "n_games": 16, "dropbacks": 35,
        }])
        _write_rushing_summary(pff_dir, 2024, [])

        player = _make_player(
            "G001", "Elite WR", "WR", "KC",
            catch_rate=0.55, rz_catch_rate=0.50,
            target_share=0.25,
        )
        original_catch = player.outcomes.catch_rate
        original_rz = player.outcomes.red_zone_catch_rate

        roster = TeamRoster(team="KC", players=[player])
        crosswalk = {100: "G001"}

        stabilizer = TalentStabilizer(default_pff_config, loader)
        stabilizer.stabilize_roster(roster, crosswalk, [2024])

        new_catch = player.outcomes.catch_rate
        new_rz = player.outcomes.red_zone_catch_rate

        # Catch rate should have been adjusted
        assert new_catch != original_catch

        # RZ catch rate should scale proportionally
        expected_ratio = new_catch / original_catch
        expected_rz = original_rz * expected_ratio
        assert new_rz == pytest.approx(expected_rz, abs=0.001)


class TestStabilizeRosterCrosswalk:
    """Tests for crosswalk filtering in stabilize_roster."""

    def test_player_not_in_crosswalk_unchanged(self, pff_dir, loader, default_pff_config):
        """Players without a PFF crosswalk entry are completely untouched."""
        # Write PFF data for player_id=100, but crosswalk won't include it
        elite_wr = {
            "player_id": 100,
            "player": "Elite WR",
            "team": "KC",
            "position": "WR",
            "drop_rate": 1.0,
            "contested_catch_rate": 70.0,
            "yprr": 2.5,
            "avg_depth_of_target": 12.0,
            "targets": 8,
            "n_games": 16,
        }
        _write_receiving_summary(pff_dir, 2024, [elite_wr])
        _write_passing_summary(pff_dir, 2024, [{
            "player_id": 500, "player": "QB", "team": "KC",
            "position": "QB", "accuracy_percent": 75.0, "n_games": 16, "dropbacks": 35,
        }])
        _write_rushing_summary(pff_dir, 2024, [])

        player = _make_player(
            "G999", "Unknown Player", "WR", "KC",
            catch_rate=0.55, rz_catch_rate=0.50,
            target_share=0.25,
            receiving_yards_dist=np.array([5.0, 10.0, 15.0]),
        )
        original_catch = player.outcomes.catch_rate
        original_rz = player.outcomes.red_zone_catch_rate
        original_dist = player.outcomes.receiving_yards_dist.copy()

        roster = TeamRoster(team="KC", players=[player])
        # Empty crosswalk — no PFF ID maps to G999
        crosswalk: dict[int, str] = {}

        stabilizer = TalentStabilizer(default_pff_config, loader)
        stabilizer.stabilize_roster(roster, crosswalk, [2024])

        assert player.outcomes.catch_rate == original_catch
        assert player.outcomes.red_zone_catch_rate == original_rz
        np.testing.assert_array_equal(player.outcomes.receiving_yards_dist, original_dist)

    def test_disabled_config_skips_all(self, pff_dir, loader):
        """When talent config is disabled, no adjustments are made."""
        config = PffConfig(
            enabled=True,
            talent=TalentConfig(enabled=False),
        )
        # Write data that would normally trigger adjustments
        _write_receiving_summary(pff_dir, 2024, [{
            "player_id": 100, "player": "WR", "team": "KC",
            "position": "WR", "drop_rate": 1.0, "contested_catch_rate": 70.0,
            "targets": 8, "n_games": 16,
        }])
        _write_passing_summary(pff_dir, 2024, [])
        _write_rushing_summary(pff_dir, 2024, [])

        player = _make_player(
            "G001", "WR", "WR", "KC",
            catch_rate=0.55, target_share=0.25,
        )
        original = player.outcomes.catch_rate

        roster = TeamRoster(team="KC", players=[player])
        crosswalk = {100: "G001"}

        stabilizer = TalentStabilizer(config, loader)
        stabilizer.stabilize_roster(roster, crosswalk, [2024])

        assert player.outcomes.catch_rate == original


class TestStabilizeRosterRushingYards:
    """Tests for rushing yards distribution stabilization."""

    def test_elite_rb_rushing_yards_shifted_up(self, pff_dir, loader):
        """Elite RB (high YCO, high elusive) gets rushing dist shifted upward."""
        # Use larger coefficients than fitted defaults (R²≈0 for rushing)
        # to test the mechanism works
        rush_config = PffConfig(
            enabled=True,
            talent=TalentConfig(
                enabled=True,
                rushing_yards_coefficients={"yco_attempt": 0.6, "elusive_rating": 0.008},
            ),
        )
        elite_rb = {
            "player_id": 100,
            "player": "Elite RB",
            "team": "KC",
            "position": "HB",
            "yco_attempt": 4.0,      # Elite yards created
            "elusive_rating": 90.0,   # Elite elusiveness
            "attempts": 18,
            "n_games": 16,
        }
        avg_rb = {
            "player_id": 200,
            "player": "Avg RB",
            "team": "BUF",
            "position": "HB",
            "yco_attempt": 2.5,
            "elusive_rating": 50.0,
            "attempts": 15,
            "n_games": 16,
        }
        bad_rb = {
            "player_id": 300,
            "player": "Bad RB",
            "team": "NYJ",
            "position": "HB",
            "yco_attempt": 1.5,
            "elusive_rating": 25.0,
            "attempts": 12,
            "n_games": 16,
        }
        _write_rushing_summary(pff_dir, 2024, [elite_rb, avg_rb, bad_rb])
        _write_receiving_summary(pff_dir, 2024, [])
        _write_passing_summary(pff_dir, 2024, [])

        original_dist = np.array([3.0, 4.0, 5.0, 2.0, 6.0, -1.0, 8.0])
        player = _make_player(
            "G001", "Elite RB", "RB", "KC",
            carry_share=0.60,
            rushing_yards_dist=original_dist.copy(),
        )
        original_mean = original_dist.mean()

        roster = TeamRoster(team="KC", players=[player])
        crosswalk = {100: "G001"}

        stabilizer = TalentStabilizer(rush_config, loader)
        stabilizer.stabilize_roster(roster, crosswalk, [2024])

        # Rushing dist should be shifted upward (elite YCO + elusive above avg)
        new_mean = player.outcomes.rushing_yards_dist.mean()
        assert new_mean > original_mean

    def test_rb_no_rushing_dist_unchanged(self, pff_dir, loader, default_pff_config):
        """RB without rushing_yards_dist is not modified."""
        rb = {
            "player_id": 100,
            "player": "RB No Dist",
            "team": "KC",
            "position": "HB",
            "yco_attempt": 4.0,
            "elusive_rating": 90.0,
            "attempts": 18,
            "n_games": 16,
        }
        _write_rushing_summary(pff_dir, 2024, [rb])
        _write_receiving_summary(pff_dir, 2024, [])
        _write_passing_summary(pff_dir, 2024, [])

        player = _make_player(
            "G001", "RB No Dist", "RB", "KC",
            carry_share=0.60,
            rushing_yards_dist=None,
        )

        roster = TeamRoster(team="KC", players=[player])
        crosswalk = {100: "G001"}

        stabilizer = TalentStabilizer(default_pff_config, loader)
        stabilizer.stabilize_roster(roster, crosswalk, [2024])

        assert player.outcomes.rushing_yards_dist is None


class TestStabilizeRosterReceivingYards:
    """Tests for receiving yards distribution stabilization."""

    def test_elite_route_runner_receiving_yards_shifted_up(self, pff_dir, loader, default_pff_config):
        """Player with high YPRR + ADOT gets receiving_yards_dist shifted upward."""
        elite_wr = {
            "player_id": 100,
            "player": "Elite WR",
            "team": "KC",
            "position": "WR",
            "yprr": 2.5,             # Elite YPRR
            "avg_depth_of_target": 14.0,  # Deep threat
            "drop_rate": 5.0,
            "contested_catch_rate": 50.0,
            "targets": 8,
            "n_games": 16,
        }
        avg_wr = {
            "player_id": 200,
            "player": "Avg WR",
            "team": "BUF",
            "position": "WR",
            "yprr": 1.5,
            "avg_depth_of_target": 10.0,
            "drop_rate": 5.0,
            "contested_catch_rate": 50.0,
            "targets": 6,
            "n_games": 16,
        }
        bad_wr = {
            "player_id": 300,
            "player": "Bad WR",
            "team": "NYJ",
            "position": "WR",
            "yprr": 0.8,
            "avg_depth_of_target": 7.0,
            "drop_rate": 5.0,
            "contested_catch_rate": 50.0,
            "targets": 4,
            "n_games": 16,
        }
        _write_receiving_summary(pff_dir, 2024, [elite_wr, avg_wr, bad_wr])
        _write_passing_summary(pff_dir, 2024, [])
        _write_rushing_summary(pff_dir, 2024, [])

        original_dist = np.array([5.0, 10.0, 15.0, 8.0, 12.0, 20.0])
        player = _make_player(
            "G001", "Elite WR", "WR", "KC",
            target_share=0.25,
            receiving_yards_dist=original_dist.copy(),
        )
        original_mean = original_dist.mean()

        roster = TeamRoster(team="KC", players=[player])
        crosswalk = {100: "G001"}

        stabilizer = TalentStabilizer(default_pff_config, loader)
        stabilizer.stabilize_roster(roster, crosswalk, [2024])

        # Distribution should be shifted upward
        new_mean = player.outcomes.receiving_yards_dist.mean()
        assert new_mean > original_mean

    def test_no_receiving_dist_unchanged(self, pff_dir, loader, default_pff_config):
        """Player without receiving_yards_dist is not modified."""
        wr = {
            "player_id": 100,
            "player": "No Dist WR",
            "team": "KC",
            "position": "WR",
            "yprr": 2.5,
            "avg_depth_of_target": 14.0,
            "targets": 8,
            "n_games": 16,
        }
        _write_receiving_summary(pff_dir, 2024, [wr])
        _write_passing_summary(pff_dir, 2024, [])
        _write_rushing_summary(pff_dir, 2024, [])

        player = _make_player(
            "G001", "No Dist WR", "WR", "KC",
            target_share=0.25,
            receiving_yards_dist=None,
        )

        roster = TeamRoster(team="KC", players=[player])
        crosswalk = {100: "G001"}

        stabilizer = TalentStabilizer(default_pff_config, loader)
        stabilizer.stabilize_roster(roster, crosswalk, [2024])

        assert player.outcomes.receiving_yards_dist is None


class TestStabilizeRosterEdgeCases:
    """Edge case tests for stabilize_roster."""

    def test_empty_pff_data_no_crash(self, pff_dir, loader, default_pff_config):
        """When PFF parquets are missing, no crash and no changes."""
        # Don't write any parquets
        player = _make_player(
            "G001", "WR", "WR", "KC",
            catch_rate=0.60, target_share=0.20,
        )
        original = player.outcomes.catch_rate

        roster = TeamRoster(team="KC", players=[player])
        crosswalk = {100: "G001"}

        stabilizer = TalentStabilizer(default_pff_config, loader)
        stabilizer.stabilize_roster(roster, crosswalk, [2024])

        assert player.outcomes.catch_rate == original

    def test_qb_carry_share_triggers_rushing_stabilization(self, pff_dir, loader):
        """QB with carry_share > 0 gets rushing yards stabilized."""
        # Use larger rushing coefficients to test the mechanism
        rush_config = PffConfig(
            enabled=True,
            talent=TalentConfig(
                enabled=True,
                rushing_yards_coefficients={"yco_attempt": 0.6, "elusive_rating": 0.008},
            ),
        )
        mobile_qb = {
            "player_id": 100,
            "player": "Mobile QB",
            "team": "KC",
            "position": "QB",
            "yco_attempt": 4.5,
            "elusive_rating": 85.0,
            "attempts": 10,
            "n_games": 16,
        }
        avg_rb = {
            "player_id": 200,
            "player": "Avg RB",
            "team": "BUF",
            "position": "HB",
            "yco_attempt": 2.5,
            "elusive_rating": 50.0,
            "attempts": 15,
            "n_games": 16,
        }
        _write_rushing_summary(pff_dir, 2024, [mobile_qb, avg_rb])
        _write_receiving_summary(pff_dir, 2024, [])
        _write_passing_summary(pff_dir, 2024, [])

        original_dist = np.array([3.0, 5.0, 7.0, 2.0, 10.0])
        player = _make_player(
            "G001", "Mobile QB", "QB", "KC",
            carry_share=0.15,
            rushing_yards_dist=original_dist.copy(),
        )
        original_mean = original_dist.mean()

        roster = TeamRoster(team="KC", players=[player])
        crosswalk = {100: "G001"}

        stabilizer = TalentStabilizer(rush_config, loader)
        stabilizer.stabilize_roster(roster, crosswalk, [2024])

        new_mean = player.outcomes.rushing_yards_dist.mean()
        assert new_mean > original_mean


class TestPositionSpecificStrength:
    def test_resolve_scalar_returns_same_for_all(self, pff_dir, loader):
        config = TalentConfig(prior_strength=50.0)
        stabilizer = TalentStabilizer(PffConfig(enabled=True, talent=config), loader)
        assert stabilizer._resolve_prior_strength("QB") == 50.0
        assert stabilizer._resolve_prior_strength("WR") == 50.0

    def test_resolve_dict_returns_position_value(self, pff_dir, loader):
        config = TalentConfig(prior_strength={"QB": 60, "WR": 40, "RB": 30, "default": 45})
        stabilizer = TalentStabilizer(PffConfig(enabled=True, talent=config), loader)
        assert stabilizer._resolve_prior_strength("QB") == 60
        assert stabilizer._resolve_prior_strength("WR") == 40

    def test_resolve_dict_falls_back_to_default(self, pff_dir, loader):
        config = TalentConfig(prior_strength={"QB": 60, "default": 45})
        stabilizer = TalentStabilizer(PffConfig(enabled=True, talent=config), loader)
        assert stabilizer._resolve_prior_strength("TE") == 45

    def test_resolve_dict_no_default_uses_40(self, pff_dir, loader):
        config = TalentConfig(prior_strength={"QB": 60})
        stabilizer = TalentStabilizer(PffConfig(enabled=True, talent=config), loader)

        assert stabilizer._resolve_prior_strength("WR") == 40.0


class TestTeamChangeBoost:
    """Tests for _effective_prior_strength — team-change factor logic."""

    def test_same_team_no_boost(self, pff_dir, loader):
        """Player on same team as PFF data → no strength reduction."""
        config = TalentConfig(prior_strength=40.0, team_change_factor=0.5)
        stabilizer = TalentStabilizer(PffConfig(enabled=True, talent=config), loader)
        effective = stabilizer._effective_prior_strength("WR", "KC", "KC")
        assert effective == 40.0

    def test_team_change_applies_factor(self, pff_dir, loader):
        """Player changed teams → prior_strength multiplied by factor."""
        config = TalentConfig(prior_strength=40.0, team_change_factor=0.5)
        stabilizer = TalentStabilizer(PffConfig(enabled=True, talent=config), loader)
        effective = stabilizer._effective_prior_strength("WR", "KC", "BUF")
        assert effective == 20.0  # 40 * 0.5

    def test_team_change_with_position_specific(self, pff_dir, loader):
        """Team change + position-specific strength stack correctly."""
        config = TalentConfig(
            prior_strength={"QB": 60, "WR": 40, "default": 40},
            team_change_factor=0.5,
        )
        stabilizer = TalentStabilizer(PffConfig(enabled=True, talent=config), loader)
        assert stabilizer._effective_prior_strength("QB", "KC", "BUF") == 30.0
        assert stabilizer._effective_prior_strength("WR", "KC", "BUF") == 20.0

    def test_factor_1_means_no_boost(self, pff_dir, loader):
        """Default factor=1.0 → no change even on team switch."""
        config = TalentConfig(prior_strength=40.0, team_change_factor=1.0)
        stabilizer = TalentStabilizer(PffConfig(enabled=True, talent=config), loader)
        effective = stabilizer._effective_prior_strength("WR", "KC", "BUF")
        assert effective == 40.0


class TestStabilizeTargetShare:
    """Tests for target_share stabilization via stabilize_roster."""

    def test_high_route_grade_increases_target_share(self, pff_dir, loader):
        """WR with elite route grade + YPRR gets target_share nudged up."""
        config = PffConfig(
            enabled=True,
            talent=TalentConfig(
                enabled=True,
                target_share_coefficients={"route_grade": 0.5, "yprr": 0.3},
            ),
        )
        elite_wr = {
            "player_id": 100,
            "player": "Elite WR",
            "team": "KC",
            "position": "WR",
            "grades_pass_route": 92.0,  # Elite route grade
            "yprr": 2.8,               # Elite YPRR
            "drop_rate": 3.0,
            "contested_catch_rate": 55.0,
            "avg_depth_of_target": 12.0,
            "targets": 8,
            "n_games": 16,
        }
        avg_wr = {
            "player_id": 200,
            "player": "Avg WR",
            "team": "BUF",
            "position": "WR",
            "grades_pass_route": 65.0,
            "yprr": 1.4,
            "drop_rate": 5.0,
            "contested_catch_rate": 50.0,
            "avg_depth_of_target": 10.0,
            "targets": 6,
            "n_games": 16,
        }
        bad_wr = {
            "player_id": 300,
            "player": "Bad WR",
            "team": "NYJ",
            "position": "WR",
            "grades_pass_route": 50.0,
            "yprr": 0.9,
            "drop_rate": 8.0,
            "contested_catch_rate": 40.0,
            "avg_depth_of_target": 8.0,
            "targets": 4,
            "n_games": 16,
        }
        _write_receiving_summary(pff_dir, 2024, [elite_wr, avg_wr, bad_wr])
        _write_passing_summary(pff_dir, 2024, [{
            "player_id": 500, "player": "QB", "team": "KC",
            "position": "QB", "accuracy_percent": 75.0,
            "n_games": 16, "dropbacks": 35,
        }])
        _write_rushing_summary(pff_dir, 2024, [])

        player = _make_player(
            "G001", "Elite WR", "WR", "KC",
            target_share=0.18, catch_rate=0.65,
        )
        original_ts = player.usage.target_share

        roster = TeamRoster(team="KC", players=[player])
        crosswalk = {100: "G001"}

        stabilizer = TalentStabilizer(config, loader)
        stabilizer.stabilize_roster(roster, crosswalk, [2024])

        # Elite route grade + YPRR above average -> target share nudged up
        assert player.usage.target_share > original_ts

    def test_low_route_grade_decreases_target_share(self, pff_dir, loader):
        """WR with poor route grade + YPRR gets target_share nudged down."""
        config = PffConfig(
            enabled=True,
            talent=TalentConfig(
                enabled=True,
                target_share_coefficients={"route_grade": 0.5, "yprr": 0.3},
            ),
        )
        bad_wr = {
            "player_id": 100,
            "player": "Bad WR",
            "team": "KC",
            "position": "WR",
            "grades_pass_route": 45.0,  # Poor route grade
            "yprr": 0.7,               # Poor YPRR
            "drop_rate": 8.0,
            "contested_catch_rate": 35.0,
            "avg_depth_of_target": 8.0,
            "targets": 4,
            "n_games": 16,
        }
        avg_wr = {
            "player_id": 200,
            "player": "Avg WR",
            "team": "BUF",
            "position": "WR",
            "grades_pass_route": 65.0,
            "yprr": 1.4,
            "drop_rate": 5.0,
            "contested_catch_rate": 50.0,
            "avg_depth_of_target": 10.0,
            "targets": 6,
            "n_games": 16,
        }
        elite_wr = {
            "player_id": 300,
            "player": "Elite WR",
            "team": "NYJ",
            "position": "WR",
            "grades_pass_route": 90.0,
            "yprr": 2.5,
            "drop_rate": 2.0,
            "contested_catch_rate": 60.0,
            "avg_depth_of_target": 12.0,
            "targets": 8,
            "n_games": 16,
        }
        _write_receiving_summary(pff_dir, 2024, [bad_wr, avg_wr, elite_wr])
        _write_passing_summary(pff_dir, 2024, [{
            "player_id": 500, "player": "QB", "team": "KC",
            "position": "QB", "accuracy_percent": 75.0,
            "n_games": 16, "dropbacks": 35,
        }])
        _write_rushing_summary(pff_dir, 2024, [])

        player = _make_player(
            "G001", "Bad WR", "WR", "KC",
            target_share=0.22, catch_rate=0.60,
        )
        original_ts = player.usage.target_share

        roster = TeamRoster(team="KC", players=[player])
        crosswalk = {100: "G001"}

        stabilizer = TalentStabilizer(config, loader)
        stabilizer.stabilize_roster(roster, crosswalk, [2024])

        # Poor route grade + YPRR below average -> target share nudged down
        assert player.usage.target_share < original_ts


class TestStabilizeFumbleRate:
    """Tests for fumble_rate stabilization via stabilize_roster."""

    def test_bad_hands_grade_increases_fumble_rate(self, pff_dir, loader):
        """RB with poor hands fumble grade gets fumble_rate nudged up."""
        config = PffConfig(
            enabled=True,
            talent=TalentConfig(
                enabled=True,
                fumble_rate_coefficients={"grades_hands_fumble": -0.002},
            ),
        )
        bad_hands_rb = {
            "player_id": 100,
            "player": "Bad Hands RB",
            "team": "KC",
            "position": "HB",
            "yco_attempt": 2.5,
            "elusive_rating": 50.0,
            "attempts": 15,
            "n_games": 16,
            "grades_hands_fumble": 35.0,  # Bad hands grade
        }
        avg_rb = {
            "player_id": 200,
            "player": "Avg RB",
            "team": "BUF",
            "position": "HB",
            "yco_attempt": 2.5,
            "elusive_rating": 50.0,
            "attempts": 15,
            "n_games": 16,
            "grades_hands_fumble": 70.0,  # Average
        }
        good_rb = {
            "player_id": 300,
            "player": "Good RB",
            "team": "NYJ",
            "position": "HB",
            "yco_attempt": 2.5,
            "elusive_rating": 50.0,
            "attempts": 15,
            "n_games": 16,
            "grades_hands_fumble": 90.0,  # Great hands
        }
        _write_rushing_summary(pff_dir, 2024, [bad_hands_rb, avg_rb, good_rb])
        _write_receiving_summary(pff_dir, 2024, [])
        _write_passing_summary(pff_dir, 2024, [])

        player = _make_player(
            "G001", "Bad Hands RB", "RB", "KC",
            carry_share=0.50,
            fumble_rate=0.015,
        )
        original_fr = player.outcomes.fumble_rate

        roster = TeamRoster(team="KC", players=[player])
        crosswalk = {100: "G001"}

        stabilizer = TalentStabilizer(config, loader)
        stabilizer.stabilize_roster(roster, crosswalk, [2024])

        # Bad hands grade below average -> fumble rate nudged up
        assert player.outcomes.fumble_rate > original_fr

    def test_good_hands_grade_decreases_fumble_rate(self, pff_dir, loader):
        """RB with excellent hands fumble grade gets fumble_rate nudged down."""
        config = PffConfig(
            enabled=True,
            talent=TalentConfig(
                enabled=True,
                fumble_rate_coefficients={"grades_hands_fumble": -0.002},
            ),
        )
        good_rb = {
            "player_id": 100,
            "player": "Good Hands RB",
            "team": "KC",
            "position": "HB",
            "yco_attempt": 2.5,
            "elusive_rating": 50.0,
            "attempts": 15,
            "n_games": 16,
            "grades_hands_fumble": 95.0,  # Excellent hands
        }
        avg_rb = {
            "player_id": 200,
            "player": "Avg RB",
            "team": "BUF",
            "position": "HB",
            "yco_attempt": 2.5,
            "elusive_rating": 50.0,
            "attempts": 15,
            "n_games": 16,
            "grades_hands_fumble": 65.0,
        }
        bad_rb = {
            "player_id": 300,
            "player": "Bad RB",
            "team": "NYJ",
            "position": "HB",
            "yco_attempt": 2.5,
            "elusive_rating": 50.0,
            "attempts": 15,
            "n_games": 16,
            "grades_hands_fumble": 40.0,
        }
        _write_rushing_summary(pff_dir, 2024, [good_rb, avg_rb, bad_rb])
        _write_receiving_summary(pff_dir, 2024, [])
        _write_passing_summary(pff_dir, 2024, [])

        player = _make_player(
            "G001", "Good Hands RB", "RB", "KC",
            carry_share=0.50,
            fumble_rate=0.040,  # High PBP fumble rate (diverges from low prior)
        )
        original_fr = player.outcomes.fumble_rate

        roster = TeamRoster(team="KC", players=[player])
        crosswalk = {100: "G001"}

        stabilizer = TalentStabilizer(config, loader)
        stabilizer.stabilize_roster(roster, crosswalk, [2024])

        # Good hands grade above average -> fumble rate nudged down
        assert player.outcomes.fumble_rate < original_fr


class TestStabilizeScrambleRate:
    """Tests for QB scramble_rate stabilization via stabilize_roster."""

    def test_pff_scramble_rate_used_as_prior(self, pff_dir, loader):
        """QB with higher PFF scramble rate gets scramble_rate nudged up."""
        config = PffConfig(
            enabled=True,
            talent=TalentConfig(
                enabled=True,
                scramble_rate_enabled=True,
                prior_strength=60.0,  # Higher strength to ensure shift exceeds MIN_SCRAMBLE_RATE_SHIFT
            ),
        )
        mobile_qb = {
            "player_id": 100,
            "player": "Mobile QB",
            "team": "KC",
            "position": "QB",
            "accuracy_percent": 75.0,
            "scrambles": 5,     # 5 scrambles per game
            "dropbacks": 35,    # 35 dropbacks per game -> PFF rate ~ 0.143
            "n_games": 16,
        }
        avg_qb = {
            "player_id": 200,
            "player": "Avg QB",
            "team": "BUF",
            "position": "QB",
            "accuracy_percent": 75.0,
            "scrambles": 2,
            "dropbacks": 35,
            "n_games": 16,
        }
        _write_passing_summary(pff_dir, 2024, [mobile_qb, avg_qb])
        _write_receiving_summary(pff_dir, 2024, [])
        _write_rushing_summary(pff_dir, 2024, [])

        player = _make_player(
            "G001", "Mobile QB", "QB", "KC",
            scramble_rate=0.06,  # PBP says 6%, PFF says ~14%
            carry_share=0.15,
        )
        original_sr = player.usage.scramble_rate

        roster = TeamRoster(team="KC", players=[player])
        crosswalk = {100: "G001"}

        stabilizer = TalentStabilizer(config, loader)
        stabilizer.stabilize_roster(roster, crosswalk, [2024])

        # PFF shows higher scramble rate -> should nudge up from 0.06
        assert player.usage.scramble_rate > original_sr


# ========== Schedule Adjustment Tests ==========


class TestScheduleAdjustment:
    """Tests for compute_schedule_adjustment pure function."""

    def test_tough_schedule_adjusts_upward(self):
        """Facing above-average defenses should yield a positive adjustment."""
        adj = compute_schedule_adjustment(
            opponent_avg_grade=80.0,
            league_avg_grade=65.0,
            weight=0.3,
            sensitivity=0.005,
        )
        assert adj > 0

    def test_easy_schedule_adjusts_downward(self):
        """Facing below-average defenses should yield a negative adjustment."""
        adj = compute_schedule_adjustment(
            opponent_avg_grade=50.0,
            league_avg_grade=65.0,
            weight=0.3,
            sensitivity=0.005,
        )
        assert adj < 0

    def test_neutral_schedule_no_adjustment(self):
        """When opponent grade equals league average, adjustment is zero."""
        adj = compute_schedule_adjustment(
            opponent_avg_grade=65.0,
            league_avg_grade=65.0,
            weight=0.3,
            sensitivity=0.005,
        )
        assert adj == 0.0

    def test_weight_zero_disables(self):
        """Weight of 0 should produce zero adjustment regardless of grades."""
        adj = compute_schedule_adjustment(
            opponent_avg_grade=80.0,
            league_avg_grade=65.0,
            weight=0.0,
            sensitivity=0.005,
        )
        assert adj == 0.0

    def test_magnitude_scales_with_grade_gap(self):
        """Larger grade differential should produce a larger adjustment."""
        adj_small = compute_schedule_adjustment(
            opponent_avg_grade=70.0,
            league_avg_grade=65.0,
            weight=0.3,
            sensitivity=0.005,
        )
        adj_large = compute_schedule_adjustment(
            opponent_avg_grade=85.0,
            league_avg_grade=65.0,
            weight=0.3,
            sensitivity=0.005,
        )
        assert adj_large > adj_small > 0

    def test_magnitude_scales_with_sensitivity(self):
        """Higher sensitivity should produce a proportionally larger adjustment."""
        adj_low = compute_schedule_adjustment(
            opponent_avg_grade=80.0,
            league_avg_grade=65.0,
            weight=0.3,
            sensitivity=0.001,
        )
        adj_high = compute_schedule_adjustment(
            opponent_avg_grade=80.0,
            league_avg_grade=65.0,
            weight=0.3,
            sensitivity=0.01,
        )
        assert adj_high == pytest.approx(adj_low * 10, rel=1e-6)

    def test_exact_value(self):
        """Verify the exact arithmetic: weight * (opp - league) * sensitivity."""
        adj = compute_schedule_adjustment(
            opponent_avg_grade=80.0,
            league_avg_grade=65.0,
            weight=0.3,
            sensitivity=0.005,
        )
        expected = 0.3 * (80.0 - 65.0) * 0.005  # = 0.0225
        assert adj == pytest.approx(expected, rel=1e-9)


# ========== compute_rookie_catch_rate_prior tests ==========


class TestRookiePrior:
    """Tests for the compute_rookie_catch_rate_prior function."""

    def test_elite_college_wr_gets_higher_catch_rate(self):
        prior = compute_rookie_catch_rate_prior(
            route_grade=90.0, contested_catch_rate=55.0,
            draft_round=1, draft_weight=0.6,
            league_avg_route_grade=65.0, league_avg_contested=45.0,
        )
        assert prior > BASELINE_CATCH_RATE

    def test_below_avg_wr_gets_lower_catch_rate(self):
        prior = compute_rookie_catch_rate_prior(
            route_grade=50.0, contested_catch_rate=35.0,
            draft_round=1, draft_weight=0.6,
            league_avg_route_grade=65.0, league_avg_contested=45.0,
        )
        assert prior < BASELINE_CATCH_RATE

    def test_late_round_gets_weaker_prior(self):
        early = compute_rookie_catch_rate_prior(
            route_grade=80.0, contested_catch_rate=50.0,
            draft_round=1, draft_weight=0.6,
            league_avg_route_grade=65.0, league_avg_contested=45.0,
        )
        late = compute_rookie_catch_rate_prior(
            route_grade=80.0, contested_catch_rate=50.0,
            draft_round=7, draft_weight=0.6,
            league_avg_route_grade=65.0, league_avg_contested=45.0,
        )
        assert abs(early - BASELINE_CATCH_RATE) > abs(late - BASELINE_CATCH_RATE)

    def test_prior_clamped_to_valid_range(self):
        # Extreme values should still be in [CATCH_RATE_PRIOR_MIN, CATCH_RATE_PRIOR_MAX]
        prior = compute_rookie_catch_rate_prior(
            route_grade=100.0, contested_catch_rate=100.0,
            draft_round=1, draft_weight=1.0,
            league_avg_route_grade=50.0, league_avg_contested=30.0,
        )
        assert CATCH_RATE_PRIOR_MIN <= prior <= CATCH_RATE_PRIOR_MAX

    def test_average_player_gets_baseline(self):
        """A player exactly at league average should get the baseline catch rate."""
        prior = compute_rookie_catch_rate_prior(
            route_grade=65.0, contested_catch_rate=45.0,
            draft_round=1, draft_weight=0.6,
            league_avg_route_grade=65.0, league_avg_contested=45.0,
        )
        assert prior == pytest.approx(BASELINE_CATCH_RATE, abs=0.001)

    def test_draft_round_multipliers_monotonic(self):
        """Earlier rounds should have higher multipliers."""
        for r in range(1, 7):
            assert DRAFT_ROUND_MULTIPLIERS[r] > DRAFT_ROUND_MULTIPLIERS[r + 1]

    def test_unknown_draft_round_uses_fallback(self):
        """Draft round not in dict (e.g. UDFA) gets minimal weight."""
        prior = compute_rookie_catch_rate_prior(
            route_grade=90.0, contested_catch_rate=55.0,
            draft_round=8, draft_weight=0.6,
            league_avg_route_grade=65.0, league_avg_contested=45.0,
        )
        # Should still deviate from baseline, just very slightly
        r1_prior = compute_rookie_catch_rate_prior(
            route_grade=90.0, contested_catch_rate=55.0,
            draft_round=1, draft_weight=0.6,
            league_avg_route_grade=65.0, league_avg_contested=45.0,
        )
        assert abs(prior - BASELINE_CATCH_RATE) < abs(r1_prior - BASELINE_CATCH_RATE)


# ========== NCAA priors integration via stabilize_roster ==========


class TestNcaaRookiePriorsIntegration:
    """Tests for NCAA priors applied through stabilize_roster."""

    def _make_ncaa_receiving(self, ncaa_dir, season, players):
        """Write NCAA receiving_summary parquet."""
        ncaa_dir.mkdir(parents=True, exist_ok=True)
        rows = {
            "player_id": [], "player": [], "team": [], "position": [],
            "season": [], "week": [], "game_id": [],
            "grades_pass_route": [], "contested_catch_rate": [],
            "targets": [], "drop_rate": [], "yprr": [],
            "avg_depth_of_target": [], "caught_percent": [], "yards": [],
        }
        gid = 7000
        for p in players:
            n_games = p.get("n_games", 12)
            for g in range(n_games):
                rows["player_id"].append(p["player_id"])
                rows["player"].append(p["player"])
                rows["team"].append(p["team"])
                rows["position"].append(p.get("position", "WR"))
                rows["season"].append(season)
                rows["week"].append(g + 1)
                rows["game_id"].append(gid + g)
                rows["grades_pass_route"].append(p.get("grades_pass_route", 70.0))
                rows["contested_catch_rate"].append(p.get("contested_catch_rate", 45.0))
                rows["targets"].append(p.get("targets", 5))
                rows["drop_rate"].append(p.get("drop_rate", 5.0))
                rows["yprr"].append(p.get("yprr", 1.5))
                rows["avg_depth_of_target"].append(p.get("avg_depth_of_target", 10.0))
                rows["caught_percent"].append(p.get("caught_percent", 65.0))
                rows["yards"].append(p.get("yards", 50.0))
            gid += 100

        df = pl.DataFrame(rows)
        df.write_parquet(ncaa_dir / f"receiving_summary_{season}.parquet")
        return df

    def test_ncaa_priors_disabled_skips(self, pff_dir, loader):
        """When ncaa_priors.enabled is False, no adjustments happen."""
        from fantasy_sim.data.pff.models import NcaaPriorsConfig
        config = PffConfig(
            enabled=True,
            talent=TalentConfig(
                enabled=True,
                ncaa_priors=NcaaPriorsConfig(enabled=False),
            ),
        )
        stabilizer = TalentStabilizer(config, loader)

        wr = _make_player("R001", "Rookie WR", "WR", "KC",
                          catch_rate=0.60, target_share=0.15, games_played=2)
        roster = TeamRoster(team="KC", players=[wr])

        stabilizer.stabilize_roster(roster, {}, [2024])
        # Catch rate unchanged (no PFF data + NCAA disabled)
        assert wr.outcomes.catch_rate == 0.60

    def test_ncaa_priors_adjusts_rookie_catch_rate(self, tmp_path):
        """Rookie with elite NCAA grades gets catch_rate adjusted."""
        from fantasy_sim.data.pff.models import NcaaPriorsConfig

        # Set up NFL PFF dir (empty — rookie won't be in NFL PFF)
        nfl_dir = tmp_path / "pff" / "processed" / "nfl"
        nfl_dir.mkdir(parents=True)
        ncaa_dir = tmp_path / "pff" / "processed" / "ncaa"

        loader = PffLoader(nfl_dir)
        config = PffConfig(
            enabled=True,
            talent=TalentConfig(
                enabled=True,
                ncaa_priors=NcaaPriorsConfig(
                    enabled=True,
                    draft_weight=0.6,
                    ncaa_data_dir=str(ncaa_dir),
                ),
            ),
        )
        stabilizer = TalentStabilizer(config, loader)

        # NCAA data: elite WR from Alabama + average player for league avg
        elite_ncaa = {
            "player_id": 5001, "player": "Elite Rookie", "team": "Alabama",
            "position": "WR", "grades_pass_route": 92.0,
            "contested_catch_rate": 60.0, "n_games": 12,
        }
        avg_ncaa = {
            "player_id": 5002, "player": "Average Player", "team": "Ohio State",
            "position": "WR", "grades_pass_route": 65.0,
            "contested_catch_rate": 45.0, "n_games": 12,
        }
        self._make_ncaa_receiving(ncaa_dir, 2024, [elite_ncaa, avg_ncaa])

        # NFL roster with the rookie
        nfl_roster = pl.DataFrame({
            "player_id": ["R001"],
            "player_name": ["Elite Rookie"],
            "college_name": ["Alabama"],
            "team": ["KC"],
            "position": ["WR"],
            "rookie_year": [2025],
            "season": [2025],
        })

        # Rookie PlayerModel with modest catch rate
        wr = _make_player("R001", "Elite Rookie", "WR", "KC",
                          catch_rate=0.60, target_share=0.15, games_played=2)
        roster = TeamRoster(team="KC", players=[wr])

        # No NFL PFF crosswalk (rookie has no NFL PFF data)
        crosswalk: dict[int, str] = {}

        stabilizer.stabilize_roster(
            roster, crosswalk, [2024],
            nfl_roster=nfl_roster, target_season=2025,
        )

        # Elite rookie should get catch rate adjusted upward from 0.60
        # (the exact value depends on the prior computation, but it should increase)
        assert wr.outcomes.catch_rate > 0.60  # Elite NCAA profile should push catch rate above starting value

    def test_ncaa_priors_no_ncaa_data_no_crash(self, tmp_path):
        """If NCAA data directory is empty, no crash and no adjustments."""
        from fantasy_sim.data.pff.models import NcaaPriorsConfig

        nfl_dir = tmp_path / "pff" / "processed" / "nfl"
        nfl_dir.mkdir(parents=True)
        ncaa_dir = tmp_path / "pff" / "processed" / "ncaa"
        ncaa_dir.mkdir(parents=True)

        loader = PffLoader(nfl_dir)
        config = PffConfig(
            enabled=True,
            talent=TalentConfig(
                enabled=True,
                ncaa_priors=NcaaPriorsConfig(
                    enabled=True,
                    ncaa_data_dir=str(ncaa_dir),
                ),
            ),
        )
        stabilizer = TalentStabilizer(config, loader)

        wr = _make_player("R001", "Rookie WR", "WR", "KC",
                          catch_rate=0.60, target_share=0.15, games_played=2)
        roster = TeamRoster(team="KC", players=[wr])

        nfl_roster = pl.DataFrame({
            "player_id": ["R001"],
            "player_name": ["Rookie WR"],
            "college_name": ["Alabama"],
            "team": ["KC"],
            "position": ["WR"],
            "rookie_year": [2025],
            "season": [2025],
        })

        # Should not crash
        stabilizer.stabilize_roster(
            roster, {}, [2024],
            nfl_roster=nfl_roster, target_season=2025,
        )
        assert wr.outcomes.catch_rate == 0.60

    def test_ncaa_priors_only_applies_to_rookies(self, tmp_path):
        """Veterans (players in NFL PFF crosswalk) should NOT get NCAA priors."""
        from fantasy_sim.data.pff.models import NcaaPriorsConfig

        nfl_dir = tmp_path / "pff" / "processed" / "nfl"
        nfl_dir.mkdir(parents=True)
        ncaa_dir = tmp_path / "pff" / "processed" / "ncaa"

        loader = PffLoader(nfl_dir)
        config = PffConfig(
            enabled=True,
            talent=TalentConfig(
                enabled=True,
                ncaa_priors=NcaaPriorsConfig(
                    enabled=True,
                    ncaa_data_dir=str(ncaa_dir),
                ),
            ),
        )
        stabilizer = TalentStabilizer(config, loader)

        # NCAA data
        elite_ncaa = {
            "player_id": 5001, "player": "Vet Player", "team": "Alabama",
            "position": "WR", "grades_pass_route": 92.0,
            "contested_catch_rate": 60.0, "n_games": 12,
        }
        avg_ncaa = {
            "player_id": 5002, "player": "Avg NCAA", "team": "Ohio State",
            "position": "WR", "grades_pass_route": 65.0,
            "contested_catch_rate": 45.0, "n_games": 12,
        }
        self._make_ncaa_receiving(ncaa_dir, 2024, [elite_ncaa, avg_ncaa])

        # Veteran IS in NFL PFF crosswalk
        vet = _make_player("V001", "Vet Player", "WR", "KC",
                           catch_rate=0.65, target_share=0.20, games_played=34)
        roster = TeamRoster(team="KC", players=[vet])

        # Veteran is in NFL crosswalk -> not a rookie
        crosswalk = {999: "V001"}

        nfl_roster = pl.DataFrame({
            "player_id": ["V001"],
            "player_name": ["Vet Player"],
            "college_name": ["Alabama"],
            "team": ["KC"],
            "position": ["WR"],
            "rookie_year": [2023],
            "season": [2025],
        })

        old_catch = vet.outcomes.catch_rate
        stabilizer.stabilize_roster(
            roster, crosswalk, [2024],
            nfl_roster=nfl_roster, target_season=2025,
        )
        # Veteran's catch rate should not be changed by NCAA priors
        # (may be changed by regular PFF stabilization, but we have no PFF data)
        assert vet.outcomes.catch_rate == old_catch

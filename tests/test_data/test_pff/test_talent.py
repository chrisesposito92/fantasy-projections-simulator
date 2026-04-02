"""Tests for PFF talent stabilizer — Bayesian blending with PFF priors."""

import numpy as np
import polars as pl
import pytest

from fantasy_sim.data.pff.loader import PffLoader
from fantasy_sim.data.pff.models import PffConfig, TalentConfig
from fantasy_sim.data.pff.talent import (
    BASELINE_CATCH_RATE,
    CATCH_RATE_PRIOR_MAX,
    CATCH_RATE_PRIOR_MIN,
    MIN_RECEIVING_YARDS_SHIFT,
    MIN_RUSHING_YARDS_SHIFT,
    TalentStabilizer,
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
        ),
        outcomes=PlayerOutcomes(
            catch_rate=catch_rate,
            red_zone_catch_rate=rz_catch_rate,
            receiving_yards_dist=receiving_yards_dist,
            rushing_yards_dist=rushing_yards_dist,
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

        # PBP catch rate near baseline (0.64) — PFF prior will also be ~0.64
        # since player == avg in all dimensions
        player = _make_player(
            "G001", "Avg Player", "WR", "KC",
            catch_rate=0.64, rz_catch_rate=0.59,
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

    def test_elite_rb_rushing_yards_shifted_up(self, pff_dir, loader, default_pff_config):
        """Elite RB (high YCO, high elusive) gets rushing dist shifted upward."""
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

        stabilizer = TalentStabilizer(default_pff_config, loader)
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

    def test_qb_carry_share_triggers_rushing_stabilization(self, pff_dir, loader, default_pff_config):
        """QB with carry_share > 0 gets rushing yards stabilized."""
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

        stabilizer = TalentStabilizer(default_pff_config, loader)
        stabilizer.stabilize_roster(roster, crosswalk, [2024])

        new_mean = player.outcomes.rushing_yards_dist.mean()
        assert new_mean > original_mean

"""Tests for PFF DST baseline engine — fumble rate + defensive TD rates."""

import numpy as np
import polars as pl
import pytest

from fantasy_sim.data.pff.loader import PffLoader
from fantasy_sim.data.pff.models import DstBaselineConfig, DstBaselineContext, PffConfig


class TestDstBaselineConfig:
    def test_default_values(self):
        cfg = DstBaselineConfig()
        assert cfg.enabled is True
        assert cfg.prior_strength == 10
        assert cfg.min_games == 4
        assert cfg.clamp == [0.85, 1.15]
        assert cfg.sensitivities == {"fumble_rate": 0.06}

    def test_pff_config_has_dst_baseline(self):
        pff = PffConfig()
        assert hasattr(pff, "dst_baseline")
        assert isinstance(pff.dst_baseline, DstBaselineConfig)


class TestDstBaselineContext:
    def test_default_neutral(self):
        ctx = DstBaselineContext()
        assert ctx.fumble_rate_factor == 1.0
        assert ctx.int_return_td_rate == 0.20
        assert ctx.fumble_return_td_rate == 0.10


from fantasy_sim.engine.types import DefensiveTdRates, TeamDistributions


class TestDefensiveTdRates:
    def test_default_matches_constants(self):
        rates = DefensiveTdRates()
        assert rates.int_return_td_rate == 0.20
        assert rates.fumble_return_td_rate == 0.10

    def test_team_distributions_has_defensive_td_rates(self):
        from fantasy_sim.models.distributions import (
            PlayCallingDist, PlayOutcomeDist, TurnoverRates, KickingModel, DriveStartModel,
        )
        dists = TeamDistributions(
            play_calling=PlayCallingDist(team="TST", distributions={}, default={"pass": 0.5, "run": 0.5}),
            play_outcomes=PlayOutcomeDist(distributions={}),
            turnover_rates=TurnoverRates(team="TST", int_rate=0.025, fumble_rate=0.012, sack_rate=0.065, sack_fumble_rate=0.10),
            kicking=KickingModel(fg_make_rate={"0_39": 0.90, "40_49": 0.84, "50_plus": 0.67}, xp_rate=0.95),
            drive_start=DriveStartModel(touchback_rate=0.6, touchback_yardline=75, return_yardlines=np.array([75])),
        )
        assert hasattr(dists, "defensive_td_rates")
        assert dists.defensive_td_rates.int_return_td_rate == 0.20
        assert dists.defensive_td_rates.fumble_return_td_rate == 0.10


# ---------- Helpers for DstBaselineEngine tests ----------


def _write_defense_summary(pff_dir, season, teams):
    """Write a defense_summary parquet for the given season and teams.

    Each entry in ``teams`` is a dict with:
        team (str), n_games (int), forced_fumbles (int, per game for player 0),
        fumble_recoveries (int, per game), fumble_recovery_touchdowns (int, per game),
        interceptions (int, per game), interception_touchdowns (int, per game),
        snap_counts_defense (int, per player per game — default 30),
        n_players (int — default 3).
    """
    rows = []
    player_counter = 1000

    for team_spec in teams:
        team = team_spec["team"]
        n_games = team_spec["n_games"]
        n_players = team_spec.get("n_players", 3)
        snaps_per = team_spec.get("snap_counts_defense", 30)

        for g in range(n_games):
            week = g + 1
            game_id = hash((team, week)) % 100000 + 100000

            for p_idx in range(n_players):
                pid = player_counter
                player_counter += 1

                # Counting stats only go to first player per game to avoid
                # double-counting at the team level (one player "causes" the event)
                if p_idx == 0:
                    ff = team_spec.get("forced_fumbles", 0)
                    fum_rec = team_spec.get("fumble_recoveries", 0)
                    fum_td = team_spec.get("fumble_recovery_touchdowns", 0)
                    ints = team_spec.get("interceptions", 0)
                    int_td = team_spec.get("interception_touchdowns", 0)
                else:
                    ff = fum_rec = fum_td = ints = int_td = 0

                rows.append({
                    "player_id": pid,
                    "player": f"Player_{pid}",
                    "team": team,
                    "position": "CB",
                    "season": season,
                    "week": week,
                    "game_id": game_id,
                    "forced_fumbles": ff,
                    "fumble_recoveries": fum_rec,
                    "fumble_recovery_touchdowns": fum_td,
                    "interceptions": ints,
                    "interception_touchdowns": int_td,
                    "snap_counts_defense": snaps_per,
                    # Grade columns — fill with 60.0 as neutral
                    "grades_defense": 60.0,
                    "grades_pass_rush_defense": 60.0,
                    "grades_run_defense": 60.0,
                    "grades_coverage_defense": 60.0,
                    "grades_tackle": 60.0,
                })

    schema = {
        "player_id": pl.Int64,
        "player": pl.Utf8,
        "team": pl.Utf8,
        "position": pl.Utf8,
        "season": pl.Int64,
        "week": pl.Int64,
        "game_id": pl.Int64,
        "forced_fumbles": pl.Int64,
        "fumble_recoveries": pl.Int64,
        "fumble_recovery_touchdowns": pl.Int64,
        "interceptions": pl.Int64,
        "interception_touchdowns": pl.Int64,
        "snap_counts_defense": pl.Int64,
        "grades_defense": pl.Float64,
        "grades_pass_rush_defense": pl.Float64,
        "grades_run_defense": pl.Float64,
        "grades_coverage_defense": pl.Float64,
        "grades_tackle": pl.Float64,
    }

    if rows:
        df = pl.DataFrame(rows, schema=schema, infer_schema_length=None)
    else:
        df = pl.DataFrame(schema=schema)

    path = pff_dir / f"defense_summary_{season}.parquet"
    df.write_parquet(path)
    return path


# ---------- Fixtures for DstBaselineEngine tests ----------


@pytest.fixture
def pff_dir(tmp_path):
    d = tmp_path / "pff" / "processed" / "nfl"
    d.mkdir(parents=True)
    return d


@pytest.fixture
def loader(pff_dir):
    return PffLoader(pff_dir)


@pytest.fixture
def default_config():
    return DstBaselineConfig()


# ---------- TestDstBaselineFumbleRate ----------


class TestDstBaselineFumbleRate:
    """Tests for the fumble_rate_factor computation."""

    def test_elite_defense_higher_fumble_factor(self, pff_dir, loader, default_config):
        """Team with 3 forced fumbles per game gets factor > 1.0."""
        from fantasy_sim.data.pff.dst_baseline import DstBaselineEngine

        _write_defense_summary(pff_dir, 2024, [
            {"team": "KC",  "n_games": 8, "forced_fumbles": 3},
            {"team": "BUF", "n_games": 8, "forced_fumbles": 1},
            {"team": "DAL", "n_games": 8, "forced_fumbles": 0},
        ])

        engine = DstBaselineEngine(default_config, loader, [2024])
        ctx = engine.compute("KC", 2024, max_week=9)
        assert ctx.fumble_rate_factor > 1.0

    def test_weak_defense_lower_fumble_factor(self, pff_dir, loader, default_config):
        """Team with 0 forced fumbles per game gets factor < 1.0."""
        from fantasy_sim.data.pff.dst_baseline import DstBaselineEngine

        _write_defense_summary(pff_dir, 2024, [
            {"team": "KC",  "n_games": 8, "forced_fumbles": 3},
            {"team": "BUF", "n_games": 8, "forced_fumbles": 1},
            {"team": "DAL", "n_games": 8, "forced_fumbles": 0},
        ])

        engine = DstBaselineEngine(default_config, loader, [2024])
        ctx = engine.compute("DAL", 2024, max_week=9)
        assert ctx.fumble_rate_factor < 1.0

    def test_clamp_enforcement(self, pff_dir, loader):
        """Very high sensitivity clamps factor to configured bounds."""
        from fantasy_sim.data.pff.dst_baseline import DstBaselineEngine

        cfg = DstBaselineConfig(sensitivities={"fumble_rate": 100.0}, clamp=[0.85, 1.15])
        _write_defense_summary(pff_dir, 2024, [
            {"team": "KC",  "n_games": 8, "forced_fumbles": 10},
            {"team": "BUF", "n_games": 8, "forced_fumbles": 0},
        ])

        engine = DstBaselineEngine(cfg, loader, [2024])
        ctx_high = engine.compute("KC",  2024, max_week=9)
        ctx_low  = engine.compute("BUF", 2024, max_week=9)

        assert ctx_high.fumble_rate_factor <= 1.15
        assert ctx_low.fumble_rate_factor  >= 0.85


# ---------- TestDstBaselineDefensiveTdRates ----------


class TestDstBaselineDefensiveTdRates:
    """Tests for int_return_td_rate and fumble_return_td_rate computations."""

    def test_high_pick_six_team(self, pff_dir, loader, default_config):
        """Team with many INT TDs should get rate > 0.20."""
        from fantasy_sim.data.pff.dst_baseline import DstBaselineEngine

        _write_defense_summary(pff_dir, 2024, [
            # 3 INTs, 2 INT-TDs per game over 8 games → very high pick-six rate
            {"team": "KC",  "n_games": 8, "interceptions": 3, "interception_touchdowns": 2},
            {"team": "BUF", "n_games": 8, "interceptions": 2, "interception_touchdowns": 0},
        ])

        engine = DstBaselineEngine(default_config, loader, [2024])
        ctx = engine.compute("KC", 2024, max_week=9)
        assert ctx.int_return_td_rate > 0.20

    def test_shrinkage_prevents_extreme_rates(self, pff_dir, loader, default_config):
        """1 INT / 1 pick-six should not produce a 100% rate — prior pulls it down."""
        from fantasy_sim.data.pff.dst_baseline import DstBaselineEngine

        _write_defense_summary(pff_dir, 2024, [
            {"team": "KC", "n_games": 1, "interceptions": 1, "interception_touchdowns": 1},
        ])

        engine = DstBaselineEngine(default_config, loader, [2024])
        ctx = engine.compute("KC", 2024, max_week=2)
        assert ctx.int_return_td_rate < 1.0
        assert ctx.int_return_td_rate > 0.20  # pulled up from prior but not extreme

    def test_no_turnovers_returns_default_rates(self, pff_dir, loader, default_config):
        """Team with 0 INTs and 0 fumble recs returns exactly the prior rates."""
        from fantasy_sim.data.pff.dst_baseline import DstBaselineEngine

        _write_defense_summary(pff_dir, 2024, [
            {"team": "KC", "n_games": 8,
             "interceptions": 0, "interception_touchdowns": 0,
             "fumble_recoveries": 0, "fumble_recovery_touchdowns": 0},
        ])

        engine = DstBaselineEngine(default_config, loader, [2024])
        ctx = engine.compute("KC", 2024, max_week=9)

        # With 0 events, Bayesian formula collapses to the prior mean exactly
        assert abs(ctx.int_return_td_rate - 0.20) < 1e-9
        assert abs(ctx.fumble_return_td_rate - 0.10) < 1e-9

    def test_no_data_returns_neutral(self, pff_dir, loader, default_config):
        """Missing parquet → DstBaselineContext with all defaults."""
        from fantasy_sim.data.pff.dst_baseline import DstBaselineEngine

        # Write nothing — no parquet files exist
        engine = DstBaselineEngine(default_config, loader, [2024])
        ctx = engine.compute("KC", 2024, max_week=9)

        assert ctx.fumble_rate_factor == 1.0
        assert ctx.int_return_td_rate == 0.20
        assert ctx.fumble_return_td_rate == 0.10

    def test_unknown_team_returns_neutral(self, pff_dir, loader, default_config):
        """Team not present in parquet → factor=1.0, rates at defaults."""
        from fantasy_sim.data.pff.dst_baseline import DstBaselineEngine

        _write_defense_summary(pff_dir, 2024, [
            {"team": "KC",  "n_games": 8, "interceptions": 3, "interception_touchdowns": 1},
            {"team": "BUF", "n_games": 8, "interceptions": 2, "interception_touchdowns": 0},
        ])

        engine = DstBaselineEngine(default_config, loader, [2024])
        ctx = engine.compute("XYZ", 2024, max_week=9)

        assert ctx.fumble_rate_factor == 1.0
        assert abs(ctx.int_return_td_rate - 0.20) < 1e-9
        assert abs(ctx.fumble_return_td_rate - 0.10) < 1e-9

    def test_early_season_blend_with_previous(self, pff_dir, loader):
        """< min_games in current season → previous-season data blended in."""
        from fantasy_sim.data.pff.dst_baseline import DstBaselineEngine

        cfg = DstBaselineConfig(min_games=4, prior_strength=10)

        # 2023: KC had many pick-sixes (pulls rate up sharply)
        _write_defense_summary(pff_dir, 2023, [
            {"team": "KC", "n_games": 16,
             "interceptions": 3, "interception_touchdowns": 3},
        ])
        # 2024: only 2 games played so far, no pick-sixes
        _write_defense_summary(pff_dir, 2024, [
            {"team": "KC", "n_games": 2,
             "interceptions": 1, "interception_touchdowns": 0},
        ])

        engine = DstBaselineEngine(cfg, loader, [2023, 2024])
        ctx = engine.compute("KC", 2024, max_week=3)

        # With only 2 games, strong 2023 signal should pull rate above prior 0.20
        assert ctx.int_return_td_rate > 0.20

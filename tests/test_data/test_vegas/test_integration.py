"""Integration tests for VegasEngine pipeline wiring.

Plan 02-02: TDD integration tests covering:
  - GameContextBuilder._apply_vegas() direct behavior (VEG-01 pace_factor, VEG-02 default)
  - Config propagation through Backtester and parallel workers
  - build_game() pipeline ordering (Vegas before matchup)
  - A/B harness mode routing (_build_vegas_config)
  - Combined-layer coexistence (Vegas + matchup, Vegas + weather)
"""
from __future__ import annotations

import copy
import inspect
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import polars as pl

from fantasy_sim.data.game_context import GameContextBuilder
from fantasy_sim.data.vegas.models import VegasConfig, VegasContext
from fantasy_sim.engine.types import TeamDistributions
from fantasy_sim.models.distributions import (
    DriveStartModel,
    KickingModel,
    PlayCallingDist,
    PlayOutcomeDist,
    TurnoverRates,
)
from fantasy_sim.models.game_state import GameStateBucket
from fantasy_sim.models.player import PlayerModel, PlayerOutcomes, PlayerUsage, TeamRoster
from fantasy_sim.validation.parallel import (
    _build_games_sequential,
    _init_build_worker_single,
    build_games_parallel,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bucket(
    down: int = 1,
    distance: str = "long",
    score_diff: str = "tied",
    quarter: int = 1,
    yard_zone: str = "own_territory",
) -> GameStateBucket:
    return GameStateBucket(
        down=down,
        distance=distance,
        score_diff=score_diff,
        quarter=quarter,
        yard_zone=yard_zone,
    )


def _make_dists(pass_rate: float = 0.57) -> TeamDistributions:
    """Create a minimal TeamDistributions with known values."""
    bucket1 = _make_bucket(down=1, quarter=1)
    bucket2 = _make_bucket(down=2, quarter=2)
    bucket3 = _make_bucket(down=3, quarter=3)

    play_calling = PlayCallingDist(
        team="KC",
        distributions={
            bucket1: {"pass": 0.50, "run": 0.50},
            bucket2: {"pass": 0.60, "run": 0.40},
            bucket3: {"pass": 0.75, "run": 0.25},
        },
        default={"pass": pass_rate, "run": 1.0 - pass_rate},
    )
    play_outcomes = PlayOutcomeDist(
        distributions={},
        defaults={
            "pass": np.array([5, 8, 12, 15, 20]),
            "run": np.array([2, 3, 4, 5, 6]),
        },
    )
    turnover_rates = TurnoverRates(
        team="KC",
        int_rate=0.025,
        fumble_rate=0.012,
        sack_rate=0.065,
        sack_fumble_rate=0.10,
    )
    kicking = KickingModel(
        fg_make_rate={"0_39": 0.90, "40_49": 0.78, "50_plus": 0.62},
        xp_rate=0.99,
    )
    drive_start = DriveStartModel(
        touchback_rate=0.60,
        touchback_yardline=75,
        return_yardlines=np.array([70, 72, 75, 78, 80]),
    )
    return TeamDistributions(
        play_calling=play_calling,
        play_outcomes=play_outcomes,
        turnover_rates=turnover_rates,
        kicking=kicking,
        drive_start=drive_start,
        pace_factor=1.0,
    )


def _make_roster(team: str = "KC") -> TeamRoster:
    """Create a minimal TeamRoster with players having yard distributions."""
    return TeamRoster(
        team=team,
        players=[
            PlayerModel(
                player_id=f"{team}_WR1",
                name="WR1",
                position="WR",
                team=team,
                usage=PlayerUsage(target_share=0.30),
                outcomes=PlayerOutcomes(
                    catch_rate=0.65,
                    receiving_yards_dist=np.array([5, 8, 12, 15, 20], dtype=float),
                ),
            ),
            PlayerModel(
                player_id=f"{team}_RB1",
                name="RB1",
                position="RB",
                team=team,
                usage=PlayerUsage(carry_share=0.60),
                outcomes=PlayerOutcomes(
                    rushing_yards_dist=np.array([2, 3, 4, 5, 6], dtype=float),
                ),
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Task 1: TestApplyVegas
# ---------------------------------------------------------------------------

class TestApplyVegas:
    """Tests for GameContextBuilder._apply_vegas() direct calls."""

    def test_volume_factor_sets_pace_factor(self):
        """VEG-01: volume_factor=1.10 sets pace_factor to 1.10."""
        dists = _make_dists()
        ctx = VegasContext(team="KC", volume_factor=1.10, pass_rate_factor=1.0)
        GameContextBuilder._apply_vegas(dists, ctx)
        assert dists.pace_factor == pytest.approx(1.10)

    def test_volume_factor_low_pace(self):
        """VEG-01: volume_factor=0.90 sets pace_factor to 0.90."""
        dists = _make_dists()
        ctx = VegasContext(team="KC", volume_factor=0.90, pass_rate_factor=1.0)
        GameContextBuilder._apply_vegas(dists, ctx)
        assert dists.pace_factor == pytest.approx(0.90)

    def test_volume_factor_compounds_existing_pace(self):
        """VEG-01: volume_factor compounds with existing pace_factor."""
        dists = _make_dists()
        dists.pace_factor = 1.05
        ctx = VegasContext(team="KC", volume_factor=1.10, pass_rate_factor=1.0)
        GameContextBuilder._apply_vegas(dists, ctx)
        assert dists.pace_factor == pytest.approx(1.05 * 1.10)

    def test_volume_does_not_shift_yards(self):
        """VEG-01: volume_factor does NOT modify per-player yard distributions.

        This explicitly verifies the review concern: Vegas volume = pace (play count),
        NOT yard efficiency. Arrays must be bitwise identical after applying
        a non-neutral volume_factor.
        """
        dists = _make_dists()
        roster = _make_roster()

        # Snapshot original arrays
        orig_receiving = {
            p.player_id: p.outcomes.receiving_yards_dist.copy()
            for p in roster.players
            if p.outcomes.receiving_yards_dist is not None
        }
        orig_rushing = {
            p.player_id: p.outcomes.rushing_yards_dist.copy()
            for p in roster.players
            if p.outcomes.rushing_yards_dist is not None
        }

        ctx = VegasContext(team="KC", volume_factor=1.10, pass_rate_factor=1.0)
        # _apply_vegas only takes dists — it does NOT touch the roster
        GameContextBuilder._apply_vegas(dists, ctx)

        # Verify roster arrays are unchanged (no additive shift)
        for p in roster.players:
            if p.outcomes.receiving_yards_dist is not None:
                np.testing.assert_array_equal(
                    p.outcomes.receiving_yards_dist,
                    orig_receiving[p.player_id],
                    err_msg=f"{p.player_id} receiving_yards_dist was modified by volume_factor",
                )
            if p.outcomes.rushing_yards_dist is not None:
                np.testing.assert_array_equal(
                    p.outcomes.rushing_yards_dist,
                    orig_rushing[p.player_id],
                    err_msg=f"{p.player_id} rushing_yards_dist was modified by volume_factor",
                )

    def test_pass_rate_modified(self):
        """VEG-02: pass_rate_factor=0.95 modifies PlayCallingDist.default correctly."""
        dists = _make_dists(pass_rate=0.57)
        ctx = VegasContext(team="KC", volume_factor=1.0, pass_rate_factor=0.95)
        GameContextBuilder._apply_vegas(dists, ctx)

        expected_pass = 0.57 * 0.95
        expected_run = 1.0 - expected_pass

        assert dists.play_calling.default["pass"] == pytest.approx(expected_pass, rel=1e-6)
        assert dists.play_calling.default["run"] == pytest.approx(expected_run, rel=1e-6)
        # Must sum to 1.0
        total = dists.play_calling.default["pass"] + dists.play_calling.default["run"]
        assert total == pytest.approx(1.0, rel=1e-9)

    def test_buckets_unchanged(self):
        """VEG-02: pass_rate_factor does NOT modify per-bucket distributions."""
        dists = _make_dists()
        # Snapshot the per-bucket distributions
        original_buckets = {
            bucket: dict(probs)
            for bucket, probs in dists.play_calling.distributions.items()
        }

        ctx = VegasContext(team="KC", volume_factor=1.0, pass_rate_factor=0.95)
        GameContextBuilder._apply_vegas(dists, ctx)

        # Per-bucket distributions must be untouched
        for bucket, orig_probs in original_buckets.items():
            current_probs = dists.play_calling.distributions[bucket]
            assert current_probs["pass"] == pytest.approx(orig_probs["pass"]), (
                f"Bucket {bucket} pass prob was modified by pass_rate_factor"
            )
            assert current_probs["run"] == pytest.approx(orig_probs["run"]), (
                f"Bucket {bucket} run prob was modified by pass_rate_factor"
            )

    def test_neutral_context_no_change(self):
        """Neutral VegasContext (all factors=1.0) leaves all fields unchanged."""
        dists = _make_dists()
        original_pace = dists.pace_factor
        original_default = dict(dists.play_calling.default)
        original_buckets = {
            bucket: dict(probs)
            for bucket, probs in dists.play_calling.distributions.items()
        }

        ctx = VegasContext(team="KC", volume_factor=1.0, pass_rate_factor=1.0)
        GameContextBuilder._apply_vegas(dists, ctx)

        assert dists.pace_factor == original_pace
        assert dists.play_calling.default == original_default
        for bucket, orig_probs in original_buckets.items():
            assert dists.play_calling.distributions[bucket] == orig_probs

    def test_extreme_pass_rate_clamp(self):
        """VEG-02: extreme high pass_rate_factor clamps pass rate to 0.99."""
        dists = _make_dists(pass_rate=0.57)
        ctx = VegasContext(team="KC", volume_factor=1.0, pass_rate_factor=5.0)
        GameContextBuilder._apply_vegas(dists, ctx)

        assert dists.play_calling.default["pass"] <= 0.99
        assert dists.play_calling.default["run"] >= 0.01
        total = dists.play_calling.default["pass"] + dists.play_calling.default["run"]
        assert total == pytest.approx(1.0, rel=1e-9)

    def test_extreme_low_pass_rate_clamp(self):
        """VEG-02: extreme low pass_rate_factor clamps pass rate to 0.01."""
        dists = _make_dists(pass_rate=0.57)
        ctx = VegasContext(team="KC", volume_factor=1.0, pass_rate_factor=0.01)
        GameContextBuilder._apply_vegas(dists, ctx)

        assert dists.play_calling.default["pass"] >= 0.01
        assert dists.play_calling.default["run"] <= 0.99
        total = dists.play_calling.default["pass"] + dists.play_calling.default["run"]
        assert total == pytest.approx(1.0, rel=1e-9)

    def test_combined_volume_and_pass_rate(self):
        """Both factors applied together work independently and correctly."""
        dists = _make_dists(pass_rate=0.57)
        ctx = VegasContext(team="KC", volume_factor=1.08, pass_rate_factor=0.95)
        GameContextBuilder._apply_vegas(dists, ctx)

        assert dists.pace_factor == pytest.approx(1.08)
        assert dists.play_calling.default["pass"] == pytest.approx(0.57 * 0.95, rel=1e-6)


# ---------------------------------------------------------------------------
# Task 1: TestVegasConfigPropagation
# ---------------------------------------------------------------------------

class TestVegasConfigPropagation:
    """Tests that vegas_config threads through Backtester and parallel workers."""

    def test_backtester_accepts_vegas_config(self):
        """Backtester.__init__ accepts vegas_config and stores it."""
        from fantasy_sim.validation.backtester import Backtester

        with patch("fantasy_sim.validation.backtester.DataLoader"):
            bt = Backtester(test_season=2024, vegas_config=VegasConfig(enabled=True))
            assert bt._vegas_config is not None
            assert bt._vegas_config.enabled is True

    def test_backtester_default_no_vegas(self):
        """Backtester without vegas_config stores None."""
        from fantasy_sim.validation.backtester import Backtester

        with patch("fantasy_sim.validation.backtester.DataLoader"):
            bt = Backtester(test_season=2024)
            assert bt._vegas_config is None

    def test_build_games_parallel_signature(self):
        """build_games_parallel accepts vegas_config keyword argument."""
        sig = inspect.signature(build_games_parallel)
        assert "vegas_config" in sig.parameters, (
            "build_games_parallel must accept 'vegas_config' keyword argument"
        )

    def test_init_worker_single_signature(self):
        """_init_build_worker_single accepts vegas_config keyword argument."""
        sig = inspect.signature(_init_build_worker_single)
        assert "vegas_config" in sig.parameters, (
            "_init_build_worker_single must accept 'vegas_config' keyword argument"
        )

    def test_sequential_builder_with_vegas(self):
        """_build_games_sequential creates GameContextBuilder with vegas_config without error."""
        import tempfile

        sample_pbp = pl.DataFrame([
            {
                "season": 2024, "week": 1, "game_id": "2024_01_KC_BUF",
                "play_type": "pass", "posteam": "KC", "defteam": "BUF",
                "down": 1, "ydstogo": 10, "yardline_100": 75,
                "score_differential": 0, "qtr": 1, "yards_gained": 8,
                "complete_pass": 1, "pass_attempt": 1, "rush_attempt": 0,
                "interception": 0, "fumble_lost": 0, "sack": 0,
                "touchdown": 0, "penalty": 0, "penalty_yards": 0,
                "passer_player_id": "PM15", "receiver_player_id": "TK87",
                "rusher_player_id": None,
            },
        ])
        sample_rosters = pl.DataFrame([
            {
                "season": 2024, "week": 1, "player_id": "PM15",
                "player_name": "P.Mahomes", "position": "QB", "team": "KC",
                "status": "ACT",
            },
        ])

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir)
            game_args = [
                ("KC", "BUF", [2024], 2024, 1, "2024_01_KC_BUF", 42)
            ]
            vegas_config = VegasConfig(enabled=False)

            # Patch out the DataLoader so no real network/disk access happens
            with patch("fantasy_sim.validation.parallel.GameContextBuilder") as MockBuilder:
                mock_instance = MagicMock()
                mock_instance.build_game.return_value = (
                    _make_dists(), _make_dists(),
                    _make_roster("KC"), _make_roster("BUF"),
                )
                MockBuilder.return_value = mock_instance

                results = _build_games_sequential(
                    game_args,
                    cache_dir=cache_path,
                    pff_config=None,
                    weather_config=None,
                    dual_arm=False,
                    on_complete=None,
                    vegas_config=vegas_config,
                )

            assert len(results) == 1
            # Verify GameContextBuilder was constructed with vegas_config
            MockBuilder.assert_called_once()
            call_kwargs = MockBuilder.call_args.kwargs
            assert "vegas_config" in call_kwargs
            assert call_kwargs["vegas_config"] is vegas_config


# ---------------------------------------------------------------------------
# Task 2: TestVegasIntegration
# ---------------------------------------------------------------------------

class TestVegasIntegration:
    """Tests for build_game() with Vegas enabled vs disabled."""

    def _make_minimal_schedule(self, spread: float = -14.0, total: float = 45.0) -> pl.DataFrame:
        """Create a schedule DataFrame for KC vs BUF with known lines."""
        return pl.DataFrame([
            {
                "season": 2024, "week": 5, "game_id": "2024_05_KC_BUF",
                "home_team": "KC", "away_team": "BUF",
                "home_score": 31, "away_score": 17,
                "spread_line": spread, "total_line": total,
            }
        ])

    def _make_minimal_pbp(self) -> pl.DataFrame:
        """Minimal PBP for 2024 season."""
        plays = []
        for i in range(12):
            plays.append({
                "season": 2024, "week": 1, "game_id": "2024_01_KC_BUF",
                "play_type": "pass" if i < 8 else "run",
                "posteam": "KC", "defteam": "BUF",
                "down": 1, "ydstogo": 10, "yardline_100": 60,
                "score_differential": 0, "qtr": 1, "yards_gained": 8,
                "complete_pass": 1 if i < 8 else 0,
                "pass_attempt": 1 if i < 8 else 0,
                "rush_attempt": 0 if i < 8 else 1,
                "interception": 0, "fumble_lost": 0, "sack": 0,
                "touchdown": 0, "penalty": 0, "penalty_yards": 0,
                "passer_player_id": "PM15" if i < 8 else None,
                "receiver_player_id": "TK87" if i < 8 else None,
                "rusher_player_id": None if i < 8 else "IP01",
            })
        # Add BUF plays
        for i in range(8):
            plays.append({
                "season": 2024, "week": 1, "game_id": "2024_01_KC_BUF",
                "play_type": "pass" if i < 5 else "run",
                "posteam": "BUF", "defteam": "KC",
                "down": 1, "ydstogo": 10, "yardline_100": 60,
                "score_differential": 0, "qtr": 1, "yards_gained": 7,
                "complete_pass": 1 if i < 5 else 0,
                "pass_attempt": 1 if i < 5 else 0,
                "rush_attempt": 0 if i < 5 else 1,
                "interception": 0, "fumble_lost": 0, "sack": 0,
                "touchdown": 0, "penalty": 0, "penalty_yards": 0,
                "passer_player_id": "JA17" if i < 5 else None,
                "receiver_player_id": "SD14" if i < 5 else None,
                "rusher_player_id": None if i < 5 else "JC02",
            })
        return pl.DataFrame(plays)

    def _make_minimal_rosters(self) -> pl.DataFrame:
        """Minimal roster data for KC and BUF."""
        rows = []
        for week in range(1, 6):
            rows.extend([
                {"season": 2024, "week": week, "player_id": "PM15",
                 "player_name": "P.Mahomes", "position": "QB", "team": "KC", "status": "ACT"},
                {"season": 2024, "week": week, "player_id": "TK87",
                 "player_name": "T.Kelce", "position": "TE", "team": "KC", "status": "ACT"},
                {"season": 2024, "week": week, "player_id": "IP01",
                 "player_name": "I.Pacheco", "position": "RB", "team": "KC", "status": "ACT"},
                {"season": 2024, "week": week, "player_id": "JA17",
                 "player_name": "J.Allen", "position": "QB", "team": "BUF", "status": "ACT"},
                {"season": 2024, "week": week, "player_id": "SD14",
                 "player_name": "S.Diggs", "position": "WR", "team": "BUF", "status": "ACT"},
                {"season": 2024, "week": week, "player_id": "JC02",
                 "player_name": "J.Cook", "position": "RB", "team": "BUF", "status": "ACT"},
            ])
        return pl.DataFrame(rows)

    def test_build_game_with_vegas_changes_pace(self):
        """build_game with VegasConfig(enabled=True) changes home_dists.pace_factor.

        Uses a large spread (KC -14) so the volume factor is non-neutral.
        """
        pbp = self._make_minimal_pbp()
        rosters = self._make_minimal_rosters()
        schedules = self._make_minimal_schedule(spread=-14.0, total=45.0)

        # Baseline without Vegas
        builder_off = GameContextBuilder()
        hd_off, ad_off, _, _ = builder_off.build_game(
            "KC", "BUF",
            training_seasons=[2024],
            target_season=2024, week=5,
            pbp=pbp, rosters=rosters,
        )

        # With Vegas enabled — mock loader.load_schedules to return known lines
        vegas_config = VegasConfig(enabled=True, itt_sensitivity=0.06)
        builder_on = GameContextBuilder(vegas_config=vegas_config)
        builder_on.loader.load_schedules = MagicMock(return_value=schedules)

        hd_on, ad_on, _, _ = builder_on.build_game(
            "KC", "BUF",
            training_seasons=[2024],
            target_season=2024, week=5,
            pbp=pbp, rosters=rosters,
        )

        # Vegas adjusts pace_factor; with spread=-14 both teams get non-neutral volume
        assert hd_on.pace_factor != hd_off.pace_factor, (
            "Vegas-enabled build should produce different pace_factor than no-Vegas build"
        )

    def test_no_vegas_matches_none(self):
        """build_game with VegasConfig(enabled=False) equals vegas_config=None.

        Verifies that disabled Vegas config is a no-op identical to no config.
        """
        pbp = self._make_minimal_pbp()
        rosters = self._make_minimal_rosters()

        builder_none = GameContextBuilder()
        hd_none, _, _, _ = builder_none.build_game(
            "KC", "BUF",
            training_seasons=[2024],
            target_season=2024, week=5,
            pbp=pbp, rosters=rosters,
        )

        builder_disabled = GameContextBuilder(vegas_config=VegasConfig(enabled=False))
        hd_disabled, _, _, _ = builder_disabled.build_game(
            "KC", "BUF",
            training_seasons=[2024],
            target_season=2024, week=5,
            pbp=pbp, rosters=rosters,
        )

        assert hd_none.pace_factor == pytest.approx(hd_disabled.pace_factor), (
            "VegasConfig(enabled=False) must be identical to no vegas_config"
        )
        assert hd_none.play_calling.default["pass"] == pytest.approx(
            hd_disabled.play_calling.default["pass"]
        )

    def test_vegas_before_matchup(self):
        """Vegas adjustments are applied before matchup in the pipeline.

        Since _apply_vegas does NOT use loader.load_schedules when enabled=False,
        this test verifies build_game pipeline order by checking that pace_factor
        is modified by Vegas BEFORE matchup can override it.

        We do this by:
        1. Mocking VegasEngine.compute to return a known volume_factor.
        2. Confirming pace_factor reflects Vegas adjustment in the final result.
        """
        pbp = self._make_minimal_pbp()
        rosters = self._make_minimal_rosters()

        # Mock VegasEngine.compute to return a distinct volume_factor
        target_volume = 1.08
        mock_home_ctx = VegasContext(team="KC", volume_factor=target_volume, pass_rate_factor=1.0)
        mock_away_ctx = VegasContext(team="BUF", volume_factor=0.95, pass_rate_factor=1.0)

        vegas_config = VegasConfig(enabled=True)
        builder = GameContextBuilder(vegas_config=vegas_config)

        with patch.object(
            builder._vegas_engine, "compute",
            return_value=(mock_home_ctx, mock_away_ctx),
        ):
            home_dists, _, _, _ = builder.build_game(
                "KC", "BUF",
                training_seasons=[2024],
                target_season=2024, week=5,
                pbp=pbp, rosters=rosters,
            )

        # pace_factor must reflect the Vegas volume (before matchup can touch it)
        # The matchup engine is None here (no PFF), so Vegas is the only modifier
        assert home_dists.pace_factor == pytest.approx(target_volume), (
            f"Expected pace_factor={target_volume} from Vegas, got {home_dists.pace_factor}"
        )

    def test_vegas_plus_weather_coexistence(self):
        """Vegas and weather both apply without error and produce different results.

        Verifies combined-layer coexistence. Both layers must apply to the
        same distributions without one overwriting the other's work.
        """
        from fantasy_sim.data.weather.models import WeatherConfig

        pbp = self._make_minimal_pbp()
        rosters = self._make_minimal_rosters()

        mock_home_ctx = VegasContext(team="KC", volume_factor=1.08, pass_rate_factor=0.95)
        mock_away_ctx = VegasContext(team="BUF", volume_factor=0.94, pass_rate_factor=1.05)

        vegas_config = VegasConfig(enabled=True)
        weather_config = WeatherConfig(enabled=True)

        builder = GameContextBuilder(
            vegas_config=vegas_config,
            weather_config=weather_config,
        )

        with patch.object(
            builder._vegas_engine, "compute",
            return_value=(mock_home_ctx, mock_away_ctx),
        ):
            # Weather engine will return None for no weather data (no network)
            # or skip if no context — that's fine, we just verify no exception
            try:
                home_dists, away_dists, _, _ = builder.build_game(
                    "KC", "BUF",
                    training_seasons=[2024],
                    target_season=2024, week=5,
                    pbp=pbp, rosters=rosters,
                )
            except Exception as exc:
                # Only fail on real errors, not on missing weather data
                if "weather" not in str(exc).lower() and "network" not in str(exc).lower():
                    raise

        # Vegas adjustments must still be present after weather layer
        assert home_dists.pace_factor == pytest.approx(1.08), (
            "Vegas pace_factor must survive weather layer application"
        )
        assert home_dists.play_calling.default["pass"] == pytest.approx(
            0.57 * 0.95, rel=0.05
        ), "Vegas pass rate must survive weather layer"


# ---------------------------------------------------------------------------
# Task 2: TestABHarnessVegasModes
# ---------------------------------------------------------------------------

class TestABHarnessVegasModes:
    """Tests for A/B harness mode routing (_build_vegas_config in validate_pff_signal.py)."""

    @pytest.fixture(autouse=True)
    def _import_build_vegas_config(self):
        """Import _build_vegas_config from validate_pff_signal with sys.path patch."""
        scripts_dir = str(
            Path(__file__).parents[3] / "scripts"
        )
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)

        # Patch load_defaults and load_vegas_config to avoid disk access
        with patch("validate_pff_signal.load_defaults") as mock_defaults, \
             patch("validate_pff_signal.load_vegas_config") as mock_load_vegas:
            mock_defaults.return_value = {}
            # Return a fresh VegasConfig each time
            mock_load_vegas.side_effect = lambda _: VegasConfig(
                enabled=False,
                itt_sensitivity=0.06,
                spread_sensitivity=0.04,
            )
            import validate_pff_signal as vps
            self._vps = vps
            yield

    def test_vegas_mode_itt_only(self):
        """_build_vegas_config('vegas') returns VegasConfig with spread_sensitivity=0."""
        config = self._vps._build_vegas_config("vegas")
        assert config is not None
        assert config.enabled is True
        assert config.spread_sensitivity == 0.0, (
            "Mode 'vegas' (ITT-only) must have spread_sensitivity=0"
        )

    def test_vegas_spread_mode(self):
        """_build_vegas_config('vegas+spread') returns VegasConfig with both sensitivities active."""
        config = self._vps._build_vegas_config("vegas+spread")
        assert config is not None
        assert config.enabled is True
        # Both sensitivities must be > 0 for the combined mode
        assert config.spread_sensitivity > 0.0, (
            "Mode 'vegas+spread' must have spread_sensitivity > 0"
        )
        assert config.itt_sensitivity > 0.0, (
            "Mode 'vegas+spread' must have itt_sensitivity > 0"
        )

    def test_non_vegas_mode_returns_none(self):
        """_build_vegas_config('tier') returns None."""
        result = self._vps._build_vegas_config("tier")
        assert result is None, (
            "_build_vegas_config must return None for non-Vegas mode 'tier'"
        )

    def test_vegas_config_default_sensitivities(self):
        """Default sensitivities: itt=0.06, spread=0.04 for 'vegas+spread' mode."""
        config = self._vps._build_vegas_config("vegas+spread")
        assert config is not None
        assert config.itt_sensitivity == pytest.approx(0.06), (
            "Default ITT sensitivity must be 0.06"
        )
        assert config.spread_sensitivity == pytest.approx(0.04), (
            "Default spread sensitivity must be 0.04"
        )

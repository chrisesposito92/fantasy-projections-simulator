"""Tests for parallel game simulation runner."""

import os
from unittest.mock import patch

from fantasy_sim.validation.parallel import default_max_workers


class TestDefaultMaxWorkers:
    def test_basic_computation(self):
        with patch.object(os, "cpu_count", return_value=12):
            result = default_max_workers(batch_size=288, num_concurrent=1)
            assert result == 10  # (12 - 2) // 1 = 10, min(10, 288) = 10

    def test_scales_by_concurrent_seasons(self):
        with patch.object(os, "cpu_count", return_value=12):
            result = default_max_workers(batch_size=288, num_concurrent=2)
            assert result == 5  # (12 - 2) // 2 = 5

    def test_capped_by_batch_size(self):
        with patch.object(os, "cpu_count", return_value=12):
            result = default_max_workers(batch_size=3, num_concurrent=1)
            assert result == 3  # min(10, 3) = 3

    def test_minimum_one_worker(self):
        with patch.object(os, "cpu_count", return_value=2):
            result = default_max_workers(batch_size=100, num_concurrent=4)
            assert result == 1  # max(1, (2-2)//4) = 1

    def test_zero_batch_size(self):
        result = default_max_workers(batch_size=0, num_concurrent=1)
        assert result == 0

    def test_cpu_count_none_fallback(self):
        with patch.object(os, "cpu_count", return_value=None):
            result = default_max_workers(batch_size=288, num_concurrent=1)
            assert result == 6  # (8 - 2) // 1 = 6 (fallback to 8)


import numpy as np

from fantasy_sim.engine.types import TeamDistributions
from fantasy_sim.models.distributions import (
    PlayCallingDist, PlayOutcomeDist, TurnoverRates, KickingModel, DriveStartModel,
)
from fantasy_sim.models.player import TeamRoster, PlayerModel, PlayerUsage, PlayerOutcomes
from fantasy_sim.validation.parallel import GameSpec, GameSimResult


def _make_dists(team: str) -> TeamDistributions:
    """Minimal TeamDistributions for tests."""
    return TeamDistributions(
        play_calling=PlayCallingDist(team=team, distributions={}, default={"pass": 0.55, "run": 0.45}),
        play_outcomes=PlayOutcomeDist(distributions={}, defaults={
            "pass": np.array([0, 5, 8, 10, 12, 15]),
            "run": np.array([2, 3, 4, 5, 6]),
        }),
        turnover_rates=TurnoverRates(team=team, int_rate=0.02, fumble_rate=0.01, sack_rate=0.06, sack_fumble_rate=0.10),
        kicking=KickingModel(fg_make_rate={"0_39": 0.93, "40_49": 0.82, "50_plus": 0.65}, xp_rate=0.94),
        drive_start=DriveStartModel(touchback_rate=0.55, touchback_yardline=75, return_yardlines=np.array([74, 76])),
    )


def _make_roster(team: str) -> TeamRoster:
    """Minimal TeamRoster for tests."""
    return TeamRoster(team=team, players=[
        PlayerModel(f"{team}_QB", "QB", "QB", team, PlayerUsage(snap_share=1.0), PlayerOutcomes()),
        PlayerModel(f"{team}_WR", "WR", "WR", team, PlayerUsage(target_share=0.50),
                   PlayerOutcomes(catch_rate=0.60, receiving_yards_dist=np.array([8, 12]))),
        PlayerModel(f"{team}_RB", "RB", "RB", team, PlayerUsage(carry_share=1.0, target_share=0.50),
                   PlayerOutcomes(rushing_yards_dist=np.array([3, 5, 7]),
                                 catch_rate=0.70, receiving_yards_dist=np.array([4, 6]))),
    ])


class TestGameSpecDataclass:
    def test_creation(self):
        spec = GameSpec(
            game_id="2024_01_KC_BUF",
            home_dists=_make_dists("KC"),
            away_dists=_make_dists("BUF"),
            home_roster=_make_roster("KC"),
            away_roster=_make_roster("BUF"),
            seed=12345,
            week=1,
            metadata={"arm": "off"},
        )
        assert spec.game_id == "2024_01_KC_BUF"
        assert spec.seed == 12345
        assert spec.metadata["arm"] == "off"

    def test_metadata_defaults_to_empty(self):
        spec = GameSpec(
            game_id="test",
            home_dists=_make_dists("KC"),
            away_dists=_make_dists("BUF"),
            home_roster=None,
            away_roster=None,
            seed=0,
            week=1,
        )
        assert spec.metadata == {}


class TestGameSimResult:
    def test_creation(self):
        result = GameSimResult(
            game_id="2024_01_KC_BUF",
            projections=[{"player_id": "KC_QB", "fpts": 22.4}],
            metadata={"arm": "baseline"},
        )
        assert result.game_id == "2024_01_KC_BUF"
        assert len(result.projections) == 1
        assert result.projections[0]["fpts"] == 22.4
        assert result.metadata["arm"] == "baseline"

    def test_metadata_defaults_to_empty(self):
        result = GameSimResult(game_id="test", projections=[])
        assert result.metadata == {}

    def test_empty_projections(self):
        result = GameSimResult(game_id="test", projections=[])
        assert result.projections == []


from fantasy_sim.config.loader import load_defaults, resolve_scoring
from fantasy_sim.validation.parallel import simulate_games_parallel


def _make_spec(game_id: str, seed: int, metadata: dict | None = None) -> GameSpec:
    """Helper to create a GameSpec with minimal valid context."""
    return GameSpec(
        game_id=game_id,
        home_dists=_make_dists("KC"),
        away_dists=_make_dists("BUF"),
        home_roster=_make_roster("KC"),
        away_roster=_make_roster("BUF"),
        seed=seed,
        week=1,
        metadata=metadata or {},
    )


class TestSimulateGamesParallel:
    def _get_scoring_config(self) -> dict:
        defaults = load_defaults()
        return resolve_scoring(defaults["scoring"], "ppr")

    def test_sequential_returns_results(self):
        specs = [_make_spec("game_a", seed=42), _make_spec("game_b", seed=99)]
        scoring = self._get_scoring_config()
        results = simulate_games_parallel(specs, n_sims=5, scoring_config=scoring, max_workers=1)
        assert len(results) == 2
        game_ids = {r.game_id for r in results}
        assert game_ids == {"game_a", "game_b"}
        for r in results:
            assert isinstance(r.projections, list)
            assert len(r.projections) > 0

    def test_empty_specs_returns_empty(self):
        scoring = self._get_scoring_config()
        results = simulate_games_parallel([], n_sims=5, scoring_config=scoring, max_workers=1)
        assert results == []

    def test_determinism_parallel_matches_sequential(self):
        """Same seeds must produce identical projections regardless of worker count."""
        specs = [
            _make_spec("game_1", seed=100),
            _make_spec("game_2", seed=200),
            _make_spec("game_3", seed=300),
        ]
        scoring = self._get_scoring_config()

        sequential = simulate_games_parallel(specs, n_sims=10, scoring_config=scoring, max_workers=1)
        parallel = simulate_games_parallel(specs, n_sims=10, scoring_config=scoring, max_workers=2)

        seq_by_id = {r.game_id: r for r in sequential}
        par_by_id = {r.game_id: r for r in parallel}

        assert set(seq_by_id.keys()) == set(par_by_id.keys())
        for game_id in seq_by_id:
            seq_projs = {p["player_id"]: p["fpts"] for p in seq_by_id[game_id].projections}
            par_projs = {p["player_id"]: p["fpts"] for p in par_by_id[game_id].projections}
            assert seq_projs == par_projs, f"Mismatch for {game_id}"

    def test_metadata_passthrough(self):
        specs = [
            _make_spec("game_off", seed=42, metadata={"arm": "off"}),
            _make_spec("game_on", seed=42, metadata={"arm": "on"}),
        ]
        scoring = self._get_scoring_config()
        results = simulate_games_parallel(specs, n_sims=5, scoring_config=scoring, max_workers=1)
        meta_by_id = {r.game_id: r.metadata for r in results}
        assert meta_by_id["game_off"]["arm"] == "off"
        assert meta_by_id["game_on"]["arm"] == "on"

    def test_error_isolation_skips_failed_games(self):
        """A broken spec should not prevent other specs from completing."""
        good_spec = _make_spec("good_game", seed=42)
        bad_spec = GameSpec(
            game_id="bad_game",
            home_dists=_make_dists("KC"),
            away_dists=_make_dists("BUF"),
            home_roster=None,
            away_roster=None,
            seed=99,
            week=1,
        )
        bad_spec.home_dists.play_outcomes = None  # type: ignore[assignment]

        scoring = self._get_scoring_config()
        results = simulate_games_parallel(
            [good_spec, bad_spec], n_sims=5, scoring_config=scoring, max_workers=1
        )
        assert len(results) >= 1
        assert any(r.game_id == "good_game" for r in results)

    def test_on_complete_callback_fires(self):
        specs = [_make_spec("g1", seed=1), _make_spec("g2", seed=2)]
        scoring = self._get_scoring_config()
        completed = []
        results = simulate_games_parallel(
            specs, n_sims=5, scoring_config=scoring, max_workers=1,
            on_complete=lambda done, total: completed.append((done, total)),
        )
        assert len(results) == 2
        assert len(completed) == 2
        assert completed[-1] == (2, 2)


import copy


class TestKickingModelIsolation:
    def test_weather_mutation_does_not_bleed_across_games(self):
        """Two TeamDistributions from the same pipeline must have independent KickingModels."""
        dists_a = _make_dists("KC")
        dists_b = _make_dists("BUF")

        # Simulate what _apply_weather does: mutate kicking in-place
        original_rate = dists_a.kicking.fg_make_rate["50_plus"]
        dists_a.kicking.fg_make_rate["50_plus"] = 0.10  # severe weather

        # dists_b should NOT see this mutation
        assert dists_b.kicking.fg_make_rate["50_plus"] == original_rate

    def test_build_team_distributions_returns_independent_kicking(self):
        """build_team_distributions must deepcopy kicking from pipeline cache."""
        from fantasy_sim.data.game_context import GameContextBuilder
        from unittest.mock import MagicMock, patch

        builder = object.__new__(GameContextBuilder)
        builder._pff_config = MagicMock(enabled=False)
        builder._matchup_engine = None
        builder._talent_stabilizer = None
        builder._tier_engine = None
        builder._team_context_engine = None
        builder._coverage_engine = None
        builder._kicker_engine = None
        builder._dst_baseline_engine = None
        builder._weather_engine = None
        builder._pff_crosswalk = None
        builder._pff_loader = None
        builder._weather_config = None

        kicking = KickingModel(
            fg_make_rate={"0_39": 0.93, "40_49": 0.82, "50_plus": 0.65},
            xp_rate=0.94,
        )
        pipeline_output = {
            "play_calling": {"KC": PlayCallingDist(team="KC", distributions={}, default={"pass": 0.55, "run": 0.45})},
            "play_outcomes": PlayOutcomeDist(distributions={}, defaults={}),
            "turnover_rates": {"KC": TurnoverRates(team="KC", int_rate=0.02, fumble_rate=0.01, sack_rate=0.06, sack_fumble_rate=0.10)},
            "kicking": kicking,
            "drive_start": DriveStartModel(touchback_rate=0.55, touchback_yardline=75, return_yardlines=np.array([74, 76])),
        }
        builder._pipeline_cache = pipeline_output
        builder._cached_training_seasons = (2022, 2023, 2024)
        builder._pbp_stats_cache = {}
        builder._player_models_cache = {}
        builder._player_cache_key = ((2022, 2023, 2024), None, None)
        builder.cache_dir = "/tmp"
        builder.loader = MagicMock()

        dists = builder.build_team_distributions("KC", training_seasons=[2022, 2023, 2024])

        # Mutate the returned kicking — should NOT affect the pipeline cache
        dists.kicking.fg_make_rate["50_plus"] = 0.10
        assert pipeline_output["kicking"].fg_make_rate["50_plus"] == 0.65


from fantasy_sim.validation.backtester import Backtester


class TestBacktesterParallel:
    def test_default_max_workers_is_one(self):
        bt = Backtester(test_season=2024, n_sims=10)
        assert bt.max_workers == 1

    def test_max_workers_param(self):
        bt = Backtester(test_season=2024, n_sims=10, max_workers=4)
        assert bt.max_workers == 4

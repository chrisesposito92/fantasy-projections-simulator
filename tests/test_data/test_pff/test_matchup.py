"""Tests for PFF matchup engine — z-score factor computation."""

import polars as pl
import pytest

from fantasy_sim.data.pff.loader import PffLoader
from fantasy_sim.data.pff.matchup import (
    MatchupEngine,
    compute_factor,
)
from fantasy_sim.data.pff.models import MatchupConfig, PffConfig


# ---------- Fixtures ----------


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
def default_config():
    """PffConfig with matchup enabled, default sensitivities."""
    return PffConfig(
        enabled=True,
        matchup=MatchupConfig(
            enabled=True,
            pass_defense_sensitivity=0.08,
            pass_rush_sensitivity=0.10,
            run_defense_sensitivity=0.08,
            int_rate_sensitivity=0.06,
            ol_pass_sensitivity=0.08,
            ol_run_sensitivity=0.06,
            factor_clamp=(0.80, 1.20),
            min_games=4,
        ),
    )


# ---------- Parquet helpers ----------


def _write_defense_coverage(pff_dir, season, teams_data):
    """Write defense_coverage parquet with per-team player-game rows.

    teams_data: list of dicts with keys:
        team, n_players, n_games, catch_rate, yards_per_reception,
        grades_coverage_defense, interceptions, targets
    """
    rows = {
        "player_id": [],
        "player": [],
        "team": [],
        "position": [],
        "season": [],
        "week": [],
        "game_id": [],
        "catch_rate": [],
        "yards_per_reception": [],
        "grades_coverage_defense": [],
        "targets": [],
        "receptions": [],
        "interceptions": [],
        "yards": [],
        "yards_after_catch": [],
    }
    pid = 1000
    gid = 5000
    for td in teams_data:
        n_players = td.get("n_players", 3)
        n_games = td.get("n_games", 6)
        for p in range(n_players):
            for g in range(n_games):
                pid_val = pid + p
                rows["player_id"].append(pid_val)
                rows["player"].append(f"Player_{td['team']}_{p}")
                rows["team"].append(td["team"])
                rows["position"].append("CB")
                rows["season"].append(season)
                rows["week"].append(g + 1)
                rows["game_id"].append(gid + g)
                rows["catch_rate"].append(td["catch_rate"])
                rows["yards_per_reception"].append(td["yards_per_reception"])
                rows["grades_coverage_defense"].append(
                    td.get("grades_coverage_defense", 65.0)
                )
                rows["targets"].append(td.get("targets", 20))
                rows["receptions"].append(
                    int(td["catch_rate"] * td.get("targets", 20) / 100)
                )
                rows["interceptions"].append(td.get("interceptions", 0.5))
                rows["yards"].append(td["yards_per_reception"] * 5.0)
                rows["yards_after_catch"].append(td["yards_per_reception"] * 2.0)
        pid += 100
        gid += 100

    df = pl.DataFrame(rows)
    df.write_parquet(pff_dir / f"defense_coverage_{season}.parquet")
    return df


def _write_defense_pass_rush(pff_dir, season, teams_data):
    """Write defense_pass_rush parquet.

    teams_data: list of dicts with keys:
        team, n_players, n_games, pass_rush_win_rate,
        grades_pass_rush_defense, total_pressures, sacks, hurries, hits,
        pass_rush_opp
    """
    rows = {
        "player_id": [],
        "player": [],
        "team": [],
        "position": [],
        "season": [],
        "week": [],
        "game_id": [],
        "pass_rush_win_rate": [],
        "grades_pass_rush_defense": [],
        "total_pressures": [],
        "sacks": [],
        "hurries": [],
        "hits": [],
        "pass_rush_opp": [],
    }
    pid = 2000
    gid = 6000
    for td in teams_data:
        n_players = td.get("n_players", 3)
        n_games = td.get("n_games", 6)
        for p in range(n_players):
            for g in range(n_games):
                rows["player_id"].append(pid + p)
                rows["player"].append(f"Rusher_{td['team']}_{p}")
                rows["team"].append(td["team"])
                rows["position"].append("EDGE")
                rows["season"].append(season)
                rows["week"].append(g + 1)
                rows["game_id"].append(gid + g)
                rows["pass_rush_win_rate"].append(td["pass_rush_win_rate"])
                rows["grades_pass_rush_defense"].append(
                    td.get("grades_pass_rush_defense", 65.0)
                )
                rows["total_pressures"].append(td.get("total_pressures", 3))
                rows["sacks"].append(td.get("sacks", 0.5))
                rows["hurries"].append(td.get("hurries", 1.5))
                rows["hits"].append(td.get("hits", 1.0))
                rows["pass_rush_opp"].append(td.get("pass_rush_opp", 25))
        pid += 100
        gid += 100

    df = pl.DataFrame(rows)
    df.write_parquet(pff_dir / f"defense_pass_rush_{season}.parquet")
    return df


def _write_defense_run(pff_dir, season, teams_data):
    """Write defense_run parquet.

    teams_data: list of dicts with keys:
        team, n_players, n_games, stop_percent, grades_run_defense,
        tackles, assists, missed_tackles
    """
    rows = {
        "player_id": [],
        "player": [],
        "team": [],
        "position": [],
        "season": [],
        "week": [],
        "game_id": [],
        "stop_percent": [],
        "grades_run_defense": [],
        "tackles": [],
        "assists": [],
        "missed_tackles": [],
    }
    pid = 3000
    gid = 7000
    for td in teams_data:
        n_players = td.get("n_players", 3)
        n_games = td.get("n_games", 6)
        for p in range(n_players):
            for g in range(n_games):
                rows["player_id"].append(pid + p)
                rows["player"].append(f"Defender_{td['team']}_{p}")
                rows["team"].append(td["team"])
                rows["position"].append("LB")
                rows["season"].append(season)
                rows["week"].append(g + 1)
                rows["game_id"].append(gid + g)
                rows["stop_percent"].append(td["stop_percent"])
                rows["grades_run_defense"].append(
                    td.get("grades_run_defense", 65.0)
                )
                rows["tackles"].append(td.get("tackles", 4))
                rows["assists"].append(td.get("assists", 2))
                rows["missed_tackles"].append(td.get("missed_tackles", 1))
        pid += 100
        gid += 100

    df = pl.DataFrame(rows)
    df.write_parquet(pff_dir / f"defense_run_{season}.parquet")
    return df


def _write_offense_pass_blocking(pff_dir, season, teams_data):
    """Write offense_pass_blocking parquet.

    teams_data: list of dicts with keys:
        team, n_players, n_games, pbe, grades_pass_block
    """
    rows = {
        "player_id": [],
        "player": [],
        "team": [],
        "position": [],
        "season": [],
        "week": [],
        "game_id": [],
        "pbe": [],
        "grades_pass_block": [],
    }
    pid = 4000
    gid = 8000
    for td in teams_data:
        n_players = td.get("n_players", 3)
        n_games = td.get("n_games", 6)
        for p in range(n_players):
            for g in range(n_games):
                rows["player_id"].append(pid + p)
                rows["player"].append(f"OL_{td['team']}_{p}")
                rows["team"].append(td["team"])
                rows["position"].append("T")
                rows["season"].append(season)
                rows["week"].append(g + 1)
                rows["game_id"].append(gid + g)
                rows["pbe"].append(td["pbe"])
                rows["grades_pass_block"].append(
                    td.get("grades_pass_block", 65.0)
                )
        pid += 100
        gid += 100

    df = pl.DataFrame(rows)
    df.write_parquet(pff_dir / f"offense_pass_blocking_{season}.parquet")
    return df


def _write_offense_run_blocking(pff_dir, season, teams_data):
    """Write offense_run_blocking parquet.

    teams_data: list of dicts with keys:
        team, n_players, n_games, grades_run_block, run_block_percent
    """
    rows = {
        "player_id": [],
        "player": [],
        "team": [],
        "position": [],
        "season": [],
        "week": [],
        "game_id": [],
        "grades_run_block": [],
        "run_block_percent": [],
    }
    pid = 5000
    gid = 9000
    for td in teams_data:
        n_players = td.get("n_players", 3)
        n_games = td.get("n_games", 6)
        for p in range(n_players):
            for g in range(n_games):
                rows["player_id"].append(pid + p)
                rows["player"].append(f"OL_{td['team']}_{p}")
                rows["team"].append(td["team"])
                rows["position"].append("G")
                rows["season"].append(season)
                rows["week"].append(g + 1)
                rows["game_id"].append(gid + g)
                rows["grades_run_block"].append(td["grades_run_block"])
                rows["run_block_percent"].append(
                    td.get("run_block_percent", 65.0)
                )
        pid += 100
        gid += 100

    df = pl.DataFrame(rows)
    df.write_parquet(pff_dir / f"offense_run_blocking_{season}.parquet")
    return df


def _write_all_facets(pff_dir, season, coverage, pass_rush, run_def, ol_pass, ol_run):
    """Convenience: write all 5 facets at once."""
    _write_defense_coverage(pff_dir, season, coverage)
    _write_defense_pass_rush(pff_dir, season, pass_rush)
    _write_defense_run(pff_dir, season, run_def)
    _write_offense_pass_blocking(pff_dir, season, ol_pass)
    _write_offense_run_blocking(pff_dir, season, ol_run)


# ---------- Three-team baseline data ----------
# BAL = elite defense, CAR = weak defense, KC = average
# PHI = elite OL, NYG = weak OL, KC = average OL

THREE_TEAM_COVERAGE = [
    {
        "team": "BAL",
        "n_players": 3,
        "n_games": 6,
        "catch_rate": 0.55,
        "yards_per_reception": 10.0,
        "grades_coverage_defense": 88.0,
        "interceptions": 1.2,
        "targets": 20,
    },
    {
        "team": "CAR",
        "n_players": 3,
        "n_games": 6,
        "catch_rate": 0.72,
        "yards_per_reception": 14.5,
        "grades_coverage_defense": 48.0,
        "interceptions": 0.3,
        "targets": 20,
    },
    {
        "team": "KC",
        "n_players": 3,
        "n_games": 6,
        "catch_rate": 0.64,
        "yards_per_reception": 12.0,
        "grades_coverage_defense": 65.0,
        "interceptions": 0.7,
        "targets": 20,
    },
]

THREE_TEAM_PASS_RUSH = [
    {
        "team": "BAL",
        "n_players": 3,
        "n_games": 6,
        "pass_rush_win_rate": 18.0,
        "grades_pass_rush_defense": 90.0,
    },
    {
        "team": "CAR",
        "n_players": 3,
        "n_games": 6,
        "pass_rush_win_rate": 8.0,
        "grades_pass_rush_defense": 45.0,
    },
    {
        "team": "KC",
        "n_players": 3,
        "n_games": 6,
        "pass_rush_win_rate": 13.0,
        "grades_pass_rush_defense": 68.0,
    },
]

THREE_TEAM_RUN_DEF = [
    {
        "team": "BAL",
        "n_players": 3,
        "n_games": 6,
        "stop_percent": 12.0,
        "grades_run_defense": 85.0,
    },
    {
        "team": "CAR",
        "n_players": 3,
        "n_games": 6,
        "stop_percent": 5.0,
        "grades_run_defense": 45.0,
    },
    {
        "team": "KC",
        "n_players": 3,
        "n_games": 6,
        "stop_percent": 8.5,
        "grades_run_defense": 65.0,
    },
]

THREE_TEAM_OL_PASS = [
    {
        "team": "PHI",
        "n_players": 3,
        "n_games": 6,
        "pbe": 92.0,
        "grades_pass_block": 88.0,
    },
    {
        "team": "NYG",
        "n_players": 3,
        "n_games": 6,
        "pbe": 78.0,
        "grades_pass_block": 52.0,
    },
    {
        "team": "KC",
        "n_players": 3,
        "n_games": 6,
        "pbe": 85.0,
        "grades_pass_block": 70.0,
    },
]

THREE_TEAM_OL_RUN = [
    {
        "team": "PHI",
        "n_players": 3,
        "n_games": 6,
        "grades_run_block": 85.0,
        "run_block_percent": 72.0,
    },
    {
        "team": "NYG",
        "n_players": 3,
        "n_games": 6,
        "grades_run_block": 55.0,
        "run_block_percent": 58.0,
    },
    {
        "team": "KC",
        "n_players": 3,
        "n_games": 6,
        "grades_run_block": 70.0,
        "run_block_percent": 65.0,
    },
]


# ========== compute_factor tests ==========


class TestComputeFactor:
    """Tests for the pure compute_factor function."""

    def test_average_team_returns_one(self):
        """A team exactly at league average gets factor 1.0."""
        result = compute_factor(
            team_value=10.0,
            league_avg=10.0,
            league_std=2.0,
            sensitivity=0.08,
            clamp=(0.80, 1.20),
        )
        assert result == pytest.approx(1.0)

    def test_above_average_team(self):
        """A team 1 std above average gets 1.0 + sensitivity."""
        result = compute_factor(
            team_value=12.0,
            league_avg=10.0,
            league_std=2.0,
            sensitivity=0.08,
            clamp=(0.80, 1.20),
        )
        # z = (12-10)/2 = 1.0, factor = 1.0 + 1.0*0.08 = 1.08
        assert result == pytest.approx(1.08)

    def test_below_average_team(self):
        """A team 1 std below average gets 1.0 - sensitivity."""
        result = compute_factor(
            team_value=8.0,
            league_avg=10.0,
            league_std=2.0,
            sensitivity=0.08,
            clamp=(0.80, 1.20),
        )
        # z = (8-10)/2 = -1.0, factor = 1.0 + (-1.0)*0.08 = 0.92
        assert result == pytest.approx(0.92)

    def test_clamp_upper_bound(self):
        """Extreme above-average team gets clamped to max."""
        result = compute_factor(
            team_value=20.0,
            league_avg=10.0,
            league_std=2.0,
            sensitivity=0.08,
            clamp=(0.80, 1.20),
        )
        # z = 5.0, unclamped = 1.40, clamped to 1.20
        assert result == pytest.approx(1.20)

    def test_clamp_lower_bound(self):
        """Extreme below-average team gets clamped to min."""
        result = compute_factor(
            team_value=0.0,
            league_avg=10.0,
            league_std=2.0,
            sensitivity=0.08,
            clamp=(0.80, 1.20),
        )
        # z = -5.0, unclamped = 0.60, clamped to 0.80
        assert result == pytest.approx(0.80)

    def test_zero_std_returns_one(self):
        """If league std is zero, can't compute z-score — return 1.0."""
        result = compute_factor(
            team_value=15.0,
            league_avg=10.0,
            league_std=0.0,
            sensitivity=0.08,
            clamp=(0.80, 1.20),
        )
        assert result == pytest.approx(1.0)

    def test_negative_std_returns_one(self):
        """Negative std (shouldn't happen but defensive) returns 1.0."""
        result = compute_factor(
            team_value=15.0,
            league_avg=10.0,
            league_std=-1.0,
            sensitivity=0.08,
            clamp=(0.80, 1.20),
        )
        assert result == pytest.approx(1.0)

    def test_half_sigma_shift(self):
        """A team 0.5 std above average gets half the sensitivity shift."""
        result = compute_factor(
            team_value=11.0,
            league_avg=10.0,
            league_std=2.0,
            sensitivity=0.10,
            clamp=(0.80, 1.20),
        )
        # z = 0.5, factor = 1.0 + 0.5*0.10 = 1.05
        assert result == pytest.approx(1.05)

    def test_different_sensitivity_values(self):
        """Higher sensitivity = larger shift for same z-score."""
        low = compute_factor(10.0, 8.0, 2.0, 0.04, (0.80, 1.20))
        high = compute_factor(10.0, 8.0, 2.0, 0.12, (0.80, 1.20))
        # z = 1.0 for both, low = 1.04, high = 1.12
        assert low == pytest.approx(1.04)
        assert high == pytest.approx(1.12)


# ========== MatchupEngine.compute tests ==========


class TestMatchupEngineCompute:
    """Integration tests for the full MatchupEngine.compute() flow."""

    def test_elite_defense_reduces_catch_rate(self, pff_dir, loader, default_config):
        """BAL elite coverage (catch_rate=0.55) should produce catch_rate_factor < 1.0."""
        _write_defense_coverage(pff_dir, 2024, THREE_TEAM_COVERAGE)

        engine = MatchupEngine(default_config, loader)
        ctx = engine.compute("BAL", "KC", [2024])

        # BAL catch_rate=0.55 is below avg (0.6367), so factor < 1.0
        assert ctx.catch_rate_factor < 1.0
        # With sensitivity=0.08 the shift is modest (z ~ -1.0 → factor ~ 0.92)
        assert ctx.catch_rate_factor == pytest.approx(0.92, abs=0.05)

    def test_weak_defense_increases_catch_rate(self, pff_dir, loader, default_config):
        """CAR weak coverage (catch_rate=0.72) should produce catch_rate_factor > 1.0."""
        _write_defense_coverage(pff_dir, 2024, THREE_TEAM_COVERAGE)

        engine = MatchupEngine(default_config, loader)
        ctx = engine.compute("CAR", "KC", [2024])

        assert ctx.catch_rate_factor > 1.0

    def test_average_defense_near_neutral(self, pff_dir, loader, default_config):
        """KC average coverage should produce catch_rate_factor near 1.0."""
        _write_defense_coverage(pff_dir, 2024, THREE_TEAM_COVERAGE)

        engine = MatchupEngine(default_config, loader)
        ctx = engine.compute("KC", "KC", [2024])

        # KC is close to average, factor should be near 1.0
        assert ctx.catch_rate_factor == pytest.approx(1.0, abs=0.05)

    def test_no_data_returns_neutral_context(self, pff_dir, loader, default_config):
        """When no PFF data exists, all factors should be 1.0."""
        engine = MatchupEngine(default_config, loader)
        ctx = engine.compute("BAL", "KC", [2024])

        assert ctx.catch_rate_factor == 1.0
        assert ctx.pass_yards_factor == 1.0
        assert ctx.sack_rate_factor == 1.0
        assert ctx.int_rate_factor == 1.0
        assert ctx.rush_yards_factor == 1.0
        assert ctx.ol_pass_block_factor == 1.0
        assert ctx.ol_run_block_factor == 1.0

    def test_disabled_config_returns_neutral(self, pff_dir, loader):
        """When matchup is disabled, return neutral context regardless of data."""
        _write_defense_coverage(pff_dir, 2024, THREE_TEAM_COVERAGE)

        config = PffConfig(
            enabled=True,
            matchup=MatchupConfig(enabled=False),
        )
        engine = MatchupEngine(config, loader)
        ctx = engine.compute("BAL", "KC", [2024])

        assert ctx.catch_rate_factor == 1.0
        assert ctx.sack_rate_factor == 1.0

    def test_factors_are_clamped(self, pff_dir, loader):
        """Extreme stat differences should be clamped to configured bounds."""
        # Use very tight clamp to make clamping obvious
        config = PffConfig(
            enabled=True,
            matchup=MatchupConfig(
                enabled=True,
                pass_defense_sensitivity=0.08,
                factor_clamp=(0.95, 1.05),
                min_games=4,
            ),
        )

        # Extreme spread in coverage stats
        extreme_teams = [
            {
                "team": "BAL",
                "n_players": 3,
                "n_games": 6,
                "catch_rate": 0.40,
                "yards_per_reception": 8.0,
                "grades_coverage_defense": 95.0,
                "interceptions": 2.0,
            },
            {
                "team": "CAR",
                "n_players": 3,
                "n_games": 6,
                "catch_rate": 0.80,
                "yards_per_reception": 18.0,
                "grades_coverage_defense": 35.0,
                "interceptions": 0.1,
            },
            {
                "team": "KC",
                "n_players": 3,
                "n_games": 6,
                "catch_rate": 0.60,
                "yards_per_reception": 13.0,
                "grades_coverage_defense": 65.0,
                "interceptions": 0.8,
            },
        ]
        _write_defense_coverage(pff_dir, 2024, extreme_teams)

        engine = MatchupEngine(config, loader)
        ctx = engine.compute("BAL", "KC", [2024])

        # With tight clamp, BAL elite defense should be clamped at 0.95
        assert ctx.catch_rate_factor >= 0.95
        assert ctx.catch_rate_factor <= 1.05

    def test_different_opponents_produce_different_contexts(
        self, pff_dir, loader, default_config
    ):
        """BAL D vs CAR D should produce measurably different contexts."""
        _write_defense_coverage(pff_dir, 2024, THREE_TEAM_COVERAGE)
        _write_defense_pass_rush(pff_dir, 2024, THREE_TEAM_PASS_RUSH)
        _write_defense_run(pff_dir, 2024, THREE_TEAM_RUN_DEF)

        engine = MatchupEngine(default_config, loader)
        ctx_bal = engine.compute("BAL", "KC", [2024])
        ctx_car = engine.compute("CAR", "KC", [2024])

        # BAL is elite, CAR is weak — all factors should differ
        assert ctx_bal.catch_rate_factor < ctx_car.catch_rate_factor
        assert ctx_bal.pass_yards_factor < ctx_car.pass_yards_factor
        assert ctx_bal.sack_rate_factor > ctx_car.sack_rate_factor

    def test_sack_rate_factor_high_for_elite_pass_rush(
        self, pff_dir, loader, default_config
    ):
        """BAL elite pass rush (win_rate=18.0) should produce sack_rate_factor > 1.0."""
        _write_defense_pass_rush(pff_dir, 2024, THREE_TEAM_PASS_RUSH)

        engine = MatchupEngine(default_config, loader)
        ctx = engine.compute("BAL", "KC", [2024])

        assert ctx.sack_rate_factor > 1.0

    def test_rush_yards_factor_inverted(self, pff_dir, loader, default_config):
        """High stop_percent (BAL) should REDUCE rush_yards_factor (inverted)."""
        _write_defense_run(pff_dir, 2024, THREE_TEAM_RUN_DEF)

        engine = MatchupEngine(default_config, loader)
        ctx_bal = engine.compute("BAL", "KC", [2024])
        ctx_car = engine.compute("CAR", "KC", [2024])

        # BAL has high stop_percent=12.0 → inverted → lower rush_yards_factor
        # CAR has low stop_percent=5.0 → inverted → higher rush_yards_factor
        assert ctx_bal.rush_yards_factor < 1.0
        assert ctx_car.rush_yards_factor > 1.0

    def test_ol_pass_block_factor_inverted(self, pff_dir, loader, default_config):
        """High pbe (PHI) should REDUCE ol_pass_block_factor (inverted = fewer sacks)."""
        _write_offense_pass_blocking(pff_dir, 2024, THREE_TEAM_OL_PASS)

        engine = MatchupEngine(default_config, loader)
        ctx_phi = engine.compute("KC", "PHI", [2024])
        ctx_nyg = engine.compute("KC", "NYG", [2024])

        # PHI has high pbe=92 → inverted → lower ol_pass_block_factor
        # NYG has low pbe=78 → inverted → higher ol_pass_block_factor
        assert ctx_phi.ol_pass_block_factor < 1.0
        assert ctx_nyg.ol_pass_block_factor > 1.0

    def test_ol_run_block_factor_not_inverted(self, pff_dir, loader, default_config):
        """High run_block grade (PHI) should increase ol_run_block_factor (not inverted)."""
        _write_offense_run_blocking(pff_dir, 2024, THREE_TEAM_OL_RUN)

        engine = MatchupEngine(default_config, loader)
        ctx_phi = engine.compute("KC", "PHI", [2024])
        ctx_nyg = engine.compute("KC", "NYG", [2024])

        # PHI has high grades_run_block=85 → factor > 1.0
        # NYG has low grades_run_block=55 → factor < 1.0
        assert ctx_phi.ol_run_block_factor > 1.0
        assert ctx_nyg.ol_run_block_factor < 1.0

    def test_full_matchup_all_facets(self, pff_dir, loader, default_config):
        """End-to-end: all 5 facets produce non-neutral factors for extreme teams."""
        _write_all_facets(
            pff_dir,
            2024,
            THREE_TEAM_COVERAGE,
            THREE_TEAM_PASS_RUSH,
            THREE_TEAM_RUN_DEF,
            THREE_TEAM_OL_PASS,
            THREE_TEAM_OL_RUN,
        )

        engine = MatchupEngine(default_config, loader)
        ctx = engine.compute("BAL", "PHI", [2024])

        # BAL elite defense: catch_rate and pass_yards below 1.0
        assert ctx.catch_rate_factor < 1.0
        assert ctx.pass_yards_factor < 1.0
        assert ctx.sack_rate_factor > 1.0
        # PHI elite OL: ol_pass_block < 1.0 (inverted, good blocking = fewer sacks)
        assert ctx.ol_pass_block_factor < 1.0
        assert ctx.ol_run_block_factor > 1.0

    def test_unknown_team_returns_neutral_for_that_factor(
        self, pff_dir, loader, default_config
    ):
        """A team not in the data should get 1.0 for that factor."""
        _write_defense_coverage(pff_dir, 2024, THREE_TEAM_COVERAGE)

        engine = MatchupEngine(default_config, loader)
        ctx = engine.compute("SEA", "KC", [2024])

        # SEA is not in the data, so defensive factors → 1.0
        assert ctx.catch_rate_factor == 1.0
        assert ctx.pass_yards_factor == 1.0


# ========== Grade fallback tests ==========


class TestGradeFallback:
    """Tests for fallback to PFF grades when games < min_games."""

    def test_insufficient_games_uses_grade_fallback(
        self, pff_dir, loader, default_config
    ):
        """Team with < min_games (4) games should fall back to grade-based factor."""
        # BAL has only 2 games (below min_games=4), but has grade data
        low_game_teams = [
            {
                "team": "BAL",
                "n_players": 3,
                "n_games": 2,  # Below min_games=4
                "catch_rate": 0.55,
                "yards_per_reception": 10.0,
                "grades_coverage_defense": 90.0,
                "interceptions": 1.2,
            },
            {
                "team": "CAR",
                "n_players": 3,
                "n_games": 6,
                "catch_rate": 0.72,
                "yards_per_reception": 14.5,
                "grades_coverage_defense": 48.0,
                "interceptions": 0.3,
            },
            {
                "team": "KC",
                "n_players": 3,
                "n_games": 6,
                "catch_rate": 0.64,
                "yards_per_reception": 12.0,
                "grades_coverage_defense": 65.0,
                "interceptions": 0.7,
            },
        ]
        _write_defense_coverage(pff_dir, 2024, low_game_teams)

        engine = MatchupEngine(default_config, loader)
        ctx = engine.compute("BAL", "KC", [2024])

        # BAL has high grades_coverage_defense=90 → above-average grade → factor > 1.0
        # (grade-based, not primary-stat-based)
        assert ctx.catch_rate_factor != 1.0  # Not neutral — fallback worked

    def test_grade_fallback_has_reduced_sensitivity(
        self, pff_dir, loader
    ):
        """Grade-based factors should use half the normal sensitivity."""
        # Custom config with high sensitivity to make the difference measurable
        config = PffConfig(
            enabled=True,
            matchup=MatchupConfig(
                enabled=True,
                pass_defense_sensitivity=0.20,  # High sensitivity
                factor_clamp=(0.50, 1.50),  # Wide clamp
                min_games=4,
            ),
        )

        # Create two datasets: one with enough games (uses primary stat),
        # one with insufficient games (uses grade fallback)
        sufficient_teams = [
            {
                "team": "BAL",
                "n_players": 3,
                "n_games": 6,
                "catch_rate": 0.55,
                "yards_per_reception": 10.0,
                "grades_coverage_defense": 88.0,
                "interceptions": 1.2,
            },
            {
                "team": "CAR",
                "n_players": 3,
                "n_games": 6,
                "catch_rate": 0.72,
                "yards_per_reception": 14.5,
                "grades_coverage_defense": 48.0,
                "interceptions": 0.3,
            },
            {
                "team": "KC",
                "n_players": 3,
                "n_games": 6,
                "catch_rate": 0.64,
                "yards_per_reception": 12.0,
                "grades_coverage_defense": 65.0,
                "interceptions": 0.7,
            },
        ]
        _write_defense_coverage(pff_dir, 2024, sufficient_teams)

        loader_sufficient = PffLoader(pff_dir)
        engine_sufficient = MatchupEngine(config, loader_sufficient)
        ctx_primary = engine_sufficient.compute("BAL", "KC", [2024])

        # Now make BAL have insufficient games
        insufficient_teams = [
            {
                "team": "BAL",
                "n_players": 3,
                "n_games": 2,  # Below min_games=4
                "catch_rate": 0.55,
                "yards_per_reception": 10.0,
                "grades_coverage_defense": 88.0,
                "interceptions": 1.2,
            },
            {
                "team": "CAR",
                "n_players": 3,
                "n_games": 6,
                "catch_rate": 0.72,
                "yards_per_reception": 14.5,
                "grades_coverage_defense": 48.0,
                "interceptions": 0.3,
            },
            {
                "team": "KC",
                "n_players": 3,
                "n_games": 6,
                "catch_rate": 0.64,
                "yards_per_reception": 12.0,
                "grades_coverage_defense": 65.0,
                "interceptions": 0.7,
            },
        ]

        # Write to a fresh dir so cache doesn't interfere
        pff_dir2 = pff_dir.parent / "pff2" / "processed" / "nfl"
        pff_dir2.mkdir(parents=True)
        _write_defense_coverage(pff_dir2, 2024, insufficient_teams)

        loader_insuf = PffLoader(pff_dir2)
        engine_insuf = MatchupEngine(config, loader_insuf)
        ctx_grade = engine_insuf.compute("BAL", "KC", [2024])

        # Both should shift catch_rate_factor away from 1.0,
        # but grade-based should shift less due to GRADE_SENSITIVITY_DISCOUNT
        primary_shift = abs(ctx_primary.catch_rate_factor - 1.0)
        grade_shift = abs(ctx_grade.catch_rate_factor - 1.0)

        # Grade shift should be smaller (half sensitivity)
        # We can't guarantee exact ratio due to different stat distributions,
        # but grade should not be larger than primary
        assert grade_shift < primary_shift or grade_shift == pytest.approx(
            0.0, abs=0.01
        )


# ========== Caching tests ==========


class TestMatchupCaching:
    """Tests for DataFrame caching in MatchupEngine."""

    def test_cached_dataframes_reused(self, pff_dir, loader, default_config):
        """Calling compute twice should reuse cached DataFrames."""
        _write_defense_coverage(pff_dir, 2024, THREE_TEAM_COVERAGE)

        engine = MatchupEngine(default_config, loader)
        ctx1 = engine.compute("BAL", "KC", [2024])
        ctx2 = engine.compute("CAR", "KC", [2024])

        # Both used the same facet+seasons — cache should have been hit
        assert len(engine._cache) >= 1
        # Results should differ (different defense teams)
        assert ctx1.catch_rate_factor != ctx2.catch_rate_factor

    def test_different_seasons_cached_separately(self, pff_dir, loader, default_config):
        """Different season lists should get separate cache entries."""
        _write_defense_coverage(pff_dir, 2023, THREE_TEAM_COVERAGE)
        _write_defense_coverage(pff_dir, 2024, THREE_TEAM_COVERAGE)

        engine = MatchupEngine(default_config, loader)
        engine.compute("BAL", "KC", [2023])
        engine.compute("BAL", "KC", [2024])

        # Should have separate cache entries for each season
        keys = list(engine._cache.keys())
        assert any("2023" in k for k in keys)
        assert any("2024" in k for k in keys)


# ========== League stats aggregation tests ==========


class TestLeagueStatsAggregation:
    """Tests that league stats aggregate per-team first, then across teams."""

    def test_unequal_player_counts_dont_skew(self, pff_dir, loader, default_config):
        """A team with more players shouldn't dominate the league average."""
        # BAL has 10 players, CAR has 1, KC has 1
        # If we don't aggregate per-team first, BAL would dominate
        unequal_teams = [
            {
                "team": "BAL",
                "n_players": 10,  # Many more players
                "n_games": 6,
                "catch_rate": 0.50,
                "yards_per_reception": 9.0,
                "grades_coverage_defense": 90.0,
                "interceptions": 1.5,
            },
            {
                "team": "CAR",
                "n_players": 1,
                "n_games": 6,
                "catch_rate": 0.80,
                "yards_per_reception": 16.0,
                "grades_coverage_defense": 40.0,
                "interceptions": 0.2,
            },
            {
                "team": "KC",
                "n_players": 1,
                "n_games": 6,
                "catch_rate": 0.65,
                "yards_per_reception": 12.0,
                "grades_coverage_defense": 65.0,
                "interceptions": 0.7,
            },
        ]
        _write_defense_coverage(pff_dir, 2024, unequal_teams)

        engine = MatchupEngine(default_config, loader)

        # Compute league stats directly
        df = loader.load_facet("defense_coverage", [2024])
        league_avg, league_std = engine._compute_league_stats(df, "catch_rate")

        # Per-team means: BAL=0.50, CAR=0.80, KC=0.65
        # League avg should be mean of those = 0.65
        # NOT skewed toward BAL's 0.50 (which would happen without per-team agg)
        assert league_avg == pytest.approx(0.65, abs=0.01)

    def test_single_team_returns_zero_std(self, pff_dir, loader, default_config):
        """With only one team, std should be 0 (can't compute deviation)."""
        single_team = [
            {
                "team": "BAL",
                "n_players": 3,
                "n_games": 6,
                "catch_rate": 0.55,
                "yards_per_reception": 10.0,
                "grades_coverage_defense": 88.0,
                "interceptions": 1.2,
            },
        ]
        _write_defense_coverage(pff_dir, 2024, single_team)

        engine = MatchupEngine(default_config, loader)
        df = loader.load_facet("defense_coverage", [2024])
        league_avg, league_std = engine._compute_league_stats(df, "catch_rate")

        assert league_avg == pytest.approx(0.55, abs=0.01)
        assert league_std == 0.0

    def test_single_team_produces_neutral_factor(
        self, pff_dir, loader, default_config
    ):
        """With only one team in the data, std=0 → factor=1.0."""
        single_team = [
            {
                "team": "BAL",
                "n_players": 3,
                "n_games": 6,
                "catch_rate": 0.55,
                "yards_per_reception": 10.0,
                "grades_coverage_defense": 88.0,
                "interceptions": 1.2,
            },
        ]
        _write_defense_coverage(pff_dir, 2024, single_team)

        engine = MatchupEngine(default_config, loader)
        ctx = engine.compute("BAL", "KC", [2024])

        # Only one team → std = 0 → all factors 1.0
        assert ctx.catch_rate_factor == 1.0


# ========== Numeric precision tests ==========


class TestNumericPrecision:
    """Verify specific numeric outcomes for known inputs."""

    def test_exact_catch_rate_factor_for_known_data(self, pff_dir, loader):
        """Compute exact factor for BAL with known 3-team data."""
        config = PffConfig(
            enabled=True,
            matchup=MatchupConfig(
                enabled=True,
                pass_defense_sensitivity=0.08,
                factor_clamp=(0.50, 1.50),  # Wide clamp to avoid clamping
                min_games=4,
            ),
        )

        # BAL=0.55, CAR=0.72, KC=0.64
        # Per-team means: [0.55, 0.72, 0.64]
        # League avg = (0.55 + 0.72 + 0.64) / 3 = 0.6367
        # League std = std([0.55, 0.72, 0.64])
        import numpy as np

        team_means = [0.55, 0.72, 0.64]
        expected_avg = np.mean(team_means)
        expected_std = np.std(team_means, ddof=1)  # polars uses ddof=1
        expected_z = (0.55 - expected_avg) / expected_std
        expected_factor = 1.0 + expected_z * 0.08

        _write_defense_coverage(pff_dir, 2024, THREE_TEAM_COVERAGE)
        engine = MatchupEngine(config, loader)
        ctx = engine.compute("BAL", "KC", [2024])

        assert ctx.catch_rate_factor == pytest.approx(expected_factor, abs=0.005)

    def test_exact_inverted_factor(self, pff_dir, loader):
        """Verify inverted factor math for rush_yards_factor."""
        config = PffConfig(
            enabled=True,
            matchup=MatchupConfig(
                enabled=True,
                run_defense_sensitivity=0.08,
                factor_clamp=(0.50, 1.50),
                min_games=4,
            ),
        )

        # BAL stop_percent=12.0, CAR=5.0, KC=8.5
        import numpy as np

        team_means = [12.0, 5.0, 8.5]
        expected_avg = np.mean(team_means)
        expected_std = np.std(team_means, ddof=1)
        expected_z = (12.0 - expected_avg) / expected_std
        normal_factor = 1.0 + expected_z * 0.08
        expected_inverted = 2.0 - normal_factor

        _write_defense_run(pff_dir, 2024, THREE_TEAM_RUN_DEF)
        engine = MatchupEngine(config, loader)
        ctx = engine.compute("BAL", "KC", [2024])

        assert ctx.rush_yards_factor == pytest.approx(expected_inverted, abs=0.005)

"""Tests for PFF coverage engine — CB profile building."""

import polars as pl
import pytest

from fantasy_sim.data.pff.coverage import (
    CB_ALIGNMENTS,
    CoverageEngine,
    _CbProfile,
)
from fantasy_sim.data.pff.loader import PffLoader
from fantasy_sim.data.pff.models import CoverageConfig


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
    """CoverageConfig with defaults."""
    return CoverageConfig()


# ---------- Parquet helpers ----------


def _write_coverage_matchup(pff_dir, season, type1_rows, type2_rows):
    """Write defense_coverage_matchup parquet with both row types.

    type1_rows: list of dicts with player_id, position, team, week, game_id,
        player, franchise_id, season (auto-filled), etc.
    type2_rows: list of dicts with player_id (receiver), coverage_player_id
        (defender), week, game_id, targets, receptions, yards,
        grades_coverage_defense, grades_overall, season (auto-filled).
    """
    all_rows = []
    for r in type1_rows:
        row = {
            "player_id": r["player_id"],
            "player": r.get("player", f"Player_{r['player_id']}"),
            "team": r.get("team"),
            "franchise_id": r.get("franchise_id", r.get("team")),
            "position": r.get("position"),
            "season": season,
            "week": r.get("week", 1),
            "game_id": r.get("game_id", 9000 + r.get("week", 1)),
            "coverage_player_id": None,
            "targets": r.get("targets", 0),
            "receptions": r.get("receptions", 0),
            "yards": r.get("yards", 0.0),
            "grades_coverage_defense": r.get("grades_coverage_defense"),
            "grades_overall": r.get("grades_overall"),
        }
        all_rows.append(row)

    for r in type2_rows:
        row = {
            "player_id": r["player_id"],
            "player": None,
            "team": None,
            "franchise_id": None,
            "position": None,
            "season": season,
            "week": r.get("week", 1),
            "game_id": r.get("game_id", 9000 + r.get("week", 1)),
            "coverage_player_id": r["coverage_player_id"],
            "targets": r.get("targets", 0),
            "receptions": r.get("receptions", 0),
            "yards": r.get("yards", 0.0),
            "grades_coverage_defense": r.get("grades_coverage_defense"),
            "grades_overall": r.get("grades_overall"),
        }
        all_rows.append(row)

    schema = {
        "player_id": pl.Int64,
        "player": pl.Utf8,
        "team": pl.Utf8,
        "franchise_id": pl.Utf8,
        "position": pl.Utf8,
        "season": pl.Int64,
        "week": pl.Int64,
        "game_id": pl.Int64,
        "coverage_player_id": pl.Int64,
        "targets": pl.Int64,
        "receptions": pl.Int64,
        "yards": pl.Float64,
        "grades_coverage_defense": pl.Float64,
        "grades_overall": pl.Float64,
    }
    if all_rows:
        df = pl.DataFrame(all_rows).cast({
            k: v for k, v in schema.items()
            if k in pl.DataFrame(all_rows).columns
        })
    else:
        df = pl.DataFrame(schema=schema)
    path = pff_dir / f"defense_coverage_matchup_{season}.parquet"
    df.write_parquet(path)
    return path


# ---------- TestBuildCbProfiles ----------


class TestBuildCbProfiles:
    """Tests for CoverageEngine._build_cb_profiles."""

    def test_identifies_starting_cbs_by_alignment(self, pff_dir, loader, default_config):
        """Two LCBs on BUF, one with more targets (starter).

        Verify correct starter is identified and stats are aggregated correctly.
        """
        # Type 1: Two LCBs on BUF across 3 weeks
        # CB 101 appears in 3 games, CB 102 appears in 2 games
        type1_rows = []
        for week in [1, 2, 3]:
            type1_rows.append({
                "player_id": 101,
                "player": "CB_Starter",
                "team": "BUF",
                "position": "LCB",
                "week": week,
                "game_id": 9000 + week,
            })
        for week in [1, 2]:
            type1_rows.append({
                "player_id": 102,
                "player": "CB_Backup",
                "team": "BUF",
                "position": "LCB",
                "week": week,
                "game_id": 9000 + week,
            })
        # Also add an RCB so we can verify alignment isolation
        for week in [1, 2, 3]:
            type1_rows.append({
                "player_id": 201,
                "player": "CB_Right",
                "team": "BUF",
                "position": "RCB",
                "week": week,
                "game_id": 9000 + week,
            })

        # Type 2: Matchup rows — CB 101 gets 30 total targets, CB 102 gets 10
        type2_rows = []
        # CB 101: 3 games, 10 targets each = 30 total
        for week in [1, 2, 3]:
            type2_rows.append({
                "player_id": 500,  # receiver
                "coverage_player_id": 101,
                "week": week,
                "game_id": 9000 + week,
                "targets": 10,
                "receptions": 6,
                "yards": 80.0,
                "grades_coverage_defense": 70.0,
                "grades_overall": 65.0,
            })
        # CB 102: 2 games, 5 targets each = 10 total
        for week in [1, 2]:
            type2_rows.append({
                "player_id": 501,  # different receiver
                "coverage_player_id": 102,
                "week": week,
                "game_id": 9000 + week,
                "targets": 5,
                "receptions": 3,
                "yards": 40.0,
                "grades_coverage_defense": 60.0,
                "grades_overall": 55.0,
            })
        # RCB 201: 3 games, 8 targets each = 24 total
        for week in [1, 2, 3]:
            type2_rows.append({
                "player_id": 502,
                "coverage_player_id": 201,
                "week": week,
                "game_id": 9000 + week,
                "targets": 8,
                "receptions": 5,
                "yards": 60.0,
                "grades_coverage_defense": 75.0,
                "grades_overall": 70.0,
            })

        _write_coverage_matchup(pff_dir, 2024, type1_rows, type2_rows)

        engine = CoverageEngine(loader, default_config)
        profiles = engine._build_cb_profiles("BUF", 2024, max_week=10)

        # Should have LCB and RCB starters
        assert "LCB" in profiles
        assert "RCB" in profiles

        # LCB starter should be CB 101 (30 targets > CB 102's 10)
        lcb = profiles["LCB"]
        assert lcb.player_id == 101
        assert lcb.team == "BUF"
        assert lcb.alignment == "LCB"
        assert lcb.total_targets == 30
        assert lcb.games_played == 3
        # catch_rate = 18 receptions / 30 targets = 0.6
        assert lcb.catch_rate_allowed == pytest.approx(18 / 30, abs=0.01)
        # ypr = 240 yards / 18 receptions
        assert lcb.ypr_allowed == pytest.approx(240 / 18, abs=0.1)
        # coverage_grade = target-weighted: all same grade 70.0
        assert lcb.coverage_grade == pytest.approx(70.0, abs=0.1)

        # RCB starter should be CB 201
        rcb = profiles["RCB"]
        assert rcb.player_id == 201
        assert rcb.total_targets == 24
        assert rcb.games_played == 3

    def test_rolling_window_filters_future_weeks(self, pff_dir, loader, default_config):
        """Data across weeks 1-8, max_week=5 should only use weeks 1-4."""
        type1_rows = []
        type2_rows = []

        # CB on KC across weeks 1-8
        for week in range(1, 9):
            type1_rows.append({
                "player_id": 301,
                "player": "CB_KC",
                "team": "KC",
                "position": "LCB",
                "week": week,
                "game_id": 9000 + week,
            })
            # Matchup rows: 5 targets per week
            type2_rows.append({
                "player_id": 600,
                "coverage_player_id": 301,
                "week": week,
                "game_id": 9000 + week,
                "targets": 5,
                "receptions": 3,
                "yards": 40.0,
                "grades_coverage_defense": 65.0,
                "grades_overall": 60.0,
            })

        _write_coverage_matchup(pff_dir, 2024, type1_rows, type2_rows)

        engine = CoverageEngine(loader, default_config)
        profiles = engine._build_cb_profiles("KC", 2024, max_week=5)

        # Should only see weeks 1-4 (week < 5)
        assert "LCB" in profiles
        lcb = profiles["LCB"]
        assert lcb.total_targets == 20  # 4 weeks * 5 targets
        assert lcb.games_played == 4
        assert lcb.catch_rate_allowed == pytest.approx(12 / 20, abs=0.01)

    def test_empty_data_returns_empty_profiles(self, pff_dir, loader, default_config):
        """No data returns empty dict."""
        # Write an empty parquet (no type1 rows for the team)
        _write_coverage_matchup(pff_dir, 2024, [], [])

        engine = CoverageEngine(loader, default_config)
        profiles = engine._build_cb_profiles("BUF", 2024, max_week=10)

        assert profiles == {}

    def test_grades_overall_fallback(self, pff_dir, loader, default_config):
        """When grades_coverage_defense is null, falls back to grades_overall."""
        type1_rows = [
            {
                "player_id": 401,
                "player": "CB_Fallback",
                "team": "SF",
                "position": "LCB",
                "week": 1,
                "game_id": 9001,
            },
        ]
        type2_rows = [
            {
                "player_id": 700,
                "coverage_player_id": 401,
                "week": 1,
                "game_id": 9001,
                "targets": 8,
                "receptions": 5,
                "yards": 60.0,
                "grades_coverage_defense": None,
                "grades_overall": 72.0,
            },
        ]

        _write_coverage_matchup(pff_dir, 2024, type1_rows, type2_rows)

        engine = CoverageEngine(loader, default_config)
        profiles = engine._build_cb_profiles("SF", 2024, max_week=10)

        assert "LCB" in profiles
        # Should use grades_overall as fallback
        assert profiles["LCB"].coverage_grade == pytest.approx(72.0, abs=0.1)


class TestComputeStub:
    """Tests for CoverageEngine.compute() stub."""

    def test_compute_returns_empty_dict(self, pff_dir, loader, default_config):
        """Stub compute() should return empty dict."""
        engine = CoverageEngine(loader, default_config)
        result = engine.compute(
            defense_team="BUF",
            roster=None,
            target_season=2024,
            max_week=10,
        )
        assert result == {}


class TestEarlySeasonBlend:
    """Tests for CoverageEngine early-season blending in _build_cb_profiles."""

    def test_blends_with_previous_season_when_few_games(self, pff_dir, loader):
        """When current season has < min_games, blend with previous season."""
        # 2023 parquet: CB 200 (LCB, BUF) with 9 games, catch_rate_allowed = 2/5 = 0.40
        type1_rows_2023 = []
        type2_rows_2023 = []
        for week in range(1, 10):  # 9 weeks
            type1_rows_2023.append({
                "player_id": 200,
                "player": "CB_Vet",
                "team": "BUF",
                "position": "LCB",
                "week": week,
                "game_id": 8000 + week,
            })
            type2_rows_2023.append({
                "player_id": 600,
                "coverage_player_id": 200,
                "week": week,
                "game_id": 8000 + week,
                "targets": 5,
                "receptions": 2,  # 18/45 = 0.40 catch_rate_allowed
                "yards": 20.0,
                "grades_coverage_defense": 70.0,
                "grades_overall": 65.0,
            })
        _write_coverage_matchup(pff_dir, 2023, type1_rows_2023, type2_rows_2023)

        # 2024 parquet: CB 200 (LCB, BUF) with 2 games, catch_rate_allowed = 4/5 = 0.80
        type1_rows_2024 = []
        type2_rows_2024 = []
        for week in range(1, 3):  # 2 weeks
            type1_rows_2024.append({
                "player_id": 200,
                "player": "CB_Vet",
                "team": "BUF",
                "position": "LCB",
                "week": week,
                "game_id": 9000 + week,
            })
            type2_rows_2024.append({
                "player_id": 600,
                "coverage_player_id": 200,
                "week": week,
                "game_id": 9000 + week,
                "targets": 5,
                "receptions": 4,  # 8/10 = 0.80 catch_rate_allowed
                "yards": 40.0,
                "grades_coverage_defense": 75.0,
                "grades_overall": 70.0,
            })
        _write_coverage_matchup(pff_dir, 2024, type1_rows_2024, type2_rows_2024)

        # Config: min_games=4
        config = CoverageConfig(min_games=4)
        engine = CoverageEngine(loader, config)
        # max_week=3 so only weeks 1-2 are visible (week < 3) → 2 games
        profiles = engine._build_cb_profiles("BUF", target_season=2024, max_week=3)

        # blend_weight = 2 / 4 = 0.5
        # blended = 0.5 * 0.80 + 0.5 * 0.40 = 0.60
        assert "LCB" in profiles
        lcb = profiles["LCB"]
        assert lcb.catch_rate_allowed == pytest.approx(0.60, abs=0.01)

    def test_no_blend_when_enough_games(self, pff_dir, loader):
        """When current season has >= min_games, use current season only."""
        # 2023 parquet: CB 200 (LCB, BUF) with 9 games, catch_rate_allowed = 0.40
        type1_rows_2023 = []
        type2_rows_2023 = []
        for week in range(1, 10):
            type1_rows_2023.append({
                "player_id": 200,
                "player": "CB_Vet",
                "team": "BUF",
                "position": "LCB",
                "week": week,
                "game_id": 8000 + week,
            })
            type2_rows_2023.append({
                "player_id": 600,
                "coverage_player_id": 200,
                "week": week,
                "game_id": 8000 + week,
                "targets": 5,
                "receptions": 2,
                "yards": 20.0,
                "grades_coverage_defense": 70.0,
                "grades_overall": 65.0,
            })
        _write_coverage_matchup(pff_dir, 2023, type1_rows_2023, type2_rows_2023)

        # 2024 parquet: CB 200 (LCB, BUF) with 6 games, catch_rate_allowed = 0.80
        type1_rows_2024 = []
        type2_rows_2024 = []
        for week in range(1, 7):  # 6 weeks
            type1_rows_2024.append({
                "player_id": 200,
                "player": "CB_Vet",
                "team": "BUF",
                "position": "LCB",
                "week": week,
                "game_id": 9000 + week,
            })
            type2_rows_2024.append({
                "player_id": 600,
                "coverage_player_id": 200,
                "week": week,
                "game_id": 9000 + week,
                "targets": 5,
                "receptions": 4,
                "yards": 40.0,
                "grades_coverage_defense": 75.0,
                "grades_overall": 70.0,
            })
        _write_coverage_matchup(pff_dir, 2024, type1_rows_2024, type2_rows_2024)

        # Config: min_games=4; current season has 6 games >= 4
        config = CoverageConfig(min_games=4)
        engine = CoverageEngine(loader, config)
        # max_week=10 so all 6 weeks are visible
        profiles = engine._build_cb_profiles("BUF", target_season=2024, max_week=10)

        # Should use current season only: catch_rate_allowed = 0.80
        assert "LCB" in profiles
        lcb = profiles["LCB"]
        assert lcb.catch_rate_allowed == pytest.approx(0.80, abs=0.01)

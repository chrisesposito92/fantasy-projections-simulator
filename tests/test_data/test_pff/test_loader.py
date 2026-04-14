"""Tests for PFF data loader and crosswalk builder."""

import polars as pl
import pytest

from fantasy_sim.data.pff.loader import (
    FANTASY_POSITIONS,
    PFF_TO_FANTASY_POSITION,
    PFF_TO_NFL_TEAM,
    PffLoader,
)


# ---------- Fixtures ----------


@pytest.fixture
def pff_dir(tmp_path):
    """Create a temporary PFF data directory with sample parquets."""
    d = tmp_path / "pff" / "processed" / "nfl"
    d.mkdir(parents=True)
    return d


def _make_receiving_parquet(pff_dir, season, rows=None):
    """Create a minimal receiving_summary parquet."""
    if rows is None:
        rows = {
            "player_id": [100, 200, 300],
            "player": ["Alice Smith", "Bob Jones", "Carol Lee"],
            "team": ["ARZ", "BLT", "KC"],
            "position": ["LWR", "TE-L", "HB"],
            "season": [season] * 3,
            "week": [1, 1, 1],
            "game_id": [1001, 1001, 1001],
            "franchise_id": [1, 2, 3],
            "jersey_number": [10, 20, 30],
            "status": ["ACT", "ACT", "ACT"],
            "drop_rate": [5.0, 8.0, 3.0],
            "caught_percent": [68.0, 55.0, 72.0],
            "grades_pass_route": [85.0, 60.0, 90.0],
            "yprr": [2.1, 1.2, 2.5],
            "targets": [8, 5, 6],
        }
    df = pl.DataFrame(rows)
    df.write_parquet(pff_dir / f"receiving_summary_{season}.parquet")
    return df


def _make_roster_df():
    """Create a minimal nflverse-style roster DataFrame."""
    return pl.DataFrame({
        "player_id": ["G001", "G002", "G003", "G004"],
        "player_name": ["Alice Smith", "Bob Jones", "Carol Lee", "Dave Wu"],
        "team": ["ARI", "BAL", "KC", "KC"],
        "position": ["WR", "TE", "RB", "QB"],
        "pff_id": ["100", None, None, "400"],
    })


# ---------- PffLoader.is_available ----------


class TestIsAvailable:
    def test_returns_true_when_parquets_exist(self, pff_dir):
        _make_receiving_parquet(pff_dir, 2024)
        loader = PffLoader(pff_dir)
        assert loader.is_available() is True

    def test_returns_false_when_dir_missing(self, tmp_path):
        loader = PffLoader(tmp_path / "nonexistent")
        assert loader.is_available() is False

    def test_returns_false_when_dir_empty(self, pff_dir):
        loader = PffLoader(pff_dir)
        assert loader.is_available() is False


# ---------- PffLoader.load_facet ----------


class TestLoadFacet:
    def test_loads_single_season(self, pff_dir):
        _make_receiving_parquet(pff_dir, 2024)
        loader = PffLoader(pff_dir)
        df = loader.load_facet("receiving_summary", [2024])
        assert len(df) == 3

    def test_concatenates_multiple_seasons(self, pff_dir):
        _make_receiving_parquet(pff_dir, 2023)
        _make_receiving_parquet(pff_dir, 2024)
        loader = PffLoader(pff_dir)
        df = loader.load_facet("receiving_summary", [2023, 2024])
        assert len(df) == 6

    def test_returns_empty_for_missing_facet(self, pff_dir):
        loader = PffLoader(pff_dir)
        df = loader.load_facet("nonexistent_facet", [2024])
        assert df.is_empty()

    def test_normalizes_team_abbreviations(self, pff_dir):
        _make_receiving_parquet(pff_dir, 2024)
        loader = PffLoader(pff_dir)
        df = loader.load_facet("receiving_summary", [2024])
        teams = df["team"].to_list()
        # ARZ should become ARI, BLT should become BAL
        assert "ARI" in teams
        assert "BAL" in teams
        assert "ARZ" not in teams
        assert "BLT" not in teams
        # KC should pass through unchanged
        assert "KC" in teams

    def test_maps_positions_to_fantasy(self, pff_dir):
        _make_receiving_parquet(pff_dir, 2024)
        loader = PffLoader(pff_dir)
        df = loader.load_facet("receiving_summary", [2024])
        positions = df["position"].to_list()
        # LWR → WR, TE-L → TE, HB → RB
        assert "WR" in positions
        assert "TE" in positions
        assert "RB" in positions
        assert "LWR" not in positions

    def test_preserves_pff_position_column(self, pff_dir):
        _make_receiving_parquet(pff_dir, 2024)
        loader = PffLoader(pff_dir)
        df = loader.load_facet("receiving_summary", [2024])
        assert "pff_position" in df.columns
        pff_positions = df["pff_position"].to_list()
        assert "LWR" in pff_positions


# ---------- Team/Position mappings ----------


class TestMappings:
    def test_all_pff_teams_map_to_nfl(self):
        for pff, nfl in PFF_TO_NFL_TEAM.items():
            assert len(pff) == 3
            assert len(nfl) == 3

    def test_known_team_mappings(self):
        assert PFF_TO_NFL_TEAM["ARZ"] == "ARI"
        assert PFF_TO_NFL_TEAM["BLT"] == "BAL"
        assert PFF_TO_NFL_TEAM["CLV"] == "CLE"
        assert PFF_TO_NFL_TEAM["HST"] == "HOU"

    def test_pff_positions_map_to_fantasy(self):
        assert PFF_TO_FANTASY_POSITION["LWR"] == "WR"
        assert PFF_TO_FANTASY_POSITION["RWR"] == "WR"
        assert PFF_TO_FANTASY_POSITION["SLWR"] == "WR"
        assert PFF_TO_FANTASY_POSITION["SRWR"] == "WR"
        assert PFF_TO_FANTASY_POSITION["HB"] == "RB"
        assert PFF_TO_FANTASY_POSITION["FB"] == "RB"
        assert PFF_TO_FANTASY_POSITION["TE-L"] == "TE"
        assert PFF_TO_FANTASY_POSITION["TE-R"] == "TE"
        assert PFF_TO_FANTASY_POSITION["QB"] == "QB"

    def test_fantasy_positions_set(self):
        assert FANTASY_POSITIONS == {"QB", "RB", "WR", "TE"}


# ---------- PffLoader.aggregate_player_stats ----------


class TestAggregatePlayerStats:
    def test_aggregates_across_games(self, pff_dir):
        # Two games for same player
        rows = {
            "player_id": [100, 100],
            "player": ["Alice Smith", "Alice Smith"],
            "team": ["KC", "KC"],
            "position": ["WR", "WR"],
            "season": [2024, 2024],
            "week": [1, 2],
            "game_id": [1001, 1002],
            "franchise_id": [1, 1],
            "jersey_number": [10, 10],
            "status": ["ACT", "ACT"],
            "drop_rate": [4.0, 6.0],
            "targets": [8, 10],
        }
        _make_receiving_parquet(pff_dir, 2024, rows)
        loader = PffLoader(pff_dir)
        agg = loader.aggregate_player_stats("receiving_summary", [2024])
        assert len(agg) == 1
        # Unweighted mean
        row = agg.row(0, named=True)
        assert row["drop_rate"] == pytest.approx(5.0, abs=0.01)
        assert row["games"] == 2

    def test_season_weights_applied(self, pff_dir):
        # Season 2023: drop_rate=10, season 2024: drop_rate=2
        rows_2023 = {
            "player_id": [100],
            "player": ["Alice"],
            "team": ["KC"],
            "position": ["WR"],
            "season": [2023],
            "week": [1],
            "game_id": [1001],
            "franchise_id": [1],
            "jersey_number": [10],
            "status": ["ACT"],
            "drop_rate": [10.0],
            "targets": [5],
        }
        rows_2024 = {
            "player_id": [100],
            "player": ["Alice"],
            "team": ["KC"],
            "position": ["WR"],
            "season": [2024],
            "week": [1],
            "game_id": [2001],
            "franchise_id": [1],
            "jersey_number": [10],
            "status": ["ACT"],
            "drop_rate": [2.0],
            "targets": [5],
        }
        _make_receiving_parquet(pff_dir, 2023, rows_2023)
        _make_receiving_parquet(pff_dir, 2024, rows_2024)
        loader = PffLoader(pff_dir)

        # Weight 2024 3x more than 2023
        agg = loader.aggregate_player_stats(
            "receiving_summary", [2023, 2024],
            season_weights={2023: 1.0, 2024: 3.0},
        )
        row = agg.row(0, named=True)
        # Weighted: (10*1 + 2*3) / (1+3) = 16/4 = 4.0
        assert row["drop_rate"] == pytest.approx(4.0, abs=0.01)

    def test_empty_when_no_data(self, pff_dir):
        loader = PffLoader(pff_dir)
        agg = loader.aggregate_player_stats("receiving_summary", [2024])
        assert agg.is_empty()


# ---------- PffLoader.build_crosswalk ----------


class TestBuildCrosswalk:
    def test_layer1_pff_id_match(self, pff_dir):
        _make_receiving_parquet(pff_dir, 2024)
        loader = PffLoader(pff_dir)
        pff_data = loader.load_facet("receiving_summary", [2024])
        roster = _make_roster_df()

        crosswalk = loader.build_crosswalk(pff_data, roster, 2024)
        # Player 100 matches via pff_id = "100"
        assert crosswalk[100] == "G001"

    def test_layer2_name_team_match(self, pff_dir):
        _make_receiving_parquet(pff_dir, 2024)
        loader = PffLoader(pff_dir)
        pff_data = loader.load_facet("receiving_summary", [2024])
        roster = _make_roster_df()

        crosswalk = loader.build_crosswalk(pff_data, roster, 2024)
        # Player 200 (Bob Jones, BAL) matches via name+team (no pff_id)
        assert crosswalk[200] == "G002"
        # Player 300 (Carol Lee, KC) matches via name+team
        assert crosswalk[300] == "G003"

    def test_unmatched_player_excluded(self, pff_dir):
        rows = {
            "player_id": [999],
            "player": ["Unknown Player"],
            "team": ["KC"],
            "position": ["WR"],
            "season": [2024],
            "week": [1],
            "game_id": [1001],
            "franchise_id": [1],
            "jersey_number": [99],
            "status": ["ACT"],
            "drop_rate": [5.0],
            "targets": [3],
        }
        _make_receiving_parquet(pff_dir, 2024, rows)
        loader = PffLoader(pff_dir)
        pff_data = loader.load_facet("receiving_summary", [2024])
        roster = _make_roster_df()

        crosswalk = loader.build_crosswalk(pff_data, roster, 2024)
        assert 999 not in crosswalk

    def test_crosswalk_cached_per_season(self, pff_dir):
        _make_receiving_parquet(pff_dir, 2024)
        loader = PffLoader(pff_dir)
        pff_data = loader.load_facet("receiving_summary", [2024])
        roster = _make_roster_df()

        cw1 = loader.build_crosswalk(pff_data, roster, 2024)
        cw2 = loader.build_crosswalk(pff_data, roster, 2024)
        assert cw1 is cw2  # Same object from cache

    def test_empty_roster_returns_empty_crosswalk(self, pff_dir):
        _make_receiving_parquet(pff_dir, 2024)
        loader = PffLoader(pff_dir)
        pff_data = loader.load_facet("receiving_summary", [2024])
        empty_roster = pl.DataFrame({
            "player_id": [],
            "player_name": [],
            "team": [],
            "position": [],
            "pff_id": [],
        })

        crosswalk = loader.build_crosswalk(pff_data, empty_roster, 2024)
        assert len(crosswalk) == 0

    def test_latest_pff_team_wins_for_name_team_fallback_when_pff_id_missing(self, tmp_path):
        loader = PffLoader(tmp_path / "pff" / "processed" / "nfl")
        pff_data = pl.DataFrame(
            {
                "player_id": [700, 700],
                "player": ["Transferred QB", "Transferred QB"],
                "team": ["LAR", "PIT"],
                "season": [2023, 2024],
                "week": [18, 1],
            }
        )
        roster = pl.DataFrame(
            {
                "player_id": ["GSIS700"],
                "player_name": ["Transferred QB"],
                "team": ["PIT"],
                "position": ["QB"],
                "pff_id": [None],
            }
        )

        crosswalk = loader.build_crosswalk(pff_data, roster, 2024)

        assert crosswalk == {700: "GSIS700"}

    def test_name_team_fallback_can_match_earlier_team_when_later_team_exists(self, tmp_path):
        loader = PffLoader(tmp_path / "pff" / "processed" / "nfl")
        pff_data = pl.DataFrame(
            {
                "player_id": [701, 701],
                "player": ["Moved Player", "Moved Player"],
                "team": ["KC", "PIT"],
                "season": [2024, 2024],
                "week": [3, 10],
            }
        )
        roster = pl.DataFrame(
            {
                "player_id": ["GSIS701"],
                "player_name": ["Moved Player"],
                "team": ["KC"],
                "position": ["QB"],
                "pff_id": [None],
            }
        )

        crosswalk = loader.build_crosswalk(pff_data, roster, 2024)

        assert crosswalk == {701: "GSIS701"}


# ---------- PffLoader.load_ncaa_facet ----------


class TestLoadNcaaFacet:
    def test_load_ncaa_facet_single_season(self, tmp_path):
        ncaa_dir = tmp_path / "pff" / "processed" / "ncaa"
        ncaa_dir.mkdir(parents=True)
        df = pl.DataFrame({
            "player_id": [1, 2],
            "player": ["Player A", "Player B"],
            "team": ["Alabama", "Ohio State"],
            "position": ["WR", "RB"],
            "grades_pass_route": [85.0, 72.0],
            "season": [2024, 2024],
        })
        df.write_parquet(ncaa_dir / "receiving_summary_2024.parquet")

        loader = PffLoader(tmp_path / "pff" / "processed" / "nfl")
        result = loader.load_ncaa_facet("receiving_summary", [2024], ncaa_dir=ncaa_dir)
        assert len(result) == 2

    def test_load_ncaa_facet_multiple_seasons(self, tmp_path):
        ncaa_dir = tmp_path / "pff" / "processed" / "ncaa"
        ncaa_dir.mkdir(parents=True)
        for season in [2023, 2024]:
            df = pl.DataFrame({
                "player_id": [1],
                "player": ["Player A"],
                "team": ["Alabama"],
                "season": [season],
            })
            df.write_parquet(ncaa_dir / f"receiving_summary_{season}.parquet")

        loader = PffLoader(tmp_path / "pff" / "processed" / "nfl")
        result = loader.load_ncaa_facet("receiving_summary", [2023, 2024], ncaa_dir=ncaa_dir)
        assert len(result) == 2

    def test_load_ncaa_facet_missing_file_returns_empty(self, tmp_path):
        ncaa_dir = tmp_path / "pff" / "processed" / "ncaa"
        ncaa_dir.mkdir(parents=True)

        loader = PffLoader(tmp_path / "pff" / "processed" / "nfl")
        result = loader.load_ncaa_facet("receiving_summary", [2024], ncaa_dir=ncaa_dir)
        assert result.is_empty()

    def test_load_ncaa_facet_uses_default_dir(self, tmp_path):
        """When ncaa_dir is None, uses DEFAULT_NCAA_DIR.

        If the default dir exists with real data, result is non-empty;
        if it doesn't exist, result is empty. Either way, no crash.
        """
        loader = PffLoader(tmp_path / "pff" / "processed" / "nfl")
        # Use a season that will never have real data
        result = loader.load_ncaa_facet("receiving_summary", [1900])
        assert result.is_empty()


# ---------- PffLoader.build_ncaa_crosswalk ----------


class TestNcaaCrosswalk:
    def test_match_by_name_and_college(self, tmp_path):
        ncaa_data = pl.DataFrame({
            "player_id": [100, 200],
            "player": ["John Smith", "Jane Doe"],
            "team": ["Alabama", "Ohio State"],
        })
        nfl_roster = pl.DataFrame({
            "player_id": ["NFL001", "NFL002"],
            "player_name": ["John Smith", "Jane Doe"],
            "college_name": ["Alabama", "Ohio State"],
            "draft_number": [15, 45],
            "team": ["KC", "BUF"],
            "position": ["WR", "RB"],
            "rookie_year": [2025, 2025],
            "season": [2025, 2025],
        })
        loader = PffLoader(tmp_path / "pff" / "processed" / "nfl")
        crosswalk = loader.build_ncaa_crosswalk(ncaa_data, nfl_roster, 2025)
        assert crosswalk[100] == "NFL001"
        assert crosswalk[200] == "NFL002"

    def test_no_match_different_college(self, tmp_path):
        ncaa_data = pl.DataFrame({
            "player_id": [300],
            "player": ["Unknown Player"],
            "team": ["Small College"],
        })
        nfl_roster = pl.DataFrame({
            "player_id": ["NFL003"],
            "player_name": ["Unknown Player"],
            "college_name": ["Different College"],
            "team": ["NYG"],
            "position": ["WR"],
            "rookie_year": [2025],
            "season": [2025],
        })
        loader = PffLoader(tmp_path / "pff" / "processed" / "nfl")
        crosswalk = loader.build_ncaa_crosswalk(ncaa_data, nfl_roster, 2025)
        assert len(crosswalk) == 0

    def test_filters_by_rookie_year(self, tmp_path):
        ncaa_data = pl.DataFrame({
            "player_id": [100],
            "player": ["John Smith"],
            "team": ["Alabama"],
        })
        nfl_roster = pl.DataFrame({
            "player_id": ["NFL001"],
            "player_name": ["John Smith"],
            "college_name": ["Alabama"],
            "team": ["KC"],
            "position": ["WR"],
            "rookie_year": [2024],  # Different year
            "season": [2025],
        })
        loader = PffLoader(tmp_path / "pff" / "processed" / "nfl")
        # Target season is 2025, but player's rookie_year is 2024 -> no match
        crosswalk = loader.build_ncaa_crosswalk(ncaa_data, nfl_roster, 2025)
        assert len(crosswalk) == 0

    def test_filters_by_season_when_no_rookie_year(self, tmp_path):
        ncaa_data = pl.DataFrame({
            "player_id": [100],
            "player": ["John Smith"],
            "team": ["Alabama"],
        })
        nfl_roster = pl.DataFrame({
            "player_id": ["NFL001"],
            "player_name": ["John Smith"],
            "college_name": ["Alabama"],
            "team": ["KC"],
            "position": ["WR"],
            "season": [2025],
        })
        loader = PffLoader(tmp_path / "pff" / "processed" / "nfl")
        crosswalk = loader.build_ncaa_crosswalk(ncaa_data, nfl_roster, 2025)
        assert crosswalk[100] == "NFL001"

    def test_empty_ncaa_data_returns_empty(self, tmp_path):
        ncaa_data = pl.DataFrame({
            "player_id": pl.Series([], dtype=pl.Int64),
            "player": pl.Series([], dtype=pl.Utf8),
            "team": pl.Series([], dtype=pl.Utf8),
        })
        nfl_roster = pl.DataFrame({
            "player_id": ["NFL001"],
            "player_name": ["John Smith"],
            "college_name": ["Alabama"],
            "team": ["KC"],
            "position": ["WR"],
            "rookie_year": [2025],
            "season": [2025],
        })
        loader = PffLoader(tmp_path / "pff" / "processed" / "nfl")
        crosswalk = loader.build_ncaa_crosswalk(ncaa_data, nfl_roster, 2025)
        assert len(crosswalk) == 0

    def test_no_college_name_column_returns_empty(self, tmp_path):
        ncaa_data = pl.DataFrame({
            "player_id": [100],
            "player": ["John Smith"],
            "team": ["Alabama"],
        })
        nfl_roster = pl.DataFrame({
            "player_id": ["NFL001"],
            "player_name": ["John Smith"],
            "team": ["KC"],
            "position": ["WR"],
            "season": [2025],
        })
        loader = PffLoader(tmp_path / "pff" / "processed" / "nfl")
        crosswalk = loader.build_ncaa_crosswalk(ncaa_data, nfl_roster, 2025)
        assert len(crosswalk) == 0

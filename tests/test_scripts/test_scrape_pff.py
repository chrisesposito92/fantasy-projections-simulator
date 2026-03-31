"""Tests for PFF scraper utilities."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

import polars as pl
import pytest
from unittest.mock import patch, MagicMock
import httpx
from scrape_pff import parse_weeks, load_cookie, ProgressTracker, fetch_json, AuthError, process_season, build_team_lookup


class TestParseWeeks:
    def test_none_returns_none(self):
        assert parse_weeks(None) is None

    def test_single_week(self):
        assert parse_weeks("12") == [12]

    def test_week_range(self):
        assert parse_weeks("1-8") == [1, 2, 3, 4, 5, 6, 7, 8]

    def test_single_digit_range(self):
        assert parse_weeks("3-5") == [3, 4, 5]


class TestLoadCookie:
    def test_loads_cookie_from_env_file(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("PFF_COOKIE=abc123xyz\n")
        cookie = load_cookie(env_file)
        assert cookie == "abc123xyz"

    def test_strips_whitespace_and_quotes(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text('PFF_COOKIE="abc123xyz"\n')
        cookie = load_cookie(env_file)
        assert cookie == "abc123xyz"

    def test_returns_none_if_file_missing(self, tmp_path):
        env_file = tmp_path / ".env"
        cookie = load_cookie(env_file)
        assert cookie is None

    def test_returns_none_if_key_missing(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("OTHER_KEY=value\n")
        cookie = load_cookie(env_file)
        assert cookie is None


class TestProgressTracker:
    def test_new_tracker_is_empty(self, tmp_path):
        tracker = ProgressTracker(tmp_path / "progress.json")
        assert not tracker.is_done("2024", "week_01", "28418", "passing_summary")

    def test_mark_done_and_check(self, tmp_path):
        tracker = ProgressTracker(tmp_path / "progress.json")
        tracker.mark_done("2024", "week_01", "28418", "passing_summary")
        assert tracker.is_done("2024", "week_01", "28418", "passing_summary")
        assert not tracker.is_done("2024", "week_01", "28418", "rushing_summary")

    def test_persists_to_disk(self, tmp_path):
        path = tmp_path / "progress.json"
        tracker = ProgressTracker(path)
        tracker.mark_done("2024", "week_01", "28418", "passing_summary")
        tracker.save()

        tracker2 = ProgressTracker(path)
        assert tracker2.is_done("2024", "week_01", "28418", "passing_summary")

    def test_multiple_facets_per_game(self, tmp_path):
        tracker = ProgressTracker(tmp_path / "progress.json")
        tracker.mark_done("2024", "week_01", "28418", "passing_summary")
        tracker.mark_done("2024", "week_01", "28418", "rushing_summary")
        assert tracker.is_done("2024", "week_01", "28418", "passing_summary")
        assert tracker.is_done("2024", "week_01", "28418", "rushing_summary")
        assert not tracker.is_done("2024", "week_01", "28418", "defense_summary")


class TestFetchJson:
    def test_successful_fetch(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [1, 2, 3]}
        mock_client = MagicMock()
        mock_client.get.return_value = mock_response

        result = fetch_json(mock_client, "/api/v1/test", delay=0)
        assert result == {"data": [1, 2, 3]}

    def test_404_returns_none(self):
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_client = MagicMock()
        mock_client.get.return_value = mock_response

        result = fetch_json(mock_client, "/api/v1/test", delay=0)
        assert result is None

    def test_401_raises_auth_error(self):
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_client = MagicMock()
        mock_client.get.return_value = mock_response

        with pytest.raises(AuthError):
            fetch_json(mock_client, "/api/v1/test", delay=0)

    def test_403_raises_auth_error(self):
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_client = MagicMock()
        mock_client.get.return_value = mock_response

        with pytest.raises(AuthError):
            fetch_json(mock_client, "/api/v1/test", delay=0)

    def test_429_retries(self):
        resp_429 = MagicMock()
        resp_429.status_code = 429
        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.json.return_value = {"ok": True}
        mock_client = MagicMock()
        mock_client.get.side_effect = [resp_429, resp_200]

        result = fetch_json(mock_client, "/api/v1/test", delay=0)
        assert result == {"ok": True}
        assert mock_client.get.call_count == 2

    def test_network_error_retries(self):
        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.json.return_value = {"ok": True}
        mock_client = MagicMock()
        mock_client.get.side_effect = [httpx.ConnectError("fail"), resp_200]

        result = fetch_json(mock_client, "/api/v1/test", delay=0)
        assert result == {"ok": True}

    def test_exhausted_retries_returns_none(self):
        mock_client = MagicMock()
        mock_client.get.side_effect = httpx.ConnectError("fail")

        result = fetch_json(mock_client, "/api/v1/test", delay=0, max_retries=2)
        assert result is None
        assert mock_client.get.call_count == 2


class TestBuildTeamLookup:
    def test_builds_lookup_from_teams_json(self, tmp_path):
        teams_dir = tmp_path / "raw" / "teams"
        teams_dir.mkdir(parents=True)
        teams_data = {
            "teams": [
                {"franchise_id": 9, "abbreviation": "DAL"},
                {"franchise_id": 24, "abbreviation": "PHI"},
            ]
        }
        (teams_dir / "2024.json").write_text(json.dumps(teams_data))
        lookup = build_team_lookup(tmp_path, 2024)
        assert lookup == {9: "DAL", 24: "PHI"}


class TestProcessSeason:
    def _setup_raw_data(self, tmp_path):
        """Create minimal raw JSON fixture data."""
        # Teams
        teams_dir = tmp_path / "raw" / "teams"
        teams_dir.mkdir(parents=True)
        teams_data = {"teams": [{"franchise_id": 9, "abbreviation": "DAL"}]}
        (teams_dir / "2024.json").write_text(json.dumps(teams_data))

        # Facet data
        week_dir = tmp_path / "raw" / "facets" / "2024" / "week_01"
        week_dir.mkdir(parents=True)

        rushing_data = {
            "rushing_summary": [
                {
                    "player": "Saquon Barkley",
                    "player_id": 45791,
                    "franchise_id": 9,
                    "position": "HB",
                    "attempts": 18,
                    "yards": 60,
                    "grades_run": 58.4,
                },
            ]
        }
        (week_dir / "28418_rushing_summary.json").write_text(json.dumps(rushing_data))
        return tmp_path

    def test_produces_parquet_file(self, tmp_path):
        base = self._setup_raw_data(tmp_path)
        processed_dir = tmp_path / "processed"
        processed_dir.mkdir(parents=True)
        process_season(base, 2024)
        parquet_path = processed_dir / "rushing_summary_2024.parquet"
        assert parquet_path.exists()

    def test_parquet_has_metadata_columns(self, tmp_path):
        base = self._setup_raw_data(tmp_path)
        processed_dir = tmp_path / "processed"
        processed_dir.mkdir(parents=True)
        process_season(base, 2024)
        df = pl.read_parquet(processed_dir / "rushing_summary_2024.parquet")
        assert "season" in df.columns
        assert "week" in df.columns
        assert "game_id" in df.columns
        assert "team" in df.columns

    def test_parquet_has_correct_data(self, tmp_path):
        base = self._setup_raw_data(tmp_path)
        processed_dir = tmp_path / "processed"
        processed_dir.mkdir(parents=True)
        process_season(base, 2024)
        df = pl.read_parquet(processed_dir / "rushing_summary_2024.parquet")
        assert len(df) == 1
        row = df.row(0, named=True)
        assert row["player"] == "Saquon Barkley"
        assert row["season"] == 2024
        assert row["week"] == 1
        assert row["game_id"] == 28418
        assert row["team"] == "DAL"
        assert row["grades_run"] == 58.4

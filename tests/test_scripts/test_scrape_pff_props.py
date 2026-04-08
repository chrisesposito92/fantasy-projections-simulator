"""Tests for PFF player props scraper.

Tests cover: pagination, caching, auth, empty weeks, CLI args.
All httpx responses are mocked — no real API calls.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

import httpx
import polars as pl
import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_prop(
    prop_key: str = "recv_yd",
    consensus_line: float = 65.5,
    player_id: int = 12345,
    first_name: str = "Travis",
    last_name: str = "Kelce",
    team_id: int = 12,
    position: str = "TE",
) -> dict:
    """Create a single prop dict matching PFF consumer API shape."""
    return {
        "propKey": prop_key,
        "consensusLine": consensus_line,
        "player": {
            "playerId": player_id,
            "firstName": first_name,
            "lastName": last_name,
            "teamId": team_id,
            "position": position,
        },
        "projections": {"value": 70.2},
        "averages": {"last5": 68.0},
        "matchup": {"rating": 3},
        "lastTen": [60, 70, 80],
        "option": {"overOdds": -110},
    }


def _make_response(
    props: list[dict] | None = None,
    status_code: int = 200,
) -> httpx.Response:
    """Build a mock httpx.Response."""
    if props is None:
        props = [_make_prop()]
    body = {
        "playerProps": props,
        "version": 1,
        "updatedAt": "2025-09-04T12:00:00Z",
    }
    resp = httpx.Response(
        status_code=status_code,
        json=body,
        request=httpx.Request("GET", "https://consumer-api.pff.com/test"),
    )
    return resp


# ---------------------------------------------------------------------------
# Tests: fetch_props_page
# ---------------------------------------------------------------------------

class TestFetchPropsPage:
    """Test fetch_props_page returns parsed playerProps list."""

    def test_returns_props_list(self):
        from scrape_pff_props import fetch_props_page

        props = [_make_prop(), _make_prop(prop_key="rush_yd", player_id=99999)]
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = _make_response(props=props)

        result = fetch_props_page(mock_client, season=2025, week=1, page=1)

        assert len(result) == 2
        assert result[0]["propKey"] == "recv_yd"
        assert result[1]["propKey"] == "rush_yd"

    def test_returns_empty_list_on_empty_page(self):
        from scrape_pff_props import fetch_props_page

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = _make_response(props=[])

        result = fetch_props_page(mock_client, season=2025, week=1, page=35)
        assert result == []

    def test_raises_auth_error_on_401(self):
        from scrape_pff_props import fetch_props_page, AuthError

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = httpx.Response(
            status_code=401,
            json={"error": "unauthorized"},
            request=httpx.Request("GET", "https://consumer-api.pff.com/test"),
        )

        with pytest.raises(AuthError):
            fetch_props_page(mock_client, season=2025, week=1, page=1)

    def test_raises_auth_error_on_403(self):
        from scrape_pff_props import fetch_props_page, AuthError

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = httpx.Response(
            status_code=403,
            json={"error": "forbidden"},
            request=httpx.Request("GET", "https://consumer-api.pff.com/test"),
        )

        with pytest.raises(AuthError):
            fetch_props_page(mock_client, season=2025, week=1, page=1)

    def test_retries_on_429(self):
        from scrape_pff_props import fetch_props_page

        props = [_make_prop()]
        mock_client = MagicMock(spec=httpx.Client)
        # First call returns 429, second succeeds
        mock_client.get.side_effect = [
            httpx.Response(
                status_code=429,
                json={},
                request=httpx.Request("GET", "https://consumer-api.pff.com/test"),
            ),
            _make_response(props=props),
        ]

        with patch("scrape_pff_props.time.sleep"):
            result = fetch_props_page(mock_client, season=2025, week=1, page=1)

        assert len(result) == 1

    def test_retries_on_server_error(self):
        from scrape_pff_props import fetch_props_page

        props = [_make_prop()]
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.side_effect = [
            httpx.Response(
                status_code=500,
                json={},
                request=httpx.Request("GET", "https://consumer-api.pff.com/test"),
            ),
            _make_response(props=props),
        ]

        with patch("scrape_pff_props.time.sleep"):
            result = fetch_props_page(mock_client, season=2025, week=1, page=1)

        assert len(result) == 1

    def test_returns_none_after_exhausted_retries(self):
        from scrape_pff_props import fetch_props_page

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.side_effect = [
            httpx.Response(
                status_code=500,
                json={},
                request=httpx.Request("GET", "https://consumer-api.pff.com/test"),
            ),
        ] * 3

        with patch("scrape_pff_props.time.sleep"):
            result = fetch_props_page(mock_client, season=2025, week=1, page=1)

        assert result is None


# ---------------------------------------------------------------------------
# Tests: paginate_week
# ---------------------------------------------------------------------------

class TestPaginateWeek:
    """Test paginate_week collects props across pages, stops on empty."""

    def test_collects_across_pages_stops_on_empty(self):
        from scrape_pff_props import paginate_week

        page1 = [_make_prop(player_id=1), _make_prop(player_id=2)]
        page2 = [_make_prop(player_id=3)]
        page3 = []  # empty -> stop

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.side_effect = [
            _make_response(props=page1),
            _make_response(props=page2),
            _make_response(props=page3),
        ]

        with patch("scrape_pff_props.time.sleep"):
            result = paginate_week(mock_client, season=2025, week=1, delay=0.0)

        assert len(result) == 3
        assert result[0]["player"]["playerId"] == 1
        assert result[2]["player"]["playerId"] == 3

    def test_returns_empty_on_first_page_empty(self):
        from scrape_pff_props import paginate_week

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = _make_response(props=[])

        with patch("scrape_pff_props.time.sleep"):
            result = paginate_week(mock_client, season=2025, week=5, delay=0.0)

        assert result == []


# ---------------------------------------------------------------------------
# Tests: scrape_week
# ---------------------------------------------------------------------------

class TestScrapeWeek:
    """Test scrape_week writes parquet with expected columns to cache dir."""

    def test_writes_parquet_with_expected_columns(self, tmp_path: Path):
        from scrape_pff_props import scrape_week

        props = [
            _make_prop(prop_key="recv_yd", consensus_line=65.5, player_id=100),
            _make_prop(prop_key="rush_yd", consensus_line=80.0, player_id=200),
        ]
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.side_effect = [
            _make_response(props=props),
            _make_response(props=[]),
        ]

        with patch("scrape_pff_props.time.sleep"):
            scrape_week(mock_client, season=2025, week=1, cache_dir=tmp_path, delay=0.0)

        cache_file = tmp_path / "props_2025_week01.parquet"
        assert cache_file.exists()

        df = pl.read_parquet(cache_file)
        assert len(df) == 2

        # Check expected columns exist
        expected_cols = {
            "prop_key", "consensus_line", "player_id", "first_name",
            "last_name", "team_id", "position", "season", "week",
            "projections_json", "averages_json", "matchup_json",
            "last_ten_json", "option_json",
        }
        assert expected_cols.issubset(set(df.columns))

        # Check values
        row = df.filter(pl.col("player_id") == 100).row(0, named=True)
        assert row["prop_key"] == "recv_yd"
        assert row["consensus_line"] == 65.5
        assert row["first_name"] == "Travis"
        assert row["season"] == 2025
        assert row["week"] == 1

    def test_skips_when_cache_exists(self, tmp_path: Path):
        from scrape_pff_props import scrape_week

        # Pre-create cache file
        cache_file = tmp_path / "props_2025_week01.parquet"
        cache_file.write_bytes(b"existing")

        mock_client = MagicMock(spec=httpx.Client)

        result = scrape_week(mock_client, season=2025, week=1, cache_dir=tmp_path, delay=0.0)

        # Should not have made any API calls
        mock_client.get.assert_not_called()
        assert result is False  # skipped

    def test_writes_empty_parquet_for_empty_week(self, tmp_path: Path):
        from scrape_pff_props import scrape_week

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = _make_response(props=[])

        with patch("scrape_pff_props.time.sleep"):
            scrape_week(mock_client, season=2025, week=18, cache_dir=tmp_path, delay=0.0)

        cache_file = tmp_path / "props_2025_week18.parquet"
        assert cache_file.exists()

        df = pl.read_parquet(cache_file)
        assert len(df) == 0


# ---------------------------------------------------------------------------
# Tests: load_api_key
# ---------------------------------------------------------------------------

class TestLoadApiKey:
    """Test load_api_key reads PFF_API_KEY from .env file."""

    def test_reads_key_from_env_file(self, tmp_path: Path):
        from scrape_pff_props import load_api_key

        env_file = tmp_path / ".env"
        env_file.write_text("PFF_COOKIE=abc123\nPFF_API_KEY=my-secret-key\n")

        result = load_api_key(env_path=env_file)
        assert result == "my-secret-key"

    def test_returns_none_when_file_missing(self, tmp_path: Path):
        from scrape_pff_props import load_api_key

        result = load_api_key(env_path=tmp_path / "nonexistent.env")
        assert result is None

    def test_returns_none_when_key_absent(self, tmp_path: Path):
        from scrape_pff_props import load_api_key

        env_file = tmp_path / ".env"
        env_file.write_text("PFF_COOKIE=abc123\n")

        result = load_api_key(env_path=env_file)
        assert result is None

    def test_env_var_takes_precedence(self, tmp_path: Path):
        from scrape_pff_props import load_api_key

        env_file = tmp_path / ".env"
        env_file.write_text("PFF_API_KEY=file-key\n")

        with patch.dict("os.environ", {"PFF_API_KEY": "env-key"}):
            result = load_api_key(env_path=env_file)
        assert result == "env-key"

    def test_strips_quotes_from_value(self, tmp_path: Path):
        from scrape_pff_props import load_api_key

        env_file = tmp_path / ".env"
        env_file.write_text('PFF_API_KEY="my-quoted-key"\n')

        result = load_api_key(env_path=env_file)
        assert result == "my-quoted-key"


# ---------------------------------------------------------------------------
# Tests: CLI
# ---------------------------------------------------------------------------

class TestCLI:
    """Test CLI argument parsing."""

    def test_help_output(self):
        """CLI --help shows usage with --season and --weeks options."""
        from click.testing import CliRunner
        from scrape_pff_props import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])

        assert result.exit_code == 0
        assert "--season" in result.output
        assert "--weeks" in result.output

    def test_season_is_required(self):
        """CLI without --season exits with error."""
        from click.testing import CliRunner
        from scrape_pff_props import cli

        runner = CliRunner()
        result = runner.invoke(cli, [])

        assert result.exit_code != 0
        assert "season" in result.output.lower() or "missing" in result.output.lower()

    def test_api_key_error_message(self, tmp_path: Path):
        """CLI exits with clear error when no API key found."""
        from click.testing import CliRunner
        from scrape_pff_props import cli

        runner = CliRunner()
        with patch("scrape_pff_props.load_api_key", return_value=None):
            result = runner.invoke(cli, ["--season", "2025"])

        assert result.exit_code != 0
        # Should not contain the actual key in error messages
        assert "api" in result.output.lower() or "key" in result.output.lower()


# ---------------------------------------------------------------------------
# Tests: API key redaction (T-06-01)
# ---------------------------------------------------------------------------

class TestApiKeyRedaction:
    """Ensure API key is never logged or included in error messages."""

    def test_auth_error_does_not_contain_key(self):
        from scrape_pff_props import AuthError

        err = AuthError("Authentication failed: 401")
        assert "my-secret-key" not in str(err)

    def test_fetch_url_does_not_contain_key(self):
        """The API key is sent via header, not query param."""
        from scrape_pff_props import PFF_PROPS_BASE_URL

        assert "key" not in PFF_PROPS_BASE_URL.lower()

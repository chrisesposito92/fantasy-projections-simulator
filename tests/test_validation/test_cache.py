"""Tests for bare baseline cache."""
from pathlib import Path
from fantasy_sim.validation.cache import cache_path, load_cache, save_cache


def test_cache_path_format():
    p = cache_path(2024, 50, "ppr", 4, cache_dir=Path("/tmp/test"))
    assert p == Path("/tmp/test/bare_2024_50_ppr_4.json")


def test_cache_path_different_params():
    p1 = cache_path(2023, 50, "ppr", 4, cache_dir=Path("/tmp/test"))
    p2 = cache_path(2024, 50, "ppr", 4, cache_dir=Path("/tmp/test"))
    assert p1 != p2


def test_load_cache_missing_file():
    result = load_cache(Path("/tmp/nonexistent_cache_xyz.json"))
    assert result is None


def test_cache_roundtrip(tmp_path):
    projections = {
        "player1": {1: 15.2, 2: 8.4, 3: 22.1},
        "player2": {1: 6.0, 2: 12.3},
    }
    meta = {
        "player1": {"position": "WR", "team": "KC", "name": "Test Player"},
        "player2": {"position": "RB", "team": "BUF", "name": "Other Player"},
    }
    p = tmp_path / "test_cache.json"
    save_cache(p, projections, meta)
    loaded = load_cache(p)
    assert loaded is not None
    assert loaded["projections"]["player1"][1] == 15.2
    assert loaded["projections"]["player2"][2] == 12.3
    assert loaded["player_meta"]["player1"]["position"] == "WR"


def test_cache_roundtrip_preserves_week_int_keys(tmp_path):
    """JSON serializes int keys as strings — verify they're restored."""
    projections = {"p1": {10: 5.0, 18: 12.0}}
    meta = {"p1": {"position": "QB", "team": "KC", "name": "QB1"}}
    p = tmp_path / "test_cache.json"
    save_cache(p, projections, meta)
    loaded = load_cache(p)
    assert 10 in loaded["projections"]["p1"]
    assert 18 in loaded["projections"]["p1"]
    assert isinstance(list(loaded["projections"]["p1"].keys())[0], int)

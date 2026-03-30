import pytest
from fantasy_sim.output.tables import (
    format_qb_table, format_rb_table, format_wr_table,
    format_te_table, format_dst_table, format_kicker_table,
)


@pytest.fixture
def qb_projections():
    return [
        {"rank": 1, "name": "P.Mahomes", "team": "KC", "fpts": 22.4,
         "pass_yards": 274, "pass_tds": 2.1, "interceptions": 0.7,
         "rush_yards": 18.3, "rush_tds": 0.2, "sacks": 2.1, "fumbles_lost": 0.3},
    ]


@pytest.fixture
def rb_projections():
    return [
        {"rank": 1, "name": "B.Robinson", "team": "ATL", "fpts": 18.7,
         "rush_yards": 82.3, "rush_tds": 0.7, "targets": 4.2,
         "receptions": 3.1, "receiving_yards": 24.8, "receiving_tds": 0.2,
         "fumbles_lost": 0.2},
    ]


class TestFormatQBTable:
    def test_returns_string(self, qb_projections):
        result = format_qb_table(qb_projections)
        assert isinstance(result, str)
        assert "Mahomes" in result
        assert "274" in result

    def test_empty_list(self):
        result = format_qb_table([])
        assert isinstance(result, str)


class TestFormatRBTable:
    def test_returns_string(self, rb_projections):
        result = format_rb_table(rb_projections)
        assert isinstance(result, str)
        assert "Robinson" in result

    def test_includes_receiving_stats(self, rb_projections):
        result = format_rb_table(rb_projections)
        assert "24.8" in result  # receiving yards


class TestFormatWRTable:
    def test_returns_string(self):
        projections = [
            {"rank": 1, "name": "N.Collins", "team": "HOU", "fpts": 17.2,
             "targets": 8.4, "receptions": 5.8, "receiving_yards": 78.2,
             "receiving_tds": 0.6, "rush_yards": 2.1, "rush_tds": 0.0,
             "fumbles_lost": 0.1},
        ]
        result = format_wr_table(projections)
        assert "Collins" in result


class TestFormatDSTTable:
    def test_returns_string(self):
        projections = [
            {"rank": 1, "team": "BAL", "fpts": 8.2,
             "sacks": 2.8, "interceptions": 0.9, "fumble_recoveries": 0.7,
             "dst_tds": 0.2, "safeties": 0.1, "points_allowed": 18.4},
        ]
        result = format_dst_table(projections)
        assert "BAL" in result

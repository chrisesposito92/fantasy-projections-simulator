import polars as pl
import pytest
from fantasy_sim.data.actuals import load_actual_scores, ActualPlayerWeek


@pytest.fixture
def sample_player_stats():
    """Mimics nflreadpy.load_player_stats output."""
    return pl.DataFrame([
        {"player_id": "PM15", "player_name": "P.Mahomes", "position": "QB",
         "recent_team": "KC", "season": 2024, "week": 1,
         "completions": 22, "attempts": 35, "passing_yards": 280,
         "passing_tds": 2, "interceptions": 1, "sacks": 2,
         "carries": 3, "rushing_yards": 18, "rushing_tds": 0,
         "receptions": 0, "targets": 0, "receiving_yards": 0,
         "receiving_tds": 0, "receiving_fumbles_lost": 0,
         "rushing_fumbles_lost": 0, "sack_fumbles_lost": 0},
        {"player_id": "TK87", "player_name": "T.Kelce", "position": "TE",
         "recent_team": "KC", "season": 2024, "week": 1,
         "completions": 0, "attempts": 0, "passing_yards": 0,
         "passing_tds": 0, "interceptions": 0, "sacks": 0,
         "carries": 0, "rushing_yards": 0, "rushing_tds": 0,
         "receptions": 7, "targets": 9, "receiving_yards": 85,
         "receiving_tds": 1, "receiving_fumbles_lost": 0,
         "rushing_fumbles_lost": 0, "sack_fumbles_lost": 0},
    ])


@pytest.fixture
def ppr_config():
    return {
        "passing_yard": 0.04, "passing_td": 4, "interception": -2,
        "rushing_yard": 0.1, "rushing_td": 6,
        "reception": 1, "receiving_yard": 0.1, "receiving_td": 6,
        "fumble_lost": -2,
    }


class TestLoadActualScores:
    def test_returns_list_of_actuals(self, sample_player_stats, ppr_config):
        actuals = load_actual_scores(sample_player_stats, ppr_config, season=2024)
        assert isinstance(actuals, list)
        assert len(actuals) > 0
        assert isinstance(actuals[0], ActualPlayerWeek)

    def test_mahomes_ppr_score(self, sample_player_stats, ppr_config):
        actuals = load_actual_scores(sample_player_stats, ppr_config, season=2024)
        mahomes = [a for a in actuals if a.player_id == "PM15"][0]
        # 280*0.04 + 2*4 + 1*(-2) + 18*0.1 = 11.2 + 8 - 2 + 1.8 = 19.0
        assert mahomes.fpts == pytest.approx(19.0)
        assert mahomes.week == 1

    def test_kelce_ppr_score(self, sample_player_stats, ppr_config):
        actuals = load_actual_scores(sample_player_stats, ppr_config, season=2024)
        kelce = [a for a in actuals if a.player_id == "TK87"][0]
        # 7*1 + 85*0.1 + 1*6 = 7 + 8.5 + 6 = 21.5
        assert kelce.fpts == pytest.approx(21.5)

    def test_filters_to_season(self, sample_player_stats, ppr_config):
        actuals = load_actual_scores(sample_player_stats, ppr_config, season=2023)
        assert len(actuals) == 0  # No 2023 data in fixture

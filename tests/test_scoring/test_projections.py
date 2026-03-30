import pytest
from fantasy_sim.scoring.projections import build_player_projections, build_dst_projections, build_detailed_projections
from fantasy_sim.engine.types import GameResult, TeamBoxScore, PlayerBoxScore


def make_game_result(player_stats=None, home_score=24, away_score=17):
    return GameResult(
        home_score=home_score, away_score=away_score,
        home_box=TeamBoxScore(
            points=home_score, sacks_made=3, interceptions_caught=1,
            fumbles_recovered=1, safeties=0,
            fg_made=1, fg_made_0_39=1, fg_made_40_49=0, fg_made_50_plus=0,
            fg_missed=0, xp_made=3, xp_attempts=3,
        ),
        away_box=TeamBoxScore(
            points=away_score, sacks_made=2, interceptions_caught=0,
            fumbles_recovered=0, safeties=0,
            fg_made=1, fg_made_0_39=0, fg_made_40_49=1, fg_made_50_plus=0,
            fg_missed=1, xp_made=2, xp_attempts=2,
        ),
        total_plays=130, overtime=False,
        player_stats=player_stats or {
            "QB1": PlayerBoxScore("QB1", "QB Name", "QB", "HOME",
                                  pass_yards=280, pass_tds=2, completions=22,
                                  pass_attempts=35, interceptions=1),
            "WR1": PlayerBoxScore("WR1", "WR Name", "WR", "HOME",
                                  targets=8, receptions=5, receiving_yards=85,
                                  receiving_tds=1),
            "RB1": PlayerBoxScore("RB1", "RB Name", "RB", "HOME",
                                  rush_attempts=15, rush_yards=65, rush_tds=1,
                                  targets=3, receptions=2, receiving_yards=18),
        },
    )


@pytest.fixture
def ppr_config():
    return {
        "passing_yard": 0.04, "passing_td": 4, "interception": -2,
        "rushing_yard": 0.1, "rushing_td": 6,
        "reception": 1, "receiving_yard": 0.1, "receiving_td": 6,
        "fumble_lost": -2,
    }


@pytest.fixture
def dst_config():
    return {
        "dst_sack": 1, "dst_interception": 2, "dst_fumble_recovery": 2,
        "dst_td": 6, "dst_safety": 2,
        "dst_points_allowed_0": 10, "dst_points_allowed_1_6": 7,
        "dst_points_allowed_7_13": 4, "dst_points_allowed_14_20": 1,
        "dst_points_allowed_21_27": 0, "dst_points_allowed_28_34": -1,
        "dst_points_allowed_35_plus": -4,
    }


class TestBuildPlayerProjections:
    def test_returns_list_of_dicts(self, ppr_config):
        games = [make_game_result() for _ in range(5)]
        projections = build_player_projections(games, ppr_config)
        assert isinstance(projections, list)
        assert len(projections) > 0
        assert "name" in projections[0]
        assert "fpts" in projections[0]

    def test_projections_sorted_by_fpts(self, ppr_config):
        games = [make_game_result() for _ in range(10)]
        projections = build_player_projections(games, ppr_config)
        fpts = [p["fpts"] for p in projections]
        assert fpts == sorted(fpts, reverse=True)

    def test_projections_have_position(self, ppr_config):
        games = [make_game_result() for _ in range(5)]
        projections = build_player_projections(games, ppr_config)
        for p in projections:
            assert p["position"] in ("QB", "RB", "WR", "TE", "K")

    def test_projections_have_mean_stats(self, ppr_config):
        games = [make_game_result() for _ in range(5)]
        projections = build_player_projections(games, ppr_config)
        qb = next(p for p in projections if p["position"] == "QB")
        assert "pass_yards" in qb
        assert "pass_tds" in qb
        assert qb["pass_yards"] > 0


class TestBuildDSTProjections:
    def test_returns_list(self, dst_config):
        games = [make_game_result()]
        projections = build_dst_projections(games, dst_config, team_map={"HOME": "KC", "AWAY": "BUF"})
        assert isinstance(projections, list)

    def test_dst_has_fpts(self, dst_config):
        games = [make_game_result() for _ in range(5)]
        projections = build_dst_projections(games, dst_config, team_map={"HOME": "KC", "AWAY": "BUF"})
        for p in projections:
            assert "fpts" in p
            assert "sacks" in p


class TestBuildDetailedProjections:
    def test_returns_list_of_dicts(self, ppr_config):
        games = [make_game_result() for _ in range(20)]
        projections = build_detailed_projections(games, ppr_config)
        assert isinstance(projections, list)
        assert len(projections) > 0

    def test_has_distribution_fields(self, ppr_config):
        games = [make_game_result() for _ in range(20)]
        projections = build_detailed_projections(games, ppr_config)
        qb = next(p for p in projections if p["position"] == "QB")
        assert "fpts_floor" in qb
        assert "fpts_ceiling" in qb
        assert "fpts_stddev" in qb
        assert "pass_yards_floor" in qb
        assert "pass_yards_ceiling" in qb
        assert "pass_yards_stddev" in qb

    def test_floor_less_than_mean_less_than_ceiling(self, ppr_config):
        games = [make_game_result() for _ in range(50)]
        projections = build_detailed_projections(games, ppr_config)
        for p in projections:
            assert p["fpts_floor"] <= p["fpts"], f"{p['name']}: floor > mean"
            assert p["fpts"] <= p["fpts_ceiling"], f"{p['name']}: mean > ceiling"

    def test_stddev_non_negative(self, ppr_config):
        games = [make_game_result() for _ in range(20)]
        projections = build_detailed_projections(games, ppr_config)
        for p in projections:
            assert p["fpts_stddev"] >= 0

    def test_sorted_by_fpts(self, ppr_config):
        games = [make_game_result() for _ in range(20)]
        projections = build_detailed_projections(games, ppr_config)
        fpts = [p["fpts"] for p in projections]
        assert fpts == sorted(fpts, reverse=True)

    def test_has_all_base_fields(self, ppr_config):
        games = [make_game_result() for _ in range(20)]
        projections = build_detailed_projections(games, ppr_config)
        qb = next(p for p in projections if p["position"] == "QB")
        assert "player_id" in qb
        assert "name" in qb
        assert "team" in qb
        assert "position" in qb
        assert "fpts" in qb
        assert "pass_yards" in qb
        assert "rank" in qb

    def test_stat_distributions_present(self, ppr_config):
        games = [make_game_result() for _ in range(20)]
        projections = build_detailed_projections(games, ppr_config)
        rb = next(p for p in projections if p["position"] == "RB")
        assert "rush_yards_floor" in rb
        assert "rush_yards_ceiling" in rb
        assert "rush_yards_stddev" in rb
        assert "receiving_yards_floor" in rb
        assert "receiving_yards_ceiling" in rb

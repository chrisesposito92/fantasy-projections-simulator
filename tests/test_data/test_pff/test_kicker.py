"""Tests for PFF kicker engine — per-kicker accuracy with Bayesian shrinkage."""

import polars as pl
import pytest

from fantasy_sim.data.pff.loader import PffLoader
from fantasy_sim.data.pff.models import KickerConfig, PffConfig
from fantasy_sim.data.pff.kicker import KickerEngine
from fantasy_sim.models.distributions import KickingModel


class TestKickerConfig:
    def test_default_values(self):
        cfg = KickerConfig()
        assert cfg.enabled is True
        assert cfg.prior_strength == 20
        assert cfg.min_attempts == 5

    def test_pff_config_has_kicker(self):
        pff = PffConfig()
        assert hasattr(pff, "kicker")
        assert isinstance(pff.kicker, KickerConfig)


# ---------- Fixtures ----------


@pytest.fixture
def pff_dir(tmp_path):
    d = tmp_path / "pff" / "processed" / "nfl"
    d.mkdir(parents=True)
    return d


@pytest.fixture
def loader(pff_dir):
    return PffLoader(pff_dir)


# ---------- Parquet helpers ----------


def _write_field_goal_summary(pff_dir, season, kickers):
    """Write field_goal_summary_{season}.parquet to pff_dir.

    Each kicker dict has:
        player_id (int), player (str), team (str), n_games (int),
        and per-game attempt/made counts:
            twenty_attempts, twenty_made, thirty_attempts, thirty_made,
            forty_attempts, forty_made, fifty_attempts, fifty_made,
            pat_attempts, pat_made  (all per-game, replicated across n_games)
    """
    rows = {
        "player_id": [],
        "player": [],
        "team": [],
        "position": [],
        "season": [],
        "week": [],
        "game_id": [],
        "grades_fgep_kicker": [],
        "one_attempts": [],
        "one_made": [],
        "one_percent": [],
        "twenty_attempts": [],
        "twenty_made": [],
        "twenty_percent": [],
        "thirty_attempts": [],
        "thirty_made": [],
        "thirty_percent": [],
        "forty_attempts": [],
        "forty_made": [],
        "forty_percent": [],
        "fifty_attempts": [],
        "fifty_made": [],
        "fifty_percent": [],
        "pat_attempts": [],
        "pat_made": [],
        "pat_percent": [],
        "total_attempts": [],
        "total_made": [],
        "total_percent": [],
        "penalties": [],
        "declined_penalties": [],
        "jersey_number": [],
        "franchise_id": [],
        "status": [],
    }
    game_id_counter = 8000
    for k in kickers:
        for week in range(1, k["n_games"] + 1):
            game_id_counter += 1
            rows["player_id"].append(k["player_id"])
            rows["player"].append(k["player"])
            rows["team"].append(k["team"])
            rows["position"].append("K")
            rows["season"].append(season)
            rows["week"].append(week)
            rows["game_id"].append(game_id_counter)
            rows["grades_fgep_kicker"].append(75.0)
            rows["one_attempts"].append(0)
            rows["one_made"].append(0)
            rows["one_percent"].append(0.0)
            for bucket in ("twenty", "thirty", "forty", "fifty", "pat"):
                att = k.get(f"{bucket}_attempts", 0)
                made = k.get(f"{bucket}_made", 0)
                pct = (made / att * 100) if att > 0 else 0.0
                rows[f"{bucket}_attempts"].append(att)
                rows[f"{bucket}_made"].append(made)
                rows[f"{bucket}_percent"].append(pct)
            tot_att = sum(k.get(f"{b}_attempts", 0) for b in ("twenty", "thirty", "forty", "fifty"))
            tot_made = sum(k.get(f"{b}_made", 0) for b in ("twenty", "thirty", "forty", "fifty"))
            rows["total_attempts"].append(tot_att)
            rows["total_made"].append(tot_made)
            rows["total_percent"].append((tot_made / tot_att * 100) if tot_att > 0 else 0.0)
            rows["penalties"].append(0)
            rows["declined_penalties"].append(0)
            rows["jersey_number"].append("1")
            rows["franchise_id"].append(k["player_id"] * 10)
            rows["status"].append("Active")

    schema = {
        "player_id": pl.Int64,
        "player": pl.Utf8,
        "team": pl.Utf8,
        "position": pl.Utf8,
        "season": pl.Int64,
        "week": pl.Int64,
        "game_id": pl.Int64,
        "grades_fgep_kicker": pl.Float64,
        "one_attempts": pl.Int64,
        "one_made": pl.Int64,
        "one_percent": pl.Float64,
        "twenty_attempts": pl.Int64,
        "twenty_made": pl.Int64,
        "twenty_percent": pl.Float64,
        "thirty_attempts": pl.Int64,
        "thirty_made": pl.Int64,
        "thirty_percent": pl.Float64,
        "forty_attempts": pl.Int64,
        "forty_made": pl.Int64,
        "forty_percent": pl.Float64,
        "fifty_attempts": pl.Int64,
        "fifty_made": pl.Int64,
        "fifty_percent": pl.Float64,
        "pat_attempts": pl.Int64,
        "pat_made": pl.Int64,
        "pat_percent": pl.Float64,
        "total_attempts": pl.Int64,
        "total_made": pl.Int64,
        "total_percent": pl.Float64,
        "penalties": pl.Int64,
        "declined_penalties": pl.Int64,
        "jersey_number": pl.Utf8,
        "franchise_id": pl.Int64,
        "status": pl.Utf8,
    }
    df = pl.DataFrame(rows, schema=schema)
    path = pff_dir / f"field_goal_summary_{season}.parquet"
    df.write_parquet(path)
    return df


def _make_kicker_roster(kickers):
    """Build a polars DataFrame representing an nflverse kicker roster.

    Each kicker dict needs: player_id (str), player_name (str), team (str),
    and optionally pff_id (str of int).
    """
    rows = {
        "player_id": [],
        "player_name": [],
        "team": [],
        "position": [],
        "pff_id": [],
    }
    for k in kickers:
        rows["player_id"].append(k["player_id"])
        rows["player_name"].append(k["player_name"])
        rows["team"].append(k["team"])
        rows["position"].append("K")
        rows["pff_id"].append(k.get("pff_id"))
    return pl.DataFrame(rows, schema={
        "player_id": pl.Utf8,
        "player_name": pl.Utf8,
        "team": pl.Utf8,
        "position": pl.Utf8,
        "pff_id": pl.Utf8,
    })


# ---------- Engine tests ----------


class TestKickerEngineShrinkage:
    """Tests for KickerEngine Bayesian shrinkage and bucket mapping."""

    def test_high_volume_kicker_near_personal_rate(self, pff_dir, loader):
        """Kicker with 17 games, 2 forty_att/game all made → 40-49 rate > 0.90."""
        _write_field_goal_summary(pff_dir, 2024, [
            {
                "player_id": 100, "player": "Justin Tucker", "team": "BAL",
                "n_games": 17,
                "forty_attempts": 2, "forty_made": 2,
                "pat_attempts": 3, "pat_made": 3,
            }
        ])
        roster = _make_kicker_roster([
            {"player_id": "00-0000100", "player_name": "Justin Tucker",
             "team": "BAL", "pff_id": "100"}
        ])
        engine = KickerEngine(KickerConfig(prior_strength=20), loader, [2024])
        engine.build_crosswalk(roster, 2024)
        model = engine.compute("00-0000100")
        assert model is not None
        # 34 made / 34 att personal, prior_strength=20 → blended close to 1.0
        assert model.fg_make_rate["40_49"] > 0.90

    def test_low_volume_kicker_near_league_rate(self, pff_dir, loader):
        """Kicker with zero fifty_attempts → 50+ rate equals league avg exactly."""
        _write_field_goal_summary(pff_dir, 2024, [
            {
                "player_id": 101, "player": "Evan McPherson", "team": "CIN",
                "n_games": 10,
                # Only forty kicks — no fifty attempts at all
                "forty_attempts": 1, "forty_made": 1,
                "pat_attempts": 3, "pat_made": 3,
            }
        ])
        roster = _make_kicker_roster([
            {"player_id": "00-0000101", "player_name": "Evan McPherson",
             "team": "CIN", "pff_id": "101"}
        ])
        engine = KickerEngine(KickerConfig(prior_strength=20), loader, [2024])
        engine.build_crosswalk(roster, 2024)
        model = engine.compute("00-0000101")
        assert model is not None
        # No fifty attempts at all → blended_rate = (0 + prior * league) / (0 + prior) = league
        league_50 = engine._league_rates["50_plus"]
        assert abs(model.fg_make_rate["50_plus"] - league_50) < 1e-9

    def test_min_attempts_returns_none(self, pff_dir, loader):
        """Kicker with only 1 FG attempt and min_attempts=10 → returns None."""
        _write_field_goal_summary(pff_dir, 2024, [
            {
                "player_id": 102, "player": "Sparse Kicker", "team": "NYG",
                "n_games": 1,
                "forty_attempts": 1, "forty_made": 1,
                "pat_attempts": 1, "pat_made": 1,
            }
        ])
        roster = _make_kicker_roster([
            {"player_id": "00-0000102", "player_name": "Sparse Kicker",
             "team": "NYG", "pff_id": "102"}
        ])
        engine = KickerEngine(KickerConfig(min_attempts=10), loader, [2024])
        engine.build_crosswalk(roster, 2024)
        assert engine.compute("00-0000102") is None

    def test_missing_kicker_returns_none(self, pff_dir, loader):
        """Kicker not in crosswalk → returns None."""
        _write_field_goal_summary(pff_dir, 2024, [
            {
                "player_id": 103, "player": "Known Kicker", "team": "KC",
                "n_games": 5,
                "forty_attempts": 2, "forty_made": 2,
                "pat_attempts": 3, "pat_made": 3,
            }
        ])
        # No roster → crosswalk stays empty
        engine = KickerEngine(KickerConfig(), loader, [2024])
        engine.build_crosswalk(pl.DataFrame(), 2024)
        assert engine.compute("00-9999999") is None

    def test_distance_bucket_mapping(self, pff_dir, loader):
        """With prior_strength=0, verify exact bucket mapping ratios."""
        _write_field_goal_summary(pff_dir, 2024, [
            {
                "player_id": 104, "player": "Test Kicker", "team": "SF",
                "n_games": 1,
                # short: twenty=3/4, thirty=2/2 → combined 5/6
                "twenty_attempts": 4, "twenty_made": 3,
                "thirty_attempts": 2, "thirty_made": 2,
                "forty_attempts": 3, "forty_made": 2,
                "fifty_attempts": 2, "fifty_made": 1,
                "pat_attempts": 5, "pat_made": 4,
            }
        ])
        roster = _make_kicker_roster([
            {"player_id": "00-0000104", "player_name": "Test Kicker",
             "team": "SF", "pff_id": "104"}
        ])
        engine = KickerEngine(KickerConfig(prior_strength=0, min_attempts=1), loader, [2024])
        engine.build_crosswalk(roster, 2024)
        model = engine.compute("00-0000104")
        assert model is not None
        assert abs(model.fg_make_rate["0_39"] - 5 / 6) < 1e-9
        assert abs(model.fg_make_rate["40_49"] - 2 / 3) < 1e-9
        assert abs(model.fg_make_rate["50_plus"] - 1 / 2) < 1e-9
        assert abs(model.xp_rate - 4 / 5) < 1e-9

    def test_returns_kicking_model(self, pff_dir, loader):
        """compute() returns a KickingModel with all required keys and valid ranges."""
        _write_field_goal_summary(pff_dir, 2024, [
            {
                "player_id": 105, "player": "Good Kicker", "team": "DAL",
                "n_games": 10,
                "twenty_attempts": 2, "twenty_made": 2,
                "forty_attempts": 2, "forty_made": 2,
                "fifty_attempts": 1, "fifty_made": 1,
                "pat_attempts": 3, "pat_made": 3,
            }
        ])
        roster = _make_kicker_roster([
            {"player_id": "00-0000105", "player_name": "Good Kicker",
             "team": "DAL", "pff_id": "105"}
        ])
        engine = KickerEngine(KickerConfig(), loader, [2024])
        engine.build_crosswalk(roster, 2024)
        model = engine.compute("00-0000105")
        assert isinstance(model, KickingModel)
        assert set(model.fg_make_rate.keys()) == {"0_39", "40_49", "50_plus"}
        for key, rate in model.fg_make_rate.items():
            assert 0.0 <= rate <= 1.0, f"{key} rate out of range: {rate}"
        assert 0.0 <= model.xp_rate <= 1.0

    def test_zero_attempts_in_bucket_uses_league_avg(self, pff_dir, loader):
        """Kicker with zero 40-49 attempts → that bucket equals league 40-49 avg."""
        _write_field_goal_summary(pff_dir, 2024, [
            {
                "player_id": 106, "player": "Short Kicker", "team": "MIA",
                "n_games": 10,
                # Only short kicks, no forties
                "twenty_attempts": 2, "twenty_made": 2,
                "pat_attempts": 3, "pat_made": 3,
            }
        ])
        roster = _make_kicker_roster([
            {"player_id": "00-0000106", "player_name": "Short Kicker",
             "team": "MIA", "pff_id": "106"}
        ])
        engine = KickerEngine(KickerConfig(prior_strength=20), loader, [2024])
        engine.build_crosswalk(roster, 2024)
        model = engine.compute("00-0000106")
        assert model is not None
        league_40 = engine._league_rates["40_49"]
        assert abs(model.fg_make_rate["40_49"] - league_40) < 1e-9

    def test_crosswalk_pff_id_match(self, pff_dir, loader):
        """Layer 1 crosswalk works: pff_id in roster matches PFF player_id."""
        _write_field_goal_summary(pff_dir, 2024, [
            {
                "player_id": 200, "player": "Layer1 Kicker", "team": "GB",
                "n_games": 10,
                "forty_attempts": 2, "forty_made": 2,
                "pat_attempts": 3, "pat_made": 3,
            }
        ])
        # pff_id = "200" matches PFF player_id = 200
        roster = _make_kicker_roster([
            {"player_id": "00-0000200", "player_name": "Layer1 Kicker",
             "team": "GB", "pff_id": "200"}
        ])
        engine = KickerEngine(KickerConfig(), loader, [2024])
        engine.build_crosswalk(roster, 2024)
        # Layer 1 match should populate the crosswalk
        assert engine._nfl_to_pff.get("00-0000200") == 200
        assert engine._pff_to_nfl.get(200) == "00-0000200"

    def test_crosswalk_name_team_fallback(self, pff_dir, loader):
        """Layer 2 crosswalk works: name+team match when pff_id is null."""
        _write_field_goal_summary(pff_dir, 2024, [
            {
                "player_id": 201, "player": "Layer2 Kicker", "team": "SEA",
                "n_games": 10,
                "forty_attempts": 2, "forty_made": 2,
                "pat_attempts": 3, "pat_made": 3,
            }
        ])
        # No pff_id, but name + team match
        roster = _make_kicker_roster([
            {"player_id": "00-0000201", "player_name": "Layer2 Kicker",
             "team": "SEA", "pff_id": None}
        ])
        engine = KickerEngine(KickerConfig(), loader, [2024])
        engine.build_crosswalk(roster, 2024)
        # Layer 2 (name+team) should populate the crosswalk
        assert engine._nfl_to_pff.get("00-0000201") == 201
        assert engine._pff_to_nfl.get(201) == "00-0000201"

    def test_no_pff_data_empty_engine(self, loader):
        """No parquet files → compute returns None for any kicker."""
        # loader points at empty dir — no field_goal_summary parquets
        engine = KickerEngine(KickerConfig(), loader, [2024])
        engine.build_crosswalk(pl.DataFrame(), 2024)
        assert engine.compute("00-0000999") is None

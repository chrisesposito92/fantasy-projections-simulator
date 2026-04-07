"""Tests for NFL stadium registry."""

import pytest

from fantasy_sim.data.weather.stadiums import (
    STADIUMS,
    StadiumInfo,
    get_stadium,
    is_indoor,
)

ALL_TEAMS = [
    "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE",
    "DAL", "DEN", "DET", "GB", "HOU", "IND", "JAX", "KC",
    "LA", "LAC", "LV", "MIA", "MIN", "NE", "NO", "NYG",
    "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN", "WAS",
]

DOME_TEAMS = {"ARI", "ATL", "DAL", "DET", "HOU", "IND", "LA", "LAC", "LV", "MIN", "NO"}


class TestStadiumInfo:
    def test_frozen(self):
        info = StadiumInfo(name="Test", latitude=40.0, longitude=-74.0, venue_type="outdoor")
        with pytest.raises(AttributeError):
            info.latitude = 50.0


class TestStadiumRegistry:
    def test_all_32_teams_present(self):
        for team in ALL_TEAMS:
            assert team in STADIUMS, f"Missing stadium for {team}"

    def test_no_extra_teams(self):
        for team in STADIUMS:
            assert team in ALL_TEAMS, f"Unexpected team {team} in registry"

    def test_latitude_bounds(self):
        for team, info in STADIUMS.items():
            assert 25.0 <= info.latitude <= 48.5, (
                f"{team}: latitude {info.latitude} out of continental US bounds"
            )

    def test_longitude_bounds(self):
        for team, info in STADIUMS.items():
            assert -125.0 <= info.longitude <= -70.0, (
                f"{team}: longitude {info.longitude} out of continental US bounds"
            )

    def test_shared_stadiums_same_coords(self):
        assert STADIUMS["LA"].latitude == STADIUMS["LAC"].latitude
        assert STADIUMS["LA"].longitude == STADIUMS["LAC"].longitude
        assert STADIUMS["NYG"].latitude == STADIUMS["NYJ"].latitude
        assert STADIUMS["NYG"].longitude == STADIUMS["NYJ"].longitude

    def test_venue_types_valid(self):
        for team, info in STADIUMS.items():
            assert info.venue_type in ("outdoor", "dome", "retractable"), (
                f"{team}: invalid venue_type '{info.venue_type}'"
            )


class TestIsIndoor:
    def test_dome_teams(self):
        for team in DOME_TEAMS:
            assert is_indoor(team) is True, f"{team} should be indoor"

    def test_outdoor_teams(self):
        outdoor = set(ALL_TEAMS) - DOME_TEAMS
        for team in outdoor:
            assert is_indoor(team) is False, f"{team} should be outdoor"

    def test_unknown_team(self):
        assert is_indoor("ZZZ") is False


class TestGetStadium:
    def test_known_team(self):
        info = get_stadium("KC")
        assert info is not None
        assert info.name == "GEHA Field at Arrowhead Stadium"
        assert info.venue_type == "outdoor"

    def test_unknown_team(self):
        assert get_stadium("ZZZ") is None

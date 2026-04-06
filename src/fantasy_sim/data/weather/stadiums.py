"""NFL stadium registry — team to location and venue type mapping."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StadiumInfo:
    """Stadium metadata for weather lookups."""
    name: str
    latitude: float
    longitude: float
    venue_type: str  # "outdoor" | "dome" | "retractable"


STADIUMS: dict[str, StadiumInfo] = {
    "ARI": StadiumInfo("State Farm Stadium", 33.5276, -112.2626, "retractable"),
    "ATL": StadiumInfo("Mercedes-Benz Stadium", 33.7554, -84.4010, "retractable"),
    "BAL": StadiumInfo("M&T Bank Stadium", 39.2780, -76.6227, "outdoor"),
    "BUF": StadiumInfo("Highmark Stadium", 42.7738, -78.7870, "outdoor"),
    "CAR": StadiumInfo("Bank of America Stadium", 35.2258, -80.8528, "outdoor"),
    "CHI": StadiumInfo("Soldier Field", 41.8623, -87.6167, "outdoor"),
    "CIN": StadiumInfo("Paycor Stadium", 39.0955, -84.5161, "outdoor"),
    "CLE": StadiumInfo("Cleveland Browns Stadium", 41.5061, -81.6995, "outdoor"),
    "DAL": StadiumInfo("AT&T Stadium", 32.7473, -97.0945, "retractable"),
    "DEN": StadiumInfo("Empower Field at Mile High", 39.7439, -105.0201, "outdoor"),
    "DET": StadiumInfo("Ford Field", 42.3400, -83.0456, "dome"),
    "GB": StadiumInfo("Lambeau Field", 44.5013, -88.0622, "outdoor"),
    "HOU": StadiumInfo("NRG Stadium", 29.6847, -95.4107, "retractable"),
    "IND": StadiumInfo("Lucas Oil Stadium", 39.7601, -86.1639, "retractable"),
    "JAX": StadiumInfo("EverBank Stadium", 30.3239, -81.6373, "outdoor"),
    "KC": StadiumInfo("GEHA Field at Arrowhead Stadium", 39.0489, -94.4839, "outdoor"),
    "LA": StadiumInfo("SoFi Stadium", 33.9534, -118.3390, "dome"),
    "LAC": StadiumInfo("SoFi Stadium", 33.9534, -118.3390, "dome"),
    "LV": StadiumInfo("Allegiant Stadium", 36.0909, -115.1833, "dome"),
    "MIA": StadiumInfo("Hard Rock Stadium", 25.9580, -80.2389, "outdoor"),
    "MIN": StadiumInfo("U.S. Bank Stadium", 44.9736, -93.2575, "dome"),
    "NE": StadiumInfo("Gillette Stadium", 42.0909, -71.2643, "outdoor"),
    "NO": StadiumInfo("Caesars Superdome", 29.9511, -90.0812, "dome"),
    "NYG": StadiumInfo("MetLife Stadium", 40.8128, -74.0742, "outdoor"),
    "NYJ": StadiumInfo("MetLife Stadium", 40.8128, -74.0742, "outdoor"),
    "PHI": StadiumInfo("Lincoln Financial Field", 39.9008, -75.1675, "outdoor"),
    "PIT": StadiumInfo("Acrisure Stadium", 40.4468, -80.0158, "outdoor"),
    "SEA": StadiumInfo("Lumen Field", 47.5952, -122.3316, "outdoor"),
    "SF": StadiumInfo("Levi's Stadium", 37.4033, -121.9694, "outdoor"),
    "TB": StadiumInfo("Raymond James Stadium", 27.9759, -82.5033, "outdoor"),
    "TEN": StadiumInfo("Nissan Stadium", 36.1665, -86.7713, "outdoor"),
    "WAS": StadiumInfo("Northwest Stadium", 38.9076, -76.8645, "outdoor"),
}


def get_stadium(team: str) -> StadiumInfo | None:
    """Get stadium info for a team abbreviation. Returns None if unknown."""
    return STADIUMS.get(team)


def is_indoor(team: str) -> bool:
    """Return True if the team plays in a dome or retractable-roof stadium."""
    info = STADIUMS.get(team)
    if info is None:
        return False
    return info.venue_type in ("dome", "retractable")

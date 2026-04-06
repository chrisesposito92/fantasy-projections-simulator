"""Integration tests — weather engine applied via build_game() pipeline."""

import numpy as np
import pytest

from fantasy_sim.data.game_context import GameContextBuilder
from fantasy_sim.data.weather.models import GameWeather, WeatherConfig, WeatherContext
from fantasy_sim.data.weather.engine import compute_weather_factors
from fantasy_sim.engine.types import TeamDistributions
from fantasy_sim.models.distributions import (
    PlayCallingDist, PlayOutcomeDist, TurnoverRates, KickingModel, DriveStartModel,
)
from fantasy_sim.models.player import TeamRoster, PlayerModel, PlayerUsage, PlayerOutcomes


def _make_test_dists(team: str) -> TeamDistributions:
    return TeamDistributions(
        play_calling=PlayCallingDist(team=team, distributions={}, default={"pass": 0.5, "run": 0.5}),
        play_outcomes=PlayOutcomeDist(distributions={}),
        turnover_rates=TurnoverRates(team=team, int_rate=0.025, fumble_rate=0.012, sack_rate=0.065, sack_fumble_rate=0.10),
        kicking=KickingModel(fg_make_rate={"0_39": 0.93, "40_49": 0.84, "50_plus": 0.67}, xp_rate=0.95),
        drive_start=DriveStartModel(touchback_rate=0.6, touchback_yardline=75, return_yardlines=np.array([75])),
    )


def _make_test_roster(team: str) -> TeamRoster:
    return TeamRoster(team=team, players=[
        PlayerModel(f"{team}_QB", "QB1", "QB", team,
                    PlayerUsage(snap_share=1.0), PlayerOutcomes()),
        PlayerModel(f"{team}_WR1", "WR1", "WR", team,
                    PlayerUsage(target_share=0.25),
                    PlayerOutcomes(catch_rate=0.65, receiving_yards_dist=np.array([5, 8, 12, 15, 20]))),
        PlayerModel(f"{team}_RB1", "RB1", "RB", team,
                    PlayerUsage(carry_share=0.60, target_share=0.10),
                    PlayerOutcomes(
                        rushing_yards_dist=np.array([2, 3, 4, 5, 6]),
                        catch_rate=0.70, receiving_yards_dist=np.array([3, 5, 7]),
                        fumble_rate=0.008)),
    ])


class TestApplyWeather:
    def test_weather_modifies_kicking(self):
        """Weather with wind should reduce FG accuracy."""
        dists = _make_test_dists("KC")
        roster = _make_test_roster("KC")
        gw = GameWeather(wind_speed_mph=25.0, temperature_f=72.0,
                         precipitation_inches=0.0, precipitation_type="none")
        ctx = compute_weather_factors(gw, WeatherConfig())

        original_fg_50 = dists.kicking.fg_make_rate["50_plus"]
        GameContextBuilder._apply_weather(dists, roster, ctx)
        assert dists.kicking.fg_make_rate["50_plus"] < original_fg_50

    def test_weather_modifies_turnover_rates(self):
        """Cold + rain should increase fumble rate."""
        dists = _make_test_dists("GB")
        roster = _make_test_roster("GB")
        gw = GameWeather(wind_speed_mph=15.0, temperature_f=20.0,
                         precipitation_inches=0.3, precipitation_type="rain")
        ctx = compute_weather_factors(gw, WeatherConfig())

        original_fumble = dists.turnover_rates.fumble_rate
        original_int = dists.turnover_rates.int_rate
        GameContextBuilder._apply_weather(dists, roster, ctx)
        assert dists.turnover_rates.fumble_rate > original_fumble
        assert dists.turnover_rates.int_rate > original_int

    def test_weather_modifies_catch_rate(self):
        """Rain should reduce catch rate on receivers."""
        dists = _make_test_dists("BUF")
        roster = _make_test_roster("BUF")
        gw = GameWeather(wind_speed_mph=0.0, temperature_f=72.0,
                         precipitation_inches=0.8, precipitation_type="rain")
        ctx = compute_weather_factors(gw, WeatherConfig())

        wr = next(p for p in roster.players if p.position == "WR")
        original_cr = wr.outcomes.catch_rate
        GameContextBuilder._apply_weather(dists, roster, ctx)
        assert wr.outcomes.catch_rate < original_cr

    def test_weather_modifies_receiving_yards(self):
        """Wind should shift receiving yards distributions down."""
        dists = _make_test_dists("CHI")
        roster = _make_test_roster("CHI")
        gw = GameWeather(wind_speed_mph=25.0, temperature_f=72.0,
                         precipitation_inches=0.0, precipitation_type="none")
        ctx = compute_weather_factors(gw, WeatherConfig())

        wr = next(p for p in roster.players if p.position == "WR")
        original_mean = np.mean(wr.outcomes.receiving_yards_dist)
        GameContextBuilder._apply_weather(dists, roster, ctx)
        assert np.mean(wr.outcomes.receiving_yards_dist) < original_mean

    def test_neutral_weather_no_change(self):
        """Calm/warm/dry weather should not modify any distributions."""
        dists = _make_test_dists("MIA")
        roster = _make_test_roster("MIA")
        ctx = WeatherContext()  # all 1.0

        original_fg = dict(dists.kicking.fg_make_rate)
        original_fumble = dists.turnover_rates.fumble_rate
        wr = next(p for p in roster.players if p.position == "WR")
        original_cr = wr.outcomes.catch_rate

        GameContextBuilder._apply_weather(dists, roster, ctx)
        assert dists.kicking.fg_make_rate == original_fg
        assert dists.turnover_rates.fumble_rate == original_fumble
        assert wr.outcomes.catch_rate == original_cr

    def test_symmetric_application(self):
        """Both teams should get identical weather adjustments."""
        gw = GameWeather(wind_speed_mph=20.0, temperature_f=30.0,
                         precipitation_inches=0.5, precipitation_type="rain")
        ctx = compute_weather_factors(gw, WeatherConfig())

        home_dists = _make_test_dists("KC")
        away_dists = _make_test_dists("BUF")
        home_roster = _make_test_roster("KC")
        away_roster = _make_test_roster("BUF")

        GameContextBuilder._apply_weather(home_dists, home_roster, ctx)
        GameContextBuilder._apply_weather(away_dists, away_roster, ctx)

        assert home_dists.kicking.fg_make_rate == away_dists.kicking.fg_make_rate
        assert home_dists.turnover_rates.fumble_rate == pytest.approx(
            away_dists.turnover_rates.fumble_rate
        )

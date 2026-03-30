"""Build game context (TeamDistributions + TeamRoster) from nflverse data."""

from pathlib import Path
import polars as pl
import numpy as np
from fantasy_sim.data.loader import DataLoader, DEFAULT_CACHE_DIR
from fantasy_sim.data.pipeline import DataPipeline
from fantasy_sim.data.player_builder import (
    build_team_roster,
    _aggregate_pbp_stats, _assemble_models,
)
from fantasy_sim.engine.types import TeamDistributions
from fantasy_sim.models.distributions import (
    PlayCallingDist, TurnoverRates,
)
from fantasy_sim.models.player import TeamRoster, PlayerModel, PlayerUsage, PlayerOutcomes
from fantasy_sim.overrides.parser import OverrideSet
from fantasy_sim.overrides.engine import apply_player_override, apply_team_override
from fantasy_sim.overrides.resolver import PlayerResolver


# League average fallbacks for teams with no data
_DEFAULT_PLAY_CALLING = PlayCallingDist(
    team="LGA", distributions={}, default={"pass": 0.57, "run": 0.43}
)
_DEFAULT_TURNOVER_RATES = TurnoverRates(
    team="LGA", int_rate=0.025, fumble_rate=0.012,
    sack_rate=0.065, sack_fumble_rate=0.10,
)


class GameContextBuilder:
    """Builds TeamDistributions + TeamRoster from real nflverse data."""

    def __init__(self, cache_dir: Path = DEFAULT_CACHE_DIR):
        self.cache_dir = Path(cache_dir)
        self.loader = DataLoader(cache_dir=self.cache_dir)
        self._pipeline_cache: dict | None = None
        self._cached_training_seasons: list[int] | None = None
        self._pbp_stats_cache: dict | None = None
        self._player_models_cache: dict | None = None
        self._player_cache_key: tuple | None = None

    def _ensure_pipeline(
        self,
        training_seasons: list[int],
        pbp: pl.DataFrame | None = None,
        rosters: pl.DataFrame | None = None,
        target_season: int | None = None,
        week: int | None = None,
    ) -> tuple[dict, dict]:
        """Build and cache pipeline output + player models.

        Three cache layers:
        1. Pipeline output (team distributions) — cached on training_seasons.
        2. PBP stats — cached on training_seasons.
        3. Player models — cached on (training_seasons, target_season, week).
        """
        # Load PBP if not provided (needed for both pipeline and player models)
        if pbp is None:
            pbp = self.loader.load_pbp(training_seasons)

        # --- Layer 1: Pipeline output (cached on training_seasons) ---
        if (
            self._pipeline_cache is None
            or self._cached_training_seasons != training_seasons
        ):
            pipeline = DataPipeline(cache_dir=self.cache_dir, seasons=training_seasons)
            self._pipeline_cache = pipeline.build(pbp=pbp)
            self._cached_training_seasons = training_seasons
            self._pbp_stats_cache = None

        # --- Layer 2: PBP stats (cached on training_seasons) ---
        if self._pbp_stats_cache is None:
            self._pbp_stats_cache = _aggregate_pbp_stats(pbp, training_seasons)

        # --- Layer 3: Player models (cached on training_seasons + target_season + week) ---
        cache_key = (tuple(training_seasons), target_season, week)
        if self._player_models_cache is None or self._player_cache_key != cache_key:
            # Determine current rosters
            if rosters is not None:
                current_rosters = rosters
            else:
                roster_season = target_season or (max(training_seasons) + 1)
                current_rosters = self.loader.load_rosters([roster_season])

            # Filter by week if specified
            if week is not None:
                current_rosters = current_rosters.filter(pl.col("week") <= week)

            self._player_models_cache = _assemble_models(
                self._pbp_stats_cache, current_rosters
            )
            self._player_cache_key = cache_key

        return self._pipeline_cache, self._player_models_cache

    def build_team_distributions(
        self,
        team: str,
        training_seasons: list[int] | None = None,
        pbp: pl.DataFrame | None = None,
        rosters: pl.DataFrame | None = None,
        target_season: int | None = None,
        week: int | None = None,
    ) -> TeamDistributions:
        """Build TeamDistributions for a specific team."""
        training_seasons = training_seasons or [2022, 2023, 2024]
        pipeline_output, _ = self._ensure_pipeline(
            training_seasons, pbp, rosters, target_season, week
        )

        play_calling = pipeline_output["play_calling"].get(team, _DEFAULT_PLAY_CALLING)
        if play_calling.team != team:
            play_calling = PlayCallingDist(
                team=team, distributions={}, default=play_calling.default
            )

        turnover_rates = pipeline_output["turnover_rates"].get(team, _DEFAULT_TURNOVER_RATES)
        if turnover_rates.team != team:
            turnover_rates = TurnoverRates(
                team=team, int_rate=turnover_rates.int_rate,
                fumble_rate=turnover_rates.fumble_rate,
                sack_rate=turnover_rates.sack_rate,
                sack_fumble_rate=turnover_rates.sack_fumble_rate,
            )

        return TeamDistributions(
            play_calling=play_calling,
            play_outcomes=pipeline_output["play_outcomes"],
            turnover_rates=turnover_rates,
            kicking=pipeline_output["kicking"],
            drive_start=pipeline_output["drive_start"],
        )

    def build_team_roster(
        self,
        team: str,
        training_seasons: list[int] | None = None,
        pbp: pl.DataFrame | None = None,
        rosters: pl.DataFrame | None = None,
        target_season: int | None = None,
        week: int | None = None,
    ) -> TeamRoster:
        """Build TeamRoster for a specific team."""
        training_seasons = training_seasons or [2022, 2023, 2024]
        _, player_models = self._ensure_pipeline(
            training_seasons, pbp, rosters, target_season, week
        )
        roster = build_team_roster(team, player_models)
        if not roster.players:
            roster = TeamRoster(team=team, players=[
                PlayerModel(
                    f"{team}_QB", "QB", "QB", team,
                    PlayerUsage(snap_share=1.0), PlayerOutcomes(),
                ),
                PlayerModel(
                    f"{team}_RB", "RB", "RB", team,
                    PlayerUsage(carry_share=1.0, target_share=0.15),
                    PlayerOutcomes(
                        rushing_yards_dist=np.array([2, 3, 4, 5, 6]),
                        catch_rate=0.65,
                        receiving_yards_dist=np.array([3, 5, 7]),
                    ),
                ),
                PlayerModel(
                    f"{team}_WR", "WR", "WR", team,
                    PlayerUsage(target_share=0.85),
                    PlayerOutcomes(
                        catch_rate=0.60,
                        receiving_yards_dist=np.array([5, 8, 12, 15, 20]),
                    ),
                ),
            ])
        return roster

    def build_game(
        self,
        home_team: str,
        away_team: str,
        training_seasons: list[int] | None = None,
        target_season: int | None = None,
        week: int | None = None,
        pbp: pl.DataFrame | None = None,
        rosters: pl.DataFrame | None = None,
    ) -> tuple[TeamDistributions, TeamDistributions, TeamRoster, TeamRoster]:
        """Build all context needed to simulate one game."""
        home_dists = self.build_team_distributions(
            home_team, training_seasons, pbp, rosters, target_season, week
        )
        away_dists = self.build_team_distributions(
            away_team, training_seasons, pbp, rosters, target_season, week
        )
        home_roster = self.build_team_roster(
            home_team, training_seasons, pbp, rosters, target_season, week
        )
        away_roster = self.build_team_roster(
            away_team, training_seasons, pbp, rosters, target_season, week
        )
        return home_dists, away_dists, home_roster, away_roster


def apply_overrides(
    overrides: OverrideSet,
    home_dists: TeamDistributions,
    away_dists: TeamDistributions,
    home_roster: TeamRoster,
    away_roster: TeamRoster,
) -> None:
    """Apply player and team overrides to distributions and rosters. Mutates in place."""
    # Build resolver from both rosters
    resolver = PlayerResolver([home_roster, away_roster])

    # Apply team overrides
    for team, team_overrides in overrides.teams.items():
        if team == home_roster.team:
            apply_team_override(home_dists, team_overrides)
        elif team == away_roster.team:
            apply_team_override(away_dists, team_overrides)

    # Apply player overrides
    for player_query, player_overrides in overrides.players.items():
        try:
            player_id = resolver.resolve(player_query)
        except KeyError:
            continue  # Skip unresolvable players

        # Find which roster the player is on
        for roster in [home_roster, away_roster]:
            if any(p.player_id == player_id for p in roster.players):
                apply_player_override(roster, player_id, player_overrides)
                break

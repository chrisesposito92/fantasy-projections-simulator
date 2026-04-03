"""Build game context (TeamDistributions + TeamRoster) from nflverse data."""

import logging
from pathlib import Path
import polars as pl
import numpy as np
from fantasy_sim.data.loader import DataLoader, DEFAULT_CACHE_DIR
from fantasy_sim.data.pipeline import DataPipeline
from fantasy_sim.data.player_builder import (
    build_team_roster,
    _aggregate_pbp_stats, _assemble_models,
)
from fantasy_sim.data.pff.models import PffConfig, MatchupContext
from fantasy_sim.engine.types import TeamDistributions
from fantasy_sim.models.distributions import (
    PlayCallingDist, TurnoverRates,
)
from fantasy_sim.models.player import TeamRoster, PlayerModel, PlayerUsage, PlayerOutcomes
from fantasy_sim.overrides.parser import OverrideSet
from fantasy_sim.overrides.engine import apply_player_override, apply_team_override
from fantasy_sim.overrides.resolver import PlayerResolver

logger = logging.getLogger(__name__)


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

    def __init__(
        self,
        cache_dir: Path = DEFAULT_CACHE_DIR,
        pff_config: PffConfig | None = None,
    ):
        self.cache_dir = Path(cache_dir)
        self.loader = DataLoader(cache_dir=self.cache_dir)
        self._pipeline_cache: dict | None = None
        self._cached_training_seasons: tuple[int, ...] | None = None
        self._pbp_stats_cache: dict | None = None
        self._player_models_cache: dict | None = None
        self._player_cache_key: tuple | None = None

        # PFF setup: create loader once, share it across matchup + talent engines
        self._pff_config = pff_config or PffConfig()
        self._matchup_engine = None
        self._talent_stabilizer = None
        self._pff_crosswalk: dict[int, str] | None = None
        self._pff_loader = None

        if self._pff_config.enabled:
            from fantasy_sim.data.pff.loader import PffLoader
            pff_dir = Path(self._pff_config.data_dir) if self._pff_config.data_dir else None
            pff_loader = PffLoader(pff_dir)
            if pff_loader.is_available():
                self._pff_loader = pff_loader

        if self._pff_config.enabled and self._pff_config.matchup.enabled and self._pff_loader:
            from fantasy_sim.data.pff.matchup import MatchupEngine
            self._matchup_engine = MatchupEngine(self._pff_config, self._pff_loader)
            logger.info("PFF matchup engine enabled")

        if self._pff_config.enabled and self._pff_config.talent.enabled and self._pff_loader:
            from fantasy_sim.data.pff.talent import TalentStabilizer
            self._talent_stabilizer = TalentStabilizer(self._pff_config, self._pff_loader)
            logger.info("PFF talent stabilizer enabled")

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
        ts_key = tuple(sorted(training_seasons))
        if (
            self._pipeline_cache is None
            or self._cached_training_seasons != ts_key
        ):
            pipeline = DataPipeline(cache_dir=self.cache_dir, seasons=training_seasons)
            self._pipeline_cache = pipeline.build(pbp=pbp)
            self._cached_training_seasons = ts_key
            self._pbp_stats_cache = None

        # --- Layer 2: PBP stats (cached on training_seasons) ---
        if self._pbp_stats_cache is None:
            self._pbp_stats_cache = _aggregate_pbp_stats(pbp, training_seasons)

        # --- Layer 3: Player models (cached on training_seasons + target_season + week) ---
        cache_key = (ts_key, target_season, week)
        if self._player_models_cache is None or self._player_cache_key != cache_key:
            # Determine current rosters
            if rosters is not None:
                current_rosters = rosters
                # Filter to target_season if provided to prevent wrong-season assignments
                if target_season is not None and "season" in current_rosters.columns:
                    current_rosters = current_rosters.filter(pl.col("season") == target_season)
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

    @staticmethod
    def _apply_matchup(
        dists: TeamDistributions,
        roster: TeamRoster,
        ctx: MatchupContext,
    ) -> None:
        """Apply MatchupContext factors to TeamDistributions and TeamRoster in-place.

        Factors are centered on 1.0 (neutral).  Only non-neutral factors
        (i.e. != 1.0) are applied to avoid unnecessary mutation.
        """
        # --- Receivers: catch_rate and red_zone_catch_rate ---
        if ctx.catch_rate_factor != 1.0:
            for player in roster.players:
                if player.usage.target_share > 0 and player.outcomes.catch_rate > 0:
                    player.outcomes.catch_rate = max(
                        0.0, min(1.0, player.outcomes.catch_rate * ctx.catch_rate_factor)
                    )
                    player.outcomes.red_zone_catch_rate = max(
                        0.0,
                        min(
                            1.0,
                            player.outcomes.red_zone_catch_rate * ctx.catch_rate_factor,
                        ),
                    )

        # --- Turnover rates ---
        combined_sack = ctx.sack_rate_factor * ctx.ol_pass_block_factor
        if combined_sack != 1.0:
            dists.turnover_rates.sack_rate = (
                dists.turnover_rates.sack_rate * combined_sack
            )

        if ctx.int_rate_factor != 1.0:
            dists.turnover_rates.int_rate = (
                dists.turnover_rates.int_rate * ctx.int_rate_factor
            )

        # --- Receiving yards: additive shift on each receiver's distribution ---
        if ctx.pass_yards_factor != 1.0:
            shift = (ctx.pass_yards_factor - 1.0) * 10.0
            for player in roster.players:
                if (
                    player.usage.target_share > 0
                    and player.outcomes.receiving_yards_dist is not None
                    and len(player.outcomes.receiving_yards_dist) > 0
                ):
                    player.outcomes.receiving_yards_dist = (
                        player.outcomes.receiving_yards_dist + shift
                    )

        # --- Rushing yards: additive shift on each rusher's distribution ---
        combined_rush = ctx.rush_yards_factor * ctx.ol_run_block_factor
        if combined_rush != 1.0:
            shift = (combined_rush - 1.0) * 10.0
            for player in roster.players:
                if (
                    player.usage.carry_share > 0
                    and player.outcomes.rushing_yards_dist is not None
                    and len(player.outcomes.rushing_yards_dist) > 0
                ):
                    player.outcomes.rushing_yards_dist = (
                        player.outcomes.rushing_yards_dist + shift
                    )

    def _ensure_pff_crosswalk(
        self,
        training_seasons: list[int],
        target_season: int | None = None,
    ) -> None:
        """Build PFF crosswalk if not already cached."""
        if self._pff_crosswalk is not None or self._pff_loader is None:
            return

        frames = []
        for facet in ("receiving_summary", "rushing_summary", "passing_summary"):
            df = self._pff_loader.load_facet(facet, training_seasons)
            if not df.is_empty():
                frames.append(df.select(["player_id", "player", "team"]))
        if not frames:
            return

        pff_data = pl.concat(frames).unique(subset=["player_id"])
        roster_season = target_season or max(training_seasons)
        nfl_roster = self.loader.load_rosters([roster_season])
        self._pff_crosswalk = self._pff_loader.build_crosswalk(
            pff_data, nfl_roster, roster_season
        )

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
        training_seasons = training_seasons or [2022, 2023, 2024]
        home_dists = self.build_team_distributions(
            home_team, training_seasons=training_seasons, pbp=pbp,
            rosters=rosters, target_season=target_season, week=week,
        )
        away_dists = self.build_team_distributions(
            away_team, training_seasons=training_seasons, pbp=pbp,
            rosters=rosters, target_season=target_season, week=week,
        )
        home_roster = self.build_team_roster(
            home_team, training_seasons=training_seasons, pbp=pbp,
            rosters=rosters, target_season=target_season, week=week,
        )
        away_roster = self.build_team_roster(
            away_team, training_seasons=training_seasons, pbp=pbp,
            rosters=rosters, target_season=target_season, week=week,
        )

        # PFF matchup adjustments: away D → home offense, home D → away offense
        if self._matchup_engine is not None:
            home_ctx = self._matchup_engine.compute(
                defense_team=away_team,
                offense_team=home_team,
                training_seasons=training_seasons,
            )
            away_ctx = self._matchup_engine.compute(
                defense_team=home_team,
                offense_team=away_team,
                training_seasons=training_seasons,
            )
            self._apply_matchup(home_dists, home_roster, home_ctx)
            self._apply_matchup(away_dists, away_roster, away_ctx)

        # PFF talent stabilization
        if self._talent_stabilizer is not None:
            from fantasy_sim.data.player_builder import _normalize_roster_shares
            self._ensure_pff_crosswalk(training_seasons, target_season)
            roster_season = target_season or max(training_seasons)
            nfl_roster_df = self.loader.load_rosters([roster_season])
            self._talent_stabilizer.stabilize_roster(
                home_roster, self._pff_crosswalk, training_seasons,
                nfl_roster=nfl_roster_df, target_season=roster_season,
            )
            self._talent_stabilizer.stabilize_roster(
                away_roster, self._pff_crosswalk, training_seasons,
                nfl_roster=nfl_roster_df, target_season=roster_season,
            )
            _normalize_roster_shares(home_roster)
            _normalize_roster_shares(away_roster)

        return home_dists, away_dists, home_roster, away_roster


def pre_resolve_overrides(
    overrides: OverrideSet,
    all_rosters: list[TeamRoster],
) -> OverrideSet:
    """Resolve player override keys to exact player_ids using all rosters.

    This prevents fuzzy matching from accidentally applying overrides
    to wrong players when applied per-game (e.g. 'bijan_robinson'
    matching 'Wan'Dale Robinson' via partial_ratio).
    """
    if not overrides.players:
        return overrides

    resolver = PlayerResolver(all_rosters)
    resolved_players: dict[str, dict] = {}

    for player_query, player_overrides in overrides.players.items():
        try:
            player_id = resolver.resolve(player_query)
            resolved_players[player_id] = player_overrides
        except KeyError:
            import click
            click.echo(
                f"Warning: Could not resolve player override '{player_query}'. Skipping.",
                err=True,
            )

    return OverrideSet(players=resolved_players, teams=overrides.teams)


def apply_overrides(
    overrides: OverrideSet,
    home_dists: TeamDistributions,
    away_dists: TeamDistributions,
    home_roster: TeamRoster,
    away_roster: TeamRoster,
) -> None:
    """Apply player and team overrides to distributions and rosters. Mutates in place.

    Uses exact matching only (no fuzzy) to prevent cross-game contamination.
    Call pre_resolve_overrides() first to resolve fuzzy names to exact IDs.
    """
    # Build resolver from both rosters
    resolver = PlayerResolver([home_roster, away_roster])

    # Apply team overrides
    for team, team_overrides in overrides.teams.items():
        if team == home_roster.team:
            apply_team_override(home_dists, team_overrides)
        elif team == away_roster.team:
            apply_team_override(away_dists, team_overrides)

    # Apply player overrides (exact matching only)
    for player_query, player_overrides in overrides.players.items():
        try:
            player_id = resolver.resolve_exact(player_query)
        except KeyError:
            continue  # Player not on either team in this game

        # Find which roster the player is on
        for roster in [home_roster, away_roster]:
            if any(p.player_id == player_id for p in roster.players):
                apply_player_override(roster, player_id, player_overrides)
                break

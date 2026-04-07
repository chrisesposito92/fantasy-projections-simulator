"""Build game context (TeamDistributions + TeamRoster) from nflverse data."""

import copy
import logging
from pathlib import Path
import polars as pl
import numpy as np
from fantasy_sim.data.loader import DataLoader, DEFAULT_CACHE_DIR
from fantasy_sim.data.pipeline import DataPipeline
from fantasy_sim.data.player_builder import (
    build_team_roster,
    _aggregate_pbp_stats, _assemble_models, _build_season_weights,
)
from fantasy_sim.data.pff.models import PffConfig, MatchupContext, CoverageModifiers
from fantasy_sim.data.weather.models import WeatherConfig, WeatherContext
from fantasy_sim.data.vegas.models import PropsConfig, VegasConfig, VegasContext
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
        weather_config: WeatherConfig | None = None,
        vegas_config: VegasConfig | None = None,
        props_config: PropsConfig | None = None,
    ):
        self.cache_dir = Path(cache_dir)
        self.loader = DataLoader(cache_dir=self.cache_dir)
        self._pipeline_cache: dict | None = None
        self._cached_training_seasons: tuple[int, ...] | None = None
        self._pbp_stats_cache: dict | None = None
        self._pbp_stats_cache_key: tuple | None = None
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

        self._tier_engine = None

        if self._pff_config.enabled and self._pff_config.tier_engine.enabled and self._pff_loader:
            from fantasy_sim.data.pff.tier_engine import TierEngine
            self._tier_engine = TierEngine(self._pff_config.tier_engine, self._pff_loader)
            logger.info("PFF tier engine enabled")

        self._team_context_engine = None

        if self._pff_config.enabled and self._pff_config.team_context.enabled and self._pff_loader:
            from fantasy_sim.data.pff.team_context import TeamContextEngine
            self._team_context_engine = TeamContextEngine(
                self._pff_config.team_context, self._pff_loader
            )
            logger.info("PFF team context engine enabled")

        self._coverage_engine = None

        if self._pff_config.enabled and self._pff_config.coverage.enabled and self._pff_loader:
            from fantasy_sim.data.pff.coverage import CoverageEngine
            self._coverage_engine = CoverageEngine(
                self._pff_loader, self._pff_config.coverage
            )
            logger.info("PFF coverage engine enabled")

        self._kicker_engine = None
        self._dst_baseline_engine = None

        if self._pff_config.enabled and self._pff_config.kicker.enabled and self._pff_loader:
            from fantasy_sim.data.pff.kicker import KickerEngine
            self._kicker_engine = KickerEngine(
                self._pff_config.kicker, self._pff_loader, [],
            )
            logger.info("PFF kicker engine enabled")

        if self._pff_config.enabled and self._pff_config.dst_baseline.enabled and self._pff_loader:
            from fantasy_sim.data.pff.dst_baseline import DstBaselineEngine
            self._dst_baseline_engine = DstBaselineEngine(
                self._pff_config.dst_baseline, self._pff_loader, [],
            )
            logger.info("PFF DST baseline engine enabled")

        # Weather engine setup
        self._weather_engine = None
        if weather_config is not None and weather_config.enabled:
            from fantasy_sim.data.weather.engine import WeatherEngine
            self._weather_engine = WeatherEngine(
                config=weather_config,
                cache_dir=self.cache_dir.parent / "weather",
            )
            logger.info("Weather engine enabled")
        self._weather_config = weather_config

        # Vegas engine setup (ITT pace scaling + spread-based pass rate)
        self._vegas_engine = None
        if vegas_config is not None and vegas_config.enabled:
            from fantasy_sim.data.vegas.engine import VegasEngine
            self._vegas_engine = VegasEngine(config=vegas_config, loader=self.loader)
            logger.info("Vegas engine enabled")
        self._vegas_config = vegas_config

        # Player props engine setup (VEG-03: Bayesian prop blend)
        self._props_engine = None
        self._props_config = props_config
        if props_config is not None and props_config.enabled:
            from fantasy_sim.data.vegas.props_loader import PropsLoader
            from fantasy_sim.data.vegas.props_engine import PlayerPropsEngine
            props_loader = PropsLoader(props_config)
            self._props_engine = PlayerPropsEngine(props_config, props_loader)
            logger.info("Player props engine enabled")

    def _ensure_pipeline(
        self,
        training_seasons: list[int],
        pbp: pl.DataFrame | None = None,
        rosters: pl.DataFrame | None = None,
        target_season: int | None = None,
        week: int | None = None,
        season_weights: dict[int, float] | None = None,
    ) -> tuple[dict, dict]:
        """Build and cache pipeline output + player models.

        Three cache layers:
        1. Pipeline output (team distributions) — cached on training_seasons.
        2. PBP stats — cached on (training_seasons, season_weights).
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
            self._pipeline_cache = pipeline.build(pbp=pbp, season_weights=season_weights)
            self._cached_training_seasons = ts_key
            self._pbp_stats_cache = None

        # --- Layer 2: PBP stats (cached on training_seasons + season_weights) ---
        _pbp_key = (ts_key, tuple(sorted((season_weights or {}).items())))
        if self._pbp_stats_cache is None or self._pbp_stats_cache_key != _pbp_key:
            self._pbp_stats_cache = _aggregate_pbp_stats(pbp, training_seasons, season_weights=season_weights)
            self._pbp_stats_cache_key = _pbp_key

        # --- Layer 3: Player models (cached on training_seasons + target_season + week + props) ---
        props_enabled = getattr(self, "_props_engine", None) is not None
        cache_key = (ts_key, target_season, week, props_enabled)
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
        season_weights: dict[int, float] | None = None,
    ) -> TeamDistributions:
        """Build TeamDistributions for a specific team."""
        training_seasons = training_seasons or [2022, 2023, 2024]
        pipeline_output, _ = self._ensure_pipeline(
            training_seasons, pbp, rosters, target_season, week,
            season_weights=season_weights,
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
            kicking=copy.deepcopy(pipeline_output["kicking"]),
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
        season_weights: dict[int, float] | None = None,
    ) -> TeamRoster:
        """Build TeamRoster for a specific team."""
        training_seasons = training_seasons or [2022, 2023, 2024]
        _, player_models = self._ensure_pipeline(
            training_seasons, pbp, rosters, target_season, week,
            season_weights=season_weights,
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
                if player.position == "WR":
                    continue  # CoverageEngine owns WR catch_rate (D-01)
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

    @staticmethod
    def _apply_coverage(
        roster: TeamRoster,
        modifiers: dict[str, CoverageModifiers],
    ) -> None:
        """Apply per-WR coverage modifiers to roster in-place.

        Only modifies WR-position players. Multiplicative for catch_rate,
        additive shift for receiving_yards_dist (same pattern as _apply_matchup).
        """
        if not modifiers:
            return
        for player in roster.players:
            if player.position != "WR":
                continue
            mods = modifiers.get(player.player_id)
            if mods is None:
                continue
            if mods.catch_rate_modifier != 1.0:
                player.outcomes.catch_rate = max(
                    0.0, min(1.0, player.outcomes.catch_rate * mods.catch_rate_modifier)
                )
                player.outcomes.red_zone_catch_rate = max(
                    0.0,
                    min(1.0, player.outcomes.red_zone_catch_rate * mods.catch_rate_modifier),
                )
            if mods.ypr_modifier != 1.0:
                if (
                    player.outcomes.receiving_yards_dist is not None
                    and len(player.outcomes.receiving_yards_dist) > 0
                ):
                    shift = (mods.ypr_modifier - 1.0) * 10.0
                    player.outcomes.receiving_yards_dist = (
                        player.outcomes.receiving_yards_dist + shift
                    )

    @staticmethod
    def _apply_weather(
        dists: TeamDistributions,
        roster: TeamRoster,
        ctx: WeatherContext,
    ) -> None:
        """Apply weather factors to TeamDistributions and TeamRoster in-place.

        Factors centered on 1.0 (neutral). Only non-neutral factors are applied.
        Weather affects both teams identically — call once per team.
        """
        import numpy as np

        # --- Kicking ---
        for bucket in ("0_39", "40_49", "50_plus"):
            factor = ctx.fg_accuracy_factor.get(bucket, 1.0)
            if factor != 1.0:
                dists.kicking.fg_make_rate[bucket] = max(
                    0.0, min(1.0, dists.kicking.fg_make_rate[bucket] * factor)
                )
        if ctx.xp_accuracy_factor != 1.0:
            dists.kicking.xp_rate = max(
                0.0, min(1.0, dists.kicking.xp_rate * ctx.xp_accuracy_factor)
            )

        # --- Turnovers ---
        if ctx.fumble_rate_factor != 1.0:
            dists.turnover_rates.fumble_rate *= ctx.fumble_rate_factor
        if ctx.int_rate_factor != 1.0:
            dists.turnover_rates.int_rate *= ctx.int_rate_factor

        # --- Receivers: catch_rate and receiving_yards_dist ---
        if ctx.catch_rate_factor != 1.0:
            for player in roster.players:
                if player.usage.target_share > 0 and player.outcomes.catch_rate > 0:
                    player.outcomes.catch_rate = max(
                        0.0, min(1.0, player.outcomes.catch_rate * ctx.catch_rate_factor)
                    )
                    player.outcomes.red_zone_catch_rate = max(
                        0.0,
                        min(1.0, player.outcomes.red_zone_catch_rate * ctx.catch_rate_factor),
                    )

        if ctx.pass_yards_factor != 1.0:
            for player in roster.players:
                if (
                    player.usage.target_share > 0
                    and player.outcomes.receiving_yards_dist is not None
                    and len(player.outcomes.receiving_yards_dist) > 0
                ):
                    mean_yards = float(np.mean(player.outcomes.receiving_yards_dist))
                    shift = (ctx.pass_yards_factor - 1.0) * mean_yards
                    player.outcomes.receiving_yards_dist = (
                        player.outcomes.receiving_yards_dist + shift
                    )

    @staticmethod
    def _apply_vegas(
        dists: TeamDistributions,
        ctx: VegasContext,
    ) -> None:
        """Apply VegasContext factors to TeamDistributions in-place.

        VEG-01: volume_factor drives pace_factor (play volume, not yard efficiency).
            pace_factor > 1.0 = faster pace = less clock per play = more plays per game.
            pace_factor < 1.0 = slower pace = more clock per play = fewer plays per game.
            This is the correct lever for ITT: it controls the number of offensive
            opportunities, not per-play yards.

        VEG-02: pass_rate_factor modifies PlayCallingDist.default ONLY.
            Per-bucket distributions (the GameStateBucket dict) are never touched.
            Favorites run more (pass_rate_factor < 1.0), underdogs pass more (> 1.0).
            Clamped so pass+run always sum to 1.0 and neither hits zero.
        """
        # VEG-01: pace_factor (multiplicative, correct lever for game volume)
        if ctx.volume_factor != 1.0:
            dists.pace_factor *= ctx.volume_factor

        # VEG-02: pass rate (default only, NOT per-bucket distributions)
        if ctx.pass_rate_factor != 1.0:
            current_pass = dists.play_calling.default["pass"]
            new_pass = max(0.01, min(0.99, current_pass * ctx.pass_rate_factor))
            new_run = 1.0 - new_pass
            dists.play_calling.default = {"pass": new_pass, "run": new_run}

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
        season_weights: dict[int, float] | None = None,
    ) -> tuple[TeamDistributions, TeamDistributions, TeamRoster, TeamRoster]:
        """Build all context needed to simulate one game."""
        training_seasons = training_seasons or [2022, 2023, 2024]
        home_dists = self.build_team_distributions(
            home_team, training_seasons=training_seasons, pbp=pbp,
            rosters=rosters, target_season=target_season, week=week,
            season_weights=season_weights,
        )
        away_dists = self.build_team_distributions(
            away_team, training_seasons=training_seasons, pbp=pbp,
            rosters=rosters, target_season=target_season, week=week,
            season_weights=season_weights,
        )
        home_roster = self.build_team_roster(
            home_team, training_seasons=training_seasons, pbp=pbp,
            rosters=rosters, target_season=target_season, week=week,
            season_weights=season_weights,
        )
        away_roster = self.build_team_roster(
            away_team, training_seasons=training_seasons, pbp=pbp,
            rosters=rosters, target_season=target_season, week=week,
            season_weights=season_weights,
        )

        # Vegas adjustments (first: base volume + game script before PFF refines)
        if self._vegas_engine is not None and target_season and week:
            home_vegas_ctx, away_vegas_ctx = self._vegas_engine.compute(
                home_team=home_team, away_team=away_team,
                target_season=target_season, week=week,
            )
            self._apply_vegas(home_dists, home_vegas_ctx)
            self._apply_vegas(away_dists, away_vegas_ctx)

        # Player props (VEG-03): Bayesian blend of prop lines into player models
        # Applied before matchup engine so PFF adjustments layer on top.
        if self._props_engine is not None and target_season and week:
            self._props_engine.apply(home_roster, home_team, target_season, week)
            self._props_engine.apply(away_roster, away_team, target_season, week)
            # Re-normalize shares after props mutation (addresses MEDIUM review concern)
            from fantasy_sim.data.player_builder import _normalize_roster_shares
            _normalize_roster_shares(home_roster)
            _normalize_roster_shares(away_roster)

        # PFF matchup adjustments: away D → home offense, home D → away offense
        if self._matchup_engine is not None:
            home_ctx = self._matchup_engine.compute(
                defense_team=away_team,
                offense_team=home_team,
                target_season=target_season,
                max_week=week,
            )
            away_ctx = self._matchup_engine.compute(
                defense_team=home_team,
                offense_team=away_team,
                target_season=target_season,
                max_week=week,
            )
            self._apply_matchup(home_dists, home_roster, home_ctx)
            self._apply_matchup(away_dists, away_roster, away_ctx)

        # PFF tier engine (takes precedence over talent stabilizer)
        if self._tier_engine is not None:
            from fantasy_sim.data.player_builder import _normalize_roster_shares
            self._ensure_pff_crosswalk(training_seasons, target_season)
            roster_season = target_season or max(training_seasons)
            all_roster_seasons = training_seasons + [roster_season]
            nfl_roster_df = self.loader.load_rosters(all_roster_seasons)
            # Use passed PBP or load if not provided
            pbp_df = pbp if pbp is not None else self.loader.load_pbp(training_seasons)

            # Compute team context (season-level, per-team)
            home_ctx = None
            away_ctx = None
            if self._team_context_engine is not None and target_season and week:
                home_ctx = self._team_context_engine.compute(
                    team=home_roster.team,
                    target_season=target_season,
                    max_week=week,
                    pbp=pbp_df,
                )
                away_ctx = self._team_context_engine.compute(
                    team=away_roster.team,
                    target_season=target_season,
                    max_week=week,
                    pbp=pbp_df,
                )

            self._tier_engine.apply_tiers(
                home_roster, self._pff_crosswalk, training_seasons,
                pbp=pbp_df, nfl_roster=nfl_roster_df, target_season=roster_season,
                team_context=home_ctx,
            )
            self._tier_engine.apply_tiers(
                away_roster, self._pff_crosswalk, training_seasons,
                pbp=pbp_df, nfl_roster=nfl_roster_df, target_season=roster_season,
                team_context=away_ctx,
            )
            _normalize_roster_shares(home_roster)
            _normalize_roster_shares(away_roster)
        elif self._talent_stabilizer is not None:
            # Keep existing talent stabilizer block as-is
            from fantasy_sim.data.player_builder import _normalize_roster_shares
            self._ensure_pff_crosswalk(training_seasons, target_season)
            roster_season = target_season or max(training_seasons)
            all_roster_seasons = training_seasons + [roster_season]
            nfl_roster_df = self.loader.load_rosters(all_roster_seasons)
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

        # PFF coverage matchup (per-WR adjustments, last PFF step)
        if self._coverage_engine is not None and target_season and week:
            self._ensure_pff_crosswalk(training_seasons, target_season)
            home_cov = self._coverage_engine.compute(
                defense_team=away_team,
                offense_roster=home_roster,
                target_season=target_season,
                max_week=week,
                pff_crosswalk=self._pff_crosswalk,
            )
            away_cov = self._coverage_engine.compute(
                defense_team=home_team,
                offense_roster=away_roster,
                target_season=target_season,
                max_week=week,
                pff_crosswalk=self._pff_crosswalk,
            )
            self._apply_coverage(home_roster, home_cov)
            self._apply_coverage(away_roster, away_cov)

        # PFF DST baseline: fumble rate + defensive TD rates
        if self._dst_baseline_engine is not None and target_season and week:
            # Re-create engine with correct seasons if needed
            if self._dst_baseline_engine._seasons != training_seasons:
                from fantasy_sim.data.pff.dst_baseline import DstBaselineEngine
                self._dst_baseline_engine = DstBaselineEngine(
                    self._pff_config.dst_baseline, self._pff_loader,
                    training_seasons + ([target_season] if target_season not in training_seasons else []),
                )
            # Away defense adjusts home offense fumble rate, home defense adjusts away
            home_dst_ctx = self._dst_baseline_engine.compute(
                away_team, target_season, max_week=week,
            )
            away_dst_ctx = self._dst_baseline_engine.compute(
                home_team, target_season, max_week=week,
            )
            if home_dst_ctx.fumble_rate_factor != 1.0:
                home_dists.turnover_rates.fumble_rate *= home_dst_ctx.fumble_rate_factor
            if away_dst_ctx.fumble_rate_factor != 1.0:
                away_dists.turnover_rates.fumble_rate *= away_dst_ctx.fumble_rate_factor
            # Set team-specific defensive TD rates on defending team's dists
            from fantasy_sim.engine.types import DefensiveTdRates
            away_dists.defensive_td_rates = DefensiveTdRates(
                int_return_td_rate=home_dst_ctx.int_return_td_rate,
                fumble_return_td_rate=home_dst_ctx.fumble_return_td_rate,
            )
            home_dists.defensive_td_rates = DefensiveTdRates(
                int_return_td_rate=away_dst_ctx.int_return_td_rate,
                fumble_return_td_rate=away_dst_ctx.fumble_return_td_rate,
            )

        # PFF kicker: replace team-level KickingModel with per-kicker rates
        if self._kicker_engine is not None:
            # Re-create engine with correct seasons if needed
            if self._kicker_engine._data.is_empty() or not self._kicker_engine._nfl_to_pff:
                from fantasy_sim.data.pff.kicker import KickerEngine
                all_seasons = training_seasons + ([target_season] if target_season and target_season not in training_seasons else [])
                self._kicker_engine = KickerEngine(
                    self._pff_config.kicker, self._pff_loader, all_seasons,
                )
                roster_season = target_season or max(training_seasons)
                nfl_roster = self.loader.load_rosters([roster_season])
                self._kicker_engine.build_crosswalk(nfl_roster, roster_season)
            for team_roster, team_dists in [
                (home_roster, home_dists), (away_roster, away_dists),
            ]:
                kicker = next(
                    (p for p in team_roster.players if p.position == "K"), None,
                )
                if kicker is not None:
                    kicker_model = self._kicker_engine.compute(kicker.player_id)
                    if kicker_model is not None:
                        team_dists.kicking = kicker_model

        # Weather adjustments (final layer — game-condition modifier)
        if self._weather_engine is not None and target_season and week:
            weather_ctx = self._weather_engine.get_context(
                home_team, away_team, target_season, week,
            )
            if weather_ctx is not None:
                self._apply_weather(home_dists, home_roster, weather_ctx)
                self._apply_weather(away_dists, away_roster, weather_ctx)

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

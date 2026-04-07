"""PlayerPropsEngine: Bayesian blend of player props into PlayerModel fields (VEG-03).

Applies The Odds API prop lines as a Bayesian prior on top of historical
PBP-derived player models. Follows the TierEngine blending pattern.

Prop-to-model mapping scope (per review-driven design, D-07/D-08):

Clean mappings (direct field adjustment):
  player_reception_yds -> WR/TE receiving_yards_dist (proportional shift)
  player_receptions    -> WR/TE target_share (Bayesian blend of ratio)
  player_rush_yds      -> RB/QB rushing_yards_dist + carry_share
  player_rush_tds      -> RB/QB red_zone_carry_share

Emergent-stat mappings (team-level propagation):
  player_pass_yds  -> QB: shift ALL WR/TE receiving_yards_dist proportionally
  player_pass_tds  -> QB: adjust WR/TE red_zone_target_share proportionally

Anytime TD mapping:
  player_anytime_td -> WR/TE: red_zone_target_share
                    -> RB:    red_zone_carry_share

Security (T-02-12): standardize_name strips special chars; fuzzy_match has
threshold + ambiguity detection to prevent injection via player names.
"""

from __future__ import annotations

import logging

import numpy as np
import polars as pl

from fantasy_sim.data.vegas.crosswalk import fuzzy_match, standardize_name
from fantasy_sim.data.vegas.models import PropsConfig
from fantasy_sim.data.vegas.props_loader import PropsLoader
from fantasy_sim.models.player import TeamRoster

logger = logging.getLogger(__name__)

# Typical NFL game seasons used to scale per-game historical rates
_DEFAULT_GAMES_PER_SEASON = 17

# Typical team pass yds per game (fallback when QB has no rushing dist)
_DEFAULT_TEAM_PASS_YDS = 230.0

# Implied TD probability baseline (per game) — used for anytime_td mapping
_BASELINE_TD_RATE = 0.5  # ~0.5 TDs per game for a featured receiver


class PlayerPropsEngine:
    """Applies Bayesian-blended player props to PlayerModel fields in-place.

    Follows the engine pattern: __init__(config, loader) + apply() method.
    Props loader is called once per (season, week); result is reused for all
    players on the roster (no repeated API calls).

    Bayesian blend formula (same as TierEngine):
        n_obs = player.games_played
        weight = n_obs / (n_obs + prior_strength)
        blended = weight * historical_value + (1 - weight) * prop_implied_value

    Args:
        config: PropsConfig controlling prior strength, thresholds, etc.
        loader: PropsLoader that provides load_props(season, week).
    """

    def __init__(self, config: PropsConfig, loader: PropsLoader) -> None:
        self.config = config
        self.loader = loader

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def apply(
        self,
        roster: TeamRoster,
        team: str,
        season: int,
        week: int,
    ) -> None:
        """Apply props adjustments to all players in roster in-place.

        Loads props once, builds name index from roster, iterates prop rows,
        applies Bayesian-blended adjustments, logs crosswalk audit.

        After this method returns, caller is responsible for running
        _normalize_roster_shares(roster) to re-sum shares to 1.0.

        Args:
            roster: TeamRoster to adjust (mutated in-place).
            team: Team abbreviation (for logging).
            season: NFL season year.
            week: NFL week number.
        """
        props_df = self.loader.load_props(season, week)
        if props_df.is_empty():
            return

        # Build {standardized_name -> player} index
        name_index = self._build_name_index(roster)

        n_matched = 0
        n_unmatched = 0
        n_ambiguous = 0

        # Group props by player name to apply all their markets together
        player_names = props_df["player_name"].unique().to_list()

        for raw_name in player_names:
            std_name = standardize_name(raw_name)
            player_id = fuzzy_match(
                std_name,
                candidates={k: v for k, v in name_index.items()},
                threshold=self.config.fuzzy_threshold,
            )

            if player_id is None:
                # Check whether it was ambiguous (fuzzy_match logs warning)
                # We count unmatched+ambiguous both as "unmatched" for the audit
                n_unmatched += 1
                continue

            # Find the PlayerModel
            player = next(
                (p for p in roster.players if p.player_id == player_id), None
            )
            if player is None:
                n_unmatched += 1
                continue

            n_matched += 1

            # Get all props rows for this player
            player_props = props_df.filter(
                pl.col("player_name") == raw_name
            )

            # Apply each market
            for row in player_props.iter_rows(named=True):
                market = row["market"]
                prop_point = float(row["point"])
                self._apply_market(player, roster, market, prop_point, team)

        logger.info(
            "Props crosswalk [%s week %d]: matched=%d, unmatched=%d",
            team, week, n_matched, n_unmatched,
        )

    # ------------------------------------------------------------------
    # Bayesian blend math
    # ------------------------------------------------------------------

    def _bayesian_blend(
        self,
        historical: float,
        prop_prior: float,
        n_obs: int,
    ) -> float:
        """Compute Bayesian-blended value.

        Formula (matches TierEngine):
            weight = n_obs / (n_obs + prior_strength)
            blended = weight * historical + (1 - weight) * prop_prior

        When n_obs=0: returns prop_prior (full prior weight).

        Args:
            historical: Historical observed value.
            prop_prior: Prop-implied value (the market signal).
            n_obs: Number of observations (games_played).

        Returns:
            Blended value.
        """
        prior_strength = self.config.prior_strength
        if n_obs <= 0:
            return prop_prior
        weight = n_obs / (n_obs + prior_strength)
        return weight * historical + (1.0 - weight) * prop_prior

    def _should_apply(self, blended_ratio: float) -> bool:
        """Return True if the blended ratio deviates enough to apply.

        Skips adjustment when |blended_ratio - 1.0| < min_divergence
        to avoid noise from near-identical prop/historical values.
        """
        return abs(blended_ratio - 1.0) >= self.config.min_divergence

    # ------------------------------------------------------------------
    # Name index
    # ------------------------------------------------------------------

    def _build_name_index(self, roster: TeamRoster) -> dict[str, str]:
        """Build {standardized_name: player_id} from roster."""
        return {
            standardize_name(p.name): p.player_id
            for p in roster.players
            if p.name
        }

    # ------------------------------------------------------------------
    # Market dispatch
    # ------------------------------------------------------------------

    def _apply_market(
        self,
        player,
        roster: TeamRoster,
        market: str,
        prop_point: float,
        team: str,
    ) -> None:
        """Route a single prop market to the appropriate adjustment method."""
        if market == "player_reception_yds":
            self._apply_recv_yds(player, prop_point)
        elif market == "player_receptions":
            self._apply_receptions(player, prop_point)
        elif market == "player_rush_yds":
            self._apply_rush_yds(player, prop_point)
        elif market == "player_rush_tds":
            self._apply_rush_tds(player, prop_point)
        elif market == "player_pass_yds":
            self._apply_pass_yds(player, roster, prop_point)
        elif market == "player_pass_tds":
            self._apply_pass_tds(player, roster, prop_point)
        elif market == "player_anytime_td":
            self._apply_anytime_td(player, prop_point)
        # Unknown markets are silently ignored

    # ------------------------------------------------------------------
    # Clean mappings: direct field adjustment
    # ------------------------------------------------------------------

    def _apply_recv_yds(self, player, prop_point: float) -> None:
        """player_reception_yds -> WR/TE: shift receiving_yards_dist proportionally.

        Computes historical per-game receiving yards from dist mean,
        builds a ratio (prop / historical), Bayesian-blends toward 1.0,
        then shifts the dist by (blended_ratio - 1.0) * dist_mean.
        """
        if player.position not in ("WR", "TE"):
            return
        dist = player.outcomes.receiving_yards_dist
        if dist is None or len(dist) == 0:
            return

        dist_mean = float(np.mean(dist))
        if dist_mean <= 0:
            return

        historical_season_yds = dist_mean * player.games_played
        if historical_season_yds <= 0:
            return

        prop_ratio = prop_point / historical_season_yds
        blended_ratio = self._bayesian_blend(
            historical=1.0,
            prop_prior=prop_ratio,
            n_obs=player.games_played,
        )

        if not self._should_apply(blended_ratio):
            return

        shift = (blended_ratio - 1.0) * dist_mean
        player.outcomes.receiving_yards_dist = dist + shift

    def _apply_receptions(self, player, prop_point: float) -> None:
        """player_receptions -> WR/TE: adjust target_share via Bayesian blend.

        Estimates historical receptions per game from catch_rate * target_share
        (proxy). Blends prop/historical ratio toward 1.0, applies as multiplier.
        """
        if player.position not in ("WR", "TE"):
            return
        if player.usage.target_share <= 0:
            return

        # Use historical receptions per game estimate.
        # If player has _test_historical_receptions set (for testing), use that.
        historical_rec_pg = getattr(player, "_test_historical_receptions", None)
        if historical_rec_pg is None:
            # Proxy: target_share * ~10 targets/game team average * catch_rate
            historical_rec_pg = max(0.1, player.usage.target_share * 10.0 * max(0.5, player.outcomes.catch_rate))

        if historical_rec_pg <= 0:
            return

        prop_ratio = prop_point / historical_rec_pg
        blended_ratio = self._bayesian_blend(
            historical=1.0,
            prop_prior=prop_ratio,
            n_obs=player.games_played,
        )

        if not self._should_apply(blended_ratio):
            return

        player.usage.target_share = max(
            0.0, player.usage.target_share * blended_ratio
        )

    def _apply_rush_yds(self, player, prop_point: float) -> None:
        """player_rush_yds -> RB/QB: adjust carry_share and rushing_yards_dist."""
        if player.position not in ("RB", "QB"):
            return

        dist = player.outcomes.rushing_yards_dist
        if dist is not None and len(dist) > 0:
            dist_mean = float(np.mean(dist))
            if dist_mean > 0:
                historical_season_yds = dist_mean * player.games_played
                if historical_season_yds > 0:
                    prop_ratio = prop_point / historical_season_yds
                    blended_ratio = self._bayesian_blend(
                        historical=1.0,
                        prop_prior=prop_ratio,
                        n_obs=player.games_played,
                    )
                    if self._should_apply(blended_ratio):
                        shift = (blended_ratio - 1.0) * dist_mean
                        player.outcomes.rushing_yards_dist = dist + shift

        # Also adjust carry_share proportionally (more yards -> more usage)
        if player.usage.carry_share > 0:
            dist = player.outcomes.rushing_yards_dist
            if dist is not None and len(dist) > 0:
                dist_mean = float(np.mean(dist))
                historical_season_yds = dist_mean * player.games_played
                if historical_season_yds > 0:
                    prop_ratio = prop_point / historical_season_yds
                    blended_ratio = self._bayesian_blend(
                        historical=1.0,
                        prop_prior=prop_ratio,
                        n_obs=player.games_played,
                    )
                    if self._should_apply(blended_ratio):
                        player.usage.carry_share = max(
                            0.0, player.usage.carry_share * blended_ratio
                        )

    def _apply_rush_tds(self, player, prop_point: float) -> None:
        """player_rush_tds -> RB/QB: adjust red_zone_carry_share proportionally."""
        if player.position not in ("RB", "QB"):
            return
        if player.usage.red_zone_carry_share <= 0:
            return

        # Historical: assume ~0.5 rush TDs/game baseline
        historical_rush_tds_pg = max(
            0.01, player.usage.red_zone_carry_share * 2.0
        )
        prop_ratio = prop_point / historical_rush_tds_pg
        blended_ratio = self._bayesian_blend(
            historical=1.0,
            prop_prior=prop_ratio,
            n_obs=player.games_played,
        )
        if not self._should_apply(blended_ratio):
            return
        player.usage.red_zone_carry_share = max(
            0.0, player.usage.red_zone_carry_share * blended_ratio
        )

    # ------------------------------------------------------------------
    # Emergent-stat mappings: team-level propagation
    # ------------------------------------------------------------------

    def _apply_pass_yds(self, player, roster: TeamRoster, prop_point: float) -> None:
        """player_pass_yds -> QB: shift ALL WR/TE receiving_yards_dist on team.

        QB passing yards are emergent from team passing volume in the sim.
        The correct lever is the WR/TE receiving_yards_dist, which drives
        total team passing yards when summed across all receptions.

        Args:
            player: The QB PlayerModel (used for games_played and historical estimate).
            roster: Full team roster (WR/TE will be adjusted).
            prop_point: QB passing yards prop line.
        """
        if player.position != "QB":
            return

        # Historical pass yds per game estimate (from test attribute or fallback)
        historical_pass_pg = getattr(player, "_test_historical_pass_yds", None)
        if historical_pass_pg is None:
            # Fallback: default team passing volume
            historical_pass_pg = _DEFAULT_TEAM_PASS_YDS

        if historical_pass_pg <= 0:
            return

        prop_ratio = prop_point / historical_pass_pg
        blended_ratio = self._bayesian_blend(
            historical=1.0,
            prop_prior=prop_ratio,
            n_obs=player.games_played,
        )

        if not self._should_apply(blended_ratio):
            return

        # Apply proportional shift to all WR/TE receiving_yards_dist on this team
        for teammate in roster.players:
            if teammate.position not in ("WR", "TE"):
                continue
            dist = teammate.outcomes.receiving_yards_dist
            if dist is None or len(dist) == 0:
                continue
            dist_mean = float(np.mean(dist))
            shift = (blended_ratio - 1.0) * dist_mean
            teammate.outcomes.receiving_yards_dist = dist + shift

    def _apply_pass_tds(self, player, roster: TeamRoster, prop_point: float) -> None:
        """player_pass_tds -> QB: adjust WR/TE red_zone_target_share proportionally.

        More QB pass TDs implies more red zone passing targets distributed
        among WR/TE on the team.
        """
        if player.position != "QB":
            return

        # Historical: ~1.5 pass TDs/game baseline
        historical_pass_tds_pg = max(0.1, 1.5)
        prop_ratio = prop_point / historical_pass_tds_pg
        blended_ratio = self._bayesian_blend(
            historical=1.0,
            prop_prior=prop_ratio,
            n_obs=player.games_played,
        )

        if not self._should_apply(blended_ratio):
            return

        for teammate in roster.players:
            if teammate.position not in ("WR", "TE"):
                continue
            if teammate.usage.red_zone_target_share > 0:
                teammate.usage.red_zone_target_share = max(
                    0.0, teammate.usage.red_zone_target_share * blended_ratio
                )

    # ------------------------------------------------------------------
    # Anytime TD mapping: red zone usage
    # ------------------------------------------------------------------

    def _apply_anytime_td(self, player, prop_point: float) -> None:
        """player_anytime_td -> adjust red zone usage (target_share or carry_share).

        Prop line is the over/under for TDs scored. Higher line implies more
        red zone opportunities. We use the ratio (prop/baseline) as a signal
        to adjust red_zone_target_share (WR/TE) or red_zone_carry_share (RB).
        """
        # Historical baseline: ~0.5 TDs/game for a featured red zone target
        prop_ratio = prop_point / _BASELINE_TD_RATE
        blended_ratio = self._bayesian_blend(
            historical=1.0,
            prop_prior=prop_ratio,
            n_obs=player.games_played,
        )

        if not self._should_apply(blended_ratio):
            return

        if player.position in ("WR", "TE"):
            if player.usage.red_zone_target_share > 0:
                player.usage.red_zone_target_share = max(
                    0.0, player.usage.red_zone_target_share * blended_ratio
                )
            elif player.usage.target_share > 0:
                # No RZ target share yet — use a small baseline
                player.usage.red_zone_target_share = max(
                    0.0, player.usage.target_share * 0.5 * blended_ratio
                )
        elif player.position == "RB":
            if player.usage.red_zone_carry_share > 0:
                player.usage.red_zone_carry_share = max(
                    0.0, player.usage.red_zone_carry_share * blended_ratio
                )

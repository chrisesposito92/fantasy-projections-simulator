"""Talent stabilizer — Bayesian blending of PBP stats with PFF priors.

Adjusts PlayerModel outcome parameters (catch_rate, yards distributions)
using PFF talent signals. Small-sample players get pulled toward their
PFF-implied talent level; large-sample players mostly keep their PBP stats.
"""

from __future__ import annotations

import logging

import polars as pl

from fantasy_sim.data.pff.loader import PffLoader
from fantasy_sim.data.pff.models import PffConfig, TalentConfig
from fantasy_sim.models.player import PlayerModel, TeamRoster

logger = logging.getLogger(__name__)

# Baseline catch rate used as the center for the PFF prior computation.
BASELINE_CATCH_RATE = 0.64

# Minimum shift thresholds — skip adjustments smaller than these.
MIN_RECEIVING_YARDS_SHIFT = 0.3
MIN_RUSHING_YARDS_SHIFT = 0.2

# Catch rate prior is clamped to this range.
CATCH_RATE_PRIOR_MIN = 0.30
CATCH_RATE_PRIOR_MAX = 0.90


def stabilize_value(
    pbp_value: float,
    pff_prior: float,
    n_observations: int,
    prior_strength: float,
    min_divergence: float,
) -> float:
    """Bayesian blend of a PBP-derived stat with a PFF-derived prior.

    If the gap between pbp_value and pff_prior is smaller than
    min_divergence, the PBP value is returned unchanged (no adjustment
    needed — they already agree).

    Otherwise, blends using:
        pbp_weight = n_observations / (n_observations + prior_strength)
        result = pbp_weight * pbp_value + (1 - pbp_weight) * pff_prior

    With 0 observations, returns pff_prior (if divergence exceeds threshold).

    Args:
        pbp_value: Stat value derived from play-by-play data.
        pff_prior: Stat value implied by PFF talent metrics.
        n_observations: Number of PBP observations (e.g., targets, carries).
        prior_strength: How many observations the PFF prior is "worth".
        min_divergence: Minimum abs difference to trigger an adjustment.

    Returns:
        Blended value, or pbp_value if divergence is below threshold.
    """
    if abs(pbp_value - pff_prior) < min_divergence:
        return pbp_value

    pbp_weight = n_observations / (n_observations + prior_strength)
    return pbp_weight * pbp_value + (1.0 - pbp_weight) * pff_prior


class TalentStabilizer:
    """Adjusts PlayerModel parameters using PFF talent signals.

    Mutates roster in-place. Only touches players found in the crosswalk
    (PFF player_id -> nflverse player_id mapping).

    Stabilized parameters:
      - catch_rate (WR, TE, RB with targets)
      - red_zone_catch_rate (scaled proportionally when catch_rate changes)
      - receiving_yards_dist (shift based on YPRR + ADOT)
      - rushing_yards_dist (shift based on YCO/attempt + elusive_rating)

    NOT stabilized: carry_share, target_share, red_zone shares, air_yards_share.
    """

    def __init__(self, config: PffConfig, pff_loader: PffLoader):
        self._config: TalentConfig = config.talent
        self._loader = pff_loader

    def stabilize_roster(
        self,
        roster: TeamRoster,
        crosswalk: dict[int, str],
        training_seasons: list[int],
    ) -> None:
        """Apply PFF talent adjustments to a roster in-place.

        Args:
            roster: TeamRoster to mutate.
            crosswalk: PFF player_id (int) -> nflverse player_id (str).
            training_seasons: Seasons to load PFF data from.
        """
        if not self._config.enabled:
            return

        # Build reverse crosswalk: nflverse_id -> pff_id
        reverse_cw: dict[str, int] = {v: k for k, v in crosswalk.items()}

        # Find which roster players have PFF data
        players_with_pff = [
            p for p in roster.players if p.player_id in reverse_cw
        ]
        if not players_with_pff:
            return

        # Load PFF facets
        receiving = self._loader.aggregate_player_stats(
            "receiving_summary", training_seasons
        )
        rushing = self._loader.aggregate_player_stats(
            "rushing_summary", training_seasons
        )
        passing = self._loader.aggregate_player_stats(
            "passing_summary", training_seasons
        )

        # Build PFF lookup dicts keyed by PFF player_id
        recv_lookup = self._build_lookup(receiving)
        rush_lookup = self._build_lookup(rushing)
        # Compute league averages
        recv_avgs = self._compute_league_averages(
            receiving,
            ["drop_rate", "contested_catch_rate", "yprr", "avg_depth_of_target"],
        )
        rush_avgs = self._compute_league_averages(
            rushing, ["yco_attempt", "elusive_rating"]
        )
        pass_avgs = self._compute_league_averages(
            passing, ["accuracy_percent"]
        )

        # Compute per-team QB accuracy for catch rate prior
        team_qb_accuracy = self._compute_team_qb_accuracy(passing)
        league_avg_accuracy = pass_avgs.get("accuracy_percent", 75.0)

        adjustments = 0
        for player in players_with_pff:
            pff_id = reverse_cw[player.player_id]

            # --- Catch rate stabilization ---
            if (
                player.position in ("WR", "TE", "RB")
                and player.usage.target_share > 0
                and pff_id in recv_lookup
            ):
                adj = self._stabilize_catch_rate(
                    player, recv_lookup[pff_id], recv_avgs,
                    team_qb_accuracy, league_avg_accuracy,
                )
                if adj:
                    adjustments += 1

            # --- Receiving yards stabilization ---
            if (
                player.outcomes.receiving_yards_dist is not None
                and pff_id in recv_lookup
            ):
                adj = self._stabilize_receiving_yards(
                    player, recv_lookup[pff_id], recv_avgs,
                )
                if adj:
                    adjustments += 1

            # --- Rushing yards stabilization ---
            if (
                player.position in ("RB", "QB")
                and player.usage.carry_share > 0
                and pff_id in rush_lookup
            ):
                adj = self._stabilize_rushing_yards(
                    player, rush_lookup[pff_id], rush_avgs,
                )
                if adj:
                    adjustments += 1

        logger.info(
            "TalentStabilizer: %d adjustments applied to %s roster (%d players with PFF)",
            adjustments, roster.team, len(players_with_pff),
        )

    def _resolve_prior_strength(self, position: str) -> float:
        """Resolve prior_strength for a given position.

        Supports both scalar (float) and position-specific (dict) formats.

        Args:
            position: Player position string (e.g. "QB", "WR", "RB", "TE").

        Returns:
            Float prior strength to use for this position.
        """
        ps = self._config.prior_strength
        if isinstance(ps, (int, float)):
            return float(ps)
        return float(ps.get(position, ps.get("default", 40.0)))

    def _build_lookup(self, df: pl.DataFrame) -> dict[int, dict]:
        """Build a dict keyed by PFF player_id from an aggregated DataFrame."""
        if df.is_empty():
            return {}
        lookup: dict[int, dict] = {}
        for row in df.iter_rows(named=True):
            pid = row.get("player_id")
            if pid is not None:
                lookup[int(pid)] = row
        return lookup

    def _compute_league_averages(
        self, df: pl.DataFrame, columns: list[str]
    ) -> dict[str, float]:
        """Compute mean of each column across all players in the DataFrame."""
        avgs: dict[str, float] = {}
        if df.is_empty():
            return avgs
        for col in columns:
            if col in df.columns:
                val = df.select(pl.col(col).mean()).item()
                avgs[col] = float(val) if val is not None else 0.0
            else:
                avgs[col] = 0.0
        return avgs

    def _compute_team_qb_accuracy(self, passing: pl.DataFrame) -> dict[str, float]:
        """Compute weighted QB accuracy per team from passing summary.

        Weights by dropbacks (or games if dropbacks unavailable).
        Returns dict of team -> accuracy_percent.
        """
        if passing.is_empty() or "accuracy_percent" not in passing.columns:
            return {}

        # Filter to QBs only
        if "position" in passing.columns:
            qbs = passing.filter(pl.col("position") == "QB")
        else:
            qbs = passing

        if qbs.is_empty():
            return {}

        # Weight by total dropbacks (dropbacks_per_game * games) if available,
        # else by games. aggregate_player_stats returns per-game means, so
        # multiply dropbacks by games to get total volume for proper weighting.
        if "dropbacks" in qbs.columns and "games" in qbs.columns:
            result = qbs.group_by("team").agg(
                (pl.col("accuracy_percent") * pl.col("dropbacks") * pl.col("games")).sum()
                / (pl.col("dropbacks") * pl.col("games")).sum()
            )
        elif "games" in qbs.columns:
            result = qbs.group_by("team").agg(
                (pl.col("accuracy_percent") * pl.col("games")).sum()
                / pl.col("games").sum()
            )
        else:
            # Unweighted fallback
            result = qbs.group_by("team").agg(
                pl.col("accuracy_percent").mean()
            )

        team_acc: dict[str, float] = {}
        for row in result.iter_rows(named=True):
            val = row.get("accuracy_percent")
            if val is not None:
                team_acc[row["team"]] = float(val)
        return team_acc

    def _stabilize_catch_rate(
        self,
        player: PlayerModel,
        pff_row: dict,
        recv_avgs: dict[str, float],
        team_qb_accuracy: dict[str, float],
        league_avg_accuracy: float,
    ) -> bool:
        """Stabilize catch_rate using PFF receiving signals. Returns True if adjusted."""
        coeffs = self._config.catch_rate_coefficients

        # Extract PFF values (with safe defaults)
        player_drop = pff_row.get("drop_rate", 0.0) or 0.0
        player_contested = pff_row.get("contested_catch_rate", 0.0) or 0.0
        avg_drop = recv_avgs.get("drop_rate", 0.0)
        avg_contested = recv_avgs.get("contested_catch_rate", 0.0)

        # QB accuracy delta for this player's team
        qb_acc = team_qb_accuracy.get(player.team, league_avg_accuracy)
        qb_accuracy_delta = (qb_acc - league_avg_accuracy) * 0.01

        # Compute PFF-implied prior
        # Lower drop rate -> higher catch rate (coefficient is negative, so
        # (avg - player) * |coeff| gives a positive boost for low droppers)
        prior = BASELINE_CATCH_RATE
        prior += coeffs.get("drop_rate", -0.15) * (avg_drop - player_drop) * 0.01
        prior += coeffs.get("contested_catch_rate", 0.10) * (player_contested - avg_contested) * 0.01
        prior += coeffs.get("qb_accuracy", 0.08) * qb_accuracy_delta

        # Clamp prior to valid range
        prior = max(CATCH_RATE_PRIOR_MIN, min(CATCH_RATE_PRIOR_MAX, prior))

        # n_observations = total targets = targets_per_game * games
        # (aggregate_player_stats returns per-game means, so multiply by games)
        games = pff_row.get("games", 0) or 0
        targets = pff_row.get("targets", 0) or 0
        n_obs = int(targets * games) if games > 0 else 0

        old_catch = player.outcomes.catch_rate
        strength = self._resolve_prior_strength(player.position)
        new_catch = stabilize_value(
            old_catch, prior, n_obs,
            strength, self._config.min_divergence,
        )

        if new_catch == old_catch:
            return False

        # Scale red_zone_catch_rate proportionally
        if old_catch > 0 and player.outcomes.red_zone_catch_rate > 0:
            ratio = new_catch / old_catch
            player.outcomes.red_zone_catch_rate *= ratio

        player.outcomes.catch_rate = new_catch

        logger.debug(
            "Catch rate stabilized: %s (%s) %.3f -> %.3f (prior=%.3f, n=%d)",
            player.name, player.player_id, old_catch, new_catch, prior, n_obs,
        )
        return True

    def _stabilize_receiving_yards(
        self,
        player: PlayerModel,
        pff_row: dict,
        recv_avgs: dict[str, float],
    ) -> bool:
        """Stabilize receiving_yards_dist using YPRR and ADOT signals. Returns True if adjusted."""
        coeffs = self._config.receiving_yards_coefficients

        player_yprr = pff_row.get("yprr", 0.0) or 0.0
        player_adot = pff_row.get("avg_depth_of_target", 0.0) or 0.0
        avg_yprr = recv_avgs.get("yprr", 0.0)
        avg_adot = recv_avgs.get("avg_depth_of_target", 0.0)

        # Compute raw shift
        shift = (
            (player_yprr - avg_yprr) * coeffs.get("yprr", 0.5)
            + (player_adot - avg_adot) * coeffs.get("avg_depth_of_target", 0.03)
        )

        # Scale by PFF confidence (more targets = more confident in PFF data,
        # so we trust the shift more).
        # aggregate_player_stats returns per-game means, so multiply by games
        # to get total observations.
        targets_per_game = pff_row.get("targets", 0) or 0
        games = pff_row.get("games", 0) or 0
        n_targets = targets_per_game * games
        strength = self._resolve_prior_strength(player.position)
        pff_confidence = 1.0 - (n_targets / (n_targets + strength))

        # Skip small shifts
        if abs(shift) < MIN_RECEIVING_YARDS_SHIFT:
            return False

        adjusted_shift = shift * (1.0 - pff_confidence)

        if abs(adjusted_shift) < MIN_RECEIVING_YARDS_SHIFT:
            return False

        dist = player.outcomes.receiving_yards_dist
        if dist is None:
            return False

        player.outcomes.receiving_yards_dist = dist + adjusted_shift

        logger.debug(
            "Receiving yards shift: %s (%s) shift=%.2f (raw=%.2f, conf=%.3f)",
            player.name, player.player_id, adjusted_shift, shift, 1.0 - pff_confidence,
        )
        return True

    def _stabilize_rushing_yards(
        self,
        player: PlayerModel,
        pff_row: dict,
        rush_avgs: dict[str, float],
    ) -> bool:
        """Stabilize rushing_yards_dist using YCO and elusive_rating signals. Returns True if adjusted."""
        coeffs = self._config.rushing_yards_coefficients

        player_yco = pff_row.get("yco_attempt", 0.0) or 0.0
        player_elusive = pff_row.get("elusive_rating", 0.0) or 0.0
        avg_yco = rush_avgs.get("yco_attempt", 0.0)
        avg_elusive = rush_avgs.get("elusive_rating", 0.0)

        # Compute raw shift
        shift = (
            (player_yco - avg_yco) * coeffs.get("yco_attempt", 0.6)
            + (player_elusive - avg_elusive) * coeffs.get("elusive_rating", 0.008)
        )

        # Scale by PFF confidence
        # aggregate_player_stats returns per-game means, so multiply by games
        # to get total observations.
        attempts_per_game = pff_row.get("attempts", 0) or 0
        games = pff_row.get("games", 0) or 0
        n_attempts = attempts_per_game * games
        strength = self._resolve_prior_strength(player.position)
        pff_confidence = 1.0 - (n_attempts / (n_attempts + strength))

        # Skip small shifts
        if abs(shift) < MIN_RUSHING_YARDS_SHIFT:
            return False

        adjusted_shift = shift * (1.0 - pff_confidence)

        if abs(adjusted_shift) < MIN_RUSHING_YARDS_SHIFT:
            return False

        dist = player.outcomes.rushing_yards_dist
        if dist is None:
            return False

        player.outcomes.rushing_yards_dist = dist + adjusted_shift

        logger.debug(
            "Rushing yards shift: %s (%s) shift=%.2f (raw=%.2f, conf=%.3f)",
            player.name, player.player_id, adjusted_shift, shift, 1.0 - pff_confidence,
        )
        return True

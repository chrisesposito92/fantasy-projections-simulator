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
BASELINE_CATCH_RATE = 0.70

# Minimum shift thresholds — skip adjustments smaller than these.
MIN_RECEIVING_YARDS_SHIFT = 0.3
MIN_RUSHING_YARDS_SHIFT = 0.2
MIN_TARGET_SHARE_SHIFT = 0.01
MIN_FUMBLE_RATE_SHIFT = 0.002
MIN_SCRAMBLE_RATE_SHIFT = 0.005

# Baseline fumble rate used as the center for the PFF prior computation.
BASELINE_FUMBLE_RATE = 0.015

# Catch rate prior is clamped to this range.
CATCH_RATE_PRIOR_MIN = 0.30
CATCH_RATE_PRIOR_MAX = 0.90


def compute_schedule_adjustment(
    opponent_avg_grade: float,
    league_avg_grade: float,
    weight: float,
    sensitivity: float,
) -> float:
    """Compute schedule difficulty adjustment.

    Positive return = tough schedule -> adjust PBP upward.
    Negative return = easy schedule -> adjust PBP downward.

    Args:
        opponent_avg_grade: Average PFF defensive grade of opponents faced.
        league_avg_grade: League-wide average PFF defensive grade.
        weight: Scaling weight for the adjustment (0 disables it).
        sensitivity: Per-grade-point sensitivity (e.g. 0.005 for catch rate).

    Returns:
        Adjustment value to add to the raw PBP stat before Bayesian blending.
    """
    return weight * (opponent_avg_grade - league_avg_grade) * sensitivity


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
      - target_share (WR, TE — multiplicative prior from route_grade + YPRR)
      - fumble_rate (RB, QB with carries — PFF hands grade)
      - scramble_rate (QB — PFF scramble/dropback ratio as prior)

    NOT stabilized: carry_share, red_zone shares, air_yards_share.
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
        pass_lookup = self._build_lookup(passing)
        # Compute league averages
        recv_avgs = self._compute_league_averages(
            receiving,
            ["drop_rate", "contested_catch_rate", "yprr", "avg_depth_of_target",
             "grades_pass_route"],
        )
        rush_avgs = self._compute_league_averages(
            rushing, ["yco_attempt", "elusive_rating", "grades_hands_fumble"]
        )
        pass_avgs = self._compute_league_averages(
            passing, ["accuracy_percent"]
        )

        # Compute per-team QB accuracy for catch rate prior
        team_qb_accuracy = self._compute_team_qb_accuracy(passing)
        league_avg_accuracy = pass_avgs.get("accuracy_percent", 75.0)

        # Load defensive grades for schedule adjustment
        team_def_grades: dict[str, float] = {}
        league_avg_def_grade = 65.0
        if self._config.schedule_adjustment.enabled:
            team_def_grades = self._load_team_defense_grades(training_seasons)
            if team_def_grades:
                league_avg_def_grade = sum(team_def_grades.values()) / len(team_def_grades)

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
                    team_def_grades, league_avg_def_grade,
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

            # --- Target share stabilization ---
            if (
                player.position in ("WR", "TE")
                and player.usage.target_share > 0
                and pff_id in recv_lookup
                and self._config.target_share_coefficients
            ):
                adj = self._stabilize_target_share(
                    player, recv_lookup[pff_id], recv_avgs,
                )
                if adj:
                    adjustments += 1

            # --- Fumble rate stabilization ---
            if (
                player.position in ("RB", "QB")
                and player.usage.carry_share > 0
                and pff_id in rush_lookup
                and self._config.fumble_rate_coefficients
            ):
                adj = self._stabilize_fumble_rate(
                    player, rush_lookup[pff_id], rush_avgs,
                )
                if adj:
                    adjustments += 1

            # --- Scramble rate stabilization ---
            if (
                player.position == "QB"
                and pff_id in pass_lookup
                and self._config.scramble_rate_enabled
            ):
                adj = self._stabilize_scramble_rate(
                    player, pass_lookup[pff_id],
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

    def _effective_prior_strength(
        self, position: str, current_team: str, pff_team: str,
    ) -> float:
        """Get effective prior_strength, accounting for position and team change.

        If player changed teams, multiply strength by team_change_factor
        (lower strength = more PFF weight for team changers).

        Args:
            position: Player position string (e.g. "QB", "WR", "RB", "TE").
            current_team: Player's current roster team.
            pff_team: Team recorded in PFF training data.

        Returns:
            Effective prior strength to use for Bayesian blending.
        """
        strength = self._resolve_prior_strength(position)
        if current_team != pff_team and self._config.team_change_factor != 1.0:
            strength *= self._config.team_change_factor
        return strength

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

    def _load_team_defense_grades(self, training_seasons: list[int]) -> dict[str, float]:
        """Load PFF defensive coverage grades per team.

        Returns dict of team -> avg defense_coverage grade.
        Uses defense_coverage facet if available, falls back to defense_summary.
        """
        for facet in ("defense_coverage", "defense_summary"):
            df = self._loader.load_facet(facet, training_seasons)
            if df.is_empty():
                continue

            # Look for a coverage grade column
            grade_col = None
            for col_name in ("grades_coverage_defense", "coverage_grade", "grade"):
                if col_name in df.columns:
                    grade_col = col_name
                    break

            if grade_col is None:
                continue

            # Team-level average
            team_grades = df.group_by("team").agg(
                pl.col(grade_col).mean().alias("def_grade")
            )
            result: dict[str, float] = {}
            for row in team_grades.iter_rows(named=True):
                result[row["team"]] = float(row["def_grade"])

            if result:
                return result

        return {}

    def _stabilize_catch_rate(
        self,
        player: PlayerModel,
        pff_row: dict,
        recv_avgs: dict[str, float],
        team_qb_accuracy: dict[str, float],
        league_avg_accuracy: float,
        team_def_grades: dict[str, float] | None = None,
        league_avg_def_grade: float = 65.0,
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

        # Schedule adjustment: players who faced tougher defenses get an upward
        # correction before Bayesian blending.
        schedule_adj = 0.0
        sched_cfg = self._config.schedule_adjustment
        if sched_cfg.enabled and team_def_grades:
            # Approximate opponent grade: average of all other teams
            # (per-game opponent tracking is future work)
            other_grades = [g for t, g in team_def_grades.items() if t != player.team]
            if other_grades:
                opp_avg = sum(other_grades) / len(other_grades)
                schedule_adj = compute_schedule_adjustment(
                    opp_avg,
                    league_avg_def_grade,
                    sched_cfg.weight,
                    sched_cfg.catch_rate_sensitivity,
                )

        adjusted_pbp = old_catch + schedule_adj

        pff_team = pff_row.get("team", player.team)
        strength = self._effective_prior_strength(player.position, player.team, pff_team)
        new_catch = stabilize_value(
            adjusted_pbp, prior, n_obs,
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
            "Catch rate stabilized: %s (%s) %.3f -> %.3f (prior=%.3f, n=%d, sched_adj=%.4f)",
            player.name, player.player_id, old_catch, new_catch, prior, n_obs, schedule_adj,
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
        pff_team = pff_row.get("team", player.team)
        strength = self._effective_prior_strength(player.position, player.team, pff_team)
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
        pff_team = pff_row.get("team", player.team)
        strength = self._effective_prior_strength(player.position, player.team, pff_team)
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

    def _stabilize_target_share(
        self,
        player: PlayerModel,
        pff_row: dict,
        recv_avgs: dict[str, float],
    ) -> bool:
        """Stabilize target_share using route grade and YPRR signals. Returns True if adjusted."""
        coeffs = self._config.target_share_coefficients

        # The PFF column for route grade is "grades_pass_route"
        player_rg = pff_row.get("grades_pass_route", 0.0) or 0.0
        player_yprr = pff_row.get("yprr", 0.0) or 0.0
        avg_rg = recv_avgs.get("grades_pass_route", 0.0)
        avg_yprr = recv_avgs.get("yprr", 0.0)

        # Avoid division by zero
        if avg_rg <= 0 or avg_yprr <= 0:
            return False

        # Compute multiplicative ratio from each signal
        rg_ratio = player_rg / avg_rg
        yprr_ratio = player_yprr / avg_yprr

        # Weighted average of ratios using coefficient weights
        rg_weight = coeffs.get("route_grade", 0.5)
        yprr_weight = coeffs.get("yprr", 0.3)
        total_weight = rg_weight + yprr_weight
        if total_weight <= 0:
            return False

        blended_ratio = (rg_ratio * rg_weight + yprr_ratio * yprr_weight) / total_weight

        # Prior target_share = current * blended_ratio, clamped
        old_ts = player.usage.target_share
        prior_ts = max(0.01, min(0.50, old_ts * blended_ratio))

        # n_observations = targets_per_game * games
        targets_per_game = pff_row.get("targets", 0) or 0
        games = pff_row.get("games", 0) or 0
        n_obs = int(targets_per_game * games) if games > 0 else 0

        pff_team = pff_row.get("team", player.team)
        strength = self._effective_prior_strength(player.position, player.team, pff_team)
        new_ts = stabilize_value(
            old_ts, prior_ts, n_obs,
            strength, self._config.min_divergence,
        )

        if abs(new_ts - old_ts) < MIN_TARGET_SHARE_SHIFT:
            return False

        player.usage.target_share = new_ts

        logger.debug(
            "Target share stabilized: %s (%s) %.3f -> %.3f (prior=%.3f, n=%d)",
            player.name, player.player_id, old_ts, new_ts, prior_ts, n_obs,
        )
        return True

    def _stabilize_fumble_rate(
        self,
        player: PlayerModel,
        pff_row: dict,
        rush_avgs: dict[str, float],
    ) -> bool:
        """Stabilize fumble_rate using PFF hands fumble grade. Returns True if adjusted."""
        coeffs = self._config.fumble_rate_coefficients

        player_hands = pff_row.get("grades_hands_fumble", 0.0) or 0.0
        avg_hands = rush_avgs.get("grades_hands_fumble", 0.0)

        # Compute PFF-implied prior:
        # coeff is negative, so better hands grade (higher) -> lower fumble rate
        coeff = coeffs.get("grades_hands_fumble", -0.002)
        prior = BASELINE_FUMBLE_RATE + coeff * (player_hands - avg_hands)

        # Clamp to valid range
        prior = max(0.001, min(0.05, prior))

        # n_observations = attempts_per_game * games
        attempts_per_game = pff_row.get("attempts", 0) or 0
        games = pff_row.get("games", 0) or 0
        n_obs = int(attempts_per_game * games) if games > 0 else 0

        old_fr = player.outcomes.fumble_rate
        pff_team = pff_row.get("team", player.team)
        strength = self._effective_prior_strength(player.position, player.team, pff_team)
        new_fr = stabilize_value(
            old_fr, prior, n_obs,
            strength, self._config.min_divergence,
        )

        if abs(new_fr - old_fr) < MIN_FUMBLE_RATE_SHIFT:
            return False

        player.outcomes.fumble_rate = new_fr

        logger.debug(
            "Fumble rate stabilized: %s (%s) %.4f -> %.4f (prior=%.4f, n=%d)",
            player.name, player.player_id, old_fr, new_fr, prior, n_obs,
        )
        return True

    def _stabilize_scramble_rate(
        self,
        player: PlayerModel,
        pff_row: dict,
    ) -> bool:
        """Stabilize scramble_rate using PFF scramble/dropback ratio. Returns True if adjusted."""
        scrambles = pff_row.get("scrambles", 0) or 0
        dropbacks = pff_row.get("dropbacks", 0) or 0

        # Skip if insufficient dropback data
        if dropbacks < 10:
            return False

        # PFF rate IS the prior directly
        prior = scrambles / dropbacks

        # n_observations = dropbacks * games (total dropbacks across all games)
        games = pff_row.get("games", 0) or 0
        n_obs = int(dropbacks * games) if games > 0 else 0

        old_sr = player.usage.scramble_rate
        pff_team = pff_row.get("team", player.team)
        strength = self._effective_prior_strength(player.position, player.team, pff_team)
        new_sr = stabilize_value(
            old_sr, prior, n_obs,
            strength, self._config.min_divergence,
        )

        if abs(new_sr - old_sr) < MIN_SCRAMBLE_RATE_SHIFT:
            return False

        player.usage.scramble_rate = new_sr

        logger.debug(
            "Scramble rate stabilized: %s (%s) %.4f -> %.4f (prior=%.4f, n=%d)",
            player.name, player.player_id, old_sr, new_sr, prior, n_obs,
        )
        return True

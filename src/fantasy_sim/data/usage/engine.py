"""UsageEngine: Snap count, CPOE, NGS, and route rate adjustments (USG-01).

Pipeline position: after Vegas, before props (D-03).

Adjustment pipeline:
  1. Snap crosswalk: pfr_player_id -> gsis_id via nflverse rosters
  2. Rolling 4-week snap window (team games, no temporal leakage)
  3. Bayesian snap blend: anchor target_share/carry_share with snap_share
  4. CPOE, NGS, route rate stubs (Plan 02 will implement these)

Threat mitigations:
  T-03-01: Filter to SKILL_POSITIONS before join; log WARNING for unmatched
  T-03-02: NGS data cached via DataLoader._save_cache()
  T-03-04: snap_share clamped to [0.0, 1.0] before blending
  T-03-05: Rolling window strictly filters week < target_week
"""

from __future__ import annotations

import logging

import polars as pl

from fantasy_sim.data.loader import DataLoader
from fantasy_sim.data.usage.models import UsageConfig
from fantasy_sim.models.player import TeamRoster

logger = logging.getLogger(__name__)

# League average snap share used for cold start linear ramp blending.
# Based on NFL starting players typically seeing 50-65% of snaps.
_LEAGUE_AVG_SNAP_SHARE = 0.50


class UsageEngine:
    """Snap count, CPOE, NGS, and route rate adjustments.

    Pipeline position: after Vegas, before props (D-03).

    Applies snap-based usage signals to WR/TE target_share and RB carry_share
    via Bayesian blending with rolling 4-week snap share from nflverse data.

    QB carry_share and scramble_rate are never modified (QB calibration constraint).
    QB snap_share is set to support get_starting_qb() selection.

    Usage:
        engine = UsageEngine(config, loader)
        engine.apply(roster, season=2024, week=5)
        _normalize_roster_shares(roster)  # caller must do this!
    """

    SKILL_POSITIONS = frozenset({"WR", "RB", "TE", "QB", "FB"})

    def __init__(self, config: UsageConfig, loader: DataLoader) -> None:
        self._config = config
        self._loader = loader
        # Caches keyed by season (int)
        self._snap_cache: dict[int, pl.DataFrame] = {}
        self._crosswalk_cache: dict[int, dict[str, str]] = {}  # season -> {pfr_player_id: gsis_id}
        self._ngs_cache: dict[str, pl.DataFrame] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def apply(
        self,
        roster: TeamRoster,
        season: int,
        week: int,
        pff_crosswalk: dict[int, str] | None = None,
    ) -> dict[str, float]:
        """Apply snap-based usage signals in-place. Returns cpoe_map for TierEngine.

        IMPORTANT: Caller MUST call _normalize_roster_shares() after this method.
        This method mutates target_share and carry_share but does NOT re-normalize,
        following the same contract as PlayerPropsEngine.apply().

        Args:
            roster: TeamRoster to adjust (mutated in-place).
            season: NFL season year.
            week: NFL week number (target week; data from week < this value only).
            pff_crosswalk: Optional PFF player ID crosswalk (unused in snap layer;
                present for interface compatibility with downstream CPOE layer).

        Returns:
            dict mapping gsis_id -> cpoe_factor (empty in Plan 01; populated in Plan 02).
        """
        if not self._config.enabled:
            return {}

        crosswalk = self._build_snap_crosswalk(season)
        if not crosswalk:
            logger.debug("UsageEngine: empty crosswalk for season %d, skipping", season)
            return {}

        for player in roster.players:
            gsis_id = player.player_id
            pfr_id = _reverse_lookup(crosswalk, gsis_id)

            if pfr_id is None:
                logger.debug(
                    "UsageEngine: no crosswalk match for player %s (%s), skipping",
                    player.name,
                    gsis_id,
                )
                continue

            snap_share = self._get_rolling_snap(gsis_id, season, week)

            # Always set snap_share field (supports get_starting_qb() for QBs)
            if snap_share is not None:
                player.usage.snap_share = max(0.0, min(1.0, snap_share))  # T-03-04: clamp

            if player.position == "QB":
                # QB ONLY: set snap_share. Never touch carry_share or scramble_rate.
                # (QB calibration constraint from Pitfall 3 / CLAUDE.md)
                continue

            if snap_share is None:
                # No historical snap data -- skip blending, leave shares unchanged
                continue

            snap_share_clamped = max(0.0, min(1.0, snap_share))  # T-03-04
            n_games = player.games_played
            prior_strength = self._config.snap.prior_strength

            if player.position in ("WR", "TE"):
                player.usage.target_share = _bayesian_blend(
                    observed=player.usage.target_share,
                    prior=snap_share_clamped,
                    n_obs=n_games,
                    prior_strength=prior_strength,
                )

            elif player.position in ("RB", "FB"):
                player.usage.carry_share = _bayesian_blend(
                    observed=player.usage.carry_share,
                    prior=snap_share_clamped,
                    n_obs=n_games,
                    prior_strength=prior_strength,
                )
                player.usage.target_share = _bayesian_blend(
                    observed=player.usage.target_share,
                    prior=snap_share_clamped,
                    n_obs=n_games,
                    prior_strength=prior_strength,
                )

        # Compute CPOE rolling map for downstream TierEngine consumption (USG-02)
        cpoe_map: dict[str, float] = {}
        if self._config.cpoe.enabled:
            try:
                cpoe_map = self._compute_cpoe_rolling(season, week)
            except Exception as exc:
                logger.warning("UsageEngine: CPOE computation failed (%s), using empty map", exc)

        return cpoe_map

    # ------------------------------------------------------------------
    # Snap crosswalk: pfr_player_id -> gsis_id
    # ------------------------------------------------------------------

    def _build_snap_crosswalk(self, season: int) -> dict[str, str]:
        """Build {pfr_player_id: gsis_id} crosswalk for a given season.

        Joins snap_counts.pfr_player_id against rosters.pfr_id to get gsis_id.
        Filters to SKILL_POSITIONS only. Logs WARNING for unmatched skill players.
        Result cached per season.

        Mitigation T-03-01: logs WARNING with unmatched player list.
        """
        if season in self._crosswalk_cache:
            return self._crosswalk_cache[season]

        snap_df = self._get_snap_df(season)
        roster_df = self._loader.load_rosters([season])

        # Normalize roster column: DataLoader renames gsis_id -> player_id
        if "player_id" in roster_df.columns and "gsis_id" not in roster_df.columns:
            roster_df = roster_df.rename({"player_id": "gsis_id"})

        # Filter snap data to skill positions
        skill_snap_df = snap_df.filter(pl.col("position").is_in(list(self.SKILL_POSITIONS)))

        if skill_snap_df.is_empty():
            logger.warning("UsageEngine: no skill-position snap data for season %d", season)
            self._crosswalk_cache[season] = {}
            return {}

        # Build pfr_id -> gsis_id map from rosters (unique per pfr_id)
        roster_map_df = (
            roster_df
            .filter(pl.col("pfr_id").is_not_null())
            .select(["pfr_id", "gsis_id"])
            .unique(subset=["pfr_id"], keep="first")
        )

        # Join snap pfr_player_id against roster pfr_id
        joined = skill_snap_df.join(
            roster_map_df,
            left_on="pfr_player_id",
            right_on="pfr_id",
            how="left",
        )

        # Build crosswalk from matched rows
        matched = joined.filter(pl.col("gsis_id").is_not_null())
        crosswalk: dict[str, str] = {}
        for row in matched.unique(subset=["pfr_player_id"]).iter_rows(named=True):
            crosswalk[row["pfr_player_id"]] = row["gsis_id"]

        # Log WARNING for unmatched skill players (T-03-01)
        unmatched = joined.filter(pl.col("gsis_id").is_null())
        total_skill = len(skill_snap_df.unique(subset=["pfr_player_id"]))
        unmatched_count = len(unmatched.unique(subset=["pfr_player_id"]))
        if unmatched_count > 0:
            pct = unmatched_count / max(1, total_skill) * 100
            unmatched_names = (
                unmatched
                .unique(subset=["pfr_player_id"])
                .select("pfr_player_id")
                .to_series()
                .to_list()
            )
            logger.warning(
                "Snap crosswalk: %d/%d skill players unmatched (%.1f%%). "
                "Unmatched: %s",
                unmatched_count,
                total_skill,
                pct,
                unmatched_names[:10],
            )

        self._crosswalk_cache[season] = crosswalk
        return crosswalk

    # ------------------------------------------------------------------
    # Rolling 4-week snap window (leak-free, team-game-based)
    # ------------------------------------------------------------------

    def _get_rolling_snap(
        self,
        gsis_id: str,
        season: int,
        week: int,
    ) -> float | None:
        """Compute rolling snap share for a player over last 4 team games before target week.

        Window:
          - Strictly excludes current week (week < target_week, T-03-05)
          - Uses last 4 completed team games (not calendar weeks -- bye week safe)
          - REG season games only

        Cold start (< min_games available):
          - Returns blended value: blend_weight * observed_mean + (1 - blend_weight) * league_avg
          - blend_weight = games_in_window / min_games

        Returns:
          Mean offense_pct over window, or None if no data at all.
        """
        snap_df = self._get_snap_df(season)
        if snap_df.is_empty():
            return None

        # Reverse crosswalk to find pfr_player_id for this gsis_id
        crosswalk = self._build_snap_crosswalk(season)
        pfr_id = _reverse_lookup(crosswalk, gsis_id)
        if pfr_id is None:
            return None

        # Filter: player's REG games STRICTLY before target week (T-03-05 temporal leakage)
        player_games = (
            snap_df
            .filter(
                (pl.col("pfr_player_id") == pfr_id)
                & (pl.col("season") == season)
                & (pl.col("week") < week)          # STRICT less-than: no current-week leakage
                & (pl.col("game_type") == "REG")
            )
            .sort("week", descending=True)
            .head(self._config.snap.min_games)     # last 4 TEAM GAMES, not calendar weeks
        )

        games_in_window = len(player_games)

        if games_in_window == 0:
            return None

        observed_mean = player_games.select(pl.col("offense_pct").mean()).item()

        if games_in_window >= self._config.snap.min_games:
            return float(observed_mean)

        # Cold start: linear ramp blend toward league average
        # blend_weight = games / min_games (e.g. 1 game -> 25% observed, 75% league avg)
        blend_weight = games_in_window / self._config.snap.min_games
        blended = blend_weight * observed_mean + (1.0 - blend_weight) * _LEAGUE_AVG_SNAP_SHARE
        return float(blended)

    # ------------------------------------------------------------------
    # CPOE rolling computation (USG-02)
    # ------------------------------------------------------------------

    def _compute_cpoe_rolling(
        self,
        season: int,
        week: int,
    ) -> dict[str, float]:
        """Compute rolling 4-week CPOE per QB with strict temporal leak guard.

        Filters PBP to (season, week strictly < target_week) to prevent
        temporal leakage (T-03-10). Groups by passer_player_id, aggregates
        mean CPOE, filters to >= min_plays threshold.

        Args:
            season: NFL season year.
            week: Target week (current game week). Only uses data from prior weeks.

        Returns:
            Dict mapping gsis_id (passer_player_id) -> rolling mean CPOE.
            Empty dict when no data available or week <= 1.
        """
        if week <= 1:
            return {}

        pbp = self._loader.load_pbp([season])
        if pbp is None or pbp.is_empty():
            return {}

        min_week = max(1, week - self._config.snap.min_games)

        try:
            pass_plays = pbp.filter(
                (pl.col("season") == season)
                & (pl.col("week") >= min_week)
                & (pl.col("week") < week)        # STRICT: never includes current week (T-03-10)
                & pl.col("cpoe").is_not_null()
                & pl.col("passer_player_id").is_not_null()
            )
        except Exception:
            return {}

        if pass_plays.is_empty():
            return {}

        grouped = (
            pass_plays
            .group_by("passer_player_id")
            .agg([
                pl.col("cpoe").mean().alias("rolling_cpoe"),
                pl.len().alias("n_plays"),
            ])
            .filter(pl.col("n_plays") >= self._config.cpoe.min_plays)
        )

        result: dict[str, float] = {}
        for row in grouped.iter_rows(named=True):
            result[row["passer_player_id"]] = float(row["rolling_cpoe"])
        return result

    # ------------------------------------------------------------------
    # NGS separation/cushion stubs (Plan 02 Task 2 implements these)
    # ------------------------------------------------------------------

    def _apply_ngs(
        self,
        player,
        ngs_df: "pl.DataFrame",
    ) -> None:
        """Stub: apply NGS separation/cushion factors to WR. Implemented in Task 2."""

    def _apply_route_rate(
        self,
        player,
        pff_df: "pl.DataFrame",
    ) -> None:
        """Stub: apply PFF route rate factor to WR target_share. Implemented in Task 2."""

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_snap_df(self, season: int) -> pl.DataFrame:
        """Load and cache snap counts DataFrame for the given season."""
        if season not in self._snap_cache:
            self._snap_cache[season] = self._loader.load_snap_counts([season])
        return self._snap_cache[season]


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------


def _bayesian_blend(
    observed: float,
    prior: float,
    n_obs: int,
    prior_strength: float,
) -> float:
    """Bayesian blend of observed value toward prior.

    Formula: adjusted = (n_obs * observed + prior_strength * prior)
                        / (n_obs + prior_strength)

    Equivalent to: weight = n_obs / (n_obs + prior_strength)
                   adjusted = weight * observed + (1 - weight) * prior

    When n_obs=0: returns pure prior.
    Result is non-negative (clamped to 0.0).
    """
    if n_obs <= 0:
        return max(0.0, prior)
    return max(0.0, (n_obs * observed + prior_strength * prior) / (n_obs + prior_strength))


def _reverse_lookup(crosswalk: dict[str, str], gsis_id: str) -> str | None:
    """Find pfr_player_id for a given gsis_id in the crosswalk.

    Crosswalk maps pfr_player_id -> gsis_id; this reverses the lookup.
    Linear scan is acceptable since crosswalk is small (<500 entries per season).
    """
    for pfr_id, gid in crosswalk.items():
        if gid == gsis_id:
            return pfr_id
    return None

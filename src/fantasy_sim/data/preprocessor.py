import polars as pl
import numpy as np
from fantasy_sim.config.loader import get_phase1_ks_flags, get_phase2_ks_flags
from fantasy_sim.models.game_state import GameStateBucket, bucket_play
from fantasy_sim.models.distributions import (
    PlayCallingDist, PlayOutcomeDist, TurnoverRates, KickingModel, DriveStartModel,
    PenaltyRates,
)

# Legacy bucket-size threshold. KS-14 (Phase 2 D-11) lowers the EFFECTIVE threshold
# to 5 when `phase2_ks_flags.ks14_thin_bucket_shrinkage.enabled=true` via the
# `_effective_min_bucket_plays()` helper below. The MIN_BUCKET_PLAYS constant
# itself stays at 10 so that flag-off behavior is byte-identical to pre-KS-14.
# Codex review HIGH 2 (2026-04-27): we MUST NOT lower the constant globally; the
# threshold change MUST flip with the flag.
MIN_BUCKET_PLAYS = 10

# Phase 1 KS-06 feature flag (Cycle 3 D-45). When enabled, the team-bucket
# pass-yards distribution computed by ``compute_play_outcomes`` is filtered to
# completed plays only — incompletions (yards_gained=0) drag the team bucket
# mean down and bias the play_resolver backup-receiver fallback path low for
# receivers without their own per-player distribution. Read once at module
# import time; A/B arms are separate Python processes via fresh
# GameContextBuilder construction so this matches the rest of the Phase 1 KS
# flag-gated code paths.
_KS06_BACKUP_RECEIVER_FIX = (
    get_phase1_ks_flags()
    .get("ks06_backup_receiver_fix", {})
    .get("enabled", False)
)

# Phase 2 KS-14 feature flag (D-11 / D-45 pattern, codex HIGH 2 fix). When the
# flag is true, the EFFECTIVE bucket-size threshold drops from 10 to 5 AND
# n∈[5,9] buckets get Bayesian shrinkage toward team default. When the flag is
# false, the legacy threshold of 10 applies AND the shrinkage branch is
# unreachable. Read once at module import time.
_KS14_THIN_BUCKET_SHRINKAGE = (
    get_phase2_ks_flags()
    .get("ks14_thin_bucket_shrinkage", {})
    .get("enabled", False)
)


def _effective_min_bucket_plays() -> int:
    """Return the active bucket-size threshold based on the KS-14 flag.

    Codex review HIGH 2 (2026-04-27): the threshold change MUST be flag-gated.
    When `_KS14_THIN_BUCKET_SHRINKAGE` is False (default, legacy), returns 10
    (matches pre-KS-14 behavior byte-identically). When True (KS-14 SHIPPED),
    returns 5 — and `compute_play_outcomes` additionally routes n∈[5,9]
    buckets through `_apply_bayesian_shrinkage`.
    """
    return 5 if _KS14_THIN_BUCKET_SHRINKAGE else MIN_BUCKET_PLAYS  # 10 by default


def _apply_bayesian_shrinkage(
    personal: list | np.ndarray,
    team_default: np.ndarray | list | None,
) -> np.ndarray:
    """Apply Bayesian shrinkage to a thin per-bucket yards array.

    KS-14 D-11 + Pattern 5 (project-wide Bayesian formula):
        adjusted_mean = (n * observed_mean + prior_strength * prior_mean) / (n + prior_strength)

    Where n = len(personal); observed_mean = np.mean(personal); prior_strength =
    5 * len(team_default); prior_mean = np.mean(team_default). The output array
    is constructed as `personal - observed_mean + adjusted_mean` so the SHAPE of
    the personal distribution is preserved (variance, skew) but the LOCATION is
    pulled toward the team default proportional to data thinness.

    When team_default is None or empty, falls back to returning personal unchanged
    (graceful degradation; matches the legacy fallback for buckets with no team data).
    """
    personal_arr = (
        np.array(personal, dtype=np.float64)
        if not isinstance(personal, np.ndarray)
        else personal.astype(np.float64)
    )
    if team_default is None or (hasattr(team_default, "__len__") and len(team_default) == 0):
        return personal_arr
    team_arr = (
        np.array(team_default, dtype=np.float64)
        if not isinstance(team_default, np.ndarray)
        else team_default.astype(np.float64)
    )
    n = len(personal_arr)
    if n == 0:
        return personal_arr
    observed_mean = float(np.mean(personal_arr))
    prior_mean = float(np.mean(team_arr))
    prior_strength = 5.0 * len(team_arr)
    if (n + prior_strength) <= 0:
        return personal_arr
    adjusted_mean = (n * observed_mean + prior_strength * prior_mean) / (n + prior_strength)
    return personal_arr - observed_mean + adjusted_mean

# League-average fallback constants for penalty rates
_LEAGUE_AVG_PENALTY_RATE = 0.07
_LEAGUE_AVG_TYPE_DIST = {
    "false_start": 0.30,
    "holding": 0.40,
    "pass_interference": 0.15,
    "other": 0.15,
}
_LEAGUE_AVG_YARDS = {
    "false_start": 5.0,
    "holding": 10.0,
    "pass_interference": 15.0,
    "other": 5.0,
}


class Preprocessor:
    """Computes probability distributions from raw PBP data."""

    def _filter_real_plays(self, pbp: pl.DataFrame) -> pl.DataFrame:
        return pbp.filter(pl.col("play_type").is_in(["pass", "run"]))

    def _apply_season_weights(
        self,
        plays: pl.DataFrame,
        season_weights: dict[int, float] | None,
    ) -> pl.DataFrame:
        """Replicate rows proportional to season_weights for weighted sampling.

        Normalises so the maximum weight yields 10 replications; all others are
        proportional (minimum 1 replication).  If season_weights is None or
        empty the original DataFrame is returned unchanged.
        """
        if not season_weights:
            return plays

        max_weight = max(season_weights.values())
        if max_weight == 0:
            return plays

        frames: list[pl.DataFrame] = []
        seasons_present = plays["season"].unique().to_list()

        for season in seasons_present:
            season_plays = plays.filter(pl.col("season") == season)
            if season_plays.is_empty():
                continue
            raw_weight = season_weights.get(int(season), 0.0)
            reps = max(1, round((raw_weight / max_weight) * 10))
            frames.extend([season_plays] * reps)

        if not frames:
            return plays

        return pl.concat(frames)

    def compute_play_calling(
        self,
        pbp: pl.DataFrame,
        season_weights: dict[int, float] | None = None,
    ) -> dict[str, PlayCallingDist]:
        """Compute P(run|state) and P(pass|state) per team."""
        plays = self._filter_real_plays(pbp)
        plays = self._apply_season_weights(plays, season_weights)
        teams = plays["posteam"].unique().to_list()
        result = {}

        for team in teams:
            team_plays = plays.filter(pl.col("posteam") == team)
            total = team_plays.shape[0]
            if total == 0:
                continue

            pass_count = team_plays.filter(pl.col("play_type") == "pass").shape[0]
            run_count = total - pass_count
            default = {"pass": pass_count / total, "run": run_count / total}

            bucket_counts: dict[GameStateBucket, dict[str, int]] = {}
            for row in team_plays.iter_rows(named=True):
                bucket = bucket_play(
                    row["down"], row["ydstogo"], row["score_differential"], row["qtr"], row["yardline_100"],
                )
                if bucket not in bucket_counts:
                    bucket_counts[bucket] = {"pass": 0, "run": 0}
                bucket_counts[bucket][row["play_type"]] += 1

            distributions: dict[GameStateBucket, dict[str, float]] = {}
            _threshold = _effective_min_bucket_plays()
            for bucket, counts in bucket_counts.items():
                total_bucket = counts["pass"] + counts["run"]
                if total_bucket >= _threshold:
                    distributions[bucket] = {
                        "pass": counts["pass"] / total_bucket,
                        "run": counts["run"] / total_bucket,
                    }

            result[team] = PlayCallingDist(team=team, distributions=distributions, default=default)

        return result

    def compute_play_outcomes(
        self,
        pbp: pl.DataFrame,
        season_weights: dict[int, float] | None = None,
    ) -> PlayOutcomeDist:
        """Compute empirical yards-gained distributions by play type and game state.

        KS-06 D-19 sub-fix 1 (Cycle 3 D-45 flag-gated): when
        ``phase1_ks_flags.ks06_backup_receiver_fix.enabled`` is true, pass plays
        with ``complete_pass != 1`` are dropped before yards are appended to the
        per-bucket and default distributions. This makes the team-bucket
        ``pass`` distribution a "yards per completion" distribution rather than
        a "yards per attempt" distribution, which matches the way the
        play_resolver backup-receiver fallback samples it (only after the catch
        succeeds via ``effective_catch_rate`` — including incompletions
        double-counts the miss). Run plays are unaffected.
        """
        plays = self._filter_real_plays(pbp)
        plays = self._apply_season_weights(plays, season_weights)

        bucket_yards: dict[tuple[str, GameStateBucket], list[int]] = {}
        defaults: dict[str, list[int]] = {"pass": [], "run": []}

        # KS-06 D-19 sub-fix 1: tolerate fixtures missing complete_pass column
        # by treating the filter as a no-op when the column isn't present
        # (older test fixtures predate this column). Production PBP from
        # nflverse always carries it.
        has_complete_pass = "complete_pass" in plays.columns
        for row in plays.iter_rows(named=True):
            play_type = row["play_type"]
            yards = row["yards_gained"]

            # Skip incomplete passes when the KS-06 flag is on so the team
            # ``pass`` distribution is completion-only. ``run`` plays are
            # unaffected. We still want to count the play in the bucket-size
            # check (>= MIN_BUCKET_PLAYS) only for the rows that actually
            # contribute, so the filter happens before the append.
            if (
                _KS06_BACKUP_RECEIVER_FIX
                and play_type == "pass"
                and has_complete_pass
                and row.get("complete_pass") != 1
            ):
                continue

            defaults[play_type].append(yards)

            bucket = bucket_play(
                row["down"], row["ydstogo"], row["score_differential"], row["qtr"], row["yardline_100"],
            )
            key = (play_type, bucket)
            if key not in bucket_yards:
                bucket_yards[key] = []
            bucket_yards[key].append(yards)

        # Build final_defaults BEFORE the bucket loop so the shrinkage helper
        # can reference team defaults when the KS-14 flag is on.
        final_defaults = {k: np.array(v) for k, v in defaults.items() if v}

        distributions = {}
        for key, yards_list in bucket_yards.items():
            n_personal = len(yards_list)
            # Codex HIGH 2 fix: when the KS-14 flag is OFF, _effective_min_bucket_plays()
            # returns 10 (legacy) so the n∈[5,9] subrange is dropped exactly as pre-KS-14.
            # When the flag is ON, the threshold drops to 5 AND n∈[5,9] gets shrinkage.
            if n_personal >= 10:
                # Robust bucket — no shrinkage needed (always retained, both modes)
                distributions[key] = np.array(yards_list)
            elif _KS14_THIN_BUCKET_SHRINKAGE and n_personal >= 5:
                # KS-14 D-11: thin bucket — apply Bayesian shrinkage toward team default
                play_type, _bucket = key
                team_default = final_defaults.get(play_type)
                distributions[key] = _apply_bayesian_shrinkage(yards_list, team_default)
            # else: drop the bucket. With flag OFF, this drops everything < 10 (legacy).
            # With flag ON, the shrinkage branch above caught n∈[5,9]; this drops n<5.

        return PlayOutcomeDist(distributions=distributions, defaults=final_defaults)

    def compute_turnover_rates(
        self,
        pbp: pl.DataFrame,
        season_weights: dict[int, float] | None = None,
    ) -> dict[str, TurnoverRates]:
        """Compute per-team turnover and sack rates from PBP data."""
        plays = self._filter_real_plays(pbp)
        plays = self._apply_season_weights(plays, season_weights)
        teams = plays["posteam"].unique().to_list()
        result = {}

        for team in teams:
            team_plays = plays.filter(pl.col("posteam") == team)
            total_plays = team_plays.shape[0]
            pass_plays = team_plays.filter(pl.col("play_type") == "pass")
            total_passes = pass_plays.shape[0]

            if total_plays == 0:
                continue

            ints = team_plays.filter(pl.col("interception") == 1).shape[0]
            fumbles = team_plays.filter(pl.col("fumble_lost") == 1).shape[0]
            sacks = team_plays.filter(pl.col("sack") == 1).shape[0]

            int_rate = ints / total_passes if total_passes > 0 else 0.0
            fumble_rate = fumbles / total_plays
            sack_rate = sacks / total_passes if total_passes > 0 else 0.0

            sack_plays = team_plays.filter(pl.col("sack") == 1)
            if sack_plays.shape[0] > 0:
                sack_fumbles = sack_plays.filter(pl.col("fumble_lost") == 1).shape[0]
                sack_fumble_rate = sack_fumbles / sack_plays.shape[0]
            else:
                sack_fumble_rate = 0.10  # League average fallback

            result[team] = TurnoverRates(
                team=team, int_rate=int_rate, fumble_rate=fumble_rate,
                sack_rate=sack_rate, sack_fumble_rate=sack_fumble_rate,
            )

        return result

    def compute_penalty_rates(self, pbp: pl.DataFrame) -> dict[str, PenaltyRates]:
        """Compute per-team penalty rates from PBP data.

        For each team:
        - penalty_rate = penalties / total_real_plays
        - type_distribution derived from penalty_yards buckets:
            <=5 -> false_start, 6-10 -> holding, >10 -> pass_interference
        - avg_yards constants: false_start=5, holding=10, pass_interference=15, other=5
        - If penalty_rate == 0, use league-average fallback.
        """
        plays = self._filter_real_plays(pbp)
        teams = plays["posteam"].unique().to_list()
        result: dict[str, PenaltyRates] = {}

        for team in teams:
            team_plays = plays.filter(pl.col("posteam") == team)
            total_plays = team_plays.shape[0]
            if total_plays == 0:
                continue

            penalty_plays = team_plays.filter(pl.col("penalty") == 1)
            n_penalties = penalty_plays.shape[0]
            penalty_rate = n_penalties / total_plays

            avg_yards = dict(_LEAGUE_AVG_YARDS)

            if penalty_rate == 0 or n_penalties == 0:
                # Use league-average fallback
                penalty_rate = _LEAGUE_AVG_PENALTY_RATE
                type_distribution = dict(_LEAGUE_AVG_TYPE_DIST)
            else:
                # Derive type distribution from penalty_yards
                counts: dict[str, int] = {
                    "false_start": 0,
                    "holding": 0,
                    "pass_interference": 0,
                    "other": 0,
                }
                for row in penalty_plays.iter_rows(named=True):
                    yards = row["penalty_yards"]
                    if yards <= 5:
                        counts["false_start"] += 1
                    elif yards <= 10:
                        counts["holding"] += 1
                    else:
                        counts["pass_interference"] += 1

                total_typed = sum(counts.values())
                if total_typed > 0:
                    type_distribution = {k: v / total_typed for k, v in counts.items()}
                else:
                    type_distribution = dict(_LEAGUE_AVG_TYPE_DIST)

            result[team] = PenaltyRates(
                team=team,
                penalty_rate=penalty_rate,
                type_distribution=type_distribution,
                avg_yards=avg_yards,
            )

        return result

    def compute_kicking_model(self, pbp: pl.DataFrame, xp_data: pl.DataFrame | None = None) -> KickingModel:
        """Compute FG make rates by distance bucket and XP rate."""
        fg_plays = pbp.filter(pl.col("play_type") == "field_goal")

        buckets = {
            "0_39": {"made": 0, "total": 0},
            "40_49": {"made": 0, "total": 0},
            "50_plus": {"made": 0, "total": 0},
        }

        for row in fg_plays.iter_rows(named=True):
            dist = row["kick_distance"]
            if dist < 40:
                bucket = "0_39"
            elif dist < 50:
                bucket = "40_49"
            else:
                bucket = "50_plus"
            buckets[bucket]["total"] += 1
            if row["field_goal_result"] == "made":
                buckets[bucket]["made"] += 1

        league_avg = {"0_39": 0.95, "40_49": 0.82, "50_plus": 0.65}
        fg_make_rate = {}
        for bucket, counts in buckets.items():
            if counts["total"] == 0:
                fg_make_rate[bucket] = league_avg[bucket]
            else:
                fg_make_rate[bucket] = counts["made"] / counts["total"]

        if xp_data is not None and xp_data.shape[0] > 0:
            xp_plays = xp_data.filter(pl.col("play_type") == "extra_point")
            if xp_plays.shape[0] > 0:
                xp_made = xp_plays.filter(pl.col("extra_point_result") == "good").shape[0]
                xp_rate = xp_made / xp_plays.shape[0]
            else:
                xp_rate = 0.94
        else:
            xp_rate = 0.94

        return KickingModel(fg_make_rate=fg_make_rate, xp_rate=xp_rate)

    def compute_drive_start_model(self, pbp: pl.DataFrame) -> DriveStartModel:
        """Compute kickoff return / touchback distributions."""
        kickoffs = pbp.filter(pl.col("play_type") == "kickoff")

        if kickoffs.shape[0] == 0:
            return DriveStartModel(
                touchback_rate=0.55, touchback_yardline=75,
                return_yardlines=np.array([72, 74, 76, 78, 80]),
            )

        touchbacks = kickoffs.filter(pl.col("touchback") == 1)
        returns = kickoffs.filter(pl.col("touchback") == 0)

        touchback_rate = touchbacks.shape[0] / kickoffs.shape[0]

        if touchbacks.shape[0] > 0:
            touchback_yardline = int(touchbacks["yardline_100"].mean())
        else:
            touchback_yardline = 75

        if returns.shape[0] > 0:
            return_yardlines = returns["yardline_100"].to_numpy()
        else:
            return_yardlines = np.array([72, 74, 76, 78, 80])

        return DriveStartModel(
            touchback_rate=touchback_rate, touchback_yardline=touchback_yardline,
            return_yardlines=return_yardlines,
        )

import polars as pl
import numpy as np
from fantasy_sim.models.game_state import GameStateBucket, bucket_play
from fantasy_sim.models.distributions import (
    PlayCallingDist, PlayOutcomeDist, TurnoverRates, KickingModel, DriveStartModel,
    PenaltyRates,
)

MIN_BUCKET_PLAYS = 10

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
            raw_weight = season_weights.get(int(season), 1.0)
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
            for bucket, counts in bucket_counts.items():
                total_bucket = counts["pass"] + counts["run"]
                if total_bucket >= MIN_BUCKET_PLAYS:
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
        """Compute empirical yards-gained distributions by play type and game state."""
        plays = self._filter_real_plays(pbp)
        plays = self._apply_season_weights(plays, season_weights)

        bucket_yards: dict[tuple[str, GameStateBucket], list[int]] = {}
        defaults: dict[str, list[int]] = {"pass": [], "run": []}

        for row in plays.iter_rows(named=True):
            play_type = row["play_type"]
            yards = row["yards_gained"]
            defaults[play_type].append(yards)

            bucket = bucket_play(
                row["down"], row["ydstogo"], row["score_differential"], row["qtr"], row["yardline_100"],
            )
            key = (play_type, bucket)
            if key not in bucket_yards:
                bucket_yards[key] = []
            bucket_yards[key].append(yards)

        distributions = {}
        for key, yards_list in bucket_yards.items():
            if len(yards_list) >= MIN_BUCKET_PLAYS:
                distributions[key] = np.array(yards_list)

        final_defaults = {k: np.array(v) for k, v in defaults.items() if v}

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

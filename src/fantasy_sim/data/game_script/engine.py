"""Empirical learning engine for game-script profiles."""

from __future__ import annotations

from collections import Counter, defaultdict

import polars as pl

from fantasy_sim.data.game_script.models import (
    GameScriptConfig,
    GameScriptDiagnostics,
    GameScriptProfile,
    RbRankFactors,
    TargetRankFactors,
)

_RANK_BUCKETS = ("rank1", "rank2", "rank3_plus")
_RB_BUCKETS = ("rb1", "rb2", "rb3_plus")


class GameScriptEngine:
    """Learns team-level game-script profiles from historical play-by-play."""

    def __init__(self, config: GameScriptConfig):
        self.config = config
        self._profile_cache: dict[tuple[str, tuple[int, ...], int | None, int | None], GameScriptProfile] = {}

    def compute(
        self,
        team: str,
        pbp: pl.DataFrame,
        training_seasons: list[int],
        target_season: int | None = None,
        week: int | None = None,
        rosters: pl.DataFrame | None = None,
    ) -> GameScriptProfile:
        cache_key = (team, tuple(training_seasons), target_season, week)
        if cache_key in self._profile_cache:
            return self._profile_cache[cache_key]

        seasons = list(training_seasons)
        if target_season is not None and target_season not in seasons:
            seasons.append(target_season)

        window = pbp.filter(pl.col("season").is_in(seasons))
        if target_season is not None and week is not None:
            window = window.filter(
                (pl.col("season") < target_season)
                | ((pl.col("season") == target_season) & (pl.col("week") < week))
            )

        offense = window.filter(pl.col("posteam") == team)
        if offense.is_empty():
            profile = GameScriptProfile(
                team=team,
                diagnostics=GameScriptDiagnostics(),
            )
            self._profile_cache[cache_key] = profile
            return profile

        trailing_team = offense.filter(self._trailing_late_expr(offense))
        leading_team = offense.filter(self._leading_late_rb_expr(offense))
        neutral_team = offense.filter(self._neutral_expr(offense))
        trailing_all = window.filter(self._trailing_late_expr(window))
        leading_all = window.filter(self._leading_late_rb_expr(window))
        neutral_all = window.filter(self._neutral_expr(window))

        pass_factor, pass_ratio, trailing_play_count = self._team_pass_rate_factor(
            trailing_team, neutral_team, trailing_all, neutral_all
        )
        pace_factor, pace_ratio, pace_sample = self._team_pace_factor(
            trailing_team, neutral_team, trailing_all, neutral_all
        )
        target_factors, target_ratios, target_sample = self._target_rank_factors(
            trailing_team, neutral_team, trailing_all, neutral_all
        )
        rb_factors, rb_ratios, rb_sample = self._rb_rank_factors(
            leading_team, neutral_team, leading_all, neutral_all, rosters=rosters
        )

        diagnostics = GameScriptDiagnostics(
            trailing_late_pass_rate_sample=trailing_play_count,
            trailing_late_pace_sample=pace_sample,
            trailing_late_target_sample=target_sample,
            leading_late_rb_sample=rb_sample,
            trailing_late_play_count=trailing_play_count,
            trailing_late_pass_rate_ratio=pass_ratio,
            trailing_late_pace_ratio=pace_ratio,
            trailing_late_rank1_ratio=target_ratios["rank1"],
            trailing_late_rank2_ratio=target_ratios["rank2"],
            trailing_late_rank3_plus_ratio=target_ratios["rank3_plus"],
            leading_late_rb_play_count=rb_sample,
            leading_late_rb1_ratio=rb_ratios["rb1"],
            leading_late_rb2_ratio=rb_ratios["rb2"],
            leading_late_rb3_plus_ratio=rb_ratios["rb3_plus"],
        )

        profile = GameScriptProfile(
            team=team,
            trailing_late_pass_rate_factor=pass_factor,
            trailing_late_pace_factor=pace_factor,
            trailing_late_target_factors=target_factors,
            leading_late_rb_factors=rb_factors,
            diagnostics=diagnostics,
        )
        self._profile_cache[cache_key] = profile
        return profile

    def _late_clock_expr(self, df: pl.DataFrame, seconds: int) -> pl.Expr:
        if "quarter_seconds_remaining" in df.columns:
            return pl.col("quarter_seconds_remaining") <= seconds
        if "game_seconds_remaining" in df.columns:
            return pl.col("game_seconds_remaining") <= seconds
        return pl.lit(False)

    def _trailing_late_expr(self, df: pl.DataFrame) -> pl.Expr:
        cfg = self.config.trailing_late
        return (
            pl.col("play_type").is_in(["pass", "run"])
            & (pl.col("qtr") == 4)
            & (
                (pl.col("score_differential") <= -cfg.deficit_threshold)
                | (
                    self._late_clock_expr(df, cfg.final_five_minutes)
                    & (pl.col("score_differential") <= -cfg.final_five_deficit_threshold)
                )
            )
        )

    def _leading_late_rb_expr(self, df: pl.DataFrame) -> pl.Expr:
        cfg = self.config.leading_late_rb
        return (
            pl.col("play_type").is_in(["pass", "run"])
            & (pl.col("qtr") == 4)
            & self._late_clock_expr(df, cfg.late_minutes)
            & (pl.col("score_differential") >= cfg.lead_threshold)
        )

    def _neutral_expr(self, df: pl.DataFrame) -> pl.Expr:
        scrimmage = pl.col("play_type").is_in(["pass", "run"])
        return scrimmage & ~self._trailing_late_expr(df) & ~self._leading_late_rb_expr(df)

    @staticmethod
    def _scrimmage_counts(df: pl.DataFrame) -> tuple[int, int]:
        if df.is_empty():
            return 0, 0
        pass_plays = int(df.select(pl.col("pass_attempt").fill_null(0).sum()).item() or 0)
        run_plays = int(df.select(pl.col("rush_attempt").fill_null(0).sum()).item() or 0)
        return pass_plays, run_plays

    def _team_pass_rate_factor(
        self,
        trailing_team: pl.DataFrame,
        neutral_team: pl.DataFrame,
        trailing_all: pl.DataFrame,
        neutral_all: pl.DataFrame,
    ) -> tuple[float, float, int]:
        team_pass, team_run = self._scrimmage_counts(trailing_team)
        neutral_pass, neutral_run = self._scrimmage_counts(neutral_team)
        trailing_total = team_pass + team_run
        neutral_total = neutral_pass + neutral_run
        if trailing_total == 0 or neutral_total == 0:
            return 1.0, 1.0, trailing_total

        league_pass, league_run = self._scrimmage_counts(trailing_all)
        league_neutral_pass, league_neutral_run = self._scrimmage_counts(neutral_all)

        trailing_rate = team_pass / trailing_total
        neutral_rate = neutral_pass / neutral_total
        observed = trailing_rate / neutral_rate if neutral_rate > 0 else 1.0

        league_trailing_total = league_pass + league_run
        league_neutral_total = league_neutral_pass + league_neutral_run
        if league_trailing_total == 0 or league_neutral_total == 0:
            prior = 1.0
        else:
            league_trailing_rate = league_pass / league_trailing_total
            league_neutral_rate = league_neutral_pass / league_neutral_total
            prior = league_trailing_rate / league_neutral_rate if league_neutral_rate > 0 else 1.0

        factor = self._bayesian_ratio(
            observed=observed,
            prior=prior,
            n_obs=trailing_total,
            prior_strength=self.config.trailing_late.pass_rate_prior_strength,
            clamp=self.config.trailing_late.pass_rate_clamp,
        )
        return factor, observed, trailing_total

    def _team_pace_factor(
        self,
        trailing_team: pl.DataFrame,
        neutral_team: pl.DataFrame,
        trailing_all: pl.DataFrame,
        neutral_all: pl.DataFrame,
    ) -> tuple[float, float, int]:
        if not self._has_clock(trailing_team) and not self._has_clock(neutral_team):
            return 1.0, 1.0, 0

        team_late_deltas = self._clock_deltas(trailing_team)
        team_neutral_deltas = self._clock_deltas(neutral_team)
        if not team_late_deltas or not team_neutral_deltas:
            return 1.0, 1.0, len(team_late_deltas)

        late_mean = sum(team_late_deltas) / len(team_late_deltas)
        neutral_mean = sum(team_neutral_deltas) / len(team_neutral_deltas)
        if late_mean <= 0 or neutral_mean <= 0:
            return 1.0, 1.0, len(team_late_deltas)

        observed = neutral_mean / late_mean
        league_late_deltas = self._clock_deltas(trailing_all)
        league_neutral_deltas = self._clock_deltas(neutral_all)
        if not league_late_deltas or not league_neutral_deltas:
            prior = 1.0
        else:
            league_late_mean = sum(league_late_deltas) / len(league_late_deltas)
            league_neutral_mean = sum(league_neutral_deltas) / len(league_neutral_deltas)
            prior = (
                league_neutral_mean / league_late_mean
                if league_late_mean > 0 and league_neutral_mean > 0
                else 1.0
            )

        factor = self._bayesian_ratio(
            observed=observed,
            prior=prior,
            n_obs=len(team_late_deltas),
            prior_strength=self.config.trailing_late.pace_prior_strength,
            clamp=self.config.trailing_late.pace_factor_clamp,
        )
        return factor, observed, len(team_late_deltas)

    def _target_rank_factors(
        self,
        trailing_team: pl.DataFrame,
        neutral_team: pl.DataFrame,
        trailing_all: pl.DataFrame,
        neutral_all: pl.DataFrame,
    ) -> tuple[TargetRankFactors, dict[str, float], int]:
        ratios, late_total = self._rank_bucket_ratios(
            trailing_team,
            neutral_team,
            event_type="pass",
            id_col="receiver_player_id",
        )
        prior_ratios, _ = self._rank_bucket_ratios(
            trailing_all,
            neutral_all,
            event_type="pass",
            id_col="receiver_player_id",
        )

        return (
            TargetRankFactors(
                rank1=self._bayesian_ratio(
                    ratios["rank1"],
                    prior_ratios["rank1"],
                    late_total,
                    self.config.trailing_late.target_prior_strength,
                    self.config.trailing_late.target_rank_factor_clamp,
                ),
                rank2=self._bayesian_ratio(
                    ratios["rank2"],
                    prior_ratios["rank2"],
                    late_total,
                    self.config.trailing_late.target_prior_strength,
                    self.config.trailing_late.target_rank_factor_clamp,
                ),
                rank3_plus=self._bayesian_ratio(
                    ratios["rank3_plus"],
                    prior_ratios["rank3_plus"],
                    late_total,
                    self.config.trailing_late.target_prior_strength,
                    self.config.trailing_late.target_rank_factor_clamp,
                ),
            ),
            ratios,
            late_total,
        )

    def _rb_rank_factors(
        self,
        leading_team: pl.DataFrame,
        neutral_team: pl.DataFrame,
        leading_all: pl.DataFrame,
        neutral_all: pl.DataFrame,
        rosters: pl.DataFrame | None = None,
    ) -> tuple[RbRankFactors, dict[str, float], int]:
        allowed_ids_by_team = self._rb_ids_by_team(rosters)
        ratios, late_total = self._rank_bucket_ratios(
            leading_team,
            neutral_team,
            event_type="run",
            id_col="rusher_player_id",
            allowed_ids_by_team=allowed_ids_by_team,
        )
        prior_ratios, _ = self._rank_bucket_ratios(
            leading_all,
            neutral_all,
            event_type="run",
            id_col="rusher_player_id",
            allowed_ids_by_team=allowed_ids_by_team,
        )

        return (
            RbRankFactors(
                rb1=self._bayesian_ratio(
                    ratios["rank1"],
                    prior_ratios["rank1"],
                    late_total,
                    self.config.leading_late_rb.rb_carry_prior_strength,
                    self.config.leading_late_rb.rb_rank_factor_clamp,
                ),
                rb2=self._bayesian_ratio(
                    ratios["rank2"],
                    prior_ratios["rank2"],
                    late_total,
                    self.config.leading_late_rb.rb_carry_prior_strength,
                    self.config.leading_late_rb.rb_rank_factor_clamp,
                ),
                rb3_plus=self._bayesian_ratio(
                    ratios["rank3_plus"],
                    prior_ratios["rank3_plus"],
                    late_total,
                    self.config.leading_late_rb.rb_carry_prior_strength,
                    self.config.leading_late_rb.rb_rank_factor_clamp,
                ),
            ),
            {
                "rb1": ratios["rank1"],
                "rb2": ratios["rank2"],
                "rb3_plus": ratios["rank3_plus"],
            },
            late_total,
        )

    def _rank_bucket_ratios(
        self,
        late_df: pl.DataFrame,
        neutral_df: pl.DataFrame,
        *,
        event_type: str,
        id_col: str,
        allowed_ids_by_team: dict[str, set[str]] | None = None,
    ) -> tuple[dict[str, float], int]:
        late_shares, neutral_shares, late_total = self._event_bucket_shares(
            late_df,
            neutral_df,
            event_type=event_type,
            id_col=id_col,
            allowed_ids_by_team=allowed_ids_by_team,
        )
        if late_total == 0:
            return {bucket: 1.0 for bucket in _RANK_BUCKETS}, 0

        ratios: dict[str, float] = {}
        for bucket in _RANK_BUCKETS:
            neutral_share = neutral_shares[bucket]
            late_share = late_shares[bucket]
            ratios[bucket] = late_share / neutral_share if neutral_share > 0 else 1.0
        return ratios, late_total

    def _event_bucket_shares(
        self,
        late_df: pl.DataFrame,
        neutral_df: pl.DataFrame,
        *,
        event_type: str,
        id_col: str,
        allowed_ids_by_team: dict[str, set[str]] | None = None,
    ) -> tuple[dict[str, float], dict[str, float], int]:
        late_events = self._event_rows(
            late_df,
            event_type=event_type,
            id_col=id_col,
            allowed_ids_by_team=allowed_ids_by_team,
        )
        neutral_events = self._event_rows(
            neutral_df,
            event_type=event_type,
            id_col=id_col,
            allowed_ids_by_team=allowed_ids_by_team,
        )

        neutral_counts_by_team: dict[str, Counter[str]] = defaultdict(Counter)
        late_counts_by_team: dict[str, Counter[str]] = defaultdict(Counter)
        for team, player_id in neutral_events:
            neutral_counts_by_team[team][player_id] += 1
        for team, player_id in late_events:
            late_counts_by_team[team][player_id] += 1

        bucket_map_by_team: dict[str, dict[str, str]] = {}
        for team, counts in neutral_counts_by_team.items():
            bucket_map: dict[str, str] = {}
            ranked_ids = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
            for index, (player_id, _) in enumerate(ranked_ids):
                if index == 0:
                    bucket = "rank1"
                elif index == 1:
                    bucket = "rank2"
                else:
                    bucket = "rank3_plus"
                bucket_map[player_id] = bucket
            bucket_map_by_team[team] = bucket_map

        late_bucket_counts = {bucket: 0 for bucket in _RANK_BUCKETS}
        neutral_bucket_counts = {bucket: 0 for bucket in _RANK_BUCKETS}
        for team, counts in neutral_counts_by_team.items():
            bucket_map = bucket_map_by_team.get(team, {})
            for player_id, count in counts.items():
                neutral_bucket_counts[bucket_map.get(player_id, "rank3_plus")] += count
        for team, counts in late_counts_by_team.items():
            bucket_map = bucket_map_by_team.get(team, {})
            for player_id, count in counts.items():
                late_bucket_counts[bucket_map.get(player_id, "rank3_plus")] += count

        neutral_total = sum(neutral_bucket_counts.values())
        late_total = sum(late_bucket_counts.values())
        late_shares = {
            bucket: (late_bucket_counts[bucket] / late_total if late_total else 0.0)
            for bucket in _RANK_BUCKETS
        }
        neutral_shares = {
            bucket: (
                neutral_bucket_counts[bucket] / neutral_total if neutral_total else 0.0
            )
            for bucket in _RANK_BUCKETS
        }
        return late_shares, neutral_shares, late_total

    def _event_rows(
        self,
        df: pl.DataFrame,
        *,
        event_type: str,
        id_col: str,
        allowed_ids_by_team: dict[str, set[str]] | None = None,
    ) -> list[tuple[str, str]]:
        if df.is_empty():
            return []

        if event_type == "run":
            filtered = df.filter(pl.col("rush_attempt") == 1)
        else:
            filtered = df.filter((pl.col("pass_attempt") == 1) & pl.col(id_col).is_not_null())

        rows: list[tuple[str, str]] = []
        for row in filtered.select(["posteam", id_col]).iter_rows(named=True):
            team = row["posteam"]
            player_id = row[id_col]
            if player_id is None:
                continue
            if allowed_ids_by_team is not None:
                allowed_ids = allowed_ids_by_team.get(team)
                if allowed_ids is None or player_id not in allowed_ids:
                    continue
            rows.append((team, player_id))
        return rows

    @staticmethod
    def _rb_ids_by_team(rosters: pl.DataFrame | None) -> dict[str, set[str]] | None:
        if rosters is None:
            return None
        required = {"team", "player_id", "position"}
        if not required.issubset(rosters.columns):
            return None

        rb_rows = rosters.filter(pl.col("position") == "RB").select(["team", "player_id"]).unique()
        ids_by_team: dict[str, set[str]] = defaultdict(set)
        for row in rb_rows.iter_rows(named=True):
            ids_by_team[row["team"]].add(row["player_id"])
        return dict(ids_by_team)

    @staticmethod
    def _bayesian_ratio(
        observed: float,
        prior: float,
        n_obs: int,
        prior_strength: float,
        clamp: tuple[float, float],
    ) -> float:
        blended = (
            (n_obs * observed + prior_strength * prior) / (n_obs + prior_strength)
            if (n_obs + prior_strength) > 0
            else prior
        )
        return max(clamp[0], min(clamp[1], blended))

    @staticmethod
    def _has_clock(df: pl.DataFrame) -> bool:
        return "quarter_seconds_remaining" in df.columns or "game_seconds_remaining" in df.columns

    def _clock_deltas(self, df: pl.DataFrame) -> list[float]:
        if df.is_empty():
            return []

        if "quarter_seconds_remaining" in df.columns:
            time_col = "quarter_seconds_remaining"
            group_cols = [col for col in ("season", "week", "posteam", "game_id", "qtr") if col in df.columns]
        elif "game_seconds_remaining" in df.columns:
            time_col = "game_seconds_remaining"
            group_cols = [col for col in ("season", "week", "posteam", "game_id") if col in df.columns]
        else:
            return []

        sort_cols = group_cols + [time_col]
        descending = [False] * len(group_cols) + [True]
        rows = (
            df.select(sort_cols)
            .sort(sort_cols, descending=descending)
            .iter_rows(named=True)
        )

        deltas: list[float] = []
        previous_clock_by_group: dict[tuple, float] = {}
        for row in rows:
            group_key = tuple(row[col] for col in group_cols)
            clock_value = float(row[time_col])
            previous = previous_clock_by_group.get(group_key)
            if previous is not None:
                delta = abs(previous - clock_value)
                if delta > 0:
                    deltas.append(delta)
            previous_clock_by_group[group_key] = clock_value
        return deltas

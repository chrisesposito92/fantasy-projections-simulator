from dataclasses import dataclass
from pathlib import Path
from collections import defaultdict
import math
import zlib
import numpy as np
import polars as pl
from fantasy_sim.data.loader import DataLoader
from fantasy_sim.data.game_context import GameContextBuilder
from fantasy_sim.data.actuals import load_actual_scores
from fantasy_sim.engine.monte_carlo import run_simulations
from fantasy_sim.scoring.projections import build_player_projections
from fantasy_sim.validation.metrics import (
    spearman_rank_correlation,
    boom_bust_calibration,
)


@dataclass
class BacktestResult:
    """Results of backtesting one season."""
    test_season: int
    weekly_mae: float
    season_mae: float
    rank_correlations: dict[str, float]
    boom_bust_calibration: float
    total_players_evaluated: int
    total_weeks_evaluated: int

    WEEKLY_MAE_TARGET = 6.0
    SEASON_MAE_TARGET = 25.0
    RANK_CORR_TARGET = 0.80
    CALIBRATION_TARGET = 0.10

    def passes_targets(self) -> bool:
        if self.weekly_mae > self.WEEKLY_MAE_TARGET:
            return False
        if self.season_mae > self.SEASON_MAE_TARGET:
            return False
        for position in ("QB", "RB", "WR", "TE"):
            corr = self.rank_correlations.get(position, 0.0)
            if math.isnan(corr) or corr < self.RANK_CORR_TARGET:
                return False
        if self.boom_bust_calibration > self.CALIBRATION_TARGET:
            return False
        return True


class Backtester:
    """Run hold-out backtests against historical seasons."""

    def __init__(
        self,
        test_season: int,
        n_sims: int = 100,
        num_training_seasons: int = 3,
        scoring_format: str = "ppr",
        cache_dir: Path | None = None,
    ):
        self.test_season = test_season
        self.n_sims = n_sims
        self.training_seasons = list(range(
            test_season - num_training_seasons, test_season
        ))
        self.scoring_format = scoring_format
        self.loader = DataLoader(cache_dir=cache_dir) if cache_dir else DataLoader()
        self.builder = GameContextBuilder(cache_dir=self.loader.cache_dir)

    def run(self, scoring_config: dict) -> BacktestResult:
        """Run the full backtest for one season.

        Uses only training_seasons data for model fitting (no leakage).
        """
        schedules = self.loader.load_schedules([self.test_season])
        player_stats = self.loader.load_player_stats([self.test_season])

        actuals = load_actual_scores(player_stats, scoring_config, self.test_season)
        actual_by_player_week = defaultdict(dict)
        for a in actuals:
            actual_by_player_week[a.player_id][a.week] = a.fpts

        weeks = sorted(
            schedules.filter(pl.col("season") == self.test_season)["week"]
            .unique().to_list()
        )
        weeks = [w for w in weeks if 1 <= w <= 18]

        projected_by_player_week = defaultdict(dict)
        all_weekly_errors = []

        for wk in weeks:
            week_games = schedules.filter(
                (pl.col("week") == wk) & (pl.col("season") == self.test_season)
            )

            games_this_week = 0
            for game in week_games.iter_rows(named=True):
                home, away = game["home_team"], game["away_team"]
                try:
                    home_dists, away_dists, home_roster, away_roster = self.builder.build_game(
                        home, away, seasons=self.training_seasons,
                    )
                    seed = zlib.crc32(game["game_id"].encode()) % (2**31)
                    results = run_simulations(
                        home_dists, away_dists, n_sims=self.n_sims,
                        seed=seed,
                        home_roster=home_roster, away_roster=away_roster,
                    )
                    # Build projections per-game to get correct per-player averages
                    game_projs = build_player_projections(results.games, scoring_config)
                    for proj in game_projs:
                        pid = proj["player_id"]
                        projected_by_player_week[pid][wk] = proj["fpts"]
                        if pid in actual_by_player_week and wk in actual_by_player_week[pid]:
                            error = abs(proj["fpts"] - actual_by_player_week[pid][wk])
                            all_weekly_errors.append(error)
                    games_this_week += 1
                except Exception:
                    continue

        weekly_mae = float(np.mean(all_weekly_errors)) if all_weekly_errors else 99.0

        proj_totals = {pid: sum(wks.values()) for pid, wks in projected_by_player_week.items()}
        act_totals = {pid: sum(wks.values()) for pid, wks in actual_by_player_week.items()}
        common = set(proj_totals.keys()) & set(act_totals.keys())
        season_errors = [abs(proj_totals[pid] - act_totals[pid]) for pid in common]
        season_mae_val = float(np.mean(season_errors)) if season_errors else 99.0

        rank_correlations = {}
        for position in ["QB", "RB", "WR", "TE"]:
            pos_actuals = {
                a.player_id: a for a in actuals
                if a.position == position
            }
            pos_proj = []
            pos_act = []
            for pid in common:
                if pid in pos_actuals:
                    pos_proj.append(proj_totals[pid])
                    pos_act.append(act_totals[pid])
            if len(pos_proj) >= 5:
                rank_correlations[position] = spearman_rank_correlation(pos_proj, pos_act)
            else:
                rank_correlations[position] = 0.0

        boom_threshold = 20.0
        predicted_boom = {}
        actual_boom = {}
        for pid in common:
            proj_weeks = projected_by_player_week.get(pid, {})
            act_weeks = actual_by_player_week.get(pid, {})
            if len(act_weeks) >= 5:
                predicted_boom[pid] = sum(
                    1 for v in proj_weeks.values() if v >= boom_threshold
                ) / max(len(proj_weeks), 1)
                actual_boom[pid] = sum(
                    1 for v in act_weeks.values() if v >= boom_threshold
                ) / len(act_weeks)

        cal = boom_bust_calibration(predicted_boom, actual_boom) if predicted_boom else 0.5

        return BacktestResult(
            test_season=self.test_season,
            weekly_mae=weekly_mae,
            season_mae=season_mae_val,
            rank_correlations=rank_correlations,
            boom_bust_calibration=cal,
            total_players_evaluated=len(common),
            total_weeks_evaluated=len(weeks),
        )

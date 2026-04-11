from dataclasses import dataclass
from pathlib import Path
from collections import defaultdict
import math
import zlib
import numpy as np
import polars as pl
from fantasy_sim.data.ensemble.models import EnsembleConfig
from fantasy_sim.data.loader import DataLoader
from fantasy_sim.data.pff.models import PffConfig
from fantasy_sim.data.weather.models import WeatherConfig
from fantasy_sim.data.vegas.models import PropsConfig, VegasConfig
from fantasy_sim.data.usage.models import UsageConfig
from fantasy_sim.data.actuals import load_actual_scores
from fantasy_sim.scoring.ensemble import FfOpportunityProjectionEnsembler
from fantasy_sim.validation.metrics import (
    spearman_rank_correlation,
    boom_bust_calibration,
)
from fantasy_sim.validation.parallel import GameSpec, simulate_games_parallel, build_games_parallel


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


_HOLDOUT_SEASON = 2025


class Backtester:
    """Run hold-out backtests against historical seasons."""

    def __init__(
        self,
        test_season: int,
        n_sims: int = 100,
        num_training_seasons: int = 3,
        scoring_format: str = "ppr",
        cache_dir: Path | None = None,
        pff_config: PffConfig | None = None,
        weather_config: WeatherConfig | None = None,
        vegas_config: VegasConfig | None = None,
        props_config: PropsConfig | None = None,
        usage_config: UsageConfig | None = None,
        ensemble_config: EnsembleConfig | None = None,
        max_workers: int = 1,
    ):
        if test_season >= _HOLDOUT_SEASON:
            raise ValueError(
                f"Season {test_season} is reserved as hold-out until milestone completion. "
                f"Use seasons 2022-2024 for A/B validation."
            )
        self.test_season = test_season
        self.n_sims = n_sims
        self.training_seasons = list(range(
            test_season - num_training_seasons, test_season
        ))
        self.scoring_format = scoring_format
        self.loader = DataLoader(cache_dir=cache_dir) if cache_dir else DataLoader()
        self._pff_config = pff_config
        self._weather_config = weather_config
        self._vegas_config = vegas_config
        self._props_config = props_config
        self._usage_config = usage_config
        self._ensemble_config = ensemble_config
        self.max_workers = max_workers

    def run(self, scoring_config: dict) -> BacktestResult:
        """Run the full backtest for one season.

        Uses only training_seasons data for model fitting (no leakage).
        Three phases: build contexts -> simulate (optionally parallel) -> aggregate.
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

        # --- Phase 1: Build game contexts (parallel) ---
        game_args = []
        for wk in weeks:
            week_games = schedules.filter(
                (pl.col("week") == wk) & (pl.col("season") == self.test_season)
            )
            for game in week_games.iter_rows(named=True):
                home, away = game["home_team"], game["away_team"]
                seed = zlib.crc32(game["game_id"].encode()) % (2**31)
                game_args.append((
                    home, away, self.training_seasons,
                    self.test_season, wk, game["game_id"], seed,
                ))

        build_results = build_games_parallel(
            game_args,
            cache_dir=self.loader.cache_dir,
            pff_config=self._pff_config,
            weather_config=self._weather_config,
            vegas_config=self._vegas_config,
            props_config=self._props_config,
            usage_config=self._usage_config,
            max_workers=self.max_workers,
            dual_arm=False,
        )

        specs: list[GameSpec] = []
        failed_games: list[str] = []
        total_games = len(build_results)

        for r in build_results:
            if r["status"] != "ok":
                err_type = r.get("error_type", "Error")
                err_msg = str(r.get("error", "unknown"))[:80]
                failed_games.append(r["game_id"])
                print(f"FAIL: {r['game_id']} — {err_type}: {err_msg}")
                continue
            specs.append(GameSpec(
                game_id=r["game_id"],
                home_dists=r["home_dists"],
                away_dists=r["away_dists"],
                home_roster=r["home_roster"],
                away_roster=r["away_roster"],
                seed=r["seed"],
                week=r["week"],
            ))

        # Failure summary and assertion (FIX-01)
        if failed_games:
            failure_rate = len(failed_games) / max(total_games, 1)
            print(f"\n{len(failed_games)}/{total_games} games failed ({failure_rate:.1%})")
            assert failure_rate < 0.05, (
                f"Game failure rate {failure_rate:.1%} >= 5% threshold "
                f"({len(failed_games)} failures: {failed_games[:5]})"
            )

        # --- Phase 2: Simulate (parallel or sequential) ---
        sim_results = simulate_games_parallel(
            specs, n_sims=self.n_sims, scoring_config=scoring_config,
            max_workers=self.max_workers,
        )

        # --- Phase 3: Aggregate results ---
        projected_by_player_week = defaultdict(dict)
        all_weekly_errors = []
        ensembler = None
        if self._ensemble_config is not None and self._ensemble_config.enabled:
            ensembler = FfOpportunityProjectionEnsembler(self._ensemble_config)

        spec_by_id = {s.game_id: s for s in specs}

        for result in sim_results:
            spec = spec_by_id[result.game_id]
            wk = spec.week
            projections = result.projections
            if ensembler is not None:
                projections, _ = ensembler.blend_week(
                    projections,
                    season=self.test_season,
                    week=wk,
                )
            for proj in projections:
                pid = proj["player_id"]
                projected_by_player_week[pid][wk] = proj["fpts"]
                if pid in actual_by_player_week and wk in actual_by_player_week[pid]:
                    error = abs(proj["fpts"] - actual_by_player_week[pid][wk])
                    all_weekly_errors.append(error)

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

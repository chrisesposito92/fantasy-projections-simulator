from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import numpy as np
from fantasy_sim.engine.types import TeamDistributions, GameResult
from fantasy_sim.engine.game_sim import simulate_game

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from fantasy_sim.models.player import TeamRoster


@dataclass
class SimulationSummary:
    """Aggregate statistics across N simulations."""
    games: list[GameResult]

    def summary(self) -> dict:
        n = len(self.games)
        home_scores = [g.home_score for g in self.games]
        away_scores = [g.away_score for g in self.games]
        total_scores = [h + a for h, a in zip(home_scores, away_scores)]
        home_wins = sum(1 for g in self.games if g.home_score > g.away_score)
        ties = sum(1 for g in self.games if g.home_score == g.away_score)
        ot_games = sum(1 for g in self.games if g.overtime)
        total_plays = [g.total_plays for g in self.games]

        return {
            "n_sims": n,
            "home_score_mean": np.mean(home_scores),
            "home_score_std": np.std(home_scores),
            "away_score_mean": np.mean(away_scores),
            "away_score_std": np.std(away_scores),
            "total_score_mean": np.mean(total_scores),
            "total_score_std": np.std(total_scores),
            "home_win_pct": home_wins / n,
            "tie_pct": ties / n,
            "overtime_pct": ot_games / n,
            "plays_mean": np.mean(total_plays),
            "plays_std": np.std(total_plays),
        }

    def player_summary(self) -> dict[str, dict]:
        """Aggregate per-player stats across all simulations."""
        # Collect all player IDs seen across all sims
        all_player_ids: set[str] = set()
        for game in self.games:
            all_player_ids.update(game.player_stats.keys())

        player_totals: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))

        for game in self.games:
            for pid in all_player_ids:
                box = game.player_stats.get(pid)
                player_totals[pid]["pass_yards"].append(box.pass_yards if box else 0)
                player_totals[pid]["rush_yards"].append(box.rush_yards if box else 0)
                player_totals[pid]["receiving_yards"].append(box.receiving_yards if box else 0)
                player_totals[pid]["targets"].append(box.targets if box else 0)
                player_totals[pid]["receptions"].append(box.receptions if box else 0)
                player_totals[pid]["pass_tds"].append(box.pass_tds if box else 0)
                player_totals[pid]["rush_tds"].append(box.rush_tds if box else 0)
                player_totals[pid]["receiving_tds"].append(box.receiving_tds if box else 0)

        result = {}
        for pid, stats in player_totals.items():
            result[pid] = {
                k: {"mean": np.mean(v), "std": np.std(v),
                     "floor": np.percentile(v, 10), "ceiling": np.percentile(v, 90)}
                for k, v in stats.items()
            }
        return result


def run_simulations(
    home_dists: TeamDistributions,
    away_dists: TeamDistributions,
    n_sims: int = 1000,
    seed: int = 42,
    home_roster: TeamRoster | None = None,
    away_roster: TeamRoster | None = None,
) -> SimulationSummary:
    """Run N game simulations and return all results."""
    if n_sims <= 0:
        raise ValueError(f"n_sims must be positive, got {n_sims}")
    rng = np.random.default_rng(seed)
    games = []
    for _ in range(n_sims):
        result = simulate_game(home_dists, away_dists, rng,
                               home_roster=home_roster, away_roster=away_roster)
        games.append(result)
    return SimulationSummary(games=games)

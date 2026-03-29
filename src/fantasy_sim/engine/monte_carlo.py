from dataclasses import dataclass
import numpy as np
from fantasy_sim.engine.types import TeamDistributions, GameResult
from fantasy_sim.engine.game_sim import simulate_game


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


def run_simulations(
    home_dists: TeamDistributions,
    away_dists: TeamDistributions,
    n_sims: int = 1000,
    seed: int = 42,
) -> SimulationSummary:
    """Run N game simulations and return all results."""
    rng = np.random.default_rng(seed)
    games = []
    for _ in range(n_sims):
        result = simulate_game(home_dists, away_dists, rng)
        games.append(result)
    return SimulationSummary(games=games)

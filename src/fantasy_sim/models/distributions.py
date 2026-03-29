from dataclasses import dataclass, field
import numpy as np
from fantasy_sim.models.game_state import GameStateBucket


@dataclass
class PlayCallingDist:
    """P(play_type | game_state) for one team."""
    team: str
    distributions: dict[GameStateBucket, dict[str, float]]
    default: dict[str, float] = field(default_factory=lambda: {"pass": 0.57, "run": 0.43})

    def get_probs(self, bucket: GameStateBucket) -> dict[str, float]:
        return self.distributions.get(bucket, self.default)


@dataclass
class PlayOutcomeDist:
    """Empirical yards-gained distributions by (play_type, game_state)."""
    distributions: dict[tuple[str, GameStateBucket], np.ndarray]
    defaults: dict[str, np.ndarray] = field(default_factory=dict)

    def sample_yards(self, play_type: str, bucket: GameStateBucket, rng: np.random.Generator) -> int:
        key = (play_type, bucket)
        if key in self.distributions:
            arr = self.distributions[key]
        elif play_type in self.defaults:
            arr = self.defaults[play_type]
        else:
            return 0
        return int(rng.choice(arr))


@dataclass
class TurnoverRates:
    """Per-team turnover and sack rates (per-play probabilities)."""
    team: str
    int_rate: float
    fumble_rate: float
    sack_rate: float
    sack_fumble_rate: float


@dataclass
class KickingModel:
    """Field goal and extra point probabilities."""
    fg_make_rate: dict[str, float]
    xp_rate: float

    def fg_prob(self, distance: int) -> float:
        if distance < 40:
            return self.fg_make_rate["0_39"]
        elif distance < 50:
            return self.fg_make_rate["40_49"]
        else:
            return self.fg_make_rate["50_plus"]


@dataclass
class DriveStartModel:
    """Kickoff return model for determining drive starting field position."""
    touchback_rate: float
    touchback_yardline: int
    return_yardlines: np.ndarray

    def sample_start_yardline(self, rng: np.random.Generator) -> int:
        if rng.random() < self.touchback_rate:
            return self.touchback_yardline
        return int(rng.choice(self.return_yardlines))


@dataclass
class PenaltyRates:
    """Per-team penalty rates by penalty type."""
    team: str
    penalty_rate: float
    type_distribution: dict[str, float]
    avg_yards: dict[str, float]

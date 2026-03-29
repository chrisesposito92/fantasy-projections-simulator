from dataclasses import dataclass


@dataclass(frozen=True)
class GameStateBucket:
    """Discretized game state for indexing probability distributions.
    frozen=True makes it hashable so it can be used as a dict key."""
    down: int
    distance: str
    score_diff: str
    quarter: int
    yard_zone: str


def bucket_distance(ydstogo: int) -> str:
    if ydstogo <= 3:
        return "short"
    elif ydstogo <= 6:
        return "medium"
    elif ydstogo <= 10:
        return "long"
    else:
        return "very_long"


def bucket_score_diff(score_differential: int) -> str:
    if score_differential <= -21:
        return "down_big"
    elif score_differential <= -8:
        return "down_med"
    elif score_differential <= -1:
        return "down_small"
    elif score_differential == 0:
        return "tied"
    elif score_differential <= 7:
        return "up_small"
    elif score_differential <= 14:
        return "up_med"
    else:
        return "up_big"


def bucket_yard_zone(yardline_100: int) -> str:
    if yardline_100 >= 80:
        return "backed_up"
    elif yardline_100 >= 50:
        return "own_territory"
    elif yardline_100 >= 21:
        return "opp_territory"
    else:
        return "red_zone"


def bucket_play(down: int, ydstogo: int, score_differential: int, qtr: int, yardline_100: int) -> GameStateBucket:
    return GameStateBucket(
        down=down,
        distance=bucket_distance(ydstogo),
        score_diff=bucket_score_diff(score_differential),
        quarter=qtr,
        yard_zone=bucket_yard_zone(yardline_100),
    )

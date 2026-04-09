"""Bare baseline cache for A/B validation.

Caches bare arm (all engines off) simulation results to disk, keyed by
(season, sims, scoring, training_years). Cache is valid regardless of
defaults.yaml engine config changes since bare = all engines off.
"""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[3] / "results" / "cache"


def cache_path(
    season: int,
    sims: int,
    scoring: str,
    training_years: int,
    cache_dir: Path = DEFAULT_CACHE_DIR,
) -> Path:
    """Generate cache file path for a bare baseline run."""
    return cache_dir / f"bare_{season}_{sims}_{scoring}_{training_years}.json"


def load_cache(path: Path) -> dict | None:
    """Load cached bare baseline results.

    Returns None if cache file doesn't exist. Converts JSON string week
    keys back to int.

    Returns:
        Dict with 'projections' (player_id -> {week: fpts}) and
        'player_meta' (player_id -> {position, team, name}), or None.
    """
    if not path.exists():
        return None
    with open(path) as f:
        raw = json.load(f)
    projections: dict[str, dict[int, float]] = {}
    for pid, weeks in raw["projections"].items():
        projections[pid] = {int(w): v for w, v in weeks.items()}
    return {"projections": projections, "player_meta": raw["player_meta"]}


def save_cache(
    path: Path,
    projections: dict[str, dict[int, float]],
    player_meta: dict[str, dict],
) -> None:
    """Write bare baseline results to cache.

    Args:
        projections: player_id -> {week: fpts} mapping.
        player_meta: player_id -> {position, team, name} mapping.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    serializable = {
        pid: {str(w): v for w, v in weeks.items()}
        for pid, weeks in projections.items()
    }
    with open(path, "w") as f:
        json.dump({"projections": serializable, "player_meta": player_meta}, f)

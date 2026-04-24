"""Bare baseline cache for A/B validation.

Caches bare arm (all engines off) simulation results to disk, keyed by
(season, sims, scoring, training_years). Cache is valid regardless of
defaults.yaml engine config changes since bare = all engines off.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[3] / "results" / "cache"


def _json_safe_value(value: Any) -> Any:
    if hasattr(value, "item"):
        try:
            value = value.item()
        except (TypeError, ValueError):
            pass
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_value(v) for v in value]
    return str(value)


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

    Returns None if cache file doesn't exist. Converts JSON string week keys
    back to int for both the legacy fpts map and the optional projection rows.

    Returns:
        Dict with 'projections' (player_id -> {week: fpts}) and
        'player_meta' (player_id -> {position, team, name}), plus optional
        'projection_rows' (player_id -> {week: projection row}), or None.
    """
    if not path.exists():
        return None
    with open(path) as f:
        raw = json.load(f)
    projections: dict[str, dict[int, float]] = {}
    for pid, weeks in raw["projections"].items():
        projections[pid] = {int(w): v for w, v in weeks.items()}
    projection_rows: dict[str, dict[int, dict]] = {}
    for pid, weeks in raw.get("projection_rows", {}).items():
        projection_rows[pid] = {
            int(w): row
            for w, row in weeks.items()
            if isinstance(row, dict)
        }
    result = {"projections": projections, "player_meta": raw["player_meta"]}
    if "projection_rows" in raw:
        result["projection_rows"] = projection_rows
    return result


def save_cache(
    path: Path,
    projections: dict[str, dict[int, float]],
    player_meta: dict[str, dict],
    projection_rows: dict[str, dict[int, dict]] | None = None,
) -> None:
    """Write bare baseline results to cache.

    Args:
        projections: player_id -> {week: fpts} mapping.
        player_meta: player_id -> {position, team, name} mapping.
        projection_rows: optional player_id -> {week: full projection row} mapping.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    serializable = {
        pid: {str(w): v for w, v in weeks.items()}
        for pid, weeks in projections.items()
    }
    payload = {"projections": serializable, "player_meta": player_meta}
    if projection_rows is not None:
        payload["projection_rows"] = {
            pid: {str(w): _json_safe_value(row) for w, row in weeks.items()}
            for pid, weeks in projection_rows.items()
        }
    with open(path, "w") as f:
        json.dump(payload, f)

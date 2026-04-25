"""Config loading for learned QB rushing adjustments."""

from __future__ import annotations

import math

from fantasy_sim.data.qb_rushing.models import (
    QbDesignedRunModelConfig,
    QbRushingConfig,
    QbScrambleModelConfig,
)


def _load_clamp(raw: object, *, path: str, min_value: float, max_value: float) -> tuple[float, float]:
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        raise ValueError(f"{path} must contain [min, max]")
    lo = float(raw[0])
    hi = float(raw[1])
    if (
        not math.isfinite(lo)
        or not math.isfinite(hi)
        or lo < min_value
        or hi > max_value
        or lo >= hi
    ):
        raise ValueError(f"{path} must satisfy {min_value} <= min < max <= {max_value}")
    return (lo, hi)


def load_qb_rushing_config(defaults: dict) -> QbRushingConfig:
    """Extract QbRushingConfig from the full defaults config dict."""
    raw = defaults.get("qb_rushing") or {}
    scramble_raw = raw.get("scramble") or {}
    designed_runs_raw = raw.get("designed_runs") or {}

    factor_clamp = _load_clamp(
        scramble_raw.get("factor_clamp", [0.50, 1.75]),
        path="qb_rushing.scramble.factor_clamp",
        min_value=0.0,
        max_value=math.inf,
    )
    probability_clamp = _load_clamp(
        scramble_raw.get("probability_clamp", [0.0, 0.25]),
        path="qb_rushing.scramble.probability_clamp",
        min_value=0.0,
        max_value=1.0,
    )
    min_examples = int(scramble_raw.get("min_examples", 500))
    if min_examples < 1:
        raise ValueError("qb_rushing.scramble.min_examples must be >= 1")

    designed_run_factor_clamp = _load_clamp(
        designed_runs_raw.get("factor_clamp", [0.50, 2.00]),
        path="qb_rushing.designed_runs.factor_clamp",
        min_value=0.0,
        max_value=math.inf,
    )
    designed_run_min_examples = int(designed_runs_raw.get("min_examples", 500))
    if designed_run_min_examples < 1:
        raise ValueError("qb_rushing.designed_runs.min_examples must be >= 1")
    min_tail_samples = int(designed_runs_raw.get("min_tail_samples", 20))
    if min_tail_samples < 1:
        raise ValueError("qb_rushing.designed_runs.min_tail_samples must be >= 1")

    return QbRushingConfig(
        scramble=QbScrambleModelConfig(
            enabled=bool(scramble_raw.get("enabled", False)),
            artifacts_dir=scramble_raw.get("artifacts_dir"),
            factor_clamp=factor_clamp,
            probability_clamp=probability_clamp,
            min_examples=min_examples,
        ),
        designed_runs=QbDesignedRunModelConfig(
            enabled=bool(designed_runs_raw.get("enabled", False)),
            artifacts_dir=designed_runs_raw.get("artifacts_dir"),
            factor_clamp=designed_run_factor_clamp,
            min_examples=designed_run_min_examples,
            min_tail_samples=min_tail_samples,
        ),
    )

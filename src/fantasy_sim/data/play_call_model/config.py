"""Config loading for learned pass/run play calling."""

from __future__ import annotations

import math

from fantasy_sim.data.play_call_model.models import PlayCallModelConfig

_VALID_FALLBACKS = {"empirical"}


def load_play_call_model_config(defaults: dict) -> PlayCallModelConfig:
    """Extract PlayCallModelConfig from the full defaults config dict."""
    raw = defaults.get("play_call_model")
    if not raw:
        return PlayCallModelConfig(enabled=False)

    clamp_raw = raw.get("probability_clamp", [0.05, 0.95])
    if not isinstance(clamp_raw, (list, tuple)) or len(clamp_raw) != 2:
        raise ValueError("play_call_model.probability_clamp must contain [min, max]")
    lo = float(clamp_raw[0])
    hi = float(clamp_raw[1])
    if not math.isfinite(lo) or not math.isfinite(hi) or lo < 0.0 or hi > 1.0 or lo >= hi:
        raise ValueError(
            "play_call_model.probability_clamp must satisfy 0 <= min < max <= 1"
        )

    fallback = str(raw.get("fallback", "empirical"))
    if fallback not in _VALID_FALLBACKS:
        raise ValueError(
            f"play_call_model.fallback must be one of {sorted(_VALID_FALLBACKS)}"
        )

    return PlayCallModelConfig(
        enabled=bool(raw.get("enabled", False)),
        artifacts_dir=raw.get("artifacts_dir"),
        probability_clamp=(lo, hi),
        fallback=fallback,
    )

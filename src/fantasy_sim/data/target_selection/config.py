"""Config loading for learned receiver target selection."""

from __future__ import annotations

from fantasy_sim.data.target_selection.models import TargetSelectionConfig

_VALID_POSITIONS = {"RB", "WR", "TE", "FB"}
_VALID_FALLBACKS = {"legacy"}


def load_target_selection_config(defaults: dict) -> TargetSelectionConfig:
    """Extract TargetSelectionConfig from the full defaults config dict."""
    raw = defaults.get("target_selection")
    if not raw:
        return TargetSelectionConfig(enabled=False)

    positions = tuple(str(pos).upper() for pos in raw.get("positions", ("RB", "WR", "TE", "FB")))
    invalid_positions = sorted(set(positions) - _VALID_POSITIONS)
    if invalid_positions:
        raise ValueError(
            "Invalid target_selection.positions config: "
            f"{invalid_positions}; allowed={sorted(_VALID_POSITIONS)}"
        )

    fallback = str(raw.get("fallback", "legacy"))
    if fallback not in _VALID_FALLBACKS:
        raise ValueError(
            "Invalid target_selection.fallback config: "
            f"{fallback!r}; allowed={sorted(_VALID_FALLBACKS)}"
        )

    return TargetSelectionConfig(
        enabled=bool(raw.get("enabled", False)),
        artifacts_dir=raw.get("artifacts_dir"),
        positions=positions,
        probability_floor=float(raw.get("probability_floor", 0.001)),
        max_logit_delta=float(raw.get("max_logit_delta", 3.0)),
        fallback=fallback,
    )

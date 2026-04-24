# Learned Play-Call Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an off-by-default artifact-backed learned pass/run play-call model that can replace empirical `PlayCallingDist` selection when valid artifacts are available.

**Architecture:** The new `fantasy_sim.data.play_call_model` package owns config parsing, feature building, logistic-model fitting, artifact loading, and runtime `P(pass)` inference. `GameContextBuilder` attaches a per-team `play_call_context` to `TeamDistributions`, and `engine.play_caller.select_play_type()` uses that context before falling back to empirical play-calling. When a learned context is valid for a team/game, Vegas pace remains active but Vegas/game-script pass-rate multipliers are skipped for that team's pass/run decision to avoid double-counting.

**Tech Stack:** Python 3.12, polars, numpy, scipy.optimize, pytest, uv, existing validation ledger and config override system.

---

## File Structure

- Create `src/fantasy_sim/data/play_call_model/__init__.py`: public exports for config, model constants, runtime model, context, and training helpers.
- Create `src/fantasy_sim/data/play_call_model/config.py`: load and validate `play_call_model` config from `defaults.yaml`.
- Create `src/fantasy_sim/data/play_call_model/models.py`: constants, dataclasses, feature helpers, and runtime context protocol implementation.
- Create `src/fantasy_sim/data/play_call_model/training.py`: logistic fit helpers and temporal source-season selection.
- Create `src/fantasy_sim/data/play_call_model/runtime.py`: artifact loading and per-team context construction.
- Create `scripts/fit_play_call_model.py`: CLI to fit one artifact per target season.
- Create `tests/test_data/test_play_call_model/`: config, training, and runtime tests.
- Create `tests/test_scripts/test_fit_play_call_model.py`: focused script helper tests.
- Modify `config/defaults.yaml`: add disabled `play_call_model` config.
- Modify `src/fantasy_sim/validation/config.py`: load and pass `play_call_model_config`.
- Modify `src/fantasy_sim/engine/types.py`: add `PlayCallContextProtocol` and `TeamDistributions.play_call_context`.
- Modify `src/fantasy_sim/engine/play_caller.py`: prefer learned context when valid.
- Modify `src/fantasy_sim/data/game_context.py`: construct `PlayCallModel`, attach contexts, and skip only pass-rate modifiers when a valid context exists.
- Modify `src/fantasy_sim/validation/backtester.py`, `src/fantasy_sim/validation/parallel.py`, and `src/fantasy_sim/cli.py`: propagate `play_call_model_config`.
- Modify `src/fantasy_sim/validation/coverage.py`: report artifact coverage.
- Modify `tests/test_validation/test_config.py`, `tests/test_engine/test_play_caller.py`, `tests/test_data/test_game_context.py`, and `tests/test_validation/test_coverage.py`: integration coverage.

---

### Task 1: Config, Models, And Defaults

**Files:**
- Create: `src/fantasy_sim/data/play_call_model/__init__.py`
- Create: `src/fantasy_sim/data/play_call_model/models.py`
- Create: `src/fantasy_sim/data/play_call_model/config.py`
- Create: `tests/test_data/test_play_call_model/__init__.py`
- Create: `tests/test_data/test_play_call_model/test_config.py`
- Modify: `config/defaults.yaml`
- Modify: `src/fantasy_sim/validation/config.py`
- Modify: `tests/test_validation/test_config.py`

- [ ] **Step 1: Write failing config tests**

Create `tests/test_data/test_play_call_model/__init__.py` as an empty file.

Create `tests/test_data/test_play_call_model/test_config.py`:

```python
import pytest

from fantasy_sim.data.play_call_model import load_play_call_model_config


def test_missing_config_is_disabled():
    config = load_play_call_model_config({})

    assert config.enabled is False
    assert config.artifacts_dir is None
    assert config.probability_clamp == (0.05, 0.95)
    assert config.fallback == "empirical"


def test_loads_enabled_config_values():
    config = load_play_call_model_config(
        {
            "play_call_model": {
                "enabled": True,
                "artifacts_dir": "results/play_call_model/test",
                "probability_clamp": [0.10, 0.90],
                "fallback": "empirical",
            }
        }
    )

    assert config.enabled is True
    assert config.artifacts_dir == "results/play_call_model/test"
    assert config.probability_clamp == (0.10, 0.90)
    assert config.fallback == "empirical"


@pytest.mark.parametrize(
    "clamp",
    [
        [0.10],
        [0.90, 0.10],
        [-0.01, 0.90],
        [0.10, 1.01],
    ],
)
def test_invalid_probability_clamp_raises(clamp):
    with pytest.raises(ValueError, match="play_call_model\\.probability_clamp"):
        load_play_call_model_config(
            {"play_call_model": {"enabled": True, "probability_clamp": clamp}}
        )


def test_invalid_fallback_raises():
    with pytest.raises(ValueError, match="play_call_model\\.fallback"):
        load_play_call_model_config(
            {"play_call_model": {"enabled": True, "fallback": "neutral"}}
        )
```

Extend `tests/test_validation/test_config.py` in `TestBuildEngineConfigs`:

```python
    def test_defaults_keep_play_call_model_disabled(self):
        defaults = load_defaults()

        configs = build_engine_configs(defaults)

        assert "play_call_model_config" in configs
        assert configs["play_call_model_config"] is None

    def test_enabled_play_call_model_config_is_built(self):
        defaults = load_defaults()
        overridden = apply_overrides(
            defaults,
            [
                "play_call_model.enabled=true",
                "play_call_model.artifacts_dir=results/play_call_model/test",
                "play_call_model.probability_clamp=[0.10,0.90]",
            ],
        )

        configs = build_engine_configs(overridden)

        assert configs["play_call_model_config"] is not None
        assert configs["play_call_model_config"].artifacts_dir == "results/play_call_model/test"
        assert configs["play_call_model_config"].probability_clamp == (0.10, 0.90)
```

- [ ] **Step 2: Run config tests and verify they fail**

Run:

```bash
uv run pytest tests/test_data/test_play_call_model/test_config.py tests/test_validation/test_config.py::TestBuildEngineConfigs::test_defaults_keep_play_call_model_disabled tests/test_validation/test_config.py::TestBuildEngineConfigs::test_enabled_play_call_model_config_is_built -v
```

Expected: FAIL because `fantasy_sim.data.play_call_model` does not exist.

- [ ] **Step 3: Add model constants and config dataclass**

Create `src/fantasy_sim/data/play_call_model/models.py`:

```python
"""Models and feature helpers for learned pass/run play calling."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from fantasy_sim.engine.game_script import RuntimeGameScript
    from fantasy_sim.engine.types import GameState

PLAY_CALL_MODEL_SCHEMA_VERSION = 1
PLAY_CALL_MODEL_TYPE = "logistic_play_call_v1"
DEFAULT_ARTIFACT_DIR = (
    Path(__file__).resolve().parent / "artifacts" / "decision_v1"
)

DEFAULT_PLAY_CALL_FEATURES: tuple[str, ...] = (
    "intercept",
    "down_1",
    "down_2",
    "down_3",
    "down_4",
    "distance_norm",
    "is_short",
    "is_long",
    "is_very_long",
    "yard_line_norm",
    "is_red_zone",
    "is_goal_to_go",
    "quarter_1",
    "quarter_2",
    "quarter_3",
    "quarter_4",
    "clock_norm",
    "is_two_minute",
    "score_diff_norm",
    "is_trailing",
    "is_leading",
    "is_home",
    "spread_norm",
    "total_norm",
    "implied_total_norm",
    "week_norm",
    "team_prior_pass_rate",
    "opponent_prior_pass_rate_allowed",
    "trailing_late",
)


@dataclass(frozen=True)
class PlayCallModelConfig:
    """Configuration for the learned pass/run play-call node."""

    enabled: bool = False
    artifacts_dir: str | None = None
    probability_clamp: tuple[float, float] = (0.05, 0.95)
    fallback: str = "empirical"


@dataclass(frozen=True)
class PlayCallContext:
    """Runtime context for a team's learned play-call artifact."""

    coefficients: dict[str, float]
    feature_names: tuple[str, ...]
    team: str
    opponent: str
    home_team: str
    away_team: str
    is_home: bool
    target_season: int
    week: int
    spread_line: float | None = None
    total_line: float | None = None
    implied_team_total: float | None = None
    team_prior_pass_rate: float = 0.57
    opponent_prior_pass_rate_allowed: float = 0.57
    probability_clamp: tuple[float, float] = (0.05, 0.95)

    def pass_probability(
        self,
        state: "GameState",
        script: "RuntimeGameScript | None" = None,
    ) -> float | None:
        values = play_call_feature_values(
            state,
            team=self.team,
            opponent=self.opponent,
            home_team=self.home_team,
            away_team=self.away_team,
            is_home=self.is_home,
            week=self.week,
            spread_line=self.spread_line,
            total_line=self.total_line,
            implied_team_total=self.implied_team_total,
            team_prior_pass_rate=self.team_prior_pass_rate,
            opponent_prior_pass_rate_allowed=self.opponent_prior_pass_rate_allowed,
            script=script,
        )
        logit = 0.0
        for name in self.feature_names:
            logit += float(self.coefficients.get(name, 0.0)) * values.get(name, 0.0)
        if not np.isfinite(logit):
            return None
        prob = float(1.0 / (1.0 + np.exp(-np.clip(logit, -35.0, 35.0))))
        lo, hi = self.probability_clamp
        prob = float(np.clip(prob, lo, hi))
        if not np.isfinite(prob):
            return None
        return prob


def play_call_feature_values(
    state: "GameState",
    *,
    team: str,
    opponent: str,
    home_team: str,
    away_team: str,
    is_home: bool,
    week: int,
    spread_line: float | None,
    total_line: float | None,
    implied_team_total: float | None,
    team_prior_pass_rate: float,
    opponent_prior_pass_rate_allowed: float,
    script: "RuntimeGameScript | None" = None,
) -> dict[str, float]:
    del team, opponent, home_team, away_team
    distance = max(0, int(state.distance))
    yard_line = max(1, min(99, int(state.yard_line)))
    score_diff = float(state.score_differential)
    clock = max(0, min(900, int(state.clock)))
    quarter = max(1, min(5, int(state.quarter)))
    trailing_late = 1.0 if getattr(script, "regime", None) == "trailing_late" else 0.0
    spread = 0.0 if spread_line is None else float(spread_line)
    total = 44.0 if total_line is None else float(total_line)
    implied = total / 2.0 if implied_team_total is None else float(implied_team_total)
    return {
        "intercept": 1.0,
        "down_1": 1.0 if state.down == 1 else 0.0,
        "down_2": 1.0 if state.down == 2 else 0.0,
        "down_3": 1.0 if state.down == 3 else 0.0,
        "down_4": 1.0 if state.down == 4 else 0.0,
        "distance_norm": min(distance, 20) / 20.0,
        "is_short": 1.0 if distance <= 3 else 0.0,
        "is_long": 1.0 if 7 <= distance <= 10 else 0.0,
        "is_very_long": 1.0 if distance > 10 else 0.0,
        "yard_line_norm": yard_line / 100.0,
        "is_red_zone": 1.0 if yard_line <= 20 else 0.0,
        "is_goal_to_go": 1.0 if yard_line <= distance else 0.0,
        "quarter_1": 1.0 if quarter == 1 else 0.0,
        "quarter_2": 1.0 if quarter == 2 else 0.0,
        "quarter_3": 1.0 if quarter == 3 else 0.0,
        "quarter_4": 1.0 if quarter == 4 else 0.0,
        "clock_norm": clock / 900.0,
        "is_two_minute": 1.0 if clock <= 120 and quarter in (2, 4) else 0.0,
        "score_diff_norm": float(np.clip(score_diff / 28.0, -1.0, 1.0)),
        "is_trailing": 1.0 if score_diff < 0 else 0.0,
        "is_leading": 1.0 if score_diff > 0 else 0.0,
        "is_home": 1.0 if is_home else 0.0,
        "spread_norm": float(np.clip(spread / 14.0, -1.5, 1.5)),
        "total_norm": float(np.clip((total - 44.0) / 14.0, -1.5, 1.5)),
        "implied_total_norm": float(np.clip((implied - 22.0) / 10.0, -1.5, 1.5)),
        "week_norm": float(np.clip(week / 18.0, 0.0, 1.0)),
        "team_prior_pass_rate": float(np.clip(team_prior_pass_rate, 0.0, 1.0)),
        "opponent_prior_pass_rate_allowed": float(
            np.clip(opponent_prior_pass_rate_allowed, 0.0, 1.0)
        ),
        "trailing_late": trailing_late,
    }
```

- [ ] **Step 4: Add config loader and public exports**

Create `src/fantasy_sim/data/play_call_model/config.py`:

```python
"""Config loading for learned pass/run play calling."""

from __future__ import annotations

from fantasy_sim.data.play_call_model.models import PlayCallModelConfig

_VALID_FALLBACKS = {"empirical"}


def load_play_call_model_config(defaults: dict) -> PlayCallModelConfig:
    raw = defaults.get("play_call_model")
    if not raw:
        return PlayCallModelConfig(enabled=False)

    clamp_raw = raw.get("probability_clamp", [0.05, 0.95])
    if (
        not isinstance(clamp_raw, (list, tuple))
        or len(clamp_raw) != 2
    ):
        raise ValueError("play_call_model.probability_clamp must contain [min, max]")
    lo = float(clamp_raw[0])
    hi = float(clamp_raw[1])
    if lo < 0.0 or hi > 1.0 or lo >= hi:
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
```

Create `src/fantasy_sim/data/play_call_model/__init__.py`:

```python
"""Learned pass/run play-call model."""

from fantasy_sim.data.play_call_model.config import load_play_call_model_config
from fantasy_sim.data.play_call_model.models import (
    DEFAULT_ARTIFACT_DIR,
    DEFAULT_PLAY_CALL_FEATURES,
    PLAY_CALL_MODEL_SCHEMA_VERSION,
    PLAY_CALL_MODEL_TYPE,
    PlayCallContext,
    PlayCallModelConfig,
    play_call_feature_values,
)

__all__ = [
    "DEFAULT_ARTIFACT_DIR",
    "DEFAULT_PLAY_CALL_FEATURES",
    "PLAY_CALL_MODEL_SCHEMA_VERSION",
    "PLAY_CALL_MODEL_TYPE",
    "PlayCallContext",
    "PlayCallModelConfig",
    "load_play_call_model_config",
    "play_call_feature_values",
]
```

- [ ] **Step 5: Add disabled defaults block**

Add this block to `config/defaults.yaml` near `target_selection:`:

```yaml
play_call_model:
  enabled: false
  artifacts_dir: null
  probability_clamp: [0.05, 0.95]
  fallback: empirical
```

- [ ] **Step 6: Wire validation config loading**

Modify `src/fantasy_sim/validation/config.py`:

```python
from fantasy_sim.data.play_call_model import load_play_call_model_config
```

In `build_engine_configs()`, after loading `target_selection`:

```python
    play_call_model = load_play_call_model_config(config)
```

Add the return key:

```python
        "play_call_model_config": play_call_model if play_call_model.enabled else None,
```

Add the disabled key to `build_bare_engine_configs()`:

```python
        "play_call_model_config": None,
```

- [ ] **Step 7: Run config tests and verify pass**

Run:

```bash
uv run pytest tests/test_data/test_play_call_model/test_config.py tests/test_validation/test_config.py::TestBuildEngineConfigs::test_defaults_keep_play_call_model_disabled tests/test_validation/test_config.py::TestBuildEngineConfigs::test_enabled_play_call_model_config_is_built -v
```

Expected: PASS.

- [ ] **Step 8: Commit config foundation**

```bash
git add \
  config/defaults.yaml \
  src/fantasy_sim/data/play_call_model/__init__.py \
  src/fantasy_sim/data/play_call_model/config.py \
  src/fantasy_sim/data/play_call_model/models.py \
  src/fantasy_sim/validation/config.py \
  tests/test_data/test_play_call_model/__init__.py \
  tests/test_data/test_play_call_model/test_config.py \
  tests/test_validation/test_config.py
git commit -m "feat: add learned play-call model config"
```

---

### Task 2: Training Helpers And Logistic Fit

**Files:**
- Create: `src/fantasy_sim/data/play_call_model/training.py`
- Create: `tests/test_data/test_play_call_model/test_training.py`
- Modify: `src/fantasy_sim/data/play_call_model/__init__.py`

- [ ] **Step 1: Write failing training tests**

Create `tests/test_data/test_play_call_model/test_training.py`:

```python
import numpy as np
import polars as pl
import pytest

from fantasy_sim.data.play_call_model.models import DEFAULT_PLAY_CALL_FEATURES
from fantasy_sim.data.play_call_model.training import (
    PlayCallTrainingExample,
    build_example_from_row,
    fit_logistic_play_call,
    source_seasons_for_artifact,
)


def _row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "season": 2023,
        "week": 5,
        "posteam": "KC",
        "defteam": "BUF",
        "home_team": "KC",
        "away_team": "BUF",
        "play_type": "pass",
        "down": 3,
        "ydstogo": 8,
        "yardline_100": 35,
        "qtr": 4,
        "quarter_seconds_remaining": 118,
        "score_differential": -6,
        "spread_line": 2.5,
        "total_line": 48.5,
        "goal_to_go": False,
    }
    row.update(overrides)
    return row


def test_source_seasons_for_artifact_uses_prior_seasons_only():
    seasons = source_seasons_for_artifact(
        target_season=2024,
        min_source_season=2018,
        training_years=4,
    )

    assert seasons == [2020, 2021, 2022, 2023]


def test_source_seasons_for_artifact_clamps_to_min_source_season():
    seasons = source_seasons_for_artifact(
        target_season=2022,
        min_source_season=2020,
        training_years=4,
    )

    assert seasons == [2020, 2021]


def test_build_example_from_row_returns_binary_label_and_feature_vector():
    example = build_example_from_row(_row(), DEFAULT_PLAY_CALL_FEATURES)

    assert example is not None
    assert example.label == 1
    assert example.features.shape == (len(DEFAULT_PLAY_CALL_FEATURES),)
    assert np.isfinite(example.features).all()


def test_build_example_from_row_labels_run_as_zero():
    example = build_example_from_row(_row(play_type="run"), DEFAULT_PLAY_CALL_FEATURES)

    assert example is not None
    assert example.label == 0


def test_build_example_from_row_skips_non_scrimmage_play():
    assert build_example_from_row(
        _row(play_type="punt"),
        DEFAULT_PLAY_CALL_FEATURES,
    ) is None


def test_fit_logistic_play_call_rejects_empty_examples():
    with pytest.raises(ValueError, match="zero examples"):
        fit_logistic_play_call([], ("intercept",))


def test_fit_logistic_play_call_learns_positive_feature_for_pass():
    examples = [
        PlayCallTrainingExample(features=np.array([1.0, 1.0]), label=1)
        for _ in range(30)
    ] + [
        PlayCallTrainingExample(features=np.array([1.0, 0.0]), label=0)
        for _ in range(30)
    ]

    result = fit_logistic_play_call(
        examples,
        ("intercept", "pass_feature"),
        l2=0.1,
        max_iter=100,
    )

    assert result.num_examples == 60
    assert result.coefficients["pass_feature"] > 0
    assert result.converged is True
```

- [ ] **Step 2: Run training tests and verify they fail**

Run:

```bash
uv run pytest tests/test_data/test_play_call_model/test_training.py -v
```

Expected: FAIL because `fantasy_sim.data.play_call_model.training` does not exist.

- [ ] **Step 3: Implement training helpers**

Create `src/fantasy_sim/data/play_call_model/training.py`:

```python
"""Training helpers for learned pass/run play calling."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np
from scipy.optimize import minimize

from fantasy_sim.data.play_call_model.models import play_call_feature_values
from fantasy_sim.engine.types import GameState


@dataclass(frozen=True)
class PlayCallTrainingExample:
    features: np.ndarray
    label: int


@dataclass(frozen=True)
class PlayCallFitResult:
    coefficients: dict[str, float]
    objective: float
    converged: bool
    iterations: int
    num_examples: int


def source_seasons_for_artifact(
    *,
    target_season: int,
    min_source_season: int,
    training_years: int,
) -> list[int]:
    start = max(int(min_source_season), int(target_season) - int(training_years))
    return list(range(start, int(target_season)))


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    try:
        value_f = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(value_f):
        return None
    return value_f


def _bool_value(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return bool(value)


def _state_from_row(row: Mapping[str, object]) -> GameState | None:
    try:
        quarter = int(row.get("qtr") or 1)
        clock = int(row.get("quarter_seconds_remaining") or 0)
        posteam = str(row["posteam"])
        home_team = str(row["home_team"])
        away_team = str(row["away_team"])
        possession = "home" if posteam == home_team else "away"
        posteam_score = int(row.get("posteam_score") or 0)
        defteam_score = int(row.get("defteam_score") or 0)
        if "score_differential" in row and row.get("score_differential") is not None:
            score_differential = int(row["score_differential"])
            if possession == "home":
                home_score = max(0, score_differential)
                away_score = max(0, -score_differential)
            else:
                home_score = max(0, -score_differential)
                away_score = max(0, score_differential)
        else:
            home_score = posteam_score if possession == "home" else defteam_score
            away_score = defteam_score if possession == "home" else posteam_score
        return GameState(
            quarter=quarter,
            clock=clock,
            possession=possession,
            down=int(row["down"]),
            distance=int(row["ydstogo"]),
            yard_line=int(row["yardline_100"]),
            home_score=home_score,
            away_score=away_score,
            home_team=home_team,
            away_team=away_team,
            receiving_2nd_half="away",
            week=int(row.get("week") or 0),
        )
    except (KeyError, TypeError, ValueError):
        return None


def build_example_from_row(
    row: Mapping[str, object],
    feature_names: tuple[str, ...],
) -> PlayCallTrainingExample | None:
    play_type = row.get("play_type")
    if play_type not in {"pass", "run"}:
        return None
    if row.get("posteam") is None or row.get("defteam") is None:
        return None
    state = _state_from_row(row)
    if state is None:
        return None
    posteam = str(row["posteam"])
    defteam = str(row["defteam"])
    home_team = str(row["home_team"])
    away_team = str(row["away_team"])
    spread_line = _float_or_none(row.get("spread_line"))
    total_line = _float_or_none(row.get("total_line"))
    implied_team_total = None
    if total_line is not None and spread_line is not None:
        if posteam == home_team:
            implied_team_total = total_line / 2.0 + spread_line / 2.0
        else:
            implied_team_total = total_line / 2.0 - spread_line / 2.0
    values = play_call_feature_values(
        state,
        team=posteam,
        opponent=defteam,
        home_team=home_team,
        away_team=away_team,
        is_home=posteam == home_team,
        week=int(row.get("week") or 0),
        spread_line=spread_line,
        total_line=total_line,
        implied_team_total=implied_team_total,
        team_prior_pass_rate=0.57,
        opponent_prior_pass_rate_allowed=0.57,
        script=None,
    )
    features = np.array([values.get(name, 0.0) for name in feature_names], dtype=float)
    if not np.all(np.isfinite(features)):
        return None
    label = 1 if play_type == "pass" else 0
    return PlayCallTrainingExample(features=features, label=label)


def fit_logistic_play_call(
    examples: list[PlayCallTrainingExample],
    feature_names: tuple[str, ...],
    *,
    l2: float = 1.0,
    max_iter: int = 200,
) -> PlayCallFitResult:
    if not examples:
        raise ValueError("Cannot fit play-call model with zero examples")
    if not feature_names:
        raise ValueError("feature_names must not be empty")
    n_features = len(feature_names)
    x = np.vstack([example.features for example in examples]).astype(float)
    y = np.array([example.label for example in examples], dtype=float)
    if x.shape != (len(examples), n_features):
        raise ValueError("Feature matrix shape does not match feature_names")

    def objective(beta: np.ndarray) -> tuple[float, np.ndarray]:
        logits = np.clip(x @ beta, -35.0, 35.0)
        probs = 1.0 / (1.0 + np.exp(-logits))
        eps = 1e-12
        loss = -float(
            np.sum(y * np.log(np.maximum(probs, eps)) + (1.0 - y) * np.log(np.maximum(1.0 - probs, eps)))
        )
        loss += 0.5 * l2 * float(np.dot(beta, beta))
        grad = x.T @ (probs - y) + l2 * beta
        return loss, grad

    result = minimize(
        objective,
        np.zeros(n_features, dtype=float),
        method="L-BFGS-B",
        jac=True,
        options={"maxiter": max_iter},
    )
    return PlayCallFitResult(
        coefficients={
            name: float(value)
            for name, value in zip(feature_names, result.x, strict=True)
        },
        objective=float(result.fun),
        converged=bool(result.success),
        iterations=int(result.nit),
        num_examples=len(examples),
    )
```

- [ ] **Step 4: Export training helpers**

Modify `src/fantasy_sim/data/play_call_model/__init__.py`:

```python
from fantasy_sim.data.play_call_model.training import (
    PlayCallFitResult,
    PlayCallTrainingExample,
    build_example_from_row,
    fit_logistic_play_call,
    source_seasons_for_artifact,
)
```

Add the names to `__all__`.

- [ ] **Step 5: Run training tests and verify pass**

Run:

```bash
uv run pytest tests/test_data/test_play_call_model/test_training.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit training helpers**

```bash
git add \
  src/fantasy_sim/data/play_call_model/__init__.py \
  src/fantasy_sim/data/play_call_model/training.py \
  tests/test_data/test_play_call_model/test_training.py
git commit -m "feat: add learned play-call training helpers"
```

---

### Task 3: Artifact Fitter Script

**Files:**
- Create: `scripts/fit_play_call_model.py`
- Create: `tests/test_scripts/test_fit_play_call_model.py`

- [ ] **Step 1: Write failing script tests**

Create `tests/test_scripts/test_fit_play_call_model.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from fit_play_call_model import collect_examples_from_pbp


def _pbp() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "season": [2022, 2022, 2022],
            "week": [1, 1, 1],
            "game_id": ["g1", "g1", "g1"],
            "posteam": ["KC", "KC", "KC"],
            "defteam": ["BUF", "BUF", "BUF"],
            "home_team": ["KC", "KC", "KC"],
            "away_team": ["BUF", "BUF", "BUF"],
            "play_type": ["pass", "run", "punt"],
            "down": [1, 2, 4],
            "ydstogo": [10, 5, 8],
            "yardline_100": [75, 50, 60],
            "qtr": [1, 2, 4],
            "quarter_seconds_remaining": [900, 500, 200],
            "score_differential": [0, -3, -3],
            "spread_line": [2.5, 2.5, 2.5],
            "total_line": [48.5, 48.5, 48.5],
            "goal_to_go": [False, False, False],
        }
    )


def test_collect_examples_from_pbp_keeps_only_pass_run():
    examples = collect_examples_from_pbp(_pbp())

    assert len(examples) == 2
    assert [example.label for example in examples] == [1, 0]
```

- [ ] **Step 2: Run script tests and verify they fail**

Run:

```bash
uv run pytest tests/test_scripts/test_fit_play_call_model.py -v
```

Expected: FAIL because `scripts/fit_play_call_model.py` does not exist.

- [ ] **Step 3: Add fitter script**

Create `scripts/fit_play_call_model.py`:

```python
"""Fit learned pass/run play-call artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import polars as pl

from fantasy_sim.data.loader import DataLoader
from fantasy_sim.data.play_call_model.models import (
    DEFAULT_PLAY_CALL_FEATURES,
    PLAY_CALL_MODEL_SCHEMA_VERSION,
    PLAY_CALL_MODEL_TYPE,
)
from fantasy_sim.data.play_call_model.training import (
    PlayCallTrainingExample,
    build_example_from_row,
    fit_logistic_play_call,
    source_seasons_for_artifact,
)


def build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fit learned pass/run play-call artifacts.",
    )
    parser.add_argument("--test-seasons", nargs="+", type=int, required=True)
    parser.add_argument("--min-source-season", type=int, default=2018)
    parser.add_argument("--training-years", type=int, default=4)
    parser.add_argument("--l2", type=float, default=1.0)
    parser.add_argument("--max-iter", type=int, default=200)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def collect_examples_from_pbp(
    pbp: pl.DataFrame,
    feature_names: tuple[str, ...] = DEFAULT_PLAY_CALL_FEATURES,
) -> list[PlayCallTrainingExample]:
    examples: list[PlayCallTrainingExample] = []
    if pbp.is_empty():
        return examples
    required = {
        "play_type",
        "posteam",
        "defteam",
        "home_team",
        "away_team",
        "down",
        "ydstogo",
        "yardline_100",
        "qtr",
    }
    missing = required - set(pbp.columns)
    if missing:
        raise ValueError(f"PBP is missing required columns: {sorted(missing)}")
    plays = pbp.filter(pl.col("play_type").is_in(["pass", "run"]))
    for row in plays.iter_rows(named=True):
        example = build_example_from_row(row, feature_names)
        if example is not None:
            examples.append(example)
    return examples


def fit_artifact_for_season(
    *,
    loader: DataLoader,
    target_season: int,
    min_source_season: int,
    training_years: int,
    output_dir: Path,
    l2: float,
    max_iter: int,
) -> dict:
    source_seasons = source_seasons_for_artifact(
        target_season=target_season,
        min_source_season=min_source_season,
        training_years=training_years,
    )
    if not source_seasons:
        raise ValueError(f"No source seasons available for target season {target_season}")
    pbp = loader.load_pbp(source_seasons)
    examples = collect_examples_from_pbp(pbp)
    fit = fit_logistic_play_call(
        examples,
        DEFAULT_PLAY_CALL_FEATURES,
        l2=l2,
        max_iter=max_iter,
    )
    pass_rate = (
        sum(example.label for example in examples) / len(examples)
        if examples else 0.0
    )
    artifact = {
        "schema_version": PLAY_CALL_MODEL_SCHEMA_VERSION,
        "model_type": PLAY_CALL_MODEL_TYPE,
        "target_season": target_season,
        "source_seasons": source_seasons,
        "feature_names": list(DEFAULT_PLAY_CALL_FEATURES),
        "coefficients": fit.coefficients,
        "probability_clamp": [0.05, 0.95],
        "diagnostics": {
            "num_examples": fit.num_examples,
            "pass_rate": pass_rate,
            "objective": fit.objective,
            "converged": fit.converged,
            "iterations": fit.iterations,
            "l2": l2,
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"play_call_model_{target_season}.json"
    path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n")
    return artifact


def main() -> int:
    args = build_cli().parse_args()
    loader = DataLoader()
    for season in args.test_seasons:
        print(f"Fitting play-call model artifact for {season}...", flush=True)
        artifact = fit_artifact_for_season(
            loader=loader,
            target_season=season,
            min_source_season=args.min_source_season,
            training_years=args.training_years,
            output_dir=args.output_dir,
            l2=args.l2,
            max_iter=args.max_iter,
        )
        diag = artifact["diagnostics"]
        print(
            f"  wrote play_call_model_{season}.json "
            f"examples={diag['num_examples']} "
            f"pass_rate={diag['pass_rate']:.3f} "
            f"converged={diag['converged']} "
            f"iterations={diag['iterations']}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run script tests and verify pass**

Run:

```bash
uv run pytest tests/test_scripts/test_fit_play_call_model.py -v
```

Expected: PASS.

- [ ] **Step 5: Run a tiny script smoke**

Run:

```bash
uv run python scripts/fit_play_call_model.py \
  --test-seasons 2022 \
  --min-source-season 2021 \
  --training-years 1 \
  --output-dir /tmp/fantasy-play-call-smoke
```

Expected: prints `wrote play_call_model_2022.json` and exits with status 0.

- [ ] **Step 6: Commit fitter**

```bash
git add scripts/fit_play_call_model.py tests/test_scripts/test_fit_play_call_model.py
git commit -m "feat: add learned play-call artifact fitter"
```

---

### Task 4: Runtime Artifact Loading

**Files:**
- Create: `src/fantasy_sim/data/play_call_model/runtime.py`
- Create: `tests/test_data/test_play_call_model/test_runtime.py`
- Modify: `src/fantasy_sim/data/play_call_model/__init__.py`

- [ ] **Step 1: Write failing runtime tests**

Create `tests/test_data/test_play_call_model/test_runtime.py`:

```python
import json

import pytest

from fantasy_sim.data.play_call_model import PlayCallModelConfig, PlayCallModel
from fantasy_sim.data.play_call_model.models import (
    PLAY_CALL_MODEL_SCHEMA_VERSION,
    PLAY_CALL_MODEL_TYPE,
)
from fantasy_sim.engine.types import GameState


def make_state() -> GameState:
    return GameState(
        quarter=1,
        clock=900,
        possession="home",
        down=3,
        distance=8,
        yard_line=45,
        home_score=0,
        away_score=7,
        home_team="KC",
        away_team="BUF",
        receiving_2nd_half="away",
        week=4,
    )


def write_artifact(path, *, schema_version=PLAY_CALL_MODEL_SCHEMA_VERSION, coefficients=None):
    path.write_text(
        json.dumps(
            {
                "schema_version": schema_version,
                "model_type": PLAY_CALL_MODEL_TYPE,
                "target_season": 2024,
                "feature_names": ["intercept", "down_3"],
                "coefficients": coefficients if coefficients is not None else {
                    "intercept": 0.0,
                    "down_3": 4.0,
                },
                "probability_clamp": [0.05, 0.95],
            }
        )
    )


def test_missing_artifact_returns_none(tmp_path):
    model = PlayCallModel(PlayCallModelConfig(enabled=True, artifacts_dir=str(tmp_path)))

    assert model.build_context(
        team="KC",
        opponent="BUF",
        home_team="KC",
        away_team="BUF",
        target_season=2024,
        week=1,
        is_home=True,
    ) is None


def test_invalid_schema_returns_none(tmp_path):
    write_artifact(tmp_path / "play_call_model_2024.json", schema_version=999)
    model = PlayCallModel(PlayCallModelConfig(enabled=True, artifacts_dir=str(tmp_path)))

    assert model.build_context(
        team="KC",
        opponent="BUF",
        home_team="KC",
        away_team="BUF",
        target_season=2024,
        week=1,
        is_home=True,
    ) is None


def test_context_loads_artifact_and_predicts_probability(tmp_path):
    write_artifact(tmp_path / "play_call_model_2024.json")
    model = PlayCallModel(PlayCallModelConfig(enabled=True, artifacts_dir=str(tmp_path)))

    context = model.build_context(
        team="KC",
        opponent="BUF",
        home_team="KC",
        away_team="BUF",
        target_season=2024,
        week=1,
        is_home=True,
    )

    assert context is not None
    assert context.pass_probability(make_state()) == pytest.approx(0.95)


def test_non_finite_coefficients_return_none_probability(tmp_path):
    write_artifact(
        tmp_path / "play_call_model_2024.json",
        coefficients={"intercept": "nan", "down_3": 4.0},
    )
    model = PlayCallModel(PlayCallModelConfig(enabled=True, artifacts_dir=str(tmp_path)))
    context = model.build_context(
        team="KC",
        opponent="BUF",
        home_team="KC",
        away_team="BUF",
        target_season=2024,
        week=1,
        is_home=True,
    )

    assert context is not None
    assert context.pass_probability(make_state()) is None
```

- [ ] **Step 2: Run runtime tests and verify they fail**

Run:

```bash
uv run pytest tests/test_data/test_play_call_model/test_runtime.py -v
```

Expected: FAIL because `PlayCallModel` is not exported and `runtime.py` does not exist.

- [ ] **Step 3: Implement runtime loader**

Create `src/fantasy_sim/data/play_call_model/runtime.py`:

```python
"""Artifact loading for learned pass/run play calling."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fantasy_sim.data.play_call_model.models import (
    DEFAULT_ARTIFACT_DIR,
    PLAY_CALL_MODEL_SCHEMA_VERSION,
    PLAY_CALL_MODEL_TYPE,
    PlayCallContext,
    PlayCallModelConfig,
)

logger = logging.getLogger(__name__)


class PlayCallModel:
    """Loads per-season learned play-call artifacts for runtime use."""

    def __init__(self, config: PlayCallModelConfig) -> None:
        self._config = config
        self._artifacts_dir = (
            Path(config.artifacts_dir)
            if config.artifacts_dir is not None
            else DEFAULT_ARTIFACT_DIR
        )
        self._cache: dict[int, dict | None] = {}

    def build_context(
        self,
        *,
        team: str,
        opponent: str,
        home_team: str,
        away_team: str,
        target_season: int,
        week: int,
        is_home: bool,
        spread_line: float | None = None,
        total_line: float | None = None,
        implied_team_total: float | None = None,
        team_prior_pass_rate: float = 0.57,
        opponent_prior_pass_rate_allowed: float = 0.57,
    ) -> PlayCallContext | None:
        if not self._config.enabled:
            return None
        artifact = self._load_artifact(target_season)
        if artifact is None:
            return None
        feature_names = tuple(str(name) for name in artifact.get("feature_names", ()))
        raw_coefficients = artifact.get("coefficients", {})
        try:
            coefficients = {
                str(name): float(value)
                for name, value in raw_coefficients.items()
            }
        except (AttributeError, TypeError, ValueError):
            logger.warning("Invalid play-call coefficients for season %s", target_season)
            return None
        if not feature_names or not coefficients:
            return None
        clamp_raw = artifact.get("probability_clamp", self._config.probability_clamp)
        try:
            probability_clamp = (float(clamp_raw[0]), float(clamp_raw[1]))
        except (TypeError, ValueError, IndexError):
            probability_clamp = self._config.probability_clamp
        return PlayCallContext(
            coefficients=coefficients,
            feature_names=feature_names,
            team=team,
            opponent=opponent,
            home_team=home_team,
            away_team=away_team,
            is_home=is_home,
            target_season=target_season,
            week=week,
            spread_line=spread_line,
            total_line=total_line,
            implied_team_total=implied_team_total,
            team_prior_pass_rate=team_prior_pass_rate,
            opponent_prior_pass_rate_allowed=opponent_prior_pass_rate_allowed,
            probability_clamp=probability_clamp,
        )

    def _load_artifact(self, target_season: int) -> dict | None:
        if target_season in self._cache:
            return self._cache[target_season]
        path = self._artifacts_dir / f"play_call_model_{target_season}.json"
        if not path.exists():
            logger.info("Play-call model artifact missing: %s", path)
            self._cache[target_season] = None
            return None
        try:
            artifact = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Unable to load play-call model artifact %s: %s", path, exc)
            self._cache[target_season] = None
            return None
        if artifact.get("schema_version") != PLAY_CALL_MODEL_SCHEMA_VERSION:
            logger.warning("Unsupported play-call model artifact schema: %s", path)
            self._cache[target_season] = None
            return None
        if artifact.get("model_type") != PLAY_CALL_MODEL_TYPE:
            logger.warning("Unsupported play-call model type: %s", path)
            self._cache[target_season] = None
            return None
        self._cache[target_season] = artifact
        return artifact
```

- [ ] **Step 4: Export runtime model**

Modify `src/fantasy_sim/data/play_call_model/__init__.py`:

```python
from fantasy_sim.data.play_call_model.runtime import PlayCallModel
```

Add `"PlayCallModel"` to `__all__`.

- [ ] **Step 5: Run runtime tests and verify pass**

Run:

```bash
uv run pytest tests/test_data/test_play_call_model/test_runtime.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit runtime loader**

```bash
git add \
  src/fantasy_sim/data/play_call_model/__init__.py \
  src/fantasy_sim/data/play_call_model/runtime.py \
  tests/test_data/test_play_call_model/test_runtime.py
git commit -m "feat: load learned play-call artifacts"
```

---

### Task 5: Engine Selection Boundary

**Files:**
- Modify: `src/fantasy_sim/engine/types.py`
- Modify: `src/fantasy_sim/engine/play_caller.py`
- Modify: `tests/test_engine/test_play_caller.py`
- Modify: `tests/test_engine/test_types.py`

- [ ] **Step 1: Write failing engine tests**

Add to `tests/test_engine/test_play_caller.py`:

```python
class FixedPlayCallContext:
    def __init__(self, probability):
        self.probability = probability

    def pass_probability(self, state, script=None):
        return self.probability


class TestLearnedPlayCallSelection:
    def test_learned_context_wins_when_valid(self):
        rng = np.random.default_rng(42)
        state = make_state()
        play_calling = make_play_calling(pass_rate=0.0)
        context = FixedPlayCallContext(1.0)

        results = [
            select_play_type(
                state,
                play_calling,
                rng,
                play_call_context=context,
            )
            for _ in range(25)
        ]

        assert all(result == "pass" for result in results)

    def test_empirical_fallback_when_learned_context_returns_none(self):
        rng = np.random.default_rng(42)
        state = make_state()
        play_calling = make_play_calling(pass_rate=1.0)
        context = FixedPlayCallContext(None)

        results = [
            select_play_type(
                state,
                play_calling,
                rng,
                play_call_context=context,
            )
            for _ in range(25)
        ]

        assert all(result == "pass" for result in results)

    def test_script_pass_rate_factor_is_skipped_for_learned_context(self):
        rng = np.random.default_rng(42)
        state = make_state()
        play_calling = make_play_calling(pass_rate=0.5)
        script = RuntimeGameScript(pass_rate_factor=1.35)
        context = FixedPlayCallContext(0.0)

        results = [
            select_play_type(
                state,
                play_calling,
                rng,
                script=script,
                play_call_context=context,
            )
            for _ in range(25)
        ]

        assert all(result == "run" for result in results)
```

Add to `tests/test_engine/test_types.py` in `TestTeamDistributions`:

```python
    def test_team_distributions_defaults_play_call_context_to_none(self):
        td = TeamDistributions(
            play_calling=PlayCallingDist(team="KC", distributions={}),
            play_outcomes=PlayOutcomeDist(distributions={}, defaults={"pass": np.array([5]), "run": np.array([3])}),
            turnover_rates=TurnoverRates(team="KC", int_rate=0.025, fumble_rate=0.01, sack_rate=0.06, sack_fumble_rate=0.10),
            kicking=KickingModel(fg_make_rate={"0_39": 0.95, "40_49": 0.82, "50_plus": 0.65}, xp_rate=0.94),
            drive_start=DriveStartModel(touchback_rate=0.55, touchback_yardline=75, return_yardlines=np.array([72, 78])),
        )

        assert td.play_call_context is None
```

- [ ] **Step 2: Run engine tests and verify they fail**

Run:

```bash
uv run pytest tests/test_engine/test_play_caller.py::TestLearnedPlayCallSelection tests/test_engine/test_types.py::TestTeamDistributions::test_team_distributions_defaults_play_call_context_to_none -v
```

Expected: FAIL because `select_play_type()` has no `play_call_context` argument and `TeamDistributions` has no `play_call_context`.

- [ ] **Step 3: Add engine protocol and distribution field**

Modify `src/fantasy_sim/engine/types.py`:

```python
class PlayCallContextProtocol(Protocol):
    """Pass/run play-call interface used by the engine."""

    def pass_probability(
        self,
        state: "GameState",
        script: "RuntimeGameScript | None" = None,
    ) -> float | None:
        ...
```

Add the field to `TeamDistributions`:

```python
    play_call_context: PlayCallContextProtocol | None = None
```

- [ ] **Step 4: Update `select_play_type()` learned boundary**

Modify imports and signature in `src/fantasy_sim/engine/play_caller.py`:

```python
from fantasy_sim.engine.types import (
    GameState,
    PlayCallContextProtocol,
)
```

```python
def select_play_type(
    state: GameState,
    play_calling: PlayCallingDist,
    rng: np.random.Generator,
    script: RuntimeGameScript | None = None,
    play_call_context: PlayCallContextProtocol | None = None,
) -> str:
```

Replace the probability block with:

```python
    probs: dict[str, float] | None = None
    if play_call_context is not None:
        learned_pass = play_call_context.pass_probability(state, script=script)
        if learned_pass is not None and np.isfinite(learned_pass):
            learned_pass = float(np.clip(learned_pass, 0.0, 1.0))
            probs = {"pass": learned_pass, "run": 1.0 - learned_pass}

    if probs is None:
        probs = play_calling.get_probs(bucket)
        if script is not None and script.pass_rate_factor != 1.0:
            probs = apply_pass_rate_factor(probs, script.pass_rate_factor)
```

- [ ] **Step 5: Wire game simulation call site**

Modify `src/fantasy_sim/engine/game_sim.py` where `select_play_type()` is called:

```python
        play_type = select_play_type(
            state,
            off_dists.play_calling,
            rng,
            script=script,
            play_call_context=off_dists.play_call_context,
        )
```

- [ ] **Step 6: Run engine tests and verify pass**

Run:

```bash
uv run pytest tests/test_engine/test_play_caller.py tests/test_engine/test_types.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit engine boundary**

```bash
git add \
  src/fantasy_sim/engine/types.py \
  src/fantasy_sim/engine/play_caller.py \
  src/fantasy_sim/engine/game_sim.py \
  tests/test_engine/test_play_caller.py \
  tests/test_engine/test_types.py
git commit -m "feat: route play calls through learned context"
```

---

### Task 6: GameContextBuilder Runtime Wiring

**Files:**
- Modify: `src/fantasy_sim/data/game_context.py`
- Modify: `tests/test_data/test_game_context.py`

- [ ] **Step 1: Write failing GameContextBuilder tests**

Add to `tests/test_data/test_game_context.py`:

```python
    def test_play_call_model_created_when_enabled(self, tmp_path):
        from fantasy_sim.data.play_call_model import PlayCallModelConfig

        builder = GameContextBuilder(
            cache_dir=tmp_path / "cache",
            play_call_model_config=PlayCallModelConfig(enabled=True, artifacts_dir=str(tmp_path)),
        )

        assert builder._play_call_model is not None

    def test_play_call_context_attached_when_artifact_exists(
        self, tmp_path, expanded_pbp, sample_rosters
    ):
        import json
        from fantasy_sim.data.play_call_model import (
            PLAY_CALL_MODEL_SCHEMA_VERSION,
            PLAY_CALL_MODEL_TYPE,
            PlayCallModelConfig,
        )

        artifact_dir = tmp_path / "artifacts"
        artifact_dir.mkdir()
        (artifact_dir / "play_call_model_2024.json").write_text(
            json.dumps(
                {
                    "schema_version": PLAY_CALL_MODEL_SCHEMA_VERSION,
                    "model_type": PLAY_CALL_MODEL_TYPE,
                    "target_season": 2024,
                    "feature_names": ["intercept"],
                    "coefficients": {"intercept": 0.0},
                    "probability_clamp": [0.05, 0.95],
                }
            )
        )
        builder = GameContextBuilder(
            cache_dir=tmp_path / "cache",
            play_call_model_config=PlayCallModelConfig(
                enabled=True,
                artifacts_dir=str(artifact_dir),
            ),
        )

        home_dists, away_dists, _, _ = builder.build_game(
            home_team="KC",
            away_team="BUF",
            pbp=expanded_pbp,
            rosters=sample_rosters,
            training_seasons=[2024],
            target_season=2024,
            week=1,
        )

        assert home_dists.play_call_context is not None
        assert away_dists.play_call_context is not None

    def test_vegas_pass_rate_is_not_skipped_when_artifact_missing(
        self, tmp_path, expanded_pbp, sample_rosters
    ):
        from fantasy_sim.data.play_call_model import PlayCallModelConfig
        from fantasy_sim.data.vegas.models import VegasContext

        builder = GameContextBuilder(
            cache_dir=tmp_path / "cache",
            play_call_model_config=PlayCallModelConfig(
                enabled=True,
                artifacts_dir=str(tmp_path / "missing"),
            ),
        )
        dists = builder.build_team_distributions(
            "KC",
            pbp=expanded_pbp,
            rosters=sample_rosters,
            training_seasons=[2024],
            target_season=2024,
            week=1,
        )
        old_pass = dists.play_calling.default["pass"]

        builder._apply_vegas(
            dists,
            VegasContext(team="KC", volume_factor=1.0, pass_rate_factor=1.10),
            apply_pass_rate=True,
        )

        assert dists.play_calling.default["pass"] > old_pass
```

- [ ] **Step 2: Run GameContextBuilder tests and verify they fail**

Run:

```bash
uv run pytest tests/test_data/test_game_context.py::TestGameContextBuilder::test_play_call_model_created_when_enabled tests/test_data/test_game_context.py::TestGameContextBuilder::test_play_call_context_attached_when_artifact_exists tests/test_data/test_game_context.py::TestGameContextBuilder::test_vegas_pass_rate_is_not_skipped_when_artifact_missing -v
```

Expected: FAIL because `GameContextBuilder` has no `play_call_model_config` and `_apply_vegas()` has no `apply_pass_rate` argument.

- [ ] **Step 3: Add constructor wiring**

Modify imports in `src/fantasy_sim/data/game_context.py`:

```python
from fantasy_sim.data.play_call_model import (
    PlayCallModel,
    PlayCallModelConfig,
)
```

Add constructor parameter:

```python
        play_call_model_config: PlayCallModelConfig | None = None,
```

Near the target-selection setup, add:

```python
        self._play_call_model_config = (
            play_call_model_config or PlayCallModelConfig(enabled=False)
        )
        self._play_call_model = None
        if self._play_call_model_config.enabled:
            self._play_call_model = PlayCallModel(self._play_call_model_config)
            logger.info("Play-call model enabled")
```

- [ ] **Step 4: Allow Vegas pace without pass-rate modifier**

Modify `_apply_vegas()` signature:

```python
    def _apply_vegas(
        dists: TeamDistributions,
        ctx: VegasContext,
        *,
        apply_pass_rate: bool = True,
    ) -> None:
```

Change the pass-rate condition:

```python
        if apply_pass_rate and ctx.pass_rate_factor != 1.0:
```

- [ ] **Step 5: Build learned contexts before Vegas pass-rate application**

Add this helper method to `GameContextBuilder` so the learned model receives
team-perspective market features even though it skips the current Vegas
pass-rate multiplier:

```python
    def _play_call_market_features(
        self,
        *,
        home_team: str,
        away_team: str,
        target_season: int,
        week: int,
    ) -> tuple[dict[str, float | None], dict[str, float | None]]:
        neutral = {
            "spread_line": None,
            "total_line": None,
            "implied_team_total": None,
        }
        try:
            schedule_df = self.loader.load_schedules([target_season])
        except Exception:
            return dict(neutral), dict(neutral)
        if schedule_df is None or schedule_df.is_empty():
            return dict(neutral), dict(neutral)
        game_rows = schedule_df.filter(
            (pl.col("home_team") == home_team)
            & (pl.col("away_team") == away_team)
            & (pl.col("week") == week)
            & (pl.col("season") == target_season)
        )
        if game_rows.is_empty():
            return dict(neutral), dict(neutral)
        row = game_rows.row(0, named=True)
        spread_line = row.get("spread_line")
        total_line = row.get("total_line")
        if spread_line is None or total_line is None:
            return dict(neutral), dict(neutral)
        spread = float(spread_line)
        total = float(total_line)
        home_implied = total / 2.0 + spread / 2.0
        away_implied = total / 2.0 - spread / 2.0
        return (
            {
                "spread_line": spread,
                "total_line": total,
                "implied_team_total": home_implied,
            },
            {
                "spread_line": -spread,
                "total_line": total,
                "implied_team_total": away_implied,
            },
        )
```

In `build_game()`, after rosters are built and before the Vegas adjustment block, add:

```python
        home_play_call_context = None
        away_play_call_context = None
        if self._play_call_model is not None and target_season is not None:
            runtime_week = int(week or 0)
            home_market, away_market = self._play_call_market_features(
                home_team=home_team,
                away_team=away_team,
                target_season=target_season,
                week=runtime_week,
            )
            home_play_call_context = self._play_call_model.build_context(
                team=home_team,
                opponent=away_team,
                home_team=home_team,
                away_team=away_team,
                target_season=target_season,
                week=runtime_week,
                is_home=True,
                **home_market,
            )
            away_play_call_context = self._play_call_model.build_context(
                team=away_team,
                opponent=home_team,
                home_team=home_team,
                away_team=away_team,
                target_season=target_season,
                week=runtime_week,
                is_home=False,
                **away_market,
            )
            home_dists.play_call_context = home_play_call_context
            away_dists.play_call_context = away_play_call_context
```

Update the Vegas block:

```python
            self._apply_vegas(
                home_dists,
                home_vegas_ctx,
                apply_pass_rate=home_play_call_context is None,
            )
            self._apply_vegas(
                away_dists,
                away_vegas_ctx,
                apply_pass_rate=away_play_call_context is None,
            )
```

- [ ] **Step 6: Run GameContextBuilder tests and verify pass**

Run:

```bash
uv run pytest tests/test_data/test_game_context.py::TestGameContextBuilder::test_play_call_model_created_when_enabled tests/test_data/test_game_context.py::TestGameContextBuilder::test_play_call_context_attached_when_artifact_exists tests/test_data/test_game_context.py::TestGameContextBuilder::test_vegas_pass_rate_is_not_skipped_when_artifact_missing -v
```

Expected: PASS.

- [ ] **Step 7: Commit builder wiring**

```bash
git add src/fantasy_sim/data/game_context.py tests/test_data/test_game_context.py
git commit -m "feat: attach learned play-call contexts"
```

---

### Task 7: Propagate Config Through CLI, Backtester, And Parallel Validation

**Files:**
- Modify: `src/fantasy_sim/cli.py`
- Modify: `src/fantasy_sim/validation/backtester.py`
- Modify: `src/fantasy_sim/validation/parallel.py`
- Modify: `scripts/validate.py`
- Modify: tests that instantiate affected classes if failures surface

- [ ] **Step 1: Run focused integration tests to expose missing propagation**

Run:

```bash
uv run pytest tests/test_validation/test_config.py tests/test_cli.py::TestCliConfig tests/test_validation/test_backtester_verification.py -v
```

Expected: may FAIL where `GameContextBuilder` construction does not pass `play_call_model_config`. Use failures to locate exact call sites.

- [ ] **Step 2: Update CLI builder creation**

In `src/fantasy_sim/cli.py`, add import:

```python
from fantasy_sim.data.play_call_model import load_play_call_model_config
```

Where defaults are loaded and other engine configs are created, add:

```python
    play_call_model_config = load_play_call_model_config(defaults)
```

Pass it into each `GameContextBuilder(...)` creation:

```python
        play_call_model_config=play_call_model_config,
```

Only pass the config object when enabled if the local code path follows that pattern:

```python
        play_call_model_config=(
            play_call_model_config if play_call_model_config.enabled else None
        ),
```

- [ ] **Step 3: Update Backtester constructor**

In `src/fantasy_sim/validation/backtester.py`, import the config type:

```python
from fantasy_sim.data.play_call_model import PlayCallModelConfig
```

Add constructor parameter:

```python
        play_call_model_config: PlayCallModelConfig | None = None,
```

Store it:

```python
        self._play_call_model_config = play_call_model_config
```

Pass it to `GameContextBuilder(...)`:

```python
            play_call_model_config=self._play_call_model_config,
```

- [ ] **Step 4: Update parallel validation builder creation**

In `src/fantasy_sim/validation/parallel.py`, add the type import under `TYPE_CHECKING`:

```python
    from fantasy_sim.data.play_call_model import PlayCallModelConfig
```

Add `play_call_model_config: "PlayCallModelConfig | None" = None` to every helper that already accepts `target_selection_config`.

Pass it through each `GameContextBuilder(...)` call:

```python
        play_call_model_config=play_call_model_config,
```

Pass it through worker argument tuples next to `target_selection_config`.

- [ ] **Step 5: Update `scripts/validate.py` arm config usage**

Where `target_selection_config=arm_b_configs.get("target_selection_config")` is passed to validation helpers, add:

```python
                play_call_model_config=arm_b_configs.get("play_call_model_config"),
```

Do the same for arm A and arm B code paths.

- [ ] **Step 6: Run propagation tests**

Run:

```bash
uv run pytest tests/test_validation/test_config.py tests/test_cli.py tests/test_validation -q
```

Expected: PASS.

- [ ] **Step 7: Commit propagation**

```bash
git add \
  src/fantasy_sim/cli.py \
  src/fantasy_sim/validation/backtester.py \
  src/fantasy_sim/validation/parallel.py \
  scripts/validate.py
git commit -m "feat: propagate play-call model config"
```

---

### Task 8: Validation Coverage Reporting

**Files:**
- Modify: `src/fantasy_sim/validation/coverage.py`
- Modify: `tests/test_validation/test_coverage.py`

- [ ] **Step 1: Write failing coverage tests**

Add helper imports to `tests/test_validation/test_coverage.py`:

```python
from fantasy_sim.data.play_call_model.models import (
    PLAY_CALL_MODEL_SCHEMA_VERSION,
    PLAY_CALL_MODEL_TYPE,
)
```

Add helper:

```python
def _write_play_call_model_artifact(
    path: Path,
    *,
    schema_version: int = PLAY_CALL_MODEL_SCHEMA_VERSION,
    model_type: str = PLAY_CALL_MODEL_TYPE,
    coefficients: dict[str, object] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": schema_version,
                "model_type": model_type,
                "target_season": 2024,
                "feature_names": ["intercept"],
                "coefficients": coefficients if coefficients is not None else {"intercept": 0.0},
            }
        )
    )
```

Add tests:

```python
def test_play_call_model_reports_disabled_by_default():
    coverage = collect_signal_coverage(_default_engine_configs(), [2023, 2024])

    assert coverage["play_call_model"] == SignalCoverage(
        enabled=False,
        status="disabled",
        covered_seasons=[],
        missing_seasons=[],
        note="Requires play_call_model_<season>.json artifacts fitted from prior-season PBP pass/run labels",
    )


def test_play_call_model_reports_partial_artifact_coverage(tmp_path):
    artifact_dir = tmp_path / "play_call"
    _write_play_call_model_artifact(artifact_dir / "play_call_model_2024.json")
    config = {
        "play_call_model": {
            "enabled": True,
            "artifacts_dir": str(artifact_dir),
        }
    }

    coverage = collect_signal_coverage(config, [2023, 2024])

    assert coverage["play_call_model"] == SignalCoverage(
        enabled=True,
        status="partial",
        covered_seasons=[2024],
        missing_seasons=[2023],
        note="Requires play_call_model_<season>.json artifacts fitted from prior-season PBP pass/run labels",
    )
```

- [ ] **Step 2: Run coverage tests and verify they fail**

Run:

```bash
uv run pytest tests/test_validation/test_coverage.py::test_play_call_model_reports_disabled_by_default tests/test_validation/test_coverage.py::test_play_call_model_reports_partial_artifact_coverage -v
```

Expected: FAIL because `collect_signal_coverage()` does not report `play_call_model`.

- [ ] **Step 3: Add coverage helpers**

In `src/fantasy_sim/validation/coverage.py`, import play-call constants:

```python
from fantasy_sim.data.play_call_model.models import (
    PLAY_CALL_MODEL_SCHEMA_VERSION,
    PLAY_CALL_MODEL_TYPE,
)
```

Add a resolver:

```python
def _resolve_play_call_model_artifacts_path(config: object) -> Path:
    play_call_config = _config_section(config, "play_call_model_config")
    if play_call_config is None:
        play_call_config = _config_section(config, "play_call_model")
    artifacts_dir = (
        _config_get(play_call_config, "artifacts_dir", default=None)
        if play_call_config is not None
        else None
    )
    from fantasy_sim.data.play_call_model.models import DEFAULT_ARTIFACT_DIR

    if artifacts_dir is not None:
        return _path_or_default(artifacts_dir, DEFAULT_ARTIFACT_DIR)
    return DEFAULT_ARTIFACT_DIR
```

Add an artifact validator:

```python
def _play_call_model_artifact_is_valid(path: Path) -> bool:
    try:
        artifact = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(artifact, Mapping):
        return False
    if artifact.get("schema_version") != PLAY_CALL_MODEL_SCHEMA_VERSION:
        return False
    if artifact.get("model_type") != PLAY_CALL_MODEL_TYPE:
        return False
    feature_names = artifact.get("feature_names")
    coefficients = artifact.get("coefficients")
    return isinstance(feature_names, list) and bool(feature_names) and isinstance(coefficients, Mapping)
```

- [ ] **Step 4: Add coverage signal**

Inside `collect_signal_coverage()`, compute:

```python
    play_call_model_enabled = _signal_enabled(
        config,
        ("play_call_model_config", "play_call_model"),
        ("play_call_model",),
    )
    play_call_model_artifacts_path = _resolve_play_call_model_artifacts_path(config)
    play_call_model_artifact_paths: dict[int, Path] = {
        season: play_call_model_artifacts_path / f"play_call_model_{season}.json"
        for season in seasons
    }
```

Add to the returned coverage dict:

```python
        "play_call_model": _build_signal(
            enabled=play_call_model_enabled,
            seasons=seasons,
            covered_seasons=[
                season
                for season, path in play_call_model_artifact_paths.items()
                if path.exists() and _play_call_model_artifact_is_valid(path)
            ],
            note=(
                "Requires play_call_model_<season>.json artifacts fitted from "
                "prior-season PBP pass/run labels"
            ),
        ),
```

- [ ] **Step 5: Run coverage tests and verify pass**

Run:

```bash
uv run pytest tests/test_validation/test_coverage.py::test_play_call_model_reports_disabled_by_default tests/test_validation/test_coverage.py::test_play_call_model_reports_partial_artifact_coverage -v
```

Expected: PASS.

- [ ] **Step 6: Commit coverage reporting**

```bash
git add src/fantasy_sim/validation/coverage.py tests/test_validation/test_coverage.py
git commit -m "feat: report play-call model coverage"
```

---

### Task 9: End-To-End Smoke And Validation Commands

**Files:**
- No source files unless earlier tests reveal missed call sites.

- [ ] **Step 1: Run the focused unit suite**

Run:

```bash
uv run pytest \
  tests/test_data/test_play_call_model \
  tests/test_scripts/test_fit_play_call_model.py \
  tests/test_engine/test_play_caller.py \
  tests/test_data/test_game_context.py \
  tests/test_validation/test_config.py \
  tests/test_validation/test_coverage.py \
  -v
```

Expected: PASS.

- [ ] **Step 2: Run the full test suite**

Run:

```bash
uv run pytest tests/ -v
```

Expected: PASS.

- [ ] **Step 3: Fit smoke artifacts**

Run:

```bash
uv run python scripts/fit_play_call_model.py \
  --test-seasons 2022 2023 2024 \
  --min-source-season 2018 \
  --training-years 4 \
  --output-dir results/play_call_model/smoke_v1
```

Expected: writes `play_call_model_2022.json`, `play_call_model_2023.json`, and `play_call_model_2024.json` with `converged=True` or a clearly printed optimizer status for each artifact.

- [ ] **Step 4: Run 50-sim marginal validation**

Run:

```bash
uv run python scripts/validate.py \
  --baseline defaults \
  --sims 50 \
  --set play_call_model.enabled=true \
  --set play_call_model.artifacts_dir=results/play_call_model/smoke_v1 \
  --label play-call-model-s50
```

Expected: validation completes, appends a ledger row, and coverage reports `play_call_model` as full or explicitly partial. Use this as smoke evidence only.

- [ ] **Step 5: Decide whether to run 200-sim validation**

Proceed only if the 50-sim run is not clearly damaging:

- average rank-correlation delta is not materially negative
- weekly MAE is not materially worse
- QB and WR are not both worse on rank correlation and MAE
- stat KS readout does not show obvious WR receiving yards, QB passing yards, RB rushing yards, or TE receiving yards damage

Run:

```bash
uv run python scripts/validate.py \
  --baseline defaults \
  --sims 200 \
  --set play_call_model.enabled=true \
  --set play_call_model.artifacts_dir=results/play_call_model/smoke_v1 \
  --label play-call-model-s200
```

Expected: validation completes and appends a decision-grade ledger row.

- [ ] **Step 6: Record verdict**

If the 200-sim run clears the gate from the spec, create a short verdict note in `docs/superpowers/handoff/` or append to the active hypothesis doc only if the user asks for documentation updates. The gate is:

- average rank-correlation delta across QB/RB/WR/TE `>= +0.0030`
- weekly MAE delta `<= -0.025`
- QB and WR do not regress on both weekly rank correlation and weekly MAE
- no obvious stat KS damage on WR receiving yards, QB passing yards, RB rushing yards, or TE receiving yards
- simulated pass rate, rush rate, total plays, and position opportunity splits remain sane

- [ ] **Step 7: Commit validation artifacts only if approved**

Do not commit `results/play_call_model/smoke_v1` or ledger changes unless the user explicitly wants validation evidence committed.

If approved:

```bash
git add results/play_call_model/smoke_v1 results/ab_ledger.json
git commit -m "chore: record learned play-call validation evidence"
```

---

## Self-Review

Spec coverage:

- Intended change: Tasks 1, 4, 5, and 6 add the off-by-default learned play-call node and runtime selection boundary.
- Runtime/data boundary: Tasks 2, 3, 4, 5, and 6 keep the model limited to pass/run selection.
- Required data inputs: Task 3 uses nflverse PBP pass/run labels and existing PBP fields.
- Implementation shape: Tasks 1 through 8 cover config, package, fitter, runtime, engine, builder, propagation, and coverage reporting.
- Validation commands and gate: Task 9 contains smoke, decision, and verdict steps.
- Risks and fallback/default behavior: Tasks 4, 5, 6, and 8 test missing artifacts, invalid artifacts, `None` probabilities, empirical fallback, and coverage reporting.

Type consistency:

- Config type is `PlayCallModelConfig`.
- Runtime model is `PlayCallModel`.
- Runtime context is `PlayCallContext`.
- Distribution field is `play_call_context`.
- Engine protocol method is `pass_probability(state, script=None)`.
- Artifact filename is `play_call_model_<season>.json`.

Scope check:

- This plan implements only learned pass/run play calling. It does not replace target selection, rusher selection, scramble/sack/turnover logic, yards, TD behavior, dynamic blend, or residual calibration.

# QB Scramble Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an off-by-default learned QB scramble-probability model that adjusts the existing passer `scramble_rate` with a bounded, artifact-backed context model.

**Architecture:** The new `fantasy_sim.data.qb_rushing` package owns config parsing, feature building, prior-season fitting, artifact validation, and runtime `QbScrambleContext` construction. `GameContextBuilder` attaches a per-team `qb_scramble_context` to `TeamDistributions`, and `_resolve_pass()` asks that context for an effective scramble probability before the existing scramble roll. The slice does not change pass/run play calling, designed QB run selection, scramble-yard sampling, or post-sim projection layers.

**Tech Stack:** Python 3.12, polars, numpy, scipy.optimize, pytest, uv, existing validation config overrides, existing validation coverage ledger.

---

## File Structure

- Create `src/fantasy_sim/data/qb_rushing/__init__.py`: public exports for config, constants, runtime model, context, and training helpers.
- Create `src/fantasy_sim/data/qb_rushing/config.py`: load and validate `qb_rushing.scramble` config.
- Create `src/fantasy_sim/data/qb_rushing/models.py`: constants, config dataclasses, feature helpers, and runtime context.
- Create `src/fantasy_sim/data/qb_rushing/training.py`: temporal source-season selection, prior computation, labeled examples, and offset-logistic fitting.
- Create `src/fantasy_sim/data/qb_rushing/runtime.py`: strict artifact loading and per-team context construction.
- Create `scripts/fit_qb_scramble_model.py`: writes one JSON artifact per target season.
- Create `tests/test_data/test_qb_rushing/`: config, model, training, and runtime tests.
- Create `tests/test_scripts/test_fit_qb_scramble_model.py`: script helper tests.
- Modify `config/defaults.yaml`: add disabled `qb_rushing.scramble` config.
- Modify `src/fantasy_sim/validation/config.py`: load and return `qb_rushing_config`.
- Modify `src/fantasy_sim/engine/types.py`: add `QbScrambleContextProtocol` and `TeamDistributions.qb_scramble_context`.
- Modify `src/fantasy_sim/engine/play_resolver.py`: thread `qb_scramble_context` into `_resolve_pass()` and use it only for the scramble gate.
- Modify `src/fantasy_sim/engine/game_sim.py`: pass `off_dists.qb_scramble_context` into `resolve_play()`.
- Modify `src/fantasy_sim/data/game_context.py`: construct `QbScrambleModel` and attach team contexts when artifacts are valid.
- Modify `src/fantasy_sim/cli.py`, `src/fantasy_sim/validation/backtester.py`, and `src/fantasy_sim/validation/parallel.py`: propagate `qb_rushing_config`.
- Modify `src/fantasy_sim/validation/coverage.py`: report `qb_rushing.scramble` artifact coverage.
- Modify `tests/test_validation/test_config.py`, `tests/test_engine/test_play_resolver.py`, `tests/test_engine/test_game_sim.py`, `tests/test_data/test_game_context.py`, `tests/test_validation/test_parallel.py`, and `tests/test_validation/test_coverage.py`: integration coverage.
- Review `AGENTS.md` after implementation and validation. Add the off-by-default QB scramble model to Current State only when the code exists.

---

### Task 1: Config, Public Package, And Defaults

**Files:**
- Create: `src/fantasy_sim/data/qb_rushing/__init__.py`
- Create: `src/fantasy_sim/data/qb_rushing/models.py`
- Create: `src/fantasy_sim/data/qb_rushing/config.py`
- Create: `tests/test_data/test_qb_rushing/__init__.py`
- Create: `tests/test_data/test_qb_rushing/test_config.py`
- Modify: `config/defaults.yaml`
- Modify: `src/fantasy_sim/validation/config.py`
- Modify: `tests/test_validation/test_config.py`

- [ ] **Step 1: Write failing config tests**

Create `tests/test_data/test_qb_rushing/__init__.py` as an empty file.

Create `tests/test_data/test_qb_rushing/test_config.py`:

```python
import pytest

from fantasy_sim.data.qb_rushing import load_qb_rushing_config


def test_missing_config_is_disabled():
    config = load_qb_rushing_config({})

    assert config.scramble.enabled is False
    assert config.scramble.artifacts_dir is None
    assert config.scramble.factor_clamp == (0.50, 1.75)
    assert config.scramble.probability_clamp == (0.0, 0.25)
    assert config.scramble.min_examples == 500


def test_loads_enabled_config_values():
    config = load_qb_rushing_config(
        {
            "qb_rushing": {
                "scramble": {
                    "enabled": True,
                    "artifacts_dir": "results/qb_rushing/scramble/test",
                    "factor_clamp": [0.75, 1.40],
                    "probability_clamp": [0.01, 0.20],
                    "min_examples": 250,
                }
            }
        }
    )

    assert config.scramble.enabled is True
    assert config.scramble.artifacts_dir == "results/qb_rushing/scramble/test"
    assert config.scramble.factor_clamp == (0.75, 1.40)
    assert config.scramble.probability_clamp == (0.01, 0.20)
    assert config.scramble.min_examples == 250


@pytest.mark.parametrize(
    "clamp",
    [[0.50], [1.75, 0.50], [-0.01, 1.75], [0.50, float("inf")]],
)
def test_invalid_factor_clamp_raises(clamp):
    with pytest.raises(ValueError, match="qb_rushing\.scramble\.factor_clamp"):
        load_qb_rushing_config(
            {"qb_rushing": {"scramble": {"factor_clamp": clamp}}}
        )


@pytest.mark.parametrize(
    "clamp",
    [[0.0], [0.25, 0.0], [-0.01, 0.25], [0.0, 1.01]],
)
def test_invalid_probability_clamp_raises(clamp):
    with pytest.raises(ValueError, match="qb_rushing\.scramble\.probability_clamp"):
        load_qb_rushing_config(
            {"qb_rushing": {"scramble": {"probability_clamp": clamp}}}
        )


def test_invalid_min_examples_raises():
    with pytest.raises(ValueError, match="qb_rushing\.scramble\.min_examples"):
        load_qb_rushing_config(
            {"qb_rushing": {"scramble": {"min_examples": 0}}}
        )
```

Extend `tests/test_validation/test_config.py` in `TestBuildEngineConfigs`:

```python
    def test_defaults_keep_qb_rushing_disabled(self):
        defaults = load_defaults()

        configs = build_engine_configs(defaults)

        assert "qb_rushing_config" in configs
        assert configs["qb_rushing_config"] is None

    def test_enabled_qb_rushing_config_is_built(self):
        defaults = load_defaults()
        overridden = apply_overrides(
            defaults,
            [
                "qb_rushing.scramble.enabled=true",
                "qb_rushing.scramble.artifacts_dir=results/qb_rushing/scramble/test",
                "qb_rushing.scramble.factor_clamp=[0.75,1.40]",
                "qb_rushing.scramble.probability_clamp=[0.01,0.20]",
            ],
        )

        configs = build_engine_configs(overridden)

        assert configs["qb_rushing_config"] is not None
        assert configs["qb_rushing_config"].scramble.artifacts_dir == "results/qb_rushing/scramble/test"
        assert configs["qb_rushing_config"].scramble.factor_clamp == (0.75, 1.40)
        assert configs["qb_rushing_config"].scramble.probability_clamp == (0.01, 0.20)
```

- [ ] **Step 2: Run config tests and verify they fail**

Run:

```bash
uv run pytest tests/test_data/test_qb_rushing/test_config.py tests/test_validation/test_config.py::TestBuildEngineConfigs::test_defaults_keep_qb_rushing_disabled tests/test_validation/test_config.py::TestBuildEngineConfigs::test_enabled_qb_rushing_config_is_built -v
```

Expected: FAIL because `fantasy_sim.data.qb_rushing` does not exist.

- [ ] **Step 3: Add config dataclasses and loader**

Create `src/fantasy_sim/data/qb_rushing/models.py`:

```python
"""Models and feature helpers for QB rushing layers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

QB_SCRAMBLE_SCHEMA_VERSION = 1
QB_SCRAMBLE_MODEL_TYPE = "offset_logistic_qb_scramble_v1"
DEFAULT_ARTIFACT_DIR = (
    Path(__file__).resolve().parent / "artifacts" / "decision_v1"
)

DEFAULT_QB_SCRAMBLE_FEATURES: tuple[str, ...] = (
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
    "qb_prior_scramble_rate",
    "team_prior_scramble_rate",
    "opponent_prior_scramble_rate_allowed",
)


@dataclass(frozen=True)
class QbScrambleModelConfig:
    """Configuration for the learned scramble-probability node."""

    enabled: bool = False
    artifacts_dir: str | None = None
    factor_clamp: tuple[float, float] = (0.50, 1.75)
    probability_clamp: tuple[float, float] = (0.0, 0.25)
    min_examples: int = 500


@dataclass(frozen=True)
class QbRushingConfig:
    """Configuration container for QB rushing sublayers."""

    scramble: QbScrambleModelConfig = field(default_factory=QbScrambleModelConfig)
```

Create `src/fantasy_sim/data/qb_rushing/config.py`:

```python
"""Config loading for QB rushing layers."""

from __future__ import annotations

import math

from fantasy_sim.data.qb_rushing.models import QbRushingConfig, QbScrambleModelConfig


def _load_clamp(
    raw: object,
    default: tuple[float, float],
    name: str,
    *,
    probability: bool,
) -> tuple[float, float]:
    if raw is None:
        return default
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        raise ValueError(f"{name} must contain [min, max]")
    lo = float(raw[0])
    hi = float(raw[1])
    if not math.isfinite(lo) or not math.isfinite(hi) or lo >= hi:
        raise ValueError(f"{name} must contain finite min < max")
    if probability and (lo < 0.0 or hi > 1.0):
        raise ValueError(f"{name} must satisfy 0 <= min < max <= 1")
    if not probability and lo < 0.0:
        raise ValueError(f"{name} must satisfy 0 <= min < max")
    return (lo, hi)


def load_qb_rushing_config(defaults: dict) -> QbRushingConfig:
    """Extract QbRushingConfig from the full defaults config dict."""
    raw = defaults.get("qb_rushing") or {}
    scramble_raw = raw.get("scramble") or {}

    min_examples = int(scramble_raw.get("min_examples", 500))
    if min_examples < 1:
        raise ValueError("qb_rushing.scramble.min_examples must be >= 1")

    return QbRushingConfig(
        scramble=QbScrambleModelConfig(
            enabled=bool(scramble_raw.get("enabled", False)),
            artifacts_dir=scramble_raw.get("artifacts_dir"),
            factor_clamp=_load_clamp(
                scramble_raw.get("factor_clamp"),
                (0.50, 1.75),
                "qb_rushing.scramble.factor_clamp",
                probability=False,
            ),
            probability_clamp=_load_clamp(
                scramble_raw.get("probability_clamp"),
                (0.0, 0.25),
                "qb_rushing.scramble.probability_clamp",
                probability=True,
            ),
            min_examples=min_examples,
        )
    )
```

Create `src/fantasy_sim/data/qb_rushing/__init__.py`:

```python
"""QB rushing model package."""

from fantasy_sim.data.qb_rushing.config import load_qb_rushing_config
from fantasy_sim.data.qb_rushing.models import (
    DEFAULT_ARTIFACT_DIR,
    DEFAULT_QB_SCRAMBLE_FEATURES,
    QB_SCRAMBLE_MODEL_TYPE,
    QB_SCRAMBLE_SCHEMA_VERSION,
    QbRushingConfig,
    QbScrambleModelConfig,
)

__all__ = [
    "DEFAULT_ARTIFACT_DIR",
    "DEFAULT_QB_SCRAMBLE_FEATURES",
    "QB_SCRAMBLE_MODEL_TYPE",
    "QB_SCRAMBLE_SCHEMA_VERSION",
    "QbRushingConfig",
    "QbScrambleModelConfig",
    "load_qb_rushing_config",
]
```

Add this block to `config/defaults.yaml` after `play_call_model:`:

```yaml
qb_rushing:
  scramble:
    enabled: false
    artifacts_dir: null
    factor_clamp: [0.50, 1.75]
    probability_clamp: [0.0, 0.25]
    min_examples: 500
```

Update `src/fantasy_sim/validation/config.py`:

```python
from fantasy_sim.data.qb_rushing import load_qb_rushing_config
```

In `build_engine_configs()`, after `play_call_model = load_play_call_model_config(config)`, add:

```python
    qb_rushing = load_qb_rushing_config(config)
```

In the returned dict, add:

```python
        "qb_rushing_config": qb_rushing if qb_rushing.scramble.enabled else None,
```

In `build_bare_engine_configs()`, add:

```python
        "qb_rushing_config": None,
```

- [ ] **Step 4: Run config tests and verify they pass**

Run:

```bash
uv run pytest tests/test_data/test_qb_rushing/test_config.py tests/test_validation/test_config.py::TestBuildEngineConfigs::test_defaults_keep_qb_rushing_disabled tests/test_validation/test_config.py::TestBuildEngineConfigs::test_enabled_qb_rushing_config_is_built -v
```

Expected: PASS.

- [ ] **Step 5: Commit config surface**

```bash
git add config/defaults.yaml src/fantasy_sim/data/qb_rushing src/fantasy_sim/validation/config.py tests/test_data/test_qb_rushing tests/test_validation/test_config.py
git commit -m "feat: add QB rushing config"
```

---

### Task 2: Feature Values And Offset-Logistic Training Helpers

**Files:**
- Modify: `src/fantasy_sim/data/qb_rushing/models.py`
- Create: `src/fantasy_sim/data/qb_rushing/training.py`
- Modify: `src/fantasy_sim/data/qb_rushing/__init__.py`
- Create: `tests/test_data/test_qb_rushing/test_models.py`
- Create: `tests/test_data/test_qb_rushing/test_training.py`

- [ ] **Step 1: Write failing model and training tests**

Create `tests/test_data/test_qb_rushing/test_models.py`:

```python
import pytest

from fantasy_sim.data.qb_rushing.models import (
    DEFAULT_QB_SCRAMBLE_FEATURES,
    QbScrambleContext,
    qb_scramble_feature_values,
)
from fantasy_sim.engine.types import GameState
from fantasy_sim.models.player import PlayerModel, PlayerOutcomes, PlayerUsage


def _state(**overrides):
    values = {
        "quarter": 4,
        "clock": 95,
        "possession": "away",
        "down": 3,
        "distance": 8,
        "yard_line": 18,
        "home_score": 21,
        "away_score": 14,
        "home_team": "KC",
        "away_team": "BUF",
        "receiving_2nd_half": "away",
        "week": 9,
    }
    values.update(overrides)
    return GameState(**values)


def _qb(scramble_rate=0.08):
    return PlayerModel(
        "QB1",
        "Mobile QB",
        "QB",
        "BUF",
        PlayerUsage(snap_share=1.0, scramble_rate=scramble_rate),
        PlayerOutcomes(),
    )


def test_feature_values_include_state_market_and_priors():
    values = qb_scramble_feature_values(
        _state(),
        team="BUF",
        opponent="KC",
        home_team="KC",
        away_team="BUF",
        is_home=False,
        week=9,
        spread_line=-3.0,
        total_line=48.0,
        implied_team_total=22.5,
        qb_prior_scramble_rate=0.10,
        team_prior_scramble_rate=0.08,
        opponent_prior_scramble_rate_allowed=0.07,
    )

    assert set(DEFAULT_QB_SCRAMBLE_FEATURES).issubset(values)
    assert values["down_3"] == 1.0
    assert values["is_red_zone"] == 1.0
    assert values["is_two_minute"] == 1.0
    assert values["is_trailing"] == 1.0
    assert values["is_home"] == 0.0
    assert values["spread_norm"] == pytest.approx(-3.0 / 14.0)
    assert values["qb_prior_scramble_rate"] == pytest.approx(0.10)


def test_context_returns_probability_anchored_to_player_prior():
    context = QbScrambleContext(
        coefficients={"intercept": 0.0},
        feature_names=("intercept",),
        team="BUF",
        opponent="KC",
        home_team="KC",
        away_team="BUF",
        is_home=False,
        target_season=2024,
        week=9,
    )

    assert context.scramble_probability(_state(), _qb(0.08)) == pytest.approx(0.08)


def test_context_clamps_factor_and_probability():
    context = QbScrambleContext(
        coefficients={"intercept": 10.0},
        feature_names=("intercept",),
        team="BUF",
        opponent="KC",
        home_team="KC",
        away_team="BUF",
        is_home=False,
        target_season=2024,
        week=9,
        factor_clamp=(0.50, 1.50),
        probability_clamp=(0.0, 0.20),
    )

    assert context.scramble_probability(_state(), _qb(0.10)) == pytest.approx(0.15)


def test_context_keeps_zero_base_rate_at_zero():
    context = QbScrambleContext(
        coefficients={"intercept": 10.0},
        feature_names=("intercept",),
        team="BUF",
        opponent="KC",
        home_team="KC",
        away_team="BUF",
        is_home=False,
        target_season=2024,
        week=9,
    )

    assert context.scramble_probability(_state(), _qb(0.0)) == 0.0
```

Create `tests/test_data/test_qb_rushing/test_training.py`:

```python
import numpy as np
import pytest

from fantasy_sim.data.qb_rushing.models import DEFAULT_QB_SCRAMBLE_FEATURES
from fantasy_sim.data.qb_rushing.training import (
    QbScrambleTrainingExample,
    build_example_from_row,
    build_scramble_priors,
    fit_logistic_qb_scramble,
    source_seasons_for_artifact,
)


def _row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "season": 2023,
        "week": 5,
        "posteam": "BUF",
        "defteam": "KC",
        "home_team": "KC",
        "away_team": "BUF",
        "play_type": "pass",
        "passer_player_id": "QB1",
        "passer_player_name": "Mobile QB",
        "qb_scramble": 0,
        "down": 3,
        "ydstogo": 8,
        "yardline_100": 35,
        "qtr": 4,
        "quarter_seconds_remaining": 118,
        "score_differential": -6,
        "spread_line": 2.5,
        "total_line": 48.5,
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


def test_build_scramble_priors_counts_dropbacks_and_scrambles():
    priors = build_scramble_priors(
        [
            _row(passer_player_id="QB1", posteam="BUF", defteam="KC", qb_scramble=1),
            _row(passer_player_id="QB1", posteam="BUF", defteam="KC", qb_scramble=0),
            _row(passer_player_id="QB2", posteam="KC", defteam="BUF", qb_scramble=0),
        ]
    )

    assert priors.qb["QB1"] == pytest.approx(0.5)
    assert priors.team["BUF"] == pytest.approx(0.5)
    assert priors.opponent_allowed["KC"] == pytest.approx(0.5)
    assert priors.league == pytest.approx(1 / 3)


def test_build_example_from_row_returns_scramble_label_and_base_rate():
    priors = build_scramble_priors([_row(qb_scramble=1), _row(qb_scramble=0)])

    example = build_example_from_row(_row(qb_scramble=1), DEFAULT_QB_SCRAMBLE_FEATURES, priors)

    assert example is not None
    assert example.label == 1
    assert example.base_rate == pytest.approx(0.5)
    assert example.features.shape == (len(DEFAULT_QB_SCRAMBLE_FEATURES),)
    assert np.isfinite(example.features).all()


def test_build_example_from_row_keeps_scramble_run_rows():
    priors = build_scramble_priors([_row(play_type="run", qb_scramble=1)])

    example = build_example_from_row(
        _row(play_type="run", qb_scramble=1),
        DEFAULT_QB_SCRAMBLE_FEATURES,
        priors,
    )

    assert example is not None
    assert example.label == 1


def test_build_example_from_row_skips_non_pass_non_scramble_rows():
    priors = build_scramble_priors([_row()])

    assert build_example_from_row(
        _row(play_type="run", qb_scramble=0),
        DEFAULT_QB_SCRAMBLE_FEATURES,
        priors,
    ) is None


def test_fit_logistic_qb_scramble_rejects_empty_examples():
    with pytest.raises(ValueError, match="zero examples"):
        fit_logistic_qb_scramble([], ("intercept",))


def test_fit_logistic_qb_scramble_learns_positive_feature_for_scramble():
    examples = [
        QbScrambleTrainingExample(
            features=np.array([1.0, 1.0]),
            label=1,
            base_rate=0.10,
        )
        for _ in range(30)
    ] + [
        QbScrambleTrainingExample(
            features=np.array([1.0, 0.0]),
            label=0,
            base_rate=0.10,
        )
        for _ in range(30)
    ]

    result = fit_logistic_qb_scramble(
        examples,
        ("intercept", "pressure_feature"),
        l2=0.1,
        max_iter=100,
    )

    assert result.num_examples == 60
    assert result.coefficients["pressure_feature"] > 0
    assert result.converged is True
```

- [ ] **Step 2: Run model/training tests and verify they fail**

Run:

```bash
uv run pytest tests/test_data/test_qb_rushing/test_models.py tests/test_data/test_qb_rushing/test_training.py -v
```

Expected: FAIL because `QbScrambleContext` and training helpers do not exist.

- [ ] **Step 3: Add feature helper and runtime context**

Replace `src/fantasy_sim/data/qb_rushing/models.py` with:

```python
"""Models and feature helpers for QB rushing layers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from fantasy_sim.engine.types import GameState
    from fantasy_sim.models.player import PlayerModel

QB_SCRAMBLE_SCHEMA_VERSION = 1
QB_SCRAMBLE_MODEL_TYPE = "offset_logistic_qb_scramble_v1"
DEFAULT_ARTIFACT_DIR = (
    Path(__file__).resolve().parent / "artifacts" / "decision_v1"
)

DEFAULT_QB_SCRAMBLE_FEATURES: tuple[str, ...] = (
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
    "qb_prior_scramble_rate",
    "team_prior_scramble_rate",
    "opponent_prior_scramble_rate_allowed",
)


@dataclass(frozen=True)
class QbScrambleModelConfig:
    """Configuration for the learned scramble-probability node."""

    enabled: bool = False
    artifacts_dir: str | None = None
    factor_clamp: tuple[float, float] = (0.50, 1.75)
    probability_clamp: tuple[float, float] = (0.0, 0.25)
    min_examples: int = 500


@dataclass(frozen=True)
class QbRushingConfig:
    """Configuration container for QB rushing sublayers."""

    scramble: QbScrambleModelConfig = field(default_factory=QbScrambleModelConfig)


@dataclass(frozen=True)
class QbScrambleContext:
    """Runtime context for a team's learned QB scramble model."""

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
    qb_priors: dict[str, float] = field(default_factory=dict)
    team_prior_scramble_rate: float = 0.06
    opponent_prior_scramble_rate_allowed: float = 0.06
    factor_clamp: tuple[float, float] = (0.50, 1.75)
    probability_clamp: tuple[float, float] = (0.0, 0.25)

    def scramble_probability(
        self,
        state: GameState,
        passer: PlayerModel,
    ) -> float | None:
        base_rate = float(getattr(passer.usage, "scramble_rate", 0.0))
        if not np.isfinite(base_rate):
            return None
        base_rate = float(np.clip(base_rate, 0.0, 1.0))
        if base_rate == 0.0:
            return 0.0

        qb_prior = self.qb_priors.get(passer.player_id, base_rate)
        values = qb_scramble_feature_values(
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
            qb_prior_scramble_rate=qb_prior,
            team_prior_scramble_rate=self.team_prior_scramble_rate,
            opponent_prior_scramble_rate_allowed=self.opponent_prior_scramble_rate_allowed,
        )
        delta = 0.0
        for name in self.feature_names:
            delta += float(self.coefficients.get(name, 0.0)) * values.get(name, 0.0)
        if not np.isfinite(delta):
            return None

        raw_probability = _sigmoid(_logit(base_rate) + delta)
        if not np.isfinite(raw_probability):
            return None

        factor_lo, factor_hi = self.factor_clamp
        probability = float(np.clip(raw_probability, base_rate * factor_lo, base_rate * factor_hi))
        prob_lo, prob_hi = self.probability_clamp
        probability = float(np.clip(probability, prob_lo, prob_hi))
        if not np.isfinite(probability):
            return None
        return probability


def _logit(probability: float) -> float:
    clipped = float(np.clip(probability, 1e-6, 1.0 - 1e-6))
    return float(np.log(clipped / (1.0 - clipped)))


def _sigmoid(logit: float) -> float:
    return float(1.0 / (1.0 + np.exp(-np.clip(logit, -35.0, 35.0))))


def qb_scramble_feature_values(
    state: GameState,
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
    qb_prior_scramble_rate: float,
    team_prior_scramble_rate: float,
    opponent_prior_scramble_rate_allowed: float,
) -> dict[str, float]:
    del team, opponent, home_team, away_team
    distance = max(0, int(state.distance))
    yard_line = max(1, min(99, int(state.yard_line)))
    score_diff = float(state.score_differential)
    clock = max(0, min(900, int(state.clock)))
    quarter = max(1, min(5, int(state.quarter)))
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
        "qb_prior_scramble_rate": float(np.clip(qb_prior_scramble_rate, 0.0, 1.0)),
        "team_prior_scramble_rate": float(np.clip(team_prior_scramble_rate, 0.0, 1.0)),
        "opponent_prior_scramble_rate_allowed": float(
            np.clip(opponent_prior_scramble_rate_allowed, 0.0, 1.0)
        ),
    }
```

- [ ] **Step 4: Add training helpers**

Create `src/fantasy_sim/data/qb_rushing/training.py`:

```python
"""Training helpers for learned QB scramble probability."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Mapping

import numpy as np
from scipy.optimize import minimize

from fantasy_sim.data.qb_rushing.models import qb_scramble_feature_values
from fantasy_sim.engine.types import GameState


@dataclass(frozen=True)
class QbScramblePriors:
    qb: dict[str, float] = field(default_factory=dict)
    team: dict[str, float] = field(default_factory=dict)
    opponent_allowed: dict[str, float] = field(default_factory=dict)
    league: float = 0.06


@dataclass(frozen=True)
class QbScrambleTrainingExample:
    features: np.ndarray
    label: int
    base_rate: float


@dataclass(frozen=True)
class QbScrambleFitResult:
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


def _is_scramble(row: Mapping[str, object]) -> int:
    value = row.get("qb_scramble")
    if value is None:
        return 0
    try:
        return 1 if int(value) == 1 else 0
    except (TypeError, ValueError):
        return 0


def _is_modeled_dropback(row: Mapping[str, object]) -> bool:
    return row.get("play_type") == "pass" or _is_scramble(row) == 1


def build_scramble_priors(rows: Iterable[Mapping[str, object]]) -> QbScramblePriors:
    qb_counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    team_counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    opponent_counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    total = [0, 0]

    for row in rows:
        if not _is_modeled_dropback(row):
            continue
        passer_id = row.get("passer_player_id")
        team = row.get("posteam")
        opponent = row.get("defteam")
        if passer_id is None or team is None or opponent is None:
            continue
        scramble = _is_scramble(row)
        qb_counts[str(passer_id)][0] += scramble
        qb_counts[str(passer_id)][1] += 1
        team_counts[str(team)][0] += scramble
        team_counts[str(team)][1] += 1
        opponent_counts[str(opponent)][0] += scramble
        opponent_counts[str(opponent)][1] += 1
        total[0] += scramble
        total[1] += 1

    league = total[0] / total[1] if total[1] else 0.06
    return QbScramblePriors(
        qb={key: count[0] / count[1] for key, count in qb_counts.items() if count[1]},
        team={key: count[0] / count[1] for key, count in team_counts.items() if count[1]},
        opponent_allowed={
            key: count[0] / count[1] for key, count in opponent_counts.items() if count[1]
        },
        league=league,
    )


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


def _state_from_row(row: Mapping[str, object]) -> GameState | None:
    try:
        posteam = str(row["posteam"])
        home_team = str(row["home_team"])
        away_team = str(row["away_team"])
        possession = "home" if posteam == home_team else "away"
        score_differential = int(row.get("score_differential") or 0)
        if possession == "home":
            home_score = max(0, score_differential)
            away_score = max(0, -score_differential)
        else:
            home_score = max(0, -score_differential)
            away_score = max(0, score_differential)
        return GameState(
            quarter=int(row.get("qtr") or 1),
            clock=int(row.get("quarter_seconds_remaining") or 0),
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
    priors: QbScramblePriors,
) -> QbScrambleTrainingExample | None:
    if not _is_modeled_dropback(row):
        return None
    if row.get("posteam") is None or row.get("defteam") is None:
        return None
    passer_id = row.get("passer_player_id")
    if passer_id is None:
        return None
    state = _state_from_row(row)
    if state is None:
        return None

    posteam = str(row["posteam"])
    defteam = str(row["defteam"])
    home_team = str(row["home_team"])
    away_team = str(row["away_team"])
    total_line = _float_or_none(row.get("total_line"))
    spread_line = _float_or_none(row.get("spread_line"))
    implied_team_total = None
    team_spread_line = None
    if total_line is not None and spread_line is not None:
        if posteam == home_team:
            team_spread_line = spread_line
            implied_team_total = total_line / 2.0 + spread_line / 2.0
        else:
            team_spread_line = -spread_line
            implied_team_total = total_line / 2.0 - spread_line / 2.0
    else:
        total_line = None

    passer_key = str(passer_id)
    qb_prior = priors.qb.get(passer_key, priors.league)
    team_prior = priors.team.get(posteam, priors.league)
    opponent_prior = priors.opponent_allowed.get(defteam, priors.league)
    values = qb_scramble_feature_values(
        state,
        team=posteam,
        opponent=defteam,
        home_team=home_team,
        away_team=away_team,
        is_home=posteam == home_team,
        week=int(row.get("week") or 0),
        spread_line=team_spread_line,
        total_line=total_line,
        implied_team_total=implied_team_total,
        qb_prior_scramble_rate=qb_prior,
        team_prior_scramble_rate=team_prior,
        opponent_prior_scramble_rate_allowed=opponent_prior,
    )
    features = np.array([values.get(name, 0.0) for name in feature_names], dtype=float)
    if not np.all(np.isfinite(features)):
        return None
    return QbScrambleTrainingExample(
        features=features,
        label=_is_scramble(row),
        base_rate=qb_prior,
    )


def _logit(probability: np.ndarray) -> np.ndarray:
    clipped = np.clip(probability, 1e-6, 1.0 - 1e-6)
    return np.log(clipped / (1.0 - clipped))


def fit_logistic_qb_scramble(
    examples: list[QbScrambleTrainingExample],
    feature_names: tuple[str, ...],
    *,
    l2: float = 1.0,
    max_iter: int = 200,
) -> QbScrambleFitResult:
    if not examples:
        raise ValueError("Cannot fit QB scramble model with zero examples")
    if not feature_names:
        raise ValueError("feature_names must not be empty")

    n_features = len(feature_names)
    x = np.vstack([example.features for example in examples]).astype(float)
    y = np.array([example.label for example in examples], dtype=float)
    base_rates = np.array([example.base_rate for example in examples], dtype=float)
    if x.shape != (len(examples), n_features):
        raise ValueError("Feature matrix shape does not match feature_names")
    if not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)):
        raise ValueError("Training examples must contain finite values")
    if not np.all(np.isfinite(base_rates)):
        raise ValueError("Training examples must contain finite base rates")

    offsets = _logit(base_rates)

    def objective(beta: np.ndarray) -> tuple[float, np.ndarray]:
        logits = np.clip(offsets + x @ beta, -35.0, 35.0)
        loss = float(np.sum(np.logaddexp(0.0, logits) - y * logits))
        loss += 0.5 * l2 * float(np.dot(beta, beta))
        probs = 1.0 / (1.0 + np.exp(-logits))
        grad = x.T @ (probs - y) + l2 * beta
        return loss, grad

    result = minimize(
        objective,
        np.zeros(n_features, dtype=float),
        method="L-BFGS-B",
        jac=True,
        options={"maxiter": max_iter},
    )
    return QbScrambleFitResult(
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

Update `src/fantasy_sim/data/qb_rushing/__init__.py` exports:

```python
from fantasy_sim.data.qb_rushing.config import load_qb_rushing_config
from fantasy_sim.data.qb_rushing.models import (
    DEFAULT_ARTIFACT_DIR,
    DEFAULT_QB_SCRAMBLE_FEATURES,
    QB_SCRAMBLE_MODEL_TYPE,
    QB_SCRAMBLE_SCHEMA_VERSION,
    QbRushingConfig,
    QbScrambleContext,
    QbScrambleModelConfig,
    qb_scramble_feature_values,
)
from fantasy_sim.data.qb_rushing.training import (
    QbScrambleFitResult,
    QbScramblePriors,
    QbScrambleTrainingExample,
    build_example_from_row,
    build_scramble_priors,
    fit_logistic_qb_scramble,
    source_seasons_for_artifact,
)

__all__ = [
    "DEFAULT_ARTIFACT_DIR",
    "DEFAULT_QB_SCRAMBLE_FEATURES",
    "QB_SCRAMBLE_MODEL_TYPE",
    "QB_SCRAMBLE_SCHEMA_VERSION",
    "QbRushingConfig",
    "QbScrambleContext",
    "QbScrambleFitResult",
    "QbScrambleModelConfig",
    "QbScramblePriors",
    "QbScrambleTrainingExample",
    "build_example_from_row",
    "build_scramble_priors",
    "fit_logistic_qb_scramble",
    "load_qb_rushing_config",
    "qb_scramble_feature_values",
    "source_seasons_for_artifact",
]
```

- [ ] **Step 5: Run model/training tests and verify they pass**

Run:

```bash
uv run pytest tests/test_data/test_qb_rushing/test_models.py tests/test_data/test_qb_rushing/test_training.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit model and training helpers**

```bash
git add src/fantasy_sim/data/qb_rushing tests/test_data/test_qb_rushing
git commit -m "feat: add QB scramble training helpers"
```

---

### Task 3: Runtime Artifact Loading

**Files:**
- Create: `src/fantasy_sim/data/qb_rushing/runtime.py`
- Modify: `src/fantasy_sim/data/qb_rushing/__init__.py`
- Create: `tests/test_data/test_qb_rushing/test_runtime.py`

- [ ] **Step 1: Write failing runtime tests**

Create `tests/test_data/test_qb_rushing/test_runtime.py`:

```python
import json

import pytest

from fantasy_sim.data.qb_rushing import (
    QB_SCRAMBLE_MODEL_TYPE,
    QB_SCRAMBLE_SCHEMA_VERSION,
    QbScrambleModel,
    QbScrambleModelConfig,
)
from fantasy_sim.engine.types import GameState
from fantasy_sim.models.player import PlayerModel, PlayerOutcomes, PlayerUsage, TeamRoster


def _qb(scramble_rate=0.08):
    return PlayerModel(
        "QB1",
        "Mobile QB",
        "QB",
        "BUF",
        PlayerUsage(snap_share=1.0, scramble_rate=scramble_rate),
        PlayerOutcomes(),
    )


def _roster():
    return TeamRoster(team="BUF", players=[_qb()])


def _state():
    return GameState(
        quarter=3,
        clock=400,
        possession="away",
        down=3,
        distance=8,
        yard_line=35,
        home_score=17,
        away_score=14,
        home_team="KC",
        away_team="BUF",
        receiving_2nd_half="away",
        week=9,
    )


def _config(tmp_path, **overrides):
    values = {"enabled": True, "artifacts_dir": str(tmp_path)}
    values.update(overrides)
    return QbScrambleModelConfig(**values)


def _artifact(**overrides):
    values = {
        "schema_version": QB_SCRAMBLE_SCHEMA_VERSION,
        "model_type": QB_SCRAMBLE_MODEL_TYPE,
        "target_season": 2024,
        "source_seasons": [2023],
        "feature_names": ["intercept"],
        "coefficients": {"intercept": 0.0},
        "factor_clamp": [0.50, 1.75],
        "probability_clamp": [0.0, 0.25],
        "priors": {
            "qb": {"QB1": 0.08},
            "team": {"BUF": 0.08},
            "opponent_allowed": {"KC": 0.07},
            "league": 0.06,
        },
    }
    values.update(overrides)
    return values


def _write_artifact(tmp_path, **overrides):
    path = tmp_path / "qb_scramble_model_2024.json"
    path.write_text(json.dumps(_artifact(**overrides)), encoding="utf-8")
    return path


def _build_context(model):
    return model.build_context(
        roster=_roster(),
        team="BUF",
        opponent="KC",
        home_team="KC",
        away_team="BUF",
        target_season=2024,
        week=9,
        is_home=False,
    )


def test_missing_artifact_returns_none_from_build_context(tmp_path):
    model = QbScrambleModel(_config(tmp_path))

    assert _build_context(model) is None


def test_valid_artifact_builds_context(tmp_path):
    _write_artifact(tmp_path)
    model = QbScrambleModel(_config(tmp_path))

    context = _build_context(model)

    assert context is not None
    assert context.scramble_probability(_state(), _qb()) == pytest.approx(0.08)


def test_invalid_schema_returns_none(tmp_path):
    _write_artifact(tmp_path, schema_version=999)
    model = QbScrambleModel(_config(tmp_path))

    assert _build_context(model) is None


def test_non_finite_coefficient_returns_none(tmp_path):
    _write_artifact(tmp_path, coefficients={"intercept": "nan"})
    model = QbScrambleModel(_config(tmp_path))

    assert _build_context(model) is None


def test_unsupported_feature_name_returns_none(tmp_path):
    _write_artifact(
        tmp_path,
        feature_names=["intercept", "unsupported_feature"],
        coefficients={"intercept": 0.0, "unsupported_feature": 1.0},
    )
    model = QbScrambleModel(_config(tmp_path))

    assert _build_context(model) is None


def test_artifact_target_season_mismatch_returns_none(tmp_path):
    _write_artifact(tmp_path, target_season=2023)
    model = QbScrambleModel(_config(tmp_path))

    assert _build_context(model) is None


@pytest.mark.parametrize("source_seasons", [[], [2024], [2023, 2024], ["2023"]])
def test_artifact_with_invalid_source_seasons_returns_none(tmp_path, source_seasons):
    _write_artifact(tmp_path, source_seasons=source_seasons)
    model = QbScrambleModel(_config(tmp_path))

    assert _build_context(model) is None


def test_invalid_utf8_artifact_returns_none(tmp_path):
    (tmp_path / "qb_scramble_model_2024.json").write_bytes(b"\xff\xfe\x00")
    model = QbScrambleModel(_config(tmp_path))

    assert _build_context(model) is None
```

- [ ] **Step 2: Run runtime tests and verify they fail**

Run:

```bash
uv run pytest tests/test_data/test_qb_rushing/test_runtime.py -v
```

Expected: FAIL because `QbScrambleModel` does not exist.

- [ ] **Step 3: Add strict runtime loader**

Create `src/fantasy_sim/data/qb_rushing/runtime.py`:

```python
"""Runtime artifact loading for learned QB scramble probability."""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Any, Mapping

from fantasy_sim.data.qb_rushing.models import (
    DEFAULT_ARTIFACT_DIR,
    DEFAULT_QB_SCRAMBLE_FEATURES,
    QB_SCRAMBLE_MODEL_TYPE,
    QB_SCRAMBLE_SCHEMA_VERSION,
    QbScrambleContext,
    QbScrambleModelConfig,
)
from fantasy_sim.models.player import TeamRoster

logger = logging.getLogger(__name__)


def _source_seasons_are_safe(source_seasons: object, target_season: int) -> bool:
    if not isinstance(source_seasons, list) or not source_seasons:
        return False
    return all(
        isinstance(season, int)
        and not isinstance(season, bool)
        and season < target_season
        for season in source_seasons
    )


def _parse_float_mapping(value: object) -> dict[str, float]:
    if not isinstance(value, Mapping):
        return {}
    parsed: dict[str, float] = {}
    for key, raw in value.items():
        try:
            parsed_value = float(raw)
        except (TypeError, ValueError):
            continue
        if math.isfinite(parsed_value):
            parsed[str(key)] = parsed_value
    return parsed


class QbScrambleModel:
    """Loads learned QB scramble artifacts and builds runtime contexts."""

    def __init__(self, config: QbScrambleModelConfig) -> None:
        self.config = config
        self.artifacts_dir = Path(config.artifacts_dir or DEFAULT_ARTIFACT_DIR)
        self._artifact_cache: dict[int, dict[str, Any] | None] = {}

    def build_context(
        self,
        roster: TeamRoster,
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
    ) -> QbScrambleContext | None:
        if not self.config.enabled:
            return None
        artifact = self._load_artifact(target_season)
        if artifact is None:
            return None
        if artifact.get("target_season") != target_season:
            logger.warning("Invalid QB scramble artifact for %s: target season mismatch", target_season)
            return None
        if not _source_seasons_are_safe(artifact.get("source_seasons"), target_season):
            logger.warning("Invalid QB scramble artifact for %s: unsafe source seasons", target_season)
            return None

        feature_names = artifact.get("feature_names")
        coefficients_raw = artifact.get("coefficients")
        if not isinstance(feature_names, list) or not isinstance(coefficients_raw, Mapping):
            logger.warning("Invalid QB scramble artifact for %s: missing feature_names/coefficients", target_season)
            return None
        if not feature_names or not all(isinstance(name, str) for name in feature_names):
            logger.warning("Invalid QB scramble artifact for %s: malformed feature_names", target_season)
            return None
        parsed_features = tuple(feature_names)
        if any(name not in DEFAULT_QB_SCRAMBLE_FEATURES for name in parsed_features):
            logger.warning("Invalid QB scramble artifact for %s: unsupported feature name", target_season)
            return None

        try:
            coefficients = {str(name): float(value) for name, value in coefficients_raw.items()}
        except (TypeError, ValueError):
            logger.warning("Invalid QB scramble artifact for %s: coefficient parsing failed", target_season)
            return None
        if set(coefficients) != set(parsed_features):
            logger.warning("Invalid QB scramble artifact for %s: coefficient/feature mismatch", target_season)
            return None
        if not all(math.isfinite(value) for value in coefficients.values()):
            logger.warning("Invalid QB scramble artifact for %s: non-finite coefficient", target_season)
            return None

        priors = artifact.get("priors") if isinstance(artifact.get("priors"), Mapping) else {}
        qb_priors = _parse_float_mapping(priors.get("qb") if isinstance(priors, Mapping) else None)
        team_priors = _parse_float_mapping(priors.get("team") if isinstance(priors, Mapping) else None)
        opponent_priors = _parse_float_mapping(
            priors.get("opponent_allowed") if isinstance(priors, Mapping) else None
        )
        league_prior = _artifact_float(priors.get("league") if isinstance(priors, Mapping) else None, 0.06)

        return QbScrambleContext(
            coefficients=coefficients,
            feature_names=parsed_features,
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
            qb_priors=qb_priors,
            team_prior_scramble_rate=team_priors.get(team, league_prior),
            opponent_prior_scramble_rate_allowed=opponent_priors.get(opponent, league_prior),
            factor_clamp=self._artifact_clamp(artifact, "factor_clamp", self.config.factor_clamp, probability=False),
            probability_clamp=self._artifact_clamp(
                artifact,
                "probability_clamp",
                self.config.probability_clamp,
                probability=True,
            ),
        )

    def _load_artifact(self, target_season: int) -> dict[str, Any] | None:
        if target_season in self._artifact_cache:
            return self._artifact_cache[target_season]
        path = self.artifacts_dir / f"qb_scramble_model_{target_season}.json"
        artifact: dict[str, Any] | None = None
        try:
            with path.open("r", encoding="utf-8") as handle:
                loaded = json.load(handle)
        except FileNotFoundError:
            logger.info("Missing QB scramble artifact: %s", path)
        except OSError:
            logger.warning("Unable to read QB scramble artifact: %s", path)
        except UnicodeDecodeError:
            logger.warning("Invalid QB scramble artifact encoding: %s", path)
        except json.JSONDecodeError:
            logger.warning("Invalid QB scramble artifact JSON: %s", path)
        else:
            if not isinstance(loaded, dict):
                logger.warning("Invalid QB scramble artifact payload: %s", path)
            elif loaded.get("schema_version") != QB_SCRAMBLE_SCHEMA_VERSION:
                logger.warning("Unsupported QB scramble artifact schema: %s", path)
            elif loaded.get("model_type") != QB_SCRAMBLE_MODEL_TYPE:
                logger.warning("Unsupported QB scramble artifact model type: %s", path)
            else:
                artifact = loaded
        self._artifact_cache[target_season] = artifact
        return artifact

    def _artifact_clamp(
        self,
        artifact: dict[str, Any],
        key: str,
        default: tuple[float, float],
        *,
        probability: bool,
    ) -> tuple[float, float]:
        clamp = artifact.get(key)
        if not isinstance(clamp, list | tuple) or len(clamp) != 2:
            return default
        try:
            lo = float(clamp[0])
            hi = float(clamp[1])
        except (TypeError, ValueError):
            return default
        if not math.isfinite(lo) or not math.isfinite(hi) or lo >= hi:
            return default
        if probability and (lo < 0.0 or hi > 1.0):
            return default
        if not probability and lo < 0.0:
            return default
        return (lo, hi)


def _artifact_float(value: object, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default
```

Update `src/fantasy_sim/data/qb_rushing/__init__.py`:

```python
from fantasy_sim.data.qb_rushing.runtime import QbScrambleModel
```

Add `"QbScrambleModel"` to `__all__`.

- [ ] **Step 4: Run runtime tests and verify they pass**

Run:

```bash
uv run pytest tests/test_data/test_qb_rushing/test_runtime.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit runtime loader**

```bash
git add src/fantasy_sim/data/qb_rushing tests/test_data/test_qb_rushing/test_runtime.py
git commit -m "feat: load QB scramble artifacts"
```

---

### Task 4: Artifact Fitting Script

**Files:**
- Create: `scripts/fit_qb_scramble_model.py`
- Create: `tests/test_scripts/test_fit_qb_scramble_model.py`

- [ ] **Step 1: Write failing script helper tests**

Create `tests/test_scripts/test_fit_qb_scramble_model.py`:

```python
import json

import polars as pl

from fantasy_sim.data.qb_rushing import QB_SCRAMBLE_MODEL_TYPE, QB_SCRAMBLE_SCHEMA_VERSION
from scripts.fit_qb_scramble_model import collect_examples_from_pbp, fit_artifact_for_season


class FakeLoader:
    def __init__(self, pbp):
        self._pbp = pbp

    def load_pbp(self, seasons):
        assert seasons == [2023]
        return self._pbp


def _pbp():
    rows = []
    for idx in range(12):
        rows.append(
            {
                "season": 2023,
                "week": 1,
                "posteam": "BUF",
                "defteam": "KC",
                "home_team": "KC",
                "away_team": "BUF",
                "play_type": "run" if idx < 4 else "pass",
                "passer_player_id": "QB1",
                "passer_player_name": "Mobile QB",
                "qb_scramble": 1 if idx < 4 else 0,
                "down": 3,
                "ydstogo": 8,
                "yardline_100": 35,
                "qtr": 2,
                "quarter_seconds_remaining": 300,
                "score_differential": -3,
                "spread_line": 2.0,
                "total_line": 47.0,
            }
        )
    return pl.DataFrame(rows)


def test_collect_examples_from_pbp_includes_passes_and_scrambles():
    examples, priors = collect_examples_from_pbp(_pbp())

    assert len(examples) == 12
    assert sum(example.label for example in examples) == 4
    assert priors.qb["QB1"] == 4 / 12


def test_fit_artifact_for_season_writes_json(tmp_path):
    artifact = fit_artifact_for_season(
        FakeLoader(_pbp()),
        target_season=2024,
        min_source_season=2023,
        training_years=1,
        output_dir=tmp_path,
        l2=1.0,
        max_iter=50,
    )

    path = tmp_path / "qb_scramble_model_2024.json"
    saved = json.loads(path.read_text())
    assert artifact["schema_version"] == QB_SCRAMBLE_SCHEMA_VERSION
    assert saved["model_type"] == QB_SCRAMBLE_MODEL_TYPE
    assert saved["target_season"] == 2024
    assert saved["source_seasons"] == [2023]
    assert saved["diagnostics"]["num_examples"] == 12
```

- [ ] **Step 2: Run script tests and verify they fail**

Run:

```bash
uv run pytest tests/test_scripts/test_fit_qb_scramble_model.py -v
```

Expected: FAIL because `scripts/fit_qb_scramble_model.py` does not exist.

- [ ] **Step 3: Add the fitting script**

Create `scripts/fit_qb_scramble_model.py`:

```python
"""Fit learned QB scramble-probability artifacts."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import polars as pl

from fantasy_sim.data.loader import DataLoader
from fantasy_sim.data.qb_rushing.models import (
    DEFAULT_QB_SCRAMBLE_FEATURES,
    QB_SCRAMBLE_MODEL_TYPE,
    QB_SCRAMBLE_SCHEMA_VERSION,
)
from fantasy_sim.data.qb_rushing.training import (
    QbScramblePriors,
    QbScrambleTrainingExample,
    build_example_from_row,
    build_scramble_priors,
    fit_logistic_qb_scramble,
    source_seasons_for_artifact,
)

_REQUIRED_PBP_COLUMNS = frozenset(
    {
        "play_type",
        "posteam",
        "defteam",
        "home_team",
        "away_team",
        "down",
        "ydstogo",
        "yardline_100",
        "passer_player_id",
        "qb_scramble",
    }
)


def build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fit learned QB scramble-probability artifacts.",
    )
    parser.add_argument("--test-seasons", type=int, nargs="+", required=True)
    parser.add_argument("--min-source-season", type=int, default=2018)
    parser.add_argument("--training-years", type=int, default=4)
    parser.add_argument("--l2", type=float, default=1.0)
    parser.add_argument("--max-iter", type=int, default=200)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def collect_examples_from_pbp(
    pbp: pl.DataFrame,
    feature_names: tuple[str, ...] = DEFAULT_QB_SCRAMBLE_FEATURES,
) -> tuple[list[QbScrambleTrainingExample], QbScramblePriors]:
    if pbp.is_empty():
        return [], QbScramblePriors()
    missing = sorted(_REQUIRED_PBP_COLUMNS.difference(pbp.columns))
    if missing:
        raise ValueError(f"PBP data is missing required columns: {missing}")
    rows = list(pbp.iter_rows(named=True))
    priors = build_scramble_priors(rows)
    examples: list[QbScrambleTrainingExample] = []
    for row in rows:
        example = build_example_from_row(row, feature_names, priors)
        if example is not None:
            examples.append(example)
    return examples, priors


def fit_artifact_for_season(
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
    examples, priors = collect_examples_from_pbp(pbp, DEFAULT_QB_SCRAMBLE_FEATURES)
    fit = fit_logistic_qb_scramble(
        examples,
        DEFAULT_QB_SCRAMBLE_FEATURES,
        l2=l2,
        max_iter=max_iter,
    )
    scramble_rate = sum(example.label for example in examples) / len(examples)
    artifact = {
        "schema_version": QB_SCRAMBLE_SCHEMA_VERSION,
        "model_type": QB_SCRAMBLE_MODEL_TYPE,
        "target_season": target_season,
        "source_seasons": source_seasons,
        "feature_names": list(DEFAULT_QB_SCRAMBLE_FEATURES),
        "coefficients": fit.coefficients,
        "factor_clamp": [0.50, 1.75],
        "probability_clamp": [0.0, 0.25],
        "priors": {
            "qb": priors.qb,
            "team": priors.team,
            "opponent_allowed": priors.opponent_allowed,
            "league": priors.league,
        },
        "diagnostics": {
            "num_examples": fit.num_examples,
            "scramble_rate": scramble_rate,
            "objective": fit.objective,
            "converged": fit.converged,
            "iterations": fit.iterations,
            "l2": l2,
        },
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"qb_scramble_model_{target_season}.json"
    path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return artifact


def main(argv: list[str] | None = None) -> int:
    args = build_cli().parse_args(argv)
    loader = DataLoader()
    started = time.time()
    for season in args.test_seasons:
        print(f"Fitting QB scramble artifact for {season}...", flush=True)
        artifact = fit_artifact_for_season(
            loader,
            season,
            args.min_source_season,
            args.training_years,
            args.output_dir,
            args.l2,
            args.max_iter,
        )
        diag = artifact["diagnostics"]
        print(
            f"  wrote qb_scramble_model_{season}.json "
            f"examples={diag['num_examples']} "
            f"scramble_rate={diag['scramble_rate']:.3f} "
            f"converged={diag['converged']}",
            flush=True,
        )
    print(f"Completed in {time.time() - started:.1f}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run script tests and verify they pass**

Run:

```bash
uv run pytest tests/test_scripts/test_fit_qb_scramble_model.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit fitting script**

```bash
git add scripts/fit_qb_scramble_model.py tests/test_scripts/test_fit_qb_scramble_model.py
git commit -m "feat: fit QB scramble artifacts"
```

---

### Task 5: Engine Runtime Wiring

**Files:**
- Modify: `src/fantasy_sim/engine/types.py`
- Modify: `src/fantasy_sim/engine/play_resolver.py`
- Modify: `src/fantasy_sim/engine/game_sim.py`
- Modify: `tests/test_engine/test_play_resolver.py`
- Modify: `tests/test_engine/test_game_sim.py`

- [ ] **Step 1: Write failing play-resolver tests**

Append to `tests/test_engine/test_play_resolver.py` after `TestResolvePassScramble`:

```python
class FixedQbScrambleContext:
    def __init__(self, probability):
        self.probability = probability

    def scramble_probability(self, state, passer):
        return self.probability


class TestResolvePassQbScrambleContext:
    def _make_context_roster(self, scramble_rate=0.0) -> TeamRoster:
        qb = PlayerModel(
            "QB1",
            "QB",
            "QB",
            "T",
            PlayerUsage(snap_share=1.0, scramble_rate=scramble_rate),
            PlayerOutcomes(scramble_yards_dist=np.array([6]), fumble_rate=0.0),
        )
        wr = PlayerModel(
            "WR1",
            "WR",
            "WR",
            "T",
            PlayerUsage(target_share=1.0),
            PlayerOutcomes(catch_rate=1.0, receiving_yards_dist=np.array([10])),
        )
        rb = PlayerModel(
            "RB1",
            "RB",
            "RB",
            "T",
            PlayerUsage(carry_share=1.0),
            PlayerOutcomes(rushing_yards_dist=np.array([4])),
        )
        return TeamRoster(team="T", players=[qb, wr, rb])

    def test_qb_scramble_context_can_force_scramble_probability(self):
        result = resolve_play(
            make_state(),
            "pass",
            make_outcomes(),
            make_turnover_rates(sack_rate=1.0, int_rate=1.0),
            np.random.default_rng(42),
            roster=self._make_context_roster(scramble_rate=0.0),
            qb_scramble_context=FixedQbScrambleContext(1.0),
        )

        assert result.play_type == "run"
        assert result.rusher_id == "QB1"
        assert result.yards == 6
        assert not result.is_sack
        assert not result.is_interception

    def test_qb_scramble_context_none_falls_back_to_base_rate(self):
        result = resolve_play(
            make_state(),
            "pass",
            make_outcomes(),
            make_turnover_rates(),
            np.random.default_rng(42),
            roster=self._make_context_roster(scramble_rate=1.0),
            qb_scramble_context=FixedQbScrambleContext(None),
        )

        assert result.play_type == "run"
        assert result.rusher_id == "QB1"
```

Extend `tests/test_engine/test_game_sim.py::TestSimulateGame::test_threads_runtime_script_into_play_selection_and_pace`.

In the local `fake_resolve_play()` signature, add the new keyword after `target_selection_context`:

```python
            qb_scramble_context=None,
```

Inside the fake, record the value:

```python
            seen["qb_scramble_context"] = qb_scramble_context
```

After `play_call_context = object()`, add:

```python
        qb_scramble_context = object()
```

After assigning `home_dists.play_call_context` and `away_dists.play_call_context`, add:

```python
        home_dists.qb_scramble_context = qb_scramble_context
        away_dists.qb_scramble_context = qb_scramble_context
```

After `assert seen["target_selection_context"] is target_context`, add:

```python
        assert seen["qb_scramble_context"] is qb_scramble_context
```

- [ ] **Step 2: Run engine tests and verify they fail**

Run:

```bash
uv run pytest tests/test_engine/test_play_resolver.py::TestResolvePassQbScrambleContext tests/test_engine/test_game_sim.py -v
```

Expected: FAIL because `qb_scramble_context` is not accepted or threaded.

- [ ] **Step 3: Add engine protocol and distribution field**

Modify `src/fantasy_sim/engine/types.py` after `PlayCallContextProtocol`:

```python
class QbScrambleContextProtocol(Protocol):
    """QB scramble-probability interface used by the engine."""

    def scramble_probability(
        self,
        state: "GameState",
        passer: "PlayerModel",
    ) -> float | None:
        raise NotImplementedError
```

Add this field to `TeamDistributions` after `play_call_context`:

```python
    qb_scramble_context: QbScrambleContextProtocol | None = None
```

- [ ] **Step 4: Thread the context into play resolution**

Modify imports in `src/fantasy_sim/engine/play_resolver.py` so the engine imports `QbScrambleContextProtocol` from `fantasy_sim.engine.types`.

Add parameter `qb_scramble_context: QbScrambleContextProtocol | None = None` to `resolve_play()` after `target_selection_context`.

Pass it into `_resolve_pass()` after `target_selection_context`.

Add the same parameter to `_resolve_pass()`.

Replace the current scramble check in `_resolve_pass()` with:

```python
        scramble_rate = passer.usage.scramble_rate
        if qb_scramble_context is not None:
            context_rate = qb_scramble_context.scramble_probability(state, passer)
            if context_rate is not None and np.isfinite(context_rate):
                scramble_rate = float(np.clip(context_rate, 0.0, 1.0))

        # QB scramble check: before sack/int, the QB decides to run.
        if scramble_rate > 0 and rng.random() < scramble_rate:
```

Modify `src/fantasy_sim/engine/game_sim.py` in the `resolve_play()` call:

```python
            target_selection_context=off_dists.target_selection_context,
            qb_scramble_context=off_dists.qb_scramble_context,
```

- [ ] **Step 5: Run engine tests and verify they pass**

Run:

```bash
uv run pytest tests/test_engine/test_play_resolver.py tests/test_engine/test_game_sim.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit engine wiring**

```bash
git add src/fantasy_sim/engine/types.py src/fantasy_sim/engine/play_resolver.py src/fantasy_sim/engine/game_sim.py tests/test_engine/test_play_resolver.py tests/test_engine/test_game_sim.py
git commit -m "feat: apply QB scramble context in engine"
```

---

### Task 6: Game Context, CLI, And Parallel Validation Plumbing

**Files:**
- Modify: `src/fantasy_sim/data/game_context.py`
- Modify: `src/fantasy_sim/cli.py`
- Modify: `src/fantasy_sim/validation/backtester.py`
- Modify: `src/fantasy_sim/validation/parallel.py`
- Modify: `tests/test_data/test_game_context.py`
- Modify: `tests/test_validation/test_parallel.py`

- [ ] **Step 1: Write failing GameContextBuilder tests**

Extend imports in `tests/test_data/test_game_context.py`:

```python
from fantasy_sim.data.qb_rushing import (
    QB_SCRAMBLE_MODEL_TYPE,
    QB_SCRAMBLE_SCHEMA_VERSION,
    QbRushingConfig,
    QbScrambleModelConfig,
)
```

Add tests near the play-call model tests:

```python
    def test_qb_scramble_model_created_when_enabled(self, tmp_path):
        builder = GameContextBuilder(
            cache_dir=tmp_path / "cache",
            qb_rushing_config=QbRushingConfig(
                scramble=QbScrambleModelConfig(enabled=True, artifacts_dir=str(tmp_path))
            ),
        )

        assert builder._qb_scramble_model is not None

    def test_qb_scramble_context_attached_when_artifact_exists(
        self, tmp_path, expanded_pbp, sample_rosters
    ):
        artifact = {
            "schema_version": QB_SCRAMBLE_SCHEMA_VERSION,
            "model_type": QB_SCRAMBLE_MODEL_TYPE,
            "target_season": 2024,
            "source_seasons": [2023],
            "feature_names": ["intercept"],
            "coefficients": {"intercept": 0.0},
            "factor_clamp": [0.50, 1.75],
            "probability_clamp": [0.0, 0.25],
            "priors": {"qb": {}, "team": {}, "opponent_allowed": {}, "league": 0.06},
        }
        (tmp_path / "qb_scramble_model_2024.json").write_text(
            json.dumps(artifact),
            encoding="utf-8",
        )
        builder = GameContextBuilder(
            cache_dir=tmp_path / "cache",
            qb_rushing_config=QbRushingConfig(
                scramble=QbScrambleModelConfig(enabled=True, artifacts_dir=str(tmp_path))
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

        assert home_dists.qb_scramble_context is not None
        assert away_dists.qb_scramble_context is not None
```

Extend `tests/test_validation/test_parallel.py` next to `test_build_games_parallel_accepts_play_call_model_config`:

```python
    @patch("fantasy_sim.validation.parallel.GameContextBuilder")
    def test_build_games_parallel_accepts_qb_rushing_config(self, mock_builder_cls):
        from fantasy_sim.validation.parallel import build_games_parallel

        mock_builder_cls.return_value = self._mock_builder()
        config = object()

        results = build_games_parallel(
            [("KC", "BUF", [2022, 2023], 2024, 1, "game_1", 42)],
            cache_dir=Path("/tmp"),
            qb_rushing_config=config,
            max_workers=1,
        )

        assert len(results) == 1
        assert mock_builder_cls.call_args.kwargs["qb_rushing_config"] is config
```

- [ ] **Step 2: Run plumbing tests and verify they fail**

Run:

```bash
uv run pytest tests/test_data/test_game_context.py::TestGameContextBuilder::test_qb_scramble_model_created_when_enabled tests/test_data/test_game_context.py::TestGameContextBuilder::test_qb_scramble_context_attached_when_artifact_exists tests/test_validation/test_parallel.py -v
```

Expected: FAIL because `GameContextBuilder` and parallel validation do not accept `qb_rushing_config`.

- [ ] **Step 3: Wire GameContextBuilder**

In `src/fantasy_sim/data/game_context.py`, add import:

```python
from fantasy_sim.data.qb_rushing import QbRushingConfig, QbScrambleModel
```

Add parameter to `GameContextBuilder.__init__()` after `play_call_model_config`:

```python
        qb_rushing_config: QbRushingConfig | None = None,
```

After play-call model setup, add:

```python
        self._qb_rushing_config = qb_rushing_config or QbRushingConfig()
        self._qb_scramble_model = None
        if self._qb_rushing_config.scramble.enabled:
            self._qb_scramble_model = QbScrambleModel(self._qb_rushing_config.scramble)
            logger.info("QB scramble model enabled")
```

In `build_game()`, after the play-call context block and before Vegas adjustments, add:

```python
        if self._qb_scramble_model is not None and target_season is not None:
            home_market, away_market = self._play_call_market_features(
                home_team,
                away_team,
                target_season,
                week,
            )
            context_week = week or 0
            home_dists.qb_scramble_context = self._qb_scramble_model.build_context(
                roster=home_roster,
                team=home_team,
                opponent=away_team,
                home_team=home_team,
                away_team=away_team,
                target_season=target_season,
                week=context_week,
                is_home=True,
                **home_market,
            )
            away_dists.qb_scramble_context = self._qb_scramble_model.build_context(
                roster=away_roster,
                team=away_team,
                opponent=home_team,
                home_team=home_team,
                away_team=away_team,
                target_season=target_season,
                week=context_week,
                is_home=False,
                **away_market,
            )
```

- [ ] **Step 4: Propagate config through CLI and validation**

In `src/fantasy_sim/cli.py`, import `load_qb_rushing_config`, load it in `_make_builder()`, and pass it to `GameContextBuilder` only when enabled:

```python
    qb_rushing_config = load_qb_rushing_config(defaults)
```

```python
        qb_rushing_config=qb_rushing_config if qb_rushing_config.scramble.enabled else None,
```

In `src/fantasy_sim/validation/backtester.py`, import `QbRushingConfig`, add `qb_rushing_config: QbRushingConfig | None = None` to `Backtester.__init__()`, store it as `self._qb_rushing_config`, and pass it to `build_games_parallel()`:

```python
            qb_rushing_config=self._qb_rushing_config,
```

In `src/fantasy_sim/validation/parallel.py`, add `qb_rushing_config: "QbRushingConfig | None" = None` to every worker initializer and to `build_games_parallel()`. Pass it through every `GameContextBuilder(...)` call:

```python
            qb_rushing_config=qb_rushing_config,
```

Run this search and update every match in `parallel.py`:

```bash
rg "play_call_model_config" src/fantasy_sim/validation/parallel.py
```

Expected: every function signature or builder call that threads `play_call_model_config` also threads `qb_rushing_config`.

- [ ] **Step 5: Run plumbing tests and verify they pass**

Run:

```bash
uv run pytest tests/test_data/test_game_context.py tests/test_validation/test_parallel.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit context plumbing**

```bash
git add src/fantasy_sim/data/game_context.py src/fantasy_sim/cli.py src/fantasy_sim/validation/backtester.py src/fantasy_sim/validation/parallel.py tests/test_data/test_game_context.py tests/test_validation/test_parallel.py
git commit -m "feat: attach QB scramble contexts"
```

---

### Task 7: Validation Coverage Reporting

**Files:**
- Modify: `src/fantasy_sim/validation/coverage.py`
- Modify: `tests/test_validation/test_coverage.py`

- [ ] **Step 1: Write failing coverage tests**

In `tests/test_validation/test_coverage.py`, add tests near the play-call model coverage tests:

```python
def test_qb_scramble_coverage_disabled_by_default(tmp_path):
    coverage = collect_signal_coverage(
        config={"qb_rushing": {"scramble": {"enabled": False}}},
        test_seasons=[2024],
        cache_dir=tmp_path,
    )

    assert coverage["qb_rushing.scramble"].enabled is False
    assert coverage["qb_rushing.scramble"].status == "disabled"


def test_qb_scramble_coverage_requires_valid_artifact(tmp_path):
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    (artifact_dir / "qb_scramble_model_2024.json").write_text(
        json.dumps(
            {
                "schema_version": QB_SCRAMBLE_SCHEMA_VERSION,
                "model_type": QB_SCRAMBLE_MODEL_TYPE,
                "target_season": 2024,
                "source_seasons": [2023],
                "feature_names": ["intercept"],
                "coefficients": {"intercept": 0.0},
            }
        ),
        encoding="utf-8",
    )

    coverage = collect_signal_coverage(
        config={
            "qb_rushing": {
                "scramble": {
                    "enabled": True,
                    "artifacts_dir": str(artifact_dir),
                }
            }
        },
        test_seasons=[2024],
        cache_dir=tmp_path,
    )

    assert coverage["qb_rushing.scramble"].enabled is True
    assert coverage["qb_rushing.scramble"].covered_seasons == [2024]
    assert coverage["qb_rushing.scramble"].missing_seasons == []
```

Add imports at the top of that file if they are not present:

```python
import json

from fantasy_sim.data.qb_rushing import QB_SCRAMBLE_MODEL_TYPE, QB_SCRAMBLE_SCHEMA_VERSION
```

- [ ] **Step 2: Run coverage tests and verify they fail**

Run:

```bash
uv run pytest tests/test_validation/test_coverage.py -k "qb_scramble or qb_rushing" -v
```

Expected: FAIL because coverage has no `qb_rushing.scramble` entry.

- [ ] **Step 3: Add coverage validator**

In `src/fantasy_sim/validation/coverage.py`, import QB constants:

```python
from fantasy_sim.data.qb_rushing.models import (
    DEFAULT_ARTIFACT_DIR as QB_SCRAMBLE_DEFAULT_ARTIFACT_DIR,
    DEFAULT_QB_SCRAMBLE_FEATURES,
    QB_SCRAMBLE_MODEL_TYPE,
    QB_SCRAMBLE_SCHEMA_VERSION,
)
```

Add path resolver after `_resolve_play_call_model_artifacts_path()`:

```python
def _resolve_qb_scramble_artifacts_path(config: object) -> Path:
    qb_rushing_config = _config_section(config, "qb_rushing_config")
    if qb_rushing_config is None:
        qb_rushing_config = _config_section(config, "qb_rushing")
    scramble_config = _config_get(qb_rushing_config, "scramble", default=None)
    artifacts_dir = (
        _config_get(scramble_config, "artifacts_dir", default=None)
        if scramble_config is not None
        else None
    )
    if artifacts_dir is not None:
        return _path_or_default(artifacts_dir, QB_SCRAMBLE_DEFAULT_ARTIFACT_DIR)
    return QB_SCRAMBLE_DEFAULT_ARTIFACT_DIR
```

Add artifact validator after `_play_call_model_artifact_is_valid()`:

```python
def _qb_scramble_artifact_is_valid(path: Path, expected_season: int) -> bool:
    if not path.exists():
        return False
    try:
        artifact = json.loads(path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    if not isinstance(artifact, Mapping):
        return False
    if artifact.get("schema_version") != QB_SCRAMBLE_SCHEMA_VERSION:
        return False
    if artifact.get("model_type") != QB_SCRAMBLE_MODEL_TYPE:
        return False
    if artifact.get("target_season") != expected_season:
        return False
    if not _play_call_source_seasons_are_safe(artifact.get("source_seasons"), expected_season):
        return False
    feature_names = artifact.get("feature_names")
    coefficients = artifact.get("coefficients")
    if not isinstance(feature_names, list) or not feature_names:
        return False
    if not all(isinstance(name, str) for name in feature_names):
        return False
    if any(name not in DEFAULT_QB_SCRAMBLE_FEATURES for name in feature_names):
        return False
    if not isinstance(coefficients, Mapping):
        return False
    if set(coefficients) != set(feature_names):
        return False
    try:
        parsed = [float(value) for value in coefficients.values()]
    except (TypeError, ValueError):
        return False
    return all(math.isfinite(value) for value in parsed)
```

Add covered-season helper:

```python
def _covered_seasons_from_qb_scramble_artifacts(
    test_seasons: Iterable[int],
    paths_by_season: Mapping[int, Path],
) -> list[int]:
    return [
        season
        for season in test_seasons
        if (path := paths_by_season.get(season)) is not None
        and _qb_scramble_artifact_is_valid(path, season)
    ]
```

Inside `collect_signal_coverage()`, add enabled flag near play-call model:

```python
    qb_scramble_enabled = _signal_enabled(
        config,
        ("qb_rushing_config", "qb_rushing"),
        ("qb_rushing", "scramble"),
        nested_path=("scramble",),
    )
```

Add artifact path map near play-call model paths:

```python
    qb_scramble_artifacts_path = _resolve_qb_scramble_artifacts_path(config)
    qb_scramble_artifact_paths: dict[int, Path] = {
        season: qb_scramble_artifacts_path / f"qb_scramble_model_{season}.json"
        for season in seasons
    }
```

Add signal entry before `ensemble.ff_opportunity`:

```python
        "qb_rushing.scramble": _build_signal(
            qb_scramble_enabled,
            seasons,
            _covered_seasons_from_qb_scramble_artifacts(
                seasons,
                qb_scramble_artifact_paths,
            ),
            note=(
                "Requires qb_scramble_model_<season>.json artifacts fitted from "
                "prior-season PBP scramble labels; runtime falls back to base "
                "QB scramble_rate when an artifact is missing or invalid"
            ),
        ),
```

- [ ] **Step 4: Run coverage tests and verify they pass**

Run:

```bash
uv run pytest tests/test_validation/test_coverage.py -k "qb_scramble or qb_rushing" -v
```

Expected: PASS.

- [ ] **Step 5: Commit coverage reporting**

```bash
git add src/fantasy_sim/validation/coverage.py tests/test_validation/test_coverage.py
git commit -m "feat: report QB scramble artifact coverage"
```

---

### Task 8: Full Verification, Validation Commands, And Documentation

**Files:**
- Modify: `AGENTS.md`
- Review: `docs/hypotheses-list.md`

- [ ] **Step 1: Run focused unit suites**

Run:

```bash
uv run pytest tests/test_data/test_qb_rushing tests/test_scripts/test_fit_qb_scramble_model.py tests/test_engine/test_play_resolver.py tests/test_engine/test_game_sim.py tests/test_data/test_game_context.py tests/test_validation/test_config.py tests/test_validation/test_coverage.py tests/test_validation/test_parallel.py -v
```

Expected: PASS.

- [ ] **Step 2: Run full test suite**

Run:

```bash
uv run pytest tests/ -v
```

Expected: PASS.

- [ ] **Step 3: Fit smoke artifacts**

Run:

```bash
uv run python scripts/fit_qb_scramble_model.py \
  --test-seasons 2022 2023 2024 \
  --min-source-season 2018 \
  --training-years 4 \
  --output-dir results/qb_rushing/scramble/smoke_v1
```

Expected: writes `qb_scramble_model_2022.json`, `qb_scramble_model_2023.json`, and `qb_scramble_model_2024.json`, each with `diagnostics.num_examples >= 500` and a finite `diagnostics.scramble_rate`.

- [ ] **Step 4: Run 50-sim A/B validation**

Run:

```bash
uv run python scripts/validate.py \
  --baseline defaults \
  --sims 50 \
  --set qb_rushing.scramble.enabled=true \
  --set qb_rushing.scramble.artifacts_dir=results/qb_rushing/scramble/smoke_v1 \
  --label qb-scramble-model-s50
```

Expected: validation completes and coverage output includes `qb_rushing.scramble` as covered for artifact seasons.

- [ ] **Step 5: Run 200-sim decision validation only if smoke is non-negative**

Use this gate before running the decision command: average rank correlation is non-negative versus defaults and weekly MAE is not worse than defaults in the 50-sim run.

Run:

```bash
uv run python scripts/validate.py \
  --baseline defaults \
  --sims 200 \
  --set qb_rushing.scramble.enabled=true \
  --set qb_rushing.scramble.artifacts_dir=results/qb_rushing/scramble/smoke_v1 \
  --label qb-scramble-model-s200
```

Expected: validation completes. Promotion requires overall rank-correlation delta at least `+0.0030`, weekly MAE delta at most `-0.025`, improved QB weekly rank correlation, improved QB weekly MAE, no material RB regression, and no worse QB rushing-yards KS.

- [ ] **Step 6: Update docs with implemented state**

Add a line to `AGENTS.md` under `Current State`:

```markdown
- QB scramble model implemented off-by-default: `qb_rushing.scramble.enabled=false`, with temporal artifacts loaded from `qb_rushing.scramble.artifacts_dir` and fallback to base QB `scramble_rate` when artifacts are missing or invalid
```

If the 200-sim decision run meets the promotion gate, update `docs/hypotheses-list.md` from Open to Done for hypothesis 7 and record the exact ledger numbers from the validation output. If it misses the gate, add a No Promotion subsection with the exact validation label and metric deltas from the output. Do not change defaults unless the promotion gate passes.

- [ ] **Step 7: Commit documentation and validation notes**

```bash
git add AGENTS.md docs/hypotheses-list.md
git commit -m "docs: record QB scramble model status"
```

Skip this commit if neither file changed because validation did not complete in the implementation session.

---

## Self-Review Checklist

- The plan covers the approved spec's scope: scramble probability only.
- The plan keeps defaults disabled and preserves fallback to base `scramble_rate`.
- The plan does not change designed QB run selection, `MIN_QB_CARRY_SHARE`, or scramble-yard sampling.
- The plan includes config, training, runtime loading, engine wiring, validation coverage, fitting, A/B validation, and docs.
- The runtime model uses prior-season artifacts and rejects unsafe target-season source seasons.
- The plan includes tests before implementation steps and commit points after passing tests.

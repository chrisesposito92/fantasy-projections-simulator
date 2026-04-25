# QB Designed-Run Chain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an off-by-default QB designed-run chain that adjusts eligible QB designed-run selection and QB designed-run yard tails without changing scramble probability.

**Architecture:** Extend the existing `fantasy_sim.data.qb_rushing` package with a second model family, `designed_runs`. Runtime attaches an optional context to `TeamDistributions`; `select_rusher()` uses it to adjust only eligible QB weights, and `_resolve_run()` uses it only when a QB was selected on a designed run.

**Tech Stack:** Python 3.12, dataclasses, numpy, scipy L-BFGS, polars, pytest, JSON artifacts, existing validation coverage reporting.

---

## Scope Check

This is one subsystem: the QB designed-run chain. It touches config, training, artifact loading, engine runtime wiring, script generation, and validation coverage. It does not modify `qb_rushing.scramble`, pass/run play calling, receiver selection, RB yard distributions, or promoted defaults.

## File Structure

- Modify: `config/defaults.yaml`
  Add default-off `qb_rushing.designed_runs` config.
- Modify: `src/fantasy_sim/data/qb_rushing/models.py`
  Add constants, config dataclass, runtime context, feature builder, mobility-tier helpers, and tail-bucket helpers for designed runs.
- Modify: `src/fantasy_sim/data/qb_rushing/config.py`
  Parse `qb_rushing.designed_runs` with clamp and minimum-sample validation.
- Modify: `src/fantasy_sim/data/qb_rushing/training.py`
  Add designed-run priors, examples, logistic fitting, tail-bucket building, and roster-position annotation helpers.
- Modify: `src/fantasy_sim/data/qb_rushing/runtime.py`
  Add a runtime loader for `qb_designed_run_model_<season>.json` artifacts.
- Modify: `src/fantasy_sim/data/qb_rushing/__init__.py`
  Export the new config, constants, model, context, and training helpers.
- Add: `scripts/fit_qb_designed_run_model.py`
  Fit one temporal JSON artifact per target season.
- Modify: `src/fantasy_sim/engine/types.py`
  Add `QbDesignedRunContextProtocol` and `TeamDistributions.qb_designed_run_context`.
- Modify: `src/fantasy_sim/engine/player_selector.py`
  Let `select_rusher()` pass eligible rusher candidates through the optional QB designed-run context.
- Modify: `src/fantasy_sim/engine/play_resolver.py`
  Thread the context into `_resolve_run()` and ask it for QB-designed-run yards after a QB is selected.
- Modify: `src/fantasy_sim/engine/game_sim.py`
  Thread `off_dists.qb_designed_run_context` into `resolve_play()`.
- Modify: `src/fantasy_sim/data/game_context.py`
  Instantiate `QbDesignedRunModel` when enabled and attach per-team contexts when valid artifacts exist.
- Modify: `src/fantasy_sim/validation/coverage.py`
  Report `qb_rushing.designed_runs` coverage.
- Modify tests under `tests/test_data/test_qb_rushing/`, `tests/test_engine/`, `tests/test_data/test_game_context.py`, `tests/test_validation/test_coverage.py`, and `tests/test_scripts/`.

## Tasks

### Task 1: Config And Model Contracts

**Files:**
- Modify: `tests/test_data/test_qb_rushing/test_config.py`
- Modify: `tests/test_data/test_qb_rushing/test_models.py`
- Modify: `src/fantasy_sim/data/qb_rushing/models.py`
- Modify: `src/fantasy_sim/data/qb_rushing/config.py`
- Modify: `src/fantasy_sim/data/qb_rushing/__init__.py`
- Modify: `config/defaults.yaml`

- [ ] **Step 1: Write failing config tests**

Add these tests to `tests/test_data/test_qb_rushing/test_config.py`:

```python
def test_missing_config_disables_designed_runs():
    config = load_qb_rushing_config({})

    assert config.designed_runs.enabled is False
    assert config.designed_runs.artifacts_dir is None
    assert config.designed_runs.factor_clamp == (0.50, 2.00)
    assert config.designed_runs.min_examples == 500
    assert config.designed_runs.min_tail_samples == 20


def test_loads_designed_run_config_values():
    config = load_qb_rushing_config(
        {
            "qb_rushing": {
                "designed_runs": {
                    "enabled": True,
                    "artifacts_dir": "results/qb_rushing/designed_runs/test",
                    "factor_clamp": [0.75, 1.60],
                    "min_examples": 250,
                    "min_tail_samples": 12,
                }
            }
        }
    )

    assert config.designed_runs.enabled is True
    assert config.designed_runs.artifacts_dir == "results/qb_rushing/designed_runs/test"
    assert config.designed_runs.factor_clamp == (0.75, 1.60)
    assert config.designed_runs.min_examples == 250
    assert config.designed_runs.min_tail_samples == 12


@pytest.mark.parametrize(
    "clamp",
    [[0.50], [2.00, 0.50], [-0.01, 2.00], [0.50, float("inf")]],
)
def test_invalid_designed_run_factor_clamp_raises(clamp):
    with pytest.raises(ValueError, match="qb_rushing\\.designed_runs\\.factor_clamp"):
        load_qb_rushing_config(
            {"qb_rushing": {"designed_runs": {"factor_clamp": clamp}}}
        )


@pytest.mark.parametrize("field", ["min_examples", "min_tail_samples"])
def test_invalid_designed_run_minimums_raise(field):
    with pytest.raises(ValueError, match=f"qb_rushing\\.designed_runs\\.{field}"):
        load_qb_rushing_config(
            {"qb_rushing": {"designed_runs": {field: 0}}}
        )
```

- [ ] **Step 2: Write failing model tests**

Add these imports to `tests/test_data/test_qb_rushing/test_models.py`:

```python
from fantasy_sim.data.qb_rushing.models import (
    DEFAULT_QB_DESIGNED_RUN_FEATURES,
    QbDesignedRunContext,
    qb_designed_run_feature_values,
)
```

Add these tests to the same file:

```python
def _designed_qb(carry_share=0.12):
    return PlayerModel(
        "QB1",
        "Mobile QB",
        "QB",
        "BUF",
        PlayerUsage(snap_share=1.0, carry_share=carry_share, scramble_rate=0.08),
        PlayerOutcomes(rushing_yards_dist=np.array([4, 7, 11])),
    )


def test_designed_run_feature_values_include_state_market_priors_and_tier():
    values = qb_designed_run_feature_values(
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
        qb_prior_designed_run_share=0.12,
        team_prior_designed_qb_run_rate=0.08,
        opponent_prior_designed_qb_run_allowed=0.07,
        mobility_tier="high",
    )

    assert set(DEFAULT_QB_DESIGNED_RUN_FEATURES).issubset(values)
    assert values["down_3"] == 1.0
    assert values["is_red_zone"] == 1.0
    assert values["is_two_minute"] == 1.0
    assert values["is_trailing"] == 1.0
    assert values["is_home"] == 0.0
    assert values["spread_norm"] == pytest.approx(-3.0 / 14.0)
    assert values["qb_prior_designed_run_share"] == pytest.approx(0.12)
    assert values["mobility_high"] == 1.0


def test_designed_run_context_adjusts_only_qb_weight():
    context = QbDesignedRunContext(
        coefficients={"intercept": 10.0},
        feature_names=("intercept",),
        tail_buckets={},
        global_tail_yards=(5, 8),
        team="BUF",
        opponent="KC",
        home_team="KC",
        away_team="BUF",
        is_home=False,
        target_season=2024,
        week=9,
        factor_clamp=(0.50, 2.00),
    )
    qb = _designed_qb(carry_share=0.12)
    rb = PlayerModel(
        "RB1",
        "RB",
        "RB",
        "BUF",
        PlayerUsage(carry_share=0.60),
        PlayerOutcomes(rushing_yards_dist=np.array([4])),
    )

    adjusted = context.rusher_weights(
        [qb, rb],
        np.array([0.12, 0.60], dtype=float),
        _state(),
    )

    assert adjusted is not None
    assert adjusted[0] == pytest.approx(0.24)
    assert adjusted[1] == pytest.approx(0.60)


def test_designed_run_context_samples_tail_yards_for_qb_only():
    context = QbDesignedRunContext(
        coefficients={"intercept": 0.0},
        feature_names=("intercept",),
        tail_buckets={},
        global_tail_yards=(12,),
        team="BUF",
        opponent="KC",
        home_team="KC",
        away_team="BUF",
        is_home=False,
        target_season=2024,
        week=9,
    )
    qb = _designed_qb()
    rb = PlayerModel("RB1", "RB", "RB", "BUF", PlayerUsage(carry_share=1.0), PlayerOutcomes())

    assert context.designed_run_yards(_state(), qb, np.random.default_rng(1)) == 12
    assert context.designed_run_yards(_state(), rb, np.random.default_rng(1)) is None
```

- [ ] **Step 3: Run the new tests and verify failure**

Run:

```bash
uv run pytest tests/test_data/test_qb_rushing/test_config.py tests/test_data/test_qb_rushing/test_models.py -v
```

Expected: FAIL because `designed_runs`, `QbDesignedRunContext`, and `qb_designed_run_feature_values` do not exist.

- [ ] **Step 4: Add designed-run config and model code**

In `src/fantasy_sim/data/qb_rushing/models.py`, add constants next to the scramble constants:

```python
QB_DESIGNED_RUN_SCHEMA_VERSION = 1
QB_DESIGNED_RUN_MODEL_TYPE = "offset_logistic_qb_designed_run_v1"
DEFAULT_QB_DESIGNED_RUN_ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts" / "designed_run_v1"

DEFAULT_QB_DESIGNED_RUN_FEATURES: tuple[str, ...] = (
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
    "qb_prior_designed_run_share",
    "team_prior_designed_qb_run_rate",
    "opponent_prior_designed_qb_run_allowed",
    "mobility_low",
    "mobility_medium",
    "mobility_high",
)
```

Add the config dataclass and extend `QbRushingConfig`:

```python
@dataclass(frozen=True)
class QbDesignedRunModelConfig:
    """Configuration for learned QB designed-run selection and yard tails."""

    enabled: bool = False
    artifacts_dir: str | None = None
    factor_clamp: tuple[float, float] = (0.50, 2.00)
    min_examples: int = 500
    min_tail_samples: int = 20


@dataclass(frozen=True)
class QbRushingConfig:
    """Configuration for QB rushing model layers."""

    scramble: QbScrambleModelConfig = field(default_factory=QbScrambleModelConfig)
    designed_runs: QbDesignedRunModelConfig = field(default_factory=QbDesignedRunModelConfig)
```

Add the context and feature helpers below `QbScrambleContext`:

```python
@dataclass(frozen=True)
class QbDesignedRunContext:
    """Runtime context for a team's learned QB designed-run artifact."""

    coefficients: dict[str, float]
    feature_names: tuple[str, ...]
    tail_buckets: dict[str, tuple[int, ...]]
    global_tail_yards: tuple[int, ...]
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
    team_prior_designed_qb_run_rate: float = 0.05
    opponent_prior_designed_qb_run_allowed: float = 0.05
    mobility_tiers: dict[str, str] = field(default_factory=dict)
    factor_clamp: tuple[float, float] = (0.50, 2.00)
    min_tail_samples: int = 20

    def rusher_weights(
        self,
        players: list["PlayerModel"],
        legacy_weights: np.ndarray,
        state: "GameState",
        script: object | None = None,
    ) -> np.ndarray | None:
        del script
        weights = np.asarray(legacy_weights, dtype=float).copy()
        if len(players) != len(weights) or not np.all(np.isfinite(weights)):
            return None
        for idx, player in enumerate(players):
            if player.position != "QB" or weights[idx] <= 0.0:
                continue
            factor = self._factor_for_qb(state, player)
            if factor is None:
                continue
            weights[idx] *= factor
        return weights if np.all(np.isfinite(weights)) else None

    def designed_run_yards(
        self,
        state: "GameState",
        rusher: "PlayerModel",
        rng: np.random.Generator,
        script: object | None = None,
    ) -> int | None:
        del script
        if rusher.position != "QB":
            return None
        key = qb_designed_run_tail_key(
            state,
            mobility_tier=self.mobility_tiers.get(rusher.player_id, "medium"),
        )
        yards = self.tail_buckets.get(key, ())
        if len(yards) < self.min_tail_samples:
            yards = self.tail_buckets.get("global", self.global_tail_yards)
        if not yards:
            return None
        return int(rng.choice(np.array(yards, dtype=int)))

    def _factor_for_qb(self, state: "GameState", qb: "PlayerModel") -> float | None:
        values = qb_designed_run_feature_values(
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
            qb_prior_designed_run_share=float(qb.usage.carry_share),
            team_prior_designed_qb_run_rate=self.team_prior_designed_qb_run_rate,
            opponent_prior_designed_qb_run_allowed=self.opponent_prior_designed_qb_run_allowed,
            mobility_tier=self.mobility_tiers.get(qb.player_id, "medium"),
        )
        delta = 0.0
        for name in self.feature_names:
            delta += float(self.coefficients.get(name, 0.0)) * values.get(name, 0.0)
        if not np.isfinite(delta):
            return None
        lo, hi = self.factor_clamp
        return float(np.clip(np.exp(np.clip(delta, -4.0, 4.0)), lo, hi))


def qb_designed_run_feature_values(
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
    qb_prior_designed_run_share: float,
    team_prior_designed_qb_run_rate: float,
    opponent_prior_designed_qb_run_allowed: float,
    mobility_tier: str,
) -> dict[str, float]:
    values = qb_scramble_feature_values(
        state,
        team=team,
        opponent=opponent,
        home_team=home_team,
        away_team=away_team,
        is_home=is_home,
        week=week,
        spread_line=spread_line,
        total_line=total_line,
        implied_team_total=implied_team_total,
        qb_prior_scramble_rate=0.0,
        team_prior_scramble_rate=0.0,
        opponent_prior_scramble_rate_allowed=0.0,
    )
    values.pop("qb_prior_scramble_rate", None)
    values.pop("team_prior_scramble_rate", None)
    values.pop("opponent_prior_scramble_rate_allowed", None)
    tier = mobility_tier if mobility_tier in {"low", "medium", "high"} else "medium"
    values.update(
        {
            "qb_prior_designed_run_share": float(np.clip(qb_prior_designed_run_share, 0.0, 1.0)),
            "team_prior_designed_qb_run_rate": float(np.clip(team_prior_designed_qb_run_rate, 0.0, 1.0)),
            "opponent_prior_designed_qb_run_allowed": float(
                np.clip(opponent_prior_designed_qb_run_allowed, 0.0, 1.0)
            ),
            "mobility_low": 1.0 if tier == "low" else 0.0,
            "mobility_medium": 1.0 if tier == "medium" else 0.0,
            "mobility_high": 1.0 if tier == "high" else 0.0,
        }
    )
    return values


def mobility_tier_from_rates(designed_run_share: float, scramble_rate: float) -> str:
    score = float(designed_run_share) + float(scramble_rate)
    if score >= 0.18:
        return "high"
    if score >= 0.08:
        return "medium"
    return "low"


def qb_designed_run_tail_key(state: "GameState", *, mobility_tier: str) -> str:
    tier = mobility_tier if mobility_tier in {"low", "medium", "high"} else "medium"
    rz = "rz" if int(state.yard_line) <= 20 else "field"
    short = "short" if int(state.distance) <= 3 else "open"
    if state.score_differential <= -7:
        script = "trailing"
    elif state.score_differential >= 7:
        script = "leading"
    else:
        script = "neutral"
    return f"{tier}|{rz}|{short}|{script}"
```

In `src/fantasy_sim/data/qb_rushing/config.py`, import `QbDesignedRunModelConfig`, parse `designed_runs_raw`, and pass it to `QbRushingConfig`:

```python
from fantasy_sim.data.qb_rushing.models import (
    QbDesignedRunModelConfig,
    QbRushingConfig,
    QbScrambleModelConfig,
)
```

```python
    designed_runs_raw = raw.get("designed_runs") or {}
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
```

```python
        designed_runs=QbDesignedRunModelConfig(
            enabled=bool(designed_runs_raw.get("enabled", False)),
            artifacts_dir=designed_runs_raw.get("artifacts_dir"),
            factor_clamp=designed_run_factor_clamp,
            min_examples=designed_run_min_examples,
            min_tail_samples=min_tail_samples,
        ),
```

In `config/defaults.yaml`, add this under `qb_rushing:` after `scramble:`:

```yaml
  designed_runs:
    enabled: false
    artifacts_dir: null
    factor_clamp: [0.50, 2.00]
    min_examples: 500
    min_tail_samples: 20
```

In `src/fantasy_sim/data/qb_rushing/__init__.py`, export the new names used by tests and later tasks.

- [ ] **Step 5: Run tests for Task 1**

Run:

```bash
uv run pytest tests/test_data/test_qb_rushing/test_config.py tests/test_data/test_qb_rushing/test_models.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit Task 1**

```bash
git add config/defaults.yaml src/fantasy_sim/data/qb_rushing/models.py src/fantasy_sim/data/qb_rushing/config.py src/fantasy_sim/data/qb_rushing/__init__.py tests/test_data/test_qb_rushing/test_config.py tests/test_data/test_qb_rushing/test_models.py
git commit -m "feat: add QB designed-run model contracts"
```

### Task 2: Training Helpers For Designed Runs And Tail Buckets

**Files:**
- Modify: `tests/test_data/test_qb_rushing/test_training.py`
- Modify: `src/fantasy_sim/data/qb_rushing/training.py`
- Modify: `src/fantasy_sim/data/qb_rushing/__init__.py`

- [ ] **Step 1: Write failing training tests**

Add these imports to `tests/test_data/test_qb_rushing/test_training.py`:

```python
from fantasy_sim.data.qb_rushing.models import DEFAULT_QB_DESIGNED_RUN_FEATURES
from fantasy_sim.data.qb_rushing.training import (
    QbDesignedRunTrainingExample,
    annotate_rusher_positions,
    build_designed_run_example_from_row,
    build_designed_run_priors,
    build_designed_run_tail_buckets,
    fit_logistic_qb_designed_run,
)
```

Add these tests:

```python
def _designed_run_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "season": 2023,
        "week": 5,
        "posteam": "BUF",
        "defteam": "KC",
        "home_team": "KC",
        "away_team": "BUF",
        "play_type": "run",
        "rusher_player_id": "QB1",
        "rusher_position": "QB",
        "qb_scramble": 0,
        "qb_kneel": 0,
        "qb_spike": 0,
        "no_play": 0,
        "yards_gained": 12,
        "down": 3,
        "ydstogo": 2,
        "yardline_100": 18,
        "qtr": 4,
        "quarter_seconds_remaining": 118,
        "score_differential": -6,
        "spread_line": 2.5,
        "total_line": 48.5,
    }
    row.update(overrides)
    return row


def test_annotate_rusher_positions_uses_roster_position():
    rows = [_designed_run_row(rusher_position=None)]
    positions = {"QB1": "QB"}

    annotated = annotate_rusher_positions(rows, positions)

    assert annotated[0]["rusher_position"] == "QB"


def test_build_designed_run_priors_excludes_scrambles_and_kneels():
    priors = build_designed_run_priors(
        [
            _designed_run_row(rusher_player_id="QB1", rusher_position="QB", qb_scramble=0),
            _designed_run_row(rusher_player_id="RB1", rusher_position="RB", qb_scramble=0),
            _designed_run_row(rusher_player_id="QB1", rusher_position="QB", qb_scramble=1),
            _designed_run_row(rusher_player_id="QB1", rusher_position="QB", qb_kneel=1),
        ]
    )

    assert priors.league == pytest.approx(0.5)
    assert priors.team["BUF"] == pytest.approx(0.5)
    assert priors.opponent_allowed["KC"] == pytest.approx(0.5)
    assert priors.qb["QB1"] == pytest.approx(1.0)


def test_build_designed_run_example_from_row_uses_qb_label_and_features():
    rows = [
        _designed_run_row(rusher_player_id="QB1", rusher_position="QB"),
        _designed_run_row(rusher_player_id="RB1", rusher_position="RB"),
    ]
    priors = build_designed_run_priors(rows)

    example = build_designed_run_example_from_row(
        rows[0],
        DEFAULT_QB_DESIGNED_RUN_FEATURES,
        priors,
    )

    assert example is not None
    assert example.label == 1
    assert example.base_rate == pytest.approx(0.5)
    assert example.features.shape == (len(DEFAULT_QB_DESIGNED_RUN_FEATURES),)
    assert np.isfinite(example.features).all()


def test_build_designed_run_example_skips_scrambles_and_non_run_rows():
    priors = build_designed_run_priors([_designed_run_row()])

    assert build_designed_run_example_from_row(
        _designed_run_row(qb_scramble=1),
        DEFAULT_QB_DESIGNED_RUN_FEATURES,
        priors,
    ) is None
    assert build_designed_run_example_from_row(
        _designed_run_row(play_type="pass"),
        DEFAULT_QB_DESIGNED_RUN_FEATURES,
        priors,
    ) is None


def test_fit_logistic_qb_designed_run_learns_positive_feature():
    examples = [
        QbDesignedRunTrainingExample(
            features=np.array([1.0, 1.0]),
            label=1,
            base_rate=0.10,
        )
        for _ in range(30)
    ] + [
        QbDesignedRunTrainingExample(
            features=np.array([1.0, 0.0]),
            label=0,
            base_rate=0.10,
        )
        for _ in range(30)
    ]

    result = fit_logistic_qb_designed_run(
        examples,
        ("intercept", "mobile_feature"),
        l2=0.1,
        max_iter=100,
    )

    assert result.num_examples == 60
    assert result.coefficients["mobile_feature"] > 0
    assert result.converged is True


def test_build_designed_run_tail_buckets_uses_only_qb_designed_rows():
    buckets = build_designed_run_tail_buckets(
        [
            _designed_run_row(rusher_player_id="QB1", rusher_position="QB", yards_gained=12),
            _designed_run_row(rusher_player_id="QB1", rusher_position="QB", yards_gained=7),
            _designed_run_row(rusher_player_id="QB1", rusher_position="QB", qb_scramble=1, yards_gained=40),
            _designed_run_row(rusher_player_id="RB1", rusher_position="RB", yards_gained=99),
        ],
        mobility_tiers={"QB1": "high"},
    )

    assert buckets["global"] == (12, 7)
    assert 40 not in buckets["global"]
    assert 99 not in buckets["global"]
```

- [ ] **Step 2: Run training tests and verify failure**

Run:

```bash
uv run pytest tests/test_data/test_qb_rushing/test_training.py -v
```

Expected: FAIL because designed-run training helpers are not defined.

- [ ] **Step 3: Add training dataclasses and helpers**

In `src/fantasy_sim/data/qb_rushing/training.py`, import the new model helpers:

```python
from fantasy_sim.data.qb_rushing.models import (
    _logit,
    mobility_tier_from_rates,
    qb_designed_run_feature_values,
    qb_designed_run_tail_key,
    qb_scramble_feature_values,
)
```

Add dataclasses near the existing scramble dataclasses:

```python
@dataclass(frozen=True)
class QbDesignedRunPriors:
    qb: dict[str, float]
    team: dict[str, float]
    opponent_allowed: dict[str, float]
    league: float
    mobility_tiers: dict[str, str]
    qb_counts: dict[str, tuple[int, int]] = field(default_factory=dict, repr=False, compare=False)
    team_counts: dict[str, tuple[int, int]] = field(default_factory=dict, repr=False, compare=False)
    opponent_allowed_counts: dict[str, tuple[int, int]] = field(default_factory=dict, repr=False, compare=False)
    league_counts: tuple[int, int] = field(default=(0, 0), repr=False, compare=False)


@dataclass(frozen=True)
class QbDesignedRunTrainingExample:
    features: np.ndarray
    label: int
    base_rate: float


@dataclass(frozen=True)
class QbDesignedRunFitResult:
    coefficients: dict[str, float]
    objective: float
    converged: bool
    iterations: int
    num_examples: int
```

Add helpers below the scramble fit function:

```python
def annotate_rusher_positions(
    rows: list[Mapping[str, object]],
    positions_by_player_id: Mapping[str, str],
) -> list[dict[str, object]]:
    annotated: list[dict[str, object]] = []
    for row in rows:
        copied = dict(row)
        rusher_id = copied.get("rusher_player_id")
        if copied.get("rusher_position") in (None, "") and rusher_id not in (None, ""):
            copied["rusher_position"] = positions_by_player_id.get(str(rusher_id))
        annotated.append(copied)
    return annotated


def build_designed_run_priors(rows: list[Mapping[str, object]]) -> QbDesignedRunPriors:
    qb_counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    team_counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    opponent_counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    qb_designed_counts: dict[str, int] = defaultdict(int)
    qb_total_counts: dict[str, int] = defaultdict(int)
    league_qb_runs = 0
    league_total = 0

    for row in rows:
        if not _is_designed_run_row(row):
            continue
        label = _designed_qb_run_label(row)
        rusher_id = row.get("rusher_player_id")
        team = row.get("posteam")
        opponent = row.get("defteam")
        league_qb_runs += label
        league_total += 1
        if rusher_id not in (None, ""):
            player_key = str(rusher_id)
            qb_total_counts[player_key] += 1
            qb_designed_counts[player_key] += label
            if label == 1:
                qb_counts[player_key][0] += label
                qb_counts[player_key][1] += 1
        if team is not None:
            team_counts[str(team)][0] += label
            team_counts[str(team)][1] += 1
        if opponent is not None:
            opponent_counts[str(opponent)][0] += label
            opponent_counts[str(opponent)][1] += 1

    league = league_qb_runs / league_total if league_total else 0.0
    qb_rates = {
        key: qb_designed_counts[key] / max(total, 1)
        for key, total in qb_total_counts.items()
        if key in qb_designed_counts
    }
    mobility_tiers = {
        key: mobility_tier_from_rates(rate, 0.0)
        for key, rate in qb_rates.items()
    }
    return QbDesignedRunPriors(
        qb=qb_rates,
        team={key: counts[0] / counts[1] for key, counts in team_counts.items()},
        opponent_allowed={key: counts[0] / counts[1] for key, counts in opponent_counts.items()},
        league=league,
        mobility_tiers=mobility_tiers,
        qb_counts={key: (counts[0], counts[1]) for key, counts in qb_counts.items()},
        team_counts={key: (counts[0], counts[1]) for key, counts in team_counts.items()},
        opponent_allowed_counts={key: (counts[0], counts[1]) for key, counts in opponent_counts.items()},
        league_counts=(league_qb_runs, league_total),
    )


def build_designed_run_example_from_row(
    row: Mapping[str, object],
    feature_names: tuple[str, ...],
    priors: QbDesignedRunPriors,
) -> QbDesignedRunTrainingExample | None:
    if not _is_designed_run_row(row):
        return None
    if row.get("posteam") is None or row.get("defteam") is None:
        return None
    state = _state_from_row(row)
    if state is None:
        return None

    label = _designed_qb_run_label(row)
    rusher_id = row.get("rusher_player_id")
    rusher_key = None if rusher_id in (None, "") else str(rusher_id)
    posteam = str(row["posteam"])
    defteam = str(row["defteam"])
    home_team = str(row["home_team"])
    away_team = str(row["away_team"])
    league_prior = _leave_one_out_counts(priors.league_counts, label)
    league_prior = 0.05 if league_prior is None else league_prior
    qb_prior = _leave_one_out_rate(priors.qb_counts, rusher_key, label, fallback=league_prior)
    team_prior = _leave_one_out_rate(priors.team_counts, posteam, label, fallback=league_prior)
    opponent_prior = _leave_one_out_rate(priors.opponent_allowed_counts, defteam, label, fallback=league_prior)
    total_line = _float_or_none(row.get("total_line"))
    spread_line = _float_or_none(row.get("spread_line"))
    implied_team_total = None
    team_spread_line = spread_line
    if total_line is not None and spread_line is not None:
        if posteam == home_team:
            implied_team_total = total_line / 2.0 + spread_line / 2.0
        else:
            implied_team_total = total_line / 2.0 - spread_line / 2.0
            team_spread_line = -spread_line
    values = qb_designed_run_feature_values(
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
        qb_prior_designed_run_share=qb_prior or league_prior,
        team_prior_designed_qb_run_rate=team_prior or league_prior,
        opponent_prior_designed_qb_run_allowed=opponent_prior or league_prior,
        mobility_tier=priors.mobility_tiers.get(rusher_key or "", "medium"),
    )
    features = np.array([values.get(name, 0.0) for name in feature_names], dtype=float)
    if not np.all(np.isfinite(features)):
        return None
    return QbDesignedRunTrainingExample(features=features, label=label, base_rate=float(team_prior or league_prior))


def fit_logistic_qb_designed_run(
    examples: list[QbDesignedRunTrainingExample],
    feature_names: tuple[str, ...],
    *,
    l2: float = 1.0,
    max_iter: int = 200,
) -> QbDesignedRunFitResult:
    if not examples:
        raise ValueError("Cannot fit QB designed-run model with zero examples")
    fit = fit_logistic_qb_scramble(
        [
            QbScrambleTrainingExample(
                features=example.features,
                label=example.label,
                base_rate=example.base_rate,
            )
            for example in examples
        ],
        feature_names,
        l2=l2,
        max_iter=max_iter,
    )
    return QbDesignedRunFitResult(
        coefficients=fit.coefficients,
        objective=fit.objective,
        converged=fit.converged,
        iterations=fit.iterations,
        num_examples=fit.num_examples,
    )


def build_designed_run_tail_buckets(
    rows: list[Mapping[str, object]],
    *,
    mobility_tiers: Mapping[str, str],
) -> dict[str, tuple[int, ...]]:
    buckets: dict[str, list[int]] = defaultdict(list)
    for row in rows:
        if not _is_designed_run_row(row) or _designed_qb_run_label(row) != 1:
            continue
        state = _state_from_row(row)
        if state is None:
            continue
        rusher_id = row.get("rusher_player_id")
        mobility_tier = mobility_tiers.get(str(rusher_id), "medium")
        yards = _int_or_none(row.get("yards_gained"))
        if yards is None:
            continue
        buckets["global"].append(yards)
        buckets[qb_designed_run_tail_key(state, mobility_tier=mobility_tier)].append(yards)
    return {key: tuple(values) for key, values in buckets.items()}


def _is_designed_run_row(row: Mapping[str, object]) -> bool:
    if row.get("play_type") != "run":
        return False
    if row.get("rusher_player_id") in (None, ""):
        return False
    if row.get("qb_scramble") in {1, 1.0, True, "1", "true", "True"}:
        return False
    if row.get("qb_kneel") in {1, 1.0, True, "1", "true", "True"}:
        return False
    if row.get("qb_spike") in {1, 1.0, True, "1", "true", "True"}:
        return False
    if row.get("no_play") in {1, 1.0, True, "1", "true", "True"}:
        return False
    return True


def _designed_qb_run_label(row: Mapping[str, object]) -> int:
    return 1 if row.get("rusher_position") == "QB" else 0


def _int_or_none(value: object) -> int | None:
    try:
        value_i = int(value)
    except (TypeError, ValueError):
        return None
    return value_i
```

Export the new helpers in `src/fantasy_sim/data/qb_rushing/__init__.py`.

- [ ] **Step 4: Run training tests**

Run:

```bash
uv run pytest tests/test_data/test_qb_rushing/test_training.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

```bash
git add src/fantasy_sim/data/qb_rushing/training.py src/fantasy_sim/data/qb_rushing/__init__.py tests/test_data/test_qb_rushing/test_training.py
git commit -m "feat: add QB designed-run training helpers"
```

### Task 3: Artifact Fitting Script

**Files:**
- Add: `scripts/fit_qb_designed_run_model.py`
- Add: `tests/test_scripts/test_fit_qb_designed_run_model.py`

- [ ] **Step 1: Write failing script tests**

Create `tests/test_scripts/test_fit_qb_designed_run_model.py`:

```python
import json
import sys
from pathlib import Path

import polars as pl
import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from fantasy_sim.data.qb_rushing import QB_DESIGNED_RUN_MODEL_TYPE, QB_DESIGNED_RUN_SCHEMA_VERSION
from fit_qb_designed_run_model import collect_examples_from_pbp, fit_artifact_for_season


class FakeLoader:
    def __init__(self, pbp, rosters):
        self._pbp = pbp
        self._rosters = rosters

    def load_pbp(self, seasons):
        assert seasons == [2023]
        return self._pbp

    def load_rosters(self, seasons):
        assert seasons == [2023]
        return self._rosters


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
                "play_type": "run",
                "rusher_player_id": "QB1" if idx < 4 else "RB1",
                "qb_scramble": 0,
                "qb_kneel": 0,
                "qb_spike": 0,
                "no_play": 0,
                "yards_gained": 8 if idx < 4 else 4,
                "down": 3,
                "ydstogo": 2,
                "yardline_100": 35,
                "qtr": 2,
                "quarter_seconds_remaining": 300,
                "score_differential": -3,
                "spread_line": 2.0,
                "total_line": 47.0,
            }
        )
    return pl.DataFrame(rows)


def _rosters():
    return pl.DataFrame(
        [
            {"season": 2023, "week": 1, "player_id": "QB1", "position": "QB"},
            {"season": 2023, "week": 1, "player_id": "RB1", "position": "RB"},
        ]
    )


def test_collect_examples_from_pbp_excludes_scrambles_and_builds_tail_buckets():
    examples, priors, tail_buckets = collect_examples_from_pbp(_pbp(), _rosters())

    assert len(examples) == 12
    assert sum(example.label for example in examples) == 4
    assert priors.team["BUF"] == pytest.approx(4 / 12)
    assert tail_buckets["global"] == (8, 8, 8, 8)


def test_collect_examples_from_pbp_requires_rusher_player_id():
    pbp = _pbp().drop("rusher_player_id")

    with pytest.raises(ValueError, match="rusher_player_id"):
        collect_examples_from_pbp(pbp, _rosters())


def test_fit_artifact_for_season_writes_json(tmp_path):
    artifact = fit_artifact_for_season(
        FakeLoader(_pbp(), _rosters()),
        target_season=2024,
        min_source_season=2023,
        training_years=1,
        output_dir=tmp_path,
        l2=1.0,
        max_iter=50,
    )

    path = tmp_path / "qb_designed_run_model_2024.json"
    saved = json.loads(path.read_text())
    assert artifact["schema_version"] == QB_DESIGNED_RUN_SCHEMA_VERSION
    assert saved["model_type"] == QB_DESIGNED_RUN_MODEL_TYPE
    assert saved["target_season"] == 2024
    assert saved["source_seasons"] == [2023]
    assert saved["diagnostics"]["num_examples"] == 12
    assert saved["tail_buckets"]["global"] == [8, 8, 8, 8]
```

- [ ] **Step 2: Run script tests and verify failure**

Run:

```bash
uv run pytest tests/test_scripts/test_fit_qb_designed_run_model.py -v
```

Expected: FAIL because the script does not exist.

- [ ] **Step 3: Add fitting script**

Create `scripts/fit_qb_designed_run_model.py`:

```python
"""Fit learned QB designed-run artifacts."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import polars as pl

from fantasy_sim.data.loader import DataLoader
from fantasy_sim.data.qb_rushing import (
    DEFAULT_QB_DESIGNED_RUN_FEATURES,
    QB_DESIGNED_RUN_MODEL_TYPE,
    QB_DESIGNED_RUN_SCHEMA_VERSION,
    annotate_rusher_positions,
    build_designed_run_example_from_row,
    build_designed_run_priors,
    build_designed_run_tail_buckets,
    fit_logistic_qb_designed_run,
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
        "rusher_player_id",
        "qb_scramble",
        "yards_gained",
    }
)


def build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fit learned QB designed-run artifacts.")
    parser.add_argument("--test-seasons", type=int, nargs="+", required=True)
    parser.add_argument("--min-source-season", type=int, default=2018)
    parser.add_argument("--training-years", type=int, default=4)
    parser.add_argument("--l2", type=float, default=1.0)
    parser.add_argument("--max-iter", type=int, default=200)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def _positions_from_rosters(rosters: pl.DataFrame) -> dict[str, str]:
    missing = sorted({"player_id", "position"}.difference(rosters.columns))
    if missing:
        raise ValueError(f"Roster data is missing required columns: {missing}")
    return {
        str(row["player_id"]): str(row["position"])
        for row in rosters.iter_rows(named=True)
        if row.get("player_id") not in (None, "") and row.get("position") not in (None, "")
    }


def collect_examples_from_pbp(pbp: pl.DataFrame, rosters: pl.DataFrame):
    missing = sorted(_REQUIRED_PBP_COLUMNS.difference(pbp.columns))
    if missing:
        raise ValueError(f"PBP data is missing required columns: {missing}")
    rows = annotate_rusher_positions(list(pbp.iter_rows(named=True)), _positions_from_rosters(rosters))
    priors = build_designed_run_priors(rows)
    examples = []
    for row in rows:
        example = build_designed_run_example_from_row(row, DEFAULT_QB_DESIGNED_RUN_FEATURES, priors)
        if example is not None:
            examples.append(example)
    tail_buckets = build_designed_run_tail_buckets(rows, mobility_tiers=priors.mobility_tiers)
    return examples, priors, tail_buckets


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
    rosters = loader.load_rosters(source_seasons)
    examples, priors, tail_buckets = collect_examples_from_pbp(pbp, rosters)
    fit = fit_logistic_qb_designed_run(
        examples,
        DEFAULT_QB_DESIGNED_RUN_FEATURES,
        l2=l2,
        max_iter=max_iter,
    )
    designed_qb_rate = sum(example.label for example in examples) / len(examples)
    artifact = {
        "schema_version": QB_DESIGNED_RUN_SCHEMA_VERSION,
        "model_type": QB_DESIGNED_RUN_MODEL_TYPE,
        "target_season": target_season,
        "source_seasons": source_seasons,
        "feature_names": list(DEFAULT_QB_DESIGNED_RUN_FEATURES),
        "coefficients": fit.coefficients,
        "factor_clamp": [0.50, 2.00],
        "priors": {
            "qb": priors.qb,
            "team": priors.team,
            "opponent_allowed": priors.opponent_allowed,
            "league": priors.league,
            "mobility_tiers": priors.mobility_tiers,
        },
        "tail_buckets": {key: list(values) for key, values in tail_buckets.items()},
        "diagnostics": {
            "num_examples": fit.num_examples,
            "designed_qb_run_rate": designed_qb_rate,
            "objective": fit.objective,
            "converged": fit.converged,
            "iterations": fit.iterations,
            "l2": l2,
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"qb_designed_run_model_{target_season}.json"
    path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return artifact


def main(argv: list[str] | None = None) -> int:
    args = build_cli().parse_args(argv)
    loader = DataLoader()
    started = time.time()
    for season in args.test_seasons:
        print(f"Fitting QB designed-run artifact for {season}...", flush=True)
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
            f"  wrote qb_designed_run_model_{season}.json "
            f"examples={diag['num_examples']} "
            f"designed_qb_run_rate={diag['designed_qb_run_rate']:.3f} "
            f"converged={diag['converged']}",
            flush=True,
        )
    print(f"Completed in {time.time() - started:.1f}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run script tests**

Run:

```bash
uv run pytest tests/test_scripts/test_fit_qb_designed_run_model.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

```bash
git add scripts/fit_qb_designed_run_model.py tests/test_scripts/test_fit_qb_designed_run_model.py
git commit -m "feat: add QB designed-run artifact fitting script"
```

### Task 4: Runtime Artifact Loader

**Files:**
- Modify: `tests/test_data/test_qb_rushing/test_runtime.py`
- Modify: `src/fantasy_sim/data/qb_rushing/runtime.py`
- Modify: `src/fantasy_sim/data/qb_rushing/__init__.py`

- [ ] **Step 1: Write failing runtime tests**

Add these imports to `tests/test_data/test_qb_rushing/test_runtime.py`:

```python
from fantasy_sim.data.qb_rushing import (
    QB_DESIGNED_RUN_MODEL_TYPE,
    QB_DESIGNED_RUN_SCHEMA_VERSION,
    QbDesignedRunModel,
    QbDesignedRunModelConfig,
)
```

Add helpers and tests:

```python
def _designed_config(tmp_path, **overrides):
    values = {"enabled": True, "artifacts_dir": str(tmp_path)}
    values.update(overrides)
    return QbDesignedRunModelConfig(**values)


def _designed_artifact(**overrides):
    values = {
        "schema_version": QB_DESIGNED_RUN_SCHEMA_VERSION,
        "model_type": QB_DESIGNED_RUN_MODEL_TYPE,
        "target_season": 2024,
        "source_seasons": [2023],
        "feature_names": ["intercept"],
        "coefficients": {"intercept": 0.0},
        "factor_clamp": [0.50, 2.00],
        "priors": {
            "qb": {"QB1": 0.12},
            "team": {"BUF": 0.08},
            "opponent_allowed": {"KC": 0.07},
            "league": 0.06,
            "mobility_tiers": {"QB1": "high"},
        },
        "tail_buckets": {"global": [6, 9, 12]},
        "diagnostics": {"num_examples": 500, "designed_qb_run_rate": 0.06},
    }
    values.update(overrides)
    return values


def _write_designed_artifact(tmp_path, **overrides):
    path = tmp_path / "qb_designed_run_model_2024.json"
    path.write_text(json.dumps(_designed_artifact(**overrides)), encoding="utf-8")
    return path


def _build_designed_context(model):
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


def test_missing_designed_run_artifact_returns_none(tmp_path):
    model = QbDesignedRunModel(_designed_config(tmp_path))

    assert _build_designed_context(model) is None


def test_valid_designed_run_artifact_builds_context(tmp_path):
    _write_designed_artifact(tmp_path)
    model = QbDesignedRunModel(_designed_config(tmp_path))

    context = _build_designed_context(model)

    assert context is not None
    assert context.team == "BUF"
    assert context.mobility_tiers["QB1"] == "high"
    assert context.global_tail_yards == (6, 9, 12)


def test_invalid_designed_run_schema_returns_none(tmp_path):
    _write_designed_artifact(tmp_path, schema_version=999)
    model = QbDesignedRunModel(_designed_config(tmp_path))

    assert _build_designed_context(model) is None


def test_designed_run_artifact_below_min_examples_returns_none(tmp_path):
    _write_designed_artifact(tmp_path, diagnostics={"num_examples": 499, "designed_qb_run_rate": 0.06})
    model = QbDesignedRunModel(_designed_config(tmp_path, min_examples=500))

    assert _build_designed_context(model) is None


def test_designed_run_artifact_requires_tail_buckets(tmp_path):
    _write_designed_artifact(tmp_path, tail_buckets={})
    model = QbDesignedRunModel(_designed_config(tmp_path))

    assert _build_designed_context(model) is None


def test_invalid_designed_run_clamp_falls_back_to_config(tmp_path):
    _write_designed_artifact(tmp_path, factor_clamp=[2.0, 1.0])
    model = QbDesignedRunModel(_designed_config(tmp_path, factor_clamp=(0.75, 1.25)))

    context = _build_designed_context(model)

    assert context is not None
    assert context.factor_clamp == (0.75, 1.25)
```

- [ ] **Step 2: Run runtime tests and verify failure**

Run:

```bash
uv run pytest tests/test_data/test_qb_rushing/test_runtime.py -v
```

Expected: FAIL because `QbDesignedRunModel` does not exist.

- [ ] **Step 3: Add runtime loader**

In `src/fantasy_sim/data/qb_rushing/runtime.py`, import designed-run constants and config/context classes:

```python
from fantasy_sim.data.qb_rushing.models import (
    DEFAULT_QB_DESIGNED_RUN_ARTIFACT_DIR,
    DEFAULT_QB_DESIGNED_RUN_FEATURES,
    QB_DESIGNED_RUN_MODEL_TYPE,
    QB_DESIGNED_RUN_SCHEMA_VERSION,
    QbDesignedRunContext,
    QbDesignedRunModelConfig,
)
```

Add this class below `QbScrambleModel`:

```python
class QbDesignedRunModel:
    """Loads learned QB designed-run artifacts and builds team runtime contexts."""

    def __init__(self, config: QbDesignedRunModelConfig) -> None:
        self.config = config
        self.artifacts_dir = Path(config.artifacts_dir or DEFAULT_QB_DESIGNED_RUN_ARTIFACT_DIR)
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
    ) -> QbDesignedRunContext | None:
        del roster
        if not self.config.enabled:
            return None
        artifact = self._load_artifact(target_season)
        if artifact is None:
            return None
        if artifact.get("target_season") != target_season:
            logger.warning("Invalid QB designed-run artifact for %s: target season mismatch", target_season)
            return None
        if not _source_seasons_are_safe(artifact.get("source_seasons"), target_season):
            logger.warning("Invalid QB designed-run artifact for %s: unsafe source seasons", target_season)
            return None
        if not _artifact_meets_min_examples(artifact, target_season, self.config.min_examples):
            return None
        parsed = _parse_designed_run_features_and_coefficients(artifact, target_season)
        if parsed is None:
            return None
        feature_names, coefficients = parsed
        tail_buckets = _parse_tail_buckets(artifact.get("tail_buckets"), target_season)
        if tail_buckets is None:
            return None
        priors = artifact.get("priors")
        league_prior = _prior_value(priors, "league", None, 0.05)
        mobility_tiers = _mobility_tiers(priors)
        return QbDesignedRunContext(
            coefficients=coefficients,
            feature_names=feature_names,
            tail_buckets=tail_buckets,
            global_tail_yards=tail_buckets.get("global", ()),
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
            team_prior_designed_qb_run_rate=_prior_value(priors, "team", team, league_prior),
            opponent_prior_designed_qb_run_allowed=_prior_value(priors, "opponent_allowed", opponent, league_prior),
            mobility_tiers=mobility_tiers,
            factor_clamp=_artifact_clamp(
                artifact.get("factor_clamp"),
                fallback=self.config.factor_clamp,
                min_value=0.0,
                max_value=math.inf,
            ),
            min_tail_samples=self.config.min_tail_samples,
        )

    def _load_artifact(self, target_season: int) -> dict[str, Any] | None:
        if target_season in self._artifact_cache:
            return self._artifact_cache[target_season]
        path = self.artifacts_dir / f"qb_designed_run_model_{target_season}.json"
        artifact: dict[str, Any] | None = None
        try:
            with path.open("r", encoding="utf-8") as handle:
                loaded = json.load(handle)
        except FileNotFoundError:
            logger.info("Missing QB designed-run artifact: %s", path)
        except OSError:
            logger.warning("Unable to read QB designed-run artifact: %s", path)
        except UnicodeDecodeError:
            logger.warning("Invalid QB designed-run artifact encoding: %s", path)
        except json.JSONDecodeError:
            logger.warning("Invalid QB designed-run artifact JSON: %s", path)
        else:
            if not isinstance(loaded, dict):
                logger.warning("Invalid QB designed-run artifact payload: %s", path)
            elif loaded.get("schema_version") != QB_DESIGNED_RUN_SCHEMA_VERSION:
                logger.warning("Unsupported QB designed-run artifact schema: %s", path)
            elif loaded.get("model_type") != QB_DESIGNED_RUN_MODEL_TYPE:
                logger.warning("Unsupported QB designed-run artifact model type: %s", path)
            else:
                artifact = loaded
        self._artifact_cache[target_season] = artifact
        return artifact
```

Add helper functions below `_parse_features_and_coefficients()`:

```python
def _parse_designed_run_features_and_coefficients(
    artifact: dict[str, Any],
    target_season: int,
) -> tuple[tuple[str, ...], dict[str, float]] | None:
    feature_names = artifact.get("feature_names")
    coefficients_raw = artifact.get("coefficients")
    if not isinstance(feature_names, list) or not isinstance(coefficients_raw, dict):
        logger.warning("Invalid QB designed-run artifact for %s: missing feature_names/coefficients", target_season)
        return None
    if not feature_names or not all(isinstance(name, str) for name in feature_names):
        return None
    if any(name not in DEFAULT_QB_DESIGNED_RUN_FEATURES for name in feature_names):
        return None
    parsed_features = tuple(feature_names)
    if len(set(parsed_features)) != len(parsed_features):
        return None
    try:
        coefficients = {str(name): float(value) for name, value in coefficients_raw.items()}
    except (TypeError, ValueError):
        return None
    if set(coefficients) != set(parsed_features):
        return None
    if not all(math.isfinite(value) for value in coefficients.values()):
        return None
    return parsed_features, coefficients


def _parse_tail_buckets(raw: object, target_season: int) -> dict[str, tuple[int, ...]] | None:
    if not isinstance(raw, dict):
        logger.warning("Invalid QB designed-run artifact for %s: missing tail_buckets", target_season)
        return None
    parsed: dict[str, tuple[int, ...]] = {}
    for key, values in raw.items():
        if not isinstance(key, str) or not isinstance(values, list):
            return None
        try:
            parsed[key] = tuple(int(value) for value in values)
        except (TypeError, ValueError):
            return None
    if not parsed.get("global"):
        return None
    return parsed


def _mobility_tiers(priors: object) -> dict[str, str]:
    if not isinstance(priors, dict):
        return {}
    raw = priors.get("mobility_tiers")
    if not isinstance(raw, dict):
        return {}
    return {
        str(player_id): str(tier)
        for player_id, tier in raw.items()
        if str(tier) in {"low", "medium", "high"}
    }
```

Export `QbDesignedRunModel` in `src/fantasy_sim/data/qb_rushing/__init__.py`.

- [ ] **Step 4: Run runtime tests**

Run:

```bash
uv run pytest tests/test_data/test_qb_rushing/test_runtime.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 4**

```bash
git add src/fantasy_sim/data/qb_rushing/runtime.py src/fantasy_sim/data/qb_rushing/__init__.py tests/test_data/test_qb_rushing/test_runtime.py
git commit -m "feat: load QB designed-run artifacts"
```

### Task 5: Engine Runtime Threading

**Files:**
- Modify: `src/fantasy_sim/engine/types.py`
- Modify: `src/fantasy_sim/engine/player_selector.py`
- Modify: `src/fantasy_sim/engine/play_resolver.py`
- Modify: `src/fantasy_sim/engine/game_sim.py`
- Modify: `tests/test_engine/test_types.py`
- Modify: `tests/test_engine/test_player_selector.py`
- Modify: `tests/test_engine/test_play_resolver.py`
- Modify: `tests/test_engine/test_game_sim.py`

- [ ] **Step 1: Write failing engine tests**

Add a `TeamDistributions` default assertion to `tests/test_engine/test_types.py`:

```python
def test_team_distributions_defaults_qb_designed_run_context_to_none(self):
    td = TeamDistributions(
        play_calling=PlayCallingDist(team="KC", distributions={}),
        play_outcomes=PlayOutcomeDist(
            distributions={},
            defaults={"pass": np.array([5]), "run": np.array([3])},
        ),
        turnover_rates=TurnoverRates(
            team="KC",
            int_rate=0.025,
            fumble_rate=0.01,
            sack_rate=0.06,
            sack_fumble_rate=0.10,
        ),
        kicking=KickingModel(
            fg_make_rate={"0_39": 0.95, "40_49": 0.82, "50_plus": 0.65},
            xp_rate=0.94,
        ),
        drive_start=DriveStartModel(
            touchback_rate=0.55,
            touchback_yardline=75,
            return_yardlines=np.array([72, 78]),
        ),
    )

    assert td.qb_designed_run_context is None
```

Add this test to `tests/test_engine/test_player_selector.py`:

```python
class FixedQbDesignedRunContext:
    def rusher_weights(self, players, legacy_weights, state, script=None):
        adjusted = legacy_weights.copy()
        for idx, player in enumerate(players):
            if player.position == "QB":
                adjusted[idx] = 100.0
        return adjusted

    def designed_run_yards(self, state, rusher, rng, script=None):
        return None


def test_qb_designed_run_context_can_tilt_rusher_pool_to_eligible_qb():
    qb = PlayerModel(
        "QB1",
        "QB",
        "QB",
        "T",
        PlayerUsage(snap_share=1.0, carry_share=0.12),
        PlayerOutcomes(rushing_yards_dist=np.array([5])),
    )
    rb = PlayerModel(
        "RB1",
        "RB",
        "RB",
        "T",
        PlayerUsage(carry_share=0.80),
        PlayerOutcomes(rushing_yards_dist=np.array([4])),
    )
    roster = TeamRoster(team="T", players=[qb, rb])

    selected = select_rusher(
        roster,
        make_state(),
        np.random.default_rng(1),
        qb_designed_run_context=FixedQbDesignedRunContext(),
    )

    assert selected.player_id == "QB1"
```

Add these tests to `tests/test_engine/test_play_resolver.py`:

```python
class FixedQbDesignedRunYardsContext:
    def rusher_weights(self, players, legacy_weights, state, script=None):
        adjusted = legacy_weights.copy()
        for idx, player in enumerate(players):
            if player.position == "QB":
                adjusted[idx] = 100.0
        return adjusted

    def designed_run_yards(self, state, rusher, rng, script=None):
        if rusher.position == "QB":
            return 15
        return None


def test_qb_designed_run_context_supplies_yards_for_selected_qb_run():
    qb = PlayerModel(
        "QB1",
        "QB",
        "QB",
        "T",
        PlayerUsage(snap_share=1.0, carry_share=0.12),
        PlayerOutcomes(rushing_yards_dist=np.array([2])),
    )
    rb = PlayerModel(
        "RB1",
        "RB",
        "RB",
        "T",
        PlayerUsage(carry_share=0.80),
        PlayerOutcomes(rushing_yards_dist=np.array([4])),
    )
    result = resolve_play(
        make_state(yard_line=50),
        "run",
        make_outcomes(run_yards=[1]),
        make_turnover_rates(),
        np.random.default_rng(1),
        roster=TeamRoster(team="T", players=[qb, rb]),
        qb_designed_run_context=FixedQbDesignedRunYardsContext(),
    )

    assert result.rusher_id == "QB1"
    assert result.yards == 15


def test_qb_designed_run_context_does_not_affect_scramble_yards():
    qb = PlayerModel(
        "QB1",
        "QB",
        "QB",
        "T",
        PlayerUsage(snap_share=1.0, scramble_rate=1.0, carry_share=0.12),
        PlayerOutcomes(scramble_yards_dist=np.array([6]), rushing_yards_dist=np.array([2])),
    )
    wr = PlayerModel("WR1", "WR", "WR", "T", PlayerUsage(target_share=1.0), PlayerOutcomes(catch_rate=1.0))
    result = resolve_play(
        make_state(yard_line=50),
        "pass",
        make_outcomes(run_yards=[1]),
        make_turnover_rates(),
        np.random.default_rng(1),
        roster=TeamRoster(team="T", players=[qb, wr]),
        qb_designed_run_context=FixedQbDesignedRunYardsContext(),
    )

    assert result.rusher_id == "QB1"
    assert result.yards == 6
```

Update the fake `resolve_play` in `tests/test_engine/test_game_sim.py` to accept `qb_designed_run_context=None`, capture it, set `home_dists.qb_designed_run_context = object()`, and assert it was threaded.

- [ ] **Step 2: Run engine tests and verify failure**

Run:

```bash
uv run pytest tests/test_engine/test_types.py tests/test_engine/test_player_selector.py tests/test_engine/test_play_resolver.py tests/test_engine/test_game_sim.py -v
```

Expected: FAIL because the protocol, field, and function parameters do not exist.

- [ ] **Step 3: Add engine protocol and distribution field**

In `src/fantasy_sim/engine/types.py`, add this protocol after `QbScrambleContextProtocol`:

```python
class QbDesignedRunContextProtocol(Protocol):
    """QB designed-run selector and yard-tail interface used by the engine."""

    def rusher_weights(
        self,
        players: list["PlayerModel"],
        legacy_weights: "np.ndarray",
        state: "GameState",
        script: "RuntimeGameScript | None" = None,
    ) -> "np.ndarray | None":
        raise NotImplementedError

    def designed_run_yards(
        self,
        state: "GameState",
        rusher: "PlayerModel",
        rng: "np.random.Generator",
        script: "RuntimeGameScript | None" = None,
    ) -> int | None:
        raise NotImplementedError
```

Add the field to `TeamDistributions`:

```python
    qb_designed_run_context: QbDesignedRunContextProtocol | None = None
```

- [ ] **Step 4: Thread selector context through `select_rusher()`**

In `src/fantasy_sim/engine/player_selector.py`, import the protocol:

```python
from fantasy_sim.engine.types import GameState, QbDesignedRunContextProtocol, TargetSelectionContextProtocol
```

Update `select_rusher()` signature:

```python
def select_rusher(
    roster: TeamRoster,
    state: GameState,
    rng: np.random.Generator,
    is_scramble: bool = False,
    goal_line_concentration_enabled: bool = False,
    script: RuntimeGameScript | None = None,
    qb_designed_run_context: QbDesignedRunContextProtocol | None = None,
) -> PlayerModel:
```

After `_apply_rb_rank_factors()`, add:

```python
    if qb_designed_run_context is not None:
        adjusted = qb_designed_run_context.rusher_weights(eligible, weights, state, script=script)
        if adjusted is not None:
            weights = adjusted
```

- [ ] **Step 5: Thread yard context through play resolution**

In `src/fantasy_sim/engine/play_resolver.py`, import the protocol:

```python
from fantasy_sim.engine.types import (
    GameState,
    PlayResult,
    QbDesignedRunContextProtocol,
    QbScrambleContextProtocol,
    TargetSelectionContextProtocol,
)
```

Add `qb_designed_run_context` to `resolve_play()` and `_resolve_run()` signatures. Pass it only to `_resolve_run()`, not `_resolve_pass()`.

In `_resolve_run()`, call `select_rusher()` with the context:

```python
        rusher = select_rusher(
            roster,
            state,
            rng,
            goal_line_concentration_enabled=goal_line_concentration_enabled,
            script=script,
            qb_designed_run_context=qb_designed_run_context,
        )
```

Replace the first yard-sampling block inside `_resolve_run()` with:

```python
        context_yards = None
        if qb_designed_run_context is not None:
            context_yards = qb_designed_run_context.designed_run_yards(state, rusher, rng, script=script)

        if context_yards is not None:
            player_yards = int(context_yards)
        elif rusher.outcomes.rushing_yards_dist is not None and len(rusher.outcomes.rushing_yards_dist) > 0:
            player_yards = int(rng.choice(rusher.outcomes.rushing_yards_dist))
        else:
            player_yards = play_outcomes.sample_yards("run", _bucket_from_state(state), rng)
```

- [ ] **Step 6: Thread through game simulation**

In `src/fantasy_sim/engine/game_sim.py`, add the argument to `resolve_play()`:

```python
            qb_designed_run_context=off_dists.qb_designed_run_context,
```

- [ ] **Step 7: Run engine tests**

Run:

```bash
uv run pytest tests/test_engine/test_types.py tests/test_engine/test_player_selector.py tests/test_engine/test_play_resolver.py tests/test_engine/test_game_sim.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit Task 5**

```bash
git add src/fantasy_sim/engine/types.py src/fantasy_sim/engine/player_selector.py src/fantasy_sim/engine/play_resolver.py src/fantasy_sim/engine/game_sim.py tests/test_engine/test_types.py tests/test_engine/test_player_selector.py tests/test_engine/test_play_resolver.py tests/test_engine/test_game_sim.py
git commit -m "feat: thread QB designed-run context through engine"
```

### Task 6: Game Context Wiring

**Files:**
- Modify: `tests/test_data/test_game_context.py`
- Modify: `src/fantasy_sim/data/game_context.py`

- [ ] **Step 1: Write failing game-context tests**

Add imports to `tests/test_data/test_game_context.py`:

```python
from fantasy_sim.data.qb_rushing import (
    QB_DESIGNED_RUN_MODEL_TYPE,
    QB_DESIGNED_RUN_SCHEMA_VERSION,
    QbDesignedRunModelConfig,
)
```

Add tests near the existing QB scramble tests:

```python
    def test_qb_designed_run_model_created_when_enabled(self, tmp_path):
        builder = GameContextBuilder(
            cache_dir=tmp_path / "cache",
            qb_rushing_config=QbRushingConfig(
                designed_runs=QbDesignedRunModelConfig(
                    enabled=True,
                    artifacts_dir=str(tmp_path),
                ),
            ),
        )

        assert builder._qb_designed_run_model is not None

    def test_qb_designed_run_context_attached_when_artifact_exists(
        self, tmp_path, expanded_pbp, sample_rosters
    ):
        artifact = {
            "schema_version": QB_DESIGNED_RUN_SCHEMA_VERSION,
            "model_type": QB_DESIGNED_RUN_MODEL_TYPE,
            "target_season": 2024,
            "source_seasons": [2023],
            "feature_names": ["intercept"],
            "coefficients": {"intercept": 0.0},
            "priors": {
                "qb": {},
                "team": {},
                "opponent_allowed": {},
                "league": 0.06,
                "mobility_tiers": {},
            },
            "tail_buckets": {"global": [5, 8, 12]},
            "diagnostics": {"num_examples": 500, "designed_qb_run_rate": 0.06},
        }
        (tmp_path / "qb_designed_run_model_2024.json").write_text(
            json.dumps(artifact),
            encoding="utf-8",
        )
        builder = GameContextBuilder(
            cache_dir=tmp_path / "cache",
            qb_rushing_config=QbRushingConfig(
                designed_runs=QbDesignedRunModelConfig(
                    enabled=True,
                    artifacts_dir=str(tmp_path),
                ),
            ),
        )
        builder.loader.load_schedules = lambda seasons: pl.DataFrame(
            [
                {
                    "season": 2024,
                    "week": 1,
                    "home_team": "KC",
                    "away_team": "BUF",
                    "spread_line": -3.0,
                    "total_line": 48.0,
                }
            ]
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

        assert home_dists.qb_designed_run_context is not None
        assert away_dists.qb_designed_run_context is not None
        assert home_dists.qb_designed_run_context.team == "KC"
        assert home_dists.qb_designed_run_context.opponent == "BUF"
        assert home_dists.qb_designed_run_context.spread_line == -3.0
        assert home_dists.qb_designed_run_context.implied_team_total == 22.5
        assert away_dists.qb_designed_run_context.team == "BUF"
        assert away_dists.qb_designed_run_context.opponent == "KC"
        assert away_dists.qb_designed_run_context.spread_line == 3.0
        assert away_dists.qb_designed_run_context.implied_team_total == 25.5
```

- [ ] **Step 2: Run game-context tests and verify failure**

Run:

```bash
uv run pytest tests/test_data/test_game_context.py -v
```

Expected: FAIL because `GameContextBuilder` does not instantiate or attach the designed-run model.

- [ ] **Step 3: Wire model into `GameContextBuilder`**

In `src/fantasy_sim/data/game_context.py`, import `QbDesignedRunModel`:

```python
from fantasy_sim.data.qb_rushing import QbDesignedRunModel, QbRushingConfig, QbScrambleModel
```

In `__init__()`, after the scramble model setup, add:

```python
        self._qb_designed_run_model = None
        if self._qb_rushing_config.designed_runs.enabled:
            self._qb_designed_run_model = QbDesignedRunModel(self._qb_rushing_config.designed_runs)
            logger.info("QB designed-run model enabled")
```

In `build_game()`, after the scramble context block and before Vegas adjustments, add:

```python
        if self._qb_designed_run_model is not None and target_season is not None:
            home_market, away_market = self._play_call_market_features(
                home_team,
                away_team,
                target_season,
                week,
            )
            context_week = week or 0
            home_dists.qb_designed_run_context = self._qb_designed_run_model.build_context(
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
            away_dists.qb_designed_run_context = self._qb_designed_run_model.build_context(
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

- [ ] **Step 4: Run game-context tests**

Run:

```bash
uv run pytest tests/test_data/test_game_context.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 6**

```bash
git add src/fantasy_sim/data/game_context.py tests/test_data/test_game_context.py
git commit -m "feat: attach QB designed-run context to games"
```

### Task 7: Validation Coverage Reporting

**Files:**
- Modify: `tests/test_validation/test_coverage.py`
- Modify: `src/fantasy_sim/validation/coverage.py`

- [ ] **Step 1: Write failing coverage tests**

Add a helper near `_write_qb_scramble_artifact()` in `tests/test_validation/test_coverage.py`:

```python
def _write_qb_designed_run_artifact(path: Path, **overrides) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    artifact = {
        "schema_version": QB_DESIGNED_RUN_SCHEMA_VERSION,
        "model_type": QB_DESIGNED_RUN_MODEL_TYPE,
        "target_season": 2024,
        "source_seasons": [2023],
        "feature_names": ["intercept"],
        "coefficients": {"intercept": 0.0},
        "factor_clamp": [0.50, 2.00],
        "priors": {"league": 0.06, "mobility_tiers": {}},
        "tail_buckets": {"global": [5, 8, 12]},
        "diagnostics": {"num_examples": 500, "designed_qb_run_rate": 0.06},
    }
    artifact.update(overrides)
    path.write_text(json.dumps(artifact), encoding="utf-8")
```

Add imports:

```python
from fantasy_sim.data.qb_rushing import QB_DESIGNED_RUN_MODEL_TYPE, QB_DESIGNED_RUN_SCHEMA_VERSION
```

Add tests:

```python
def test_qb_designed_run_coverage_disabled_by_default(tmp_path):
    coverage = collect_signal_coverage(
        config={"qb_rushing": {"designed_runs": {"enabled": False}}},
        test_seasons=[2024],
        cache_dir=tmp_path,
    )

    assert coverage["qb_rushing.designed_runs"].enabled is False
    assert coverage["qb_rushing.designed_runs"].status == "disabled"


def test_qb_designed_run_coverage_requires_valid_artifact(tmp_path):
    artifact_dir = tmp_path / "artifacts"
    _write_qb_designed_run_artifact(artifact_dir / "qb_designed_run_model_2024.json")

    coverage = collect_signal_coverage(
        config={
            "qb_rushing": {
                "designed_runs": {
                    "enabled": True,
                    "artifacts_dir": str(artifact_dir),
                }
            }
        },
        test_seasons=[2024],
        cache_dir=tmp_path,
    )

    assert coverage["qb_rushing.designed_runs"].enabled is True
    assert coverage["qb_rushing.designed_runs"].covered_seasons == [2024]
    assert coverage["qb_rushing.designed_runs"].missing_seasons == []


def test_qb_designed_run_coverage_rejects_missing_tail_buckets(tmp_path):
    artifact_dir = tmp_path / "artifacts"
    _write_qb_designed_run_artifact(
        artifact_dir / "qb_designed_run_model_2024.json",
        tail_buckets={},
    )

    coverage = collect_signal_coverage(
        config={
            "qb_rushing": {
                "designed_runs": {
                    "enabled": True,
                    "artifacts_dir": str(artifact_dir),
                }
            }
        },
        test_seasons=[2024],
        cache_dir=tmp_path,
    )

    assert coverage["qb_rushing.designed_runs"].covered_seasons == []
    assert coverage["qb_rushing.designed_runs"].missing_seasons == [2024]
```

- [ ] **Step 2: Run coverage tests and verify failure**

Run:

```bash
uv run pytest tests/test_validation/test_coverage.py -v
```

Expected: FAIL because `qb_rushing.designed_runs` coverage is not reported.

- [ ] **Step 3: Add coverage support**

In `src/fantasy_sim/validation/coverage.py`, import designed-run constants and features from `fantasy_sim.data.qb_rushing`.

Add a validator near `_qb_scramble_artifact_is_valid()`:

```python
def _qb_designed_run_artifact_is_valid(
    path: Path,
    expected_season: int,
    min_examples: int,
) -> bool:
    if not path.exists():
        return False
    try:
        artifact = json.loads(path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    if not isinstance(artifact, Mapping):
        return False
    if artifact.get("schema_version") != QB_DESIGNED_RUN_SCHEMA_VERSION:
        return False
    if artifact.get("model_type") != QB_DESIGNED_RUN_MODEL_TYPE:
        return False
    if artifact.get("target_season") != expected_season:
        return False
    if not _play_call_source_seasons_are_safe(artifact.get("source_seasons"), expected_season):
        return False
    diagnostics = artifact.get("diagnostics")
    if not isinstance(diagnostics, Mapping):
        return False
    num_examples = diagnostics.get("num_examples")
    if not isinstance(num_examples, int) or isinstance(num_examples, bool) or num_examples < min_examples:
        return False
    feature_names = artifact.get("feature_names")
    coefficients = artifact.get("coefficients")
    if not isinstance(feature_names, list) or not feature_names:
        return False
    if len(set(feature_names)) != len(feature_names):
        return False
    if any(name not in DEFAULT_QB_DESIGNED_RUN_FEATURES for name in feature_names):
        return False
    if not isinstance(coefficients, Mapping) or set(coefficients) != set(feature_names):
        return False
    try:
        parsed = [float(value) for value in coefficients.values()]
    except (TypeError, ValueError):
        return False
    if not all(math.isfinite(value) for value in parsed):
        return False
    tail_buckets = artifact.get("tail_buckets")
    if not isinstance(tail_buckets, Mapping):
        return False
    global_tail = tail_buckets.get("global")
    return isinstance(global_tail, list) and len(global_tail) > 0


def _covered_seasons_from_qb_designed_run_artifacts(
    test_seasons: Iterable[int],
    paths_by_season: Mapping[int, Path],
    min_examples: int,
) -> list[int]:
    return [
        season
        for season in test_seasons
        if (path := paths_by_season.get(season)) is not None
        and _qb_designed_run_artifact_is_valid(path, season, min_examples)
    ]
```

In `collect_signal_coverage()`, add enabled/min/path handling analogous to scramble:

```python
    qb_designed_run_enabled = _signal_enabled(
        config,
        ("qb_rushing_config", "qb_rushing"),
        ("qb_rushing", "designed_runs"),
        nested_path=("designed_runs",),
    )
    qb_designed_run_min_examples = int(
        _config_value(
            config,
            ("qb_rushing_config", "qb_rushing"),
            ("qb_rushing", "designed_runs", "min_examples"),
            nested_path=("designed_runs", "min_examples"),
            default=500,
        )
    )
```

Add artifact paths:

```python
    qb_designed_run_artifact_paths: dict[int, Path] = {
        season: qb_designed_run_artifacts_path / f"qb_designed_run_model_{season}.json"
        for season in seasons
    }
```

Add a signal entry:

```python
        "qb_rushing.designed_runs": _build_signal(
            qb_designed_run_enabled,
            seasons,
            _covered_seasons_from_qb_designed_run_artifacts(
                seasons,
                qb_designed_run_artifact_paths,
                qb_designed_run_min_examples,
            ),
            note=(
                "Requires qb_designed_run_model_<season>.json artifacts fitted from "
                "prior-season PBP designed-run labels; runtime falls back to legacy "
                "rusher selection and QB rushing_yards_dist when an artifact is missing or invalid"
            ),
        ),
```

Resolve `qb_designed_run_artifacts_path` using the same raw-config fallback pattern as `_resolve_qb_scramble_artifacts_path()`. Name the helper `_resolve_qb_designed_run_artifacts_path()` and default it to `results/qb_rushing/designed_runs/smoke_v1` only when no config path exists.

- [ ] **Step 4: Run coverage tests**

Run:

```bash
uv run pytest tests/test_validation/test_coverage.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 7**

```bash
git add src/fantasy_sim/validation/coverage.py tests/test_validation/test_coverage.py
git commit -m "feat: report QB designed-run artifact coverage"
```

### Task 8: Verification And Smoke Commands

**Files:**
- Modify: `docs/hypotheses-list.md`

- [ ] **Step 1: Run focused test suite**

Run:

```bash
uv run pytest \
  tests/test_data/test_qb_rushing/ \
  tests/test_scripts/test_fit_qb_designed_run_model.py \
  tests/test_engine/test_types.py \
  tests/test_engine/test_player_selector.py \
  tests/test_engine/test_play_resolver.py \
  tests/test_engine/test_game_sim.py \
  tests/test_data/test_game_context.py \
  tests/test_validation/test_coverage.py \
  -v
```

Expected: PASS.

- [ ] **Step 2: Run full unit tests**

Run:

```bash
uv run pytest tests/ -v
```

Expected: PASS.

- [ ] **Step 3: Fit smoke artifacts**

Run:

```bash
uv run python scripts/fit_qb_designed_run_model.py \
  --test-seasons 2022 2023 2024 \
  --min-source-season 2018 \
  --training-years 4 \
  --output-dir results/qb_rushing/designed_runs/smoke_v1
```

Expected: writes `qb_designed_run_model_2022.json`, `qb_designed_run_model_2023.json`, and `qb_designed_run_model_2024.json` with nonzero `diagnostics.num_examples`, source seasons all less than target season, and nonempty `tail_buckets.global`.

- [ ] **Step 4: Run 50-sim validation**

Run:

```bash
uv run python scripts/validate.py \
  --baseline defaults \
  --sims 50 \
  --set qb_rushing.designed_runs.enabled=true \
  --set qb_rushing.designed_runs.artifacts_dir=results/qb_rushing/designed_runs/smoke_v1 \
  --label qb-designed-run-chain-s50
```

Expected: validation completes and coverage output reports `qb_rushing.designed_runs=full(2022,2023,2024)` or an explicit partial/missing status if an artifact was rejected.

- [ ] **Step 5: Update hypothesis document with implementation status**

In `docs/hypotheses-list.md`, under the QB rushing model entry, add a short implementation note with the artifact path and 50-sim smoke label. If smoke failed, state that defaults remain unchanged. If smoke passed and a 200-sim run is warranted, state that the decision run is pending.

- [ ] **Step 6: Commit Task 8**

```bash
git add docs/hypotheses-list.md results/qb_rushing/designed_runs/smoke_v1 scripts/fit_qb_designed_run_model.py src/fantasy_sim tests
git commit -m "test: validate QB designed-run chain smoke run"
```

If artifact files are too large for the repository policy, do not add `results/qb_rushing/designed_runs/smoke_v1`; instead commit only code, tests, and docs, and include this trailer in the commit body:

```text
Not-tested-artifacts: smoke artifacts generated locally under results/qb_rushing/designed_runs/smoke_v1 and intentionally not committed
```

## Self-Review

Spec coverage:

- Default-off config: Task 1.
- Runtime boundary: Tasks 5 and 6.
- Temporal artifacts: Tasks 2 and 3.
- Selector component: Tasks 1, 2, 4, and 5.
- Tail component: Tasks 1, 2, 4, and 5.
- Safe fallbacks: Tasks 4, 5, and 7.
- Validation coverage: Task 7.
- Smoke validation commands: Task 8.

Placeholder scan:

- No placeholder sections remain.
- Every command has an expected result.
- Each code-changing task contains concrete code blocks and exact file paths.

Type consistency:

- Config type: `QbDesignedRunModelConfig`.
- Runtime type: `QbDesignedRunContext` and `QbDesignedRunModel`.
- Engine protocol: `QbDesignedRunContextProtocol`.
- Team distribution field: `qb_designed_run_context`.
- Artifact file name: `qb_designed_run_model_<season>.json`.

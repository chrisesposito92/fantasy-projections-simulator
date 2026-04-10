# Game Script / Garbage Time Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a two-phase late-game behavior layer that adds trailing-late pass rate, pace, and target concentration overlays plus late-lead RB carry redistribution without mutating neutral roster construction.

**Architecture:** Add a new `data/game_script` package that learns team-specific late-game profiles from historical PBP with Bayesian fallback, then attach those profiles and their config to `TeamDistributions` in `GameContextBuilder`. Add a new `engine/game_script.py` runtime helper that resolves the current regime from `GameState`, and have `play_caller`, `player_selector`, and `game_sim` consume that runtime script as transient per-play overlays. Keep phase 1 and phase 2 independently toggleable so A/B validation can isolate them.

**Tech Stack:** Python 3.12+, polars, numpy, dataclasses, pytest, Click, Rich

**Spec:** `docs/superpowers/specs/2026-04-10-game-script-garbage-time-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `src/fantasy_sim/data/game_script/models.py` | Create | Config dataclasses, learned profile dataclasses, diagnostics payload |
| `src/fantasy_sim/data/game_script/config.py` | Create | YAML/dict loader for `game_script:` defaults |
| `src/fantasy_sim/data/game_script/engine.py` | Create | Historical PBP learning, Bayesian shrinkage, per-team profile cache |
| `src/fantasy_sim/data/game_script/__init__.py` | Create | Export config/model/engine surface |
| `src/fantasy_sim/engine/game_script.py` | Create | Runtime regime resolver and overlay helpers |
| `src/fantasy_sim/engine/types.py` | Modify | Carry optional `game_script_config` and `game_script_profile` on `TeamDistributions` |
| `src/fantasy_sim/engine/play_caller.py` | Modify | Apply pass-rate overlay to bucket probabilities |
| `src/fantasy_sim/engine/player_selector.py` | Modify | Apply target concentration and RB redistribution at selection time |
| `src/fantasy_sim/engine/play_resolver.py` | Modify | Thread runtime script into receiver and rusher selection |
| `src/fantasy_sim/engine/game_sim.py` | Modify | Resolve runtime script each play and combine pace factors |
| `src/fantasy_sim/data/game_context.py` | Modify | Accept `game_script_config`, instantiate `GameScriptEngine`, attach profiles to team distributions |
| `src/fantasy_sim/validation/config.py` | Modify | Build and return `game_script_config` alongside existing engines |
| `src/fantasy_sim/validation/parallel.py` | Modify | Pass `game_script_config` through sequential, thread, and process build paths |
| `src/fantasy_sim/validation/game_script.py` | Create | Rich-formatted validation summary for learned game-script profiles |
| `src/fantasy_sim/cli.py` | Modify | Load `game_script` defaults and pass them into `GameContextBuilder` |
| `scripts/validate.py` | Modify | Print game-script profile summaries when Arm B enables the feature |
| `config/defaults.yaml` | Modify | Add `game_script:` config block with independent phase toggles |
| `tests/test_data/test_game_script_config.py` | Create | Config-loader coverage for nested game-script settings |
| `tests/test_data/test_game_script_integration.py` | Create | Builder wiring coverage for `game_script_config` acceptance and profile attachment |
| `tests/test_data/test_game_script_engine.py` | Create | Empirical-learning tests from synthetic PBP windows |
| `tests/test_engine/test_game_script.py` | Create | Runtime regime resolution and pace helper tests |
| `tests/test_engine/test_player_selector_game_script.py` | Create | Target concentration and RB redistribution selector behavior |
| `tests/test_engine/test_play_caller.py` | Modify | Pass-rate overlay coverage |
| `tests/test_validation/test_config.py` | Modify | Generic validation-config key coverage for `game_script_config` |
| `tests/test_validation/test_game_script_summary.py` | Create | Summary formatting coverage |

---

### Task 1: Add Game-Script Config, Profile Models, and Plumbing

**Files:**
- Create: `src/fantasy_sim/data/game_script/models.py`
- Create: `src/fantasy_sim/data/game_script/config.py`
- Create: `src/fantasy_sim/data/game_script/__init__.py`
- Modify: `src/fantasy_sim/engine/types.py:1-24`
- Modify: `src/fantasy_sim/data/game_context.py:18-20`
- Modify: `src/fantasy_sim/data/game_context.py:52-61`
- Modify: `src/fantasy_sim/data/game_context.py:167-183`
- Modify: `src/fantasy_sim/validation/config.py:10-15`
- Modify: `src/fantasy_sim/validation/config.py:69-100`
- Modify: `src/fantasy_sim/validation/parallel.py:176-197`
- Modify: `src/fantasy_sim/validation/parallel.py:242-260`
- Modify: `src/fantasy_sim/validation/parallel.py:401-435`
- Modify: `src/fantasy_sim/validation/parallel.py:530-600`
- Modify: `src/fantasy_sim/cli.py:10-14`
- Modify: `src/fantasy_sim/cli.py:110-138`
- Modify: `config/defaults.yaml:241-248`
- Create: `tests/test_data/test_game_script_config.py`
- Create: `tests/test_data/test_game_script_integration.py`
- Modify: `tests/test_validation/test_config.py`

- [ ] **Step 1: Write the failing config and plumbing tests**

Create `tests/test_data/test_game_script_config.py`:

```python
from fantasy_sim.data.game_script.config import load_game_script_config
from fantasy_sim.data.game_script.models import GameScriptConfig


def test_missing_key_returns_disabled_config():
    cfg = load_game_script_config({})
    assert isinstance(cfg, GameScriptConfig)
    assert cfg.enabled is False
    assert cfg.trailing_late.deficit_threshold == 8
    assert cfg.leading_late_rb.lead_threshold == 14


def test_nested_values_are_loaded():
    cfg = load_game_script_config(
        {
            "game_script": {
                "enabled": True,
                "trailing_late": {
                    "enabled": True,
                    "deficit_threshold": 10,
                    "final_five_minutes": 240,
                    "final_five_deficit_threshold": 3,
                    "pass_rate_prior_strength": 180,
                    "pace_prior_strength": 90,
                    "target_prior_strength": 40,
                    "pass_rate_clamp": [1.0, 1.25],
                    "pace_factor_clamp": [1.0, 1.10],
                    "target_rank_factor_clamp": [0.9, 1.2],
                },
                "leading_late_rb": {
                    "enabled": True,
                    "lead_threshold": 17,
                    "late_minutes": 420,
                    "rb_carry_prior_strength": 55,
                    "rb_rank_factor_clamp": [0.85, 1.15],
                },
            }
        }
    )
    assert cfg.enabled is True
    assert cfg.trailing_late.deficit_threshold == 10
    assert cfg.trailing_late.final_five_minutes == 240
    assert cfg.trailing_late.target_rank_factor_clamp == (0.9, 1.2)
    assert cfg.leading_late_rb.enabled is True
    assert cfg.leading_late_rb.lead_threshold == 17
    assert cfg.leading_late_rb.rb_rank_factor_clamp == (0.85, 1.15)
```

Create `tests/test_data/test_game_script_integration.py`:

```python
from fantasy_sim.data.game_context import GameContextBuilder
from fantasy_sim.data.game_script.models import (
    GameScriptConfig,
    LeadingLateRbConfig,
    TrailingLateConfig,
)


def test_builder_accepts_game_script_config():
    cfg = GameScriptConfig(
        enabled=True,
        trailing_late=TrailingLateConfig(enabled=True),
        leading_late_rb=LeadingLateRbConfig(enabled=False),
    )
    builder = GameContextBuilder(game_script_config=cfg)
    assert builder._game_script_config.enabled is True
    assert builder._game_script_engine is None
```

Modify `tests/test_validation/test_config.py` by adding:

```python
    def test_defaults_include_game_script_config(self):
        defaults = load_defaults()
        configs = build_engine_configs(defaults)
        assert "game_script_config" in configs
        assert configs["game_script_config"] is None


class TestBuildBareEngineConfigs:
    def test_game_script_is_none(self):
        configs = build_bare_engine_configs()
        assert configs["game_script_config"] is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
uv run pytest \
  tests/test_data/test_game_script_config.py \
  tests/test_data/test_game_script_integration.py \
  tests/test_validation/test_config.py -v
```

Expected:

- `ModuleNotFoundError: No module named 'fantasy_sim.data.game_script'`
- `KeyError: 'game_script_config'`

- [ ] **Step 3: Add the config and profile dataclasses**

Create `src/fantasy_sim/data/game_script/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TargetRankFactors:
    rank1: float = 1.0
    rank2: float = 1.0
    rank3_plus: float = 1.0


@dataclass(frozen=True)
class RbRankFactors:
    rb1: float = 1.0
    rb2: float = 1.0
    rb3_plus: float = 1.0


@dataclass(frozen=True)
class TrailingLateConfig:
    enabled: bool = True
    deficit_threshold: int = 8
    final_five_minutes: int = 300
    final_five_deficit_threshold: int = 4
    pass_rate_prior_strength: float = 250.0
    pace_prior_strength: float = 250.0
    target_prior_strength: float = 80.0
    pass_rate_clamp: tuple[float, float] = (1.00, 1.35)
    pace_factor_clamp: tuple[float, float] = (1.00, 1.20)
    target_rank_factor_clamp: tuple[float, float] = (0.85, 1.25)


@dataclass(frozen=True)
class LeadingLateRbConfig:
    enabled: bool = False
    lead_threshold: int = 14
    late_minutes: int = 600
    rb_carry_prior_strength: float = 100.0
    rb_rank_factor_clamp: tuple[float, float] = (0.80, 1.20)


@dataclass(frozen=True)
class GameScriptConfig:
    enabled: bool = False
    trailing_late: TrailingLateConfig = field(default_factory=TrailingLateConfig)
    leading_late_rb: LeadingLateRbConfig = field(default_factory=LeadingLateRbConfig)


@dataclass(frozen=True)
class GameScriptDiagnostics:
    trailing_late_play_count: int = 0
    trailing_late_pass_rate_ratio: float = 1.0
    trailing_late_pace_ratio: float = 1.0
    trailing_late_rank1_ratio: float = 1.0
    trailing_late_rank2_ratio: float = 1.0
    trailing_late_rank3_plus_ratio: float = 1.0
    leading_late_rb_play_count: int = 0
    leading_late_rb1_ratio: float = 1.0
    leading_late_rb2_ratio: float = 1.0
    leading_late_rb3_plus_ratio: float = 1.0


@dataclass(frozen=True)
class GameScriptProfile:
    team: str
    trailing_late_pass_rate_factor: float = 1.0
    trailing_late_pace_factor: float = 1.0
    trailing_late_target_factors: TargetRankFactors = field(default_factory=TargetRankFactors)
    leading_late_rb_factors: RbRankFactors = field(default_factory=RbRankFactors)
    diagnostics: GameScriptDiagnostics = field(default_factory=GameScriptDiagnostics)
```

Create `src/fantasy_sim/data/game_script/config.py`:

```python
from __future__ import annotations

from fantasy_sim.data.game_script.models import (
    GameScriptConfig,
    LeadingLateRbConfig,
    TrailingLateConfig,
)


def load_game_script_config(defaults: dict) -> GameScriptConfig:
    raw = defaults.get("game_script")
    if not raw:
        return GameScriptConfig(enabled=False)

    trailing = raw.get("trailing_late", {})
    leading = raw.get("leading_late_rb", {})

    return GameScriptConfig(
        enabled=raw.get("enabled", False),
        trailing_late=TrailingLateConfig(
            enabled=trailing.get("enabled", True),
            deficit_threshold=trailing.get("deficit_threshold", 8),
            final_five_minutes=trailing.get("final_five_minutes", 300),
            final_five_deficit_threshold=trailing.get("final_five_deficit_threshold", 4),
            pass_rate_prior_strength=trailing.get("pass_rate_prior_strength", 250.0),
            pace_prior_strength=trailing.get("pace_prior_strength", 250.0),
            target_prior_strength=trailing.get("target_prior_strength", 80.0),
            pass_rate_clamp=tuple(trailing.get("pass_rate_clamp", [1.00, 1.35])),
            pace_factor_clamp=tuple(trailing.get("pace_factor_clamp", [1.00, 1.20])),
            target_rank_factor_clamp=tuple(trailing.get("target_rank_factor_clamp", [0.85, 1.25])),
        ),
        leading_late_rb=LeadingLateRbConfig(
            enabled=leading.get("enabled", False),
            lead_threshold=leading.get("lead_threshold", 14),
            late_minutes=leading.get("late_minutes", 600),
            rb_carry_prior_strength=leading.get("rb_carry_prior_strength", 100.0),
            rb_rank_factor_clamp=tuple(leading.get("rb_rank_factor_clamp", [0.80, 1.20])),
        ),
    )
```

Create `src/fantasy_sim/data/game_script/__init__.py`:

```python
from fantasy_sim.data.game_script.config import load_game_script_config
from fantasy_sim.data.game_script.models import (
    GameScriptConfig,
    GameScriptDiagnostics,
    GameScriptProfile,
    LeadingLateRbConfig,
    RbRankFactors,
    TargetRankFactors,
    TrailingLateConfig,
)

__all__ = [
    "GameScriptConfig",
    "GameScriptDiagnostics",
    "GameScriptProfile",
    "LeadingLateRbConfig",
    "RbRankFactors",
    "TargetRankFactors",
    "TrailingLateConfig",
    "load_game_script_config",
]
```

- [ ] **Step 4: Thread the new config through the existing surfaces**

In `src/fantasy_sim/engine/types.py`, replace the top of the file with:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from fantasy_sim.data.game_script.models import GameScriptConfig, GameScriptProfile
from fantasy_sim.models.distributions import (
    PlayCallingDist, PlayOutcomeDist, TurnoverRates, KickingModel, DriveStartModel,
)


@dataclass
class DefensiveTdRates:
    """Team-specific defensive TD rates (replaces fixed constants in game_sim)."""
    int_return_td_rate: float = 0.20
    fumble_return_td_rate: float = 0.10


@dataclass
class TeamDistributions:
    """All distributions needed to simulate one team."""
    play_calling: PlayCallingDist
    play_outcomes: PlayOutcomeDist
    turnover_rates: TurnoverRates
    kicking: KickingModel
    drive_start: DriveStartModel
    pace_factor: float = 1.0
    defensive_td_rates: DefensiveTdRates = field(default_factory=DefensiveTdRates)
    game_script_config: GameScriptConfig | None = None
    game_script_profile: GameScriptProfile | None = None
```

In `src/fantasy_sim/data/game_context.py`, add the new import and constructor parameter:

```python
from fantasy_sim.data.game_script.models import GameScriptConfig
```

```python
    def __init__(
        self,
        cache_dir: Path = DEFAULT_CACHE_DIR,
        pff_config: PffConfig | None = None,
        weather_config: WeatherConfig | None = None,
        vegas_config: VegasConfig | None = None,
        props_config: PropsConfig | None = None,
        usage_config: UsageConfig | None = None,
        td_tendency_config: TdTendencyConfig | None = None,
        game_script_config: GameScriptConfig | None = None,
    ):
```

Add the stored attribute near the existing engine setup:

```python
        self._game_script_engine = None
        self._game_script_config = game_script_config or GameScriptConfig(enabled=False)
```

In `src/fantasy_sim/validation/config.py`, add the new import and dict key:

```python
from fantasy_sim.data.game_script.config import load_game_script_config
```

```python
    game_script = load_game_script_config(config)
    return {
        "pff_config": pff if pff.enabled else None,
        "weather_config": weather if weather.enabled else None,
        "vegas_config": vegas if vegas.enabled else None,
        "props_config": props if props.enabled else None,
        "usage_config": usage if usage.enabled else None,
        "td_tendency_config": td_tendency if td_tendency.enabled else None,
        "game_script_config": game_script if game_script.enabled else None,
    }
```

```python
    return {
        "pff_config": None,
        "weather_config": None,
        "vegas_config": None,
        "props_config": None,
        "usage_config": None,
        "td_tendency_config": None,
        "game_script_config": None,
    }
```

In `src/fantasy_sim/validation/parallel.py`, thread `game_script_config` through every builder creation point:

```python
def _init_build_worker_single(
    cache_dir: Path,
    pff_config: "PffConfig | None",
    weather_config: "WeatherConfig | None",
    vegas_config: "VegasConfig | None" = None,
    props_config: "PropsConfig | None" = None,
    usage_config: "UsageConfig | None" = None,
    td_tendency_config: "TdTendencyConfig | None" = None,
    game_script_config: "GameScriptConfig | None" = None,
) -> None:
```

```python
    builder = GameContextBuilder(
        cache_dir=cache_dir,
        pff_config=pff_config,
        weather_config=weather_config,
        vegas_config=vegas_config,
        props_config=props_config,
        usage_config=usage_config,
        td_tendency_config=td_tendency_config,
        game_script_config=game_script_config,
    )
```

Also update `_init_build_worker_dual()` in `src/fantasy_sim/validation/parallel.py`:

```python
def _init_build_worker_dual(
    cache_dir: Path,
    pff_config: PffConfig | None,
    weather_config: WeatherConfig | None,
    vegas_config: "VegasConfig | None" = None,
    props_config: "PropsConfig | None" = None,
    usage_config: "UsageConfig | None" = None,
    td_tendency_config: "TdTendencyConfig | None" = None,
    game_script_config: "GameScriptConfig | None" = None,
) -> None:
```

```python
    _worker_builders = {
        "off": GameContextBuilder(cache_dir=cache_dir),
        "on": GameContextBuilder(
            cache_dir=cache_dir,
            pff_config=pff_config,
            weather_config=weather_config,
            vegas_config=vegas_config,
            props_config=props_config,
            usage_config=usage_config,
            td_tendency_config=td_tendency_config,
            game_script_config=game_script_config,
        ),
    }
```

Update `_create_builders()` in `src/fantasy_sim/validation/parallel.py`:

```python
def _create_builders(
    cache_dir: Path,
    pff_config,
    weather_config,
    vegas_config,
    props_config,
    usage_config,
    td_tendency_config,
    game_script_config,
    dual_arm: bool,
) -> dict:
```

```python
    return {
        "single": GameContextBuilder(
            cache_dir=cache_dir,
            pff_config=pff_config,
            weather_config=weather_config,
            vegas_config=vegas_config,
            props_config=props_config,
            usage_config=usage_config,
            td_tendency_config=td_tendency_config,
            game_script_config=game_script_config,
        ),
    }
```

Update `build_games_parallel()` in `src/fantasy_sim/validation/parallel.py`:

```python
def build_games_parallel(
    game_args: list[tuple],
    cache_dir: Path,
    pff_config=None,
    weather_config=None,
    vegas_config=None,
    props_config=None,
    usage_config=None,
    td_tendency_config=None,
    game_script_config=None,
    max_workers: int | None = None,
    dual_arm: bool = False,
    on_complete: "Callable[[int, int], None] | None" = None,
) -> list[dict]:
```

Update the process-pool initializer tuple:

```python
                initargs=(
                    cache_dir,
                    pff_config,
                    weather_config,
                    vegas_config,
                    props_config,
                    usage_config,
                    td_tendency_config,
                    game_script_config,
                ),
```

Update the thread-path builder creation call:

```python
        builders = _create_builders(
            cache_dir,
            pff_config,
            weather_config,
            vegas_config,
            props_config,
            usage_config,
            td_tendency_config,
            game_script_config,
            dual_arm,
        )
```

In `src/fantasy_sim/cli.py`, add the loader import and pass the config through `_make_builder()`:

```python
from fantasy_sim.data.game_script.config import load_game_script_config
```

```python
    game_script_config = load_game_script_config(defaults)
    return GameContextBuilder(
        cache_dir=loader.cache_dir,
        pff_config=pff_config,
        weather_config=weather_config,
        vegas_config=vegas_config,
        props_config=props_config,
        usage_config=usage_config,
        td_tendency_config=td_tendency_config,
        game_script_config=game_script_config,
    )
```

In `config/defaults.yaml`, add:

```yaml
game_script:
  enabled: false
  trailing_late:
    enabled: true
    deficit_threshold: 8
    final_five_minutes: 300
    final_five_deficit_threshold: 4
    pass_rate_prior_strength: 250
    pace_prior_strength: 250
    target_prior_strength: 80
    pass_rate_clamp: [1.00, 1.35]
    pace_factor_clamp: [1.00, 1.20]
    target_rank_factor_clamp: [0.85, 1.25]
  leading_late_rb:
    enabled: false
    lead_threshold: 14
    late_minutes: 600
    rb_carry_prior_strength: 100
    rb_rank_factor_clamp: [0.80, 1.20]
```

- [ ] **Step 5: Run the targeted tests to verify the scaffolding passes**

Run:

```bash
uv run pytest \
  tests/test_data/test_game_script_config.py \
  tests/test_data/test_game_script_integration.py \
  tests/test_validation/test_config.py -v
```

Expected:

- all tests PASS
- no import errors for `fantasy_sim.data.game_script`

- [ ] **Step 6: Commit**

```bash
git add \
  src/fantasy_sim/data/game_script/models.py \
  src/fantasy_sim/data/game_script/config.py \
  src/fantasy_sim/data/game_script/__init__.py \
  src/fantasy_sim/engine/types.py \
  src/fantasy_sim/data/game_context.py \
  src/fantasy_sim/validation/config.py \
  src/fantasy_sim/validation/parallel.py \
  src/fantasy_sim/cli.py \
  config/defaults.yaml \
  tests/test_data/test_game_script_config.py \
  tests/test_data/test_game_script_integration.py \
  tests/test_validation/test_config.py
git commit -F - <<'EOF'
Establish game-script config plumbing and neutral profile types

Add the game_script config dataclasses and carry them through
GameContextBuilder, CLI, and validation so runtime behavior can be
added in later tasks without reopening the construction path.

Constraint: The new feature must be independently toggleable in A/B validation
Rejected: Hardcode thresholds in engine helpers only | would block config sweeps
Confidence: high
Scope-risk: narrow
Directive: Keep YAML parsing isolated in data/game_script/config.py
Tested: uv run pytest tests/test_data/test_game_script_config.py tests/test_data/test_game_script_integration.py tests/test_validation/test_config.py -v
Not-tested: full test suite
EOF
```

---

### Task 2: Add Runtime Regime Resolution and Pass/Pace Overlays

**Files:**
- Create: `src/fantasy_sim/engine/game_script.py`
- Modify: `src/fantasy_sim/engine/play_caller.py:1-18`
- Modify: `src/fantasy_sim/engine/game_sim.py:4-95`
- Create: `tests/test_engine/test_game_script.py`
- Modify: `tests/test_engine/test_play_caller.py`

- [ ] **Step 1: Write failing tests for runtime regime resolution and pass-rate overlay**

Create `tests/test_engine/test_game_script.py`:

```python
import numpy as np
import pytest

from fantasy_sim.data.game_script.models import (
    GameScriptConfig,
    GameScriptProfile,
    LeadingLateRbConfig,
    RbRankFactors,
    TargetRankFactors,
    TrailingLateConfig,
)
from fantasy_sim.engine.game_script import effective_pace_factor, resolve_game_script
from fantasy_sim.engine.types import GameState


def make_state(**overrides) -> GameState:
    defaults = dict(
        quarter=4,
        clock=900,
        possession="home",
        down=1,
        distance=10,
        yard_line=75,
        home_score=0,
        away_score=0,
        home_team="KC",
        away_team="BUF",
        receiving_2nd_half="away",
    )
    defaults.update(overrides)
    return GameState(**defaults)


def make_config() -> GameScriptConfig:
    return GameScriptConfig(
        enabled=True,
        trailing_late=TrailingLateConfig(enabled=True),
        leading_late_rb=LeadingLateRbConfig(enabled=True),
    )


def make_profile() -> GameScriptProfile:
    return GameScriptProfile(
        team="KC",
        trailing_late_pass_rate_factor=1.18,
        trailing_late_pace_factor=1.08,
        trailing_late_target_factors=TargetRankFactors(rank1=1.2, rank2=1.0, rank3_plus=0.85),
        leading_late_rb_factors=RbRankFactors(rb1=0.85, rb2=1.15, rb3_plus=1.0),
    )


def test_trailing_late_uses_deficit_threshold():
    state = make_state(home_score=14, away_score=24, clock=700)
    script = resolve_game_script(state, make_config(), make_profile())
    assert script.regime == "trailing_late"
    assert script.pass_rate_factor == 1.18
    assert script.pace_factor == 1.08


def test_trailing_late_uses_final_five_rule():
    state = make_state(home_score=20, away_score=24, clock=240)
    script = resolve_game_script(state, make_config(), make_profile())
    assert script.regime == "trailing_late"


def test_leading_late_rb_uses_lead_threshold():
    state = make_state(home_score=31, away_score=14, clock=300)
    script = resolve_game_script(state, make_config(), make_profile())
    assert script.regime == "leading_late_rb"
    assert script.rb_factors.rb2 == 1.15


def test_neutral_when_feature_disabled():
    state = make_state(home_score=24, away_score=21, clock=240)
    script = resolve_game_script(state, GameScriptConfig(enabled=False), make_profile())
    assert script.regime == "neutral"
    assert script.pass_rate_factor == 1.0


def test_effective_pace_factor_multiplies_base_and_script():
    state = make_state(home_score=14, away_score=24, clock=240)
    script = resolve_game_script(state, make_config(), make_profile())
    assert effective_pace_factor(1.05, script) == pytest.approx(1.05 * 1.08)
```

In `tests/test_engine/test_play_caller.py`, add this import near the top:

```python
from fantasy_sim.engine.game_script import RuntimeGameScript
```

Then add this method inside `class TestSelectPlayType:`:

```python
    def test_script_pass_factor_pushes_pass_rate_up(self):
        rng = np.random.default_rng(42)
        state = make_state()
        play_calling = make_play_calling(pass_rate=0.50)
        script = RuntimeGameScript(
            regime="trailing_late",
            pass_rate_factor=1.30,
        )
        results = [select_play_type(state, play_calling, rng, script=script) for _ in range(1000)]
        pass_rate = sum(1 for r in results if r == "pass") / 1000
        assert pass_rate > 0.58
```
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
uv run pytest \
  tests/test_engine/test_game_script.py \
  tests/test_engine/test_play_caller.py -v
```

Expected:

- `ModuleNotFoundError: No module named 'fantasy_sim.engine.game_script'`
- `TypeError: select_play_type() got an unexpected keyword argument 'script'`

- [ ] **Step 3: Add the runtime helper and wire play-calling and pace**

Create `src/fantasy_sim/engine/game_script.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field

from fantasy_sim.data.game_script.models import (
    GameScriptConfig,
    GameScriptProfile,
    RbRankFactors,
    TargetRankFactors,
)
from fantasy_sim.engine.types import GameState


@dataclass(frozen=True)
class RuntimeGameScript:
    regime: str = "neutral"
    pass_rate_factor: float = 1.0
    pace_factor: float = 1.0
    target_factors: TargetRankFactors = field(default_factory=TargetRankFactors)
    rb_factors: RbRankFactors = field(default_factory=RbRankFactors)


def resolve_game_script(
    state: GameState,
    config: GameScriptConfig | None,
    profile: GameScriptProfile | None,
) -> RuntimeGameScript:
    if config is None or profile is None or not config.enabled:
        return RuntimeGameScript()

    trailing = config.trailing_late
    if trailing.enabled and state.quarter == 4:
        if state.score_differential <= -trailing.deficit_threshold:
            return RuntimeGameScript(
                regime="trailing_late",
                pass_rate_factor=profile.trailing_late_pass_rate_factor,
                pace_factor=profile.trailing_late_pace_factor,
                target_factors=profile.trailing_late_target_factors,
            )
        if (
            state.clock <= trailing.final_five_minutes
            and state.score_differential <= -trailing.final_five_deficit_threshold
        ):
            return RuntimeGameScript(
                regime="trailing_late",
                pass_rate_factor=profile.trailing_late_pass_rate_factor,
                pace_factor=profile.trailing_late_pace_factor,
                target_factors=profile.trailing_late_target_factors,
            )

    leading = config.leading_late_rb
    if (
        leading.enabled
        and state.quarter == 4
        and state.clock <= leading.late_minutes
        and state.score_differential >= leading.lead_threshold
    ):
        return RuntimeGameScript(
            regime="leading_late_rb",
            rb_factors=profile.leading_late_rb_factors,
        )

    return RuntimeGameScript()


def apply_pass_rate_factor(probs: dict[str, float], factor: float) -> dict[str, float]:
    pass_prob = max(0.01, min(0.99, probs["pass"] * factor))
    return {"pass": pass_prob, "run": 1.0 - pass_prob}


def effective_pace_factor(base_pace: float, script: RuntimeGameScript | None) -> float:
    if script is None:
        return base_pace
    return base_pace * script.pace_factor
```

In `src/fantasy_sim/engine/play_caller.py`, replace `select_play_type()` with:

```python
import numpy as np
from fantasy_sim.engine.game_script import RuntimeGameScript, apply_pass_rate_factor
from fantasy_sim.engine.types import GameState
from fantasy_sim.models.distributions import PlayCallingDist, KickingModel
from fantasy_sim.models.game_state import bucket_play


def select_play_type(
    state: GameState,
    play_calling: PlayCallingDist,
    rng: np.random.Generator,
    script: RuntimeGameScript | None = None,
) -> str:
    """Select run or pass based on game state and team tendencies."""
    bucket = bucket_play(
        state.down, state.distance, state.score_differential,
        state.quarter, state.yard_line,
    )
    probs = play_calling.get_probs(bucket)
    if script is not None and script.pass_rate_factor != 1.0:
        probs = apply_pass_rate_factor(probs, script.pass_rate_factor)
    play_types = list(probs.keys())
    probabilities = list(probs.values())
    return rng.choice(play_types, p=probabilities)
```

In `src/fantasy_sim/engine/game_sim.py`, add the runtime resolution and pace combination:

```python
from fantasy_sim.engine.game_script import effective_pace_factor, resolve_game_script
```

```python
        script = resolve_game_script(
            state,
            off_dists.game_script_config,
            off_dists.game_script_profile,
        )

        play_type = select_play_type(state, off_dists.play_calling, rng, script=script)
```

```python
        result = resolve_play(
            state, play_type, off_dists.play_outcomes,
            off_dists.turnover_rates, rng, roster=roster,
            is_home=is_home_team,
            pace_factor=effective_pace_factor(off_dists.pace_factor, script),
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```bash
uv run pytest \
  tests/test_engine/test_game_script.py \
  tests/test_engine/test_play_caller.py -v
```

Expected:

- all tests PASS
- pass-rate overlay test shows higher pass frequency than the neutral 0.50 baseline

- [ ] **Step 5: Run a targeted regression pass**

Run:

```bash
uv run pytest \
  tests/test_engine/test_game_sim.py \
  tests/test_engine/test_types.py -v
```

Expected:

- all tests PASS
- `simulate_game()` still returns a valid `GameResult` when no game-script profile is attached

- [ ] **Step 6: Commit**

```bash
git add \
  src/fantasy_sim/engine/game_script.py \
  src/fantasy_sim/engine/play_caller.py \
  src/fantasy_sim/engine/game_sim.py \
  tests/test_engine/test_game_script.py \
  tests/test_engine/test_play_caller.py
git commit -F - <<'EOF'
Add runtime game-script regime resolution and pass/pace overlays

Resolve a per-play game-script regime from GameState and apply its
pass-rate and pace multipliers without mutating the neutral roster
or team distributions.

Constraint: Phase 1 must not touch fourth-down or PAT logic
Rejected: Inline threshold checks inside play_caller only | would hide pace handling and make selector reuse harder
Confidence: high
Scope-risk: narrow
Directive: Keep resolve_game_script pure and side-effect-free
Tested: uv run pytest tests/test_engine/test_game_script.py tests/test_engine/test_play_caller.py tests/test_engine/test_game_sim.py tests/test_engine/test_types.py -v
Not-tested: full suite
EOF
```

---

### Task 3: Add Trailing-Late Receiver Target Concentration

**Files:**
- Modify: `src/fantasy_sim/engine/player_selector.py:1-71`
- Modify: `src/fantasy_sim/engine/play_resolver.py:91-110`
- Modify: `src/fantasy_sim/engine/game_sim.py:86-95`
- Create: `tests/test_engine/test_player_selector_game_script.py`

- [ ] **Step 1: Write failing tests for receiver concentration**

Create `tests/test_engine/test_player_selector_game_script.py`:

```python
import numpy as np

from fantasy_sim.data.game_script.models import TargetRankFactors
from fantasy_sim.engine.game_script import RuntimeGameScript
from fantasy_sim.engine.player_selector import select_receiver
from fantasy_sim.engine.types import GameState
from fantasy_sim.models.player import PlayerModel, PlayerOutcomes, PlayerUsage, TeamRoster


def make_state(**overrides) -> GameState:
    defaults = dict(
        quarter=4,
        clock=240,
        possession="home",
        down=1,
        distance=10,
        yard_line=40,
        home_score=17,
        away_score=24,
        home_team="KC",
        away_team="BUF",
        receiving_2nd_half="away",
        week=10,
    )
    defaults.update(overrides)
    return GameState(**defaults)


def make_receiver_roster() -> TeamRoster:
    return TeamRoster(
        team="KC",
        players=[
            PlayerModel("QB1", "QB1", "QB", "KC", PlayerUsage(snap_share=1.0), PlayerOutcomes()),
            PlayerModel(
                "WR1",
                "WR1",
                "WR",
                "KC",
                PlayerUsage(target_share=0.30, red_zone_target_share=0.35),
                PlayerOutcomes(catch_rate=0.65),
            ),
            PlayerModel(
                "WR2",
                "WR2",
                "WR",
                "KC",
                PlayerUsage(target_share=0.18, red_zone_target_share=0.18),
                PlayerOutcomes(catch_rate=0.60),
            ),
            PlayerModel(
                "TE1",
                "TE1",
                "TE",
                "KC",
                PlayerUsage(target_share=0.12, red_zone_target_share=0.20),
                PlayerOutcomes(catch_rate=0.70),
            ),
            PlayerModel(
                "RB1",
                "RB1",
                "RB",
                "KC",
                PlayerUsage(carry_share=0.60, target_share=0.08, red_zone_target_share=0.07),
                PlayerOutcomes(catch_rate=0.72),
            ),
        ],
    )


def test_trailing_late_concentrates_targets_to_rank1():
    roster = make_receiver_roster()
    state = make_state()
    script = RuntimeGameScript(
        regime="trailing_late",
        target_factors=TargetRankFactors(rank1=1.30, rank2=0.95, rank3_plus=0.75),
    )
    rng_neutral = np.random.default_rng(42)
    rng_script = np.random.default_rng(42)

    neutral = [select_receiver(roster, state, rng_neutral).player_id for _ in range(1500)]
    scripted = [select_receiver(roster, state, rng_script, script=script).player_id for _ in range(1500)]

    assert scripted.count("WR1") > neutral.count("WR1")


def test_red_zone_selection_uses_red_zone_shares_then_concentration():
    roster = make_receiver_roster()
    state = make_state(yard_line=12)
    script = RuntimeGameScript(
        regime="trailing_late",
        target_factors=TargetRankFactors(rank1=1.25, rank2=1.0, rank3_plus=0.80),
    )
    rng = np.random.default_rng(7)
    receiver = select_receiver(roster, state, rng, script=script)
    assert receiver.player_id in {"WR1", "WR2", "TE1", "RB1"}


def test_neutral_script_preserves_existing_behavior():
    roster = make_receiver_roster()
    state = make_state()
    rng_a = np.random.default_rng(9)
    rng_b = np.random.default_rng(9)

    neutral = [select_receiver(roster, state, rng_a).player_id for _ in range(300)]
    scripted = [select_receiver(roster, state, rng_b, script=RuntimeGameScript()).player_id for _ in range(300)]
    assert neutral == scripted
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
uv run pytest tests/test_engine/test_player_selector_game_script.py -v
```

Expected:

- `TypeError: select_receiver() got an unexpected keyword argument 'script'`

- [ ] **Step 3: Add receiver-side target concentration and thread the script through play resolution**

In `src/fantasy_sim/engine/player_selector.py`, replace `select_receiver()` with:

```python
import numpy as np
from fantasy_sim.engine.game_script import RuntimeGameScript
from fantasy_sim.engine.types import GameState
from fantasy_sim.models.player import PlayerModel, TeamRoster
```

```python
def _receiver_rank_factor(rank: int, script: RuntimeGameScript | None) -> float:
    if script is None or script.regime != "trailing_late":
        return 1.0
    if rank == 0:
        return script.target_factors.rank1
    if rank == 1:
        return script.target_factors.rank2
    return script.target_factors.rank3_plus


def select_receiver(
    roster: TeamRoster,
    state: GameState,
    rng: np.random.Generator,
    script: RuntimeGameScript | None = None,
) -> PlayerModel:
    """Select a receiver weighted by target share, filtering out missed-week players."""
    filtered = _filter_available(roster, state)
    eligible = [p for p in filtered.players if p.usage.target_share > 0]
    if not eligible:
        eligible = [p for p in filtered.players if p.position != "QB"]
    if not eligible:
        raise ValueError(f"No eligible receivers on roster for {roster.team}")

    is_red_zone = state.yard_line <= 20
    base_weights = np.array(
        [
            p.usage.red_zone_target_share if is_red_zone and p.usage.red_zone_target_share > 0
            else p.usage.target_share
            for p in eligible
        ],
        dtype=float,
    )

    ranked = sorted(
        range(len(eligible)),
        key=lambda idx: base_weights[idx],
        reverse=True,
    )
    adjusted = base_weights.copy()
    for rank, idx in enumerate(ranked):
        adjusted[idx] *= _receiver_rank_factor(rank, script)

    if adjusted.sum() == 0:
        adjusted = np.ones(len(eligible), dtype=float)
    adjusted = adjusted / adjusted.sum()
    return eligible[rng.choice(len(eligible), p=adjusted)]
```

In `src/fantasy_sim/engine/play_resolver.py`, update the public signature and pass the script into receiver selection:

```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from fantasy_sim.engine.game_script import RuntimeGameScript
    from fantasy_sim.models.player import TeamRoster
```

```python
def resolve_play(
    state: GameState,
    play_type: str,
    play_outcomes: PlayOutcomeDist,
    turnover_rates: TurnoverRates,
    rng: np.random.Generator,
    roster: TeamRoster | None = None,
    is_home: bool = False,
    pace_factor: float = 1.0,
    script: "RuntimeGameScript | None" = None,
) -> PlayResult:
```

```python
        receiver = select_receiver(roster, state, rng, script=script)
```

In `src/fantasy_sim/engine/game_sim.py`, pass the runtime script into `resolve_play()`:

```python
        result = resolve_play(
            state, play_type, off_dists.play_outcomes,
            off_dists.turnover_rates, rng, roster=roster,
            is_home=is_home_team,
            pace_factor=effective_pace_factor(off_dists.pace_factor, script),
            script=script,
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```bash
uv run pytest \
  tests/test_engine/test_player_selector_game_script.py \
  tests/test_engine/test_play_resolver.py -v
```

Expected:

- new selector tests PASS
- existing resolver tests still PASS with the default `script=None` path

- [ ] **Step 5: Run a focused regression pass**

Run:

```bash
uv run pytest \
  tests/test_engine/test_player_selector.py \
  tests/test_engine/test_game_sim.py -v
```

Expected:

- all tests PASS
- neutral game simulation remains unchanged

- [ ] **Step 6: Commit**

```bash
git add \
  src/fantasy_sim/engine/player_selector.py \
  src/fantasy_sim/engine/play_resolver.py \
  src/fantasy_sim/engine/game_sim.py \
  tests/test_engine/test_player_selector_game_script.py
git commit -F - <<'EOF'
Add trailing-late receiver target concentration overlays

Apply rank-based target concentration only at receiver selection time
so late-game alpha consolidation happens without mutating the base
roster shares stored in TeamRoster.

Constraint: Red-zone share logic must remain intact and compose with late-game concentration
Rejected: Mutate roster.target_share in build_game | would contaminate neutral baselines and overrides
Confidence: high
Scope-risk: moderate
Directive: Keep target concentration logic in engine/player_selector.py, not TeamRoster
Tested: uv run pytest tests/test_engine/test_player_selector_game_script.py tests/test_engine/test_play_resolver.py tests/test_engine/test_player_selector.py tests/test_engine/test_game_sim.py -v
Not-tested: full suite
EOF
```

---

### Task 4: Add Late-Lead RB Carry Redistribution

**Files:**
- Modify: `src/fantasy_sim/engine/player_selector.py:54-71`
- Modify: `src/fantasy_sim/engine/play_resolver.py:274-289`
- Modify: `tests/test_engine/test_player_selector_game_script.py`

- [ ] **Step 1: Write failing tests for RB redistribution**

Append to `tests/test_engine/test_player_selector_game_script.py`:

```python
from fantasy_sim.data.game_script.models import RbRankFactors
from fantasy_sim.engine.player_selector import _apply_rb_rank_factors, select_rusher


def make_rusher_roster() -> TeamRoster:
    return TeamRoster(
        team="KC",
        players=[
            PlayerModel("QB1", "QB1", "QB", "KC", PlayerUsage(snap_share=1.0, carry_share=0.12), PlayerOutcomes()),
            PlayerModel("RB1", "RB1", "RB", "KC", PlayerUsage(carry_share=0.58), PlayerOutcomes()),
            PlayerModel("RB2", "RB2", "RB", "KC", PlayerUsage(carry_share=0.22), PlayerOutcomes()),
            PlayerModel("RB3", "RB3", "RB", "KC", PlayerUsage(carry_share=0.08), PlayerOutcomes()),
        ],
    )


def test_leading_late_rb_increases_rb2_selection():
    roster = make_rusher_roster()
    state = make_state(home_score=31, away_score=14, clock=300)
    script = RuntimeGameScript(
        regime="leading_late_rb",
        rb_factors=RbRankFactors(rb1=0.80, rb2=1.30, rb3_plus=1.10),
    )
    rng_neutral = np.random.default_rng(5)
    rng_script = np.random.default_rng(5)

    neutral = [select_rusher(roster, state, rng_neutral).player_id for _ in range(1500)]
    scripted = [select_rusher(roster, state, rng_script, script=script).player_id for _ in range(1500)]

    assert scripted.count("RB2") > neutral.count("RB2")


def test_rb_redistribution_preserves_non_rb_mass():
    players = make_rusher_roster().players
    weights = np.array([0.12, 0.58, 0.22, 0.08], dtype=float)
    script = RuntimeGameScript(
        regime="leading_late_rb",
        rb_factors=RbRankFactors(rb1=0.80, rb2=1.30, rb3_plus=1.10),
    )
    adjusted = _apply_rb_rank_factors(players, weights, script)
    assert adjusted[0] == weights[0]
    assert adjusted[1:].sum() == weights[1:].sum()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
uv run pytest tests/test_engine/test_player_selector_game_script.py -v
```

Expected:

- `ImportError: cannot import name '_apply_rb_rank_factors'`
- `TypeError: select_rusher() got an unexpected keyword argument 'script'`

- [ ] **Step 3: Add RB subgroup redistribution without touching QB carry mass**

In `src/fantasy_sim/engine/player_selector.py`, add the helper and update `select_rusher()`:

```python
def _rb_rank_factor(rank: int, script: RuntimeGameScript | None) -> float:
    if script is None or script.regime != "leading_late_rb":
        return 1.0
    if rank == 0:
        return script.rb_factors.rb1
    if rank == 1:
        return script.rb_factors.rb2
    return script.rb_factors.rb3_plus


def _apply_rb_rank_factors(
    players: list[PlayerModel],
    weights: np.ndarray,
    script: RuntimeGameScript | None,
) -> np.ndarray:
    if script is None or script.regime != "leading_late_rb":
        return weights

    rb_indices = [idx for idx, player in enumerate(players) if player.position == "RB"]
    if len(rb_indices) < 2:
        return weights

    rb_total = float(weights[rb_indices].sum())
    if rb_total == 0:
        return weights

    adjusted = weights.copy()
    ranked = sorted(rb_indices, key=lambda idx: weights[idx], reverse=True)
    rb_weights = np.array(
        [weights[idx] * _rb_rank_factor(rank, script) for rank, idx in enumerate(ranked)],
        dtype=float,
    )
    rb_weights = (rb_weights / rb_weights.sum()) * rb_total

    for value, idx in zip(rb_weights, ranked):
        adjusted[idx] = value
    return adjusted


def select_rusher(
    roster: TeamRoster,
    state: GameState,
    rng: np.random.Generator,
    is_scramble: bool = False,
    script: RuntimeGameScript | None = None,
) -> PlayerModel:
    """Select a ball carrier, filtering out missed-week players."""
    if is_scramble:
        if state.week > 0:
            filtered = _filter_available(roster, state)
            try:
                return filtered.get_starting_qb()
            except ValueError:
                pass
        return roster.get_starting_qb()

    filtered = _filter_available(roster, state)
    eligible = [
        p for p in filtered.players
        if p.usage.carry_share > 0
        and (p.position != "QB" or p.usage.carry_share >= 0.10)
    ]
    if not eligible:
        eligible = [p for p in filtered.players if p.position == "RB"]
    if not eligible:
        raise ValueError(f"No eligible rushers on roster for {roster.team}")

    is_red_zone = state.yard_line <= 20
    weights = np.array(
        [
            p.usage.red_zone_carry_share if is_red_zone and p.usage.red_zone_carry_share > 0
            else p.usage.carry_share
            for p in eligible
        ],
        dtype=float,
    )

    weights = _apply_rb_rank_factors(eligible, weights, script)
    if weights.sum() == 0:
        weights = np.ones(len(eligible), dtype=float)
    weights = weights / weights.sum()
    return eligible[rng.choice(len(eligible), p=weights)]
```

In `src/fantasy_sim/engine/play_resolver.py`, change the run-path selection line to:

```python
        rusher = select_rusher(roster, state, rng, script=script)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```bash
uv run pytest tests/test_engine/test_player_selector_game_script.py -v
```

Expected:

- all tests PASS
- `RB2` frequency increases under the leading-late script

- [ ] **Step 5: Run a focused regression pass**

Run:

```bash
uv run pytest \
  tests/test_engine/test_player_selector.py \
  tests/test_engine/test_play_resolver.py -v
```

Expected:

- all tests PASS
- scramble path still returns the QB

- [ ] **Step 6: Commit**

```bash
git add \
  src/fantasy_sim/engine/player_selector.py \
  src/fantasy_sim/engine/play_resolver.py \
  tests/test_engine/test_player_selector_game_script.py
git commit -F - <<'EOF'
Add late-lead RB carry redistribution overlays

Redistribute rushing weight among RBs only in late blowout states so
secondary backs can absorb protected-lead volume without changing QB
designed-run behavior or the neutral carry tree.

Constraint: Non-RB carry mass must remain unchanged
Rejected: Reweight the full eligible rusher pool | would distort QB and WR carry shares
Confidence: high
Scope-risk: moderate
Directive: Preserve RB subgroup mass before renormalizing the full selection weights
Tested: uv run pytest tests/test_engine/test_player_selector_game_script.py tests/test_engine/test_player_selector.py tests/test_engine/test_play_resolver.py -v
Not-tested: full suite
EOF
```

---

### Task 5: Implement GameScriptEngine and Attach Profiles in GameContextBuilder

**Files:**
- Create: `src/fantasy_sim/data/game_script/engine.py`
- Modify: `src/fantasy_sim/data/game_context.py:175-182`
- Modify: `src/fantasy_sim/data/game_context.py:636-884`
- Modify: `tests/test_data/test_game_script_integration.py`
- Create: `tests/test_data/test_game_script_engine.py`
- Modify: `tests/test_data/test_game_context.py`

- [ ] **Step 1: Write failing tests for empirical learning and builder attachment**

Create `tests/test_data/test_game_script_engine.py`:

```python
import polars as pl

from fantasy_sim.data.game_script.engine import GameScriptEngine
from fantasy_sim.data.game_script.models import GameScriptConfig


def make_game_script_pbp() -> pl.DataFrame:
    plays = []

    # KC neutral: 10 pass, 10 run, WR1=6 targets, WR2=3, TE1=1, RB1=10 carries, RB2=0
    for week in range(1, 5):
        for _ in range(3):
            plays.append(
                {
                    "season": 2024,
                    "week": week,
                    "posteam": "KC",
                    "play_type": "pass",
                    "pass_attempt": 1,
                    "rush_attempt": 0,
                    "receiver_player_id": "WR1",
                    "rusher_player_id": None,
                    "score_differential": 0,
                    "qtr": 2,
                    "game_seconds_remaining": 1800,
                }
            )
        for _ in range(2):
            plays.append(
                {
                    "season": 2024,
                    "week": week,
                    "posteam": "KC",
                    "play_type": "pass",
                    "pass_attempt": 1,
                    "rush_attempt": 0,
                    "receiver_player_id": "WR2",
                    "rusher_player_id": None,
                    "score_differential": 0,
                    "qtr": 2,
                    "game_seconds_remaining": 1800,
                }
            )
        plays.append(
            {
                "season": 2024,
                "week": week,
                "posteam": "KC",
                "play_type": "pass",
                "pass_attempt": 1,
                "rush_attempt": 0,
                "receiver_player_id": "TE1",
                "rusher_player_id": None,
                "score_differential": 0,
                "qtr": 2,
                "game_seconds_remaining": 1800,
            }
        )
        for _ in range(5):
            plays.append(
                {
                    "season": 2024,
                    "week": week,
                    "posteam": "KC",
                    "play_type": "run",
                    "pass_attempt": 0,
                    "rush_attempt": 1,
                    "receiver_player_id": None,
                    "rusher_player_id": "RB1",
                    "score_differential": 0,
                    "qtr": 2,
                    "game_seconds_remaining": 1800,
                }
            )

    # KC trailing late: heavy pass, concentrated to WR1
    for week in range(5, 9):
        for _ in range(6):
            plays.append(
                {
                    "season": 2024,
                    "week": week,
                    "posteam": "KC",
                    "play_type": "pass",
                    "pass_attempt": 1,
                    "rush_attempt": 0,
                    "receiver_player_id": "WR1",
                    "rusher_player_id": None,
                    "score_differential": -10,
                    "qtr": 4,
                    "game_seconds_remaining": 240,
                }
            )
        plays.append(
            {
                "season": 2024,
                "week": week,
                "posteam": "KC",
                "play_type": "pass",
                "pass_attempt": 1,
                "rush_attempt": 0,
                "receiver_player_id": "WR2",
                "rusher_player_id": None,
                "score_differential": -10,
                "qtr": 4,
                "game_seconds_remaining": 240,
            }
        )
        plays.append(
            {
                "season": 2024,
                "week": week,
                "posteam": "KC",
                "play_type": "run",
                "pass_attempt": 0,
                "rush_attempt": 1,
                "receiver_player_id": None,
                "rusher_player_id": "RB1",
                "score_differential": -10,
                "qtr": 4,
                "game_seconds_remaining": 240,
            }
        )

    # KC leading late RB: RB2 absorbs more carries than neutral
    for week in range(5, 9):
        for _ in range(2):
            plays.append(
                {
                    "season": 2024,
                    "week": week,
                    "posteam": "KC",
                    "play_type": "run",
                    "pass_attempt": 0,
                    "rush_attempt": 1,
                    "receiver_player_id": None,
                    "rusher_player_id": "RB1",
                    "score_differential": 17,
                    "qtr": 4,
                    "game_seconds_remaining": 420,
                }
            )
        for _ in range(4):
            plays.append(
                {
                    "season": 2024,
                    "week": week,
                    "posteam": "KC",
                    "play_type": "run",
                    "pass_attempt": 0,
                    "rush_attempt": 1,
                    "receiver_player_id": None,
                    "rusher_player_id": "RB2",
                    "score_differential": 17,
                    "qtr": 4,
                    "game_seconds_remaining": 420,
                }
            )

    # Week 9 should be excluded when target week is 9
    for _ in range(10):
        plays.append(
            {
                "season": 2024,
                "week": 9,
                "posteam": "KC",
                "play_type": "pass",
                "pass_attempt": 1,
                "rush_attempt": 0,
                "receiver_player_id": "WR2",
                "rusher_player_id": None,
                "score_differential": -10,
                "qtr": 4,
                "game_seconds_remaining": 240,
            }
        )

    return pl.DataFrame(plays)


def test_compute_trailing_late_profile_moves_pass_rate_and_rank1():
    engine = GameScriptEngine(GameScriptConfig(enabled=True))
    profile = engine.compute("KC", make_game_script_pbp(), [2023, 2024], target_season=2024, week=9)
    assert profile.trailing_late_pass_rate_factor > 1.0
    assert profile.trailing_late_target_factors.rank1 > 1.0
    assert profile.trailing_late_target_factors.rank3_plus < 1.0


def test_compute_leading_late_rb_profile_shifts_to_rb2():
    engine = GameScriptEngine(GameScriptConfig(enabled=True))
    profile = engine.compute("KC", make_game_script_pbp(), [2023, 2024], target_season=2024, week=9)
    assert profile.leading_late_rb_factors.rb1 < 1.0
    assert profile.leading_late_rb_factors.rb2 > 1.0


def test_target_week_is_excluded():
    engine = GameScriptEngine(GameScriptConfig(enabled=True))
    profile = engine.compute("KC", make_game_script_pbp(), [2023, 2024], target_season=2024, week=9)
    assert profile.diagnostics.trailing_late_play_count > 0
    assert profile.trailing_late_target_factors.rank2 < 1.0


def test_missing_clock_column_keeps_pace_neutral():
    engine = GameScriptEngine(GameScriptConfig(enabled=True))
    pbp = make_game_script_pbp().drop("game_seconds_remaining")
    profile = engine.compute("KC", pbp, [2023, 2024], target_season=2024, week=9)
    assert profile.trailing_late_pace_factor == 1.0
```

Append to `tests/test_data/test_game_script_integration.py`:

```python
from unittest.mock import MagicMock

from fantasy_sim.data.game_script.models import GameScriptProfile, GameScriptConfig, TrailingLateConfig


def test_builder_attaches_profiles_to_team_distributions(expanded_pbp, sample_rosters):
    cfg = GameScriptConfig(enabled=True, trailing_late=TrailingLateConfig(enabled=True))
    builder = GameContextBuilder(game_script_config=cfg)
    builder._game_script_engine = MagicMock()
    builder._game_script_engine.compute.side_effect = [
        GameScriptProfile(team="KC", trailing_late_pass_rate_factor=1.10),
        GameScriptProfile(team="BUF", trailing_late_pass_rate_factor=1.05),
    ]

    home_dists, away_dists, _, _ = builder.build_game(
        "KC",
        "BUF",
        pbp=expanded_pbp,
        rosters=sample_rosters,
        training_seasons=[2024],
        target_season=2024,
        week=3,
    )

    assert home_dists.game_script_config is cfg
    assert home_dists.game_script_profile.team == "KC"
    assert away_dists.game_script_profile.team == "BUF"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
uv run pytest \
  tests/test_data/test_game_script_engine.py \
  tests/test_data/test_game_script_integration.py -v
```

Expected:

- `ModuleNotFoundError: No module named 'fantasy_sim.data.game_script.engine'`
- builder attachment assertions fail because `game_script_profile` stays `None`

- [ ] **Step 3: Implement the empirical learning engine**

Create `src/fantasy_sim/data/game_script/engine.py`:

```python
from __future__ import annotations

from dataclasses import replace

import polars as pl

from fantasy_sim.data.game_script.models import (
    GameScriptConfig,
    GameScriptDiagnostics,
    GameScriptProfile,
    RbRankFactors,
    TargetRankFactors,
)


class GameScriptEngine:
    def __init__(self, config: GameScriptConfig) -> None:
        self._config = config
        self._profile_cache: dict[tuple, GameScriptProfile] = {}

    def compute(
        self,
        team: str,
        pbp: pl.DataFrame,
        training_seasons: list[int],
        target_season: int | None = None,
        week: int | None = None,
        rosters: pl.DataFrame | None = None,
    ) -> GameScriptProfile:
        cache_key = (team, tuple(training_seasons), target_season, week)
        if cache_key in self._profile_cache:
            return self._profile_cache[cache_key]

        window = self._filter_window(pbp, training_seasons, target_season, week)
        offense = window.filter(pl.col("posteam") == team)
        if offense.is_empty():
            profile = GameScriptProfile(team=team)
            self._profile_cache[cache_key] = profile
            return profile

        trailing_team = offense.filter(self._trailing_late_expr(offense))
        leading_team = offense.filter(self._leading_late_rb_expr(offense))
        neutral_team = offense.filter(self._neutral_expr(offense))

        trailing_all = window.filter(self._trailing_late_expr(window))
        leading_all = window.filter(self._leading_late_rb_expr(window))
        neutral_all = window.filter(self._neutral_expr(window))

        pass_factor, pass_ratio, pass_n = self._team_pass_rate_factor(
            trailing_team,
            neutral_team,
            trailing_all,
            neutral_all,
        )
        pace_factor, pace_ratio, _ = self._team_pace_factor(
            trailing_team,
            neutral_team,
            trailing_all,
            neutral_all,
        )
        target_factors, target_ratios, target_n = self._target_rank_factors(
            trailing_team,
            neutral_team,
            trailing_all,
            neutral_all,
        )
        rb_factors, rb_ratios, rb_n = self._rb_rank_factors(
            leading_team,
            neutral_team,
            leading_all,
            neutral_all,
            rosters=rosters,
        )

        profile = GameScriptProfile(
            team=team,
            trailing_late_pass_rate_factor=pass_factor,
            trailing_late_pace_factor=pace_factor,
            trailing_late_target_factors=target_factors,
            leading_late_rb_factors=rb_factors,
            diagnostics=GameScriptDiagnostics(
                trailing_late_play_count=pass_n,
                trailing_late_pass_rate_ratio=pass_ratio,
                trailing_late_pace_ratio=pace_ratio,
                trailing_late_rank1_ratio=target_ratios["rank1"],
                trailing_late_rank2_ratio=target_ratios["rank2"],
                trailing_late_rank3_plus_ratio=target_ratios["rank3_plus"],
                leading_late_rb_play_count=rb_n,
                leading_late_rb1_ratio=rb_ratios["rb1"],
                leading_late_rb2_ratio=rb_ratios["rb2"],
                leading_late_rb3_plus_ratio=rb_ratios["rb3_plus"],
            ),
        )
        self._profile_cache[cache_key] = profile
        return profile

    def _filter_window(
        self,
        pbp: pl.DataFrame,
        training_seasons: list[int],
        target_season: int | None,
        week: int | None,
    ) -> pl.DataFrame:
        allowed = set(training_seasons)
        if target_season is not None:
            allowed.add(target_season)
        window = pbp.filter(pl.col("season").is_in(sorted(allowed)))
        if target_season is not None and week is not None and "week" in window.columns:
            window = window.filter(
                (pl.col("season") < target_season)
                | ((pl.col("season") == target_season) & (pl.col("week") < week))
            )
        return window

    def _late_clock_expr(self, df: pl.DataFrame, seconds: int) -> pl.Expr:
        if "quarter_seconds_remaining" in df.columns:
            return pl.col("quarter_seconds_remaining") <= seconds
        if "game_seconds_remaining" in df.columns:
            return pl.col("game_seconds_remaining") <= seconds
        return pl.lit(False)

    def _trailing_late_expr(self, df: pl.DataFrame) -> pl.Expr:
        cfg = self._config.trailing_late
        q4 = pl.col("qtr") == 4
        big_deficit = pl.col("score_differential") <= -cfg.deficit_threshold
        final_five = self._late_clock_expr(df, cfg.final_five_minutes) & (
            pl.col("score_differential") <= -cfg.final_five_deficit_threshold
        )
        return q4 & (big_deficit | final_five)

    def _leading_late_rb_expr(self, df: pl.DataFrame) -> pl.Expr:
        cfg = self._config.leading_late_rb
        return (
            (pl.col("qtr") == 4)
            & self._late_clock_expr(df, cfg.late_minutes)
            & (pl.col("score_differential") >= cfg.lead_threshold)
        )

    def _neutral_expr(self, df: pl.DataFrame) -> pl.Expr:
        return (
            pl.col("play_type").is_in(["pass", "run"])
            & ~self._trailing_late_expr(df)
            & ~self._leading_late_rb_expr(df)
        )

    def _scrimmage_counts(self, df: pl.DataFrame) -> tuple[int, int]:
        pass_plays = df.filter(pl.col("pass_attempt") == 1).height
        run_plays = df.filter(pl.col("rush_attempt") == 1).height
        return pass_plays, run_plays

    def _team_pass_rate_factor(
        self,
        trailing_team: pl.DataFrame,
        neutral_team: pl.DataFrame,
        trailing_all: pl.DataFrame,
        neutral_all: pl.DataFrame,
    ) -> tuple[float, float, int]:
        team_pass, team_run = self._scrimmage_counts(trailing_team)
        neutral_pass, neutral_run = self._scrimmage_counts(neutral_team)
        league_pass, league_run = self._scrimmage_counts(trailing_all)
        league_neutral_pass, league_neutral_run = self._scrimmage_counts(neutral_all)
        if team_pass + team_run == 0 or neutral_pass + neutral_run == 0:
            return 1.0, 1.0, 0

        team_ratio = (team_pass / (team_pass + team_run)) / (
            neutral_pass / (neutral_pass + neutral_run)
        )
        league_ratio = (league_pass / max(1, league_pass + league_run)) / (
            league_neutral_pass / max(1, league_neutral_pass + league_neutral_run)
        )
        factor = self._bayesian_ratio(
            team_ratio,
            league_ratio,
            team_pass + team_run,
            self._config.trailing_late.pass_rate_prior_strength,
            self._config.trailing_late.pass_rate_clamp,
        )
        return factor, team_ratio, team_pass + team_run

    def _team_pace_factor(
        self,
        trailing_team: pl.DataFrame,
        neutral_team: pl.DataFrame,
        trailing_all: pl.DataFrame,
        neutral_all: pl.DataFrame,
    ) -> tuple[float, float, int]:
        if "game_seconds_remaining" not in trailing_team.columns and "quarter_seconds_remaining" not in trailing_team.columns:
            return 1.0, 1.0, 0

        team_ratio = self._pace_ratio(trailing_team, neutral_team)
        league_ratio = self._pace_ratio(trailing_all, neutral_all)
        if team_ratio is None or league_ratio is None:
            return 1.0, 1.0, 0
        factor = self._bayesian_ratio(
            team_ratio,
            league_ratio,
            trailing_team.height,
            self._config.trailing_late.pace_prior_strength,
            self._config.trailing_late.pace_factor_clamp,
        )
        return factor, team_ratio, trailing_team.height

    def _pace_ratio(self, late_df: pl.DataFrame, neutral_df: pl.DataFrame) -> float | None:
        if late_df.is_empty() or neutral_df.is_empty():
            return None
        column = "quarter_seconds_remaining" if "quarter_seconds_remaining" in late_df.columns else "game_seconds_remaining"
        late_clock = late_df.select(pl.col(column)).to_series().to_list()
        neutral_clock = neutral_df.select(pl.col(column)).to_series().to_list()
        if len(late_clock) < 2 or len(neutral_clock) < 2:
            return None
        late_deltas = [abs(a - b) for a, b in zip(late_clock[:-1], late_clock[1:]) if abs(a - b) > 0]
        neutral_deltas = [abs(a - b) for a, b in zip(neutral_clock[:-1], neutral_clock[1:]) if abs(a - b) > 0]
        if not late_deltas or not neutral_deltas:
            return None
        late_seconds = sum(late_deltas) / len(late_deltas)
        neutral_seconds = sum(neutral_deltas) / len(neutral_deltas)
        return neutral_seconds / late_seconds

    def _target_rank_factors(
        self,
        trailing_team: pl.DataFrame,
        neutral_team: pl.DataFrame,
        trailing_all: pl.DataFrame,
        neutral_all: pl.DataFrame,
    ) -> tuple[TargetRankFactors, dict[str, float], int]:
        team_ratios, count = self._rank_bucket_ratios(
            trailing_team, neutral_team, "receiver_player_id", ("rank1", "rank2", "rank3_plus")
        )
        league_ratios, _ = self._rank_bucket_ratios(
            trailing_all, neutral_all, "receiver_player_id", ("rank1", "rank2", "rank3_plus")
        )
        if count == 0:
            return TargetRankFactors(), {"rank1": 1.0, "rank2": 1.0, "rank3_plus": 1.0}, 0
        cfg = self._config.trailing_late
        return (
            TargetRankFactors(
                rank1=self._bayesian_ratio(team_ratios["rank1"], league_ratios["rank1"], count, cfg.target_prior_strength, cfg.target_rank_factor_clamp),
                rank2=self._bayesian_ratio(team_ratios["rank2"], league_ratios["rank2"], count, cfg.target_prior_strength, cfg.target_rank_factor_clamp),
                rank3_plus=self._bayesian_ratio(team_ratios["rank3_plus"], league_ratios["rank3_plus"], count, cfg.target_prior_strength, cfg.target_rank_factor_clamp),
            ),
            team_ratios,
            count,
        )

    def _rb_rank_factors(
        self,
        leading_team: pl.DataFrame,
        neutral_team: pl.DataFrame,
        leading_all: pl.DataFrame,
        neutral_all: pl.DataFrame,
        rosters: pl.DataFrame | None = None,
    ) -> tuple[RbRankFactors, dict[str, float], int]:
        rb_ids_by_team = self._rb_ids_by_team(rosters)
        team_ratios, count = self._rank_bucket_ratios(
            leading_team,
            neutral_team,
            "rusher_player_id",
            ("rb1", "rb2", "rb3_plus"),
            position_filter="run",
            allowed_ids_by_team=rb_ids_by_team,
        )
        league_ratios, _ = self._rank_bucket_ratios(
            leading_all,
            neutral_all,
            "rusher_player_id",
            ("rb1", "rb2", "rb3_plus"),
            position_filter="run",
            allowed_ids_by_team=rb_ids_by_team,
        )
        if count == 0:
            return RbRankFactors(), {"rb1": 1.0, "rb2": 1.0, "rb3_plus": 1.0}, 0
        cfg = self._config.leading_late_rb
        return (
            RbRankFactors(
                rb1=self._bayesian_ratio(team_ratios["rb1"], league_ratios["rb1"], count, cfg.rb_carry_prior_strength, cfg.rb_rank_factor_clamp),
                rb2=self._bayesian_ratio(team_ratios["rb2"], league_ratios["rb2"], count, cfg.rb_carry_prior_strength, cfg.rb_rank_factor_clamp),
                rb3_plus=self._bayesian_ratio(team_ratios["rb3_plus"], league_ratios["rb3_plus"], count, cfg.rb_carry_prior_strength, cfg.rb_rank_factor_clamp),
            ),
            team_ratios,
            count,
        )

    def _rank_bucket_ratios(
        self,
        late_df: pl.DataFrame,
        neutral_df: pl.DataFrame,
        id_col: str,
        bucket_names: tuple[str, str, str],
        position_filter: str | None = None,
        allowed_ids_by_team: dict[str, set[str]] | None = None,
    ) -> tuple[dict[str, float], int]:
        late_events = self._event_bucket_shares(
            late_df,
            neutral_df,
            id_col,
            bucket_names,
            position_filter,
            allowed_ids_by_team,
        )
        if late_events[2] == 0:
            return {name: 1.0 for name in bucket_names}, 0
        late_shares, neutral_shares, count = late_events
        ratios = {}
        for name in bucket_names:
            neutral_share = neutral_shares[name]
            ratios[name] = (late_shares[name] / neutral_share) if neutral_share > 0 else 1.0
        return ratios, count

    def _event_bucket_shares(
        self,
        late_df: pl.DataFrame,
        neutral_df: pl.DataFrame,
        id_col: str,
        bucket_names: tuple[str, str, str],
        position_filter: str | None = None,
        allowed_ids_by_team: dict[str, set[str]] | None = None,
    ) -> tuple[dict[str, float], dict[str, float], int]:
        late = late_df
        neutral = neutral_df
        if position_filter == "run":
            late = late.filter(pl.col("rush_attempt") == 1)
            neutral = neutral.filter(pl.col("rush_attempt") == 1)
        else:
            late = late.filter((pl.col("pass_attempt") == 1) & pl.col(id_col).is_not_null())
            neutral = neutral.filter((pl.col("pass_attempt") == 1) & pl.col(id_col).is_not_null())
        if neutral.is_empty() or late.is_empty():
            return ({name: 0.0 for name in bucket_names}, {name: 0.0 for name in bucket_names}, 0)

        rank_maps: dict[str, dict[str, str]] = {}
        for team_df in neutral.partition_by("posteam", as_dict=False):
            team = team_df[0, "posteam"]
            grouped = (
                team_df.group_by(id_col)
                .agg(pl.len().alias("events"))
                .sort("events", descending=True)
            )
            team_map: dict[str, str] = {}
            for index, row in enumerate(grouped.iter_rows(named=True)):
                pid = row[id_col]
                if index == 0:
                    team_map[pid] = bucket_names[0]
                elif index == 1:
                    team_map[pid] = bucket_names[1]
                else:
                    team_map[pid] = bucket_names[2]
            rank_maps[team] = team_map

        late_counts = {name: 0 for name in bucket_names}
        neutral_counts = {name: 0 for name in bucket_names}
        for row in neutral.select(["posteam", id_col]).iter_rows(named=True):
            if allowed_ids_by_team is not None:
                allowed = allowed_ids_by_team.get(row["posteam"])
                if allowed is not None and row[id_col] not in allowed:
                    continue
            bucket = rank_maps.get(row["posteam"], {}).get(row[id_col], bucket_names[2])
            neutral_counts[bucket] += 1
        for row in late.select(["posteam", id_col]).iter_rows(named=True):
            if allowed_ids_by_team is not None:
                allowed = allowed_ids_by_team.get(row["posteam"])
                if allowed is not None and row[id_col] not in allowed:
                    continue
            bucket = rank_maps.get(row["posteam"], {}).get(row[id_col], bucket_names[2])
            late_counts[bucket] += 1

        late_total = sum(late_counts.values())
        neutral_total = sum(neutral_counts.values())
        late_shares = {name: late_counts[name] / late_total for name in bucket_names}
        neutral_shares = {name: neutral_counts[name] / neutral_total for name in bucket_names}
        return late_shares, neutral_shares, late_total

    def _rb_ids_by_team(self, rosters: pl.DataFrame | None) -> dict[str, set[str]] | None:
        if rosters is None or "team" not in rosters.columns or "position" not in rosters.columns:
            return None
        rb_rows = rosters.filter(pl.col("position") == "RB").select(["team", "player_id"]).unique()
        if rb_rows.is_empty():
            return None

        result: dict[str, set[str]] = {}
        for team_df in rb_rows.partition_by("team", as_dict=False):
            team = team_df[0, "team"]
            result[team] = set(team_df["player_id"].to_list())
        return result

    def _bayesian_ratio(
        self,
        observed: float,
        prior: float,
        n_obs: int,
        prior_strength: float,
        clamp: tuple[float, float],
    ) -> float:
        blended = (n_obs * observed + prior_strength * prior) / (n_obs + prior_strength)
        return max(clamp[0], min(clamp[1], blended))
```

- [ ] **Step 4: Instantiate the engine in `GameContextBuilder` and attach profiles to each team**

In `src/fantasy_sim/data/game_context.py`, instantiate the engine when enabled:

```python
        self._game_script_engine = None
        self._game_script_config = game_script_config or GameScriptConfig(enabled=False)
        if self._game_script_config.enabled:
            from fantasy_sim.data.game_script.engine import GameScriptEngine
            self._game_script_engine = GameScriptEngine(self._game_script_config)
            logger.info("Game script engine enabled")
```

In `build_game()`, attach profiles before returning:

```python
        if self._game_script_engine is not None and target_season and week:
            profile_pbp = pbp
            if profile_pbp is None:
                profile_pbp = self.loader.load_pbp(_seasons_with_target(training_seasons, target_season))

            home_dists.game_script_config = self._game_script_config
            away_dists.game_script_config = self._game_script_config
            profile_rosters = rosters
            if profile_rosters is None:
                roster_season = target_season or max(training_seasons)
                profile_rosters = self.loader.load_rosters([roster_season])

            home_dists.game_script_profile = self._game_script_engine.compute(
                home_team,
                profile_pbp,
                training_seasons,
                target_season=target_season,
                week=week,
                rosters=profile_rosters,
            )
            away_dists.game_script_profile = self._game_script_engine.compute(
                away_team,
                profile_pbp,
                training_seasons,
                target_season=target_season,
                week=week,
                rosters=profile_rosters,
            )
```

- [ ] **Step 5: Run the tests to verify they pass**

Run:

```bash
uv run pytest \
  tests/test_data/test_game_script_engine.py \
  tests/test_data/test_game_script_integration.py \
  tests/test_data/test_game_context.py -v
```

Expected:

- all tests PASS
- target-week leakage test remains green
- `GameContextBuilder.build_game()` returns `TeamDistributions` with attached `game_script_profile`

- [ ] **Step 6: Run a focused regression pass**

Run:

```bash
uv run pytest \
  tests/test_validation/test_config.py \
  tests/test_validation/test_parallel.py -v
```

Expected:

- all tests PASS
- validation builder plumbing still works in sequential and threaded paths

- [ ] **Step 7: Commit**

```bash
git add \
  src/fantasy_sim/data/game_script/engine.py \
  src/fantasy_sim/data/game_context.py \
  tests/test_data/test_game_script_engine.py \
  tests/test_data/test_game_script_integration.py \
  tests/test_data/test_game_context.py
git commit -F - <<'EOF'
Learn historical game-script profiles and attach them in build_game

Compute team-specific late-game pass, pace, target, and RB carry
factors from historical PBP, then attach the learned profiles to
TeamDistributions so the simulation loop can consume them per play.

Constraint: Target-week and future plays must never leak into the learned profile
Rejected: Reuse _pbp_stats_cache for profile learning | it lacks the state-conditioned play windows this feature needs
Confidence: medium
Scope-risk: broad
Directive: Keep the profile cache inside GameScriptEngine; do not expand the player-model cache key for this feature
Tested: uv run pytest tests/test_data/test_game_script_engine.py tests/test_data/test_game_script_integration.py tests/test_data/test_game_context.py tests/test_validation/test_config.py tests/test_validation/test_parallel.py -v
Not-tested: full validation harness
EOF
```

---

### Task 6: Add Validation Summary Output for Learned Game-Script Profiles

**Files:**
- Create: `src/fantasy_sim/validation/game_script.py`
- Modify: `scripts/validate.py:1-320`
- Create: `tests/test_validation/test_game_script_summary.py`

- [ ] **Step 1: Write failing tests for validation summary formatting**

Create `tests/test_validation/test_game_script_summary.py`:

```python
from fantasy_sim.data.game_script.models import (
    GameScriptDiagnostics,
    GameScriptProfile,
    RbRankFactors,
    TargetRankFactors,
)
from fantasy_sim.validation.game_script import format_game_script_summary


def test_summary_includes_team_and_factor_columns():
    profiles = {
        "KC": GameScriptProfile(
            team="KC",
            trailing_late_pass_rate_factor=1.12,
            trailing_late_pace_factor=1.05,
            trailing_late_target_factors=TargetRankFactors(rank1=1.20, rank2=0.95, rank3_plus=0.82),
            leading_late_rb_factors=RbRankFactors(rb1=0.87, rb2=1.15, rb3_plus=1.02),
            diagnostics=GameScriptDiagnostics(
                trailing_late_play_count=42,
                trailing_late_pass_rate_ratio=1.18,
                trailing_late_pace_ratio=1.07,
                trailing_late_rank1_ratio=1.30,
                trailing_late_rank2_ratio=0.92,
                trailing_late_rank3_plus_ratio=0.75,
                leading_late_rb_play_count=21,
                leading_late_rb1_ratio=0.80,
                leading_late_rb2_ratio=1.26,
                leading_late_rb3_plus_ratio=1.04,
            ),
        )
    }
    report = format_game_script_summary(profiles)
    assert "KC" in report
    assert "TrailPass" in report
    assert "LeadN" in report
    assert "1.12/1.18" in report
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
uv run pytest tests/test_validation/test_game_script_summary.py -v
```

Expected:

- `ModuleNotFoundError: No module named 'fantasy_sim.validation.game_script'`

- [ ] **Step 3: Add the summary formatter and call it from `scripts/validate.py`**

Create `src/fantasy_sim/validation/game_script.py`:

```python
from __future__ import annotations

from rich.console import Console
from rich.table import Table

from fantasy_sim.data.game_script.models import GameScriptProfile


def collect_game_script_profiles(specs) -> dict[str, GameScriptProfile]:
    profiles: dict[str, GameScriptProfile] = {}
    for spec in specs:
        for dists in (spec.home_dists, spec.away_dists):
            profile = getattr(dists, "game_script_profile", None)
            if profile is not None:
                profiles[profile.team] = profile
    return profiles


def format_game_script_summary(profiles: dict[str, GameScriptProfile]) -> str:
    console = Console(width=140, force_terminal=True)
    with console.capture() as capture:
        table = Table(title="Game Script Summary")
        table.add_column("Team")
        table.add_column("TrailPass")
        table.add_column("TrailPace")
        table.add_column("Rank1")
        table.add_column("Rank2")
        table.add_column("Rank3+")
        table.add_column("TrailN", justify="right")
        table.add_column("RB1")
        table.add_column("RB2")
        table.add_column("RB3+")
        table.add_column("LeadN", justify="right")

        for team, profile in sorted(profiles.items()):
            diag = profile.diagnostics
            table.add_row(
                team,
                f"{profile.trailing_late_pass_rate_factor:.2f}/{diag.trailing_late_pass_rate_ratio:.2f}",
                f"{profile.trailing_late_pace_factor:.2f}/{diag.trailing_late_pace_ratio:.2f}",
                f"{profile.trailing_late_target_factors.rank1:.2f}/{diag.trailing_late_rank1_ratio:.2f}",
                f"{profile.trailing_late_target_factors.rank2:.2f}/{diag.trailing_late_rank2_ratio:.2f}",
                f"{profile.trailing_late_target_factors.rank3_plus:.2f}/{diag.trailing_late_rank3_plus_ratio:.2f}",
                str(diag.trailing_late_play_count),
                f"{profile.leading_late_rb_factors.rb1:.2f}/{diag.leading_late_rb1_ratio:.2f}",
                f"{profile.leading_late_rb_factors.rb2:.2f}/{diag.leading_late_rb2_ratio:.2f}",
                f"{profile.leading_late_rb_factors.rb3_plus:.2f}/{diag.leading_late_rb3_plus_ratio:.2f}",
                str(diag.leading_late_rb_play_count),
            )
        console.print(table)
    return capture.get()
```

In `scripts/validate.py`, add the imports:

```python
from fantasy_sim.validation.game_script import (
    collect_game_script_profiles,
    format_game_script_summary,
)
```

After Arm B specs are available and before `run_season()` returns, add:

```python
        if arm_b_configs.get("game_script_config") is not None:
            profiles = collect_game_script_profiles(specs_b)
            if profiles:
                print(format_game_script_summary(profiles), flush=True)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```bash
uv run pytest tests/test_validation/test_game_script_summary.py -v
```

Expected:

- the summary formatter test PASSes
- the formatted table includes factor/observed-ratio pairs

- [ ] **Step 5: Run a focused regression pass**

Run:

```bash
uv run pytest \
  tests/test_validation/test_config.py \
  tests/test_validation/test_report.py -v
```

Expected:

- all tests PASS
- existing backtest report formatting remains unchanged

- [ ] **Step 6: Commit**

```bash
git add \
  src/fantasy_sim/validation/game_script.py \
  scripts/validate.py \
  tests/test_validation/test_game_script_summary.py
git commit -F - <<'EOF'
Add validation summaries for learned game-script profiles

Print a compact per-team summary of learned game-script factors and
their observed historical ratios so A/B runs can be checked for both
accuracy and late-game realism before the feature is enabled by default.

Constraint: Validation output must stay additive and not break the existing ledger flow
Rejected: Hide profile diagnostics inside debug logging only | too hard to compare during sweeps
Confidence: high
Scope-risk: narrow
Directive: Keep validation formatting in src/fantasy_sim/validation/game_script.py, not scripts/validate.py
Tested: uv run pytest tests/test_validation/test_game_script_summary.py tests/test_validation/test_config.py tests/test_validation/test_report.py -v
Not-tested: full script/validate end-to-end run
EOF
```

---

### Task 7: Run the Full Regression and A/B Validation Sweep

**Files:**
- Modify: none
- Test: `tests/`
- Validate: `scripts/validate.py`

- [ ] **Step 1: Run the full unit/integration test suite**

Run:

```bash
uv run pytest tests/ -v
```

Expected:

- all tests PASS
- no regressions in existing engine, validation, or CLI coverage

- [ ] **Step 2: Run a phase-1 A/B validation**

Run:

```bash
uv run python scripts/validate.py \
  --sims 50 \
  --set game_script.enabled=true \
  --set game_script.trailing_late.enabled=true \
  --label "game-script-trailing"
```

Expected:

- validation completes successfully
- summary output prints a `Game Script Summary` table
- overall `rank_corr` / `weekly_mae` do not materially regress

- [ ] **Step 3: Run a phase-2 A/B validation**

Run:

```bash
uv run python scripts/validate.py \
  --sims 50 \
  --set game_script.enabled=true \
  --set game_script.trailing_late.enabled=true \
  --set game_script.leading_late_rb.enabled=true \
  --label "game-script-rb"
```

Expected:

- validation completes successfully
- late-lead RB factors appear in the summary table
- phase 2 can be judged independently from phase 1

- [ ] **Step 4: Commit the final verification update**

```bash
git add .
git commit -F - <<'EOF'
Finish verification for the game-script late-game behavior feature

Run the full regression suite and the two staged validation passes so
the new late-game overlays have evidence for correctness, isolation,
and expected A/B behavior before any default toggle is considered.

Constraint: Phase 1 and phase 2 must remain independently measurable
Rejected: Enable the defaults immediately after implementation | validation must decide that separately
Confidence: medium
Scope-risk: narrow
Directive: Do not flip config/defaults.yaml to enabled without reviewing the validation ledger
Tested: uv run pytest tests/ -v; uv run python scripts/validate.py --sims 50 --set game_script.enabled=true --set game_script.trailing_late.enabled=true --label game-script-trailing; uv run python scripts/validate.py --sims 50 --set game_script.enabled=true --set game_script.trailing_late.enabled=true --set game_script.leading_late_rb.enabled=true --label game-script-rb
Not-tested: season-level sweep across alternative prior strengths
EOF
```

---

## Self-Review Checklist

### Spec Coverage

- `Phase 1 trailing-late pass rate` → Task 2 and Task 5
- `Phase 1 trailing-late pace` → Task 2 and Task 5
- `Phase 1 trailing-late target concentration` → Task 3 and Task 5
- `Phase 2 late-lead RB redistribution only` → Task 4 and Task 5
- `Config toggles for both phases` → Task 1
- `Attach profiles in build_game without mutating neutral roster` → Task 5
- `Validation summary alongside A/B harness` → Task 6 and Task 7

### Placeholder Scan

- No `TBD`, `TODO`, `implement later`, or `similar to task N` placeholders remain.
- Every code-changing step includes concrete code.
- Every run step includes an exact command and an expected result.

### Type Consistency

- Config names are consistently `GameScriptConfig`, `TrailingLateConfig`, `LeadingLateRbConfig`.
- Learned profile names are consistently `GameScriptProfile`, `TargetRankFactors`, `RbRankFactors`.
- Runtime overlay name is consistently `RuntimeGameScript`.
- Public signatures are consistent across tasks:
  - `select_play_type(..., script=None)`
  - `select_receiver(..., script=None)`
  - `select_rusher(..., script=None)`
  - `resolve_play(..., script=None)`

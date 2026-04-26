# Coding Conventions

**Analysis Date:** 2026-04-26

## Naming Patterns

**Files:**
- Module files use snake_case: `game_context.py`, `play_resolver.py`, `player_builder.py`
- Packages group related functionality: `data/pff/`, `data/weather/`, `engine/`, `scoring/`
- Test files mirror source structure with `test_` prefix: `tests/test_data/test_player_builder.py`

**Functions:**
- snake_case for all function names: `simulate_game()`, `build_player_models()`, `resolve_play()`
- Private/internal functions prefixed with single underscore: `_red_zone_td_gate()`, `_scale_clock_runoff()`, `_aggregate_pbp_stats()`
- Engine methods follow `compute()` or `apply()` patterns for consistency with engine pattern

**Variables:**
- snake_case for variables: `carry_share`, `target_share`, `rng`, `yard_line`, `score_differential`
- Numpy arrays: `_dist` suffix for distribution arrays: `receiving_yards_dist`, `rushing_yards_dist`, `scramble_yards_dist`
- Boolean flags: descriptive names with `is_` or `has_` prefix: `is_red_zone`, `has_scramble_data`, `is_home`

**Types & Classes:**
- PascalCase for all classes: `PlayerModel`, `PlayerUsage`, `PlayerOutcomes`, `TeamRoster`, `GameState`, `GameResult`
- Exception classes also PascalCase: `ConfigError`, `AmbiguousMatchError`
- Dataclass fields use snake_case with type hints (Python 3.12+ union syntax): `player_id: str`, `carry_share: float`, `receiving_yards_dist: np.ndarray | None`

## Code Style

**Formatting:**
- No explicit formatter enforced; code is readable and consistent
- 4-space indentation (standard Python)
- Line length is practical (under 120 characters typical)

**Linting:**
- No explicit linter in pyproject.toml (ESLint/Pylint not configured)
- Type hints on all function signatures are mandatory
- Union types use Python 3.12+ syntax: `X | None` (not `Optional[X]`)

**Type Hints:**
Example from `src/fantasy_sim/models/player.py`:
```python
def select_receiver(
    self, rng: np.random.Generator, is_red_zone: bool = False
) -> PlayerModel:
    """Randomly select a pass target, weighted by target share."""
```

Example from `src/fantasy_sim/engine/play_resolver.py`:
```python
def _red_zone_td_gate(
    yard_line: int, 
    play_type: str, 
    rng: np.random.Generator, 
    td_factor: float = 1.0
) -> bool:
    """Check if a would-be TD actually scores, based on field position."""
```

## Import Organization

**Order:**
1. Future annotations (for Python 3.12+ compatibility): `from __future__ import annotations`
2. Standard library: `import logging`, `from pathlib import Path`, `from typing import TYPE_CHECKING`
3. Third-party packages: `import numpy as np`, `import polars as pl`, `import yaml`
4. Local imports: `from fantasy_sim.models.player import PlayerModel`, `from fantasy_sim.engine.types import GameState`

**Circular Import Prevention:**
- Use `TYPE_CHECKING` guard for type hints only:
```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from fantasy_sim.models.player import TeamRoster
```
- Functions receive protocol types or concrete types at runtime, avoiding circular dependencies

**Path Aliases:**
- No path aliases configured; absolute imports from `fantasy_sim.` root package
- All tests use absolute imports: `from fantasy_sim.data.player_builder import build_player_models`

## Error Handling

**Patterns:**
- Custom exceptions inherit from Python built-ins: `class ConfigError(Exception):`
- Exceptions include descriptive messages: `raise ConfigError(f"Config file not found: {path}")`
- Validation errors on circular inheritance: `raise ConfigError(f"Circular _inherit detected: '{format_name}' already in chain")`
- Safe fallback returns instead of exceptions where appropriate:
  - `ValueError` for missing required data: `raise ValueError(f"No QB found on roster for {self.team}")`
  - Division by zero prevented with condition checks: `if weights.sum() == 0: weights = np.ones(len(eligible))`
- Option handling: functions accept `| None` types and check explicitly before use

## Logging

**Framework:** Python's built-in `logging` module

**Patterns:**
- Logger created per module: `logger = logging.getLogger(__name__)` at module level
- Used in data loading and context building: `logger.debug()`, `logger.warning()`, `logger.info()`
- No aggressive logging in hot paths (simulation, scoring)

## Comments

**When to Comment:**
- Comments explain WHY, not WHAT: "Field-position clamping bias fixed with boost" not "Add 1 yard"
- Domain-specific constants documented inline:
```python
# Red zone TD gate probabilities — per-play probability that a would-be TD
# actually scores. Calibrated so that drive-level TD rates match NFL averages
# (~55% of RZ drives end in TD) given realistic RZ drive progression.
PASS_TD_GATE = {
    (1, 3): 0.55,
    (4, 5): 0.50,
    ...
}
```
- Regression notes in tests: "Regression: when former players had carries in training data but aren't on the current roster..."

**JSDoc/TSDoc:**
- Google-style docstrings on all public functions and classes:
```python
def resolve_play(
    state: GameState,
    off_dists: TeamDistributions,
    def_dists: TeamDistributions,
    runtime_script: RuntimeGameScript | None = None,
    rng: np.random.Generator | None = None,
) -> PlayResult:
    """Resolve a single play and return player stats.
    
    Args:
        state: Current game state (down, distance, field position).
        off_dists: Offensive team distributions.
        def_dists: Defensive team distributions.
        rng: Random number generator (seeded for reproducibility).
        
    Returns:
        PlayResult with yards_gained, touchdown, turnover, and player stats.
    """
```
- Docstrings include Args, Returns, Raises sections

## Function Design

**Size:** 
- Functions are typically 20-50 lines (short, focused)
- Complex logic (e.g., `resolve_play()`) can reach 150+ lines with clear internal structure
- Engine pattern: class with `__init__(config, loader)` + `compute() -> context/result object`

**Parameters:**
- RNG always passed explicitly: `rng: np.random.Generator` (never global state)
- Config objects passed as constructor parameters: `GameContextBuilder(pff_config, weather_config, vegas_config, ...)`
- Protocol types for optional dependencies: `runtime_script: RuntimeGameScript | None = None`

**Return Values:**
- Dataclass instances for structured data: `PlayerModel`, `GameResult`, `PlayResult`
- Tuples for unrelated outputs: `tuple[list[PlayerModel], np.ndarray]` from `rusher_candidates_and_weights()`
- Dicts for lookups: `dict[GameStateBucket, dict[str, float]]` for distributions
- `| None` for optional results, explicitly checked before use

## Module Design

**Exports:**
- `__init__.py` files are minimal; import what users need
- Public API is explicit: `from fantasy_sim.data.player_builder import build_player_models`
- Internal functions (leading underscore) not exported

**Barrel Files:**
- Used in test modules for multiple imports from same package: `from fantasy_sim.data.player_builder import (build_player_models, build_team_roster, ...)`
- Source packages avoid barrel imports; import specific functions only

## Domain Patterns

**Key Constants:**
- Module-level constants in UPPER_SNAKE_CASE: `CLOCK_RUN = 35`, `CATCH_YARDS_BOOST = 1`, `MIN_QB_CARRY_SHARE = 0.10`
- Documented with comments explaining domain meaning:
```python
# Home-field advantage: 50% chance of +1 yard per play
HOME_FIELD_YARDS_BONUS = 0.5
```

**Factors & Multipliers:**
- Factors are multiplicative, centered on 1.0, clamped to configurable range
- Example: `td_factor: float = 1.0` with clamping: `rng.random() < min(1.0, prob * td_factor)`
- Used consistently across all engine layers (PFF, weather, Vegas)

**Bayesian Blending:**
- Standard formula used throughout: `adjusted = (n * observed + prior_strength * prior) / (n + prior_strength)`
- Applied in PFF tier engine, kicker model, DST baseline
- Shrinkage toward league average when sample size is low

**Dataclass Usage:**
- Frozen dataclasses used as dict keys: `@dataclass(frozen=True)` on `GameStateBucket`
- Mutable dataclasses for player models: `@dataclass` on `PlayerModel` (deepcopy for roster)
- Field defaults in constructor: `games_played: int = 17`, `weeks_missed: list[int] = field(default_factory=list)`

## Configuration Patterns

**YAML Inheritance:**
- Config files at `config/defaults.yaml`, `config/season.2025.yaml`, custom configs
- `_inherit` directive in YAML enables preset chains: PPR → half_ppr → standard
- Resolution logic in `config/loader.py`: `resolve_scoring()` with cycle detection

**Config Classes:**
- Domain configs are dataclasses: `PffConfig`, `WeatherConfig`, `VegasConfig`, `AvailabilityConfig`
- Loaded via `DataLoader` and `GameContextBuilder` constructor
- Boolean flags enable/disable features: `pff.tier_engine.enabled`, `weather.enabled`, `vegas.props.enabled`

**CLI Integration:**
- Click CLI in `cli.py`: commands `demo`, `week`, `season`, `game`, `player`, `backtest`
- Flag mapping: `--pff/--no-pff`, `--weather/--no-weather`, `--scoring ppr`
- Override syntax: `--override "name.field=value"` for dotted paths in config

---

*Convention analysis: 2026-04-26*

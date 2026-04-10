# Goal-Line Concentration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an internal, config-gated `goal_line_concentration` feature that splits red-zone opportunity selection into `1-5` and `6-20` bands for both receiving and rushing, with fallback to existing red-zone and base shares.

**Architecture:** Keep the feature isolated to usage data, runtime selection, and config plumbing. Compute the new banded shares unconditionally in player-model building so cache behavior stays simple, then gate only the runtime selector behavior with a single boolean config that is stamped onto `TeamDistributions` and threaded through play resolution.

**Tech Stack:** Python 3.12+, polars, numpy, pytest

---

## File Map

| File | Action | Purpose |
| --- | --- | --- |
| `src/fantasy_sim/data/goal_line_concentration.py` | Create | Minimal config dataclass + loader for the top-level feature flag |
| `src/fantasy_sim/models/player.py` | Modify | Add internal `outer_rz_*` and `goal_line_*` usage fields |
| `src/fantasy_sim/data/player_builder.py` | Modify | Count `1-5` and `6-20` opportunities, assemble shares, normalize new fields |
| `src/fantasy_sim/engine/types.py` | Modify | Carry the runtime `goal_line_concentration_enabled` flag on `TeamDistributions` |
| `src/fantasy_sim/engine/player_selector.py` | Modify | Choose band-specific target/carry weights with explicit fallback order |
| `src/fantasy_sim/engine/play_resolver.py` | Modify | Thread feature flag into `select_receiver()` / `select_rusher()` |
| `src/fantasy_sim/engine/game_sim.py` | Modify | Pass team-level runtime flag from `TeamDistributions` into play resolution |
| `src/fantasy_sim/data/game_context.py` | Modify | Accept feature config and stamp runtime flag onto built distributions |
| `src/fantasy_sim/cli.py` | Modify | Load goal-line concentration config into `GameContextBuilder` |
| `src/fantasy_sim/validation/config.py` | Modify | Include feature config in Arm A/B config resolution |
| `src/fantasy_sim/validation/parallel.py` | Modify | Thread feature config into builder creation, especially dual-arm runs |
| `config/defaults.yaml` | Modify | Add `goal_line_concentration.enabled: false` |
| `tests/test_data/test_goal_line_concentration_config.py` | Create | Unit tests for config loader |
| `tests/test_validation/test_goal_line_concentration_config_resolution.py` | Create | Validation config-resolution tests |
| `tests/test_data/test_player_builder.py` | Modify | Tests for banded share computation and normalization |
| `tests/test_engine/test_player_selector.py` | Modify | Tests for runtime weight selection and fallback behavior |
| `tests/test_data/test_game_context.py` | Modify | Verify builder stamps runtime flag on distributions |
| `tests/test_validation/test_parallel.py` | Modify | Verify dual-arm builder threading for the new config |
| `tests/test_validation/test_validate_script.py` | Modify | Verify `scripts/validate.py` threads the new config into dual-arm builds |

---

### Task 1: Add Goal-Line Concentration Config Surface

**Files:**
- Create: `src/fantasy_sim/data/goal_line_concentration.py`
- Modify: `config/defaults.yaml`
- Modify: `src/fantasy_sim/validation/config.py`
- Test: `tests/test_data/test_goal_line_concentration_config.py`
- Test: `tests/test_validation/test_goal_line_concentration_config_resolution.py`

- [ ] **Step 1: Write failing config-loader tests**

Create `tests/test_data/test_goal_line_concentration_config.py` with:

```python
from fantasy_sim.data.goal_line_concentration import (
    GoalLineConcentrationConfig,
    load_goal_line_concentration_config,
)


class TestGoalLineConcentrationConfig:
    def test_default_config_is_disabled(self):
        config = GoalLineConcentrationConfig()
        assert config.enabled is False

    def test_load_enabled_from_dict(self):
        raw = {"goal_line_concentration": {"enabled": True}}
        config = load_goal_line_concentration_config(raw)
        assert config.enabled is True

    def test_missing_section_returns_disabled_config(self):
        config = load_goal_line_concentration_config({})
        assert config.enabled is False
```

- [ ] **Step 2: Write failing validation-resolution tests**

Create `tests/test_validation/test_goal_line_concentration_config_resolution.py` with:

```python
from fantasy_sim.validation.config import (
    build_bare_engine_configs,
    build_engine_configs,
)


class TestGoalLineConcentrationConfigResolution:
    def test_build_engine_configs_includes_goal_line_concentration(self):
        config = {
            "pff": {"enabled": False},
            "weather": {"enabled": False},
            "vegas": {"enabled": False},
            "usage": {"enabled": False},
            "game_script": {"enabled": False},
            "td_tendency": {"enabled": False},
            "goal_line_concentration": {"enabled": True},
        }

        result = build_engine_configs(config)

        assert "goal_line_concentration_config" in result
        assert result["goal_line_concentration_config"] is not None
        assert result["goal_line_concentration_config"].enabled is True

    def test_disabled_goal_line_concentration_returns_none(self):
        config = {
            "pff": {"enabled": False},
            "weather": {"enabled": False},
            "vegas": {"enabled": False},
            "usage": {"enabled": False},
            "game_script": {"enabled": False},
            "td_tendency": {"enabled": False},
            "goal_line_concentration": {"enabled": False},
        }

        result = build_engine_configs(config)

        assert result["goal_line_concentration_config"] is None

    def test_build_bare_engine_configs_includes_goal_line_concentration_none(self):
        result = build_bare_engine_configs()
        assert "goal_line_concentration_config" in result
        assert result["goal_line_concentration_config"] is None
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_data/test_goal_line_concentration_config.py tests/test_validation/test_goal_line_concentration_config_resolution.py -v
```

Expected:
- import failure for `fantasy_sim.data.goal_line_concentration`, or
- `KeyError` / missing-key failures because validation config does not expose `goal_line_concentration_config`

- [ ] **Step 4: Add the new config module**

Create `src/fantasy_sim/data/goal_line_concentration.py`:

```python
"""Configuration loader for goal-line concentration."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GoalLineConcentrationConfig:
    """Configuration for goal-line concentration selection behavior."""

    enabled: bool = False


def load_goal_line_concentration_config(defaults: dict) -> GoalLineConcentrationConfig:
    """Extract GoalLineConcentrationConfig from the full defaults config dict."""
    raw = defaults.get("goal_line_concentration")
    if not raw:
        return GoalLineConcentrationConfig(enabled=False)
    return GoalLineConcentrationConfig(enabled=raw.get("enabled", False))
```

- [ ] **Step 5: Add the new defaults key**

In `config/defaults.yaml`, add:

```yaml
goal_line_concentration:
  enabled: false
```

Place it near `game_script:` / `td_tendency:` so all accuracy-feature toggles stay grouped.

- [ ] **Step 6: Expose the config in validation resolution**

In `src/fantasy_sim/validation/config.py`, add the import:

```python
from fantasy_sim.data.goal_line_concentration import load_goal_line_concentration_config
```

Update `build_engine_configs()`:

```python
    goal_line_concentration = load_goal_line_concentration_config(config)
    return {
        "pff_config": pff if pff.enabled else None,
        "weather_config": weather if weather.enabled else None,
        "vegas_config": vegas if vegas.enabled else None,
        "props_config": props if props.enabled else None,
        "usage_config": usage if usage.enabled else None,
        "game_script_config": game_script if game_script.enabled else None,
        "td_tendency_config": td_tendency if td_tendency.enabled else None,
        "goal_line_concentration_config": (
            goal_line_concentration if goal_line_concentration.enabled else None
        ),
    }
```

Update `build_bare_engine_configs()`:

```python
    return {
        "pff_config": None,
        "weather_config": None,
        "vegas_config": None,
        "props_config": None,
        "usage_config": None,
        "game_script_config": None,
        "td_tendency_config": None,
        "goal_line_concentration_config": None,
    }
```

- [ ] **Step 7: Run tests to verify they pass**

Run:

```bash
uv run pytest tests/test_data/test_goal_line_concentration_config.py tests/test_validation/test_goal_line_concentration_config_resolution.py -v
```

Expected: all tests PASS

- [ ] **Step 8: Commit**

```bash
git add src/fantasy_sim/data/goal_line_concentration.py config/defaults.yaml src/fantasy_sim/validation/config.py tests/test_data/test_goal_line_concentration_config.py tests/test_validation/test_goal_line_concentration_config_resolution.py
git commit -m "Expose goal-line concentration as a disabled config feature" -m "Add the minimal config loader and validation resolution entry for goal-line concentration so the feature can be enabled explicitly without changing runtime behavior yet.

Constraint: Feature must stay off by default until isolated A/B validation
Rejected: Read defaults directly inside runtime selectors | hides configuration boundaries and complicates tests
Confidence: high
Scope-risk: narrow
Directive: Keep this config surface as a single boolean until the split itself proves useful
Tested: uv run pytest tests/test_data/test_goal_line_concentration_config.py tests/test_validation/test_goal_line_concentration_config_resolution.py -v
Not-tested: Runtime propagation through GameContextBuilder and simulation"
```

---

### Task 2: Add Banded Usage Fields, Counts, And Normalization

**Files:**
- Modify: `src/fantasy_sim/models/player.py`
- Modify: `src/fantasy_sim/data/player_builder.py`
- Test: `tests/test_data/test_player_builder.py`

- [ ] **Step 1: Write failing share-computation tests**

Add to `tests/test_data/test_player_builder.py`:

```python
class TestGoalLineConcentrationShares:
    def test_goal_line_and_outer_red_zone_target_shares_computed(self, sample_rosters):
        pbp = pl.DataFrame([
            {"play_type": "pass", "season": 2024, "posteam": "KC", "game_id": "g1", "receiver_player_id": "RE11", "complete_pass": 1, "yards_gained": 3, "yardline_100": 4},
            {"play_type": "pass", "season": 2024, "posteam": "KC", "game_id": "g1", "receiver_player_id": "TK87", "complete_pass": 1, "yards_gained": 2, "yardline_100": 4},
            {"play_type": "pass", "season": 2024, "posteam": "KC", "game_id": "g1", "receiver_player_id": "RE11", "complete_pass": 1, "yards_gained": 9, "yardline_100": 8},
            {"play_type": "pass", "season": 2024, "posteam": "KC", "game_id": "g1", "receiver_player_id": "TK87", "complete_pass": 1, "yards_gained": 7, "yardline_100": 12},
        ])

        models = build_player_models(pbp, sample_rosters, training_seasons=[2024])

        assert models["RE11"].usage.goal_line_target_share == pytest.approx(0.5)
        assert models["TK87"].usage.goal_line_target_share == pytest.approx(0.5)
        assert models["RE11"].usage.outer_rz_target_share == pytest.approx(0.5)
        assert models["TK87"].usage.outer_rz_target_share == pytest.approx(0.5)

    def test_goal_line_and_outer_red_zone_carry_shares_computed(self, sample_rosters):
        pbp = pl.DataFrame([
            {"play_type": "run", "season": 2024, "posteam": "KC", "game_id": "g2", "rusher_player_id": "IP01", "yards_gained": 2, "yardline_100": 3},
            {"play_type": "run", "season": 2024, "posteam": "KC", "game_id": "g2", "rusher_player_id": "CH02", "yards_gained": 1, "yardline_100": 4},
            {"play_type": "run", "season": 2024, "posteam": "KC", "game_id": "g2", "rusher_player_id": "IP01", "yards_gained": 5, "yardline_100": 7},
            {"play_type": "run", "season": 2024, "posteam": "KC", "game_id": "g2", "rusher_player_id": "IP01", "yards_gained": 4, "yardline_100": 10},
            {"play_type": "run", "season": 2024, "posteam": "KC", "game_id": "g2", "rusher_player_id": "CH02", "yards_gained": 3, "yardline_100": 18},
        ])

        models = build_player_models(pbp, sample_rosters, training_seasons=[2024])

        assert models["IP01"].usage.goal_line_carry_share == pytest.approx(0.5)
        assert models["CH02"].usage.goal_line_carry_share == pytest.approx(0.5)
        assert models["IP01"].usage.outer_rz_carry_share == pytest.approx(2 / 3)
        assert models["CH02"].usage.outer_rz_carry_share == pytest.approx(1 / 3)

    def test_roster_normalizes_goal_line_and_outer_rz_shares(self):
        models = {
            "RB1": PlayerModel(
                "RB1", "Back One", "RB", "T1",
                PlayerUsage(goal_line_carry_share=0.30, outer_rz_carry_share=0.20),
                PlayerOutcomes(),
            ),
            "RB2": PlayerModel(
                "RB2", "Back Two", "RB", "T1",
                PlayerUsage(goal_line_carry_share=0.10, outer_rz_carry_share=0.30),
                PlayerOutcomes(),
            ),
            "WR1": PlayerModel(
                "WR1", "Wideout One", "WR", "T1",
                PlayerUsage(goal_line_target_share=0.15, outer_rz_target_share=0.10),
                PlayerOutcomes(),
            ),
            "TE1": PlayerModel(
                "TE1", "Tight End", "TE", "T1",
                PlayerUsage(goal_line_target_share=0.05, outer_rz_target_share=0.30),
                PlayerOutcomes(),
            ),
        }

        roster = build_team_roster("T1", models)

        goal_line_carry_total = sum(
            p.usage.goal_line_carry_share for p in roster.players if p.usage.goal_line_carry_share > 0
        )
        outer_rz_carry_total = sum(
            p.usage.outer_rz_carry_share for p in roster.players if p.usage.outer_rz_carry_share > 0
        )
        goal_line_target_total = sum(
            p.usage.goal_line_target_share for p in roster.players if p.usage.goal_line_target_share > 0
        )
        outer_rz_target_total = sum(
            p.usage.outer_rz_target_share for p in roster.players if p.usage.outer_rz_target_share > 0
        )

        assert goal_line_carry_total == pytest.approx(1.0)
        assert outer_rz_carry_total == pytest.approx(1.0)
        assert goal_line_target_total == pytest.approx(1.0)
        assert outer_rz_target_total == pytest.approx(1.0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_data/test_player_builder.py -k "GoalLineConcentrationShares" -v
```

Expected:
- `TypeError` because `PlayerUsage` does not accept the new fields, or
- assertion failures because the new counts/shares are not computed

- [ ] **Step 3: Add the new internal usage fields**

In `src/fantasy_sim/models/player.py`, extend `PlayerUsage`:

```python
@dataclass
class PlayerUsage:
    """How often a player is involved in plays."""

    carry_share: float = 0.0
    red_zone_carry_share: float = 0.0
    outer_rz_carry_share: float = 0.0
    goal_line_carry_share: float = 0.0
    target_share: float = 0.0
    red_zone_target_share: float = 0.0
    outer_rz_target_share: float = 0.0
    goal_line_target_share: float = 0.0
    air_yards_share: float = 0.0
    snap_share: float = 0.0
    scramble_rate: float = 0.0
```

- [ ] **Step 4: Extend `_aggregate_pbp_stats()` with non-overlapping band counts**

In `src/fantasy_sim/data/player_builder.py`, update team totals:

```python
    team_outer_rz_pass_attempts: dict[str, int] = {}
    team_goal_line_pass_attempts: dict[str, int] = {}
    team_outer_rz_rush_attempts: dict[str, int] = {}
    team_goal_line_rush_attempts: dict[str, int] = {}
```

Add the team counting logic:

```python
        team_outer_rz_pass_attempts[team] = pass_plays_team.filter(
            (pl.col("yardline_100") >= 6) & (pl.col("yardline_100") <= 20)
        ).shape[0]
        team_goal_line_pass_attempts[team] = pass_plays_team.filter(
            pl.col("yardline_100") <= 5
        ).shape[0]
        team_outer_rz_rush_attempts[team] = rush_plays_team.filter(
            (pl.col("yardline_100") >= 6) & (pl.col("yardline_100") <= 20)
        ).shape[0]
        team_goal_line_rush_attempts[team] = rush_plays_team.filter(
            pl.col("yardline_100") <= 5
        ).shape[0]
```

Extend receiving stats dictionaries:

```python
                "outer_rz_targets": 0,
                "goal_line_targets": 0,
```

and increment them:

```python
        if row["yardline_100"] <= 5:
            receiving_stats[rid]["goal_line_targets"] += 1
        elif row["yardline_100"] <= 20:
            receiving_stats[rid]["outer_rz_targets"] += 1
```

Extend rushing stats dictionaries:

```python
                "outer_rz_carries": 0,
                "goal_line_carries": 0,
```

and increment them:

```python
        if row["yardline_100"] <= 5:
            rushing_stats[rid]["goal_line_carries"] += 1
        elif row["yardline_100"] <= 20:
            rushing_stats[rid]["outer_rz_carries"] += 1
```

Return the new team-total maps:

```python
        "team_outer_rz_pass_attempts": team_outer_rz_pass_attempts,
        "team_goal_line_pass_attempts": team_goal_line_pass_attempts,
        "team_outer_rz_rush_attempts": team_outer_rz_rush_attempts,
        "team_goal_line_rush_attempts": team_goal_line_rush_attempts,
```

- [ ] **Step 5: Assemble and normalize the new shares**

In `_assemble_models()`, load the new maps:

```python
    team_outer_rz_pass_attempts = aggregated_stats["team_outer_rz_pass_attempts"]
    team_goal_line_pass_attempts = aggregated_stats["team_goal_line_pass_attempts"]
    team_outer_rz_rush_attempts = aggregated_stats["team_outer_rz_rush_attempts"]
    team_goal_line_rush_attempts = aggregated_stats["team_goal_line_rush_attempts"]
```

Compute the new receiving shares:

```python
            team_outer_rz_pa = team_outer_rz_pass_attempts.get(hist_team, 0)
            if team_outer_rz_pa > 0:
                usage.outer_rz_target_share = rs["outer_rz_targets"] / team_outer_rz_pa

            team_goal_line_pa = team_goal_line_pass_attempts.get(hist_team, 0)
            if team_goal_line_pa > 0:
                usage.goal_line_target_share = rs["goal_line_targets"] / team_goal_line_pa
```

Compute the new rushing shares:

```python
            team_outer_rz_ra = team_outer_rz_rush_attempts.get(hist_team, 0)
            if team_outer_rz_ra > 0:
                usage.outer_rz_carry_share = rs["outer_rz_carries"] / team_outer_rz_ra

            team_goal_line_ra = team_goal_line_rush_attempts.get(hist_team, 0)
            if team_goal_line_ra > 0:
                usage.goal_line_carry_share = rs["goal_line_carries"] / team_goal_line_ra
```

Normalize the new share families in `_normalize_roster_shares()`:

```python
    eligible_outer_rz_rushers = [
        p for p in roster.players
        if p.usage.outer_rz_carry_share > 0
        and (p.position != "QB" or p.usage.carry_share >= MIN_QB_CARRY_SHARE)
    ]
    _scale_shares(eligible_outer_rz_rushers, "outer_rz_carry_share")

    eligible_goal_line_rushers = [
        p for p in roster.players
        if p.usage.goal_line_carry_share > 0
        and (p.position != "QB" or p.usage.carry_share >= MIN_QB_CARRY_SHARE)
    ]
    _scale_shares(eligible_goal_line_rushers, "goal_line_carry_share")

    eligible_outer_rz_receivers = [
        p for p in roster.players if p.usage.outer_rz_target_share > 0
    ]
    _scale_shares(eligible_outer_rz_receivers, "outer_rz_target_share")

    eligible_goal_line_receivers = [
        p for p in roster.players if p.usage.goal_line_target_share > 0
    ]
    _scale_shares(eligible_goal_line_receivers, "goal_line_target_share")
```

Do this unconditionally. The feature flag should gate runtime use, not whether the data is computed.

- [ ] **Step 6: Run tests to verify they pass**

Run:

```bash
uv run pytest tests/test_data/test_player_builder.py -k "GoalLineConcentrationShares or RedZoneMetrics" -v
```

Expected: all selected tests PASS

- [ ] **Step 7: Commit**

```bash
git add src/fantasy_sim/models/player.py src/fantasy_sim/data/player_builder.py tests/test_data/test_player_builder.py
git commit -m "Teach player models to track goal-line and outer red-zone shares" -m "Split player usage aggregation into non-overlapping 1-5 and 6-20 bands for both targets and carries, and normalize those shares on the current roster while keeping them inert until runtime wiring is complete.

Constraint: Preserve current cache behavior by computing banded shares unconditionally
Rejected: Compute the new fields only when the feature flag is enabled | would complicate cache keys without reducing much work
Confidence: high
Scope-risk: moderate
Directive: Keep the band definitions non-overlapping: <=5 for goal line and 6-20 for outer red zone
Tested: uv run pytest tests/test_data/test_player_builder.py -k \"GoalLineConcentrationShares or RedZoneMetrics\" -v
Not-tested: Runtime selection and builder/config plumbing"
```

---

### Task 3: Apply Banded Selector Weights With Explicit Fallbacks

**Files:**
- Modify: `src/fantasy_sim/engine/player_selector.py`
- Modify: `src/fantasy_sim/engine/play_resolver.py`
- Modify: `src/fantasy_sim/engine/game_sim.py`
- Test: `tests/test_engine/test_player_selector.py`

- [ ] **Step 1: Write failing selector-behavior tests**

Add to `tests/test_engine/test_player_selector.py`:

```python
def make_goal_line_roster() -> TeamRoster:
    qb = PlayerModel("QB1", "QB", "QB", "KC",
                     PlayerUsage(snap_share=1.0, scramble_rate=0.08),
                     PlayerOutcomes(scramble_yards_dist=np.array([5, 8])))
    wr1 = PlayerModel("WR1", "WR1", "WR", "KC",
                      PlayerUsage(
                          target_share=0.24,
                          red_zone_target_share=0.20,
                          outer_rz_target_share=0.15,
                          goal_line_target_share=0.85,
                      ),
                      PlayerOutcomes(catch_rate=0.65, receiving_yards_dist=np.array([8, 12, 20])))
    te1 = PlayerModel("TE1", "TE1", "TE", "KC",
                      PlayerUsage(
                          target_share=0.20,
                          red_zone_target_share=0.80,
                          outer_rz_target_share=0.85,
                          goal_line_target_share=0.15,
                      ),
                      PlayerOutcomes(catch_rate=0.70, receiving_yards_dist=np.array([5, 10])))
    rb1 = PlayerModel("RB1", "RB1", "RB", "KC",
                      PlayerUsage(
                          carry_share=0.60,
                          red_zone_carry_share=0.30,
                          outer_rz_carry_share=0.20,
                          goal_line_carry_share=0.85,
                      ),
                      PlayerOutcomes(rushing_yards_dist=np.array([3, 5, 7])))
    rb2 = PlayerModel("RB2", "RB2", "RB", "KC",
                      PlayerUsage(
                          carry_share=0.40,
                          red_zone_carry_share=0.70,
                          outer_rz_carry_share=0.80,
                          goal_line_carry_share=0.15,
                      ),
                      PlayerOutcomes(rushing_yards_dist=np.array([2, 4, 6])))
    return TeamRoster(team="KC", players=[qb, wr1, te1, rb1, rb2])


class TestGoalLineConcentrationSelection:
    def test_goal_line_receiver_weights_override_red_zone_when_enabled(self):
        roster = make_goal_line_roster()
        state = make_state(yard_line=4)
        rng = np.random.default_rng(42)

        ids = [
            select_receiver(roster, state, rng, goal_line_concentration_enabled=True).player_id
            for _ in range(250)
        ]

        assert ids.count("WR1") > ids.count("TE1")

    def test_outer_rz_receiver_weights_used_when_enabled(self):
        roster = make_goal_line_roster()
        state = make_state(yard_line=10)
        rng = np.random.default_rng(42)

        ids = [
            select_receiver(roster, state, rng, goal_line_concentration_enabled=True).player_id
            for _ in range(250)
        ]

        assert ids.count("TE1") > ids.count("WR1")

    def test_disabled_feature_uses_existing_red_zone_share(self):
        roster = make_goal_line_roster()
        state = make_state(yard_line=4)
        rng = np.random.default_rng(42)

        ids = [select_receiver(roster, state, rng).player_id for _ in range(250)]

        assert ids.count("TE1") > ids.count("WR1")

    def test_missing_goal_line_mass_falls_back_to_red_zone(self):
        roster = make_goal_line_roster()
        for player in roster.players:
            player.usage.goal_line_target_share = 0.0

        state = make_state(yard_line=4)
        rng = np.random.default_rng(42)
        ids = [
            select_receiver(roster, state, rng, goal_line_concentration_enabled=True).player_id
            for _ in range(250)
        ]

        assert ids.count("TE1") > ids.count("WR1")

    def test_goal_line_rusher_weights_override_red_zone_when_enabled(self):
        roster = make_goal_line_roster()
        state = make_state(yard_line=3)
        rng = np.random.default_rng(42)

        ids = [
            select_rusher(roster, state, rng, goal_line_concentration_enabled=True).player_id
            for _ in range(250)
        ]

        assert ids.count("RB1") > ids.count("RB2")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_engine/test_player_selector.py -k "GoalLineConcentrationSelection" -v
```

Expected:
- `TypeError` because `select_receiver()` / `select_rusher()` do not accept `goal_line_concentration_enabled`, or
- assertion failures because selection still uses only `red_zone_*_share`

- [ ] **Step 3: Add weight helpers and new selector parameter**

In `src/fantasy_sim/engine/player_selector.py`, add explicit helper functions:

```python
def _receiver_usage_weight(
    player: PlayerModel,
    yard_line: int,
    goal_line_concentration_enabled: bool,
) -> float:
    if yard_line > 20:
        return player.usage.target_share
    if goal_line_concentration_enabled:
        if yard_line <= 5 and player.usage.goal_line_target_share > 0:
            return player.usage.goal_line_target_share
        if 6 <= yard_line <= 20 and player.usage.outer_rz_target_share > 0:
            return player.usage.outer_rz_target_share
    if player.usage.red_zone_target_share > 0:
        return player.usage.red_zone_target_share
    return player.usage.target_share


def _rusher_usage_weight(
    player: PlayerModel,
    yard_line: int,
    goal_line_concentration_enabled: bool,
) -> float:
    if yard_line > 20:
        return player.usage.carry_share
    if goal_line_concentration_enabled:
        if yard_line <= 5 and player.usage.goal_line_carry_share > 0:
            return player.usage.goal_line_carry_share
        if 6 <= yard_line <= 20 and player.usage.outer_rz_carry_share > 0:
            return player.usage.outer_rz_carry_share
    if player.usage.red_zone_carry_share > 0:
        return player.usage.red_zone_carry_share
    return player.usage.carry_share
```

Update selector signatures:

```python
def select_receiver(
    roster: TeamRoster,
    state: GameState,
    rng: np.random.Generator,
    goal_line_concentration_enabled: bool = False,
    script: RuntimeGameScript | None = None,
) -> PlayerModel:
```

```python
    base_weights = np.array(
        [
            _receiver_usage_weight(
                player,
                state.yard_line,
                goal_line_concentration_enabled,
            )
            for player in eligible
        ],
        dtype=float,
    )
```

Update `select_rusher()` similarly:

```python
def select_rusher(
    roster: TeamRoster,
    state: GameState,
    rng: np.random.Generator,
    is_scramble: bool = False,
    goal_line_concentration_enabled: bool = False,
    script: RuntimeGameScript | None = None,
) -> PlayerModel:
```

```python
    eligible, _ = filtered.rusher_candidates_and_weights(is_red_zone=state.yard_line <= 20)
    base_weights = np.array(
        [
            _rusher_usage_weight(
                player,
                state.yard_line,
                goal_line_concentration_enabled,
            )
            for player in eligible
        ],
        dtype=float,
    )
```

- [ ] **Step 4: Thread the new flag through play resolution**

In `src/fantasy_sim/engine/play_resolver.py`, update the signatures:

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
    goal_line_concentration_enabled: bool = False,
    script: RuntimeGameScript | None = None,
) -> PlayResult:
```

Pass the flag into `_resolve_pass()` / `_resolve_run()` and then into selector calls:

```python
        receiver = select_receiver(
            roster,
            state,
            rng,
            goal_line_concentration_enabled=goal_line_concentration_enabled,
            script=script,
        )
```

```python
        rusher = select_rusher(
            roster,
            state,
            rng,
            goal_line_concentration_enabled=goal_line_concentration_enabled,
            script=script,
        )
```

In `src/fantasy_sim/engine/game_sim.py`, pass the runtime team flag into `resolve_play()`:

```python
        result = resolve_play(
            state,
            play_type,
            off_dists.play_outcomes,
            off_dists.turnover_rates,
            rng,
            roster=roster,
            is_home=is_home_team,
            pace_factor=effective_pace_factor(off_dists.pace_factor, script),
            goal_line_concentration_enabled=off_dists.goal_line_concentration_enabled,
            script=script,
        )
```

- [ ] **Step 5: Run selector and regression tests**

Run:

```bash
uv run pytest tests/test_engine/test_player_selector.py tests/test_engine/test_player_selector_game_script.py -v
```

Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/fantasy_sim/engine/player_selector.py src/fantasy_sim/engine/play_resolver.py src/fantasy_sim/engine/game_sim.py tests/test_engine/test_player_selector.py
git commit -m "Apply goal-line concentration weights during player selection" -m "Teach receiver and rusher selection to prefer 1-5 or 6-20 usage shares when the feature is enabled, while preserving the existing red-zone and base-share fallback chain.

Constraint: The feature must change opportunity allocation only, not TD gates or play-calling
Rejected: Reuse TeamRoster.select_receiver/select_rusher for this behavior | runtime selection already lives in engine/player_selector.py and must stay game-state aware
Confidence: high
Scope-risk: moderate
Directive: Keep the fallback order explicit: band-specific share, then red-zone share, then base share
Tested: uv run pytest tests/test_engine/test_player_selector.py tests/test_engine/test_player_selector_game_script.py -v
Not-tested: Builder, CLI, and validation plumbing"
```

---

### Task 4: Thread The Feature Flag Through GameContext, CLI, And Validation

**Files:**
- Modify: `src/fantasy_sim/engine/types.py`
- Modify: `src/fantasy_sim/data/game_context.py`
- Modify: `src/fantasy_sim/cli.py`
- Modify: `src/fantasy_sim/validation/parallel.py`
- Modify: `tests/test_data/test_game_context.py`
- Modify: `tests/test_validation/test_parallel.py`
- Modify: `tests/test_validation/test_validate_script.py`

- [ ] **Step 1: Write failing runtime-plumbing tests**

Add to `tests/test_data/test_game_context.py`:

```python
from fantasy_sim.data.goal_line_concentration import GoalLineConcentrationConfig

    def test_goal_line_concentration_flag_stamped_on_distributions(
        self, tmp_path, expanded_pbp, sample_rosters
    ):
        builder = GameContextBuilder(
            cache_dir=tmp_path / "cache",
            goal_line_concentration_config=GoalLineConcentrationConfig(enabled=True),
        )

        home_dists, away_dists, _, _ = builder.build_game(
            home_team="KC",
            away_team="BUF",
            pbp=expanded_pbp,
            rosters=sample_rosters,
            training_seasons=[2024],
        )

        assert home_dists.goal_line_concentration_enabled is True
        assert away_dists.goal_line_concentration_enabled is True
```

Add to `tests/test_validation/test_parallel.py`:

```python
    @patch("fantasy_sim.validation.parallel.GameContextBuilder")
    def test_dual_arm_only_threads_goal_line_config_to_on_builder(self, mock_builder_cls):
        from fantasy_sim.validation.parallel import _create_builders

        config = object()

        _create_builders(
            cache_dir=Path("/tmp"),
            pff_config=None,
            weather_config=None,
            vegas_config=None,
            props_config=None,
            usage_config=None,
            game_script_config=None,
            td_tendency_config=None,
            goal_line_concentration_config=config,
            dual_arm=True,
        )

        assert mock_builder_cls.call_count == 2
        assert "goal_line_concentration_config" not in mock_builder_cls.call_args_list[0].kwargs
        assert mock_builder_cls.call_args_list[1].kwargs["goal_line_concentration_config"] is config
```

Add to `tests/test_validation/test_validate_script.py`:

```python
def test_run_season_threads_goal_line_config_into_dual_arm_build():
    validate = _load_validate_module()

    with patch.object(validate, "simulate_games_parallel", return_value=[]), \
         patch.object(validate, "build_games_parallel", return_value=[]) as mock_build_games_parallel, \
         patch.object(validate, "load_actual_scores", return_value=[]), \
         patch.object(validate, "DataLoader") as mock_loader_cls:
        mock_loader = mock_loader_cls.return_value
        mock_loader.cache_dir = Path("/tmp/test-cache")
        mock_loader.load_schedules.return_value = pl.DataFrame([
            {
                "season": 2024,
                "week": 1,
                "game_id": "2024_01_KC_BUF",
                "home_team": "KC",
                "away_team": "BUF",
            }
        ])
        mock_loader.load_player_stats.return_value = pl.DataFrame(
            {"season": pl.Series([], dtype=pl.Int32)}
        )

        goal_line_config = object()
        arm_a_configs = {
            "pff_config": None,
            "weather_config": None,
            "vegas_config": None,
            "props_config": None,
            "usage_config": None,
            "game_script_config": None,
            "td_tendency_config": None,
            "goal_line_concentration_config": None,
        }
        arm_b_configs = {
            "pff_config": None,
            "weather_config": None,
            "vegas_config": None,
            "props_config": None,
            "usage_config": None,
            "game_script_config": None,
            "td_tendency_config": None,
            "goal_line_concentration_config": goal_line_config,
        }

        validate.run_season(
            test_season=2024,
            n_sims=10,
            scoring_config={},
            num_training_seasons=3,
            arm_a_configs=arm_a_configs,
            arm_b_configs=arm_b_configs,
            positions=["QB"],
            max_workers=1,
        )

    call_kwargs = mock_build_games_parallel.call_args.kwargs
    assert call_kwargs["dual_arm"] is True
    assert call_kwargs["goal_line_concentration_config"] is goal_line_config
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_data/test_game_context.py tests/test_validation/test_parallel.py tests/test_validation/test_validate_script.py -k "goal_line_concentration" -v
```

Expected:
- `TypeError` because `GameContextBuilder` does not accept `goal_line_concentration_config`, or
- missing-key / missing-kwarg failures in validation plumbing

- [ ] **Step 3: Add the runtime flag to `TeamDistributions`**

In `src/fantasy_sim/engine/types.py`, extend `TeamDistributions`:

```python
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
    goal_line_concentration_enabled: bool = False
```

- [ ] **Step 4: Wire the config through `GameContextBuilder` and CLI**

In `src/fantasy_sim/data/game_context.py`, add the import:

```python
from fantasy_sim.data.goal_line_concentration import GoalLineConcentrationConfig
```

Update `GameContextBuilder.__init__()`:

```python
    def __init__(
        self,
        cache_dir: Path = DEFAULT_CACHE_DIR,
        pff_config: PffConfig | None = None,
        weather_config: WeatherConfig | None = None,
        vegas_config: VegasConfig | None = None,
        props_config: PropsConfig | None = None,
        usage_config: UsageConfig | None = None,
        game_script_config: GameScriptConfig | None = None,
        td_tendency_config: TdTendencyConfig | None = None,
        goal_line_concentration_config: GoalLineConcentrationConfig | None = None,
    ):
```

Store the config:

```python
        self._goal_line_concentration_config = (
            goal_line_concentration_config or GoalLineConcentrationConfig(enabled=False)
        )
```

Wherever `TeamDistributions` are materialized in `GameContextBuilder`, stamp the runtime flag before returning them:

```python
        home_dists.goal_line_concentration_enabled = self._goal_line_concentration_config.enabled
        away_dists.goal_line_concentration_enabled = self._goal_line_concentration_config.enabled
```

If `build_team_distributions()` has its own return path separate from `build_game()`, stamp the same flag there as well so standalone distribution builds behave consistently.

In `src/fantasy_sim/cli.py`, add the import:

```python
from fantasy_sim.data.goal_line_concentration import load_goal_line_concentration_config
```

Update `_make_builder()`:

```python
    goal_line_concentration_config = load_goal_line_concentration_config(defaults)
```

and pass it through:

```python
        td_tendency_config=td_tendency_config,
        goal_line_concentration_config=goal_line_concentration_config,
```

- [ ] **Step 5: Wire the config through validation parallel builders**

In `src/fantasy_sim/validation/parallel.py`, add the new parameter to all build-worker and builder-creation signatures that currently accept `td_tendency_config`.

For example:

```python
def _init_build_worker_single(
    cache_dir: Path,
    pff_config: "PffConfig | None",
    weather_config: "WeatherConfig | None",
    vegas_config: "VegasConfig | None" = None,
    props_config: "PropsConfig | None" = None,
    usage_config: "UsageConfig | None" = None,
    game_script_config: "GameScriptConfig | None" = None,
    td_tendency_config: "TdTendencyConfig | None" = None,
    goal_line_concentration_config: "GoalLineConcentrationConfig | None" = None,
) -> None:
```

Pass it into the single builder:

```python
    builder = GameContextBuilder(
        cache_dir=cache_dir,
        pff_config=pff_config,
        weather_config=weather_config,
        vegas_config=vegas_config,
        props_config=props_config,
        usage_config=usage_config,
        game_script_config=game_script_config,
        td_tendency_config=td_tendency_config,
        goal_line_concentration_config=goal_line_concentration_config,
    )
```

In dual-arm creation, mirror the game-script pattern so the off builder stays clean:

```python
        "off": GameContextBuilder(
            cache_dir=cache_dir,
        ),
        "on": GameContextBuilder(
            cache_dir=cache_dir,
            pff_config=pff_config,
            weather_config=weather_config,
            vegas_config=vegas_config,
            props_config=props_config,
            usage_config=usage_config,
            game_script_config=game_script_config,
            td_tendency_config=td_tendency_config,
            goal_line_concentration_config=goal_line_concentration_config,
        ),
```

Also extend any `build_games_parallel()` / `_create_builders()` kwargs dictionaries so `goal_line_concentration_config` is accepted and forwarded.

- [ ] **Step 6: Run the plumbing tests**

Run:

```bash
uv run pytest tests/test_data/test_game_context.py tests/test_validation/test_parallel.py tests/test_validation/test_validate_script.py -k "goal_line_concentration" -v
```

Expected: all selected tests PASS

- [ ] **Step 7: Run the full targeted regression slice**

Run:

```bash
uv run pytest tests/test_data/test_goal_line_concentration_config.py tests/test_validation/test_goal_line_concentration_config_resolution.py tests/test_data/test_player_builder.py tests/test_engine/test_player_selector.py tests/test_data/test_game_context.py tests/test_validation/test_parallel.py tests/test_validation/test_validate_script.py -v
```

Expected: all tests PASS

- [ ] **Step 8: Commit**

```bash
git add src/fantasy_sim/engine/types.py src/fantasy_sim/data/game_context.py src/fantasy_sim/cli.py src/fantasy_sim/validation/parallel.py tests/test_data/test_game_context.py tests/test_validation/test_parallel.py tests/test_validation/test_validate_script.py
git commit -m "Thread goal-line concentration through game building and validation" -m "Carry the new feature flag from defaults and Arm B overrides into built team distributions so simulation and validation can activate goal-line concentration without changing the off arm.

Constraint: Dual-arm validation must keep Arm A behavior untouched
Rejected: Store the flag globally or read defaults inside simulation | would make A/B isolation brittle
Confidence: high
Scope-risk: moderate
Directive: In dual-arm validation, only the on builder should receive goal-line concentration config
Tested: uv run pytest tests/test_data/test_game_context.py tests/test_validation/test_parallel.py tests/test_validation/test_validate_script.py -k \"goal_line_concentration\" -v
Not-tested: Full-season A/B validation"
```

---

### Task 5: Final Verification And User-Run A/B Hand-Off

**Files:**
- No code changes

- [ ] **Step 1: Run the focused goal-line concentration test slice**

Run:

```bash
uv run pytest tests/test_data/test_goal_line_concentration_config.py tests/test_validation/test_goal_line_concentration_config_resolution.py tests/test_data/test_player_builder.py tests/test_engine/test_player_selector.py tests/test_data/test_game_context.py tests/test_validation/test_parallel.py tests/test_validation/test_validate_script.py -v
```

Expected: all targeted goal-line concentration tests PASS

- [ ] **Step 2: Run the full suite**

Run:

```bash
uv run pytest tests/ -v
```

Expected: full suite PASS

- [ ] **Step 3: Prepare the isolated validation experiment for the user**

Provide this command to the user instead of running it:

```bash
uv run python scripts/validate.py --sims 50 --set goal_line_concentration.enabled=true --label "goal-line-concentration"
```

- [ ] **Step 4: If the initial signal looks promising, prepare higher-sim confirmation commands for the user**

Provide these follow-up commands to the user instead of running them:

```bash
uv run python scripts/validate.py --sims 200 --set goal_line_concentration.enabled=true --label "goal-line-concentration-200"
uv run python scripts/validate.py --sims 400 --set goal_line_concentration.enabled=true --label "goal-line-concentration-400"
```

Expected:
- the user has the exact isolated commands needed to evaluate the feature
- metrics from those runs will determine whether the feature stays off or should be considered for a default change later

- [ ] **Step 5: Commit any final cleanup if code changed during verification**

If verification required code cleanup or test adjustments, commit them with a Lore-format message that records the verification evidence. If verification is clean and no files changed, skip this step.

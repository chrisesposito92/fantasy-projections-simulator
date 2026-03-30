# Phase 7B: Scoring + Config + CLI Features — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fill 11 feature gaps in scoring (position-specific bonuses, yardage thresholds), configuration (custom_scoring.yaml, auto-load season.yaml, use defaults.yaml values), CLI commands (game, player, --detail), and output (floor/ceiling/stddev distributions).

**Architecture:** Scoring engine gains position-aware reception keys and yardage bonus thresholds, both driven purely by config dict keys. Config loader gets a `load_custom_scoring()` function that reads a `custom_scoring.yaml` with `inherit` + `overrides` fields. CLI auto-detects `config/season.yaml` using a new `_resolve_config_chain()` helper that merges defaults.yaml -> season.yaml -> CLI flags. Two new CLI commands (`game`, `player`) use existing `GameContextBuilder` and `PlayerResolver`. A new `build_detailed_projections()` function bridges `SimulationSummary.player_summary()` distributions into the projection pipeline, and `format_*_detail_table()` functions in `output/tables.py` render floor/ceiling/stddev columns. The `--detail` flag propagates from CLI through projections to output.

**Tech Stack:** Python 3.14, click, rich, pyyaml, numpy, pytest

---

## File Structure

```
config/
├── defaults.yaml                 EXISTS (no changes)
├── season.example.yaml           EXISTS (no changes)
└── custom_scoring.example.yaml   NEW: Example custom scoring config

src/fantasy_sim/
├── scoring/
│   ├── engine.py                 MODIFY: Position-specific reception + yardage bonuses
│   └── projections.py            MODIFY: Add build_detailed_projections()
├── config/
│   └── loader.py                 MODIFY: Add load_custom_scoring()
├── output/
│   └── tables.py                 MODIFY: Add detail table formatters
└── cli.py                        MODIFY: game command, player command, --detail, --weeks validation,
                                           auto-load season.yaml, --scoring-config, use defaults.yaml

tests/
├── test_scoring/
│   ├── test_engine.py            MODIFY: Position bonus + yardage bonus tests
│   └── test_projections.py       MODIFY: Detailed projections tests
├── test_config/
│   └── test_loader.py            MODIFY: Custom scoring tests
├── test_output/
│   └── test_tables.py            MODIFY: Detail table tests
└── test_cli.py                   MODIFY: game, player, --detail, --weeks validation tests
```

## Dependencies from Phases 1-6

- `engine.types.PlayerBoxScore` — has `position: str`, `pass_yards`, `rush_yards`, `receiving_yards`, `receptions`, all int fields
- `engine.types.GameResult` — has `player_stats: dict[str, PlayerBoxScore]`, `home_score`, `away_score`, `home_box`, `away_box`
- `engine.monte_carlo.SimulationSummary` — `player_summary()` returns `{pid: {stat: {mean, std, floor, ceiling}}}`
- `engine.monte_carlo.run_simulations()` — returns `SimulationSummary`
- `scoring.engine.score_player(box, config)` — current generic reception scoring
- `scoring.projections.build_player_projections(games, scoring_config)` — returns mean-only projections
- `config.loader.load_defaults()`, `resolve_scoring(presets, format_name)`, `load_config(path)`
- `overrides.resolver.PlayerResolver(rosters).resolve(query)` — fuzzy name matching
- `data.game_context.GameContextBuilder.build_game(home, away, seasons)` — returns `(TeamDistributions, TeamDistributions, TeamRoster, TeamRoster)`
- `output.tables.format_qb_table()`, `format_rb_table()`, etc. — Rich table formatters
- CLI uses Click with `@click.group()` main and `@main.command()` subcommands

---

### Task 1: Scoring Improvements — Position-Specific Reception + Yardage Bonuses (Gaps 11, 12)

**Files:**
- Modify: `src/fantasy_sim/scoring/engine.py`
- Modify: `tests/test_scoring/test_engine.py`

- [ ] **Step 1: Write failing tests for position-specific reception bonus**

```python
# tests/test_scoring/test_engine.py — ADD to end of file

class TestPositionSpecificReception:
    """Gap 11: Position-specific reception bonus (e.g., reception_wr: 1.5)."""

    def test_wr_uses_position_specific_key(self):
        """When config has reception_wr, WR should use that instead of generic reception."""
        config = {
            "passing_yard": 0.04, "passing_td": 4, "interception": -2,
            "rushing_yard": 0.1, "rushing_td": 6,
            "reception": 1, "receiving_yard": 0.1, "receiving_td": 6,
            "fumble_lost": -2,
            "reception_wr": 1.5,
        }
        box = PlayerBoxScore("WR1", "WR Name", "WR", "KC",
                             receptions=5, receiving_yards=100, receiving_tds=1)
        points = score_player(box, config)
        # 5 * 1.5 (position-specific) + 100 * 0.1 + 1 * 6 = 7.5 + 10 + 6 = 23.5
        assert points == pytest.approx(23.5)

    def test_te_uses_position_specific_key(self):
        """TE premium scoring: reception_te: 1.5."""
        config = {
            "passing_yard": 0.04, "passing_td": 4, "interception": -2,
            "rushing_yard": 0.1, "rushing_td": 6,
            "reception": 1, "receiving_yard": 0.1, "receiving_td": 6,
            "fumble_lost": -2,
            "reception_te": 1.5,
        }
        box = PlayerBoxScore("TE1", "TE Name", "TE", "KC",
                             receptions=4, receiving_yards=60, receiving_tds=1)
        points = score_player(box, config)
        # 4 * 1.5 + 60 * 0.1 + 1 * 6 = 6 + 6 + 6 = 18
        assert points == pytest.approx(18.0)

    def test_rb_falls_back_to_generic_reception(self):
        """RB with no position-specific key should use generic reception."""
        config = {
            "rushing_yard": 0.1, "rushing_td": 6,
            "reception": 1, "receiving_yard": 0.1, "receiving_td": 6,
            "fumble_lost": -2,
            "reception_wr": 1.5, "reception_te": 1.5,
        }
        box = PlayerBoxScore("RB1", "RB Name", "RB", "KC",
                             rush_yards=50, receptions=3, receiving_yards=20)
        points = score_player(box, config)
        # 50 * 0.1 + 3 * 1 (generic) + 20 * 0.1 = 5 + 3 + 2 = 10
        assert points == pytest.approx(10.0)

    def test_no_position_key_uses_generic(self):
        """Without position-specific keys, all positions use generic reception."""
        config = {
            "reception": 1, "receiving_yard": 0.1, "receiving_td": 6,
            "fumble_lost": -2,
        }
        box = PlayerBoxScore("WR1", "WR Name", "WR", "KC",
                             receptions=5, receiving_yards=80, receiving_tds=0)
        points = score_player(box, config)
        # 5 * 1 + 80 * 0.1 = 5 + 8 = 13
        assert points == pytest.approx(13.0)

    def test_qb_uses_position_specific_reception(self):
        """QB receptions (rare) can have position-specific scoring too."""
        config = {
            "passing_yard": 0.04, "passing_td": 4, "interception": -2,
            "rushing_yard": 0.1, "rushing_td": 6,
            "reception": 1, "receiving_yard": 0.1, "receiving_td": 6,
            "fumble_lost": -2,
            "reception_qb": 0,
        }
        box = PlayerBoxScore("QB1", "QB Name", "QB", "KC",
                             pass_yards=200, pass_tds=1,
                             receptions=1, receiving_yards=5)
        points = score_player(box, config)
        # 200 * 0.04 + 1 * 4 + 1 * 0 (qb-specific) + 5 * 0.1 = 8 + 4 + 0 + 0.5 = 12.5
        assert points == pytest.approx(12.5)


class TestYardageBonuses:
    """Gap 12: Yardage bonus thresholds (e.g., rushing_bonus_100: 3)."""

    def test_rushing_bonus_100(self):
        """3 bonus points for 100+ rushing yards."""
        config = {
            "rushing_yard": 0.1, "rushing_td": 6,
            "reception": 1, "receiving_yard": 0.1, "receiving_td": 6,
            "fumble_lost": -2,
            "rushing_bonus_100": 3,
        }
        box = PlayerBoxScore("RB1", "RB Name", "RB", "KC",
                             rush_yards=120, rush_tds=1)
        points = score_player(box, config)
        # 120 * 0.1 + 1 * 6 + 3 (bonus) = 12 + 6 + 3 = 21
        assert points == pytest.approx(21.0)

    def test_rushing_no_bonus_under_100(self):
        """No bonus when under 100 rushing yards."""
        config = {
            "rushing_yard": 0.1, "rushing_td": 6,
            "fumble_lost": -2,
            "rushing_bonus_100": 3,
        }
        box = PlayerBoxScore("RB1", "RB Name", "RB", "KC",
                             rush_yards=99, rush_tds=1)
        points = score_player(box, config)
        # 99 * 0.1 + 1 * 6 = 9.9 + 6 = 15.9 (no bonus)
        assert points == pytest.approx(15.9)

    def test_receiving_bonus_100(self):
        """3 bonus points for 100+ receiving yards."""
        config = {
            "reception": 1, "receiving_yard": 0.1, "receiving_td": 6,
            "fumble_lost": -2,
            "receiving_bonus_100": 3,
        }
        box = PlayerBoxScore("WR1", "WR Name", "WR", "KC",
                             receptions=7, receiving_yards=105, receiving_tds=0)
        points = score_player(box, config)
        # 7 * 1 + 105 * 0.1 + 3 (bonus) = 7 + 10.5 + 3 = 20.5
        assert points == pytest.approx(20.5)

    def test_passing_bonus_300(self):
        """3 bonus points for 300+ passing yards."""
        config = {
            "passing_yard": 0.04, "passing_td": 4, "interception": -2,
            "fumble_lost": -2,
            "passing_bonus_300": 3,
        }
        box = PlayerBoxScore("QB1", "QB Name", "QB", "KC",
                             pass_yards=320, pass_tds=2, interceptions=0)
        points = score_player(box, config)
        # 320 * 0.04 + 2 * 4 + 3 (bonus) = 12.8 + 8 + 3 = 23.8
        assert points == pytest.approx(23.8)

    def test_passing_no_bonus_under_300(self):
        """No passing bonus under 300 yards."""
        config = {
            "passing_yard": 0.04, "passing_td": 4, "interception": -2,
            "fumble_lost": -2,
            "passing_bonus_300": 3,
        }
        box = PlayerBoxScore("QB1", "QB Name", "QB", "KC",
                             pass_yards=299, pass_tds=2, interceptions=0)
        points = score_player(box, config)
        # 299 * 0.04 + 2 * 4 = 11.96 + 8 = 19.96 (no bonus)
        assert points == pytest.approx(19.96)

    def test_rushing_bonus_200(self):
        """Additional bonus at 200+ rushing yards."""
        config = {
            "rushing_yard": 0.1, "rushing_td": 6,
            "fumble_lost": -2,
            "rushing_bonus_100": 3,
            "rushing_bonus_200": 5,
        }
        box = PlayerBoxScore("RB1", "RB Name", "RB", "KC",
                             rush_yards=210, rush_tds=2)
        points = score_player(box, config)
        # 210 * 0.1 + 2 * 6 + 3 (100+) + 5 (200+) = 21 + 12 + 3 + 5 = 41
        assert points == pytest.approx(41.0)

    def test_passing_bonus_400(self):
        """Stacking passing bonuses: 300+ and 400+."""
        config = {
            "passing_yard": 0.04, "passing_td": 4, "interception": -2,
            "fumble_lost": -2,
            "passing_bonus_300": 3,
            "passing_bonus_400": 5,
        }
        box = PlayerBoxScore("QB1", "QB Name", "QB", "KC",
                             pass_yards=420, pass_tds=3, interceptions=1)
        points = score_player(box, config)
        # 420 * 0.04 + 3 * 4 + 1 * (-2) + 3 (300+) + 5 (400+) = 16.8 + 12 - 2 + 3 + 5 = 34.8
        assert points == pytest.approx(34.8)

    def test_no_bonus_keys_no_effect(self):
        """Without bonus keys in config, no bonuses applied."""
        config = {
            "rushing_yard": 0.1, "rushing_td": 6,
            "fumble_lost": -2,
        }
        box = PlayerBoxScore("RB1", "RB Name", "RB", "KC",
                             rush_yards=150, rush_tds=1)
        points = score_player(box, config)
        # 150 * 0.1 + 1 * 6 = 15 + 6 = 21 (no bonus)
        assert points == pytest.approx(21.0)
```

- [ ] **Step 2: Implement position-specific reception and yardage bonuses**

```python
# src/fantasy_sim/scoring/engine.py — FULL REPLACEMENT
from fantasy_sim.engine.types import PlayerBoxScore, TeamBoxScore

# Yardage bonus definitions: (stat_attr, config_prefix, threshold) tuples
_YARDAGE_BONUSES = [
    ("rush_yards", "rushing_bonus_", [100, 200]),
    ("receiving_yards", "receiving_bonus_", [100, 200]),
    ("pass_yards", "passing_bonus_", [300, 400, 500]),
]


def score_player(box: PlayerBoxScore, config: dict) -> float:
    """Calculate fantasy points for an offensive player (QB/RB/WR/TE).

    Supports:
    - Position-specific reception keys: reception_wr, reception_te, etc.
      Falls back to generic 'reception' key if no position-specific key exists.
    - Yardage bonuses: rushing_bonus_100, receiving_bonus_100, passing_bonus_300, etc.
      Each threshold that is met adds the configured bonus points. Bonuses stack
      (e.g., 200+ rush yards triggers both rushing_bonus_100 and rushing_bonus_200).
    """
    points = 0.0
    points += box.pass_yards * config.get("passing_yard", 0)
    points += box.pass_tds * config.get("passing_td", 0)
    points += box.interceptions * config.get("interception", 0)
    points += box.rush_yards * config.get("rushing_yard", 0)
    points += box.rush_tds * config.get("rushing_td", 0)

    # Position-specific reception: check for reception_{position} first, fall back to reception
    pos_key = f"reception_{box.position.lower()}"
    reception_value = config.get(pos_key, config.get("reception", 0))
    points += box.receptions * reception_value

    points += box.receiving_yards * config.get("receiving_yard", 0)
    points += box.receiving_tds * config.get("receiving_td", 0)
    points += box.fumbles_lost * config.get("fumble_lost", 0)

    # Yardage bonuses: check each threshold, add bonus if met
    for stat_attr, config_prefix, thresholds in _YARDAGE_BONUSES:
        stat_value = getattr(box, stat_attr, 0)
        for threshold in thresholds:
            bonus_key = f"{config_prefix}{threshold}"
            if stat_value >= threshold and bonus_key in config:
                points += config[bonus_key]

    return points


def score_dst(box: TeamBoxScore, opponent_score: int, config: dict) -> float:
    """Calculate fantasy points for a team defense/special teams."""
    points = 0.0
    points += box.sacks_made * config.get("dst_sack", 0)
    points += box.interceptions_caught * config.get("dst_interception", 0)
    points += box.fumbles_recovered * config.get("dst_fumble_recovery", 0)
    points += box.safeties * config.get("dst_safety", 0)

    if opponent_score == 0:
        points += config.get("dst_points_allowed_0", 0)
    elif opponent_score <= 6:
        points += config.get("dst_points_allowed_1_6", 0)
    elif opponent_score <= 13:
        points += config.get("dst_points_allowed_7_13", 0)
    elif opponent_score <= 20:
        points += config.get("dst_points_allowed_14_20", 0)
    elif opponent_score <= 27:
        points += config.get("dst_points_allowed_21_27", 0)
    elif opponent_score <= 34:
        points += config.get("dst_points_allowed_28_34", 0)
    else:
        points += config.get("dst_points_allowed_35_plus", 0)

    return points


def score_kicker(box: TeamBoxScore, config: dict) -> float:
    """Calculate fantasy points for a kicker from team-level kicking stats."""
    points = 0.0
    points += box.fg_made_0_39 * config.get("fg_0_39", 0)
    points += box.fg_made_40_49 * config.get("fg_40_49", 0)
    points += box.fg_made_50_plus * config.get("fg_50_plus", 0)
    points += box.xp_made * config.get("xp_made", 0)
    points += box.fg_missed * config.get("fg_miss", 0)
    return points
```

- [ ] **Step 3: Run tests and verify**

```bash
uv run pytest tests/test_scoring/test_engine.py -v
```

All existing tests must still pass. New `TestPositionSpecificReception` (5 tests) and `TestYardageBonuses` (8 tests) must pass.

- [ ] **Step 4: Commit**

```bash
git add src/fantasy_sim/scoring/engine.py tests/test_scoring/test_engine.py
git commit -m "feat(scoring): add position-specific reception bonuses and yardage thresholds

Position-specific keys (reception_wr, reception_te, etc.) override
the generic reception key per position. Yardage bonus keys
(rushing_bonus_100, passing_bonus_300, etc.) add bonus points when
stat thresholds are met. Bonuses stack at multiple tiers."
```

---

### Task 2: Config Integration — Auto-Load season.yaml, Custom Scoring, Use Defaults (Gaps 14, 15, 16)

**Files:**
- Modify: `src/fantasy_sim/config/loader.py`
- Modify: `src/fantasy_sim/cli.py`
- Create: `config/custom_scoring.example.yaml`
- Modify: `tests/test_config/test_loader.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing tests for custom scoring loader**

```python
# tests/test_config/test_loader.py — ADD to end of file

class TestLoadCustomScoring:
    """Gap 15: custom_scoring.yaml with inherit + overrides."""

    def test_load_custom_scoring_with_inherit(self, tmp_path):
        """Custom scoring inherits from a preset and overrides specific values."""
        custom = tmp_path / "custom_scoring.yaml"
        custom.write_text(
            "inherit: ppr\n"
            "overrides:\n"
            "  passing_td: 6\n"
            "  reception_wr: 1.5\n"
            "  reception_te: 1.5\n"
            "  rushing_bonus_100: 3\n"
        )
        defaults = load_defaults()
        result = load_custom_scoring(custom, defaults["scoring"])
        # Should have all PPR values plus overrides
        assert result["passing_td"] == 6  # overridden from 4
        assert result["reception"] == 1  # inherited from PPR
        assert result["reception_wr"] == 1.5  # new override
        assert result["reception_te"] == 1.5  # new override
        assert result["rushing_bonus_100"] == 3  # new override
        assert result["passing_yard"] == 0.04  # inherited from PPR

    def test_load_custom_scoring_without_inherit(self, tmp_path):
        """Custom scoring with no inherit starts from empty base."""
        custom = tmp_path / "custom_scoring.yaml"
        custom.write_text(
            "overrides:\n"
            "  passing_td: 6\n"
            "  rushing_td: 6\n"
        )
        defaults = load_defaults()
        result = load_custom_scoring(custom, defaults["scoring"])
        assert result["passing_td"] == 6
        assert result["rushing_td"] == 6
        assert "passing_yard" not in result  # no inheritance

    def test_load_custom_scoring_inherit_half_ppr(self, tmp_path):
        """Inherit from half_ppr preset."""
        custom = tmp_path / "custom_scoring.yaml"
        custom.write_text(
            "inherit: half_ppr\n"
            "overrides:\n"
            "  passing_td: 6\n"
        )
        defaults = load_defaults()
        result = load_custom_scoring(custom, defaults["scoring"])
        assert result["reception"] == 0.5  # inherited from half_ppr
        assert result["passing_td"] == 6  # overridden

    def test_load_custom_scoring_invalid_inherit(self, tmp_path):
        """Invalid inherit preset raises ConfigError."""
        custom = tmp_path / "custom_scoring.yaml"
        custom.write_text("inherit: superflex_ppr\noverrides:\n  passing_td: 6\n")
        defaults = load_defaults()
        with pytest.raises(ConfigError, match="Unknown scoring format"):
            load_custom_scoring(custom, defaults["scoring"])

    def test_load_custom_scoring_file_not_found(self):
        """Missing custom scoring file raises ConfigError."""
        from pathlib import Path
        defaults = load_defaults()
        with pytest.raises(ConfigError, match="Config file not found"):
            load_custom_scoring(Path("/nonexistent/custom.yaml"), defaults["scoring"])
```

- [ ] **Step 2: Write failing tests for config resolution chain**

```python
# tests/test_cli.py — ADD to end of file

class TestConfigResolution:
    """Gap 14: Auto-load season.yaml. Gap 16: Use defaults.yaml values."""

    def test_resolve_config_chain_defaults_only(self):
        """With no season.yaml and no CLI flags, use defaults."""
        from fantasy_sim.cli import _resolve_config_chain
        config = _resolve_config_chain(
            scoring_format="ppr",
            scoring_config_path=None,
            season_yaml_path=None,
        )
        assert config["passing_yard"] == 0.04
        assert config["reception"] == 1

    def test_resolve_config_chain_with_scoring_config(self, tmp_path):
        """--scoring-config overrides the preset."""
        from fantasy_sim.cli import _resolve_config_chain
        custom = tmp_path / "custom.yaml"
        custom.write_text("inherit: ppr\noverrides:\n  passing_td: 6\n")
        config = _resolve_config_chain(
            scoring_format="ppr",
            scoring_config_path=str(custom),
            season_yaml_path=None,
        )
        assert config["passing_td"] == 6
        assert config["reception"] == 1  # still from PPR

    def test_defaults_yaml_provides_num_sims(self):
        """defaults.yaml simulation.num_sims should be accessible."""
        from fantasy_sim.config.loader import load_defaults
        defaults = load_defaults()
        assert defaults["simulation"]["num_sims"] == 1000

    def test_defaults_yaml_provides_historical_seasons(self):
        """defaults.yaml simulation.historical_seasons should be accessible."""
        from fantasy_sim.config.loader import load_defaults
        defaults = load_defaults()
        assert defaults["simulation"]["historical_seasons"] == [2022, 2023, 2024]
```

- [ ] **Step 3: Implement load_custom_scoring in config/loader.py**

```python
# src/fantasy_sim/config/loader.py — ADD after existing functions

def load_custom_scoring(path: Path, scoring_presets: dict) -> dict:
    """Load a custom scoring config that optionally inherits from a preset.

    Custom scoring file format:
        inherit: ppr          # optional: base preset to inherit from
        overrides:            # scoring keys to override or add
            passing_td: 6
            reception_wr: 1.5

    Args:
        path: Path to custom_scoring.yaml
        scoring_presets: The "scoring" section from defaults.yaml

    Returns:
        Flat dict of stat_name -> point_value with inheritance resolved.
    """
    config = load_config(path)

    # Start with inherited base if specified
    inherit_from = config.get("inherit")
    if inherit_from:
        base = resolve_scoring(scoring_presets, inherit_from)
    else:
        base = {}

    # Apply overrides on top
    overrides = config.get("overrides", {})
    if overrides and isinstance(overrides, dict):
        base.update(overrides)

    return base
```

- [ ] **Step 4: Add _resolve_config_chain and _get_training_seasons to cli.py**

```python
# src/fantasy_sim/cli.py — ADD after _build_overrides function, before @click.group()

def _resolve_config_chain(
    scoring_format: str,
    scoring_config_path: str | None,
    season_yaml_path: str | None = None,
) -> dict:
    """Resolve scoring config through the config chain.

    Resolution order:
    1. defaults.yaml -> resolve scoring preset (ppr/half_ppr/standard)
    2. If season.yaml exists at season_yaml_path, load scoring_format from it
    3. If --scoring-config is provided, load custom scoring (overrides preset)

    Returns:
        Flat scoring config dict.
    """
    from fantasy_sim.config.loader import load_custom_scoring

    defaults = load_defaults()
    scoring_presets = defaults["scoring"]

    # Step 1: Check if season.yaml specifies a different scoring format
    effective_format = scoring_format
    if season_yaml_path:
        season_path = Path(season_yaml_path)
        if season_path.exists():
            import yaml
            with open(season_path) as f:
                season_config = yaml.safe_load(f) or {}
            if "scoring_format" in season_config:
                effective_format = season_config["scoring_format"]

    # Step 2: Resolve the base preset
    scoring_config = resolve_scoring(scoring_presets, effective_format)

    # Step 3: If custom scoring config provided, apply it on top
    if scoring_config_path:
        scoring_config = load_custom_scoring(Path(scoring_config_path), scoring_presets)

    return scoring_config


def _get_training_seasons(season: int) -> list[int]:
    """Get training seasons from defaults.yaml or fall back to [season-3 : season].

    Uses defaults.yaml simulation.historical_seasons if available and applicable,
    otherwise computes relative to the target season.
    """
    defaults = load_defaults()
    sim_config = defaults.get("simulation", {})
    num_years = len(sim_config.get("historical_seasons", [1, 2, 3]))
    return list(range(season - num_years, season))


def _auto_detect_season_yaml() -> str | None:
    """Auto-detect config/season.yaml if it exists in the project root."""
    candidates = [
        Path("config/season.yaml"),
        Path.cwd() / "config" / "season.yaml",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None
```

- [ ] **Step 5: Update week and season commands to use config chain**

In `src/fantasy_sim/cli.py`, update the `week` command to add `--scoring-config` option and use `_resolve_config_chain` and `_get_training_seasons`:

```python
# src/fantasy_sim/cli.py — REPLACE the week command decorator and first few lines

@main.command()
@click.argument("week_num", type=int)
@click.option("--season", default=2024, help="NFL season year")
@click.option("--sims", default=None, type=click.IntRange(min=1), help="Number of simulations per game")
@click.option("--scoring", default="ppr", type=click.Choice(["ppr", "half_ppr", "standard"]))
@click.option("--scoring-config", "scoring_config_path", default=None, help="Path to custom_scoring.yaml")
@click.option("--format", "output_format", default="table", type=click.Choice(["table", "csv", "json"]))
@click.option("--output", "output_path", default=None)
@click.option("--override", "overrides", multiple=True, help="Player/team override: 'name.field=value'")
@click.option("--config", "config_path", default=None, help="Path to season.yaml with overrides")
def week(week_num, season, sims, scoring, scoring_config_path, output_format, output_path, overrides, config_path):
    """Simulate all games in an NFL week using real nflverse data."""
    # Auto-detect season.yaml if --config not provided
    effective_config_path = config_path or _auto_detect_season_yaml()

    # Resolve scoring through config chain
    scoring_config = _resolve_config_chain(
        scoring_format=scoring,
        scoring_config_path=scoring_config_path,
        season_yaml_path=effective_config_path,
    )

    # Use defaults.yaml for num_sims if not specified via CLI
    if sims is None:
        defaults = load_defaults()
        sims = defaults.get("simulation", {}).get("num_sims", 1000)

    training_seasons = _get_training_seasons(season)

    loader = DataLoader()
    builder = GameContextBuilder(cache_dir=loader.cache_dir)

    click.echo(f"Loading schedule for {season} Week {week_num}...")
    schedules = loader.load_schedules([season])
    week_games = schedules.filter(
        (pl.col("week") == week_num) & (pl.col("season") == season)
    )

    if week_games.shape[0] == 0:
        click.echo(f"No games found for {season} Week {week_num}.", err=True)
        click.echo("Check the schedule data or try a different week.", err=True)
        raise SystemExit(1)

    click.echo(f"Found {week_games.shape[0]} games. Running {sims} sims each ({scoring})...\n")

    all_player_projs = []
    override_set = _build_overrides(overrides, effective_config_path)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
    ) as progress:
        task = progress.add_task("Simulating games...", total=week_games.shape[0])
        for game in week_games.iter_rows(named=True):
            home = game["home_team"]
            away = game["away_team"]
            progress.update(task, description=f"{away} @ {home}")

            home_dists, away_dists, home_roster, away_roster = builder.build_game(
                home_team=home, away_team=away, seasons=training_seasons,
            )

            if override_set.players or override_set.teams:
                apply_overrides_fn(override_set, home_dists, away_dists, home_roster, away_roster)

            seed = zlib.crc32(game["game_id"].encode()) % (2**31)
            results = run_simulations(
                home_dists, away_dists, n_sims=sims, seed=seed,
                home_roster=home_roster, away_roster=away_roster,
            )

            all_player_projs.extend(build_player_projections(results.games, scoring_config))
            progress.advance(task)

    all_player_projs.sort(key=lambda p: p["fpts"], reverse=True)
    for i, p in enumerate(all_player_projs, 1):
        p["rank"] = i
    player_projs = all_player_projs
    click.echo(f"\n{season} Week {week_num} Projections ({scoring.upper()}, {sims} sims/game)\n")

    _display_projections(player_projs, output_format, output_path)
```

Apply the same pattern to the `season` command: add `--scoring-config`, use `_resolve_config_chain`, `_get_training_seasons`, auto-detect season.yaml, and default `sims` from `defaults.yaml`. The `demo` command should also gain `--scoring-config`.

- [ ] **Step 6: Create custom_scoring.example.yaml**

```yaml
# config/custom_scoring.example.yaml
# Custom scoring configuration. Copy and modify for your league.
#
# Usage: fantasy-sim week 1 --scoring-config config/custom_scoring.yaml
#
# "inherit" sets the base preset (ppr, half_ppr, or standard).
# "overrides" adds or replaces scoring values on top of the base.

inherit: ppr

overrides:
  # Superflex / 6pt passing TD
  passing_td: 6

  # TE premium
  reception_te: 1.5

  # Yardage bonuses (stackable)
  rushing_bonus_100: 3
  receiving_bonus_100: 3
  passing_bonus_300: 3
```

- [ ] **Step 7: Run tests and verify**

```bash
uv run pytest tests/test_config/test_loader.py tests/test_cli.py -v
```

- [ ] **Step 8: Commit**

```bash
git add src/fantasy_sim/config/loader.py src/fantasy_sim/cli.py \
    config/custom_scoring.example.yaml \
    tests/test_config/test_loader.py tests/test_cli.py
git commit -m "feat(config): add custom scoring config, auto-load season.yaml, use defaults.yaml

load_custom_scoring() reads custom_scoring.yaml with inherit + overrides.
_resolve_config_chain() merges defaults -> season.yaml -> --scoring-config.
_get_training_seasons() reads historical_seasons from defaults.yaml.
week/season commands auto-detect config/season.yaml and default sims
from defaults.yaml simulation.num_sims."
```

---

### Task 3: Detailed Projections with Distributions (Gaps 19, 21)

**Files:**
- Modify: `src/fantasy_sim/scoring/projections.py`
- Modify: `tests/test_scoring/test_projections.py`

- [ ] **Step 1: Write failing tests for build_detailed_projections**

```python
# tests/test_scoring/test_projections.py — ADD to end of file

from fantasy_sim.scoring.projections import build_detailed_projections


class TestBuildDetailedProjections:
    """Gap 21: Projections with floor/ceiling/stddev."""

    def test_returns_list_of_dicts(self, ppr_config):
        games = [make_game_result() for _ in range(20)]
        projections = build_detailed_projections(games, ppr_config)
        assert isinstance(projections, list)
        assert len(projections) > 0

    def test_has_distribution_fields(self, ppr_config):
        games = [make_game_result() for _ in range(20)]
        projections = build_detailed_projections(games, ppr_config)
        qb = next(p for p in projections if p["position"] == "QB")
        # Must have distribution keys for fpts
        assert "fpts_floor" in qb
        assert "fpts_ceiling" in qb
        assert "fpts_stddev" in qb
        # Must have distribution keys for key stats
        assert "pass_yards_floor" in qb
        assert "pass_yards_ceiling" in qb
        assert "pass_yards_stddev" in qb

    def test_floor_less_than_mean_less_than_ceiling(self, ppr_config):
        """floor (10th pct) <= mean <= ceiling (90th pct)."""
        games = [make_game_result() for _ in range(50)]
        projections = build_detailed_projections(games, ppr_config)
        for p in projections:
            assert p["fpts_floor"] <= p["fpts"], f"{p['name']}: floor > mean"
            assert p["fpts"] <= p["fpts_ceiling"], f"{p['name']}: mean > ceiling"

    def test_stddev_non_negative(self, ppr_config):
        games = [make_game_result() for _ in range(20)]
        projections = build_detailed_projections(games, ppr_config)
        for p in projections:
            assert p["fpts_stddev"] >= 0

    def test_sorted_by_fpts(self, ppr_config):
        games = [make_game_result() for _ in range(20)]
        projections = build_detailed_projections(games, ppr_config)
        fpts = [p["fpts"] for p in projections]
        assert fpts == sorted(fpts, reverse=True)

    def test_has_all_base_fields(self, ppr_config):
        """Detailed projections should include all fields from regular projections too."""
        games = [make_game_result() for _ in range(20)]
        projections = build_detailed_projections(games, ppr_config)
        qb = next(p for p in projections if p["position"] == "QB")
        # All base fields present
        assert "player_id" in qb
        assert "name" in qb
        assert "team" in qb
        assert "position" in qb
        assert "fpts" in qb
        assert "pass_yards" in qb
        assert "rank" in qb

    def test_stat_distributions_present(self, ppr_config):
        """Key stats should have floor/ceiling/stddev variants."""
        games = [make_game_result() for _ in range(20)]
        projections = build_detailed_projections(games, ppr_config)
        rb = next(p for p in projections if p["position"] == "RB")
        assert "rush_yards_floor" in rb
        assert "rush_yards_ceiling" in rb
        assert "rush_yards_stddev" in rb
        assert "receiving_yards_floor" in rb
        assert "receiving_yards_ceiling" in rb
```

- [ ] **Step 2: Implement build_detailed_projections**

```python
# src/fantasy_sim/scoring/projections.py — ADD after build_player_projections function

# Stats to compute distributions for
_DISTRIBUTION_STATS = [
    "pass_yards", "pass_tds", "rush_yards", "rush_tds",
    "targets", "receptions", "receiving_yards", "receiving_tds",
    "fumbles_lost",
]


def build_detailed_projections(
    games: list[GameResult], scoring_config: dict
) -> list[dict]:
    """Build projections with floor (10th pct), ceiling (90th pct), and stddev.

    Returns the same structure as build_player_projections, plus:
    - fpts_floor, fpts_ceiling, fpts_stddev
    - {stat}_floor, {stat}_ceiling, {stat}_stddev for each stat in _DISTRIBUTION_STATS

    Uses per-sim fantasy point scoring to compute fpts distributions directly
    rather than distributing the mean.
    """
    if not games:
        return []

    n_games = len(games)
    player_games: dict[str, list[PlayerBoxScore]] = defaultdict(list)
    for game in games:
        for pid, box in game.player_stats.items():
            player_games[pid].append(box)

    projections = []
    for pid, boxes in player_games.items():
        if not boxes:
            continue
        first = boxes[0]

        # Compute per-sim fpts for distribution
        fpts_per_sim = [score_player(b, scoring_config) for b in boxes]
        # Pad with zeros for sims where player didn't appear
        fpts_all = fpts_per_sim + [0.0] * (n_games - len(boxes))

        fpts_arr = np.array(fpts_all)

        # Base projection (same as build_player_projections)
        proj = {
            "player_id": pid,
            "name": first.name,
            "position": first.position,
            "team": first.team,
            "fpts": round(float(np.mean(fpts_arr)), 1),
            "fpts_floor": round(float(np.percentile(fpts_arr, 10)), 1),
            "fpts_ceiling": round(float(np.percentile(fpts_arr, 90)), 1),
            "fpts_stddev": round(float(np.std(fpts_arr)), 1),
        }

        # Add stat means + distributions
        for stat in _DISTRIBUTION_STATS:
            values = [getattr(b, stat, 0) for b in boxes]
            # Pad with zeros for missing sims
            all_values = values + [0] * (n_games - len(boxes))
            arr = np.array(all_values, dtype=float)
            proj[stat] = round(float(np.mean(arr)), 1)
            proj[f"{stat}_floor"] = round(float(np.percentile(arr, 10)), 1)
            proj[f"{stat}_ceiling"] = round(float(np.percentile(arr, 90)), 1)
            proj[f"{stat}_stddev"] = round(float(np.std(arr)), 1)

        projections.append(proj)

    projections.sort(key=lambda p: p["fpts"], reverse=True)
    for i, p in enumerate(projections, 1):
        p["rank"] = i

    return projections
```

- [ ] **Step 3: Run tests and verify**

```bash
uv run pytest tests/test_scoring/test_projections.py -v
```

- [ ] **Step 4: Commit**

```bash
git add src/fantasy_sim/scoring/projections.py tests/test_scoring/test_projections.py
git commit -m "feat(projections): add build_detailed_projections with floor/ceiling/stddev

Computes per-sim fantasy points for true fpts distribution. Adds
floor (10th percentile), ceiling (90th percentile), and stddev for
fpts and all tracked stats (pass_yards, rush_yards, etc.)."
```

---

### Task 4: Detail Tables — Output Formatting (Gap 19 continued, Gap 21 continued)

**Files:**
- Modify: `src/fantasy_sim/output/tables.py`
- Modify: `tests/test_output/test_tables.py`

- [ ] **Step 1: Write failing tests for detail tables**

```python
# tests/test_output/test_tables.py — ADD to end of file

class TestDetailTables:
    """Gap 19/21: Detail tables with floor/ceiling/stddev columns."""

    def _make_qb_detail_proj(self):
        return [{
            "rank": 1, "player_id": "QB1", "name": "QB Name", "team": "KC", "position": "QB",
            "fpts": 22.5, "fpts_floor": 12.0, "fpts_ceiling": 35.0, "fpts_stddev": 7.2,
            "pass_yards": 280.0, "pass_yards_floor": 180.0, "pass_yards_ceiling": 390.0, "pass_yards_stddev": 65.0,
            "pass_tds": 2.1, "pass_tds_floor": 1.0, "pass_tds_ceiling": 3.0, "pass_tds_stddev": 0.8,
            "interceptions": 0.8, "interceptions_floor": 0.0, "interceptions_ceiling": 2.0, "interceptions_stddev": 0.6,
            "rush_yards": 15.0, "rush_yards_floor": 2.0, "rush_yards_ceiling": 32.0, "rush_yards_stddev": 10.0,
            "rush_tds": 0.2, "rush_tds_floor": 0.0, "rush_tds_ceiling": 1.0, "rush_tds_stddev": 0.4,
            "sacks": 2.0, "fumbles_lost": 0.3,
            "targets": 0.0, "receptions": 0.0, "receiving_yards": 0.0, "receiving_tds": 0.0,
        }]

    def _make_rb_detail_proj(self):
        return [{
            "rank": 1, "player_id": "RB1", "name": "RB Name", "team": "KC", "position": "RB",
            "fpts": 18.0, "fpts_floor": 8.0, "fpts_ceiling": 30.0, "fpts_stddev": 6.5,
            "rush_yards": 75.0, "rush_yards_floor": 35.0, "rush_yards_ceiling": 120.0, "rush_yards_stddev": 28.0,
            "rush_tds": 0.7, "rush_tds_floor": 0.0, "rush_tds_ceiling": 2.0, "rush_tds_stddev": 0.6,
            "targets": 4.0, "receptions": 3.0,
            "receiving_yards": 22.0, "receiving_yards_floor": 5.0, "receiving_yards_ceiling": 45.0, "receiving_yards_stddev": 13.0,
            "receiving_tds": 0.2, "receiving_tds_floor": 0.0, "receiving_tds_ceiling": 1.0, "receiving_tds_stddev": 0.4,
            "fumbles_lost": 0.1,
            "pass_yards": 0.0, "pass_tds": 0.0, "interceptions": 0.0, "sacks": 0.0,
        }]

    def test_format_qb_detail_table_returns_string(self):
        from fantasy_sim.output.tables import format_qb_detail_table
        result = format_qb_detail_table(self._make_qb_detail_proj())
        assert isinstance(result, str)
        assert "QB" in result

    def test_qb_detail_table_has_floor_ceiling(self):
        from fantasy_sim.output.tables import format_qb_detail_table
        result = format_qb_detail_table(self._make_qb_detail_proj())
        assert "Floor" in result or "Flr" in result
        assert "Ceil" in result

    def test_format_rb_detail_table_returns_string(self):
        from fantasy_sim.output.tables import format_rb_detail_table
        result = format_rb_detail_table(self._make_rb_detail_proj())
        assert isinstance(result, str)
        assert "RB" in result

    def test_format_wr_detail_table_returns_string(self):
        from fantasy_sim.output.tables import format_wr_detail_table
        proj = self._make_rb_detail_proj()
        proj[0]["position"] = "WR"
        result = format_wr_detail_table(proj)
        assert isinstance(result, str)

    def test_format_te_detail_table_returns_string(self):
        from fantasy_sim.output.tables import format_te_detail_table
        proj = self._make_rb_detail_proj()
        proj[0]["position"] = "TE"
        result = format_te_detail_table(proj)
        assert isinstance(result, str)
```

- [ ] **Step 2: Implement detail table formatters**

```python
# src/fantasy_sim/output/tables.py — ADD after existing functions

def format_qb_detail_table(projections: list[dict]) -> str:
    """QB table with floor/ceiling/stddev columns."""
    table = Table(title="QB Projections (Detailed)")
    table.add_column("Rk", justify="right", style="bold")
    table.add_column("Player", style="cyan")
    table.add_column("Team")
    table.add_column("FPts", justify="right", style="green bold")
    table.add_column("Flr", justify="right", style="dim")
    table.add_column("Ceil", justify="right", style="yellow")
    table.add_column("SD", justify="right", style="dim")
    table.add_column("PaYd", justify="right")
    table.add_column("Flr", justify="right", style="dim")
    table.add_column("Ceil", justify="right", style="yellow")
    table.add_column("PaTD", justify="right")
    table.add_column("INT", justify="right")
    table.add_column("RuYd", justify="right")
    table.add_column("FL", justify="right")

    for p in projections:
        table.add_row(
            str(p["rank"]), p["name"], p["team"],
            f"{p['fpts']:.1f}",
            f"{p.get('fpts_floor', 0):.1f}",
            f"{p.get('fpts_ceiling', 0):.1f}",
            f"{p.get('fpts_stddev', 0):.1f}",
            f"{p['pass_yards']:.0f}",
            f"{p.get('pass_yards_floor', 0):.0f}",
            f"{p.get('pass_yards_ceiling', 0):.0f}",
            f"{p['pass_tds']:.1f}",
            f"{p['interceptions']:.1f}",
            f"{p.get('rush_yards', 0):.1f}",
            f"{p['fumbles_lost']:.1f}",
        )

    return _render_table(table)


def format_rb_detail_table(projections: list[dict]) -> str:
    """RB table with floor/ceiling/stddev columns."""
    table = Table(title="RB Projections (Detailed)")
    table.add_column("Rk", justify="right", style="bold")
    table.add_column("Player", style="cyan")
    table.add_column("Team")
    table.add_column("FPts", justify="right", style="green bold")
    table.add_column("Flr", justify="right", style="dim")
    table.add_column("Ceil", justify="right", style="yellow")
    table.add_column("SD", justify="right", style="dim")
    table.add_column("RuYd", justify="right")
    table.add_column("Flr", justify="right", style="dim")
    table.add_column("Ceil", justify="right", style="yellow")
    table.add_column("RuTD", justify="right")
    table.add_column("Rec", justify="right")
    table.add_column("ReYd", justify="right")
    table.add_column("FL", justify="right")

    for p in projections:
        table.add_row(
            str(p["rank"]), p["name"], p["team"],
            f"{p['fpts']:.1f}",
            f"{p.get('fpts_floor', 0):.1f}",
            f"{p.get('fpts_ceiling', 0):.1f}",
            f"{p.get('fpts_stddev', 0):.1f}",
            f"{p['rush_yards']:.1f}",
            f"{p.get('rush_yards_floor', 0):.1f}",
            f"{p.get('rush_yards_ceiling', 0):.1f}",
            f"{p['rush_tds']:.1f}",
            f"{p['receptions']:.1f}",
            f"{p['receiving_yards']:.1f}",
            f"{p['fumbles_lost']:.1f}",
        )

    return _render_table(table)


def format_wr_detail_table(projections: list[dict]) -> str:
    """WR table with floor/ceiling/stddev columns."""
    table = Table(title="WR Projections (Detailed)")
    table.add_column("Rk", justify="right", style="bold")
    table.add_column("Player", style="cyan")
    table.add_column("Team")
    table.add_column("FPts", justify="right", style="green bold")
    table.add_column("Flr", justify="right", style="dim")
    table.add_column("Ceil", justify="right", style="yellow")
    table.add_column("SD", justify="right", style="dim")
    table.add_column("Tgt", justify="right")
    table.add_column("Rec", justify="right")
    table.add_column("ReYd", justify="right")
    table.add_column("Flr", justify="right", style="dim")
    table.add_column("Ceil", justify="right", style="yellow")
    table.add_column("ReTD", justify="right")
    table.add_column("FL", justify="right")

    for p in projections:
        table.add_row(
            str(p["rank"]), p["name"], p["team"],
            f"{p['fpts']:.1f}",
            f"{p.get('fpts_floor', 0):.1f}",
            f"{p.get('fpts_ceiling', 0):.1f}",
            f"{p.get('fpts_stddev', 0):.1f}",
            f"{p['targets']:.1f}",
            f"{p['receptions']:.1f}",
            f"{p['receiving_yards']:.1f}",
            f"{p.get('receiving_yards_floor', 0):.1f}",
            f"{p.get('receiving_yards_ceiling', 0):.1f}",
            f"{p['receiving_tds']:.1f}",
            f"{p['fumbles_lost']:.1f}",
        )

    return _render_table(table)


def format_te_detail_table(projections: list[dict]) -> str:
    """TE table with floor/ceiling/stddev columns."""
    table = Table(title="TE Projections (Detailed)")
    table.add_column("Rk", justify="right", style="bold")
    table.add_column("Player", style="cyan")
    table.add_column("Team")
    table.add_column("FPts", justify="right", style="green bold")
    table.add_column("Flr", justify="right", style="dim")
    table.add_column("Ceil", justify="right", style="yellow")
    table.add_column("SD", justify="right", style="dim")
    table.add_column("Tgt", justify="right")
    table.add_column("Rec", justify="right")
    table.add_column("ReYd", justify="right")
    table.add_column("Flr", justify="right", style="dim")
    table.add_column("Ceil", justify="right", style="yellow")
    table.add_column("ReTD", justify="right")
    table.add_column("FL", justify="right")

    for p in projections:
        table.add_row(
            str(p["rank"]), p["name"], p["team"],
            f"{p['fpts']:.1f}",
            f"{p.get('fpts_floor', 0):.1f}",
            f"{p.get('fpts_ceiling', 0):.1f}",
            f"{p.get('fpts_stddev', 0):.1f}",
            f"{p['targets']:.1f}",
            f"{p['receptions']:.1f}",
            f"{p['receiving_yards']:.1f}",
            f"{p.get('receiving_yards_floor', 0):.1f}",
            f"{p.get('receiving_yards_ceiling', 0):.1f}",
            f"{p['receiving_tds']:.1f}",
            f"{p['fumbles_lost']:.1f}",
        )

    return _render_table(table)
```

- [ ] **Step 3: Run tests and verify**

```bash
uv run pytest tests/test_output/test_tables.py -v
```

- [ ] **Step 4: Commit**

```bash
git add src/fantasy_sim/output/tables.py tests/test_output/test_tables.py
git commit -m "feat(output): add detail table formatters with floor/ceiling/stddev

New format_qb_detail_table, format_rb_detail_table, format_wr_detail_table,
format_te_detail_table show Flr/Ceil/SD columns for fpts and key stats."
```

---

### Task 5: `game` Command (Gap 17)

**Files:**
- Modify: `src/fantasy_sim/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing tests for game command**

```python
# tests/test_cli.py — ADD to end of file

class TestGameCommand:
    """Gap 17: game command — single-game deep dive."""

    def test_game_help(self, runner):
        result = runner.invoke(main, ["game", "--help"])
        assert result.exit_code == 0
        assert "game" in result.output.lower() or "home" in result.output.lower()

    @patch("fantasy_sim.cli.GameContextBuilder")
    @patch("fantasy_sim.cli.DataLoader")
    def test_game_command_runs(self, MockLoader, MockBuilder, runner):
        """game KC BUF --week 5 should simulate and display results."""
        mock_loader = MockLoader.return_value
        mock_loader.load_schedules.return_value = pl.DataFrame([
            {"season": 2024, "week": 5, "game_id": "2024_05_KC_BUF",
             "home_team": "KC", "away_team": "BUF"},
        ])
        mock_loader.cache_dir = Path("/tmp/cache")

        mock_builder = MockBuilder.return_value
        from fantasy_sim.engine.types import TeamDistributions
        from fantasy_sim.models.distributions import (
            PlayCallingDist, PlayOutcomeDist, TurnoverRates, KickingModel, DriveStartModel,
        )
        from fantasy_sim.models.player import TeamRoster, PlayerModel, PlayerUsage, PlayerOutcomes

        def make_dists(team):
            return TeamDistributions(
                play_calling=PlayCallingDist(team=team, distributions={}, default={"pass": 0.55, "run": 0.45}),
                play_outcomes=PlayOutcomeDist(distributions={}, defaults={
                    "pass": np.array([0, 5, 8, 10, 12, 15]),
                    "run": np.array([2, 3, 4, 5, 6]),
                }),
                turnover_rates=TurnoverRates(team=team, int_rate=0.02, fumble_rate=0.01, sack_rate=0.06, sack_fumble_rate=0.10),
                kicking=KickingModel(fg_make_rate={"0_39": 0.93, "40_49": 0.82, "50_plus": 0.65}, xp_rate=0.94),
                drive_start=DriveStartModel(touchback_rate=0.55, touchback_yardline=75, return_yardlines=np.array([74, 76])),
            )

        def make_roster(team):
            return TeamRoster(team=team, players=[
                PlayerModel(f"{team}_QB", "QB", "QB", team, PlayerUsage(snap_share=1.0), PlayerOutcomes()),
                PlayerModel(f"{team}_WR", "WR", "WR", team, PlayerUsage(target_share=0.50),
                           PlayerOutcomes(catch_rate=0.60, receiving_yards_dist=np.array([8, 12]))),
                PlayerModel(f"{team}_RB", "RB", "RB", team, PlayerUsage(carry_share=1.0, target_share=0.50),
                           PlayerOutcomes(rushing_yards_dist=np.array([3, 5, 7]),
                                         catch_rate=0.70, receiving_yards_dist=np.array([4, 6]))),
            ])

        mock_builder.build_game.return_value = (
            make_dists("KC"), make_dists("BUF"), make_roster("KC"), make_roster("BUF"),
        )

        result = runner.invoke(main, ["game", "KC", "BUF", "--week", "5", "--sims", "10"])
        assert result.exit_code == 0
        # Should show game score summary
        assert "KC" in result.output
        assert "BUF" in result.output
        assert "Win" in result.output or "win" in result.output

    def test_game_demo_mode(self, runner):
        """game with --demo should work without real data."""
        result = runner.invoke(main, ["game", "HOME", "AWAY", "--demo", "--sims", "10"])
        assert result.exit_code == 0
        assert "HOME" in result.output
        assert "AWAY" in result.output
```

- [ ] **Step 2: Implement game command**

```python
# src/fantasy_sim/cli.py — ADD before the backtest command

@main.command()
@click.argument("home_team")
@click.argument("away_team")
@click.option("--week", "week_num", default=1, type=int, help="Week number for schedule lookup")
@click.option("--season", default=2024, help="NFL season year")
@click.option("--sims", default=None, type=click.IntRange(min=1), help="Number of simulations")
@click.option("--scoring", default="ppr", type=click.Choice(["ppr", "half_ppr", "standard"]))
@click.option("--scoring-config", "scoring_config_path", default=None, help="Path to custom_scoring.yaml")
@click.option("--demo", is_flag=True, help="Use synthetic data (no network needed)")
@click.option("--detail", is_flag=True, help="Show floor/ceiling/stddev distributions")
@click.option("--override", "overrides", multiple=True, help="Player/team override: 'name.field=value'")
@click.option("--config", "config_path", default=None, help="Path to season.yaml with overrides")
def game(home_team, away_team, week_num, season, sims, scoring, scoring_config_path, demo, detail, overrides, config_path):
    """Simulate a single game with deep-dive projections.

    Example: fantasy-sim game KC BUF --week 5
    """
    effective_config_path = config_path or _auto_detect_season_yaml()
    scoring_config = _resolve_config_chain(
        scoring_format=scoring,
        scoring_config_path=scoring_config_path,
        season_yaml_path=effective_config_path,
    )

    if sims is None:
        defaults = load_defaults()
        sims = defaults.get("simulation", {}).get("num_sims", 1000)

    home_team = home_team.upper()
    away_team = away_team.upper()

    if demo:
        home_dists = _make_demo_dists(home_team)
        away_dists = _make_demo_dists(away_team)
        home_roster = _make_demo_roster(home_team)
        away_roster = _make_demo_roster(away_team)
    else:
        training_seasons = _get_training_seasons(season)
        loader = DataLoader()
        builder = GameContextBuilder(cache_dir=loader.cache_dir)
        home_dists, away_dists, home_roster, away_roster = builder.build_game(
            home_team=home_team, away_team=away_team, seasons=training_seasons,
        )

    override_set = _build_overrides(overrides, effective_config_path)
    if override_set.players or override_set.teams:
        apply_overrides_fn(override_set, home_dists, away_dists, home_roster, away_roster)

    click.echo(f"Simulating {away_team} @ {home_team} — Week {week_num} ({sims} sims)...\n")

    seed = 42 if demo else zlib.crc32(f"{season}_{week_num}_{home_team}_{away_team}".encode()) % (2**31)
    results = run_simulations(
        home_dists, away_dists, n_sims=sims, seed=seed,
        home_roster=home_roster, away_roster=away_roster,
    )

    # Game summary
    game_summary = results.summary()
    home_wins = sum(1 for g in results.games if g.home_score > g.away_score)
    away_wins = sum(1 for g in results.games if g.away_score > g.home_score)
    ties = len(results.games) - home_wins - away_wins

    click.echo(f"{home_team} vs {away_team} — Week {week_num} ({sims} sims)")
    click.echo(f"Avg Score: {home_team} {game_summary['home_score_mean']:.1f} - {away_team} {game_summary['away_score_mean']:.1f}")
    click.echo(f"{home_team} Win%: {home_wins/len(results.games):.1%}   {away_team} Win%: {away_wins/len(results.games):.1%}")
    if ties > 0:
        click.echo(f"Tie%: {ties/len(results.games):.1%}")
    click.echo()

    # Player projections — grouped by team
    team_map = {"HOME": home_team, "AWAY": away_team}
    if detail:
        from fantasy_sim.scoring.projections import build_detailed_projections
        player_projs = build_detailed_projections(results.games, scoring_config)
    else:
        player_projs = build_player_projections(results.games, scoring_config)

    dst_projs = build_dst_projections(results.games, scoring_config, team_map=team_map)
    kicker_projs = build_kicker_projections(results.games, scoring_config, team_map=team_map)

    # Display by team
    for team_name in [home_team, away_team]:
        team_players = [p for p in player_projs if p["team"] == team_name]
        if not team_players:
            continue

        click.echo(f"{team_name} Key Players:")
        if detail:
            from fantasy_sim.output.tables import (
                format_qb_detail_table, format_rb_detail_table,
                format_wr_detail_table, format_te_detail_table,
            )
            qbs = [p for p in team_players if p["position"] == "QB"]
            rbs = [p for p in team_players if p["position"] == "RB"]
            wrs = [p for p in team_players if p["position"] == "WR"]
            tes = [p for p in team_players if p["position"] == "TE"]
            if qbs:
                click.echo(format_qb_detail_table(qbs))
            if rbs:
                click.echo(format_rb_detail_table(rbs))
            if wrs:
                click.echo(format_wr_detail_table(wrs))
            if tes:
                click.echo(format_te_detail_table(tes))
        else:
            qbs = [p for p in team_players if p["position"] == "QB"]
            rbs = [p for p in team_players if p["position"] == "RB"]
            wrs = [p for p in team_players if p["position"] == "WR"]
            tes = [p for p in team_players if p["position"] == "TE"]
            if qbs:
                click.echo(format_qb_table(qbs))
            if rbs:
                click.echo(format_rb_table(rbs))
            if wrs:
                click.echo(format_wr_table(wrs))
            if tes:
                click.echo(format_te_table(tes))

    if kicker_projs:
        click.echo(format_kicker_table(kicker_projs))
    if dst_projs:
        click.echo(format_dst_table(dst_projs))
```

- [ ] **Step 3: Run tests and verify**

```bash
uv run pytest tests/test_cli.py::TestGameCommand -v
```

- [ ] **Step 4: Commit**

```bash
git add src/fantasy_sim/cli.py tests/test_cli.py
git commit -m "feat(cli): add game command for single-game deep dive

fantasy-sim game KC BUF --week 5 shows game score distribution,
win percentages, and per-team player projections. Supports --demo
for synthetic data and --detail for floor/ceiling/stddev."
```

---

### Task 6: `player` Command (Gap 18)

**Files:**
- Modify: `src/fantasy_sim/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing tests for player command**

```python
# tests/test_cli.py — ADD to end of file

class TestPlayerCommand:
    """Gap 18: player command — single player projection."""

    def test_player_help(self, runner):
        result = runner.invoke(main, ["player", "--help"])
        assert result.exit_code == 0
        assert "player" in result.output.lower()

    @patch("fantasy_sim.cli.GameContextBuilder")
    @patch("fantasy_sim.cli.DataLoader")
    def test_player_command_runs(self, MockLoader, MockBuilder, runner):
        """player 'nico_collins' --week 5 should find and display the player."""
        mock_loader = MockLoader.return_value
        mock_loader.load_schedules.return_value = pl.DataFrame([
            {"season": 2024, "week": 5, "game_id": "2024_05_HOU_BUF",
             "home_team": "HOU", "away_team": "BUF"},
        ])
        mock_loader.cache_dir = Path("/tmp/cache")

        mock_builder = MockBuilder.return_value
        from fantasy_sim.engine.types import TeamDistributions
        from fantasy_sim.models.distributions import (
            PlayCallingDist, PlayOutcomeDist, TurnoverRates, KickingModel, DriveStartModel,
        )
        from fantasy_sim.models.player import TeamRoster, PlayerModel, PlayerUsage, PlayerOutcomes

        def make_dists(team):
            return TeamDistributions(
                play_calling=PlayCallingDist(team=team, distributions={}, default={"pass": 0.55, "run": 0.45}),
                play_outcomes=PlayOutcomeDist(distributions={}, defaults={
                    "pass": np.array([0, 5, 8, 10, 12, 15]),
                    "run": np.array([2, 3, 4, 5, 6]),
                }),
                turnover_rates=TurnoverRates(team=team, int_rate=0.02, fumble_rate=0.01, sack_rate=0.06, sack_fumble_rate=0.10),
                kicking=KickingModel(fg_make_rate={"0_39": 0.93, "40_49": 0.82, "50_plus": 0.65}, xp_rate=0.94),
                drive_start=DriveStartModel(touchback_rate=0.55, touchback_yardline=75, return_yardlines=np.array([74, 76])),
            )

        hou_roster = TeamRoster(team="HOU", players=[
            PlayerModel("HOU_QB", "QB", "QB", "HOU", PlayerUsage(snap_share=1.0), PlayerOutcomes()),
            PlayerModel("nico_collins", "Nico Collins", "WR", "HOU", PlayerUsage(target_share=0.50),
                       PlayerOutcomes(catch_rate=0.65, receiving_yards_dist=np.array([8, 12, 15, 20]))),
            PlayerModel("HOU_RB", "RB", "RB", "HOU", PlayerUsage(carry_share=1.0, target_share=0.50),
                       PlayerOutcomes(rushing_yards_dist=np.array([3, 5, 7]),
                                     catch_rate=0.70, receiving_yards_dist=np.array([4, 6]))),
        ])
        buf_roster = TeamRoster(team="BUF", players=[
            PlayerModel("BUF_QB", "QB", "QB", "BUF", PlayerUsage(snap_share=1.0), PlayerOutcomes()),
            PlayerModel("BUF_WR", "WR", "WR", "BUF", PlayerUsage(target_share=0.50),
                       PlayerOutcomes(catch_rate=0.60, receiving_yards_dist=np.array([8, 12]))),
            PlayerModel("BUF_RB", "RB", "RB", "BUF", PlayerUsage(carry_share=1.0, target_share=0.50),
                       PlayerOutcomes(rushing_yards_dist=np.array([3, 5, 7]),
                                     catch_rate=0.70, receiving_yards_dist=np.array([4, 6]))),
        ])

        mock_builder.build_game.return_value = (
            make_dists("HOU"), make_dists("BUF"), hou_roster, buf_roster,
        )

        result = runner.invoke(main, [
            "player", "nico_collins", "--week", "5", "--season", "2024", "--sims", "10"
        ])
        assert result.exit_code == 0
        assert "Nico Collins" in result.output or "nico_collins" in result.output

    def test_player_not_found(self, runner):
        """Player not in any game should show helpful error."""
        # Demo mode has no "nico_collins"
        result = runner.invoke(main, ["player", "nonexistent_player_xyz", "--demo", "--sims", "10"])
        assert result.exit_code != 0 or "not found" in result.output.lower() or "No player" in result.output
```

- [ ] **Step 2: Implement player command**

```python
# src/fantasy_sim/cli.py — ADD after game command, before backtest command

@main.command()
@click.argument("player_query")
@click.option("--week", "week_num", default=1, type=int, help="Week number")
@click.option("--season", default=2024, help="NFL season year")
@click.option("--sims", default=None, type=click.IntRange(min=1), help="Number of simulations")
@click.option("--scoring", default="ppr", type=click.Choice(["ppr", "half_ppr", "standard"]))
@click.option("--scoring-config", "scoring_config_path", default=None, help="Path to custom_scoring.yaml")
@click.option("--demo", is_flag=True, help="Use synthetic data (no network needed)")
@click.option("--override", "overrides", multiple=True, help="Player/team override: 'name.field=value'")
@click.option("--config", "config_path", default=None, help="Path to season.yaml with overrides")
def player(player_query, week_num, season, sims, scoring, scoring_config_path, demo, overrides, config_path):
    """Show projection for a single player.

    Uses fuzzy name matching. Example: fantasy-sim player "nico_collins" --week 5
    """
    effective_config_path = config_path or _auto_detect_season_yaml()
    scoring_config = _resolve_config_chain(
        scoring_format=scoring,
        scoring_config_path=scoring_config_path,
        season_yaml_path=effective_config_path,
    )

    if sims is None:
        defaults = load_defaults()
        sims = defaults.get("simulation", {}).get("num_sims", 1000)

    if demo:
        # Demo mode: run one game with synthetic data
        home_dists = _make_demo_dists("HOME")
        away_dists = _make_demo_dists("AWAY")
        home_roster = _make_demo_roster("HOME")
        away_roster = _make_demo_roster("AWAY")
        all_rosters = [home_roster, away_roster]
        game_configs = [(home_dists, away_dists, home_roster, away_roster, "HOME", "AWAY")]
    else:
        training_seasons = _get_training_seasons(season)
        loader = DataLoader()
        builder = GameContextBuilder(cache_dir=loader.cache_dir)

        click.echo(f"Loading schedule for {season} Week {week_num}...")
        schedules = loader.load_schedules([season])
        week_games = schedules.filter(
            (pl.col("week") == week_num) & (pl.col("season") == season)
        )

        if week_games.shape[0] == 0:
            click.echo(f"No games found for {season} Week {week_num}.", err=True)
            raise SystemExit(1)

        # Build all games to find the player
        all_rosters = []
        game_configs = []
        for g in week_games.iter_rows(named=True):
            home, away = g["home_team"], g["away_team"]
            home_dists, away_dists, home_roster, away_roster = builder.build_game(
                home_team=home, away_team=away, seasons=training_seasons,
            )
            all_rosters.extend([home_roster, away_roster])
            game_configs.append((home_dists, away_dists, home_roster, away_roster, home, away))

    # Resolve player name
    from fantasy_sim.overrides.resolver import PlayerResolver
    resolver = PlayerResolver(all_rosters)
    try:
        player_id = resolver.resolve(player_query)
    except KeyError as e:
        click.echo(f"No player found matching '{player_query}'. {e}", err=True)
        raise SystemExit(1)

    # Find which game this player is in
    target_game = None
    for game_cfg in game_configs:
        hd, ad, hr, ar, home_name, away_name = game_cfg
        roster_ids = {p.player_id for p in hr.players} | {p.player_id for p in ar.players}
        if player_id in roster_ids:
            target_game = game_cfg
            break

    if target_game is None:
        click.echo(f"Player '{player_query}' not found in any Week {week_num} game.", err=True)
        raise SystemExit(1)

    hd, ad, hr, ar, home_name, away_name = target_game

    override_set = _build_overrides(overrides, effective_config_path)
    if override_set.players or override_set.teams:
        apply_overrides_fn(override_set, hd, ad, hr, ar)

    # Find player info
    player_info = None
    for roster in [hr, ar]:
        for p in roster.players:
            if p.player_id == player_id:
                player_info = p
                break

    click.echo(f"Simulating {away_name} @ {home_name} for {player_info.name} ({player_info.position}, {player_info.team})...\n")

    seed = 42 if demo else zlib.crc32(f"{season}_{week_num}_{home_name}_{away_name}".encode()) % (2**31)
    results = run_simulations(
        hd, ad, n_sims=sims, seed=seed,
        home_roster=hr, away_roster=ar,
    )

    # Build detailed projections for this player
    from fantasy_sim.scoring.projections import build_detailed_projections
    all_projs = build_detailed_projections(results.games, scoring_config)
    player_proj = next((p for p in all_projs if p["player_id"] == player_id), None)

    if player_proj is None:
        click.echo(f"No projection data for {player_info.name}.", err=True)
        raise SystemExit(1)

    # Display player card
    click.echo(f"{player_info.name} ({player_info.position}, {player_info.team}) — Week {week_num}")
    click.echo(f"Matchup: {away_name} @ {home_name} ({sims} sims)\n")

    from rich.table import Table as RichTable
    from rich.console import Console

    table = RichTable(title=f"{player_info.name} Projection")
    table.add_column("Stat", style="cyan")
    table.add_column("Avg", justify="right", style="green bold")
    table.add_column("Floor", justify="right", style="dim")
    table.add_column("Ceiling", justify="right", style="yellow")
    table.add_column("StdDev", justify="right", style="dim")

    # FPts row
    table.add_row(
        "FPts",
        f"{player_proj['fpts']:.1f}",
        f"{player_proj['fpts_floor']:.1f}",
        f"{player_proj['fpts_ceiling']:.1f}",
        f"{player_proj['fpts_stddev']:.1f}",
    )

    # Position-specific stat rows
    stat_labels = {
        "pass_yards": "Pass Yds", "pass_tds": "Pass TD",
        "interceptions": "INT",
        "rush_yards": "Rush Yds", "rush_tds": "Rush TD",
        "targets": "Targets", "receptions": "Rec",
        "receiving_yards": "Rec Yds", "receiving_tds": "Rec TD",
        "fumbles_lost": "Fum Lost",
    }
    for stat, label in stat_labels.items():
        mean_val = player_proj.get(stat, 0)
        if mean_val == 0 and stat not in ("fumbles_lost",):
            # Skip zero stats that aren't relevant to position
            floor_val = player_proj.get(f"{stat}_floor", 0)
            ceil_val = player_proj.get(f"{stat}_ceiling", 0)
            if mean_val == 0 and floor_val == 0 and ceil_val == 0:
                continue

        table.add_row(
            label,
            f"{mean_val:.1f}",
            f"{player_proj.get(f'{stat}_floor', 0):.1f}",
            f"{player_proj.get(f'{stat}_ceiling', 0):.1f}",
            f"{player_proj.get(f'{stat}_stddev', 0):.1f}",
        )

    console = Console(width=120, force_terminal=True)
    with console.capture() as capture:
        console.print(table)
    click.echo(capture.get())
```

- [ ] **Step 3: Run tests and verify**

```bash
uv run pytest tests/test_cli.py::TestPlayerCommand -v
```

- [ ] **Step 4: Commit**

```bash
git add src/fantasy_sim/cli.py tests/test_cli.py
git commit -m "feat(cli): add player command for single-player deep dive

fantasy-sim player 'nico_collins' --week 5 finds the player via fuzzy
matching, simulates their game, and displays a detailed stat card
with avg/floor/ceiling/stddev for all relevant stats."
```

---

### Task 7: Kicker Projection Attribution (Gap 13)

**Files:**
- Modify: `src/fantasy_sim/scoring/projections.py`
- Modify: `tests/test_scoring/test_projections.py`

- [ ] **Step 1: Write failing tests for kicker attribution**

```python
# tests/test_scoring/test_projections.py — ADD to end of file

from fantasy_sim.scoring.projections import build_kicker_projections


class TestKickerAttribution:
    """Gap 13: Kicker projections attributed to actual kicker player."""

    def test_kicker_uses_team_name_when_no_roster(self, ppr_config):
        """Without roster info, kicker is labeled as team name."""
        kicker_config = {
            "fg_0_39": 3, "fg_40_49": 4, "fg_50_plus": 5, "xp_made": 1, "fg_miss": -1,
        }
        games = [make_game_result() for _ in range(5)]
        team_map = {"HOME": "KC", "AWAY": "BUF"}
        projs = build_kicker_projections(games, kicker_config, team_map=team_map)
        # Default: team name + " K"
        names = [p["name"] for p in projs]
        assert any("KC" in n for n in names)

    def test_kicker_attributed_to_roster_player(self):
        """When roster has a kicker, projection uses the kicker's real name."""
        from fantasy_sim.models.player import TeamRoster, PlayerModel, PlayerUsage, PlayerOutcomes
        kicker_config = {
            "fg_0_39": 3, "fg_40_49": 4, "fg_50_plus": 5, "xp_made": 1, "fg_miss": -1,
        }
        games = [make_game_result() for _ in range(5)]
        home_roster = TeamRoster(team="KC", players=[
            PlayerModel("kc_k", "Harrison Butker", "K", "KC",
                       PlayerUsage(), PlayerOutcomes()),
        ])
        away_roster = TeamRoster(team="BUF", players=[
            PlayerModel("buf_k", "Tyler Bass", "K", "BUF",
                       PlayerUsage(), PlayerOutcomes()),
        ])
        team_map = {"HOME": "KC", "AWAY": "BUF"}
        projs = build_kicker_projections(
            games, kicker_config, team_map=team_map,
            home_roster=home_roster, away_roster=away_roster,
        )
        names = [p["name"] for p in projs]
        assert "Harrison Butker" in names
        assert "Tyler Bass" in names

    def test_kicker_no_k_on_roster_uses_synthetic(self):
        """When roster has no K, fall back to team name."""
        from fantasy_sim.models.player import TeamRoster, PlayerModel, PlayerUsage, PlayerOutcomes
        kicker_config = {
            "fg_0_39": 3, "fg_40_49": 4, "fg_50_plus": 5, "xp_made": 1, "fg_miss": -1,
        }
        games = [make_game_result() for _ in range(5)]
        home_roster = TeamRoster(team="KC", players=[
            PlayerModel("kc_qb", "Mahomes", "QB", "KC",
                       PlayerUsage(snap_share=1.0), PlayerOutcomes()),
        ])
        away_roster = TeamRoster(team="BUF", players=[
            PlayerModel("buf_qb", "Allen", "QB", "BUF",
                       PlayerUsage(snap_share=1.0), PlayerOutcomes()),
        ])
        team_map = {"HOME": "KC", "AWAY": "BUF"}
        projs = build_kicker_projections(
            games, kicker_config, team_map=team_map,
            home_roster=home_roster, away_roster=away_roster,
        )
        names = [p["name"] for p in projs]
        assert any("KC" in n for n in names)
        assert any("BUF" in n for n in names)
```

- [ ] **Step 2: Update build_kicker_projections to accept roster params**

```python
# src/fantasy_sim/scoring/projections.py — REPLACE build_kicker_projections

def build_kicker_projections(
    games: list[GameResult],
    scoring_config: dict,
    team_map: dict[str, str] | None = None,
    home_roster: "TeamRoster | None" = None,
    away_roster: "TeamRoster | None" = None,
) -> list[dict]:
    """Build kicker projections from team-level kicking stats.

    If rosters are provided and contain a player with position "K",
    the kicker projection is attributed to that player. Otherwise,
    a synthetic "{TEAM} K" entry is used.
    """
    if not games:
        return []

    # Import here to avoid circular imports at module level
    from fantasy_sim.models.player import TeamRoster

    home_boxes = [g.home_box for g in games]
    away_boxes = [g.away_box for g in games]

    def _find_kicker(roster: TeamRoster | None) -> tuple[str | None, str | None]:
        """Find the kicker's player_id and name from roster, if one exists."""
        if roster is None:
            return None, None
        for p in roster.players:
            if p.position == "K":
                return p.player_id, p.name
        return None, None

    projections = []
    for side, boxes, roster in [
        ("HOME", home_boxes, home_roster),
        ("AWAY", away_boxes, away_roster),
    ]:
        team_name = team_map.get(side, side) if team_map else side
        kicker_id, kicker_name = _find_kicker(roster)

        if kicker_name is None:
            kicker_name = f"{team_name} K"

        fpts_list = [score_kicker(b, scoring_config) for b in boxes]
        proj = {
            "name": kicker_name,
            "team": team_name,
            "fpts": round(float(np.mean(fpts_list)), 1),
            "fg_attempts": round(float(np.mean([b.fg_attempts for b in boxes])), 1),
            "fg_made": round(float(np.mean([b.fg_made for b in boxes])), 1),
            "fg_50_plus": round(float(np.mean([b.fg_made_50_plus for b in boxes])), 1),
            "xp_attempts": round(float(np.mean([b.xp_attempts for b in boxes])), 1),
            "xp_made": round(float(np.mean([b.xp_made for b in boxes])), 1),
        }
        if kicker_id:
            proj["player_id"] = kicker_id
            proj["position"] = "K"
        projections.append(proj)

    projections.sort(key=lambda p: p["fpts"], reverse=True)
    for i, p in enumerate(projections, 1):
        p["rank"] = i

    return projections
```

- [ ] **Step 3: Run tests and verify**

```bash
uv run pytest tests/test_scoring/test_projections.py -v
```

All existing kicker tests must still pass (they don't pass rosters, so behavior is unchanged). New `TestKickerAttribution` (3 tests) must pass.

- [ ] **Step 4: Commit**

```bash
git add src/fantasy_sim/scoring/projections.py tests/test_scoring/test_projections.py
git commit -m "feat(scoring): attribute kicker projections to roster kicker player

build_kicker_projections now accepts optional home_roster/away_roster.
When a roster contains a K-position player, projections use their
real name and player_id. Falls back to '{TEAM} K' when no kicker
is on the roster."
```

---

### Task 8: CLI Polish — Week Validation + --detail Wiring (Gaps 19, 20)

**Files:**
- Modify: `src/fantasy_sim/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing tests for --weeks validation and --detail flag**

```python
# tests/test_cli.py — ADD to end of file

class TestWeeksValidation:
    """Gap 20: Validate week numbers are 1-18."""

    def test_season_invalid_week_range(self, runner):
        """Weeks 0 or 19+ should produce a helpful error."""
        result = runner.invoke(main, ["season", "--season", "2024", "--weeks", "0-5", "--sims", "10"])
        assert result.exit_code != 0 or "invalid" in result.output.lower() or "1-18" in result.output

    def test_season_invalid_single_week(self, runner):
        result = runner.invoke(main, ["season", "--season", "2024", "--weeks", "19", "--sims", "10"])
        assert result.exit_code != 0 or "invalid" in result.output.lower() or "1-18" in result.output

    def test_season_valid_week_range(self, runner):
        """Valid range should not raise validation error (may fail on data loading)."""
        # We just check that the validation doesn't reject it
        result = runner.invoke(main, ["season", "--season", "2024", "--weeks", "1-2", "--sims", "10"])
        # It might fail on data loading, but should NOT fail on week validation
        assert "invalid week" not in result.output.lower()


class TestDetailFlag:
    """Gap 19: --detail flag on demo and game commands."""

    def test_demo_detail_flag(self, runner):
        """--detail flag should be accepted on demo."""
        result = runner.invoke(main, ["demo", "--sims", "10", "--detail"])
        assert result.exit_code == 0
        # Should show floor/ceiling columns
        assert "Flr" in result.output or "Floor" in result.output or "Ceil" in result.output

    def test_game_detail_flag(self, runner):
        """--detail flag should be accepted on game command."""
        result = runner.invoke(main, ["game", "HOME", "AWAY", "--demo", "--sims", "10", "--detail"])
        assert result.exit_code == 0
```

- [ ] **Step 2: Add week validation helper**

```python
# src/fantasy_sim/cli.py — ADD after _auto_detect_season_yaml function

def _parse_and_validate_weeks(weeks_str: str) -> list[int]:
    """Parse --weeks string and validate all week numbers are 1-18.

    Accepts: 'all', '1-5', '1,3,5,7'
    Raises click.BadParameter for invalid week numbers.
    """
    if weeks_str == "all":
        return []  # Empty signals "all" to the caller

    if "-" in weeks_str and "," not in weeks_str:
        parts = weeks_str.split("-")
        if len(parts) != 2:
            raise click.BadParameter(f"Invalid week range: '{weeks_str}'. Use format: '1-5'")
        try:
            start, end = int(parts[0]), int(parts[1])
        except ValueError:
            raise click.BadParameter(f"Invalid week range: '{weeks_str}'. Week numbers must be integers.")
        week_nums = list(range(start, end + 1))
    else:
        try:
            week_nums = [int(w.strip()) for w in weeks_str.split(",")]
        except ValueError:
            raise click.BadParameter(f"Invalid week list: '{weeks_str}'. Use format: '1,3,5'")

    # Validate range
    invalid = [w for w in week_nums if w < 1 or w > 18]
    if invalid:
        raise click.BadParameter(
            f"Invalid week number(s): {invalid}. Regular season weeks are 1-18."
        )

    return week_nums
```

- [ ] **Step 3: Update season command to use week validation**

In the `season` command body, replace the existing week parsing block:

```python
# src/fantasy_sim/cli.py — REPLACE the week-parsing block inside season()
# OLD:
#     if weeks == "all":
#         week_nums = sorted(schedules.filter(pl.col("season") == season_year)["week"].unique().to_list())
#     elif "-" in weeks:
#         start, end = weeks.split("-")
#         week_nums = list(range(int(start), int(end) + 1))
#     else:
#         week_nums = [int(w) for w in weeks.split(",")]

# NEW:
    try:
        parsed_weeks = _parse_and_validate_weeks(weeks)
    except click.BadParameter as e:
        click.echo(f"Error: {e.format_message()}", err=True)
        raise SystemExit(1)

    if not parsed_weeks:
        # "all" — get from schedule data
        week_nums = sorted(schedules.filter(pl.col("season") == season_year)["week"].unique().to_list())
    else:
        week_nums = parsed_weeks
```

- [ ] **Step 4: Add --detail flag to demo command**

Update the `demo` command to accept `--detail` and use detail formatters:

```python
# src/fantasy_sim/cli.py — ADD to demo command decorator
@click.option("--detail", is_flag=True, help="Show floor/ceiling/stddev distributions")

# In demo command body, after building projections, replace the table display block:

    if output_format == "table":
        qbs = [p for p in player_projs if p["position"] == "QB"]
        rbs = [p for p in player_projs if p["position"] == "RB"]
        wrs = [p for p in player_projs if p["position"] == "WR"]
        tes = [p for p in player_projs if p["position"] == "TE"]

        if detail:
            from fantasy_sim.scoring.projections import build_detailed_projections
            from fantasy_sim.output.tables import (
                format_qb_detail_table, format_rb_detail_table,
                format_wr_detail_table, format_te_detail_table,
            )
            player_projs = build_detailed_projections(results.games, scoring_config)
            qbs = [p for p in player_projs if p["position"] == "QB"]
            rbs = [p for p in player_projs if p["position"] == "RB"]
            wrs = [p for p in player_projs if p["position"] == "WR"]
            tes = [p for p in player_projs if p["position"] == "TE"]
            if qbs:
                click.echo(format_qb_detail_table(qbs))
            if rbs:
                click.echo(format_rb_detail_table(rbs))
            if wrs:
                click.echo(format_wr_detail_table(wrs))
            if tes:
                click.echo(format_te_detail_table(tes))
        else:
            if qbs:
                click.echo(format_qb_table(qbs))
            if rbs:
                click.echo(format_rb_table(rbs))
            if wrs:
                click.echo(format_wr_table(wrs))
            if tes:
                click.echo(format_te_table(tes))

        if kicker_projs:
            click.echo(format_kicker_table(kicker_projs))
        if dst_projs:
            click.echo(format_dst_table(dst_projs))
```

Also add `--detail` to the `week` command signature and pass it through to `_display_projections`, updating `_display_projections` to accept a `detail` parameter:

```python
# src/fantasy_sim/cli.py — UPDATE _display_projections signature and body

def _display_projections(player_projs, output_format, output_path, detail=False):
    """Display or export projections."""
    if output_format == "table":
        qbs = [p for p in player_projs if p["position"] == "QB"]
        rbs = [p for p in player_projs if p["position"] == "RB"]
        wrs = [p for p in player_projs if p["position"] == "WR"]
        tes = [p for p in player_projs if p["position"] == "TE"]

        if detail:
            from fantasy_sim.output.tables import (
                format_qb_detail_table, format_rb_detail_table,
                format_wr_detail_table, format_te_detail_table,
            )
            if qbs:
                click.echo(format_qb_detail_table(qbs[:24]))
            if rbs:
                click.echo(format_rb_detail_table(rbs[:24]))
            if wrs:
                click.echo(format_wr_detail_table(wrs[:24]))
            if tes:
                click.echo(format_te_detail_table(tes[:12]))
        else:
            if qbs:
                click.echo(format_qb_table(qbs[:24]))
            if rbs:
                click.echo(format_rb_table(rbs[:24]))
            if wrs:
                click.echo(format_wr_table(wrs[:24]))
            if tes:
                click.echo(format_te_table(tes[:12]))
    elif output_format in ("csv", "json"):
        if output_path is None:
            output_path = f"projections.{output_format}"
        if output_format == "csv":
            export_csv(player_projs, Path(output_path))
        else:
            export_json(player_projs, Path(output_path))
        click.echo(f"Exported to {output_path}")
```

Add `--detail` option to `week` and `season` commands:

```python
# Add to both week and season command decorators:
@click.option("--detail", is_flag=True, help="Show floor/ceiling/stddev distributions")
```

In `week` command body, when `--detail` is set, use `build_detailed_projections` instead of `build_player_projections`:

```python
# Inside week command's game loop, replace build_player_projections call:
            if detail:
                from fantasy_sim.scoring.projections import build_detailed_projections
                all_player_projs.extend(build_detailed_projections(results.games, scoring_config))
            else:
                all_player_projs.extend(build_player_projections(results.games, scoring_config))

# And update the _display_projections call:
    _display_projections(player_projs, output_format, output_path, detail=detail)
```

Apply the same pattern to the `season` command.

- [ ] **Step 5: Run all tests**

```bash
uv run pytest tests/test_cli.py -v
uv run pytest tests/ -v
```

All tests must pass: existing tests unchanged, new `TestWeeksValidation` (3 tests), `TestDetailFlag` (2 tests).

- [ ] **Step 6: Commit**

```bash
git add src/fantasy_sim/cli.py tests/test_cli.py
git commit -m "feat(cli): add --detail flag, --weeks validation, wire config chain

--detail flag on demo/week/season/game shows floor/ceiling/stddev.
--weeks validates 1-18 range with helpful error messages.
week/season commands auto-detect season.yaml and use defaults.yaml
for num_sims and training seasons."
```

---

## Post-Implementation Verification

After all 8 tasks are complete:

- [ ] **Full test suite passes:**

```bash
uv run pytest tests/ -v
```

- [ ] **Demo commands work end-to-end:**

```bash
# Basic demo
uv run fantasy-sim demo --sims 20

# Demo with detail
uv run fantasy-sim demo --sims 20 --detail

# Game command
uv run fantasy-sim game HOME AWAY --demo --sims 20
uv run fantasy-sim game HOME AWAY --demo --sims 20 --detail

# Player command
uv run fantasy-sim player HOME_QB --demo --sims 20

# Custom scoring
uv run fantasy-sim demo --sims 20 --scoring-config config/custom_scoring.example.yaml
```

- [ ] **Update CLAUDE.md** with new commands and features:

Add to the Commands section:
```
# Game command (single-game deep dive)
uv run fantasy-sim game KC BUF --week 5 --sims 100
uv run fantasy-sim game HOME AWAY --demo --sims 100

# Player command (single-player projection)
uv run fantasy-sim player "nico_collins" --week 5 --sims 100

# Detail mode (floor/ceiling/stddev)
uv run fantasy-sim demo --sims 100 --detail
uv run fantasy-sim week 1 --detail

# Custom scoring
uv run fantasy-sim week 1 --scoring-config config/custom_scoring.yaml
```

Add to Current State:
```
- **Phase 7B (Scoring + Config + CLI)**: Complete — N tests (total)
```

Add to Key Patterns:
```
- **ScoringEngine**: Position-specific reception keys (reception_wr, reception_te) override generic. Yardage bonus keys (rushing_bonus_100, passing_bonus_300) stack at each threshold.
- **CustomScoring**: load_custom_scoring(path, presets) reads inherit + overrides format. _resolve_config_chain() merges defaults → season.yaml → --scoring-config.
- **DetailedProjections**: build_detailed_projections(games, config) returns projections with fpts_floor/ceiling/stddev and stat distributions. Detail tables add Flr/Ceil/SD columns.
```

- [ ] **Update README.md** with new CLI commands and scoring features.

---

## Summary

| Task | Gaps | Files Modified | New Tests |
|------|------|----------------|-----------|
| 1. Scoring improvements | 11, 12 | scoring/engine.py | ~13 |
| 2. Config integration | 14, 15, 16 | config/loader.py, cli.py | ~9 |
| 3. Detailed projections | 19, 21 | scoring/projections.py | ~7 |
| 4. Detail tables | 19, 21 | output/tables.py | ~5 |
| 5. `game` command | 17 | cli.py | ~4 |
| 6. `player` command | 18 | cli.py | ~4 |
| 7. Kicker attribution | 13 | scoring/projections.py | ~3 |
| 8. CLI polish | 19, 20 | cli.py | ~5 |
| **Total** | **11 gaps** | **6 files** | **~50 tests** |

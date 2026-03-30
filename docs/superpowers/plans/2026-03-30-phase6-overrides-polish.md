# Phase 6: Overrides + Polish — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the player and team override system (target share, carry share, games missed, pass rate, pace) with usage share redistribution, wire overrides into the CLI via `--override` flags and `season.yaml` config, add progress bars and error messages, and finalize documentation.

**Architecture:** An `OverrideEngine` applies player and team overrides to `TeamRoster` and `TeamDistributions` objects after they're built from data but before simulation runs. Player usage overrides trigger proportional redistribution to teammates. A `PlayerResolver` handles fuzzy name matching (CLI names → nflverse player IDs). Overrides can come from a YAML config file (`season.yaml`) or CLI `--override` flags, merged in resolution order. `GameContextBuilder.build_game()` gains an optional `overrides` parameter that applies all overrides before returning.

**Tech Stack:** Python 3.14, click, pyyaml, rich (progress bars), thefuzz (fuzzy matching), pytest

---

## File Structure

```
config/
└── season.example.yaml        NEW: Example season config with overrides

src/fantasy_sim/
├── overrides/
│   ├── __init__.py             NEW
│   ├── engine.py               NEW: apply_player_overrides, apply_team_overrides, redistribute_shares
│   ├── resolver.py             NEW: PlayerResolver — fuzzy name → player_id matching
│   └── parser.py               NEW: parse_override_config, parse_cli_overrides
├── data/
│   └── game_context.py         MODIFY: Add overrides parameter to build_game
└── cli.py                      MODIFY: Add --override and --config flags, progress bars

tests/
├── test_overrides/
│   ├── test_engine.py          NEW
│   ├── test_resolver.py        NEW
│   └── test_parser.py          NEW
└── test_cli.py                 MODIFY: Add override CLI tests
```

## Dependencies from Phases 1-5

- `models.player.PlayerModel` — `usage: PlayerUsage` (carry_share, target_share, etc.), `games_played: int`
- `models.player.PlayerUsage` — fields: carry_share, red_zone_carry_share, target_share, red_zone_target_share, snap_share, scramble_rate
- `models.player.TeamRoster` — `players: list[PlayerModel]`, `team: str`
- `models.distributions.PlayCallingDist` — `default: dict[str, float]` (e.g., `{"pass": 0.57, "run": 0.43}`)
- `models.distributions.TurnoverRates` — `int_rate`, `fumble_rate`, `sack_rate`, `sack_fumble_rate`
- `engine.types.TeamDistributions` — bundles PlayCallingDist, PlayOutcomeDist, TurnoverRates, KickingModel, DriveStartModel
- `data.game_context.GameContextBuilder.build_game()` — returns `(TeamDistributions, TeamDistributions, TeamRoster, TeamRoster)`
- `data.loader.DataLoader.load_rosters()` — provides roster data for player name resolution

---

### Task 1: Override Engine (Player Overrides + Redistribution)

**Files:**
- Create: `src/fantasy_sim/overrides/__init__.py`
- Create: `src/fantasy_sim/overrides/engine.py`
- Create: `tests/test_overrides/test_engine.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_overrides/test_engine.py
import numpy as np
import pytest
from copy import deepcopy
from fantasy_sim.overrides.engine import (
    apply_player_override,
    apply_team_override,
    redistribute_target_shares,
    redistribute_carry_shares,
)
from fantasy_sim.models.player import (
    PlayerModel, PlayerUsage, PlayerOutcomes, TeamRoster,
)
from fantasy_sim.engine.types import TeamDistributions
from fantasy_sim.models.distributions import (
    PlayCallingDist, PlayOutcomeDist, TurnoverRates, KickingModel, DriveStartModel,
)


def make_roster() -> TeamRoster:
    return TeamRoster(team="KC", players=[
        PlayerModel("QB1", "Mahomes", "QB", "KC",
                    PlayerUsage(snap_share=1.0), PlayerOutcomes()),
        PlayerModel("WR1", "Worthy", "WR", "KC",
                    PlayerUsage(target_share=0.24, red_zone_target_share=0.22),
                    PlayerOutcomes(catch_rate=0.63, receiving_yards_dist=np.array([8, 12]))),
        PlayerModel("WR2", "Rice", "WR", "KC",
                    PlayerUsage(target_share=0.18),
                    PlayerOutcomes(catch_rate=0.60, receiving_yards_dist=np.array([7, 10]))),
        PlayerModel("TE1", "Kelce", "TE", "KC",
                    PlayerUsage(target_share=0.22),
                    PlayerOutcomes(catch_rate=0.68, receiving_yards_dist=np.array([5, 10]))),
        PlayerModel("RB1", "Pacheco", "RB", "KC",
                    PlayerUsage(carry_share=0.60, target_share=0.10),
                    PlayerOutcomes(rushing_yards_dist=np.array([3, 5, 7]),
                                  catch_rate=0.72, receiving_yards_dist=np.array([4, 6]))),
        PlayerModel("RB2", "Clyde", "RB", "KC",
                    PlayerUsage(carry_share=0.30, target_share=0.05),
                    PlayerOutcomes(rushing_yards_dist=np.array([2, 4]))),
    ])


def make_dists() -> TeamDistributions:
    return TeamDistributions(
        play_calling=PlayCallingDist(team="KC", distributions={}, default={"pass": 0.57, "run": 0.43}),
        play_outcomes=PlayOutcomeDist(distributions={}, defaults={
            "pass": np.array([5, 10]), "run": np.array([3, 5])}),
        turnover_rates=TurnoverRates(team="KC", int_rate=0.025, fumble_rate=0.012, sack_rate=0.065, sack_fumble_rate=0.10),
        kicking=KickingModel(fg_make_rate={"0_39": 0.93, "40_49": 0.82, "50_plus": 0.65}, xp_rate=0.94),
        drive_start=DriveStartModel(touchback_rate=0.55, touchback_yardline=75, return_yardlines=np.array([74, 76])),
    )


class TestApplyPlayerOverride:
    def test_override_target_share(self):
        roster = make_roster()
        apply_player_override(roster, "WR1", {"target_share": 0.30})
        wr1 = next(p for p in roster.players if p.player_id == "WR1")
        assert wr1.usage.target_share == pytest.approx(0.30)

    def test_override_carry_share(self):
        roster = make_roster()
        apply_player_override(roster, "RB1", {"carry_share": 0.75})
        rb1 = next(p for p in roster.players if p.player_id == "RB1")
        assert rb1.usage.carry_share == pytest.approx(0.75)

    def test_override_games_played(self):
        roster = make_roster()
        apply_player_override(roster, "WR1", {"games_played": 14})
        wr1 = next(p for p in roster.players if p.player_id == "WR1")
        assert wr1.games_played == 14

    def test_override_games_missed(self):
        roster = make_roster()
        apply_player_override(roster, "QB1", {"games_missed": [4, 5, 6]})
        qb = next(p for p in roster.players if p.player_id == "QB1")
        assert qb.games_played == 14  # 17 - 3

    def test_unknown_player_raises(self):
        roster = make_roster()
        with pytest.raises(KeyError):
            apply_player_override(roster, "FAKE_ID", {"target_share": 0.30})

    def test_unknown_field_raises(self):
        roster = make_roster()
        with pytest.raises(ValueError):
            apply_player_override(roster, "WR1", {"nonexistent_field": 0.5})


class TestRedistributeTargetShares:
    def test_increase_redistributes_to_teammates(self):
        roster = make_roster()
        # WR1 goes from 0.24 to 0.30 (+0.06)
        # Others: WR2=0.18, TE1=0.22, RB1=0.10, RB2=0.05 (sum=0.55)
        redistribute_target_shares(roster, "WR1", old_share=0.24, new_share=0.30)
        wr2 = next(p for p in roster.players if p.player_id == "WR2")
        te1 = next(p for p in roster.players if p.player_id == "TE1")
        rb1 = next(p for p in roster.players if p.player_id == "RB1")
        rb2 = next(p for p in roster.players if p.player_id == "RB2")
        # All others should decrease
        assert wr2.usage.target_share < 0.18
        assert te1.usage.target_share < 0.22
        # Total target shares should still sum to ~0.79 (original sum)
        total = 0.30 + wr2.usage.target_share + te1.usage.target_share + rb1.usage.target_share + rb2.usage.target_share
        assert total == pytest.approx(0.79, abs=0.01)

    def test_decrease_redistributes_to_teammates(self):
        roster = make_roster()
        redistribute_target_shares(roster, "WR1", old_share=0.24, new_share=0.18)
        wr2 = next(p for p in roster.players if p.player_id == "WR2")
        # WR2 should increase (got some of the freed share)
        assert wr2.usage.target_share > 0.18


class TestRedistributeCarryShares:
    def test_increase_redistributes(self):
        roster = make_roster()
        redistribute_carry_shares(roster, "RB1", old_share=0.60, new_share=0.75)
        rb2 = next(p for p in roster.players if p.player_id == "RB2")
        assert rb2.usage.carry_share < 0.30
        # Total should still be ~0.90
        total = 0.75 + rb2.usage.carry_share
        assert total == pytest.approx(0.90, abs=0.01)


class TestApplyTeamOverride:
    def test_override_pass_rate(self):
        dists = make_dists()
        apply_team_override(dists, {"pass_rate": 0.65})
        assert dists.play_calling.default["pass"] == pytest.approx(0.65)
        assert dists.play_calling.default["run"] == pytest.approx(0.35)

    def test_override_sack_rate(self):
        dists = make_dists()
        apply_team_override(dists, {"sack_rate": 0.08})
        assert dists.turnover_rates.sack_rate == pytest.approx(0.08)

    def test_override_int_rate(self):
        dists = make_dists()
        apply_team_override(dists, {"int_rate": 0.03})
        assert dists.turnover_rates.int_rate == pytest.approx(0.03)

    def test_stacking_player_and_team_overrides(self):
        """Player + team overrides on same team should not conflict."""
        roster = make_roster()
        dists = make_dists()
        apply_player_override(roster, "WR1", {"target_share": 0.30})
        apply_team_override(dists, {"pass_rate": 0.65})
        wr1 = next(p for p in roster.players if p.player_id == "WR1")
        assert wr1.usage.target_share == pytest.approx(0.30)
        assert dists.play_calling.default["pass"] == pytest.approx(0.65)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_overrides/test_engine.py -v`
Expected: FAIL

- [ ] **Step 3: Implement override engine**

```python
# src/fantasy_sim/overrides/__init__.py
```

```python
# src/fantasy_sim/overrides/engine.py
from fantasy_sim.models.player import TeamRoster, PlayerModel
from fantasy_sim.engine.types import TeamDistributions
from fantasy_sim.models.distributions import PlayCallingDist, TurnoverRates

# Valid player override fields
PLAYER_USAGE_FIELDS = {
    "target_share", "carry_share", "red_zone_target_share",
    "red_zone_carry_share", "snap_share", "scramble_rate",
}
PLAYER_OUTCOME_FIELDS = {"catch_rate", "fumble_rate"}
PLAYER_META_FIELDS = {"games_played", "games_missed"}

# Valid team override fields
TEAM_OVERRIDE_FIELDS = {
    "pass_rate", "int_rate", "fumble_rate", "sack_rate", "sack_fumble_rate",
    "pace_plays_per_game",
}


def apply_player_override(
    roster: TeamRoster, player_id: str, overrides: dict
) -> None:
    """Apply overrides to a specific player in the roster. Mutates in place."""
    player = None
    for p in roster.players:
        if p.player_id == player_id:
            player = p
            break
    if player is None:
        raise KeyError(f"Player '{player_id}' not found in {roster.team} roster")

    for field, value in overrides.items():
        if field in PLAYER_USAGE_FIELDS:
            old_value = getattr(player.usage, field)
            setattr(player.usage, field, value)
            # Trigger redistribution for share fields
            if field == "target_share":
                redistribute_target_shares(roster, player_id, old_value, value)
            elif field == "carry_share":
                redistribute_carry_shares(roster, player_id, old_value, value)
        elif field in PLAYER_OUTCOME_FIELDS:
            setattr(player.outcomes, field, value)
        elif field == "games_played":
            player.games_played = value
        elif field == "games_missed":
            # games_missed is a list of week numbers; convert to games_played
            player.games_played = 17 - len(value)
        else:
            raise ValueError(
                f"Unknown override field '{field}'. "
                f"Valid: {PLAYER_USAGE_FIELDS | PLAYER_OUTCOME_FIELDS | PLAYER_META_FIELDS}"
            )


def redistribute_target_shares(
    roster: TeamRoster, changed_id: str, old_share: float, new_share: float
) -> None:
    """Redistribute target share delta proportionally to eligible teammates."""
    delta = new_share - old_share  # positive = increased, negative = decreased

    # Eligible: all players with target_share > 0 except the changed player
    eligible = [
        p for p in roster.players
        if p.player_id != changed_id and p.usage.target_share > 0
    ]
    if not eligible or delta == 0:
        return

    total_eligible = sum(p.usage.target_share for p in eligible)
    if total_eligible == 0:
        return

    for p in eligible:
        proportion = p.usage.target_share / total_eligible
        adjustment = -delta * proportion  # If WR1 increased, others decrease
        p.usage.target_share = max(0.0, p.usage.target_share + adjustment)


def redistribute_carry_shares(
    roster: TeamRoster, changed_id: str, old_share: float, new_share: float
) -> None:
    """Redistribute carry share delta proportionally to eligible teammates."""
    delta = new_share - old_share

    eligible = [
        p for p in roster.players
        if p.player_id != changed_id and p.usage.carry_share > 0
    ]
    if not eligible or delta == 0:
        return

    total_eligible = sum(p.usage.carry_share for p in eligible)
    if total_eligible == 0:
        return

    for p in eligible:
        proportion = p.usage.carry_share / total_eligible
        adjustment = -delta * proportion
        p.usage.carry_share = max(0.0, p.usage.carry_share + adjustment)


def apply_team_override(dists: TeamDistributions, overrides: dict) -> None:
    """Apply team-level overrides to distributions. Mutates in place."""
    for field, value in overrides.items():
        if field == "pass_rate":
            dists.play_calling = PlayCallingDist(
                team=dists.play_calling.team,
                distributions=dists.play_calling.distributions,
                default={"pass": value, "run": 1.0 - value},
            )
        elif field == "int_rate":
            dists.turnover_rates = TurnoverRates(
                team=dists.turnover_rates.team,
                int_rate=value,
                fumble_rate=dists.turnover_rates.fumble_rate,
                sack_rate=dists.turnover_rates.sack_rate,
                sack_fumble_rate=dists.turnover_rates.sack_fumble_rate,
            )
        elif field == "fumble_rate":
            dists.turnover_rates = TurnoverRates(
                team=dists.turnover_rates.team,
                int_rate=dists.turnover_rates.int_rate,
                fumble_rate=value,
                sack_rate=dists.turnover_rates.sack_rate,
                sack_fumble_rate=dists.turnover_rates.sack_fumble_rate,
            )
        elif field == "sack_rate":
            dists.turnover_rates = TurnoverRates(
                team=dists.turnover_rates.team,
                int_rate=dists.turnover_rates.int_rate,
                fumble_rate=dists.turnover_rates.fumble_rate,
                sack_rate=value,
                sack_fumble_rate=dists.turnover_rates.sack_fumble_rate,
            )
        elif field == "sack_fumble_rate":
            dists.turnover_rates = TurnoverRates(
                team=dists.turnover_rates.team,
                int_rate=dists.turnover_rates.int_rate,
                fumble_rate=dists.turnover_rates.fumble_rate,
                sack_rate=dists.turnover_rates.sack_rate,
                sack_fumble_rate=value,
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_overrides/test_engine.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/overrides/ tests/test_overrides/test_engine.py
git commit -m "feat: add override engine with player/team overrides and share redistribution"
```

---

### Task 2: Player Name Resolver (Fuzzy Matching)

**Files:**
- Create: `src/fantasy_sim/overrides/resolver.py`
- Create: `tests/test_overrides/test_resolver.py`

- [ ] **Step 1: Add thefuzz to dependencies**

Add `"thefuzz>=0.22.0"` to the `dependencies` list in `pyproject.toml`, then run:

```bash
uv pip install -e ".[dev]"
```

- [ ] **Step 2: Write failing tests**

```python
# tests/test_overrides/test_resolver.py
import pytest
from fantasy_sim.overrides.resolver import PlayerResolver
from fantasy_sim.models.player import (
    PlayerModel, PlayerUsage, PlayerOutcomes, TeamRoster,
)


def make_roster() -> TeamRoster:
    return TeamRoster(team="KC", players=[
        PlayerModel("PM15", "Patrick Mahomes", "QB", "KC", PlayerUsage(), PlayerOutcomes()),
        PlayerModel("TK87", "Travis Kelce", "TE", "KC", PlayerUsage(), PlayerOutcomes()),
        PlayerModel("RE11", "Rashee Rice", "WR", "KC", PlayerUsage(), PlayerOutcomes()),
        PlayerModel("IP01", "Isiah Pacheco", "RB", "KC", PlayerUsage(), PlayerOutcomes()),
    ])


@pytest.fixture
def resolver():
    rosters = [make_roster()]
    return PlayerResolver(rosters)


class TestPlayerResolver:
    def test_exact_id_match(self, resolver):
        pid = resolver.resolve("PM15")
        assert pid == "PM15"

    def test_exact_name_match(self, resolver):
        pid = resolver.resolve("Patrick Mahomes")
        assert pid == "PM15"

    def test_fuzzy_name_match(self, resolver):
        pid = resolver.resolve("mahomes")
        assert pid == "PM15"

    def test_underscore_name(self, resolver):
        pid = resolver.resolve("patrick_mahomes")
        assert pid == "PM15"

    def test_partial_name(self, resolver):
        pid = resolver.resolve("kelce")
        assert pid == "TK87"

    def test_no_match_raises(self, resolver):
        with pytest.raises(KeyError):
            resolver.resolve("totally_unknown_player")

    def test_case_insensitive(self, resolver):
        pid = resolver.resolve("TRAVIS KELCE")
        assert pid == "TK87"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_overrides/test_resolver.py -v`
Expected: FAIL

- [ ] **Step 4: Implement player resolver**

```python
# src/fantasy_sim/overrides/resolver.py
from thefuzz import fuzz
from fantasy_sim.models.player import TeamRoster

# Minimum fuzzy match score to accept (0-100)
MIN_MATCH_SCORE = 70


class PlayerResolver:
    """Resolve player names/IDs to nflverse player_id values."""

    def __init__(self, rosters: list[TeamRoster]):
        self._id_map: dict[str, str] = {}  # player_id → player_id (identity)
        self._name_map: dict[str, str] = {}  # lowercase name → player_id
        self._all_names: list[tuple[str, str]] = []  # (name, player_id) for fuzzy

        for roster in rosters:
            for player in roster.players:
                self._id_map[player.player_id] = player.player_id
                name_lower = player.name.lower()
                self._name_map[name_lower] = player.player_id
                self._all_names.append((player.name, player.player_id))

    def resolve(self, query: str) -> str:
        """Resolve a player query to a player_id.

        Tries in order:
        1. Exact player_id match
        2. Exact name match (case-insensitive)
        3. Underscore-to-space conversion
        4. Fuzzy name match

        Raises KeyError if no match found.
        """
        # 1. Exact ID
        if query in self._id_map:
            return self._id_map[query]

        # 2. Exact name (case-insensitive)
        query_lower = query.lower()
        if query_lower in self._name_map:
            return self._name_map[query_lower]

        # 3. Underscore conversion
        query_spaces = query_lower.replace("_", " ")
        if query_spaces in self._name_map:
            return self._name_map[query_spaces]

        # 4. Fuzzy match
        best_score = 0
        best_id = None
        for name, pid in self._all_names:
            score = max(
                fuzz.ratio(query_lower, name.lower()),
                fuzz.partial_ratio(query_lower, name.lower()),
            )
            if score > best_score:
                best_score = score
                best_id = pid

        if best_score >= MIN_MATCH_SCORE and best_id is not None:
            return best_id

        raise KeyError(
            f"No player found matching '{query}'. "
            f"Best match score: {best_score}/100 (need {MIN_MATCH_SCORE}+)"
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_overrides/test_resolver.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/fantasy_sim/overrides/resolver.py tests/test_overrides/test_resolver.py
git commit -m "feat: add fuzzy player name resolver for CLI overrides"
```

---

### Task 3: Override Config Parser

**Files:**
- Create: `src/fantasy_sim/overrides/parser.py`
- Create: `tests/test_overrides/test_parser.py`
- Create: `config/season.example.yaml`

- [ ] **Step 1: Create example season config**

```yaml
# config/season.example.yaml
# Copy to config/season.yaml and customize for your league.

season: 2025
weeks: all
scoring_format: ppr

# Team-level overrides
teams:
  KC:
    pass_rate: 0.62
  BUF:
    pass_rate: 0.58

# Player-level overrides (use player names or nflverse player_id)
players:
  patrick_mahomes:
    games_missed: [4, 5, 6]
  nico_collins:
    target_share: 0.28
  bijan_robinson:
    carry_share: 0.72
    red_zone_carry_share: 0.80
```

- [ ] **Step 2: Write failing tests**

```python
# tests/test_overrides/test_parser.py
import pytest
from pathlib import Path
from fantasy_sim.overrides.parser import (
    parse_override_config,
    parse_cli_override,
    OverrideSet,
)


class TestParseOverrideConfig:
    def test_parses_player_overrides(self, tmp_path):
        config = tmp_path / "season.yaml"
        config.write_text("""
season: 2025
players:
  WR1:
    target_share: 0.28
  RB1:
    carry_share: 0.75
""")
        result = parse_override_config(config)
        assert isinstance(result, OverrideSet)
        assert "WR1" in result.players
        assert result.players["WR1"]["target_share"] == 0.28

    def test_parses_team_overrides(self, tmp_path):
        config = tmp_path / "season.yaml"
        config.write_text("""
season: 2025
teams:
  KC:
    pass_rate: 0.62
""")
        result = parse_override_config(config)
        assert "KC" in result.teams
        assert result.teams["KC"]["pass_rate"] == 0.62

    def test_empty_config_returns_empty_overrides(self, tmp_path):
        config = tmp_path / "season.yaml"
        config.write_text("season: 2025\n")
        result = parse_override_config(config)
        assert len(result.players) == 0
        assert len(result.teams) == 0

    def test_parses_games_missed(self, tmp_path):
        config = tmp_path / "season.yaml"
        config.write_text("""
season: 2025
players:
  QB1:
    games_missed: [4, 5, 6]
""")
        result = parse_override_config(config)
        assert result.players["QB1"]["games_missed"] == [4, 5, 6]


class TestParseCLIOverride:
    def test_player_override(self):
        result = parse_cli_override("mahomes.target_share=0.30")
        assert result == ("mahomes", "target_share", 0.30)

    def test_player_override_integer(self):
        result = parse_cli_override("mahomes.games_played=14")
        assert result == ("mahomes", "games_played", 14)

    def test_team_override(self):
        result = parse_cli_override("KC.pass_rate=0.65")
        assert result == ("KC", "pass_rate", 0.65)

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError):
            parse_cli_override("invalid_no_equals")

    def test_invalid_format_no_dot_raises(self):
        with pytest.raises(ValueError):
            parse_cli_override("nodot=0.5")
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_overrides/test_parser.py -v`
Expected: FAIL

- [ ] **Step 4: Implement parser**

```python
# src/fantasy_sim/overrides/parser.py
from dataclasses import dataclass, field
from pathlib import Path
import yaml


@dataclass
class OverrideSet:
    """Parsed overrides ready to apply."""
    players: dict[str, dict] = field(default_factory=dict)  # player_name/id → {field: value}
    teams: dict[str, dict] = field(default_factory=dict)    # team_abbr → {field: value}


def parse_override_config(path: Path) -> OverrideSet:
    """Parse a season.yaml config file into an OverrideSet."""
    with open(path) as f:
        config = yaml.safe_load(f) or {}

    result = OverrideSet()

    players = config.get("players", {})
    if players:
        for name, overrides in players.items():
            result.players[str(name)] = dict(overrides)

    teams = config.get("teams", {})
    if teams:
        for team, overrides in teams.items():
            result.teams[str(team)] = dict(overrides)

    return result


def parse_cli_override(override_str: str) -> tuple[str, str, float | int | list]:
    """Parse a CLI override string like 'mahomes.target_share=0.30'.

    Returns: (entity_name, field_name, value)
    """
    if "=" not in override_str:
        raise ValueError(
            f"Invalid override format: '{override_str}'. "
            f"Expected: 'name.field=value'"
        )

    key, value_str = override_str.split("=", 1)

    if "." not in key:
        raise ValueError(
            f"Invalid override key: '{key}'. "
            f"Expected: 'player_name.field' or 'TEAM.field'"
        )

    entity, field_name = key.rsplit(".", 1)

    # Parse value
    try:
        if "." in value_str:
            value = float(value_str)
        else:
            value = int(value_str)
    except ValueError:
        # Try as list (e.g., "[1,2,3]")
        if value_str.startswith("[") and value_str.endswith("]"):
            value = [int(x.strip()) for x in value_str[1:-1].split(",")]
        else:
            value = value_str

    return entity, field_name, value
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_overrides/test_parser.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add config/season.example.yaml src/fantasy_sim/overrides/parser.py tests/test_overrides/test_parser.py
git commit -m "feat: add override config parser and CLI override parsing"
```

---

### Task 4: Wire Overrides into GameContextBuilder + CLI

**Files:**
- Modify: `src/fantasy_sim/data/game_context.py`
- Modify: `src/fantasy_sim/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_cli.py`:

```python
class TestOverrideCLI:
    def test_override_flag_accepted(self, runner):
        result = runner.invoke(main, ["demo", "--sims", "10", "--override", "HOME_WR1.target_share=0.30"])
        assert result.exit_code == 0

    def test_config_flag_accepted(self, runner, tmp_path):
        config = tmp_path / "season.yaml"
        config.write_text("season: 2025\nplayers:\n  HOME_WR1:\n    target_share: 0.30\n")
        result = runner.invoke(main, ["demo", "--sims", "10", "--config", str(config)])
        assert result.exit_code == 0

    def test_multiple_overrides(self, runner):
        result = runner.invoke(main, [
            "demo", "--sims", "10",
            "--override", "HOME_WR1.target_share=0.30",
            "--override", "HOME_RB1.carry_share=0.75",
        ])
        assert result.exit_code == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py::TestOverrideCLI -v`
Expected: FAIL

- [ ] **Step 3: Add apply_overrides helper to game_context.py**

Add to `src/fantasy_sim/data/game_context.py`:

```python
from fantasy_sim.overrides.parser import OverrideSet
from fantasy_sim.overrides.engine import apply_player_override, apply_team_override
from fantasy_sim.overrides.resolver import PlayerResolver


def apply_overrides(
    overrides: OverrideSet,
    home_dists: TeamDistributions,
    away_dists: TeamDistributions,
    home_roster: TeamRoster,
    away_roster: TeamRoster,
) -> None:
    """Apply player and team overrides to distributions and rosters. Mutates in place."""
    # Build resolver from both rosters
    resolver = PlayerResolver([home_roster, away_roster])

    # Apply team overrides
    for team, team_overrides in overrides.teams.items():
        if team == home_roster.team:
            apply_team_override(home_dists, team_overrides)
        elif team == away_roster.team:
            apply_team_override(away_dists, team_overrides)

    # Apply player overrides
    for player_query, player_overrides in overrides.players.items():
        try:
            player_id = resolver.resolve(player_query)
        except KeyError:
            continue  # Skip unresolvable players

        # Find which roster the player is on
        for roster in [home_roster, away_roster]:
            if any(p.player_id == player_id for p in roster.players):
                apply_player_override(roster, player_id, player_overrides)
                break
```

- [ ] **Step 4: Add --override and --config flags to CLI commands**

Update `demo`, `week`, and `season` commands in `src/fantasy_sim/cli.py` to accept override options. Add to each command:

```python
@click.option("--override", "overrides", multiple=True, help="Player/team override: 'name.field=value'")
@click.option("--config", "config_path", default=None, help="Path to season.yaml with overrides")
```

Add a helper function to merge CLI overrides with config file overrides:

```python
from fantasy_sim.overrides.parser import parse_override_config, parse_cli_override, OverrideSet
from fantasy_sim.data.game_context import apply_overrides as apply_overrides_fn


def _build_overrides(overrides: tuple[str, ...], config_path: str | None) -> OverrideSet:
    """Merge overrides from config file and CLI flags."""
    result = OverrideSet()

    # Load config file overrides first
    if config_path is not None:
        result = parse_override_config(Path(config_path))

    # CLI overrides take precedence
    for override_str in overrides:
        entity, field_name, value = parse_cli_override(override_str)
        # Determine if it's a team (all-caps, 2-3 chars) or player
        if entity.isupper() and len(entity) <= 3:
            if entity not in result.teams:
                result.teams[entity] = {}
            result.teams[entity][field_name] = value
        else:
            if entity not in result.players:
                result.players[entity] = {}
            result.players[entity][field_name] = value

    return result
```

In the `demo` command, after building rosters but before running simulations, apply overrides:

```python
    override_set = _build_overrides(overrides, config_path)
    if override_set.players or override_set.teams:
        apply_overrides_fn(override_set, home_dists, away_dists, home_roster, away_roster)
```

Apply the same pattern to `week` and `season` commands — apply overrides after `builder.build_game()` returns.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -v`
Expected: All PASS

- [ ] **Step 6: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
git add src/fantasy_sim/data/game_context.py src/fantasy_sim/cli.py tests/test_cli.py
git commit -m "feat: wire overrides into CLI with --override and --config flags"
```

---

### Task 5: Progress Bars + Error Messages

**Files:**
- Modify: `src/fantasy_sim/cli.py`

- [ ] **Step 1: Add rich progress bars to CLI commands**

Update the `week` command to use `rich.progress`:

```python
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn


# In the week command, replace the game loop with:
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
    ) as progress:
        task = progress.add_task("Simulating games...", total=week_games.shape[0])
        for game in week_games.iter_rows(named=True):
            home, away = game["home_team"], game["away_team"]
            progress.update(task, description=f"{away} @ {home}")
            # ... simulation code ...
            progress.advance(task)
```

Apply the same pattern to the `season` command (progress per week).

- [ ] **Step 2: Add helpful error messages**

Add error handling to CLI commands for common issues:

```python
# In week command, wrap the main logic:
    try:
        schedules = loader.load_schedules([season])
    except Exception as e:
        click.echo(f"Error loading schedule data: {e}", err=True)
        click.echo("Try running: uv run python scripts/validate_data.py", err=True)
        raise SystemExit(1)

    if week_games.shape[0] == 0:
        click.echo(f"No games found for {season} Week {week_num}.")
        click.echo(f"Available weeks: {sorted(schedules['week'].unique().to_list())}")
        raise SystemExit(1)
```

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add src/fantasy_sim/cli.py
git commit -m "feat: add progress bars and helpful error messages to CLI"
```

---

### Task 6: Integration Tests + Documentation

**Files:**
- Create: `tests/test_overrides/test_integration.py`

- [ ] **Step 1: Write override integration tests**

```python
# tests/test_overrides/test_integration.py
import numpy as np
import pytest
from fantasy_sim.overrides.engine import apply_player_override, apply_team_override
from fantasy_sim.overrides.parser import OverrideSet
from fantasy_sim.data.game_context import apply_overrides
from fantasy_sim.models.player import (
    PlayerModel, PlayerUsage, PlayerOutcomes, TeamRoster,
)
from fantasy_sim.engine.types import TeamDistributions
from fantasy_sim.models.distributions import (
    PlayCallingDist, PlayOutcomeDist, TurnoverRates, KickingModel, DriveStartModel,
)


def make_roster(team="KC"):
    return TeamRoster(team=team, players=[
        PlayerModel(f"{team}_QB", "QB", "QB", team,
                    PlayerUsage(snap_share=1.0), PlayerOutcomes()),
        PlayerModel(f"{team}_WR1", "WR1", "WR", team,
                    PlayerUsage(target_share=0.25),
                    PlayerOutcomes(catch_rate=0.63, receiving_yards_dist=np.array([8, 12]))),
        PlayerModel(f"{team}_WR2", "WR2", "WR", team,
                    PlayerUsage(target_share=0.20),
                    PlayerOutcomes(catch_rate=0.60, receiving_yards_dist=np.array([7, 10]))),
        PlayerModel(f"{team}_RB1", "RB1", "RB", team,
                    PlayerUsage(carry_share=0.60, target_share=0.10),
                    PlayerOutcomes(rushing_yards_dist=np.array([3, 5, 7]))),
        PlayerModel(f"{team}_RB2", "RB2", "RB", team,
                    PlayerUsage(carry_share=0.30, target_share=0.05),
                    PlayerOutcomes(rushing_yards_dist=np.array([2, 4]))),
    ])


def make_dists(team="KC"):
    return TeamDistributions(
        play_calling=PlayCallingDist(team=team, distributions={}, default={"pass": 0.57, "run": 0.43}),
        play_outcomes=PlayOutcomeDist(distributions={}, defaults={
            "pass": np.array([5, 10]), "run": np.array([3, 5])}),
        turnover_rates=TurnoverRates(team=team, int_rate=0.025, fumble_rate=0.012, sack_rate=0.065, sack_fumble_rate=0.10),
        kicking=KickingModel(fg_make_rate={"0_39": 0.93, "40_49": 0.82, "50_plus": 0.65}, xp_rate=0.94),
        drive_start=DriveStartModel(touchback_rate=0.55, touchback_yardline=75, return_yardlines=np.array([74, 76])),
    )


class TestOverrideIntegration:
    def test_target_share_override_redistributes(self):
        """Spec test: player target share override redistributes to teammates."""
        roster = make_roster()
        original_total = sum(p.usage.target_share for p in roster.players)
        apply_player_override(roster, "KC_WR1", {"target_share": 0.30})
        new_total = sum(p.usage.target_share for p in roster.players)
        assert new_total == pytest.approx(original_total, abs=0.01)

    def test_games_missed_reduces_games_played(self):
        """Spec test: games_missed override reduces games_played."""
        roster = make_roster()
        apply_player_override(roster, "KC_QB", {"games_missed": [4, 5, 6]})
        qb = next(p for p in roster.players if p.player_id == "KC_QB")
        assert qb.games_played == 14

    def test_team_pass_rate_shifts_balance(self):
        """Spec test: team pass rate override shifts run/pass balance."""
        dists = make_dists()
        apply_team_override(dists, {"pass_rate": 0.65})
        assert dists.play_calling.default["pass"] == pytest.approx(0.65)
        assert dists.play_calling.default["run"] == pytest.approx(0.35)

    def test_stacking_player_and_team_no_conflict(self):
        """Spec test: stacking player + team overrides doesn't conflict."""
        roster = make_roster()
        dists = make_dists()
        apply_player_override(roster, "KC_WR1", {"target_share": 0.30})
        apply_team_override(dists, {"pass_rate": 0.65})
        wr1 = next(p for p in roster.players if p.player_id == "KC_WR1")
        assert wr1.usage.target_share == pytest.approx(0.30)
        assert dists.play_calling.default["pass"] == pytest.approx(0.65)

    def test_config_file_matches_cli_override(self):
        """Spec test: override via CLI flag matches override via config file."""
        roster1 = make_roster("T1")
        roster2 = make_roster("T2")
        dists1 = make_dists("T1")
        dists2 = make_dists("T2")

        # Apply via OverrideSet (config file path)
        overrides = OverrideSet(
            players={"T1_WR1": {"target_share": 0.30}},
            teams={"T1": {"pass_rate": 0.62}},
        )
        apply_overrides(overrides, dists1, dists2, roster1, roster2)

        wr1 = next(p for p in roster1.players if p.player_id == "T1_WR1")
        assert wr1.usage.target_share == pytest.approx(0.30)
        assert dists1.play_calling.default["pass"] == pytest.approx(0.62)

    def test_apply_overrides_resolves_to_correct_roster(self):
        """Overrides applied to the right team's roster/dists."""
        home_roster = make_roster("KC")
        away_roster = make_roster("BUF")
        home_dists = make_dists("KC")
        away_dists = make_dists("BUF")

        overrides = OverrideSet(
            players={"KC_WR1": {"target_share": 0.30}},
            teams={"BUF": {"pass_rate": 0.62}},
        )
        apply_overrides(overrides, home_dists, away_dists, home_roster, away_roster)

        kc_wr1 = next(p for p in home_roster.players if p.player_id == "KC_WR1")
        assert kc_wr1.usage.target_share == pytest.approx(0.30)
        assert away_dists.play_calling.default["pass"] == pytest.approx(0.62)
        # KC pass rate should be unchanged
        assert home_dists.play_calling.default["pass"] == pytest.approx(0.57)
```

- [ ] **Step 2: Run integration tests**

Run: `uv run pytest tests/test_overrides/test_integration.py -v`
Expected: All PASS

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add tests/test_overrides/test_integration.py
git commit -m "feat: add override integration tests covering all spec requirements"
```

---

## Phase 6 Completion Criteria

All of these must be true before Phase 6 is done:

1. Player target share override redistributes remaining share proportionally to teammates
2. Player carry share override redistributes remaining share proportionally to teammates
3. `games_missed` override reduces `games_played` (e.g., `[4, 5, 6]` → 14 games)
4. Team `pass_rate` override shifts run/pass balance in `PlayCallingDist.default`
5. Team `sack_rate`, `int_rate` overrides modify `TurnoverRates`
6. Stacking player + team overrides on the same team doesn't conflict
7. `--override "name.field=value"` CLI flag works on `demo`, `week`, `season` commands
8. `--config season.yaml` loads overrides from file
9. CLI override matches config file override (same result)
10. Fuzzy player name matching resolves "mahomes" → correct player_id
11. Progress bars display during multi-game simulations
12. Helpful error messages for missing data, invalid weeks, unknown players
13. All existing tests still pass (backward compatible)

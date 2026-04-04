# NCAA Rookie Tier Assignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Use college PFF grades to place rookies into NFL talent tiers instead of draft-capital archetypes, with draft capital modulating blend confidence.

**Architecture:** Extend `TierEngine` with a rookie-specific path that activates for players skipped by the veteran loop (no NFL PFF crosswalk). Loads NCAA grades via the `pff_id` bridge (nflverse roster `pff_id` == NCAA PFF `player_id`), assigns tiers using existing NFL boundaries, and blends with draft-capital-modulated confidence via the existing `_blend_player()` machinery.

**Tech Stack:** Python 3.12+, polars, numpy, pytest, YAML config

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `src/fantasy_sim/data/pff/models.py` | Modify | Add `NcaaRookieConfig` dataclass, add `ncaa_rookie` field to `TierConfig` |
| `src/fantasy_sim/data/pff/config.py` | Modify | Parse `ncaa_rookie` sub-config from YAML into `NcaaRookieConfig` |
| `config/defaults.yaml` | Modify | Add `ncaa_rookie` section under `tier_engine` |
| `src/fantasy_sim/data/pff/tier_engine.py` | Modify | Add `_pick_to_round()`, `_load_ncaa_grades()`, `_apply_rookie_tiers()`. Modify `apply_tiers()` to collect skipped players and call rookie path |
| `scripts/validate_pff_signal.py` | Modify | Add NCAA rookie modes to `--mode` choices and `--config-override` support |
| `tests/test_data/test_pff/test_tier_engine.py` | Modify | Add tests for all rookie tier functionality |

---

### Task 1: Config — `NcaaRookieConfig` dataclass and YAML parsing

**Files:**
- Modify: `src/fantasy_sim/data/pff/models.py:116-142` (TierConfig class)
- Modify: `src/fantasy_sim/data/pff/config.py:89-123` (tier_engine parsing)
- Modify: `config/defaults.yaml:62-83` (tier_engine section)
- Test: `tests/test_data/test_pff/test_tier_engine.py`

- [ ] **Step 1: Write failing tests for NcaaRookieConfig**

Add to `tests/test_data/test_pff/test_tier_engine.py`:

```python
class TestNcaaRookieConfig:
    def test_load_ncaa_rookie_config_from_yaml(self):
        """Full YAML dict is parsed correctly into NcaaRookieConfig."""
        cfg = load_pff_config({
            "pff": {
                "tier_engine": {
                    "enabled": True,
                    "position_grades": {
                        "QB": {"primary": "grades_pass", "secondary": "accuracy_percent"},
                        "RB": {"primary": "grades_run", "secondary": "elusive_rating"},
                        "WR": {"primary": "grades_pass_route", "secondary": "_disabled"},
                        "TE": {"primary": "grades_pass_route", "secondary": "recv_grade"},
                    },
                    "ncaa_rookie": {
                        "enabled": True,
                        "draft_confidence": {
                            1: 1.0, 2: 0.95, 3: 0.85, 4: 0.75,
                            5: 0.65, 6: 0.55, 7: 0.50,
                        },
                        "undrafted_confidence": 0.35,
                        "ncaa_lookback_seasons": 3,
                    },
                }
            }
        })
        ncaa = cfg.tier_engine.ncaa_rookie
        assert ncaa.enabled is True
        assert ncaa.draft_confidence[1] == 1.0
        assert ncaa.draft_confidence[7] == 0.50
        assert ncaa.undrafted_confidence == 0.35
        assert ncaa.ncaa_lookback_seasons == 3

    def test_ncaa_rookie_config_defaults(self):
        """Missing ncaa_rookie section uses sensible defaults."""
        cfg = load_pff_config({"pff": {"tier_engine": {"enabled": True,
            "position_grades": {
                "QB": {"primary": "grades_pass", "secondary": "accuracy_percent"},
                "RB": {"primary": "grades_run", "secondary": "elusive_rating"},
                "WR": {"primary": "grades_pass_route", "secondary": "_disabled"},
                "TE": {"primary": "grades_pass_route", "secondary": "recv_grade"},
            }}}})
        ncaa = cfg.tier_engine.ncaa_rookie
        assert ncaa.enabled is True
        assert ncaa.undrafted_confidence == 0.40
        assert ncaa.ncaa_lookback_seasons == 4
        assert 1 in ncaa.draft_confidence

    def test_ncaa_rookie_config_yaml_string_keys(self):
        """YAML parses dict keys as strings — config parser converts to int."""
        cfg = load_pff_config({
            "pff": {
                "tier_engine": {
                    "enabled": True,
                    "position_grades": {
                        "QB": {"primary": "grades_pass", "secondary": "accuracy_percent"},
                        "RB": {"primary": "grades_run", "secondary": "elusive_rating"},
                        "WR": {"primary": "grades_pass_route", "secondary": "_disabled"},
                        "TE": {"primary": "grades_pass_route", "secondary": "recv_grade"},
                    },
                    "ncaa_rookie": {
                        "draft_confidence": {
                            "1": 0.99, "2": 0.90, "3": 0.80,
                            "4": 0.70, "5": 0.60, "6": 0.50, "7": 0.45,
                        },
                    },
                }
            }
        })
        ncaa = cfg.tier_engine.ncaa_rookie
        assert ncaa.draft_confidence[1] == 0.99
        assert ncaa.draft_confidence[7] == 0.45
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_pff/test_tier_engine.py::TestNcaaRookieConfig -v`
Expected: FAIL — `NcaaRookieConfig` not defined, `ncaa_rookie` attribute missing from `TierConfig`

- [ ] **Step 3: Add NcaaRookieConfig to models.py**

Add before the `TierConfig` class in `src/fantasy_sim/data/pff/models.py`:

```python
@dataclass
class NcaaRookieConfig:
    """Configuration for NCAA-based rookie tier assignment."""
    enabled: bool = True
    draft_confidence: dict[int, float] = field(default_factory=lambda: {
        1: 1.0, 2: 0.95, 3: 0.85, 4: 0.75, 5: 0.65, 6: 0.55, 7: 0.50,
    })
    undrafted_confidence: float = 0.40
    ncaa_lookback_seasons: int = 4
```

Add `ncaa_rookie` field to `TierConfig`:

```python
@dataclass
class TierConfig:
    # ... existing fields ...
    blend_pool_size: int = 500
    ncaa_rookie: NcaaRookieConfig = field(default_factory=NcaaRookieConfig)
```

- [ ] **Step 4: Add NcaaRookieConfig parsing to config.py**

In `src/fantasy_sim/data/pff/config.py`, add `NcaaRookieConfig` to the imports:

```python
from fantasy_sim.data.pff.models import (
    MatchupConfig,
    NcaaPriorsConfig,
    NcaaRookieConfig,
    PffConfig,
    # ... rest unchanged ...
)
```

Then in `load_pff_config()`, after the `tier_engine = TierConfig(...)` block (around line 123), add:

```python
    ncaa_raw = tier_raw.get("ncaa_rookie", {})
    raw_draft_conf = ncaa_raw.get("draft_confidence", {})
    # YAML may parse int keys as strings — convert to int
    draft_confidence = {int(k): float(v) for k, v in raw_draft_conf.items()} if raw_draft_conf else None

    ncaa_rookie = NcaaRookieConfig(
        enabled=ncaa_raw.get("enabled", True),
        undrafted_confidence=ncaa_raw.get("undrafted_confidence", 0.40),
        ncaa_lookback_seasons=ncaa_raw.get("ncaa_lookback_seasons", 4),
        **({"draft_confidence": draft_confidence} if draft_confidence else {}),
    )
    tier_engine.ncaa_rookie = ncaa_rookie
```

- [ ] **Step 5: Add ncaa_rookie section to defaults.yaml**

In `config/defaults.yaml`, add after the `blend_pool_size: 500` line inside `tier_engine:`:

```yaml
    ncaa_rookie:
      enabled: true
      draft_confidence:
        1: 1.0
        2: 0.95
        3: 0.85
        4: 0.75
        5: 0.65
        6: 0.55
        7: 0.50
      undrafted_confidence: 0.40
      ncaa_lookback_seasons: 4
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_pff/test_tier_engine.py::TestNcaaRookieConfig -v`
Expected: 3 PASSED

- [ ] **Step 7: Run full test suite to verify no regressions**

Run: `uv run pytest tests/ -x -q`
Expected: 925 passed

- [ ] **Step 8: Commit**

```bash
git add src/fantasy_sim/data/pff/models.py src/fantasy_sim/data/pff/config.py config/defaults.yaml tests/test_data/test_pff/test_tier_engine.py
git commit -m "feat: add NcaaRookieConfig and YAML parsing for rookie tier assignment"
```

---

### Task 2: `_pick_to_round()` helper

**Files:**
- Modify: `src/fantasy_sim/data/pff/tier_engine.py` (module-level function)
- Test: `tests/test_data/test_pff/test_tier_engine.py`

- [ ] **Step 1: Write failing tests for _pick_to_round**

Add to `tests/test_data/test_pff/test_tier_engine.py`:

```python
from fantasy_sim.data.pff.tier_engine import _pick_to_round


class TestPickToRound:
    def test_first_pick_is_round_1(self):
        assert _pick_to_round(1) == 1

    def test_pick_32_is_round_1(self):
        assert _pick_to_round(32) == 1

    def test_pick_33_is_round_2(self):
        assert _pick_to_round(33) == 2

    def test_pick_64_is_round_2(self):
        assert _pick_to_round(64) == 2

    def test_pick_65_is_round_3(self):
        assert _pick_to_round(65) == 3

    def test_pick_224_is_round_7(self):
        assert _pick_to_round(224) == 7

    def test_compensatory_picks_cap_at_round_7(self):
        assert _pick_to_round(260) == 7

    def test_none_returns_none(self):
        assert _pick_to_round(None) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_pff/test_tier_engine.py::TestPickToRound -v`
Expected: FAIL — `_pick_to_round` not importable

- [ ] **Step 3: Implement _pick_to_round**

Add to `src/fantasy_sim/data/pff/tier_engine.py` after the `MIN_TIER_POOL_SIZE` constant:

```python
def _pick_to_round(draft_number: int | None) -> int | None:
    """Derive draft round from overall pick number.

    NFL draft has ~32 picks per round (compensatory picks vary).
    Caps at round 7.
    """
    if draft_number is None:
        return None
    return min((draft_number - 1) // 32 + 1, 7)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_pff/test_tier_engine.py::TestPickToRound -v`
Expected: 8 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/pff/tier_engine.py tests/test_data/test_pff/test_tier_engine.py
git commit -m "feat: add _pick_to_round() helper for draft capital derivation"
```

---

### Task 3: `_load_ncaa_grades()` method

**Files:**
- Modify: `src/fantasy_sim/data/pff/tier_engine.py` (new method on `TierEngine`)
- Test: `tests/test_data/test_pff/test_tier_engine.py`

- [ ] **Step 1: Write failing tests for _load_ncaa_grades**

Add to `tests/test_data/test_pff/test_tier_engine.py`:

```python
import polars as pl
from unittest.mock import MagicMock
from fantasy_sim.data.pff.models import TierConfig, NcaaRookieConfig, PositionGradeConfig


def _make_tier_engine(ncaa_enabled=True, lookback=4):
    """Create a TierEngine with a mock PFF loader for testing."""
    config = TierConfig(
        enabled=True,
        position_grades={
            "QB": PositionGradeConfig(primary="grades_pass", secondary="accuracy_percent"),
            "RB": PositionGradeConfig(primary="grades_run", secondary="elusive_rating"),
            "WR": PositionGradeConfig(primary="grades_pass_route", secondary="_disabled"),
            "TE": PositionGradeConfig(primary="grades_pass_route", secondary="recv_grade"),
        },
        ncaa_rookie=NcaaRookieConfig(enabled=ncaa_enabled, ncaa_lookback_seasons=lookback),
    )
    loader = MagicMock()
    from fantasy_sim.data.pff.tier_engine import TierEngine
    return TierEngine(config, loader)


def _ncaa_facet_df(player_id, grades_col, grade_values, position="RWR"):
    """Build a minimal NCAA facet DataFrame for testing."""
    return pl.DataFrame({
        "player_id": [player_id] * len(grade_values),
        "player": ["Test Player"] * len(grade_values),
        "team": ["TESTCOL"] * len(grade_values),
        "position": [position] * len(grade_values),
        grades_col: grade_values,
        "season": [2024] * len(grade_values),
        "week": list(range(1, len(grade_values) + 1)),
        "game_id": [f"game_{i}" for i in range(len(grade_values))],
    })


class TestLoadNcaaGrades:
    def test_loads_wr_grades_from_receiving_summary(self):
        """WR loads from receiving_summary facet and averages across games."""
        engine = _make_tier_engine()
        engine._pff_loader.load_ncaa_facet.return_value = _ncaa_facet_df(
            player_id=12345, grades_col="grades_pass_route",
            grade_values=[70.0, 80.0, 90.0],
        )

        result = engine._load_ncaa_grades(12345, "WR", rookie_season=2025)

        engine._pff_loader.load_ncaa_facet.assert_called_once_with(
            "receiving_summary", [2024],
        )
        assert result is not None
        assert abs(result["grades_pass_route"] - 80.0) < 0.01

    def test_loads_rb_grades_from_rushing_summary(self):
        """RB loads from rushing_summary facet."""
        engine = _make_tier_engine()
        engine._pff_loader.load_ncaa_facet.return_value = _ncaa_facet_df(
            player_id=99999, grades_col="grades_run",
            grade_values=[65.0, 75.0], position="HB",
        )

        result = engine._load_ncaa_grades(99999, "RB", rookie_season=2025)

        engine._pff_loader.load_ncaa_facet.assert_called_once_with(
            "rushing_summary", [2024],
        )
        assert result is not None
        assert abs(result["grades_run"] - 70.0) < 0.01

    def test_loads_qb_grades_from_passing_summary(self):
        """QB loads from passing_summary facet."""
        engine = _make_tier_engine()
        engine._pff_loader.load_ncaa_facet.return_value = _ncaa_facet_df(
            player_id=11111, grades_col="grades_pass",
            grade_values=[85.0], position="QB",
        )

        result = engine._load_ncaa_grades(11111, "QB", rookie_season=2025)

        engine._pff_loader.load_ncaa_facet.assert_called_once_with(
            "passing_summary", [2024],
        )
        assert result is not None
        assert abs(result["grades_pass"] - 85.0) < 0.01

    def test_lookback_when_most_recent_season_missing(self):
        """Falls back to earlier NCAA season when most recent has no data."""
        engine = _make_tier_engine(lookback=3)
        # First call (2024): empty. Second call (2023): has data.
        engine._pff_loader.load_ncaa_facet.side_effect = [
            pl.DataFrame(),
            _ncaa_facet_df(
                player_id=12345, grades_col="grades_pass_route",
                grade_values=[72.0, 78.0],
            ),
        ]

        result = engine._load_ncaa_grades(12345, "WR", rookie_season=2025)

        assert engine._pff_loader.load_ncaa_facet.call_count == 2
        assert result is not None
        assert abs(result["grades_pass_route"] - 75.0) < 0.01

    def test_returns_none_for_unknown_player(self):
        """Returns None when player not found in NCAA data."""
        engine = _make_tier_engine()
        engine._pff_loader.load_ncaa_facet.return_value = _ncaa_facet_df(
            player_id=99999, grades_col="grades_pass_route",
            grade_values=[70.0],
        )

        result = engine._load_ncaa_grades(12345, "WR", rookie_season=2025)
        assert result is None

    def test_caches_results(self):
        """Second call for same player uses cache, no loader call."""
        engine = _make_tier_engine()
        engine._pff_loader.load_ncaa_facet.return_value = _ncaa_facet_df(
            player_id=12345, grades_col="grades_pass_route",
            grade_values=[80.0],
        )

        result1 = engine._load_ncaa_grades(12345, "WR", rookie_season=2025)
        result2 = engine._load_ncaa_grades(12345, "WR", rookie_season=2025)

        assert engine._pff_loader.load_ncaa_facet.call_count == 1
        assert result1 == result2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_pff/test_tier_engine.py::TestLoadNcaaGrades -v`
Expected: FAIL — `_load_ncaa_grades` not defined

- [ ] **Step 3: Implement _load_ncaa_grades**

Add to `TierEngine` in `src/fantasy_sim/data/pff/tier_engine.py`, after the `_load_season_grades` method. Also add the `_ncaa_grade_cache` to `__init__`:

In `__init__`, add after `self._pbp_season_cache_key`:

```python
        # NCAA grade cache: (pff_id, position, rookie_season) -> grades dict or None
        self._ncaa_grade_cache: dict[tuple[int, str, int], dict[str, float] | None] = {}
```

New method:

```python
    def _load_ncaa_grades(
        self, pff_id: int, position: str, rookie_season: int,
    ) -> dict[str, float] | None:
        """Load NCAA PFF grades for a rookie via the pff_id bridge.

        Tries the most recent college season (rookie_season - 1) first,
        then walks back up to ncaa_lookback_seasons.  Returns a grade dict
        (same format as _load_season_grades) or None.
        """
        cache_key = (pff_id, position, rookie_season)
        if cache_key in self._ncaa_grade_cache:
            return self._ncaa_grade_cache[cache_key]

        if self._pff_loader is None:
            self._ncaa_grade_cache[cache_key] = None
            return None

        facet = self._POSITION_FACETS.get(position)
        if facet is None:
            self._ncaa_grade_cache[cache_key] = None
            return None

        lookback = self._config.ncaa_rookie.ncaa_lookback_seasons
        meta_cols = {
            "player_id", "player", "team", "position", "pff_position",
            "season", "week", "game_id", "franchise_id", "jersey_number",
            "status",
        }

        for offset in range(lookback):
            ncaa_season = rookie_season - 1 - offset
            df = self._pff_loader.load_ncaa_facet(facet, [ncaa_season])
            if df.is_empty():
                continue

            player_rows = df.filter(pl.col("player_id") == pff_id)
            if player_rows.is_empty():
                continue

            # Average numeric grade columns across games
            numeric_cols = [
                c for c in player_rows.columns
                if c not in meta_cols
                and player_rows[c].dtype in (pl.Float64, pl.Int64, pl.Float32, pl.Int32)
            ]
            if not numeric_cols:
                continue

            grades: dict[str, float] = {}
            for c in numeric_cols:
                vals = player_rows[c].drop_nulls()
                if len(vals) > 0:
                    grades[c] = float(vals.mean())

            if grades:
                self._ncaa_grade_cache[cache_key] = grades
                return grades

        self._ncaa_grade_cache[cache_key] = None
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_pff/test_tier_engine.py::TestLoadNcaaGrades -v`
Expected: 6 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/pff/tier_engine.py tests/test_data/test_pff/test_tier_engine.py
git commit -m "feat: add _load_ncaa_grades() for NCAA PFF grade loading with lookback"
```

---

### Task 4: `_apply_rookie_tiers()` and `apply_tiers()` integration

**Files:**
- Modify: `src/fantasy_sim/data/pff/tier_engine.py` (new method + modify `apply_tiers`)
- Test: `tests/test_data/test_pff/test_tier_engine.py`

- [ ] **Step 1: Write failing tests for _apply_rookie_tiers**

Add to `tests/test_data/test_pff/test_tier_engine.py`:

```python
from fantasy_sim.models.player import PlayerModel, PlayerUsage, PlayerOutcomes, TeamRoster
from fantasy_sim.data.pff.models import TeamContext


def _make_rookie_player(player_id, position, team, **usage_overrides):
    """Create a PlayerModel resembling a rookie archetype."""
    usage = PlayerUsage()
    outcomes = PlayerOutcomes(
        catch_rate=0.58,
        fumble_rate=0.008,
        receiving_yards_dist=np.array([3, 5, 7, 8, 10, 12, 15]),
    )
    if position == "RB":
        usage.carry_share = 0.10
        usage.target_share = 0.02
        outcomes.rushing_yards_dist = np.array([-1, 0, 1, 2, 3, 4, 5, 6])
    elif position in ("WR", "TE"):
        usage.target_share = 0.03
    for k, v in usage_overrides.items():
        setattr(usage, k, v)
    return PlayerModel(
        player_id=player_id, name=f"Rookie {player_id}",
        position=position, team=team,
        usage=usage, outcomes=outcomes, games_played=0,
    )


def _make_roster_df(rows):
    """Build a minimal nflverse-style roster DataFrame."""
    return pl.DataFrame({
        "player_id": [r["player_id"] for r in rows],
        "player_name": [r.get("name", "Test") for r in rows],
        "position": [r.get("position", "WR") for r in rows],
        "team": [r.get("team", "KC") for r in rows],
        "pff_id": [r.get("pff_id") for r in rows],
        "draft_number": [r.get("draft_number") for r in rows],
        "rookie_year": [r.get("rookie_year") for r in rows],
        "season": [r.get("season", 2025) for r in rows],
        "week": [r.get("week", 1) for r in rows],
        "status": [r.get("status", "ACT") for r in rows],
    })


class TestApplyRookieTiers:
    def test_first_rounder_gets_full_tier_influence(self):
        """1st-round pick with NCAA grade gets reliability ~0.0 (full tier)."""
        engine = _make_tier_engine()
        # Pre-build pools so _apply_rookie_tiers can use them
        pool = _make_pool_entry(
            target_share=(0.15, 0.20, 0.25),
            catch_rate=(0.60, 0.65, 0.70),
        )
        engine._pools = {"WR": {2: pool}}
        engine._boundaries = {"WR": [85.0, 70.0, 55.0, 40.0]}

        player = _make_rookie_player("rookie1", "WR", "KC", target_share=0.03)
        roster = TeamRoster(team="KC", players=[player])

        nfl_roster = _make_roster_df([{
            "player_id": "rookie1", "pff_id": 12345,
            "draft_number": 5, "rookie_year": 2025,
        }])

        # Mock NCAA grades: grade 75.0 -> tier 2 (between boundaries 70.0 and 85.0)
        engine._pff_loader.load_ncaa_facet.return_value = _ncaa_facet_df(
            player_id=12345, grades_col="grades_pass_route",
            grade_values=[75.0],
        )

        engine._apply_rookie_tiers(
            roster, nfl_roster, [player], target_season=2025,
            team_context=None, rng=np.random.default_rng(42),
        )

        # Round 1 (pick 5) -> draft_confidence 1.0 -> reliability 0.0
        # target_share should be almost entirely from tier pool (~0.20)
        assert player.usage.target_share > 0.15  # moved well above archetype 0.03

    def test_udfa_gets_partial_archetype_blend(self):
        """Undrafted player blends ~60% archetype, ~40% tier."""
        engine = _make_tier_engine()
        pool = _make_pool_entry(
            target_share=(0.15, 0.20, 0.25),
            catch_rate=(0.60, 0.65, 0.70),
        )
        engine._pools = {"WR": {2: pool}}
        engine._boundaries = {"WR": [85.0, 70.0, 55.0, 40.0]}

        player = _make_rookie_player("rookie_udfa", "WR", "KC", target_share=0.03)
        original_ts = player.usage.target_share
        roster = TeamRoster(team="KC", players=[player])

        nfl_roster = _make_roster_df([{
            "player_id": "rookie_udfa", "pff_id": 54321,
            "draft_number": None, "rookie_year": 2025,
        }])

        engine._pff_loader.load_ncaa_facet.return_value = _ncaa_facet_df(
            player_id=54321, grades_col="grades_pass_route",
            grade_values=[75.0],
        )

        engine._apply_rookie_tiers(
            roster, nfl_roster, [player], target_season=2025,
            team_context=None, rng=np.random.default_rng(42),
        )

        # UDFA -> draft_confidence 0.40 -> reliability 0.60
        # target_share = 0.60 * 0.03 + 0.40 * ~0.20 = ~0.098
        assert player.usage.target_share > original_ts
        assert player.usage.target_share < 0.15  # not full tier influence

    def test_non_rookie_skipped_player_is_ignored(self):
        """Player who isn't a rookie (veteran missing PFF data) is unchanged."""
        engine = _make_tier_engine()
        engine._pools = {"WR": {2: _make_pool_entry()}}
        engine._boundaries = {"WR": [85.0, 70.0, 55.0, 40.0]}

        player = _make_rookie_player("vet_no_pff", "WR", "KC", target_share=0.12)
        original_ts = player.usage.target_share
        roster = TeamRoster(team="KC", players=[player])

        nfl_roster = _make_roster_df([{
            "player_id": "vet_no_pff", "pff_id": 99999,
            "draft_number": 45, "rookie_year": 2020,  # not a 2025 rookie
        }])

        engine._apply_rookie_tiers(
            roster, nfl_roster, [player], target_season=2025,
            team_context=None, rng=np.random.default_rng(42),
        )

        assert player.usage.target_share == original_ts

    def test_player_without_ncaa_data_keeps_archetype(self):
        """Rookie without NCAA PFF data keeps their archetype model."""
        engine = _make_tier_engine()
        engine._pools = {"WR": {2: _make_pool_entry()}}
        engine._boundaries = {"WR": [85.0, 70.0, 55.0, 40.0]}

        player = _make_rookie_player("rookie_no_ncaa", "WR", "KC", target_share=0.03)
        original_ts = player.usage.target_share
        roster = TeamRoster(team="KC", players=[player])

        nfl_roster = _make_roster_df([{
            "player_id": "rookie_no_ncaa", "pff_id": 88888,
            "draft_number": 150, "rookie_year": 2025,
        }])

        # NCAA data doesn't contain this player
        engine._pff_loader.load_ncaa_facet.return_value = pl.DataFrame()

        engine._apply_rookie_tiers(
            roster, nfl_roster, [player], target_season=2025,
            team_context=None, rng=np.random.default_rng(42),
        )

        assert player.usage.target_share == original_ts

    def test_team_context_applied_before_blend(self):
        """Team context adjustments apply to tier distributions before blending."""
        engine = _make_tier_engine()
        pool = _make_pool_entry(catch_rate=(0.60, 0.65, 0.70))
        engine._pools = {"WR": {2: pool}}
        engine._boundaries = {"WR": [85.0, 70.0, 55.0, 40.0]}

        player = _make_rookie_player("rookie_tc", "WR", "KC", target_share=0.03)
        roster = TeamRoster(team="KC", players=[player])

        nfl_roster = _make_roster_df([{
            "player_id": "rookie_tc", "pff_id": 77777,
            "draft_number": 1, "rookie_year": 2025,
        }])

        engine._pff_loader.load_ncaa_facet.return_value = _ncaa_facet_df(
            player_id=77777, grades_col="grades_pass_route",
            grade_values=[75.0],
        )

        # Team context with boosted QB quality -> higher catch rate
        tc = TeamContext(qb_quality_factor=1.05)

        engine._apply_rookie_tiers(
            roster, nfl_roster, [player], target_season=2025,
            team_context=tc, rng=np.random.default_rng(42),
        )

        # 1st rounder -> full tier influence. Catch rate should reflect
        # the team context boost (1.05x on tier pool value)
        assert player.outcomes.catch_rate > 0.60


class TestApplyTiersRookieIntegration:
    def test_veterans_processed_rookies_also_processed(self):
        """Veterans go through normal path, rookies through NCAA path."""
        engine = _make_tier_engine()
        pool = _make_pool_entry()
        engine._pools = {"WR": {2: pool, 3: pool}}
        engine._boundaries = {"WR": [85.0, 70.0, 55.0, 40.0]}
        engine._cache_key = (2022, 2023, 2024)

        vet = _make_rookie_player("vet1", "WR", "KC", target_share=0.20)
        vet.games_played = 32
        rookie = _make_rookie_player("rookie1", "WR", "KC", target_share=0.03)

        roster = TeamRoster(team="KC", players=[vet, rookie])

        # Crosswalk: veteran is in NFL PFF, rookie is not
        crosswalk = {100: "vet1"}

        nfl_roster = _make_roster_df([
            {"player_id": "vet1", "pff_id": 100, "draft_number": 20, "rookie_year": 2020},
            {"player_id": "rookie1", "pff_id": 12345, "draft_number": 5, "rookie_year": 2025},
        ])

        # Mock NFL grades for veteran
        engine._load_season_grades = MagicMock(return_value={
            100: {"grades_pass_route": 72.0},
        })

        # Mock NCAA grades for rookie
        engine._pff_loader.load_ncaa_facet.return_value = _ncaa_facet_df(
            player_id=12345, grades_col="grades_pass_route",
            grade_values=[78.0],
        )

        engine.apply_tiers(
            roster, crosswalk, [2022, 2023, 2024],
            nfl_roster=nfl_roster, target_season=2025,
        )

        # Both should have been adjusted
        assert vet.usage.target_share != 0.20  # veteran was blended
        assert rookie.usage.target_share > 0.03  # rookie was blended

    def test_ncaa_rookie_disabled_skips_rookie_path(self):
        """When ncaa_rookie.enabled=False, skipped players are unchanged."""
        engine = _make_tier_engine(ncaa_enabled=False)
        pool = _make_pool_entry()
        engine._pools = {"WR": {3: pool}}
        engine._boundaries = {"WR": [85.0, 70.0, 55.0, 40.0]}
        engine._cache_key = (2022, 2023, 2024)

        rookie = _make_rookie_player("rookie1", "WR", "KC", target_share=0.03)
        original_ts = rookie.usage.target_share
        roster = TeamRoster(team="KC", players=[rookie])

        nfl_roster = _make_roster_df([
            {"player_id": "rookie1", "pff_id": 12345, "draft_number": 5, "rookie_year": 2025},
        ])

        engine.apply_tiers(
            roster, {}, [2022, 2023, 2024],
            nfl_roster=nfl_roster, target_season=2025,
        )

        assert rookie.usage.target_share == original_ts
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_pff/test_tier_engine.py::TestApplyRookieTiers -v`
Expected: FAIL — `_apply_rookie_tiers` not defined

- [ ] **Step 3: Implement _apply_rookie_tiers**

Add to `TierEngine` in `src/fantasy_sim/data/pff/tier_engine.py`, before `apply_tiers`:

```python
    def _apply_rookie_tiers(
        self,
        roster: "TeamRoster",
        nfl_roster: "pl.DataFrame",
        skipped_players: "list[PlayerModel]",
        target_season: int,
        team_context: "TeamContext | None",
        rng: "np.random.Generator",
    ) -> None:
        """Apply NCAA-grade-based tier assignment to rookie players.

        For each skipped player (not in NFL PFF crosswalk):
        1. Check if they're a rookie (rookie_year == target_season)
        2. Load NCAA grades via pff_id bridge
        3. Assign tier using NFL boundaries
        4. Blend with draft-capital-modulated confidence

        Players who aren't rookies or lack NCAA data are unchanged.
        """
        if self._pools is None or self._boundaries is None:
            return

        ncaa_cfg = self._config.ncaa_rookie

        # Build roster lookup: nfl_player_id -> {pff_id, draft_number, rookie_year}
        pid_col = "player_id"
        roster_lookup: dict[str, dict] = {}
        for row in nfl_roster.iter_rows(named=True):
            pid = row.get(pid_col)
            if pid is None:
                continue
            pff_id_raw = row.get("pff_id")
            if pff_id_raw is None:
                continue
            try:
                pff_id_int = int(pff_id_raw)
            except (ValueError, TypeError):
                continue
            roster_lookup[str(pid)] = {
                "pff_id": pff_id_int,
                "draft_number": row.get("draft_number"),
                "rookie_year": row.get("rookie_year"),
            }

        for player in skipped_players:
            position = player.position
            if position not in self._pools:
                continue

            info = roster_lookup.get(player.player_id)
            if info is None:
                continue

            # Only process rookies
            if info["rookie_year"] != target_season:
                continue

            pff_id = info["pff_id"]

            # Load NCAA grades
            ncaa_grades = self._load_ncaa_grades(pff_id, position, target_season)
            if ncaa_grades is None:
                continue

            # Assign tier using NFL boundaries
            result = self.select_distributions(ncaa_grades, position)
            if result is None:
                continue

            assignment, tier_dists = result

            # Apply team context before blending
            if team_context is not None:
                self.apply_team_context(tier_dists, team_context, position)

            # Compute draft-capital-modulated blend weight
            draft_round = _pick_to_round(info["draft_number"])
            if draft_round is not None:
                draft_confidence = ncaa_cfg.draft_confidence.get(
                    draft_round, ncaa_cfg.undrafted_confidence,
                )
            else:
                draft_confidence = ncaa_cfg.undrafted_confidence

            reliability = 1.0 - draft_confidence

            # Blend: player's archetype model is the "PBP" side
            self._blend_player(player, tier_dists, reliability, rng)

            logger.info(
                "NCAA tier %d assigned to rookie %s (%s) — "
                "draft_confidence=%.2f, pff_id=%d",
                assignment.tier, player.player_id, position,
                draft_confidence, pff_id,
            )
```

- [ ] **Step 4: Modify apply_tiers to collect skipped players and call rookie path**

In `apply_tiers()`, change the player loop to collect skipped players. Replace the block starting at `for player in roster.players:` (line 1027):

Change:
```python
        for player in roster.players:
            pff_id = reverse_cw.get(player.player_id)
            if pff_id is None:
                continue
```

To:
```python
        skipped_players: list = []

        for player in roster.players:
            pff_id = reverse_cw.get(player.player_id)
            if pff_id is None:
                skipped_players.append(player)
                continue
```

Then at the very end of `apply_tiers()` (after the `logger.info` in the loop), add:

```python
        # NCAA rookie tier assignment for players not in NFL PFF crosswalk
        if (
            skipped_players
            and self._config.ncaa_rookie.enabled
            and nfl_roster is not None
        ):
            self._apply_rookie_tiers(
                roster, nfl_roster, skipped_players, target_s,
                team_context, rng,
            )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_pff/test_tier_engine.py::TestApplyRookieTiers tests/test_data/test_pff/test_tier_engine.py::TestApplyTiersRookieIntegration -v`
Expected: 7 PASSED

- [ ] **Step 6: Run full test suite**

Run: `uv run pytest tests/ -x -q`
Expected: All tests pass (925 existing + new tests)

- [ ] **Step 7: Commit**

```bash
git add src/fantasy_sim/data/pff/tier_engine.py tests/test_data/test_pff/test_tier_engine.py
git commit -m "feat: add _apply_rookie_tiers() and integrate into apply_tiers() loop"
```

---

### Task 5: A/B validation harness modes

**Files:**
- Modify: `scripts/validate_pff_signal.py`

- [ ] **Step 1: Add NCAA rookie modes to --mode choices**

In `scripts/validate_pff_signal.py`, update the `--mode` argument choices (line 483):

Change:
```python
        choices=["matchup", "talent", "tier", "matchup+tier",
                 "team_context+tier", "team_context+tier+matchup", "all"],
```

To:
```python
        choices=["matchup", "talent", "tier", "matchup+tier",
                 "team_context+tier", "team_context+tier+matchup",
                 "ncaa_rookie+tier", "ncaa_rookie+tier+matchup", "all"],
```

Update the help text to include the new modes:

```python
        help=(
            "Which PFF layer(s) to enable in the ON run. "
            "'ncaa_rookie+tier' = tier + NCAA rookie assignment, "
            "'ncaa_rookie+tier+matchup' = tier + NCAA rookie + matchup, "
            "'team_context+tier' = tier + team context, "
            "'team_context+tier+matchup' = full stack, "
            "'matchup+tier' = matchup + tier (current default), "
            "'matchup' = defensive matchup adjustments only, "
            "'talent' = talent stabilizer only, "
            "'tier' = tier distribution engine only, "
            "'all' = matchup + talent layers (default: all)."
        ),
```

- [ ] **Step 2: Add mode handlers in _build_pff_config**

In `_build_pff_config()`, add two new `elif` branches before the `else` (around line 250):

```python
    elif mode == "ncaa_rookie+tier":
        matchup_cfg = MatchupConfig(enabled=False)
        talent_cfg = TalentConfig(enabled=False)
        tier_cfg = TierConfig(enabled=True)
        tc_cfg = TeamContextConfig(enabled=False)
    elif mode == "ncaa_rookie+tier+matchup":
        matchup_cfg = MatchupConfig(enabled=True)
        talent_cfg = TalentConfig(enabled=False)
        tier_cfg = TierConfig(enabled=True)
        tc_cfg = TeamContextConfig(enabled=False)
```

- [ ] **Step 3: Add ncaa_rookie to config-override support**

In `_build_pff_config()`, add after the `team_context` override block (around line 293):

```python
    if overrides and "ncaa_rookie" in overrides:
        ncaa_cfg = tier_cfg.ncaa_rookie
        for key, val in overrides["ncaa_rookie"].items():
            if key == "draft_confidence" and isinstance(val, dict):
                ncaa_cfg.draft_confidence = {int(k): float(v) for k, v in val.items()}
            elif hasattr(ncaa_cfg, key):
                setattr(ncaa_cfg, key, val)
```

Update the `--config-override` help text to include `ncaa_rookie`:

```python
        help='PFF config overrides as JSON. Keys: "talent", "matchup", "tier_engine", "team_context", "ncaa_rookie". '
             'Example: \'{"ncaa_rookie": {"undrafted_confidence": 0.30}}\'',
```

- [ ] **Step 4: Commit**

```bash
git add scripts/validate_pff_signal.py
git commit -m "feat: add ncaa_rookie+tier modes to A/B validation harness"
```

---

### Task 6: Full regression test and docs update

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/pff-improvement-roadmap.md`

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests pass (925 existing + ~20 new = ~945)

- [ ] **Step 2: Update CLAUDE.md**

Add to the "Current State" section, after the PFF Team Context Layer entry:

```
- **NCAA Rookie Tier Assignment**: Complete — N tests (total tests). Uses college PFF grades to place rookies into NFL talent tiers via the pff_id bridge. Grade drives tier, draft capital modulates blend confidence. All rookies with NCAA PFF data get grade-based assignment; others fall back to existing archetypes.
```

Update the PFF Intelligence Layer bullet in "Key Patterns" to mention NCAA rookie assignment:

```
- **PFF Intelligence Layer**: Three active layers in `data/pff/` (tier + team context + matchup) plus NCAA rookie tier assignment. **TierEngine** ... (existing text) ... `_apply_rookie_tiers()` handles rookies via NCAA grades (pff_id bridge), with draft-capital-modulated blend confidence via `NcaaRookieConfig`.
```

- [ ] **Step 3: Update pff-improvement-roadmap.md**

Mark item #3 as COMPLETE in `docs/pff-improvement-roadmap.md`:

```markdown
### 3. ~~NCAA Tier Assignment for Rookies~~ — COMPLETE

**Result:** NCAA grades via pff_id bridge place rookies into NFL talent tiers. 85/85 drafted, 143/144 total rookies matched for 2025 class. Grade drives tier assignment (direct comparison against NFL boundaries), draft capital modulates blend confidence (1st round = 1.0, UDFA = 0.4). Config in `defaults.yaml` under `tier_engine.ncaa_rookie`.
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md docs/pff-improvement-roadmap.md
git commit -m "docs: mark NCAA rookie tier assignment complete, update CLAUDE.md"
```

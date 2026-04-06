# Kicker/DST from PFF Grades — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace placeholder kicker model with per-kicker PFF accuracy (Bayesian shrinkage) and add light DST baseline adjustments (fumble rate + defensive TD rates) that complement the matchup engine.

**Architecture:** Two new PFF engine classes (`KickerEngine`, `DstBaselineEngine`) follow the established matchup/coverage engine pattern: load PFF facet data, compute adjustments, apply in `build_game()` after existing layers. Config dataclasses extend `PffConfig`. `DefensiveTdRates` added to `TeamDistributions` replaces fixed constants in `game_sim.py`.

**Tech Stack:** Python 3.12+, polars, numpy, pytest, YAML config

---

### Task 1: Config Dataclasses + Types

**Files:**
- Modify: `src/fantasy_sim/data/pff/models.py:212-222`
- Modify: `src/fantasy_sim/engine/types.py:1-16`
- Test: `tests/test_data/test_pff/test_kicker.py` (new)
- Test: `tests/test_data/test_pff/test_dst_baseline.py` (new)

- [ ] **Step 1: Write failing test for KickerConfig and DstBaselineConfig**

Create `tests/test_data/test_pff/test_kicker.py`:

```python
"""Tests for PFF kicker engine — per-kicker accuracy with Bayesian shrinkage."""

import polars as pl
import pytest

from fantasy_sim.data.pff.models import KickerConfig, PffConfig


class TestKickerConfig:
    def test_default_values(self):
        cfg = KickerConfig()
        assert cfg.enabled is True
        assert cfg.prior_strength == 20
        assert cfg.min_attempts == 5

    def test_pff_config_has_kicker(self):
        pff = PffConfig()
        assert hasattr(pff, "kicker")
        assert isinstance(pff.kicker, KickerConfig)
```

Create `tests/test_data/test_pff/test_dst_baseline.py`:

```python
"""Tests for PFF DST baseline engine — fumble rate + defensive TD rates."""

import polars as pl
import pytest

from fantasy_sim.data.pff.models import DstBaselineConfig, DstBaselineContext, PffConfig


class TestDstBaselineConfig:
    def test_default_values(self):
        cfg = DstBaselineConfig()
        assert cfg.enabled is True
        assert cfg.prior_strength == 10
        assert cfg.min_games == 4
        assert cfg.clamp == [0.85, 1.15]
        assert cfg.sensitivities == {"fumble_rate": 0.06}

    def test_pff_config_has_dst_baseline(self):
        pff = PffConfig()
        assert hasattr(pff, "dst_baseline")
        assert isinstance(pff.dst_baseline, DstBaselineConfig)


class TestDstBaselineContext:
    def test_default_neutral(self):
        ctx = DstBaselineContext()
        assert ctx.fumble_rate_factor == 1.0
        assert ctx.int_return_td_rate == 0.20
        assert ctx.fumble_return_td_rate == 0.10
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_pff/test_kicker.py::TestKickerConfig -v && uv run pytest tests/test_data/test_pff/test_dst_baseline.py -v`
Expected: FAIL with ImportError (KickerConfig, DstBaselineConfig, DstBaselineContext not defined)

- [ ] **Step 3: Implement config dataclasses in models.py**

Add before `PffConfig` class in `src/fantasy_sim/data/pff/models.py`:

```python
@dataclass
class KickerConfig:
    """Configuration for the PFF kicker engine."""
    enabled: bool = True
    prior_strength: int = 20
    min_attempts: int = 5


@dataclass
class DstBaselineConfig:
    """Configuration for the DST baseline engine."""
    enabled: bool = True
    sensitivities: dict[str, float] = field(default_factory=lambda: {"fumble_rate": 0.06})
    prior_strength: int = 10
    min_games: int = 4
    clamp: list[float] = field(default_factory=lambda: [0.85, 1.15])


@dataclass
class DstBaselineContext:
    """Per-team DST baseline adjustments from PFF defensive data.

    fumble_rate_factor: multiplicative factor for opposing offense fumble_rate (z-score based).
    int_return_td_rate: team-specific pick-six rate (Bayesian shrinkage from 0.20 default).
    fumble_return_td_rate: team-specific fumble return TD rate (Bayesian shrinkage from 0.10 default).
    """
    fumble_rate_factor: float = 1.0
    int_return_td_rate: float = 0.20
    fumble_return_td_rate: float = 0.10
```

Update `PffConfig` to add kicker and dst_baseline fields:

```python
@dataclass
class PffConfig:
    """Top-level PFF configuration."""
    enabled: bool = False
    data_dir: str | None = None
    matchup: MatchupConfig = field(default_factory=MatchupConfig)
    talent: TalentConfig = field(default_factory=TalentConfig)
    tier_engine: TierConfig = field(default_factory=TierConfig)
    team_context: TeamContextConfig = field(default_factory=TeamContextConfig)
    coverage: CoverageConfig = field(default_factory=CoverageConfig)
    kicker: KickerConfig = field(default_factory=KickerConfig)
    dst_baseline: DstBaselineConfig = field(default_factory=DstBaselineConfig)
```

- [ ] **Step 4: Run config tests to verify they pass**

Run: `uv run pytest tests/test_data/test_pff/test_kicker.py::TestKickerConfig tests/test_data/test_pff/test_dst_baseline.py -v`
Expected: PASS

- [ ] **Step 5: Write failing test for DefensiveTdRates and TeamDistributions**

Add to `tests/test_data/test_pff/test_dst_baseline.py`:

```python
from fantasy_sim.engine.types import DefensiveTdRates, TeamDistributions


class TestDefensiveTdRates:
    def test_default_matches_constants(self):
        rates = DefensiveTdRates()
        assert rates.int_return_td_rate == 0.20
        assert rates.fumble_return_td_rate == 0.10

    def test_team_distributions_has_defensive_td_rates(self):
        """TeamDistributions should have a defensive_td_rates field with defaults."""
        from fantasy_sim.models.distributions import (
            PlayCallingDist, PlayOutcomeDist, TurnoverRates, KickingModel, DriveStartModel,
        )
        import numpy as np
        dists = TeamDistributions(
            play_calling=PlayCallingDist(team="TST", distributions={}, default={"pass": 0.5, "run": 0.5}),
            play_outcomes=PlayOutcomeDist(team="TST", distributions={}, default={"complete": 0.6, "incomplete": 0.2, "sack": 0.1, "scramble": 0.1}),
            turnover_rates=TurnoverRates(team="TST", int_rate=0.025, fumble_rate=0.012, sack_rate=0.065, sack_fumble_rate=0.10),
            kicking=KickingModel(fg_make_rate={"0_39": 0.90, "40_49": 0.84, "50_plus": 0.67}, xp_rate=0.95),
            drive_start=DriveStartModel(touchback_rate=0.6, touchback_yardline=75, return_yardlines=np.array([75])),
        )
        assert hasattr(dists, "defensive_td_rates")
        assert dists.defensive_td_rates.int_return_td_rate == 0.20
        assert dists.defensive_td_rates.fumble_return_td_rate == 0.10
```

- [ ] **Step 6: Run test to verify it fails**

Run: `uv run pytest tests/test_data/test_pff/test_dst_baseline.py::TestDefensiveTdRates -v`
Expected: FAIL with ImportError (DefensiveTdRates not defined)

- [ ] **Step 7: Implement DefensiveTdRates in engine/types.py**

Add to `src/fantasy_sim/engine/types.py` after imports, before `TeamDistributions`:

```python
@dataclass
class DefensiveTdRates:
    """Team-specific defensive TD rates (replaces fixed constants in game_sim)."""
    int_return_td_rate: float = 0.20
    fumble_return_td_rate: float = 0.10
```

Add `defensive_td_rates` field to `TeamDistributions`:

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
```

- [ ] **Step 8: Run test to verify it passes**

Run: `uv run pytest tests/test_data/test_pff/test_dst_baseline.py::TestDefensiveTdRates -v`
Expected: PASS

- [ ] **Step 9: Run full test suite to verify no regressions**

Run: `uv run pytest tests/ -x -q`
Expected: All tests pass (the new `defensive_td_rates` field has a default factory, so existing TeamDistributions constructors work unchanged)

- [ ] **Step 10: Commit**

```bash
git add src/fantasy_sim/data/pff/models.py src/fantasy_sim/engine/types.py tests/test_data/test_pff/test_kicker.py tests/test_data/test_pff/test_dst_baseline.py
git commit -m "feat(pff): add KickerConfig, DstBaselineConfig, DefensiveTdRates dataclasses"
```

---

### Task 2: KickerEngine — Core Logic

**Files:**
- Create: `src/fantasy_sim/data/pff/kicker.py`
- Test: `tests/test_data/test_pff/test_kicker.py`

- [ ] **Step 1: Write failing tests for Bayesian shrinkage and distance mapping**

Add to `tests/test_data/test_pff/test_kicker.py`:

```python
from fantasy_sim.data.pff.loader import PffLoader
from fantasy_sim.data.pff.models import KickerConfig
from fantasy_sim.data.pff.kicker import KickerEngine
from fantasy_sim.models.distributions import KickingModel


# ---------- Fixtures ----------

@pytest.fixture
def pff_dir(tmp_path):
    d = tmp_path / "pff" / "processed" / "nfl"
    d.mkdir(parents=True)
    return d


@pytest.fixture
def loader(pff_dir):
    return PffLoader(pff_dir)


def _write_field_goal_summary(pff_dir, season, kickers):
    """Write field_goal_summary parquet with per-kicker game rows.

    kickers: list of dicts with keys:
        player_id, player, team, n_games,
        twenty_attempts, twenty_made,
        thirty_attempts, thirty_made,
        forty_attempts, forty_made,
        fifty_attempts, fifty_made,
        pat_attempts, pat_made
    """
    rows = {
        "player_id": [], "player": [], "team": [], "position": [],
        "season": [], "week": [], "game_id": [],
        "jersey_number": [], "franchise_id": [], "status": [],
        "grades_fgep_kicker": [],
        "one_attempts": [], "one_made": [], "one_percent": [],
        "twenty_attempts": [], "twenty_made": [], "twenty_percent": [],
        "thirty_attempts": [], "thirty_made": [], "thirty_percent": [],
        "forty_attempts": [], "forty_made": [], "forty_percent": [],
        "fifty_attempts": [], "fifty_made": [], "fifty_percent": [],
        "pat_attempts": [], "pat_made": [], "pat_percent": [],
        "total_attempts": [], "total_made": [], "total_percent": [],
        "penalties": [], "declined_penalties": [],
    }
    gid = 9000
    for k in kickers:
        for g in range(k.get("n_games", 1)):
            rows["player_id"].append(k["player_id"])
            rows["player"].append(k["player"])
            rows["team"].append(k["team"])
            rows["position"].append("K")
            rows["season"].append(season)
            rows["week"].append(g + 1)
            rows["game_id"].append(gid)
            gid += 1
            rows["jersey_number"].append("1")
            rows["franchise_id"].append(1)
            rows["status"].append("S")
            rows["grades_fgep_kicker"].append(k.get("grade", 70.0))
            rows["one_attempts"].append(0)
            rows["one_made"].append(0)
            rows["one_percent"].append(0.0)
            t_att = k.get("twenty_attempts", 0)
            t_made = k.get("twenty_made", 0)
            rows["twenty_attempts"].append(t_att)
            rows["twenty_made"].append(t_made)
            rows["twenty_percent"].append(t_made / t_att * 100 if t_att else 0.0)
            th_att = k.get("thirty_attempts", 0)
            th_made = k.get("thirty_made", 0)
            rows["thirty_attempts"].append(th_att)
            rows["thirty_made"].append(th_made)
            rows["thirty_percent"].append(th_made / th_att * 100 if th_att else 0.0)
            f_att = k.get("forty_attempts", 0)
            f_made = k.get("forty_made", 0)
            rows["forty_attempts"].append(f_att)
            rows["forty_made"].append(f_made)
            rows["forty_percent"].append(f_made / f_att * 100 if f_att else 0.0)
            fi_att = k.get("fifty_attempts", 0)
            fi_made = k.get("fifty_made", 0)
            rows["fifty_attempts"].append(fi_att)
            rows["fifty_made"].append(fi_made)
            rows["fifty_percent"].append(fi_made / fi_att * 100 if fi_att else 0.0)
            p_att = k.get("pat_attempts", 0)
            p_made = k.get("pat_made", 0)
            rows["pat_attempts"].append(p_att)
            rows["pat_made"].append(p_made)
            rows["pat_percent"].append(p_made / p_att * 100 if p_att else 0.0)
            total_att = t_att + th_att + f_att + fi_att
            total_made = t_made + th_made + f_made + fi_made
            rows["total_attempts"].append(total_att)
            rows["total_made"].append(total_made)
            rows["total_percent"].append(total_made / total_att * 100 if total_att else 0.0)
            rows["penalties"].append(0)
            rows["declined_penalties"].append(0)

    df = pl.DataFrame(rows)
    df.write_parquet(pff_dir / f"field_goal_summary_{season}.parquet")


def _make_kicker_roster(kickers):
    """Build a minimal nflverse roster DataFrame for kickers.

    kickers: list of dicts with keys: player_id (str), player_name, team, pff_id (int)
    """
    return pl.DataFrame({
        "player_id": [k["player_id"] for k in kickers],
        "player_name": [k["player_name"] for k in kickers],
        "team": [k["team"] for k in kickers],
        "position": ["K"] * len(kickers),
        "pff_id": [str(k["pff_id"]) for k in kickers],
    })


class TestKickerEngineShrinkage:
    """Test Bayesian shrinkage on per-kicker FG accuracy."""

    def test_high_volume_kicker_near_personal_rate(self, pff_dir, loader):
        """Kicker with many attempts should have rate near personal accuracy."""
        _write_field_goal_summary(pff_dir, 2024, [
            {"player_id": 100, "player": "Justin Tucker", "team": "BAL",
             "n_games": 17, "thirty_attempts": 2, "thirty_made": 2,
             "forty_attempts": 2, "forty_made": 2,
             "fifty_attempts": 1, "fifty_made": 1,
             "pat_attempts": 3, "pat_made": 3},
            {"player_id": 200, "player": "Bad Kicker", "team": "NYG",
             "n_games": 17, "thirty_attempts": 2, "thirty_made": 1,
             "forty_attempts": 1, "forty_made": 0,
             "fifty_attempts": 1, "fifty_made": 0,
             "pat_attempts": 2, "pat_made": 2},
        ])
        roster = _make_kicker_roster([
            {"player_id": "tucker-01", "player_name": "Justin Tucker", "team": "BAL", "pff_id": 100},
        ])
        cfg = KickerConfig(prior_strength=5, min_attempts=3)
        engine = KickerEngine(cfg, loader, [2024])
        engine.build_crosswalk(roster, 2024)
        model = engine.compute("tucker-01")
        assert model is not None
        # Tucker: 34 thirty_made / 34 thirty_att (17 games * 2 each)
        # With prior=5: (34 + 5*league) / (34 + 5) → near personal rate
        # His 40-49 rate is 100% (34/34), league is ~75%
        assert model.fg_make_rate["40_49"] > 0.90  # dominated by personal 100%

    def test_low_volume_kicker_near_league_rate(self, pff_dir, loader):
        """Kicker with few attempts should have rate near league average."""
        _write_field_goal_summary(pff_dir, 2024, [
            {"player_id": 100, "player": "Elite K", "team": "KC",
             "n_games": 17, "forty_attempts": 2, "forty_made": 2,
             "fifty_attempts": 1, "fifty_made": 1,
             "thirty_attempts": 2, "thirty_made": 2,
             "pat_attempts": 3, "pat_made": 3},
            # Low-volume kicker: only 1 game
            {"player_id": 200, "player": "New K", "team": "NYG",
             "n_games": 1, "forty_attempts": 1, "forty_made": 1,
             "fifty_attempts": 0, "fifty_made": 0,
             "thirty_attempts": 1, "thirty_made": 1,
             "pat_attempts": 1, "pat_made": 1},
        ])
        roster = _make_kicker_roster([
            {"player_id": "newk-01", "player_name": "New K", "team": "NYG", "pff_id": 200},
        ])
        cfg = KickerConfig(prior_strength=20, min_attempts=1)
        engine = KickerEngine(cfg, loader, [2024])
        engine.build_crosswalk(roster, 2024)
        model = engine.compute("newk-01")
        assert model is not None
        league_50 = engine._league_rates["50_plus"]
        # 0 personal attempts at 50+, prior=20 → rate equals league exactly
        assert model.fg_make_rate["50_plus"] == pytest.approx(league_50, abs=0.001)

    def test_min_attempts_returns_none(self, pff_dir, loader):
        """Kicker below min_attempts threshold returns None."""
        _write_field_goal_summary(pff_dir, 2024, [
            {"player_id": 100, "player": "Sparse K", "team": "DEN",
             "n_games": 1, "thirty_attempts": 1, "thirty_made": 1,
             "pat_attempts": 1, "pat_made": 1},
        ])
        roster = _make_kicker_roster([
            {"player_id": "sparse-01", "player_name": "Sparse K", "team": "DEN", "pff_id": 100},
        ])
        cfg = KickerConfig(prior_strength=20, min_attempts=10)
        engine = KickerEngine(cfg, loader, [2024])
        engine.build_crosswalk(roster, 2024)
        result = engine.compute("sparse-01")
        assert result is None

    def test_missing_kicker_returns_none(self, pff_dir, loader):
        """Kicker not in crosswalk returns None."""
        _write_field_goal_summary(pff_dir, 2024, [
            {"player_id": 100, "player": "Known K", "team": "KC",
             "n_games": 5, "thirty_attempts": 2, "thirty_made": 2,
             "pat_attempts": 2, "pat_made": 2},
        ])
        roster = _make_kicker_roster([])
        cfg = KickerConfig()
        engine = KickerEngine(cfg, loader, [2024])
        engine.build_crosswalk(roster, 2024)
        result = engine.compute("unknown-01")
        assert result is None

    def test_distance_bucket_mapping(self, pff_dir, loader):
        """PFF twenty+thirty → 0_39, forty → 40_49, fifty → 50_plus."""
        _write_field_goal_summary(pff_dir, 2024, [
            {"player_id": 100, "player": "Test K", "team": "BUF",
             "n_games": 10,
             "twenty_attempts": 1, "twenty_made": 1,  # 10 total, 10 made
             "thirty_attempts": 1, "thirty_made": 1,  # 10 total, 10 made
             "forty_attempts": 1, "forty_made": 0,    # 10 total, 0 made
             "fifty_attempts": 1, "fifty_made": 1,    # 10 total, 10 made
             "pat_attempts": 2, "pat_made": 1},       # 20 total, 10 made
        ])
        roster = _make_kicker_roster([
            {"player_id": "testk-01", "player_name": "Test K", "team": "BUF", "pff_id": 100},
        ])
        cfg = KickerConfig(prior_strength=0, min_attempts=1)  # zero prior = pure personal
        engine = KickerEngine(cfg, loader, [2024])
        engine.build_crosswalk(roster, 2024)
        model = engine.compute("testk-01")
        assert model is not None
        # 0_39 = (10+10) made / (10+10) att = 1.0
        assert model.fg_make_rate["0_39"] == pytest.approx(1.0, abs=0.01)
        # 40_49 = 0/10 = 0.0
        assert model.fg_make_rate["40_49"] == pytest.approx(0.0, abs=0.01)
        # 50+ = 10/10 = 1.0
        assert model.fg_make_rate["50_plus"] == pytest.approx(1.0, abs=0.01)
        # XP = 10/20 = 0.5
        assert model.xp_rate == pytest.approx(0.5, abs=0.01)

    def test_returns_kicking_model(self, pff_dir, loader):
        """compute() returns a KickingModel with all required keys."""
        _write_field_goal_summary(pff_dir, 2024, [
            {"player_id": 100, "player": "Test K", "team": "KC",
             "n_games": 10, "thirty_attempts": 2, "thirty_made": 2,
             "forty_attempts": 1, "forty_made": 1,
             "fifty_attempts": 1, "fifty_made": 0,
             "pat_attempts": 3, "pat_made": 3},
        ])
        roster = _make_kicker_roster([
            {"player_id": "testk-01", "player_name": "Test K", "team": "KC", "pff_id": 100},
        ])
        cfg = KickerConfig()
        engine = KickerEngine(cfg, loader, [2024])
        engine.build_crosswalk(roster, 2024)
        model = engine.compute("testk-01")
        assert model is not None
        assert isinstance(model, KickingModel)
        assert "0_39" in model.fg_make_rate
        assert "40_49" in model.fg_make_rate
        assert "50_plus" in model.fg_make_rate
        assert 0.0 <= model.xp_rate <= 1.0

    def test_zero_attempts_in_bucket_uses_league_avg(self, pff_dir, loader):
        """Distance bucket with zero personal attempts inherits league average."""
        _write_field_goal_summary(pff_dir, 2024, [
            {"player_id": 100, "player": "Short K", "team": "MIA",
             "n_games": 10, "thirty_attempts": 2, "thirty_made": 2,
             "forty_attempts": 0, "forty_made": 0,
             "fifty_attempts": 0, "fifty_made": 0,
             "pat_attempts": 3, "pat_made": 3},
            {"player_id": 200, "player": "Other K", "team": "NYJ",
             "n_games": 10, "thirty_attempts": 2, "thirty_made": 1,
             "forty_attempts": 1, "forty_made": 1,
             "fifty_attempts": 1, "fifty_made": 0,
             "pat_attempts": 3, "pat_made": 3},
        ])
        roster = _make_kicker_roster([
            {"player_id": "shortk-01", "player_name": "Short K", "team": "MIA", "pff_id": 100},
        ])
        cfg = KickerConfig(prior_strength=20, min_attempts=1)
        engine = KickerEngine(cfg, loader, [2024])
        engine.build_crosswalk(roster, 2024)
        model = engine.compute("shortk-01")
        assert model is not None
        # 0 personal 40-49 attempts, 0 personal 50+ attempts
        # Rate should equal league average (prior dominates)
        assert model.fg_make_rate["40_49"] == pytest.approx(engine._league_rates["40_49"], abs=0.001)
        assert model.fg_make_rate["50_plus"] == pytest.approx(engine._league_rates["50_plus"], abs=0.001)

    def test_crosswalk_pff_id_match(self, pff_dir, loader):
        """Kicker crosswalk Layer 1: pff_id direct match."""
        _write_field_goal_summary(pff_dir, 2024, [
            {"player_id": 555, "player": "Test Kicker", "team": "KC",
             "n_games": 5, "thirty_attempts": 2, "thirty_made": 2,
             "pat_attempts": 2, "pat_made": 2},
        ])
        roster = _make_kicker_roster([
            {"player_id": "kicker-nfl-01", "player_name": "Test Kicker", "team": "KC", "pff_id": 555},
        ])
        cfg = KickerConfig(min_attempts=1)
        engine = KickerEngine(cfg, loader, [2024])
        engine.build_crosswalk(roster, 2024)
        assert engine._nfl_to_pff.get("kicker-nfl-01") == 555
        model = engine.compute("kicker-nfl-01")
        assert model is not None

    def test_crosswalk_name_team_fallback(self, pff_dir, loader):
        """Kicker crosswalk Layer 2: name + team match when no pff_id."""
        _write_field_goal_summary(pff_dir, 2024, [
            {"player_id": 666, "player": "Fallback Kicker", "team": "SEA",
             "n_games": 5, "thirty_attempts": 2, "thirty_made": 2,
             "pat_attempts": 2, "pat_made": 2},
        ])
        roster = pl.DataFrame({
            "player_id": ["kicker-nfl-02"],
            "player_name": ["Fallback Kicker"],
            "team": ["SEA"],
            "position": ["K"],
            "pff_id": [None],
        })
        cfg = KickerConfig(min_attempts=1)
        engine = KickerEngine(cfg, loader, [2024])
        engine.build_crosswalk(roster, 2024)
        assert engine._nfl_to_pff.get("kicker-nfl-02") == 666

    def test_no_pff_data_empty_engine(self, pff_dir, loader):
        """No field_goal_summary files → engine returns None for all kickers."""
        roster = _make_kicker_roster([
            {"player_id": "k-01", "player_name": "Ghost", "team": "KC", "pff_id": 999},
        ])
        cfg = KickerConfig()
        engine = KickerEngine(cfg, loader, [2024])
        engine.build_crosswalk(roster, 2024)
        assert engine.compute("k-01") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_pff/test_kicker.py::TestKickerEngineShrinkage -v`
Expected: FAIL with ImportError (KickerEngine not defined)

- [ ] **Step 3: Implement KickerEngine**

Create `src/fantasy_sim/data/pff/kicker.py`:

```python
"""PFF Kicker Engine — per-kicker FG accuracy with Bayesian shrinkage.

Replaces the team-level KickingModel placeholder with per-kicker accuracy
rates computed from PFF field_goal_summary data. Uses Bayesian shrinkage
toward league-average rates to stabilize small sample sizes.
"""

from __future__ import annotations

import logging

import polars as pl

from fantasy_sim.data.pff.loader import PffLoader
from fantasy_sim.data.pff.models import KickerConfig
from fantasy_sim.models.distributions import KickingModel

logger = logging.getLogger(__name__)

# PFF distance buckets that map to sim's "0_39" bucket
_SHORT_BUCKETS = ("one", "twenty", "thirty")


class KickerEngine:
    """Computes per-kicker KickingModel from PFF field goal accuracy data.

    Uses Bayesian shrinkage: each kicker's rate is blended with the league
    average weighted by prior_strength (pseudo-attempts). High-volume kickers
    are dominated by personal data; low-volume kickers stay near league avg.
    """

    def __init__(
        self,
        config: KickerConfig,
        pff_loader: PffLoader,
        training_seasons: list[int],
    ) -> None:
        self._config = config
        self._data = pff_loader.load_facet("field_goal_summary", training_seasons)
        self._league_rates = self._compute_league_rates()
        self._nfl_to_pff: dict[str, int] = {}
        self._pff_to_nfl: dict[int, str] = {}

    def build_crosswalk(self, roster: pl.DataFrame, season: int) -> None:
        """Build kicker crosswalk (nflverse ↔ PFF) from roster data.

        Layer 1: nflverse roster pff_id direct match.
        Layer 2: exact name + team fallback for unmatched.
        """
        if self._data.is_empty() or roster.is_empty():
            return

        pff_kickers = self._data.select(
            ["player_id", "player", "team"]
        ).unique(subset=["player_id"])

        if pff_kickers.is_empty():
            return

        # --- Layer 1: pff_id match ---
        if "pff_id" in roster.columns:
            kicker_roster = (
                roster
                .filter(pl.col("position") == "K")
                .filter(pl.col("pff_id").is_not_null())
                .with_columns(
                    pl.col("pff_id").cast(pl.Utf8).cast(pl.Int64, strict=False).alias("_pff_id_int")
                )
                .filter(pl.col("_pff_id_int").is_not_null())
                .select(["player_id", "_pff_id_int"])
                .unique(subset=["_pff_id_int"])
            )

            matched = pff_kickers.join(
                kicker_roster, left_on="player_id", right_on="_pff_id_int", how="inner",
            )
            for row in matched.iter_rows(named=True):
                self._pff_to_nfl[row["player_id"]] = row["player_id_right"]
                self._nfl_to_pff[row["player_id_right"]] = row["player_id"]

        # --- Layer 2: name + team fallback ---
        unmatched = pff_kickers.filter(
            ~pl.col("player_id").is_in(list(self._pff_to_nfl.keys()))
        )
        if not unmatched.is_empty():
            kicker_lookup = (
                roster.filter(pl.col("position") == "K")
                .select(["player_id", "player_name", "team"])
                .unique(subset=["player_id"])
            )
            name_matched = unmatched.join(
                kicker_lookup, left_on=["player", "team"],
                right_on=["player_name", "team"], how="inner",
            )
            for row in name_matched.iter_rows(named=True):
                self._pff_to_nfl[row["player_id"]] = row["player_id_right"]
                self._nfl_to_pff[row["player_id_right"]] = row["player_id"]

        logger.info(
            "Kicker crosswalk: %d/%d matched",
            len(self._pff_to_nfl), pff_kickers.height,
        )

    def _compute_league_rates(self) -> dict[str, float]:
        """Compute league-average FG rates by sim distance bucket."""
        if self._data.is_empty():
            return {"0_39": 0.90, "40_49": 0.84, "50_plus": 0.67, "xp": 0.95}

        short_att, short_made = 0, 0
        for bucket in _SHORT_BUCKETS:
            att_col, made_col = f"{bucket}_attempts", f"{bucket}_made"
            if att_col in self._data.columns and made_col in self._data.columns:
                short_att += self._data[att_col].fill_null(0).sum()
                short_made += self._data[made_col].fill_null(0).sum()

        def _safe_rate(made: int, att: int, fallback: float) -> float:
            return made / att if att > 0 else fallback

        forty_att = self._data["forty_attempts"].fill_null(0).sum() if "forty_attempts" in self._data.columns else 0
        forty_made = self._data["forty_made"].fill_null(0).sum() if "forty_made" in self._data.columns else 0
        fifty_att = self._data["fifty_attempts"].fill_null(0).sum() if "fifty_attempts" in self._data.columns else 0
        fifty_made = self._data["fifty_made"].fill_null(0).sum() if "fifty_made" in self._data.columns else 0
        pat_att = self._data["pat_attempts"].fill_null(0).sum() if "pat_attempts" in self._data.columns else 0
        pat_made = self._data["pat_made"].fill_null(0).sum() if "pat_made" in self._data.columns else 0

        return {
            "0_39": _safe_rate(short_made, short_att, 0.90),
            "40_49": _safe_rate(forty_made, forty_att, 0.84),
            "50_plus": _safe_rate(fifty_made, fifty_att, 0.67),
            "xp": _safe_rate(pat_made, pat_att, 0.95),
        }

    def compute(self, kicker_player_id: str) -> KickingModel | None:
        """Return per-kicker KickingModel with Bayesian-shrunk rates, or None.

        Takes a nflverse player_id. Returns None if the kicker isn't in the
        crosswalk or has fewer than min_attempts total FG attempts.
        """
        pff_id = self._nfl_to_pff.get(kicker_player_id)
        if pff_id is None:
            return None

        kicker_data = self._data.filter(pl.col("player_id") == pff_id)
        if kicker_data.is_empty():
            return None

        # Check min_attempts (FGs only, not PATs)
        total_fg_att = 0
        for bucket in list(_SHORT_BUCKETS) + ["forty", "fifty"]:
            att_col = f"{bucket}_attempts"
            if att_col in kicker_data.columns:
                total_fg_att += kicker_data[att_col].fill_null(0).sum()
        if total_fg_att < self._config.min_attempts:
            return None

        prior = self._config.prior_strength

        def _shrink(made: int, att: int, league_key: str) -> float:
            league = self._league_rates[league_key]
            return (made + prior * league) / (att + prior)

        # 0_39: weighted combination of short buckets
        short_att, short_made = 0, 0
        for bucket in _SHORT_BUCKETS:
            att_col, made_col = f"{bucket}_attempts", f"{bucket}_made"
            if att_col in kicker_data.columns and made_col in kicker_data.columns:
                short_att += kicker_data[att_col].fill_null(0).sum()
                short_made += kicker_data[made_col].fill_null(0).sum()

        forty_att = kicker_data["forty_attempts"].fill_null(0).sum() if "forty_attempts" in kicker_data.columns else 0
        forty_made = kicker_data["forty_made"].fill_null(0).sum() if "forty_made" in kicker_data.columns else 0
        fifty_att = kicker_data["fifty_attempts"].fill_null(0).sum() if "fifty_attempts" in kicker_data.columns else 0
        fifty_made = kicker_data["fifty_made"].fill_null(0).sum() if "fifty_made" in kicker_data.columns else 0
        pat_att = kicker_data["pat_attempts"].fill_null(0).sum() if "pat_attempts" in kicker_data.columns else 0
        pat_made = kicker_data["pat_made"].fill_null(0).sum() if "pat_made" in kicker_data.columns else 0

        return KickingModel(
            fg_make_rate={
                "0_39": float(_shrink(short_made, short_att, "0_39")),
                "40_49": float(_shrink(forty_made, forty_att, "40_49")),
                "50_plus": float(_shrink(fifty_made, fifty_att, "50_plus")),
            },
            xp_rate=float(_shrink(pat_made, pat_att, "xp")),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_pff/test_kicker.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/pff/kicker.py tests/test_data/test_pff/test_kicker.py
git commit -m "feat(pff): add KickerEngine with Bayesian shrinkage per-kicker accuracy"
```

---

### Task 3: DstBaselineEngine — Core Logic

**Files:**
- Create: `src/fantasy_sim/data/pff/dst_baseline.py`
- Test: `tests/test_data/test_pff/test_dst_baseline.py`

- [ ] **Step 1: Write failing tests for fumble rate factor and defensive TD rates**

Add to `tests/test_data/test_pff/test_dst_baseline.py`:

```python
from fantasy_sim.data.pff.loader import PffLoader
from fantasy_sim.data.pff.models import DstBaselineConfig, DstBaselineContext
from fantasy_sim.data.pff.dst_baseline import DstBaselineEngine


# ---------- Fixtures ----------

@pytest.fixture
def pff_dir(tmp_path):
    d = tmp_path / "pff" / "processed" / "nfl"
    d.mkdir(parents=True)
    return d


@pytest.fixture
def loader(pff_dir):
    return PffLoader(pff_dir)


def _write_defense_summary(pff_dir, season, teams):
    """Write defense_summary parquet with team-level defensive stats.

    teams: list of dicts with keys:
        team, n_players, n_games, forced_fumbles, fumble_recoveries,
        fumble_recovery_touchdowns, interceptions, interception_touchdowns,
        snap_counts_defense
    """
    rows = {
        "player_id": [], "player": [], "team": [], "position": [],
        "season": [], "week": [], "game_id": [],
        "jersey_number": [], "franchise_id": [], "status": [],
        "grades_defense": [], "grades_pass_rush_defense": [],
        "grades_run_defense": [], "grades_coverage_defense": [],
        "grades_tackle": [], "grades_defense_penalty": [],
        "sacks": [], "hits": [], "hurries": [], "total_pressures": [],
        "batted_passes": [],
        "interceptions": [], "interception_touchdowns": [],
        "pass_break_ups": [], "targets": [], "receptions": [],
        "yards": [], "yards_per_reception": [], "catch_rate": [],
        "yards_after_catch": [], "longest": [],
        "qb_rating_against": [], "touchdowns": [],
        "tackles": [], "assists": [], "stops": [],
        "tackles_for_loss": [], "missed_tackles": [],
        "missed_tackle_rate": [], "safeties": [],
        "forced_fumbles": [], "fumble_recoveries": [],
        "fumble_recovery_touchdowns": [],
        "penalties": [], "declined_penalties": [],
        "snap_counts_defense": [], "snap_counts_pass_rush": [],
        "snap_counts_run_defense": [], "snap_counts_coverage": [],
        "snap_counts_offball": [], "snap_counts_box": [],
        "snap_counts_dl": [], "snap_counts_dl_over_t": [],
        "snap_counts_dl_a_gap": [], "snap_counts_dl_b_gap": [],
        "snap_counts_dl_outside_t": [],
        "snap_counts_corner": [], "snap_counts_fs": [],
        "snap_counts_slot": [],
    }
    pid = 2000
    gid = 7000
    for td in teams:
        n_players = td.get("n_players", 3)
        n_games = td.get("n_games", 8)
        ff_per = td.get("forced_fumbles", 0)
        fr_per = td.get("fumble_recoveries", 0)
        frtd_per = td.get("fumble_recovery_touchdowns", 0)
        ints_per = td.get("interceptions", 0)
        int_tds_per = td.get("interception_touchdowns", 0)
        snaps_per = td.get("snap_counts_defense", 50)
        for g in range(n_games):
            for p in range(n_players):
                rows["player_id"].append(pid + p)
                rows["player"].append(f"Player_{pid + p}")
                rows["team"].append(td["team"])
                rows["position"].append("LB")
                rows["season"].append(season)
                rows["week"].append(g + 1)
                rows["game_id"].append(gid + g)
                rows["jersey_number"].append(str(50 + p))
                rows["franchise_id"].append(1)
                rows["status"].append("S")
                for gc in ("grades_defense", "grades_pass_rush_defense",
                           "grades_run_defense", "grades_coverage_defense",
                           "grades_tackle", "grades_defense_penalty"):
                    rows[gc].append(60.0)
                rows["sacks"].append(0)
                rows["hits"].append(0)
                rows["hurries"].append(0)
                rows["total_pressures"].append(0)
                rows["batted_passes"].append(0)
                # Distribute counting stats to first player only
                rows["interceptions"].append(ints_per if p == 0 else 0)
                rows["interception_touchdowns"].append(int_tds_per if p == 0 else 0)
                rows["pass_break_ups"].append(0)
                rows["targets"].append(0)
                rows["receptions"].append(0)
                rows["yards"].append(0)
                rows["yards_per_reception"].append(0.0)
                rows["catch_rate"].append(0.0)
                rows["yards_after_catch"].append(0)
                rows["longest"].append(0)
                rows["qb_rating_against"].append(0.0)
                rows["touchdowns"].append(0)
                rows["tackles"].append(3)
                rows["assists"].append(1)
                rows["stops"].append(1)
                rows["tackles_for_loss"].append(0)
                rows["missed_tackles"].append(0)
                rows["missed_tackle_rate"].append(0.0)
                rows["safeties"].append(0)
                rows["forced_fumbles"].append(ff_per if p == 0 else 0)
                rows["fumble_recoveries"].append(fr_per if p == 0 else 0)
                rows["fumble_recovery_touchdowns"].append(frtd_per if p == 0 else 0)
                rows["penalties"].append(0)
                rows["declined_penalties"].append(0)
                rows["snap_counts_defense"].append(snaps_per)
                for sc in ("snap_counts_pass_rush", "snap_counts_run_defense",
                           "snap_counts_coverage", "snap_counts_offball",
                           "snap_counts_box", "snap_counts_dl",
                           "snap_counts_dl_over_t", "snap_counts_dl_a_gap",
                           "snap_counts_dl_b_gap", "snap_counts_dl_outside_t",
                           "snap_counts_corner", "snap_counts_fs", "snap_counts_slot"):
                    rows[sc].append(10)
            pid += n_players
            gid += 1

    df = pl.DataFrame(rows)
    df.write_parquet(pff_dir / f"defense_summary_{season}.parquet")


class TestDstBaselineFumbleRate:
    """Test fumble rate factor from forced fumble quality."""

    def test_elite_defense_higher_fumble_factor(self, pff_dir, loader):
        """Team with many forced fumbles should get factor > 1.0."""
        _write_defense_summary(pff_dir, 2024, [
            {"team": "PIT", "n_games": 8, "forced_fumbles": 3, "fumble_recoveries": 2,
             "snap_counts_defense": 50, "interceptions": 1, "interception_touchdowns": 0,
             "fumble_recovery_touchdowns": 0},
            {"team": "CHI", "n_games": 8, "forced_fumbles": 0, "fumble_recoveries": 0,
             "snap_counts_defense": 50, "interceptions": 1, "interception_touchdowns": 0,
             "fumble_recovery_touchdowns": 0},
            {"team": "DAL", "n_games": 8, "forced_fumbles": 1, "fumble_recoveries": 1,
             "snap_counts_defense": 50, "interceptions": 1, "interception_touchdowns": 0,
             "fumble_recovery_touchdowns": 0},
        ])
        cfg = DstBaselineConfig(sensitivities={"fumble_rate": 0.06}, clamp=[0.85, 1.15], min_games=4)
        engine = DstBaselineEngine(cfg, loader, [2024])
        ctx = engine.compute("PIT", 2024, max_week=18)
        assert ctx.fumble_rate_factor > 1.0

    def test_weak_defense_lower_fumble_factor(self, pff_dir, loader):
        """Team with zero forced fumbles should get factor < 1.0."""
        _write_defense_summary(pff_dir, 2024, [
            {"team": "PIT", "n_games": 8, "forced_fumbles": 3, "fumble_recoveries": 2,
             "snap_counts_defense": 50, "interceptions": 1, "interception_touchdowns": 0,
             "fumble_recovery_touchdowns": 0},
            {"team": "CHI", "n_games": 8, "forced_fumbles": 0, "fumble_recoveries": 0,
             "snap_counts_defense": 50, "interceptions": 1, "interception_touchdowns": 0,
             "fumble_recovery_touchdowns": 0},
            {"team": "DAL", "n_games": 8, "forced_fumbles": 1, "fumble_recoveries": 1,
             "snap_counts_defense": 50, "interceptions": 1, "interception_touchdowns": 0,
             "fumble_recovery_touchdowns": 0},
        ])
        cfg = DstBaselineConfig(sensitivities={"fumble_rate": 0.06}, clamp=[0.85, 1.15], min_games=4)
        engine = DstBaselineEngine(cfg, loader, [2024])
        ctx = engine.compute("CHI", 2024, max_week=18)
        assert ctx.fumble_rate_factor < 1.0

    def test_clamp_enforcement(self, pff_dir, loader):
        """Extreme z-scores should be clamped to configured bounds."""
        _write_defense_summary(pff_dir, 2024, [
            {"team": "KC", "n_games": 8, "forced_fumbles": 10, "fumble_recoveries": 8,
             "snap_counts_defense": 50, "interceptions": 1, "interception_touchdowns": 0,
             "fumble_recovery_touchdowns": 0},
            {"team": "LV", "n_games": 8, "forced_fumbles": 0, "fumble_recoveries": 0,
             "snap_counts_defense": 50, "interceptions": 1, "interception_touchdowns": 0,
             "fumble_recovery_touchdowns": 0},
        ])
        cfg = DstBaselineConfig(
            sensitivities={"fumble_rate": 0.50},  # very high sensitivity
            clamp=[0.85, 1.15], min_games=4,
        )
        engine = DstBaselineEngine(cfg, loader, [2024])
        ctx_high = engine.compute("KC", 2024, max_week=18)
        ctx_low = engine.compute("LV", 2024, max_week=18)
        assert ctx_high.fumble_rate_factor <= 1.15
        assert ctx_low.fumble_rate_factor >= 0.85


class TestDstBaselineDefensiveTdRates:
    """Test Bayesian shrinkage on defensive TD rates."""

    def test_high_pick_six_team(self, pff_dir, loader):
        """Team with many pick-sixes gets int_return_td_rate > 0.20."""
        _write_defense_summary(pff_dir, 2024, [
            {"team": "BUF", "n_games": 8, "interceptions": 2,
             "interception_touchdowns": 1,  # 50% raw rate
             "forced_fumbles": 1, "fumble_recoveries": 1,
             "fumble_recovery_touchdowns": 0, "snap_counts_defense": 50},
            {"team": "MIA", "n_games": 8, "interceptions": 1,
             "interception_touchdowns": 0,
             "forced_fumbles": 1, "fumble_recoveries": 1,
             "fumble_recovery_touchdowns": 0, "snap_counts_defense": 50},
        ])
        cfg = DstBaselineConfig(prior_strength=10, min_games=4)
        engine = DstBaselineEngine(cfg, loader, [2024])
        ctx = engine.compute("BUF", 2024, max_week=18)
        # BUF: 8 INTs (2/game * 8), 8 INT TDs (1/game * 8) → raw 100%
        # Shrunk: (8 + 10*0.20) / (8 + 10) = 10/18 ≈ 0.556
        assert ctx.int_return_td_rate > 0.20

    def test_shrinkage_prevents_extreme_rates(self, pff_dir, loader):
        """Single INT with pick-six should not produce 100% rate."""
        _write_defense_summary(pff_dir, 2024, [
            {"team": "NYJ", "n_games": 1, "interceptions": 1,
             "interception_touchdowns": 1,  # 1/1 = 100% raw
             "forced_fumbles": 0, "fumble_recoveries": 0,
             "fumble_recovery_touchdowns": 0, "snap_counts_defense": 50},
            {"team": "NE", "n_games": 8, "interceptions": 1,
             "interception_touchdowns": 0,
             "forced_fumbles": 1, "fumble_recoveries": 1,
             "fumble_recovery_touchdowns": 0, "snap_counts_defense": 50},
        ])
        cfg = DstBaselineConfig(prior_strength=10, min_games=4)
        engine = DstBaselineEngine(cfg, loader, [2024])
        ctx = engine.compute("NYJ", 2024, max_week=18)
        # NYJ: 1 INT, 1 INT TD → raw 100%
        # Shrunk: (1 + 10*0.20) / (1 + 10) = 3/11 ≈ 0.273
        assert ctx.int_return_td_rate < 0.50  # far from 100%
        assert ctx.int_return_td_rate > 0.20  # above default

    def test_no_turnovers_returns_default_rates(self, pff_dir, loader):
        """Team with no INTs/fumble recoveries gets default rates."""
        _write_defense_summary(pff_dir, 2024, [
            {"team": "JAX", "n_games": 8, "interceptions": 0,
             "interception_touchdowns": 0, "forced_fumbles": 0,
             "fumble_recoveries": 0, "fumble_recovery_touchdowns": 0,
             "snap_counts_defense": 50},
            {"team": "HOU", "n_games": 8, "interceptions": 1,
             "interception_touchdowns": 0, "forced_fumbles": 1,
             "fumble_recoveries": 1, "fumble_recovery_touchdowns": 0,
             "snap_counts_defense": 50},
        ])
        cfg = DstBaselineConfig(prior_strength=10, min_games=4)
        engine = DstBaselineEngine(cfg, loader, [2024])
        ctx = engine.compute("JAX", 2024, max_week=18)
        # 0 INTs, 0 recs → (0 + 10*default) / (0 + 10) = default
        assert ctx.int_return_td_rate == pytest.approx(0.20, abs=0.001)
        assert ctx.fumble_return_td_rate == pytest.approx(0.10, abs=0.001)

    def test_no_data_returns_neutral(self, pff_dir, loader):
        """No defense_summary data → all defaults."""
        cfg = DstBaselineConfig()
        engine = DstBaselineEngine(cfg, loader, [2024])
        ctx = engine.compute("KC", 2024, max_week=18)
        assert ctx.fumble_rate_factor == 1.0
        assert ctx.int_return_td_rate == 0.20
        assert ctx.fumble_return_td_rate == 0.10

    def test_unknown_team_returns_neutral(self, pff_dir, loader):
        """Unknown team with no data returns neutral context."""
        _write_defense_summary(pff_dir, 2024, [
            {"team": "KC", "n_games": 8, "interceptions": 1,
             "interception_touchdowns": 0, "forced_fumbles": 1,
             "fumble_recoveries": 1, "fumble_recovery_touchdowns": 0,
             "snap_counts_defense": 50},
            {"team": "BUF", "n_games": 8, "interceptions": 1,
             "interception_touchdowns": 0, "forced_fumbles": 1,
             "fumble_recoveries": 1, "fumble_recovery_touchdowns": 0,
             "snap_counts_defense": 50},
        ])
        cfg = DstBaselineConfig(min_games=4)
        engine = DstBaselineEngine(cfg, loader, [2024])
        ctx = engine.compute("FAKE", 2024, max_week=18)
        assert ctx.fumble_rate_factor == 1.0
        assert ctx.int_return_td_rate == 0.20
        assert ctx.fumble_return_td_rate == 0.10

    def test_early_season_blend_with_previous(self, pff_dir, loader):
        """< min_games in target season blends with previous season."""
        # Previous season: strong defense
        _write_defense_summary(pff_dir, 2023, [
            {"team": "SF", "n_games": 17, "interceptions": 2,
             "interception_touchdowns": 1, "forced_fumbles": 3,
             "fumble_recoveries": 2, "fumble_recovery_touchdowns": 0,
             "snap_counts_defense": 50},
            {"team": "LAR", "n_games": 17, "interceptions": 1,
             "interception_touchdowns": 0, "forced_fumbles": 1,
             "fumble_recoveries": 1, "fumble_recovery_touchdowns": 0,
             "snap_counts_defense": 50},
        ])
        # Current season: only 2 games
        _write_defense_summary(pff_dir, 2024, [
            {"team": "SF", "n_games": 2, "interceptions": 0,
             "interception_touchdowns": 0, "forced_fumbles": 0,
             "fumble_recoveries": 0, "fumble_recovery_touchdowns": 0,
             "snap_counts_defense": 50},
            {"team": "LAR", "n_games": 2, "interceptions": 0,
             "interception_touchdowns": 0, "forced_fumbles": 0,
             "fumble_recoveries": 0, "fumble_recovery_touchdowns": 0,
             "snap_counts_defense": 50},
        ])
        cfg = DstBaselineConfig(prior_strength=10, min_games=4)
        engine = DstBaselineEngine(cfg, loader, [2023, 2024])
        ctx = engine.compute("SF", 2024, max_week=18)
        # Should blend 2024 (2 games, 0 INTs) with 2023 (17 games, elite stats)
        # INT TD rate should be pulled above 0.20 by 2023 data
        assert ctx.int_return_td_rate > 0.20
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_pff/test_dst_baseline.py::TestDstBaselineFumbleRate tests/test_data/test_pff/test_dst_baseline.py::TestDstBaselineDefensiveTdRates -v`
Expected: FAIL with ImportError (DstBaselineEngine not defined)

- [ ] **Step 3: Implement DstBaselineEngine**

Create `src/fantasy_sim/data/pff/dst_baseline.py`:

```python
"""DST Baseline Engine — fumble rate and defensive TD rate adjustments.

Complements the matchup engine by adjusting factors it doesn't cover:
- fumble_rate (opposing offense) via forced fumble quality z-score
- int_return_td_rate (team-specific, Bayesian shrinkage from 0.20 constant)
- fumble_return_td_rate (team-specific, Bayesian shrinkage from 0.10 constant)
"""

from __future__ import annotations

import logging

import numpy as np
import polars as pl

from fantasy_sim.data.pff.loader import PffLoader
from fantasy_sim.data.pff.matchup import compute_factor
from fantasy_sim.data.pff.models import DstBaselineConfig, DstBaselineContext

logger = logging.getLogger(__name__)

DEFAULT_INT_RETURN_TD_RATE = 0.20
DEFAULT_FUMBLE_RETURN_TD_RATE = 0.10


class DstBaselineEngine:
    """Computes team-level DST baseline adjustments from PFF defense_summary."""

    def __init__(
        self,
        config: DstBaselineConfig,
        pff_loader: PffLoader,
        seasons: list[int],
    ) -> None:
        self._config = config
        self._loader = pff_loader
        self._seasons = seasons
        self._cache: dict[str, pl.DataFrame] = {}

    def _load_cached(self, seasons: list[int]) -> pl.DataFrame:
        key = "_".join(str(s) for s in sorted(seasons))
        if key not in self._cache:
            self._cache[key] = self._loader.load_facet("defense_summary", seasons)
        return self._cache[key]

    def _get_team_game_stats(
        self,
        df: pl.DataFrame,
        team: str,
        target_season: int,
        max_week: int | None,
    ) -> pl.DataFrame:
        """Aggregate player-level rows to team-game totals."""
        filtered = df.filter(pl.col("season") == target_season)
        if max_week is not None:
            filtered = filtered.filter(pl.col("week") < max_week)
        filtered = filtered.filter(pl.col("team") == team)
        if filtered.is_empty():
            return pl.DataFrame()

        return filtered.group_by(["team", "season", "week"]).agg([
            pl.col("forced_fumbles").fill_null(0).sum(),
            pl.col("fumble_recoveries").fill_null(0).sum(),
            pl.col("fumble_recovery_touchdowns").fill_null(0).sum(),
            pl.col("interceptions").fill_null(0).sum(),
            pl.col("interception_touchdowns").fill_null(0).sum(),
            pl.col("snap_counts_defense").fill_null(0).sum(),
        ])

    def _compute_all_team_fumble_rates(
        self,
        df: pl.DataFrame,
        target_season: int,
        max_week: int | None,
    ) -> dict[str, float]:
        """Compute forced fumble rate per snap for each team."""
        filtered = df.filter(pl.col("season") == target_season)
        if max_week is not None:
            filtered = filtered.filter(pl.col("week") < max_week)
        if filtered.is_empty():
            return {}

        team_stats = filtered.group_by("team").agg([
            pl.col("forced_fumbles").fill_null(0).sum().alias("total_ff"),
            pl.col("snap_counts_defense").fill_null(0).sum().alias("total_snaps"),
        ])

        result: dict[str, float] = {}
        for row in team_stats.iter_rows(named=True):
            snaps = row["total_snaps"]
            if snaps > 0:
                result[row["team"]] = row["total_ff"] / snaps
        return result

    def compute(
        self,
        defense_team: str,
        target_season: int,
        max_week: int | None = None,
    ) -> DstBaselineContext:
        """Compute DST baseline adjustments for one defense."""
        df = self._load_cached(self._seasons)
        if df.is_empty():
            return DstBaselineContext()

        team_games = self._get_team_game_stats(df, defense_team, target_season, max_week)
        n_games = team_games.height if not team_games.is_empty() else 0

        # Early-season blend: pull previous season if < min_games
        prev_games = None
        if n_games < self._config.min_games and (target_season - 1) in self._seasons:
            prev_games = self._get_team_game_stats(
                df, defense_team, target_season - 1, None,
            )
            if prev_games.is_empty():
                prev_games = None

        # --- Fumble rate factor (z-score) ---
        all_rates = self._compute_all_team_fumble_rates(df, target_season, max_week)
        fumble_factor = 1.0

        if all_rates and defense_team in all_rates:
            league_rates = list(all_rates.values())
            if len(league_rates) >= 2:
                league_mean = float(np.mean(league_rates))
                league_std = float(np.std(league_rates, ddof=1))
                fumble_factor = compute_factor(
                    all_rates[defense_team],
                    league_mean,
                    league_std,
                    self._config.sensitivities.get("fumble_rate", 0.06),
                    tuple(self._config.clamp),
                )

        # --- Defensive TD rates (Bayesian shrinkage) ---
        prior = self._config.prior_strength

        if not team_games.is_empty():
            team_ints = int(team_games["interceptions"].sum())
            team_int_tds = int(team_games["interception_touchdowns"].sum())
            team_fum_recs = int(team_games["fumble_recoveries"].sum())
            team_fum_tds = int(team_games["fumble_recovery_touchdowns"].sum())
        else:
            team_ints, team_int_tds = 0, 0
            team_fum_recs, team_fum_tds = 0, 0

        # Blend with previous season if early
        if prev_games is not None and n_games < self._config.min_games:
            blend_w = n_games / self._config.min_games  # 0..1 linear ramp
            prev_ints = int(prev_games["interceptions"].sum())
            prev_int_tds = int(prev_games["interception_touchdowns"].sum())
            prev_fum_recs = int(prev_games["fumble_recoveries"].sum())
            prev_fum_tds = int(prev_games["fumble_recovery_touchdowns"].sum())
            team_ints = round(team_ints * blend_w + prev_ints * (1 - blend_w))
            team_int_tds = round(team_int_tds * blend_w + prev_int_tds * (1 - blend_w))
            team_fum_recs = round(team_fum_recs * blend_w + prev_fum_recs * (1 - blend_w))
            team_fum_tds = round(team_fum_tds * blend_w + prev_fum_tds * (1 - blend_w))

        denom_int = team_ints + prior
        int_td_rate = (
            (team_int_tds + prior * DEFAULT_INT_RETURN_TD_RATE) / denom_int
            if denom_int > 0 else DEFAULT_INT_RETURN_TD_RATE
        )

        denom_fum = team_fum_recs + prior
        fum_td_rate = (
            (team_fum_tds + prior * DEFAULT_FUMBLE_RETURN_TD_RATE) / denom_fum
            if denom_fum > 0 else DEFAULT_FUMBLE_RETURN_TD_RATE
        )

        return DstBaselineContext(
            fumble_rate_factor=fumble_factor,
            int_return_td_rate=float(int_td_rate),
            fumble_return_td_rate=float(fum_td_rate),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_pff/test_dst_baseline.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/pff/dst_baseline.py tests/test_data/test_pff/test_dst_baseline.py
git commit -m "feat(pff): add DstBaselineEngine with fumble rate factor and defensive TD rates"
```

---

### Task 4: game_sim.py — Use Team-Specific Defensive TD Rates

**Files:**
- Modify: `src/fantasy_sim/engine/game_sim.py:119,163-197`
- Test: `tests/test_engine/test_game_sim.py` (add test)

- [ ] **Step 1: Write failing test for team-specific defensive TD rates**

Add to a new test class in `tests/test_data/test_pff/test_dst_baseline.py`:

```python
class TestGameSimDefensiveTdRates:
    """Test that game_sim uses team-specific defensive TD rates."""

    def test_update_box_scores_uses_custom_int_td_rate(self):
        """_update_box_scores should use the passed int_return_td_rate."""
        from fantasy_sim.engine.game_sim import _update_box_scores
        from fantasy_sim.engine.types import TeamBoxScore, PlayResult

        off_box = TeamBoxScore()
        def_box = TeamBoxScore()
        result = PlayResult(play_type="pass", yards=0, is_interception=True)

        rng = np.random.default_rng(42)
        # Run many times with rate=1.0 (guaranteed TD)
        for _ in range(10):
            off = TeamBoxScore()
            defb = TeamBoxScore()
            _update_box_scores(off, defb, result, rng=rng,
                               int_return_td_rate=1.0, fumble_return_td_rate=0.0)
            assert defb.defensive_tds == 1  # guaranteed with rate 1.0

    def test_update_box_scores_uses_custom_fumble_td_rate(self):
        """_update_box_scores should use the passed fumble_return_td_rate."""
        from fantasy_sim.engine.game_sim import _update_box_scores
        from fantasy_sim.engine.types import TeamBoxScore, PlayResult

        result = PlayResult(play_type="run", yards=3, is_fumble=True)

        rng = np.random.default_rng(42)
        for _ in range(10):
            off = TeamBoxScore()
            defb = TeamBoxScore()
            _update_box_scores(off, defb, result, rng=rng,
                               int_return_td_rate=0.0, fumble_return_td_rate=1.0)
            assert defb.defensive_tds == 1  # guaranteed with rate 1.0

    def test_update_box_scores_default_rates_unchanged(self):
        """Without custom rates, behavior matches original constants."""
        from fantasy_sim.engine.game_sim import _update_box_scores, INT_RETURN_TD_RATE, FUMBLE_RETURN_TD_RATE

        # Just verify the defaults still exist as constants
        assert INT_RETURN_TD_RATE == 0.20
        assert FUMBLE_RETURN_TD_RATE == 0.10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data/test_pff/test_dst_baseline.py::TestGameSimDefensiveTdRates -v`
Expected: FAIL — `_update_box_scores` doesn't accept `int_return_td_rate` / `fumble_return_td_rate` params

- [ ] **Step 3: Modify _update_box_scores to accept team-specific rates**

In `src/fantasy_sim/engine/game_sim.py`, update the function signature and body:

Change `_update_box_scores` signature from:
```python
def _update_box_scores(
    off_box: TeamBoxScore,
    def_box: TeamBoxScore,
    result: PlayResult,
    rng: np.random.Generator | None = None,
) -> None:
```
To:
```python
def _update_box_scores(
    off_box: TeamBoxScore,
    def_box: TeamBoxScore,
    result: PlayResult,
    rng: np.random.Generator | None = None,
    int_return_td_rate: float = INT_RETURN_TD_RATE,
    fumble_return_td_rate: float = FUMBLE_RETURN_TD_RATE,
) -> None:
```

Replace the two constant references in the body:
- `rng.random() < INT_RETURN_TD_RATE` → `rng.random() < int_return_td_rate`
- `rng.random() < FUMBLE_RETURN_TD_RATE` → `rng.random() < fumble_return_td_rate`

Update the call site (line ~119) from:
```python
_update_box_scores(off_box, def_box, result, rng=rng)
```
To:
```python
_update_box_scores(
    off_box, def_box, result, rng=rng,
    int_return_td_rate=def_dists.defensive_td_rates.int_return_td_rate,
    fumble_return_td_rate=def_dists.defensive_td_rates.fumble_return_td_rate,
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_data/test_pff/test_dst_baseline.py::TestGameSimDefensiveTdRates -v`
Expected: PASS

- [ ] **Step 5: Run full test suite to verify no regressions**

Run: `uv run pytest tests/ -x -q`
Expected: All pass (existing callers don't pass the new params, so they use the unchanged default constants)

- [ ] **Step 6: Commit**

```bash
git add src/fantasy_sim/engine/game_sim.py tests/test_data/test_pff/test_dst_baseline.py
git commit -m "feat(pff): wire DefensiveTdRates through game_sim _update_box_scores"
```

---

### Task 5: game_context.py — Wire Engines Into build_game()

**Files:**
- Modify: `src/fantasy_sim/data/game_context.py:1-100,466-486`

- [ ] **Step 1: Add engine initialization to GameContextBuilder.__init__**

Add to `src/fantasy_sim/data/game_context.py` after the coverage engine init block (~line 99):

```python
        self._kicker_engine = None
        self._dst_baseline_engine = None

        if self._pff_config.enabled and self._pff_config.kicker.enabled and self._pff_loader:
            from fantasy_sim.data.pff.kicker import KickerEngine
            self._kicker_engine = KickerEngine(
                self._pff_config.kicker, self._pff_loader, [],
            )
            logger.info("PFF kicker engine enabled")

        if self._pff_config.enabled and self._pff_config.dst_baseline.enabled and self._pff_loader:
            from fantasy_sim.data.pff.dst_baseline import DstBaselineEngine
            self._dst_baseline_engine = DstBaselineEngine(
                self._pff_config.dst_baseline, self._pff_loader, [],
            )
            logger.info("PFF DST baseline engine enabled")
```

Note: engines init with empty seasons `[]` — the actual seasons are passed in `build_game()` below to reinitialize with the correct training seasons.

- [ ] **Step 2: Add engine calls to build_game() after coverage block**

In `build_game()`, after the coverage engine block (after line ~484) and before the `return` statement:

```python
        # PFF DST baseline: fumble rate + defensive TD rates
        if self._dst_baseline_engine is not None and target_season and week:
            # Re-create engine with correct seasons if needed
            if self._dst_baseline_engine._seasons != training_seasons:
                from fantasy_sim.data.pff.dst_baseline import DstBaselineEngine
                self._dst_baseline_engine = DstBaselineEngine(
                    self._pff_config.dst_baseline, self._pff_loader,
                    training_seasons + ([target_season] if target_season not in training_seasons else []),
                )
            # Away defense adjusts home offense fumble rate
            home_dst_ctx = self._dst_baseline_engine.compute(
                away_team, target_season, max_week=week,
            )
            away_dst_ctx = self._dst_baseline_engine.compute(
                home_team, target_season, max_week=week,
            )
            if home_dst_ctx.fumble_rate_factor != 1.0:
                home_dists.turnover_rates.fumble_rate *= home_dst_ctx.fumble_rate_factor
            if away_dst_ctx.fumble_rate_factor != 1.0:
                away_dists.turnover_rates.fumble_rate *= away_dst_ctx.fumble_rate_factor
            # Set team-specific defensive TD rates on defending team's dists
            from fantasy_sim.engine.types import DefensiveTdRates
            away_dists.defensive_td_rates = DefensiveTdRates(
                int_return_td_rate=home_dst_ctx.int_return_td_rate,
                fumble_return_td_rate=home_dst_ctx.fumble_return_td_rate,
            )
            home_dists.defensive_td_rates = DefensiveTdRates(
                int_return_td_rate=away_dst_ctx.int_return_td_rate,
                fumble_return_td_rate=away_dst_ctx.fumble_return_td_rate,
            )

        # PFF kicker: replace team-level KickingModel with per-kicker rates
        if self._kicker_engine is not None:
            # Re-create engine with correct seasons if needed
            if self._kicker_engine._data.is_empty() or not self._kicker_engine._nfl_to_pff:
                from fantasy_sim.data.pff.kicker import KickerEngine
                all_seasons = training_seasons + ([target_season] if target_season and target_season not in training_seasons else [])
                self._kicker_engine = KickerEngine(
                    self._pff_config.kicker, self._pff_loader, all_seasons,
                )
                roster_season = target_season or max(training_seasons)
                nfl_roster = self.loader.load_rosters([roster_season])
                self._kicker_engine.build_crosswalk(nfl_roster, roster_season)
            for team_roster, team_dists in [
                (home_roster, home_dists), (away_roster, away_dists),
            ]:
                kicker = next(
                    (p for p in team_roster.players if p.position == "K"), None,
                )
                if kicker is not None:
                    kicker_model = self._kicker_engine.compute(kicker.player_id)
                    if kicker_model is not None:
                        team_dists.kicking = kicker_model
```

- [ ] **Step 3: Add KickerConfig and DstBaselineConfig to game_context.py imports**

Update the import at the top of `game_context.py`:

```python
from fantasy_sim.data.pff.models import PffConfig, MatchupContext, CoverageModifiers
```

No additional imports needed — the engine imports are lazy (inside `if` blocks).

- [ ] **Step 4: Run full test suite**

Run: `uv run pytest tests/ -x -q`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/game_context.py
git commit -m "feat(pff): integrate KickerEngine and DstBaselineEngine into build_game()"
```

---

### Task 6: defaults.yaml Config

**Files:**
- Modify: `config/defaults.yaml`

- [ ] **Step 1: Add kicker and dst_baseline sections to defaults.yaml**

Add after the `coverage:` block in the `pff:` section:

```yaml
  # Per-kicker accuracy from PFF field goal data (Bayesian shrinkage)
  kicker:
    enabled: true
    prior_strength: 20        # pseudo-attempts for Bayesian prior
    min_attempts: 5           # minimum FG attempts to use personal data

  # DST baseline: fumble rate + defensive TD rates (complements matchup engine)
  dst_baseline:
    enabled: true
    sensitivities:
      fumble_rate: 0.06
    prior_strength: 10        # for defensive TD rate Bayesian shrinkage
    min_games: 4
    clamp: [0.85, 1.15]
```

- [ ] **Step 2: Verify config loads correctly**

Run: `uv run python -c "from fantasy_sim.config.loader import load_defaults; cfg = load_defaults(); print(cfg.get('pff', {}).get('kicker')); print(cfg.get('pff', {}).get('dst_baseline'))"`
Expected: Prints both config dicts

- [ ] **Step 3: Commit**

```bash
git add config/defaults.yaml
git commit -m "config: add kicker and dst_baseline PFF engine settings to defaults.yaml"
```

---

### Task 7: A/B Harness Extension

**Files:**
- Modify: `scripts/validate_pff_signal.py:212-341,535-538`

- [ ] **Step 1: Add new modes to _build_pff_config**

In `scripts/validate_pff_signal.py`, add new imports at the top alongside existing ones:

```python
from fantasy_sim.data.pff.models import (
    CoverageConfig, KickerConfig, DstBaselineConfig,
    MatchupConfig, PffConfig, TalentConfig, TeamContextConfig, TierConfig,
)
```

Add new `elif` blocks in `_build_pff_config` before the `else: # "all"` block:

```python
    elif mode == "kicker":
        matchup_cfg = MatchupConfig(enabled=False)
        talent_cfg = TalentConfig(enabled=False)
        tier_cfg = TierConfig(enabled=False)
        tc_cfg = TeamContextConfig(enabled=False)
        cov_cfg = CoverageConfig(enabled=False)
        kicker_cfg = KickerConfig(enabled=True)
        dst_cfg = DstBaselineConfig(enabled=False)
    elif mode == "dst_baseline":
        matchup_cfg = MatchupConfig(enabled=False)
        talent_cfg = TalentConfig(enabled=False)
        tier_cfg = TierConfig(enabled=False)
        tc_cfg = TeamContextConfig(enabled=False)
        cov_cfg = CoverageConfig(enabled=False)
        kicker_cfg = KickerConfig(enabled=False)
        dst_cfg = DstBaselineConfig(enabled=True)
    elif mode == "kicker+dst_baseline":
        matchup_cfg = MatchupConfig(enabled=False)
        talent_cfg = TalentConfig(enabled=False)
        tier_cfg = TierConfig(enabled=False)
        tc_cfg = TeamContextConfig(enabled=False)
        cov_cfg = CoverageConfig(enabled=False)
        kicker_cfg = KickerConfig(enabled=True)
        dst_cfg = DstBaselineConfig(enabled=True)
    elif mode == "kicker+dst_baseline+tier+matchup+coverage":
        matchup_cfg = MatchupConfig(enabled=True)
        talent_cfg = TalentConfig(enabled=False)
        tier_cfg = TierConfig(enabled=True)
        tc_cfg = TeamContextConfig(enabled=False)
        cov_cfg = CoverageConfig(enabled=True)
        kicker_cfg = KickerConfig(enabled=True)
        dst_cfg = DstBaselineConfig(enabled=True)
```

For all existing mode branches, add default disabled kicker/dst configs:
```python
        kicker_cfg = KickerConfig(enabled=False)
        dst_cfg = DstBaselineConfig(enabled=False)
```

Add override handling after the `coverage` overrides block:
```python
    if overrides and "kicker" in overrides:
        for key, val in overrides["kicker"].items():
            if hasattr(kicker_cfg, key):
                setattr(kicker_cfg, key, val)
    if overrides and "dst_baseline" in overrides:
        for key, val in overrides["dst_baseline"].items():
            if hasattr(dst_cfg, key):
                setattr(dst_cfg, key, val)
```

Update the return statement to include kicker and dst_baseline:
```python
    return PffConfig(enabled=True, matchup=matchup_cfg, talent=talent_cfg,
                     tier_engine=tier_cfg, team_context=tc_cfg, coverage=cov_cfg,
                     kicker=kicker_cfg, dst_baseline=dst_cfg)
```

- [ ] **Step 2: Update argparse choices**

Update the `--mode` choices list to include new modes:

```python
        choices=["matchup", "talent", "tier", "matchup+tier",
                 "team_context+tier", "team_context+tier+matchup",
                 "ncaa_rookie+tier", "ncaa_rookie+tier+matchup",
                 "coverage+tier", "coverage+tier+matchup",
                 "kicker", "dst_baseline", "kicker+dst_baseline",
                 "kicker+dst_baseline+tier+matchup+coverage",
                 "all"],
```

Update the help text for `--config-override` to mention kicker and dst_baseline keys.

- [ ] **Step 3: Commit**

```bash
git add scripts/validate_pff_signal.py
git commit -m "feat(pff): add kicker and dst_baseline modes to A/B validation harness"
```

---

### Task 8: Full Integration Test + Cleanup

**Files:**
- Test: `tests/test_data/test_pff/test_kicker.py`
- Test: `tests/test_data/test_pff/test_dst_baseline.py`

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 2: Run a quick smoke test with the CLI**

Run: `uv run fantasy-sim demo --sims 10 --pff`
Expected: Completes without error (demo mode uses synthetic data, PFF layers will log warnings about missing data and fall back gracefully)

- [ ] **Step 3: Final commit with any fixups**

If any fixes were needed, commit them:
```bash
git add -u
git commit -m "fix: address integration test feedback for kicker/DST PFF engines"
```

- [ ] **Step 4: Update CLAUDE.md Current State section**

Add to the Current State list in `CLAUDE.md`:
```
- **PFF Kicker/DST Baseline**: Complete — N tests (total). Per-kicker FG accuracy from PFF field_goal_summary with Bayesian shrinkage replaces placeholder model. DST baseline engine adjusts fumble_rate (z-score) and team-specific defensive TD rates (Bayesian shrinkage) from PFF defense_summary. Non-overlapping with matchup engine. Config in `defaults.yaml` under `pff.kicker` and `pff.dst_baseline`.
```

Update the test count in the Current State section.

- [ ] **Step 5: Commit docs update**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with kicker/DST PFF engine status"
```

# Coverage Matchup Adjustments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-WR coverage matchup adjustments that map each WR to the opposing CB by alignment, then adjust catch_rate and yards_per_reception based on that CB's rolling performance profile.

**Architecture:** New `CoverageEngine` class in `src/fantasy_sim/data/pff/coverage.py` — peer to `MatchupEngine`. Loads `defense_coverage_matchup` parquet, builds CB profiles (outcome stats + grade stabilizer), maps WR alignment to CB alignment, returns per-WR `CoverageModifiers`. Integrated as the last PFF step in `GameContextBuilder.build_game()`.

**Tech Stack:** Python 3.12+, polars, numpy, pytest, YAML config

**Spec:** `docs/superpowers/specs/2026-04-05-coverage-matchup-adjustments-design.md`

---

### Task 1: Data Model + Config

**Files:**
- Modify: `src/fantasy_sim/data/pff/models.py`
- Modify: `src/fantasy_sim/data/pff/config.py`
- Modify: `config/defaults.yaml`
- Test: `tests/test_data/test_pff/test_config.py`

- [ ] **Step 1: Add CoverageModifiers and CoverageConfig to models.py**

Add after `TeamContextConfig`:

```python
@dataclass
class CoverageModifiers:
    """Per-WR modifiers from coverage matchup analysis."""
    catch_rate_modifier: float = 1.0
    ypr_modifier: float = 1.0


@dataclass
class CoverageConfig:
    """Configuration for the coverage matchup engine."""
    enabled: bool = True
    catch_rate_sensitivity: float = 0.04
    ypr_sensitivity: float = 0.04
    min_coverage_targets: int = 20
    min_z_score_targets: int = 10
    min_z_score_population: int = 8
    factor_clamp: tuple[float, float] = (0.95, 1.05)
    min_games: int = 4
```

- [ ] **Step 2: Add coverage field to PffConfig**

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
```

- [ ] **Step 3: Add coverage section to defaults.yaml**

Add after the `matchup:` section (before `talent:`):

```yaml
  coverage:
    enabled: true
    catch_rate_sensitivity: 0.04
    ypr_sensitivity: 0.04
    min_coverage_targets: 20
    min_z_score_targets: 10
    min_z_score_population: 8
    factor_clamp: [0.95, 1.05]
    min_games: 4
```

- [ ] **Step 4: Add coverage parsing to config.py**

Import `CoverageConfig` at the top of `config.py`:

```python
from fantasy_sim.data.pff.models import (
    ArchetypeConfig,
    CoverageConfig,
    MatchupConfig,
    ...
)
```

Add coverage parsing before the `return PffConfig(...)` at the end of `load_pff_config()`:

```python
    cov_raw = pff.get("coverage", {})
    cov_clamp = cov_raw.get("factor_clamp", [0.95, 1.05])
    coverage = CoverageConfig(
        enabled=cov_raw.get("enabled", True),
        catch_rate_sensitivity=cov_raw.get("catch_rate_sensitivity", 0.04),
        ypr_sensitivity=cov_raw.get("ypr_sensitivity", 0.04),
        min_coverage_targets=cov_raw.get("min_coverage_targets", 20),
        min_z_score_targets=cov_raw.get("min_z_score_targets", 10),
        min_z_score_population=cov_raw.get("min_z_score_population", 8),
        factor_clamp=tuple(cov_clamp),
        min_games=cov_raw.get("min_games", 4),
    )
```

And add `coverage=coverage` to the return:

```python
    return PffConfig(
        enabled=pff.get("enabled", False),
        data_dir=pff.get("data_dir"),
        matchup=matchup,
        talent=talent,
        tier_engine=tier_engine,
        team_context=team_context,
        coverage=coverage,
    )
```

- [ ] **Step 5: Write test for config loading**

Add to `tests/test_data/test_pff/test_config.py`:

```python
def test_load_pff_config_coverage():
    """Coverage config is loaded from defaults.yaml."""
    from fantasy_sim.data.pff.config import load_pff_config

    config = {
        "pff": {
            "enabled": True,
            "coverage": {
                "enabled": True,
                "catch_rate_sensitivity": 0.06,
                "ypr_sensitivity": 0.05,
                "min_coverage_targets": 30,
                "min_z_score_targets": 15,
                "min_z_score_population": 10,
                "factor_clamp": [0.93, 1.07],
                "min_games": 3,
            },
        }
    }
    pff = load_pff_config(config)
    assert pff.coverage.enabled is True
    assert pff.coverage.catch_rate_sensitivity == 0.06
    assert pff.coverage.ypr_sensitivity == 0.05
    assert pff.coverage.min_coverage_targets == 30
    assert pff.coverage.min_z_score_targets == 15
    assert pff.coverage.min_z_score_population == 10
    assert pff.coverage.factor_clamp == (0.93, 1.07)
    assert pff.coverage.min_games == 3


def test_load_pff_config_coverage_defaults():
    """Coverage config uses defaults when not specified in yaml."""
    from fantasy_sim.data.pff.config import load_pff_config

    config = {"pff": {"enabled": True}}
    pff = load_pff_config(config)
    assert pff.coverage.enabled is True
    assert pff.coverage.catch_rate_sensitivity == 0.04
    assert pff.coverage.factor_clamp == (0.95, 1.05)
```

- [ ] **Step 6: Run tests to verify**

Run: `uv run pytest tests/test_data/test_pff/test_config.py -v -k coverage`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/fantasy_sim/data/pff/models.py src/fantasy_sim/data/pff/config.py \
    config/defaults.yaml tests/test_data/test_pff/test_config.py
git commit -m "feat: add CoverageConfig + CoverageModifiers data model"
```

---

### Task 2: CoverageEngine — CB Profile Building

**Files:**
- Create: `src/fantasy_sim/data/pff/coverage.py`
- Create: `tests/test_data/test_pff/test_coverage.py`

The `defense_coverage_matchup` parquet has two row types:
- **Type 1 (coverage_player_id IS NULL):** Game-level aggregates for individual players. Both offensive receivers (position=WR with pff_position=LWR/RWR/etc.) AND defensive players (position=LCB/RCB/SCB). Have team, player, franchise_id populated.
- **Type 2 (coverage_player_id IS NOT NULL):** Per-matchup-pair rows. `player_id` = receiver, `coverage_player_id` = defender. Position/team/player are NULL. Stats are matchup-specific.

To build CB profiles:
1. From Type 1 rows, identify CBs (position in LCB/RCB/SCB) and their team
2. From Type 2 rows, get per-matchup outcome stats (targets, receptions, yards)
3. Join Type 2 with CB Type 1 on coverage_player_id = player_id to attribute matchups to CBs

- [ ] **Step 1: Write test fixtures (parquet helper)**

Create `tests/test_data/test_pff/test_coverage.py`:

```python
"""Tests for PFF coverage matchup engine."""

import numpy as np
import polars as pl
import pytest

from fantasy_sim.data.pff.loader import PffLoader
from fantasy_sim.data.pff.models import CoverageConfig, CoverageModifiers, PffConfig
from fantasy_sim.models.player import (
    PlayerModel, PlayerOutcomes, PlayerUsage, TeamRoster,
)


# ---------- Fixtures ----------


@pytest.fixture
def pff_dir(tmp_path):
    """Create a temporary PFF data directory."""
    d = tmp_path / "pff" / "processed" / "nfl"
    d.mkdir(parents=True)
    return d


@pytest.fixture
def loader(pff_dir):
    return PffLoader(pff_dir)


@pytest.fixture
def default_config():
    return CoverageConfig(
        enabled=True,
        catch_rate_sensitivity=0.04,
        ypr_sensitivity=0.04,
        min_coverage_targets=20,
        min_z_score_targets=10,
        min_z_score_population=8,
        factor_clamp=(0.95, 1.05),
        min_games=4,
    )


# ---------- Parquet helpers ----------


def _write_coverage_matchup(pff_dir, season, type1_rows, type2_rows):
    """Write a defense_coverage_matchup parquet with Type 1 + Type 2 rows.

    type1_rows: list of dicts with keys:
        player_id, player, position, team, franchise_id, season, week,
        game_id, targets, receptions, yards, grades_coverage_defense,
        grades_overall
    type2_rows: list of dicts with keys:
        player_id (receiver), coverage_player_id (defender), season, week,
        game_id, targets, receptions, yards, grades_coverage_defense,
        grades_overall
    """
    columns = {
        "player_id": [], "coverage_player_id": [], "player": [],
        "position": [], "team": [], "franchise_id": [],
        "season": [], "week": [], "game_id": [],
        "targets": [], "receptions": [], "yards": [],
        "yards_per_reception": [], "yards_after_catch": [],
        "touchdowns": [], "first_downs": [], "drops": [],
        "broken_up_passes": [], "interceptions": [],
        "grades_coverage_defense": [], "grades_overall": [],
        "grades_defense": [], "grades_pass_route": [],
        "jersey_number": [], "status": [],
    }

    for row in type1_rows:
        columns["player_id"].append(row["player_id"])
        columns["coverage_player_id"].append(None)
        columns["player"].append(row.get("player", f"Player_{row['player_id']}"))
        columns["position"].append(row["position"])
        columns["team"].append(row["team"])
        columns["franchise_id"].append(row.get("franchise_id", 0))
        columns["season"].append(season)
        columns["week"].append(row["week"])
        columns["game_id"].append(row["game_id"])
        columns["targets"].append(row.get("targets", 0))
        columns["receptions"].append(row.get("receptions", 0))
        columns["yards"].append(row.get("yards", 0))
        ypr = row.get("yards", 0) / max(row.get("receptions", 1), 1)
        columns["yards_per_reception"].append(ypr)
        columns["yards_after_catch"].append(row.get("yards_after_catch", 0))
        columns["touchdowns"].append(row.get("touchdowns", 0))
        columns["first_downs"].append(row.get("first_downs", 0))
        columns["drops"].append(row.get("drops", 0))
        columns["broken_up_passes"].append(row.get("broken_up_passes", 0))
        columns["interceptions"].append(row.get("interceptions", 0))
        columns["grades_coverage_defense"].append(
            row.get("grades_coverage_defense")
        )
        columns["grades_overall"].append(row.get("grades_overall", 65.0))
        columns["grades_defense"].append(None)
        columns["grades_pass_route"].append(None)
        columns["jersey_number"].append(None)
        columns["status"].append(row.get("status", "S"))

    for row in type2_rows:
        columns["player_id"].append(row["player_id"])
        columns["coverage_player_id"].append(row["coverage_player_id"])
        columns["player"].append(None)
        columns["position"].append(None)
        columns["team"].append(None)
        columns["franchise_id"].append(None)
        columns["season"].append(season)
        columns["week"].append(row["week"])
        columns["game_id"].append(row["game_id"])
        columns["targets"].append(row.get("targets", 0))
        columns["receptions"].append(row.get("receptions", 0))
        columns["yards"].append(row.get("yards", 0))
        ypr = row.get("yards", 0) / max(row.get("receptions", 1), 1)
        columns["yards_per_reception"].append(ypr)
        columns["yards_after_catch"].append(0)
        columns["touchdowns"].append(0)
        columns["first_downs"].append(0)
        columns["drops"].append(0)
        columns["broken_up_passes"].append(row.get("broken_up_passes", 0))
        columns["interceptions"].append(row.get("interceptions", 0))
        columns["grades_coverage_defense"].append(
            row.get("grades_coverage_defense")
        )
        columns["grades_overall"].append(row.get("grades_overall"))
        columns["grades_defense"].append(None)
        columns["grades_pass_route"].append(None)
        columns["jersey_number"].append(None)
        columns["status"].append(None)

    df = pl.DataFrame(columns)
    path = pff_dir / f"defense_coverage_matchup_{season}.parquet"
    df.write_parquet(path)
    return path


def _make_wr_roster(team: str, players: list[dict]) -> TeamRoster:
    """Create a TeamRoster with WR players.

    players: list of dicts with player_id, target_share, catch_rate.
    """
    models = []
    for p in players:
        models.append(PlayerModel(
            player_id=p["player_id"],
            name=p.get("name", p["player_id"]),
            position="WR",
            team=team,
            usage=PlayerUsage(target_share=p.get("target_share", 0.20)),
            outcomes=PlayerOutcomes(
                catch_rate=p.get("catch_rate", 0.65),
                red_zone_catch_rate=p.get("catch_rate", 0.65) * 0.92,
                receiving_yards_dist=np.array([5, 8, 12, 15, 20], dtype=float),
            ),
        ))
    return TeamRoster(team=team, players=models)
```

- [ ] **Step 2: Write test for CB profile building**

Add to `test_coverage.py`:

```python
class TestBuildCbProfiles:
    """Tests for _build_cb_profiles() internal method."""

    def test_identifies_starting_cbs_by_alignment(
        self, pff_dir, loader, default_config
    ):
        """Finds the starter at each CB alignment by target volume."""
        from fantasy_sim.data.pff.coverage import CoverageEngine

        # BUF has 2 LCBs — starter (pid=200) has more targets in matchup rows
        type1_rows = [
            # BUF CBs (Type 1 game-level aggregates)
            {"player_id": 200, "position": "LCB", "team": "BUF",
             "week": w, "game_id": 1000 + w, "grades_overall": 75.0}
            for w in range(1, 7)
        ] + [
            {"player_id": 201, "position": "LCB", "team": "BUF",
             "week": w, "game_id": 1000 + w, "grades_overall": 60.0}
            for w in range(1, 7)
        ] + [
            {"player_id": 202, "position": "RCB", "team": "BUF",
             "week": w, "game_id": 1000 + w, "grades_overall": 70.0}
            for w in range(1, 7)
        ] + [
            {"player_id": 203, "position": "SCB", "team": "BUF",
             "week": w, "game_id": 1000 + w, "grades_overall": 65.0}
            for w in range(1, 7)
        ] + [
            # KC WR (Type 1 — needed for game context)
            {"player_id": 500, "position": "RWR", "team": "KC",
             "week": w, "game_id": 1000 + w, "targets": 8, "receptions": 5,
             "yards": 60, "grades_overall": 72.0}
            for w in range(1, 7)
        ]

        # Matchup rows — starter 200 gets 6 targets/game, backup 201 gets 2
        type2_rows = []
        for w in range(1, 7):
            type2_rows.append({
                "player_id": 500, "coverage_player_id": 200,
                "week": w, "game_id": 1000 + w,
                "targets": 6, "receptions": 3, "yards": 36,
                "grades_coverage_defense": 75.0,
            })
            type2_rows.append({
                "player_id": 500, "coverage_player_id": 201,
                "week": w, "game_id": 1000 + w,
                "targets": 2, "receptions": 1, "yards": 10,
                "grades_coverage_defense": 55.0,
            })
            type2_rows.append({
                "player_id": 500, "coverage_player_id": 202,
                "week": w, "game_id": 1000 + w,
                "targets": 5, "receptions": 3, "yards": 40,
                "grades_coverage_defense": 70.0,
            })
            type2_rows.append({
                "player_id": 500, "coverage_player_id": 203,
                "week": w, "game_id": 1000 + w,
                "targets": 4, "receptions": 3, "yards": 30,
                "grades_coverage_defense": 65.0,
            })

        _write_coverage_matchup(pff_dir, 2024, type1_rows, type2_rows)

        engine = CoverageEngine(loader, default_config)
        profiles = engine._build_cb_profiles("BUF", target_season=2024, max_week=7)

        # Starter 200 should be the LCB (more targets)
        assert "LCB" in profiles
        assert profiles["LCB"].player_id == 200
        assert profiles["LCB"].total_targets == 36  # 6 * 6 weeks
        assert profiles["LCB"].catch_rate_allowed == pytest.approx(0.5)  # 3/6

        assert "RCB" in profiles
        assert profiles["RCB"].player_id == 202

        assert "SCB" in profiles
        assert profiles["SCB"].player_id == 203

    def test_rolling_window_filters_future_weeks(
        self, pff_dir, loader, default_config
    ):
        """Only uses data from week < max_week."""
        from fantasy_sim.data.pff.coverage import CoverageEngine

        type1_rows = [
            {"player_id": 200, "position": "LCB", "team": "BUF",
             "week": w, "game_id": 1000 + w, "grades_overall": 70.0}
            for w in range(1, 9)
        ]
        type2_rows = [
            {"player_id": 500, "coverage_player_id": 200,
             "week": w, "game_id": 1000 + w,
             "targets": 5, "receptions": 3, "yards": 30,
             "grades_coverage_defense": 70.0}
            for w in range(1, 9)
        ]

        _write_coverage_matchup(pff_dir, 2024, type1_rows, type2_rows)
        engine = CoverageEngine(loader, default_config)

        # max_week=5 → only uses weeks 1-4
        profiles = engine._build_cb_profiles("BUF", target_season=2024, max_week=5)
        assert profiles["LCB"].total_targets == 20  # 5 * 4 weeks

    def test_empty_data_returns_empty_profiles(
        self, pff_dir, loader, default_config
    ):
        """No data for team returns empty dict."""
        from fantasy_sim.data.pff.coverage import CoverageEngine

        _write_coverage_matchup(pff_dir, 2024, [], [])
        engine = CoverageEngine(loader, default_config)
        profiles = engine._build_cb_profiles("BUF", target_season=2024, max_week=7)
        assert profiles == {}
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_pff/test_coverage.py::TestBuildCbProfiles -v`
Expected: FAIL (CoverageEngine not implemented yet)

- [ ] **Step 4: Implement CoverageEngine skeleton + _build_cb_profiles**

Create `src/fantasy_sim/data/pff/coverage.py`:

```python
"""Coverage matchup engine — per-WR adjustments based on opposing CB quality.

Maps each offensive WR to the opposing CB by alignment (LWR→RCB, RWR→LCB,
slot→SCB), then adjusts catch_rate and yards_per_reception based on that
CB's rolling performance profile. Outcome-based stats serve as the primary
signal, with PFF coverage grades as a stabilizer for low-sample CBs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import polars as pl

from fantasy_sim.data.pff.loader import PffLoader
from fantasy_sim.data.pff.models import CoverageConfig, CoverageModifiers
from fantasy_sim.models.player import TeamRoster

logger = logging.getLogger(__name__)

# CB alignment positions we care about
CB_ALIGNMENTS = {"LCB", "RCB", "SCB"}

# WR alignment → opposing CB alignment
_ALIGNMENT_MAP: dict[str, str] = {
    "RWR": "LCB",    # Right WR faces Left CB
    "LWR": "RCB",    # Left WR faces Right CB
    "SLWR": "SCB",   # Slot left WR faces Slot CB
    "SRWR": "SCB",   # Slot right WR faces Slot CB
}


@dataclass
class _CbProfile:
    """Rolling stats for one CB at a specific alignment."""
    player_id: int
    team: str
    alignment: str
    catch_rate_allowed: float
    ypr_allowed: float
    coverage_grade: float
    total_targets: int
    games_played: int


class CoverageEngine:
    """Computes per-WR coverage matchup modifiers from PFF data."""

    def __init__(self, loader: PffLoader, config: CoverageConfig) -> None:
        self._loader = loader
        self._config = config
        self._cache: dict[str, pl.DataFrame] = {}

    def _load_cached(self, seasons: list[int]) -> pl.DataFrame:
        """Load defense_coverage_matchup with caching."""
        key = "_".join(str(s) for s in sorted(seasons))
        if key not in self._cache:
            self._cache[key] = self._loader.load_facet(
                "defense_coverage_matchup", seasons
            )
        return self._cache[key]

    def _build_cb_profiles(
        self,
        defense_team: str,
        target_season: int,
        max_week: int,
    ) -> dict[str, _CbProfile]:
        """Build rolling CB profiles for a defensive team.

        Returns dict mapping alignment (LCB/RCB/SCB) to the starter's
        profile at that alignment.
        """
        df = self._load_cached([target_season])
        if df.is_empty():
            return {}

        # Filter to rolling window
        if "week" in df.columns:
            df = df.filter(pl.col("week") < max_week)
        if df.is_empty():
            return {}

        # --- Identify CBs from Type 1 rows (coverage_player_id IS NULL) ---
        # Type 1 defensive rows have position = LCB/RCB/SCB and team populated
        type1 = df.filter(pl.col("coverage_player_id").is_null())
        if type1.is_empty():
            return {}

        # Get CB rows for the defensive team
        # After load_facet(), CB positions stay as LCB/RCB/SCB (not in PFF_TO_FANTASY_POSITION)
        cb_type1 = type1.filter(
            (pl.col("team") == defense_team)
            & pl.col("position").is_in(list(CB_ALIGNMENTS))
        )
        if cb_type1.is_empty():
            return {}

        # Build a lookup: player_id → (team, alignment)
        cb_info = (
            cb_type1
            .group_by("player_id")
            .agg([
                pl.col("team").first(),
                pl.col("position").first().alias("alignment"),
            ])
        )
        cb_player_ids = set(cb_info["player_id"].to_list())

        # --- Aggregate matchup stats from Type 2 rows ---
        type2 = df.filter(pl.col("coverage_player_id").is_not_null())
        if type2.is_empty():
            return {}

        # Filter to matchups involving our defensive CBs
        cb_matchups = type2.filter(
            pl.col("coverage_player_id").is_in(list(cb_player_ids))
        )
        if cb_matchups.is_empty():
            return {}

        # Aggregate per CB: sum targets, receptions, yards + weighted grade
        cb_stats = cb_matchups.group_by("coverage_player_id").agg([
            pl.col("targets").sum().alias("total_targets"),
            pl.col("receptions").sum().alias("total_receptions"),
            pl.col("yards").sum().alias("total_yards"),
            pl.col("game_id").n_unique().alias("games_played"),
            # Target-weighted mean of coverage grade (fallback to overall)
            (
                pl.when(pl.col("grades_coverage_defense").is_not_null())
                .then(pl.col("grades_coverage_defense") * pl.col("targets"))
                .otherwise(pl.col("grades_overall") * pl.col("targets"))
            ).sum().alias("weighted_grade_sum"),
        ])

        # Join with CB info to get alignment
        cb_stats = cb_stats.join(
            cb_info, left_on="coverage_player_id", right_on="player_id",
        )

        # Compute derived stats
        cb_stats = cb_stats.with_columns([
            (pl.col("total_receptions") / pl.col("total_targets").cast(pl.Float64))
            .alias("catch_rate_allowed"),
            (pl.col("total_yards") / pl.col("total_receptions").cast(pl.Float64).replace(0, 1))
            .alias("ypr_allowed"),
            (pl.col("weighted_grade_sum") / pl.col("total_targets").cast(pl.Float64))
            .alias("coverage_grade"),
        ])

        # Pick starter at each alignment (most targets)
        profiles: dict[str, _CbProfile] = {}
        for alignment in CB_ALIGNMENTS:
            align_cbs = cb_stats.filter(pl.col("alignment") == alignment)
            if align_cbs.is_empty():
                continue
            # Starter = CB with most targets at this alignment
            starter = align_cbs.sort("total_targets", descending=True).row(0, named=True)
            profiles[alignment] = _CbProfile(
                player_id=starter["coverage_player_id"],
                team=defense_team,
                alignment=alignment,
                catch_rate_allowed=float(starter["catch_rate_allowed"]),
                ypr_allowed=float(starter["ypr_allowed"]),
                coverage_grade=float(starter["coverage_grade"]),
                total_targets=int(starter["total_targets"]),
                games_played=int(starter["games_played"]),
            )

        return profiles

    def compute(
        self,
        defense_team: str,
        offense_roster: TeamRoster,
        target_season: int | None = None,
        max_week: int | None = None,
    ) -> dict[str, CoverageModifiers]:
        """Return per-WR modifiers for one offense vs one defense.

        Placeholder — will be completed in Task 6.
        """
        if not self._config.enabled:
            return {}
        if target_season is None or max_week is None:
            return {}
        return {}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_pff/test_coverage.py::TestBuildCbProfiles -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/fantasy_sim/data/pff/coverage.py tests/test_data/test_pff/test_coverage.py
git commit -m "feat: add CoverageEngine with CB profile building"
```

---

### Task 3: CoverageEngine — Early-Season Blend

**Files:**
- Modify: `src/fantasy_sim/data/pff/coverage.py`
- Modify: `tests/test_data/test_pff/test_coverage.py`

- [ ] **Step 1: Write test for early-season blend**

Add to `test_coverage.py`:

```python
class TestEarlySeasonBlend:
    """Tests for early-season blending with previous season."""

    def test_blends_with_previous_season_when_few_games(
        self, pff_dir, loader
    ):
        """CB with < min_games blends current + previous season."""
        from fantasy_sim.data.pff.coverage import CoverageEngine

        config = CoverageConfig(
            enabled=True, min_games=4,
            catch_rate_sensitivity=0.04, ypr_sensitivity=0.04,
            min_coverage_targets=5, min_z_score_targets=5,
            min_z_score_population=2, factor_clamp=(0.95, 1.05),
        )

        # Previous season: CB 200 allowed 50% catch rate
        prev_type1 = [
            {"player_id": 200, "position": "LCB", "team": "BUF",
             "week": w, "game_id": 2000 + w, "grades_overall": 70.0}
            for w in range(1, 11)
        ]
        prev_type2 = [
            {"player_id": 500, "coverage_player_id": 200,
             "week": w, "game_id": 2000 + w,
             "targets": 5, "receptions": 2, "yards": 20,
             "grades_coverage_defense": 70.0}
            for w in range(1, 11)
        ]
        _write_coverage_matchup(pff_dir, 2023, prev_type1, prev_type2)

        # Current season: CB 200 has only 2 games, allowed 80% catch rate
        cur_type1 = [
            {"player_id": 200, "position": "LCB", "team": "BUF",
             "week": w, "game_id": 3000 + w, "grades_overall": 60.0}
            for w in range(1, 3)
        ]
        cur_type2 = [
            {"player_id": 500, "coverage_player_id": 200,
             "week": w, "game_id": 3000 + w,
             "targets": 5, "receptions": 4, "yards": 50,
             "grades_coverage_defense": 55.0}
            for w in range(1, 3)
        ]
        _write_coverage_matchup(pff_dir, 2024, cur_type1, cur_type2)

        engine = CoverageEngine(loader, config)
        profiles = engine._build_cb_profiles("BUF", target_season=2024, max_week=3)

        # With 2 games and min_games=4, blend_weight = 2/4 = 0.5
        # Current catch_rate = 4/5 = 0.80, prev = 2/5 = 0.40
        # Blended = 0.5 * 0.80 + 0.5 * 0.40 = 0.60
        assert "LCB" in profiles
        assert profiles["LCB"].catch_rate_allowed == pytest.approx(0.60, abs=0.01)

    def test_no_blend_when_enough_games(self, pff_dir, loader):
        """CB with >= min_games uses current season only."""
        from fantasy_sim.data.pff.coverage import CoverageEngine

        config = CoverageConfig(
            enabled=True, min_games=4,
            catch_rate_sensitivity=0.04, ypr_sensitivity=0.04,
            min_coverage_targets=5, min_z_score_targets=5,
            min_z_score_population=2, factor_clamp=(0.95, 1.05),
        )

        # Previous season — should be ignored
        prev_type1 = [
            {"player_id": 200, "position": "LCB", "team": "BUF",
             "week": w, "game_id": 2000 + w, "grades_overall": 70.0}
            for w in range(1, 11)
        ]
        prev_type2 = [
            {"player_id": 500, "coverage_player_id": 200,
             "week": w, "game_id": 2000 + w,
             "targets": 5, "receptions": 1, "yards": 10,
             "grades_coverage_defense": 80.0}
            for w in range(1, 11)
        ]
        _write_coverage_matchup(pff_dir, 2023, prev_type1, prev_type2)

        # Current season: 6 games, enough data
        cur_type1 = [
            {"player_id": 200, "position": "LCB", "team": "BUF",
             "week": w, "game_id": 3000 + w, "grades_overall": 60.0}
            for w in range(1, 7)
        ]
        cur_type2 = [
            {"player_id": 500, "coverage_player_id": 200,
             "week": w, "game_id": 3000 + w,
             "targets": 5, "receptions": 4, "yards": 50,
             "grades_coverage_defense": 55.0}
            for w in range(1, 7)
        ]
        _write_coverage_matchup(pff_dir, 2024, cur_type1, cur_type2)

        engine = CoverageEngine(loader, config)
        profiles = engine._build_cb_profiles("BUF", target_season=2024, max_week=7)

        # 6 games >= min_games=4, so no blend. Current catch_rate = 4/5 = 0.80
        assert profiles["LCB"].catch_rate_allowed == pytest.approx(0.80, abs=0.01)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_pff/test_coverage.py::TestEarlySeasonBlend -v`
Expected: FAIL (blend not implemented)

- [ ] **Step 3: Update _build_cb_profiles to support early-season blend**

Update `_build_cb_profiles` in `coverage.py` to accept previous season data and blend:

```python
    def _build_cb_profiles(
        self,
        defense_team: str,
        target_season: int,
        max_week: int,
    ) -> dict[str, _CbProfile]:
        """Build rolling CB profiles for a defensive team.

        When a CB has < min_games games in the current season, blends
        with previous-season profile using a linear ramp.
        """
        current_profiles = self._build_season_profiles(
            defense_team, target_season, max_week,
        )
        if not current_profiles:
            return {}

        # Check if any CB needs early-season blend
        needs_blend = any(
            p.games_played < self._config.min_games
            for p in current_profiles.values()
        )
        if not needs_blend:
            return current_profiles

        # Load previous season profiles (full season)
        prev_profiles = self._build_season_profiles(
            defense_team, target_season - 1, max_week=99,
        )
        if not prev_profiles:
            return current_profiles

        # Blend each alignment
        blended: dict[str, _CbProfile] = {}
        for alignment, current in current_profiles.items():
            if current.games_played >= self._config.min_games:
                blended[alignment] = current
                continue

            prev = prev_profiles.get(alignment)
            if prev is None:
                blended[alignment] = current
                continue

            weight = current.games_played / self._config.min_games
            blended[alignment] = _CbProfile(
                player_id=current.player_id,
                team=defense_team,
                alignment=alignment,
                catch_rate_allowed=(
                    weight * current.catch_rate_allowed
                    + (1 - weight) * prev.catch_rate_allowed
                ),
                ypr_allowed=(
                    weight * current.ypr_allowed
                    + (1 - weight) * prev.ypr_allowed
                ),
                coverage_grade=(
                    weight * current.coverage_grade
                    + (1 - weight) * prev.coverage_grade
                ),
                total_targets=current.total_targets + prev.total_targets,
                games_played=current.games_played,
            )

        return blended
```

Rename the original `_build_cb_profiles` body to `_build_season_profiles` (same logic, no blend). The new `_build_cb_profiles` calls `_build_season_profiles` for current + previous and blends.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_pff/test_coverage.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/pff/coverage.py tests/test_data/test_pff/test_coverage.py
git commit -m "feat: add early-season blend for CB profiles"
```

---

### Task 4: CoverageEngine — WR Alignment + CB Mapping

**Files:**
- Modify: `src/fantasy_sim/data/pff/coverage.py`
- Modify: `tests/test_data/test_pff/test_coverage.py`

- [ ] **Step 1: Write test for WR alignment determination**

Add to `test_coverage.py`:

```python
class TestWrAlignment:
    """Tests for WR alignment determination and CB mapping."""

    def test_determines_wr_alignment_from_matchup_data(
        self, pff_dir, loader, default_config
    ):
        """WR alignment is the pff_position they appear in most often."""
        from fantasy_sim.data.pff.coverage import CoverageEngine

        # WR "wr_1" appears as RWR 4 times, SLWR 2 times → primary = RWR
        type1_rows = [
            {"player_id": 500, "position": "RWR", "team": "KC",
             "week": w, "game_id": 1000 + w, "targets": 6, "receptions": 4,
             "yards": 50}
            for w in range(1, 5)
        ] + [
            {"player_id": 500, "position": "SLWR", "team": "KC",
             "week": w, "game_id": 1000 + w, "targets": 4, "receptions": 3,
             "yards": 30}
            for w in [5, 6]
        ]

        _write_coverage_matchup(pff_dir, 2024, type1_rows, [])

        engine = CoverageEngine(loader, default_config)
        alignments = engine._determine_wr_alignments(
            ["wr_1"], "KC", target_season=2024, max_week=7,
            pff_player_id_map={"wr_1": 500},
        )

        assert alignments.get("wr_1") == "RWR"

    def test_fallback_by_target_share_rank(
        self, pff_dir, loader, default_config
    ):
        """WRs with no matchup data fall back to target_share ranking."""
        from fantasy_sim.data.pff.coverage import CoverageEngine

        _write_coverage_matchup(pff_dir, 2024, [], [])

        engine = CoverageEngine(loader, default_config)
        roster = _make_wr_roster("KC", [
            {"player_id": "wr_1", "target_share": 0.30},  # WR1 → outside
            {"player_id": "wr_2", "target_share": 0.22},  # WR2 → outside
            {"player_id": "wr_3", "target_share": 0.12},  # WR3 → slot
        ])

        alignments = engine._determine_wr_alignments(
            ["wr_1", "wr_2", "wr_3"], "KC",
            target_season=2024, max_week=7,
            pff_player_id_map={},
        )

        # WR1 and WR2 map to outside, WR3 to slot
        assert alignments["wr_1"] in ("RWR", "LWR")
        assert alignments["wr_2"] in ("RWR", "LWR")
        assert alignments["wr_3"] in ("SLWR", "SRWR")

    def test_alignment_to_cb_mapping(self, default_config):
        """WR alignment maps to the correct opposing CB."""
        from fantasy_sim.data.pff.coverage import _ALIGNMENT_MAP

        assert _ALIGNMENT_MAP["RWR"] == "LCB"
        assert _ALIGNMENT_MAP["LWR"] == "RCB"
        assert _ALIGNMENT_MAP["SLWR"] == "SCB"
        assert _ALIGNMENT_MAP["SRWR"] == "SCB"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_pff/test_coverage.py::TestWrAlignment -v`
Expected: FAIL (except alignment_to_cb_mapping which tests the constant)

- [ ] **Step 3: Implement _determine_wr_alignments**

Add to `CoverageEngine`:

```python
    def _determine_wr_alignments(
        self,
        wr_player_ids: list[str],
        offense_team: str,
        target_season: int,
        max_week: int,
        pff_player_id_map: dict[str, int],
    ) -> dict[str, str]:
        """Determine each WR's primary alignment from matchup data.

        Falls back to target_share ranking when matchup data is unavailable:
        WR1/WR2 → outside (RWR/LWR), WR3+ → slot (SLWR).

        Args:
            wr_player_ids: List of nflverse player_ids for WRs.
            offense_team: Team abbreviation.
            target_season: Season year.
            max_week: Week filter (< max_week).
            pff_player_id_map: nflverse_id → PFF player_id mapping.

        Returns:
            Dict mapping nflverse player_id → pff_position alignment.
        """
        alignments: dict[str, str] = {}

        df = self._load_cached([target_season])
        if not df.is_empty() and "week" in df.columns:
            df = df.filter(pl.col("week") < max_week)

        # Type 1 rows for the offensive team's receivers
        type1 = df.filter(
            pl.col("coverage_player_id").is_null()
            & (pl.col("team") == offense_team)
            & (pl.col("position") == "WR")
        ) if not df.is_empty() else pl.DataFrame()

        # For each WR, find their most common pff_position
        for nfl_id in wr_player_ids:
            pff_id = pff_player_id_map.get(nfl_id)
            if pff_id is not None and not type1.is_empty():
                wr_rows = type1.filter(pl.col("player_id") == pff_id)
                if not wr_rows.is_empty() and "pff_position" in wr_rows.columns:
                    valid = wr_rows.filter(pl.col("pff_position").is_not_null())
                    if not valid.is_empty():
                        # Plurality: most common pff_position
                        counts = (
                            valid
                            .group_by("pff_position")
                            .agg(pl.len().alias("n"))
                            .sort("n", descending=True)
                        )
                        alignments[nfl_id] = counts.row(0, named=True)["pff_position"]

        # Fallback for WRs without matchup data
        unresolved = [pid for pid in wr_player_ids if pid not in alignments]
        if unresolved:
            # Already ordered by target_share from caller
            for i, pid in enumerate(unresolved):
                if i < 2:
                    # WR1→RWR, WR2→LWR (outside)
                    alignments[pid] = "RWR" if i == 0 else "LWR"
                else:
                    alignments[pid] = "SLWR"  # slot

        return alignments
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_pff/test_coverage.py::TestWrAlignment -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/pff/coverage.py tests/test_data/test_pff/test_coverage.py
git commit -m "feat: add WR alignment determination and CB mapping"
```

---

### Task 5: CoverageEngine — Z-Score + Modifier Computation

**Files:**
- Modify: `src/fantasy_sim/data/pff/coverage.py`
- Modify: `tests/test_data/test_pff/test_coverage.py`

- [ ] **Step 1: Write test for z-score and modifier computation**

Add to `test_coverage.py`:

```python
class TestModifierComputation:
    """Tests for z-score computation and modifier conversion."""

    def test_strong_cb_produces_negative_modifier(self, default_config):
        """A CB with low catch_rate_allowed (strong) produces modifier < 1.0."""
        from fantasy_sim.data.pff.coverage import _compute_modifiers

        # Strong CB: low catch rate allowed, high grade
        cb = _CbProfile(
            player_id=200, team="BUF", alignment="LCB",
            catch_rate_allowed=0.50, ypr_allowed=9.0,
            coverage_grade=82.0, total_targets=60, games_played=8,
        )
        # League population at this alignment
        all_cbs = [
            _CbProfile(200, "BUF", "LCB", 0.50, 9.0, 82.0, 60, 8),  # strong
            _CbProfile(300, "MIA", "LCB", 0.62, 11.0, 68.0, 55, 8),  # average
            _CbProfile(400, "NE", "LCB", 0.65, 12.0, 60.0, 50, 8),   # average
            _CbProfile(500, "NYJ", "LCB", 0.70, 14.0, 55.0, 45, 8),  # weak
            _CbProfile(600, "DAL", "LCB", 0.64, 11.5, 65.0, 50, 8),
            _CbProfile(700, "PHI", "LCB", 0.58, 10.0, 72.0, 55, 8),
            _CbProfile(800, "WAS", "LCB", 0.68, 13.0, 58.0, 48, 8),
            _CbProfile(900, "NYG", "LCB", 0.60, 10.5, 70.0, 52, 8),
        ]

        mods = _compute_modifiers(cb, all_cbs, default_config)

        # Strong CB → WR should be penalized (modifier < 1.0)
        assert mods.catch_rate_modifier < 1.0
        assert mods.ypr_modifier < 1.0

    def test_weak_cb_produces_positive_modifier(self, default_config):
        """A CB with high catch_rate_allowed (weak) produces modifier > 1.0."""
        from fantasy_sim.data.pff.coverage import _compute_modifiers

        weak_cb = _CbProfile(
            player_id=500, team="NYJ", alignment="LCB",
            catch_rate_allowed=0.70, ypr_allowed=14.0,
            coverage_grade=55.0, total_targets=45, games_played=8,
        )
        all_cbs = [
            _CbProfile(200, "BUF", "LCB", 0.50, 9.0, 82.0, 60, 8),
            _CbProfile(300, "MIA", "LCB", 0.62, 11.0, 68.0, 55, 8),
            _CbProfile(400, "NE", "LCB", 0.65, 12.0, 60.0, 50, 8),
            _CbProfile(500, "NYJ", "LCB", 0.70, 14.0, 55.0, 45, 8),
            _CbProfile(600, "DAL", "LCB", 0.64, 11.5, 65.0, 50, 8),
            _CbProfile(700, "PHI", "LCB", 0.58, 10.0, 72.0, 55, 8),
            _CbProfile(800, "WAS", "LCB", 0.68, 13.0, 58.0, 48, 8),
            _CbProfile(900, "NYG", "LCB", 0.60, 10.5, 70.0, 52, 8),
        ]

        mods = _compute_modifiers(weak_cb, all_cbs, default_config)
        assert mods.catch_rate_modifier > 1.0
        assert mods.ypr_modifier > 1.0

    def test_modifiers_clamped_to_range(self):
        """Modifiers are clamped to factor_clamp range."""
        from fantasy_sim.data.pff.coverage import _compute_modifiers

        config = CoverageConfig(
            enabled=True, catch_rate_sensitivity=0.20,  # very high
            ypr_sensitivity=0.20, factor_clamp=(0.95, 1.05),
            min_coverage_targets=20, min_z_score_targets=10,
            min_z_score_population=8, min_games=4,
        )

        extreme_cb = _CbProfile(
            200, "BUF", "LCB", 0.30, 6.0, 95.0, 80, 10,  # elite
        )
        all_cbs = [
            extreme_cb,
            _CbProfile(300, "MIA", "LCB", 0.65, 12.0, 60.0, 50, 8),
            _CbProfile(400, "NE", "LCB", 0.65, 12.0, 60.0, 50, 8),
            _CbProfile(500, "NYJ", "LCB", 0.65, 12.0, 60.0, 50, 8),
            _CbProfile(600, "DAL", "LCB", 0.65, 12.0, 60.0, 50, 8),
            _CbProfile(700, "PHI", "LCB", 0.65, 12.0, 60.0, 50, 8),
            _CbProfile(800, "WAS", "LCB", 0.65, 12.0, 60.0, 50, 8),
            _CbProfile(900, "NYG", "LCB", 0.65, 12.0, 60.0, 50, 8),
        ]

        mods = _compute_modifiers(extreme_cb, all_cbs, config)
        assert mods.catch_rate_modifier == pytest.approx(0.95)  # clamped
        assert mods.ypr_modifier == pytest.approx(0.95)  # clamped

    def test_reliability_ramp_blends_outcome_and_grade(self):
        """Low-target CBs lean on grade; high-target CBs use outcomes."""
        from fantasy_sim.data.pff.coverage import _compute_modifiers

        config = CoverageConfig(
            enabled=True, catch_rate_sensitivity=0.04,
            ypr_sensitivity=0.04, min_coverage_targets=20,
            min_z_score_targets=5, min_z_score_population=8,
            factor_clamp=(0.90, 1.10), min_games=4,
        )

        # CB with only 10 targets (reliability=0.5) but high grade
        # Outcomes say average, grade says strong → blend should pull
        # toward strong (grade influence = 50%)
        low_sample_cb = _CbProfile(
            200, "BUF", "LCB",
            catch_rate_allowed=0.62,  # average outcome
            ypr_allowed=11.0,
            coverage_grade=82.0,  # strong grade
            total_targets=10,  # half of min_coverage_targets
            games_played=2,
        )
        population = [
            low_sample_cb,
            _CbProfile(300, "MIA", "LCB", 0.62, 11.0, 65.0, 50, 8),
            _CbProfile(400, "NE", "LCB", 0.62, 11.0, 65.0, 50, 8),
            _CbProfile(500, "NYJ", "LCB", 0.62, 11.0, 65.0, 50, 8),
            _CbProfile(600, "DAL", "LCB", 0.62, 11.0, 65.0, 50, 8),
            _CbProfile(700, "PHI", "LCB", 0.62, 11.0, 65.0, 50, 8),
            _CbProfile(800, "WAS", "LCB", 0.62, 11.0, 65.0, 50, 8),
            _CbProfile(900, "NYG", "LCB", 0.62, 11.0, 65.0, 50, 8),
        ]

        mods = _compute_modifiers(low_sample_cb, population, config)

        # Outcome z ≈ 0 (average), grade z < 0 (stronger than average, inverted)
        # At reliability=0.5: blended pulls toward grade = below 1.0
        assert mods.catch_rate_modifier < 1.0

    def test_small_population_returns_neutral(self):
        """Fewer CBs than min_z_score_population → neutral modifiers."""
        from fantasy_sim.data.pff.coverage import _compute_modifiers

        config = CoverageConfig(
            enabled=True, catch_rate_sensitivity=0.04,
            ypr_sensitivity=0.04, min_coverage_targets=20,
            min_z_score_targets=10, min_z_score_population=8,
            factor_clamp=(0.95, 1.05), min_games=4,
        )

        cb = _CbProfile(200, "BUF", "LCB", 0.50, 9.0, 82.0, 60, 8)
        small_pop = [cb, _CbProfile(300, "MIA", "LCB", 0.65, 12.0, 60.0, 50, 8)]

        mods = _compute_modifiers(cb, small_pop, config)
        assert mods.catch_rate_modifier == 1.0
        assert mods.ypr_modifier == 1.0
```

Add the `_CbProfile` import at the top of the test file:

```python
from fantasy_sim.data.pff.coverage import CoverageEngine, _CbProfile
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_pff/test_coverage.py::TestModifierComputation -v`
Expected: FAIL

- [ ] **Step 3: Implement _compute_modifiers**

Add as a module-level function in `coverage.py`:

```python
def _compute_modifiers(
    cb: _CbProfile,
    all_cbs_at_alignment: list[_CbProfile],
    config: CoverageConfig,
) -> CoverageModifiers:
    """Compute catch_rate and ypr modifiers for a WR facing this CB.

    Uses z-scores across all CBs at the same alignment. Blends outcome-based
    z-scores with grade-based z-scores using a reliability ramp based on the
    CB's target volume.
    """
    # Filter population to CBs meeting min target threshold
    population = [
        c for c in all_cbs_at_alignment
        if c.total_targets >= config.min_z_score_targets
    ]

    if len(population) < config.min_z_score_population:
        return CoverageModifiers()

    # Compute league stats at this alignment
    catch_rates = [c.catch_rate_allowed for c in population]
    yprs = [c.ypr_allowed for c in population]
    grades = [c.coverage_grade for c in population]

    catch_mean = sum(catch_rates) / len(catch_rates)
    ypr_mean = sum(yprs) / len(yprs)
    grade_mean = sum(grades) / len(grades)

    catch_std = (sum((x - catch_mean) ** 2 for x in catch_rates) / len(catch_rates)) ** 0.5
    ypr_std = (sum((x - ypr_mean) ** 2 for x in yprs) / len(yprs)) ** 0.5
    grade_std = (sum((x - grade_mean) ** 2 for x in grades) / len(grades)) ** 0.5

    # Z-scores for this CB
    catch_z = (cb.catch_rate_allowed - catch_mean) / catch_std if catch_std > 0 else 0.0
    ypr_z = (cb.ypr_allowed - ypr_mean) / ypr_std if ypr_std > 0 else 0.0
    # Grade inverted: higher grade = tougher CB = negative WR adjustment
    grade_z = -(cb.coverage_grade - grade_mean) / grade_std if grade_std > 0 else 0.0

    # Reliability ramp: outcome vs grade blend
    reliability = min(cb.total_targets / config.min_coverage_targets, 1.0)
    blended_catch_z = reliability * catch_z + (1 - reliability) * grade_z
    blended_ypr_z = reliability * ypr_z + (1 - reliability) * grade_z

    # Convert to modifiers
    lo, hi = config.factor_clamp
    catch_mod = max(lo, min(hi, 1.0 + blended_catch_z * config.catch_rate_sensitivity))
    ypr_mod = max(lo, min(hi, 1.0 + blended_ypr_z * config.ypr_sensitivity))

    return CoverageModifiers(
        catch_rate_modifier=catch_mod,
        ypr_modifier=ypr_mod,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_pff/test_coverage.py::TestModifierComputation -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/pff/coverage.py tests/test_data/test_pff/test_coverage.py
git commit -m "feat: add z-score modifier computation with reliability ramp"
```

---

### Task 6: CoverageEngine.compute() — Full Orchestration

**Files:**
- Modify: `src/fantasy_sim/data/pff/coverage.py`
- Modify: `tests/test_data/test_pff/test_coverage.py`

- [ ] **Step 1: Write integration test for compute()**

Add to `test_coverage.py`:

```python
class TestCoverageEngineCompute:
    """Integration tests for CoverageEngine.compute()."""

    def _setup_league_data(self, pff_dir, season):
        """Create matchup data with 8+ CBs per alignment for valid z-scores.

        Sets up BUF with a strong LCB (200), average RCB (202), weak SCB (203).
        Plus 7 other teams' CBs at each alignment for z-score population.
        """
        teams = ["MIA", "NE", "NYJ", "DAL", "PHI", "WAS", "NYG"]
        type1_rows = []
        type2_rows = []

        # BUF CBs
        for w in range(1, 7):
            gid = 1000 + w
            type1_rows.extend([
                {"player_id": 200, "position": "LCB", "team": "BUF",
                 "week": w, "game_id": gid, "grades_overall": 80.0},
                {"player_id": 202, "position": "RCB", "team": "BUF",
                 "week": w, "game_id": gid, "grades_overall": 65.0},
                {"player_id": 203, "position": "SCB", "team": "BUF",
                 "week": w, "game_id": gid, "grades_overall": 55.0},
            ])
            # BUF matchup rows — strong LCB, average RCB, weak SCB
            type2_rows.extend([
                {"player_id": 900, "coverage_player_id": 200,
                 "week": w, "game_id": gid,
                 "targets": 6, "receptions": 2, "yards": 18,
                 "grades_coverage_defense": 80.0},
                {"player_id": 901, "coverage_player_id": 202,
                 "week": w, "game_id": gid,
                 "targets": 5, "receptions": 3, "yards": 33,
                 "grades_coverage_defense": 65.0},
                {"player_id": 902, "coverage_player_id": 203,
                 "week": w, "game_id": gid,
                 "targets": 4, "receptions": 3, "yards": 42,
                 "grades_coverage_defense": 55.0},
            ])

        # Other teams' CBs — all average (catch_rate ~0.60, YPR ~11.0)
        pid = 300
        for team in teams:
            for alignment in ["LCB", "RCB", "SCB"]:
                for w in range(1, 7):
                    gid = 2000 + pid + w
                    type1_rows.append({
                        "player_id": pid, "position": alignment, "team": team,
                        "week": w, "game_id": gid, "grades_overall": 65.0,
                    })
                    type2_rows.append({
                        "player_id": 950, "coverage_player_id": pid,
                        "week": w, "game_id": gid,
                        "targets": 5, "receptions": 3, "yards": 33,
                        "grades_coverage_defense": 65.0,
                    })
                pid += 1

        # KC WR Type 1 rows (for alignment determination)
        for w in range(1, 7):
            gid = 1000 + w
            type1_rows.extend([
                {"player_id": 500, "position": "RWR", "team": "KC",
                 "week": w, "game_id": gid, "targets": 8, "receptions": 5,
                 "yards": 60},
                {"player_id": 501, "position": "LWR", "team": "KC",
                 "week": w, "game_id": gid, "targets": 6, "receptions": 4,
                 "yards": 50},
                {"player_id": 502, "position": "SLWR", "team": "KC",
                 "week": w, "game_id": gid, "targets": 4, "receptions": 3,
                 "yards": 30},
            ])

        _write_coverage_matchup(pff_dir, season, type1_rows, type2_rows)

    def test_compute_returns_per_wr_modifiers(
        self, pff_dir, loader, default_config
    ):
        """compute() returns correct modifiers for each WR based on CB matchup."""
        from fantasy_sim.data.pff.coverage import CoverageEngine

        self._setup_league_data(pff_dir, 2024)

        engine = CoverageEngine(loader, default_config)

        # KC roster with known PFF mappings
        roster = _make_wr_roster("KC", [
            {"player_id": "wr_1", "target_share": 0.30, "catch_rate": 0.65},
            {"player_id": "wr_2", "target_share": 0.22, "catch_rate": 0.62},
            {"player_id": "wr_3", "target_share": 0.12, "catch_rate": 0.60},
        ])

        # Need crosswalk so engine can find PFF ids for WRs
        pff_crosswalk = {500: "wr_1", 501: "wr_2", 502: "wr_3"}

        modifiers = engine.compute(
            defense_team="BUF",
            offense_roster=roster,
            target_season=2024,
            max_week=7,
            pff_crosswalk=pff_crosswalk,
        )

        # wr_1 (RWR) faces BUF LCB (strong, low catch rate) → modifier < 1.0
        assert "wr_1" in modifiers
        assert modifiers["wr_1"].catch_rate_modifier < 1.0

        # wr_3 (SLWR) faces BUF SCB (weak, high catch rate) → modifier > 1.0
        assert "wr_3" in modifiers
        assert modifiers["wr_3"].catch_rate_modifier > 1.0

    def test_compute_disabled_returns_empty(self, pff_dir, loader):
        """Disabled engine returns empty dict."""
        from fantasy_sim.data.pff.coverage import CoverageEngine

        config = CoverageConfig(enabled=False)
        engine = CoverageEngine(loader, config)
        roster = _make_wr_roster("KC", [{"player_id": "wr_1"}])
        result = engine.compute("BUF", roster, 2024, 7)
        assert result == {}

    def test_compute_no_season_returns_empty(self, pff_dir, loader, default_config):
        """No target_season returns empty dict."""
        from fantasy_sim.data.pff.coverage import CoverageEngine

        engine = CoverageEngine(loader, default_config)
        roster = _make_wr_roster("KC", [{"player_id": "wr_1"}])
        result = engine.compute("BUF", roster, None, None)
        assert result == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_pff/test_coverage.py::TestCoverageEngineCompute -v`
Expected: FAIL

- [ ] **Step 3: Implement compute()**

Update the `compute()` method in `CoverageEngine`. Note: the signature adds `pff_crosswalk` parameter (reverse crosswalk: PFF ID → nflverse ID):

```python
    def compute(
        self,
        defense_team: str,
        offense_roster: TeamRoster,
        target_season: int | None = None,
        max_week: int | None = None,
        pff_crosswalk: dict[int, str] | None = None,
    ) -> dict[str, CoverageModifiers]:
        """Return per-WR modifiers for one offense vs one defense."""
        if not self._config.enabled:
            return {}
        if target_season is None or max_week is None:
            return {}

        # Build CB profiles for the defense
        cb_profiles = self._build_cb_profiles(
            defense_team, target_season, max_week,
        )
        if not cb_profiles:
            return {}

        # Build league-wide CB profiles for z-score population
        all_cb_profiles = self._build_all_cb_profiles(target_season, max_week)

        # Identify WRs on the offense roster
        wrs = [p for p in offense_roster.players if p.position == "WR"]
        if not wrs:
            return {}

        # Build reverse crosswalk: nflverse_id → PFF player_id
        pff_id_map: dict[str, int] = {}
        if pff_crosswalk:
            pff_id_map = {nfl_id: pff_id for pff_id, nfl_id in pff_crosswalk.items()}

        # Sort WRs by target_share for fallback alignment
        wr_ids_sorted = [
            p.player_id
            for p in sorted(wrs, key=lambda p: p.usage.target_share, reverse=True)
        ]

        # Determine WR alignments
        alignments = self._determine_wr_alignments(
            wr_ids_sorted, offense_roster.team,
            target_season, max_week, pff_id_map,
        )

        # Compute modifiers per WR
        modifiers: dict[str, CoverageModifiers] = {}
        for wr in wrs:
            wr_alignment = alignments.get(wr.player_id)
            if wr_alignment is None:
                continue

            cb_alignment = _ALIGNMENT_MAP.get(wr_alignment)
            if cb_alignment is None:
                continue

            cb = cb_profiles.get(cb_alignment)
            if cb is None:
                continue

            population = all_cb_profiles.get(cb_alignment, [])
            mods = _compute_modifiers(cb, population, self._config)
            if mods.catch_rate_modifier != 1.0 or mods.ypr_modifier != 1.0:
                modifiers[wr.player_id] = mods

        if modifiers:
            logger.info(
                "Coverage modifiers: %s D vs %s O (season=%d, week<%d) → %d WRs adjusted",
                defense_team, offense_roster.team, target_season, max_week,
                len(modifiers),
            )

        return modifiers
```

Also add `_build_all_cb_profiles` method:

```python
    def _build_all_cb_profiles(
        self,
        target_season: int,
        max_week: int,
    ) -> dict[str, list[_CbProfile]]:
        """Build CB profiles for ALL teams, grouped by alignment.

        Used as the z-score population for modifier computation.
        """
        df = self._load_cached([target_season])
        if df.is_empty():
            return {}

        if "week" in df.columns:
            df = df.filter(pl.col("week") < max_week)
        if df.is_empty():
            return {}

        # Get all CB Type 1 rows
        type1 = df.filter(
            pl.col("coverage_player_id").is_null()
            & pl.col("position").is_in(list(CB_ALIGNMENTS))
        )
        if type1.is_empty():
            return {}

        # Get all unique teams with CBs
        teams = type1.select("team").unique()["team"].to_list()

        # Build profiles per team, then group by alignment
        all_profiles: dict[str, list[_CbProfile]] = {a: [] for a in CB_ALIGNMENTS}
        for team in teams:
            profiles = self._build_season_profiles(team, target_season, max_week)
            for alignment, profile in profiles.items():
                all_profiles[alignment].append(profile)

        return all_profiles
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_pff/test_coverage.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/pff/coverage.py tests/test_data/test_pff/test_coverage.py
git commit -m "feat: implement CoverageEngine.compute() orchestration"
```

---

### Task 7: GameContextBuilder Integration

**Files:**
- Modify: `src/fantasy_sim/data/game_context.py`
- Modify: `tests/test_data/test_pff/test_coverage.py`

- [ ] **Step 1: Write integration test**

Add to `test_coverage.py`:

```python
class TestGameContextIntegration:
    """Tests for CoverageEngine integration in GameContextBuilder."""

    def test_apply_coverage_modifies_wr_catch_rate(self):
        """_apply_coverage multiplies WR catch_rate by modifier."""
        from fantasy_sim.data.game_context import GameContextBuilder

        roster = _make_wr_roster("KC", [
            {"player_id": "wr_1", "catch_rate": 0.65},
            {"player_id": "wr_2", "catch_rate": 0.60},
        ])

        modifiers = {
            "wr_1": CoverageModifiers(catch_rate_modifier=0.95, ypr_modifier=0.97),
        }

        GameContextBuilder._apply_coverage(roster, modifiers)

        wr1 = next(p for p in roster.players if p.player_id == "wr_1")
        wr2 = next(p for p in roster.players if p.player_id == "wr_2")

        # wr_1 adjusted: 0.65 * 0.95 = 0.6175
        assert wr1.outcomes.catch_rate == pytest.approx(0.6175, abs=0.001)
        # RZ catch rate also adjusted: (0.65 * 0.92) * 0.95 = 0.5681
        assert wr1.outcomes.red_zone_catch_rate == pytest.approx(
            0.65 * 0.92 * 0.95, abs=0.001
        )
        # wr_2 NOT adjusted (not in modifiers dict)
        assert wr2.outcomes.catch_rate == pytest.approx(0.60, abs=0.001)

    def test_apply_coverage_shifts_receiving_yards(self):
        """_apply_coverage applies additive shift to receiving_yards_dist."""
        from fantasy_sim.data.game_context import GameContextBuilder

        roster = _make_wr_roster("KC", [
            {"player_id": "wr_1", "catch_rate": 0.65},
        ])

        modifiers = {
            "wr_1": CoverageModifiers(catch_rate_modifier=1.0, ypr_modifier=1.03),
        }

        original_yards = roster.players[0].outcomes.receiving_yards_dist.copy()
        GameContextBuilder._apply_coverage(roster, modifiers)

        # ypr_modifier=1.03 → shift = (1.03 - 1.0) * 10.0 = 0.3
        expected = original_yards + 0.3
        np.testing.assert_array_almost_equal(
            roster.players[0].outcomes.receiving_yards_dist, expected
        )

    def test_apply_coverage_skips_non_wr(self):
        """_apply_coverage only modifies WR position players."""
        from fantasy_sim.data.game_context import GameContextBuilder

        roster = _make_wr_roster("KC", [
            {"player_id": "wr_1", "catch_rate": 0.65},
        ])
        # Add an RB
        roster.players.append(PlayerModel(
            "rb_1", "RB", "RB", "KC",
            PlayerUsage(carry_share=0.40),
            PlayerOutcomes(catch_rate=0.70),
        ))

        modifiers = {
            "wr_1": CoverageModifiers(catch_rate_modifier=0.95, ypr_modifier=1.0),
            "rb_1": CoverageModifiers(catch_rate_modifier=0.90, ypr_modifier=0.90),
        }

        GameContextBuilder._apply_coverage(roster, modifiers)

        rb = next(p for p in roster.players if p.player_id == "rb_1")
        assert rb.outcomes.catch_rate == pytest.approx(0.70)  # unchanged
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_pff/test_coverage.py::TestGameContextIntegration -v`
Expected: FAIL

- [ ] **Step 3: Add _apply_coverage static method to GameContextBuilder**

In `game_context.py`, add the import at the top:

```python
from fantasy_sim.data.pff.models import PffConfig, MatchupContext, CoverageModifiers
```

Add after `_apply_matchup`:

```python
    @staticmethod
    def _apply_coverage(
        roster: TeamRoster,
        modifiers: dict[str, CoverageModifiers],
    ) -> None:
        """Apply per-WR coverage modifiers to roster in-place.

        Only modifies WR-position players. Multiplicative for catch_rate,
        additive shift for receiving_yards_dist (same pattern as _apply_matchup).
        """
        if not modifiers:
            return
        for player in roster.players:
            if player.position != "WR":
                continue
            mods = modifiers.get(player.player_id)
            if mods is None:
                continue
            if mods.catch_rate_modifier != 1.0:
                player.outcomes.catch_rate = max(
                    0.0, min(1.0, player.outcomes.catch_rate * mods.catch_rate_modifier)
                )
                player.outcomes.red_zone_catch_rate = max(
                    0.0,
                    min(1.0, player.outcomes.red_zone_catch_rate * mods.catch_rate_modifier),
                )
            if mods.ypr_modifier != 1.0:
                if (
                    player.outcomes.receiving_yards_dist is not None
                    and len(player.outcomes.receiving_yards_dist) > 0
                ):
                    shift = (mods.ypr_modifier - 1.0) * 10.0
                    player.outcomes.receiving_yards_dist = (
                        player.outcomes.receiving_yards_dist + shift
                    )
```

- [ ] **Step 4: Wire CoverageEngine into GameContextBuilder.__init__ and build_game**

In `__init__`, add after the team_context_engine block:

```python
        self._coverage_engine = None

        if self._pff_config.enabled and self._pff_config.coverage.enabled and self._pff_loader:
            from fantasy_sim.data.pff.coverage import CoverageEngine
            self._coverage_engine = CoverageEngine(
                self._pff_loader, self._pff_config.coverage
            )
            logger.info("PFF coverage engine enabled")
```

In `build_game()`, add after the tier engine block (after `_normalize_roster_shares`) but before `return`:

```python
        # PFF coverage matchup (per-WR adjustments, last PFF step)
        if self._coverage_engine is not None and target_season and week:
            self._ensure_pff_crosswalk(training_seasons, target_season)
            home_cov = self._coverage_engine.compute(
                defense_team=away_team,
                offense_roster=home_roster,
                target_season=target_season,
                max_week=week,
                pff_crosswalk=self._pff_crosswalk,
            )
            away_cov = self._coverage_engine.compute(
                defense_team=home_team,
                offense_roster=away_roster,
                target_season=target_season,
                max_week=week,
                pff_crosswalk=self._pff_crosswalk,
            )
            self._apply_coverage(home_roster, home_cov)
            self._apply_coverage(away_roster, away_cov)
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_data/test_pff/test_coverage.py -v`
Expected: All PASS

Run: `uv run pytest tests/ -v --timeout=120`
Expected: All 978+ tests PASS (no regressions)

- [ ] **Step 6: Commit**

```bash
git add src/fantasy_sim/data/game_context.py tests/test_data/test_pff/test_coverage.py
git commit -m "feat: integrate CoverageEngine into GameContextBuilder.build_game()"
```

---

### Task 8: A/B Harness — Coverage Modes + Overrides

**Files:**
- Modify: `scripts/validate_pff_signal.py`

- [ ] **Step 1: Add coverage modes to _build_pff_config**

In `_build_pff_config`, import `CoverageConfig`:

```python
from fantasy_sim.data.pff.models import (
    CoverageConfig, MatchupConfig, PffConfig, TalentConfig,
    TeamContextConfig, TierConfig,
)
```

Add new mode branches:

```python
    elif mode == "coverage+tier":
        matchup_cfg = MatchupConfig(enabled=False)
        talent_cfg = TalentConfig(enabled=False)
        tier_cfg = TierConfig(enabled=True)
        tc_cfg = TeamContextConfig(enabled=False)
        cov_cfg = CoverageConfig(enabled=True)
    elif mode == "coverage+tier+matchup":
        matchup_cfg = MatchupConfig(enabled=True)
        talent_cfg = TalentConfig(enabled=False)
        tier_cfg = TierConfig(enabled=True)
        tc_cfg = TeamContextConfig(enabled=False)
        cov_cfg = CoverageConfig(enabled=True)
```

For all existing modes, add `cov_cfg = CoverageConfig(enabled=False)`.

Add coverage override handling:

```python
    if overrides and "coverage" in overrides:
        for key, val in overrides["coverage"].items():
            if hasattr(cov_cfg, key):
                if key == "factor_clamp" and isinstance(val, list):
                    setattr(cov_cfg, key, tuple(val))
                else:
                    setattr(cov_cfg, key, val)
```

Update the return to include `coverage=cov_cfg`:

```python
    return PffConfig(enabled=True, matchup=matchup_cfg, talent=talent_cfg,
                     tier_engine=tier_cfg, team_context=tc_cfg, coverage=cov_cfg)
```

- [ ] **Step 2: Add coverage modes to argparse choices**

Update the `--mode` argument:

```python
    parser.add_argument(
        "--mode",
        choices=["matchup", "talent", "tier", "matchup+tier",
                 "team_context+tier", "team_context+tier+matchup",
                 "ncaa_rookie+tier", "ncaa_rookie+tier+matchup",
                 "coverage+tier", "coverage+tier+matchup", "all"],
        ...
    )
```

Update mode label detection in `run_backtest_pair` to detect coverage:

```python
    if pff_config.coverage.enabled:
        if pff_config.matchup.enabled and pff_config.tier_engine.enabled:
            mode_label = "coverage+tier+matchup"
        elif pff_config.tier_engine.enabled:
            mode_label = "coverage+tier"
    elif pff_config.team_context.enabled and ...
```

- [ ] **Step 3: Add --config-override docs for coverage**

Update the help text for `--config-override`:

```python
        help='PFF config overrides as JSON. Keys: "talent", "matchup", "tier_engine", '
             '"team_context", "ncaa_rookie", "coverage". '
             'Example: \'{"coverage": {"catch_rate_sensitivity": 0.06}}\'',
```

- [ ] **Step 4: Run existing harness tests**

Run: `uv run pytest tests/ -v --timeout=120`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/validate_pff_signal.py
git commit -m "feat: add coverage+tier and coverage+tier+matchup A/B modes"
```

---

### Task 9: Documentation Updates

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/pff-improvement-roadmap.md`

- [ ] **Step 1: Update CLAUDE.md**

Add to the "Current State" section:

```
- **PFF Coverage Matchup Engine**: Complete — N tests (TBD total). Per-WR coverage adjustments using defense_coverage_matchup facet. Alignment-based CB mapping (RWR→LCB, LWR→RCB, slot→SCB), outcome-based stats with grade stabilizer, catch_rate + YPR modifiers. WR-only, TEs excluded for v1.
```

Add to the "PFF Intelligence Layer" bullet in Key Patterns:

```
**CoverageEngine** (`coverage.py`) computes per-WR modifiers by mapping WR alignment to opposing CB, then computing z-scored catch_rate and YPR factors from the CB's rolling performance profile. Outcome-based stats (catch rate allowed, YPR allowed) serve as primary signal with PFF grades as stabilizer for low-sample CBs (reliability ramp at min_coverage_targets). Applied as the last PFF step in `build_game()` after tier engine and share normalization. Config in `defaults.yaml` under `pff.coverage`. A/B harness modes: `--mode coverage+tier`, `--mode coverage+tier+matchup`.
```

- [ ] **Step 2: Update roadmap**

Mark item #5 as complete in `docs/pff-improvement-roadmap.md`:

```markdown
### 5. ~~Coverage Matchup Adjustments~~ — COMPLETE

**Result:** Per-WR coverage adjustments via alignment-based CB mapping. Outcome-based stats (catch rate allowed, YPR allowed) with PFF grade stabilizer for low-sample CBs. WR-only for v1. Applied as last PFF step after tier engine + normalization. Conservative starting sensitivities (0.04) with tight clamp [0.95, 1.05].

Config in `defaults.yaml` under `pff.coverage`. A/B harness modes: `--mode coverage+tier`, `--mode coverage+tier+matchup`. Config-override supports `coverage` key.
```

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest tests/ -v --timeout=120`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md docs/pff-improvement-roadmap.md
git commit -m "docs: mark coverage matchup adjustments complete, update CLAUDE.md"
```

---

### Follow-up: WR-Specific Validation Metrics

**Not included in this plan** — requires backtester changes to expose per-week per-position data.

The spec calls for a `--wr-coverage-detail` flag with:
1. **WR-only weekly rank_corr** — partially available (BacktestResult.rank_correlations already has WR), but needs per-week granularity
2. **WR weekly MAE by matchup difficulty** — requires per-week data + modifier magnitude per WR-week
3. **Directional accuracy** — requires per-WR per-week actuals vs modifier direction

These should be implemented as a follow-up after the core engine is validated with the standard A/B harness. The standard metrics (overall rank_corr, MAE) serve as a regression check; the WR-specific metrics are needed to confirm the feature adds value for weekly projections.

Recommended approach: extend `BacktestResult` with a `weekly_details` field containing per-week per-position breakdowns, then add post-processing in the harness to compute the three WR-specific metrics.

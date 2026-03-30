# Phase 7A: Data + Engine Accuracy — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 10 core accuracy gaps in the data pipeline and simulation engine: recency weighting, red zone metrics, QB scramble data, penalty modeling, two-minute warning, home-field advantage, two-point conversion tracking, and rookie blend system.

**Architecture:** All changes are additive to existing modules. The `Preprocessor` gains recency weighting via a `season_weights` parameter and a new `compute_penalty_rates()` method. `player_builder.build_player_models()` gains red zone metrics, air yards share, and QB scramble extraction from PBP data. The play resolution layer adds a penalty check post-play and a home-field yards bonus. `clock.py` gains two-minute warning logic. `PlayerBoxScore` gains a `two_point_conversions` field that flows through `game_flow.attempt_pat()` -> `game_sim._update_player_stats()` -> `scoring.engine.score_player()`. The rookie blend system in `player_builder.py` blends sparse real data with archetype profiles based on games played.

**Tech Stack:** Python 3.14, numpy, polars, scipy, pytest

---

## File Structure

```
src/fantasy_sim/
├── data/
│   ├── preprocessor.py       MODIFY: Add season_weights param, compute_penalty_rates()
│   ├── pipeline.py            MODIFY: Pass season_weights through to preprocessor
│   └── player_builder.py      MODIFY: Red zone, air yards, scramble, rookie blend
├── models/
│   ├── player.py              MODIFY: Add air_yards_share to PlayerUsage
│   └── distributions.py       (no changes — PenaltyRates already exists)
├── engine/
│   ├── clock.py               MODIFY: Add two-minute warning logic
│   ├── play_resolver.py       MODIFY: Add penalty check, home-field advantage
│   ├── game_flow.py           MODIFY: Add player attribution to 2PT conversions
│   ├── game_sim.py            MODIFY: Wire penalty into game loop, 2PT stats
│   └── types.py               MODIFY: Add two_point_conversions to PlayerBoxScore, is_penalty to PlayResult
└── scoring/
    └── engine.py              MODIFY: Add two_point_conversions to score_player()

tests/
├── test_data/
│   ├── test_preprocessor.py   MODIFY: Add recency weighting + penalty tests
│   └── test_player_builder.py MODIFY: Add red zone, air yards, scramble, rookie blend tests
├── test_engine/
│   ├── test_clock.py          MODIFY: Add two-minute warning tests
│   ├── test_play_resolver.py  MODIFY: Add penalty + home-field tests
│   ├── test_game_flow.py      MODIFY: Add 2PT attribution tests
│   └── test_game_sim.py       MODIFY: Add penalty integration + 2PT integration tests
└── test_scoring/
    └── test_engine.py         MODIFY: Add two_point scoring test
```

## Dependencies from Phases 1-6

- `models.player.PlayerUsage` — carry_share, target_share, red_zone_carry_share, red_zone_target_share, snap_share, scramble_rate
- `models.player.PlayerOutcomes` — catch_rate, receiving_yards_dist, rushing_yards_dist, scramble_yards_dist, fumble_rate
- `models.player.PlayerModel` — player_id, name, position, team, usage, outcomes, games_played
- `models.distributions.PenaltyRates` — team, penalty_rate, type_distribution, avg_yards (already defined, never instantiated)
- `engine.types.PlayResult` — play_type, yards, is_complete, is_sack, is_interception, is_fumble, is_touchdown, is_safety, clock_runoff, passer_id, receiver_id, rusher_id
- `engine.types.PlayerBoxScore` — passing/rushing/receiving/misc stats
- `engine.types.GameState` — quarter, clock, possession, down, distance, yard_line, home_score, away_score
- `engine.play_resolver.resolve_play()` — returns PlayResult
- `engine.clock.apply_clock()` — subtracts clock runoff
- `engine.game_flow.attempt_pat()` — handles PAT after TD
- `engine.game_sim._update_player_stats()` — records per-player stats from PlayResult
- `scoring.engine.score_player()` — calculates fantasy points from PlayerBoxScore
- `data.preprocessor.Preprocessor` — compute_play_calling, compute_play_outcomes, compute_turnover_rates
- `data.player_builder.build_player_models()` — builds PlayerModel dicts from PBP + roster
- `data.rookie_builder.POSITIONAL_ARCHETYPES` — archetype profiles for rookies
- `config/defaults.yaml` — recency_weights: [0.2, 0.3, 0.5], rookie_blend_games: 4

---

### Task 1: Recency Weighting in Preprocessor

**Files:**
- Modify: `src/fantasy_sim/data/preprocessor.py`
- Modify: `src/fantasy_sim/data/pipeline.py`
- Modify: `tests/test_data/test_preprocessor.py`

**Gaps covered:** Gap 1 (recency weighting not implemented)

- [ ] **Step 1: Write failing tests**

```python
# tests/test_data/test_preprocessor.py — ADD at bottom of file

class TestRecencyWeighting:
    def _make_multi_season_pbp(self) -> pl.DataFrame:
        """PBP with 3 seasons: 2022 is all runs, 2023 is mixed, 2024 is all passes."""
        plays = []
        # 2022: 10 run plays
        for i in range(10):
            plays.append({
                "season": 2022, "week": 1, "game_id": "2022_01_KC",
                "play_type": "run", "posteam": "KC", "defteam": "BUF",
                "down": 1, "ydstogo": 10, "yardline_100": 75,
                "score_differential": 0, "qtr": 1,
                "yards_gained": 4, "complete_pass": 0,
                "pass_attempt": 0, "rush_attempt": 1,
                "interception": 0, "fumble_lost": 0, "sack": 0,
                "touchdown": 0, "penalty": 0, "penalty_yards": 0,
                "passer_player_id": None, "receiver_player_id": None,
                "rusher_player_id": "IP01",
            })
        # 2023: 5 pass, 5 run
        for i in range(5):
            plays.append({
                "season": 2023, "week": 1, "game_id": "2023_01_KC",
                "play_type": "pass", "posteam": "KC", "defteam": "BUF",
                "down": 1, "ydstogo": 10, "yardline_100": 75,
                "score_differential": 0, "qtr": 1,
                "yards_gained": 10, "complete_pass": 1,
                "pass_attempt": 1, "rush_attempt": 0,
                "interception": 0, "fumble_lost": 0, "sack": 0,
                "touchdown": 0, "penalty": 0, "penalty_yards": 0,
                "passer_player_id": "PM15", "receiver_player_id": "TK87",
                "rusher_player_id": None,
            })
        for i in range(5):
            plays.append({
                "season": 2023, "week": 1, "game_id": "2023_01_KC",
                "play_type": "run", "posteam": "KC", "defteam": "BUF",
                "down": 1, "ydstogo": 10, "yardline_100": 75,
                "score_differential": 0, "qtr": 1,
                "yards_gained": 5, "complete_pass": 0,
                "pass_attempt": 0, "rush_attempt": 1,
                "interception": 0, "fumble_lost": 0, "sack": 0,
                "touchdown": 0, "penalty": 0, "penalty_yards": 0,
                "passer_player_id": None, "receiver_player_id": None,
                "rusher_player_id": "IP01",
            })
        # 2024: 10 pass plays
        for i in range(10):
            plays.append({
                "season": 2024, "week": 1, "game_id": "2024_01_KC",
                "play_type": "pass", "posteam": "KC", "defteam": "BUF",
                "down": 1, "ydstogo": 10, "yardline_100": 75,
                "score_differential": 0, "qtr": 1,
                "yards_gained": 12, "complete_pass": 1,
                "pass_attempt": 1, "rush_attempt": 0,
                "interception": 0, "fumble_lost": 0, "sack": 0,
                "touchdown": 0, "penalty": 0, "penalty_yards": 0,
                "passer_player_id": "PM15", "receiver_player_id": "TK87",
                "rusher_player_id": None,
            })
        return pl.DataFrame(plays)

    def test_without_weights_equal_treatment(self):
        """Without weights, all 30 plays are treated equally: 15 pass, 15 run = 50/50."""
        pbp = self._make_multi_season_pbp()
        pre = Preprocessor()
        dists = pre.compute_play_calling(pbp)
        kc = dists["KC"]
        assert kc.default["pass"] == pytest.approx(15 / 30, abs=0.01)
        assert kc.default["run"] == pytest.approx(15 / 30, abs=0.01)

    def test_with_recency_weights_biases_recent(self):
        """With weights {2022: 0.2, 2023: 0.3, 2024: 0.5}, recent pass-heavy data dominates.

        Weighted counts:
          2022: 10 run * 0.2 = 2.0 run, 0 pass
          2023: 5 pass * 0.3 = 1.5 pass, 5 run * 0.3 = 1.5 run
          2024: 10 pass * 0.5 = 5.0 pass, 0 run
        Total: 6.5 pass, 3.5 run => 65% pass rate
        """
        pbp = self._make_multi_season_pbp()
        pre = Preprocessor()
        season_weights = {2022: 0.2, 2023: 0.3, 2024: 0.5}
        dists = pre.compute_play_calling(pbp, season_weights=season_weights)
        kc = dists["KC"]
        assert kc.default["pass"] == pytest.approx(0.65, abs=0.02)
        assert kc.default["run"] == pytest.approx(0.35, abs=0.02)

    def test_play_outcomes_with_recency_weights(self):
        """Weighted play outcomes should bias toward recent season yards."""
        pbp = self._make_multi_season_pbp()
        pre = Preprocessor()
        season_weights = {2022: 0.1, 2023: 0.2, 2024: 0.7}
        dist = pre.compute_play_outcomes(pbp, season_weights=season_weights)
        # Run defaults should exist and contain weighted samples
        assert "run" in dist.defaults
        assert len(dist.defaults["run"]) > 0

    def test_turnover_rates_with_recency_weights(self):
        """Turnover rates should accept season_weights without error."""
        pbp = self._make_multi_season_pbp()
        pre = Preprocessor()
        season_weights = {2022: 0.2, 2023: 0.3, 2024: 0.5}
        rates = pre.compute_turnover_rates(pbp, season_weights=season_weights)
        assert "KC" in rates
        assert 0.0 <= rates["KC"].fumble_rate <= 1.0

    def test_no_weights_backward_compatible(self):
        """Calling without season_weights should produce same results as before."""
        pbp = self._make_multi_season_pbp()
        pre = Preprocessor()
        dists_no_weights = pre.compute_play_calling(pbp)
        dists_none = pre.compute_play_calling(pbp, season_weights=None)
        assert dists_no_weights["KC"].default["pass"] == dists_none["KC"].default["pass"]
```

- [ ] **Step 2: Implement recency weighting in Preprocessor**

```python
# src/fantasy_sim/data/preprocessor.py — FULL REPLACEMENT

import polars as pl
import numpy as np
from fantasy_sim.models.game_state import GameStateBucket, bucket_play
from fantasy_sim.models.distributions import (
    PlayCallingDist, PlayOutcomeDist, TurnoverRates, KickingModel, DriveStartModel,
    PenaltyRates,
)

MIN_BUCKET_PLAYS = 10


class Preprocessor:
    """Computes probability distributions from raw PBP data."""

    def _filter_real_plays(self, pbp: pl.DataFrame) -> pl.DataFrame:
        return pbp.filter(pl.col("play_type").is_in(["pass", "run"]))

    def _apply_season_weights(
        self, plays: pl.DataFrame, season_weights: dict[int, float] | None
    ) -> pl.DataFrame:
        """Duplicate rows proportional to season weights for weighted sampling.

        If season_weights is None, returns plays unchanged.
        Approach: normalize weights so the max weight maps to 1.0 (no duplication
        for the heaviest season), then duplicate lighter seasons less.
        We use integer replication counts: round(weight / max_weight * 10).
        """
        if season_weights is None:
            return plays

        if not season_weights:
            return plays

        max_w = max(season_weights.values())
        if max_w <= 0:
            return plays

        # Build replication counts per season (min 1, max 10)
        rep_counts = {}
        for season, weight in season_weights.items():
            rep_counts[season] = max(1, round(weight / max_w * 10))

        # Replicate each season's rows
        parts = []
        seasons_in_data = plays["season"].unique().to_list()
        for season in seasons_in_data:
            season_plays = plays.filter(pl.col("season") == season)
            count = rep_counts.get(season, 1)
            for _ in range(count):
                parts.append(season_plays)

        if not parts:
            return plays

        return pl.concat(parts)

    def compute_play_calling(
        self, pbp: pl.DataFrame, season_weights: dict[int, float] | None = None,
    ) -> dict[str, PlayCallingDist]:
        """Compute P(run|state) and P(pass|state) per team."""
        plays = self._filter_real_plays(pbp)
        plays = self._apply_season_weights(plays, season_weights)
        teams = plays["posteam"].unique().to_list()
        result = {}

        for team in teams:
            team_plays = plays.filter(pl.col("posteam") == team)
            total = team_plays.shape[0]
            if total == 0:
                continue

            pass_count = team_plays.filter(pl.col("play_type") == "pass").shape[0]
            run_count = total - pass_count
            default = {"pass": pass_count / total, "run": run_count / total}

            bucket_counts: dict[GameStateBucket, dict[str, int]] = {}
            for row in team_plays.iter_rows(named=True):
                bucket = bucket_play(
                    row["down"], row["ydstogo"], row["score_differential"], row["qtr"], row["yardline_100"],
                )
                if bucket not in bucket_counts:
                    bucket_counts[bucket] = {"pass": 0, "run": 0}
                bucket_counts[bucket][row["play_type"]] += 1

            distributions: dict[GameStateBucket, dict[str, float]] = {}
            for bucket, counts in bucket_counts.items():
                total_bucket = counts["pass"] + counts["run"]
                if total_bucket >= MIN_BUCKET_PLAYS:
                    distributions[bucket] = {
                        "pass": counts["pass"] / total_bucket,
                        "run": counts["run"] / total_bucket,
                    }

            result[team] = PlayCallingDist(team=team, distributions=distributions, default=default)

        return result

    def compute_play_outcomes(
        self, pbp: pl.DataFrame, season_weights: dict[int, float] | None = None,
    ) -> PlayOutcomeDist:
        """Compute empirical yards-gained distributions by play type and game state."""
        plays = self._filter_real_plays(pbp)
        plays = self._apply_season_weights(plays, season_weights)

        bucket_yards: dict[tuple[str, GameStateBucket], list[int]] = {}
        defaults: dict[str, list[int]] = {"pass": [], "run": []}

        for row in plays.iter_rows(named=True):
            play_type = row["play_type"]
            yards = row["yards_gained"]
            defaults[play_type].append(yards)

            bucket = bucket_play(
                row["down"], row["ydstogo"], row["score_differential"], row["qtr"], row["yardline_100"],
            )
            key = (play_type, bucket)
            if key not in bucket_yards:
                bucket_yards[key] = []
            bucket_yards[key].append(yards)

        distributions = {}
        for key, yards_list in bucket_yards.items():
            if len(yards_list) >= MIN_BUCKET_PLAYS:
                distributions[key] = np.array(yards_list)

        final_defaults = {k: np.array(v) for k, v in defaults.items() if v}

        return PlayOutcomeDist(distributions=distributions, defaults=final_defaults)

    def compute_turnover_rates(
        self, pbp: pl.DataFrame, season_weights: dict[int, float] | None = None,
    ) -> dict[str, TurnoverRates]:
        """Compute per-team turnover and sack rates from PBP data."""
        plays = self._filter_real_plays(pbp)
        plays = self._apply_season_weights(plays, season_weights)
        teams = plays["posteam"].unique().to_list()
        result = {}

        for team in teams:
            team_plays = plays.filter(pl.col("posteam") == team)
            total_plays = team_plays.shape[0]
            pass_plays = team_plays.filter(pl.col("play_type") == "pass")
            total_passes = pass_plays.shape[0]

            if total_plays == 0:
                continue

            ints = team_plays.filter(pl.col("interception") == 1).shape[0]
            fumbles = team_plays.filter(pl.col("fumble_lost") == 1).shape[0]
            sacks = team_plays.filter(pl.col("sack") == 1).shape[0]

            int_rate = ints / total_passes if total_passes > 0 else 0.0
            fumble_rate = fumbles / total_plays
            sack_rate = sacks / total_passes if total_passes > 0 else 0.0

            sack_plays = team_plays.filter(pl.col("sack") == 1)
            if sack_plays.shape[0] > 0:
                sack_fumbles = sack_plays.filter(pl.col("fumble_lost") == 1).shape[0]
                sack_fumble_rate = sack_fumbles / sack_plays.shape[0]
            else:
                sack_fumble_rate = 0.10  # League average fallback

            result[team] = TurnoverRates(
                team=team, int_rate=int_rate, fumble_rate=fumble_rate,
                sack_rate=sack_rate, sack_fumble_rate=sack_fumble_rate,
            )

        return result

    def compute_kicking_model(self, pbp: pl.DataFrame, xp_data: pl.DataFrame | None = None) -> KickingModel:
        """Compute FG make rates by distance bucket and XP rate."""
        fg_plays = pbp.filter(pl.col("play_type") == "field_goal")

        buckets = {
            "0_39": {"made": 0, "total": 0},
            "40_49": {"made": 0, "total": 0},
            "50_plus": {"made": 0, "total": 0},
        }

        for row in fg_plays.iter_rows(named=True):
            dist = row["kick_distance"]
            if dist < 40:
                bucket = "0_39"
            elif dist < 50:
                bucket = "40_49"
            else:
                bucket = "50_plus"
            buckets[bucket]["total"] += 1
            if row["field_goal_result"] == "made":
                buckets[bucket]["made"] += 1

        league_avg = {"0_39": 0.95, "40_49": 0.82, "50_plus": 0.65}
        fg_make_rate = {}
        for bucket, counts in buckets.items():
            if counts["total"] == 0:
                fg_make_rate[bucket] = league_avg[bucket]
            else:
                fg_make_rate[bucket] = counts["made"] / counts["total"]

        if xp_data is not None and xp_data.shape[0] > 0:
            xp_plays = xp_data.filter(pl.col("play_type") == "extra_point")
            if xp_plays.shape[0] > 0:
                xp_made = xp_plays.filter(pl.col("extra_point_result") == "good").shape[0]
                xp_rate = xp_made / xp_plays.shape[0]
            else:
                xp_rate = 0.94
        else:
            xp_rate = 0.94

        return KickingModel(fg_make_rate=fg_make_rate, xp_rate=xp_rate)

    def compute_drive_start_model(self, pbp: pl.DataFrame) -> DriveStartModel:
        """Compute kickoff return / touchback distributions."""
        kickoffs = pbp.filter(pl.col("play_type") == "kickoff")

        if kickoffs.shape[0] == 0:
            return DriveStartModel(
                touchback_rate=0.55, touchback_yardline=75,
                return_yardlines=np.array([72, 74, 76, 78, 80]),
            )

        touchbacks = kickoffs.filter(pl.col("touchback") == 1)
        returns = kickoffs.filter(pl.col("touchback") == 0)

        touchback_rate = touchbacks.shape[0] / kickoffs.shape[0]

        if touchbacks.shape[0] > 0:
            touchback_yardline = int(touchbacks["yardline_100"].mean())
        else:
            touchback_yardline = 75

        if returns.shape[0] > 0:
            return_yardlines = returns["yardline_100"].to_numpy()
        else:
            return_yardlines = np.array([72, 74, 76, 78, 80])

        return DriveStartModel(
            touchback_rate=touchback_rate, touchback_yardline=touchback_yardline,
            return_yardlines=return_yardlines,
        )

    def compute_penalty_rates(self, pbp: pl.DataFrame) -> dict[str, PenaltyRates]:
        """Compute per-team penalty rates from PBP data."""
        plays = self._filter_real_plays(pbp)
        teams = plays["posteam"].unique().to_list()
        result = {}

        for team in teams:
            team_plays = plays.filter(pl.col("posteam") == team)
            total_plays = team_plays.shape[0]
            if total_plays == 0:
                continue

            penalty_plays = team_plays.filter(pl.col("penalty") == 1)
            penalty_count = penalty_plays.shape[0]
            penalty_rate = penalty_count / total_plays

            if penalty_rate == 0.0:
                # Use league average fallback
                penalty_rate = 0.07
                type_distribution = {
                    "false_start": 0.30,
                    "holding": 0.40,
                    "pass_interference": 0.15,
                    "other": 0.15,
                }
                avg_yards = {
                    "false_start": 5.0,
                    "holding": 10.0,
                    "pass_interference": 15.0,
                    "other": 5.0,
                }
            else:
                # Derive from penalty_yards column to approximate type distribution
                if penalty_plays.shape[0] > 0 and "penalty_yards" in penalty_plays.columns:
                    yards_list = penalty_plays["penalty_yards"].to_list()
                    five_yd = sum(1 for y in yards_list if y is not None and abs(y) <= 5)
                    ten_yd = sum(1 for y in yards_list if y is not None and 6 <= abs(y) <= 10)
                    long_yd = sum(1 for y in yards_list if y is not None and abs(y) > 10)
                    total_p = max(five_yd + ten_yd + long_yd, 1)
                    type_distribution = {
                        "false_start": five_yd / total_p,
                        "holding": ten_yd / total_p,
                        "pass_interference": long_yd / total_p,
                        "other": 0.0,
                    }
                    avg_yards = {
                        "false_start": 5.0,
                        "holding": 10.0,
                        "pass_interference": 15.0,
                        "other": 5.0,
                    }
                else:
                    type_distribution = {
                        "false_start": 0.30,
                        "holding": 0.40,
                        "pass_interference": 0.15,
                        "other": 0.15,
                    }
                    avg_yards = {
                        "false_start": 5.0,
                        "holding": 10.0,
                        "pass_interference": 15.0,
                        "other": 5.0,
                    }

            result[team] = PenaltyRates(
                team=team,
                penalty_rate=penalty_rate,
                type_distribution=type_distribution,
                avg_yards=avg_yards,
            )

        return result
```

- [ ] **Step 3: Update pipeline to pass season_weights**

```python
# src/fantasy_sim/data/pipeline.py — FULL REPLACEMENT

from pathlib import Path
import polars as pl
from fantasy_sim.data.loader import DataLoader
from fantasy_sim.data.preprocessor import Preprocessor


class DataPipeline:
    """Orchestrates data loading and preprocessing into distributions."""

    def __init__(self, cache_dir: Path, seasons: list[int]):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.seasons = seasons
        self.loader = DataLoader(cache_dir=self.cache_dir)
        self.preprocessor = Preprocessor()

    def build(
        self,
        pbp: pl.DataFrame | None = None,
        fg_data: pl.DataFrame | None = None,
        kickoff_data: pl.DataFrame | None = None,
        season_weights: dict[int, float] | None = None,
    ) -> dict:
        """Build all distributions from raw data.

        Pass dataframes directly for testing, or leave None to load from nflreadpy.
        season_weights: optional dict mapping season year to weight (e.g., {2022: 0.2, 2023: 0.3, 2024: 0.5}).
        """
        if pbp is None:
            pbp = self.loader.load_pbp(self.seasons)
        if fg_data is None:
            fg_data = pbp.filter(pl.col("play_type") == "field_goal")
        if kickoff_data is None:
            kickoff_data = pbp.filter(pl.col("play_type") == "kickoff")
        xp_data = pbp.filter(pl.col("play_type") == "extra_point")

        return {
            "play_calling": self.preprocessor.compute_play_calling(pbp, season_weights=season_weights),
            "play_outcomes": self.preprocessor.compute_play_outcomes(pbp, season_weights=season_weights),
            "turnover_rates": self.preprocessor.compute_turnover_rates(pbp, season_weights=season_weights),
            "kicking": self.preprocessor.compute_kicking_model(fg_data, xp_data=xp_data),
            "drive_start": self.preprocessor.compute_drive_start_model(kickoff_data),
            "penalty_rates": self.preprocessor.compute_penalty_rates(pbp),
        }
```

- [ ] **Step 4: Run tests and verify**

```bash
uv run pytest tests/test_data/test_preprocessor.py -v
```

- [ ] **Step 5: Commit**

```
feat: add recency weighting to preprocessor and penalty rate computation

Preprocessor.compute_play_calling, compute_play_outcomes, and
compute_turnover_rates now accept an optional season_weights parameter.
Rows from each season are replicated proportionally so recent data has
more influence. Also adds compute_penalty_rates() which builds
PenaltyRates from PBP penalty columns. Pipeline.build() now passes
season_weights through and includes penalty_rates in output.
```

---

### Task 2: Player Builder Improvements — Red Zone, Air Yards, Scramble Data

**Files:**
- Modify: `src/fantasy_sim/models/player.py`
- Modify: `src/fantasy_sim/data/player_builder.py`
- Modify: `tests/test_data/test_player_builder.py`
- Modify: `tests/conftest.py`

**Gaps covered:** Gap 2 (red zone metrics), Gap 3 (air yards share), Gap 4 (QB scramble data), Gap 10 (scramble rate)

- [ ] **Step 1: Write failing tests**

```python
# tests/test_data/test_player_builder.py — ADD at bottom of file

class TestRedZoneMetrics:
    def test_red_zone_target_share_computed(self, rz_pbp, sample_rosters):
        """When PBP contains red zone plays (yardline_100 <= 20), target shares are computed."""
        models = build_player_models(rz_pbp, sample_rosters, seasons=[2024])
        # SD14 is the only receiver in red zone plays in rz_pbp
        sd = models.get("SD14")
        assert sd is not None
        assert sd.usage.red_zone_target_share > 0

    def test_red_zone_carry_share_computed(self, rz_pbp, sample_rosters):
        """Red zone carry shares should be computed for RBs."""
        models = build_player_models(rz_pbp, sample_rosters, seasons=[2024])
        ip = models.get("IP01")
        assert ip is not None
        assert ip.usage.red_zone_carry_share > 0


class TestAirYardsShare:
    def test_air_yards_share_computed(self, air_yards_pbp, sample_rosters):
        """Receivers should have air_yards_share when air_yards column exists."""
        models = build_player_models(air_yards_pbp, sample_rosters, seasons=[2024])
        tk = models.get("TK87")
        assert tk is not None
        assert tk.usage.air_yards_share > 0

    def test_air_yards_share_sums_near_one(self, air_yards_pbp, sample_rosters):
        """Air yards shares for receivers on one team should sum near 1.0."""
        models = build_player_models(air_yards_pbp, sample_rosters, seasons=[2024])
        kc_receivers = [m for m in models.values() if m.team == "KC" and m.usage.air_yards_share > 0]
        total = sum(p.usage.air_yards_share for p in kc_receivers)
        assert total == pytest.approx(1.0, abs=0.05)


class TestQBScrambleData:
    def test_qb_scramble_rate_from_pbp(self, scramble_pbp, sample_rosters):
        """QB scramble rate should be computed from PBP rush attempts by the QB."""
        models = build_player_models(scramble_pbp, sample_rosters, seasons=[2024])
        ja = models.get("JA17")
        assert ja is not None
        assert ja.usage.scramble_rate > 0

    def test_qb_scramble_yards_dist(self, scramble_pbp, sample_rosters):
        """QB should have scramble_yards_dist built from PBP rush plays."""
        models = build_player_models(scramble_pbp, sample_rosters, seasons=[2024])
        ja = models.get("JA17")
        assert ja is not None
        assert ja.outcomes.scramble_yards_dist is not None
        assert len(ja.outcomes.scramble_yards_dist) > 0

    def test_non_qb_has_no_scramble_rate(self, scramble_pbp, sample_rosters):
        """RBs should not have a scramble_rate set."""
        models = build_player_models(scramble_pbp, sample_rosters, seasons=[2024])
        jc = models.get("JC02")
        assert jc is not None
        assert jc.usage.scramble_rate == 0.0
```

- [ ] **Step 2: Add test fixtures to conftest.py**

```python
# tests/conftest.py — ADD these fixtures after the existing ones

@pytest.fixture
def rz_pbp() -> pl.DataFrame:
    """PBP with red zone plays (yardline_100 <= 20)."""
    plays = []
    # KC: 5 non-red-zone passes, 5 red-zone passes to TK87/RE11, 5 non-rz runs, 3 rz runs
    for i in range(5):
        plays.append({
            "season": 2024, "week": 1, "game_id": "2024_01_KC",
            "play_type": "pass", "posteam": "KC", "defteam": "BUF",
            "down": 1, "ydstogo": 10, "yardline_100": 50,
            "score_differential": 0, "qtr": 1,
            "yards_gained": 8, "complete_pass": 1,
            "pass_attempt": 1, "rush_attempt": 0,
            "interception": 0, "fumble_lost": 0, "sack": 0,
            "touchdown": 0, "penalty": 0, "penalty_yards": 0,
            "passer_player_id": "PM15", "receiver_player_id": "TK87",
            "rusher_player_id": None, "air_yards": 6,
        })
    for i in range(5):
        plays.append({
            "season": 2024, "week": 1, "game_id": "2024_01_KC",
            "play_type": "pass", "posteam": "KC", "defteam": "BUF",
            "down": 1, "ydstogo": 10, "yardline_100": 15,
            "score_differential": 0, "qtr": 2,
            "yards_gained": 12, "complete_pass": 1,
            "pass_attempt": 1, "rush_attempt": 0,
            "interception": 0, "fumble_lost": 0, "sack": 0,
            "touchdown": 1, "penalty": 0, "penalty_yards": 0,
            "passer_player_id": "PM15", "receiver_player_id": "RE11",
            "rusher_player_id": None, "air_yards": 10,
        })
    for i in range(5):
        plays.append({
            "season": 2024, "week": 1, "game_id": "2024_01_KC",
            "play_type": "run", "posteam": "KC", "defteam": "BUF",
            "down": 1, "ydstogo": 10, "yardline_100": 50,
            "score_differential": 0, "qtr": 1,
            "yards_gained": 5, "complete_pass": 0,
            "pass_attempt": 0, "rush_attempt": 1,
            "interception": 0, "fumble_lost": 0, "sack": 0,
            "touchdown": 0, "penalty": 0, "penalty_yards": 0,
            "passer_player_id": None, "receiver_player_id": None,
            "rusher_player_id": "IP01", "air_yards": None,
        })
    for i in range(3):
        plays.append({
            "season": 2024, "week": 1, "game_id": "2024_01_KC",
            "play_type": "run", "posteam": "KC", "defteam": "BUF",
            "down": 1, "ydstogo": 5, "yardline_100": 10,
            "score_differential": 0, "qtr": 2,
            "yards_gained": 3, "complete_pass": 0,
            "pass_attempt": 0, "rush_attempt": 1,
            "interception": 0, "fumble_lost": 0, "sack": 0,
            "touchdown": 0, "penalty": 0, "penalty_yards": 0,
            "passer_player_id": None, "receiver_player_id": None,
            "rusher_player_id": "IP01", "air_yards": None,
        })
    # BUF: 5 passes including 3 red zone to SD14, 5 runs including 2 red zone
    for i in range(2):
        plays.append({
            "season": 2024, "week": 1, "game_id": "2024_01_BUF",
            "play_type": "pass", "posteam": "BUF", "defteam": "KC",
            "down": 1, "ydstogo": 10, "yardline_100": 50,
            "score_differential": 0, "qtr": 1,
            "yards_gained": 10, "complete_pass": 1,
            "pass_attempt": 1, "rush_attempt": 0,
            "interception": 0, "fumble_lost": 0, "sack": 0,
            "touchdown": 0, "penalty": 0, "penalty_yards": 0,
            "passer_player_id": "JA17", "receiver_player_id": "SD14",
            "rusher_player_id": None, "air_yards": 8,
        })
    for i in range(3):
        plays.append({
            "season": 2024, "week": 1, "game_id": "2024_01_BUF",
            "play_type": "pass", "posteam": "BUF", "defteam": "KC",
            "down": 1, "ydstogo": 5, "yardline_100": 12,
            "score_differential": 0, "qtr": 2,
            "yards_gained": 10, "complete_pass": 1,
            "pass_attempt": 1, "rush_attempt": 0,
            "interception": 0, "fumble_lost": 0, "sack": 0,
            "touchdown": 1, "penalty": 0, "penalty_yards": 0,
            "passer_player_id": "JA17", "receiver_player_id": "SD14",
            "rusher_player_id": None, "air_yards": 7,
        })
    for i in range(3):
        plays.append({
            "season": 2024, "week": 1, "game_id": "2024_01_BUF",
            "play_type": "run", "posteam": "BUF", "defteam": "KC",
            "down": 1, "ydstogo": 10, "yardline_100": 50,
            "score_differential": 0, "qtr": 1,
            "yards_gained": 4, "complete_pass": 0,
            "pass_attempt": 0, "rush_attempt": 1,
            "interception": 0, "fumble_lost": 0, "sack": 0,
            "touchdown": 0, "penalty": 0, "penalty_yards": 0,
            "passer_player_id": None, "receiver_player_id": None,
            "rusher_player_id": "JC02", "air_yards": None,
        })
    for i in range(2):
        plays.append({
            "season": 2024, "week": 1, "game_id": "2024_01_BUF",
            "play_type": "run", "posteam": "BUF", "defteam": "KC",
            "down": 1, "ydstogo": 5, "yardline_100": 8,
            "score_differential": 0, "qtr": 2,
            "yards_gained": 2, "complete_pass": 0,
            "pass_attempt": 0, "rush_attempt": 1,
            "interception": 0, "fumble_lost": 0, "sack": 0,
            "touchdown": 0, "penalty": 0, "penalty_yards": 0,
            "passer_player_id": None, "receiver_player_id": None,
            "rusher_player_id": "JC02", "air_yards": None,
        })
    return pl.DataFrame(plays)


@pytest.fixture
def air_yards_pbp() -> pl.DataFrame:
    """PBP with air_yards column for computing air yards share."""
    plays = []
    # KC: 10 passes with air_yards (TK87 gets 60%, RE11 gets 30%, IP01 gets 10%)
    for i in range(6):
        plays.append({
            "season": 2024, "week": 1, "game_id": "2024_01_KC",
            "play_type": "pass", "posteam": "KC", "defteam": "BUF",
            "down": 1, "ydstogo": 10, "yardline_100": 50,
            "score_differential": 0, "qtr": 1,
            "yards_gained": 8, "complete_pass": 1,
            "pass_attempt": 1, "rush_attempt": 0,
            "interception": 0, "fumble_lost": 0, "sack": 0,
            "touchdown": 0, "penalty": 0, "penalty_yards": 0,
            "passer_player_id": "PM15", "receiver_player_id": "TK87",
            "rusher_player_id": None, "air_yards": 10,
        })
    for i in range(3):
        plays.append({
            "season": 2024, "week": 1, "game_id": "2024_01_KC",
            "play_type": "pass", "posteam": "KC", "defteam": "BUF",
            "down": 1, "ydstogo": 10, "yardline_100": 50,
            "score_differential": 0, "qtr": 2,
            "yards_gained": 12, "complete_pass": 1,
            "pass_attempt": 1, "rush_attempt": 0,
            "interception": 0, "fumble_lost": 0, "sack": 0,
            "touchdown": 0, "penalty": 0, "penalty_yards": 0,
            "passer_player_id": "PM15", "receiver_player_id": "RE11",
            "rusher_player_id": None, "air_yards": 10,
        })
    plays.append({
        "season": 2024, "week": 1, "game_id": "2024_01_KC",
        "play_type": "pass", "posteam": "KC", "defteam": "BUF",
        "down": 1, "ydstogo": 10, "yardline_100": 50,
        "score_differential": 0, "qtr": 2,
        "yards_gained": 5, "complete_pass": 1,
        "pass_attempt": 1, "rush_attempt": 0,
        "interception": 0, "fumble_lost": 0, "sack": 0,
        "touchdown": 0, "penalty": 0, "penalty_yards": 0,
        "passer_player_id": "PM15", "receiver_player_id": "IP01",
        "rusher_player_id": None, "air_yards": 10,
    })
    # 5 run plays
    for i in range(5):
        plays.append({
            "season": 2024, "week": 1, "game_id": "2024_01_KC",
            "play_type": "run", "posteam": "KC", "defteam": "BUF",
            "down": 1, "ydstogo": 10, "yardline_100": 50,
            "score_differential": 0, "qtr": 1,
            "yards_gained": 4, "complete_pass": 0,
            "pass_attempt": 0, "rush_attempt": 1,
            "interception": 0, "fumble_lost": 0, "sack": 0,
            "touchdown": 0, "penalty": 0, "penalty_yards": 0,
            "passer_player_id": None, "receiver_player_id": None,
            "rusher_player_id": "IP01", "air_yards": None,
        })
    return pl.DataFrame(plays)


@pytest.fixture
def scramble_pbp() -> pl.DataFrame:
    """PBP where JA17 (QB) has rush attempts mixed in (scrambles)."""
    plays = []
    # JA17 pass plays: 10
    for i in range(10):
        plays.append({
            "season": 2024, "week": 1, "game_id": "2024_01_BUF",
            "play_type": "pass", "posteam": "BUF", "defteam": "KC",
            "down": 1, "ydstogo": 10, "yardline_100": 50,
            "score_differential": 0, "qtr": 1,
            "yards_gained": 8, "complete_pass": 1,
            "pass_attempt": 1, "rush_attempt": 0,
            "interception": 0, "fumble_lost": 0, "sack": 0,
            "touchdown": 0, "penalty": 0, "penalty_yards": 0,
            "passer_player_id": "JA17", "receiver_player_id": "SD14",
            "rusher_player_id": None,
        })
    # JA17 scramble/rush plays: 3
    for i in range(3):
        plays.append({
            "season": 2024, "week": 1, "game_id": "2024_01_BUF",
            "play_type": "run", "posteam": "BUF", "defteam": "KC",
            "down": 2, "ydstogo": 8, "yardline_100": 45,
            "score_differential": 0, "qtr": 2,
            "yards_gained": 6 + i * 2, "complete_pass": 0,
            "pass_attempt": 0, "rush_attempt": 1,
            "interception": 0, "fumble_lost": 0, "sack": 0,
            "touchdown": 0, "penalty": 0, "penalty_yards": 0,
            "passer_player_id": None, "receiver_player_id": None,
            "rusher_player_id": "JA17",
        })
    # JC02 rush plays: 7
    for i in range(7):
        plays.append({
            "season": 2024, "week": 1, "game_id": "2024_01_BUF",
            "play_type": "run", "posteam": "BUF", "defteam": "KC",
            "down": 1, "ydstogo": 10, "yardline_100": 60,
            "score_differential": 0, "qtr": 1,
            "yards_gained": 4, "complete_pass": 0,
            "pass_attempt": 0, "rush_attempt": 1,
            "interception": 0, "fumble_lost": 0, "sack": 0,
            "touchdown": 0, "penalty": 0, "penalty_yards": 0,
            "passer_player_id": None, "receiver_player_id": None,
            "rusher_player_id": "JC02",
        })
    return pl.DataFrame(plays)
```

- [ ] **Step 3: Add air_yards_share to PlayerUsage**

```python
# src/fantasy_sim/models/player.py — MODIFY PlayerUsage dataclass

@dataclass
class PlayerUsage:
    """How often a player is involved in plays."""
    carry_share: float = 0.0
    red_zone_carry_share: float = 0.0
    target_share: float = 0.0
    red_zone_target_share: float = 0.0
    air_yards_share: float = 0.0
    snap_share: float = 0.0
    scramble_rate: float = 0.0
```

- [ ] **Step 4: Implement red zone, air yards, scramble in player_builder**

```python
# src/fantasy_sim/data/player_builder.py — FULL REPLACEMENT

"""Build PlayerModel objects from PBP and roster data."""

import polars as pl
import numpy as np
from fantasy_sim.models.player import PlayerModel, PlayerUsage, PlayerOutcomes, TeamRoster

MIN_PLAYER_PLAYS = 5


def build_player_models(
    pbp: pl.DataFrame,
    rosters: pl.DataFrame,
    seasons: list[int],
) -> dict[str, PlayerModel]:
    """Build PlayerModels from PBP and roster data. Returns dict keyed by player_id."""
    plays = pbp.filter(
        pl.col("play_type").is_in(["pass", "run"]) &
        pl.col("season").is_in(seasons)
    )

    player_meta = (
        rosters.filter(pl.col("season").is_in(seasons))
        .sort(["season", "week"], descending=True)
        .group_by("player_id")
        .first()
        .select(["player_id", "player_name", "position", "team"])
    )
    meta_map = {
        row["player_id"]: row
        for row in player_meta.iter_rows(named=True)
    }

    # --- Team-level totals ---
    team_pass_attempts = {}
    team_rush_attempts = {}
    team_rz_pass_attempts = {}
    team_rz_rush_attempts = {}
    team_air_yards = {}

    for team in plays["posteam"].unique().to_list():
        tp = plays.filter(pl.col("posteam") == team)
        team_pass_plays = tp.filter(pl.col("play_type") == "pass")
        team_rush_plays = tp.filter(pl.col("play_type") == "run")
        team_pass_attempts[team] = team_pass_plays.shape[0]
        team_rush_attempts[team] = team_rush_plays.shape[0]

        # Red zone totals
        rz_plays = tp.filter(pl.col("yardline_100") <= 20)
        team_rz_pass_attempts[team] = rz_plays.filter(pl.col("play_type") == "pass").shape[0]
        team_rz_rush_attempts[team] = rz_plays.filter(pl.col("play_type") == "run").shape[0]

        # Air yards totals
        if "air_yards" in team_pass_plays.columns:
            ay_col = team_pass_plays["air_yards"]
            team_air_yards[team] = ay_col.drop_nulls().sum()
        else:
            team_air_yards[team] = 0

    # --- Receiving stats ---
    pass_plays = plays.filter(pl.col("play_type") == "pass")
    has_air_yards = "air_yards" in pass_plays.columns

    receiving_stats = {}
    for row in pass_plays.iter_rows(named=True):
        rid = row.get("receiver_player_id")
        if rid is None:
            continue
        if rid not in receiving_stats:
            receiving_stats[rid] = {
                "targets": 0, "catches": 0, "yards": [],
                "team": row["posteam"],
                "rz_targets": 0, "air_yards": 0,
            }
        receiving_stats[rid]["targets"] += 1
        if row["complete_pass"] == 1:
            receiving_stats[rid]["catches"] += 1
            receiving_stats[rid]["yards"].append(row["yards_gained"])
        # Red zone targets
        if row["yardline_100"] <= 20:
            receiving_stats[rid]["rz_targets"] += 1
        # Air yards
        if has_air_yards:
            ay = row.get("air_yards")
            if ay is not None:
                receiving_stats[rid]["air_yards"] += ay

    # --- Rushing stats ---
    rush_plays = plays.filter(pl.col("play_type") == "run")
    rushing_stats = {}
    for row in rush_plays.iter_rows(named=True):
        rid = row.get("rusher_player_id")
        if rid is None:
            continue
        if rid not in rushing_stats:
            rushing_stats[rid] = {
                "carries": 0, "yards": [], "team": row["posteam"],
                "rz_carries": 0,
            }
        rushing_stats[rid]["carries"] += 1
        rushing_stats[rid]["yards"].append(row["yards_gained"])
        # Red zone carries
        if row["yardline_100"] <= 20:
            rushing_stats[rid]["rz_carries"] += 1

    # --- QB stats (passing) ---
    qb_stats = {}
    for row in pass_plays.iter_rows(named=True):
        pid = row.get("passer_player_id")
        if pid is None:
            continue
        if pid not in qb_stats:
            qb_stats[pid] = {"attempts": 0, "team": row["posteam"]}
        qb_stats[pid]["attempts"] += 1

    # --- Build models ---
    models = {}
    all_player_ids = set()
    all_player_ids.update(receiving_stats.keys())
    all_player_ids.update(rushing_stats.keys())
    all_player_ids.update(qb_stats.keys())

    for pid in all_player_ids:
        meta = meta_map.get(pid)
        if meta is None:
            continue

        team = meta["team"]
        position = meta["position"]

        usage = PlayerUsage()

        # Receiving usage
        if pid in receiving_stats:
            rs = receiving_stats[pid]
            team_pa = team_pass_attempts.get(team, 0)
            usage.target_share = rs["targets"] / max(team_pa, 1)

            # Red zone target share
            rz_pa = team_rz_pass_attempts.get(team, 0)
            usage.red_zone_target_share = rs["rz_targets"] / max(rz_pa, 1)

            # Air yards share
            team_ay = team_air_yards.get(team, 0)
            if team_ay > 0 and has_air_yards:
                usage.air_yards_share = rs["air_yards"] / team_ay

        # Rushing usage
        if pid in rushing_stats:
            rs = rushing_stats[pid]
            team_ra = team_rush_attempts.get(team, 0)
            usage.carry_share = rs["carries"] / max(team_ra, 1)

            # Red zone carry share
            rz_ra = team_rz_rush_attempts.get(team, 0)
            usage.red_zone_carry_share = rs["rz_carries"] / max(rz_ra, 1)

        # QB usage
        if position == "QB" and pid in qb_stats:
            qs = qb_stats[pid]
            team_pa = team_pass_attempts.get(team, 0)
            usage.snap_share = qs["attempts"] / max(team_pa, 1)

            # Scramble rate: QB rush attempts / (QB pass attempts + QB rush attempts)
            qb_rush_attempts = rushing_stats.get(pid, {}).get("carries", 0)
            qb_pass_attempts = qs["attempts"]
            total_qb_plays = qb_pass_attempts + qb_rush_attempts
            if total_qb_plays > 0:
                usage.scramble_rate = qb_rush_attempts / total_qb_plays

        outcomes = PlayerOutcomes()
        if pid in receiving_stats:
            rs = receiving_stats[pid]
            if rs["targets"] > 0:
                outcomes.catch_rate = rs["catches"] / rs["targets"]
            if len(rs["yards"]) >= MIN_PLAYER_PLAYS:
                outcomes.receiving_yards_dist = np.array(rs["yards"])
        if pid in rushing_stats:
            rs = rushing_stats[pid]
            if position == "QB":
                # QB rush yards go to scramble_yards_dist
                if len(rs["yards"]) >= MIN_PLAYER_PLAYS:
                    outcomes.scramble_yards_dist = np.array(rs["yards"])
            else:
                if len(rs["yards"]) >= MIN_PLAYER_PLAYS:
                    outcomes.rushing_yards_dist = np.array(rs["yards"])

        # Count games played for rookie blend system
        player_games = _count_games(plays, pid)

        models[pid] = PlayerModel(
            player_id=pid,
            name=meta["player_name"],
            position=position,
            team=team,
            usage=usage,
            outcomes=outcomes,
            games_played=player_games,
        )

    return models


def _count_games(plays: pl.DataFrame, player_id: str) -> int:
    """Count distinct game_ids where this player appears."""
    player_plays = plays.filter(
        (pl.col("passer_player_id") == player_id) |
        (pl.col("receiver_player_id") == player_id) |
        (pl.col("rusher_player_id") == player_id)
    )
    if "game_id" in player_plays.columns:
        return player_plays["game_id"].n_unique()
    return 17  # Default fallback


def build_team_roster(team: str, models: dict[str, PlayerModel]) -> TeamRoster:
    """Build a TeamRoster from a dict of PlayerModels."""
    team_players = [m for m in models.values() if m.team == team]
    return TeamRoster(team=team, players=team_players)
```

- [ ] **Step 5: Run tests and verify**

```bash
uv run pytest tests/test_data/test_player_builder.py -v
```

- [ ] **Step 6: Commit**

```
feat: add red zone metrics, air yards share, and QB scramble extraction to player builder

player_builder now computes red_zone_target_share and red_zone_carry_share
by filtering PBP to yardline_100 <= 20. Air yards share is computed from
the air_yards column when present. QB scramble_rate is derived from
QB rush attempts / total QB plays, and scramble_yards_dist is built from
QB rush yard data. PlayerUsage gains air_yards_share field. games_played
is now tracked per player for future rookie blend support.
```

---

### Task 3: Penalty Modeling in Engine

**Files:**
- Modify: `src/fantasy_sim/engine/play_resolver.py`
- Modify: `src/fantasy_sim/engine/game_sim.py`
- Modify: `src/fantasy_sim/engine/types.py`
- Modify: `tests/test_engine/test_play_resolver.py`
- Modify: `tests/test_engine/test_game_sim.py`

**Gaps covered:** Gap 5 (penalty modeling not implemented)

- [ ] **Step 1: Write failing tests**

```python
# tests/test_engine/test_play_resolver.py — ADD at bottom of file

from fantasy_sim.models.distributions import PenaltyRates


def make_penalty_rates(**overrides) -> PenaltyRates:
    defaults = dict(
        team="KC",
        penalty_rate=0.0,
        type_distribution={"false_start": 0.30, "holding": 0.40, "pass_interference": 0.15, "other": 0.15},
        avg_yards={"false_start": 5.0, "holding": 10.0, "pass_interference": 15.0, "other": 5.0},
    )
    defaults.update(overrides)
    return PenaltyRates(**defaults)


class TestPenaltyCheck:
    def test_no_penalty_when_rate_zero(self):
        """With penalty_rate=0, check_penalty should return None."""
        from fantasy_sim.engine.play_resolver import check_penalty
        rng = np.random.default_rng(42)
        rates = make_penalty_rates(penalty_rate=0.0)
        result = check_penalty(rates, rng)
        assert result is None

    def test_always_penalty_when_rate_one(self):
        """With penalty_rate=1.0, check_penalty should always return a penalty tuple."""
        from fantasy_sim.engine.play_resolver import check_penalty
        rng = np.random.default_rng(42)
        rates = make_penalty_rates(penalty_rate=1.0)
        result = check_penalty(rates, rng)
        assert result is not None
        penalty_type, yards = result
        assert penalty_type in ("false_start", "holding", "pass_interference", "other")
        assert yards > 0

    def test_false_start_returns_5_yards(self):
        """False start penalties should be 5 yards."""
        from fantasy_sim.engine.play_resolver import check_penalty
        rng = np.random.default_rng(42)
        rates = make_penalty_rates(
            penalty_rate=1.0,
            type_distribution={"false_start": 1.0, "holding": 0.0, "pass_interference": 0.0, "other": 0.0},
        )
        result = check_penalty(rates, rng)
        assert result is not None
        penalty_type, yards = result
        assert penalty_type == "false_start"
        assert yards == 5

    def test_holding_returns_10_yards(self):
        """Holding penalties should be 10 yards."""
        from fantasy_sim.engine.play_resolver import check_penalty
        rng = np.random.default_rng(42)
        rates = make_penalty_rates(
            penalty_rate=1.0,
            type_distribution={"false_start": 0.0, "holding": 1.0, "pass_interference": 0.0, "other": 0.0},
        )
        result = check_penalty(rates, rng)
        assert result is not None
        penalty_type, yards = result
        assert penalty_type == "holding"
        assert yards == 10

    def test_penalty_result_has_is_penalty_flag(self):
        """PlayResult should have is_penalty flag when penalty occurs."""
        from fantasy_sim.engine.play_resolver import apply_penalty
        state = make_state(down=2, distance=10, yard_line=50)
        penalty_type = "false_start"
        penalty_yards = 5
        result = apply_penalty(state, penalty_type, penalty_yards)
        assert result.is_penalty is True
        assert result.yards == -5
        assert result.clock_runoff == 0
```

- [ ] **Step 2: Add is_penalty to PlayResult**

```python
# src/fantasy_sim/engine/types.py — MODIFY PlayResult dataclass
# Add these fields to PlayResult:

@dataclass
class PlayResult:
    """Outcome of a single play."""
    play_type: str          # "pass" | "run"
    yards: int
    is_complete: bool = False
    is_sack: bool = False
    is_interception: bool = False
    is_fumble: bool = False
    is_touchdown: bool = False
    is_safety: bool = False
    is_penalty: bool = False
    clock_runoff: int = 0
    # Player attribution (Phase 3)
    passer_id: str | None = None
    receiver_id: str | None = None
    rusher_id: str | None = None
```

And add `two_point_conversions` to `PlayerBoxScore`:

```python
# src/fantasy_sim/engine/types.py — MODIFY PlayerBoxScore dataclass
# Add this field at the end of PlayerBoxScore, after fumbles_lost:

@dataclass
class PlayerBoxScore:
    """Per-player stats for one game."""
    player_id: str
    name: str
    position: str
    team: str
    # Passing
    pass_attempts: int = 0
    completions: int = 0
    pass_yards: int = 0
    pass_tds: int = 0
    interceptions: int = 0
    sacks: int = 0
    # Rushing
    rush_attempts: int = 0
    rush_yards: int = 0
    rush_tds: int = 0
    # Receiving
    targets: int = 0
    receptions: int = 0
    receiving_yards: int = 0
    receiving_tds: int = 0
    # Misc
    fumbles_lost: int = 0
    two_point_conversions: int = 0
```

- [ ] **Step 3: Implement check_penalty and apply_penalty in play_resolver**

```python
# src/fantasy_sim/engine/play_resolver.py — ADD these functions after the imports

from fantasy_sim.models.distributions import PenaltyRates

def check_penalty(
    penalty_rates: PenaltyRates,
    rng: np.random.Generator,
) -> tuple[str, int] | None:
    """Check if a penalty occurs on this play.

    Returns (penalty_type, yards) or None if no penalty.
    """
    if penalty_rates.penalty_rate <= 0:
        return None

    if rng.random() >= penalty_rates.penalty_rate:
        return None

    # Sample penalty type
    types = list(penalty_rates.type_distribution.keys())
    probs = np.array([penalty_rates.type_distribution[t] for t in types])

    # Handle case where all probs are zero
    if probs.sum() == 0:
        return None

    probs = probs / probs.sum()
    penalty_type = types[rng.choice(len(types), p=probs)]

    yards = int(penalty_rates.avg_yards.get(penalty_type, 5))
    return penalty_type, yards


def apply_penalty(
    state: "GameState",
    penalty_type: str,
    penalty_yards: int,
) -> PlayResult:
    """Create a PlayResult for a penalty. Does NOT mutate state (caller handles that).

    Penalties:
      - false_start: -5 yards, repeat down
      - holding: -10 yards, repeat down
      - pass_interference (defensive): +yards to spot, automatic first down
      - other: -5 yards, repeat down
    """
    if penalty_type == "pass_interference":
        # Defensive PI: offense gets yards, first down
        return PlayResult(
            play_type="pass",
            yards=penalty_yards,
            is_penalty=True,
            clock_runoff=0,
        )
    else:
        # Offensive penalty: lose yards, repeat down
        return PlayResult(
            play_type="pass",
            yards=-penalty_yards,
            is_penalty=True,
            clock_runoff=0,
        )
```

- [ ] **Step 4: Wire penalty into game_sim loop**

```python
# src/fantasy_sim/engine/game_sim.py — MODIFY the simulate_game function
# After the play is resolved and before handling the play outcome,
# add penalty check. The key change is in the while loop:

# ADD import at top of file:
from fantasy_sim.engine.play_resolver import check_penalty, apply_penalty
from fantasy_sim.models.distributions import PenaltyRates

# MODIFY: Add penalty_rates parameter to TeamDistributions usage in simulate_game.
# In the while loop, after resolve_play() and _update_box_scores(), add:

        # --- Penalty check ---
        # Only check if penalty_rates is available in the distributions
        off_penalty_rates = getattr(off_dists, 'penalty_rates', None)
        if off_penalty_rates is not None and result.is_penalty is False:
            penalty = check_penalty(off_penalty_rates, rng)
            if penalty is not None:
                penalty_type, penalty_yards = penalty
                pen_result = apply_penalty(state, penalty_type, penalty_yards)

                if penalty_type == "pass_interference":
                    # Defensive PI: advance ball, first down
                    yards = min(penalty_yards, state.yard_line)
                    state.yard_line -= yards
                    state.down = 1
                    state.distance = min(10, state.yard_line)
                else:
                    # Offensive penalty: move ball back, repeat down
                    state.yard_line = min(99, state.yard_line + penalty_yards)
                    # Keep same down and add penalty yards to distance
                    state.distance = min(state.distance + penalty_yards, 99)

                apply_clock(state, pen_result.clock_runoff)
                check_quarter_end(state, home_dists.drive_start, away_dists.drive_start, rng)
                continue
```

Note: Since `TeamDistributions` does not yet have a `penalty_rates` field, we use `getattr` with a fallback to `None`. This keeps the change backward-compatible. In a later step, `penalty_rates` can be added to `TeamDistributions` when the full pipeline integration is done. For now the penalty logic is self-contained and testable.

- [ ] **Step 5: Run tests and verify**

```bash
uv run pytest tests/test_engine/test_play_resolver.py -v
uv run pytest tests/test_engine/test_game_sim.py -v
```

- [ ] **Step 6: Commit**

```
feat: add penalty modeling to play resolver and game simulation loop

Adds check_penalty() and apply_penalty() to play_resolver.py. Penalties
are sampled per-play using PenaltyRates (false_start=-5, holding=-10,
pass_interference=+yards). PlayResult gains is_penalty flag. The game
simulation loop checks for penalties after each play resolution and
applies yardage adjustments with down/distance handling. PlayerBoxScore
gains two_point_conversions field (wired in Task 6).
```

---

### Task 4: Two-Minute Warning

**Files:**
- Modify: `src/fantasy_sim/engine/clock.py`
- Modify: `tests/test_engine/test_clock.py`

**Gaps covered:** Gap 7 (two-minute warning not implemented)

- [ ] **Step 1: Write failing tests**

```python
# tests/test_engine/test_clock.py — ADD at bottom of file

class TestTwoMinuteWarning:
    def test_clock_stops_at_two_minutes_q2(self):
        """When clock crosses 120s in Q2, it should stop at 120."""
        from fantasy_sim.engine.clock import apply_clock, check_two_minute_warning
        state = make_state(quarter=2, clock=150)
        apply_clock(state, 38)
        # Clock would be 112, but two-minute warning should catch it
        check_two_minute_warning(state)
        assert state.clock == 120

    def test_clock_stops_at_two_minutes_q4(self):
        """When clock crosses 120s in Q4, it should stop at 120."""
        from fantasy_sim.engine.clock import apply_clock, check_two_minute_warning
        state = make_state(quarter=4, clock=155)
        apply_clock(state, 40)
        check_two_minute_warning(state)
        assert state.clock == 120

    def test_no_stop_in_q1(self):
        """Two-minute warning does not apply in Q1."""
        from fantasy_sim.engine.clock import apply_clock, check_two_minute_warning
        state = make_state(quarter=1, clock=150)
        apply_clock(state, 38)
        check_two_minute_warning(state)
        assert state.clock == 112  # No two-minute warning in Q1

    def test_no_stop_in_q3(self):
        """Two-minute warning does not apply in Q3."""
        from fantasy_sim.engine.clock import apply_clock, check_two_minute_warning
        state = make_state(quarter=3, clock=150)
        apply_clock(state, 38)
        check_two_minute_warning(state)
        assert state.clock == 112  # No two-minute warning in Q3

    def test_no_stop_when_already_below_two_minutes(self):
        """If clock is already below 120s, two-minute warning should not fire."""
        from fantasy_sim.engine.clock import apply_clock, check_two_minute_warning
        state = make_state(quarter=2, clock=100)
        apply_clock(state, 30)
        check_two_minute_warning(state)
        assert state.clock == 70  # Already past two-minute warning

    def test_exact_120_no_stop(self):
        """If clock is exactly at 120 after runoff, no adjustment needed."""
        from fantasy_sim.engine.clock import apply_clock, check_two_minute_warning
        state = make_state(quarter=4, clock=158)
        apply_clock(state, 38)
        check_two_minute_warning(state)
        assert state.clock == 120  # Was 120 exactly, stays 120
```

- [ ] **Step 2: Implement two-minute warning**

```python
# src/fantasy_sim/engine/clock.py — ADD this function and modify apply_clock

TWO_MINUTE_MARK = 120  # 2:00 in seconds


def check_two_minute_warning(state: GameState) -> None:
    """If the clock just crossed the two-minute mark in Q2 or Q4, stop it at 120.

    The two-minute warning fires when a play ends with the clock below 2:00
    for the first time in the half. We detect this by checking if the clock
    is below 120 but was above it before the last runoff.

    Call this AFTER apply_clock() on each play.
    """
    if state.quarter not in (2, 4):
        return

    # If clock dropped below 120, snap it back to 120 (two-minute warning stop)
    # This only triggers on the first crossing — once clock is at 120,
    # subsequent plays will reduce it further normally.
    if state.clock < TWO_MINUTE_MARK:
        # Check if we just crossed (the caller should track this).
        # Simplest approach: if clock < 120, set to 120. The game loop will
        # naturally continue from 120 on the next play, and subsequent plays
        # won't trigger this again because apply_clock will reduce below 120
        # and this function won't fire since clock is already < 120 on re-entry.
        # We use a flag approach instead:
        if not getattr(state, '_two_min_warning_fired', False):
            state.clock = TWO_MINUTE_MARK
            state._two_min_warning_fired = True  # type: ignore[attr-defined]
```

Wait -- `GameState` is a dataclass and we should not add ad-hoc attributes. Let us add a proper field.

```python
# src/fantasy_sim/engine/types.py — MODIFY GameState: add _two_min_warning_fired field

@dataclass
class GameState:
    """Mutable game state updated on every play."""
    quarter: int            # 1-4 regulation, 5 = overtime
    clock: int              # seconds remaining in quarter (900 per quarter)
    possession: str         # "home" | "away"
    down: int               # 1-4
    distance: int           # yards to first down
    yard_line: int          # yardline_100: 99=own 1, 50=midfield, 1=opp 1
    home_score: int
    away_score: int
    home_team: str
    away_team: str
    receiving_2nd_half: str  # "home" | "away"
    game_over: bool = False
    two_min_warning_fired: bool = False

    @property
    def score_differential(self) -> int:
        """Score diff from perspective of possessing team (positive = winning)."""
        if self.possession == "home":
            return self.home_score - self.away_score
        return self.away_score - self.home_score

    @property
    def offense(self) -> str:
        return self.possession

    @property
    def defense(self) -> str:
        return "away" if self.possession == "home" else "home"
```

Now the clean implementation:

```python
# src/fantasy_sim/engine/clock.py — FULL REPLACEMENT

import numpy as np
from fantasy_sim.engine.types import GameState
from fantasy_sim.engine.game_flow import perform_kickoff
from fantasy_sim.models.distributions import DriveStartModel

QUARTER_SECONDS = 900
OT_SECONDS = 600
TWO_MINUTE_MARK = 120


def apply_clock(state: GameState, runoff: int) -> None:
    """Subtract clock runoff, clamping to zero."""
    state.clock = max(0, state.clock - runoff)


def check_two_minute_warning(state: GameState) -> None:
    """If the clock just crossed the two-minute mark in Q2 or Q4, stop it at 120.

    Must be called after apply_clock(). Only fires once per half.
    The two_min_warning_fired flag resets at halftime (Q2->Q3 transition).
    """
    if state.quarter not in (2, 4):
        return

    if state.clock < TWO_MINUTE_MARK and not state.two_min_warning_fired:
        state.clock = TWO_MINUTE_MARK
        state.two_min_warning_fired = True


def check_quarter_end(
    state: GameState,
    home_drive_start: DriveStartModel,
    away_drive_start: DriveStartModel,
    rng: np.random.Generator,
) -> None:
    """Check if the quarter has ended and handle transitions."""
    if state.clock > 0:
        return

    if state.quarter == 1:
        # Q1 -> Q2: teams switch ends, same possession continues
        state.quarter = 2
        state.clock = QUARTER_SECONDS

    elif state.quarter == 2:
        # Halftime -> Q3: second-half receiving team gets kickoff
        state.quarter = 3
        state.clock = QUARTER_SECONDS
        state.possession = state.receiving_2nd_half
        state.two_min_warning_fired = False  # Reset for second half
        recv_dists = home_drive_start if state.possession == "home" else away_drive_start
        perform_kickoff(state, recv_dists, rng)

    elif state.quarter == 3:
        # Q3 -> Q4
        state.quarter = 4
        state.clock = QUARTER_SECONDS

    elif state.quarter == 4:
        # End of regulation
        if state.home_score != state.away_score:
            state.game_over = True
        else:
            # Overtime
            state.quarter = 5
            state.clock = OT_SECONDS
            # Coin toss for OT — random team receives
            ot_receiver = "home" if rng.random() < 0.5 else "away"
            state.possession = ot_receiver
            recv_dists = home_drive_start if ot_receiver == "home" else away_drive_start
            perform_kickoff(state, recv_dists, rng)

    elif state.quarter == 5:
        # OT period ended — in regular season, game ends as tie
        state.game_over = True
```

- [ ] **Step 3: Wire check_two_minute_warning into game_sim**

```python
# src/fantasy_sim/engine/game_sim.py — MODIFY imports and game loop
# Change the import line:
from fantasy_sim.engine.clock import apply_clock, check_quarter_end, check_two_minute_warning

# In the while loop, after apply_clock and before check_quarter_end, add:
        # Clock
        apply_clock(state, result.clock_runoff)
        check_two_minute_warning(state)
        check_quarter_end(state, home_dists.drive_start, away_dists.drive_start, rng)
```

Also fix the clock handling for punts and field goals:

```python
        # In the 4th down punt block:
                apply_clock(state, 5)
                check_two_minute_warning(state)
                check_quarter_end(state, home_dists.drive_start, away_dists.drive_start, rng)

        # In the 4th down field_goal block:
                apply_clock(state, 5)
                check_two_minute_warning(state)
                check_quarter_end(state, home_dists.drive_start, away_dists.drive_start, rng)
```

- [ ] **Step 4: Update test helper make_state to include two_min_warning_fired**

```python
# tests/test_engine/test_clock.py — MODIFY make_state function
def make_state(**overrides) -> GameState:
    defaults = dict(
        quarter=1, clock=900, possession="home",
        down=1, distance=10, yard_line=75,
        home_score=0, away_score=0,
        home_team="KC", away_team="BUF",
        receiving_2nd_half="away",
    )
    defaults.update(overrides)
    return GameState(**defaults)
```

Note: `two_min_warning_fired` defaults to `False` in the dataclass so no change needed to `make_state` unless tests need it pre-set.

- [ ] **Step 5: Run tests and verify**

```bash
uv run pytest tests/test_engine/test_clock.py -v
uv run pytest tests/test_engine/test_game_sim.py -v
```

- [ ] **Step 6: Commit**

```
feat: implement two-minute warning clock stop in Q2 and Q4

When apply_clock reduces the clock below 120 seconds in Q2 or Q4, the
new check_two_minute_warning function snaps the clock back to 120 once
per half. GameState gains a two_min_warning_fired flag that resets at
halftime. All clock transitions in game_sim now call
check_two_minute_warning after apply_clock.
```

---

### Task 5: Home-Field Advantage

**Files:**
- Modify: `src/fantasy_sim/engine/play_resolver.py`
- Modify: `src/fantasy_sim/engine/game_sim.py`
- Modify: `tests/test_engine/test_play_resolver.py`

**Gaps covered:** Gap 8 (home-field advantage not modeled)

- [ ] **Step 1: Write failing tests**

```python
# tests/test_engine/test_play_resolver.py — ADD at bottom of file

class TestHomeFieldAdvantage:
    def test_home_field_adds_yards(self):
        """With home-field advantage, the resolve_play function should produce
        slightly higher average yards for the home team over many samples."""
        from fantasy_sim.engine.play_resolver import resolve_play
        rng = np.random.default_rng(42)
        outcomes = make_outcomes(run_yards=[4, 4, 4, 4, 4])
        rates = make_turnover_rates()
        n = 500

        home_yards = []
        away_yards = []
        for _ in range(n):
            state = make_state(possession="home")
            result = resolve_play(state, "run", outcomes, rates, rng, is_home=True)
            if not result.is_fumble and not result.is_safety:
                home_yards.append(result.yards)

            state = make_state(possession="away")
            result = resolve_play(state, "run", outcomes, rates, rng, is_home=False)
            if not result.is_fumble and not result.is_safety:
                away_yards.append(result.yards)

        avg_home = sum(home_yards) / len(home_yards)
        avg_away = sum(away_yards) / len(away_yards)
        # Home should average slightly more (0.5 yards bonus)
        assert avg_home > avg_away

    def test_is_home_false_no_bonus(self):
        """With is_home=False, no yards bonus is applied."""
        rng = np.random.default_rng(42)
        outcomes = make_outcomes(run_yards=[5])
        rates = make_turnover_rates()
        state = make_state()
        result = resolve_play(state, "run", outcomes, rates, rng, is_home=False)
        assert result.yards == 5  # No bonus, exact yards from distribution
```

- [ ] **Step 2: Implement home-field advantage in play_resolver**

```python
# src/fantasy_sim/engine/play_resolver.py — MODIFY resolve_play signature and implementation

# Home field advantage constant
HOME_FIELD_YARDS_BONUS = 0.5  # Average +0.5 yards per play for home team

def resolve_play(
    state: GameState,
    play_type: str,
    play_outcomes: PlayOutcomeDist,
    turnover_rates: TurnoverRates,
    rng: np.random.Generator,
    roster: TeamRoster | None = None,
    is_home: bool = False,
) -> PlayResult:
    if play_type == "pass":
        return _resolve_pass(state, play_outcomes, turnover_rates, rng, roster, is_home)
    if play_type == "run":
        return _resolve_run(state, play_outcomes, turnover_rates, rng, roster, is_home)
    raise ValueError(f"Unexpected play_type: {play_type!r}")


def _apply_home_field(yards: int, is_home: bool, rng: np.random.Generator) -> int:
    """Apply home-field advantage yards bonus.

    Adds a small probabilistic bonus: 50% chance of +1 yard.
    This averages out to +0.5 yards per play for the home team.
    """
    if is_home and rng.random() < HOME_FIELD_YARDS_BONUS:
        return yards + 1
    return yards
```

Then update `_resolve_pass` and `_resolve_run` to accept and use `is_home`:

```python
# In _resolve_pass — add is_home parameter and apply it to yards before clamping:
def _resolve_pass(
    state: GameState,
    play_outcomes: PlayOutcomeDist,
    turnover_rates: TurnoverRates,
    rng: np.random.Generator,
    roster: TeamRoster | None = None,
    is_home: bool = False,
) -> PlayResult:
    # ... (existing code for scramble, sack, interception stays the same)

    # Where yards are computed for completions, apply home-field bonus:
    # In the roster path, after determining yards:
    #   yards = _apply_home_field(yards, is_home, rng)
    # In the legacy path, after computing team_yards:
    #   team_yards = _apply_home_field(team_yards, is_home, rng)
    # ... (rest stays the same)


def _resolve_run(
    state: GameState,
    play_outcomes: PlayOutcomeDist,
    turnover_rates: TurnoverRates,
    rng: np.random.Generator,
    roster: TeamRoster | None = None,
    is_home: bool = False,
) -> PlayResult:
    # ... same pattern: apply _apply_home_field to raw_yards before safety check
```

The full `_resolve_pass` function with home-field applied:

```python
def _resolve_pass(
    state: GameState,
    play_outcomes: PlayOutcomeDist,
    turnover_rates: TurnoverRates,
    rng: np.random.Generator,
    roster: TeamRoster | None = None,
    is_home: bool = False,
) -> PlayResult:
    from fantasy_sim.engine.player_selector import select_passer, select_receiver, select_rusher

    passer_id: str | None = None
    receiver_id: str | None = None

    if roster is not None:
        passer = select_passer(roster)
        passer_id = passer.player_id

        # QB scramble check
        if passer.usage.scramble_rate > 0 and rng.random() < passer.usage.scramble_rate:
            scramble_yards_dist = passer.outcomes.scramble_yards_dist
            if scramble_yards_dist is not None and len(scramble_yards_dist) > 0:
                raw_yards = int(rng.choice(scramble_yards_dist))
            else:
                bucket = bucket_play(
                    state.down, state.distance, state.score_differential,
                    state.quarter, state.yard_line,
                )
                raw_yards = play_outcomes.sample_yards("run", bucket, rng)
            raw_yards = _apply_home_field(raw_yards, is_home, rng)
            is_safety = (state.yard_line - raw_yards) >= 100
            if is_safety:
                yards = -(99 - state.yard_line)
            else:
                yards = _clamp_yards(state.yard_line, raw_yards)
            is_td = (state.yard_line - yards) <= 0
            is_fumble = rng.random() < passer.outcomes.fumble_rate
            return PlayResult(
                play_type="run", yards=yards,
                is_touchdown=is_td and not is_fumble and not is_safety,
                is_fumble=is_fumble and not is_safety,
                is_safety=is_safety,
                rusher_id=passer_id,
                passer_id=passer_id,
                clock_runoff=CLOCK_RUN,
            )

    # Check for sack
    if rng.random() < turnover_rates.sack_rate:
        yards = int(rng.choice(SACK_YARDS))
        is_fumble = rng.random() < turnover_rates.sack_fumble_rate
        new_yl = state.yard_line - yards
        is_safety = new_yl >= 100
        if is_safety:
            yards = -(99 - state.yard_line)
        return PlayResult(
            play_type="pass", yards=yards, is_sack=True,
            is_fumble=is_fumble and not is_safety, is_safety=is_safety,
            clock_runoff=CLOCK_SACK,
            passer_id=passer_id,
        )

    # Check for interception
    if rng.random() < turnover_rates.int_rate:
        return PlayResult(
            play_type="pass", yards=0, is_interception=True,
            clock_runoff=CLOCK_PASS_INCOMPLETE,
            passer_id=passer_id,
        )

    if roster is not None:
        receiver = select_receiver(roster, state, rng)
        receiver_id = receiver.player_id

    bucket = bucket_play(
        state.down, state.distance, state.score_differential,
        state.quarter, state.yard_line,
    )
    team_yards = play_outcomes.sample_yards("pass", bucket, rng)

    if roster is not None and receiver_id is not None:
        is_complete = rng.random() < receiver.outcomes.catch_rate

        if is_complete:
            if receiver.outcomes.receiving_yards_dist is not None and len(receiver.outcomes.receiving_yards_dist) > 0:
                yards = int(rng.choice(receiver.outcomes.receiving_yards_dist))
            else:
                yards = max(team_yards, 1)
            yards = _apply_home_field(yards, is_home, rng)
            yards = _clamp_yards(state.yard_line, yards)
        else:
            yards = 0

        is_td = is_complete and (state.yard_line - yards) <= 0

        is_fumble = False
        if is_complete:
            player_fumble = receiver.outcomes.fumble_rate
            effective_rate = player_fumble if player_fumble > 0 else turnover_rates.fumble_rate
            is_fumble = rng.random() < effective_rate

        return PlayResult(
            play_type="pass", yards=yards,
            is_complete=is_complete,
            is_touchdown=is_td and not is_fumble,
            is_fumble=is_fumble,
            clock_runoff=CLOCK_PASS_COMPLETE if is_complete else CLOCK_PASS_INCOMPLETE,
            passer_id=passer_id,
            receiver_id=receiver_id,
        )

    # Legacy path
    team_yards = _apply_home_field(team_yards, is_home, rng)
    yards = _clamp_yards(state.yard_line, team_yards)

    is_complete = yards > 0
    is_td = (state.yard_line - yards) <= 0

    is_fumble = False
    if is_complete and rng.random() < turnover_rates.fumble_rate:
        is_fumble = True

    return PlayResult(
        play_type="pass", yards=yards,
        is_complete=is_complete,
        is_touchdown=is_td and not is_fumble,
        is_fumble=is_fumble,
        clock_runoff=CLOCK_PASS_COMPLETE if is_complete else CLOCK_PASS_INCOMPLETE,
    )


def _resolve_run(
    state: GameState,
    play_outcomes: PlayOutcomeDist,
    turnover_rates: TurnoverRates,
    rng: np.random.Generator,
    roster: TeamRoster | None = None,
    is_home: bool = False,
) -> PlayResult:
    from fantasy_sim.engine.player_selector import select_rusher

    rusher_id: str | None = None

    if roster is not None:
        rusher = select_rusher(roster, state, rng)
        rusher_id = rusher.player_id

        if rusher.outcomes.rushing_yards_dist is not None and len(rusher.outcomes.rushing_yards_dist) > 0:
            raw_yards = int(rng.choice(rusher.outcomes.rushing_yards_dist))
        else:
            bucket = bucket_play(
                state.down, state.distance, state.score_differential,
                state.quarter, state.yard_line,
            )
            raw_yards = play_outcomes.sample_yards("run", bucket, rng)

        raw_yards = _apply_home_field(raw_yards, is_home, rng)
        is_safety = (state.yard_line - raw_yards) >= 100
        yards = _clamp_yards(state.yard_line, raw_yards)
        is_td = (state.yard_line - yards) <= 0

        player_fumble = rusher.outcomes.fumble_rate
        effective_rate = player_fumble if player_fumble > 0 else turnover_rates.fumble_rate
        is_fumble = rng.random() < effective_rate

        return PlayResult(
            play_type="run", yards=yards,
            is_touchdown=is_td and not is_fumble,
            is_fumble=is_fumble and not is_safety,
            is_safety=is_safety,
            clock_runoff=CLOCK_RUN,
            rusher_id=rusher_id,
        )

    # Legacy path
    bucket = bucket_play(
        state.down, state.distance, state.score_differential,
        state.quarter, state.yard_line,
    )
    raw_yards = play_outcomes.sample_yards("run", bucket, rng)
    raw_yards = _apply_home_field(raw_yards, is_home, rng)

    is_safety = (state.yard_line - raw_yards) >= 100
    yards = _clamp_yards(state.yard_line, raw_yards)
    is_td = (state.yard_line - yards) <= 0
    is_fumble = rng.random() < turnover_rates.fumble_rate

    return PlayResult(
        play_type="run", yards=yards,
        is_touchdown=is_td and not is_fumble,
        is_fumble=is_fumble and not is_safety,
        is_safety=is_safety,
        clock_runoff=CLOCK_RUN,
    )
```

- [ ] **Step 3: Update game_sim to pass is_home**

```python
# src/fantasy_sim/engine/game_sim.py — MODIFY resolve_play call
# In the while loop, change the resolve_play call to:

        is_home_team = (state.possession == "home")
        result = resolve_play(
            state, play_type, off_dists.play_outcomes,
            off_dists.turnover_rates, rng, roster=roster,
            is_home=is_home_team,
        )
```

- [ ] **Step 4: Run tests and verify**

```bash
uv run pytest tests/test_engine/test_play_resolver.py -v
uv run pytest tests/test_engine/test_game_sim.py -v
```

- [ ] **Step 5: Commit**

```
feat: add home-field advantage with probabilistic yards bonus

resolve_play gains is_home parameter. When True, a 50% chance of +1 yard
is applied to each play (averaging +0.5 yards/play for the home team).
The _apply_home_field helper is applied to all yardage calculations in
both pass and run resolution paths. game_sim passes is_home based on
current possession.
```

---

### Task 6: Two-Point Conversion Tracking

**Files:**
- Modify: `src/fantasy_sim/engine/game_flow.py`
- Modify: `src/fantasy_sim/engine/game_sim.py`
- Modify: `src/fantasy_sim/scoring/engine.py`
- Modify: `tests/test_engine/test_game_flow.py`
- Modify: `tests/test_scoring/test_engine.py`

**Gaps covered:** Gap 6 (two-point conversion tracking incomplete)

- [ ] **Step 1: Write failing tests**

```python
# tests/test_engine/test_game_flow.py — ADD at bottom of file

class TestAttemptPatWithAttribution:
    def test_2pt_success_returns_scorer_id(self):
        """attempt_pat should return the player_id of the 2PT scorer when successful."""
        from fantasy_sim.engine.game_flow import attempt_pat
        state = make_state(possession="home", home_score=6)
        rng = np.random.default_rng(42)
        off_box = TeamBoxScore(points=6)
        kicking = make_kicking(xp_rate=1.0)
        # Force 2PT attempt by passing force_two_point=True
        scorer_id = attempt_pat(state, kicking, rng, off_box, td_scorer_id="WR1", force_two_point=True)
        # Either success or failure, but scorer_id should be returned when successful
        if state.home_score == 8:
            assert scorer_id == "WR1"
        else:
            assert scorer_id is None

    def test_xp_returns_none(self):
        """Regular XP should return None (no player attribution)."""
        from fantasy_sim.engine.game_flow import attempt_pat
        state = make_state(possession="home", home_score=6)
        rng = np.random.default_rng(42)
        off_box = TeamBoxScore(points=6)
        kicking = make_kicking(xp_rate=1.0)
        scorer_id = attempt_pat(state, kicking, rng, off_box, td_scorer_id="WR1", force_two_point=False)
        assert scorer_id is None


# tests/test_scoring/test_engine.py — ADD at bottom of file

class TestScorePlayerTwoPoint:
    def test_two_point_conversions_score(self, ppr_config):
        """Two-point conversions should be worth 2 points each."""
        box = PlayerBoxScore("WR1", "WR1", "WR", "KC",
                            receiving_yards=50, receiving_tds=1,
                            two_point_conversions=1)
        points = score_player(box, ppr_config)
        expected = 50 * 0.1 + 1 * 6 + 1 * 2  # 5 + 6 + 2 = 13
        assert points == pytest.approx(expected)

    def test_zero_two_point_no_effect(self, ppr_config):
        """With zero 2PT conversions, score should be unaffected."""
        box = PlayerBoxScore("WR1", "WR1", "WR", "KC",
                            receiving_yards=50, receiving_tds=1,
                            two_point_conversions=0)
        points = score_player(box, ppr_config)
        expected = 50 * 0.1 + 1 * 6  # 5 + 6 = 11
        assert points == pytest.approx(expected)
```

- [ ] **Step 2: Modify attempt_pat to return scorer_id**

```python
# src/fantasy_sim/engine/game_flow.py — MODIFY attempt_pat

def attempt_pat(
    state: GameState,
    kicking: KickingModel,
    rng: np.random.Generator,
    off_box: TeamBoxScore,
    td_scorer_id: str | None = None,
    force_two_point: bool | None = None,
) -> str | None:
    """Attempt PAT (extra point or 2-point conversion) after a touchdown.

    Args:
        td_scorer_id: The player who scored the TD (for 2PT attribution).
        force_two_point: If True, always attempt 2PT. If False, always attempt XP.
                         If None, use random TWO_POINT_ATTEMPT_RATE.

    Returns:
        The player_id who scored the 2PT conversion, or None if XP or failed 2PT.
    """
    if force_two_point is True or (force_two_point is None and rng.random() < TWO_POINT_ATTEMPT_RATE):
        # 2-point attempt
        if rng.random() < TWO_POINT_SUCCESS_RATE:
            score_points(state, 2)
            off_box.points += 2
            return td_scorer_id
        return None
    else:
        # Extra point
        off_box.xp_attempts += 1
        if rng.random() < kicking.xp_rate:
            score_points(state, 1)
            off_box.points += 1
            off_box.xp_made += 1
        return None
```

- [ ] **Step 3: Wire 2PT attribution into game_sim**

```python
# src/fantasy_sim/engine/game_sim.py — MODIFY _handle_touchdown to track scorer

def _handle_touchdown(
    state: GameState,
    off_dists: TeamDistributions,
    off_box: TeamBoxScore,
    recv_drive_start: DriveStartModel,
    rng: np.random.Generator,
    td_scorer_id: str | None = None,
    player_stats: dict[str, PlayerBoxScore] | None = None,
) -> None:
    """Score a TD (6 points), attempt PAT, then kickoff."""
    score_points(state, 6)
    off_box.points += 6
    two_pt_scorer = attempt_pat(state, off_dists.kicking, rng, off_box, td_scorer_id=td_scorer_id)

    # If 2PT was scored, attribute it to the player
    if two_pt_scorer is not None and player_stats is not None and two_pt_scorer in player_stats:
        player_stats[two_pt_scorer].two_point_conversions += 1

    change_possession(state)
    perform_kickoff(state, recv_drive_start, rng)
```

Update the call site in `simulate_game`:

```python
# src/fantasy_sim/engine/game_sim.py — MODIFY the touchdown handling in the while loop

        elif result.is_touchdown:
            # Determine who scored the TD for 2PT attribution
            td_scorer_id = None
            if result.play_type == "pass" and result.receiver_id:
                td_scorer_id = result.receiver_id
            elif result.play_type == "run" and result.rusher_id:
                td_scorer_id = result.rusher_id

            _handle_touchdown(
                state, off_dists, off_box, def_dists.drive_start, rng,
                td_scorer_id=td_scorer_id, player_stats=player_stats,
            )
            # OT walk-off TD
            if state.quarter == 5 and state.home_score != state.away_score:
                state.game_over = True
```

- [ ] **Step 4: Add two_point_conversions to score_player**

```python
# src/fantasy_sim/scoring/engine.py — MODIFY score_player

def score_player(box: PlayerBoxScore, config: dict) -> float:
    """Calculate fantasy points for an offensive player (QB/RB/WR/TE)."""
    points = 0.0
    points += box.pass_yards * config.get("passing_yard", 0)
    points += box.pass_tds * config.get("passing_td", 0)
    points += box.interceptions * config.get("interception", 0)
    points += box.rush_yards * config.get("rushing_yard", 0)
    points += box.rush_tds * config.get("rushing_td", 0)
    points += box.receptions * config.get("reception", 0)
    points += box.receiving_yards * config.get("receiving_yard", 0)
    points += box.receiving_tds * config.get("receiving_td", 0)
    points += box.fumbles_lost * config.get("fumble_lost", 0)
    points += box.two_point_conversions * config.get("two_point", 0)
    return points
```

- [ ] **Step 5: Run tests and verify**

```bash
uv run pytest tests/test_engine/test_game_flow.py -v
uv run pytest tests/test_scoring/test_engine.py -v
uv run pytest tests/test_engine/test_game_sim.py -v
```

- [ ] **Step 6: Commit**

```
feat: add two-point conversion tracking and scoring

attempt_pat now accepts td_scorer_id and returns the scorer's player_id
when a 2PT conversion succeeds. _handle_touchdown passes the TD scorer
through and increments PlayerBoxScore.two_point_conversions. score_player
now includes two_point_conversions * config["two_point"] in fantasy
point calculations. PlayerBoxScore gains the two_point_conversions field.
```

---

### Task 7: Rookie Blend System

**Files:**
- Modify: `src/fantasy_sim/data/player_builder.py`
- Modify: `tests/test_data/test_player_builder.py`

**Gaps covered:** Gap 9 (rookie blend system not implemented)

- [ ] **Step 1: Write failing tests**

```python
# tests/test_data/test_player_builder.py — ADD at bottom of file

from fantasy_sim.data.player_builder import blend_with_archetype
from fantasy_sim.data.rookie_builder import POSITIONAL_ARCHETYPES


class TestRookieBlendSystem:
    def test_full_data_player_no_blend(self):
        """A player with 17 games should have no blending (all real data)."""
        usage = PlayerUsage(target_share=0.25, red_zone_target_share=0.20)
        outcomes = PlayerOutcomes(catch_rate=0.68, fumble_rate=0.005)
        model = PlayerModel(
            player_id="WR1", name="Vet WR", position="WR", team="KC",
            usage=usage, outcomes=outcomes, games_played=17,
        )
        blended = blend_with_archetype(model, rookie_blend_games=4)
        # No blending — values should be unchanged
        assert blended.usage.target_share == pytest.approx(0.25)
        assert blended.outcomes.catch_rate == pytest.approx(0.68)

    def test_zero_games_full_archetype(self):
        """A player with 0 games should be 100% archetype (tier3 fallback)."""
        usage = PlayerUsage(target_share=0.0)
        outcomes = PlayerOutcomes(catch_rate=0.0, fumble_rate=0.0)
        model = PlayerModel(
            player_id="WR1", name="New WR", position="WR", team="KC",
            usage=usage, outcomes=outcomes, games_played=0,
        )
        blended = blend_with_archetype(model, rookie_blend_games=4)
        # Should be fully archetype tier3 values
        arch = POSITIONAL_ARCHETYPES["WR"]["tier3"]
        assert blended.usage.target_share == pytest.approx(arch["target_share"])
        assert blended.outcomes.catch_rate == pytest.approx(arch["catch_rate"])

    def test_partial_blend(self):
        """A player with 2 of 4 blend games should be 50% real, 50% archetype."""
        usage = PlayerUsage(target_share=0.30)
        outcomes = PlayerOutcomes(catch_rate=0.70, fumble_rate=0.01)
        model = PlayerModel(
            player_id="WR1", name="Soph WR", position="WR", team="KC",
            usage=usage, outcomes=outcomes, games_played=2,
        )
        blended = blend_with_archetype(model, rookie_blend_games=4)
        # 50% real (0.30) + 50% archetype tier3 (0.03) = 0.165
        arch = POSITIONAL_ARCHETYPES["WR"]["tier3"]
        expected_ts = 0.5 * 0.30 + 0.5 * arch["target_share"]
        assert blended.usage.target_share == pytest.approx(expected_ts, abs=0.01)

    def test_blend_doesnt_modify_original(self):
        """Blending should return a new model, not modify the original."""
        usage = PlayerUsage(target_share=0.30)
        outcomes = PlayerOutcomes(catch_rate=0.70)
        model = PlayerModel(
            player_id="WR1", name="WR", position="WR", team="KC",
            usage=usage, outcomes=outcomes, games_played=2,
        )
        blended = blend_with_archetype(model, rookie_blend_games=4)
        assert model.usage.target_share == 0.30  # Original unchanged
        assert blended is not model

    def test_qb_blend_includes_scramble_rate(self):
        """QB blending should include scramble_rate from archetype."""
        usage = PlayerUsage(snap_share=0.50, scramble_rate=0.10)
        outcomes = PlayerOutcomes(fumble_rate=0.02)
        model = PlayerModel(
            player_id="QB1", name="Rook QB", position="QB", team="KC",
            usage=usage, outcomes=outcomes, games_played=1,
        )
        blended = blend_with_archetype(model, rookie_blend_games=4)
        # 25% real, 75% archetype
        arch = POSITIONAL_ARCHETYPES["QB"]["tier3"]
        expected_sr = 0.25 * 0.10 + 0.75 * arch["scramble_rate"]
        assert blended.usage.scramble_rate == pytest.approx(expected_sr, abs=0.01)

    def test_rb_blend_includes_carry_share(self):
        """RB blending should include carry_share from archetype."""
        usage = PlayerUsage(carry_share=0.40, target_share=0.06)
        outcomes = PlayerOutcomes(catch_rate=0.60, fumble_rate=0.01)
        model = PlayerModel(
            player_id="RB1", name="Rook RB", position="RB", team="KC",
            usage=usage, outcomes=outcomes, games_played=2,
        )
        blended = blend_with_archetype(model, rookie_blend_games=4)
        arch = POSITIONAL_ARCHETYPES["RB"]["tier3"]
        expected_cs = 0.5 * 0.40 + 0.5 * arch["carry_share"]
        assert blended.usage.carry_share == pytest.approx(expected_cs, abs=0.01)
```

- [ ] **Step 2: Implement blend_with_archetype**

```python
# src/fantasy_sim/data/player_builder.py — ADD this function after the imports

from copy import deepcopy
from fantasy_sim.data.rookie_builder import POSITIONAL_ARCHETYPES


def blend_with_archetype(
    model: PlayerModel,
    rookie_blend_games: int = 4,
    draft_round: int = 7,
) -> PlayerModel:
    """Blend a player's real stats with positional archetype when data is sparse.

    Args:
        model: The player model built from real PBP data.
        rookie_blend_games: Number of games at which real data is fully trusted.
        draft_round: Draft round for archetype tier selection (default tier3).

    Returns:
        A new PlayerModel with blended usage and outcomes.
    """
    if model.games_played >= rookie_blend_games:
        return model

    if model.position not in POSITIONAL_ARCHETYPES:
        return model

    # Determine tier from draft round
    if draft_round <= 2:
        tier = "tier1"
    elif draft_round <= 4:
        tier = "tier2"
    else:
        tier = "tier3"

    archetype = POSITIONAL_ARCHETYPES[model.position][tier]
    real_weight = min(1.0, model.games_played / max(rookie_blend_games, 1))
    arch_weight = 1.0 - real_weight

    blended_model = deepcopy(model)

    # Blend usage rates
    if model.position == "QB":
        blended_model.usage.snap_share = _blend_float(
            model.usage.snap_share, archetype.get("snap_share", 0.0), real_weight, arch_weight,
        )
        blended_model.usage.scramble_rate = _blend_float(
            model.usage.scramble_rate, archetype.get("scramble_rate", 0.0), real_weight, arch_weight,
        )
    elif model.position == "RB":
        blended_model.usage.carry_share = _blend_float(
            model.usage.carry_share, archetype.get("carry_share", 0.0), real_weight, arch_weight,
        )
        blended_model.usage.target_share = _blend_float(
            model.usage.target_share, archetype.get("target_share", 0.0), real_weight, arch_weight,
        )
    elif model.position in ("WR", "TE"):
        blended_model.usage.target_share = _blend_float(
            model.usage.target_share, archetype.get("target_share", 0.0), real_weight, arch_weight,
        )
        blended_model.usage.red_zone_target_share = _blend_float(
            model.usage.red_zone_target_share,
            archetype.get("red_zone_target_share", 0.0),
            real_weight, arch_weight,
        )

    # Blend outcome rates
    blended_model.outcomes.catch_rate = _blend_float(
        model.outcomes.catch_rate, archetype.get("catch_rate", 0.0), real_weight, arch_weight,
    )
    blended_model.outcomes.fumble_rate = _blend_float(
        model.outcomes.fumble_rate, archetype.get("fumble_rate", 0.0), real_weight, arch_weight,
    )

    # Blend yards distributions: if real data is sparse, mix in archetype samples
    if model.position == "QB" and "scramble_yards" in archetype:
        blended_model.outcomes.scramble_yards_dist = _blend_dist(
            model.outcomes.scramble_yards_dist,
            np.array(archetype["scramble_yards"]),
            real_weight, arch_weight,
        )
    if model.position == "RB" and "rush_yards" in archetype:
        blended_model.outcomes.rushing_yards_dist = _blend_dist(
            model.outcomes.rushing_yards_dist,
            np.array(archetype["rush_yards"]),
            real_weight, arch_weight,
        )
    if model.position in ("RB", "WR", "TE") and "rec_yards" in archetype:
        blended_model.outcomes.receiving_yards_dist = _blend_dist(
            model.outcomes.receiving_yards_dist,
            np.array(archetype["rec_yards"]),
            real_weight, arch_weight,
        )

    return blended_model


def _blend_float(real: float, archetype: float, real_weight: float, arch_weight: float) -> float:
    """Blend two float values with given weights."""
    return real * real_weight + archetype * arch_weight


def _blend_dist(
    real_dist: np.ndarray | None,
    archetype_dist: np.ndarray,
    real_weight: float,
    arch_weight: float,
) -> np.ndarray:
    """Blend two yard distributions by concatenating proportional samples.

    If real_dist is None or empty, returns the archetype distribution.
    """
    if real_dist is None or len(real_dist) == 0:
        return archetype_dist.copy()

    # Target size: combined length of both distributions
    target_size = max(len(real_dist) + len(archetype_dist), 10)
    real_count = max(1, int(target_size * real_weight))
    arch_count = max(1, int(target_size * arch_weight))

    # Sample from each proportionally
    rng = np.random.default_rng(0)  # Deterministic for blending
    real_samples = rng.choice(real_dist, size=min(real_count, len(real_dist) * 3), replace=True)
    arch_samples = rng.choice(archetype_dist, size=min(arch_count, len(archetype_dist) * 3), replace=True)

    return np.concatenate([real_samples, arch_samples])
```

- [ ] **Step 3: Wire blend into build_player_models (optional application)**

```python
# src/fantasy_sim/data/player_builder.py — ADD to build_player_models, after building all models
# This is an optional integration point. The caller can also call blend_with_archetype
# directly. For automatic blending, add this at the end of build_player_models:

def build_player_models(
    pbp: pl.DataFrame,
    rosters: pl.DataFrame,
    seasons: list[int],
    rookie_blend_games: int = 0,
) -> dict[str, PlayerModel]:
    """Build PlayerModels from PBP and roster data.

    Args:
        rookie_blend_games: If > 0, players with fewer games get blended with archetype.
                            Set to 0 to disable (default for backward compatibility).
    """
    # ... (existing code up through building models dict)

    # Apply rookie blend if configured
    if rookie_blend_games > 0:
        for pid in list(models.keys()):
            model = models[pid]
            if model.games_played < rookie_blend_games:
                models[pid] = blend_with_archetype(model, rookie_blend_games=rookie_blend_games)

    return models
```

- [ ] **Step 4: Run tests and verify**

```bash
uv run pytest tests/test_data/test_player_builder.py -v
```

- [ ] **Step 5: Commit**

```
feat: implement rookie blend system for sparse player data

When a player has fewer than rookie_blend_games worth of data, their
usage rates and outcome distributions are blended with positional
archetypes. The blend weight is real_weight = games_played /
rookie_blend_games. Usage rates are linearly interpolated, and yards
distributions are combined by concatenating proportional samples.
build_player_models accepts an optional rookie_blend_games parameter
to enable automatic blending.
```

---

## Integration Checklist

After all 7 tasks are complete, run the full test suite to verify nothing is broken:

- [ ] `uv run pytest tests/ -v`
- [ ] `uv run pytest tests/test_data/ -v`
- [ ] `uv run pytest tests/test_engine/ -v`
- [ ] `uv run pytest tests/test_scoring/ -v`

## Summary of Changes by Gap

| Gap | Description | Task | Files Modified |
|-----|-------------|------|----------------|
| 1 | Recency weighting | Task 1 | preprocessor.py, pipeline.py |
| 2 | Red zone metrics | Task 2 | player_builder.py |
| 3 | Air yards share | Task 2 | player.py, player_builder.py |
| 4 | QB scramble data | Task 2 | player_builder.py |
| 5 | Penalty modeling | Task 3 | play_resolver.py, game_sim.py, types.py |
| 6 | 2PT conversion tracking | Task 6 | game_flow.py, game_sim.py, types.py, engine.py |
| 7 | Two-minute warning | Task 4 | clock.py, game_sim.py, types.py |
| 8 | Home-field advantage | Task 5 | play_resolver.py, game_sim.py |
| 9 | Rookie blend system | Task 7 | player_builder.py |
| 10 | Scramble rate from data | Task 2 | player_builder.py |

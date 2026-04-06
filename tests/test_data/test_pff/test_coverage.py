"""Tests for PFF coverage engine — CB profile building."""

import polars as pl
import pytest

from fantasy_sim.data.pff.coverage import (
    CB_ALIGNMENTS,
    CoverageEngine,
    _CbProfile,
)
from fantasy_sim.data.pff.loader import PffLoader
from fantasy_sim.data.pff.models import CoverageConfig


# ---------- Fixtures ----------


@pytest.fixture
def pff_dir(tmp_path):
    """Create a temporary PFF data directory."""
    d = tmp_path / "pff" / "processed" / "nfl"
    d.mkdir(parents=True)
    return d


@pytest.fixture
def loader(pff_dir):
    """PffLoader pointed at temp directory."""
    return PffLoader(pff_dir)


@pytest.fixture
def default_config():
    """CoverageConfig with defaults."""
    return CoverageConfig()


# ---------- Parquet helpers ----------


def _write_coverage_matchup(pff_dir, season, type1_rows, type2_rows):
    """Write defense_coverage_matchup parquet with both row types.

    type1_rows: list of dicts with player_id, position, team, week, game_id,
        player, franchise_id, season (auto-filled), etc.
    type2_rows: list of dicts with player_id (receiver), coverage_player_id
        (defender), week, game_id, targets, receptions, yards,
        grades_coverage_defense, grades_overall, season (auto-filled).
    """
    all_rows = []
    for r in type1_rows:
        row = {
            "player_id": r["player_id"],
            "player": r.get("player", f"Player_{r['player_id']}"),
            "team": r.get("team"),
            "franchise_id": r.get("franchise_id", r.get("team")),
            "position": r.get("position"),
            "season": season,
            "week": r.get("week", 1),
            "game_id": r.get("game_id", 9000 + r.get("week", 1)),
            "coverage_player_id": None,
            "targets": r.get("targets", 0),
            "receptions": r.get("receptions", 0),
            "yards": r.get("yards", 0.0),
            "grades_coverage_defense": r.get("grades_coverage_defense"),
            "grades_overall": r.get("grades_overall"),
        }
        all_rows.append(row)

    for r in type2_rows:
        row = {
            "player_id": r["player_id"],
            "player": None,
            "team": None,
            "franchise_id": None,
            "position": None,
            "season": season,
            "week": r.get("week", 1),
            "game_id": r.get("game_id", 9000 + r.get("week", 1)),
            "coverage_player_id": r["coverage_player_id"],
            "targets": r.get("targets", 0),
            "receptions": r.get("receptions", 0),
            "yards": r.get("yards", 0.0),
            "grades_coverage_defense": r.get("grades_coverage_defense"),
            "grades_overall": r.get("grades_overall"),
        }
        all_rows.append(row)

    schema = {
        "player_id": pl.Int64,
        "player": pl.Utf8,
        "team": pl.Utf8,
        "franchise_id": pl.Utf8,
        "position": pl.Utf8,
        "season": pl.Int64,
        "week": pl.Int64,
        "game_id": pl.Int64,
        "coverage_player_id": pl.Int64,
        "targets": pl.Int64,
        "receptions": pl.Int64,
        "yards": pl.Float64,
        "grades_coverage_defense": pl.Float64,
        "grades_overall": pl.Float64,
    }
    if all_rows:
        df = pl.DataFrame(all_rows, schema=schema, infer_schema_length=None)
    else:
        df = pl.DataFrame(schema=schema)
    path = pff_dir / f"defense_coverage_matchup_{season}.parquet"
    df.write_parquet(path)
    return path


# ---------- TestBuildCbProfiles ----------


class TestBuildCbProfiles:
    """Tests for CoverageEngine._build_cb_profiles."""

    def test_identifies_starting_cbs_by_alignment(self, pff_dir, loader, default_config):
        """Two LCBs on BUF, one with more targets (starter).

        Verify correct starter is identified and stats are aggregated correctly.
        """
        # Type 1: Two LCBs on BUF across 3 weeks
        # CB 101 appears in 3 games, CB 102 appears in 2 games
        type1_rows = []
        for week in [1, 2, 3]:
            type1_rows.append({
                "player_id": 101,
                "player": "CB_Starter",
                "team": "BUF",
                "position": "LCB",
                "week": week,
                "game_id": 9000 + week,
            })
        for week in [1, 2]:
            type1_rows.append({
                "player_id": 102,
                "player": "CB_Backup",
                "team": "BUF",
                "position": "LCB",
                "week": week,
                "game_id": 9000 + week,
            })
        # Also add an RCB so we can verify alignment isolation
        for week in [1, 2, 3]:
            type1_rows.append({
                "player_id": 201,
                "player": "CB_Right",
                "team": "BUF",
                "position": "RCB",
                "week": week,
                "game_id": 9000 + week,
            })

        # Type 2: Matchup rows — CB 101 gets 30 total targets, CB 102 gets 10
        type2_rows = []
        # CB 101: 3 games, 10 targets each = 30 total
        for week in [1, 2, 3]:
            type2_rows.append({
                "player_id": 500,  # receiver
                "coverage_player_id": 101,
                "week": week,
                "game_id": 9000 + week,
                "targets": 10,
                "receptions": 6,
                "yards": 80.0,
                "grades_coverage_defense": 70.0,
                "grades_overall": 65.0,
            })
        # CB 102: 2 games, 5 targets each = 10 total
        for week in [1, 2]:
            type2_rows.append({
                "player_id": 501,  # different receiver
                "coverage_player_id": 102,
                "week": week,
                "game_id": 9000 + week,
                "targets": 5,
                "receptions": 3,
                "yards": 40.0,
                "grades_coverage_defense": 60.0,
                "grades_overall": 55.0,
            })
        # RCB 201: 3 games, 8 targets each = 24 total
        for week in [1, 2, 3]:
            type2_rows.append({
                "player_id": 502,
                "coverage_player_id": 201,
                "week": week,
                "game_id": 9000 + week,
                "targets": 8,
                "receptions": 5,
                "yards": 60.0,
                "grades_coverage_defense": 75.0,
                "grades_overall": 70.0,
            })

        _write_coverage_matchup(pff_dir, 2024, type1_rows, type2_rows)

        engine = CoverageEngine(loader, default_config)
        profiles = engine._build_cb_profiles("BUF", 2024, max_week=10)

        # Should have LCB and RCB starters
        assert "LCB" in profiles
        assert "RCB" in profiles

        # LCB starter should be CB 101 (30 targets > CB 102's 10)
        lcb = profiles["LCB"]
        assert lcb.player_id == 101
        assert lcb.team == "BUF"
        assert lcb.alignment == "LCB"
        assert lcb.total_targets == 30
        assert lcb.games_played == 3
        # catch_rate = 18 receptions / 30 targets = 0.6
        assert lcb.catch_rate_allowed == pytest.approx(18 / 30, abs=0.01)
        # ypr = 240 yards / 18 receptions
        assert lcb.ypr_allowed == pytest.approx(240 / 18, abs=0.1)
        # coverage_grade = target-weighted: all same grade 70.0
        assert lcb.coverage_grade == pytest.approx(70.0, abs=0.1)

        # RCB starter should be CB 201
        rcb = profiles["RCB"]
        assert rcb.player_id == 201
        assert rcb.total_targets == 24
        assert rcb.games_played == 3

    def test_rolling_window_filters_future_weeks(self, pff_dir, loader, default_config):
        """Data across weeks 1-8, max_week=5 should only use weeks 1-4."""
        type1_rows = []
        type2_rows = []

        # CB on KC across weeks 1-8
        for week in range(1, 9):
            type1_rows.append({
                "player_id": 301,
                "player": "CB_KC",
                "team": "KC",
                "position": "LCB",
                "week": week,
                "game_id": 9000 + week,
            })
            # Matchup rows: 5 targets per week
            type2_rows.append({
                "player_id": 600,
                "coverage_player_id": 301,
                "week": week,
                "game_id": 9000 + week,
                "targets": 5,
                "receptions": 3,
                "yards": 40.0,
                "grades_coverage_defense": 65.0,
                "grades_overall": 60.0,
            })

        _write_coverage_matchup(pff_dir, 2024, type1_rows, type2_rows)

        engine = CoverageEngine(loader, default_config)
        profiles = engine._build_cb_profiles("KC", 2024, max_week=5)

        # Should only see weeks 1-4 (week < 5)
        assert "LCB" in profiles
        lcb = profiles["LCB"]
        assert lcb.total_targets == 20  # 4 weeks * 5 targets
        assert lcb.games_played == 4
        assert lcb.catch_rate_allowed == pytest.approx(12 / 20, abs=0.01)

    def test_empty_data_returns_empty_profiles(self, pff_dir, loader, default_config):
        """No data returns empty dict."""
        # Write an empty parquet (no type1 rows for the team)
        _write_coverage_matchup(pff_dir, 2024, [], [])

        engine = CoverageEngine(loader, default_config)
        profiles = engine._build_cb_profiles("BUF", 2024, max_week=10)

        assert profiles == {}

    def test_grades_overall_fallback(self, pff_dir, loader, default_config):
        """When grades_coverage_defense is null, falls back to grades_overall."""
        type1_rows = [
            {
                "player_id": 401,
                "player": "CB_Fallback",
                "team": "SF",
                "position": "LCB",
                "week": 1,
                "game_id": 9001,
            },
        ]
        type2_rows = [
            {
                "player_id": 700,
                "coverage_player_id": 401,
                "week": 1,
                "game_id": 9001,
                "targets": 8,
                "receptions": 5,
                "yards": 60.0,
                "grades_coverage_defense": None,
                "grades_overall": 72.0,
            },
        ]

        _write_coverage_matchup(pff_dir, 2024, type1_rows, type2_rows)

        engine = CoverageEngine(loader, default_config)
        profiles = engine._build_cb_profiles("SF", 2024, max_week=10)

        assert "LCB" in profiles
        # Should use grades_overall as fallback
        assert profiles["LCB"].coverage_grade == pytest.approx(72.0, abs=0.1)


class TestWrAlignment:
    """Tests for CoverageEngine._determine_wr_alignments."""

    def test_determines_wr_alignment_from_matchup_data(self, pff_dir, loader, default_config):
        """WR with 4 RWR rows and 2 SLWR rows should resolve to RWR (plurality)."""
        # Type 1 rows for PFF player_id=500 on KC
        type1_rows = []
        for week, position in enumerate(["RWR", "RWR", "RWR", "RWR", "SLWR", "SLWR"], start=1):
            type1_rows.append({
                "player_id": 500,
                "player": "WR_Plurality",
                "team": "KC",
                "position": position,
                "week": week,
                "game_id": 9000 + week,
            })

        _write_coverage_matchup(pff_dir, 2024, type1_rows, [])

        engine = CoverageEngine(loader, default_config)
        alignments = engine._determine_wr_alignments(
            wr_player_ids=["wr_1"],
            offense_team="KC",
            target_season=2024,
            max_week=7,
            pff_player_id_map={"wr_1": 500},
        )

        assert alignments["wr_1"] == "RWR"

    def test_fallback_by_target_share_rank(self, pff_dir, loader, default_config):
        """WRs with no PFF data fall back to index-based alignment."""
        # Write empty parquet — no WR rows at all
        _write_coverage_matchup(pff_dir, 2024, [], [])

        engine = CoverageEngine(loader, default_config)
        alignments = engine._determine_wr_alignments(
            wr_player_ids=["wr_1", "wr_2", "wr_3"],
            offense_team="KC",
            target_season=2024,
            max_week=7,
            pff_player_id_map={},
        )

        # WR1 and WR2 should be outside alignments, WR3 should be slot
        outside = {"RWR", "LWR"}
        slot = {"SLWR", "SRWR"}
        assert alignments["wr_1"] in outside
        assert alignments["wr_2"] in outside
        assert alignments["wr_3"] in slot

    def test_alignment_to_cb_mapping(self):
        """_ALIGNMENT_MAP correctly maps WR alignments to CB alignments."""
        from fantasy_sim.data.pff.coverage import _ALIGNMENT_MAP

        assert _ALIGNMENT_MAP["RWR"] == "LCB"
        assert _ALIGNMENT_MAP["LWR"] == "RCB"
        assert _ALIGNMENT_MAP["SLWR"] == "SCB"
        assert _ALIGNMENT_MAP["SRWR"] == "SCB"


class TestModifierComputation:
    """Tests for _compute_modifiers function."""

    # Standard 8-CB population used across most tests
    _POPULATION = [
        _CbProfile(200, "BUF", "LCB", 0.50, 9.0, 82.0, 60, 8),   # strong
        _CbProfile(300, "MIA", "LCB", 0.62, 11.0, 68.0, 55, 8),   # average
        _CbProfile(400, "NE",  "LCB", 0.65, 12.0, 60.0, 50, 8),   # average
        _CbProfile(500, "NYJ", "LCB", 0.70, 14.0, 55.0, 45, 8),   # weak
        _CbProfile(600, "DAL", "LCB", 0.64, 11.5, 65.0, 50, 8),
        _CbProfile(700, "PHI", "LCB", 0.58, 10.0, 72.0, 55, 8),
        _CbProfile(800, "WAS", "LCB", 0.68, 13.0, 58.0, 48, 8),
        _CbProfile(900, "NYG", "LCB", 0.60, 10.5, 70.0, 52, 8),
    ]

    def test_strong_cb_produces_negative_modifier(self, default_config):
        """Strong CB (low catch_rate_allowed, high grade) → modifiers < 1.0."""
        from fantasy_sim.data.pff.coverage import _compute_modifiers

        strong_cb = _CbProfile(200, "BUF", "LCB", 0.50, 9.0, 82.0, 60, 8)
        result = _compute_modifiers(strong_cb, self._POPULATION, default_config)

        assert result.catch_rate_modifier < 1.0
        assert result.ypr_modifier < 1.0

    def test_weak_cb_produces_positive_modifier(self, default_config):
        """Weak CB (high catch_rate_allowed, low grade) → modifiers > 1.0."""
        from fantasy_sim.data.pff.coverage import _compute_modifiers

        weak_cb = _CbProfile(500, "NYJ", "LCB", 0.70, 14.0, 55.0, 45, 8)
        result = _compute_modifiers(weak_cb, self._POPULATION, default_config)

        assert result.catch_rate_modifier > 1.0
        assert result.ypr_modifier > 1.0

    def test_modifiers_clamped_to_range(self, default_config):
        """Extreme CB with very high sensitivity should be clamped at factor_clamp bounds."""
        from fantasy_sim.data.pff.coverage import _compute_modifiers

        # Very high sensitivity so unclamped modifier would exceed bounds
        config = CoverageConfig(
            catch_rate_sensitivity=0.20,
            ypr_sensitivity=0.20,
            factor_clamp=(0.95, 1.05),
            min_coverage_targets=20,
            min_z_score_targets=10,
            min_z_score_population=8,
        )

        # Extreme strong CB (far below population mean)
        extreme_cb = _CbProfile(200, "BUF", "LCB", 0.30, 7.0, 95.0, 60, 8)
        result = _compute_modifiers(extreme_cb, self._POPULATION, config)

        lo, hi = config.factor_clamp
        assert result.catch_rate_modifier == pytest.approx(lo, abs=1e-9)
        assert result.ypr_modifier == pytest.approx(lo, abs=1e-9)

    def test_reliability_ramp_blends_outcome_and_grade(self, default_config):
        """Low target count → grade pulls modifier, outcome z ≈ 0 but grade is strong."""
        from fantasy_sim.data.pff.coverage import _compute_modifiers

        # min_coverage_targets=20, CB has only 10 → reliability = 0.5
        config = CoverageConfig(
            catch_rate_sensitivity=0.04,
            ypr_sensitivity=0.04,
            min_coverage_targets=20,
            min_z_score_targets=10,
            min_z_score_population=8,
            factor_clamp=(0.95, 1.05),
        )

        # CB with average outcomes (z ≈ 0) but strong grade (high → negative grade_z)
        # Population mean catch_rate ≈ 0.622, mean grade ≈ 66.25
        # Outcomes are right at the mean so outcome z ≈ 0
        # Grade is 82 (above mean) → grade_z < 0 → blended_z < 0 → modifier < 1.0
        low_target_cb = _CbProfile(200, "BUF", "LCB", 0.622, 11.0, 82.0, 10, 8)
        result = _compute_modifiers(low_target_cb, self._POPULATION, config)

        assert result.catch_rate_modifier < 1.0

    def test_small_population_returns_neutral(self, default_config):
        """Fewer than min_z_score_population CBs → neutral modifiers (1.0, 1.0)."""
        from fantasy_sim.data.pff.coverage import _compute_modifiers

        small_pop = [
            _CbProfile(200, "BUF", "LCB", 0.50, 9.0, 82.0, 60, 8),
            _CbProfile(300, "MIA", "LCB", 0.62, 11.0, 68.0, 55, 8),
        ]
        cb = _CbProfile(200, "BUF", "LCB", 0.50, 9.0, 82.0, 60, 8)
        result = _compute_modifiers(cb, small_pop, default_config)

        assert result.catch_rate_modifier == pytest.approx(1.0)
        assert result.ypr_modifier == pytest.approx(1.0)


class TestCoverageEngineCompute:
    """Tests for CoverageEngine.compute() full orchestration."""

    # ---------- helper ----------

    @staticmethod
    def _setup_league_data(pff_dir, season):
        """Write a parquet with league-wide CB data (8+ per alignment) and KC WRs.

        BUF CBs: strong LCB (pid=200, catch_rate ~0.33), average RCB (pid=202),
                  weak SCB (pid=203, catch_rate ~0.75).
        7 other teams with average CBs at all 3 alignments.
        KC WR Type 1 rows: pid=500 as RWR, pid=501 as LWR, pid=502 as SLWR.
        """
        type1_rows = []
        type2_rows = []

        # --- BUF CBs ---
        buf_cbs = [
            # (pid, alignment, targets_per_week, recs_per_week, ypr, grade)
            (200, "LCB", 8, 2, 8.0, 88.0),   # strong: 2/8 = 0.25 catch rate
            (202, "RCB", 8, 5, 11.0, 65.0),   # average: 5/8 = 0.625
            (203, "SCB", 8, 7, 14.0, 45.0),   # weak: 7/8 = 0.875 catch rate
        ]
        for pid, align, tgt, rec, ypr, grade in buf_cbs:
            for week in range(1, 7):
                type1_rows.append({
                    "player_id": pid,
                    "player": f"BUF_{align}_{pid}",
                    "team": "BUF",
                    "position": align,
                    "week": week,
                    "game_id": 1000 + week,
                })
                yards = round(ypr * rec, 1) if rec > 0 else 0.0
                type2_rows.append({
                    "player_id": 900 + week,  # dummy receiver
                    "coverage_player_id": pid,
                    "week": week,
                    "game_id": 1000 + week,
                    "targets": tgt,
                    "receptions": rec,
                    "yards": yards,
                    "grades_coverage_defense": grade,
                    "grades_overall": grade - 5.0,
                })

        # --- 7 other teams with average CBs at all 3 alignments ---
        other_teams = ["MIA", "NE", "NYJ", "DAL", "PHI", "WAS", "NYG"]
        avg_cbs = [
            # (alignment, targets, recs, ypr, grade)
            ("LCB", 8, 5, 11.0, 65.0),
            ("RCB", 8, 5, 11.0, 65.0),
            ("SCB", 8, 5, 11.0, 65.0),
        ]
        pid_counter = 1000
        for team in other_teams:
            for align, tgt, rec, ypr, grade in avg_cbs:
                pid_counter += 1
                pid = pid_counter
                for week in range(1, 7):
                    type1_rows.append({
                        "player_id": pid,
                        "player": f"{team}_{align}_{pid}",
                        "team": team,
                        "position": align,
                        "week": week,
                        "game_id": 2000 + pid_counter * 10 + week,
                    })
                    yards = round(ypr * rec, 1) if rec > 0 else 0.0
                    type2_rows.append({
                        "player_id": 900 + week,
                        "coverage_player_id": pid,
                        "week": week,
                        "game_id": 2000 + pid_counter * 10 + week,
                        "targets": tgt,
                        "receptions": rec,
                        "yards": yards,
                        "grades_coverage_defense": grade,
                        "grades_overall": grade - 5.0,
                    })

        # --- KC WRs (Type 1 only, for alignment resolution) ---
        kc_wrs = [
            (500, "RWR"),
            (501, "LWR"),
            (502, "SLWR"),
        ]
        for pid, align in kc_wrs:
            for week in range(1, 7):
                type1_rows.append({
                    "player_id": pid,
                    "player": f"KC_WR_{pid}",
                    "team": "KC",
                    "position": align,
                    "week": week,
                    "game_id": 3000 + week,
                })

        _write_coverage_matchup(pff_dir, season, type1_rows, type2_rows)

    def test_compute_returns_per_wr_modifiers(self, pff_dir, loader):
        """compute() returns per-WR modifiers based on CB matchups.

        wr_1 (RWR) faces BUF LCB (strong) -> catch_rate_modifier < 1.0
        wr_3 (SLWR) faces BUF SCB (weak) -> catch_rate_modifier > 1.0
        """
        from fantasy_sim.models.player import (
            PlayerModel,
            PlayerOutcomes,
            PlayerUsage,
            TeamRoster,
        )

        self._setup_league_data(pff_dir, 2024)

        # Build KC roster with 3 WRs
        wrs = []
        for pid, name, ts in [
            ("wr_1", "WR_One", 0.30),
            ("wr_2", "WR_Two", 0.25),
            ("wr_3", "WR_Three", 0.15),
        ]:
            wrs.append(PlayerModel(
                player_id=pid,
                name=name,
                position="WR",
                team="KC",
                usage=PlayerUsage(target_share=ts),
                outcomes=PlayerOutcomes(catch_rate=0.65),
            ))
        roster = TeamRoster(team="KC", players=wrs)

        # PFF crosswalk: pff_id -> nfl_id
        pff_crosswalk = {500: "wr_1", 501: "wr_2", 502: "wr_3"}

        config = CoverageConfig(
            enabled=True,
            min_z_score_population=8,
            min_z_score_targets=10,
            min_coverage_targets=20,
        )
        engine = CoverageEngine(loader, config)
        result = engine.compute(
            defense_team="BUF",
            offense_roster=roster,
            target_season=2024,
            max_week=7,
            pff_crosswalk=pff_crosswalk,
        )

        # wr_1 (RWR) faces BUF LCB (strong, catch_rate ~0.33) -> modifier < 1.0
        assert "wr_1" in result
        assert result["wr_1"].catch_rate_modifier < 1.0

        # wr_3 (SLWR) faces BUF SCB (weak, catch_rate ~0.75) -> modifier > 1.0
        assert "wr_3" in result
        assert result["wr_3"].catch_rate_modifier > 1.0

    def test_compute_disabled_returns_empty(self, pff_dir, loader):
        """compute() with enabled=False returns empty dict."""
        config = CoverageConfig(enabled=False)
        engine = CoverageEngine(loader, config)
        result = engine.compute(
            defense_team="BUF",
            offense_roster=None,
            target_season=2024,
            max_week=7,
        )
        assert result == {}

    def test_compute_no_season_returns_empty(self, pff_dir, loader):
        """compute() with target_season=None returns empty dict."""
        config = CoverageConfig(enabled=True)
        engine = CoverageEngine(loader, config)
        result = engine.compute(
            defense_team="BUF",
            offense_roster=None,
            target_season=None,
            max_week=None,
        )
        assert result == {}


class TestEarlySeasonBlend:
    """Tests for CoverageEngine early-season blending in _build_cb_profiles."""

    def test_blends_with_previous_season_when_few_games(self, pff_dir, loader):
        """When current season has < min_games, blend with previous season."""
        # 2023 parquet: CB 200 (LCB, BUF) with 9 games, catch_rate_allowed = 2/5 = 0.40
        type1_rows_2023 = []
        type2_rows_2023 = []
        for week in range(1, 10):  # 9 weeks
            type1_rows_2023.append({
                "player_id": 200,
                "player": "CB_Vet",
                "team": "BUF",
                "position": "LCB",
                "week": week,
                "game_id": 8000 + week,
            })
            type2_rows_2023.append({
                "player_id": 600,
                "coverage_player_id": 200,
                "week": week,
                "game_id": 8000 + week,
                "targets": 5,
                "receptions": 2,  # 18/45 = 0.40 catch_rate_allowed
                "yards": 20.0,
                "grades_coverage_defense": 70.0,
                "grades_overall": 65.0,
            })
        _write_coverage_matchup(pff_dir, 2023, type1_rows_2023, type2_rows_2023)

        # 2024 parquet: CB 200 (LCB, BUF) with 2 games, catch_rate_allowed = 4/5 = 0.80
        type1_rows_2024 = []
        type2_rows_2024 = []
        for week in range(1, 3):  # 2 weeks
            type1_rows_2024.append({
                "player_id": 200,
                "player": "CB_Vet",
                "team": "BUF",
                "position": "LCB",
                "week": week,
                "game_id": 9000 + week,
            })
            type2_rows_2024.append({
                "player_id": 600,
                "coverage_player_id": 200,
                "week": week,
                "game_id": 9000 + week,
                "targets": 5,
                "receptions": 4,  # 8/10 = 0.80 catch_rate_allowed
                "yards": 40.0,
                "grades_coverage_defense": 75.0,
                "grades_overall": 70.0,
            })
        _write_coverage_matchup(pff_dir, 2024, type1_rows_2024, type2_rows_2024)

        # Config: min_games=4
        config = CoverageConfig(min_games=4)
        engine = CoverageEngine(loader, config)
        # max_week=3 so only weeks 1-2 are visible (week < 3) → 2 games
        profiles = engine._build_cb_profiles("BUF", target_season=2024, max_week=3)

        # blend_weight = 2 / 4 = 0.5
        # blended = 0.5 * 0.80 + 0.5 * 0.40 = 0.60
        assert "LCB" in profiles
        lcb = profiles["LCB"]
        assert lcb.catch_rate_allowed == pytest.approx(0.60, abs=0.01)

    def test_no_blend_when_enough_games(self, pff_dir, loader):
        """When current season has >= min_games, use current season only."""
        # 2023 parquet: CB 200 (LCB, BUF) with 9 games, catch_rate_allowed = 0.40
        type1_rows_2023 = []
        type2_rows_2023 = []
        for week in range(1, 10):
            type1_rows_2023.append({
                "player_id": 200,
                "player": "CB_Vet",
                "team": "BUF",
                "position": "LCB",
                "week": week,
                "game_id": 8000 + week,
            })
            type2_rows_2023.append({
                "player_id": 600,
                "coverage_player_id": 200,
                "week": week,
                "game_id": 8000 + week,
                "targets": 5,
                "receptions": 2,
                "yards": 20.0,
                "grades_coverage_defense": 70.0,
                "grades_overall": 65.0,
            })
        _write_coverage_matchup(pff_dir, 2023, type1_rows_2023, type2_rows_2023)

        # 2024 parquet: CB 200 (LCB, BUF) with 6 games, catch_rate_allowed = 0.80
        type1_rows_2024 = []
        type2_rows_2024 = []
        for week in range(1, 7):  # 6 weeks
            type1_rows_2024.append({
                "player_id": 200,
                "player": "CB_Vet",
                "team": "BUF",
                "position": "LCB",
                "week": week,
                "game_id": 9000 + week,
            })
            type2_rows_2024.append({
                "player_id": 600,
                "coverage_player_id": 200,
                "week": week,
                "game_id": 9000 + week,
                "targets": 5,
                "receptions": 4,
                "yards": 40.0,
                "grades_coverage_defense": 75.0,
                "grades_overall": 70.0,
            })
        _write_coverage_matchup(pff_dir, 2024, type1_rows_2024, type2_rows_2024)

        # Config: min_games=4; current season has 6 games >= 4
        config = CoverageConfig(min_games=4)
        engine = CoverageEngine(loader, config)
        # max_week=10 so all 6 weeks are visible
        profiles = engine._build_cb_profiles("BUF", target_season=2024, max_week=10)

        # Should use current season only: catch_rate_allowed = 0.80
        assert "LCB" in profiles
        lcb = profiles["LCB"]
        assert lcb.catch_rate_allowed == pytest.approx(0.80, abs=0.01)

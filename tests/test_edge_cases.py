"""Comprehensive edge case tests covering Gaps 30-31.

Covers: empty rosters, invalid override values, unknown player/team overrides,
scoring config edge cases, empty projections, CLI validation,
redistribution preservation, and legacy simulation mode (no roster).
"""

import numpy as np
import pytest
from click.testing import CliRunner
from fantasy_sim.engine.types import (
    TeamDistributions, TeamBoxScore, GameState, PlayerBoxScore, PlayResult,
)
from fantasy_sim.engine.game_sim import simulate_game
from fantasy_sim.engine.player_selector import select_receiver, select_rusher, select_passer
from fantasy_sim.engine.play_resolver import resolve_play
from fantasy_sim.models.distributions import (
    PlayCallingDist, PlayOutcomeDist, TurnoverRates, KickingModel, DriveStartModel,
)
from fantasy_sim.models.player import (
    PlayerModel, PlayerUsage, PlayerOutcomes, TeamRoster,
)
from fantasy_sim.overrides.engine import (
    apply_player_override, apply_team_override,
    PLAYER_USAGE_FIELDS, PLAYER_OUTCOME_FIELDS, PLAYER_META_FIELDS,
)
from fantasy_sim.overrides.resolver import PlayerResolver
from fantasy_sim.scoring.engine import score_player, score_dst, score_kicker
from fantasy_sim.scoring.projections import (
    build_player_projections, build_dst_projections, build_kicker_projections,
)
from fantasy_sim.config.loader import resolve_scoring, ConfigError
from fantasy_sim.cli import main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_dists(team: str) -> TeamDistributions:
    """Create TeamDistributions with all fields including pace_factor."""
    return TeamDistributions(
        play_calling=PlayCallingDist(
            team=team,
            distributions={},
            default={"pass": 0.57, "run": 0.43},
        ),
        play_outcomes=PlayOutcomeDist(
            distributions={},
            defaults={
                "pass": np.array([0, 5, 7, 10, 12, 15, 20]),
                "run": np.array([-2, 0, 1, 2, 3, 4, 5, 6, 7]),
            },
        ),
        turnover_rates=TurnoverRates(
            team=team, int_rate=0.025, fumble_rate=0.012,
            sack_rate=0.065, sack_fumble_rate=0.10,
        ),
        kicking=KickingModel(
            fg_make_rate={"0_39": 0.93, "40_49": 0.82, "50_plus": 0.65},
            xp_rate=0.94,
        ),
        drive_start=DriveStartModel(
            touchback_rate=0.55,
            touchback_yardline=75,
            return_yardlines=np.array([72, 74, 76, 78, 80]),
        ),
        pace_factor=1.0,
    )


def make_minimal_roster(team: str) -> TeamRoster:
    """Create TeamRoster with QB, WR1, RB1 with basic usage/outcomes."""
    return TeamRoster(team=team, players=[
        PlayerModel(
            f"{team}_QB", "QB1", "QB", team,
            PlayerUsage(snap_share=1.0, scramble_rate=0.06),
            PlayerOutcomes(scramble_yards_dist=np.array([2, 4, 6, 8])),
        ),
        PlayerModel(
            f"{team}_WR1", "WR1", "WR", team,
            PlayerUsage(target_share=0.28),
            PlayerOutcomes(
                catch_rate=0.65,
                receiving_yards_dist=np.array([5, 8, 10, 15, 20]),
            ),
        ),
        PlayerModel(
            f"{team}_RB1", "RB1", "RB", team,
            PlayerUsage(carry_share=0.65, target_share=0.10),
            PlayerOutcomes(
                rushing_yards_dist=np.array([-1, 0, 2, 3, 4, 5, 7]),
                catch_rate=0.70,
                receiving_yards_dist=np.array([3, 5, 7]),
                fumble_rate=0.008,
            ),
        ),
    ])


# ---------------------------------------------------------------------------
# 1. TestEmptyRosterEdgeCases (Gap 31)
# ---------------------------------------------------------------------------

class TestEmptyRosterEdgeCases:
    """Edge cases around rosters with too few position players."""

    def test_roster_with_only_qb_crashes_on_run_play(self):
        """QB-only roster crashes on run plays — no eligible rushers.

        Documents actual behavior: even with scramble_rate=1.0, that only
        applies to pass plays. When the play caller selects a run,
        select_rusher is called directly and raises ValueError.
        """
        home_dists = make_dists("HOME")
        away_dists = make_dists("AWAY")

        qb_only = TeamRoster(team="HOME", players=[
            PlayerModel(
                "HOME_QB", "QB1", "QB", "HOME",
                PlayerUsage(snap_share=1.0, scramble_rate=1.0),
                PlayerOutcomes(scramble_yards_dist=np.array([2, 4, 6, 8, 12])),
            ),
        ])
        away_roster = make_minimal_roster("AWAY")

        rng = np.random.default_rng(42)
        # The 43% run rate will eventually select a run play, which raises
        with pytest.raises(ValueError, match="No eligible rushers"):
            simulate_game(
                home_dists, away_dists, rng,
                home_roster=qb_only, away_roster=away_roster,
            )

    def test_select_receiver_no_eligible_raises(self):
        """QB-only roster raises ValueError when selecting a receiver."""
        qb_only = TeamRoster(team="TST", players=[
            PlayerModel(
                "TST_QB", "QB1", "QB", "TST",
                PlayerUsage(snap_share=1.0),
                PlayerOutcomes(),
            ),
        ])
        state = GameState(
            quarter=1, clock=900, possession="home",
            down=1, distance=10, yard_line=75,
            home_score=0, away_score=0,
            home_team="TST", away_team="OPP",
            receiving_2nd_half="away",
        )
        rng = np.random.default_rng(42)
        with pytest.raises(ValueError, match="No eligible receivers"):
            select_receiver(qb_only, state, rng)

    def test_select_rusher_no_eligible_raises(self):
        """QB+WR only roster raises ValueError when selecting a rusher."""
        no_rbs = TeamRoster(team="TST", players=[
            PlayerModel(
                "TST_QB", "QB1", "QB", "TST",
                PlayerUsage(snap_share=1.0),
                PlayerOutcomes(),
            ),
            PlayerModel(
                "TST_WR1", "WR1", "WR", "TST",
                PlayerUsage(target_share=0.30),
                PlayerOutcomes(catch_rate=0.65),
            ),
        ])
        state = GameState(
            quarter=1, clock=900, possession="home",
            down=1, distance=10, yard_line=75,
            home_score=0, away_score=0,
            home_team="TST", away_team="OPP",
            receiving_2nd_half="away",
        )
        rng = np.random.default_rng(42)
        with pytest.raises(ValueError, match="No eligible rushers"):
            select_rusher(no_rbs, state, rng)


# ---------------------------------------------------------------------------
# 2. TestInvalidOverrideValues (Gap 31)
# ---------------------------------------------------------------------------

class TestInvalidOverrideValues:
    """Override validation edge cases — documents current behavior."""

    def test_negative_carry_share_accepted(self):
        """Documents current behavior: negative carry_share is accepted (no validation)."""
        roster = make_minimal_roster("TST")
        # Should not raise — no per-field validation on player usage
        apply_player_override(roster, "TST_RB1", {"carry_share": -0.5})
        rb = next(p for p in roster.players if p.player_id == "TST_RB1")
        assert rb.usage.carry_share == -0.5

    def test_target_share_over_one_accepted(self):
        """Documents current behavior: target_share > 1.0 accepted."""
        roster = make_minimal_roster("TST")
        apply_player_override(roster, "TST_WR1", {"target_share": 1.5})
        wr = next(p for p in roster.players if p.player_id == "TST_WR1")
        assert wr.usage.target_share == 1.5

    def test_pass_rate_out_of_range_raises(self):
        """pass_rate > 1.0 raises ValueError."""
        dists = make_dists("TST")
        with pytest.raises(ValueError, match="pass_rate must be between"):
            apply_team_override(dists, {"pass_rate": 1.5})

    def test_pass_rate_negative_raises(self):
        """pass_rate < 0.0 raises ValueError."""
        dists = make_dists("TST")
        with pytest.raises(ValueError, match="pass_rate must be between"):
            apply_team_override(dists, {"pass_rate": -0.1})

    def test_unknown_team_override_raises(self):
        """Nonexistent team override field raises ValueError."""
        dists = make_dists("TST")
        with pytest.raises(ValueError, match="Unknown team override field"):
            apply_team_override(dists, {"nonexistent_field": 0.5})

    def test_unknown_player_override_raises(self):
        """Nonexistent player override field raises ValueError."""
        roster = make_minimal_roster("TST")
        with pytest.raises(ValueError, match="Unknown override field"):
            apply_player_override(roster, "TST_QB", {"fake_field": 0.5})


# ---------------------------------------------------------------------------
# 3. TestOverrideForUnknownPlayer (Gap 31)
# ---------------------------------------------------------------------------

class TestOverrideForUnknownPlayer:
    """Overriding a player not on the roster."""

    def test_player_not_on_roster_raises(self):
        """KeyError when overriding a player not on the roster."""
        roster = make_minimal_roster("TST")
        with pytest.raises(KeyError, match="not found"):
            apply_player_override(roster, "GHOST_PLAYER", {"carry_share": 0.5})


# ---------------------------------------------------------------------------
# 4. TestPlayerResolverEdgeCases (Gap 31)
# ---------------------------------------------------------------------------

class TestPlayerResolverEdgeCases:
    """Edge cases for PlayerResolver name matching."""

    def test_empty_rosters(self):
        """Empty rosters list raises KeyError on any resolve."""
        resolver = PlayerResolver([])
        with pytest.raises(KeyError):
            resolver.resolve("anyone")

    def test_single_player_roster(self):
        """Single-player roster resolves by ID and name."""
        roster = TeamRoster(team="TST", players=[
            PlayerModel(
                "TST_QB1", "Patrick Mahomes", "QB", "TST",
                PlayerUsage(snap_share=1.0),
                PlayerOutcomes(),
            ),
        ])
        resolver = PlayerResolver([roster])
        assert resolver.resolve("TST_QB1") == "TST_QB1"
        assert resolver.resolve("Patrick Mahomes") == "TST_QB1"

    def test_empty_query_raises(self):
        """Empty string query raises KeyError."""
        roster = make_minimal_roster("TST")
        resolver = PlayerResolver([roster])
        with pytest.raises(KeyError):
            resolver.resolve("")


# ---------------------------------------------------------------------------
# 5. TestScoringConfigEdgeCases (Gap 31)
# ---------------------------------------------------------------------------

class TestScoringConfigEdgeCases:
    """Scoring engine behavior with unusual configs."""

    def test_score_player_with_empty_config(self):
        """Empty scoring config returns 0.0 fantasy points."""
        box = PlayerBoxScore(
            player_id="QB1", name="QB1", position="QB", team="TST",
            pass_yards=300, pass_tds=3, rush_yards=20,
        )
        assert score_player(box, {}) == 0.0

    def test_score_dst_with_empty_config(self):
        """Empty scoring config returns 0.0 DST points."""
        box = TeamBoxScore(sacks_made=4, interceptions_caught=2)
        assert score_dst(box, 14, {}) == 0.0

    def test_score_kicker_with_empty_config(self):
        """Empty scoring config returns 0.0 kicker points."""
        box = TeamBoxScore(fg_made_0_39=2, fg_made_40_49=1, xp_made=3)
        assert score_kicker(box, {}) == 0.0

    def test_score_player_with_partial_config(self):
        """Only configured keys contribute to score."""
        box = PlayerBoxScore(
            player_id="QB1", name="QB1", position="QB", team="TST",
            pass_yards=300, pass_tds=3, rush_yards=50, rush_tds=1,
        )
        # Only passing_td configured
        config = {"passing_td": 4}
        pts = score_player(box, config)
        assert pts == 3 * 4  # 12 points, only from pass TDs

    def test_resolve_scoring_unknown_format_raises(self):
        """Unknown scoring format raises ConfigError."""
        presets = {"ppr": {"reception": 1.0, "passing_td": 4}}
        with pytest.raises(ConfigError, match="Unknown scoring format"):
            resolve_scoring(presets, "nonexistent_format")

    def test_resolve_scoring_circular_inherit_raises(self):
        """Circular _inherit chain raises ConfigError."""
        presets = {
            "a": {"_inherit": "b", "reception": 1.0},
            "b": {"_inherit": "a", "reception": 0.5},
        }
        with pytest.raises(ConfigError, match="Circular"):
            resolve_scoring(presets, "a")


# ---------------------------------------------------------------------------
# 6. TestProjectionEdgeCases (Gap 30)
# ---------------------------------------------------------------------------

class TestProjectionEdgeCases:
    """Projection builders with empty inputs."""

    def test_build_player_projections_empty_games(self):
        """Empty games list returns empty projections."""
        assert build_player_projections([], {}) == []

    def test_build_dst_projections_empty_games(self):
        """Empty games list returns empty DST projections."""
        assert build_dst_projections([], {}) == []

    def test_build_kicker_projections_empty_games(self):
        """Empty games list returns empty kicker projections."""
        assert build_kicker_projections([], {}) == []


# ---------------------------------------------------------------------------
# 7. TestSimulationWithoutRoster (Gap 30)
# ---------------------------------------------------------------------------

class TestSimulationWithoutRoster:
    """Legacy mode: simulate_game without rosters."""

    def test_simulate_game_without_rosters(self):
        """Game completes with no player_stats when rosters are omitted."""
        home_dists = make_dists("HOME")
        away_dists = make_dists("AWAY")
        rng = np.random.default_rng(42)

        result = simulate_game(home_dists, away_dists, rng)

        assert result.total_plays > 0
        assert isinstance(result.home_score, int)
        assert isinstance(result.away_score, int)
        assert result.player_stats == {}


# ---------------------------------------------------------------------------
# 8. TestCLIEdgeCases (Gap 31)
# ---------------------------------------------------------------------------

class TestCLIEdgeCases:
    """CLI validation with invalid inputs."""

    def test_demo_with_zero_sims(self):
        """Zero sims should be rejected (IntRange min=1)."""
        runner = CliRunner()
        result = runner.invoke(main, ["demo", "--sims", "0"])
        assert result.exit_code != 0

    def test_demo_with_invalid_scoring(self):
        """Invalid scoring format rejected by Click Choice."""
        runner = CliRunner()
        result = runner.invoke(main, ["demo", "--scoring", "superflex"])
        assert result.exit_code != 0

    def test_demo_with_invalid_format(self):
        """Invalid output format rejected by Click Choice."""
        runner = CliRunner()
        result = runner.invoke(main, ["demo", "--format", "xml"])
        assert result.exit_code != 0

    def test_demo_with_malformed_override(self):
        """Override without '=' should fail."""
        runner = CliRunner()
        result = runner.invoke(main, ["demo", "--sims", "1", "--override", "namevalue"])
        assert result.exit_code != 0

    def test_demo_with_override_missing_dot(self):
        """Override key without '.' should fail."""
        runner = CliRunner()
        result = runner.invoke(main, ["demo", "--sims", "1", "--override", "name=0.5"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# 9. TestRedistributionFullValidation (Gap 30)
# ---------------------------------------------------------------------------

class TestRedistributionFullValidation:
    """Verify share redistribution preserves totals and avoids negatives."""

    def test_target_share_redistribution_preserves_total(self):
        """Total target share is preserved after overriding one player."""
        roster = TeamRoster(team="TST", players=[
            PlayerModel(
                "TST_WR1", "WR1", "WR", "TST",
                PlayerUsage(target_share=0.25),
                PlayerOutcomes(catch_rate=0.65),
            ),
            PlayerModel(
                "TST_WR2", "WR2", "WR", "TST",
                PlayerUsage(target_share=0.20),
                PlayerOutcomes(catch_rate=0.60),
            ),
            PlayerModel(
                "TST_RB1", "RB1", "RB", "TST",
                PlayerUsage(carry_share=0.60, target_share=0.10),
                PlayerOutcomes(
                    rushing_yards_dist=np.array([2, 3, 4]),
                    catch_rate=0.70,
                ),
            ),
        ])
        total_before = sum(p.usage.target_share for p in roster.players)

        apply_player_override(roster, "TST_WR1", {"target_share": 0.35})

        total_after = sum(p.usage.target_share for p in roster.players)
        assert abs(total_before - total_after) < 1e-9

    def test_carry_share_redistribution_preserves_total(self):
        """Total carry share is preserved after overriding one player."""
        roster = TeamRoster(team="TST", players=[
            PlayerModel(
                "TST_RB1", "RB1", "RB", "TST",
                PlayerUsage(carry_share=0.55),
                PlayerOutcomes(rushing_yards_dist=np.array([2, 3, 4])),
            ),
            PlayerModel(
                "TST_RB2", "RB2", "RB", "TST",
                PlayerUsage(carry_share=0.30),
                PlayerOutcomes(rushing_yards_dist=np.array([1, 2, 3])),
            ),
            PlayerModel(
                "TST_QB", "QB1", "QB", "TST",
                PlayerUsage(snap_share=1.0, carry_share=0.05),
                PlayerOutcomes(scramble_yards_dist=np.array([2, 4])),
            ),
        ])
        total_before = sum(p.usage.carry_share for p in roster.players)

        apply_player_override(roster, "TST_RB1", {"carry_share": 0.70})

        total_after = sum(p.usage.carry_share for p in roster.players)
        assert abs(total_before - total_after) < 1e-9

    def test_shares_never_go_negative(self):
        """All shares remain >= 0 even after an extreme override."""
        roster = TeamRoster(team="TST", players=[
            PlayerModel(
                "TST_WR1", "WR1", "WR", "TST",
                PlayerUsage(target_share=0.25),
                PlayerOutcomes(catch_rate=0.65),
            ),
            PlayerModel(
                "TST_WR2", "WR2", "WR", "TST",
                PlayerUsage(target_share=0.20),
                PlayerOutcomes(catch_rate=0.60),
            ),
            PlayerModel(
                "TST_TE", "TE1", "TE", "TST",
                PlayerUsage(target_share=0.15),
                PlayerOutcomes(catch_rate=0.67),
            ),
        ])

        # Extreme: give one player 0.90 target share
        apply_player_override(roster, "TST_WR1", {"target_share": 0.90})

        for p in roster.players:
            assert p.usage.target_share >= 0.0, (
                f"{p.player_id} has negative target_share: {p.usage.target_share}"
            )

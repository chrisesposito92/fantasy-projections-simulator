from __future__ import annotations

from types import SimpleNamespace

import pytest

from fantasy_sim.data.game_script import (
    GameScriptDiagnostics,
    GameScriptProfile,
    RbRankFactors,
    TargetRankFactors,
)
from fantasy_sim.validation.game_script import (
    collect_game_script_profiles,
    format_game_script_summary,
)
from fantasy_sim.validation.parallel import GameSpec


def _make_profile(
    team: str,
    *,
    trail_pass: float,
    trail_pass_ratio: float,
    trail_pace: float = 1.0,
    trail_pace_ratio: float = 1.0,
    rank1: float = 1.0,
    rank1_ratio: float = 1.0,
    rank2: float = 1.0,
    rank2_ratio: float = 1.0,
    rank3_plus: float = 1.0,
    rank3_plus_ratio: float = 1.0,
    trail_sample: int = 0,
    trail_play_count: int = 0,
    rb1: float = 1.0,
    rb1_ratio: float = 1.0,
    rb2: float = 1.0,
    rb2_ratio: float = 1.0,
    rb3_plus: float = 1.0,
    rb3_plus_ratio: float = 1.0,
    lead_sample: int = 0,
    lead_play_count: int = 0,
) -> GameScriptProfile:
    return GameScriptProfile(
        team=team,
        trailing_late_pass_rate_factor=trail_pass,
        trailing_late_pace_factor=trail_pace,
        trailing_late_target_factors=TargetRankFactors(
            rank1=rank1,
            rank2=rank2,
            rank3_plus=rank3_plus,
        ),
        leading_late_rb_factors=RbRankFactors(
            rb1=rb1,
            rb2=rb2,
            rb3_plus=rb3_plus,
        ),
        diagnostics=GameScriptDiagnostics(
            trailing_late_target_sample=trail_sample,
            leading_late_rb_sample=lead_sample,
            trailing_late_play_count=trail_play_count,
            leading_late_rb_play_count=lead_play_count,
            trailing_late_pass_rate_ratio=trail_pass_ratio,
            trailing_late_pace_ratio=trail_pace_ratio,
            trailing_late_rank1_ratio=rank1_ratio,
            trailing_late_rank2_ratio=rank2_ratio,
            trailing_late_rank3_plus_ratio=rank3_plus_ratio,
            leading_late_rb1_ratio=rb1_ratio,
            leading_late_rb2_ratio=rb2_ratio,
            leading_late_rb3_plus_ratio=rb3_plus_ratio,
        ),
    )


def _make_spec(
    game_id: str,
    *,
    week: int = 1,
    home_profile: GameScriptProfile | None,
    away_profile: GameScriptProfile | None,
) -> GameSpec:
    return GameSpec(
        game_id=game_id,
        home_dists=SimpleNamespace(game_script_profile=home_profile),
        away_dists=SimpleNamespace(game_script_profile=away_profile),
        home_roster=None,
        away_roster=None,
        seed=1,
        week=week,
    )


def test_collect_game_script_profiles_aggregates_per_team_across_specs():
    specs = [
        _make_spec(
            "game-1",
            week=1,
            home_profile=_make_profile(
                "KC",
                trail_pass=1.10,
                trail_pass_ratio=1.20,
                trail_pace=1.04,
                trail_pace_ratio=1.08,
                rank1=1.01,
                rank1_ratio=1.03,
                rank2=0.96,
                rank2_ratio=0.98,
                rank3_plus=0.90,
                rank3_plus_ratio=0.94,
                trail_sample=80,
                trail_play_count=100,
                rb1=1.16,
                rb1_ratio=1.18,
                rb2=0.97,
                rb2_ratio=0.95,
                rb3_plus=0.84,
                rb3_plus_ratio=0.82,
                lead_sample=40,
                lead_play_count=55,
            ),
            away_profile=_make_profile(
                "BUF",
                trail_pass=1.03,
                trail_pass_ratio=1.05,
                trail_sample=20,
                trail_play_count=24,
                lead_sample=11,
                lead_play_count=15,
            ),
        ),
        _make_spec(
            "game-2",
            week=2,
            home_profile=_make_profile(
                "KC",
                trail_pass=1.14,
                trail_pass_ratio=1.16,
                trail_pace=1.08,
                trail_pace_ratio=1.10,
                rank1=1.05,
                rank1_ratio=0.99,
                rank2=0.98,
                rank2_ratio=1.00,
                rank3_plus=0.94,
                rank3_plus_ratio=0.96,
                trail_sample=70,
                trail_play_count=90,
                rb1=1.20,
                rb1_ratio=1.24,
                rb2=0.93,
                rb2_ratio=0.91,
                rb3_plus=0.82,
                rb3_plus_ratio=0.78,
                lead_sample=30,
                lead_play_count=45,
            ),
            away_profile=None,
        ),
    ]

    profiles = collect_game_script_profiles(specs)

    assert set(profiles) == {"BUF", "KC"}

    kc = profiles["KC"]
    assert kc.trailing_late_pass_rate_factor == pytest.approx(1.12)
    assert kc.trailing_late_pace_factor == pytest.approx(1.06)
    assert kc.trailing_late_target_factors.rank1 == pytest.approx(1.03)
    assert kc.trailing_late_target_factors.rank2 == pytest.approx(0.97)
    assert kc.trailing_late_target_factors.rank3_plus == pytest.approx(0.92)
    assert kc.leading_late_rb_factors.rb1 == pytest.approx(1.18)
    assert kc.leading_late_rb_factors.rb2 == pytest.approx(0.95)
    assert kc.leading_late_rb_factors.rb3_plus == pytest.approx(0.83)
    assert kc.diagnostics.trailing_late_target_sample == 70
    assert kc.diagnostics.trailing_late_play_count == 90
    assert kc.diagnostics.leading_late_rb_sample == 30
    assert kc.diagnostics.leading_late_rb_play_count == 45
    assert kc.diagnostics.trailing_late_pass_rate_ratio == pytest.approx(1.18)
    assert kc.diagnostics.trailing_late_pace_ratio == pytest.approx(1.09)
    assert kc.diagnostics.trailing_late_rank1_ratio == pytest.approx(1.01)
    assert kc.diagnostics.trailing_late_rank2_ratio == pytest.approx(0.99)
    assert kc.diagnostics.trailing_late_rank3_plus_ratio == pytest.approx(0.95)
    assert kc.diagnostics.leading_late_rb1_ratio == pytest.approx(1.21)
    assert kc.diagnostics.leading_late_rb2_ratio == pytest.approx(0.93)
    assert kc.diagnostics.leading_late_rb3_plus_ratio == pytest.approx(0.80)


def test_format_game_script_summary_renders_multiple_teams_sorted_with_counts():
    profiles = {
        "KC": _make_profile(
            "KC",
            trail_pass=1.12,
            trail_pass_ratio=1.18,
            trail_pace=1.06,
            trail_pace_ratio=1.09,
            rank1=1.04,
            rank1_ratio=1.01,
            rank2=0.97,
            rank2_ratio=0.98,
            rank3_plus=0.92,
            rank3_plus_ratio=0.94,
            trail_sample=150,
            trail_play_count=190,
            rb1=1.18,
            rb1_ratio=1.21,
            rb2=0.95,
            rb2_ratio=0.93,
            rb3_plus=0.83,
            rb3_plus_ratio=0.80,
            lead_sample=70,
            lead_play_count=100,
        ),
        "BUF": _make_profile(
            "BUF",
            trail_pass=1.03,
            trail_pass_ratio=1.05,
            trail_pace=1.01,
            trail_pace_ratio=1.02,
            trail_sample=20,
            trail_play_count=24,
            lead_sample=11,
            lead_play_count=15,
        ),
    }

    summary = format_game_script_summary(profiles)

    assert "TrailPass" in summary
    assert "LeadN" in summary
    assert "1.12/1.18" in summary
    assert "150/190" in summary
    assert "11/15" in summary
    assert summary.index("BUF") < summary.index("KC")

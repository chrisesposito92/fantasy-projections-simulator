from fantasy_sim.data.game_script import (
    GameScriptDiagnostics,
    GameScriptProfile,
    RbRankFactors,
    TargetRankFactors,
)
from fantasy_sim.validation.game_script import format_game_script_summary


def test_format_game_script_summary_renders_profile_factors_and_headers():
    profiles = {
        "KC": GameScriptProfile(
            team="KC",
            trailing_late_pass_rate_factor=1.12,
            trailing_late_pace_factor=1.06,
            trailing_late_target_factors=TargetRankFactors(
                rank1=1.04,
                rank2=0.97,
                rank3_plus=0.92,
            ),
            leading_late_rb_factors=RbRankFactors(
                rb1=1.18,
                rb2=0.95,
                rb3_plus=0.83,
            ),
            diagnostics=GameScriptDiagnostics(
                trailing_late_target_sample=87,
                leading_late_rb_sample=44,
                trailing_late_play_count=102,
                leading_late_rb_play_count=58,
                trailing_late_pass_rate_ratio=1.18,
                trailing_late_pace_ratio=1.09,
                trailing_late_rank1_ratio=1.01,
                trailing_late_rank2_ratio=0.98,
                trailing_late_rank3_plus_ratio=0.94,
                leading_late_rb1_ratio=1.21,
                leading_late_rb2_ratio=0.93,
                leading_late_rb3_plus_ratio=0.80,
            ),
        )
    }

    summary = format_game_script_summary(profiles)

    assert "KC" in summary
    assert "TrailPass" in summary
    assert "LeadN" in summary
    assert "1.12/1.18" in summary

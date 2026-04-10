"""Validation helpers for learned game-script profiles."""

from __future__ import annotations

from dataclasses import fields

from rich.console import Console
from rich.table import Table

from fantasy_sim.data.game_script import (
    GameScriptDiagnostics,
    GameScriptProfile,
    RbRankFactors,
    TargetRankFactors,
)
from fantasy_sim.validation.parallel import GameSpec

_DIAGNOSTIC_COUNT_FIELDS = {
    "trailing_late_pass_rate_sample",
    "trailing_late_pace_sample",
    "trailing_late_target_sample",
    "leading_late_rb_sample",
    "trailing_late_play_count",
    "leading_late_rb_play_count",
}


def collect_game_script_profiles(specs: list[GameSpec]) -> dict[str, GameScriptProfile]:
    """Collect season-level learned game-script profiles keyed by team."""
    grouped_profiles: dict[str, list[GameScriptProfile]] = {}
    for spec in specs:
        for distributions in (spec.home_dists, spec.away_dists):
            profile = distributions.game_script_profile
            if profile is not None:
                grouped_profiles.setdefault(profile.team, []).append(profile)

    return {
        team: _aggregate_team_profiles(team_profiles)
        for team, team_profiles in grouped_profiles.items()
    }


def _average(values: list[float]) -> float:
    return sum(values) / len(values)


def _sum_diagnostic_fields(team_profiles: list[GameScriptProfile], field_name: str) -> int:
    return sum(getattr(profile.diagnostics, field_name) for profile in team_profiles)


def _average_diagnostic_fields(team_profiles: list[GameScriptProfile], field_name: str) -> float:
    return _average([getattr(profile.diagnostics, field_name) for profile in team_profiles])


def _aggregate_team_profiles(team_profiles: list[GameScriptProfile]) -> GameScriptProfile:
    first_profile = team_profiles[0]
    diagnostics = GameScriptDiagnostics(**{
        field.name: (
            _sum_diagnostic_fields(team_profiles, field.name)
            if field.name in _DIAGNOSTIC_COUNT_FIELDS
            else _average_diagnostic_fields(team_profiles, field.name)
        )
        for field in fields(GameScriptDiagnostics)
    })

    return GameScriptProfile(
        team=first_profile.team,
        trailing_late_pass_rate_factor=_average(
            [profile.trailing_late_pass_rate_factor for profile in team_profiles]
        ),
        trailing_late_pace_factor=_average(
            [profile.trailing_late_pace_factor for profile in team_profiles]
        ),
        trailing_late_target_factors=TargetRankFactors(
            rank1=_average([profile.trailing_late_target_factors.rank1 for profile in team_profiles]),
            rank2=_average([profile.trailing_late_target_factors.rank2 for profile in team_profiles]),
            rank3_plus=_average(
                [profile.trailing_late_target_factors.rank3_plus for profile in team_profiles]
            ),
        ),
        leading_late_rb_factors=RbRankFactors(
            rb1=_average([profile.leading_late_rb_factors.rb1 for profile in team_profiles]),
            rb2=_average([profile.leading_late_rb_factors.rb2 for profile in team_profiles]),
            rb3_plus=_average(
                [profile.leading_late_rb_factors.rb3_plus for profile in team_profiles]
            ),
        ),
        diagnostics=diagnostics,
    )


def _format_ratio_pair(factor: float, ratio: float) -> str:
    return f"{factor:.2f}/{ratio:.2f}"


def _format_count_pair(sample: int, play_count: int) -> str:
    return f"{sample}/{play_count}"


def format_game_script_summary(profiles: dict[str, GameScriptProfile]) -> str:
    """Render learned game-script profiles as a Rich table."""
    console = Console(
        width=180,
        force_terminal=False,
        no_color=True,
        _environ={"COLUMNS": "180", "LINES": "40"},
    )

    with console.capture() as capture:
        table = Table(title="Game Script Summary")
        table.add_column("Team", style="cyan", no_wrap=True)
        table.add_column("TrailPass", justify="right", no_wrap=True)
        table.add_column("TrailPace", justify="right", no_wrap=True)
        table.add_column("Rank1", justify="right", no_wrap=True)
        table.add_column("Rank2", justify="right", no_wrap=True)
        table.add_column("Rank3+", justify="right", no_wrap=True)
        table.add_column("TrailN", justify="right", no_wrap=True)
        table.add_column("RB1", justify="right", no_wrap=True)
        table.add_column("RB2", justify="right", no_wrap=True)
        table.add_column("RB3+", justify="right", no_wrap=True)
        table.add_column("LeadN", justify="right", no_wrap=True)

        for team in sorted(profiles):
            profile = profiles[team]
            diagnostics = profile.diagnostics
            table.add_row(
                profile.team,
                _format_ratio_pair(
                    profile.trailing_late_pass_rate_factor,
                    diagnostics.trailing_late_pass_rate_ratio,
                ),
                _format_ratio_pair(
                    profile.trailing_late_pace_factor,
                    diagnostics.trailing_late_pace_ratio,
                ),
                _format_ratio_pair(
                    profile.trailing_late_target_factors.rank1,
                    diagnostics.trailing_late_rank1_ratio,
                ),
                _format_ratio_pair(
                    profile.trailing_late_target_factors.rank2,
                    diagnostics.trailing_late_rank2_ratio,
                ),
                _format_ratio_pair(
                    profile.trailing_late_target_factors.rank3_plus,
                    diagnostics.trailing_late_rank3_plus_ratio,
                ),
                _format_count_pair(
                    diagnostics.trailing_late_target_sample,
                    diagnostics.trailing_late_play_count,
                ),
                _format_ratio_pair(
                    profile.leading_late_rb_factors.rb1,
                    diagnostics.leading_late_rb1_ratio,
                ),
                _format_ratio_pair(
                    profile.leading_late_rb_factors.rb2,
                    diagnostics.leading_late_rb2_ratio,
                ),
                _format_ratio_pair(
                    profile.leading_late_rb_factors.rb3_plus,
                    diagnostics.leading_late_rb3_plus_ratio,
                ),
                _format_count_pair(
                    diagnostics.leading_late_rb_sample,
                    diagnostics.leading_late_rb_play_count,
                ),
            )

        console.print(table)

    return capture.get()

"""Validation helpers for learned game-script profiles."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from fantasy_sim.data.game_script import GameScriptProfile
from fantasy_sim.validation.parallel import GameSpec


def collect_game_script_profiles(specs: list[GameSpec]) -> dict[str, GameScriptProfile]:
    """Collect learned game-script profiles keyed by team."""
    profiles: dict[str, GameScriptProfile] = {}
    for spec in specs:
        for distributions in (spec.home_dists, spec.away_dists):
            profile = distributions.game_script_profile
            if profile is not None:
                profiles[profile.team] = profile
    return profiles


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

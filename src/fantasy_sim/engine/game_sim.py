from __future__ import annotations

import numpy as np
from fantasy_sim.engine.game_script import effective_pace_factor, resolve_game_script
from fantasy_sim.engine.types import GameState, GameResult, TeamBoxScore, TeamDistributions, PlayResult, PlayerBoxScore
from fantasy_sim.engine.play_caller import select_play_type, fourth_down_decision
from fantasy_sim.engine.play_resolver import resolve_play, check_penalty
from fantasy_sim.engine.game_flow import (
    apply_yards, change_possession, score_points,
    handle_turnover, perform_kickoff, perform_punt,
    attempt_field_goal, attempt_pat,
)
from fantasy_sim.engine.clock import apply_clock, check_quarter_end, check_two_minute_warning
from fantasy_sim.models.distributions import DriveStartModel

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from fantasy_sim.models.player import TeamRoster

MAX_PLAYS = 400
INT_RETURN_TD_RATE = 0.20   # ~20% of INTs returned for TD
FUMBLE_RETURN_TD_RATE = 0.10  # ~10% of fumble recoveries returned for TD


def simulate_game(
    home_dists: TeamDistributions,
    away_dists: TeamDistributions,
    rng: np.random.Generator,
    home_roster: TeamRoster | None = None,
    away_roster: TeamRoster | None = None,
    week: int = 0,
) -> GameResult:
    """Simulate a complete NFL game play-by-play."""
    player_stats: dict[str, PlayerBoxScore] = {}
    state = GameState(
        quarter=1, clock=900, possession="home",
        down=1, distance=10, yard_line=75,
        home_score=0, away_score=0,
        home_team=home_dists.play_calling.team,
        away_team=away_dists.play_calling.team,
        receiving_2nd_half="away",
        week=week,
    )
    home_box = TeamBoxScore()
    away_box = TeamBoxScore()

    # Coin toss
    if rng.random() < 0.5:
        state.possession = "home"
        state.receiving_2nd_half = "away"
    else:
        state.possession = "away"
        state.receiving_2nd_half = "home"

    # Opening kickoff
    recv_dists = home_dists if state.possession == "home" else away_dists
    perform_kickoff(state, recv_dists.drive_start, rng)

    total_plays = 0

    while not state.game_over and total_plays < MAX_PLAYS:
        off_dists = home_dists if state.possession == "home" else away_dists
        def_dists = away_dists if state.possession == "home" else home_dists
        off_box = home_box if state.possession == "home" else away_box
        def_box = away_box if state.possession == "home" else home_box

        # 4th down decision
        if state.down == 4:
            decision = fourth_down_decision(state, off_dists.kicking)
            if decision == "punt":
                perform_punt(state, rng, off_box)
                apply_clock(state, 5)
                check_two_minute_warning(state)
                check_quarter_end(state, home_dists.drive_start, away_dists.drive_start, rng)
                continue
            elif decision == "field_goal":
                recv_ds = away_dists.drive_start if state.possession == "home" else home_dists.drive_start
                attempt_field_goal(state, off_dists.kicking, recv_ds, rng, off_box)
                apply_clock(state, 5)
                check_two_minute_warning(state)
                check_quarter_end(state, home_dists.drive_start, away_dists.drive_start, rng)
                # Check OT walk-off FG
                if state.quarter == 5 and state.home_score != state.away_score:
                    state.game_over = True
                continue

        # Select and resolve play
        script = resolve_game_script(
            state,
            off_dists.game_script_config,
            off_dists.game_script_profile,
        )
        play_type = select_play_type(
            state,
            off_dists.play_calling,
            rng,
            script=script,
            play_call_context=off_dists.play_call_context,
        )
        roster = home_roster if state.possession == "home" else away_roster
        is_home_team = (state.possession == "home")
        result = resolve_play(
            state, play_type, off_dists.play_outcomes,
            off_dists.turnover_rates, rng, roster=roster,
            is_home=is_home_team,
            pace_factor=effective_pace_factor(off_dists.pace_factor, script),
            goal_line_concentration_enabled=off_dists.goal_line_concentration_enabled,
            script=script,
            target_selection_context=off_dists.target_selection_context,
            qb_scramble_context=off_dists.qb_scramble_context,
        )
        total_plays += 1

        # --- Penalty check FIRST — if penalty, skip stats and play outcome ---
        off_penalty_rates = getattr(off_dists, 'penalty_rates', None)
        if off_penalty_rates is not None and not result.is_penalty:
            penalty = check_penalty(off_penalty_rates, rng)
            if penalty is not None:
                penalty_type, penalty_yards = penalty
                if penalty_type == "pass_interference":
                    max_advance = max(0, state.yard_line - 1)
                    yards = min(penalty_yards, max_advance)
                    state.yard_line -= yards
                    state.down = 1
                    state.distance = min(10, state.yard_line)
                else:
                    state.yard_line = min(99, state.yard_line + penalty_yards)
                    state.distance = min(state.distance + penalty_yards, 99)
                apply_clock(state, 0)
                check_two_minute_warning(state)
                check_quarter_end(state, home_dists.drive_start, away_dists.drive_start, rng)
                continue

        # Only update stats if play was NOT a penalty
        _update_box_scores(
            off_box, def_box, result, rng=rng,
            int_return_td_rate=def_dists.defensive_td_rates.int_return_td_rate,
            fumble_return_td_rate=def_dists.defensive_td_rates.fumble_return_td_rate,
        )

        # Update per-player stats when rosters are provided
        if roster is not None:
            _update_player_stats(player_stats, result, roster)

        # Handle play outcome
        if result.is_safety:
            _handle_safety(state, off_box, def_box, def_dists.drive_start, rng)
        elif result.is_touchdown:
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
        elif result.is_interception or result.is_fumble:
            handle_turnover(state, result)
        else:
            apply_yards(state, result.yards)

        # Clock
        apply_clock(state, result.clock_runoff)
        check_two_minute_warning(state)
        check_quarter_end(state, home_dists.drive_start, away_dists.drive_start, rng)

    return GameResult(
        home_score=state.home_score,
        away_score=state.away_score,
        home_box=home_box,
        away_box=away_box,
        total_plays=total_plays,  # scrimmage plays only (excludes punts/FGs)
        overtime=state.quarter >= 5,
        player_stats=player_stats,
    )


def _update_box_scores(
    off_box: TeamBoxScore,
    def_box: TeamBoxScore,
    result: PlayResult,
    rng: np.random.Generator | None = None,
    int_return_td_rate: float = INT_RETURN_TD_RATE,
    fumble_return_td_rate: float = FUMBLE_RETURN_TD_RATE,
) -> None:
    """Update both offensive and defensive box scores from a play result."""
    if result.play_type == "pass":
        off_box.pass_attempts += 1
        if result.is_sack:
            off_box.sacks_taken += 1
            off_box.sack_yards += abs(result.yards)
            def_box.sacks_made += 1
        elif result.is_interception:
            off_box.interceptions_thrown += 1
            def_box.interceptions_caught += 1
            if rng is not None and rng.random() < int_return_td_rate:
                def_box.defensive_tds += 1
        elif result.is_complete:
            off_box.completions += 1
            off_box.pass_yards += result.yards
            if result.is_touchdown:
                off_box.pass_tds += 1
    elif result.play_type == "run":
        off_box.rush_attempts += 1
        off_box.rush_yards += result.yards
        if result.is_touchdown:
            off_box.rush_tds += 1

    if result.is_fumble:
        off_box.fumbles_lost += 1
        def_box.fumbles_recovered += 1
        if rng is not None and rng.random() < fumble_return_td_rate:
            def_box.defensive_tds += 1


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

    if two_pt_scorer is not None and player_stats is not None and two_pt_scorer in player_stats:
        player_stats[two_pt_scorer].two_point_conversions += 1

    change_possession(state)
    perform_kickoff(state, recv_drive_start, rng)


def _handle_safety(
    state: GameState,
    off_box: TeamBoxScore,
    def_box: TeamBoxScore,
    def_drive_start: DriveStartModel,
    rng: np.random.Generator,
) -> None:
    """Score a safety (2 points to defense), then free kick to defense."""
    defending = state.defense
    if defending == "home":
        state.home_score += 2
    else:
        state.away_score += 2
    def_box.points += 2
    def_box.safeties += 1
    change_possession(state)
    perform_kickoff(state, def_drive_start, rng)


def _get_player_info(roster: "TeamRoster", player_id: str) -> tuple[str, str, str]:
    """Look up player name, position, team from roster."""
    for p in roster.players:
        if p.player_id == player_id:
            return p.name, p.position, p.team
    return "", "", ""


def _update_player_stats(
    player_stats: dict[str, PlayerBoxScore],
    result: PlayResult,
    roster: "TeamRoster",
) -> None:
    """Update per-player stats from a play result."""
    if result.passer_id is not None:
        if result.passer_id not in player_stats:
            name, position, team = _get_player_info(roster, result.passer_id)
            player_stats[result.passer_id] = PlayerBoxScore(
                player_id=result.passer_id, name=name,
                position=position or "QB", team=team)
        qb = player_stats[result.passer_id]
        if result.play_type == "pass":
            qb.pass_attempts += 1
            if result.is_sack:
                qb.sacks += 1
            elif result.is_interception:
                qb.interceptions += 1
            elif result.is_complete:
                qb.completions += 1
                qb.pass_yards += result.yards
                if result.is_touchdown:
                    qb.pass_tds += 1
            # QB fumble: sack-fumble or pre-throw fumble (not complete, not INT).
            # Guarded by play_type=="pass" to avoid double-counting on scrambles,
            # where the rusher block handles fumble attribution instead.
            if result.is_fumble and not result.is_complete and not result.is_interception:
                qb.fumbles_lost += 1

    if result.receiver_id is not None:
        if result.receiver_id not in player_stats:
            name, position, team = _get_player_info(roster, result.receiver_id)
            player_stats[result.receiver_id] = PlayerBoxScore(
                player_id=result.receiver_id, name=name,
                position=position, team=team)
        rec = player_stats[result.receiver_id]
        rec.targets += 1
        if result.is_complete:
            rec.receptions += 1
            rec.receiving_yards += result.yards
            if result.is_touchdown:
                rec.receiving_tds += 1
        if result.is_fumble and result.is_complete:
            rec.fumbles_lost += 1

    if result.rusher_id is not None:
        if result.rusher_id not in player_stats:
            name, position, team = _get_player_info(roster, result.rusher_id)
            player_stats[result.rusher_id] = PlayerBoxScore(
                player_id=result.rusher_id, name=name,
                position=position, team=team)
        rush = player_stats[result.rusher_id]
        rush.rush_attempts += 1
        rush.rush_yards += result.yards
        if result.is_touchdown:
            rush.rush_tds += 1
        if result.is_fumble:
            rush.fumbles_lost += 1

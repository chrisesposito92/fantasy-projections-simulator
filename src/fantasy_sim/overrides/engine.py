from fantasy_sim.models.player import TeamRoster
from fantasy_sim.engine.types import TeamDistributions
from fantasy_sim.models.distributions import PlayCallingDist, TurnoverRates

# Valid player override fields
PLAYER_USAGE_FIELDS = {
    "target_share", "carry_share", "red_zone_target_share",
    "red_zone_carry_share", "snap_share", "scramble_rate",
}
PLAYER_OUTCOME_FIELDS = {"catch_rate", "fumble_rate"}
PLAYER_META_FIELDS = {"games_played", "games_missed"}

# Valid team override fields
TEAM_OVERRIDE_FIELDS = {
    "pass_rate", "int_rate", "fumble_rate", "sack_rate", "sack_fumble_rate",
}


def apply_player_override(
    roster: TeamRoster, player_id: str, overrides: dict
) -> None:
    """Apply overrides to a specific player in the roster. Mutates in place."""
    player = None
    for p in roster.players:
        if p.player_id == player_id:
            player = p
            break
    if player is None:
        raise KeyError(f"Player '{player_id}' not found in {roster.team} roster")

    for field, value in overrides.items():
        if field in PLAYER_USAGE_FIELDS:
            old_value = getattr(player.usage, field)
            setattr(player.usage, field, value)
            # Trigger redistribution for share fields
            if field == "target_share":
                redistribute_target_shares(roster, player_id, old_value, value)
            elif field == "carry_share":
                redistribute_carry_shares(roster, player_id, old_value, value)
        elif field in PLAYER_OUTCOME_FIELDS:
            setattr(player.outcomes, field, value)
        elif field == "games_played":
            player.games_played = value
        elif field == "games_missed":
            # games_missed is a list of week numbers; convert to games_played
            player.games_played = 17 - len(value)
        else:
            raise ValueError(
                f"Unknown override field '{field}'. "
                f"Valid: {PLAYER_USAGE_FIELDS | PLAYER_OUTCOME_FIELDS | PLAYER_META_FIELDS}"
            )


def redistribute_target_shares(
    roster: TeamRoster, changed_id: str, old_share: float, new_share: float
) -> None:
    """Redistribute target share delta proportionally to eligible teammates."""
    delta = new_share - old_share

    eligible = [
        p for p in roster.players
        if p.player_id != changed_id and p.usage.target_share > 0
    ]
    if not eligible or delta == 0:
        return

    total_eligible = sum(p.usage.target_share for p in eligible)
    if total_eligible == 0:
        return

    # Cap delta so teammates don't go below zero (preserves total)
    if delta > total_eligible:
        delta = total_eligible

    for p in eligible:
        proportion = p.usage.target_share / total_eligible
        adjustment = -delta * proportion
        p.usage.target_share = max(0.0, p.usage.target_share + adjustment)


def redistribute_carry_shares(
    roster: TeamRoster, changed_id: str, old_share: float, new_share: float
) -> None:
    """Redistribute carry share delta proportionally to eligible teammates."""
    delta = new_share - old_share

    eligible = [
        p for p in roster.players
        if p.player_id != changed_id and p.usage.carry_share > 0
    ]
    if not eligible or delta == 0:
        return

    total_eligible = sum(p.usage.carry_share for p in eligible)
    if total_eligible == 0:
        return

    # Cap delta so teammates don't go below zero (preserves total)
    if delta > total_eligible:
        delta = total_eligible

    for p in eligible:
        proportion = p.usage.carry_share / total_eligible
        adjustment = -delta * proportion
        p.usage.carry_share = max(0.0, p.usage.carry_share + adjustment)


def apply_team_override(dists: TeamDistributions, overrides: dict) -> None:
    """Apply team-level overrides to distributions. Mutates in place."""
    for field, value in overrides.items():
        if field == "pass_rate":
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"pass_rate must be between 0.0 and 1.0, got {value}")
            dists.play_calling = PlayCallingDist(
                team=dists.play_calling.team,
                distributions=dists.play_calling.distributions,
                default={"pass": value, "run": 1.0 - value},
            )
        elif field == "int_rate":
            dists.turnover_rates = TurnoverRates(
                team=dists.turnover_rates.team,
                int_rate=value,
                fumble_rate=dists.turnover_rates.fumble_rate,
                sack_rate=dists.turnover_rates.sack_rate,
                sack_fumble_rate=dists.turnover_rates.sack_fumble_rate,
            )
        elif field == "fumble_rate":
            dists.turnover_rates = TurnoverRates(
                team=dists.turnover_rates.team,
                int_rate=dists.turnover_rates.int_rate,
                fumble_rate=value,
                sack_rate=dists.turnover_rates.sack_rate,
                sack_fumble_rate=dists.turnover_rates.sack_fumble_rate,
            )
        elif field == "sack_rate":
            dists.turnover_rates = TurnoverRates(
                team=dists.turnover_rates.team,
                int_rate=dists.turnover_rates.int_rate,
                fumble_rate=dists.turnover_rates.fumble_rate,
                sack_rate=value,
                sack_fumble_rate=dists.turnover_rates.sack_fumble_rate,
            )
        elif field == "sack_fumble_rate":
            dists.turnover_rates = TurnoverRates(
                team=dists.turnover_rates.team,
                int_rate=dists.turnover_rates.int_rate,
                fumble_rate=dists.turnover_rates.fumble_rate,
                sack_rate=dists.turnover_rates.sack_rate,
                sack_fumble_rate=value,
            )
        else:
            raise ValueError(
                f"Unknown team override field '{field}'. "
                f"Valid: {TEAM_OVERRIDE_FIELDS}"
            )

from dataclasses import dataclass, field
from pathlib import Path
import yaml


@dataclass
class OverrideSet:
    """Parsed overrides ready to apply."""
    players: dict[str, dict] = field(default_factory=dict)
    teams: dict[str, dict] = field(default_factory=dict)


def parse_override_config(path: Path) -> OverrideSet:
    """Parse a season.yaml config file into an OverrideSet."""
    with open(path) as f:
        config = yaml.safe_load(f) or {}

    result = OverrideSet()

    players = config.get("players", {})
    if players:
        for name, overrides in players.items():
            result.players[str(name)] = dict(overrides)

    teams = config.get("teams", {})
    if teams:
        for team, overrides in teams.items():
            result.teams[str(team)] = dict(overrides)

    return result


def parse_cli_override(override_str: str) -> tuple[str, str, float | int | list]:
    """Parse a CLI override string like 'mahomes.target_share=0.30'.

    Returns: (entity_name, field_name, value)
    """
    if "=" not in override_str:
        raise ValueError(
            f"Invalid override format: '{override_str}'. "
            f"Expected: 'name.field=value'"
        )

    key, value_str = override_str.split("=", 1)

    if "." not in key:
        raise ValueError(
            f"Invalid override key: '{key}'. "
            f"Expected: 'player_name.field' or 'TEAM.field'"
        )

    entity, field_name = key.rsplit(".", 1)

    # Parse value
    try:
        if "." in value_str:
            value = float(value_str)
        else:
            value = int(value_str)
    except ValueError:
        # Try as list (e.g., "[1,2,3]")
        if value_str.startswith("[") and value_str.endswith("]"):
            value = [int(x.strip()) for x in value_str[1:-1].split(",")]
        else:
            value = value_str

    return entity, field_name, value

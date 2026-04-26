from pathlib import Path
import yaml


class ConfigError(Exception):
    """Raised for configuration errors."""
    pass


def load_config(path: Path) -> dict:
    """Load a YAML config file and return as dict."""
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")
    with open(path) as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ConfigError(f"Config file is empty or not a valid YAML mapping: {path}")
    return data


def resolve_scoring(
    scoring_presets: dict, format_name: str, _seen: frozenset[str] | None = None,
) -> dict:
    """Resolve a scoring format, following _inherit chains.

    Args:
        scoring_presets: The "scoring" section of the config (contains ppr, half_ppr, etc.)
        format_name: Which format to resolve (e.g., "ppr", "half_ppr")

    Returns:
        Flat dict of stat_name -> point_value with all inheritance resolved.
    """
    _seen = _seen or frozenset()
    if format_name in _seen:
        raise ConfigError(
            f"Circular _inherit detected: '{format_name}' already in chain"
        )
    if format_name not in scoring_presets:
        raise ConfigError(
            f"Unknown scoring format '{format_name}'. "
            f"Available: {', '.join(scoring_presets.keys())}"
        )

    preset = scoring_presets[format_name]

    if "_inherit" in preset:
        parent_name = preset["_inherit"]
        base = resolve_scoring(scoring_presets, parent_name, _seen | {format_name})
        # Override parent values with child values
        for k, v in preset.items():
            if k != "_inherit":
                base[k] = v
        return base
    else:
        return {k: v for k, v in preset.items()}


def load_custom_scoring(path: Path, scoring_presets: dict) -> dict:
    """Load a custom scoring config that optionally inherits from a preset.

    Custom scoring file format:
        inherit: ppr          # optional: base preset to inherit from
        overrides:            # scoring keys to override or add
            passing_td: 6
            reception_wr: 1.5
    """
    config = load_config(path)

    inherit_from = config.get("inherit")
    if inherit_from:
        base = resolve_scoring(scoring_presets, inherit_from)
    else:
        base = {}

    if "overrides" in config and not isinstance(config["overrides"], dict):
        raise ConfigError(
            f"'overrides' must be a mapping in custom scoring config: {path}"
        )

    overrides = config.get("overrides") or {}
    if overrides:
        base.update(overrides)

    return base


def get_defaults_path() -> Path:
    """Return the path to the default config file."""
    return Path(__file__).parent.parent.parent.parent / "config" / "defaults.yaml"


def load_defaults() -> dict:
    """Load the default configuration."""
    return load_config(get_defaults_path())


def get_phase1_ks_flags() -> dict:
    """Return the phase1_ks_flags block from the loaded defaults.yaml.

    Used by per-KS code-change sites to branch on whether the new code path is
    enabled. Read at module import time (not per call) for performance — flag
    flips during a single Python process require a process restart anyway, since
    validate.py's two arms are a single process.

    Returns an empty dict if the block is missing (so callers'
    ``.get(...).get('enabled', False)`` chains stay defensive against older
    defaults snapshots that pre-date Cycle 3).
    """
    defaults = load_defaults()
    return defaults.get("phase1_ks_flags", {})

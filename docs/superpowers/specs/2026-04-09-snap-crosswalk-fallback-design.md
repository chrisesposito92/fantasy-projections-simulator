# Snap Crosswalk Fallback Matching

**Date**: 2026-04-09
**Status**: Draft
**Scope**: `src/fantasy_sim/data/usage/engine.py`, `models.py`, `config.py`, `config/defaults.yaml`

## Problem

The snap crosswalk in `UsageEngine._build_snap_crosswalk()` matches PFR player IDs (`pfr_player_id` from snap counts) to nflverse `gsis_id` via two tiers:

1. **Tier 1**: Direct `pfr_player_id` -> roster `pfr_id` join
2. **Tier 2**: Exact name+team fallback for players with null `pfr_id` in rosters

Across 2022-2024, 3-9 skill players per season-week remain unmatched (0.5-1.4%). Investigation reveals five root causes:

| Cause | Examples | Count |
|-------|----------|-------|
| **Capitalization** mismatch | "Grant Dubose" vs "Grant DuBose", "D'Vonte" vs "D'vonte" | 2 |
| **Suffix** mismatch (Jr./II/III) | "Kevin Austin" vs "Kevin Austin Jr." | 1+ |
| **Name variant** (nickname/middle name) | "Michael Woods II" vs "Mike Woods", "John Samuel Shenker" vs "John Shenker" | 2 |
| **PFR ID mismatch** between sources | snap LassKw00 vs roster LassKw20 (same player) | 1 |
| **Missing from rosters** entirely | Rodney Williams (WillRo08) — irrelevant TE | 1 |

Players with inconsistent `pfr_id` across seasons (WalkKe00, RobiBr01, JoneVe00) fail Tier 1 in some seasons and fall through to Tier 2, where suffix differences block the name match.

## Solution

Three changes to `_build_snap_crosswalk()`, ordered from most-automatic to most-manual:

### 1. Case-insensitive Tier 2 matching

Lowercase both snap `player` and roster `full_name`/`player_name` before joining. Fixes capitalization mismatches (DuboGr00, PricDV00) with zero maintenance.

### 2. Suffix + middle-name normalization in Tier 2

Before the name+team join, normalize both sides:
- Strip suffixes: `Jr.`, `Jr`, `Sr.`, `Sr`, `II`, `III`, `IV`, `V` (as whole words at end of string)
- Collapse to first + last name only (drop middle names): `"John Samuel Shenker"` -> `"John Shenker"`
- Strip periods and extra whitespace

This is applied as a **derived join column** — the original names are preserved, only the comparison key is normalized. Fixes suffix and middle-name mismatches automatically.

**Edge case**: Two players with identical first+last name on the same team (e.g., father/son). This is extremely rare for active NFL skill players on the same roster. If it occurs, the manual crosswalk (below) serves as the override.

### 3. Manual crosswalk dict (Tier 0 — checked first)

A `pfr_player_id -> gsis_id` dict in YAML config, checked **before** Tier 1. This is the authoritative override for:
- Name variants that normalization can't fix ("Michael" vs "Mike")
- PFR ID mismatches between data sources (LassKw00 in snaps = LassKw20 in rosters)
- Any future edge case

Checked first because it represents human-verified mappings that should override automated matching.

## Files Changed

### `config/defaults.yaml`

Add `manual_crosswalk` under `usage.snap`:

```yaml
usage:
  snap:
    prior_strength: 8.0
    min_games: 4
    factor_clamp: [0.70, 1.30]
    manual_crosswalk:
      # Name variants (automated matching can't resolve)
      WoodMi00: "00-0037300"   # Michael Woods II -> Mike Woods (CLE)
      # PFR ID mismatches between snap data and roster data
      LassKw00: "00-0037420"   # Kwamie Lassiter II (snap LassKw00 != roster LassKw20)
```

Only entries that automated matching can't resolve go here. Suffix/capitalization cases are handled automatically and should NOT be added to the manual dict.

### `src/fantasy_sim/data/usage/models.py`

Add `manual_crosswalk` field to `SnapConfig`:

```python
@dataclass
class SnapConfig:
    prior_strength: float = 8.0
    min_games: int = 4
    factor_clamp: tuple[float, float] = (0.70, 1.30)
    manual_crosswalk: dict[str, str] = field(default_factory=dict)
```

### `src/fantasy_sim/data/usage/config.py`

Parse `manual_crosswalk` from YAML:

```python
snap=SnapConfig(
    prior_strength=snap_d.get("prior_strength", 8.0),
    min_games=snap_d.get("min_games", 4),
    factor_clamp=tuple(snap_d.get("factor_clamp", [0.70, 1.30])),
    manual_crosswalk=snap_d.get("manual_crosswalk", {}),
),
```

### `src/fantasy_sim/data/usage/engine.py`

Changes to `_build_snap_crosswalk()`:

1. **Tier 0 (new)**: Seed `crosswalk` dict from `self._config.snap.manual_crosswalk` before any automated matching. Log count at INFO level.

2. **Tier 1 (unchanged)**: Direct `pfr_player_id` -> roster `pfr_id` join. Skip any PFR IDs already in crosswalk from Tier 0.

3. **Tier 2 (enhanced)**: For remaining unmatched players:
   - Derive normalized name columns on both snap and roster DataFrames using a `_normalize_name()` helper
   - Join on normalized name (lowercased, suffix-stripped, first+last only) + team
   - Skip any PFR IDs already in crosswalk from Tier 0/1

Add module-level helper:

```python
import re

_SUFFIXES = re.compile(r'\s+(jr\.?|sr\.?|ii|iii|iv|v)\s*$', re.IGNORECASE)

def _normalize_name(name: str) -> str:
    """Normalize player name for fuzzy matching.

    Lowercases, strips suffixes (Jr./Sr./II/III/IV/V),
    collapses to first + last name, removes periods.
    """
    name = name.lower().strip()
    name = _SUFFIXES.sub('', name)
    name = name.replace('.', '')
    parts = name.split()
    if len(parts) > 2:
        parts = [parts[0], parts[-1]]  # first + last only
    return ' '.join(parts)
```

## Logging

- **Tier 0**: `INFO` — "Snap crosswalk: %d manual overrides applied"
- **Tier 2**: Existing `INFO` for name+team fallback matches (now includes normalized matches)
- **Remaining unmatched**: Existing `WARNING` with player list (unchanged)

The warning log now only fires for players that fail all three tiers — expected to be 0-2 per season (genuinely missing from nflverse rosters).

## Testing

- Unit test `_normalize_name()` with suffix, middle-name, capitalization, and clean-name cases
- Unit test Tier 0: manual crosswalk overrides automated matching
- Unit test enhanced Tier 2: capitalization and suffix mismatches now resolve
- Integration test: mock snap data with known mismatched names, verify crosswalk resolves them
- Regression: existing tests continue to pass (no behavior change for already-matched players)

## What This Does NOT Fix

- Players genuinely missing from nflverse rosters (no `gsis_id` exists) — these stay as warnings. Correct behavior for irrelevant players.
- The manual dict requires knowing the `gsis_id`, which must be looked up from nflverse rosters. The unmatched warning log provides the PFR IDs to investigate.

## Maintenance

The manual crosswalk should be reviewed each season when new unmatched warnings appear. Most new unmatched players will be auto-resolved by the enhanced Tier 2. Only name variants and PFR ID mismatches need manual entries.

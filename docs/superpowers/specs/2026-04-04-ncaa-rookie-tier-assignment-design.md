# NCAA Rookie Tier Assignment Design

## Problem

Rookies have zero NFL PBP history, so the tier engine skips them entirely. They fall back to `build_rookie_model(draft_round=7)` — the worst-tier draft-capital archetype. An elite college route runner lands in the same tier as a 7th-round pick regardless of film quality. ~50-60 rookies per season are disproportionately misranked.

## Solution

Use college PFF grades (2022-2025 NCAA data) to place rookies directly into NFL talent tiers. The `pff_id` field on the nflverse roster matches the NCAA PFF `player_id` directly — no name/college matching needed. Match rate: 85/85 drafted, 143/144 total skill rookies for 2025.

## Design Decisions

1. **All rookies with NCAA PFF data** get grade-based tier assignment, not just drafted players. Undrafted breakouts (Amon-Ra St. Brown pattern) get grade-appropriate tiers. Players without NCAA PFF data fall back to existing `rookie_builder.py` archetypes.

2. **Direct grade comparison** — NCAA grades are plugged directly into NFL tier percentile boundaries. The distributions are close (NCAA WR route: mean 62.2, std 10.6; NFL: mean 63.6, std 12.1). The 1.4-point gap doesn't justify a percentile remapping transformation.

3. **Grade drives tier, draft capital drives confidence** — PFF grades are an independent evaluation of what the player did on film. A UDFA with an 82.0 college route grade genuinely ran elite routes. Draft capital modulates how much we trust the tier placement (blend weight), not which tier they land in.

4. **Most recent NCAA season only** — a 2025 NFL rookie uses their 2024 college grades. Most predictive of NFL readiness. A WR who went from 55 to 80 sophomore-to-junior should be evaluated on the 80.

## Config

New `NcaaRookieConfig` dataclass under `TierConfig`:

```python
@dataclass
class NcaaRookieConfig:
    """Configuration for NCAA-based rookie tier assignment."""
    enabled: bool = True
    draft_confidence: dict[int, float] = field(default_factory=lambda: {
        1: 1.0, 2: 0.95, 3: 0.85, 4: 0.75, 5: 0.65, 6: 0.55, 7: 0.50,
    })
    undrafted_confidence: float = 0.40
    ncaa_lookback_seasons: int = 4
```

`defaults.yaml` addition under `tier_engine:`:

```yaml
ncaa_rookie:
  enabled: true
  draft_confidence:
    1: 1.0
    2: 0.95
    3: 0.85
    4: 0.75
    5: 0.65
    6: 0.55
    7: 0.50
  undrafted_confidence: 0.40
  ncaa_lookback_seasons: 4
```

Draft round derived from pick number: `round = min((draft_number - 1) // 32 + 1, 7)`.

## NCAA Grade Loading

New method `TierEngine._load_ncaa_grades(pff_id, position, rookie_season)`:

1. Compute most recent college season: `rookie_season - 1`. Walk back up to `ncaa_lookback_seasons` if not found (handles redshirts, opt-outs).
2. Load position-appropriate NCAA facet via `self._pff_loader.load_ncaa_facet()` — same `_POSITION_FACETS` mapping as NFL (receiving_summary for WR/TE, rushing_summary for RB, passing_summary for QB).
3. Filter to player's `pff_id`, compute season average across games.
4. Return grade dict (same format as `_load_season_grades()`) or `None`.
5. Cache in `_ncaa_grade_cache: dict[tuple[int, str, int], dict[str, float] | None]`.

The `pff_id` bridge: nflverse roster `pff_id` column == NCAA PFF `player_id`. Verified: 85/85 drafted, 143/144 total for 2025 class.

## Rookie Tier Assignment & Blending

New method `TierEngine._apply_rookie_tiers(roster, nfl_roster, skipped_players, target_season, team_context, rng)`:

`skipped_players` = players the main `apply_tiers()` loop couldn't process (no NFL PFF crosswalk entry).

Per-player pipeline:

1. **Identify rookies** — look up `rookie_year` from roster DF. Skip if `rookie_year != target_season` (not a rookie, just missing NFL PFF data for other reasons).
2. **Load NCAA grades** — get `pff_id` from roster DF, call `_load_ncaa_grades()`. Skip if no grades found (keeps archetype model).
3. **Assign tier** — call existing `_assign_tier(primary_grade, position)` using NFL boundaries. Direct grade comparison.
4. **Select tier distributions** — call existing `_interpolate_scalars(pool, secondary_pct)`. Use NCAA secondary grade for within-tier percentile if available, else 0.5.
5. **Apply team context** — call existing `apply_team_context()` if `team_context` provided.
6. **Compute blend weight** — derive draft round from `draft_number`, look up `draft_confidence` (or `undrafted_confidence`). Blend reliability = `1.0 - draft_confidence`.
7. **Blend** — call existing `_blend_player(player, tier_dists, reliability, rng)`. The player's current model is the archetype from `build_rookie_model()`. After blending, archetype values are partially or fully replaced by tier pool distributions.

Blend direction:
- `draft_confidence = 1.0` (1st round) → `reliability = 0.0` → 100% tier, 0% archetype
- `draft_confidence = 0.4` (UDFA) → `reliability = 0.6` → 60% archetype, 40% tier

## Integration

**`apply_tiers()` change:**

```python
# After existing veteran loop:
skipped = []
for player in roster.players:
    pff_id = reverse_cw.get(player.player_id)
    if pff_id is None:
        skipped.append(player)
        continue
    # ... existing veteran tier assignment ...

if skipped and self._config.ncaa_rookie.enabled and nfl_roster is not None:
    self._apply_rookie_tiers(
        roster, nfl_roster, skipped, target_s, team_context, rng,
    )
```

**`GameContextBuilder`:** No changes. Already passes `nfl_roster` and `team_context` to `apply_tiers()`.

**`loader.py`:** No changes. Existing `build_ncaa_crosswalk()` is unused by this feature (pff_id bridge replaces it). `load_ncaa_facet()` already exists.

**`rookie_builder.py`:** No changes. Continues producing archetype models for all rookies. NCAA tier assignment blends over those archetypes for players with college grades.

**Pipeline ordering:**
```
base model (PBP + archetype) → matchup → team context + tier blend (veterans)
→ team context + tier blend (rookies via NCAA) → normalize → user overrides → normalize
```

## Files Modified

| File | Change |
|------|--------|
| `src/fantasy_sim/data/pff/models.py` | Add `NcaaRookieConfig` dataclass, add `ncaa_rookie` field to `TierConfig` |
| `src/fantasy_sim/data/pff/tier_engine.py` | Add `_pick_to_round()`, `_load_ncaa_grades()`, `_apply_rookie_tiers()`. Modify `apply_tiers()` to collect skipped players and call rookie path. |
| `config/defaults.yaml` | Add `ncaa_rookie` section under `tier_engine` |
| `src/fantasy_sim/data/pff/config.py` | Parse `ncaa_rookie` sub-config from `tier_engine` YAML section into `NcaaRookieConfig`. Manual parsing like the other sub-configs (not generic dict→dataclass). Handle `draft_confidence` dict with int keys. |
| `scripts/validate_pff_signal.py` | Add `--mode ncaa_rookie+tier` and `ncaa_rookie+tier+matchup`, support `ncaa_rookie` in `--config-override` |
| `tests/test_data/test_pff/test_tier_engine.py` | New tests for rookie tier assignment |

## Test Plan

1. **`_pick_to_round()`** — pick 1→round 1, pick 32→round 1, pick 33→round 2, pick 224→round 7, pick 260→round 7 (capped), None→None
2. **`_load_ncaa_grades()`** — loads correct facet per position, returns season-averaged grades, lookback when most recent season missing, returns None for unknown player, caches results
3. **`_apply_rookie_tiers()`** — 1st-rounder gets full tier influence (reliability~0.0), UDFA gets partial archetype blend (reliability~0.6), non-rookie skipped player is ignored, player without NCAA data keeps archetype, team context applied before blend
4. **`apply_tiers()` integration** — veterans still processed normally, rookies with NCAA data get tier-assigned, rookies without NCAA data unchanged, config `enabled: false` skips rookie path
5. **Config parsing** — `NcaaRookieConfig` round-trips through YAML, draft_confidence dict parsed correctly, defaults applied
6. **pff_id bridge** — roster `pff_id` correctly matches NCAA `player_id`, handles missing/null pff_id

## A/B Validation

- New modes in `validate_pff_signal.py`: `ncaa_rookie+tier`, `ncaa_rookie+tier+matchup`
- `--config-override` supports `ncaa_rookie` key for sweep testing
- Compare against baseline #24 (tc+matchup-no-passrate: rank_corr +0.0381, szn_mae -4.309)
- Expected signal: better rank correlation for rookie-heavy teams, improved season MAE from ~50-60 correctly-tiered rookies per season

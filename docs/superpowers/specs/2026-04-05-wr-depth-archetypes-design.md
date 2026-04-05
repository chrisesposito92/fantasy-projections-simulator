# WR Depth-of-Target Archetypes Within Tiers

**Date**: 2026-04-05
**Status**: Design approved
**Roadmap item**: #4 — Depth-of-Target Archetypes Within Tiers
**Baseline**: #28 ncaa-rookie+tier+matchup (rank_corr +0.0472, szn_mae -4.923, calibr -0.0126)

## Problem

All WRs within a tier share one yards distribution pool and one catch_rate summary. A deep-threat WR and a slot WR in Tier 2 have genuinely different yards-per-catch distributions (deep threats average ~15+ YPC, slot receivers ~7-9 YPC) and catch rates (slot ~68-72%, deep ~50-55%). Blending them into one pool is actively wrong — it systematically underestimates deep-threat yards and overestimates slot yards.

## Solution

Create 3 archetype sub-pools (slot / possession / deep) within each WR tier, classified by ADOT (Average Depth of Target) from PFF's `receiving_summary` facet. Override only `receiving_yards_dist` and `catch_rate` from the archetype sub-pool. All other scalars (target_share, carry_share, air_yards_share, fumble_rate) remain from the main tier pool.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Fields affected | yards distributions + catch_rate | Yards and catch_rate are structurally different by archetype (~15pt catch_rate gap). Target/carry share are about role/volume, already well-captured by PBP data. |
| Boundary method | Global ADOT percentiles (p33, p67) | "Deep threat" is a role definition, not tier-relative. Global percentiles adapt across seasons unlike fixed thresholds. |
| Number of archetypes | 3 (slot / possession / deep) with fallback | Slot/possession/deep are genuinely different player types. Fallback to full tier pool when sub-pool < min_archetype_pool_size. |
| NCAA rookies | Yes, use NCAA ADOT | Depth profile is the most stable trait across college-to-NFL transition. NCAA receiving_summary has avg_depth_of_target. |

## Data Foundation

**Signal source**: `avg_depth_of_target` from `receiving_summary` PFF facet — already loaded by `_load_season_grades()` for WRs. No new facet loading required.

**Correlation**: ADOT from receiving_summary has 0.825 correlation with `deep_pct` computed from the separate `receiving_depth` facet (n=115 WRs, 2024 season).

**Archetype separation** (342 WR player-seasons, 2022-2024, >=30 targets; approximate profiles from exploration — actual boundaries will be p33/p67 of ADOT):

| Archetype | Short % | Medium % | Deep % | ADOT range | Example players |
|-----------|---------|----------|--------|------------|-----------------|
| Slot (bottom 33%) | ~51% | ~26% | ~8% | ~5-8 | Greg Dortch, Wan'Dale Robinson, Curtis Samuel |
| Possession (middle 33%) | ~43% | ~30% | ~17% | ~9-14 | Justin Jefferson, Ja'Marr Chase, Malik Nabers |
| Deep (top 33%) | ~35% | ~29% | ~28% | ~15+ | Alec Pierce, Christian Watson, Marquez Valdes-Scantling |

**NCAA availability**: `avg_depth_of_target` present in NCAA `receiving_summary` (2022-2025).

## Architecture

### Data Model

New config dataclass in `models.py`:

```python
@dataclass
class ArchetypeConfig:
    """Configuration for WR depth-of-target archetypes within tiers."""
    enabled: bool = True
    n_archetypes: int = 3
    adot_grade_key: str = "avg_depth_of_target"
    min_archetype_pool_size: int = 20
```

Added to `TierConfig` as `archetypes: ArchetypeConfig`.

New instance state on `TierEngine`:

```python
# Archetype sub-pools: {position: {tier: {archetype_name: _TierPoolEntry}}}
self._archetype_pools: dict[str, dict[int, dict[str, _TierPoolEntry]]] | None = None

# Global ADOT boundaries: tuple of N-1 percentile values (e.g., (p33, p67) for 3 archetypes)
self._adot_boundaries: tuple[float, ...] | None = None
```

**`n_archetypes` behavior**: For N archetypes, compute N-1 evenly-spaced percentile boundaries. N=3: p33/p67 → slot/possession/deep. N=2: p50 → short-area/downfield. Archetype names for N=3 are `"slot"`, `"possession"`, `"deep"`; for N=2: `"short"`, `"deep"`. The `_classify_archetype` method handles both cases.

### Pool Building

Inside `_build_tier_pools()`, after existing WR tier pool construction:

1. **Compute global ADOT boundaries** — Collect `pff_grades["avg_depth_of_target"]` from all WR player-seasons across all tiers. Compute `N-1` evenly-spaced percentile boundaries where `N = n_archetypes` (for N=3: p33/p67; for N=2: p50). Store in `self._adot_boundaries`. Skip entirely if `archetypes.enabled = false`.

2. **Classify each WR player-season**:
   - ADOT < p33 → `"slot"`
   - p33 <= ADOT <= p67 → `"possession"`
   - ADOT > p67 → `"deep"`
   - ADOT missing → excluded from archetype sub-pools (still in main tier pool)

3. **Build archetype sub-pool entries** — For each (tier, archetype) combo, call `_build_pool_entry()` on the archetype's members. Produces a `_TierPoolEntry` with archetype-specific `receiving_yards_dist` and `catch_rate`.

4. **Thin pool check** — Sub-pools with fewer than `min_archetype_pool_size` members are not stored. Missing sub-pools fall back to the main tier pool at blend time.

The main `self._pools["WR"]` is built from ALL WR members as before — it is the fallback and the source for all non-archetype scalars.

### Archetype Classification

New method on `TierEngine`:

```python
def _classify_archetype(self, pff_grades: dict[str, float]) -> str | None:
    """Classify a WR into slot/possession/deep based on ADOT.
    Returns None if ADOT missing or boundaries not computed."""
    if self._adot_boundaries is None:
        return None
    adot = pff_grades.get(self._config.archetypes.adot_grade_key)
    if adot is None:
        return None
    p33, p67 = self._adot_boundaries
    if adot < p33:
        return "slot"
    if adot > p67:
        return "deep"
    return "possession"
```

### Blend-Time Override

In `apply_tiers()`, after `select_distributions()` returns `tier_dists` and before `_blend_player()`:

```python
if position == "WR" and self._archetype_pools:
    archetype = self._classify_archetype(pff_grades)
    if archetype:
        arch_pool = (self._archetype_pools
                     .get("WR", {}).get(assignment.tier, {}).get(archetype))
        if arch_pool:
            tier_dists.receiving_yards_dist = arch_pool.receiving_yards_dist
            tier_dists.catch_rate = self._interp_scalar(arch_pool.catch_rate, 0.5)
```

Catch_rate uses `0.5` (median) for interpolation — no within-archetype secondary grade interpolation, since the archetype sub-pool already narrows the population.

### NCAA Rookie Archetype Assignment

In `_apply_rookie_tiers()`, same pattern after `select_distributions()`:

```python
if position == "WR" and self._archetype_pools:
    archetype = self._classify_archetype(ncaa_grades)
    if archetype:
        arch_pool = (self._archetype_pools
                     .get("WR", {}).get(assignment.tier, {}).get(archetype))
        if arch_pool:
            tier_dists.receiving_yards_dist = arch_pool.receiving_yards_dist
            tier_dists.catch_rate = self._interp_scalar(arch_pool.catch_rate, 0.5)
```

NCAA ADOT is on the same scale as NFL ADOT (both from PFF `receiving_summary`). Global ADOT boundaries from NFL data are used for classification.

### Config

`defaults.yaml` addition under `pff.tier_engine`:

```yaml
archetypes:
  enabled: true
  n_archetypes: 3
  adot_grade_key: avg_depth_of_target
  min_archetype_pool_size: 20
```

## What Changes, What Doesn't

| Aspect | Changed? | Detail |
|--------|----------|--------|
| WR `receiving_yards_dist` | Yes | From archetype sub-pool when available |
| WR `catch_rate` | Yes | From archetype sub-pool when available |
| WR other scalars | No | target_share, carry_share, air_yards_share, fumble_rate from main tier pool |
| RB/TE/QB blending | No | Completely unaffected |
| `_blend_player()` | No | Receives better tier_dists, logic unchanged |
| `_build_pool_entry()` | No | Called on archetype member subsets, logic unchanged |
| Reliability scoring | No | Same formula, same blending weights |
| Main tier pools | No | Built from all WR members as before |

## Estimated Pool Sizes (3 training years, 342 WR player-seasons)

| Tier | Slot (~33%) | Possession (~33%) | Deep (~33%) | Full pool |
|------|-------------|-------------------|-------------|-----------|
| 1 (top 15%) | ~6 | ~6 | ~6 | ~17 |
| 2 | ~10 | ~10 | ~10 | ~30 |
| 3 | ~14 | ~14 | ~14 | ~41 |
| 4 | ~10 | ~10 | ~10 | ~30 |
| 5 (bottom 20%) | ~7 | ~7 | ~7 | ~20 |

Tiers 1, 4, 5 archetype sub-pools will likely fall below `min_archetype_pool_size=20` and use the full tier pool fallback. Tiers 2-3 (where most fantasy-relevant WRs live) will have active archetype sub-pools.

## A/B Validation

Uses existing `validate_pff_signal.py` harness with `--config-override`:

```bash
# Archetypes enabled (new default)
uv run python scripts/validate_pff_signal.py \
  --mode ncaa_rookie+tier+matchup --sims 50 --label "archetypes-on"

# Archetypes disabled (current behavior)
uv run python scripts/validate_pff_signal.py \
  --mode ncaa_rookie+tier+matchup --sims 50 \
  --config-override '{"tier_engine": {"archetypes": {"enabled": false}}}' \
  --label "archetypes-off"

# 2 archetypes variant
uv run python scripts/validate_pff_signal.py \
  --mode ncaa_rookie+tier+matchup --sims 50 \
  --config-override '{"tier_engine": {"archetypes": {"n_archetypes": 2}}}' \
  --label "archetypes-2"
```

**Success criteria** vs baseline #28:
- rank_corr: must not degrade (>= +0.047)
- wk_mae: improvement expected (archetype-specific yards → better weekly accuracy)
- szn_mae: improvement expected
- calibr: must not degrade

**Watch for**: rank_corr degradation → sub-pools too small, raising `min_archetype_pool_size` or reducing to 2 archetypes.

## Testing

Unit tests in `tests/test_data/test_pff/test_tier_engine.py`:

1. `_classify_archetype()` — correct archetype for ADOT below/at/above boundaries; `None` when ADOT missing or boundaries unset
2. ADOT boundary computation — p33/p67 from global WR player-seasons, not per-tier
3. Archetype sub-pool construction — 3 sub-pools built per tier with sufficient data; members correctly partitioned by ADOT
4. Thin pool fallback — sub-pool with < `min_archetype_pool_size` not stored; blend uses main tier pool
5. Blend override — WR blend uses archetype `receiving_yards_dist` and `catch_rate`; other scalars from main pool
6. Non-WR passthrough — RB/TE/QB unaffected by archetype logic
7. NCAA archetype — rookie with NCAA ADOT gets archetype sub-pool; rookie without ADOT uses full tier pool
8. Config disabled — `archetypes.enabled = false` produces identical behavior

Statistical validation tests (`@pytest.mark.statistical`):

9. Deep-threat archetype sub-pool has higher mean `receiving_yards_dist` than slot within the same tier
10. Slot archetype sub-pool has higher median `catch_rate` than deep within the same tier

## Files Modified

| File | Change |
|------|--------|
| `src/fantasy_sim/data/pff/models.py` | Add `ArchetypeConfig` dataclass, add `archetypes` field to `TierConfig` |
| `src/fantasy_sim/data/pff/tier_engine.py` | Add `_archetype_pools`, `_adot_boundaries` state; add `_classify_archetype()`; extend `_build_tier_pools()` for WR sub-pooling; extend `apply_tiers()` and `_apply_rookie_tiers()` for blend-time override |
| `config/defaults.yaml` | Add `archetypes` config under `pff.tier_engine` |
| `tests/test_data/test_pff/test_tier_engine.py` | 10 new tests (8 unit + 2 statistical) |
| `docs/pff-improvement-roadmap.md` | Mark item #4 complete with results |
| `CLAUDE.md` | Update PFF Intelligence Layer section |

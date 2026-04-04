# Team Context Layer — Tier Engine v2

**Date:** 2026-04-04
**Status:** Approved
**Roadmap item:** #2 (Team Context Layer)
**Baseline:** matchup+tier #20 (rank_corr +0.0376, wk_mae -0.306, szn_mae -4.331), 886 tests

## Summary

Adjust tier distributions for the player's own team context before blending with PBP data. Three season-level factors — team pass rate, OL run blocking quality, and QB quality — shift tier-level priors so that two players in the same tier project differently based on what team they play for.

Complements the matchup engine: team context = season-level ("what team does he play for"), matchup = week-level ("what defense is he facing").

## Motivation

Currently, two Tier 2 RBs on different teams get the same tier distributions. But a Tier 2 RB behind the league's best OL projects differently than one behind the worst. Similarly, a Tier 2 WR on a pass-heavy team with an elite QB gets more targets and catches at a higher rate than one on a run-heavy team with a mediocre QB.

The tier pool averages across all team contexts. Team context multipliers restore that lost signal.

## Architecture: Peer Engine (Approach A)

New `TeamContextEngine` in `data/pff/team_context.py`, owned by `GameContextBuilder` as a peer to `MatchupEngine` and `TierEngine`.

### Pipeline Ordering

```
1. Build team distributions + roster (from PBP)
2. Matchup engine: per-game factors from opposing D + own OL (week-level)
   → adjusts blended player models + turnover rates
3. Team context engine: compute per-team factors from own OL/QB/pass-rate (season-level)
4. Tier engine: assign tier → select distributions → apply team context → blend with PBP
   → adjusts tier prior before blending
5. Normalize shares
6. User overrides → normalize
```

Matchup and team context don't interfere: matchup adjusts the *final* player model (post-blend), team context adjusts the *tier prior* (pre-blend). Different application points, independent signals.

## Data Model

### TeamContext (in `models.py`)

```python
@dataclass
class TeamContext:
    """Season-level team environment factors for tier distribution adjustment.

    All factors centered on 1.0 (neutral).
    """
    pass_rate_factor: float = 1.0   # >1 = pass-heavy, <1 = run-heavy
    ol_run_block_factor: float = 1.0  # >1 = better OL, <1 = worse
    qb_quality_factor: float = 1.0   # >1 = more accurate QB, <1 = less
    ol_run_yards_scale: float = 10.0  # from config, packaged here for TierEngine
```

### TeamContextConfig (in `models.py`)

```python
@dataclass
class TeamContextConfig:
    """Configuration for the team context engine."""
    enabled: bool = True
    pass_rate_sensitivity: float = 0.08
    ol_run_sensitivity: float = 0.06
    qb_quality_sensitivity: float = 0.05
    factor_clamp: tuple[float, float] = (0.90, 1.10)
    min_games: int = 4
    ol_run_yards_scale: float = 10.0
```

- `factor_clamp` defaults to `[0.90, 1.10]` — same as matchup engine. At most +/-10% adjustment.
- `ol_run_yards_scale = 10.0` — a factor of 1.10 (max clamp) produces a +1.0 yard/carry shift. NFL data shows ~0.5-1.0 ypc difference between best and worst OL.
- `min_games = 4` — below this, blend with previous season (same as matchup engine).
- Sensitivity values are starting points for the sweep. Conservative intentionally.

## TeamContextEngine

**New file:** `src/fantasy_sim/data/pff/team_context.py`

### Constructor

```python
class TeamContextEngine:
    def __init__(self, config: TeamContextConfig, pff_loader: PffLoader):
        self._config = config
        self._loader = pff_loader
        self._cache: dict[str, pl.DataFrame] = {}
```

### `compute()` — Public Entry Point

```python
def compute(
    self, team: str, target_season: int, max_week: int,
    pbp: pl.DataFrame | None = None,
) -> TeamContext:
```

Computes three factors via internal methods, returns a `TeamContext` dataclass. Called once per team per game (cheap — two calls per simulated game).

### Factor 1: Team Pass Rate

- **Source:** PBP data filtered to `season == target_season` and `week < max_week`
- **Metric:** `count(play_type == "pass") / count(play_type in ["pass", "run"])` per team
- **Why PBP, not PFF:** Team pass rate is a play-calling frequency, not a quality measure. PFF doesn't offer a direct team-level pass rate metric. PBP is the authoritative source for play-calling distribution.
- **Aggregation:** Per-team pass rate → league avg/std across all teams in the window → z-score → `compute_factor()` → clamped factor
- **Early-season blend:** If team has < `min_games` weeks of PBP data in the target season, blend with previous season's pass rate. Linear ramp: `weight = current_games / min_games`. The PBP DataFrame passed to `compute()` includes all training seasons (loaded via `load_pbp(training_seasons)` in `GameContextBuilder`), so previous-season data is already available — no additional loading needed.

### Factor 2: OL Run Blocking Quality

- **Source:** PFF `offense_run_blocking` facet, filtered to `week < max_week`
- **Metric:** `grades_run_block`, snap-weighted by `snap_counts_run_block` per team
- **Why snap-weighted:** A team's starting LT (100% of snaps) matters more than a backup guard (10% of snaps). Snap weighting ensures starters dominate.
- **Aggregation:** Snap-weighted average per team → league avg/std across teams → z-score → `compute_factor()` → clamped factor
- **Early-season blend:** Same linear ramp as pass rate when team has < `min_games` games.

### Factor 3: QB Quality

- **Source:** PFF `passing_summary` facet, filtered to `week < max_week`
- **Metric:** `grades_pass`, snap-weighted by `passing_snaps` per team
- **Why snap-weighted:** Starting QB (95% of snaps) defines team passing quality. Backup mop-up snaps get minimal influence.
- **Aggregation:** Snap-weighted average across all QBs per team → league avg/std across teams → z-score → `compute_factor()` → clamped factor
- **Early-season blend:** Same linear ramp when team has < `min_games` games.

### Shared Infrastructure

- `_load_cached(facet, seasons)` — identical caching pattern to `MatchupEngine._load_cached()`
- Reuses `compute_factor()` from `matchup.py` directly (standalone function, no coupling)
- Each factor method handles its own rolling-window filtering and early-season blend

## Integration into TierEngine

### New Static Method

```python
@staticmethod
def apply_team_context(
    tier_dists: TierDistributions, ctx: TeamContext, position: str,
) -> None:
    """Adjust tier distributions for team environment before blending."""
    if position in ("WR", "TE"):
        tier_dists.target_share *= ctx.pass_rate_factor
        tier_dists.catch_rate *= ctx.qb_quality_factor
    elif position == "RB":
        if tier_dists.rushing_yards_dist is not None:
            shift = (ctx.ol_run_block_factor - 1.0) * ctx.ol_run_yards_scale
            tier_dists.rushing_yards_dist = tier_dists.rushing_yards_dist + shift
    # QB: no adjustments (consistent with QB skip rule in _blend_player)
```

### Modified apply_tiers()

New optional parameter `team_context: TeamContext | None = None`. Applied in the player loop after `select_distributions()` and before `_blend_player()`:

```python
assignment, tier_dists = result

# Apply team context to tier distributions before blending
if team_context is not None:
    self.apply_team_context(tier_dists, team_context, position)

reliability = self.compute_reliability(...)
self._blend_player(player, tier_dists, reliability, rng)
```

### Interaction with Reliability

- High reliability (veteran with lots of PBP data) → less tier influence → team context has less impact. Correct: veteran's PBP stats already reflect their team context.
- Low reliability (rookie, traded player) → more tier influence → team context matters more. Correct: new player needs the tier prior to reflect their new team environment.

### QB Skip Maintained

None of the three adjustments apply to QBs, consistent with `_blend_player()`'s existing QB skip rule.

### No Additional Clamping Needed

Factor clamping (0.90-1.10) prevents extreme values. Post-blending `_normalize_roster_shares()` ensures target_share and carry_share sum to 1.0.

## Integration into GameContextBuilder

### `__init__`

```python
self._team_context_engine = None
if (
    self._pff_config.enabled
    and self._pff_config.team_context.enabled
    and self._pff_loader
):
    from fantasy_sim.data.pff.team_context import TeamContextEngine
    self._team_context_engine = TeamContextEngine(
        self._pff_config.team_context, self._pff_loader
    )
    logger.info("PFF team context engine enabled")
```

### `build_game()`

Team context computed once per team, passed to `apply_tiers()`:

```python
home_ctx = None
away_ctx = None
if self._team_context_engine is not None and target_season and week:
    home_ctx = self._team_context_engine.compute(
        home_roster.team, target_season, week, pbp=pbp_df,
    )
    away_ctx = self._team_context_engine.compute(
        away_roster.team, target_season, week, pbp=pbp_df,
    )

self._tier_engine.apply_tiers(
    home_roster, self._pff_crosswalk, training_seasons,
    pbp=pbp_df, nfl_roster=nfl_roster_df,
    target_season=roster_season, team_context=home_ctx,
)
# ... same for away_roster with away_ctx
```

### Graceful Degradation

`target_season=None` or `week=None` (demo mode) → team context skipped, `apply_tiers()` receives `team_context=None`. Existing behavior unchanged.

## Configuration

### defaults.yaml

```yaml
pff:
  team_context:
    enabled: true
    pass_rate_sensitivity: 0.08
    ol_run_sensitivity: 0.06
    qb_quality_sensitivity: 0.05
    factor_clamp: [0.90, 1.10]
    min_games: 4
    ol_run_yards_scale: 10.0
```

### PffConfig Update

New field on `PffConfig`:

```python
team_context: TeamContextConfig = field(default_factory=TeamContextConfig)
```

### CLI

No new CLI flag. Team context is gated by `pff.team_context.enabled`, which follows the existing `--pff/--no-pff` master switch.

### A/B Harness

New modes in `validate_pff_signal.py`:

- `--mode team_context+tier` — tier + team context, no matchup (isolates team context signal vs tier-only baseline)
- `--mode team_context+tier+matchup` — full stack (likely production combo)

Note: there is no standalone `--mode team_context` — team context modifies `TierDistributions`, which requires the tier engine to be active. The minimum viable mode is `team_context+tier`.

`--config-override` supports `team_context` key:

```bash
uv run python scripts/validate_pff_signal.py \
  --mode team_context+tier+matchup --sims 50 \
  --config-override '{"team_context": {"pass_rate_sensitivity": 0.10}}' \
  --label "tc-high-pass-sens"
```

### Sweep Strategy

1. **Round 1 — Isolation:** `team_context+tier` vs `tier`-only baseline to isolate team context's incremental signal.
2. **Round 2 — Stacking:** `team_context+tier+matchup` vs current default (`tier+matchup` #20) to measure incremental lift on the full stack.
3. **Round 3 — Sensitivity sweep:** Vary each sensitivity independently, combine winners.

## Testing Strategy

### Unit Tests (~12 tests in `test_team_context.py`)

1. `TeamContext` dataclass defaults and construction
2. `TeamContextConfig` defaults and construction
3. `_compute_pass_rate_factor()` — mock PBP, known pass/run ratios, verify z-score → factor
4. `_compute_ol_run_factor()` — mock PFF `offense_run_blocking`, verify snap-weighted aggregation → factor. Backup lineman (10 snaps) doesn't skew team grade.
5. `_compute_qb_quality_factor()` — mock PFF `passing_summary`, starter (500 snaps) vs backup (20 snaps), verify snap-weighted average heavily favors starter
6. Rolling window — verify `week < max_week` filtering
7. Early-season blend — 0 games → previous season only; `min_games` games → current season only; 2 games → weighted blend
8. Factor clamping — extreme z-scores clamped to [0.90, 1.10]
9. Missing data — team not in data → neutral (1.0), empty PBP → neutral

### TierEngine Integration (~5 tests, extend `test_tier_engine.py`)

10. `apply_team_context()` — WR gets target_share + catch_rate adjusted, RB gets rushing_yards shifted, QB gets nothing
11. Pass-rate factor 1.10 → WR target_share increases 10%
12. OL factor 1.06, scale 10.0 → +0.6 yard shift on RB rushing_yards_dist
13. Neutral context (all 1.0) → no changes
14. `apply_tiers()` with `team_context=None` → backward compatible, unchanged behavior

### GameContextBuilder Integration (~3 tests, extend `test_game_context.py`)

15. Engine wiring — `team_context.enabled=True` creates engine, `False` does not
16. `build_game()` passes context — mock team context engine, verify apply_tiers receives TeamContext
17. Graceful degradation — `target_season=None` → team context skipped

**Estimated:** ~20 new tests, total ~906.

## Scope Decisions

### Included in v1

- Team pass rate → WR/TE target_share (PBP source)
- OL run blocking grade → RB rushing_yards_dist (PFF source)
- QB quality → WR/TE catch_rate (PFF source)
- Same-season rolling window with previous-season blend
- Snap-weighted aggregation for OL and QB data
- A/B harness modes and config-override support

### Explicitly excluded from v1

- **OL pass blocking → receiving yards** — double-counts with matchup engine's `ol_pass_block_factor`
- **Team run rate → RB carry_share** — carry_share is already directly measured from PBP; low marginal value
- **Air yards share adjustment** — player-role-within-passing-game, not team-volume metric
- **QB quality → receiving_yards_dist** — possible v2 follow-up (accurate QBs may enable more YAC)

## Files Changed

| File | Change |
|------|--------|
| `src/fantasy_sim/data/pff/team_context.py` | **NEW** — TeamContextEngine class |
| `src/fantasy_sim/data/pff/models.py` | Add TeamContext, TeamContextConfig, update PffConfig |
| `src/fantasy_sim/data/pff/tier_engine.py` | Add apply_team_context(), update apply_tiers() signature |
| `src/fantasy_sim/data/game_context.py` | Wire TeamContextEngine, pass context to apply_tiers() |
| `config/defaults.yaml` | Add pff.team_context section |
| `config/loader.py` | Parse team_context config into TeamContextConfig |
| `scripts/validate_pff_signal.py` | Add team_context modes to A/B harness |
| `tests/test_data/test_pff/test_team_context.py` | **NEW** — ~12 unit tests |
| `tests/test_data/test_pff/test_tier_engine.py` | ~5 integration tests |
| `tests/test_data/test_game_context.py` | ~3 integration tests |

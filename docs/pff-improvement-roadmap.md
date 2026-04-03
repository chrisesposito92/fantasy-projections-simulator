# PFF Improvement Roadmap

Status as of 2026-04-03:
- **tier-v1-4yr-3szn**: PASS (rank_corr +0.0255, season_mae -2.714) — first PASS ever
- **QB fix v2**: Only blend fumble_rate for QBs, skip all other fields + yards (committed, not yet A/B tested)

## Completed Fixes

1. **QB carry_share/scramble_rate skip** (v1 fix) — tier pool PBP aggregation doesn't separate designed runs from scrambles the way player_builder does. Skipping prevents undoing QB-specific calibration.

2. **QB fumble_rate-only blending** (v2 fix) — Extended to skip ALL scalar fields and yards distributions for QBs. target_share, air_yards_share, catch_rate are receiver/rusher concepts (irrelevant for QBs). rushing_yards_dist mixes mobile and pocket QBs within the same tier. Only fumble_rate is meaningful and safe to blend.

## Tuning Candidates (config-override sweeps)

### A. WR Secondary Grade
**Current:** `yprr` (yards per route run)
**Issue:** WR improved in 2023/2024 but slightly regressed in 2025 (-0.016). yprr may overcorrect for YAC-dependent receivers who have high catch rates but low yards-per-route-run.
**Try:**
```bash
uv run python scripts/validate_pff_signal.py --mode tier --sims 50 --training-years 4 \
  --seasons 2023 2024 2025 \
  --config-override '{"tier_engine": {"position_grades": {"WR": {"secondary": "avg_depth_of_target"}}}}' \
  --label "tier-wr-adot-secondary"
```
**Also try:** Disabling secondary interpolation entirely (set secondary to a non-existent column, falls back to 0.5 percentile = tier median for all WRs).

### B. Reliability Floor/Cap
**Current:** floor=0.15, cap=0.85 (15% tier weight minimum, 85% PBP weight maximum)
**Issue:** 15% tier influence on established 3-year players may be too much noise, especially for positions with thin tier pools.
**Try:**
```bash
# Less tier influence on established players
--config-override '{"tier_engine": {"reliability": {"floor": 0.10, "cap": 0.90}}}'

# More tier influence (if we think tiers are underweighted)
--config-override '{"tier_engine": {"reliability": {"floor": 0.20, "cap": 0.80}}}'
```

### C. Tier Count
**Current:** 5 tiers with cutoffs [0.85, 0.65, 0.40, 0.20]
**Issue:** Some positions may have too few player-seasons per tier, causing thin-tier merging. Fewer tiers = larger pools = more robust distributions.
**Try:** 4 tiers with cutoffs [0.80, 0.55, 0.30]:
```bash
--config-override '{"tier_engine": {"cutoffs": [0.80, 0.55, 0.30]}}'
```

### D. Blend Pool Size
**Current:** 500 samples
**Issue:** Might be too small or too large for the yards concatenation blend.
**Try:** 300 and 800:
```bash
--config-override '{"tier_engine": {"blend_pool_size": 300}}'
--config-override '{"tier_engine": {"blend_pool_size": 800}}'
```

### E. Additional Position Grades (3+ per position)

**Current:** 2 grades per position (primary → tier assignment, secondary → within-tier interpolation).
**Opportunity:** The design supports N grades per position, but `PositionGradeConfig` currently only has `primary` and `secondary` fields. Adding a tertiary grade would require extending the dataclass and interpolation logic — small code change, not just config.

**Candidates for a third grade:**

| Position | Current (primary, secondary) | Tertiary candidate | What it adds |
|----------|-----------------------------|--------------------|--------------|
| RB | grades_run, elusive_rating | yards_after_contact | Separates power backs from finesse backs within a tier |
| WR | grades_pass_route, yprr | avg_depth_of_target | Separates deep threats from slot receivers (addresses the WR archetype gap) |
| TE | grades_pass_route, recv_grade | yprr | Adds per-route production to the route quality + receiving grade combo |
| QB | grades_pass, accuracy_percent | (skip — QBs only blend fumble_rate) | N/A |

**Implementation approach:** Extend `PositionGradeConfig` with an optional `tertiary: str | None` field. If present, use it as a second interpolation dimension within the tier (2D interpolation on secondary × tertiary). Or simpler: average the secondary and tertiary percentiles into one composite within-tier percentile.

**Note:** This is a stepping stone toward the kNN approach (future v3), which naturally handles N dimensions without discrete interpolation logic.

### F. Position-Specific Reliability

**Current:** Same reliability formula for all positions.
**Opportunity:** QBs are more stable year-to-year (larger PBP samples, less role volatility). RBs are the most volatile (committee changes, injuries). Position-specific reliability params could improve per-position accuracy.
**Try:** Lower floor for QBs (0.05 — minimal tier influence), higher floor for RBs (0.20 — more tier influence):
```bash
# Would require a code change to support per-position reliability config
# For now, can approximate by adjusting max_games (higher = less tier influence)
```

## Sweep Strategy

Run each override independently against the baseline (tier-v2-qbfix-4yr) to isolate effects. Use the same params:
```bash
--mode tier --sims 50 --training-years 4 --seasons 2023 2024 2025
```

Priority order: B (reliability) > A (WR secondary) > E (additional grades) > C (tier count) > F (position-specific reliability) > D (pool size)

Reliability tuning has the broadest impact across all positions. WR secondary grade is targeted at the one position with inconsistent results. Tier count and pool size are refinements.

---

## PFF Feature Roadmap (ordered by expected backtest impact)

### 1. Re-enable Matchup Engine with Same-Season Rolling Window (HIGH)

**What:** The matchup engine was parked because cross-season defensive data (2022-2023 predicting 2024) didn't work. Fix: use same-season rolling data. For a week 8 game, use PFF defensive grades from weeks 1-7 of the current season. Early weeks (1-2) fall back to previous season.

**Why highest priority:** The tier engine answers "who is this player?" The matchup engine answers "who are they playing this week?" These are additive — tier fixes season-level rankings, matchup fixes weekly variance. Weekly MAE and calibration are the metrics this targets.

**Data required:** Already have it. PFF data for test seasons (2023-2025) includes week-by-week defensive grades. The existing `MatchupEngine` code (`matchup.py`) just needs the data strategy changed.

**Implementation:** Modify `MatchupEngine.compute()` to accept a `max_week` parameter. Filter PFF defensive data to `week <= max_week` for the current season. Reuse all existing factor computation and application code.

**PFF facets used:** defense_coverage, defense_pass_rush, defense_run, offense_pass_blocking, offense_run_blocking

### 2. Team Context Layer — Tier Engine v2 (MEDIUM-HIGH)

**What:** Adjust tier distributions for the player's own team context: team pass rate scales target volume, OL grade shifts rushing yards, QB quality scales WR/TE catch rate.

**Why:** A Tier 2 RB behind the league's best OL projects differently than one behind the worst. Currently, two Tier 2 RBs on different teams get the same distributions. Team context differentiates them.

**Data required:** offense_pass_blocking, offense_run_blocking (OL grades), passing_summary (QB quality). All already scraped.

**Implementation:** New step between tier selection and blending. After `select_distributions()` returns tier-level values, apply team context multipliers before blending with PBP. Complements the matchup engine: team context = season-level ("what team does he play for"), matchup = week-level ("what defense is he facing").

### 3. NCAA Tier Assignment for Rookies (MEDIUM)

**What:** Use college PFF grades (2022-2025 NCAA data) to place rookies directly into NFL talent tiers instead of relying on draft-capital archetypes from `rookie_builder.py`.

**Why:** Rookies have zero NFL PBP history, so the tier engine assigns them based on the 15% tier floor. An elite college route runner should be placed in Tier 1-2 with NFL-caliber distributions, regardless of draft round. ~50-60 rookies per season, disproportionately misranked.

**Data required:** NCAA PFF data at `~/.fantasy-sim/pff/processed/ncaa/`. Already scraped (2022-2025). Need NCAA-to-NFL player crosswalk via draft picks.

**Implementation:** Extend `TierEngine` with a `_assign_rookie_tier()` method. Map college grades to the NFL tier percentile scale (college grades are on the same 0-100 PFF scale but distribution differs). Weight by draft capital — a 1st-round pick's college grades carry more than a 5th-rounder's.

### 4. Depth-of-Target Archetypes Within Tiers (MEDIUM)

**What:** Use the `receiving_depth` PFF facet to create sub-pools within WR tiers based on target depth profile (deep threat vs slot vs possession).

**Why:** Currently, all Tier 2 WRs share one yards distribution pool. A deep-threat WR and a slot WR in the same tier have genuinely different yards-per-catch distributions. This is the one case where secondary grade interpolation on yards distributions makes sense — but via archetype sub-pooling, not continuous interpolation.

**Data required:** receiving_depth facet (already scraped). Contains per-player breakdowns by short/medium/deep targets.

**Implementation:** Cluster WRs within each tier into 2-3 archetypes by depth profile. Assign each player to an archetype. Use the archetype's sub-pool for yards distributions instead of the full tier pool. Only applies to WR — other positions don't have the same depth variance.

### 5. Coverage Matchup Adjustments (LOW for backtest / HIGH for weekly)

**What:** Use `defense_coverage_matchup` data for receiver-vs-defender matchup adjustments. When a WR1 faces a shadow CB, adjust target_share and catch_rate for that specific game.

**Why:** The most granular matchup signal PFF offers. Less useful for season-level backtesting (matchup effects average out over 17 games) but very high value for weekly projection accuracy.

**Data required:** defense_coverage_matchup facet (already scraped). Contains receiver-defender pairing data.

**Implementation:** Per-game overlay on top of the matchup engine. After the team-level defensive adjustment, apply a player-specific modifier based on the expected CB matchup. Requires mapping WR alignment to likely CB assignment.

### 6. Kicker/DST from PFF Grades (LOW)

**What:** Use `field_goal_summary` and defensive facets to improve kicker and DST projections. Currently kickers are placeholder models and DST uses team-level aggregates.

**Why:** Small component of overall backtest metrics, but easy wins. PFF kicker grades + accuracy by distance could replace the placeholder. Defensive grades could improve DST scoring projections.

**Data required:** field_goal_summary, defense_summary (both already scraped).

**Implementation:** Extend `build_kicker_model()` to use PFF FG accuracy data by distance bucket. Extend DST projections with PFF defensive grades for sack rate, INT rate, fumble recovery rate.

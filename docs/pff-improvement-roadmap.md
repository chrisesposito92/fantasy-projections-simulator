# PFF Improvement Roadmap

Status as of 2026-04-04:
- **tc+matchup-no-passrate** (#24): PASS (rank_corr +0.0381, wk_mae -0.260, szn_mae -4.309, calibr -0.0125) — current default
- Tier config: reliability_floor=0.20, reliability_cap=0.80, WR secondary=_disabled
- Team context config: pass_rate_sensitivity=0.0 (disabled), ol_run_sensitivity=0.06, qb_quality_sensitivity=0.05, clamp [0.90, 1.10], min_games=4
- Matchup config: medium sensitivities (0.06-0.075), clamp [0.90, 1.10], min_games=4
- Same-season rolling window: week < max_week filter, linear ramp blend with previous season
- Sweep rounds 1+2 (tier) + round 3 (matchup) + round 4 (team context) complete (see results below)

## Completed Fixes

1. **QB carry_share/scramble_rate skip** (v1 fix) — tier pool PBP aggregation doesn't separate designed runs from scrambles the way player_builder does. Skipping prevents undoing QB-specific calibration.

2. **QB fumble_rate-only blending** (v2 fix) — Extended to skip ALL scalar fields and yards distributions for QBs. target_share, air_yards_share, catch_rate are receiver/rusher concepts (irrelevant for QBs). rushing_yards_dist mixes mobile and pocket QBs within the same tier. Only fumble_rate is meaningful and safe to blend.

## Tuning Candidates (config-override sweeps)

### A. WR Secondary Grade — SWEPT
**Result:** Disabling WR secondary interpolation is best. ADOT is better than yprr but still worse than disabled.
- **#12 tier-wr-no-secondary**: rank_corr +0.0363 (new best), szn_mae -3.130 — **WINNER**
- **#14 tier-wr-adot-secondary**: rank_corr +0.0340, szn_mae -3.304 — solid but not best
- yprr within-tier interpolation was adding noise for WRs, not signal

### B. Reliability Floor/Cap — SWEPT
**Result:** More tier influence is better. Tight (0.20/0.80) beats loose (0.10/0.90) on MAE; both beat baseline.
- **#10 tier-reliability-tight (0.20/0.80)**: rank_corr +0.0335, szn_mae -3.341 (best MAE) — **WINNER**
- **#11 tier-reliability-loose (0.10/0.90)**: rank_corr +0.0328, szn_mae -2.822 — worse than baseline MAE

### C. Tier Count — SWEPT, RULED OUT
**Result:** 4 tiers is worse than 5 tiers on rank_corr. Keep 5 tiers.
- **#13 tier-4tiers**: rank_corr +0.0287 (below baseline +0.0304) — not adopted

### D. Blend Pool Size — NOT YET TESTED
**Current:** 500 samples. Lower priority given strong results from A+B sweeps.

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

Base command for all sweeps:
```bash
uv run python scripts/validate_pff_signal.py --mode tier --sims 50 --training-years 4 --seasons 2023 2024 2025
```

### Round 1 Results (2026-04-03)

Each candidate tested independently against baseline #9 (tier-v2-qbfix-4yr):

| # | Config | rank_corr | wk_mae | szn_mae | calibr |
|---|--------|-----------|--------|---------|--------|
| 9 | baseline (current) | +0.0304 | -0.227 | -2.900 | -0.0085 |
| 12 | WR secondary disabled | **+0.0363** | -0.235 | -3.130 | -0.0086 |
| 14 | WR secondary=ADOT | +0.0340 | -0.237 | -3.304 | -0.0076 |
| 10 | reliability tight (0.20/0.80) | +0.0335 | **-0.243** | **-3.341** | **-0.0092** |
| 11 | reliability loose (0.10/0.90) | +0.0328 | -0.207 | -2.822 | -0.0082 |
| 13 | 4 tiers | +0.0287 | -0.214 | -2.926 | -0.0088 |

### Round 2: Combo Sweep (2026-04-03)

Combined tight reliability + WR no-secondary:

| # | Config | rank_corr | wk_mae | szn_mae | calibr |
|---|--------|-----------|--------|---------|--------|
| 15 | tight + WR no-sec | +0.0353 | **-0.254** | -3.201 | -0.0086 |

Best weekly MAE, second-best rank_corr. Adopted as new default (#15 → defaults.yaml).

### Remaining Candidates

Priority: E (additional grades) > F (position-specific reliability) > D (pool size)

---

## PFF Feature Roadmap (ordered by expected backtest impact)

### 1. ~~Re-enable Matchup Engine with Same-Season Rolling Window~~ — COMPLETE

**Result:** matchup+tier-med-sens (#20) is new default. rank_corr +0.0376, wk_mae -0.306, szn_mae -4.331.

Same-season rolling window with early-season blend (linear ramp, min_games=4). Medium sensitivities (0.06-0.075) won the sweep — best MAE with negligible rank_corr trade-off vs conservative. High sensitivities showed diminishing returns. Wide clamp didn't help.

Sweep results (all matchup+tier, 4yr training, 3 seasons):

| # | Config | rank_corr | wk_mae | szn_mae | calibr |
|---|--------|-----------|--------|---------|--------|
| 18 | conservative (0.04-0.05) | +0.0384 | -0.267 | -4.086 | -0.0118 |
| 19 | high (0.08-0.10) | +0.0370 | -0.268 | -4.169 | -0.0123 |
| **20** | **medium (0.06-0.075)** | **+0.0376** | **-0.306** | **-4.331** | -0.0108 |
| 21 | wide clamp (0.85-1.15) | +0.0360 | -0.282 | -4.235 | -0.0122 |

### 2. ~~Team Context Layer — Tier Engine v2~~ — COMPLETE

**Result:** tc+matchup-no-passrate (#24) is new default. rank_corr +0.0381, wk_mae -0.260, szn_mae -4.309, calibr -0.0125.

Three factors implemented, one disabled after sweep. **OL run blocking → RB rushing_yards** and **QB quality → WR/TE catch_rate** show consistent per-position lift (RB +0.05-0.10, TE +0.02-0.09 across all 3 seasons). **Pass rate → WR/TE target_share** was disabled (sensitivity=0.0) — it diluted rank_corr because target_share is already well-measured from PBP data.

Sweep results (all tc+tier+matchup, 4yr training, 3 seasons):

| # | Config | rank_corr | wk_mae | szn_mae | calibr |
|---|--------|-----------|--------|---------|--------|
| 22 | tc+tier default (all 3 factors) | +0.0319 | -0.231 | -3.016 | -0.0095 |
| 23 | tc+tier+matchup default | +0.0328 | -0.285 | -4.307 | -0.0122 |
| **24** | **no pass rate, default sens** | **+0.0381** | -0.260 | -4.309 | **-0.0125** |
| 25 | no pass rate, high OL (0.09) | +0.0354 | -0.269 | -4.288 | -0.0124 |
| 26 | no pass rate, high QB (0.08) | +0.0376 | -0.264 | -4.338 | -0.0126 |

### 3. ~~NCAA Tier Assignment for Rookies~~ — COMPLETE

**Result:** NCAA grades via `pff_id` bridge place rookies into NFL talent tiers. 85/85 drafted, 143/144 total rookies matched for 2025 class. Grade drives tier assignment (direct comparison against NFL boundaries — distributions are close: NCAA WR route mean=62.2 vs NFL mean=63.6). Draft capital modulates blend confidence (1st round=1.0 full tier influence, UDFA=0.4 partial). `TierEngine._apply_rookie_tiers()` processes players skipped by the NFL PFF crosswalk. Players without NCAA PFF data fall back to existing `rookie_builder.py` archetypes. Config in `defaults.yaml` under `pff.tier_engine.ncaa_rookie`. A/B harness modes: `--mode ncaa_rookie+tier`, `--mode ncaa_rookie+tier+matchup`.

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

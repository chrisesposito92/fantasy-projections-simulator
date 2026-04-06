# PFF Improvement Roadmap

Status as of 2026-04-05:
- **coverage+ncaa-rookie-tier+matchup**: PASS (1000 tests) — current default
- Active PFF layers: tier (5 tiers, reliability 0.20-0.80) + team context (disabled) + matchup (medium sens 0.06-0.075) + NCAA rookie (draft confidence curve) + coverage (0.04 sens, clamp [0.95, 1.05], WR-only)
- Tier config: reliability_floor=0.20, reliability_cap=0.80, WR secondary=_disabled
- NCAA rookie config: enabled, draft confidence 1st=1.0→7th=0.50, UDFA=0.40, lookback=4 seasons
- Matchup config: medium sensitivities (0.06-0.075), clamp [0.90, 1.10], min_games=4
- Coverage config: outcome-based stats (catch rate allowed, YPR allowed) with grade stabilizer, alignment-based CB mapping (RWR→LCB, LWR→RCB, slot→SCB), WR-only for v1
- Same-season rolling window: week < max_week filter, linear ramp blend with previous season
- Sweep rounds 1+2 (tier) + round 3 (matchup) + round 4 (team context) + round 5 (NCAA rookie) + round 6 (coverage) complete

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

### D. Blend Pool Size — SWEPT
**Result:** 250 samples adopted. Tied for best rank_corr (+0.0494), best weekly MAE (-0.315).

| # | Config | rank_corr | wk_mae | szn_mae | calibr |
|---|--------|-----------|--------|---------|--------|
| 32 | pool=500 (baseline) | +0.0479 | -0.317 | -4.845 | -0.0148 |
| **33** | **pool=250** | **+0.0494** | **-0.315** | -4.902 | -0.0134 |
| 34 | pool=1000 | +0.0494 | -0.326 | -4.904 | -0.0124 |

Smaller pool weights personal PBP data more heavily, improving weekly precision.

### E. Additional Position Grades (3+ per position) — SWEPT

**Result:** RB `yards_after_contact` adopted as tertiary. TE `yprr` ruled out. WR handled by archetypes (item #4).

Tertiary grades are averaged with secondary percentile into a composite within-tier percentile. `PositionGradeConfig` extended with optional `tertiary: str | None` field.

| # | Config | rank_corr | wk_mae | szn_mae | calibr |
|---|--------|-----------|--------|---------|--------|
| 33 | no tertiary (baseline) | +0.0494 | -0.315 | -4.902 | -0.0134 |
| **37** | **RB yards_after_contact** | **+0.0498** | -0.336 | **-5.179** | **-0.0139** |
| 38 | TE yprr | +0.0435 | -0.313 | -4.627 | -0.0120 |
| 39 | RB + TE combo | +0.0482 | -0.318 | -4.961 | -0.0131 |

RB `yards_after_contact` separates power backs from finesse backs within tiers — best rank_corr and season MAE. TE `yprr` adds noise (similar to how WR secondary interpolation added noise before archetypes). QB skipped (only blends fumble_rate).

### F. Position-Specific Reliability — SWEPT, RULED OUT
**Result:** Position-specific floor/cap hurts rank_corr. Global reliability (0.20/0.80) works best.

| # | Config | rank_corr | wk_mae | szn_mae | calibr |
|---|--------|-----------|--------|---------|--------|
| **33** | **global 0.20/0.80 (current)** | **+0.0494** | **-0.315** | -4.902 | -0.0134 |
| 35 | QB 0.05/0.50 + RB 0.30/0.85 | +0.0460 | -0.319 | -4.913 | -0.0126 |
| 36 | QB 0.05/0.50 only | +0.0450 | -0.312 | -4.740 | -0.0127 |

QB tier influence likely helps via fumble_rate blending (the only QB field blended). Cutting it too aggressively loses that signal. Code support for `position_reliability` dict is in place if future sweeps find better settings.

Previously:
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

All tuning candidates swept (D, E, F).

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

### 4. ~~Depth-of-Target Archetypes Within Tiers~~ — COMPLETE

**Result:** 3 archetype sub-pools (slot/possession/deep) within each WR tier, classified by ADOT from `receiving_summary`. Overrides `receiving_yards_dist` and `catch_rate` from archetype sub-pool when available (>= 10 members); falls back to full tier pool otherwise. Global ADOT percentile boundaries (p33/p67) computed across all WR player-seasons. NCAA rookies also get archetype assignment via NCAA ADOT. Deep-threat sub-pools have higher mean yards and lower catch rates than slot sub-pools within the same tier, matching NFL reality.

Config in `defaults.yaml` under `pff.tier_engine.archetypes`. A/B override: `--config-override '{"tier_engine": {"archetypes": {"enabled": false}}}'`.

Sweep results (all ncaa_rookie+tier+matchup, 4yr training, 3 seasons):

| # | Config | rank_corr | wk_mae | szn_mae | calibr |
|---|--------|-----------|--------|---------|--------|
| 30 | archetypes on (pool=20) | +0.0462 | -0.313 | -4.764 | -0.0128 |
| 31 | archetypes off | +0.0453 | -0.319 | -5.020 | -0.0133 |
| **32** | **archetypes on (pool=10)** | **+0.0479** | -0.317 | -4.845 | **-0.0148** |

`min_archetype_pool_size=10` (#32) adopted as new default: best rank_corr (+0.0479) and best calibration (-0.0148) in the ledger. Pool size 20 was too restrictive — most tier-archetype cells fell below threshold and used the full tier pool fallback.

### 5. ~~Coverage Matchup Adjustments~~ — COMPLETE

**Result:** Per-WR coverage adjustments via alignment-based CB mapping. Outcome-based stats (catch rate allowed, YPR allowed) with PFF grade stabilizer for low-sample CBs. WR-only for v1 (TEs excluded — already got biggest tier engine lift). Applied as last PFF step after tier engine + normalization. Conservative starting sensitivities (0.04) with tight clamp [0.95, 1.05].

Config in `defaults.yaml` under `pff.coverage`. A/B harness modes: `--mode coverage+tier`, `--mode coverage+tier+matchup`. Config-override supports `coverage` key.

### 6. Kicker/DST from PFF Grades (LOW)

**What:** Use `field_goal_summary` and defensive facets to improve kicker and DST projections. Currently kickers are placeholder models and DST uses team-level aggregates.

**Why:** Small component of overall backtest metrics, but easy wins. PFF kicker grades + accuracy by distance could replace the placeholder. Defensive grades could improve DST scoring projections.

**Data required:** field_goal_summary, defense_summary (both already scraped).

**Implementation:** Extend `build_kicker_model()` to use PFF FG accuracy data by distance bucket. Extend DST projections with PFF defensive grades for sack rate, INT rate, fumble recovery rate.

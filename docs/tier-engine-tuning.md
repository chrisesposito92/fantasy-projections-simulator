# Tier Engine Tuning — Next Steps

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

## Sweep Strategy

Run each override independently against the baseline (tier-v2-qbfix-4yr) to isolate effects. Use the same params:
```bash
--mode tier --sims 50 --training-years 4 --seasons 2023 2024 2025
```

Priority order: B (reliability) > A (WR secondary) > C (tier count) > D (pool size)

Reliability tuning has the broadest impact across all positions. WR secondary grade is targeted at the one position with inconsistent results. Tier count and pool size are refinements.

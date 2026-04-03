# PFF Synthetic Distribution Generation

## Concept

Use PFF talent grades to generate full PBP-like statistical distributions for players with thin or misleading play-by-play samples, rather than just nudging the mean via the talent stabilizer.

## Problem

The current talent stabilizer adjusts point estimates (catch_rate, yards distribution means) but the underlying distributions still come from PBP data. This breaks down for:

- **Rookies**: 0-4 NFL games → archetype distributions (generic)
- **Traded players**: PBP distributions from old scheme/QB/OL
- **Role changers**: WR3 promoted to WR1 mid-season → thin high-usage data
- **Injury returners**: Pre-injury PBP may not reflect post-injury talent

For these players, we're simulating from distributions that don't represent their current situation. Nudging the mean helps, but the shape (variance, skew, tails) stays wrong.

## Proposed Approach

Build a mapping from PFF grade profiles to full statistical distributions:

### Phase 1: Grade-to-Distribution Templates

For each position, cluster NFL players by PFF grade profile and extract their PBP distributions:

```
PFF Profile Cluster → Distribution Template
─────────────────────────────────────────────
Elite WR (route_grade > 85, yprr > 2.0)
  → receiving_yards_dist from top-10 WR PBP outcomes
  → catch_rate from top-10 WR historical range
  → target_share range based on snap% + route_grade

Average WR (route_grade 60-75, yprr 1.2-1.8)
  → receiving_yards_dist from WR15-30 PBP outcomes
  → catch_rate from that tier
  ...
```

This gives us empirical distributions for each talent tier, preserving the shape/variance/tails that matter for simulation.

### Phase 2: Continuous Interpolation

Instead of discrete clusters, interpolate between distribution templates using PFF grades as continuous features:

```python
def generate_distribution(pff_grades, position):
    # Find k-nearest players by PFF grade profile
    # Weight their PBP distributions by grade similarity
    # Return blended distribution
```

This produces a unique distribution for each player, scaled by their specific PFF profile.

### Phase 3: Context-Aware Generation

Layer team context onto the PFF-derived distributions:

- Team pass rate → scales target volume
- OL grade → shifts rushing yards distribution
- QB accuracy → scales catch rate
- Offensive scheme (from PFF formation data) → adjusts route tree and usage patterns

## Use Cases

### Weekly Stat Line Projections

With proper distributions, the simulator produces full projected stat lines per week:

```
Nico Collins (Week 5 vs IND)
  Targets: 8.2 (6-11)     Receptions: 5.8 (4-8)
  Rec Yards: 78.4 (42-128) Rec TDs: 0.6 (0-2)
  Carries: 0.3 (0-1)       Rush Yards: 2.1 (0-8)
  PPR: 18.6 (9.2-31.4)     Boom%: 22%  Bust%: 15%
```

Every stat is a distribution, not a point estimate. This enables:

### Prop Bet Coverage

Full stat distributions map directly to prop bet lines:

```
Nico Collins Receiving Yards: O/U 72.5
  Simulator: P(over) = 56.2%
  Edge: +6.2% (line implies 50%)

Nico Collins Receptions: O/U 5.5
  Simulator: P(over) = 52.8%

Nico Collins Anytime TD: Yes -110
  Simulator: P(TD) = 48.3%
  Implied: 52.4%
  Edge: -4.1% (no bet)
```

The simulator already produces per-player box scores with all these stats — prop coverage is output formatting, not a modeling change.

### Required Output Changes

The `PlayerBoxScore` already tracks all relevant stats. To support props:
1. Store per-sim stat lines (not just means) — `build_detailed_projections()` already does percentiles
2. Add prop-line comparison: `P(stat > line)` for any stat/threshold
3. Weekly output format with full stat distributions

## Data Requirements

- PFF NFL data (already have 2022-2025, 21 facets)
- PFF NCAA data (already have 2022-2025 for rookie profiles)
- nflverse PBP (already have, used for distribution extraction)
- Enough seasons to build robust grade→distribution mappings (3+ seasons = ~1500 player-seasons)

## Implementation Order

1. **Grade-to-distribution templates** — cluster players by PFF profile, extract per-cluster distributions
2. **Integration point** — in `player_builder.py`, replace archetype blending for thin-sample players with PFF-derived distributions
3. **Continuous interpolation** — kNN-based blending for smooth grade→distribution mapping
4. **Prop bet output** — format simulator output for prop line comparison
5. **Context-aware generation** — layer team/scheme effects onto PFF-derived distributions

## Relationship to Current Architecture

This builds on top of the existing talent stabilizer, not replacing it:

- **Current flow**: PBP distributions → talent stabilizer nudges means → simulation
- **New flow**: PFF grades → generate full distributions (for thin-sample players) → talent stabilizer fine-tunes → simulation
- **Thick-sample players** (established starters with 2+ seasons of PBP): current flow unchanged
- **Thin-sample players** (rookies, traded, role changes): PFF-generated distributions replace archetype/thin-PBP distributions

The talent stabilizer still runs on PFF-generated distributions — it validates that the generated distribution aligns with whatever PBP data IS available.

## Open Questions

- How many PFF profile clusters per position? Start with 3-5 tiers, expand if data supports it
- Should distributions be generated per-season or per-career? Per-season captures development
- How to handle PFF grade inconsistencies across seasons (grading calibration drift)?
- Minimum PFF sample size to trust the grade-to-distribution mapping?

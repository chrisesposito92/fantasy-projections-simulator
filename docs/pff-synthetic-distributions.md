# PFF Talent-Tier Distribution Engine

## Problem

The current pipeline builds player models from PBP history: "Pollard had 280 carries for 1000 yards last year, so project similar." This produces obviously wrong rankings because **PBP volume reflects role and opportunity, not talent:**

- Tony Pollard → RB5 (got volume because Tennessee had nobody else)
- Jerry Jeudy → WR2 (high targets from a bad QB throwing short)
- Raheem Mostert → above Jahmyr Gibbs (one elite scheme-dependent season vs a more talented player in a timeshare)
- Rachaad White → RB7 (volume-inflated by game script)
- Jakobi Meyers → WR3 (target hog on a bad offense)

The talent stabilizer (mean-nudging) can't fix this — shifting a catch rate by +0.008 doesn't change a player's projected tier. The distributions themselves (shape, variance, volume assumptions) are still built from misleading PBP data.

## Root Cause

Two separate issues compound:

1. **Efficiency distributions** (yards/catch, yards/carry, catch_rate): Built from personal PBP history. A scheme-dependent player's PBP efficiency looks elite even when PFF talent grades say average. Current stabilizer nudges these means but doesn't change the distribution shape.

2. **Usage rates** (carry_share, target_share): Taken directly from PBP. This is the bigger problem. A player who got 30% carry share because his team had no alternatives projects 30% again, even when PFF grades say he's not good enough to hold that role. The stabilizer currently touches target_share via route_grade, but the effect is too small.

## Proposed Architecture: Talent-Tier Distribution Selection

Instead of building distributions from a player's OWN PBP history and nudging, use PFF talent grades to SELECT which tier of distributions to draw from.

### Current flow (PBP-first)
```
Player's PBP history → personal distributions → nudge means with PFF → simulate
```

### Proposed flow (PFF-informed selection)
```
Player's PFF grades → identify talent tier → select tier distributions from PBP pool
                                           → weight with personal PBP where reliable
                                           → layer team context → simulate
```

The key difference: **PFF grades drive distribution SELECTION, PBP provides the distribution SHAPE for each tier.**

## How It Works

### Step 1: Build Talent-Tier Distribution Pool

For each position, use 3+ seasons of PFF + PBP data to build a mapping:

```
PFF Grade Profile → PBP Distribution Pool
──────────────────────────────────────────

RB Tier 1 (PFF rush_grade > 80, elusive_rating top 15%)
  carry_share: 0.55-0.75 (bellcow role)
  rushing_yards_dist: sampled from tier-1 RB PBP outcomes
  catch_rate: from tier-1 RB receiving
  Expected finish: RB1-RB8

RB Tier 3 (PFF rush_grade 60-70, elusive_rating 30th-60th pct)
  carry_share: 0.30-0.50 (committee or weak starter)
  rushing_yards_dist: sampled from tier-3 RB PBP outcomes
  catch_rate: from tier-3 RB receiving
  Expected finish: RB15-RB25

WR Tier 1 (route_grade > 85, yprr > 2.0)
  target_share: 0.22-0.30 (alpha WR)
  receiving_yards_dist: from tier-1 WR PBP outcomes
  Expected finish: WR1-WR10
```

Each tier's distributions come from ACTUAL PBP outcomes of players at that talent level — so the shape, variance, and tails are empirically grounded.

### Step 2: Player-Specific Tier Assignment

For each player, compute their talent tier from PFF grades:

```python
def assign_talent_tier(player_pff_grades: dict, position: str) -> TalentTier:
    # Option A: Discrete tiers (simpler)
    # Map PFF composite to tier 1-5 based on percentile cutoffs

    # Option B: Continuous (better)
    # Find k-nearest players in PFF grade space
    # Weight their PBP distributions by grade similarity
    # Returns a blended distribution unique to this player
```

### Step 3: Weight with Personal PBP

Don't throw away personal PBP entirely — blend it with the tier distribution based on how RELIABLE the personal data is:

```python
def compute_pbp_reliability(player) -> float:
    """How much to trust this player's personal PBP data.

    High reliability: same team, same role, 2+ seasons, stable coaching
    Low reliability: new team, role change, 1 season, coaching change
    """
    factors = {
        'same_team': 1.0 if not changed_teams else 0.3,
        'sample_size': min(games_played / 32, 1.0),  # 2 full seasons = full trust
        'role_stability': target_share_variance_across_weeks,
        'scheme_stability': same_oc_flag,
    }
    return weighted_average(factors)

# Final distribution
reliability = compute_pbp_reliability(player)
final_dist = reliability * personal_pbp_dist + (1 - reliability) * tier_dist
```

This means:
- **Davante Adams (stable, 3 years)**: 85% personal PBP, 15% tier distribution
- **Tony Pollard (new team, scheme change)**: 30% personal PBP, 70% tier distribution
- **Rookie (0 NFL games)**: 0% personal PBP, 100% tier distribution (from NCAA priors)

### Step 4: Layer Team Context

After tier selection, adjust for team-specific factors:

- **Team pass rate** → scales target volume (an elite WR on a run-heavy team gets fewer targets than one on a pass-heavy team)
- **OL grade** → shifts rushing yards distribution (a tier-2 RB behind the best OL plays like a tier-1)
- **QB quality** → scales catch rate, air yards, TD rate
- **Coaching scheme** → PFF formation/tendency data adjusts usage patterns

## What This Fixes

| Problem | Current | With Tier Engine |
|---------|---------|-----------------|
| Pollard RB5 | PBP says 280 carries | PFF says tier-3 talent → RB15-20 |
| Jeudy WR2 | PBP says high targets | PFF says average route grade → WR20-30 |
| Mostert > Gibbs | PBP says elite 2023 | PFF says scheme-dependent vs elite talent |
| Volume-inflated players | Repeat last year's volume | Project volume for their talent tier |
| Aging players | PBP still shows peak | PFF grades decline before volume does |

## Data Requirements

- PFF NFL data: already have 2020-2025, 21 facets
- PFF NCAA data: already have 2020-2025 for rookie tier assignment
- nflverse PBP: already have, provides distribution pools per tier
- nflverse rosters: already have, for team change detection
- 3+ seasons needed for robust tier→distribution mappings (~1500 player-seasons)

## Implementation Order

1. **Tier definition + clustering** — Define talent tiers per position from PFF grade profiles. Start with 4-5 tiers per position using percentile cutoffs on composite PFF grades. Validate tiers against actual fantasy finishes.

2. **Distribution pool extraction** — For each tier, extract PBP distributions (carry_share, target_share, yards dists, catch_rate, TD rate) from all players who graded into that tier. These become the tier templates.

3. **PBP reliability scoring** — Compute per-player reliability (team stability, sample size, role stability). This determines the blend weight between personal PBP and tier distributions.

4. **Integration into player_builder.py** — Replace current `_assemble_models()` flow: instead of personal PBP → player model, use PFF tier → tier distribution → blend with personal PBP → player model.

5. **Team context layer** — Adjust tier distributions for team-specific factors (pass rate, OL, QB quality). This replaces and supersedes the current schedule-adjusted talent approach.

6. **Continuous interpolation** — Graduate from discrete tiers to kNN-based continuous blending for smoother, player-specific distributions.

## Relationship to Current Architecture

This **replaces** the talent stabilizer for efficiency and usage parameters, but the sim engine stays exactly the same:

- `player_builder.py` changes: distribution source shifts from personal-PBP-only to PFF-tier-blended
- `talent.py` simplifies: no more mean-nudging (the tier engine handles it at the distribution level)
- `game_sim.py`, `play_resolver.py`, `monte_carlo.py`: **unchanged** — they still sample from distributions, just better ones
- `game_context.py`: wires the tier engine into the pipeline where the talent stabilizer currently sits

The matchup engine (parked) could eventually feed into Step 4 as per-game team context adjustments.

## Open Questions

- How many tiers per position? Start with 4-5, validate against historical fantasy finishes
- Which PFF grades matter most per position? Need feature importance analysis
- How to handle multi-position players (RB/WR flex types)?
- How to handle mid-season role changes (monitor weekly PFF grades)?
- Should tiers be re-computed weekly or locked at season start?
- How to validate: compare tier-engine rankings vs current rankings vs actual finishes for 2023-2024 seasons

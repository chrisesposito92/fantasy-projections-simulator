# Brainstorming Handoff: Next Big Accuracy Improvement

## What to do

Start a brainstorming session (`/superpowers:brainstorming`) for the next major accuracy improvement to the fantasy projections simulator. The goal is to find the next "usage.snap" — a single change that gives a step-change lift in projection accuracy, particularly weekly metrics.

## Current State

### Engine Stack (all in defaults.yaml)
- **PFF**: tier_engine, matchup, coverage, kicker, dst_baseline (all enabled)
- **Weather**: wind, temp, precipitation (enabled)
- **Vegas**: ITT pace, spread pass_rate, player props (all enabled)
- **Usage**: snap blend (enabled, CPOE enabled but stubbed), NGS (disabled), route_rate (disabled)
- **Disabled**: team_context, talent stabilizer

### Latest A/B Results (from unified validate.py, 50 sims, 3 seasons)
```
Baseline (bare vs defaults):
  SEASONAL rank_corr: +0.1502 delta (absolute: QB 0.93, RB 0.87, WR 0.85, TE 0.82)
  WEEKLY rank_corr:   QB +0.035, RB +0.102, WR +0.105, TE +0.064
  Weekly MAE:         -0.606 (from ~5.3 to ~4.7)
  Season MAE:         -10.5 (from ~44.5 to ~34.0)
```

### Key Insight from Last Phase
Usage snap counts gave a **massive** +0.15 rank_corr lift (up from ~0.03 with previous best). The insight: fixing "who is actually playing and how much" matters far more than fine-tuning matchup factors. The equivalent question for weekly accuracy is: what systematic signal are we missing that drives week-to-week variance?

### Where the Gaps Are (from codebase exploration)

**Weekly rank_corr (0.38-0.57) has the most room to grow.** Seasonal (0.83-0.93) is strong.

1. **Player-level TD tendency (CRITICAL)** — The simulation uses a uniform TD gate per play (pass: 55%-15% by yard line, run: 35%-8%). No player-level TD probability. Kelce in the red zone gets the same gate as a backup TE. TDs are the single biggest source of weekly fantasy variance (~12 points per TD in PPR). Fixing "who actually scores" is the weekly equivalent of fixing "who actually plays."

2. **CPOE is stubbed (MODERATE)** — Config says `cpoe.enabled: true` but `_compute_cpoe_rolling()` returns an empty dict. Never applied. This is a 4-week rolling QB accuracy signal that would modulate WR catch rates weekly.

3. **Game script / garbage time (HIGH but HARD)** — The sim tracks score differential in GameStateBucket and adjusts pass/run split, but doesn't model: garbage time (backup usage), pace changes from blowouts, or desperation target concentration. Blowouts are the biggest weekly correlation killers.

4. **NGS separation/cushion (TESTED, HURT)** — Already built and tested. **Brought numbers DOWN** when enabled. Don't re-test without a hypothesis for why it hurt (likely: separation data is noisy at small samples, cushion directionality is questionable).

5. **Route rate (UNTESTED)** — Built but never A/B tested. Targets-per-route z-score → target_share multiplier. Worth a quick test.

6. **Team context engine (DISABLED)** — Season-level team environment (pass rate, OL quality, QB quality). Was disabled — check A/B results in the old ledger to see why.

### Testing Infrastructure
New unified A/B script makes testing easy:
```bash
# Test any change against current defaults
uv run python scripts/validate.py --sims 50 --set <key>=<value> --label "test-name"

# Marginal impact of a change
uv run python scripts/validate.py --sims 50 --baseline defaults --set <key>=<value> --label "test-name"

# View history
uv run python scripts/validate.py --show-ledger
```

Bare baseline is cached — repeat runs take ~60% of the time.

### Constraints
- A/B validation before merging any change
- Must maintain 1414+ test suite
- PFF premium data available; open to free sources; will consider paid if justified
- 2025 season is hold-out (reserved for final validation)
- User preference: quality/accuracy over simplicity

### Files to Read
- `config/defaults.yaml` — all engine configs and current settings
- `src/fantasy_sim/engine/play_resolver.py` — TD gate logic, play resolution
- `src/fantasy_sim/data/usage/engine.py` — snap blend, CPOE (stubbed), NGS, route_rate
- `src/fantasy_sim/data/player_builder.py` — how player models are built
- `src/fantasy_sim/validation/` — A/B testing infrastructure
- `docs/AB-TESTING.md` — how to run A/B tests
- `CLAUDE.md` — full project reference

### Recommendation
Start with the **player-level TD tendency** design. It's the highest-impact opportunity that parallels the "snap counts" insight: snap counts fixed volume estimation, TD tendency would fix scoring estimation. Both attack the same problem — the simulation is good at modeling play-by-play mechanics but bad at modeling individual player tendencies that drive fantasy points.

Second priority: get CPOE actually working (it's half-built). Third: quick A/B test of route_rate since it's free to try.

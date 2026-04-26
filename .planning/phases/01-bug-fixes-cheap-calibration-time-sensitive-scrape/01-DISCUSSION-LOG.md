# Phase 1: Bug Fixes, Cheap Calibration & Time-Sensitive Scrape - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in `01-CONTEXT.md` — this log preserves the alternatives considered.

**Date:** 2026-04-26
**Phase:** 01-bug-fixes-cheap-calibration-time-sensitive-scrape
**Areas discussed:** KS-21 Odds API scrape strategy; RZ + clamping bug stack (KS-01/04/15); Remaining bug + calibration retunes (KS-03/05/06/07/29/32); Sequencing, A/B cadence, promotion bar

---

## Gray Area Selection

| Option | Description | Selected |
|--------|-------------|----------|
| Odds API scrape strategy (KS-21) | Bookmakers, snapshot timing/frequency, alt-line market coverage, historical-coverage probe + fallback plan, parquet cache schema, credit pacing. | ✓ |
| RZ + clamping bug stack (KS-01, KS-04, KS-15) | 3 interlocking fixes touch play_resolver.py:21-49 / 264-284 / 421-446. Each has variants. Choice ripples through all three. | ✓ |
| Remaining bug + calibration retunes (KS-03, KS-05, KS-06, KS-07, KS-29, KS-32) | Per-item variant picks. | ✓ |
| Sequencing, A/B cadence, promotion bar | Per-KS commits vs theme-batched; ledger label scheme; promotion bar for 'small' expected KS gains. | ✓ |

**User's choice:** All four areas selected.

---

## KS-21 Odds API Scrape Strategy

### Q1: Which sportsbooks should we query for alt-line markets?

| Option | Description | Selected |
|--------|-------------|----------|
| DK + FD + Caesars (Recommended) | 3 books — covers ~80% of US market consensus, consistent with PFF props sourcing. Modest credit budget, redundant for de-vig pairing. Fits ~5M tier comfortably for 2022-2024 × 18 weeks. | ✓ |
| Top 6-8 US books | DK, FD, Caesars, BetMGM, PointsBet, BetRivers (~6 books). Better consensus but ~2x credit cost. | |
| All available US books | Maximum coverage but credit-heavy and may exceed remaining tier on historical backfill. | |
| Match what The Odds API returns by default | Use API's default region selection (us, us2). Less control but minimum decisions. | |

**User's choice:** DK + FD + Caesars (Recommended)

### Q2: What snapshot timing for each game?

| Option | Description | Selected |
|--------|-------------|----------|
| Close-line only (Recommended) | Single snapshot ~1hr before kickoff per game. Most-informative single point for KS validation; minimum credit cost. | |
| Open + close | Two snapshots per game (Tuesday open + ~1hr pre-kick close). Captures line movement but doubles credit cost. | ✓ |
| Daily snapshots throughout week | 5-7 snapshots per game across the week. Best line movement data but credit-prohibitive over 3 seasons. | |
| Whatever is cheapest given remaining tier | Compute credit budget first, then maximize coverage within budget. | |

**User's choice:** Open + close (with reframing — close-line for 8 main markets already exists at `/Users/chrisesposito/.fantasy-sim/market-history/processed/player_markets_*_close_core8.parquet` for 2023-2025; "no historical pre-2023")
**Notes:** User noted no historical player props exist in The Odds API prior to 2023; existing close-line cache for 8 main markets is at `~/.fantasy-sim/market-history/processed/player_markets_*_close_core8.parquet`.

### Q3: Which markets to scrape?

| Option | Description | Selected |
|--------|-------------|----------|
| ROADMAP's 6 alt-line markets exactly (Recommended) | The 6 listed in success criterion #5. | |
| 6 alt-line + anytime_td + pass_tds | Adds player_anytime_td and player_pass_tds (regular line, not alt). | |
| 6 alt-line + main lines (player_pass_yds, etc.) | Scrape standard mean lines alongside alt lines for cross-check (de-vig sanity). | ✓ |
| Maximum useful coverage (alt + main + TDs) | Scrape everything reasonable for offensive skill positions. | |

**User's choice:** 6 alt-line + main lines (player_pass_yds, etc.)

### Q4: How to handle the 'historical alt-line coverage may be enterprise-only' risk?

| Option | Description | Selected |
|--------|-------------|----------|
| Probe first, scope-down if reduced (Recommended) | Day 1: hit 1 game in each of 2022/2023/2024 to confirm alt-line availability. | |
| Front-load all 2024 first, then 2023, then 2022 | Skip the probe; assume coverage exists. | |
| Two-pass: scrape main lines first (cheap), then alt lines | Main lines confirmed available historically. | |
| Skip historical entirely; only scrape 2025-2026 going forward | Conservative — avoid risk of wasted credits. | ✓ (reframed) |

**User's choice:** Confirmed pre-2023 props historically not available in The Odds API; existing 2023-2025 main-line scrape proved reliable.
**Notes:** User has already validated the historical-availability boundary. Phase 1 success criterion #5 ("2022-2024 weeks 1-18") relaxed to "2023-2024 + 2025 to current" with documented rationale.

### Q5 (follow-up): What does 'open' snapshot mean for the new scrape?

| Option | Description | Selected |
|--------|-------------|----------|
| Tuesday 12pm ET (line release) (Recommended) | Standard 'opening line' — most US books post NFL props Tuesday around lunchtime. | ✓ |
| Wednesday morning (overnight settle) | After overnight market activity but before mid-week info (injury reports). | |
| Game day -24h | Symmetric with close (-1h). | |
| Skip 'open' — close-only is enough | Defer to close-only and revisit if engine needs movement data. | |

**User's choice:** Tuesday 12pm ET (line release) (Recommended)

### Q6 (follow-up): For 'open' snapshots, which markets to scrape?

| Option | Description | Selected |
|--------|-------------|----------|
| New alt-line markets only (6 markets) (Recommended) | Open + close for the 6 alt-line markets only. | |
| Alt-line + main-line for all 14 markets | Add open snapshots for both new alt-lines AND the existing 8 main-line markets. | ✓ |
| Just alt-line close, add main-line open in a separate sweep later | Most cautious. | |

**User's choice:** Alt-line + main-line for all 14 markets

### Q7 (follow-up): Coverage scope given confirmed no-pre-2023 historical data?

| Option | Description | Selected |
|--------|-------------|----------|
| 2023 + 2024 weeks 1-18 + 2025 to current (Recommended) | Full available historical for backtest validation. | |
| 2024 weeks 1-18 + 2025 to current only | Skip 2023 alt-lines. | |
| All years available, capped by remaining credit budget | Maximize coverage; pause if credits drop below 1M. | |

**User's choice:** 2023, 2024, 2025 regular seasons (matches existing main-line coverage)

### Q8 (follow-up): Parquet schema for the new alt-line snapshots?

| Option | Description | Selected |
|--------|-------------|----------|
| Reuse existing player_markets schema (Recommended) | Existing schema already supports multi-line per market via repeated rows. | ✓ |
| New schema with alt_lines as a list column | More compact but breaks compatibility. | |
| Defer schema choice to planning phase | Capture as a planner decision. | |

**User's choice:** Reuse existing player_markets schema (Recommended)

---

## RZ + clamping bug stack (KS-01, KS-04, KS-15)

### Q1: Which KS-01 variant for the `_tackled_short()` RZ TD-gate fix?

| Option | Description | Selected |
|--------|-------------|----------|
| Cleanest: `min(yard_line - 1, sampled_yards)` (Recommended) | Replace _tackled_short() rewrite everywhere. | ✓ |
| Calibrated: 1-yard-short only at goal-line (yard_line ≤ 3) | Mirrors real NFL goal-line dynamics. | |
| Both: cleanest first, evaluate calibrated as a follow-up | Two-phase approach. | |

**User's choice:** Cleanest: `min(yard_line - 1, sampled_yards)` (Recommended)

### Q2: Which KS-04 CATCH_YARDS_BOOST variant?

| Option | Description | Selected |
|--------|-------------|----------|
| Best: condition boost on _clamp_yards firing (Recommended) | If raw_yards > yard_line, apply +1.5-2.0; else +0. | ✓ |
| Reasonable: increase to CATCH_YARDS_BOOST = 2 outside RZ | Simple constant bump. | |
| Quick: drop the `if state.yard_line > 20` gate | Apply +1 in RZ too. | |
| All three sequenced: best-then-reasonable-then-quick comparison | Test all three in isolation A/B. | |

**User's choice:** Best: condition boost on _clamp_yards firing (Recommended)

### Q3: After KS-15 (clamping fix), what happens to CATCH_YARDS_BOOST?

| Option | Description | Selected |
|--------|-------------|----------|
| Drop to 0 in same change (Recommended) | KS-15 obviates the boost's original justification. | ✓ |
| Keep KS-04's tuned value; let KS-15 ride on top | Boost may help with sub-clamping shortfalls. | |
| Decide based on KS-15 A/B results | Ship KS-15 with boost held; A/B; drop in follow-up if equal/better. | |

**User's choice:** Drop to 0 in same change (Recommended)

### Q4: Test strategy for these 3 fixes given the existing 1,200+ test suite?

| Option | Description | Selected |
|--------|-------------|----------|
| TDD: write failing tests first per HYPOTHESES targets, then fix (Recommended) | 6-10 unit tests per KS + regression tests for PASS_TD_GATE calibration. | ✓ |
| Fix first, run full suite, add targeted tests for any broken cases | Faster; relies on existing coverage. | |
| TDD for KS-15 only; lighter for KS-01/KS-04 | KS-15 has highest double-count risk. | |

**User's choice:** TDD: write failing tests first per HYPOTHESES targets, then fix (Recommended)

### Q5 (follow-up): Given KS-15 will drop CATCH_YARDS_BOOST to 0, what's the path through KS-04?

| Option | Description | Selected |
|--------|-------------|----------|
| Ship KS-04 as intermediate, then KS-15 obviates it (Recommended) | KS-01 → KS-04 → measure → KS-15 → measure. Captures intermediate KS gain. | ✓ |
| KS-04 magnitude: pick 1.5 first, sweep [1.0, 1.5, 2.0] only if hard floor at risk | Skip the sweep unless borderline. | |
| Skip KS-04; jump KS-01 → KS-15 directly with boost→0 | Saves an A/B round; risks losing KS-04 fallback. | |
| Ship KS-04 (condition-on-clamp +1.5), skip the sweep, then KS-15 | Pragmatic middle ground. | |

**User's choice:** Ship KS-04 as intermediate, then KS-15 obviates it (Recommended)

### Q6 (follow-up): KS-04 boost magnitude when condition triggers?

| Option | Description | Selected |
|--------|-------------|----------|
| +1.5 (HYPOTHESES low-end of 1.5-2.0) (Recommended) | Conservative; minimizes overshoot risk. | ✓ |
| +2.0 (HYPOTHESES high-end) | Aggressive; max intermediate KS gain. | |
| Pre-fit by sweeping {1.0, 1.5, 2.0} in plan-phase | Most thorough; +2 A/B runs. | |

**User's choice:** +1.5 (HYPOTHESES low-end of 1.5-2.0) (Recommended)

---

## Remaining bug + calibration retunes (KS-03, KS-05, KS-06, KS-07, KS-29, KS-32)

### Q1: KS-05 props bug fix scope (props_engine.py:43, 248)?

| Option | Description | Selected |
|--------|-------------|----------|
| Both: constant fix + magnitude bug fix (Recommended) | _DEFAULT_TEAM_PASS_YDS 230→240 + _apply_recv_yds magnitude fix. | |
| All three: constant + magnitude + pipeline-derived team pass yards | Full fix per HYPOTHESES long-term recommendation. | ✓ |
| Magnitude bug only; constant left for follow-up | Magnitude bug is the bigger error. | |

**User's choice:** All three: constant + magnitude + pipeline-derived team pass yards

### Q2: KS-06 backup-receiver fallback scope (play_resolver.py:268, preprocessor.py)?

| Option | Description | Selected |
|--------|-------------|----------|
| All 3 changes per HYPOTHESES (Recommended) | Filter completed plays + integer fallback retune + lower MIN_PLAYER_PLAYS. | ✓ |
| Just the integer fallback (option 2) | Smallest change. | |
| Integer fallback + MIN_PLAYER_PLAYS only; skip preprocessor filter | Avoids preprocessor refactor. | |

**User's choice:** All 3 changes per HYPOTHESES (Recommended)

### Q3: How to handle the calibration-conditional items (KS-29 team_context, KS-32 clock runoff)?

| Option | Description | Selected |
|--------|-------------|----------|
| KS-29: enable + sensitivity 0.05; KS-32: measure-then-decide (Recommended) | KS-29 enable + standard sensitivity; KS-32 only retune if validate_passing.py shows attempts low. | ✓ |
| Both proactive: enable + retune both up front | Faster but tunes against moving target. | |
| Both conditional: measure first for both | Most cautious. | |

**User's choice:** KS-29: enable + sensitivity 0.05; KS-32: measure-then-decide (Recommended)

### Q4: KS-29 pass_rate_sensitivity — single value or sweep?

| Option | Description | Selected |
|--------|-------------|----------|
| Single value: 0.05 (Recommended) | HYPOTHESES recommendation. | |
| Sweep {0.03, 0.05, 0.08} | Pre-test three; pick best. | ✓ |
| Defer choice to planner per HYPOTHESES rationale | Planner picks. | |

**User's choice:** Sweep {0.03, 0.05, 0.08}

---

## Sequencing, A/B cadence, promotion bar

### Q1: Commit cadence for the 9 KS code changes?

| Option | Description | Selected |
|--------|-------------|----------|
| One commit per KS-XX, in dependency order (Recommended) | Each KS lands as own commit. Clean bisect, attribution, rollback. | ✓ |
| Theme-batched (Theme A bugs in one commit, Theme E retunes in another) | 2 commits total; faster but harder attribution. | |
| Hybrid: bugs individually, calibration retunes batched | KS-01/03/05/06/15 each as own commit; KS-04/07/29/32 batched. | |

**User's choice:** One commit per KS-XX, in dependency order (Recommended)

### Q2: Ledger label scheme for A/B runs?

| Option | Description | Selected |
|--------|-------------|----------|
| `p1.ksXX.bare` + `p1.ksXX.full` per KS (Recommended) | Clean phase + KS prefix. | ✓ |
| Add season suffix: `p1.ksXX.s2024.bare` | More granular. | |
| Defer label scheme to plan-phase | Planner picks. | |

**User's choice:** `p1.ksXX.bare` + `p1.ksXX.full` per KS (Recommended)

### Q3: Promotion bar for items HYPOTHESES marks 'small' expected KS gain?

| Option | Description | Selected |
|--------|-------------|----------|
| Ship if hard floor passes AND any non-regression KS (Recommended) | Per `feedback_quality_over_simplicity.md`: small wins compound. | ✓ |
| Ship only if KS delta ≤ -0.005 absolute on primary target | Stricter threshold. | |
| Ship all that pass floor, batch-validate stack at end of phase | End-of-phase aggregate with walk-back option. | |

**User's choice:** Ship if hard floor passes AND any non-regression KS (Recommended)

### Q4: Validation seasons for per-KS A/B runs?

| Option | Description | Selected |
|--------|-------------|----------|
| All 2022-2024, 200 sims/season (Recommended) | Matches PROJECT.md baseline + ROADMAP success criteria. | ✓ |
| 2024 hold-out only, 200 sims (faster per run) | Single season; faster. | |
| 2024 quick sweep at 50 sims; full 200 × 2022-2024 only on promotion-candidates | Cheap screen pass first. | |

**User's choice:** All 2022-2024, 200 sims/season (Recommended)

---

## Mid-Discussion Rule Update

After CONTEXT.md was drafted, user updated the A/B execution rule:

> "i saw you mention that i will be running the A/B tests, i know your memories say to do that, but i ahev changed my mind"
> "you cvan run them yourself"

**Effect:** Memory `feedback_ab_manual.md` reversed (2026-04-26). Agents now run `scripts/validate.py`, `scripts/validate_passing.py`, and other A/B harness scripts directly. CONTEXT.md decisions D-21, D-29, D-32 updated; specifics section updated; canonical_refs validation infrastructure section updated.

---

## Claude's Discretion

- Exact ordering of KS-03/05/06/07 within the post-KS-01 / pre-KS-15 window — planner picks based on file-touch overlap.
- Specific test-case enumeration for TDD on KS-01/04/15 — planner derives from HYPOTHESES.md mechanism descriptions.
- Per-team rolling-mean window length for KS-05 D-18 — planner picks based on existing pipeline window conventions.
- KS-21 scrape execution sequencing — opportunistic, no formal dependency.
- Specific snapshot timestamps within "Tuesday 12pm ET" — timezone handling, DST transitions.

## Deferred Ideas

- Per-team rolling-mean source for KS-05 (D-18) plumbing complexity → fall back to constant-only fix and defer architectural plumbing to Phase 2 if needed
- KS-04 magnitude sweep → only revisit if KS-04 A/B shows borderline floor
- KS-01 calibrated goal-line variant → revisit only if post-Phase-1 measurements show goal-line distortion
- Open-snapshot timing follow-up (Tuesday vs Wednesday)
- KS-21 alt-line market expansion (additional markets like `player_pass_tds_alternate`, kicker markets)
- End-of-phase Phase 1 vs Phase 0 aggregate ledger entry → captured as D-32; final comparison happens in Phase 5 wrap-up

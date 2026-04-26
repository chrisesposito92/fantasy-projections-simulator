# Phase 1: Bug Fixes, Cheap Calibration & Time-Sensitive Scrape - Context

**Gathered:** 2026-04-26
**Replanned:** 2026-04-26 (Cycle 1 — incorporates Codex `01-REVIEWS.md` HIGH-1..HIGH-4 + MEDIUM-1..MEDIUM-4)
**Re-replanned (Cycle 3):** 2026-04-26 — incorporates Codex `01-REVIEWS.md` Cycle 2 findings: 3 NEW HIGHs (per-KS code-change A/B is no-op; `bare_config_dict()` incomplete; Plan 11 mean-bias not in ledger schema) + 2 partial-resolves of Cycle-1 HIGH-2/HIGH-3 (RESEARCH.md staleness reconciled with CONTEXT/Plan 09)
**Status:** Ready for planning (post-Cycle-3 revision)

<domain>
## Phase Boundary

Ship 9 confirmed bug fixes / cheap calibration retunes (KS-01, KS-03, KS-04, KS-05, KS-06, KS-07, KS-15, KS-29, KS-32) AND complete the Odds API alternate-line scrape sub-deliverable for KS-21. All code changes A/B-validated through `scripts/validate.py` per the hard floor (rank_corr regression ≤ 0.005 AND MAE regression ≤ 0.05). The KS-21 *requirement* (engine integration) is mapped to Phase 4 — only the data-acquisition portion runs here, time-sensitive against the ~4.93M-of-5M Odds API credit tier with ~2 weeks remaining.

Out of scope for this phase (belongs in later phases):
- KS-09 per-stat `residual_calibration` extension (Phase 2)
- KS-08 `dynamic_blend` simulator-weight floor (Phase 2)
- KS-02 / KS-16 / KS-17 / KS-18 PFF Phase 5 slice activations (Phase 3)
- KS-19 / KS-20 PFF cached-data engines (Phase 4)
- KS-21 Odds API alt-line CDF engine (Phase 4) — only the scrape happens here

</domain>

<decisions>
## Implementation Decisions

### KS-21 Odds API Alternate-Line Scrape (Phase 1 sub-deliverable)

- **D-01:** Books = DraftKings + FanDuel + Caesars (3-book consensus). Sufficient for de-vig pairing; fits within remaining ~4.93M credit tier.
- **D-02:** **REVISED 2026-04-26 (HIGH-3):** "Earlier" snapshot = whatever The Odds API returns as `previous_timestamp` relative to the existing gameday-noon UTC events crawl (`events_inventory.build_request_window` at `events_inventory.py:89-96`). The current pipeline does NOT store a real Tuesday 12pm ET line-release marker, so the earlier-snapshot label honestly describes itself as "prior" not "open". Phase 4 expectations updated to consume "prior-snapshot" lines, not "Tuesday 12pm ET line release". A future follow-up may extend the event inventory to capture a true Tuesday marker; out of scope for Phase 1's time-sensitive scrape.
- **D-03:** Scrape scope = prior + close snapshots for **all 14 markets** (the existing 8 main-line markets in `DEFAULT_PROP_MARKETS` + 6 new alt-line markets). Existing 8 main-line `close_core8` cache stays untouched; this scrape adds prior-line versions of the 8 main lines AND prior + close for the 6 new alt-line markets.
- **D-04:** New alt-line markets = `player_pass_yds_alternate`, `player_reception_yds_alternate`, `player_rush_yds_alternate`, `player_pass_attempts_alternate`, `player_receptions_alternate`, `player_rush_attempts_alternate` (6 markets, matches ROADMAP success criterion #5).
- **D-05:** Coverage = 2023, 2024, 2025 regular seasons (matches existing main-line coverage). The Odds API has no historical player props pre-2023 — Phase 1 success criterion #5 ("2022-2024 weeks 1-18") is hereby relaxed to "2023-2024 regular season + 2025 to current" with no further investigation needed (confirmed by user from prior scrape work).
- **D-06:** **REVISED 2026-04-26 (HIGH-3):** Snapshot labels = `prior_core8`, `prior_alt6`, `close_alt6` (and existing `close_core8` stays as-is). The `prior_*` prefix replaces the misleading `open_*` prefix from the original plan, and explicitly identifies these as "API previous_timestamp relative to gameday-noon UTC crawl". Phase 4 engine integration must reference `prior_*` labels.
- **D-07:** Parquet schema = reuse existing `player_markets_*` schema unchanged (`season, week, event_id, schedule_game_id, snapshot_label, snapshot_timestamp, market_key, player_name, player_name_normalized, home_team, away_team, bookmaker_count, line, line_stddev, over_price, under_price, yes_price, implied_prob`). Multi-line alt-line markets are encoded as repeated rows (one row per (player, market_key, line) tuple). Existing `props_backfill.py` machinery handles this without code changes.
- **D-08:** **REVISED 2026-04-26 (HIGH-2):** Pipeline = (1) `scripts/fetch_market_history_props.py` writes raw JSON to `~/.fantasy-sim/market-history/raw/props/{season}/{snapshot_label}/{event_id}.json` via `save_raw_props_snapshot()` (`props_backfill.py:139`); (2) `scripts/build_market_history_player_markets.py` reads the JSON cache and writes processed parquet at `~/.fantasy-sim/market-history/processed/player_markets_{season}_{snapshot_label}.parquet` via `build_player_market_signals_for_season()` (`player_markets.py:190`). Both scripts must run; the original CONTEXT incorrectly assumed `fetch_market_history_props.py` produced parquet directly. KS-21 plan adds (a) the alt-line market tuple, (b) raw fetch loop, (c) processed-build loop, (d) schema/timing verification.

### KS-01 RZ TD-Gate Truncation Fix (`play_resolver.py:279-284, 421-424`)

- **D-09:** Variant = **Cleanest**: replace `_tackled_short()` rewrite with `yards = max(1, min(yard_line - 1, sampled_yards_pre_clamp))` everywhere when RZ TD-gate fails. Preserves the sampled distribution; denies TD by reserving 1 yard short.
- **D-10:** No "calibrated goal-line-only" variant for v1 of the fix. If subsequent measurements show goal-line distortion, revisit as a follow-up — not blocking Phase 1.

### KS-04 CATCH_YARDS_BOOST Retune (`play_resolver.py:32, 264-265`)

- **D-11:** Variant = **Best**: condition boost on `_clamp_yards` actually firing. If `raw_yards > yard_line` (i.e., the un-clamped sample would have been clamped), apply boost; else no boost. Tied to actual mechanism per HYPOTHESES KS-04.
- **D-12:** Boost magnitude when condition triggers = **+1.5** (HYPOTHESES low-end of 1.5-2.0). No sweep — ship at 1.5 directly. Conservative; minimizes overshoot risk.
- **D-13:** Path = ship KS-04 (boost +1.5 conditional) as an intermediate, even though KS-15 will obviate it. This captures KS-04's intermediate KS gain in the ledger and provides a fallback if KS-15 fails the hard floor.

### KS-15 Field-Position Clamping Fix (`play_resolver.py:32, 265-274, 302-321, 392-410, 437-446`)

- **D-14:** Approach = restore un-clamped sample as `min(yard_line, sample)` for yards while using the un-clamped sample for the TD probability gate. Per HYPOTHESES KS-15: "convert truncated samples into TDs rather than truncating to goal line." Bug-fix-class change.
- **D-15:** In the same change, drop `CATCH_YARDS_BOOST` to 0. Per HYPOTHESES, KS-15 obviates the boost's original justification (band-aid for clamping-induced under-counting). KS-04's tuned value becomes archival.
- **D-15b (added 2026-04-26 — MEDIUM-4):** Apply the same `min(yard_line, sample)` + would-be-TD detection pattern to the legacy non-roster paths in `_resolve_pass` (lines 302-321) and `_resolve_run` (lines 392-410). The validation harness instantiates rosters in all production paths, but keeping two divergent clamping semantics in the same module is a foot-gun. New tests must cover both roster and non-roster code paths. The rewrite re-uses the same `would_be_td = (state.yard_line - raw_yards) <= 0` detection used in the roster path.

### KS-03 Matchup/Coverage Yard Anchor Fix (`game_context.py:534-544, 546-558, 591`)

- **D-16:** Replace hardcoded `* 10.0` with `* float(np.mean(player.outcomes.<dist>))` in:
  - `_apply_matchup` receiving branch (lines 534-544) → uses `receiving_yards_dist`
  - `_apply_coverage` (line 591) → uses `receiving_yards_dist`
  - **D-16b (added 2026-04-26 — MEDIUM-1):** `_apply_matchup` rushing branch (lines 546-558) → uses `rushing_yards_dist`. The original D-16 stated "receiving yards only" but the existing Plan 03 already widens scope to rushing. Codex review flagged this as scope creep; resolution is to formally widen KS-03's hypothesis to cover all three call sites consistently. RB rush_yards is already a Phase 1 success criterion (#3) so the attribution is appropriate. The mirror pattern (`_apply_weather` at `game_context.py:701-712`) is identical for both rushing and receiving branches.
- All 3 sites mirror the correct reference implementation in `_apply_weather` at `game_context.py:701-712`. Single-mechanism fix; no variant choice.

### KS-05 Props Engine Bug Fixes (`props_engine.py:43, 248, 380-409`)

- **D-17:** Scope = **all three** sub-fixes per HYPOTHESES KS-05:
  - Fix `_DEFAULT_TEAM_PASS_YDS = 230.0 → 240.0` (constant retune)
  - Fix `_apply_recv_yds` magnitude bug at line 248: `historical_season_yds = dist_mean * catches_per_game * games_played` (currently `dist_mean * games_played`)
  - Long-term: replace `_DEFAULT_TEAM_PASS_YDS` constant with per-team rolling mean from pipeline (full architectural fix, not a temporary patch)
- **D-18:** Per-team rolling mean source = pipeline's existing per-team PBP stats (already cached). Plumb through `props_engine.apply()` as an argument when available; constant fallback for missing teams.

### KS-06 Backup Receiver Fallback Fixes (`play_resolver.py:268-271`, `preprocessor.py`, `player_builder.py:11`)

- **D-19:** Scope = **all 3 changes** per HYPOTHESES KS-06:
  - Filter team-bucket distribution to completed plays only (`preprocessor.py`)
  - Change integer fallback `rng.integers(3, 12) → rng.integers(5, 18)` (mean ~11, matches NFL ~11.5)
  - Lower `MIN_PLAYER_PLAYS = 5 → 3` (gives more players their own dist)

### KS-07 Positional RZ Catch Rate (`play_resolver.py:60`, `player_builder.py:520`)

- **D-20:** Replace single `RZ_CATCH_RATE_MODIFIER = 0.92` with positional `RZ_CATCH_RATE_MODIFIERS = {"WR": 0.92, "TE": 0.95, "RB": 0.85}`. Single-mechanism fix; no variant choice.

### KS-29 Re-enable `pff.team_context` (`config/defaults.yaml:103-110`, `tier_engine.py:1196-1215`)

- **D-21:** Set `pff.team_context.enabled=true` and add A/B sweep on `pass_rate_sensitivity ∈ {0.03, 0.05, 0.08}`. Plan stages the three configs; agent runs all three A/B (per updated 2026-04-26 rule); pick the best within hard floor.
- **D-22:** Coordinate with `feedback_qb_calibration.md` discipline: team_context must NOT blend QB `carry_share` / `scramble_rate` / yards.

### KS-32 Clock Runoff Calibration (`play_resolver.py:21-24`, `scripts/validate_passing.py:24`)

- **D-23:** **Measure-then-decide**: run `scripts/validate_passing.py` against the post-KS-01-bug-fixes baseline (i.e., after KS-01/KS-04/KS-15/KS-03/KS-05/KS-06/KS-07 ship and stack). Only reduce `CLOCK_PASS_INCOMPLETE` from 5 → 3 if the validation shows pass attempts low (32-33 instead of 35-36). Avoid retuning on a moving target.
- **D-24:** If the measurement does not motivate a change, document KS-32 as "measured, no change" in the ledger. The KS-XX requirement is "delivered" via the documented measurement (per REQUIREMENTS.md "delivered" definition: implemented + tested + ledgered + promotion decision documented).

### Sequencing, Commit Cadence & A/B Cadence

- **D-25:** **REVISED 2026-04-26 (MEDIUM-2):** Commit cadence = **one promotion-state commit per KS-XX, in dependency order**. Within a KS plan, intermediate task commits (RED test, GREEN implementation, ledger record) are normal git practice for clean bisect within a plan. The FINAL commit per KS plan is the "promotion-state" commit using a standardized message format: `feat(01-NN): KS-XX [PROMOTED|SHIPPED-NO-OP|BLOCKED|SHIPPED-OFF|MEASURED-NO-CHANGE] — <short summary>`. The ledger entry name (`p1.ksXX.bare`/`.full`) and the PROMOTION-NOTES section header are tied to this final commit. Bisect/rollback at KS-XX granularity is achieved by reverting the promotion commit + intermediate commits via `git revert` of the commit range, or `git reset` to the promotion commit's parent. The original "HEAD~3 after Plan 01" claim was already broken by Plan 09 running parallel in wave 1; this revision replaces it with a per-plan promotion-commit anchor that is stable regardless of wave parallelism.
- **D-26:** Dependency-mandatory order: **KS-01 → KS-04 → KS-15** (RZ stack). Other items can ship in any order after KS-01 (which clears the largest mean-bias mechanism). Suggested overall order: KS-01 → KS-04 → KS-03 → KS-05 → KS-06 → KS-07 → KS-15 → KS-29 → KS-32 (measure). KS-21 scrape runs in parallel with the code changes — no dependency conflict.
- **D-27:** Ledger label scheme = `p1.ksXX.bare` (true bare-baseline isolation: bare engines + KS-XX only — see D-29) and `p1.ksXX.full` (defaults + KS-XX, full-stack overlay) per change. KS-29 sweep adds `p1.ks29.s003.bare`, `p1.ks29.s005.bare`, `p1.ks29.s008.bare` (and `.full` versions). KS-32 measurement adds `p1.ks32.measure` if no change is needed; otherwise normal `p1.ks32.bare`/`.full`. **NEW Phase-0 baseline labels (D-32b):** `phase0.baseline.full` (Arm A = bare, Arm B = current pre-Phase-1 promoted defaults) and `phase0.baseline.bare` (Arm A = bare, Arm B = bare — sanity-check no-op) pinned in Wave 0 BEFORE any KS work begins.
- **D-28:** Validation set = **all 2022-2024, 200 sims/season**, PPR scoring. Matches PROJECT.md baseline evidence + ROADMAP success criteria + existing `decision_s200` artifact convention. KS-21 historical limited to 2023+, but that doesn't affect 2022 stat-level validation for code-side changes.
- **D-29:** **REVISED 2026-04-26 (HIGH-1):** A/B mode per change = **true isolation + full-stack overlay** (per `feedback_ab_testing_approach.md`).
  - The current `scripts/validate.py` has a documented mismatch: `--baseline bare` makes Arm A bare but Arm B = `apply_overrides(defaults, overrides)`, NOT `apply_overrides(bare, overrides)`. So `--baseline bare --set X.enabled=true` actually compares `(bare) vs (defaults + X)`, which is contaminated by all default-on engines. This was the basis for HIGH-1 in the Codex review.
  - **Resolution (Plan 00 implements this):** Extend `scripts/validate.py` with a new `--arm-b-base {defaults,bare}` flag (default: `defaults`, preserves backward compatibility). When `--arm-b-base bare`, Arm B starts from `build_bare_engine_configs()` and applies `--set` overrides on top. Then **true isolation** is `--baseline bare --arm-b-base bare --set <KS-X overrides>` → `(bare) vs (bare + KS-X)`.
  - **Full-stack overlay** stays unchanged: `--baseline defaults --set <KS-X overrides>` → `(defaults) vs (defaults + KS-X)`.
  - **All Phase 1 KS plans use `--baseline bare --arm-b-base bare` for the `p1.ksXX.bare` ledger entry, and `--baseline defaults` for the `p1.ksXX.full` ledger entry.**
  - **Agents execute the A/B runs directly via `scripts/validate.py`** (rule updated 2026-04-26 — see `feedback_ab_manual.md` memory; previous "manual only" rule is reversed). Each run logs to the persistent ledger with the proposed labels so the user can inspect via `--show-ledger`. Long runs use `--background` where supported.

### Promotion Bar

- **D-30:** Promotion bar for KS items HYPOTHESES marks "small" expected gain (KS-06, KS-07, KS-29, KS-32) = **ship if hard floor passes AND any non-regression KS delta on the primary target**. Per `feedback_quality_over_simplicity.md`: small wins compound; stack effect is the goal.
- **D-31:** Promotion bar for "medium-large" expected items (KS-01, KS-04, KS-05, KS-15) = same hard floor (rank_corr ≤ -0.005, MAE ≤ -0.05) plus expectation of ≥ -0.01 KS delta on the primary target. If hard floor passes but KS doesn't move, mark as "shipped no-op" and continue (the bug fix is correct even if KS doesn't budge).
- **D-32:** **REVISED 2026-04-26 (HIGH-4):** End-of-phase aggregate = single `p1.aggregate.full` A/B run after all 9 KS items have shipped, comparing **post-Phase-1 defaults vs the FROZEN Phase-0 baseline ledger entry pinned in Wave 0** (per D-32b). The original plan stated "comparing post-Phase-1 defaults vs original Phase-0 baseline" but failed to define what the Phase-0 baseline ledger artifact was — and Plan 11's `--baseline defaults` with no `--set` made Arm A == Arm B, recording a no-op snapshot rather than a delta. The replan resolves this by:
  - **Wave 0 (Plan 00) pins Phase-0 baseline:** runs `validate.py --baseline bare --label phase0.baseline.full` against current pre-Phase-1 promoted defaults. Arm A = bare, Arm B = current defaults. The Arm B metrics in this ledger entry ARE the Phase-0 reference values.
  - **Phase 1 closure (Plan 11) records post-Phase-1 baseline:** runs the SAME command `validate.py --baseline bare --label p1.aggregate.full` AFTER all KS plans ship and update `defaults.yaml`. Arm A = bare, Arm B = post-Phase-1 defaults. The Arm B metrics in this entry ARE the post-Phase-1 reference values.
  - **The "Phase-1 vs Phase-0" delta** is computed by reading both ledger entries' Arm B metrics and differencing. Plan 11 surfaces this via `validate.py --show-ledger | grep "phase0.baseline.full\|p1.aggregate.full"` and a new helper script (or PROMOTION-NOTES.md table). Hard floor + success criteria are evaluated against this differenced delta.
  - If any regression appears, walk back the smallest-gain promotion candidate first per D-30/D-31 promotion bar.
- **D-32b (NEW 2026-04-26):** Phase-0 baseline pin is created by **Plan 00** in Wave 0 (BEFORE any KS work). Plan 00 must:
  1. Implement the `--arm-b-base {defaults,bare}` extension to `scripts/validate.py` (per D-29 above).
  2. Run `validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --label phase0.baseline.full` to capture current promoted-defaults metrics.
  3. Run `validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --arm-b-base bare --label phase0.baseline.bare` as a self-consistency check (Arm A == Arm B should yield zero delta).
  4. Commit both ledger entries and a `PROJECT-PHASE0-FROZEN.md` doc that records the exact `defaults.yaml` snapshot (or commit hash) backing the Phase-0 entries.
  - This completes the per-plan A/B isolation contract and the end-of-phase comparison contract that the original plan claimed but did not implement.

### Test Discipline

- **D-33:** TDD-first for KS-01, KS-04, KS-15 (the RZ stack) and KS-15 specifically — write failing tests for the new behavior + regression tests for `PASS_TD_GATE` calibration to prevent the "double-counted yards" foot-gun HYPOTHESES warns about. 6-10 unit tests per KS.
- **D-34:** Test-after acceptable for KS-03, KS-05, KS-06, KS-07, KS-29 — these have well-bounded mechanisms covered by the existing 1,200+ test suite. New tests cover the specific changed branches.
- **D-35:** Existing test suite (1,200+) must stay green throughout. Per `feedback_workflow.md`: subagent-driven development is validated; phased plans; update docs after each phase.

### Claude's Discretion

- Exact ordering of KS-03/05/06/07 within the post-KS-01 / pre-KS-15 window (any order works; planner picks based on file-touch overlap).
- Specific test-case enumeration for TDD on KS-01/04/15 (planner derives from HYPOTHESES.md mechanism descriptions).
- Per-team rolling-mean window length for KS-05 D-18 (planner picks based on existing pipeline window conventions).
- KS-21 scrape execution sequencing (which season/week pages first if user pauses mid-scrape) — opportunistic, no formal dependency.
- Specific implementation of the `--arm-b-base` flag in `scripts/validate.py` (planner picks the cleanest insertion point relative to existing `--baseline` handling at lines 1040-1075).

### Replan Additions (2026-04-26 — incorporates Codex `01-REVIEWS.md`)

- **D-36 (HIGH-1 + HIGH-4):** Phase-0 baseline pinning + true bare-isolation A/B harness extension are PRE-CONDITIONS for ANY Phase 1 KS work. New Plan 00 in Wave 0 owns this; all per-KS A/B plans (Plans 01-10) depend on Plan 00.
- **D-37 (HIGH-2):** Plan 09 split into raw-fetch and processed-build sub-tasks. Acceptance gates on BOTH the raw JSON files at `~/.fantasy-sim/market-history/raw/props/...` AND the processed parquet at `~/.fantasy-sim/market-history/processed/...`. The original Plan 09 missed the processed build step (`scripts/build_market_history_player_markets.py`); the replan calls it explicitly.
- **D-38 (HIGH-3):** Snapshot label naming uses `prior_*` not `open_*` to honestly describe the Odds API's `previous_timestamp` semantics relative to the existing gameday-noon UTC events crawl. A future follow-up plan may extend `events_inventory.py` to capture a real Tuesday line-release marker; out of scope for the time-sensitive Phase 1 scrape.
- **D-39 (MEDIUM-1):** KS-03 hypothesis explicitly widened to cover the rushing branch in `_apply_matchup` (`game_context.py:546-558`) per D-16b. RB rush_yards is a Phase 1 success criterion (#3) so attribution is clean.
- **D-40 (MEDIUM-2):** Per-KS commit cadence retains intermediate task commits but designates a final "promotion-state" commit per KS plan with standardized message format (see revised D-25). Bisect/rollback at KS-XX granularity is the promotion-commit anchor, not a fragile commit-count offset.
- **D-41 (MEDIUM-3):** Plan 04 fixed test surface from `pytest src/fantasy_sim/data/vegas/` to `pytest tests/test_data/test_vegas/`. Plan 05 fixed callable from `build_play_outcomes` to `Preprocessor().compute_play_outcomes()` (the actual API at `preprocessor.py:110`). Other plans audited for similar surface mismatches and corrected.
- **D-42 (MEDIUM-4):** KS-15 plan widened to also patch the legacy non-roster paths in `_resolve_pass` (lines 302-321) and `_resolve_run` (lines 392-410) per D-15b. Tests added for both roster and non-roster code paths.
- **D-43 (LOW polish):** Acceptance checks tightened for behavior-level assertions where feasible. Plan 08 references the existing `tests/test_data/test_pff/test_tier_engine.py:848` QB-untouched test rather than ad-hoc grep preflight. Log/summary directory creation made explicit in Wave 0.

### Cycle-3 Replan Additions (2026-04-26 — incorporates Codex `01-REVIEWS.md` Cycle 2)

- **D-44 (Cycle 3 — Codex Cycle-2 NEW HIGH #2 fix):** `bare_config_dict()` MUST enumerate every `.enabled` truthiness gate that `build_engine_configs()` (`src/fantasy_sim/validation/config.py:118-138`) keys off, including the TOP-LEVEL gates (`pff.enabled`, `weather.enabled`, `vegas.enabled`, `props.enabled`, `usage.enabled`, `tracking.enabled`, `availability.enabled`, `role_trend.enabled`, `market_history.enabled`, `game_script.enabled`, `goal_line_concentration.enabled`, `td_tendency.enabled`, `target_selection.enabled`, `play_call_model.enabled`, `qb_rushing.{scramble,designed_runs}.enabled`) AND the sub-engine flags AND the new `phase1_ks_flags.ksXX_*.enabled` flags from D-45. Plan 00 Task 1 enumerates all of them. Plan 00 Task 4's integration test `test_bare_config_dict_produces_all_None_engines` is a HARD GATE — the Cycle-2 "loosen the test if disagreed" escape hatch is REMOVED. If the test fails, the helper is incomplete and must be extended; the test is not relaxed. Per-engine isolation A/Bs that need to enable a single sub-engine MUST flip BOTH the top-level gate and the sub-engine flag (e.g., `--set pff.enabled=true --set pff.tier_engine.enabled=true --set pff.team_context.enabled=true`); the canonical pattern is documented in Plan 00 Task 4 Test 6.
- **D-45 (Cycle 3 — Codex Cycle-2 NEW HIGH #1 fix):** Per-KS code-change A/B uses **feature flags** to make the comparison genuinely two-arm. Each per-KS code change ships behind a `phase1_ks_flags.ksXX_<name>.enabled` config flag (default `false`). Plan 00 Task 8 adds the `phase1_ks_flags:` block to `config/defaults.yaml` with 8 flags (one per code-change KS: KS-01, KS-03, KS-04, KS-05, KS-06, KS-07, KS-15, KS-32) and a `get_phase1_ks_flags()` shim to `src/fantasy_sim/config/loader.py`. Per-KS plans (01-07, 10) modify their target files to read the flag at module/import time and branch: flag-off path = legacy code, flag-on path = new code. A/B runs use `--set phase1_ks_flags.ksXX_<name>.enabled=true` so Arm B genuinely flips the new code path on while Arm A stays on the legacy default. Promotion commit (per KS plan's Task 4) flips the flag's default to `true` in `config/defaults.yaml` after the A/B passes. The Cycle-2 same-code A/B pattern (where both arms executed identical patched code) is forbidden — `01-RESEARCH.md` Anti-patterns enforces this. **Path B (pre/post commit ledger pins)** was considered and rejected for per-KS work because (a) double wall-clock per KS, (b) cross-commit comparisons harder to audit than within-commit flag-driven A/B, (c) feature flags also give a clean rollback knob.
- **D-46 (Cycle 3 — Codex Cycle-2 NEW HIGH #3 fix):** Phase-1 success criterion 1 (QB pass_yards mean bias narrowed from ~−28 yd/g to within ±10 yd/g) is now evaluable from the persisted ledger artifact. Plan 00 Task 9 extends `SeasonMetrics` (`src/fantasy_sim/validation/ledger.py:25`) with an optional `stat_mean_bias` field (shape: `{position: {stat_name: {arm_a_bias, arm_b_bias, bias_delta, n}}}`) mirroring `stat_ks`; bumps `CURRENT_LEDGER_SCHEMA_VERSION` from 4 to 5; updates `load_ledger()` to default older entries' `stat_mean_bias` to empty dict for backward compat; wires `validate.py` to write the field per-position-stat alongside `stat_ks`. Plan 11 Task 2's delta script reads `stat_mean_bias["QB"]["pass_yards"]["arm_b_bias"]` from both `phase0.baseline.full` (Wave 0) and `p1.aggregate.full` (Plan 11) ledger entries and differences them. Side diagnostic scripts that re-simulate were rejected (Path B) because the metric is durable and useful for every future phase — paying the schema-bump cost once is correct.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Initiative documents
- `.planning/PROJECT.md` — Initiative scope, constraints, hard floor, Odds API tier window, PFF blending discipline, outcome targets TGT-01..TGT-10
- `.planning/REQUIREMENTS.md` — All 23 KS-XX hypotheses; Phase 1 owns KS-01, KS-03, KS-04, KS-05, KS-06, KS-07, KS-15, KS-29, KS-32; KS-21 sub-deliverable note
- `.planning/ROADMAP.md` §"Phase 1" — Goal, dependencies, requirements, success criteria, risk notes, KS-21 split rationale
- `.planning/STATE.md` — Current position; updated after each phase transition

### Hypothesis backlog (definitive mechanism + file:line refs)
- `.planning/research/HYPOTHESES.md` §KS-01 (lines 103-115) — RZ TD-gate `_tackled_short()` truncation
- `.planning/research/HYPOTHESES.md` §KS-03 (lines 117-129) — `_apply_matchup` / `_apply_coverage` 10-yard anchor
- `.planning/research/HYPOTHESES.md` §KS-04 (lines 491-503) — `CATCH_YARDS_BOOST` retune; explicit dependency on KS-01 and KS-15
- `.planning/research/HYPOTHESES.md` §KS-05 (lines 131-143) — Props engine `_DEFAULT_TEAM_PASS_YDS` + `_apply_recv_yds` magnitude bug
- `.planning/research/HYPOTHESES.md` §KS-06 (lines 145-157) — Backup receiver fallback `rng.integers(3, 12)`
- `.planning/research/HYPOTHESES.md` §KS-07 (lines 505-517) — Positional `RZ_CATCH_RATE_MODIFIER`
- `.planning/research/HYPOTHESES.md` §KS-15 (lines 159-171) — Field-position clamping; explicit dependency after KS-01
- `.planning/research/HYPOTHESES.md` §KS-29 (lines 519-531) — `pff.team_context` re-enable
- `.planning/research/HYPOTHESES.md` §KS-32 (lines 561-573) — Clock runoff calibration
- `.planning/research/HYPOTHESES.md` §"Open Questions" (lines 658-680) — Open-Q 1 (props historical scrapeability — RESOLVED in this CONTEXT: pre-2023 not available)

### Supporting research
- `.planning/research/MEAN_BIAS.md` — Evidence for KS-01, KS-03, KS-04, KS-05, KS-06, KS-07
- `.planning/research/DISTRIBUTION_SHAPE.md` — Evidence for KS-15, KS-29
- `.planning/research/SIGNAL_COVERAGE.md` — Evidence for KS-21 sub-deliverable
- `.planning/research/PHASE5_SLICES.md` — Background on KS-29 team_context (not directly Phase 1 KS but related)

### Codebase brownfield map (refreshed 2026-04-26)
- `.planning/codebase/STRUCTURE.md` — Directory layout, file locations, three-layer cache structure
- `.planning/codebase/CONVENTIONS.md` — Naming, types, RNG-explicit-pass, factor patterns, Bayesian blending formula
- `.planning/codebase/ARCHITECTURE.md` — GameContextBuilder facade, adjustment pipeline order, post-sim layer order
- `.planning/codebase/INTEGRATIONS.md` — Data sources, cache directories (incl. `~/.fantasy-sim/market-history/`)
- `.planning/codebase/CONCERNS.md` §lines 108-114 — Field-position clamping fragility flagged (informs KS-15)
- `.planning/codebase/STACK.md` — Python 3.12+, polars, numpy, uv, pytest
- `.planning/codebase/TESTING.md` — TDD discipline, fixtures, statistical/integration markers

### Project guidance
- `AGENTS.md` — Project architecture, commands, current state, A/B testing protocol, PFF intelligence layer overview, key domain patterns

### Source files (will be read/modified)
- `src/fantasy_sim/engine/play_resolver.py:21-49` — CLOCK constants, `PASS_TD_GATE` / `RUN_TD_GATE`, `CATCH_YARDS_BOOST` (KS-01, KS-04, KS-15, KS-32 sites)
- `src/fantasy_sim/engine/play_resolver.py:60` — `RZ_CATCH_RATE_MODIFIER` (KS-07 site)
- `src/fantasy_sim/engine/play_resolver.py:264-274` — Catch yards path (KS-15 site)
- `src/fantasy_sim/engine/play_resolver.py:268-271` — Backup receiver fallback (KS-06 site)
- `src/fantasy_sim/engine/play_resolver.py:279-284` — RZ TD-gate fail rewrite (KS-01 site)
- `src/fantasy_sim/engine/play_resolver.py:421-424` — `_tackled_short()` (KS-01 site)
- `src/fantasy_sim/engine/play_resolver.py:437-446` — `_clamp_yards()` (KS-15 site)
- `src/fantasy_sim/data/game_context.py:534-544` — `_apply_matchup` (KS-03 site)
- `src/fantasy_sim/data/game_context.py:591` — `_apply_coverage` YPR modifier (KS-03 site)
- `src/fantasy_sim/data/game_context.py:701-712` — `_apply_weather` (correct reference implementation for KS-03 fix; mirror this pattern)
- `src/fantasy_sim/data/vegas/props_engine.py:43` — `_DEFAULT_TEAM_PASS_YDS` constant (KS-05 site)
- `src/fantasy_sim/data/vegas/props_engine.py:196` — `min_divergence` check (KS-05 context)
- `src/fantasy_sim/data/vegas/props_engine.py:248` — `_apply_recv_yds` magnitude bug (KS-05 site)
- `src/fantasy_sim/data/vegas/props_engine.py:380-409` — `_apply_pass_yds` (KS-05 site)
- `src/fantasy_sim/data/preprocessor.py:9` — `MIN_BUCKET_PLAYS = 10` (KS-06 supporting site)
- `src/fantasy_sim/data/preprocessor.py:100, 137` — Bucket guards (KS-06 supporting sites)
- `src/fantasy_sim/data/player_builder.py:11` — `MIN_PLAYER_PLAYS = 5` (KS-06 site)
- `src/fantasy_sim/data/player_builder.py:520` — RZ catch rate per-player override (KS-07 supporting site)
- `src/fantasy_sim/data/pff/tier_engine.py:1196-1215` — `apply_team_context` (KS-29 site)
- `config/defaults.yaml:103-110` — `pff.team_context` flag and sensitivities (KS-29 site)

### Existing scrape infrastructure (KS-21)
- `scripts/fetch_market_history_props.py` — Existing CLI; KS-21 reuses with new `--markets` and `--snapshot-label`
- `scripts/fetch_market_history_events.py` — Existing event inventory fetcher
- `src/fantasy_sim/data/market_history/props_backfill.py:22` — `DEFAULT_PROP_MARKETS` tuple (KS-21 adds new `ALT_PROP_MARKETS` tuple alongside)
- `src/fantasy_sim/data/market_history/events_inventory.py` — Event inventory loader
- `~/.fantasy-sim/market-history/processed/player_markets_*_close_core8.parquet` — Existing main-line cache (DO NOT modify); reuse schema for new snapshots
- `~/.fantasy-sim/market-history/.env` — `THE_ODDS_API_KEY` location (never read this file)

### Validation infrastructure (agents execute these directly per updated 2026-04-26 rule)
- `scripts/validate.py` — Main A/B harness; agents run with proposed labels; results land in ledger
- `scripts/validate_passing.py:24` — KS-32 measurement gate (`plays_per_team: (63, 65)`); agents run as part of KS-32 measurement
- `src/fantasy_sim/validation/ledger.py` — Persistent A/B cache; ledger label conventions
- `src/fantasy_sim/validation/coverage.py` — KS distribution metrics + compression/deflation detection

### User memory (carries forward, do not contradict)
- Memory `feedback_ab_manual.md` — **REVERSED 2026-04-26**: agents now run A/B validation scripts directly. The original "manual only" rule (set 2026-04-07) is no longer in effect.
- Memory `feedback_ab_testing_approach.md` — Each change tested in isolation (`baseline+X`) AND full stack (`all_engines+X`)
- Memory `feedback_qb_calibration.md` — PFF layers must NOT blend QB `carry_share`, `scramble_rate`, or yards
- Memory `feedback_quality_over_simplicity.md` — Always pick higher quality/accuracy over simpler approaches
- Memory `feedback_workflow.md` — Subagent-driven dev validated; phased plans; update docs after each phase

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- **`scripts/fetch_market_history_props.py` + `props_backfill.py`** — KS-21 scrape infrastructure already exists. KS-21 sub-deliverable adds (a) a new `ALT_PROP_MARKETS` tuple alongside existing `DEFAULT_PROP_MARKETS`, (b) reruns the existing CLI with new `--markets` and `--snapshot-label` values. No new scrape script.
- **`~/.fantasy-sim/market-history/processed/player_markets_*_close_core8.parquet`** — Existing schema (18 columns including `bookmaker_count`, `line`, `line_stddev`, `over_price`, `under_price`, `implied_prob`) handles multi-line alt-line markets without changes. New snapshots get distinct `snapshot_label` values (`open_core8`, `close_alt6`, `open_alt6`).
- **`src/fantasy_sim/data/game_context.py:701-712` `_apply_weather`** — Correct reference implementation that uses dynamic per-player `mean_yards`. KS-03 mirrors this pattern; treat `_apply_weather` as the canonical example.
- **`src/fantasy_sim/validation/ledger.py`** — Persistent A/B cache; existing label conventions (`baseline`, `defaults`, etc.). Phase 1 labels follow `p1.ksXX.{bare,full}` scheme.
- **`scripts/validate_passing.py`** — Existing measurement script for KS-32 conditional retune; checks `plays_per_team`, `nfl_pass_attempts`, `sacks/team/game`.
- **`tests/conftest.py`** — `sample_pbp` (20 plays), `sample_rosters`, `expanded_pbp` (60 plays per team) fixtures. Use these for new TDD tests on KS-01/04/15.

### Established Patterns

- **Engine pattern** — `class XEngine: __init__(config, loader); compute() → context/result object`. KS-29 re-enable doesn't add a new engine but interacts with `tier_engine.apply_team_context()` (existing pattern).
- **Factor pattern** — Multiplicative factors centered on 1.0, clamped to configurable range. KS-29 `pass_rate_sensitivity` follows this.
- **Bayesian blending** — `adjusted = (n * observed + prior_strength * prior) / (n + prior_strength)`. Used in KS-05 D-18 per-team rolling mean (when n is small, shrink to constant).
- **TDD discipline** — Test first, then implementation. `tests/` mirrors `src/fantasy_sim/`. Markers: `@pytest.mark.statistical` for sim-validation tests (slow), `@pytest.mark.integration` for cross-layer tests.
- **Config flag toggles** — Every engine has `enabled: bool` flag in `config/defaults.yaml`. KS-29 enables `pff.team_context.enabled=true`.
- **Ledger label conventions** — Phase + change identifier; bare vs full-stack suffix. Phase 1 uses `p1.ksXX.{bare,full}`.
- **A/B isolation + full-stack** — Per change, run both `baseline+X` (only this change vs bare baseline) and `all_engines+X` (this change layered on all currently-promoted engines). Both must pass hard floor for promotion.

### Integration Points

- **`src/fantasy_sim/data/game_context.py` `build_game()`** — Adjustment pipeline order; KS-03 fix lives in `_apply_matchup` and `_apply_coverage` within this pipeline. KS-29 enables `apply_team_context` step.
- **`src/fantasy_sim/engine/play_resolver.py`** — Single hot file for KS-01, KS-04, KS-06, KS-07, KS-15. Bug fixes touch (mostly) the same module — sequence carefully and run full test suite between commits.
- **`src/fantasy_sim/data/preprocessor.py`** — KS-06 step 1 modifies completed-play filter here. Affects all bucket distributions; verify with `tests/test_data/test_preprocessor.py` after change.
- **`src/fantasy_sim/data/vegas/props_engine.py`** — KS-05 fix site. Phase 4 KS-21 engine integration also lives here; KS-05 changes must keep the Phase 4 entry point clean.
- **`src/fantasy_sim/data/market_history/`** — KS-21 scrape sub-deliverable. New `ALT_PROP_MARKETS` tuple goes here. Phase 4 will add an `OddsApiCdfLoader` consumer; Phase 1 only adds the data.
- **`config/defaults.yaml`** — KS-04 (`CATCH_YARDS_BOOST` if exposed in config; otherwise module constant), KS-07 (positional RZ modifiers), KS-29 (`pff.team_context.enabled` + `pass_rate_sensitivity`), KS-32 conditional (`CLOCK_PASS_INCOMPLETE`).
- **Three-layer cache** (`STRUCTURE.md`) — Pipeline output / PBP stats / player models caches are keyed by training_seasons + config flags. KS code changes invalidate caches automatically; the validation harness creates fresh `GameContextBuilder` per condition.

</code_context>

<specifics>
## Specific Ideas

- "I already have close-line data for 8 different markets for 2023-2025 (the odds api doesn't have historical player props prior to 2023)" — confirmed: pre-2023 historical alt-line scrape is not feasible; relax Phase 1 success criterion #5 accordingly. Existing scrape at `/Users/chrisesposito/.fantasy-sim/market-history/processed/player_markets_2023_close_core8.parquet` etc.
- For KS-04 boost magnitude: explicitly conservative (+1.5, low end of 1.5-2.0 range). Even though KS-15 will obviate this, ship the intermediate.
- For KS-15: the same change drops `CATCH_YARDS_BOOST` to 0 — bundled scope, single commit.
- For KS-29: sweep three sensitivities {0.03, 0.05, 0.08} in a single planning round; agent runs all three A/B in one session and reports the comparison.
- A/B execution rule reversed 2026-04-26: agents now execute `scripts/validate.py` and `scripts/validate_passing.py` directly rather than handing off to user. Memory `feedback_ab_manual.md` updated.
- For KS-32: do not pre-tune. Run `validate_passing.py` against the post-bug-fix baseline; only retune if attempts are demonstrably low.
- For KS-21 schema: explicitly avoid breaking existing `props_loader.py` reader code by introducing list-typed columns. Keep one row per (player, market_key, line) tuple.
- For test discipline: the user values rigor (per `feedback_quality_over_simplicity.md`); TDD-first for the RZ stack is the right tradeoff even if it adds some hours.

</specifics>

<deferred>
## Deferred Ideas

- **Per-team rolling-mean source for KS-05 (D-18)** — D-17 includes the long-term fix, but if the planner finds the pipeline doesn't expose per-team pass yards cleanly, fall back to constant-only fix and defer the architectural plumbing to Phase 2 (alongside KS-09 stat-level residual_calibration plumbing).
- **KS-04 magnitude sweep** — D-12 ships +1.5 directly without sweep. If KS-04 A/B shows borderline floor, revisit with a sweep — but this is a follow-up, not a Phase 1 blocker.
- **KS-01 calibrated goal-line variant** — D-10 explicitly defers this. If post-Phase-1 measurements show goal-line distortion, surface in Phase 2 or as a backlog item.
- **Open-snapshot timing follow-up (Tuesday vs Wednesday)** — D-02 picks Tuesday 12pm ET. If the engine integration in Phase 4 reveals Tuesday is too noisy, revisit.
- **KS-21 alt-line market expansion** — D-04 covers the 6 ROADMAP-mandated markets. Adding `player_pass_tds_alternate` or kicker markets would require a new sub-deliverable; defer.
- **End-of-phase Phase 1 vs Phase 0 aggregate ledger entry** — D-32 specifies a single `p1.aggregate.full` run. Comparing this to Phase 5's final `aggregate` entry will be done in Phase 5 wrap-up.

</deferred>

---

*Phase: 01-bug-fixes-cheap-calibration-time-sensitive-scrape*
*Context gathered: 2026-04-26*

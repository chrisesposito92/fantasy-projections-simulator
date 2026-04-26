---
phase: 1
slug: bug-fixes-cheap-calibration-time-sensitive-scrape
status: revised
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-26
revised: 2026-04-26 (Cycle 1)
re_revised: 2026-04-26 (Cycle 3)
revision_reason: "Cycle 1: incorporates Codex 01-REVIEWS.md HIGH-1 (true-isolation harness) + HIGH-4 (Phase-0 baseline pin). Cycle 3: incorporates Codex Cycle-2 NEW HIGH #1 (per-KS feature-flag pattern via D-45 — replaces same-code no-op A/B), NEW HIGH #2 (bare_config_dict() exhaustive top-level + KS-flag enumeration via D-44 + Plan 00 Task 4 hard-gate test, escape hatch removed), NEW HIGH #3 (SeasonMetrics.stat_mean_bias schema bump 4→5 via D-46 + Plan 11 Task 2 reads it directly). Plus Cycle 1 partial-resolves of HIGH-2/HIGH-3 (RESEARCH.md staleness reconciled)."
---

# Phase 1 — Validation Strategy (REVISED 2026-04-26 — Cycle 3)

> Per-phase validation contract for feedback sampling during execution. Hard floor: any change must NOT regress rank_corr by >0.005 OR MAE by >0.05 vs prior promoted defaults.
>
> **Cycle 1 Revision (2026-04-26):** Codex `01-REVIEWS.md` flagged that the original `--baseline bare` was contaminated by all default-on engines (HIGH-1) and that Plan 11's aggregate was a no-op (HIGH-4). Plan 00 (Wave 0) implements the `--arm-b-base bare` flag and pins `phase0.baseline.full` so all subsequent plans can perform true isolation A/B and the end-of-phase aggregate compares against a frozen reference.
>
> **Cycle 3 Revision (2026-04-26):** Codex Cycle-2 review flagged 3 new HIGH-severity blockers: (a) per-KS code-change A/B was structurally a no-op because both arms ran the same patched code (NEW HIGH #1), (b) `bare_config_dict()` omitted top-level engine gates (NEW HIGH #2), (c) Plan 11 mean-bias success criterion couldn't be evaluated from the ledger (NEW HIGH #3). Cycle 3 fixes via D-44/D-45/D-46: feature-gated per-KS code changes, exhaustive `bare_config_dict` + hard-gate Plan 00 Task 4, schema-bumped ledger with `stat_mean_bias`. Plus Cycle 1 partial-resolves: `01-RESEARCH.md` reconciled with `01-CONTEXT.md` and Plan 09 (`prior_*` labels, raw→build pipeline split, `previous_timestamp` honesty).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x with pytest-xdist + hypothesis |
| **Config file** | `pyproject.toml` (project-managed via uv) |
| **Quick run command** | `uv run pytest tests/test_engine/test_play_resolver.py tests/test_data/test_game_context.py tests/test_data/test_pff -v` |
| **Full suite command** | `uv run pytest tests/ -v` |
| **Statistical-only command** | `uv run pytest tests/ -v -m statistical` |
| **Estimated runtime** | ~30s (quick), ~6 min (full), ~12 min (statistical) |
| **A/B harness — true isolation (per-KS bare)** | `uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --arm-b-base bare [--set k=v ...] --label "p1.ksXX.bare"` (requires Plan 00 to have landed) |
| **A/B harness — full-stack overlay (per-KS full)** | `uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline defaults [--set k=v ...] --label "p1.ksXX.full"` |
| **A/B harness — Wave 0 baseline pin** | `uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --label "phase0.baseline.full"` (no `--set`) |
| **A/B harness — end-of-phase aggregate** | `uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --label "p1.aggregate.full"` (no `--set`; compare Arm B vs phase0.baseline.full Arm B) |
| **A/B inspection** | `uv run python scripts/validate.py --show-ledger \| grep p1.` |
| **Pass-attempts gate** | `uv run python scripts/validate_passing.py --sims 50 --seasons 2024` |

---

## Sampling Rate

- **After every task commit:** Run quick command — must be green.
- **After every plan completes (each KS-XX):** Run full suite — must be green.
- **After every plan completes (each KS-XX):** Run BOTH `validate.py --baseline bare --arm-b-base bare --label p1.ksXX.bare` (true isolation) AND `validate.py --baseline defaults --label p1.ksXX.full` (full-stack overlay). Both must pass hard floor.
- **End of phase (after all 9 KS plans + KS-21 scrape ship):** Run `validate.py --baseline bare --label p1.aggregate.full` (no `--set`) — captures post-Phase-1 promoted defaults' metrics in Arm B; Plan 11 differences this against Wave-0 `phase0.baseline.full` Arm B to evaluate against TGT-XX.
- **Max feedback latency per task:** ~30s (quick suite); ~30 min (per A/B run at 200 sims/season × 3 seasons).

---

## Per-Plan Verification Map

| Plan ID | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 00-validation-harness-and-phase0-baseline | 0 | (prerequisite for all KS plans) | — | `--arm-b-base bare` flag wired on validate.py; **Cycle 3:** exhaustive `bare_config_dict()` (incl. top-level gates + KS flags); `phase1_ks_flags:` block in defaults.yaml + `get_phase1_ks_flags()` helper (Task 8); SeasonMetrics.stat_mean_bias + ledger schema v5 (Task 9); phase0.baseline.full + phase0.baseline.bare ledger entries pinned with stat_mean_bias populated; PROJECT-PHASE0-FROZEN.md captures defaults SHA + headline mean-bias | unit + integration + ledger | `uv run pytest tests/test_validation/test_config.py -v -k bare_config_dict && uv run pytest tests/test_validation/test_config.py -v -k all_None && uv run pytest tests/test_validation/test_config.py -v -k phase1_ks && uv run pytest tests/test_validation/test_ledger_schema.py -v && uv run python scripts/validate.py --help \| grep arm-b-base && uv run python -c "from fantasy_sim.config.loader import get_phase1_ks_flags; assert len(get_phase1_ks_flags())>=8" && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --label phase0.baseline.full && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --arm-b-base bare --label phase0.baseline.bare` | ✅ scripts/validate.py exists | ⬜ pending |
| 01-ks01-rz-tdgate-fix | 1 | KS-01 | — | RZ TD-gate fail preserves sampled distribution; PASS_TD_GATE calibration unchanged. **Cycle 3 D-45:** gated behind `phase1_ks_flags.ks01_preserve_distribution.enabled` | unit + statistical | `uv run pytest tests/test_engine/test_play_resolver.py -v -k "tackled_short or rz_td_gate or ks01" && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --arm-b-base bare --set phase1_ks_flags.ks01_preserve_distribution.enabled=true --label p1.ks01.bare && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline defaults --set phase1_ks_flags.ks01_preserve_distribution.enabled=true --label p1.ks01.full` | ✅ existing test file | ⬜ pending |
| 02-ks04-catch-yards-boost | 2 | KS-04 | — | Conditional boost (+1.5) only when `_clamp_yards` would fire. **Cycle 3 D-45:** gated behind `phase1_ks_flags.ks04_conditional_catch_boost.enabled` | unit + statistical | `uv run pytest tests/test_engine/test_play_resolver.py -v -k "catch_yards or boost or ks04" && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --arm-b-base bare --set phase1_ks_flags.ks04_conditional_catch_boost.enabled=true --label p1.ks04.bare && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline defaults --set phase1_ks_flags.ks04_conditional_catch_boost.enabled=true --label p1.ks04.full` | ✅ existing test file | ⬜ pending |
| 03-ks03-matchup-coverage-anchor | 3 | KS-03 | — | `_apply_matchup` (BOTH receiving and rushing branches per D-16b) and `_apply_coverage` use per-player `np.mean(<dist>)` like `_apply_weather`. **Cycle 3 D-45:** gated behind `phase1_ks_flags.ks03_dynamic_yard_anchor.enabled` | unit + statistical | `uv run pytest tests/test_data/test_game_context.py -v -k "matchup or coverage or ks03" && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --arm-b-base bare --set phase1_ks_flags.ks03_dynamic_yard_anchor.enabled=true --label p1.ks03.bare && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline defaults --set phase1_ks_flags.ks03_dynamic_yard_anchor.enabled=true --label p1.ks03.full` | ✅ existing test file | ⬜ pending |
| 04-ks05-props-engine-bugs | 3 | KS-05 | — | `_DEFAULT_TEAM_PASS_YDS=240`, `_apply_recv_yds` uses `dist_mean * catches_per_game * games_played`. **Cycle 3 D-45:** gated behind `phase1_ks_flags.ks05_props_recv_yds_fix.enabled`. Bare-isolation requires `--set vegas.enabled=true --set vegas.props.enabled=true` (Cycle 3 D-44 — bare_config_dict now correctly disables top-level vegas.enabled gate) | unit + statistical | `uv run pytest tests/test_data/test_vegas/ -v -k "props or recv_yds or ks05" && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --arm-b-base bare --set vegas.enabled=true --set vegas.props.enabled=true --set phase1_ks_flags.ks05_props_recv_yds_fix.enabled=true --label p1.ks05.bare && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline defaults --set phase1_ks_flags.ks05_props_recv_yds_fix.enabled=true --label p1.ks05.full` | ✅ existing test dir (`tests/test_data/test_vegas/` — D-41 corrects original wrong path `src/fantasy_sim/data/vegas/`) | ⬜ pending |
| 05-ks06-backup-receiver-fallback | 3 | KS-06 | — | Filter team-bucket via `Preprocessor().compute_play_outcomes()` to completed plays (D-41 corrects original wrong API name `build_play_outcomes`); fallback `rng.integers(5, 18)`; `MIN_PLAYER_PLAYS=3`. **Cycle 3 D-45:** gated behind `phase1_ks_flags.ks06_backup_receiver_fix.enabled` | unit + statistical | `uv run pytest tests/test_data/test_preprocessor.py tests/test_data/test_player_builder.py tests/test_engine/test_play_resolver.py -v -k "backup or fallback or ks06 or MIN_PLAYER" && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --arm-b-base bare --set phase1_ks_flags.ks06_backup_receiver_fix.enabled=true --label p1.ks06.bare && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline defaults --set phase1_ks_flags.ks06_backup_receiver_fix.enabled=true --label p1.ks06.full` | ✅ existing test files | ⬜ pending |
| 06-ks07-positional-rz-catch-rate | 3 | KS-07 | — | `RZ_CATCH_RATE_MODIFIERS = {"WR": 0.92, "TE": 0.95, "RB": 0.85}`. **Cycle 3 D-45:** gated behind `phase1_ks_flags.ks07_positional_rz_catch_rate.enabled` | unit + statistical | `uv run pytest tests/test_engine/test_play_resolver.py tests/test_data/test_player_builder.py -v -k "rz_catch or RZ_CATCH or ks07" && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --arm-b-base bare --set phase1_ks_flags.ks07_positional_rz_catch_rate.enabled=true --label p1.ks07.bare && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline defaults --set phase1_ks_flags.ks07_positional_rz_catch_rate.enabled=true --label p1.ks07.full` | ✅ existing test files | ⬜ pending |
| 07-ks15-clamping-fix | 4 | KS-15 | — | Roster path AND legacy non-roster path (per D-15b) both use `min(yard_line, sample)` for yards; un-clamped sample drives TD gate; `CATCH_YARDS_BOOST=0`. **Cycle 3 D-45:** gated behind `phase1_ks_flags.ks15_unclamp_for_td_gate.enabled` | unit + statistical | `uv run pytest tests/test_engine/test_play_resolver.py -v -k "clamp or catch_yards or ks15 or rz_td_gate or legacy" && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --arm-b-base bare --set phase1_ks_flags.ks15_unclamp_for_td_gate.enabled=true --label p1.ks15.bare && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline defaults --set phase1_ks_flags.ks15_unclamp_for_td_gate.enabled=true --label p1.ks15.full` | ✅ existing test file | ⬜ pending |
| 08-ks29-team-context-enable | 5 | KS-29 | — | `pff.team_context.enabled=true` with chosen `pass_rate_sensitivity` from sweep {0.03, 0.05, 0.08}; QB carry/scramble/yards untouched (verified via existing `tests/test_data/test_pff/test_tier_engine.py:848` test per LOW-2 fix). **Cycle 3 D-44:** bare-isolation also requires `--set pff.enabled=true --set pff.tier_engine.enabled=true` because the Cycle-3 bare_config_dict now correctly disables those top-level/sub gates. | unit + statistical + behavior preflight | `uv run pytest tests/test_data/test_pff/test_tier_engine.py -v -k "team_context and qb" && uv run pytest tests/test_data/test_pff -v -k "team_context or ks29" && for s in 003 005 008; do dec=$(echo $s \| sed 's/^0*/0./'); uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --arm-b-base bare --set pff.enabled=true --set pff.tier_engine.enabled=true --set pff.team_context.enabled=true --set pff.team_context.pass_rate_sensitivity=$dec --label p1.ks29.s${s}.bare; uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline defaults --set pff.team_context.enabled=true --set pff.team_context.pass_rate_sensitivity=$dec --label p1.ks29.s${s}.full; done` | ✅ existing test dir | ⬜ pending |
| 09-ks21-altline-scrape | 1 | KS-21 (sub-deliverable) | — | Three new processed parquet caches: `prior_core8`, `prior_alt6`, `close_alt6` for 2023, 2024, 2025. Built via TWO scripts per pair: (1) raw fetch via `fetch_market_history_props.py`, (2) parquet build via `build_market_history_player_markets.py`. Per HIGH-2/HIGH-3 fixes: pipeline split made explicit; labels renamed `open_*` → `prior_*` to honestly describe API semantics. | data-acquisition + schema verification | `ls ~/.fantasy-sim/market-history/processed/player_markets_*_prior_core8.parquet ~/.fantasy-sim/market-history/processed/player_markets_*_prior_alt6.parquet ~/.fantasy-sim/market-history/processed/player_markets_*_close_alt6.parquet` (existence check after BOTH raw fetch and parquet build) | ✅ infra exists (`fetch_market_history_props.py`, `props_backfill.py`, `build_market_history_player_markets.py`, `player_markets.py`) | ⬜ pending |
| 10-ks32-clock-runoff-measure | 6 | KS-32 | — | `validate_passing.py` measurement; only retune `CLOCK_PASS_INCOMPLETE` if attempts demonstrably low. NO CHANGE branch uses `--baseline bare` (no `--set`) per HIGH-4 fix. RETUNE branch (Cycle 3 D-45) gated behind `phase1_ks_flags.ks32_clock_pass_incomplete_3s.enabled`. | measurement + (conditional) statistical | `uv run python scripts/validate_passing.py --sims 50 --seasons 2024` THEN conditional: if attempts in [32, 33] and plays in [60, 62], `uv run pytest tests/test_engine/test_clock.py -v -k ks32 && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --arm-b-base bare --set phase1_ks_flags.ks32_clock_pass_incomplete_3s.enabled=true --label p1.ks32.bare && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline defaults --set phase1_ks_flags.ks32_clock_pass_incomplete_3s.enabled=true --label p1.ks32.full`; else `uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --label p1.ks32.measure` (REAL delta vs bare per HIGH-4) | ✅ existing test file | ⬜ pending |
| 11-phase1-aggregate-validation | 7 | (covers all KS-01..KS-29, KS-32) | — | `p1.aggregate.full` ledger entry uses `--baseline bare` (NOT `--baseline defaults` per HIGH-4 fix); Phase-1-vs-Phase-0 delta computed from `phase0.baseline.full` (Wave 0) and `p1.aggregate.full` Arm B differences. **Cycle 3 D-46:** delta computation reads `stat_mean_bias["QB"]["pass_yards"]["arm_b_bias"]` from both ledger entries (schema v5 from Plan 00 Task 9) to evaluate success criterion 1. | aggregate validation | `uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --label p1.aggregate.full && uv run python scripts/validate.py --show-ledger \| grep -E "phase0.baseline.full\|p1.aggregate.full"` (then Task 2's delta-computation script that reads stat_mean_bias from both entries) | ✅ harness exists (post-Plan-00) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

> Hard floor enforcement: each `--label p1.ksXX.{bare,full}` ledger entry must show `Δ rank_corr ≥ -0.005 AND Δ weekly_mae ≤ +0.05`. Promotion bar per D-30/D-31 (small-gain vs medium-large items) layers KS delta requirements on top.

---

## Wave 0 Requirements (REVISED 2026-04-26)

- [x] `tests/test_engine/test_play_resolver.py` — exists (32.3 KB), receives new tests for KS-01, KS-04, KS-15 (roster + legacy paths per D-15b), KS-06 backup-receiver fallback, KS-07 positional RZ
- [x] `tests/test_data/test_game_context.py` — exists, receives new tests for KS-03 anchor fix (3 sites: matchup pass, matchup rush, coverage)
- [x] `tests/test_data/test_preprocessor.py` — exists, receives new tests for KS-06 completed-play filter
- [x] `tests/test_data/test_player_builder.py` — exists, receives new tests for KS-06 `MIN_PLAYER_PLAYS=3` and KS-07 RZ catch-rate
- [x] `tests/test_engine/test_clock.py` — exists, receives new tests for KS-32 (only if measurement motivates change)
- [x] `tests/test_data/test_pff/` — directory exists, receives new tests for KS-29 team_context (existing test patterns under `tests/test_data/test_pff_config_loader.py` etc.); existing `tests/test_data/test_pff/test_tier_engine.py:848` QB-untouched test reused for KS-29 preflight per LOW-2 fix
- [x] `tests/test_data/test_vegas/` — directory exists; KS-05 props_engine tests live here (D-41 corrects original wrong `src/fantasy_sim/data/vegas/` path in this VALIDATION.md)
- [x] `tests/test_validation/` — directory exists; Plan 00 adds `test_config.py` with 5 unit + 1 integration tests for `bare_config_dict` and `--arm-b-base` flow
- [x] `tests/conftest.py` — exists with `sample_pbp` (20 plays, KC/BUF), `sample_rosters`, `expanded_pbp` (60 plays/team) fixtures — sufficient for new tests
- [x] pytest framework — installed via `uv` (project uses `uv run pytest`)
- [x] hypothesis property-based testing — installed via `uv` (used in `tests/test_engine/test_statistical_validation.py`)
- [x] `scripts/validate.py` — A/B harness present with `--baseline {bare,defaults}`, `--set`, `--label`, `--show-ledger`, `--no-cache`, `--workers` CLI flags. **NEW IN PLAN 00:** `--arm-b-base {defaults,bare}` flag for true isolation. Default `defaults` preserves backward compatibility.
- [x] `scripts/validate_passing.py` — Pass-attempts measurement gate present (16.2 KB; checks `plays_per_team`, `nfl_pass_attempts`, `sacks/team/game`)
- [x] `scripts/fetch_market_history_props.py` — Raw-fetch CLI present with `--season`, `--week`, `--markets`, `--snapshot-label`, `--date-source`, `--offset-minutes`, `--limit`, `--force` (verified). Writes raw JSON only.
- [x] `scripts/build_market_history_player_markets.py` — **NEWLY DOCUMENTED IN PLAN 09 PER HIGH-2 FIX:** Parquet-build CLI present with `--season`, `--snapshot-label`. Reads raw JSON, writes processed parquet. Both scripts must run for KS-21 deliverable.
- [x] `src/fantasy_sim/validation/ledger.py` — Persistent A/B ledger with schema versioning + `format_ledger_table` (verified)
- [x] `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/` — Created in Plan 00 Task 5 per D-43

> All testing infrastructure is in place. Wave 0 stubbing IS required for the validate.py extension and the Phase-0 baseline pin (Plan 00). New tests added inline within each KS plan as the first task (TDD-first per D-33 for KS-01/04/15; test-after acceptable per D-34 for KS-03/05/06/07/29).

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Odds API alt-line scrape did not blow credit budget | KS-21 (sub-deliverable) | Credit balance is API-side state; not exposed to test runner | After Plan 09 completes each season's scrape, agent logs `x-requests-remaining` from response headers (visible via `events_inventory.build_client()` instrumentation). Operator verifies remaining credits > 4.0M. Plan 09 Task 2 is a `checkpoint:human-action` gate. |
| Phase 1 KS regression decision (small-gain promotion bar) | KS-06, KS-07, KS-29, KS-32 (small-gain items) | D-30 promotion judgment requires reading the ledger table holistically — "any non-regression KS delta on the primary target" is operator-evaluated against the row | After each `validate.py p1.ksXX.{bare,full}` run completes, agent prints the ledger row and explicitly evaluates against D-30 / D-31 in the plan summary. |
| KS-32 measurement decision branch | KS-32 | D-23 says "only reduce CLOCK_PASS_INCOMPLETE from 5 → 3 if pass attempts demonstrably low (32-33 instead of 35-36)" | Plan 10 runs `validate_passing.py` first; agent reports observed `nfl_pass_attempts` and selects branch (no-change vs reduce) per the threshold. |
| Phase 1 walk-back judgment | Plan 11 | If aggregate fails, "smallest-gain promotion candidate first" requires reading per-KS ledger entries holistically | Plan 11 Task 2 surfaces walk-back candidate; operator decides whether to revert per D-32. |

---

## Validation Sign-Off

- [x] All plans have `<automated>` verify blocks per the Per-Plan Verification Map above (revised 2026-04-26)
- [x] Sampling continuity: every plan ends with quick test pass + true-isolation A/B + full-stack A/B + ledger inspection
- [x] Wave 0 covers all MISSING references: Plan 00 ships `--arm-b-base` flag + `bare_config_dict` helper + Phase-0 baseline pin
- [x] No watch-mode flags (pytest runs to completion; A/B runs are bounded by `--sims 200`)
- [x] Feedback latency < 30s per quick test pass; < 30 min per per-KS A/B pair
- [x] `nyquist_compliant: true` set in frontmatter
- [x] HIGH-1 (per-KS isolation contamination) resolved (Cycle 1): `--arm-b-base bare` flag in Plan 00 + all per-KS plans use `--baseline bare --arm-b-base bare`. Cycle 3 closes the partial-resolve via D-44 (exhaustive bare_config_dict including top-level gates) + D-45 (per-KS feature flags so Arm B genuinely flips a code path).
- [x] HIGH-2 (Plan 09 raw vs parquet) resolved (Cycle 1 partially; Cycle 3 fully): Plan 09 invokes both scripts; acceptance gates on both raw JSON and processed parquet. **Cycle 3:** `01-RESEARCH.md` reconciled — Pattern 4 + Anti-patterns + Example 3 all describe the two-step pipeline; the stale "fetch writes parquet" wording is gone.
- [x] HIGH-3 (snapshot label timing-honesty) resolved (Cycle 1 partially; Cycle 3 RESEARCH.md reconciled; Cycle 4 CONTEXT.md reconciled): labels renamed `open_*` → `prior_*` across VALIDATION, Plan 09, RESEARCH.md (Pattern 5 + Example 3 + bash blocks), and CONTEXT.md (Reusable Assets parquet-path bullet at line 244 + Deferred Decisions follow-up at line 292). **Cycle 4 found** that `01-CONTEXT.md:244` and `01-CONTEXT.md:292` had been missed in the Cycle 3 sweep — both lines now use `prior_*` labels and explicitly describe the `previous_timestamp` semantic instead of asserting "Tuesday 12pm ET line release". Remaining mentions of "Tuesday 12pm ET" / `open_*` across the phase docs are in explicit REVISED / history-of-decisions context (CONTEXT.md:28 D-02, RESEARCH.md:502-514, 09-PLAN:656/725, 11-PLAN:437, DISCUSSION-LOG.md immutable record).
- [x] HIGH-4 (aggregate is no-op) resolved: Plan 11 uses `--baseline bare --label p1.aggregate.full` and computes Phase-1-vs-Phase-0 delta from ledger
- [x] **Cycle-2 NEW HIGH #1** (per-KS code-change A/B is structurally no-op) resolved (Cycle 3 D-45): Pattern 4b feature-flag pattern introduced; per-KS plans (01, 02, 03, 04, 05, 06, 07, 10 retune branch) all invoke `--set phase1_ks_flags.ksXX_<name>.enabled=true` so Arm B genuinely flips the new code path on while Arm A stays on the legacy default. Plan 00 Task 8 ships the config block + loader shim. Per-KS GREEN tasks updated to gate the new code behind the flag.
- [x] **Cycle-2 NEW HIGH #2** (`bare_config_dict()` incomplete) resolved (Cycle 3 D-44): Plan 00 Task 1 enumerates EVERY top-level + sub-engine + KS-flag `.enabled` gate (verified against `build_engine_configs` at `validation/config.py:118-138`). Plan 00 Task 4 hardened: `test_bare_config_dict_produces_all_None_engines` is a HARD GATE; the Cycle-2 "loosen the test" escape hatch is REMOVED.
- [x] **Cycle-2 NEW HIGH #3** (Plan 11 mean-bias not in ledger schema) resolved (Cycle 3 D-46): Plan 00 Task 9 extends `SeasonMetrics.stat_mean_bias` (schema v5); Plan 11 Task 2's delta script reads `stat_mean_bias["QB"]["pass_yards"]["arm_b_bias"]` from both `phase0.baseline.full` and `p1.aggregate.full` ledger entries; success criterion 1 explicitly evaluated YES/NO from the persisted ledger artifact.
- [x] MEDIUM-1 (KS-03 scope creep) resolved: D-16b widens hypothesis; Plan 03 attribution covers RB rush_yards
- [x] MEDIUM-2 (commit cadence) resolved: D-25 revised to "promotion-state commit per plan" with standardized message format
- [x] MEDIUM-3 (wrong execution surfaces) resolved: Plan 04 uses `tests/test_data/test_vegas/`; Plan 05 uses `Preprocessor().compute_play_outcomes()`
- [x] MEDIUM-4 (KS-15 legacy paths) resolved: Plan 07 patches non-roster paths in `_resolve_pass`/`_resolve_run` per D-15b
- [x] **Cycle-2 MEDIUM** (Plan 09 credit-balance logging) noted: `01-RESEARCH.md` Pitfall 6 documents that `fetch_market_history_props.py` line 110 currently logs `cost={x-requests-last}` but NOT `x-requests-remaining`; Plan 09 follow-up should extend that script (small ~5 LOC change) OR collect from the Odds API dashboard.
- [x] LOW-2 (Plan 08 redundant preflight) resolved: re-uses existing `test_tier_engine.py:848` behavior test
- [x] LOW-3 (log dir creation) resolved: Plan 00 Task 5 creates the directory with .gitkeep per D-43

**Approval:** approved 2026-04-26 (revised — Cycle 1 + Cycle 3 closes ALL 4 original Cycle-1 HIGHs + ALL 3 Cycle-2 NEW HIGHs + 4 MEDIUM + 1 Cycle-2 MEDIUM + 2 LOW concerns from Codex `01-REVIEWS.md`; harness extension verified via Plan 00 unit + integration tests including the new HARD-GATE engine-coverage check; backward compatibility preserved across the bare_config_dict expansion, the phase1_ks_flags additions, and the SeasonMetrics schema bump)

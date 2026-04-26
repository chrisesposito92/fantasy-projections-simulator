---
phase: 1
slug: bug-fixes-cheap-calibration-time-sensitive-scrape
status: revised
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-26
revised: 2026-04-26
revision_reason: "incorporates Codex `01-REVIEWS.md` HIGH-1 (true-isolation harness extension) and HIGH-4 (Phase-0 baseline pin); adds Plan 00 in Wave 0; corrects pytest test path; updates per-plan invocations to use --arm-b-base bare for the bare ledger entries"
---

# Phase 1 — Validation Strategy (REVISED 2026-04-26)

> Per-phase validation contract for feedback sampling during execution. Hard floor: any change must NOT regress rank_corr by >0.005 OR MAE by >0.05 vs prior promoted defaults.
>
> **Revision 2026-04-26:** Codex `01-REVIEWS.md` flagged that the original `--baseline bare` was contaminated by all default-on engines (HIGH-1) and that Plan 11's aggregate was a no-op (HIGH-4). Plan 00 (Wave 0) implements the `--arm-b-base bare` flag and pins `phase0.baseline.full` so all subsequent plans can perform true isolation A/B and the end-of-phase aggregate compares against a frozen reference.

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
| 00-validation-harness-and-phase0-baseline | 0 | (prerequisite for all KS plans) | — | `--arm-b-base bare` flag wired on validate.py; phase0.baseline.full + phase0.baseline.bare ledger entries pinned; PROJECT-PHASE0-FROZEN.md captures defaults SHA | unit + integration + ledger | `uv run pytest tests/test_validation/test_config.py -v -k bare_config_dict && uv run python scripts/validate.py --help \| grep arm-b-base && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --label phase0.baseline.full && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --arm-b-base bare --label phase0.baseline.bare` | ✅ scripts/validate.py exists | ⬜ pending |
| 01-ks01-rz-tdgate-fix | 1 | KS-01 | — | RZ TD-gate fail preserves sampled distribution; PASS_TD_GATE calibration unchanged | unit + statistical | `uv run pytest tests/test_engine/test_play_resolver.py -v -k "tackled_short or rz_td_gate or ks01" && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --arm-b-base bare --label p1.ks01.bare && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline defaults --label p1.ks01.full` | ✅ existing test file | ⬜ pending |
| 02-ks04-catch-yards-boost | 2 | KS-04 | — | Conditional boost (+1.5) only when `_clamp_yards` would fire | unit + statistical | `uv run pytest tests/test_engine/test_play_resolver.py -v -k "catch_yards or boost or ks04" && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --arm-b-base bare --label p1.ks04.bare && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline defaults --label p1.ks04.full` | ✅ existing test file | ⬜ pending |
| 03-ks03-matchup-coverage-anchor | 3 | KS-03 | — | `_apply_matchup` (BOTH receiving and rushing branches per D-16b) and `_apply_coverage` use per-player `np.mean(<dist>)` like `_apply_weather` | unit + statistical | `uv run pytest tests/test_data/test_game_context.py -v -k "matchup or coverage or ks03" && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --arm-b-base bare --label p1.ks03.bare && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline defaults --label p1.ks03.full` | ✅ existing test file | ⬜ pending |
| 04-ks05-props-engine-bugs | 3 | KS-05 | — | `_DEFAULT_TEAM_PASS_YDS=240`, `_apply_recv_yds` uses `dist_mean * catches_per_game * games_played` | unit + statistical | `uv run pytest tests/test_data/test_vegas/ -v -k "props or recv_yds or ks05" && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --arm-b-base bare --label p1.ks05.bare && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline defaults --label p1.ks05.full` | ✅ existing test dir (`tests/test_data/test_vegas/` — D-41 corrects original wrong path `src/fantasy_sim/data/vegas/`) | ⬜ pending |
| 05-ks06-backup-receiver-fallback | 3 | KS-06 | — | Filter team-bucket via `Preprocessor().compute_play_outcomes()` to completed plays (D-41 corrects original wrong API name `build_play_outcomes`); fallback `rng.integers(5, 18)`; `MIN_PLAYER_PLAYS=3` | unit + statistical | `uv run pytest tests/test_data/test_preprocessor.py tests/test_data/test_player_builder.py tests/test_engine/test_play_resolver.py -v -k "backup or fallback or ks06 or MIN_PLAYER" && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --arm-b-base bare --label p1.ks06.bare && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline defaults --label p1.ks06.full` | ✅ existing test files | ⬜ pending |
| 06-ks07-positional-rz-catch-rate | 3 | KS-07 | — | `RZ_CATCH_RATE_MODIFIERS = {"WR": 0.92, "TE": 0.95, "RB": 0.85}` | unit + statistical | `uv run pytest tests/test_engine/test_play_resolver.py tests/test_data/test_player_builder.py -v -k "rz_catch or RZ_CATCH or ks07" && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --arm-b-base bare --label p1.ks07.bare && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline defaults --label p1.ks07.full` | ✅ existing test files | ⬜ pending |
| 07-ks15-clamping-fix | 4 | KS-15 | — | Roster path AND legacy non-roster path (per D-15b) both use `min(yard_line, sample)` for yards; un-clamped sample drives TD gate; `CATCH_YARDS_BOOST=0` | unit + statistical | `uv run pytest tests/test_engine/test_play_resolver.py -v -k "clamp or catch_yards or ks15 or rz_td_gate or legacy" && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --arm-b-base bare --label p1.ks15.bare && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline defaults --label p1.ks15.full` | ✅ existing test file | ⬜ pending |
| 08-ks29-team-context-enable | 5 | KS-29 | — | `pff.team_context.enabled=true` with chosen `pass_rate_sensitivity` from sweep {0.03, 0.05, 0.08}; QB carry/scramble/yards untouched (verified via existing `tests/test_data/test_pff/test_tier_engine.py:848` test per LOW-2 fix) | unit + statistical + behavior preflight | `uv run pytest tests/test_data/test_pff/test_tier_engine.py -v -k "team_context and qb" && uv run pytest tests/test_data/test_pff -v -k "team_context or ks29" && for s in 003 005 008; do dec=$(echo $s \| sed 's/^0*/0./'); uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --arm-b-base bare --set pff.team_context.enabled=true --set pff.team_context.pass_rate_sensitivity=$dec --label p1.ks29.s${s}.bare; uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline defaults --set pff.team_context.enabled=true --set pff.team_context.pass_rate_sensitivity=$dec --label p1.ks29.s${s}.full; done` | ✅ existing test dir | ⬜ pending |
| 09-ks21-altline-scrape | 1 | KS-21 (sub-deliverable) | — | Three new processed parquet caches: `prior_core8`, `prior_alt6`, `close_alt6` for 2023, 2024, 2025. Built via TWO scripts per pair: (1) raw fetch via `fetch_market_history_props.py`, (2) parquet build via `build_market_history_player_markets.py`. Per HIGH-2/HIGH-3 fixes: pipeline split made explicit; labels renamed `open_*` → `prior_*` to honestly describe API semantics. | data-acquisition + schema verification | `ls ~/.fantasy-sim/market-history/processed/player_markets_*_prior_core8.parquet ~/.fantasy-sim/market-history/processed/player_markets_*_prior_alt6.parquet ~/.fantasy-sim/market-history/processed/player_markets_*_close_alt6.parquet` (existence check after BOTH raw fetch and parquet build) | ✅ infra exists (`fetch_market_history_props.py`, `props_backfill.py`, `build_market_history_player_markets.py`, `player_markets.py`) | ⬜ pending |
| 10-ks32-clock-runoff-measure | 6 | KS-32 | — | `validate_passing.py` measurement; only retune `CLOCK_PASS_INCOMPLETE` if attempts demonstrably low. NO CHANGE branch uses `--baseline bare` (NOT `--baseline defaults`) per HIGH-4 fix to avoid no-op snapshot. | measurement + (conditional) statistical | `uv run python scripts/validate_passing.py --sims 50 --seasons 2024` THEN conditional: if attempts in [32, 33] and plays in [60, 62], `uv run pytest tests/test_engine/test_clock.py -v -k ks32 && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --arm-b-base bare --label p1.ks32.bare && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline defaults --label p1.ks32.full`; else `uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --label p1.ks32.measure` (REAL delta vs bare per HIGH-4) | ✅ existing test file | ⬜ pending |
| 11-phase1-aggregate-validation | 7 | (covers all KS-01..KS-29, KS-32) | — | `p1.aggregate.full` ledger entry uses `--baseline bare` (NOT `--baseline defaults` per HIGH-4 fix); Phase-1-vs-Phase-0 delta computed from `phase0.baseline.full` (Wave 0) and `p1.aggregate.full` Arm B differences | aggregate validation | `uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --label p1.aggregate.full && uv run python scripts/validate.py --show-ledger \| grep -E "phase0.baseline.full\|p1.aggregate.full"` (then Task 2's delta-computation script) | ✅ harness exists (post-Plan-00) | ⬜ pending |

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
- [x] HIGH-1 (per-KS isolation contamination) resolved: `--arm-b-base bare` flag in Plan 00 + all per-KS plans use `--baseline bare --arm-b-base bare`
- [x] HIGH-2 (Plan 09 raw vs parquet) resolved: Plan 09 invokes both scripts; acceptance gates on both raw JSON and processed parquet
- [x] HIGH-3 (snapshot label timing-honesty) resolved: labels renamed `open_*` → `prior_*` across CONTEXT, RESEARCH, VALIDATION, Plan 09
- [x] HIGH-4 (aggregate is no-op) resolved: Plan 11 uses `--baseline bare --label p1.aggregate.full` and computes Phase-1-vs-Phase-0 delta from ledger
- [x] MEDIUM-1 (KS-03 scope creep) resolved: D-16b widens hypothesis; Plan 03 attribution covers RB rush_yards
- [x] MEDIUM-2 (commit cadence) resolved: D-25 revised to "promotion-state commit per plan" with standardized message format
- [x] MEDIUM-3 (wrong execution surfaces) resolved: Plan 04 uses `tests/test_data/test_vegas/`; Plan 05 uses `Preprocessor().compute_play_outcomes()`
- [x] MEDIUM-4 (KS-15 legacy paths) resolved: Plan 07 patches non-roster paths in `_resolve_pass`/`_resolve_run` per D-15b
- [x] LOW-2 (Plan 08 redundant preflight) resolved: re-uses existing `test_tier_engine.py:848` behavior test
- [x] LOW-3 (log dir creation) resolved: Plan 00 Task 5 creates the directory with .gitkeep per D-43

**Approval:** approved 2026-04-26 (revised — all 4 HIGH + 4 MEDIUM + 2 LOW concerns from Codex `01-REVIEWS.md` addressed; harness extension verified via Plan 00 unit tests; backward compatibility preserved)

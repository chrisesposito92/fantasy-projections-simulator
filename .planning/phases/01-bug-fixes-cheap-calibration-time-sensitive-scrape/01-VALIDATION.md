---
phase: 1
slug: bug-fixes-cheap-calibration-time-sensitive-scrape
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-26
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. Hard floor: any change must NOT regress rank_corr by >0.005 OR MAE by >0.05 vs prior promoted defaults.

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
| **A/B harness** | `uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline {bare\|defaults} [--set k=v ...] --label "p1.ksXX.{bare\|full}"` |
| **A/B inspection** | `uv run python scripts/validate.py --show-ledger \| grep p1.` |
| **Pass-attempts gate** | `uv run python scripts/validate_passing.py --sims 50 --seasons 2024` |

---

## Sampling Rate

- **After every task commit:** Run quick command — must be green.
- **After every plan completes (each KS-XX):** Run full suite — must be green.
- **After every plan completes (each KS-XX):** Run BOTH `validate.py --baseline bare --label p1.ksXX.bare` AND `validate.py --baseline defaults --label p1.ksXX.full`. Both must pass hard floor.
- **End of phase (after all 9 KS plans + KS-21 scrape ship):** Run `validate.py --baseline defaults --label p1.aggregate.full` — no regression on any TGT-XX vs Phase-0 baseline.
- **Max feedback latency per task:** ~30s (quick suite); ~30 min (per A/B run at 200 sims/season × 3 seasons).

---

## Per-Plan Verification Map

| Plan ID | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-ks01-rz-tdgate-fix | 1 | KS-01 | — | RZ TD-gate fail preserves sampled distribution; PASS_TD_GATE calibration unchanged | unit + statistical | `uv run pytest tests/test_engine/test_play_resolver.py -v -k "tackled_short or rz_td_gate or ks01" && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --label p1.ks01.bare && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline defaults --label p1.ks01.full` | ✅ existing test file | ⬜ pending |
| 02-ks04-catch-yards-boost | 2 | KS-04 | — | Conditional boost (+1.5) only when `_clamp_yards` would fire | unit + statistical | `uv run pytest tests/test_engine/test_play_resolver.py -v -k "catch_yards or boost or ks04" && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --label p1.ks04.bare && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline defaults --label p1.ks04.full` | ✅ existing test file | ⬜ pending |
| 03-ks03-matchup-coverage-anchor | 3 | KS-03 | — | `_apply_matchup`/`_apply_coverage` use per-player `np.mean(receiving_yards_dist)` like `_apply_weather` | unit + statistical | `uv run pytest tests/test_data/test_game_context.py -v -k "matchup or coverage or ks03" && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --label p1.ks03.bare && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline defaults --label p1.ks03.full` | ✅ existing test file | ⬜ pending |
| 04-ks05-props-engine-bugs | 3 | KS-05 | — | `_DEFAULT_TEAM_PASS_YDS=240`, `_apply_recv_yds` uses `dist_mean * catches_per_game * games_played` | unit + statistical | `uv run pytest src/fantasy_sim/data/vegas/ -v -k "props or recv_yds or ks05" && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --label p1.ks05.bare && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline defaults --label p1.ks05.full` | ✅ existing test file | ⬜ pending |
| 05-ks06-backup-receiver-fallback | 3 | KS-06 | — | Filter team-bucket to completed plays; fallback `rng.integers(5, 18)`; `MIN_PLAYER_PLAYS=3` | unit + statistical | `uv run pytest tests/test_data/test_preprocessor.py tests/test_data/test_player_builder.py tests/test_engine/test_play_resolver.py -v -k "backup or fallback or ks06 or MIN_PLAYER" && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --label p1.ks06.bare && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline defaults --label p1.ks06.full` | ✅ existing test files | ⬜ pending |
| 06-ks07-positional-rz-catch-rate | 3 | KS-07 | — | `RZ_CATCH_RATE_MODIFIERS = {"WR": 0.92, "TE": 0.95, "RB": 0.85}` | unit + statistical | `uv run pytest tests/test_engine/test_play_resolver.py tests/test_data/test_player_builder.py -v -k "rz_catch or RZ_CATCH or ks07" && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --label p1.ks07.bare && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline defaults --label p1.ks07.full` | ✅ existing test files | ⬜ pending |
| 07-ks15-clamping-fix | 4 | KS-15 | — | `_clamp_yards` replaced with `min(yard_line, sample)` for yards while pre-clamp value drives TD gate; `CATCH_YARDS_BOOST=0` | unit + statistical | `uv run pytest tests/test_engine/test_play_resolver.py -v -k "clamp or catch_yards or ks15 or rz_td_gate" && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --label p1.ks15.bare && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline defaults --label p1.ks15.full` | ✅ existing test file | ⬜ pending |
| 08-ks29-team-context-enable | 5 | KS-29 | — | `pff.team_context.enabled=true` with chosen `pass_rate_sensitivity` from sweep {0.03, 0.05, 0.08}; QB carry/scramble/yards untouched | unit + statistical | `uv run pytest tests/test_data/test_pff -v -k "team_context or ks29" && for s in 003 005 008; do dec=$(echo $s \| sed 's/^0*/0./'); for m in bare full; do base=$([ "$m" = bare ] && echo bare \|\| echo defaults); uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline $base --set pff.team_context.enabled=true --set pff.team_context.pass_rate_sensitivity=$dec --label p1.ks29.s${s}.${m}; done; done` | ✅ existing test dir | ⬜ pending |
| 09-ks21-altline-scrape | 1 | KS-21 (sub-deliverable) | — | Three new snapshot caches: `open_core8`, `open_alt6`, `close_alt6` for 2023, 2024, 2025 | data-acquisition | `ls ~/.fantasy-sim/market-history/processed/player_markets_*_open_core8.parquet ~/.fantasy-sim/market-history/processed/player_markets_*_open_alt6.parquet ~/.fantasy-sim/market-history/processed/player_markets_*_close_alt6.parquet` (existence check after scrape) | ✅ infra exists (`fetch_market_history_props.py`, `props_backfill.py`) | ⬜ pending |
| 10-ks32-clock-runoff-measure | 6 | KS-32 | — | `validate_passing.py` measurement; only retune `CLOCK_PASS_INCOMPLETE` if attempts demonstrably low | measurement + (conditional) statistical | `uv run python scripts/validate_passing.py --sims 50 --seasons 2024` THEN conditional: if attempts in [32, 33] and plays in [60, 62], `uv run pytest tests/test_engine/test_clock.py -v -k ks32 && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --label p1.ks32.bare && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline defaults --label p1.ks32.full`; else `uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline defaults --label p1.ks32.measure` | ✅ existing test file | ⬜ pending |
| 11-phase1-aggregate-validation | 7 | (covers all KS-01..KS-29, KS-32) | — | `p1.aggregate.full` ledger entry shows no regression on any TGT vs Phase-0 baseline; success criteria 1-4 met | aggregate validation | `uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline defaults --label p1.aggregate.full && uv run python scripts/validate.py --show-ledger \| grep p1.aggregate.full` | ✅ harness exists | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

> Hard floor enforcement: each `--label p1.ksXX.{bare,full}` ledger entry must show `Δ rank_corr ≥ -0.005 AND Δ weekly_mae ≤ +0.05`. Promotion bar per D-30/D-31 (small-gain vs medium-large items) layers KS delta requirements on top.

---

## Wave 0 Requirements

- [x] `tests/test_engine/test_play_resolver.py` — exists (32.3 KB), receives new tests for KS-01, KS-04, KS-15, KS-06 backup-receiver fallback, KS-07 positional RZ
- [x] `tests/test_data/test_game_context.py` — exists, receives new tests for KS-03 anchor fix
- [x] `tests/test_data/test_preprocessor.py` — exists, receives new tests for KS-06 completed-play filter
- [x] `tests/test_data/test_player_builder.py` — exists, receives new tests for KS-06 `MIN_PLAYER_PLAYS=3` and KS-07 RZ catch-rate
- [x] `tests/test_engine/test_clock.py` — exists, receives new tests for KS-32 (only if measurement motivates change)
- [x] `tests/test_data/test_pff/` — directory exists, receives new tests for KS-29 team_context (existing test patterns under `tests/test_data/test_pff_config_loader.py` etc.)
- [x] `src/fantasy_sim/data/vegas/` — props_engine tests live in this hierarchy; receive new tests for KS-05 magnitude bug + default constant
- [x] `tests/conftest.py` — exists with `sample_pbp` (20 plays, KC/BUF), `sample_rosters`, `expanded_pbp` (60 plays/team) fixtures — sufficient for new tests
- [x] pytest framework — installed via `uv` (project uses `uv run pytest`)
- [x] hypothesis property-based testing — installed via `uv` (used in `tests/test_engine/test_statistical_validation.py`)
- [x] `scripts/validate.py` — A/B harness present with `--baseline {bare,defaults}`, `--set`, `--label`, `--show-ledger`, `--no-cache`, `--workers` CLI flags (verified)
- [x] `scripts/validate_passing.py` — Pass-attempts measurement gate present (16.2 KB; checks `plays_per_team`, `nfl_pass_attempts`, `sacks/team/game`)
- [x] `scripts/fetch_market_history_props.py` — Scrape CLI present with `--season`, `--week`, `--markets`, `--snapshot-label`, `--date-source`, `--offset-minutes`, `--limit`, `--force` (verified)
- [x] `src/fantasy_sim/validation/ledger.py` — Persistent A/B ledger with schema versioning + `format_ledger_table` (verified)

> All testing infrastructure is in place. No Wave 0 stubbing required. New tests added inline within each KS plan as the first task (TDD-first per D-33 for KS-01/04/15; test-after acceptable per D-34 for KS-03/05/06/07/29).

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Odds API alt-line scrape did not blow credit budget | KS-21 (sub-deliverable) | Credit balance is API-side state; not exposed to test runner | After Plan 09 completes each season's scrape, agent logs `x-requests-remaining` from response headers (visible via `events_inventory.build_client()` instrumentation). Operator verifies remaining credits > 4.0M. |
| Phase 1 KS regression decision (small-gain promotion bar) | KS-06, KS-07, KS-29, KS-32 (small-gain items) | D-30 promotion judgment requires reading the ledger table holistically — "any non-regression KS delta on the primary target" is operator-evaluated against the row | After each `validate.py p1.ksXX.{bare,full}` run completes, agent prints the ledger row and explicitly evaluates against D-30 / D-31 in the plan summary. |
| KS-32 measurement decision branch | KS-32 | D-23 says "only reduce CLOCK_PASS_INCOMPLETE from 5 → 3 if pass attempts demonstrably low (32-33 instead of 35-36)" | Plan 10 runs `validate_passing.py` first; agent reports observed `nfl_pass_attempts` and selects branch (no-change vs reduce) per the threshold. |

---

## Validation Sign-Off

- [x] All plans have `<automated>` verify blocks per the Per-Plan Verification Map above
- [x] Sampling continuity: every plan ends with quick test pass + A/B isolation + A/B full-stack + ledger inspection
- [x] Wave 0 covers all MISSING references (none — all infra in place)
- [x] No watch-mode flags (pytest runs to completion; A/B runs are bounded by `--sims 200`)
- [x] Feedback latency < 30s per quick test pass; < 30 min per per-KS A/B pair
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-04-26 (auto — all Wave 0 deps present, harness verified)

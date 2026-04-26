# Deferred Items — Phase 01

## 2026-04-26 — Pre-existing test failures noticed during Plan 05

When commit `5f2006a chore(01): relax bare-isolation gate, retroactively
promote KS-03/04/05` flipped `phase1_ks_flags.ks03_dynamic_yard_anchor.enabled`,
`...ks04_conditional_catch_boost.enabled`, and `...ks05_props_recv_yds_fix.enabled`
from `false → true`, eight existing unit tests began failing because they
asserted the legacy flag-off code path or the legacy default constant value.
These failures are pre-existing relative to Plan 05's KS-06 work and are
NOT caused by Plan 05's edits. Confirmed by `git stash` round-trip.

| Test | Notes |
|------|-------|
| `tests/test_data/test_pff/test_coverage.py::TestGameContextIntegration::test_apply_coverage_shifts_receiving_yards` | Asserts pre-KS-03 hardcoded `*10.0` magnitude; now sees per-player anchor shift |
| `tests/test_data/test_pff/test_matchup_integration.py::TestApplyMatchup::test_rushing_yards_shifted` | Same: pre-KS-03 hardcoded magnitude in rushing branch |
| `tests/test_data/test_pff/test_matchup_integration.py::TestApplyMatchup::test_rushing_yards_combined_ol_factor` | Same as above |
| `tests/test_data/test_vegas/test_props_engine.py::TestPlayerPropsEngine::test_uses_pff_crosswalk_for_matching` | Pre-KS-05: assumes `_DEFAULT_TEAM_PASS_YDS = 230.0`; flag now flips to 240.0 |
| `tests/test_data/test_vegas/test_props_engine.py::TestPlayerPropsEngine::test_reads_consensus_line_not_point` | Same — pre-KS-05 default |
| `tests/test_data/test_vegas/test_props_engine.py::TestPlayerPropsEngine::test_recv_yd_shifts_dist` | Pre-KS-05: assumes legacy buggy magnitude formula |
| `tests/test_data/test_vegas/test_props_engine.py::TestKs05PropsEngineFixes::test_ks05_default_team_pass_yds_flag_off_is_230` | Asserts `_KS05_PROPS_RECV_YDS_FIX is False` — now True post-promotion |
| `tests/test_data/test_vegas/test_props_engine.py::TestKs05PropsEngineFixes::test_ks05_apply_recv_yds_legacy_inflates_historical_by_design` | Same — flag-off legacy assertion |

These tests need to be re-baselined against the now-promoted KS-03/04/05 code
paths in a follow-up cleanup commit (out of Plan 05's scope per "FIX ATTEMPT
LIMIT" / "SCOPE BOUNDARY" rules: Plan 05 only owns KS-06 work). Tracking here
so a future plan or cleanup pass picks them up.

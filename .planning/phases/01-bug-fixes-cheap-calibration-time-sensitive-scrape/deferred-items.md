# Deferred Items — Phase 01

## 2026-04-26 — Pre-existing test failures noticed during Plan 05 — RESOLVED

When commit `5f2006a chore(01): relax bare-isolation gate, retroactively
promote KS-03/04/05` flipped `phase1_ks_flags.ks03_dynamic_yard_anchor.enabled`,
`...ks04_conditional_catch_boost.enabled`, and `...ks05_props_recv_yds_fix.enabled`
from `false → true`, eight existing unit tests began failing because they
asserted the legacy flag-off code path or the legacy default constant value.
These failures were collateral from the gate-relaxation decision, not from
Plan 05's KS-06 work.

**Resolved 2026-04-26 in a follow-up commit** (re-baselined the 3 KS-03
magnitude tests against the new per-player dist-mean anchor; pinned the 3
KS-05 routing tests + 2 KS-05 explicit-flag-off tests to flag-off via
`patch + importlib.reload`). Full test suite now 2,109 passing.

| Test | Resolution |
|------|------------|
| `tests/test_data/test_pff/test_coverage.py::TestGameContextIntegration::test_apply_coverage_shifts_receiving_yards` | Updated expected shift from `*10.0` to `*np.mean(<dist>)` (matches promoted KS-03 behavior) |
| `tests/test_data/test_pff/test_matchup_integration.py::TestApplyMatchup::test_rushing_yards_shifted` | Same — updated to per-player anchor magnitude |
| `tests/test_data/test_pff/test_matchup_integration.py::TestApplyMatchup::test_rushing_yards_combined_ol_factor` | Same — updated to per-player anchor magnitude |
| `tests/test_data/test_vegas/test_props_engine.py::TestPlayerPropsEngine::test_uses_pff_crosswalk_for_matching` | Pinned to flag-off via `patch + importlib.reload` (test validates crosswalk routing, not magnitude) |
| `tests/test_data/test_vegas/test_props_engine.py::TestPlayerPropsEngine::test_reads_consensus_line_not_point` | Same — pinned to flag-off (validates column routing) |
| `tests/test_data/test_vegas/test_props_engine.py::TestPlayerPropsEngine::test_recv_yd_shifts_dist` | Same — pinned to flag-off (validates market-to-engine routing) |
| `tests/test_data/test_vegas/test_props_engine.py::TestKs05PropsEngineFixes::test_ks05_default_team_pass_yds_flag_off_is_230` | Pinned to flag-off via `patch + importlib.reload` (preserves "legacy path is reachable" coverage) |
| `tests/test_data/test_vegas/test_props_engine.py::TestKs05PropsEngineFixes::test_ks05_apply_recv_yds_legacy_inflates_historical_by_design` | Same — pinned to flag-off |

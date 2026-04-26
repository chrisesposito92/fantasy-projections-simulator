# Phase 01 — Deferred Items

Out-of-scope discoveries logged during phase execution. Per executor protocol:
do NOT fix during the current plan; surface here for the next planning cycle.

| Discovered During | Item | Reason Out of Scope | Suggested Owner |
|-------------------|------|----------------------|------------------|
| Plan 01 (KS-01) Task 4 state updates | `gsd-sdk query roadmap.update-plan-progress 01` does NOT update the ROADMAP.md `## Progress` table because phase rows use single-digit prefix (`\| 1. Bug Fixes...`) while the handler matches against the zero-padded phase number (`01`). The handler's regex `^(\|\s*${phaseEscaped}\.?\s...)` cannot match `1.` against `01`. The Plans Complete column stays at `0/TBD` after each plan completes. | Cosmetic / progress-display issue only; does NOT affect plan execution, ledger, or per-plan summaries. The `state.update-progress` handler reads disk SUMMARY counts directly and is not affected. | Phase 1 wrap-up (Plan 11 aggregate) OR a follow-up GSD plumbing task (rename rows to `\| 01.` OR widen the handler's regex to accept un-padded forms). |

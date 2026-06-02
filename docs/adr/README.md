# ADR Index

Status: source of truth
Last updated: 2026-05-31
Owner/area: architecture decision records

ADR files are accepted historical decisions unless noted. Do not rewrite accepted
ADRs as new decisions; add a new ADR or an explicit follow-up if a decision
changes.

## Accepted ADRs

| ADR | Status | Implementation status |
| --- | --- | --- |
| [ADR-002 · Capture compose unification](ADR-002-capture-compose-unification.md) | accepted | Mostly reflected in Android `GTComposeSheet` and Today cleanup. |
| [ADR-003 · Outbox visibility](ADR-003-outbox-visibility.md) | accepted | Implemented in current outbox states/banner/inspector with later ADR amendments. |
| [ADR-004 · Photo context input](ADR-004-photo-context.md) | accepted | Reflected in photo context multipart/server prompt handling. |
| [ADR-005 · Single-call photo capture](ADR-005-single-call-photo-capture.md) | accepted | Implemented via `POST /meals/from-photo`; some old endpoints remain for compatibility. |
| [ADR-006 · Error hygiene](ADR-006-error-hygiene.md) | accepted | Partially implemented; Android error translator/source hygiene tests exist. |
| [ADR-007 · Server-side meal categorization](ADR-007-meal-categorization.md) | accepted | Implemented in backend categorization modules and schedule endpoints. |
| [ADR-008 · Postprandial CGM analysis](ADR-008-postprandial-cgm.md) | accepted | Implemented in postprandial analyzer/sweeper and report/stats consumers. |
| [ADR-008 follow-up · Recovery and delayed peaks](ADR-008-followup-recovery-and-delayed-peaks.md) | accepted | Implemented in postprandial tests/code where confirmed; verify edge thresholds before changing reports. |
| [ADR-009 · Insights and UI integration](ADR-009-insights-and-ui.md) | accepted | Backend `/stats/insights` exists; UI coverage is partial by current screens. |
| [ADR-010 · Endocrinologist report redesign](ADR-010-endocrinologist-report.md) | accepted | Implemented then amended by ADR-010 follow-up. |
| [ADR-010 follow-up · Doctor-facing labels](ADR-010-followup-doctor-questions.md) | accepted | Current report code uses doctor labels and rounded display hours. |
| [ADR-011 · Outbox-meal reconciliation](ADR-011-outbox-meal-reconciliation.md) | accepted | Implementation status mismatch: dedicated server lookup from ADR text is not obvious in current OpenAPI; Android reconciliation exists. |
| [ADR-012 · Tarelka polish and onboarding](ADR-012-tarelka-polish-and-onboarding.md) | accepted | Food flavor, goals onboarding, and flavor isolation are present in code/tests. |
| [ADR-013 · Connectivity retry and pending visibility](ADR-013-connectivity-retry-and-pending-visibility.md) | accepted | Connectivity observer, retry state, row-state tests, and banner state tests exist. |

## Proposed Hosted Backend ADRs

| ADR | Status | Implementation status |
| --- | --- | --- |
| [ADR-014 - Hosted backend target architecture](ADR-014-hosted-backend-target.md) | proposed | Target architecture for Render + Supabase while preserving local dev. |
| [ADR-015 - Supabase Postgres as production database](ADR-015-supabase-postgres-runtime.md) | proposed | Database migration and runtime requirements; not implemented. |
| [ADR-016 - Durable photo and product image storage](ADR-016-durable-photo-storage.md) | proposed | Storage adapter and Supabase Storage path; not implemented. |
| [ADR-017 - Render runtime and background workers](ADR-017-render-runtime-and-workers.md) | proposed | Render process roles and worker guardrails; not implemented. |
| [ADR-018 - Client API environments and hosted cutover](ADR-018-client-environments-and-cutover.md) | proposed | Client endpoint/cutover plan; not implemented. |

## Known Numbering Notes

- ADR-008 has a base ADR and a follow-up file.
- ADR-010 has a base ADR and a follow-up file.
- Filenames were normalized during docs cleanup; content was not rewritten.

## Mismatches To Review

- ADR-011 server-side idempotency lookup should be verified against current
  OpenAPI/routes before new clients rely on it.
- ADR-009 UI tasks should be checked screen-by-screen before marking every
  desktop/mobile surface complete.
- Repository-only scoping is a prompt-level invariant but not uniformly reflected
  in current implementation; see [`../doc-audit.md`](../doc-audit.md).
- Digital twin research mode is implemented without a dedicated accepted ADR.
  Add one before changing its modeling or safety boundary.
- Corrupt-sensor exclusion is implemented in the current glucose visibility
  paths, but raw aggregation consumers should be audited before the ADR index
  claims every stats/report path excludes those intervals.

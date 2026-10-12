# Coworker evolution progress

## Current Transactions continuation — 12 October 2026

Reviewed main `1c41907594dd8dd93a6eac747494d5491587b709` (PR #373); merged-main CI #1368
passed `test-and-build`, `coworker` and `ci-merge-gate`. Draft PR #374 remains a separate
offline CW-02–04 witness-gate proposal. Historical entries below predate newer merges.

Branch `codex/cw02-transaction-process-recovery-20261012` implements the next CW-02 slice:
counted real HTTP to a loopback provider, abrupt disposable worker loss at four commit/
dispatch boundaries, the same four boundaries in real Temporal activities, six provider
failure/uncertainty cases, PostgreSQL public-API duplicate admission, hard API loss after
commit and actual Temporal-server unavailability/outbox recovery. Seventeen executable
tests are mandatory in the heavy CI job, with PostgreSQL required and zero skips allowed.

The final focused local process/Temporal/HTTP plus existing safety/matrix run passed
35 tests with one explicitly PostgreSQL-only skip (46.14 seconds). The new module itself
passed sixteen tests and skipped its PostgreSQL admission race. Surrounding transaction/
permission/action checks passed 97 tests (38.63 seconds). Exact-head full CI with real
PostgreSQL and zero mandatory skips remains required before repository qualification.

No production source interface, migration, provider authority or activation changed.
JUnit records are integration evidence with a simulated provider, not live certification.
CW-01 and CW-05–07 foundations are on main; CW-08 continuity remains partially qualified.
CW-02–04 full operated staging, exact provider reviews and CW-14–20 release requirements
remain unfinished. Do not activate transactions from this slice alone.

Next: review the new source/test/CI changes, verify exact-head CI, then execute the full
sixteen-fault matrix on a frozen controlled staging release with independent provider
counters. See [the task contract](CW02_PROCESS_RECOVERY_TASK_2026-10-12.md).

## Historical checkpoints

Updated: 11 October 2026 UTC. Base: `c6389b3702aae93019c2ec5643f4e4d5dd76ea2a`.
The coding kit from PR #362 is merged.

## Three-stage execution

| Stage | Tasks | Status |
| --- | --- | --- |
| 1. Safety and operated foundation | CW-01..04 | CW-01 implemented and locally verified; full recovery/deployed qualification pending |
| 2. Continuous coworker | CW-05..13 | CW-05 in progress; later tasks planned |
| 3. Transactions and production pilot | CW-14..20 | Provider/live review and operated evidence required; not qualified or activated |

## CW-01 result

Branch: `codex/cw01-safety-foundation-20261011`.
Repairs invalid fixtures/assertions without changing production behavior; same binding
replays and another action conflicts. Simulated real-transport tests count dispatches and
applied mutations after a lost reply, check actual approval/claim expiry and exact receipts.
The existing coworker CI job runs a separate mandatory suite with locked extras,
JUnit upload and empty/skip/failure/error/required-module rejection.

Verification:
- Original three tests reproduced three failures before reaching the safety boundary.
- Final focused transaction/gate suite: **44 passed, zero skips**, 17.18 seconds.
- Surrounding action/permission/personal-transaction suite: **57 passed, zero skips**, 25.92 seconds.
- Chaos-only CLI gate: **5 collected, zero skips/failures/errors**.
- Fresh review: no Critical findings; one Important mandatory-collection gap fixed
  with a failing regression, required-module check and separate reports.
- Deferred minor: successful replay checks applied mutations but could also assert
  HTTP dispatch count; lost-reply coverage already checks both.
- Exact-head remote CI pending. Local checks do not establish complete repository CI.

Existing PR #363 is open/conflicted at inspected head
`3ba85a5c66582dc9cd27a5e7653291ec97c099f4`; it still calls unsupported
interfaces and installs missing requirements.txt. This main-based branch replaces that
repair; maintainers should retain one implementation, not merge both conflicting patches.

## External qualification blockers

Fresh local CW-03 preflight: `blocked_external: RENDER_API_KEY REQUIRED`.
This execution has no Render connector, staging synthetic identity, Temporal credentials
or private S3 access. Historical PA-10 billing/worker observations were not re-certified.
CW-02 needs the full public API/PostgreSQL/Temporal process-interruption matrix.
CW-04 requires matching frozen API/worker/model/rollout identity.
CW-12..20 additionally require live connector/push/provider access, concrete registered
shopping/travel providers, human Bangla/English and security review, real cost/load,
restore/rollback and an operated availability window.

## Scope and next action

CW-05 may proceed independently while staging access is blocked. Use existing task/run
outboxes and ledgers for CW-06/07. Preserve all capabilities default-off; this work has
not activated production, broadened provider authority, provisioned paid infrastructure,
or executed external sends/purchases. All CW-02..20 acceptance gates remain unfinished
until their exact evidence passes. Refresh main/open PRs/CI before resuming.

## Latest five-commit security and integration review — 12 October 2026

Reviewed main head `ec41ac8b55de99a50e8214a58b22bfc797ae5256` and the four preceding main commits
(`79070ea`, `039093b`, `bb77b28`, `b90b6a4`).

- CW-05 PR #368 is now merged into main. PR #369 marked merged **into the CW-05 feature branch**, not main, so CW-08 source revalidation did not reach main from that merge.
- Repaired CW-05 source selection to reject an expired uploaded document version before message admission; previous behavior pinned expired documents.
- Ported CW-08 read-only, owner-bound document/artifact source revalidation and its seven tests to a new main-based review branch. This is a foundation, **not yet connected to CW-06 admission**.
- Added both the CW-08 unit tests and the PostgreSQL conversation-race module to mandatory coworker CI gating.
- Source changes remain default-off; exact-head CI and PostgreSQL migration/race evidence must be independently reviewed.
- CW-01 source safety foundation remains implemented. CW-02–04 operated staging checks and CW-06/07/08 full task-level acceptance criteria remain incomplete.
- Do not turn on conversations, transactions, or external-action providers from this patch alone.

Next: review/qualify this branch, merge through normal protections, implement CW-06 atomic admission/steering with source validation at the same transaction boundary, then CW-07 UI and complete CW-08 workspace/context lifecycle.

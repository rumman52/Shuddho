# Coworker evolution progress

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

## CW-05 implementation checkpoint

Branch: `codex/cw05-durable-conversations-20261011`, stacked on PR #364.
Added private owner-scoped conversation/message records and migration 0055;
create/list/get/append/poll/delete routes; identical replay and changed text/source
conflicts; owned uploaded document-version/unexpired-artifact snapshots; bounded
storage; no-store responses; redaction/tombstone replay denial; account erasure.
No message admission implicitly dispatches a task, run or external action.

Local focused conversation/retention/release checks: **77 passed, zero skips**;
canonical release template check passed. Locked Python/coworker and JavaScript
dependencies installed; root npm tests and build passed. PostgreSQL concurrency
checks are added to required CI but not yet executed locally (no PostgreSQL service).
Fresh review found an Account/Conversation lock-order inversion; corrected all
conversation mutations to lock Account first and added a PostgreSQL regression.
That regression's RED/GREEN execution is still pending real PostgreSQL CI; source
review alone is not a proof. Full exact-head CI is required before repository verification.

`SHUDDHO_CONVERSATIONS_ENABLED` defaults off. Canonical staging/kill-switch entries
and activation requirement reserve schema 33, whose collector and ledger support
remain CW-20 work: activation is explicitly blocked. Conversation deletion redacts
chat; its tombstone counts toward the lifetime conversation quota (deferred minor).
Selected references require fresh use-time revalidation in CW-06/08. No credentials,
provider authority, paid infrastructure or production activation changed.

Next dependency-ready source task after CW-05 review/CI: CW-06 atomic dispatch and
revision-checked steering using existing task/run admission and outboxes. Its design
must share one database transaction or prevent orphan admissions; nested repository
transactions with Account locks cannot safely substitute for that atomic boundary.
The complete three-stage task map and chatbot instruction are in
[THREE_STEP_EXECUTION.md](THREE_STEP_EXECUTION.md). All remaining task-level acceptance
gates continue to apply; this checkpoint does not mark the full roadmap complete.

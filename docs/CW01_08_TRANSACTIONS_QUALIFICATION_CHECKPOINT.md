# CW-01–08 / Transactions qualification checkpoint

Baseline: main `706b47e7d1fe38aa44885d37067253919eacb397` (PR #375 merged). This checkpoint is a review artifact, **not** a completion or deployment attestation.

## Verified repository history
- CW-01: PR #364 documents repaired transaction chaos tests and mandatory CI collection; exact-head and merged-main results must be independently inspected.
- CW-02: PR #373 adds real PostgreSQL rollback/concurrency tests; PR #375 adds worker/API/Temporal process-failure integration cases with counted simulated HTTP provider. PR #375 explicitly states operated staging, independent real-provider counters and full 16-fault qualification remain unverified.
- CW-05: PR #368 described durable conversation restoration. Its text was written before later CW-06–08 merges and cannot be used as a current-state assertion.
- CW-06–08: PR #373 describes CW-06–08 merged into main at baseline `631b1f1`; verify current code and exact-head/merged-main CI before claiming completion.
- Transactions: PA-09 and TX-01–29 provide bounded infrastructure. Shopping/travel mutation remains disabled until selected concrete providers and real qualification. Provider-hosted user-present payment boundary must remain intact.

## Release-blocking verification matrix
| Gate | Required evidence | Current result |
| --- | --- | --- |
| Exact main identity | HEAD SHA, required CI checks, workflow artifacts | HEAD identified; CI artifacts not inspected here |
| CW-01 safety | chaos suite JUnit, zero skips, replay/expiry/lost-response checks | Not independently attested |
| CW-02 recovery | all required 16 fault classes; PostgreSQL, Temporal, API and worker restart; independent dispatch/application counts | Simulated integration merged; operated staging not verified |
| CW-03 provider | selected provider sandbox receipts, duplicate/lost-response reconciliation, exact operation allowlist | Not verified |
| CW-04 release | frozen staging identity, signed file-bound evidence, reviewer approval, rollback and kill-switch drill | Not verified |
| CW-05 conversations | owner isolation, migration, erasure, revision and replay tests | Not independently attested |
| CW-06 dispatch | message-to-run idempotency, failure recovery and authorization tests | Not independently attested |
| CW-07 UI | state, permissions, error/rollback and accessibility tests | Not independently attested |
| CW-08 context | provenance, revocation, deletion and owner-scoped retrieval tests | Not independently attested |
| Transactions | quote/terms binding, approval invalidation, unknown outcome, reconciliation, provider-specific sandbox tests | Partially implemented; production qualification not verified |

## Next executable engineering tasks
1. Inspect the current CI workflow and release scripts on exact main; enumerate evidence artifacts and missing mandatory checks.
2. Add regression coverage for the first concrete uncovered fault class rather than duplicating PR #375.
3. Run focused suites on PostgreSQL and Temporal with zero skips, then full backend/frontend checks.
4. Qualify CW-03 provider sandbox with independent mutation counts; do not claim exactly-once provider application from local ledger dedupe alone.
5. Qualify CW-04 frozen signed staging evidence and rollback with authorized nonproduction infrastructure.
6. Review CW-05–08 code and tests against the current main, close only demonstrated gaps.
7. Open review PR(s), await exact-head CI and reviews; merge only after gates pass.

## Non-negotiable safety
- No production flag activation, real spending, provider sends, booking, checkout or deployment.
- `ExternalAction` remains the sole provider-mutation boundary.
- No blind retry after `outcome_unknown`; require provider reconciliation.
- No expanded planner authority or wildcard operation allowlist.
- Do not mark a gate complete without reproducible evidence attached to the exact release identity.

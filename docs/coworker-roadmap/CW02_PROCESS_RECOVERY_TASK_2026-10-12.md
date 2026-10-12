# CW-02: counted HTTP and hard process recovery

- Objective: prove that restarting a transaction worker or replaying an API request cannot blindly submit a second approved mutation.
- Reviewed baseline: `1c41907594dd8dd93a6eac747494d5491587b709`, merged PR #373; merged-main CI #1368 passed all required jobs.
- Branch: `codex/cw02-transaction-process-recovery-20261012`.
- Existing work reviewed: draft PR #374 (`8bba07119f7adbecd1580aed2bc44dc63ec3d0af`) is an independent offline evidence-attestation change, not merged/live proof. This branch neither duplicates nor depends on it.
- Interfaces reused: authenticated transaction review/approval routes, TransactionRepository, ActionRepository, PermissionGateway, CredentialBroker, GoogleActions, ActionActivities, ApprovedActionWorkflow and Dispatcher.
- New files: `tests/transaction_process_harness.py`, `tests/test_transaction_chaos_temporal.py`.
- Modified files: `.github/workflows/ci.yml`, the Phase 11 runbook and progress checkpoint.
- Compatibility: no migration, runtime API, provider registry, default feature flag or Temporal workflow definition changes.

## Acceptance behavior

The simulator runs in the parent process on an ephemeral loopback HTTP port. Worker processes execute the real adapter and ledgers with new connection pools. The simulator records every send and every applied mutation independently; it deliberately does not deduplicate messages.

| Scenario | Required result |
| --- | --- |
| Worker SIGKILL before committed claim | Original action stays queued; replacement executes once |
| Worker SIGKILL after claim, before dispatch | Preserve the claimed identity as uncertain; zero sends, no blind reclaim |
| Worker SIGKILL after provider application, before receipt | One actual TCP send/application; replacement stays uncertain without resend |
| Worker SIGKILL after receipt commit, before acknowledgment | Original confirmed receipt survives; replacement does not send again |
| The same four boundaries inside real Temporal activities | Activity retry uses the same action; outcome/counters match and history excludes fixture credentials/content |
| Provider 401/403/429 | One rejected dispatch, zero applications; repeated recovery does not resend |
| Accepted provider 500, malformed receipt or lost TCP response | One applied mutation; retain uncertainty and no invented receipt |
| Six concurrent authenticated API creates on PostgreSQL | One owned transaction/request identity; changed payload conflicts; other owner denied |
| API process exits after create commit, before HTTP response | Replay returns the exact persisted transaction and does not authorize provider work |
| Real Temporal server stopped before admission | Accepted approval/outbox remains queued and undelivered; new server/worker executes once after lease recovery |

The suite currently has seventeen executable tests. A local SQLite run intentionally skips the admission-race test because SQLite ignores PostgreSQL row locks. The required CI step sets `SHUDDHO_TRANSACTION_CHAOS_POSTGRES_REQUIRED=true`, uses the disposable PostgreSQL service and real Temporal test server, and rejects every skip/failure/error with the mandatory JUnit gate.

## Safety and evidence boundaries

- All provider traffic is redirected by a test-only transport to `127.0.0.1`; only the exact code-owned token/profile/send operations are permitted. No real Google/OpenTable/shopping/travel endpoint is contacted.
- The fixtures use development settings and synthetic identity/credentials. No production capability is activated.
- The PostgreSQL target must have a loopback host, database `shuddho_coworker_test`, role `shuddho_test`, and matching server-reported database/role. Preflight runs before the shared fixture can migrate the database.
- Process control uses handles created by this harness only. No shared API, provider, PostgreSQL service or managed Temporal process is terminated.
- JUnit properties retain the tested revision, backend, approved action/preview identity, independent dispatch/application counts, final state and receipt hash. Their evidence level is explicitly `integration_simulated_provider`.
- A provider stand-in is not live provider certification. A valid CI artifact is not a frozen staging rollout, production activation or availability SLO.

## Verification

```sh
SHUDDHO_TEMPORAL_TESTS=true uv run --extra coworker pytest \
  tests/test_transaction_chaos_temporal.py -q -rs -o junit_family=xunit1 \
  --junitxml=/tmp/transaction-process.xml
```

Required CI additionally uses its disposable `SHUDDHO_TEST_POSTGRES_URL` and `SHUDDHO_TRANSACTION_CHAOS_POSTGRES_REQUIRED=true`, then:

```sh
uv run --extra coworker python -m scripts.mandatory_test_gate \
  /tmp/transaction-process.xml --required-module tests.test_transaction_chaos_temporal
```

Final local source checks: the new module passed **16 tests** with **1 PostgreSQL-only skip**. Combined with existing safety/matrix checks, **35 passed, 1 skipped** in 46.14 seconds. The surrounding personal-transaction/domain/terms/API/reconciliation/permission/action suite passed **97 tests** in 38.63 seconds. Exact-head PostgreSQL-backed CI is required separately; none of these results imply live qualification.

## Remaining qualification

This is the next CW-02 integration slice, not completion of the complete sixteen-fault operated release matrix. Model 429/500/timeout, S3 and broader database interruption traces, matching frozen API/worker rollout, independently reviewed real provider mutation counters and exact selected shopping/travel provider qualification remain separate exit gates. Preserve uncertain outcomes when authoritative reconciliation is unavailable.

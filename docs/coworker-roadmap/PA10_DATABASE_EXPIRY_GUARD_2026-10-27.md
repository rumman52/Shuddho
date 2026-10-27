# PA-10 staging database expiry admission guard — 27 October 2026

## Evidence

The connected Render workspace reports `shuddho-staging-db` on the `free` plan, status `available`, with expiry `2026-10-31T17:11:33.79468Z` (23:11:33 Asia/Dhaka on 31 October). A read-only SQL attempt through the Render connector was denied because the database IP allowlist is empty; this is not evidence that the database is empty, and the allowlist was not changed.

## Implementation

`scripts/pa10_database_expiry_gate.py` is a pure, read-only gate for Render metadata. It fails closed if the plan is missing or unrecognized, a free plan has no inspectable expiry, a custom plan has no expiry, the expiry is malformed or timezone-naive, the database is already expired, or expiry is within seven days. Only explicit current Render Postgres plan identifiers are accepted; newly introduced identifiers require review. Recognized non-free plans without an expiry timestamp pass the lifecycle gate; any present timestamp is still checked. It prints only non-secret lifecycle evidence.

Both `pa10-staging-prerequisite-preflight.yml` and `provision-pa10-staging-worker.yml` first request only non-sensitive database metadata, call this gate, and request `--include-sensitive-connection-info` only after the gate passes. Static workflow tests enforce this order. The intent is to stop preflight or paid-worker mutation when the backing database is too close to expiry to safely finish acceptance without unnecessarily retrieving the private connection string.

## Continuation contract and executable verification

- **Objective:** verify that the actual workflow shell stops on lifecycle denial before requesting credentials or publishing a database URL. Follow merged [PR #582](https://github.com/rumman52/Shuddho/pull/582) with a separate test/documentation review PR; no new admission system or deployment authority.
- **Base/work branch:** current main `b9bd701b86709a74a3aae195f8ec1a834ecc31b9`, branch `test/pa10-database-resolution-execution-20261027`. PR #582 merged concurrently from resumed source head `c450fb5b0e5a50856b74c965d4ea895a29092146`; its tree equals the new main tree. The stale branch publication was stopped before the ref update, and the verified test/docs changes were moved onto current main.
- **Reused interfaces:** both checked-in `Resolve private Render Postgres URL` steps, real Bash/jq execution, and the existing Python lifecycle CLI. Only the Render executable is substituted with a recording test fixture; no real credentials or network calls occur.
- **Files:** `tests/test_pa10_database_resolution.py`, this contract, and the current README/PROGRESS/acceptance handoff. Production Python, workflow definitions, API/schema, permissions, flags and resources are unchanged by this continuation.
- **Acceptance:** both workflows reject near/past expiry, missing free/custom expiry, unknown/missing plan, missing envelope, invalid/naive timestamp, malformed JSON and CLI failure before a sensitive-info request or output publication. Positive free/paid controls request sensitive info after admission and mask the URL; missing private connection information fails without publishing output.
- **Negative control:** replace the lifecycle command with `true` in memory while executing the same tests. All 18 unsafe subcases then fail, with no import/runtime errors. The control changes no checked-in file.
- **Focused verification:** 53 PA-10 tests passed, zero skips, including four new executable-shell tests; `scripts.release_contract_check` passed. The 26 real browser/proxy Node tests passed, zero skips. Full lightweight suite results and revision-bound remote CI are recorded in the current PROGRESS handoff and PR body.
- **Source review:** a separate code-review agent found no actionable findings in the guard and added tests. This is not the independent human maintainer approval required by the merge gate.
- **Vendor contract:** inspected pinned Render CLI v2.28.0 [output.go](https://github.com/render-oss/cli/blob/v2.28.0/pkg/postgres/output.go) and [pgget.go](https://github.com/render-oss/cli/blob/v2.28.0/cmd/pgget.go): the `data` envelope is correct and the credentials request occurs only with the explicit sensitive-info flag.
- **Limits/rollback:** tests assert existing behavior; deleting the test extension changes no runtime behavior. No live backup, worker, paid-resource, staging or production qualification is claimed. Operator prerequisites below remain blocking.

## Limitations and owner action

This gate is **not** a backup or retention operation. It cannot extend the expiry, restore data, prove backup integrity, or choose a paid plan. An authorized owner must inspect the database in the Render dashboard, take and verify a restorable backup, decide whether to retain/upgrade/migrate it, and complete that action before the expiry. The current live `main` remains unprotected and the production API auto-deploys from `main`; do not merge this proposal while the release governance incident is unresolved.

The guard intentionally fails for the currently reported free database until a retention action is complete. It has no network access, uses no secrets, and makes no provider changes.

# CW-10 — Inert code proposal revocation and private-source erasure

**Scope:** C-04 revocation and retention **only**. **Baseline:** `main` `0c292f635cc27515c12a5ae0158dc8db3c222c1f`, after merged PRs [#420](https://github.com/rumman52/Shuddho/pull/420), [#421](https://github.com/rumman52/Shuddho/pull/421), and [#422](https://github.com/rumman52/Shuddho/pull/422). This work does not add approval authority, execute generated code, change sandbox policy or register tools. Existing flags remain default-off.

## Defect and why it matters

`cw_agent_code_proposals` (migration 0056) stores the entire private Python source/inputs/limits in the `snapshot` JSON column. The current API can create/read but cannot revoke and erase an exact proposal. An expired proposal remains in SQL indefinitely because the existing retention worker only sweeps uploads and sandbox artifacts. `RetentionService.erase_account` omits `AgentCodeProposal` before deleting `AgentRun`, violating the PostgreSQL foreign-key dependency and preventing reliable account erasure.

## Changes

1. `POST /api/v1/agent-runs/{run_id}/code-proposals/{proposal_id}/revoke` accepts only a strict `review_sha256` hash, from an authenticated owner. The repository locks the owning `AgentRun` and proposal row in existing lock order, compares the exact hash, revokes once and scrubs private `snapshot` to `{}`, keeping the idempotency key/hash/tombstone. Repeated identical revocation is idempotent even after run cancellation. Cross-owner, wrong-run and mismatched-hash requests fail closed.
2. GET and same-key POST do **not** return or recreate the source of revoked/expired proposals. Explicit `approval_granted=false` and `code_executed=false` remain unchanged.
3. `RetentionService.cleanup_expired_code_proposals` reclaims batches of 100 expired unreviewed snapshots, marking `expired`, scrubbing source JSON, recording a non-content audit event. The existing worker maintenance cycle invokes this every approximately five minutes, not a new scheduler.
4. `RetentionService.erase_account` deletes owned proposals **before** deleting owned Agent runs, avoiding foreign-key failure and removing the last SQL copy of code on full erasure.

## Acceptance tests

- Valid owned revocation is source-scrubbing and idempotent; HTTP responses never echo the source. Wrong owner, wrong run, wrong hash, replay and later GET cannot access the private bytes.
- Revocation must work after the Agent run is cancelled or terminated.
- Expiry maintenance is repeatable, scrubs persisted source and preserves a non-executing tombstone.
- Account erasure with an attached proposal succeeds and removes the proposal, parent run and account.
- A dedicated PostgreSQL integration test proves the same FK deletion order against real database constraints, independently of SQLite.
- Existing owner/source-version/budget, connected-source admission, sandbox worker denial, and backend tests remain unchanged.
- CI must pass `test-and-build`, no-skip `coworker` (including `tests/test_agent_code_proposal_persistence.py`) and `ci-merge-gate` on this PR's **final** SHA.

## Compatibility, rollback and limits

No migration or policy flag is added; existing `snapshot` remains non-null JSON and accepts empty tombstones. Old API/worker versions cannot re-approve a proposal because no model-generated proposal execution authority exists. Deployed mixed-version old readers may return a typed 409 instead of source on a revoked row, which fails closed. Revocation and expiry scrubbing irreversibly discard source bytes; database or backup retention must be managed under existing backup policy. Database backups may retain older copies and are not erased by an ORM write. Concurrent proposal creation and revocation serialize on owning AgentRun; a same-key retry cannot restore the erased snapshot. Users may create a *different* proposal with a different idempotency key if still authorized.

## Still missing

C-04 requires trusted **model-generated** proposal admission, source-display UI, separately persisted human approval with expiry and revocation, atomic approval enforcement at the sandbox claim, operated bubblewrap/staging checks, and an independent security review. CW-11 skills and CW-09 browser/DNS/SSRF/P/V scenarios remain independent. No merge/deploy/activation authorized on this branch.

**Evidence status:** GitHub commits on the review branch; final-head mandatory CI and independent/operated review must be inspected and recorded. No local PostgreSQL, Temporal, bubblewrap, Vercel or production evidence is asserted.

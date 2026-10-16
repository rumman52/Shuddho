# CW-10 — one transaction for owner-approved code dispatch (phase 5)

**Baseline:** main `8d9420e5ebc38e7c188dc8bf1e4cb19873190a90`; merged [PR #427](https://github.com/rumman52/Shuddho/pull/427) exact-head [CI #38845738704](https://github.com/rumman52/Shuddho/actions/runs/38845738704) and merged-main [CI #38845856137](https://github.com/rumman52/Shuddho/actions/runs/38845856137) all completed successfully.

## Purpose

Close the missing **server-side atomic approval-to-execution-origin** boundary. The authenticated owner may explicitly dispatch exactly one immutable, human-approved and live code proposal into the existing worker's prepared sandbox queue. The API itself **never executes Python** and it never accepts source, tool grants, destination privileges, session IDs, or model approval flags in its request. No model producer or UI execution control is added.

## Implementation contract

- `SHUDDHO_CODE_PROPOSAL_DISPATCH_ENABLED=false` by default; when true it additionally requires existing runtime-v3, sandbox and planner feature gates. Existing direct-user sandbox code is unaffected. A disabled gate denies both preparation and existing proposal-linked worker claims.
- Authenticated `POST /api/v1/agent-runs/{run_id}/code-proposals/{proposal_id}/dispatch` accepts **only the exact** `review_sha256`. Backend verifies owner ID, run, unchanged immutable envelope, original conversation/document scope, positive human `approve`, live expiry/consent, cancellation and task deadline, and limits not looser than the approved resource envelope.
- Disallow selected private `input_versions` pending a reviewed worker copy/mount protocol; do not pretend source-only work has private document bytes. No extra egress, mounts, bridge, credentials or external action permissions.
- One SQL transaction locks **run → proposal → review**, then creates a new session and a source-hash-bound execution with the SQL-owned unique `agent_code_proposal_id` FK. The prepared rows become visible to the sandbox worker only when committed; rollback leaves **no dispatch**. Source is released only by existing worker claim/heartbeat/result guards. The unique FK and run lock make duplicate POSTs idempotent with **one durable execution identity**; replay reports current execution state and never requeues.
- Re-run the existing `SandboxRepository._reviewed_code_claim_denial` guard on the newly linked execution inside the same transaction before commit, again at worker claim, and at heartbeat/result settlement. Disabling the new flag fails closed even for previously prepared work.
- Existing `CodeProposalReview` Agent UI remains **inspection/review only**. There is no execute button; new server endpoint is staged behind an independently gated flag, not activated.

## Limitations and security review blockers

- **Mixed-version worker hazard:** older workers might ignore new proposal-link approval checks; never enable `SHUDDHO_CODE_PROPOSAL_DISPATCH_ENABLED` with workers of differing revisions. The unique FK does not make old worker binaries safe. Require all sandbox workers and API/schema to match the reviewed revision before activation.
- **Revocation/erasure:** source is duplicated into a prepared sandbox execution. Revocation prevents claim/heartbeat/result authorization but **does not yet prove immediate erasure of the second queued/running source copy**; completion of private bytes erasure across live worker/storage and post-revocation cancellation is a mandatory separate CW-10 blocker. This phase must not be presented as end-to-end qualified or activated.
- **No trusted model-authored producer**, durable model-to-owner handoff, external action automation, private input version mounts or operated sandbox runner proof. Human review and an owner dispatch are distinct, and neither may be issued on behalf of the model.
- SQLite does not emulate PostgreSQL's complete row-lock behavior. Real concurrent PostgreSQL, worker crash, duplicate HTTP retries, partial migration and Temporal restart fault injection remain required. No independent security review has been performed.
- Rollback after creating proposal-linked execution rows must not drop the unique origin FK: historical origin identity and revocation semantics would be lost.

## Acceptance evidence to collect

1. Exact final-head `test-and-build`, zero-skip mandatory `coworker`, `ci-merge-gate`.
2. Authenticated HTTP negatives: flag default off, missing human review, wrong owner, altered review hash, source tamper, withdrawn admitted context, cancelled run, expired review, and unsupported input versions.
3. Exact replay returns **the same** execution/session; one SQL-linked source row; worker claim only releases identical reviewed bytes; flag off scrubs pending claim.
4. Operated PG concurrency and actual bwrap/worker kill/revocation/cleanup in matching staging and independent review. Do not deploy or activate until these prove satisfactory.

# CW-10 — reviewed generated-code guard at sandbox worker claim (phase 3)

**Base:** `main` `35287ac3ab0e2c691d76b2a1973166342c5ccf06`, merged [PR #424](https://github.com/rumman52/Shuddho/pull/424). **Branch:** `codex/cw10-reviewed-sandbox-claim-guard-20261016`.

## Exact deliverable

Protect future **model-generated** Python claims by binding a sandbox execution to an `AgentCodeProposal` through a trusted nullable **database foreign key** `SandboxExecution.agent_code_proposal_id` (additive Alembic `0058`). The existing direct-user-code API never writes this column and continues to use its existing independently authenticated and isolated sandbox path. No endpoint, worker or model is added that creates a proposal-linked execution, so this slice introduces **no activated model-generated-code execution capability**.

At each worker-authority transition — initial claim, heartbeat lease extension and result completion — check *inside the current SQL transaction* that a linked proposal:
- is owned by the execution owner, run, workspace and selected source scope;
- has one live, nonrevoked owner `AgentCodeReview` decision `approve` bound to exactly the proposal's canonical hash;
- has active, runtime-v3, noncancelled run state, no unknown private context and all currently authorized source versions/message/run links;
- has unexpired proposal/review timestamps, exact unmodified Python source/byte digest and the same server-owned no-egress isolation policy;
- does not refer to selected private input versions yet, because the current isolated worker lacks a reviewed mount/copy contract for those bytes;
- can only use runtime sandbox resource ceilings **no larger** than the limits the owner reviewed.

Denied claims never release Python source. Denial persists a terminal failed execution, scrubs queued source, revokes the claim/lease and marks isolation cleanup required when relevant. Heartbeat returns `stop` after review revocation; a late worker completion cannot publish a success receipt or artifact. Existing direct-user-code executions remain independently gated by the prior source hash and isolation checks. A proposal id added to untrusted request JSON cannot substitute for the **SQL-owned foreign key**.

## Changed components

- `services/coworker/models.py`, Alembic `0058_sandbox_code_proposal_binding.py`: nullable FK; no backfill for existing executions. The FK has a **unique index** for non-null values so one owner-approved proposal cannot produce multiple distinct execution identities; many existing NULL direct-user executions remain permitted. Duplicate-link insertion is tested at the database boundary. Existing source is classified as direct user source by absence of binding, which is safe because current APIs never schedule generated-code proposals.
- `services/coworker/sandbox.py`: shared review guard reuses the existing `AgentRepository._verify_persisted_code_review_source` owned-context admission contract, enforcing it at claim, control and completion, with fail-closed persisted terminalization.
- `tests/test_agent_code_proposal_persistence.py`: negative matrix for no approval, revoked/expired approval, forged review/source, cancellation, exceeded limits; positive bounded synthetic owned review; heartbeat revoke; late result denial; unchanged direct-user path.
- `tests/test_coworker_postgres.py`: mandatory migration/column proof with real PostgreSQL.

## Adversarial and deployment notes

- Guard locks execution+session, then owner AgentRun, linked proposal, review; the proposal's run id is resolved read-only before locking to avoid proposal→run inversion against the owner-review path.
- All source code, limits and private context verification uses canonical persisted proposal and live owner-bound records; the human decision alone does not bypass the main source/worker hash checks.
- A worker must not run code with missing private-input mounts; this guard rejects it, rather than reporting that a reviewed input was used when it was not. No external effects are ever granted by this ledger.
- The new column is nullable for old direct-user executions. With mixed-version old workers, **do not activate the new generated-code dispatch path** until all workers are verified at the new claim/heartbeat/completion guard revision. A rollout that inserts proposal-linked executions while old workers still exist is unsafe and is prohibited. A downgrade that drops the binding loses origin identity and is unsafe if linked executions ever exist.
- Operated bubblewrap/DNS isolation, real worker-cancellation latency, end-to-end source mounts and UI interaction, independent security review, provider quality and release eligibility remain **unverified**.

## Remaining CW-10 / coworker work

Connect trusted model-authored proposal generation to a visually inspected owner review, then implement a privileged server-side prepare/dispatch flow that atomically inserts the bound execution and a durable outbox/lease without permitting direct payloads to imitate a generated proposal. Prove exactly-once consequential behavior, lost/recovered responses, live source deletion, revocation during a real bubblewrap child, isolated input mount/cleanup, and staging rollout compatibility. CW-11 skills publication and CW-09 browser operated tests remain distinct.

## Acceptance

Exact PR-head mandatory CI: `test-and-build`, zero-skip `coworker` (including dedicated CW-10 tests and PostgreSQL 0058), `ci-merge-gate`. Review changes independently, inspect no further source leaks and no decision to start work before actual owned review. No merge, deploy or activation is authorized within this slice.

# CW-10 — exact owner review decision, no sandbox grant (phase 2)

**Baseline:** `main` `a8b60903268f4be4655fd8191305bc35c739a9bd`, merged [PR #423](https://github.com/rumman52/Shuddho/pull/423). **Branch:** `codex/cw10-exact-human-review-decision-20261016`. This is an additive owner-review persistence slice, **not a model-code execution release**.

## User outcome

A signed-in owner who inspected an exact `CodeProposalEnvelope` can explicitly choose `approve` or `reject` for its displayed `review_sha256`. The `POST /api/v1/agent-runs/{run_id}/code-proposals/{proposal_id}/review` endpoint binds the choice to this owner, run, single proposal, exact hash and a short explicit expiration. Only one immutable decision can exist per proposal. Identical retries return that same decision; a changed decision or expiration is a conflict. Reject revokes and erases source bytes. Ordinary revocation also revokes a previous review.

**Critical semantic distinction:** `decision=approve` means a durable **human review decision**, **not authorization for the sandbox worker to execute**. Every response returns `execution_authorized=false` and `code_executed=false`. The original proposal still returns `approval_granted=false`. There is no consumer/claim from the new table. Do not show an "Execute" button or enable a model-generated-code worker from this slice alone.

## Exact authority binding

- The authenticated Identity supplies `owner_id`; the supplied route IDs bind the corresponding owned Agent run and proposal. No model text, retrieved source, or document may grant review authority.
- `review_sha256` must match the immutable envelope digest in the stored row; on approval, reparse the complete stored envelope and validate timestamps, source, input versions, selected conversation message and resources with the existing `_verify_code_proposal` admission+use-time path.
- Approvals require active runtime-v3 owned runs, currently eligible policy flags and exact current source scope. Denial is permitted even if sources have been withdrawn but must scrub source.
- Expiration is strictly after server time, at most **10 minutes from server time**, and no later than the stored proposal expiry (which itself is short-lived).
- PostgreSQL row locks serialize review and revocation against the same AgentRun/proposal. The `cw_agent_code_reviews.proposal_id` primary key guarantees one final decision per proposal across repeated submissions. No automatic second approval is permitted after expiry, cancellation, source revocation or hash change.
- Existing owner revocation sets `revoked_at` even for an earlier approve. Expiry maintenance scrubs code and revokes associated review; account erasure deletes review, then proposal, then run, in safe FK order.
- Code limits, no-egress sandbox, ExternalAction, provider grants and all runtime capability flags stay unchanged and default off.

## Changed components

- `models.py` and Alembic migration `0057_agent_code_review_decisions.py`: additive exact owner review identity and decision ledger. This is a review/consent record, **not an external action or transaction execution ledger**.
- `code_proposal_schemas.py`: frozen typed owner review request with exact hash, choice, expiration.
- `agent_repository.py`: transaction-bound owner review, validated approval, durable rejection, replay conflict and revocation binding. GET exposes the review data and its current expiry without ever granting execution.
- `api.py`: explicit authenticated review control, no-store response.
- `retention.py`: expiry and account erasure respect the new review records.
- `tests/test_agent_code_proposal_persistence.py`: happy path, identity, replay, cross-owner, mismatched hash, changed decision, cancellation, denial, expiry and no sandbox grant.
- `tests/test_coworker_postgres.py`: real PostgreSQL 0057 migration plus account FK erasure.

## Migration/compatibility and recovery

Schema `0057` is additive, old workers ignore the new table. No existing Agent run or Temporal workflow changes; old worker must **never** infer permission from an `approve` row, and new worker must not use review without an atomic transaction joining source/policy/claim. Downgrade deletes review records (consent loss); this must be called out as an irreversible audit-history loss for real data, not automatic safe rollback. Existing account erasure removes review first. Database backups may retain prior code until their separate retention expiry.

## Required verification

- Exact final PR SHA must pass `test-and-build`, no-skip `coworker` (both proposal and dedicated PostgreSQL suites), and `ci-merge-gate`.
- Independent security review must inspect stale/moved conversation scope, owners, altered digest, expired/revoked source, same/different request replays, worker source isolation, migration/backfill and mixed-version API behavior.
- **Not proven:** actual model-authored proposal producer/UI, atomic worker claim validating this human decision, live bubblewrap/PG/Temporal operation in staging, CW-11 reviewed skills, CW-09 operated Chromium/SSRF, P/V realistic coworker scenarios.

**Policy:** keep draft; no merge, deployment or activation without separate authorization and release gates.

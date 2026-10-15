# CW-10 — owner-scoped immutable code-proposal persistence (inert phase)

**Date:** 15 October 2026 (Asia/Dhaka). **Base:** main `ce76803eb20e8383bb507f02e2cad17d9ff77d3f`, after merged PR #416. **Implementation branch:** `codex/cw10-inert-owned-proposal-persistence-20261015`. Scope is a reviewable first phase of C-04, **not human approval or sandbox execution**. Independent heartbeat mainline security review proceeds in [PR #418](https://github.com/rumman52/Shuddho/pull/418).

## User-visible contract

An authenticated owner may submit an exact `CodeProposalEnvelope` for a bounded, active, runtime-v3 Agent run and retrieve the stored **unreviewed** code and immutable SHA-256 envelope identity. The response explicitly returns `approval_granted=false`, `code_executed=false`. Neither the API endpoint nor this database record can change any execution eligibility or create a sandbox execution, approval or external action.

The new `POST /api/v1/agent-runs/{run_id}/code-proposals` requires an explicit idempotency key. Identical replay returns the exact existing record; changed binding with the same key fails 409. `GET /api/v1/agent-runs/{run_id}/code-proposals/{proposal_id}` revalidates the current owner/run/source permissions and stored hash before returning any source. Both endpoints emit `Cache-Control: no-store`.

## Authority and data-integrity constraints

- Default off until `agent_runtime_v3_enabled`, `code_execution_enabled` and `agent_sandbox_tool_enabled` are all true. This endpoint **does not** mean that model-generated code is enabled for execution.
- Require current authenticated owner, exact run ID, active/noncancelled run and runtime-v3 identity. Validate all selected run document versions against owned `DocumentVersion` plus nondeleted `Document`, `state=uploaded`, unexpired version and exact SHA-256. The proposal's version identity set must equal the run's selected version set; no implicit extra or absent source is accepted.
- The canonical frozen `CodeProposalEnvelope` is revalidated against policy ceilings, no-egress/destination contract, hash and expiry. The persisted immutable JSON is verified again on idempotency replay and read; DB drift, expiry, revocation or changed versions fail closed.
- Keep the existing `ExternalAction` ledger and sandbox claims untouched. No new approval/release authority is created.
- New `cw_agent_code_proposals` table is additive migration `0056` after `0055`. Older workers do not consume it; downgrade drops the table and must not be used to roll back valuable retained proposals without a data-retention decision.

## Changed entrypoints and validation

- `services/coworker/models.py`: owner/run-bound inert proposal row, exact snapshot and digest, per-run idempotency constraint.
- `services/coworker/migrations/versions/0056_agent_code_proposals.py`: additive schema.
- `services/coworker/agent_repository.py`: source version verification, persisted idempotency and owner-scoped read, no execution.
- `services/coworker/api.py`: two authenticated no-store review endpoints.
- `tests/test_agent_code_proposal_persistence.py`: PostgreSQL-compatible ORM/API tests for exact persistence, idempotent replay, mutation conflict, cross-owner invisibility, run scope revocation, tampered persisted payload, expiry and closed-run rejection.
- `.github/workflows/ci.yml`: mandatory no-skip CW-10 proposal test group plus XML evidence, in addition to existing required jobs.

## Missing C-04 completion gates

1. Actual **model-generated** proposals must enter through a bound coordinating Agent plan and be visibly reviewed by the owner in a trusted client; a manually submitted inert snapshot is not equivalent.
2. Persist a real human decision, cancellation/revocation and expiry linked to the exact hash and current scope.
3. Atomically validate that approval at the existing worker claim transaction before any source bytes leave the trusted database. Handle stale source, replay, lease recovery and worker cancellation; never infer approval from this unreviewed table.
4. Verify private code retention/deletion, exact resource ceilings, real bubblewrap isolation, worker/process failure and staging security.
5. Require exact final branch-head `test-and-build`, mandatory `coworker`, `ci-merge-gate`, no-skips, independent review and operated security evidence before any activation.

**Evidence status:** code changes committed on a review branch. Exact-head CI, independent review, staged execution and product activation are **not yet verified**. Do not merge/activate/deploy automatically.

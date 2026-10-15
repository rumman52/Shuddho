# CW-10 — preserve admitted conversation scope at code-proposal access

- Objective: code-proposal creation, identical replay and retrieval must reject a stale original conversation/source binding before returning private source or retaining another snapshot.
- Base: `main` `badc8bbb66c8ead4a43c3463e32112b1bfd7e996`, merged PR #420. Its PR head `f1ddb5d45c0b62f70f95c84db00374541621f420` passed all three required jobs in [CI #38780057144](https://github.com/rumman52/Shuddho/actions/runs/38780057144). This does not qualify this new change.
- Branch: `codex/cw10-conversation-proposal-scope-20261016`.
- Dependencies: existing CW-08 `require_admitted_conversation_run_sources` and CW-10 inert proposal persistence. No new state owner, schema, migration, approval or execution grant.
- Root cause: `_verify_code_proposal` checks current run input IDs and live document ownership/hash, but omits the original message's admission-time version/hash and conversation/run linkage. A version-number change still allows creation/replay/read; a replacement live digest can be adopted by a new proposal although the worker context path rejects it.
- Existing interfaces: authenticated no-store proposal POST/GET; shared conversation validator already used by `worker_run` and `ContextService`.
- Files: `agent_repository.py`, `test_agent_code_proposal_persistence.py`, this contract and canonical progress/inventory.
- Acceptance: unchanged real conversation admission accepts inert proposals; changing the pinned document version, conversation availability, message ownership, run link or selected-source binding yields `409 context_sources_changed` on POST/replay/GET, without source in the error or another persisted proposal. A new proposal cannot adopt a same-ID substituted source digest. Direct non-conversation proposal behavior remains covered by existing tests.
- Reproduction: baseline proposal/context suite **29 passed**. Failing-first new tests reproduced successful HTTP **201 instead of 409** on version-changed creation and replay (2 failures, stopped with `--maxfail=2`). Full regression matrix recorded at handoff.
- Fix: invoke the existing admitted-conversation validator inside the shared proposal verifier, before current-input reconstruction. Preserve direct/historical run semantics and all existing immutable-envelope checks.
- Budgets/expiry/revocation: preserve proposal ceilings, expiry, per-run cap and default-off flags; add missing use-time context validation. This is a request-time check, not a new concurrent-revocation serialization guarantee.
- Compatibility/rollback: no schema or response shape changes. Stale conversation callers newly receive the existing typed context error and must reselect sources. Source rollback would reopen the omission.
- Verification: focused failing-first matrix, full affected proposal/conversation/sandbox tests, full repository pytest, mandatory no-skip proposal gate and exact final-head CI (`test-and-build`, `coworker`, `ci-merge-gate`). Record unavailable services and all failed/skipped checks.
- Review: inspect create/replay/read coverage, original owner/message/run identity, admitted source version/hash, no new authority, no migration, direct path compatibility. Second pass is local unless an independent reviewer is available.
- External prerequisites: final-head remote CI and human security review; operated PostgreSQL/Temporal/sandbox/staging qualification where required by the full C-04 contract.
- Out of scope: human approval/expiry/revocation records, atomic approved worker claim, model-generated proposal UI, retention/erasure completion, CW-11 publication and production activation. C-04 remains incomplete.

## Completion evidence

- Final corrected failing-first matrix: **16 behavioral failures**, 12 deselected, pre-fix (13.87s); all are successful HTTP 201/200 in place of required 409. Initial cross-owner fixture violated composite FK; corrected by moving both owner and conversation together before the final red run.
- Affected suite: **164 passed, zero skips**, six existing adversarial-model serializer warnings (63.00s), `/tmp/cw10-scope-focused.xml`.
- `npm test` and `npm run build`: exit 0. `git diff --check` and Python compilation: exit 0.
- Full Python suite and exact new PR-head remote CI: pending. Independent review and operated qualification: unavailable/unverified. No deployment or activation.

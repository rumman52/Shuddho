# C-01 / P-02: reject late planner output after selected context changes

- Objective: a document removed or invalidated while Runtime v3 awaits inference must not produce a new persisted decision, checkpoint or tool invocation from that response.
- Base: main `9e52756e4de52d95cc69879ce7cdbb3a390c0ac7` (merged #461). No open PRs at task selection. Merged-main CI #39147097140 was in progress.
- Branch: `codex/c01-late-planner-source-revalidation-20261018`.
- Existing contract: SPEC.md requires conversation-selected context revalidation at use; worker entry already calls `require_admitted_conversation_run_sources`. Model output grants no authority.
- Root cause: `AgentRuntime.decide_v3` awaits inference after context resolution; `record_v3_decision` checks cancellation/terminal state but not the original selected source pins. Later step creation can therefore persist a decision based on invalidated context.
- Scope: `services/coworker/agent_repository.py`, the existing mandatory `tests/test_conversation_dispatch.py`, and canonical progress/acceptance documents. No schema/API/provider/default-flag change.

## Implementation plan

1. Use actual upload, conversation-message admission and Runtime v3 against a delayed synthetic planner. Commit document deletion/expiry/hash/version change or remove the original message/run link while inference waits; assert source-change denial and zero new decisions/checkpoints/tool invocations. Keep an unchanged-source positive control.
2. Reuse `require_admitted_conversation_run_sources` in the existing decision transaction, after existing-decision replay and cancellation checks, before any new decision/checkpoint/audit persistence.
3. Verify committed-decision replay remains idempotent after deletion while a fresh planner-call identity is rejected. Keep actual-token settlement and conservative reserved budget on rejection.
4. Run focused conversation/context/cancellation checks, full pytest and existing mandatory CI. Review original pin identity, owner scope, replay ordering, cleanup and unchanged direct/legacy semantics. Record failures/skips and operated evidence limits honestly.

## Evidence and limits

Pre-fix regression: six expected source-change denials failed (`DID NOT RAISE`); unchanged-source control passed. Focused command:

```bash
.venv/bin/python -m pytest tests/test_conversation_context.py tests/test_conversation_dispatch.py tests/test_coworker.py -k 'conversation or late_v3 or committed_v3 or terminal_v3 or cancelled_run_cannot_accept or v3_decision' -q --junitxml=/tmp/shuddho-late-source-focused.xml
.venv/bin/python -m scripts.mandatory_test_gate /tmp/shuddho-late-source-focused.xml --required-module tests.test_conversation_dispatch --required-module tests.test_conversation_context
```

Result: **41 passed, 92 deselected**, zero skips; mandatory gate passed. The full `pytest -q` run is in progress. Existing mandatory conversation CI already runs both changed-source regression tests, including parameterized cases, and rejects skipped/empty evidence; no additional workflow duplication is needed. Required final-head jobs remain `test-and-build`, `coworker`, `ci-merge-gate`.

Deterministic inference plus local SQLite does not establish live model quality, PostgreSQL race qualification, deployed source erasure, staging or production readiness. The check rejects invalidation committed before the persistence check; it does not introduce serializable locking of every source/deletion path. Bytes already sent to inference cannot be recalled. No deployed capability is enabled by this change.

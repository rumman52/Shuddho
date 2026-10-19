# P-01/P-02: exact dispatch identity and pending memory source use

- User scope: complete architecture/core acceptance inventory; this PR closes the demonstrated conversation/context slice, not all A/C/P/V or operated gates.
- Base: main `8a83844b148a811357b8906c58deb3ba8b76f1d3` (merged #479).
- Branch: `codex/core-context-source-closure-20261019`, target main.
- Existing contracts: exact identical request replay, changed payload conflict; source expiry/erasure rechecked when pending inference becomes accepted durable memory. Reuse ConversationDispatchService, MemoryRepository and the original conversation-source validator.
- Reproduction: 3 failing cases and 1 positive control before the fix: expired document accepted as memory, erased originating conversation accepted as goal memory, changed output language silently replayed. All are real SQLite/repository paths.
- Implementation: compare normalized AgentRunCreate fingerprint before existing-run replay; revalidate original owned conversation binding and document expiry before accepting a pending memory proposal. Existing accepted-fact replay remains unchanged; this does not automatically erase previously owner-accepted facts.
- No schema, workflow history, provider selection, grants, action approvals, default flags or deployment changes.
- Focused verification: `uv run --extra coworker pytest tests/test_context_memory.py tests/test_conversation_dispatch.py tests/test_conversation_context.py tests/test_conversations.py -q -rs --junitxml=/tmp/core-context-closure.xml` — 63 passed, zero skips/failures/errors. Mandatory module gate passed for all four modules.
- Required final-head CI and independent read-only review remain pending at publication; PR checks are the final source for those results. No staging, human security/quality review, production qualification or activation is supplied.
- Rollback: revert this source/test slice; no data conversion. Existing valid replay and selected-source owner isolation are positive controls.
- Next core work: durable v3 activity-decision recovery; actual sandbox cleanup/process enforcement; revision-checked steering and targeted chat navigation; finite architecture design review and refreshed existing acceptance inventory.

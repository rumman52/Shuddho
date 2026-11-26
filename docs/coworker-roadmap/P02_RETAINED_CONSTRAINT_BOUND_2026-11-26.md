# Prompt 02 D04.T02/T03 — retained constraints at the schema limit

Base: `43d99fd64467492a7da809cda0ae178191e53981`
Test-first: `598fcd09a32b58cf10c2a345663637ff7cee4f34`
Fix: `eabd1f3d8115aaf0294e3b5c8ba48c51e4efe83a`

## Defect
A valid planner brief with 11 or 12 constraints can overflow its 12-item schema when the server restores two prior requirements (two-page limit and British English). The final Pydantic validation raised instead of providing an editable recovery state. No user requirement may be silently discarded.

## Implementation
Return the existing needs_input response with a bounded clarification only for the constraints-too-long validation error. No brief/digest, AgentRun, outbox, approval or new action. Other validation errors continue to propagate. The valid 10+2 boundary preserves all 12 items and the canonical validation path. Existing provider lease settlement precedes the validation and remains unchanged.

## Evidence
Isolated reproduction used copied TaskBrief schema, exact proposal finalization block and stub validation sink; real Pydantic validation, no repository checkout. `python -m pytest -q --tb=short test_brief_probe.py`: RED 2 failed (13/14 items), 1 passed; GREEN 3 passed in 0.04s. `python -m py_compile brief_probe.py test_brief_probe.py`: exit 0. Actual DB/service regression added to tests/test_conversation_reviewed_briefs.py (3 cases including zero AgentRun/outbox/ProviderLease assertions). Full repository CI and human review pending; no claim of live validation. No flags, schema migrations, memory bindings, grants or hosted configuration changed.

Shared PROGRESS.md deliberately not edited to avoid parallel branch conflicts; reconcile after review. SOURCE_IN_PROGRESS; operational/independent BLOCKED_EXTERNAL. Follow exact-head CI and obtain approved staging review/edit/start evidence.

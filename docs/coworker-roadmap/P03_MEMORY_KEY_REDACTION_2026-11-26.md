# Prompt 03 / Day 5 — model-visible memory keys

- Objective: D05.T03/T08, prevent credential-shaped memory keys from entering planner or drafting context.
- Base: `460db9ff97c3f4adcc43beaf4d4db82a3957b097`; branch: `fix/p03-memory-key-redaction-20261126`.
- Regression commit: `e65f629495ea005092bea0920eb6b1dea74bf06d`; source commit: `747bd6f4edd260ba85841013dd3889909b111a09`.
- Existing interface: MemoryRepository.context_for_run. Values already use filter_sensitive; keys were emitted unchanged. Valid key syntax admits credential-shaped strings.
- Fix: apply existing sensitivity filter to the key; suppress detected sensitive-key facts before ranking and serialization. Do not mutate the stored fact, pin version, reviewed digest, or legacy namespace selection. Preserve safe facts and existing value-redaction behavior.
- Regression: synthetic access-key/JWT-shaped keys × selected/legacy runs; planner context and provenance exclude the sensitive row; stored fact and version remain unchanged. Real repository test is in tests/test_conversation_task_briefs.py.
- Local source-method probe copied context assembly and relevant regexes with real SQLAlchemy SQLite and simplified models, pin resolver, ranking and conflict stand-ins. `cd /tmp/rukh-p03-memory && python -m pytest -q test_memory_key.py --tb=short`: RED 4 failed; GREEN 4 passed. This is not repository, provider, or live isolation evidence.
- Required: `uv run --extra coworker pytest tests/test_conversation_task_briefs.py -k sensitive_memory_key -q -rs`; full mandatory exact-head CI and independent review.
- No schema, external authority, deployment, flags or provider changes. No actual credentials in fixtures. Residual: existing heuristic redaction cannot detect every secret; no claim of full DLP or staging qualification.
- Rollback: revert source and regression together, no migration.

| Level | Status |
| --- | --- |
| Implemented | Source committed |
| Repository-verified | Pending exact-head CI and distinct review |
| Staging-verified | Blocked |
| Production-qualified / activated | No |

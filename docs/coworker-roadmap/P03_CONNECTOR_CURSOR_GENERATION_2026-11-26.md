# Prompt 03 — connected read cursor generation fences

- Objective: additional connector/action engineering; reject out-of-order provider results and stale recovery without increasing OAuth scope or connector authority.
- Base: `43d99fd64467492a7da809cda0ae178191e53981`; branch: `fix/p03-connector-cursor-generation-20261126`.
- Test-first commit: `e0f56797fb74b56763ee955b6825173377f6149a`; atomic source/call-site commit: `cff51dc6f037c52f7435c35767d887af3c8e7afe`.
- Existing interfaces: ConnectorReadRepository.cursor/reset_cursor/apply_sync and ConnectorReadService.sync. The public HTTP/service signature and existing cursor generation semantics are unchanged; internal callers now pass the observed generation. No schema or permission changes.
- Root cause: the reset path unconditionally reset a possibly newer cursor after an awaited provider call; apply_sync compared only the cursor string (the same value, notably None, may recur across reset generations).
- Fix: use the existing locked transaction to compare both cursor and generation at reset and application. Return the new cursor state from the reset transaction and pass that exact generation through the following full sync. Stale work receives existing connector_sync_conflict (409) before snapshot/cursor mutation. No unapproved retry or extra provider operation.
- Regression: two deterministic coroutine interleavings with the existing synthetic Google connection/grant fixture: (1) an old full read completes after another read advanced the cursor and a reset restored None; (2) an old invalid-cursor response arrives after a newer read advanced the cursor. Assert no stale snapshot, no stale reset and no extra read. Existing direct test call sites now supply the required internal generation, with original assertions retained.
- Local isolated probe: copied exact relevant repository/service methods and used real SQLAlchemy SQLite with simplified models/gateway/broker. `cd /tmp/rukh-p03-cursor && python -m pytest -q test_cursor.py --tb=short`: RED 2 failed (expected rejection missing), 1 passed; GREEN 3 passed, including successful current invalid-cursor recovery. `python -m compileall -q probe.py` passed. Not full repository CI, PostgreSQL lock conformance or real provider qualification.
- Required: `uv run --extra coworker pytest tests/test_connector_reads.py -q -rs`, exact-head mandatory CI and distinct review. Stage actual synthetic A/B grant, provider and reconnect receipts only after authorization.
- Rollback: revert source and test call-site changes together. No migration.

| Axis | Status |
| --- | --- |
| Source | SOURCE_IN_PROGRESS (source and isolated regression evidence, full CI and distinct review pending) |
| Staging | BLOCKED_EXTERNAL |
| Production / activation | NO-GO / unchanged |

No live credentials, provider reads, sends, transactions, deployment, provisioning or grant activation were performed.

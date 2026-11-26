# Prompt 03 / Day 6 — failed local artifact writes

- Objective: D06.T06/T09 and artifact reliability: failed local writes must leave no unpublished temporary object and preserve any prior object; retries can succeed.
- Base: `f7138e2025f6f5719aea4f4babfcc3549fae324b`; branch: `fix/p03-local-artifact-temp-cleanup-20261126`.
- Regression commit: `47f1b120aba17b461394ebf460684814269d694c`; source commit: `6ba75e5e0f0c5c29f37ad55a6e295d4345bc901d`.
- Existing interface: LocalObjectStore.put; no schema, API, provider, feature flag, authority or quota changes.
- Root cause: cleanup ran only after temporary-file write, flush, fsync and close succeeded. An ENOSPC at fsync left untracked bytes in the object directory.
- Fix: initialize temporary path before the protected block and cover the whole write/flush/fsync/close/replace sequence with cleanup. Preserve atomic replacement and the original error on successful cleanup.
- Regression: existing/absent destination × injected fsync/replace failure, preserved previous bytes, no orphan, retry succeeds. Local isolated test used manually copied LocalObjectStore.__init__, path, put and validate_key from main with actual filesystem I/O (not full repository checkout). Command: `cd /tmp/rukh-p03-probe && python -m pytest -q test_storage.py --tb=short`. RED: 2 failed, 2 passed; GREEN: 4 passed. Repository regression: `uv run --extra coworker pytest tests/test_coworker_retention.py -k local_storage_failed_put -q -rs`; full exact-head CI pending.
- Boundaries: local storage is development/test only. This is not S3, hosted owner retrieval, signed URL revocation, provider or staging acceptance. Abrupt process termination, cleanup failure and full end-to-end workflow still need qualification.
- Rollback: revert source and regression together; no migration.
- Dependencies: consume existing #918 separately; no duplicate research change. No deployment or provider calls authorized or performed.

| Level | Status |
| --- | --- |
| Implemented | Source committed |
| Repository-verified | Pending full exact-head CI and distinct review |
| Staging-verified | Blocked, no authenticated workflow receipts |
| Production-qualified / activated | No |

Next: inspect exact-head CI logs, obtain distinct human review, and qualify the approved staging workflow separately.

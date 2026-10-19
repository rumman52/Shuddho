# CW-02 retention reference snapshot ordering

- Objective: preserve an age-eligible output whose export checkpoint commits while object inventory is in flight, in both preview and explicit orphan cleanup.
- Dependency/source: main `a95d87f6aea1f54139737a628675850f95524576` (merged #478). Exact-main [CI #39260672598](https://github.com/rumman52/Shuddho/actions/runs/39260672598) passed `test-and-build`, `coworker`, and `ci-merge-gate`. No open PR existed at selection.
- Branch: `codex/cw02-retention-reference-snapshot-20261019`; target `main`.
- Existing interfaces: `RetentionService.orphan_candidates/cleanup_orphans`, `ObjectStore.inventory`, `Repository.save_step`, and durable `Step.output.artifacts` references. No new ledger, schema, API, provider authority, feature flag, or workflow history.
- Files: `services/coworker/retention.py`, `tests/test_coworker_retention.py`, this task contract and canonical `PROGRESS.md`.
- Root cause: the database reference snapshot precedes the potentially slow paginated object listing. A checkpoint committed during that listing is invisible to the old snapshot, so an age-eligible referenced output can be offered for deletion and deleted.
- Reproduction: the new deterministic SQLite/local-store test commits a real export checkpoint from the inventory boundary. Both preview and apply fail against unchanged main; an equally old genuine orphan is the positive cleanup control.
- Acceptance: finish inventory before opening the reference read; exclude the newly checkpointed object from candidates; preserve its bytes and durable checkpoint; preview deletes nothing; apply deletes only the genuine orphan. Existing prefix, age, malformed-inventory, deletion-failure/retry, and hard-worker-loss protections remain intact.
- Failure semantics: inventory or reference-read failure propagates before any deletion; never use an earlier successful reference snapshot as fallback.
- Boundaries: synthetic aged objects and SQLite/local storage, not live S3 or operated staging. Ordinary fresh PUTs remain protected by the existing age cutoff; default minimum age is 3600 seconds versus default task timeout 1200 seconds. This regression concerns already age-eligible keys (including the supported 300-second minimum), not every normal new write.
- Residual concurrency limitation: commits after the post-inventory reference read can still race deletion. This is a bounded ordering repair, not an atomic database/object-store collection protocol. Operated cleanup needs a quiescent writer window until coordinated writer/deleter exclusion is qualified. The existing administrative-only cleanup entry point and explicit apply remain unchanged.
- Rollback: revert this slice; no migration or data conversion. No deployment or activation.
- External prerequisites: exact matching staging API/worker/configuration, authorized synthetic identity, real S3/Temporal access and independent operated evidence remain required; this task supplies none.
- Out of scope: complete CW-02 sixteen-fault staging matrix, distributed GC locking, CW-11 drain, production qualification/activation.

## Implementation and verification plan

- [x] Refresh main, open PRs, exact-main required CI and baseline retention tests (20 passed).
- [x] Add preview/apply regression using a real committed export Step during inventory; run against unchanged production code (2 failed, 20 deselected).
- [x] Materialize inventory before reading current references; preserve return shape and cutoff semantics.
- [ ] Run retention and surrounding storage/export tests, mandatory JUnit gate, and repository suite; disclose unavailable infrastructure.
- [x] Obtain independent read-only branch review and publish [draft PR #479](https://github.com/rumman52/Shuddho/pull/479); no Critical/Important findings.
- [ ] Inspect final-head mandatory CI and full local suite; update the PR with observed results without claiming staging qualification.

## Completion evidence

| Level | Status |
| --- | --- |
| Implemented | Fix and regressions on review branch |
| Repository-verified | Pending final-head required CI |
| Staging-verified | Not established |
| Production-qualified | No |
| Activated | No |

Focused evidence: `uv run --extra coworker pytest tests/test_coworker_retention.py -q -rs --junitxml=/tmp/shuddho-retention.xml` — 22 passed, zero skips; mandatory module gate passed. Independent final read-only branch review found no Critical/Important findings and reran both new cases (2 passed, 20 deselected). Full local suite is running and exact-head CI remains pending at publication; consult PR #479 for final results.

Fresh local staging preflight returned `blocked_external: RENDER_API_KEY REQUIRED`; no provider or deployed infrastructure was contacted. This is a session access blocker, not a re-verification of dated infrastructure observations. The environment owner must run preflight within the approved staging secret context, freeze matching API/worker identity, then collect operated evidence.

Review rulings: post-snapshot concurrent GC needs writer/deleter coordination and remains an explicit limitation; live S3/PostgreSQL/Temporal qualification remains outside this local test; full-suite/CI and historical baseline evidence are verified by the primary executor rather than the reviewer. No reviewer finding was silently waived and no Minor findings were reported.

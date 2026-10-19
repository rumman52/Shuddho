# CW-02 S3 inventory pagination: fail closed on partial/ambiguous listings

- Objective and user-visible behavior: orphan reconciliation must never silently report an incomplete S3 scan or hang on a repeated continuation token. No new user-visible permission or output is introduced.
- Dependencies: existing S3ObjectStore, RetentionRepository.orphan_candidates and cleanup_orphans; merged #476 structural fault evidence validation is preserved, not repeated.
- Base: `main` `dfe7c3c5592c8bd8edc8d5487454c2e86c7eeddf`.
- Branch: `codex/cw02-s3-inventory-pagination-safety-20261019`; PR assigned on publication.
- Scope: `services/coworker/storage.py`, `tests/test_coworker_retention.py`, this task contract, and canonical PROGRESS.md.
- Reproduction: code inspected on current main; a truncated response without a token triggers `break` and returns a partial list; a repeated token is passed indefinitely to `list_objects_v2`; duplicate object keys are counted separately.
- Acceptance: valid two-page listing returns both keys; absent/blank/non-string next tokens raise; repeated token raises by second page; duplicate keys raise rather than inflate cleanup counts.
- Failure and authority: propagate ValueError to the existing cleanup caller; no best-effort success or delete occurs from a partially fetched listing. Do not log keys or provider credentials. No database/Temporal schema or provider contract changes.
- Verification: `uv run --extra coworker pytest tests/test_coworker_retention.py -q`, mandatory full repo `test-and-build`, `coworker`, `ci-merge-gate`; independent code review. Test fixtures use a synthetic client, not AWS.
- External prerequisites: live S3 listing and recovery observation on matching non-production rollout, operator-side mutation and retention audit, reviewer security signoff.
- Out of scope: S3 operational proof, API/worker failover, credentials, account erasure activation, full CW-02 matrix, production rollout.

## Evidence level

| Gate | Status | Evidence |
| --- | --- | --- |
| Implemented | Code committed on review branch | Review SHA/PR in GitHub |
| Repository verified | Pending exact-head CI | Required job set |
| Staging verified | Unverified | No live S3 observation |
| Production qualified | No | Independent review and release gates missing |
| Activated | No | No activation authority or changes |

# CW-02 S3 inventory owner-scope and page completion validation

- Objective: prevent retention orphan cleanup from trusting a malformed S3 inventory response that broadens a caller's owner/prefix scope or silently treats an ambiguous page as complete.
- Base main: `b91d7952da640cc59c9c826ca0c0a18f9f23599b` (merged #477); preserve its valid pagination, duplicate-key, malformed-timestamp and missing-token checks.
- Work branch: `codex/cw02-s3-inventory-prefix-truncation-20261019`.
- Existing interfaces: `S3ObjectStore.inventory(prefix)`, `RetentionRepository.orphan_candidates/cleanup_orphans`; no contract/schema changes.
- Reproduction: code currently trusts returned keys without comparing to `Prefix` and treats absent, `0` or `"false"` IsTruncated as a final page. These are unsafe for an inventory used to authorize deletion.
- Acceptance: missing/non-boolean page-completion flag raises rather than declaring success; foreign-prefix object on initial or subsequent page raises before any inventory result is yielded or orphan deletion proceeds; valid two-page fixture remains unchanged.
- Required tests: `uv run --extra coworker pytest tests/test_coworker_retention.py -q`, plus exact-head mandatory `test-and-build`, `coworker`, `ci-merge-gate`, human independent review.
- Safety: exception propagates before `cleanup_orphans` deletes; never expand authorized prefix, hide malformed provider data, log object keys or call a live provider. No approval/transaction/credentials changes.
- External proof: protected staging real S3 inventory, orphan reconciliation, owner isolation and storage interruption/recovery still require operated evidence. No deployment or activation.

## Completion levels

| Level | State |
| --- | --- |
| Implemented | Committed to review branch; PR pending review |
| Repository verified | Pending exact-head full CI |
| Staging verified | Not proven |
| Production qualified | No |
| Activated | No |

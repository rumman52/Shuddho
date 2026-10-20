# V-01: revalidate PR state after review retrieval

- Objective: prevent the CI review gate from accepting stale PR metadata when a push, closure, merge, or draft conversion occurs while review pages are fetched.
- Dependency: merged #518 provides the current-head review gate. V-01 governance #484 remains unresolved.
- Base branch/SHA: main `3eba42fb767ca29e24eca4ead22273eae09dd535`.
- Work branch/PR: `fix/v01-review-fetch-revalidation-20261020`; [#519](https://github.com/rumman52/Shuddho/pull/519).
- Reuse: `validate_live_review`, `require_current_head_review`, and the existing read-only `_get_json` boundary.
- Files: `scripts/independent_review_gate.py`, `tests/test_independent_review_gate.py`, this contract and `PROGRESS.md`.
- Interface/schema compatibility: no signature, database, workflow or permission changes.
- Acceptance: unchanged open/non-draft current head with valid independent approval succeeds after reading all pages and refetching PR metadata. Changed head, draft, closed, merged, self-review, malformed/missing final metadata or failed final read must raise `ReviewGateError`.
- Test-first commit: `36ea88e83dcf5a6a01c3b720cc77b28152aa0e3f`; [CI #39471147429](https://github.com/rumman52/Shuddho/actions/runs/39471147429). Observed RED in test-and-build job 118795217428: **9 failed, 1,219 passed, 71 skipped**, all nine failures in the added live review regressions. Three additional initial-invalid/final-valid cases were committed before implementation at `6b2e7cf19c7053fb23ae38e07e071c9751008d7b` after independent agent review identified that coverage gap.
- Tests: existing `test-and-build` executes `uv run pytest -q`, JS tests and workspace builds. Existing mandatory coworker job covers integration, PostgreSQL, Temporal/process recovery and browser boundaries.
- Boundaries: no credentials, authority, external sends, capabilities, release flags, deployment or repository settings are changed. Existing review rules and bounded pagination stay in force.
- Timeout/revocation: final read uses the existing 20-second request timeout; API failure denies approval. A changed PR at final validation denies approval.
- Default-off/rollback: no product capability is enabled. Source rollback removes the additional snapshot check and leaves native GitHub protection separately necessary.
- External prerequisites: effective non-bypassable required checks and independent human review under #484; live staging prerequisites under #291.
- Out of scope: atomic merge authorization, review-history snapshot isolation, collaborator permission revalidation, trusted base-workflow enforcement and production qualification.

## Completion evidence

Implementation, exact-head code CI and independent agent review are recorded in the final PR description. Human approval and the merge gate remain separate. This check establishes metadata validity only at the final GitHub read: a subsequent push or review dismissal still requires native GitHub protection and event-driven re-evaluation. It is defense in depth, not an atomic transaction with a merge.

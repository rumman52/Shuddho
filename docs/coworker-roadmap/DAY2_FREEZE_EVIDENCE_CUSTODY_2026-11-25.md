# Day 2 — release-freeze evidence custody (2026-11-25)

- **Objective:** freeze the exact validated operator JSON bytes; reject duplicate fields, non-finite numbers, symlinks and oversized evidence. Publish prepared and final receipts privately without replacing an existing evidence file.
- **Dependency and base:** Day 2 #728; main `67d187f972c8069e4369ebc9fdb28dae55c40e3f`. Native governance and live staging approval are separate gates.
- **Work branch:** `fix/day2-freeze-evidence-snapshot-20261125`; source/test implementation head `3e752f5faee2a09563a8ff89d47d648162bd4962`.
- **Reuse:** `scripts/staging_release_evidence.py` bounded no-follow reader and atomic private JSON writer. No new store, migration, authorization mechanism, or runtime flag.
- **Files:** `scripts/staging_release_freeze.py`, `tests/test_staging_release_freeze.py`, this contract, progress ledger.
- **Compatibility:** CLI inputs/outputs and evidence schema unchanged; local input file bound is 1 MiB. Operators must use a new output pathname for each attempt, in a protected operator directory. Never overwrite an old receipt to rerun a drill. Symlinks and ambiguous JSON are intentionally rejected.
- **Reproduction:** original load_json function copied into a local isolated Python harness accepted six synthetic malformed/symlink cases (6 failing assertions). The original write_text pattern created mode 0644 rather than 0600 (1 failing assertion). No full repository checkout was available in that harness.
- **Execution:** test-only commits 9778f828fe905d1cfda5b1230ed139cb0067a9b3 and 7af94f9c6bc0e0ace14a262c1696c75b6ed50b75; minimal source fixes 09267add6739f8bc7d909af1a6154554b5bd2158 and 3e752f5faee2a09563a8ff89d47d648162bd4962.
- **Acceptance:** strict file parser rejects nested duplicate keys and non-finite values; path replacement after validation cannot change either recorded digest; valid receipts remain compatible; private publication is 0600 and refuses overwrite. Existing runtime manifest, provider, cohort and source revision checks remain.
- **Verification plan:** run `uv run --extra coworker python -m pytest tests/test_staging_release_freeze.py -q`, then required exact-head `test-and-build`, `coworker`, `ci-merge-gate`; inspect independent review. The local excerpt-level harness passed seven cases after repair, not a full test-suite or final-head result.
- **Boundaries:** no credential access, live calls, paid resources, deployment, migration or production activation. Protect operator evidence files outside the repository. Independent review and native enforcement remain required.
- **Residual risk:** this slice does not authenticate the operator's underlying decisions, harden runtime HTTP JSON parsing, or establish live release identity. The operator directory must itself be trusted.

| Level | Status |
| --- | --- |
| Implemented | IMPLEMENTED_UNVERIFIED — source commits above |
| Repository-verified | Pending exact-head required CI and independent review |
| Staging-verified | BLOCKED_EXTERNAL — approved live evidence required |
| Production-qualified | No |
| Activated | No |

Next action: review the draft diff and exact-head CI, then separately qualify staging under the existing Day 2 contract.

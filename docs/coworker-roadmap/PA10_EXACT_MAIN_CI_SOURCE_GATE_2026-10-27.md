# PA-10 source precondition for staging worker provisioning — 27 October 2026

## Problem and scope
The repository has repeatedly merged commits with a failed `ci-merge-gate` and without submitted independent review while `main` is reported unprotected. Running the existing manually dispatched PA-10 worker provisioning workflow from such a merged commit would otherwise not require successful source qualification. This change adds **defense in depth**, not native GitHub merge protection or live staging evidence.

## Implementation
- `scripts/pa10_source_gate.py` restricts reads to `rumman52/Shuddho`, checks the exact 40-character dispatched source SHA, and reuses the existing read-only `scripts.main_protection_audit.inspect_repository` native governance predicate.
- The same source must be the current protected `main` head. The latest workflow run for the exact SHA must be a completed successful **push** of `.github/workflows/ci.yml`. Its job list must be complete and contain exactly one successful `test-and-build`, `coworker`, `governance-audit`, and `ci-merge-gate`. Missing, skipped, duplicate, failed, truncated, wrong-SHA, wrong-event, and pending evidence fail closed.
- `.github/workflows/provision-pa10-staging-worker.yml` requests only `actions: read` in addition to `contents: read` and runs the gate before checking Render credentials, resolving PostgreSQL, changing worker resources, reconciling secrets, or deploying.
- `tests/test_pa10_source_gate.py` uses mocked responses; it never invokes real GitHub, Render, Temporal, Supabase, or provider resources.

## Required operational prerequisites — NOT closed by this PR
1. A repository owner must apply and validate native, non-bypassable protection and independently reviewed current-head PR checks ([V-01 #484](https://github.com/rumman52/Shuddho/issues/484)). A candidate ruleset configuration is not a successful negative-control merge test.
2. Independent review and exact-head CI are required for **this** PR. Preserve draft status until those checks and the native governance controls have been verified.
3. A protected `pa10-staging` GitHub environment must be operator-verified. Staging credentials, Render service plan approval, database continuity before 31 October 2026, migration, persistent Temporal polling, private S3, managed auth/owner isolation, and source freeze remain separate ([PA-10 #291](https://github.com/rumman52/Shuddho/issues/291)).
4. No paid worker, credentials, secret values, service, migration, production flags, production deployment or activation are changed by this proposal.

## Verification boundary
Isolated local tests were executed against mocked API responses using a local import shim for the existing `main_protection_audit` module; that does **not** prove the real integration. Require repository CI, a real GitHub API permission/readback test after ruleset setup, and the existing environment approval plus controlled staging evidence. A successful source preflight is **not** production or staging qualification.

## Rollback
Revert this bounded guard only after security review. Never bypass a failed gate to provision the worker from an unreviewed or unqualified main revision.

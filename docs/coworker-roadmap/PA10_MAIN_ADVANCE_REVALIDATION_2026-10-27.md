# PA-10: Revalidate current main after staging approval — 27 October 2026

## Problem and invariants

The PA-10 workflows now qualify the exact current protected main commit in an unprivileged `source_gate` job **before** their secret-bearing environment jobs can start. However, `pa10-staging` approval may introduce a delay. During that delay, `main` can advance. Running the approved workflow's older `github.sha` against Render after approval can create stale worker configuration or deploy an unqualified revision.

The guard must fail closed if:
- the repository or SHA input is malformed;
- GitHub cannot return the current `main` branch;
- native branch protection is no longer enabled;
- `main` points at anything other than the dispatched `github.sha`.

No safety condition is satisfied by observing a successful Vercel deployment or a source-controlled flag.

## Implemented proposal

- New `scripts/pa10_main_head_guard.py` performs a read-only `GET /repos/rumman52/Shuddho/branches/main` using the existing non-redirecting GitHub API helper; it accepts only the known repository, an exact lowercase 40-byte hex SHA, `protected=true`, and the current branch head equal to that SHA.
- Both `pa10-staging-prerequisite-preflight.yml` and `provision-pa10-staging-worker.yml` run this guard **after** entering the environment and **before** any Render access. Checkout stops persisting GitHub credentials. The workflow's protected-environment job continues to depend on the original unprivileged source check, which is not moved or weakened.
- The worker provisioning workflow additionally revalidates immediately before `Create or repair shuddho-worker-staging` and immediately before `Deploy exact main revision and require migration success`. No additional GitHub API scopes are required in those jobs (`contents:read` suffices).
- `tests/test_pa10_main_head_guard.py` exercises fail-closed behavior with mocked HTTP and negative cases; `tests/test_pa10_secret_boundary.py` checks the relative placement and count of revalidation steps.

These checks are observational and not atomic with a branch push. They cannot prevent an attacker permitted to edit unprotected `main` from changing source-controlled guards, and they cannot stop credentials from being injected into an already-authorized environment job. They reduce stale-provider operations, but do **not** replace administrator-enforced V-01 merge protection, native staging environment reviewers, freeze controls, or same-release post-deployment evidence.

## Qualification and owner actions

Full application and coworker tests, independently submitted code review and protected branch merge enforcement are mandatory on the final PR head. Do not merge the proposal until policy #484 is satisfied. Run no credential-bearing workflow while the current `main` branch reports `protected=false` and `governance-audit` fails. The source admission job is intentionally expected to fail today.

Staging database continuity remains urgent: prior Render evidence lists free `shuddho-staging-db` expiry on **2026-10-31**. The owner must decide retention, upgrade, or re-provisioning with verified data migration before expiration; no paid plan may be activated without approval. Do not claim PA-10 ready without worker, Temporal, storage, auth isolation, tenancy, compensation, recovery and release freeze evidence.

**Status:** Proposed code defense only. No Render database, Temporal, S3, Supabase, PostHog, Vercel or production resources modified by this work.

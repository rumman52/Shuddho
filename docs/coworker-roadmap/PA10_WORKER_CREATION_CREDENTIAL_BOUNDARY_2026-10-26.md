# PA-10 worker creation credential boundary — 26 October 2026

## Objective and dependency evidence
- Prevent a newly created persistent Render staging worker from receiving database credentials, Supabase S3 access keys, or Temporal API keys **before** its source, type, workspace, branch, region, plan, commands and disabled auto-deployment settings have been independently read back and checked.
- Baseline: `main` `5f6365fe9290383b184a1b464bb9c360a1fa7669`. PR #575 merged the metadata-readback gate, but `render services create --env-var` still submitted four credential-bearing variables before that gate.
- Work branch: `fix/pa10-create-without-credentials-20261026`. Depends on PR #575; PR #576 is separate and covers graceful shutdown.

## Implementation and interfaces
- Only change `.github/workflows/provision-pa10-staging-worker.yml` and `tests/test_pa10_worker_provisioning.py`, plus the release handoff and this contract. No application schema changes or new privilege interfaces.
- During `render services create`, keep reviewed inert/default-off flags and non-secret config; **omit** `SHUDDHO_COWORKER_DATABASE_URL`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `SHUDDHO_TEMPORAL_API_KEY`. Do not inject the database URL into the create step's environment.
- The existing `Verify reconciled staging worker configuration` step continues to gate the `Reconcile reviewed worker environment` step. The latter performs service-specific Render `PUT /v1/services/{serviceId}/env-vars/{envVarKey}` operations and then explicitly deploys the reviewed exact `main` revision.
- Preserve `pa10-staging` protected-environment scoping, manual `PROVISION` confirmation, task queue, feature flag defaults, database preflight and current worker API identity checks.

## Acceptance tests and initial regression
- Introduced regression in `tests/test_pa10_worker_provisioning.py` **before** the source edit; the former command included the forbidden variables and would fail this check.
- Fake Render executable records full `services create` argv in an isolated temporary test directory. The test rejects all four credential variables and test-only credential values, confirms two sensitive capabilities remain explicitly OFF, and verifies credential reconciliation is ordered after metadata readback.
- Existing tests for valid creation/repair, ambiguity, wrong identity, bad deployments, preflight, and error summaries remain required.
- Required final-head checks: `test-and-build`, `coworker`, `ci-merge-gate`, and independent human review; do not merge with failures.

## Threat model, residual limitations and rollback
- Credential deferral prevents intentional provisioning of a *new/unverified* service with those four secret values. It is **not** a guarantee about runner process environment, API provider availability, Render operator identity, or secrets already installed on an existing service.
- Render may start an initial build/deploy on service creation without the deferred credentials. That initial attempt must remain inert/fail-closed; the successful qualification path is the deliberate, exact-commit deployment **after** env reconciliation. Runtime behavior has **not** been observed in staging.
- No infrastructure has been provisioned by this code-only PR. Paid compute, secure environment reviewers/secrets, staging database expiry (31 October 2026), Temporal polling, private S3 round trip, source freeze and full PA-10 evidence still require operator action.
- Roll back by reverting this PR after human review; do **not** reintroduce credentials at create-time as an expedient workaround without a separate security review.
- Out of scope: PR #576's 120-second shutdown readback, GitHub V-01 ruleset administration, production API auto-deploy settings, provider contract/account provisioning, production activation.

## Completion evidence
| Level | State |
| --- | --- |
| Implemented | Changes proposed in review branch; verify exact commit/PR below |
| Repository-verified | Pending complete final-head GitHub Actions and independent human review |
| Staging-verified | **NOT VERIFIED**: no connected persistent worker exists |
| Production-qualified | **NO**: V-01 governance and provider/operational evidence missing |
| Activated | **NO**: no authorized capability/cohort activation |

- Test-first commit: `06ffe0e00b8f47934a04fecded573f7659e6b168`.
- Implementation commit: `c069f756937bb4adfefe21117ec1b9b89b31c12b`.
- Current main protection: `protected=false`, active rulesets listing `[]`, and PR #576 merge gate failed, so V-01 remains blocked.
- Next exact action: wait for complete exact-final-head CI, request an independent review, then have repo owner enforce native protections and Render operator configure approved staging resources. Do not merge or activate early.

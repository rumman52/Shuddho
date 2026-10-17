# CW-11 staging workflow fail-closed hardening

**Date:** 17 October 2026 (Asia/Dhaka)  
**Base:** `main` `e7a9f22834c8c84b5d4d2e81c33af7dc96d65f32`.  
**Branch:** `codex/cw11-staging-workflow-fail-closed-20261017`.

## Objective

Make the protected staging-evidence workflow fail visibly and before exposing staging secrets when explicit confirmation is missing or incorrect. Ensure live mixed-version worker checks run before any staging database migration.

## Reproduced workflow defects

1. The only evidence job used a job-level `if: inputs.confirm == 'CW11-STAGING'`. A wrong confirmation silently skipped the entire job instead of failing the workflow, potentially producing a green run with no evidence artifact.
2. Pending staging migrations ran before the workflow verified that the legacy Render worker had zero instances and that the candidate worker was running the exact qualification revision. That ordering could mutate staging schema while the old worker had not yet been proven stopped.

## Bounded implementation

- Add a separate confirmation job with no staging environment and no secrets. It exits nonzero unless the exact `CW11-STAGING` token is supplied.
- Scope Render, database and auth secrets to only the steps that need them; dependency installation and checkout receive no staging credentials.
- Make the evidence job depend on the confirmation job. A failed confirmation therefore fails the workflow and prevents the staging environment job from starting.
- Move the live Render service/instance/deployment check before pending database migrations.
- Add standard-library-only regression checks for the confirmation boundary and step ordering; these run in the lightweight test-and-build suite.
- Update the rollout runbook to reflect the fail-closed gate and migration ordering.

## Acceptance

- Incorrect confirmation produces a failed workflow, not a skipped-only green run.
- Staging secrets are only exposed to the evidence job after confirmation succeeds.
- The workflow verifies legacy service instance count is zero and candidate commit/instance evidence matches before applying migrations.
- The read-only collector still validates the selected publication, worker inventory, active claims and reviewed-task ledger.
- Exact-head `test-and-build`, mandatory zero-skip `coworker`, and `ci-merge-gate` pass.
- Protected staging evidence and independent operational review remain separate acceptance gates.

## Boundaries

This change does not dispatch the protected workflow, access staging secrets, deploy a worker, select a publication, migrate real staging data, activate CW-11, or claim production qualification. It hardens the workflow contract only.

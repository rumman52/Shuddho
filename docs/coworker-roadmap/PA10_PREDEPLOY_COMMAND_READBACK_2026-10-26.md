# PA-10 pre-deploy migration command readback — 26 October 2026

## Bounded task contract
- **Objective:** Refuse any PA-10 staging-worker credential reconciliation or explicit deploy unless Render's independently read-back **pre-deploy migration command** exactly matches the reviewed Blueprint and CLI creation/update settings.
- **Dependency and source truth:** baseline `main` `87d54dcbd1dcc899b247aef1908ff6cc85047847`, after PRs #575–#577. Render CLI NativeEnvironmentDetails serializes `preDeployCommand` under `serviceDetails.envSpecificDetails`; see Context7 reference `/render-oss/cli` and its generated `pkg/client/types_gen.go` type definition.
- **Risk/reproduction:** build/start command, owner, branch, auto-deploy, plan and shutdown setting were checked, but `preDeployCommand` was not. A service with a changed/missing migration command could be accepted and then receive sensitive worker credentials before `render deploys create`.
- **Files:** `.github/workflows/provision-pa10-staging-worker.yml`, `tests/test_pa10_worker_provisioning.py`, this contract and progress checkpoint. No schemas, service configs, secrets or feature flags are changed.
- **Reused interface:** existing `render services --output json` service inventory and pre-credential, pre-deploy jq predicate; retain existing S3, Temporal and PostgreSQL authority boundaries.
- **Contract:** require `.serviceDetails.envSpecificDetails.preDeployCommand == "uv run --extra coworker python -m services.coworker.migrate"` in the same fail-closed expression as source/region/commands. Missing/null and different values must fail.
- **Regression cases:** fake Render worker with reviewed migration command passes; changed migration module and missing field are rejected. Existing readback, staging prerequisites and unsafe-resource tests remain mandatory.
- **Source sequence:** test-first commit `70a551857d84237d70d7b47ab93ea75ebd108207`, implementation commit `860c6f5a368f0f293894dc3160e0da2d60238fd3`.
- **Verification:** run exact final-head test-and-build, coworker, merge gate; independent human review. Do not merge a draft or bypass release controls.
- **External requirements:** native branch protection (V-01 #484), fail-closed production promotion, secure staging environment and paid persistent Render worker with supported Temporal/PostgreSQL/private-S3 credentials (PA-10 #291), staging DB expiry **31 Oct 2026**, operated provider proofs and source freeze.
- **Rollback:** revert this isolated check only after security review; never weaken it to get an unknown migration command through staging.
- **Out of scope:** production activation or claiming real migration success. A live deployment result, not a static command check, is needed to confirm migrations ran correctly.

## Completion levels

| Level | Result |
| --- | --- |
| Implemented | Proposed on review branch (pending exact-head CI) |
| Repository-verified | Pending complete CI and human review |
| Staging-verified | No: no persistent staging worker observed |
| Production-qualified | No: V-01 and operational qualification missing |
| Activated | No: expanded capability flags remain OFF |

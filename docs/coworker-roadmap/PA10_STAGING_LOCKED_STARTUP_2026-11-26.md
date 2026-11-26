# PA-10 staging locked build and startup — 2026-11-26

- Base: `f7138e2025f6f5719aea4f4babfcc3549fae324b`; branch `fix/pa10-staging-locked-startup-20261126`.
- Root cause: both checked-in staging services used `pip install uv` without a version, and their startup/predeploy commands used `uv run` without `--no-sync`. Provisioning create/update/readback enforced the same mutable configuration.
- Fix: pin the existing CI-selected uv 0.7.22; retain frozen no-dev coworker sync during build; add `--no-sync` to both API startup invocations and the worker migration check/start invocation; reconcile the identical create/update/readback contract.
- No deployment changed. The exact commit deployment, reviewed worker plan, 120-second drain, protected credentials, migration checks, auto-deploy disabled and paid approval gates are unchanged.
- Files: infra/render.staging.yaml, .github/workflows/provision-pa10-staging-worker.yml, tests/test_pa10_worker_provisioning.py, this contract, PROGRESS.md.
- Acceptance: two regression test methods pin Blueprint commands, create/update and independent readback. Extend the existing fake Render shell test to reject the former unpinned build and syncing start/predeploy commands without weakening existing negative controls.
- Reproduction: isolated unittest of verbatim relevant command lines produced four failing assertions/subtests in two methods before and two passing methods after the replacement. Local uv is 0.10.0, not the pinned 0.7.22; the excerpt test is a config check, not the full mocked provisioning workflow or a live build.
- Test-first `6498b8907a057a758495d3c49129e4d6bff0da0d`; implementation `de118cae816cde17bd5b6630a67a5ec68bff5ca3`.
- Exact-head verification: `uv run --extra coworker python -m pytest tests/test_pa10_worker_provisioning.py tests/test_pa10_preflight_workflow.py tests/test_pa10_secret_boundary.py -q`; mandatory CI and independent review still required.
- This narrows dependency mutability; does not claim immutable Render base image or artifact provenance. Render workspace confirmation, billing, native governance and staging deployment proof remain external gates.
- Status: IMPLEMENTED_UNVERIFIED. No credentials, infrastructure, production flags or billing changes.

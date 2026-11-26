# D01.T02 / D02 staging source admission — full CI evidence binding

- Objective: require every mandatory main push CI job independently before staging source admission, with exact run and source identity. Canonical issues #727 and #728.
- Base: `43d99fd64467492a7da809cda0ae178191e53981`; branch `fix/day1-pa10-ci-evidence-binding-20261126`. PR #931 is a separate staging configuration patch; no overlapping production files.
- Reuse: `scripts/pa10_source_gate.py` and the existing CI workflow; do not change native required-check policy or replace the privileged governance audit.
- Root cause: the staging source gate checked four mandatory jobs and trusted aggregate success for frontend, browser, and PG18. It accepted inconsistent job lists, unbound job identities, duplicate run IDs, invalid run IDs, and some mismatched counts. Live GitHub jobs API readback confirmed job id, run_id and head_sha are present.
- Files: source gate, existing test module, this task contract, PROGRESS.md. No API/schema changes.
- Acceptance: require all seven main push jobs, one successful completed record per required name; reject malformed or repeated job/run identities, incorrect counts, wrong job run/SHA. Preserve skipped PR-only ancestry on push and existing separate privileged audit. Do not require identical run_attempt on every row: GitHub latest-job queries can retain successful jobs from an earlier attempt after a failed-job rerun.
- TDD: reconstructed full source and test files from main, matching Git blobs `0dfdb8222757def40168a6ba6baf8a628212c5c4` and `4dfb83a8f8fb389271c954672bb5bfbf898578d5`. Network-only dependency stubbed to reject unmocked IO; existing tests mock both network entry points. Baseline 9 passed + 14 subtests; RED 21 failed (20 new regression cases plus one existing subtest using full fixture), 10 passed + 13 subtests; GREEN 30 passed + 14 subtests; no skips. `python -m pytest -q` and `python -m py_compile scripts/pa10_source_gate.py tests/test_pa10_source_gate.py` executed in isolated reconstruction. Test commit `9c775ea5403a14b1b60ab09861edb9e41f72e728`; source commit `a3631afe261aaf169b65d1fa73e46b62a7ed4670`. Exact remote test blob `9fcc342687449a5f48c6b38ad42a9bca8a15d4b1`, source blob `a5ccae85d2aed42035fde69e231929848ca9ecd4` match tested local bytes.
- Security: no expanded permission, provider call, secrets, production deployment, native ruleset write, paid provisioning, telemetry activation, or hosted admission. PR #931 and this PR require reconciliation of shared progress log before merge.
- Full checkout DNS unavailable. Mandatory exact-head CI and independent human approval remain required. Governance native ruleset 27324410 still requires zero approvals and no required status checks; source patch cannot repair external settings.

| Level | Status |
| --- | --- |
| Implemented | Focused RED/GREEN verified |
| Repository-verified | Pending exact-head CI and independent review |
| Staging-verified | BLOCKED_EXTERNAL |
| Production-qualified | No |
| Activated | No |

Next: inspect final-head CI, restore native ruleset and dedicated App identity, obtain independent review, reconcile concurrent documentation edits, merge through protected rules only. Day 1 and Day 2 gates remain NO-GO.

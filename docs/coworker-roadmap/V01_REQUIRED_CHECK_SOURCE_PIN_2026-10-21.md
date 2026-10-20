# V-01 task contract — trusted required-check producer

Date: 21 October 2026 (Asia/Dhaka).

- **Objective:** Eliminate a false configuration-candidate from the read-only
  native GitHub protection diagnostic when required CI context names are present
  but their origin is unpinned or wrong.
- **Prior evidence:** Merged PR #525 produced failed exact-head CI
  https://github.com/rumman52/Shuddho/actions/runs/39493914888
  (`test-and-build` success, `coworker` success, `ci-merge-gate` failure)
  and was merged without verified native protection. Issue #484 remains open.
- **Base SHA:** `0c4b8a7d049aad4ff4657a5f101af55d05c792b5`.
- **Branch:** `audit/v01-ci-check-source-pinning-20261021`.
- **Reuse:** `assess_native_policy`, `_missing_status_checks`,
  `tests/test_v01_native_protection_audit.py`. Do not add a second ledger
  or mutate branch settings.
- **Scope:** `scripts/v01_native_protection_audit.py`,
  `tests/test_v01_native_protection_audit.py`, and V-01 documentation.
- **Interface/compatibility:** Existing JSON input/output and exit-code shape
  retained. Conservative policy classification may change from
  `configuration_candidate` to `blocked` on contexts lacking source
  metadata. Expect GitHub Actions App ID `15368`.
- **Acceptance:** All three required job names must have
  `checks[].app_id=15368` (branch protection) or
  `required_status_checks[].integration_id=15368` (ruleset).
  Reject absent, null, -1, arbitrary, bool/string, or mixed duplicated app
  IDs. Continue to reject missing jobs, weak reviews/bypasses and no policy.
  Correctly pinned configured snapshots remain nonzero exit **3**
  and `enforcement_verified=false`.
- **Test-first:** New test cases committed before the implementation.
  Changed positive fixtures explicitly pin the producer; negative cases
  target legacy contexts, wrong/missing producers and duplicate mixed actors.
- **Expected failure:** `blocked` and exit 2 for insufficient policy
  evidence; no weakening of failed `ci-merge-gate` signals.
- **Validation:** `python -m pytest tests/test_v01_native_protection_audit.py -q`;
  `python -m py_compile scripts/v01_native_protection_audit.py`;
  exact-final-head `test-and-build`, `coworker`, `ci-merge-gate` in
  GitHub Actions. Do not claim local commands or CI green unless observed.
- **Security:** No secrets, owners, grants, approval, egress or provider
  mutations. Read-only policy diagnostics cannot enforce merges.
- **Cost/time/cancellation:** No new external calls or durable worker.
  Preexisting bounded read-only admin network calls unchanged.
- **Default-off/rollback:** No runtime feature toggle. Revert this
  validation-only patch if faulty; do not enable new capabilities.
- **External prerequisites:** Admin-configured effective main protection,
  independent human final-head approval and actor-scoped live negative
  controls; staging #291 separate.
- **Out of scope:** Updating native branch rules, merging, deployed
  workers, token provisioning, provider calls and production activation.

## Completion evidence

| Level | Status | Exact revision / evidence |
| --- | --- | --- |
| Implemented | Proposed on review branch | PR and final-head SHA must be verified |
| Repository-verified | Pending exact-head CI | Mandatory jobs and human review not claimed |
| Staging-verified | Not applicable to read-only diagnostic | Issue #291 separate |
| Production-qualified | No | V-01 #484 remains open |
| Activated | No | No production changes |

- **Residual risks:** GitHub settings may be unconfigured, inherited or
  admin-bypassed; the diagnostic checks supplied evidence, not effective
  enforcement. A checked-in CI script cannot block merges on an unprotected branch.
- **Next:** Obtain independent PR review, exact-head CI and admin run with
  real rule snapshots. Independently demonstrate blocked unreviewed/red/stale
  negative controls and a reviewed/green positive control.

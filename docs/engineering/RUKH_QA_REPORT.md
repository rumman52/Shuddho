# Rukh AI QA report — 4 November 2026

## Baseline main
GitHub Actions run [#41768410772](https://github.com/rumman52/Shuddho/actions/runs/41768410772):
- Frontend tests/builds: success.
- test-and-build: failed; 1,741 passed, 1 failed, 73 skipped, 6 warnings.
- Coworker: failed on the same 0.8333 quality gate.
- governance-audit: failed with “main branch protection is not confirmed.”

## Regression proof
PR #619 RED run [#41780272070](https://github.com/rumman52/Shuddho/actions/runs/41780272070):
- Existing curated quality fixture failed at 0.8333.
- New numeric structured-fact regression failed as expected.
- 1,741 tests passed before the two expected failures.

## Fixed-head verification
PR #619 exact-head run [#41780778140](https://github.com/rumman52/Shuddho/actions/runs/41780778140):
- Frontend tests/builds: success.
- test-and-build: success; 1,743 passed, 73 skipped, 6 warnings.
- Heavy Coworker job: in progress at the time this report was written.
- Governance audit: skipped for pull_request event.
- Final merge gate and independent review: pending.

A full green result is not claimed until the heavy Coworker job and required PR checks finish. Skips and warnings are reported, not suppressed.

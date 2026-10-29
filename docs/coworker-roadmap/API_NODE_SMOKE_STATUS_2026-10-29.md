# Node API smoke analysis status

- **Objective:** avoid reporting analysis as ready when health metadata only proves
  liveness. Match the existing Python operator probe's three-state result.
- **Base:** main `93ff94f0e60723652d2a1b523bf91198ebe3bd74`.
- **Branch:** `fix/api-node-smoke-analysis-status-20261029`.
- **Existing interface:** `scripts/test-production-api.mjs` JSON summary;
  `scripts/api_deployment_smoke.py` supplies the established classification contract.
- **Changes:** Node script, its subprocess/fetch-boundary tests and operator documentation.
  No API/schema/provider/deployment/capability changes.
- **Acceptance:** only `full_local` with no reasons is `ready`; a known partial profile
  or any valid degradation reason is `degraded`; absent, unknown or malformed profiles
  are `unverified`. Default invocation remains exactly two unauthenticated GETs, with
  redirects disabled and `release_qualified=false`. Existing analysis/provider opt-ins
  and diagnostic redaction remain intact.
- **Reproduction:** original 14 tests passed; 12 added cases produced 10 failures and
  16 passes before implementation. Final probe suite: 26 passed, zero skips.
- **Verification:** full `npm test` passed, including 131 editor tests and Bangla NLP /
  shared-package suites; `node --check` and `git diff --check` passed. Local Node 24.22.1;
  required GitHub CI on its configured Node version remains a separate result.
- **Review:** a separate read-only agent found no scoped issues and independently
  verified 32 profile/reason combinations with two mocked GETs each. Not human approval.
- **Live evidence:** the pinned read-only production probe failed to reach `/health`
  from this environment. This is a network limitation, not proof the service is down.
- **Levels:** implemented and locally verified; final-head CI pending publication;
  deployed readiness and overall release qualification incomplete; activation unauthorized.
- **External gates:** independent current-head human review, native governance #484,
  live readiness policy/evidence #583 and staging #291. No provider inference, secrets,
  paid resources, data mutation, merge or production change was performed.
- **Next:** inspect the final PR-head CI and obtain independent human review. Preserve
  the draft until release-governance prerequisites are met; never weaken the review gate.

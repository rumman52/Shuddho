# Node API smoke analysis status

- **Objective:** avoid reporting analysis as ready when health metadata only proves liveness. Match the existing Python operator probe's three-state result.
- **Original implementation base:** main `93ff94f0e60723652d2a1b523bf91198ebe3bd74`.
- **Current integration base:** main `b5cf162452a06fbb203c52eb73ceb04fec2a0dd5`.
- **Original implementation commit:** `4f725b5558769a2072782be4cb069e3a5c7b8394`.
- **Branch / PR:** `fix/api-node-smoke-analysis-status-20261029` / [draft PR #596](https://github.com/rumman52/Shuddho/pull/596).
- **Changes:** Node smoke classification, subprocess/fetch-boundary regression tests and operator documentation. No API, schema, provider, deployment or capability changes.
- **Acceptance:** only `full_local` with no degradation reasons is `ready`; a known partial profile or any valid degradation reason yields `degraded`; absent, unknown or malformed profiles yield `unverified`. Default invocation remains exactly two unauthenticated GETs, with redirects disabled and `release_qualified=false`. Existing analysis/provider opt-ins and diagnostic redaction remain intact.
- **Original reproduction:** the original 14 tests passed; 12 added cases produced 10 failures and 16 passes before implementation. The original final probe suite reported 26 passed, zero skips; full `npm test`, `node --check` and `git diff --check` passed on the original branch.
- **Original exact-head CI:** [run #40861018712](https://github.com/rumman52/Shuddho/actions/runs/40861018712) passed `test-and-build` and `coworker`; the merge gate failed because independent review was not present and the PR was a draft.
- **Current exact-head CI:** pending on the refreshed branch; the original CI result is not substituted for a rerun against the current integration base.
- **Review:** a separate read-only review reported no scoped issues and independently checked 32 profile/reason combinations with two mocked GETs each. This is not human approval.
- **Live evidence:** current production deployment is live on main `b5cf162452a06fbb203c52eb73ceb04fec2a0dd5`, but startup logs report detector/corrector disabled and degraded local analysis. Production `healthCheckPath` is blank. Direct external `/health` and `/version` retrieval was unavailable; no live readiness is claimed.
- **Release gates:** independent current-head human review and native governance [#484](https://github.com/rumman52/Shuddho/issues/484); staging database/worker/Temporal/S3 [#291](https://github.com/rumman52/Shuddho/issues/291); production readiness [#583](https://github.com/rumman52/Shuddho/issues/583); telemetry/privacy [#584](https://github.com/rumman52/Shuddho/issues/584).
- **Safety:** no provider inference, secrets, paid resources, data mutation, merge or production change was performed.
- **Next:** inspect exact-head CI after the refresh and obtain independent human approval. Preserve draft status and do not merge until native governance is enforced.

# Read-only API Deployment Smoke Check

Use `scripts/api_deployment_smoke.py` to verify the **currently deployed** Shuddho API liveness response and exact source revision. It is an operator smoke probe, not a qualification or deployment step.

## Preconditions

- Obtain the exact 40-character Git commit from the **intended** Render deployment record. Do not substitute a PR-head SHA for a different merged commit.
- Decide whether the target is `staging` or `production`; the script pins those choices to the corresponding Shuddho `onrender.com` origins.
- Run it only in a network environment able to reach the specified public HTTPS endpoint. Do not use production credentials or account content.

## Commands

```bash
uv run python -m scripts.api_deployment_smoke --environment staging --expected-sha <full-40-character-staging-deployment-sha>
uv run python -m scripts.api_deployment_smoke --environment production --expected-sha <full-40-character-production-deployment-sha>
```

By default, the check accepts **liveness with degraded optional local analysis**, but records a non-sensitive analysis state. It reports `ready` only when `/health` supplies `analysis_profile=full_local` and no degradation reasons; known partial profiles or reported degradation yield `degraded`, while a missing/unrecognized profile yields `unverified`. No profile is inferred from an empty degradation list. Only when a specifically approved release contract requires loaded local analysis, add `--require-analysis-ready` (this fails closed for both `degraded` and `unverified`):

```bash
uv run python -m scripts.api_deployment_smoke --environment staging --expected-sha <full-40-character-staging-deployment-sha> --require-analysis-ready
```

## Safety boundary

- **Read only:** performs exactly two unauthenticated `GET` requests: `/health` and `/version`. No uploads, POST, account access, LLM invocation, or mutations.
- **Pinned targets:** only `https://shuddho-api-staging.onrender.com` and `https://shuddho-api.onrender.com`; no arbitrary URL or hostname argument.
- **No cross-origin redirects:** HTTPS validation is retained, environment proxy settings are ignored, and redirects are not followed.
- **Fail closed:** any non-200 response, wrong JSON shape, invalid health response, unavailable/short commit, or wrong full commit causes a nonzero exit.
- **Minimal output:** reports only the requested environment, exact expected source revision, liveness result, and coarse analysis state; never prints response body, checkpoint paths, raw error details, tokens, or user data.

## What a pass means

`status=passed` confirms that the public service returned the expected **liveness** and **full revision** responses at that moment. The output always includes `release_qualified=false` and `scope=liveness_and_revision_only`. This check **does not** prove business functionality, model-backed analysis, authentication, storage, agent scheduling, owner isolation, performance, transaction safety, or production readiness.

To qualify a release, retain separately reviewed evidence of the protected source/CI/review gate, actual staging worker and storage, representative synthetic identities, realistic task outcomes, restore/recovery tests, quality/SLOs, and the explicit release decision. Do not merge a smoke-tool PR around the native GitHub V-01 branch-protection blocker.

## Tests

```bash
uv run pytest tests/test_api_deployment_smoke.py -q
```

The unit tests use `httpx.MockTransport` and make no live network calls. A deliberately disabled source-revision comparison is detected by the mismatch regression, confirming the test is capable of failing if this critical check is removed.

## Node API diagnostic — read-only by default

The legacy operator script `scripts/test-production-api.mjs` is **GET-only by default**.
Running it normally makes exactly two unauthenticated requests (`/health`, `/version`) to
the pinned production Shuddho host. The only alternative allowed host is the pinned
Shuddho staging host. It rejects redirect responses, invalid health/revision payloads,
unexpected hosts, HTTP failures and network errors. No response body is printed.

```bash
node scripts/test-production-api.mjs
SHUDDHO_PRODUCTION_API_URL=https://shuddho-api-staging.onrender.com node scripts/test-production-api.mjs
node scripts/test-production-api.mjs --inspect-components
```

The optional `--inspect-components` adds read-only GET requests to `/health/deep` and
`/api/llm/debug`. It does not run analysis.

**Synthetic analysis is a separate explicit operator decision.**
`--allow-synthetic-analysis` adds a synthetic Bengali analysis POST with
`includeLLM=false`. It is not part of ordinary smoke checks.

`--allow-provider-inference` is rejected unless **both**
`--allow-synthetic-analysis` and the operator-controlled environment setting
`SHUDDHO_PROVIDER_SMOKE_AUTHORIZED=YES` are present. This option can incur provider
costs and must only be run with the appropriate approval and privacy controls.
Do not enable either POST mode in routine CI, previews or routine liveness checks.
No real user content is required. All modes report `release_qualified=false`.

The Node probe checks that the returned Git commit is a full well-formed SHA but
does not compare it to an intended deployment revision. Use the pinned Python
exact-SHA tool documented above for source provenance.

```bash
node --test scripts/test-production-api.test.mjs
```

The test suite mocks every fetch and sends no network traffic.

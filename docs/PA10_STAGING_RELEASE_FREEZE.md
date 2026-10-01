# PA-10 controlled-staging release freeze

Controlled staging must start from one exact reviewed non-production release. Do not use `docs/cohort-rollout.template.json` for this step: that template is production-specific.

The dedicated contract is:

- `docs/pa10-staging-rollout.template.json` — narrow PA-10 staging capability/rollback declaration;
- `scripts/staging_release_freeze.py prepare` — freezes the exact intended source SHA, build/image reference, deployment reference, rollout hash, provider-policy hash and synthetic-account reference before deployment;
- `scripts/staging_release_freeze.py verify` — authenticates to the deployed staging API and proves `/api/v1/runtime-manifest` exactly matches the prepared candidate.

## Why two phases

A hand-written note saying “deploy main to staging” is not release identity. The prepare artifact is immutable input to deployment; verify proves the running API really exposes the exact SHA/environment/capabilities/providers/cohort expected by that prepared artifact.

The verifier rejects:

- production environments;
- non-HTTPS or credential-bearing API origins;
- a source revision different from the frozen candidate;
- capability drift;
- action-provider drift;
- cohort-control drift;
- a provider-policy plan for another release;
- missing PA-10 capabilities;
- unrelated high-authority capabilities such as browser automation, code execution, transaction adapters, social publishing or Agent action proposals.

## Prepare before deployment

Copy the PA-10 staging rollout template to a reviewed secure release location and replace every placeholder/reference. Use the reviewed provider-policy plan for the same `release_id`.

```bash
export SHUDDHO_STAGING_ALLOW_RELEASE_FREEZE=true
export SHUDDHO_STAGING_SYNTHETIC_ACCOUNT=true

uv run --extra coworker python scripts/staging_release_freeze.py prepare \
  --rollout /secure/release/pa10-staging-rollout.json \
  --provider-policy-plan /secure/release/provider-policy-plan.json \
  --expected-source-revision "<40-char candidate SHA>" \
  --build-reference "<immutable image/build reference>" \
  --deployment-reference "<approved staging change/deployment reference>" \
  --synthetic-account-reference "<approved synthetic account/cohort reference>" \
  --state /secure/release/pa10-staging-freeze-state.json
```

Do not put tokens, OAuth secrets, provider credentials or raw account identifiers in these references.

## Deploy exactly the prepared candidate

Deploy the exact source/build and exact reviewed staging configuration. The rollout template intentionally enables only the capabilities required for the full PA-10 controlled-staging program and keeps unrelated high-authority capabilities off.

For the same release identity, Google and Microsoft provider availability is required because the implemented PA-10 provider matrix includes both families. If provider credentials/admin setup are not available, record that as an external blocker rather than weakening the freeze contract.

## Verify the running staging release

Use one authorized synthetic staging identity:

```bash
export SHUDDHO_STAGING_API_BASE_URL="https://<staging-api-origin>"
export SHUDDHO_STAGING_TOKEN_A="<synthetic staging access token>"

uv run --extra coworker python scripts/staging_release_freeze.py verify \
  --state /secure/release/pa10-staging-freeze-state.json \
  --output /secure/release/pa10-staging-release-freeze.json
```

A successful artifact has `status="frozen"` and binds:

- release ID;
- exact source SHA;
- non-production environment;
- immutable build/image reference;
- deployment reference;
- reviewed rollout SHA-256;
- reviewed provider-policy SHA-256;
- exact runtime capability set;
- exact action-provider set;
- cohort controls;
- canonical runtime-manifest SHA-256;
- prepare and verify timestamps.

All subsequent PA-10 scenario evidence should reference the same release identity. A meaningful code/config/provider-policy change invalidates the freeze and requires a fresh prepare/deploy/verify cycle.

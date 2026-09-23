# Agent Action-Proposal Production Activation

This gate verifies that non-executable Agent action proposals are actually deployed in the reviewed controlled-cohort configuration.

A passed live `action_proposals` staging gate is necessary but not sufficient. Production activation must prove that the exact staging evidence and exact reviewed rollout manifest were used for the reviewed deployment, that the deployed backend is running the expected source revision and capability set, and that post-deploy cohort health is clean.

## Design principle

The verifier does not trust the operator shell as proof of production state.

Instead it combines five independent facts:

1. exact timestamped live action-proposal staging evidence;
2. exact reviewed controlled-cohort rollout manifest;
3. reviewed deployment record containing exact artifact hashes and source revision;
4. authenticated remote runtime manifest fetched from the deployed backend over HTTPS;
5. fresh post-deploy `CONTINUE_COHORT` health with zero breaches.

Only then does it emit:

```text
action_proposals_verified
```

## Runtime source revision

The Coworker backend reads its source revision in this order:

1. `SHUDDHO_SOURCE_REVISION`;
2. Render's `RENDER_GIT_COMMIT`;
3. `GITHUB_SHA`.

A configured revision must be a full lowercase 40-character Git commit SHA.

On Render, `RENDER_GIT_COMMIT` is provided at runtime by the platform, so no extra secret is required for the normal deployment path.

## Authenticated runtime manifest

The verifier calls:

```http
GET /api/v1/runtime-manifest
Authorization: Bearer <short-lived admitted verification token>
```

The endpoint is authenticated, controlled-cohort checked, read-only and `Cache-Control: no-store`.

It exposes only:

- schema version;
- deployed source revision;
- deployment environment;
- rollout capability booleans;
- enabled action-provider names;
- cohort enforcement boolean;
- configured cohort member count;
- cohort ceiling.

It does **not** expose account IDs, OAuth details, provider credentials, database URLs, model keys, storage credentials, prompts, proposal payloads or user content.

## Exact rollout equality

The verifier normalizes the reviewed rollout's optional action-selection/action-proposal capabilities to explicit booleans and then requires the deployed runtime capability map to match **exactly**.

This intentionally fails activation if any reviewed capability drifts, including unrelated capabilities such as:

- memory;
- research;
- handoffs;
- parallel execution;
- outcome replanning;
- Microsoft actions/provider set.

Action-proposal activation is not allowed to hide broader configuration drift.

## Required order

1. Run [Controlled Live Agent Action-Proposal Staging](CONTROLLED_STAGING_ACTION_PROPOSALS.md).
2. Retain the exact resulting evidence file.
3. Review the exact controlled-cohort rollout manifest with `action_proposals=true`.
4. Calculate SHA-256 for both files.
5. Prepare `docs/action-proposals-deployment.template.json`.
6. Set the exact source revision to deploy.
7. Deploy that reviewed revision/configuration.
8. Generate fresh post-deploy cohort operator status.
9. Use a short-lived admitted verification token.
10. Run the activation verifier.
11. Treat action proposals as activated only if the artifact status is exactly `action_proposals_verified`.

## Deployment record

The deployment record contains exactly:

- release ID;
- reviewed change reference;
- current stage;
- deployment timestamp;
- full source revision;
- SHA-256 of exact action-proposal staging evidence;
- SHA-256 of exact reviewed rollout manifest.

The release ID and change reference must match the rollout manifest.

Deployment must occur after the staging proof.

## Run

Keep the bearer token out of process arguments and shell history:

```bash
export SHUDDHO_PRODUCTION_VERIFICATION_TOKEN='<short-lived-token>'
```

Then run:

```bash
uv run --extra coworker python scripts/action_proposals_activation.py \
  --staging-evidence /secure/release/staging-evidence.action-proposals.json \
  --rollout /secure/release/cohort-rollout.json \
  --deployment-change /secure/release/action-proposals-deployment.json \
  --operator-status /secure/release/post-action-proposals-status.json \
  --api-base-url https://api.example.com \
  --max-cohort-users 25 \
  --max-staging-age-minutes 1440 \
  --freshness-minutes 30 \
  --output /secure/release/action-proposals-activation.json
```

The API origin must be clean HTTPS with no userinfo, query or fragment. Redirects are not followed.

## Remote checks

The verifier requires:

- runtime manifest schema version 1;
- exact deployed source revision equals the deployment record;
- deployed environment equals the reviewed rollout;
- deployed capability map exactly equals the reviewed rollout;
- deployed action-provider list exactly equals the reviewed rollout;
- controlled-cohort enforcement is on;
- deployed cohort ceiling equals the reviewed ceiling;
- configured cohort membership is between 1 and that ceiling;
- `action_proposals=true`.

## Health checks

The operator status must:

- use the same release ID;
- be generated after deployment;
- be within the configured freshness window;
- have `decision == CONTINUE_COHORT`;
- contain zero breaches.

## Activation artifact

The resulting artifact contains:

- `status: action_proposals_verified`;
- release ID and stage;
- verification/deployment timestamps;
- change reference;
- exact source revision;
- fresh operator-status timestamp;
- the sanitized remote runtime snapshot;
- canonical SHA-256 of that runtime snapshot;
- SHA-256 of exact staging evidence;
- SHA-256 of exact reviewed rollout;
- SHA-256 of exact deployment record;
- SHA-256 of exact operator status.

It contains no bearer token or private user data.

## Failure semantics

Any of the following fails closed and produces no passing artifact:

- stale/missing staging evidence;
- invalid reviewed rollout;
- `action_proposals=false`;
- wrong/missing rollback switch;
- artifact SHA mismatch;
- deployment older than staging evidence;
- invalid/mismatched source revision;
- unauthenticated runtime manifest;
- HTTP redirect/non-200 runtime response;
- runtime capability/provider drift;
- cohort enforcement off;
- cohort overflow;
- stale or breached post-deploy health.

## Rollback

If activation fails or post-deploy behavior is unexpected, disable:

```text
SHUDDHO_AGENT_ACTION_PROPOSALS_ENABLED=false
```

This disables new proposal generation/promotion without enabling provider mutations, deleting audit history or disabling the ordinary user-prepared action path.

If the broader Agent runtime must stop:

```text
SHUDDHO_AGENT_RUNTIME_ENABLED=false
```

If all consequential actions must stop:

```text
SHUDDHO_ACTIONS_ENABLED=false
```

## Next release-evidence step

After this activation verifier is green, the exact activation artifact should be chained into the existing tamper-evident controlled-cohort release ledger as a new evidence-only schema version.

Scale/recovery should consume that ledgered proof only after the ledger increment lands. Do not make standalone `action_proposals_verified` JSON sufficient for scale or recovery.

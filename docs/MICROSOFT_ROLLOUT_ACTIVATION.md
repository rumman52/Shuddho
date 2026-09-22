# Microsoft Rollout Activation Verification

This gate is the final control-plane step between **passed Microsoft live staging** and **actual Microsoft UI rollout**.

It exists because three different things can otherwise drift independently:

1. live Microsoft Graph staging evidence;
2. backend Microsoft connector flags;
3. the frontend build-time Microsoft provider flag.

A successful staging probe alone does not prove that the deployed frontend and backend match the approved rollout.

## Required order

1. Merge and deploy the Microsoft backend adapter.
2. Run the independent live `microsoft_actions` staging gate.
3. Merge/deploy the gated frontend provider selector.
4. Build the frontend with:
   - `VITE_COWORKER_ENABLED=true`
   - `VITE_MICROSOFT_ACTIONS_ENABLED=true`
5. Deploy the backend with:
   - `SHUDDHO_ACTIONS_ENABLED=true`
   - `SHUDDHO_MICROSOFT_ACTIONS_ENABLED=true`
6. Record the deployment in the rollout deployment JSON.
7. Generate a fresh clean post-deploy operator status.
8. Run this activation verifier.
9. Treat Microsoft user exposure as verified only if the output status is `microsoft_rollout_verified`.

## Frontend rollout manifest

Every web-editor production build now writes:

```text
/shuddho-rollout-manifest.json
```

Example:

```json
{
  "schema_version": 1,
  "app": "shuddho-web-editor",
  "source_revision": "<deployed git sha>",
  "coworker_enabled": true,
  "microsoft_actions_enabled": true
}
```

The verifier fetches this from the **deployed frontend over HTTPS**. It does not trust a human assertion that the Microsoft selector is enabled.

The manifest contains no secrets, tokens, user identifiers, connection identifiers, or provider account data.

## Deployment record

Create the deployment record from:

```text
docs/microsoft-rollout-deployment.template.json
```

It binds:

- release id;
- approved change reference;
- deployment time;
- deployed frontend base URL;
- exact frontend source revision;
- SHA-256 of the exact Microsoft live staging evidence.

The deployment must occur after the staging evidence was verified.

## Activation checks

The verifier requires all of the following:

- `microsoft_actions.status == passed`;
- staging evidence has a `verified_at` timestamp;
- staging evidence is fresh enough for the requested rollout window;
- deployment record binds the exact staging evidence SHA-256;
- deployment time is after the staging verification;
- backend global external actions are enabled;
- backend Microsoft actions are enabled;
- deployed frontend manifest exists at the expected HTTPS location;
- deployed frontend revision exactly matches the approved deployment record;
- deployed frontend Coworker UI is enabled;
- deployed frontend Microsoft provider selector is enabled;
- a fresh post-deploy operator status says `CONTINUE_COHORT`;
- operator status contains zero breaches.

## Run

```bash
uv run --extra coworker python scripts/microsoft_rollout_activation.py \
  --staging-evidence /secure/release/staging-evidence.microsoft-actions.json \
  --deployment-change /secure/release/microsoft-rollout-deployment.json \
  --operator-status /secure/release/post-microsoft-rollout-status.json \
  --max-staging-age-minutes 1440 \
  --freshness-minutes 30 \
  --output /secure/release/microsoft-rollout-activation.json
```

The output status must be:

```text
microsoft_rollout_verified
```

## Rollback

If the Microsoft rollout causes any significant action, OAuth, provider, audit, or user-experience issue:

Frontend:

```text
VITE_MICROSOFT_ACTIONS_ENABLED=false
```

Backend:

```text
SHUDDHO_MICROSOFT_ACTIONS_ENABLED=false
```

If all consequential actions must stop:

```text
SHUDDHO_ACTIONS_ENABLED=false
```

Rebuild/redeploy the frontend after changing its build-time flag.

Do not delete connection/action history or migration data as routine rollback.

## Architecture boundary

This gate verifies **deployment consistency**, not Microsoft tenant entitlement or provider correctness. Those are proven by the earlier controlled live Microsoft staging gate.

The two gates are intentionally separate:

```
live Microsoft provider proof
→ deployment
→ deployed frontend/backend proof
→ rollout activation verified
```

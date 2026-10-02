# Controlled Staging Authenticated API Exercise

This is the next staging phase after the live connectivity probes.

It promotes release evidence only after exercising the deployed Coworker API with two real, disposable staging accounts.

## Required staging inputs

Provide these only to the staging process environment:

```bash
SHUDDHO_STAGING_API_BASE_URL=https://staging-api.example.com
SHUDDHO_STAGING_TOKEN_A=<short-lived access token for staging account A>
SHUDDHO_STAGING_TOKEN_B=<short-lived access token for staging account B>
```

Use dedicated staging identities with no customer data. The script never writes tokens to the evidence file.

## Base owner-isolation exercise

```bash
uv run --extra coworker python scripts/staging_api_exercise.py \
  --base-evidence /secure/path/staging-evidence.json \
  --output /secure/path/staging-evidence.next.json
```

The script uses synthetic probe content only and verifies:

- the two access tokens resolve to distinct account IDs and distinct workspaces;
- account B cannot upload bytes into account A's reserved document;
- account B cannot enumerate or delete account A's document;
- account B cannot read, stream events for, or cancel account A's task;
- account A retains access and can clean up its own probe document/task.

Only after every check passes is the `identity` staging evidence promoted to `passed`.


## PA-10 personal-agent owner isolation

When the reviewed staging release intentionally enables personal goals, automations and memory, add `--personal-agent`:

```bash
uv run --extra coworker python scripts/staging_api_exercise.py \
  --base-evidence /secure/path/staging-evidence.next.json \
  --output /secure/path/staging-evidence.pa10-owner.json \
  --personal-agent
```

This creates only synthetic, owner-scoped Shuddho state for account A and verifies that account B cannot read, enumerate, edit, cancel or delete account A's goal, automation, automation history or memory. The exercise then cancels/deletes the synthetic state through account A.

This mode deliberately creates **no Agent run, model call, connector read, provider write or approval**. Those higher-authority surfaces remain separate qualification scenarios and are not inferred from this result.

The output records a separate `personal_agent_owner_isolation` evidence item. A failure is a staging stop condition; do not promote it by editing evidence manually.


## Remaining PA-10 owner surfaces

After real synthetic staging scenarios have already produced User A resources, create a **non-secret** JSON manifest containing only these UUIDs:

```json
{
  "agent_run_id": "<uuid>",
  "notification_id": "<uuid>",
  "action_id": "<uuid>",
  "artifact_id": "<uuid>",
  "connector_read_grant_id": "<uuid>",
  "connector_snapshot_id": "<uuid>"
}
```

Then run:

```bash
uv run --extra coworker python scripts/staging_api_exercise.py \
  --base-evidence /secure/path/staging-evidence.pa10-owner.json \
  --output /secure/path/staging-evidence.remaining-owner.json \
  --owned-resource-manifest /secure/path/pa10-owned-resources.json
```

The manifest is strict: extra fields are rejected so tokens, provider credentials, message bodies and other sensitive values cannot be smuggled into the evidence input.

This mode performs no provider action and creates no new Agent run. It verifies:

- account B cannot enumerate, read, stream events for, or cancel account A's Agent run;
- account B cannot enumerate or mark account A's notification read;
- account B cannot enumerate/read/approve/cancel account A's prepared action, and the denied attempts do not change its state or immutable preview hash;
- account B cannot enumerate/download/read account A's artifact;
- account B cannot enumerate account A's connector read grant or read its provider-derived snapshots/subscription.

The selected IDs must already exist for account A and remain valid long enough to run the exercise. Provider-event authenticity and provider-specific duplicate/revocation behavior remain separate live-provider scenarios.

## Full artifact authorization exercise

Add `--artifact` when a staging worker and live model are intentionally available:

```bash
uv run --extra coworker python scripts/staging_api_exercise.py \
  --base-evidence /secure/path/staging-evidence.next.json \
  --output /secure/path/staging-evidence.artifact.json \
  --artifact
```

This creates one synthetic Coworker task, waits for a terminal result, and verifies:

- account B receives 404 for account A's artifact;
- account A receives a private signed URL or authenticated content path;
- the private download returns non-empty bytes.

Only then is `storage` promoted to `passed`.

## Fail-closed behavior

The exercise aborts on any unexpected HTTP status, shared account/workspace identity, missing task/artifact identifier, timeout, empty download, or cross-account access.

The output contains only staging evidence text. It does not contain JWTs, database URLs, storage keys, provider bodies, model reasoning, or probe document contents.

## Still manual after this increment

The following gates remain separate and must not be inferred from this API exercise:

- production Temporal worker restart/replay;
- AgentWorkflow v2 no-duplicate restart and fan-in verification;
- database/object backup and restore;
- retention/account/task deletion and orphan cleanup;
- v2 to v1 rollback;
- live Tavily research validation;
- live Google approval/execution/receipt validation.

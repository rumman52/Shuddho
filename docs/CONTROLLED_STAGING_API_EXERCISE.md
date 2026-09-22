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

# Controlled Staging Live Probes

This phase turns the production release checklist into executable, non-destructive staging evidence.

## Command

Run from the deployed staging environment with backend-only credentials available to the process:

```bash
uv run --extra coworker python scripts/staging_live_probe.py \
  --output /secure/path/staging-live.json \
  --base-evidence /secure/path/staging-evidence.json \
  --live-model
```

The probe never enables a feature flag and does not use user content.

## What is verified automatically

- managed identity JWKS endpoint is reachable and exposes supported asymmetric signing keys;
- PostgreSQL is reachable, the active schema is `shuddho_coworker`, TLS is active, and the Alembic version table is present;
- private S3-compatible object storage can complete an isolated write/read/delete round trip;
- the configured Temporal namespace is reachable over TLS;
- when `--live-model` is supplied, the checked-in planner evaluation runs against live DeepSeek and must score 100%.

The output contains only statuses and concise evidence text. It must never include credentials, raw JWTs, database URLs, object keys, provider response bodies, model reasoning, or user data.

## Fail-closed composite gates

A connectivity probe is not enough to satisfy every production gate. The following results intentionally remain `partial` until a higher-level staging exercise is recorded:

- **identity**: JWKS connectivity does not prove owner isolation;
- **storage**: direct object storage round trip does not prove API authorization for owner-scoped signed downloads;
- **temporal**: namespace connectivity does not prove worker restart/replay or duplicate suppression.

The existing `scripts/staging_gate.py` accepts only `status: passed` with a non-empty evidence reference, so these partial checks cannot accidentally produce a production GO.

## Remaining controlled-staging exercises

After the live probe succeeds, complete and record:

1. two-account owner-isolation checks across workspace, source, task, artifact, memory and action boundaries;
2. API upload and owner-scoped signed-download verification;
3. worker replacement during an active legacy task and AgentWorkflow v2 parallel run;
4. backup and restore drill against isolated staging data;
5. retention/deletion exercise covering source cleanup, task/account erasure and orphan object cleanup;
6. v2 parallel fan-in/no-duplicate validation and flag rollback to v1;
7. live Tavily evidence checks if research will be enabled;
8. live Google approval/execution/receipt checks if actions will be enabled.

Only after those evidence records are updated to `passed` should `scripts/staging_gate.py` return `GO`.

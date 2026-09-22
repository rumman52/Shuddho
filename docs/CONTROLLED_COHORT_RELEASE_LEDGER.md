# Tamper-Evident Controlled Cohort Release Ledger

Canary progression answers whether Shuddho should HOLD, STOP, or become eligible for a reviewed expansion. Operations also need a durable record of **which exact evidence produced each decision**.

The release ledger is an operations-side JSONL file protected by:

- SHA-256 hashes of the exact rollout manifest, canary plan, progression decision, and operator status;
- a SHA-256 hash chain linking every entry to the previous entry;
- HMAC-SHA256 authentication using an operations-only secret;
- strict release-id, stage, and decision binding.

It contains references and hashes only. Do not put access tokens, prompts, files, email/calendar payloads, OAuth data, or raw user identifiers into actor/change references.

## Secret

Provide an operations-only secret with at least 32 UTF-8 bytes:

```bash
SHUDDHO_RELEASE_LEDGER_HMAC_KEY=<secret from the operations secret store>
```

Do not place this key in the repository, application environment, browser environment, database, or ledger file.

The normal Shuddho API/worker deployment does not need this secret.

## Append an event

Example HOLD record:

```bash
uv run python scripts/cohort_release_ledger.py append \
  --ledger /secure/release/coworker-cohort-001.jsonl \
  --release-id coworker-cohort-001 \
  --event-type hold \
  --actor-reference oncall-primary \
  --change-reference change-123 \
  --current-stage canary-5 \
  --next-stage canary-10 \
  --rollout /secure/release/cohort-rollout.json \
  --canary-plan /secure/release/cohort-canary-plan.json \
  --progression-decision /secure/release/cohort-progression.json \
  --operator-status /secure/release/shuddho-coworker-status.json
```

Supported schema-v1 event types:

- `hold` → progression decision must be `HOLD`;
- `eligible_for_expansion` → decision must be `ELIGIBLE_FOR_EXPANSION`;
- `stage_approved` → decision must be `ELIGIBLE_FOR_EXPANSION` and the target must be the immediately following canary stage;
- `stop_rollout` → decision must be `STOP_ROLLOUT`.

Schema v2 adds only `rollback_completed`. It must follow an existing STOP event for the same release/stage and bind the same rollout manifest, canary plan and STOP progression decision plus the exact rollback-completion evidence.

Schema v3 adds only `recovery_verified`. It must follow the recorded rollback completion and bind the same release/stage, original STOP artifacts, exact rollback-completion artifact, post-recovery operator status and recovery-verification evidence.

Existing schema-v1/v2 entries are not migrated or rewritten.

The command atomically rewrites the ledger only after verifying the full existing chain.

## Verify

```bash
uv run python scripts/cohort_release_ledger.py verify \
  --ledger /secure/release/coworker-cohort-001.jsonl
```

Verification fails if:

- an entry was edited;
- an entry was removed from the middle of the chain;
- entries were reordered;
- the HMAC key is wrong;
- the chain contains more than one release ID;
- the schema or artifact-hash set is unexpected.

## External anchor

A hash chain plus HMAC detects modification for anyone who does not possess the operations key. It does not by itself prevent a privileged operator with the key from rewriting the full ledger.

After each reviewed change, copy the returned `head_entry_hash` into an independent change-ticket, deployment record, or immutable object-retention system. That external anchor makes silent whole-ledger replacement detectable.

For the first cohort, treat the change-ticket anchor as mandatory for:

- `stage_approved`;
- `stop_rollout`;
- any later rollback-completion workflow added to this ledger.

## Storage and writer model

Use one ledger file per release ID and one designated writer/scheduler. The script uses atomic replacement so readers do not observe partial JSONL content.

Do not run multiple concurrent ledger writers against the same local file. If operations later need distributed concurrent writers, move this contract behind a transactional/conditional object or database writer rather than adding ad-hoc file locking.

Retain the ledger and independently anchored head hashes according to the approved release-evidence retention policy.

## What the ledger does not authorize

A valid ledger entry does not itself:

- add users to the cohort;
- enable a feature flag;
- execute a rollback;
- approve a Google action;
- replace the rollout manifest or canary progression gate.

It is evidence of an operations decision, not a deployment control plane.

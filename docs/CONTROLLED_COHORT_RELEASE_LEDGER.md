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


## Post-25 bounded expansion verification

Schema v4 adds one event type: `bounded_expansion_verified`.

It is appended only after the post-25 bounded scale review has passed and the reviewed deployment has been independently verified. The entry binds by SHA-256:

- the exact bounded scale decision;
- the exact deployment-change record;
- the post-deployment operator status;
- the bounded scale-activation verification artifact.

The ledger verifies older schema-v1, v2 and v3 entries unchanged.

Example:

```bash
uv run python scripts/cohort_release_ledger.py append-scale \
  --ledger /secure/release/coworker-cohort-001.jsonl \
  --release-id coworker-cohort-001 \
  --actor-reference oncall-primary \
  --change-reference change-42 \
  --current-stage cohort-25 \
  --next-stage cohort-40 \
  --scale-decision /secure/release/bounded-scale-decision.json \
  --deployment-change /secure/release/cohort-scale-deployment.json \
  --operator-status /secure/release/post-scale-operator-status.json \
  --scale-activation /secure/release/bounded-scale-activation.json
```

A schema-v4 entry is evidence that a reviewed bounded stage was deployed and verified. It does not authorize the next expansion.


## Provider policy verification

Schema v5 adds one event type: `provider_policy_verified`.

It binds by SHA-256:

- the exact `ELIGIBLE_FOR_POLICY_REVIEW` provider-policy proposal;
- the exact provider-policy deployment record;
- the fresh post-policy operator status;
- the provider-policy activation verification artifact.

The event must extend an existing chain that already reached the current cohort stage. A duplicate record for the same exact policy activation is rejected.

A later schema-v4 `bounded_expansion_verified` event is accepted only when its scale-activation evidence binds a provider-policy activation that already has exactly one matching schema-v5 ledger record for the same current → proposed stage.

This makes the order explicit: runtime policy is verified first, cohort membership expands second.


## Microsoft rollout activation evidence

Schema v6 adds one event type: `microsoft_rollout_verified`.

It is appended only after the independent Microsoft live-provider gate and the deployed frontend/backend activation verifier both pass. The event requires the same release ID as the existing controlled-cohort ledger and an existing chain that has already reached the supplied current stage.

It binds by SHA-256:

- the exact timestamped `microsoft_actions` live-staging evidence;
- the exact reviewed Microsoft rollout deployment record;
- the fresh post-deploy operator status;
- the exact `microsoft_rollout_verified` activation artifact.

The deployment record must itself bind the exact live-staging evidence. The activation artifact must prove that global actions, backend Microsoft actions, Coworker frontend exposure, and the Microsoft frontend selector are all enabled for the reviewed deployment revision. Duplicate recording of the same exact rollout activation is rejected.

Example:

```bash
uv run python scripts/cohort_release_ledger.py append-microsoft-rollout \
  --ledger /secure/release/coworker-cohort-001.jsonl \
  --release-id coworker-cohort-001 \
  --actor-reference oncall-primary \
  --change-reference change-microsoft-rollout-001 \
  --current-stage cohort-25 \
  --staging-evidence /secure/release/staging-evidence.microsoft-actions.json \
  --deployment-change /secure/release/microsoft-rollout-deployment.json \
  --operator-status /secure/release/post-microsoft-rollout-status.json \
  --rollout-activation /secure/release/microsoft-rollout-activation.json
```

A schema-v6 event is evidence that the reviewed Microsoft provider rollout was deployed and verified inside the existing release chain. It does not authorize cohort expansion or any consequential user action.


## Agent action-selection activation evidence

Schema v7 adds one event type: `action_selection_verified`.

It is appended only after the live action-selection staging gate and the deployed-runtime activation verifier both pass. The event requires the same release ID as the existing controlled-cohort ledger and a chain that has already reached the supplied current stage.

It binds by SHA-256:

- the exact timestamped `action_selection` live-staging evidence;
- the exact reviewed action-selection deployment record;
- the fresh post-deploy operator status;
- the exact `action_selection_verified` activation artifact.

The deployment record must bind the exact staging evidence and the same current stage/change reference. The activation artifact must bind the exact staging, deployment, and operator-status files and prove Coworker, Agent Runtime, Intelligent Planner, Actions, Action Selection, and cohort enforcement were enabled in the reviewed deployment.

Duplicate recording of the same exact activation is rejected.

Example:

```bash
uv run python scripts/cohort_release_ledger.py append-action-selection \
  --ledger /secure/release/coworker-cohort-001.jsonl \
  --release-id coworker-cohort-001 \
  --actor-reference oncall-primary \
  --change-reference change-action-selection-001 \
  --current-stage cohort-25 \
  --staging-evidence /secure/release/staging-evidence.action-selection.json \
  --deployment-change /secure/release/action-selection-deployment.json \
  --operator-status /secure/release/post-action-selection-status.json \
  --action-selection-activation /secure/release/action-selection-activation.json
```

After appending, verify the complete ledger and copy the new `head_entry_hash` to the independent release/change record.

A schema-v7 event records release evidence only. It does not enable action selection, approve or execute an external action, change cohort membership, or authorize expansion/recovery by itself.

## Agent action-proposal activation evidence

Schema v8 adds one event type: `action_proposals_verified`.

It is appended only after the controlled live action-proposal staging gate and the production activation verifier both pass. The event requires the same release ID as the existing controlled-cohort ledger and a chain that has already reached the supplied current stage.

It binds by SHA-256:

- the exact timestamped `action_proposals` live-staging evidence;
- the exact reviewed controlled-cohort rollout manifest;
- the exact reviewed action-proposal deployment record;
- the fresh post-deploy operator status;
- the exact `action_proposals_verified` activation artifact.

Before append, the ledger writer independently verifies:

- the rollout has `action_proposals=true` and the exact proposal kill switch;
- the deployment binds the exact staging proof and rollout manifest;
- the deployment source revision is a full lowercase Git SHA;
- the activation binds the same release, stage, change reference, deployment time, source revision and operator-status generation time;
- the activation runtime snapshot hash is internally consistent;
- the runtime source revision and environment match the reviewed deployment/rollout;
- the complete normalized capability map exactly matches the reviewed rollout;
- the normalized provider set exactly matches the reviewed rollout, including legacy Google-only manifests that omit `action_providers`;
- controlled-cohort enforcement and the reviewed cohort ceiling match;
- every activation artifact hash matches the exact supplied file.

Duplicate recording of the same exact activation is rejected.

Example:

```bash
uv run python scripts/cohort_release_ledger.py append-action-proposals \
  --ledger /secure/release/coworker-cohort-001.jsonl \
  --release-id coworker-cohort-001 \
  --actor-reference oncall-primary \
  --change-reference change-action-proposals-001 \
  --current-stage cohort-25 \
  --staging-evidence /secure/release/staging-evidence.action-proposals.json \
  --rollout /secure/release/cohort-rollout.json \
  --deployment-change /secure/release/action-proposals-deployment.json \
  --operator-status /secure/release/post-action-proposals-status.json \
  --action-proposals-activation /secure/release/action-proposals-activation.json
```

After appending, verify the complete ledger:

```bash
uv run python scripts/cohort_release_ledger.py verify \
  --ledger /secure/release/coworker-cohort-001.jsonl
```

Copy the new `head_entry_hash` to the independent release/change record.

A schema-v8 event records release evidence only. It does not enable action proposals, promote a proposal, approve or execute an external action, change cohort membership, authorize expansion/recovery, or create any provider mutation.



## Approved action-attachment activation evidence

Schema v9 adds one event type: `action_attachments_verified`.

It is appended only after the controlled live attachment staging gate and the production attachment activation verifier both pass. The event requires the same release ID as the existing controlled-cohort ledger and a chain that has already reached the supplied current stage.

It binds by SHA-256:

- the exact timestamped `action_attachments` live-staging evidence;
- the exact reviewed controlled-cohort rollout manifest;
- the exact reviewed attachment deployment record;
- the fresh post-deploy operator status;
- the exact `action_attachments_verified` activation artifact.

Before append, the ledger writer independently verifies the reviewed artifact/action prerequisites, exact attachment kill switch, deployment source revision, exact normalized runtime capability/provider snapshot, controlled-cohort enforcement and ceiling, runtime snapshot hash, and every bound artifact hash. Duplicate recording of the same exact activation is rejected.

Append:

```bash
uv run python scripts/cohort_release_ledger.py append-action-attachments \
  --ledger /secure/release/coworker-cohort-001.jsonl \
  --release-id coworker-cohort-001 \
  --actor-reference oncall-primary \
  --change-reference change-action-attachments-001 \
  --current-stage cohort-25 \
  --staging-evidence /secure/release/staging-evidence.action-attachments.json \
  --rollout /secure/release/cohort-rollout.json \
  --deployment-change /secure/release/action-attachments-deployment.json \
  --operator-status /secure/release/post-action-attachments-status.json \
  --action-attachments-activation /secure/release/action-attachments-activation.json
```

Then verify the complete chain and retain the new head hash independently.

Schema v9 is evidence only. It does not enable attachments or approve an action. When attachments are enabled, bounded scale/recovery consume the exact schema-v9 activation SHA plus its ledger sequence/hash; recovery requires the satisfying schema-v9 event to occur after the exact rollback-completion event.


## LinkedIn social-publishing activation evidence

Schema v14 adds one event type: `action_social_publishing_verified`.

It is appended only after the guarded LinkedIn live-staging gate and exact production runtime activation verifier pass. The event requires the same release ID as the existing controlled-cohort ledger and a chain that has already reached the supplied current stage.

It binds by SHA-256:

- the timestamped `action_social_publishing` staging evidence;
- the reviewed controlled-cohort rollout manifest;
- the reviewed social-publishing deployment record;
- the fresh post-deploy operator status;
- the exact `action_social_publishing_verified` activation artifact.

Before append, the ledger independently verifies the exact social-publishing kill switch, LinkedIn provider presence, deployed source revision, normalized runtime capability/provider snapshot, controlled-cohort enforcement and ceiling, runtime snapshot hash, and all bound artifact hashes. Duplicate recording of the same activation is rejected.

Append:

```bash
uv run --extra coworker python scripts/cohort_release_ledger.py append-action-social-publishing \
  --ledger /secure/release/coworker-cohort-001.jsonl \
  --release-id coworker-cohort-001 \
  --actor-reference oncall-primary \
  --change-reference change-social-publishing-001 \
  --current-stage cohort-25 \
  --staging-evidence /secure/release/staging-evidence.social-publishing.json \
  --rollout /secure/release/cohort-rollout.json \
  --deployment-change /secure/release/social-publishing-deployment.json \
  --operator-status /secure/release/post-social-publishing-status.json \
  --action-social-publishing-activation /secure/release/social-publishing-activation.json
```

Then verify the complete chain and externally anchor the returned head hash.

Schema v14 records release evidence only. It does not enable social publishing, approve a post, mutate LinkedIn, change cohort membership, or authorize expansion/recovery by itself. When social publishing is enabled, scale and recovery require the exact schema-v14 activation SHA; post-rollback recovery requires a fresh satisfying schema-v14 event after the recorded rollback completion.

## Release activation bundle handoff

Schema v16 adds one event type: `release_activation_bundle_verified`.

This event is the final operations handoff checkpoint after the reviewed rollout has passed the final controlled-cohort gate and every required optional capability activation has already been independently recorded in the ledger.

The bundle verifier derives the exact required activation set from the reviewed rollout and verifies each required schema-v6 through schema-v15 activation artifact against its exact ledger event. The schema-v16 append then binds by SHA-256:

- the exact reviewed rollout manifest;
- the exact staging evidence file used to re-run the final GO/NO-GO decision;
- the exact `release_activation_bundle_verified` artifact.

The bundle also records the ledger entry count and head hash it verified. Schema-v16 append fails if the ledger changed after bundle verification, preventing a proof verified against one chain head from being committed onto another.

Run:

```bash
uv run python -m scripts.release_activation_bundle \
  --rollout /secure/release/cohort-rollout.json \
  --staging-evidence /secure/release/staging-evidence.final.json \
  --release-ledger /secure/release/coworker-cohort-001.jsonl \
  --activations /secure/release/activation-manifest.json \
  --current-stage canary-5 \
  --output /secure/release/release-activation-bundle.json

uv run python scripts/cohort_release_ledger.py append-release-activation-bundle \
  --ledger /secure/release/coworker-cohort-001.jsonl \
  --release-id coworker-cohort-001 \
  --actor-reference oncall-primary \
  --change-reference change-123 \
  --current-stage canary-5 \
  --rollout /secure/release/cohort-rollout.json \
  --staging-evidence /secure/release/staging-evidence.final.json \
  --release-activation-bundle /secure/release/release-activation-bundle.json
```

A schema-v16 event is evidence that the combined activation handoff was complete at that exact ledger head. It does not enable flags, approve actions, expand the cohort, authorize recovery or replace any feature-specific activation attestation.


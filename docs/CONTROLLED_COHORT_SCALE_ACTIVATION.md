# Controlled Cohort Scale Activation Verification

The bounded scale-review gate authorizes only a reviewed **proposal**. It does not prove that the production deployment actually applied the reviewed cohort ceiling or that server-side admission still works afterward.

This increment closes that gap.

## What is verified

After a human-approved deployment change, the verifier requires:

- the exact scale-review artifact to say `ELIGIBLE_FOR_BOUNDED_EXPANSION`;
- the exact provider-policy activation for this current → proposed stage to already be recorded as schema-v5 `provider_policy_verified` in the release ledger;
- when deployed Microsoft actions are enabled, the exact `microsoft_rollout_verified` activation artifact to already be recorded as one matching schema-v6 event for the current stage;
- a deployment-change record for the same release, stage, reviewed max users, and change reference;
- the deployment timestamp to be after the scale-review decision;
- backend cohort enforcement to remain enabled;
- the deployed `SHUDDHO_COWORKER_COHORT_MAX_USERS` to equal the reviewed proposed maximum exactly;
- configured membership to be larger than the previous cohort but no larger than the reviewed maximum;
- one allowed verification identity to succeed through the deployed API;
- one fresh non-member identity to receive `403 cohort_not_enabled` before provisioning;
- a fresh `CONTINUE_COHORT` operator status with zero breaches generated after the deployment change.

No account identifiers are written to the evidence artifact.

## Run

Provide a short-lived allowed verification token and a fresh denied identity:

```bash
export SHUDDHO_SCALE_VERIFY_TOKEN_ALLOWED=...
export SHUDDHO_SCALE_VERIFY_TOKEN_DENIED=...

uv run --extra coworker python scripts/cohort_scale_activation.py \
  --scale-decision /secure/release/bounded-scale-decision.json \
  --rollout /secure/release/cohort-rollout.json \
  --deployment-change /secure/release/cohort-scale-deployment.json \
  --operator-status /secure/release/post-scale-operator-status.json \
  --provider-policy-activation /secure/release/provider-policy-activation.json \
  --release-activation-bundle /secure/release/release-activation-bundle.json \
  --microsoft-rollout-activation /secure/release/microsoft-rollout-activation.json \
  --action-selection-activation /secure/release/action-selection-activation.json \
  --action-proposals-activation /secure/release/action-proposals-activation.json \
  --action-attachments-activation /secure/release/action-attachments-activation.json \
  --release-ledger /secure/release/coworker-cohort-001.jsonl \
  --freshness-minutes 30 \
  --output /secure/release/bounded-scale-activation.json
```

The verifier reads the real deployed Coworker settings, verifies the tamper-evident release ledger, requires the exact schema-v16 release activation bundle for the current stage, and checks the deployed HTTPS API. New output is schema v12 and binds the exact rollout-manifest SHA-256 plus that bundle's exact ledger sequence/hash in addition to the existing per-capability proofs. It does not update the allowlist, provider policy, or any feature flag.

## Release ledger

After successful verification, append a schema-v4 `bounded_expansion_verified` event to the existing release ledger. The event binds the exact scale decision, deployment record, post-deploy operator status, and activation-verification artifact by SHA-256.

That event is evidence that the reviewed stage was actually activated and verified. It still does not authorize another expansion. The newly activated stage must accumulate fresh health and demand evidence before another scale review.


## Post-scale observation

After the schema-v4 activation event is committed, begin a fresh observation epoch using [post-scale cohort observation](POST_SCALE_COHORT_OBSERVATION.md).

Only health generated after the ledgered activation may count. The new stage must earn sustained healthy windows and real usage samples before it can re-enter capacity qualification for any later scale review.


## Microsoft-enabled expansion

Google-only releases remain backward-compatible: if `SHUDDHO_MICROSOFT_ACTIONS_ENABLED=false`, no Microsoft rollout artifact is required.

If the deployed backend has `SHUDDHO_MICROSOFT_ACTIONS_ENABLED=true`, bounded scale activation fails closed unless all of the following are true:

- `--microsoft-rollout-activation` is supplied;
- the artifact status is `microsoft_rollout_verified`;
- its release ID matches the scale decision;
- it proves backend global actions and backend Microsoft actions are enabled;
- it proves Coworker frontend and Microsoft provider UI are enabled;
- the tamper-evident ledger verifies successfully;
- exactly one schema-v6 `microsoft_rollout_verified` event for the current stage binds the exact activation artifact SHA-256.

The bounded scale activation evidence also records the Microsoft rollout activation SHA-256 when Microsoft is enabled. This makes later scale evidence cryptographically dependent on the exact rollout proof rather than only on the current runtime flag.


## Action-selection-aware expansion

If `SHUDDHO_AGENT_ACTION_SELECTION_ENABLED=false`, bounded scale activation remains backward-compatible and no action-selection artifact is required.

If it is enabled, scale activation fails closed unless:

- `--action-selection-activation` is supplied;
- its status is `action_selection_verified`;
- its release ID and current stage match the scale decision;
- it proves Coworker, Agent Runtime, Intelligent Planner, Actions, Action Selection and cohort enforcement are enabled;
- the complete release ledger verifies;
- exactly one schema-v7 `action_selection_verified` event for the current stage binds the exact activation SHA-256.

Historical action-selection-aware scale activation evidence uses schema v2. New verifier output uses schema v3, preserving the same action-selection fields while also carrying action-proposals requirements when applicable.

The later schema-v4 ledger append independently re-verifies the schema-v7 action-selection proof for both historical v2 and new v3 evidence. If a required hash/ledger reference is stripped or changed, the ledger writer rejects the expansion record.

## Action-proposals release attestation

When `SHUDDHO_AGENT_ACTION_PROPOSALS_ENABLED=true`, bounded expansion now requires the exact production activation artifact to already be recorded as schema-v8 `action_proposals_verified` in the verified release ledger for the current stage.

Run scale activation with:

```bash
--action-proposals-activation /secure/release/action-proposals-activation.json
```

The verifier requires:

- `status == action_proposals_verified`;
- matching release ID and current stage;
- runtime proof with Coworker, Agent Runtime, Intelligent Planner, Actions, and Action Proposals enabled;
- controlled-cohort enforcement enabled;
- the exact activation SHA-256 to match exactly one schema-v8 ledger event.

New scale activation evidence is schema v3. It records `action_proposals_enabled` in `runtime_requirements`, binds the activation SHA-256, and records the exact satisfying ledger sequence and entry hash.

The later `append-scale` operation independently re-verifies the same schema-v8 event, sequence, entry hash, current stage, and activation SHA-256. Removing or replacing the proposal attestation after activation verification therefore fails closed.

If `SHUDDHO_AGENT_ACTION_PROPOSALS_ENABLED=false`, no proposal activation artifact is required. Historical schema-v1 and schema-v2 scale activation evidence remains verifiable; this change does not rewrite older release evidence.


## Approved-attachment-aware expansion

When `SHUDDHO_ACTION_ATTACHMENTS_ENABLED=false`, existing schema-v3 scale evidence remains unchanged and no attachment activation artifact is required.

When approved email attachments are enabled, bounded expansion fails closed unless:

- `--action-attachments-activation` is supplied;
- the artifact status is `action_attachments_verified`;
- release ID and current stage match the scale decision;
- the runtime proof shows Coworker, artifact services, Actions, Action Attachments and controlled-cohort enforcement enabled;
- the exact activation SHA-256 is recorded in one schema-v9 `action_attachments_verified` event for the current stage.

Attachment-enabled scale evidence is schema v4. It adds `action_attachments_enabled=true`, the exact attachment activation SHA-256, and the satisfying schema-v9 ledger sequence/hash.

The later `append-scale` operation independently re-verifies the same schema-v9 event and the exact sequence/hash references. Stripping or replacing the attachment attestation after runtime verification is therefore rejected.

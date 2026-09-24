# Controlled Release Activation Bundle

The final controlled-cohort GO decision proves that the reviewed rollout has the required staging evidence and operational controls. Individual production activation verifiers then prove that each optional capability was actually deployed as reviewed and recorded in the tamper-evident release ledger.

This bundle closes the operator handoff gap between those two layers.

It does **not** enable a feature flag, add a user to a cohort, approve an action, call an external provider, or authorize scale/recovery by itself.

## What it proves

For one exact rollout manifest and one current cohort stage, the verifier:

1. re-runs the final controlled-cohort GO/NO-GO decision;
2. derives every required production activation from the canonical release contract;
3. requires the activation manifest to contain exactly that set;
4. verifies each activation status, release ID and stage;
5. for schema-v8 through schema-v15 activations, requires the activation to SHA-bind the exact reviewed rollout manifest;
6. for historical schema-v7 action-selection activation, requires the embedded runtime capability map to match the normalized reviewed rollout exactly;
7. requires Microsoft activation when Microsoft is in the reviewed action-provider set;
8. verifies the full HMAC release ledger;
9. requires exactly one matching ledger event for every required activation artifact SHA-256;
10. records the exact ledger head used by verification.

## Activation manifest

Create a small operations-side JSON object mapping required activation keys to their exact artifact files.

Example:

```json
{
  "action_proposals": "/secure/release/action-proposals-activation.json",
  "action_social_publishing": "/secure/release/action-social-publishing-activation.json",
  "agent_linkedin_proposals": "/secure/release/linkedin-agent-proposals-activation.json"
}
```

Do not include disabled capabilities. Do not include extra stale activation files. The manifest must exactly match the reviewed rollout.

Microsoft-enabled action releases additionally use:

```json
{
  "microsoft_actions": "/secure/release/microsoft-rollout-activation.json"
}
```

## Verify the bundle

Set the operations-only release-ledger HMAC key, then run:

```bash
export SHUDDHO_RELEASE_LEDGER_HMAC_KEY=...

uv run python -m scripts.release_activation_bundle \
  --rollout /secure/release/cohort-rollout.json \
  --staging-evidence /secure/release/staging-evidence.final.json \
  --release-ledger /secure/release/coworker-cohort-001.jsonl \
  --activations /secure/release/activation-manifest.json \
  --current-stage canary-5 \
  --output /secure/release/release-activation-bundle.json
```

Passing output has:

```text
status = release_activation_bundle_verified
```

and records the exact rollout/staging hashes, required activation keys, every activation artifact hash, satisfying ledger sequence/hash, and the ledger head that was verified.

## Record schema-v16 attestation

Immediately append the verified bundle to the same ledger:

```bash
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

Schema v16 refuses to append if the release ledger changed after bundle verification. This prevents recording a bundle that was verified against an earlier ledger head.

After append succeeds, copy the returned `head_entry_hash` into the independent change/deployment record.

## Release semantics

A schema-v16 `release_activation_bundle_verified` event means:

> Every optional production activation required by this exact reviewed rollout was independently verified and already recorded in the release ledger at this stage, and the combined handoff proof was committed without an intervening ledger change.

It does not mean:

- general availability;
- unrestricted Agent autonomy;
- a provider mutation is approved;
- a cohort may expand;
- recovery after rollback is authorized;
- an operator may bypass feature-specific activation runbooks.

Scale and recovery continue to enforce their existing feature-specific activation/ledger requirements independently.

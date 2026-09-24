# Release Activation Bundle Scale and Recovery Enforcement

This increment makes the schema-v16 `release_activation_bundle_verified` attestation a required control-plane input for all **new** bounded cohort scale and post-rollback recovery verification runs.

It is additive. The bundle does not replace any feature-specific production activation, ledger attestation, health gate, provider-policy proof, rollback proof, or live admission check.

## Why

PR #199 created a single machine-verifiable handoff proving that every production activation required by one reviewed rollout was present and ledger-attested at an exact ledger head.

Two enforcement gaps remained:

1. the schema-v16 ledger append trusted the bundle's activation summary instead of independently re-deriving and checking the canonical required activation set; and
2. bounded scale and recovery continued to consume only the individual activation attestations, so the combined release handoff was not part of those later authorization paths.

This increment closes both gaps.

## Invariants

### Schema-v16 append

Before writing `release_activation_bundle_verified`, the ledger writer now independently:

- derives required production activations from the canonical release contract and reviewed provider set;
- requires the bundle's ordered `required_activation_keys` to match exactly;
- rejects missing or extra activation references;
- checks each expected status and artifact SHA-256;
- re-verifies each referenced ledger event by schema, type, stage, artifact hash, sequence, and entry hash;
- still rejects any ledger-head change between bundle verification and append.

A hand-edited bundle cannot become trusted merely by preserving its top-level status and prior ledger-head fields.

### Bounded scale

The operational scale verifier now requires `--release-activation-bundle`.

New scale evidence uses schema v11 and records:

- the exact bundle SHA-256;
- the satisfying schema-v16 ledger sequence and entry hash;
- the complete current runtime-requirement boolean map.

The later `append-scale` path independently re-verifies that exact schema-v16 event. Existing per-capability schema-v6 through schema-v15 checks remain mandatory.

Historical scale evidence remains verifiable unchanged.

### Post-rollback recovery

The operational recovery verifier now requires both the release ledger and `--release-activation-bundle`.

New recovery evidence uses schema v11 and requires:

- the exact schema-v16 bundle event to occur after the exact schema-v2 `rollback_completed` event;
- every activation ledger sequence referenced inside the bundle to also occur after that rollback event;
- the exact bundle SHA-256, schema-v16 sequence, and entry hash to be recorded in recovery evidence.

The later `recovery_verified` ledger append independently re-verifies the same schema-v16 event after rollback. Existing fresh post-rollback capability checks remain mandatory.

This prevents a newly created bundle from laundering stale pre-rollback activation evidence.

## Compatibility

- Historical scale/recovery evidence schemas 1-10 remain accepted according to their original semantics.
- Ledger event schemas remain unchanged: bounded expansion is schema v4 and recovery is schema v3.
- Schema v11 refers to the **scale/recovery evidence document format**, not a new release-ledger event type.
- No feature flag is enabled by this increment.
- No cohort membership is changed.
- No provider mutation, approval, or external action is performed.

## Operator flow

For a new controlled release or a post-rollback recovery:

1. complete all required feature-specific production activations;
2. verify the exact activation bundle;
3. append schema-v16 `release_activation_bundle_verified`;
4. supply that exact bundle to scale or recovery verification;
5. append the existing bounded-scale or recovery ledger event only after the new evidence passes.

For recovery, steps 1-3 must be completed after the exact rollback-completion event.

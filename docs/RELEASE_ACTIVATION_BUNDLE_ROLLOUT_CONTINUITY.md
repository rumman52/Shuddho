# Release Activation Bundle Rollout Continuity

This increment closes a same-release, same-stage stale-evidence gap in the controlled release chain.

PR #200 required the schema-v16 `release_activation_bundle_verified` artifact for new bounded-scale and post-rollback recovery verification. That proved the bundle itself was ledger-attested, but the downstream verifiers did not yet prove that the bundle belonged to the **exact rollout manifest** currently being scaled or recovered.

A previously valid schema-v16 bundle from the same release and stage could therefore be presented after the reviewed rollout manifest changed.

## Invariant

Every new scale or recovery transition must carry one immutable rollout identity from the reviewed manifest through:

`rollout manifest -> activation bundle -> schema-v16 ledger event -> scale/recovery evidence -> final ledger consumer`

The rollout identity is the exact SHA-256 of the rollout manifest bytes.

## Bounded scale

The operational scale verifier now requires `--rollout`.

It:

- validates the rollout using the canonical final-release manifest rules;
- requires the rollout release ID to match the scale decision while preserving dynamic later cohort ceilings;
- requires the supplied schema-v16 bundle's `rollout_manifest_sha256` to equal the current rollout SHA-256;
- requires the matching schema-v16 ledger event to carry the same rollout SHA-256.

New scale evidence uses schema v12 and records the exact rollout SHA-256 in `artifact_sha256.rollout_manifest`.

The later `append-scale` command also requires `--rollout` and independently checks that:

- schema-v12 scale evidence binds that exact manifest;
- the referenced schema-v16 event binds that exact manifest;
- the existing bundle hash, sequence and entry-hash checks still pass.

Historical scale evidence schemas remain valid under their original semantics.

## Post-rollback recovery

Recovery already receives the reviewed rollout manifest. The recovery verifier now additionally requires the post-rollback schema-v16 bundle and matching ledger event to bind that exact manifest SHA-256.

New recovery evidence uses schema v12 and records the same rollout SHA-256.

The `recovery_verified` ledger writer independently rechecks:

- recovery evidence rollout SHA-256;
- schema-v16 ledger event rollout SHA-256;
- post-rollback ordering of the bundle;
- post-rollback ordering of every activation reference in the bundle.

Historical recovery evidence remains valid under its original schema.

## Safety

This is control-plane continuity only. It does not:

- enable a feature flag;
- change cohort membership;
- authorize expansion by itself;
- approve or execute an external action;
- relax provider, health, capacity or feature-specific release gates.

A rollout manifest change now requires a new matching activation bundle before scale or recovery may continue.

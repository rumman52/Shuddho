# Downstream Rollout Identity Continuity

This increment extends the rollout-manifest identity invariant introduced in PR #201 through the immediate consumers that can authorize later cohort movement.

PR #201 bound the exact rollout SHA-256 through release activation, schema-v16 bundle attestation, scale/recovery verification, and the corresponding signed ledger event. The next-stage consumers still accepted those artifacts without preserving that rollout identity into later requalification decisions.

## Invariant

For all new operational runs, the same rollout-manifest SHA-256 must remain continuous through:

`rollout -> activation bundle -> scale/recovery evidence -> signed ledger -> observation/progression -> capacity qualification -> scale review -> next scale activation`

A release ID or stage name alone is not sufficient identity.

## Post-scale observation

`cohort_post_scale_observation.py` now requires `--rollout`.

For schema-v12 scale activation evidence it requires:

- the current rollout release ID to match;
- `artifact_sha256.rollout_manifest` in the scale activation to match the exact current rollout file.

The observation result carries `rollout_manifest_sha256` forward into dynamic requalification evidence.

Historical scale activation evidence remains readable; it does not gain identity retroactively.

## Capacity qualification

All new CLI capacity qualification runs now require `--rollout`.

The tool:

- verifies the rollout release ID;
- checks any rollout identity already present in the progression artifact;
- records the exact rollout SHA-256 in the capacity result and artifact hashes.

This covers both the original final controlled-cohort qualification and later dynamic requalification without hard-coding a stage name.

## Bounded scale review

All new scale-review CLI runs now require `--rollout`.

The review requires the capacity qualification to bind that exact rollout SHA-256, records the same SHA-256 in the scale decision, and includes it in the decision artifact hashes.

The next scale activation rejects a scale decision whose rollout identity differs from the current rollout, even if the release ID and stages still match.

## Post-recovery canary progression

For schema-v12 recovery evidence, `cohort_canary_progression.py` requires the supplied rollout manifest to match both:

- the recovery verification artifact's rollout SHA-256; and
- the signed schema-v3 recovery ledger entry's rollout SHA-256.

This prevents post-recovery health from restarting expansion against a different same-release rollout.

## Compatibility

- Historical helper/test paths remain valid where rollout identity did not exist.
- New operational CLI paths fail closed and require the rollout manifest.
- Existing signed ledger event schema numbers remain unchanged.
- No feature flags, cohort membership, provider state, approvals, or external actions are changed.

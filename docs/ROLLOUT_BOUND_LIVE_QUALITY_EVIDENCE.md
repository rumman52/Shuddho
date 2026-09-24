# Rollout-Bound Live Quality Evidence

This increment closes a release-control gap in Shuddho's multilingual quality gate.

Before this change, live quality evidence recorded the release ID, fixture SHA-256 and configured provider model, but it did not bind the exact reviewed rollout manifest. The final controlled-cohort gate also trusted the staging evidence record as a pass/fail reference without parsing the quality artifact itself.

That allowed a valid quality PASS from one same-release rollout to be reused after the rollout manifest changed.

## Invariant

For every new operational live-quality run:

`quality evidence.rollout_manifest_sha256 == SHA256(reviewed rollout)`

That identity is checked at every authorization boundary that consumes quality evidence.

## Live quality producer

`coworker_quality_eval.py --live` now requires `--rollout`.

It verifies the rollout release ID matches `--release-id` and records the exact rollout SHA-256 in the emitted quality artifact.

Offline deterministic CI mode remains unchanged and does not require a rollout.

## Shared verifier

`scripts/coworker_quality_evidence.py` defines the common live-quality evidence contract.

It requires:

- live mode;
- matching release ID;
- exact rollout SHA-256;
- clean PASS with no case or gate failures;
- configured minimum pass rate and fact recall;
- valid fixture SHA-256;
- non-empty provider model;
- timezone-aware generation timestamp.

## Final controlled-cohort admission

New operational final-gate runs require `--quality-eval`.

The gate parses and validates that artifact directly. A `quality` staging record with a `passed` status and evidence string is no longer sufficient by itself for the CLI path.

The artifact must bind the exact rollout supplied to the final gate.

## Bounded scale review

Scale review uses the same shared verifier, with the scale-review plan's pass-rate/fact-recall thresholds plus its freshness window.

Capacity evidence and quality evidence must therefore bind the same rollout before a new bounded-scale decision can be emitted.

## Activation bundle and schema-v16 handoff

New activation-bundle runs require the same `--quality-eval` artifact.

The bundle records its exact SHA-256. When the bundle is appended as schema-v16, the ledger writer independently compares the supplied quality file against that bundle hash before signing the bundle event.

The schema-v16 event artifact-key shape is unchanged; it signs the complete release-activation-bundle artifact, which transitively binds the verified quality hash.

Historical schema-v16 bundles without `quality_evidence_sha256` remain verifiable under their original semantics.

## Safety and scope

This increment does not:

- enable a production feature;
- expand a cohort;
- change model configuration;
- claim universal language quality;
- approve or execute external actions;
- replace feature-specific staging or production activation gates.

It prevents quality evidence from silently crossing rollout-manifest boundaries.

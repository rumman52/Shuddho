# Live Model Identity Continuity

This increment closes the AI-runtime identity gap between Shuddho's live planner gate, multilingual quality gate, final controlled-cohort admission, and the signed activation handoff.

## Problem

A release could previously have:

- a valid live planner pass;
- a valid multilingual quality pass;
- the same release ID;
- the same rollout manifest;

while the two evaluations were produced by different DeepSeek models or different source revisions.

The staging evidence map also treated the `model` gate as a generic passed reference rather than machine-verifying the planner artifact.

## Invariant

For every new operational release:

`planner.rollout_manifest_sha256 == quality.rollout_manifest_sha256 == SHA256(reviewed rollout)`

and:

`planner.provider_model == quality.provider_model`

and:

`planner.source_revision == quality.source_revision`

## Live planner evidence

`agent_eval.py --live` now requires:

- `--release-id`;
- `--rollout`;
- a full lowercase source revision from `SHUDDHO_SOURCE_REVISION`, `RENDER_GIT_COMMIT`, or `GITHUB_SHA`.

The artifact records:

- release ID;
- rollout SHA-256;
- fixture SHA-256;
- configured DeepSeek model;
- exact source revision;
- timestamp;
- pass/fail decision and failures.

The actual live planner uses the same `DEEPSEEK_MODEL` value recorded in the artifact.

## Multilingual quality evidence

Live quality evidence now also records the exact source revision and fails before provider calls when no valid revision is available.

The final gate requires its provider model and source revision to match the verified planner artifact.

## Final controlled-cohort admission

New operational final-gate runs require both:

- `--model-eval`;
- `--quality-eval`.

The gate parses both artifacts directly. A generic staging evidence reference cannot substitute for either AI-runtime proof.

## Activation bundle and schema-v16

The release activation bundle records exact SHA-256 hashes for both live planner and live quality artifacts.

Schema-v16 append independently checks the supplied files against those bundle hashes before signing the bundle event. Historical bundles without these additive hashes retain their original verification semantics.

## Scope

This is evidence continuity only. It does not change the deployed model, source revision, feature flags, cohort membership, provider permissions, or action authority.

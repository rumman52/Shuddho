# CW-02/03/04 reviewer-attested release evidence gate

**A green test suite is not live staging qualification.** PR #373 added disposable PostgreSQL fault tests; that does not prove all sixteen real CW-02 failure injections or completed CW-03/04 staging.

This offline gate adds three explicit checks:

1. CW-02: All sixteen entries and their actual evidence file bytes must pass the existing scenario and SHA-256 checks, and the complete evidence-file tree digest is bound to the reviewer signature.
2. CW-03: Both API and worker must report the same full forty-character source revision and individual deployment IDs. PostgreSQL, Temporal, private storage, model and synthetic identity must have observed passing prerequisites with nonempty references.
3. CW-04: Seven independently reviewed staged workflow records (read, draft, goal, reminder, worker_restart, backup_restore and flag_rollback) must match the exact release, rollout and deployment IDs, and include unique run IDs and evidence hashes.

A separate release reviewer signs canonical compact sorted JSON containing the raw CW-02 manifest hash, CW-03/04 checkpoint hash and actual evidence tree hash. The verifier requires Ed25519 and the independently pinned SHA-256 of the public key's DER SubjectPublicKeyInfo. Do not accept a key or fingerprint obtained only from the evidence submitter.

### Operating procedure

First freeze a dedicated staging release and identify the exact deployed API/worker revisions. Run all failure injections with sandbox-only credentials after explicit operator authorization, including Temporal/process/network failures. Preserve logs and independent provider-side mutation observations, and rehearse rollback and restore. Have a separate authorized reviewer inspect these raw observations and sign the evidence bundle with an approved signing process.

The verifier is intentionally **read-only**. Example:

    uv run --extra coworker python -m scripts.cw0204_qualification_gate \
      --manifest /secure/cw02-manifest.json \
      --checkpoint /secure/cw0304-checkpoint.json \
      --evidence-dir /secure/cw02-evidence \
      --attestation /secure/reviewer-attestation.json \
      --trusted-public-key /secure/approved-reviewer-public.pem \
      --trusted-key-sha256 INDEPENDENTLY_PINNED_PUBLIC_KEY_FINGERPRINT \
      --source-revision FULL_FROZEN_40_CHARACTER_GIT_SHA \
      --rollout-id EXACT_STAGING_ROLLOUT

The attestation has: schema_version=1, role=independent_release_reviewer, reviewer_id, timezone-aware attested_at, source_revision, rollout_id, manifest_sha256, checkpoint_sha256, evidence_tree_sha256, and a base64 Ed25519 signature over all fields except signature_base64.

CI runs *synthetic* positive/negative tests using ephemeral reviewer keys, rejecting missing workflow data, modified evidence, mismatched deployments, duplicate JSON keys, altered signatures, and substituted reviewer keys. Synthetic tests cannot certify actual staging outcomes.

**Scope limitations:** The verifier authenticates a configured reviewer approval of a given byte-for-byte bundle. It does NOT prove a provider mutation count, the truth of the staging observations, the reviewer organization's key custody, clock accuracy, or real process recovery. Independently inspect those facts before operational release. Do not fabricate receipts, enable unqualified transactions or bypass the existing provider/action kill switches.

CW-01–08 remain not fully production-qualified pending operated CW-02–04 staging, and CW-08 end-to-end and revocation/reconnect testing.

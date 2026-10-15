# CW-10 — exact source and policy integrity at sandbox worker claim

**Date:** 15 October 2026. **Base:** `main` `e4381617fd51107b74b4aac25e76109caf1a0123` ([PR #412](https://github.com/rumman52/Shuddho/pull/412) merged, required final-head [CI #38725411478](https://github.com/rumman52/Shuddho/actions/runs/38725411478) passed all three jobs). **Branch:** `codex/cw10-sandbox-claim-source-integrity-20261015`. The latest matching main push [CI #38727695049](https://github.com/rumman52/Shuddho/actions/runs/38727695049) was still running `coworker` when inspected. This slice does not enable generated-code execution or alter rollout authority.

## Source-level defect and user-visible outcome

`SandboxRepository.prepare_execution` stores exact untrusted Python source and its UTF-8 byte count/SHA-256. `SandboxRepository.claim_executions` is the **actual worker authority boundary** but previously returned stored `request_spec.source` to an authenticated sandbox worker without comparing it to the immutable `SandboxExecution.source_sha256` or `source_bytes`. Modified persisted request_spec after creation could therefore issue different Python bytes under the previously recorded digest on first claim or lease recovery. The separately merged Agent ToolReceipt check does not protect a generic sandbox worker claim. **Outcome:** only source bytes with the originally stored exact digest/size and expected untrusted-policy metadata are ever given to a worker; mismatches fail closed before dispatch.

## Integrated patch

1. During the existing `claim_executions` database transaction, verify the request spec is an object, source is nonempty valid UTF-8, source size is within configured maximum and equals the prepared `source_bytes`, digest equals `source_sha256`, `source_trust` equals `untrusted`, and `policy_version` equals canonical `sandbox-control-v1`. Do not rely on later container-side worker source checks alone.
2. On any mismatch, return **no claim** and atomically mark the execution failed (`sandbox_source_integrity_failed`), scrub untrusted source bytes, release lease/claim, close the owning session, and record an audit event. If a previous worker held a now-expired lease, keep `cleanup_state=required` to avoid falsely asserting that its sandbox is already destroyed. A clean first-claim rejection sets `not_required`.
3. Preserve normal unmodified user-supplied Python, existing worker sandbox isolation, idempotent retry, max-attempt cap, owner scope, source hash and output receipt rules. Do not register a model-written code tool, alter the human approval requirements, add another event ledger, or widen sandbox permissions.

## Falsifiable tests

- `tests/test_sandbox_control_plane.py`: six tamper forms (same byte-length different program, removed source, byte count mismatch, substituted source trust, substituted policy version, invalid UTF-8) before first worker claim **and** on lease-recovery claim. All must yield zero returned worker source, a durable failed/scrubbed execution with no remaining lease, terminal session, and no future re-claim. A stale prior claimant cannot continue; cleanup remains required if it ever held the job.
- `tests/test_coworker_postgres.py`: real PostgreSQL confirms that a same-length code substitution cannot be claimed, persists failure/scrubbing and remains ineligible for subsequent claims. This is required in existing `coworker` CI, not a mock.
- Final exact PR-head `test-and-build`, mandatory no-skip `coworker` (PG/Temporal/transactions/browser/sandbox), and `ci-merge-gate`. Independent adversarial security review plus staging sandbox/worker network isolation are separate gates. No stale CI run qualifies a new revision.

## Remaining CW-10 scope and limitations

This prevents **partial-record source changes** after preparation. If a database adversary can rewrite *all* identity fields (including expected digest and owner), a digest alone is not an authorization boundary: generated code still needs a **separately persisted, immutable owner-and-run-bound proposal**, exact human decision, expiry/revocation, input versions/limits and an atomic worker-claim check tied to that decision. That lifecycle is **not** implemented here. Likewise, user-provided already-claimed source can remain in a running worker until bounded stop/cleanup; this fix prevents giving altered source to a *new* claimant rather than recalling bytes already dispatched. CW-09 staging egress/DNS/SSRF, CW-11 skills, personal context workflows and release evaluation are still incomplete.

**No automatic merge, deploy, paid provider call, or activation.**

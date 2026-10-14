# CW-10 — reject subclassed review-envelope clocks and UUID identity

**Date:** 14 October 2026 (Asia/Dhaka)  
**Workstream:** Architecture and core-agent / CW-10 reviewed generated code  
**Baseline:** main `3505c5029891d488678b1f2e8b302694ce0a96e4`  
**Branch:** `codex/cw10-exact-timestamp-uuid-review-20261014`  
**Code and adversarial test head before docs:** `6624209e7f7b2b778a9897e005fcc1aef39733e2`

## Reproduced/independently reviewed finding

The independent final review of merged [CW-10 PR #394](https://github.com/rumman52/Shuddho/pull/394#discussion_r4267484974) showed that Pydantic's `model_validate(..., strict=True)` accepts `datetime` subclasses. A custom object may override `astimezone()` to report a shorter expiry than its represented clock, allowing a copied, self-digested `CodeProposalEnvelope` to pass a bounded lifetime check while the original object is not trusted. UUID subclasses pose a similar identity-method overriding concern. The invariant applies **before** any method on the untrusted copied proposal is invoked. The envelope remains inert: no grant, workflow admission, approval, storage or execution is created by this schema.

## Bounded change and test contract

- `services/coworker/code_proposal_schemas.py::verify_reviewed_code_identity` now rejects non-exact `datetime` in `created_at` and `expires_at`, non-exact `UUID` in `run_id` and in every `CodeInputVersion.document_id` and `version_id` prior to `model_dump` or strict validation. Retain exact Pydantic classes, declared fields, immutable nested models, frozen tuple types, fully signed review digest, owner/run/input version and budget/deadline checks.
- `tests/test_agent_code_proposals.py` tests crafted `MisleadingDatetime` with an overridden `astimezone` and a three-hour disguised instant, and `UntrustedUUID` copied into run/input references. Provide each with its own consistent reviewed SHA to test the **real authority boundary**, not a trivial hash mismatch. Assert `code_proposal_invalid`; ordinary exact datetime/UUID remain valid.
- No model provider change, schema migration, Temporal history change, sandbox privilege expansion or production switch.

## Acceptance and remaining dependencies

Require final PR head `test-and-build`, `coworker`, all mandatory PostgreSQL/Temporal/transaction/browser checks, `ci-merge-gate` and independent review. A green earlier SHA does not count. Request a reviewer to adversarially check exact type guards and remaining subclassable types. If a test fails, correct the evidenced defect, not thresholds/gates.

CW-10 **still lacks** persisted immutable generated-code proposal records, exact human-reviewed approval identity, worker-claim revalidation and isolated-sandbox recovery; this patch addresses only a correctness defect in its inert envelope precursor. CW-09 still lacks read-only content capture/private hash, isolated browser SSRF/egress security tests and canonical runtime release eligibility. CW-11 versioned skill manifests and qualification remain open.

**Rollback:** keep generated-code execution unavailable and revert this isolated slice only in favor of a reviewed alternative that preserves exact class/field validation. No merging/deploying/provisioning/activation authorized.

**Next exact action:** create draft PR, obtain exact-head CI including `tests/test_agent_code_proposals.py`, get independent security review, resolve findings. Then work on the next dependency-ready core contract without treating a pure verifier as approval authority.

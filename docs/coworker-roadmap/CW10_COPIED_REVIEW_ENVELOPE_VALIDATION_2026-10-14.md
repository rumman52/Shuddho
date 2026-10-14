# CW-10 — Reject Unvalidated Copied Immutable Review Envelopes

**14 October 2026.** Workstream: Architecture/core agent CW-10.  
**Base:** `main` `9f8cf53a422ba5eee7d5a0772b2943328d3faaaa`.  
**Branch:** `codex/cw10-review-envelope-revalidate-20261014`.  
**Initial code/tests SHA:** `d3740983443bdf450422ebcab9b60e8ca9cdb9f7`. **Latest source/test SHA:** `9285ff38408f9099bcf3d80c3794169589700507` before final docs. Independent [second P2 review](https://github.com/rumman52/Shuddho/pull/394#discussion_r4266920978) found that `strict=True` reconstruction still normalizes nested mutable mappings while the original copied object remains mutable. The verifier now requires exact `CodeComputeLimits`, `CodeInputVersion`, `tuple` input/destination runtime types before parsing, with same-value mapping and mutable-list negative tests. Earlier runs are superseded; requalify final head. **Final source/test SHA before this documentation:** `db2aafa7feca94a399c816f1fc0437da51dded65`. Independent [PR #394 P2 review](https://github.com/rumman52/Shuddho/pull/394#discussion_r4266890920) observed ordinary model validation silently coerces copied JSON-like types; corrected with `strict=True`, explicit boolean schema-version rejection, and three additional malformed-but-self-hashed regressions. Require **exact new head** CI and fresh review. [Draft PR #394](https://github.com/rumman52/Shuddho/pull/394), unmerged.

## Source-backed correctness gap

Merged #392 introduced a frozen strict Pydantic `CodeProposalEnvelope` and inert `verify_reviewed_code_identity`. Pydantic `model_copy(update={...})` does **not** invoke field/model validators, despite `frozen=True`. A copied envelope may contain forbidden `egress_profile="internet"`, destinations, a mismatched source digest, invalid nested limits or a 4-hour lifetime. If the caller supplies that copied instance and its self-consistent new `review_sha256()`, the old verifier checks owner/run, hash, current inputs and maximum limits but does not confirm the object satisfies its declared immutable schema. This gap must be corrected **before** binding the envelope to persistence, human review or sandbox claims.

## Bounded change

At `verify_reviewed_code_identity`, require an actual `CodeProposalEnvelope` and reconstruct it from `model_dump(mode="python")` through `CodeProposalEnvelope.model_validate()` before time, owner, hash, source and sandbox policy checks. This invokes all nested validators even when the incoming in-memory object was copied without validation. On malformed/invalid proposal data, return deterministic `CoworkerError(code_proposal_invalid, 409)`, never an execution grant. No broader egress policies, destinations, storage grants or approval shortcuts.

Add offline regressions forging the source hash, network profile, destination, resource limits and lifetime using `model_copy`, recomputing the proposal digest in each case. Every forged envelope must be rejected even when the digest matches its malformed state. Preserve valid envelope and actual owner/revision/digest/expiry tests.

## Validation and non-authority boundary

Require `tests/test_agent_code_proposals.py`, general Python tests, full required `test-and-build`, `coworker`, `ci-merge-gate` on exact PR head; independent review for compatibility and unexpected warning/error behavior. This is still an **inert** validator, with no approval, execution endpoint, sandbox claim or production activation. User-authored fenced Python route remains unchanged. No migration, Temporal change or real external mutation. **Rollback** by reverting this isolated additive integrity guard only if an equivalent stricter model validation is installed.

**Independent dependency:** merged CW-09 main CI is red and being repaired in [draft PR #393](https://github.com/rumman52/Shuddho/pull/393); this CW-10 slice does not depend on that branch but cannot make the whole repository green until #393 is also resolved. Do not auto-merge.

**Next exact action:** open a separate draft PR, inspect exact-head CI and review, fix any findings, checkpoint the result. Then proceed with persisted owner/run immutable proposal and exact human-reviewed approval through existing sandbox.

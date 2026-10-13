# CW-10 — Immutable inert generated-code review contract (first independent slice)

**Date:** 14 October 2026 (Asia/Dhaka)  
**Base:** `main` `76a07600328d0c6ff0ed73b69d2c7933d38bf927`  
**Branch:** `codex/cw10-immutable-proposal-envelope-20261014`  
**Initial code/tests revision:** `cd5463231a9a18043f26363b33777c2a251d7b4d`. **Updated source/tests head before final checkpoint:** `804a875ddfa4f3a104b21c301a6d039eb7131084` after fixing both [P2 future-validity](https://github.com/rumman52/Shuddho/pull/392#discussion_r4263712225) and [P2 DST-duration](https://github.com/rumman52/Shuddho/pull/392#discussion_r4263771173) findings, with future-date and DST fall-back regression. The branch was reconciled to merged CW-09 main `905a09c3a5e2931be46d9053ba4af09ecd331125` using a two-parent reviewed-history-preserving merge commit; exact latest CI must rerun.; [draft PR #392](https://github.com/rumman52/Shuddho/pull/392). Independent review [P2](https://github.com/rumman52/Shuddho/pull/392#discussion_r4263712225) found future-created proposals accepted before their validity window; now verified against server-provided `now >= created_at` and new future-date regression. Full exact-head CI/re-review required.

## Requirement and initial gap

[Canonical CW-10](../superpowers/plans/2026-10-12-coworker-evolution.md) requires generated-code proposals with exact immutable reviewed owner/run/source/input checksums, limits, destinations, egress, expiry, human review, and existing isolated sandbox claim. Current Runtime v3 `sandbox.execute_python` intentionally allows **only exact user-authored fenced Python**, never model-authored source. The current sandbox worker does not have reviewed generated-code approval authority.

## In-scope change (inert and non-authorizing)

- New `services/coworker/code_proposal_schemas.py` declares a **frozen** and strict review envelope with owner, run UUID, exact raw Python source (no whitespace rewriting), verified SHA-256 source bytes, owner-scoped unique version and checksum input references, bounded CPU/wall/memory/disk/output limits, strict `egress_profile=none`, **no destinations**, aware creation and short expiry.
- Canonical `review_sha256()` hashes the entire deterministic review envelope, including source text, source and version hashes, resource policy and expiration.
- `verify_reviewed_code_identity` compares the **previously reviewed** SHA with the current envelope, exact owner/run, independently supplied current input-version tuple, current sandbox ceiling and expiry. It returns no execution grant, generates no approval token and cannot call the sandbox.
- New `tests/test_agent_code_proposals.py` exercises valid deterministic review, a modified source+source digest, limits, expiry, owner/run mismatch, revoked/stale input refs, cross-owner refs, fake hashes and network destinations.

## Security and compatibility

This slice is preparation toward **CW-10 step 1 only**, not execution or approval. Existing exact-user-Python pathway, `sandbox.execute_python`, sandbox worker, provider ledger, PostgreSQL models/migrations and user interface are **untouched**. Zero real external mutations or provider calls. It is not equivalent to an operational code-review flow or a CW-10 completion claim.

## Required next acceptance

1. Persist immutable proposals with additive migration and owner/run/idempotency/revision bound to exact source and private input versions.
2. Present exact reviewed source and policy to owner; persist an actual human approval with canonical hash and expiry. No conversational shortcut or model approval.
3. At **worker claim**, atomically validate owner, run, approval, source+input hashes, expiry, storage refs, policy ceilings, egress and release grant. Reuse the *existing* isolated compute rather than another worker/execution ledger.
4. Verify stale revocation, race/cancel/replay, source tampering, budgets, cleanup, output checksums, preview origin, zero secret/network access with PostgreSQL+staging. Keep generated-code execution **disabled** until operated security gates pass.
5. Exact final PR-head CI for this bounded slice, including mandatory coworker checks; resolve independent review findings.

**Rollback:** remove this inert schema/test contract without touching production database or execution. **Current status:** Implemented on isolated branch; CI and PR review pending. No automatic merge, deploy, paid provisioning or activation.

**Next exact action:** Open draft CW-10 PR and verify focused tests and mandatory exact-head CI; then choose next storage/approval persistence slice after review.

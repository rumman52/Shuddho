# CW-09 — independent Agent browser read release evidence contract

**Date:** 14 October 2026 (Asia/Dhaka)  
**Repository:** `rumman52/Shuddho`  
**Baseline:** `main` `d6ba9c183860284207cafd5f8cc2052205080837`  
**Branch:** `codex/cw09-agent-browser-release-contract-20261014`  
**Source and contract regression SHA before docs:** `a069daf5d2567e84d5bff3c1e525553e1d98d9b4`

## Existing evidence and gap

CW-09 Agent `browser.read` is implemented as a **default-off** Runtime v3 tool backed by the owned browser broker and worker. The merged receipt/cancellation safety repair [PR #389](https://github.com/rumman52/Shuddho/pull/389) reached passing mandatory PostgreSQL and dedicated browser suite steps in [run 38456526299](https://github.com/rumman52/Shuddho/actions/runs/38456526299); at this contract's bootstrap, full coworker/merge-gate CI and current main CI had not completed. This does not verify the remaining live browser boundary or production readiness.

Prior to this patch, the canonical `scripts/release_contract.py`, `docs/staging-evidence.template.json` and `docs/cohort-rollout.template.json` registered only generic `browser`, not independently `agent_browser_read`. Thus a rollout could not separately attest or enforce an independent Agent read gate through the canonical capability, rollback and activation-evidence interface, contrary to CW-09's explicit read-only release boundary.

## Bounded change

- Add `agent_browser_read` to `OPTIONAL_CAPABILITIES` with dependencies on `browser`, `runtime_v3` and `connector_trust_boundary`.
- Require a distinct `agent_browser_read` staging gate, describing operated single-owner/session/run/receipt identity, no interaction/submission, private bounded captured page content and true content hash, egress/redirect/metadata SSRF denial, prompt injection, cancellation/TTL cleanup and runtime eligibility. **Metadata-only title hashing does not satisfy the content-capture gate.**
- Add separate rollback entry `agent_browser_read_kill_switch` with `SHUDDHO_AGENT_BROWSER_READ_ENABLED=false`.
- Register `agent_browser_read_verified` activation evidence, own ledger event and artifact key with next distinct schema version 34. This is a declaration of expected evidence, **not** creation of evidence or permission to activate.
- Extend checked-in rollout and staging templates with **false/pending** values.
- Add canonical contract tests showing default-off and independent gates; missing supervised browser dependency or correct rollback fails release validation; future activation must have its own ledger requirement.

## Acceptance and negative cases

- Template keys exactly match canonical expected capability/rollback/staging sets.
- With Agent read disabled, no new required gate or activation proof is introduced.
- Turning Agent read on (even with a qualified generic browser) introduces independent `agent_browser_read` staged evidence and activation proof.
- Missing `browser` dependency or invalid Agent read rollback fails `validate_rollout`.
- Required release-contract tests and exact-final-head `test-and-build`, `coworker` and `ci-merge-gate` pass without suppressing mandatory checks.
- No existing rollout is implicitly opted in; none of these changes start a browser, produce a receipt or change live deployment flags.

## Authority, compatibility, rollback and remaining work

This **only registers** the existing code-owned Agent tool for reviewable rollout/ledger qualification; it does **not** add an alternate activation ledger or relax the current broker flag validation. No DB migration or Temporal history change is needed. Keep flag disabled until actual staged evidence, independent security review, canonical enforcement at **runtime execution** and operated read-only page capture/private source digest are in place. Thus CW-09 overall remains incomplete, and current main's merged PR #389 CI still needs an exact-result checkpoint.

Rollback: keep `SHUDDHO_AGENT_BROWSER_READ_ENABLED=false`; revert this additive contract PR if necessary. Existing deployments without the new key should remain disabled through canonical normalization; rollout template defaults false.

**Next exact action:** Open draft PR on this isolated branch. Obtain exact-final-head CI, independent review and evidence checkpoint. Never auto-merge, provision, deploy or enable flags. Continue CW-09 runtime eligibility and content capture as separate dependency-ready reviewed slices; CW-10/11 remain pending.

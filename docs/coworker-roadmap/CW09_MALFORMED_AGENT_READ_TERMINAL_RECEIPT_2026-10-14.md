# CW-09 — Terminal handling for malformed Agent browser worker receipts

**Date:** 14 October 2026 (Asia/Dhaka)  
**Workstream:** Architecture and core agent; read-only browser broker  
**Base main:** `607b828274f9f4c580cd3dbd2ea5889d947904fc`  
**Branch:** `codex/cw09-terminal-malformed-agent-browser-evidence-20261014`  
**Source/test baseline:** `846f7f5a72edef2025fbcfed496594605a84c8c1`; **P1 review correction through source/test commit:** `5832dce5eff5bdb04a8efab07f3861e8fb7d27b0`

## Reproduced invariant gap

`BrowserRepository.complete_command` validated untrusted worker data via `_bounded_observation` **before** entering its success-path transaction. For a claimed, code-owned Agent `browser.read` command, any shape/type error (non-object, missing URL, invalid title or DNS collection) raised `CoworkerError` without setting a terminal command/session state. The same claimed worker could then send a different well-formed receipt for the same already-attempted navigation, and the Agent runtime could settle it as a verified observation. The existing interaction signal path already handled interactive evidence with an explicit terminal commit; this malformed-envelope path did not.

This is a bounded broker receipt correctness/safety defect, not a change in browser functionality.

## Chosen patch and boundaries

- Inside `services/coworker/browser.py::complete_command`, catch the existing typed `CoworkerError` from `_bounded_observation`.
- Reacquire the existing session-before-command PostgreSQL row locks; for a still-running, exactly worker-claimed, **`agent_read_only=True`** command, atomically record `failed` on the command and session with `browser_observation_invalid`, clear claim/lease, sealed command/session state and takeover affinity/frame, mark cancellation, and write the existing `AuditEvent` record. **Commit** that state before propagating the validation error.
- Do not mutate an ordinary interactive/supervised browser command: its existing validation exception and retry behavior remain unchanged. Do not let a different worker claim the malformed Agent command.
- Tests use the existing database-backed real `BrowserRepository` for malformed non-object, missing final URL, invalid DNS collection and title type; assert the command is terminal, canceled session cannot reopen, and a later rewritten successful receipt is rejected. Existing non-Agent `prepare_navigation` behavior is separately checked: invalid evidence remains retryable and the same rightful worker can finish with genuine valid evidence.
- Do not alter database tables, workflow history, broker egress policy, runtime feature flags, provider credentials, grant/approval ledgers or production release eligibility.

## Acceptance and failure cases

1. Dedicated no-skip `tests/test_agent_browser_tool.py` runs with five new cases and existing replay, revocation and no interaction tests.
2. `tests/test_browser_broker.py` preserves normal session ownership and malformed-observation retry contract.
3. Exact final PR revision passes `test-and-build`, `coworker`, mandatory PostgreSQL/browser tests and `ci-merge-gate`, with independent review findings resolved. A green older revision does not count.
4. The failure path does not leak worker secrets/content into ordinary receipts/logs; no misleading “verified read” is created.
5. **P1 independent review resolution:** reviewer identified post-envelope errors inside the broker transaction that rolled back attempted terminal states. The corrective patch now wraps completion in a rollback-first `try/except CoworkerError`, then commits Agent-only failed/cancelled state through the same session-before-command helper for observation errors. State-control exceptions (cancelled/expired/takeover, lost claim, disabled flag) do not reactivate or overwrite terminal states. Tests include invalid storage, URL, missing DNS and cross-origin redirect, rewritten receipt denial, and wrong-worker claims. This addresses bounded broker observation-validation errors, **not** actual page content, egress staging or production qualification.

## Rollback and remaining work

Retain `SHUDDHO_AGENT_BROWSER_READ_ENABLED=false`. Do not automatically merge/deploy/activate. Remaining CW-09 requirements: bounded actual page text persisted privately with source checksum/provenance, worker network/redirect SSRF bypass qualification and canonical release eligibility enforced at execution. CW-10 requires persisted immutable exact-reviewed generated-code approvals, CW-11 requires reviewed manifest publication/runtime grant constraints; these are not completed here.

**Next exact action:** Open draft PR, inspect exact head CI and independent review, diagnose any fail from actual logs, then update `PROGRESS.md` with exact evidence and next unmet task.

# CW-09 — Agent browser receipt expiry revalidation (15 October 2026)

**Base revision:** `main` `96462220bb4d418227b322e55c6b4e4b60e67cd5`. **Branch:** `codex/cw09-expired-agent-receipt-guard-20261015`. **Contract source:** [SPEC](SPEC.md) and [acceptance inventory](ARCHITECTURE_CORE_ACCEPTANCE_INVENTORY_V1.md). **Work item:** CW-09 data integrity / late authorization.

## Reproduced source-level gap
The broker's `read_agent_capture` checks browser-session expiry when it opens the owned, sealed visible-text observation. The separate `AgentRepository.finish_invocation` transaction previously checked the persisted `cancel_requested` and terminal state but **not** `expires_at`. Likewise `_settle_agent_browser_session(completed=True)` had no expiry guard. A session can expire **after** the broker getter but **before** the final authoritative ToolReceipt commit. In that race, the old code could mark the Agent invocation completed with a stale read. The same gap exists for legacy metadata-only receipts. This is a source-level gap, not evidence of an observed live exploit.

## Required result
- At final Agent ToolReceipt settlement, independently recheck the owner-bound browser session's `expires_at` against trusted server time while holding its row lock. Expired sessions must **never** yield a verified Agent ToolReceipt, regardless of earlier successful browser-command completion or prior content retrieval.
- The canonical session settlement helper independently denies `completed=True` for expired sessions, for defense in depth. On `completed=False`, keep the existing cancellation cleanup semantics.
- Preserve broker expiry-sweep ownership, ciphertext deletion, worker-claim restrictions, replay compatibility, old metadata-only read semantics, default-off feature, state machine and existing no-double-action guarantees. Do not invent browser content, merge, deploy or activate.

## Falsifiable acceptance
1. A real owned Runtime v3 run queues a read; an existing browser worker claim completes before expiry, optionally with bounded private text. The server can read the completed capture while unexpired.
2. Simulate expiry **between** the first observation transaction and the final Agent receipt transaction. Direct final settlement returns `browser_session_closed`, adds **no** `ToolReceipt`, and cannot be replayed into success.
3. Both metadata-only legacy and actual bounded content cases are covered. Subsequent broker expiry sweep persists `expired` state and removes transient sealed page text from the stored worker command.
4. Mandatory final SHA `test-and-build`, zero-skip `coworker` (PostgreSQL/Temporal/browser/transaction) and `ci-merge-gate` pass, followed by independent adversarial review before merging.

**Not established by this slice:** operated staging browser egress, DNS rebinding/SSRF, private source artifact lifecycle, the CW-10 generated-code execution approval lifecycle, CW-11 reviewed skills, complete architecture/core workstream or production qualification. No activation is authorized.

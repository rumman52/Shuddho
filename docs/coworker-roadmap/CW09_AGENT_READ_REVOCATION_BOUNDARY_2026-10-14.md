# CW-09 — Agent browser read kill-switch at worker boundaries

## Task contract

- **Objective:** A disabled `agent_browser_read` capability must prevent queued or claimed autonomous Agent browser navigation from receiving a new worker egress grant or a verified completion receipt, while supervised browser sessions continue using their independent permissions.
- **Canonical workstream:** CW-09 read-only brokered browser; `docs/coworker-roadmap/SPEC.md` and `docs/superpowers/plans/2026-10-12-coworker-evolution.md`.
- **Base branch/SHA:** `main` at `7da39a13e0207b96a2b05dde72e1fb876a970a5c`.
- **Review branch:** `codex/cw09-agent-read-revocation-boundary-20261014`. Draft PR and actual final head to be read from GitHub.
- **Previously present:** `ToolSpec.enabled` and `AgentRuntime.execute_step` rechecked the Agent feature switch, but `BrowserRepository.claim_commands`, `worker_control`, worker network preflight and `complete_command` did not distinguish an already-prepared Agent command after the Agent switch was disabled.
- **Changed interfaces:** Existing `BrowserRepository.create`, `prepare_agent_read`, `claim_commands`, `worker_control`, `validate_worker_network_target`, `complete_command`. Adds a broker-internal terminal revocation helper, not a ledger or public API.
- **Acceptance:** A queued `agent_read_only` command is terminally failed before claim when disabled. An already-claimed read is denied the next broker egress check, stopped by worker control, and prevented from settling a late completion. Non-Agent supervised navigation remains eligible when its own browser capability is enabled.
- **Failure behavior:** `browser_agent_read_disabled` with an owner-scoped terminal command/session; no retries or production activation, and no Agent-generated external mutation.
- **Checks:** `uv run --extra coworker pytest tests/test_agent_browser_tool.py tests/test_browser_broker.py -q`, mandatory repo `test-and-build`, `coworker` and `ci-merge-gate` at the final PR head. Actual pass/fail/skip counts must be recorded from CI, not inferred from commits.
- **Secrets/ownership:** Existing server-owned session and command rows, claim leases and worker service identities remain authoritative. Browser worker cannot bypass the broker's DNS/origin check through a model instruction. Flag changes do not grant new resources.
- **Rollback:** Revert this isolated PR. The Agent capability remains default-off. No production flags changed.
- **Out of scope:** Independent release-ledger activation verification, encrypted private page-content capture, live isolated DNS/redirect bypass qualification, and production activation.

## Risk and review

This closes the application broker's revocation checks, but **cannot guarantee that an HTTP request already permitted just before a kill-switch change is undone**. Existing worker polling, cancellation and isolation policies remain necessary. Real worker-process tests with staged flag transitions are still required for operated assurance.

Self-review before PR: confirmed that the new helper affects only commands explicitly tagged `agent_read_only`, not interactive takeover or human-supervised reads. Exact-head tests and an independent review are pending.

## Completion evidence

| Level | State |
| --- | --- |
| Implemented | Broker guard and regression tests on review branch; final SHA pending docs update |
| Repository-verified | Pending exact-head mandatory CI, zero mandatory skips and review |
| Staging-verified | Not established |
| Production-qualified | Not established |
| Activated | No |

**Next exact action:** Open a draft PR, run/inspect final-head `test-and-build`, `coworker` and `ci-merge-gate`, review worker stop/network behavior and correct any failures without weakening tests. Then continue CW-09 page-content/private provenance and canonical execution-time release-gate work in a separate PR.

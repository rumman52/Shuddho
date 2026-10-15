# CW-10 — Exact code binding during Agent sandbox resume

**Date:** 15 October 2026. **Base:** `main` `1a75eb2f66595ef6ec2f8ccd01156f03276c9566`, incorporating [PR #410](https://github.com/rumman52/Shuddho/pull/410). **Branch:** `codex/cw10-agent-sandbox-source-binding-20261015`. No merge/activation/deployment authority.

## Reproduced code-level gap
The current user-authored fenced Python path in `AgentRuntime.execute_step` is correctly separate from future model-generated code approval. It creates an owned `SandboxSession` and an immutable `SandboxExecution` containing the exact source SHA-256 and source byte count. On subsequent invocation resume, however, `AgentRuntime` fetches `list_executions` and consumes the first execution state and result **without checking the source SHA/length against current `ToolInvocation.arguments.source`**. If a persisted invocation has been modified, mis-replayed or misbound, a result for code A could be attributed to a request for code B. A session ID alone is not proof of exact code identity. This is source-level logic, not evidence of an actual privilege escalation.

## Integrated bounded fix
- The actual sandbox branch in `services/coworker/agent_runtime.py` validates that the owned session has exactly one execution and that its persisted source byte count **and SHA-256 over UTF-8** equal the current invocation source before reporting `prepared`, `running`, `succeeded` or committing an Agent ToolReceipt. Deny with typed `409 sandbox_source_binding_mismatch` on ambiguity or changed source, without a second sandbox job, extra grant, or incorrect receipt. Existing standard single-execution idempotent retry remains.
- Integration tests in `tests/test_sandbox_control_plane.py` begin a real owned Agent v3 Python step, persist code A, modify its stored invocation to same-byte-length code B, and require denial both before the worker claims and after the original worker confirms success. Assert that no alternate execution or ToolReceipt was produced. Existing sandbox tests cover ordinary valid success, owner isolation, sandbox worker, cancellation and credentials.
- No new schema, Temporal contract, provider integration, tool registry entry, approval decision or production flag. The sandbox stays gated and the generated-code route remains **unapproved** until a separate CW-10 review lifecycle is implemented.

## Acceptance / limits
1. Fail closed for different code bytes on resume even when length is equal; reject ambiguous multiple job records; do not emit false verified receipt or repeat execution.
2. Existing own user-authored source path still reaches real sandbox with user-only code, not model text. All required CI on exact final SHA: `test-and-build`, mandatory zero-skip `coworker` including PostgreSQL, Temporal and sandbox, and `ci-merge-gate`. Independent review and operating-stage tests are separate.
3. This is **not** the new model-generated code review and approval path. Remaining CW-10: persist exact code/input versions/limits and expiry, record authorized human decision, atomically revalidate approved claim, sandbox execution and source revocation, bounded result/cleanup and operated staging. No new model authority.
4. Preserve CW-09 live browser/DNS/SSRF isolation, CW-11 skill version/grant, personal context isolation, and release evidence as independent remaining requirements.

**Do not merge/deploy/activate without review and explicit authorization.**

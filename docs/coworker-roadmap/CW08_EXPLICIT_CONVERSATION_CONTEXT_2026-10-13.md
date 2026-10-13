# CW-08 — Explicit selected-source boundary for conversation planning

## Objective and observed behavior
A conversation message without explicit source selections must not silently ingest private prior task instructions, notes or generated draft content into its Agent planner context. This is a privacy/purpose authorization boundary, not just lexical relevance. A conversation's explicit selected_sources is the sole prior-workspace document selection boundary; prior task text was not admitted in the conversation source pin.

As inspected on `main` `b2a6920d2fea10dfc5a813746e19c7241597846b`, `ContextService._resolved` always searched up to 12 completed/needs-input `Task` rows for the same owner/workspace and added lexical matches to source_map and planning. `ConversationDispatchService.dispatch` authorizes only message.selected_sources and passes those document pins through `AgentRun.input_versions`. Therefore an empty selection still admitted matching historical task text. This contract gap is independent of the previously merged CW-08 exact selected source pin recheck.

## Change contract
- **Task:** CW-08 Architecture/Core Agent context consent.
- **Base:** `main` at `b2a6920d2fea10dfc5a813746e19c7241597846b`.
- **Branch:** `codex/cw08-explicit-conversation-context-20261013`; draft PR links from GitHub when created.
- **Touched code:** `services/coworker/context.py`, `tests/test_context_memory.py`.
- **Control:** For `run.idempotency_key` with server-owned `conversation:` prefix, bypass implicit completed/needs-input prior-task search. Existing `require_admitted_conversation_run_sources` in _run_and_sources first checks the original owned message, matching run link and immutable admitted pins.
- **Compatibility:** Standalone/direct Agent runs retain the established owner/workspace prior-task retrieval; no settings, migration, schema or workflow history change.
- **Authority:** No new permission, approval, credential, tool, network egress, memory proposal, or provider action. Explicit selected documents still flow through existing owner, sha256, version, expiry and deletion rechecks.

## Regression acceptance
1. Create a real completed owner task with private notes and a stored draft step; direct Agent run with the same lexical topic still sees the prior task under its existing continuity contract.
2. Create a same-owner conversation and append a message selecting no source. Explicit dispatch creates a new run linked to the owner message.
3. `context.for_run` and `context.planner_context` must exclude prior_task entries and private task text; context budget usage is zero absent another selected source; no extra Agent launch or mutation occurs.
4. Existing CW-08 pinned-source hash/version/owner/revocation tests and mandatory conversation ownership/race suite must remain green.

## Failure and rollback
- Failing or missing bound message/source hash still denies at worker use; this patch does not weaken those checks.
- Disabling context retrieval still returns the previous disabled projection; direct Agent behavior unaffected.
- Rollback removes the conversation-specific prior task exclusion and its test. That would reintroduce unintended private task context, so verify explicit consent requirements before rollback.

## Verification and review
- Required focused commands: `uv run --extra coworker pytest tests/test_context_memory.py tests/test_conversation_context.py tests/test_conversation_dispatch.py -q -rs`; mandatory GitHub Actions exact-head `coworker`, `test-and-build`, `ci-merge-gate`.
- Current connected-GitHub environment is not a full runnable checkout. Do not claim local pytest, staging or human acceptance. Inspect exact PR head, all mandatory check outcomes and skips before marking repository-verified.
- Self-review concerns: Origin prefix is server-assigned at conversation dispatch and forbidden from direct Agent-create keys; the remaining old direct-run prior-task behavior is a separate consent-contract review, not silently changed here. A live worker race still needs frozen staging qualification.
- **Operational evidence:** not established. No production activation.

## Evidence status
| Level | Status |
| --- | --- |
| Implemented | Source regression on review branch; final exact SHA in PR |
| Repository-verified | Pending required exact-head CI |
| Staging-verified | Unverified |
| Production-qualified | Not established |
| Activated | None |

**Next exact action:** Open draft PR, inspect mandatory GitHub Actions against final head; fix any failure without weakening the source selection boundary. Obtain independent review where available, then continue CW-08 selected file/context lifecycle or independently ready CW-09 typed browser work; keep those separate from this PR.

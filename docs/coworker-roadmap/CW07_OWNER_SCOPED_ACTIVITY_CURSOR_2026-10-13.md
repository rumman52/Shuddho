# CW-07 — Owner-bound resumable conversation activity

- **Objective and user-visible behavior:** Reconnecting to an owned conversation restores every previously dispatched Agent activity card (up to the configured 2,000-message bound), rather than only the newest 50 messages. Polling refreshes run state even if no new message was appended. Reading activity never dispatches work.
- **Dependencies and evidence:** CW-05/06 message and durable run ledgers are on main. PR #384 CW-08 worker source pin fix is merged, with exact-head successful [CI 38395801164](https://github.com/rumman52/Shuddho/actions/runs/38395801164). Operated CW-02–04 staging and live browser qualification remain separate gates.
- **Base:** `main` at `4b369fa99b9a7c4784f5060aa3399a58e340815f`.
- **Branch:** `codex/cw07-owner-bound-activity-cursors-20261013` (draft PR pending initial creation).
- **Observed gap:** `ConversationDispatchService.activity` returned only the most recent `limit` messages, with no `after` cursor or `next_cursor`. The CW-07 web UI always consumed that snapshot. Longer conversations lost older Agent work cards on reconnect.
- **Existing authorities reused:** `Conversation`, `ConversationMessage.sequence`, `AgentRun`, `AgentEvent`; no new database ledger, migration, provider, credential, or approval permission.
- **Modified interfaces:** `ConversationDispatchService.activity(owner, conversation_id, *, after=None, limit=50)` and read-only `GET /conversations/{conversation_id}/activity?after=...&limit=...`. `after=start` selects first page in ascending message sequence; subsequent `v1` owner/conversation-bound checkpoints walk message pages. The response adds `next_cursor` and `has_more`, preserving existing `items` and `message_sequence`. Legacy `after` omission still returns latest N snapshots so run progress can change with no new messages. Cursor is a position, not an access grant, credential or event subscription.
- **Frontend:** `CoworkerClient.conversationActivityHistory` retrieves up to twenty 100-message pages from the owned server, advancing through undispatched messages; `ConversationWorkspace` uses it on reconnect and polling. Max configured messages is 2,000. No infinite pagination loops, a stalled cursor fails visibly; errors use existing UI rendering.
- **No side effects:** GET is read-only; append/dispatch and approval controls remain explicit and separate.
- **Accepted cases:** Two launched runs separated by an unlaunched message, cursor page advancement across idle message, empty terminal page, unsupported/foreign cursor failure, foreign owner 404, old snapshot capturing later cancellation and no extra AgentRun rows. HTTP contract handles valid/invalid cursor. Existing conversation and UI tests remain unchanged.
- **Failure outcomes:** Owner or conversation not found: existing 404; malformed, foreign or future cursor: `invalid_cursor` (422); out of range page limit 422; disabled conversations 409. A cursor alone never grants permissions.
- **Verification:** `uv run --extra coworker pytest tests/test_conversation_dispatch.py tests/test_conversations.py tests/test_conversation_context.py -q -rs`; `npm run test --workspace @shuddho/web-editor`; `npm run build --workspace @shuddho/web-editor`; mandatory exact-head GitHub `coworker`, `test-and-build`, `ci-merge-gate`. Current GitHub connector environment has no complete local repository checkout, so CI is the required executable evidence. Verify zero skips in mandatory safety suites.
- **Compatibility and rollback:** Existing unpaginated endpoint works unchanged for clients unaware of `next_cursor`. Revert backend cursor + frontend history use if incompatible; no schema/history migration. Long pagination remains bounded by 20 pages.
- **Authority and security:** All read queries verify owner and non-deleted conversation; cursor scope digest rejects replay to another conversation. The digest is not a security secret, and cursor data is not used for access decisions; ownership is enforced independently in SQL.
- **Unmet qualifications:** Live mobile/keyboard/reconnect accessibility, operated staging with real concurrent run updates, independent PR review and full CW-07 activity/state validation. This code slice alone does not qualify production.

## Evidence checkpoint

| Level | Result |
| --- | --- |
| Implemented | Source, frontend and regressions committed to branch, verification pending |
| Repository-verified | Pending exact-final-head GitHub Actions |
| Staging-verified | Not established |
| Production-qualified | Not established |
| Activated | No new capability or provider activation |

**Review risk:** Cursor position is message-sequence-based; it is not a durable *event* feed and does not replace existing per-run `AgentEvent` streams. UI intentionally rereads activity history to capture changes on already-seen runs. A fully event-sourced combined feed remains outside this bounded CW-07 slice.

**Next exact action:** Open draft PR; verify mandatory CI on its final implementation SHA, inspect failure logs and review any owner-scoping or latency findings; seek independent review. Follow with remaining CW-07 live UI qualification and CW-08/09 capability slices.

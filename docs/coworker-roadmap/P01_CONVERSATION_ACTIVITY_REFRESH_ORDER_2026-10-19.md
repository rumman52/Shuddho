# P-01 / CW-07 — Conversation activity refresh ordering

Date: 19 October 2026 (Asia/Dhaka)  
Base: `bc88f124e61f003bcbf70dbba2303590992edd0a` (PR #482 merged)  
Review branch: `codex/p01-conversation-activity-refresh-race-20261019`

## Defect

`ConversationWorkspace` retrieves message history, activity and conversation list
every five seconds. Polls can overlap when an earlier request is slow, and
`reloadConversation` after dispatch/cancel may execute concurrently with a
poll. Without request ordering, an older response can overwrite a later state
(e.g., `completed` becomes `running` on screen). Changing the selected
conversation also requires invalidating old refreshes.

## Acceptance

- A new poll supersedes the old poll only after the old in-flight poll settles;
  background polling is serialized to avoid uncontrolled accumulation.
- An explicit refresh after a confirmed mutation supersedes any earlier poll.
- Older responses cannot overwrite newer activity or a different conversation.
- No refreshed read creates an Agent run or grants new permissions.
- Existing owner-authenticated read-only activity and cursor contracts remain.
- Unit tests validate stale response rejection and selection invalidation.
- Exact PR-head frontend tests/build and mandatory CI must pass before merge.
- Live UI reconnect/staging evidence is not supplied by mock HTTP/node tests.

## Scope

Only UI refresh sequencing and its pure helper; no schema changes, new orchestration,
agent provider changes, default capability activation, credential usage or
ExternalAction authority. Existing Bangla/free writing and Gemma rollback remain.

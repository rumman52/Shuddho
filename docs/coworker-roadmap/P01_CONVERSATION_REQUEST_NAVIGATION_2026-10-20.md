# P-01 — preserve conversation request and linked-run identity

- Base: main `b6e57dd8f378b0b878c66fd6ef8ceb1d09dbcb4d`; branch `codex/p01-conversation-request-navigation-20261020`.
- Objective: a conversation result opens its exact owned Agent run, including runs older than the thirty-item history; retry identity is retained only for the same normalized payload.
- Existing interfaces: conversation resource_links, CoworkerWorkspace tab state, owner-authorized `client.agentRun(id)`, existing client request keys and backend conflicts.
- Defects reproduced with actual mounted React components and a deterministic client boundary: exact linked run discarded by navigation; edited message/title reuses the key for an already accepted original payload. Three failures before fix; unchanged message retry positive control passed.
- Plan: bind title key to normalized title and message key to conversation/text/exact source selection; forward linked run ID into keyed AgentWorkspace and load it through existing authorized GET; retain history limits; test unchanged and edited retries, out-of-history target and denied target; full JS tests and web-editor build; independent review and exact-head CI.
- Files: ConversationWorkspace.tsx, CoworkerWorkspace.tsx, AgentWorkspace.tsx, conversationIdentity.test.tsx, test runner, dev-only react-test-renderer dependency and lockfile.
- Request behavior: identical response-loss retry must preserve the original key. A deliberate payload change creates a distinct request. No automatic dispatch or permission change. Source selection order is retained exactly, matching the backend payload fingerprint.
- Navigation behavior: default Agent tab remains recent history; explicit conversation links carry the owned run ID. Failed target retrieval displays an error without substituting unrelated work. Keyed remount and aborted effects prevent a previous focused response from winning after navigation.
- Verification boundary: mounted component/client integration is repository evidence, not operated UI reconnect/API/worker/model qualification. Local Chromium download failed; existing mandatory browser CI remains required.
- React review: independent requests stay parallel; effects abort on unmount; transient retry state stays in refs; controls and labels remain accessible; no CSS/UI library or production dependency added.
- Default-off, approval, model provider, API, schema and backend history limits remain unchanged. No deployment or activation.

## Completion evidence

Pre-fix: 3 failures and 1 positive control passed. Final six component scenarios passed; complete JavaScript workspace suite passed (web-editor 120 tests, zero failures/skips/cancellations); final web-editor TypeScript/Vite build passed. Independent read-only agent review: no Critical/Important findings. Exact-head CI: pending. Staging/production: unverified. Activated: no.

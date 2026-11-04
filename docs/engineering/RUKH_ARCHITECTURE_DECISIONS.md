# Rukh AI architecture decisions — verified source snapshot

1. **Product separation:** Coworker and Editor remain separate application routes. Do not collapse them into one generic chatbot.
2. **Coworker entry:** authenticated Coworker workspace initializes to conversations. The root route is gated by `VITE_COWORKER_ENABLED`; a disabled flag routes users to the workspace home. This fail-closed behavior is preserved.
3. **Conversation versus execution:** saving a user message and requesting a direct assistant reply are distinct from explicit Agent dispatch. Plain chat must not silently authorize tool execution.
4. **Direct reply transport:** `POST /api/v1/conversations/{conversation_id}/messages/{message_id}/reply` returns a persisted reply state; the DeepSeek adapter currently requests `stream: false`. Do not simulate token streaming.
5. **Progress transport:** task progress has a separate SSE endpoint; it is not evidence that direct conversation replies stream.
6. **Source of truth:** conversation/message state is retrieved from the authenticated backend API. Session storage is only a convenience for restoring a selected task/conversation, not the durable message store.
7. **Identity:** Coworker frontend obtains the current Supabase Auth session and supplies its access token through the Coworker API client. No service-role credential is used in the browser.
8. **External actions:** agent tool dispatch and consequential actions remain behind the existing backend authorization/approval boundary. This recovery did not broaden tool authority.
9. **Editor handoff:** Editor remains independently routable; cross-app document identity/ownership must be verified in staging before release.

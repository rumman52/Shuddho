# Rukh AI remaining blockers — 4 November 2026

1. **Heavy Coworker CI:** PR #619 heavy Coworker job was still running at the last checkpoint. Wait for exact-head result.
2. **Independent review:** PR #619 is draft and has no independent review. Do not merge.
3. **Main governance:** main governance audit failed because branch protection is not confirmed. Requires repository owner/admin action.
4. **Render workspace:** confirm the `Rumman` workspace before service/database inspection; current staging database and worker state are not verified.
5. **Vercel project access/preview:** connected Vercel context does not expose a Shuddho-linked project; PR #618 reported the Hobby daily deployment limit.
6. **PostHog telemetry:** active project 675660 reports no ingested events in the last 30 days. Privacy approval and environment configuration are still required.
7. **Coworker activation:** `VITE_COWORKER_ENABLED` and backend conversation-reply configuration must be verified in staging; no production flags were changed.
8. **Direct reply streaming:** provider uses `stream: false`; implement only after designing persistence, cancellation, reconnect and duplicate-submission semantics.
9. **Production qualification:** no live provider run, browser E2E against deployment, backup/restore drill or production release was performed.

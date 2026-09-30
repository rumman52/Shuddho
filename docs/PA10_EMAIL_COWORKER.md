# PA-10 bounded proactive Email Coworker

**Status: repository implementation slice; default-off behind existing automation, connector-read, Runtime v3, planner, context and Work Service gates.**

## Outcome

An explicitly configured Email Coworker automation listens only to one authenticated `email_read` connector source already managed by the PA-06/PA-10 event pipeline. After provider verification, dedupe and synchronization, the event records the exact connector snapshots changed by that sync. A goal-bound Email Coworker admits a bounded Runtime v3 run only when the changed active email snapshot is relevant enough to the user's active goal or carries a deterministic action/urgency signal.

The run can summarize the authorized email context, identify action items/dates/meeting relevance, recommend a follow-up and prepare an email draft when useful.

## Authority boundary

- Incoming email is untrusted data.
- Email content cannot grant permissions, change tool scope, expose credentials, cross owners, or invoke arbitrary tools.
- The proactive run persists `tool_allowlist=["report.create", "email.draft"]`.
- It receives no `ExternalAction` IDs.
- `email.send` remains a separate consequential approved-action tool.
- Sending still requires the existing immutable-preview, explicit-approval, fresh-authorization, provider-receipt and reconciliation path.
- A proactive event cannot modify recipients, calendar state, provider mailbox state, publishing state, purchases or payments.

## Exact event context

Migration 0042 adds `cw_connector_events.synced_snapshot_ids`.

`ConnectorReadRepository.apply_sync` returns the snapshot IDs actually inserted/updated by the authenticated event synchronization. The event binds those IDs before proactive consumers execute. Retry after cursor advancement preserves the first non-empty evidence set, preventing a recovered event from silently widening to unrelated mailbox snapshots.

Email Coworker passes those exact snapshot IDs into the existing Agent run snapshot-scope field introduced by Meeting Coworker. Context retrieval therefore sees only the exact changed message snapshots plus still-authorized goal documents.

Deleted messages or events with no changed active email snapshot are suppressed.

## Relevance

A deterministic low-cost gate checks the active goal against bounded provider metadata and common urgency/action signals before spending a planner call. The model remains responsible for synthesis and drafting, not authority.

## Dedupe and recovery

The existing connected-event occurrence identity remains owner + automation + automation revision + connector event ID. Provider event dedupe, retry leases, automation occurrence recovery, Runtime v3 idempotency and notification outbox semantics are reused rather than duplicated.

## Notifications

Start and completion notices are generic, quiet-hour aware and deduplicated. They do not include email body/subject content. Completion copy explicitly states that nothing was sent.

## Qualification boundary

Repository CI can verify event evidence, owner scope, exact-context binding, prompt-injection treatment, duplicate suppression and no-send authority. It does **not** prove live Gmail/Outlook delivery.

Controlled staging still must verify Gmail and Outlook authentication, duplicate/out-of-order/delayed events, token refresh/expiry, disconnect/reconnect, deleted messages, malicious content, quiet hours, Browser Push and explicit send approval.

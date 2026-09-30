# PA-10 automation controls and execution visibility

**Status: repository implementation slice stacked after goal-driven proactivity.**

## Outcome

Users can inspect and manage automation without hidden background authority.

This slice reuses existing automation revisioning and occurrence/run ledgers to add:

- reviewed edit controls for time-based schedules and Meeting Coworker preparation windows;
- per-automation quiet-hours editing;
- recent execution evidence with trigger type, due time, occurrence state/reason and Agent run state/message;
- explicit guidance that connected-event source changes require cancel + newly reviewed recreation rather than silent connector replacement.

Pause, resume, cancel, notification consent and Browser Push controls continue to use their existing paths.

## Edit boundary

The backend PATCH endpoint already enforced expected automation revision. The frontend now uses it directly.

Time-based edits update only the reviewed schedule. Meeting edits update only the preparation window. Every edit increments the automation revision and queues normal Temporal reconciliation.

Changing a connected-event source is intentionally not an inline edit because it changes authorization. The UI requires cancellation and a newly reviewed automation instead.

## Execution visibility

The new owner-scoped history endpoint reads existing `cw_automation_occurrences` and `cw_agent_runs` records. It creates no new store.

Each history row exposes:
- occurrence ID;
- schedule/event/meeting trigger classification;
- due time;
- occurrence state and suppression/block reason;
- linked run ID/state/message when present.

This gives users a bounded explanation of why work ran or was suppressed without exposing private provider content.

## Security

- history first resolves the automation through owner scope;
- occurrence rows are additionally filtered by owner;
- no credentials/provider content are returned;
- stale edit revisions fail closed;
- connector authority cannot silently change through this UI.

## Qualification boundary

Repository tests verify edit revision conflicts and cross-owner history rejection. Browser/user-flow staging still must verify usability, reconciliation after edits, pause/resume/cancel, quiet-hours changes and recent-activity rendering.

# PA-10 Bounded Connected-Event Automations

## Scope

This slice extends the existing PA-02 automation ledger so one already-authenticated
PA-06 connector event may wake one finite Agent run when the user explicitly binds
an active connector-read grant to an active persistent goal.

It does **not** add a second scheduler, provider-write authority, automatic sending,
calendar mutation, purchasing, booking, payment, publishing, or approval bypass.

## Authority model

The durable binding is:

```text
owner
+ automation id/revision
+ persistent goal id/revision
+ connector read grant id
+ provider event id
= one event occurrence
```

At admission the server revalidates:

- the global automation gate;
- the automation is still active and at the expected revision;
- the goal still exists, is active and has the exact bound revision;
- the connector read grant still belongs to the same owner;
- the grant is active, unexpired, for `agent_context` and `planner_context`;
- the persisted connector event belongs to the same owner and bound grant;
- overlap policy and the persistent-goal bounded-run budget.

Provider event content remains untrusted context. It cannot grant tools, widen scopes,
change destinations, or authorize consequential work.

## Event processing and dedupe

The existing PA-06 connector path remains authoritative for provider event
authentication, persistence, duplicate rejection, ordering checks, cursor recovery and
source synchronization.

After synchronization, event-automation admission runs as a durable consumer before
the connector event is marked processed. If admission fails transiently, the connector
event remains retryable. Retry attempts are not discarded merely because the connector
cursor already advanced during the first successful sync.

Occurrence identity is SHA-256 over owner, automation id, automation revision and the
persisted provider-event id. Agent creation uses a second deterministic idempotency key.
Replays therefore return the same occurrence/run instead of starting duplicate work.

## Recovery

Migration 0039 adds nullable `trigger_event_id` to
`cw_automation_occurrences`. An event occurrence persists this source identity before
Agent-run creation. If a worker/process dies after occurrence admission but before the
run is linked, the existing buffered/accepting recovery loop can reclaim the occurrence
and retry admission with the same event id.

## Scheduling boundary

Connected-event automations reuse `cw_automations` but do not create Temporal
Schedules. The schedule reconciler deletes any obsolete Temporal Schedule if a
time-based automation is revised into an event trigger. Temporal remains the only
due-time authority for daily/weekly automations; the authenticated connector-event
ledger is the event authority for event triggers.

## Notifications

An accepted event occurrence reuses the existing first-class
`NotificationRepository` and creates the same consent-controlled
`automation_started` class of notice. Quiet-hour calculation, outbox delivery,
Browser Push mirroring and latest-consent checks stay in the shared notification path.

## Rollback and qualification

No new production flag is introduced. The capability remains behind:

- `SHUDDHO_AUTOMATIONS_ENABLED=false`;
- `SHUDDHO_CONNECTOR_READS_ENABLED=false`;
- `SHUDDHO_AGENT_RUNTIME_V3_ENABLED=false`.

Repository implementation does not qualify live providers or production. Controlled
staging must prove authenticated event intake, exact owner/grant/goal binding, duplicate
and out-of-order delivery, process loss, cursor advancement followed by consumer retry,
revocation, quiet hours, notification delivery and rollback before activation.

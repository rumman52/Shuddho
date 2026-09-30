# PA-10 bounded Goal-Driven Proactivity

**Status: repository implementation slice stacked after Deadline Coworker; default-off behind existing automation, Runtime v3, planner, context and Work Service gates.**

## Outcome

A user can attach a reviewed finite proactive profile to an active persistent goal. Each authorized wake-up starts one bounded Runtime v3 run, refreshes only reviewed context, exposes only the user-selected safe Work Service allowlist, produces a private result or no useful action, and stops.

This is not a continuously running LLM and it does not create a second agent runtime.

## Reviewed authority

The automation persists a reviewed `tool_allowlist` of one to four tools chosen from:

- `report.create`
- `document.create`
- `career.create`
- `social.draft`
- `daily_plan.create`
- `personal_plan.create`
- `email.draft`
- `meeting.prepare`

The schema excludes consequential tools, arbitrary tool names, research, sandbox execution, browser mutation, email send, calendar writes, publishing and transactions. Runtime v3 revalidates every selected tool again before admitting a run.

Migration 0043 adds `cw_automations.tool_allowlist`. The allowlist is included in automation revisions and therefore changes only through the existing reviewed automation update boundary.

## Trigger model

The backend supports reviewed daily/weekly schedules and authenticated connector-event triggers.

Scheduled wake-ups:
- revalidate automation + goal revision/state;
- revalidate optional explicitly selected connector read grants;
- include still-owned goal documents;
- create one Runtime v3 run with the exact persisted tool scope.

Connected-event wake-ups:
- reuse PA-06 authenticated event intake and event dedupe;
- revalidate the trigger grant/subscription;
- freeze only the exact active snapshots changed by that provider event;
- do not allow extra connector grants on the event profile;
- create one Runtime v3 run with the exact persisted tool scope.

The current UI exposes the reviewed scheduled profile. Event-triggered profile support is present in the backend contract for controlled use and later UX extension without creating a second execution path.

## Finite execution

Runtime v3 already owns:
- planner-call limits;
- step limits;
- token/cost budgets;
- run deadline;
- retry bounds;
- verified tool receipts;
- typed decisions such as next step, wait, needs input, blocked, approval wait and complete.

This slice does not duplicate those mechanisms. It narrows authority at automation admission and hands the finite run to Runtime v3.

## No authority expansion

External/provider content is data, never permission. The planner cannot add tools to the persisted allowlist. This profile creates no ExternalAction IDs. Any future consequential action must still enter its separate immutable-preview and explicit-approval flow.

## Dedupe and recovery

Scheduled wake-ups reuse the existing stable occurrence identity. Connected-event wake-ups reuse stable provider-event occurrence identity plus exact synchronized snapshot evidence. Existing accepting/buffered recovery, worker restart behavior, notification outbox and quiet hours are reused.

## Qualification boundary

Repository tests verify reviewed tool scope, rejection of consequential tools, scheduled occurrence dedupe, connected-event exact snapshot scope, no ExternalAction authority and completion-notice dedupe.

Controlled staging still must verify real provider events, worker/API restart, revoked context, timezone/DST, planner no-action behavior, quality, cost and rollback. Production flags remain unchanged and default-safe.

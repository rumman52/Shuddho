# PA-10 Deterministic In-App Suggestions

This slice adds the first bounded relevance layer for PA-10 without adding a new
model call, scheduler, external delivery channel, provider permission, or
autonomous execution path.

## Scope

Suggestions are generated on authenticated read from already-owned persistent
goal metadata. The server considers only:

- active goal revision and state;
- `next_review_at` and `deadline_at`;
- whether an active automation already exists for the goal;
- whether explicitly authorized document or memory-namespace references still
  resolve to owner-scoped resources;
- whether the exact goal revision already has a linked Agent run.

No document text, memory value, mailbox/calendar body, browser content, or model
output is returned in the suggestion payload. Authorized context contributes
only a bounded resource count.

The current deterministic kinds are:

- `goal_review_due`;
- `goal_deadline_due`;
- `goal_schedule_due`;
- `goal_context_ready`.

At most one highest-relevance suggestion is returned per goal and at most five
suggestions are returned per request.

## User control and deduplication

Personal suggestions are **off by default** for every account. The user must
explicitly enable the in-app preview.

Suggestion identifiers are stable SHA-256 digests bound to owner, goal ID, exact
goal revision, suggestion kind, and due-time marker. Dismissing a suggestion
stores only its digest in the existing account preference document. A new goal
revision creates a new suggestion identity so an old dismissal cannot silently
suppress materially changed goal state.

The API surface is:

```text
GET /api/v1/personal-suggestion-preferences
PUT /api/v1/personal-suggestion-preferences
GET /api/v1/personal-suggestions
POST /api/v1/personal-suggestions/{suggestion_id}/dismiss
```

## Authority boundary

A suggestion is inert. Reading, enabling, or dismissing suggestions cannot:

- create an Agent run;
- create or modify a Temporal automation;
- prepare or approve an ExternalAction;
- contact a provider;
- send email, calendar changes, push messages, or other external communication;
- expand the permissions of a goal or an authorized resource.

The UI offers only review navigation. A schedule suggestion can open the
existing Automations workspace, where the user must separately create a bounded
automation.

## Release boundary

This slice reuses the already controlled persistent-goals capability and the
existing account preference store. It adds no independent production feature
flag and no database migration. Repository implementation and CI do not prove
controlled-staging or production qualification.

Broader PA-10 work remains separate, including event-triggered suggestion
generation, model-assisted relevance, digest grouping, browser/mobile push,
email or collaboration delivery, and channel-specific qualification.

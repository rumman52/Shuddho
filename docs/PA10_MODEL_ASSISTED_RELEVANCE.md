# PA-10 Bounded Model-Assisted Suggestion Relevance

## User outcome and scope

A user who has already enabled deterministic personal suggestions may explicitly ask Shuddho to reorder the currently visible bounded suggestion set for review. The model can change presentation order only. It cannot add, remove, rewrite, suppress, deliver or execute a suggestion.

The deterministic PA-10 candidate generator remains authoritative. Background notification reconciliation and source validation continue to use deterministic candidates and deterministic ordering. Model ranking is never called by notification delivery, connector event intake, Temporal schedules or Agent execution.

## Authority and release boundary

Model ranking is default-off behind `SHUDDHO_SUGGESTION_MODEL_RELEVANCE_ENABLED=false`. Availability also requires persistent goals, the existing intelligent-model boundary and a configured backend DeepSeek key.

The API is an explicit user action: `POST /api/v1/personal-suggestions/rank`. Deterministic preview must already be enabled. The model receives only the exact current candidate set plus bounded review metadata: candidate ID, kind, deterministic score, due time, review action, context-resource count, goal revision, goal objective and deterministic reason.

No provider message/calendar body, credential, connection identity, memory content, document content, arbitrary tool schema, approval state or ExternalAction is supplied.

## Exact-set invariant

The model response contains only an ordered list of suggestion IDs. The server requires:

- every returned ID to be a unique lowercase SHA-256 suggestion digest;
- the returned count to equal the current deterministic candidate count;
- the returned ID set to equal the deterministic candidate ID set exactly.

Any missing, duplicated or invented ID fails the ranking request. The deterministic list remains available and unchanged. Model output never mutates a goal, preference, notification, automation, run or action.

## Budget, provider failure and evidence

Ranking shares the existing workspace daily model budget and global/provider concurrency and token-reservation governor. The call is bounded to at most 2,000 reserved tokens and a small structured response. Known provider usage settles the reservation; unknown outcomes retain the conservative charge through the existing provider-capacity behavior.

Timeouts, network/provider failures, oversized responses, invalid JSON and changed candidate sets return explicit errors. They do not alter deterministic suggestions or notification delivery. Successful responses expose configured model identity, prompt SHA-256 and latency for review; repository CI is not live-provider qualification.

## UI and compatibility

The Goals workspace keeps deterministic suggestions as the default display. When the release gate is available and at least two candidates exist, the user may select **Rank these suggestions with AI**. The UI states that only current review order changes and that no work or delivery authority is added.

Existing suggestion preview, dismissal, in-app delivery, event-triggered connected-context notices and digest grouping remain compatible. No migration or second scheduler is introduced.

## Acceptance and qualification

Repository tests must prove the feature is default-off, requires its dependencies, sends only the bounded candidate fields, preserves the exact candidate set, rejects invented IDs, consumes the shared provider budget and creates no Agent run. Existing deterministic retrieval after both success and failure must remain unchanged.

Controlled staging must separately prove exact-set ranking against the reviewed live DeepSeek configuration, provider-budget accounting, timeout/provider fallback, owner isolation and zero background-model invocation. Production activation remains blocked until the registered staging and rollback evidence is reviewed. External push/email/collaboration channels and autonomous relevance-triggered execution remain separate PA-10 work.

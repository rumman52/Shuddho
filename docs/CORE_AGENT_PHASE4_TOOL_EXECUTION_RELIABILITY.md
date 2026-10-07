# CORE-04 — Tool Execution Reliability

CORE-04 normalizes every registered Agent tool behind one code-owned execution
contract while preserving the existing consequential-action approval boundary.

## Tool contract

Every entry returned by `GET /api/v1/agent-tools` now exposes:

- name and version;
- capability;
- input and output JSON schemas;
- required permissions;
- read/write classification;
- risk class;
- timeout;
- bounded retry policy;
- idempotency policy;
- approval requirement;
- result-size limit;
- circuit-breaker policy.

The server remains authoritative. Planner output cannot change any of these
fields.

## Standard failures

The shared execution layer normalizes core failures to:

- `provider_unavailable`;
- `provider_rate_limited`;
- `permission_denied`;
- `invalid_tool_input`;
- `tool_timeout`;
- `outcome_unknown`;
- `tool_not_supported`;
- `approval_required`.

Cancellation remains the separate run-control condition `agent_cancelled`.

Provider exceptions and malformed outputs are never returned directly to the
planner or client.

## Retries and idempotency

Non-consequential durable task tools may receive at most two execution attempts.
Each attempt reuses the existing `agent:{run_id}:{ordinal}` server idempotency
scope, so a retry resumes the same durable task rather than creating a second
logical operation.

Public-read research uses the same bounded retry ceiling.

Sandbox execution is server-idempotent but does not receive a blind retry.

Consequential tools never enter the generic retry executor. Email/calendar
mutations remain on the immutable ExternalAction approval and reconciliation
state machine. An uncertain mutation remains `outcome_unknown`; it is never
blindly sent again.

Temporal activity retries remain transport/crash recovery. They re-enter the
same durable invocation and resource identity and therefore do not expand
provider mutation authority.

## Timeouts, result limits and circuit breakers

Every generic tool execution is bounded by its registered timeout using the
shared executor. Returned data is validated against the registered output schema
and JSON-size limit before it becomes a verified tool observation.

Repeated provider-unavailable, rate-limit or timeout failures open a bounded
process-local circuit for that tool. A successful call closes/resets the circuit.

The circuit is deliberately not persisted as transaction authority. Durable
checkpoint/recovery remains the source of truth after worker restart.

## Cancellation

The executor checks the run cancellation state before a call and after a call.
Durable task phases also check cancellation between phases. Native asyncio
cancellation is propagated rather than rewritten.

Sandbox and consequential-action cleanup continue through their existing
durable cancellation/reconciliation paths.

## Transactions

CORE-04 does not grant new transaction authority. The existing transaction
activation gates remain authoritative:

- exact provider/action operation allowlist;
- immutable terms and approval;
- provider-specific idempotency/reconciliation;
- controlled staging evidence;
- capability activation and kill switches.

Shopping checkout and travel booking remain provider-dependent and cannot be
activated without a real qualified provider. Restaurant reservation remains the
currently concrete provider-backed transaction slice.

## Qualification

The CORE-04 regression suite proves:

- complete public tool metadata;
- input/output schema enforcement;
- bounded timeout/retry behavior;
- circuit opening;
- result-size enforcement;
- malformed provider response handling;
- rate-limit and connector-unavailable normalization;
- cancellation propagation;
- no generic execution of approval-required tools;
- required structured error vocabulary.

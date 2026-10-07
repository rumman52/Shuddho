# CORE-06 — Context + Memory Finalization

CORE-06 finalizes controlled context quality for the Core Agent. The goal is
not to remember everything. The goal is to provide the smallest relevant,
fresh, attributable context that preserves the user's newest instruction.

## Context hierarchy

The server owns this precedence order:

1. current user message;
2. current task/run context;
3. workspace/document context;
4. relevant prior task context;
5. durable preferences/memory;
6. external connector context.

The current run goal is passed separately to the planner/model and is always
authoritative over lower-priority remembered preferences.

## Relevance and recency

Retrieved context receives deterministic lexical relevance scores. Prior task
context is included only when it has a lexical relationship to the current
request. Within prior-task candidates, score and recency determine order.

Durable memory is ranked by relevance and recency. External connector snapshots
carry relevance/freshness metadata and are bounded by a configurable freshness
window.

No extra model/network call is used for context ranking.

## Freshness and expiry

Memory facts with explicit expiry continue to be excluded after expiry.

CORE-06 additionally suppresses non-expiring memory that has not been updated
within the configured maximum memory-context age.

Prior completed task context and connector snapshots have independent maximum
age settings. Stale sources are not passed to the model.

## Contradiction handling

A newer explicit current instruction overrides conflicting durable memory for
that run.

The deterministic contradiction detector currently covers bounded preference
axes including:

- formal vs casual tone;
- concise vs detailed output;
- direct vs gentle phrasing;
- explicit negation of remembered terms.

Example:

- memory: "Usually write formally."
- current request: "For this message make it casual."

The formal memory is suppressed for that run. The memory record is not deleted
or rewritten.

## Duplicate removal

Context excerpts are normalized and fingerprinted. Duplicate retrieved content
is included only once across workspace documents, prior tasks, memory and
external connector context.

Duplicates are recorded as invalidated context with reason `duplicate`.

## Context size budgeting

The retrieved context pipeline uses one shared UTF-8 byte budget for:

- workspace/document excerpts;
- relevant prior task context;
- durable memory;
- external connector context.

Higher-precedence context consumes the budget first. Per-item and item-count
limits remain enforced.

The current user message/current run goal is not silently truncated into the
retrieval budget; it remains the direct authoritative instruction.

## Sensitive-data filtering

Retrieved/persisted context is filtered before model exposure for high-risk
secret material, including:

- private keys;
- bearer/JWT tokens;
- common secret/API-key/password assignments;
- AWS access-key patterns;
- payment-card candidates that pass a Luhn check.

This filtering applies to retrieved documents, prior task content, durable
memory and connector context. It does not rewrite source storage.

## Source attribution

Planner context now carries:

- source ID;
- source type;
- precedence;
- relevance score;
- freshness metadata;
- content hash;
- trusted provenance references.

Document provenance remains compatible with the existing memory-proposal source
revalidation contract.

## Prior task context

Only completed/needs-input tasks from the same owner/workspace are eligible.
Tasks belonging to the current Agent run are excluded. Prior task carryover is
read-only context and grants no tool, provider, approval or transaction
authority.

## Connector context

Only already-authorized connector read grants and snapshots bound to the run are
eligible. Revoked/inactive/missing snapshots remain invalidated. CORE-06 adds
freshness suppression and the same redaction/deduplication controls used for
other retrieved context.

## Transactions and approvals

CORE-06 does not broaden transaction or provider authority. Context, memory,
prior tasks and connector snapshots never grant permission.

All consequential work continues through the existing approval boundary:

Agent -> Prepared Action -> Immutable Preview -> Human Approval -> Execution
Gateway -> Provider

Transaction qualification, exact reviewed terms, kill switches, idempotency,
reconciliation and provider qualification remain unchanged.

## Regression coverage

CORE-06 tests verify:

- current casual instruction overrides remembered formal preference;
- stale durable memory is suppressed while remaining user-visible;
- sensitive memory values are redacted before model context;
- duplicate documents are included once;
- context hierarchy and shared byte budget are reported;
- relevant prior completed task context is available;
- planner context exposes precedence, source type, freshness and authority
  metadata.

Production completion still requires all repository CI and controlled staging
qualification gates to pass.

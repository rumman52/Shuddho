# Structured Agent Memory

This increment adds explicit, user-controlled structured memory for the Shuddho Agent Runtime. It is disabled by default.

## Goals

Memory is intentionally narrow and inspectable. It stores small facts such as writing preferences, profile facts, project facts, organization context, and reusable writing conventions.

It does not copy raw chats, documents, search results, action previews, credentials, or arbitrary model output into long-term memory.

## Data model

Each fact has:

- owner and workspace scope;
- namespace and stable key;
- UTF-8 value and language;
- monotonically increasing version;
- provenance type/ref;
- optional expiry;
- created/updated timestamps.

The initial API accepts only provenance type `user`. Model-created memory is deferred.

Namespaces:

- `profile`
- `preferences`
- `project`
- `organization`
- `writing`

A user may store at most the configured account limit. The default is 200 facts.

## User controls

Authenticated endpoints:

- `GET /api/v1/memory`
- `POST /api/v1/memory`
- `PUT /api/v1/memory/{id}`
- `DELETE /api/v1/memory/{id}`

Create/update require `SHUDDHO_AGENT_MEMORY_ENABLED=true`.

List and hard-delete remain available even if memory use is later disabled so existing facts can still be inspected and removed.

Delete removes the memory row. Audit records retain only the resource ID and action name, never the memory value.

## Runtime use

Memory is consumed only by agent-owned child tasks.

```text
Agent run
   |
   +-- child task stores agent_run_id only
   |
   +-- draft phase
         |
         +-- live bounded memory lookup
         |
         +-- ephemeral model prompt
         |
         +-- draft checkpoint stores only fact IDs + versions
```

Standalone Coworker tasks do not receive agent memory.

Memory is not injected into:

- web search queries;
- document extraction;
- Temporal workflow arguments/history;
- Gmail/Calendar action previews;
- action approvals;
- task notes;
- agent goal/tool arguments.

The model system prompt explicitly treats memory as user-controlled context, not independent evidence and not permission for an external action.

## Bounds

Defaults:

```text
SHUDDHO_AGENT_MEMORY_FACTS=200
SHUDDHO_AGENT_MEMORY_CONTEXT_FACTS=20
SHUDDHO_AGENT_MEMORY_CONTEXT_BYTES=8192
```

Context is selected by most recently updated active facts and stops at both the fact-count and UTF-8 byte limits.

Expired facts are excluded from list/context use.

## Provenance

Tool receipts contain only:

```json
{"memory":[{"id":"...","version":2}]}
```

They do not copy fact values. This gives execution provenance without defeating hard deletion.

## Deferred

Not part of this increment:

- automatic model-written memories;
- semantic/vector retrieval;
- embeddings;
- raw conversation memory;
- connector-derived memory;
- organization-shared memory;
- memory conflict resolution;
- inferred sensitive attributes;
- autonomous memory promotion.

## Release gate

Keep:

```text
SHUDDHO_AGENT_MEMORY_ENABLED=false
```

until:

1. migration `0006` is applied;
2. API and workers run the same release;
3. ownership/deletion tests pass on PostgreSQL;
4. agent drafting tests verify memory values stay out of durable receipts/history;
5. retention/privacy review approves the namespaces and deletion behavior;
6. staging verifies update/delete while active agent runs exist.

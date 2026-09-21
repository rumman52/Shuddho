# Agent Runtime foundation

This increment adds the durable, owner-scoped substrate for Shuddho's future goal-driven coworker. It is deliberately disabled by default and does **not** introduce an unrestricted autonomous loop.

## Scope

The foundation adds:

- durable agent runs with one user goal, owned source versions, language, state and deadline;
- durable agent steps, typed tool invocations, tool receipts and resumable progress events;
- a server-owned typed tool registry over existing Shuddho capabilities;
- bounded plan validation: 1 to 8 steps, registered tools only, JSON-bounded arguments;
- source scoping: a tool may reference only files attached to that agent run;
- owner isolation and idempotent run creation;
- cancellation and resumable event retrieval;
- explicit consequential-tool metadata that preserves the Part 3 approval boundary.

This increment does **not** add a model planner, automatic execution, replanning, memory, arbitrary shell/browser access, or silent external actions.

## Feature flag

Keep:

```text
SHUDDHO_AGENT_RUNTIME_ENABLED=false
```

until migration `0003`, all API instances, future agent workers and staging verification are coordinated.

## Durable ledger

```text
cw_agent_runs
  |
  +-- cw_agent_steps
        |
        +-- cw_tool_invocations
              |
              +-- cw_tool_receipts

cw_agent_runs
  |
  +-- cw_agent_events
```

Agent histories contain IDs, tool names, states and bounded metadata. The planner/executor added later must use these records rather than keeping an agent loop only in process memory.

## Typed registry

Current registered tools wrap capabilities that already exist in Shuddho:

| Tool | Existing capability | Consequential |
| --- | --- | --- |
| `report.create` | report + email draft workflow | no |
| `document.create` | official document workflow | no |
| `career.create` | career/CV workflow | no |
| `social.draft` | social draft workflow | no |
| `email.draft` | email draft workflow | no |
| `meeting.prepare` | meeting workflow | no |
| `daily_plan.create` | daily planning workflow | no |
| `personal_plan.create` | personal planning workflow | no |
| `presentation.create` | editable PPTX workflow | no |
| `spreadsheet.create` | editable XLSX workflow | no |
| `research.search` | cited web research workflow | no |
| `email.send` | approved Gmail action | **yes** |
| `calendar.create` | approved Google Calendar action | **yes** |

Tool availability follows the existing service flags. A disabled capability is not available to an agent plan.

The two consequential tools require approval. In this foundation they can only reference an owner-scoped existing action record of the matching kind. The runtime does not create a new permission path around the immutable preview/hash/receipt design from the approved-actions increment.

## API

All routes require the authenticated owner boundary.

| Route | Purpose |
| --- | --- |
| `GET /api/v1/agent-tools` | Feature availability and currently enabled server-owned tools |
| `POST /api/v1/agent-runs` | Create an owned run with an idempotency key |
| `GET /api/v1/agent-runs` | Recent owned runs |
| `GET /api/v1/agent-runs/{id}` | Run, steps and tool ledger |
| `GET /api/v1/agent-runs/{id}/events` | Resumable progress events; SSE is supported |
| `POST /api/v1/agent-runs/{id}/cancel` | Cancel a non-terminal run |

The internal `AgentRepository.save_plan` contract is intentionally not a public API. The next planner implementation must validate its proposed steps through this server-owned boundary before anything can execute.

## Safety invariants

1. Model or document text cannot register a new tool.
2. Plans contain at most eight steps.
3. Tool arguments are validated by code-owned Pydantic schemas and capped at 32 KiB.
4. File IDs must be a subset of the source files attached when the run was created.
5. Consequential tools remain marked `approval_required=true`.
6. Email/calendar action IDs must belong to the same Shuddho owner and match the registered capability.
7. No arbitrary URL, shell command or browser action is a registered tool.
8. Run idempotency is serialized per account before quota decisions.

## Next increment

The next runtime increment adds the first deterministic planner and Temporal `AgentWorkflow`:

```text
goal
 -> bounded planner
 -> save validated plan
 -> execute one registered tool at a time
 -> persist receipt/checkpoint
 -> evaluate
 -> complete
```

Start with non-consequential tools. Approval-aware execution of Gmail/Calendar remains a later increment and must pause at the existing exact approval boundary.

# Agent Workspace Proposal Review

This increment exposes Shuddho's existing bounded Agent Runtime in the authenticated Coworker UI without expanding Agent authority.

## User flow

```text
user goal
→ bounded Agent run
→ registered-tool plan
→ inert typed action proposal
→ user reviews exact proposal payload + rationale
→ user chooses an owned connected account
→ exact proposal hash is promoted
→ immutable ExternalAction preview
→ existing Email & Calendar review surface
→ separate explicit approval
→ durable provider execution
```

The Agent screen does **not** contain an approval or execution control.

## Agent workspace

The new Agent tab can:

- create a bounded Agent run with a goal, up to five already-owned source documents and an output language;
- restore recent runs from the server;
- show run state, planner mode, bounded planner usage and server-owned steps;
- show inert email/calendar proposals returned by the backend;
- show the exact proposal hash prefix, rationale and typed payload;
- allow dismissal of the exact proposal hash;
- allow promotion only after the user explicitly chooses a matching owned connection;
- hand a promoted preview to the existing ActionWorkspace for final review.

The browser never constructs a provider mutation from model output.

## Human-control boundary

Provider/account identity is not part of the model proposal.

The proposal contains typed content only. Promotion requires the user to choose one of their currently connected accounts. The backend then re-validates the exact proposal hash and calls the existing `ActionRepository.prepare` path.

Promotion therefore still inherits:

- owner-scoped connection lookup;
- provider/capability validation;
- connector kill switches;
- immutable preview hashing;
- server-owned approval scope;
- quotas and expiry;
- existing explicit approval.

After promotion, the UI moves to the existing Email & Calendar action review. The user must independently check the immutable preview and opt in before the normal approval endpoint can queue execution.

## Browser proof

The Coworker browser fixture runs the real Agent Temporal workflow with an explicitly simulated planner.

The browser test proves:

1. a bounded Agent run produces an inert proposal;
2. provider mutation counters remain unchanged while the proposal is visible;
3. the user explicitly selects a connected account;
4. promotion creates an `awaiting_approval` immutable action preview;
5. the final approval button remains disabled until the existing review checkbox is checked;
6. provider mutation counters remain unchanged after promotion;
7. cancelling the promoted preview still results in zero additional provider mutations.

The browser fixture uses simulated identity, planner output and provider transport only. No real email or calendar mutation occurs in CI.

## Safety boundary

This increment does not:

- let the planner select a connection or provider identity;
- let the Agent approve an action;
- add auto-approval;
- execute a proposal directly;
- insert a promoted proposal into the saved Agent plan;
- bypass the consequential-action registry;
- add arbitrary HTTP, browser, shell or connector tools.

Broader model-created executable actions remain outside this increment.

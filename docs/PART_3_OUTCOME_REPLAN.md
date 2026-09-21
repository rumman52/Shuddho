# Bounded Incomplete-Result Replanning

This increment lets the Agent Runtime adapt when a completed non-consequential task returns the existing structured `needs_input` state and there are still unstarted steps.

It remains disabled by default.

## Trigger

The server may request one replan only when all of these are true:

- intelligent planning is enabled;
- `SHUDDHO_AGENT_OUTCOME_REPLAN_ENABLED=true`;
- the completed task is non-consequential;
- the task finished as `needs_input`;
- at least one later step is still unstarted;
- the run has not already consumed its one automatic replan.

The completed step is immutable. Replacement begins at the next ordinal.

## What this is not

This is not a model-based quality judge. Shuddho does not ask a second model to score prose, style, truthfulness, or usefulness. The trigger is the existing typed task state produced by validated draft contracts.

It does not replan for:

- provider/model outages;
- arbitrary tool failures;
- user cancellation;
- approval rejection or expiry;
- uncertain external-action outcomes;
- subjective quality scores;
- a `needs_input` result on the final step.

## Planner privacy

The planner receives the same bounded inputs as PR #114:

- the original agent goal;
- currently enabled non-consequential tool names;
- a safe reason string: `result_incomplete`.

It does not receive the generated draft, missing-information text, handoff content, memory values, search evidence, provider receipts, or external-action previews.

Temporal history contains only run IDs, ordinals, counts, safe status values, and the safe reason string.

## Replan contract

The existing replacement contract remains authoritative:

1. completed steps before the replacement boundary must stay completed;
2. only `prepared` invocations may be replaced;
3. the complete run stays bounded to eight steps;
4. executable arguments are reconstructed by Shuddho;
5. consequential actions remain server-appended and approval-bound;
6. planner-call and token budgets remain unchanged;
7. one workflow may automatically replan at most once.

If a prior capability-change replan has already happened, a later `needs_input` result is preserved and execution continues without a second replan.

## Release gate

Keep:

```text
SHUDDHO_AGENT_OUTCOME_REPLAN_ENABLED=false
```

until staging verifies:

1. incomplete-result replans never delete or rewrite completed steps;
2. the planner never receives draft or missing-information content;
3. Temporal history contains no private generated content;
4. one-replan limits hold across capability and outcome triggers;
5. final-step `needs_input` completes without an unnecessary planner call;
6. restart/replay tests remain green.

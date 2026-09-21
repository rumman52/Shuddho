# Bounded Dependency Graph

This increment gives the Agent Runtime durable, server-owned dependency metadata without allowing the model to invent step IDs or arbitrary graph edges.

## Contract

When `SHUDDHO_AGENT_DEPENDENCY_GRAPH_ENABLED=true`:

- dependencies are derived only by trusted server code after planner output is validated;
- dependency references are ordinals in the same owner/run;
- edges point backward only, making cycles impossible by construction;
- a non-research, non-consequential task may depend on the nearest prior eligible task;
- research remains an independent source-producing step;
- approved/consequential actions retain their existing explicit approval binding and gain no implicit dependency;
- a step cannot execute until every persisted dependency is completed;
- replanning replaces only unstarted steps and recomputes dependencies for that suffix;
- the existing eight-step run ceiling remains unchanged.

The feature is disabled by default. With the flag off, plans expose empty dependency lists and the existing runtime behavior is preserved.

## Why server-owned first

The planner still selects bounded tool objectives, not durable graph identifiers. This prevents prompt/model output from becoming an authorization or scheduling primitive. It also gives us a stable persisted graph contract before introducing parallel fan-out/fan-in scheduling.

## Privacy and safety

Dependency metadata contains only same-run ordinals. It does not persist handoff text, memory values, document contents, research results or action payloads. Existing owner scoping, tool validation, action approval and handoff isolation continue to apply.

## Release gate

Keep the flag disabled outside controlled staging until we verify migration/rollback, restart/replay behavior, out-of-order blocking, replan suffix rebuilding, approval isolation, and backward compatibility.

## Deferred

This increment intentionally does not add model-selected edges, arbitrary DAGs, parallel Temporal branches, cross-run dependencies, multi-agent delegation or autonomous external actions.

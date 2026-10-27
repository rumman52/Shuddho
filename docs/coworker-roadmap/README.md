## Current release-blocker checkpoint — 27 October 2026 (Asia/Dhaka)

The **single canonical release-readiness handoff** is maintained at the top of [PROGRESS.md](PROGRESS.md), under “Current release-readiness handoff — 27 October 2026”. It records the exact main SHA and CI state, PR #582 verification, V-01 governance blocker, current Render production/staging identities, database expiry, and the dependency-ordered owner actions.

Treat the historical planning baselines below as history, not current deployment or qualification evidence. Do not repeat already-merged source fixes merely because an older checkpoint labels them pending.


---

# Shuddho coworker roadmap and coding kit

Reviewed on 12 October 2026 (Asia/Dhaka). Baseline: main `ed1467d3e9ce230d1a8d9b24fdfa5594ebc0df40`.

Start with [ROADMAP.md](ROADMAP.md), then [CHATBOT_WORKFLOW.md](CHATBOT_WORKFLOW.md).
For the requested three-stage execution, use [THREE_STEP_EXECUTION.md](THREE_STEP_EXECUTION.md)
and refresh [PROGRESS.md](PROGRESS.md) before starting the next task.
The versioned architecture/core acceptance tracker is [ARCHITECTURE_CORE_ACCEPTANCE_INVENTORY_V1.md](ARCHITECTURE_CORE_ACCEPTANCE_INVENTORY_V1.md).
The target contract is [SPEC.md](SPEC.md); the implementation queue is
[2026-10-12-coworker-evolution.md](../superpowers/plans/2026-10-12-coworker-evolution.md).
Copy [TASK_TEMPLATE.md](TASK_TEMPLATE.md) for each PR and update [PROGRESS.md](PROGRESS.md) at handoff.

A reusable coding skill lives in `.agents/skills/shuddho-engineering`.
It helps a coding assistant build Shuddho; it is not a new tool installed into Shuddho's production agent.

This kit adds planning and coding guidance only. It does not complete the roadmap,
activate capabilities, install production infrastructure, or supply provider credentials.
Personal ChatGPT Skills-page installation was unavailable in the authoring environment.
Use the repository skill in a compatible coding environment or paste the bootstrap prompt.

The attached research report supplied the initial framing. Current repository source and
fresh primary documentation govern factual claims; historical checkpoints must be refreshed.


## Current source-revalidation checkpoint — 18 October 2026 (Asia/Dhaka)

- Refreshed main: `9e52756e4de52d95cc69879ce7cdbb3a390c0ac7`; #461 is merged, not open. No open PRs existed at task selection. Main CI [#39147097140](https://github.com/rumman52/Shuddho/actions/runs/39147097140) was still running when this checkpoint was written; its `test-and-build` job passed. The earlier #461 code/test head passed all three required jobs in #39141823326. No formal independent review submission was recorded for #461.
- Work branch: `codex/c01-late-planner-source-revalidation-20261018`. [Task contract](C01_LATE_PLANNER_SOURCE_REVALIDATION_2026-10-18.md). Fresh Runtime v3 decisions now revalidate the original conversation's selected source pins after inference, before saving model output/checkpoints. Already-committed decisions retain idempotent replay; direct/legacy run semantics remain unchanged.
- Reproduction: six source-invalidated cases failed before the guard; unchanged-source control passed. Focused conversation/context/cancellation regressions: **41 passed, 92 deselected**, zero skips. The mandatory JUnit gate passed. Full local pytest and exact-head required CI remain pending at publication; consult this branch's PR checks for the final revision. These numbers are a focused selection, not a repository-wide total.

| Part | Evidence-supported status | Remaining gates |
| --- | --- | --- |
| Architecture A-01..04 | Existing state/trust foundations and repository recovery contracts; this slice adds no store, orchestrator or schema | Mixed-version operated recovery/rollback, staging boundary review |
| Core C-01..06 | #461 grounded adapter handoff is merged; late selected-source response guard locally verified in this branch | Final-head CI/review; real browser/sandbox isolation; CW-11 staged drain; live provider/model qualification |
| Context/experience P-01..03 | Existing owned conversations and explicit selected context; delayed invalidation regression added | Four operated study/work/separation/recovery scenarios and UI reconnect evidence |
| Verification V-01..04 | Focused regression evidence only for this branch | Full mandatory final-head CI, protected staging, human security/quality review and separately authorized production rollout |

Separate read-only agent review found no Critical/Important issues; this is not human security certification. Minor observation: the no-memory-proposal assertion is only incidental because the synthetic response proposes no memory. End-to-end Temporal failure-state persistence and PostgreSQL invalidation races remain outside this regression.

The full Architecture/Core Agent workstream remains **INCOMPLETE**. No staging, production qualification or activation is established. The guard observes invalidation committed before its source check; it does not claim serializable source-deletion locking or recall of data already submitted to inference. Historical checkpoints below are retained and superseded by this entry.

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


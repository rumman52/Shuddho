# CW-11 / C-05 — Default-off reviewed research skill worker binding

Date: 16 October 2026 (Asia/Dhaka)  
Baseline: `main` `d4fccefdced8a68e8fb839525141d9796a6f4dac` (merged PR #433).  
Working branch: `codex/cw11-reviewed-research-worker-binding-20261016`.

## Problem and boundary

The code-reviewed `CoworkerSkillManifest` pilot validates `research` and `research.search` but had **no consumer** in the actual Agent→Task→worker phase route. A validator alone does not constrain which pinned skill/version/grant a worker executes. Untrusted instructions or model steps cannot publish authority.

## Bounded behavior

This change adds default-off `SHUDDHO_AGENT_REVIEWED_RESEARCH_SKILL_ENABLED`. It requires the existing Agent runtime and research service flags. It does NOT activate those services. Only **Agent-owned** research Task workflow `work_research_v1` is in this pilot; standalone research work-service tasks retain their existing path.

With the pilot enabled:

1. The already-existing AgentRun, AgentStep and ToolInvocation records must all match the same owner and run. Only an eligible non-cancelled run with `research.search` may proceed.
2. The persisted run tool allowlist must explicitly contain `research.search`, and the actual registered tool must still be enabled and match the invocation's pinned `ToolSpec.version`.
3. Admission and worker reads rebuild and compare the exact Task instruction, notes, selected documents, output language, search query and search time range against the authorized invocation, rejecting replay with changed inputs. The admitted Task's selected `DocumentVersion` IDs must also be a subset of the owning AgentRun's pinned `input_versions`, both when creating the Task and on worker resume; matching a document ID but consuming a new version is not sufficient.
4. The exact source-reviewed pilot manifest and schema/tool policy pins must still validate. The pilot's one-call ceiling is enforced against the SQL ToolInvocation ledger. A `reviewed_skill_identity` Step persists the exact review SHA-256 alongside the accepted Task, so a later code-reviewed manifest change cannot silently upgrade that pending task.
5. The task's existing `workflow_version` and pinned review identity are rechecked before worker phases, including after direct SQL alteration. Revoking/cancelling the run or removing its grant fails closed before the next worker-phase read. The research-credit reservation independently locks the parent AgentRun first, then the Task, and repeats grant/review validation before accepting paid search budget.
6. Idempotent Task replay must match both the existing Task fingerprint and its original `agent_run_id`/`agent_step_id`; an owner-controlled public idempotency key cannot promote a standalone task into an Agent execution. A reviewed replay also reruns current manifest and bound Task checks.
7. The parent AgentRun deadline is checked on every reviewed validation. After a research-credit reservation, the runner rechecks the current task/run before handing the query to the provider; a denied pre-dispatch recheck settles credits as failed with zero actual usage. No new provider connection, token or action ledger is created.

No new Task or run schema was added. The existing task workflow version is the identity used for this pilot. Research skill publication beyond this source-reviewed pilot, immutable deployed publication state, multiple reviewed versions, effective cross-release rollback, model/provider quality, and staging/restart qualifications **remain unimplemented/unverified**. Disabling the new feature flag restores the historical standalone and Agent research behavior; therefore a rollout must not mix worker versions or toggle it for in-flight Agent runs without a qualification plan. The reviewed SHA record is a Task-scoped commitment, not a public publication catalog or a deployment approval.

## Acceptance and review

- New SQL-backed tests in `tests/test_coworker.py`: valid owned binding; wrong owner; altered query; changed workflow/tool version; altered stored review SHA; public/Agent replay key collisions; dropped grant; changed reviewed guidance; expired/cancelled run; paid reservation denial and post-reservation pre-provider revocation with zero provider calls; mismatch with an ordinary planned tool; standalone research compatibility; disabled/dependency flag behavior.
- Focused: `uv run --extra coworker pytest tests/test_coworker.py -k 'reviewed_agent_research' -q`. Full mandatory exact-final-HEAD `test-and-build`, `coworker` and `ci-merge-gate` must pass.
- Independently review admission/worker TOCTOU, source deletion, scope/expiry, tool policy drift, task idempotency, schema-version compatibility and replay. Synthetic SQL tests do not prove running-provider interruption or live PostgreSQL/Temporal race outcomes.
- Existing release gates remain authoritative and default-off. No merge, staging deployment, provider spending or activation is authorized by this task brief.

## Remaining next slices

Add a trusted, separately reviewed skill publication/version registry with explicit rollback and current grant/eligibility at real worker selection, then prove staged mixed-version worker behavior and user-facing reviewed research outcomes. CW-09 operated browser, CW-10 real sandbox isolation, context/purpose separation, four coworker scenarios and A/V release qualification remain separate mandatory items.

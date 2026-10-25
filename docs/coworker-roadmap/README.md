## Current release-blocker checkpoint — 25 October 2026 (Asia/Dhaka)

- **Current main:** da7b7b66903be1ff5d29ec474fe8af2511d83701, merge of PR #562. The connected GitHub API currently reports main as protected=false, required-check enforcement off, and no repository/parent rulesets. Refresh before relying on this snapshot.
- **Latest observed main CI:** [run #40169838677](https://github.com/rumman52/Shuddho/actions/runs/40169838677) on this exact SHA: test-and-build passed, governance-audit failed with “main branch protection is not confirmed”, and coworker was still running at the last check. This revision is **not fully CI-verified**.
- **Do not repeat the operator implementation:** PR #562 already merged scripts/apply_main_ruleset.py, its tests, and the reviewed policy infra/github/main-ruleset.json. The source-level gate is behaving fail-closed; the missing step is actual owner/admin configuration and behavioral proof. The connected GitHub integration can read rulesets but cannot write them.
- **Required V-01 operator action:** in a secure local admin environment, inspect existing repository/organization policy, then apply the reviewed rule only if it does not weaken stricter policy:
  ~~~bash
  python -m scripts.apply_main_ruleset --repository rumman52/Shuddho
  python -m scripts.apply_main_ruleset --repository rumman52/Shuddho --apply --confirm-repository rumman52/Shuddho
  ~~~
  Supply an appropriately scoped GITHUB_TOKEN through the secure local environment, never in chat or PR-controlled CI. Then read back the effective policy and prove pending/red checks, missing/stale approval and unresolved threads block merge, with a reviewed green PR eligible. Configuration read-back alone is not enforcement proof.
- **Production deployment control remains external:** the connected Render service previously reported commit-triggered auto-deploy and a live deploy while this revision's governance check failed and coworker CI was unfinished. A source validator cannot stop a manually configured Render trigger. The owner must prevent commit-only production deployment until a fail-closed release gate is effective, then verify the actual service setting and a blocked-candidate control.
- **Staging is also externally blocked:** infra/render.staging.yaml already declares shuddho-worker-staging with auto-deploy off, but the connected Render workspace did not contain that worker. Issue [#291](https://github.com/rumman52/Shuddho/issues/291) records the remaining worker, Temporal/S3 credentials, synthetic identity and provider/device prerequisites. Sync the existing reviewed Blueprint; do not recreate its code or substitute a web/cron service.
- **Readiness boundary:** operator code merged ≠ native protection applied ≠ staging frozen ≠ production qualified ≠ capability activated. Keep V-01 and the 17 A/C/P/V acceptance rows open until their actual evidence exists.

| Priority | Next action | Completion evidence |
| --- | --- | --- |
| 1 | Owner/admin applies the existing ruleset operator | Effective ruleset read-back plus negative/positive merge-control evidence |
| 2 | Owner/admin removes unsafe commit-only production deployment behavior | Actual Render setting read-back and proof an unqualified candidate cannot deploy |
| 3 | Provision/sync the existing staging worker and complete authorized secrets | Matching API/worker SHA, migrations, Temporal polling, private storage and owner-isolation checks |
| 4 | Freeze one reviewed staging release, then continue core/automation/transaction qualification | Fresh version-bound scenario evidence; no synthetic evidence relabelled as live |


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


# CW-11 — inert versioned reviewed skill manifest pilot

**Date:** 14 October 2026 (Asia/Dhaka)  
**Workstream:** Architecture/core / CW-11 reviewed skills  
**Base:** `main` `3505c5029891d488678b1f2e8b302694ce0a96e4`  
**Branch:** `codex/cw11-inert-reviewed-skill-manifest-20261014`  
**Initial implementation/tests SHA before docs:** `6f11f841c8427620d62b9e897eda96fe80fda57c`

## Requirement and current gap

Canonical [CW-11](../superpowers/plans/2026-10-12-coworker-evolution.md) requires versioned skill manifests pinning instruction and I/O schema hashes, code-owned tool names and resource limits, denying unknown tools/provider authority and wider grants, with compatible version rollback. Existing `skills.py` supplies server-owned `WorkSkill` versions and `agent_tools.py` supplies code-owned `ToolSpec` policies, but no reviewed manifest binds the two with rollback/invalidation identity. In CW-10, source itself documents that immutable envelopes are only inert proposals; no dynamic installation or execution grant is authorized.

## Scoped pilot contract

- Add **`services/coworker/skill_manifests.py`**, a pure, no-side-effect `CoworkerSkillManifest`, immutable `SkillResourceLimits`, `pilot_skill_manifest()`, `validate_manifest(manifest, allowed_tools: frozenset[str])`.
- Limit pilot to **existing `research` WorkSkill, version `work_research_v1`, and registered `research.search` ToolSpec**. No new provider, tool or feature flag is introduced. Use SHA-256 for canonical version/instruction/guidance, input schema, output schema **and full code-owned tool policy** (risk, approval requirement, permissions, resource bounds and retry behavior). Changes to a reviewed instruction/tool policy/schema invalidate a persisted old manifest.
- Enforce exact reviewed name/version/rollback version, one known tool, code-owned task type, no consequential or approval-required tool, caller's existing `allowed_tools` subset, immutable positive resource limits within the registered tool timeout/output ceiling. Never use model suggestions to widen that grant.
- The validator is **inert**: it neither registers/distributes skills nor authorizes runtime execution, provider access, approval, code execution or external mutations. Existing `skill_for_version` remains the sole WorkSkill version lookup.

## Negative and positive verification

`tests/test_coworker_skill_manifests.py` exercises normal code-owned version, unknown/duplicate tools, email.send and browser.read escalation, missing grants, unreviewed version/rollback, changed instruction/output/input schema/policy hashes, changed live guidance/tool input policy/permission list, mutable/coercible limits, subclassed manifest and non-Pydantic mutable limits, and exact version rollback lookup. No synthetic receipt counts as staging evidence.

Require focused `uv run --extra coworker pytest tests/test_coworker_skill_manifests.py tests/test_coworker_services.py tests/test_agent_release_gates.py -q`, plus exact-final-head mandatory `test-and-build`, `coworker` with no skipped safety gates and `ci-merge-gate`, and independent security review. A new manifest may only become active after separate reviewed integration and eligibility tests, **not** from a valid data structure alone.

## Compatibility, tradeoff and rollback

No schema migrations, worker or workflow-history changes; no imported plugin system or competing tool registry. Computed source/schema fingerprints are pinned to current code-owned objects and checked on every validation. An alternative dynamic manifest loader is rejected for this pilot because it would expand runtime authority without an operated approval system. Resource limits are intentionally the current ToolSpec's ceiling, not a new runtime allocator; admission budgets remain owned by existing code.

Rollback: remove the inert manifest/test modules; the existing `skills.py` and `agent_tools.py` are unchanged. Existing service/task behavior remains identical.

**Next exact action:** open independent draft PR, require exact-head CI and review, fix any failed checks and persist checkpoint. Later CW-11 tasks: reviewed persisted publication/version rollback, grant-subset enforcement at runtime selection, actual model quality/cost comparison and staging; CW-10 real approved code and CW-09 browser content/staging remain blocked. No automatic merging/deployment/production activation.

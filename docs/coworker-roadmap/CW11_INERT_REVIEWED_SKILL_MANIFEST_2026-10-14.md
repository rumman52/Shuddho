# CW-11 — inert versioned reviewed skill manifest pilot

**Date:** 14 October 2026 (Asia/Dhaka)  
**Workstream:** Architecture/core / CW-11 reviewed skills  
**Base:** `main` `3505c5029891d488678b1f2e8b302694ce0a96e4`  
**Branch:** `codex/cw11-inert-reviewed-skill-manifest-20261014`  
**Initial implementation/tests SHA:** `6f11f841c8427620d62b9e897eda96fe80fda57c`. **Reviewed P2 source/test correction SHA:** `d0264e22cf4c6ae6a606f8f6bafb8e36b7270bc6` before final docs. **Review PR:** [#396](https://github.com/rumman52/Shuddho/pull/396), open and unmerged. **Additional dependency-pin correction:** code/test SHA `045830b2afc2e5645438c00a769929b36ae03953` before checkpoint. Exact-head [CI #38527404758](https://github.com/rumman52/Shuddho/actions/runs/38527404758) passed but independent [P2 review](https://github.com/rumman52/Shuddho/pull/396#discussion_r4267904354) found that Pydantic schema changes under an updated `uv.lock` silently regenerate import-time reviewed JSON schema fingerprints. Added exact review pin of `uv.lock` Git blob `6b19816f0fe2aa1e5e51a9e88bc03b171608cd0f` and installed Pydantic/core/typing-extensions/typing-inspection versions; fail closed on drift. Tests mutate lockfile and generator version and assert denial. Rerun full CI and request review on the new head. Independent first-head review found three P2 defects: dynamic policy re-review, copied identity subclass equality and retry-unaware wall budget. Added separately pinned source Git blob identities for skills/tools/input schemas, a module-import fixed pilot reviewed manifest and live-code mismatch checks, exact identity/field types, and 481-second retry-aware declared wall ceiling. All changes require final-head CI/review.

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

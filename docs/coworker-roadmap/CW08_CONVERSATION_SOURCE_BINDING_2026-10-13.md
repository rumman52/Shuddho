# CW-08 — Exact conversation source pins at worker use

## Task contract

- **Objective:** A conversation-bound Agent run may use only the same owner-selected document version and SHA-256 digest that passed admission. Replacements, deletions, expiry or link inconsistencies reject context before storage bytes/model prompt dispatch.
- **Source requirement:** `docs/coworker-roadmap/SPEC.md` and CW-08 in `docs/superpowers/plans/2026-10-12-coworker-evolution.md`: recheck source authorization, version, deletion and integrity on worker use.
- **Canonical baseline:** `main` at `fb3c8994edc2d6a7db2781b9a798a21a7a9beec6` (13 Oct 2026).
- **Review branch:** `codex/cw08-conversation-pinned-context-20261013`.
- **Current gap:** `ConversationMessage.selected_sources` stores admitted `document_id`, exact `version` and `sha256`. `AgentRun.input_versions` stores only version IDs. Existing `ContextService._run_and_sources` loaded current `DocumentVersion` attributes without comparing them with the admission-time message pin. A row changed in-place after acceptance could be read as a new context source without detecting the changed admission hash/version.
- **Interfaces reused:** `Conversation`, `ConversationMessage`, `AgentRun`, `require_current_selected_sources`, `ContextService._run_and_sources`.
- **Source files:** `services/coworker/context.py`; `tests/test_conversation_context.py`. No migration or public API addition.
- **Compatibility:** Only runs whose durable idempotency key begins with reserved `conversation:` require the corresponding owned message, existing run link, non-deleted conversation and exact list of current selected document pins. Direct/legacy Agent runs preserve existing source handling. Empty attached-source lists are permitted for conversation runs with no selected documents.
- **Authority:** No new read grants, no automatic mutation/approval, no model-supplied source identity, no connector or browser access. Source checks rely on persisted owner-scoped database identities.
- **Failure results:** Stale hash/version, expired/deleted source, inconsistent run linkage, missing/deleted message and run/source mismatch return `context_sources_changed` (409). Storage/document bytes never become newly authorized by their availability.
- **Acceptance regressions:** `test_worker_context_rechecks_exact_admitted_conversation_pin` (SHA, version, deletion, expiry), `test_worker_context_requires_original_owned_message_and_exact_run_link`, and `test_worker_context_accepts_conversation_without_attached_sources`. Existing `test_runtime_context_invalidates_expired_document_after_admission` must remain valid for non-conversation runs.
- **Verification:** `uv run --frozen --extra coworker pytest tests/test_conversation_context.py tests/test_context_memory.py tests/test_conversation_dispatch.py -q -rs`, plus mandatory GitHub `coworker`, `test-and-build` and `ci-merge-gate` at exact final PR SHA. Test execution in this environment is not equivalent to the full repo runner (no local source checkout).
- **Rollback:** Revert the CW-08 `_run_and_sources` binding check and associated regressions. No schema change. Keep the new protection default-on for already-enabled conversation context, without enabling a disabled capability.
- **External dependencies:** Operated staging release with real worker, temporal persistence, object storage, revocation and cross-owner tests for staging verification. No authorization to provision paid resources or activate production.
- **Out of scope:** Full CW-08 memory workspace lifecycle, CW-09 browser, CW-10 reviewed generated-code execution, CW-11 manifests, deployment and transactions.

## Evidence checkpoint

| Level | Status |
| --- | --- |
| Implemented | Branch-only change `e3ad321a6d51a3c3076b6257d8c65d023a22253c` before documentation |
| Repository-verified | Pending exact-PR-head required CI |
| Staging-verified | Not established |
| Production-qualified | Not established |
| Activated | None |

**Initial reproduction:** Main source and stored-record contracts show no worker-time comparison against `ConversationMessage.selected_sources`; four new regressions exercise modified SHA/version/deletion/expiry and linked-source identity failures. **Testing:** Not run locally against a full checkout; CI evidence must be collected on final SHA. **Review:** Self-review only; independent review pending.

**Next action:** Inspect the CI result for the final PR SHA; diagnose/redesign any failing check without weakening fixtures; then obtain independent review. Continue separate CW-08 context/memory acceptance slices once this patch qualifies.

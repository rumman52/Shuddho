# Day 4 reviewed delegation — acceptance evidence and owner handoff (18 November 2026)

Issue: [#730](https://github.com/rumman52/Shuddho/issues/730). Pinned pre-change candidate: `c8aa7cf8444f1cf8c5408568e78b3cae6792f00a`. Review branch: `test/day4-reviewed-brief-acceptance-20261118`.

## Scope and reproduced gap

The transaction implementation is already on main via merged PRs [#719](https://github.com/rumman52/Shuddho/pull/719), [#738](https://github.com/rumman52/Shuddho/pull/738), [#743](https://github.com/rumman52/Shuddho/pull/743), and [#745](https://github.com/rumman52/Shuddho/pull/745). No separate run/outbox ledger or duplicate aggregate UTF-8 cap is needed.

Before editing, the baseline `tests/test_conversation_reviewed_briefs.py` defined `test_reviewed_brief_rejects_oversized_canonical_utf8_snapshot` twice and `test_admitted_reviewed_brief_replays_after_context_budget_is_lowered` twice. The earlier parameterized function (four collected cases if independently named) and earlier replay test were overwritten by later same-name definitions during Python module import. The later definitions still exercised equivalent cases, so this was a *shadowed-test maintenance/collection issue*, not proof of a product regression.

The patch removes the dead duplicate definitions and adds new, nonduplicate acceptance checks:
- Exactly 4,096 and 16,000 serialized UTF-8 bytes with multibyte Bangla text are valid at both preview and first dispatch; one additional byte is HTTP 422 before any run/outbox record.
- A source's changed SHA-256 after preview invalidates validation and dispatch (409, no admission).
- Every UI review field (objective, constraints, deliverables, output language, selected source) invalidates the digest and requires revalidation before the explicit Start action.
- Existing memory-selection, concurrency, retry-after-follow-up, Runtime v3, and historical replay tests remain unchanged.

The source dispatch path is `ConversationTaskBriefService.validate_in_session` -> `ConversationDispatchService._dispatch_once` -> one transaction inserting `AgentRun`, `AgentOutbox` and message link. This change modifies tests and evidence only, not production implementation, authorization, migration, or runtime configuration.

## Verification commands and evidence status

```bash
uv run --extra coworker pytest tests/test_conversation_reviewed_briefs.py tests/test_conversation_task_briefs.py tests/test_conversation_dispatch.py tests/test_agent_v3_decision_recovery.py -q -rs
npm run test --workspace @shuddho/web-editor
npm run build --workspace @shuddho/web-editor
```

On the pinned main SHA, the focused Day 4 gate collected 25 cases with zero skips/failures, the conversation/dispatch suite passed 171 and memory/dispatch passed 80; browser 53, PG18 compatibility 226, and frontend test/build checks passed. The full Coworker job failed in two unrelated export/worker-loss fixtures now addressed in separate [PR #774](https://github.com/rumman52/Shuddho/pull/774); governance audit and merge gate were also red. [Exact-main CI run](https://github.com/rumman52/Shuddho/actions/runs/44278207003). Those baseline counts **do not** verify this branch. Exact-PR-head results and an independent reviewer must be read back before merge.

## Read-only staging readback (18 November 2026)

| Property | Before | After this source-only change |
| --- | ---: | ---: |
| `shuddho_coworker.cw_agent_runs` | 0 | 0 |
| `shuddho_coworker.cw_agent_outbox` | 0 | 0 |
| `shuddho_coworker.cw_conversations` | 0 | 0 |
| `shuddho_coworker.cw_artifacts` | 0 | 0 |

- Supabase staging is PostgreSQL 17.11; migration ledger `shuddho_coworker.cw_alembic_version` reports `0070`. Checked-in migration head is `0072_merge_0071_heads`.
- Live task digest: **not generated**. Sanitized transaction ID: **not available**. Sanitized worker ID: **not available**. User-visible retrieved artifact: **not available**. Do not substitute fake identifiers or test fixture outputs for operated receipts.
- The Day 2 owner tracker [#728](https://github.com/rumman52/Shuddho/issues/728) records an unprovisioned persistent worker and missing provider/Temporal/storage prerequisites. Staging was **not** mutated, upgraded, dispatched, deployed or billed by this PR.

## Remaining acceptance and authorization gates

1. **A**: Confirm exact-PR-head focused and required CI green and review report; do not merge without the independent human review.
2. **B**: On an owner-approved same-SHA staging deployment, perform the real browser flow: two-page constraint, British English, ambiguous second option -> needs input, add a versioned source, edit deliverable, validate and explicitly start.
3. **D**: Independently run simultaneous Start plus lost-response/retry-after-follow-up; capture redacted canonical digest, one `run_id`, one outbox effect and evidence of changed brief/source/memory pin conflicts. Retrieve the actual worker-produced artifact and verify the reviewed constraints survived.
4. **C**: With explicit staging/release authorization, reconcile migration `0070` vs `0072_merge_0071_heads`, API/worker source and identity, protected storage, Temporal credentials and the GitHub App governance ruleset prerequisites. No DDL or paid worker was authorized in this task.
5. **Founder / owner**: Explicitly approve any billed worker, external sends, provider usage, or production promotion; keep all high-authority/production flags disabled otherwise.

**Disposition:** Source/test improvement only. Repository-verified status depends on the PR's exact-head CI. Staging-verified, production-qualified and activated are **NO / NOT CLAIMED**. The next executable action without additional owner permissions is to review the PR's exact-head CI and request an independent reviewer; the first blocked operational action is the approved staging migration/worker preflight.

---

## PR-specific progress record (preserved from shared roadmap)

## Day 4 reviewed delegation: exact-byte and UI qualification tests — 18 November 2026 (Asia/Dhaka)

Pinned base `c8aa7cf8444f1cf8c5408568e78b3cae6792f00a`. Source change is **tests/evidence only**: removed two shadowed duplicate pytest definitions (same-name imports hid earlier versions), added exact 4,096/16,000-byte Bangla boundary tests with pre-admission 422 and one-run/one-outbox positive cases, source SHA revocation and per-field React preview invalidation tests. Reuses the merged #719/#738/#743/#745 transaction/runtime implementation and does **not** patch production source.

Read-only staging: PostgreSQL 17.11, ledger `0070` versus source Alembic head `0072_merge_0071_heads`; before/after counts all zero for conversations/runs/outbox/artifacts. The digest, sanitized staging transaction/worker IDs, provider result and artifact remain **unavailable**; no dispatch or deployment was attempted. On pinned-main CI, Day 4's existing focused gate passed but the full Coworker and governance/merge checks failed. New branch checks and independent review are separate pending gates. See [Day 4 acceptance evidence](DAY4_REVIEWED_DELEGATION_ACCEPTANCE_2026-11-18.md) and [#730](https://github.com/rumman52/Shuddho/issues/730). Keep production activation, external sends and paid worker provisioning unapproved. Next: inspect exact PR head CI, then owner-authorized C preflight and B/A/D operated same-SHA staging journey.

---

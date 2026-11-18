# Day 3 grounded chat — citation hardening and acceptance evidence

**Recorded:** 18 November 2026 (Asia/Dhaka)  
**Tracker:** [#729](https://github.com/rumman52/Shuddho/issues/729)  
**Follow-up PR:** [#777](https://github.com/rumman52/Shuddho/pull/777) (draft, not approval)  
**Pinned main baseline:** `c8aa7cf8444f1cf8c5408568e78b3cae6792f00a`  
**Red test-only commit:** `b28c42b73470d7460e65679355725a0541b68d4d`  
**First fix commit:** `f99b44a537a4d26dce5718352ad93db4e3918df6`

> **Disposition: code-level citation gap reproduced and fixed; live staging pilot acceptance NOT ESTABLISHED.**
> No production activation, provider spend, new identity/storage content, external dispatch or sends were authorized or performed in this qualification.

## Scope and call path

- The authenticated `services/coworker/api.py` reply and reply/stream routes use `ConversationReplyCreate.expected_sequence` and the authenticated owner, then call the existing `ConversationReplyService`.
- `claim` locks the owner and conversation, loads the server-persisted message's `selected_sources`, invokes `ConversationGroundingService.resolve`, and reserves provider capacity; it does **not** accept arbitrary client-supplied grounded content or create an `AgentRun`.
- `resolve` enforces five sources, checks owner/document version/hash/expiry/deletion via `require_current_selected_sources`, reads bytes via `read_verified_source` and the shared isolated extractor, redacts and bounds excerpts, and constructs `src-N` source metadata.
- `reply` and `prepare_stream` recheck the sources before inference; `prepare_stream` buffers grounded text until citation validation and owner-locked final source recheck/commit in `finish`. **Only text-only answers continue to send incremental deltas before final completion.**
- The existing `ConversationWorkspace`/`client` handles up to five selected sources and displays citation references; the separate Writing Assistant was not touched.
- Read [#739](https://github.com/rumman52/Shuddho/pull/739) and [#744](https://github.com/rumman52/Shuddho/pull/744) alongside the current call path. Their merged protections remain intact; #777 addresses a new narrow malformed-marker case, not a new grounding subsystem.

## Reproduction and smallest fix

In `conversation_grounding.py` at the pinned main baseline, the incomplete-source guard matched only `[[src-` (case-insensitive, optional whitespace). A valid `[[src-1]]` followed by **unclosed, source-looking** `[[src_999`, `[[src—999`, `[[sRc:999`, or `[[ src _ 999` was incorrectly accepted; `[[src-999` was correctly rejected. The latter difference identifies the prefix guard as the cause.

1. **RED:** local isolated Python harness faithfully copying the pinned validator from `conversation_grounding.py`, `python -m pytest -q test_citation_validator.py`: **4 failed (unexpected acceptance)**, exit 1, before editing the implementation. Its copy is not a full repository test.
2. Regression committed **before** the fix in `tests/test_conversation_citation_markers.py`: four validator cases, the service allowlist, and a synthetic TXT grounded SSE test asserting **no displayed delta, no committed answer and no AgentRun**.
3. **GREEN (isolated harness):** widen only the incomplete source-prefix regex to `r"\[\[\s*src"`; rerunning the same harness: **4 passed**, plus normal repeated valid-ID and forged/unknown-ID smoke cases. The real repository tests must be verified separately in GitHub CI.
4. No API, identity, storage, provider, frontend, schema, Writing Assistant or production configuration was changed.

## Synthetic fixture hashes (NOT staging document-version receipts)

| Synthetic source | Input provenance | SHA-256 | Qualification |
| --- | --- | --- | --- |
| `[TXT-A]` | UTF-8 bytes of `Renewal date: 17 March 2027.` | `f7d75177f831588865c68b5db1c11b5658b209f837f89dcf10c3a58ff16a1a3b` | Locally computed; not uploaded |
| `[PDF-A]` | Existing `_simple_pdf` test helper with the same sentence; locally generated pypdf 5.9.0, 647 bytes | `47adaa8a4fb818950a424e667687214b42acb75bade54a08db4d3ae4b72e2a15` | Locally computed; bytes may vary with renderer version; not uploaded |

These hashes identify test fixture bytes, **not** owner-verified hosted document versions. The pinned SHA, owner, source version and authoritative object digest must be re-recorded at actual staging admission.

## Redacted answer reviews (fixture-only, NOT D signoff)

| Language | Synthetic question | Synthetic model/test answer | Claim/citation assessment | Required independent D review |
| --- | --- | --- | --- | --- |
| English | What is the renewal date? | `The renewal date is 17 March 2027. [[src-1]]` | Date matches `[TXT-A]`/ `[PDF-A]`; `src-1` is the only server-defined source. This is **fixture interpretation**, not a captured provider response. | Verify every factual claim, original uploaded digest/version and English output against the real selected source. |
| Bangla | নবায়নের তারিখ কবে? | `নবায়নের তারিখ ১৭ মার্চ ২০২৭। [[src-1]]` | Date matches the same synthetic sentence; Bangla output and authorized citation marker are consistent. This is **fixture interpretation**, not a captured provider response. | Independently verify every factual claim, real citations, Bangla output and source-version receipt. |

Neither row is a model invocation, user-visible staging screenshot or human D approval. Do not count them toward Day 3 live acceptance.

## Read-only platform inventory and zero-admission evidence

The connected Supabase **staging** PostgreSQL readback on 18 November 2026 recorded:
`auth.users=0`, `storage.objects=0`, `cw_conversations=0`, `cw_document_versions=0`, `cw_agent_runs=0`, `cw_agent_outbox=0` and `cw_outbox=0`. The previous readback in this investigation was also zero for all these admission/storage counts. **Before/after AgentRun and both outbox deltas = 0.** This proves no task admission occurred during this read-only work, not that a live authenticated request exercised no admission.

Render `shuddho-api-staging` last reported **live** deployed commit `0e0b662fad0a02817a79a4514abba8f94e0ad022` (14 November 2026), behind pinned `main`; no matching-candidate runtime qualification. The available Vercel connection does not expose a Shuddho-linked project; do not substitute a Vercel preview for the API/source storage/auth boundary. Linear workspace search points to [MD-5](https://linear.app/md-rumman-ali/issue/MD-5/rukh-ai-day-one-close-ci-protected-main-staging-recovery-and-heldout). PostHog project/event mapping and independent telemetry have not been established.

No staging account was created, no PDF/TXT uploaded, no real provider called, and no deletion/revocation made against live private data.

## Tests and release gates

- **Local narrow RED/GREEN:** isolated exact-source validator copy, 4 failed before / 4 passed after. **Not equivalent to full repository tests.**
- **Real Python scope:** `uv run --extra coworker pytest tests/test_conversation_citation_markers.py tests/test_conversation_replies.py tests/test_conversation_context.py -q -rs`.
- **Broader API/grounding:** `uv run --extra coworker pytest tests/test_conversations.py tests/test_conversation_dispatch.py tests/test_coworker_projects.py tests/test_coworker_postgres.py -q -rs`.
- **Web editor:** `npm run test --workspace @shuddho/web-editor` and `npm run build --workspace @shuddho/web-editor` (verify package scripts before executing).
- **Browser:** GitHub Actions `browser-qualification`; fixture evidence is not a substitute for staging with actual owner Auth/storage.
- **Required CI:** `[PR #777](https://github.com/rumman52/Shuddho/pull/777/checks)`, exact corrected PR head/merge SHA. The preexisting full-main Coworker export/recovery and governance configuration failures are release blockers if they persist; no scope-based waiver.
- **Live owner approval gate:** Two synthetic identities A/B, private source uploads and authoritative version hashes, one genuine model-supported English and one Bangla Q&A, foreign-source rejection, source selection/removal/missing-context browser check, revoke-during-generation (no stale output or history), before/after run/outbox counts, model identity, and D's independent citations/language claim-by-claim review. Owner C/staging custodian must explicitly authorize provider use and deployment of the exact candidate.
- **Background worker:** tracked separately; not required for text-only grounded chat but still an overall readiness gate.

## Accountable next step

**A (API/security)**: verify exact candidate focused/red-green CI and review final owner/source/version checks.  
**B (browser/UI)**: verify source selection, missing context and streaming behavior; run live authenticated browser scenarios after prerequisites.  
**C/staging custodian**: obtain explicit authorization, prepare synthetic identities/provider credentials/private storage, exact candidate staging deployment and non-billed/non-production limits.  
**D (independent answer reviewer)**: sign off facts/citations/output language and model receipts; do not accept fixture rows as live review.  
**Release/governance owner**: resolve required CI/governance and independent review before any merge or pilot decision.

**Next executable action:** inspect the exact final PR head's CI; if green, request independent code review. Keep PR draft and stage admission disabled until owner-authorized real qualification has completed.

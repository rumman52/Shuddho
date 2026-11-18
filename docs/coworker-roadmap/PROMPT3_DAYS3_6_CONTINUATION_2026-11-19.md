# Prompt 3 / Days 3–6 — continuation and executable acceptance boundary

**Date:** 2026-11-19 (Asia/Dhaka; UTC readbacks on 2026-11-18).  
**Decision:** **NO-GO / hosted workflow acceptance OPEN**. This document updates [PR #787](https://github.com/rumman52/Shuddho/pull/787)'s immutable November 18 source-only evidence; it does not retroactively change its baseline or claim real user-facing execution.

## Actual, separately verified identities

| Component | Observed evidence | Consequence |
| --- | --- | --- |
| Source | `main` base for [PR #793](https://github.com/rumman52/Shuddho/pull/793): `cebe322d88d2120e6c78c6755b70445eedf8c39f` (merged #789); PR head must be independently re-read after CI | Source fixes and synthetic regression evidence are not hosted proof |
| Render staging API | `shuddho-api-staging`, service `srv-dav98otg1s2s73cod4gg`, last **live** deploy `dep-dbsbon4r5hns73b3dv9g`, commit `0e0b662fad0a02817a79a4514abba8f94e0ad022` (2026-11-14). Auto-deploy **off**, no newer live deployment in service readback | Do not treat successful GitHub CI as the deployed API identity |
| Supabase staging | Project `bsmbvjenpvcyfjzwtuax`, PostgreSQL 17.11, `shuddho_coworker.cw_alembic_version = 0070` (latest source head advertised in the prior ledger: `0072_merge_0071_heads`) | Mismatch must be reconciled under controlled migration/release authorization before accepting new code |
| Staging data | `auth.users=0`, conversations `0`, tasks `0`, AgentRuns `0`, agent outbox `0`, work outbox `0`, artifacts `0`, memory facts `0`, storage objects `0`, worker instances `0` | **Only preflight zeros**; none proves a post-action zero/one/effect condition |
| Storage | Bucket `shuddho-coworker-staging` reports `public=false` | Private bucket configuration is not an owner-A positive / owner-B negative download proof |
| Worker/provider | Render service listing contains no dedicated Shuddho staging worker. [Day 2 #728](https://github.com/rumman52/Shuddho/issues/728) records missing approved Temporal/model/S3 execution prerequisites | No real model-backed artifact, persistent worker resume or provider-side send audit |
| Frontend | Connected Vercel scope lists `ali` only; GitHub status checks may contain another Vercel project, but its owner/preview auth was not established in this connection | Do not claim authenticated hosted browser acceptance |
| Release governance | Prior [CI #44351920620](https://github.com/rumman52/Shuddho/actions/runs/44351920620) failed governance (missing nonempty GitHub App client-ID input) although major source suites passed. The new PR's governance job is skipped rather than approved | An absent or skipped gate is not independent governance sign-off |

Readbacks were obtained from the connected Render, Supabase, GitHub and Vercel APIs. Public platform dashboard URLs are not a substitute for restricted request/response evidence. No secrets were retrieved, printed or modified.

## Day-by-day required proof (every hosted row remains OPEN)

### Day 3 — direct grounded chat

- Owner A and owner B authenticate independently; A uploads selected synthetic PDF/TXT files with recorded source-byte SHA-256 and immutable version pins. Record the actual server-produced Bangla and English answer text, model ID, request ID, source map, citations and factual checks.
- While provider inference is active, revoke/delete the selected source through an authorized endpoint; prove **no stale source-backed delta becomes visible and no stale answer is committed**. Include separate forged citation, foreign-owner and unsupported-file denials.
- Compare the **same** owner-scoped AgentRun/outbox database counts immediately before and after both real direct-chat actions. A pre-action zero is **NOT** a post-action zero.
- Existing source coverage: `tests/test_conversation_replies.py`. It uses bounded synthetic/deterministic provider cases and is not the real hosted acceptance.

### Day 4 — reviewed task admission

- Capture a Bangla multi-turn task brief, initial preview digest, edited objective/constraint/deliverable/language, and newly validated digest. Show an explicit user approval and Start action tied to the current digest.
- Record persisted AgentRun and outbox IDs before/after exact retry; require one run and one admission effect. Race a concurrent edit with Start; require HTTP 409 with **zero additional** admission effects. Include historical-v1 replay.
- Source tests in `tests/test_conversation_task_briefs.py` and `tests/test_conversation_dispatch.py` do not substitute for a hosted concurrent receipt.

### Day 5 — version-selected memory

- On a single pinned model/source/prompt/budget, run **three real inferences**: (A) explicit empty selection, (B) selected `Fact-01@v1`, (C) corrected `Fact-01@v2`. Preserve provider IDs, output bytes/digests and the **specific output fact** that changed. A deterministic context assembly test is not a model-quality improvement proof.
- Attempt foreign, expired, deleted, stale and changed-version pins through the owned API. Prove no unselected same-category fact entered the model input. Replay already-admitted historical runs without changing their identity or effect count.
- PR #789 repaired explicit empty-selection v2 digest, frontend preview/Start serialization and old-v1 replay. **This has merged into source only**; staging still requires requalification.

### Day 6 — two useful bilingual deliverables

- Generate **both languages for both workflows**: a source-cited research comparison and a project report plus unsent email draft. Capture research source URL/title/retrieval date/sha256 and each evidence quote, approved source/fact pins and recorded scope.
- Download/open original DOCX/PDF files as owner A; verify byte length, MIME, SHA-256, headings, Bangla glyphs, English structure, actual factual claims and complete source references. Verify owner B receives a denial for the same artifact IDs.
- Disconnect/reconnect the browser and restart the authorized worker during a running job. Prove identical run/artifact identities and exactly-once effects. Record **provider-side** sends before and after (zero); an unsent-draft label or zero local outbox before any action is not a send audit.
- Run and score all 40 approved model-backed development cases with the frozen rubric and provider budget, preserving first-run outputs and changed-case reruns. [PR #793](https://github.com/rumman52/Shuddho/pull/793) introduces fail-closed research source-SHA validation and aligns the synthetic Day 6 golden test to reviewed explicit memory pins. This remains source/CI evidence.

## Authorization and release path

1. **C / founder:** record fresh exact resource, cost and duration authorization **before** any paid Render worker, Temporal/model spend, new infrastructure, or protected migrations. Prior $7/month approval is explicitly stale (Day 2 #728). No provision/deploy/migration occurred in this continuation.
2. **C / release:** reconcile source SHA, `migrate --check` DB revision, worker poller/Temporal namespace, private S3 endpoint, provider identity, model budget and approved governance secret reference (never print secret material). Capture a signed/redacted immutable release manifest digest.
3. **A/B / operators:** create two synthetic owner sessions via normal authentication; run Days 3–6 through real hosted API and browser against that single release, preserving raw redacted receipts, answer/artifact hashes and errors.
4. **D / independent reviewer:** reproduce source citation/owner checks, verify native files and provider send count, and validate retained exact request/run/manifest identities. Only then mark each specific row **PASS**; never batch-close on CI alone.

## Candidate-change retest rules

Research hash validation or export changes re-open Day 6 factual/source and artifact checks. Conversation dispatch or memory binding changes re-open Days 4–6 and Day 3 zero-AgentRun sentinel. A change to the staged SHA, migration, worker or model re-opens **all** four hosted days. This document is a release-blocking checklist, not a pass receipt.

# Day 6 — source-to-claim and controlled-pilot acceptance evidence (18 November 2026)

**Owner roles:** A/B workflow operation; C staging/security/authorization; D independent recipient-grade QA; Founder/C paid-resource and production release. **Tracker:** [#732](https://github.com/rumman52/Shuddho/issues/732). **Disposition:** **NO-GO** for operated pilot acceptance.

## Freeze and history

- Frozen initial source `c8aa7cf8444f1cf8c5408568e78b3cae6792f00a` at the original Day 6 investigation. Main moved during review to `aa705726f4c76cbb819a62211b7743aa44c59b17` via merged [#774](https://github.com/rumman52/Shuddho/pull/774).
- [#703](https://github.com/rumman52/Shuddho/pull/703) and [#766](https://github.com/rumman52/Shuddho/pull/766) already merged reviewed-brief admission and per-task language/native export validation.
- [Baseline CI](https://github.com/rumman52/Shuddho/actions/runs/44278207003) reproduced two recovery-fixture failures: 1,628 passed, 2 failed, 4 skipped in Coworker. Both used malformed 1-/3-file synthetic renderers incompatible with `DocumentRunner.export -> validate_day6_exports -> storage.put`.
- A parallel Day 1 repair [#774](https://github.com/rumman52/Shuddho/pull/774) now contains the stronger bounded correction: stable real native export bytes, ambiguous second PUT by ordinal, SHA readback, real native child renderer and age-bounded orphan cleanup. **Do not merge parallel overlapping #775**. Distinct independent review and required CI must still be verified for the now-merged candidate.

## Source-to-claim review — implementation contracts, not live proof

| Claim and acceptance criterion | Traceable code/evidence | What it does **not** prove |
|---|---|---|
| Research comparisons bind citations to supplied retrieved pages, valid URLs, dates, titles and source hashes where applicable | [research.py#L33-L60](https://github.com/rumman52/Shuddho/blob/c8aa7cf8444f1cf8c5408568e78b3cae6792f00a/services/coworker/research.py#L33-L60), [#L155-L190](https://github.com/rumman52/Shuddho/blob/c8aa7cf8444f1cf8c5408568e78b3cae6792f00a/services/coworker/research.py#L155-L190) | `validate_evidence` proves quotation inclusion, **not semantic entailment** or independent factual correctness |
| Research brief contains comparison/limitations; English project report/email uses reviewed constraints, source IDs and selected memory, without fabricated recipient/actions | [content_generation.py#L56-L81](https://github.com/rumman52/Shuddho/blob/c8aa7cf8444f1cf8c5408568e78b3cae6792f00a/services/coworker/content_generation.py#L56-L81), [#L231-L251](https://github.com/rumman52/Shuddho/blob/c8aa7cf8444f1cf8c5408568e78b3cae6792f00a/services/coworker/content_generation.py#L231-L251) | Prompt contracts are **not** a delivered bilingual model run or human factual review |
| Research and report/email use native DOCX/PDF/TXT/JSON, structural/MIME/heading/status checks before publication | [exports.py](https://github.com/rumman52/Shuddho/blob/c8aa7cf8444f1cf8c5408568e78b3cae6792f00a/services/coworker/exports.py), [work_exports.py#L106-L123](https://github.com/rumman52/Shuddho/blob/c8aa7cf8444f1cf8c5408568e78b3cae6792f00a/services/coworker/work_exports.py#L106-L123) | Offline rendered fixtures cannot certify a requested file opened from a private owner account |
| Owner/task/content-addressed keys, SHA-256 write/readback and fail-closed completion are present | [runner.py#L248-L345](https://github.com/rumman52/Shuddho/blob/c8aa7cf8444f1cf8c5408568e78b3cae6792f00a/services/coworker/runner.py#L248-L345), [api.py#L2765-L2793](https://github.com/rumman52/Shuddho/blob/c8aa7cf8444f1cf8c5408568e78b3cae6792f00a/services/coworker/api.py#L2765-L2793) | No owner-A private read, checksum receipt or owner-B denial without approved live identities and objects |
| Test fixture recovery and offline quality qualification have reproducible source-based checks | [PR #774](https://github.com/rumman52/Shuddho/pull/774), [PR #775 CI](https://github.com/rumman52/Shuddho/actions/runs/44286592901) | JUnit/fixtures are not an approved-provider 40-case first run, worker-restart operation or D's human quality approval |

## Observable test results and boundaries

The parallel [PR #775 CI Day 6 artifact](https://github.com/rumman52/Shuddho/actions/runs/44286592901/artifacts/14419896139) was independently downloaded and parsed. It contains **107/107 focused pytest successes, 0 skipped**, and a **14/14 OFFLINE fixture quality calibration** (Bangla 2/2; English 10/10; Arabic 1/1; Spanish 1/1). The two original recovery-test names are **not** included in that focused 107-case JUnit; they are part of the extended Coworker suite, which was still running at readback. The PR run used synthetic merge ref `113a54339a2c1f5bafc4fc1ec929926f3d5114bb` (parents: pinned original main and #775's test-only head). This evidence is **not** a verification of new main `aa705...` or the actual 40-case pilot run.

## Day 6 artifact manifest and pass/fail gates

| Workflow / check | Expected output or action | Observed | Acceptance |
|---|---|---|---|
| A/B research in Bangla | `research-report.docx`, `.pdf`, `.txt`, `source-manifest.json` with criteria, findings, limitations, citations | Source code exists; no authenticated generated object | BLOCKED |
| A/B project status/report in English | `report.docx`, `.pdf`, `email-draft.txt`, `source-manifest.json` | Source code exists; no authenticated generated object | BLOCKED |
| Approved-recipient email UI | Clearly says **Draft ready** and retains source associations; zero provider sends | No approved recipient, authenticated UI receipt or send-provider audit | UNVERIFIED |
| Native owner retrieval | Open actual files; check headings, facts, language, MIME, size, SHA-256; A allowed and B denied | No owner identities/object, so no byte-level private readback | BLOCKED |
| Golden conversation | Prior constraints + reviewed brief + chosen memory/docs; Bangla research then English report/email | Run ID **null**; language scores Bangla **null**, English report **null**, English email **null** | BLOCKED |
| Mid-task recovery | Browser disconnect/reconnect, worker restart, same run/artifact, missing-object failure state | No operated receipt | BLOCKED |
| D's 40 development-case first run and regression | 10 per workflow/language cell; immutable first-run and post-fix scores | Frozen registry exists; candidate first-run **null**, regression **null** | BLOCKED |

**Read-only staging preflight:** connected Supabase `shuddho-staging` PostgreSQL 17.11 has 1 private bucket but **0 Auth users, 0 Coworker accounts, 0 agent runs, 0 tasks, 0 artifact records, 0 stored objects and 0 outbox records**; schema ledger `0070` is behind source head `0072_merge_0071_heads`. Zero in the outbox is **not** proof of zero provider-side send calls. The Render staging API has a live older deploy from `0e0b662fad0a02817a79a4514abba8f94e0ad022` (14 Nov) and **no registered workflow** in the connected Render workspace. The connected Vercel account has no Shuddho project. A read-only PostHog search for “Day 6” offline experiments in the active project returned zero; it is not a global absence claim. No production deploy, paid provisioning, schema migration, test user creation, provider send or external-mail mutation was performed.

**Local offline sample outputs:** separate Bangla research review DOCX/PDF and English report DOCX/PDF were generated and visually opened; both have local SHA-256 and byte lengths. They are **not** produced by the Rukh runtime, private-stored, attributable to owner A/B or a passing golden run, and therefore are excluded from the pilot acceptance manifest.

## Next executable step and owner

**C** secures explicit authorization and freezes non-production API + worker + schema/model + private storage + two synthetic owner identities, with private credentials in approved storage. **A/B** then execute the normal-conversation bilingual golden flow and retain actual IDs, reviewed recipient and draft-only state; they must not send. **D** independently opens, checks/rehashes, verifies A success/B denial and lost-object UI/restart, scores each requested language separately and preserves the 40 first-run scores before regression. **Founder/C** separately approve any spend, production mutation or release.

For review of the merged recovery correction, A/B run:

```bash
uv run --extra coworker pytest \
  tests/test_coworker.py::test_partial_export_storage_failure_cleans_unpublished_objects_before_retry \
  tests/test_coworker_retention.py::test_hard_worker_loss_after_object_put_is_reconciled_without_deleting_checkpointed_outputs -q -rs
uv run --extra coworker pytest tests/test_coworker_office.py tests/test_coworker_research.py tests/test_coworker_services.py -q -rs
```

**Do not claim Day 6 completed, make the email send-ready as a send action, or sign off a release from deterministic CI fixtures.** Keep [#732](https://github.com/rumman52/Shuddho/issues/732) open for A/B/C/D operated evidence.
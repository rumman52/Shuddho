# Day 6 — Exact Unsent Email Draft Artifact Contract

> Source: uploaded `03_Rukh_AI_Product_Workflows.docx`, pp. 8–9, Day 6 task D06.T04 (email draft, explicitly not sent), D06.T05–T06 (native artifacts, verified owner bytes), and D06.G03. This is source-level validation only, not hosted acceptance.

## Goal and design

When a reviewed `report_email` package is exported as DOCX, PDF, text and source manifest, **only** the UTF-8 encoding of `draft.email.subject + "\n\n" + draft.email.body` may become the email draft artifact. The draft must not have a renderer-supplied recipient, forged sent receipt, injected dispatch claim, duplicated body, or extra text. The same validation runs at `DocumentRunner.export` before the storage write and at `DocumentRunner.complete` after the private owner-storage byte readback. Preserve all existing published artifact names and content types, human approval before actual delivery, zero outbound sends, and native file gate behavior.

## RED: characterize the existing fail-open predicate

- [x] **Test first** in `tests/test_export_manifest_rejections.py` with six distinct tampered email artifacts from a deterministic `report_email` model task. Each retains both original subject and body, is syntactically valid UTF-8 and keeps real DOCX, PDF and manifest unchanged.
- [x] Prove a no-publish expectation: `CoworkerError("export_invalid")`, **zero** storage puts, failed task and zero published artifacts.
- [x] Commit before production change: `9fe0bfb1eb2d18380495876361e6ca8e412ea635`.
- [x] [GitHub Actions RED run #44921110944](https://github.com/rumman52/Shuddho/actions/runs/44921110944) Coworker Day 6 export-manifest focused step: **6 expected `DID NOT RAISE` failures, 21 passed**. This demonstrates the original substring acceptance vulnerability.

## GREEN: fix one shared native validator

- [x] In `services/coworker/exports.py::validate_day6_exports` replace subject/body substring checks with exact decoded text equality to the deterministic native renderer's `subject + "\n\n" + body`.
- [x] Keep the existing `render_artifacts` output and storage/identity/checksum gates. Do not introduce an email-sending endpoint, external integration, schema migration, or background work.
- [x] Production commit `3175828e4386f780d9d53b19dd07bb5b6a058ffa`.
- [ ] Verify full impacted Coworker, backend Python, frontend, browser, PostgreSQL and source-level CI at final SHA.
- [ ] Have an independent reviewer inspect the code and receipts before the PR is ready to merge. Governance audit is skipped on draft and is not a hosted proof.

## Hosted acceptance boundary

This code change alone cannot prove D06.T04/G03 hosted PASS. The operator must independently inspect the reviewed draft text and evidence gaps, A-owned native text/DOCX/PDF originals and SHA-256, B-denied access, provider send audit before/after (both zero), and the real same-SHA deployed worker/browser/DB/provider release. `scripts.staging_days3_6_acceptance` only checks operator-supplied receipts for *internal consistency*; no one may promote the Day 3–6 exit to hosted PASS until [Day 2 MD-6](https://linear.app/md-rumman-ali/issue/MD-6/rukh-ai-day-2-staging-backuprestore-dual-0071-private-pdf-and-temporal) prerequisite, [Day 3–6 MD-7](https://linear.app/md-rumman-ali/issue/MD-7/rukh-ai-days-3-6-complete-hosted-golden-workflow-and-same-release), and independent review are completed.

## Verification command

```sh
uv run --locked --extra coworker pytest -q tests/test_export_manifest_rejections.py tests/test_coworker_office.py tests/test_coworker_research.py tests/test_coworker_services.py
```

The mandatory GitHub Actions Coworker job provides a reproducible CI execution of the focused native-artifact tests with installed fonts, PDF renderer, database and worker fixtures; verify the exact PR head and do not infer the result from a prior commit.

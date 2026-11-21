# Rukh AI Part 03 — Day 6 native content and readback binding

**Scope:** Original uploaded `03_Rukh_AI_Product_Workflows.docx`, pp. 8–9 (D06.T02/T03/T05/T06/T07, exits G01/G02/G04) and p. 10 independent operated evidence.

## User-visible defect

The prior `validate_day6_exports()` checked four expected file names, MIME/native byte format, DOCX title/headings, PDF openability and nonempty text, email TXT subject/body, and exact source-manifest provenance, but did **not** establish that DOCX/PDF report paragraphs, source references, or source-backed research findings actually match the approved draft.

An unrelated valid PDF or a native DOCX that changes the facts or citations can therefore be accepted. Integrity hashes alone will not reveal that legitimate persisted bytes correspond to a different reviewed content version.

## TDD and acceptance sequence

1. [x] Write failing *actual renderer/worker* tests in `tests/test_export_manifest_rejections.py`: changed reviewed report facts, missing section references, replaced source catalog, readable but unrelated PDF title/claim/reference; separately alter saved reviewed draft between completed export and storage readback; substitute research DOCX finding and quote.
2. [x] RED commit `33429cbe7e8921f7827864b627fd32a49b8f549d` with the optional-dependency collection guard. [GitHub Actions #44910512221](https://github.com/rumman52/Shuddho/actions/runs/44910512221), extended Coworker Day 6 export-manifest step: **8 failed, 13 passed** with expected `DID NOT RAISE` failures. The preceding test-only commit `ed4cf682894824fccc8c02b1a4923ddaabd51c31` had a lightweight Python collection error because `docx` is a Coworker-extra dependency; corrected *before* production change.
3. [x] Minimal production commit `39835fd92e736315d7e7eb56942ad366e4e866ca`: report DOCX must preserve its deterministic reviewed paragraph order, including sections, claims, source IDs, source labels, and evidence gaps. Research DOCX must retain selected findings, exact quotes and gaps. PDF must contain the extractable ASCII/Latin facts and reference fields after whitespace normalization; no strict Bengali PDF transcription requirement, because complex glyph shaping and PDF text extraction may be lossy.
4. [ ] Verify actual GREEN run of `tests/test_export_manifest_rejections.py` on exact final head and run full affected source tests, then mandatory full Python, frontend, browser qualification, PostgreSQL, all Coworker steps and independent review. Fix any failures.
5. [ ] Independent reviewer must inspect original native DOCX/PDF bytes, authority of source facts, Bangla shaping, actual owner-A download SHA, owner-B download denial, same-run reconnect and zero send counts. This cannot be replaced by automated structural checks.

## Boundaries

Keep `DocumentRunner.export` validation before object-storage PUT; `DocumentRunner.complete` rechecks storage identity, readback digest, and the latest saved approved draft. No changes to schema, runtime identity, provider, staging deployment, authorization, external email, or budget. The source-level patch cannot establish hosted acceptance; result remains **NO-GO** until Part 02 Day 2 infrastructure and all Day 3–6 same-release independent operated receipts are collected, checked and reviewed. Follow GitHub #732 and Linear MD-7. Do not fabricate platform evidence, merge without required governance or claim full acceptance from synthetic tests.

## Risk and verification notes

- The report/email Word renderer uses a deterministic paragraph sequence, so exact paragraph equality can be enforced without relying on rendered layout.
- Research references can be implemented as `w:hyperlink` nodes, which are not always exposed as `Document.paragraphs[*].text`; require the source-backed finding and quotation there, and continue binding complete source metadata in the exact JSON manifest.
- Require extractable ASCII PDF claims and source references but **do not infer full semantic fidelity of complex-script Bengali PDF glyphs**; a person opening the actual native bytes is still required for hosted D06.T05/T07.

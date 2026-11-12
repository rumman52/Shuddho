# Consolidated Rukh AI PR conflict resolution — 13 November 2026

## Purpose and release boundary

Consolidate unique, unmerged work from #680, #681 and #682 on a fresh main base without bypassing failed CI, independent human reviews, native branch protection, or the blocked live Render staging prerequisites. This is **source-only** work. No pilot, production or paid deployment is authorized.

## Source-by-source disposition

- **#680, Day 10 recovery fixture:** The main recovery tests already use the four canonical report/email files after #678/#679. Keep main's recovered tests and their existing data-integrity assertions. Preserve #680's extra missing/duplicate/unexpected export-inventory negative cases in `tests/test_export_manifest_rejections.py`. Do not reintroduce the outdated `test_coworker.py` file or overwrite newer recovery fixes.
- **#681, Day 2 evidence:** Carry forward the new immutable-identity reconciliation helper, its negative tests and exact-release operator instructions. This *verifies receipt consistency only*; it does not produce live worker, model, database restore, or owner-isolation evidence.
- **#682, Day 6 quality:** Carry forward additional multilingual research-memory/unsent-email coverage, the quality fixtures and checks, authenticated mobile navigation helper and its focused browser test, plus the fail-early Day 6 CI gate. Keep the newer four-file recovery tests already merged into main, not #682's obsolete overlapping test edits.
- **Mobile CI root cause:** A fixed 64px responsive header can contain the selected-task shortcut; the result preview then intercepts its click. Allow the header to size to its content when `.cw-view-task` is present, rather than forcing Playwright clicks or disabling the browser scenario. Final verification requires the full real-browser CI on this exact branch.
- **Other release blockers:** V-01 main protection and required independent review are not solved by a source patch. Historical Render staging Postgres billing suspension and missing persistent worker likewise require authorized operations and actual runtime receipts.

## Required acceptance

1. Review the combined diff and preserve original PR references.
2. Run exact-head `test-and-build`, `Frontend tests and builds`, `browser-qualification`, `PostgreSQL 18 staging compatibility`, `coworker`, `governance-audit` and `ci-merge-gate`. No skip/reduced acceptance.
3. Confirm new focused Day 2, Day 6 and export-manifest negative cases passed.
4. Obtain independent human approval and enforce branch protection before merging to main.
5. Treat live model/Temporal/restore, 40 held-out human reviews, 20 operated fault receipts, and founder+C pilot GO as separate, unmet release gates. Do not represent a green source PR as pilot completion.

# V-01 — Confirmation review snapshot before CI merge gate success

Date: 21 October 2026 (Asia/Dhaka). Base main: `e937dd974c04c725faca74fb5d6c3569f83c1b2c`.
Draft PR: [#524](https://github.com/rumman52/Shuddho/pull/524).

## Root cause and security boundary

The CI-only `scripts/independent_review_gate.py` fetched the PR, read paginated PR reviews, checked the independent approval, and reread PR metadata. It **never reread review state** after paging. A `DISMISSED` review or new independent `CHANGES_REQUESTED` record between the initial review read and the final PR read could leave a stale, valid-looking approval. Conversely, a head/PR-state mutation while any *new* verification read is in flight must fail closed.

GitHub PR and reviews API calls are not an atomic snapshot; this mitigation reduces the stale-read window, **does not eliminate all races**, and cannot replace GitHub's native required reviews, branch-protection enforcement, or rule-bypass controls.

## Actual regression-first evidence

- Tests-only commit `1f19e502f60accae966de5b3620bb069dba736e3`.
- [RED run #39490196014](https://github.com/rumman52/Shuddho/actions/runs/39490196014): `test-and-build` **failed as expected**: 5 new regressions failed with `DID NOT RAISE ReviewGateError` or the expected second-read call-count assertion; **1,266 tests passed**, 71 skipped, six warnings. `coworker` was not green during RED verification and is irrelevant to implementation proof.
- Source correction `dfcf9e1f7178a7a23cbafd5ab47be33c54e88f60`: shared bounded paginated review fetch, initial evaluation, PR metadata revalidation, full second review fetch, fail-closed comparison when review evidence changed, and final PR metadata validation after the confirmation fetch. On second-read API or pagination failure, no approval is returned.
- Updated existing page-count regression in `200e8595b401d91479d0f660a07cfe6342fd151a`; first-page and second-page ordering is verified explicitly.
- Five new tests: dismissal during review, new change request, PR head update on third PR read, second review read failure, and stable double-read success.
- Exact final-head `test-and-build`, mandatory `coworker` integration and `ci-merge-gate` must all pass before any green-complete claim. Check the final SHA after this documentation commit. An early or cancelled run does not count as success.

## Boundaries and operator release gate

This is defensive coding only: no provider mutation, payment, credential grant, schema migration, branch protection change, production switch, or external deployment. Review state could still change after the last API read; only **effective native GitHub policies** can prevent unauthorized merges.

Independent final-head human review and configured/enforced main protections, with negative tests against unreviewed / red / pending PRs, remain OPEN in [#484](https://github.com/rumman52/Shuddho/issues/484). Previous [PR #523](https://github.com/rumman52/Shuddho/pull/523) merged at **2026-10-20 20:06:45 UTC** despite no submitted reviews; [its exact-head run #39487739882](https://github.com/rumman52/Shuddho/actions/runs/39487739882) had `test-and-build` success, `coworker` cancelled, and `ci-merge-gate` failure. These remain governance incidents and are not cured by this change. Staging [#291](https://github.com/rumman52/Shuddho/issues/291) remains blocked separately.

PR #524 must remain **draft and unmerged** without final-head green CI, independent reviewer approval and native protected-branch verification.

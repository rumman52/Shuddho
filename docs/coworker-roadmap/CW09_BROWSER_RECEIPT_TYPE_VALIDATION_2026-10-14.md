# CW-09 — Browser worker receipt type validation

## Contract and source evidence

- **Workstream:** Architecture/core, CW-09 read-only brokered browser receipt boundary.
- **Canonical references:** `SPEC.md`, `ROADMAP.md`, `docs/superpowers/plans/2026-10-12-coworker-evolution.md`; root `AGENTS.md`.
- **Base:** `main` `ddc81711c8ccb4475d3a0053b26b5955a5be35b1`; successful required main CI [#38548692557](https://github.com/rumman52/Shuddho/actions/runs/38548692557).
- **Branch:** `codex/cw09-observation-type-validation-20261014`.
- **PR:** [#399](https://github.com/rumman52/Shuddho/pull/399), draft/unmerged at checkpoint creation.
- **Defect:** `_bounded_observation` unconditionally called `value.get`. Passing valid worker-transport JSON that is not an object (null, array, string, numeric or boolean scalar) caused `AttributeError`, not a controlled `CoworkerError`. No worker receipt can be treated as valid solely because its JSON parses.
- **Changed boundary:** `services/coworker/browser.py::_bounded_observation`; `tests/test_browser_broker.py`.
- **Expected behavior:** Reject the non-object input with `browser_observation_invalid`, HTTP 409; leave the valid worker claim unsettled and allow a subsequent properly verified receipt. Preserve DNS/origin/ownership/read-only checks and human-supervised browser behavior.
- **Regression:** Five parametrized non-object values exercising the real claimed browser command, error code/status, unchanged running state and later legitimate settlement. No test fixtures, policies, feature switches or CI gates weakened.
- **Rollback:** Revert isolated PR #399; browser Agent capability stays default-off.
- **Security:** No new storage, provider grants or network privileges. This is receipt input validation, not page-text capture or worker egress certification.

## Evidence and outstanding acceptance

| Level | Evidence |
| --- | --- |
| Implemented | `a0601c01e1ddd770ef5a4632a8570223ff588fdf` regression; `edd7fa8bb9dfaccccd19de6edd6c3bdd9646ee01` code |
| Repository-verified | Pending exact-final-head required `test-and-build`, `coworker` and `ci-merge-gate` and review |
| Staging-verified | Not established |
| Production-qualified | Not established |
| Activated | No |

**Required review:** Confirm validation happens before field access, rejects scalar/list/null without leaking stack traces, leaves claims recoverable, and does not mask revoked Agent read authority. Independent review not yet established.

**Next exact action:** Update final branch head after checkpoint, inspect [PR #399 CI](https://github.com/rumman52/Shuddho/pull/399/checks) at that SHA; repair failures, seek independent review without claiming automatic merge. Continue separate CW-09 bounded private page-text observation and canonical release eligibility, CW-10 reviewed persisted proposals and CW-11 runtime skill grants. The full workstream remains incomplete.

# CW-09 — Repair merged mandatory browser CI and release attestation contract

**14 October 2026.** Repository `rumman52/Shuddho`. Branch `codex/cw09-main-red-ci-ledger-review-repair-20261014`. Baseline main `9f8cf53a422ba5eee7d5a0772b2943328d3faaaa`. Source/test SHA before this documentation: `b4f5e0c32fcaa96c05c73aaf7b971a7481f7bb42`.

## Reproduced defects and authority

Merged CW-09 PR [#391](https://github.com/rumman52/Shuddho/pull/391) head `0e6ea7182ffae6e5bf8dbdfc4e229cb6472dcd46` [workflow #38463696028](https://github.com/rumman52/Shuddho/actions/runs/38463696028) failed the **mandatory** `Qualify brokered Agent browser tool without skips` step: `tests/test_agent_browser_tool.py` had 21 passed, 1 setup error because `signed_client` is defined by the API's test module, not the standalone browser gate. After #391 and CW-10 PR #392 were merged, main `9f8cf53` [workflow #38465787058](https://github.com/rumman52/Shuddho/actions/runs/38465787058) failed the same gate. This is a test ownership defect, **not** evidence that a skipped test passed.

The latest independent security review on #391 additionally identified:
- [P1](https://github.com/rumman52/Shuddho/pull/391#pullrequestreview-5509664548): schema-34 `append_agent_browser_read_event` signs release proof when `rollout.incident.change_reference` differs from the deployment's approved `change_reference` even though rollout-file hashes match.
- [P1](https://github.com/rumman52/Shuddho/pull/391#pullrequestreview-5509664548): matching arbitrary string `source_revision` values pass despite the canonical lowercase 40-character Git SHA-1 requirement.
- [P2](https://github.com/rumman52/Shuddho/pull/391#pullrequestreview-5509664548): the ledger append accepts `activation` without `schema_version=1`, later rejected by canonical bundle verification.

Earlier review findings about rollout digest binding, post-deployment status order and independent rollback key were already corrected on main; preserve these protections.

## Bounded implementation

- Remove the improperly scoped `signed_client` fixture test from standalone `tests/test_agent_browser_tool.py`. Preserve its mandatory no-skip browser ledger, routing, worker and cancellation tests. Add its true/false authenticated manifest assertion to the existing `tests/test_coworker.py::test_runtime_manifest_is_authenticated_sanitized_and_uncached`, which owns that fixture and verifies authorization, cohort, no-store and secret redaction.
- Require the reviewed `rollout.incident.change_reference` matches the argument and deployment reference **before** signing schema 34.
- Require the deployment source revision is exactly 40 lowercase hexadecimal characters and matches activation/runtime.
- Require `activation.schema_version == 1` before accepting schema-34 activation evidence.
- Extend synthetic offline ledger fixtures to the intended release contract and add negative cases with **recomputed hashes** for wrong/missing incident, mutated but matching non-Git revision and missing/unsupported activation schema. These tests never count as live staging evidence.

## Verification and release boundary

Pass exact-final-head full `test-and-build`, `coworker`, `ci-merge-gate`, especially `tests/test_agent_browser_tool.py`, `tests/test_coworker.py`, `tests/test_agent_browser_release_attestation.py`, existing full postgres/Temporal/transactions mandatory gates, and independent review. Do not alter required safety checks or broaden permissions to manufacture a pass.

The patch changes no production flags, database schema, Temporal history, credential permissions or API execution authority. All browser-read capabilities remain default-off and activation still requires actual staged independent evidence and execution-time release guard; no page-content storage, isolated browser egress or DNS/redirect safety has been qualified. CW-10 proposal envelope merged in #392 is separately unqualified; operational human-approved code execution and CW-11 reviewed skills remain incomplete.

**Rollback:** revert this isolated change only with an equivalent fail-closed release and mandatory browser gate repair; never disable the tests. **Next exact action:** open draft PR, obtain final-head mandatory CI and independent security review, correct any findings, update canonical progress with exact outcome. No automatic merges/deployment/activation.

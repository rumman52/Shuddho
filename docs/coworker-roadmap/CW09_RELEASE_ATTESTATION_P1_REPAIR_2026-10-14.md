# CW-09: Complete Canonical Browser-Read Release Attestation — 14 October 2026

**Scope:** review-blocking correctness repair to merged [PR #390](https://github.com/rumman52/Shuddho/pull/390), not a new browser capability.
**Base:** main `76a07600328d0c6ff0ed73b69d2c7933d38bf927`.
**Branch:** `codex/cw09-release-attestation-repair-20261014`.
**Initial implementation/tests commit:** `2e03cb331a8833826d9ffd5a92a015713fe57bb3`. **Latest source/test commit before final docs:** `78908cabdc7108a9211aafc416f49ab6d50ff63f` (includes authenticated enabled-manifest regression). **Draft PR:** [#391](https://github.com/rumman52/Shuddho/pull/391), unmerged. First PR-head `test-and-build` succeeded; subsequent source edit superseded that head, so require complete exact-final-head CI.

## Reproduced findings

Merged #390 registered `agent_browser_read` controlled-release evidence and schema 34 but its independent review raised **three P1** issues:
- [#390 review](https://github.com/rumman52/Shuddho/pull/390#discussion_r4263411541): `cohort_recovery_verification.CAPABILITY_ATTRS` omitted the runtime flag and `cohort_rollback_completion.ROLLBACK_MODES` omitted its rollback mode. Recovery could certify an unintended active capability.
- [#390 review](https://github.com/rumman52/Shuddho/pull/390#discussion_r4263411549): `cohort_release_ledger.verify_entries` rejects schema 34 and no append path exists. The registered activation evidence was unachievable.
- [#390 review](https://github.com/rumman52/Shuddho/pull/390#discussion_r4263411559): `/api/v1/runtime-manifest` omitted `agent_browser_read`, making reviewed rollout and runtime proof irreconcilable.

## Minimal existing-authority changes

- Check `Settings.agent_browser_read_enabled` against the normalized approved rollout in the existing recovery validator. This denies legacy/omitted default-off manifest recovering with the read tool silently active.
- Add independent `agent_browser_read` rollback-completion mode, requiring the exact kill-switch environment name, false value, cohort checks and operator evidence.
- Expose `agent_browser_read` in the existing authenticated, owner-cohort-gated, uncached runtime manifest (no new API).
- Extend the tamper-evident release ledger to schema 34: exact `agent_browser_read_verified` event and five artifact hashes. Add `append-agent-browser-read` through the existing HMAC-chained ledger CLI. Its validator requires approved rollout dependencies, passed timestamped staging evidence, clean operator status, deployment/reference binding, identical live runtime capability map and source revision, controlled-cohort proof, exact canonical SHA-256 artifact binds and activation digest, an existing attested stage and deduplicated activation hash. No evidence or execution authority is manufactured.
- Add focused negative tests for wrong flag/recovery, rollback-switch drift, manifest, schema/event/artifact tampering and rejected altered/missing evidence.

## Acceptance/rollback

Require exact-final-head `test-and-build`, full `coworker` with mandatory PostgreSQL/browser suites and `ci-merge-gate`. Review the validation of generated release evidence and old-version chain compatibility. A green older SHA or skipped gate is insufficient. Changes remain branch-only and default-off. Rollback: keep `SHUDDHO_AGENT_BROWSER_READ_ENABLED=false` and revert only the isolated repair if a reviewed replacement retains fail-closed recovery and ledger verification.

**Not done:** actual content capture/private hash, runtime execution-time canonical release guard, real isolated-browser egress/SSRF staging and human acceptance. CW-10 immutable code approval and CW-11 reviewed skill versions remain separate. **Do not merge automatically, deploy or activate.**

**Next exact action:** open draft PR, inspect exact-head CI failure logs and review findings, correct any failures and record final acceptance. If qualified as a repository code repair, continue CW-09 page content and execution-time eligibility as dependency-ready work.

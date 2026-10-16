# CW-10 — owner-inspected exact code review UI (phase 4)

**Baseline:** `main` `d9d664c8b5a735260a17c1af58687e14e2b8c058`, merged [PR #426](https://github.com/rumman52/Shuddho/pull/426). The #426 exact-head CI [#38843127126](https://github.com/rumman52/Shuddho/actions/runs/38843127126) passed `test-and-build`, mandatory `coworker`, and `ci-merge-gate`; merged-main [CI #38844772799](https://github.com/rumman52/Shuddho/actions/runs/38844772799) was in progress at branch creation.

## User-visible outcome

The signed-in owner can discover reviewable proposals from a selected Agent run, explicitly inspect exact Python source and its full SHA-256 hash, original input-version hashes, per-resource compute limits, egress destinations and expiry, and record an explicit human **approve/reject** decision. **Review does not execute or enqueue Python**. Owner revocation can erase the stored source. This is not the missing **trusted model-generated proposal producer**, and is not the future **atomic privileged dispatcher**.

## Security and scope

- New bounded `GET /api/v1/agent-runs/{run_id}/code-proposals` returns up to eight **metadata-only** proposals for the authenticated owner/run. It never includes source bytes or the source snapshot, and uses the existing full immutable-envelope and live source/permission version validator on every candidate before publishing even its review hash. Terminal, expired, revoked, tampered or permission-withdrawn proposals are undiscoverable.
- Selecting an individual proposal calls the existing owner-bound `GET .../{proposal_id}` for the exact canonical source; the rendered text is React-escaped and is not executed or interpreted.
- The separate `CodeProposalReview` panel in Agent workspace is keyed to the current run and clears all previously inspected content when a run changes. It displays the entire source, input version identities and checksums, exact immutable review digest, no-egress policy, expiry and compute ceilings. An explicit "I inspected" acknowledgement is required before a first human review decision.
- `approve`/ `reject` use the existing exact-hash, server-validated human review API. Client-chosen expiry is no more than two minutes and no later than proposal expiry; server checks remain authoritative. `revoke` uses the existing exact-hash endpoint and additionally confirms irreversible source erasure. An approved decision still displays `execution_authorized=false`.
- No new feature flags are enabled, no sandbox/worker dispatch endpoints are called, and no model gains authority. Access is backend-authorized; the frontend is not a policy boundary.
- A closed or newly invalid run may make an old code proposal disappear from the list; this is intentional fail-closed behavior. Existing `get_code_proposal` can return 409 on the later individual fetch; the UI presents that error without source content.

## Files and verification

`services/coworker/agent_repository.py`: bounded metadata listing with live admission checks.
`services/coworker/api.py`: authenticated no-store list route.
`apps/web-editor/src/coworker/client.ts`: typed list/detail/review/revoke methods.
`apps/web-editor/src/coworker/CodeProposalReview.tsx`: explicit owner inspection and decision.
`apps/web-editor/src/coworker/AgentWorkspace.tsx`: actual Agent workspace integration.
`tests/test_agent_code_proposal_persistence.py`: owner isolation, source omission, tamper and revoke tests.
`apps/web-editor/src/coworker/client.test.ts`: exact transport, auth and no execution route.

**Acceptance:** final PR-head mandatory `test-and-build`, no-skip `coworker` (CW-10 and PostgreSQL), and `ci-merge-gate`; React/web-editor test/build must pass. Independent security and browser UI inspection remain required for qualification. Do not mistake passing unit tests for operated staging or activation.

**Known blockers:** no privileged trusted model-authored proposal creator, no safe model-to-owner notification path, no owner-authorized atomic dispatch with recovery and post-revocation worker lifecycle proof. Private-input mounts remain unsupported and must not be claimed present. CW-11 reviewed skills, CW-09 operated browser isolation, and P/V realistic coworker scenarios remain unverified. No merging/deploying/activation under the present authority.

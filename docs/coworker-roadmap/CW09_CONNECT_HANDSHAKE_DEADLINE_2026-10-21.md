# CW-09: Bound the browser proxy CONNECT handshake

- Objective: close stalled broker authorization and upstream TCP handshakes within the existing navigation timeout; never dial from an expired authorization result.
- Dependency evidence: CW-09 proxy and policy tests pass on main `94fd180e895c3fd90e760874ac8ff83cf11c1e78` (21 tests, zero skips). PR #527's separate private-address filtering remains under review and is not duplicated here.
- Base branch/SHA: main `94fd180e895c3fd90e760874ac8ff83cf11c1e78`.
- Work branch: `fix/cw09-connect-handshake-deadline-20261021`.
- Existing interfaces: `createPinnedProxy(state, {validateHost, dial, navigationTimeoutMs})`; existing claim epoch, socket registry and cancellation methods.
- Files: `scripts/browser_pinned_proxy.mjs`, its existing test file, and this contract/progress checkpoint.
- Confirmed root cause: authorization is awaited before any timeout is attached. Once authorization finishes, the upstream inactivity timeout starts a fresh budget rather than sharing the original handshake budget. A stalled TCP connection alone already times out; this patch does not claim that was missing.
- Acceptance: stalled authorization closes without outbound dial/evidence; late authorization cannot dial; stalled upstream closes both sides; a successful, active tunnel survives the handshake deadline. Existing revocation, malformed-response and valid-tunnel tests remain green.
- Compatibility: no schema, tool/provider registration, new dependency, configuration or worker API changes. The existing timeout is reused only for the handshake; the established tunnel retains its inactivity timeout.
- Boundaries: no secrets, credentials, owner grants, egress permissions or approval policies change. Browser capability remains under existing release gates.
- Rollback: revert this patch; no migration required.
- External prerequisites: independent final-head human review and required CI; live Chromium/network staging and V-01 #484 remain separate gates.
- Out of scope: native repository settings, deployment, production activation, provider calls and paid resources.

## Execution plan

- [x] Add real localhost CONNECT regressions and observe the expected failures on unchanged production source.
- [x] Add one handshake timer spanning authorization and TCP connect, clean it up on close/success, and reject late results.
- [ ] Run browser policy/proxy tests, available repository checks and exact-head CI; report unavailable checks.
- [ ] Obtain fresh code review, fix material findings, and publish a draft PR with final evidence.

## Completion evidence

| Level | Status | Evidence |
| --- | --- | --- |
| Implemented | Yes, review branch | Source correction `24d59057637984a97e522a4cecb652cc550d58b3` |
| Repository-verified | Pending | Exact final-head CI required |
| Staging-verified | Not established | Live isolated Chromium not run |
| Production-qualified | No | Qualification gates remain open |
| Activated | No | No activation or deployment |

- Test-only revision `43831763912852a22a55bb6b07d661bb8f423891`: actual local Node regression run reported 22 passed, 2 expected deadline failures, zero skips. The already-existing stalled-upstream behavior and active-tunnel positive control passed.
- Initial implementation: local browser policy/proxy run reported 24 passed, zero failures/skips. Review then reproduced a real ordering defect: an elapsed deadline could be bypassed before its timer callback ran.
- Review regression revision `7189e57`: 24 passed, 2 intended failures, zero skips. Correction `24d5905` captures a monotonic expiry and checks it before evidence/dial and before acknowledging TCP readiness. Final focused suite: **26 passed, zero failures/skips**. Source syntax check passed.
- Separate read-only agent re-review found no remaining Critical/Important issue and confirmed the original real localhost TCP reproduction rejects readiness at 86 ms against a 40 ms deadline, with no HTTP 200. Late authorization produced zero dials and empty evidence. This is agent review, not independent human approval.
- `npm test` completed successfully across the configured workspaces, including 120 web-editor tests (zero failures/skips). The full Python suite and full workspace build are in progress at this checkpoint. All required exact-head CI remains pending publication.
- The GitHub publication attempt was rejected by automatic approval review for repository-authorization verification. Subsequent read-only checks confirmed authenticated user `rumman52` owns the target repository and has push/admin permission. No remote branch or PR existed at that recheck; publication status must be checked separately.
- Existing PR #527 exact-head CI #39540792404: `test-and-build` and `coworker` succeeded; `ci-merge-gate` failed specifically because there is no independent current-head maintainer approval. This is separate from the local deadline correction.
- These are localhost TCP/injected broker regressions, not operated Chromium or staging qualification. Outstanding DNS/broker operations are not cancelled by this patch; sockets and subsequent side effects are bounded.
- Native main protection remains unconfigured in the branch summary (`protected=false`), tracked in #484; staging prerequisites #291 remain open. No merge is authorized by these local results.

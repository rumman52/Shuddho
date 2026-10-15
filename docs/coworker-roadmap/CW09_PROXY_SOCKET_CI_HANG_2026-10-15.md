# CW-09 mandatory browser proxy socket CI hang / cleanup qualification

**Date:** 15 October 2026. **Base:** `main` `1a75eb2f66595ef6ec2f8ccd01156f03276c9566`, incorporating merged PR #410, whose latest [exact-head CI #38711309533](https://github.com/rumman52/Shuddho/actions/runs/38711309533) and [main CI #38711977867](https://github.com/rumman52/Shuddho/actions/runs/38711977867) both reached the mandatory `Test isolated browser worker policy and real HTTPS CONNECT boundary` step without a reported completion at the first investigation. **Review branch:** `codex/cw09-proxy-socket-test-hang-repair-20261015`. No merge/deploy/activation permission.

## Reproduction and root cause

An isolated local Node reproduction based on the merged CONNECT handler and five socket regressions (Node 22) showed the pre-fix test process did not exit within 15 seconds: cancellation and same-command tests timed out at 4 seconds each while client TCP close wasn't observed; the disconnect test could dial before the proxy observed disconnect; and the permitted test's `state.evidence.example.com` JavaScript property access threw a `TypeError` rather than accessing the `"example.com"` entry. This is a deterministic test/code gap and not proof that a live external connection bypassed policy. GitHub's in-progress log download was unavailable until jobs finish.

The **production cancellation defect** is that `scripts/browser_pinned_proxy.mjs` registers the inbound `clientSocket` in its cleanup `sockets` set only **after** the asynchronous broker network-check. While DNS is pending, `proxy.pause()` cannot destroy that inbound socket, so cancellation leaves a pending CONNECT resource in the proxy.

## Bounded production and qualification fix

1. Register each incoming `clientSocket` and its close handler **at the beginning of the actual CONNECT callback**, before first awaited validation, not after `net.connect`. Keep the upstream in the same sockets set after it is established. `pause/destroy` now close pending inbound sockets even with broker network-check stalled. Existing exact command/epoch/evidence, HTTPS/443 and pinned-IP checks and pre-200 fail-closed behavior stay.
2. Node test clients always drain incoming bytes; track up to 8,192 recent characters and emit a test-local response event to reliably assert successful HTTP 200 without losing an early response.
3. The pause and ABA tests demand the actual inbound client socket close **before** the suspended broker promise resolves, and then assert zero outbound dials. The disconnected-client test explicitly tears down the server-side transport after the client disconnects, without assuming the server observes a remote FIN while asynchronous validation leaves the socket unread.
4. Fix hostname assertion to the literal bracketed `state.evidence["example.com"]` key. No weakenings of ownership, pinned IP, TLS, or safety assertions.
5. Source-level isolated local reproduction of the corrected real proxy/test logic: five passing tests, no skipped cases, process exit 0 in ~0.1s. This is **not** GitHub exact-head repository evidence; the final PR checks below remain required.

## Gates and limits

- Final-head `test-and-build`, mandatory `coworker` with PostgreSQL, Temporal, transactions, full browser worker tests and zero skipped mandatory modules, `ci-merge-gate` must pass on this branch, not a prior #410 SHA. Check finished GitHub logs for any further blocker.
- Explicit independent reviewer/security assessment and operated Chromium network/SSRF/DNS-rebinding staging are still absent. This fixes a pending-socket cancellation leak and makes regression tests finish deterministically, **not** all CW-09 acceptance, a production SLO, or release eligibility.
- Existing PR #411 (CW-10 atomic source/receipt binding) was branched from the same merged `main` and remains a separate draft; if this fix reaches default branch, #411 must refresh its base and rerun final-head CI rather than relying on inherited stuck tests.
- No database migration, provider, external action, permission expansion, runtime feature activation or deployment.

**Keep draft and do not auto-merge/deploy/activate.**

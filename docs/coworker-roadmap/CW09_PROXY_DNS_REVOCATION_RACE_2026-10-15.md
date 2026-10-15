# CW-09 browser proxy async authorization revocation race — 15 October 2026

**Base:** `main` `896b5014bc371f5549fb9daa815338d932506a73` (source artifact PR #406 merged; matching main [CI #38699094958](https://github.com/rumman52/Shuddho/actions/runs/38699094958) passed). **Working branch:** `codex/cw09-browser-proxy-revocation-race-20261015`. Independent safety hardening; do not depend on the separate in-review direct-main source-erasure PR. Feature remains default off, supervised takeover compatibility unchanged.

## Reproduced code-level gap
`scripts/browser_worker.mjs` binds its local HTTPS CONNECT proxy to the browser worker, not directly to one immutable command. The CONNECT callback captures a hostname, awaits `validateHost(commandId, host)` (which calls DNS + trusted API network check), then initiates a socket to the resolved pinned IP. During that `await`, the browser session can be paused/cancelled or the runtime reassigned a new claim. Previously the callback neither rechecked the current command nor an immutable claim generation after the await. Worse, client/upstream sockets are registered **after** the network-check awaits; `proxy.pause()` cannot destroy a socket that was not yet registered. There is another interleaving while `net.connect` completes before acknowledging a tunnel. A stale response could therefore establish a tunnel for a no-longer-active command. This is an observed source-level race condition, **not evidence of live exploitation**.

## Intended safety outcome and patch
- Each active proxy claim has a monotonically incremented in-memory `proxyClaimEpoch` on `setCommand`, `pause`, and `destroy`. The CONNECT handler snapshots immutable `{commandId, epoch, evidence}` before validating. This closes same-command resume ("ABA") and different-command transition races.
- `browserProxyClaimValid` is pure and validates current state identity, claim generation and evidence object reference. Validate before network-check, **after asynchronous network-check and before any outbound TCP connection**, and again on the upstream socket's `connect` event **before** sending `200 Connection Established`, forwarding any request head or piping bytes.
- Only the original snapshotted command ID is passed to the server network-check. The old claim cannot mutate new command evidence; after invalidation the tunnel fails closed.
- Existing enforcement of HTTPS-only, DNS/pinned IP authorization, worker API token, request method policy, current user-grant checks, claim cancellation and existing socket destroy remains. No new external provider, backend API, approval ledger, migration or rollout flag.

## Acceptance and limitations
1. Node policy tests prove a claim captured pre-await is invalid after cancellation while awaiting DNS, and that same command ID reused after pause, evidence replacement and another command fail. Valid current claims still pass. Existing worker policy tests must continue passing.
2. Full CI on the final PR SHA: `test-and-build`, mandatory `coworker` PostgreSQL/Temporal/browser/transactions, `ci-merge-gate`, no skipped required checks. Perform explicit author second-pass and independent adversarial review.
3. A **live Chromium/network proxy race test under staging identity** is required for operated qualification. Unit policy tests don't prove it. Real SSRF, CNAME/DNS rebinding, redirect, content injection, socket-level interrupts and network isolation remain relevant CW-09 acceptance; claim not closed by this bounded patch.
4. Source erasure PR and this safety PR are independent branches rooted in the same main SHA. Do not merge/deploy/activate without separate authorization and gates.

**Completion label:** source implementation and tests on branch, repository qualification pending until exact-head checks pass, staging/production not qualified, activated no.

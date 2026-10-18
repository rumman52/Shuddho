# CW-09 — Real HTTPS CONNECT cancellation and claim-race qualification

**Opened:** 15 October 2026. **Baseline:** `main` `74902c9223d648d3422a7d70b18991e8266f0281` ([PR #409](https://github.com/rumman52/Shuddho/pull/409) merged its `6993024eee41961e7c22cda76817939dc1eb193d` resolved race patch). **Branch:** `codex/cw09-proxy-socket-race-qualification-20261015`. Existing agent browser stays disabled unless explicitly configured and separately qualified. No external provider, billable call, deployment or merge.

## First unresolved observed acceptance gap
PR #409 put monotonic proxy claim generations and before-dial / before-200 checks into `scripts/browser_worker.mjs`, but its new tests in `scripts/browser_worker_policy.test.mjs` exercise **only the pure claim predicate**. They do not demonstrate that the *actual* `http.Server` CONNECT callback, async authorization, socket registration, pause/destroy or TCP event ordering refuse stale connections. A source-only race fix can regress even when a predicate unit test stays green.

## Minimal vertical slice
- Extract the existing production CONNECT server into a dedicated trusted `scripts/browser_pinned_proxy.mjs` module, leaving the ordinary worker's code-owned `validateHost` and configured navigation timeout in `browser_worker.mjs`. The same route, HTTPS/443 authority parser, broker network-check, pinned response IP and state claims are preserved. The factory optionally accepts a trusted dial callback solely to substitute **in-process local TCP** for external Internet access in tests; untrusted page/commands cannot select dependencies.
- Preserve the already merged `browserProxyClaimValid` checks before network-check, after its asynchronous result and on upstream TCP connect **before HTTP 200/piping**. Strengthen the post-await gate by checking `clientSocket.destroyed`: a browser cancelling a pending CONNECT must not cause an unnecessary outbound dial, even if the server has not revoked the claim.
- Add `scripts/browser_pinned_proxy.test.mjs` to exercise actual local `http.Server` CONNECT and TCP sockets with suspended broker authorization: cancel during wait; resume same command ID with a new generation; disconnect client during wait; revoke before pending TCP connect acknowledgement; and an allowed pinned destination. Assertions count independent outbound dial attempts and `200 Connection Established` acknowledgements, not merely a helper boolean.
- Add this test to the **existing mandatory** GitHub `coworker` Node browser worker policy job. Existing Python broker, owned Agent browser, PostgreSQL, Temporal and transaction suites stay mandatory with no skips, and `test-and-build` must pass.
- No API/DB schema/Temporal workflow contract changes, no changes to model authority, no second ledger, no worker egress or authorization bypass. Supervised browsing continuity unaffected.

## Acceptance and limitations
1. Pending broker checks deny stale/same-ID-resumed/disconnected-client TCP dials, and permitted owned command opens its tunnel. The test drives the production handler, not only exported authorization predicates. No live Internet domains or real private endpoints used in CI.
2. The final PR commit SHA must pass all required `test-and-build`, `coworker`, `ci-merge-gate` jobs; review the exact logs and skip results. Explicit author second-pass is not independent review. Reviewers should check lifecycle, socket cleanup and possibility of bypassing the pinned proxy.
3. **Not equivalent to staging verification:** live Chromium browser, real DNS resolution and redirect rebinding, network namespace or egress firewall enforcement, object-store S3 erasure, and adversarial page-content prompt-injection still need operated evidence. Source code/tests do not establish 99.9% availability.
4. Architecture/core remains INCOMPLETE; CW-10 exact approved generated code, CW-11 reviewed skill publishing/selection, selected memory/context staging, operated recovery, and formal release gates remain in the canonical inventory.

**Release rule:** draft review only. Do not merge, deploy, enable, pay for providers or activate a cohort without explicit authorization and the required gates.


## Follow-up: fail closed on malformed broker DNS results — 19 October 2026

The CONNECT proxy previously assumed that the trusted network-check response always contained the expected hostname and a non-empty list of resolved IP literals. It selected `resolved_ips[0]` without validating the response shape. A malformed or mismatched response could therefore pass an undefined/non-IP host into `net.connect`; Node's default host behavior makes that an unsafe assumption even though the normal broker path rejects empty/private results.

The follow-up in `scripts/browser_pinned_proxy.mjs` validates the returned hostname against the CONNECT target (normalizing case and one trailing dot), requires 1–16 resolved entries, and requires every entry to be an IP literal before updating evidence or dialing. Invalid broker output is denied by the existing fail-closed CONNECT error path. The server-side `validate_resolved_addresses` public-address policy remains authoritative; this is an additional response-shape guard, not a replacement for DNS/SSRF controls.

The real local CONNECT test covers a missing response, hostname mismatch, empty and non-array address lists, an invalid IP literal, and excessive result count. It asserts zero outbound dial attempts and no CONNECT 200 acknowledgement. All traffic remains in local test sockets; live Chromium, redirect/DNS rebinding, private-network isolation and staging evidence remain unverified until separately operated.

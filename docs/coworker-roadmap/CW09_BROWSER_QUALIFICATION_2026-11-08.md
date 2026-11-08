# CW-09 — browser runtime qualification increment (8 November 2026)

**Base main:** `ebc6a3547fbaa6b3e3a1e55396938ecdaecbc192`  
**Review branch:** `codex/cw09-browser-runtime-qualification-20261108`  
**Capability:** `browser.read` remains default-off.  
**Release status:** source-level hardening and CI qualification only; no staging or production activation.

## Existing foundations retained

- The worker already uses Playwright Chromium and the owner-bound browser broker.
- The CONNECT proxy checks the active command claim, revalidates each CONNECT hostname through the broker, rejects non-public/mixed address sets, pins the approved IP, and closes pending sockets on cancellation.
- Agent reads are read-only, do not import or persist authenticated browser storage state, and block service workers, downloads and non-GET/HEAD requests.
- Captured visible text is bounded, sealed until settlement, hashed over the exact UTF-8 bytes, and stored as an owner-bound private `browser_source` artifact.
- Per-source deletion revokes metadata before object deletion; failed object deletion is eligible for the existing orphan reconciler.

## Changes in this increment

1. **Chromium proxy enforcement**
   - Remove Chromium's implicit loopback proxy bypass with `bypass: "<-loopback>"`.
   - Disable QUIC and DNS prefetch, block Chromium-side destination DNS resolution, and disable non-proxied WebRTC UDP. The sole Chromium resolver exception is the numeric loopback address of its worker-owned proxy.
   - For Agent read-only contexts, block all WebSocket upgrades and disable WebRTC/WebTransport page APIs before scripts execute.
   - Keep the proxy endpoint restricted to the worker-owned `127.0.0.1` listener.

2. **Request target policy**
   - Context-wide request routing applies the HTTPS/443, same-origin and method policy to page and dedicated-worker requests.
   - Reject IP-literal, single-label, localhost, metadata and local/internal suffix destinations before continuing a request.
   - Preserve method-level Agent read-only checks and the existing broker/proxy DNS checks as independent layers.

3. **Real Chromium regressions**
   - Launch the installed Playwright Chromium headless shell.
   - Route a real browser navigation through the production CONNECT handler.
   - Verify a redirect to `localhost` reaches the proxy and is denied before a second TCP dial.
   - Verify a fresh Chromium process cannot reuse a prior public DNS authorization after the same hostname is rebound to a private address.
   - Verify an Agent read-only page cannot open a WebSocket, access WebRTC/WebTransport APIs, or send a POST from a dedicated Web Worker.
   - The fixture uses a local TLS server and a test-only dial mapping. It is not live Internet or staging evidence.
   - WebSocket-backed page features intentionally fail closed in Agent read-only mode; use the human-supervised path when such interaction is necessary.

4. **Source cleanup regression**
   - Extend the browser-source deletion-outage test to invoke `RetentionService.cleanup_orphans` with an age-qualified synthetic inventory record.
   - Verify the unreferenced private object is removed by the real reconciler after deletion failure, while source metadata and access have already been revoked.

## Required verification

- `node --test scripts/browser_worker_policy.test.mjs scripts/browser_pinned_proxy.test.mjs`
- `node --test scripts/browser_worker_chromium.test.mjs` after installing Playwright Chromium.
- `uv run --extra coworker pytest tests/test_agent_browser_tool.py -q -rs`
- Exact-head `test-and-build`, `frontend`, `coworker`, dedicated `browser-qualification`, and `ci-merge-gate`; inspect skipped tests and logs.
- Independent security review of proxy bypass semantics, browser transport flags, redirect behavior and DNS/CNAME edge cases.

## Explicit qualification boundary

This increment adds Chromium-level proxy, resolver, request-target and read-only realtime-transport restrictions plus real Chromium/proxy integration tests. It does **not** prove kernel-enforced network namespace isolation, host/container firewall policy, live DNS resolver behavior, real CNAME rebinding, deployed worker identity, S3 deletion behavior, or protected-staging rollback. Those require an operated protected staging worker and independently captured evidence.

Do not mark CW-09 production-qualified or enable `agent_browser_read` from these repository tests alone. Do not merge, deploy or activate automatically. Rollback is limited to reverting this review-branch commit.

# CW-09 — worker-side public-IP fence for browser CONNECT

**Task date:** 2026-10-21 (Asia/Dhaka)  
**Base main:** `0c4b8a7d049aad4ff4657a5f101af55d05c792b5`  
**Draft PR:** [#527](https://github.com/rumman52/Shuddho/pull/527)

## Scope and objective

A broker network-check response may inadvertently return syntactically valid but non-public DNS answers. The pinned proxy in `scripts/browser_pinned_proxy.mjs` must refuse every private, loopback, link-local, documentation, multicast, NAT64/transitional or mixed public/private address **before any TCP dial**. This is redundant defense-in-depth: the existing Python broker in `services/coworker/browser.py` already applies `ipaddress.is_global` and owner/claim policy; no trust or permission boundary is removed.

## Root cause and test-first reproduction

Original `networkCheckMatchesTarget` checked hostname matching, address-list length and `net.isIP(address) !== 0`. It did **not** test public routability. A direct local reproduction of the original predicate returned **true** for `127.0.0.1` and raised the expected assertion when asked to refuse it.

- **Test-only commit:** `4431e5fa0d7136114353c075d2f7d12d6ed867b9`, no source changes.
- The existing real HTTPS CONNECT suite in `scripts/browser_pinned_proxy.test.mjs` now includes 14 new negative DNS cases covering localhost/metadata/RFC1918/CGNAT/benchmark/multicast/IPv6 ULA, link-local and mapped IPv4, plus a mixed public/private answer. Each case requires **zero outbound dials**, no successful CONNECT response and no false DNS evidence.
- **Important RED limitation:** exact-head [test-only CI #39539992177](https://github.com/rumman52/Shuddho/actions/runs/39539992177) was cancelled when source commits superseded the branch before the long coworker job reached the browser step. Do **not** claim test-only real-CONNECT RED completed. The independent local predicate reproduction (not the actual integration harness) is the observed RED evidence.

## Implementation

- **Source commit:** `1d4334f709bc8b5875889dcb63e6ae3d4b121ad9`.
- Use Node `net.BlockList` deny CIDRs for non-global IPv4; accept IPv6 only from 2000::/3 and reject transitional/documentation subnets. IPv4-mapped IPv6 is denied by the non-global IPv6 restriction.
- A single invalid item rejects the **entire DNS answer set**; never select a public item and ignore a private sibling. The existing pinned IP, exact worker claim epoch, CONNECT-only port 443 and cancellation checks remain unchanged.
- Local Node v22 classification probe: **16 reserved/non-public blocked**, **4 public IPv4/IPv6 accepted**. This is a focused data check, not a complete proxy or staging exercise.
- Worker runs Node 20 in CI. No new package, outbound host, permission or credential required.

## Verification and release boundary

- **Required:** final-head `test-and-build` now directly executes `node --test scripts/browser_worker_policy.test.mjs scripts/browser_pinned_proxy.test.mjs`, so a fast CI pass cannot hide a private-DNS CONNECT regression while a longer run is cancelled. Mandatory `coworker` continues executing the same real-proxy suite as well. `ci-merge-gate` and independent review remain separate. No skips for mandatory safety checks. Exact-head results are not implied by the local probe.
- **Security:** no browser live egress, DNS rebinding, actual Chromium redirect chain, isolated-worker network namespace, private S3, synthetic identity, or production deployment was exercised. CW-09 **staging verification remains blocked** on operated infrastructure.
- **Review:** independent code/security review required; validate CIDR deny list against broker `ipaddress.is_global` semantics and real network policies. A privileged broker failure or new address special use must still be considered.
- **Governance:** V-01 [#484](https://github.com/rumman52/Shuddho/issues/484) requires effective protected main and negative controls. The new PR is draft and **must not be merged** until independently reviewed and fully checked. Staging [#291](https://github.com/rumman52/Shuddho/issues/291) remains separate.
- **Rollback:** revert only this proxy filter/test/doc change on the feature branch. Never disable the broker's network-check to achieve test pass.

## Completion evidence

| Level | Status |
| --- | --- |
| Implemented | Source and test changes committed to draft PR |
| Repository-verified | Pending exact-final-head coworker integration |
| Staging-verified | Not verified |
| Production-qualified | No |
| Activated | No |

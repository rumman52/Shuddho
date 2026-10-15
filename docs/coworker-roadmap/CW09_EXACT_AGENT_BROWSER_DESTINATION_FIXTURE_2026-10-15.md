# CW-09 Agent browser DNS fixture exact-destination CI repair — 15 October 2026

## Scope and reproduced regression
Merged [PR #401](https://github.com/rumman52/Shuddho/pull/401) at main `052194a2b27eafc13d37b701cd90d25e887993eb` still failed its [exact PR-head CI](https://github.com/rumman52/Shuddho/actions/runs/38681248077): `test-and-build` passed; required `coworker` Agent browser test had **1 failed and 35 passed**; `ci-merge-gate` failed. The newly added negative DNS test creates a server-owned Agent session for `https://example.com/` then calls `prepare_agent_read` for `https://example.com/article`. That call correctly fails closed with `browser_agent_scope` before the test reaches DNS evidence. This is a test fixture defect, not a defect in the destination-binding policy.

## Implementation contract
- **User-visible outcome:** Retain exact server-bound destination security, while actually testing that malicious DNS worker evidence causes a committed terminal Agent rejection and cannot be rewritten.
- **Base:** main `052194a2b27eafc13d37b701cd90d25e887993eb`. **Branch:** `codex/cw09-bound-destination-ci-fixture-20261015`.
- **Change:** In `test_agent_browser_dns_violation_is_terminal_and_cannot_be_rewritten` only, create the session at `https://example.com/article`, identical to the already-established command and final URL. No service implementation or policy change.
- **Acceptance:** Newly corrected negative test must reach `complete_command`, return `browser_network_blocked`, commit failed+cancelled session and failed command, then reject a clean-looking replacement; the full mandatory Agent browser suite must pass with zero required skips. Verify exact-final-head `test-and-build`, `coworker`, `ci-merge-gate` and independent safety review.
- **Boundaries:** No changes to API, authentication, permission, DNS/SSRF checks, worker, provider, ledger, DB schema, feature switch or deployment. Preserve default-off Agent browser and all existing mandatory CI gates.
- **Residual:** CW-09 remains metadata-only, without independently operated page-content provenance, sandbox egress/SSRF, staging, runtime release-gate eligibility and production evidence. CW-10 generated-code execution and CW-11 reviewed-skill activation remain separate incomplete workstreams.

## Evidence
| Level | State |
| --- | --- |
| Implemented | One-line test fixture correction committed on review branch |
| Repository verified | Pending all required exact-head CI jobs |
| Staging verified | No |
| Production qualified | No |
| Activated | No |

**Next:** Inspect the PR exact-head CI and review; repair any further mandatory failure without weakening safety. Continue CW-09 real content capture once CI is green.

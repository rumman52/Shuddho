# CW-09: autonomous browser credential and HTTP mutation isolation

**Date:** 15 October 2026. **Base main:** `45906f87cf2eba9f6abb5afc654f834166fa5820`. **Branch:** `codex/cw09-agent-read-cookie-isolation-20261015`.

## Reproduced source-level risks
The default-off `browser.read` Agent tool reuses the human browser broker's navigation command and Python worker receipt path. Prior source read showed:

1. `scripts/browser_worker.mjs` created a Playwright context from `command.storage_state` for **all** commands, then serialized `context.storageState()` into **every** completion, including `agent_read_only`. The broker accepted and persisted this state from Agent receipts. This needlessly introduces cookies and state continuity into an autonomous research surface.
2. `scripts/browser_worker_policy.mjs` `browserRequestAllowed` allowed POST, PUT, PATCH, DELETE for `kind="navigate"` without consulting `policy.agent_read_only`. An untrusted page can cause subresource writes without a model asking to click. The browser-worker route had no Agent-specific method restriction.

These are source-level enforcement gaps; no live exploitation or operated production event has been claimed.

## Required behavior
- The Agent-owned browser worker must **not import** `storage_state` from the server command; the broker must **not provide** it, independently of worker behavior.
- The Agent-owned worker must **not collect or send** cookie storage after reading.
- The broker must reject even a syntactically valid Agent worker cookie receipt, commit the same terminal failed session/command, and deny a clean retry.
- For Agent-owned `navigate` only, worker network requests other than GET/HEAD must be rejected before dispatch. Preserve the separate human-supervised browsing/takeover contract, including authenticated continuity.
- Preserve existing auth, DNS/redirect/proxy, origin, exact-run ownership, revocation, feature default-off, worker claim and current persisted schema.
- Do not activate the feature, assert a live egress test from a JS policy fixture or count metadata-only title hashing as actual page capture.

## Verification
- `node --test scripts/browser_worker_policy.test.mjs` (network-method and storage policy)
- Full mandatory GitHub `test-and-build` and `coworker` (including zero-skip CW-09 Agent browser, PG and Temporal, transaction checks), `ci-merge-gate` **at exact final PR SHA**
- Python `tests/test_agent_browser_tool.py` covers forbidden cookie receipt committed terminal, refused second receipt and unaffected clean read. Existing `tests/test_browser_broker.py` protects supervised storage continuity.
- Second-pass review must check cancellation/worker ownership, claims, Unicode error precedence, fatal receipt isolation, page POST network suppression, and human-browser continuity. Independent review if available.

## Remaining limitations
Even after required CI passes, content capture is still metadata-only. A live, isolated browser worker run with real private extracted page text/bytes and truthful SHA-256, provider-independent DNS/SSRF adversarial checks, staging release eligibility and operated evidence are still required. CW-10, CW-11, context/recovery scenarios and production qualification remain incomplete.

**Status on branch at authoring:** source+regression implemented; exact-head CI and independent review pending; staging not verified; production not qualified; not activated. No auto-merge, deployment or permissions changes.

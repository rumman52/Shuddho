# Day 2 runtime manifest evidence boundary — 2026-11-26

## Task contract
- Base: `f7138e2025f6f5719aea4f4babfcc3549fae324b`; branch `fix/day2-runtime-manifest-evidence-20261126`.
- Scope: the authenticated HTTP runtime-manifest read used by the existing release freeze. Reject ambiguous/invalid JSON and bound actual body consumption; no new runtime capability or production flag.
- Root cause: `client.get` buffered an unrestricted body before permissive `response.json()` decoded duplicate names, non-finite floats and alternate encodings. A reviewed capability manifest could be shadowed, and unbounded content consumed memory.
- Reuse: extract the existing strict UTF-8 evidence parser from `staging_release_evidence.py`, preserving file reading and hashing; stream the runtime response using the existing 1 MiB evidence bound, request identity encoding, reject unexpected content encoding, and preserve the no-proxy/no-redirect/auth settings.
- Files: `scripts/staging_release_evidence.py`, `scripts/staging_release_freeze.py`, `tests/test_staging_release_freeze.py`, this contract and PROGRESS.md.
- Acceptance: duplicate root/nested keys, non-finite literals/overflow, oversized bytes, UTF-16, compression, invalid status/shape/UTF-8 all rejected; valid UTF-8 including Bangla accepted; stop after 17 64-KiB chunks on oversize and close response. Existing full release checks unchanged.
- Local excerpt-level pytest (real httpx 0.28.1 and synthetic response bodies): original function 9 failed / 5 passed; patched functions 14 passed; additional real MockTransport streaming case 15 passed. These are copied function excerpts, not full checkout execution (GitHub DNS unavailable in local sandbox).
- Test-first commit `79e24a82e1d6c3cd93d99f3c636c912e3c0afb34`; implementation `f8b1cc2055c0db39570e0dd8454823ce946c52c0`.
- Verification: run `uv run --extra coworker python -m pytest tests/test_staging_release_freeze.py -q` and exact-head mandatory CI; independent review required. No claim of full CI success.
- Compatibility: runtime JSON must be UTF-8 and uncompressed as requested by the verifier. Operators must not relax the bound or accept alternate encoding to accommodate an unreviewed deployment. A slow-stream total wall-clock deadline is not added by this slice.
- External boundaries: governance missing independent-review enforcement/credentials; database remains 0070; no authorized synthetic owners, restore or worker operation. No paid infrastructure, migration, model calls or deployment.
- Status: IMPLEMENTED_UNVERIFIED, live Day 2 BLOCKED_EXTERNAL, production not qualified or activated. Next: independent review and exact-head CI.

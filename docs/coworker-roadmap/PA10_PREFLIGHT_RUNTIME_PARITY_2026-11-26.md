# PA-10 / D02.T01–T05 — staging preflight runtime parity

- Objective: reject staging configuration values that the static preflight previously accepted but the runtime parses or consumes differently. Preserve exact staging boundaries and valid percent-encoded credentials.
- Dependencies: #727, #728, #291; #920 and #923 are already merged as of base `43d99fd64467492a7da809cda0ae178191e53981`. No new hosted authority.
- Base: `43d99fd64467492a7da809cda0ae178191e53981`; branch `fix/day2-preflight-runtime-parity-20261126`.
- Reuse: standard-library-only `scripts/staging_prerequisite_preflight.py` (also invoked by system Python in the worker provisioning workflow); do not add SQLAlchemy to that entry point. Compare actual runtime URL normalization and raw settings in `services/coworker/config.py`, engine creation in `services/coworker/database.py`.
- Changed: preflight, its existing test module, this contract, progress log. No schema or API changes.
- Regression: preflight trimmed eight runtime settings that are consumed raw; TLS with padding was certified true but runtime lowercasing alone does not make it true. Unicode decimal ports passed; a 5,000-digit port raised ValueError instead of the sanitized preflight failure. urllib normalized uppercase schemes and leading controls and accepted ambiguous raw userinfo that SQLAlchemy interprets differently. NUL in decoded DB password and raw DEL previously passed.
- Acceptance: reject padded exact runtime fields, whitespace/control in namespace/region, non-ASCII or overlong ports, noncanonical scheme, raw controls and ambiguous userinfo, decoded NUL. Preserve all three supported schemes, correctly escaped password delimiters, case-insensitive true TLS and all existing endpoint/role/TLS/queue/bucket checks. No secret values in exceptions.
- TDD: reconstructed complete source and test modules; Git blob hashes matched exact main (source `e72b74a551d28d149abd94315b7a1f2d284fb309`, tests `8f868d268a7ebaadf210ece83492ec9e103b3c0c`). Original focused suite 46 passed. Tests-first commit `e33b561647f82d4b88b832368045eebf7b78b5ea`; local RED 25 failed / 49 passed. Source commit `5f7974adfaa4e24d569e419c960bd4d735f9e496`; GREEN 74 passed / 0 skipped, py_compile passed. Patched GitHub blobs match locally tested bytes (source `464eba8ba4d34e597a8b9a367748cdbac3114ef0`, tests `18b0d81bc47d2ef5b64726d06ee771b7c2c9f6b6`).
- Commands: `python -m pytest -q` in isolated two-file reconstruction; `python -m py_compile scripts/staging_prerequisite_preflight.py`. Required full checkout and exact-head mandatory PR CI remain separate. Local clone blocked by GitHub DNS; no claim of full suite or hosted qualification.
- Security: static input validation only; no network calls, provider credentials, changes to production settings, billing, database, deployment, telemetry, governance or runtime feature authority. Public DNS syntax remains not a certificate or approved namespace attestation.
- Rollback: revert this scoped PR through reviewed protected rules if needed; leave staging admission disabled while evidence is incomplete.

| Level | Status |
| --- | --- |
| Implemented | Focused RED/GREEN verified on exact source and test bytes |
| Repository-verified | Pending exact final-head full mandatory CI and distinct human review |
| Staging-verified | BLOCKED_EXTERNAL |
| Production-qualified | No |
| Activated | No |

Next: inspect exact-head checks, obtain distinct approval and native governance enforcement before merge. Founder/C must separately authorize original backup/restore, migration, worker cost, model budget and reviewed staging deployment; D must independently verify live receipts. Do not treat a green static check as provider identity or operated recovery evidence.

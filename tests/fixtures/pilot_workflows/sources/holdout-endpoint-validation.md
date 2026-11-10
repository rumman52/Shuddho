# PA-10 — staging prerequisite endpoint validation (29 October 2026)

- **Objective:** Before any protected staging provider is contacted, fail closed on malformed or local auth-issuer/S3 HTTPS URLs. Keep genuine public HTTPS provider endpoints valid.
- **Dependency / reason:** `scripts/staging_prerequisite_preflight.py` previously called `urlparse(value.strip())`, which silently removed CR/LF/TAB and accepted IP literals, localhost, internal/single-label hosts and leading/trailing whitespace as valid HTTPS endpoints. The separate [PR #593](https://github.com/rumman52/Shuddho/pull/593) secures `staging_release_freeze.py` and does **not** cover this preflight.
- **Baseline:** `main` `141d1f0f16655dcb4037cb32fafbae374aab42e1`.
- **Branch:** `fix/pa10-preflight-https-raw-host-20261029` (draft review).
- **Existing interface:** `_validate_https_endpoint(value: str, name: str) -> None`; no CLI or environment schema changes.
- **Files:** `scripts/staging_prerequisite_preflight.py`, `tests/test_preflight_endpoint_security.py`, this task contract and `PROGRESS.md`.
- **Acceptance:** reject CR/LF/TAB, whitespace trimming, loopback/private/link-local IP literals, internal/local/single-label DNS names and trailing-dot hostnames; accept existing public Supabase Auth/S3 HTTPS shapes; errors identify only the configuration key, never the supplied secret.
- **TDD evidence:** Using an isolated local mirror of the unchanged source function: new 36-parametric-case suite initially reported **28 failures / 8 passes** (unsafe inputs accepted). After the bounded fix: **36 passed**, Python compilation passed. This is *not* the full repository suite or live provider proof.
- **Required checks:** `python -m pytest tests/test_preflight_endpoint_security.py tests/test_staging_prerequisite_preflight.py -q`, full `test-and-build`, full `coworker`, `ci-merge-gate` on exact PR SHA, independent review.
- **Security limits:** Shape validation does not verify DNS resolution, prevent rebinding or enforce network egress isolation. Those protections must stay at the execution boundary. This change does not handle secrets, networking changes, deployment, billing, worker creation, production promotion or high-authority flags.
- **External blockers:** Render free staging DB expires at `2026-10-31T17:11:33.79468Z`, no verified restorable backup; missing Render persistent staging worker; `main` protection and independent review absent; production auto-deploy enabled. See [#291](https://github.com/rumman52/Shuddho/issues/291) and [#484](https://github.com/rumman52/Shuddho/issues/484).

## Completion evidence

| Level | Status | Evidence |
| --- | --- | --- |
| Implemented | Proposed branch | Local isolated red-green tests: 28 expected failures before / 36 passes after |
| Repository-verified | Pending | Exact PR-head CI and independent review still required |
| Staging-verified | Not performed | Blocked by protected infrastructure and credentials |
| Production-qualified | No | Independent security and release sign-off required |
| Activated | No | No feature flags or environment settings changed |

**Next:** review the branch code, run mandatory CI on its final SHA, require independent current-head approval and native branch governance before merge. Separately preserve/restore-test the staging database before expiry.

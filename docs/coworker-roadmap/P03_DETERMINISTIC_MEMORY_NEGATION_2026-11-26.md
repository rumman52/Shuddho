# Prompt 03 / Day 5 — deterministic explicit memory negation

- Objective: D05.T04/T08. A current explicit negation must suppress matching remembered terms consistently; unrelated word fragments must not suppress memory.
- Base: `43d99fd64467492a7da809cda0ae178191e53981`; branch: `fix/p03-deterministic-memory-negation-20261126`.
- Test-first commit: `a212847ca8ea47f849dfbde30e06f0103d6bff57`; source commit: `b24e8b5a2dd8b22cb1d80c96db2073b39294fcb8`.
- Existing interface: `context_policy.memory_conflict`, used before planner/drafting memory serialization.
- Root cause: the old code sliced the first twelve terms of a Python set, making the result hash-seed-dependent and silently omitting valid terms. Substring matches could also confuse a longer unrelated word or a phrase embedded in another word with explicit negation.
- Fix: intersect whole words following explicit negation with remembered terms; include ordinary typographic apostrophe. The existing length-four threshold and positive style-axis precedence remain. Input lengths are bounded by the existing schemas. No saved facts, versions, reviewed digests, authority, persistence schema or provider settings changed.
- Regression: five failing cases plus three positive controls before the patch; all eight passed after it, including separate processes with `PYTHONHASHSEED=1,2,3,42`. The complete existing stdlib policy test file plus appended cases passes 23 tests.
- Local execution used full byte-for-byte copies of the inspected module and test file in an isolated directory, **not a repository checkout**. Original module blob `11aeb1e39ee7465212237a8201832c0aebfa17b4`; original test blob `1131a7ed97db9de5137659412c5c645a8ba474f8`; exact patched blobs `167442d85f7944def71db29e59231815d66f3674` and `a6439b7042dd34d9984f800f446648ce5e3c7d97` matched remote readback. Commands: `python -m pytest -q tests/test_memory_negation.py --tb=short` (local regression-only file), `python -m pytest -q tests/test_context_policy_security.py --tb=short` (repository test file), `python -m compileall -q services/coworker/context_policy.py`. No test skips in these local runs.
- Required: exact-head full mandatory CI, distinct current-head review, and the approved staging two-owner/golden workflow. Local checkout unavailable (GitHub DNS resolution failed). This narrow rule is not unrestricted natural-language contradiction detection or bilingual quality attestation.
- Rollback: revert source and regression together. No migration.

| Axis | Status |
| --- | --- |
| Source | SOURCE_IN_PROGRESS (patch and exact-file tests; CI and distinct review pending) |
| Staging | BLOCKED_EXTERNAL |
| Production / activation | NO-GO / unchanged |

No production deployment, provider calls, paid provisioning, external sends, telemetry or transaction changes were performed.

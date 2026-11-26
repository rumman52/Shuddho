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

## Continuation: negated style directives

The prior deterministic whole-word fix left a separate axis-precedence defect: negated style commands (e.g. "don't write professionally") could be classified as a positive style choice, suppressing a compatible saved preference and retaining the forbidden one. Generic negation could also misread "write" as banning all writing. Separate bounded affirmative and negative choices and track recognized style-negation offsets; preserve generic negation elsewhere and ordinary research-topic vocabulary.

- Test-first `7ab205c19570a0abf0f4f7c695aa8ad79a01ad90`: 9 failed / 28 passed on previous exact module. Source `eeb81c6bee311844ddea511647543266ee6e9c12`: 37 passed. Topic guard and prepositional regression tests `35fda9a8398e7fad7d0ac615395fed7440e0b647`, `957dcce9d96f2bbdf0919b0f9084e2d1c5760081`: 3 failed / 39 passed on intermediate code. Source `6724b312028cd9312e8ccad5dca83e7c53b924ad`: 42 passed / 0 failed / 0 skipped across each of four hash seeds.
- Exact source blob `aaa154d47f4801f5e282b019fc717a7a04828519`, test blob `d84ce2028871a7b1af5eb9c4b38f93923856ae29`. Command: `cd /tmp/rukh-p03-precedence && PYTHONHASHSEED=1 PYTHONPATH=. python -m pytest -q tests/test_context_policy_security.py --tb=short` (also 2, 3, 42); compileall succeeded. Full byte-identical module/test copies; no integrated checkout.
- Original PR CI run 45776214356: engineering jobs passed; independent review gate failed because draft. New head requires fresh CI. No human review or hosted acceptance. This deliberately bounded English-language heuristic does not establish arbitrary natural-language or bilingual preference correctness.

# D02.T06/D02.T09 — strict release evidence Unicode and publication parity

- Objective: fail closed before malformed evidence is hashed or published; preserve valid bilingual text and existing receipt bytes. Canonical Day 2 issue #728; depends on #727, #920 and #923. PR #931 and #947 have separate production source ownership.
- Base: `43d99fd64467492a7da809cda0ae178191e53981`; branch `fix/day2-strict-evidence-unicode-20261126`.
- Existing interfaces: `parse_evidence_json`, `release_context`, `write_private_json` in `scripts/staging_release_evidence.py`; freeze HTTP reader already reuses the parser. No signature/schema/dependency changes.
- Root cause: UTF-8 decoding of raw bytes does not reject JSON-escaped lone surrogates; Python JSON accepts them in keys/values, but downstream canonical UTF-8 hashing cannot encode them. The private writer used default permissive serialization, publishing non-finite numbers and keys that collide after JSON coercion, which the existing strict reader cannot consume.
- Acceptance: reject lone/misordered surrogates even in nested keys/arrays before evidence read/hash; reject invalid writer receipts before temporary or target file creation; preserve valid Bangla, emoji/supplementary scalars, replacement character, same byte format, atomic non-overwriting publication and existing no-follow snapshot checks.
- Tests-first commit `627703002ac9e90542f3593d45ebcc7ce3c37230`; source `ae050e8427d01fabde100bc7f65d341366bbf9f5`; mandatory no-skip CI wiring `be6a0c30a122d6c9eb8cec274fa96dd498032172`. Full local reconstruction of exact source blob `e10a8dd9c7735df15b5e88a7781b9668445321d8` and existing test blob `f459e33d8dcd4c97e822f5520ce3f3955da6289c`. No network stubs in this focused test. Test blob `2f7222b0843d5c23ef87cad8b85b87a231cec51d` and patched source blob `0160f663ea93e6b5266f61c140da036107c0eb50` verified against remote. New regressions RED 12 failed/1 passed; GREEN 13 passed; combined existing + new 28 passed, zero skips/failures/errors. Python compilation passed. Exact mandatory gate script blob `1115c30dad7981dc254317e11b1163bb8affa833` checked both modules successfully against real JUnit.
- Commands in isolated reconstruction: `python -m pytest -q tests/test_staging_evidence_unicode.py`; `python -m pytest -q tests/test_staging_release_evidence.py tests/test_staging_evidence_unicode.py --junitxml=green.xml`; `python -m py_compile scripts/staging_release_evidence.py tests/test_staging_evidence_unicode.py`; `python -m scripts.mandatory_test_gate green.xml --required-module tests.test_staging_release_evidence` and `--required-module tests.test_staging_evidence_unicode`. Both modules are now explicitly listed in the existing Day 2 Coworker no-skip CI group.
- Files: source, new regression module, CI workflow, task contract, PROGRESS.md. CI adds required test coverage only; no credential/permissions/job-condition changes.
- Boundary: no network/provider requests, database or storage writes, deployment, paid provisioning, credential changes, governance mutation or telemetry activation. No claim of authentic hosted receipt, custody, approved migration, or successful restore. Valid existing evidence byte format is preserved. Additional writer validation performs a second parse of the serialized payload before publication; evidence files are low-volume operator artifacts.
- Rollback: reviewed revert through protected rules only; leave staging admission blocked. No bypass of malformed evidence or required checks.
- Full checkout remains unavailable (local DNS); exact-head full CI and distinct human review required. Shared PROGRESS.md conflicts with parallel prompt branches must be reconciled without dropping entries. Native ruleset/App audit remains an external prerequisite.

| Level | Status |
| --- | --- |
| Implemented | Focused RED/GREEN on hash-verified source |
| Repository-verified | Pending exact-head full CI and independent review |
| Staging-verified | BLOCKED_EXTERNAL |
| Production-qualified | No |
| Activated | No |

Next: inspect exact-head CI and no-skip evidence, restore native ruleset protection, obtain independent reviewer signoff, and reconcile approved changes. Do not run hosted Day 2 until original-state archive/restore proof, dated Founder/C authorization and exact candidate identity are available.

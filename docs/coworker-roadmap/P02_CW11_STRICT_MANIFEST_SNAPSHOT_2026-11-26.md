# Prompt 02 / CW-11 — exact persisted reviewed skill manifest reconstruction

- Base: `f7138e2025f6f5719aea4f4babfcc3549fae324b`; branch: `fix/p02-cw11-strict-manifest-snapshot-20261126`.
- Tests-first commit: `da59d38dd317ddaca7c361a20d423a0b96127d64`; source commit: `c44c95852d972137a75ffae3078d1e01a85c6393`.
- Root cause: manifest_from_snapshot reconstructed known fields and converted any iterable tool_names to a tuple before computing review/publication identity. Unknown top-level and resource-limit keys were silently discarded; a mapping could masquerade as the approved tools array. Numeric limit types were accepted at this boundary.
- Fix: require exact declared top-level/nested keys, plain dictionary limits, exact integer and string types, list/tuple tool names with exact strings. Preserve canonical JSON-array and in-memory tuple forms. Existing downstream manifest hashes, grant checks, code-owned reviewed source pins, state and worker-revision fencing are unchanged.
- Local isolated evidence: `python -m pytest -q /tmp/rukh-p02/manifest_probe.py --tb=short` on manually copied decoder with fixture dataclasses/errors: RED 5 failed, 1 compatibility case passed; GREEN 6 passed. Not full repository CI or an actual persisted PostgreSQL publication.
- Regression coverage: tests/test_coworker_skill_manifests.py, five malformed variants plus canonical round-trip with actual pilot manifest and existing validation.
- Required next: full exact-head CI and independent review, existing CW-11 staging collector on approved frozen worker. No new skill, provider, tool grant, deployment, cost, or activation.
- Residual: no hosted revocation/drain/rollback evidence, publisher identity qualification, or complete Prompt 02 acceptance.

| Level | Status |
| --- | --- |
| Implemented | Source committed |
| Repository-verified | Pending |
| Staging-verified | Blocked |
| Production-qualified / activated | No |

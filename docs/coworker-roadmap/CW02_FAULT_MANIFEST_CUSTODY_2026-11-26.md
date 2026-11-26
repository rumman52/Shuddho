# CW-02 fault manifest custody — 26 November 2026

- Scope: #378, master completion brief, fail-closed CW-02 qualification evidence. Base f7138e2025f6f5719aea4f4babfcc3549fae324b.
- Root cause: the CLI opened its manifest using unrestricted Path.read_text, following symlinks and permitting oversized files and overflowed JSON numeric values; the existing strict reader did not reject 1e999.
- Test-first commit: 626b3d1930e2c1dde4f3bd8715c9128b8b4b6670. Four CLI cases use the existing sixteen-scenario synthetic bundle: valid control, linked manifest, oversized manifest, exponent overflow.
- Source commit: a2663578a66d9f7d703679987943f3eaba841292. Reuses staging_release_evidence._read_rollout_manifest (1 MiB, stable regular-file descriptor, no-follow, strict JSON). Keeps direct/module entry points and explicit nonqualification on errors. Existing scenario contracts and per-receipt limits unchanged.
- Local focused verification: baseline source blob 1af225ea88d348e113f7f886f2c6ed9d3f4ec29a matched GitHub exactly; isolated copied module, existing fixture helpers and shared reader excerpt, not a full checkout. RED 3 failed/1 passed; GREEN 4 passed. Direct and module --help succeeded; patched blob 6d301c557fcbd37e489ec3628d6716c8de080547 matched connector response. Full CI, broader suite, and independent review pending.
- Run uv run --extra coworker pytest tests/test_transaction_chaos_matrix.py -q -rs and all mandatory exact-head CI; no staging proof is claimed. Individual fault receipt read-path races are a separate residual risk, not corrected by this change.
- Rollback: revert scoped source/test/docs commits together; no schema or runtime authority changes.
- Production and controlled pilot remain NO-GO; no provider calls, deployment, paid provisioning, secrets, migrations, or activation. No task/exit credit advanced.

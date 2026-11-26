# Day 9 evaluation evidence snapshot stability — 26 November 2026

- Scope: #735, Day 9 frozen candidate/holdout custody and evidence integrity. Base f7138e2025f6f5719aea4f4babfcc3549fae324b.
- Root cause: _read_evidence_bytes opened one no-follow bounded regular file but did not compare descriptor metadata before and after reading. In-place replacement, truncation, growth and permission changes could be accepted; private blinding-key validation relied on stale mode.
- Test-first  fed91d80651df426d30e29306f4ddedf7b8ef720; source 6cb23f0a3ec76d0d3d5804523e51b5790ff4689f. Reuse the existing descriptor and size cap; compare device, inode, mode, size, bytes read, mtime and ctime. No path reopen, new dependencies, rubric or authorization changes.
- Local focused reproduction used the copied exact reader function, standard-library filesystem operations and deterministic timing injection. RED 4 failed/1 passed; GREEN 5 passed. Full repository clone unavailable due DNS; full mandatory exact-head CI and distinct independent review pending.
- Verify with uv run --extra coworker pytest tests/test_ruke_pilot_eval.py -q -rs plus required repository CI. Synthetic tests do not establish independent custody, genuine held-out results, operated recovery or staging acceptance.
- Residual: directory-ancestor trust and mutation after the final metadata read are outside this bounded patch; use independently controlled immutable evidence and real access receipts.
- Rollback: revert scoped source, test and doc commits together. No schema, production flags, provider, deployment or spending changes. No acceptance credits advanced.

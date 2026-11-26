# Prompt 02 D03.T02/D04.T04 — malformed source kind

Base main `43d99fd64467492a7da809cda0ae178191e53981`. Implemented serially on source-validation PR #941 to avoid competing edits to the context regression file.

Previously list/dict resource types in persisted JSON reached set membership, raising TypeError rather than the normal 409 source conflict. Validate string type before membership. Existing owner, digest, version, expiry and deletion checks are unchanged. No database lookup is needed for malformed source kind.

Test-first `89d0aa8802f81234455ad6c5cb2d83d8126589d4`; source `bcbcad149810d732a61d070776e845b23765a49c`. Isolated guard probe (DB-valid path intentionally excluded, local time/error stubs): `python -m pytest -q --tb=short test_pin_probe.py`: RED 4 failed/3 passed; GREEN 7 passed in 0.03s. `python -m py_compile pin_probe.py test_pin_probe.py` exit 0. Seven repository regression cases verify typed conflicts without DB access. Full exact-head CI, independent review and hosted acceptance remain required. No production or staging changes.

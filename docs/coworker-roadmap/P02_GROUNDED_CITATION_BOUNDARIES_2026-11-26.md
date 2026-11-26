# Prompt 02 D03.T05 — exact source citation boundaries

Base: `43d99fd64467492a7da809cda0ae178191e53981`.

Regression: malformed surplus brackets around a permitted ID were accepted because the regex matched an inner pair. Reject these without changing valid adjacent/repeated citations or Bangla prose. This verifies citation syntax/allow-list, not the truth of a generated claim.

Test-first commit: `905700146939bfb84acecc69ebddb16676cf53d7`. Source fix: `b05192cc93c73849642bd277397879a5d73198a8`.

Local isolated harness copied the pinned citation function and regex verbatim (not a full repository checkout): `python -m pytest -q --tb=short test_citation_probe.py`: RED 8 failed, 3 passed; GREEN 11 passed in 0.04s. `python -m py_compile citation_probe.py test_citation_probe.py`: exit 0. Repository integration tests added to `tests/test_conversation_context.py`; exact-head CI pending. No provider, production, migration or telemetry changes. Independent review and authenticated hosted acceptance remain required. Shared PROGRESS.md deliberately left untouched to avoid conflicting parallel edits.

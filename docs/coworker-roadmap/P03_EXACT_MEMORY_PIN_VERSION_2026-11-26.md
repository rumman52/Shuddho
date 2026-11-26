# Prompt 03 — exact memory pin version boundary

Base: `43d99fd64467492a7da809cda0ae178191e53981`. Issue #731; D05.T01/T08. The memory pin schema coerced JSON true, integral floats and numeric strings into positive integer revisions before approval digest construction. Require strict positive integers for newly supplied pins while preserving integer serialization, duplicate checks, cap, omitted selection and explicit empty selection. This does not change the DB schema or namespace compatibility.

Test-first `3029322a8cad938113342bc26e092fe20e11dbc9`; source `be5e7aaaf2e66b4beb8f9f717cbe1a1050660ef3`.
Local `cd /tmp/rukh-p03-pins && python -m pytest -q tests/test_memory_pin_versions.py --tb=short` RED 5 failed/8 passed, GREEN 13 passed, zero skips. Exact original and patched schema blobs verified (`cbbe1e50f8dfaf21dbc0499bde736a1c1b2b85b4`, `8f36df53ae8d81576ad67979411922b21ed93ba8`); local dependency limited to copied existing text validator. Test blob verified `5e60898e351b98d8bbac8b69a5160518926c97d0`. Compileall passed.

Repository command: `uv run --extra coworker pytest tests/test_memory_pin_versions.py tests/test_conversation_task_briefs.py -q`. Full checkout blocked by DNS, exact-head mandatory CI and independent review pending. NO-GO for staging acceptance; no provider, configuration or production changes. Revert source and regression together if rollback is needed.

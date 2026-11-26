# Prompt 02 / conversation — strict DeepSeek reply frames

- Base: `f7138e2025f6f5719aea4f4babfcc3549fae324b`; branch: `fix/p02-chat-provider-stream-shape-20261126`.
- Test-first: `46938456f2ee7632d3509f0b71d88a565813c7d2`; source: `b62f5bf6102fef1255ef904420e7f015873a778b`.
- Root cause: the SSE decoder converted falsy delta values to an empty object, allowing null, false, zero, empty strings and empty arrays to be treated as a clean stop after text. The streaming and nonstreaming reply decoders did not reject non-null legacy function_call fields.
- Fix: require an object delta on each choice, reject non-null legacy function calls alongside the existing tool-call/refusal checks. Ordinary text and empty object stop frames remain compatible. No tools, new provider, retry, credential, grant or feature-flag changes.
- Local isolated evidence: `python -m pytest -q /tmp/rukh-p02/chat_probe.py --tb=short` on manually copied adapter methods with HTTPX MockTransport and a stub _post_review: RED 7 failed / 1 passed, GREEN 8 passed. No real provider requests or full repository test claim.
- Regression tests: tests/test_conversation_replies.py adds six malformed SSE terminal-delta cases and one legacy nonstream function-call case. Existing valid split-SSE/Bangla coverage remains unchanged.
- Required: exact-head full CI, focused conversation tests, independent review and operated staging browser/adapter acceptance. No staging or production mutation. The Prompt 02 exit gate remains unmet.

| Level | Status |
| --- | --- |
| Implemented | Source committed |
| Repository-verified | Pending |
| Staging-verified | Blocked |
| Production-qualified / activated | No |

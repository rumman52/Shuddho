# Prompt 02 D03.T06 — DeepSeek reply frame semantics

- Base: `43d99fd64467492a7da809cda0ae178191e53981` (includes prior #921 correction).
- Branch: `fix/p02-deepseek-reply-frame-semantics-20261126`.
- Regression commit: `1af7922f14c887390cfdcb54400c33c581206404`.
- Implementation: `9a2d81f05b128f184ece3676b4b4edfb5c39834e`.
- Scope: existing text-only DeepSeek direct-chat adapter; no provider change, new tool, authority, migration, deployment or live request.

## Root cause and correction
The previous decoder ignored the response role and choice index, accepted arbitrary empty-choice frames, and yielded text before validating the frame's finish reason. Nonstreaming shape checks also assumed an object/list. Reject non-assistant explicit roles, nonzero/noninteger explicit choice indices, error envelopes, malformed response shapes, early or duplicate usage trailers, and truncated-frame text before its first yield. Preserve missing role/index compatibility, ordinary Bangla output, optional single usage object after a clean stop, and stop/[DONE] handling. Usage remains opaque: no token count is fabricated.

## Test evidence
Test-first reproduction using a manually copied pinned adapter class, real HTTPX MockTransport and a stub _post_review (no network or full repository checkout): `python -m pytest -q --tb=short test_reply_probe.py`: RED 13 failed, 1 passed; GREEN 14 passed in 0.11s. `python -m py_compile reply_probe.py test_reply_probe.py`: exit 0. The regression is committed in the existing tests/test_conversation_replies.py. Full repo checkout DNS is unavailable; exact-head CI, independent human review and approved provider/owner A/B staging acceptance remain required. The adapter does not promise to detect bytes sent after the protocol's [DONE] delimiter, nor does this patch retract already emitted earlier ordinary text if later frames fail. Grounded replies remain buffered by the existing service.

Status SOURCE_IN_PROGRESS, staging/independent BLOCKED_EXTERNAL. Do not merge without review or activate any capability. Shared PROGRESS.md left unchanged to avoid conflicts with concurrent work; reconcile at integration.

# Shuddho Agent Instructions

## Project goal

Shuddho is a Bangla AI writing assistant. The production architecture must be AI-first for deep review, with local spelling/rule/dictionary engines as fallback and quick typing support.

The main user experience should be similar to a professional writing assistant:
- User writes Bangla text.
- Deep AI Review reads the full text with context.
- Backend returns structured suggestions and corrected text.
- Frontend shows suggestions clearly with apply/dismiss actions.
- Backend never silently returns 0 suggestions when AI failed.

## Important principles

1. Do not expose API keys in frontend code, commits, logs, or test fixtures.
2. API keys must be read from backend environment variables only.
3. OpenAI should be the primary provider when SHUDDHO_LLM_PROVIDER=openai.
4. OpenRouter should still work when SHUDDHO_LLM_PROVIDER=openrouter.
5. Local spelling/rule/dictionary engines must remain available as fallback.
6. Heavy local ML corrector must not block production when its checkpoint is missing.
7. Missing checkpoint should be a health warning, not a hard crash.
8. /api/check must return diagnostics explaining whether AI was requested, attempted, used, skipped, failed, timed out, or truncated.
9. Frontend must not show a confusing empty result when AI actually failed.
10. Keep code maintainable, typed, tested, and production-safe.

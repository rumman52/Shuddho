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
3. The competition generative runtime is Gemma-only: `SHUDDHO_LLM_PROVIDER=gemma`.
4. The Google Gen AI SDK/API is transport for `gemma-4-26b-a4b-it`; OpenAI,
   OpenRouter, Qwen, and Gemini models must fail closed without a generative fallback.
5. Local spelling/rule/dictionary engines must remain available as fallback.
6. Heavy local ML corrector must not block production when its checkpoint is missing.
7. Missing checkpoint should be a health warning, not a hard crash.
8. `/api/check` must return diagnostics explaining whether AI was requested, attempted, used, skipped, failed, timed out, or truncated.
9. Frontend must not show a confusing empty result when AI actually failed.
10. Keep code maintainable, typed, tested, and production-safe.

## Backend expected behavior

`/api/check` should support:
- `options.includeLLM=true`: force AI review.
- `options.includeLLM=false`: local-only quick check.
- no includeLLM with `SHUDDHO_CHECK_STRATEGY=ai_first`: AI-first review.

Response should include:
- suggestions
- correctedText
- documentAssessment
- warnings
- llm_requested
- llm_attempted
- llm_used
- llm_status
- llm_provider
- llm_model
- llm_response_mode
- local_suggestion_count
- ai_suggestion_count
- diagnostics

## AI review behavior

The AI must review the full Bangla text with context, not only isolated words.

It must return:
- spelling corrections
- grammar corrections
- punctuation corrections
- spacing corrections
- word-choice corrections
- clarity corrections
- fluency corrections
- meaning/context corrections
- full corrected text
- document-level assessment

The backend must validate exact spans before showing inline suggestions.

When AI output is truncated, invalid, or unusable, return warnings and diagnostics.

## Frontend expected behavior

The editor UI should be professional and responsive:
- Deep AI Review button.
- Loading state while AI review is running.
- Request cancellation for stale checks.
- Debounced quick local check.
- Clear AI status chip: Ready, Checking, Complete, Warning, Error.
- Suggestion groups: Spelling, Grammar, Clarity, Fluency, Style.
- Corrected text preview.
- Apply, dismiss, accept all.
- Developer diagnostics panel.
- No sticky/stuck UI behavior.

## Suggested validation commands

Backend:
```bash
python -m py_compile services/api/shuddho_api/app.py
python -m py_compile services/api/shuddho_api/llm_provider.py services/api/shuddho_api/llm_gemma.py
python -m pytest tests/test_api_app.py tests/test_frontend_backend_only.py tests/test_suggestion_validation.py -q
```

Frontend:
```bash
npm install
npm run build --workspace @shuddho/web-editor
npm run test --workspace @shuddho/web-editor
```

If a command does not exist, inspect `package.json`, `pyproject.toml`, and tests, then run the closest equivalent command.

## Do not

- Do not commit real API keys.
- Do not remove the local engine completely.
- Do not fake high-quality ML corrector results.
- Do not hide AI provider errors.
- Do not return 200 OK with no explanation when AI failed.

# Shuddho

Shuddho is a Bangla writing assistant with deterministic spelling/rule/dictionary checks and contextual Deep AI Review. The competition application uses the Google Gen AI SDK/API as transport for the pretrained instruction-tuned Gemma 4 model `gemma-4-26b-a4b-it`; it does not call Gemini models and does not claim a fine-tuned Gemma model.

## Development

```bash
uv sync --group dev
uv run pytest -q
npm ci
npm run test --workspace @shuddho/web-editor
npm run build --workspace @shuddho/web-editor
```

Run the API locally without optional ML engines:

```bash
SHUDDHO_ENABLE_LLM=false SHUDDHO_DETECTOR_ENABLED=false SHUDDHO_CORRECTOR_ENABLED=false \
python -m uvicorn services.api.shuddho_api.app:app --host 127.0.0.1 --port 8000
```

The local rules, lexicon, spelling, punctuation, and spacing checks continue to work in this profile. Developers who intentionally need checkpoint engines can install `.[ml]` or build `docker build --target ml-cpu .`; production must not do so.

## Production

See [`DEPLOYMENT.md`](DEPLOYMENT.md) for the exact lightweight Render and Vercel settings. Backend secrets are read from server environment variables only. Never expose `GOOGLE_API_KEY` in a `VITE_*` variable, frontend code, logs, tests, or commits.

Key endpoints are `/health`, `/health/deep`, `/api/llm/debug`, and `/api/check`. AI errors are surfaced through warnings and diagnostics while valid local suggestions are preserved.

## Gemma production contract

Render must use `SHUDDHO_GEMMA_RESPONSE_MODE=function_call`; legacy JSON response modes are local compatibility modes only. Keep `GOOGLE_API_KEY` exclusively in the backend environment and never configure it in Vercel. Safe diagnostics expose both the requested and effective mode so stale deployment configuration is visible.

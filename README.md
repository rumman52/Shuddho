# Shuddho

Shuddho is a global multilingual writing platform evolving into an AI coworker for everyday and professional work. Its existing Bangla rules, spelling, punctuation, spacing, and dictionary engines remain the foundation of the free writing experience.

Writing review uses a configurable DeepSeek adapter. The default is `SHUDDHO_LLM_PROVIDER=deepseek` with `DEEPSEEK_MODEL=deepseek-flash`. Explicit `gemma` configuration remains supported for existing deployments and rollback.

The repository also contains the authenticated coworker foundation: durable tasks and agent runs, Temporal workflows, native artifacts, bounded research, structured memory, and approval-controlled external actions. These capabilities retain their feature flags and live staging/activation gates; repository code does not establish production availability.

The proposed personal-agent redesign covers persistent goals, recurring work, connected reads, isolated browser/code execution, and qualified personal transactions while preserving Shuddho's writing services.

- [Current architecture and personal-agent redesign](docs/ARCHITECTURE.md)
- [Complete personal-agent service catalog](docs/PERSONAL_AGENT_SERVICES.md)
- [Personal-agent implementation and release plan](docs/PERSONAL_AGENT_IMPLEMENTATION.md)
- [Three-part implementation plan](docs/IMPLEMENTATION_PLAN.md)
- [Part 1 changes, configuration, and verification](docs/PART_1_WRITING_FOUNDATION.md)

## Development

```bash
uv lock --check
uv sync --group dev
uv run pytest -q
npm ci
npm run test --workspace @shuddho/web-editor
npm run build --workspace @shuddho/web-editor
```

Optional dependencies are excluded by default, so the lightweight setup does
not need `--no-extra ml`. Use `uv sync --group dev --extra ml` only when the
checkpoint-backed ML engines are intentionally required.

Run the API locally without optional ML engines:

```bash
SHUDDHO_ENABLE_LLM=false SHUDDHO_DETECTOR_ENABLED=false SHUDDHO_CORRECTOR_ENABLED=false \
uv run uvicorn services.api.shuddho_api.app:app --host 127.0.0.1 --port 8000
```

The local rules, lexicon, spelling, punctuation, and spacing checks continue to work in this profile. Developers who intentionally need checkpoint engines can install `.[ml]` or build `docker build --target ml-cpu .`; production must not do so.

## Production

See [`DEPLOYMENT.md`](DEPLOYMENT.md) for lightweight Render and Vercel settings and the staging release gate. Backend secrets are read from server environment variables only. Never expose provider credentials in a `VITE_*` variable, frontend code, logs, or commits.

Key endpoints are `/health`, `/health/deep`, `/api/llm/debug`, and `/api/check`. AI errors are surfaced through warnings and diagnostics while valid local suggestions are preserved.

## Explicit Gemma rollback contract

Render must use `SHUDDHO_GEMMA_RESPONSE_MODE=function_call`; legacy JSON response modes are local compatibility modes only. Keep `GOOGLE_API_KEY` exclusively in the backend environment and never configure it in Vercel. Safe diagnostics expose both the requested and effective mode so stale deployment configuration is visible.

# Shuddho production root-cause report

## Current confirmed live failure (July 31, 2026)

The live backend is healthy and correctly configured for `gemma` with
`gemma-4-26b-a4b-it`. The latency repair exposed the active failure: Gemma completes within its
deadline and returns non-empty output, but JSON MIME output can be malformed and
was rejected as `invalid_json`.

## Repository repair

Production now sends one compact forced `submit_shuddho_review` function call, includes the original text
once, uses offset-only sentence boundaries and compact local hints, explicitly
selects minimal thinking, disables SDK retries, and uses a 40-second provider
budget within the 45/50-second backend and 60-second frontend hierarchy.
Returned JSON still passes Pydantic and exact-span validation. Timeout failures
remain explicit and local deterministic suggestions are preserved.

## Required deployment actions

Render must retain its existing secret, set `SHUDDHO_LLM_PROVIDER=gemma`,
`SHUDDHO_ENABLE_LLM=true`, `GEMMA_MODEL=gemma-4-26b-a4b-it`,
`SHUDDHO_GEMMA_THINKING_LEVEL=minimal`, `SHUDDHO_GEMMA_RESPONSE_MODE=function_call`,
`SHUDDHO_GEMMA_TIMEOUT_SECONDS=40`, `SHUDDHO_LLM_INTERACTIVE_TIMEOUT_SECONDS=45`,
`SHUDDHO_LLM_TOTAL_TIMEOUT_SECONDS=50`, and
`SHUDDHO_LLM_MAX_COMPLETION_TOKENS=1400`, then clear build cache and deploy.
Vercel must set `VITE_COMPETITION_DEMO_MODE=false` and redeploy. Never put the
Google API key in Vercel or client code.

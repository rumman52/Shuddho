# Shuddho production root-cause report

## Current confirmed live failure (July 31, 2026)

The live backend is healthy and correctly configured for `gemma` with
`gemma-4-26b-a4b-it`. The active failure is provider latency: a schema-first
request with a duplicated 5–15K-character prompt exhausts the 30-second Gemma
deadline before producing visible output tokens. SDK timeout exceptions were
also being reported as `network_error`.

## Repository repair

Production now sends one compact JSON MIME request, includes the original text
once, uses offset-only sentence boundaries and compact local hints, explicitly
selects minimal thinking, disables SDK retries, and uses a 40-second provider
budget within the 45/50-second backend and 60-second frontend hierarchy.
Returned JSON still passes Pydantic and exact-span validation. Timeout failures
remain explicit and local deterministic suggestions are preserved.

## Required deployment actions

Render must retain its existing secret, set `SHUDDHO_LLM_PROVIDER=gemma`,
`SHUDDHO_ENABLE_LLM=true`, `GEMMA_MODEL=gemma-4-26b-a4b-it`,
`SHUDDHO_GEMMA_THINKING_LEVEL=minimal`, `SHUDDHO_GEMMA_RESPONSE_MODE=json_mime`,
`SHUDDHO_GEMMA_TIMEOUT_SECONDS=40`, `SHUDDHO_LLM_INTERACTIVE_TIMEOUT_SECONDS=45`,
`SHUDDHO_LLM_TOTAL_TIMEOUT_SECONDS=50`, and
`SHUDDHO_LLM_MAX_COMPLETION_TOKENS=1400`, then clear build cache and deploy.
Vercel must set `VITE_COMPETITION_DEMO_MODE=false` and redeploy. Never put the
Google API key in Vercel or client code.

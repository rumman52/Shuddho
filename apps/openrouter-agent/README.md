# OpenRouter Agent

This workspace is a small server-side OpenRouter agent for local development inside the Shuddho repository.

It follows the modular pattern from OpenRouter's `create-agent` skill:

- standalone agent core with hooks in `src/agent.ts`
- reusable tools in `src/tools.ts`
- headless CLI entrypoint in `src/headless.ts`

## Quickstart

From the repo root:

```bash
npm install
npm run build:agent
npm run start:agent
```

The agent reads `OPENROUTER_API_KEY` from the repo-root `.env`.

Optional attribution variables:

- `OPENROUTER_AGENT_SITE_URL`
- `OPENROUTER_AGENT_TITLE`
- `OPENROUTER_AGENT_MODEL`

This agent is server-side only. The Shuddho web editor and Chrome extension still do not call OpenRouter directly.

# Security and privacy

- The gateway logs request IDs, path, latency, provider, text length, and suggestion counts, not raw full text.
- `/api/events` sanitizes metadata fields such as `text`, `rawText`, `fullText`, and `documentText`.
- Product-improvement consent is represented in preferences and check requests, but MVP memory stores do not send raw text to analytics.
- DLP/privacy preprocessing is an explicit gateway hook before provider calls.
- Local development can run entirely in memory without Postgres or Redis; production should enable auth, durable stores, rate limits, and audit logs.

# Shuddho API

The canonical client contract is the TypeScript gateway `POST /api/check`. Legacy Python `/analyze`, `/rewrite`, and `/tone/analyze` remain available for direct local development.

## `POST /api/check`

Request:

```json
{
  "text": "আমি  আমি ভাত খাই ।",
  "language": "bn",
  "documentId": "demo-document",
  "revision": 3,
  "client": { "surface": "web", "version": "mvp" }
}
```

Response uses `CheckResponse`: request ID, Bangla language, optional normalized text, timings, warnings, and canonical suggestions with stable `id`, reusable `suppressionKey`, `ruleId`, Bangla explanation, provider, source, confidence, and span offsets.

## Other MVP endpoints

- `GET /health` gateway process health.
- `GET /health/deep` gateway-safe deep health. The gateway proxies Python `/health/deep` when reachable so the web editor can show detector/corrector status, and returns a degraded fallback payload instead of a 404 when Python is down.
- `GET /ready` provider readiness, including Python provider readiness when configured.
- `POST /api/rewrite` gateway rewrite proxy to Python when available.
- `POST /api/tone` gateway tone proxy to Python when available.
- `POST /api/feedback` durable suggestion feedback path. The gateway forwards the full payload to Python `POST /feedback` using `SHUDDHO_PYTHON_API_URL` (default `http://127.0.0.1:8000`) and propagates upstream failures.
- `GET /api/preferences`, `PUT /api/preferences` in-memory preference placeholder.
- `POST /api/events` privacy-safe analytics/event ingestion only; raw full text is stripped from metadata.
- `GET /api/documents/:documentId`, `PUT /api/documents/:documentId` in-memory document store.
- `WebSocket /ws/docs/:documentId` MVP revision-based sync.

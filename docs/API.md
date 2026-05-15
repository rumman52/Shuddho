# API

Base URL: `http://localhost:4000`.

## POST /api/check

Validates text and returns normalized suggestions.

```json
{
  "documentId": "demo-document",
  "text": "I has teh draft",
  "revision": 1,
  "goals": ["grammar", "spelling", "style", "tone", "rewrite"]
}
```

## POST /api/rewrite

Returns a mock rewrite suggestion without calling paid AI services.

## POST /api/tone

Returns tone labels and notes.

## GET /api/preferences

Returns current user writing preferences and product-improvement consent state.

## POST /api/events

Ingests product and telemetry events.

## WebSocket /ws/docs/:documentId

Accepts `delta` messages with server-authoritative revision checks.

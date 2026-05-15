# Data Flow

1. The editor stores local text and revision state.
2. Text changes trigger a debounced `POST /api/check` request.
3. The API validates the request, applies auth/privacy/rate-limit middleware, and calls the orchestrator.
4. Providers return normalized suggestions.
5. The client renders underlines and cards.
6. Accept/reject decisions update local state and emit events.
7. WebSocket deltas prepare the document for conflict-safe server-authoritative synchronization.

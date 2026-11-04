# Rukh AI API contract matrix — source inventory

These routes were verified in `services/coworker/api.py` and `apps/web-editor/src/coworker/client.ts`. This is a source-level inventory, not a live staging contract test.

| Operation | HTTP contract | Behavior/evidence |
|---|---|---|
| Runtime capability manifest | `GET /api/v1/runtime-manifest` | Reports whether conversation replies are enabled |
| List conversations | `GET /api/v1/conversations` | Owner-scoped conversation list |
| Create conversation | `POST /api/v1/conversations` | Idempotency key and created resource |
| Read conversation | `GET /api/v1/conversations/{id}` | Owner-scoped conversation metadata |
| Rename conversation | `PATCH /api/v1/conversations/{id}` | Expected update timestamp contract |
| Delete conversation | `DELETE /api/v1/conversations/{id}` | Deletes/redacts owned conversation |
| Append message | `POST /api/v1/conversations/{id}/messages` | Persists user message |
| Read message history | `GET /api/v1/conversations/{id}/messages` | Cursor-paginated history |
| Request assistant reply | `POST /api/v1/conversations/{id}/messages/{message_id}/reply` | JSON reply state; provider call is non-streaming |
| Explicit Agent dispatch | `POST /api/v1/conversations/{id}/messages/{message_id}/dispatch` | Separate 202 dispatch operation |
| Cancel Agent run | `POST /api/v1/conversations/{id}/messages/{message_id}/cancel` | Cancels the linked execution where supported |
| Read conversation activity | `GET /api/v1/conversations/{id}/activity` | Cursor-paginated activity records |

The API also exposes SSE for task progress at `/api/v1/tasks/{id}/events?stream=true`. It must not be conflated with assistant-reply streaming. Verify the live OpenAPI/runtime manifest and exact staging version before relying on these contracts externally.

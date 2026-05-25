from __future__ import annotations

from typing import Any, Protocol


class LlmReviewProvider(Protocol):
    def review(
        self,
        text: str,
        local_suggestions: list[dict[str, Any]],
        candidates: list[dict[str, Any]],
        request_id: str,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        ...

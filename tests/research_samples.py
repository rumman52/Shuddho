"""Explicitly simulated search transport. Never imported by production code."""
from datetime import datetime, timezone

import httpx

from services.coworker.research import TavilyResearchProvider

PAGE_TEXT = "The team completed 12 reviews. This is simulated test evidence, not an actual organization or report. "


def search_data():
    return {"results": [{"url": "https://example.org/project-update", "title": "Example project update",
                         "raw_content": PAGE_TEXT, "content": "A search snippet must never be evidence.",
                         "published_date": datetime.now(timezone.utc).isoformat()}], "usage": {"credits": 1}}


class SimulatedResearch(TavilyResearchProvider):
    def __init__(self, settings):
        from dataclasses import replace
        self.calls = 0
        def transport(_request):
            self.calls += 1
            return httpx.Response(200, json=search_data())
        super().__init__(replace(settings, search_api_key="fixture-only-search-key"), httpx.MockTransport(transport))

"""One bounded search request. Only the fixed provider origin receives traffic.

The provider retrieves page text; our worker never fetches a result URL. Search
snippets/answers are not evidence. URLs and dates are provenance, not truth scores.
"""
from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import re
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Protocol
from urllib.parse import unquote, urlsplit, urlunsplit

import httpx

from .config import Settings
from .errors import CoworkerError
from .schemas import ResearchOptions, ResearchPackage

SEARCH_ENDPOINT = "https://api.tavily.com/search"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_PAGE_CHARS = 3000
RANGE_DAYS = {"day": 1, "week": 7, "month": 31, "year": 366}


def public_source_url(value: str) -> str:
    """Conservative link validation, not a DNS/SSRF boundary. Never fetch this URL."""
    if not isinstance(value, str) or len(value) > 2048 or re.search(r"[\s\\\x00-\x1f\x7f]", value):
        raise ValueError("Invalid source URL")
    parts = urlsplit(value)
    if parts.scheme not in {"https", "http"} or not parts.hostname or parts.username is not None or parts.password is not None:
        raise ValueError("Invalid source origin")
    host = parts.hostname.encode("idna").decode("ascii").lower().rstrip(".")
    if parts.port not in {None, 443 if parts.scheme == "https" else 80}:
        raise ValueError("Nonstandard source port")
    if not re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{1,62}", host):
        raise ValueError("Invalid source hostname")
    if host.endswith((".localhost", ".local", ".internal", ".lan", ".home", ".invalid", ".test", ".onion")):
        raise ValueError("Local source hostname")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("IP source URLs are not supported")
    if re.search(r"[\x00-\x1f\x7f\\]", unquote(value)):
        raise ValueError("Invalid source characters")
    return urlunsplit((parts.scheme, host, parts.path or "/", parts.query, ""))


def clean_text(value: str) -> str:
    return unicodedata.normalize("NFC", re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value)).strip()


def source_date(value) -> datetime | None:
    if not isinstance(value, str) or len(value) > 100:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None
    return (parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed).astimezone(timezone.utc)


@dataclass
class ResearchResult:
    sources: list[dict]
    metadata: dict
    credits: int | None = None


class ResearchProvider(Protocol):
    async def retrieve(self, options: ResearchOptions) -> ResearchResult: ...


class SearchFailure(CoworkerError):
    def __init__(self, code, message, credits=None):
        super().__init__(code, message, 502)
        self.credits = credits


class TavilyResearchProvider:
    def __init__(self, settings: Settings, transport=None):
        self.settings, self.transport = settings, transport

    def configured(self):
        if self.settings.search_provider != "tavily" or not self.settings.search_api_key:
            raise CoworkerError("search_not_configured", "Web research is temporarily unavailable. Please try again later.", 503)

    async def retrieve(self, options: ResearchOptions) -> ResearchResult:
        self.configured()
        started = time.monotonic()
        # Only the explicit query is public. Never derive queries from private
        # notes, document contents, model output or a retrieved page's instructions.
        payload = {"query": options.query, "search_depth": "basic", "max_results": 5,
                   "topic": "general", "auto_parameters": False, "include_answer": False,
                   "include_raw_content": "text", "include_images": False,
                   "include_published_date": True, "include_usage": True}
        if options.time_range != "any":
            payload.update(time_range=options.time_range, filter_by_published_date=True)
        try:
            async with asyncio.timeout(self.settings.search_timeout_seconds):
                async with httpx.AsyncClient(transport=self.transport, follow_redirects=False, trust_env=False,
                                            timeout=self.settings.search_timeout_seconds) as client:
                    async with client.stream("POST", SEARCH_ENDPOINT, json=payload,
                                             headers={"Authorization": "Bearer " + self.settings.search_api_key}) as response:
                        if response.status_code != 200:
                            raise SearchFailure("search_unavailable", "The search service could not finish. Please try a new task later.")
                        body = bytearray()
                        async for chunk in response.aiter_bytes():
                            if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                                raise SearchFailure("search_response_limit", "The search response was too large. Try a narrower query.")
                            body.extend(chunk)
            data = json.loads(body)
            if not isinstance(data, dict) or not isinstance(data.get("results"), list) or len(data["results"]) > 5:
                raise ValueError("Invalid search shape")
        except (httpx.HTTPError, TimeoutError):
            raise SearchFailure("search_unavailable", "The search service did not respond in time. Please try a new task later.") from None
        except (ValueError, TypeError):
            raise SearchFailure("search_invalid", "The search response could not be read. Please try a new task later.") from None
        result = self.parse(data, options)
        result.metadata["latency_ms"] = int((time.monotonic() - started) * 1000)
        request_id = data.get("request_id")
        if isinstance(request_id, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,100}", request_id):
            result.metadata["request_id"] = request_id
        return result

    @staticmethod
    def parse(data: dict, options: ResearchOptions) -> ResearchResult:
        now = datetime.now(timezone.utc)
        sources, seen = [], set()
        usage = data.get("usage")
        credits = usage.get("credits") if isinstance(usage, dict) else None
        credits = credits if type(credits) is int and 0 <= credits <= 100 else None
        for item in data["results"]:
            if not isinstance(item, dict) or not isinstance(item.get("raw_content"), str):
                continue
            try:
                url = public_source_url(item.get("url"))
            except (ValueError, TypeError, UnicodeError):
                continue
            if url in seen:
                continue
            seen.add(url)
            date = source_date(item.get("published_date"))
            if date and date > now + timedelta(days=1):
                date = None  # Future provider dates cannot establish freshness.
            if options.time_range != "any" and (date is None or date < now - timedelta(days=RANGE_DAYS[options.time_range])):
                continue
            text = clean_text(item["raw_content"])
            if len(text) < 80:
                continue  # An empty page or a search snippet is not a fetched page.
            excerpt = text[:MAX_PAGE_CHARS]
            label = item.get("title") if isinstance(item.get("title"), str) else urlsplit(url).hostname
            sources.append({"id": f"web-{len(sources) + 1}", "kind": "web", "url": url,
                            "label": " ".join(clean_text(label).split())[:180] or urlsplit(url).hostname,
                            "text": excerpt, "sha256": hashlib.sha256(excerpt.encode()).hexdigest(),
                            "retrieved_at": now.isoformat(), "source_date": date.isoformat() if date else None,
                            "date_basis": "provider_estimate", "provider": "tavily", "truncated": len(text) > len(excerpt)})
        if not sources:
            raise SearchFailure("research_no_evidence", "No readable pages matched this search and date range. Broaden the query or date range and try again.", credits)
        return ResearchResult(sources, {"query": options.query, "time_range": options.time_range, "provider": "tavily",
                                      "retrieved_at": now.isoformat(), "skipped_results": len(data["results"]) - len(sources)}, credits)


def validate_evidence(draft: ResearchPackage, sources: list[dict]) -> None:
    """Reject invented references/quotes. This does not prove semantic entailment."""
    by_id = {source["id"]: source for source in sources if source.get("kind") == "web"}
    used_quotes: dict[str, set[str]] = {}
    for finding in draft.findings:
        for citation in finding.citations:
            source = by_id.get(citation.source_id)
            quote = " ".join(unicodedata.normalize("NFC", citation.quote).split())
            if not source or quote not in " ".join(source["text"].split()):
                raise ValueError("A citation does not match the retrieved evidence")
            if public_source_url(source["url"]) != source["url"]:
                raise ValueError("Invalid source URL")
            used_quotes.setdefault(citation.source_id, set()).add(quote)
    if any(sum(map(len, quotes)) > 400 for quotes in used_quotes.values()):
        raise ValueError("Too much quoted source text")

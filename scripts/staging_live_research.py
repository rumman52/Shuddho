from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx

from scripts.staging_api_exercise import env_secret, require_https_base
from services.coworker.config import Settings
from services.coworker.research import TavilyResearchProvider, public_source_url, validate_evidence
from services.coworker.schemas import ResearchOptions, ResearchPackage


TERMINAL = {"completed", "failed", "cancelled", "needs_input"}


class ResearchValidationFailure(RuntimeError):
    pass


def passed(evidence: str) -> dict:
    return {"status": "passed", "evidence": evidence}


def require_guard() -> None:
    if os.environ.get("SHUDDHO_STAGING_ALLOW_LIVE_RESEARCH_EXERCISE", "").lower() != "true":
        raise ResearchValidationFailure(
            "Set SHUDDHO_STAGING_ALLOW_LIVE_RESEARCH_EXERCISE=true only in controlled staging."
        )


def validate_live_source(source: dict) -> None:
    if source.get("provider") != "tavily" or source.get("kind") != "web":
        raise ResearchValidationFailure("Live Tavily source metadata is incomplete.")
    url = source.get("url")
    if not isinstance(url, str) or public_source_url(url) != url:
        raise ResearchValidationFailure("Live Tavily source URL did not pass Shuddho validation.")
    text = source.get("text")
    if not isinstance(text, str) or len(text) < 80 or len(text) > 3000:
        raise ResearchValidationFailure("Live Tavily source did not contain bounded readable page text.")
    if source.get("sha256") != hashlib.sha256(text.encode()).hexdigest():
        raise ResearchValidationFailure("Live Tavily source SHA-256 did not match retained page text.")
    try:
        datetime.fromisoformat(str(source["retrieved_at"]).replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError):
        raise ResearchValidationFailure("Live Tavily source retrieval timestamp is invalid.") from None
    source_date = source.get("source_date")
    if source_date is not None:
        try:
            datetime.fromisoformat(str(source_date).replace("Z", "+00:00"))
        except ValueError:
            raise ResearchValidationFailure("Live Tavily source date is invalid.") from None


def citation_probe(sources: list[dict]) -> None:
    source = sources[0]
    words = source["text"].split()
    quote = ""
    for size in range(min(30, len(words)), 3, -1):
        candidate = " ".join(words[:size])
        if 20 <= len(candidate) <= 200:
            quote = candidate
            break
    if not quote:
        raise ResearchValidationFailure("Live source did not contain a bounded citation excerpt.")
    draft = ResearchPackage.model_validate({
        "kind": "research",
        "output_language": "en",
        "title": "Synthetic live research validation",
        "labels": {
            "sources": "Sources",
            "evidence": "Evidence",
            "retrieved": "Retrieved",
            "source_date": "Source date",
            "undated": "Undated",
            "gaps": "Gaps",
        },
        "findings": [{
            "heading": "Provider evidence",
            "text": "This synthetic finding exists only to exercise exact-quote validation.",
            "citations": [{"source_id": source["id"], "quote": quote}],
        }],
        "missing_information": [],
    })
    validate_evidence(draft, sources)


async def direct_probe(settings: Settings, query: str, time_range: str) -> dict:
    if not settings.research_services_enabled:
        raise ResearchValidationFailure("SHUDDHO_RESEARCH_SERVICES_ENABLED must be true in staging.")
    if settings.search_provider != "tavily" or not settings.search_api_key:
        raise ResearchValidationFailure("Tavily must be configured with a backend-only API key.")
    result = await TavilyResearchProvider(settings).retrieve(
        ResearchOptions(query=query, time_range=time_range)
    )
    if not 1 <= len(result.sources) <= 5:
        raise ResearchValidationFailure("Live Tavily returned an unexpected number of usable sources.")
    for source in result.sources:
        validate_live_source(source)
    citation_probe(result.sources)
    metadata = result.metadata
    if metadata.get("provider") != "tavily" or metadata.get("query") != query:
        raise ResearchValidationFailure("Live Tavily metadata did not preserve the explicit public query.")
    latency = metadata.get("latency_ms")
    if not isinstance(latency, int) or latency < 0:
        raise ResearchValidationFailure("Live Tavily latency metadata is missing.")
    if result.credits is not None and (not isinstance(result.credits, int) or not 0 <= result.credits <= 100):
        raise ResearchValidationFailure("Live Tavily credit metadata is invalid.")
    return {
        "sources": len(result.sources),
        "dated_sources": sum(1 for item in result.sources if item.get("source_date")),
        "credits": result.credits,
        "latency_ms": latency,
        "request_id_present": bool(metadata.get("request_id")),
    }


def auth(token: str) -> dict[str, str]:
    return {"Authorization": "Bearer " + token}


def request_json(response: httpx.Response, label: str, expected: int = 200) -> dict:
    if response.status_code != expected:
        raise ResearchValidationFailure(
            f"{label} returned HTTP {response.status_code}; expected {expected}."
        )
    try:
        value = response.json()
    except ValueError:
        raise ResearchValidationFailure(f"{label} did not return JSON.") from None
    if not isinstance(value, dict):
        raise ResearchValidationFailure(f"{label} returned an unexpected JSON shape.")
    return value


def validate_task_result(value: dict) -> None:
    if value.get("state") != "completed":
        raise ResearchValidationFailure(
            f"Live Research task ended in state {value.get('state')!r}; a release-gate pass requires completed."
        )
    if value.get("workflow_version") != "work_research_v1":
        raise ResearchValidationFailure("Live task did not use the research workflow version.")
    research = value.get("research")
    if not isinstance(research, dict) or research.get("provider") != "tavily":
        raise ResearchValidationFailure("Live task did not preserve Tavily research provenance.")
    sources = value.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ResearchValidationFailure("Live task returned no research sources.")
    source_ids = set()
    for source in sources:
        if not isinstance(source, dict):
            raise ResearchValidationFailure("Live task source metadata is invalid.")
        if "text" in source:
            raise ResearchValidationFailure("Completed task exposed retained raw page text.")
        source_id = source.get("id")
        if not isinstance(source_id, str) or not source_id.startswith("web-"):
            raise ResearchValidationFailure("Live task source ID is invalid.")
        if source.get("provider") != "tavily":
            raise ResearchValidationFailure("Live task source provider is invalid.")
        if not isinstance(source.get("url"), str) or public_source_url(source["url"]) != source["url"]:
            raise ResearchValidationFailure("Live task source URL is invalid.")
        source_ids.add(source_id)

    draft = value.get("draft")
    if not isinstance(draft, dict) or draft.get("kind") != "research":
        raise ResearchValidationFailure("Live Research task returned no typed research draft.")
    findings = draft.get("findings")
    if not isinstance(findings, list) or not findings:
        raise ResearchValidationFailure("Live Research task produced no cited findings.")
    citation_count = 0
    for finding in findings:
        citations = finding.get("citations") if isinstance(finding, dict) else None
        if not isinstance(citations, list) or not citations:
            raise ResearchValidationFailure("A live research finding had no citations.")
        for citation in citations:
            if not isinstance(citation, dict) or citation.get("source_id") not in source_ids:
                raise ResearchValidationFailure("Live research citation referenced an unknown source.")
            quote = citation.get("quote")
            if not isinstance(quote, str) or not 20 <= len(quote) <= 200:
                raise ResearchValidationFailure("Live research citation quote violated bounds.")
            citation_count += 1
    if citation_count < 1:
        raise ResearchValidationFailure("Live Research task produced no citations.")

    usage = value.get("usage")
    search_usage = usage.get("search") if isinstance(usage, dict) else None
    if not isinstance(search_usage, dict):
        raise ResearchValidationFailure("Live Research task has no search accounting evidence.")
    if search_usage.get("state") not in {"completed", "accounted"} and search_usage.get("actual_credits") is None:
        raise ResearchValidationFailure("Live Research task search accounting is incomplete.")
    artifacts = value.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) < 3:
        raise ResearchValidationFailure("Live Research task did not produce the expected cited artifacts.")


def verify_download(client: httpx.Client, token: str, artifact: dict) -> None:
    artifact_id = artifact.get("id")
    if not isinstance(artifact_id, str) or not artifact_id:
        raise ResearchValidationFailure("Live artifact metadata did not include an id.")
    route = f"/api/v1/artifacts/{artifact_id}/download"
    value = request_json(client.get(route, headers=auth(token)), "research artifact download")
    if value.get("url"):
        response = httpx.get(value["url"], timeout=20, follow_redirects=False)
    elif value.get("content_path"):
        response = client.get(str(value["content_path"]), headers=auth(token))
    else:
        raise ResearchValidationFailure("Research artifact download returned no authorized path.")
    if response.status_code != 200 or not response.content:
        raise ResearchValidationFailure(
            f"Research artifact content returned HTTP {response.status_code} or empty bytes."
        )
    expected_sha = artifact.get("sha256")
    if isinstance(expected_sha, str) and hashlib.sha256(response.content).hexdigest() != expected_sha:
        raise ResearchValidationFailure("Downloaded Research artifact SHA-256 did not match metadata.")


def api_probe(base_url: str, token: str, query: str, time_range: str, timeout_seconds: int) -> dict:
    with httpx.Client(base_url=base_url, timeout=20, follow_redirects=False) as client:
        payload = {
            "skill_id": "research",
            "instruction": "Prepare a short synthetic live-provider validation report using cited evidence only.",
            "notes": "Synthetic staging probe only. No customer data.",
            "document_ids": [],
            "output_language": "en",
            "research": {"query": query, "time_range": time_range},
        }
        created = request_json(
            client.post(
                "/api/v1/tasks",
                headers=auth(token) | {"Idempotency-Key": "live-tavily-" + uuid.uuid4().hex},
                json=payload,
            ),
            "create live Research task",
            expected=202,
        )
        task_id = created.get("id")
        if not isinstance(task_id, str) or not task_id:
            raise ResearchValidationFailure("Live Research task creation returned no task id.")

        deadline = time.monotonic() + max(60, timeout_seconds)
        value = created
        while time.monotonic() < deadline:
            value = request_json(
                client.get(f"/api/v1/tasks/{task_id}", headers=auth(token)),
                "live Research task status",
            )
            if value.get("state") in TERMINAL:
                break
            time.sleep(2)
        else:
            client.post(f"/api/v1/tasks/{task_id}/cancel", headers=auth(token))
            raise ResearchValidationFailure("Live Research task did not finish before the staging timeout.")

        validate_task_result(value)
        artifacts = value["artifacts"]
        for artifact in artifacts:
            verify_download(client, token, artifact)
        return {
            "task_id": task_id,
            "sources": len(value["sources"]),
            "findings": len(value["draft"]["findings"]),
            "artifacts": len(artifacts),
            "accounted_tokens": value.get("usage", {}).get("accounted_tokens"),
            "actual_search_credits": value.get("usage", {}).get("search", {}).get("actual_credits"),
        }


def merge_evidence(base_evidence: Path | None, update: dict) -> dict:
    base = {}
    if base_evidence:
        value = json.loads(base_evidence.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ResearchValidationFailure("Base staging evidence must be a JSON object.")
        base.update(value)
    base.update(update)
    return base


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate live Tavily retrieval and the deployed Shuddho Research workflow."
    )
    parser.add_argument("--query", default="Python programming language official documentation")
    parser.add_argument("--time-range", choices=["any", "day", "week", "month", "year"], default="any")
    parser.add_argument("--task-timeout", type=int, default=240)
    parser.add_argument("--base-evidence", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    require_guard()
    settings = Settings.from_env()
    base_url = require_https_base(env_secret("SHUDDHO_STAGING_API_BASE_URL"))
    token = env_secret("SHUDDHO_STAGING_TOKEN_A")
    try:
        direct = asyncio.run(direct_probe(settings, args.query, args.time_range))
        task = api_probe(base_url, token, args.query, args.time_range, args.task_timeout)
        evidence = merge_evidence(
            args.base_evidence,
            {
                "research": passed(
                    f"live Tavily adapter + deployed Research workflow passed; "
                    f"sources={task['sources']}; findings={task['findings']}; artifacts={task['artifacts']}"
                )
            },
        )
        args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({
            "written": str(args.output),
            "checks": {"research": "passed"},
            "direct": direct,
            "task": task,
        }, indent=2))
    except (ResearchValidationFailure, httpx.HTTPError, OSError, ValueError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, indent=2))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()

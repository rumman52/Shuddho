"""Research provenance, private-query boundary, paid-call recovery and native links."""
import asyncio
import copy
import hashlib
import io
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import httpx
import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("temporalio")

from docx import Document
from pypdf import PdfReader

from test_coworker import container, signed_client, account
from coworker_samples import WorkModel, work_draft
from research_samples import PAGE_TEXT, SimulatedResearch, search_data
from services.coworker.drafting import DeepSeekDraftModel, DraftFailure
from services.coworker.errors import CoworkerError
from services.coworker.research import MAX_PAGE_CHARS, MAX_RESPONSE_BYTES, SEARCH_ENDPOINT, SearchFailure, TavilyResearchProvider, public_source_url, validate_evidence
from services.coworker.runner import DocumentRunner
from services.coworker.schemas import ResearchOptions, TaskCreate
from services.coworker.worker import Activities, Dispatcher
from services.coworker.workflow import ResearchWorkflow


def enable_research(container):
    container.settings = replace(container.settings, research_services_enabled=True)
    container.repository.settings = container.settings


def research_request(**kwargs):
    return TaskCreate(skill_id="research", instruction="Compare the evidence in a short report.",
                      notes="Private context not for web search.", research={"query": "public project reviews", "time_range": "week"}, **kwargs)


def create_research(container, **kwargs):
    enable_research(container)
    return container.repository.create_task(account(container), research_request(**kwargs), "research-key")[0]


def provider(container, handler):
    return TavilyResearchProvider(replace(container.settings, search_api_key="fixture-only-search-key"), httpx.MockTransport(handler))


def test_research_catalog_request_idempotency_isolation_and_flag_rollback(container, signed_client):
    client, headers = signed_client
    auth = headers() | {"Idempotency-Key": "research-api-key"}
    payload = research_request().model_dump(mode="json")
    assert client.post("/api/v1/tasks", headers=auth, json=payload).status_code == 409
    assert client.get("/api/v1/me", headers=headers()).json()["usage"]["tasks_today"] == 0
    enable_research(container)
    assert [item["id"] for item in client.get("/api/v1/skills", headers=headers()).json()["skills"]] == ["report_email", "research"]
    created = client.post("/api/v1/tasks", headers=auth, json=payload).json()
    assert created["input"]["research"] == payload["research"]
    changed = payload | {"research": {"query": "a different query", "time_range": "week"}}
    assert client.post("/api/v1/tasks", headers=auth, json=changed).status_code == 409
    changed["research"] = {"query": payload["research"]["query"], "time_range": "any"}
    assert client.post("/api/v1/tasks", headers=auth, json=changed).status_code == 409
    for mutation in [{"research": None}, {"skill_id": "email"}, {"research": {"query": "ab"}},
                     {"research": {"query": "safe query", "url": "http://localhost"}}]:
        assert client.post("/api/v1/tasks", headers=auth, json=payload | mutation).status_code == 422
    assert client.get(f'/api/v1/tasks/{created["id"]}', headers=headers("bob")).status_code == 404
    assert client.get(f'/api/v1/tasks/{created["id"]}/events', headers=headers("bob")).status_code == 404
    container.settings = replace(container.settings, research_services_enabled=False)
    container.repository.settings = container.settings
    replay = client.post("/api/v1/tasks", headers=auth, json=payload)
    assert replay.status_code == 202 and replay.json()["id"] == created["id"]
    assert client.post("/api/v1/tasks", headers=headers() | {"Idempotency-Key": "new-research-key"}, json=payload).status_code == 409


def test_fixed_search_origin_receives_only_explicit_public_query(container):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=search_data())
    task = create_research(container)
    runner = DocumentRunner(container, WorkModel(), research=provider(container, handler))
    async def run():
        await runner.phase(task["id"], "extract")
        await runner.phase(task["id"], "research")
    asyncio.run(run())
    assert len(calls) == 1 and str(calls[0].url) == SEARCH_ENDPOINT
    payload = json.loads(calls[0].content)
    assert payload["query"] == "public project reviews" and payload["max_results"] == 5
    assert payload["time_range"] == "week" and payload["filter_by_published_date"] is True
    assert payload["include_answer"] is False and payload["auto_parameters"] is False
    assert payload["include_raw_content"] == "text" and payload["search_depth"] == "basic"
    assert "Private context" not in calls[0].content.decode() and "Compare the evidence" not in calls[0].content.decode()
    saved = container.repository.step(task["id"], "research")
    source = saved["sources"][0]
    assert source["text"] == PAGE_TEXT.strip() and source["sha256"] == hashlib.sha256(source["text"].encode()).hexdigest()
    assert "snippet" not in source["text"]
    model = DeepSeekDraftModel(container.settings, skill_id="research")
    prompt = model.messages(research_request().model_dump(), saved["sources"])
    assert "untrusted data" in prompt[0]["content"] and "exact quote" in prompt[0]["content"]
    assert "there are no additional tools" in prompt[0]["content"].lower()


@pytest.mark.parametrize("url", ["javascript:alert(1)", "file:///etc/passwd", "http://127.0.0.1/", "http://[::1]/", "http://2130706433/",
                                    "http://169.254.169.254/latest/meta-data", "https://localhost/", "https://service.internal/",
                                    "https://example.org:8443/", "https://user:password@example.org/", "https://example.org\\@localhost/",
                                    "https://example.org/%0aheader", "https://example.org\n/", "//example.org/", "https://%31%32%37.0.0.1/"])
def test_unsafe_source_links_rejected(url):
    with pytest.raises(ValueError):
        public_source_url(url)


def test_retrieval_ignores_snippets_duplicates_bad_links_and_wrong_dates(container):
    data = search_data()
    good = data["results"][0]
    data["results"] = [good, good | {"url": good["url"] + "#section"}, good | {"raw_content": None},
                       good | {"url": "http://127.0.0.1/private"}, good | {"url": "https://example.net/old", "published_date": "2001-01-01"}]
    result = asyncio.run(provider(container, lambda _: httpx.Response(200, json=data)).retrieve(ResearchOptions(query="test query", time_range="week")))
    assert len(result.sources) == 1 and result.metadata["skipped_results"] == 4
    for date in [None, "invalid date", (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()]:
        data["results"] = [good | {"published_date": date}]
        with pytest.raises(SearchFailure) as error:
            asyncio.run(provider(container, lambda _: httpx.Response(200, json=data)).retrieve(ResearchOptions(query="test query", time_range="week")))
        assert error.value.code == "research_no_evidence" and error.value.credits == 1
        result = asyncio.run(provider(container, lambda _: httpx.Response(200, json=data)).retrieve(ResearchOptions(query="test query")))
        assert result.sources[0]["source_date"] is None


def test_truncated_source_quotes_and_reference_validation(container):
    data = search_data()
    data["results"][0]["raw_content"] = PAGE_TEXT * 50 + "This evidence is beyond the retained excerpt."
    result = TavilyResearchProvider.parse(data, ResearchOptions(query="test query"))
    assert len(result.sources[0]["text"]) == MAX_PAGE_CHARS and result.sources[0]["truncated"] is True
    valid = work_draft("research")
    validate_evidence(valid, result.sources)
    for source_id, quote in [("web-2", "The team completed 12 reviews."),
                             ("web-1", "The team completed 99 reviews."),
                             ("web-1", "This evidence is beyond the retained excerpt.")]:
        bad = copy.deepcopy(valid)
        bad.findings[0].citations[0].source_id = source_id
        bad.findings[0].citations[0].quote = quote
        with pytest.raises(ValueError):
            validate_evidence(bad, result.sources)


@pytest.mark.parametrize("response,code", [
    (httpx.Response(302, headers={"Location": "http://169.254.169.254/private"}), "search_unavailable"),
    (httpx.Response(429, text="secret provider diagnostics"), "search_unavailable"),
    (httpx.Response(200, text="not json"), "search_invalid"),
    (httpx.Response(200, json={"results": {}}), "search_invalid"),
    (httpx.Response(200, json={"results": []}), "research_no_evidence"),
    (httpx.Response(200, content=b"x" * (MAX_RESPONSE_BYTES + 1)), "search_response_limit"),
])
def test_provider_failure_is_bounded_sanitized_and_never_fabricates_results(container, response, code):
    seen = []
    def handler(request):
        seen.append(str(request.url))
        return response
    with pytest.raises(SearchFailure) as error:
        asyncio.run(provider(container, handler).retrieve(ResearchOptions(query="test query")))
    assert error.value.code == code and "secret" not in str(error.value)
    assert seen == [SEARCH_ENDPOINT]


def test_search_total_timeout_bounds_a_slow_response_body(container):
    class Slow(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'{"results":'
            await asyncio.sleep(1)
            yield b"[]}"
    search = TavilyResearchProvider(replace(container.settings, search_api_key="fixture", search_timeout_seconds=.03),
                                   httpx.MockTransport(lambda _: httpx.Response(200, stream=Slow())))
    with pytest.raises(SearchFailure) as error:
        asyncio.run(search.retrieve(ResearchOptions(query="test query")))
    assert error.value.code == "search_unavailable"


@pytest.mark.parametrize("language", ["en", "bn", "ar"])
def test_research_resumes_with_owned_native_citations_and_discards_raw_pages(container, language):
    task = create_research(container, output_language=language)
    search, model = SimulatedResearch(container.settings), WorkModel()
    runner = DocumentRunner(container, model, research=search)
    async def scenario():
        await runner.phase(task["id"], "extract")
        await runner.phase(task["id"], "research")
        resumed = DocumentRunner(container, model, research=search)
        await resumed.run_for_test(task["id"])
        await resumed.run_for_test(task["id"])
    asyncio.run(scenario())
    value = container.repository.get_task(account(container), task["id"])
    assert value["state"] == "completed" and search.calls == model.calls == 1
    assert value["research"]["query"] == "public project reviews" and value["usage"]["search"]["actual_credits"] == 1
    assert all("text" not in source for source in container.repository.step(task["id"], "research")["sources"])
    assert all("text" not in source for source in value["sources"])
    assert len(value["artifacts"]) == 4
    for artifact in value["artifacts"]:
        owned = container.repository.artifact(account(container), artifact["id"])
        body = container.storage.get(owned["object_key"], owned["byte_size"])
        if artifact["filename"].endswith(".docx"):
            word = Document(io.BytesIO(body))
            assert "https://example.org/project-update" in [rel.target_ref for rel in word.part.rels.values() if rel.is_external]
        elif artifact["filename"].endswith(".pdf"):
            pdf = PdfReader(io.BytesIO(body))
            urls = [item.get_object().get("/A", {}).get("/URI") for page in pdf.pages for item in page.get("/Annots", [])]
            assert "https://example.org/project-update" in urls
        elif artifact["filename"].endswith(".txt"):
            assert "https://example.org/project-update" in body.decode() and "The team completed 12 reviews." in body.decode()
        else:
            assert "raw_content" not in body.decode() and "https://example.org/project-update" in body.decode()
        with pytest.raises(CoworkerError):
            container.repository.artifact(account(container, "bob"), artifact["id"])


def test_invented_evidence_cannot_publish_and_known_model_usage_is_charged(container):
    task = create_research(container)
    class WrongEvidence(WorkModel):
        async def generate(self, *args):
            result = await super().generate(*args)
            result.draft.findings[0].citations[0].quote = "The team completed 999 reviews."
            return result
    with pytest.raises(DraftFailure):
        asyncio.run(DocumentRunner(container, WrongEvidence(), research=SimulatedResearch(container.settings)).run_for_test(task["id"]))
    value = container.repository.get_task(account(container), task["id"])
    assert value["state"] == "failed" and not value["artifacts"] and value["draft"] is None
    assert value["usage"]["accounted_tokens"] == 220
    assert value["usage"]["search"]["actual_credits"] == 1
    assert "text" not in container.repository.step(task["id"], "research")["sources"][0]


def test_missing_search_result_is_not_retried_or_replaced_with_a_model_guess(container):
    task = create_research(container)
    container.repository.reserve_search(task["id"])  # Simulate process loss before checkpoint.
    search, model = SimulatedResearch(container.settings), WorkModel()
    with pytest.raises(CoworkerError) as error:
        asyncio.run(DocumentRunner(container, model, research=search).run_for_test(task["id"]))
    assert error.value.code == "search_outcome_unknown"
    value = container.repository.get_task(account(container), task["id"])
    assert value["state"] == "failed" and search.calls == model.calls == 0
    assert value["usage"]["search"]["accounted_credits"] == 1


def test_search_only_task_routes_to_new_workflow_and_rejects_work_entry(container):
    task = create_research(container)
    class Client:
        calls = []
        async def start_workflow(self, workflow, task_id, **kwargs):
            self.calls.append((workflow, task_id))
    client = Client()
    asyncio.run(Dispatcher(container, client).tick())
    assert client.calls == [(ResearchWorkflow.run, task["id"])]
    runner = DocumentRunner(container, WorkModel(), research=SimulatedResearch(container.settings))
    with pytest.raises(CoworkerError):
        asyncio.run(Activities(runner).checked_phase({"task_id": task["id"], "phase": "draft"}, legacy=False))
    assert runner.model.calls == 0


def test_unconfigured_search_cannot_spend_and_unsupported_adapter_fails_closed(container):
    task = create_research(container)
    with pytest.raises(CoworkerError) as error:
        asyncio.run(DocumentRunner(container, WorkModel()).run_for_test(task["id"]))
    assert error.value.code == "search_not_configured"
    assert container.repository.step(task["id"], "search_attempt") is None
    with pytest.raises(ValueError):
        replace(container.settings, search_provider="unknown", search_api_key="fixture").validate()
    assert "fixture-secret" not in repr(replace(container.settings, search_api_key="fixture-secret"))


def test_insufficient_evidence_produces_a_needs_input_report_without_made_up_findings(container):
    task = create_research(container)
    class EvidenceGap(WorkModel):
        async def generate(self, *args):
            result = await super().generate(*args)
            result.draft.findings = []
            result.draft.missing_information = ["The retrieved pages do not establish the requested comparison. Please narrow the topic."]
            return result
    asyncio.run(DocumentRunner(container, EvidenceGap(), research=SimulatedResearch(container.settings)).run_for_test(task["id"]))
    value = container.repository.get_task(account(container), task["id"])
    assert value["state"] == "needs_input" and value["draft"]["findings"] == [] and len(value["artifacts"]) == 4

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

import pytest

pytest.importorskip("sqlalchemy", reason="Install the coworker extra for live research staging tests")

from scripts import staging_live_research as live


def source():
    text = (
        "Python is a programming language that lets you work quickly and integrate systems effectively. "
        "This synthetic fixture is long enough to exercise retained page evidence validation safely."
    )
    return {
        "id": "web-1",
        "kind": "web",
        "url": "https://www.python.org/about/",
        "label": "Python",
        "text": text,
        "sha256": hashlib.sha256(text.encode()).hexdigest(),
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "source_date": None,
        "date_basis": "provider_estimate",
        "provider": "tavily",
        "truncated": False,
    }


def test_validate_live_source_accepts_bounded_tavily_evidence():
    live.validate_live_source(source())


def test_validate_live_source_rejects_hash_mismatch():
    value = source()
    value["sha256"] = "0" * 64
    with pytest.raises(live.ResearchValidationFailure, match="SHA-256"):
        live.validate_live_source(value)


def test_citation_probe_uses_exact_retained_text():
    live.citation_probe([source()])


def test_validate_task_result_requires_cited_completed_research():
    value = {
        "state": "completed",
        "workflow_version": "work_research_v1",
        "research": {"provider": "tavily", "query": "Python programming language official documentation"},
        "sources": [{
            "id": "web-1",
            "kind": "web",
            "url": "https://www.python.org/about/",
            "label": "Python",
            "provider": "tavily",
            "source_date": None,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
        }],
        "draft": {
            "kind": "research",
            "findings": [{
                "heading": "Python",
                "text": "Synthetic finding.",
                "citations": [{
                    "source_id": "web-1",
                    "quote": "Python is a programming language that lets you work quickly.",
                }],
            }],
        },
        "usage": {
            "accounted_tokens": 100,
            "search": {"actual_credits": 1},
        },
        "artifacts": [
            {"id": "a", "filename": "report.docx", "sha256": "a" * 64},
            {"id": "b", "filename": "report.pdf", "sha256": "b" * 64},
            {"id": "c", "filename": "report.txt", "sha256": "c" * 64},
        ],
    }
    live.validate_task_result(value)


def test_validate_task_result_rejects_raw_page_text_after_completion():
    value = {
        "state": "completed",
        "workflow_version": "work_research_v1",
        "research": {"provider": "tavily"},
        "sources": [{
            "id": "web-1",
            "kind": "web",
            "url": "https://www.python.org/about/",
            "provider": "tavily",
            "text": "raw page text must not survive completed-task DTOs",
        }],
        "draft": {
            "kind": "research",
            "findings": [{
                "heading": "Python",
                "text": "Synthetic finding.",
                "citations": [{"source_id": "web-1", "quote": "This quote is long enough for the schema."}],
            }],
        },
        "usage": {"search": {"actual_credits": 1}},
        "artifacts": [{}, {}, {}],
    }
    with pytest.raises(live.ResearchValidationFailure, match="raw page text"):
        live.validate_task_result(value)


def test_merge_evidence_preserves_existing_gates(tmp_path):
    path = tmp_path / "base.json"
    path.write_text(json.dumps({
        "backup_restore": {"status": "passed", "evidence": "restore-run"}
    }), encoding="utf-8")
    result = live.merge_evidence(path, {
        "research": {"status": "passed", "evidence": "live-tavily"}
    })
    assert result["backup_restore"]["status"] == "passed"
    assert result["research"]["evidence"] == "live-tavily"


def test_guard_is_fail_closed(monkeypatch):
    monkeypatch.delenv("SHUDDHO_STAGING_ALLOW_LIVE_RESEARCH_EXERCISE", raising=False)
    with pytest.raises(live.ResearchValidationFailure, match="SHUDDHO_STAGING_ALLOW_LIVE_RESEARCH_EXERCISE"):
        live.require_guard()
    monkeypatch.setenv("SHUDDHO_STAGING_ALLOW_LIVE_RESEARCH_EXERCISE", "true")
    live.require_guard()

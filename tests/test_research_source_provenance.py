"""Day 6 source provenance boundaries (synthetic retrieval; no live-provider claims)."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("temporalio")

from coworker_samples import work_draft
from research_samples import search_data
from services.coworker.research import TavilyResearchProvider, validate_evidence
from services.coworker.schemas import ResearchOptions


def _cited_source():
    source = TavilyResearchProvider.parse(
        search_data(), ResearchOptions(query="synthetic project update")
    ).sources[0]
    draft = work_draft("research")
    validate_evidence(draft, [source])  # A real, source-backed fixture still passes.
    return draft, source


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("label", None),
        ("label", "   "),
        ("retrieved_at", None),
        ("retrieved_at", "not-a-date"),
        ("retrieved_at", datetime.now(timezone.utc).replace(tzinfo=None).isoformat()),
        ("retrieved_at", (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()),
        ("source_date", "not-a-date"),
    ],
)
def test_cited_research_source_requires_verifiable_provenance(field, value):
    draft, source = _cited_source()
    mutated = deepcopy(source)
    if value is None:
        mutated.pop(field, None)
    else:
        mutated[field] = value

    with pytest.raises(ValueError, match="provenance"):
        validate_evidence(draft, [mutated])


def test_duplicate_web_identifiers_cannot_silently_rebind_citations():
    draft, source = _cited_source()
    shadow = deepcopy(source)
    shadow["url"] = "https://example.net/different-page"
    # Both excerpts and hashes are intact, but their shared ID is ambiguous.
    with pytest.raises(ValueError, match="duplicate"):
        validate_evidence(draft, [source, shadow])


def test_absent_publication_date_remains_valid_for_unfiltered_retrieval():
    draft, source = _cited_source()
    source["source_date"] = None
    validate_evidence(draft, [source])

"""Browser fixture capacity must support its three deliberately held decisions."""
import asyncio
import runpy
from pathlib import Path

import pytest

pytest.importorskip("sqlalchemy", reason="Install the coworker extra")
pytest.importorskip("temporalio", reason="Install the coworker extra")

from sqlalchemy import select

from services.coworker.agent_runtime import AgentRuntime
from services.coworker.agent_schemas import AgentRunCreate
from services.coworker.errors import CoworkerError
from services.coworker.models import ProviderLease
from services.coworker.schemas import parse_draft


@pytest.fixture
def browser_fixture(tmp_path, monkeypatch):
    # Load the actual local-only server configuration without starting Temporal.
    # Falling back to the production two-call workspace limit breaks this case.
    monkeypatch.setenv("SHUDDHO_BROWSER_TESTS", "true")
    monkeypatch.setenv("SHUDDHO_TEST_WORKDIR", str(tmp_path))
    fixture = runpy.run_path(str(Path(__file__).with_name("coworker_browser_server.py")))
    try:
        yield fixture
    finally:
        fixture["container"].repository.sessions.kw["bind"].dispose()


def test_browser_fixture_can_hold_three_planner_reservations(browser_fixture):
    container = browser_fixture["container"]
    browser_fixture["_set_agent_runtime_v3"](True)
    owner = browser_fixture["account"](container, "alice")
    runs = [container.agent.create(owner, AgentRunCreate(
        goal=f"Create the project document for milestone {number}.", output_language="en",
    ), f"browser-capacity-{number}")[0] for number in range(3)]
    runtime = AgentRuntime(container, None, planner=browser_fixture["BrowserAgentPlanner"]())
    tokens = runtime._v3_planner_reservation()
    for run in runs:
        container.agent.reserve_planner(run["id"], tokens)

    with container.repository.sessions() as db:
        leases = list(db.scalars(select(ProviderLease)).all())
        assert len(leases) == 3
        assert {lease.resource_id for lease in leases} == {run["id"] for run in runs}
        assert all(lease.kind == "planner" for lease in leases)

    # The fixture remains bounded: a fourth concurrent call is still denied.
    with pytest.raises(CoworkerError) as caught:
        container.agent.reserve_planner(runs[0]["id"], tokens)
    assert caught.value.code == "workspace_provider_busy"


@pytest.mark.parametrize("language, instruction, expected", [
    ("auto", "Create a concise project document.", "en"),
    ("auto", "Create a concise Bangla summary document.", "bn"),
    ("bn", "Create a concise project document.", "bn"),
    ("ar", "Create a concise project document.", "ar"),
])
def test_browser_model_accepts_conversation_output_language(
    browser_fixture, language, instruction, expected,
):
    model = browser_fixture["BrowserModel"]()
    messages = model.messages({"skill_id": "document", "instruction": instruction},
                              [{"id": "brief", "text": instruction}])
    result = asyncio.run(model.generate(messages, language, {"brief"}))
    validated = parse_draft("document", result.draft.model_dump(mode="json"))
    assert validated.output_language == expected
    assert validated.document.sections[0].source_ids == ["brief"]
    if expected == "bn":
        assert validated.document.sections[0].paragraphs == ["দলটি ১২টি পর্যালোচনা সম্পন্ন করেছে।"]

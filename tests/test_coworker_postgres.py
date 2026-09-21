"""Concurrency guarantees must run against PostgreSQL, not SQLite."""
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from uuid import uuid4

import pytest

pytest.importorskip("sqlalchemy")
pytestmark = [pytest.mark.coworker_integration, pytest.mark.skipif(not os.getenv("SHUDDHO_TEST_POSTGRES_URL"), reason="Dedicated PostgreSQL test database required")]

from sqlalchemy import inspect, text
from services.coworker.auth import Principal
from services.coworker.config import Settings
from services.coworker.database import session_factory
from services.coworker.errors import CoworkerError
from services.coworker.migrate import upgrade
from services.coworker.repository import Repository
from services.coworker.schemas import TaskCreate


@pytest.fixture
def repository():
    url = os.environ["SHUDDHO_TEST_POSTGRES_URL"]
    settings = Settings(database_url=url, auth_issuer="https://identity.example.test/auth/v1", environment="development", storage_backend="local")
    upgrade(url)
    repo = Repository(session_factory(url), settings)
    yield repo
    repo.sessions.kw["bind"].dispose()


def owner(repo):
    return repo.ensure_account(Principal(repo.settings.auth_issuer, str(uuid4()), 9999999999))["account_id"]


def test_migrations_use_private_schema_and_repeat_safely(repository):
    upgrade(repository.settings.database_url)
    with repository.sessions() as db:
        assert db.scalar(text("SELECT current_schema()")) == "shuddho_coworker"
        assert db.scalar(text("SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_name LIKE 'cw_%'")) == 0
        assert "cw_tasks" in inspect(db.bind).get_table_names(schema="shuddho_coworker")


def test_simultaneous_retries_share_one_task_and_usage_record(repository):
    identity = owner(repository)
    request = TaskCreate(instruction="Create report", notes="12 reviews completed.")
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda _: repository.create_task(identity, request, "same-key"), range(6)))
    assert len({task["id"] for task, _created in results}) == 1
    assert sum(created for _task, created in results) == 1


def test_active_task_limit_is_atomic(repository):
    repository.settings = replace(repository.settings, max_active_tasks=1)
    identity = owner(repository)
    def submit(_index):
        try:
            return repository.create_task(identity, TaskCreate(instruction="Create report", notes="Source"), str(uuid4()))[0]["state"]
        except CoworkerError as error:
            return error.code
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(submit, range(6)))
    assert results.count("queued") == 1
    assert results.count("active_task_limit") == 5


def test_daily_token_reservation_and_settlement_are_atomic(repository):
    repository.settings = replace(repository.settings, daily_token_budget=10000)
    identity = owner(repository)
    tasks = [repository.create_task(identity, TaskCreate(instruction="Create report", notes="Source"), str(uuid4()))[0] for _ in range(2)]
    def reserve(task):
        try:
            return task["id"], repository.reserve_model(task["id"], 6000)
        except CoworkerError as error:
            return task["id"], error.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        values = list(pool.map(reserve, tasks))
    assert sorted(str(result) for _, result in values) == ["1", "daily_limit"]
    task_id = next(task_id for task_id, value in values if value == 1)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: repository.settle_model(task_id, 1, 100, 10, "completed"), range(4)))
    with repository.sessions() as db:
        assert db.scalar(text("SELECT allocated_tokens FROM cw_daily_usage WHERE owner_id=:owner"), {"owner": identity}) == 100


def test_paid_search_reservation_is_atomic_under_duplicate_delivery(repository):
    repository.settings = replace(repository.settings, research_services_enabled=True)
    task = repository.create_task(owner(repository), TaskCreate(skill_id="research", instruction="Compare the evidence",
                                                                research={"query": "public project update"}), str(uuid4()))[0]
    def reserve(_index):
        try:
            repository.reserve_search(task["id"])
            return "reserved"
        except CoworkerError as error:
            return error.code
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(reserve, range(6)))
    assert results.count("reserved") == 1 and results.count("search_outcome_unknown") == 5


def action_repository(repository):
    import base64
    from services.coworker.action_repository import ActionRepository
    settings = replace(repository.settings, actions_enabled=True,
                       connector_encryption_key=base64.urlsafe_b64encode(b"\x22" * 32).decode())
    return ActionRepository(repository.sessions, settings)


def test_simultaneous_action_previews_approvals_and_execution_claims(repository):
    from action_samples import connected, action_request
    actions, identity = action_repository(repository), owner(repository)
    connection = connected(actions, identity)
    request = action_request(connection)
    with ThreadPoolExecutor(max_workers=6) as pool:
        previews = list(pool.map(lambda _: actions.prepare(identity, request, "same-action-key"), range(6)))
    assert len({p["id"] for p in previews}) == 1
    value = previews[0]
    with ThreadPoolExecutor(max_workers=6) as pool:
        approvals = list(pool.map(lambda _: actions.approve(identity, value["id"], value["preview_hash"]), range(6)))
    assert len({p["approved_at"] for p in approvals}) == 1
    with ThreadPoolExecutor(max_workers=6) as pool:
        claims = list(pool.map(lambda _: actions.claim_execution(value["id"]), range(6)))
    assert sum(claim is not None for claim in claims) == 1


def test_daily_action_approval_limit_is_atomic(repository):
    from action_samples import connected, action_request
    actions, identity = action_repository(repository), owner(repository)
    actions.settings = replace(actions.settings, max_daily_actions=1)
    connection = connected(actions, identity)
    values = [actions.prepare(identity, action_request(connection), str(uuid4())) for _ in range(6)]
    def approve(value):
        try:
            return actions.approve(identity, value["id"], value["preview_hash"])["state"]
        except CoworkerError as error:
            return error.code
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(approve, values))
    assert results.count("queued") == 1 and results.count("action_limit") == 5

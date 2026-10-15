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
        tables = set(inspect(db.bind).get_table_names(schema="shuddho_coworker"))
        assert "cw_tasks" in tables
        assert {"cw_conversations", "cw_conversation_messages"} <= tables
        assert {
            "cw_transactions",
            "cw_transaction_revisions",
            "cw_transaction_events",
            "cw_transaction_execution_links",
            "cw_transaction_terms",
            "cw_transaction_reconciliation_evidence",
            "cw_restaurant_reservation_intents",
            "cw_travel_quote_intents",
            "cw_travel_quote_verifications",
            "cw_shopping_cart_intents",
            "cw_shopping_cart_verifications",
            "cw_shopping_checkout_bindings",
            "cw_travel_booking_bindings",
        } <= tables
        columns = {
            column["name"]
            for column in inspect(db.bind).get_columns(
                "cw_transactions",
                schema="shuddho_coworker",
            )
        }
        assert "current_terms_revision" in columns
        link_columns = {
            column["name"]
            for column in inspect(db.bind).get_columns(
                "cw_transaction_execution_links",
                schema="shuddho_coworker",
            )
        }
        assert {
            "terms_revision",
            "terms_sha256",
            "preview_hash",
            "provider",
            "action_kind",
        } <= link_columns


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



def test_structured_memory_limit_is_atomic(repository):
    from services.coworker.memory_repository import MemoryRepository
    from services.coworker.memory_schemas import MemoryFactCreate
    settings = replace(repository.settings, agent_memory_enabled=True, max_memory_facts=1)
    memory = MemoryRepository(repository.sessions, settings)
    identity = owner(repository)

    def create(index):
        try:
            return memory.create(identity, MemoryFactCreate(
                namespace="preferences",
                key=f"preference-{index}",
                value=f"value-{index}",
                language="en",
            ))["key"]
        except CoworkerError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(create, range(6)))
    assert sum(value.startswith("preference-") for value in results) == 1
    assert results.count("memory_limit") == 5



def test_agent_planner_call_limit_and_daily_budget_are_atomic(repository):
    from services.coworker.agent_repository import AgentRepository
    from services.coworker.agent_schemas import AgentRunCreate
    settings = replace(repository.settings, agent_runtime_enabled=True,
                       max_agent_planner_calls=1, agent_planner_token_budget=1000,
                       daily_token_budget=5000)
    agent = AgentRepository(repository.sessions, settings)
    identity = owner(repository)
    run, _ = agent.create(identity, AgentRunCreate(
        goal="Prepare a professional update.", output_language="en"
    ), "planner-race")

    def reserve(_index):
        try:
            return agent.reserve_planner(run["id"], 1000)["call"]
        except CoworkerError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(reserve, range(6)))
    assert results.count(1) == 1
    assert results.count("planner_call_limit") == 5
    agent.release_planner_capacity(run["id"], 1)
    with repository.sessions() as db:
        allocated = db.scalar(text(
            "SELECT allocated_tokens FROM cw_daily_usage WHERE owner_id=:owner"
        ), {"owner": identity})
        assert allocated == 1000


def test_provider_global_capacity_is_atomic_across_workspaces(repository):
    settings = replace(
        repository.settings,
        daily_token_budget=500000,
        task_token_budget=100000,
        provider_max_concurrent_calls=1,
        provider_max_concurrent_per_workspace=1,
        provider_max_reserved_tokens=200000,
        provider_max_reserved_tokens_per_workspace=100000,
    )
    repository.settings = settings
    owners = [owner(repository), owner(repository)]
    tasks = [
        repository.create_task(
            identity,
            TaskCreate(instruction="Create report", notes="Source"),
            str(uuid4()),
        )[0]
        for identity in owners
    ]

    def reserve(task):
        try:
            return task["id"], repository.reserve_model(task["id"], 10000)
        except CoworkerError as error:
            return task["id"], error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(reserve, tasks))

    assert sum(value == 1 for _task_id, value in results) == 1
    assert sum(value == "provider_capacity_busy" for _task_id, value in results) == 1

    admitted = next(task_id for task_id, value in results if value == 1)
    blocked = next(task_id for task_id, value in results if value == "provider_capacity_busy")
    repository.settle_model(admitted, 1, 100, 10, "completed")
    assert repository.reserve_model(blocked, 10000) == 1
    repository.settle_model(blocked, 1, 100, 10, "completed")


def test_provider_workspace_fair_share_is_atomic(repository):
    repository.settings = replace(
        repository.settings,
        daily_token_budget=500000,
        task_token_budget=100000,
        provider_max_concurrent_calls=4,
        provider_max_concurrent_per_workspace=1,
        provider_max_reserved_tokens=400000,
        provider_max_reserved_tokens_per_workspace=100000,
    )
    identity = owner(repository)
    tasks = [
        repository.create_task(
            identity,
            TaskCreate(instruction="Create report", notes="Source"),
            str(uuid4()),
        )[0]
        for _ in range(2)
    ]

    def reserve(task):
        try:
            return repository.reserve_model(task["id"], 10000)
        except CoworkerError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(reserve, tasks))

    assert results.count(1) == 1
    assert results.count("workspace_provider_busy") == 1
    admitted = next(task for task in tasks if repository.get_task(identity, task["id"])["usage"]["model_attempts"] == 1)
    repository.settle_model(admitted["id"], 1, 100, 10, "completed")


def test_expired_provider_lease_releases_shared_capacity(repository):
    repository.settings = replace(
        repository.settings,
        daily_token_budget=500000,
        task_token_budget=100000,
        provider_max_concurrent_calls=1,
        provider_max_concurrent_per_workspace=1,
        provider_max_reserved_tokens=200000,
        provider_max_reserved_tokens_per_workspace=100000,
    )
    first_owner, second_owner = owner(repository), owner(repository)
    first = repository.create_task(
        first_owner, TaskCreate(instruction="Create report", notes="Source"), str(uuid4())
    )[0]
    second = repository.create_task(
        second_owner, TaskCreate(instruction="Create report", notes="Source"), str(uuid4())
    )[0]
    assert repository.reserve_model(first["id"], 10000) == 1

    with repository.sessions.begin() as db:
        db.execute(text(
            "UPDATE cw_provider_leases SET expires_at = now() - interval '1 second'"
        ))

    assert repository.reserve_model(second["id"], 10000) == 1
    repository.settle_model(second["id"], 1, 100, 10, "completed")


def test_planner_and_draft_share_one_provider_capacity_pool(repository):
    from services.coworker.agent_repository import AgentRepository
    from services.coworker.agent_schemas import AgentRunCreate

    settings = replace(
        repository.settings,
        agent_runtime_enabled=True,
        intelligent_planner_enabled=True,
        max_agent_planner_calls=2,
        agent_planner_token_budget=20000,
        daily_token_budget=500000,
        task_token_budget=100000,
        provider_max_concurrent_calls=1,
        provider_max_concurrent_per_workspace=1,
        provider_max_reserved_tokens=200000,
        provider_max_reserved_tokens_per_workspace=100000,
    )
    repository.settings = settings
    agent = AgentRepository(repository.sessions, settings)
    planner_owner = owner(repository)
    task_owner = owner(repository)
    run, _ = agent.create(
        planner_owner,
        AgentRunCreate(goal="Prepare a professional update.", output_language="en"),
        "shared-provider-pool",
    )
    task = repository.create_task(
        task_owner,
        TaskCreate(instruction="Create report", notes="Source"),
        str(uuid4()),
    )[0]

    reservation = agent.reserve_planner(run["id"], 10000)
    with pytest.raises(CoworkerError) as blocked:
        repository.reserve_model(task["id"], 10000)
    assert blocked.value.code == "provider_capacity_busy"

    agent.release_planner_capacity(run["id"], reservation["call"])
    assert repository.reserve_model(task["id"], 10000) == 1
    repository.settle_model(task["id"], 1, 100, 10, "completed")


def test_global_provider_daily_budget_is_atomic_across_workspaces(repository):
    with repository.sessions() as db:
        baseline = db.scalar(text(
            "SELECT COALESCE(allocated_tokens, 0) FROM cw_provider_daily_usage WHERE day = to_char(now() at time zone 'utc', 'YYYY-MM-DD')"
        )) or 0
    repository.settings = replace(
        repository.settings,
        daily_token_budget=500000,
        task_token_budget=100000,
        provider_max_concurrent_calls=4,
        provider_max_concurrent_per_workspace=2,
        provider_max_reserved_tokens=400000,
        provider_max_reserved_tokens_per_workspace=200000,
        provider_daily_token_budget=int(baseline) + 15000,
    )
    identities = [owner(repository), owner(repository)]
    tasks = [
        repository.create_task(
            identity,
            TaskCreate(instruction="Create report", notes="Source"),
            str(uuid4()),
        )[0]
        for identity in identities
    ]

    def reserve(task):
        try:
            return task["id"], repository.reserve_model(task["id"], 10000)
        except CoworkerError as error:
            return task["id"], error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(reserve, tasks))

    assert sum(value == 1 for _task_id, value in results) == 1
    assert sum(value == "provider_daily_budget" for _task_id, value in results) == 1
    admitted = next(task_id for task_id, value in results if value == 1)
    repository.settle_model(admitted, 1, 100, 10, "completed")


def test_known_usage_reduces_global_daily_reservation(repository):
    with repository.sessions() as db:
        baseline = db.scalar(text(
            "SELECT COALESCE(allocated_tokens, 0) FROM cw_provider_daily_usage WHERE day = to_char(now() at time zone 'utc', 'YYYY-MM-DD')"
        )) or 0
    repository.settings = replace(
        repository.settings,
        daily_token_budget=500000,
        task_token_budget=100000,
        provider_daily_token_budget=int(baseline) + 50000,
    )
    identity = owner(repository)
    task = repository.create_task(
        identity,
        TaskCreate(instruction="Create report", notes="Source"),
        str(uuid4()),
    )[0]
    repository.reserve_model(task["id"], 10000)
    repository.settle_model(task["id"], 1, 250, 10, "completed")
    with repository.sessions() as db:
        total = db.scalar(text(
            "SELECT allocated_tokens FROM cw_provider_daily_usage WHERE day = to_char(now() at time zone 'utc', 'YYYY-MM-DD')"
        ))
    assert total == int(baseline) + 250


def test_browser_push_active_device_limit_is_atomic(repository):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from services.coworker.notification_repository import NotificationRepository
    from services.coworker.notification_schemas import BrowserPushSubscriptionUpsert
    from services.coworker.web_push import b64url_encode

    settings = replace(
        repository.settings,
        agent_runtime_enabled=True,
        personal_goals_enabled=True,
        automations_enabled=True,
        browser_push_enabled=True,
        max_browser_push_subscriptions=2,
        web_push_vapid_private_key=b64url_encode((1).to_bytes(32, "big")),
        web_push_vapid_subject="mailto:ops@example.test",
        web_push_encryption_key=b64url_encode(b"p" * 32),
    )
    identity = owner(repository)
    notifications = NotificationRepository(repository.sessions, settings)
    ua = ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    p256dh = b64url_encode(ua)
    auth = b64url_encode(b"a" * 16)

    def register(index):
        try:
            notifications.register_browser_push_subscription(
                identity,
                BrowserPushSubscriptionUpsert(
                    endpoint=f"https://fcm.googleapis.com/fcm/send/postgres-{index}",
                    p256dh=p256dh,
                    auth=auth,
                    expiration_time=None,
                ),
            )
            return "active"
        except CoworkerError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(register, range(6)))

    assert results.count("active") == 2
    assert results.count("browser_push_subscription_limit") == 4
    with repository.sessions() as db:
        assert db.scalar(text(
            "SELECT count(*) FROM cw_browser_push_subscriptions WHERE owner_id=:owner AND active"
        ), {"owner": identity}) == 2


def test_concurrent_conversation_creation_and_message_replay_accept_once(repository):
    from threading import Barrier
    from services.coworker.conversation_repository import ConversationRepository
    from services.coworker.conversation_schemas import ConversationCreate, MessageCreate
    repo = ConversationRepository(repository.sessions, replace(repository.settings, conversations_enabled=True))
    identity = owner(repository)
    barrier = Barrier(6)
    def create(_):
        barrier.wait(timeout=10)
        return repo.create(identity, ConversationCreate(title="Project"), "conversation-race-key")
    with ThreadPoolExecutor(max_workers=6) as pool:
        created = list(pool.map(create, range(6)))
    assert len({item[0]["id"] for item in created}) == 1
    assert sum(item[1] for item in created) == 1
    conversation_id = created[0][0]["id"]
    barrier = Barrier(6)
    def append(_):
        barrier.wait(timeout=10)
        return repo.append_message(identity, conversation_id, MessageCreate(text="Create a report", client_request_key="message-race-key"))
    with ThreadPoolExecutor(max_workers=6) as pool:
        messages = list(pool.map(append, range(6)))
    assert len({item[0]["id"] for item in messages}) == 1
    assert sum(item[1] for item in messages) == 1
    assert repo.get(identity, conversation_id)["message_sequence"] == 1


def test_concurrent_independent_conversation_messages_preserve_sequence(repository):
    from services.coworker.conversation_repository import ConversationRepository
    from services.coworker.conversation_schemas import ConversationCreate, MessageCreate
    repo = ConversationRepository(repository.sessions, replace(repository.settings, conversations_enabled=True))
    identity = owner(repository)
    conversation, _ = repo.create(identity, ConversationCreate(title="Project"), "conversation-sequence")
    with ThreadPoolExecutor(max_workers=6) as pool:
        messages = list(pool.map(lambda index: repo.append_message(identity, conversation["id"], MessageCreate(text=f"Message {index}", client_request_key=f"message-independent-{index}")), range(6)))
    assert sorted(item[0]["sequence"] for item in messages) == [1, 2, 3, 4, 5, 6]
    assert all(item[1] for item in messages)


def test_conversation_mutations_wait_for_account_lock_before_child_lock(repository):
    from threading import Event
    from sqlalchemy import event, select
    from services.coworker.models import Account
    from services.coworker.conversation_repository import ConversationRepository
    from services.coworker.conversation_schemas import ConversationCreate, MessageCreate
    repo = ConversationRepository(repository.sessions, replace(repository.settings, conversations_enabled=True))
    identity = owner(repository)
    engine = repository.sessions.kw["bind"]
    for operation in ("append", "delete"):
        conversation, _ = repo.create(identity, ConversationCreate(title="Project"), "conversation-lock-" + operation)
        attempted = Event()
        observed = []
        def before_cursor(_conn, _cursor, statement, _params, _context, _many):
            if "FOR UPDATE" in statement and not observed:
                observed.append("account" if "cw_accounts" in statement else "child")
                attempted.set()
        with ThreadPoolExecutor(max_workers=1) as pool:
            with repository.sessions.begin() as db:
                # Match erasure's first lock. The other request must wait here
                # without holding a conversation lock that erasure needs next.
                db.scalar(select(Account).where(Account.id == identity).with_for_update())
                event.listen(engine, "before_cursor_execute", before_cursor)
                try:
                    if operation == "append":
                        future = pool.submit(repo.append_message, identity, conversation["id"], MessageCreate(text="Message", client_request_key="message-lock-key"))
                    else:
                        future = pool.submit(repo.delete, identity, conversation["id"])
                    assert attempted.wait(10)
                finally:
                    event.remove(engine, "before_cursor_execute", before_cursor)
            # Release account before checking/awaiting, so a regression never
            # leaves the pool blocked during cleanup.
            result = future.result(timeout=10)
            assert result is not None
            assert observed == ["account"]


def test_concurrent_conversation_dispatch_is_one_agent_run_and_one_outbox(repository):
    """PostgreSQL owner lock serializes repeated admission of one reviewed message."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy import select
    from services.coworker.agent_repository import AgentRepository
    from services.coworker.conversation_dispatch import ConversationDispatchService
    from services.coworker.conversation_repository import ConversationRepository
    from services.coworker.conversation_schemas import ConversationCreate, MessageCreate
    from services.coworker.models import AgentOutbox, AgentRun
    settings = replace(repository.settings, conversations_enabled=True, agent_runtime_enabled=True, work_services_enabled=True)
    agent = AgentRepository(repository.sessions, settings)
    conversations = ConversationRepository(repository.sessions, settings)
    dispatch = ConversationDispatchService(repository.sessions, settings, agent)
    identity = owner(repository)
    conversation, _ = conversations.create(identity, ConversationCreate(title="Report"), "postgres-cw06-conversation")
    message, _ = conversations.append_message(
        identity, conversation["id"],
        MessageCreate(text="Create a detailed report about quarterly sales", client_request_key="postgres-cw06-message"),
    )
    gate = Barrier(6)
    def launch(_):
        gate.wait(timeout=10)
        return dispatch.dispatch(identity, conversation["id"], message["id"], expected_sequence=1)
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(launch, range(6)))
    ids = [item[0]["run_id"] for item in results]
    assert len(set(ids)) == 1
    assert sum(item[1] for item in results) == 1
    with repository.sessions() as db:
        assert db.scalar(select(AgentRun.id).where(AgentRun.owner_id == identity)) == ids[0]
        assert db.get(AgentOutbox, ids[0]) is not None


def test_agent_browser_cancel_and_worker_control_are_serialized_on_postgres(repository):
    """Cancellation and worker polls share session-first row locking, not deadlocks."""
    import base64
    from threading import Barrier
    from services.coworker.agent_repository import AgentRepository
    from services.coworker.agent_schemas import AgentRunCreate
    from services.coworker.browser import BrowserRepository
    from services.coworker.browser_schemas import BrowserSessionCreate

    settings = replace(
        repository.settings,
        actions_enabled=True,
        # Browser use requires the existing connector trust boundary, which
        # in turn requires a syntactically valid development OAuth config.
        # These values are inert test fixtures, never usable provider secrets.
        google_client_id="simulated-client-id",
        google_client_secret="simulated-client-secret",
        google_redirect_uri="http://127.0.0.1:5173/oauth/google/callback",
        connector_encryption_key=base64.urlsafe_b64encode(b"1" * 32).decode(),
        connector_trust_boundary_enabled=True,
        agent_runtime_enabled=True,
        intelligent_planner_enabled=True,
        agent_runtime_v3_enabled=True,
        browser_enabled=True,
        agent_browser_read_enabled=True,
        browser_worker_token="postgres-browser-worker-token-0123456789abcdef",
    )
    settings.validate()
    identity = owner(repository)
    agent = AgentRepository(repository.sessions, settings)
    browser = BrowserRepository(repository.sessions, settings)
    run, _ = agent.create(
        identity, AgentRunCreate(goal="Read https://example.com/article"), str(uuid4()),
    )
    ordinal = agent.append_v3_step(
        identity, run["id"], "browser.read", "Read the user's exact URL",
    )
    agent.begin_invocation(run["id"], ordinal)
    session, _ = browser.create(
        identity, BrowserSessionCreate(purpose="research", start_url="https://example.com/article"),
        f"agent:{run['id']}:{ordinal}", agent_origin=True,
    )
    agent.link_invocation_resource(run["id"], ordinal, "browser_session", session["id"])
    command = browser.prepare_agent_read(identity, session["id"], "https://example.com/article")
    assert [item["id"] for item in browser.claim_commands("postgres-worker")] == [command["id"]]

    ready = Barrier(2)
    def cancel():
        ready.wait(timeout=10)
        return agent.cancel(identity, run["id"])
    def poll():
        ready.wait(timeout=10)
        return browser.worker_control("postgres-worker", command["id"])

    with ThreadPoolExecutor(max_workers=2) as pool:
        cancelled = pool.submit(cancel)
        control = pool.submit(poll)
        result_cancel = cancelled.result(timeout=20)
        result_control = control.result(timeout=20)
    assert result_cancel["state"] == "cancelled"
    assert result_control["action"] in {"continue", "stop"}
    assert browser.get(identity, session["id"])["state"] == "cancelled"
    assert browser.list_commands(identity, session["id"])[0]["state"] == "cancelled"
    assert browser.worker_control("postgres-worker", command["id"])["action"] == "stop"


def test_agent_browser_receipt_and_revocation_share_session_first_locks_on_postgres(repository):
    """One concurrent winner: browser receipt commits OR revocation, never a deadlock."""
    import base64
    from threading import Barrier
    from services.coworker.agent_repository import AgentRepository
    from services.coworker.agent_schemas import AgentRunCreate
    from services.coworker.browser import BrowserRepository
    from services.coworker.browser_schemas import BrowserSessionCreate

    settings = replace(
        repository.settings,
        actions_enabled=True,
        google_client_id="simulated-client-id",
        google_client_secret="simulated-client-secret",
        google_redirect_uri="http://127.0.0.1:5173/oauth/google/callback",
        connector_encryption_key=base64.urlsafe_b64encode(b"1" * 32).decode(),
        connector_trust_boundary_enabled=True,
        agent_runtime_enabled=True,
        intelligent_planner_enabled=True,
        agent_runtime_v3_enabled=True,
        browser_enabled=True,
        agent_browser_read_enabled=True,
        browser_worker_token="postgres-browser-worker-token-0123456789abcdef",
    )
    settings.validate()
    identity = owner(repository)
    agent = AgentRepository(repository.sessions, settings)
    browser = BrowserRepository(repository.sessions, settings)
    run, _ = agent.create(
        identity, AgentRunCreate(goal="Read https://example.com/article"), str(uuid4()),
    )
    ordinal = agent.append_v3_step(
        identity, run["id"], "browser.read", "Read the exact user URL",
    )
    agent.begin_invocation(run["id"], ordinal)
    session, _ = browser.create(
        identity, BrowserSessionCreate(purpose="research", start_url="https://example.com/article"),
        f"agent:{run['id']}:{ordinal}", agent_origin=True,
    )
    agent.link_invocation_resource(run["id"], ordinal, "browser_session", session["id"])
    command = browser.prepare_agent_read(identity, session["id"], "https://example.com/article")
    assert [item["id"] for item in browser.claim_commands("pg-receipt-worker")] == [command["id"]]
    completed = browser.complete_command("pg-receipt-worker", command["id"], {
        "final_url": "https://example.com/article", "title": "Read-only source",
        "redirect_chain": [], "resolved_ips": {"example.com": ["93.184.216.34"]},
        "submission_performed": False,
    })
    assert completed["state"] == "succeeded"

    ready = Barrier(2)
    def settle():
        ready.wait(timeout=10)
        try:
            agent.finish_invocation(
                run["id"], ordinal, "browser_command", command["id"],
                {"observation_scope": "metadata_only", "observation_trust": "untrusted"},
            )
            return "verified"
        except CoworkerError as error:
            return error.code
    def revoke():
        ready.wait(timeout=10)
        return browser.cancel(identity, session["id"])

    with ThreadPoolExecutor(max_workers=2) as pool:
        settled = pool.submit(settle)
        revoked = pool.submit(revoke)
        result = settled.result(timeout=20)
        revoked_result = revoked.result(timeout=20)
    final_state = browser.get(identity, session["id"])["state"]
    assert final_state == revoked_result["state"]
    if result == "verified":
        assert final_state == "completed"
        receipts = agent.verified_observations(identity, run["id"])
        assert len(receipts) == 1
        assert receipts[0]["tool"] == "browser.read"
    else:
        assert result == "browser_session_closed"
        assert final_state == "cancelled"
        assert agent.verified_observations(identity, run["id"]) == []
    assert len(browser.list_commands(identity, session["id"])) == 1


def test_agent_browser_receipt_sql_locks_session_before_command_on_postgres(repository):
    """Inspect real PostgreSQL SELECT FOR UPDATE order; prevent the previous P1 inversion."""
    import base64
    import re
    from sqlalchemy import event
    from services.coworker.agent_repository import AgentRepository
    from services.coworker.agent_schemas import AgentRunCreate
    from services.coworker.browser import BrowserRepository
    from services.coworker.browser_schemas import BrowserSessionCreate

    settings = replace(
        repository.settings,
        actions_enabled=True,
        google_client_id="simulated-client-id",
        google_client_secret="simulated-client-secret",
        google_redirect_uri="http://127.0.0.1:5173/oauth/google/callback",
        connector_encryption_key=base64.urlsafe_b64encode(b"1" * 32).decode(),
        connector_trust_boundary_enabled=True,
        agent_runtime_enabled=True,
        intelligent_planner_enabled=True,
        agent_runtime_v3_enabled=True,
        browser_enabled=True,
        agent_browser_read_enabled=True,
        browser_worker_token="postgres-browser-worker-token-0123456789abcdef",
    )
    settings.validate()
    identity = owner(repository)
    agent = AgentRepository(repository.sessions, settings)
    browser = BrowserRepository(repository.sessions, settings)
    run, _ = agent.create(
        identity, AgentRunCreate(goal="Read https://example.com/article"), str(uuid4()),
    )
    ordinal = agent.append_v3_step(identity, run["id"], "browser.read", "Read source")
    agent.begin_invocation(run["id"], ordinal)
    session, _ = browser.create(
        identity, BrowserSessionCreate(purpose="research", start_url="https://example.com/article"),
        f"agent:{run['id']}:{ordinal}", agent_origin=True,
    )
    agent.link_invocation_resource(run["id"], ordinal, "browser_session", session["id"])
    cmd = browser.prepare_agent_read(identity, session["id"], "https://example.com/article")
    assert [item["id"] for item in browser.claim_commands("pg-order-worker")] == [cmd["id"]]
    assert browser.complete_command("pg-order-worker", cmd["id"], {
        "final_url": "https://example.com/article",
        "title": "Source title",
        "redirect_chain": [],
        "resolved_ips": {"example.com": ["93.184.216.34"]},
        "submission_performed": False,
    })["state"] == "succeeded"

    locks = []
    def on_execute(_connection, _cursor, statement, _parameters, _context, _many):
        sql = " ".join(statement.lower().split())
        if "for update" not in sql:
            return
        for kind in ("session", "command"):
            table = "cw_browser_sessions" if kind == "session" else "cw_browser_commands"
            if re.search(r"\bfrom\s+(?:[a-z0-9_]+\.)?" + table + r"\b", sql):
                locks.append(kind)
                break

    engine = repository.sessions.kw["bind"]
    event.listen(engine, "before_cursor_execute", on_execute)
    try:
        agent.finish_invocation(
            run["id"], ordinal, "browser_command", cmd["id"],
            {"observation_scope": "metadata_only", "observation_trust": "untrusted"},
        )
    finally:
        event.remove(engine, "before_cursor_execute", on_execute)

    assert "session" in locks, locks
    assert "command" in locks, locks
    assert locks.index("session") < locks.index("command"), locks
    assert browser.get(identity, session["id"])["state"] == "completed"
    assert len(agent.verified_observations(identity, run["id"])) == 1


def test_postgres_agent_browser_expiry_between_capture_and_receipt_denies_stale_result(tmp_path):
    """Exercise the CW-09 final receipt/expiry race under actual PostgreSQL locks."""
    import asyncio

    from test_agent_browser_tool import enabled_agent_browser
    from test_coworker import account
    from services.coworker.agent_runtime import AgentRuntime
    from services.coworker.agent_schemas import AgentRunCreate
    from services.coworker.container import Container
    from services.coworker.models import BrowserCommand, BrowserSession, utcnow
    from datetime import timedelta

    url = os.environ["SHUDDHO_TEST_POSTGRES_URL"]
    settings = Settings(
        database_url=url, auth_issuer="https://identity.example.test/auth/v1",
        environment="development", storage_backend="local",
        local_storage_path=tmp_path / "objects",
    )
    upgrade(url)
    service = Container.create(settings)
    try:
        enabled_agent_browser(service)
        identity = account(service, "cw09-pg-expiry-" + str(uuid4()))
        run, _ = service.agent.create(
            identity, AgentRunCreate(goal="Read https://example.com/article"),
            "cw09-postgres-late-receipt-" + str(uuid4()),
        )
        ordinal = service.agent.append_v3_step(
            identity, run["id"], "browser.read", "Read exactly the owned public URL",
        )
        runtime = AgentRuntime(service, None)
        assert asyncio.run(runtime.execute_step(run["id"], ordinal)) == {"status": "executing"}
        session_id = service.agent.step_resource(run["id"], ordinal)["resource_id"]
        command = service.browser.claim_commands("cw09-pg-expiry-worker")[0]
        service.browser.complete_command("cw09-pg-expiry-worker", command["id"], {
            "final_url": "https://example.com/article",
            "title": "Already captured",
            "resolved_ips": {"example.com": ["93.184.216.34"]},
            "page_text": "Captured untrusted browser body",
        })
        assert service.browser.read_agent_capture(
            identity, session_id, command["id"],
        )["text"] == "Captured untrusted browser body"
        with service.repository.sessions.begin() as db:
            session = db.get(BrowserSession, session_id)
            session.expires_at = utcnow() - timedelta(seconds=1)
        with pytest.raises(CoworkerError) as denied:
            service.agent.finish_invocation(
                run["id"], ordinal, "browser_command", command["id"],
                {"observation_scope": "captured_text_excerpt", "observation_trust": "untrusted"},
            )
        assert denied.value.code == "browser_session_closed"
        assert service.agent.verified_observations(identity, run["id"]) == []
        assert service.browser.get(identity, session_id)["state"] == "expired"
        with service.repository.sessions() as db:
            persisted = db.get(BrowserCommand, command["id"])
            assert "agent_page_text_sealed" not in (persisted.result or {})
    finally:
        service.repository.sessions.kw["bind"].dispose()


def test_postgres_agent_source_artifact_commits_with_verified_browser_receipt(tmp_path):
    """A real PG Agent receipt points to precisely one owned private object."""
    import asyncio
    import hashlib

    from test_agent_browser_tool import enabled_agent_browser
    from test_coworker import account
    from services.coworker.agent_runtime import AgentRuntime
    from services.coworker.agent_schemas import AgentRunCreate
    from services.coworker.browser_sources import browser_source_identity
    from services.coworker.container import Container
    from services.coworker.models import Artifact, BrowserCommand

    url = os.environ["SHUDDHO_TEST_POSTGRES_URL"]
    settings = Settings(
        database_url=url, auth_issuer="https://identity.example.test/auth/v1",
        environment="development", storage_backend="local",
        local_storage_path=tmp_path / "source-objects",
    )
    upgrade(url)
    service = Container.create(settings)
    try:
        enabled_agent_browser(service)
        identity = account(service, "cw09-source-pg-" + str(uuid4()))
        other = account(service, "cw09-source-other-" + str(uuid4()))
        run, _ = service.agent.create(
            identity, AgentRunCreate(goal="Read https://example.com/article"),
            "cw09-source-artifact-" + str(uuid4()),
        )
        ordinal = service.agent.append_v3_step(
            identity, run["id"], "browser.read", "Read and retain the exact source",
        )
        runtime = AgentRuntime(service, None)
        assert asyncio.run(runtime.execute_step(run["id"], ordinal)) == {"status": "executing"}
        command = service.browser.claim_commands("source-pg-worker")[0]
        body = "বাংলা গবেষণা and an untrusted public page"
        service.browser.complete_command("source-pg-worker", command["id"], {
            "final_url": "https://example.com/article",
            "title": "Captured",
            "resolved_ips": {"example.com": ["93.184.216.34"]},
            "page_text": body,
        })
        assert asyncio.run(runtime.execute_step(run["id"], ordinal)) == {"status": "completed"}
        summaries = service.agent.verified_observations(identity, run["id"])
        assert len(summaries) == 1
        summary = summaries[0]["summary"]
        source_id, object_key, _ = browser_source_identity(identity, command["id"])
        assert summary["artifact_id"] == source_id
        assert summary["artifact_sha256"] == hashlib.sha256(body.encode("utf-8")).hexdigest()
        assert service.storage.get(object_key, 8192).decode("utf-8") == body
        assert service.repository.artifact(identity, source_id)["object_key"] == object_key
        with pytest.raises(CoworkerError) as denied:
            service.repository.artifact(other, source_id)
        assert denied.value.status_code == 404
        with service.repository.sessions() as db:
            artifact = db.get(Artifact, source_id)
            assert artifact is not None and artifact.artifact_class == "browser_source"
            assert "agent_page_text_sealed" not in db.get(BrowserCommand, command["id"]).result
        assert asyncio.run(runtime.execute_step(run["id"], ordinal)) == {"status": "completed"}
        with service.repository.sessions() as db:
            assert db.get(Artifact, source_id).sha256 == summary["artifact_sha256"]
        service.agent.complete_run(run["id"])
        deleted = service.retention.erase_browser_source(identity, source_id)
        assert deleted["metadata_erased"] is True
        assert deleted["object_deleted"] is True
        with pytest.raises(CoworkerError):
            service.repository.artifact(identity, source_id)
        assert service.agent.verified_observations(identity, run["id"])[0]["summary"]["source_deleted"] is True
        with pytest.raises(FileNotFoundError):
            service.storage.get(object_key, 8192)
    finally:
        service.repository.sessions.kw["bind"].dispose()


def test_postgres_agent_sandbox_receipt_rechecks_exact_source_and_output_atomically(tmp_path):
    """Final receipt commit must deny altered Agent code and forged observation."""
    import asyncio

    from sqlalchemy import select
    from test_coworker import account
    from test_sandbox_control_plane import enable_sandbox, completion_observation
    from services.coworker.container import Container
    from services.coworker.agent_runtime import AgentRuntime
    from services.coworker.agent_schemas import AgentRunCreate
    from services.coworker.models import SandboxExecution, ToolInvocation, ToolReceipt

    url = os.environ["SHUDDHO_TEST_POSTGRES_URL"]
    settings = Settings(
        database_url=url, auth_issuer="https://identity.example.test/auth/v1",
        environment="development", storage_backend="local",
        local_storage_path=tmp_path / "sandbox-source-objects",
    )
    upgrade(url)
    service = Container.create(settings)
    try:
        base = enable_sandbox(service)
        enabled = replace(base, agent_sandbox_tool_enabled=True)
        enabled.validate()
        service.settings = enabled
        service.repository.settings = enabled
        service.agent.settings = enabled
        service.sandbox.settings = enabled

        identity = account(service, "cw10-source-binding-pg-" + str(uuid4()))
        original = "print(101)"
        run, _ = service.agent.create(
            identity,
            AgentRunCreate(goal="Run exactly this code.\n\n```python\n" + original + "\n```"),
            "cw10-identity-pg-" + str(uuid4()),
        )
        ordinal = service.agent.append_v3_step(
            identity, run["id"], "sandbox.execute_python", "Execute exact source",
        )
        runtime = AgentRuntime(service, None)
        assert asyncio.run(runtime.execute_step(run["id"], ordinal)) == {"status": "executing"}
        claim = service.sandbox.claim_executions("cw10-pg-sandbox-worker", limit=10)
        resource = service.agent.step_resource(run["id"], ordinal)
        prepared_id = service.sandbox.list_executions(identity, resource["resource_id"])[0]["id"]
        own_claim = next(item for item in claim if item["id"] == prepared_id)
        assert own_claim["source"] == original
        completed = service.sandbox.complete_execution(
            "cw10-pg-sandbox-worker", own_claim["id"], {
                **completion_observation(), "stdout": "101\n",
            },
        )
        assert completed["state"] == "succeeded"
        result = completed["result"]
        bound_summary = {
            "sandbox_state": "succeeded", "exit_code": 0,
            "sandbox_destroyed": True,
            "stdout_sha256": result["stdout_sha256"],
            "stderr_sha256": result["stderr_sha256"],
            "stdout_excerpt": "101\n", "stderr_excerpt": "",
            "output_trust": "untrusted", "artifact_id": None,
            "artifact_sha256": None,
        }

        with service.repository.sessions.begin() as db:
            invocation = db.scalar(select(ToolInvocation).where(
                ToolInvocation.run_id == run["id"],
                ToolInvocation.owner_id == identity,
            ))
            assert invocation is not None
            invocation_id = invocation.id
            invocation.arguments = {"source": "print(999)"}

        with pytest.raises(CoworkerError) as altered:
            service.agent.finish_invocation(
                run["id"], ordinal, "sandbox_execution", own_claim["id"], bound_summary,
            )
        assert altered.value.code == "sandbox_source_binding_mismatch"

        with service.repository.sessions.begin() as db:
            invocation = db.get(ToolInvocation, invocation_id)
            invocation.arguments = {"source": original}

        # Worker completion locks SandboxExecution before SandboxSession.
        # Simulate an in-flight worker claim holding that row: Agent receipt
        # must fail fast (SKIP LOCKED) instead of deadlocking or fabricating
        # an observation while retaining the session lock.
        with service.repository.sessions.begin() as locker:
            held = locker.scalar(select(SandboxExecution).where(
                SandboxExecution.id == own_claim["id"],
            ).with_for_update())
            assert held is not None
            with pytest.raises(CoworkerError) as busy:
                service.agent.finish_invocation(
                    run["id"], ordinal, "sandbox_execution",
                    own_claim["id"], bound_summary,
                )
            assert busy.value.code == "sandbox_source_binding_mismatch"

        with pytest.raises(CoworkerError) as forged:
            service.agent.finish_invocation(
                run["id"], ordinal, "sandbox_execution", own_claim["id"],
                {**bound_summary, "stdout_excerpt": "FORGED"},
            )
        assert forged.value.code == "sandbox_receipt_unverified"
        with service.repository.sessions() as db:
            assert db.get(ToolReceipt, invocation_id) is None

        assert asyncio.run(runtime.execute_step(run["id"], ordinal)) == {"status": "completed"}
        assert service.agent.verified_observations(identity, run["id"])[0]["summary"]["stdout_excerpt"] == "101\n"
    finally:
        service.repository.sessions.kw["bind"].dispose()


def test_postgres_sandbox_worker_claim_rejects_changed_source_before_execution(tmp_path):
    """Real PostgreSQL claim refuses altered queued code even at equal length."""
    from test_coworker import account
    from test_sandbox_control_plane import enable_sandbox, create_session
    from services.coworker.container import Container
    from services.coworker.models import SandboxExecution, SandboxSession
    from services.coworker.sandbox_schemas import SandboxExecutionCreate

    url = os.environ["SHUDDHO_TEST_POSTGRES_URL"]
    settings = Settings(
        database_url=url,
        auth_issuer="https://identity.example.test/auth/v1",
        environment="development",
        storage_backend="local",
        local_storage_path=tmp_path / "claim-integrity-objects",
    )
    upgrade(url)
    service = Container.create(settings)
    try:
        enable_sandbox(service)
        identity = account(service, "cw10-claim-integrity-pg-" + str(uuid4()))
        session = create_session(service, identity, "claim-integrity-" + str(uuid4()))
        original = "print(101)"
        execution = service.sandbox.prepare_execution(
            identity, session["id"], SandboxExecutionCreate(source=original),
        )
        with service.repository.sessions.begin() as db:
            row = db.get(SandboxExecution, execution["id"])
            spec = dict(row.request_spec)
            spec["source"] = "print(999)"
            assert len(spec["source"].encode("utf-8")) == row.source_bytes
            row.request_spec = spec

        claims = service.sandbox.claim_executions("cw10-claim-integrity-worker", limit=10)
        assert all(item["id"] != execution["id"] for item in claims)
        with service.repository.sessions() as db:
            row = db.get(SandboxExecution, execution["id"])
            assert row.state == "failed"
            assert row.error_code == "sandbox_source_integrity_failed"
            assert row.request_spec == {"source_scrubbed": True}
            assert row.claimed_by is None
            assert row.lease_until is None
            owned = db.get(SandboxSession, session["id"])
            assert owned.state == "failed"
        assert all(
            item["id"] != execution["id"]
            for item in service.sandbox.claim_executions("cw10-claim-integrity-retry", limit=10)
        )
    finally:
        service.repository.sessions.kw["bind"].dispose()


def test_postgres_terminal_sandbox_session_blocks_prior_worker_result(tmp_path):
    """A sibling integrity failure closes the real PostgreSQL worker authority."""
    from test_coworker import account
    from test_sandbox_control_plane import (
        completion_observation, create_session, enable_sandbox,
    )
    from services.coworker.container import Container
    from services.coworker.models import SandboxExecution, SandboxSession
    from services.coworker.sandbox_schemas import SandboxExecutionCreate

    url = os.environ["SHUDDHO_TEST_POSTGRES_URL"]
    settings = Settings(
        database_url=url,
        auth_issuer="https://identity.example.test/auth/v1",
        environment="development",
        storage_backend="local",
        local_storage_path=tmp_path / "cw10-terminal-guard",
    )
    upgrade(url)
    service = Container.create(settings)
    try:
        enable_sandbox(service)
        identity = account(service, "terminal-worker-pg-" + str(uuid4()))
        session = create_session(service, identity, "terminal-worker-" + str(uuid4()))
        first = service.sandbox.prepare_execution(
            identity, session["id"], SandboxExecutionCreate(source="print(101)"),
        )
        claimed = service.sandbox.claim_executions("cw10-terminal-first", limit=10)
        assert any(item["id"] == first["id"] for item in claimed)

        second = service.sandbox.prepare_execution(
            identity, session["id"], SandboxExecutionCreate(source="print(202)"),
        )
        with service.repository.sessions.begin() as db:
            row = db.get(SandboxExecution, second["id"])
            spec = dict(row.request_spec)
            spec["source"] = "print(999)"
            row.request_spec = spec

        assert all(
            item["id"] != second["id"]
            for item in service.sandbox.claim_executions("cw10-terminal-second", limit=10)
        )
        with service.repository.sessions() as db:
            assert db.get(SandboxSession, session["id"]).state == "failed"

        with pytest.raises(CoworkerError) as rejected:
            service.sandbox.complete_execution(
                "cw10-terminal-first", first["id"], completion_observation(),
            )
        assert rejected.value.code == "sandbox_session_closed"

        with service.repository.sessions() as db:
            former = db.get(SandboxExecution, first["id"])
            parent = db.get(SandboxSession, session["id"])
            assert former.state == "failed"
            assert former.error_code == "sandbox_session_closed"
            assert former.request_spec == {"source_scrubbed": True}
            assert former.claimed_by is None
            assert former.lease_until is None
            assert former.result == {}
            assert parent.state == "failed"
            assert parent.cleanup_state == "required"
    finally:
        service.repository.sessions.kw["bind"].dispose()

def test_postgres_cw10_inert_code_proposal_replay_is_atomic(repository):
    """Same review identity cannot produce two persisted code rows under racing workers."""
    import hashlib
    from datetime import timedelta
    from uuid import UUID

    from sqlalchemy import select
    from services.coworker.agent_repository import AgentRepository
    from services.coworker.agent_schemas import AgentRunCreate
    from services.coworker.code_proposal_schemas import CodeComputeLimits, CodeProposalEnvelope
    from services.coworker.models import AgentCodeProposal, utcnow

    settings = replace(
        repository.settings,
        agent_runtime_enabled=True,
        intelligent_planner_enabled=True,
        agent_runtime_v3_enabled=True,
        artifact_services_enabled=True,
        code_execution_enabled=True,
        agent_sandbox_tool_enabled=True,
        sandbox_worker_token="postgres-sandbox-worker-token-0123456789abcdef",
        sandbox_preview_origin="https://sandbox-preview.example.test",
        sandbox_preview_secret="postgres-sandbox-preview-secret-0123456789abcdef",
    )
    settings.validate()
    agent = AgentRepository(repository.sessions, settings)
    identity = owner(repository)
    run, created = agent.create(
        identity, AgentRunCreate(goal="Compute owned source data in a sandbox."),
        "postgres-code-run-" + str(uuid4()),
    )
    assert created is True
    source = "print('inert')\n"
    created_at = utcnow()
    proposal = CodeProposalEnvelope(
        owner_id=identity, run_id=UUID(run["id"]),
        source=source, source_sha256=hashlib.sha256(source.encode("utf-8")).hexdigest(),
        input_versions=(),
        limits=CodeComputeLimits(
            cpu_seconds=5, wall_seconds=15, memory_mb=128,
            disk_mb=32, stdout_bytes=1024,
        ),
        created_at=created_at,
        expires_at=created_at + timedelta(minutes=5),
    )
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(
            lambda _: agent.prepare_code_proposal(
                identity, run["id"], proposal, "identical-postgres-code",
            ),
            range(4),
        ))
    assert len({item["id"] for item, _created in results}) == 1
    assert sum(created for _item, created in results) == 1
    assert all(item["approval_granted"] is False for item, _created in results)
    assert all(item["code_executed"] is False for item, _created in results)

    with repository.sessions() as db:
        rows = db.scalars(select(AgentCodeProposal).where(
            AgentCodeProposal.run_id == run["id"],
            AgentCodeProposal.owner_id == identity,
        )).all()
        assert len(rows) == 1
        assert rows[0].state == "unreviewed"
        assert rows[0].snapshot["source"] == source

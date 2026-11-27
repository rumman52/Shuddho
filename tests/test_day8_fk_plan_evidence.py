import pytest

from scripts.day8_fk_plan_evidence import FINDINGS, connection_parameters, summarize_plan


@pytest.mark.parametrize("url", [
    "postgresql+psycopg://u:p@db.supabase.co/staging_test",
    "postgresql+psycopg://u:p@localhost/postgres",
    "postgresql+psycopg://u:p@localhost/production",
    "postgresql+psycopg://u:p@localhost/staging_test?host=db.supabase.co",
    "postgresql+psycopg://u:p@localhost/staging_test?hostaddr=10.0.0.1",
    "postgresql+psycopg://u:p@localhost/staging_test?service=remote",
    "postgresql+psycopg://u:p@localhost/staging_test?options=-c%20transaction_read_only=off",
    "postgresql+psycopg://u:p@127.0.0.2/staging_test",
    "sqlite:///staging_test",
])
def test_reject_unsafe_connections(url):
    with pytest.raises(ValueError, match="disposable loopback"):
        connection_parameters(url)


def test_loopback_address_and_database_are_explicit():
    params = connection_parameters("postgresql+psycopg://u:p@localhost:5432/shuddho_coworker_test")
    assert params["hostaddr"] == "127.0.0.1"
    assert params["host"] == "127.0.0.1"
    assert params["dbname"] == "shuddho_coworker_test"
    assert params["port"] == 5432
    assert params["connect_timeout"] == 5
    assert "statement_timeout" in params["options"]


def test_advisor_inventory_is_exactly_32_unique_named_constraints():
    assert len(FINDINGS) == len(set(FINDINGS)) == 32
    assert ("cw_tasks", "cw_tasks_workspace_id_fkey") in FINDINGS
    assert ("cw_conversation_messages", "cw_conversation_messages_conversation_id_owner_id_fkey") in FINDINGS


def test_measured_plan_is_reduced_to_non_sensitive_metrics():
    raw = [{"Planning Time": 0.2, "Execution Time": 0.3, "Plan": {
        "Node Type": "Bitmap Heap Scan", "Actual Rows": 5, "Actual Loops": 1,
        "Shared Hit Blocks": 2, "Shared Read Blocks": 0,
        "Filter": "owner_id = 'synthetic-private-marker'",
        "Plans": [{"Node Type": "Bitmap Index Scan", "Index Cond": "synthetic-private-marker"}],
    }}]
    result = summarize_plan(raw)
    assert result == {
        "execution_ms": 0.3, "planning_ms": 0.2, "actual_rows": 5,
        "shared_hit_blocks": 2, "shared_read_blocks": 0,
        "node_types": ["Bitmap Heap Scan", "Bitmap Index Scan"],
    }
    assert "synthetic-private-marker" not in str(result)


@pytest.mark.parametrize("bad", [None, [], [{}], [{"Plan": {}}], [{"Plan": {"Node Type": "Seq Scan"}, "Execution Time": float("nan")} ]])
def test_missing_or_invalid_measurement_is_not_zero(bad):
    with pytest.raises(ValueError, match="EXPLAIN"):
        summarize_plan(bad)

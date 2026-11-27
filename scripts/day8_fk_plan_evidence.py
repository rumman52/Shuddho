"""Read-only FK lookup-plan evidence for an explicitly disposable PostgreSQL database.

This is a diagnostic, not an index recommendation or a release gate. It never
writes data, changes indexes, or queries an approved hosted/staging endpoint.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from urllib.parse import unquote, urlsplit

SCHEMA = "shuddho_coworker"
# Supabase performance-advisor snapshot, 2026-11-27T19:54:21Z.
FINDINGS = (
    ("cw_action_proposals", "cw_action_proposals_promoted_action_id_fkey"),
    ("cw_action_proposals", "cw_action_proposals_promotion_connection_id_fkey"),
    ("cw_agent_runs", "cw_agent_runs_workspace_id_fkey"),
    ("cw_browser_push_deliveries", "cw_browser_push_deliveries_subscription_id_fkey"),
    ("cw_conversation_messages", "cw_conversation_messages_conversation_id_owner_id_fkey"),
    ("cw_documents", "cw_documents_workspace_id_fkey"),
    ("cw_external_actions", "cw_external_actions_connection_id_fkey"),
    ("cw_fly_patch_proposals", "cw_fly_patch_proposals_project_id_owner_id_fkey"),
    ("cw_fly_patch_reviews", "cw_fly_patch_reviews_project_id_owner_id_fkey"),
    ("cw_fly_workspace_manifests", "cw_fly_workspace_manifests_project_id_owner_id_fkey"),
    ("cw_github_connect_attempts", "fk_cw_github_attempt_project_owner"),
    ("cw_github_repository_bindings", "fk_cw_github_binding_installation_owner"),
    ("cw_github_repository_bindings", "fk_cw_github_binding_project_owner"),
    ("cw_memory_proposals", "cw_memory_proposals_accepted_fact_id_fkey"),
    ("cw_model_attempts", "cw_model_attempts_owner_id_fkey"),
    ("cw_notifications", "cw_notifications_workspace_id_fkey"),
    ("cw_project_resources", "cw_project_resources_project_id_owner_id_fkey"),
    ("cw_restaurant_reservation_intents", "fk_cw_restaurant_reservation_intents_transaction_owner"),
    ("cw_shopping_cart_intents", "fk_cw_shopping_cart_intents_transaction_owner"),
    ("cw_shopping_cart_verifications", "fk_cw_shopping_cart_verifications_transaction_owner"),
    ("cw_shopping_checkout_bindings", "fk_cw_shopping_checkout_bindings_transaction_owner"),
    ("cw_shopping_checkout_bindings", "fk_cw_shopping_checkout_bindings_verification"),
    ("cw_tasks", "cw_tasks_workspace_id_fkey"),
    ("cw_transaction_events", "fk_cw_transaction_events_transaction_owner"),
    ("cw_transaction_execution_links", "fk_cw_transaction_execution_links_transaction_owner"),
    ("cw_transaction_reconciliation_evidence", "fk_cw_transaction_reconciliation_transaction_owner"),
    ("cw_transaction_revisions", "fk_cw_transaction_revisions_transaction_owner"),
    ("cw_transaction_terms", "fk_cw_transaction_terms_transaction_owner"),
    ("cw_travel_booking_bindings", "fk_cw_travel_booking_bindings_transaction_owner"),
    ("cw_travel_booking_bindings", "fk_cw_travel_booking_bindings_verification"),
    ("cw_travel_quote_intents", "fk_cw_travel_quote_intents_transaction_owner"),
    ("cw_travel_quote_verifications", "fk_cw_travel_quote_verifications_transaction_owner"),
)


def connection_parameters(url: str) -> dict:
    error = "FK plan evidence requires a disposable loopback PostgreSQL test database"
    try:
        parsed = urlsplit(url)
        port = parsed.port or 5432
        database = unquote(parsed.path.removeprefix("/"))
        if (
            parsed.scheme != "postgresql+psycopg"
            or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
            or "?" in url or "#" in url
            or not parsed.username or parsed.password is None
            or not re.fullmatch(r"(?:[a-z][a-z0-9_]*_test|day2_dual_0071_[0-9a-f]{20})", database)
        ):
            raise ValueError(error)
        host = "127.0.0.1" if parsed.hostname == "localhost" else parsed.hostname
        return {
            "host": host, "hostaddr": host, "port": port, "dbname": database,
            "user": unquote(parsed.username), "password": unquote(parsed.password),
            "connect_timeout": 5, "sslmode": "disable",
            "options": "-c statement_timeout=5000 -c lock_timeout=1000 -c search_path=pg_catalog",
        }
    except (AttributeError, TypeError, ValueError):
        raise ValueError(error) from None


def summarize_plan(raw: object) -> dict:
    error = "EXPLAIN did not return a complete measured plan"
    if not isinstance(raw, list) or len(raw) != 1 or not isinstance(raw[0], dict):
        raise ValueError(error)
    envelope = raw[0]
    root = envelope.get("Plan")
    if not isinstance(root, dict):
        raise ValueError(error)

    def number(value, *, integer=False):
        if type(value) not in (int, float) or (integer and type(value) is not int):
            raise ValueError(error)
        if not math.isfinite(value) or value < 0:
            raise ValueError(error)
        return value

    nodes = []
    pending = [root]
    while pending:
        node = pending.pop()
        if not isinstance(node, dict) or not isinstance(node.get("Node Type"), str):
            raise ValueError(error)
        nodes.append(node["Node Type"])
        children = node.get("Plans", [])
        if not isinstance(children, list):
            raise ValueError(error)
        pending.extend(reversed(children))
    if root.get("Actual Loops") != 1:
        raise ValueError(error)
    return {
        "execution_ms": number(envelope.get("Execution Time")),
        "planning_ms": number(envelope.get("Planning Time")),
        "actual_rows": number(root.get("Actual Rows")),
        "shared_hit_blocks": number(root.get("Shared Hit Blocks"), integer=True),
        "shared_read_blocks": number(root.get("Shared Read Blocks"), integer=True),
        "node_types": nodes,
    }


def collect(url: str) -> dict:
    params = connection_parameters(url)  # Reject unsafe endpoints before importing or connecting.
    import psycopg
    from psycopg import sql

    findings = []
    with psycopg.connect(**params) as db:
        db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        revision = db.execute("SELECT version_num FROM shuddho_coworker.cw_alembic_version ORDER BY version_num").fetchall()
        version = db.execute("SHOW server_version_num").fetchone()[0]
        for table, constraint in FINDINGS:
            entry = {"table": table, "constraint": constraint}
            try:
                # Nested transactions are savepoints. A timeout in one probe cannot
                # turn a later missing measurement into a measured zero.
                with db.transaction():
                    catalog = db.execute("""
                        SELECT array_agg(a.attname::text ORDER BY k.ord), c.reltuples::bigint
                        FROM pg_catalog.pg_constraint f
                        JOIN pg_catalog.pg_class c ON c.oid = f.conrelid
                        JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
                        CROSS JOIN LATERAL unnest(f.conkey) WITH ORDINALITY AS k(attnum, ord)
                        JOIN pg_catalog.pg_attribute a ON a.attrelid = c.oid AND a.attnum = k.attnum
                        WHERE n.nspname = %s AND c.relname = %s AND f.conname = %s AND f.contype = 'f'
                        GROUP BY c.oid, c.reltuples
                    """, (SCHEMA, table, constraint)).fetchone()
                    if catalog is None:
                        entry["status"] = "constraint_missing"
                    else:
                        columns, row_estimate = catalog
                        entry["columns"] = columns
                        entry["table_rows_estimate"] = row_estimate if row_estimate >= 0 else None
                        identifiers = [sql.Identifier(column) for column in columns]
                        relation = sql.Identifier(SCHEMA, table)
                        predicate = sql.SQL(" AND ").join(sql.SQL("{} IS NOT NULL").format(c) for c in identifiers)
                        sample = db.execute(sql.SQL("SELECT {} FROM {} WHERE {} LIMIT 1").format(
                            sql.SQL(", ").join(identifiers), relation, predicate,
                        )).fetchone()
                        if sample is None:
                            entry["status"] = "unavailable_no_nonnull_child_key"
                        else:
                            equality = sql.SQL(" AND ").join(sql.SQL("{} = %s").format(c) for c in identifiers)
                            plan = db.execute(sql.SQL("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) SELECT 1 FROM {} WHERE {}").format(
                                relation, equality,
                            ), sample).fetchone()[0]
                            entry["measurement"] = summarize_plan(plan)
                            entry["status"] = "measured"
            except psycopg.Error as exc:
                entry["status"] = "unavailable_query_error"
                entry["sqlstate"] = exc.sqlstate
            except ValueError:
                entry["status"] = "unavailable_invalid_plan"
            findings.append(entry)
    return {
        "schema_version": 1,
        "advisor_snapshot_utc": "2026-11-27T19:54:21Z",
        "scope": "disposable_fk_equality_probe_not_workload_qualification",
        "postgres_version_num": version,
        "schema_revisions": [row[0] for row in revision],
        "finding_count": len(findings),
        "measured_count": sum(row["status"] == "measured" for row in findings),
        "findings": findings,
        "index_changes_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--disposable-confirmed", action="store_true", required=True)
    parser.parse_args()
    try:
        result = collect(os.environ.get("SHUDDHO_TEST_POSTGRES_URL", ""))
    except Exception:
        # Never echo a connection URL, database error, or bound key.
        print("FK plan collection failed; inspect the disposable test environment.", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0 if result["measured_count"] == result["finding_count"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

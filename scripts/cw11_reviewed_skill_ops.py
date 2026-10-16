"""Trusted CW-11 reviewed-skill operator controls.

This CLI is deliberately database/operator scoped. It is not exposed to the
Agent planner or workspace API, and it never grants a model tool. Use it only
from the controlled deployment/staging environment with the database identity
reserved for release operations.
"""
from __future__ import annotations

import argparse
import json

from services.coworker.config import Settings
from services.coworker.database import session_factory
from services.coworker.errors import CoworkerError
from services.coworker.repository import Repository
from services.coworker.reviewed_skill_registry import (
    REVIEWED_RESEARCH_SKILL,
    REVIEWED_RESEARCH_TASK_WORKFLOW_VERSION,
    build_reviewed_publication,
)


def repository_from_env() -> tuple[Repository, Settings]:
    settings = Settings.from_env()
    return Repository(session_factory(settings.database_url), settings), settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Operate the trusted CW-11 reviewed skill registry.")
    sub = parser.add_subparsers(dest="command", required=True)

    publish = sub.add_parser("publish", help="Persist a reviewed publication without selecting it.")
    publish.add_argument("--publication-version", required=True)
    publish.add_argument("--source-revision", required=True)
    publish.add_argument("--rollback-target-version")
    publish.add_argument("--actor-reference", required=True)
    publish.add_argument("--reason", required=True)

    select = sub.add_parser("select", help="Explicitly select one already-published version.")
    select.add_argument("--publication-version", required=True)
    select.add_argument("--worker-source-revision", required=True)
    select.add_argument("--actor-reference", required=True)
    select.add_argument("--reason", required=True)

    rollback = sub.add_parser("rollback", help="Explicitly roll back to the publication's declared target.")
    rollback.add_argument("--target-publication-version", required=True)
    rollback.add_argument("--worker-source-revision", required=True)
    rollback.add_argument("--actor-reference", required=True)
    rollback.add_argument("--reason", required=True)

    inventory = sub.add_parser("inventory", help="Print the durable worker-version inventory.")
    inventory.add_argument("--task-queue")

    drain = sub.add_parser("drain", help="Request cooperative drain for one worker source revision.")
    drain.add_argument("--task-queue", required=True)
    drain.add_argument("--source-revision", required=True)
    drain.add_argument("--actor-reference", required=True)
    drain.add_argument("--reason", required=True)

    verify = sub.add_parser("verify-drain", help="Require explicit drained state for the legacy revision.")
    verify.add_argument("--task-queue", required=True)
    verify.add_argument("--old-source-revision", required=True)

    migrate = sub.add_parser("migrate-legacy", help="Rebind safe historical reviewed tasks after old-worker drain.")
    migrate.add_argument("--task-queue", required=True)
    migrate.add_argument("--old-source-revision", required=True)
    migrate.add_argument("--publication-version", required=True)
    migrate.add_argument("--actor-reference", required=True)
    migrate.add_argument("--reason", required=True)

    history = sub.add_parser("history", help="Print the append-only reviewed-skill control history.")
    history.add_argument("--limit", type=int, default=100)

    runtime = sub.add_parser("runtime", help="Print the selected reviewed publication identity.")

    args = parser.parse_args()
    repository, _settings = repository_from_env()

    try:
        if args.command == "publish":
            publication = build_reviewed_publication(
                skill_name=REVIEWED_RESEARCH_SKILL,
                publication_version=args.publication_version,
                task_workflow_version=REVIEWED_RESEARCH_TASK_WORKFLOW_VERSION,
                source_revision=args.source_revision,
                rollback_target_version=args.rollback_target_version,
            )
            result = repository.publish_reviewed_skill(
                publication,
                actor_reference=args.actor_reference,
                reason=args.reason,
            )
        elif args.command == "select":
            result = repository.select_reviewed_skill(
                REVIEWED_RESEARCH_SKILL,
                args.publication_version,
                actor_reference=args.actor_reference,
                reason=args.reason,
                worker_source_revision=args.worker_source_revision,
            )
        elif args.command == "rollback":
            result = repository.rollback_reviewed_skill(
                REVIEWED_RESEARCH_SKILL,
                args.target_publication_version,
                actor_reference=args.actor_reference,
                reason=args.reason,
                worker_source_revision=args.worker_source_revision,
            )
        elif args.command == "inventory":
            result = {"workers": repository.worker_inventory(task_queue=args.task_queue)}
        elif args.command == "drain":
            result = {
                "drain_requested": repository.request_worker_drain(
                    task_queue=args.task_queue,
                    source_revision=args.source_revision,
                    actor_reference=args.actor_reference,
                    reason=args.reason,
                )
            }
        elif args.command == "verify-drain":
            result = repository.assert_worker_drain_complete(
                task_queue=args.task_queue,
                old_source_revision=args.old_source_revision,
            )
        elif args.command == "migrate-legacy":
            result = repository.migrate_legacy_reviewed_tasks(
                task_queue=args.task_queue,
                old_source_revision=args.old_source_revision,
                publication_version=args.publication_version,
                actor_reference=args.actor_reference,
                reason=args.reason,
            )
        elif args.command == "history":
            result = {"events": repository.reviewed_control_history(limit=args.limit)}
        elif args.command == "runtime":
            result = repository.reviewed_skill_runtime_manifest()
        else:
            raise CoworkerError("skill_operator", "Unsupported operator command.", 422)
    except (CoworkerError, ValueError) as error:
        print(json.dumps({
            "status": "blocked",
            "code": getattr(error, "code", type(error).__name__),
            "error": str(error),
        }, indent=2))
        raise SystemExit(2) from None
    finally:
        repository.sessions.kw["bind"].dispose()

    print(json.dumps({
        "status": "ok",
        "command": args.command,
        "result": result,
    }, indent=2))


if __name__ == "__main__":
    main()

"""Deterministic identity for a built Coworker runtime, not a release approval."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import stat
from importlib import metadata
from pathlib import Path

_MAX_BUILD_INPUT_BYTES = 32 * 1024 * 1024


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def _file_digest(path: Path) -> str:
    # O_NONBLOCK prevents a substituted FIFO from hanging before fstat.
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_NONBLOCK"):
        raise ValueError("secure build input reading is unavailable")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_size > _MAX_BUILD_INPUT_BYTES:
                raise ValueError("build input must be a bounded regular file")
            digest = hashlib.sha256()
            total = 0
            while chunk := os.read(fd, 65536):
                total += len(chunk)
                if total > _MAX_BUILD_INPUT_BYTES:
                    raise ValueError("build input exceeds size limit")
                digest.update(chunk)
            after = os.fstat(fd)
            current = path.lstat()
            def signature(s):
                return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
            if signature(before) != signature(after) or signature(after) != signature(current) or total != before.st_size:
                raise ValueError("build input changed during fingerprinting")
            return digest.hexdigest()
        finally:
            os.close(fd)
    except OSError as exc:
        raise ValueError("build input is missing, inaccessible, or a symlink") from exc


def _identity_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 512 or value != value.strip() or any(not c.isprintable() for c in value):
        raise ValueError(f"invalid {label}")
    return value


def _distribution_inventory(distributions) -> list[list[str]]:
    if distributions is None:
        distributions = ((dist.metadata.get("Name"), dist.version) for dist in metadata.distributions())
    inventory: dict[str, str] = {}
    for name, version in distributions:
        name = _identity_text(name, "distribution name")
        if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?", name):
            raise ValueError("invalid distribution name")
        normalized = re.sub(r"[-_.]+", "-", name).lower()
        version = _identity_text(version, "distribution version")
        if normalized in inventory and inventory[normalized] != version:
            raise ValueError("conflicting distribution versions")
        inventory[normalized] = version
    return [[name, version] for name, version in sorted(inventory.items())]


def compute_build_digest(*, root: Path | None = None, source_revision: str,
                         distributions=None, python_implementation: str | None = None,
                         python_version: str | None = None, platform_identity: str | None = None) -> str:
    """Bind the source claim, lock/project bytes and observed Python installation.

    This is a deterministic metadata fingerprint, not a signature or an OCI digest.
    """
    if not isinstance(source_revision, str) or not re.fullmatch(r"[0-9a-f]{40}", source_revision):
        raise ValueError("invalid source revision")
    root = Path(root) if root is not None else Path(__file__).resolve().parents[2]
    return canonical_sha256({
        "fingerprint_version": 1,
        "source_revision": source_revision,
        "pyproject_sha256": _file_digest(root / "pyproject.toml"),
        "lock_sha256": _file_digest(root / "uv.lock"),
        "distributions": _distribution_inventory(distributions),
        "python_implementation": _identity_text(platform.python_implementation() if python_implementation is None else python_implementation, "Python implementation"),
        "python_version": _identity_text(platform.python_version() if python_version is None else python_version, "Python version"),
        "platform_identity": _identity_text(f"{platform.system().lower()}-{platform.machine().lower()}" if platform_identity is None else platform_identity, "platform identity"),
    })


def runtime_manifest_payload(settings, reviewed_skills: dict) -> dict:
    """One capability projection shared by v2 and the v3 identity builder."""
    from .config import enabled as coworker_enabled

    capabilities = {
        "coworker": coworker_enabled(),
        "work_services": settings.work_services_enabled,
        "artifact_services": settings.artifact_services_enabled,
        "agent_runtime": settings.agent_runtime_enabled,
        "conversations": settings.conversations_enabled,
        "projects": settings.projects_enabled and settings.conversations_enabled,
        "fly_github": settings.fly_github_enabled,
        "conversation_replies": settings.conversations_enabled and settings.conversation_replies_enabled and settings.chat_provider_configured,
        "grounded_conversation_replies": settings.conversations_enabled and settings.conversation_replies_enabled and settings.chat_provider_configured,
        "runtime_v3": settings.agent_runtime_v3_enabled,
        "context_retrieval": settings.context_retrieval_enabled,
        "personal_goals": settings.personal_goals_enabled,
        "automations": settings.automations_enabled,
        "intelligent_planner": settings.intelligent_planner_enabled,
        "memory": settings.agent_memory_enabled,
        "handoffs": settings.agent_handoffs_enabled,
        "multi_handoffs": settings.agent_multi_handoffs_enabled,
        "dependency_graph": settings.agent_dependency_graph_enabled,
        "parallel_execution": settings.agent_parallel_execution_enabled,
        "outcome_replan": settings.agent_outcome_replan_enabled,
        "research": settings.research_services_enabled,
        "actions": settings.actions_enabled,
        "connector_trust_boundary": settings.connector_trust_boundary_enabled,
        "connector_reads": settings.connector_reads_enabled,
        "browser": settings.browser_enabled,
        "agent_browser_read": settings.agent_browser_read_enabled,
        "code_execution": settings.code_execution_enabled,
        "agent_sandbox_tool": settings.agent_sandbox_tool_enabled,
        "action_attachments": settings.action_attachments_enabled,
        "action_reminders": settings.action_reminders_enabled,
        "action_recipients": settings.action_recipients_enabled,
        "action_document_sharing": settings.action_document_sharing_enabled,
        "action_email_threading": settings.action_email_threading_enabled,
        "action_social_publishing": settings.action_social_publishing_enabled,
        "personal_transactions": settings.personal_transactions_enabled,
        "restaurant_reservations": settings.restaurant_reservations_enabled,
        "shopping_checkout": settings.shopping_checkout_enabled,
        "travel_booking": settings.travel_booking_enabled,
        "action_selection": settings.agent_action_selection_enabled,
        "action_proposals": settings.agent_action_proposals_enabled,
        "negotiation_proposal_promotion": settings.negotiation_proposal_promotion_enabled,
        "agent_linkedin_proposals": settings.agent_linkedin_proposals_enabled,
        "browser_push": settings.browser_push_enabled,
        "reviewed_research": (
            settings.agent_reviewed_research_skill_enabled
            and reviewed_skills["research"]["state"] == "selected"
        ),
    }
    providers = []
    if settings.actions_enabled:
        providers.append("google")
        if settings.microsoft_actions_enabled:
            providers.append("microsoft")
        if settings.action_social_publishing_enabled:
            providers.append("linkedin")
        if settings.restaurant_reservations_enabled:
            providers.append("opentable")
        if settings.shopping_checkout_enabled or settings.travel_booking_enabled:
            for operation in sorted(settings.transaction_operations):
                provider, separator, kind = operation.partition(":")
                if (
                    separator
                    and kind in {"shopping_checkout_create", "travel_booking_create"}
                    and provider not in providers
                ):
                    providers.append(provider)
    return {
        "schema_version": 2,
        "source_revision": settings.source_revision,
        "environment": settings.environment,
        "capabilities": capabilities,
        # Separate configured authority outside the fixed 43 runtime-v2 flags.
        # Report the actual setting, even if another dependency blocks its use.
        "canonical_only_capabilities": {
            "suggestion_model_relevance": settings.suggestion_model_relevance_enabled,
        },
        "reviewed_skills": reviewed_skills,
        "action_providers": providers,
        "cohort": {
            "enforced": settings.cohort_enforced,
            "configured_members": len(settings.cohort_account_ids),
            "max_users": settings.cohort_max_users,
        },
    }


def build_runtime_identity(settings, repository, *, root: Path | None = None,
                           distributions=None, python_implementation: str | None = None,
                           python_version: str | None = None, platform_identity: str | None = None) -> dict:
    """Bind actual build, schema, model, queue and capability metadata."""
    provider = settings.chat_provider
    if provider not in {"deepseek", "gemma"}:
        raise ValueError("unsupported model provider")
    model = settings.deepseek_model if provider == "deepseek" else settings.gemma_model
    identity = runtime_manifest_payload(settings, repository.reviewed_skill_runtime_manifest())
    identity.update(
        schema_version=3,
        build_digest=compute_build_digest(root=root, source_revision=settings.source_revision,
                                          distributions=distributions, python_implementation=python_implementation,
                                          python_version=python_version, platform_identity=platform_identity),
        schema_revision=_identity_text(repository.current_schema_revision(), "schema revision"),
        model_provider=provider,
        model_id=_identity_text(model, "model id"),
        task_queue=_identity_text(settings.task_queue, "task queue"),
    )
    identity["runtime_identity_sha256"] = canonical_sha256(identity)
    return identity


WORKER_IDENTITY_KEYS = (
    "task_queue", "source_revision", "build_digest", "schema_revision",
    "model_provider", "model_id", "runtime_identity_sha256",
)


def qualify_worker_inventory(identity: dict, workers: list[dict]) -> dict:
    """Sanitize the observed queue and reject any uncertain worker evidence."""
    expected = {key: identity[key] for key in WORKER_IDENTITY_KEYS}
    inventory = []
    blocked = 0
    for row in workers:
        if (row.get("state") == "drained" and row.get("drained_at")
                and type(row.get("active_claim_count")) is int
                and row["active_claim_count"] == 0):
            continue
        observed = {key: row.get(key) for key in WORKER_IDENTITY_KEYS}
        if (row.get("state") != "running" or row.get("heartbeat_fresh") is not True
                or row.get("drained_at") is not None or observed != expected):
            blocked += 1
        else:
            inventory.append(observed)
    inventory.sort(key=canonical_sha256)
    return {
        "worker_fleet_ready": bool(inventory) and blocked == 0,
        "blocked_worker_count": blocked,
        "worker_inventory": inventory,
        "worker_inventory_sha256": canonical_sha256(inventory),
    }

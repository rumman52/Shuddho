from __future__ import annotations

import hashlib
import ipaddress
import json
from datetime import timedelta
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from sqlalchemy import func, or_, select

from .browser_schemas import BrowserNavigateCreate, BrowserSessionCreate
from .errors import CoworkerError
from .models import Account, AuditEvent, BrowserCommand, BrowserSession, Workspace, utcnow
from .repository import aware, iso, not_found

TERMINAL_BROWSER_STATES = {"cancelled", "completed", "expired", "failed"}
ACTIVE_BROWSER_STATES = {"prepared", "queued", "running", "takeover"}
BLOCKED_HOST_SUFFIXES = (
    ".localhost",
    ".local",
    ".internal",
    ".home",
    ".lan",
)
BLOCKED_HOSTS = {
    "localhost",
    "metadata.google.internal",
    "metadata",
}


def validate_resolved_addresses(hostname: str, addresses: list[str]) -> list[str]:
    """Fail closed unless DNS resolved only to public routable IP addresses."""
    if not addresses:
        raise CoworkerError("browser_dns_unresolved", "The browser target did not resolve to an allowed address.", 403)
    clean: list[str] = []
    for raw in addresses:
        try:
            value = ipaddress.ip_address(raw)
        except ValueError:
            raise CoworkerError("browser_dns_invalid", "The browser target resolved to an invalid address.", 403) from None
        if not value.is_global:
            raise CoworkerError(
                "browser_network_blocked",
                "The browser target resolved to a private or reserved address.",
                403,
            )
        text = value.compressed
        if text not in clean:
            clean.append(text)
    if len(clean) > 16:
        raise CoworkerError("browser_dns_invalid", "The browser target resolved to too many addresses.", 403)
    return clean


def _bounded_observation(value: dict) -> dict:
    final_url = value.get("final_url")
    title = value.get("title")
    redirects = value.get("redirect_chain", [])
    resolved = value.get("resolved_ips", {})
    if not isinstance(final_url, str):
        raise CoworkerError("browser_observation_invalid", "The browser worker returned an invalid final URL.", 409)
    if title is not None and (not isinstance(title, str) or len(title) > 300):
        raise CoworkerError("browser_observation_invalid", "The browser worker returned an invalid page title.", 409)
    if not isinstance(redirects, list) or len(redirects) > 10 or any(not isinstance(item, str) for item in redirects):
        raise CoworkerError("browser_observation_invalid", "The browser worker returned an invalid redirect chain.", 409)
    if not isinstance(resolved, dict) or len(resolved) > 12:
        raise CoworkerError("browser_observation_invalid", "The browser worker returned invalid DNS evidence.", 409)
    normalized_resolved: dict[str, list[str]] = {}
    for host, addresses in resolved.items():
        if not isinstance(host, str) or not isinstance(addresses, list):
            raise CoworkerError("browser_observation_invalid", "The browser worker returned invalid DNS evidence.", 409)
        normalized_resolved[host.lower().rstrip(".")] = validate_resolved_addresses(host, addresses)
    return {
        "final_url": final_url,
        "title": title,
        "redirect_chain": redirects,
        "resolved_ips": normalized_resolved,
    }


def _digest(value: dict) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def normalize_browser_target(raw_url: str) -> tuple[str, str]:
    try:
        parsed = urlsplit(raw_url)
    except ValueError:
        raise CoworkerError("browser_target_invalid", "This browser target URL is invalid.", 400) from None
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise CoworkerError(
            "browser_target_invalid",
            "Browser targets must be clean HTTPS URLs without credentials or fragments.",
            400,
        )
    hostname = parsed.hostname.rstrip(".").lower()
    if not hostname or len(hostname) > 253:
        raise CoworkerError("browser_target_invalid", "This browser target host is invalid.", 400)
    try:
        ascii_host = hostname.encode("idna").decode("ascii")
    except UnicodeError:
        raise CoworkerError("browser_target_invalid", "This browser target host is invalid.", 400) from None
    if ascii_host in BLOCKED_HOSTS or any(ascii_host.endswith(value) for value in BLOCKED_HOST_SUFFIXES):
        raise CoworkerError("browser_target_blocked", "This browser target is not allowed.", 403)
    try:
        ipaddress.ip_address(ascii_host)
    except ValueError:
        pass
    else:
        # Direct-IP browsing is deliberately excluded from the first broker
        # slice. The isolated worker must resolve DNS and re-check every
        # address/redirect before network egress.
        raise CoworkerError("browser_target_blocked", "Direct IP browser targets are not allowed.", 403)
    try:
        port = parsed.port
    except ValueError:
        raise CoworkerError("browser_target_invalid", "This browser target port is invalid.", 400) from None
    if port not in {None, 443}:
        raise CoworkerError("browser_target_blocked", "Only standard HTTPS browser targets are allowed.", 403)
    netloc = ascii_host
    path = parsed.path or "/"
    normalized = urlunsplit(("https", netloc, path, parsed.query, ""))
    origin = "https://" + ascii_host
    if len(normalized) > 4096 or len(origin) > 512:
        raise CoworkerError("browser_target_invalid", "This browser target URL is too long.", 400)
    return normalized, origin


class BrowserRepository:
    def __init__(self, sessions, settings):
        self.sessions = sessions
        self.settings = settings

    @staticmethod
    def _dto(row: BrowserSession) -> dict:
        state = row.state
        if state not in TERMINAL_BROWSER_STATES and aware(row.expires_at) <= utcnow():
            state = "expired"
        return {
            "id": row.id,
            "purpose": row.purpose,
            "start_url": row.start_url,
            "allowed_origins": list(row.allowed_origins or []),
            "state": state,
            "takeover_required": row.takeover_required,
            "cancel_requested": row.cancel_requested,
            "last_url": row.last_url,
            "last_title": row.last_title,
            "error_code": row.error_code,
            "created_at": iso(row.created_at),
            "updated_at": iso(row.updated_at),
            "expires_at": iso(row.expires_at),
            "execution": {
                "worker_attached": bool(row.worker_session_ref),
                "network_revalidation_required": True,
                "arbitrary_script_execution": False,
                "downloads_enabled": False,
            },
        }

    def _require_enabled(self):
        if not self.settings.browser_enabled:
            raise CoworkerError(
                "browser_disabled",
                "The supervised browser is not enabled in this deployment.",
                503,
            )


    def validate_worker_network_target(
        self,
        worker_id: str,
        command_id: str,
        raw_url: str,
        addresses: list[str],
    ) -> dict:
        """Trusted service check performed immediately before browser egress."""
        self._require_enabled()
        normalized, origin = normalize_browser_target(raw_url)
        hostname = (urlsplit(normalized).hostname or "").lower().rstrip(".")
        checked = validate_resolved_addresses(hostname, addresses)
        now = utcnow()
        with self.sessions() as db:
            command = db.scalar(select(BrowserCommand).where(
                BrowserCommand.id == command_id,
            ))
            if command is None:
                raise not_found()
            session = db.scalar(select(BrowserSession).where(
                BrowserSession.id == command.session_id,
                BrowserSession.owner_id == command.owner_id,
            ))
            if (
                command.state != "running"
                or command.claimed_by != worker_id
                or command.lease_until is None
                or aware(command.lease_until) <= now
            ):
                raise CoworkerError(
                    "browser_worker_claim_invalid",
                    "This browser command is not actively owned by this worker.",
                    409,
                )
            if (
                session is None
                or session.cancel_requested
                or session.takeover_required
                or session.state in TERMINAL_BROWSER_STATES
                or aware(session.expires_at) <= now
            ):
                raise CoworkerError(
                    "browser_session_closed",
                    "This browser session is not available for network access.",
                    409,
                )
            if origin not in set(session.allowed_origins or []):
                raise CoworkerError(
                    "browser_origin_not_allowed",
                    "This network request leaves the session's approved origin.",
                    403,
                )
        return {
            "url": normalized,
            "origin": origin,
            "hostname": hostname,
            "resolved_ips": checked,
        }

    def create(self, owner: str, request: BrowserSessionCreate, idempotency_key: str) -> tuple[dict, bool]:
        self._require_enabled()
        start_url, origin = normalize_browser_target(request.start_url)
        fingerprint = _digest({"purpose": request.purpose, "start_url": start_url})
        with self.sessions.begin() as db:
            account = db.get(Account, owner)
            workspace_id = db.scalar(select(Workspace.id).where(Workspace.owner_id == owner))
            if account is None or workspace_id is None:
                raise not_found()
            previous = db.scalar(select(BrowserSession).where(
                BrowserSession.owner_id == owner,
                BrowserSession.idempotency_key == idempotency_key,
            ))
            if previous is not None:
                if previous.fingerprint != fingerprint:
                    raise CoworkerError(
                        "idempotency_conflict",
                        "This request key belongs to a different browser session.",
                        409,
                    )
                return self._dto(previous), False
            active = db.scalar(select(func.count()).select_from(BrowserSession).where(
                BrowserSession.owner_id == owner,
                BrowserSession.state.in_(tuple(ACTIVE_BROWSER_STATES)),
                BrowserSession.expires_at > utcnow(),
            )) or 0
            if active >= self.settings.max_active_browser_sessions:
                raise CoworkerError(
                    "browser_session_limit",
                    "Close an active browser session before starting another.",
                    429,
                )
            row = BrowserSession(
                id=str(uuid4()),
                owner_id=owner,
                workspace_id=workspace_id,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                purpose=request.purpose,
                start_url=start_url,
                start_origin=origin,
                allowed_origins=[origin],
                state="prepared",
                expires_at=utcnow() + timedelta(seconds=self.settings.browser_session_ttl_seconds),
            )
            db.add(row)
            db.add(AuditEvent(
                id=str(uuid4()),
                owner_id=owner,
                resource_id=row.id,
                action="browser_session.prepared",
            ))
            # SQLAlchemy column defaults (created_at/updated_at) are populated
            # during flush. Materialize them before serializing the new row.
            db.flush()
            return self._dto(row), True

    def list(self, owner: str) -> list[dict]:
        self._require_enabled()
        with self.sessions() as db:
            rows = db.scalars(select(BrowserSession).where(
                BrowserSession.owner_id == owner,
            ).order_by(BrowserSession.created_at.desc()).limit(50)).all()
            return [self._dto(row) for row in rows]

    def get(self, owner: str, session_id: str) -> dict:
        self._require_enabled()
        with self.sessions() as db:
            row = db.scalar(select(BrowserSession).where(
                BrowserSession.id == session_id,
                BrowserSession.owner_id == owner,
            ))
            if row is None:
                raise not_found()
            return self._dto(row)

    def prepare_navigation(self, owner: str, session_id: str, request: BrowserNavigateCreate) -> dict:
        self._require_enabled()
        target_url, origin = normalize_browser_target(request.url)
        with self.sessions.begin() as db:
            row = db.scalar(select(BrowserSession).where(
                BrowserSession.id == session_id,
                BrowserSession.owner_id == owner,
            ).with_for_update())
            if row is None:
                raise not_found()
            if aware(row.expires_at) <= utcnow():
                row.state = "expired"
                raise CoworkerError("browser_session_expired", "This browser session expired.", 410)
            if row.state in TERMINAL_BROWSER_STATES or row.cancel_requested:
                raise CoworkerError("browser_session_closed", "This browser session is no longer active.", 409)
            if row.state == "takeover":
                raise CoworkerError("browser_takeover_active", "Resume the session after user takeover.", 409)
            if origin not in set(row.allowed_origins or []):
                raise CoworkerError(
                    "browser_origin_not_allowed",
                    "This navigation leaves the session's approved origin.",
                    409,
                )
            sequence = (db.scalar(select(func.max(BrowserCommand.sequence)).where(
                BrowserCommand.session_id == session_id,
            )) or 0) + 1
            command = BrowserCommand(
                id=str(uuid4()),
                session_id=session_id,
                owner_id=owner,
                sequence=sequence,
                kind="navigate",
                target_url=target_url,
                target_origin=origin,
                payload={
                    "policy_version": "browser-v1",
                    "requires_dns_ip_validation": True,
                    "redirect_validation": True,
                    "allow_downloads": False,
                    "allow_script_injection": False,
                },
                state="prepared",
            )
            db.add(command)
            row.updated_at = utcnow()
            db.add(AuditEvent(
                id=str(uuid4()), owner_id=owner, resource_id=row.id,
                action="browser_navigation.prepared",
            ))
            return {
                "id": command.id,
                "sequence": sequence,
                "kind": command.kind,
                "target_url": target_url,
                "target_origin": origin,
                "state": command.state,
                "policy": command.payload,
            }

    def request_takeover(self, owner: str, session_id: str, reason: str) -> dict:
        self._require_enabled()
        now = utcnow()
        with self.sessions.begin() as db:
            row = db.scalar(select(BrowserSession).where(
                BrowserSession.id == session_id,
                BrowserSession.owner_id == owner,
            ).with_for_update())
            if row is None:
                raise not_found()
            if aware(row.expires_at) <= now or row.state in TERMINAL_BROWSER_STATES:
                raise CoworkerError("browser_session_closed", "This browser session is no longer active.", 409)
            row.state = "takeover"
            row.takeover_required = True
            row.worker_session_ref = None
            row.updated_at = now
            for command in db.scalars(select(BrowserCommand).where(
                BrowserCommand.session_id == session_id,
                BrowserCommand.state == "running",
            ).with_for_update()).all():
                command.state = "cancelled"
                command.error_code = "takeover_requested"
                command.finished_at = now
                command.lease_until = None
                command.claimed_by = None
            db.add(AuditEvent(
                id=str(uuid4()), owner_id=owner, resource_id=row.id,
                action="browser_takeover." + reason,
            ))
            return self._dto(row)

    def resume(self, owner: str, session_id: str) -> dict:
        self._require_enabled()
        with self.sessions.begin() as db:
            row = db.scalar(select(BrowserSession).where(
                BrowserSession.id == session_id,
                BrowserSession.owner_id == owner,
            ).with_for_update())
            if row is None:
                raise not_found()
            if row.state != "takeover" or not row.takeover_required:
                raise CoworkerError("browser_takeover_not_active", "This session is not waiting for user takeover.", 409)
            if aware(row.expires_at) <= utcnow():
                row.state = "expired"
                raise CoworkerError("browser_session_expired", "This browser session expired.", 410)
            row.state = "prepared"
            row.takeover_required = False
            row.updated_at = utcnow()
            db.add(AuditEvent(
                id=str(uuid4()), owner_id=owner, resource_id=row.id,
                action="browser_takeover.resumed",
            ))
            return self._dto(row)

    def cancel(self, owner: str, session_id: str) -> dict:
        self._require_enabled()
        now = utcnow()
        with self.sessions.begin() as db:
            row = db.scalar(select(BrowserSession).where(
                BrowserSession.id == session_id,
                BrowserSession.owner_id == owner,
            ).with_for_update())
            if row is None:
                raise not_found()
            if row.state not in TERMINAL_BROWSER_STATES:
                row.cancel_requested = True
                row.state = "cancelled"
                row.takeover_required = False
                row.worker_session_ref = None
                row.updated_at = now
                for command in db.scalars(select(BrowserCommand).where(
                    BrowserCommand.session_id == session_id,
                    BrowserCommand.state.in_(("prepared", "running")),
                ).with_for_update()).all():
                    command.state = "cancelled"
                    command.error_code = "session_cancelled"
                    command.finished_at = now
                    command.lease_until = None
                    command.claimed_by = None
                db.add(AuditEvent(
                    id=str(uuid4()), owner_id=owner, resource_id=row.id,
                    action="browser_session.cancelled",
                ))
            return self._dto(row)


    # Trusted isolated-worker boundary. These methods are intentionally not
    # mounted on the end-user API.
    def claim_commands(self, worker_id: str, limit: int = 5) -> list[dict]:
        self._require_enabled()
        if not worker_id or len(worker_id) > 64:
            raise CoworkerError("browser_worker_invalid", "The browser worker identity is invalid.", 403)
        now = utcnow()
        with self.sessions.begin() as db:
            rows = db.scalars(
                select(BrowserCommand)
                .join(BrowserSession, BrowserSession.id == BrowserCommand.session_id)
                .where(
                    BrowserSession.cancel_requested.is_(False),
                    BrowserSession.takeover_required.is_(False),
                    BrowserSession.state.in_(("prepared", "running", "queued")),
                    BrowserSession.expires_at > now,
                    BrowserCommand.state.in_(("prepared", "running")),
                    BrowserCommand.attempts < self.settings.browser_command_max_attempts,
                    or_(BrowserCommand.lease_until.is_(None), BrowserCommand.lease_until < now),
                )
                .order_by(BrowserCommand.created_at)
                .limit(max(1, min(limit, 10)))
                .with_for_update(skip_locked=True)
            ).all()
            claimed: list[dict] = []
            claimed_sessions: set[str] = set()
            for command in rows:
                if command.session_id in claimed_sessions:
                    continue
                earlier_pending = db.scalar(select(func.count()).select_from(BrowserCommand).where(
                    BrowserCommand.session_id == command.session_id,
                    BrowserCommand.sequence < command.sequence,
                    BrowserCommand.state.in_(("prepared", "running")),
                )) or 0
                if earlier_pending:
                    continue
                session = db.get(BrowserSession, command.session_id)
                command.state = "running"
                command.attempts += 1
                command.claimed_by = worker_id
                command.lease_until = now + timedelta(seconds=self.settings.browser_worker_lease_seconds)
                command.started_at = command.started_at or now
                session.state = "running"
                session.worker_session_ref = worker_id
                session.updated_at = now
                claimed_sessions.add(command.session_id)
                claimed.append({
                    "id": command.id,
                    "session_id": command.session_id,
                    "owner_id": command.owner_id,
                    "sequence": command.sequence,
                    "kind": command.kind,
                    "target_url": command.target_url,
                    "target_origin": command.target_origin,
                    "allowed_origins": list(session.allowed_origins or []),
                    "expires_at": iso(session.expires_at),
                    "policy": dict(command.payload or {}),
                    "attempt": command.attempts,
                })
            return claimed

    def worker_control(self, worker_id: str, command_id: str) -> dict:
        """Return the authoritative control-plane action for an in-flight worker command."""
        self._require_enabled()
        now = utcnow()
        with self.sessions.begin() as db:
            command = db.scalar(select(BrowserCommand).where(
                BrowserCommand.id == command_id,
            ).with_for_update())
            if command is None:
                raise not_found()
            session = db.scalar(select(BrowserSession).where(
                BrowserSession.id == command.session_id,
                BrowserSession.owner_id == command.owner_id,
            ).with_for_update())
            if session is None:
                raise not_found()

            if session.cancel_requested or session.state == "cancelled":
                if command.state in {"prepared", "running"}:
                    command.state = "cancelled"
                    command.error_code = "session_cancelled"
                    command.finished_at = now
                    command.lease_until = None
                    command.claimed_by = None
                session.worker_session_ref = None
                return {"action": "stop", "reason": "session_cancelled"}

            if session.takeover_required or session.state == "takeover":
                if command.state == "running":
                    command.state = "cancelled"
                    command.error_code = "takeover_requested"
                    command.finished_at = now
                    command.lease_until = None
                    command.claimed_by = None
                session.worker_session_ref = None
                return {"action": "pause", "reason": "takeover_requested"}

            if aware(session.expires_at) <= now:
                session.state = "expired"
                session.worker_session_ref = None
                session.updated_at = now
                if command.state in {"prepared", "running"}:
                    command.state = "failed"
                    command.error_code = "session_expired"
                    command.finished_at = now
                    command.lease_until = None
                    command.claimed_by = None
                return {"action": "stop", "reason": "session_expired"}

            if session.state in TERMINAL_BROWSER_STATES:
                session.worker_session_ref = None
                return {"action": "stop", "reason": "session_" + session.state}

            if (
                command.state != "running"
                or command.claimed_by != worker_id
                or command.lease_until is None
                or aware(command.lease_until) <= now
            ):
                raise CoworkerError(
                    "browser_worker_claim_invalid",
                    "This browser command is not actively owned by this worker.",
                    409,
                )
            return {
                "action": "continue",
                "reason": None,
                "lease_until": iso(command.lease_until),
                "session_expires_at": iso(session.expires_at),
            }

    def complete_command(self, worker_id: str, command_id: str, observation: dict) -> dict:
        self._require_enabled()
        checked = _bounded_observation(observation)
        now = utcnow()
        with self.sessions.begin() as db:
            command = db.scalar(select(BrowserCommand).where(
                BrowserCommand.id == command_id,
            ).with_for_update())
            if command is None:
                raise not_found()
            session = db.scalar(select(BrowserSession).where(
                BrowserSession.id == command.session_id,
                BrowserSession.owner_id == command.owner_id,
            ).with_for_update())
            if session is None:
                raise not_found()
            if session.takeover_required or session.state == "takeover":
                if command.state == "running":
                    command.state = "cancelled"
                    command.error_code = "takeover_requested"
                    command.finished_at = now
                    command.lease_until = None
                    command.claimed_by = None
                session.worker_session_ref = None
                raise CoworkerError("browser_takeover_active", "Browser execution paused for user takeover.", 409)
            if session.cancel_requested or session.state in TERMINAL_BROWSER_STATES:
                if command.state == "running":
                    command.state = "cancelled"
                    command.error_code = "session_cancelled"
                    command.finished_at = now
                    command.lease_until = None
                    command.claimed_by = None
                session.worker_session_ref = None
                raise CoworkerError("browser_session_closed", "This browser session is no longer active.", 409)
            if command.state != "running" or command.claimed_by != worker_id:
                raise CoworkerError("browser_worker_claim_invalid", "This browser command is not owned by this worker.", 409)
            if aware(session.expires_at) <= now:
                session.state = "expired"
                command.state = "failed"
                command.error_code = "session_expired"
                command.finished_at = now
                command.lease_until = None
                command.claimed_by = None
                raise CoworkerError("browser_session_expired", "This browser session expired.", 410)

            urls = [*checked["redirect_chain"], checked["final_url"]]
            normalized_chain: list[str] = []
            for raw_url in urls:
                normalized, origin = normalize_browser_target(raw_url)
                if origin not in set(session.allowed_origins or []):
                    command.state = "failed"
                    command.error_code = "redirect_origin_blocked"
                    command.finished_at = now
                    command.lease_until = None
                    command.claimed_by = None
                    session.state = "failed"
                    session.error_code = "redirect_origin_blocked"
                    raise CoworkerError("browser_origin_not_allowed", "The browser worker observed a redirect outside the approved origin.", 409)
                hostname = (urlsplit(normalized).hostname or "").lower().rstrip(".")
                if hostname not in checked["resolved_ips"]:
                    raise CoworkerError(
                        "browser_dns_evidence_missing",
                        "The browser worker did not provide DNS evidence for every observed host.",
                        409,
                    )
                normalized_chain.append(normalized)

            command.result = {
                "final_url": normalized_chain[-1],
                "title": checked["title"],
                "redirect_chain": normalized_chain[:-1],
                "resolved_ips": checked["resolved_ips"],
            }
            command.state = "succeeded"
            command.error_code = None
            command.finished_at = now
            command.lease_until = None
            command.claimed_by = None
            session.state = "prepared"
            session.worker_session_ref = None
            session.last_url = normalized_chain[-1]
            session.last_title = checked["title"]
            session.updated_at = now
            db.add(AuditEvent(
                id=str(uuid4()), owner_id=session.owner_id, resource_id=session.id,
                action="browser_navigation.succeeded",
            ))
            return {
                "id": command.id,
                "state": command.state,
                "result": dict(command.result or {}),
            }

    def fail_command(self, worker_id: str, command_id: str, error_code: str) -> dict:
        self._require_enabled()
        allowed = {
            "navigation_failed",
            "network_blocked",
            "dns_failed",
            "worker_interrupted",
            "unsupported_site",
        }
        if error_code not in allowed:
            error_code = "navigation_failed"
        now = utcnow()
        with self.sessions.begin() as db:
            command = db.scalar(select(BrowserCommand).where(
                BrowserCommand.id == command_id,
            ).with_for_update())
            if command is None:
                raise not_found()
            if command.state != "running" or command.claimed_by != worker_id:
                raise CoworkerError("browser_worker_claim_invalid", "This browser command is not owned by this worker.", 409)
            session = db.scalar(select(BrowserSession).where(
                BrowserSession.id == command.session_id,
                BrowserSession.owner_id == command.owner_id,
            ).with_for_update())
            command.state = "failed"
            command.error_code = error_code
            command.finished_at = now
            command.lease_until = None
            command.claimed_by = None
            if session is not None and session.state not in TERMINAL_BROWSER_STATES:
                session.state = "failed"
                session.worker_session_ref = None
                session.error_code = error_code
                session.updated_at = now
            return {"id": command.id, "state": command.state, "error_code": error_code}

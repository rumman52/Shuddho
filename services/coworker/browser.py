from __future__ import annotations

import hashlib
import ipaddress
import json
from datetime import timedelta
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from sqlalchemy import func, select

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
        with self.sessions.begin() as db:
            row = db.scalar(select(BrowserSession).where(
                BrowserSession.id == session_id,
                BrowserSession.owner_id == owner,
            ).with_for_update())
            if row is None:
                raise not_found()
            if aware(row.expires_at) <= utcnow() or row.state in TERMINAL_BROWSER_STATES:
                raise CoworkerError("browser_session_closed", "This browser session is no longer active.", 409)
            row.state = "takeover"
            row.takeover_required = True
            row.updated_at = utcnow()
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
                row.updated_at = utcnow()
                db.add(AuditEvent(
                    id=str(uuid4()), owner_id=owner, resource_id=row.id,
                    action="browser_session.cancelled",
                ))
            return self._dto(row)

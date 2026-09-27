from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
from datetime import timedelta
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from sqlalchemy import and_, func, or_, select

from .action_security import TokenVault
from .browser_schemas import BrowserFormPrepareCreate, BrowserNavigateCreate, BrowserSessionCreate, BrowserTakeoverInputCreate, BrowserTakeoverInteractionCreate
from .errors import CoworkerError
from .models import Account, AuditEvent, BrowserCommand, BrowserSession, Workspace, utcnow
from .repository import aware, iso, not_found

TERMINAL_BROWSER_STATES = {"cancelled", "completed", "expired", "failed"}
ACTIVE_BROWSER_STATES = {"prepared", "queued", "running", "takeover"}
TAKEOVER_COMMAND_KINDS = {"takeover_input", "takeover_frame", "takeover_interaction"}
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

MAX_BROWSER_STORAGE_STATE_BYTES = 65536
MAX_BROWSER_STORAGE_COOKIES = 100
MAX_BROWSER_STORAGE_ORIGINS = 10
MAX_BROWSER_LOCAL_STORAGE_ITEMS = 100
MAX_BROWSER_TAKEOVER_FRAME_BYTES = 350000


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
    prepared_fields = value.get("prepared_fields", [])
    submission_performed = value.get("submission_performed", False)
    storage_state = value.get("storage_state")
    takeover_frame_b64 = value.get("takeover_frame_b64")
    takeover_frame_content_type = value.get("takeover_frame_content_type")
    interaction_performed = value.get("interaction_performed", False)
    if not isinstance(final_url, str):
        raise CoworkerError("browser_observation_invalid", "The browser worker returned an invalid final URL.", 409)
    if title is not None and (not isinstance(title, str) or len(title) > 300):
        raise CoworkerError("browser_observation_invalid", "The browser worker returned an invalid page title.", 409)
    if not isinstance(redirects, list) or len(redirects) > 10 or any(not isinstance(item, str) for item in redirects):
        raise CoworkerError("browser_observation_invalid", "The browser worker returned an invalid redirect chain.", 409)
    if not isinstance(resolved, dict) or len(resolved) > 12:
        raise CoworkerError("browser_observation_invalid", "The browser worker returned invalid DNS evidence.", 409)
    if (
        not isinstance(prepared_fields, list)
        or len(prepared_fields) > 10
        or any(not isinstance(item, str) or not item or len(item) > 160 for item in prepared_fields)
    ):
        raise CoworkerError("browser_observation_invalid", "The browser worker returned invalid prepared-field evidence.", 409)
    if not isinstance(submission_performed, bool):
        raise CoworkerError("browser_observation_invalid", "The browser worker returned invalid submission evidence.", 409)
    if not isinstance(interaction_performed, bool):
        raise CoworkerError("browser_observation_invalid", "The browser worker returned invalid interaction evidence.", 409)
    normalized_resolved: dict[str, list[str]] = {}
    for host, addresses in resolved.items():
        if not isinstance(host, str) or not isinstance(addresses, list):
            raise CoworkerError("browser_observation_invalid", "The browser worker returned invalid DNS evidence.", 409)
        normalized_resolved[host.lower().rstrip(".")] = validate_resolved_addresses(host, addresses)

    takeover_frame: bytes | None = None
    if takeover_frame_b64 is not None or takeover_frame_content_type is not None:
        if (
            takeover_frame_content_type != "image/jpeg"
            or not isinstance(takeover_frame_b64, str)
            or not takeover_frame_b64
            or len(takeover_frame_b64) > 500000
        ):
            raise CoworkerError("browser_takeover_frame_invalid", "The browser worker returned an invalid takeover frame.", 409)
        try:
            takeover_frame = base64.b64decode(takeover_frame_b64, validate=True)
        except (ValueError, TypeError):
            raise CoworkerError("browser_takeover_frame_invalid", "The browser worker returned an invalid takeover frame.", 409) from None
        if (
            not takeover_frame
            or len(takeover_frame) > MAX_BROWSER_TAKEOVER_FRAME_BYTES
            or not takeover_frame.startswith(b"\xff\xd8\xff")
        ):
            raise CoworkerError("browser_takeover_frame_invalid", "The browser worker returned an invalid takeover frame.", 409)

    return {
        "final_url": final_url,
        "title": title,
        "redirect_chain": redirects,
        "resolved_ips": normalized_resolved,
        "prepared_fields": prepared_fields,
        "submission_performed": submission_performed,
        "storage_state": storage_state,
        "takeover_frame": takeover_frame,
        "takeover_frame_content_type": takeover_frame_content_type,
        "interaction_performed": interaction_performed,
    }


def _scrub_form_payload(command: BrowserCommand) -> None:
    if command.kind != "prepare_form":
        return
    payload = dict(command.payload or {})
    scrubbed: list[dict[str, str]] = []
    for item in payload.get("fields", []):
        if isinstance(item, dict):
            by = item.get("by")
            field = item.get("field")
            if isinstance(by, str) and isinstance(field, str):
                scrubbed.append({"by": by, "field": field})
    payload["fields"] = scrubbed
    payload["values_scrubbed"] = True
    command.payload = payload


def _bounded_storage_state(value: dict | None, allowed_origins: list[str]) -> dict | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise CoworkerError("browser_storage_state_invalid", "The browser worker returned invalid session state.", 409)
    try:
        encoded = json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError):
        raise CoworkerError("browser_storage_state_invalid", "The browser worker returned invalid session state.", 409) from None
    if len(encoded) > MAX_BROWSER_STORAGE_STATE_BYTES:
        raise CoworkerError("browser_storage_state_too_large", "The browser session state exceeded its bounded size.", 409)

    cookies = value.get("cookies", [])
    origins = value.get("origins", [])
    if not isinstance(cookies, list) or len(cookies) > MAX_BROWSER_STORAGE_COOKIES:
        raise CoworkerError("browser_storage_state_invalid", "The browser worker returned invalid cookies.", 409)
    if not isinstance(origins, list) or len(origins) > MAX_BROWSER_STORAGE_ORIGINS:
        raise CoworkerError("browser_storage_state_invalid", "The browser worker returned invalid origin state.", 409)

    allowed_hosts = {
        (urlsplit(origin).hostname or "").lower().rstrip(".")
        for origin in allowed_origins
    }
    normalized_cookies: list[dict] = []
    for cookie in cookies:
        if not isinstance(cookie, dict):
            raise CoworkerError("browser_storage_state_invalid", "The browser worker returned invalid cookies.", 409)
        domain = cookie.get("domain")
        name = cookie.get("name")
        cookie_value = cookie.get("value")
        path = cookie.get("path")
        domain_host = domain.lower().lstrip(".").rstrip(".") if isinstance(domain, str) else ""
        domain_allowed = any(
            host == domain_host or (domain_host and "." in domain_host and host.endswith("." + domain_host))
            for host in allowed_hosts
        )
        if (
            not domain_allowed
            or not isinstance(name, str)
            or not name
            or len(name) > 256
            or not isinstance(cookie_value, str)
            or len(cookie_value) > 4096
            or not isinstance(path, str)
            or len(path) > 2048
        ):
            raise CoworkerError("browser_storage_state_invalid", "The browser worker returned out-of-scope cookie state.", 409)
        normalized_cookies.append(dict(cookie))

    normalized_origins: list[dict] = []
    allowed = set(allowed_origins)
    for item in origins:
        if not isinstance(item, dict) or item.get("origin") not in allowed:
            raise CoworkerError("browser_storage_state_invalid", "The browser worker returned out-of-scope origin state.", 409)
        local_storage = item.get("localStorage", [])
        if (
            not isinstance(local_storage, list)
            or len(local_storage) > MAX_BROWSER_LOCAL_STORAGE_ITEMS
        ):
            raise CoworkerError("browser_storage_state_invalid", "The browser worker returned invalid local storage state.", 409)
        clean_items: list[dict[str, str]] = []
        for entry in local_storage:
            if (
                not isinstance(entry, dict)
                or not isinstance(entry.get("name"), str)
                or not entry["name"]
                or len(entry["name"]) > 512
                or not isinstance(entry.get("value"), str)
                or len(entry["value"]) > 8192
            ):
                raise CoworkerError("browser_storage_state_invalid", "The browser worker returned invalid local storage state.", 409)
            clean_items.append({"name": entry["name"], "value": entry["value"]})
        normalized_origins.append({"origin": item["origin"], "localStorage": clean_items})

    return {"cookies": normalized_cookies, "origins": normalized_origins}


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
        self._session_vault = TokenVault(settings.connector_encryption_key) if settings.browser_enabled else None

    @staticmethod
    def _storage_binding(row: BrowserSession) -> str:
        return f"browser-session:{row.owner_id}:{row.id}"

    @staticmethod
    def _frame_binding(row: BrowserSession) -> str:
        return f"browser-takeover-frame:{row.owner_id}:{row.id}"

    def _store_takeover_frame(self, row: BrowserSession, value: bytes, content_type: str, now) -> None:
        if self._session_vault is None:
            raise CoworkerError("browser_takeover_frame_unavailable", "The visual takeover frame is unavailable.", 503)
        if content_type != "image/jpeg" or not value or len(value) > MAX_BROWSER_TAKEOVER_FRAME_BYTES:
            raise CoworkerError("browser_takeover_frame_invalid", "The visual takeover frame is invalid.", 409)
        row.takeover_frame_sealed = self._session_vault.seal(
            {"content_type": content_type, "data_b64": base64.b64encode(value).decode("ascii")},
            self._frame_binding(row),
        )
        row.takeover_frame_version = int(row.takeover_frame_version or 0) + 1
        row.takeover_frame_content_type = content_type
        row.takeover_frame_byte_size = len(value)
        row.takeover_frame_sha256 = hashlib.sha256(value).hexdigest()
        row.takeover_frame_updated_at = now

    def _open_takeover_frame(self, row: BrowserSession) -> tuple[bytes, str]:
        if not row.takeover_frame_sealed or self._session_vault is None:
            raise CoworkerError("browser_takeover_frame_missing", "No visual takeover frame is available yet.", 404)
        try:
            value = self._session_vault.open(row.takeover_frame_sealed, self._frame_binding(row))
            content_type = value.get("content_type")
            encoded = value.get("data_b64")
            if content_type != "image/jpeg" or not isinstance(encoded, str):
                raise ValueError()
            data = base64.b64decode(encoded, validate=True)
        except (CoworkerError, ValueError, TypeError):
            raise CoworkerError("browser_takeover_frame_unavailable", "The visual takeover frame could not be opened.", 503) from None
        if not data or len(data) > MAX_BROWSER_TAKEOVER_FRAME_BYTES or not data.startswith(b"\xff\xd8\xff"):
            raise CoworkerError("browser_takeover_frame_unavailable", "The visual takeover frame could not be opened.", 503)
        return data, content_type

    @staticmethod
    def _clear_takeover_frame(row: BrowserSession) -> None:
        row.takeover_frame_sealed = None
        row.takeover_frame_version = 0
        row.takeover_frame_content_type = None
        row.takeover_frame_byte_size = None
        row.takeover_frame_sha256 = None
        row.takeover_frame_updated_at = None

    @staticmethod
    def _secret_binding(command: BrowserCommand) -> str:
        return f"browser-takeover:{command.owner_id}:{command.session_id}:{command.id}"

    def _seal_takeover_secret(self, command: BrowserCommand, value: str) -> None:
        if self._session_vault is None:
            raise CoworkerError("browser_secret_unavailable", "Secure browser takeover input is unavailable.", 503)
        command.secret_sealed = self._session_vault.seal({"value": value}, self._secret_binding(command))

    def _open_takeover_secret(self, command: BrowserCommand) -> str:
        if not command.secret_sealed or self._session_vault is None:
            raise CoworkerError("browser_secret_unavailable", "Secure browser takeover input is unavailable.", 503)
        try:
            value = self._session_vault.open(command.secret_sealed, self._secret_binding(command))
        except CoworkerError:
            raise CoworkerError("browser_secret_unavailable", "Secure browser takeover input could not be opened.", 503) from None
        secret = value.get("value")
        if not isinstance(secret, str) or not secret or len(secret) > 1000:
            raise CoworkerError("browser_secret_unavailable", "Secure browser takeover input is invalid.", 503)
        return secret

    @staticmethod
    def _clear_command_secret(command: BrowserCommand) -> None:
        command.secret_sealed = None

    def _open_storage_state(self, row: BrowserSession) -> dict | None:
        if not row.storage_state_sealed:
            return None
        if self._session_vault is None:
            raise CoworkerError("browser_storage_unavailable", "Encrypted browser session state is unavailable.", 503)
        try:
            value = self._session_vault.open(row.storage_state_sealed, self._storage_binding(row))
        except CoworkerError:
            raise CoworkerError("browser_storage_unavailable", "Encrypted browser session state could not be opened.", 503) from None
        return _bounded_storage_state(value, list(row.allowed_origins or []))

    def _store_storage_state(self, row: BrowserSession, value: dict | None, now) -> None:
        if value is None:
            return
        checked = _bounded_storage_state(value, list(row.allowed_origins or []))
        if self._session_vault is None:
            raise CoworkerError("browser_storage_unavailable", "Encrypted browser session state is unavailable.", 503)
        row.storage_state_sealed = self._session_vault.seal(checked or {}, self._storage_binding(row))
        row.storage_state_version = int(row.storage_state_version or 0) + 1
        row.storage_state_updated_at = now

    @staticmethod
    def _clear_storage_state(row: BrowserSession) -> None:
        row.storage_state_sealed = None
        row.storage_state_version = 0
        row.storage_state_updated_at = None

    def _expire_stale_sessions(self, db, owner: str | None = None) -> None:
        now = utcnow()
        query = select(BrowserSession).where(
            BrowserSession.state.not_in(tuple(TERMINAL_BROWSER_STATES)),
            BrowserSession.expires_at <= now,
        )
        if owner is not None:
            query = query.where(BrowserSession.owner_id == owner)
        rows = db.scalars(query.with_for_update()).all()
        for row in rows:
            row.state = "expired"
            row.takeover_required = False
            row.takeover_reason = None
            row.cancel_requested = True
            row.worker_session_ref = None
            row.updated_at = now
            self._clear_storage_state(row)
            self._clear_takeover_frame(row)
            for command in db.scalars(select(BrowserCommand).where(
                BrowserCommand.session_id == row.id,
                BrowserCommand.state.in_(("prepared", "running")),
            ).with_for_update()).all():
                command.state = "failed"
                command.error_code = "session_expired"
                command.finished_at = now
                command.lease_until = None
                command.claimed_by = None
                _scrub_form_payload(command)
                self._clear_command_secret(command)
            db.add(AuditEvent(
                id=str(uuid4()),
                owner_id=row.owner_id,
                resource_id=row.id,
                action="browser_session.expired",
            ))

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
            "takeover_reason": row.takeover_reason,
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
                "authenticated_state_available": bool(row.storage_state_sealed),
                "storage_state_version": int(row.storage_state_version or 0),
                "takeover_frame_available": bool(row.takeover_frame_sealed),
                "takeover_frame_version": int(row.takeover_frame_version or 0),
                "takeover_frame_updated_at": iso(row.takeover_frame_updated_at) if row.takeover_frame_updated_at else None,
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
                or (session.takeover_required and command.kind not in TAKEOVER_COMMAND_KINDS)
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
            self._expire_stale_sessions(db, owner)
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
        with self.sessions.begin() as db:
            self._expire_stale_sessions(db, owner)
            rows = db.scalars(select(BrowserSession).where(
                BrowserSession.owner_id == owner,
            ).order_by(BrowserSession.created_at.desc()).limit(50)).all()
            return [self._dto(row) for row in rows]

    def get(self, owner: str, session_id: str) -> dict:
        self._require_enabled()
        with self.sessions.begin() as db:
            self._expire_stale_sessions(db, owner)
            row = db.scalar(select(BrowserSession).where(
                BrowserSession.id == session_id,
                BrowserSession.owner_id == owner,
            ))
            if row is None:
                raise not_found()
            return self._dto(row)

    @staticmethod
    def _command_dto(row: BrowserCommand) -> dict:
        raw_result = dict(row.result or {})
        result = {
            key: raw_result[key]
            for key in ("final_url", "title", "redirect_chain", "prepared_fields", "submission_performed", "takeover_frame_version", "interaction_performed")
            if key in raw_result
        }
        return {
            "id": row.id,
            "sequence": row.sequence,
            "kind": row.kind,
            "target_url": row.target_url,
            "state": row.state,
            "error_code": row.error_code,
            "attempts": row.attempts,
            "result": result,
            "created_at": iso(row.created_at),
            "started_at": iso(row.started_at) if row.started_at else None,
            "finished_at": iso(row.finished_at) if row.finished_at else None,
        }

    def list_commands(self, owner: str, session_id: str) -> list[dict]:
        self._require_enabled()
        with self.sessions.begin() as db:
            self._expire_stale_sessions(db, owner)
            session = db.scalar(select(BrowserSession.id).where(
                BrowserSession.id == session_id,
                BrowserSession.owner_id == owner,
            ))
            if session is None:
                raise not_found()
            rows = db.scalars(select(BrowserCommand).where(
                BrowserCommand.session_id == session_id,
                BrowserCommand.owner_id == owner,
            ).order_by(BrowserCommand.sequence.desc()).limit(50)).all()
            return [self._command_dto(row) for row in rows]

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
                row.takeover_required = False
                row.cancel_requested = True
                self._clear_storage_state(row)
                self._clear_takeover_frame(row)
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

    def prepare_form(self, owner: str, session_id: str, request: BrowserFormPrepareCreate) -> dict:
        self._require_enabled()
        target_url, origin = normalize_browser_target(request.url)
        sensitive_markers = {
            "password", "passcode", "pin", "otp", "one time", "one-time",
            "verification code", "security code", "cvv", "cvc", "card number",
            "credit card", "debit card", "ssn", "social security", "secret",
        }
        fields: list[dict[str, str]] = []
        for item in request.fields:
            marker = item.field.lower()
            if any(value in marker for value in sensitive_markers):
                raise CoworkerError(
                    "sensitive_field_requires_takeover",
                    "Sensitive credentials or authentication fields require supervised user takeover.",
                    409,
                )
            fields.append({"by": item.by, "field": item.field, "value": item.value})

        with self.sessions.begin() as db:
            row = db.scalar(select(BrowserSession).where(
                BrowserSession.id == session_id,
                BrowserSession.owner_id == owner,
            ).with_for_update())
            if row is None:
                raise not_found()
            if row.purpose != "form_prepare":
                raise CoworkerError(
                    "browser_form_not_allowed",
                    "This browser session was not created for form preparation.",
                    409,
                )
            if aware(row.expires_at) <= utcnow():
                row.state = "expired"
                row.takeover_required = False
                row.cancel_requested = True
                self._clear_storage_state(row)
                raise CoworkerError("browser_session_expired", "This browser session expired.", 410)
            if row.state in TERMINAL_BROWSER_STATES or row.cancel_requested:
                raise CoworkerError("browser_session_closed", "This browser session is no longer active.", 409)
            if row.state == "takeover":
                raise CoworkerError("browser_takeover_active", "Resume the session after user takeover.", 409)
            if origin not in set(row.allowed_origins or []):
                raise CoworkerError(
                    "browser_origin_not_allowed",
                    "This form target leaves the session's approved origin.",
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
                kind="prepare_form",
                target_url=target_url,
                target_origin=origin,
                payload={
                    "policy_version": "browser-v1",
                    "requires_dns_ip_validation": True,
                    "redirect_validation": True,
                    "allow_downloads": False,
                    "allow_script_injection": False,
                    "allow_form_submission": False,
                    "fields": fields,
                },
                state="prepared",
            )
            db.add(command)
            row.updated_at = utcnow()
            db.add(AuditEvent(
                id=str(uuid4()), owner_id=owner, resource_id=row.id,
                action="browser_form.prepared",
            ))
            return {
                "id": command.id,
                "sequence": sequence,
                "kind": command.kind,
                "target_url": target_url,
                "target_origin": origin,
                "state": command.state,
                "policy": {
                    "allow_form_submission": False,
                    "field_count": len(fields),
                },
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
            if aware(row.expires_at) <= now:
                row.state = "expired"
                row.takeover_required = False
                row.cancel_requested = True
                self._clear_storage_state(row)
                self._clear_takeover_frame(row)
                raise CoworkerError("browser_session_closed", "This browser session is no longer active.", 409)
            if row.state in TERMINAL_BROWSER_STATES:
                raise CoworkerError("browser_session_closed", "This browser session is no longer active.", 409)
            row.state = "takeover"
            row.takeover_required = True
            row.takeover_reason = reason
            row.worker_session_ref = None
            self._clear_takeover_frame(row)
            row.updated_at = now
            for command in db.scalars(select(BrowserCommand).where(
                BrowserCommand.session_id == session_id,
                BrowserCommand.state.in_(("prepared", "running")),
            ).with_for_update()).all():
                command.state = "cancelled"
                command.error_code = "takeover_requested"
                command.finished_at = now
                command.lease_until = None
                command.claimed_by = None
                _scrub_form_payload(command)
                self._clear_command_secret(command)
            db.add(AuditEvent(
                id=str(uuid4()), owner_id=owner, resource_id=row.id,
                action="browser_takeover." + reason,
            ))
            return self._dto(row)

    def prepare_takeover_frame(self, owner: str, session_id: str) -> dict:
        self._require_enabled()
        now = utcnow()
        with self.sessions.begin() as db:
            row = db.scalar(select(BrowserSession).where(
                BrowserSession.id == session_id,
                BrowserSession.owner_id == owner,
            ).with_for_update())
            if row is None:
                raise not_found()
            if row.state != "takeover" or not row.takeover_required:
                raise CoworkerError("browser_takeover_not_active", "This session is not waiting for user takeover.", 409)
            if aware(row.expires_at) <= now:
                row.state = "expired"
                row.takeover_required = False
                row.takeover_reason = None
                row.cancel_requested = True
                row.worker_session_ref = None
                self._clear_storage_state(row)
                self._clear_takeover_frame(row)
                raise CoworkerError("browser_session_expired", "This browser session expired.", 410)
            active = db.scalar(select(func.count()).select_from(BrowserCommand).where(
                BrowserCommand.session_id == session_id,
                BrowserCommand.state.in_(("prepared", "running")),
            )) or 0
            if active:
                raise CoworkerError("browser_takeover_busy", "Wait for the current browser command before refreshing the takeover view.", 409)
            target_url, origin = normalize_browser_target(row.last_url or row.start_url)
            if origin not in set(row.allowed_origins or []):
                raise CoworkerError("browser_origin_not_allowed", "The takeover target is outside the approved origin.", 409)
            self._clear_takeover_frame(row)
            sequence = (db.scalar(select(func.max(BrowserCommand.sequence)).where(
                BrowserCommand.session_id == session_id,
            )) or 0) + 1
            command = BrowserCommand(
                id=str(uuid4()),
                session_id=session_id,
                owner_id=owner,
                sequence=sequence,
                kind="takeover_frame",
                target_url=target_url,
                target_origin=origin,
                payload={
                    "policy_version": "browser-v1",
                    "requires_dns_ip_validation": True,
                    "redirect_validation": True,
                    "allow_downloads": False,
                    "allow_script_injection": False,
                    "allow_mutation": False,
                },
                state="prepared",
            )
            db.add(command)
            row.updated_at = now
            db.add(AuditEvent(
                id=str(uuid4()), owner_id=owner, resource_id=row.id,
                action="browser_takeover.frame_requested",
            ))
            return {
                "id": command.id,
                "sequence": sequence,
                "kind": command.kind,
                "target_url": target_url,
                "target_origin": origin,
                "state": command.state,
                "policy": {"allow_mutation": False},
            }

    def get_takeover_frame(self, owner: str, session_id: str) -> tuple[bytes, str, int]:
        self._require_enabled()
        with self.sessions.begin() as db:
            self._expire_stale_sessions(db, owner)
            row = db.scalar(select(BrowserSession).where(
                BrowserSession.id == session_id,
                BrowserSession.owner_id == owner,
            ))
            if row is None:
                raise not_found()
            if row.state != "takeover" or not row.takeover_required:
                raise CoworkerError("browser_takeover_not_active", "This session is not waiting for user takeover.", 409)
            data, content_type = self._open_takeover_frame(row)
            return data, content_type, int(row.takeover_frame_version or 0)

    def prepare_takeover_interaction(
        self,
        owner: str,
        session_id: str,
        request: BrowserTakeoverInteractionCreate,
    ) -> dict:
        self._require_enabled()
        now = utcnow()
        with self.sessions.begin() as db:
            row = db.scalar(select(BrowserSession).where(
                BrowserSession.id == session_id,
                BrowserSession.owner_id == owner,
            ).with_for_update())
            if row is None:
                raise not_found()
            if row.state != "takeover" or not row.takeover_required:
                raise CoworkerError("browser_takeover_not_active", "This session is not waiting for user takeover.", 409)
            if aware(row.expires_at) <= now:
                row.state = "expired"
                row.takeover_required = False
                row.takeover_reason = None
                row.cancel_requested = True
                row.worker_session_ref = None
                self._clear_storage_state(row)
                self._clear_takeover_frame(row)
                raise CoworkerError("browser_session_expired", "This browser session expired.", 410)
            if (
                not row.takeover_frame_sealed
                or not row.takeover_frame_sha256
                or int(row.takeover_frame_version or 0) != request.frame_version
            ):
                raise CoworkerError(
                    "browser_takeover_frame_stale",
                    "Refresh the visual takeover frame before interacting with the page.",
                    409,
                )
            if request.kind == "click":
                if request.x is None or request.y is None or request.key is not None:
                    raise CoworkerError("browser_takeover_interaction_invalid", "Click takeover requires normalized x/y coordinates only.", 422)
            elif request.kind == "key":
                if request.key is None or request.x is not None or request.y is not None:
                    raise CoworkerError("browser_takeover_interaction_invalid", "Key takeover requires one allowed navigation key only.", 422)
            else:
                raise CoworkerError("browser_takeover_interaction_invalid", "Unsupported takeover interaction.", 422)

            active = db.scalar(select(func.count()).select_from(BrowserCommand).where(
                BrowserCommand.session_id == session_id,
                BrowserCommand.state.in_(("prepared", "running")),
            )) or 0
            if active:
                raise CoworkerError("browser_takeover_busy", "Wait for the current takeover command before interacting again.", 409)
            target_url, origin = normalize_browser_target(row.last_url or row.start_url)
            if origin not in set(row.allowed_origins or []):
                raise CoworkerError("browser_origin_not_allowed", "The takeover target is outside the approved origin.", 409)
            sequence = (db.scalar(select(func.max(BrowserCommand.sequence)).where(
                BrowserCommand.session_id == session_id,
            )) or 0) + 1
            interaction = {
                "kind": request.kind,
                "x": request.x,
                "y": request.y,
                "key": request.key,
            }
            command = BrowserCommand(
                id=str(uuid4()),
                session_id=session_id,
                owner_id=owner,
                sequence=sequence,
                kind="takeover_interaction",
                target_url=target_url,
                target_origin=origin,
                payload={
                    "policy_version": "browser-v1",
                    "requires_dns_ip_validation": True,
                    "redirect_validation": True,
                    "allow_downloads": False,
                    "allow_script_injection": False,
                    "human_only": True,
                    "expected_frame_version": request.frame_version,
                    "expected_frame_sha256": row.takeover_frame_sha256,
                    "interaction": interaction,
                },
                state="prepared",
            )
            db.add(command)
            row.updated_at = now
            db.add(AuditEvent(
                id=str(uuid4()), owner_id=owner, resource_id=row.id,
                action="browser_takeover.interaction_prepared",
            ))
            return {
                "id": command.id,
                "sequence": sequence,
                "kind": command.kind,
                "target_url": target_url,
                "target_origin": origin,
                "state": command.state,
                "policy": {
                    "human_only": True,
                    "frame_version": request.frame_version,
                    "interaction_kind": request.kind,
                },
            }

    def prepare_takeover_input(self, owner: str, session_id: str, request: BrowserTakeoverInputCreate) -> dict:
        self._require_enabled()
        now = utcnow()
        with self.sessions.begin() as db:
            row = db.scalar(select(BrowserSession).where(
                BrowserSession.id == session_id,
                BrowserSession.owner_id == owner,
            ).with_for_update())
            if row is None:
                raise not_found()
            if row.state != "takeover" or not row.takeover_required:
                raise CoworkerError("browser_takeover_not_active", "This session is not waiting for user takeover.", 409)
            if aware(row.expires_at) <= now:
                row.state = "expired"
                row.takeover_required = False
                row.takeover_reason = None
                row.cancel_requested = True
                row.worker_session_ref = None
                self._clear_storage_state(row)
                self._clear_takeover_frame(row)
                raise CoworkerError("browser_session_expired", "This browser session expired.", 410)
            if row.takeover_reason == "captcha":
                raise CoworkerError(
                    "browser_captcha_requires_interactive_takeover",
                    "CAPTCHA requires a supervised interactive browser surface and cannot be injected as a secret field.",
                    409,
                )
            target_url, origin = normalize_browser_target(row.last_url or row.start_url)
            if origin not in set(row.allowed_origins or []):
                raise CoworkerError("browser_origin_not_allowed", "The takeover target is outside the approved origin.", 409)
            active = db.scalar(select(func.count()).select_from(BrowserCommand).where(
                BrowserCommand.session_id == session_id,
                BrowserCommand.state.in_(("prepared", "running")),
            )) or 0
            if active:
                raise CoworkerError("browser_takeover_busy", "Wait for the current browser command to stop before entering sensitive input.", 409)
            sequence = (db.scalar(select(func.max(BrowserCommand.sequence)).where(
                BrowserCommand.session_id == session_id,
            )) or 0) + 1
            command = BrowserCommand(
                id=str(uuid4()),
                session_id=session_id,
                owner_id=owner,
                sequence=sequence,
                kind="takeover_input",
                target_url=target_url,
                target_origin=origin,
                payload={
                    "policy_version": "browser-v1",
                    "requires_dns_ip_validation": True,
                    "redirect_validation": True,
                    "allow_downloads": False,
                    "allow_script_injection": False,
                    "allow_auth_submission": bool(request.submit),
                    "by": request.by,
                    "field": request.field,
                },
                state="prepared",
            )
            self._seal_takeover_secret(command, request.value)
            db.add(command)
            row.updated_at = now
            db.add(AuditEvent(
                id=str(uuid4()), owner_id=owner, resource_id=row.id,
                action="browser_takeover.input_prepared",
            ))
            return {
                "id": command.id,
                "sequence": sequence,
                "kind": command.kind,
                "target_url": target_url,
                "target_origin": origin,
                "state": command.state,
                "policy": {
                    "field": request.field,
                    "submit": bool(request.submit),
                    "secret_concealed": True,
                },
            }

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
                row.takeover_required = False
                row.takeover_reason = None
                row.cancel_requested = True
                row.worker_session_ref = None
                self._clear_storage_state(row)
                self._clear_takeover_frame(row)
                raise CoworkerError("browser_session_expired", "This browser session expired.", 410)
            row.state = "prepared"
            row.takeover_required = False
            row.takeover_reason = None
            self._clear_takeover_frame(row)
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
                row.takeover_reason = None
                row.worker_session_ref = None
                self._clear_storage_state(row)
                self._clear_takeover_frame(row)
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
                    _scrub_form_payload(command)
                    self._clear_command_secret(command)
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
            self._expire_stale_sessions(db)
            stale_interactions = db.scalars(
                select(BrowserCommand)
                .join(BrowserSession, BrowserSession.id == BrowserCommand.session_id)
                .where(
                    BrowserCommand.kind == "takeover_interaction",
                    BrowserCommand.state == "running",
                    BrowserCommand.lease_until.is_not(None),
                    BrowserCommand.lease_until < now,
                    BrowserSession.state == "takeover",
                    BrowserSession.takeover_required.is_(True),
                    BrowserSession.cancel_requested.is_(False),
                    BrowserSession.expires_at > now,
                )
                .with_for_update(skip_locked=True)
            ).all()
            for stale in stale_interactions:
                session = db.get(BrowserSession, stale.session_id)
                stale.state = "failed"
                stale.error_code = "takeover_interaction_uncertain"
                stale.finished_at = now
                stale.lease_until = None
                stale.claimed_by = None
                if session is not None:
                    session.worker_session_ref = None
                    session.state = "takeover"
                    self._clear_takeover_frame(session)
                    session.updated_at = now
                    db.add(AuditEvent(
                        id=str(uuid4()),
                        owner_id=session.owner_id,
                        resource_id=session.id,
                        action="browser_takeover.interaction_uncertain",
                    ))
            rows = db.scalars(
                select(BrowserCommand)
                .join(BrowserSession, BrowserSession.id == BrowserCommand.session_id)
                .where(
                    BrowserSession.cancel_requested.is_(False),
                    BrowserSession.expires_at > now,
                    BrowserCommand.state.in_(("prepared", "running")),
                    or_(
                        and_(
                            BrowserSession.takeover_required.is_(False),
                            BrowserSession.state.in_(("prepared", "running", "queued")),
                            BrowserCommand.kind.not_in(tuple(TAKEOVER_COMMAND_KINDS)),
                        ),
                        and_(
                            BrowserSession.takeover_required.is_(True),
                            BrowserSession.state == "takeover",
                            BrowserCommand.kind.in_(tuple(TAKEOVER_COMMAND_KINDS)),
                        ),
                    ),
                    BrowserCommand.attempts < self.settings.browser_command_max_attempts,
                    or_(
                        BrowserCommand.kind != "takeover_interaction",
                        and_(
                            BrowserCommand.kind == "takeover_interaction",
                            BrowserCommand.state == "prepared",
                            BrowserCommand.attempts == 0,
                        ),
                    ),
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
                if command.kind not in TAKEOVER_COMMAND_KINDS:
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
                    "storage_state": self._open_storage_state(session),
                    "storage_state_version": int(session.storage_state_version or 0),
                    "takeover_input": ({
                        "by": (command.payload or {}).get("by"),
                        "field": (command.payload or {}).get("field"),
                        "value": self._open_takeover_secret(command),
                        "submit": bool((command.payload or {}).get("allow_auth_submission")),
                    } if command.kind == "takeover_input" else None),
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
                    self._clear_command_secret(command)
                session.worker_session_ref = None
                return {"action": "stop", "reason": "session_cancelled"}

            if (session.takeover_required or session.state == "takeover") and command.kind not in TAKEOVER_COMMAND_KINDS:
                if command.state == "running":
                    command.state = "cancelled"
                    command.error_code = "takeover_requested"
                    command.finished_at = now
                    command.lease_until = None
                    command.claimed_by = None
                    self._clear_command_secret(command)
                session.worker_session_ref = None
                return {"action": "pause", "reason": "takeover_requested"}

            if aware(session.expires_at) <= now:
                session.state = "expired"
                session.takeover_required = False
                session.takeover_reason = None
                session.worker_session_ref = None
                self._clear_command_secret(command)
                self._clear_storage_state(session)
                self._clear_takeover_frame(session)
                session.updated_at = now
                if command.state in {"prepared", "running"}:
                    command.state = "failed"
                    command.error_code = "session_expired"
                    command.finished_at = now
                    command.lease_until = None
                    command.claimed_by = None
                return {"action": "stop", "reason": "session_expired"}

            if session.state in TERMINAL_BROWSER_STATES:
                self._clear_command_secret(command)
                self._clear_takeover_frame(session)
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
            checked["storage_state"] = _bounded_storage_state(
                checked.get("storage_state"),
                list(session.allowed_origins or []),
            )
            if (session.takeover_required or session.state == "takeover") and command.kind not in TAKEOVER_COMMAND_KINDS:
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
                self._clear_command_secret(command)
                self._clear_takeover_frame(session)
                session.worker_session_ref = None
                raise CoworkerError("browser_session_closed", "This browser session is no longer active.", 409)
            if command.state != "running" or command.claimed_by != worker_id:
                raise CoworkerError("browser_worker_claim_invalid", "This browser command is not owned by this worker.", 409)
            if aware(session.expires_at) <= now:
                session.state = "expired"
                command.state = "failed"
                self._clear_command_secret(command)
                self._clear_storage_state(session)
                self._clear_takeover_frame(session)
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
                    session.takeover_required = False
                    session.takeover_reason = None
                    session.error_code = "redirect_origin_blocked"
                    session.worker_session_ref = None
                    session.updated_at = now
                    self._clear_command_secret(command)
                    self._clear_storage_state(session)
                    self._clear_takeover_frame(session)
                    raise CoworkerError("browser_origin_not_allowed", "The browser worker observed a redirect outside the approved origin.", 409)
                hostname = (urlsplit(normalized).hostname or "").lower().rstrip(".")
                if hostname not in checked["resolved_ips"]:
                    raise CoworkerError(
                        "browser_dns_evidence_missing",
                        "The browser worker did not provide DNS evidence for every observed host.",
                        409,
                    )
                normalized_chain.append(normalized)

            if checked["submission_performed"] and not (
                command.kind == "takeover_input"
                and bool((command.payload or {}).get("allow_auth_submission"))
            ):
                command.state = "failed"
                command.error_code = "form_submission_blocked"
                command.finished_at = now
                command.lease_until = None
                command.claimed_by = None
                session.state = "failed"
                session.takeover_required = False
                session.takeover_reason = None
                session.error_code = "form_submission_blocked"
                session.worker_session_ref = None
                session.updated_at = now
                self._clear_command_secret(command)
                self._clear_storage_state(session)
                self._clear_takeover_frame(session)
                raise CoworkerError(
                    "browser_form_submission_blocked",
                    "The browser worker reported a form submission, which is not authorized.",
                    409,
                )
            if command.kind == "prepare_form":
                expected = [item.get("field") for item in (command.payload or {}).get("fields", [])]
                if checked["prepared_fields"] != expected:
                    raise CoworkerError(
                        "browser_form_evidence_mismatch",
                        "The browser worker did not prepare exactly the requested fields.",
                        409,
                    )

            if command.kind == "takeover_input":
                expected = [(command.payload or {}).get("field")]
                if checked["prepared_fields"] != expected:
                    raise CoworkerError(
                        "browser_takeover_evidence_mismatch",
                        "The browser worker did not apply exactly the requested sensitive field.",
                        409,
                    )

            if command.kind == "takeover_frame":
                if checked["prepared_fields"] or checked["submission_performed"] or checked["interaction_performed"]:
                    raise CoworkerError(
                        "browser_takeover_frame_invalid",
                        "The visual takeover command reported an unauthorized mutation.",
                        409,
                    )
                if checked["takeover_frame"] is None or checked["takeover_frame_content_type"] != "image/jpeg":
                    raise CoworkerError(
                        "browser_takeover_frame_missing",
                        "The browser worker did not return a visual takeover frame.",
                        409,
                    )
                self._store_takeover_frame(
                    session,
                    checked["takeover_frame"],
                    checked["takeover_frame_content_type"],
                    now,
                )
            elif command.kind == "takeover_interaction":
                if checked["prepared_fields"] or checked["submission_performed"] or not checked["interaction_performed"]:
                    raise CoworkerError(
                        "browser_takeover_interaction_invalid",
                        "The browser worker returned invalid human-interaction evidence.",
                        409,
                    )
                if checked["takeover_frame"] is None or checked["takeover_frame_content_type"] != "image/jpeg":
                    raise CoworkerError(
                        "browser_takeover_frame_missing",
                        "The browser worker did not return a fresh visual frame after the interaction.",
                        409,
                    )
                self._store_takeover_frame(
                    session,
                    checked["takeover_frame"],
                    checked["takeover_frame_content_type"],
                    now,
                )
            elif checked["takeover_frame"] is not None or checked["interaction_performed"]:
                raise CoworkerError(
                    "browser_takeover_frame_invalid",
                    "Takeover interaction evidence was returned for a command that did not request it.",
                    409,
                )

            self._store_storage_state(session, checked.get("storage_state"), now)
            _scrub_form_payload(command)
            self._clear_command_secret(command)
            command.result = {
                "final_url": normalized_chain[-1],
                "title": checked["title"],
                "redirect_chain": normalized_chain[:-1],
                "resolved_ips": checked["resolved_ips"],
                "prepared_fields": checked["prepared_fields"],
                "submission_performed": bool(checked["submission_performed"]) if command.kind == "takeover_input" else False,
                **({"takeover_frame_version": int(session.takeover_frame_version or 0)} if command.kind in {"takeover_frame", "takeover_interaction"} else {}),
                **({"interaction_performed": True} if command.kind == "takeover_interaction" else {}),
            }
            command.state = "succeeded"
            command.error_code = None
            command.finished_at = now
            command.lease_until = None
            command.claimed_by = None
            session.worker_session_ref = None
            if command.kind in {"takeover_frame", "takeover_interaction"}:
                session.state = "takeover"
            else:
                session.state = "prepared"
            if command.kind == "takeover_input":
                session.takeover_required = False
                session.takeover_reason = None
                self._clear_takeover_frame(session)
            session.last_url = normalized_chain[-1]
            session.last_title = checked["title"]
            session.updated_at = now
            db.add(AuditEvent(
                id=str(uuid4()), owner_id=session.owner_id, resource_id=session.id,
                action=(
                    "browser_form.prepared" if command.kind == "prepare_form"
                    else "browser_takeover.input_completed" if command.kind == "takeover_input"
                    else "browser_takeover.frame_captured" if command.kind == "takeover_frame"
                    else "browser_takeover.interaction_completed" if command.kind == "takeover_interaction"
                    else "browser_navigation.succeeded"
                ),
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
            "sensitive_field_requires_takeover",
            "form_field_not_found",
            "form_field_ambiguous",
            "form_field_not_editable",
            "form_mutation_blocked",
            "takeover_frame_too_large",
            "takeover_frame_capture_failed",
            "takeover_frame_stale",
            "takeover_context_missing",
            "takeover_interaction_failed",
            "takeover_interaction_uncertain",
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
            _scrub_form_payload(command)
            self._clear_command_secret(command)
            command.finished_at = now
            command.lease_until = None
            command.claimed_by = None
            if session is not None and session.state not in TERMINAL_BROWSER_STATES:
                session.worker_session_ref = None
                if command.kind in {"takeover_frame", "takeover_interaction"}:
                    session.state = "takeover"
                    if command.kind == "takeover_interaction":
                        self._clear_takeover_frame(session)
                    session.updated_at = now
                else:
                    session.state = "failed"
                    session.takeover_required = False
                    session.takeover_reason = None
                    self._clear_storage_state(session)
                    self._clear_takeover_frame(session)
                    session.error_code = error_code
                    session.updated_at = now
            return {"id": command.id, "state": command.state, "error_code": error_code}

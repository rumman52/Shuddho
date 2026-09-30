from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Callable
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from .errors import CoworkerError
from .models import (
    Account,
    AuditEvent,
    BrowserPushDelivery,
    BrowserPushSubscription,
    Notification,
    NotificationOutbox,
    utcnow,
)
from .notification_digests import GROUPED_KINDS, MAX_INBOX_ITEMS, digest_views
from .notification_schemas import (
    BrowserPushSubscriptionDeactivate,
    BrowserPushSubscriptionUpsert,
    NotificationPreferences,
)
from .repository import aware, iso, not_found
from .web_push import (
    WebPushPreparationError,
    WebPushSender,
    WebPushSubscriptionVault,
    WebPushTransportError,
    endpoint_fingerprint,
    validate_push_endpoint,
    validate_subscription_material,
)


SourceValidator = Callable[[object, Notification, Account], bool]


class NotificationRepository:
    """Durable in-app notification preferences, queueing, delivery and inbox."""

    NOTIFICATION_PREFERENCES_KEY = "notifications"
    DEFAULT_NOTIFICATION_PREFERENCES = {
        "in_app_enabled": True,
        "automation_updates_enabled": True,
        "browser_push_enabled": False,
    }
    BROWSER_PUSH_MAX_ATTEMPTS = 3
    BROWSER_PUSH_RETRY_SECONDS = 30

    def __init__(self, sessions, settings):
        self.sessions = sessions
        self.settings = settings
        self.web_push_sender = WebPushSender(settings)
        self.web_push_vault = WebPushSubscriptionVault(settings)
        self._source_validators: dict[str, SourceValidator] = {}

    def register_source_validator(self, source_kind: str, validator: SourceValidator) -> None:
        if not source_kind:
            raise ValueError("Notification source kind must not be empty.")
        self._source_validators[source_kind] = validator

    @classmethod
    def _normalized_notification_preferences(cls, value: dict | None) -> dict[str, bool]:
        if not isinstance(value, dict):
            return dict(cls.DEFAULT_NOTIFICATION_PREFERENCES)
        raw = value.get(cls.NOTIFICATION_PREFERENCES_KEY)
        if raw is None:
            return dict(cls.DEFAULT_NOTIFICATION_PREFERENCES)
        if not isinstance(raw, dict):
            return {
                "in_app_enabled": False,
                "automation_updates_enabled": False,
                "browser_push_enabled": False,
            }
        return {
            "in_app_enabled": raw.get("in_app_enabled") is True,
            "automation_updates_enabled": raw.get("automation_updates_enabled") is True,
            "browser_push_enabled": raw.get("browser_push_enabled") is True,
        }

    @classmethod
    def in_app_enabled(cls, preferences: dict | None) -> bool:
        return cls._normalized_notification_preferences(preferences)["in_app_enabled"]

    @classmethod
    def _notification_allowed(cls, preferences: dict | None, kind: str) -> bool:
        value = cls._normalized_notification_preferences(preferences)
        if not value["in_app_enabled"]:
            return False
        if kind == "automation_started":
            return value["automation_updates_enabled"]
        if kind == "personal_suggestion":
            raw = preferences.get("personal_suggestions") if isinstance(preferences, dict) else None
            return isinstance(raw, dict) and raw.get("enabled") is True and raw.get("delivery_enabled") is True
        if kind == "personal_suggestion_event":
            raw = preferences.get("personal_suggestions") if isinstance(preferences, dict) else None
            return (
                isinstance(raw, dict)
                and raw.get("enabled") is True
                and raw.get("delivery_enabled") is True
                and raw.get("event_delivery_enabled") is True
            )
        return True

    def _source_allowed(self, db, notification: Notification, account: Account) -> bool:
        if notification.source_kind is None and notification.source_id is None:
            return True
        if not notification.source_kind or not notification.source_id:
            return False
        validator = self._source_validators.get(notification.source_kind)
        return validator is not None and bool(validator(db, notification, account))

    @staticmethod
    def _audit(db, owner: str, resource: str, action: str) -> None:
        db.add(AuditEvent(id=str(uuid4()), owner_id=owner, resource_id=resource, action=action))

    @staticmethod
    def _suppress_pending(db, notification: Notification) -> None:
        if notification.state != "pending":
            return
        notification.state = "suppressed"
        outbox = db.get(NotificationOutbox, notification.id)
        if outbox is not None:
            outbox.delivered = True
            outbox.lease_until = None

    def _require_inbox_enabled(self) -> None:
        if not self.settings.automations_enabled:
            raise CoworkerError("automations_unavailable", "Automations are not enabled in this workspace yet.", 409)

    def notification_preferences(self, owner: str) -> dict[str, bool]:
        with self.sessions() as db:
            account = db.scalar(select(Account).where(Account.id == owner))
            if account is None:
                raise not_found()
            return self._normalized_notification_preferences(account.preferences)

    def save_notification_preferences(self, owner: str, request: NotificationPreferences) -> dict[str, bool]:
        value = request.model_dump()
        if value["browser_push_enabled"] and not value["in_app_enabled"]:
            raise CoworkerError(
                "browser_push_requires_in_app",
                "Browser Push requires in-app notifications to remain enabled.",
                409,
            )
        if value["browser_push_enabled"] and not self.browser_push_available():
            raise CoworkerError(
                "browser_push_unavailable",
                "Browser Push is not enabled in this deployment yet.",
                409,
            )
        with self.sessions.begin() as db:
            account = db.scalar(select(Account).where(Account.id == owner).with_for_update())
            if account is None:
                raise not_found()
            current = dict(account.preferences or {})
            current[self.NOTIFICATION_PREFERENCES_KEY] = dict(value)
            account.preferences = current
            if not value["browser_push_enabled"]:
                rows = db.scalars(select(BrowserPushDelivery).where(
                    BrowserPushDelivery.owner_id == owner,
                    BrowserPushDelivery.state == "pending",
                ).with_for_update()).all()
                for row in rows:
                    row.state = "suppressed"
                    row.lease_until = None
                    row.error_code = "browser_push_opted_out"
            self._audit(db, owner, owner, "notification_preferences_updated")
        return value

    def browser_push_available(self) -> bool:
        return bool(
            self.settings.browser_push_enabled
            and self.web_push_sender.available
            and self.web_push_vault.available
        )

    def browser_push_config(self) -> dict:
        enabled = self.browser_push_available()
        return {
            "enabled": enabled,
            "application_server_key": self.web_push_sender.application_server_key if enabled else "",
        }

    def register_browser_push_subscription(
        self, owner: str, request: BrowserPushSubscriptionUpsert
    ) -> dict:
        if not self.browser_push_available():
            raise CoworkerError(
                "browser_push_unavailable",
                "Browser Push is not enabled in this deployment yet.",
                409,
            )
        try:
            endpoint = validate_push_endpoint(request.endpoint)
            validate_subscription_material(request.p256dh, request.auth)
            expires_at = (
                datetime.fromtimestamp(request.expiration_time / 1000, tz=timezone.utc)
                if request.expiration_time is not None else None
            )
        except (ValueError, OverflowError, OSError) as exc:
            raise CoworkerError(
                "invalid_browser_push_subscription",
                "The browser push subscription is invalid.",
                422,
            ) from exc
        if expires_at is not None and expires_at <= utcnow():
            raise CoworkerError("browser_push_expired", "This browser push subscription has expired.", 409)
        fingerprint = endpoint_fingerprint(endpoint)
        ciphertext = self.web_push_vault.seal(endpoint, request.p256dh, request.auth)
        try:
            with self.sessions.begin() as db:
                account = db.scalar(select(Account).where(Account.id == owner).with_for_update())
                if account is None:
                    raise not_found()
                row = db.scalar(select(BrowserPushSubscription).where(
                    BrowserPushSubscription.owner_id == owner,
                    BrowserPushSubscription.endpoint_hash == fingerprint,
                ).with_for_update())
                needs_activation = row is None or not row.active
                if needs_activation:
                    active_count = len(db.scalars(select(BrowserPushSubscription.id).where(
                        BrowserPushSubscription.owner_id == owner,
                        BrowserPushSubscription.active.is_(True),
                    ).with_for_update()).all())
                    if active_count >= self.settings.max_browser_push_subscriptions:
                        raise CoworkerError(
                            "browser_push_subscription_limit",
                            "This account already has the maximum number of active browser notification devices.",
                            409,
                        )
                other_rows = db.scalars(select(BrowserPushSubscription).where(
                    BrowserPushSubscription.endpoint_hash == fingerprint,
                    BrowserPushSubscription.owner_id != owner,
                    BrowserPushSubscription.active.is_(True),
                ).with_for_update()).all()
                for other in other_rows:
                    other.active = False
                    other.updated_at = utcnow()
                    pending = db.scalars(select(BrowserPushDelivery).where(
                        BrowserPushDelivery.subscription_id == other.id,
                        BrowserPushDelivery.state == "pending",
                    ).with_for_update()).all()
                    for delivery in pending:
                        delivery.state = "suppressed"
                        delivery.lease_until = None
                        delivery.error_code = "browser_push_subscription_rebound"
                if row is None:
                    row = BrowserPushSubscription(
                        id=str(uuid4()),
                        owner_id=owner,
                        endpoint_hash=fingerprint,
                        subscription_ciphertext=ciphertext,
                        expires_at=expires_at,
                        active=True,
                        created_at=utcnow(),
                        updated_at=utcnow(),
                    )
                    db.add(row)
                else:
                    row.subscription_ciphertext = ciphertext
                    row.expires_at = expires_at
                    row.active = True
                    row.updated_at = utcnow()
                self._audit(db, owner, row.id, "browser_push_subscription_saved")
                db.flush()
                result = {
                    "id": row.id,
                    "active": row.active,
                    "expires_at": iso(row.expires_at) if row.expires_at else None,
                }
            return result
        except IntegrityError as exc:
            raise CoworkerError(
                "browser_push_endpoint_conflict",
                "This browser push endpoint changed ownership concurrently. Refresh and try again.",
                409,
            ) from exc

    def browser_push_subscription_status(
        self, owner: str, request: BrowserPushSubscriptionDeactivate
    ) -> dict:
        try:
            endpoint = validate_push_endpoint(request.endpoint)
        except ValueError as exc:
            raise CoworkerError(
                "invalid_browser_push_subscription",
                "The browser push subscription is invalid.",
                422,
            ) from exc
        fingerprint = endpoint_fingerprint(endpoint)
        with self.sessions() as db:
            row = db.scalar(select(BrowserPushSubscription).where(
                BrowserPushSubscription.owner_id == owner,
                BrowserPushSubscription.endpoint_hash == fingerprint,
            ))
            now = utcnow()
            return {
                "active": bool(
                    row is not None
                    and row.active
                    and (row.expires_at is None or aware(row.expires_at) > now)
                )
            }

    def deactivate_browser_push_subscription(
        self, owner: str, request: BrowserPushSubscriptionDeactivate
    ) -> dict:
        try:
            endpoint = validate_push_endpoint(request.endpoint)
        except ValueError as exc:
            raise CoworkerError(
                "invalid_browser_push_subscription",
                "The browser push subscription is invalid.",
                422,
            ) from exc
        fingerprint = endpoint_fingerprint(endpoint)
        with self.sessions.begin() as db:
            row = db.scalar(select(BrowserPushSubscription).where(
                BrowserPushSubscription.owner_id == owner,
                BrowserPushSubscription.endpoint_hash == fingerprint,
            ).with_for_update())
            if row is None:
                raise not_found()
            row.active = False
            row.updated_at = utcnow()
            deliveries = db.scalars(select(BrowserPushDelivery).where(
                BrowserPushDelivery.subscription_id == row.id,
                BrowserPushDelivery.state == "pending",
            ).with_for_update()).all()
            for delivery in deliveries:
                delivery.state = "suppressed"
                delivery.lease_until = None
                delivery.error_code = "browser_push_subscription_inactive"
            self._audit(db, owner, row.id, "browser_push_subscription_deactivated")
            return {"id": row.id, "active": False}

    def _browser_push_allowed(self, preferences: dict | None) -> bool:
        value = self._normalized_notification_preferences(preferences)
        return bool(
            self.browser_push_available()
            and value["in_app_enabled"]
            and value["browser_push_enabled"]
        )

    def _enqueue_browser_push_deliveries(
        self, db, notification: Notification, account: Account
    ) -> None:
        if notification.state not in {"delivered", "read"} or not self._browser_push_allowed(account.preferences):
            return
        now = utcnow()
        subscriptions = db.scalars(select(BrowserPushSubscription).where(
            BrowserPushSubscription.owner_id == notification.owner_id,
            BrowserPushSubscription.active.is_(True),
            or_(
                BrowserPushSubscription.expires_at.is_(None),
                BrowserPushSubscription.expires_at > now,
            ),
        )).all()
        for subscription in subscriptions:
            existing = db.scalar(select(BrowserPushDelivery.id).where(
                BrowserPushDelivery.notification_id == notification.id,
                BrowserPushDelivery.subscription_id == subscription.id,
            ))
            if existing is not None:
                continue
            db.add(BrowserPushDelivery(
                id=str(uuid4()),
                owner_id=notification.owner_id,
                notification_id=notification.id,
                subscription_id=subscription.id,
                state="pending",
                created_at=now,
            ))

    def claim_browser_push_deliveries(self, limit: int = 20) -> list[str]:
        if not self.browser_push_available():
            return []
        with self.sessions.begin() as db:
            now = utcnow()
            rows = db.execute(
                select(BrowserPushDelivery, BrowserPushSubscription, Notification, Account)
                .join(BrowserPushSubscription, BrowserPushSubscription.id == BrowserPushDelivery.subscription_id)
                .join(Notification, Notification.id == BrowserPushDelivery.notification_id)
                .join(Account, Account.id == BrowserPushDelivery.owner_id)
                .where(
                    BrowserPushDelivery.state == "pending",
                    BrowserPushDelivery.attempts < self.BROWSER_PUSH_MAX_ATTEMPTS,
                    or_(
                        BrowserPushDelivery.lease_until.is_(None),
                        BrowserPushDelivery.lease_until < now,
                    ),
                )
                .order_by(BrowserPushDelivery.created_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            ).all()
            claimed: list[str] = []
            for delivery, subscription, notification, account in rows:
                source_ok = self._source_allowed(db, notification, account)
                subscription_ok = (
                    subscription.active
                    and (subscription.expires_at is None or aware(subscription.expires_at) > now)
                )
                if (
                    notification.state not in {"delivered", "read"}
                    or aware(notification.expires_at) <= now
                    or not self._browser_push_allowed(account.preferences)
                    or not source_ok
                    or not subscription_ok
                ):
                    delivery.state = "suppressed"
                    delivery.lease_until = None
                    delivery.error_code = "browser_push_not_authorized"
                    if not subscription_ok:
                        subscription.active = False
                    continue
                delivery.attempts += 1
                delivery.lease_until = now + timedelta(seconds=30)
                claimed.append(delivery.id)
            return claimed

    def deliver_browser_push(self, delivery_id: str) -> None:
        if not self.browser_push_available():
            return
        with self.sessions.begin() as db:
            result = db.execute(
                select(BrowserPushDelivery, BrowserPushSubscription, Notification, Account)
                .join(BrowserPushSubscription, BrowserPushSubscription.id == BrowserPushDelivery.subscription_id)
                .join(Notification, Notification.id == BrowserPushDelivery.notification_id)
                .join(Account, Account.id == BrowserPushDelivery.owner_id)
                .where(BrowserPushDelivery.id == delivery_id)
                .with_for_update()
            ).first()
            if result is None:
                return
            delivery, subscription, notification, account = result
            if delivery.state != "pending":
                return
            now = utcnow()
            if (
                notification.state not in {"delivered", "read"}
                or aware(notification.expires_at) <= now
                or not self._browser_push_allowed(account.preferences)
                or not self._source_allowed(db, notification, account)
                or not subscription.active
                or (subscription.expires_at is not None and aware(subscription.expires_at) <= now)
            ):
                delivery.state = "suppressed"
                delivery.lease_until = None
                delivery.error_code = "browser_push_not_authorized"
                return
            try:
                material = self.web_push_vault.open(subscription.subscription_ciphertext)
            except Exception:
                delivery.state = "failed"
                delivery.lease_until = None
                delivery.error_code = "browser_push_subscription_unreadable"
                subscription.active = False
                subscription.updated_at = utcnow()
                return
            try:
                result = self.web_push_sender.send(
                    material,
                    {
                        "title": "Shuddho",
                        "body": "You have a new Shuddho update.",
                        "url": "/?view=automations",
                        "notification_id": notification.id,
                    },
                    ttl=max(0, int((aware(notification.expires_at) - now).total_seconds())),
                )
            except WebPushPreparationError:
                delivery.state = "failed"
                delivery.lease_until = None
                delivery.error_code = "browser_push_preparation_failed"
                return
            except WebPushTransportError:
                delivery.state = "outcome_unknown"
                delivery.lease_until = None
                delivery.error_code = "browser_push_transport_unknown"
                return
            delivery.provider_status = result.status_code
            delivery.lease_until = None
            if 200 <= result.status_code < 300:
                delivery.state = "provider_accepted"
                delivery.accepted_at = utcnow()
                delivery.error_code = None
                return
            if result.status_code in {404, 410}:
                delivery.state = "failed"
                delivery.error_code = "browser_push_endpoint_gone"
                subscription.active = False
                subscription.updated_at = utcnow()
                return
            if result.status_code in {429, 503} and delivery.attempts < self.BROWSER_PUSH_MAX_ATTEMPTS:
                delivery.lease_until = utcnow() + timedelta(seconds=self.BROWSER_PUSH_RETRY_SECONDS)
                delivery.error_code = "browser_push_retryable"
                return
            delivery.state = "failed"
            delivery.error_code = "browser_push_rejected"

    @staticmethod
    def visible_at_after_quiet_hours(value: datetime, timezone_name: str, quiet: dict | None) -> datetime:
        now = max(aware(value).astimezone(timezone.utc), utcnow())
        if not quiet:
            return now
        zone = ZoneInfo(timezone_name)
        local = now.astimezone(zone)
        start_h, start_m = map(int, quiet["start"].split(":"))
        end_h, end_m = map(int, quiet["end"].split(":"))
        start = time(start_h, start_m); end = time(end_h, end_m)
        current = local.timetz().replace(tzinfo=None)
        in_quiet = start < end and start <= current < end or start > end and (current >= start or current < end)
        if not in_quiet:
            return now
        end_date = local.date()
        if start > end and current >= start:
            end_date += timedelta(days=1)
        return datetime.combine(end_date, end, tzinfo=zone).astimezone(timezone.utc)

    def enqueue_pending(self, db, *, owner: str, workspace_id: str, kind: str, title: str, message: str,
                        visible_at: datetime, expires_at: datetime, notification_id: str | None = None,
                        automation_id: str | None = None, occurrence_id: str | None = None,
                        source_kind: str | None = None, source_id: str | None = None) -> str:
        if (source_kind is None) != (source_id is None):
            raise ValueError("Notification source kind and source ID must be supplied together.")
        if occurrence_id is not None:
            existing = db.scalar(select(Notification).where(Notification.occurrence_id == occurrence_id))
            if existing is not None:
                return existing.id
        if source_kind is not None:
            existing = db.scalar(select(Notification).where(
                Notification.owner_id == owner,
                Notification.source_kind == source_kind,
                Notification.source_id == source_id,
            ))
            if existing is not None:
                return existing.id
        if notification_id is not None:
            existing = db.get(Notification, notification_id)
            if existing is not None:
                if existing.owner_id != owner:
                    raise CoworkerError("notification_id_conflict", "Notification identity is already in use.", 409)
                return existing.id
        row = Notification(id=notification_id or str(uuid4()), owner_id=owner, workspace_id=workspace_id,
                           automation_id=automation_id, occurrence_id=occurrence_id,
                           source_kind=source_kind, source_id=source_id, kind=kind, title=title,
                           message=message, state="pending", visible_at=visible_at,
                           expires_at=expires_at, created_at=utcnow())
        db.add(row); db.flush(); db.add(NotificationOutbox(notification_id=row.id))
        return row.id

    def reconcile_sources(self, owner: str, source_kind: str, plans: list[dict]) -> None:
        with self.sessions.begin() as db:
            account = db.scalar(select(Account).where(Account.id == owner).with_for_update())
            if account is None:
                raise not_found()
            rows = db.scalars(select(Notification).where(
                Notification.owner_id == owner, Notification.source_kind == source_kind
            )).all()
            by_source = {row.source_id: row for row in rows if row.source_id}
            keep = {plan["source_id"] for plan in plans}
            for row in rows:
                if row.source_id not in keep:
                    self._suppress_pending(db, row)
            now = utcnow()
            for plan in plans:
                if aware(plan["expires_at"]) <= now:
                    continue
                existing = by_source.get(plan["source_id"])
                if existing is None:
                    self.enqueue_pending(db, owner=owner, workspace_id=plan["workspace_id"],
                        source_kind=source_kind, source_id=plan["source_id"], kind=plan["kind"],
                        title=plan["title"], message=plan["message"], visible_at=plan["visible_at"],
                        expires_at=plan["expires_at"])
                    continue
                if existing.state in {"delivered", "read"}:
                    continue
                existing.workspace_id=plan["workspace_id"]; existing.kind=plan["kind"]
                existing.title=plan["title"]; existing.message=plan["message"]
                existing.visible_at=plan["visible_at"]; existing.expires_at=plan["expires_at"]
                existing.state="pending"
                outbox=db.get(NotificationOutbox,existing.id)
                if outbox is None:
                    db.add(NotificationOutbox(notification_id=existing.id))
                else:
                    outbox.delivered=False; outbox.lease_until=None

    def claim_notifications(self, limit: int = 20) -> list[str]:
        with self.sessions.begin() as db:
            now=utcnow()
            rows=db.execute(select(NotificationOutbox,Notification,Account)
                .join(Notification,Notification.id==NotificationOutbox.notification_id)
                .join(Account,Account.id==Notification.owner_id)
                .where(NotificationOutbox.delivered.is_(False),Notification.visible_at<=now,
                       Notification.expires_at>now,
                       or_(NotificationOutbox.lease_until.is_(None),NotificationOutbox.lease_until<now))
                .order_by(Notification.visible_at,Notification.created_at).limit(limit)
                .with_for_update(skip_locked=True)).all()
            claimed=[]
            for outbox,notification,account in rows:
                if not self._notification_allowed(account.preferences,notification.kind) or not self._source_allowed(db,notification,account):
                    notification.state="suppressed"; outbox.delivered=True; outbox.lease_until=None; continue
                outbox.lease_until=now+timedelta(seconds=30); outbox.attempts+=1; claimed.append(outbox.notification_id)
            return claimed

    def deliver_notification(self, notification_id: str) -> None:
        with self.sessions.begin() as db:
            result=db.execute(select(Notification,NotificationOutbox,Account)
                .join(NotificationOutbox,NotificationOutbox.notification_id==Notification.id)
                .join(Account,Account.id==Notification.owner_id)
                .where(Notification.id==notification_id).with_for_update()).first()
            if result is None:
                return
            notification,outbox,account=result
            if outbox.delivered:
                return
            notification.state = "delivered" if self._notification_allowed(account.preferences,notification.kind) and self._source_allowed(db,notification,account) else "suppressed"
            if notification.state == "delivered":
                self._enqueue_browser_push_deliveries(db, notification, account)
            outbox.delivered=True; outbox.lease_until=None

    def notifications(self, owner: str, after: datetime | None = None) -> list[dict]:
        self._require_inbox_enabled()
        with self.sessions() as db:
            query=select(Notification).where(Notification.owner_id==owner,
                Notification.state.in_({"delivered","read"}),Notification.expires_at>utcnow())
            if after is not None:
                query=query.where(Notification.created_at>aware(after))
            rows=db.scalars(query.order_by(Notification.created_at.desc()).limit(100)).all()
            return [{"id":row.id,"automation_id":row.automation_id,"occurrence_id":row.occurrence_id,
                     "kind":row.kind,"title":row.title,"message":row.message,"state":row.state,
                     "visible_at":iso(row.visible_at),"read_at":iso(row.read_at) if row.read_at else None,
                     "created_at":iso(row.created_at)} for row in rows]

    def mark_read(self, owner: str, notification_id: str) -> dict:
        self._require_inbox_enabled()
        with self.sessions.begin() as db:
            row=db.scalar(select(Notification).where(Notification.id==notification_id,
                Notification.owner_id==owner).with_for_update())
            if row is None:
                raise not_found()
            row.state="read"; row.read_at=utcnow()
            return {"id":row.id,"state":row.state,"read_at":iso(row.read_at)}

    @staticmethod
    def _digest_item(row: Notification) -> dict:
        return {"id": row.id, "workspace_id": row.workspace_id,
                "automation_id": row.automation_id, "occurrence_id": row.occurrence_id,
                "kind": row.kind, "title": row.title, "message": row.message,
                "state": row.state, "visible_at": iso(row.visible_at),
                "read_at": iso(row.read_at) if row.read_at else None, "created_at": iso(row.created_at)}

    def _digest_member_allowed(self, db, row: Notification, account: Account, now: datetime) -> bool:
        if row.kind in GROUPED_KINDS and (row.source_kind != row.kind or not row.source_id):
            return False
        return (row.state in {"delivered", "read"} and aware(row.visible_at) <= now
                and aware(row.expires_at) > now
                and self._notification_allowed(account.preferences, row.kind)
                and self._source_allowed(db, row, account))

    def notification_digests(self, owner: str) -> list[dict]:
        self._require_inbox_enabled()
        with self.sessions() as db:
            account = db.get(Account, owner)
            if account is None:
                raise not_found()
            now = utcnow()
            rows = db.scalars(select(Notification).where(
                Notification.owner_id == owner, Notification.state.in_({"delivered", "read"}),
                Notification.visible_at <= now, Notification.expires_at > now,
            ).order_by(Notification.visible_at.desc(), Notification.created_at.desc(),
                       Notification.id.desc()).limit(MAX_INBOX_ITEMS)).all()
            items = [self._digest_item(row) for row in rows
                     if self._digest_member_allowed(db, row, account, now)]
            return digest_views(owner, items)

    def mark_digest_read(self, owner: str, digest_id: str, notification_ids: list[str]) -> dict:
        self._require_inbox_enabled()
        with self.sessions.begin() as db:
            account = db.scalar(select(Account).where(Account.id == owner).with_for_update())
            if account is None:
                raise not_found()
            rows = db.scalars(select(Notification).where(
                Notification.owner_id == owner, Notification.id.in_(notification_ids),
            ).order_by(Notification.id).with_for_update()).all()
            if len(rows) != len(notification_ids):
                raise not_found()
            now = utcnow()
            allowed = all(self._digest_member_allowed(db, row, account, now) for row in rows)
            groups = digest_views(owner, [self._digest_item(row) for row in rows]) if allowed else []
            if len(groups) != 1 or groups[0]["id"] != digest_id:
                raise CoworkerError("notification_digest_changed",
                    "This digest changed or is no longer available. Refresh your inbox.", 409)
            for row in rows:
                if row.state == "delivered":
                    row.state = "read"
                    row.read_at = now
            return {"id": digest_id, "notifications": [
                {"id": row.id, "state": row.state, "read_at": iso(row.read_at) if row.read_at else None}
                for row in rows
            ]}

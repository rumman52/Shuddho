from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select

from .errors import CoworkerError
from .models import Account, AuditEvent, Notification, NotificationOutbox, utcnow
from .notification_schemas import NotificationPreferences
from .repository import aware, iso, not_found


class NotificationRepository:
    """Durable in-app notification preferences, queueing, delivery and inbox."""

    NOTIFICATION_PREFERENCES_KEY = "notifications"
    DEFAULT_NOTIFICATION_PREFERENCES = {
        "in_app_enabled": True,
        "automation_updates_enabled": True,
    }

    def __init__(self, sessions, settings):
        self.sessions = sessions
        self.settings = settings

    @classmethod
    def _normalized_notification_preferences(
        cls,
        value: dict | None,
    ) -> dict[str, bool]:
        if not isinstance(value, dict):
            return dict(cls.DEFAULT_NOTIFICATION_PREFERENCES)
        raw = value.get(cls.NOTIFICATION_PREFERENCES_KEY)
        if raw is None:
            return dict(cls.DEFAULT_NOTIFICATION_PREFERENCES)
        if not isinstance(raw, dict):
            return {
                "in_app_enabled": False,
                "automation_updates_enabled": False,
            }
        return {
            "in_app_enabled": raw.get("in_app_enabled") is True,
            "automation_updates_enabled": raw.get("automation_updates_enabled") is True,
        }

    @classmethod
    def _notification_allowed(cls, preferences: dict | None, kind: str) -> bool:
        value = cls._normalized_notification_preferences(preferences)
        if not value["in_app_enabled"]:
            return False
        if kind == "automation_started":
            return value["automation_updates_enabled"]
        return True

    @staticmethod
    def _audit(db, owner: str, resource: str, action: str) -> None:
        db.add(
            AuditEvent(
                id=str(uuid4()),
                owner_id=owner,
                resource_id=resource,
                action=action,
            )
        )

    def _require_inbox_enabled(self) -> None:
        # Preserve the currently released PA-02 API boundary while extracting
        # notification ownership from AutomationRepository. Future PA-10 slices
        # can broaden the inbox gate without creating another notification store.
        if not self.settings.automations_enabled:
            raise CoworkerError(
                "automations_unavailable",
                "Automations are not enabled in this workspace yet.",
                409,
            )

    def notification_preferences(self, owner: str) -> dict[str, bool]:
        with self.sessions() as db:
            account = db.scalar(select(Account).where(Account.id == owner))
            if account is None:
                raise not_found()
            return self._normalized_notification_preferences(account.preferences)

    def save_notification_preferences(
        self,
        owner: str,
        request: NotificationPreferences,
    ) -> dict[str, bool]:
        value = request.model_dump()
        with self.sessions.begin() as db:
            account = db.scalar(
                select(Account).where(Account.id == owner).with_for_update()
            )
            if account is None:
                raise not_found()
            current = dict(account.preferences or {})
            current[self.NOTIFICATION_PREFERENCES_KEY] = dict(value)
            account.preferences = current
            self._audit(db, owner, owner, "notification_preferences_updated")
        return value

    @staticmethod
    def visible_at_after_quiet_hours(
        value: datetime,
        timezone_name: str,
        quiet: dict | None,
    ) -> datetime:
        now = max(aware(value).astimezone(timezone.utc), utcnow())
        if not quiet:
            return now
        zone = ZoneInfo(timezone_name)
        local = now.astimezone(zone)
        start_h, start_m = map(int, quiet["start"].split(":"))
        end_h, end_m = map(int, quiet["end"].split(":"))
        start = time(start_h, start_m)
        end = time(end_h, end_m)
        current = local.timetz().replace(tzinfo=None)
        in_quiet = (
            start < end and start <= current < end
            or start > end and (current >= start or current < end)
        )
        if not in_quiet:
            return now
        end_date = local.date()
        if start > end and current >= start:
            end_date += timedelta(days=1)
        quiet_end = datetime.combine(end_date, end, tzinfo=zone)
        return quiet_end.astimezone(timezone.utc)

    def enqueue_pending(
        self,
        db,
        *,
        owner: str,
        workspace_id: str,
        kind: str,
        title: str,
        message: str,
        visible_at: datetime,
        expires_at: datetime,
        notification_id: str | None = None,
        automation_id: str | None = None,
        occurrence_id: str | None = None,
    ) -> str:
        if occurrence_id is not None:
            existing = db.scalar(
                select(Notification).where(
                    Notification.occurrence_id == occurrence_id
                )
            )
            if existing is not None:
                return existing.id
        if notification_id is not None:
            existing = db.get(Notification, notification_id)
            if existing is not None:
                if existing.owner_id != owner:
                    raise CoworkerError(
                        "notification_id_conflict",
                        "Notification identity is already in use.",
                        409,
                    )
                return existing.id

        row = Notification(
            id=notification_id or str(uuid4()),
            owner_id=owner,
            workspace_id=workspace_id,
            automation_id=automation_id,
            occurrence_id=occurrence_id,
            kind=kind,
            title=title,
            message=message,
            state="pending",
            visible_at=visible_at,
            expires_at=expires_at,
            created_at=utcnow(),
        )
        db.add(row)
        db.flush()
        db.add(NotificationOutbox(notification_id=row.id))
        return row.id

    def claim_notifications(self, limit: int = 20) -> list[str]:
        with self.sessions.begin() as db:
            now = utcnow()
            rows = db.execute(
                select(NotificationOutbox, Notification, Account)
                .join(
                    Notification,
                    Notification.id == NotificationOutbox.notification_id,
                )
                .join(Account, Account.id == Notification.owner_id)
                .where(
                    NotificationOutbox.delivered.is_(False),
                    Notification.visible_at <= now,
                    Notification.expires_at > now,
                    or_(
                        NotificationOutbox.lease_until.is_(None),
                        NotificationOutbox.lease_until < now,
                    ),
                )
                .order_by(Notification.visible_at, Notification.created_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            ).all()
            claimed: list[str] = []
            for outbox, notification, account in rows:
                if not self._notification_allowed(
                    account.preferences,
                    notification.kind,
                ):
                    notification.state = "suppressed"
                    outbox.delivered = True
                    outbox.lease_until = None
                    continue
                outbox.lease_until = now + timedelta(seconds=30)
                outbox.attempts += 1
                claimed.append(outbox.notification_id)
            return claimed

    def deliver_notification(self, notification_id: str) -> None:
        with self.sessions.begin() as db:
            result = db.execute(
                select(Notification, NotificationOutbox, Account)
                .join(
                    NotificationOutbox,
                    NotificationOutbox.notification_id == Notification.id,
                )
                .join(Account, Account.id == Notification.owner_id)
                .where(Notification.id == notification_id)
                .with_for_update()
            ).first()
            if result is None:
                return
            notification, outbox, account = result
            if outbox.delivered:
                return
            if not self._notification_allowed(
                account.preferences,
                notification.kind,
            ):
                notification.state = "suppressed"
            else:
                notification.state = "delivered"
            outbox.delivered = True
            outbox.lease_until = None

    def notifications(
        self,
        owner: str,
        after: datetime | None = None,
    ) -> list[dict]:
        self._require_inbox_enabled()
        with self.sessions() as db:
            query = select(Notification).where(
                Notification.owner_id == owner,
                Notification.state.in_({"delivered", "read"}),
                Notification.expires_at > utcnow(),
            )
            if after is not None:
                query = query.where(Notification.created_at > aware(after))
            rows = db.scalars(
                query.order_by(Notification.created_at.desc()).limit(100)
            ).all()
            return [
                {
                    "id": row.id,
                    "automation_id": row.automation_id,
                    "occurrence_id": row.occurrence_id,
                    "kind": row.kind,
                    "title": row.title,
                    "message": row.message,
                    "state": row.state,
                    "visible_at": iso(row.visible_at),
                    "read_at": iso(row.read_at) if row.read_at else None,
                    "created_at": iso(row.created_at),
                }
                for row in rows
            ]

    def mark_read(self, owner: str, notification_id: str) -> dict:
        self._require_inbox_enabled()
        with self.sessions.begin() as db:
            row = db.scalar(
                select(Notification).where(
                    Notification.id == notification_id,
                    Notification.owner_id == owner,
                ).with_for_update()
            )
            if row is None:
                raise not_found()
            row.state = "read"
            row.read_at = utcnow()
            return {
                "id": row.id,
                "state": row.state,
                "read_at": iso(row.read_at),
            }

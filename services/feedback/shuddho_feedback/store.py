from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from shared.schemas.python_models import FeedbackAction, FeedbackRecord, FeedbackRequest, Suggestion, SuggestionSource
from shared.utils.suggestions import build_feedback_key


NEGATIVE_FEEDBACK_ACTIONS = frozenset(
    {
        FeedbackAction.DISMISSED.value,
        FeedbackAction.SUPPRESSED.value,
        FeedbackAction.IGNORE_FOREVER.value,
        FeedbackAction.NOT_WRONG.value,
    }
)
SUPPRESSION_ACTIONS = frozenset(
    {
        FeedbackAction.SUPPRESSED.value,
        FeedbackAction.IGNORE_FOREVER.value,
        FeedbackAction.NOT_WRONG.value,
    }
)


@dataclass(frozen=True)
class FeedbackStats:
    accepted: int = 0
    dismissed: int = 0

    @property
    def total(self) -> int:
        return self.accepted + self.dismissed

    @property
    def balance(self) -> float:
        if self.total == 0:
            return 0.0
        return (self.accepted - self.dismissed) / self.total


@dataclass(frozen=True)
class FeedbackSignalIndex:
    by_feedback_key: dict[str, FeedbackStats]
    by_rule_id: dict[str, FeedbackStats]
    by_subtype: dict[str, FeedbackStats]


@dataclass(frozen=True)
class FeedbackPreferenceIndex:
    suppressed_keys: set[str]
    personal_dictionary: set[str]


class FeedbackStore:
    def __init__(self, database_path: Path | None = None) -> None:
        self.database_path = database_path or Path(__file__).resolve().parents[3] / "data" / "shuddho_feedback.db"
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _initialize(self) -> None:
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    suggestion_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    text TEXT NOT NULL,
                    replacement TEXT,
                    feedback_key TEXT,
                    rule_id TEXT,
                    subtype TEXT,
                    source TEXT,
                    original_text TEXT,
                    suppression_key TEXT,
                    user_dictionary_entry TEXT,
                    user_id TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS feedback_preferences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action TEXT NOT NULL,
                    suppression_key TEXT,
                    user_dictionary_entry TEXT,
                    user_id TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            self._ensure_column(connection, "feedback", "feedback_key", "TEXT")
            self._ensure_column(connection, "feedback", "rule_id", "TEXT")
            self._ensure_column(connection, "feedback", "subtype", "TEXT")
            self._ensure_column(connection, "feedback", "source", "TEXT")
            self._ensure_column(connection, "feedback", "original_text", "TEXT")
            self._ensure_column(connection, "feedback", "suppression_key", "TEXT")
            self._ensure_column(connection, "feedback", "user_dictionary_entry", "TEXT")
            self._ensure_column(connection, "feedback", "user_id", "TEXT")
            self._ensure_column(connection, "feedback_preferences", "suppression_key", "TEXT")
            self._ensure_column(connection, "feedback_preferences", "user_dictionary_entry", "TEXT")
            self._ensure_column(connection, "feedback_preferences", "user_id", "TEXT")
            connection.commit()

    def save(self, payload: FeedbackRequest) -> FeedbackRecord:
        created_at = datetime.now(timezone.utc)
        feedback_key = self._resolve_feedback_key(payload)
        suppression_key = self._resolve_suppression_key(payload, feedback_key=feedback_key)
        user_dictionary_entry = self._resolve_user_dictionary_entry(payload)

        with sqlite3.connect(self.database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO feedback (
                    suggestion_id,
                    action,
                    text,
                    replacement,
                    feedback_key,
                    rule_id,
                    subtype,
                    source,
                    original_text,
                    suppression_key,
                    user_dictionary_entry,
                    user_id,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.suggestion_id,
                    payload.action.value,
                    payload.text,
                    payload.replacement,
                    feedback_key,
                    payload.rule_id,
                    payload.subtype,
                    payload.source.value if payload.source else None,
                    payload.original_text,
                    suppression_key,
                    user_dictionary_entry,
                    payload.user_id,
                    created_at.isoformat(),
                ),
            )
            self._persist_preference(
                connection,
                action=payload.action,
                suppression_key=suppression_key,
                user_dictionary_entry=user_dictionary_entry,
                user_id=payload.user_id,
                created_at=created_at,
            )
            connection.commit()
            row_id = int(cursor.lastrowid)
        return FeedbackRecord(
            id=row_id,
            suggestion_id=payload.suggestion_id,
            action=payload.action,
            text=payload.text,
            replacement=payload.replacement,
            feedback_key=feedback_key,
            rule_id=payload.rule_id,
            subtype=payload.subtype,
            source=payload.source,
            original_text=payload.original_text,
            suppression_key=suppression_key,
            user_dictionary_entry=user_dictionary_entry,
            user_id=payload.user_id,
            created_at=created_at,
        )

    def load_signal_index(self, suggestions: list[Suggestion]) -> FeedbackSignalIndex:
        feedback_keys = sorted({suggestion.feedback_key for suggestion in suggestions if suggestion.feedback_key})
        rule_ids = sorted({suggestion.rule_id for suggestion in suggestions if suggestion.rule_id})
        subtypes = sorted({suggestion.subtype for suggestion in suggestions if suggestion.subtype})

        with sqlite3.connect(self.database_path) as connection:
            return FeedbackSignalIndex(
                by_feedback_key=self._load_grouped_stats(connection, "feedback_key", feedback_keys),
                by_rule_id=self._load_grouped_stats(connection, "rule_id", rule_ids),
                by_subtype=self._load_grouped_stats(connection, "subtype", subtypes),
            )

    def load_preference_index(self, user_id: str | None = None) -> FeedbackPreferenceIndex:
        with sqlite3.connect(self.database_path) as connection:
            if user_id:
                rows = connection.execute(
                    """
                    SELECT action, suppression_key, user_dictionary_entry
                    FROM feedback_preferences
                    WHERE user_id IS NULL OR user_id = ?
                    ORDER BY id ASC
                    """,
                    (user_id,),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT action, suppression_key, user_dictionary_entry
                    FROM feedback_preferences
                    WHERE user_id IS NULL
                    ORDER BY id ASC
                    """
                ).fetchall()

        suppressed_keys = {
            str(suppression_key)
            for action, suppression_key, _ in rows
            if suppression_key and str(action) in SUPPRESSION_ACTIONS
        }
        personal_dictionary = {
            str(entry)
            for action, _, entry in rows
            if entry and str(action) == FeedbackAction.ADD_TO_PERSONAL_DICTIONARY.value
        }
        return FeedbackPreferenceIndex(
            suppressed_keys=suppressed_keys,
            personal_dictionary=personal_dictionary,
        )

    def load_suppressed_keys(self, user_id: str | None = None) -> set[str]:
        return self.load_preference_index(user_id=user_id).suppressed_keys

    def load_personal_dictionary(self, user_id: str | None = None) -> list[str]:
        return sorted(self.load_preference_index(user_id=user_id).personal_dictionary)

    def _load_grouped_stats(
        self,
        connection: sqlite3.Connection,
        column: str,
        values: list[str],
    ) -> dict[str, FeedbackStats]:
        if not values:
            return {}

        placeholders = ", ".join("?" for _ in values)
        rows = connection.execute(
            f"""
            SELECT {column}, action, COUNT(*)
            FROM feedback
            WHERE {column} IN ({placeholders})
            GROUP BY {column}, action
            """,
            values,
        ).fetchall()

        grouped: dict[str, dict[str, int]] = {}
        for key, action, count in rows:
            if key is None:
                continue
            grouped.setdefault(str(key), {})[str(action)] = int(count)

        return {
            key: FeedbackStats(
                accepted=actions.get(FeedbackAction.ACCEPTED.value, 0),
                dismissed=sum(
                    count
                    for action, count in actions.items()
                    if action in NEGATIVE_FEEDBACK_ACTIONS
                ),
            )
            for key, actions in grouped.items()
        }

    def _persist_preference(
        self,
        connection: sqlite3.Connection,
        *,
        action: FeedbackAction,
        suppression_key: str | None,
        user_dictionary_entry: str | None,
        user_id: str | None,
        created_at: datetime,
    ) -> None:
        if action not in {
            FeedbackAction.SUPPRESSED,
            FeedbackAction.IGNORE_FOREVER,
            FeedbackAction.ADD_TO_PERSONAL_DICTIONARY,
            FeedbackAction.NOT_WRONG,
        }:
            return

        connection.execute(
            """
            INSERT INTO feedback_preferences (
                action,
                suppression_key,
                user_dictionary_entry,
                user_id,
                created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                action.value,
                suppression_key,
                user_dictionary_entry,
                user_id,
                created_at.isoformat(),
            ),
        )

    def _resolve_feedback_key(self, payload: FeedbackRequest) -> str | None:
        if payload.feedback_key:
            return payload.feedback_key
        if payload.original_text is not None:
            return build_feedback_key(
                category=(payload.source.value if payload.source else "feedback"),
                original_text=payload.original_text,
                replacement_options=[payload.replacement] if payload.replacement else [],
            )
        return None

    def _resolve_suppression_key(self, payload: FeedbackRequest, *, feedback_key: str | None) -> str | None:
        if payload.suppression_key:
            return payload.suppression_key
        if payload.rule_id and payload.subtype and payload.original_text is not None:
            normalized_original = " ".join(payload.original_text.split())
            normalized_replacement = " ".join((payload.replacement or "").split())
            return _stable_digest(
                "sup",
                f"{payload.rule_id}:{payload.subtype}:{normalized_original}:{normalized_replacement}",
            )
        return feedback_key

    def _resolve_user_dictionary_entry(self, payload: FeedbackRequest) -> str | None:
        if payload.user_dictionary_entry:
            return " ".join(payload.user_dictionary_entry.split())
        if payload.action == FeedbackAction.ADD_TO_PERSONAL_DICTIONARY and payload.original_text:
            return " ".join(payload.original_text.split())
        return None

    def _ensure_column(self, connection: sqlite3.Connection, table_name: str, column_name: str, column_type: str) -> None:
        existing_columns = {
            row[1]
            for row in connection.execute(f"PRAGMA table_info({table_name})")
        }
        if column_name in existing_columns:
            return
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")


def _stable_digest(prefix: str, payload: str) -> str:
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from shared.schemas.python_models import FeedbackAction, FeedbackRecord, FeedbackRequest, Suggestion, SuggestionSource
from shared.utils.suggestions import build_feedback_key


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
                    created_at TEXT NOT NULL
                )
                """
            )
            self._ensure_column(connection, "feedback", "feedback_key", "TEXT")
            self._ensure_column(connection, "feedback", "rule_id", "TEXT")
            self._ensure_column(connection, "feedback", "subtype", "TEXT")
            self._ensure_column(connection, "feedback", "source", "TEXT")
            self._ensure_column(connection, "feedback", "original_text", "TEXT")
            connection.commit()

    def save(self, payload: FeedbackRequest) -> FeedbackRecord:
        created_at = datetime.now(timezone.utc)
        feedback_key = self._resolve_feedback_key(payload)
        with sqlite3.connect(self.database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO feedback (
                    suggestion_id, action, text, replacement, feedback_key, rule_id, subtype, source, original_text, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    created_at.isoformat()
                )
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
            created_at=created_at
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
                dismissed=actions.get(FeedbackAction.DISMISSED.value, 0),
            )
            for key, actions in grouped.items()
        }

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

    def _ensure_column(self, connection: sqlite3.Connection, table_name: str, column_name: str, column_type: str) -> None:
        existing_columns = {
            row[1]
            for row in connection.execute(f"PRAGMA table_info({table_name})")
        }
        if column_name in existing_columns:
            return
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")

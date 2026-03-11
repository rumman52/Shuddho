from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from shared.schemas.python_models import FeedbackRecord, FeedbackRequest


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
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.commit()

    def save(self, payload: FeedbackRequest) -> FeedbackRecord:
        created_at = datetime.now(timezone.utc)
        with sqlite3.connect(self.database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO feedback (suggestion_id, action, text, replacement, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    payload.suggestion_id,
                    payload.action.value,
                    payload.text,
                    payload.replacement,
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
            created_at=created_at
        )


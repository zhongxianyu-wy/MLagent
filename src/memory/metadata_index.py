from __future__ import annotations

import sqlite3
from pathlib import Path

from src.models import MemoryEntry


class MetadataIndex:
    def __init__(self, db_path: str = "db/experiments.db") -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_metadata (
                memory_id TEXT PRIMARY KEY,
                chroma_id TEXT NOT NULL,
                source TEXT NOT NULL,
                linked_experiment_id TEXT,
                linked_round_id TEXT,
                linked_skill_id TEXT,
                confidence TEXT NOT NULL,
                needs_review INTEGER NOT NULL,
                created_at INTEGER NOT NULL
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_texts (
                memory_id TEXT PRIMARY KEY,
                text TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def add(self, entry: MemoryEntry, chroma_id: str | None = None) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO memory_metadata (
                memory_id,
                chroma_id,
                source,
                linked_experiment_id,
                linked_round_id,
                linked_skill_id,
                confidence,
                needs_review,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.memory_id,
                chroma_id or entry.memory_id,
                entry.source,
                entry.linked_experiment_id,
                entry.linked_round_id,
                entry.linked_skill_id,
                entry.confidence,
                int(entry.needs_review),
                entry.created_at,
            ),
        )
        self._conn.execute(
            """
            INSERT OR REPLACE INTO memory_texts (
                memory_id,
                text
            ) VALUES (?, ?)
            """,
            (entry.memory_id, entry.text),
        )
        self._conn.commit()

    def get(self, memory_id: str, text: str) -> MemoryEntry:
        row = self._conn.execute(
            """
            SELECT
                memory_id,
                source,
                linked_experiment_id,
                linked_round_id,
                linked_skill_id,
                confidence,
                needs_review,
                created_at
            FROM memory_metadata
            WHERE memory_id = ?
            """,
            (memory_id,),
        ).fetchone()
        if row is None:
            raise KeyError(memory_id)

        return MemoryEntry(
            memory_id=row[0],
            source=row[1],
            text=text,
            linked_experiment_id=row[2],
            linked_round_id=row[3],
            linked_skill_id=row[4],
            confidence=row[5],
            needs_review=bool(row[6]),
            created_at=row[7],
        )

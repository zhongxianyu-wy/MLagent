from __future__ import annotations

import sqlite3
from pathlib import Path

from src.models import MemoryEntry


class SkillLinker:
    def __init__(self, db_path: str = "db/experiments.db") -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_skill_links (
                memory_id TEXT NOT NULL,
                candidate_id TEXT NOT NULL,
                PRIMARY KEY (memory_id, candidate_id)
            )
            """
        )
        self._conn.commit()

    def link_memory_to_skill(self, memory_id: str, candidate_id: str) -> None:
        self._conn.execute(
            """
            INSERT OR IGNORE INTO memory_skill_links (
                memory_id,
                candidate_id
            ) VALUES (?, ?)
            """,
            (memory_id, candidate_id),
        )
        self._conn.commit()

    def list_candidate_evidence(self, candidate_id: str) -> list[MemoryEntry]:
        rows = self._conn.execute(
            """
            SELECT
                m.memory_id,
                m.source,
                m.linked_experiment_id,
                m.linked_round_id,
                m.linked_skill_id,
                m.confidence,
                m.needs_review,
                m.created_at
            FROM memory_skill_links AS l
            JOIN memory_metadata AS m ON m.memory_id = l.memory_id
            WHERE l.candidate_id = ?
            ORDER BY m.created_at ASC
            """,
            (candidate_id,),
        ).fetchall()
        return [
            MemoryEntry(
                memory_id=row[0],
                source=row[1],
                text=self._memory_text(row[0]),
                linked_experiment_id=row[2],
                linked_round_id=row[3],
                linked_skill_id=row[4],
                confidence=row[5],
                needs_review=bool(row[6]),
                created_at=row[7],
            )
            for row in rows
        ]

    def _memory_text(self, memory_id: str) -> str:
        # The metadata index is deterministic but text lives in the vector store.
        # Until a full semantic store is wired here, integration tests use a
        # lightweight mirror table when available and otherwise return empty text.
        row = self._conn.execute(
            """
            SELECT text FROM memory_texts WHERE memory_id = ?
            """,
            (memory_id,),
        ).fetchone()
        return "" if row is None else row[0]


class SkillExecutionWriteback:
    def __init__(self, memory_service, registry) -> None:
        self.memory_service = memory_service
        self.registry = registry

    def record_execution(
        self,
        skill_id: str,
        round_id: str,
        metrics: dict,
        used_at: int,
    ):
        memory = self.memory_service.add_experience(
            round_id=round_id,
            summary=f"Skill {skill_id} reproduced with metrics {metrics}",
            confidence="high",
        )
        self.registry.record_use(skill_id, used_at)
        return memory

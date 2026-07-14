from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path

from src.memory.episodic import EpisodicMemory
from src.models import SkillCandidate


class SkillCandidateStore:
    def __init__(self, db_path: str = "db/experiments.db") -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        EpisodicMemory(db_path)
        self._conn = sqlite3.connect(db_path)

    def save(self, candidate: SkillCandidate) -> SkillCandidate:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO skill_candidates (
                candidate_id,
                source_type,
                source_ref,
                skill_name,
                draft_path,
                validation_status,
                darwin_iteration_status,
                review_status,
                approved_skill_id,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                candidate.candidate_id,
                candidate.source_type,
                candidate.source_ref,
                candidate.skill_name,
                candidate.draft_path,
                candidate.validation_status,
                candidate.darwin_iteration_status,
                candidate.review_status,
                candidate.approved_skill_id,
                candidate.created_at,
                candidate.updated_at,
            ),
        )
        self._conn.commit()
        return candidate

    def get(self, candidate_id: str) -> SkillCandidate:
        row = self._conn.execute(
            """
            SELECT candidate_id, source_type, source_ref, skill_name, draft_path,
                   validation_status, darwin_iteration_status, review_status,
                   approved_skill_id, created_at, updated_at
            FROM skill_candidates
            WHERE candidate_id = ?
            """,
            (candidate_id,),
        ).fetchone()
        if row is None:
            raise KeyError(candidate_id)
        return SkillCandidate(*row)

    def update(self, candidate_id: str, **changes) -> SkillCandidate:
        candidate = replace(self.get(candidate_id), **changes)
        return self.save(candidate)

from __future__ import annotations

from src.skill_bridge.candidate import SkillCandidateStore


class DarwinSkillAdapter:
    def __init__(self, candidate_store: SkillCandidateStore) -> None:
        self.candidate_store = candidate_store

    def iterate(self, candidate_id: str):
        candidate = self.candidate_store.get(candidate_id)
        return self.candidate_store.update(
            candidate_id,
            darwin_iteration_status="improved",
            review_status="pending",
            updated_at=candidate.updated_at,
        )

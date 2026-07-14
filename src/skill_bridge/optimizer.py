from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SkillOptimizationJob:
    skill_id: str
    dataset_id: str | None
    dataset_approval_status: str
    backup_path: str
    candidate_path: str
    repeat_count: int
    max_runtime_minutes: int
    selection_metric: str
    leakage_policy: str
    performance_comparison: dict
    review_status: str


class SkillOptimizer:
    def __init__(self, skill_store, evaluator) -> None:
        self.skill_store = skill_store
        self.evaluator = evaluator

    def optimize_skill(
        self,
        skill_id: str,
        dataset_id: str | None,
        dataset_approved: bool,
        repeat_count: int,
        max_runtime_minutes: int,
        selection_metric: str,
    ) -> SkillOptimizationJob:
        if dataset_id is not None and not dataset_approved:
            raise ValueError("dataset approval is required for skill optimization")

        backup_path = self.skill_store.backup(skill_id)
        candidate_path = f"candidates/{skill_id}-optimized"
        comparison = self.evaluator.compare(
            skill_id=skill_id,
            candidate_path=candidate_path,
            dataset_id=dataset_id,
            repeat_count=repeat_count,
            selection_metric=selection_metric,
        )

        return SkillOptimizationJob(
            skill_id=skill_id,
            dataset_id=dataset_id,
            dataset_approval_status="approved" if dataset_approved else "not_required",
            backup_path=backup_path,
            candidate_path=candidate_path,
            repeat_count=repeat_count,
            max_runtime_minutes=max_runtime_minutes,
            selection_metric=selection_metric,
            leakage_policy="train_cv_only_for_selection",
            performance_comparison=comparison,
            review_status="pending",
        )

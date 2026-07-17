from __future__ import annotations

import importlib.metadata
import platform
from pathlib import Path

from src.domain.models import (
    CapacityStatus,
    DatasetVersionSnapshot,
    ExplorationApprovalSnapshot,
    ExplorationPlanSnapshot,
    RunStatusSnapshot,
    WorkspaceError,
)
from src.domain.run_repository import (
    InstancePreparationSpec,
    RunRepository,
    RunStartSpec,
)
from src.training.executor import SubprocessTrainingExecutor


class TrainingRunCoordinator:
    def __init__(
        self,
        repository: RunRepository,
        executor: SubprocessTrainingExecutor,
        capacity: CapacityStatus,
        actor_id: str,
    ) -> None:
        self.repository = repository
        self.executor = executor
        self.capacity = capacity
        self.actor_id = actor_id

    def execute_new(
        self,
        *,
        run_id: str,
        plan: ExplorationPlanSnapshot,
        approval: ExplorationApprovalSnapshot,
        dataset: DatasetVersionSnapshot,
        code_root: Path,
        entrypoint_path: str,
        human_marked_rounds: tuple[int, ...],
    ) -> RunStatusSnapshot:
        self.repository.start_run(
            RunStartSpec(
                run_id=run_id,
                dataset_id=dataset.dataset_id,
                dataset_version=dataset.version,
                dataset_content_fingerprint=dataset.content_fingerprint,
                dataset_version_fingerprint=dataset.version_fingerprint,
                plan_id=plan.plan_id,
                plan_event_id=plan.asset_id,
                plan_fingerprint=plan.plan_fingerprint,
                approval_id=approval.asset_id,
                approval_fingerprint=approval.approval_fingerprint,
                code_fingerprint=plan.code_fingerprint,
                user_direction=plan.user_direction,
                stop_conditions=plan.stop_conditions,
                primary_metric_name=plan.primary_metric,
                target_metric_value=plan.target_metric,
                expected_round_count=len(plan.rounds),
                human_marked_rounds=human_marked_rounds,
                experience_citations=plan.experience_citations,
            ),
            actor_id=self.actor_id,
            capacity=self.capacity,
        )
        try:
            code_revision = self.repository.freeze_code_revision(
                run_id=run_id,
                code_root=code_root,
                candidate_code_files=plan.candidate_code_files,
                code_fingerprint=plan.code_fingerprint,
                entrypoint_path=entrypoint_path,
                actor_id=self.actor_id,
                capacity=self.capacity,
            )
            with self.repository.active_run(run_id):
                return self._execute_rounds(
                    run_id=run_id,
                    plan=plan,
                    dataset=dataset,
                    code_revision=code_revision,
                    human_marked_rounds=human_marked_rounds,
                )
        except WorkspaceError as error:
            self._finish_after_coordinator_error(run_id, error.code)
            raise
        except Exception as error:
            self._finish_after_coordinator_error(
                run_id,
                "coordinator_failed",
            )
            raise WorkspaceError(
                code="coordinator_failed",
                message=f"Training Run coordinator failed: {type(error).__name__}.",
                next_action="Inspect Run Status and retry from reviewed frozen inputs.",
            ) from error

    def resume_existing(
        self,
        *,
        run_id: str,
        plan: ExplorationPlanSnapshot,
        dataset: DatasetVersionSnapshot,
        code_revision,
        human_marked_rounds: tuple[int, ...],
    ) -> RunStatusSnapshot:
        self.repository.recover_run(
            run_id,
            action="resume",
            actor_id=self.actor_id,
            capacity=self.capacity,
        )
        completed = tuple(
            instance
            for instance in self.repository.list_instances(run_id)
            if instance.state == "completed"
        )
        best_value = max(
            (instance.primary_metric_value for instance in completed),
            default=None,
        )
        if best_value is not None and best_value >= plan.target_metric:
            self.repository.finish_run(
                run_id,
                state="completed",
                reason="target_metric_reached",
                actor_id=self.actor_id,
                capacity=self.capacity,
            )
            return self.repository.status(run_id)
        completed_rounds = {instance.round_number for instance in completed}
        remaining = tuple(
            round_plan
            for round_plan in plan.rounds
            if round_plan.round_number not in completed_rounds
        )
        if not remaining:
            self.repository.finish_run(
                run_id,
                state="completed",
                reason="recovered_completed",
                actor_id=self.actor_id,
                capacity=self.capacity,
            )
            return self.repository.status(run_id)
        next_round = remaining[0].round_number
        parent_candidates = tuple(
            instance
            for instance in completed
            if instance.round_number < next_round
        )
        parent = max(
            parent_candidates,
            key=lambda item: item.round_number,
            default=None,
        )
        try:
            with self.repository.active_run(run_id):
                return self._execute_rounds(
                    run_id=run_id,
                    plan=plan,
                    dataset=dataset,
                    code_revision=code_revision,
                    human_marked_rounds=human_marked_rounds,
                    rounds=remaining,
                    parent_id=None if parent is None else parent.asset_id,
                    parent_fingerprint=(
                        None
                        if parent is None
                        else self.repository.instance_fingerprint(parent)
                    ),
                    best_value=best_value,
                    successful_rounds=len(completed),
                )
        except WorkspaceError as error:
            self._finish_after_coordinator_error(run_id, error.code)
            raise
        except Exception as error:
            self._finish_after_coordinator_error(run_id, "coordinator_failed")
            raise WorkspaceError(
                code="coordinator_failed",
                message=f"Training Run recovery failed: {type(error).__name__}.",
                next_action="Inspect Run Status and close or retry the frozen Run.",
            ) from error

    def _execute_rounds(
        self,
        *,
        run_id: str,
        plan: ExplorationPlanSnapshot,
        dataset: DatasetVersionSnapshot,
        code_revision,
        human_marked_rounds: tuple[int, ...],
        rounds=None,
        parent_id=None,
        parent_fingerprint=None,
        best_value=None,
        successful_rounds: int = 0,
    ) -> RunStatusSnapshot:
        split_path = (
            self.repository.repository_path
            / dataset.asset_path
        ).parent / dataset.files["split"]
        environment = _environment_snapshot()
        timeout_seconds = _timeout_seconds(plan.resource_limits)
        human_marked = set(human_marked_rounds)
        for round_plan in rounds or plan.rounds:
            if self.repository.stop_requested(run_id):
                self.repository.finish_run(
                    run_id,
                    state="stopped",
                    reason="user_stop",
                    actor_id=self.actor_id,
                    capacity=self.capacity,
                )
                return self.repository.status(run_id)
            requested_retention = []
            if round_plan.round_number in human_marked:
                requested_retention.append("human_marked")
            configuration = {
                "worker_contract": 1,
                "task_type": dataset.task_type,
                "class_labels": list(dataset.class_labels),
                "positive_class": dataset.positive_class,
                "primary_metric": dataset.primary_metric,
                "target_metric": dataset.target_metric,
                "evaluation_protocol": dataset.split_strategy,
                "cv_folds": int(plan.resource_limits.get("cv_folds", 5)),
                "timeout_seconds": timeout_seconds,
                "hypothesis": round_plan.hypothesis,
                "optimization_direction": round_plan.optimization_direction,
                "intended_changes": list(round_plan.intended_changes),
                "retention_request": requested_retention,
            }
            prepared = self.repository.prepare_instance(
                InstancePreparationSpec(
                    run_id=run_id,
                    round_number=round_plan.round_number,
                    hypothesis=round_plan.hypothesis,
                    optimization_direction=round_plan.optimization_direction,
                    intended_changes=round_plan.intended_changes,
                    random_seed=dataset.random_seed,
                    parent_instance_id=parent_id,
                    parent_instance_fingerprint=parent_fingerprint,
                    configuration=configuration,
                    environment=environment,
                ),
                code_revision=code_revision,
                split_path=split_path,
                actor_id=self.actor_id,
                capacity=self.capacity,
            )
            result = self.executor.execute(
                prepared,
                stop_requested=lambda: self.repository.stop_requested(run_id),
                timeout_seconds=timeout_seconds,
            )
            retention = []
            if result.state == "completed":
                if successful_rounds == 0:
                    retention.append("baseline")
                elif best_value is None or result.primary_metric_value > best_value:
                    retention.append("stage_best")
                if round_plan.round_number in human_marked:
                    retention.append("human_marked")
            instance = self.repository.seal_instance(
                prepared,
                result,
                retention_reasons=tuple(retention),
                actor_id=self.actor_id,
                capacity=self.capacity,
            )
            if instance.state != "completed":
                self.repository.finish_run(
                    run_id,
                    state=instance.state,
                    reason=instance.error_code or instance.state,
                    actor_id=self.actor_id,
                    capacity=self.capacity,
                )
                return self.repository.status(run_id)
            successful_rounds += 1
            if best_value is None or instance.primary_metric_value > best_value:
                best_value = instance.primary_metric_value
            parent_id = instance.asset_id
            parent_fingerprint = self.repository.instance_fingerprint(instance)
            if instance.primary_metric_value >= plan.target_metric:
                self.repository.finish_run(
                    run_id,
                    state="completed",
                    reason="target_metric_reached",
                    actor_id=self.actor_id,
                    capacity=self.capacity,
                )
                return self.repository.status(run_id)
        self.repository.finish_run(
            run_id,
            state="completed",
            reason="round_budget_exhausted",
            actor_id=self.actor_id,
            capacity=self.capacity,
        )
        return self.repository.status(run_id)

    def _finish_after_coordinator_error(self, run_id: str, reason: str) -> None:
        try:
            status = self.repository.status(run_id)
            if status.state not in {"completed", "failed", "timed_out", "stopped"}:
                self.repository.finish_run(
                    run_id,
                    state="failed",
                    reason=reason,
                    actor_id=self.actor_id,
                    capacity=self.capacity,
                )
        except WorkspaceError:
            pass


def _timeout_seconds(resource_limits: dict[str, str | int | float]) -> float:
    raw = resource_limits.get("max_seconds")
    if raw is None:
        raw = float(resource_limits.get("max_minutes", 30)) * 60
    if isinstance(raw, bool) or not isinstance(raw, (int, float)) or raw <= 0:
        raise WorkspaceError(
            code="invalid_run_timeout",
            message="Approved Run timeout must be a positive number.",
            next_action="Record and approve a positive max_seconds or max_minutes limit.",
        )
    return float(raw)


def _environment_snapshot() -> dict[str, object]:
    packages = {}
    for name in ("joblib", "numpy", "pandas", "scikit-learn"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = "unavailable"
    return {
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "packages": packages,
    }

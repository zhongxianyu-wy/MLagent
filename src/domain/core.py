from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.domain.dataset_intake import DatasetInspector
from src.domain.dataset_repository import DatasetRepository
from src.domain.exploration_repository import ExplorationRepository
from src.domain.local_index import LocalIndex
from src.domain.memory_repository import MemoryRepository, RepositoryStatus
from src.domain.models import (
    ApproveExplorationPlanCommand,
    AuthorizeTrainingCommand,
    BootstrapMemoryCommand,
    ConfirmedDatasetReference,
    ConfirmDatasetCommand,
    DatasetInspection,
    DatasetVersionSnapshot,
    ExecuteExplorationCommand,
    ExplorationApprovalSnapshot,
    ExplorationPlanSnapshot,
    ExplorationReviewSnapshot,
    IndexSummary,
    InspectDatasetCommand,
    RecordExplorationPlanCommand,
    RecoverRunCommand,
    RequestRunStopCommand,
    RunStatusSnapshot,
    TrainingAuthorization,
    WorkspaceConnection,
    WorkspaceError,
    WorkspaceSnapshot,
)
from src.domain.run_execution import TrainingRunCoordinator
from src.domain.run_repository import RunRepository
from src.training.executor import SubprocessTrainingExecutor


class DomainCore:
    def __init__(
        self,
        id_factory: Callable[[], str] | None = None,
        dataset_id_factory: Callable[[], str] | None = None,
        exploration_event_id_factory: Callable[[], str] | None = None,
        exploration_approval_id_factory: Callable[[], str] | None = None,
        training_gate_audit_id_factory: Callable[[], str] | None = None,
        run_id_factory: Callable[[], str] | None = None,
        run_event_id_factory: Callable[[], str] | None = None,
        training_instance_id_factory: Callable[[], str] | None = None,
        training_executor_factory: Callable[[], SubprocessTrainingExecutor]
        | None = None,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self.dataset_id_factory = dataset_id_factory
        self.exploration_event_id_factory = exploration_event_id_factory
        self.exploration_approval_id_factory = exploration_approval_id_factory
        self.training_gate_audit_id_factory = training_gate_audit_id_factory
        self.run_id_factory = run_id_factory or (lambda: f"run-{uuid.uuid4()}")
        self.run_event_id_factory = run_event_id_factory
        self.training_instance_id_factory = training_instance_id_factory
        self.training_executor_factory = training_executor_factory
        self.clock = clock
        self.memory_repository = MemoryRepository(
            id_factory=id_factory,
            clock=clock,
        )
        self.dataset_inspector = DatasetInspector()

    def bootstrap_memory(
        self,
        command: BootstrapMemoryCommand,
    ) -> WorkspaceSnapshot:
        connection_path = (
            command.connection_path or Path.cwd() / ".mlagent-workspace.json"
        )
        self._validate_connection_location(
            command.repository_path,
            connection_path,
        )
        repository = self.memory_repository.bootstrap(
            command.repository_path,
            actor_id=command.actor_id,
            remote_url=command.remote_url,
        )
        self._write_connection(
            connection_path,
            WorkspaceConnection(
                repository_path=repository.repository_path,
                actor_id=command.actor_id,
            ),
        )
        index = LocalIndex(repository.repository_path).rebuild()
        return self._snapshot(repository, index)

    def open_workspace(self, connection_path: Path) -> WorkspaceSnapshot:
        connection = self._load_connection(connection_path)
        repository = self.memory_repository.open(
            connection.repository_path,
            actor_id=connection.actor_id,
        )
        index = LocalIndex(repository.repository_path).rebuild()
        return self._snapshot(repository, index)

    def rebuild_local_index(self, connection_path: Path) -> IndexSummary:
        connection = self._load_connection(connection_path)
        repository = self.memory_repository.open(
            connection.repository_path,
            actor_id=connection.actor_id,
        )
        return LocalIndex(repository.repository_path).rebuild()

    def inspect_dataset(
        self,
        command: InspectDatasetCommand,
    ) -> DatasetInspection:
        return self.dataset_inspector.inspect(command)

    def confirm_dataset(
        self,
        command: ConfirmDatasetCommand,
    ) -> DatasetVersionSnapshot:
        connection = self._load_connection(command.connection_path)
        repository = self.memory_repository.open(
            connection.repository_path,
            actor_id=connection.actor_id,
        )
        normalized = self.dataset_inspector.normalize(command)
        return DatasetRepository(
            repository.repository_path,
            id_factory=self.dataset_id_factory,
            clock=self.clock,
        ).create_version(
            normalized,
            actor_id=connection.actor_id,
            capacity=repository.capacity,
            dataset_id=command.dataset_id,
        )

    def get_dataset_overview(
        self,
        connection_path: Path,
        dataset_id: str | None = None,
        version: int | None = None,
    ) -> DatasetVersionSnapshot | None:
        connection = self._load_connection(connection_path)
        repository = self.memory_repository.open(
            connection.repository_path,
            actor_id=connection.actor_id,
        )
        datasets = DatasetRepository(repository.repository_path)
        if dataset_id is None:
            if version is not None:
                raise WorkspaceError(
                    code="missing_dataset_id",
                    message="A dataset ID is required when selecting a version.",
                    next_action="Choose a Dataset Version from Dataset Overview.",
                )
            return datasets.latest()
        return datasets.load(dataset_id, version)

    def require_confirmed_dataset(
        self,
        connection_path: Path,
        dataset_id: str,
        version: int,
    ) -> DatasetVersionSnapshot:
        connection = self._load_connection(connection_path)
        repository = self.memory_repository.open(
            connection.repository_path,
            actor_id=connection.actor_id,
        )
        return self._require_confirmed_from_repository(
            repository.repository_path,
            dataset_id,
            version,
        )

    def require_confirmed_dataset_reference(
        self,
        connection_path: Path,
        dataset_id: str,
        version: int,
    ) -> ConfirmedDatasetReference:
        connection = self._load_connection(connection_path)
        repository = self.memory_repository.open(
            connection.repository_path,
            actor_id=connection.actor_id,
        )
        repository_root = repository.repository_path
        snapshot = self._require_confirmed_from_repository(
            repository_root,
            dataset_id,
            version,
        )
        manifest_path = (repository_root / snapshot.asset_path).resolve()
        try:
            manifest_path.relative_to(repository_root)
        except ValueError as error:
            raise WorkspaceError(
                code="unsafe_dataset_path",
                message="The confirmed Dataset Version manifest is outside Team Memory.",
                next_action="Restore the Dataset Version under the managed datasets directory.",
            ) from error
        return ConfirmedDatasetReference(
            snapshot=snapshot,
            manifest_path=manifest_path,
        )

    def record_exploration_plan(
        self,
        command: RecordExplorationPlanCommand,
    ) -> ExplorationPlanSnapshot:
        connection = self._load_connection(command.connection_path)
        self._require_managed_code_root(
            command.connection_path,
            command.code_root,
        )
        repository = self.memory_repository.open(
            connection.repository_path,
            actor_id=connection.actor_id,
        )
        dataset = self._require_confirmed_from_repository(
            repository.repository_path,
            command.dataset_id,
            command.dataset_version,
        )
        return self._exploration_repository(
            repository.repository_path
        ).record_plan(
            command,
            dataset,
            actor_id=connection.actor_id,
            capacity=repository.capacity,
        )

    def approve_exploration_plan(
        self,
        command: ApproveExplorationPlanCommand,
    ) -> ExplorationApprovalSnapshot:
        connection = self._load_connection(command.connection_path)
        self._require_managed_code_root(
            command.connection_path,
            command.code_root,
        )
        repository = self.memory_repository.open(
            connection.repository_path,
            actor_id=connection.actor_id,
        )
        return self._exploration_repository(
            repository.repository_path
        ).approve_current(
            command.plan_id,
            command.code_root,
            actor_id=connection.actor_id,
            capacity=repository.capacity,
        )

    def get_exploration_review(
        self,
        connection_path: Path,
        code_root: Path,
        plan_id: str | None = None,
    ) -> ExplorationReviewSnapshot | None:
        connection = self._load_connection(connection_path)
        repository = self.memory_repository.open(
            connection.repository_path,
            actor_id=connection.actor_id,
        )
        exploration = self._exploration_repository(repository.repository_path)
        selected_plan_id = plan_id
        if selected_plan_id is None:
            latest = exploration.latest()
            if latest is None:
                return None
            selected_plan_id = latest.plan_id
        self._require_managed_code_root(connection_path, code_root)
        review = exploration.review(selected_plan_id, code_root)
        if review.approval_state != "approved" or review.approval is None:
            return replace(
                review,
                training_gate_state="blocked",
                training_gate_reason=review.approval_state,
            )
        try:
            dataset = self._require_confirmed_from_repository(
                repository.repository_path,
                review.plan.dataset_id,
                review.plan.dataset_version,
            )
            self._require_approved_dataset_binding(
                dataset,
                review.plan,
                review.approval,
            )
        except WorkspaceError as error:
            return replace(
                review,
                training_gate_state="blocked",
                training_gate_reason=error.code,
            )
        return replace(
            review,
            training_gate_state="authorized",
            training_gate_reason=None,
        )

    def authorize_training(
        self,
        command: AuthorizeTrainingCommand,
    ) -> TrainingAuthorization:
        connection = self._load_connection(command.connection_path)
        repository = self.memory_repository.open(
            connection.repository_path,
            actor_id=connection.actor_id,
        )
        exploration = self._exploration_repository(repository.repository_path)
        try:
            dataset = self._require_confirmed_from_repository(
                repository.repository_path,
                command.dataset_id,
                command.dataset_version,
            )
            if not command.plan_id or not command.approval_id:
                raise WorkspaceError(
                    code="plan_approval_required",
                    message="Formal exploration requires an approved current plan and code.",
                    next_action="Review and approve the current exploration plan before training.",
                )
            self._require_managed_code_root(
                command.connection_path,
                command.code_root,
            )
            plan, approval = exploration.require_current_approval(
                command.plan_id,
                command.approval_id,
                command.code_root,
            )
            self._require_approved_dataset_binding(dataset, plan, approval)
            authorized_at = self.clock() if self.clock is not None else _utc_now()
            return TrainingAuthorization(
                authorized=True,
                entry_point=command.entry_point,
                dataset_id=dataset.dataset_id,
                dataset_version=dataset.version,
                dataset_version_fingerprint=dataset.version_fingerprint,
                plan_id=plan.plan_id,
                plan_event_id=plan.asset_id,
                approval_id=approval.asset_id,
                plan_fingerprint=plan.plan_fingerprint,
                code_fingerprint=plan.code_fingerprint,
                round_count=len(plan.rounds),
                authorized_at=authorized_at,
                authorized_by=connection.actor_id,
            )
        except WorkspaceError as error:
            try:
                exploration.append_training_gate_audit(
                    entry_point=command.entry_point,
                    dataset_id=command.dataset_id,
                    dataset_version=command.dataset_version,
                    plan_id=command.plan_id,
                    approval_id=command.approval_id,
                    reason_code=error.code,
                    next_action=error.next_action,
                    actor_id=connection.actor_id,
                    capacity=repository.capacity,
                )
            except WorkspaceError as audit_error:
                raise WorkspaceError(
                    code="training_gate_audit_failed",
                    message="Formal training was blocked, but its required audit event could not be recorded.",
                    next_action="Repair Team Memory write access before retrying formal training.",
                ) from audit_error
            raise

    def execute_exploration(
        self,
        command: ExecuteExplorationCommand,
    ) -> RunStatusSnapshot:
        authorization = self.authorize_training(
            AuthorizeTrainingCommand(
                connection_path=command.connection_path,
                code_root=command.code_root,
                entry_point="execute_exploration",
                dataset_id=command.dataset_id,
                dataset_version=command.dataset_version,
                plan_id=command.plan_id,
                approval_id=command.approval_id,
            )
        )
        connection = self._load_connection(command.connection_path)
        repository = self.memory_repository.open(
            connection.repository_path,
            actor_id=connection.actor_id,
        )
        dataset = self._require_confirmed_from_repository(
            repository.repository_path,
            command.dataset_id,
            command.dataset_version,
        )
        exploration = self._exploration_repository(repository.repository_path)
        plan, approval = exploration.require_current_approval(
            command.plan_id,
            command.approval_id,
            command.code_root,
        )
        self._require_approved_dataset_binding(dataset, plan, approval)
        if (
            authorization.plan_event_id != plan.asset_id
            or authorization.approval_id != approval.asset_id
            or authorization.plan_fingerprint != plan.plan_fingerprint
            or authorization.code_fingerprint != plan.code_fingerprint
        ):
            raise WorkspaceError(
                code="authorization_changed",
                message="Exploration authorization changed before Run creation.",
                next_action="Review and authorize the current plan again.",
            )
        entrypoint = self._select_training_entrypoint(
            plan,
            command.entrypoint_path,
        )
        approved_rounds = {round_plan.round_number for round_plan in plan.rounds}
        if (
            len(set(command.human_marked_rounds))
            != len(command.human_marked_rounds)
            or any(
                round_number not in approved_rounds
                for round_number in command.human_marked_rounds
            )
        ):
            raise WorkspaceError(
                code="invalid_human_model_mark",
                message="Human model marks must reference approved exploration rounds once.",
                next_action="Choose round numbers from the approved plan.",
            )
        run_repository = self._run_repository(repository.repository_path)
        executor = (
            self.training_executor_factory()
            if self.training_executor_factory is not None
            else SubprocessTrainingExecutor()
        )
        return TrainingRunCoordinator(
            run_repository,
            executor,
            repository.capacity,
            connection.actor_id,
        ).execute_new(
            run_id=self.run_id_factory(),
            plan=plan,
            approval=approval,
            dataset=dataset,
            code_root=command.code_root,
            entrypoint_path=entrypoint,
            human_marked_rounds=command.human_marked_rounds,
        )

    def get_run_status(
        self,
        connection_path: Path,
        run_id: str,
    ) -> RunStatusSnapshot:
        connection = self._load_connection(connection_path)
        repository = self.memory_repository.open(
            connection.repository_path,
            actor_id=connection.actor_id,
        )
        return self._run_repository(repository.repository_path).status(run_id)

    def list_run_statuses(
        self,
        connection_path: Path,
    ) -> tuple[RunStatusSnapshot, ...]:
        connection = self._load_connection(connection_path)
        repository = self.memory_repository.open(
            connection.repository_path,
            actor_id=connection.actor_id,
        )
        return self._run_repository(repository.repository_path).list_statuses()

    def request_run_stop(
        self,
        command: RequestRunStopCommand,
    ) -> RunStatusSnapshot:
        connection = self._load_connection(command.connection_path)
        repository = self.memory_repository.open(
            connection.repository_path,
            actor_id=connection.actor_id,
        )
        runs = self._run_repository(repository.repository_path)
        runs.request_stop(
            command.run_id,
            reason=command.reason,
            actor_id=connection.actor_id,
            capacity=repository.capacity,
        )
        return runs.status(command.run_id)

    def recover_run(
        self,
        command: RecoverRunCommand,
    ) -> RunStatusSnapshot:
        connection = self._load_connection(command.connection_path)
        repository = self.memory_repository.open(
            connection.repository_path,
            actor_id=connection.actor_id,
        )
        runs = self._run_repository(repository.repository_path)
        if command.action == "close":
            runs.recover_run(
                command.run_id,
                action="close",
                actor_id=connection.actor_id,
                capacity=repository.capacity,
            )
            return runs.status(command.run_id)
        binding = runs.load_run_start(command.run_id)
        exploration = self._exploration_repository(repository.repository_path)
        plan = exploration.load_plan_event(
            binding["plan_id"],
            binding["plan_event_id"],
        )
        approval = exploration.load_approval(
            binding["plan_id"],
            binding["approval_id"],
        )
        dataset = self._require_confirmed_from_repository(
            repository.repository_path,
            binding["dataset_id"],
            binding["dataset_version"],
        )
        self._require_approved_dataset_binding(dataset, plan, approval)
        if (
            binding["dataset_content_fingerprint"]
            != dataset.content_fingerprint
            or binding["dataset_version_fingerprint"]
            != dataset.version_fingerprint
            or binding["plan_fingerprint"] != plan.plan_fingerprint
            or binding["approval_fingerprint"]
            != approval.approval_fingerprint
            or binding["code_fingerprint"] != plan.code_fingerprint
        ):
            raise WorkspaceError(
                code="run_recovery_binding_mismatch",
                message="Run recovery binding no longer matches its frozen approved evidence.",
                next_action="Restore the Run evidence from Git or close it as interrupted.",
            )
        code_revision = runs.load_code_revision(
            command.run_id,
            binding["code_fingerprint"],
        )
        executor = (
            self.training_executor_factory()
            if self.training_executor_factory is not None
            else SubprocessTrainingExecutor()
        )
        return TrainingRunCoordinator(
            runs,
            executor,
            repository.capacity,
            connection.actor_id,
        ).resume_existing(
            run_id=command.run_id,
            plan=plan,
            dataset=dataset,
            code_revision=code_revision,
            human_marked_rounds=tuple(binding["human_marked_rounds"]),
        )

    def _exploration_repository(self, repository_path: Path) -> ExplorationRepository:
        return ExplorationRepository(
            repository_path,
            event_id_factory=self.exploration_event_id_factory,
            approval_id_factory=self.exploration_approval_id_factory,
            audit_id_factory=self.training_gate_audit_id_factory,
            clock=self.clock,
        )

    def _run_repository(self, repository_path: Path) -> RunRepository:
        return RunRepository(
            repository_path,
            event_id_factory=self.run_event_id_factory,
            instance_id_factory=self.training_instance_id_factory,
            clock=self.clock,
        )

    @staticmethod
    def _select_training_entrypoint(
        plan: ExplorationPlanSnapshot,
        requested: str | None,
    ) -> str:
        python_files = tuple(
            item.path
            for item in plan.candidate_code_files
            if item.path.endswith(".py")
        )
        selected = requested or (python_files[0] if python_files else None)
        if selected is None or selected not in python_files:
            raise WorkspaceError(
                code="invalid_training_entrypoint",
                message="Training entrypoint is not an approved Python code file.",
                next_action="Choose an approved .py file that defines build_estimator(context).",
            )
        return selected

    @staticmethod
    def _require_managed_code_root(
        connection_path: Path,
        code_root: Path,
    ) -> Path:
        workspace_root = connection_path.expanduser().resolve().parent
        resolved_code_root = code_root.expanduser().resolve()
        try:
            resolved_code_root.relative_to(workspace_root)
        except ValueError as error:
            raise WorkspaceError(
                code="unmanaged_code_root",
                message="Candidate code root is outside the connected local workspace.",
                next_action=(
                    "Place candidate code beside the workspace connection or "
                    "in one of its subdirectories."
                ),
            ) from error
        return resolved_code_root

    @staticmethod
    def _require_approved_dataset_binding(
        dataset: DatasetVersionSnapshot,
        plan: ExplorationPlanSnapshot,
        approval: ExplorationApprovalSnapshot,
    ) -> None:
        if (
            plan.dataset_id != dataset.dataset_id
            or plan.dataset_version != dataset.version
            or plan.dataset_content_fingerprint != dataset.content_fingerprint
            or plan.dataset_version_fingerprint != dataset.version_fingerprint
            or approval.dataset_id != dataset.dataset_id
            or approval.dataset_version != dataset.version
            or approval.dataset_version_fingerprint != dataset.version_fingerprint
        ):
            raise WorkspaceError(
                code="approved_dataset_mismatch",
                message=(
                    "The approved exploration plan does not match the requested "
                    "Dataset Version."
                ),
                next_action=(
                    "Select the approved Dataset Version or record and approve "
                    "a new plan."
                ),
            )

    @staticmethod
    def _require_confirmed_from_repository(
        repository_path: Path,
        dataset_id: str,
        version: int,
    ) -> DatasetVersionSnapshot:
        dataset = DatasetRepository(repository_path).load(dataset_id, version)
        if dataset.state != "confirmed":
            raise WorkspaceError(
                code="dataset_not_confirmed",
                message=f"Dataset {dataset_id} is not a confirmed Dataset Version.",
                next_action="Complete intake-data confirmation before formal training.",
            )
        return dataset

    @staticmethod
    def _snapshot(
        repository: RepositoryStatus,
        index: IndexSummary,
    ) -> WorkspaceSnapshot:
        return WorkspaceSnapshot(
            repository_id=repository.repository_id,
            schema_version=repository.schema_version,
            repository_path=repository.repository_path,
            actor_id=repository.actor_id,
            managed_paths=repository.managed_paths,
            index_path=index.index_path,
            indexed_assets=index.asset_count,
            git_state=repository.git_state,
            remote=repository.remote,
            capacity=repository.capacity,
            ready=repository.ready,
            issues=repository.issues,
        )

    @staticmethod
    def _validate_connection_location(
        repository_path: Path,
        connection_path: Path,
    ) -> None:
        root = repository_path.expanduser().resolve()
        resolved_connection = connection_path.expanduser().resolve()
        try:
            relative = resolved_connection.relative_to(root)
        except ValueError:
            return
        if relative != Path(".mlagent-workspace.json"):
            raise WorkspaceError(
                code="connection_inside_repository",
                message="A local workspace connection cannot be an authoritative repository file.",
                next_action="Store it outside the Team Memory Repository or use the ignored root .mlagent-workspace.json path.",
            )

    @staticmethod
    def _write_connection(
        connection_path: Path,
        connection: WorkspaceConnection,
    ) -> None:
        path = connection_path.expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(connection.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _load_connection(connection_path: Path) -> WorkspaceConnection:
        path = connection_path.expanduser().resolve()
        try:
            payload: Any = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise WorkspaceError(
                code="invalid_connection",
                message=f"Workspace connection cannot be read: {path}",
                next_action="Run bootstrap-memory to create a valid local workspace connection.",
            ) from error
        if (
            not isinstance(payload, dict)
            or not isinstance(payload.get("repository_path"), str)
            or not isinstance(payload.get("actor_id"), str)
            or not payload["actor_id"].strip()
        ):
            raise WorkspaceError(
                code="invalid_connection",
                message=f"Workspace connection has invalid fields: {path}",
                next_action="Run bootstrap-memory to recreate the local workspace connection.",
            )
        return WorkspaceConnection(
            repository_path=Path(payload["repository_path"]),
            actor_id=payload["actor_id"],
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

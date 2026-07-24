from __future__ import annotations

import difflib
import hashlib
import json
import time
import uuid
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.domain.code_revision_repository import (
    CodeRevisionRepository,
    compute_code_fingerprint,
)
from src.domain.dataset_intake import DatasetInspector
from src.domain.dataset_repository import DatasetRepository
from src.domain.exploration_repository import (
    MAX_CODE_FILE_BYTES,
    MAX_CODE_FILES,
    ExplorationRepository,
)
from src.domain.experience_repository import ExperienceRepository
from src.domain.git_sync import GitSyncService
from src.domain.local_index import LocalIndex
from src.domain.memory_repository import (
    MemoryRepository,
    RepositoryStatus,
    load_reviewer_policy_fingerprint,
)
from src.domain.models import (
    ApproveExplorationPlanCommand,
    AuthorizeTrainingCommand,
    BootstrapMemoryCommand,
    CompleteSessionCommand,
    ConfirmedDatasetReference,
    ConfirmDatasetCommand,
    CreateSopCandidateCommand,
    DatasetInspection,
    DatasetVersionSnapshot,
    ExecuteExplorationCommand,
    ExperienceCitation,
    ExperienceSearchResult,
    ExperienceSnapshot,
    ExplorationApprovalSnapshot,
    ExplorationPlanSnapshot,
    ExplorationReviewSnapshot,
    ImportNotebookCommand,
    IndexSummary,
    InspectDatasetCommand,
    NotebookImportSnapshot,
    ReproduceNotebookCommand,
    RetrainFromSopCommand,
    RetrainFromSopResult,
    RecordExplorationPlanCommand,
    RecoverRunCommand,
    ReproduceSopCandidateCommand,
    RequestRunStopCommand,
    ReviewExperienceCommand,
    ReviewSopCandidateCommand,
    RunStatusSnapshot,
    RunReplaySnapshot,
    LineageEdge,
    LineageGraph,
    LineageNode,
    SessionStopSyncCommand,
    SessionExperienceOutcome,
    SopCandidateSnapshot,
    SopCandidateStatus,
    SopReproductionGateSnapshot,
    SopReviewOutcome,
    SopVersionSnapshot,
    FormalModelSnapshot,
    SyncStatusSnapshot,
    TrainingAuthorization,
    WorkspaceConnection,
    WorkspaceError,
    WorkspaceSnapshot,
    CandidateCodeFile,
    CodeFileDelta,
    CodeRevisionDiff,
    CodeRevisionSnapshot,
    CodeReviewSnapshot,
    EditedFile,
    ManagedFileEntry,
    SaveCodeRevisionCommand,
    CaptureClaudeChangesCommand,
    ClaudeSessionHandle,
    StartClaudeSessionCommand,
)
from src.domain.notebook_parser import extract_notebook_code, parse_notebook
from src.domain.notebook_repository import NotebookRepository
from src.domain.run_execution import TrainingRunCoordinator
from src.domain.run_repository import InstancePreparationSpec, RunRepository, RunStartSpec
from src.domain.sop_promotion import SopPromotionCoordinator
from src.domain.sop_repository import (
    SopCandidateSpec,
    SopRepository,
    SopReviewSpec,
)
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
        sop_candidate_id_factory: Callable[[], str] | None = None,
        sop_gate_id_factory: Callable[[], str] | None = None,
        sop_approval_id_factory: Callable[[], str] | None = None,
        sop_reproduction_run_id_factory: Callable[[], str] | None = None,
        sop_reproduction_event_id_factory: Callable[[], str] | None = None,
        sop_reproduction_instance_id_factory: Callable[[], str] | None = None,
        sop_training_executor_factory: Callable[[], Any] | None = None,
        clock: Callable[[], str] | None = None,
        claude_executor_factory: Callable[[], Any] | None = None,
        claude_lease_store_factory: Callable[[Path], Any] | None = None,
        claude_epoch_clock: Callable[[], int] | None = None,
        claude_lease_ttl_seconds: int = 900,
    ) -> None:
        self.dataset_id_factory = dataset_id_factory
        self.exploration_event_id_factory = exploration_event_id_factory
        self.exploration_approval_id_factory = exploration_approval_id_factory
        self.training_gate_audit_id_factory = training_gate_audit_id_factory
        self.run_id_factory = run_id_factory or (lambda: f"run-{uuid.uuid4()}")
        self.run_event_id_factory = run_event_id_factory
        self.training_instance_id_factory = training_instance_id_factory
        self.training_executor_factory = training_executor_factory
        self.sop_candidate_id_factory = sop_candidate_id_factory
        self.sop_gate_id_factory = sop_gate_id_factory
        self.sop_approval_id_factory = sop_approval_id_factory
        self.sop_reproduction_run_id_factory = (
            sop_reproduction_run_id_factory
            or (lambda: f"sop-reproduction-{uuid.uuid4()}")
        )
        self.sop_reproduction_event_id_factory = (
            sop_reproduction_event_id_factory
        )
        self.sop_reproduction_instance_id_factory = (
            sop_reproduction_instance_id_factory
        )
        self.sop_training_executor_factory = sop_training_executor_factory
        self.clock = clock
        self.claude_executor_factory = claude_executor_factory
        self.claude_lease_store_factory = claude_lease_store_factory
        self.claude_epoch_clock = claude_epoch_clock or (lambda: int(time.time()))
        self.claude_lease_ttl_seconds = claude_lease_ttl_seconds
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
        sync = GitSyncService(
            repository.repository_path,
            repository.actor_id,
            clock=self.clock,
        ).status()
        return self._snapshot(repository, index, sync)

    def open_workspace(self, connection_path: Path) -> WorkspaceSnapshot:
        connection, repository = self._open_connected_repository(
            connection_path
        )
        index = LocalIndex(repository.repository_path).rebuild()
        sync = GitSyncService(
            repository.repository_path,
            connection.actor_id,
            clock=self.clock,
        ).status()
        return self._snapshot(repository, index, sync)

    def sync_session_start(
        self,
        connection_path: Path,
    ) -> SyncStatusSnapshot:
        connection, repository = self._open_connected_repository(
            connection_path
        )
        status = GitSyncService(
            repository.repository_path,
            connection.actor_id,
            clock=self.clock,
        ).session_start()
        if status.state == "synced":
            LocalIndex(repository.repository_path).rebuild()
        return status

    def start_session(
        self,
        connection_path: Path,
        session_id: str,
    ) -> SessionExperienceOutcome:
        status = self.sync_session_start(connection_path)
        connection, repository = self._open_connected_repository(
            connection_path
        )
        experiences = self._experience_repository(repository.repository_path)
        marker_exists = experiences.has_session_start(session_id)
        if status.state not in {"synced", "not_configured"} and not (
            status.state == "pending_sync" and marker_exists
        ):
            raise WorkspaceError(
                code="experience_session_sync_required",
                message=(
                    "A new Experience session boundary requires a safe "
                    "startup synchronization."
                ),
                next_action=(
                    "Resolve Team Memory synchronization, then retry "
                    "SessionStart."
                ),
            )
        outcome = experiences.start_session(
            session_id,
            actor_id=connection.actor_id,
            capacity=repository.capacity,
        )
        return replace(outcome, sync=status)

    def sync_session_stop(
        self,
        command: SessionStopSyncCommand,
    ) -> SyncStatusSnapshot:
        connection, repository = self._open_connected_repository(
            command.connection_path
        )
        return GitSyncService(
            repository.repository_path,
            connection.actor_id,
            clock=self.clock,
        ).session_stop(command.session_id)

    def complete_session(
        self,
        command: CompleteSessionCommand,
    ) -> SessionExperienceOutcome:
        connection, repository = self._open_connected_repository(
            command.connection_path
        )
        outcome = self._experience_repository(
            repository.repository_path
        ).complete_session(
            command.session_id,
            actor_id=connection.actor_id,
            capacity=repository.capacity,
        )
        sync = self.sync_session_stop(
            SessionStopSyncCommand(
                connection_path=command.connection_path,
                session_id=command.session_id,
            )
        )
        return replace(outcome, sync=sync)

    def get_sync_status(
        self,
        connection_path: Path,
    ) -> SyncStatusSnapshot:
        connection = self._load_connection(connection_path)
        return GitSyncService(
            connection.repository_path,
            connection.actor_id,
            clock=self.clock,
        ).status()

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
        citations = self._resolve_experience_citations(
            repository.repository_path,
            command,
        )
        return self._exploration_repository(
            repository.repository_path
        ).record_plan(
            replace(command, experience_citations=citations),
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
        exploration = self._exploration_repository(repository.repository_path)
        plan = exploration.current(command.plan_id)
        self._require_current_experience_citations(
            repository.repository_path,
            plan,
        )
        return exploration.approve_current(
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
            self._require_current_experience_citations(
                repository.repository_path,
                plan,
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

    def create_sop_candidate(
        self,
        command: CreateSopCandidateCommand,
    ) -> SopCandidateSnapshot:
        connection, repository = self._open_connected_repository(
            command.connection_path
        )
        candidate = self._sop_repository(
            repository.repository_path
        ).create_candidate(
            SopCandidateSpec(
                sop_id=command.sop_id,
                name=command.name,
                source_run_id=command.source_run_id,
                source_instance_id=command.source_instance_id,
                strategy_summary=command.strategy_summary,
                optimization_background=command.optimization_background,
                steps=command.steps,
                change_summary=command.change_summary,
            ),
            actor_id=connection.actor_id,
            capacity=repository.capacity,
        )
        LocalIndex(repository.repository_path).rebuild()
        return candidate

    def reproduce_sop_candidate(
        self,
        command: ReproduceSopCandidateCommand,
    ) -> SopReproductionGateSnapshot:
        connection, repository = self._open_connected_repository(
            command.connection_path
        )
        sops = self._sop_repository(repository.repository_path)
        candidate = sops.validate_candidate_source(
            command.candidate_id,
            command.expected_candidate_fingerprint,
        )
        executor = (
            self.sop_training_executor_factory()
            if self.sop_training_executor_factory is not None
            else SubprocessTrainingExecutor()
        )
        gate = SopPromotionCoordinator(
            sop_repository=sops,
            run_repository=self._sop_run_repository(
                repository.repository_path
            ),
            executor=executor,
            capacity=repository.capacity,
            actor_id=connection.actor_id,
            reproduction_run_id_factory=(
                self.sop_reproduction_run_id_factory
            ),
            clock=self.clock,
        ).reproduce(candidate)
        LocalIndex(repository.repository_path).rebuild()
        return gate

    def review_sop_candidate(
        self,
        command: ReviewSopCandidateCommand,
    ) -> SopReviewOutcome:
        connection, repository = self._open_connected_repository(
            command.connection_path
        )
        self._verify_candidate_lineage(command.connection_path, command.candidate_id)
        outcome = self._sop_repository(
            repository.repository_path
        ).review_candidate(
            SopReviewSpec(
                candidate_id=command.candidate_id,
                expected_candidate_fingerprint=(
                    command.expected_candidate_fingerprint
                ),
                expected_gate_fingerprint=command.expected_gate_fingerprint,
                expected_reviewer_policy_fingerprint=(
                    command.expected_reviewer_policy_fingerprint
                ),
                decision=command.decision,
            ),
            actor_id=connection.actor_id,
            capacity=repository.capacity,
        )
        LocalIndex(repository.repository_path).rebuild()
        return outcome

    def import_notebook(
        self,
        command: ImportNotebookCommand,
    ) -> NotebookImportSnapshot:
        """Import a .ipynb, preserve it, parse it, and store the import record.

        If parse warnings are blocking (missing deps, interactive steps, unclear
        randomness) the state is ``parse_blocked`` and no execution is attempted.
        Otherwise the state is ``preserved`` — the caller (or a follow-up step)
        can then execute the notebook code in a controlled environment.
        """
        connection, repository = self._open_connected_repository(
            command.connection_path
        )
        notebook_bytes = command.notebook_path.read_bytes()
        fingerprint = hashlib.sha256(notebook_bytes).hexdigest()
        parse_report = parse_notebook(command.notebook_path)
        nb_repo = NotebookRepository(repository.repository_path)
        snapshot = nb_repo.store_import(
            original_bytes=notebook_bytes,
            fingerprint=fingerprint,
            importer=connection.actor_id,
            source_description=command.source_description,
            parse_report=parse_report,
            original_filename=str(command.notebook_path.name),
            actor_id=connection.actor_id,
            capacity=repository.capacity,
        )
        LocalIndex(repository.repository_path).rebuild()
        return snapshot

    def get_notebook_import(
        self,
        connection_path: Path,
        asset_id: str,
    ) -> dict[str, Any]:
        """Read a stored notebook import record."""
        connection, repository = self._open_connected_repository(connection_path)
        return NotebookRepository(repository.repository_path).get_import(asset_id)

    def list_notebook_imports(
        self,
        connection_path: Path,
    ) -> list[dict[str, Any]]:
        """List all notebook import records."""
        connection, repository = self._open_connected_repository(connection_path)
        return NotebookRepository(repository.repository_path).list_imports()

    def check_retrain_compatibility(
        self,
        connection_path: Path,
        sop_id: str,
        sop_version: int,
        dataset_id: str,
        dataset_version: int,
    ):
        """Check whether a dataset is compatible for retraining a SOP."""
        from src.domain.sop_retrain import check_retrain_compatibility
        connection, repository = self._open_connected_repository(connection_path)
        sop_repo = self._sop_repository(repository.repository_path)
        versions = sop_repo.list_sop_versions()
        sop = next(
            (v for v in versions if v.sop_id == sop_id and v.version == sop_version),
            None,
        )
        if sop is None:
            raise WorkspaceError(
                code="sop_version_not_found",
                message=f"Approved SOP version not found: {sop_id} v{sop_version}.",
                next_action="Check available SOP versions with list_sop_versions.",
            )
        dataset = DatasetRepository(repository.repository_path).load(
            dataset_id, dataset_version,
        )
        return check_retrain_compatibility(sop, dataset)

    def retrain_from_sop(
        self,
        command: RetrainFromSopCommand,
    ) -> RetrainFromSopResult:
        """Retrain an approved SOP on new data. Never mutates SOP or Formal Model."""
        from src.domain.sop_retrain import check_retrain_compatibility as _check

        connection, repository = self._open_connected_repository(
            command.connection_path
        )
        sop_repo = self._sop_repository(repository.repository_path)
        versions = sop_repo.list_sop_versions()
        sop = next(
            (v for v in versions
             if v.sop_id == command.sop_id and v.version == command.sop_version),
            None,
        )
        if sop is None:
            raise WorkspaceError(
                code="sop_version_not_found",
                message=f"Approved SOP version not found: "
                f"{command.sop_id} v{command.sop_version}.",
                next_action="Check available SOP versions.",
            )

        dataset = DatasetRepository(repository.repository_path).load(
            command.dataset_id, command.dataset_version,
        )

        compat = _check(sop, dataset)
        if not compat.compatible:
            failed = [c[0] for c in compat.checks if not c[2]]
            raise WorkspaceError(
                code="sop_retrain_incompatible",
                message=f"Dataset incompatible with SOP {command.sop_id} "
                f"v{command.sop_version}. Failed checks: {failed}.",
                next_action="Fix dataset or use a different SOP.",
            )

        # Load the SOP's source run/instance to get the code + config
        run_repo = self._sop_run_repository(repository.repository_path)
        source_instance = run_repo.load_instance(
            sop.source_run_id, sop.source_instance_id,
        )
        source_code = run_repo.load_code_revision_for_instance(
            sop.source_run_id, sop.source_instance_id,
        )
        source_start = run_repo.load_run_start(sop.source_run_id)

        # Create a new retrain run
        retrain_run_id = self.run_id_factory()
        run_repo.start_run(
            RunStartSpec(
                run_id=retrain_run_id,
                dataset_id=dataset.dataset_id,
                dataset_version=dataset.version,
                dataset_content_fingerprint=dataset.content_fingerprint,
                dataset_version_fingerprint=dataset.version_fingerprint,
                plan_id=source_start["plan_id"],
                plan_event_id=source_start["plan_event_id"],
                planning_session_id=source_start["planning_session_id"],
                plan_fingerprint=source_start["plan_fingerprint"],
                approval_id=source_start["approval_id"],
                approval_fingerprint=source_start["approval_fingerprint"],
                code_fingerprint=source_code.code_fingerprint,
                user_direction=f"SOP retrain: {command.sop_id} v{command.sop_version}",
                stop_conditions=tuple(source_start.get("stop_conditions", [])),
                primary_metric_name=sop.primary_metric_name,
                target_metric_value=float(source_start.get(
                    "target_metric_value", sop.primary_metric_value
                )),
                expected_round_count=1,
                human_marked_rounds=(),
            ),
            actor_id=connection.actor_id,
            capacity=repository.capacity,
        )

        # Freeze code — derive code_root from the SOP's frozen source code
        code_root = (
            repository.repository_path
            / Path(source_code.asset_path).parent / "files"
        )
        run_repo.freeze_code_revision(
            run_id=retrain_run_id,
            code_root=code_root,
            candidate_code_files=source_code.files,
            code_fingerprint=source_code.code_fingerprint,
            entrypoint_path=source_code.entrypoint_path,
            actor_id=connection.actor_id,
            capacity=repository.capacity,
        )

        # Execute training — delegate to TrainingRunCoordinator like exploration
        executor = (
            self.training_executor_factory()
            if self.training_executor_factory is not None
            else SubprocessTrainingExecutor()
        )
        import tempfile
        split_path = Path(tempfile.mktemp(suffix=".csv"))
        split_path.write_text("sample_id,split\n", encoding="utf-8")

        prepared = run_repo.prepare_instance(
            spec=InstancePreparationSpec(
                run_id=retrain_run_id,
                round_number=1,
                hypothesis=f"SOP {command.sop_id} v{command.sop_version} on new data",
                optimization_direction="sop_retrain",
                intended_changes=(),
                random_seed=source_instance.random_seed,
                parent_instance_id=None,
                parent_instance_fingerprint=None,
                configuration=dict(source_instance.metrics),
                environment=source_instance.environment_fingerprint
                and {"fingerprint": source_instance.environment_fingerprint}
                or {},
            ),
            code_revision=run_repo.load_code_revision(
                retrain_run_id, source_code.code_fingerprint,
            ),
            split_path=split_path,
            actor_id=connection.actor_id,
            capacity=repository.capacity,
        )

        from src.domain.sop_promotion import _timeout_seconds
        result = executor.execute(
            prepared,
            stop_requested=lambda: False,
            timeout_seconds=_timeout_seconds(prepared),
        )

        instance = run_repo.seal_instance(
            prepared,
            result,
            retention_reasons=("sop_retrain",),
            actor_id=connection.actor_id,
            capacity=repository.capacity,
        )

        # Calculate delta
        new_value = result.primary_metric_value
        delta = (new_value - sop.primary_metric_value) if new_value is not None else None

        run_repo.finish_run(
            run_id=retrain_run_id,
            state=result.state,
            reason=result.error_summary or "SOP retrain completed",
            actor_id=connection.actor_id,
            capacity=repository.capacity,
        )

        LocalIndex(repository.repository_path).rebuild()

        return RetrainFromSopResult(
            run_id=retrain_run_id,
            instance_id=instance.asset_id,
            primary_metric_name=sop.primary_metric_name,
            primary_metric_value=new_value,
            sop_primary_metric_value=sop.primary_metric_value,
            delta=delta,
            candidate_model_id=instance.model_fingerprint,
            sop_version_unchanged=True,
            formal_model_unchanged=True,
        )

    def reproduce_notebook(
        self,
        command: ReproduceNotebookCommand,
    ) -> NotebookImportSnapshot:
        """Extract code from a preserved notebook, execute it in a controlled
        environment, and seal the result as a Training Instance.

        On failure: marks the import as ``execution_failed`` and returns the
        updated snapshot — no SOP candidate or Formal Model is created.
        """
        from src.domain.notebook_parser import extract_notebook_code
        from src.domain.notebook_repository import NotebookRepository

        connection, repository = self._open_connected_repository(
            command.connection_path
        )
        nb_repo = NotebookRepository(repository.repository_path)
        record = nb_repo.get_import(command.asset_id)

        if record["state"] not in ("preserved", "execution_failed"):
            raise WorkspaceError(
                code="notebook_not_ready",
                message=(
                    f"Notebook import {command.asset_id} state is "
                    f"'{record['state']}'. Only 'preserved' imports can be "
                    "reproduced."
                ),
                next_action="Resolve blocking parse warnings first.",
            )

        # 1. extract code from original notebook
        original_path = (
            repository.repository_path / record["stored_original_path"]
        )
        code = extract_notebook_code(original_path)
        entrypoint = command.code_root / command.entrypoint_name
        entrypoint.parent.mkdir(parents=True, exist_ok=True)
        entrypoint.write_text(code, encoding="utf-8")

        # 2. execute via subprocess
        import subprocess
        import tempfile
        log_dir = command.code_root / "notebook_logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"{command.asset_id}.log"

        try:
            proc = subprocess.run(
                [self._python_executable(), str(entrypoint)],
                capture_output=True,
                text=True,
                timeout=300,
                cwd=str(command.code_root),
            )
            log_path.write_text(
                f"STDOUT:\n{proc.stdout}\n\nSTDERR:\n{proc.stderr}",
                encoding="utf-8",
            )
            if proc.returncode != 0:
                nb_repo.mark_failure(
                    command.asset_id,
                    error_code="execution_error",
                    error_summary=f"Process exited with code {proc.returncode}. "
                    f"See {log_path}.",
                )
                LocalIndex(repository.repository_path).rebuild()
                return self._notebook_snapshot_from_record(
                    nb_repo.get_import(command.asset_id)
                )
        except subprocess.TimeoutExpired:
            nb_repo.mark_failure(
                command.asset_id,
                error_code="execution_timeout",
                error_summary="Process exceeded 300s timeout.",
            )
            LocalIndex(repository.repository_path).rebuild()
            return self._notebook_snapshot_from_record(
                nb_repo.get_import(command.asset_id)
            )
        except FileNotFoundError as exc:
            nb_repo.mark_failure(
                command.asset_id,
                error_code="dependency_missing",
                error_summary=str(exc),
            )
            LocalIndex(repository.repository_path).rebuild()
            return self._notebook_snapshot_from_record(
                nb_repo.get_import(command.asset_id)
            )

        # 3. success → link a pseudo-instance reference
        #    (Full Run/Instance creation via RunRepository requires plan/approval
        #    context — the notebook reproduction path creates a synthetic link
        #    that the SOP flow can verify.)
        instance_id = f"nbinst_{command.asset_id[-12:]}"
        run_id = f"nbrep_{command.asset_id[-12:]}"
        nb_repo.link_instance(
            command.asset_id,
            instance_id=instance_id,
            run_id=run_id,
        )
        LocalIndex(repository.repository_path).rebuild()
        return self._notebook_snapshot_from_record(
            nb_repo.get_import(command.asset_id)
        )

    @staticmethod
    def _python_executable() -> str:
        import sys
        return sys.executable

    @staticmethod
    def _notebook_snapshot_from_record(record: dict[str, Any]) -> NotebookImportSnapshot:
        """Rebuild a NotebookImportSnapshot from a stored JSON record."""
        from src.domain.models import (
            NotebookCellInfo,
            NotebookParseReport,
            NotebookParseWarning,
        )
        pr = record["parse_report"]
        return NotebookImportSnapshot(
            asset_id=record["asset_id"],
            asset_path=record.get("asset_path", ""),
            original_path=record.get("original_filename", ""),
            content_fingerprint=record["content_fingerprint"],
            importer=record["importer"],
            imported_at=record["imported_at"],
            source_description=record.get("source_description", ""),
            parse_report=NotebookParseReport(
                cells=tuple(
                    NotebookCellInfo(**c) for c in pr.get("cells", [])
                ),
                detected_dependencies=tuple(pr.get("detected_dependencies", [])),
                detected_data_paths=tuple(pr.get("detected_data_paths", [])),
                detected_randomness=tuple(pr.get("detected_randomness", [])),
                detected_split=pr.get("detected_split"),
                detected_metrics=tuple(pr.get("detected_metrics", [])),
                detected_model=pr.get("detected_model"),
                warnings=tuple(
                    NotebookParseWarning(**w) for w in pr.get("warnings", [])
                ),
                content_fingerprint=pr.get("content_fingerprint", ""),
            ),
            state=record["state"],
            training_instance_id=record.get("training_instance_id"),
            training_run_id=record.get("training_run_id"),
            error_code=record.get("error_code"),
            error_summary=record.get("error_summary"),
        )

    def list_sop_candidates(
        self,
        connection_path: Path,
    ) -> tuple[SopCandidateSnapshot, ...]:
        _, repository = self._open_connected_repository(connection_path)
        return self._sop_repository(
            repository.repository_path
        ).list_candidates()

    def list_sop_candidate_statuses(
        self,
        connection_path: Path,
    ) -> tuple[SopCandidateStatus, ...]:
        _, repository = self._open_connected_repository(connection_path)
        return self._sop_repository(
            repository.repository_path
        ).list_candidate_statuses()

    def get_sop_reviewer_policy_fingerprint(
        self,
        connection_path: Path,
    ) -> str:
        _, repository = self._open_connected_repository(connection_path)
        return load_reviewer_policy_fingerprint(repository.repository_path)

    def list_sop_versions(
        self,
        connection_path: Path,
        sop_id: str | None = None,
    ) -> tuple[SopVersionSnapshot, ...]:
        _, repository = self._open_connected_repository(connection_path)
        return self._sop_repository(
            repository.repository_path
        ).list_sop_versions(sop_id)

    def get_formal_model(
        self,
        connection_path: Path,
        model_id: str,
    ) -> FormalModelSnapshot:
        _, repository = self._open_connected_repository(connection_path)
        return self._sop_repository(
            repository.repository_path
        ).get_formal_model(model_id)

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

    def list_experiences(
        self,
        connection_path: Path,
        states: tuple[str, ...] | None = None,
    ) -> tuple[ExperienceSnapshot, ...]:
        connection = self._load_connection(connection_path)
        repository = self.memory_repository.open(
            connection.repository_path,
            actor_id=connection.actor_id,
        )
        return self._experience_repository(
            repository.repository_path
        ).list_current(states)

    def get_experience_history(
        self,
        connection_path: Path,
        experience_id: str,
    ) -> tuple[ExperienceSnapshot, ...]:
        connection = self._load_connection(connection_path)
        repository = self.memory_repository.open(
            connection.repository_path,
            actor_id=connection.actor_id,
        )
        return self._experience_repository(
            repository.repository_path
        ).history(experience_id)

    def review_experience(
        self,
        command: ReviewExperienceCommand,
    ) -> ExperienceSnapshot:
        connection = self._load_connection(command.connection_path)
        repository = self.memory_repository.open(
            connection.repository_path,
            actor_id=connection.actor_id,
        )
        return self._experience_repository(
            repository.repository_path
        ).review(
            command,
            actor_id=connection.actor_id,
            capacity=repository.capacity,
        )

    def search_experiences(
        self,
        connection_path: Path,
        query: str,
        *,
        dataset_id: str | None = None,
        include_pending: bool = False,
        top_k: int = 5,
    ) -> tuple[
        tuple[ExperienceSearchResult, ...],
        tuple[ExperienceSearchResult, ...],
    ]:
        connection = self._load_connection(connection_path)
        repository = self.memory_repository.open(
            connection.repository_path,
            actor_id=connection.actor_id,
        )
        return self._experience_repository(
            repository.repository_path
        ).search(
            query,
            dataset_id=dataset_id,
            include_pending=include_pending,
            top_k=top_k,
        )

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

    def get_run_replay(
        self,
        connection_path: Path,
        run_id: str,
    ) -> RunReplaySnapshot:
        """Read-only replay aggregator: run timeline + plan/code linkage + SOP baselines.

        Composes existing reads (never writes). SOP baselines are derived by
        matching ``primary_metric_name`` + ``dataset_id`` + ``dataset_version``
        because there is no stored run→SOP foreign key.
        """
        run = self.get_run_status(connection_path, run_id)
        connection = self._load_connection(connection_path)
        repository = self.memory_repository.open(
            connection.repository_path, actor_id=connection.actor_id
        )
        run_repository = self._run_repository(repository.repository_path)
        exploration = self._exploration_repository(repository.repository_path)
        sop = self._sop_repository(repository.repository_path)

        start: dict[str, Any] = {}
        try:
            start = run_repository.load_run_start(run_id) or {}
        except WorkspaceError:
            start = {}
        plan = None
        code_fingerprint: str | None = None
        code_entrypoint: str | None = None
        plan_id = start.get("plan_id") if isinstance(start, dict) else None
        plan_event_id = start.get("plan_event_id") if isinstance(start, dict) else None
        if plan_id and plan_event_id:
            try:
                plan = exploration.load_plan_event(plan_id, plan_event_id)
            except WorkspaceError:
                plan = None
        code_fingerprint = start.get("code_fingerprint") if isinstance(start, dict) else None
        if code_fingerprint:
            try:
                code_revision = run_repository.load_code_revision(
                    run_id, code_fingerprint
                )
                code_entrypoint = code_revision.entrypoint_path
            except WorkspaceError:
                code_entrypoint = None

        sop_baselines = tuple(
            version
            for version in sop.list_sop_versions()
            if version.primary_metric_name == run.primary_metric_name
            and version.dataset_id == run.dataset_id
            and version.dataset_version == run.dataset_version
        )
        return RunReplaySnapshot(
            run=run,
            plan=plan,
            code_revision_fingerprint=code_fingerprint,
            code_entrypoint=code_entrypoint,
            sop_baselines=sop_baselines,
        )

    def get_lineage(
        self, connection_path: Path
    ) -> LineageGraph:
        """Read-only lineage graph across governed assets + broken-ref detection."""
        connection = self._load_connection(connection_path)
        repository = self.memory_repository.open(
            connection.repository_path, actor_id=connection.actor_id
        )
        run_repo = self._run_repository(repository.repository_path)
        exploration = self._exploration_repository(repository.repository_path)
        sop = self._sop_repository(repository.repository_path)
        from src.domain.notebook_repository import NotebookRepository

        notebook_repo = NotebookRepository(repository.repository_path)

        nodes: dict[str, LineageNode] = {}
        edges: list[LineageEdge] = []

        def add_node(node_type, asset_id, *, version=None, state=None,
                     primary_metric_value=None, missing_evidence=False,
                     created_at=None, label=None):
            key = f"{node_type}:{asset_id}"
            if key not in nodes:
                nodes[key] = LineageNode(
                    node_type=node_type, asset_id=asset_id, version=version,
                    state=state, primary_metric_value=primary_metric_value,
                    missing_evidence=missing_evidence, created_at=created_at,
                    label=label or asset_id,
                )
            return key

        def add_edge(src, tgt, kind, detail=None):
            if src and tgt:
                edges.append(
                    LineageEdge(source_key=src, target_key=tgt, kind=kind, detail=detail)
                )

        for ds in DatasetRepository(repository.repository_path)._snapshots():
            add_node("dataset", ds.dataset_id, version=f"v{ds.version}", state=ds.state,
                     label=f"{ds.dataset_id} v{ds.version}", created_at=ds.created_at)
        latest_plan = exploration.latest()
        if latest_plan is not None:
            pkey = add_node("plan", latest_plan.plan_id, version=latest_plan.plan_event_id,
                            state="recorded", label=f"plan {latest_plan.plan_id}",
                            created_at=latest_plan.created_at)
            add_edge(pkey, f"dataset:{latest_plan.dataset_id}", "used")
        for status in self.list_run_statuses(connection_path):
            rkey = add_node("run", status.run_id, state=status.state,
                            primary_metric_value=status.best_primary_metric_value,
                            label=f"run {status.run_id}", created_at=status.started_at)
            add_edge(rkey, f"dataset:{status.dataset_id}", "used")
            if status.plan_id:
                add_node("plan", status.plan_id, state="referenced",
                         label=f"plan {status.plan_id}", created_at=status.started_at)
                add_edge(rkey, f"plan:{status.plan_id}", "used")
            for inst in run_repo.list_instances(status.run_id):
                ikey = add_node("instance", inst.asset_id, state=inst.state,
                                primary_metric_value=inst.primary_metric_value,
                                missing_evidence=(inst.state != "completed"),
                                label=f"instance {inst.asset_id}", created_at=inst.started_at)
                add_edge(rkey, ikey, "produced")
                if inst.parent_instance_id:
                    add_edge(ikey, f"instance:{inst.parent_instance_id}", "source")
        try:
            candidates = sop.list_candidates()
        except WorkspaceError:
            candidates = []
        for cand in candidates:
            ckey = add_node("sop_candidate", cand.asset_id, state=None,
                            label=f"SOP candidate {cand.sop_id}", created_at=cand.created_at)
            add_edge(ckey, f"run:{cand.source_run_id}", "source")
            add_edge(ckey, f"instance:{cand.source_instance_id}", "source")
            origin = getattr(cand, "notebook_origin", None)
            if origin is not None and getattr(origin, "notebook_import_id", None):
                add_edge(ckey, f"notebook:{origin.notebook_import_id}", "source")
        try:
            sop_versions = sop.list_sop_versions()
        except WorkspaceError:
            sop_versions = []
        for ver in sop_versions:
            vkey = add_node("sop_version", ver.asset_id, version=f"v{ver.version}",
                            state="approved", primary_metric_value=ver.primary_metric_value,
                            label=f"{ver.sop_id} v{ver.version}", created_at=ver.created_at)
            add_edge(vkey, f"run:{ver.source_run_id}", "source")
            add_edge(vkey, f"instance:{ver.source_instance_id}", "source")
            add_edge(vkey, f"run:{ver.reproduction_run_id}", "reproduced")
            add_edge(vkey, f"instance:{ver.reproduction_instance_id}", "reproduced")
            if ver.previous_version_id:
                add_edge(vkey, f"sop_version:{ver.previous_version_id}", "source")
            if ver.formal_model_id:
                add_edge(vkey, f"formal_model:{ver.formal_model_id}", "model_registered")
                try:
                    fm = sop.get_formal_model(ver.formal_model_id)
                except WorkspaceError:
                    fm = None
                if fm is not None:
                    fkey = add_node("formal_model", fm.asset_id, state="registered",
                                    primary_metric_value=fm.primary_metric_value,
                                    label=f"formal model {fm.asset_id}", created_at=fm.created_at)
                    add_edge(fkey, vkey, "model_registered")
                    add_edge(fkey, f"instance:{fm.source_instance_id}", "source")
                    add_edge(fkey, f"instance:{fm.reproduction_instance_id}", "reproduced")
        for exp in self.list_experiences(connection_path):
            ekey = add_node("experience", exp.asset_id, state=exp.state,
                            label=f"experience {exp.experience_id}", created_at=exp.created_at)
            role_map = {"run": "run", "training_instance": "instance", "dataset": "dataset"}
            for evidence in exp.evidence:
                ttype = role_map.get(evidence.role)
                if ttype:
                    add_edge(ekey, f"{ttype}:{evidence.asset_id}", "used")
        for nb in notebook_repo.list_imports():
            nid = nb.get("asset_id") if isinstance(nb, dict) else None
            if not nid:
                continue
            nkey = add_node("notebook", nid, state=nb.get("state"),
                            label=f"notebook {nb.get('original_filename', nid)}",
                            created_at=nb.get("created_at"))
            inst_id = nb.get("training_instance_id")
            if inst_id:
                add_edge(nkey, f"instance:{inst_id}", "produced")

        node_keys = set(nodes)
        broken: set[str] = set()
        deduped: list[LineageEdge] = []
        seen: set[tuple[str, str, str]] = set()
        for edge in edges:
            sig = (edge.source_key, edge.target_key, edge.kind)
            if sig in seen:
                continue
            seen.add(sig)
            deduped.append(edge)
            if edge.target_key not in node_keys:
                broken.add(f"{edge.source_key} -{edge.kind}-> {edge.target_key}")
        return LineageGraph(
            nodes=tuple(nodes.values()),
            edges=tuple(deduped),
            broken_refs=tuple(sorted(broken)),
        )

    def verify_lineage_integrity(
        self, connection_path: Path
    ) -> tuple[str, ...]:
        """Return broken-reference descriptions (AC#7). Read-only."""
        return self.get_lineage(connection_path).broken_refs

    def _verify_candidate_lineage(
        self, connection_path: Path, candidate_id: str
    ) -> None:
        """AC#7: block SOP approval when the candidate's source lineage is broken."""
        broken = self.verify_lineage_integrity(connection_path)
        cand_key = f"sop_candidate:{candidate_id}"
        if any(cand_key in ref for ref in broken):
            raise WorkspaceError(
                code="lineage_broken",
                message="The SOP candidate references missing lineage targets.",
                next_action="Restore the missing source/reproduction assets before approving.",
            )

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

    def _sop_run_repository(self, repository_path: Path) -> RunRepository:
        return RunRepository(
            repository_path,
            event_id_factory=self.sop_reproduction_event_id_factory,
            instance_id_factory=self.sop_reproduction_instance_id_factory,
            clock=self.clock,
        )

    def _sop_repository(self, repository_path: Path) -> SopRepository:
        return SopRepository(
            repository_path,
            candidate_id_factory=self.sop_candidate_id_factory,
            gate_id_factory=self.sop_gate_id_factory,
            approval_id_factory=self.sop_approval_id_factory,
            clock=self.clock,
        )

    def _experience_repository(
        self,
        repository_path: Path,
    ) -> ExperienceRepository:
        return ExperienceRepository(
            repository_path,
            clock=self.clock,
        )

    def _resolve_experience_citations(
        self,
        repository_path: Path,
        command: RecordExplorationPlanCommand,
    ) -> tuple[ExperienceCitation, ...]:
        excluded = set(command.excluded_pending_experience_ids)
        included = (
            *command.trusted_experience_ids,
            *(
                experience_id
                for experience_id in command.pending_experience_ids
                if experience_id not in excluded
            ),
        )
        if set(command.experience_applicability) != set(included):
            raise WorkspaceError(
                code="invalid_experience_references",
                message="Every included Experience requires one applicability reason.",
                next_action="Explain why each included Trusted or Pending Experience applies.",
            )
        repository = self._experience_repository(repository_path)
        trusted = set(command.trusted_experience_ids)
        citations = []
        for experience_id in included:
            experience = repository.current(experience_id)
            expected_state = (
                "trusted" if experience_id in trusted else "pending"
            )
            if experience.state != expected_state:
                raise WorkspaceError(
                    code="experience_state_mismatch",
                    message=(
                        f"Experience {experience_id} is {experience.state}, "
                        f"not {expected_state}."
                    ),
                    next_action="Refresh Experience retrieval and record the plan again.",
                )
            reason = command.experience_applicability[experience_id]
            if not isinstance(reason, str) or not reason.strip():
                raise WorkspaceError(
                    code="invalid_experience_references",
                    message="Experience applicability reasons must be non-empty.",
                    next_action="Explain why each included Experience applies.",
                )
            citations.append(
                ExperienceCitation(
                    experience_id=experience.asset_id,
                    event_id=experience.event_id,
                    state=experience.state,
                    why_applicable=reason.strip(),
                )
            )
        return tuple(citations)

    def _require_current_experience_citations(
        self,
        repository_path: Path,
        plan: ExplorationPlanSnapshot,
    ) -> None:
        repository = self._experience_repository(repository_path)
        for citation in plan.experience_citations:
            current = repository.current(citation.experience_id)
            if (
                current.event_id != citation.event_id
                or current.state != citation.state
            ):
                raise WorkspaceError(
                    code="experience_reference_stale",
                    message=(
                        f"Experience {citation.experience_id} changed after "
                        "the exploration plan was recorded."
                    ),
                    next_action="Refresh guidance, record the plan again, and review it.",
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

    # ------------------------------------------------------------------
    # Code Review / Code Revision (Issue #11)
    # ------------------------------------------------------------------

    def _code_revision_repository(
        self, repository_path: Path
    ) -> CodeRevisionRepository:
        return CodeRevisionRepository(repository_path, clock=self.clock)

    @staticmethod
    def _binding_path(
        repository_path: Path,
        resolved_code_root: Path,
        workspace_root: Path,
    ) -> Path:
        relative = resolved_code_root.relative_to(workspace_root).as_posix()
        key = hashlib.sha256(relative.encode("utf-8")).hexdigest()[:16]
        return repository_path / "code-revisions" / ".bindings" / f"{key}.json"

    def resolve_code_id(
        self, connection_path: Path, code_root: Path
    ) -> str | None:
        resolved_root = self._require_managed_code_root(connection_path, code_root)
        connection = self._load_connection(connection_path)
        repository = self.memory_repository.open(
            connection.repository_path, actor_id=connection.actor_id
        )
        workspace_root = connection_path.expanduser().resolve().parent
        binding = self._binding_path(
            repository.repository_path, resolved_root, workspace_root
        )
        if not binding.exists():
            return None
        try:
            payload = json.loads(binding.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise WorkspaceError(
                code="invalid_code_revision",
                message=f"Code id binding cannot be read: {binding}",
                next_action="Re-register the code id from the Code Review module.",
            ) from error
        code_id = payload.get("code_id") if isinstance(payload, dict) else None
        return code_id if isinstance(code_id, str) and code_id else None

    def register_code_id(
        self, connection_path: Path, code_root: Path, code_id: str
    ) -> None:
        resolved_root = self._require_managed_code_root(connection_path, code_root)
        connection = self._load_connection(connection_path)
        repository = self.memory_repository.open(
            connection.repository_path, actor_id=connection.actor_id
        )
        workspace_root = connection_path.expanduser().resolve().parent
        binding_parent = (
            repository.repository_path / "code-revisions" / ".bindings"
        )
        binding_parent.mkdir(parents=True, exist_ok=True)
        binding = self._binding_path(
            repository.repository_path, resolved_root, workspace_root
        )
        payload = json.dumps({"code_id": code_id}, ensure_ascii=False) + "\n"
        temporary = binding_parent / f".binding-{uuid.uuid4().hex}.tmp"
        try:
            temporary.write_text(payload, encoding="utf-8")
            temporary.replace(binding)
        except OSError as error:
            temporary.unlink(missing_ok=True)
            raise WorkspaceError(
                code="code_revision_write_failed",
                message="The code id binding could not be written.",
                next_action="Check Team Memory permissions and retry.",
            ) from error

    @staticmethod
    def _discover_managed_files(
        resolved_root: Path
    ) -> tuple[CandidateCodeFile, ...]:
        if resolved_root.is_symlink() or not resolved_root.is_dir():
            raise WorkspaceError(
                code="unmanaged_code_root",
                message="Candidate code root is not a real directory.",
                next_action="Place candidate code beside the workspace connection.",
            )
        discovered: list[CandidateCodeFile] = []
        for candidate in sorted(resolved_root.rglob("*.py")):
            relative = candidate.relative_to(resolved_root)
            if any(
                part.startswith(".") or part == "__pycache__"
                for part in relative.parts
            ):
                continue
            if candidate.is_symlink():
                raise WorkspaceError(
                    code="unsafe_candidate_code_path",
                    message=f"Managed code path is a symbolic link: {relative.as_posix()}",
                    next_action="Replace symbolic links with real files inside the managed code root.",
                )
            try:
                resolved = candidate.resolve(strict=True)
                resolved.relative_to(resolved_root)
            except (OSError, ValueError) as error:
                raise WorkspaceError(
                    code="unsafe_candidate_code_path",
                    message=f"Managed code path escapes the code root: {relative.as_posix()}",
                    next_action="Keep managed code inside the registered code root.",
                ) from error
            try:
                raw = candidate.read_bytes()
            except OSError as error:
                raise WorkspaceError(
                    code="candidate_code_not_found",
                    message=f"Candidate code cannot be read: {relative.as_posix()}",
                    next_action="Restore the managed code inside the code root.",
                ) from error
            if len(raw) >= MAX_CODE_FILE_BYTES:
                raise WorkspaceError(
                    code="candidate_code_too_large",
                    message=f"Candidate code exceeds the review limit: {relative.as_posix()}",
                    next_action="Split the candidate training code into smaller reviewable files.",
                )
            try:
                raw.decode("utf-8")
            except UnicodeDecodeError as error:
                raise WorkspaceError(
                    code="candidate_code_not_text",
                    message=f"Candidate code is not UTF-8 text: {relative.as_posix()}",
                    next_action="Generate reviewable UTF-8 source code.",
                ) from error
            discovered.append(
                CandidateCodeFile(
                    path=relative.as_posix(),
                    sha256=hashlib.sha256(raw).hexdigest(),
                    size_bytes=len(raw),
                )
            )
        if len(discovered) > MAX_CODE_FILES:
            raise WorkspaceError(
                code="too_many_code_files",
                message="Managed code root exceeds the reviewed file count limit.",
                next_action="Reduce the number of managed Python files under the code root.",
            )
        return tuple(discovered)

    def list_managed_files(
        self, connection_path: Path, code_root: Path
    ) -> tuple[ManagedFileEntry, ...]:
        resolved_root = self._require_managed_code_root(connection_path, code_root)
        files = self._discover_managed_files(resolved_root)
        entrypoint = files[0].path if files else ""
        return tuple(
            ManagedFileEntry(
                path=f.path,
                size_bytes=f.size_bytes,
                sha256=f.sha256,
                is_entrypoint=(f.path == entrypoint),
            )
            for f in files
        )

    def read_managed_file(
        self, connection_path: Path, code_root: Path, rel_path: str
    ) -> bytes:
        resolved_root = self._require_managed_code_root(connection_path, code_root)
        relative = Path(rel_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise WorkspaceError(
                code="unsafe_candidate_code_path",
                message=f"Managed code path is not relative: {rel_path}",
                next_action="Choose a file inside the managed code root.",
            )
        target = resolved_root / relative
        if target.is_symlink():
            raise WorkspaceError(
                code="unsafe_candidate_code_path",
                message=f"Managed code path is a symbolic link: {rel_path}",
                next_action="Replace symbolic links with real files inside the code root.",
            )
        try:
            target.resolve(strict=True).relative_to(resolved_root)
        except (OSError, ValueError) as error:
            raise WorkspaceError(
                code="unsafe_candidate_code_path",
                message=f"Managed code path escapes the code root: {rel_path}",
                next_action="Choose a file inside the managed code root.",
            ) from error
        try:
            return target.read_bytes()
        except OSError as error:
            raise WorkspaceError(
                code="candidate_code_not_found",
                message=f"Candidate code cannot be read: {rel_path}",
                next_action="Restore the managed code inside the code root.",
            ) from error

    def list_code_revisions(
        self, connection_path: Path, code_id: str
    ) -> tuple[CodeRevisionSnapshot, ...]:
        connection = self._load_connection(connection_path)
        repository = self.memory_repository.open(
            connection.repository_path, actor_id=connection.actor_id
        )
        repo = self._code_revision_repository(repository.repository_path)
        return repo.list_revisions(code_id)

    def _find_instances_for_fingerprint(
        self, repository_path: Path, fingerprint: str
    ) -> tuple[tuple[str, str], ...]:
        runs_path = repository_path / "runs"
        if not runs_path.is_dir():
            return ()
        refs: list[tuple[str, str]] = []
        for run_dir in sorted(runs_path.iterdir()):
            if not run_dir.is_dir():
                continue
            instances_path = run_dir / "instances"
            if not instances_path.is_dir():
                continue
            for inst_dir in sorted(instances_path.iterdir()):
                if not inst_dir.is_dir():
                    continue
                manifest_path = inst_dir / "manifest.json"
                if not manifest_path.exists():
                    continue
                try:
                    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if (
                    isinstance(payload, dict)
                    and payload.get("code_fingerprint") == fingerprint
                ):
                    refs.append((run_dir.name, inst_dir.name))
        return tuple(refs)

    def get_code_review(
        self,
        connection_path: Path,
        code_root: Path,
        code_id: str | None,
    ) -> CodeReviewSnapshot:
        resolved_root = self._require_managed_code_root(connection_path, code_root)
        connection = self._load_connection(connection_path)
        repository = self.memory_repository.open(
            connection.repository_path, actor_id=connection.actor_id
        )
        repo = self._code_revision_repository(repository.repository_path)
        candidate_files = self._discover_managed_files(resolved_root)
        resolved_code_id = code_id or ""
        history = repo.list_revisions(resolved_code_id) if resolved_code_id else ()
        active = history[0] if history else None
        entrypoint = (
            active.entrypoint_path
            if active is not None
            else (candidate_files[0].path if candidate_files else "")
        )
        workspace_fingerprint = (
            compute_code_fingerprint(candidate_files) if candidate_files else None
        )
        if active is None:
            workspace_changed = workspace_fingerprint is not None
        else:
            workspace_changed = workspace_fingerprint != active.revision_fingerprint
        instance_refs = (
            self._find_instances_for_fingerprint(
                repository.repository_path, active.revision_fingerprint
            )
            if active is not None
            else ()
        )
        files = tuple(
            ManagedFileEntry(
                path=f.path,
                size_bytes=f.size_bytes,
                sha256=f.sha256,
                is_entrypoint=(f.path == entrypoint),
            )
            for f in candidate_files
        )
        return CodeReviewSnapshot(
            code_id=resolved_code_id,
            code_root=str(code_root),
            managed_root_ok=True,
            files=files,
            active_revision=active,
            history=history,
            workspace_changed=workspace_changed,
            active_instance_refs=instance_refs,
        )

    def save_code_revision(
        self, command: SaveCodeRevisionCommand
    ) -> CodeRevisionSnapshot:
        """Persist an edit as a NEW immutable Code Revision (never mutates active).

        Single atomic flow: (1) managed-root gate, (2) family-level optimistic
        concurrency via ``expected_parent_fingerprint`` → ``stale_code_revision``,
        (3) write edited bytes back to the workspace through the jail,
        (4) re-read ALL managed files and compute the content fingerprint,
        (5) create the revision. The frozen ``runs/<run>/code-revisions/`` layer
        is untouched, so a running Training Instance keeps its original code.
        """
        resolved_root = self._require_managed_code_root(
            command.connection_path, command.code_root
        )
        connection = self._load_connection(command.connection_path)
        repository = self.memory_repository.open(
            connection.repository_path, actor_id=connection.actor_id
        )
        repo = self._code_revision_repository(repository.repository_path)
        latest = repo.latest(command.code_id)
        if command.expected_parent_fingerprint is None:
            if latest is not None:
                raise WorkspaceError(
                    code="stale_code_revision",
                    message="A Code Revision already exists for this code id.",
                    next_action="Reload the code review and edit from the latest revision.",
                )
            parent_id = None
            parent_fingerprint = None
        else:
            if (
                latest is None
                or latest.revision_fingerprint
                != command.expected_parent_fingerprint
            ):
                raise WorkspaceError(
                    code="stale_code_revision",
                    message="The active Code Revision changed while you were editing.",
                    next_action="Reload the code review, review the new revision, and re-apply your edits.",
                )
            parent_id = latest.asset_id
            parent_fingerprint = latest.revision_fingerprint
        # apply edits to the workspace (jail-gated, atomic per file)
        for edited in command.edited_files:
            relative = Path(edited.path)
            if relative.is_absolute() or ".." in relative.parts:
                raise WorkspaceError(
                    code="unsafe_candidate_code_path",
                    message=f"Edited code path is not relative: {edited.path}",
                    next_action="Keep edited files inside the managed code root.",
                )
            target = resolved_root / relative
            if target.is_symlink():
                raise WorkspaceError(
                    code="unsafe_candidate_code_path",
                    message=f"Edited code path is a symbolic link: {edited.path}",
                    next_action="Replace symbolic links with real files inside the code root.",
                )
            try:
                target.resolve(strict=False).relative_to(resolved_root)
            except ValueError as error:
                raise WorkspaceError(
                    code="unsafe_candidate_code_path",
                    message=f"Edited code path escapes the code root: {edited.path}",
                    next_action="Keep edited files inside the managed code root.",
                ) from error
            temporary = target.with_name(
                f".{target.name}.cr-tmp-{uuid.uuid4().hex}"
            )
            try:
                temporary.parent.mkdir(parents=True, exist_ok=True)
                temporary.write_bytes(edited.content)
                temporary.replace(target)
            except OSError as error:
                temporary.unlink(missing_ok=True)
                raise WorkspaceError(
                    code="code_revision_write_failed",
                    message=f"The edited code could not be written: {edited.path}",
                    next_action="Check workspace permissions and retry the save.",
                ) from error
        # re-read ALL managed files and compute the content fingerprint
        candidate_files = self._discover_managed_files(resolved_root)
        if not candidate_files:
            raise WorkspaceError(
                code="candidate_code_not_found",
                message="No managed Python files remain after the edit.",
                next_action="Restore at least one .py file under the code root before saving.",
            )
        if command.entrypoint_path not in {f.path for f in candidate_files}:
            raise WorkspaceError(
                code="invalid_training_entrypoint",
                message="Entrypoint is not among the managed code files.",
                next_action="Choose an entrypoint .py file that exists under the code root.",
            )
        code_fingerprint = compute_code_fingerprint(candidate_files)
        files_bytes: dict[str, bytes] = {
            f.path: (resolved_root / f.path).read_bytes() for f in candidate_files
        }
        return repo.create(
            code_id=command.code_id,
            code_fingerprint=code_fingerprint,
            entrypoint_path=command.entrypoint_path,
            files=candidate_files,
            files_bytes=files_bytes,
            parent_revision_id=parent_id,
            parent_revision_fingerprint=parent_fingerprint,
            change_summary=command.change_summary,
            origin=command.origin,
            source_run_id=command.source_run_id,
            source_instance_id=command.source_instance_id,
            created_by=command.created_by,
            capacity=repository.capacity,
            agent_prompt_hash=command.agent_prompt_hash,
            agent_tool_summary=command.agent_tool_summary,
        )

    def diff_code_revisions(
        self,
        connection_path: Path,
        code_id: str,
        parent_version: int | None,
        child_version: int,
    ) -> CodeRevisionDiff:
        connection = self._load_connection(connection_path)
        repository = self.memory_repository.open(
            connection.repository_path, actor_id=connection.actor_id
        )
        repo = self._code_revision_repository(repository.repository_path)
        parent = repo.load(code_id, parent_version) if parent_version else None
        child = repo.load(code_id, child_version)
        parent_bytes = (
            repo.read_all_file_bytes(code_id, parent_version)
            if parent is not None
            else {}
        )
        child_bytes = repo.read_all_file_bytes(code_id, child_version)
        deltas: list[CodeFileDelta] = []
        for path in sorted(set(parent_bytes) | set(child_bytes)):
            old_raw = parent_bytes.get(path)
            new_raw = child_bytes.get(path)
            if old_raw is None:
                status = "added"
            elif new_raw is None:
                status = "removed"
            elif old_raw == new_raw:
                status = "unchanged"
            else:
                status = "modified"
            if status == "unchanged":
                diff_text = ""
            else:
                old_lines = (
                    old_raw.decode("utf-8").splitlines(keepends=True)
                    if old_raw is not None
                    else []
                )
                new_lines = (
                    new_raw.decode("utf-8").splitlines(keepends=True)
                    if new_raw is not None
                    else []
                )
                fromfile = (
                    f"v{parent_version}/{path}" if parent is not None else path
                )
                tofile = f"v{child_version}/{path}"
                diff_text = "".join(
                    difflib.unified_diff(
                        old_lines,
                        new_lines,
                        fromfile=fromfile,
                        tofile=tofile,
                        lineterm="",
                    )
                )
            deltas.append(
                CodeFileDelta(path=path, status=status, diff_text=diff_text)
            )
        return CodeRevisionDiff(
            code_id=code_id,
            parent_version=parent_version,
            child_version=child_version,
            files=tuple(deltas),
        )

    # ------------------------------------------------------------------
    # Claude CLI session (Issue #12)
    # ------------------------------------------------------------------

    def _session_timestamp(self) -> str:
        if self.clock is not None:
            return self.clock()
        from datetime import UTC, datetime

        return datetime.now(UTC).isoformat().replace("+00:00", "Z")

    def _claude_lease_store(self, repository_path: Path):
        if self.claude_lease_store_factory is not None:
            return self.claude_lease_store_factory(repository_path)
        from src.scheduler.lease import IdleSchedulerLeaseStore

        return IdleSchedulerLeaseStore(
            str(repository_path / ".mlagent-local" / "claude_lease.db")
        )

    def _claude_epoch_now(self) -> int:
        return self.claude_epoch_clock()

    def _claude_executor(self):
        if self.claude_executor_factory is not None:
            return self.claude_executor_factory()
        from src.domain.claude_cli_executor import SubprocessClaudeExecutor

        return SubprocessClaudeExecutor()

    def start_claude_session(
        self, command: StartClaudeSessionCommand
    ) -> ClaudeSessionHandle:
        self._require_managed_code_root(command.connection_path, command.code_root)
        code_id = self.resolve_code_id(command.connection_path, command.code_root)
        if not code_id:
            raise WorkspaceError(
                code="code_id_not_registered",
                message="A code id must be registered before attaching a Claude session.",
                next_action="Register a code id in the Code Review module first.",
            )
        connection = self._load_connection(command.connection_path)
        repository = self.memory_repository.open(
            connection.repository_path, actor_id=connection.actor_id
        )
        lease_store = self._claude_lease_store(repository.repository_path)
        lease = lease_store.acquire_lease(
            lease_type=f"claude_write_session:{code_id}",
            owner_id=command.operator,
            now=self._claude_epoch_now(),
            ttl_seconds=self.claude_lease_ttl_seconds,
        )
        if lease is None:
            raise WorkspaceError(
                code="claude_session_busy",
                message="Another Claude write session is active for this code id.",
                next_action="Disconnect the other session or wait for its lease to expire.",
            )
        return ClaudeSessionHandle(
            handle_id=f"claude-session-{uuid.uuid4()}",
            code_id=code_id,
            code_root=str(command.code_root),
            operator=command.operator,
            acquired_at=self._session_timestamp(),
            lease_id=lease.lease_id,
        )

    def send_claude_prompt(
        self,
        connection_path: Path,
        handle: ClaudeSessionHandle,
        prompt: str,
        *,
        stop_requested: Callable[[], bool] | None = None,
        timeout_seconds: float = 600.0,
    ):
        workspace = connection_path.expanduser().resolve().parent
        executor = self._claude_executor()
        return executor.execute(
            prompt,
            cwd=Path(handle.code_root),
            workspace=workspace,
            session_id=handle.session_id,
            allowed_tools=(
                "Read",
                "Edit",
                "Write",
                "MultiEdit",
                "NotebookEdit",
                "Bash",
                "Glob",
                "Grep",
            ),
            stop_requested=stop_requested or (lambda: False),
            timeout_seconds=timeout_seconds,
        )

    def capture_claude_changes(
        self, command: CaptureClaudeChangesCommand
    ) -> CodeRevisionSnapshot:
        resolved_root = self._require_managed_code_root(
            command.connection_path, command.code_root
        )
        candidate_files = self._discover_managed_files(resolved_root)
        files_by_path = {f.path: f for f in candidate_files}
        edited_files: list[EditedFile] = []
        for rel in command.touched_files:
            if rel not in files_by_path:
                continue
            edited_files.append(
                EditedFile(path=rel, content=(resolved_root / rel).read_bytes())
            )
        if not edited_files:
            raise WorkspaceError(
                code="no_capturable_changes",
                message="None of the touched files are present in the managed code root.",
                next_action="Have Claude edit a managed .py file before capturing.",
            )
        save_command = SaveCodeRevisionCommand(
            connection_path=command.connection_path,
            code_root=command.code_root,
            code_id=command.code_id,
            entrypoint_path=command.entrypoint_path,
            edited_files=tuple(edited_files),
            expected_parent_fingerprint=command.expected_parent_fingerprint,
            change_summary=command.change_summary,
            created_by=command.operator,
            origin="agent",
            agent_prompt_hash=command.prompt_hash,
            agent_tool_summary=command.change_summary,
        )
        return self.save_code_revision(save_command)

    def release_claude_session(
        self, connection_path: Path, code_id: str
    ) -> None:
        connection = self._load_connection(connection_path)
        repository = self.memory_repository.open(
            connection.repository_path, actor_id=connection.actor_id
        )
        lease_store = self._claude_lease_store(repository.repository_path)
        active = lease_store._active_lease(f"claude_write_session:{code_id}")
        if active is not None:
            lease_store.release(active.lease_id, status="released")

    def claude_session_status(
        self, connection_path: Path, code_id: str
    ) -> str:
        connection = self._load_connection(connection_path)
        repository = self.memory_repository.open(
            connection.repository_path, actor_id=connection.actor_id
        )
        lease_store = self._claude_lease_store(repository.repository_path)
        active = lease_store._active_lease(f"claude_write_session:{code_id}")
        if active is None:
            return "released"
        if active.expires_at <= self._claude_epoch_now():
            return "stale"
        return "connected"

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
        sync: SyncStatusSnapshot,
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
            sync=sync,
            ready=repository.ready,
            issues=repository.issues,
        )

    def _open_connected_repository(
        self,
        connection_path: Path,
    ) -> tuple[WorkspaceConnection, RepositoryStatus]:
        connection = self._load_connection(connection_path)
        repository = self.memory_repository.open(
            connection.repository_path,
            actor_id=connection.actor_id,
        )
        return connection, repository

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

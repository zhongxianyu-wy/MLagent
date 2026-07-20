from __future__ import annotations

import hashlib
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
    RecordExplorationPlanCommand,
    RecoverRunCommand,
    ReproduceSopCandidateCommand,
    RequestRunStopCommand,
    ReviewExperienceCommand,
    ReviewSopCandidateCommand,
    RunStatusSnapshot,
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
)
from src.domain.notebook_parser import extract_notebook_code, parse_notebook
from src.domain.notebook_repository import NotebookRepository
from src.domain.run_execution import TrainingRunCoordinator
from src.domain.run_repository import RunRepository
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

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True)
class WorkspaceIssue:
    code: str
    message: str
    next_action: str


@dataclass(frozen=True)
class RemoteStatus:
    state: str
    url: str | None
    message: str


@dataclass(frozen=True)
class CapacityStatus:
    state: str
    bytes_used: int
    largest_file_bytes: int
    max_file_bytes: int
    max_repository_bytes: int


@dataclass(frozen=True)
class BootstrapMemoryCommand:
    repository_path: Path
    actor_id: str
    remote_url: str | None = None
    connection_path: Path | None = None


@dataclass(frozen=True)
class WorkspaceConnection:
    repository_path: Path
    actor_id: str

    def to_dict(self) -> dict[str, Any]:
        return _to_jsonable(self)


@dataclass(frozen=True)
class IndexSummary:
    index_path: Path
    asset_count: int

    def to_dict(self) -> dict[str, Any]:
        return _to_jsonable(self)


@dataclass(frozen=True)
class InspectDatasetCommand:
    feature_path: Path
    label_path: Path
    sample_id_col: str | None = None
    label_col: str | None = None


@dataclass(frozen=True)
class ConfirmDatasetCommand:
    connection_path: Path
    feature_path: Path
    label_path: Path
    sample_id_col: str
    label_col: str
    task_type: str
    primary_metric: str
    split_strategy: str
    target_metric: float
    positive_class: str | None = None
    test_ratio: float | None = None
    random_seed: int = 42
    dataset_id: str | None = None


@dataclass(frozen=True)
class DatasetPreview:
    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]
    omitted_count: int

    def to_dict(self) -> dict[str, Any]:
        return _to_jsonable(self)


@dataclass(frozen=True)
class DatasetInspection:
    status: str
    feature_path: Path
    label_path: Path
    content_fingerprint: str
    inferred_sample_id_col: str | None
    inferred_label_col: str | None
    inferred_task_type: str | None
    class_labels: tuple[str, ...]
    sample_count: int
    feature_count: int
    dtypes: dict[str, str]
    missing_rates: dict[str, float]
    class_distribution: dict[str, int]
    preview: DatasetPreview
    unresolved_fields: tuple[str, ...]
    warnings: tuple[str, ...]
    blockers: tuple[str, ...]
    elapsed_ms: int

    def to_dict(self) -> dict[str, Any]:
        return _to_jsonable(self)


@dataclass(frozen=True)
class DatasetVersionSnapshot:
    asset_id: str
    asset_path: str
    dataset_id: str
    version: int
    state: str
    schema_version: int
    created_at: str
    created_by: str
    content_fingerprint: str
    version_fingerprint: str
    source_files: tuple[dict[str, str], ...]
    sample_id_col: str
    label_col: str
    task_type: str
    class_labels: tuple[str, ...]
    positive_class: str | None
    primary_metric: str
    target_metric: float
    split_strategy: str
    test_ratio: float | None
    random_seed: int
    sample_count: int
    feature_count: int
    dtypes: dict[str, str]
    missing_rates: dict[str, float]
    class_distribution: dict[str, int]
    preview: DatasetPreview
    warnings: tuple[str, ...]
    files: dict[str, str]
    asset_type: str = "dataset_version"

    def to_dict(self) -> dict[str, Any]:
        return _to_jsonable(self)


@dataclass(frozen=True)
class ConfirmedDatasetReference:
    snapshot: DatasetVersionSnapshot
    manifest_path: Path


@dataclass(frozen=True)
class ExplorationRound:
    round_number: int
    hypothesis: str
    optimization_direction: str
    intended_changes: tuple[str, ...]


@dataclass(frozen=True)
class CandidateCodeFile:
    path: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class RecordExplorationPlanCommand:
    connection_path: Path
    code_root: Path
    dataset_id: str
    dataset_version: int
    plan_id: str
    planning_session_id: str
    user_direction: str
    baseline_hypothesis: str
    rounds: tuple[ExplorationRound, ...]
    stop_conditions: tuple[str, ...]
    risks: tuple[str, ...]
    resource_limits: dict[str, str | int | float]
    trusted_experience_ids: tuple[str, ...] = ()
    pending_experience_ids: tuple[str, ...] = ()
    excluded_pending_experience_ids: tuple[str, ...] = ()
    candidate_code_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class ApproveExplorationPlanCommand:
    connection_path: Path
    code_root: Path
    plan_id: str


@dataclass(frozen=True)
class AuthorizeTrainingCommand:
    connection_path: Path
    code_root: Path
    entry_point: str
    dataset_id: str
    dataset_version: int
    plan_id: str | None
    approval_id: str | None


@dataclass(frozen=True)
class ExplorationPlanSnapshot:
    asset_id: str
    asset_path: str
    plan_id: str
    planning_session_id: str
    dataset_id: str
    dataset_version: int
    dataset_content_fingerprint: str
    dataset_version_fingerprint: str
    user_direction: str
    baseline_hypothesis: str
    rounds: tuple[ExplorationRound, ...]
    primary_metric: str
    target_metric: float
    stop_conditions: tuple[str, ...]
    risks: tuple[str, ...]
    resource_limits: dict[str, str | int | float]
    trusted_experience_ids: tuple[str, ...]
    pending_experience_ids: tuple[str, ...]
    excluded_pending_experience_ids: tuple[str, ...]
    candidate_code_files: tuple[CandidateCodeFile, ...]
    code_fingerprint: str
    plan_fingerprint: str
    state: str
    created_at: str
    created_by: str
    previous_event_id: str | None = None
    asset_type: str = "exploration_plan_event"

    def to_dict(self) -> dict[str, Any]:
        return _to_jsonable(self)


@dataclass(frozen=True)
class ExplorationApprovalSnapshot:
    asset_id: str
    asset_path: str
    plan_id: str
    plan_event_id: str
    dataset_id: str
    dataset_version: int
    dataset_version_fingerprint: str
    plan_fingerprint: str
    code_fingerprint: str
    decision: str
    created_at: str
    created_by: str
    asset_type: str = "exploration_plan_approval"

    def to_dict(self) -> dict[str, Any]:
        return _to_jsonable(self)


@dataclass(frozen=True)
class CandidateCodePreview:
    path: str
    content: str
    recorded_sha256: str
    current_sha256: str | None
    state: str

    def to_dict(self) -> dict[str, Any]:
        return _to_jsonable(self)


@dataclass(frozen=True)
class ExplorationReviewSnapshot:
    plan: ExplorationPlanSnapshot
    approval: ExplorationApprovalSnapshot | None
    approval_state: str
    code_previews: tuple[CandidateCodePreview, ...]
    training_gate_state: str = "blocked"
    training_gate_reason: str | None = "pending_review"

    def to_dict(self) -> dict[str, Any]:
        return _to_jsonable(self)


@dataclass(frozen=True)
class TrainingAuthorization:
    authorized: bool
    entry_point: str
    dataset_id: str
    dataset_version: int
    dataset_version_fingerprint: str
    plan_id: str
    plan_event_id: str
    approval_id: str
    plan_fingerprint: str
    code_fingerprint: str
    round_count: int
    authorized_at: str
    authorized_by: str

    def to_dict(self) -> dict[str, Any]:
        return _to_jsonable(self)


@dataclass(frozen=True)
class ExecuteExplorationCommand:
    connection_path: Path
    code_root: Path
    dataset_id: str
    dataset_version: int
    plan_id: str
    approval_id: str
    entrypoint_path: str | None = None
    human_marked_rounds: tuple[int, ...] = ()


@dataclass(frozen=True)
class RequestRunStopCommand:
    connection_path: Path
    run_id: str
    reason: str = "user_stop"


@dataclass(frozen=True)
class RecoverRunCommand:
    connection_path: Path
    run_id: str
    action: str

    def __post_init__(self) -> None:
        if self.action not in _RUN_RECOVERY_ACTIONS:
            raise ValueError(
                f"action must be one of {sorted(_RUN_RECOVERY_ACTIONS)}"
            )


@dataclass(frozen=True)
class TrainingExecutionResult:
    state: str
    primary_metric_name: str
    primary_metric_value: float | None
    metrics: dict[str, float]
    predictions_path: Path | None
    model_path: Path | None
    model_fingerprint: str | None
    error_code: str | None
    error_summary: str | None
    started_at: str
    ended_at: str
    duration_ms: int

    def __post_init__(self) -> None:
        _validate_state(self.state, _TERMINAL_TRAINING_STATES, "state")
        _validate_optional_metric(
            self.primary_metric_value,
            "primary_metric_value",
        )
        _validate_metrics(self.metrics)
        _validate_non_negative(self.duration_ms, "duration_ms")
        if self.state == "completed":
            if self.primary_metric_value is None:
                raise ValueError(
                    "completed result requires primary_metric_value"
                )
            if self.error_code is not None:
                raise ValueError("completed result requires no error_code")
            if self.error_summary is not None:
                raise ValueError("completed result requires no error_summary")
            if self.predictions_path is None:
                raise ValueError("completed result requires predictions_path")
            if self.model_path is None:
                raise ValueError("completed result requires model_path")
            if self.model_fingerprint is None:
                raise ValueError("completed result requires model_fingerprint")
            _validate_primary_metric(
                self.primary_metric_name,
                self.primary_metric_value,
                self.metrics,
            )
        else:
            if self.primary_metric_value is not None:
                raise ValueError(
                    "non-completed result requires primary_metric_value to be None"
                )
            _validate_non_empty(self.error_code, "error_code")
            _validate_non_empty(self.error_summary, "error_summary")
            if self.predictions_path is not None:
                raise ValueError(
                    "non-completed result requires predictions_path to be None"
                )
            if self.model_path is not None:
                raise ValueError(
                    "non-completed result requires model_path to be None"
                )
            if self.model_fingerprint is not None:
                raise ValueError(
                    "non-completed result requires model_fingerprint to be None"
                )
            if self.metrics:
                raise ValueError("non-completed result requires metrics to be empty")
        object.__setattr__(
            self,
            "metrics",
            MappingProxyType(dict(self.metrics)),
        )

    def to_dict(self) -> dict[str, Any]:
        return _to_jsonable(self)


@dataclass(frozen=True)
class TrainingInstanceSnapshot:
    asset_id: str
    asset_path: str
    run_id: str
    round_number: int
    state: str
    reproducible_evidence: bool
    dataset_content_fingerprint: str
    dataset_version_fingerprint: str
    code_fingerprint: str
    configuration_fingerprint: str
    environment_fingerprint: str
    split_fingerprint: str
    plan_fingerprint: str
    approval_fingerprint: str
    random_seed: int
    parent_instance_id: str | None
    parent_instance_fingerprint: str | None
    optimization_direction: str
    primary_metric_name: str
    primary_metric_value: float | None
    metrics: dict[str, float]
    predictions_path: str | None
    predictions_fingerprint: str | None
    model_fingerprint: str | None
    model_retention_reasons: tuple[str, ...]
    model_path: str | None
    error_code: str | None
    error_summary: str | None
    started_at: str
    ended_at: str
    duration_ms: int
    sop_source_eligible: bool = field(init=False)

    def __post_init__(self) -> None:
        _validate_state(self.state, _TERMINAL_TRAINING_STATES, "state")
        _validate_positive(self.round_number, "round_number")
        _validate_optional_metric(
            self.primary_metric_value,
            "primary_metric_value",
        )
        _validate_metrics(self.metrics)
        _validate_non_negative(self.duration_ms, "duration_ms")
        _validate_parent_fingerprint(
            self.parent_instance_id,
            self.parent_instance_fingerprint,
        )
        if self.state == "completed":
            if not self.reproducible_evidence:
                raise ValueError(
                    "completed instance requires reproducible_evidence true"
                )
            if self.primary_metric_value is None:
                raise ValueError(
                    "completed instance requires primary_metric_value"
                )
            if self.error_code is not None:
                raise ValueError("completed instance requires no error_code")
            if self.error_summary is not None:
                raise ValueError("completed instance requires no error_summary")
            _validate_completed_instance_evidence(self)
            _validate_primary_metric(
                self.primary_metric_name,
                self.primary_metric_value,
                self.metrics,
            )
        else:
            if self.reproducible_evidence:
                raise ValueError(
                    "non-completed instance requires reproducible_evidence false"
                )
            if self.primary_metric_value is not None:
                raise ValueError(
                    "non-completed instance requires primary_metric_value to be None"
                )
            _validate_non_empty(self.error_code, "error_code")
            _validate_non_empty(self.error_summary, "error_summary")
        object.__setattr__(
            self,
            "metrics",
            MappingProxyType(dict(self.metrics)),
        )
        object.__setattr__(
            self,
            "sop_source_eligible",
            self.state == "completed"
            and self.reproducible_evidence
            and _has_complete_instance_evidence(self),
        )

    def to_dict(self) -> dict[str, Any]:
        return _to_jsonable(self)


@dataclass(frozen=True)
class RunPerformancePoint:
    round_number: int
    instance_id: str
    primary_metric_value: float

    def __post_init__(self) -> None:
        _validate_positive(self.round_number, "round_number")
        _validate_metric(self.primary_metric_value, "primary_metric_value")

    def to_dict(self) -> dict[str, Any]:
        return _to_jsonable(self)


@dataclass(frozen=True)
class RunRoundSnapshot:
    round_number: int
    instance_id: str
    hypothesis: str
    optimization_direction: str
    parent_instance_id: str | None
    instance_state: str
    duration_ms: int
    primary_metric_value: float | None
    model_retention_reasons: tuple[str, ...]
    error_code: str | None
    error_summary: str | None

    def __post_init__(self) -> None:
        _validate_positive(self.round_number, "round_number")
        _validate_state(
            self.instance_state,
            _TERMINAL_TRAINING_STATES,
            "instance_state",
        )
        _validate_non_negative(self.duration_ms, "duration_ms")
        _validate_optional_metric(
            self.primary_metric_value,
            "primary_metric_value",
        )
        if self.instance_state == "completed" and self.primary_metric_value is None:
            raise ValueError("completed round requires primary_metric_value")
        if self.instance_state != "completed" and self.primary_metric_value is not None:
            raise ValueError(
                "non-completed round requires primary_metric_value to be None"
            )

    def to_dict(self) -> dict[str, Any]:
        return _to_jsonable(self)


@dataclass(frozen=True)
class RunStatusSnapshot:
    run_id: str
    plan_id: str
    approval_id: str
    dataset_id: str
    dataset_version: int
    user_direction: str
    stop_conditions: tuple[str, ...]
    primary_metric_name: str
    target_metric_value: float
    state: str
    current_round: int
    rounds: tuple[RunRoundSnapshot, ...]
    performance_points: tuple[RunPerformancePoint, ...]
    best_instance_id: str | None
    best_primary_metric_value: float | None
    target_gap: float | None
    started_at: str
    ended_at: str | None
    elapsed_ms: int
    updated_at: str
    stop_reason: str | None
    stop_requested: bool
    recovery_reason: str | None
    recovery_actions: tuple[str, ...]

    def __post_init__(self) -> None:
        _validate_state(self.state, _RUN_STATES, "state")
        _validate_non_negative(self.current_round, "current_round")
        _validate_metric(self.target_metric_value, "target_metric_value")
        _validate_optional_metric(
            self.best_primary_metric_value,
            "best_primary_metric_value",
        )
        _validate_optional_metric(self.target_gap, "target_gap")
        _validate_non_negative(self.elapsed_ms, "elapsed_ms")
        if self.state == "recovery_required":
            _validate_non_empty(self.recovery_reason, "recovery_reason")
            if self.recovery_actions != ("resume", "close"):
                raise ValueError(
                    "recovery_actions must be exactly ('resume', 'close')"
                )
        elif self.recovery_reason is not None or self.recovery_actions:
            raise ValueError(
                "recovery_reason and recovery_actions require recovery_required state"
            )

    def to_dict(self) -> dict[str, Any]:
        return _to_jsonable(self)


@dataclass(frozen=True)
class WorkspaceSnapshot:
    repository_id: str
    schema_version: int
    repository_path: Path
    actor_id: str
    managed_paths: tuple[str, ...]
    index_path: Path
    indexed_assets: int
    git_state: str
    remote: RemoteStatus
    capacity: CapacityStatus
    ready: bool
    issues: tuple[WorkspaceIssue, ...]

    def to_dict(self) -> dict[str, Any]:
        return _to_jsonable(self)


class WorkspaceError(RuntimeError):
    def __init__(self, code: str, message: str, next_action: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.next_action = next_action

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
            "next_action": self.next_action,
        }


_TERMINAL_TRAINING_STATES = frozenset(
    {"completed", "failed", "timed_out", "stopped"}
)
_RUN_STATES = frozenset(
    {
        "created",
        "running",
        "completed",
        "failed",
        "timed_out",
        "stopped",
        "recovery_required",
    }
)
_RUN_RECOVERY_ACTIONS = frozenset({"resume", "close"})
_COMPLETED_INSTANCE_EVIDENCE_FIELDS = (
    "dataset_content_fingerprint",
    "dataset_version_fingerprint",
    "code_fingerprint",
    "configuration_fingerprint",
    "environment_fingerprint",
    "split_fingerprint",
    "plan_fingerprint",
    "approval_fingerprint",
    "predictions_path",
    "predictions_fingerprint",
    "model_fingerprint",
)


def _validate_state(value: str, allowed: frozenset[str], field_name: str) -> None:
    if value not in allowed:
        raise ValueError(f"{field_name} must be one of {sorted(allowed)}")


def _validate_metric(value: float, field_name: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not 0 <= value <= 1
    ):
        raise ValueError(f"{field_name} must be a finite number in [0, 1]")


def _validate_optional_metric(value: float | None, field_name: str) -> None:
    if value is not None:
        _validate_metric(value, field_name)


def _validate_metrics(metrics: Mapping[str, float]) -> None:
    for name, value in metrics.items():
        _validate_metric(value, f"metrics.{name}")


def _validate_primary_metric(
    primary_metric_name: str,
    primary_metric_value: float,
    metrics: Mapping[str, float],
) -> None:
    _validate_non_empty(primary_metric_name, "primary_metric_name")
    if primary_metric_name not in metrics:
        raise ValueError("metrics must contain primary_metric_name")
    if float(metrics[primary_metric_name]) != float(primary_metric_value):
        raise ValueError(
            "metrics primary value must equal primary_metric_value"
        )


def _validate_non_empty(value: str | None, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _validate_parent_fingerprint(
    parent_instance_id: str | None,
    parent_instance_fingerprint: str | None,
) -> None:
    if parent_instance_id is not None:
        _validate_non_empty(parent_instance_id, "parent_instance_id")
    if parent_instance_fingerprint is not None:
        _validate_non_empty(
            parent_instance_fingerprint,
            "parent_instance_fingerprint",
        )
    if (parent_instance_id is None) != (parent_instance_fingerprint is None):
        raise ValueError(
            "parent_instance_fingerprint is required exactly when "
            "parent_instance_id is present"
        )


def _validate_completed_instance_evidence(
    snapshot: TrainingInstanceSnapshot,
) -> None:
    for field_name in _COMPLETED_INSTANCE_EVIDENCE_FIELDS:
        _validate_non_empty(getattr(snapshot, field_name), field_name)


def _has_complete_instance_evidence(
    snapshot: TrainingInstanceSnapshot,
) -> bool:
    return all(
        isinstance(getattr(snapshot, field_name), str)
        and bool(getattr(snapshot, field_name).strip())
        for field_name in _COMPLETED_INSTANCE_EVIDENCE_FIELDS
    ) and snapshot.primary_metric_value is not None


def _validate_non_negative(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")


def _validate_positive(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field_name} must be a positive integer")


def _to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {
            field.name: _to_jsonable(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, Mapping):
        return {key: _to_jsonable(item) for key, item in value.items()}
    return value

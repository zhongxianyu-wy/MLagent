from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from pathlib import Path
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
    if isinstance(value, dict):
        return {key: _to_jsonable(item) for key, item in value.items()}
    return value

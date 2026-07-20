from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field, fields, is_dataclass
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True)
class WorkspaceIssue:
    code: str
    message: str
    next_action: str

    def to_dict(self) -> dict[str, Any]:
        return _to_jsonable(self)


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
    experience_applicability: dict[str, str] = field(default_factory=dict)
    experience_citations: tuple[ExperienceCitation, ...] = ()
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
    experience_applicability: dict[str, str] = field(default_factory=dict)
    experience_citations: tuple[ExperienceCitation, ...] = ()
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
    approval_fingerprint: str
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
class SopEvidenceReference:
    role: str
    asset_id: str
    asset_path: str
    sha256: str

    def __post_init__(self) -> None:
        _validate_state(self.role, _SOP_EVIDENCE_ROLES, "role")
        _validate_safe_id(self.asset_id, "asset_id")
        _validate_safe_asset_path(self.asset_path, "asset_path")
        _validate_sha256(self.sha256, "sha256")

    def to_dict(self) -> dict[str, Any]:
        return _to_jsonable(self)


@dataclass(frozen=True)
class CreateSopCandidateCommand:
    connection_path: Path
    sop_id: str
    name: str
    source_run_id: str
    source_instance_id: str
    strategy_summary: str
    optimization_background: str
    steps: tuple[str, ...]
    change_summary: str

    def __post_init__(self) -> None:
        _validate_safe_id(self.sop_id, "sop_id")
        _validate_non_empty(self.name, "name")
        _validate_safe_id(self.source_run_id, "source_run_id")
        _validate_safe_id(self.source_instance_id, "source_instance_id")
        _validate_non_empty(self.strategy_summary, "strategy_summary")
        _validate_non_empty(
            self.optimization_background,
            "optimization_background",
        )
        _validate_steps(self.steps)
        if not isinstance(self.change_summary, str):
            raise ValueError("change_summary must be a string")

    def to_dict(self) -> dict[str, Any]:
        return _to_jsonable(self)


@dataclass(frozen=True)
class ReproduceSopCandidateCommand:
    connection_path: Path
    candidate_id: str
    expected_candidate_fingerprint: str

    def __post_init__(self) -> None:
        _validate_safe_id(self.candidate_id, "candidate_id")
        _validate_sha256(
            self.expected_candidate_fingerprint,
            "expected_candidate_fingerprint",
        )

    def to_dict(self) -> dict[str, Any]:
        return _to_jsonable(self)


@dataclass(frozen=True)
class ReviewSopCandidateCommand:
    connection_path: Path
    candidate_id: str
    expected_candidate_fingerprint: str
    expected_gate_fingerprint: str
    expected_reviewer_policy_fingerprint: str
    decision: str

    def __post_init__(self) -> None:
        _validate_safe_id(self.candidate_id, "candidate_id")
        _validate_sha256(
            self.expected_candidate_fingerprint,
            "expected_candidate_fingerprint",
        )
        _validate_sha256(
            self.expected_gate_fingerprint,
            "expected_gate_fingerprint",
        )
        _validate_sha256(
            self.expected_reviewer_policy_fingerprint,
            "expected_reviewer_policy_fingerprint",
        )
        _validate_state(self.decision, _SOP_REVIEW_DECISIONS, "decision")

    def to_dict(self) -> dict[str, Any]:
        return _to_jsonable(self)


@dataclass(frozen=True)
class NotebookOriginInfo:
    """Provenance link showing a SOP candidate originated from a notebook import."""
    notebook_import_id: str
    original_filename: str
    content_fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return _to_jsonable(self)


@dataclass(frozen=True)
class SopCandidateSnapshot:
    asset_id: str
    asset_path: str
    sop_id: str
    name: str
    source_run_id: str
    source_instance_id: str
    candidate_fingerprint: str
    dataset_id: str
    dataset_version: int
    dataset_content_fingerprint: str
    dataset_version_fingerprint: str
    code_fingerprint: str
    configuration_fingerprint: str
    environment_fingerprint: str
    split_fingerprint: str
    random_seed: int
    primary_metric_name: str
    source_metric_value: float
    source_model_fingerprint: str
    strategy_summary: str
    optimization_background: str
    steps: tuple[str, ...]
    change_summary: str
    evidence: tuple[SopEvidenceReference, ...]
    created_at: str
    created_by: str
    notebook_origin: NotebookOriginInfo | None = None
    asset_type: str = "sop_candidate"

    def __post_init__(self) -> None:
        for field_name in (
            "asset_id",
            "sop_id",
            "source_run_id",
            "source_instance_id",
            "dataset_id",
        ):
            _validate_safe_id(getattr(self, field_name), field_name)
        _validate_safe_asset_path(self.asset_path, "asset_path")
        _validate_non_empty(self.name, "name")
        _validate_positive(self.dataset_version, "dataset_version")
        for field_name in _SOP_CANDIDATE_FINGERPRINT_FIELDS:
            _validate_sha256(getattr(self, field_name), field_name)
        if isinstance(self.random_seed, bool) or not isinstance(
            self.random_seed,
            int,
        ):
            raise ValueError("random_seed must be an integer")
        _validate_non_empty(self.primary_metric_name, "primary_metric_name")
        _validate_metric(self.source_metric_value, "source_metric_value")
        _validate_non_empty(self.strategy_summary, "strategy_summary")
        _validate_non_empty(
            self.optimization_background,
            "optimization_background",
        )
        _validate_steps(self.steps)
        if not isinstance(self.change_summary, str):
            raise ValueError("change_summary must be a string")
        roles = tuple(item.role for item in self.evidence)
        if len(roles) != len(set(roles)) or set(roles) != set(
            _SOP_EVIDENCE_ROLES
        ):
            raise ValueError(
                "evidence roles must contain every SOP source role exactly once"
            )
        _validate_non_empty(self.created_at, "created_at")
        _validate_non_empty(self.created_by, "created_by")
        if self.asset_type != "sop_candidate":
            raise ValueError("asset_type must be sop_candidate")

    def to_dict(self) -> dict[str, Any]:
        return _to_jsonable(self)


@dataclass(frozen=True)
class SopReproductionGateSnapshot:
    asset_id: str
    asset_path: str
    candidate_id: str
    candidate_fingerprint: str
    gate_fingerprint: str
    outcome: str
    source_run_id: str
    source_instance_id: str
    reproduction_run_id: str
    reproduction_instance_id: str
    source_metric_value: float
    reproduction_metric_value: float | None
    source_metric_six_decimals: str
    reproduction_metric_six_decimals: str | None
    created_at: str
    created_by: str
    asset_type: str = "sop_reproduction_gate"

    def __post_init__(self) -> None:
        for field_name in (
            "asset_id",
            "candidate_id",
            "source_run_id",
            "source_instance_id",
            "reproduction_run_id",
            "reproduction_instance_id",
        ):
            _validate_safe_id(getattr(self, field_name), field_name)
        _validate_safe_asset_path(self.asset_path, "asset_path")
        _validate_sha256(
            self.candidate_fingerprint,
            "candidate_fingerprint",
        )
        _validate_sha256(self.gate_fingerprint, "gate_fingerprint")
        _validate_state(self.outcome, _SOP_GATE_OUTCOMES, "outcome")
        if self.reproduction_run_id == self.source_run_id:
            raise ValueError("reproduction_run_id must differ from source_run_id")
        if self.reproduction_instance_id == self.source_instance_id:
            raise ValueError(
                "reproduction_instance_id must differ from source_instance_id"
            )
        _validate_metric(self.source_metric_value, "source_metric_value")
        _validate_metric_text(
            self.source_metric_value,
            self.source_metric_six_decimals,
            "source_metric_six_decimals",
        )
        _validate_optional_metric(
            self.reproduction_metric_value,
            "reproduction_metric_value",
        )
        if self.outcome == "execution_failed":
            if self.reproduction_metric_value is not None:
                raise ValueError(
                    "execution_failed requires reproduction_metric_value to be None"
                )
            if self.reproduction_metric_six_decimals is not None:
                raise ValueError(
                    "execution_failed requires reproduction_metric_six_decimals "
                    "to be None"
                )
        elif self.reproduction_metric_value is None:
            raise ValueError(f"{self.outcome} requires reproduction_metric_value")
        elif self.reproduction_metric_six_decimals is None:
            raise ValueError(
                f"{self.outcome} requires reproduction_metric_six_decimals"
            )
        else:
            _validate_metric_text(
                self.reproduction_metric_value,
                self.reproduction_metric_six_decimals,
                "reproduction_metric_six_decimals",
            )
        if self.outcome == "passed" and (
            self.source_metric_six_decimals
            != self.reproduction_metric_six_decimals
        ):
            raise ValueError("passed gate requires equal six-decimal metrics")
        if self.outcome == "metric_mismatch" and (
            self.source_metric_six_decimals
            == self.reproduction_metric_six_decimals
        ):
            raise ValueError("metric_mismatch requires unequal six-decimal metrics")
        _validate_non_empty(self.created_at, "created_at")
        _validate_non_empty(self.created_by, "created_by")
        if self.asset_type != "sop_reproduction_gate":
            raise ValueError("asset_type must be sop_reproduction_gate")

    def to_dict(self) -> dict[str, Any]:
        return _to_jsonable(self)


@dataclass(frozen=True)
class SopVersionSnapshot:
    asset_id: str
    asset_path: str
    sop_id: str
    version: int
    version_fingerprint: str
    previous_version_id: str | None
    previous_version_fingerprint: str | None
    candidate_id: str
    gate_id: str
    gate_fingerprint: str
    source_run_id: str
    source_instance_id: str
    reproduction_run_id: str
    reproduction_instance_id: str
    dataset_id: str
    dataset_version: int
    primary_metric_name: str
    primary_metric_value: float
    source_metric_value: float
    reproduction_metric_value: float
    environment: dict[str, Any]
    strategy_summary: str
    optimization_background: str
    steps: tuple[str, ...]
    change_summary: str
    approval_id: str
    formal_model_id: str
    created_at: str
    created_by: str
    asset_type: str = "sop_version"

    def __post_init__(self) -> None:
        for field_name in (
            "asset_id",
            "sop_id",
            "candidate_id",
            "gate_id",
            "source_run_id",
            "source_instance_id",
            "reproduction_run_id",
            "reproduction_instance_id",
            "dataset_id",
            "approval_id",
            "formal_model_id",
        ):
            _validate_safe_id(getattr(self, field_name), field_name)
        _validate_safe_asset_path(self.asset_path, "asset_path")
        _validate_positive(self.version, "version")
        _validate_positive(self.dataset_version, "dataset_version")
        _validate_sha256(self.version_fingerprint, "version_fingerprint")
        _validate_sha256(self.gate_fingerprint, "gate_fingerprint")
        if self.version == 1:
            if self.previous_version_id is not None:
                raise ValueError("version 1 cannot have previous_version_id")
            if self.previous_version_fingerprint is not None:
                raise ValueError(
                    "version 1 cannot have previous_version_fingerprint"
                )
        else:
            _validate_safe_id(
                self.previous_version_id,
                "previous_version_id",
            )
            _validate_sha256(
                self.previous_version_fingerprint,
                "previous_version_fingerprint",
            )
            _validate_non_empty(self.change_summary, "change_summary")
        if self.source_run_id == self.reproduction_run_id:
            raise ValueError("reproduction_run_id must differ from source_run_id")
        if self.source_instance_id == self.reproduction_instance_id:
            raise ValueError(
                "reproduction_instance_id must differ from source_instance_id"
            )
        _validate_non_empty(self.primary_metric_name, "primary_metric_name")
        _validate_metric(self.primary_metric_value, "primary_metric_value")
        _validate_metric(self.source_metric_value, "source_metric_value")
        _validate_metric(
            self.reproduction_metric_value,
            "reproduction_metric_value",
        )
        if (
            not isinstance(self.environment, dict)
            or not self.environment
            or any(not isinstance(key, str) or not key for key in self.environment)
        ):
            raise ValueError("environment must be a non-empty JSON object")
        object.__setattr__(
            self,
            "environment",
            MappingProxyType(dict(self.environment)),
        )
        _validate_non_empty(self.strategy_summary, "strategy_summary")
        _validate_non_empty(
            self.optimization_background,
            "optimization_background",
        )
        _validate_steps(self.steps)
        if not isinstance(self.change_summary, str):
            raise ValueError("change_summary must be a string")
        _validate_non_empty(self.created_at, "created_at")
        _validate_non_empty(self.created_by, "created_by")
        if self.asset_type != "sop_version":
            raise ValueError("asset_type must be sop_version")

    def to_dict(self) -> dict[str, Any]:
        return _to_jsonable(self)


@dataclass(frozen=True)
class FormalModelSnapshot:
    asset_id: str
    asset_path: str
    model_path: str
    model_fingerprint: str
    sop_version_id: str
    source_instance_id: str
    reproduction_instance_id: str
    dataset_id: str
    dataset_version: int
    primary_metric_name: str
    primary_metric_value: float
    strategy_summary: str
    optimization_background: str
    approval_id: str
    created_at: str
    created_by: str
    asset_type: str = "formal_model"

    def __post_init__(self) -> None:
        for field_name in (
            "asset_id",
            "sop_version_id",
            "source_instance_id",
            "reproduction_instance_id",
            "dataset_id",
            "approval_id",
        ):
            _validate_safe_id(getattr(self, field_name), field_name)
        _validate_safe_asset_path(self.asset_path, "asset_path")
        _validate_safe_asset_path(self.model_path, "model_path")
        _validate_sha256(self.model_fingerprint, "model_fingerprint")
        if self.source_instance_id == self.reproduction_instance_id:
            raise ValueError(
                "reproduction_instance_id must differ from source_instance_id"
            )
        _validate_positive(self.dataset_version, "dataset_version")
        _validate_non_empty(self.primary_metric_name, "primary_metric_name")
        _validate_metric(self.primary_metric_value, "primary_metric_value")
        _validate_non_empty(self.strategy_summary, "strategy_summary")
        _validate_non_empty(
            self.optimization_background,
            "optimization_background",
        )
        _validate_non_empty(self.created_at, "created_at")
        _validate_non_empty(self.created_by, "created_by")
        if self.asset_type != "formal_model":
            raise ValueError("asset_type must be formal_model")

    def to_dict(self) -> dict[str, Any]:
        return _to_jsonable(self)


@dataclass(frozen=True)
class SopCandidateStatus:
    candidate: SopCandidateSnapshot
    gate: SopReproductionGateSnapshot | None
    state: str

    def __post_init__(self) -> None:
        _validate_state(self.state, _SOP_CANDIDATE_STATES, "state")
        if self.gate is not None and self.gate.candidate_id != self.candidate.asset_id:
            raise ValueError("gate must reference candidate")
        if self.state == "pending_reproduction" and self.gate is not None:
            raise ValueError("pending_reproduction requires gate to be None")
        if self.state != "pending_reproduction" and self.gate is None:
            raise ValueError(f"{self.state} requires gate")
        if self.state in {"pending_review", "approved", "rejected"} and (
            self.gate is not None and self.gate.outcome != "passed"
        ):
            raise ValueError(f"{self.state} requires a passed gate")
        if self.state == "reproduction_failed" and (
            self.gate is not None and self.gate.outcome == "passed"
        ):
            raise ValueError("reproduction_failed requires a failed gate")

    def to_dict(self) -> dict[str, Any]:
        return _to_jsonable(self)


@dataclass(frozen=True)
class SopReviewOutcome:
    decision: str
    candidate_id: str
    gate_id: str
    approval_id: str
    sop_version: SopVersionSnapshot | None
    formal_model: FormalModelSnapshot | None

    def __post_init__(self) -> None:
        _validate_state(self.decision, _SOP_REVIEW_DECISIONS, "decision")
        for field_name in ("candidate_id", "gate_id", "approval_id"):
            _validate_safe_id(getattr(self, field_name), field_name)
        formal_assets_present = (
            self.sop_version is not None,
            self.formal_model is not None,
        )
        if self.decision == "approve" and not all(formal_assets_present):
            raise ValueError("approve requires both formal assets")
        if self.decision == "reject" and any(formal_assets_present):
            raise ValueError("reject cannot contain formal assets")
        if (
            self.sop_version is not None
            and self.formal_model is not None
            and self.formal_model.sop_version_id != self.sop_version.asset_id
        ):
            raise ValueError("formal assets must reference the same SOP version")

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
class SessionStopSyncCommand:
    connection_path: Path
    session_id: str

    def __post_init__(self) -> None:
        _validate_non_empty(self.session_id, "session_id")


@dataclass(frozen=True)
class CompleteSessionCommand:
    connection_path: Path
    session_id: str

    def __post_init__(self) -> None:
        _validate_non_empty(self.session_id, "session_id")

    def to_dict(self) -> dict[str, Any]:
        return _to_jsonable(self)


@dataclass(frozen=True)
class ExperienceContent:
    conclusion: str
    applicability: str
    recommended_action: str
    failure_boundary: str
    risk: str
    confidence: float

    def __post_init__(self) -> None:
        for field_name in _EXPERIENCE_CONTENT_FIELDS:
            value = getattr(self, field_name)
            _validate_non_empty(value, field_name)
            if len(value) > _MAX_EXPERIENCE_TEXT_LENGTH:
                raise ValueError(
                    f"{field_name} must be at most "
                    f"{_MAX_EXPERIENCE_TEXT_LENGTH} characters"
                )
        _validate_metric(self.confidence, "confidence")

    def to_dict(self) -> dict[str, Any]:
        return _to_jsonable(self)


@dataclass(frozen=True)
class ExperienceEvidence:
    role: str
    asset_id: str
    asset_path: str
    sha256: str

    def __post_init__(self) -> None:
        _validate_state(self.role, _EXPERIENCE_EVIDENCE_ROLES, "role")
        _validate_non_empty(self.asset_id, "asset_id")
        _validate_non_empty(self.asset_path, "asset_path")
        relative = Path(self.asset_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("asset_path must be a safe relative path")
        if _SHA256_PATTERN.fullmatch(self.sha256) is None:
            raise ValueError("sha256 must be a lowercase SHA-256 digest")

    def to_dict(self) -> dict[str, Any]:
        return _to_jsonable(self)


@dataclass(frozen=True)
class ExperienceCitation:
    experience_id: str
    event_id: str
    state: str
    why_applicable: str

    def __post_init__(self) -> None:
        _validate_non_empty(self.experience_id, "experience_id")
        _validate_non_empty(self.event_id, "event_id")
        _validate_state(self.state, _ACTIVE_EXPERIENCE_STATES, "state")
        _validate_non_empty(self.why_applicable, "why_applicable")
        if len(self.why_applicable) > _MAX_EXPERIENCE_TEXT_LENGTH:
            raise ValueError(
                "why_applicable must be at most "
                f"{_MAX_EXPERIENCE_TEXT_LENGTH} characters"
            )

    def to_dict(self) -> dict[str, Any]:
        return _to_jsonable(self)


@dataclass(frozen=True)
class ExperienceSnapshot:
    asset_id: str
    asset_path: str
    event_id: str
    event_fingerprint: str
    previous_event_id: str | None
    previous_event_fingerprint: str | None
    state: str
    content: ExperienceContent
    evidence: tuple[ExperienceEvidence, ...]
    extraction_session_id: str
    source_kind: str
    relation_type: str | None
    related_experience_id: str | None
    created_at: str
    created_by: str
    reviewed_at: str | None
    reviewed_by: str | None
    decision: str | None
    asset_type: str = "experience_event"

    def __post_init__(self) -> None:
        _validate_non_empty(self.asset_id, "asset_id")
        _validate_non_empty(self.asset_path, "asset_path")
        _validate_non_empty(self.event_id, "event_id")
        if _SHA256_PATTERN.fullmatch(self.event_fingerprint) is None:
            raise ValueError(
                "event_fingerprint must be a lowercase SHA-256 digest"
            )
        _validate_state(self.state, _EXPERIENCE_STATES, "state")
        _validate_non_empty(
            self.extraction_session_id,
            "extraction_session_id",
        )
        _validate_state(self.source_kind, _EXPERIENCE_SOURCE_KINDS, "source_kind")
        _validate_non_empty(self.created_at, "created_at")
        _validate_non_empty(self.created_by, "created_by")
        roles = tuple(item.role for item in self.evidence)
        if len(roles) != len(set(roles)) or set(roles) != set(
            _EXPERIENCE_EVIDENCE_ROLES
        ):
            raise ValueError(
                "evidence roles must contain dataset, run, "
                "training_instance, and raw_record exactly once"
            )
        if self.state == "pending":
            if self.previous_event_id is not None:
                raise ValueError("pending state cannot have previous_event_id")
            if self.previous_event_fingerprint is not None:
                raise ValueError(
                    "pending state cannot have previous_event_fingerprint"
                )
            if any(
                value is not None
                for value in (
                    self.reviewed_at,
                    self.reviewed_by,
                    self.decision,
                    self.relation_type,
                    self.related_experience_id,
                )
            ):
                raise ValueError("pending state cannot contain review or relation fields")
        else:
            _validate_non_empty(self.previous_event_id, "previous_event_id")
            if (
                self.previous_event_fingerprint is None
                or _SHA256_PATTERN.fullmatch(
                    self.previous_event_fingerprint
                )
                is None
            ):
                raise ValueError(
                    "previous_event_fingerprint must be a lowercase "
                    "SHA-256 digest"
                )
            _validate_non_empty(self.reviewed_at, "reviewed_at")
            _validate_non_empty(self.reviewed_by, "reviewed_by")
            _validate_non_empty(self.decision, "decision")
            expected_decision = _EXPERIENCE_STATE_DECISIONS[self.state]
            if self.decision != expected_decision:
                raise ValueError(
                    f"{self.state} state requires decision {expected_decision}"
                )
        relation_required = self.state in {"conflict", "superseded"}
        if (self.relation_type is None) != (self.related_experience_id is None):
            raise ValueError("relation type and related Experience ID must be paired")
        if relation_required:
            expected_relation = _EXPERIENCE_STATE_RELATIONS[self.state]
            if self.relation_type != expected_relation:
                raise ValueError(
                    f"{self.state} state requires relation {expected_relation}"
                )
            _validate_non_empty(
                self.related_experience_id,
                "related_experience_id",
            )
            if self.related_experience_id == self.asset_id:
                raise ValueError("relation must reference another Experience")
        elif self.relation_type is not None:
            raise ValueError(f"{self.state} state cannot contain a relation")

    def to_dict(self) -> dict[str, Any]:
        return _to_jsonable(self)


@dataclass(frozen=True)
class ExperienceSearchResult:
    experience: ExperienceSnapshot
    why_applicable: str
    score: int

    def __post_init__(self) -> None:
        if self.experience.state not in _ACTIVE_EXPERIENCE_STATES:
            raise ValueError("search result requires active Experience state")
        _validate_non_empty(self.why_applicable, "why_applicable")
        _validate_non_negative(self.score, "score")

    def to_dict(self) -> dict[str, Any]:
        return _to_jsonable(self)


@dataclass(frozen=True)
class ReviewExperienceCommand:
    connection_path: Path
    experience_id: str
    decision: str
    content: ExperienceContent
    related_experience_id: str | None = None

    def __post_init__(self) -> None:
        _validate_non_empty(self.experience_id, "experience_id")
        _validate_state(self.decision, _EXPERIENCE_REVIEW_DECISIONS, "decision")
        relation_required = self.decision in {"conflict", "supersede"}
        if relation_required:
            _validate_non_empty(
                self.related_experience_id,
                "related_experience_id",
            )
            if self.related_experience_id == self.experience_id:
                raise ValueError("related_experience_id must be different")
        elif self.related_experience_id is not None:
            raise ValueError(
                "related_experience_id requires conflict or supersede decision"
            )

    def to_dict(self) -> dict[str, Any]:
        return _to_jsonable(self)


@dataclass(frozen=True)
class SessionExperienceOutcome:
    session_id: str
    outcome: str
    candidate_ids: tuple[str, ...]
    new_event_ids: tuple[str, ...]
    new_instance_ids: tuple[str, ...]
    pending_review_count: int
    sync: SyncStatusSnapshot | None

    def __post_init__(self) -> None:
        _validate_non_empty(self.session_id, "session_id")
        _validate_state(
            self.outcome,
            _SESSION_EXPERIENCE_OUTCOMES,
            "outcome",
        )
        _validate_non_negative(
            self.pending_review_count,
            "pending_review_count",
        )
        for field_name in (
            "candidate_ids",
            "new_event_ids",
            "new_instance_ids",
        ):
            values = getattr(self, field_name)
            if len(values) != len(set(values)) or any(
                not isinstance(value, str) or not value.strip()
                for value in values
            ):
                raise ValueError(f"{field_name} must contain unique non-empty IDs")
        if self.outcome == "created" and not self.candidate_ids:
            raise ValueError("created outcome requires candidate_ids")
        if self.outcome != "created" and self.candidate_ids:
            raise ValueError("candidate_ids require created outcome")

    def to_dict(self) -> dict[str, Any]:
        return _to_jsonable(self)


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
    experience_citations: tuple[ExperienceCitation, ...] = ()
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
        if len(self.experience_citations) != len(
            {item.experience_id for item in self.experience_citations}
        ):
            raise ValueError(
                "experience_citations must contain unique Experience IDs"
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
            expected_actions = (
                ("close",)
                if self.recovery_reason == "legacy_run"
                else ("resume", "close")
            )
            if self.recovery_actions != expected_actions:
                raise ValueError(
                    "recovery_actions do not match the recovery reason"
                )
        elif self.recovery_reason is not None or self.recovery_actions:
            raise ValueError(
                "recovery_reason and recovery_actions require recovery_required state"
            )

    def to_dict(self) -> dict[str, Any]:
        return _to_jsonable(self)


@dataclass(frozen=True)
class SyncStatusSnapshot:
    state: str
    branch: str | None
    local_head: str | None
    remote_head: str | None
    ahead_count: int
    behind_count: int
    changed_managed_paths: tuple[str, ...]
    conflict_paths: tuple[str, ...]
    last_attempt_at: str | None
    last_success_at: str | None
    sync_commit: str | None
    message: str
    next_action: str | None

    def __post_init__(self) -> None:
        _validate_state(self.state, _SYNC_STATES, "state")
        _validate_non_negative(self.ahead_count, "ahead_count")
        _validate_non_negative(self.behind_count, "behind_count")
        _validate_non_empty(self.message, "message")
        if self.state == "conflict":
            if not self.conflict_paths:
                raise ValueError("conflict requires conflict_paths")
            _validate_non_empty(self.next_action, "next_action")
        elif self.conflict_paths:
            raise ValueError("conflict_paths require conflict state")

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
    sync: SyncStatusSnapshot
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
_SYNC_STATES = frozenset(
    {
        "not_configured",
        "synced",
        "syncing",
        "pending_sync",
        "conflict",
    }
)
_EXPERIENCE_STATES = frozenset(
    {"pending", "trusted", "rejected", "conflict", "superseded"}
)
_ACTIVE_EXPERIENCE_STATES = frozenset({"pending", "trusted"})
_EXPERIENCE_EVIDENCE_ROLES = frozenset(
    {"dataset", "run", "training_instance", "raw_record"}
)
_EXPERIENCE_SOURCE_KINDS = frozenset(
    {"metric_improvement", "training_failure"}
)
_EXPERIENCE_REVIEW_DECISIONS = frozenset(
    {"approve", "reject", "conflict", "supersede"}
)
_EXPERIENCE_STATE_DECISIONS = {
    "trusted": "approve",
    "rejected": "reject",
    "conflict": "conflict",
    "superseded": "supersede",
}
_EXPERIENCE_STATE_RELATIONS = {
    "conflict": "conflicts_with",
    "superseded": "superseded_by",
}
_SESSION_EXPERIENCE_OUTCOMES = frozenset(
    {"started", "created", "no_op", "already_completed"}
)
_SOP_EVIDENCE_ROLES = frozenset(
    {
        "dataset",
        "run",
        "training_instance",
        "input",
        "environment",
        "split",
        "code_revision",
        "metrics",
        "predictions",
        "source_model",
    }
)
_SOP_GATE_OUTCOMES = frozenset(
    {"passed", "execution_failed", "metric_mismatch", "evidence_mismatch"}
)
_SOP_REVIEW_DECISIONS = frozenset({"approve", "reject"})
_SOP_CANDIDATE_STATES = frozenset(
    {
        "pending_reproduction",
        "pending_review",
        "reproduction_failed",
        "approved",
        "rejected",
    }
)
_EXPERIENCE_CONTENT_FIELDS = (
    "conclusion",
    "applicability",
    "recommended_action",
    "failure_boundary",
    "risk",
)
_MAX_EXPERIENCE_TEXT_LENGTH = 4000
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SOP_CANDIDATE_FINGERPRINT_FIELDS = (
    "candidate_fingerprint",
    "dataset_content_fingerprint",
    "dataset_version_fingerprint",
    "code_fingerprint",
    "configuration_fingerprint",
    "environment_fingerprint",
    "split_fingerprint",
    "source_model_fingerprint",
)
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


def _validate_safe_id(value: str | None, field_name: str) -> None:
    _validate_non_empty(value, field_name)
    if _SAFE_ID_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a safe stable ID")


def _validate_safe_asset_path(value: str, field_name: str) -> None:
    _validate_non_empty(value, field_name)
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or path == Path("."):
        raise ValueError(f"{field_name} must be a safe relative path")


def _validate_sha256(value: str | None, field_name: str) -> None:
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")


def _validate_steps(steps: tuple[str, ...]) -> None:
    if not isinstance(steps, tuple) or not steps:
        raise ValueError("steps must be a non-empty tuple")
    for step in steps:
        _validate_non_empty(step, "steps")


def _validate_metric_text(
    value: float,
    text: str,
    field_name: str,
) -> None:
    expected = format(
        Decimal(str(value)).quantize(
            Decimal("0.000001"),
            rounding=ROUND_HALF_UP,
        ),
        ".6f",
    )
    if text != expected:
        raise ValueError(f"{field_name} must equal the six-decimal metric")


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


# ── Issue #9: Notebook import models ──────────────────────────────────


@dataclass(frozen=True)
class NotebookCellInfo:
    """One cell from the parsed notebook."""
    index: int
    cell_type: str  # code | markdown
    source_lines: int
    has_outputs: bool


@dataclass(frozen=True)
class NotebookParseWarning:
    """A potential issue found during notebook parsing."""
    kind: str  # missing_dependency | hidden_path | non_portable_path | implicit_state | unclear_randomness | interactive_step
    detail: str
    blocking: bool


@dataclass(frozen=True)
class NotebookParseReport:
    """Structured analysis of a notebook's training logic."""
    cells: tuple[NotebookCellInfo, ...]
    detected_dependencies: tuple[str, ...]
    detected_data_paths: tuple[str, ...]
    detected_randomness: tuple[str, ...]
    detected_split: str | None
    detected_metrics: tuple[str, ...]
    detected_model: str | None
    warnings: tuple[NotebookParseWarning, ...]
    content_fingerprint: str


@dataclass(frozen=True)
class ImportNotebookCommand:
    """Command to import, parse and reproduce a notebook."""
    connection_path: Path
    notebook_path: Path
    source_description: str
    dataset_id: str
    dataset_version: str
    code_root: Path


@dataclass(frozen=True)
class ReproduceNotebookCommand:
    """Command to execute a preserved notebook into a Training Instance."""
    connection_path: Path
    asset_id: str           # the notebook import asset to reproduce
    code_root: Path         # where to write the extracted .py entrypoint
    entrypoint_name: str = "notebook_reproduce.py"
    random_seed: int = 42   # injected if notebook lacks explicit seed


@dataclass(frozen=True)
class NotebookImportSnapshot:
    """Result of a notebook import — may be reproduced, blocked, or failed."""
    asset_id: str
    asset_path: str
    original_path: str
    content_fingerprint: str
    importer: str
    imported_at: str
    source_description: str
    parse_report: NotebookParseReport
    state: str  # preserved | parse_blocked | execution_failed | reproduced
    training_instance_id: str | None = None
    training_run_id: str | None = None
    error_code: str | None = None
    error_summary: str | None = None


_NOTEBOOK_IMPORT_STATES = frozenset(
    {"preserved", "parse_blocked", "execution_failed", "reproduced"}
)
_NOTEBOOK_PARSE_WARNING_KINDS = frozenset(
    {
        "missing_dependency",
        "hidden_path",
        "non_portable_path",
        "implicit_state",
        "unclear_randomness",
        "interactive_step",
    }
)

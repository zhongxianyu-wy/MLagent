from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DatasetManifest:
    dataset_id: str
    source_paths: list[str]
    sample_id_col: str
    label_col: str
    positive_label: str
    negative_label: str
    train_feature_path: str
    train_label_path: str
    test_feature_path: str | None
    test_label_path: str | None
    split_strategy: str
    split_ratio: float | None
    random_seed: int | None
    notes: str


@dataclass(frozen=True)
class RunControlPolicy:
    target_metric_name: str
    target_metric_value: float | None
    max_iterations: int
    max_runtime_minutes: int
    patience_rounds: int
    min_delta: float
    user_stoppable: bool


@dataclass(frozen=True)
class EvaluationConfig:
    metric: str
    k_folds: int
    target_specificity: float | None
    threshold_policy: str
    use_test_if_available: bool


@dataclass(frozen=True)
class ExperimentRun:
    experiment_id: str
    mode: str
    dataset_id: str | None
    status: str
    run_control_policy_id: str | None
    started_at: int
    ended_at: int | None
    stop_reason: str | None


@dataclass(frozen=True)
class ExperimentRoundTrace:
    round_id: str
    experiment_id: str
    round_num: int
    mode: str
    exploration_direction: str
    hypothesis: str | None
    preprocessing_strategy: str
    feature_subset_strategy: str
    selected_features_json: str
    model_type: str
    params_json: str
    cv_metrics_json: str
    threshold_policy: str
    selected_threshold: float | None
    test_metrics_json: str | None
    guidance_metric_name: str
    guidance_metric_value: float | None
    status: str
    stop_reason: str | None
    error_msg: str | None
    llm_rationale_summary: str
    created_at: int


@dataclass(frozen=True)
class MemoryEntry:
    memory_id: str
    source: str
    text: str
    linked_experiment_id: str | None
    linked_round_id: str | None
    linked_skill_id: str | None
    confidence: str
    needs_review: bool
    created_at: int


@dataclass(frozen=True)
class SkillCandidate:
    candidate_id: str
    source_type: str
    source_ref: str
    skill_name: str
    draft_path: str
    validation_status: str
    darwin_iteration_status: str
    review_status: str
    approved_skill_id: str | None
    created_at: int
    updated_at: int


@dataclass(frozen=True)
class ApprovedSkill:
    skill_id: str
    name: str
    path: str
    description: str
    applicability: str
    version: str
    created_from_candidate_id: str | None
    last_used_at: int | None


@dataclass(frozen=True)
class ResearchArtifact:
    artifact_id: str
    research_job_id: str
    source_url: str
    source_type: str
    method_summary: str
    feature_engineering_notes: str
    model_notes: str
    evaluation_notes: str
    reference_code_notes: str
    limitations: str
    created_at: int


@dataclass(frozen=True)
class LLMProviderConfig:
    provider_name: str
    base_url: str
    api_key_env: str
    model: str
    small_model: str | None
    max_tokens: int
    timeout_sec: int
    api_protocol: str = "anthropic-messages"


@dataclass(frozen=True)
class SafetyDecision:
    allowed: bool
    reason: str
    blocked_pattern: str | None
    requires_user_approval: bool


@dataclass(frozen=True)
class TrackingRecord:
    tracking_id: str
    round_id: str
    experiment_id: str
    mlflow_run_id: str | None
    artifact_paths: list[str]
    logged_at: int
    status: str
    error_msg: str | None


@dataclass(frozen=True)
class ConversationSession:
    session_id: str
    active_experiment_id: str | None
    active_dataset_id: str | None
    pending_question: str | None
    last_slash_command: str | None
    last_user_text: str | None
    history_json: str
    created_at: int
    updated_at: int


@dataclass(frozen=True)
class ConversationTurn:
    turn_id: str
    session_id: str
    raw_user_text: str
    runtime_mode: str
    parsed_command: str | None
    natural_language_tail: str
    streaming: bool
    tool_calls_allowed: bool
    linked_experiment_id: str | None
    created_at: int

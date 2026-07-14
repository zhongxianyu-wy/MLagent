# Data Model: NGS ML Experiment Agent

## DatasetManifest

Represents standardized input data.

Fields:

- `dataset_id: str`
- `source_paths: list[str]`
- `sample_id_col: str`
- `label_col: str`
- `positive_label: str`
- `negative_label: str`
- `train_feature_path: str`
- `train_label_path: str`
- `test_feature_path: str | None`
- `test_label_path: str | None`
- `split_strategy: existing | random_split | train_only`
- `split_ratio: float | None`
- `random_seed: int | None`
- `notes: str`

Validation:

- Train features and train labels must share sample IDs.
- Binary label mapping must be explicit.
- Test metrics can be guidance only when test labels exist.

## RunControlPolicy

Controls all run termination.

Fields:

- `target_metric_name: auc | accuracy | sensitivity_at_specificity`
- `target_metric_value: float | None`
- `max_iterations: int`
- `max_runtime_minutes: int`
- `patience_rounds: int`
- `min_delta: float`
- `user_stoppable: bool`

## EvaluationConfig

Defines k-fold and threshold rules.

Fields:

- `metric: auc | accuracy | sensitivity_at_specificity`
- `k_folds: int`
- `target_specificity: float | None`
- `threshold_policy: youden | target_specificity`
- `use_test_if_available: bool`

Validation:

- `k_folds` cannot exceed the minority class count without confirmation.
- `target_specificity` is required when threshold policy is `target_specificity`.

## ExperimentRun

Top-level run.

Fields:

- `experiment_id: str`
- `mode: data_standardization | exploration | reproduction | interactive_validation | skill_distillation | research_ingestion`
- `dataset_id: str | None`
- `status: created | running | paused | completed | failed | stopped`
- `run_control_policy_id: str | None`
- `started_at: int`
- `ended_at: int | None`
- `stop_reason: str | None`

## ExperimentRoundTrace

Per-round trace for frontend and Skill distillation.

Fields:

- `round_id: str`
- `experiment_id: str`
- `round_num: int`
- `mode: str`
- `exploration_direction: str`
- `hypothesis: str | None`
- `preprocessing_strategy: str`
- `feature_subset_strategy: str`
- `selected_features_json: str`
- `model_type: str`
- `params_json: str`
- `cv_metrics_json: str`
- `threshold_policy: str`
- `selected_threshold: float | None`
- `test_metrics_json: str | None`
- `guidance_metric_name: str`
- `guidance_metric_value: float | None`
- `status: completed | failed | timeout | stopped`
- `stop_reason: str | None`
- `error_msg: str | None`
- `llm_rationale_summary: str`
- `created_at: int`

## MemoryEntry

Semantic experience or knowledge.

Fields:

- `memory_id: str`
- `source: agent | notebook | paper | project | research`
- `text: str`
- `linked_experiment_id: str | None`
- `linked_round_id: str | None`
- `linked_skill_id: str | None`
- `confidence: low | medium | high`
- `needs_review: bool`
- `created_at: int`

## SkillCandidate

Draft executable knowledge.

States:

`draft → validated → optimized → pending_review → approved | rejected`

Fields:

- `candidate_id: str`
- `source_type: notebook | best_run | memory`
- `source_ref: str`
- `skill_name: str`
- `draft_path: str`
- `validation_status: pending | passed | failed`
- `darwin_iteration_status: not_started | improved | reverted | failed`
- `review_status: pending | approved | rejected`
- `approved_skill_id: str | None`

## ApprovedSkill

Published reusable Skill.

Fields:

- `skill_id: str`
- `name: str`
- `path: str`
- `description: str`
- `applicability: str`
- `version: str`
- `created_from_candidate_id: str | None`
- `last_used_at: int | None`

## ResearchArtifact

Structured literature/project finding.

Fields:

- `artifact_id: str`
- `research_job_id: str`
- `source_url: str`
- `source_type: paper | project | article`
- `method_summary: str`
- `feature_engineering_notes: str`
- `model_notes: str`
- `evaluation_notes: str`
- `reference_code_notes: str`
- `limitations: str`
- `created_at: int`

## LLMProviderConfig

Anthropic-compatible provider settings.

Fields:

- `provider_name: str`
- `base_url: str`
- `api_key_env: str`
- `model: str`
- `small_model: str | None`
- `max_tokens: int`
- `timeout_sec: int`

## ConversationSession

Interactive LLM shell state.

Fields:

- `session_id: str`
- `active_experiment_id: str | None`
- `active_dataset_id: str | None`
- `pending_question: str | None`
- `last_slash_command: str | None`
- `last_user_text: str | None`
- `history_json: str`
- `created_at: int`
- `updated_at: int`

## ConversationTurn

A single interactive shell turn.

Fields:

- `turn_id: str`
- `session_id: str`
- `raw_user_text: str`
- `runtime_mode: ask | plan | agent`
- `parsed_command: str | None`
- `natural_language_tail: str`
- `streaming: bool`
- `tool_calls_allowed: bool`
- `linked_experiment_id: str | None`
- `created_at: int`

## ValidationPlan

Plan-mode artifact produced before execution.

Fields:

- `plan_id: str`
- `session_id: str`
- `dataset_ref: str | None`
- `objective: str`
- `metric: str`
- `k_folds: int | None`
- `threshold_policy: str | None`
- `target_specificity: float | None`
- `proposed_directions_json: str`
- `run_control_policy_json: str`
- `open_questions_json: str`
- `status: draft | ready | superseded`
- `created_at: int`
- `updated_at: int`

## SlashCommand

Command registry item for the interactive shell.

Fields:

- `name: str`
- `aliases: list[str]`
- `mode: str`
- `description: str`
- `requires_llm_routing: bool`

## FunctionalHarness

Configured mapping from slash command aliases to domain actions.

Fields:

- `harness_id: str`
- `commands: list[str]`
- `domain_action: str`
- `required_inputs_json: str`
- `allow_plan_promotion: bool`
- `source: seed_config | user_config | migration`
- `description: str`

Validation:

- Commands and aliases must be unique across active harnesses.
- Domain action must map to a known service method or harness adapter.
- Prompt-only intent classification cannot create or modify harness mappings.

## ModeCapabilityPolicy

Deterministic guard for runtime mode permissions.

Fields:

- `mode: ask | plan | agent`
- `allowed_service_methods: list[str]`
- `allowed_mutations: list[str]`
- `allow_file_writes: bool`
- `allow_training_execution: bool`
- `allow_skill_mutation: bool`

Validation:

- Ask mode allows conversation-history writes only.
- Plan mode allows memory reads and validation-plan writes only.
- Agent mode still requires safety hooks before local commands or file writes.

## ExplorationTool

Bounded candidate tool used by the exploration harness.

Fields:

- `tool_id: str`
- `tool_type: aide_tree_search | memory_guided_search | manual_validation_plan | skill_seeded_search`
- `input_schema_json: str`
- `timeout_sec: int`
- `fallback_rank: int`
- `status: available | unavailable | disabled`

Validation:

- Tool outputs must include a trace payload and failure reason when not successful.
- AIDE-backed tools cannot mutate conversation, memory, frontend, or safety state directly.

## DreamJob

Idle-time memory maintenance record.

Fields:

- `dream_job_id: str`
- `started_at: int`
- `ended_at: int | None`
- `status: pending | running | completed | failed`
- `memory_scope_json: str`
- `deduplicated_count: int`
- `summaries_created: int`
- `needs_review_count: int`
- `report_path: str | None`
- `lease_id: str | None`

## IdleSchedulerLease

Exclusive background-job lease for a workspace.

Fields:

- `lease_id: str`
- `lease_type: dream`
- `owner_id: str`
- `acquired_at: int`
- `heartbeat_at: int`
- `expires_at: int`
- `status: active | released | expired`

Validation:

- Only one active lease per `lease_type` may exist at a time.
- Expired leases may be superseded but not silently deleted.

## SkillOptimizationJob

Controlled `/skill_opt` run.

Fields:

- `skill_opt_job_id: str`
- `skill_id: str`
- `dataset_id: str | None`
- `dataset_approval_status: pending | approved | rejected`
- `backup_path: str`
- `candidate_path: str | None`
- `old_version_metrics_json: str | None`
- `candidate_version_metrics_json: str | None`
- `speed_comparison_json: str | None`
- `consistency_comparison_json: str | None`
- `performance_comparison_json: str | None`
- `repeat_count: int`
- `max_runtime_minutes: int`
- `selection_metric: str`
- `leakage_policy: train_cv_only_for_selection`
- `stop_reason: str | None`
- `review_status: pending | approved | rejected`
- `created_at: int`
- `updated_at: int`

Validation:

- Candidate selection must use training k-fold metrics only.
- Test metrics may be added to the report after selection but cannot choose the winner.

## SafetyDecision

Result of local command or file-write validation.

Fields:

- `allowed: bool`
- `reason: str`
- `blocked_pattern: str | None`
- `requires_user_approval: bool`

## TrackingRecord

Local MLflow/logging bridge entry.

Fields:

- `tracking_id: str`
- `round_id: str`
- `experiment_id: str`
- `mlflow_run_id: str | None`
- `artifact_paths: list[str]`
- `logged_at: int`
- `status: pending | logged | failed`
- `error_msg: str | None`

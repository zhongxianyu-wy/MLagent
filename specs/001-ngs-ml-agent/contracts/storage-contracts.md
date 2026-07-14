# Storage Contracts

## SQLite Tables

### `dataset_manifests`

Stores `DatasetManifest` fields. `dataset_id` is primary key.

Required columns:

- `dataset_id`
- `source_paths_json`
- `sample_id_col`
- `label_col`
- `positive_label`
- `negative_label`
- `train_feature_path`
- `train_label_path`
- `test_feature_path`
- `test_label_path`
- `split_strategy`
- `split_ratio`
- `random_seed`
- `notes`
- `created_at`

### `experiment_runs`

Stores run-level state.

Required columns:

- `experiment_id`
- `mode`
- `dataset_id`
- `status`
- `run_control_policy_json`
- `started_at`
- `ended_at`
- `stop_reason`

### `conversation_sessions`

Stores interactive LLM shell state.

Required columns:

- `session_id`
- `active_experiment_id`
- `active_dataset_id`
- `pending_question`
- `last_slash_command`
- `last_user_text`
- `history_json`
- `created_at`
- `updated_at`

### `conversation_turns`

Stores ask/plan/agent shell turns.

Required columns:

- `turn_id`
- `session_id`
- `raw_user_text`
- `runtime_mode`
- `parsed_command`
- `natural_language_tail`
- `streaming`
- `tool_calls_allowed`
- `linked_experiment_id`
- `created_at`

### `validation_plans`

Stores plan-mode validation plans.

Required columns:

- `plan_id`
- `session_id`
- `dataset_ref`
- `objective`
- `metric`
- `k_folds`
- `threshold_policy`
- `target_specificity`
- `proposed_directions_json`
- `run_control_policy_json`
- `open_questions_json`
- `status`
- `created_at`
- `updated_at`

### `functional_harnesses`

Stores explicit command-to-function mappings.

Required columns:

- `harness_id`
- `commands_json`
- `domain_action`
- `required_inputs_json`
- `allow_plan_promotion`
- `source`
- `description`

### `mode_capability_policies`

Stores deterministic runtime-mode permissions.

Required columns:

- `mode`
- `allowed_service_methods_json`
- `allowed_mutations_json`
- `allow_file_writes`
- `allow_training_execution`
- `allow_skill_mutation`
- `updated_at`

### `exploration_tools`

Stores bounded exploration tool candidates, including AIDE-backed tools.

Required columns:

- `tool_id`
- `tool_type`
- `input_schema_json`
- `timeout_sec`
- `fallback_rank`
- `status`
- `updated_at`

### `dream_jobs`

Stores idle memory maintenance records.

Required columns:

- `dream_job_id`
- `started_at`
- `ended_at`
- `status`
- `memory_scope_json`
- `deduplicated_count`
- `summaries_created`
- `needs_review_count`
- `report_path`
- `lease_id`

### `idle_scheduler_leases`

Stores exclusive leases for idle/background jobs.

Required columns:

- `lease_id`
- `lease_type`
- `owner_id`
- `acquired_at`
- `heartbeat_at`
- `expires_at`
- `status`

### `skill_optimization_jobs`

Stores `/skill_opt` old/new comparison workflow.

Required columns:

- `skill_opt_job_id`
- `skill_id`
- `dataset_id`
- `dataset_approval_status`
- `backup_path`
- `candidate_path`
- `old_version_metrics_json`
- `candidate_version_metrics_json`
- `speed_comparison_json`
- `consistency_comparison_json`
- `performance_comparison_json`
- `repeat_count`
- `max_runtime_minutes`
- `selection_metric`
- `leakage_policy`
- `stop_reason`
- `review_status`
- `created_at`
- `updated_at`

### `experiment_rounds`

Stores frontend-visible round traces.

Required columns:

- `round_id`
- `experiment_id`
- `round_num`
- `mode`
- `exploration_direction`
- `hypothesis`
- `preprocessing_strategy`
- `feature_subset_strategy`
- `selected_features_json`
- `model_type`
- `params_json`
- `cv_metrics_json`
- `threshold_policy`
- `selected_threshold`
- `test_metrics_json`
- `guidance_metric_name`
- `guidance_metric_value`
- `status`
- `stop_reason`
- `error_msg`
- `llm_rationale_summary`
- `created_at`

### `memory_metadata`

Maps vector memory IDs to deterministic metadata.

Required columns:

- `memory_id`
- `chroma_id`
- `source`
- `linked_experiment_id`
- `linked_round_id`
- `linked_skill_id`
- `confidence`
- `needs_review`
- `created_at`

### `memory_texts`

Stores deterministic text mirrors for audit and Skill evidence reconstruction while the vector store remains responsible for semantic retrieval.

Required columns:

- `memory_id`
- `text`

### `memory_skill_links`

Stores evidence links from semantic memory entries to SkillCandidates.

Required columns:

- `memory_id`
- `candidate_id`

### `skill_candidates`

Tracks candidate lifecycle.

Required columns:

- `candidate_id`
- `source_type`
- `source_ref`
- `skill_name`
- `draft_path`
- `validation_status`
- `darwin_iteration_status`
- `review_status`
- `approved_skill_id`
- `created_at`
- `updated_at`

### `approved_skills`

Tracks published Skills and execution history.

Required columns:

- `skill_id`
- `name`
- `path`
- `description`
- `applicability`
- `version`
- `created_from_candidate_id`
- `last_used_at`

### `research_artifacts`

Stores structured research findings.

Required columns:

- `artifact_id`
- `research_job_id`
- `source_url`
- `source_type`
- `method_summary`
- `feature_engineering_notes`
- `model_notes`
- `evaluation_notes`
- `reference_code_notes`
- `limitations`
- `created_at`

### `tracking_records`

Stores local tracking writeback status.

Required columns:

- `tracking_id`
- `round_id`
- `experiment_id`
- `mlflow_run_id`
- `artifact_paths_json`
- `logged_at`
- `status`
- `error_msg`

## Filesystem

- `experiments/standardized/<dataset_id>/`: standardized train/test files and manifest JSON.
- `experiments/models/<experiment_id>/`: model artifacts and final reports.
- `experiments/outputs/<experiment_id>/`: logs, intermediate configs, and SkillCandidate drafts.
- `.claude/skills/<skill-name>/SKILL.md`: approved Skills only.
- `db/chroma/`: local semantic vector store.

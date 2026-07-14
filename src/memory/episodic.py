from __future__ import annotations

import sqlite3
from pathlib import Path

from src.models import ExperimentRoundTrace


class EpisodicMemory:
    def __init__(self, db_path: str = "db/experiments.db") -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS dataset_manifests (
                dataset_id TEXT PRIMARY KEY,
                source_paths_json TEXT NOT NULL,
                sample_id_col TEXT NOT NULL,
                label_col TEXT NOT NULL,
                positive_label TEXT NOT NULL,
                negative_label TEXT NOT NULL,
                train_feature_path TEXT NOT NULL,
                train_label_path TEXT NOT NULL,
                test_feature_path TEXT,
                test_label_path TEXT,
                split_strategy TEXT NOT NULL,
                split_ratio REAL,
                random_seed INTEGER,
                notes TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS experiment_runs (
                experiment_id TEXT PRIMARY KEY,
                mode TEXT NOT NULL,
                dataset_id TEXT,
                status TEXT NOT NULL,
                run_control_policy_json TEXT,
                started_at INTEGER NOT NULL,
                ended_at INTEGER,
                stop_reason TEXT
            );

            CREATE TABLE IF NOT EXISTS conversation_sessions (
                session_id TEXT PRIMARY KEY,
                active_experiment_id TEXT,
                active_dataset_id TEXT,
                pending_question TEXT,
                last_slash_command TEXT,
                last_user_text TEXT,
                history_json TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS conversation_turns (
                turn_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                raw_user_text TEXT NOT NULL,
                runtime_mode TEXT NOT NULL,
                parsed_command TEXT,
                natural_language_tail TEXT NOT NULL,
                streaming INTEGER NOT NULL,
                tool_calls_allowed INTEGER NOT NULL,
                linked_experiment_id TEXT,
                created_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS validation_plans (
                plan_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                dataset_ref TEXT,
                objective TEXT NOT NULL,
                metric TEXT NOT NULL,
                k_folds INTEGER,
                threshold_policy TEXT,
                target_specificity REAL,
                proposed_directions_json TEXT NOT NULL,
                run_control_policy_json TEXT NOT NULL,
                open_questions_json TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS functional_harnesses (
                harness_id TEXT PRIMARY KEY,
                commands_json TEXT NOT NULL,
                domain_action TEXT NOT NULL,
                required_inputs_json TEXT NOT NULL,
                allow_plan_promotion INTEGER NOT NULL,
                source TEXT NOT NULL,
                description TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS mode_capability_policies (
                mode TEXT PRIMARY KEY,
                allowed_service_methods_json TEXT NOT NULL,
                allowed_mutations_json TEXT NOT NULL,
                allow_file_writes INTEGER NOT NULL,
                allow_training_execution INTEGER NOT NULL,
                allow_skill_mutation INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS exploration_tools (
                tool_id TEXT PRIMARY KEY,
                tool_type TEXT NOT NULL,
                input_schema_json TEXT NOT NULL,
                timeout_sec INTEGER NOT NULL,
                fallback_rank INTEGER NOT NULL,
                status TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS dream_jobs (
                dream_job_id TEXT PRIMARY KEY,
                started_at INTEGER NOT NULL,
                ended_at INTEGER,
                status TEXT NOT NULL,
                memory_scope_json TEXT NOT NULL,
                deduplicated_count INTEGER NOT NULL,
                summaries_created INTEGER NOT NULL,
                needs_review_count INTEGER NOT NULL,
                report_path TEXT,
                lease_id TEXT
            );

            CREATE TABLE IF NOT EXISTS idle_scheduler_leases (
                lease_id TEXT PRIMARY KEY,
                lease_type TEXT NOT NULL,
                owner_id TEXT NOT NULL,
                acquired_at INTEGER NOT NULL,
                heartbeat_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                status TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS skill_optimization_jobs (
                skill_opt_job_id TEXT PRIMARY KEY,
                skill_id TEXT NOT NULL,
                dataset_id TEXT,
                dataset_approval_status TEXT NOT NULL,
                backup_path TEXT NOT NULL,
                candidate_path TEXT,
                old_version_metrics_json TEXT,
                candidate_version_metrics_json TEXT,
                speed_comparison_json TEXT,
                consistency_comparison_json TEXT,
                performance_comparison_json TEXT,
                repeat_count INTEGER NOT NULL,
                max_runtime_minutes INTEGER NOT NULL,
                selection_metric TEXT NOT NULL,
                leakage_policy TEXT NOT NULL,
                stop_reason TEXT,
                review_status TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS experiment_rounds (
                round_id TEXT PRIMARY KEY,
                experiment_id TEXT NOT NULL,
                round_num INTEGER NOT NULL,
                mode TEXT NOT NULL,
                exploration_direction TEXT,
                hypothesis TEXT,
                preprocessing_strategy TEXT,
                feature_subset_strategy TEXT,
                selected_features_json TEXT,
                model_type TEXT,
                params_json TEXT,
                cv_metrics_json TEXT,
                threshold_policy TEXT,
                selected_threshold REAL,
                test_metrics_json TEXT,
                guidance_metric_name TEXT,
                guidance_metric_value REAL,
                status TEXT NOT NULL,
                stop_reason TEXT,
                error_msg TEXT,
                llm_rationale_summary TEXT,
                created_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS memory_metadata (
                memory_id TEXT PRIMARY KEY,
                chroma_id TEXT NOT NULL,
                source TEXT NOT NULL,
                linked_experiment_id TEXT,
                linked_round_id TEXT,
                linked_skill_id TEXT,
                confidence TEXT NOT NULL,
                needs_review INTEGER NOT NULL,
                created_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS memory_texts (
                memory_id TEXT PRIMARY KEY,
                text TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS memory_skill_links (
                memory_id TEXT NOT NULL,
                candidate_id TEXT NOT NULL,
                PRIMARY KEY (memory_id, candidate_id)
            );

            CREATE TABLE IF NOT EXISTS skill_candidates (
                candidate_id TEXT PRIMARY KEY,
                source_type TEXT NOT NULL,
                source_ref TEXT NOT NULL,
                skill_name TEXT NOT NULL,
                draft_path TEXT NOT NULL,
                validation_status TEXT NOT NULL,
                darwin_iteration_status TEXT NOT NULL,
                review_status TEXT NOT NULL,
                approved_skill_id TEXT,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS approved_skills (
                skill_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                path TEXT NOT NULL,
                description TEXT NOT NULL,
                applicability TEXT NOT NULL,
                version TEXT NOT NULL,
                created_from_candidate_id TEXT,
                last_used_at INTEGER
            );

            CREATE TABLE IF NOT EXISTS research_artifacts (
                artifact_id TEXT PRIMARY KEY,
                research_job_id TEXT NOT NULL,
                source_url TEXT NOT NULL,
                source_type TEXT NOT NULL,
                method_summary TEXT NOT NULL,
                feature_engineering_notes TEXT NOT NULL,
                model_notes TEXT NOT NULL,
                evaluation_notes TEXT NOT NULL,
                reference_code_notes TEXT NOT NULL,
                limitations TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tracking_records (
                tracking_id TEXT PRIMARY KEY,
                round_id TEXT NOT NULL,
                experiment_id TEXT NOT NULL,
                mlflow_run_id TEXT,
                artifact_paths_json TEXT NOT NULL,
                logged_at INTEGER NOT NULL,
                status TEXT NOT NULL,
                error_msg TEXT
            );
            """
        )
        self._conn.commit()

    def add_round_trace(self, trace: ExperimentRoundTrace) -> None:
        self._conn.execute(
            """
            INSERT INTO experiment_rounds (
                round_id,
                experiment_id,
                round_num,
                mode,
                exploration_direction,
                hypothesis,
                preprocessing_strategy,
                feature_subset_strategy,
                selected_features_json,
                model_type,
                params_json,
                cv_metrics_json,
                threshold_policy,
                selected_threshold,
                test_metrics_json,
                guidance_metric_name,
                guidance_metric_value,
                status,
                stop_reason,
                error_msg,
                llm_rationale_summary,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trace.round_id,
                trace.experiment_id,
                trace.round_num,
                trace.mode,
                trace.exploration_direction,
                trace.hypothesis,
                trace.preprocessing_strategy,
                trace.feature_subset_strategy,
                trace.selected_features_json,
                trace.model_type,
                trace.params_json,
                trace.cv_metrics_json,
                trace.threshold_policy,
                trace.selected_threshold,
                trace.test_metrics_json,
                trace.guidance_metric_name,
                trace.guidance_metric_value,
                trace.status,
                trace.stop_reason,
                trace.error_msg,
                trace.llm_rationale_summary,
                trace.created_at,
            ),
        )
        self._conn.commit()

    def list_round_traces(self, experiment_id: str) -> list[ExperimentRoundTrace]:
        rows = self._conn.execute(
            """
            SELECT
                round_id,
                experiment_id,
                round_num,
                mode,
                exploration_direction,
                hypothesis,
                preprocessing_strategy,
                feature_subset_strategy,
                selected_features_json,
                model_type,
                params_json,
                cv_metrics_json,
                threshold_policy,
                selected_threshold,
                test_metrics_json,
                guidance_metric_name,
                guidance_metric_value,
                status,
                stop_reason,
                error_msg,
                llm_rationale_summary,
                created_at
            FROM experiment_rounds
            WHERE experiment_id = ?
            ORDER BY round_num ASC
            """,
            (experiment_id,),
        ).fetchall()
        return [ExperimentRoundTrace(*row) for row in rows]

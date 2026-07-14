import sqlite3

from src.memory.episodic import EpisodicMemory
from src.models import ExperimentRoundTrace


def table_columns(conn, table_name):
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row[1] for row in rows}


def test_sqlite_schema_initializes_contract_tables(tmp_path):
    db_path = tmp_path / "experiments.db"

    EpisodicMemory(str(db_path))

    conn = sqlite3.connect(db_path)
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }

    assert {
        "dataset_manifests",
        "experiment_runs",
        "experiment_rounds",
        "memory_metadata",
        "skill_candidates",
        "approved_skills",
        "research_artifacts",
            "tracking_records",
            "memory_texts",
            "memory_skill_links",
            "conversation_sessions",
            "conversation_turns",
            "validation_plans",
            "functional_harnesses",
            "mode_capability_policies",
            "exploration_tools",
            "dream_jobs",
            "idle_scheduler_leases",
            "skill_optimization_jobs",
        }.issubset(tables)


def test_experiment_rounds_schema_contains_frontend_trace_columns(tmp_path):
    db_path = tmp_path / "experiments.db"

    EpisodicMemory(str(db_path))

    conn = sqlite3.connect(db_path)
    columns = table_columns(conn, "experiment_rounds")

    assert {
        "round_id",
        "experiment_id",
        "round_num",
        "mode",
        "exploration_direction",
        "preprocessing_strategy",
        "feature_subset_strategy",
        "cv_metrics_json",
        "threshold_policy",
        "selected_threshold",
        "test_metrics_json",
        "guidance_metric_name",
        "guidance_metric_value",
        "status",
        "stop_reason",
        "llm_rationale_summary",
        "created_at",
    }.issubset(columns)


def test_round_trace_repository_writes_and_lists_frontend_rows(tmp_path):
    db_path = tmp_path / "experiments.db"
    memory = EpisodicMemory(str(db_path))
    trace = ExperimentRoundTrace(
        round_id="round-1",
        experiment_id="exp-1",
        round_num=1,
        mode="exploration",
        exploration_direction="variance filter then xgboost",
        hypothesis="low variance features add noise",
        preprocessing_strategy="standardize",
        feature_subset_strategy="variance_threshold",
        selected_features_json='["f1", "f2"]',
        model_type="xgboost",
        params_json='{"max_depth": 2}',
        cv_metrics_json='{"auc": 0.91}',
        threshold_policy="youden",
        selected_threshold=0.42,
        test_metrics_json=None,
        guidance_metric_name="auc",
        guidance_metric_value=0.91,
        status="completed",
        stop_reason=None,
        error_msg=None,
        llm_rationale_summary="first baseline",
        created_at=123,
    )

    memory.add_round_trace(trace)

    rows = memory.list_round_traces("exp-1")
    assert rows == [trace]
    assert memory.list_round_traces("other-exp") == []


def test_runtime_storage_tables_contain_required_columns(tmp_path):
    db_path = tmp_path / "experiments.db"

    EpisodicMemory(str(db_path))

    conn = sqlite3.connect(db_path)
    expected_columns = {
        "conversation_sessions": {
            "session_id",
            "active_experiment_id",
            "active_dataset_id",
            "pending_question",
            "last_slash_command",
            "last_user_text",
            "history_json",
            "created_at",
            "updated_at",
        },
        "conversation_turns": {
            "turn_id",
            "session_id",
            "raw_user_text",
            "runtime_mode",
            "parsed_command",
            "natural_language_tail",
            "streaming",
            "tool_calls_allowed",
            "linked_experiment_id",
            "created_at",
        },
        "validation_plans": {
            "plan_id",
            "session_id",
            "dataset_ref",
            "objective",
            "metric",
            "k_folds",
            "threshold_policy",
            "target_specificity",
            "proposed_directions_json",
            "run_control_policy_json",
            "open_questions_json",
            "status",
            "created_at",
            "updated_at",
        },
        "functional_harnesses": {
            "harness_id",
            "commands_json",
            "domain_action",
            "required_inputs_json",
            "allow_plan_promotion",
            "source",
            "description",
        },
        "mode_capability_policies": {
            "mode",
            "allowed_service_methods_json",
            "allowed_mutations_json",
            "allow_file_writes",
            "allow_training_execution",
            "allow_skill_mutation",
            "updated_at",
        },
        "exploration_tools": {
            "tool_id",
            "tool_type",
            "input_schema_json",
            "timeout_sec",
            "fallback_rank",
            "status",
            "updated_at",
        },
        "dream_jobs": {
            "dream_job_id",
            "started_at",
            "ended_at",
            "status",
            "memory_scope_json",
            "deduplicated_count",
            "summaries_created",
            "needs_review_count",
            "report_path",
            "lease_id",
        },
        "idle_scheduler_leases": {
            "lease_id",
            "lease_type",
            "owner_id",
            "acquired_at",
            "heartbeat_at",
            "expires_at",
            "status",
        },
        "skill_optimization_jobs": {
            "skill_opt_job_id",
            "skill_id",
            "dataset_id",
            "dataset_approval_status",
            "backup_path",
            "candidate_path",
            "old_version_metrics_json",
            "candidate_version_metrics_json",
            "speed_comparison_json",
            "consistency_comparison_json",
            "performance_comparison_json",
            "repeat_count",
            "max_runtime_minutes",
            "selection_metric",
            "leakage_policy",
            "stop_reason",
            "review_status",
            "created_at",
            "updated_at",
        },
        "memory_texts": {
            "memory_id",
            "text",
        },
        "memory_skill_links": {
            "memory_id",
            "candidate_id",
        },
    }

    for table_name, columns in expected_columns.items():
        assert columns.issubset(table_columns(conn, table_name))

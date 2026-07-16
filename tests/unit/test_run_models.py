from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from src.domain.models import (
    ExecuteExplorationCommand,
    RecoverRunCommand,
    RequestRunStopCommand,
    RunPerformancePoint,
    RunRoundSnapshot,
    RunStatusSnapshot,
    TrainingExecutionResult,
    TrainingInstanceSnapshot,
)


def test_execute_and_control_commands_keep_governed_references_explicit():
    execute = ExecuteExplorationCommand(
        connection_path=Path(".mlagent-workspace.json"),
        code_root=Path("code"),
        dataset_id="ds-1",
        dataset_version=1,
        plan_id="plan-1",
        approval_id="approval-1",
        entrypoint_path="train.py",
        human_marked_rounds=(2,),
    )
    stop = RequestRunStopCommand(
        connection_path=Path(".mlagent-workspace.json"),
        run_id="run-1",
    )
    recover = RecoverRunCommand(
        connection_path=Path(".mlagent-workspace.json"),
        run_id="run-1",
        action="resume",
    )

    assert execute.dataset_version == 1
    assert execute.plan_id == "plan-1"
    assert execute.human_marked_rounds == (2,)
    assert stop.reason == "user_stop"
    assert recover.action == "resume"
    with pytest.raises(FrozenInstanceError):
        execute.plan_id = "changed"


def test_recovery_action_is_explicit():
    with pytest.raises(ValueError, match="action"):
        RecoverRunCommand(Path("workspace.json"), "run-1", "retry")


def test_completed_instance_derives_sop_source_eligibility_and_serializes():
    snapshot = instance_snapshot()

    assert snapshot.sop_source_eligible is True
    assert snapshot.to_dict()["sop_source_eligible"] is True
    assert snapshot.to_dict()["dataset_version_fingerprint"] == "dataset-version-sha"


@pytest.mark.parametrize("state", ("failed", "timed_out", "stopped"))
def test_non_completed_instance_cannot_claim_success(state):
    snapshot = instance_snapshot(
        state=state,
        reproducible_evidence=False,
        primary_metric_value=None,
        metrics={},
        model_fingerprint=None,
        model_retention_reasons=(),
        model_path=None,
        error_code=f"worker_{state}",
        error_summary=f"Worker {state}",
    )

    assert snapshot.sop_source_eligible is False
    assert snapshot.primary_metric_value is None


@pytest.mark.parametrize(
    ("updates", "message"),
    (
        ({"reproducible_evidence": False}, "reproducible_evidence"),
        ({"primary_metric_value": None}, "primary_metric_value"),
        ({"error_code": "worker_failed"}, "error_code"),
    ),
)
def test_completed_instance_requires_complete_reproducible_evidence(updates, message):
    with pytest.raises(ValueError, match=message):
        instance_snapshot(**updates)


@pytest.mark.parametrize(
    "updates",
    (
        {"reproducible_evidence": True},
        {"primary_metric_value": 0.8},
    ),
)
def test_non_completed_instance_rejects_success_claims(updates):
    values = {
        "state": "failed",
        "reproducible_evidence": False,
        "primary_metric_value": None,
        "metrics": {},
        "model_fingerprint": None,
        "model_retention_reasons": (),
        "model_path": None,
        "error_code": "worker_failed",
        "error_summary": "Worker failed",
    }
    values.update(updates)

    with pytest.raises(ValueError):
        instance_snapshot(**values)


@pytest.mark.parametrize("value", (float("nan"), float("inf"), -0.01, 1.01))
def test_instance_metric_values_must_be_finite_unit_interval(value):
    with pytest.raises(ValueError, match="metrics.roc_auc"):
        instance_snapshot(metrics={"roc_auc": value})


def test_training_execution_result_is_terminal_json_safe_and_governed():
    result = execution_result()

    assert result.to_dict()["predictions_path"] == "outputs/predictions.csv"
    assert result.to_dict()["model_path"] == "outputs/model.joblib"
    with pytest.raises(ValueError, match="state"):
        replace(result, state="running")
    with pytest.raises(ValueError, match="primary_metric_value"):
        replace(
            result,
            state="failed",
            primary_metric_value=0.8,
            model_path=None,
            model_fingerprint=None,
            error_code="worker_failed",
        )


def test_run_status_serializes_rounds_performance_and_recovery_data():
    status = run_status_snapshot()

    payload = status.to_dict()
    assert payload["rounds"][0]["instance_state"] == "completed"
    assert payload["performance_points"][0]["primary_metric_value"] == 0.82
    assert payload["best_instance_id"] == "instance-1"
    assert payload["recovery_actions"] == []


@pytest.mark.parametrize("value", (float("nan"), float("inf"), -0.01, 1.01))
def test_target_compatible_performance_values_are_finite_unit_interval(value):
    with pytest.raises(ValueError, match="primary_metric_value"):
        RunPerformancePoint(
            round_number=2,
            instance_id="instance-2",
            primary_metric_value=value,
        )
    with pytest.raises(ValueError, match="target_metric_value"):
        replace(run_status_snapshot(), target_metric_value=value)


def test_run_and_round_states_use_explicit_names():
    with pytest.raises(ValueError, match="instance_state"):
        replace(run_status_snapshot().rounds[0], instance_state="success")
    with pytest.raises(ValueError, match="state"):
        replace(run_status_snapshot(), state="unknown")
    with pytest.raises(ValueError, match="state"):
        instance_snapshot(state="interrupted")


def instance_snapshot(**updates) -> TrainingInstanceSnapshot:
    values = {
        "asset_id": "instance-1",
        "asset_path": "runs/run-1/instances/instance-1/manifest.json",
        "run_id": "run-1",
        "round_number": 1,
        "state": "completed",
        "reproducible_evidence": True,
        "dataset_version_fingerprint": "dataset-version-sha",
        "code_fingerprint": "code-sha",
        "configuration_fingerprint": "config-sha",
        "environment_fingerprint": "environment-sha",
        "split_fingerprint": "split-sha",
        "random_seed": 42,
        "parent_instance_id": None,
        "optimization_direction": "baseline",
        "primary_metric_name": "roc_auc",
        "primary_metric_value": 0.82,
        "metrics": {"roc_auc": 0.82, "accuracy": 0.8},
        "model_fingerprint": "model-sha",
        "model_retention_reasons": ("baseline",),
        "model_path": "models/instance-1.joblib",
        "error_code": None,
        "error_summary": None,
        "started_at": "2026-07-16T01:00:00Z",
        "ended_at": "2026-07-16T01:00:02Z",
        "duration_ms": 2000,
    }
    values.update(updates)
    return TrainingInstanceSnapshot(**values)


def execution_result(**updates) -> TrainingExecutionResult:
    values = {
        "state": "completed",
        "primary_metric_name": "roc_auc",
        "primary_metric_value": 0.82,
        "metrics": {"roc_auc": 0.82, "accuracy": 0.8},
        "predictions_path": Path("outputs/predictions.csv"),
        "model_path": Path("outputs/model.joblib"),
        "model_fingerprint": "model-sha",
        "error_code": None,
        "error_summary": None,
        "started_at": "2026-07-16T01:00:00Z",
        "ended_at": "2026-07-16T01:00:02Z",
        "duration_ms": 2000,
    }
    values.update(updates)
    return TrainingExecutionResult(**values)


def run_status_snapshot(**updates) -> RunStatusSnapshot:
    values = {
        "run_id": "run-1",
        "plan_id": "plan-1",
        "approval_id": "approval-1",
        "dataset_id": "ds-1",
        "dataset_version": 1,
        "user_direction": "Improve validation AUC",
        "stop_conditions": ("target reached",),
        "primary_metric_name": "roc_auc",
        "target_metric_value": 0.9,
        "state": "completed",
        "current_round": 1,
        "rounds": (
            RunRoundSnapshot(
                round_number=1,
                instance_id="instance-1",
                hypothesis="Fit a baseline",
                optimization_direction="baseline",
                parent_instance_id=None,
                instance_state="completed",
                duration_ms=2000,
                primary_metric_value=0.82,
                model_retention_reasons=("baseline",),
                error_code=None,
                error_summary=None,
            ),
        ),
        "performance_points": (RunPerformancePoint(1, "instance-1", 0.82),),
        "best_instance_id": "instance-1",
        "best_primary_metric_value": 0.82,
        "target_gap": 0.08,
        "started_at": "2026-07-16T01:00:00Z",
        "ended_at": "2026-07-16T01:00:02Z",
        "elapsed_ms": 2000,
        "updated_at": "2026-07-16T01:00:02Z",
        "stop_reason": "plan_complete",
        "stop_requested": False,
        "recovery_reason": None,
        "recovery_actions": (),
    }
    values.update(updates)
    return RunStatusSnapshot(**values)

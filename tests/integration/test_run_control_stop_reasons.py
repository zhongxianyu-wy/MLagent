from src.agent.control_center import apply_run_control
from src.frontend_api.run_service import RunService
from src.models import RunControlPolicy


def test_run_control_records_target_metric_stop_reason():
    service = RunService(id_factory=lambda: "exp-1", clock=lambda: 100)
    service.start_run({"mode": "exploration", "dataset_id": "dataset-1"})

    status = apply_run_control(
        run_service=service,
        experiment_id="exp-1",
        policy=RunControlPolicy("auc", 0.8, 10, 60, 3, 0.01, True),
        completed_iterations=1,
        elapsed_minutes=1,
        best_metric_value=0.81,
        rounds_since_improvement=0,
        user_stop_requested=False,
    )

    assert status["status"] == "stopped"
    assert status["stop_reason"] == "target_metric_reached"


def test_run_control_records_max_runtime_and_patience_stop_reasons():
    service = RunService(id_factory=lambda: "exp-1", clock=lambda: 100)
    service.start_run({"mode": "exploration", "dataset_id": "dataset-1"})
    runtime = apply_run_control(
        service,
        "exp-1",
        RunControlPolicy("auc", None, 10, 5, 3, 0.01, True),
        completed_iterations=1,
        elapsed_minutes=5,
        best_metric_value=0.7,
        rounds_since_improvement=0,
        user_stop_requested=False,
    )

    service = RunService(id_factory=lambda: "exp-2", clock=lambda: 100)
    service.start_run({"mode": "exploration", "dataset_id": "dataset-1"})
    patience = apply_run_control(
        service,
        "exp-2",
        RunControlPolicy("auc", None, 10, 60, 2, 0.01, True),
        completed_iterations=3,
        elapsed_minutes=3,
        best_metric_value=0.7,
        rounds_since_improvement=2,
        user_stop_requested=False,
    )

    assert runtime["stop_reason"] == "max_runtime"
    assert patience["stop_reason"] == "patience"

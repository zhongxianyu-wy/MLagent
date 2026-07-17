import hashlib
from decimal import Decimal

import pytest

from src.domain.models import TrainingExecutionResult
from src.domain.run_repository import RunRepository
from src.domain.sop_promotion import (
    SopPromotionCoordinator,
    compare_reproduction_metric,
    metric_at_six_places,
)
from src.domain.sop_repository import SopRepository
from tests.integration.test_sop_repository import (
    build_sop_workspace,
    candidate_spec,
)


class DeterministicExecutor:
    def __init__(self, metric=0.82, state="completed"):
        self.metric = metric
        self.state = state
        self.calls = 0

    def execute(self, prepared, stop_requested, timeout_seconds):
        self.calls += 1
        if self.state != "completed":
            return TrainingExecutionResult(
                state=self.state,
                primary_metric_name="roc_auc",
                primary_metric_value=None,
                metrics={},
                predictions_path=None,
                model_path=None,
                model_fingerprint=None,
                error_code="reproduction_failed",
                error_summary="Independent reproduction failed",
                started_at="2026-07-17T00:20:00Z",
                ended_at="2026-07-17T00:21:00Z",
                duration_ms=60_000,
            )
        prepared.worker_output_path.mkdir(parents=True, exist_ok=True)
        predictions = prepared.worker_output_path / "predictions.csv"
        predictions.write_text(
            "sample_id,observed,predicted,probability_case\n"
            "s1,case,case,0.9\n",
            encoding="utf-8",
        )
        model = prepared.worker_output_path / "model.joblib"
        model.write_bytes(b"independent-reproduction-model")
        return TrainingExecutionResult(
            state="completed",
            primary_metric_name="roc_auc",
            primary_metric_value=self.metric,
            metrics={"roc_auc": self.metric, "accuracy": 0.8},
            predictions_path=predictions,
            model_path=model,
            model_fingerprint=hashlib.sha256(model.read_bytes()).hexdigest(),
            error_code=None,
            error_summary=None,
            started_at="2026-07-17T00:20:00Z",
            ended_at="2026-07-17T00:21:00Z",
            duration_ms=60_000,
        )


def test_reproduction_uses_distinct_exact_execution(tmp_path):
    workspace = build_sop_workspace(tmp_path)
    candidate_repository = SopRepository(
        workspace.root,
        candidate_id_factory=lambda: "candidate-1",
        gate_id_factory=lambda: "gate-1",
        clock=lambda: "2026-07-17T00:10:00Z",
    )
    candidate = candidate_repository.create_candidate(
        candidate_spec(workspace),
        actor_id="alice",
        capacity=workspace.capacity,
    )
    executor = DeterministicExecutor()
    coordinator, reproduction_repository = make_coordinator(
        workspace,
        candidate_repository,
        executor,
    )

    gate = coordinator.reproduce(candidate)
    reproduction = reproduction_repository.load_instance(
        gate.reproduction_run_id,
        gate.reproduction_instance_id,
    )
    source = workspace.run_repository.load_instance(
        candidate.source_run_id,
        candidate.source_instance_id,
    )

    assert gate.outcome == "passed"
    assert gate.reproduction_run_id != candidate.source_run_id
    assert gate.reproduction_instance_id != candidate.source_instance_id
    assert gate.source_metric_six_decimals == gate.reproduction_metric_six_decimals
    assert reproduction.parent_instance_id is None
    assert reproduction.model_retention_reasons == ("sop_reproduction",)
    assert reproduction.model_fingerprint != source.model_fingerprint
    assert reproduction.dataset_content_fingerprint == source.dataset_content_fingerprint
    assert reproduction.dataset_version_fingerprint == source.dataset_version_fingerprint
    assert reproduction.code_fingerprint == source.code_fingerprint
    assert reproduction.configuration_fingerprint == source.configuration_fingerprint
    assert reproduction.environment_fingerprint == source.environment_fingerprint
    assert reproduction.split_fingerprint == source.split_fingerprint
    assert reproduction.random_seed == source.random_seed
    assert reproduction.plan_fingerprint == source.plan_fingerprint
    assert reproduction.approval_fingerprint == source.approval_fingerprint


def test_reproduction_retry_returns_existing_gate_without_running_again(tmp_path):
    workspace = build_sop_workspace(tmp_path)
    repository = SopRepository(
        workspace.root,
        candidate_id_factory=lambda: "candidate-1",
        gate_id_factory=lambda: "gate-1",
        clock=lambda: "2026-07-17T00:10:00Z",
    )
    candidate = repository.create_candidate(
        candidate_spec(workspace),
        actor_id="alice",
        capacity=workspace.capacity,
    )
    executor = DeterministicExecutor()
    coordinator, _ = make_coordinator(workspace, repository, executor)

    first = coordinator.reproduce(candidate)
    repeated = coordinator.reproduce(candidate)

    assert repeated == first
    assert executor.calls == 1


def test_failed_reproduction_seals_failed_gate_and_no_retained_model(tmp_path):
    workspace = build_sop_workspace(tmp_path)
    repository = SopRepository(
        workspace.root,
        candidate_id_factory=lambda: "candidate-1",
        gate_id_factory=lambda: "gate-1",
        clock=lambda: "2026-07-17T00:10:00Z",
    )
    candidate = repository.create_candidate(
        candidate_spec(workspace),
        actor_id="alice",
        capacity=workspace.capacity,
    )
    coordinator, run_repository = make_coordinator(
        workspace,
        repository,
        DeterministicExecutor(state="failed"),
    )

    gate = coordinator.reproduce(candidate)
    reproduction = run_repository.load_instance(
        gate.reproduction_run_id,
        gate.reproduction_instance_id,
    )

    assert gate.outcome == "execution_failed"
    assert gate.reproduction_metric_value is None
    assert reproduction.state == "failed"
    assert reproduction.model_path is None
    assert reproduction.model_retention_reasons == ()


@pytest.mark.parametrize(
    ("source", "reproduced", "outcome"),
    (
        (0.81234551, 0.81234549, "metric_mismatch"),
        (0.81234551, 0.81234552, "passed"),
    ),
)
def test_gate_compares_round_half_up_at_six_places(source, reproduced, outcome):
    assert compare_reproduction_metric(source, reproduced) == outcome


def test_metric_text_is_exactly_six_decimal_places():
    assert metric_at_six_places(0.8) == "0.800000"
    assert Decimal(metric_at_six_places(0.8123455)) == Decimal("0.812346")


def make_coordinator(workspace, sop_repository, executor):
    event_ids = iter(f"reproduction-event-{index}" for index in range(1, 10))
    run_repository = RunRepository(
        workspace.root,
        event_id_factory=lambda: next(event_ids),
        instance_id_factory=lambda: "instance-reproduction",
        clock=lambda: "2026-07-17T00:20:00Z",
    )
    coordinator = SopPromotionCoordinator(
        sop_repository=sop_repository,
        run_repository=run_repository,
        executor=executor,
        capacity=workspace.capacity,
        actor_id="alice",
        reproduction_run_id_factory=lambda: "run-reproduction",
    )
    return coordinator, run_repository

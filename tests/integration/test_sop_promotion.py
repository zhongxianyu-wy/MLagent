import hashlib
from decimal import Decimal
from dataclasses import replace

import pytest

from src.domain.models import TrainingExecutionResult, WorkspaceError
from src.domain.run_repository import RunRepository
from src.domain.sop_promotion import (
    SopPromotionCoordinator,
    compare_reproduction_metric,
    metric_at_six_places,
)
from src.domain.sop_repository import (
    SopRepository,
    SopReviewSpec,
)
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


def test_authorized_approval_publishes_sop_and_reproduction_model(tmp_path):
    workspace = build_sop_workspace(tmp_path)
    repository = promotion_repository(workspace)
    candidate = repository.create_candidate(
        candidate_spec(workspace),
        actor_id="alice",
        capacity=workspace.capacity,
    )
    coordinator, run_repository = make_coordinator(
        workspace,
        repository,
        DeterministicExecutor(),
    )
    gate = coordinator.reproduce(candidate)

    outcome = repository.review_candidate(
        review_spec(candidate, gate),
        actor_id="alice",
        capacity=workspace.capacity,
    )
    repeated = repository.review_candidate(
        review_spec(candidate, gate),
        actor_id="alice",
        capacity=workspace.capacity,
    )

    reproduction = run_repository.load_instance(
        gate.reproduction_run_id,
        gate.reproduction_instance_id,
    )
    reproduction_model = (
        workspace.root
        / reproduction.asset_path
    ).parent / reproduction.model_path
    formal_model = workspace.root / outcome.formal_model.model_path
    assert outcome.sop_version.version == 1
    assert outcome.formal_model.sop_version_id == outcome.sop_version.asset_id
    assert formal_model.read_bytes() == reproduction_model.read_bytes()
    assert outcome.formal_model.model_fingerprint == hashlib.sha256(
        formal_model.read_bytes()
    ).hexdigest()
    assert repeated == outcome
    assert repository.list_sop_versions(candidate.sop_id) == (
        outcome.sop_version,
    )
    assert repository.get_formal_model(outcome.formal_model.asset_id) == (
        outcome.formal_model
    )


def test_unauthorized_approval_creates_no_formal_assets(tmp_path):
    workspace = build_sop_workspace(tmp_path)
    repository = promotion_repository(workspace)
    candidate = repository.create_candidate(
        candidate_spec(workspace),
        actor_id="alice",
        capacity=workspace.capacity,
    )
    gate = make_coordinator(
        workspace,
        repository,
        DeterministicExecutor(),
    )[0].reproduce(candidate)

    with pytest.raises(WorkspaceError) as caught:
        repository.review_candidate(
            review_spec(candidate, gate),
            actor_id="bob",
            capacity=workspace.capacity,
        )

    assert caught.value.code == "unauthorized_sop_reviewer"
    assert repository.list_sop_versions(candidate.sop_id) == ()
    assert not (workspace.root / "models/formal").exists()


def test_non_passing_gate_cannot_publish_formal_assets(tmp_path):
    workspace = build_sop_workspace(tmp_path)
    repository = promotion_repository(workspace)
    candidate = repository.create_candidate(
        candidate_spec(workspace),
        actor_id="alice",
        capacity=workspace.capacity,
    )
    gate = make_coordinator(
        workspace,
        repository,
        DeterministicExecutor(metric=0.7),
    )[0].reproduce(candidate)

    with pytest.raises(WorkspaceError) as caught:
        repository.review_candidate(
            review_spec(candidate, gate),
            actor_id="alice",
            capacity=workspace.capacity,
        )

    assert gate.outcome == "metric_mismatch"
    assert caught.value.code == "sop_gate_not_passed"
    assert repository.list_sop_versions(candidate.sop_id) == ()
    assert not (workspace.root / "models/formal").exists()


def test_second_approval_appends_version_without_changing_version_one(tmp_path):
    workspace = build_sop_workspace(tmp_path)
    candidate_ids = iter(("candidate-1", "candidate-2"))
    gate_ids = iter(("gate-1", "gate-2"))
    approval_ids = iter(("sop-approval-1", "sop-approval-2"))
    repository = SopRepository(
        workspace.root,
        candidate_id_factory=lambda: next(candidate_ids),
        gate_id_factory=lambda: next(gate_ids),
        approval_id_factory=lambda: next(approval_ids),
        clock=lambda: "2026-07-17T00:10:00Z",
    )
    first_candidate = repository.create_candidate(
        candidate_spec(workspace),
        actor_id="alice",
        capacity=workspace.capacity,
    )
    first_gate = make_coordinator(
        workspace,
        repository,
        DeterministicExecutor(),
        run_id="run-reproduction-1",
        instance_id="instance-reproduction-1",
    )[0].reproduce(first_candidate)
    first = repository.review_candidate(
        review_spec(first_candidate, first_gate),
        actor_id="alice",
        capacity=workspace.capacity,
    )
    first_bytes = (workspace.root / first.sop_version.asset_path).read_bytes()

    second_candidate = repository.create_candidate(
        replace(
            candidate_spec(workspace),
            strategy_summary="Fit and calibrate the reviewed baseline.",
            change_summary="Add probability calibration.",
        ),
        actor_id="alice",
        capacity=workspace.capacity,
    )
    second_gate = make_coordinator(
        workspace,
        repository,
        DeterministicExecutor(),
        run_id="run-reproduction-2",
        instance_id="instance-reproduction-2",
    )[0].reproduce(second_candidate)
    second = repository.review_candidate(
        review_spec(second_candidate, second_gate),
        actor_id="alice",
        capacity=workspace.capacity,
    )

    assert second.sop_version.version == 2
    assert second.sop_version.previous_version_id == first.sop_version.asset_id
    assert second.sop_version.previous_version_fingerprint == (
        first.sop_version.version_fingerprint
    )
    assert (workspace.root / first.sop_version.asset_path).read_bytes() == first_bytes
    assert repository.list_sop_versions(first_candidate.sop_id) == (
        first.sop_version,
        second.sop_version,
    )


def promotion_repository(workspace):
    return SopRepository(
        workspace.root,
        candidate_id_factory=lambda: "candidate-1",
        gate_id_factory=lambda: "gate-1",
        approval_id_factory=lambda: "sop-approval-1",
        clock=lambda: "2026-07-17T00:10:00Z",
    )


def review_spec(candidate, gate):
    return SopReviewSpec(
        candidate_id=candidate.asset_id,
        expected_candidate_fingerprint=candidate.candidate_fingerprint,
        expected_gate_fingerprint=gate.gate_fingerprint,
        decision="approve",
    )


def make_coordinator(
    workspace,
    sop_repository,
    executor,
    *,
    run_id="run-reproduction",
    instance_id="instance-reproduction",
):
    event_ids = iter(f"reproduction-event-{index}" for index in range(1, 10))
    run_repository = RunRepository(
        workspace.root,
        event_id_factory=lambda: next(event_ids),
        instance_id_factory=lambda: instance_id,
        clock=lambda: "2026-07-17T00:20:00Z",
    )
    coordinator = SopPromotionCoordinator(
        sop_repository=sop_repository,
        run_repository=run_repository,
        executor=executor,
        capacity=workspace.capacity,
        actor_id="alice",
        reproduction_run_id_factory=lambda: run_id,
    )
    return coordinator, run_repository

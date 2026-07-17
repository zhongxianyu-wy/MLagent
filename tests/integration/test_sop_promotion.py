import hashlib
import json
from decimal import Decimal
from dataclasses import replace

import pytest

from src.domain.memory_repository import (
    REVIEWER_POLICY_PATH,
    MemoryRepository,
)
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


def test_approval_retry_resumes_an_interrupted_publication(tmp_path, monkeypatch):
    workspace = build_sop_workspace(tmp_path)
    approval_ids = iter(("sop-approval-first", "sop-approval-second"))
    repository = SopRepository(
        workspace.root,
        candidate_id_factory=lambda: "candidate-1",
        gate_id_factory=lambda: "gate-1",
        approval_id_factory=lambda: next(approval_ids),
        clock=lambda: "2026-07-17T00:10:00Z",
    )
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
    original_publish = repository._publish_exact_file
    publish_calls = 0

    def interrupt_before_approval(target, raw):
        nonlocal publish_calls
        publish_calls += 1
        if publish_calls == 4:
            raise WorkspaceError(
                code="sop_publication_failed",
                message="simulated interruption",
                next_action="retry",
            )
        original_publish(target, raw)

    monkeypatch.setattr(
        repository,
        "_publish_exact_file",
        interrupt_before_approval,
    )
    with pytest.raises(WorkspaceError) as caught:
        repository.review_candidate(
            review_spec(candidate, gate),
            actor_id="alice",
            capacity=workspace.capacity,
        )
    assert caught.value.code == "sop_publication_failed"
    assert repository.list_sop_versions(candidate.sop_id) == ()
    with pytest.raises(WorkspaceError):
        repository.get_formal_model("model-sop-random-forest-v0001")

    monkeypatch.setattr(repository, "_publish_exact_file", original_publish)
    outcome = repository.review_candidate(
        review_spec(candidate, gate),
        actor_id="alice",
        capacity=workspace.capacity,
    )

    assert outcome.approval_id == "sop-approval-first"
    assert outcome.sop_version.version == 1
    assert repository.list_sop_versions(candidate.sop_id) == (
        outcome.sop_version,
    )


@pytest.mark.parametrize(
    ("candidate_fingerprint", "gate_fingerprint", "expected_code"),
    (
        ("0" * 64, None, "stale_sop_candidate"),
        (None, "0" * 64, "stale_sop_review"),
    ),
)
def test_review_rejects_stale_expected_fingerprints(
    tmp_path,
    candidate_fingerprint,
    gate_fingerprint,
    expected_code,
):
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
    spec = SopReviewSpec(
        candidate_id=candidate.asset_id,
        expected_candidate_fingerprint=(
            candidate_fingerprint or candidate.candidate_fingerprint
        ),
        expected_gate_fingerprint=gate_fingerprint or gate.gate_fingerprint,
        expected_reviewer_policy_fingerprint=(
            _fixture_reviewer_policy_fingerprint()
        ),
        decision="approve",
    )

    with pytest.raises(WorkspaceError) as caught:
        repository.review_candidate(
            spec,
            actor_id="alice",
            capacity=workspace.capacity,
        )

    assert caught.value.code == expected_code
    assert repository.list_sop_versions(candidate.sop_id) == ()
    assert not (workspace.root / "models/formal").exists()


def test_replacing_published_model_invalidates_formal_version(tmp_path):
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
    outcome = repository.review_candidate(
        review_spec(candidate, gate),
        actor_id="alice",
        capacity=workspace.capacity,
    )
    (workspace.root / outcome.formal_model.model_path).write_bytes(
        b"replaced-formal-model"
    )

    with pytest.raises(WorkspaceError) as caught:
        repository.load_sop_version(candidate.sop_id, 1)

    assert caught.value.code == "invalid_formal_model"


def test_gate_substitution_across_candidate_directories_is_rejected(tmp_path):
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
    substituted = (
        workspace.root
        / "approvals/sop-reproductions/candidate-other"
        / f"{gate.asset_id}.json"
    )
    substituted.parent.mkdir(parents=True)
    substituted.write_bytes((workspace.root / gate.asset_path).read_bytes())

    with pytest.raises(WorkspaceError) as caught:
        repository.load_gate(gate.asset_id, "candidate-other")

    assert caught.value.code == "invalid_sop_reproduction_gate"


def test_tampered_reproduction_model_invalidates_approved_sop(tmp_path):
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
    repository.review_candidate(
        review_spec(candidate, gate),
        actor_id="alice",
        capacity=workspace.capacity,
    )
    reproduction = RunRepository(workspace.root).load_instance(
        gate.reproduction_run_id,
        gate.reproduction_instance_id,
    )
    reproduction_model = (
        workspace.root / reproduction.asset_path
    ).parent / reproduction.model_path
    reproduction_model.write_bytes(b"tampered-reproduction-model")

    with pytest.raises(WorkspaceError):
        repository.load_sop_version(candidate.sop_id, 1)


def test_tampered_reproduction_binding_cannot_be_resealed_for_approval(tmp_path):
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
    reproduction_manifest = (
        workspace.root
        / "runs"
        / gate.reproduction_run_id
        / "instances"
        / gate.reproduction_instance_id
        / "manifest.json"
    )
    reproduction_payload = json.loads(reproduction_manifest.read_text())
    reproduction_payload["configuration_fingerprint"] = "0" * 64
    _reseal(reproduction_payload, "manifest_fingerprint")
    reproduction_manifest.write_text(
        json.dumps(reproduction_payload, indent=2, sort_keys=True) + "\n"
    )
    gate_path = workspace.root / gate.asset_path
    gate_payload = json.loads(gate_path.read_text())
    gate_payload["reproduction_instance_fingerprint"] = (
        reproduction_payload["manifest_fingerprint"]
    )
    _reseal(gate_payload, "gate_fingerprint")
    gate_path.write_text(
        json.dumps(gate_payload, indent=2, sort_keys=True) + "\n"
    )
    resealed_gate = repository.load_gate(gate.asset_id, candidate.asset_id)

    with pytest.raises(WorkspaceError) as caught:
        repository.review_candidate(
            review_spec(candidate, resealed_gate),
            actor_id="alice",
            capacity=workspace.capacity,
        )

    assert caught.value.code == "invalid_sop_reproduction_gate"
    assert repository.list_sop_versions(candidate.sop_id) == ()


def test_uncommitted_reviewer_policy_cannot_self_authorize_actor(tmp_path):
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
    policy_path = workspace.root / REVIEWER_POLICY_PATH
    policy = json.loads(policy_path.read_text())
    policy["reviewer_ids"] = ["alice", "bob"]
    policy.pop("policy_fingerprint")
    policy["policy_fingerprint"] = MemoryRepository.reviewer_policy_fingerprint(
        policy
    )
    policy_path.write_text(json.dumps(policy, indent=2, sort_keys=True) + "\n")

    with pytest.raises(WorkspaceError) as caught:
        repository.review_candidate(
            review_spec(candidate, gate),
            actor_id="bob",
            capacity=workspace.capacity,
        )

    assert caught.value.code == "reviewer_policy_uncommitted"
    assert repository.list_sop_versions(candidate.sop_id) == ()


def test_stale_reviewer_policy_fingerprint_cannot_approve(tmp_path):
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
    stale = replace(
        review_spec(candidate, gate),
        expected_reviewer_policy_fingerprint="0" * 64,
    )

    with pytest.raises(WorkspaceError) as caught:
        repository.review_candidate(
            stale,
            actor_id="alice",
            capacity=workspace.capacity,
        )

    assert caught.value.code == "stale_reviewer_policy"
    assert repository.list_sop_versions(candidate.sop_id) == ()


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
        expected_reviewer_policy_fingerprint=(
            _fixture_reviewer_policy_fingerprint()
        ),
        decision="approve",
    )


def _fixture_reviewer_policy_fingerprint():
    return MemoryRepository.reviewer_policy_fingerprint(
        {
            "asset_type": "reviewer_policy",
            "asset_id": "reviewer-policy",
            "schema_version": 1,
            "reviewer_ids": ["alice"],
            "created_at": "2026-07-17T00:00:00Z",
            "created_by": "alice",
        }
    )


def _reseal(payload, fingerprint_field):
    canonical = dict(payload)
    canonical.pop(fingerprint_field, None)
    payload[fingerprint_field] = hashlib.sha256(
        json.dumps(
            canonical,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


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

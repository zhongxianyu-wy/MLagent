import hashlib
from dataclasses import dataclass
from pathlib import Path

import pytest

from src.domain.dataset_intake import DatasetInspector
from src.domain.dataset_repository import DatasetRepository
from src.domain.memory_repository import MemoryRepository
from src.domain.models import (
    CandidateCodeFile,
    ConfirmDatasetCommand,
    TrainingExecutionResult,
    WorkspaceError,
)
from src.domain.run_repository import (
    InstancePreparationSpec,
    RunRepository,
    RunStartSpec,
)
from src.domain.sop_repository import SopCandidateSpec, SopRepository


@dataclass
class SopWorkspace:
    root: Path
    capacity: object
    run_repository: RunRepository
    source_run_id: str
    source_instance_id: str
    source_instance_path: Path
    code_revision_path: Path


@pytest.fixture
def sop_workspace(tmp_path) -> SopWorkspace:
    return build_sop_workspace(tmp_path)


def test_complete_source_creates_immutable_candidate(sop_workspace):
    repository = candidate_repository(sop_workspace)

    candidate = repository.create_candidate(
        candidate_spec(sop_workspace),
        actor_id="alice",
        capacity=sop_workspace.capacity,
    )

    assert candidate.source_instance_id == sop_workspace.source_instance_id
    assert candidate.dataset_id == "ds-1"
    assert candidate.source_metric_value == 0.82
    assert {item.role for item in candidate.evidence} == {
        "dataset",
        "run",
        "training_instance",
        "input",
        "environment",
        "split",
        "code_revision",
        "metrics",
        "predictions",
        "source_model",
    }
    manifest = sop_workspace.root / candidate.asset_path
    assert manifest.is_file()
    before = manifest.read_bytes()
    assert repository.load_candidate(candidate.asset_id) == candidate
    assert manifest.read_bytes() == before


def test_identical_candidate_request_is_idempotent(sop_workspace):
    repository = candidate_repository(sop_workspace)
    spec = candidate_spec(sop_workspace)

    first = repository.create_candidate(
        spec,
        actor_id="alice",
        capacity=sop_workspace.capacity,
    )
    repeated = repository.create_candidate(
        spec,
        actor_id="alice",
        capacity=sop_workspace.capacity,
    )

    assert repeated == first
    assert len(list((sop_workspace.root / "sops/candidates").rglob("*.json"))) == 1


@pytest.mark.parametrize(
    ("role", "relative_path"),
    (
        ("input", "input.json"),
        ("environment", "environment.json"),
        ("split", "split.csv"),
        ("metrics", "metrics.json"),
        ("predictions", "predictions.csv"),
        ("source_model", "model.joblib"),
    ),
)
def test_missing_instance_evidence_cannot_create_candidate(
    sop_workspace,
    role,
    relative_path,
):
    (sop_workspace.source_instance_path / relative_path).unlink()

    with pytest.raises(WorkspaceError) as caught:
        candidate_repository(sop_workspace).create_candidate(
            candidate_spec(sop_workspace),
            actor_id="alice",
            capacity=sop_workspace.capacity,
        )

    assert caught.value.code == "sop_source_incomplete"
    assert role in caught.value.message
    assert not list((sop_workspace.root / "sops/candidates").rglob("*.json"))


def test_missing_frozen_code_cannot_create_candidate(sop_workspace):
    (sop_workspace.code_revision_path / "files/train.py").unlink()

    with pytest.raises(WorkspaceError) as caught:
        candidate_repository(sop_workspace).create_candidate(
            candidate_spec(sop_workspace),
            actor_id="alice",
            capacity=sop_workspace.capacity,
        )

    assert caught.value.code == "sop_source_incomplete"
    assert "code_revision" in caught.value.message
    assert not list((sop_workspace.root / "sops/candidates").rglob("*.json"))


def test_dataset_binding_mismatch_cannot_create_candidate(tmp_path):
    workspace = build_sop_workspace(
        tmp_path,
        run_dataset_content_fingerprint="f" * 64,
    )

    with pytest.raises(WorkspaceError) as caught:
        candidate_repository(workspace).create_candidate(
            candidate_spec(workspace),
            actor_id="alice",
            capacity=workspace.capacity,
        )

    assert caught.value.code == "sop_source_mismatch"
    assert "Dataset content fingerprint" in caught.value.message
    assert not list((workspace.root / "sops/candidates").rglob("*.json"))


def test_source_model_fingerprint_mismatch_cannot_create_candidate(
    sop_workspace,
):
    (sop_workspace.source_instance_path / "model.joblib").write_bytes(
        b"replaced-model"
    )

    with pytest.raises(WorkspaceError) as caught:
        candidate_repository(sop_workspace).create_candidate(
            candidate_spec(sop_workspace),
            actor_id="alice",
            capacity=sop_workspace.capacity,
        )

    assert caught.value.code == "sop_source_incomplete"
    assert "source_model" in caught.value.message
    assert not list((sop_workspace.root / "sops/candidates").rglob("*.json"))


def test_unretained_model_cannot_create_candidate(tmp_path):
    workspace = build_sop_workspace(tmp_path, retention_reasons=())

    with pytest.raises(WorkspaceError) as caught:
        candidate_repository(workspace).create_candidate(
            candidate_spec(workspace),
            actor_id="alice",
            capacity=workspace.capacity,
        )

    assert caught.value.code == "sop_source_incomplete"
    assert "source_model" in caught.value.message


def test_failed_training_instance_cannot_create_candidate(tmp_path):
    workspace = build_sop_workspace(tmp_path, completed=False)

    with pytest.raises(WorkspaceError) as caught:
        candidate_repository(workspace).create_candidate(
            candidate_spec(workspace),
            actor_id="alice",
            capacity=workspace.capacity,
        )

    assert caught.value.code == "sop_source_incomplete"
    assert "successful" in caught.value.message
    assert not list((workspace.root / "sops/candidates").rglob("*.json"))


def candidate_repository(workspace: SopWorkspace) -> SopRepository:
    return SopRepository(
        workspace.root,
        candidate_id_factory=lambda: "candidate-1",
        clock=lambda: "2026-07-17T00:10:00Z",
    )


def candidate_spec(workspace: SopWorkspace) -> SopCandidateSpec:
    return SopCandidateSpec(
        sop_id="sop-random-forest",
        name="Random forest baseline",
        source_run_id=workspace.source_run_id,
        source_instance_id=workspace.source_instance_id,
        strategy_summary="Fit a reviewed random forest baseline.",
        optimization_background="Selected after improving validation AUC.",
        steps=(
            "Load the frozen Dataset Version and split",
            "Execute the frozen train.py entrypoint",
        ),
        change_summary="",
    )


def build_sop_workspace(
    tmp_path: Path,
    *,
    retention_reasons: tuple[str, ...] = ("baseline",),
    completed: bool = True,
    run_dataset_content_fingerprint: str | None = None,
) -> SopWorkspace:
    root = tmp_path / "team-memory"
    status = MemoryRepository(
        id_factory=lambda: "tmr-1",
        clock=lambda: "2026-07-17T00:00:00Z",
    ).bootstrap(root, actor_id="alice")
    source = tmp_path / "source"
    source.mkdir()
    feature_path = source / "features.csv"
    label_path = source / "labels.csv"
    feature_path.write_text(
        "sample_id,f1\ns1,1\ns2,2\ns3,3\ns4,4\n",
        encoding="utf-8",
    )
    label_path.write_text(
        "sample_id,group\ns1,case\ns2,case\ns3,control\ns4,control\n",
        encoding="utf-8",
    )
    normalized = DatasetInspector().normalize(
        ConfirmDatasetCommand(
            connection_path=Path(".mlagent-workspace.json"),
            feature_path=feature_path,
            label_path=label_path,
            sample_id_col="sample_id",
            label_col="group",
            task_type="binary",
            positive_class="case",
            primary_metric="roc_auc",
            split_strategy="train_only",
            target_metric=0.9,
        )
    )
    dataset = DatasetRepository(
        root,
        id_factory=lambda: "ds-1",
        clock=lambda: "2026-07-17T00:01:00Z",
    ).create_version(
        normalized,
        actor_id="alice",
        capacity=status.capacity,
    )

    code_root = tmp_path / "code"
    code_root.mkdir()
    code_bytes = b"def build_estimator(context):\n    return context\n"
    (code_root / "train.py").write_bytes(code_bytes)
    code_sha = hashlib.sha256(code_bytes).hexdigest()
    event_ids = iter(f"run-event-{index}" for index in range(1, 10))
    run_repository = RunRepository(
        root,
        event_id_factory=lambda: next(event_ids),
        instance_id_factory=lambda: "instance-source",
        clock=lambda: "2026-07-17T00:02:00Z",
    )
    run_repository.start_run(
        RunStartSpec(
            run_id="run-source",
            dataset_id=dataset.dataset_id,
            dataset_version=dataset.version,
            dataset_content_fingerprint=(
                run_dataset_content_fingerprint
                or dataset.content_fingerprint
            ),
            dataset_version_fingerprint=dataset.version_fingerprint,
            plan_id="plan-1",
            plan_event_id="plan-event-1",
            planning_session_id="session-1",
            plan_fingerprint="d" * 64,
            approval_id="approval-1",
            approval_fingerprint="e" * 64,
            code_fingerprint=code_sha,
            user_direction="Improve validation AUC",
            stop_conditions=("round budget exhausted",),
            primary_metric_name="roc_auc",
            target_metric_value=0.9,
            expected_round_count=1,
        ),
        actor_id="alice",
        capacity=status.capacity,
    )
    revision = run_repository.freeze_code_revision(
        run_id="run-source",
        code_root=code_root,
        candidate_code_files=(
            CandidateCodeFile("train.py", code_sha, len(code_bytes)),
        ),
        code_fingerprint=code_sha,
        entrypoint_path="train.py",
        actor_id="alice",
        capacity=status.capacity,
    )
    prepared = run_repository.prepare_instance(
        InstancePreparationSpec(
            run_id="run-source",
            round_number=1,
            hypothesis="Reviewed baseline",
            optimization_direction="baseline",
            intended_changes=("fit reviewed estimator",),
            random_seed=42,
            parent_instance_id=None,
            parent_instance_fingerprint=None,
            configuration={"worker_contract": 1, "n_estimators": 100},
            environment={"python": "3.13", "sklearn": "1.7"},
        ),
        code_revision=revision,
        split_path=root / dataset.asset_path.replace("manifest.json", "split.csv"),
        actor_id="alice",
        capacity=status.capacity,
    )
    if completed:
        prepared.worker_output_path.mkdir(parents=True)
        predictions = prepared.worker_output_path / "predictions.csv"
        predictions.write_text(
            "sample_id,observed,predicted,probability_case\n"
            "s1,case,case,0.9\n",
            encoding="utf-8",
        )
        model = prepared.worker_output_path / "model.joblib"
        model.write_bytes(b"independently-reproducible-model")
        result = TrainingExecutionResult(
            state="completed",
            primary_metric_name="roc_auc",
            primary_metric_value=0.82,
            metrics={"roc_auc": 0.82, "accuracy": 0.8},
            predictions_path=predictions,
            model_path=model,
            model_fingerprint=hashlib.sha256(model.read_bytes()).hexdigest(),
            error_code=None,
            error_summary=None,
            started_at="2026-07-17T00:03:00Z",
            ended_at="2026-07-17T00:04:00Z",
            duration_ms=60_000,
        )
    else:
        result = TrainingExecutionResult(
            state="failed",
            primary_metric_name="roc_auc",
            primary_metric_value=None,
            metrics={},
            predictions_path=None,
            model_path=None,
            model_fingerprint=None,
            error_code="worker_failed",
            error_summary="Worker failed",
            started_at="2026-07-17T00:03:00Z",
            ended_at="2026-07-17T00:04:00Z",
            duration_ms=60_000,
        )
    instance = run_repository.seal_instance(
        prepared,
        result,
        retention_reasons=retention_reasons if completed else (),
        actor_id="alice",
        capacity=status.capacity,
    )
    return SopWorkspace(
        root=root,
        capacity=status.capacity,
        run_repository=run_repository,
        source_run_id="run-source",
        source_instance_id=instance.asset_id,
        source_instance_path=(root / instance.asset_path).parent,
        code_revision_path=(root / revision.asset_path).parent,
    )

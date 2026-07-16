import hashlib
from pathlib import Path

import pandas as pd
import pytest

from src.domain.dataset_intake import DatasetInspector
from src.domain.dataset_repository import DatasetRepository
from src.domain.memory_repository import MemoryRepository
from src.domain.models import CandidateCodeFile, ConfirmDatasetCommand
from src.domain.run_repository import (
    InstancePreparationSpec,
    RunRepository,
    RunStartSpec,
)
from src.training.executor import SubprocessTrainingExecutor


ESTIMATOR_FIXTURE = (
    Path(__file__).parents[1] / "fixtures" / "training" / "estimator.py"
)


def _prepare_training(tmp_path, task_type):
    memory_root = tmp_path / "team-memory"
    workspace = MemoryRepository(
        id_factory=lambda: "tmr-1",
        clock=lambda: "2026-07-16T00:00:00Z",
    ).bootstrap(memory_root, actor_id="alice")
    source_root = tmp_path / "source"
    source_root.mkdir()
    rows = []
    labels = []
    class_labels = ("case", "control") if task_type == "binary" else ("a", "b", "c")
    centers = {
        "case": 4.0,
        "control": -4.0,
        "a": -6.0,
        "b": 0.0,
        "c": 6.0,
    }
    for class_index, label in enumerate(class_labels):
        for offset in range(10):
            sample_id = f"s{class_index:02d}-{offset:02d}"
            value = centers[label] + offset / 20
            rows.append({"sample_id": sample_id, "f1": value, "f2": value * 0.5})
            labels.append({"sample_id": sample_id, "group": label})
    feature_path = source_root / "features.csv"
    label_path = source_root / "labels.csv"
    pd.DataFrame(rows).to_csv(feature_path, index=False)
    pd.DataFrame(labels).to_csv(label_path, index=False)
    primary_metric = "roc_auc" if task_type == "binary" else "macro_f1"
    split_strategy = "train_only" if task_type == "binary" else "stratified_random"
    normalized = DatasetInspector().normalize(
        ConfirmDatasetCommand(
            connection_path=Path(".mlagent-workspace.json"),
            feature_path=feature_path,
            label_path=label_path,
            sample_id_col="sample_id",
            label_col="group",
            task_type=task_type,
            positive_class="case" if task_type == "binary" else None,
            primary_metric=primary_metric,
            split_strategy=split_strategy,
            test_ratio=None if task_type == "binary" else 0.3,
            target_metric=0.9,
            random_seed=42,
        )
    )
    dataset = DatasetRepository(
        memory_root,
        id_factory=lambda: "ds-1",
        clock=lambda: "2026-07-16T00:00:01Z",
    ).create_version(normalized, actor_id="alice", capacity=workspace.capacity)

    code_root = tmp_path / "approved-code"
    code_root.mkdir()
    code_bytes = ESTIMATOR_FIXTURE.read_bytes()
    (code_root / "estimator.py").write_bytes(code_bytes)
    event_ids = iter(f"run-event-{index}" for index in range(1, 20))
    repository = RunRepository(
        memory_root,
        event_id_factory=lambda: next(event_ids),
        instance_id_factory=lambda: "instance-1",
        clock=lambda: "2026-07-16T00:00:02Z",
    )
    repository.start_run(
        RunStartSpec(
            run_id="run-1",
            dataset_id=dataset.dataset_id,
            dataset_version=dataset.version,
            dataset_content_fingerprint=dataset.content_fingerprint,
            dataset_version_fingerprint=dataset.version_fingerprint,
            plan_id="plan-1",
            plan_event_id="plan-event-1",
            plan_fingerprint="plan-sha",
            approval_id="approval-1",
            approval_fingerprint="approval-sha",
            code_fingerprint="code-sha",
            user_direction="Validate the reviewed estimator",
            stop_conditions=("target reached", "round budget exhausted"),
            primary_metric_name=primary_metric,
            target_metric_value=0.9,
            expected_round_count=1,
        ),
        actor_id="alice",
        capacity=workspace.capacity,
    )
    code_revision = repository.freeze_code_revision(
        run_id="run-1",
        code_root=code_root,
        candidate_code_files=(
            CandidateCodeFile(
                path="estimator.py",
                sha256=hashlib.sha256(code_bytes).hexdigest(),
                size_bytes=len(code_bytes),
            ),
        ),
        code_fingerprint="code-sha",
        entrypoint_path="estimator.py",
        actor_id="alice",
        capacity=workspace.capacity,
    )
    prepared = repository.prepare_instance(
        InstancePreparationSpec(
            run_id="run-1",
            round_number=1,
            hypothesis="Reviewed logistic baseline",
            optimization_direction="baseline",
            intended_changes=("fit reviewed estimator",),
            random_seed=42,
            parent_instance_id=None,
            parent_instance_fingerprint=None,
            configuration={"worker_contract": 1},
            environment={"python": "3.13", "sklearn": "1.8"},
        ),
        code_revision=code_revision,
        split_path=memory_root / dataset.asset_path.replace("manifest.json", "split.csv"),
        actor_id="alice",
        capacity=workspace.capacity,
    )
    return repository, prepared, workspace.capacity


@pytest.mark.parametrize(
    ("task_type", "expected_metrics"),
    [
        ("binary", {"roc_auc", "accuracy", "f1"}),
        ("multiclass", {"macro_f1", "accuracy", "roc_auc_ovr"}),
    ],
)
def test_frozen_code_runs_real_deterministic_classification(
    tmp_path,
    task_type,
    expected_metrics,
):
    repository, prepared, capacity = _prepare_training(tmp_path, task_type)
    executor = SubprocessTrainingExecutor(poll_interval_seconds=0.01)

    first = executor.execute(prepared, stop_requested=lambda: False, timeout_seconds=30)
    first_predictions = first.predictions_path.read_bytes()
    second = executor.execute(prepared, stop_requested=lambda: False, timeout_seconds=30)

    assert first.state == "completed"
    assert set(first.metrics) == expected_metrics
    assert all(0 <= value <= 1 for value in first.metrics.values())
    assert first_predictions == second.predictions_path.read_bytes()
    sealed = repository.seal_instance(
        prepared,
        second,
        retention_reasons=("baseline",),
        actor_id="alice",
        capacity=capacity,
    )
    assert sealed.state == "completed"
    assert sealed.model_path == "model.joblib"


def test_executor_reports_stop_without_claiming_success(tmp_path):
    _, prepared, _ = _prepare_training(tmp_path, "binary")

    result = SubprocessTrainingExecutor().execute(
        prepared,
        stop_requested=lambda: True,
        timeout_seconds=30,
    )

    assert result.state == "stopped"
    assert result.error_code == "user_stop"
    assert result.primary_metric_value is None


def test_executor_times_out_and_rejects_malformed_worker_output(tmp_path):
    _, prepared, _ = _prepare_training(tmp_path, "binary")
    timeout = SubprocessTrainingExecutor(poll_interval_seconds=0.01).execute(
        prepared,
        stop_requested=lambda: False,
        timeout_seconds=0.001,
    )
    malformed = SubprocessTrainingExecutor(
        worker_module="src.training.runner",
        poll_interval_seconds=0.01,
    ).execute(
        prepared,
        stop_requested=lambda: False,
        timeout_seconds=30,
    )

    assert timeout.state == "timed_out"
    assert timeout.error_code == "training_timeout"
    assert malformed.state == "failed"
    assert malformed.error_code == "invalid_worker_result"

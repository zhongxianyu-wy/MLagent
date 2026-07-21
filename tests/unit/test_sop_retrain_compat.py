"""Unit tests for SOP retraining compatibility (Issue #10 T2)."""
from src.domain.models import (
    DatasetVersionSnapshot,
    DatasetPreview,
    SopVersionSnapshot,
)
from src.domain.sop_retrain import check_retrain_compatibility


def _sop(metric="roc_auc"):
    """Minimal SopVersionSnapshot for testing."""
    return SopVersionSnapshot(
        asset_id="sop-v1",
        asset_path="sops/approved/sop-v1/manifest.json",
        sop_id="baseline",
        version=1,
        version_fingerprint="a" * 64,
        previous_version_id=None,
        previous_version_fingerprint=None,
        candidate_id="cand-1",
        gate_id="gate-1",
        gate_fingerprint="b" * 64,
        source_run_id="run-1",
        source_instance_id="inst-1",
        reproduction_run_id="run-repro-1",
        reproduction_instance_id="inst-repro-1",
        dataset_id="ds1",
        dataset_version=1,
        primary_metric_name=metric,
        primary_metric_value=0.85,
        source_metric_value=0.85,
        reproduction_metric_value=0.85,
        environment={"python": "3.11"},
        strategy_summary="baseline",
        optimization_background="chi2 top-50",
        steps=("Load data", "Train RF", "Evaluate"),
        change_summary="initial",
        approval_id="appr-1",
        formal_model_id="fm-1",
        created_at="2026-07-21T00:00:00Z",
        created_by="alice",
    )


def _dataset(metric="roc_auc", task="binary_classification", features=100, samples=200):
    return DatasetVersionSnapshot(
        asset_id="ds-v2",
        asset_path="datasets/ds1/v2/manifest.json",
        dataset_id="ds1",
        version=2,
        state="confirmed",
        schema_version=1,
        created_at="2026-07-21T00:00:00Z",
        created_by="alice",
        content_fingerprint="c" * 64,
        version_fingerprint="d" * 64,
        source_files=(),
        sample_id_col="sample_id",
        label_col="group",
        task_type=task,
        class_labels=("case", "control"),
        positive_class="case",
        primary_metric=metric,
        target_metric=0.9,
        split_strategy="stratified",
        test_ratio=0.2,
        random_seed=42,
        sample_count=samples,
        feature_count=features,
        dtypes={},
        missing_rates={},
        class_distribution={"case": 100, "control": 100},
        preview=DatasetPreview(
            columns=(),
            rows=(),
            omitted_count=0,
        ),
        warnings=(),
        files={},
    )


def test_compatible_dataset_passes_all_checks():
    report = check_retrain_compatibility(_sop(), _dataset())
    assert report.compatible
    assert all(passed for _, _, passed in report.checks)
    assert len(report.checks) >= 4


def test_incompatible_metric_rejected():
    report = check_retrain_compatibility(_sop("roc_auc"), _dataset(metric="accuracy"))
    assert not report.compatible
    metric_check = next(c for c in report.checks if c[0] == "primary_metric")
    assert metric_check[2] is False


def test_incompatible_task_type_rejected():
    report = check_retrain_compatibility(_sop(), _dataset(task="regression"))
    assert not report.compatible
    task_check = next(c for c in report.checks if c[0] == "task_type")
    assert task_check[2] is False


def test_empty_dataset_rejected():
    report = check_retrain_compatibility(_sop(), _dataset(features=0, samples=0))
    assert not report.compatible

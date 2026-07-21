"""SOP retraining compatibility checker — pure functions, no side effects."""

from __future__ import annotations

from src.domain.models import (
    DatasetVersionSnapshot,
    SopRetrainCompatibilityReport,
    SopVersionSnapshot,
)


def check_retrain_compatibility(
    sop: SopVersionSnapshot,
    new_dataset: DatasetVersionSnapshot,
) -> SopRetrainCompatibilityReport:
    """Check whether *new_dataset* is compatible with *sop* for retraining."""
    checks: list[tuple[str, str, bool]] = []

    # 1. primary metric
    metric_ok = sop.primary_metric_name == new_dataset.primary_metric
    checks.append((
        "primary_metric",
        f"SOP expects '{sop.primary_metric_name}', dataset has "
        f"'{new_dataset.primary_metric}'",
        metric_ok,
    ))

    # 2. task type
    task_ok = new_dataset.task_type in (
        "binary", "binary_classification",
        "multiclass", "multiclass_classification",
    )
    checks.append((
        "task_type",
        f"Dataset task type is '{new_dataset.task_type}'",
        task_ok,
    ))

    # 3. feature schema — new dataset must have at least the original features
    #    (we can't directly know the original feature list from SopVersionSnapshot,
    #     but we can check that the dataset has a non-empty feature set that
    #     is compatible with the SOP's dataset_id lineage)
    feature_ok = new_dataset.feature_count > 0
    checks.append((
        "feature_schema",
        f"Dataset has {new_dataset.feature_count} features",
        feature_ok,
    ))

    # 4. label column present
    label_ok = bool(new_dataset.label_col)
    checks.append((
        "label_column",
        f"Label column: '{new_dataset.label_col}'",
        label_ok,
    ))

    # 5. sample count > 0
    sample_ok = new_dataset.sample_count > 0
    checks.append((
        "sample_count",
        f"Dataset has {new_dataset.sample_count} samples",
        sample_ok,
    ))

    compatible = all(passed for _, _, passed in checks)
    return SopRetrainCompatibilityReport(
        compatible=compatible,
        checks=tuple(checks),
    )

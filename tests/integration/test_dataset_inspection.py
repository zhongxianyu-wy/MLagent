from pathlib import Path

import pandas as pd
import pytest

from src.domain.dataset_intake import DatasetInspector
from src.domain.models import (
    ConfirmDatasetCommand,
    InspectDatasetCommand,
    WorkspaceError,
)


def write_pair(
    root: Path,
    features: pd.DataFrame,
    labels: pd.DataFrame,
) -> tuple[Path, Path]:
    feature_path = root / "features.csv"
    label_path = root / "labels.csv"
    features.to_csv(feature_path, index=False)
    labels.to_csv(label_path, index=False)
    return feature_path, label_path


def confirmation(
    feature_path: Path,
    label_path: Path,
    **changes,
) -> ConfirmDatasetCommand:
    values = {
        "connection_path": Path(".mlagent-workspace.json"),
        "feature_path": feature_path,
        "label_path": label_path,
        "sample_id_col": "sample_id",
        "label_col": "group",
        "task_type": "binary",
        "positive_class": "case",
        "primary_metric": "roc_auc",
        "split_strategy": "train_only",
        "target_metric": 0.9,
    }
    values.update(changes)
    return ConfirmDatasetCommand(**values)


def test_binary_inspection_stays_pending_and_builds_bounded_head_tail_preview(
    tmp_path,
):
    sample_ids = [f"s{index:02d}" for index in range(12)]
    feature_path, label_path = write_pair(
        tmp_path,
        pd.DataFrame(
            {
                "sample_id": sample_ids,
                "f1": [index / 10 for index in range(12)],
                "f2": list(range(12)),
            }
        ),
        pd.DataFrame(
            {
                "sample_id": sample_ids,
                "group": ["case"] * 6 + ["control"] * 6,
            }
        ),
    )

    inspection = DatasetInspector().inspect(
        InspectDatasetCommand(feature_path=feature_path, label_path=label_path)
    )

    assert inspection.status == "Pending confirmation"
    assert inspection.inferred_sample_id_col == "sample_id"
    assert inspection.inferred_label_col == "group"
    assert inspection.inferred_task_type == "binary"
    assert inspection.sample_count == 12
    assert inspection.feature_count == 2
    assert inspection.class_distribution == {"case": 6, "control": 6}
    assert inspection.preview.columns == ("sample_id", "f1", "f2", "group")
    assert len(inspection.preview.rows) == 10
    assert inspection.preview.omitted_count == 2
    assert inspection.preview.rows[0][0] == "s00"
    assert inspection.preview.rows[-1][0] == "s11"
    assert inspection.unresolved_fields == (
        "positive_class",
        "primary_metric",
        "split_strategy",
        "target_metric",
    )
    assert inspection.blockers == ()


def test_multiclass_inspection_profiles_missing_features_and_classes(tmp_path):
    feature_path, label_path = write_pair(
        tmp_path,
        pd.DataFrame(
            {
                "sample_id": ["s1", "s2", "s3", "s4", "s5", "s6"],
                "f1": [1.0, None, 3.0, 4.0, 5.0, 6.0],
            }
        ),
        pd.DataFrame(
            {
                "sample_id": ["s1", "s2", "s3", "s4", "s5", "s6"],
                "group": ["a", "b", "c", "a", "b", "c"],
            }
        ),
    )

    inspection = DatasetInspector().inspect(
        InspectDatasetCommand(feature_path=feature_path, label_path=label_path)
    )

    assert inspection.inferred_task_type == "multiclass"
    assert inspection.class_labels == ("a", "b", "c")
    assert inspection.missing_rates["f1"] == pytest.approx(1 / 6)
    assert "feature_missing_values" in inspection.warnings
    assert "positive_class" not in inspection.unresolved_fields


def test_ambiguous_columns_remain_unconfirmed_without_writing_facts(tmp_path):
    feature_path, label_path = write_pair(
        tmp_path,
        pd.DataFrame({"patient_key": ["p1", "p2"], "f1": [1, 2]}),
        pd.DataFrame(
            {
                "patient_key": ["p1", "p2"],
                "diagnosis": ["case", "control"],
                "cohort": ["x", "x"],
            }
        ),
    )

    inspection = DatasetInspector().inspect(
        InspectDatasetCommand(feature_path=feature_path, label_path=label_path)
    )

    assert inspection.inferred_sample_id_col is None
    assert inspection.inferred_label_col is None
    assert inspection.inferred_task_type is None
    assert inspection.status == "Pending confirmation"
    assert inspection.unresolved_fields[:3] == (
        "sample_id_col",
        "label_col",
        "task_type",
    )


@pytest.mark.parametrize(
    ("features", "labels", "blocker"),
    [
        (
            pd.DataFrame({"sample_id": ["s1", "s1"], "f1": [1, 2]}),
            pd.DataFrame({"sample_id": ["s1", "s2"], "group": ["case", "control"]}),
            "duplicate_feature_sample_id",
        ),
        (
            pd.DataFrame({"sample_id": ["s1", "s2"], "f1": [1, 2]}),
            pd.DataFrame({"sample_id": ["s1", "s3"], "group": ["case", "control"]}),
            "sample_mismatch",
        ),
        (
            pd.DataFrame({"sample_id": ["s1", "s2"], "f1": [1, 2]}),
            pd.DataFrame({"sample_id": ["s1", "s2"], "group": ["case", None]}),
            "missing_label",
        ),
    ],
)
def test_structural_data_errors_are_visible_blockers(
    tmp_path,
    features,
    labels,
    blocker,
):
    feature_path, label_path = write_pair(tmp_path, features, labels)

    inspection = DatasetInspector().inspect(
        InspectDatasetCommand(feature_path=feature_path, label_path=label_path)
    )

    assert inspection.status == "Failed"
    assert blocker in inspection.blockers


def test_normalize_binary_data_aligns_labels_and_creates_train_only_split(tmp_path):
    feature_path, label_path = write_pair(
        tmp_path,
        pd.DataFrame(
            {"sample_id": ["s1", "s2", "s3", "s4"], "f1": [1, 2, 3, 4]}
        ),
        pd.DataFrame(
            {
                "sample_id": ["s4", "s3", "s2", "s1"],
                "group": ["control", "control", "case", "case"],
            }
        ),
    )

    normalized = DatasetInspector().normalize(
        confirmation(feature_path, label_path)
    )

    assert normalized.task_type == "binary"
    assert normalized.class_labels == ("case", "control")
    assert normalized.positive_class == "case"
    assert normalized.sample_count == 4
    assert normalized.split_bytes.decode().splitlines() == [
        "sample_id,partition",
        "s1,train",
        "s2,train",
        "s3,train",
        "s4,train",
    ]
    assert len(normalized.content_fingerprint) == 64
    assert len(normalized.version_fingerprint) == 64


def test_normalize_multiclass_data_uses_reproducible_stratified_split(tmp_path):
    sample_ids = [f"s{index}" for index in range(12)]
    feature_path, label_path = write_pair(
        tmp_path,
        pd.DataFrame({"sample_id": sample_ids, "f1": list(range(12))}),
        pd.DataFrame(
            {
                "sample_id": sample_ids,
                "group": ["a", "b", "c"] * 4,
            }
        ),
    )
    command = confirmation(
        feature_path,
        label_path,
        task_type="multiclass",
        positive_class=None,
        primary_metric="macro_f1",
        split_strategy="stratified_random",
        test_ratio=0.25,
        random_seed=7,
    )

    first = DatasetInspector().normalize(command)
    second = DatasetInspector().normalize(command)

    assert first.split_bytes == second.split_bytes
    assert first.class_labels == ("a", "b", "c")
    assert first.split_bytes.decode().count(",test") == 3


@pytest.mark.parametrize(
    ("changes", "error_code"),
    [
        ({"task_type": "regression"}, "unsupported_task"),
        ({"positive_class": "unknown"}, "invalid_positive_class"),
        ({"primary_metric": "macro_f1"}, "invalid_metric"),
        ({"target_metric": 1.1}, "invalid_target_metric"),
        (
            {"split_strategy": "stratified_random", "test_ratio": None},
            "invalid_split",
        ),
    ],
)
def test_confirmation_rejects_invalid_classification_semantics(
    tmp_path,
    changes,
    error_code,
):
    feature_path, label_path = write_pair(
        tmp_path,
        pd.DataFrame(
            {"sample_id": ["s1", "s2", "s3", "s4"], "f1": [1, 2, 3, 4]}
        ),
        pd.DataFrame(
            {
                "sample_id": ["s1", "s2", "s3", "s4"],
                "group": ["case", "case", "control", "control"],
            }
        ),
    )

    with pytest.raises(WorkspaceError) as caught:
        DatasetInspector().normalize(
            confirmation(feature_path, label_path, **changes)
        )

    assert caught.value.code == error_code
    assert caught.value.next_action

from pathlib import Path

import pytest

from src.domain.models import (
    ConfirmDatasetCommand,
    DatasetInspection,
    DatasetPreview,
    DatasetVersionSnapshot,
    InspectDatasetCommand,
)


def dataset_preview() -> DatasetPreview:
    return DatasetPreview(
        columns=("sample_id", "f1", "group"),
        rows=(("s1", 0.2, "case"), ("s12", 0.8, "control")),
        omitted_count=10,
    )


def test_dataset_inspection_serializes_bounded_preview():
    inspection = DatasetInspection(
        status="Pending confirmation",
        feature_path=Path("features.csv"),
        label_path=Path("labels.csv"),
        inferred_sample_id_col="sample_id",
        inferred_label_col="group",
        inferred_task_type="binary",
        class_labels=("case", "control"),
        sample_count=12,
        feature_count=1,
        dtypes={"f1": "float64"},
        missing_rates={"f1": 0.0},
        class_distribution={"case": 6, "control": 6},
        preview=dataset_preview(),
        unresolved_fields=(
            "positive_class",
            "primary_metric",
            "split_strategy",
            "target_metric",
        ),
        warnings=(),
        blockers=(),
        elapsed_ms=4,
    )

    payload = inspection.to_dict()

    assert payload["preview"]["omitted_count"] == 10
    assert payload["preview"]["rows"] == [
        ["s1", 0.2, "case"],
        ["s12", 0.8, "control"],
    ]
    assert payload["class_labels"] == ["case", "control"]
    assert payload["feature_path"] == "features.csv"


def test_dataset_commands_and_version_snapshot_are_immutable_and_serializable():
    inspection_command = InspectDatasetCommand(
        feature_path=Path("features.csv"),
        label_path=Path("labels.csv"),
    )
    confirmation = ConfirmDatasetCommand(
        connection_path=Path(".mlagent-workspace.json"),
        feature_path=inspection_command.feature_path,
        label_path=inspection_command.label_path,
        sample_id_col="sample_id",
        label_col="group",
        task_type="binary",
        positive_class="case",
        primary_metric="roc_auc",
        split_strategy="train_only",
        target_metric=0.9,
    )
    version = DatasetVersionSnapshot(
        asset_id="ds-1-v0001",
        asset_path="datasets/ds-1/v0001/manifest.json",
        dataset_id="ds-1",
        version=1,
        state="confirmed",
        schema_version=1,
        created_at="2026-07-14T00:00:00Z",
        created_by="alice",
        content_fingerprint="content-sha",
        version_fingerprint="version-sha",
        source_files=(
            {"role": "features", "name": "features.csv", "sha256": "f-sha"},
            {"role": "labels", "name": "labels.csv", "sha256": "l-sha"},
        ),
        sample_id_col="sample_id",
        label_col="group",
        task_type="binary",
        class_labels=("case", "control"),
        positive_class="case",
        primary_metric="roc_auc",
        target_metric=0.9,
        split_strategy="train_only",
        test_ratio=None,
        random_seed=42,
        sample_count=12,
        feature_count=1,
        dtypes={"f1": "float64"},
        missing_rates={"f1": 0.0},
        class_distribution={"case": 6, "control": 6},
        preview=dataset_preview(),
        warnings=(),
        files={
            "features": "features.csv",
            "labels": "labels.csv",
            "split": "split.csv",
        },
    )

    assert version.to_dict()["source_files"][0]["name"] == "features.csv"
    assert confirmation.random_seed == 42
    with pytest.raises(AttributeError):
        version.version = 2

from pathlib import Path

from src.frontend_api.dataset_service import DatasetService


def test_dataset_service_inspects_clear_feature_and_label_files(tmp_path):
    service = DatasetService(output_root=str(tmp_path / "standardized"))

    inspection = service.inspect_path("tests/fixtures/data_intake/clear")

    assert inspection.ready is True
    assert inspection.feature_file.endswith("features.csv")
    assert inspection.label_file.endswith("labels.csv")
    assert inspection.sample_id_col == "sample_id"
    assert inspection.label_col == "group"
    assert inspection.unresolved_questions == []


def test_dataset_service_builds_manifest_and_standardized_files(tmp_path):
    service = DatasetService(output_root=str(tmp_path / "standardized"))
    inspection = service.inspect_path("tests/fixtures/data_intake/clear")

    manifest = service.build_manifest(inspection.session_id)

    assert manifest.dataset_id == inspection.session_id
    assert Path(manifest.train_feature_path).exists()
    assert Path(manifest.train_label_path).exists()
    assert manifest.positive_label == "case"
    assert manifest.negative_label == "control"
    assert manifest.split_strategy == "train_only"

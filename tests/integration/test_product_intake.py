import json
from pathlib import Path

import pandas as pd

from src.frontend_api.dataset_service import DatasetService


def test_intake_writes_manifest_and_standardized_files(tmp_path):
    service = DatasetService(output_root=str(tmp_path / "standardized"))
    inspection = service.inspect_path("tests/fixtures/data_intake/clear")

    manifest = service.build_manifest(inspection.session_id)
    manifest_path = Path(tmp_path, "standardized", manifest.dataset_id, "manifest.json")

    assert manifest_path.exists()
    payload = json.loads(manifest_path.read_text())
    assert payload["dataset_id"] == manifest.dataset_id
    assert Path(payload["train_feature_path"]).exists()
    assert Path(payload["train_label_path"]).exists()
    assert payload["split_strategy"] in {"provided", "random", "train_only"}


def test_intake_random_split_creates_train_and_test_files(tmp_path):
    service = DatasetService(output_root=str(tmp_path / "standardized"))
    inspection = service.inspect_path("tests/fixtures/data_intake/clear")

    manifest = service.build_manifest(
        inspection.session_id,
        split_strategy="random",
        split_ratio=0.5,
        random_seed=7,
    )

    train_labels = pd.read_csv(manifest.train_label_path)
    test_labels = pd.read_csv(manifest.test_label_path)
    assert len(train_labels) + len(test_labels) == 4
    assert len(test_labels) == 2
    assert set(train_labels["sample_id"]).isdisjoint(set(test_labels["sample_id"]))


def test_random_split_rejects_invalid_ratio(tmp_path):
    service = DatasetService(output_root=str(tmp_path / "standardized"))
    inspection = service.inspect_path("tests/fixtures/data_intake/clear")

    try:
        service.build_manifest(
            inspection.session_id,
            split_strategy="random",
            split_ratio=1.0,
            random_seed=7,
        )
    except ValueError as exc:
        assert "split_ratio must be between 0 and 1" in str(exc)
    else:
        raise AssertionError("random split should reject invalid ratio")

import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from src.domain.dataset_intake import DatasetInspector
from src.domain.dataset_repository import DatasetRepository
from src.domain.local_index import LocalIndex
from src.domain.memory_repository import MemoryRepository
from src.domain.models import ConfirmDatasetCommand, WorkspaceError


def bootstrap_workspace(tmp_path):
    repository_path = tmp_path / "team-memory"
    workspace = MemoryRepository(
        id_factory=lambda: "tmr-1",
        clock=lambda: "2026-07-14T00:00:00Z",
    ).bootstrap(repository_path, actor_id="alice")
    return repository_path, workspace


def write_pair(
    root: Path,
    labels=("case", "case", "control", "control"),
    include_f2=False,
):
    root.mkdir(parents=True, exist_ok=True)
    sample_ids = ["s1", "s2", "s3", "s4"]
    feature_data = {"sample_id": sample_ids, "f1": [1, 2, 3, 4]}
    if include_f2:
        feature_data["f2"] = [5, 6, 7, 8]
    feature_path = root / "features.csv"
    label_path = root / "labels.csv"
    pd.DataFrame(feature_data).to_csv(feature_path, index=False)
    pd.DataFrame(
        {"sample_id": sample_ids, "group": list(labels)}
    ).to_csv(label_path, index=False)
    return feature_path, label_path


def normalize(feature_path, label_path, **changes):
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
    return DatasetInspector().normalize(ConfirmDatasetCommand(**values))


def dataset_repository(repository_path):
    return DatasetRepository(
        repository_path,
        id_factory=lambda: "ds-1",
        clock=lambda: "2026-07-14T01:00:00Z",
    )


def test_create_and_repeat_identical_dataset_version_is_idempotent(tmp_path):
    repository_path, workspace = bootstrap_workspace(tmp_path)
    feature_path, label_path = write_pair(tmp_path / "source")
    normalized = normalize(feature_path, label_path)
    repository = dataset_repository(repository_path)

    created = repository.create_version(
        normalized,
        actor_id="alice",
        capacity=workspace.capacity,
    )
    repeated = repository.create_version(
        normalized,
        actor_id="alice",
        capacity=workspace.capacity,
    )

    assert created == repeated
    assert created.dataset_id == "ds-1"
    assert created.version == 1
    assert created.asset_path == "datasets/ds-1/v0001/manifest.json"
    assert repository.load("ds-1", 1) == created
    assert (repository_path / created.asset_path).is_file()
    manifest = json.loads((repository_path / created.asset_path).read_text())
    assert manifest["asset_type"] == "dataset_version"
    assert manifest["asset_id"] == "ds-1-v0001"
    assert manifest["source_files"][0]["name"] == "features.csv"
    assert all("/" not in item["name"] for item in manifest["source_files"])
    assert sorted(path.name for path in (repository_path / "datasets/ds-1").iterdir()) == [
        "v0001"
    ]


def test_default_id_factory_reuses_identical_dataset_across_families(tmp_path):
    repository_path, workspace = bootstrap_workspace(tmp_path)
    feature_path, label_path = write_pair(tmp_path / "source")
    normalized = normalize(feature_path, label_path)
    repository = DatasetRepository(
        repository_path,
        clock=lambda: "2026-07-14T01:00:00Z",
    )

    first = repository.create_version(
        normalized,
        actor_id="alice",
        capacity=workspace.capacity,
    )
    repeated = repository.create_version(
        normalized,
        actor_id="alice",
        capacity=workspace.capacity,
    )

    assert repeated == first
    assert [path.name for path in (repository_path / "datasets").iterdir()] == [
        first.dataset_id
    ]


@pytest.mark.parametrize("change", ["labels", "schema", "split"])
def test_changed_dataset_inputs_append_version_without_rewriting_v1(
    tmp_path,
    change,
):
    repository_path, workspace = bootstrap_workspace(tmp_path)
    feature_path, label_path = write_pair(tmp_path / "source")
    repository = dataset_repository(repository_path)
    first = repository.create_version(
        normalize(feature_path, label_path),
        actor_id="alice",
        capacity=workspace.capacity,
    )
    first_bytes = (repository_path / first.asset_path).read_bytes()

    if change == "labels":
        feature_path, label_path = write_pair(
            tmp_path / "source",
            labels=("control", "control", "case", "case"),
        )
        changed = normalize(feature_path, label_path)
    elif change == "schema":
        feature_path, label_path = write_pair(
            tmp_path / "source",
            include_f2=True,
        )
        changed = normalize(feature_path, label_path)
    else:
        changed = normalize(
            feature_path,
            label_path,
            split_strategy="stratified_random",
            test_ratio=0.5,
        )

    second = repository.create_version(
        changed,
        actor_id="alice",
        capacity=workspace.capacity,
        dataset_id=first.dataset_id,
    )

    assert second.version == 2
    assert second.version_fingerprint != first.version_fingerprint
    assert (repository_path / first.asset_path).read_bytes() == first_bytes
    assert (repository_path / "datasets/ds-1/v0002/manifest.json").is_file()


def test_changed_source_bytes_create_new_version_even_when_normalized_data_match(
    tmp_path,
):
    repository_path, workspace = bootstrap_workspace(tmp_path)
    feature_path, label_path = write_pair(tmp_path / "source")
    repository = dataset_repository(repository_path)
    first = repository.create_version(
        normalize(feature_path, label_path),
        actor_id="alice",
        capacity=workspace.capacity,
    )
    original_content_fingerprint = first.content_fingerprint

    feature_path.write_bytes(feature_path.read_bytes().replace(b"\n", b"\r\n"))
    second = repository.create_version(
        normalize(feature_path, label_path),
        actor_id="alice",
        capacity=workspace.capacity,
        dataset_id=first.dataset_id,
    )

    assert second.version == 2
    assert second.content_fingerprint == original_content_fingerprint
    assert second.version_fingerprint != first.version_fingerprint
    assert second.source_files != first.source_files


def test_dataset_id_cannot_escape_managed_dataset_root(tmp_path):
    repository_path, workspace = bootstrap_workspace(tmp_path)
    feature_path, label_path = write_pair(tmp_path / "source")

    with pytest.raises(WorkspaceError) as caught:
        dataset_repository(repository_path).create_version(
            normalize(feature_path, label_path),
            actor_id="alice",
            capacity=workspace.capacity,
            dataset_id="../../outside",
        )

    assert caught.value.code == "invalid_dataset_id"
    assert not (tmp_path / "outside").exists()


@pytest.mark.parametrize("link_level", ["datasets", "family"])
def test_symlinked_dataset_paths_cannot_escape_team_memory(tmp_path, link_level):
    repository_path, workspace = bootstrap_workspace(tmp_path)
    feature_path, label_path = write_pair(tmp_path / "source")
    outside = tmp_path / "outside"
    outside.mkdir()
    datasets_path = repository_path / "datasets"
    if link_level == "datasets":
        datasets_path.rmdir()
        datasets_path.symlink_to(outside, target_is_directory=True)
    else:
        (datasets_path / "ds-safe").symlink_to(outside, target_is_directory=True)

    with pytest.raises(WorkspaceError) as caught:
        dataset_repository(repository_path).create_version(
            normalize(feature_path, label_path),
            actor_id="alice",
            capacity=workspace.capacity,
            dataset_id="ds-safe",
        )

    assert caught.value.code == "unsafe_dataset_path"
    assert list(outside.iterdir()) == []


def test_tampered_dataset_file_is_rejected_on_reload(tmp_path):
    repository_path, workspace = bootstrap_workspace(tmp_path)
    feature_path, label_path = write_pair(tmp_path / "source")
    repository = dataset_repository(repository_path)
    created = repository.create_version(
        normalize(feature_path, label_path),
        actor_id="alice",
        capacity=workspace.capacity,
    )
    (repository_path / "datasets/ds-1/v0001/features.csv").write_text(
        "sample_id,f1\ns1,999\n"
    )

    with pytest.raises(WorkspaceError) as caught:
        repository.load(created.dataset_id, created.version)

    assert caught.value.code == "dataset_fingerprint_mismatch"
    assert "Restore" in caught.value.next_action


@pytest.mark.parametrize("limit", ["file", "repository"])
def test_capacity_failure_leaves_no_partial_dataset_version(tmp_path, limit):
    repository_path, workspace = bootstrap_workspace(tmp_path)
    feature_path, label_path = write_pair(tmp_path / "source")
    normalized = normalize(feature_path, label_path)
    if limit == "file":
        capacity = replace(workspace.capacity, max_file_bytes=10)
        expected_code = "file_too_large"
    else:
        capacity = replace(
            workspace.capacity,
            bytes_used=workspace.capacity.max_repository_bytes - 1,
        )
        expected_code = "repository_capacity_exceeded"

    with pytest.raises(WorkspaceError) as caught:
        dataset_repository(repository_path).create_version(
            normalized,
            actor_id="alice",
            capacity=capacity,
        )

    assert caught.value.code == expected_code
    assert not (repository_path / "datasets/ds-1").exists()


def test_committed_dataset_version_is_compatible_with_local_index(tmp_path):
    repository_path, workspace = bootstrap_workspace(tmp_path)
    feature_path, label_path = write_pair(tmp_path / "source")
    created = dataset_repository(repository_path).create_version(
        normalize(feature_path, label_path),
        actor_id="alice",
        capacity=workspace.capacity,
    )
    subprocess.run(
        ["git", "add", "--", "datasets"],
        cwd=repository_path,
        capture_output=True,
        text=True,
        check=True,
    )
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=tester",
            "-c",
            "user.email=tester@mlagent.local",
            "commit",
            "-m",
            "test: add dataset version",
        ],
        cwd=repository_path,
        capture_output=True,
        text=True,
        check=True,
    )

    index = LocalIndex(repository_path)
    index.rebuild()
    assets = index.list_assets()

    assert [asset["asset_id"] for asset in assets] == [
        "tmr-1",
        "reviewer-policy",
        created.asset_id,
    ]
    assert assets[2]["asset_type"] == "dataset_version"
    assert assets[2]["state"] == "confirmed"


def test_latest_returns_most_recent_version_across_dataset_families(tmp_path):
    repository_path, workspace = bootstrap_workspace(tmp_path)
    feature_path, label_path = write_pair(tmp_path / "source")
    repository = dataset_repository(repository_path)
    repository.create_version(
        normalize(feature_path, label_path),
        actor_id="alice",
        capacity=workspace.capacity,
    )
    second_repository = DatasetRepository(
        repository_path,
        id_factory=lambda: "ds-2",
        clock=lambda: "2026-07-14T02:00:00Z",
    )
    second = second_repository.create_version(
        normalize(feature_path, label_path, target_metric=0.8),
        actor_id="bob",
        capacity=workspace.capacity,
    )

    assert second_repository.latest() == second

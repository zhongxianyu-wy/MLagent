from pathlib import Path

import pandas as pd
import pytest

from src.domain.core import DomainCore
from src.domain.models import (
    BootstrapMemoryCommand,
    ConfirmDatasetCommand,
    InspectDatasetCommand,
    WorkspaceError,
)


def write_pair(root: Path):
    feature_path = root / "features.csv"
    label_path = root / "labels.csv"
    pd.DataFrame(
        {
            "sample_id": ["s1", "s2", "s3", "s4"],
            "f1": [1, 2, 3, 4],
        }
    ).to_csv(feature_path, index=False)
    pd.DataFrame(
        {
            "sample_id": ["s1", "s2", "s3", "s4"],
            "group": ["case", "case", "control", "control"],
        }
    ).to_csv(label_path, index=False)
    return feature_path, label_path


def core_and_workspace(tmp_path):
    core = DomainCore(
        id_factory=lambda: "tmr-1",
        dataset_id_factory=lambda: "ds-1",
        clock=lambda: "2026-07-14T00:00:00Z",
    )
    repository_path = tmp_path / "team-memory"
    connection_path = tmp_path / ".mlagent-workspace.json"
    core.bootstrap_memory(
        BootstrapMemoryCommand(
            repository_path=repository_path,
            actor_id="alice",
            connection_path=connection_path,
        )
    )
    return core, repository_path, connection_path


def confirmation(connection_path, feature_path, label_path, **changes):
    values = {
        "connection_path": connection_path,
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


def test_domain_core_inspection_is_read_only_and_confirmation_writes_version(
    tmp_path,
):
    core, repository_path, connection_path = core_and_workspace(tmp_path)
    feature_path, label_path = write_pair(tmp_path)

    inspection = core.inspect_dataset(
        InspectDatasetCommand(feature_path=feature_path, label_path=label_path)
    )

    assert inspection.status == "Pending confirmation"
    assert list((repository_path / "datasets").iterdir()) == []

    version = core.confirm_dataset(
        confirmation(connection_path, feature_path, label_path)
    )
    overview = core.get_dataset_overview(connection_path)

    assert version.dataset_id == "ds-1"
    assert version.created_by == "alice"
    assert overview == version
    assert (repository_path / version.asset_path).is_file()


def test_domain_core_can_select_an_explicit_dataset_version(tmp_path):
    core, _, connection_path = core_and_workspace(tmp_path)
    feature_path, label_path = write_pair(tmp_path)
    first = core.confirm_dataset(
        confirmation(connection_path, feature_path, label_path)
    )
    labels = pd.read_csv(label_path)
    labels["group"] = ["control", "control", "case", "case"]
    labels.to_csv(label_path, index=False)
    second = core.confirm_dataset(
        confirmation(
            connection_path,
            feature_path,
            label_path,
            dataset_id=first.dataset_id,
        )
    )

    selected = core.get_dataset_overview(
        connection_path,
        dataset_id=first.dataset_id,
        version=1,
    )

    assert second.version == 2
    assert selected == first


def test_domain_core_reports_no_overview_before_confirmation(tmp_path):
    core, _, connection_path = core_and_workspace(tmp_path)

    assert core.get_dataset_overview(connection_path) is None


def test_domain_core_rejects_confirmation_without_valid_workspace(tmp_path):
    feature_path, label_path = write_pair(tmp_path)

    with pytest.raises(WorkspaceError) as caught:
        DomainCore().confirm_dataset(
            confirmation(
                tmp_path / "missing-workspace.json",
                feature_path,
                label_path,
            )
        )

    assert caught.value.code == "invalid_connection"
    assert not (tmp_path / "datasets").exists()

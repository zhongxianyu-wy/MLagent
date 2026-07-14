import json
from pathlib import Path

import pandas as pd

from src.agent.main import main
from src.domain.core import DomainCore
from src.domain.models import BootstrapMemoryCommand


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


def configured_core(tmp_path):
    core = DomainCore(
        id_factory=lambda: "tmr-1",
        dataset_id_factory=lambda: "ds-1",
        clock=lambda: "2026-07-14T00:00:00Z",
    )
    connection_path = tmp_path / ".mlagent-workspace.json"
    core.bootstrap_memory(
        BootstrapMemoryCommand(
            repository_path=tmp_path / "team-memory",
            actor_id="alice",
            connection_path=connection_path,
        )
    )
    return core, connection_path


def test_intake_data_cli_returns_pending_inspection_without_confirmation(
    tmp_path,
    capsys,
):
    feature_path, label_path = write_pair(tmp_path)

    exit_code = main(
        ["intake-data", str(feature_path), str(label_path)],
        domain_core_factory=lambda: DomainCore(),
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "Pending confirmation"
    assert payload["inferred_task_type"] == "binary"
    assert payload["unresolved_fields"] == [
        "positive_class",
        "primary_metric",
        "split_strategy",
        "target_metric",
    ]


def test_intake_data_cli_confirms_dataset_version_through_domain_core(
    tmp_path,
    capsys,
):
    core, connection_path = configured_core(tmp_path)
    feature_path, label_path = write_pair(tmp_path)

    exit_code = main(
        [
            "intake-data",
            str(feature_path),
            str(label_path),
            "--confirm",
            "--workspace-config",
            str(connection_path),
            "--sample-id",
            "sample_id",
            "--label-column",
            "group",
            "--task",
            "binary",
            "--positive-class",
            "case",
            "--metric",
            "roc_auc",
            "--split-strategy",
            "train_only",
            "--target",
            "0.9",
            "--random-seed",
            "0",
        ],
        domain_core_factory=lambda: core,
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["asset_type"] == "dataset_version"
    assert payload["asset_id"] == "ds-1-v0001"
    assert payload["state"] == "confirmed"
    assert payload["random_seed"] == 0
    assert core.get_dataset_overview(connection_path).asset_id == payload["asset_id"]


def test_intake_data_cli_returns_actionable_error_for_unsupported_task(
    tmp_path,
    capsys,
):
    core, connection_path = configured_core(tmp_path)
    feature_path, label_path = write_pair(tmp_path)

    exit_code = main(
        [
            "intake-data",
            str(feature_path),
            str(label_path),
            "--confirm",
            "--workspace-config",
            str(connection_path),
            "--sample-id",
            "sample_id",
            "--label-column",
            "group",
            "--task",
            "regression",
            "--metric",
            "rmse",
            "--split-strategy",
            "train_only",
            "--target",
            "0.1",
        ],
        domain_core_factory=lambda: core,
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["status"] == "Failed"
    assert payload["error"]["code"] == "unsupported_task"
    assert payload["error"]["next_action"]


def test_intake_data_cli_requires_both_input_paths(capsys):
    exit_code = main(["intake-data", "features.csv"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["error"]["code"] == "missing_dataset_paths"


def test_intake_data_cli_returns_nonzero_for_structural_blockers(tmp_path, capsys):
    feature_path = tmp_path / "features.csv"
    label_path = tmp_path / "labels.csv"
    pd.DataFrame(
        {"sample_id": ["s1", "s2"], "f1": [1, 2]}
    ).to_csv(feature_path, index=False)
    pd.DataFrame(
        {"sample_id": ["s1", "s3"], "group": ["case", "control"]}
    ).to_csv(label_path, index=False)

    exit_code = main(["intake-data", str(feature_path), str(label_path)])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["status"] == "Failed"
    assert payload["blockers"] == ["sample_mismatch"]

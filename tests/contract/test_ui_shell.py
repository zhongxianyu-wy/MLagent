from pathlib import Path

from src.domain.models import (
    CapacityStatus,
    DatasetPreview,
    DatasetVersionSnapshot,
    RemoteStatus,
    WorkspaceSnapshot,
)
from src.ui.shell import GLOBAL_STATUS_VOCABULARY, NAVIGATION, build_shell_state


def workspace_snapshot() -> WorkspaceSnapshot:
    return WorkspaceSnapshot(
        repository_id="tmr-1",
        schema_version=1,
        repository_path=Path("/tmp/team-memory"),
        actor_id="alice",
        managed_paths=("datasets", "runs"),
        index_path=Path("/tmp/team-memory/.mlagent-local/index.sqlite3"),
        indexed_assets=1,
        git_state="initialized",
        remote=RemoteStatus(
            state="reachable",
            url="/tmp/team-memory.git",
            message="Origin is reachable.",
        ),
        capacity=CapacityStatus(
            state="ok",
            bytes_used=120,
            largest_file_bytes=80,
            max_file_bytes=100_000_000,
            max_repository_bytes=20_000_000_000,
        ),
        ready=True,
        issues=(),
    )


def dataset_version() -> DatasetVersionSnapshot:
    return DatasetVersionSnapshot(
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
        source_files=(),
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
        feature_count=2,
        dtypes={"f1": "float64", "f2": "int64"},
        missing_rates={"f1": 0.0, "f2": 0.0},
        class_distribution={"case": 6, "control": 6},
        preview=DatasetPreview(
            columns=("sample_id", "f1", "f2", "group"),
            rows=(("s1", 0.1, 1, "case"),),
            omitted_count=2,
        ),
        warnings=(),
        files={
            "features": "features.csv",
            "labels": "labels.csv",
            "split": "split.csv",
        },
    )


def test_shell_has_exactly_six_primary_modules_and_context_fields():
    shell = build_shell_state(workspace_snapshot())

    assert NAVIGATION == (
        "Code Review",
        "Dataset Overview",
        "Run Status",
        "SOP Overview",
        "Experience Review",
        "Lineage Trace",
    )
    assert shell.navigation == NAVIGATION
    assert tuple(shell.context) == ("workspace", "dataset", "run", "git", "writer")
    assert shell.context == {
        "workspace": "tmr-1",
        "dataset": "Not started",
        "run": "Not started",
        "git": "Success",
        "writer": "alice",
    }


def test_shell_exposes_the_approved_global_status_vocabulary():
    assert GLOBAL_STATUS_VOCABULARY == (
        "Not started",
        "Pending confirmation",
        "Running",
        "Success",
        "Failed",
        "Pending review",
        "Approved",
        "Rejected",
        "Pending sync",
        "Conflict",
    )


def test_shell_uses_confirmed_dataset_version_in_context_and_module_status():
    shell = build_shell_state(workspace_snapshot(), dataset_version())

    assert shell.context["dataset"] == "ds-1 v1"
    assert shell.module_status["Dataset Overview"] == "Success"
    assert shell.dataset == dataset_version()

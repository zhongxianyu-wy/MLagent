import hashlib
import io
from pathlib import Path
from time import perf_counter

import pandas as pd
from streamlit.testing.v1 import AppTest

from src.domain.core import DomainCore
from src.domain.dataset_intake import (
    NormalizedDataset,
    dataset_semantic_fingerprint,
)
from src.domain.dataset_repository import DatasetRepository
from src.domain.models import (
    BootstrapMemoryCommand,
    ConfirmDatasetCommand,
    DatasetPreview,
)


def write_pair(root: Path, sample_count: int = 12):
    sample_ids = [f"s{index:05d}" for index in range(sample_count)]
    feature_path = root / "features.csv"
    label_path = root / "labels.csv"
    pd.DataFrame(
        {
            "sample_id": sample_ids,
            "f1": [index / 10 for index in range(sample_count)],
            "f2": list(range(sample_count)),
        }
    ).to_csv(feature_path, index=False)
    pd.DataFrame(
        {
            "sample_id": sample_ids,
            "group": [
                "case" if index < sample_count / 2 else "control"
                for index in range(sample_count)
            ],
        }
    ).to_csv(label_path, index=False)
    return feature_path, label_path


def test_dataset_overview_renders_confirmed_structure_and_bounded_preview(
    tmp_path,
    monkeypatch,
):
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
    feature_path, label_path = write_pair(tmp_path)
    core.confirm_dataset(
        ConfirmDatasetCommand(
            connection_path=connection_path,
            feature_path=feature_path,
            label_path=label_path,
            sample_id_col="sample_id",
            label_col="group",
            task_type="binary",
            positive_class="case",
            primary_metric="roc_auc",
            split_strategy="train_only",
            target_metric=0.9,
        )
    )
    monkeypatch.setenv("MLAGENT_WORKSPACE_CONFIG", str(connection_path))

    app = AppTest.from_file(
        Path("src/ui/app.py").resolve(),
        default_timeout=5,
    ).run()
    app.sidebar.radio[0].set_value("Dataset Overview").run()

    assert not app.exception
    metrics = {(metric.label, metric.value) for metric in app.metric}
    assert ("Dataset", "ds-1 v1") in metrics
    assert ("Samples", "12") in metrics
    assert ("Features", "2") in metrics
    assert ("Task", "binary") in metrics
    assert app.subheader[0].value == "Dataset Overview"
    preview = app.dataframe[0].value
    assert len(preview) == 11
    assert preview.iloc[5].tolist() == ["...", "...", "...", "..."]
    fields = app.dataframe[1].value
    assert list(fields["Field"]) == ["f1", "f2"]
    assert any("roc_auc" in caption.value for caption in app.caption)
    assert any("case" in dataframe.value.columns for dataframe in app.dataframe[2:])


def test_dataset_overview_is_not_started_before_inspection(tmp_path, monkeypatch):
    core = DomainCore(id_factory=lambda: "tmr-1")
    connection_path = tmp_path / ".mlagent-workspace.json"
    core.bootstrap_memory(
        BootstrapMemoryCommand(
            repository_path=tmp_path / "team-memory",
            actor_id="alice",
            connection_path=connection_path,
        )
    )
    monkeypatch.setenv("MLAGENT_WORKSPACE_CONFIG", str(connection_path))

    app = AppTest.from_file(
        Path("src/ui/app.py").resolve(),
        default_timeout=5,
    ).run()
    app.sidebar.radio[0].set_value("Dataset Overview").run()

    assert not app.exception
    metrics = {(metric.label, metric.value) for metric in app.metric}
    assert ("Dataset", "Not started") in metrics
    assert any(caption.value == "Not started" for caption in app.caption)
    assert len(app.text_input) == 2
    assert any("no dataset selected" in info.value.lower() for info in app.info)


def test_dataset_overview_renders_pending_inspection(tmp_path, monkeypatch):
    core = DomainCore(id_factory=lambda: "tmr-1")
    connection_path = tmp_path / ".mlagent-workspace.json"
    core.bootstrap_memory(
        BootstrapMemoryCommand(
            repository_path=tmp_path / "team-memory",
            actor_id="alice",
            connection_path=connection_path,
        )
    )
    feature_path, label_path = write_pair(tmp_path)
    monkeypatch.setenv("MLAGENT_WORKSPACE_CONFIG", str(connection_path))

    app = AppTest.from_file(
        Path("src/ui/app.py").resolve(),
        default_timeout=5,
    ).run()
    app.sidebar.radio[0].set_value("Dataset Overview").run()
    app.text_input[0].set_value(str(feature_path))
    app.text_input[1].set_value(str(label_path))
    app.button[0].click().run()

    assert not app.exception
    metrics = {(metric.label, metric.value) for metric in app.metric}
    assert ("Dataset", "Pending confirmation") in metrics
    assert ("Samples", "12") in metrics
    assert ("Features", "2") in metrics
    assert ("Task", "binary") in metrics
    assert any(
        caption.value == "Pending confirmation" for caption in app.caption
    )
    assert len(app.dataframe[0].value) == 11
    assert any("positive_class" in warning.value for warning in app.warning)


def test_dataset_overview_first_view_stays_within_budget_for_80_mb_asset(
    tmp_path,
    monkeypatch,
):
    core = DomainCore(id_factory=lambda: "tmr-1")
    connection_path = tmp_path / ".mlagent-workspace.json"
    workspace = core.bootstrap_memory(
        BootstrapMemoryCommand(
            repository_path=tmp_path / "team-memory",
            actor_id="alice",
            connection_path=connection_path,
        )
    )
    normalized = large_normalized_dataset(sample_count=40_000, feature_count=1_000)
    assert 80_000_000 < len(normalized.feature_bytes) < 100_000_000
    DatasetRepository(
        workspace.repository_path,
        id_factory=lambda: "ds-large",
    ).create_version(
        normalized,
        actor_id="alice",
        capacity=workspace.capacity,
    )
    monkeypatch.setenv("MLAGENT_WORKSPACE_CONFIG", str(connection_path))

    started = perf_counter()
    app = AppTest.from_file(
        Path("src/ui/app.py").resolve(),
        default_timeout=5,
    ).run()
    app.sidebar.radio[0].set_value("Dataset Overview").run()
    elapsed = perf_counter() - started

    assert not app.exception
    assert any(
        metric.label == "Samples" and metric.value == "40000"
        for metric in app.metric
    )
    assert elapsed < 3


def large_normalized_dataset(
    sample_count: int,
    feature_count: int,
) -> NormalizedDataset:
    feature_buffer = io.BytesIO()
    feature_buffer.write(
        (
            "sample_id,"
            + ",".join(f"f{index}" for index in range(feature_count))
            + "\n"
        ).encode()
    )
    feature_values = (",".join("0" for _ in range(feature_count)) + "\n").encode()
    label_buffer = io.BytesIO()
    label_buffer.write(b"sample_id,group\n")
    split_buffer = io.BytesIO()
    split_buffer.write(b"sample_id,partition\n")
    for index in range(sample_count):
        sample_id = f"s{index:05d}"
        feature_buffer.write(sample_id.encode() + b"," + feature_values)
        label = "case" if index < sample_count // 2 else "control"
        label_buffer.write(f"{sample_id},{label}\n".encode())
        split_buffer.write(f"{sample_id},train\n".encode())
    feature_bytes = feature_buffer.getvalue()
    label_bytes = label_buffer.getvalue()
    split_bytes = split_buffer.getvalue()
    content_fingerprint = hashlib.sha256(
        feature_bytes + b"\0" + label_bytes
    ).hexdigest()
    split_fingerprint = hashlib.sha256(split_bytes).hexdigest()
    source_files = (
        {
            "role": "features",
            "name": "features.csv",
            "sha256": hashlib.sha256(feature_bytes).hexdigest(),
        },
        {
            "role": "labels",
            "name": "labels.csv",
            "sha256": hashlib.sha256(label_bytes).hexdigest(),
        },
    )
    semantics = {
        "content_fingerprint": content_fingerprint,
        "split_fingerprint": split_fingerprint,
        "source_files": source_files,
        "sample_id_col": "sample_id",
        "label_col": "group",
        "task_type": "binary",
        "class_labels": ("case", "control"),
        "positive_class": "case",
        "primary_metric": "roc_auc",
        "target_metric": 0.9,
        "split_strategy": "train_only",
        "test_ratio": None,
        "random_seed": 42,
    }
    dtypes = {f"f{index}": "int64" for index in range(feature_count)}
    return NormalizedDataset(
        feature_bytes=feature_bytes,
        label_bytes=label_bytes,
        split_bytes=split_bytes,
        content_fingerprint=content_fingerprint,
        split_fingerprint=split_fingerprint,
        version_fingerprint=dataset_semantic_fingerprint(semantics),
        source_files=source_files,
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
        sample_count=sample_count,
        feature_count=feature_count,
        dtypes=dtypes,
        missing_rates={field: 0.0 for field in dtypes},
        class_distribution={"case": sample_count // 2, "control": sample_count // 2},
        preview=DatasetPreview(
            columns=("sample_id", "f0", "group"),
            rows=(
                ("s00000", 0, "case"),
                (f"s{sample_count - 1:05d}", 0, "control"),
            ),
            omitted_count=sample_count - 2,
        ),
        warnings=(),
    )

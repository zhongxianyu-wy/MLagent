from pathlib import Path
from time import perf_counter

import pandas as pd
from streamlit.testing.v1 import AppTest

from src.domain.core import DomainCore
from src.domain.dataset_intake import DatasetInspector
from src.domain.models import (
    BootstrapMemoryCommand,
    ConfirmDatasetCommand,
    InspectDatasetCommand,
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


def test_dataset_inspection_first_view_stays_within_local_budget(tmp_path):
    feature_path, label_path = write_pair(tmp_path, sample_count=20_000)

    started = perf_counter()
    inspection = DatasetInspector().inspect(
        InspectDatasetCommand(feature_path=feature_path, label_path=label_path)
    )
    elapsed = perf_counter() - started

    assert inspection.sample_count == 20_000
    assert inspection.preview.omitted_count == 19_990
    assert elapsed < 3

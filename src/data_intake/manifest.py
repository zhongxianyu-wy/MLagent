from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from src.data_intake.explorer import IntakeInspection
from src.data_intake.splitter import deterministic_split_indices
from src.models import DatasetManifest


def build_manifest_from_inspection(
    inspection: IntakeInspection,
    output_root: str,
    split_strategy: str = "train_only",
    split_ratio: float | None = None,
    random_seed: int | None = None,
) -> DatasetManifest:
    if not inspection.ready:
        raise ValueError("cannot build manifest until intake is ready")
    if (
        inspection.sample_id_col is None
        or inspection.label_col is None
        or inspection.positive_label is None
        or inspection.negative_label is None
    ):
        raise ValueError("inspection is missing required dataset fields")

    if split_strategy not in {"train_only", "random"}:
        raise ValueError("split_strategy must be 'train_only' or 'random'")
    if split_strategy == "random" and split_ratio is None:
        raise ValueError("split_ratio is required for random split")
    if split_strategy == "random" and not 0 < float(split_ratio) < 1:
        raise ValueError("split_ratio must be between 0 and 1")

    features = pd.read_csv(inspection.feature_file)
    labels = pd.read_csv(inspection.label_file)
    _validate_sample_alignment(
        features,
        labels,
        sample_id_col=inspection.sample_id_col,
    )

    dataset_dir = Path(output_root) / inspection.session_id
    dataset_dir.mkdir(parents=True, exist_ok=True)
    train_feature_path = dataset_dir / "train_features.csv"
    train_label_path = dataset_dir / "train_labels.csv"
    test_feature_path = None
    test_label_path = None

    features = features.set_index(inspection.sample_id_col, drop=False)
    labels = labels.set_index(inspection.sample_id_col, drop=False)
    labels = labels.loc[features.index]

    if split_strategy == "random":
        train_indices, test_indices = deterministic_split_indices(
            n_samples=len(features),
            test_ratio=float(split_ratio),
            seed=int(random_seed or 0),
        )
        train_features = features.iloc[train_indices]
        train_labels = labels.iloc[train_indices]
        test_features = features.iloc[test_indices]
        test_labels = labels.iloc[test_indices]
        test_feature_path = dataset_dir / "test_features.csv"
        test_label_path = dataset_dir / "test_labels.csv"
        test_features.to_csv(test_feature_path, index=False)
        test_labels.to_csv(test_label_path, index=False)
    else:
        train_features = features
        train_labels = labels

    train_features.to_csv(train_feature_path, index=False)
    train_labels.to_csv(train_label_path, index=False)

    manifest = DatasetManifest(
        dataset_id=inspection.session_id,
        source_paths=[inspection.source_path],
        sample_id_col=inspection.sample_id_col,
        label_col=inspection.label_col,
        positive_label=inspection.positive_label,
        negative_label=inspection.negative_label,
        train_feature_path=str(train_feature_path),
        train_label_path=str(train_label_path),
        test_feature_path=str(test_feature_path) if test_feature_path is not None else None,
        test_label_path=str(test_label_path) if test_label_path is not None else None,
        split_strategy=split_strategy,
        split_ratio=split_ratio,
        random_seed=random_seed,
        notes="standardized from user-provided feature and label files",
    )
    (dataset_dir / "manifest.json").write_text(
        json.dumps(asdict(manifest), ensure_ascii=False, indent=2)
    )
    (dataset_dir / "intake_report.md").write_text(
        "\n".join(
            [
                f"# Intake Report: {inspection.session_id}",
                "",
                f"- Source path: {inspection.source_path}",
                f"- Split strategy: {split_strategy}",
                f"- Train samples: {len(train_labels)}",
                f"- Test samples: {0 if test_label_path is None else len(test_labels)}",
            ]
        )
        + "\n"
    )
    return manifest


def _validate_sample_alignment(
    features: pd.DataFrame,
    labels: pd.DataFrame,
    sample_id_col: str,
) -> None:
    if sample_id_col not in features.columns or sample_id_col not in labels.columns:
        raise ValueError(f"sample id column '{sample_id_col}' must exist in both files")
    feature_ids = set(features[sample_id_col])
    label_ids = set(labels[sample_id_col])
    missing_labels = sorted(feature_ids - label_ids)
    missing_features = sorted(label_ids - feature_ids)
    if missing_labels or missing_features:
        raise ValueError(
            "sample ids are not aligned; "
            f"missing labels={missing_labels}; missing features={missing_features}"
        )

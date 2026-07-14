from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.models import DatasetManifest


@dataclass(frozen=True)
class LoadedDataset:
    manifest: DatasetManifest
    feature_names: list[str]
    train_x: list[list[float]]
    train_y: list[int]


def load_dataset_from_manifest(manifest_path: str) -> LoadedDataset:
    payload = json.loads(Path(manifest_path).read_text())
    manifest = DatasetManifest(**payload)
    features = pd.read_csv(manifest.train_feature_path)
    labels = pd.read_csv(manifest.train_label_path)
    features = features.set_index(manifest.sample_id_col, drop=False)
    labels = labels.set_index(manifest.sample_id_col, drop=False).loc[features.index]
    feature_names = [
        column for column in features.columns if column != manifest.sample_id_col
    ]
    train_x = features[feature_names].astype(float).values.tolist()
    train_y = [
        1 if value == manifest.positive_label else 0
        for value in labels[manifest.label_col].tolist()
    ]
    return LoadedDataset(
        manifest=manifest,
        feature_names=feature_names,
        train_x=train_x,
        train_y=train_y,
    )

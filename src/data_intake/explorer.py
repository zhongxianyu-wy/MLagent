from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class IntakeInspection:
    session_id: str
    source_path: str
    feature_file: str
    label_file: str
    sample_id_col: str | None
    label_col: str | None
    positive_label: str | None
    negative_label: str | None
    ready: bool
    unresolved_questions: list[str]


def inspect_path(path: str) -> IntakeInspection:
    root = Path(path)
    csv_files = sorted(root.glob("*.csv"))
    feature_file = _pick_file(csv_files, ("feature", "matrix"))
    label_file = _pick_file(csv_files, ("label", "group"))
    if feature_file is None or label_file is None:
        raise ValueError("path must contain feature/matrix and label/group csv files")

    feature_header = _header(feature_file)
    label_header = _header(label_file)
    sample_id_col = _first_matching(feature_header, ("sample_id", "id"))
    label_sample_col = _first_matching(label_header, ("sample_id", "id"))
    label_col = _first_non_id(label_header)
    labels = _unique_values(label_file, label_col)

    clear = (
        feature_file.name == "features.csv"
        and label_file.name == "labels.csv"
        and sample_id_col == label_sample_col == "sample_id"
        and label_col == "group"
    )
    if clear:
        return IntakeInspection(
            session_id=root.name,
            source_path=str(root),
            feature_file=str(feature_file),
            label_file=str(label_file),
            sample_id_col=sample_id_col,
            label_col=label_col,
            positive_label=labels[0],
            negative_label=labels[1],
            ready=True,
            unresolved_questions=[],
        )

    return IntakeInspection(
        session_id=root.name,
        source_path=str(root),
        feature_file=str(feature_file),
        label_file=str(label_file),
        sample_id_col=sample_id_col,
        label_col=label_col,
        positive_label=None,
        negative_label=None,
        ready=False,
        unresolved_questions=[
            f"请确认标签列：{label_file.name} 中是否使用 {label_col} 作为分组标签？"
        ],
    )


def _pick_file(files: list[Path], keywords: tuple[str, ...]) -> Path | None:
    for file in files:
        if any(keyword in file.stem.lower() for keyword in keywords):
            return file
    return None


def _header(path: Path) -> list[str]:
    with path.open(newline="") as handle:
        return next(csv.reader(handle))


def _first_matching(values: list[str], candidates: tuple[str, ...]) -> str | None:
    for candidate in candidates:
        if candidate in values:
            return candidate
    return None


def _first_non_id(values: list[str]) -> str:
    for value in values:
        if value not in {"sample_id", "id"}:
            return value
    raise ValueError("label file must contain a non-id label column")


def _unique_values(path: Path, column: str) -> list[str]:
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        values = []
        for row in reader:
            value = row[column]
            if value not in values:
                values.append(value)
        return values

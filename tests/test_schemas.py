from pathlib import Path

import pytest
from pydantic import ValidationError

from mlagent_memory.io import read_yaml, sha256_file, write_yaml
from mlagent_memory.schemas import ExperienceRecord, RawMemoryRecord, SkillVersion


def test_raw_memory_requires_known_type():
    record = RawMemoryRecord(
        id="raw_20260622_001",
        type="run",
        created_at="2026-06-22T10:00:00+08:00",
        session_id="session_20260622_001",
        goal="Improve AUC",
    )
    assert record.type == "run"


def test_experience_requires_confidence_and_source():
    record = ExperienceRecord(
        id="exp_20260622_001",
        type="pitfall",
        summary="Leakage appeared when target-derived fields were kept.",
        detail="Remove target-derived fields before feature selection.",
        confidence="medium",
        needs_review=True,
        source_raw_records=["raw_memory/runs/raw_20260622_001.yaml"],
        created_at="2026-06-22T10:30:00+08:00",
    )
    assert record.object_type == "experience"


def test_skill_version_rejects_unreviewed_approved_state():
    with pytest.raises(ValidationError):
        SkillVersion(
            version="v001",
            name="baseline",
            object_type="skill_version",
            state="approved",
            source_type="best_run",
            source_evidence=[],
            human_review={"reviewed": False},
            performance={"primary_metric": {"name": "auc", "value": 0.91}},
            reproducibility={"entrypoint": "train.py"},
        )


def test_yaml_round_trip_and_hash(tmp_path):
    path = tmp_path / "record.yaml"
    write_yaml(path, {"id": "abc", "items": [1, 2]})
    assert read_yaml(path) == {"id": "abc", "items": [1, 2]}
    assert len(sha256_file(path)) == 64


import math

import pytest
from pydantic import ValidationError

from mlagent_memory.schemas import BenchmarkMetric, Performance, PrimaryMetric


def test_performance_rejects_empty_strings():
    with pytest.raises(ValidationError):
        Performance(primary_metric={"name": "", "value": 0.9}, dataset_version="d1", validation_protocol="holdout")
    with pytest.raises(ValidationError):
        Performance(primary_metric={"name": "auc", "value": 0.9}, dataset_version="", validation_protocol="holdout")
    with pytest.raises(ValidationError):
        Performance(primary_metric={"name": "auc", "value": 0.9}, dataset_version="d1", validation_protocol="")


def test_performance_rejects_non_finite_values():
    for bad in [float("nan"), float("inf"), float("-inf")]:
        with pytest.raises(ValidationError):
            PrimaryMetric(name="auc", value=bad)
        with pytest.raises(ValidationError):
            BenchmarkMetric(name="base", value=bad)


def test_performance_accepts_valid_complete_data():
    p = Performance(
        primary_metric={"name": "auc", "value": 0.91},
        dataset_version="data_v001",
        validation_protocol="holdout",
        benchmark_metric={"name": "baseline_auc", "value": 0.86},
    )
    assert p.primary_metric.value == 0.91

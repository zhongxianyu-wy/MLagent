from mlagent_memory.experience import add_experience
from mlagent_memory.io import read_yaml
from mlagent_memory.raw import add_raw_memory
from mlagent_memory.repo import init_memory_repo


def test_add_raw_memory_writes_record_to_type_directory(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    record = add_raw_memory(
        root,
        {
            "id": "raw_001",
            "type": "run",
            "created_at": "2026-06-22T10:00:00+08:00",
            "session_id": "session_001",
            "goal": "Improve AUC",
        },
    )
    path = root / "raw_memory/runs/raw_001.yaml"
    assert path.exists()
    assert read_yaml(path)["id"] == record.id


def test_add_experience_writes_record_to_type_directory(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    record = add_experience(
        root,
        {
            "id": "exp_001",
            "type": "lesson",
            "summary": "Remove leakage fields",
            "detail": "Post outcome fields must be excluded.",
            "confidence": "high",
            "needs_review": False,
            "source_raw_records": ["raw_memory/runs/raw_001.yaml"],
            "created_at": "2026-06-22T10:30:00+08:00",
        },
    )
    path = root / "experience/lessons/exp_001.yaml"
    assert path.exists()
    assert read_yaml(path)["id"] == record.id


import pytest
from mlagent_memory.errors import RecordExists


def test_add_raw_rejects_duplicate_unless_replace(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    payload = {"id": "r1", "type": "run", "created_at": "2026-06-22T10:00:00+08:00", "goal": "first"}
    add_raw_memory(root, payload)
    with pytest.raises(RecordExists):
        add_raw_memory(root, payload)
    add_raw_memory(root, {**payload, "goal": "second"}, replace=True)
    assert read_yaml(root / "raw_memory/runs/r1.yaml")["goal"] == "second"


def test_add_experience_rejects_duplicate_unless_replace(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    payload = {"id": "e1", "type": "lesson", "summary": "s", "detail": "d", "confidence": "high", "needs_review": False, "source_raw_records": ["raw_memory/runs/r1.yaml"], "created_at": "2026-06-22T10:30:00+08:00"}
    add_experience(root, payload)
    with pytest.raises(RecordExists):
        add_experience(root, payload)
    add_experience(root, {**payload, "summary": "s2"}, replace=True)
    assert read_yaml(root / "experience/lessons/e1.yaml")["summary"] == "s2"


def test_add_raw_from_yaml_with_unquoted_timestamp(tmp_path):
    # PyYAML auto-parses bare ISO timestamps to datetime; read_yaml must keep them as str
    # so the record schema (created_at: str) accepts a user-authored YAML record.
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    record_file = tmp_path / "run.yaml"
    record_file.write_text(
        "id: raw_ts\n"
        "type: run\n"
        "created_at: 2026-06-23T10:00:00+08:00\n"
        "session_id: s1\n"
        "goal: g\n",
        encoding="utf-8",
    )
    data = read_yaml(record_file)
    assert isinstance(data["created_at"], str)
    record = add_raw_memory(root, data)
    assert record.created_at == "2026-06-23T10:00:00+08:00"


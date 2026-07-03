import pytest

from mlagent.errors import RecordExists
from mlagent.experience import add_experience
from mlagent.io import read_yaml
from mlagent.raw import add_raw_memory
from mlagent.repo import init_memory_repo


def _raw_payload():
    return {
        "id": "raw_001",
        "type": "run",
        "created_at": "2026-07-03T10:00:00+08:00",
        "goal": "Improve AUC",
        "conclusion": {"hypothesis": "top-50 helps", "outcome": "confirmed", "summary": "auc +0.03"},
    }


def test_add_raw_routes_by_type_and_keeps_conclusion(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    add_raw_memory(root, _raw_payload())
    path = root / "raw_memory/runs/raw_001.yaml"
    assert path.exists()
    data = read_yaml(path)
    assert data["conclusion"]["outcome"] == "confirmed"


def test_add_raw_rejects_duplicate_unless_replace(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    add_raw_memory(root, _raw_payload())
    with pytest.raises(RecordExists):
        add_raw_memory(root, _raw_payload())
    add_raw_memory(root, {**_raw_payload(), "goal": "v2"}, replace=True)
    assert read_yaml(root / "raw_memory/runs/raw_001.yaml")["goal"] == "v2"


def test_add_experience_convention_routes_to_conventions(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    add_experience(
        root,
        {
            "id": "exp_conv",
            "type": "convention",
            "summary": "Use 10-fold StratifiedKFold",
            "confidence": "high",
            "needs_review": False,
            "source_raw_records": ["raw_memory/runs/raw_001.yaml"],
            "created_at": "2026-07-03T10:30:00+08:00",
            "derived_from": ["raw://raw_001"],
        },
    )
    assert (root / "experience/conventions/exp_conv.yaml").exists()


def test_add_experience_rejects_duplicate(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    payload = {
        "id": "e1",
        "type": "pitfall",
        "summary": "s",
        "confidence": "medium",
        "needs_review": True,
        "source_raw_records": [],
        "created_at": "2026-07-03T10:30:00+08:00",
    }
    add_experience(root, payload)
    with pytest.raises(RecordExists):
        add_experience(root, payload)


def test_cli_record_raw_and_add_experience(tmp_path):
    from typer.testing import CliRunner
    from mlagent.cli import app

    runner = CliRunner()
    root = tmp_path / "project_memory"
    runner.invoke(app, ["init", "--memory-root", str(root), "--project-name", "demo"], catch_exceptions=False)

    raw_yaml = tmp_path / "raw.yaml"
    raw_yaml.write_text(
        "id: raw_001\ntype: run\ncreated_at: 2026-07-03T10:00:00+08:00\ngoal: g\n"
        "conclusion:\n  hypothesis: h\n  outcome: confirmed\n  summary: s\n",
        encoding="utf-8",
    )
    r = runner.invoke(app, ["record-raw", str(raw_yaml), "--memory-root", str(root)])
    assert r.exit_code == 0 and "raw_001" in r.stdout

    exp_yaml = tmp_path / "exp.yaml"
    exp_yaml.write_text(
        "id: exp_001\ntype: pitfall\nsummary: s\ndetail: d\nconfidence: high\nneeds_review: false\n"
        "source_raw_records: []\ncreated_at: 2026-07-03T10:30:00+08:00\n",
        encoding="utf-8",
    )
    r = runner.invoke(app, ["add-experience", str(exp_yaml), "--memory-root", str(root)])
    assert r.exit_code == 0 and "exp_001" in r.stdout

    # duplicate -> exit 2
    dup = runner.invoke(app, ["record-raw", str(raw_yaml), "--memory-root", str(root)])
    assert dup.exit_code == 2

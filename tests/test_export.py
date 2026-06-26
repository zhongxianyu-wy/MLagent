import json

from mlagent_memory.export import export_memory_snapshot
from mlagent_memory.experience import add_experience
from mlagent_memory.io import write_yaml
from mlagent_memory.raw import add_raw_memory
from mlagent_memory.repo import init_memory_repo
from mlagent_memory.skill_versions import approve_skill_candidate, create_skill_candidate


def _seed(root):
    add_raw_memory(
        root,
        {
            "id": "run_001",
            "type": "run",
            "created_at": "2026-06-24T10:00:00+08:00",
            "session_id": "session_001",
            "goal": "GBC baseline",
            "commands": [{"command": "python train.py", "summary": "ok", "status": "success"}],
            "results": {"auc": 0.88, "logloss": 0.31, "note": "baseline"},
        },
    )
    add_raw_memory(
        root,
        {
            "id": "run_002",
            "type": "run",
            "created_at": "2026-06-25T10:00:00+08:00",
            "session_id": "session_001",
            "goal": "add feature selection",
            "results": {"auc": 0.91},
        },
    )
    add_experience(
        root,
        {
            "id": "exp_001",
            "type": "pitfall",
            "summary": "leakage pitfall",
            "detail": "d",
            "confidence": "high",
            "needs_review": False,
            "source_raw_records": ["raw_memory/runs/run_001.yaml"],
            "created_at": "2026-06-24T11:00:00+08:00",
        },
    )


def test_export_snapshot_structure(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    _seed(root)
    snap = export_memory_snapshot(root)

    assert set(snap) >= {"project", "data_understanding", "knowledge", "runs", "experience",
                         "skills", "links", "timeline", "metric_series"}
    assert snap["project"]["name"] == "demo"
    assert snap["data_understanding"]["has_dataset_card"] is True
    assert len(snap["runs"]) == 2
    assert {r["id"] for r in snap["runs"]} == {"run_001", "run_002"}
    # experience grouped
    assert [e["id"] for e in snap["experience"]["pitfall"]] == ["exp_001"]
    # metric series extracted (only numeric values)
    assert {m["run_id"] for m in snap["metric_series"]["auc"]} == {"run_001", "run_002"}
    assert "logloss" in snap["metric_series"]
    assert "note" not in snap["metric_series"]  # non-numeric excluded
    # links: experience -> run, run -> session
    kinds = {l["kind"] for l in snap["links"]}
    assert "experience_derives_from" in kinds
    assert "run_in_session" in kinds
    # timeline sorted chronologically
    ts = [e["ts"] for e in snap["timeline"]]
    assert ts == sorted(ts)


def test_export_includes_approved_and_candidate_skills(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    create_skill_candidate(root, version="v001", name="b", source_type="best_run", source_evidence=["raw_memory/runs/r.yaml"])
    perf = tmp_path / "p.yaml"
    write_yaml(perf, {"primary_metric": {"name": "auc", "value": 0.91}, "dataset_version": "d1", "validation_protocol": "holdout"})
    approve_skill_candidate(root, version="v001", reviewer="human", approval_note="ok", performance_path=perf)
    create_skill_candidate(root, version="v002", name="c", source_type="best_run", source_evidence=["raw_memory/runs/r2.yaml"])

    snap = export_memory_snapshot(root)
    assert [s["version"] for s in snap["skills"]["approved"]] == ["v001"]
    assert {s["version"] for s in snap["skills"]["candidates"]} == {"v002"}
    # skill evidence link
    assert any(l["kind"] == "skill_evidence" and l["source"] == "skill:v002" for l in snap["links"])


def test_export_missing_repo_raises(tmp_path):
    from mlagent_memory.errors import MemoryRepoNotFound
    import pytest
    with pytest.raises(MemoryRepoNotFound):
        export_memory_snapshot(tmp_path / "nope")


def test_cli_export(tmp_path):
    from typer.testing import CliRunner
    from mlagent_memory.cli import app
    root = tmp_path / "project_memory"
    runner = CliRunner()
    runner.invoke(app, ["init", "--memory-root", str(root), "--project-name", "demo"], catch_exceptions=False)
    result = runner.invoke(app, ["export", "--memory-root", str(root)])
    assert result.exit_code == 0
    out = root / "snapshot.json"
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["project"]["name"] == "demo"


def test_cli_export_stdout_and_output(tmp_path):
    from typer.testing import CliRunner
    from mlagent_memory.cli import app
    root = tmp_path / "project_memory"
    runner = CliRunner()
    runner.invoke(app, ["init", "--memory-root", str(root), "--project-name", "demo"], catch_exceptions=False)
    # --stdout prints JSON, no file
    stdout_run = runner.invoke(app, ["export", "--stdout", "--memory-root", str(root)])
    assert stdout_run.exit_code == 0
    assert json.loads(stdout_run.stdout)["project"]["name"] == "demo"
    assert not (root / "snapshot.json").exists()
    # --output custom path
    custom = tmp_path / "out.json"
    custom_run = runner.invoke(app, ["export", "--output", str(custom), "--memory-root", str(root)])
    assert custom_run.exit_code == 0 and custom.exists()

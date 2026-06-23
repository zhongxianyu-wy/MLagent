from typer.testing import CliRunner

from mlagent_memory.cli import app


runner = CliRunner()


def test_cli_version():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "mlagent-memory 0.1.0" in result.stdout


def test_cli_status_requires_existing_memory_repo(tmp_path):
    missing = tmp_path / "project_memory"
    result = runner.invoke(app, ["status", "--memory-root", str(missing)])
    assert result.exit_code == 2
    assert "Project memory repo does not exist" in result.stdout


def test_cli_init_then_status(tmp_path):
    root = tmp_path / "project_memory"
    init_result = runner.invoke(
        app,
        [
            "init",
            "--memory-root",
            str(root),
            "--project-name",
            "demo",
            "--primary-metric",
            "auc",
        ],
    )
    assert init_result.exit_code == 0

    status_result = runner.invoke(app, ["status", "--memory-root", str(root)])
    assert status_result.exit_code == 0
    assert "Project: demo" in status_result.stdout
    assert "Skill versions: 0" in status_result.stdout


def test_cli_end_to_end_memory_flow(tmp_path):
    root = tmp_path / "project_memory"
    source = tmp_path / "note.md"
    source.write_text("# AUC\nAvoid leakage", encoding="utf-8")

    assert runner.invoke(app, ["init", "--memory-root", str(root), "--project-name", "demo"]).exit_code == 0
    assert runner.invoke(app, ["import-knowledge", str(source), "--memory-root", str(root), "--type", "method_note"]).exit_code == 0
    assert runner.invoke(app, ["index", "--memory-root", str(root)]).exit_code == 0
    search = runner.invoke(app, ["search", "leakage", "--memory-root", str(root)])
    assert search.exit_code == 0
    assert "knowledge" in search.stdout


def test_cli_approve_rejects_empty_performance(tmp_path):
    root = tmp_path / "project_memory"
    runner.invoke(
        app,
        ["init", "--memory-root", str(root), "--project-name", "demo"],
        catch_exceptions=False,
    )
    runner.invoke(
        app,
        [
            "create-skill-candidate",
            "--memory-root",
            str(root),
            "--version",
            "v001",
            "--name",
            "baseline",
            "--source-type",
            "best_run",
            "--source-evidence",
            "raw_memory/runs/r.yaml",
        ],
        catch_exceptions=False,
    )
    perf = tmp_path / "perf.yaml"
    perf.write_text("{}", encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "approve-skill",
            "--memory-root",
            str(root),
            "--version",
            "v001",
            "--reviewer",
            "human",
            "--approval-note",
            "ok",
            "--performance-path",
            str(perf),
        ],
    )
    assert result.exit_code == 2
    assert "performance" in result.stdout.lower() or "invalid" in result.stdout.lower()


def test_cli_list_skills_and_get_skill(tmp_path):
    root = tmp_path / "project_memory"
    runner.invoke(app, ["init", "--memory-root", str(root), "--project-name", "demo"], catch_exceptions=False)
    # empty list
    empty = runner.invoke(app, ["list-skills", "--memory-root", str(root)])
    assert empty.exit_code == 0
    assert "No approved" in empty.stdout
    # approve one
    runner.invoke(
        app,
        [
            "create-skill-candidate",
            "--memory-root",
            str(root),
            "--version",
            "v001",
            "--name",
            "baseline",
            "--source-type",
            "best_run",
            "--source-evidence",
            "raw_memory/runs/r.yaml",
        ],
        catch_exceptions=False,
    )
    perf = tmp_path / "perf.yaml"
    perf.write_text(
        "primary_metric:\n  name: auc\n  value: 0.91\ndataset_version: d1\nvalidation_protocol: holdout\n",
        encoding="utf-8",
    )
    runner.invoke(
        app,
        [
            "approve-skill",
            "--memory-root",
            str(root),
            "--version",
            "v001",
            "--reviewer",
            "human",
            "--approval-note",
            "ok",
            "--performance-path",
            str(perf),
        ],
        catch_exceptions=False,
    )
    listed = runner.invoke(app, ["list-skills", "--memory-root", str(root)])
    assert listed.exit_code == 0
    assert "v001" in listed.stdout
    got = runner.invoke(app, ["get-skill", "v001", "--memory-root", str(root)])
    assert got.exit_code == 0
    assert "approved" in got.stdout
    # candidate rejection
    runner.invoke(
        app,
        [
            "create-skill-candidate",
            "--memory-root",
            str(root),
            "--version",
            "v002",
            "--name",
            "draft",
            "--source-type",
            "ipynb_import",
            "--source-evidence",
            "nb.ipynb",
        ],
        catch_exceptions=False,
    )
    rejected = runner.invoke(app, ["get-skill", "v002", "--memory-root", str(root)])
    assert rejected.exit_code == 2

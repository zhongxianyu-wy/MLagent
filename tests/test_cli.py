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

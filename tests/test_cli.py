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

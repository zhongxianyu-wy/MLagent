from typer.testing import CliRunner

from mlagent.cli import app

runner = CliRunner()


def test_cli_version():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "mlagent 0.1.0" in result.stdout

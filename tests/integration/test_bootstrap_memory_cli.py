import json
import subprocess

from src.agent.main import main
from src.domain.core import DomainCore
from src.domain.models import BootstrapMemoryCommand


def test_bootstrap_memory_cli_creates_workspace_via_domain_core(tmp_path, capsys):
    repository_path = tmp_path / "team-memory"
    connection_path = tmp_path / ".mlagent-workspace.json"

    exit_code = main(
        [
            "bootstrap-memory",
            str(repository_path),
            "--actor",
            "alice",
            "--workspace-config",
            str(connection_path),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["ready"] is True
    assert payload["repository_path"] == str(repository_path.resolve())
    assert payload["indexed_assets"] == 1
    assert DomainCore().open_workspace(connection_path).repository_id == payload["repository_id"]


def test_bootstrap_memory_cli_returns_actionable_json_for_invalid_repository(
    tmp_path, capsys
):
    repository_path = tmp_path / "team-memory"
    repository_path.mkdir()
    (repository_path / "unrelated.txt").write_text("keep me")

    exit_code = main(
        [
            "bootstrap-memory",
            str(repository_path),
            "--actor",
            "alice",
            "--workspace-config",
            str(tmp_path / ".mlagent-workspace.json"),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["ready"] is False
    assert payload["error"]["code"] == "unrecognized_repository"
    assert "next_action" in payload["error"]


def test_bootstrap_memory_cli_requires_actor(tmp_path, capsys):
    exit_code = main(["bootstrap-memory", str(tmp_path / "team-memory")])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["error"]["code"] == "missing_actor"


def test_bootstrap_memory_cli_returns_actionable_json_for_unsupported_schema(
    tmp_path,
    capsys,
):
    repository_path = tmp_path / "team-memory"
    DomainCore(
        id_factory=lambda: "tmr-1",
        clock=lambda: "2026-07-14T00:00:00Z",
    ).bootstrap_memory(
        BootstrapMemoryCommand(
            repository_path=repository_path,
            actor_id="alice",
            connection_path=tmp_path / ".mlagent-workspace.json",
        )
    )
    manifest_path = repository_path / ".mlagent/repository.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["schema_version"] = 2
    manifest_path.write_text(json.dumps(manifest))
    subprocess.run(
        ["git", "add", "--", ".mlagent/repository.json"],
        cwd=repository_path,
        capture_output=True,
        text=True,
        check=True,
    )
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=tester",
            "-c",
            "user.email=tester@mlagent.local",
            "commit",
            "-m",
            "test: unsupported schema",
        ],
        cwd=repository_path,
        capture_output=True,
        text=True,
        check=True,
    )

    exit_code = main(
        [
            "bootstrap-memory",
            str(repository_path),
            "--actor",
            "alice",
            "--workspace-config",
            str(tmp_path / ".mlagent-workspace.json"),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["ready"] is False
    assert payload["error"]["code"] == "unsupported_schema"
    assert "next_action" in payload["error"]

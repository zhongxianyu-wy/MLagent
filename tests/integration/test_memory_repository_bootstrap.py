import json
import shutil
import subprocess

import pytest

from src.domain.memory_repository import MANAGED_PATHS, MemoryRepository
from src.domain.models import WorkspaceError


def repository_manager() -> MemoryRepository:
    return MemoryRepository(
        id_factory=lambda: "tmr-1",
        clock=lambda: "2026-07-14T00:00:00Z",
    )


def test_bootstrap_creates_and_reopens_authoritative_git_workspace(tmp_path):
    repository_path = tmp_path / "team-memory"
    manager = repository_manager()

    created = manager.bootstrap(repository_path, actor_id="alice")
    manifest_before = (repository_path / ".mlagent/repository.json").read_bytes()
    reopened = manager.open(repository_path, actor_id="bob")

    manifest = json.loads(manifest_before)
    assert created.repository_id == "tmr-1"
    assert reopened.repository_id == "tmr-1"
    assert created.git_state == "initialized"
    assert reopened.git_state == "existing"
    assert (repository_path / ".git").is_dir()
    assert manifest["asset_type"] == "team_memory_repository"
    assert manifest["schema_version"] == 1
    assert manifest["created_by"] == "alice"
    assert tuple(manifest["managed_paths"]) == MANAGED_PATHS
    assert all((repository_path / path).is_dir() for path in MANAGED_PATHS)
    assert (repository_path / ".mlagent/repository.json").read_bytes() == manifest_before
    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=repository_path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    assert tracked == [".gitignore", ".mlagent/repository.json"]
    assert subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=repository_path,
        capture_output=True,
        text=True,
        check=False,
    ).returncode == 0
    assert subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repository_path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout == ""


def test_bootstrap_adds_local_and_credential_ignore_rules(tmp_path):
    repository_path = tmp_path / "team-memory"

    repository_manager().bootstrap(repository_path, actor_id="alice")

    ignore_rules = (repository_path / ".gitignore").read_text().splitlines()
    assert ".mlagent-local/" in ignore_rules
    assert ".mlagent-workspace.json" in ignore_rules
    assert ".env" in ignore_rules
    assert "*.pem" in ignore_rules
    assert "*.key" in ignore_rules


def test_bootstrap_refuses_nonempty_unrecognized_directory(tmp_path):
    repository_path = tmp_path / "team-memory"
    repository_path.mkdir()
    (repository_path / "unrelated.txt").write_text("do not adopt")

    with pytest.raises(WorkspaceError) as caught:
        repository_manager().bootstrap(repository_path, actor_id="alice")

    assert caught.value.code == "unrecognized_repository"
    assert "empty directory" in caught.value.next_action


def test_open_refuses_malformed_manifest(tmp_path):
    repository_path = tmp_path / "team-memory"
    manager = repository_manager()
    manager.bootstrap(repository_path, actor_id="alice")
    (repository_path / ".mlagent/repository.json").write_text("{not-json")

    with pytest.raises(WorkspaceError) as caught:
        manager.open(repository_path, actor_id="alice")

    assert caught.value.code == "invalid_manifest"
    assert "Restore" in caught.value.next_action


def test_open_refuses_unsupported_schema(tmp_path):
    repository_path = tmp_path / "team-memory"
    manager = repository_manager()
    manager.bootstrap(repository_path, actor_id="alice")
    manifest_path = repository_path / ".mlagent/repository.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["schema_version"] = 2
    manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(WorkspaceError) as caught:
        manager.open(repository_path, actor_id="alice")

    assert caught.value.code == "unsupported_schema"
    assert "schema version 1" in caught.value.next_action


def test_bootstrap_rejects_empty_repository_id_before_writing_manifest(tmp_path):
    repository_path = tmp_path / "team-memory"
    manager = MemoryRepository(
        id_factory=lambda: "",
        clock=lambda: "2026-07-14T00:00:00Z",
    )

    with pytest.raises(WorkspaceError) as caught:
        manager.bootstrap(repository_path, actor_id="alice")

    assert caught.value.code == "invalid_repository_id"
    assert not (repository_path / ".mlagent/repository.json").exists()


def test_open_refuses_directory_with_fake_git_metadata(tmp_path):
    repository_path = tmp_path / "team-memory"
    manager = repository_manager()
    manager.bootstrap(repository_path, actor_id="alice")
    shutil.rmtree(repository_path / ".git")
    (repository_path / ".git").mkdir()

    with pytest.raises(WorkspaceError) as caught:
        manager.open(repository_path, actor_id="alice")

    assert caught.value.code == "invalid_repository"
    assert "Git metadata" in caught.value.next_action


def test_open_wraps_type_invalid_manifest_as_actionable_error(tmp_path):
    repository_path = tmp_path / "team-memory"
    manager = repository_manager()
    manager.bootstrap(repository_path, actor_id="alice")
    manifest_path = repository_path / ".mlagent/repository.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["managed_paths"] = None
    manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(WorkspaceError) as caught:
        manager.open(repository_path, actor_id="alice")

    assert caught.value.code == "invalid_manifest"
    assert "Restore" in caught.value.next_action

import json
import shutil
import subprocess

import pytest

import src.domain.memory_repository as memory_repository_module
from src.domain.memory_repository import MANAGED_PATHS, MANIFEST_PATH, MemoryRepository
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


@pytest.mark.parametrize("stage_change", [False, True])
def test_open_refuses_manifest_identity_that_differs_from_head(
    tmp_path,
    stage_change,
):
    repository_path = tmp_path / "team-memory"
    manager = repository_manager()
    manager.bootstrap(repository_path, actor_id="alice")
    manifest_path = repository_path / ".mlagent/repository.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["repository_id"] = "tmr-worktree"
    manifest_path.write_text(json.dumps(manifest))
    if stage_change:
        subprocess.run(
            ["git", "add", "--", str(MANIFEST_PATH)],
            cwd=repository_path,
            capture_output=True,
            text=True,
            check=True,
        )

    with pytest.raises(WorkspaceError) as caught:
        manager.open(repository_path, actor_id="alice")

    assert caught.value.code == "authoritative_manifest_modified"
    assert "commit" in caught.value.next_action.lower()


def test_bootstrap_validates_manifest_before_writing_and_can_retry(tmp_path):
    repository_path = tmp_path / "team-memory"
    invalid_manager = MemoryRepository(
        id_factory=lambda: "tmr-1",
        clock=lambda: "",
    )

    with pytest.raises(WorkspaceError) as caught:
        invalid_manager.bootstrap(repository_path, actor_id="alice")

    assert caught.value.code == "invalid_manifest"
    assert not (repository_path / MANIFEST_PATH).exists()
    recovered = repository_manager().bootstrap(repository_path, actor_id="alice")
    assert recovered.repository_id == "tmr-1"


def test_bootstrap_rolls_back_generated_files_when_commit_fails(
    tmp_path,
    monkeypatch,
):
    repository_path = tmp_path / "team-memory"
    failing_manager = repository_manager()

    def fail_commit(root, actor_id):
        raise WorkspaceError(
            code="git_commit_failed",
            message="simulated failure",
            next_action="Retry bootstrap-memory.",
        )

    monkeypatch.setattr(failing_manager, "_commit_bootstrap", fail_commit)

    with pytest.raises(WorkspaceError) as caught:
        failing_manager.bootstrap(repository_path, actor_id="alice")

    assert caught.value.code == "git_commit_failed"
    assert not (repository_path / MANIFEST_PATH).exists()
    recovered = repository_manager().bootstrap(repository_path, actor_id="alice")
    assert recovered.git_state == "initialized"


def test_bootstrap_clears_staged_assets_when_git_commit_fails(
    tmp_path,
    monkeypatch,
):
    repository_path = tmp_path / "team-memory"
    real_run = subprocess.run

    def fail_commit(command, *args, **kwargs):
        if command[0] == "git" and "commit" in command:
            return subprocess.CompletedProcess(
                command,
                returncode=1,
                stdout="",
                stderr="simulated commit failure",
            )
        return real_run(command, *args, **kwargs)

    monkeypatch.setattr(memory_repository_module.subprocess, "run", fail_commit)

    with pytest.raises(WorkspaceError) as caught:
        repository_manager().bootstrap(repository_path, actor_id="alice")

    assert caught.value.code == "git_commit_failed"
    status = real_run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=repository_path,
        capture_output=True,
        text=True,
        check=True,
    )
    assert status.stdout == ""


def test_open_requires_manifest_to_exist_in_head_not_only_the_index(tmp_path):
    source_path = tmp_path / "source"
    repository_manager().bootstrap(source_path, actor_id="alice")
    manifest_bytes = (source_path / MANIFEST_PATH).read_bytes()

    repository_path = tmp_path / "team-memory"
    repository_path.mkdir()
    subprocess.run(
        ["git", "init"],
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
            "--allow-empty",
            "-m",
            "test: initialize repository",
        ],
        cwd=repository_path,
        capture_output=True,
        text=True,
        check=True,
    )
    manifest_path = repository_path / MANIFEST_PATH
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_bytes(manifest_bytes)
    subprocess.run(
        ["git", "add", "--", str(MANIFEST_PATH)],
        cwd=repository_path,
        capture_output=True,
        text=True,
        check=True,
    )

    with pytest.raises(WorkspaceError) as caught:
        repository_manager().open(repository_path, actor_id="alice")

    assert caught.value.code == "invalid_repository"


def test_open_refuses_committed_repository_id_rewrite(tmp_path):
    repository_path = tmp_path / "team-memory"
    manager = repository_manager()
    manager.bootstrap(repository_path, actor_id="alice")
    manifest_path = repository_path / MANIFEST_PATH
    manifest = json.loads(manifest_path.read_text())
    manifest["repository_id"] = "tmr-rewritten"
    manifest_path.write_text(json.dumps(manifest))
    subprocess.run(
        ["git", "add", "--", str(MANIFEST_PATH)],
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
            "test: rewrite repository identity",
        ],
        cwd=repository_path,
        capture_output=True,
        text=True,
        check=True,
    )

    with pytest.raises(WorkspaceError) as caught:
        manager.open(repository_path, actor_id="alice")

    assert caught.value.code == "repository_identity_changed"
    assert "original" in caught.value.next_action.lower()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("created_by", "mallory"),
        ("created_at", "2026-07-15T00:00:00Z"),
    ],
)
def test_open_refuses_committed_creation_provenance_rewrite(
    tmp_path,
    field,
    value,
):
    repository_path = tmp_path / "team-memory"
    manager = repository_manager()
    manager.bootstrap(repository_path, actor_id="alice")
    manifest_path = repository_path / MANIFEST_PATH
    manifest = json.loads(manifest_path.read_text())
    manifest[field] = value
    manifest_path.write_text(json.dumps(manifest))
    subprocess.run(
        ["git", "add", "--", str(MANIFEST_PATH)],
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
            "test: rewrite repository provenance",
        ],
        cwd=repository_path,
        capture_output=True,
        text=True,
        check=True,
    )

    with pytest.raises(WorkspaceError) as caught:
        manager.open(repository_path, actor_id="alice")

    assert caught.value.code == "repository_provenance_changed"
    assert "original" in caught.value.next_action.lower()


def test_open_wraps_missing_git_executable_as_actionable_error(
    tmp_path,
    monkeypatch,
):
    repository_path = tmp_path / "team-memory"
    manager = repository_manager()
    manager.bootstrap(repository_path, actor_id="alice")

    def missing_git(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(memory_repository_module.subprocess, "run", missing_git)

    with pytest.raises(WorkspaceError) as caught:
        manager.open(repository_path, actor_id="alice")

    assert caught.value.code == "git_unavailable"
    assert "Install Git" in caught.value.next_action

import json
import subprocess

import pytest

from src.domain.memory_repository import MemoryRepository
from src.domain.models import WorkspaceError


def manager(**kwargs) -> MemoryRepository:
    return MemoryRepository(
        id_factory=lambda: "tmr-1",
        clock=lambda: "2026-07-14T00:00:00Z",
        **kwargs,
    )


def init_bare_remote(path):
    subprocess.run(
        ["git", "init", "--bare", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )


def test_bootstrap_reports_reachable_local_git_remote(tmp_path):
    remote_path = tmp_path / "team-memory.git"
    init_bare_remote(remote_path)

    status = manager().bootstrap(
        tmp_path / "team-memory",
        actor_id="alice",
        remote_url=str(remote_path),
    )

    assert status.ready is True
    assert status.remote.state == "reachable"
    assert status.remote.url == str(remote_path)
    assert status.issues == ()


def test_bootstrap_accepts_reachable_file_url_for_hermetic_remote(tmp_path):
    remote_path = tmp_path / "team-memory.git"
    init_bare_remote(remote_path)

    status = manager().bootstrap(
        tmp_path / "team-memory",
        actor_id="alice",
        remote_url=remote_path.as_uri(),
    )

    assert status.ready is True
    assert status.remote.state == "reachable"
    assert status.remote.url == remote_path.as_uri()


@pytest.mark.parametrize("name", ["local:remote.git", "local@remote.git"])
def test_bootstrap_accepts_local_remote_with_network_punctuation(tmp_path, name):
    remote_path = tmp_path / name
    init_bare_remote(remote_path)

    status = manager().bootstrap(
        tmp_path / "team-memory",
        actor_id="alice",
        remote_url=str(remote_path),
    )

    assert status.ready is True
    assert status.remote.state == "reachable"


def test_bootstrap_rejects_http_remote_before_credentials_can_be_persisted(tmp_path):
    repository_path = tmp_path / "team-memory"

    with pytest.raises(WorkspaceError) as caught:
        manager().bootstrap(
            repository_path,
            actor_id="alice",
            remote_url="https://example.com/team-memory.git",
        )

    assert caught.value.code == "remote_not_ssh"
    assert "SSH" in caught.value.next_action
    assert not (repository_path / ".mlagent/repository.json").exists()
    assert not (repository_path / ".git").exists()


def test_bootstrap_rejects_non_git_scp_network_identity(tmp_path):
    with pytest.raises(WorkspaceError) as caught:
        manager().bootstrap(
            tmp_path / "team-memory",
            actor_id="alice",
            remote_url="other-user@example.com:team-memory.git",
        )

    assert caught.value.code == "remote_not_ssh"


def test_bootstrap_rejects_scp_style_remote_without_git_identity(tmp_path):
    with pytest.raises(WorkspaceError) as caught:
        manager().bootstrap(
            tmp_path / "team-memory",
            actor_id="alice",
            remote_url="example.com:team-memory.git",
        )

    assert caught.value.code == "remote_not_ssh"


def test_bootstrap_reports_unreachable_ssh_remote_as_not_ready(tmp_path):
    status = manager(remote_timeout_seconds=1).bootstrap(
        tmp_path / "team-memory",
        actor_id="alice",
        remote_url="ssh://127.0.0.1:1/team-memory.git",
    )

    assert status.ready is False
    assert status.remote.state == "unreachable"
    assert [issue.code for issue in status.issues] == ["remote_unreachable"]
    assert "SSH agent" in status.issues[0].next_action


def test_open_blocks_file_at_configured_size_limit(tmp_path):
    repository_path = tmp_path / "team-memory"
    policy_manager = manager(
        max_file_bytes=1024,
        max_repository_bytes=100_000,
    )
    policy_manager.bootstrap(repository_path, actor_id="alice")
    large_file = repository_path / "models/large.bin"
    large_file.write_bytes(b"x" * 1024)

    status = policy_manager.open(repository_path, actor_id="alice")

    assert status.ready is False
    assert status.capacity.state == "blocked"
    assert "file_too_large" in {issue.code for issue in status.issues}


def test_open_warns_at_eighty_percent_without_blocking(tmp_path):
    repository_path = tmp_path / "team-memory"
    max_repository_bytes = 10_000
    policy_manager = manager(
        max_file_bytes=100_000,
        max_repository_bytes=max_repository_bytes,
        warning_ratio=0.8,
    )
    created = policy_manager.bootstrap(repository_path, actor_id="alice")
    warning_bytes = int(max_repository_bytes * 0.8)
    padding_bytes = max(warning_bytes - created.capacity.bytes_used + 1, 1)
    (repository_path / "raw-records/padding.bin").write_bytes(b"x" * padding_bytes)

    status = policy_manager.open(repository_path, actor_id="alice")

    assert status.ready is True
    assert status.capacity.state == "warning"
    assert [issue.code for issue in status.issues] == [
        "repository_capacity_warning"
    ]


def test_bootstrap_persists_and_enforces_repository_capacity_policy(tmp_path):
    repository_path = tmp_path / "team-memory"
    policy_manager = manager(
        max_file_bytes=2048,
        max_repository_bytes=20_000,
        warning_ratio=0.75,
    )

    created = policy_manager.bootstrap(repository_path, actor_id="alice")
    manifest = json.loads(
        (repository_path / ".mlagent/repository.json").read_text()
    )
    reopened = manager().open(repository_path, actor_id="bob")

    assert manifest["limits"] == {
        "max_file_bytes": 2048,
        "max_repository_bytes": 20_000,
        "warning_ratio": 0.75,
    }
    assert created.capacity.max_file_bytes == 2048
    assert reopened.capacity.max_file_bytes == 2048
    assert reopened.capacity.max_repository_bytes == 20_000


@pytest.mark.parametrize(
    "policy",
    [
        {"max_file_bytes": 0},
        {"max_file_bytes": 100_000_001},
        {"max_repository_bytes": -1},
        {"max_repository_bytes": 20_000_000_001},
        {"warning_ratio": 0},
        {"warning_ratio": 0.81},
        {"warning_ratio": 1},
    ],
)
def test_bootstrap_rejects_invalid_capacity_policy_before_writing(tmp_path, policy):
    repository_path = tmp_path / "team-memory"

    with pytest.raises(WorkspaceError) as caught:
        manager(**policy).bootstrap(repository_path, actor_id="alice")

    assert caught.value.code == "invalid_capacity_policy"
    assert not (repository_path / ".mlagent/repository.json").exists()


def test_open_blocks_repository_at_configured_capacity_limit(tmp_path):
    repository_path = tmp_path / "team-memory"
    max_repository_bytes = 10_000
    policy_manager = manager(
        max_file_bytes=100_000,
        max_repository_bytes=max_repository_bytes,
    )
    created = policy_manager.bootstrap(repository_path, actor_id="alice")
    padding_bytes = max_repository_bytes - created.capacity.bytes_used
    (repository_path / "raw-records/padding.bin").write_bytes(
        b"x" * padding_bytes
    )

    status = policy_manager.open(repository_path, actor_id="alice")

    assert status.ready is False
    assert status.capacity.state == "blocked"
    assert "repository_capacity_exceeded" in {
        issue.code for issue in status.issues
    }


def test_capacity_excludes_git_metadata_and_disposable_local_index(tmp_path):
    repository_path = tmp_path / "team-memory"
    policy_manager = manager(
        max_file_bytes=100_000,
        max_repository_bytes=10_000,
    )
    created = policy_manager.bootstrap(repository_path, actor_id="alice")
    (repository_path / ".git/ignored-capacity.bin").write_bytes(b"x" * 20_000)
    local_asset = repository_path / ".mlagent-local/ignored-capacity.bin"
    local_asset.parent.mkdir(parents=True)
    local_asset.write_bytes(b"x" * 20_000)

    reopened = policy_manager.open(repository_path, actor_id="alice")

    assert reopened.capacity.bytes_used == created.capacity.bytes_used
    assert reopened.capacity.state == "ok"

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


def test_bootstrap_rejects_http_remote_before_credentials_can_be_persisted(tmp_path):
    with pytest.raises(WorkspaceError) as caught:
        manager().bootstrap(
            tmp_path / "team-memory",
            actor_id="alice",
            remote_url="https://example.com/team-memory.git",
        )

    assert caught.value.code == "remote_not_ssh"
    assert "SSH" in caught.value.next_action


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
    manager().bootstrap(repository_path, actor_id="alice")
    large_file = repository_path / "models/large.bin"
    large_file.write_bytes(b"x" * 1024)

    status = manager(
        max_file_bytes=1024,
        max_repository_bytes=100_000,
    ).open(repository_path, actor_id="alice")

    assert status.ready is False
    assert status.capacity.state == "blocked"
    assert "file_too_large" in {issue.code for issue in status.issues}


def test_open_warns_at_eighty_percent_without_blocking(tmp_path):
    repository_path = tmp_path / "team-memory"
    created = manager().bootstrap(repository_path, actor_id="alice")
    max_repository_bytes = created.capacity.bytes_used + 1000
    warning_bytes = int(max_repository_bytes * 0.8)
    padding_bytes = max(warning_bytes - created.capacity.bytes_used + 1, 1)
    (repository_path / "raw-records/padding.bin").write_bytes(b"x" * padding_bytes)

    status = manager(
        max_file_bytes=100_000,
        max_repository_bytes=max_repository_bytes,
        warning_ratio=0.8,
    ).open(repository_path, actor_id="alice")

    assert status.ready is True
    assert status.capacity.state == "warning"
    assert [issue.code for issue in status.issues] == [
        "repository_capacity_warning"
    ]

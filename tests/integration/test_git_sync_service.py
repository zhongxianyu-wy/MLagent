import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from src.domain.git_sync import GitSyncService
from src.domain.memory_repository import MemoryRepository


def git(
    root: Path,
    *arguments: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *arguments],
        cwd=root,
        capture_output=True,
        text=True,
        check=check,
    )


def init_bare_remote(path: Path) -> None:
    subprocess.run(
        ["git", "init", "--bare", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )


@dataclass(frozen=True)
class SyncWorkspace:
    root: Path
    remote: Path
    branch: str

    def service(self, actor_id: str = "alice") -> GitSyncService:
        return GitSyncService(
            self.root,
            actor_id,
            clock=lambda: "2026-07-16T00:00:00Z",
        )


@dataclass(frozen=True)
class TwoClients:
    alice: Path
    bob: Path
    remote: Path
    branch: str

    @property
    def alice_service(self) -> GitSyncService:
        return GitSyncService(
            self.alice,
            "alice",
            clock=lambda: "2026-07-16T00:00:00Z",
        )


@pytest.fixture
def sync_workspace(tmp_path: Path) -> SyncWorkspace:
    remote = tmp_path / "team-memory.git"
    init_bare_remote(remote)
    root = tmp_path / "alice"
    MemoryRepository(
        id_factory=lambda: "tmr-1",
        clock=lambda: "2026-07-16T00:00:00Z",
    ).bootstrap(root, actor_id="alice", remote_url=str(remote))
    branch = git(root, "branch", "--show-current").stdout.strip()
    git(root, "push", "--set-upstream", "origin", f"HEAD:{branch}")
    return SyncWorkspace(root=root, remote=remote, branch=branch)


@pytest.fixture
def empty_remote_workspace(tmp_path: Path) -> SyncWorkspace:
    remote = tmp_path / "team-memory.git"
    init_bare_remote(remote)
    root = tmp_path / "alice"
    MemoryRepository(
        id_factory=lambda: "tmr-1",
        clock=lambda: "2026-07-16T00:00:00Z",
    ).bootstrap(root, actor_id="alice", remote_url=str(remote))
    branch = git(root, "branch", "--show-current").stdout.strip()
    return SyncWorkspace(root=root, remote=remote, branch=branch)


@pytest.fixture
def two_clients(tmp_path: Path) -> TwoClients:
    remote = tmp_path / "team-memory.git"
    init_bare_remote(remote)
    alice = tmp_path / "alice"
    MemoryRepository(
        id_factory=lambda: "tmr-1",
        clock=lambda: "2026-07-16T00:00:00Z",
    ).bootstrap(alice, actor_id="alice", remote_url=str(remote))
    branch = git(alice, "branch", "--show-current").stdout.strip()
    git(alice, "push", "--set-upstream", "origin", f"HEAD:{branch}")
    bob = tmp_path / "bob"
    subprocess.run(
        ["git", "clone", "--branch", branch, str(remote), str(bob)],
        capture_output=True,
        text=True,
        check=True,
    )
    return TwoClients(
        alice=alice,
        bob=bob,
        remote=remote,
        branch=branch,
    )


def write_and_commit(
    root: Path,
    relative: str,
    content: str,
    actor: str,
) -> str:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    git(root, "add", "--", relative)
    git(
        root,
        "-c",
        f"user.name={actor}",
        "-c",
        "user.email=mlagent@local",
        "commit",
        "-m",
        f"test: add {relative}",
    )
    return git(root, "rev-parse", "HEAD").stdout.strip()


def test_missing_local_state_is_derived_without_network(sync_workspace):
    status = sync_workspace.service().status()

    assert status.state == "synced"
    assert status.branch == sync_workspace.branch
    assert status.ahead_count == 0
    assert status.behind_count == 0
    assert status.changed_managed_paths == ()


def test_untracked_managed_asset_is_pending_but_unrelated_file_is_not_managed(
    sync_workspace,
):
    managed = sync_workspace.root / "experiences/candidate-1.json"
    managed.write_text(
        '{"asset_type":"experience_candidate"}\n',
        encoding="utf-8",
    )
    unrelated = sync_workspace.root / "notes.txt"
    unrelated.write_text("private note\n", encoding="utf-8")

    status = sync_workspace.service().status()

    assert status.state == "pending_sync"
    assert status.changed_managed_paths == (
        "experiences/candidate-1.json",
    )
    assert "notes.txt" not in status.changed_managed_paths


def test_corrupt_local_state_fails_closed_without_changing_git(sync_workspace):
    state_path = sync_workspace.root / ".mlagent-local/sync-state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text("{not-json", encoding="utf-8")
    before = git(sync_workspace.root, "rev-parse", "HEAD").stdout.strip()

    status = sync_workspace.service().status()

    assert status.state == "pending_sync"
    assert status.next_action is not None
    assert "local sync state" in status.message.lower()
    assert git(sync_workspace.root, "rev-parse", "HEAD").stdout.strip() == before


def test_session_start_pushes_initial_branch_without_reclone(
    empty_remote_workspace,
):
    git_inode = (empty_remote_workspace.root / ".git").stat().st_ino

    status = empty_remote_workspace.service().session_start()

    assert status.state == "synced"
    assert status.ahead_count == 0
    assert (
        git(
            empty_remote_workspace.remote,
            "rev-parse",
            f"refs/heads/{status.branch}",
        ).stdout.strip()
        == status.local_head
    )
    assert (empty_remote_workspace.root / ".git").stat().st_ino == git_inode


def test_session_start_with_no_changes_does_not_create_commit(sync_workspace):
    before = git(sync_workspace.root, "rev-parse", "HEAD").stdout.strip()

    status = sync_workspace.service().session_start()

    assert status.state == "synced"
    assert git(sync_workspace.root, "rev-parse", "HEAD").stdout.strip() == before


def test_session_start_fast_forwards_remote_only_commit(two_clients):
    remote_head = write_and_commit(
        two_clients.bob,
        "raw-records/bob-event.json",
        '{"asset_type":"run_event"}\n',
        "bob",
    )
    git(two_clients.bob, "push")

    status = two_clients.alice_service.session_start()

    assert status.state == "synced"
    assert status.local_head == remote_head
    assert (two_clients.alice / "raw-records/bob-event.json").is_file()


def test_session_start_merges_disjoint_divergence(two_clients):
    write_and_commit(
        two_clients.alice,
        "experiences/alice.json",
        '{"actor":"alice"}\n',
        "alice",
    )
    write_and_commit(
        two_clients.bob,
        "raw-records/bob.json",
        '{"actor":"bob"}\n',
        "bob",
    )
    git(two_clients.bob, "push")

    status = two_clients.alice_service.session_start()

    assert status.state == "synced"
    assert (two_clients.alice / "experiences/alice.json").is_file()
    assert (two_clients.alice / "raw-records/bob.json").is_file()
    parents = git(
        two_clients.alice,
        "rev-list",
        "--parents",
        "-n",
        "1",
        "HEAD",
    ).stdout.split()
    assert len(parents) == 3

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

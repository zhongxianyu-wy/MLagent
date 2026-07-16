import json
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


def repository_capacity(root: Path):
    return MemoryRepository().open(root, actor_id="test").capacity


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


def test_stale_syncing_state_recovers_to_pending_when_lock_is_free(
    sync_workspace,
):
    head = git(sync_workspace.root, "rev-parse", "HEAD").stdout.strip()
    state_path = sync_workspace.root / ".mlagent-local/sync-state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "state": "syncing",
                "branch": sync_workspace.branch,
                "local_head": head,
                "remote_head": head,
                "ahead_count": 0,
                "behind_count": 0,
                "changed_managed_paths": [],
                "conflict_paths": [],
                "last_attempt_at": "2026-07-16T00:00:00Z",
                "last_success_at": None,
                "sync_commit": None,
                "message": "Team Memory synchronization is running.",
                "next_action": None,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    status = sync_workspace.service().status()

    assert status.state == "pending_sync"
    assert "interrupted" in status.message.lower()


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


def test_session_start_fast_forwards_with_unrelated_dirty_file(two_clients):
    remote_head = write_and_commit(
        two_clients.bob,
        "raw-records/bob-event.json",
        '{"asset_type":"run_event","asset_id":"bob-event"}\n',
        "bob",
    )
    git(two_clients.bob, "push")
    note = two_clients.alice / "notes.txt"
    note.write_text("local note\n", encoding="utf-8")

    status = two_clients.alice_service.session_start()

    assert status.state == "synced"
    assert status.local_head == remote_head
    assert note.read_text(encoding="utf-8") == "local note\n"


def test_session_start_preserves_dirty_path_touched_by_remote(two_clients):
    relative = "experiences/shared.json"
    write_and_commit(
        two_clients.bob,
        relative,
        '{"actor":"bob"}\n',
        "bob",
    )
    git(two_clients.bob, "push")
    local = two_clients.alice / relative
    local.write_text('{"actor":"alice"}\n', encoding="utf-8")

    status = two_clients.alice_service.session_start()

    assert status.state == "pending_sync"
    assert local.read_text(encoding="utf-8") == '{"actor":"alice"}\n'


def test_status_reports_both_paths_for_managed_rename(sync_workspace):
    original = sync_workspace.root / "experiences/original.json"
    original.write_text("{}\n", encoding="utf-8")
    git(sync_workspace.root, "add", "--", "experiences/original.json")
    git(
        sync_workspace.root,
        "-c",
        "user.name=alice",
        "-c",
        "user.email=mlagent@local",
        "commit",
        "-m",
        "test: add original",
    )
    git(sync_workspace.root, "push")
    renamed = sync_workspace.root / "experiences/renamed.json"
    original.rename(renamed)
    git(sync_workspace.root, "add", "-A", "--", "experiences")

    status = sync_workspace.service().status()

    assert status.changed_managed_paths == (
        "experiences/original.json",
        "experiences/renamed.json",
    )


def test_session_stop_commits_only_managed_differences(two_clients):
    managed = two_clients.alice / "experiences/candidate.json"
    managed.write_text("{}\n", encoding="utf-8")
    unrelated = two_clients.alice / "notes.txt"
    unrelated.write_text("local only\n", encoding="utf-8")

    status = two_clients.alice_service.session_stop(
        "session-1",
        repository_capacity(two_clients.alice),
    )

    assert status.state == "synced"
    committed = git(
        two_clients.alice,
        "show",
        "--name-only",
        "--format=",
        "HEAD",
    ).stdout.splitlines()
    assert "experiences/candidate.json" in committed
    assert "notes.txt" not in committed
    assert unrelated.is_file()
    assert git(
        two_clients.alice,
        "status",
        "--porcelain",
        "--",
        "notes.txt",
    ).stdout.startswith("??")


def test_session_stop_preserves_pre_staged_unmanaged_differences(two_clients):
    unrelated = two_clients.alice / "notes.txt"
    unrelated.write_text("review later\n", encoding="utf-8")
    git(two_clients.alice, "add", "--", "notes.txt")
    (two_clients.alice / "experiences/candidate.json").write_text(
        "{}\n",
        encoding="utf-8",
    )

    status = two_clients.alice_service.session_stop(
        "session-staged-note",
        repository_capacity(two_clients.alice),
    )

    assert status.state == "synced"
    committed = git(
        two_clients.alice,
        "show",
        "--name-only",
        "--format=",
        "HEAD",
    ).stdout.splitlines()
    assert "experiences/candidate.json" in committed
    assert "notes.txt" not in committed
    assert git(
        two_clients.alice,
        "status",
        "--porcelain",
        "--",
        "notes.txt",
    ).stdout.startswith("A ")


def test_empty_session_stop_does_not_create_commit(two_clients):
    before = git(two_clients.alice, "rev-parse", "HEAD").stdout.strip()

    status = two_clients.alice_service.session_stop(
        "session-empty",
        repository_capacity(two_clients.alice),
    )

    assert status.state == "synced"
    assert git(two_clients.alice, "rev-parse", "HEAD").stdout.strip() == before


def test_rejected_push_fetches_merges_disjoint_and_retries_once(two_clients):
    (two_clients.alice / "experiences/alice.json").write_text(
        '{"actor":"alice"}\n',
        encoding="utf-8",
    )
    write_and_commit(
        two_clients.bob,
        "raw-records/bob.json",
        '{"actor":"bob"}\n',
        "bob",
    )
    git(two_clients.bob, "push")

    status = two_clients.alice_service.session_stop(
        "session-retry",
        repository_capacity(two_clients.alice),
    )

    assert status.state == "synced"
    assert (
        git(
            two_clients.remote,
            "show",
            f"{two_clients.branch}:experiences/alice.json",
        ).returncode
        == 0
    )
    assert (
        git(
            two_clients.remote,
            "show",
            f"{two_clients.branch}:raw-records/bob.json",
        ).returncode
        == 0
    )


def test_same_path_divergence_preserves_local_commit_and_reports_conflict(
    two_clients,
):
    relative = "experiences/shared.json"
    write_and_commit(
        two_clients.bob,
        relative,
        '{"actor":"bob"}\n',
        "bob",
    )
    git(two_clients.bob, "push")
    (two_clients.alice / relative).write_text(
        '{"actor":"alice"}\n',
        encoding="utf-8",
    )

    status = two_clients.alice_service.session_stop(
        "session-conflict",
        repository_capacity(two_clients.alice),
    )

    assert status.state == "conflict"
    assert status.conflict_paths == (relative,)
    assert (
        (two_clients.alice / relative).read_text(encoding="utf-8")
        == '{"actor":"alice"}\n'
    )
    local_head = git(two_clients.alice, "rev-parse", "HEAD").stdout.strip()
    assert local_head != status.remote_head
    assert status.sync_commit == local_head


def test_unavailable_remote_preserves_commit_and_later_start_retries(
    two_clients,
):
    asset = two_clients.alice / "experiences/pending.json"
    asset.write_text("{}\n", encoding="utf-8")
    disabled_remote = two_clients.remote.with_name("team-memory.disabled")
    two_clients.remote.rename(disabled_remote)
    try:
        pending = two_clients.alice_service.session_stop(
            "session-offline",
            repository_capacity(two_clients.alice),
        )
    finally:
        disabled_remote.rename(two_clients.remote)

    assert pending.state == "pending_sync"
    assert pending.sync_commit is not None
    assert asset.is_file()

    recovered = two_clients.alice_service.session_start()

    assert recovered.state == "synced"
    assert (
        git(
            two_clients.remote,
            "show",
            f"{two_clients.branch}:experiences/pending.json",
        ).returncode
        == 0
    )


def test_session_stop_rejects_file_at_capacity_limit_before_commit(tmp_path):
    remote = tmp_path / "team-memory.git"
    init_bare_remote(remote)
    root = tmp_path / "alice"
    manager = MemoryRepository(
        id_factory=lambda: "tmr-1",
        clock=lambda: "2026-07-16T00:00:00Z",
        max_file_bytes=512,
        max_repository_bytes=100_000,
    )
    manager.bootstrap(root, actor_id="alice", remote_url=str(remote))
    branch = git(root, "branch", "--show-current").stdout.strip()
    git(root, "push", "--set-upstream", "origin", f"HEAD:{branch}")
    stale_capacity = manager.capacity_status(root)
    oversized = root / "models/too-large.bin"
    oversized.write_bytes(b"x" * 512)
    before = git(root, "rev-parse", "HEAD").stdout.strip()

    status = GitSyncService(
        root,
        "alice",
        clock=lambda: "2026-07-16T00:00:00Z",
    ).session_stop("session-large", stale_capacity)

    assert status.state == "pending_sync"
    assert "single-file" in status.message
    assert git(root, "rev-parse", "HEAD").stdout.strip() == before
    assert oversized.is_file()


def test_session_stop_allows_repository_capacity_warning(tmp_path):
    remote = tmp_path / "team-memory.git"
    init_bare_remote(remote)
    root = tmp_path / "alice"
    max_repository_bytes = 10_000
    manager = MemoryRepository(
        id_factory=lambda: "tmr-1",
        clock=lambda: "2026-07-16T00:00:00Z",
        max_file_bytes=100_000,
        max_repository_bytes=max_repository_bytes,
        warning_ratio=0.8,
    )
    created = manager.bootstrap(
        root,
        actor_id="alice",
        remote_url=str(remote),
    )
    branch = git(root, "branch", "--show-current").stdout.strip()
    git(root, "push", "--set-upstream", "origin", f"HEAD:{branch}")
    warning_bytes = int(max_repository_bytes * 0.8)
    padding_bytes = max(warning_bytes - created.capacity.bytes_used + 1, 1)
    (root / "experiences/padding.bin").write_bytes(b"x" * padding_bytes)
    capacity = manager.capacity_status(root)

    status = GitSyncService(
        root,
        "alice",
        clock=lambda: "2026-07-16T00:00:00Z",
    ).session_stop("session-warning", capacity)

    assert capacity.state == "warning"
    assert status.state == "synced"


def test_session_stop_never_invokes_force_git_arguments(
    two_clients,
    monkeypatch,
):
    (two_clients.alice / "experiences/candidate.json").write_text(
        "{}\n",
        encoding="utf-8",
    )
    capacity = repository_capacity(two_clients.alice)
    real_run = subprocess.run
    commands: list[tuple[str, ...]] = []

    def recording_run(arguments, *args, **kwargs):
        commands.append(tuple(str(argument) for argument in arguments))
        return real_run(arguments, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", recording_run)

    status = two_clients.alice_service.session_stop(
        "session-no-force",
        capacity,
    )

    assert status.state == "synced"
    assert commands
    assert not any(
        argument in {"--force", "--force-with-lease", "--force-if-includes"}
        or (argument.startswith("+") and ":" in argument)
        for command in commands
        for argument in command
    )

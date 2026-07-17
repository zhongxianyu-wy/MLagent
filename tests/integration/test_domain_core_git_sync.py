import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from src.domain.core import DomainCore
from src.domain.models import (
    BootstrapMemoryCommand,
    SessionStopSyncCommand,
    WorkspaceError,
)


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


@dataclass(frozen=True)
class SyncCoreWorkspace:
    core: DomainCore
    connection_path: Path
    memory_root: Path
    remote: Path
    branch: str


@pytest.fixture
def sync_core_workspace(tmp_path: Path) -> SyncCoreWorkspace:
    remote = tmp_path / "team-memory.git"
    subprocess.run(
        ["git", "init", "--bare", str(remote)],
        capture_output=True,
        text=True,
        check=True,
    )
    memory_root = tmp_path / "alice"
    connection_path = tmp_path / ".mlagent-workspace.json"
    core = DomainCore(
        id_factory=lambda: "tmr-1",
        clock=lambda: "2026-07-16T00:00:00Z",
    )
    core.bootstrap_memory(
        BootstrapMemoryCommand(
            repository_path=memory_root,
            actor_id="alice",
            remote_url=str(remote),
            connection_path=connection_path,
        )
    )
    branch = git(memory_root, "branch", "--show-current").stdout.strip()
    git(
        memory_root,
        "push",
        "--set-upstream",
        "origin",
        f"HEAD:{branch}",
    )
    return SyncCoreWorkspace(
        core=core,
        connection_path=connection_path,
        memory_root=memory_root,
        remote=remote,
        branch=branch,
    )


def test_domain_core_session_start_syncs_then_rebuilds_index(
    sync_core_workspace,
    tmp_path,
):
    collaborator = tmp_path / "bob"
    subprocess.run(
        [
            "git",
            "clone",
            "--branch",
            sync_core_workspace.branch,
            str(sync_core_workspace.remote),
            str(collaborator),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    asset = collaborator / "raw-records/remote-event.json"
    asset.parent.mkdir(parents=True, exist_ok=True)
    asset.write_text(
        json.dumps(
            {
                "asset_type": "run_event",
                "asset_id": "remote-event",
                "created_at": "2026-07-16T00:00:00Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    git(collaborator, "add", "--", "raw-records/remote-event.json")
    git(
        collaborator,
        "-c",
        "user.name=bob",
        "-c",
        "user.email=mlagent@local",
        "commit",
        "-m",
        "test: add remote event",
    )
    git(collaborator, "push")

    status = sync_core_workspace.core.sync_session_start(
        sync_core_workspace.connection_path
    )
    snapshot = sync_core_workspace.core.open_workspace(
        sync_core_workspace.connection_path
    )

    assert status.state == "synced"
    assert snapshot.sync == status
    assert snapshot.indexed_assets == 2


def test_new_experience_session_requires_safe_startup_sync(
    sync_core_workspace,
):
    disabled_remote = sync_core_workspace.remote.with_name(
        "team-memory.disabled"
    )
    sync_core_workspace.remote.rename(disabled_remote)
    try:
        with pytest.raises(WorkspaceError, match="synchron"):
            sync_core_workspace.core.start_session(
                sync_core_workspace.connection_path,
                "session-unsafe",
            )
    finally:
        disabled_remote.rename(sync_core_workspace.remote)

    assert not (
        sync_core_workspace.memory_root
        / "raw-records/sessions/session-unsafe/start.json"
    ).exists()


def test_repeated_start_reuses_existing_boundary_while_marker_is_pending_sync(
    sync_core_workspace,
):
    first = sync_core_workspace.core.start_session(
        sync_core_workspace.connection_path,
        "session-resume",
    )
    marker = (
        sync_core_workspace.memory_root
        / "raw-records/sessions/session-resume/start.json"
    )
    before = marker.read_bytes()

    resumed = sync_core_workspace.core.start_session(
        sync_core_workspace.connection_path,
        "session-resume",
    )

    assert first.sync.state == "synced"
    assert resumed.outcome == "started"
    assert resumed.sync.state == "pending_sync"
    assert marker.read_bytes() == before


def test_domain_core_stop_preserves_pending_commit_on_remote_failure(
    sync_core_workspace,
):
    asset = sync_core_workspace.memory_root / "experiences/candidate.json"
    asset.write_text(
        json.dumps(
            {
                "asset_type": "experience_candidate",
                "asset_id": "candidate-1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    disabled_remote = sync_core_workspace.remote.with_name(
        "team-memory.disabled"
    )
    sync_core_workspace.remote.rename(disabled_remote)
    try:
        status = sync_core_workspace.core.sync_session_stop(
            SessionStopSyncCommand(
                connection_path=sync_core_workspace.connection_path,
                session_id="session-1",
            )
        )
    finally:
        disabled_remote.rename(sync_core_workspace.remote)

    assert status.state == "pending_sync"
    assert status.sync_commit is not None
    assert asset.is_file()
    assert git(
        sync_core_workspace.memory_root,
        "show",
        f"{status.sync_commit}:experiences/candidate.json",
    ).returncode == 0


def test_domain_core_get_sync_status_never_fetches(
    sync_core_workspace,
    monkeypatch,
):
    initial = sync_core_workspace.core.sync_session_start(
        sync_core_workspace.connection_path
    )
    real_run = subprocess.run
    commands: list[tuple[str, ...]] = []

    def recording_run(arguments, *args, **kwargs):
        commands.append(tuple(str(argument) for argument in arguments))
        return real_run(arguments, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", recording_run)

    status = sync_core_workspace.core.get_sync_status(
        sync_core_workspace.connection_path
    )

    assert status == initial
    assert commands
    assert not any("fetch" in command for command in commands)

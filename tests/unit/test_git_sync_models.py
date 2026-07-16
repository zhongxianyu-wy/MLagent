from pathlib import Path

import pytest

from src.domain.models import (
    SessionStopSyncCommand,
    SyncStatusSnapshot,
)


def sync_status(**changes) -> SyncStatusSnapshot:
    values = {
        "state": "synced",
        "branch": "main",
        "local_head": "local-sha",
        "remote_head": "remote-sha",
        "ahead_count": 0,
        "behind_count": 0,
        "changed_managed_paths": (),
        "conflict_paths": (),
        "last_attempt_at": "2026-07-16T00:00:00Z",
        "last_success_at": "2026-07-16T00:00:00Z",
        "sync_commit": None,
        "message": "Team Memory is synchronized.",
        "next_action": None,
    }
    values.update(changes)
    return SyncStatusSnapshot(**values)


def test_sync_status_accepts_conflict_only_with_paths_and_action():
    status = sync_status(
        state="conflict",
        ahead_count=1,
        behind_count=1,
        conflict_paths=("datasets/ds-1/v0001/manifest.json",),
        last_success_at=None,
        message="Same authoritative path changed on both sides.",
        next_action="Review both committed versions.",
    )

    assert status.state == "conflict"
    assert status.conflict_paths == (
        "datasets/ds-1/v0001/manifest.json",
    )


def test_sync_status_rejects_conflict_without_conflict_paths():
    with pytest.raises(ValueError, match="conflict_paths"):
        sync_status(
            state="conflict",
            ahead_count=1,
            behind_count=1,
            last_success_at=None,
            message="Conflict",
            next_action="Review",
        )


def test_sync_status_rejects_conflict_paths_for_non_conflict_state():
    with pytest.raises(ValueError, match="conflict_paths"):
        sync_status(
            state="pending_sync",
            conflict_paths=("experiences/shared.json",),
            next_action="Retry",
        )


def test_sync_status_rejects_negative_commit_counts():
    with pytest.raises(ValueError, match="ahead_count"):
        sync_status(ahead_count=-1)


def test_session_stop_command_requires_nonempty_session_identity():
    with pytest.raises(ValueError, match="session_id"):
        SessionStopSyncCommand(
            connection_path=Path(".mlagent-workspace.json"),
            session_id="",
        )

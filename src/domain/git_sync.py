from __future__ import annotations

import json
import os
import subprocess
import uuid
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.domain.memory_repository import MANAGED_PATHS
from src.domain.models import SyncStatusSnapshot, WorkspaceError


SYNC_STATE_PATH = Path(".mlagent-local/sync-state.json")
SYNC_LOCK_PATH = Path(".mlagent-local/sync.lock")
FORBIDDEN_GIT_ARGUMENTS = {
    "--force",
    "--force-with-lease",
    "--force-if-includes",
}


class GitSyncService:
    def __init__(
        self,
        repository_path: Path,
        actor_id: str,
        clock: Callable[[], str] | None = None,
    ) -> None:
        root = repository_path.expanduser()
        if root.is_symlink():
            self._invalid_repository()
        self.repository_path = root.resolve()
        if not isinstance(actor_id, str) or not actor_id.strip():
            raise WorkspaceError(
                code="missing_actor",
                message="Git synchronization requires a non-empty actor.",
                next_action="Reconnect Team Memory with a valid member identity.",
            )
        self.actor_id = actor_id
        self.clock = clock or _utc_now

    def status(self) -> SyncStatusSnapshot:
        self._validate_repository()
        persisted, state_error = self._load_local_state()
        if state_error is not None:
            return self._snapshot(
                state="pending_sync",
                branch=self._current_branch(),
                local_head=self._rev_parse("HEAD"),
                remote_head=None,
                ahead_count=0,
                behind_count=0,
                changed_managed_paths=self._managed_changes(),
                conflict_paths=(),
                last_attempt_at=None,
                last_success_at=None,
                sync_commit=None,
                message="The local sync state is invalid and cannot be trusted.",
                next_action=(
                    "Retry SessionStart synchronization to rebuild local sync state."
                ),
            )
        if persisted is not None and persisted.state in {"syncing", "conflict"}:
            return persisted

        branch = self._current_branch()
        local_head = self._rev_parse("HEAD")
        origin_url = self._origin_url()
        remote_ref = self._remote_ref(branch)
        remote_head = self._optional_rev_parse(remote_ref)
        ahead, behind = self._ahead_behind(local_head, remote_head)
        changed = self._managed_changes()
        if origin_url is None:
            state = "not_configured"
            message = "No origin remote is configured."
            next_action = "Configure the Team Memory origin before synchronization."
        elif remote_head is None or changed or ahead or behind:
            state = "pending_sync"
            message = "Team Memory has local or fetched differences to synchronize."
            next_action = "Run SessionStart or Stop synchronization."
        else:
            state = "synced"
            message = "Team Memory is synchronized."
            next_action = None
        return self._snapshot(
            state=state,
            branch=branch,
            local_head=local_head,
            remote_head=remote_head,
            ahead_count=ahead,
            behind_count=behind,
            changed_managed_paths=changed,
            conflict_paths=(),
            last_attempt_at=(
                None if persisted is None else persisted.last_attempt_at
            ),
            last_success_at=(
                None if persisted is None else persisted.last_success_at
            ),
            sync_commit=None if persisted is None else persisted.sync_commit,
            message=message,
            next_action=next_action,
        )

    def _load_local_state(
        self,
    ) -> tuple[SyncStatusSnapshot | None, Exception | None]:
        path = self.repository_path / SYNC_STATE_PATH
        if not path.exists():
            return None, None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("sync state must be an object")
            payload["changed_managed_paths"] = tuple(
                payload["changed_managed_paths"]
            )
            payload["conflict_paths"] = tuple(payload["conflict_paths"])
            return SyncStatusSnapshot(**payload), None
        except (
            KeyError,
            OSError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            return None, error

    def _persist(self, status: SyncStatusSnapshot) -> SyncStatusSnapshot:
        path = self.repository_path / SYNC_STATE_PATH
        self._require_local_path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.parent / f".{path.name}.tmp-{uuid.uuid4().hex}"
        try:
            temporary.write_text(
                json.dumps(
                    status.to_dict(),
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, path)
        except OSError as error:
            raise WorkspaceError(
                code="sync_state_write_failed",
                message="Local synchronization state could not be written.",
                next_action="Check Team Memory local directory permissions.",
            ) from error
        finally:
            temporary.unlink(missing_ok=True)
        return status

    def _managed_changes(self) -> tuple[str, ...]:
        result = self._git(
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
            "--",
            *MANAGED_PATHS,
        )
        records = result.stdout.split("\0")
        changed: set[str] = set()
        index = 0
        while index < len(records):
            record = records[index]
            index += 1
            if not record:
                continue
            if len(record) < 4 or record[2] != " ":
                raise WorkspaceError(
                    code="invalid_git_status",
                    message="Managed Git status output is invalid.",
                    next_action="Inspect the Team Memory Git worktree manually.",
                )
            status = record[:2]
            path = record[3:]
            if "R" in status or "C" in status:
                if index >= len(records) or not records[index]:
                    raise WorkspaceError(
                        code="invalid_git_status",
                        message="Managed Git rename status is incomplete.",
                        next_action="Inspect the Team Memory Git worktree manually.",
                    )
                path = records[index]
                index += 1
            changed.add(Path(path).as_posix())
        return tuple(sorted(changed))

    def _ahead_behind(
        self,
        local_head: str,
        remote_head: str | None,
    ) -> tuple[int, int]:
        if remote_head is None:
            return (self._rev_count(local_head), 0)
        result = self._git(
            "rev-list",
            "--left-right",
            "--count",
            f"{local_head}...{remote_head}",
        )
        try:
            ahead, behind = (int(value) for value in result.stdout.split())
        except (TypeError, ValueError) as error:
            raise WorkspaceError(
                code="invalid_git_history",
                message="Git ahead/behind counts could not be read.",
                next_action="Inspect the Team Memory branch history manually.",
            ) from error
        return ahead, behind

    def _rev_count(self, reference: str) -> int:
        result = self._git("rev-list", "--count", reference)
        try:
            return int(result.stdout.strip())
        except ValueError as error:
            raise WorkspaceError(
                code="invalid_git_history",
                message="Git commit count could not be read.",
                next_action="Inspect the Team Memory branch history manually.",
            ) from error

    def _current_branch(self) -> str:
        branch = self._git("branch", "--show-current").stdout.strip()
        if not branch:
            raise WorkspaceError(
                code="detached_memory_head",
                message="Team Memory must be on a named Git branch.",
                next_action="Check out the team branch before synchronization.",
            )
        return branch

    def _remote_ref(self, branch: str) -> str:
        upstream = self._git(
            "rev-parse",
            "--abbrev-ref",
            "--symbolic-full-name",
            "@{upstream}",
            check=False,
        )
        if upstream.returncode == 0 and upstream.stdout.strip():
            return upstream.stdout.strip()
        return f"refs/remotes/origin/{branch}"

    def _origin_url(self) -> str | None:
        result = self._git("remote", "get-url", "origin", check=False)
        return result.stdout.strip() if result.returncode == 0 else None

    def _rev_parse(self, reference: str) -> str:
        result = self._git("rev-parse", "--verify", reference)
        value = result.stdout.strip()
        if not value:
            raise WorkspaceError(
                code="invalid_git_history",
                message=f"Git reference cannot be resolved: {reference}.",
                next_action="Restore a valid Team Memory branch.",
            )
        return value

    def _optional_rev_parse(self, reference: str) -> str | None:
        result = self._git(
            "rev-parse",
            "--verify",
            reference,
            check=False,
        )
        value = result.stdout.strip()
        return value if result.returncode == 0 and value else None

    def _validate_repository(self) -> None:
        result = self._git(
            "rev-parse",
            "--show-toplevel",
            check=False,
        )
        try:
            root = Path(result.stdout.strip()).resolve()
        except (OSError, ValueError):
            self._invalid_repository()
            return
        if result.returncode != 0 or root != self.repository_path:
            self._invalid_repository()

    def _git(
        self,
        *arguments: str,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        self._validate_git_arguments(arguments)
        try:
            result = subprocess.run(
                ["git", *arguments],
                cwd=self.repository_path,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as error:
            raise WorkspaceError(
                code="git_unavailable",
                message="Git could not be started for Team Memory synchronization.",
                next_action="Install Git and retry synchronization.",
            ) from error
        if check and result.returncode != 0:
            raise WorkspaceError(
                code="git_command_failed",
                message=(
                    result.stderr.strip()[-2000:]
                    or f"Git command failed: {arguments[0]}."
                ),
                next_action="Inspect Team Memory Git status and retry.",
            )
        return result

    @staticmethod
    def _validate_git_arguments(arguments: Sequence[str]) -> None:
        if any(argument in FORBIDDEN_GIT_ARGUMENTS for argument in arguments):
            raise WorkspaceError(
                code="unsafe_git_command",
                message="Force options are forbidden for Team Memory synchronization.",
                next_action="Resolve branch differences with ordinary Git history.",
            )
        if any(argument.startswith("+") and ":" in argument for argument in arguments):
            raise WorkspaceError(
                code="unsafe_git_command",
                message="Force refspecs are forbidden for Team Memory synchronization.",
                next_action="Resolve branch differences with ordinary Git history.",
            )

    def _require_local_path(self, path: Path) -> None:
        expected_root = self.repository_path / ".mlagent-local"
        try:
            path.resolve(strict=False).relative_to(expected_root.resolve())
        except ValueError as error:
            raise WorkspaceError(
                code="unsafe_sync_path",
                message="Synchronization state path escaped the local-only root.",
                next_action="Restore the Team Memory local directory layout.",
            ) from error

    @staticmethod
    def _snapshot(**values: Any) -> SyncStatusSnapshot:
        return SyncStatusSnapshot(**values)

    @staticmethod
    def _invalid_repository() -> None:
        raise WorkspaceError(
            code="invalid_repository",
            message="Team Memory path is not a valid Git worktree.",
            next_action="Restore the Team Memory Git repository.",
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

from __future__ import annotations

import json
import subprocess
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.domain.models import (
    CapacityStatus,
    RemoteStatus,
    WorkspaceError,
    WorkspaceIssue,
)


SCHEMA_VERSION = 1
MANIFEST_PATH = Path(".mlagent/repository.json")
MANAGED_PATHS = (
    "datasets",
    "raw-records",
    "experiences",
    "sops",
    "runs",
    "models",
    "approvals",
)
LOCAL_IGNORE_RULES = (
    ".mlagent-local/",
    ".mlagent-workspace.json",
    ".env",
    "*.pem",
    "*.key",
)
MAX_FILE_BYTES = 100_000_000
MAX_REPOSITORY_BYTES = 20_000_000_000


@dataclass(frozen=True)
class RepositoryStatus:
    repository_id: str
    schema_version: int
    repository_path: Path
    actor_id: str
    managed_paths: tuple[str, ...]
    git_state: str
    remote: RemoteStatus
    capacity: CapacityStatus
    ready: bool
    issues: tuple[WorkspaceIssue, ...]


class MemoryRepository:
    def __init__(
        self,
        id_factory: Callable[[], str] | None = None,
        clock: Callable[[], str] | None = None,
        max_file_bytes: int = MAX_FILE_BYTES,
        max_repository_bytes: int = MAX_REPOSITORY_BYTES,
        warning_ratio: float = 0.8,
        remote_timeout_seconds: float = 5,
    ) -> None:
        self.id_factory = id_factory or (lambda: f"tmr-{uuid.uuid4()}")
        self.clock = clock or _utc_now
        self.max_file_bytes = max_file_bytes
        self.max_repository_bytes = max_repository_bytes
        self.warning_ratio = warning_ratio
        self.remote_timeout_seconds = remote_timeout_seconds

    def bootstrap(
        self,
        repository_path: Path,
        actor_id: str,
        remote_url: str | None = None,
    ) -> RepositoryStatus:
        root = repository_path.expanduser().resolve()
        self._validate_actor(actor_id)
        self._prepare_root(root)

        manifest_path = root / MANIFEST_PATH
        if manifest_path.exists():
            if remote_url is not None:
                self._configure_remote(root, remote_url)
            return self._open(root, actor_id=actor_id, git_state="existing")

        unexpected = [entry.name for entry in root.iterdir() if entry.name != ".git"]
        if unexpected:
            raise WorkspaceError(
                code="unrecognized_repository",
                message=f"Refusing to adopt non-empty directory: {root}",
                next_action="Choose an empty directory or an existing MLagent Team Memory Repository.",
            )

        initialized_git = not (root / ".git").is_dir()
        if initialized_git:
            self._initialize_git(root)

        for managed_path in MANAGED_PATHS:
            (root / managed_path).mkdir(parents=True, exist_ok=True)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest = {
            "asset_type": "team_memory_repository",
            "repository_id": self.id_factory(),
            "schema_version": SCHEMA_VERSION,
            "created_at": self.clock(),
            "created_by": actor_id,
            "managed_paths": list(MANAGED_PATHS),
            "limits": {
                "max_file_bytes": MAX_FILE_BYTES,
                "max_repository_bytes": MAX_REPOSITORY_BYTES,
                "warning_ratio": 0.8,
            },
        }
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        self._merge_ignore_rules(root)
        if remote_url is not None:
            self._configure_remote(root, remote_url)
        return self._open(root, actor_id=actor_id, git_state="initialized")

    def open(self, repository_path: Path, actor_id: str) -> RepositoryStatus:
        root = repository_path.expanduser().resolve()
        self._validate_actor(actor_id)
        return self._open(root, actor_id=actor_id, git_state="existing")

    def _open(
        self,
        root: Path,
        actor_id: str,
        git_state: str,
    ) -> RepositoryStatus:
        if not root.is_dir() or not (root / ".git").is_dir():
            raise WorkspaceError(
                code="invalid_repository",
                message=f"Team Memory Repository is not a Git worktree: {root}",
                next_action="Run bootstrap-memory with an empty directory or restore the repository Git metadata.",
            )

        manifest = self._load_manifest(root / MANIFEST_PATH)
        self._validate_manifest(manifest)
        for managed_path in MANAGED_PATHS:
            (root / managed_path).mkdir(parents=True, exist_ok=True)
        self._merge_ignore_rules(root)

        remote = self._remote_status(root)
        capacity = self._capacity_status(root)
        issues = self._readiness_issues(remote, capacity)

        return RepositoryStatus(
            repository_id=manifest["repository_id"],
            schema_version=manifest["schema_version"],
            repository_path=root,
            actor_id=actor_id,
            managed_paths=tuple(manifest["managed_paths"]),
            git_state=git_state,
            remote=remote,
            capacity=capacity,
            ready=(remote.state not in {"invalid", "unreachable"})
            and capacity.state != "blocked",
            issues=issues,
        )

    @staticmethod
    def _validate_actor(actor_id: str) -> None:
        if not actor_id.strip():
            raise WorkspaceError(
                code="missing_actor",
                message="A non-empty team member identity is required.",
                next_action="Pass --actor with the identity used for repository audit records.",
            )

    @staticmethod
    def _prepare_root(root: Path) -> None:
        if root.exists() and not root.is_dir():
            raise WorkspaceError(
                code="invalid_repository_path",
                message=f"Repository path is not a directory: {root}",
                next_action="Choose a directory path for the Team Memory Repository.",
            )
        root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _initialize_git(root: Path) -> None:
        try:
            result = subprocess.run(
                ["git", "init"],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as error:
            raise WorkspaceError(
                code="git_unavailable",
                message="Git could not be started.",
                next_action="Install Git and make it available on PATH, then retry bootstrap-memory.",
            ) from error
        if result.returncode != 0:
            raise WorkspaceError(
                code="git_init_failed",
                message=result.stderr.strip() or "Git repository initialization failed.",
                next_action="Check directory permissions and run bootstrap-memory again.",
            )

    @staticmethod
    def _load_manifest(path: Path) -> dict[str, Any]:
        if not path.is_file():
            raise WorkspaceError(
                code="missing_manifest",
                message=f"Team Memory manifest is missing: {path}",
                next_action="Restore .mlagent/repository.json from Git or bootstrap an empty repository.",
            )
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise WorkspaceError(
                code="invalid_manifest",
                message=f"Team Memory manifest is not valid JSON: {path}",
                next_action="Restore a valid .mlagent/repository.json from Git before reopening the workspace.",
            ) from error
        if not isinstance(payload, dict):
            raise WorkspaceError(
                code="invalid_manifest",
                message="Team Memory manifest must be a JSON object.",
                next_action="Restore a valid .mlagent/repository.json from Git before reopening the workspace.",
            )
        return payload

    @staticmethod
    def _validate_manifest(manifest: dict[str, Any]) -> None:
        required = {
            "asset_type",
            "repository_id",
            "schema_version",
            "created_at",
            "created_by",
            "managed_paths",
        }
        if not required.issubset(manifest):
            raise WorkspaceError(
                code="invalid_manifest",
                message="Team Memory manifest is missing required fields.",
                next_action="Restore the complete manifest from Git before reopening the workspace.",
            )
        if manifest["schema_version"] != SCHEMA_VERSION:
            raise WorkspaceError(
                code="unsupported_schema",
                message=f"Schema version {manifest['schema_version']} is not supported.",
                next_action=f"Use a repository with schema version {SCHEMA_VERSION} or run an approved migration.",
            )
        if manifest["asset_type"] != "team_memory_repository":
            raise WorkspaceError(
                code="invalid_manifest",
                message="Manifest asset_type is not team_memory_repository.",
                next_action="Restore the Team Memory manifest from Git.",
            )
        if tuple(manifest["managed_paths"]) != MANAGED_PATHS:
            raise WorkspaceError(
                code="invalid_manifest",
                message="Manifest managed_paths do not match schema version 1.",
                next_action="Restore the schema version 1 managed path declaration from Git.",
            )

    @staticmethod
    def _merge_ignore_rules(root: Path) -> None:
        ignore_path = root / ".gitignore"
        existing_text = ignore_path.read_text(encoding="utf-8") if ignore_path.exists() else ""
        existing_rules = existing_text.splitlines()
        missing = [rule for rule in LOCAL_IGNORE_RULES if rule not in existing_rules]
        if not missing:
            return
        prefix = "" if not existing_text or existing_text.endswith("\n") else "\n"
        ignore_path.write_text(
            existing_text + prefix + "\n".join(missing) + "\n",
            encoding="utf-8",
        )

    def _configure_remote(self, root: Path, remote_url: str) -> None:
        if remote_url.startswith(("http://", "https://")) or (
            "://" in remote_url and not remote_url.startswith("ssh://")
        ):
            raise WorkspaceError(
                code="remote_not_ssh",
                message="Team Memory network remotes must use SSH.",
                next_action="Configure an SSH remote and ensure the team SSH identity is available.",
            )

        existing = self._git_remote_url(root)
        if existing is not None and existing != remote_url:
            raise WorkspaceError(
                code="remote_mismatch",
                message=f"Origin remote is already configured as {existing}.",
                next_action="Use the configured Team Memory remote or change it manually after team review.",
            )
        if existing is not None:
            return

        result = subprocess.run(
            ["git", "remote", "add", "origin", remote_url],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise WorkspaceError(
                code="remote_configuration_failed",
                message=result.stderr.strip() or "Git origin could not be configured.",
                next_action="Check the remote URL and repository permissions, then retry bootstrap-memory.",
            )

    def _remote_status(self, root: Path) -> RemoteStatus:
        remote_url = self._git_remote_url(root)
        if remote_url is None:
            return RemoteStatus(
                state="not_configured",
                url=None,
                message="No origin remote configured.",
            )
        if remote_url.startswith(("http://", "https://")):
            return RemoteStatus(
                state="invalid",
                url=remote_url,
                message="Origin is not an SSH remote.",
            )
        try:
            result = subprocess.run(
                ["git", "ls-remote", "origin"],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
                timeout=self.remote_timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired):
            return RemoteStatus(
                state="unreachable",
                url=remote_url,
                message="Origin did not respond before the readiness timeout.",
            )
        if result.returncode == 0:
            return RemoteStatus(
                state="reachable",
                url=remote_url,
                message="Origin is reachable.",
            )
        return RemoteStatus(
            state="unreachable",
            url=remote_url,
            message="Origin could not be reached with the current Git/SSH identity.",
        )

    @staticmethod
    def _git_remote_url(root: Path) -> str | None:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout.strip() if result.returncode == 0 else None

    def _capacity_status(self, root: Path) -> CapacityStatus:
        sizes = [
            path.stat().st_size
            for path in root.rglob("*")
            if path.is_file()
            and ".git" not in path.relative_to(root).parts
            and ".mlagent-local" not in path.relative_to(root).parts
        ]
        bytes_used = sum(sizes)
        largest_file_bytes = max(sizes, default=0)
        if (
            largest_file_bytes >= self.max_file_bytes
            or bytes_used >= self.max_repository_bytes
        ):
            state = "blocked"
        elif bytes_used >= int(self.max_repository_bytes * self.warning_ratio):
            state = "warning"
        else:
            state = "ok"
        return CapacityStatus(
            state=state,
            bytes_used=bytes_used,
            largest_file_bytes=largest_file_bytes,
            max_file_bytes=self.max_file_bytes,
            max_repository_bytes=self.max_repository_bytes,
        )

    @staticmethod
    def _readiness_issues(
        remote: RemoteStatus,
        capacity: CapacityStatus,
    ) -> tuple[WorkspaceIssue, ...]:
        issues: list[WorkspaceIssue] = []
        if remote.state == "invalid":
            issues.append(
                WorkspaceIssue(
                    code="remote_not_ssh",
                    message="The configured origin is not an SSH remote.",
                    next_action="Configure an SSH remote before team synchronization.",
                )
            )
        elif remote.state == "unreachable":
            issues.append(
                WorkspaceIssue(
                    code="remote_unreachable",
                    message="The configured origin is not reachable.",
                    next_action="Check the remote path, SSH agent, access grants, and network, then retry.",
                )
            )

        if capacity.largest_file_bytes >= capacity.max_file_bytes:
            issues.append(
                WorkspaceIssue(
                    code="file_too_large",
                    message="At least one managed file is at or above the single-file limit.",
                    next_action="Remove or replace the oversized file before committing managed assets.",
                )
            )
        if capacity.bytes_used >= capacity.max_repository_bytes:
            issues.append(
                WorkspaceIssue(
                    code="repository_capacity_exceeded",
                    message="The Team Memory Repository is at or above its capacity limit.",
                    next_action="Archive approved historical assets before adding new large files.",
                )
            )
        elif capacity.state == "warning":
            issues.append(
                WorkspaceIssue(
                    code="repository_capacity_warning",
                    message="The Team Memory Repository has reached its maintenance threshold.",
                    next_action="Plan an archive review before the repository reaches its hard limit.",
                )
            )
        return tuple(issues)


def _utc_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat().replace("+00:00", "Z")

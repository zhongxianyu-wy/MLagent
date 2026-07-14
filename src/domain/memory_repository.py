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
    ) -> None:
        self.id_factory = id_factory or (lambda: f"tmr-{uuid.uuid4()}")
        self.clock = clock or _utc_now

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

        return RepositoryStatus(
            repository_id=manifest["repository_id"],
            schema_version=manifest["schema_version"],
            repository_path=root,
            actor_id=actor_id,
            managed_paths=tuple(manifest["managed_paths"]),
            git_state=git_state,
            remote=RemoteStatus(
                state="not_configured",
                url=None,
                message="No origin remote configured.",
            ),
            capacity=self._capacity_status(root),
            ready=True,
            issues=(),
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

    @staticmethod
    def _capacity_status(root: Path) -> CapacityStatus:
        sizes = [
            path.stat().st_size
            for path in root.rglob("*")
            if path.is_file()
            and ".git" not in path.relative_to(root).parts
            and ".mlagent-local" not in path.relative_to(root).parts
        ]
        return CapacityStatus(
            state="ok",
            bytes_used=sum(sizes),
            largest_file_bytes=max(sizes, default=0),
            max_file_bytes=MAX_FILE_BYTES,
            max_repository_bytes=MAX_REPOSITORY_BYTES,
        )


def _utc_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat().replace("+00:00", "Z")

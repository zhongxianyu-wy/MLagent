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
        self._validate_capacity_policy(
            self.max_file_bytes,
            self.max_repository_bytes,
            self.warning_ratio,
        )
        if remote_url is not None:
            self._validate_remote_url(remote_url, root)
        self._prepare_root(root)

        manifest_path = root / MANIFEST_PATH
        if manifest_path.exists():
            current = self._open(root, actor_id=actor_id, git_state="existing")
            if remote_url is None:
                return current
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

        repository_id = self.id_factory()
        if not isinstance(repository_id, str) or not repository_id.strip():
            raise WorkspaceError(
                code="invalid_repository_id",
                message="The generated Team Memory Repository ID is empty or invalid.",
                next_action="Retry with a repository ID generator that returns a stable non-empty string.",
            )
        manifest = {
            "asset_type": "team_memory_repository",
            "repository_id": repository_id,
            "schema_version": SCHEMA_VERSION,
            "created_at": self.clock(),
            "created_by": actor_id,
            "managed_paths": list(MANAGED_PATHS),
            "limits": {
                "max_file_bytes": self.max_file_bytes,
                "max_repository_bytes": self.max_repository_bytes,
                "warning_ratio": self.warning_ratio,
            },
        }
        self._validate_manifest(manifest)

        try:
            for managed_path in MANAGED_PATHS:
                (root / managed_path).mkdir(parents=True, exist_ok=True)
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            self._merge_ignore_rules(root)
            self._commit_bootstrap(root, actor_id=actor_id)
        except WorkspaceError:
            self._rollback_bootstrap_assets(root)
            raise
        except OSError as error:
            self._rollback_bootstrap_assets(root)
            raise WorkspaceError(
                code="bootstrap_write_failed",
                message="Team Memory bootstrap assets could not be written.",
                next_action="Check repository permissions, then retry bootstrap-memory.",
            ) from error
        if remote_url is not None:
            self._configure_remote(root, remote_url)
        return self._open(root, actor_id=actor_id, git_state="initialized")

    def open(self, repository_path: Path, actor_id: str) -> RepositoryStatus:
        root = repository_path.expanduser().resolve()
        self._validate_actor(actor_id)
        return self._open(root, actor_id=actor_id, git_state="existing")

    def capacity_status(self, repository_path: Path) -> CapacityStatus:
        root = repository_path.expanduser().resolve()
        if not root.is_dir() or not (root / ".git").is_dir():
            raise WorkspaceError(
                code="invalid_repository",
                message=f"Team Memory Repository is not a Git worktree: {root}",
                next_action="Restore the repository before checking capacity.",
            )
        manifest = self._load_manifest(root / MANIFEST_PATH)
        self._validate_manifest(manifest)
        return self._capacity_status(root, manifest["limits"])

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
        self._validate_git_repository(root)

        manifest = self._load_manifest(root / MANIFEST_PATH)
        self._validate_manifest(manifest)
        self._validate_authoritative_manifest_clean(root)
        self._validate_repository_origin_history(
            root,
            manifest,
        )
        for managed_path in MANAGED_PATHS:
            (root / managed_path).mkdir(parents=True, exist_ok=True)
        self._merge_ignore_rules(root)

        remote = self._remote_status(root)
        capacity = self._capacity_status(root, manifest["limits"])
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
    def _validate_capacity_policy(
        max_file_bytes: int,
        max_repository_bytes: int,
        warning_ratio: float,
    ) -> None:
        if not MemoryRepository._capacity_policy_is_valid(
            max_file_bytes,
            max_repository_bytes,
            warning_ratio,
        ):
            raise WorkspaceError(
                code="invalid_capacity_policy",
                message="Team Memory capacity limits are invalid.",
                next_action="Use positive limits at or below 100 MB per file and 20 GB per repository, with a warning ratio greater than 0 and no later than 0.8.",
            )

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
    def _commit_bootstrap(root: Path, actor_id: str) -> None:
        try:
            staged = subprocess.run(
                ["git", "add", "--", ".gitignore", str(MANIFEST_PATH)],
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
        if staged.returncode != 0:
            raise WorkspaceError(
                code="git_stage_failed",
                message=staged.stderr.strip() or "Bootstrap assets could not be staged.",
                next_action="Check Git repository permissions, then retry bootstrap-memory.",
            )
        try:
            committed = subprocess.run(
                [
                    "git",
                    "-c",
                    f"user.name={actor_id}",
                    "-c",
                    "user.email=mlagent@local",
                    "commit",
                    "-m",
                    "chore(memory): initialize team memory repository",
                ],
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
        if committed.returncode != 0:
            raise WorkspaceError(
                code="git_commit_failed",
                message=committed.stderr.strip() or "Bootstrap assets could not be committed.",
                next_action="Check Git repository permissions and identity, then retry bootstrap-memory.",
            )

    @staticmethod
    def _validate_git_repository(root: Path) -> None:
        try:
            worktree = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )
            head = subprocess.run(
                ["git", "rev-parse", "--verify", "HEAD"],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )
            committed_manifest = subprocess.run(
                ["git", "cat-file", "-e", f"HEAD:{MANIFEST_PATH}"],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as error:
            raise WorkspaceError(
                code="git_unavailable",
                message="Git could not be started.",
                next_action="Install Git and make it available on PATH, then reopen the workspace.",
            ) from error
        if (
            worktree.returncode != 0
            or Path(worktree.stdout.strip()).resolve() != root
            or head.returncode != 0
            or committed_manifest.returncode != 0
        ):
            raise WorkspaceError(
                code="invalid_repository",
                message=f"Team Memory path is not a valid versioned Git repository: {root}",
                next_action="Restore valid Git metadata and the committed Team Memory manifest, or bootstrap an empty directory.",
            )

    @staticmethod
    def _validate_authoritative_manifest_clean(root: Path) -> None:
        try:
            result = subprocess.run(
                ["git", "diff", "--quiet", "HEAD", "--", str(MANIFEST_PATH)],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as error:
            raise WorkspaceError(
                code="git_unavailable",
                message="Git could not be started.",
                next_action="Install Git and make it available on PATH, then reopen the workspace.",
            ) from error
        if result.returncode == 1:
            raise WorkspaceError(
                code="authoritative_manifest_modified",
                message="The Team Memory manifest differs from the committed Git snapshot.",
                next_action="Restore the manifest from Git or commit an approved manifest change before reopening the workspace.",
            )
        if result.returncode != 0:
            raise WorkspaceError(
                code="invalid_repository",
                message="The committed Team Memory manifest could not be compared with the worktree.",
                next_action="Restore valid Git metadata and retry opening the workspace.",
            )

    @staticmethod
    def _validate_repository_origin_history(
        root: Path,
        current_manifest: dict[str, Any],
    ) -> None:
        try:
            history = subprocess.run(
                [
                    "git",
                    "log",
                    "--diff-filter=A",
                    "--format=%H",
                    "--reverse",
                    "--",
                    str(MANIFEST_PATH),
                ],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )
            introduction_commits = history.stdout.splitlines()
            if history.returncode != 0 or not introduction_commits:
                raise WorkspaceError(
                    code="invalid_repository",
                    message="The Team Memory manifest has no committed introduction point.",
                    next_action="Restore the original committed manifest history before reopening the workspace.",
                )
            original = subprocess.run(
                [
                    "git",
                    "show",
                    f"{introduction_commits[0]}:{MANIFEST_PATH}",
                ],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as error:
            raise WorkspaceError(
                code="git_unavailable",
                message="Git could not be started.",
                next_action="Install Git and make it available on PATH, then reopen the workspace.",
            ) from error
        try:
            original_manifest = json.loads(original.stdout)
            original_repository_id = original_manifest["repository_id"]
            original_created_by = original_manifest["created_by"]
            original_created_at = original_manifest["created_at"]
        except (json.JSONDecodeError, KeyError, TypeError) as error:
            raise WorkspaceError(
                code="invalid_repository",
                message="The original Team Memory repository identity is invalid.",
                next_action="Restore the original committed manifest history before reopening the workspace.",
            ) from error
        if (
            original.returncode != 0
            or not isinstance(original_repository_id, str)
            or not original_repository_id.strip()
            or not isinstance(original_created_by, str)
            or not original_created_by.strip()
            or not isinstance(original_created_at, str)
            or not original_created_at.strip()
        ):
            raise WorkspaceError(
                code="invalid_repository",
                message="The original Team Memory repository identity cannot be read.",
                next_action="Restore the original committed manifest history before reopening the workspace.",
            )
        if original_repository_id != current_manifest["repository_id"]:
            raise WorkspaceError(
                code="repository_identity_changed",
                message="The committed Team Memory repository ID differs from its original value.",
                next_action="Restore the original repository_id and commit that correction before reopening the workspace.",
            )
        if (
            original_created_by != current_manifest["created_by"]
            or original_created_at != current_manifest["created_at"]
        ):
            raise WorkspaceError(
                code="repository_provenance_changed",
                message="The committed Team Memory creation provenance differs from its original values.",
                next_action="Restore the original created_by and created_at values and commit that correction before reopening the workspace.",
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
            "limits",
        }
        if not required.issubset(manifest):
            raise WorkspaceError(
                code="invalid_manifest",
                message="Team Memory manifest is missing required fields.",
                next_action="Restore the complete manifest from Git before reopening the workspace.",
            )
        if type(manifest["schema_version"]) is not int:
            raise WorkspaceError(
                code="invalid_manifest",
                message="Manifest schema_version must be an integer.",
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
        if (
            not isinstance(manifest["repository_id"], str)
            or not manifest["repository_id"].strip()
            or not isinstance(manifest["created_at"], str)
            or not manifest["created_at"].strip()
            or not isinstance(manifest["created_by"], str)
            or not manifest["created_by"].strip()
        ):
            raise WorkspaceError(
                code="invalid_manifest",
                message="Manifest identity and audit fields must be non-empty strings.",
                next_action="Restore the complete manifest from Git before reopening the workspace.",
            )
        if (
            not isinstance(manifest["managed_paths"], list)
            or not all(isinstance(path, str) for path in manifest["managed_paths"])
            or tuple(manifest["managed_paths"]) != MANAGED_PATHS
        ):
            raise WorkspaceError(
                code="invalid_manifest",
                message="Manifest managed_paths do not match schema version 1.",
                next_action="Restore the schema version 1 managed path declaration from Git.",
            )
        limits = manifest["limits"]
        if (
            not isinstance(limits, dict)
            or not MemoryRepository._capacity_policy_is_valid(
                limits.get("max_file_bytes"),
                limits.get("max_repository_bytes"),
                limits.get("warning_ratio"),
            )
        ):
            raise WorkspaceError(
                code="invalid_manifest",
                message="Manifest capacity limits do not match schema version 1.",
                next_action="Restore the complete manifest from Git before reopening the workspace.",
            )

    @staticmethod
    def _capacity_policy_is_valid(
        max_file_bytes: Any,
        max_repository_bytes: Any,
        warning_ratio: Any,
    ) -> bool:
        return (
            type(max_file_bytes) is int
            and max_file_bytes > 0
            and max_file_bytes <= MAX_FILE_BYTES
            and type(max_repository_bytes) is int
            and max_repository_bytes > 0
            and max_repository_bytes <= MAX_REPOSITORY_BYTES
            and type(warning_ratio) in {int, float}
            and 0 < warning_ratio <= 0.8
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
    def _rollback_bootstrap_assets(root: Path) -> None:
        try:
            subprocess.run(
                [
                    "git",
                    "rm",
                    "--cached",
                    "-f",
                    "--ignore-unmatch",
                    "--",
                    ".gitignore",
                    str(MANIFEST_PATH),
                ],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            pass
        for path in (root / MANIFEST_PATH, root / ".gitignore"):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        for managed_path in MANAGED_PATHS:
            try:
                (root / managed_path).rmdir()
            except OSError:
                pass
        try:
            (root / MANIFEST_PATH.parent).rmdir()
        except OSError:
            pass

    def _configure_remote(self, root: Path, remote_url: str) -> None:
        self._validate_remote_url(remote_url, root)

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
        if not self._is_supported_remote(remote_url, root):
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

    @staticmethod
    def _is_supported_remote(
        remote_url: str,
        repository_root: Path | None = None,
    ) -> bool:
        if not remote_url.strip():
            return False
        if remote_url.startswith("ssh://"):
            return True
        if remote_url.startswith("git@"):
            return ":" in remote_url.removeprefix("git@")
        if remote_url.startswith("file://"):
            return True
        if "://" in remote_url:
            return False
        if remote_url.startswith(("/", "./", "../", "~")):
            return True
        if (
            len(remote_url) >= 3
            and remote_url[0].isalpha()
            and remote_url[1] == ":"
            and remote_url[2] in {"/", "\\"}
        ):
            return True
        if repository_root is not None:
            local_path = Path(remote_url).expanduser()
            if not local_path.is_absolute():
                local_path = repository_root / local_path
            if local_path.exists():
                return True
        return ":" not in remote_url

    @staticmethod
    def _validate_remote_url(remote_url: str, repository_root: Path) -> None:
        if not MemoryRepository._is_supported_remote(remote_url, repository_root):
            raise WorkspaceError(
                code="remote_not_ssh",
                message="Team Memory network remotes must use SSH.",
                next_action="Configure an SSH remote and ensure the team SSH identity is available.",
            )

    @staticmethod
    def _capacity_status(root: Path, limits: dict[str, Any]) -> CapacityStatus:
        max_file_bytes = limits["max_file_bytes"]
        max_repository_bytes = limits["max_repository_bytes"]
        warning_ratio = limits["warning_ratio"]
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
            largest_file_bytes >= max_file_bytes
            or bytes_used >= max_repository_bytes
        ):
            state = "blocked"
        elif bytes_used >= int(max_repository_bytes * warning_ratio):
            state = "warning"
        else:
            state = "ok"
        return CapacityStatus(
            state=state,
            bytes_used=bytes_used,
            largest_file_bytes=largest_file_bytes,
            max_file_bytes=max_file_bytes,
            max_repository_bytes=max_repository_bytes,
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

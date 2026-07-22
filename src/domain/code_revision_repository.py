"""Code Revision repository — immutable, versioned, fingerprint-sealed.

Mirrors DatasetRepository's storage mechanics (atomic tmp+rename write,
idempotency, load-time tamper detection, capacity gate) and SopVersion's
parent-chain shape. The editable Code Revision layer is deliberately separate
from the frozen per-run ``FrozenCodeRevisionSnapshot`` (lives under
``runs/<run_id>/code-revisions/``); this repository owns the top-level
``code-revisions/<code_id>/v<NNNN>/`` namespace.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from src.domain.models import (
    CODE_REVISION_SCHEMA_VERSION,
    CapacityStatus,
    CandidateCodeFile,
    CodeRevisionSnapshot,
    WorkspaceError,
)

VERSION_DIRECTORY_PATTERN = re.compile(r"^v([0-9]{4})$")


def compute_code_fingerprint(files: tuple[CandidateCodeFile, ...]) -> str:
    """Canonical-JSON SHA-256 over ``[{path, sha256, size_bytes}, ...]``.

    Identical algorithm to ``exploration_repository._code_fingerprint`` so a
    Code Revision's fingerprint is directly comparable to a frozen run's
    ``code_fingerprint`` and a plan's recorded code fingerprint.
    """
    payload = [
        {"path": item.path, "sha256": item.sha256, "size_bytes": item.size_bytes}
        for item in files
    ]
    return _fingerprint(payload)


def _fingerprint(payload: Any) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _utc_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class CodeRevisionRepository:
    def __init__(
        self,
        repository_path: Path,
        clock: Callable[[], str] | None = None,
        version_id_factory: Callable[[str, int], str] | None = None,
    ) -> None:
        self.repository_path = repository_path.expanduser().resolve()
        self.code_revisions_path = self.repository_path / "code-revisions"
        self.clock = clock or _utc_now
        self.version_id_factory = (
            version_id_factory
            or (lambda code_id, version: f"{code_id}-v{version:04d}")
        )

    def create(
        self,
        *,
        code_id: str,
        code_fingerprint: str,
        entrypoint_path: str,
        files: tuple[CandidateCodeFile, ...],
        files_bytes: dict[str, bytes],
        parent_revision_id: str | None,
        parent_revision_fingerprint: str | None,
        change_summary: str,
        origin: str,
        source_run_id: str | None,
        source_instance_id: str | None,
        created_by: str,
        capacity: CapacityStatus,
        agent_prompt_hash: str | None = None,
        agent_tool_summary: str | None = None,
    ) -> CodeRevisionSnapshot:
        self._validate_managed_path(self.code_revisions_path)
        family_path = self.code_revisions_path / code_id
        self._validate_managed_path(family_path)

        existing = self._version_numbers(code_id)
        for version in existing:  # idempotent: same fingerprint ⇒ return existing
            snapshot = self.load(code_id, version)
            if snapshot.revision_fingerprint == code_fingerprint:
                return snapshot

        version = max(existing, default=0) + 1
        created_at = self.clock()
        if not isinstance(created_at, str) or not created_at.strip():
            raise WorkspaceError(
                code="invalid_code_revision",
                message="Code Revision creation time is empty or invalid.",
                next_action="Retry with a valid UTC clock before writing authoritative assets.",
            )
        asset_id = self.version_id_factory(code_id, version)
        manifest = self._build_manifest(
            asset_id=asset_id,
            code_id=code_id,
            version=version,
            code_fingerprint=code_fingerprint,
            entrypoint_path=entrypoint_path,
            files=files,
            parent_revision_id=parent_revision_id,
            parent_revision_fingerprint=parent_revision_fingerprint,
            change_summary=change_summary,
            origin=origin,
            source_run_id=source_run_id,
            source_instance_id=source_instance_id,
            created_at=created_at,
            created_by=created_by,
            agent_prompt_hash=agent_prompt_hash,
            agent_tool_summary=agent_tool_summary,
        )
        manifest_bytes = self._manifest_bytes(manifest)
        encoded: dict[str, bytes] = {"manifest.json": manifest_bytes}
        for rel, content in files_bytes.items():
            encoded[f"files/{rel}"] = content
        self._validate_capacity(encoded, capacity)

        version_name = f"v{version:04d}"
        version_path = family_path / version_name
        if version_path.exists():
            raise WorkspaceError(
                code="code_revision_exists",
                message=f"Code Revision path already exists: {version_path}",
                next_action="Reload the existing version or create the next reviewed version.",
            )
        family_path.mkdir(parents=True, exist_ok=True)
        self._validate_managed_path(family_path)
        temporary_path = family_path / f".{version_name}.tmp-{uuid.uuid4().hex}"
        try:
            temporary_path.mkdir()
            for filename, content in encoded.items():
                target = temporary_path / filename
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            temporary_path.rename(version_path)
        except OSError as error:
            shutil.rmtree(temporary_path, ignore_errors=True)
            try:
                family_path.rmdir()
            except OSError:
                pass
            raise WorkspaceError(
                code="code_revision_write_failed",
                message="The Code Revision could not be written atomically.",
                next_action="Check Team Memory permissions and free disk space, then retry.",
            ) from error
        return self.load(code_id, version)

    def load(
        self,
        code_id: str,
        version: int | None = None,
    ) -> CodeRevisionSnapshot:
        self._validate_managed_path(self.code_revisions_path / code_id)
        existing = self._version_numbers(code_id)
        if not existing:
            raise WorkspaceError(
                code="code_revision_not_found",
                message=f"No Code Revision found for code_id '{code_id}'.",
                next_action="Create the first Code Revision before loading it.",
            )
        selected = version if version is not None else max(existing)
        if selected not in existing:
            raise WorkspaceError(
                code="code_revision_not_found",
                message=f"Code Revision '{code_id}' v{selected} does not exist.",
                next_action="Reload the Code Review and pick an existing version.",
            )
        version_path = self.code_revisions_path / code_id / f"v{selected:04d}"
        manifest_path = version_path / "manifest.json"
        self._validate_managed_path(manifest_path)
        manifest = self._load_manifest(manifest_path)
        if (
            manifest.get("asset_type") != "code_revision"
            or manifest.get("code_id") != code_id
            or manifest.get("version") != selected
            or manifest.get("schema_version") != CODE_REVISION_SCHEMA_VERSION
            or manifest.get("asset_id") != self.version_id_factory(code_id, selected)
        ):
            self._invalid("identity fields do not match the asset path")
        self._validate_manifest_fingerprint(manifest)
        self._validate_code_fingerprint(manifest, version_path)
        asset_path = f"code-revisions/{code_id}/v{selected:04d}/manifest.json"
        return self._snapshot(manifest, asset_path)

    def list_revisions(self, code_id: str) -> tuple[CodeRevisionSnapshot, ...]:
        family_path = self.code_revisions_path / code_id
        self._validate_managed_path(family_path)
        versions = self._version_numbers(code_id)
        snapshots = [self.load(code_id, version) for version in versions]
        snapshots.sort(key=lambda snapshot: snapshot.version, reverse=True)
        return tuple(snapshots)

    def latest(self, code_id: str) -> CodeRevisionSnapshot | None:
        revisions = self.list_revisions(code_id)
        return revisions[0] if revisions else None

    def read_all_file_bytes(
        self,
        code_id: str,
        version: int,
    ) -> dict[str, bytes]:
        """Read every managed file's bytes for a revision (jail-gated)."""
        version_path = self.code_revisions_path / code_id / f"v{version:04d}"
        manifest = self._load_manifest(version_path / "manifest.json")
        files_dir = version_path / "files"
        result: dict[str, bytes] = {}
        for entry in manifest["files"]:
            rel = entry["path"]
            file_path = files_dir / rel
            self._validate_managed_path(file_path)
            try:
                result[rel] = file_path.read_bytes()
            except OSError as error:
                raise WorkspaceError(
                    code="code_revision_fingerprint_mismatch",
                    message=f"A Code Revision file is missing or unreadable: {rel}",
                    next_action="Restore the immutable Code Revision from Git.",
                ) from error
        return result

    def _version_numbers(self, code_id: str) -> list[int]:
        family_path = self.code_revisions_path / code_id
        self._validate_managed_path(family_path)
        if not family_path.is_dir():
            return []
        versions: list[int] = []
        for path in family_path.iterdir():
            self._validate_managed_path(path)
            match = VERSION_DIRECTORY_PATTERN.fullmatch(path.name)
            if path.is_dir() and match is not None:
                versions.append(int(match.group(1)))
        return sorted(versions)

    def _validate_managed_path(self, path: Path) -> None:
        try:
            relative = path.relative_to(self.repository_path)
        except ValueError:
            self._unsafe_path()
            return
        current = self.repository_path
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                self._unsafe_path()
        try:
            path.resolve(strict=False).relative_to(self.repository_path)
        except ValueError:
            self._unsafe_path()

    @staticmethod
    def _unsafe_path() -> None:
        raise WorkspaceError(
            code="unsafe_code_revision_path",
            message="A Code Revision path uses a symbolic link or resolves outside Team Memory.",
            next_action="Replace symbolic links with real directories inside the Team Memory Repository.",
        )

    @staticmethod
    def _build_manifest(
        *,
        asset_id: str,
        code_id: str,
        version: int,
        code_fingerprint: str,
        entrypoint_path: str,
        files: tuple[CandidateCodeFile, ...],
        parent_revision_id: str | None,
        parent_revision_fingerprint: str | None,
        change_summary: str,
        origin: str,
        source_run_id: str | None,
        source_instance_id: str | None,
        created_at: str,
        created_by: str,
        agent_prompt_hash: str | None = None,
        agent_tool_summary: str | None = None,
    ) -> dict[str, Any]:
        manifest: dict[str, Any] = {
            "asset_type": "code_revision",
            "asset_id": asset_id,
            "schema_version": CODE_REVISION_SCHEMA_VERSION,
            "code_id": code_id,
            "version": version,
            "revision_fingerprint": code_fingerprint,
            "code_fingerprint": code_fingerprint,
            "parent_revision_id": parent_revision_id,
            "parent_revision_fingerprint": parent_revision_fingerprint,
            "entrypoint_path": entrypoint_path,
            "origin": origin,
            "source_run_id": source_run_id,
            "source_instance_id": source_instance_id,
            "change_summary": change_summary,
            "files": [
                {"path": f.path, "sha256": f.sha256, "size_bytes": f.size_bytes}
                for f in files
            ],
            "created_at": created_at,
            "created_by": created_by,
            "agent_prompt_hash": agent_prompt_hash,
            "agent_tool_summary": agent_tool_summary,
        }
        manifest["manifest_fingerprint"] = CodeRevisionRepository._manifest_fingerprint(
            manifest
        )
        return manifest

    @staticmethod
    def _manifest_bytes(manifest: dict[str, Any]) -> bytes:
        return (
            json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        ).encode("utf-8")

    @staticmethod
    def _manifest_fingerprint(manifest: dict[str, Any]) -> str:
        payload = {
            key: value
            for key, value in manifest.items()
            if key != "manifest_fingerprint"
        }
        return _fingerprint(payload)

    @staticmethod
    def _validate_capacity(
        encoded_files: dict[str, bytes],
        capacity: CapacityStatus,
    ) -> None:
        oversized = [
            filename
            for filename, content in encoded_files.items()
            if len(content) >= capacity.max_file_bytes
        ]
        if oversized:
            raise WorkspaceError(
                code="file_too_large",
                message=f"Code Revision files reach the single-file limit: {', '.join(oversized)}",
                next_action="Reduce or partition the source before creating a Git-backed Code Revision.",
            )
        projected_size = capacity.bytes_used + sum(
            len(content) for content in encoded_files.values()
        )
        if projected_size >= capacity.max_repository_bytes:
            raise WorkspaceError(
                code="repository_capacity_exceeded",
                message="The Code Revision would reach the Team Memory capacity limit.",
                next_action="Archive reviewed assets or choose smaller code before saving this version.",
            )

    @staticmethod
    def _load_manifest(path: Path) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise WorkspaceError(
                code="invalid_code_revision",
                message=f"Code Revision manifest cannot be read: {path}",
                next_action="Restore the immutable Code Revision from Git.",
            ) from error
        if not isinstance(payload, dict):
            raise WorkspaceError(
                code="invalid_code_revision",
                message="Code Revision manifest must be a JSON object.",
                next_action="Restore the immutable Code Revision from Git.",
            )
        return payload

    @staticmethod
    def _validate_manifest_fingerprint(manifest: dict[str, Any]) -> None:
        actual = manifest.get("manifest_fingerprint")
        expected = CodeRevisionRepository._manifest_fingerprint(manifest)
        if actual != expected:
            raise WorkspaceError(
                code="code_revision_fingerprint_mismatch",
                message="Code Revision manifest fingerprint does not match its contents.",
                next_action="Restore the immutable Code Revision from Git.",
            )

    def _validate_code_fingerprint(
        self,
        manifest: dict[str, Any],
        version_path: Path,
    ) -> None:
        actual_files: list[CandidateCodeFile] = []
        for entry in manifest["files"]:
            rel = entry["path"]
            file_path = version_path / "files" / rel
            self._validate_managed_path(file_path)
            try:
                content = file_path.read_bytes()
            except OSError as error:
                raise WorkspaceError(
                    code="code_revision_fingerprint_mismatch",
                    message=f"A Code Revision file is missing or unreadable: {rel}",
                    next_action="Restore the immutable Code Revision from Git.",
                ) from error
            sha = hashlib.sha256(content).hexdigest()
            if sha != entry["sha256"] or len(content) != entry["size_bytes"]:
                raise WorkspaceError(
                    code="code_revision_fingerprint_mismatch",
                    message="Code Revision files have changed in place.",
                    next_action="Restore the immutable Code Revision from Git and create a new version for changes.",
                )
            actual_files.append(
                CandidateCodeFile(path=rel, sha256=sha, size_bytes=len(content))
            )
        if (
            compute_code_fingerprint(tuple(actual_files))
            != manifest["revision_fingerprint"]
        ):
            raise WorkspaceError(
                code="code_revision_fingerprint_mismatch",
                message="Code Revision fingerprint does not match its files.",
                next_action="Restore the immutable Code Revision from Git.",
            )

    @staticmethod
    def _snapshot(
        manifest: dict[str, Any],
        asset_path: str,
    ) -> CodeRevisionSnapshot:
        return CodeRevisionSnapshot(
            asset_id=manifest["asset_id"],
            asset_path=asset_path,
            code_id=manifest["code_id"],
            version=manifest["version"],
            revision_fingerprint=manifest["revision_fingerprint"],
            parent_revision_id=manifest["parent_revision_id"],
            parent_revision_fingerprint=manifest["parent_revision_fingerprint"],
            code_fingerprint=manifest["code_fingerprint"],
            entrypoint_path=manifest["entrypoint_path"],
            files=tuple(
                CandidateCodeFile(
                    path=f["path"], sha256=f["sha256"], size_bytes=f["size_bytes"]
                )
                for f in manifest["files"]
            ),
            origin=manifest["origin"],
            source_run_id=manifest["source_run_id"],
            source_instance_id=manifest["source_instance_id"],
            change_summary=manifest["change_summary"],
            created_at=manifest["created_at"],
            created_by=manifest["created_by"],
            agent_prompt_hash=manifest.get("agent_prompt_hash"),
            agent_tool_summary=manifest.get("agent_tool_summary"),
        )

    @staticmethod
    def _invalid(detail: str) -> None:
        raise WorkspaceError(
            code="invalid_code_revision",
            message=f"Code Revision manifest is invalid: {detail}",
            next_action="Restore the immutable Code Revision from Git.",
        )

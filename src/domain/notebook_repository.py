"""Notebook repository — stores notebook imports as immutable Team Memory assets."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.domain.models import (
    CapacityStatus,
    NotebookImportSnapshot,
    NotebookParseReport,
    NotebookCellInfo,
    NotebookParseWarning,
    WorkspaceError,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_jsonable(value: Any) -> Any:
    """Lightweight serialiser for dataclasses → JSON."""
    if hasattr(value, "__dataclass_fields__"):
        return {k: _to_jsonable(getattr(value, k)) for k in value.__dataclass_fields__}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    return value


class NotebookRepository:
    """Reads and writes notebook import assets in Team Memory."""

    def __init__(self, repository_path: Path) -> None:
        self._root = repository_path

    # ── paths ──────────────────────────────────────────────────────

    @property
    def _originals_dir(self) -> Path:
        return self._root / "notebooks" / "originals"

    @property
    def _imports_dir(self) -> Path:
        return self._root / "notebooks" / "imports"

    def _original_path(self, fingerprint: str) -> Path:
        return self._originals_dir / f"{fingerprint[:12]}.ipynb"

    def _import_record_path(self, asset_id: str) -> Path:
        return self._imports_dir / f"{asset_id}.json"

    # ── store ──────────────────────────────────────────────────────

    def store_import(
        self,
        original_bytes: bytes,
        fingerprint: str,
        importer: str,
        source_description: str,
        parse_report: NotebookParseReport,
        original_filename: str,
        actor_id: str,
        capacity: CapacityStatus,
    ) -> NotebookImportSnapshot:
        asset_id = f"nbimp_{uuid.uuid4().hex[:12]}"
        self._originals_dir.mkdir(parents=True, exist_ok=True)
        self._imports_dir.mkdir(parents=True, exist_ok=True)

        original_path = self._original_path(fingerprint)
        if not original_path.exists():
            original_path.write_bytes(original_bytes)

        imported_at = _utc_now()
        has_blocking = any(w.blocking for w in parse_report.warnings)
        state = "parse_blocked" if has_blocking else "preserved"

        record = {
            "asset_id": asset_id,
            "schema_version": 1,
            "original_filename": original_filename,
            "stored_original_path": str(original_path.relative_to(self._root)),
            "content_fingerprint": fingerprint,
            "importer": importer,
            "imported_at": imported_at,
            "source_description": source_description,
            "actor_id": actor_id,
            "state": state,
            "parse_report": _to_jsonable(parse_report),
            "training_instance_id": None,
            "training_run_id": None,
            "error_code": None,
            "error_summary": None,
        }

        record_path = self._import_record_path(asset_id)
        record_path.write_text(
            json.dumps(record, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        return NotebookImportSnapshot(
            asset_id=asset_id,
            asset_path=str(record_path.relative_to(self._root)),
            original_path=original_filename,
            content_fingerprint=fingerprint,
            importer=importer,
            imported_at=imported_at,
            source_description=source_description,
            parse_report=parse_report,
            state=state,
        )

    # ── link instance ─────────────────────────────────────────────

    def link_instance(
        self,
        asset_id: str,
        instance_id: str,
        run_id: str,
    ) -> None:
        record_path = self._import_record_path(asset_id)
        if not record_path.exists():
            raise WorkspaceError(
                code="notebook_import_not_found",
                message=f"Notebook import {asset_id} not found.",
                next_action="Re-import the notebook.",
            )
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["training_instance_id"] = instance_id
        record["training_run_id"] = run_id
        record["state"] = "reproduced"
        record_path.write_text(
            json.dumps(record, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # ── mark failure ──────────────────────────────────────────────

    def mark_failure(
        self,
        asset_id: str,
        error_code: str,
        error_summary: str,
    ) -> None:
        record_path = self._import_record_path(asset_id)
        if not record_path.exists():
            return
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["state"] = "execution_failed"
        record["error_code"] = error_code
        record["error_summary"] = error_summary
        record_path.write_text(
            json.dumps(record, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # ── read ───────────────────────────────────────────────────────

    def get_import(self, asset_id: str) -> dict[str, Any]:
        record_path = self._import_record_path(asset_id)
        if not record_path.exists():
            raise WorkspaceError(
                code="notebook_import_not_found",
                message=f"Notebook import {asset_id} not found.",
                next_action="Re-import the notebook.",
            )
        return json.loads(record_path.read_text(encoding="utf-8"))

    def list_imports(self) -> list[dict[str, Any]]:
        if not self._imports_dir.exists():
            return []
        records = []
        for path in sorted(self._imports_dir.glob("*.json")):
            records.append(json.loads(path.read_text(encoding="utf-8")))
        return records

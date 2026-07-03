"""Layer 1 writer: raw_memory records (evidence + conclusion)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mlagent.errors import RecordExists
from mlagent.io import write_yaml
from mlagent.repo import require_memory_repo
from mlagent.schemas import RawMemoryRecord

RAW_DIRS = {
    "session": "sessions",
    "exploration": "explorations",
    "run": "runs",
    "human_note": "human_notes",
}


def add_raw_memory(root: Path, data: dict[str, Any], replace: bool = False) -> RawMemoryRecord:
    require_memory_repo(root)
    record = RawMemoryRecord(**data)
    path = root / "raw_memory" / RAW_DIRS[record.type] / f"{record.id}.yaml"
    if path.exists() and not replace:
        raise RecordExists(f"Raw memory record already exists: {path} (pass replace=True)")
    write_yaml(path, record.model_dump(exclude_none=True))
    return record

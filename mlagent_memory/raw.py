from __future__ import annotations

from pathlib import Path
from typing import Any

from mlagent_memory.errors import RecordExists
from mlagent_memory.io import write_yaml
from mlagent_memory.repo import require_memory_repo
from mlagent_memory.schemas import RawMemoryRecord


RAW_DIRS = {
    "session": "sessions",
    "exploration": "explorations",
    "run": "runs",
    "human_note": "human_notes",
}


def add_raw_memory(root: Path, data: dict[str, Any], replace: bool = False) -> RawMemoryRecord:
    require_memory_repo(root)
    record = RawMemoryRecord(**data)
    relative_dir = RAW_DIRS[record.type]
    path = root / "raw_memory" / relative_dir / f"{record.id}.yaml"
    if path.exists() and not replace:
        raise RecordExists(f"Raw memory record already exists: {path} (pass replace=True to overwrite)")
    write_yaml(path, record.model_dump(exclude_none=True))
    return record

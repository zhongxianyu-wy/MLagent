from __future__ import annotations

from pathlib import Path
from typing import Any

from mlagent_memory.errors import RecordExists
from mlagent_memory.io import write_yaml
from mlagent_memory.repo import require_memory_repo
from mlagent_memory.schemas import ExperienceRecord


EXPERIENCE_DIRS = {
    "lesson": "lessons",
    "pitfall": "pitfalls",
    "successful_pattern": "successful_patterns",
    "failed_direction": "failed_directions",
}


def add_experience(root: Path, data: dict[str, Any], replace: bool = False) -> ExperienceRecord:
    require_memory_repo(root)
    record = ExperienceRecord(**data)
    relative_dir = EXPERIENCE_DIRS[record.type]
    path = root / "experience" / relative_dir / f"{record.id}.yaml"
    if path.exists() and not replace:
        raise RecordExists(f"Experience record already exists: {path} (pass replace=True to overwrite)")
    write_yaml(path, record.model_dump(exclude_none=True))
    return record

"""Layer 2 writer: experience records (lessons/pitfalls/patterns/directions/conventions)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mlagent.errors import RecordExists
from mlagent.io import write_yaml
from mlagent.repo import require_memory_repo
from mlagent.schemas import ExperienceRecord

EXPERIENCE_DIRS = {
    "lesson": "lessons",
    "pitfall": "pitfalls",
    "successful_pattern": "successful_patterns",
    "failed_direction": "failed_directions",
    "convention": "conventions",
}


def add_experience(root: Path, data: dict[str, Any], replace: bool = False) -> ExperienceRecord:
    require_memory_repo(root)
    record = ExperienceRecord(**data)
    path = root / "experience" / EXPERIENCE_DIRS[record.type] / f"{record.id}.yaml"
    if path.exists() and not replace:
        raise RecordExists(f"Experience record already exists: {path} (pass replace=True)")
    write_yaml(path, record.model_dump(exclude_none=True))
    return record
